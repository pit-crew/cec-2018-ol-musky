"""Scenario: the constants, costs, and asteroid belt for one game.

A Scenario is immutable. The ScenarioStore holds the active one and replaces it
as a unit (hot swap), thus no request sees a partially changed scenario.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

COST_ITEMS = ("hub", "deploy", "ship", "move")


class ScenarioError(Exception):
    """The scenario is absent or not valid."""


class CostSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: str = Field(max_length=16)
    weeks: int = Field(ge=0)
    rate: float = Field(ge=0)


class Sector(BaseModel):
    model_config = ConfigDict(frozen=True)

    ore_id: str = Field(min_length=1, max_length=8)
    deposit_amt: int = Field(ge=0)


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(min_length=1, max_length=32)
    lifetime: int = Field(gt=0)  # weeks
    rows: int = Field(gt=0)
    cols: int = Field(gt=0)
    hub_capacity: int = Field(gt=0)  # tonnes
    mining_rate: int = Field(gt=0)  # tonnes for each week
    starting_capital: int = Field(ge=0)  # millions of dollars
    ms_per_week: int = Field(gt=0)
    prospecting_offset: int = Field(default=7, gt=0)
    costs: dict[str, CostSpec]
    belt: tuple[Sector, ...]  # index is the sector ID

    @model_validator(mode="after")
    def _check_consistency(self) -> "Scenario":
        missing = [item for item in COST_ITEMS if item not in self.costs]
        if missing:
            raise ValueError(f"costs are missing for: {missing}")
        expected = self.rows * self.cols
        if len(self.belt) != expected:
            raise ValueError(f"belt has {len(self.belt)} sectors; rows*cols requires {expected}")
        if self.prospecting_offset > self.lifetime:
            raise ValueError("prospecting_offset must not be larger than lifetime")
        return self

    def parameters_dict(self) -> dict[str, Any]:
        """Body of the /mcp/parameters response, as the Django application returned it."""
        return {
            "lifetime": self.lifetime,
            "rows": self.rows,
            "cols": self.cols,
            "hub_capacity": self.hub_capacity,
            "mining_rate": self.mining_rate,
            "ms_per_week": self.ms_per_week,
            "costs": {item: cost.model_dump() for item, cost in self.costs.items()},
        }


def read_belt_file(path: Path) -> tuple[Sector, ...]:
    """Read a belt CSV. Each line is `ore_id,deposit_amt`; the line number is the sector ID."""
    sectors = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            ore_id, deposit_amt = line.split(",")
            sectors.append(Sector(ore_id=ore_id.strip(), deposit_amt=int(deposit_amt)))
        except (ValueError, ValidationError) as exc:
            raise ScenarioError(f"{path}:{line_number}: bad belt record {line!r}") from exc
    return tuple(sectors)


def read_scenario_file(path: Path) -> Scenario:
    """Read a scenario YAML file (config/mcp.yaml format) and the belt file that it names."""
    try:
        cfg = yaml.safe_load(path.read_text())
        constants = cfg["constants"]
        belt = cfg["belt"]
        costs = {
            item: CostSpec(item=item, weeks=spec["weeks"], rate=spec["rate"])
            for item, spec in cfg["costs"].items()
        }
        return Scenario(
            scenario_id=cfg["scenario_id"],
            lifetime=constants["lifetime"],
            hub_capacity=constants["hub_capacity"],
            mining_rate=constants["mining_rate"],
            starting_capital=constants["starting_capital"],
            ms_per_week=constants["ms_per_week"],
            rows=belt["rows"],
            cols=belt["cols"],
            prospecting_offset=belt.get("prospecting_offset", 7),
            costs=costs,
            belt=read_belt_file(path.parent / belt["file"]),
        )
    except ScenarioError:
        raise
    except (OSError, KeyError, TypeError, yaml.YAMLError, ValidationError) as exc:
        raise ScenarioError(f"{path}: {exc}") from exc


class ScenarioStore:
    """Holds the active scenario for the process."""

    def __init__(self) -> None:
        self._current: Scenario | None = None

    @property
    def current(self) -> Scenario | None:
        return self._current

    def activate(self, scenario: Scenario) -> None:
        self._current = scenario
