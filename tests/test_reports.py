"""Report and clock tests."""

from datetime import UTC, datetime, timedelta
from itertools import islice

import pytest

from ol_musky import reports
from ol_musky.clock import catch_up, week_at
from ol_musky.game import build, deploy, move, new_game, play, ship
from ol_musky.ledger import balance
from ol_musky.timeline import history
from ol_musky.world import Asteroid, Cost, Terms, World

COLS, ROWS = 9, 5
TERMS = Terms(
    lifetime=100,
    starting_capital=100,
    hub_capacity=2000,
    build=Cost(rate=10, weeks=2),
    deploy=Cost(rate=5, weeks=3),
    move=Cost(rate=1, weeks=1),
    ship=Cost(rate=2, weeks=4),
)
CENTRE = 2 * COLS + 2
FAR = 2 * COLS + 6


@pytest.fixture
def world() -> World:
    asteroids = [Asteroid("Y" if s >= 4 * COLS else "X", 1000) for s in range(ROWS * COLS)]
    return new_game(asteroids, cols=COLS, rate=100, terms=TERMS, seed=2018)


def after(world: World, count: int) -> World:
    return next(islice(history(world), count, None))


# --- Status ----------------------------------------------------------------------------


def test_status_of_a_new_game(world):
    assert reports.status(world) == {"week": 0, "balance": 100, "hubs": {}, "orders": []}


def test_status_follows_a_hub_through_its_life(world):
    ordered = build(world, ["A"])
    assert reports.status(ordered) == {
        "week": 0,
        "balance": 90,
        "hubs": {},
        "orders": [{"week": 2, "action": "deliver_hubs", "hub_list": ["A"]}],
    }

    idle = after(ordered, 2)
    assert reports.status(idle)["orders"] == []
    assert reports.status(idle)["hubs"]["A"] == {
        "hub_id": "A",
        "state": "idle",
        "sector_id": None,
        "amt": {},
        "space_remaining": 100,
    }

    in_transit = deploy(idle, {"A": CENTRE})
    report = reports.status(in_transit)
    assert report["hubs"]["A"]["state"] == "in_transit"
    assert report["hubs"]["A"]["sector_id"] == CENTRE  # the sector that the hub goes to
    assert report["orders"] == [
        {"week": 5, "action": "relocate_hubs", "hub_list": ["A"], "sector_id_list": [CENTRE]}
    ]

    mining = after(in_transit, 5)
    assert reports.status(mining)["hubs"]["A"] == {
        "hub_id": "A",
        "state": "mining",
        "sector_id": CENTRE,
        "amt": {"X": 1600},
        "space_remaining": 20,
    }

    shipped = ship(mining, ["A"])
    report = reports.status(shipped)
    assert report["hubs"]["A"]["amt"] == {} and report["hubs"]["A"]["state"] == "mining"
    assert report["orders"] == [{"week": 11, "action": "sell_ore", "ore_load": {"X": 1600}}]
    assert report["balance"] == balance(shipped)

    moving = move(shipped, {"A": FAR})
    hub = reports.status(moving)["hubs"]["A"]
    assert (hub["state"], hub["sector_id"]) == ("in_transit", FAR)
    assert [o["action"] for o in reports.status(moving)["orders"]] == [
        "relocate_hubs",
        "sell_ore",
    ]


def test_orders_are_in_week_sequence_with_one_order_for_each_hub_that_travels(world):
    world = after(build(world, ["A", "B"]), 2)
    world = build(deploy(world, {"A": CENTRE, "B": FAR}), ["C"])
    assert [(o["week"], o["action"], o["hub_list"]) for o in reports.status(world)["orders"]] == [
        (4, "deliver_hubs", ["C"]),
        (5, "relocate_hubs", ["A"]),
        (5, "relocate_hubs", ["B"]),
    ]


def test_an_event_with_no_order_format_is_an_error(world):
    with pytest.raises(TypeError):
        reports.order(lambda w: w, 3, world)


# --- Money and constants ---------------------------------------------------------------


def test_ledger_report(world):
    sold = after(ship(after(deploy(after(build(world, ["A"]), 2), {"A": CENTRE}), 5), ["A"]), 4)
    lines = reports.ledger(sold)
    assert lines[:4] == [
        {"week": 0, "item": "startup", "credit": 100, "debit": 0},
        {"week": 0, "item": "build hubs", "credit": 0, "debit": 10},
        {"week": 2, "item": "deploy hubs", "credit": 0, "debit": 5},
        {"week": 7, "item": "ship ore", "credit": 0, "debit": pytest.approx(3.2)},
    ]
    assert (lines[4]["week"], lines[4]["item"], lines[4]["debit"]) == (11, "sell ore", 0)
    assert sum(line["credit"] - line["debit"] for line in lines) == pytest.approx(balance(sold))


