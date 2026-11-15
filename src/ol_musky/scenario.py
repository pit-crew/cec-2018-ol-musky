"""Scenario files: the constants and the belt of a game.

A scenario is a YAML file (see config/mcp.yaml) that names a belt file. The belt
file has one line for each sector, `ore,deposit`, row by row.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from ol_musky import market
from ol_musky.game import new_game
from ol_musky.world import Asteroid, Cost, Terms, World


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    asteroids: tuple[Asteroid, ...]
    cols: int
    rate: int  # tonnes that one bot mines in one week
    terms: Terms
    ms_per_week: int  # real time of one week

    def new_world(self, seed: int = 0) -> World:
        return new_game(self.asteroids, self.cols, self.rate, self.terms, seed)


def read_belt(path: Path) -> tuple[Asteroid, ...]:
    lines = [line.split(",") for line in path.read_text().splitlines() if line.strip()]
    return tuple(Asteroid(ore.strip(), int(deposit)) for ore, deposit in lines)


def read_scenario(path: Path) -> Scenario:
    cfg = yaml.safe_load(path.read_text())
    constants, costs, belt = cfg["constants"], cfg["costs"], cfg["belt"]
    asteroids = read_belt(path.parent / belt["file"])

    sectors = belt["rows"] * belt["cols"]
    if len(asteroids) != sectors:
        raise ValueError(f"{path}: the belt has {len(asteroids)} sectors, not {sectors}")
    unknown = {asteroid.ore for asteroid in asteroids} - market.prices(0).keys()
    if unknown:
        raise ValueError(f"{path}: the belt has ore with no market price: {sorted(unknown)}")
    if min(asteroid.deposit for asteroid in asteroids) < 0:
        raise ValueError(f"{path}: the belt has a deposit that is less than zero")

    def cost(item: str) -> Cost:
        return Cost(rate=costs[item]["rate"], weeks=costs[item]["weeks"])

    return Scenario(
        name=cfg["scenario_id"],
        asteroids=asteroids,
        cols=belt["cols"],
        rate=constants["mining_rate"],
        ms_per_week=constants["ms_per_week"],
        terms=Terms(
            lifetime=constants["lifetime"],
            starting_capital=constants["starting_capital"],
            hub_capacity=constants["hub_capacity"],
            build=cost("hub"),
            deploy=cost("deploy"),
            move=cost("move"),
            ship=cost("ship"),
            survey_passes=belt.get("prospecting_offset", 7),
        ),
    )


def read_teams(path: Path) -> dict[str, str]:
    """Teams file: API token -> team name. A file that is absent gives no teams."""
    if not path.exists():
        return {}
    return {
        str(token): str(name) for token, name in (yaml.safe_load(path.read_text()) or {}).items()
    }
