import asyncio
import json
import sqlite3
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ol_musky.app import create_app
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.db.scenario_repo import save_scenario
from ol_musky.db.team_repo import add_team
from ol_musky.engine import market

from .conftest import best_sector

TOKEN = "71a653928dc1152537d002cd1349f0d4"


def _prepare(settings, scenario=None, teams=()):
    async def run():
        engine = make_engine(settings)
        async with make_session_factory(engine)() as session:
            if scenario is not None:
                await save_scenario(session, scenario)
            for token, name in teams:
                row = {"week": 0, "start_time": datetime.now(UTC), "balance": 0}
                await add_team(session, token, name, row)
        await engine.dispose()

    asyncio.run(run())


class Mcp:
    """Test client for one team."""

    def __init__(self, client: TestClient, token: str = TOKEN) -> None:
        self.client, self.token = client, token

    def get(self, action: str, **params) -> dict:
        response = self.client.get(f"/mcp/{action}", params={"token": self.token, **params})
        assert response.status_code == 200
        return response.json()

    def ok(self, action: str, key: str | None = None, **params):
        body = self.get(action, **params)
        assert body["status"] == 0, body
        assert body["description"] == ""
        return body[key or action]


@pytest.fixture
def mcp(settings, scenario, clock):
    _prepare(settings, scenario, [(TOKEN, "testgremlins")])
    with TestClient(create_app(settings, clock=clock)) as client:
        yield Mcp(client)


# --- Sprint 1: parameters and token ----------------------------------------------------


def test_parameters(mcp, scenario):
    body = mcp.get("parameters")
    assert body == {"parameters": scenario.parameters_dict(), "status": 0, "description": ""}
    assert "starting_capital" not in body["parameters"]


def test_parameters_without_scenario(settings):
    with TestClient(create_app(settings)) as client:
        body = Mcp(client).get("parameters")
        assert (body["status"], body["parameters"]) == (2200, {})
        assert Mcp(client).get("status_report")["status"] == 2200


def test_token_is_required(mcp):
    response = mcp.client.get("/mcp/parameters")
    assert response.status_code == 200
    assert response.json() == {
        "validation": {},
        "status": 1001,
        "description": "token required - see competition coordinator",
    }


def test_token_format(mcp):
    for token in ("x" * 33, "bad token", "semi;colon"):
        assert Mcp(mcp.client, token).get("parameters")["status"] == 1000, token
    for token in ("x" * 32, "with-dash_ok"):
        assert Mcp(mcp.client, token).get("parameters")["status"] == 0, token


# --- Team endpoints --------------------------------------------------------------------


def test_startup(mcp, clock):
    assert mcp.ok("startup") == {
        "team": {
            "token": TOKEN,
            "name": "testgremlins",
            "week": 0,
            "start_time": "2018-03-09 00:00:00+00:00",
            "balance": 175,
        },
        "hubs": {},
        "pending_orders": [],
    }


def test_startup_starts_the_game_again(mcp, clock):
    mcp.ok("build_hubs", hubs="A")
    clock.weeks(9)
    assert mcp.ok("status_report")["team"]["week"] == 9
    session = mcp.ok("startup")
    assert (session["team"]["week"], session["team"]["balance"]) == (0, 175)
    assert session["hubs"] == {} and session["pending_orders"] == []
    assert len(mcp.ok("get_ledger", "ledger")) == 1


def test_unknown_team(mcp):
    other = Mcp(mcp.client, "nobody")
    for action in ("status_report", "market_report", "prospect_report", "build_hubs",
                   "deploy_hubs", "move_hubs", "ship_ore", "get_ledger"):  # fmt: skip
        body = other.get(action)
        assert (body["status"], body["validation"]) == (1100, {}), action
        assert "nobody" in body["description"]
    body = other.get("startup")
    assert body["status"] == 2100 and "Exception - startup" in body
    assert other.ok("final_report") == {}


