from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from skrisk.api import create_app
from skrisk.config import Settings
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


async def _record_skill_with_install_history(
    repository: SkillRepository,
    *,
    repo_id: int,
    repo_snapshot_id: int,
    skill_slug: str,
    risk_report: dict,
    install_history: list[tuple[datetime, int | None, int | None]],
) -> int:
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
        risk_report=risk_report,
    )
    for index, (observed_at, weekly_installs, registry_rank) in enumerate(
        install_history,
        start=1,
    ):
        run_id = await repository.record_registry_sync_run(
            source="skills.sh",
            view="all-time",
            total_skills_reported=3,
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
    return skill_id


@pytest.mark.asyncio
async def test_api_exposes_latest_skill_stats_and_detail(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="tul-sh",
        repo="skills",
        source_url="https://github.com/tul-sh/skills",
        registry_rank=3,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )
    skill_id = await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        skill_slug="agent-tools",
        repo_snapshot_id=repo_snapshot_id,
        risk_report={
            "severity": "high",
            "score": 72,
            "confidence": "likely",
            "categories": ["remote_code_execution"],
            "extracted_domains": ["cli.inference.sh"],
            "indicator_matches": [
                {
                    "indicator_type": "domain",
                    "indicator_value": "cli.inference.sh",
                    "observations": [],
                }
            ],
        },
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 1000, 6),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 1500, 4),
        ],
    )
    await repository.record_external_verdict(
        skill_id=skill_id,
        partner="snyk",
        verdict="CRITICAL",
        summary="Suspicious download URL",
        analyzed_at="2026-03-05T08:31:28.415042+00:00",
    )
    await repository.record_skill_registry_observation(
        skill_id=skill_id,
        registry_sync_run_id=None,
        repo_snapshot_id=repo_snapshot_id,
        observed_at=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
        weekly_installs=1500,
        registry_rank=4,
        observation_kind="scan_attribution",
        raw_payload={"source": "scan"},
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        stats_response = await client.get("/api/stats")
        list_response = await client.get("/api/skills?limit=0")
        detail_response = await client.get("/api/skills/tul-sh/skills/agent-tools")

    assert stats_response.status_code == 200
    assert stats_response.json()["critical_skills"] == 0
    assert stats_response.json()["intel_backed_findings"] == 1
    assert stats_response.json()["tracked_repos"] == 1

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["current_weekly_installs"] == 1500
    assert list_payload[0]["current_weekly_installs_observed_at"] == "2026-03-07T08:00:00+00:00"
    assert list_payload[0]["peak_weekly_installs"] == 1500
    assert list_payload[0]["weekly_installs_delta"] == 500
    assert list_payload[0]["impact_score"] == 60
    assert list_payload[0]["priority_score"] == 94

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["publisher"] == "tul-sh"
    assert detail["repo"] == "skills"
    assert detail["skill_slug"] == "agent-tools"
    assert detail["current_weekly_installs"] == 1500
    assert detail["current_weekly_installs_observed_at"] == "2026-03-07T08:00:00+00:00"
    assert detail["peak_weekly_installs"] == 1500
    assert detail["weekly_installs_delta"] == 500
    assert detail["impact_score"] == 60
    assert detail["priority_score"] == 94
    assert [row["weekly_installs"] for row in detail["install_history"]] == [1000, 1500, 1500]
    assert [row["observation_kind"] for row in detail["install_history"]] == [
        "directory_fetch",
        "directory_fetch",
        "scan_attribution",
    ]
    assert detail["latest_snapshot"]["risk_report"]["severity"] == "high"
    assert detail["external_verdicts"][0]["partner"] == "snyk"


@pytest.mark.asyncio
async def test_app_factory_initializes_database_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "SKRISK_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'factory.db'}",
    )

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/stats")

    assert response.status_code == 200
    assert response.json()["tracked_repos"] == 0


