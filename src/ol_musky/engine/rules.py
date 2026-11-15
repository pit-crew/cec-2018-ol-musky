"""Game rules: team start, time advance, and the four team actions.

Each action checks the request, then changes the TeamState. A request that
breaks a rule raises RuleError and changes nothing. The status codes and the
response bodies are those of the 2018 competition server, with the differences
that the README lists.
"""

from collections import Counter
from datetime import datetime
from random import Random
from typing import Any

from ol_musky.engine import market
from ol_musky.engine.grid import adjacent_sectors
from ol_musky.engine.state import (
    DELIVER_HUBS,
    RELOCATE_HUBS,
    SHIP_AND_SELL_ORE,
    UNDEPLOYED,
    Hub,
    Order,
    Site,
    TeamState,
)
from ol_musky.scenario import Scenario

MAX_HUB_ID_LENGTH = 8
INSURANCE_RATE = 0.20  # fraction of the shipping cost

# Piracy: a shipment with no insurance and an approximate value of more than
# PIRACY_VALUE_THRESHOLD (millions) has a 50 % risk. Pirates leave 10 % to 20 % of each ore.
PIRACY_APPROX_PRICE = 6
PIRACY_VALUE_THRESHOLD = 1000
PIRACY_KEPT_PERCENT = (10, 20)


class RuleError(Exception):
    """A request broke a rule. The fields map to the MCP response envelope."""

    def __init__(self, action: str, status: int, description: str, data: Any = None) -> None:
        super().__init__(description)
        self.action = action
        self.status = status
        self.description = description
        self.data = {} if data is None else data


# --- Team start and time ------------------------------------------------------------


def new_team(scenario: Scenario, token: str, name: str, start_time: datetime) -> TeamState:
    """A team at week 0 with the starting capital and no hubs."""
    team = TeamState(token=token, name=name, start_time=start_time, balance=0)
    team.credit("startup", scenario.starting_capital)
    return team


def is_over(scenario: Scenario, week: int) -> bool:
    """True when the week is after the end of the game."""
    return week > scenario.lifetime


def advance(scenario: Scenario, team: TeamState, week: int, rng: Random) -> None:
    """Move the team forward to the given week. Time stops at the scenario lifetime."""
    for current in range(team.week + 1, min(week, scenario.lifetime) + 1):
        team.week = current
        _fulfill_orders(scenario, team, rng)
        _mine(scenario, team)


# --- Build ---------------------------------------------------------------------------


def build_hubs(scenario: Scenario, team: TeamState, hub_ids: list[str]) -> dict:
    """Pay for new hubs and order their delivery."""
    action = "build_hubs"
    known = set(team.hubs)
    for order in team.pending_orders(DELIVER_HUBS):
        known.update(order.hub_ids)
    if (
        not hub_ids
        or any(not _valid_hub_id(hub_id) for hub_id in hub_ids)
        or len(set(hub_ids)) != len(hub_ids)
        or known.intersection(hub_ids)
    ):
        raise RuleError(
            action,
            2302,
            f"hub IDs must be new, unique, and {MAX_HUB_ID_LENGTH} or fewer alpha-numerics",
        )

    count = len(hub_ids)
    cost = scenario.costs["hub"]
    total = count * cost.rate
    if total > team.balance:
        raise RuleError(action, 2301, "not enough money", {"hubs_to_build": count})

    team.debit("build hubs", total)
    team.orders.append(
        Order(week=team.week + cost.weeks, action=DELIVER_HUBS, hub_ids=tuple(hub_ids))
    )
    return {"hubs_built": count, "week": team.week}


def _valid_hub_id(hub_id: str) -> bool:
    return 0 < len(hub_id) <= MAX_HUB_ID_LENGTH and all(
        char.isalnum() or char in "-_" for char in hub_id
    )


# --- Deploy and move ----------------------------------------------------------------


def deploy_hubs(
    scenario: Scenario, team: TeamState, hub_ids: list[str], sector_ids: list[int]
) -> dict:
    return _locate_hubs(scenario, team, hub_ids, sector_ids, "deploy hubs", "deploy")


def move_hubs(
    scenario: Scenario, team: TeamState, hub_ids: list[str], sector_ids: list[int]
) -> dict:
    return _locate_hubs(scenario, team, hub_ids, sector_ids, "move hubs", "move")


