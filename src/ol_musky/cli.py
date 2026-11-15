"""Command-line interface: `ol-musky <command>`."""

import asyncio
import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from ol_musky.db import migrate
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.db.scenario_repo import save_scenario
from ol_musky.db.team_repo import TeamStore, add_team
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


def _make_token(name: str, key: str) -> str:
    """Token from a name and a secret key: the first 32 hex digits of HMAC-SHA1(key, name)."""
    digest = hmac.new(key.encode("ascii"), name.encode("ascii"), hashlib.sha1)
    return digest.hexdigest()[:32]


@app.command("register-team")
def register_team(
    name: str,
    key: Annotated[
        str | None, typer.Option(help="Secret key: token = HMAC-SHA1(key, name).")
    ] = None,
    token: Annotated[str | None, typer.Option(help="Use this token.")] = None,
) -> None:
    """Add a team to the database and print its token. Start the server again to use it."""
    if not name or len(name) > 32 or not all(c.isalnum() or c in "-_" for c in name):
        typer.echo("error: name must be 32 or fewer alpha-numerics", err=True)
        raise typer.Exit(1)
    token = token or (_make_token(name, key) if key else secrets.token_hex(16))
    if len(token) > 32 or not all(c.isalnum() or c in "-_" for c in token):
        typer.echo("error: token must be 32 or fewer alpha-numerics", err=True)
        raise typer.Exit(1)

    settings = Settings()
    migrate.upgrade(settings)

    async def run() -> None:
        engine = make_engine(settings)
        try:
            async with make_session_factory(engine)() as session:
                await add_team(
                    session, token, name, {"week": 0, "start_time": datetime.now(UTC), "balance": 0}
                )
        finally:
            await engine.dispose()

    asyncio.run(run())
    typer.echo(token)


@app.command("list-teams")
def list_teams() -> None:
    """Print the token and name of each team in the database."""
    settings = Settings()
    migrate.upgrade(settings)

    async def run() -> list[tuple[str, str]]:
        engine = make_engine(settings)
        try:
            return await TeamStore(make_session_factory(engine)).registered()
        finally:
            await engine.dispose()

    for team_token, team_name in asyncio.run(run()):
        typer.echo(f"{team_token}  {team_name}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server."""
    import uvicorn

    migrate.upgrade(Settings())
    uvicorn.run("ol_musky.app:create_app", factory=True, host=host, port=port)
