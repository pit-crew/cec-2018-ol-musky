"""The spectator view: the belt and what all teams do.

A spectator sees the ore of the belt at the start of a game, where the hubs of
each team mine, and the week and the balance of each team. The view has no API
tokens. The players do not have access to the spectator screen.
"""

from ol_musky.league import League, Team
from ol_musky.ledger import balance
from ol_musky.placement import hub_state
from ol_musky.world import World


def _hubs(world: World) -> list[dict]:
    return [
        {
            "hub_id": hub_id,
            "state": hub_state(world, hub_id).value,
            "sector_id": world.sites.get(hub_id),
            "fill": 100 - int(100 * hub.free / hub.capacity),  # percent
        }
        for hub_id, hub in world.hubs.items()
    ]


def _waiting(team: Team) -> dict:
    return {"name": team.name, "state": "waiting"}


def _playing(league: League, team: Team) -> dict:
    team = league.current(team.token)
    world = team.world
    over = league.week_now(team) > world.terms.lifetime
    return {
        "name": team.name,
        "state": "finished" if over else "playing",
        "week": world.week,
        "balance": balance(world),
        "hubs": _hubs(world),
    }


def belt(league: League) -> dict:
    """The belt of the scenario at the start of a game: the ore and the deposit of each sector."""
    scenario = league.scenario
    return {
        "rows": len(scenario.asteroids) // scenario.cols,
        "cols": scenario.cols,
        "ores": "".join(asteroid.ore for asteroid in scenario.asteroids),
        "deposits": [asteroid.deposit for asteroid in scenario.asteroids],
    }


def snapshot(league: League) -> dict:
    """The state of all teams at this time. Each team that plays moves forward to its week."""
    scenario = league.scenario
    teams = sorted(league.teams.values(), key=lambda team: team.name.lower())
    return {
        "scenario": scenario.name,
        "rows": len(scenario.asteroids) // scenario.cols,
        "cols": scenario.cols,
        "lifetime": scenario.terms.lifetime,
        "starting_capital": scenario.terms.starting_capital,
        "ms_per_week": scenario.ms_per_week,
        "teams": [
            _waiting(team) if team.world is None else _playing(league, team) for team in teams
        ],
    }
