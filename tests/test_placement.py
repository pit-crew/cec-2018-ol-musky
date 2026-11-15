"""Placement tests. They use the sweep to show the effect, and no time line or money."""

from collections import Counter
from itertools import islice
from random import Random

import pytest

from ol_musky import placement
from ol_musky.placement import Land, claim, claim_all, footprint, land, lift, ring
from ol_musky.rejection import Rejected
from ol_musky.sweep import sweep, weeks
from ol_musky.world import Asteroid, Hub, World

COLS, ROWS = 9, 5


def sector(row: int, col: int) -> int:
    return row * COLS + col


CENTRE = sector(2, 2)


@pytest.fixture
def world() -> World:
    """A 5 x 9 belt with 1000 tonnes of X in each sector, and three idle hubs."""
    return World(
        asteroids=tuple(Asteroid("X", 1000) for _ in range(ROWS * COLS)),
        hubs={hub_id: Hub(5000) for hub_id in "ABC"},
        rate=100,
        cols=COLS,
    )


def rejected(rule: str, command, *args) -> Rejected:
    with pytest.raises(Rejected) as info:
        command(*args)
    assert info.value.rule == rule
    return info.value


# --- Geometry --------------------------------------------------------------------------


def test_ring_of_an_interior_sector(world):
    assert sorted(ring(world, CENTRE)) == [
        sector(1, 1), sector(1, 2), sector(1, 3),
        sector(2, 1), sector(2, 3),
        sector(3, 1), sector(3, 2), sector(3, 3),
    ]  # fmt: skip


def test_ring_at_the_limits_of_the_belt(world):
    assert sorted(ring(world, 0)) == [1, COLS, COLS + 1]
    assert len(ring(world, sector(0, 4))) == 5
    assert len(ring(world, sector(2, COLS - 1))) == 5
    last = ROWS * COLS - 1
    assert sorted(ring(world, last)) == [last - COLS - 1, last - COLS, last - 1]


def test_the_belt_does_not_wrap(world):
    assert sector(1, COLS - 1) not in ring(world, sector(2, 0))


def test_footprint_is_the_sector_and_its_ring(world):
    assert footprint(world, CENTRE) == {CENTRE, *ring(world, CENTRE)}
    assert len(footprint(world, CENTRE)) == 9


# --- claim -----------------------------------------------------------------------------


def test_claim_holds_a_place_and_puts_no_bots_in_the_belt(world):
    after = claim(world, "A", CENTRE)
    assert after.sites == {"A": CENTRE}
    assert after.miners == {}
    assert placement.taken(after) == footprint(world, CENTRE)
    assert world.sites == {}  # the world that the command read is not changed


def test_claim_rules(world):
    rejected(placement.UNKNOWN_HUB, claim, world, "Z", CENTRE)
    rejected(placement.OUTSIDE_THE_BELT, claim, world, "A", -1)
    rejected(placement.OUTSIDE_THE_BELT, claim, world, "A", ROWS * COLS)
    placed = claim(world, "A", CENTRE)
    rejected(placement.HUB_HAS_A_PLACE, claim, placed, "A", sector(2, 7))


@pytest.mark.parametrize("other", [CENTRE, sector(2, 3), sector(3, 3), sector(2, 4), sector(4, 4)])
def test_footprints_must_not_touch(world, other):
    placed = claim(world, "A", CENTRE)
    error = rejected(placement.PLACE_IS_TAKEN, claim, placed, "B", other)
    assert set(error.detail) == footprint(world, CENTRE) & footprint(world, other)


def test_footprints_three_sectors_apart_are_permitted(world):
    placed = claim(claim(world, "A", CENTRE), "B", sector(2, 5))
    assert placed.sites == {"A": CENTRE, "B": sector(2, 5)}


def test_the_place_of_a_hub_in_transit_is_taken(world):
    in_transit = claim(world, "A", CENTRE)  # claimed, and not landed
    assert not placement.is_mining(in_transit, "A")
    rejected(placement.PLACE_IS_TAKEN, claim, in_transit, "B", sector(2, 4))


def test_claim_all_is_all_or_nothing(world):
    assert claim_all(world, {"A": CENTRE, "B": sector(2, 5)}).sites == {
        "A": CENTRE,
        "B": sector(2, 5),
    }
    rejected(placement.PLACE_IS_TAKEN, claim_all, world, {"A": CENTRE, "B": sector(2, 4)})
    rejected(placement.UNKNOWN_HUB, claim_all, world, {"A": CENTRE, "Z": sector(2, 5)})
    assert world.sites == {}
    assert claim_all(world, {}) == world


# --- land ------------------------------------------------------------------------------


def test_land_puts_one_bot_on_each_adjacent_sector(world):
    landed = land(claim(world, "A", CENTRE), "A")
    assert landed.miners == {cell: ("A",) for cell in ring(world, CENTRE)}
    assert CENTRE not in landed.miners
    assert placement.is_mining(landed, "A")


