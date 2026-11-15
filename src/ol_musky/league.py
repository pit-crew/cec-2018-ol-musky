"""The league: the teams of a server and their games.

This is the only place that holds state that changes. A team is an immutable
value; the league replaces it when the team starts, when time moves its world
forward, and when a command gives a new world.

Each team has its own clock. The clock starts when the team starts, and the
team can start again at any time. No timer moves the worlds: the league
calculates the world of the current week when a request asks for it.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from ol_musky.clock import catch_up, week_at
from ol_musky.rejection import Rejected
from ol_musky.scenario import Scenario
from ol_musky.world import World

UNKNOWN_TEAM = "unknown team"
NOT_STARTED = "team has not started"


def utc_now() -> datetime:
    return datetime.now(UTC)


def random_seed() -> int:
    return secrets.randbits(32)


@dataclass(frozen=True, slots=True)
class Team:
    token: str
    name: str
    start_time: datetime | None = None  # None: the team did not start
    world: World | None = None


class League:
    def __init__(
        self,
        scenario: Scenario,
        clock: Callable[[], datetime] = utc_now,
        seeds: Callable[[], int] = random_seed,
        on_finish: Callable[[Team], None] | None = None,
    ) -> None:
        self.scenario = scenario
        self.clock = clock
        self.seeds = seeds
        # Called one time for each game, when something reads the team after the end of its game.
        self.on_finish = on_finish
        self.teams: dict[str, Team] = {}
        self._reported: set[str] = set()  # tokens whose game in progress was given to on_finish

    def register(self, token: str, name: str) -> Team:
        """Add a team. It has no game until it starts."""
        self.teams[token] = Team(token, name)
        return self.teams[token]

    def team(self, token: str) -> Team:
        if token not in self.teams:
            raise Rejected(UNKNOWN_TEAM, token)
        return self.teams[token]

    def start(self, token: str) -> Team:
        """Start the clock of the team with a new world. A game in progress is discarded."""
        team = self.team(token)
        world = self.scenario.new_world(self.seeds())
        self.teams[token] = replace(team, start_time=self.clock(), world=world)
        self._reported.discard(token)
        return self.teams[token]

    def is_finished(self, team: Team) -> bool:
        """True when the clock of the team is after the last week of its game."""
        return self.week_now(team) > team.world.terms.lifetime

    def unreported(self) -> list[Team]:
        """The teams with a game that was not given to on_finish, at their current week."""
        tokens = [t for t, team in self.teams.items() if team.world is not None]
        return [self.current(t) for t in tokens if t not in self._reported]

    def week_now(self, team: Team) -> int:
        """The week on the clock of the team. It continues after the end of the game."""
        return week_at(team.start_time, self.clock(), self.scenario.ms_per_week)

    def current(self, token: str) -> Team:
        """The team with its world at the current week (or the last week of the game)."""
        team = self.team(token)
        if team.world is None:
            raise Rejected(NOT_STARTED, token)
        team = replace(team, world=catch_up(team.world, self.week_now(team)))
        self.teams[token] = team
        if self.on_finish and token not in self._reported and self.is_finished(team):
            self._reported.add(token)
            self.on_finish(team)
        return team

    def command(self, token: str, command: Callable[[World], World]) -> Team:
        """Apply a command to the current world of the team."""
        team = self.current(token)
        self.teams[token] = replace(team, world=command(team.world))
        return self.teams[token]
