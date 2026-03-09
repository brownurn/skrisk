"""Repository methods for the initial API and ingestion flows."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
import ipaddress
from typing import Any

from sqlalchemy import Float, Integer, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from skrisk.analysis import compute_priority_metrics
from skrisk.storage.models import (
    ExternalVerdict,
    Indicator,
    IndicatorEnrichment,
    IndicatorObservation,
    IntelFeedArtifact,
    IntelFeedRun,
    RegistrySource,
    RegistrySyncRun,
    Skill,
    SkillIndicatorLink,
    SkillRegistryObservation,
    SkillRepo,
    SkillRepoSnapshot,
    SkillSnapshot,
    SkillSourceEntry,
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

    async def record_registry_sync_run(
        self,
        *,
        source: str,
        view: str,
        total_skills_reported: int | None,
        pages_fetched: int,
        success: bool,
        error_summary: str | None = None,
    ) -> int:
        async with self._session_factory() as session:
            row = RegistrySyncRun(
                source=source,
                view=view,
                total_skills_reported=total_skills_reported,
                pages_fetched=pages_fetched,
                success=success,
                error_summary=error_summary,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def upsert_registry_source(
        self,
        *,
        name: str,
        base_url: str,
    ) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(RegistrySource).where(RegistrySource.name == name)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = RegistrySource(name=name, base_url=base_url)
                session.add(row)
            else:
                row.base_url = base_url

            await session.commit()
            await session.refresh(row)
            return row.id

    async def upsert_skill_source_entry(
        self,
        *,
        skill_id: int,
        registry_source_id: int,
        source_url: str,
        source_native_id: str | None,
        weekly_installs: int | None,
        registry_rank: int | None,
        registry_sync_run_id: int | None,
        observed_at: datetime,
        raw_payload: dict[str, Any] | None,
    ) -> int:
        observed_at = _coerce_datetime_utc(observed_at) or datetime.now(UTC)
        async with self._session_factory() as session:
            base_query = select(SkillSourceEntry).where(
                SkillSourceEntry.skill_id == skill_id,
                SkillSourceEntry.registry_source_id == registry_source_id,
            )
            if source_native_id is not None:
                query = base_query.where(SkillSourceEntry.source_native_id == source_native_id)
            else:
                query = base_query.where(
                    SkillSourceEntry.source_native_id.is_(None),
                    SkillSourceEntry.source_url == source_url,
                )
            result = await session.execute(query)
            row = result.scalar_one_or_none()
            if row is None and source_native_id is not None:
                fallback_result = await session.execute(
                    base_query.where(SkillSourceEntry.source_url == source_url)
                )
                row = fallback_result.scalar_one_or_none()
            if row is None:
                row = SkillSourceEntry(
                    skill_id=skill_id,
                    registry_source_id=registry_source_id,
                    source_url=source_url,
                    source_native_id=source_native_id,
                    weekly_installs=weekly_installs,
                    registry_rank=registry_rank,
                    current_registry_sync_run_id=registry_sync_run_id,
                    current_registry_sync_observed_at=(
                        observed_at if registry_sync_run_id is not None else None
                    ),
                    raw_payload=raw_payload,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                )
                session.add(row)
            else:
                row.source_url = source_url
                row.source_native_id = source_native_id
                row.weekly_installs = weekly_installs
                if registry_rank is not None:
                    row.registry_rank = registry_rank
                row.raw_payload = raw_payload
                first_seen_at = _coerce_datetime_utc(row.first_seen_at) or observed_at
                last_seen_at = _coerce_datetime_utc(row.last_seen_at) or observed_at
                if observed_at >= last_seen_at and registry_sync_run_id is not None:
                    row.current_registry_sync_run_id = registry_sync_run_id
                    row.current_registry_sync_observed_at = observed_at
                row.first_seen_at = min(first_seen_at, observed_at)
                row.last_seen_at = max(last_seen_at, observed_at)

            await session.flush()
            await self._recompute_skill_total_installs(session, skill_id=skill_id)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def record_skill_registry_observation(
        self,
        *,
        skill_id: int,
        registry_sync_run_id: int | None,
        repo_snapshot_id: int | None,
        observed_at: datetime,
        weekly_installs: int | None,
        registry_rank: int | None,
        observation_kind: str,
        raw_payload: dict[str, Any] | None,
    ) -> int:
        _validate_registry_observation_provenance(
            observation_kind=observation_kind,
            registry_sync_run_id=registry_sync_run_id,
            repo_snapshot_id=repo_snapshot_id,
        )
        async with self._session_factory() as session:
            row = SkillRegistryObservation(
                skill_id=skill_id,
                registry_sync_run_id=registry_sync_run_id,
                repo_snapshot_id=repo_snapshot_id,
                observed_at=observed_at,
                weekly_installs=weekly_installs,
                registry_rank=registry_rank,
                observation_kind=observation_kind,
                raw_payload=raw_payload,
            )
            session.add(row)

            if observation_kind == "directory_fetch":
                skill = await session.get(Skill, skill_id)
                if skill is not None:
                    current_observed_at = _coerce_datetime_utc(
                        skill.current_weekly_installs_observed_at
                    )
                    incoming_observed_at = _coerce_datetime_utc(observed_at)
                    if current_observed_at is None or incoming_observed_at >= current_observed_at:
                        skill.current_weekly_installs = weekly_installs
                        skill.current_weekly_installs_observed_at = incoming_observed_at
                        if registry_rank is not None or skill.current_registry_rank is None:
                            skill.current_registry_rank = registry_rank
                        skill.current_registry_sync_run_id = registry_sync_run_id

            await session.commit()
            await session.refresh(row)
            return row.id

    async def list_skill_registry_observations(self, *, skill_id: int) -> list[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SkillRegistryObservation)
                .where(SkillRegistryObservation.skill_id == skill_id)
                .order_by(
                    SkillRegistryObservation.observed_at.asc(),
                    SkillRegistryObservation.id.asc(),
                )
            )
            rows = result.scalars().all()
            return [
                {
                    "id": row.id,
                    "skill_id": row.skill_id,
                    "registry_sync_run_id": row.registry_sync_run_id,
                    "repo_snapshot_id": row.repo_snapshot_id,
                    "observed_at": _isoformat_datetime(row.observed_at),
                    "weekly_installs": row.weekly_installs,
                    "registry_rank": row.registry_rank,
                    "observation_kind": row.observation_kind,
                    "raw_payload": row.raw_payload,
                }
                for row in rows
            ]

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

    async def indicator_has_completed_enrichment(
        self,
        *,
        indicator_id: int,
        provider: str,
    ) -> bool:
        async with self._session_factory() as session:
            result = await session.scalar(
                select(func.count())
                .select_from(IndicatorEnrichment)
                .where(IndicatorEnrichment.indicator_id == indicator_id)
                .where(IndicatorEnrichment.provider == provider)
                .where(IndicatorEnrichment.status == "completed")
            )
            return bool(result)

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
        scan_interval_hours: int = 72,
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
                    next_scan_at=None,
                )
                session.add(row)
            else:
                row.source_url = source_url
                if registry_rank is not None:
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
        title: str | None,
        relative_path: str,
        registry_url: str,
        registry_source: str | None = None,
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
                    title=title or skill_slug,
                    relative_path=relative_path,
                    registry_url=registry_url,
                )
                session.add(row)
            else:
                if title is not None:
                    row.title = title
                row.relative_path = relative_path
                if registry_source is None or _should_replace_registry_url(
                    existing_url=row.registry_url,
                    incoming_url=registry_url,
                    incoming_source=registry_source,
                ):
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
                if snapshot_row is not None
                and (snapshot_row.risk_report or {}).get("severity") == "critical"
            )
            high_risk_skills = sum(
                1
                for _, _, snapshot_row in latest_rows
                if snapshot_row is not None
                and (snapshot_row.risk_report or {}).get("severity") in {"critical", "high"}
            )
            intel_backed_findings = sum(
                1
                for _, _, snapshot_row in latest_rows
                if snapshot_row is not None
                and (snapshot_row.risk_report or {}).get("indicator_matches")
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
        min_weekly_installs: int | None = None,
        max_weekly_installs: int | None = None,
        sort: str | None = None,
        query: str | None = None,
    ) -> list[dict]:
        page = await self.list_skills_page(
            page=1,
            page_size=limit if limit > 0 else 0,
            severity=severity,
            min_weekly_installs=min_weekly_installs,
            max_weekly_installs=max_weekly_installs,
            sort=sort,
            query=query,
        )
        return page["items"]

    async def list_skills_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        severity: str | None = None,
        min_weekly_installs: int | None = None,
        max_weekly_installs: int | None = None,
        sort: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        page = max(1, page)
        limit = None if page_size <= 0 else page_size
        offset = 0 if limit is None else (page - 1) * page_size

        async with self._session_factory() as session:
            rows, total = await self._load_latest_skill_page_rows(
                session,
                offset=offset,
                limit=limit,
                severity=severity,
                min_weekly_installs=min_weekly_installs,
                max_weekly_installs=max_weekly_installs,
                sort=sort,
                query=query,
            )
            observations_by_skill = await self._load_registry_observations(
                session,
                [skill_row.id for skill_row, _, _, _ in rows],
            )
            source_entries_by_skill = await self._load_source_entries(
                session,
                [skill_row.id for skill_row, _, _, _ in rows],
            )

            items = []
            for skill_row, repo_row, snapshot_row, _previous_weekly_installs in rows:
                telemetry = _build_install_telemetry(
                    skill_row=skill_row,
                    snapshot_row=snapshot_row,
                    observations=observations_by_skill.get(skill_row.id, []),
                )
                source_entries = source_entries_by_skill.get(skill_row.id, [])
                items.append(
                    {
                        "publisher": repo_row.publisher,
                        "repo": repo_row.repo,
                        "skill_slug": skill_row.skill_slug,
                        "title": skill_row.title,
                        "current_weekly_installs": telemetry["current_weekly_installs"],
                        "current_weekly_installs_observed_at": telemetry[
                            "current_weekly_installs_observed_at"
                        ],
                        "peak_weekly_installs": telemetry["peak_weekly_installs"],
                        "weekly_installs_delta": telemetry["weekly_installs_delta"],
                        "impact_score": telemetry["impact_score"],
                        "priority_score": telemetry["priority_score"],
                        "current_total_installs": _resolved_total_installs(skill_row),
                        "current_total_installs_observed_at": _isoformat_datetime(
                            _resolved_total_installs_observed_at(skill_row)
                        ),
                        "source_count": len(source_entries),
                        "sources": [entry["source_name"] for entry in source_entries],
                        "install_breakdown": _build_install_breakdown(source_entries),
                        "latest_snapshot": (
                            {
                                "id": snapshot_row.id,
                                "version_label": snapshot_row.version_label,
                                "folder_hash": snapshot_row.folder_hash,
                                "referenced_files": snapshot_row.referenced_files,
                                "extracted_domains": snapshot_row.extracted_domains,
                                "risk_report": snapshot_row.risk_report,
                            }
                            if snapshot_row is not None
                            else None
                        ),
                    }
                )

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": 0 if limit is None else page_size,
                "has_previous": page > 1,
                "has_next": False if limit is None else (offset + len(items)) < total,
            }

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

    async def list_infrastructure_candidates(
        self,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            link_count = func.count(func.distinct(SkillIndicatorLink.id))
            observation_count = func.count(func.distinct(IndicatorObservation.id))
            new_link_count = func.sum(
                case((SkillIndicatorLink.is_new_in_snapshot.is_(True), 1), else_=0)
            )
            max_risk_score = func.max(
                cast(func.json_extract(SkillSnapshot.risk_report, "$.score"), Integer)
            )
            result = await session.execute(
                select(
                    Indicator,
                    link_count.label("link_count"),
                    observation_count.label("observation_count"),
                    new_link_count.label("new_link_count"),
                    max_risk_score.label("max_risk_score"),
                )
                .outerjoin(SkillIndicatorLink, SkillIndicatorLink.indicator_id == Indicator.id)
                .outerjoin(SkillSnapshot, SkillSnapshot.id == SkillIndicatorLink.skill_snapshot_id)
                .outerjoin(IndicatorObservation, IndicatorObservation.indicator_id == Indicator.id)
                .where(Indicator.indicator_type.in_(("domain", "ip")))
                .group_by(Indicator.id)
                .having(link_count > 0)
                .order_by(
                    observation_count.desc(),
                    max_risk_score.desc().nulls_last(),
                    new_link_count.desc().nulls_last(),
                    link_count.desc(),
                    Indicator.id.asc(),
                )
                .limit(max(limit * 5, limit))
            )
            indicator_rows = result.all()
            indicator_ids = [indicator.id for indicator, *_ in indicator_rows]
            if not indicator_ids:
                return []

            enrichment_result = await session.execute(
                select(IndicatorEnrichment)
                .where(IndicatorEnrichment.indicator_id.in_(indicator_ids))
                .order_by(IndicatorEnrichment.id.asc())
            )
            completed_providers_by_indicator: dict[int, set[str]] = defaultdict(set)
            for enrichment in enrichment_result.scalars().all():
                if enrichment.status == "completed":
                    completed_providers_by_indicator[enrichment.indicator_id].add(enrichment.provider)

            candidates: list[dict[str, Any]] = []
            for (
                indicator,
                linked_skill_count,
                matched_observation_count,
                new_indicator_count,
                max_indicator_risk_score,
            ) in indicator_rows:
                if _is_low_signal_infrastructure_indicator(
                    indicator_type=indicator.indicator_type,
                    indicator_value=indicator.indicator_value,
                ):
                    continue
                completed_providers = completed_providers_by_indicator.get(indicator.id, set())
                if indicator.indicator_type == "domain" and {
                    "local_dns",
                    "mewhois",
                }.issubset(completed_providers):
                    continue
                if indicator.indicator_type == "ip" and "meip" in completed_providers:
                    continue
                candidates.append(
                    {
                        "id": indicator.id,
                        "indicator_type": indicator.indicator_type,
                        "indicator_value": indicator.indicator_value,
                        "completed_providers": sorted(completed_providers),
                        "linked_skill_count": int(linked_skill_count or 0),
                        "matched_observation_count": int(matched_observation_count or 0),
                        "new_indicator_count": int(new_indicator_count or 0),
                        "max_risk_score": int(max_indicator_risk_score or 0),
                    }
                )
                if len(candidates) >= limit:
                    break
            return candidates

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
    ) -> list[tuple[Skill, SkillRepo, SkillSnapshot | None]]:
        latest_snapshot_ids = (
            select(
                SkillSnapshot.skill_id.label("skill_id"),
                func.max(SkillSnapshot.id).label("latest_snapshot_id"),
            )
            .group_by(SkillSnapshot.skill_id)
            .subquery()
        )
        result = await session.execute(
            select(Skill, SkillRepo, SkillSnapshot)
            .join(SkillRepo, Skill.repo_id == SkillRepo.id)
            .outerjoin(latest_snapshot_ids, latest_snapshot_ids.c.skill_id == Skill.id)
            .outerjoin(SkillSnapshot, SkillSnapshot.id == latest_snapshot_ids.c.latest_snapshot_id)
            .order_by(SkillSnapshot.id.desc().nulls_last(), Skill.id.desc())
        )
        return list(result.all())

    async def _load_latest_skill_page_rows(
        self,
        session: AsyncSession,
        *,
        offset: int,
        limit: int | None,
        severity: str | None,
        min_weekly_installs: int | None,
        max_weekly_installs: int | None,
        sort: str | None,
        query: str | None,
    ) -> tuple[list[tuple[Skill, SkillRepo, SkillSnapshot | None, int | None]], int]:
        latest_snapshot_ids = (
            select(
                SkillSnapshot.skill_id.label("skill_id"),
                func.max(SkillSnapshot.id).label("latest_snapshot_id"),
            )
            .group_by(SkillSnapshot.skill_id)
            .subquery()
        )
        aggregated_observations = (
            select(
                SkillRegistryObservation.skill_id.label("skill_id"),
                SkillRegistryObservation.observed_at.label("observed_at"),
                func.sum(SkillRegistryObservation.weekly_installs).label("weekly_installs"),
                func.max(SkillRegistryObservation.id).label("latest_observation_id"),
            )
            .where(SkillRegistryObservation.observation_kind == "directory_fetch")
            .group_by(
                SkillRegistryObservation.skill_id,
                SkillRegistryObservation.observed_at,
            )
            .subquery()
        )
        ranked_observations = (
            select(
                aggregated_observations.c.skill_id,
                aggregated_observations.c.weekly_installs,
                func.row_number()
                .over(
                    partition_by=aggregated_observations.c.skill_id,
                    order_by=(
                        aggregated_observations.c.observed_at.desc(),
                        aggregated_observations.c.latest_observation_id.desc(),
                    ),
                )
                .label("row_number"),
            )
            .select_from(aggregated_observations)
            .subquery()
        )
        previous_weekly_installs = (
            select(
                ranked_observations.c.skill_id,
                ranked_observations.c.weekly_installs.label("previous_weekly_installs"),
            )
            .where(ranked_observations.c.row_number == 2)
            .subquery()
        )

        severity_expression = func.coalesce(
            func.json_extract(SkillSnapshot.risk_report, "$.severity"),
            "none",
        )
        risk_score_expression = cast(
            func.coalesce(func.json_extract(SkillSnapshot.risk_report, "$.score"), 0),
            Integer,
        )
        confidence_expression = func.json_extract(SkillSnapshot.risk_report, "$.confidence")
        current_weekly_installs = func.coalesce(
            Skill.current_total_installs,
            Skill.current_weekly_installs,
        )
        previous_weekly_installs_expression = previous_weekly_installs.c.previous_weekly_installs
        growth_expression = case(
            (
                and_(
                    current_weekly_installs.is_not(None),
                    previous_weekly_installs_expression.is_not(None),
                ),
                current_weekly_installs - previous_weekly_installs_expression,
            ),
            else_=-10**9,
        )
        impact_expression = _impact_score_sql(
            current_weekly_installs=current_weekly_installs,
            previous_weekly_installs=previous_weekly_installs_expression,
        )
        priority_expression = _priority_score_sql(
            risk_score=risk_score_expression,
            severity=severity_expression,
            confidence=confidence_expression,
            impact_score=impact_expression,
        )

        query_stmt = (
            select(
                Skill,
                SkillRepo,
                SkillSnapshot,
                previous_weekly_installs_expression.label("previous_weekly_installs"),
            )
            .join(SkillRepo, Skill.repo_id == SkillRepo.id)
            .outerjoin(latest_snapshot_ids, latest_snapshot_ids.c.skill_id == Skill.id)
            .outerjoin(SkillSnapshot, SkillSnapshot.id == latest_snapshot_ids.c.latest_snapshot_id)
            .outerjoin(
                previous_weekly_installs,
                previous_weekly_installs.c.skill_id == Skill.id,
            )
        )

        if severity is not None:
            query_stmt = query_stmt.where(severity_expression == severity)
        if min_weekly_installs is not None:
            query_stmt = query_stmt.where(
                current_weekly_installs.is_not(None),
                current_weekly_installs >= min_weekly_installs,
            )
        if max_weekly_installs is not None:
            query_stmt = query_stmt.where(
                current_weekly_installs.is_not(None),
                current_weekly_installs <= max_weekly_installs,
            )
        normalized_query = (query or "").strip().lower()
        if normalized_query:
            query_pattern = f"%{normalized_query}%"
            query_stmt = query_stmt.where(
                or_(
                    func.lower(SkillRepo.publisher).like(query_pattern),
                    func.lower(SkillRepo.repo).like(query_pattern),
                    func.lower(Skill.skill_slug).like(query_pattern),
                    func.lower(Skill.title).like(query_pattern),
                )
            )

        count_query = select(func.count()).select_from(query_stmt.order_by(None).subquery())
        total = int((await session.scalar(count_query)) or 0)

        if sort in {None, "priority"}:
            query_stmt = query_stmt.order_by(
                priority_expression.desc(),
                func.coalesce(current_weekly_installs, -1).desc(),
                risk_score_expression.desc(),
                SkillSnapshot.id.desc().nullslast(),
                Skill.id.desc(),
            )
        elif sort == "risk":
            query_stmt = query_stmt.order_by(
                risk_score_expression.desc(),
                priority_expression.desc(),
                SkillSnapshot.id.desc().nullslast(),
                Skill.id.desc(),
            )
        elif sort == "installs":
            query_stmt = query_stmt.order_by(
                func.coalesce(current_weekly_installs, -1).desc(),
                priority_expression.desc(),
                SkillSnapshot.id.desc().nullslast(),
                Skill.id.desc(),
            )
        elif sort == "growth":
            query_stmt = query_stmt.order_by(
                growth_expression.desc(),
                func.coalesce(current_weekly_installs, -1).desc(),
                SkillSnapshot.id.desc().nullslast(),
                Skill.id.desc(),
            )

        if limit is not None:
            query_stmt = query_stmt.offset(offset).limit(limit)

        result = await session.execute(query_stmt)
        return list(result.all()), total

    async def _load_registry_observations(
        self,
        session: AsyncSession,
        skill_ids: list[int],
    ) -> dict[int, list[SkillRegistryObservation]]:
        if not skill_ids:
            return {}

        result = await session.execute(
            select(SkillRegistryObservation)
            .where(SkillRegistryObservation.skill_id.in_(skill_ids))
            .order_by(
                SkillRegistryObservation.skill_id.asc(),
                SkillRegistryObservation.observed_at.asc(),
                SkillRegistryObservation.id.asc(),
            )
        )
        observations_by_skill: dict[int, list[SkillRegistryObservation]] = defaultdict(list)
        for row in result.scalars().all():
            observations_by_skill[row.skill_id].append(row)
        return dict(observations_by_skill)

    async def _load_source_entries(
        self,
        session: AsyncSession,
        skill_ids: list[int],
    ) -> dict[int, list[dict[str, Any]]]:
        if not skill_ids:
            return {}

        result = await session.execute(
            select(SkillSourceEntry, RegistrySource, RegistrySyncRun)
            .join(RegistrySource, SkillSourceEntry.registry_source_id == RegistrySource.id)
            .outerjoin(
                RegistrySyncRun,
                RegistrySyncRun.id == SkillSourceEntry.current_registry_sync_run_id,
            )
            .where(SkillSourceEntry.skill_id.in_(skill_ids))
            .order_by(
                SkillSourceEntry.skill_id.asc(),
                RegistrySource.name.asc(),
                SkillSourceEntry.id.asc(),
            )
        )
        source_entries_by_skill: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for source_entry, registry_source, registry_sync_run in result.all():
            source_entries_by_skill[source_entry.skill_id].append(
                _serialize_source_entry(source_entry, registry_source, registry_sync_run)
            )
        return dict(source_entries_by_skill)

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

    async def get_skill_registry_observation_context(self, *, skill_id: int) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            source_entries_by_skill = await self._load_source_entries(session, [skill_id])
            primary_source_entry = _primary_source_entry(source_entries_by_skill.get(skill_id, []))
            if primary_source_entry is not None:
                return {
                    "weekly_installs": primary_source_entry["weekly_installs"],
                    "observed_at": _coerce_datetime_utc(
                        primary_source_entry["current_registry_sync_observed_at"]
                    )
                    or _coerce_datetime_utc(primary_source_entry["last_seen_at"]),
                    "registry_rank": primary_source_entry["registry_rank"],
                    "registry_sync_run_id": primary_source_entry["current_registry_sync_run_id"],
                    "view": primary_source_entry["view"],
                    "source": primary_source_entry["source_name"],
                }

            row = await session.get(Skill, skill_id)
            if row is None:
                return None
            return {
                "weekly_installs": row.current_weekly_installs,
                "observed_at": _coerce_datetime_utc(row.current_weekly_installs_observed_at),
                "registry_rank": row.current_registry_rank,
                "registry_sync_run_id": row.current_registry_sync_run_id,
            }

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
            skill_rows = result.all()
            source_entries_by_skill = await self._load_source_entries(
                session,
                [skill.id for skill, _ in skill_rows],
            )
            entries: list[dict[str, Any]] = []
            for skill, repo in skill_rows:
                source_entries = source_entries_by_skill.get(skill.id, [])
                primary_source_entry = _primary_source_entry(source_entries)
                entries.append(
                    {
                        "publisher": repo.publisher,
                        "repo": repo.repo,
                        "skill_slug": skill.skill_slug,
                        "registry_url": (
                            primary_source_entry["source_url"]
                            if primary_source_entry is not None
                            else skill.registry_url
                        ),
                        "source": (
                            primary_source_entry["source_name"]
                            if primary_source_entry is not None
                            else _registry_source_from_url(skill.registry_url)
                        ),
                        "source_native_id": (
                            primary_source_entry["source_native_id"]
                            if primary_source_entry is not None
                            else None
                        ),
                        "view": (
                            primary_source_entry["view"]
                            if primary_source_entry is not None
                            else "all-time"
                        ),
                        "weekly_installs": (
                            primary_source_entry["weekly_installs"]
                            if primary_source_entry is not None
                            else skill.current_weekly_installs
                        ),
                        "weekly_installs_observed_at": (
                            _coerce_datetime_utc(
                                primary_source_entry["current_registry_sync_observed_at"]
                            )
                            or _coerce_datetime_utc(primary_source_entry["last_seen_at"])
                            if primary_source_entry is not None
                            else _coerce_datetime_utc(skill.current_weekly_installs_observed_at)
                        ),
                        "registry_rank": (
                            primary_source_entry["registry_rank"]
                            if primary_source_entry is not None
                            else skill.current_registry_rank
                        ),
                        "registry_sync_run_id": (
                            primary_source_entry["current_registry_sync_run_id"]
                            if primary_source_entry is not None
                            else skill.current_registry_sync_run_id
                        ),
                    }
                )
            return entries

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
            observations_by_skill = await self._load_registry_observations(session, [skill_row.id])
            observations = observations_by_skill.get(skill_row.id, [])
            source_entry_result = await session.execute(
                select(SkillSourceEntry, RegistrySource, RegistrySyncRun)
                .join(RegistrySource, SkillSourceEntry.registry_source_id == RegistrySource.id)
                .outerjoin(
                    RegistrySyncRun,
                    RegistrySyncRun.id == SkillSourceEntry.current_registry_sync_run_id,
                )
                .where(SkillSourceEntry.skill_id == skill_row.id)
                .order_by(RegistrySource.name.asc(), SkillSourceEntry.id.asc())
            )
            source_entries = [
                _serialize_source_entry(source_entry, registry_source, registry_sync_run)
                for source_entry, registry_source, registry_sync_run in source_entry_result.all()
            ]
            telemetry = _build_install_telemetry(
                skill_row=skill_row,
                snapshot_row=latest_snapshot,
                observations=observations,
            )

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
                link_rows = link_result.all()
                indicator_ids = [indicator.id for _, indicator in link_rows]
                enrichments_by_indicator: dict[int, list[dict[str, Any]]] = defaultdict(list)
                if indicator_ids:
                    enrichment_result = await session.execute(
                        select(IndicatorEnrichment)
                        .where(IndicatorEnrichment.indicator_id.in_(indicator_ids))
                        .order_by(IndicatorEnrichment.id.asc())
                    )
                    for enrichment in enrichment_result.scalars().all():
                        enrichments_by_indicator[enrichment.indicator_id].append(
                            {
                                "provider": enrichment.provider,
                                "lookup_key": enrichment.lookup_key,
                                "status": enrichment.status,
                                "summary": enrichment.summary,
                                "archive_relative_path": enrichment.archive_relative_path,
                                "normalized_payload": enrichment.normalized_payload,
                            }
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
                        "enrichments": enrichments_by_indicator.get(indicator.id, []),
                    }
                    for link, indicator in link_rows
                ]

            return {
                "publisher": publisher,
                "repo": repo,
                "skill_slug": skill_row.skill_slug,
                "title": skill_row.title,
                "relative_path": skill_row.relative_path,
                "registry_url": skill_row.registry_url,
                "current_weekly_installs": telemetry["current_weekly_installs"],
                "current_weekly_installs_observed_at": telemetry[
                    "current_weekly_installs_observed_at"
                ],
                "current_total_installs": _resolved_total_installs(skill_row),
                "current_total_installs_observed_at": _isoformat_datetime(
                    _resolved_total_installs_observed_at(skill_row)
                ),
                "current_registry_rank": skill_row.current_registry_rank,
                "source_count": len(source_entries),
                "sources": [entry["source_name"] for entry in source_entries],
                "install_breakdown": _build_install_breakdown(source_entries),
                "source_entries": source_entries,
                "peak_weekly_installs": telemetry["peak_weekly_installs"],
                "weekly_installs_delta": telemetry["weekly_installs_delta"],
                "impact_score": telemetry["impact_score"],
                "priority_score": telemetry["priority_score"],
                "install_history": _serialize_install_history(observations),
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

    async def _recompute_skill_total_installs(
        self,
        session: AsyncSession,
        *,
        skill_id: int,
    ) -> None:
        skill = await session.get(Skill, skill_id)
        if skill is None:
            return

        result = await session.execute(
            select(SkillSourceEntry).where(SkillSourceEntry.skill_id == skill_id)
        )
        source_entries = result.scalars().all()
        known_installs = [
            entry.weekly_installs
            for entry in source_entries
            if entry.weekly_installs is not None
        ]
        latest_observed_at = max(
            (_coerce_datetime_utc(entry.last_seen_at) for entry in source_entries),
            default=None,
        )
        skill.current_total_installs = sum(known_installs) if known_installs else None
        skill.current_total_installs_observed_at = latest_observed_at


def _sort_skill_listing(rows: list[dict[str, Any]], *, sort: str | None) -> None:
    if sort in {None, "priority"}:
        rows.sort(
            key=lambda item: (
                item["priority_score"],
                _sort_weekly_installs_value(item["current_weekly_installs"]),
                _sort_latest_snapshot_risk_score(item),
                _sort_latest_snapshot_id(item),
            ),
            reverse=True,
        )
        return
    if sort == "risk":
        rows.sort(
            key=lambda item: (
                _sort_latest_snapshot_risk_score(item),
                item["priority_score"],
                _sort_latest_snapshot_id(item),
            ),
            reverse=True,
        )
        return
    if sort == "installs":
        rows.sort(
            key=lambda item: (
                _sort_weekly_installs_value(item["current_weekly_installs"]),
                item["priority_score"],
                _sort_latest_snapshot_id(item),
            ),
            reverse=True,
        )
        return
    if sort == "growth":
        rows.sort(
            key=lambda item: (
                item["weekly_installs_delta"] if item["weekly_installs_delta"] is not None else -10**9,
                _sort_weekly_installs_value(item["current_weekly_installs"]),
                _sort_latest_snapshot_id(item),
            ),
            reverse=True,
        )
        return


def _impact_score_sql(*, current_weekly_installs, previous_weekly_installs):
    base_score = case(
        (
            or_(
                current_weekly_installs.is_(None),
                current_weekly_installs <= 0,
            ),
            0,
        ),
        (current_weekly_installs < 10, 5),
        (current_weekly_installs < 100, 15),
        (current_weekly_installs < 1_000, 30),
        (current_weekly_installs < 10_000, 50),
        (current_weekly_installs < 50_000, 70),
        else_=90,
    )
    ratio_expression = cast(current_weekly_installs, Float) / cast(previous_weekly_installs, Float)

    return case(
        (
            or_(
                current_weekly_installs.is_(None),
                previous_weekly_installs.is_(None),
            ),
            base_score,
        ),
        (
            previous_weekly_installs <= 0,
            func.min(
                100,
                base_score
                + case((current_weekly_installs > 0, 20), else_=0),
            ),
        ),
        (ratio_expression >= 2, func.min(100, base_score + 20)),
        (ratio_expression >= 1.1, func.min(100, base_score + 10)),
        (ratio_expression <= 0.5, func.max(0, base_score - 10)),
        else_=base_score,
    )


def _priority_score_sql(*, risk_score, severity, confidence, impact_score):
    severity_multiplier = case(
        (severity == "none", 0.5),
        (severity == "low", 0.7),
        (severity == "medium", 0.9),
        (severity == "high", 1.0),
        (severity == "critical", 1.1),
        else_=1.0,
    )
    confidence_multiplier = case(
        (confidence == "suspected", 0.9),
        (confidence == "likely", 1.0),
        (confidence == "confirmed", 1.1),
        else_=1.0,
    )
    return func.round(
        func.min(
            100,
            func.max(
                0,
                risk_score
                * severity_multiplier
                * confidence_multiplier
                * (1 + (impact_score / 200.0)),
            ),
        )
    )


def _sort_weekly_installs_value(value: int | None) -> int:
    return -1 if value is None else value


def _sort_latest_snapshot_id(item: dict[str, Any]) -> int:
    latest_snapshot = item.get("latest_snapshot") or {}
    return int(latest_snapshot.get("id") or -1)


def _sort_latest_snapshot_risk_score(item: dict[str, Any]) -> int:
    latest_snapshot = item.get("latest_snapshot") or {}
    risk_report = latest_snapshot.get("risk_report") or {}
    return int(risk_report.get("score") or 0)


def _build_install_telemetry(
    *,
    skill_row: Skill,
    snapshot_row: SkillSnapshot | None,
    observations: list[SkillRegistryObservation],
) -> dict[str, Any]:
    metric_observations = _aggregate_metric_observations(observations)
    previous_weekly_installs = _previous_weekly_installs(metric_observations)
    peak_weekly_installs = _peak_weekly_installs(metric_observations)
    risk_report = snapshot_row.risk_report if snapshot_row is not None else {}
    current_weekly_installs = skill_row.current_total_installs
    current_weekly_installs_observed_at = skill_row.current_total_installs_observed_at
    if current_weekly_installs is None:
        current_weekly_installs = skill_row.current_weekly_installs
        current_weekly_installs_observed_at = skill_row.current_weekly_installs_observed_at
    metrics = compute_priority_metrics(
        risk_score=int((risk_report or {}).get("score") or 0),
        severity=str((risk_report or {}).get("severity") or "none"),
        confidence=(risk_report or {}).get("confidence"),
        current_weekly_installs=current_weekly_installs,
        previous_weekly_installs=previous_weekly_installs,
        peak_weekly_installs=peak_weekly_installs,
    )
    return {
        "current_weekly_installs": current_weekly_installs,
        "current_weekly_installs_observed_at": _isoformat_datetime(
            current_weekly_installs_observed_at
        ),
        "peak_weekly_installs": metrics.peak_weekly_installs,
        "weekly_installs_delta": metrics.install_delta,
        "impact_score": metrics.impact_score,
        "priority_score": metrics.priority_score,
    }


def _resolved_total_installs(skill_row: Skill) -> int | None:
    if skill_row.current_total_installs is not None:
        return skill_row.current_total_installs
    return skill_row.current_weekly_installs


def _resolved_total_installs_observed_at(skill_row: Skill) -> datetime | None:
    if skill_row.current_total_installs_observed_at is not None:
        return _coerce_datetime_utc(skill_row.current_total_installs_observed_at)
    return _coerce_datetime_utc(skill_row.current_weekly_installs_observed_at)


def _serialize_source_entry(
    source_entry: SkillSourceEntry,
    registry_source: RegistrySource,
    registry_sync_run: RegistrySyncRun | None,
) -> dict[str, Any]:
    return {
        "id": source_entry.id,
        "registry_source_id": registry_source.id,
        "source_name": registry_source.name,
        "source_base_url": registry_source.base_url,
        "source_url": source_entry.source_url,
        "source_native_id": source_entry.source_native_id,
        "current_registry_sync_run_id": source_entry.current_registry_sync_run_id,
        "current_registry_sync_observed_at": _isoformat_datetime(
            source_entry.current_registry_sync_observed_at
        ),
        "view": registry_sync_run.view if registry_sync_run is not None else "all-time",
        "weekly_installs": source_entry.weekly_installs,
        "registry_rank": source_entry.registry_rank,
        "first_seen_at": _isoformat_datetime(source_entry.first_seen_at),
        "last_seen_at": _isoformat_datetime(source_entry.last_seen_at),
        "raw_payload": source_entry.raw_payload,
    }


def _primary_source_entry(source_entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not source_entries:
        return None
    return sorted(
        source_entries,
        key=lambda entry: (
            _registry_source_priority(entry["source_name"]),
            -1 * _sort_weekly_installs_value(entry["weekly_installs"]),
            entry["source_url"],
        ),
    )[0]


def _should_replace_registry_url(
    *,
    existing_url: str,
    incoming_url: str,
    incoming_source: str,
) -> bool:
    existing_source = _registry_source_from_url(existing_url)
    return _registry_source_priority(incoming_source) < _registry_source_priority(existing_source)


def _registry_source_from_url(url: str | None) -> str | None:
    if not url:
        return None
    lowered = url.casefold()
    if "skills.sh" in lowered:
        return "skills.sh"
    if "skillsmp.com" in lowered:
        return "skillsmp"
    return None


def _registry_source_priority(source: str | None) -> int:
    if source == "skills.sh":
        return 0
    if source == "skillsmp":
        return 1
    return 99


def _aggregate_metric_observations(
    observations: list[SkillRegistryObservation],
) -> list[tuple[datetime, int | None]]:
    directory_fetches = [
        row for row in observations if row.observation_kind == "directory_fetch"
    ]
    metric_observations = directory_fetches or observations
    grouped_installs: dict[datetime, list[int | None]] = {}
    for row in metric_observations:
        observed_at = _coerce_datetime_utc(row.observed_at)
        if observed_at is None:
            continue
        grouped_installs.setdefault(observed_at, []).append(row.weekly_installs)

    aggregated = []
    for observed_at in sorted(grouped_installs):
        installs = [value for value in grouped_installs[observed_at] if value is not None]
        aggregated.append((observed_at, sum(installs) if installs else None))
    return aggregated


def _previous_weekly_installs(
    observations: list[tuple[datetime, int | None]],
) -> int | None:
    for _, installs in reversed(observations[:-1]):
        if installs is not None:
            return installs
    return None


def _peak_weekly_installs(
    observations: list[tuple[datetime, int | None]],
) -> int | None:
    known_installs = [installs for _, installs in observations if installs is not None]
    if not known_installs:
        return None
    return max(known_installs)


def _serialize_install_history(
    observations: list[SkillRegistryObservation],
) -> list[dict[str, Any]]:
    return [
        {
            "id": row.id,
            "skill_id": row.skill_id,
            "registry_sync_run_id": row.registry_sync_run_id,
            "repo_snapshot_id": row.repo_snapshot_id,
            "observed_at": _isoformat_datetime(row.observed_at),
            "weekly_installs": row.weekly_installs,
            "registry_rank": row.registry_rank,
            "observation_kind": row.observation_kind,
            "raw_payload": row.raw_payload,
        }
        for row in observations
    ]


def _build_install_breakdown(source_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_name": entry["source_name"],
            "weekly_installs": entry["weekly_installs"],
            "source_url": entry["source_url"],
            "registry_rank": entry["registry_rank"],
        }
        for entry in source_entries
    ]


_LOW_SIGNAL_HOSTS = {
    "localhost",
    "github.com",
    "www.github.com",
    "raw.githubusercontent.com",
    "api.github.com",
    "example.com",
}


def _is_low_signal_infrastructure_indicator(
    *,
    indicator_type: str,
    indicator_value: str,
) -> bool:
    normalized_value = indicator_value.casefold().strip()
    if indicator_type == "domain":
        if normalized_value in _LOW_SIGNAL_HOSTS:
            return True
        if normalized_value.endswith(".example.com") or normalized_value.endswith(".example.org"):
            return True
        return False
    if indicator_type == "ip":
        try:
            address = ipaddress.ip_address(normalized_value)
        except ValueError:
            return False
        return (
            address.is_loopback
            or address.is_private
            or address.is_multicast
            or address.is_reserved
            or address.is_link_local
        )
    return False


def _normalize_indicator_value(indicator_type: str, indicator_value: str) -> str:
    value = indicator_value.strip()
    if indicator_type in {"domain", "hostname", "ip", "sha256"}:
        return value.lower()
    return value


def _isoformat_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    value = _coerce_datetime_utc(value)
    if value is None:
        return None
    return value.isoformat()


def _coerce_datetime_utc(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _validate_registry_observation_provenance(
    *,
    observation_kind: str,
    registry_sync_run_id: int | None,
    repo_snapshot_id: int | None,
) -> None:
    if observation_kind == "directory_fetch":
        if registry_sync_run_id is None:
            raise ValueError("directory_fetch requires registry_sync_run_id")
        return

    if observation_kind == "scan_attribution":
        if repo_snapshot_id is None:
            raise ValueError("scan_attribution requires repo_snapshot_id")
        return

    raise ValueError(f"Invalid observation_kind: {observation_kind}")
