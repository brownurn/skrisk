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
        registry_sync_run_id=None,
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
        registry_sync_run_id=None,
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
    assert detail["current_weekly_installs"] == 175
    assert detail["current_weekly_installs_observed_at"] == observed_at.isoformat()
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
async def test_multi_registry_install_sort_uses_combined_installs(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'registry-source-sorting.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
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

    first_repo_id = await repository.upsert_skill_repo(
        publisher="example",
        repo="alpha-skills",
        source_url="https://github.com/example/alpha-skills",
        registry_rank=4,
    )
    first_skill_id = await repository.upsert_skill(
        repo_id=first_repo_id,
        skill_slug="alpha",
        title="alpha",
        relative_path="skills/alpha",
        registry_url="https://skills.sh/example/alpha-skills/alpha",
    )
    await repository.upsert_skill_source_entry(
        skill_id=first_skill_id,
        registry_source_id=source_ids["skills.sh"],
        source_url="https://skills.sh/example/alpha-skills/alpha",
        source_native_id=None,
        weekly_installs=120,
        registry_rank=1,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"source": "skills.sh"},
    )
    await repository.upsert_skill_source_entry(
        skill_id=first_skill_id,
        registry_source_id=source_ids["skillsmp"],
        source_url="https://skillsmp.com/skills/example-alpha",
        source_native_id="example-alpha",
        weekly_installs=55,
        registry_rank=None,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"source": "skillsmp"},
    )

    second_repo_id = await repository.upsert_skill_repo(
        publisher="example",
        repo="beta-skills",
        source_url="https://github.com/example/beta-skills",
        registry_rank=4,
    )
    second_skill_id = await repository.upsert_skill(
        repo_id=second_repo_id,
        skill_slug="beta",
        title="beta",
        relative_path="skills/beta",
        registry_url="https://skills.sh/example/beta-skills/beta",
    )
    await repository.upsert_skill_source_entry(
        skill_id=second_skill_id,
        registry_source_id=source_ids["skills.sh"],
        source_url="https://skills.sh/example/beta-skills/beta",
        source_native_id=None,
        weekly_installs=150,
        registry_rank=2,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"source": "skills.sh"},
    )

    listing = await repository.list_skills(limit=2, sort="installs")

    assert [row["skill_slug"] for row in listing] == ["alpha", "beta"]
    assert listing[0]["current_weekly_installs"] == 175
    assert listing[0]["current_total_installs"] == 175
    assert listing[1]["current_weekly_installs"] == 150
    assert listing[1]["current_total_installs"] == 150


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
        registry_sync_run_id=None,
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
        registry_sync_run_id=None,
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
            "current_registry_sync_run_id": None,
            "current_registry_sync_observed_at": None,
            "view": "all-time",
            "weekly_installs": 65,
            "registry_rank": 5,
            "first_seen_at": earlier_observed_at.isoformat(),
            "last_seen_at": later_observed_at.isoformat(),
            "raw_payload": {"source": "skillsmp", "version": 2},
        }
    ]


@pytest.mark.asyncio
async def test_skill_source_entry_upgrades_existing_url_row_when_native_id_arrives(
    tmp_path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'registry-source-upgrade.db'}"
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
    observed_at = datetime(2026, 3, 8, 20, 45, tzinfo=UTC)
    source_url = "https://skillsmp.com/skills/example-agent-tools"

    first_entry_id = await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_id,
        source_url=source_url,
        source_native_id=None,
        weekly_installs=40,
        registry_rank=None,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"stage": "discovery"},
    )
    second_entry_id = await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_id,
        source_url=source_url,
        source_native_id="example-agent-tools",
        weekly_installs=45,
        registry_rank=2,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"stage": "api"},
    )

    detail = await repository.get_skill_detail(
        publisher="example",
        repo="skills",
        skill_slug="agent-tools",
    )

    assert detail is not None
    assert first_entry_id == second_entry_id
    assert detail["source_count"] == 1
    assert detail["current_total_installs"] == 45
    assert detail["source_entries"][0]["source_native_id"] == "example-agent-tools"
    assert detail["source_entries"][0]["registry_rank"] == 2
    assert detail["source_entries"][0]["raw_payload"] == {"stage": "api"}


@pytest.mark.asyncio
async def test_skill_registry_context_preserves_run_observed_at_when_source_entry_is_later_merged(
    tmp_path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'registry-context-preserved.db'}"
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
    run_id = await repository.record_registry_sync_run(
        source="skillsmp",
        view="all-time",
        total_skills_reported=1,
        pages_fetched=0,
        success=True,
    )
    directory_observed_at = datetime(2026, 3, 8, 20, 45, tzinfo=UTC)
    merged_observed_at = datetime(2026, 3, 9, 9, 10, tzinfo=UTC)

    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_id,
        source_url="https://skillsmp.com/skills/example-agent-tools",
        source_native_id="example-agent-tools",
        weekly_installs=55,
        registry_rank=4,
        registry_sync_run_id=run_id,
        observed_at=directory_observed_at,
        raw_payload={"stage": "directory"},
    )
    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_id,
        source_url="https://skillsmp.com/skills/example-agent-tools",
        source_native_id="example-agent-tools",
        weekly_installs=55,
        registry_rank=4,
        registry_sync_run_id=None,
        observed_at=merged_observed_at,
        raw_payload={"stage": "api"},
    )

    context = await repository.get_skill_registry_observation_context(skill_id=skill_id)

    assert context == {
        "weekly_installs": 55,
        "observed_at": directory_observed_at,
        "registry_rank": 4,
        "registry_sync_run_id": run_id,
        "view": "all-time",
        "source": "skillsmp",
    }
