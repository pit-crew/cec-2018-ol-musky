"""Results: the export of the games to a SQLite database.

Nothing is recorded while a game runs. When the game of a team ends, the server
writes the final world of the team to the database one time. When the server
stops, it writes the games that did not end.

The database is for reports. The server does not read it. The tables have the
names that the SQL reports in admin/ use:

    mcp_team    one row for each team: its last exported game
    mcp_ledger  the ledger of that game
    mcp_hub     the hubs at the end of that game
    mcp_order   the work orders that were pending at the end
    mcp_site    the sectors that the team mined, with the ore that remains
    mcp_belt    the belt of the scenario at the start of a game
    mcp_result  one row for each export: the history of all scores

A new export of a team replaces its rows, except in mcp_result.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from ol_musky import reports
from ol_musky.league import Team
from ol_musky.ledger import balance
from ol_musky.scenario import Scenario

SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_team (
    token TEXT PRIMARY KEY, name TEXT NOT NULL, week INTEGER NOT NULL,
    start_time TEXT NOT NULL, balance REAL NOT NULL,
    finished INTEGER NOT NULL, exported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mcp_ledger (
    id INTEGER PRIMARY KEY, team_id TEXT NOT NULL, week INTEGER NOT NULL,
    item TEXT NOT NULL, credit REAL NOT NULL, debit REAL NOT NULL);
CREATE TABLE IF NOT EXISTS mcp_hub (
    id INTEGER PRIMARY KEY, team_id TEXT NOT NULL, hub_id TEXT NOT NULL,
    state TEXT NOT NULL, sector_id INTEGER, amt TEXT NOT NULL, space_remaining INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mcp_order (
    id INTEGER PRIMARY KEY, team_id TEXT NOT NULL, week INTEGER NOT NULL,
    action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mcp_site (
    id INTEGER PRIMARY KEY, team_id TEXT NOT NULL, sector_id INTEGER NOT NULL,
    ore_id TEXT NOT NULL, deposit_amt INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mcp_belt (
    sector_id INTEGER PRIMARY KEY, ore_id TEXT NOT NULL, deposit_amt INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mcp_result (
    id INTEGER PRIMARY KEY, token TEXT NOT NULL, name TEXT NOT NULL, scenario TEXT NOT NULL,
    start_time TEXT NOT NULL, week INTEGER NOT NULL, balance REAL NOT NULL,
    finished INTEGER NOT NULL, exported_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mcp_ledger_team ON mcp_ledger (team_id);
CREATE INDEX IF NOT EXISTS mcp_site_team ON mcp_site (team_id);
"""

TEAM_TABLES = ("mcp_ledger", "mcp_hub", "mcp_order", "mcp_site")


def sites(team: Team, scenario: Scenario) -> list[tuple[int, str, int]]:
    """The sectors that the team mined or mines, as (sector_id, ore, tonnes that remain)."""
    world = team.world
    mined = {
        sector
        for sector, (now, start) in enumerate(zip(world.asteroids, scenario.asteroids, strict=True))
        if now.deposit != start.deposit
    }
    return [
        (sector, world.asteroids[sector].ore, world.asteroids[sector].deposit)
        for sector in sorted(mined | world.miners.keys())
    ]


def export_team(path: Path, team: Team, scenario: Scenario, finished: bool, now: datetime) -> None:
    """Write the game of the team to the database. The rows of the team are replaced."""
    world, token = team.world, team.token
    status = reports.status(world)
    start, total, done, at = str(team.start_time), balance(world), int(finished), str(now)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(SCHEMA)
        for table in TEAM_TABLES:
            db.execute(f"DELETE FROM {table} WHERE team_id = ?", (token,))  # noqa: S608
        db.execute(
            "INSERT OR REPLACE INTO mcp_team VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token, team.name, world.week, start, total, done, at),
        )
        db.execute(
            "INSERT INTO mcp_result (token, name, scenario, start_time, week, balance, finished,"
            " exported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (token, team.name, scenario.name, start, world.week, total, done, at),
        )
        db.executemany(
            "INSERT INTO mcp_ledger (team_id, week, item, credit, debit) VALUES (?, ?, ?, ?, ?)",
            [
                (token, line["week"], line["item"], line["credit"], line["debit"])
                for line in reports.ledger(world)
            ],
        )
        db.executemany(
            "INSERT INTO mcp_hub (team_id, hub_id, state, sector_id, amt, space_remaining)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    token,
                    hub["hub_id"],
                    hub["state"],
                    hub["sector_id"],
                    json.dumps(hub["amt"]),
                    hub["space_remaining"],
                )
                for hub in status["hubs"].values()
            ],
        )
        db.executemany(
            "INSERT INTO mcp_order (team_id, week, action, detail) VALUES (?, ?, ?, ?)",
            [
                (
                    token,
                    order["week"],
                    order["action"],
                    json.dumps({k: v for k, v in order.items() if k not in ("week", "action")}),
                )
                for order in status["orders"]
            ],
        )
        db.executemany(
            "INSERT INTO mcp_site (team_id, sector_id, ore_id, deposit_amt) VALUES (?, ?, ?, ?)",
            [(token, *site) for site in sites(team, scenario)],
        )
        db.execute("DELETE FROM mcp_belt")
        db.executemany(
            "INSERT INTO mcp_belt VALUES (?, ?, ?)",
            [(s, a.ore, a.deposit) for s, a in enumerate(scenario.asteroids)],
        )
