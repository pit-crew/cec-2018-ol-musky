"""Results export tests."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ol_musky import game, results
from ol_musky.league import League
from ol_musky.ledger import balance
from ol_musky.placement import ring
from ol_musky.scenario import read_scenario
from ol_musky.server import create_app

DATA = Path(__file__).resolve().parent / "data"
ADMIN = Path(__file__).resolve().parent.parent / "admin"
SITE = 3503  # the interior sector of the test belt with the most ore in reach


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2018, 3, 9, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def weeks(self, count: float) -> None:
        self.now += timedelta(milliseconds=200 * count)


@pytest.fixture(scope="module")
def scenario():
    return read_scenario(DATA / "mcp.yaml")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def league(scenario, clock) -> League:
    this_league = League(scenario, clock=clock, seeds=lambda: 2018)
    this_league.register("t1", "eastbank")
    this_league.register("t2", "westbank")
    return this_league


def play(league: League, clock: FakeClock, token: str = "t1") -> None:
    """A short game: one hub mines and ships one time."""
    league.start(token)
    league.command(token, lambda world: game.build(world, ["A", "B"]))
    clock.weeks(5)
    league.command(token, lambda world: game.deploy(world, {"A": SITE}))
    clock.weeks(17 + 10)
    league.command(token, lambda world: game.ship(world, ["A"]))
    clock.weeks(20)
    league.command(token, lambda world: game.build(world, ["C"]))


def rows(path: Path, sql: str, *args) -> list[tuple]:
    with sqlite3.connect(path) as db:
        return db.execute(sql, args).fetchall()


# --- The end of a game -----------------------------------------------------------------


def test_on_finish_is_called_one_time_when_a_game_ends(league, clock):
    finished = []
    league.on_finish = finished.append
    league.start("t1")
    clock.weeks(600)
    league.current("t1")
    assert finished == []  # the last week is not after the end

    clock.weeks(1)
    team = league.current("t1")
    assert finished == [team] and team.world.week == 600
    league.current("t1")
    clock.weeks(50)
    league.current("t1")
    assert len(finished) == 1


def test_a_new_game_of_the_same_team_is_reported_again(league, clock):
    finished = []
    league.on_finish = finished.append
    for _ in range(2):
        league.start("t1")
        clock.weeks(601)
        league.current("t1")
    assert len(finished) == 2
    assert finished[0].start_time < finished[1].start_time


def test_unreported_gives_the_games_that_did_not_end(league, clock):
    league.on_finish = lambda team: None
    league.start("t1")
    clock.weeks(601)
    league.current("t1")  # t1 ended and was reported
    league.start("t2")
    clock.weeks(40)
    assert [(team.name, team.world.week) for team in league.unreported()] == [("westbank", 40)]
    assert League(league.scenario).unreported() == []


# --- export_team -----------------------------------------------------------------------


def test_export_writes_the_game_of_a_team(league, clock, scenario, tmp_path):
    path = tmp_path / "deep" / "results.sqlite3"
    play(league, clock)
    team = league.current("t1")
    results.export_team(path, team, scenario, finished=False, now=clock.now)

    assert rows(path, "SELECT * FROM mcp_team") == [
        ("t1", "eastbank", 52, "2018-03-09 00:00:00+00:00", balance(team.world), 0, str(clock.now))
    ]
    ledger = rows(path, "SELECT week, item, credit, debit FROM mcp_ledger ORDER BY id")
    assert [(week, item) for week, item, _, _ in ledger] == [
        (0, "startup"), (0, "build hubs"), (5, "deploy hubs"), (32, "ship ore"),
        (50, "sell ore"), (52, "build hubs"),
    ]  # fmt: skip
    assert sum(credit - debit for _, _, credit, debit in ledger) == pytest.approx(
        balance(team.world)
    )

    hubs = rows(path, "SELECT hub_id, state, sector_id, amt FROM mcp_hub ORDER BY hub_id")
    assert [hub[:3] for hub in hubs] == [("A", "mining", SITE), ("B", "idle", None)]
    assert json.loads(hubs[0][3]) == dict(team.world.hubs["A"].hold)
    assert rows(path, "SELECT week, action, detail FROM mcp_order") == [
        (57, "deliver_hubs", '{"hub_list": ["C"]}')
    ]

    mined = rows(path, "SELECT sector_id, ore_id, deposit_amt FROM mcp_site ORDER BY sector_id")
    assert [sector for sector, _, _ in mined] == sorted(ring(team.world, SITE))
    assert all(
        (ore, tonnes) == (team.world.asteroids[s].ore, team.world.asteroids[s].deposit)
        for s, ore, tonnes in mined
    )
    belt = rows(path, "SELECT sector_id, ore_id, deposit_amt FROM mcp_belt ORDER BY sector_id")
    assert belt == [(s, a.ore, a.deposit) for s, a in enumerate(scenario.asteroids)]


def test_a_new_export_replaces_the_rows_of_the_team_and_keeps_the_history(
    league, clock, scenario, tmp_path
):
    path = tmp_path / "results.sqlite3"
    play(league, clock, "t1")
    play(league, clock, "t2")
    for token in ("t1", "t2"):
        results.export_team(path, league.current(token), scenario, False, clock.now)

    league.start("t1")  # a new game of t1
    clock.weeks(601)
    results.export_team(path, league.current("t1"), scenario, True, clock.now)

    assert rows(path, "SELECT token, week, finished FROM mcp_team ORDER BY token") == [
        ("t1", 600, 1),  # the new game of t1
        ("t2", 52, 0),  # the rows of t2 did not change
    ]
    assert rows(path, "SELECT balance FROM mcp_team WHERE token = 't1'") == [(175.0,)]
    assert rows(path, "SELECT count(*) FROM mcp_ledger WHERE team_id = 't1'") == [(1,)]
    assert rows(path, "SELECT count(*) FROM mcp_hub WHERE team_id = 't1'") == [(0,)]
    assert rows(path, "SELECT count(*) FROM mcp_site WHERE team_id = 't1'") == [(0,)]
    assert rows(path, "SELECT count(*) FROM mcp_ledger WHERE team_id = 't2'")[0][0] > 4
    assert rows(path, "SELECT count(*) FROM mcp_belt") == [(4800,)]
    history = rows(path, "SELECT token, scenario, week, finished FROM mcp_result ORDER BY id")
    assert history == [("t1", "debug", 104, 0), ("t2", "debug", 52, 0), ("t1", "debug", 600, 1)]


def test_the_sql_reports_run_on_the_export(league, clock, scenario, tmp_path):
    path = tmp_path / "results.sqlite3"
    play(league, clock)
    results.export_team(path, league.current("t1"), scenario, False, clock.now)

    name, available, mined = rows(path, (ADMIN / "eff.sql").read_text())[0]
    world = league.current("t1").world
    assert name == "eastbank"
    assert available == sum(scenario.asteroids[s].deposit for s in ring(world, SITE))
    assert mined == available - sum(world.asteroids[s].deposit for s in ring(world, SITE)) > 0
    assert rows(path, (ADMIN / "ship-eff.sql").read_text()) == [("eastbank", 6, 1, 1, 0)]
    name, total, empty, active = rows(path, (ADMIN / "sites_summary.sql").read_text())[0]
    assert (name, total, empty + active) == ("eastbank", 8, 8)
    assert len(rows(path, (ADMIN / "hist.sql").read_text())) > 3


# --- The server ------------------------------------------------------------------------


def test_the_server_exports_a_game_when_it_ends(league, clock, tmp_path):
    path = tmp_path / "results.sqlite3"
    with TestClient(create_app(league, results_path=path)) as client:
        play(league, clock)
        client.get("/spectator/state")
        assert not path.exists()  # nothing is written while a game runs

        clock.weeks(600)
        client.get("/spectator/state")  # the page reads the team after the end of its game
        assert rows(path, "SELECT name, week, finished FROM mcp_team") == [("eastbank", 600, 1)]
        client.get("/spectator/state")
        assert rows(path, "SELECT count(*) FROM mcp_result") == [(1,)]

        client.get("/mcp/startup", params={"token": "t1"})  # a new game
        clock.weeks(30)
    # The server stopped: the game that did not end is exported.
    assert rows(path, "SELECT name, week, finished FROM mcp_team") == [("eastbank", 30, 0)]
    assert rows(path, "SELECT week, finished FROM mcp_result ORDER BY id") == [(600, 1), (30, 0)]


def test_a_server_with_no_results_path_writes_nothing(league, clock, tmp_path):
    with TestClient(create_app(league)) as client:
        play(league, clock)
        clock.weeks(700)
        client.get("/spectator/state")
    assert list(tmp_path.iterdir()) == []
    assert league.on_finish is None


def test_a_failed_export_does_not_stop_a_request(league, clock, tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    with TestClient(create_app(league, results_path=blocked / "results.sqlite3")) as client:
        league.start("t1")
        clock.weeks(601)
        assert client.get("/spectator/state").status_code == 200
