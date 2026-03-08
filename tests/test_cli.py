from __future__ import annotations

from click.testing import CliRunner

from skrisk.cli import cli


def test_cli_help_lists_operational_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "enrich-vt" in result.output
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


def test_scan_due_cli_uses_tracked_registry_entries(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_MIRROR_ROOT", str(tmp_path / "mirrors"))

    async def fake_list_due_repos(self, *, now=None):
        return [
            {
                "id": 10,
                "publisher": "tul-sh",
                "repo": "skills",
                "source_url": "https://github.com/tul-sh/skills",
                "registry_rank": 1,
            }
        ]

    async def fake_list_registry_entries_for_repo_ids(self, repo_ids):
        assert repo_ids == [10]
        return [
            {
                "publisher": "tul-sh",
                "repo": "skills",
                "skill_slug": "agent-tools",
                "registry_url": "https://skills.sh/tul-sh/skills/agent-tools",
            }
        ]

    async def fake_ingest_registry_snapshot(self, *, sitemap_entries, audit_rows, skill_loader):
        assert len(sitemap_entries) == 1
        assert sitemap_entries[0].skill_slug == "agent-tools"
        assert audit_rows == []
        return {"skills_seen": 1, "repos_seen": 1, "skills_failed": 0}

    async def fail_fetch_snapshot(self, client=None):
        raise AssertionError("scan-due should not fetch the full registry")

    monkeypatch.setattr("skrisk.storage.repository.SkillRepository.list_due_repos", fake_list_due_repos)
    monkeypatch.setattr(
        "skrisk.storage.repository.SkillRepository.list_registry_entries_for_repo_ids",
        fake_list_registry_entries_for_repo_ids,
    )
    monkeypatch.setattr(
        "skrisk.services.sync.RegistrySyncService.ingest_registry_snapshot",
        fake_ingest_registry_snapshot,
    )
    monkeypatch.setattr("skrisk.services.sync.SkillsShClient.fetch_snapshot", fail_fetch_snapshot)

    result = runner.invoke(cli, ["scan-due", "--limit-repos", "1"])

    assert result.exit_code == 0
    assert "Scanned 1 skills across 1 repos" in result.output
