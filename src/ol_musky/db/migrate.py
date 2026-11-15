"""Programmatic Alembic entry point. No alembic.ini is necessary at run time."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from ol_musky.settings import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def alembic_config(settings: Settings) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", settings.sync_db_url)
    return config


def upgrade(settings: Settings, revision: str = "head") -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(settings), revision)
