"""Persistence models for the initial SK Risk slice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base with JSON support for simple list/dict columns."""

    type_annotation_map = {
        dict[str, Any]: JSON,
        list[str]: JSON,
    }


class SkillRepo(Base):
    """Source repository discovered through the registry."""

    __tablename__ = "skill_repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    registry_rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    skills: Mapped[list["Skill"]] = relationship(back_populates="repo_ref")
    snapshots: Mapped[list["SkillRepoSnapshot"]] = relationship(back_populates="repo_ref")

    __table_args__ = (UniqueConstraint("publisher", "repo", name="uq_skill_repo"),)


class SkillRepoSnapshot(Base):
    """Point-in-time snapshot of a repository head."""

    __tablename__ = "skill_repo_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("skill_repos.id"), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    discovered_skill_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repo_ref: Mapped[SkillRepo] = relationship(back_populates="snapshots")
    skill_snapshots: Mapped[list["SkillSnapshot"]] = relationship(back_populates="repo_snapshot")
    registry_observations: Mapped[list["SkillRegistryObservation"]] = relationship(
        back_populates="repo_snapshot"
    )


class RegistrySource(Base):
    """A first-class source registry such as skills.sh or skillsmp."""

    __tablename__ = "registry_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    skill_entries: Mapped[list["SkillSourceEntry"]] = relationship(back_populates="registry_source")

    __table_args__ = (UniqueConstraint("name", name="uq_registry_source_name"),)


