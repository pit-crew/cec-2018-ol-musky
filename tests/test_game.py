"""Game play tests: ledger, market, and the four commands of a player."""

from collections import Counter
from itertools import islice

import pytest

from ol_musky import game, ledger, market, placement
from ol_musky.game import Deliver, Sell, build, deploy, move, new_game, play, ship
from ol_musky.ledger import balance
from ol_musky.placement import Land, ring
from ol_musky.rejection import Rejected
from ol_musky.timeline import history, pending
from ol_musky.world import Asteroid, Cost, Entry, Hub, Terms, World

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


def sector(row: int, col: int) -> int:
    return row * COLS + col


CENTRE = sector(2, 2)
FAR = sector(2, 6)


@pytest.fixture
def world() -> World:
    """A new game: a 5 x 9 belt with 1000 tonnes in each sector; row 4 is ore Y."""
    asteroids = [Asteroid("Y" if s >= 4 * COLS else "X", 1000) for s in range(ROWS * COLS)]
    return new_game(asteroids, cols=COLS, rate=100, terms=TERMS)


def after(world: World, count: int) -> World:
    """The world `count` weeks later."""
    return next(islice(history(world), count, None))


def rejected(rule: str, command, *args) -> Rejected:
    with pytest.raises(Rejected) as info:
        command(*args)
    assert info.value.rule == rule
    return info.value


def mining(world: World, places: dict) -> World:
    """Build and deploy hubs, then go to the week in which they land."""
    world = after(build(world, list(places)), TERMS.build.weeks)
    return after(deploy(world, places), TERMS.deploy.weeks)


def items(world: World) -> list[tuple[int, str, float]]:
    return [(entry.week, entry.item, entry.amount) for entry in world.ledger]


# --- Ledger and market -----------------------------------------------------------------


def test_new_game(world):
    assert world.week == 0 and world.hubs == {} and world.timeline == {}
    assert world.ledger == (Entry(0, "startup", 100),)
    assert balance(world) == 100


def test_pay_and_post(world):
    paid = ledger.pay(world, "tea", 30.5)
    assert balance(paid) == 69.5
    assert paid.ledger[-1] == Entry(0, "tea", -30.5)
    assert balance(ledger.post(paid, "gift", 0.5)) == 70
    assert balance(ledger.pay(world, "all", 100)) == 0
    assert rejected(ledger.NOT_ENOUGH_MONEY, ledger.pay, world, "more", 100.01).detail == 100.01
    assert balance(world) == 100


def test_market_prices_agree_with_the_2018_server():
    assert market.prices(0) == {"X": 4.32, "Y": 9.47}
    assert market.prices(42) == {"X": 2.66, "Y": 7.01}
    assert market.prices(600) == {"X": 4.63, "Y": 8.69}
    assert all(price > 0 for week in range(1200) for price in market.prices(week).values())


def test_market_value_of_a_load():
    assert market.value({"X": 1600, "Y": 500}, 42) == pytest.approx(1.6 * 2.66 + 0.5 * 7.01)
    assert market.value({}, 42) == 0


# --- build -----------------------------------------------------------------------------


def test_build(world):
    ordered = build(world, ["A", "B"])
    assert items(ordered)[-1] == (0, "build hubs", -20)
    assert ordered.hubs == {}
    assert pending(ordered) == [(2, Deliver(("A", "B")))]

    assert after(ordered, 1).hubs == {}
    delivered = after(ordered, 2)
    assert delivered.hubs == {"A": Hub(2000), "B": Hub(2000)}
    assert delivered.sites == {} and delivered.miners == {} and delivered.timeline == {}


def test_build_rules(world):
    rejected(game.NO_HUBS, build, world, [])
    rejected(game.HUB_ID_REPEATED, build, world, ["A", "A"])
    rejected(ledger.NOT_ENOUGH_MONEY, build, world, list("ABCDEFGHIJK"))
    assert balance(build(world, list("ABCDEFGHIJ"))) == 0  # the full balance

    ordered = build(world, ["A"])
    assert rejected(game.HUB_EXISTS, build, ordered, ["B", "A"]).detail == ["A"]  # on order
    rejected(game.HUB_EXISTS, build, after(ordered, 2), ["A"])  # delivered


# --- deploy ----------------------------------------------------------------------------


def test_deploy(world):
    world = after(build(world, ["A"]), 2)
    sent = deploy(world, {"A": CENTRE})
    assert items(sent)[-1] == (2, "deploy hubs", -5)
    assert sent.sites == {"A": CENTRE}  # the place is held from the command
    assert sent.miners == {}
    assert placement.in_transit(sent, "A")
    assert pending(sent) == [(5, Land("A"))]

    assert after(sent, 2).miners == {}
    landed = after(sent, 3)
    assert set(landed.miners) == set(ring(world, CENTRE))
    assert landed.hubs["A"].hold == {} and landed.timeline == {}
    assert after(sent, 4).hubs["A"].hold == {"X": 800}


