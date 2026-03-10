"""Async SQLAlchemy helpers for SK Risk."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit

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
    "latest_snapshot_id": "INTEGER",
    "latest_severity": "VARCHAR(32)",
    "latest_risk_score": "INTEGER",
    "latest_confidence": "VARCHAR(32)",
    "latest_indicator_match_count": "INTEGER",
}

_LEGACY_SKILL_SOURCE_ENTRY_COLUMN_MIGRATIONS = {
    "current_registry_sync_run_id": "INTEGER",
    "current_registry_sync_observed_at": "DATETIME",
}

_COMMON_INDEX_STATEMENTS = (
    (
        "skill_registry_observations",
        {"skill_id", "observed_at", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skill_registry_observations_skill_observed "
        "ON skill_registry_observations (skill_id, observed_at DESC, id DESC)",
    ),
    (
        "skill_registry_observations",
        {"skill_id", "observation_kind", "observed_at", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skill_registry_observations_skill_kind_observed "
        "ON skill_registry_observations (skill_id, observation_kind, observed_at DESC, id DESC)",
    ),
    (
        "skill_snapshots",
        {"skill_id", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skill_snapshots_skill_latest "
        "ON skill_snapshots (skill_id, id DESC)",
    ),
    (
        "skills",
        {"latest_snapshot_id"},
        "CREATE INDEX IF NOT EXISTS ix_skills_latest_snapshot_id "
        "ON skills (latest_snapshot_id)",
    ),
    (
        "skills",
        {"latest_severity", "latest_risk_score", "current_total_installs", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skills_latest_summary "
        "ON skills (latest_severity, latest_risk_score DESC, current_total_installs DESC, id DESC)",
    ),
    (
        "skills",
        {"repo_id", "latest_severity", "latest_risk_score", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skills_repo_latest_summary "
        "ON skills (repo_id, latest_severity, latest_risk_score DESC, id DESC)",
    ),
    (
        "skill_source_entries",
        {"skill_id", "registry_source_id", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skill_source_entries_skill_source "
        "ON skill_source_entries (skill_id, registry_source_id, id DESC)",
    ),
    (
        "skill_source_entries",
        {"skill_id", "last_seen_at", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skill_source_entries_skill_last_seen "
        "ON skill_source_entries (skill_id, last_seen_at DESC, id DESC)",
    ),
    (
        "skill_source_entries",
        {"skill_id", "current_registry_sync_run_id", "id"},
        "CREATE INDEX IF NOT EXISTS ix_skill_source_entries_skill_current_run "
        "ON skill_source_entries (skill_id, current_registry_sync_run_id, id DESC)",
    ),
)


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory and retain its engine for setup."""
    normalized_url = _normalize_database_url(database_url)
    engine_kwargs = {"future": True, "pool_pre_ping": True}
    if normalized_url.startswith("sqlite+aiosqlite:"):
        engine_kwargs["poolclass"] = NullPool
    engine = create_async_engine(normalized_url, **engine_kwargs)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    setattr(session_factory, "engine", engine)
    setattr(session_factory, "_initialized", False)
    setattr(session_factory, "_init_lock", asyncio.Lock())
    return session_factory


def create_sqlite_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Backward-compatible alias for older tests and callers."""
    return create_session_factory(database_url)


async def init_db(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create all configured tables."""
    engine: AsyncEngine = getattr(session_factory, "engine")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_additive_migrations)
        await conn.run_sync(_ensure_common_indexes)
        await conn.run_sync(_backfill_latest_skill_summary)
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


def _run_additive_migrations(connection) -> None:
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


