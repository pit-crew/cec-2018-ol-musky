"""Bot API under /mcp: the team endpoints.

All requests are GET with a `token` query parameter. Lists are comma-separated.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ol_musky.api import wire
from ol_musky.api.deps import ActiveScenario, KnownTeam, LiveTeam, Scenarios, Token, Worlds
from ol_musky.api.envelope import McpError, envelope
from ol_musky.engine import market, prospecting, rules
from ol_musky.engine.rules import RuleError

router = APIRouter(prefix="/mcp")

ListParam = Annotated[str | None, Query()]


def _split(value: str | None) -> list[str]:
    return [] if value is None else value.split(",")


# --- Start and constants ---------------------------------------------------------------


@router.get("/startup")
async def startup(token: Token, world: Worlds, scenario: ActiveScenario) -> JSONResponse:
    """Start the team again: week 0, starting capital, no hubs, no history."""
    known = world.teams.get(token)
    if known is None:
        raise McpError("Exception - startup", 2100, f"no team found for token {token}")
    team = world.register(known.token, known.name)
    return envelope("startup", wire.session_dict(team, scenario, orders_key="pending_orders"))


@router.get("/parameters")
async def parameters(_token: Token, scenarios: Scenarios) -> JSONResponse:
    scenario = scenarios.current
    if scenario is None:
        raise McpError("parameters", 2200, "no scenario is loaded")
    return envelope("parameters", scenario.parameters_dict())


# --- Reports ---------------------------------------------------------------------------


@router.get("/status_report")
async def status_report(team: LiveTeam, scenario: ActiveScenario) -> JSONResponse:
    return envelope("status_report", wire.session_dict(team, scenario))


@router.get("/final_report")
async def final_report(token: Token, world: Worlds, scenario: ActiveScenario) -> JSONResponse:
    """The status report and the ledger, with no time limit check.

    An unknown team gets an empty report.
    """
    team = world.teams.get(token)
    if team is None:
        return envelope("final_report", {})
    world.sync(team)
    report = wire.session_dict(team, scenario)
    report["ledger"] = [wire.ledger_dict(entry) for entry in team.ledger]
    return envelope("final_report", report)


@router.get("/get_ledger")
async def get_ledger(team: KnownTeam) -> JSONResponse:
    return envelope("ledger", [wire.ledger_dict(entry) for entry in team.ledger])


@router.get("/market_report")
async def market_report(team: LiveTeam) -> JSONResponse:
    return envelope("market_report", market.market_report(team.week))


@router.get("/prospect_report")
async def prospect_report(team: LiveTeam, world: Worlds, scenario: ActiveScenario) -> JSONResponse:
    report = prospecting.prospect_report(scenario, team.week, world.rng)
    return envelope("prospect_report", {"report": report})


# --- Actions ---------------------------------------------------------------------------


@router.get("/build_hubs")
async def build_hubs(
    team: LiveTeam, world: Worlds, scenario: ActiveScenario, hubs: ListParam = None
) -> JSONResponse:
    result = rules.build_hubs(scenario, team, _split(hubs))
    world.touch(team)
    return envelope("build_hubs", result)


def _locate_args(action: str, hubs: str | None, sector_ids: str | None):
    if hubs is None or sector_ids is None:
        raise RuleError(action, 2400, "hub list and sector_id list need to be the same length")
    try:
        return _split(hubs), [int(sector_id) for sector_id in _split(sector_ids)]
    except ValueError:
        raise RuleError(action, 2404, "sector IDs must be numeric") from None


@router.get("/deploy_hubs")
async def deploy_hubs(
    team: LiveTeam,
    world: Worlds,
    scenario: ActiveScenario,
    hubs: ListParam = None,
    sector_ids: ListParam = None,
) -> JSONResponse:
    action = "deploy hubs"
    result = rules.deploy_hubs(scenario, team, *_locate_args(action, hubs, sector_ids))
    world.touch(team)
    return envelope(action, result)


@router.get("/move_hubs")
async def move_hubs(
    team: LiveTeam,
    world: Worlds,
    scenario: ActiveScenario,
    hubs: ListParam = None,
    sector_ids: ListParam = None,
) -> JSONResponse:
    action = "move hubs"
    result = rules.move_hubs(scenario, team, *_locate_args(action, hubs, sector_ids))
    world.touch(team)
    return envelope(action, result)


@router.get("/ship_ore")
async def ship_ore(
    team: LiveTeam,
    world: Worlds,
    scenario: ActiveScenario,
    hubs: ListParam = None,
    insured: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    is_insured = insured is not None and insured.lower() == "true"
    result = rules.ship_ore(scenario, team, _split(hubs), is_insured)
    world.touch(team)
    return envelope("ship_ore", result)
