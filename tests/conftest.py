from pathlib import Path

import pytest

from ol_musky.db import migrate
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.scenario import read_scenario_file
from ol_musky.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIO_FILE = REPO_ROOT / "config" / "mcp.yaml"


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Settings for an empty, migrated database in a temporary directory."""
    settings = Settings(db_path=tmp_path / "test.sqlite3", scenario_file=SCENARIO_FILE)
    migrate.upgrade(settings)
    return settings


@pytest.fixture(scope="session")
def scenario():
    return read_scenario_file(SCENARIO_FILE)


@pytest.fixture
async def sessions(settings):
    engine = make_engine(settings)
    yield make_session_factory(engine)
    await engine.dispose()