def _backfill_latest_skill_summary(connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "skills" not in table_names or "skill_snapshots" not in table_names:
        return

    skill_columns = {column["name"] for column in inspector.get_columns("skills")}
    required_columns = {
        "latest_snapshot_id",
        "latest_severity",
        "latest_risk_score",
        "latest_confidence",
        "latest_indicator_match_count",
    }
    if not required_columns.issubset(skill_columns):
        return
    if not _latest_summary_backfill_required(connection):
        return

    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (skill_id)
                        id,
                        skill_id,
                        COALESCE(risk_report ->> 'severity', 'none') AS severity,
                        COALESCE((risk_report ->> 'score')::integer, 0) AS risk_score,
                        risk_report ->> 'confidence' AS confidence,
                        CASE
                            WHEN json_typeof(risk_report -> 'indicator_matches') = 'array'
                            THEN json_array_length(risk_report -> 'indicator_matches')
                            ELSE 0
                        END AS indicator_match_count
                    FROM skill_snapshots
                    ORDER BY skill_id, id DESC
                )
                UPDATE skills AS s
                SET latest_snapshot_id = latest.id,
                    latest_severity = latest.severity,
                    latest_risk_score = latest.risk_score,
                    latest_confidence = latest.confidence,
                    latest_indicator_match_count = latest.indicator_match_count
                FROM latest
                WHERE s.id = latest.skill_id
                  AND (
                    s.latest_snapshot_id IS DISTINCT FROM latest.id
                    OR s.latest_severity IS DISTINCT FROM latest.severity
                    OR s.latest_risk_score IS DISTINCT FROM latest.risk_score
                    OR s.latest_confidence IS DISTINCT FROM latest.confidence
                    OR s.latest_indicator_match_count IS DISTINCT FROM latest.indicator_match_count
                  )
                """
            )
        )
        return

    if connection.dialect.name == "sqlite":
        connection.execute(
            text(
                """
                UPDATE skills
                SET latest_snapshot_id = (
                        SELECT ss.id
                        FROM skill_snapshots AS ss
                        WHERE ss.skill_id = skills.id
                        ORDER BY ss.id DESC
                        LIMIT 1
                    ),
                    latest_severity = COALESCE((
                        SELECT json_extract(ss.risk_report, '$.severity')
                        FROM skill_snapshots AS ss
                        WHERE ss.skill_id = skills.id
                        ORDER BY ss.id DESC
                        LIMIT 1
                    ), 'none'),
                    latest_risk_score = COALESCE((
                        SELECT CAST(json_extract(ss.risk_report, '$.score') AS INTEGER)
                        FROM skill_snapshots AS ss
                        WHERE ss.skill_id = skills.id
                        ORDER BY ss.id DESC
                        LIMIT 1
                    ), 0),
                    latest_confidence = (
                        SELECT json_extract(ss.risk_report, '$.confidence')
                        FROM skill_snapshots AS ss
                        WHERE ss.skill_id = skills.id
                        ORDER BY ss.id DESC
                        LIMIT 1
                    ),
                    latest_indicator_match_count = COALESCE((
                        SELECT CASE
                            WHEN json_type(ss.risk_report, '$.indicator_matches') = 'array'
                            THEN json_array_length(json_extract(ss.risk_report, '$.indicator_matches'))
                            ELSE 0
                        END
                        FROM skill_snapshots AS ss
                        WHERE ss.skill_id = skills.id
                        ORDER BY ss.id DESC
                        LIMIT 1
                    ), 0)
                WHERE EXISTS (
                    SELECT 1
                    FROM skill_snapshots AS ss
                    WHERE ss.skill_id = skills.id
                )
                """
            )
        )


def _latest_summary_backfill_required(connection) -> bool:
    result = connection.execute(
        text(
            """
            SELECT 1
            FROM skills
            WHERE (
                latest_snapshot_id IS NULL
                OR latest_severity IS NULL
                OR latest_risk_score IS NULL
            )
              AND EXISTS (
                SELECT 1
                FROM skill_snapshots
                WHERE skill_snapshots.skill_id = skills.id
              )
            LIMIT 1
            """
        )
    ).first()
    return result is not None


def _ensure_common_indexes(connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    cached_columns: dict[str, set[str]] = {}

    for table_name, required_columns, statement in _COMMON_INDEX_STATEMENTS:
        if table_name not in table_names:
            continue
        if table_name not in cached_columns:
            cached_columns[table_name] = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
        if not required_columns.issubset(cached_columns[table_name]):
            continue
        connection.execute(text(statement))


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("sqlite+aiosqlite://"):
        return database_url
    if database_url.startswith("sqlite://"):
        return database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        parsed = urlsplit(database_url.replace("postgres://", "postgresql://", 1))
        scheme = "postgresql+asyncpg"
        return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return database_url
