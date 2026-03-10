from __future__ import annotations

from datetime import UTC, datetime
import sqlite3

import pytest

from skrisk.services.db_migrate import DatabaseMigrationService
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


@pytest.mark.asyncio
async def test_migrate_from_legacy_sqlite_skips_missing_tables_and_columns(tmp_path) -> None:
    source_path = tmp_path / "legacy.db"
    target_path = tmp_path / "target.db"

    connection = sqlite3.connect(source_path)
    connection.executescript(
        """
        CREATE TABLE skill_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publisher VARCHAR(255) NOT NULL,
            repo VARCHAR(255) NOT NULL,
            source_url VARCHAR(2000) NOT NULL,
            registry_rank INTEGER,
            last_scanned_at DATETIME,
            next_scan_at DATETIME,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE(publisher, repo)
        );
        CREATE TABLE skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id INTEGER NOT NULL,
            skill_slug VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            relative_path VARCHAR(1000) NOT NULL,
            registry_url VARCHAR(2000) NOT NULL,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE(repo_id, skill_slug)
        );
        INSERT INTO skill_repos (id, publisher, repo, source_url, registry_rank, created_at, updated_at)
        VALUES (
            1,
            'melurna',
            'skill-pack',
            'https://github.com/melurna/skill-pack',
            2,
            '2026-03-09 08:00:00+00:00',
            '2026-03-09 08:00:00+00:00'
        );
        INSERT INTO skills (id, repo_id, skill_slug, title, relative_path, registry_url, created_at, updated_at)
        VALUES (
            1,
            1,
            'seed-only',
            'Seed Only',
            'skills/seed-only',
            'https://skills.sh/melurna/skill-pack/seed-only',
            '2026-03-09 08:00:00+00:00',
            '2026-03-09 08:00:00+00:00'
        );
        """
    )
    connection.commit()
    connection.close()

    summary = await DatabaseMigrationService(
        target_database_url=f"sqlite+aiosqlite:///{target_path}",
    ).migrate_from_sqlite(
        source_sqlite_path=source_path,
        reset_target=False,
        batch_size=10,
    )

    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{target_path}")
    await init_db(session_factory)
    repository = SkillRepository(session_factory)

    skills = await repository.list_skills(limit=0)
    detail = await repository.get_skill_detail(
        publisher="melurna",
        repo="skill-pack",
        skill_slug="seed-only",
    )

    assert summary["tables_copied"] == 2
    assert summary["rows_copied"] == 2
    assert skills[0]["publisher"] == "melurna"
    assert skills[0]["skill_slug"] == "seed-only"
    assert skills[0]["current_total_installs"] is None
    assert detail is not None
    assert detail["source_entries"] == []
    assert detail["install_history"] == []


@pytest.mark.asyncio
async def test_migrate_from_sqlite_strips_null_bytes_from_text_fields(tmp_path) -> None:
    source_path = tmp_path / "source-null-byte.db"
    target_path = tmp_path / "target-null-byte.db"

    connection = sqlite3.connect(source_path)
    connection.executescript(
        """
        CREATE TABLE skill_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publisher VARCHAR(255) NOT NULL,
            repo VARCHAR(255) NOT NULL,
            source_url VARCHAR(2000) NOT NULL,
            registry_rank INTEGER,
            last_scanned_at DATETIME,
            next_scan_at DATETIME,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE(publisher, repo)
        );
        INSERT INTO skill_repos (id, publisher, repo, source_url, registry_rank)
        VALUES (
            1,
            'melurna',
            'skill-pack',
            'https://github.com/melurna/skill-pack' || char(0) || '/nul',
            2
        );
        """
    )
    connection.commit()
    connection.close()

    await DatabaseMigrationService(
        target_database_url=f"sqlite+aiosqlite:///{target_path}",
    ).migrate_from_sqlite(
        source_sqlite_path=source_path,
        reset_target=False,
        batch_size=10,
    )

    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{target_path}")
    await init_db(session_factory)
    repository = SkillRepository(session_factory)

    repos = await repository.list_due_repos()

    assert repos[0]["source_url"] == "https://github.com/melurna/skill-pack/nul"


