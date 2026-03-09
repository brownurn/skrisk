from __future__ import annotations

from datetime import UTC, datetime

import pytest

from skrisk.analysis.analyzer import SkillAnalyzer
from skrisk.collectors.skills_sh import SkillSitemapEntry
from skrisk.config import Settings
from skrisk.services.skillsmp_discovery import SkillsMpDiscoveryService
from skrisk.services.sync import RegistrySyncService
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


@pytest.mark.asyncio
async def test_skillsmp_discovery_service_normalizes_skill_pages_and_archives_html(
    tmp_path,
) -> None:
    settings = Settings(
        archive_root=tmp_path / "archive",
        skillsmp_base_url="https://skillsmp.com",
    )
    responses = {
        "https://skillsmp.com/categories/security": """
            <html>
              <body>
                <a href="/fr/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md">
                  prose
                </a>
              </body>
            </html>
        """,
        "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md": """
            <html>
              <head><title>prose</title></head>
              <body>
                <a href="https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose">
                  GitHub
                </a>
              </body>
            </html>
        """,
    }

    async def fake_fetch(url: str) -> str:
        return responses[url]

    service = SkillsMpDiscoveryService(settings=settings, fetch_html=fake_fetch)
    result = await service.discover_from_urls(
        ["https://skillsmp.com/categories/security"],
        fetched_at=datetime(2026, 3, 8, 15, 30, tzinfo=UTC),
    )

    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.source == "skillsmp"
    assert entry.url == "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md"
    assert entry.repo_url == "https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose"
    assert entry.publisher == "openclaw"
    assert entry.repo == "openclaw"
    assert entry.skill_slug == "prose"

    manifests = sorted((settings.archive_root / "registries" / "skillsmp").rglob("manifest.json"))
    assert len(manifests) == 2
    assert '"provider": "skillsmp"' in manifests[0].read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_skillsmp_discovery_service_crawls_generic_listing_pages(
    tmp_path,
) -> None:
    settings = Settings(
        archive_root=tmp_path / "archive",
        skillsmp_base_url="https://skillsmp.com",
    )
    responses = {
        "https://skillsmp.com": """
            <html>
              <body>
                <a href="/categories/security">Security</a>
                <a href="/timeline">Timeline</a>
                <a href="https://www.reddit.com/user/ignored-link">External</a>
              </body>
            </html>
        """,
        "https://skillsmp.com/categories/security": """
            <html>
              <body>
                <a href="/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md">Prose</a>
              </body>
            </html>
        """,
        "https://skillsmp.com/timeline": """
            <html>
              <body>
                <a href="/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md">Prose</a>
              </body>
            </html>
        """,
        "https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md": """
            <html>
              <body>
                <a href="https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose">
                  GitHub
                </a>
              </body>
            </html>
        """,
    }

    async def fake_fetch(url: str) -> str:
        return responses[url]

    service = SkillsMpDiscoveryService(settings=settings, fetch_html=fake_fetch)
    result = await service.discover_from_urls(
        ["https://skillsmp.com/"],
        fetched_at=datetime(2026, 3, 9, 8, 0, tzinfo=UTC),
    )

    assert len(result.entries) == 1
    assert result.entries[0].url.endswith("/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md")


@pytest.mark.asyncio
async def test_skillsmp_discovery_entries_merge_with_api_enrichment_without_duplicate_skills(
    tmp_path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'skillsmp-discovery.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    service = RegistrySyncService(
        session_factory=session_factory,
        analyzer=SkillAnalyzer(),
    )
    discovered_entry = SkillSitemapEntry(
        publisher="openclaw",
        repo="openclaw",
        skill_slug="prose",
        url="https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
        source="skillsmp",
        repo_url="https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose",
    )
    enriched_entry = SkillSitemapEntry(
        publisher="openclaw",
        repo="openclaw",
        skill_slug="prose",
        url="https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
        source="skillsmp",
        source_native_id="openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
        repo_url="https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose",
        author="openclaw",
        description="Open prose skill",
        stars=42,
        updated_at="1772794212",
    )

    await service.seed_registry_snapshot(
        sitemap_entries=[discovered_entry],
        audit_rows=[],
        observed_at=datetime(2026, 3, 8, 15, 30, tzinfo=UTC),
    )
    await service.seed_registry_snapshot(
        sitemap_entries=[enriched_entry],
        audit_rows=[],
        observed_at=datetime(2026, 3, 8, 16, 30, tzinfo=UTC),
    )

    repository = SkillRepository(session_factory)
    detail = await repository.get_skill_detail(
        publisher="openclaw",
        repo="openclaw",
        skill_slug="prose",
    )

    assert detail is not None
    assert detail["source_count"] == 1
    assert detail["source_entries"][0]["source_native_id"] == enriched_entry.source_native_id
    assert detail["source_entries"][0]["raw_payload"]["author"] == "openclaw"
