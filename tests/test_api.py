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
    assert list_payload[0]["registry_url"] == "https://skills.sh/tul-sh/skills/agent-tools"
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
async def test_api_exposes_multi_registry_sources_and_install_breakdown(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'multi-source-api.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="openclaw",
        repo="openclaw",
        source_url="https://github.com/openclaw/openclaw",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="prose",
        title="prose",
        relative_path="extensions/open-prose/skills/prose",
        registry_url="https://skills.sh/openclaw/openclaw/prose",
    )
    await repository.record_skill_snapshot(
        skill_id=skill_id,
        repo_snapshot_id=repo_snapshot_id,
        folder_hash="hash-prose",
        version_label="main@abc123",
        skill_text="name: prose",
        referenced_files=["SKILL.md"],
        extracted_domains=[],
        risk_report={"severity": "medium", "score": 50, "confidence": "likely"},
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
    observed_at = datetime(2026, 3, 7, 8, 0, tzinfo=UTC)
    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_ids["skills.sh"],
        source_url="https://skills.sh/openclaw/openclaw/prose",
        source_native_id=None,
        weekly_installs=1_500,
        registry_rank=4,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"source": "skills.sh"},
    )
    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=source_ids["skillsmp"],
        source_url="https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
        source_native_id="openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
        weekly_installs=400,
        registry_rank=None,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"source": "skillsmp"},
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        list_response = await client.get("/api/skills?limit=0")
        detail_response = await client.get("/api/skills/openclaw/openclaw/prose")

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["current_weekly_installs"] == 1900
    assert list_payload[0]["current_total_installs"] == 1900
    assert list_payload[0]["source_count"] == 2
    assert list_payload[0]["sources"] == ["skills.sh", "skillsmp"]
    assert [row["source_name"] for row in list_payload[0]["install_breakdown"]] == [
        "skills.sh",
        "skillsmp",
    ]
    assert list_payload[0]["registry_url"] == "https://skills.sh/openclaw/openclaw/prose"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["current_total_installs"] == 1900
    assert detail["source_count"] == 2
    assert detail["sources"] == ["skills.sh", "skillsmp"]
    assert len(detail["source_entries"]) == 2
    assert detail["source_entries"][1]["source_name"] == "skillsmp"


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
async def test_api_exposes_multi_registry_provenance_and_combined_installs(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'multi-registry-api.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="openclaw",
        repo="openclaw",
        source_url="https://github.com/openclaw/openclaw",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="prose",
        title="Prose",
        relative_path="extensions/open-prose/skills/prose",
        registry_url="https://skills.sh/openclaw/openclaw/prose",
        registry_source="skills.sh",
    )
    await repository.record_skill_snapshot(
        skill_id=skill_id,
        repo_snapshot_id=repo_snapshot_id,
        folder_hash="hash-prose",
        version_label="main@abc123",
        skill_text="name: prose",
        referenced_files=["SKILL.md"],
        extracted_domains=[],
        risk_report={"severity": "medium", "score": 42, "confidence": "likely"},
    )
    skills_sh_source_id = await repository.upsert_registry_source(
        name="skills.sh",
        base_url="https://skills.sh",
    )
    skillsmp_source_id = await repository.upsert_registry_source(
        name="skillsmp",
        base_url="https://skillsmp.com",
    )
    observed_at = datetime(2026, 3, 8, 9, 0, tzinfo=UTC)
    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=skills_sh_source_id,
        source_url="https://skills.sh/openclaw/openclaw/prose",
        source_native_id=None,
        weekly_installs=1200,
        registry_rank=3,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"source": "skills.sh"},
    )
    await repository.upsert_skill_source_entry(
        skill_id=skill_id,
        registry_source_id=skillsmp_source_id,
        source_url="https://skillsmp.com/skills/openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
        source_native_id="openclaw-openclaw-extensions-open-prose-skills-prose-skill-md",
        weekly_installs=300,
        registry_rank=None,
        registry_sync_run_id=None,
        observed_at=observed_at,
        raw_payload={"source": "skillsmp", "author": "openclaw"},
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        list_response = await client.get("/api/skills?limit=1")
        detail_response = await client.get("/api/skills/openclaw/openclaw/prose")

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["current_total_installs"] == 1500
    assert list_payload[0]["source_count"] == 2
    assert list_payload[0]["sources"] == ["skills.sh", "skillsmp"]

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["current_total_installs"] == 1500
    assert detail["source_count"] == 2
    assert [entry["source_name"] for entry in detail["source_entries"]] == ["skills.sh", "skillsmp"]
    assert [entry["weekly_installs"] for entry in detail["source_entries"]] == [1200, 300]


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
async def test_api_skills_includes_seed_only_skills_with_install_telemetry(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'seed-only.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="melurna",
        repo="skill-pack",
        source_url="https://github.com/melurna/skill-pack",
        registry_rank=2,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="seed-only",
        title="Seed Only",
        relative_path="registry/seed-only",
        registry_url="https://skills.sh/melurna/skill-pack/seed-only",
    )
    run_id = await repository.record_registry_sync_run(
        source="skills.sh",
        view="all-time",
        total_skills_reported=250,
        pages_fetched=3,
        success=True,
    )
    await repository.record_skill_registry_observation(
        skill_id=skill_id,
        registry_sync_run_id=run_id,
        repo_snapshot_id=None,
        observed_at=datetime(2026, 3, 7, 8, 0, tzinfo=UTC),
        weekly_installs=480,
        registry_rank=2,
        observation_kind="directory_fetch",
        raw_payload={"installs": 480},
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/skills?limit=0")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["skill_slug"] == "seed-only"
    assert payload[0]["current_weekly_installs"] == 480
    assert payload[0]["latest_snapshot"] is None


@pytest.mark.asyncio
async def test_api_skills_default_and_priority_sort_break_ties_by_installs(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'priority-ties.db'}"
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

    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="higher-installs",
        risk_report={"severity": "high", "score": 20, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 600, 5),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 2000, 4),
        ],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="higher-risk-lower-installs",
        risk_report={"severity": "medium", "score": 22, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 600, 5),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 1200, 4),
        ],
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        default_response = await client.get("/api/skills?limit=0")
        priority_response = await client.get("/api/skills?limit=0&sort=priority")

    assert default_response.status_code == 200
    assert [item["skill_slug"] for item in default_response.json()] == [
        "higher-installs",
        "higher-risk-lower-installs",
    ]

    assert priority_response.status_code == 200
    assert [item["skill_slug"] for item in priority_response.json()] == [
        "higher-installs",
        "higher-risk-lower-installs",
    ]


