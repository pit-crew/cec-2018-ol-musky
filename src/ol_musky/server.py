"""The HTTP server: the MCP API of the competition text (README.md).

All requests are GET with a `token` query parameter. Lists are comma-separated.
Each response is JSON: {"<action>": <data>, "status": <code>, "description": <text>}
with HTTP status 200. Status 0 is success.
"""

import os
from collections import Counter
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from ol_musky import game, league, ledger, placement, reports
from ol_musky.league import League, Team
from ol_musky.rejection import Rejected, require
from ol_musky.scenario import read_scenario, read_teams

TOKEN_REQUIRED = "token required - see competition coordinator"
BAD_TOKEN = "token must be 32 or fewer alpha-numerics"
LISTS_DIFFER = "hub list and sector_id list need to be the same length"
BAD_SECTOR = "sector IDs must be numeric"
BAD_HUB_ID = "hub IDs must be 8 or fewer alpha-numerics"

TIMES_UP = -1

# Status code of each rule. A rule can have a different code for each action.
CODES: dict[str, int | dict[str, int]] = {
    BAD_TOKEN: 1000,
    TOKEN_REQUIRED: 1001,
    league.UNKNOWN_TEAM: {"startup": 2100, "*": 1100},
    league.NOT_STARTED: 1102,
    game.GAME_IS_OVER: TIMES_UP,
    ledger.NOT_ENOUGH_MONEY: {"build_hubs": 2301, "ship_ore": 2503, "*": 2409},
    BAD_HUB_ID: 2302,
    game.HUB_EXISTS: 2302,
    game.HUB_ID_REPEATED: {"build_hubs": 2302, "*": 2402},
    game.NO_HUBS: {"build_hubs": 2302, "ship_ore": 2501, "*": 2400},
    LISTS_DIFFER: 2401,
    placement.UNKNOWN_HUB: {"ship_ore": 2504, "*": 2402},
    game.HUB_IN_TRANSIT: 2403,
    BAD_SECTOR: 2404,
    placement.OUTSIDE_THE_BELT: 2404,
    placement.PLACE_IS_TAKEN: 2407,
    placement.HUB_HAS_NO_PLACE: 2408,
    game.NO_ORE: 2502,
}


def status_code(rule: str, action: str) -> int:
    code = CODES[rule]
    return code if isinstance(code, int) else code.get(action, code["*"])


def envelope(action: str, data: Any, status: int = 0, description: str = "") -> JSONResponse:
    return JSONResponse({action: data, "status": status, "description": description})


def _clean(value: str) -> bool:
    return all(char.isalnum() or char in "-_" for char in value)


# --- Request data ----------------------------------------------------------------------


def get_league(request: Request) -> League:
    return request.app.state.league


Leagues = Annotated[League, Depends(get_league)]


def get_token(token: Annotated[str | None, Query()] = None) -> str:
    require(token is not None, TOKEN_REQUIRED)
    require(len(token) <= 32 and _clean(token), BAD_TOKEN)
    return token


Token = Annotated[str, Depends(get_token)]


def get_live_team(token: Token, league: Leagues) -> Team:
    """The team at its current week. Rejected when the clock is after the end of the game."""
    team = league.current(token)
    week = league.week_now(team)
    lifetime = team.world.terms.lifetime
    require(week <= lifetime, game.GAME_IS_OVER, {"week": week, "max": lifetime})
    return team


LiveTeam = Annotated[Team, Depends(get_live_team)]
ListParam = Annotated[str | None, Query()]


def hub_list(value: str | None) -> list[str]:
    hubs = [] if value is None else value.split(",")
    require(all(0 < len(hub) <= 8 and _clean(hub) for hub in hubs), BAD_HUB_ID)
    return hubs


def places(hubs: str | None, sector_ids: str | None) -> dict[str, int]:
    require(hubs is not None and sector_ids is not None, game.NO_HUBS)
    names, sectors = hub_list(hubs), sector_ids.split(",")
    require(len(names) == len(sectors), LISTS_DIFFER, abs(len(names) - len(sectors)))
    require(len(set(names)) == len(names), game.HUB_ID_REPEATED)
    require(all(sector.strip().lstrip("-").isdigit() for sector in sectors), BAD_SECTOR)
    return dict(zip(names, map(int, sectors), strict=True))


# --- Responses -------------------------------------------------------------------------


def team_view(team: Team) -> dict:
    return {
        "token": team.token,
        "name": team.name,
        "week": team.world.week,
        "start_time": str(team.start_time),
        "balance": ledger.balance(team.world),
    }


