"""Time line tests. The events are test functions; only the last group uses placement."""

import ast
import inspect
from dataclasses import dataclass, replace
from itertools import islice

from ol_musky import timeline as timeline_module
from ol_musky.placement import Land, claim, ring
from ol_musky.timeline import fire, history, pending, schedule
from ol_musky.world import Asteroid, Hub, World


@dataclass(frozen=True)
class Add:
    """Test event: add a hub with the given ID. The capacity records the week of the event."""

    hub_id: str

    def __call__(self, world: World) -> World:
        return replace(world, hubs={**world.hubs, self.hub_id: Hub(capacity=world.week)})


@dataclass(frozen=True)
class Chain:
    """Test event: schedule a different event."""

    delay: int
    event: object

    def __call__(self, world: World) -> World:
        return schedule(world, self.delay, self.event)


def empty_world(week: int = 0) -> World:
    return World(asteroids=(Asteroid("X", 1000),), week=week)


def nth(world: World, count: int) -> World:
    return next(islice(history(world), count, None))


def test_schedule_puts_the_event_at_its_week():
    world = schedule(empty_world(week=10), 5, Add("A"))
    assert world.timeline == {15: (Add("A"),)}
    assert world.hubs == {}
    assert pending(world) == [(15, Add("A"))]


def test_schedule_does_not_change_the_world_that_it_reads():
    world = empty_world()
    schedule(world, 5, Add("A"))
    assert world.timeline == {}


def test_an_event_occurs_at_its_week_and_not_before():
    world = schedule(empty_world(), 3, Add("A"))
    assert nth(world, 2).hubs == {}
    assert pending(nth(world, 2)) == [(3, Add("A"))]
    at_three = nth(world, 3)
    assert at_three.hubs == {"A": Hub(capacity=3)}
    assert at_three.timeline == {}  # an event that occurred is removed
    assert nth(world, 10).hubs == at_three.hubs  # it occurs one time only


def test_events_of_one_week_occur_in_the_sequence_of_their_scheduling():
    @dataclass(frozen=True)
    class Rename:
        old: str
        new: str

        def __call__(self, world: World) -> World:
            hubs = {self.new if key == self.old else key: hub for key, hub in world.hubs.items()}
            return replace(world, hubs=hubs)

    world = schedule(schedule(empty_world(), 2, Add("A")), 2, Rename("A", "B"))
    assert list(nth(world, 2).hubs) == ["B"]
    world = schedule(schedule(empty_world(), 2, Rename("A", "B")), 2, Add("A"))
    assert list(nth(world, 2).hubs) == ["A"]


def test_events_of_different_weeks_occur_in_week_sequence():
    world = schedule(schedule(empty_world(), 5, Add("late")), 2, Add("early"))
    assert pending(world) == [(2, Add("early")), (5, Add("late"))]
    assert {hub_id: hub.capacity for hub_id, hub in nth(world, 5).hubs.items()} == {
        "early": 2,
        "late": 5,
    }


def test_a_delay_of_zero_applies_the_event_immediately():
    world = schedule(empty_world(week=4), 0, Add("A"))
    assert world.hubs == {"A": Hub(capacity=4)}
    assert world.timeline == {}
    assert schedule(empty_world(week=4), -3, Add("A")) == world


def test_an_event_can_schedule_an_event():
    world = schedule(empty_world(), 2, Chain(3, Add("A")))
    assert pending(nth(world, 2)) == [(5, Add("A"))]
    assert nth(world, 5).hubs == {"A": Hub(capacity=5)}

    world = schedule(empty_world(), 2, Chain(0, Add("A")))
    assert nth(world, 2).hubs == {"A": Hub(capacity=2)}


def test_fire_with_no_events_changes_nothing():
    world = schedule(empty_world(), 3, Add("A"))
    assert fire(world) == world


def test_history_starts_with_the_given_world_and_counts_the_weeks():
    world = empty_world(week=7)
    stream = history(world)
    assert next(stream) is world
    assert [w.week for w in islice(stream, 3)] == [8, 9, 10]


def test_the_timeline_module_has_no_conditionals():
    tree = ast.parse(inspect.getsource(timeline_module))
    assert [n for n in ast.walk(tree) if isinstance(n, ast.If | ast.IfExp | ast.Match)] == []


# --- The time line with placement and the sweep ----------------------------------------


def test_a_hub_that_lands_in_week_w_mines_for_the_first_time_in_week_w_plus_one():
    world = World(
        asteroids=tuple(Asteroid("X", 1000) for _ in range(25)),
        hubs={"A": Hub(5000)},
        rate=100,
        cols=5,
    )
    centre = 12
    world = schedule(claim(world, "A", centre), 3, Land("A"))

    in_transit = nth(world, 2)
    assert in_transit.miners == {} and in_transit.hubs["A"].hold == {}
    assert pending(in_transit) == [(3, Land("A"))]

    landed = nth(world, 3)
    assert set(landed.miners) == set(ring(world, centre))
    assert landed.hubs["A"].hold == {}
    assert landed.timeline == {}

    assert nth(world, 4).hubs["A"].hold == {"X": 800}
    assert nth(world, 6).hubs["A"].hold == {"X": 2400}
