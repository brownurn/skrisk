"""Registry synchronization helpers for SK Risk."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from skrisk.analysis.analyzer import SkillAnalyzer
from skrisk.collectors.github import (
    compute_folder_hash,
    discover_skills_in_checkout,
    load_skill_files,
    mirror_repo_snapshot,
)
from skrisk.collectors.skills_sh import (
    AuditRow,
    SkillSitemapEntry,
    extract_audit_rows,
    parse_directory_page,
)
from skrisk.storage.repository import SkillRepository


SkillLoader = Callable[[SkillSitemapEntry], Awaitable[tuple[str, dict[str, str]]]]


class _RegistryEntryBatch(list[SkillSitemapEntry]):
    def __init__(
        self,
        *,
        total_skills_reported: int | None = None,
        pages_fetched: int = 0,
    ) -> None:
        super().__init__()
        self.total_skills_reported = total_skills_reported
        self.pages_fetched = pages_fetched


@dataclass(slots=True, frozen=True)
class RegistrySnapshot:
    sitemap_entries: list[SkillSitemapEntry]
    audit_rows: list[AuditRow]
    total_skills: int | None = None
    pages_fetched: int = 0


class SkillsShClient:
    """HTTP client for fetching the public registry surfaces."""

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    _DEFAULT_RETRY_DELAY_SECONDS = 30.0
    _MAX_RETRIES = 6

    def __init__(self, base_url: str = "https://skills.sh") -> None:
        self._base_url = base_url.rstrip("/")

    async def fetch_snapshot(self, client: httpx.AsyncClient | None = None) -> RegistrySnapshot:
        if client is None:
            async with httpx.AsyncClient(timeout=30.0) as managed_client:
                return await self.fetch_snapshot(managed_client)

        audits_response = await client.get(f"{self._base_url}/audits")
        audits_response.raise_for_status()
        entries = _RegistryEntryBatch()
        seen: set[tuple[str, str, str]] = set()
        page = 0
        page_count = 0
        total_skills: int | None = None

        while True:
            directory_response = await self._get_with_retry(
                client,
                f"{self._base_url}/api/skills/all-time/{page}",
            )
            directory_page = parse_directory_page(directory_response.json(), base_url=self._base_url)
            total_skills = directory_page.total
            page_count += 1

            for entry in directory_page.entries:
                key = (entry.publisher, entry.repo, entry.skill_slug)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(entry)

            if not directory_page.has_more:
                break
            page += 1

        entries.total_skills_reported = total_skills
        entries.pages_fetched = page_count

        return RegistrySnapshot(
            sitemap_entries=entries,
            audit_rows=extract_audit_rows(audits_response.text),
            total_skills=total_skills,
            pages_fetched=page_count,
        )

    async def _get_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> httpx.Response:
        for attempt in range(self._MAX_RETRIES + 1):
            response = await client.get(url)
            if response.status_code not in self._RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response

            if attempt == self._MAX_RETRIES:
                response.raise_for_status()

            await asyncio.sleep(self._retry_delay_seconds(response))

        raise RuntimeError(f"Exceeded retry budget for {url}")

    def _retry_delay_seconds(self, response: httpx.Response) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return self._DEFAULT_RETRY_DELAY_SECONDS


class GitHubSkillLoader:
    """Load skill files from a mirrored GitHub repository."""

    def __init__(self, mirror_root: Path) -> None:
        self._mirror_root = mirror_root

    async def __call__(self, entry: SkillSitemapEntry) -> tuple[str, dict[str, str]]:
        checkout_path = self._mirror_root / entry.publisher / entry.repo
        source_url = f"https://github.com/{entry.publisher}/{entry.repo}"
        mirrored_path, commit_sha = await asyncio.to_thread(
            mirror_repo_snapshot,
            source_url=source_url,
            destination=checkout_path,
        )
        discovered = discover_skills_in_checkout(mirrored_path)
        matched = next((skill for skill in discovered if skill.slug == entry.skill_slug), None)
        if matched is None:
            raise FileNotFoundError(
                f"Could not find skill '{entry.skill_slug}' in mirrored repo {source_url}"
            )
        files = load_skill_files(mirrored_path / matched.relative_path)
        return commit_sha, files


class RegistrySyncService:
    """Sync a registry snapshot into the local SK Risk database."""

    def __init__(self, *, session_factory, analyzer: SkillAnalyzer) -> None:
        self._repository = SkillRepository(session_factory)
        self._analyzer = analyzer

    async def seed_registry_snapshot(
        self,
        *,
        sitemap_entries: list[SkillSitemapEntry],
        audit_rows: list[AuditRow],
        total_skills_reported: int | None = None,
        pages_fetched: int | None = None,
        observed_at: datetime | None = None,
    ) -> dict[str, int]:
        _, _, seen_repos, _, unique_skill_keys = await self._seed_registry_metadata(
            sitemap_entries=sitemap_entries,
            audit_rows=audit_rows,
            record_directory_fetch=True,
            total_skills_reported=total_skills_reported,
            pages_fetched=pages_fetched,
            observed_at=observed_at,
        )
        return {
            "repos_seeded": len(seen_repos),
            "skills_seeded": len(unique_skill_keys),
        }

    async def ingest_registry_snapshot(
        self,
        *,
        sitemap_entries: list[SkillSitemapEntry],
        audit_rows: list[AuditRow],
        skill_loader: SkillLoader,
        record_directory_fetch: bool = True,
        total_skills_reported: int | None = None,
        pages_fetched: int | None = None,
        observed_at: datetime | None = None,
        registry_observation_context_by_skill: dict[
            tuple[str, str, str],
            dict[str, object],
        ]
        | None = None,
    ) -> dict[str, int]:
        audit_map, repo_groups, seen_repos, repo_ids_by_key, _ = await self._seed_registry_metadata(
            sitemap_entries=sitemap_entries,
            audit_rows=audit_rows,
            record_directory_fetch=record_directory_fetch,
            total_skills_reported=total_skills_reported,
            pages_fetched=pages_fetched,
            observed_at=observed_at,
        )
        skills_succeeded = 0
        skills_failed = 0

        for (publisher, repo), repo_entries in repo_groups.items():
            repo_id = repo_ids_by_key[(publisher, repo)]

            repo_snapshot_id: int | None = None
            repo_commit_sha: str | None = None

            for entry in repo_entries:
                audit_row = audit_map.get((entry.publisher, entry.repo, entry.skill_slug))
                try:
                    commit_sha, files = await skill_loader(entry)
                except Exception:
                    skills_failed += 1
                    continue

                if repo_snapshot_id is None:
                    repo_snapshot_id = await self._repository.record_repo_snapshot(
                        repo_id=repo_id,
                        commit_sha=commit_sha,
                        default_branch="main",
                        discovered_skill_count=len(repo_entries),
                    )
                    repo_commit_sha = commit_sha

                skill_id = await self._repository.upsert_skill(
                    repo_id=repo_id,
                    skill_slug=entry.skill_slug,
                    title=audit_row.name if audit_row is not None else entry.skill_slug,
                    relative_path=f"skills/{entry.skill_slug}",
                    registry_url=entry.url,
                )

                report = self._analyzer.analyze_skill(
                    publisher=entry.publisher,
                    repo=entry.repo,
                    skill_slug=entry.skill_slug,
                    files=files,
                )
                linked_indicators, indicator_matches = await _prepare_indicator_context(
                    repository=self._repository,
                    report=report,
                )
                previous_indicator_ids = await self._repository.get_latest_indicator_ids_for_skill(
                    skill_id=skill_id
                )
                risk_report = self._analyzer.build_risk_report(
                    report=report,
                    indicator_matches=indicator_matches,
                )
                skill_snapshot_id = await self._repository.record_skill_snapshot(
                    skill_id=skill_id,
                    repo_snapshot_id=repo_snapshot_id,
                    folder_hash=compute_folder_hash(files),
                    version_label=f"main@{repo_commit_sha or commit_sha}",
                    skill_text=files.get("SKILL.md", ""),
                    referenced_files=sorted(files),
                    extracted_domains=report.domains,
                    risk_report=risk_report,
                )
                observation_context = registry_observation_context_by_skill or {}
                scan_attribution_context = observation_context.get(
                    (entry.publisher, entry.repo, entry.skill_slug)
                )
                if scan_attribution_context is None:
                    scan_attribution_context = await self._repository.get_skill_registry_observation_context(
                        skill_id=skill_id
                    )
                scan_observed_at = _coerce_datetime_utc(
                    (scan_attribution_context or {}).get("observed_at")
                ) or datetime.now(UTC)
                await self._repository.record_skill_registry_observation(
                    skill_id=skill_id,
                    registry_sync_run_id=(scan_attribution_context or {}).get(
                        "registry_sync_run_id"
                    ),
                    repo_snapshot_id=repo_snapshot_id,
                    observed_at=scan_observed_at,
                    weekly_installs=entry.weekly_installs,
                    registry_rank=(
                        audit_row.rank
                        if audit_row is not None
                        else (scan_attribution_context or {}).get("registry_rank")
                    ),
                    observation_kind="scan_attribution",
                    raw_payload={
                        "publisher": entry.publisher,
                        "repo": entry.repo,
                        "skill_slug": entry.skill_slug,
                        "registry_url": entry.url,
                        "weekly_installs": entry.weekly_installs,
                    },
                )
                await _record_skill_indicator_links(
                    repository=self._repository,
                    skill_snapshot_id=skill_snapshot_id,
                    linked_indicators=linked_indicators,
                    previous_indicator_ids=previous_indicator_ids,
                )
                await _enqueue_vt_candidates(
                    repository=self._repository,
                    linked_indicators=linked_indicators,
                    risk_report=risk_report,
                )

                if audit_row is not None:
                    for partner in audit_row.partners.values():
                        if partner.verdict is None and partner.alert_count == 0:
                            continue
                        await self._repository.record_external_verdict(
                            skill_id=skill_id,
                            partner=partner.partner,
                            verdict=partner.verdict or "ALERTS",
                            summary=partner.summary,
                            analyzed_at=partner.analyzed_at,
                        )
                skills_succeeded += 1

            await self._repository.mark_repo_scanned(repo_id=repo_id)

        return {
            "repos_seen": len(seen_repos),
            "skills_seen": skills_succeeded,
            "skills_failed": skills_failed,
        }

    async def _seed_registry_metadata(
        self,
        *,
        sitemap_entries: list[SkillSitemapEntry],
        audit_rows: list[AuditRow],
        record_directory_fetch: bool,
        total_skills_reported: int | None = None,
        pages_fetched: int | None = None,
        observed_at: datetime | None = None,
    ) -> tuple[
        dict[tuple[str, str, str], AuditRow],
        dict[tuple[str, str], list[SkillSitemapEntry]],
        set[tuple[str, str]],
        dict[tuple[str, str], int],
        set[tuple[str, str, str]],
    ]:
        audit_map = {
            (row.publisher, row.repo, row.skill_slug): row
            for row in audit_rows
        }
        repo_groups: dict[tuple[str, str], list[SkillSitemapEntry]] = {}
        for entry in sitemap_entries:
            repo_groups.setdefault((entry.publisher, entry.repo), []).append(entry)

        seen_repos: set[tuple[str, str]] = set()
        repo_ids_by_key: dict[tuple[str, str], int] = {}
        unique_skill_keys = {
            (entry.publisher, entry.repo, entry.skill_slug)
            for entry in sitemap_entries
        }
        registry_sync_run_id: int | None = None
        resolved_total_skills_reported, resolved_pages_fetched = _resolve_registry_provenance(
            sitemap_entries=sitemap_entries,
            total_skills_reported=total_skills_reported,
            pages_fetched=pages_fetched,
        )
        observed_at = observed_at or datetime.now(UTC)

        if record_directory_fetch:
            registry_sync_run_id = await self._repository.record_registry_sync_run(
                source="skills.sh",
                view="all-time",
                total_skills_reported=resolved_total_skills_reported,
                pages_fetched=resolved_pages_fetched,
                success=True,
            )

        for (publisher, repo), repo_entries in repo_groups.items():
            ranked_rows = [
                audit_map[(publisher, repo, entry.skill_slug)].rank
                for entry in repo_entries
                if (publisher, repo, entry.skill_slug) in audit_map
            ]
            repo_id = await self._repository.upsert_skill_repo(
                publisher=publisher,
                repo=repo,
                source_url=f"https://github.com/{publisher}/{repo}",
                registry_rank=min(ranked_rows) if ranked_rows else None,
            )
            repo_ids_by_key[(publisher, repo)] = repo_id
            seen_repos.add((publisher, repo))

            for entry in repo_entries:
                audit_row = audit_map.get((entry.publisher, entry.repo, entry.skill_slug))
                skill_id = await self._repository.upsert_skill(
                    repo_id=repo_id,
                    skill_slug=entry.skill_slug,
                    title=audit_row.name if audit_row is not None else entry.skill_slug,
                    relative_path=f"registry/{entry.skill_slug}",
                    registry_url=entry.url,
                )
                if not record_directory_fetch:
                    continue
                await self._repository.record_skill_registry_observation(
                    skill_id=skill_id,
                    registry_sync_run_id=registry_sync_run_id,
                    repo_snapshot_id=None,
                    observed_at=observed_at,
                    weekly_installs=entry.weekly_installs,
                    registry_rank=audit_row.rank if audit_row is not None else None,
                    observation_kind="directory_fetch",
                    raw_payload={
                        "publisher": entry.publisher,
                        "repo": entry.repo,
                        "skill_slug": entry.skill_slug,
                        "registry_url": entry.url,
                        "weekly_installs": entry.weekly_installs,
                    },
                )

        return audit_map, repo_groups, seen_repos, repo_ids_by_key, unique_skill_keys


def _resolve_registry_provenance(
    *,
    sitemap_entries: list[SkillSitemapEntry],
    total_skills_reported: int | None,
    pages_fetched: int | None,
) -> tuple[int | None, int]:
    resolved_total_skills_reported = total_skills_reported
    if resolved_total_skills_reported is None:
        resolved_total_skills_reported = getattr(
            sitemap_entries,
            "total_skills_reported",
            None,
        )

    resolved_pages_fetched = pages_fetched
    if resolved_pages_fetched is None:
        resolved_pages_fetched = getattr(sitemap_entries, "pages_fetched", 0)

    return resolved_total_skills_reported, resolved_pages_fetched or 0


def _coerce_datetime_utc(value: object | None) -> datetime | None:
    if value is None or not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


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
