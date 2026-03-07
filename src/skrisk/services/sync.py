"""Registry synchronization helpers for SK Risk."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
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
from skrisk.collectors.skills_sh import AuditRow, SkillSitemapEntry, extract_audit_rows, parse_sitemap
from skrisk.storage.repository import SkillRepository


SkillLoader = Callable[[SkillSitemapEntry], Awaitable[tuple[str, dict[str, str]]]]


@dataclass(slots=True, frozen=True)
class RegistrySnapshot:
    sitemap_entries: list[SkillSitemapEntry]
    audit_rows: list[AuditRow]


class SkillsShClient:
    """HTTP client for fetching the public registry surfaces."""

    def __init__(self, base_url: str = "https://skills.sh") -> None:
        self._base_url = base_url.rstrip("/")

    async def fetch_snapshot(self, client: httpx.AsyncClient | None = None) -> RegistrySnapshot:
        if client is None:
            async with httpx.AsyncClient(timeout=30.0) as managed_client:
                return await self.fetch_snapshot(managed_client)

        sitemap_response = await client.get(f"{self._base_url}/sitemap.xml")
        sitemap_response.raise_for_status()
        audits_response = await client.get(f"{self._base_url}/audits")
        audits_response.raise_for_status()
        return RegistrySnapshot(
            sitemap_entries=parse_sitemap(sitemap_response.text),
            audit_rows=extract_audit_rows(audits_response.text),
        )


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

    async def ingest_registry_snapshot(
        self,
        *,
        sitemap_entries: list[SkillSitemapEntry],
        audit_rows: list[AuditRow],
        skill_loader: SkillLoader,
    ) -> dict[str, int]:
        audit_map = {
            (row.publisher, row.repo, row.skill_slug): row
            for row in audit_rows
        }
        repo_skill_counts = Counter((entry.publisher, entry.repo) for entry in sitemap_entries)
        seen_repos: set[tuple[str, str]] = set()

        for entry in sitemap_entries:
            audit_row = audit_map.get((entry.publisher, entry.repo, entry.skill_slug))
            repo_id = await self._repository.upsert_skill_repo(
                publisher=entry.publisher,
                repo=entry.repo,
                source_url=f"https://github.com/{entry.publisher}/{entry.repo}",
                registry_rank=audit_row.rank if audit_row is not None else None,
            )
            seen_repos.add((entry.publisher, entry.repo))

            commit_sha, files = await skill_loader(entry)
            repo_snapshot_id = await self._repository.record_repo_snapshot(
                repo_id=repo_id,
                commit_sha=commit_sha,
                default_branch="main",
                discovered_skill_count=repo_skill_counts[(entry.publisher, entry.repo)],
            )
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
            risk_report = {
                "severity": report.severity,
                "score": report.score,
                "categories": [finding.category for finding in report.findings],
                "domains": report.domains,
                "findings": [
                    {
                        "path": finding.path,
                        "category": finding.category,
                        "severity": finding.severity,
                        "evidence": finding.evidence,
                    }
                    for finding in report.findings
                ],
            }
            await self._repository.record_skill_snapshot(
                skill_id=skill_id,
                repo_snapshot_id=repo_snapshot_id,
                folder_hash=compute_folder_hash(files),
                version_label=f"main@{commit_sha}",
                skill_text=files.get("SKILL.md", ""),
                referenced_files=sorted(files),
                extracted_domains=report.domains,
                risk_report=risk_report,
            )

            if audit_row is None:
                await self._repository.mark_repo_scanned(repo_id=repo_id)
                continue
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
            await self._repository.mark_repo_scanned(repo_id=repo_id)

        return {
            "repos_seen": len(seen_repos),
            "skills_seen": len(sitemap_entries),
        }
