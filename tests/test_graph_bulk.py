from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
import pytest

from skrisk.cli import cli
from skrisk.config import Settings


@pytest.mark.asyncio
async def test_export_bundle_writes_expected_csvs(tmp_path, monkeypatch) -> None:
    from skrisk.services.graph_bulk import GraphBulkImportService

    bundle_dir = tmp_path / "graph-bundle"
    settings = Settings(
        database_url="postgresql://skrisk:skrisk@127.0.0.1:15432/skrisk",
        archive_root=tmp_path,
    )
    service = GraphBulkImportService(settings=settings)

    copied_queries: list[str] = []

    class FakeConnection:
        async def execute(self, query: str) -> None:
            return None

        async def copy_from_query(self, query, *args, output, **kwargs):
            copied_queries.append(query)
            output.write(b"id\nexample\n")

        async def close(self) -> None:
            return None

    async def fake_connect(dsn: str):
        assert dsn == settings.database_url
        return FakeConnection()

    monkeypatch.setattr("skrisk.services.graph_bulk.asyncpg.connect", fake_connect)

    summary = await service.export_bundle(bundle_dir=bundle_dir)

    assert summary["bundle_dir"] == bundle_dir
    assert summary["files_written"] == 16
    assert {
        path.name for path in bundle_dir.iterdir() if path.is_file()
    } == {
        "skills.csv",
        "repos.csv",
        "registries.csv",
        "indicators.csv",
        "asns.csv",
        "registrars.csv",
        "organizations.csv",
        "nameservers.csv",
        "hosted_in.csv",
        "seen_in.csv",
        "emits.csv",
        "resolves_to.csv",
        "announced_by.csv",
        "registered_with.csv",
        "registered_to.csv",
        "uses_nameserver.csv",
    }
    assert len(copied_queries) == 16


@pytest.mark.asyncio
async def test_import_bundle_runs_stop_import_start_sequence(tmp_path, monkeypatch) -> None:
    from skrisk.services.graph_bulk import GraphBulkImportService

    bundle_dir = tmp_path / "graph-bundle"
    bundle_dir.mkdir()
    for name in (
        "skills.csv",
        "repos.csv",
        "registries.csv",
        "indicators.csv",
        "asns.csv",
        "registrars.csv",
        "organizations.csv",
        "nameservers.csv",
        "hosted_in.csv",
        "seen_in.csv",
        "emits.csv",
        "resolves_to.csv",
        "announced_by.csv",
        "registered_with.csv",
        "registered_to.csv",
        "uses_nameserver.csv",
    ):
        (bundle_dir / name).write_text("id\nexample\n", encoding="utf-8")

    settings = Settings(archive_root=tmp_path)
    service = GraphBulkImportService(settings=settings)

    commands: list[list[str]] = []

    async def fake_run_command(cmd: list[str]) -> None:
        commands.append(cmd)

    async def fake_wait_for_neo4j() -> None:
        return None

    async def fake_fetch_graph_counts() -> dict[str, int]:
        return {"nodes": 10, "relationships": 20}

    monkeypatch.setattr(service, "_run_command", fake_run_command)
    monkeypatch.setattr(service, "_wait_for_neo4j", fake_wait_for_neo4j)
    monkeypatch.setattr(service, "_fetch_graph_counts", fake_fetch_graph_counts)

    await service.import_bundle(
        bundle_dir=bundle_dir,
        threads=8,
        max_off_heap_memory="8G",
    )

    assert commands[0] == ["docker", "compose", "stop", "neo4j"]
    assert commands[1][:6] == ["docker", "compose", "run", "--rm", "--no-deps", "-T"]
    assert any(str(bundle_dir) in part for part in commands[1])
    assert any("neo4j-admin" in part for part in commands[1])
    assert any("--threads=8" in part for part in commands[1])
    assert any("--max-off-heap-memory=8G" in part for part in commands[1])
    assert commands[2] == ["docker", "compose", "up", "-d", "neo4j"]


def test_rebuild_graph_bulk_cli_invokes_service(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("SKRISK_ARCHIVE_ROOT", str(tmp_path / "archive"))

    calls: list[dict[str, object]] = []

    class FakeGraphBulkImportService:
        def __init__(self, *, settings):
            self.settings = settings

        async def rebuild(
            self,
            *,
            bundle_dir: Path | None = None,
            threads: int,
            max_off_heap_memory: str,
            export_only: bool,
            import_only: bool,
        ) -> dict[str, object]:
            calls.append(
                {
                    "bundle_dir": bundle_dir,
                    "threads": threads,
                    "max_off_heap_memory": max_off_heap_memory,
                    "export_only": export_only,
                    "import_only": import_only,
                }
            )
            return {
                "bundle_dir": tmp_path / "archive" / "graph-import" / "latest",
                "files_written": 16,
            }

    monkeypatch.setattr("skrisk.cli.GraphBulkImportService", FakeGraphBulkImportService)

    result = runner.invoke(
        cli,
        [
            "rebuild-graph-bulk",
            "--threads",
            "8",
            "--max-off-heap-memory",
            "8G",
        ],
    )

    assert result.exit_code == 0
    assert "graph-import" in result.output
    assert calls == [
        {
            "bundle_dir": None,
            "threads": 8,
            "max_off_heap_memory": "8G",
            "export_only": False,
            "import_only": False,
        }
    ]
