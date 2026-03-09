from __future__ import annotations

from datetime import UTC, datetime

import pytest

from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


@pytest.mark.asyncio
async def test_repository_tracks_multiple_source_entries_and_combined_installs(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'registry-sources.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="example",
        repo="skills",
        source_url="https://github.com/example/skills",
        registry_rank=4,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="agent-tools",
        title="agent-tools",
        relative_path="skills/agent-tools",
        registry_url="https://skills.sh/example/skills/agent-tools",
    )
    source_ids = {
        "skills.sh": await repository.upsert_registry_source(
            name="skills.sh",
            base_url="https://skills.sh",
        ),
        "skillsmp": await repository.upsert_registry_source(
            name="skillsmp",
            base_url="https://skillsmp.com",
        ),
    }
    observed_at = datetime(2026, 3, 8, 20, 45, tzinfo=UTC)

    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_ids["skills.sh"],
        source_url="https://skills.sh/example/skills/agent-tools",
        source_native_id=None,
        weekly_installs=120,
        registry_rank=8,
        observed_at=observed_at,
        raw_payload={"source": "skills.sh"},
    )
    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_ids["skillsmp"],
        source_url="https://skillsmp.com/skills/example-agent-tools",
        source_native_id="example-agent-tools",
        weekly_installs=55,
        registry_rank=None,
        observed_at=observed_at,
        raw_payload={"source": "skillsmp"},
    )

    detail = await repository.get_skill_detail(
        publisher="example",
        repo="skills",
        skill_slug="agent-tools",
    )
    listing = await repository.list_skills(limit=1)

    assert detail is not None
    assert detail["current_total_installs"] == 175
    assert detail["current_total_installs_observed_at"] == observed_at.isoformat()
    assert detail["source_count"] == 2
    assert listing[0]["current_total_installs"] == 175
    assert listing[0]["source_count"] == 2
    assert listing[0]["sources"] == ["skills.sh", "skillsmp"]
    assert {entry["source_name"] for entry in detail["source_entries"]} == {
        "skills.sh",
        "skillsmp",
    }
    assert {entry["source_url"] for entry in detail["source_entries"]} == {
        "https://skills.sh/example/skills/agent-tools",
        "https://skillsmp.com/skills/example-agent-tools",
    }
    assert {entry["source_native_id"] for entry in detail["source_entries"]} == {
        None,
        "example-agent-tools",
    }
    assert {entry["weekly_installs"] for entry in detail["source_entries"]} == {120, 55}
    assert {entry["registry_rank"] for entry in detail["source_entries"]} == {8, None}
    assert {entry["first_seen_at"] for entry in detail["source_entries"]} == {
        observed_at.isoformat()
    }
    assert {entry["last_seen_at"] for entry in detail["source_entries"]} == {
        observed_at.isoformat()
    }


@pytest.mark.asyncio
async def test_skill_source_entry_prefers_source_native_id_and_preserves_first_last_seen(
    tmp_path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'registry-source-updates.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="example",
        repo="skills",
        source_url="https://github.com/example/skills",
        registry_rank=4,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="agent-tools",
        title="agent-tools",
        relative_path="skills/agent-tools",
        registry_url="https://skills.sh/example/skills/agent-tools",
    )
    source_id = await repository.upsert_registry_source(
        name="skillsmp",
        base_url="https://skillsmp.com",
    )
    later_observed_at = datetime(2026, 3, 8, 20, 45, tzinfo=UTC)
    earlier_observed_at = datetime(2026, 3, 7, 20, 45, tzinfo=UTC)

    first_entry_id = await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_id,
        source_url="https://skillsmp.com/skills/example-agent-tools",
        source_native_id="example-agent-tools",
        weekly_installs=55,
        registry_rank=4,
        observed_at=later_observed_at,
        raw_payload={"source": "skillsmp", "version": 1},
    )
    second_entry_id = await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_id,
        source_url="https://skillsmp.com/fr/skills/example-agent-tools",
        source_native_id="example-agent-tools",
        weekly_installs=65,
        registry_rank=5,
        observed_at=earlier_observed_at,
        raw_payload={"source": "skillsmp", "version": 2},
    )

    detail = await repository.get_skill_detail(
        publisher="example",
        repo="skills",
        skill_slug="agent-tools",
    )

    assert detail is not None
    assert first_entry_id == second_entry_id
    assert detail["current_total_installs"] == 65
    assert detail["current_total_installs_observed_at"] == later_observed_at.isoformat()
    assert detail["source_count"] == 1
    assert detail["source_entries"] == [
        {
            "id": first_entry_id,
            "registry_source_id": source_id,
            "source_name": "skillsmp",
            "source_base_url": "https://skillsmp.com",
            "source_url": "https://skillsmp.com/fr/skills/example-agent-tools",
            "source_native_id": "example-agent-tools",
            "weekly_installs": 65,
            "registry_rank": 5,
            "first_seen_at": earlier_observed_at.isoformat(),
            "last_seen_at": later_observed_at.isoformat(),
            "raw_payload": {"source": "skillsmp", "version": 2},
        }
    ]