def test_deploy_rules(world):
    world = after(build(world, ["A", "B"]), 2)
    rejected(game.NO_HUBS, deploy, world, {})
    assert rejected(placement.UNKNOWN_HUB, deploy, world, {"A": CENTRE, "Z": FAR}).detail == ["Z"]
    rejected(placement.OUTSIDE_THE_BELT, deploy, world, {"A": 45})
    rejected(placement.PLACE_IS_TAKEN, deploy, world, {"A": CENTRE, "B": sector(2, 4)})

    sent = deploy(world, {"A": CENTRE})
    rejected(game.HUB_IN_TRANSIT, deploy, sent, {"A": FAR})
    rejected(placement.PLACE_IS_TAKEN, deploy, sent, {"B": sector(2, 4)})  # A's destination
    assert deploy(sent, {"B": FAR}).sites == {"A": CENTRE, "B": FAR}


def test_deploy_needs_money(world):
    world = after(build(world, list("ABCDEFGHI")), 2)  # 90 paid, 10 remain
    places = {"A": sector(1, 1), "B": sector(1, 4), "C": sector(1, 7)}
    assert rejected(ledger.NOT_ENOUGH_MONEY, deploy, world, places).detail == 15
    assert balance(deploy(world, {"A": sector(1, 1), "B": sector(1, 4)})) == 0


def test_deploy_of_a_hub_that_mines_sends_it_to_a_new_place(world):
    world = after(mining(world, {"A": CENTRE}), 1)
    sent = deploy(world, {"A": FAR})
    assert items(sent)[-1][1:] == ("deploy hubs", -5)
    assert sent.sites == {"A": FAR} and sent.miners == {}
    assert after(sent, 3).hubs["A"].hold == {"X": 800}  # no mining during the journey
    assert after(sent, 4).hubs["A"].hold == {"X": 1600}


# --- move ------------------------------------------------------------------------------


def test_move(world):
    world = after(mining(world, {"A": CENTRE}), 2)
    assert world.hubs["A"].hold == {"X": 1600}

    # The new place is in the hub's own footprint: a move releases that footprint.
    moved = move(world, {"A": sector(2, 3)})
    assert items(moved)[-1] == (world.week, "move hubs", -1)
    assert moved.sites == {"A": sector(2, 3)} and moved.miners == {}
    assert pending(moved) == [(world.week + 1, Land("A"))]

    arrived = after(moved, 1)
    assert set(arrived.miners) == set(ring(world, sector(2, 3)))
    assert arrived.hubs["A"].hold == {"X": 1600}
    # Free space is 400 t: the first 4 bots in sector sequence mine, and the others stop.
    full = after(arrived, 1)
    assert full.hubs["A"].hold == {"X": 2000}
    assert full.asteroids[sector(1, 2)].deposit == 700  # in the two footprints
    assert full.asteroids[sector(1, 4)].deposit == 900  # only in the new footprint
    assert full.asteroids[sector(3, 2)].deposit == 800  # the bot there did not mine


def test_move_rules(world):
    world = after(build(world, ["A", "B", "C"]), 2)
    assert rejected(placement.HUB_HAS_NO_PLACE, move, world, {"A": CENTRE}).detail == ["A"]
    rejected(placement.UNKNOWN_HUB, move, world, {"Z": CENTRE})

    world = after(deploy(world, {"A": CENTRE, "B": FAR}), 3)
    rejected(placement.PLACE_IS_TAKEN, move, world, {"A": sector(2, 4)})  # touches B
    in_transit = move(world, {"A": sector(0, 0)})
    rejected(game.HUB_IN_TRANSIT, move, in_transit, {"A": CENTRE})
    # A's old place is free: C can go to a sector in A's old footprint.
    assert deploy(in_transit, {"C": sector(3, 2)}).sites["C"] == sector(3, 2)


def test_two_hubs_can_exchange_places_in_one_command(world):
    world = mining(world, {"A": CENTRE, "B": FAR})
    assert move(world, {"A": FAR, "B": CENTRE}).sites == {"A": FAR, "B": CENTRE}


# --- ship ------------------------------------------------------------------------------


