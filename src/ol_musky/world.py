"""World: the live state of all teams in one process.

All changes to the state occur in the event loop thread, in functions that do
not await. Thus each engine call is atomic, and no locks are necessary.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from random import Random

from ol_musky.engine import rules
from ol_musky.engine.clock import week_at
from ol_musky.engine.state import Hub, TeamState
from ol_musky.scenario import Scenario, ScenarioError, ScenarioStore


def utc_now() -> datetime:
    return datetime.now(UTC)


def hub_start_time(team: TeamState, hub: Hub, ms_per_week: int) -> datetime:
    """Real time of the last week for which the hub's mining is complete."""
    return team.start_time + timedelta(milliseconds=ms_per_week * hub.mined_through)


class World:
    def __init__(
        self,
        scenarios: ScenarioStore,
        clock: Callable[[], datetime] = utc_now,
        rng: Random | None = None,
    ) -> None:
        self.scenarios = scenarios
        self.clock = clock
        self.rng = rng or Random()
        self.teams: dict[str, TeamState] = {}
        # Tokens with changes that are not in the database.
        self.dirty: set[str] = set()
        # Tokens whose stored rows are out of date and must be replaced as a unit.
        self.stale: set[str] = set()

    @property
    def scenario(self) -> Scenario:
        scenario = self.scenarios.current
        if scenario is None:
            raise ScenarioError("no scenario is loaded")
        return scenario

    def register(self, token: str, name: str) -> TeamState:
        """Add a team, or start an existing team again: week 0, starting capital, no hubs."""
        team = rules.new_team(self.scenario, token, name, self.clock())
        self.teams[token] = team
        self.dirty.add(token)
        self.stale.add(token)
        return team

    def week_now(self, team: TeamState) -> int:
        return week_at(team.start_time, self.clock(), self.scenario.ms_per_week)

    def sync(self, team: TeamState) -> int:
        """Move the team forward to the current week. Returns the current week."""
        week = self.week_now(team)
        before = team.week
        rules.advance(self.scenario, team, week, self.rng)
        if team.week != before:
            self.dirty.add(team.token)
        return week

    def touch(self, team: TeamState) -> None:
        """Record that an action changed the team."""
        self.dirty.add(team.token)

    def tick(self) -> None:
        """Move all teams forward. Teams that send no requests continue to operate."""
        if self.scenarios.current is None:
            return
        for team in self.teams.values():
            self.sync(team)
