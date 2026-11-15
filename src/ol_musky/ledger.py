"""Money: the ledger of a world.

The ledger is the only record of money. The balance is its total, thus the
balance and the ledger always agree.
"""

from dataclasses import replace

from ol_musky.rejection import require
from ol_musky.world import Entry, World

NOT_ENOUGH_MONEY = "not enough money"


def balance(world: World) -> float:
    return sum(entry.amount for entry in world.ledger)


def post(world: World, item: str, amount: float) -> World:
    """Add a line to the ledger. A positive amount is a credit."""
    return replace(world, ledger=(*world.ledger, Entry(world.week, item, amount)))


def pay(world: World, item: str, cost: float) -> World:
    """Debit the cost. The balance must be sufficient."""
    require(cost <= balance(world), NOT_ENOUGH_MONEY, cost)
    return post(world, item, -cost)