def test_ship(world):
    world = after(mining(world, {"A": CENTRE}), 2)
    before = balance(world)
    shipped = ship(world, ["A"])
    assert balance(shipped) == pytest.approx(before - 3.2)  # 1600 t at 2 for each 1000 t
    assert items(shipped)[-1][:2] == (world.week, "ship ore")
    assert shipped.hubs["A"] == Hub(2000)
    assert pending(shipped) == [(world.week + 4, Sell(Counter(X=1600)))]
    assert after(shipped, 1).hubs["A"].hold == {"X": 800}  # the hub continues to mine


def test_ore_sells_at_the_prices_of_the_arrival_week(world):
    shipped = ship(after(mining(world, {"A": CENTRE}), 2), ["A"])
    assert balance(after(shipped, 3)) == balance(shipped)
    sold = after(shipped, 4)
    revenue = 1.6 * market.prices(sold.week)["X"]
    assert items(sold)[-1] == (sold.week, "sell ore", pytest.approx(revenue))
    assert balance(sold) == pytest.approx(balance(shipped) + revenue)
    assert sold.timeline == {}


def test_ship_two_ore_types_from_two_hubs(world):
    world = after(mining(world, {"A": sector(3, 2), "B": FAR}), 1)
    shipped = ship(world, ["A", "B"])
    assert pending(shipped)[0][1].load == {"X": 500 + 800, "Y": 300}
    assert shipped.hubs == {"A": Hub(2000), "B": Hub(2000)}


def test_ship_rules(world):
    rejected(game.NO_HUBS, ship, world, [])
    rejected(placement.UNKNOWN_HUB, ship, world, ["A"])
    world = mining(world, {"A": CENTRE})
    rejected(game.NO_ORE, ship, world, ["A"])

    world = after(world, 20)  # the hub is full: 2000 t, shipping costs 4
    poor = ledger.post(world, "loss", 3 - balance(world))
    assert rejected(ledger.NOT_ENOUGH_MONEY, ship, poor, ["A"]).detail == 4
    assert ship(world, ["A", "A"]) == ship(world, ["A"])


def test_ship_from_a_hub_in_transit(world):
    world = move(after(mining(world, {"A": CENTRE}), 1), {"A": FAR})
    shipped = ship(world, ["A"])
    assert shipped.hubs["A"].hold == {}
    assert placement.in_transit(shipped, "A")


# --- The end of the game ---------------------------------------------------------------


def test_play_stops_at_the_last_week(world):
    worlds = list(play(mining(world, {"A": CENTRE})))
    assert [w.week for w in worlds] == list(range(5, 101))
    assert game.is_over(worlds[-1]) and not game.is_over(worlds[-2])


def test_commands_are_rejected_when_the_game_is_over(world):
    last = list(play(mining(world, {"A": CENTRE})))[-1]
    rejected(game.GAME_IS_OVER, build, last, ["B"])
    rejected(game.GAME_IS_OVER, deploy, last, {"A": FAR})
    rejected(game.GAME_IS_OVER, move, last, {"A": FAR})
    rejected(game.GAME_IS_OVER, ship, last, ["A"])


def test_an_event_after_the_last_week_does_not_occur(world):
    world = after(mining(world, {"A": CENTRE}), 93)  # week 98
    late = build(ship(world, ["A"]), ["B"])  # sale in week 102, delivery in week 100
    last = list(play(late))[-1]
    assert "B" in last.hubs
    assert pending(last) == [(102, Sell(Counter(X=2000)))]
    assert items(last)[-1][1] == "build hubs"


# --- A full game -----------------------------------------------------------------------


def test_a_full_game_keeps_all_ore_and_all_money_in_the_books(world):
    start_ore = sum(asteroid.deposit for asteroid in world.asteroids)
    world = build(world, ["A", "B", "C"])
    shipped = 0
    for _ in range(19):
        world = after(world, 5)
        idle = [hub for hub in world.hubs if hub not in world.sites]
        try:
            places = [sector(2, 1), sector(2, 4), sector(2, 7)]
            world = deploy(world, dict(zip(idle, places, strict=False)))
        except Rejected:
            pass
        full = [hub_id for hub_id, hub in world.hubs.items() if sum(hub.hold.values()) >= 1000]
        if full:
            shipped += sum(sum(world.hubs[hub_id].hold.values()) for hub_id in full)
            world = ship(world, full)

    assert world.week == 95
    assert {entry.item for entry in world.ledger} == {
        "startup", "build hubs", "deploy hubs", "ship ore", "sell ore",
    }  # fmt: skip
    in_belt = sum(asteroid.deposit for asteroid in world.asteroids)
    in_hubs = sum(sum(hub.hold.values()) for hub in world.hubs.values())
    assert in_belt + in_hubs + shipped == start_ore
    assert [entry.week for entry in world.ledger] == sorted(e.week for e in world.ledger)
    assert balance(world) > 0
