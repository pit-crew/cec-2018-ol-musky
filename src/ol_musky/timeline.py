"""The time line: events that occur at a given week.

`world.timeline` is a sparse stream along time: at each week, the events that
occur at the start of that week. An event is a function from a world to a new
world, for example the arrival of a hub at its place.

`advance` is the full step of one week:

    advance(world) = fire(sweep(world))

First the bots that were in the belt during the week mine. Then the events of
the new week occur. Thus a hub that lands in week W mines for the first time in
the sweep that makes week W + 1.

An event that occurs is removed from the time line. There is no "complete"
flag, and nothing examines events that are not due: `fire` reads one index.
As in the sweep, this module has no conditional statements.

An event must not be rejected when it occurs. The command that schedules an
event makes sure that the event stays valid until its week.
"""

from collections.abc import Iterator
from dataclasses import replace
from functools import reduce

from ol_musky.sweep import sweep, weeks
from ol_musky.world import Event, World


def fire(world: World) -> World:
    """Apply the events of the current week, in the sequence of their scheduling."""
    events = world.timeline.get(world.week, ())
    later = {week: due for week, due in world.timeline.items() if week != world.week}
    return reduce(lambda w, event: event(w), events, replace(world, timeline=later))


def schedule(world: World, delay: int, event: Event) -> World:
    """Add an event `delay` weeks from now. A delay of zero applies the event immediately."""
    week = world.week + max(delay, 0)
    timeline = {**world.timeline, week: (*world.timeline.get(week, ()), event)}
    return fire(replace(world, timeline=timeline))


def advance(world: World) -> World:
    """The world of the next week: mining, then the events of that week."""
    return fire(sweep(world))


def history(world: World) -> Iterator[World]:
    """The stream of worlds: world, advance(world), advance(advance(world)), ..."""
    return weeks(world, advance)


def pending(world: World) -> list[tuple[int, Event]]:
    """The events that did not occur yet, as (week, event), in the sequence of their weeks."""
    return [(week, event) for week in sorted(world.timeline) for event in world.timeline[week]]
