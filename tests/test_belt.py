"""Belt creation and belt measurement tests."""

from dataclasses import replace
from math import hypot
from pathlib import Path
from random import Random

import pytest

from ol_musky import belt as belt_module
from ol_musky.belt import BeltSpec, hub_sites, largest_gap, make_belt, measure
from ol_musky.scenario import read_belt
from ol_musky.world import Asteroid

SPEC = BeltSpec()
SMALL = BeltSpec(rows=12, cols=30, clusters=3, cluster_size=3, total_ore=1_000_000)


def tonnes(belt, ore=None) -> int:
    return sum(a.deposit for a in belt if ore is None or a.ore == ore)


# --- make_belt: a function of the specification and the seed ---------------------------


def test_the_same_specification_and_seed_give_the_same_belt():
    assert make_belt(SPEC, 7) == make_belt(SPEC, 7)
    assert make_belt(SPEC, 7) != make_belt(SPEC, 8)
    assert make_belt(SPEC, 7) != make_belt(replace(SPEC, clusters=6), 7)


def test_the_belt_has_one_asteroid_for_each_sector():
    belt = make_belt(SMALL, 1)
    assert len(belt) == 12 * 30
    assert {a.ore for a in belt} <= {"X", "Y"}
    assert all(a.deposit >= 0 for a in belt)


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("coverage", [0.05, 0.23, 0.5, 1.0])
def test_coverage_and_total_are_exact(seed, coverage):
    spec = replace(SPEC, coverage=coverage)
    belt = make_belt(spec, seed)
    assert sum(a.deposit > 0 for a in belt) == round(coverage * 4800)
    assert tonnes(belt) == spec.total_ore


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("y_share", [0.0, 0.11, 0.5, 1.0])
def test_ore_y_has_its_share_of_the_tonnes(seed, y_share):
    belt = make_belt(replace(SPEC, y_share=y_share), seed)
    largest = max(a.deposit for a in belt)
    assert abs(tonnes(belt, "Y") - y_share * SPEC.total_ore) <= largest / 2
    assert all(a.deposit > 0 for a in belt if a.ore == "Y")  # ore Y is only where ore is


def test_the_largest_deposit_is_some_times_the_typical_deposit():
    for seed in range(10):
        report = measure(make_belt(SPEC, seed), SPEC.cols, 383, 25000)
        assert 1.5 < report.largest_deposit / report.median_deposit < 5


def test_a_deposit_is_larger_near_the_core_of_a_cluster():
    spec = BeltSpec(rows=41, cols=41, clusters=1, cluster_size=8, coverage=0.6, roughness=0.0)
    belt = make_belt(spec, 3)
    core = max(range(len(belt)), key=lambda s: belt[s].deposit)
    row, col = divmod(core, spec.cols)

    def mean_at(distance: int) -> float:
        cells = [
            belt[r * spec.cols + c].deposit
            for r in range(spec.rows)
            for c in range(spec.cols)
            if round(hypot(r - row, c - col)) == distance
        ]
        return sum(cells) / len(cells)

    assert mean_at(1) > mean_at(4) > mean_at(8)


def test_cluster_centres_keep_a_distance_from_each_other_and_from_the_limits():
    for seed in range(20):
        clusters = belt_module._clusters(SPEC, Random(seed))
        assert len(clusters) == SPEC.clusters
        centres = [(c.row, c.col) for c in clusters]
        nearest = min(
            hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(centres) for b in centres[:i]
        )
        assert nearest > SPEC.cluster_size * 1.5, seed
        margin = SPEC.cluster_size * 0.7
        assert all(margin <= row <= SPEC.rows - 1 - margin for row, _ in centres)
        assert all(margin <= col <= SPEC.cols - 1 - margin for _, col in centres)


def test_more_roughness_gives_more_irregular_deposits():
    def spread(roughness: float) -> float:
        report = measure(make_belt(replace(SPEC, roughness=roughness), 3), 120, 383, 25000)
        return report.largest_deposit / report.median_deposit

    assert spread(0.0) < spread(0.6) < spread(1.2)


