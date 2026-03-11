from __future__ import annotations

from pathlib import Path

import pytest

from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository, _chunked_values


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


def test_chunked_values_splits_large_lists() -> None:
    chunks = _chunked_values(list(range(8)), chunk_size=3)

    assert chunks == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7],
    ]


@pytest.mark.asyncio
async def test_load_indicator_enrichments_chunks_large_lists() -> None:
    class _FakeScalarResult:
        def all(self) -> list[object]:
            return []

    class _FakeResult:
        def scalars(self) -> _FakeScalarResult:
            return _FakeScalarResult()

    class _FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, _statement) -> _FakeResult:
            self.calls += 1
            return _FakeResult()

    repository = SkillRepository(session_factory=None)  # type: ignore[arg-type]
    session = _FakeSession()

    result = await repository._load_indicator_enrichments(  # type: ignore[attr-defined]
        session,  # type: ignore[arg-type]
        indicator_ids=list(range(25001)),
    )

    assert result == {}
    assert session.calls == 3