def status_view(team: Team) -> dict:
    status = reports.status(team.world)
    return {"team": team_view(team), "hubs": status["hubs"], "orders": status["orders"]}


# --- Routes ----------------------------------------------------------------------------

router = APIRouter(prefix="/mcp")


@router.get("/startup")
async def startup(token: Token, league: Leagues) -> JSONResponse:
    """Start the game of the team again: week 0, the starting capital, no hubs."""
    return envelope("startup", status_view(league.start(token)))


@router.get("/parameters")
async def parameters(_token: Token, league: Leagues) -> JSONResponse:
    scenario = league.scenario
    data = reports.parameters(scenario.new_world())
    return envelope("parameters", {**data, "ms_per_week": scenario.ms_per_week})


@router.get("/status_report")
async def status_report(team: LiveTeam) -> JSONResponse:
    return envelope("status_report", status_view(team))


@router.get("/final_report")
async def final_report(token: Token, league: Leagues) -> JSONResponse:
    """The status report and the ledger. It is available after the end of the game."""
    team = league.current(token)
    return envelope("final_report", {**status_view(team), "ledger": reports.ledger(team.world)})


@router.get("/get_ledger")
async def get_ledger(token: Token, league: Leagues) -> JSONResponse:
    return envelope("ledger", reports.ledger(league.current(token).world))


@router.get("/market_report")
async def market_report(team: LiveTeam) -> JSONResponse:
    return envelope("market_report", reports.market_report(team.world))


@router.get("/prospect_report")
async def prospect_report(team: LiveTeam) -> JSONResponse:
    return envelope("prospect_report", {"report": reports.prospect(team.world)})


@router.get("/build_hubs")
async def build_hubs(team: LiveTeam, league: Leagues, hubs: ListParam = None) -> JSONResponse:
    names = hub_list(hubs)
    after = league.command(team.token, lambda world: game.build(world, names))
    return envelope("build_hubs", {"hubs_built": len(names), "week": after.world.week})


@router.get("/deploy_hubs")
async def deploy_hubs(
    team: LiveTeam, league: Leagues, hubs: ListParam = None, sector_ids: ListParam = None
) -> JSONResponse:
    where = places(hubs, sector_ids)
    league.command(team.token, lambda world: game.deploy(world, where))
    return envelope("deploy_hubs", {"hubs_located": len(where)})


@router.get("/move_hubs")
async def move_hubs(
    team: LiveTeam, league: Leagues, hubs: ListParam = None, sector_ids: ListParam = None
) -> JSONResponse:
    where = places(hubs, sector_ids)
    league.command(team.token, lambda world: game.move(world, where))
    return envelope("move_hubs", {"hubs_located": len(where)})


@router.get("/ship_ore")
async def ship_ore(team: LiveTeam, league: Leagues, hubs: ListParam = None) -> JSONResponse:
    names = hub_list(hubs)
    known = set(names) & team.world.hubs.keys()
    load = sum((team.world.hubs[name].hold for name in known), Counter())
    league.command(team.token, lambda world: game.ship(world, names))
    return envelope("ship_ore", {"hubs_dumped": len(known), "ore": dict(load)})


# --- Application -----------------------------------------------------------------------


async def rejected(request: Request, error: Rejected) -> JSONResponse:
    action = request.url.path.rsplit("/", 1)[-1]
    code = status_code(error.rule, action)
    data = error.detail if isinstance(error.detail, dict) else {}
    key = "validation" if code < 2000 else action
    return envelope(key, data, code, "times up" if code == TIMES_UP else str(error))


def create_app(league: League) -> FastAPI:
    app = FastAPI(title="Ol' Musky MCP")
    app.state.league = league
    app.add_exception_handler(Rejected, rejected)
    app.include_router(router)
    return app


def app_from_files() -> FastAPI:
    """The application for `uvicorn --factory`. The file paths come from the environment."""
    scenario = read_scenario(Path(os.environ.get("OL_MUSKY_SCENARIO", "config/mcp.yaml")))
    this_league = League(scenario)
    teams = read_teams(Path(os.environ.get("OL_MUSKY_TEAMS", "config/teams.yaml")))
    for token, name in teams.items():
        this_league.register(token, name)
    return create_app(this_league)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "ol_musky.server:app_from_files",
        factory=True,
        host=os.environ.get("OL_MUSKY_HOST", "127.0.0.1"),
        port=int(os.environ.get("OL_MUSKY_PORT", "8000")),
    )
