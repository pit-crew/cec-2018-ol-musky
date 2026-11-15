"""Prospecting reports: noisy estimates of a subset of the belt."""

from random import Random

from ol_musky.scenario import Scenario

# The estimate error is +/- (largest deposit / 6.5), which is approximately 15 %.
_ERROR_DIVISOR = 6.5


def pass_number(scenario: Scenario, week: int) -> int:
    """Index of the prospecting pass that is current in the given week."""
    return week // (scenario.lifetime // scenario.prospecting_offset)


def prospect_report(scenario: Scenario, week: int, rng: Random) -> list[tuple[int, str, int]]:
    """Estimates as (sector_id, ore_id, estimated_tonnes) for the current pass.

    Pass N covers each sector whose ID is N, N + offset, N + 2 * offset, and so on.
    The estimates come from the initial belt, not from the deposits that a team
    has mined. Each call makes new noise.
    """
    max_deposit = max(sector.deposit_amt for sector in scenario.belt)
    error = int(max_deposit // _ERROR_DIVISOR)
    first = pass_number(scenario, week)
    return [
        (
            sector_id,
            scenario.belt[sector_id].ore_id,
            max(0, scenario.belt[sector_id].deposit_amt + rng.randint(-error, error)),
        )
        for sector_id in range(first, len(scenario.belt), scenario.prospecting_offset)
    ]
