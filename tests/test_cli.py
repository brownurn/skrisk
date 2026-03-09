from __future__ import annotations

from datetime import UTC, datetime

from click.testing import CliRunner

from skrisk.cli import cli
from skrisk.collectors.skills_sh import SkillSitemapEntry
from skrisk.collectors.skillsmp import SkillsMpSearchPage
from skrisk.services.sync import RegistrySnapshot


def test_cli_help_lists_operational_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "enrich-vt" in result.output
    assert "enrich-infra" in result.output
    assert "init-db" in result.output
    assert "scan-due" in result.output
    assert "seed-registry" in result.output
    assert "sync-intel" in result.output
    assert "sync-registry" in result.output
    assert "serve" in result.output


def test_init_dirs_creates_expected_paths(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    mirror_root = tmp_path / "mirrors"
    archive_root = tmp_path / "archive"
    monkeypatch.setenv("SKRISK_MIRROR_ROOT", str(mirror_root))
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(archive_root))

    result = runner.invoke(cli, ["init-dirs"])

    assert result.exit_code == 0
    assert mirror_root.exists()
    assert archive_root.exists()


def test_sync_intel_cli_runs_abusech_sync(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.setenv("ABUSECH_AUTH_KEY", "test-key")

    async def fake_sync_all(self, *, urlhaus_bytes=None, threatfox_bytes=None):
        assert urlhaus_bytes is None
        assert threatfox_bytes is None
        return {
            "feed_runs": 2,
            "indicators_upserted": 4,
            "observations_recorded": 4,
        }

    monkeypatch.setattr("skrisk.services.intel_sync.AbuseChSyncService.sync_all", fake_sync_all)

    result = runner.invoke(cli, ["sync-intel", "--provider", "abusech"])

    assert result.exit_code == 0
    assert "2 feed runs" in result.output


def test_enrich_vt_cli_runs_triage_service_with_limit(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.setenv("VT_APIKEY", "test-key")

    async def fake_run_once(self, *, limit=None):
        assert limit == 25
        return {
            "lookups_completed": 1,
            "lookups_failed": 0,
            "lookups_skipped_budget": 2,
        }

    monkeypatch.setattr("skrisk.services.vt_triage.VTTriageService.run_once", fake_run_once)

    result = runner.invoke(cli, ["enrich-vt", "--limit", "25"])

    assert result.exit_code == 0
    assert "1 VT lookups completed" in result.output


def test_enrich_vt_cli_reports_missing_api_key_cleanly(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.delenv("VT_APIKEY", raising=False)

    result = runner.invoke(cli, ["enrich-vt", "--limit", "1"])

    assert result.exit_code != 0
    assert "VT_APIKEY is required to run VT triage" in result.output
    assert "Traceback" not in result.output


def test_enrich_vt_cli_rejects_non_positive_limits() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["enrich-vt", "--limit", "0"])

    assert result.exit_code != 0
    assert "0" in result.output


def test_enrich_infra_cli_runs_service_with_limit(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(tmp_path / "archive"))

    async def fake_run_once(self, *, limit=None, requested_at=None):
        assert limit == 25
        assert requested_at is None
        return {
            "candidates_processed": 12,
            "whois_completed": 7,
            "dns_completed": 7,
            "ip_completed": 3,
            "ip_provider_unavailable": 0,
            "failed": 0,
        }

    monkeypatch.setattr(
        "skrisk.services.infrastructure_enrichment.InfrastructureEnrichmentService.run_once",
        fake_run_once,
    )

    result = runner.invoke(cli, ["enrich-infra", "--limit", "25"])

    assert result.exit_code == 0
    assert "12 infrastructure candidates processed" in result.output


def test_seed_registry_cli_uses_seed_snapshot_path(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")

    async def fake_fetch_snapshot(self):
        return RegistrySnapshot(
            sitemap_entries=[
                SkillSitemapEntry(
                    publisher="tul-sh",
                    repo="skills",
                    skill_slug="agent-tools",
                    url="https://skills.sh/tul-sh/skills/agent-tools",
                    weekly_installs=321,
                )
            ],
            audit_rows=[],
            total_skills=500,
            pages_fetched=4,
        )

    async def fake_seed_registry_snapshot(
        self,
        *,
        sitemap_entries,
        audit_rows,
        total_skills_reported=None,
        pages_fetched=None,
        observed_at=None,
    ):
        assert len(sitemap_entries) == 1
        assert sitemap_entries[0].weekly_installs == 321
        assert audit_rows == []
        assert total_skills_reported == 500
        assert pages_fetched == 4
        assert observed_at is None
        return {
            "repos_seeded": 1,
            "skills_seeded": 1,
        }

    monkeypatch.setattr("skrisk.services.sync.SkillsShClient.fetch_snapshot", fake_fetch_snapshot)
    monkeypatch.setattr(
        "skrisk.services.sync.RegistrySyncService.seed_registry_snapshot",
        fake_seed_registry_snapshot,
    )

    result = runner.invoke(cli, ["seed-registry"])

    assert result.exit_code == 0
    assert "Seeded 1 skills across 1 repos from 500 reported rows" in result.output


def test_sync_registry_cli_passes_snapshot_metadata_to_ingest_service(
    tmp_path,
    monkeypatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_MIRROR_ROOT", str(tmp_path / "mirrors"))

    async def fake_fetch_snapshot(self):
        return RegistrySnapshot(
            sitemap_entries=[
                SkillSitemapEntry(
                    publisher="tul-sh",
                    repo="skills",
                    skill_slug="agent-tools",
                    url="https://skills.sh/tul-sh/skills/agent-tools",
                    weekly_installs=321,
                )
            ],
            audit_rows=[],
            total_skills=500,
            pages_fetched=4,
        )

    async def fake_ingest_registry_snapshot(
        self,
        *,
        sitemap_entries,
        audit_rows,
        skill_loader,
        record_directory_fetch=True,
        total_skills_reported=None,
        pages_fetched=None,
        observed_at=None,
        registry_observation_context_by_skill=None,
    ):
        assert len(sitemap_entries) == 1
        assert sitemap_entries[0].weekly_installs == 321
        assert audit_rows == []
        assert callable(skill_loader)
        assert record_directory_fetch is True
        assert total_skills_reported == 500
        assert pages_fetched == 4
        assert observed_at is None
        assert registry_observation_context_by_skill is None
        return {
            "repos_seen": 1,
            "skills_seen": 1,
            "skills_failed": 0,
        }

    monkeypatch.setattr("skrisk.services.sync.SkillsShClient.fetch_snapshot", fake_fetch_snapshot)
    monkeypatch.setattr(
        "skrisk.services.sync.RegistrySyncService.ingest_registry_snapshot",
        fake_ingest_registry_snapshot,
    )

    result = runner.invoke(cli, ["sync-registry"])

    assert result.exit_code == 0
    assert (
        "Discovered 1 unique skills from 500 reported rows; synchronized 1 skills across 1 repos"
        in result.output
    )


def test_seed_registry_cli_supports_skillsmp_search_source(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKILLSMP_API_KEY", "test-key")

    async def fake_fetch_search_page(self, query, *, page=1, page_size=100, client=None):
        assert query == "security"
        assert page == 3
        assert page_size == 100
        return SkillsMpSearchPage(
            query=query,
            page=page,
            page_size=20,
            total=21,
            total_pages=2,
            has_next=False,
            has_prev=True,
            total_is_exact=False,
            entries=[
                SkillSitemapEntry(
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
            ],
        )

    async def fake_seed_registry_snapshot(
        self,
        *,
        sitemap_entries,
        audit_rows,
        total_skills_reported=None,
        pages_fetched=None,
        observed_at=None,
    ):
        assert len(sitemap_entries) == 1
        assert sitemap_entries[0].source == "skillsmp"
        assert sitemap_entries[0].repo_url == "https://github.com/openclaw/openclaw/tree/main/extensions/open-prose/skills/prose"
        assert audit_rows == []
        assert total_skills_reported == 21
        assert pages_fetched == 1
        assert observed_at is None
        return {
            "repos_seeded": 1,
            "skills_seeded": 1,
        }

    monkeypatch.setattr(
        "skrisk.collectors.skillsmp.SkillsMpClient.fetch_search_page",
        fake_fetch_search_page,
    )
    monkeypatch.setattr(
        "skrisk.services.sync.RegistrySyncService.seed_registry_snapshot",
        fake_seed_registry_snapshot,
    )

    result = runner.invoke(
        cli,
        [
            "seed-registry",
            "--source",
            "skillsmp",
            "--query",
            "security",
            "--page",
            "3",
            "--page-size",
            "100",
        ],
    )

    assert result.exit_code == 0
    assert "Seeded 1 skills across 1 repos from 21 reported rows" in result.output


def test_sync_registry_cli_requires_query_for_skillsmp_source(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKILLSMP_API_KEY", "test-key")

    result = runner.invoke(cli, ["sync-registry", "--source", "skillsmp"])

    assert result.exit_code != 0
    assert "requires --query" in result.output


def test_sync_registry_cli_passes_skillsmp_page_size(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKILLSMP_API_KEY", "test-key")
    monkeypatch.setenv("SKRISK_MIRROR_ROOT", str(tmp_path / "mirrors"))

    async def fake_fetch_search_page(self, query, *, page=1, page_size=100, client=None):
        assert query == "security"
        assert page == 2
        assert page_size == 100
        return SkillsMpSearchPage(
            query=query,
            page=page,
            page_size=page_size,
            total=1,
            total_pages=1,
            has_next=False,
            has_prev=False,
            total_is_exact=False,
            entries=[
                SkillSitemapEntry(
                    publisher="openclaw",
                    repo="openclaw",
                    skill_slug="prose",
                    url="https://skillsmp.com/skills/openclaw-prose",
                    source="skillsmp",
                )
            ],
        )

    async def fake_ingest_registry_snapshot(
        self,
        *,
        sitemap_entries,
        audit_rows,
        skill_loader,
        record_directory_fetch=True,
        total_skills_reported=None,
        pages_fetched=None,
        observed_at=None,
        registry_observation_context_by_skill=None,
    ):
        assert len(sitemap_entries) == 1
        return {
            "repos_seen": 1,
            "skills_seen": 1,
            "skills_failed": 0,
        }

    monkeypatch.setattr(
        "skrisk.collectors.skillsmp.SkillsMpClient.fetch_search_page",
        fake_fetch_search_page,
    )
    monkeypatch.setattr(
        "skrisk.services.sync.RegistrySyncService.ingest_registry_snapshot",
        fake_ingest_registry_snapshot,
    )

    result = runner.invoke(
        cli,
        [
            "sync-registry",
            "--source",
            "skillsmp",
            "--query",
            "security",
            "--page",
            "2",
            "--page-size",
            "100",
        ],
    )

    assert result.exit_code == 0


def test_scan_due_cli_uses_tracked_registry_entries(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_MIRROR_ROOT", str(tmp_path / "mirrors"))
    cached_observed_at = datetime(2026, 3, 7, 9, 15, tzinfo=UTC)

    async def fake_list_due_repos(self, *, now=None):
        return [
            {
                "id": 1,
                "publisher": "tul-sh",
                "repo": "skills",
                "registry_rank": 2,
                "source_url": "https://github.com/tul-sh/skills",
            }
        ]

    async def fake_list_registry_entries_for_repo_ids(self, repo_ids):
        assert repo_ids == [1]
        return [
            {
                "publisher": "tul-sh",
                "repo": "skills",
                "skill_slug": "agent-tools",
                "registry_url": "https://skills.sh/tul-sh/skills/agent-tools",
                "source": "skillsmp",
                "source_native_id": "example-agent-tools",
                "view": "all-time",
                "weekly_installs": 1200,
                "weekly_installs_observed_at": cached_observed_at,
                "registry_rank": 9,
                "registry_sync_run_id": 44,
            }
        ]

    async def fake_ingest_registry_snapshot(
        self,
        *,
        sitemap_entries,
        audit_rows,
        skill_loader,
        record_directory_fetch=True,
        registry_observation_context_by_skill=None,
        total_skills_reported=None,
        pages_fetched=None,
        observed_at=None,
    ):
        assert len(sitemap_entries) == 1
        assert sitemap_entries[0].skill_slug == "agent-tools"
        assert sitemap_entries[0].weekly_installs == 1200
        assert sitemap_entries[0].source == "skillsmp"
        assert sitemap_entries[0].source_native_id == "example-agent-tools"
        assert sitemap_entries[0].view == "all-time"
        assert audit_rows == []
        assert callable(skill_loader)
        assert record_directory_fetch is False
        assert total_skills_reported is None
        assert pages_fetched is None
        assert observed_at is None
        assert registry_observation_context_by_skill == {
            ("tul-sh", "skills", "agent-tools"): {
                "observed_at": cached_observed_at,
                "registry_rank": 9,
                "registry_sync_run_id": 44,
            }
        }
        return {
            "repos_seen": 1,
            "skills_seen": 1,
            "skills_failed": 0,
        }

    async def fail_fetch_snapshot(self, client=None):
        raise AssertionError("scan-due should not fetch the full registry")

    monkeypatch.setattr(
        "skrisk.storage.repository.SkillRepository.list_due_repos",
        fake_list_due_repos,
    )
    monkeypatch.setattr(
        "skrisk.storage.repository.SkillRepository.list_registry_entries_for_repo_ids",
        fake_list_registry_entries_for_repo_ids,
    )
    monkeypatch.setattr(
        "skrisk.services.sync.RegistrySyncService.ingest_registry_snapshot",
        fake_ingest_registry_snapshot,
    )
    monkeypatch.setattr("skrisk.services.sync.SkillsShClient.fetch_snapshot", fail_fetch_snapshot)

    result = runner.invoke(cli, ["scan-due", "--limit-repos", "100"])

    assert result.exit_code == 0
    assert "Scanned 1 skills across 1 repos from 1 due repos" in result.output
