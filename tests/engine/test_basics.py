from datetime import timedelta
from random import Random

from ol_musky.engine import market, prospecting
from ol_musky.engine.clock import week_at
from ol_musky.engine.grid import adjacent_sectors

from .conftest import COLS, ROWS, START, sector


def test_week_at():
    assert week_at(START, START, 200) == 0
    assert week_at(START, START + timedelta(milliseconds=199), 200) == 0
    assert week_at(START, START + timedelta(milliseconds=200), 200) == 1
    assert week_at(START, START + timedelta(seconds=120), 200) == 600
    assert week_at(START, START - timedelta(seconds=1), 200) == 0


def test_adjacent_sectors_interior():
    assert sorted(adjacent_sectors(sector(4, 5), ROWS, COLS)) == [
        sector(3, 4), sector(3, 5), sector(3, 6),
        sector(4, 4), sector(4, 6),
        sector(5, 4), sector(5, 5), sector(5, 6),
    ]  # fmt: skip


def test_adjacent_sectors_at_the_belt_limits():
    assert sorted(adjacent_sectors(0, ROWS, COLS)) == [1, COLS, COLS + 1]
    assert len(adjacent_sectors(sector(0, 5), ROWS, COLS)) == 5
    assert len(adjacent_sectors(sector(4, COLS - 1), ROWS, COLS)) == 5
    last = ROWS * COLS - 1
    assert sorted(adjacent_sectors(last, ROWS, COLS)) == [last - COLS - 1, last - COLS, last - 1]


def test_market_prices_agree_with_the_2018_server():
    # Reference values from the 2018 competition server.
    assert market.prices(0) == {"X": 4.32, "Y": 9.47}
    assert market.prices(42) == {"X": 2.66, "Y": 7.01}
    assert market.prices(600) == {"X": 4.63, "Y": 8.69}
    assert market.market_report(42) == {"week": 42, "prices": {"X": 2.66, "Y": 7.01}, "status": 0}


def test_market_prices_stay_positive():
    for week in range(0, 1201):
        assert all(price > 0 for price in market.prices(week).values())


def test_prospect_pass_schedule(scenario):
    # lifetime 100, offset 7: a new pass each 14 weeks.
    assert prospecting.pass_number(scenario, 0) == 0
    assert prospecting.pass_number(scenario, 13) == 0
    assert prospecting.pass_number(scenario, 14) == 1
    assert prospecting.pass_number(scenario, 97) == 6


def test_prospect_report_covers_one_pass(scenario):
    report = prospecting.prospect_report(scenario, 0, Random(1))
    assert [row[0] for row in report] == list(range(0, ROWS * COLS, 7))

    report = prospecting.prospect_report(scenario, 14, Random(1))
    assert [row[0] for row in report] == list(range(1, ROWS * COLS, 7))


def test_all_passes_cover_the_belt(scenario):
    seen = set()
    for week in range(0, scenario.lifetime, 14):
        seen.update(row[0] for row in prospecting.prospect_report(scenario, week, Random(1)))
    assert seen == set(range(ROWS * COLS))


def test_prospect_estimates(scenario):
    error = int(1000 // 6.5)
    report = prospecting.prospect_report(scenario, 0, Random(1))
    for sector_id, ore_id, estimate in report:
        assert ore_id == scenario.belt[sector_id].ore_id
        assert 1000 - error <= estimate <= 1000 + error
    assert len({estimate for _, _, estimate in report}) > 1


def test_prospect_estimate_is_not_negative(scenario):
    belt = list(scenario.belt)
    belt[0] = belt[0].model_copy(update={"deposit_amt": 0})
    scenario = scenario.model_copy(update={"belt": tuple(belt)})
    for seed in range(20):
        assert prospecting.prospect_report(scenario, 0, Random(seed))[0][2] >= 0
