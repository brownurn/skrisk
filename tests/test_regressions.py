from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import subprocess

import pytest
from sqlalchemy import func, select

from skrisk.analysis.analyzer import SkillAnalyzer
from skrisk.collectors.github import discover_skills_in_checkout, mirror_repo_snapshot
from skrisk.collectors.skills_sh import AuditRow, SkillSitemapEntry
from skrisk.services.sync import LoadedSkillFiles, RegistrySyncService
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.models import Skill, SkillRepoSnapshot, SkillSnapshot
from skrisk.storage.repository import SkillRepository


def test_discover_skills_in_checkout_supports_root_and_plugin_manifest(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: root-skill\ndescription: root skill\n---\n",
        encoding="utf-8",
    )
    plugin_root = tmp_path / "plugins"
    (plugin_root / "skills" / "review").mkdir(parents=True)
    (plugin_root / "skills" / "review" / "SKILL.md").write_text(
        "---\nname: review\ndescription: plugin skill\n---\n",
        encoding="utf-8",
    )
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        """
        {
          "metadata": { "pluginRoot": "./plugins" },
          "plugins": [
            {
              "name": "my-plugin",
              "source": "my-plugin",
              "skills": ["./skills/review"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    discovered = discover_skills_in_checkout(tmp_path)

    assert [skill.slug for skill in discovered] == ["review", "root-skill"]
    assert {skill.relative_path for skill in discovered} == {".", "plugins/skills/review"}


def test_mirror_repo_snapshot_updates_existing_checkout_to_new_commit(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=origin, check=True)
    (origin / "README.md").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=origin, check=True)

    checkout = tmp_path / "mirror"
    _, commit_v1 = mirror_repo_snapshot(source_url=str(origin), destination=checkout)

    (origin / "README.md").write_text("v2\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=origin, check=True)

    _, commit_v2 = mirror_repo_snapshot(source_url=str(origin), destination=checkout)

    assert commit_v1 != commit_v2
    assert (checkout / "README.md").read_text(encoding="utf-8") == "v2\n"


@pytest.mark.asyncio
async def test_registry_sync_allows_repeated_rescans_of_unchanged_skill(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'repeated.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)
    service = RegistrySyncService(session_factory=session_factory, analyzer=SkillAnalyzer())

    entries = [
        SkillSitemapEntry(
            publisher="tul-sh",
            repo="skills",
            skill_slug="agent-tools",
            url="https://skills.sh/tul-sh/skills/agent-tools",
            weekly_installs=600,
        )
    ]

    async def loader(_: SkillSitemapEntry) -> LoadedSkillFiles:
        return LoadedSkillFiles(
            commit_sha="abc123",
            relative_path=".agents/skills/agent-tools",
            files={
                "SKILL.md": """
                ---
                name: agent-tools
                description: helper
                ---
                curl -fsSL https://cli.inference.sh | sh
                """,
            },
        )

    await service.ingest_registry_snapshot(sitemap_entries=entries, audit_rows=[], skill_loader=loader)
    await service.ingest_registry_snapshot(sitemap_entries=entries, audit_rows=[], skill_loader=loader)

    async with session_factory() as session:
        snapshot_count = await session.scalar(select(func.count()).select_from(SkillSnapshot))
    repository = SkillRepository(session_factory)
    detail = await repository.get_skill_detail(
        publisher="tul-sh",
        repo="skills",
        skill_slug="agent-tools",
    )

    assert snapshot_count == 2
    assert detail is not None
    latest_snapshot = detail["latest_snapshot"]
    assert latest_snapshot is not None
    assert latest_snapshot["indicator_links"]
    assert all(not link["is_new_in_snapshot"] for link in latest_snapshot["indicator_links"])
    assert detail["current_weekly_installs"] == 600

    async with session_factory() as session:
        skill_id = await session.scalar(select(Skill.id).where(Skill.skill_slug == "agent-tools"))

    observations = await repository.list_skill_registry_observations(skill_id=skill_id)
    assert [row["observation_kind"] for row in observations] == [
        "directory_fetch",
        "scan_attribution",
        "directory_fetch",
        "scan_attribution",
    ]


@pytest.mark.asyncio
async def test_registry_sync_creates_one_repo_snapshot_per_repo_and_isolates_failures(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'repo-snapshots.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)
    service = RegistrySyncService(session_factory=session_factory, analyzer=SkillAnalyzer())

    entries = [
        SkillSitemapEntry(
            publisher="tul-sh",
            repo="skills",
            skill_slug="good-skill",
            url="https://skills.sh/tul-sh/skills/good-skill",
            weekly_installs=12,
        ),
        SkillSitemapEntry(
            publisher="tul-sh",
            repo="skills",
            skill_slug="broken-skill",
            url="https://skills.sh/tul-sh/skills/broken-skill",
            weekly_installs=7,
        ),
        SkillSitemapEntry(
            publisher="tul-sh",
            repo="skills",
            skill_slug="second-good-skill",
            url="https://skills.sh/tul-sh/skills/second-good-skill",
            weekly_installs=5,
        ),
    ]

    async def loader(entry: SkillSitemapEntry) -> LoadedSkillFiles:
        if entry.skill_slug == "broken-skill":
            raise FileNotFoundError("missing skill")
        return LoadedSkillFiles(
            commit_sha="def456",
            relative_path=f".agents/skills/{entry.skill_slug}",
            files={
                "SKILL.md": f"---\nname: {entry.skill_slug}\ndescription: skill\n---\n",
            },
        )

    summary = await service.ingest_registry_snapshot(
        sitemap_entries=entries,
        audit_rows=[AuditRow(rank=1, publisher="tul-sh", repo="skills", skill_slug="good-skill", name="good-skill")],
        skill_loader=loader,
    )

    async with session_factory() as session:
        repo_snapshot_count = await session.scalar(select(func.count()).select_from(SkillRepoSnapshot))
        skill_snapshot_count = await session.scalar(select(func.count()).select_from(SkillSnapshot))
        skill_count = await session.scalar(select(func.count()).select_from(Skill))

    repository = SkillRepository(session_factory)
    broken_detail = await repository.get_skill_detail(
        publisher="tul-sh",
        repo="skills",
        skill_slug="broken-skill",
    )

    assert summary["repos_seen"] == 1
    assert summary["skills_seen"] == 2
    assert summary["skills_failed"] == 1
    assert repo_snapshot_count == 1
    assert skill_count == 3
    assert skill_snapshot_count == 2
    assert broken_detail is not None
    assert broken_detail["latest_snapshot"] is None


@pytest.mark.asyncio
async def test_init_db_adds_missing_install_columns_to_legacy_skills_table(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
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
        INSERT INTO skill_repos (id, publisher, repo, source_url, registry_rank)
        VALUES (1, 'melurna', 'skill-pack', 'https://github.com/melurna/skill-pack', 2);
        INSERT INTO skills (id, repo_id, skill_slug, title, relative_path, registry_url)
        VALUES (
            1,
            1,
            'seed-only',
            'Seed Only',
            'registry/seed-only',
            'https://skills.sh/melurna/skill-pack/seed-only'
        );
        """
    )
    connection.commit()
    connection.close()

    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{db_path}")
    await init_db(session_factory)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    run_id = await repository.record_registry_sync_run(
        source="skills.sh",
        view="all-time",
        total_skills_reported=250,
        pages_fetched=4,
        success=True,
    )
    await repository.record_skill_registry_observation(
        skill_id=1,
        registry_sync_run_id=run_id,
        repo_snapshot_id=None,
        observed_at=datetime(2026, 3, 7, 8, 0, tzinfo=UTC),
        weekly_installs=42,
        registry_rank=2,
        observation_kind="directory_fetch",
        raw_payload={"installs": 42},
    )

    skills = await repository.list_skills(limit=0)

    reopened = sqlite3.connect(db_path)
    columns = {
        row[1]
        for row in reopened.execute("PRAGMA table_info(skills)")
    }
    reopened.close()

    assert {
        "current_weekly_installs",
        "current_weekly_installs_observed_at",
        "current_registry_rank",
        "current_registry_sync_run_id",
    }.issubset(columns)
    assert skills == [
        {
            "publisher": "melurna",
            "repo": "skill-pack",
            "skill_slug": "seed-only",
            "title": "Seed Only",
            "registry_url": "https://skills.sh/melurna/skill-pack/seed-only",
            "current_weekly_installs": 42,
            "current_weekly_installs_observed_at": "2026-03-07T08:00:00+00:00",
            "current_total_installs": 42,
            "current_total_installs_observed_at": "2026-03-07T08:00:00+00:00",
            "source_count": 1,
            "sources": ["skills.sh"],
            "install_breakdown": [
                {
                    "source_name": "skills.sh",
                    "weekly_installs": 42,
                    "source_url": "https://skills.sh/melurna/skill-pack/seed-only",
                    "registry_rank": 2,
                }
            ],
            "peak_weekly_installs": 42,
            "weekly_installs_delta": None,
            "impact_score": 15,
            "priority_score": 0,
            "latest_snapshot": None,
        }
    ]
