from __future__ import annotations

from datetime import UTC, datetime

import pytest

from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


@pytest.mark.asyncio
async def test_repository_records_latest_installs_and_history(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'registry-observations.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="tul-sh",
        repo="skills",
        source_url="https://github.com/tul-sh/skills",
        registry_rank=4,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="agent-tools",
        title="agent-tools",
        relative_path="skills/agent-tools",
        registry_url="https://skills.sh/tul-sh/skills/agent-tools",
    )

    first_run_id = await repository.record_registry_sync_run(
        source="skills.sh",
        view="all-time",
        total_skills_reported=3,
        pages_fetched=1,
        success=True,
    )
    first_observed_at = datetime(2026, 3, 7, 16, 0, tzinfo=UTC)
    await repository.record_skill_registry_observation(
        skill_id=skill_id,
        registry_sync_run_id=first_run_id,
        repo_snapshot_id=None,
        observed_at=first_observed_at,
        weekly_installs=1200,
        registry_rank=4,
        observation_kind="directory_fetch",
        raw_payload={"installs": 1200},
    )

    second_run_id = await repository.record_registry_sync_run(
        source="skills.sh",
        view="all-time",
        total_skills_reported=3,
        pages_fetched=1,
        success=True,
    )
    second_observed_at = datetime(2026, 3, 8, 16, 0, tzinfo=UTC)
    await repository.record_skill_registry_observation(
        skill_id=skill_id,
        registry_sync_run_id=second_run_id,
        repo_snapshot_id=None,
        observed_at=second_observed_at,
        weekly_installs=1500,
        registry_rank=3,
        observation_kind="directory_fetch",
        raw_payload={"installs": 1500},
    )

    detail = await repository.get_skill_detail(
        publisher="tul-sh",
        repo="skills",
        skill_slug="agent-tools",
    )
    observations = await repository.list_skill_registry_observations(skill_id=skill_id)

    assert detail is not None
    assert detail["current_weekly_installs"] == 1500
    assert detail["current_registry_rank"] == 3
    assert detail["current_weekly_installs_observed_at"] == second_observed_at.isoformat()
    assert [row["weekly_installs"] for row in observations] == [1200, 1500]
    assert [row["registry_rank"] for row in observations] == [4, 3]


@pytest.mark.asyncio
async def test_scan_attribution_appends_history_without_overwriting_current_directory_metrics(
    tmp_path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'scan-attribution.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="tul-sh",
        repo="skills",
        source_url="https://github.com/tul-sh/skills",
        registry_rank=6,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="agent-tools",
        title="agent-tools",
        relative_path="skills/agent-tools",
        registry_url="https://skills.sh/tul-sh/skills/agent-tools",
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )

    sync_run_id = await repository.record_registry_sync_run(
        source="skills.sh",
        view="all-time",
        total_skills_reported=3,
        pages_fetched=1,
        success=True,
    )
    directory_observed_at = datetime(2026, 3, 7, 16, 0, tzinfo=UTC)
    await repository.record_skill_registry_observation(
        skill_id=skill_id,
        registry_sync_run_id=sync_run_id,
        repo_snapshot_id=None,
        observed_at=directory_observed_at,
        weekly_installs=800,
        registry_rank=6,
        observation_kind="directory_fetch",
        raw_payload={"installs": 800},
    )

    scan_observed_at = datetime(2026, 3, 7, 20, 0, tzinfo=UTC)
    await repository.record_skill_registry_observation(
        skill_id=skill_id,
        registry_sync_run_id=None,
        repo_snapshot_id=repo_snapshot_id,
        observed_at=scan_observed_at,
        weekly_installs=800,
        registry_rank=6,
        observation_kind="scan_attribution",
        raw_payload={"source": "scan"},
    )

    detail = await repository.get_skill_detail(
        publisher="tul-sh",
        repo="skills",
        skill_slug="agent-tools",
    )
    observations = await repository.list_skill_registry_observations(skill_id=skill_id)

    assert detail is not None
    assert detail["current_weekly_installs"] == 800
    assert detail["current_registry_rank"] == 6
    assert detail["current_weekly_installs_observed_at"] == directory_observed_at.isoformat()
    assert [row["observation_kind"] for row in observations] == [
        "directory_fetch",
        "scan_attribution",
    ]
    assert observations[1]["repo_snapshot_id"] == repo_snapshot_id
