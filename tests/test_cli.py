from __future__ import annotations

from click.testing import CliRunner

from skrisk.cli import cli


def test_cli_help_lists_operational_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "enrich-vt" in result.output
    assert "init-db" in result.output
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
