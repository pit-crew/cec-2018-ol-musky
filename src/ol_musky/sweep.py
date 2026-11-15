"""The Sweep: mining as a transformation of streams.

The model follows the dataflow idea of the Lucid language. A value is not one
item; it is a stream of items, and an operation applies to streams point by point.

Two dimensions exist:

- Space. The belt is a stream of asteroids; the index is the sector ID.
  `miners` is a sparse stream in parallel with it: at each index, the hub of
  each bot that is at that asteroid.
- Time. A world is one point in a stream of worlds; the index is the week.
  `weeks(world)` is that stream: `world fby sweep(world)` in Lucid terms.

`sweep` makes the world of the next week from the world of this week. It goes
along the asteroid stream in sector sequence and applies `dig` one time for each
bot that it finds. It knows nothing about hubs that are in transit, placement
rules, money, or the geometry of the belt:

- A bot mines because it is in `miners`. A hub that must not mine has no bots there.
- The limits are arithmetic. A bot takes the minimum of its weekly rate, the
  remainder of the deposit, and the free space of its hub. An empty deposit or
  a full hub gives zero.

Thus this module has no conditional statements, and all values are immutable:
`sweep` returns a new world and does not change the world that it reads.
"""

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import replace

from ol_musky.world import Asteroid, Hub, World


def dig(asteroid: Asteroid, hub: Hub, rate: int) -> tuple[Asteroid, Hub]:
    """One bot, one week: move ore from the asteroid to the hub."""
    take = min(rate, asteroid.deposit, hub.free)
    return (
        Asteroid(asteroid.ore, asteroid.deposit - take),
        Hub(hub.capacity, hub.hold + Counter({asteroid.ore: take})),
    )


def sweep(world: World) -> World:
    """The world of the next week."""
    asteroids = list(world.asteroids)
    hubs = dict(world.hubs)
    for sector in sorted(world.miners):
        for hub_id in world.miners[sector]:
            asteroids[sector], hubs[hub_id] = dig(asteroids[sector], hubs[hub_id], world.rate)
    return replace(world, asteroids=tuple(asteroids), hubs=hubs, week=world.week + 1)


def weeks(world: World, step: Callable[[World], World] = sweep) -> Iterator[World]:
    """The stream of worlds from the given world: world, step(world), step(step(world)), ..."""
    while True:
        yield world
        world = step(world)
