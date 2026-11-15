"""Async engine and session factory."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ol_musky.settings import Settings


def make_engine(settings: Settings) -> AsyncEngine:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(settings.async_db_url)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
