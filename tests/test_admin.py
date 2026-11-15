"""Belt file and admin tests."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ol_musky import belt_files
from ol_musky.belt import BeltSpec, make_belt
from ol_musky.belt_files import BeltFileError
from ol_musky.league import League
from ol_musky.scenario import read_belt, read_scenario
from ol_musky.server import create_app

CONFIG = Path(__file__).resolve().parent / "data"
KEY = "s3cret-key"
SPEC = BeltSpec()


@pytest.fixture
def scenario_path(tmp_path) -> Path:
    """A copy of the repository scenario and its belt in a temporary directory."""
    for name in ("mcp.yaml", "belt_map-dev.csv", "test_map-dev.csv"):
        shutil.copy(CONFIG / name, tmp_path / name)
    return tmp_path / "mcp.yaml"


# --- Belt files ------------------------------------------------------------------------


def test_save_and_load_a_belt(tmp_path):
    belt = make_belt(SPEC, 1)
    path = belt_files.save_belt(tmp_path, "final-2026", belt, SPEC, 1)
    assert path == tmp_path / "final-2026.csv"
    assert belt_files.load_belt(tmp_path, "final-2026") == belt
    assert read_belt(path) == belt  # the scenario reader ignores the comment lines
    assert belt_files.origin(path) == {"seed": 1, "spec": {**_spec_dict(SPEC)}}
    assert make_belt(BeltSpec(**belt_files.origin(path)["spec"]), 1) == belt  # made again


def _spec_dict(spec: BeltSpec) -> dict:
    return {name: getattr(spec, name) for name in spec.__slots__}


def test_save_does_not_replace_a_file(tmp_path):
    belt = make_belt(SPEC, 1)
    belt_files.save_belt(tmp_path, "a", belt, SPEC, 1)
    with pytest.raises(BeltFileError, match="exists"):
        belt_files.save_belt(tmp_path, "a", belt, SPEC, 1)


@pytest.mark.parametrize("name", ["", "../x", "a/b", "a.csv", "has space", "-start", "x" * 41])
def test_bad_belt_names_are_rejected(tmp_path, name):
    with pytest.raises(BeltFileError, match="belt name"):
        belt_files.save_belt(tmp_path, name, make_belt(SPEC, 1), SPEC, 1)
    with pytest.raises(BeltFileError):
        belt_files.load_belt(tmp_path, name)
    assert list(tmp_path.parent.glob("x.csv")) == []


def test_belt_names_and_origin_of_a_file_from_2018(scenario_path):
    assert belt_files.belt_names(scenario_path.parent) == ["belt_map-dev", "test_map-dev"]
    assert belt_files.origin(scenario_path.parent / "belt_map-dev.csv") is None
    with pytest.raises(BeltFileError, match="no belt"):
        belt_files.load_belt(scenario_path.parent, "absent")


def test_select_belt_changes_only_the_file_name(scenario_path):
    belt = make_belt(SPEC, 1)
    belt_files.save_belt(scenario_path.parent, "dense", belt, SPEC, 1)
    before = scenario_path.read_text()
    assert belt_files.selected_belt(scenario_path) == "belt_map-dev"

    belt_files.select_belt(scenario_path, "dense")
    after = scenario_path.read_text()
    assert belt_files.selected_belt(scenario_path) == "dense"
    assert after == before.replace("file: belt_map-dev.csv", "file: dense.csv")
    assert "# cols = 3*rows" in after  # the comments stay
    assert read_scenario(scenario_path).asteroids == belt


def test_select_belt_rejects_a_belt_of_the_wrong_size(scenario_path):
    before = scenario_path.read_text()
    with pytest.raises(BeltFileError, match="2700 sectors"):
        belt_files.select_belt(scenario_path, "test_map-dev")
    with pytest.raises(BeltFileError, match="no belt"):
        belt_files.select_belt(scenario_path, "absent")
    assert scenario_path.read_text() == before


# --- Admin API -------------------------------------------------------------------------


@pytest.fixture
def client(scenario_path) -> TestClient:
    league = League(read_scenario(scenario_path))
    return TestClient(create_app(league, scenario_path, admin_key=KEY))


def get(client, path, **params):
    return client.get(path, params={"key": KEY, **params})


def post(client, path, body):
    return client.post(path, params={"key": KEY}, json=body)


def test_admin_needs_the_key(client):
    for path in ("/admin", "/admin/belts", "/admin/belt/preview"):
        assert client.get(path).status_code == 403
        assert client.get(path, params={"key": "wrong"}).status_code == 403
        assert get(client, path).status_code == 200
    assert client.post("/admin/belt/select", json={"name": "x"}).status_code == 403
    assert client.post("/admin/belt/save", json={"name": "x"}).status_code == 403


def test_with_no_key_only_the_computer_of_the_server_has_access(scenario_path):
    league = League(read_scenario(scenario_path))
    app = create_app(league, scenario_path)
    assert TestClient(app).get("/admin/belts").status_code == 403  # the test client is not local
    local = TestClient(app, client=("127.0.0.1", 50000))
    assert local.get("/admin/belts").status_code == 200
    assert local.get("/admin").status_code == 200


def test_admin_page(client):
    response = get(client, "/admin")
    assert response.headers["content-type"].startswith("text/html")
    assert "admin/belt/preview" in response.text


def test_preview(client):
    belt = get(client, "/admin/belt/preview").json()
    assert (belt["rows"], belt["cols"], belt["seed"]) == (40, 120, 1)
    assert len(belt["ores"]) == len(belt["deposits"]) == 4800
    assert belt["deposits"] == [a.deposit for a in make_belt(SPEC, 1)]
    assert belt["report"]["good_sites"] == 204
    assert belt["report"]["total_ore"] == 80_000_000

    sparse = get(client, "/admin/belt/preview", coverage=0.1, seed=9, total_ore=20_000_000).json()
    assert sparse["report"]["coverage"] == pytest.approx(0.1)
    assert sparse["report"]["total_ore"] == 20_000_000
    assert sparse["spec"]["coverage"] == 0.1 and sparse["seed"] == 9

    bad = get(client, "/admin/belt/preview", coverage=2)
    assert bad.status_code == 400 and "coverage" in bad.json()["detail"]


def test_save_then_list_then_select(client, scenario_path):
    listing = get(client, "/admin/belts").json()
    assert (listing["loaded"], listing["selected"]) == ("belt_map-dev", "belt_map-dev")
    assert [b["name"] for b in listing["belts"]] == ["belt_map-dev", "test_map-dev"]
    old, wrong = listing["belts"]
    assert old["fits"] and old["origin"] is None and old["report"]["good_sites"] == 186
    assert (wrong["fits"], wrong["sectors"], wrong["report"]) == (False, 2700, None)

    saved = post(client, "/admin/belt/save", {"name": "dense", "seed": 1})
    assert saved.status_code == 200 and saved.json() == {"saved": "dense.csv"}
    assert read_belt(scenario_path.parent / "dense.csv") == make_belt(SPEC, 1)
    again = post(client, "/admin/belt/save", {"name": "dense", "seed": 2})
    assert again.status_code == 400 and "exists" in again.json()["detail"]
    assert post(client, "/admin/belt/save", {"name": "../x", "seed": 1}).status_code == 400

    belt = get(client, "/admin/belt/saved", name="dense").json()
    assert belt["name"] == "dense" and belt["report"]["good_sites"] == 204
    assert get(client, "/admin/belt/saved", name="absent").status_code == 400
    assert get(client, "/admin/belt/saved", name="test_map-dev").status_code == 400

    assert post(client, "/admin/belt/select", {"name": "dense"}).json() == {"selected": "dense"}
    listing = get(client, "/admin/belts").json()
    assert (listing["loaded"], listing["selected"]) == ("belt_map-dev", "dense")
    dense = next(b for b in listing["belts"] if b["name"] == "dense")
    assert dense["origin"]["seed"] == 1 and dense["origin"]["spec"]["coverage"] == 0.4
    assert post(client, "/admin/belt/select", {"name": "test_map-dev"}).status_code == 400
    assert post(client, "/admin/belt/select", {"name": "absent"}).status_code == 400

    # The next start of the server loads the selected belt.
    restarted = create_app(League(read_scenario(scenario_path)), scenario_path, admin_key=KEY)
    assert restarted.state.loaded_belt == "dense"
    assert restarted.state.league.scenario.asteroids == make_belt(SPEC, 1)


def test_the_running_game_keeps_its_belt_after_a_selection(client, scenario_path):
    before = client.get("/spectator/belt").json()
    post(client, "/admin/belt/save", {"name": "dense", "seed": 1})
    post(client, "/admin/belt/select", {"name": "dense"})
    assert client.get("/spectator/belt").json() == before