@pytest.mark.asyncio
async def test_api_skills_limit_zero_returns_full_registry(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'all-skills.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="melurna",
        repo="skill-pack",
        source_url="https://github.com/melurna/skill-pack",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=2,
    )

    for skill_slug in ("alpha", "beta"):
        skill_id = await repository.upsert_skill(
            repo_id=repo_id,
            skill_slug=skill_slug,
            title=skill_slug,
            relative_path=f"skills/{skill_slug}",
            registry_url=f"https://skills.sh/melurna/skill-pack/{skill_slug}",
        )
        await repository.record_skill_snapshot(
            skill_id=skill_id,
            repo_snapshot_id=repo_snapshot_id,
            folder_hash=f"hash-{skill_slug}",
            version_label="main@abc123",
            skill_text="echo safe",
            referenced_files=["SKILL.md"],
            extracted_domains=[],
            risk_report={"severity": "none", "score": 0},
        )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/skills?limit=0")

    assert response.status_code == 200
    assert {item["skill_slug"] for item in response.json()} == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_api_skills_support_install_filters_and_sorting(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'skill-sorting.db'}"
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
        discovered_skill_count=3,
    )

    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="risky-riser",
        risk_report={"severity": "high", "score": 70, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 1000, 5),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 2000, 4),
        ],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="popular-safe",
        risk_report={"severity": "low", "score": 25, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 3000, 3),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 9000, 2),
        ],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="shrinking-critical",
        risk_report={"severity": "critical", "score": 55, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 2400, 7),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 1200, 6),
        ],
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        default_response = await client.get("/api/skills?limit=0")
        installs_response = await client.get(
            "/api/skills?limit=0&min_weekly_installs=1500&max_weekly_installs=9000&sort=installs"
        )
        priority_response = await client.get("/api/skills?limit=0&sort=priority")
        risk_response = await client.get("/api/skills?limit=0&sort=risk")
        growth_response = await client.get("/api/skills?limit=0&sort=growth")

    assert default_response.status_code == 200
    assert [item["skill_slug"] for item in default_response.json()] == [
        "risky-riser",
        "shrinking-critical",
        "popular-safe",
    ]

    assert installs_response.status_code == 200
    assert [item["skill_slug"] for item in installs_response.json()] == [
        "popular-safe",
        "risky-riser",
    ]

    assert priority_response.status_code == 200
    assert [item["skill_slug"] for item in priority_response.json()] == [
        "risky-riser",
        "shrinking-critical",
        "popular-safe",
    ]

    assert risk_response.status_code == 200
    assert [item["skill_slug"] for item in risk_response.json()] == [
        "risky-riser",
        "shrinking-critical",
        "popular-safe",
    ]

    assert growth_response.status_code == 200
    assert [item["skill_slug"] for item in growth_response.json()] == [
        "popular-safe",
        "risky-riser",
        "shrinking-critical",
    ]


@pytest.mark.asyncio
async def test_app_serves_built_frontend_for_non_api_routes(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'frontend.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    frontend_dist_root = tmp_path / "frontend-build"
    frontend_dist_root.mkdir(parents=True, exist_ok=True)
    (frontend_dist_root / "index.html").write_text(
        "<!doctype html><html><body>SK Risk SPA</body></html>",
        encoding="utf-8",
    )
    (frontend_dist_root / "robots.txt").write_text("User-agent: *", encoding="utf-8")

    app = create_app(
        session_factory,
        settings=Settings(
            database_url=database_url,
            frontend_dist_root=frontend_dist_root,
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        root_response = await client.get("/")
        deep_link_response = await client.get("/skills/melurna/skill-pack/network-probe")
        asset_response = await client.get("/robots.txt")

    assert root_response.status_code == 200
    assert "SK Risk SPA" in root_response.text
    assert deep_link_response.status_code == 200
    assert deep_link_response.text == root_response.text
    assert asset_response.status_code == 200
    assert "User-agent" in asset_response.text
