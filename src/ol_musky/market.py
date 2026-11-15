"""The ore market. The price of each ore is a fixed function of the week."""

from collections.abc import Mapping
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


def prices(week: int) -> dict[str, float]:
    """Millions of dollars for each 1000 tonnes of each ore, rounded up to 0.01."""
    return {ore: ceil(price(week) * 100) / 100 for ore, price in _PRICE_FUNCTIONS.items()}


def value(load: Mapping[str, int], week: int) -> float:
    """What a load of ore (tonnes of each ore type) sells for in the given week."""
    current = prices(week)
    return sum(tonnes * current[ore] / 1000 for ore, tonnes in load.items())
