"""Repo-first analysis for already-mirrored repositories."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

from skrisk.analysis.analyzer import RiskReport, SkillAnalyzer
from skrisk.collectors.github import compute_folder_hash, discover_skills_in_checkout, load_skill_files
from skrisk.storage.repository import SkillRepository


@dataclass(slots=True)
class AnalyzedSkill:
    skill_slug: str
    relative_path: str
    folder_hash: str
    skill_text: str
    referenced_files: list[str]
    report: RiskReport


@dataclass(slots=True)
class AnalyzedCheckout:
    publisher: str
    repo: str
    checkout_root: str
    commit_sha: str
    default_branch: str
    discovered_skill_count: int
    skills: list[AnalyzedSkill]


def default_worker_count() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, int(cpu_count * 0.8))


def analyze_checkout(*, checkout_root: Path, publisher: str, repo: str) -> AnalyzedCheckout:
    analyzer = SkillAnalyzer()
    commit_sha, default_branch = _checkout_metadata(checkout_root)
    discovered_skills = _dedupe_discovered_skills(discover_skills_in_checkout(checkout_root))
    analyzed_skills: list[AnalyzedSkill] = []

    for discovered in discovered_skills:
        skill_root = checkout_root / discovered.relative_path
        files = load_skill_files(skill_root)
        report = analyzer.analyze_skill(
            publisher=publisher,
            repo=repo,
            skill_slug=discovered.slug,
            files=files,
        )
        analyzed_skills.append(
            AnalyzedSkill(
                skill_slug=discovered.slug,
                relative_path=discovered.relative_path,
                folder_hash=compute_folder_hash(files),
                skill_text=files.get("SKILL.md", ""),
                referenced_files=sorted(files),
                report=report,
            )
        )

    return AnalyzedCheckout(
        publisher=publisher,
        repo=repo,
        checkout_root=checkout_root.as_posix(),
        commit_sha=commit_sha,
        default_branch=default_branch,
        discovered_skill_count=len(discovered_skills),
        skills=analyzed_skills,
    )


def _dedupe_discovered_skills(discovered_skills):
    unique_skills = []
    seen_slugs: set[str] = set()
    for discovered in discovered_skills:
        if discovered.slug in seen_slugs:
            continue
        seen_slugs.add(discovered.slug)
        unique_skills.append(discovered)
    return unique_skills


class MirroredRepoAnalysisService:
    """Analyze mirrored repositories using process-based parallelism."""

    _MISSING_MIRROR_RETRY_HOURS = 24
    _FAILED_ANALYSIS_RETRY_HOURS = 6

    def __init__(self, *, session_factory, mirror_root: Path, progress_callback=None) -> None:
        self._repository = SkillRepository(session_factory)
        self._mirror_root = mirror_root
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
            "repos_analyzed": 0,
            "repos_missing_mirror": 0,
            "repos_failed": 0,
            "skills_analyzed": 0,
        }

        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=workers) as executor:
            while True:
                due_repos = await self._repository.list_due_repos()
                candidates, missing_mirror_rows = self._candidate_repos(
                    due_repos,
                    limit_repos=limit_repos,
                )
                if missing_mirror_rows:
                    await self._defer_repos(
                        rows=missing_mirror_rows,
                        retry_after_hours=self._MISSING_MIRROR_RETRY_HOURS,
                    )
                if not candidates:
                    summary["repos_missing_mirror"] += len(missing_mirror_rows)
                    if not continuous or not due_repos:
                        break
                    await asyncio.sleep(2.0)
                    continue

                summary["repos_requested"] += len(candidates)
                summary["repos_missing_mirror"] += len(missing_mirror_rows)
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
                        await self._repository.defer_repo_scan(
                            repo_id=int(candidate["id"]),
                            retry_after_hours=self._FAILED_ANALYSIS_RETRY_HOURS,
                        )
                        summary["repos_failed"] += 1
                        self._report_progress(
                            repos_requested=summary["repos_requested"],
                            repos_analyzed=summary["repos_analyzed"],
                            repos_failed=summary["repos_failed"],
                            skills_analyzed=summary["skills_analyzed"],
                            last_repo=f"{candidate['publisher']}/{candidate['repo']}",
                            batch_completed=completed_in_batch,
                            batch_size=len(candidates),
                        )
                        continue
                    await self._persist_candidate(candidate=candidate, analyzed_checkout=analyzed_checkout)
                    summary["repos_analyzed"] += 1
                    summary["skills_analyzed"] += len(analyzed_checkout.skills)
                    self._report_progress(
                        repos_requested=summary["repos_requested"],
                        repos_analyzed=summary["repos_analyzed"],
                        repos_failed=summary["repos_failed"],
                        skills_analyzed=summary["skills_analyzed"],
                        last_repo=f"{candidate['publisher']}/{candidate['repo']}",
                        batch_completed=completed_in_batch,
                        batch_size=len(candidates),
                    )

                if not continuous:
                    break

        return summary

    def _candidate_repos(self, due_repos: list[dict], *, limit_repos: int) -> tuple[list[dict], list[dict]]:
        candidates: list[dict] = []
        missing_mirror_rows: list[dict] = []
        for row in due_repos:
            checkout_path = self._mirror_root / row["publisher"] / row["repo"]
            if not (checkout_path / ".git").exists():
                missing_mirror_rows.append(row)
                continue
            candidate = dict(row)
            candidate["checkout_path"] = checkout_path
            candidates.append(candidate)
            if len(candidates) >= limit_repos:
                break
        return candidates, missing_mirror_rows

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

    async def _defer_repos(self, *, rows: list[dict], retry_after_hours: int) -> None:
        for row in rows:
            await self._repository.defer_repo_scan(
                repo_id=int(row["id"]),
                retry_after_hours=retry_after_hours,
            )

    async def _persist_candidate(self, *, candidate: dict, analyzed_checkout: AnalyzedCheckout) -> None:
        from skrisk.services.ingestion import persist_analyzed_checkout

        registry_entries = await self._repository.list_registry_entries_for_repo_ids([candidate["id"]])
        registry_urls = {
            row["skill_slug"]: row["registry_url"]
            for row in registry_entries
        }
        await persist_analyzed_checkout(
            repository=self._repository,
            publisher=candidate["publisher"],
            repo=candidate["repo"],
            source_url=candidate["source_url"],
            analyzed_checkout=analyzed_checkout,
            registry_urls=registry_urls,
        )
        await self._repository.mark_repo_scanned(repo_id=candidate["id"])

    def _report_progress(
        self,
        *,
        repos_requested: int,
        repos_analyzed: int,
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
                    "repos_analyzed": repos_analyzed,
                    "repos_failed": repos_failed,
                    "skills_analyzed": skills_analyzed,
                    "last_repo": last_repo,
                    "batch_completed": batch_completed,
                    "batch_size": batch_size,
                }
            )


def _analyze_checkout_for_pool(publisher: str, repo: str, checkout_root: str) -> AnalyzedCheckout:
    return analyze_checkout(
        checkout_root=Path(checkout_root),
        publisher=publisher,
        repo=repo,
    )


def _checkout_metadata(checkout_root: Path) -> tuple[str, str]:
    commit_sha = (
        subprocess.run(
            ["git", "-C", str(checkout_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    current_branch = (
        subprocess.run(
            ["git", "-C", str(checkout_root), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    if current_branch != "HEAD":
        return commit_sha, current_branch

    remote_head = (
        subprocess.run(
            ["git", "-C", str(checkout_root), "symbolic-ref", "refs/remotes/origin/HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    return commit_sha, remote_head.rsplit("/", maxsplit=1)[-1]