def test_small_and_extreme_specifications():
    tiny = make_belt(BeltSpec(rows=3, cols=3, clusters=1, total_ore=900, coverage=1.0), 1)
    assert len(tiny) == 9 and tonnes(tiny) == 900 and all(a.deposit > 0 for a in tiny)
    one = make_belt(replace(SMALL, coverage=0.001), 1)  # at least one sector has ore
    assert sum(a.deposit > 0 for a in one) == 1 and tonnes(one) == SMALL.total_ore
    few = make_belt(replace(SMALL, total_ore=5), 1)  # not more sectors than tonnes
    assert sum(a.deposit > 0 for a in few) == 5 and tonnes(few) == 5


@pytest.mark.parametrize(
    "change",
    [
        {"rows": 2},
        {"clusters": 0},
        {"cluster_size": 0},
        {"coverage": 0},
        {"coverage": 1.1},
        {"total_ore": 0},
        {"y_share": -0.1},
        {"y_share": 1.5},
        {"roughness": -1},
    ],
)
def test_a_bad_specification_is_rejected(change):
    with pytest.raises(ValueError):
        replace(SPEC, **change)


# --- Measurement -----------------------------------------------------------------------


def grid(rows: list[str], deposit: int = 1000) -> tuple[Asteroid, ...]:
    """A belt from a picture: `.` is empty, `x` is ore X, `y` is ore Y."""
    return tuple(
        Asteroid("Y" if cell == "y" else "X", 0 if cell == "." else deposit)
        for row in rows
        for cell in row
    )


def test_hub_sites_are_the_richest_places_whose_footprints_do_not_touch():
    belt = grid(
        [
            "xxx......",
            "x.x......",
            "xxx...xx.",
            ".........",
        ]
    )
    sites = hub_sites(belt, cols=9)
    assert sites[0] == (10, 8000)  # the centre of the ring of 8
    assert sites[1][1] == 2000  # the pair at the right
    assert sites[1][0] in {14, 15, 16, 23, 24, 25, 32, 33, 34}  # a sector that touches the pair
    assert len(sites) == 2


def test_largest_gap():
    belt = grid(
        [
            "x.....x",
            "......x",
            "...x...",
            "......x",
        ]
    )
    assert largest_gap(belt, cols=7) == 3
    assert largest_gap(grid(["xx", "xx"]), cols=2) == 0
    assert largest_gap(grid(["....", "....", "...."]), cols=4) == 3


def test_measure_a_small_belt():
    belt = grid(
        [
            "xxx......",
            "xyx......",
            "xxx...xx.",
            ".........",
        ],
        deposit=5000,
    )
    report = measure(belt, cols=9, rate=100, hub_capacity=10_000, good_site_loads=2)
    assert report.sectors == 36
    assert report.coverage == pytest.approx(11 / 36)
    assert report.total_ore == 55_000
    assert report.y_share == pytest.approx(5000 / 55_000)
    assert (report.largest_deposit, report.median_deposit) == (5000, 5000)
    assert (report.sites, report.good_sites) == (2, 1)  # 40 000 t and 10 000 t in reach
    assert report.best_site_loads == 4.0
    assert report.median_site_loads == 4.0
    assert report.best_site_weeks == 50.0  # 40 000 t / (8 bots x 100 t)
    assert report.ore_in_reach == pytest.approx(50_000 / 55_000)  # the centre has no bot
    assert report.left_share == pytest.approx(45_000 / 55_000)


def test_measure_an_empty_belt():
    report = measure(grid(["...", "...", "..."]), cols=3, rate=100, hub_capacity=1000)
    assert (report.total_ore, report.sites, report.good_sites) == (0, 0, 0)
    assert (report.coverage, report.y_share, report.best_site_loads) == (0, 0, 0)
    assert report.largest_gap == 3


def test_measure_agrees_with_the_targets_of_the_specification():
    report = measure(make_belt(SPEC, 5), SPEC.cols, rate=383, hub_capacity=25000)
    assert report.coverage == pytest.approx(SPEC.coverage, abs=0.001)
    assert report.total_ore == SPEC.total_ore
    assert report.y_share == pytest.approx(SPEC.y_share, abs=0.002)
    assert report.good_sites > 100
    assert 0.6 < report.ore_in_reach < 1


def test_measure_the_belt_of_2018():
    belt = read_belt(Path(__file__).resolve().parent / "data" / "belt_map-dev.csv")
    report = measure(belt, cols=120, rate=383, hub_capacity=25000)
    assert report.coverage == pytest.approx(0.229, abs=0.001)
    assert (report.total_ore, report.largest_deposit) == (80_789_916, 137_244)
    assert (report.sites, report.good_sites) == (229, 186)
