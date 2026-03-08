"""Repository methods for the initial API and ingestion flows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from skrisk.storage.models import (
    ExternalVerdict,
    Indicator,
    IndicatorEnrichment,
    IndicatorObservation,
    IntelFeedArtifact,
    IntelFeedRun,
    Skill,
    SkillIndicatorLink,
    SkillRepo,
    SkillRepoSnapshot,
    SkillSnapshot,
    VTLookupQueueItem,
)


class SkillRepository:
    """High-level persistence operations used by tests and the API."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record_intel_feed_run(
        self,
        *,
        provider: str,
        feed_name: str,
        source_url: str,
        auth_mode: str | None,
        parser_version: str,
        archive_sha256: str,
        archive_size_bytes: int,
    ) -> int:
        async with self._session_factory() as session:
            row = IntelFeedRun(
                provider=provider,
                feed_name=feed_name,
                source_url=source_url,
                auth_mode=auth_mode,
                parser_version=parser_version,
                archive_sha256=archive_sha256,
                archive_size_bytes=archive_size_bytes,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def record_intel_feed_artifact(
        self,
        *,
        feed_run_id: int,
        artifact_type: str,
        relative_path: str,
        sha256: str,
        size_bytes: int,
        content_type: str | None,
    ) -> int:
        async with self._session_factory() as session:
            row = IntelFeedArtifact(
                feed_run_id=feed_run_id,
                artifact_type=artifact_type,
                relative_path=relative_path,
                sha256=sha256,
                size_bytes=size_bytes,
                content_type=content_type,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def upsert_indicator(
        self,
        indicator_type: str,
        indicator_value: str,
    ) -> int:
        normalized_value = _normalize_indicator_value(indicator_type, indicator_value)
        async with self._session_factory() as session:
            result = await session.execute(
                select(Indicator).where(
                    Indicator.indicator_type == indicator_type,
                    Indicator.normalized_value == normalized_value,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = Indicator(
                    indicator_type=indicator_type,
                    indicator_value=indicator_value.strip(),
                    normalized_value=normalized_value,
                    first_seen_at=datetime.now(UTC),
                    last_seen_at=datetime.now(UTC),
                )
                session.add(row)
            else:
                row.indicator_value = indicator_value.strip()
                row.last_seen_at = datetime.now(UTC)

            await session.commit()
            await session.refresh(row)
            return row.id

    async def record_indicator_observation(
        self,
        *,
        indicator_id: int,
        feed_run_id: int,
        source_provider: str,
        source_feed: str,
        classification: str | None,
        confidence_label: str | None,
        summary: str | None,
        provider_record_id: str | None = None,
        malware_family: str | None = None,
        threat_type: str | None = None,
        reporter: str | None = None,
        first_seen_in_source: datetime | None = None,
        last_seen_in_source: datetime | None = None,
        provider_score: int | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> int:
        async with self._session_factory() as session:
            row = IndicatorObservation(
                indicator_id=indicator_id,
                feed_run_id=feed_run_id,
                source_provider=source_provider,
                source_feed=source_feed,
                provider_record_id=provider_record_id,
                classification=classification,
                confidence_label=confidence_label,
                malware_family=malware_family,
                threat_type=threat_type,
                reporter=reporter,
                first_seen_in_source=first_seen_in_source,
                last_seen_in_source=last_seen_in_source,
                provider_score=provider_score,
                summary=summary,
                raw_payload=raw_payload,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def record_skill_indicator_link(
        self,
        *,
        skill_snapshot_id: int,
        indicator_id: int,
        source_path: str | None,
        extraction_kind: str | None,
        raw_value: str | None,
        is_new_in_snapshot: bool,
    ) -> int:
        async with self._session_factory() as session:
            row = SkillIndicatorLink(
                skill_snapshot_id=skill_snapshot_id,
                indicator_id=indicator_id,
                source_path=source_path,
                extraction_kind=extraction_kind,
                raw_value=raw_value,
                is_new_in_snapshot=is_new_in_snapshot,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def get_latest_indicator_ids_for_skill(self, *, skill_id: int) -> set[int]:
        async with self._session_factory() as session:
            latest_snapshot_id = await session.scalar(
                select(func.max(SkillSnapshot.id)).where(SkillSnapshot.skill_id == skill_id)
            )
            if latest_snapshot_id is None:
                return set()

            result = await session.execute(
                select(SkillIndicatorLink.indicator_id)
                .where(SkillIndicatorLink.skill_snapshot_id == latest_snapshot_id)
            )
            return set(result.scalars().all())

    async def record_indicator_enrichment(
        self,
        *,
        indicator_id: int,
        provider: str,
        lookup_key: str,
        status: str,
        summary: str | None,
        archive_relative_path: str | None,
        normalized_payload: dict[str, Any] | None,
        requested_at: datetime | None,
        completed_at: datetime | None,
    ) -> int:
        async with self._session_factory() as session:
            row = IndicatorEnrichment(
                indicator_id=indicator_id,
                provider=provider,
                lookup_key=lookup_key,
                status=status,
                summary=summary,
                archive_relative_path=archive_relative_path,
                normalized_payload=normalized_payload,
                requested_at=requested_at,
                completed_at=completed_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def enqueue_vt_lookup(
        self,
        *,
        indicator_type: str,
        indicator_value: str,
        priority: int,
        reason: str,
        requested_by: str | None = None,
    ) -> int:
        indicator_id = await self.upsert_indicator(indicator_type, indicator_value)
        async with self._session_factory() as session:
            result = await session.execute(
                select(VTLookupQueueItem).where(
                    VTLookupQueueItem.indicator_id == indicator_id,
                    VTLookupQueueItem.status.in_(("queued", "running")),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = VTLookupQueueItem(
                    indicator_id=indicator_id,
                    priority=priority,
                    reason=reason,
                    status="queued",
                    requested_by=requested_by,
                )
                session.add(row)
            else:
                row.priority = max(row.priority, priority)
                row.reason = reason
                row.requested_by = requested_by or row.requested_by

            await session.commit()
            await session.refresh(row)
            return row.id

    async def list_vt_queue_items(self, *, status: str | None = None) -> list[dict]:
        async with self._session_factory() as session:
            query = (
                select(VTLookupQueueItem, Indicator)
                .join(Indicator, VTLookupQueueItem.indicator_id == Indicator.id)
                .order_by(VTLookupQueueItem.priority.desc(), VTLookupQueueItem.id.asc())
            )
            if status is not None:
                query = query.where(VTLookupQueueItem.status == status)

            result = await session.execute(query)
            return [
                {
                    "id": queue_item.id,
                    "indicator_id": indicator.id,
                    "indicator_type": indicator.indicator_type,
                    "indicator_value": indicator.indicator_value,
                    "priority": queue_item.priority,
                    "reason": queue_item.reason,
                    "status": queue_item.status,
                    "attempt_count": queue_item.attempt_count,
                }
                for queue_item, indicator in result.all()
            ]

    async def update_vt_queue_item(
        self,
        *,
        queue_item_id: int,
        status: str,
        attempt_count: int | None = None,
        next_attempt_at: datetime | None = None,
    ) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(VTLookupQueueItem).where(VTLookupQueueItem.id == queue_item_id)
            )
            row = result.scalar_one()
            row.status = status
            if attempt_count is not None:
                row.attempt_count = attempt_count
            row.next_attempt_at = next_attempt_at
            await session.commit()

    async def count_indicator_enrichments_today(
        self,
        *,
        provider: str,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with self._session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(IndicatorEnrichment)
                .where(IndicatorEnrichment.provider == provider)
                .where(func.coalesce(IndicatorEnrichment.requested_at, IndicatorEnrichment.created_at) >= day_start)
            )
            return int(count or 0)

    async def get_indicator_detail(
        self,
        indicator_type: str,
        indicator_value: str,
    ) -> dict | None:
        normalized_value = _normalize_indicator_value(indicator_type, indicator_value)
        async with self._session_factory() as session:
            indicator_result = await session.execute(
                select(Indicator).where(
                    Indicator.indicator_type == indicator_type,
                    Indicator.normalized_value == normalized_value,
                )
            )
            indicator = indicator_result.scalar_one_or_none()
            if indicator is None:
                return None

            observation_result = await session.execute(
                select(IndicatorObservation)
                .where(IndicatorObservation.indicator_id == indicator.id)
                .order_by(IndicatorObservation.id.asc())
            )
            observations = observation_result.scalars().all()
            enrichment_result = await session.execute(
                select(IndicatorEnrichment)
                .where(IndicatorEnrichment.indicator_id == indicator.id)
                .order_by(IndicatorEnrichment.id.asc())
            )
            enrichments = enrichment_result.scalars().all()
            linked_skill_result = await session.execute(
                select(SkillIndicatorLink, SkillSnapshot, Skill, SkillRepo)
                .join(SkillSnapshot, SkillIndicatorLink.skill_snapshot_id == SkillSnapshot.id)
                .join(Skill, SkillSnapshot.skill_id == Skill.id)
                .join(SkillRepo, Skill.repo_id == SkillRepo.id)
                .where(SkillIndicatorLink.indicator_id == indicator.id)
                .order_by(SkillIndicatorLink.id.asc())
            )
            return {
                "indicator": {
                    "id": indicator.id,
                    "indicator_type": indicator.indicator_type,
                    "indicator_value": indicator.indicator_value,
                    "normalized_value": indicator.normalized_value,
                },
                "observations": [
                    {
                        "id": observation.id,
                        "source_provider": observation.source_provider,
                        "source_feed": observation.source_feed,
                        "classification": observation.classification,
                        "confidence_label": observation.confidence_label,
                        "summary": observation.summary,
                    }
                    for observation in observations
                ],
                "enrichments": [
                    {
                        "provider": enrichment.provider,
                        "lookup_key": enrichment.lookup_key,
                        "status": enrichment.status,
                        "summary": enrichment.summary,
                        "archive_relative_path": enrichment.archive_relative_path,
                    }
                    for enrichment in enrichments
                ],
                "linked_skills": [
                    {
                        "publisher": repo.publisher,
                        "repo": repo.repo,
                        "skill_slug": skill.skill_slug,
                        "snapshot_id": snapshot.id,
                        "version_label": snapshot.version_label,
                        "source_path": link.source_path,
                        "extraction_kind": link.extraction_kind,
                    }
                    for link, snapshot, skill, repo in linked_skill_result.all()
                ],
            }

    async def upsert_skill_repo(
        self,
        *,
        publisher: str,
        repo: str,
        source_url: str,
        registry_rank: int | None,
    ) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SkillRepo).where(
                    SkillRepo.publisher == publisher,
                    SkillRepo.repo == repo,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = SkillRepo(
                    publisher=publisher,
                    repo=repo,
                    source_url=source_url,
                    registry_rank=registry_rank,
                    next_scan_at=datetime.now(UTC),
                )
                session.add(row)
            else:
                row.source_url = source_url
                row.registry_rank = registry_rank

            await session.commit()
            await session.refresh(row)
            return row.id

    async def record_repo_snapshot(
        self,
        *,
        repo_id: int,
        commit_sha: str,
        default_branch: str,
        discovered_skill_count: int,
    ) -> int:
        async with self._session_factory() as session:
            row = SkillRepoSnapshot(
                repo_id=repo_id,
                commit_sha=commit_sha,
                default_branch=default_branch,
                discovered_skill_count=discovered_skill_count,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def upsert_skill(
        self,
        *,
        repo_id: int,
        skill_slug: str,
        title: str,
        relative_path: str,
        registry_url: str,
    ) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Skill).where(
                    Skill.repo_id == repo_id,
                    Skill.skill_slug == skill_slug,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = Skill(
                    repo_id=repo_id,
                    skill_slug=skill_slug,
                    title=title,
                    relative_path=relative_path,
                    registry_url=registry_url,
                )
                session.add(row)
            else:
                row.title = title
                row.relative_path = relative_path
                row.registry_url = registry_url

            await session.commit()
            await session.refresh(row)
            return row.id

    async def record_skill_snapshot(
        self,
        *,
        skill_id: int,
        repo_snapshot_id: int,
        folder_hash: str,
        version_label: str,
        skill_text: str,
        referenced_files: list[str],
        extracted_domains: list[str],
        risk_report: dict,
    ) -> int:
        async with self._session_factory() as session:
            row = SkillSnapshot(
                skill_id=skill_id,
                repo_snapshot_id=repo_snapshot_id,
                folder_hash=folder_hash,
                version_label=version_label,
                skill_text=skill_text,
                referenced_files=referenced_files,
                extracted_domains=extracted_domains,
                risk_report=risk_report,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def record_external_verdict(
        self,
        *,
        skill_id: int,
        partner: str,
        verdict: str,
        summary: str | None,
        analyzed_at: str | None,
    ) -> int:
        async with self._session_factory() as session:
            row = ExternalVerdict(
                skill_id=skill_id,
                partner=partner,
                verdict=verdict,
                summary=summary,
                analyzed_at=analyzed_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def get_dashboard_stats(self) -> dict[str, int]:
        async with self._session_factory() as session:
            tracked_repos = await session.scalar(select(func.count()).select_from(SkillRepo))
            tracked_skills = await session.scalar(select(func.count()).select_from(Skill))
            latest_rows = await self._load_latest_skill_rows(session)
            critical_skills = sum(
                1
                for _, _, snapshot_row in latest_rows
                if (snapshot_row.risk_report or {}).get("severity") == "critical"
            )
            high_risk_skills = sum(
                1
                for _, _, snapshot_row in latest_rows
                if (snapshot_row.risk_report or {}).get("severity") in {"critical", "high"}
            )
            intel_backed_findings = sum(
                1
                for _, _, snapshot_row in latest_rows
                if (snapshot_row.risk_report or {}).get("indicator_matches")
            )
            return {
                "tracked_repos": int(tracked_repos or 0),
                "tracked_skills": int(tracked_skills or 0),
                "critical_skills": int(critical_skills or 0),
                "high_risk_skills": int(high_risk_skills or 0),
                "intel_backed_findings": int(intel_backed_findings or 0),
            }

    async def list_skills(
        self,
        *,
        limit: int = 50,
        severity: str | None = None,
    ) -> list[dict]:
        async with self._session_factory() as session:
            rows = await self._load_latest_skill_rows(session)
            if severity is not None:
                rows = [
                    row
                    for row in rows
                    if (row[2].risk_report or {}).get("severity") == severity
                ]
            if limit > 0:
                rows = rows[:limit]
            return [
                {
                    "publisher": repo_row.publisher,
                    "repo": repo_row.repo,
                    "skill_slug": skill_row.skill_slug,
                    "title": skill_row.title,
                    "latest_snapshot": {
                        "id": snapshot_row.id,
                        "version_label": snapshot_row.version_label,
                        "folder_hash": snapshot_row.folder_hash,
                        "referenced_files": snapshot_row.referenced_files,
                        "extracted_domains": snapshot_row.extracted_domains,
                        "risk_report": snapshot_row.risk_report,
                    },
                }
                for skill_row, repo_row, snapshot_row in rows
            ]

    async def list_intel_feed_runs(self, *, limit: int = 20) -> list[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(IntelFeedRun)
                .options(selectinload(IntelFeedRun.artifacts))
                .order_by(IntelFeedRun.id.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [
                {
                    "id": row.id,
                    "provider": row.provider,
                    "feed_name": row.feed_name,
                    "source_url": row.source_url,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "artifacts": [
                        {
                            "id": artifact.id,
                            "artifact_type": artifact.artifact_type,
                            "relative_path": artifact.relative_path,
                            "sha256": artifact.sha256,
                            "size_bytes": artifact.size_bytes,
                            "content_type": artifact.content_type,
                        }
                        for artifact in sorted(row.artifacts, key=lambda item: item.id)
                    ],
                }
                for row in rows
            ]

    async def list_indicators(
        self,
        *,
        limit: int = 50,
        indicator_type: str | None = None,
    ) -> list[dict]:
        async with self._session_factory() as session:
            query = select(Indicator).order_by(Indicator.id.desc()).limit(limit)
            if indicator_type is not None:
                query = query.where(Indicator.indicator_type == indicator_type)

            result = await session.execute(query)
            rows = result.scalars().all()
            return [
                {
                    "id": row.id,
                    "indicator_type": row.indicator_type,
                    "indicator_value": row.indicator_value,
                    "normalized_value": row.normalized_value,
                }
                for row in rows
            ]

    async def get_vt_queue_status(
        self,
        *,
        daily_budget: int,
        now: datetime | None = None,
    ) -> dict:
        queue_items = await self.list_vt_queue_items(status="queued")
        used_today = await self.count_indicator_enrichments_today(provider="virustotal", now=now)
        return {
            "daily_budget": daily_budget,
            "daily_budget_used": used_today,
            "daily_budget_remaining": max(0, daily_budget - used_today),
            "queue_items": queue_items,
        }

    async def _load_latest_skill_rows(
        self,
        session: AsyncSession,
    ) -> list[tuple[Skill, SkillRepo, SkillSnapshot]]:
        latest_snapshot_ids = (
            select(func.max(SkillSnapshot.id))
            .group_by(SkillSnapshot.skill_id)
            .scalar_subquery()
        )
        result = await session.execute(
            select(Skill, SkillRepo, SkillSnapshot)
            .join(SkillRepo, Skill.repo_id == SkillRepo.id)
            .join(SkillSnapshot, SkillSnapshot.skill_id == Skill.id)
            .where(SkillSnapshot.id.in_(latest_snapshot_ids))
            .order_by(SkillSnapshot.id.desc())
        )
        return list(result.all())

    async def list_due_repos(self, *, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now(UTC)
        async with self._session_factory() as session:
            result = await session.execute(
                select(SkillRepo).where(
                    SkillRepo.next_scan_at.is_(None) | (SkillRepo.next_scan_at <= now)
                )
            )
            rows = result.scalars().all()
            return [
                {
                    "id": row.id,
                    "publisher": row.publisher,
                    "repo": row.repo,
                    "source_url": row.source_url,
                    "registry_rank": row.registry_rank,
                }
                for row in rows
            ]

    async def list_registry_entries_for_repo_ids(self, repo_ids: list[int]) -> list[dict]:
        if not repo_ids:
            return []

        async with self._session_factory() as session:
            result = await session.execute(
                select(Skill, SkillRepo)
                .join(SkillRepo, Skill.repo_id == SkillRepo.id)
                .where(Skill.repo_id.in_(repo_ids))
                .order_by(SkillRepo.registry_rank.asc().nulls_last(), Skill.id.asc())
            )
            return [
                {
                    "publisher": repo.publisher,
                    "repo": repo.repo,
                    "skill_slug": skill.skill_slug,
                    "registry_url": skill.registry_url,
                }
                for skill, repo in result.all()
            ]

    async def mark_repo_scanned(
        self,
        *,
        repo_id: int,
        scan_interval_hours: int = 72,
        scanned_at: datetime | None = None,
    ) -> None:
        scanned_at = scanned_at or datetime.now(UTC)
        async with self._session_factory() as session:
            result = await session.execute(select(SkillRepo).where(SkillRepo.id == repo_id))
            row = result.scalar_one()
            row.last_scanned_at = scanned_at
            row.next_scan_at = scanned_at + timedelta(hours=scan_interval_hours)
            await session.commit()

    async def get_skill_detail(
        self,
        *,
        publisher: str,
        repo: str,
        skill_slug: str,
    ) -> dict | None:
        async with self._session_factory() as session:
            skill_result = await session.execute(
                select(Skill)
                .join(SkillRepo, Skill.repo_id == SkillRepo.id)
                .where(SkillRepo.publisher == publisher)
                .where(SkillRepo.repo == repo)
                .where(Skill.skill_slug == skill_slug)
            )
            skill_row = skill_result.scalar_one_or_none()
            if skill_row is None:
                return None

            snapshot_result = await session.execute(
                select(SkillSnapshot)
                .where(SkillSnapshot.skill_id == skill_row.id)
                .order_by(SkillSnapshot.id.desc())
                .limit(1)
            )
            latest_snapshot = snapshot_result.scalar_one_or_none()

            verdict_result = await session.execute(
                select(ExternalVerdict)
                .where(ExternalVerdict.skill_id == skill_row.id)
                .order_by(ExternalVerdict.id.asc())
            )
            verdicts = verdict_result.scalars().all()

            indicator_links: list[dict[str, Any]] = []
            if latest_snapshot is not None:
                link_result = await session.execute(
                    select(SkillIndicatorLink, Indicator)
                    .join(Indicator, SkillIndicatorLink.indicator_id == Indicator.id)
                    .where(SkillIndicatorLink.skill_snapshot_id == latest_snapshot.id)
                    .order_by(SkillIndicatorLink.id.asc())
                )
                indicator_links = [
                    {
                        "indicator_id": indicator.id,
                        "indicator_type": indicator.indicator_type,
                        "indicator_value": indicator.indicator_value,
                        "source_path": link.source_path,
                        "extraction_kind": link.extraction_kind,
                        "raw_value": link.raw_value,
                        "is_new_in_snapshot": link.is_new_in_snapshot,
                    }
                    for link, indicator in link_result.all()
                ]

            return {
                "publisher": publisher,
                "repo": repo,
                "skill_slug": skill_row.skill_slug,
                "title": skill_row.title,
                "relative_path": skill_row.relative_path,
                "registry_url": skill_row.registry_url,
                "latest_snapshot": (
                    {
                        "id": latest_snapshot.id,
                        "version_label": latest_snapshot.version_label,
                        "folder_hash": latest_snapshot.folder_hash,
                        "referenced_files": latest_snapshot.referenced_files,
                        "extracted_domains": latest_snapshot.extracted_domains,
                        "risk_report": latest_snapshot.risk_report,
                        "indicator_links": indicator_links,
                    }
                    if latest_snapshot is not None
                    else None
                ),
                "external_verdicts": [
                    {
                        "partner": verdict.partner,
                        "verdict": verdict.verdict,
                        "summary": verdict.summary,
                        "analyzed_at": verdict.analyzed_at,
                    }
                    for verdict in verdicts
                ],
            }


def _normalize_indicator_value(indicator_type: str, indicator_value: str) -> str:
    value = indicator_value.strip()
    if indicator_type in {"domain", "hostname", "ip", "sha256"}:
        return value.lower()
    return value