def test_full_game_flow(mcp, clock, scenario):
    site = best_sector(scenario)
    mcp.ok("startup")

    assert mcp.ok("build_hubs", hubs="A,B") == {"hubs_built": 2, "week": 0}
    report = mcp.ok("status_report")
    assert report["team"]["balance"] == 135
    assert report["hubs"] == {}
    assert report["orders"] == [
        {
            "week": 5,
            "action": "deliver_hubs",
            "hub_list": "A,B",
            "sector_id_list": "",
            "ore_load": "{}",
            "complete": False,
        }
    ]

    clock.weeks(5)
    report = mcp.ok("status_report")
    assert report["orders"] == []
    assert report["hubs"]["A"] == {
        "hub_id": "A",
        "start_time": "2018-03-09 00:00:00+00:00",
        "sector_id": -1,
        "amt": "{}",
        "space_remaining": 100,
        "active": False,
    }

    result = mcp.ok("deploy_hubs", "deploy hubs", hubs="A", sector_ids=str(site))
    assert result == {"hubs relocated": 1, "cost": 30.0}
    order = mcp.ok("status_report")["orders"][0]
    assert (order["week"], order["action"], order["hub_list"], order["sector_id_list"]) == (
        22, "relocate_hubs", "A", str(site),
    )  # fmt: skip

    clock.weeks(17 + 10)
    hub = mcp.ok("status_report")["hubs"]["A"]
    assert (hub["sector_id"], hub["active"]) == (site, True)
    amt = json.loads(hub["amt"])
    assert sum(amt.values()) > 0
    assert hub["space_remaining"] == 100 - int(100 * sum(amt.values()) / 25000)
    assert hub["start_time"] == "2018-03-09 00:00:06.400000+00:00"  # week 32

    result = mcp.ok("ship_ore", hubs="A", insured="TRUE")
    assert result == {"hubs_dumped": 1, "ore": amt}
    order = mcp.ok("status_report")["orders"][0]
    assert (order["week"], order["action"], json.loads(order["ore_load"])) == (
        50, "ship and sell ore", amt,
    )  # fmt: skip

    clock.weeks(18)
    report = mcp.ok("status_report")
    assert report["orders"] == []
    ledger = mcp.ok("get_ledger", "ledger")
    assert [entry["item"] for entry in ledger] == [
        "startup", "build hubs", "deploy hubs", "ship ore", "insurance", "sell ore",
    ]  # fmt: skip
    assert set(ledger[0]) == {"week", "item", "credit", "debit"}
    prices = market.prices(50)
    assert ledger[-1]["week"] == 50
    assert ledger[-1]["credit"] == pytest.approx(
        sum(tonnes * prices[ore] / 1000 for ore, tonnes in amt.items())
    )
    balance = sum(entry["credit"] - entry["debit"] for entry in ledger)
    assert report["team"]["balance"] == int(balance // 1)

    result = mcp.ok("move_hubs", "move hubs", hubs="A", sector_ids=str(site + 1))
    assert result == {"hubs relocated": 1, "cost": 10.0}


def test_rule_errors_use_the_envelope(mcp, clock):
    body = mcp.get("build_hubs", hubs="A,B,C,D,E,F,G,H,I")
    assert body == {
        "build_hubs": {"hubs_to_build": 9},
        "status": 2301,
        "description": "not enough money",
    }
    assert mcp.get("build_hubs")["status"] == 2302
    assert mcp.get("build_hubs", hubs="")["status"] == 2302

    body = mcp.get("deploy_hubs", hubs="A")
    assert body["status"] == 2400 and "deploy hubs" in body
    body = mcp.get("move_hubs", sector_ids="5")
    assert body["status"] == 2400 and "move hubs" in body
    assert mcp.get("deploy_hubs", hubs="A", sector_ids="x")["status"] == 2404
    assert mcp.get("deploy_hubs", hubs="A", sector_ids="1,2")["status"] == 2401
    assert mcp.get("deploy_hubs", hubs="A", sector_ids="4800")["status"] == 2404
    assert mcp.get("deploy_hubs", hubs="A", sector_ids="1")["status"] == 2402

    assert mcp.get("ship_ore")["status"] == 2501
    assert mcp.get("ship_ore", hubs="A")["status"] == 2501
    mcp.ok("build_hubs", hubs="A")
    clock.weeks(5)
    body = mcp.get("ship_ore", hubs="A")
    assert (body["status"], body["ship_ore"]) == (2502, {"hubs_to_unload": 1})
    assert mcp.get("move_hubs", hubs="A", sector_ids="1")["status"] == 2408


def test_market_report(mcp, clock):
    clock.weeks(42)
    assert mcp.ok("market_report") == {
        "week": 42,
        "prices": {"X": 2.66, "Y": 7.01},
        "status": 0,
    }


def test_prospect_report(mcp, clock, scenario):
    report = mcp.ok("prospect_report")["report"]
    assert [row[0] for row in report] == list(range(0, 4800, 7))
    sector_id, ore_id, estimate = report[3]
    assert ore_id == scenario.belt[sector_id].ore_id
    assert isinstance(estimate, int) and estimate >= 0

    clock.weeks(85)  # lifetime 600 // offset 7: a new pass each 85 weeks
    report = mcp.ok("prospect_report")["report"]
    assert [row[0] for row in report][:3] == [1, 8, 15]


def test_times_up(mcp, clock):
    mcp.ok("build_hubs", hubs="A")
    clock.weeks(600)
    assert mcp.ok("status_report")["team"]["week"] == 600
    clock.weeks(1)
    for action in ("status_report", "market_report", "prospect_report", "build_hubs",
                   "deploy_hubs", "move_hubs", "ship_ore"):  # fmt: skip
        body = mcp.get(action, hubs="B", sector_ids="1")
        assert body == {
            "validation": {"week": 601, "max": 600},
            "status": -1,
            "description": "times up",
        }, action
    report = mcp.ok("final_report")
    assert report["team"]["week"] == 600
    assert set(report) == {"team", "hubs", "orders", "ledger"}
    assert report["ledger"] == mcp.ok("get_ledger", "ledger")
    assert [entry["item"] for entry in report["ledger"]] == ["startup", "build hubs"]
    assert "ledger" not in mcp.ok("startup")
    assert mcp.ok("startup")["team"]["week"] == 0


def test_idle_team_moves_forward_with_no_requests(mcp, clock):
    mcp.ok("build_hubs", hubs="A")
    clock.weeks(7)
    team = mcp.client.app.state.world.teams[TOKEN]
    deadline = time.monotonic() + 5
    while team.week != 7 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert team.week == 7
    assert "A" in team.hubs and team.pending_orders() == []


def test_state_is_in_the_database_after_shutdown(settings, scenario, clock):
    _prepare(settings, scenario, [(TOKEN, "testgremlins"), ("other", "idlers")])
    site = best_sector(scenario)
    with TestClient(create_app(settings, clock=clock)) as client:
        mcp = Mcp(client)
        mcp.ok("build_hubs", hubs="A")
        clock.weeks(5)
        mcp.ok("deploy_hubs", "deploy hubs", hubs="A", sector_ids=str(site))
        clock.weeks(40)
        mcp.ok("ship_ore", hubs="A")
        clock.weeks(20)
        ledger = mcp.ok("get_ledger", "ledger")

    connection = sqlite3.connect(settings.db_path)
    query = connection.execute
    assert query("select name, week from mcp_team order by name").fetchall() == [
        ("idlers", 65),
        ("testgremlins", 65),
    ]
    balance, total, entries = query(
        "select t.balance, sum(l.credit - l.debit), count(*) from mcp_team t "
        "join mcp_ledger l on l.team_id = t.token where t.token = ?",
        (TOKEN,),
    ).fetchone()
    assert entries == len(ledger) == 5
    assert balance == pytest.approx(total)
    assert query("select action, complete from mcp_order order by id").fetchall() == [
        ("deliver_hubs", 1),
        ("relocate_hubs", 1),
        ("ship and sell ore", 1),
    ]
    assert query("select hub_id, sector_id, active from mcp_hub").fetchall() == [("A", site, 1)]
    assert query("select count(*) from mcp_site").fetchone() == (8,)
    connection.close()


def test_teams_start_again_when_the_server_starts(settings, scenario, clock):
    _prepare(settings, scenario, [(TOKEN, "testgremlins")])
    with TestClient(create_app(settings, clock=clock)) as client:
        Mcp(client).ok("build_hubs", hubs="A")
        clock.weeks(10)

    with TestClient(create_app(settings, clock=clock)) as client:
        report = Mcp(client).ok("status_report")
        assert report["team"] == {
            "token": TOKEN,
            "name": "testgremlins",
            "week": 0,
            "start_time": str(clock.now),
            "balance": 175,
        }
        assert report["hubs"] == {}

    connection = sqlite3.connect(settings.db_path)
    assert connection.execute("select count(*) from mcp_ledger").fetchone() == (1,)
    assert connection.execute("select count(*) from mcp_order").fetchone() == (0,)
    connection.close()
