from __future__ import annotations

from pathlib import Path

import pytest

from skrisk.analysis.analyzer import ExtractedIndicator, RiskReport
from skrisk.services.analysis_spool import (
    AnalysisSpool,
    AnalysisSpoolProducerService,
    AnalysisSpoolIngestService,
)
from skrisk.services.repo_analysis import AnalyzedCheckout, AnalyzedSkill
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


def _sample_checkout() -> AnalyzedCheckout:
    return AnalyzedCheckout(
        publisher="tul-sh",
        repo="skills",
        checkout_root="/tmp/checkout",
        commit_sha="abc123",
        default_branch="main",
        discovered_skill_count=1,
        skills=[
            AnalyzedSkill(
                skill_slug="compact-skill",
                relative_path=".agents/skills/compact-skill",
                folder_hash="folder-hash",
                skill_text="Visit compact.example for updates.",
                referenced_files=["SKILL.md"],
                report=RiskReport(
                    publisher="tul-sh",
                    repo="skills",
                    skill_slug="compact-skill",
                    severity="none",
                    score=0,
                    behavior_score=0,
                    domains=["compact.example"],
                    indicators=[
                        ExtractedIndicator(
                            path="SKILL.md",
                            indicator_type="domain",
                            indicator_value="compact.example",
                            extraction_kind="bare-domain",
                            raw_value="compact.example",
                        )
                    ],
                ),
            )
        ],
    )


def test_analysis_spool_claims_are_exclusive(tmp_path: Path) -> None:
    spool = AnalysisSpool(tmp_path / "archive")
    candidate = {
        "id": 42,
        "publisher": "tul-sh",
        "repo": "skills",
        "source_url": "https://github.com/tul-sh/skills",
    }

    first_claim = spool.claim_repo(candidate)
    second_claim = spool.claim_repo(candidate)

    assert first_claim is not None
    assert second_claim is None


@pytest.mark.asyncio
async def test_ingest_service_persists_spooled_analysis_and_clears_claim(tmp_path: Path) -> None:
    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    await init_db(session_factory)
    repository = SkillRepository(session_factory)
    spool = AnalysisSpool(tmp_path / "archive")

    repo_id = await repository.upsert_skill_repo(
        publisher="tul-sh",
        repo="skills",
        source_url="https://github.com/tul-sh/skills",
        registry_rank=None,
    )
    claim = spool.claim_repo(
        {
            "id": repo_id,
            "publisher": "tul-sh",
            "repo": "skills",
            "source_url": "https://github.com/tul-sh/skills",
        }
    )
    assert claim is not None
    spool.write_artifact(claim=claim, analyzed_checkout=_sample_checkout())

    service = AnalysisSpoolIngestService(
        session_factory=session_factory,
        spool=spool,
    )
    summary = await service.run_once(limit_artifacts=10, continuous=False)

    detail = await repository.get_skill_detail(
        publisher="tul-sh",
        repo="skills",
        skill_slug="compact-skill",
    )

    assert summary["artifacts_ingested"] == 1
    assert detail is not None
    assert "compact.example" in detail["latest_snapshot"]["extracted_domains"]
    assert spool.list_pending_artifacts() == []
    assert not spool.is_claimed(repo_id)


@pytest.mark.asyncio
async def test_producer_service_spools_artifacts_without_persisting_to_db(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = create_sqlite_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'skrisk.db'}")
    await init_db(session_factory)
    repository = SkillRepository(session_factory)
    spool = AnalysisSpool(tmp_path / "archive")

    repo_id = await repository.upsert_skill_repo(
        publisher="tul-sh",
        repo="skills",
        source_url="https://github.com/tul-sh/skills",
        registry_rank=None,
    )
    (tmp_path / "mirrors" / "tul-sh" / "skills" / ".git").mkdir(parents=True)

    async def fake_analyze_candidate(self, loop, executor, candidate):
        return candidate, _sample_checkout(), None

    monkeypatch.setattr(
        "skrisk.services.analysis_spool.AnalysisSpoolProducerService._analyze_candidate",
        fake_analyze_candidate,
    )

    service = AnalysisSpoolProducerService(
        session_factory=session_factory,
        mirror_root=tmp_path / "mirrors",
        spool=spool,
    )
    summary = await service.run_once(limit_repos=1, workers=1, continuous=False)

    detail = await repository.get_skill_detail(
        publisher="tul-sh",
        repo="skills",
        skill_slug="compact-skill",
    )

    assert summary["repos_spooled"] == 1
    assert summary["skills_analyzed"] == 1
    assert len(spool.list_pending_artifacts()) == 1
    assert detail is None
