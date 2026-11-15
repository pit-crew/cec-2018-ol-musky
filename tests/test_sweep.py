"""Mining tests. They use no game play: no money, orders, deployment, or belt geometry."""

import ast
import inspect
from collections import Counter
from dataclasses import replace
from itertools import islice
from random import Random

import pytest

from ol_musky import sweep as sweep_module
from ol_musky.sweep import Asteroid, Hub, World, dig, sweep, weeks


def belt(*deposits: int, ore: str = "X") -> tuple[Asteroid, ...]:
    return tuple(Asteroid(ore, deposit) for deposit in deposits)


def nth(world: World, count: int) -> World:
    """The world after `count` weeks."""
    return next(islice(weeks(world), count, None))


def total_ore(world: World) -> int:
    in_belt = sum(asteroid.deposit for asteroid in world.asteroids)
    in_hubs = sum(sum(hub.hold.values()) for hub in world.hubs.values())
    return in_belt + in_hubs


# --- dig: one bot, one week ------------------------------------------------------------


@pytest.mark.parametrize(
    ("deposit", "free", "rate", "take"),
    [
        (1000, 5000, 100, 100),  # the rate is the limit
        (60, 5000, 100, 60),  # the deposit is the limit
        (1000, 30, 100, 30),  # the hub space is the limit
        (0, 5000, 100, 0),  # empty asteroid
        (1000, 0, 100, 0),  # full hub
        (1000, 5000, 0, 0),  # a bot that cannot mine
    ],
)
def test_dig_takes_the_smallest_limit(deposit, free, rate, take):
    hub = Hub(capacity=free + 200, hold=Counter(Y=200))
    asteroid, hub_after = dig(Asteroid("X", deposit), hub, rate)
    assert asteroid == Asteroid("X", deposit - take)
    assert hub_after.hold["X"] == take
    assert hub_after.hold["Y"] == 200
    assert hub_after.free == free - take


def test_dig_adds_to_the_ore_that_the_hub_holds():
    _, hub = dig(Asteroid("X", 1000), Hub(5000, Counter(X=300)), 100)
    assert hub.hold == {"X": 400}


def test_dig_of_nothing_leaves_no_entry_in_the_hold():
    _, hub = dig(Asteroid("X", 0), Hub(5000), 100)
    assert hub.hold == {}


def test_dig_does_not_change_its_inputs():
    asteroid, hub = Asteroid("X", 1000), Hub(5000, Counter(X=300))
    dig(asteroid, hub, 100)
    assert asteroid == Asteroid("X", 1000)
    assert hub == Hub(5000, Counter(X=300))


# --- sweep: one week -------------------------------------------------------------------


def test_sweep_with_no_miners_changes_only_the_week():
    world = World(asteroids=belt(1000, 2000), hubs={"A": Hub(5000)}, rate=100)
    assert sweep(world) == replace(world, week=1)


def test_one_bot_mines_its_asteroid():
    world = World(
        asteroids=belt(1000, 2000, 3000), hubs={"A": Hub(5000)}, miners={1: ("A",)}, rate=100
    )
    after = sweep(world)
    assert after.asteroids == belt(1000, 1900, 3000)
    assert after.hubs["A"].hold == {"X": 100}
    assert after.week == 1


def test_all_bots_of_a_hub_fill_the_same_hold():
    miners = {sector: ("A",) for sector in (0, 2, 3)}
    world = World(
        asteroids=belt(1000, 1000, 50, 1000), hubs={"A": Hub(5000)}, miners=miners, rate=100
    )
    after = sweep(world)
    assert after.asteroids == belt(900, 1000, 0, 900)
    assert after.hubs["A"].hold == {"X": 250}


def test_a_hub_holds_each_ore_type_separately_with_one_capacity():
    asteroids = (Asteroid("X", 1000), Asteroid("Y", 1000))
    world = World(asteroids, hubs={"A": Hub(450)}, miners={0: ("A",), 1: ("A",)}, rate=100)
    assert sweep(world).hubs["A"].hold == {"X": 100, "Y": 100}
    full = nth(world, 3)
    assert full.hubs["A"].hold == {"X": 250, "Y": 200}  # week 3: X takes 50 and fills the hub
    assert full.hubs["A"].free == 0


def test_mining_stops_when_the_hub_is_full_and_no_ore_is_lost():
    world = World(
        asteroids=belt(1000, 1000), hubs={"A": Hub(300)}, miners={0: ("A",), 1: ("A",)}, rate=100
    )
    full = nth(world, 2)
    assert full.hubs["A"].hold == {"X": 300}
    assert full.asteroids == belt(800, 900)  # sector sequence: sector 0 mines first
    assert nth(full, 10).asteroids == full.asteroids
    assert total_ore(nth(full, 10)) == 2000


