from datetime import UTC, datetime
from random import Random

import pytest

from ol_musky.engine import rules
from ol_musky.scenario import CostSpec, Scenario, Sector

ROWS, COLS = 10, 20
START = datetime(2018, 3, 9, tzinfo=UTC)


def make_scenario(**changes) -> Scenario:
    """A small scenario: 10 x 20 belt, 1000 tonnes of X in each sector, Y in row 9."""
    belt = [Sector(ore_id="X", deposit_amt=1000) for _ in range(ROWS * COLS)]
    for sector_id in range(9 * COLS, 10 * COLS):
        belt[sector_id] = Sector(ore_id="Y", deposit_amt=1000)
    fields = {
        "scenario_id": "test",
        "lifetime": 100,
        "rows": ROWS,
        "cols": COLS,
        "hub_capacity": 2000,
        "mining_rate": 100,
        "starting_capital": 100,
        "ms_per_week": 200,
        "prospecting_offset": 7,
        "costs": {
            "hub": CostSpec(item="hub", weeks=2, rate=10),
            "deploy": CostSpec(item="deploy", weeks=3, rate=5),
            "ship": CostSpec(item="ship", weeks=4, rate=2),
            "move": CostSpec(item="move", weeks=1, rate=1),
        },
        "belt": tuple(belt),
    }
    fields.update(changes)
    return Scenario(**fields)


@pytest.fixture
def scenario() -> Scenario:
    return make_scenario()


@pytest.fixture
def rng() -> Random:
    return Random(2018)


@pytest.fixture
def team(scenario):
    return rules.new_team(scenario, "token", "testgremlins", START)


class Game:
    """Test helper: one team in one scenario."""

    def __init__(self, scenario, team, rng):
        self.scenario, self.team, self.rng = scenario, team, rng

    def advance(self, weeks: int) -> None:
        rules.advance(self.scenario, self.team, self.team.week + weeks, self.rng)

    def build(self, *hub_ids):
        return rules.build_hubs(self.scenario, self.team, list(hub_ids))

    def deploy(self, placements: dict):
        return rules.deploy_hubs(
            self.scenario, self.team, list(placements), list(placements.values())
        )

    def move(self, placements: dict):
        return rules.move_hubs(
            self.scenario, self.team, list(placements), list(placements.values())
        )

    def ship(self, *hub_ids, insured=False):
        return rules.ship_ore(self.scenario, self.team, list(hub_ids), insured)

    def with_deployed(self, placements: dict) -> "Game":
        """Build and deploy hubs, then advance to the week in which they become active."""
        self.build(*placements)
        self.advance(self.scenario.costs["hub"].weeks)
        self.deploy(placements)
        self.advance(self.scenario.costs["deploy"].weeks)
        return self


@pytest.fixture
def game(scenario, team, rng) -> Game:
    return Game(scenario, team, rng)


def sector(row: int, col: int) -> int:
    return row * COLS + col
