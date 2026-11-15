import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, select, text

from ol_musky.db.models import Base, Belt, Cost, Parameter
from ol_musky.db.scenario_repo import load_scenario, save_scenario
from ol_musky.scenario import ScenarioError


def test_migrations_agree_with_models(settings):
    engine = create_engine(settings.sync_db_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    assert diff == []


async def test_scenario_round_trip(sessions, scenario):
    async with sessions() as session:
        await save_scenario(session, scenario)
    async with sessions() as session:
        assert await load_scenario(session) == scenario
        assert await load_scenario(session, "debug") == scenario
        assert (await session.execute(select(func.count()).select_from(Belt))).scalar() == 4800
        assert (await session.execute(select(func.count()).select_from(Cost))).scalar() == 4


async def test_load_replaces_the_stored_scenario(sessions, scenario):
    other = scenario.model_copy(update={"scenario_id": "final", "lifetime": 260})
    async with sessions() as session:
        await save_scenario(session, scenario)
        await save_scenario(session, other)
    async with sessions() as session:
        ids = (await session.execute(select(Parameter.scenario_id))).scalars().all()
        assert ids == ["final"]
        assert (await session.execute(select(func.count()).select_from(Cost))).scalar() == 4
        assert (await load_scenario(session)).lifetime == 260


async def test_load_from_empty_database_fails(sessions):
    async with sessions() as session:
        with pytest.raises(ScenarioError):
            await load_scenario(session)


async def test_connection_pragmas(sessions):
    async with sessions() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