def test_mining_stops_when_the_asteroid_is_empty():
    world = World(asteroids=belt(250), hubs={"A": Hub(5000)}, miners={0: ("A",)}, rate=100)
    assert [w.asteroids[0].deposit for w in islice(weeks(world), 5)] == [250, 150, 50, 0, 0]
    assert nth(world, 5).hubs["A"].hold == {"X": 250}


def test_the_sweep_goes_in_sector_sequence_not_in_placement_sequence():
    hubs = {"A": Hub(150)}
    first = World(asteroids=belt(1000, 1000), hubs=hubs, miners={0: ("A",), 1: ("A",)}, rate=100)
    second = replace(first, miners={1: ("A",), 0: ("A",)})
    assert sweep(first) == sweep(second)
    assert sweep(first).asteroids == belt(900, 950)


def test_bots_of_two_hubs_at_one_asteroid_share_the_deposit():
    world = World(
        asteroids=belt(150), hubs={"A": Hub(5000), "B": Hub(5000)}, miners={0: ("A", "B")}, rate=100
    )
    after = sweep(world)
    assert after.asteroids == belt(0)
    assert (after.hubs["A"].hold, after.hubs["B"].hold) == ({"X": 100}, {"X": 50})


def test_a_hub_with_no_bots_in_the_belt_does_not_mine():
    world = World(
        asteroids=belt(1000, 1000),
        hubs={"A": Hub(5000), "transit": Hub(5000, Counter(X=40))},
        miners={0: ("A",)},
        rate=100,
    )
    after = nth(world, 3)
    assert after.hubs["transit"] == world.hubs["transit"]
    assert after.asteroids[1] == world.asteroids[1]


def test_sweep_does_not_change_the_world_that_it_reads():
    world = World(asteroids=belt(1000), hubs={"A": Hub(5000)}, miners={0: ("A",)}, rate=100)
    copy = World(asteroids=belt(1000), hubs={"A": Hub(5000)}, miners={0: ("A",)}, rate=100)
    sweep(world)
    assert world == copy


# --- weeks: the stream of worlds -------------------------------------------------------


def test_weeks_starts_with_the_given_world():
    world = World(asteroids=belt(1000), hubs={"A": Hub(5000)}, miners={0: ("A",)}, rate=100)
    stream = weeks(world)
    assert next(stream) is world
    assert next(stream) == sweep(world)
    assert next(stream) == sweep(sweep(world))


def test_weeks_counts_the_weeks():
    world = World(asteroids=belt(1000), week=7)
    assert [w.week for w in islice(weeks(world), 4)] == [7, 8, 9, 10]


# --- Properties that hold for all worlds -----------------------------------------------


def random_world(rng: Random) -> World:
    sectors = rng.randint(1, 40)
    hub_ids = [f"H{n}" for n in range(rng.randint(1, 6))]
    return World(
        asteroids=tuple(
            Asteroid(rng.choice("XY"), rng.choice([0, rng.randint(1, 3000)]))
            for _ in range(sectors)
        ),
        hubs={hub_id: Hub(rng.randint(0, 4000)) for hub_id in hub_ids},
        miners={
            sector: tuple(rng.choices(hub_ids, k=rng.randint(1, 3)))
            for sector in rng.sample(range(sectors), rng.randint(0, sectors))
        },
        rate=rng.randint(0, 500),
    )


@pytest.mark.parametrize("seed", range(50))
def test_invariants(seed):
    world = random_world(Random(seed))
    start = total_ore(world)
    previous = world
    for current in islice(weeks(world), 1, 60):
        assert total_ore(current) == start  # ore is neither made nor lost
        assert all(asteroid.deposit >= 0 for asteroid in current.asteroids)
        assert all(0 <= hub.free <= hub.capacity for hub in current.hubs.values())
        assert all(  # a deposit never grows; a hold never shrinks
            now.deposit <= before.deposit
            for now, before in zip(current.asteroids, previous.asteroids, strict=True)
        )
        assert all(
            sum(current.hubs[hub_id].hold.values()) >= sum(previous.hubs[hub_id].hold.values())
            for hub_id in current.hubs
        )
        idle = set(range(len(current.asteroids))) - set(current.miners)
        assert all(current.asteroids[s] == world.asteroids[s] for s in idle)
        assert (current.miners, current.rate) == (world.miners, world.rate)
        previous = current


def test_mining_reaches_a_fixed_point():
    world = random_world(Random(7))
    end = nth(world, 500)
    assert sweep(end) == replace(end, week=end.week + 1)


# --- The design rule -------------------------------------------------------------------


def test_the_sweep_module_has_no_conditionals():
    tree = ast.parse(inspect.getsource(sweep_module))
    conditionals = [
        node for node in ast.walk(tree) if isinstance(node, ast.If | ast.IfExp | ast.Match)
    ]
    assert conditionals == []