def test_market_report(world):
    assert reports.market_report(after(world, 42)) == {
        "week": 42,
        "prices": {"X": 2.66, "Y": 7.01},
    }


def test_parameters(world):
    assert reports.parameters(world) == {
        "lifetime": 100,
        "rows": 5,
        "cols": 9,
        "hub_capacity": 2000,
        "mining_rate": 100,
        "starting_capital": 100,
        "prospect_weeks": 14,
        "costs": {
            "build": {"item": "build", "weeks": 2, "rate": 10},
            "deploy": {"item": "deploy", "weeks": 3, "rate": 5},
            "move": {"item": "move", "weeks": 1, "rate": 1},
            "ship": {"item": "ship", "weeks": 4, "rate": 2},
        },
    }
    assert reports.parameters(after(world, 30)) == reports.parameters(world)


# --- Prospecting -----------------------------------------------------------------------


def test_each_pass_covers_new_sectors(world):
    assert [row[0] for row in reports.prospect(world)] == list(range(0, 45, 7))
    assert [row[0] for row in reports.prospect(after(world, 13))] == list(range(0, 45, 7))
    assert [row[0] for row in reports.prospect(after(world, 14))] == list(range(1, 45, 7))


def test_all_passes_cover_the_belt_one_time(world):
    seen = [row[0] for week in range(0, 98, 14) for row in reports.prospect(after(world, week))]
    assert sorted(seen) == list(range(45))
    assert reports.survey_pass(after(world, 99)) == 0  # the passes start again


def test_estimates_are_near_the_deposits(world):
    error = int(1000 // 6.5)
    report = reports.prospect(world)
    for sector, ore, estimate in report:
        assert ore == world.asteroids[sector].ore
        assert 1000 - error <= estimate <= 1000 + error
    assert len({estimate for _, _, estimate in report}) > 1


def test_a_report_is_a_function_of_the_world(world):
    assert reports.prospect(world) == reports.prospect(world)
    assert reports.prospect(after(world, 5)) == reports.prospect(world)  # the same pass
    other = new_game(world.asteroids, cols=COLS, rate=100, terms=TERMS, seed=2019)
    assert reports.prospect(other) != reports.prospect(world)


def test_an_estimate_is_not_negative():
    asteroids = [Asteroid("X", 0)] * 44 + [Asteroid("X", 5000)]
    for seed in range(20):
        world = new_game(asteroids, cols=COLS, rate=100, terms=TERMS, seed=seed)
        assert all(estimate >= 0 for _, _, estimate in reports.prospect(world))


def test_estimates_show_the_deposits_at_this_time(world):
    # A hub at the corner sector 8 mines sector 7 until the hub is full.
    mined = after(deploy(after(build(world, ["A"]), 2), {"A": 8}), 13)
    assert mined.asteroids[7].deposit == 300
    depleted = new_game(mined.asteroids, cols=COLS, rate=100, terms=TERMS, seed=2018)
    before = {sector: estimate for sector, _, estimate in reports.prospect(world)}
    now = {sector: estimate for sector, _, estimate in reports.prospect(depleted)}
    assert now[7] == before[7] - 700
    assert now[14] == before[14]


# --- Clock -----------------------------------------------------------------------------

START = datetime(2018, 3, 9, tzinfo=UTC)


def test_week_at():
    assert week_at(START, START, 200) == 0
    assert week_at(START, START + timedelta(milliseconds=199), 200) == 0
    assert week_at(START, START + timedelta(milliseconds=200), 200) == 1
    assert week_at(START, START + timedelta(seconds=120), 200) == 600
    assert week_at(START, START - timedelta(seconds=1), 200) == 0


def test_catch_up_gives_the_world_of_the_week(world):
    world = deploy(after(build(world, ["A"]), 2), {"A": CENTRE})
    assert catch_up(world, 9) == after(world, 7)
    assert catch_up(world, world.week) is world
    assert catch_up(world, 0) is world  # time does not go back


def test_one_long_step_and_many_short_steps_give_the_same_world(world):
    world = deploy(after(build(world, ["A"]), 2), {"A": CENTRE})
    stepped = world
    for week in range(3, 41):
        stepped = catch_up(stepped, week)
    assert catch_up(world, 40) == stepped


def test_catch_up_stops_at_the_last_week_of_the_game(world):
    end = catch_up(world, 5000)
    assert end.week == 100
    assert end == list(play(world))[-1]
    assert catch_up(end, 6000) is end
