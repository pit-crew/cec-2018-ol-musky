"""The clock of a team.

There is no universal clock. Each team has a start time, and its current week
is the number of full weeks from that time. A world is not moved forward by a
timer: `catch_up` calculates the world of the current week when something asks
for it. The result is the same for one request after 100 weeks and for 100
requests, because `advance` goes one week at a time.
"""

from datetime import datetime, timedelta
from functools import reduce

from ol_musky.timeline import advance
from ol_musky.world import World


def week_at(start_time: datetime, now: datetime, ms_per_week: int) -> int:
    """The number of full weeks from start_time to now."""
    return max((now - start_time) // timedelta(milliseconds=ms_per_week), 0)


def catch_up(world: World, week: int) -> World:
    """The world at the given week, or at the last week of the game if that is before it."""
    target = min(week, world.terms.lifetime)
    return reduce(lambda w, _: advance(w), range(world.week, target), world)