def test_a_hub_at_the_corner_has_three_bots(world):
    landed = land(claim(world, "A", 0), "A")
    assert sorted(landed.miners) == [1, COLS, COLS + 1]


def test_land_rules(world):
    rejected(placement.HUB_HAS_NO_PLACE, land, world, "A")
    landed = land(claim(world, "A", CENTRE), "A")
    rejected(placement.HUB_IS_MINING, land, landed, "A")


def test_land_event(world):
    placed = claim(world, "A", CENTRE)
    assert Land("A")(placed) == land(placed, "A")
    assert Land("A") == Land("A")


# --- lift ------------------------------------------------------------------------------


def test_lift_takes_the_bots_out_and_releases_the_place(world):
    both = land(land(claim_all(world, {"A": CENTRE, "B": sector(2, 5)}), "A"), "B")
    after = lift(both, "A")
    assert after.sites == {"B": sector(2, 5)}
    assert after.miners == {cell: ("B",) for cell in ring(world, sector(2, 5))}
    assert claim(after, "C", CENTRE).sites["C"] == CENTRE


def test_lift_of_a_hub_in_transit_releases_the_place(world):
    assert lift(claim(world, "A", CENTRE), "A") == world


def test_lift_of_an_idle_hub_changes_nothing(world):
    assert lift(world, "A") == world
    assert lift(world, "nobody") == world


def test_a_move_can_use_the_hub_s_own_old_footprint(world):
    landed = land(claim(world, "A", CENTRE), "A")
    rejected(placement.HUB_HAS_A_PLACE, claim, landed, "A", sector(2, 3))
    moved = land(claim(lift(landed, "A"), "A", sector(2, 3)), "A")
    assert moved.sites == {"A": sector(2, 3)}
    assert set(moved.miners) == set(ring(world, sector(2, 3)))


# --- Placement and the sweep -----------------------------------------------------------


def deposits(world: World) -> list[int]:
    return [asteroid.deposit for asteroid in world.asteroids]


def test_a_hub_mines_from_the_sweep_after_it_lands(world):
    placed = claim(world, "A", CENTRE)
    in_transit = sweep(sweep(placed))
    assert deposits(in_transit) == deposits(world)
    assert in_transit.hubs["A"].hold == {}

    mined = sweep(land(in_transit, "A"))
    assert mined.hubs["A"].hold == {"X": 800}
    assert {s for s, d in enumerate(deposits(mined)) if d == 900} == set(ring(world, CENTRE))
    assert mined.asteroids[CENTRE].deposit == 1000  # the hub's own sector is not mined


def test_a_lifted_hub_keeps_its_ore_and_does_not_mine(world):
    mined = sweep(land(claim(world, "A", CENTRE), "A"))
    lifted = lift(mined, "A")
    later = next(islice(weeks(lifted), 5, None))
    assert later.hubs["A"].hold == {"X": 800}
    assert deposits(later) == deposits(mined)


def test_depletion_stays_when_a_hub_comes_back(world):
    mined = sweep(sweep(land(claim(world, "A", CENTRE), "A")))
    away = land(claim(lift(mined, "A"), "A", sector(2, 6)), "A")
    back = land(claim(lift(sweep(away), "A"), "A", CENTRE), "A")
    assert back.asteroids[sector(1, 1)].deposit == 800
    assert sweep(back).asteroids[sector(1, 1)].deposit == 700


# --- Properties that hold after all sequences of commands -------------------------------


@pytest.mark.parametrize("seed", range(30))
def test_invariants(seed, world):
    rng = Random(seed)
    world = World(
        asteroids=world.asteroids,
        hubs={f"H{n}": Hub(10**6) for n in range(8)},
        rate=10,
        cols=COLS,
    )
    mining: set[str] = set()
    for _ in range(200):
        hub_id = rng.choice(sorted(world.hubs))
        command = rng.choice(["claim", "land", "lift", "sweep"])
        try:
            if command == "claim":
                world = claim(world, hub_id, rng.randrange(-2, ROWS * COLS + 2))
            elif command == "land":
                world = land(world, hub_id)
                mining.add(hub_id)
            elif command == "lift":
                world = lift(world, hub_id)
                mining.discard(hub_id)
            else:
                world = sweep(world)
        except Rejected:
            pass

        footprints = [footprint(world, place) for place in world.sites.values()]
        assert sum(map(len, footprints)) == len(placement.taken(world))  # no two touch
        assert all(len(bots) == 1 for bots in world.miners.values())  # one bot for each sector
        assert mining <= set(world.sites)
        assert Counter(bot for bots in world.miners.values() for bot in bots) == Counter(
            {hub: len(ring(world, world.sites[hub])) for hub in mining}
        )
        assert {hub for hub in world.hubs if placement.is_mining(world, hub)} == mining
