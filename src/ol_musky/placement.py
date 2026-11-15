"""Placement: the commands that put bots into the belt and take them out.

The sweep mines with each bot that is in `world.miners`. This module controls
which bots are there. A command is a function from a world to a new world. A
command that breaks a rule raises Rejected; the world that it read is not
changed, thus a sequence of commands is all or nothing.

The life of a hub in the belt:

    claim  - hold a place: the hub's sector and the adjacent sectors (its footprint)
    land   - put one bot on each adjacent sector: the hub mines from the next sweep
    lift   - take the bots out and release the place

A move is `lift`, then `claim` of the new place, then `land` when the hub arrives.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import reduce

from ol_musky.rejection import require
from ol_musky.world import World

# The rules that a command can break.
UNKNOWN_HUB = "unknown hub"
HUB_HAS_A_PLACE = "hub has a place"
HUB_HAS_NO_PLACE = "hub has no place"
HUB_IS_MINING = "hub is mining"
OUTSIDE_THE_BELT = "sector is outside the belt"
PLACE_IS_TAKEN = "place is taken"


# --- Geometry --------------------------------------------------------------------------


def ring(world: World, sector: int) -> tuple[int, ...]:
    """The sectors adjacent to the given sector: 8, or fewer at the limits of the belt."""
    cols, rows = world.cols, len(world.asteroids) // world.cols
    row, col = divmod(sector, cols)
    return tuple(
        (row + dr) * cols + (col + dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if (dr or dc) and 0 <= row + dr < rows and 0 <= col + dc < cols
    )


def footprint(world: World, sector: int) -> frozenset[int]:
    """The sectors that a hub at the given sector holds: the sector and its ring."""
    return frozenset((sector, *ring(world, sector)))


def taken(world: World) -> frozenset[int]:
    """All sectors that are in the footprint of a hub with a place."""
    return frozenset().union(*(footprint(world, sector) for sector in world.sites.values()))


def is_mining(world: World, hub_id: str) -> bool:
    return any(hub_id in bots for bots in world.miners.values())


class HubState(StrEnum):
    IDLE = "idle"  # the hub holds no place
    IN_TRANSIT = "in_transit"  # the hub holds a place and its bots are not in the belt
    MINING = "mining"  # the bots of the hub are in the belt


def hub_state(world: World, hub_id: str) -> HubState:
    """The state of a hub, from where the hub and its bots are."""
    states = (HubState.IDLE, HubState.IN_TRANSIT, HubState.MINING)
    return states[(hub_id in world.sites) + is_mining(world, hub_id)]


def in_transit(world: World, hub_id: str) -> bool:
    return hub_state(world, hub_id) is HubState.IN_TRANSIT


# --- Commands --------------------------------------------------------------------------


def claim(world: World, hub_id: str, sector: int) -> World:
    """Hold a place for the hub. The footprint must not touch the place of a different hub."""
    require(hub_id in world.hubs, UNKNOWN_HUB, hub_id)
    require(hub_id not in world.sites, HUB_HAS_A_PLACE, hub_id)
    require(0 <= sector < len(world.asteroids), OUTSIDE_THE_BELT, sector)
    collisions = footprint(world, sector) & taken(world)
    require(not collisions, PLACE_IS_TAKEN, sorted(collisions))
    return replace(world, sites={**world.sites, hub_id: sector})


def claim_all(world: World, places: Mapping[str, int]) -> World:
    """Hold a place for each hub. If one claim is rejected, no claim is made."""
    return reduce(lambda w, place: claim(w, *place), places.items(), world)


def land(world: World, hub_id: str) -> World:
    """Put one bot of the hub on each sector adjacent to its place."""
    require(hub_id in world.sites, HUB_HAS_NO_PLACE, hub_id)
    require(not is_mining(world, hub_id), HUB_IS_MINING, hub_id)
    bots = {
        sector: (*world.miners.get(sector, ()), hub_id)
        for sector in ring(world, world.sites[hub_id])
    }
    return replace(world, miners={**world.miners, **bots})


def lift(world: World, hub_id: str) -> World:
    """Take the bots of the hub out of the belt and release its place."""
    miners = {
        sector: remaining
        for sector, bots in world.miners.items()
        if (remaining := tuple(bot for bot in bots if bot != hub_id))
    }
    sites = {hub: sector for hub, sector in world.sites.items() if hub != hub_id}
    return replace(world, miners=miners, sites=sites)


# --- Events ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Land:
    """The arrival of a hub at its place."""

    hub_id: str

    def __call__(self, world: World) -> World:
        return land(world, self.hub_id)