@pytest.mark.asyncio
async def test_api_skills_install_sort_keeps_zero_above_missing_telemetry(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'install-ordering.db'}"
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
        skill_slug="positive-installs",
        risk_report={"severity": "low", "score": 15, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 5, 3),
        ],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="zero-installs",
        risk_report={"severity": "low", "score": 10, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 0, 4),
        ],
    )
    missing_skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="unknown-installs",
        title="unknown-installs",
        relative_path="skills/unknown-installs",
        registry_url="https://skills.sh/tul-sh/skills/unknown-installs",
    )
    await repository.record_skill_snapshot(
        skill_id=missing_skill_id,
        repo_snapshot_id=repo_snapshot_id,
        folder_hash="hash-unknown-installs",
        version_label="main@abc123",
        skill_text="name: unknown-installs",
        referenced_files=["SKILL.md"],
        extracted_domains=[],
        risk_report={"severity": "critical", "score": 90, "confidence": "likely"},
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        installs_response = await client.get("/api/skills?limit=0&sort=installs")

    assert installs_response.status_code == 200
    assert [item["skill_slug"] for item in installs_response.json()] == [
        "positive-installs",
        "zero-installs",
        "unknown-installs",
    ]


@pytest.mark.asyncio
async def test_api_skills_growth_sort_keeps_zero_above_missing_telemetry(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'growth-ordering.db'}"
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
        skill_slug="positive-growth",
        risk_report={"severity": "low", "score": 15, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 6, 8, 0, tzinfo=UTC), 1, 3),
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 5, 2),
        ],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="zero-installs",
        risk_report={"severity": "low", "score": 10, "confidence": "likely"},
        install_history=[
            (datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 0, 4),
        ],
    )
    missing_skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="unknown-installs",
        title="unknown-installs",
        relative_path="skills/unknown-installs",
        registry_url="https://skills.sh/tul-sh/skills/unknown-installs",
    )
    await repository.record_skill_snapshot(
        skill_id=missing_skill_id,
        repo_snapshot_id=repo_snapshot_id,
        folder_hash="hash-unknown-installs",
        version_label="main@abc123",
        skill_text="name: unknown-installs",
        referenced_files=["SKILL.md"],
        extracted_domains=[],
        risk_report={"severity": "critical", "score": 90, "confidence": "likely"},
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        growth_response = await client.get("/api/skills?limit=0&sort=growth")

    assert growth_response.status_code == 200
    assert [item["skill_slug"] for item in growth_response.json()] == [
        "positive-growth",
        "zero-installs",
        "unknown-installs",
    ]


@pytest.mark.asyncio
async def test_api_skills_page_supports_server_side_pagination_and_search(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'skills-page.db'}"
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
        discovered_skill_count=3,
    )

    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="alpha-agent",
        risk_report={"severity": "high", "score": 85, "confidence": "likely"},
        install_history=[(datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 2200, 1)],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="beta-agent",
        risk_report={"severity": "medium", "score": 70, "confidence": "likely"},
        install_history=[(datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 1800, 2)],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="gamma-safe",
        risk_report={"severity": "low", "score": 10, "confidence": "likely"},
        install_history=[(datetime(2026, 3, 7, 8, 0, tzinfo=UTC), 50, 3)],
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/skills/page?page=2&page_size=1&sort=installs&q=agent&min_weekly_installs=1000"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 2
    assert payload["page_size"] == 1
    assert payload["has_previous"] is True
    assert payload["has_next"] is False
    assert [item["skill_slug"] for item in payload["items"]] == ["beta-agent"]


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


