"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ol_musky import __version__
from ol_musky.api import mcp
from ol_musky.api.envelope import McpError, mcp_error_handler
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.db.scenario_repo import load_scenario
from ol_musky.scenario import ScenarioError, ScenarioStore
from ol_musky.settings import Settings

logger = logging.getLogger("ol_musky")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessions = make_session_factory(engine)
        app.state.scenarios = ScenarioStore()
        try:
            async with app.state.sessions() as session:
                scenario = await load_scenario(session, settings.scenario_id)
            app.state.scenarios.activate(scenario)
            logger.info(
                "scenario %s active: %d x %d sectors",
                scenario.scenario_id,
                scenario.rows,
                scenario.cols,
            )
        except ScenarioError as exc:
            logger.warning("no active scenario (%s); run `ol-musky load-scenario`", exc)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Ol' Musky MCP", version=__version__, lifespan=lifespan)
    app.add_exception_handler(McpError, mcp_error_handler)
    app.include_router(mcp.router)
    return app
