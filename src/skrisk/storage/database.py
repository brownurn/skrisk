"""Async SQLAlchemy helpers for SK Risk."""

from __future__ import annotations

import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from skrisk.storage.models import Base

_LEGACY_SKILLS_COLUMN_MIGRATIONS = {
    "current_weekly_installs": "INTEGER",
    "current_weekly_installs_observed_at": "DATETIME",
    "current_total_installs": "INTEGER",
    "current_total_installs_observed_at": "DATETIME",
    "current_registry_rank": "INTEGER",
    "current_registry_sync_run_id": "INTEGER",
}

_LEGACY_SKILL_SOURCE_ENTRY_COLUMN_MIGRATIONS = {
    "current_registry_sync_run_id": "INTEGER",
}


def create_sqlite_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory and retain its engine for setup."""
    engine = create_async_engine(database_url, future=True, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    setattr(session_factory, "engine", engine)
    setattr(session_factory, "_initialized", False)
    setattr(session_factory, "_init_lock", asyncio.Lock())
    return session_factory


async def init_db(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create all configured tables."""
    engine: AsyncEngine = getattr(session_factory, "engine")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_sqlite_additive_migrations)
    setattr(session_factory, "_initialized", True)


async def ensure_initialized(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create the schema on first use if it has not been initialized yet."""
    if getattr(session_factory, "_initialized", False):
        return

    lock: asyncio.Lock = getattr(session_factory, "_init_lock")
    async with lock:
        if getattr(session_factory, "_initialized", False):
            return
        await init_db(session_factory)


def _run_sqlite_additive_migrations(connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    inspector = inspect(connection)
    if "skills" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("skills")
    }
    for column_name, column_type in _LEGACY_SKILLS_COLUMN_MIGRATIONS.items():
        if column_name in existing_columns:
            continue
        connection.execute(text(f"ALTER TABLE skills ADD COLUMN {column_name} {column_type}"))

    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_skill_registry_observations_skill_observed "
            "ON skill_registry_observations (skill_id, observed_at DESC, id DESC)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_skill_registry_observations_skill_kind_observed "
            "ON skill_registry_observations (skill_id, observation_kind, observed_at DESC, id DESC)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_skill_snapshots_skill_latest "
            "ON skill_snapshots (skill_id, id DESC)"
        )
    )
    if "skill_source_entries" in inspector.get_table_names():
        skill_source_entry_columns = {
            column["name"]
            for column in inspector.get_columns("skill_source_entries")
        }
        for column_name, column_type in _LEGACY_SKILL_SOURCE_ENTRY_COLUMN_MIGRATIONS.items():
            if column_name in skill_source_entry_columns:
                continue
            connection.execute(
                text(
                    f"ALTER TABLE skill_source_entries ADD COLUMN {column_name} {column_type}"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_skill_source_entries_skill_source "
                "ON skill_source_entries (skill_id, registry_source_id, id DESC)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_skill_source_entries_skill_last_seen "
                "ON skill_source_entries (skill_id, last_seen_at DESC, id DESC)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_skill_source_entries_skill_current_run "
                "ON skill_source_entries (skill_id, current_registry_sync_run_id, id DESC)"
            )
        )
