"""File-backed analysis spool for producer/consumer analysis pipelines."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import uuid

from skrisk.analysis.analyzer import ExtractedIndicator, Finding, RiskReport
from skrisk.services.ingestion import persist_analyzed_checkout
from skrisk.services.repo_analysis import (
    AnalyzedCheckout,
    AnalyzedSkill,
    _analyze_checkout_for_pool,
)
from skrisk.storage.repository import SkillRepository


@dataclass(slots=True, frozen=True)
class AnalysisClaim:
    repo_id: int
    publisher: str
    repo: str
    source_url: str
    claim_token: str
    claimed_at: str


class AnalysisSpool:
    def __init__(self, archive_root: Path) -> None:
        self._base_dir = archive_root / "analysis-spool"
        self._claims_dir = self._base_dir / "claims"
        self._pending_dir = self._base_dir / "pending"
        self._claims_dir.mkdir(parents=True, exist_ok=True)
        self._pending_dir.mkdir(parents=True, exist_ok=True)

    def claim_repo(self, candidate: dict) -> AnalysisClaim | None:
        claim = AnalysisClaim(
            repo_id=int(candidate["id"]),
            publisher=candidate["publisher"],
            repo=candidate["repo"],
            source_url=candidate["source_url"],
            claim_token=uuid.uuid4().hex,
            claimed_at=datetime.now(UTC).isoformat(),
        )
        claim_path = self._claim_path(claim.repo_id)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(claim_path, flags, 0o644)
        except FileExistsError:
            return None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(asdict(claim), handle, sort_keys=True)
        return claim

    def is_claimed(self, repo_id: int) -> bool:
        return self._claim_path(repo_id).exists()

    def release_claim(self, claim: AnalysisClaim) -> None:
        self._claim_path(claim.repo_id).unlink(missing_ok=True)

    def write_artifact(self, *, claim: AnalysisClaim, analyzed_checkout: AnalyzedCheckout) -> Path:
        artifact_path = self._artifact_path(claim)
        payload = {
            "claim": asdict(claim),
            "analyzed_checkout": _serialize_checkout(analyzed_checkout),
        }
        artifact_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return artifact_path

    def list_pending_artifacts(self) -> list[Path]:
        return sorted(self._pending_dir.glob("*.json"))

    def load_artifact(self, artifact_path: Path) -> tuple[AnalysisClaim, AnalyzedCheckout]:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        claim = AnalysisClaim(**payload["claim"])
        analyzed_checkout = _deserialize_checkout(payload["analyzed_checkout"])
        return claim, analyzed_checkout

    def complete_artifact(self, *, artifact_path: Path, claim: AnalysisClaim) -> None:
        artifact_path.unlink(missing_ok=True)
        self.release_claim(claim)

    def _claim_path(self, repo_id: int) -> Path:
        return self._claims_dir / f"{repo_id}.json"

    def _artifact_path(self, claim: AnalysisClaim) -> Path:
        return self._pending_dir / f"{claim.repo_id}-{claim.claim_token}.json"


class AnalysisSpoolIngestService:
    def __init__(self, *, session_factory, spool: AnalysisSpool) -> None:
        self._repository = SkillRepository(session_factory)
        self._spool = spool

    async def run_once(
        self,
        *,
        limit_artifacts: int,
        continuous: bool,
        poll_interval_seconds: float = 2.0,
        max_idle_polls: int | None = None,
    ) -> dict[str, int]:
        summary = {
            "artifacts_seen": 0,
            "artifacts_ingested": 0,
            "artifacts_failed": 0,
            "skills_ingested": 0,
        }
        idle_polls = 0

        while True:
            artifacts = self._spool.list_pending_artifacts()[:limit_artifacts]
            if not artifacts:
                if not continuous:
                    break
                idle_polls += 1
                if max_idle_polls is not None and idle_polls >= max_idle_polls:
                    break
                await asyncio.sleep(poll_interval_seconds)
                continue
            idle_polls = 0
            summary["artifacts_seen"] += len(artifacts)
            for artifact_path in artifacts:
                try:
                    claim, analyzed_checkout = self._spool.load_artifact(artifact_path)
                    registry_entries = await self._repository.list_registry_entries_for_repo_ids(
                        [claim.repo_id]
                    )
                    registry_urls = {
                        row["skill_slug"]: row["registry_url"]
                        for row in registry_entries
                    }
                    await persist_analyzed_checkout(
                        repository=self._repository,
                        publisher=claim.publisher,
                        repo=claim.repo,
                        source_url=claim.source_url,
                        analyzed_checkout=analyzed_checkout,
                        registry_urls=registry_urls,
                    )
                    self._spool.complete_artifact(
                        artifact_path=artifact_path,
                        claim=claim,
                    )
                    summary["artifacts_ingested"] += 1
                    summary["skills_ingested"] += len(analyzed_checkout.skills)
                except Exception:
                    summary["artifacts_failed"] += 1
            if not continuous:
                break
        return summary


class AnalysisSpoolProducerService:
    def __init__(self, *, session_factory, mirror_root: Path, spool: AnalysisSpool, progress_callback=None) -> None:
        self._repository = SkillRepository(session_factory)
        self._mirror_root = mirror_root
        self._spool = spool
        self._progress_callback = progress_callback

    async def run_once(
        self,
        *,
        limit_repos: int,
        workers: int,
        continuous: bool,
    ) -> dict[str, int]:
        summary = {
            "repos_requested": 0,
            "repos_spooled": 0,
            "repos_failed": 0,
            "repos_missing_mirror": 0,
            "skills_analyzed": 0,
        }

        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=workers) as executor:
            while True:
                due_repos = await self._repository.list_due_repos()
                candidates, missing_mirror_count = self._candidate_repos(due_repos, limit_repos=limit_repos)
                if not candidates:
                    summary["repos_missing_mirror"] += missing_mirror_count
                    break

                summary["repos_requested"] += len(candidates)
                summary["repos_missing_mirror"] += missing_mirror_count
                tasks = [
                    asyncio.create_task(
                        self._analyze_candidate(loop, executor, candidate)
                    )
                    for candidate in candidates
                ]
                completed_in_batch = 0
                for task in asyncio.as_completed(tasks):
                    candidate, analyzed_checkout, error = await task
                    completed_in_batch += 1
                    if error is not None:
                        self._spool.release_claim(candidate["claim"])
                        summary["repos_failed"] += 1
                        self._report_progress(
                            repos_requested=summary["repos_requested"],
                            repos_spooled=summary["repos_spooled"],
                            repos_failed=summary["repos_failed"],
                            skills_analyzed=summary["skills_analyzed"],
                            last_repo=f"{candidate['publisher']}/{candidate['repo']}",
                            batch_completed=completed_in_batch,
                            batch_size=len(candidates),
                        )
                        continue
                    self._spool.write_artifact(
                        claim=candidate["claim"],
                        analyzed_checkout=analyzed_checkout,
                    )
                    summary["repos_spooled"] += 1
                    summary["skills_analyzed"] += len(analyzed_checkout.skills)
                    self._report_progress(
                        repos_requested=summary["repos_requested"],
                        repos_spooled=summary["repos_spooled"],
                        repos_failed=summary["repos_failed"],
                        skills_analyzed=summary["skills_analyzed"],
                        last_repo=f"{candidate['publisher']}/{candidate['repo']}",
                        batch_completed=completed_in_batch,
                        batch_size=len(candidates),
                    )

                if not continuous:
                    break
        return summary

    def _candidate_repos(self, due_repos: list[dict], *, limit_repos: int) -> tuple[list[dict], int]:
        candidates: list[dict] = []
        missing_mirror_count = 0
        for row in due_repos:
            checkout_path = self._mirror_root / row["publisher"] / row["repo"]
            if not (checkout_path / ".git").exists():
                missing_mirror_count += 1
                continue
            claim = self._spool.claim_repo(row)
            if claim is None:
                continue
            candidate = dict(row)
            candidate["claim"] = claim
            candidate["checkout_path"] = checkout_path
            candidates.append(candidate)
            if len(candidates) >= limit_repos:
                break
        return candidates, missing_mirror_count

    async def _analyze_candidate(self, loop, executor, candidate: dict) -> tuple[dict, AnalyzedCheckout | None, str | None]:
        try:
            analyzed = await loop.run_in_executor(
                executor,
                _analyze_checkout_for_pool,
                candidate["publisher"],
                candidate["repo"],
                candidate["checkout_path"].as_posix(),
            )
            return candidate, analyzed, None
        except Exception as exc:
            return candidate, None, repr(exc)

    def _report_progress(
        self,
        *,
        repos_requested: int,
        repos_spooled: int,
        repos_failed: int,
        skills_analyzed: int,
        last_repo: str,
        batch_completed: int,
        batch_size: int,
    ) -> None:
        if self._progress_callback is None:
            return
        if batch_completed <= 5 or batch_completed % 10 == 0:
            self._progress_callback(
                {
                    "repos_requested": repos_requested,
                    "repos_spooled": repos_spooled,
                    "repos_failed": repos_failed,
                    "skills_analyzed": skills_analyzed,
                    "last_repo": last_repo,
                    "batch_completed": batch_completed,
                    "batch_size": batch_size,
                }
            )


def _serialize_checkout(analyzed_checkout: AnalyzedCheckout) -> dict:
    return asdict(analyzed_checkout)


def _deserialize_checkout(payload: dict) -> AnalyzedCheckout:
    return AnalyzedCheckout(
        publisher=payload["publisher"],
        repo=payload["repo"],
        checkout_root=payload["checkout_root"],
        commit_sha=payload["commit_sha"],
        default_branch=payload["default_branch"],
        discovered_skill_count=payload["discovered_skill_count"],
        skills=[
            AnalyzedSkill(
                skill_slug=skill["skill_slug"],
                relative_path=skill["relative_path"],
                folder_hash=skill["folder_hash"],
                skill_text=skill["skill_text"],
                referenced_files=skill["referenced_files"],
                report=_deserialize_risk_report(skill["report"]),
            )
            for skill in payload["skills"]
        ],
    )


def _deserialize_risk_report(payload: dict) -> RiskReport:
    return RiskReport(
        publisher=payload["publisher"],
        repo=payload["repo"],
        skill_slug=payload["skill_slug"],
        severity=payload["severity"],
        score=payload["score"],
        behavior_score=payload["behavior_score"],
        findings=[Finding(**finding) for finding in payload.get("findings", [])],
        domains=payload.get("domains", []),
        indicators=[ExtractedIndicator(**indicator) for indicator in payload.get("indicators", [])],
    )
