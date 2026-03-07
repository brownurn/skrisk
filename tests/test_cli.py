from __future__ import annotations

from click.testing import CliRunner

from skrisk.cli import cli


def test_cli_help_lists_operational_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "init-db" in result.output
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
