"""Command-line interface: `ol-musky <command>`."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from ol_musky.db import migrate
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.db.scenario_repo import save_scenario
from ol_musky.scenario import Scenario, ScenarioError, read_scenario_file
from ol_musky.settings import Settings

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("init-db")
def init_db() -> None:
    """Create the database, or upgrade it to the latest schema."""
    settings = Settings()
    migrate.upgrade(settings)
    typer.echo(f"database ready: {settings.db_path}")


async def _store(settings: Settings, scenario: Scenario) -> None:
    engine = make_engine(settings)
    try:
        async with make_session_factory(engine)() as session:
            await save_scenario(session, scenario)
    finally:
        await engine.dispose()


@app.command("load-scenario")
def load_scenario(
    config: Annotated[
        Path | None, typer.Option(help="Scenario YAML file. Default: OL_MUSKY_SCENARIO_FILE.")
    ] = None,
) -> None:
    """Load a scenario and its belt into the database. This replaces the stored scenario."""
    settings = Settings()
    try:
        scenario = read_scenario_file(config or settings.scenario_file)
    except ScenarioError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    migrate.upgrade(settings)
    asyncio.run(_store(settings, scenario))
    typer.echo(
        f"scenario {scenario.scenario_id!r} loaded into {settings.db_path}: "
        f"{len(scenario.belt)} sectors ({scenario.rows} x {scenario.cols}), "
        f"{len(scenario.costs)} costs"
    )


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server."""
    import uvicorn

    migrate.upgrade(Settings())
    uvicorn.run("ol_musky.app:create_app", factory=True, host=host, port=port)
