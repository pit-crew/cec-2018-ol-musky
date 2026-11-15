import sqlite3
from random import Random

import pytest
from sqlalchemy import func, select

from ol_musky.db.models import Hub, Ledger, Order, Site, Team
from ol_musky.db.scenario_repo import save_scenario
from ol_musky.db.team_repo import TeamStore
from ol_musky.engine import rules
from ol_musky.scenario import ScenarioError, ScenarioStore
from ol_musky.world import World

from .conftest import REPO_ROOT, best_sector


@pytest.fixture
def world(scenario, clock) -> World:
    scenarios = ScenarioStore()
    scenarios.activate(scenario)
    return World(scenarios, clock=clock, rng=Random(1))


def test_world_needs_a_scenario(clock):
    world = World(ScenarioStore(), clock=clock)
    world.tick()
    with pytest.raises(ScenarioError):
        world.register("t", "n")


def test_sync_follows_the_clock(world, clock):
    team = world.register("t1", "eastbank")
    assert (team.week, team.balance) == (0, 175)
    world.dirty.clear()

    assert world.sync(team) == 0
    assert world.dirty == set()
    clock.weeks(3)
    assert world.sync(team) == 3
    assert team.week == 3 and world.dirty == {"t1"}


def test_sync_reports_the_real_week_after_the_end(world, clock):
    team = world.register("t1", "eastbank")
    clock.weeks(700)
    assert world.sync(team) == 700
    assert team.week == 600


def test_tick_moves_all_teams(world, clock):
    first = world.register("t1", "eastbank")
    clock.weeks(10)
    second = world.register("t2", "westbank")
    clock.weeks(5)
    world.tick()
    assert (first.week, second.week) == (15, 5)


def test_register_starts_a_team_again(world, clock):
    team = world.register("t1", "eastbank")
    rules.build_hubs(world.scenario, team, ["A"])
    clock.weeks(8)
    world.tick()
    again = world.register("t1", "eastbank")
    assert world.teams["t1"] is again
    assert (again.week, again.balance, again.hubs, len(again.ledger)) == (0, 175, {}, 1)
    assert again.start_time == clock.now


async def _count(session, model, token="t1"):
    query = select(func.count()).select_from(model)
    if model is not Team:
        query = query.where(model.team_id == token)
    return (await session.execute(query)).scalar()


async def test_store_writes_changes_only_one_time(world, clock, sessions, settings):
    store = TeamStore(sessions)
    scenario = world.scenario
    async with sessions() as session:
        await save_scenario(session, scenario)  # the SQL reports read the belt
    site = best_sector(scenario)
    team = world.register("t1", "eastbank")
    world.register("t2", "westbank")

    rules.build_hubs(scenario, team, ["A", "B"])
    assert await store.flush(world) == 2
    assert await store.flush(world) == 0
    async with sessions() as session:
        assert await _count(session, Team) == 2
        assert await _count(session, Ledger) == 2
        assert await _count(session, Order) == 1
        assert await _count(session, Hub) == 0
        assert await _count(session, Ledger, "t2") == 1

    clock.weeks(5)
    world.tick()
    rules.deploy_hubs(scenario, team, ["A"], [site])
    world.touch(team)
    clock.weeks(17 + 30)
    world.tick()
    rules.ship_ore(scenario, team, ["A"], insured=True)
    world.touch(team)
    await store.flush(world)

    clock.weeks(18)
    world.tick()
    assert await store.flush(world) == 2
    async with sessions() as session:
        stored = (await session.execute(select(Team).where(Team.token == "t1"))).scalar_one()
        assert stored.week == team.week == 70
        assert stored.balance == pytest.approx(team.balance)

        ledger = (await session.execute(select(Ledger).where(Ledger.team_id == "t1"))).scalars()
        ledger = list(ledger)
        assert [entry.item for entry in ledger] == [
            "startup", "build hubs", "deploy hubs", "ship ore", "insurance", "sell ore",
        ]  # fmt: skip
        assert sum(e.credit - e.debit for e in ledger) == pytest.approx(team.balance)

        orders = (await session.execute(select(Order).order_by(Order.id))).scalars().all()
        assert [(o.action, o.complete) for o in orders] == [
            ("deliver_hubs", True), ("relocate_hubs", True), ("ship and sell ore", True),
        ]  # fmt: skip
        assert (orders[1].hub_list, orders[1].sector_id_list) == ("A", str(site))
        assert orders[2].ore_load == team.orders[2].ore_load and orders[2].insured

        hubs = {
            hub.hub_id: hub
            for hub in (await session.execute(select(Hub).where(Hub.team_id == "t1"))).scalars()
        }
        assert (hubs["A"].sector_id, hubs["A"].active) == (site, True)
        assert hubs["A"].amt == team.hubs["A"].amt != {}
        assert (hubs["B"].sector_id, hubs["B"].active) == (-1, False)
        assert await _count(session, Site) == len(team.sites) == 8

    # The legacy SQL reports operate on the new database.
    connection = sqlite3.connect(settings.db_path)
    for report in ("eff.sql", "ship-eff.sql", "sites_summary.sql"):
        rows = connection.execute((REPO_ROOT / "admin" / report).read_text()).fetchall()
        assert rows and rows[0][0] == "eastbank", report
    histogram = connection.execute((REPO_ROOT / "admin" / "hist.sql").read_text()).fetchall()
    assert len(histogram) > 3
    assert all(deposit % 10000 == 0 and set(bar) <= {"#"} for deposit, bar in histogram)
    assert sum(len(bar) for _, bar in histogram) > 100
    connection.close()


async def test_store_replaces_the_rows_of_a_team_that_starts_again(world, clock, sessions):
    store = TeamStore(sessions)
    team = world.register("t1", "eastbank")
    rules.build_hubs(world.scenario, team, ["A"])
    clock.weeks(6)
    world.tick()
    await store.flush(world)

    world.register("t1", "eastbank")
    await store.flush(world)
    async with sessions() as session:
        assert await _count(session, Ledger) == 1
        assert await _count(session, Order) == 0
        assert await _count(session, Hub) == 0
        stored = (await session.execute(select(Team))).scalar_one()
        assert (stored.week, stored.balance) == (0, 175)


async def test_store_lists_registered_teams(world, sessions):
    store = TeamStore(sessions)
    world.register("t2", "westbank")
    world.register("t1", "eastbank")
    await store.flush(world)
    assert await TeamStore(sessions).registered() == [("t1", "eastbank"), ("t2", "westbank")]
