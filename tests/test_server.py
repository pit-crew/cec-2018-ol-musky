"""Scenario, league, and HTTP server tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ol_musky import game, league, market
from ol_musky.league import League
from ol_musky.rejection import Rejected
from ol_musky.scenario import read_scenario, read_teams
from ol_musky.server import create_app

CONFIG = Path(__file__).resolve().parent.parent / "config"
TOKEN = "71a653928dc1152537d002cd1349f0d4"


class FakeClock:
    """A clock that the test moves. One week of the repository scenario is 200 ms."""

    def __init__(self) -> None:
        self.now = datetime(2018, 3, 9, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def weeks(self, count: float) -> None:
        self.now += timedelta(milliseconds=200 * count)


@pytest.fixture(scope="module")
def scenario():
    return read_scenario(CONFIG / "mcp.yaml")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def teams(scenario, clock) -> League:
    this_league = League(scenario, clock=clock, seeds=lambda: 2018)
    this_league.register(TOKEN, "testgremlins")
    return this_league


def best_sector(scenario) -> int:
    """An interior sector whose ring holds much ore."""
    world = scenario.new_world()
    from ol_musky.placement import ring

    return max(
        range(len(world.asteroids)),
        key=lambda s: sum(world.asteroids[cell].deposit for cell in ring(world, s)),
    )


# --- Scenario files --------------------------------------------------------------------


def test_read_the_repository_scenario(scenario):
    assert scenario.name == "debug"
    assert (len(scenario.asteroids), scenario.cols) == (4800, 120)
    assert (scenario.rate, scenario.ms_per_week) == (383, 200)
    terms = scenario.terms
    assert (terms.lifetime, terms.starting_capital, terms.hub_capacity) == (600, 175, 25000)
    assert (terms.build.rate, terms.build.weeks) == (20, 5)
    assert (terms.ship.rate, terms.ship.weeks) == (1.5, 18)
    assert terms.survey_passes == 7
    assert {asteroid.ore for asteroid in scenario.asteroids} == {"X", "Y"}


def test_scenario_rejects_a_belt_of_the_wrong_size(tmp_path):
    for name in ("mcp.yaml", "belt_map-dev.csv"):
        (tmp_path / name).write_text((CONFIG / name).read_text())
    belt = tmp_path / "belt_map-dev.csv"
    belt.write_text("\n".join(belt.read_text().splitlines()[:-1]))
    with pytest.raises(ValueError, match="4799 sectors"):
        read_scenario(tmp_path / "mcp.yaml")


def test_read_teams(tmp_path):
    assert read_teams(CONFIG / "teams.yaml") == {"dev": "developer"}
    assert read_teams(tmp_path / "absent.yaml") == {}


# --- League: teams and their clocks ----------------------------------------------------


def test_a_team_has_no_game_until_it_starts(teams):
    assert teams.team(TOKEN).world is None
    with pytest.raises(Rejected, match=league.NOT_STARTED):
        teams.current(TOKEN)
    with pytest.raises(Rejected, match=league.UNKNOWN_TEAM):
        teams.start("nobody")


def test_the_clock_of_a_team_starts_when_the_team_starts(teams, clock):
    clock.weeks(50)
    team = teams.start(TOKEN)
    assert (team.start_time, team.world.week, team.world.seed) == (clock.now, 0, 2018)
    clock.weeks(7.9)
    assert teams.current(TOKEN).world.week == 7


def test_each_team_has_its_own_clock(teams, clock):
    teams.register("late", "latecomers")
    teams.start(TOKEN)
    clock.weeks(30)
    teams.start("late")
    clock.weeks(5)
    assert teams.current(TOKEN).world.week == 35
    assert teams.current("late").world.week == 5


def test_a_team_can_start_again_at_any_time(teams, clock):
    teams.start(TOKEN)
    teams.command(TOKEN, lambda world: game.build(world, ["A"]))
    clock.weeks(40)
    assert "A" in teams.current(TOKEN).world.hubs

    again = teams.start(TOKEN)
    assert (again.world.week, again.world.hubs, len(again.world.ledger)) == (0, {}, 1)
    assert again.start_time == clock.now


def test_a_world_moves_forward_only_when_something_asks_for_it(teams, clock):
    teams.start(TOKEN)
    clock.weeks(100)
    assert teams.team(TOKEN).world.week == 0  # nothing asked
    assert teams.current(TOKEN).world.week == 100
    assert teams.team(TOKEN).world.week == 100


def test_the_world_stops_at_the_last_week_and_the_clock_continues(teams, clock):
    teams.start(TOKEN)
    clock.weeks(700)
    team = teams.current(TOKEN)
    assert team.world.week == 600
    assert teams.week_now(team) == 700


def test_a_rejected_command_leaves_the_team_unchanged(teams, clock):
    teams.start(TOKEN)
    before = teams.current(TOKEN)
    with pytest.raises(Rejected):
        teams.command(TOKEN, lambda world: game.build(world, ["A"] * 2))
    assert teams.team(TOKEN) == before


# --- HTTP API --------------------------------------------------------------------------


class Mcp:
    def __init__(self, client: TestClient, token: str = TOKEN) -> None:
        self.client, self.token = client, token

    def get(self, action: str, **params) -> dict:
        response = self.client.get(f"/mcp/{action}", params={"token": self.token, **params})
        assert response.status_code == 200
        return response.json()

    def ok(self, action: str, key: str | None = None, **params):
        body = self.get(action, **params)
        assert (body["status"], body["description"]) == (0, ""), body
        return body[key or action]

    def fails(self, code: int, action: str, key: str | None = None, **params) -> dict:
        body = self.get(action, **params)
        assert body["status"] == code, body
        assert (key or action) in body, body
        return body


@pytest.fixture
def mcp(teams) -> Mcp:
    return Mcp(TestClient(create_app(teams)))


def test_token_checks(mcp):
    body = mcp.client.get("/mcp/parameters").json()
    assert body == {
        "validation": {},
        "status": 1001,
        "description": "token required - see competition coordinator",
    }
    for token in ("x" * 33, "bad token", "semi;colon"):
        Mcp(mcp.client, token).fails(1000, "parameters", "validation")
    Mcp(mcp.client, "nobody").fails(1100, "status_report", "validation")
    Mcp(mcp.client, "nobody").fails(2100, "startup")
    mcp.fails(1102, "status_report", "validation")  # the team did not start


def test_parameters(mcp):
    assert mcp.ok("parameters") == {
        "lifetime": 600,
        "rows": 40,
        "cols": 120,
        "hub_capacity": 25000,
        "mining_rate": 383,
        "starting_capital": 175,
        "prospect_weeks": 85,
        "ms_per_week": 200,
        "costs": {
            "build": {"item": "build", "weeks": 5, "rate": 20},
            "deploy": {"item": "deploy", "weeks": 17, "rate": 30},
            "move": {"item": "move", "weeks": 2, "rate": 10},
            "ship": {"item": "ship", "weeks": 18, "rate": 1.5},
        },
    }


def test_startup(mcp):
    assert mcp.ok("startup") == {
        "team": {
            "token": TOKEN,
            "name": "testgremlins",
            "week": 0,
            "start_time": "2018-03-09 00:00:00+00:00",
            "balance": 175,
        },
        "hubs": {},
        "orders": [],
    }


def test_a_full_game_through_the_api(mcp, clock, scenario):
    site = best_sector(scenario)
    mcp.ok("startup")

    assert mcp.ok("build_hubs", hubs="A,B") == {"hubs_built": 2, "week": 0}
    report = mcp.ok("status_report")
    assert report["team"]["balance"] == 135
    assert report["orders"] == [{"week": 5, "action": "deliver_hubs", "hub_list": ["A", "B"]}]

    clock.weeks(5)
    assert mcp.ok("status_report")["hubs"]["A"] == {
        "hub_id": "A",
        "state": "idle",
        "sector_id": None,
        "amt": {},
        "space_remaining": 100,
    }

    assert mcp.ok("deploy_hubs", hubs="A", sector_ids=str(site)) == {"hubs_located": 1}
    report = mcp.ok("status_report")
    hub = report["hubs"]["A"]
    assert (hub["state"], hub["sector_id"]) == ("in_transit", site)
    assert report["orders"] == [
        {"week": 22, "action": "relocate_hubs", "hub_list": ["A"], "sector_id_list": [site]}
    ]

    clock.weeks(17 + 5)
    hub = mcp.ok("status_report")["hubs"]["A"]
    assert (hub["state"], hub["sector_id"]) == ("mining", site)
    assert sum(hub["amt"].values()) == 5 * 8 * 383
    assert hub["space_remaining"] == int(100 * (25000 - 15320) / 25000)

    assert mcp.ok("ship_ore", hubs="A") == {"hubs_dumped": 1, "ore": hub["amt"]}
    assert mcp.ok("status_report")["orders"] == [
        {"week": 45, "action": "sell_ore", "ore_load": hub["amt"]}
    ]

    clock.weeks(18)
    lines = mcp.ok("get_ledger", "ledger")
    assert [line["item"] for line in lines] == [
        "startup", "build hubs", "deploy hubs", "ship ore", "sell ore",
    ]  # fmt: skip
    assert lines[-1]["credit"] == pytest.approx(market.value(hub["amt"], 45))
    balance = sum(line["credit"] - line["debit"] for line in lines)
    assert mcp.ok("status_report")["team"]["balance"] == pytest.approx(balance)

    assert mcp.ok("move_hubs", hubs="A", sector_ids=str(site + 1)) == {"hubs_located": 1}
    final = mcp.ok("final_report")
    assert set(final) == {"team", "hubs", "orders", "ledger"}
    assert final["ledger"][-1]["item"] == "move hubs"


def test_reports(mcp, clock):
    mcp.ok("startup")
    clock.weeks(42)
    assert mcp.ok("market_report") == {"week": 42, "prices": {"X": 2.66, "Y": 7.01}}
    report = mcp.ok("prospect_report")["report"]
    assert [row[0] for row in report] == list(range(0, 4800, 7))
    assert mcp.ok("prospect_report")["report"] == report
    clock.weeks(43)
    assert [row[0] for row in mcp.ok("prospect_report")["report"]][:3] == [1, 8, 15]


def test_error_codes(mcp, clock):
    mcp.ok("startup")
    body = mcp.fails(2301, "build_hubs", hubs="A,B,C,D,E,F,G,H,I")
    assert body["description"].startswith("not enough money")
    mcp.fails(2302, "build_hubs")
    mcp.fails(2302, "build_hubs", hubs="")
    mcp.fails(2302, "build_hubs", hubs="A,A")
    mcp.fails(2302, "build_hubs", hubs="123456789")
    mcp.ok("build_hubs", hubs="A,B,C")
    mcp.fails(2302, "build_hubs", hubs="A")

    mcp.fails(2400, "deploy_hubs", hubs="A")
    mcp.fails(2400, "move_hubs", sector_ids="5")
    mcp.fails(2401, "deploy_hubs", hubs="A", sector_ids="1,2")
    mcp.fails(2404, "deploy_hubs", hubs="A", sector_ids="x")
    mcp.fails(2402, "deploy_hubs", hubs="A", sector_ids="500")  # not delivered
    mcp.fails(2501, "ship_ore")
    mcp.fails(2504, "ship_ore", hubs="Z")

    clock.weeks(5)
    mcp.fails(2402, "deploy_hubs", hubs="A,A", sector_ids="500,900")
    mcp.fails(2404, "deploy_hubs", hubs="A", sector_ids="4800")
    mcp.fails(2404, "deploy_hubs", hubs="A", sector_ids="-1")
    mcp.fails(2407, "deploy_hubs", hubs="A,B", sector_ids="500,502")
    mcp.fails(2408, "move_hubs", hubs="A", sector_ids="500")
    mcp.fails(2502, "ship_ore", hubs="A")
    mcp.ok("deploy_hubs", hubs="A,B", sector_ids="500,900")
    mcp.fails(2403, "deploy_hubs", hubs="A", sector_ids="1500")
    mcp.fails(2407, "deploy_hubs", hubs="C", sector_ids="501")
    mcp.ok("build_hubs", hubs="D,E")  # 15 remain
    body = mcp.fails(2409, "deploy_hubs", hubs="C", sector_ids="1500")
    assert "not enough money" in body["description"]


def test_times_up(mcp, clock):
    mcp.ok("startup")
    mcp.ok("build_hubs", hubs="A")
    clock.weeks(600)
    assert mcp.ok("status_report")["team"]["week"] == 600
    mcp.fails(-1, "build_hubs", "validation", hubs="B")  # the last week: no new commands

    clock.weeks(1)
    for action in ("status_report", "market_report", "prospect_report", "build_hubs",
                   "deploy_hubs", "move_hubs", "ship_ore"):  # fmt: skip
        body = mcp.get(action, hubs="B", sector_ids="1")
        assert body == {
            "validation": {"week": 601, "max": 600},
            "status": -1,
            "description": "times up",
        }, action
    assert mcp.ok("final_report")["team"]["week"] == 600
    assert len(mcp.ok("get_ledger", "ledger")) == 2
    assert mcp.ok("startup")["team"]["week"] == 0


# --- Spectator -------------------------------------------------------------------------


def test_spectator_state(mcp, teams, clock, scenario):
    teams.register("zz-token", "Idlers")
    teams.register("aa-token", "eastbank")
    site = best_sector(scenario)
    mcp.ok("startup")
    mcp.ok("build_hubs", hubs="A,B")
    clock.weeks(5)
    mcp.ok("deploy_hubs", hubs="A", sector_ids=str(site))
    Mcp(mcp.client, "aa-token").ok("startup")
    clock.weeks(17 + 10)

    state = mcp.client.get("/spectator/state").json()
    assert {key: state[key] for key in ("scenario", "rows", "cols", "lifetime")} == {
        "scenario": "debug",
        "rows": 40,
        "cols": 120,
        "lifetime": 600,
    }
    assert (state["starting_capital"], state["ms_per_week"]) == (175, 200)
    assert [team["name"] for team in state["teams"]] == ["eastbank", "Idlers", "testgremlins"]

    eastbank, idlers, gremlins = state["teams"]
    assert idlers == {"name": "Idlers", "state": "waiting"}
    assert eastbank == {
        "name": "eastbank",
        "state": "playing",
        "week": 27,
        "balance": 175,
        "hubs": [],
    }
    assert (gremlins["state"], gremlins["week"], gremlins["balance"]) == ("playing", 32, 105)
    assert gremlins["hubs"] == [
        {"hub_id": "A", "state": "mining", "sector_id": site, "fill": 100},
        {"hub_id": "B", "state": "idle", "sector_id": None, "fill": 0},
    ]


def test_spectator_data_has_no_tokens(mcp):
    mcp.ok("startup")
    for path in ("/spectator/state", "/spectator/belt"):
        text = mcp.client.get(path).text
        assert TOKEN not in text and "token" not in text


def test_spectator_belt(mcp, scenario):
    belt = mcp.client.get("/spectator/belt").json()
    assert (belt["rows"], belt["cols"]) == (40, 120)
    assert len(belt["ores"]) == len(belt["deposits"]) == 4800
    assert set(belt["ores"]) == {"X", "Y"}
    assert belt["deposits"][:50] == [asteroid.deposit for asteroid in scenario.asteroids[:50]]

    # The belt is the scenario belt: it does not change when a team mines.
    mcp.ok("startup")
    assert mcp.client.get("/spectator/belt").json() == belt


def test_the_spectator_view_moves_idle_teams_forward(mcp, teams, clock):
    mcp.ok("startup")
    clock.weeks(250)
    assert teams.team(TOKEN).world.week == 0
    assert mcp.client.get("/spectator/state").json()["teams"][0]["week"] == 250
    clock.weeks(400)
    team = mcp.client.get("/spectator/state").json()["teams"][0]
    assert (team["state"], team["week"]) == ("finished", 600)


def test_spectator_page(mcp):
    response = mcp.client.get("/spectator")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "spectator/state" in response.text
    home = mcp.client.get("/", follow_redirects=False)
    assert home.status_code == 307 and home.headers["location"] == "/spectator"