@pytest.mark.asyncio
async def test_migrate_from_sqlite_remaps_indicator_ids_after_null_byte_sanitization(tmp_path) -> None:
    source_path = tmp_path / "source-indicators.db"
    target_path = tmp_path / "target-indicators.db"

    connection = sqlite3.connect(source_path)
    connection.executescript(
        """
        CREATE TABLE indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator_type VARCHAR(100) NOT NULL,
            indicator_value VARCHAR(2000) NOT NULL,
            normalized_value VARCHAR(2000) NOT NULL,
            first_seen_at DATETIME,
            last_seen_at DATETIME,
            created_at DATETIME,
            updated_at DATETIME
        );
        CREATE TABLE skill_indicator_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_snapshot_id INTEGER NOT NULL,
            indicator_id INTEGER NOT NULL,
            source_path VARCHAR(1000),
            extraction_kind VARCHAR(100),
            raw_value VARCHAR(2000),
            is_new_in_snapshot BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME
        );
        INSERT INTO indicators (
            id,
            indicator_type,
            indicator_value,
            normalized_value,
            first_seen_at,
            last_seen_at,
            created_at,
            updated_at
        )
        VALUES
            (
                1,
                'url',
                'https://legit.com.evil.com`',
                'https://legit.com.evil.com`',
                '2026-03-09 08:00:00+00:00',
                '2026-03-09 08:00:00+00:00',
                '2026-03-09 08:00:00+00:00',
                '2026-03-09 08:00:00+00:00'
            ),
            (
                2,
                'url',
                'https://legit.com' || char(0) || '.evil.com`',
                'https://legit.com' || char(0) || '.evil.com`',
                '2026-03-09 09:00:00+00:00',
                '2026-03-09 09:00:00+00:00',
                '2026-03-09 09:00:00+00:00',
                '2026-03-09 09:00:00+00:00'
            );
        INSERT INTO skill_indicator_links (
            id,
            skill_snapshot_id,
            indicator_id,
            source_path,
            extraction_kind,
            raw_value,
            is_new_in_snapshot,
            created_at
        )
        VALUES
            (1, 10, 1, 'skill.md', 'inline-url', 'https://legit.com.evil.com`', 1, '2026-03-09 08:00:00+00:00'),
            (2, 10, 2, 'skill.md', 'decoded-base64', 'https://legit.com' || char(0) || '.evil.com`', 1, '2026-03-09 09:00:00+00:00');
        """
    )
    connection.commit()
    connection.close()

    await DatabaseMigrationService(
        target_database_url=f"sqlite+aiosqlite:///{target_path}",
    ).migrate_from_sqlite(
        source_sqlite_path=source_path,
        reset_target=False,
        batch_size=10,
    )

    target = sqlite3.connect(target_path)
    indicators = target.execute(
        "SELECT id, indicator_type, normalized_value FROM indicators ORDER BY id"
    ).fetchall()
    links = target.execute(
        "SELECT id, indicator_id, raw_value FROM skill_indicator_links ORDER BY id"
    ).fetchall()
    target.close()

    assert indicators == [
        (1, "url", "https://legit.com.evil.com`"),
    ]
    assert links == [
        (1, 1, "https://legit.com.evil.com`"),
        (2, 1, "https://legit.com.evil.com`"),
    ]


@pytest.mark.asyncio
async def test_migrate_from_sqlite_truncates_overlong_varchar_values(tmp_path) -> None:
    source_path = tmp_path / "source-long-text.db"
    target_path = tmp_path / "target-long-text.db"
    oversized_url = "https://example.com/" + ("a" * 2105)

    connection = sqlite3.connect(source_path)
    connection.executescript(
        """
        CREATE TABLE skill_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publisher VARCHAR(255) NOT NULL,
            repo VARCHAR(255) NOT NULL,
            source_url VARCHAR(2000) NOT NULL,
            registry_rank INTEGER,
            last_scanned_at DATETIME,
            next_scan_at DATETIME,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE(publisher, repo)
        );
        """
    )
    connection.execute(
        """
        INSERT INTO skill_repos (
            id, publisher, repo, source_url, registry_rank, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "melurna",
            "skill-pack",
            oversized_url,
            2,
            "2026-03-09 08:00:00+00:00",
            "2026-03-09 08:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()

    await DatabaseMigrationService(
        target_database_url=f"sqlite+aiosqlite:///{target_path}",
    ).migrate_from_sqlite(
        source_sqlite_path=source_path,
        reset_target=False,
        batch_size=10,
    )

    target = sqlite3.connect(target_path)
    migrated_source_url = target.execute(
        "SELECT source_url FROM skill_repos WHERE id = 1"
    ).fetchone()[0]
    target.close()

    assert len(migrated_source_url) == 2000
    assert migrated_source_url == oversized_url[:2000]
