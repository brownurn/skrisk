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