def _locate_hubs(
    scenario: Scenario,
    team: TeamState,
    hub_ids: list[str],
    sector_ids: list[int],
    action: str,
    cost_item: str,
) -> dict:
    """Pay to send hubs to sectors and order the relocation.

    The footprint of a hub is its sector and the adjacent sectors. The footprints
    of the hubs in the request must not touch each other. They also must not touch
    the footprint of a deployed hub that is not in a move request, or the
    destination footprint of a hub that is in transit.
    """
    rows, cols = scenario.rows, scenario.cols
    is_move = cost_item == "move"

    difference = abs(len(hub_ids) - len(sector_ids))
    if difference != 0:
        raise RuleError(
            action,
            2401,
            f"hub list and sector_id list need to be the same length {difference}",
        )

    sector_count = rows * cols
    invalid = [sector_id for sector_id in sector_ids if not 0 <= sector_id < sector_count]
    if invalid:
        raise RuleError(
            action,
            2404,
            f"sector {invalid} - sector IDs must be within the range [0,{sector_count})",
        )

    if (
        not hub_ids
        or len(set(hub_ids)) != len(hub_ids)
        or any(hub_id not in team.hubs for hub_id in hub_ids)
    ):
        raise RuleError(action, 2402, "some hubs requested do not exist")

    if is_move:
        undeployed = [hub_id for hub_id in hub_ids if not team.hubs[hub_id].deployed]
        if undeployed:
            raise RuleError(action, 2408, f"hubs must be deployed before being moved: {undeployed}")

    count = len(hub_ids)
    cost = scenario.costs[cost_item]
    total = count * cost.rate
    if total > team.balance:
        raise RuleError(action, 2409, "not enough money", {"hubs": count, "cost": total})

    in_transit = {
        hub_id for order in team.pending_orders(RELOCATE_HUBS) for hub_id in order.hub_ids
    }
    collisions = sorted(in_transit.intersection(hub_ids))
    if collisions:
        raise RuleError(action, 2403, f"hubs: {collisions} currently being deployed")

    if len(set(sector_ids)) != len(sector_ids):
        raise RuleError(action, 2405, "hubs must be deployed to unique sectors", {"hubs": count})

    requested = set(sector_ids)
    for sector_id in sector_ids:
        ring = adjacent_sectors(sector_id, rows, cols)
        if requested.intersection(ring):
            raise RuleError(action, 2406, "mining bots must use separate sectors", {"hubs": count})
        requested.update(ring)

    occupied: set[int] = set()
    for hub in team.hubs.values():
        if hub.deployed and not (is_move and hub.hub_id in hub_ids):
            occupied.add(hub.sector_id)
            occupied.update(adjacent_sectors(hub.sector_id, rows, cols))
    for order in team.pending_orders(RELOCATE_HUBS):
        for sector_id in order.sector_ids:
            occupied.add(sector_id)
            occupied.update(adjacent_sectors(sector_id, rows, cols))
    collisions = sorted(requested.intersection(occupied))
    if collisions:
        raise RuleError(
            action,
            2407,
            f"unable to deploy to occupied sectors: {collisions}",
            {"hubs": count},
        )

    team.debit(action, total)
    for hub_id in hub_ids:
        hub = team.hubs[hub_id]
        hub.sector_id = UNDEPLOYED
        hub.active = False
    team.orders.append(
        Order(
            week=team.week + cost.weeks,
            action=RELOCATE_HUBS,
            hub_ids=tuple(hub_ids),
            sector_ids=tuple(sector_ids),
        )
    )
    return {"hubs relocated": count, "cost": total}


# --- Ship ----------------------------------------------------------------------------


