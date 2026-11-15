from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ol_musky.db import migrate
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.engine.grid import adjacent_sectors
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


class FakeClock:
    """A clock that the test moves. One MCP week of the repository scenario is 200 ms."""

    def __init__(self, ms_per_week: int = 200) -> None:
        self.now = datetime(2018, 3, 9, tzinfo=UTC)
        self.ms_per_week = ms_per_week

    def __call__(self) -> datetime:
        return self.now

    def weeks(self, count: int) -> None:
        self.now += timedelta(milliseconds=self.ms_per_week * count)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def best_sector(scenario) -> int:
    """The sector whose adjacent sectors hold the most ore."""
    return max(
        range(len(scenario.belt)),
        key=lambda sid: sum(
            scenario.belt[adj].deposit_amt
            for adj in adjacent_sectors(sid, scenario.rows, scenario.cols)
        ),
    )
