from __future__ import annotations

from pathlib import Path

import pytest

from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


@pytest.mark.asyncio
async def test_record_intel_feed_run_and_indicator_observation(tmp_path: Path) -> None:
    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    await init_db(session_factory)
    repository = SkillRepository(session_factory)

    feed_run_id = await repository.record_intel_feed_run(
        provider="abusech",
        feed_name="urlhaus",
        source_url="https://urlhaus-api.abuse.ch/files/exports/full.json.zip",
        auth_mode="query-key",
        parser_version="v1",
        archive_sha256="abc123",
        archive_size_bytes=10,
    )
    indicator_id = await repository.upsert_indicator(
        indicator_type="domain",
        indicator_value="bad.example",
    )
    await repository.record_indicator_observation(
        indicator_id=indicator_id,
        feed_run_id=feed_run_id,
        source_provider="abusech",
        source_feed="urlhaus",
        classification="malicious",
        confidence_label="high",
        summary="Known payload host",
    )

    detail = await repository.get_indicator_detail("domain", "bad.example")
    assert detail is not None
    assert detail["indicator"]["indicator_value"] == "bad.example"
    assert detail["observations"][0]["classification"] == "malicious"