def ship_ore(
    scenario: Scenario, team: TeamState, hub_ids: list[str], insured: bool = False
) -> dict:
    """Empty the given hubs, pay for the shipment, and order the sale on Earth."""
    action = "ship_ore"
    hubs = [hub for hub in team.hubs.values() if hub.hub_id in hub_ids]
    count = len(hubs)
    if count == 0:
        raise RuleError(action, 2501, "no hubs requested", {"hubs_to_unload": count})

    load: Counter[str] = Counter()
    for hub in hubs:
        load.update(hub.amt)
    ore_load = {ore_id: amount for ore_id, amount in load.items() if amount > 0}
    total_ore = sum(ore_load.values())
    if total_ore == 0:
        raise RuleError(action, 2502, "no ore to ship", {"hubs_to_unload": count})

    cost = scenario.costs["ship"]
    shipping = total_ore * cost.rate / 1000
    premium = INSURANCE_RATE * shipping if insured else 0.0
    if shipping + premium > team.balance:
        raise RuleError(
            action, 2503, "not enough money", {"hubs_to_unload": count, "cost": shipping}
        )

    for hub in hubs:
        hub.amt = {}
        hub.space_remaining = 100
        hub.active = hub.deployed

    team.debit("ship ore", shipping)
    if insured:
        team.debit("insurance", premium)
    team.orders.append(
        Order(
            week=team.week + cost.weeks,
            action=SHIP_AND_SELL_ORE,
            ore_load=ore_load,
            insured=insured,
        )
    )
    return {"hubs_dumped": count, "ore": ore_load}


# --- Order fulfilment ---------------------------------------------------------------


def _fulfill_orders(scenario: Scenario, team: TeamState, rng: Random) -> None:
    due = [order for order in team.orders if not order.complete and order.week <= team.week]
    for order in sorted(due, key=lambda order: order.week):
        if order.action == DELIVER_HUBS:
            _deliver_hubs(team, order)
        elif order.action == RELOCATE_HUBS:
            _relocate_hubs(scenario, team, order)
        elif order.action == SHIP_AND_SELL_ORE:
            _sell_ore(team, order, rng)
        order.complete = True


def _deliver_hubs(team: TeamState, order: Order) -> None:
    for hub_id in order.hub_ids:
        team.hubs[hub_id] = Hub(hub_id=hub_id)


def _relocate_hubs(scenario: Scenario, team: TeamState, order: Order) -> None:
    for hub_id, sector_id in zip(order.hub_ids, order.sector_ids, strict=True):
        for adjacent in adjacent_sectors(sector_id, scenario.rows, scenario.cols):
            if adjacent not in team.sites:
                sector = scenario.belt[adjacent]
                team.sites[adjacent] = Site(ore_id=sector.ore_id, deposit_amt=sector.deposit_amt)
        hub = team.hubs[hub_id]
        hub.sector_id = sector_id
        hub.active = True
        hub.mined_through = team.week


def _sell_ore(team: TeamState, order: Order, rng: Random) -> None:
    ore_load = dict(order.ore_load)
    approx_value = int(sum(ore_load.values()) * PIRACY_APPROX_PRICE / 1000)
    if not order.insured and approx_value > PIRACY_VALUE_THRESHOLD and rng.getrandbits(1):
        order.pirated = True
        for ore_id, amount in ore_load.items():
            ore_load[ore_id] = int(rng.randint(*PIRACY_KEPT_PERCENT) * amount / 100)

    prices = market.prices(team.week)
    revenue = sum(amount * prices[ore_id] / 1000 for ore_id, amount in ore_load.items())
    team.credit("ore was pirated" if order.pirated else "sell ore", revenue)


# --- Mining --------------------------------------------------------------------------


def _mine(scenario: Scenario, team: TeamState) -> None:
    for hub in team.hubs.values():
        if not (hub.active and hub.deployed):
            continue
        weeks = team.week - hub.mined_through
        if weeks <= 0:
            continue
        _mine_hub(scenario, team, hub, weeks)
        hub.mined_through = team.week


def _mine_hub(scenario: Scenario, team: TeamState, hub: Hub, weeks: int) -> None:
    """Move ore from the adjacent sectors into the hub.

    Each bot takes mining_rate tonnes for each week from its sector, or the
    remainder of the deposit. The hub capacity is the total of all ore types.
    Mining stops when the hub is full: the bots take no more than the free space,
    and the deposits keep the remainder.
    """
    max_ore = weeks * scenario.mining_rate
    free = scenario.hub_capacity - sum(hub.amt.values())
    for adjacent in adjacent_sectors(hub.sector_id, scenario.rows, scenario.cols):
        if free <= 0:
            break
        site = team.sites.get(adjacent)
        if site is None or site.deposit_amt <= 0:
            continue
        ore = min(site.deposit_amt, max_ore, free)
        site.deposit_amt -= ore
        hub.amt[site.ore_id] = hub.amt.get(site.ore_id, 0) + ore
        free -= ore
    hub.space_remaining = max(0, int(100 * free / scenario.hub_capacity))
