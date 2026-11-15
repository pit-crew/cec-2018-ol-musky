"""FastAPI application factory."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from random import Random

from fastapi import FastAPI

from ol_musky import __version__
from ol_musky.api import mcp
from ol_musky.api.envelope import McpError, mcp_error_handler, unexpected_error_handler
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.db.scenario_repo import load_scenario
from ol_musky.db.team_repo import TeamStore
from ol_musky.engine.rules import RuleError
from ol_musky.scenario import ScenarioError, ScenarioStore
from ol_musky.settings import Settings
from ol_musky.world import World, utc_now

logger = logging.getLogger("ol_musky")

MIN_TICK_SECONDS = 0.02


async def _run_ticks(world: World) -> None:
    """Move all teams forward two times for each MCP week."""
    while True:
        scenario = world.scenarios.current
        ms_per_week = scenario.ms_per_week if scenario else 1000
        await asyncio.sleep(max(ms_per_week / 2000, MIN_TICK_SECONDS))
        try:
            world.tick()
        except Exception:
            logger.exception("tick failed")


async def _run_flushes(store: TeamStore, world: World, interval_seconds: float) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await store.flush(world)
        except Exception:
            logger.exception("database flush failed")


def create_app(
    settings: Settings | None = None, clock: Callable[[], datetime] = utc_now
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings)
        sessions = make_session_factory(engine)
        scenarios = ScenarioStore()
        world = World(scenarios, clock=clock, rng=Random(settings.random_seed))
        store = TeamStore(sessions)
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessions = sessions
        app.state.scenarios = scenarios
        app.state.world = world
        app.state.team_store = store

        try:
            async with sessions() as session:
                scenario = await load_scenario(session, settings.scenario_id)
            scenarios.activate(scenario)
            # Each team starts again when the server starts. Recovery of a game is not supplied.
            for token, name in await store.registered():
                world.register(token, name)
            logger.info(
                "scenario %s active: %d x %d sectors, %d teams",
                scenario.scenario_id,
                scenario.rows,
                scenario.cols,
                len(world.teams),
            )
        except ScenarioError as exc:
            logger.warning("no active scenario (%s); run `ol-musky load-scenario`", exc)

        tasks = [
            asyncio.create_task(_run_ticks(world)),
            asyncio.create_task(_run_flushes(store, world, settings.flush_interval_ms / 1000)),
        ]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task
            try:
                world.tick()
                await store.flush(world)
            except Exception:
                logger.exception("last database flush failed")
            await engine.dispose()

    app = FastAPI(title="Ol' Musky MCP", version=__version__, lifespan=lifespan)
    app.add_exception_handler(McpError, mcp_error_handler)
    app.add_exception_handler(RuleError, mcp_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(mcp.router)
    return app
