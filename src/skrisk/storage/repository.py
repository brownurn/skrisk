"""Repository methods for the initial API and ingestion flows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from skrisk.storage.models import ExternalVerdict, Skill, SkillRepo, SkillRepoSnapshot, SkillSnapshot


class SkillRepository:
    """High-level persistence operations used by tests and the API."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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
                    next_scan_at=datetime.now(UTC) + timedelta(hours=scan_interval_hours),
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
            return {
                "tracked_repos": int(tracked_repos or 0),
                "tracked_skills": int(tracked_skills or 0),
                "critical_skills": int(critical_skills or 0),
                "high_risk_skills": int(high_risk_skills or 0),
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