class Skill(Base):
    """Logical skill tracked across repo snapshots."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("skill_repos.id"), nullable=False)
    skill_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    registry_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    current_weekly_installs: Mapped[int | None] = mapped_column(Integer)
    current_weekly_installs_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    current_total_installs: Mapped[int | None] = mapped_column(Integer)
    current_total_installs_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    current_registry_rank: Mapped[int | None] = mapped_column(Integer)
    current_registry_sync_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("registry_sync_runs.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    repo_ref: Mapped[SkillRepo] = relationship(back_populates="skills")
    snapshots: Mapped[list["SkillSnapshot"]] = relationship(back_populates="skill")
    external_verdicts: Mapped[list["ExternalVerdict"]] = relationship(back_populates="skill")
    current_registry_sync_run: Mapped["RegistrySyncRun | None"] = relationship(
        back_populates="current_skills",
        foreign_keys=[current_registry_sync_run_id],
    )
    registry_observations: Mapped[list["SkillRegistryObservation"]] = relationship(
        back_populates="skill"
    )
    source_entries: Mapped[list["SkillSourceEntry"]] = relationship(back_populates="skill")

    __table_args__ = (UniqueConstraint("repo_id", "skill_slug", name="uq_repo_skill"),)


class SkillSourceEntry(Base):
    """Registry-specific provenance for a canonical skill."""

    __tablename__ = "skill_source_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    registry_source_id: Mapped[int] = mapped_column(ForeignKey("registry_sources.id"), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_native_id: Mapped[str | None] = mapped_column(String(255))
    weekly_installs: Mapped[int | None] = mapped_column(Integer)
    registry_rank: Mapped[int | None] = mapped_column(Integer)
    current_registry_sync_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("registry_sync_runs.id")
    )
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    skill: Mapped[Skill] = relationship(back_populates="source_entries")
    registry_source: Mapped[RegistrySource] = relationship(back_populates="skill_entries")
    current_registry_sync_run: Mapped["RegistrySyncRun | None"] = relationship(
        foreign_keys=[current_registry_sync_run_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "skill_id",
            "registry_source_id",
            "source_url",
            name="uq_skill_source_entry",
        ),
        UniqueConstraint(
            "skill_id",
            "registry_source_id",
            "source_native_id",
            name="uq_skill_source_native_entry",
        ),
    )


class SkillSnapshot(Base):
    """Snapshot of a skill folder at a specific repo snapshot."""

    __tablename__ = "skill_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    repo_snapshot_id: Mapped[int] = mapped_column(ForeignKey("skill_repo_snapshots.id"), nullable=False)
    folder_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    version_label: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_text: Mapped[str] = mapped_column(Text, nullable=False)
    referenced_files: Mapped[list[str]] = mapped_column(nullable=False, default=list)
    extracted_domains: Mapped[list[str]] = mapped_column(nullable=False, default=list)
    risk_report: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    skill: Mapped[Skill] = relationship(back_populates="snapshots")
    repo_snapshot: Mapped[SkillRepoSnapshot] = relationship(back_populates="skill_snapshots")
    indicator_links: Mapped[list["SkillIndicatorLink"]] = relationship(back_populates="skill_snapshot")

    __table_args__ = (
        UniqueConstraint("skill_id", "repo_snapshot_id", name="uq_skill_snapshot_observation"),
    )


class ExternalVerdict(Base):
    """Third-party verdict attached to a tracked skill."""

    __tablename__ = "external_verdicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    partner: Mapped[str] = mapped_column(String(100), nullable=False)
    verdict: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    skill: Mapped[Skill] = relationship(back_populates="external_verdicts")


class RegistrySyncRun(Base):
    """Directory crawl metadata for install telemetry observations."""

    __tablename__ = "registry_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    view: Mapped[str] = mapped_column(String(255), nullable=False)
    total_skills_reported: Mapped[int | None] = mapped_column(Integer)
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(nullable=False, default=True)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    observations: Mapped[list["SkillRegistryObservation"]] = relationship(
        back_populates="registry_sync_run"
    )
    current_skills: Mapped[list["Skill"]] = relationship(
        back_populates="current_registry_sync_run",
        foreign_keys="Skill.current_registry_sync_run_id",
    )


class SkillRegistryObservation(Base):
    """Historical install telemetry observations for a skill."""

    __tablename__ = "skill_registry_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    registry_sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("registry_sync_runs.id"))
    repo_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("skill_repo_snapshots.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    weekly_installs: Mapped[int | None] = mapped_column(Integer)
    registry_rank: Mapped[int | None] = mapped_column(Integer)
    observation_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    skill: Mapped[Skill] = relationship(back_populates="registry_observations")
    registry_sync_run: Mapped[RegistrySyncRun | None] = relationship(back_populates="observations")
    repo_snapshot: Mapped[SkillRepoSnapshot | None] = relationship(
        back_populates="registry_observations"
    )


class IntelFeedRun(Base):
    """Download and parse run for a bulk intelligence feed."""

    __tablename__ = "intel_feed_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    feed_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    auth_mode: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    archive_sha256: Mapped[str] = mapped_column(String(255), nullable=False)
    archive_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    artifacts: Mapped[list["IntelFeedArtifact"]] = relationship(back_populates="feed_run")
    observations: Mapped[list["IndicatorObservation"]] = relationship(back_populates="feed_run")


class IntelFeedArtifact(Base):
    """Immutable file tied to an intelligence feed run."""

    __tablename__ = "intel_feed_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_run_id: Mapped[int] = mapped_column(ForeignKey("intel_feed_runs.id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    feed_run: Mapped[IntelFeedRun] = relationship(back_populates="artifacts")


class Indicator(Base):
    """Canonical IOC identity across skills and external feeds."""

    __tablename__ = "indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(String(100), nullable=False)
    indicator_value: Mapped[str] = mapped_column(String(2000), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(2000), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    observations: Mapped[list["IndicatorObservation"]] = relationship(back_populates="indicator")
    skill_links: Mapped[list["SkillIndicatorLink"]] = relationship(back_populates="indicator")
    enrichments: Mapped[list["IndicatorEnrichment"]] = relationship(back_populates="indicator")
    vt_queue_items: Mapped[list["VTLookupQueueItem"]] = relationship(back_populates="indicator")

    __table_args__ = (
        UniqueConstraint("indicator_type", "normalized_value", name="uq_indicator_identity"),
    )


class IndicatorObservation(Base):
    """Provider-specific observation attached to a canonical indicator."""

    __tablename__ = "indicator_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicators.id"), nullable=False)
    feed_run_id: Mapped[int] = mapped_column(ForeignKey("intel_feed_runs.id"), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    source_feed: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_record_id: Mapped[str | None] = mapped_column(String(255))
    classification: Mapped[str | None] = mapped_column(String(100))
    confidence_label: Mapped[str | None] = mapped_column(String(100))
    malware_family: Mapped[str | None] = mapped_column(String(255))
    threat_type: Mapped[str | None] = mapped_column(String(255))
    reporter: Mapped[str | None] = mapped_column(String(255))
    first_seen_in_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_in_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_score: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    indicator: Mapped[Indicator] = relationship(back_populates="observations")
    feed_run: Mapped[IntelFeedRun] = relationship(back_populates="observations")


class SkillIndicatorLink(Base):
    """Skill snapshot evidence pointing at an extracted indicator."""

    __tablename__ = "skill_indicator_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_snapshot_id: Mapped[int] = mapped_column(ForeignKey("skill_snapshots.id"), nullable=False)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicators.id"), nullable=False)
    source_path: Mapped[str | None] = mapped_column(String(1000))
    extraction_kind: Mapped[str | None] = mapped_column(String(100))
    raw_value: Mapped[str | None] = mapped_column(String(2000))
    is_new_in_snapshot: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    skill_snapshot: Mapped[SkillSnapshot] = relationship(back_populates="indicator_links")
    indicator: Mapped[Indicator] = relationship(back_populates="skill_links")


class IndicatorEnrichment(Base):
    """Cached non-bulk enrichment attached to a canonical indicator."""

    __tablename__ = "indicator_enrichments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicators.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    lookup_key: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    archive_relative_path: Mapped[str | None] = mapped_column(String(2000))
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    indicator: Mapped[Indicator] = relationship(back_populates="enrichments")


class VTLookupQueueItem(Base):
    """Queued selective VT lookup for a canonical indicator."""

    __tablename__ = "vt_lookup_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicators.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    indicator: Mapped[Indicator] = relationship(back_populates="vt_queue_items")
