"""Game play: the commands of a player.

Each command is a function from a world to a new world. It checks the rules,
pays, changes where things are, and schedules the event that completes it:

    build   - pay; the hubs arrive from the factory after the build time
    deploy  - pay; hold the places; the hubs land after the deploy time
    move    - as deploy, for hubs that have a place, at the move cost
    ship    - pay; empty the hubs; the ore sells after the ship time

A command that is rejected changes nothing, because it returns no world.
"""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import reduce
from itertools import takewhile

from ol_musky import market
from ol_musky.ledger import pay, post
from ol_musky.placement import (
    HUB_HAS_NO_PLACE,
    UNKNOWN_HUB,
    Land,
    claim_all,
    in_transit,
    lift,
)
from ol_musky.rejection import require
from ol_musky.timeline import history, pending, schedule
from ol_musky.world import Asteroid, Cost, Hub, Terms, World

GAME_IS_OVER = "game is over"
NO_HUBS = "no hubs in the request"
HUB_ID_REPEATED = "hub ID is repeated"
HUB_EXISTS = "hub exists"
HUB_IN_TRANSIT = "hub is in transit"
NO_ORE = "no ore to ship"


# --- The game --------------------------------------------------------------------------


def new_game(
    asteroids: Sequence[Asteroid], cols: int, rate: int, terms: Terms, seed: int = 0
) -> World:
    """The world of a player at week 0: the starting capital and no hubs."""
    world = World(asteroids=tuple(asteroids), cols=cols, rate=rate, terms=terms, seed=seed)
    return post(world, "startup", terms.starting_capital)


def is_over(world: World) -> bool:
    return world.week >= world.terms.lifetime


def play(world: World) -> Iterator[World]:
    """The stream of worlds from the given world to the last week of the game."""
    return takewhile(lambda w: w.week <= w.terms.lifetime, history(world))


# --- Events ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Deliver:
    """New hubs arrive from the factory. They are idle."""

    hub_ids: tuple[str, ...]

    def __call__(self, world: World) -> World:
        new = {hub_id: Hub(world.terms.hub_capacity) for hub_id in self.hub_ids}
        return replace(world, hubs={**world.hubs, **new})


@dataclass(frozen=True, slots=True)
class Sell:
    """A shipment arrives on Earth and sells at the prices of that week."""

    load: Mapping[str, int]  # tonnes of each ore type

    def __call__(self, world: World) -> World:
        return post(world, "sell ore", market.value(self.load, world.week))


# --- Commands --------------------------------------------------------------------------


def build(world: World, hub_ids: Sequence[str]) -> World:
    require(not is_over(world), GAME_IS_OVER)
    require(hub_ids, NO_HUBS)
    require(len(set(hub_ids)) == len(hub_ids), HUB_ID_REPEATED)
    on_order = {
        hub_id
        for _, event in pending(world)
        if isinstance(event, Deliver)
        for hub_id in event.hub_ids
    }
    known = sorted(set(hub_ids) & (world.hubs.keys() | on_order))
    require(not known, HUB_EXISTS, known)

    cost = world.terms.build
    world = pay(world, "build hubs", len(hub_ids) * cost.rate)
    return schedule(world, cost.weeks, Deliver(tuple(hub_ids)))


def deploy(world: World, places: Mapping[str, int]) -> World:
    """Send hubs to sectors. A hub that has a place leaves it."""
    return _send(world, places, "deploy hubs", world.terms.deploy)


def move(world: World, places: Mapping[str, int]) -> World:
    """Send hubs that have a place to new sectors."""
    idle = [hub_id for hub_id in places if hub_id in world.hubs and hub_id not in world.sites]
    require(not idle, HUB_HAS_NO_PLACE, idle)
    return _send(world, places, "move hubs", world.terms.move)


def _send(world: World, places: Mapping[str, int], item: str, cost: Cost) -> World:
    require(not is_over(world), GAME_IS_OVER)
    require(places, NO_HUBS)
    unknown = [hub_id for hub_id in places if hub_id not in world.hubs]
    require(not unknown, UNKNOWN_HUB, unknown)
    travelling = [hub_id for hub_id in places if in_transit(world, hub_id)]
    require(not travelling, HUB_IN_TRANSIT, travelling)

    world = pay(world, item, len(places) * cost.rate)
    world = claim_all(reduce(lift, places, world), places)
    return reduce(lambda w, hub_id: schedule(w, cost.weeks, Land(hub_id)), places, world)


def ship(world: World, hub_ids: Sequence[str]) -> World:
    """Send the ore of the given hubs to Earth. The hubs continue to mine."""
    require(not is_over(world), GAME_IS_OVER)
    require(hub_ids, NO_HUBS)
    unknown = [hub_id for hub_id in hub_ids if hub_id not in world.hubs]
    require(not unknown, UNKNOWN_HUB, unknown)
    load = sum((world.hubs[hub_id].hold for hub_id in set(hub_ids)), Counter())
    tonnes = sum(load.values())
    require(tonnes > 0, NO_ORE)

    cost = world.terms.ship
    world = pay(world, "ship ore", tonnes * cost.rate / 1000)
    emptied = {hub_id: Hub(world.hubs[hub_id].capacity) for hub_id in hub_ids}
    world = replace(world, hubs={**world.hubs, **emptied})
    return schedule(world, cost.weeks, Sell(load))
