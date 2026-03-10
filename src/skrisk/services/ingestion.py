"""Ingestion helpers that turn a local checkout into persisted snapshots."""

from __future__ import annotations

from pathlib import Path

from skrisk.analysis.analyzer import SkillAnalyzer
from skrisk.collectors.github import compute_folder_hash, discover_skills_in_checkout, load_skill_files
from skrisk.services.repo_analysis import AnalyzedCheckout, AnalyzedSkill
from skrisk.storage.repository import SkillRepository


async def ingest_local_checkout(
    *,
    repository: SkillRepository,
    publisher: str,
    repo: str,
    source_url: str,
    checkout_root: Path,
    commit_sha: str,
    default_branch: str,
    registry_urls: dict[str, str] | None = None,
) -> None:
    """Discover and persist skills from a checked-out repository."""
    analyzed_checkout = _analyze_checkout_from_directory(
        checkout_root=checkout_root,
        publisher=publisher,
        repo=repo,
        commit_sha=commit_sha,
        default_branch=default_branch,
    )
    await persist_analyzed_checkout(
        repository=repository,
        publisher=publisher,
        repo=repo,
        source_url=source_url,
        analyzed_checkout=analyzed_checkout,
        registry_urls=registry_urls or {},
    )


async def persist_analyzed_checkout(
    *,
    repository: SkillRepository,
    publisher: str,
    repo: str,
    source_url: str,
    analyzed_checkout: AnalyzedCheckout,
    registry_urls: dict[str, str],
    repo_timeout_seconds: int | None = None,
) -> None:
    canonical_registry_urls = {
        analyzed_skill.skill_slug: registry_urls.get(
            analyzed_skill.skill_slug,
            _repo_discovered_skill_url(
                publisher=publisher,
                repo=repo,
                commit_sha=analyzed_checkout.commit_sha,
                relative_path=analyzed_skill.relative_path,
            ),
        )
        for analyzed_skill in analyzed_checkout.skills
    }
    await repository.persist_repo_analysis(
        publisher=publisher,
        repo=repo,
        source_url=source_url,
        analyzed_checkout=analyzed_checkout,
        registry_urls=canonical_registry_urls,
        statement_timeout_ms=(
            int(repo_timeout_seconds * 1000) if repo_timeout_seconds is not None else None
        ),
    )


def _analyze_checkout_from_directory(
    *,
    checkout_root: Path,
    publisher: str,
    repo: str,
    commit_sha: str,
    default_branch: str,
) -> AnalyzedCheckout:
    analyzer = SkillAnalyzer()
    discovered_skills = []
    seen_slugs: set[str] = set()
    for discovered in discover_skills_in_checkout(checkout_root):
        if discovered.slug in seen_slugs:
            continue
        seen_slugs.add(discovered.slug)
        discovered_skills.append(discovered)
    analyzed_skills: list[AnalyzedSkill] = []
    for discovered in discovered_skills:
        files = load_skill_files(checkout_root / discovered.relative_path)
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


def _repo_discovered_skill_url(
    *,
    publisher: str,
    repo: str,
    commit_sha: str,
    relative_path: str,
) -> str:
    return f"https://github.com/{publisher}/{repo}/tree/{commit_sha}/{relative_path}"
