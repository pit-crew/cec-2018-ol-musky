"""Ore market. The price of each ore is a fixed function of the week."""

from math import ceil, cos, sin

# The value is 3.14, not pi: the published 2018 prices came from this value.
_RAD = 3.14 / 180


def _price_x(week: int) -> float:
    wave = sin(5 * week * _RAD) + cos(2 * week * _RAD) + sin(week / 10 * _RAD) - 1.55
    return 5 + wave * (5 / 3.989)


def _price_y(week: int) -> float:
    wave = cos(3 * week * _RAD) + cos(7 * week * _RAD) + sin(week / 10 * _RAD) - 1.60
    return 9 + wave * (5 / 4.278)


_PRICE_FUNCTIONS = {"X": _price_x, "Y": _price_y}
ORE_IDS = frozenset(_PRICE_FUNCTIONS)


def prices(week: int) -> dict[str, float]:
    """Price of each ore in millions of dollars for each 1000 tonnes, rounded up to 0.01."""
    return {ore_id: ceil(fn(week) * 100) / 100 for ore_id, fn in _PRICE_FUNCTIONS.items()}


def market_report(week: int) -> dict:
    """Body of the /mcp/market_report response."""
    return {"week": week, "prices": prices(week), "status": 0}
