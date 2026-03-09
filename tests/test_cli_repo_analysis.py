from __future__ import annotations

from click.testing import CliRunner

from skrisk.cli import cli


def test_analyze_mirrors_cli_uses_auto_worker_budget(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_MIRROR_ROOT", str(tmp_path / "mirrors"))
    monkeypatch.setattr("skrisk.cli.os.cpu_count", lambda: 10)

    async def fake_run_once(self, *, limit_repos, workers, continuous):
        assert limit_repos == 25
        assert workers == 8
        assert continuous is True
        return {
            "repos_requested": 25,
            "repos_analyzed": 22,
            "repos_missing_mirror": 2,
            "repos_failed": 1,
            "skills_analyzed": 80,
        }

    monkeypatch.setattr("skrisk.services.repo_analysis.MirroredRepoAnalysisService.run_once", fake_run_once)

    result = runner.invoke(cli, ["analyze-mirrors", "--limit-repos", "25", "--continuous"])

    assert result.exit_code == 0
    assert "Analyzed 22 repos" in result.output
    assert "80 skills" in result.output


def test_produce_analysis_spool_cli_uses_auto_worker_budget(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_MIRROR_ROOT", str(tmp_path / "mirrors"))
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.setattr("skrisk.cli.os.cpu_count", lambda: 10)

    async def fake_run_once(self, *, limit_repos, workers, continuous):
        assert limit_repos == 25
        assert workers == 8
        assert continuous is True
        return {
            "repos_requested": 25,
            "repos_spooled": 20,
            "repos_missing_mirror": 3,
            "repos_failed": 2,
            "skills_analyzed": 77,
        }

    monkeypatch.setattr("skrisk.services.analysis_spool.AnalysisSpoolProducerService.run_once", fake_run_once)

    result = runner.invoke(cli, ["produce-analysis-spool", "--limit-repos", "25", "--continuous"])

    assert result.exit_code == 0
    assert "Spooled 20 repos" in result.output
    assert "77 skills" in result.output


def test_ingest_analysis_spool_cli_runs_service(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(tmp_path / "archive"))

    async def fake_run_once(self, *, limit_artifacts, continuous):
        assert limit_artifacts == 50
        assert continuous is True
        return {
            "artifacts_seen": 50,
            "artifacts_ingested": 47,
            "artifacts_failed": 3,
            "skills_ingested": 120,
        }

    monkeypatch.setattr("skrisk.services.analysis_spool.AnalysisSpoolIngestService.run_once", fake_run_once)

    result = runner.invoke(cli, ["ingest-analysis-spool", "--limit-artifacts", "50", "--continuous"])

    assert result.exit_code == 0
    assert "Ingested 47 analysis artifacts" in result.output
    assert "120 skills" in result.output
