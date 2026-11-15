"""Reports: views of a world as plain data.

A report is a function of a world. It changes nothing and it costs the player
nothing. The server adds the data that is not in a world (the team and its clock).
"""

from functools import singledispatch
from zlib import crc32

from ol_musky import market
from ol_musky.game import Deliver, Sell
from ol_musky.ledger import balance
from ol_musky.placement import Land, hub_state
from ol_musky.timeline import pending
from ol_musky.world import Cost, World

# The survey error is +/- (largest deposit / 6.5), which is approximately 15 %.
_SURVEY_ERROR_DIVISOR = 6.5


# --- Status ----------------------------------------------------------------------------


def hub(world: World, hub_id: str) -> dict:
    """One hub.

    `state` is "idle", "in_transit", or "mining". `sector_id` is the sector that
    the hub holds: where it mines, or where it goes to. An idle hub holds no
    sector, and its `sector_id` is null.
    """
    hold = world.hubs[hub_id]
    return {
        "hub_id": hub_id,
        "state": hub_state(world, hub_id).value,
        "sector_id": world.sites.get(hub_id),
        "amt": dict(hold.hold),
        "space_remaining": int(100 * hold.free / hold.capacity),  # percent
    }


@singledispatch
def order(event: object, week: int, world: World) -> dict:
    """A pending event as a work order."""
    raise TypeError(f"no order format for {event!r}")


@order.register
def _(event: Deliver, week: int, world: World) -> dict:
    return {"week": week, "action": "deliver_hubs", "hub_list": list(event.hub_ids)}


@order.register
def _(event: Land, week: int, world: World) -> dict:
    return {
        "week": week,
        "action": "relocate_hubs",
        "hub_list": [event.hub_id],
        "sector_id_list": [world.sites[event.hub_id]],
    }


@order.register
def _(event: Sell, week: int, world: World) -> dict:
    return {"week": week, "action": "sell_ore", "ore_load": dict(event.load)}


def status(world: World) -> dict:
    return {
        "week": world.week,
        "balance": balance(world),
        "hubs": {hub_id: hub(world, hub_id) for hub_id in world.hubs},
        "orders": [order(event, week, world) for week, event in pending(world)],
    }


# --- Money -----------------------------------------------------------------------------


def ledger(world: World) -> list[dict]:
    return [
        {
            "week": entry.week,
            "item": entry.item,
            "credit": max(entry.amount, 0),
            "debit": max(-entry.amount, 0),
        }
        for entry in world.ledger
    ]


def market_report(world: World) -> dict:
    return {"week": world.week, "prices": market.prices(world.week)}


# --- Constants -------------------------------------------------------------------------


def _cost(item: str, cost: Cost) -> dict:
    return {"item": item, "weeks": cost.weeks, "rate": cost.rate}


def parameters(world: World) -> dict:
    terms = world.terms
    return {
        "lifetime": terms.lifetime,
        "rows": len(world.asteroids) // world.cols,
        "cols": world.cols,
        "hub_capacity": terms.hub_capacity,
        "mining_rate": world.rate,
        "starting_capital": terms.starting_capital,
        "prospect_weeks": survey_interval(world),
        "costs": {
            item: _cost(item, getattr(terms, item)) for item in ("build", "deploy", "move", "ship")
        },
    }


# --- Prospecting -----------------------------------------------------------------------


def survey_interval(world: World) -> int:
    """The number of weeks between new prospecting reports."""
    return max(world.terms.lifetime // world.terms.survey_passes, 1)


def survey_pass(world: World) -> int:
    """The index of the survey pass that is current: 0, 1, ... survey_passes - 1."""
    return world.week // survey_interval(world) % world.terms.survey_passes


def _noise(world: World, sector: int, error: int) -> int:
    """A fixed value in the range -error to +error for each sector of a world."""
    return crc32(f"{world.seed}:{sector}".encode()) % (2 * error + 1) - error


def prospect(world: World) -> list[tuple[int, str, int]]:
    """The estimates of the current survey pass, as (sector_id, ore, estimated_tonnes).

    Pass N covers the sectors N, N + passes, N + 2 * passes, and so on. Thus all
    the passes together cover the belt, and each report shows only new sectors.
    An estimate is the deposit at this time with a fixed error for the sector:
    a second request in the same pass gives the same error.
    """
    error = int(max(asteroid.deposit for asteroid in world.asteroids) // _SURVEY_ERROR_DIVISOR)
    sectors = range(survey_pass(world), len(world.asteroids), world.terms.survey_passes)
    return [
        (
            sector,
            world.asteroids[sector].ore,
            max(world.asteroids[sector].deposit + _noise(world, sector, error), 0),
        )
        for sector in sectors
    ]
