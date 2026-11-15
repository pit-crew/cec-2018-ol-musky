"""The values that the engine transforms. All of them are immutable.

A world is the state of one player in one week. State is where things are:

- A hub that is in `sites` holds a place in the belt (its sector and the sectors
  adjacent to it). The hub is there, or it is in transit to that place.
- A hub whose bots are in `miners` mines.
- A hub that is in neither is idle.
- An event that is in `timeline` is pending. An event that occurred is not there.
- The balance is the total of the ledger. It is not stored.

There are no status flags.
"""

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Asteroid:
    """One element of the belt stream."""

    ore: str
    deposit: int  # tonnes that remain


@dataclass(frozen=True, slots=True)
class Hub:
    capacity: int  # tonnes, the total of all ore types
    hold: Counter[str] = field(default_factory=Counter)  # tonnes of each ore type

    @property
    def free(self) -> int:
        return self.capacity - sum(self.hold.values())


@dataclass(frozen=True, slots=True)
class Entry:
    """One line of the ledger. Money is in millions of dollars."""

    week: int
    item: str
    amount: float  # positive = credit, negative = debit


@dataclass(frozen=True, slots=True)
class Cost:
    rate: float  # millions of dollars for each hub; for shipping, for each 1000 tonnes
    weeks: int  # time from the command to its effect


@dataclass(frozen=True, slots=True)
class Terms:
    """The constants of one game."""

    lifetime: int  # weeks
    starting_capital: float
    hub_capacity: int  # tonnes
    build: Cost
    deploy: Cost
    move: Cost
    ship: Cost
    survey_passes: int = 7  # the prospecting survey covers the belt in this number of passes


@dataclass(frozen=True, slots=True)
class World:
    asteroids: tuple[Asteroid, ...]  # the belt: index = sector ID, row by row
    hubs: Mapping[str, Hub] = field(default_factory=dict)  # key = hub ID
    # Sparse, parallel to `asteroids`: sector ID -> the hub ID of each bot at that sector.
    miners: Mapping[int, tuple[str, ...]] = field(default_factory=dict)
    rate: int = 0  # tonnes that one bot mines in one week
    week: int = 0
    cols: int = 1  # width of the belt; the number of rows is len(asteroids) // cols
    sites: Mapping[str, int] = field(default_factory=dict)  # hub ID -> the sector that it holds
    # Sparse stream along time: week -> the events that occur at the start of that week.
    timeline: Mapping[int, tuple["Event", ...]] = field(default_factory=dict)
    ledger: tuple[Entry, ...] = ()
    terms: Terms | None = None
    seed: int = 0  # selects the survey noise of this world


# An event is a function from a world to a new world.
Event = Callable[[World], World]
