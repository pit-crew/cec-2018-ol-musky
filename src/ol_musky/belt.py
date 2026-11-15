"""Belt creation: a belt is a function of a specification and a seed.

The same specification and seed always give the same belt. The specification
states the properties of the belt as targets, and the generator reaches them
exactly:

- `coverage`: the fraction of the sectors that have ore. A belt cannot be more
  sparse or more dense than this value.
- `total_ore`: the tonnes in the belt.
- `y_share`: the fraction of the ore that is ore Y.

The ore is in clusters. The centres of the clusters keep a distance from each
other and from the limits of the belt. A deposit is largest at the core of its
cluster and becomes smaller with distance. Ore Y is in veins in some clusters.

`measure` gives the properties of a belt (one that this module made, or one
from a file) that show if the belt gives a good game.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, exp, hypot, pi, sin
from random import Random
from statistics import median

from ol_musky.placement import footprint, ring
from ol_musky.world import Asteroid, World

_CANDIDATES = 40  # candidate positions for each cluster centre; the most distant one is used
# The deposits are in proportion to (raw value) ** _FLATTEN. A value below 1 makes the
# largest deposit only some times the typical deposit, as in the belts of 2018.
_FLATTEN = 0.5


@dataclass(frozen=True, slots=True)
class BeltSpec:
    rows: int = 40
    cols: int = 120
    clusters: int = 7  # the number of ore clusters
    cluster_size: float = 6.0  # the typical radius of a cluster, in sectors
    coverage: float = 0.40  # the fraction of the sectors that have ore
    total_ore: int = 80_000_000  # tonnes
    y_share: float = 0.11  # the fraction of the ore that is ore Y
    roughness: float = 0.6  # 0 = smooth clusters; a larger value = more irregular deposits

    def __post_init__(self) -> None:
        checks = {
            "rows and cols must be 3 or more": self.rows >= 3 and self.cols >= 3,
            "clusters must be 1 or more": self.clusters >= 1,
            "cluster_size must be more than 0": self.cluster_size > 0,
            "coverage must be more than 0 and not more than 1": 0 < self.coverage <= 1,
            "total_ore must be more than 0": self.total_ore > 0,
            "y_share must be from 0 to 1": 0 <= self.y_share <= 1,
            "roughness must be 0 or more": self.roughness >= 0,
        }
        problems = [text for text, ok in checks.items() if not ok]
        if problems:
            raise ValueError("; ".join(problems))


@dataclass(frozen=True, slots=True)
class _Cluster:
    row: float
    col: float
    long: float  # radius along the cluster
    short: float  # radius across the cluster
    angle: float
    weight: float  # how rich the cluster is

    def strength(self, row: int, col: int) -> float:
        """1 at the centre, and smaller with distance. The shape is an ellipse."""
        dx, dy = col - self.col, row - self.row
        along = (dx * cos(self.angle) + dy * sin(self.angle)) / self.long
        across = (-dx * sin(self.angle) + dy * cos(self.angle)) / self.short
        return self.weight * exp(-(along * along + across * across) / 2)


def _clusters(spec: BeltSpec, rng: Random) -> list[_Cluster]:
    """Cluster centres that keep a distance from each other and from the limits of the belt."""
    margin_row = min(spec.cluster_size * 0.7, (spec.rows - 1) / 2)
    margin_col = min(spec.cluster_size * 0.7, (spec.cols - 1) / 2)
    centres: list[tuple[float, float]] = []
    for _ in range(spec.clusters):
        candidates = [
            (
                rng.uniform(margin_row, spec.rows - 1 - margin_row),
                rng.uniform(margin_col, spec.cols - 1 - margin_col),
            )
            for _ in range(_CANDIDATES)
        ]
        # The candidate that is the most distant from the centres that exist.
        centres.append(
            max(
                candidates,
                key=lambda c: min((hypot(c[0] - r, c[1] - k) for r, k in centres), default=0.0),
            )
        )
    clusters = []
    for row, col in centres:
        size = spec.cluster_size * rng.uniform(0.7, 1.35)
        stretch = rng.uniform(1.0, 1.7)
        clusters.append(
            _Cluster(
                row=row,
                col=col,
                long=size * stretch,
                short=size / stretch,
                angle=rng.uniform(0, pi),
                weight=rng.uniform(0.65, 1.0),
            )
        )
    return clusters


def _share_out(total: int, weights: Sequence[float]) -> list[int]:
    """Integers in proportion to the weights, each 1 or more, with the exact total."""
    scale = (total - len(weights)) / sum(weights)
    exact = [weight * scale for weight in weights]
    parts = [int(value) for value in exact]
    remainder = total - len(weights) - sum(parts)
    by_fraction = sorted(range(len(exact)), key=lambda i: exact[i] - parts[i], reverse=True)
    for i in by_fraction[:remainder]:
        parts[i] += 1
    return [part + 1 for part in parts]


def make_belt(spec: BeltSpec, seed: int) -> tuple[Asteroid, ...]:
    """The belt of the specification and the seed: `rows * cols` asteroids, row by row."""
    rng = Random(seed)
    clusters = _clusters(spec, rng)
    sectors = spec.rows * spec.cols

    # The raw value of each sector: the strength of the clusters there, with noise.
    values = []
    for sector in range(sectors):
        row, col = divmod(sector, spec.cols)
        strength = sum(cluster.strength(row, col) for cluster in clusters)
        values.append(strength * exp(spec.roughness * rng.gauss(0, 1)))

    # Coverage: exactly this number of sectors, those with the largest values, have ore.
    count = min(max(round(spec.coverage * sectors), 1), spec.total_ore)
    with_ore = sorted(sorted(range(sectors), key=values.__getitem__, reverse=True)[:count])

    # Total: the deposits follow the values, with the exact total.
    weights = [values[s] ** _FLATTEN for s in with_ore]
    tonnes = dict(zip(with_ore, _share_out(spec.total_ore, weights), strict=True))

    # Ore Y: veins. A vein is a band through a cluster, with irregular edges. The sectors
    # with the largest vein score become ore Y, until ore Y has its share of the tonnes.
    veins = [
        _Cluster(
            row=cluster.row + rng.uniform(-0.4, 0.4) * cluster.short,
            col=cluster.col + rng.uniform(-0.4, 0.4) * cluster.long,
            long=cluster.long * rng.uniform(0.7, 1.1),
            short=max(cluster.short * rng.uniform(0.25, 0.45), 0.8),
            angle=cluster.angle + rng.uniform(-0.6, 0.6),
            weight=rng.uniform(0.5, 1.0),
        )
        for cluster in rng.sample(clusters, k=max(1, (len(clusters) + 1) // 2))
    ]
    score = {
        s: sum(vein.strength(*divmod(s, spec.cols)) for vein in veins) * rng.uniform(0.25, 1.0)
        for s in with_ore
    }
    target = spec.y_share * spec.total_ore
    ore_y: set[int] = set()
    y_tonnes = 0
    for sector in sorted(with_ore, key=score.__getitem__, reverse=True):
        if y_tonnes + tonnes[sector] / 2 > target:
            break
        ore_y.add(sector)
        y_tonnes += tonnes[sector]

    return tuple(
        Asteroid("Y" if sector in ore_y else "X", tonnes.get(sector, 0))
        for sector in range(sectors)
    )


# --- Measurement -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BeltReport:
    sectors: int
    coverage: float  # the fraction of the sectors that have ore
    total_ore: int  # tonnes
    y_share: float  # the fraction of the ore that is ore Y
    largest_deposit: int
    median_deposit: int  # of the sectors that have ore
    # Hub sites: places for hubs whose footprints do not touch, the richest first.
    sites: int  # sites with ore in reach
    good_sites: int  # sites where a hub can fill `good_site_loads` times or more
    best_site_loads: float  # hub loads in reach at the best site
    median_site_loads: float  # hub loads in reach at the median good site
    best_site_weeks: float  # weeks to mine the best site, with all bots at the full rate
    ore_in_reach: float  # the fraction of the ore that the hub sites can reach
    largest_gap: int  # the side of the largest square with no ore, in sectors
    left_share: float  # the fraction of the ore in the left half of the belt


def hub_sites(asteroids: Sequence[Asteroid], cols: int) -> list[tuple[int, int]]:
    """Places for hubs as (sector, tonnes in reach), the richest first.

    The selection is greedy: the sector with the most ore in its 8 adjacent sectors,
    then the best sector whose footprint does not touch a selected one, and so on.
    This is an approximation of the best set, and it is how a simple bot selects sites.
    """
    world = World(asteroids=tuple(asteroids), cols=cols)
    in_reach = {
        sector: sum(asteroids[cell].deposit for cell in ring(world, sector))
        for sector in range(len(asteroids))
    }
    taken: set[int] = set()
    sites = []
    for sector in sorted(in_reach, key=in_reach.__getitem__, reverse=True):
        place = footprint(world, sector)
        if in_reach[sector] > 0 and not place & taken:
            taken |= place
            sites.append((sector, in_reach[sector]))
    return sites


def largest_gap(asteroids: Sequence[Asteroid], cols: int) -> int:
    """The side of the largest square of sectors that has no ore."""
    best = 0
    above = [0] * (cols + 1)
    for start in range(0, len(asteroids), cols):
        row = [0] * (cols + 1)
        for col in range(cols):
            if asteroids[start + col].deposit == 0:
                row[col + 1] = 1 + min(row[col], above[col], above[col + 1])
                best = max(best, row[col + 1])
        above = row
    return best


def measure(
    asteroids: Sequence[Asteroid],
    cols: int,
    rate: int,
    hub_capacity: int,
    good_site_loads: float = 4.0,
) -> BeltReport:
    """The properties of a belt for a game with the given mining rate and hub capacity."""
    deposits = [asteroid.deposit for asteroid in asteroids if asteroid.deposit > 0]
    total = sum(deposits)
    sites = [tonnes for _, tonnes in hub_sites(asteroids, cols)]
    good = [tonnes for tonnes in sites if tonnes >= good_site_loads * hub_capacity]
    left = sum(a.deposit for i, a in enumerate(asteroids) if i % cols < cols / 2)
    return BeltReport(
        sectors=len(asteroids),
        coverage=len(deposits) / len(asteroids),
        total_ore=total,
        y_share=sum(a.deposit for a in asteroids if a.ore == "Y") / max(total, 1),
        largest_deposit=max(deposits, default=0),
        median_deposit=int(median(deposits)) if deposits else 0,
        sites=len(sites),
        good_sites=len(good),
        best_site_loads=sites[0] / hub_capacity if sites else 0.0,
        median_site_loads=median(good) / hub_capacity if good else 0.0,
        best_site_weeks=sites[0] / (8 * rate) if sites else 0.0,
        ore_in_reach=sum(sites) / max(total, 1),
        largest_gap=largest_gap(asteroids, cols),
        left_share=left / max(total, 1),
    )
