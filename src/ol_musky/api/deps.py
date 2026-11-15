"""Request dependencies."""

from typing import Annotated

from fastapi import Depends, Query, Request

from ol_musky.api.envelope import McpError
from ol_musky.engine import rules
from ol_musky.engine.state import TeamState
from ol_musky.scenario import Scenario, ScenarioStore
from ol_musky.world import World

MAX_TOKEN_LENGTH = 32


def _is_clean(value: str) -> bool:
    return all(char.isalnum() or char in "-_" for char in value)


def require_token(token: Annotated[str | None, Query()] = None) -> str:
    """Check the format of the `token` query parameter (status codes 1000 and 1001)."""
    if token is None:
        raise McpError("validation", 1001, "token required - see competition coordinator")
    if len(token) > MAX_TOKEN_LENGTH or not _is_clean(token):
        raise McpError("validation", 1000, "token must be 32 or fewer alpha-numerics")
    return token


Token = Annotated[str, Depends(require_token)]


def get_scenario_store(request: Request) -> ScenarioStore:
    return request.app.state.scenarios


Scenarios = Annotated[ScenarioStore, Depends(get_scenario_store)]


def get_world(request: Request) -> World:
    return request.app.state.world


Worlds = Annotated[World, Depends(get_world)]


def get_scenario(scenarios: Scenarios) -> Scenario:
    scenario = scenarios.current
    if scenario is None:
        raise McpError("validation", 2200, "no scenario is loaded")
    return scenario


ActiveScenario = Annotated[Scenario, Depends(get_scenario)]


def get_team(token: Token, world: Worlds, _scenario: ActiveScenario) -> TeamState:
    """The team for the token, moved forward to the current week or the end of the game."""
    team = world.teams.get(token)
    if team is None:
        raise McpError("validation", 1100, f"no team for token {token}")
    world.sync(team)
    return team


KnownTeam = Annotated[TeamState, Depends(get_team)]


def get_live_team(team: KnownTeam, world: Worlds, scenario: ActiveScenario) -> TeamState:
    """The team for the token, at the current week. Rejects a request after the end."""
    week = world.week_now(team)
    if rules.is_over(scenario, week):
        raise McpError("validation", -1, "times up", {"week": week, "max": scenario.lifetime})
    return team


LiveTeam = Annotated[TeamState, Depends(get_live_team)]
