from __future__ import annotations

from pathlib import Path
import subprocess

import pytest
from sqlalchemy import func, select

from skrisk.analysis.analyzer import SkillAnalyzer
from skrisk.collectors.github import discover_skills_in_checkout, mirror_repo_snapshot
from skrisk.collectors.skills_sh import AuditRow, SkillSitemapEntry
from skrisk.services.sync import RegistrySyncService
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.models import SkillRepoSnapshot, SkillSnapshot


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
        )
    ]

    async def loader(_: SkillSitemapEntry) -> tuple[str, dict[str, str]]:
        return (
            "abc123",
            {
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

    assert snapshot_count == 2


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
        ),
        SkillSitemapEntry(
            publisher="tul-sh",
            repo="skills",
            skill_slug="broken-skill",
            url="https://skills.sh/tul-sh/skills/broken-skill",
        ),
        SkillSitemapEntry(
            publisher="tul-sh",
            repo="skills",
            skill_slug="second-good-skill",
            url="https://skills.sh/tul-sh/skills/second-good-skill",
        ),
    ]

    async def loader(entry: SkillSitemapEntry) -> tuple[str, dict[str, str]]:
        if entry.skill_slug == "broken-skill":
            raise FileNotFoundError("missing skill")
        return (
            "def456",
            {
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

    assert summary["repos_seen"] == 1
    assert summary["skills_seen"] == 2
    assert summary["skills_failed"] == 1
    assert repo_snapshot_count == 1
    assert skill_snapshot_count == 2