@pytest.mark.asyncio
async def test_api_exposes_fast_overview_with_flagged_repos(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'overview-api.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    high_repo_id = await repository.upsert_skill_repo(
        publisher="acme",
        repo="skills-pack",
        source_url="https://github.com/acme/skills-pack",
        registry_rank=1,
    )
    critical_repo_id = await repository.upsert_skill_repo(
        publisher="melurna",
        repo="threat-pack",
        source_url="https://github.com/melurna/threat-pack",
        registry_rank=2,
    )
    high_repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=high_repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )
    critical_repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=critical_repo_id,
        commit_sha="def456",
        default_branch="main",
        discovered_skill_count=1,
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=high_repo_id,
        repo_snapshot_id=high_repo_snapshot_id,
        skill_slug="network-probe",
        risk_report={
            "severity": "high",
            "score": 74,
            "confidence": "likely",
            "categories": ["network_egress"],
            "indicator_matches": [],
        },
        install_history=[(datetime(2026, 3, 9, 8, 0, tzinfo=UTC), 120, 10)],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=critical_repo_id,
        repo_snapshot_id=critical_repo_snapshot_id,
        skill_slug="secret-dump",
        risk_report={
            "severity": "critical",
            "score": 93,
            "confidence": "confirmed",
            "categories": ["exfiltration"],
            "indicator_matches": [
                {
                    "indicator_type": "domain",
                    "indicator_value": "drop.example",
                    "observations": [],
                }
            ],
        },
        install_history=[(datetime(2026, 3, 9, 8, 0, tzinfo=UTC), 5400, 2)],
    )

    async def fail_latest_rows(*_args, **_kwargs):
        raise AssertionError("overview should not load all latest rows into Python")

    monkeypatch.setattr(SkillRepository, "_load_latest_skill_rows", fail_latest_rows)

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["tracked_repos"] == 2
    assert payload["stats"]["critical_skills"] == 1
    assert payload["critical_skills"][0]["skill_slug"] == "secret-dump"
    assert payload["flagged_repos"][0]["publisher"] == "melurna"
    assert payload["flagged_repos"][0]["repo"] == "threat-pack"


