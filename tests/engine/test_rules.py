import copy

import pytest

from ol_musky.engine import market, rules
from ol_musky.engine.rules import RuleError
from ol_musky.engine.state import DELIVER_HUBS, RELOCATE_HUBS, SHIP_AND_SELL_ORE

from .conftest import COLS, Game, make_scenario, sector

HUB_A = sector(4, 5)  # interior sector; all 8 adjacent sectors hold 1000 t of X


def rejects(code: int, call, team) -> RuleError:
    """Check that the call raises RuleError with the code and changes nothing."""
    before = copy.deepcopy(team)
    with pytest.raises(RuleError) as info:
        call()
    assert info.value.status == code
    assert team == before
    return info.value


def ledger_balance(team) -> float:
    return sum(entry.credit - entry.debit for entry in team.ledger)


# --- Team start ----------------------------------------------------------------------


def test_new_team(team):
    assert team.week == 0
    assert team.balance == 100
    assert [(e.week, e.item, e.credit, e.debit) for e in team.ledger] == [(0, "startup", 100, 0)]
    assert team.hubs == {} and team.orders == [] and team.sites == {}


# --- Build ---------------------------------------------------------------------------


def test_build_hubs(game, team):
    assert game.build("A", "B") == {"hubs_built": 2, "week": 0}
    assert team.balance == 80
    assert (team.ledger[-1].item, team.ledger[-1].debit) == ("build hubs", 20)
    order = team.orders[0]
    assert (order.week, order.action, order.hub_ids, order.complete) == (
        2, DELIVER_HUBS, ("A", "B"), False,
    )  # fmt: skip
    assert team.hubs == {}


def test_hubs_arrive_when_the_build_order_is_due(game, team):
    game.build("A")
    game.advance(1)
    assert team.hubs == {}
    game.advance(1)
    hub = team.hubs["A"]
    assert (hub.sector_id, hub.active, hub.amt, hub.space_remaining) == (-1, False, {}, 100)
    assert team.orders[0].complete


def test_build_needs_money(game, team):
    error = rejects(2301, lambda: game.build(*"ABCDEFGHIJK"), team)  # 11 hubs = 110
    assert error.data == {"hubs_to_build": 11}
    game.build(*"ABCDEFGHIJ")  # 10 hubs = 100, the full balance
    assert team.balance == 0


@pytest.mark.parametrize("hub_ids", [[], [""], ["A", "A"], ["123456789"], ["A B"]])
def test_build_rejects_bad_hub_ids(game, team, hub_ids):
    rejects(2302, lambda: game.build(*hub_ids), team)


def test_build_rejects_known_hub_ids(game, team):
    game.build("A")
    rejects(2302, lambda: game.build("A"), team)  # pending delivery
    game.advance(2)
    rejects(2302, lambda: game.build("B", "A"), team)  # delivered


# --- Deploy --------------------------------------------------------------------------


def test_deploy_hubs(game, team):
    game.build("A")
    game.advance(2)
    assert game.deploy({"A": HUB_A}) == {"hubs relocated": 1, "cost": 5}
    assert team.balance == 100 - 10 - 5
    assert (team.ledger[-1].item, team.ledger[-1].debit) == ("deploy hubs", 5)
    order = team.orders[-1]
    assert (order.week, order.action, order.hub_ids, order.sector_ids) == (
        5, RELOCATE_HUBS, ("A",), (HUB_A,),
    )  # fmt: skip

    game.advance(2)
    assert not team.hubs["A"].active and team.sites == {}
    game.advance(1)
    hub = team.hubs["A"]
    assert (hub.sector_id, hub.active, hub.amt) == (HUB_A, True, {})
    assert len(team.sites) == 8 and HUB_A not in team.sites


def test_deploy_pairs_hubs_and_sectors_in_request_sequence(game, team):
    game.build("A", "B")
    game.advance(2)
    game.deploy({"B": sector(1, 1), "A": sector(6, 6)})
    game.advance(3)
    assert team.hubs["B"].sector_id == sector(1, 1)
    assert team.hubs["A"].sector_id == sector(6, 6)


