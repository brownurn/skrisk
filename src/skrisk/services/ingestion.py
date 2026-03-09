"""Ingestion helpers that turn a local checkout into persisted snapshots."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from skrisk.analysis.analyzer import SkillAnalyzer
from skrisk.collectors.github import discover_skills_in_checkout, load_skill_files
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
) -> None:
    repo_id = await repository.upsert_skill_repo(
        publisher=publisher,
        repo=repo,
        source_url=source_url,
        registry_rank=None,
    )
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha=analyzed_checkout.commit_sha,
        default_branch=analyzed_checkout.default_branch,
        discovered_skill_count=analyzed_checkout.discovered_skill_count,
    )

    analyzer = SkillAnalyzer()
    for analyzed_skill in analyzed_checkout.skills:
        skill_id = await repository.upsert_skill(
            repo_id=repo_id,
            skill_slug=analyzed_skill.skill_slug,
            title=analyzed_skill.skill_slug,
            relative_path=analyzed_skill.relative_path,
            registry_url=registry_urls.get(
                analyzed_skill.skill_slug,
                _repo_discovered_skill_url(
                    publisher=publisher,
                    repo=repo,
                    commit_sha=analyzed_checkout.commit_sha,
                    relative_path=analyzed_skill.relative_path,
                ),
            ),
        )
        linked_indicators, indicator_matches = await _prepare_indicator_context(
            repository=repository,
            report=analyzed_skill.report,
        )
        previous_indicator_ids = await repository.get_latest_indicator_ids_for_skill(skill_id=skill_id)
        risk_report = analyzer.build_risk_report(
            report=analyzed_skill.report,
            indicator_matches=indicator_matches,
        )
        skill_snapshot_id = await repository.record_skill_snapshot(
            skill_id=skill_id,
            repo_snapshot_id=repo_snapshot_id,
            folder_hash=_folder_hash(analyzed_skill.files),
            version_label=f"{analyzed_checkout.default_branch}@{analyzed_checkout.commit_sha}",
            skill_text=analyzed_skill.files.get("SKILL.md", ""),
            referenced_files=sorted(analyzed_skill.files),
            extracted_domains=analyzed_skill.report.domains,
            risk_report=risk_report,
        )
        await _record_skill_indicator_links(
            repository=repository,
            skill_snapshot_id=skill_snapshot_id,
            linked_indicators=linked_indicators,
            previous_indicator_ids=previous_indicator_ids,
        )
        await _enqueue_vt_candidates(
            repository=repository,
            linked_indicators=linked_indicators,
            risk_report=risk_report,
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
    discovered_skills = discover_skills_in_checkout(checkout_root)
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
                files=files,
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


def _folder_hash(files: dict[str, str]) -> str:
    digest = sha256()
    for relative_path, content in sorted(files.items()):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


async def _prepare_indicator_context(
    *,
    repository: SkillRepository,
    report,
) -> tuple[list[tuple[object, int]], list[dict]]:
    linked_indicators: list[tuple[object, int]] = []
    indicator_matches: dict[tuple[str, str], dict] = {}

    for indicator in report.indicators:
        indicator_id = await repository.upsert_indicator(
            indicator.indicator_type,
            indicator.indicator_value,
        )
        linked_indicators.append((indicator, indicator_id))
        detail = await repository.get_indicator_detail(
            indicator.indicator_type,
            indicator.indicator_value,
        )
        if detail is None or not detail["observations"]:
            continue
        key = (
            detail["indicator"]["indicator_type"],
            detail["indicator"]["normalized_value"],
        )
        indicator_matches[key] = detail

    return linked_indicators, list(indicator_matches.values())


async def _record_skill_indicator_links(
    *,
    repository: SkillRepository,
    skill_snapshot_id: int,
    linked_indicators: list[tuple[object, int]],
    previous_indicator_ids: set[int],
) -> None:
    for indicator, indicator_id in linked_indicators:
        await repository.record_skill_indicator_link(
            skill_snapshot_id=skill_snapshot_id,
            indicator_id=indicator_id,
            source_path=indicator.path,
            extraction_kind=indicator.extraction_kind,
            raw_value=indicator.raw_value,
            is_new_in_snapshot=indicator_id not in previous_indicator_ids,
        )


async def _enqueue_vt_candidates(
    *,
    repository: SkillRepository,
    linked_indicators: list[tuple[object, int]],
    risk_report: dict,
) -> None:
    if risk_report["severity"] not in {"critical", "high"}:
        return
    if risk_report["behavior_score"] < 40 and risk_report["intel_score"] <= 0:
        return

    priority = 100 if risk_report["severity"] == "critical" else 80
    seen: set[tuple[str, str]] = set()
    for indicator, _ in linked_indicators:
        if indicator.indicator_type not in {"url", "domain", "sha256"}:
            continue
        key = (indicator.indicator_type, indicator.indicator_value)
        if key in seen:
            continue
        seen.add(key)
        await repository.enqueue_vt_lookup(
            indicator_type=indicator.indicator_type,
            indicator_value=indicator.indicator_value,
            priority=priority,
            reason=f"{risk_report['severity']}-skill",
        )
