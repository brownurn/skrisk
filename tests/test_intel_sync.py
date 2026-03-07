from __future__ import annotations

from pathlib import Path

import pytest

from skrisk.config import Settings
from skrisk.services.intel_sync import AbuseChSyncService
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_sync_abusech_archives_raw_feed_and_persists_indicators(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}",
        archive_root=tmp_path / "archive",
    )
    session_factory = create_sqlite_session_factory(settings.database_url)
    await init_db(session_factory)

    summary = await AbuseChSyncService(session_factory=session_factory, settings=settings).sync_all(
        urlhaus_bytes=(FIXTURES / "urlhaus_full.json.zip").read_bytes(),
        threatfox_bytes=(FIXTURES / "threatfox_full.csv.zip").read_bytes(),
    )

    repository = SkillRepository(session_factory)
    detail = await repository.get_indicator_detail("domain", "bad.example")
    feed_runs = await repository.list_intel_feed_runs(limit=2)

    assert summary["feed_runs"] == 2
    assert summary["indicators_upserted"] >= 4
    assert summary["observations_recorded"] >= 4
    assert detail is not None
    assert len(detail["observations"]) == 2
    assert len(feed_runs) == 2
    urlhaus_run = next(run for run in feed_runs if run["feed_name"] == "urlhaus")
    threatfox_run = next(run for run in feed_runs if run["feed_name"] == "threatfox")
    assert {artifact["artifact_type"] for artifact in urlhaus_run["artifacts"]} == {
        "raw-archive",
        "manifest",
    }
    assert {artifact["artifact_type"] for artifact in threatfox_run["artifacts"]} == {
        "raw-archive",
        "manifest",
    }
    assert any(
        artifact["relative_path"].endswith("full.json.zip")
        for artifact in urlhaus_run["artifacts"]
    )
    assert any(
        artifact["relative_path"].endswith("full.csv.zip")
        for artifact in threatfox_run["artifacts"]
    )
    assert all(
        artifact["relative_path"].startswith("intel/abusech/")
        for run in feed_runs
        for artifact in run["artifacts"]
    )
    assert any((settings.archive_root / "intel" / "abusech" / "urlhaus").rglob("manifest.json"))
    assert any((settings.archive_root / "intel" / "abusech" / "threatfox").rglob("manifest.json"))