def test_deploy_request_checks(game, team, scenario):
    game.build("A", "B", "C")
    game.advance(2)
    args = (scenario, team)

    error = rejects(2401, lambda: rules.deploy_hubs(*args, ["A", "B"], [HUB_A]), team)
    assert error.description.endswith("same length 1")
    error = rejects(2404, lambda: game.deploy({"A": 200}), team)
    assert "[200]" in error.description and "[0,200)" in error.description
    rejects(2404, lambda: game.deploy({"A": -1}), team)
    rejects(2402, lambda: game.deploy({"Z": HUB_A}), team)
    rejects(2402, lambda: rules.deploy_hubs(*args, ["A", "A"], [1, 100]), team)
    rejects(2402, lambda: rules.deploy_hubs(*args, [], []), team)
    rejects(2405, lambda: rules.deploy_hubs(*args, ["A", "B"], [HUB_A, HUB_A]), team)


def test_deploy_needs_money(game, team):
    game.build(*"ABCDEFGHI")  # 90
    game.advance(2)
    placements = {"A": sector(1, 1), "B": sector(1, 4), "C": sector(1, 7)}  # 15 > 10
    error = rejects(2409, lambda: game.deploy(placements), team)
    assert error.data == {"hubs": 3, "cost": 15}


@pytest.mark.parametrize("other", [sector(4, 6), sector(5, 6), sector(4, 7), sector(6, 7)])
def test_footprints_in_one_request_must_not_touch(game, team, other):
    game.build("A", "B")
    game.advance(2)
    rejects(2406, lambda: game.deploy({"A": HUB_A, "B": other}), team)


def test_footprints_three_sectors_apart_are_permitted(game, team):
    game.build("A", "B")
    game.advance(2)
    game.deploy({"A": HUB_A, "B": sector(4, 8)})


def test_deploy_to_the_footprint_of_a_deployed_hub(game, team):
    game.with_deployed({"A": HUB_A})
    game.build("B")
    game.advance(2)
    error = rejects(2407, lambda: game.deploy({"B": sector(4, 7)}), team)
    assert str(sector(4, 6)) in error.description
    game.deploy({"B": sector(4, 8)})


def test_deploy_to_the_destination_footprint_of_a_hub_in_transit(game, team):
    game.build("A", "B", "C")
    game.advance(2)
    game.deploy({"A": HUB_A})
    rejects(2407, lambda: game.deploy({"B": HUB_A}), team)
    rejects(2407, lambda: game.deploy({"B": sector(4, 7)}), team)
    game.deploy({"B": sector(4, 8)})

    game.advance(3)
    game.move({"A": sector(1, 1)})  # A is in transit; its old footprint is free
    rejects(2407, lambda: game.deploy({"C": sector(2, 3)}), team)
    game.deploy({"C": HUB_A})


def test_hub_in_transit_cannot_get_a_second_order(game, team):
    game.build("A")
    game.advance(2)
    game.deploy({"A": HUB_A})
    error = rejects(2403, lambda: game.deploy({"A": sector(1, 1)}), team)
    assert "'A'" in error.description


# --- Move ----------------------------------------------------------------------------


