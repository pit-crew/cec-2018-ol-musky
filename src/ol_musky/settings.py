"""Runtime configuration. Each field reads from an OL_MUSKY_* environment variable."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OL_MUSKY_")

    db_path: Path = Path("db/ol_musky.sqlite3")
    scenario_file: Path = Path("config/mcp.yaml")
    # Scenario to activate at start. None selects the only scenario in the database.
    scenario_id: str | None = None
    # Interval between writes of the live team state to the database.
    flush_interval_ms: int = 1000
    # Seed for piracy and prospecting noise. None gives a different game each time.
    random_seed: int | None = None

    @property
    def async_db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def sync_db_url(self) -> str:
        return f"sqlite:///{self.db_path}"
