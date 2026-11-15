import shutil

import pytest

from ol_musky.scenario import ScenarioError, ScenarioStore, read_scenario_file

from .conftest import SCENARIO_FILE


def test_reads_repository_scenario(scenario):
    assert scenario.scenario_id == "debug"
    assert (scenario.rows, scenario.cols) == (40, 120)
    assert len(scenario.belt) == 4800
    assert set(scenario.costs) == {"hub", "deploy", "ship", "move"}
    assert scenario.costs["ship"].rate == 1.5
    assert scenario.costs["deploy"].weeks == 17
    assert scenario.prospecting_offset == 7
    assert {sector.ore_id for sector in scenario.belt} == {"X", "Y"}


def test_parameters_dict_has_the_legacy_shape(scenario):
    body = scenario.parameters_dict()
    assert list(body) == [
        "lifetime",
        "rows",
        "cols",
        "hub_capacity",
        "mining_rate",
        "ms_per_week",
        "costs",
    ]
    assert body["costs"]["hub"] == {"item": "hub", "weeks": 5, "rate": 20.0}


def _copy_config(tmp_path):
    for name in ("mcp.yaml", "belt_map-dev.csv"):
        shutil.copy(SCENARIO_FILE.parent / name, tmp_path / name)
    return tmp_path / "mcp.yaml"


def test_rejects_belt_of_wrong_size(tmp_path):
    config = _copy_config(tmp_path)
    belt = tmp_path / "belt_map-dev.csv"
    belt.write_text("\n".join(belt.read_text().splitlines()[:-1]) + "\n")
    with pytest.raises(ScenarioError, match="4799 sectors"):
        read_scenario_file(config)


def test_rejects_bad_belt_record(tmp_path):
    config = _copy_config(tmp_path)
    belt = tmp_path / "belt_map-dev.csv"
    lines = belt.read_text().splitlines()
    lines[2] = "X,lots"
    belt.write_text("\n".join(lines) + "\n")
    with pytest.raises(ScenarioError, match="belt_map-dev.csv:3"):
        read_scenario_file(config)


def test_rejects_missing_cost(tmp_path):
    config = _copy_config(tmp_path)
    text = config.read_text().replace("  move:\n    rate: 10\n    weeks: 2\n", "")
    config.write_text(text)
    with pytest.raises(ScenarioError, match="move"):
        read_scenario_file(config)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(ScenarioError):
        read_scenario_file(tmp_path / "absent.yaml")


def test_store_swaps_the_active_scenario(scenario):
    store = ScenarioStore()
    assert store.current is None
    store.activate(scenario)
    other = scenario.model_copy(update={"scenario_id": "final"})
    store.activate(other)
    assert store.current.scenario_id == "final"
