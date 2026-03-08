from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from skrisk.api.dashboard import router as dashboard_router
from skrisk.api import create_app
from skrisk.config import Settings
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


async def _record_dashboard_skill(
    repository: SkillRepository,
    *,
    repo_id: int,
    repo_snapshot_id: int,
    skill_slug: str,
    risk_score: int,
    install_history: list[tuple[datetime, int, int]],
) -> None:
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug=skill_slug,
        title=skill_slug,
        relative_path=f"skills/{skill_slug}",
        registry_url=f"https://skills.sh/tul-sh/skills/{skill_slug}",
    )
    await repository.record_skill_snapshot(
        skill_id=skill_id,
        repo_snapshot_id=repo_snapshot_id,
        folder_hash=f"hash-{skill_slug}",
        version_label="main@abc123",
        skill_text=f"name: {skill_slug}",
        referenced_files=["SKILL.md"],
        extracted_domains=[],
        risk_report={
            "severity": "critical",
            "score": risk_score,
            "confidence": "likely",
        },
    )
    for index, (observed_at, weekly_installs, registry_rank) in enumerate(
        install_history,
        start=1,
    ):
        run_id = await repository.record_registry_sync_run(
            source="skills.sh",
            view="all-time",
            total_skills_reported=2,
            pages_fetched=index,
            success=True,
        )
        await repository.record_skill_registry_observation(
            skill_id=skill_id,
            registry_sync_run_id=run_id,
            repo_snapshot_id=None,
            observed_at=observed_at,
            weekly_installs=weekly_installs,
            registry_rank=registry_rank,
            observation_kind="directory_fetch",
            raw_payload={"installs": weekly_installs},
        )


@pytest.mark.asyncio
async def test_frontend_shell_reports_missing_build_cleanly(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'frontend-shell.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)
    app = create_app(
        session_factory,
        settings=Settings(
            database_url=database_url,
            frontend_dist_root=tmp_path / "missing-build",
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 503
    assert "SK Risk frontend build not found" in response.text
    assert "npm run build" in response.text


@pytest.mark.asyncio
async def test_dashboard_overview_orders_critical_skills_by_priority(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'dashboard-priority.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="tul-sh",
        repo="skills",
        source_url="https://github.com/tul-sh/skills",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=2,
    )
    await _record_dashboard_skill(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="top-priority",
        risk_score=60,
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 1000, 5),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 1500, 4),
        ],
    )
    await _record_dashboard_skill(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="newer-lower-priority",
        risk_score=40,
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 1000, 8),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 2000, 7),
        ],
    )

    app = FastAPI()
    app.state.session_factory = session_factory
    app.state.db_initialized = True
    app.include_router(dashboard_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.text.index("top-priority") < response.text.index("newer-lower-priority")
