from __future__ import annotations

from pathlib import Path

import pytest

from skrisk.config import Settings
from skrisk.services.vt_triage import VTTriageService
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


class FakeVTClient:
    async def lookup(self, indicator_type: str, indicator_value: str) -> dict:
        return {
            "indicator_type": indicator_type,
            "indicator_value": indicator_value,
            "stats": {
                "malicious": 7,
                "suspicious": 2,
                "harmless": 1,
            },
        }


@pytest.mark.asyncio
async def test_vt_triage_respects_daily_budget_and_caches_results(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}",
        archive_root=tmp_path / "archive",
        vt_daily_budget=2,
        vt_api_key="test-key",
    )
    session_factory = create_sqlite_session_factory(settings.database_url)
    await init_db(session_factory)
    repository = SkillRepository(session_factory)

    await repository.enqueue_vt_lookup(
        indicator_type="url",
        indicator_value="https://bad.example/a.sh",
        priority=100,
        reason="critical",
    )
    await repository.enqueue_vt_lookup(
        indicator_type="domain",
        indicator_value="bad.example",
        priority=90,
        reason="abusech-hit",
    )
    await repository.enqueue_vt_lookup(
        indicator_type="url",
        indicator_value="https://other.example/b.sh",
        priority=10,
        reason="medium",
    )

    summary = await VTTriageService(
        session_factory=session_factory,
        settings=settings,
        client=FakeVTClient(),
    ).run_once()

    queue_items = await repository.list_vt_queue_items()
    bad_detail = await repository.get_indicator_detail("url", "https://bad.example/a.sh")

    assert summary["lookups_completed"] == 2
    assert summary["lookups_skipped_budget"] == 1
    assert queue_items[0]["status"] == "completed"
    assert queue_items[-1]["status"] == "queued"
    assert any(enrichment["provider"] == "virustotal" for enrichment in bad_detail["enrichments"])
    assert any((settings.archive_root / "intel" / "virustotal" / "url").rglob("*.json"))
