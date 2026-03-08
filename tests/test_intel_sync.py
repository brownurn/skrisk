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


@pytest.mark.asyncio
async def test_sync_abusech_falls_back_to_recent_api_when_exports_are_malformed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}",
        archive_root=tmp_path / "archive",
        abusech_auth_key="test-key",
    )
    session_factory = create_sqlite_session_factory(settings.database_url)
    await init_db(session_factory)

    async def fake_download_urlhaus_recent(*, auth_key: str) -> dict:
        assert auth_key == "test-key"
        return {
            "query_status": "ok",
            "urls": [
                {
                    "id": 3791294,
                    "url": "http://110.37.118.241:46513/i",
                    "url_status": "online",
                    "host": "110.37.118.241",
                    "threat": "malware_download",
                }
            ],
        }

    async def fake_download_threatfox_recent(*, auth_key: str) -> dict:
        assert auth_key == "test-key"
        return {
            "query_status": "ok",
            "data": [
                {
                    "id": "1760828",
                    "ioc": "thorntrue.draniercismn.in.net",
                    "threat_type": "payload_delivery",
                    "ioc_type": "domain",
                    "confidence_level": "100",
                    "malware": "js.clearfake",
                    "malware_printable": "ClearFake",
                    "reporter": "unit-test",
                }
            ],
        }

    monkeypatch.setattr(
        "skrisk.services.intel_sync.download_urlhaus_recent_payload",
        fake_download_urlhaus_recent,
    )
    monkeypatch.setattr(
        "skrisk.services.intel_sync.download_threatfox_recent_payload",
        fake_download_threatfox_recent,
    )

    summary = await AbuseChSyncService(session_factory=session_factory, settings=settings).sync_all(
        urlhaus_bytes=b"not-a-valid-zip",
        threatfox_bytes=b"not-a-valid-zip",
    )

    repository = SkillRepository(session_factory)
    feed_runs = await repository.list_intel_feed_runs(limit=4)
    urlhaus_recent = next(run for run in feed_runs if run["feed_name"] == "urlhaus_recent")
    threatfox_recent = next(run for run in feed_runs if run["feed_name"] == "threatfox_recent")
    detail = await repository.get_indicator_detail("domain", "thorntrue.draniercismn.in.net")

    assert summary["feed_runs"] == 2
    assert summary["observations_recorded"] >= 2
    assert any(artifact["relative_path"].endswith("recent.json") for artifact in urlhaus_recent["artifacts"])
    assert any(artifact["relative_path"].endswith("recent.json") for artifact in threatfox_recent["artifacts"])
    assert detail is not None
    assert detail["observations"][0]["source_feed"] == "threatfox_recent"