@pytest.mark.asyncio
async def test_api_overview_and_skills_page_do_not_depend_on_latest_snapshot_subquery(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'latest-summary.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="acme",
        repo="skills-pack",
        source_url="https://github.com/acme/skills-pack",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=2,
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="network-probe",
        risk_report={
            "severity": "high",
            "score": 74,
            "confidence": "likely",
            "categories": ["network_egress"],
            "indicator_matches": [],
        },
        install_history=[(datetime(2026, 3, 9, 8, 0, tzinfo=UTC), 120, 10)],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="secret-dump",
        risk_report={
            "severity": "critical",
            "score": 93,
            "confidence": "confirmed",
            "categories": ["exfiltration"],
            "indicator_matches": [
                {
                    "indicator_type": "domain",
                    "indicator_value": "drop.example",
                    "observations": [],
                }
            ],
        },
        install_history=[(datetime(2026, 3, 9, 8, 0, tzinfo=UTC), 5400, 2)],
    )

    def fail_latest_snapshot_ids(*_args, **_kwargs):
        raise AssertionError("summary endpoints should not recompute latest snapshot ids")

    monkeypatch.setattr(SkillRepository, "_latest_snapshot_ids_subquery", fail_latest_snapshot_ids)

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        overview_response = await client.get("/api/overview")
        skills_page_response = await client.get("/api/skills/page?page=1&page_size=50")

    assert overview_response.status_code == 200
    assert overview_response.json()["stats"]["critical_skills"] == 1
    assert skills_page_response.status_code == 200
    assert skills_page_response.json()["items"][0]["skill_slug"] == "secret-dump"