def test_move_hubs(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(2)
    mined = dict(team.hubs["A"].amt)
    assert mined == {"X": 1600}

    # The destination is in the hub's own footprint: a move releases that footprint.
    assert game.move({"A": sector(4, 6)}) == {"hubs relocated": 1, "cost": 1}
    assert (team.ledger[-1].item, team.ledger[-1].debit) == ("move hubs", 1)
    hub = team.hubs["A"]
    assert (hub.sector_id, hub.active) == (-1, False)

    game.advance(1)
    assert (hub.sector_id, hub.active, hub.amt) == (sector(4, 6), True, mined)
    game.advance(1)
    # 6 sectors are common to the two footprints and now hold 800 t. 3 sectors are new.
    # The hub has space for 400 t: the first 4 bots mine and the others stop.
    assert hub.amt["X"] == 2000
    assert team.sites[sector(3, 5)].deposit_amt == 700
    assert team.sites[sector(3, 7)].deposit_amt == 900
    assert team.sites[sector(3, 4)].deposit_amt == 800


def test_move_needs_a_deployed_hub(game, team):
    game.build("A")
    game.advance(2)
    error = rejects(2408, lambda: game.move({"A": HUB_A}), team)
    assert "'A'" in error.description


def test_move_cannot_use_the_footprint_of_a_different_hub(game, team):
    game.with_deployed({"A": HUB_A, "B": sector(4, 8)})
    rejects(2407, lambda: game.move({"A": sector(4, 6)}), team)


def test_move_needs_money(game, team, scenario):
    game.with_deployed({"A": HUB_A})
    team.balance = 0.5
    rejects(2409, lambda: game.move({"A": sector(1, 1)}), team)


# --- Mining --------------------------------------------------------------------------


def test_mining_starts_the_week_after_activation(game, team):
    game.with_deployed({"A": HUB_A})
    hub = team.hubs["A"]
    assert hub.amt == {} and hub.space_remaining == 100
    game.advance(1)
    assert hub.amt == {"X": 800}  # 8 bots x 100 t
    assert hub.space_remaining == 60
    assert all(site.deposit_amt == 900 for site in team.sites.values())


def test_mining_is_the_same_for_one_long_step_and_many_short_steps(scenario, rng):
    def play(step: int):
        team = rules.new_team(scenario, "t", "n", None)
        game = Game(scenario, team, rng).with_deployed({"A": HUB_A})
        for _ in range(0, 12, step):
            game.advance(step)
        return team

    assert play(1) == play(12)


def test_hub_at_the_belt_corner_has_fewer_bots(game, team):
    game.with_deployed({"A": 0})
    game.advance(1)
    assert team.hubs["A"].amt == {"X": 300}


def deposits(team) -> int:
    return sum(site.deposit_amt for site in team.sites.values())


def test_mining_stops_when_the_hub_is_full(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(3)
    hub = team.hubs["A"]
    assert hub.amt == {"X": 2000}
    assert hub.space_remaining == 0
    assert deposits(team) == 8000 - 2000  # no ore is lost
    game.advance(5)
    assert hub.amt == {"X": 2000}
    assert deposits(team) == 6000

    game.ship("A")
    game.advance(1)
    assert hub.amt == {"X": 800}  # mining starts again
    assert deposits(team) == 5200


def test_deposits_deplete(game, team):
    game.with_deployed({"A": HUB_A})
    for _ in range(6):
        game.advance(3)
        if team.hubs["A"].amt:
            game.ship("A")
    assert deposits(team) == 0
    shipped = sum(order.ore_load["X"] for order in team.orders if order.ore_load)
    assert shipped == 8000
    game.advance(5)
    assert team.hubs["A"].amt == {}


def test_deposit_smaller_than_the_weekly_rate():
    scenario = make_scenario(mining_rate=1500, hub_capacity=20_000)
    team = rules.new_team(scenario, "t", "n", None)
    game = Game(scenario, team, None).with_deployed({"A": HUB_A})
    game.advance(1)
    assert deposits(team) == 0
    assert team.hubs["A"].amt == {"X": 8000}


def test_capacity_is_the_total_of_all_ore_types(game, team):
    # Row 8 hub: 5 sectors of X and 3 sectors of Y (row 9).
    game.with_deployed({"A": sector(8, 5)})
    game.advance(1)
    hub = team.hubs["A"]
    assert hub.amt == {"X": 500, "Y": 300}
    assert hub.space_remaining == 60
    game.advance(9)
    assert sum(hub.amt.values()) == 2000
    assert hub.amt == {"X": 1400, "Y": 600}
    assert hub.space_remaining == 0
    assert deposits(team) == 8000 - 2000


def test_space_remaining_is_never_negative(game, team):
    game.with_deployed({"A": sector(8, 5)})
    for _ in range(20):
        game.advance(1)
        assert 0 <= team.hubs["A"].space_remaining <= 100


def test_no_mining_during_relocation(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(1)
    game.deploy({"A": sector(1, 1)})  # a second deploy is permitted
    deposits = {sector_id: site.deposit_amt for sector_id, site in team.sites.items()}
    game.advance(2)
    assert team.hubs["A"].amt == {"X": 800}
    assert {sector_id: site.deposit_amt for sector_id, site in team.sites.items()} == deposits


def test_site_depletion_stays_when_a_hub_comes_back(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(3)
    game.move({"A": sector(1, 15)})
    game.advance(1)
    game.move({"A": HUB_A})
    game.advance(1)
    assert team.sites[sector(4, 4)].deposit_amt == 700


# --- Ship and sell -------------------------------------------------------------------


def test_ship_ore(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(2)
    balance = team.balance
    assert game.ship("A") == {"hubs_dumped": 1, "ore": {"X": 1600}}
    assert team.balance == pytest.approx(balance - 3.2)  # 1600 t at 2 for each 1000 t
    assert (team.ledger[-1].item, team.ledger[-1].debit) == ("ship ore", pytest.approx(3.2))
    hub = team.hubs["A"]
    assert (hub.amt, hub.space_remaining, hub.active) == ({}, 100, True)
    order = team.orders[-1]
    assert (order.week, order.action, order.ore_load, order.insured) == (
        team.week + 4, SHIP_AND_SELL_ORE, {"X": 1600}, False,
    )  # fmt: skip
    game.advance(1)
    assert hub.amt == {"X": 800}  # mining continues


def test_ore_sells_at_the_price_of_the_arrival_week(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(2)
    game.ship("A")
    balance = team.balance
    game.advance(3)
    assert team.balance == balance
    game.advance(1)
    # Partial units of 1000 t sell: 1600 t is 1.6 units.
    revenue = 1.6 * market.prices(team.week)["X"]
    assert team.balance == pytest.approx(balance + revenue)
    assert (team.ledger[-1].week, team.ledger[-1].item, team.ledger[-1].credit) == (
        team.week, "sell ore", pytest.approx(revenue),
    )  # fmt: skip
    assert team.orders[-1].complete and not team.orders[-1].pirated


def test_ship_two_ore_types_from_two_hubs(game, team):
    game.with_deployed({"A": sector(8, 5), "B": sector(4, 12)})
    game.advance(1)
    assert game.ship("A", "B", "unknown")["ore"] == {"X": 1300, "Y": 300}


def test_insurance(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(2)
    balance = team.balance
    game.ship("A", insured=True)
    assert team.balance == pytest.approx(balance - 3.2 - 0.64)
    assert [(e.item, e.debit) for e in team.ledger[-2:]] == [
        ("ship ore", pytest.approx(3.2)),
        ("insurance", pytest.approx(0.64)),
    ]
    assert team.orders[-1].insured


def test_ship_request_checks(game, team):
    rejects(2501, lambda: game.ship("A"), team)
    game.with_deployed({"A": HUB_A})
    error = rejects(2502, lambda: game.ship("A"), team)
    assert error.data == {"hubs_to_unload": 1}
    game.advance(2)
    team.balance = 3.5  # shipping 3.2, premium 0.64
    error = rejects(2503, lambda: game.ship("A", insured=True), team)
    assert error.data == {"hubs_to_unload": 1, "cost": pytest.approx(3.2)}
    game.ship("A")


def test_ship_from_a_hub_in_transit_leaves_it_inactive(game, team):
    game.with_deployed({"A": HUB_A})
    game.advance(1)
    game.move({"A": sector(1, 1)})
    game.ship("A")
    hub = team.hubs["A"]
    assert (hub.amt, hub.active, hub.sector_id) == ({}, False, -1)


class Pirates:
    """Random source that always attacks and leaves 10 %."""

    def getrandbits(self, _bits):
        return 1

    def randint(self, low, _high):
        return low


class NoPirates(Pirates):
    def getrandbits(self, _bits):
        return 0


def ship_big_load(scenario, team, rng, insured=False, tonnes=200_000):
    game = Game(scenario, team, rng).with_deployed({"A": HUB_A})
    team.hubs["A"].amt = {"X": tonnes}
    team.balance = 10_000
    game.ship("A", insured=insured)
    balance = team.balance
    game.advance(4)
    return team.orders[-1], team.ledger[-1], team.balance - balance


def test_pirates_attack_a_large_shipment_with_no_insurance(scenario, team):
    order, entry, revenue = ship_big_load(scenario, team, Pirates())
    assert order.pirated and order.complete
    assert order.ore_load == {"X": 200_000}
    assert entry.item == "ore was pirated"
    assert revenue == pytest.approx(20 * market.prices(team.week)["X"])  # 10 % of 200 units


def test_pirates_do_not_always_attack(scenario, team):
    order, entry, revenue = ship_big_load(scenario, team, NoPirates())
    assert not order.pirated and entry.item == "sell ore"
    assert revenue == pytest.approx(200 * market.prices(team.week)["X"])


def test_insurance_stops_pirates(scenario, team):
    order, entry, _ = ship_big_load(scenario, team, Pirates(), insured=True)
    assert not order.pirated and entry.item == "sell ore"


def test_pirates_ignore_a_small_shipment(scenario, team):
    # 166 000 t x 6 / 1000 = 996, which is not more than the threshold of 1000.
    order, _, _ = ship_big_load(scenario, team, Pirates(), tonnes=166_000)
    assert not order.pirated


# --- Time ----------------------------------------------------------------------------


def test_time_stops_at_the_lifetime(game, team, scenario):
    game.with_deployed({"A": HUB_A})
    game.advance(2)
    rules.advance(scenario, team, 95, game.rng)
    game.ship("A")  # arrival in week 99
    game.build("B")  # delivery in week 97
    rules.advance(scenario, team, 99, game.rng)
    game.build("C")  # delivery in week 101: after the end
    rules.advance(scenario, team, 5000, game.rng)
    assert team.week == 100
    assert not rules.is_over(scenario, 100) and rules.is_over(scenario, 101)
    assert [order.complete for order in team.orders[-3:]] == [True, True, False]
    assert "B" in team.hubs and "C" not in team.hubs
    assert team.ledger[-2].item == "sell ore"


def test_advance_to_a_past_week_does_nothing(game, team, scenario):
    game.advance(10)
    before = copy.deepcopy(team)
    rules.advance(scenario, team, 5, game.rng)
    assert team == before


def test_ledger_agrees_with_balance_for_a_full_game(game, team, scenario):
    game.with_deployed({"A": HUB_A, "B": sector(8, 12)})
    game.build("C")
    for _ in range(18):
        game.advance(5)
        for hub in list(team.hubs.values()):
            if sum(hub.amt.values()) >= 1000:
                game.ship(hub.hub_id, insured=hub.hub_id == "B")
            if hub.hub_id == "C" and not hub.deployed and not team.pending_orders(RELOCATE_HUBS):
                game.deploy({"C": sector(1, 1)})
    assert team.week == 95
    assert any(entry.item == "sell ore" for entry in team.ledger)
    assert team.balance == pytest.approx(ledger_balance(team))
    assert [entry.week for entry in team.ledger] == sorted(entry.week for entry in team.ledger)


def test_orders_complete_in_due_week_sequence(game, team):
    # A build order (2 weeks) made after a deploy order (3 weeks) completes first.
    game.build("A")
    game.advance(2)
    game.deploy({"A": HUB_A})
    game.build("B")
    game.advance(2)
    assert "B" in team.hubs and not team.hubs["A"].active
    game.advance(1)
    assert team.hubs["A"].active
    assert COLS == 20