@pytest.mark.asyncio
async def test_api_repo_detail_returns_skills_and_flagged_rollup(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'repo-detail.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="ypyt1",
        repo="all-skills",
        source_url="https://github.com/ypyt1/all-skills",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=2,
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="dangerous-helper",
        risk_report={"severity": "critical", "score": 92, "confidence": "confirmed"},
        install_history=[(datetime(2026, 3, 9, 8, 0, tzinfo=UTC), 5000, 1)],
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="guide-only",
        risk_report={"severity": "none", "score": 0, "confidence": "likely"},
        install_history=[(datetime(2026, 3, 9, 8, 0, tzinfo=UTC), 100, 2)],
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/repos/ypyt1/all-skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload["publisher"] == "ypyt1"
    assert payload["repo"] == "all-skills"
    assert payload["flagged_skill_count"] == 1
    assert payload["critical_skill_count"] == 1
    assert payload["top_severity"] == "critical"
    assert [item["skill_slug"] for item in payload["skills"]] == [
        "dangerous-helper",
        "guide-only",
    ]


@pytest.mark.asyncio
async def test_api_summary_endpoints_trim_heavy_snapshot_evidence(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'summary-payload.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="acme",
        repo="skills-pack",
        source_url="https://github.com/acme/skills-pack",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )
    await _record_skill_with_install_history(
        repository,
        repo_id=repo_id,
        repo_snapshot_id=repo_snapshot_id,
        skill_slug="secret-dump",
        risk_report={
            "severity": "critical",
            "score": 93,
            "behavior_score": 55,
            "intel_score": 20,
            "change_score": 18,
            "confidence": "confirmed",
            "categories": ["exfiltration"],
            "findings": [
                {
                    "path": "SKILL.md",
                    "category": "data_exfiltration",
                    "severity": "critical",
                    "evidence": "upload ~/.aws/credentials",
                }
            ],
            "indicator_matches": [
                {
                    "indicator_type": "domain",
                    "indicator_value": "drop.example",
                    "observations": [{"source_provider": "abusech"}],
                }
            ],
        },
        install_history=[(datetime(2026, 3, 9, 8, 0, tzinfo=UTC), 5400, 2)],
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        overview_response = await client.get("/api/overview")
        skills_page_response = await client.get("/api/skills/page?page=1&page_size=50")
        detail_response = await client.get("/api/skills/acme/skills-pack/secret-dump")

    assert overview_response.status_code == 200
    critical_summary = overview_response.json()["critical_skills"][0]["latest_snapshot"]["risk_report"]
    assert critical_summary["severity"] == "critical"
    assert critical_summary["indicator_matches"] == []
    assert critical_summary["findings"] == []

    assert skills_page_response.status_code == 200
    page_summary = skills_page_response.json()["items"][0]["latest_snapshot"]["risk_report"]
    assert page_summary["indicator_matches"] == []
    assert page_summary["findings"] == []

    assert detail_response.status_code == 200
    detail_risk_report = detail_response.json()["latest_snapshot"]["risk_report"]
    assert len(detail_risk_report["indicator_matches"]) == 1
    assert len(detail_risk_report["findings"]) == 1


@pytest.mark.asyncio
async def test_skill_detail_api_surfaces_outbound_evidence_and_country_risk(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'outbound-evidence.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="176336109",
        repo=".openclaw",
        source_url="https://github.com/176336109/.openclaw",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="bocha-web-search",
        title="bocha-web-search",
        relative_path="skills/bocha-web-search",
        registry_url="https://skills.sh/176336109/.openclaw/bocha-web-search",
    )
    skill_snapshot_id = await repository.record_skill_snapshot(
        skill_id=skill_id,
        repo_snapshot_id=repo_snapshot_id,
        folder_hash="hash-bocha",
        version_label="main@abc123",
        skill_text="curl -X POST https://api.bocha.cn/v1/web-search",
        referenced_files=["test_api.sh"],
        extracted_domains=["api.bocha.cn"],
        risk_report={
            "severity": "medium",
            "score": 18,
            "behavior_score": 18,
            "intel_score": 0,
            "change_score": 0,
            "confidence": "likely",
            "categories": ["credential_transmission"],
            "domains": ["api.bocha.cn"],
            "findings": [
                {
                    "path": "test_api.sh",
                    "category": "credential_transmission",
                    "severity": "high",
                    "evidence": "RESPONSE=$(curl -s -X POST \"https://api.bocha.cn/v1/web-search\" \\",
                    "context": "direct_operational",
                    "details": {
                        "kind": "credential_transmission",
                        "source_kind": "authorization_header",
                        "source_values": ["BOCHA_API_KEY"],
                        "sink_kind": "curl",
                        "sink_url": "https://api.bocha.cn/v1/web-search",
                        "sink_host": "api.bocha.cn",
                        "transport_detail": "Authorization header",
                    },
                }
            ],
            "indicator_matches": [],
        },
    )
    domain_indicator_id = await repository.upsert_indicator("domain", "api.bocha.cn")
    await repository.record_skill_indicator_link(
        skill_snapshot_id=skill_snapshot_id,
        indicator_id=domain_indicator_id,
        source_path="test_api.sh",
        extraction_kind="url-host",
        raw_value="https://api.bocha.cn/v1/web-search",
        is_new_in_snapshot=True,
    )
    await repository.record_indicator_enrichment(
        indicator_id=domain_indicator_id,
        provider="local_dns",
        lookup_key="api.bocha.cn",
        status="completed",
        summary="resolved_ips=123.57.128.210",
        archive_relative_path=None,
        normalized_payload={
            "host": "api.bocha.cn",
            "resolved_ips": ["123.57.128.210"],
            "resolved_ip_profiles": {
                "123.57.128.210": {
                    "ip": "123.57.128.210",
                    "countryCode": "CN",
                    "countryName": "China",
                    "asName": "Hangzhou Alibaba Advertising Co.,Ltd.",
                }
            },
        },
        requested_at=datetime(2026, 3, 11, 8, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 11, 8, 0, tzinfo=UTC),
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/skills/176336109/.openclaw/bocha-web-search")

    assert response.status_code == 200
    payload = response.json()
    assert payload["outbound_evidence"] == [
        {
            "path": "test_api.sh",
            "category": "credential_transmission",
            "severity": "high",
            "context": "direct_operational",
            "evidence": 'RESPONSE=$(curl -s -X POST "https://api.bocha.cn/v1/web-search" \\',
            "source_kind": "authorization_header",
            "source_values": ["BOCHA_API_KEY"],
            "sink_kind": "curl",
            "sink_url": "https://api.bocha.cn/v1/web-search",
            "sink_host": "api.bocha.cn",
            "transport_detail": "Authorization header",
            "destinations": [
                {
                    "ip": "123.57.128.210",
                    "country_code": "CN",
                    "country_name": "China",
                    "asn_name": "Hangzhou Alibaba Advertising Co.,Ltd.",
                    "is_primary_cyber_concern": True,
                }
            ],
            "has_primary_cyber_concern_destination": True,
        }
    ]


@pytest.mark.asyncio
async def test_skill_detail_api_prefers_enriched_domain_link_for_outbound_evidence(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'outbound-evidence-prefer-domain.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)

    repository = SkillRepository(session_factory)
    repo_id = await repository.upsert_skill_repo(
        publisher="176336109",
        repo=".openclaw",
        source_url="https://github.com/176336109/.openclaw",
        registry_rank=1,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
    )
    skill_id = await repository.upsert_skill(
        repo_id=repo_id,
        skill_slug="bocha-web-search",
        title="bocha-web-search",
        relative_path="skills/bocha-web-search",
        registry_url="https://skills.sh/176336109/.openclaw/bocha-web-search",
    )
    skill_snapshot_id = await repository.record_skill_snapshot(
        skill_id=skill_id,
        repo_snapshot_id=repo_snapshot_id,
        folder_hash="hash-bocha",
        version_label="main@abc123",
        skill_text="curl -X POST https://api.bocha.cn/v1/web-search",
        referenced_files=["test_api.sh"],
        extracted_domains=["api.bocha.cn"],
        risk_report={
            "severity": "medium",
            "score": 18,
            "behavior_score": 18,
            "intel_score": 0,
            "change_score": 0,
            "confidence": "likely",
            "categories": ["credential_transmission"],
            "domains": ["api.bocha.cn"],
            "findings": [
                {
                    "path": "test_api.sh",
                    "category": "credential_transmission",
                    "severity": "high",
                    "evidence": "curl -X POST https://api.bocha.cn/v1/web-search",
                    "context": "direct_operational",
                    "details": {
                        "kind": "credential_transmission",
                        "source_kind": "authorization_header",
                        "source_values": ["BOCHA_API_KEY"],
                        "sink_kind": "curl",
                        "sink_url": "https://api.bocha.cn/v1/web-search",
                        "sink_host": "api.bocha.cn",
                        "transport_detail": "Authorization header",
                    },
                }
            ],
            "indicator_matches": [],
        },
    )
    url_indicator_id = await repository.upsert_indicator("url", "https://api.bocha.cn/v1/web-search")
    domain_indicator_id = await repository.upsert_indicator("domain", "api.bocha.cn")
    await repository.record_skill_indicator_link(
        skill_snapshot_id=skill_snapshot_id,
        indicator_id=url_indicator_id,
        source_path="test_api.sh",
        extraction_kind="inline-url",
        raw_value="https://api.bocha.cn/v1/web-search",
        is_new_in_snapshot=True,
    )
    await repository.record_skill_indicator_link(
        skill_snapshot_id=skill_snapshot_id,
        indicator_id=domain_indicator_id,
        source_path="test_api.sh",
        extraction_kind="url-host",
        raw_value="https://api.bocha.cn/v1/web-search",
        is_new_in_snapshot=True,
    )
    await repository.record_indicator_enrichment(
        indicator_id=domain_indicator_id,
        provider="local_dns",
        lookup_key="api.bocha.cn",
        status="completed",
        summary="resolved_ips=123.57.128.210,8.147.108.53",
        archive_relative_path=None,
        normalized_payload={
            "host": "api.bocha.cn",
            "resolved_ips": ["123.57.128.210", "8.147.108.53"],
            "resolved_ip_profiles": {
                "123.57.128.210": {
                    "ip": "123.57.128.210",
                    "countryCode": "CN",
                    "countryName": "China",
                    "asName": "Hangzhou Alibaba Advertising Co.,Ltd.",
                },
                "8.147.108.53": {
                    "ip": "8.147.108.53",
                    "countryCode": "CN",
                    "countryName": "China",
                    "asName": "Hangzhou Alibaba Advertising Co.,Ltd.",
                },
            },
        },
        requested_at=datetime(2026, 3, 11, 8, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 11, 8, 0, tzinfo=UTC),
    )

    app = create_app(session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/skills/176336109/.openclaw/bocha-web-search")

    assert response.status_code == 200
    payload = response.json()
    assert payload["outbound_evidence"][0]["destinations"] == [
        {
            "ip": "123.57.128.210",
            "country_code": "CN",
            "country_name": "China",
            "asn_name": "Hangzhou Alibaba Advertising Co.,Ltd.",
            "is_primary_cyber_concern": True,
        },
        {
            "ip": "8.147.108.53",
            "country_code": "CN",
            "country_name": "China",
            "asn_name": "Hangzhou Alibaba Advertising Co.,Ltd.",
            "is_primary_cyber_concern": True,
        },
    ]
    assert payload["outbound_evidence"][0]["has_primary_cyber_concern_destination"] is True
