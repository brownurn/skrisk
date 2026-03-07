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


class Skill(Base):
    """Logical skill tracked across repo snapshots."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("skill_repos.id"), nullable=False)
    skill_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    registry_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    repo_ref: Mapped[SkillRepo] = relationship(back_populates="skills")
    snapshots: Mapped[list["SkillSnapshot"]] = relationship(back_populates="skill")
    external_verdicts: Mapped[list["ExternalVerdict"]] = relationship(back_populates="skill")

    __table_args__ = (UniqueConstraint("repo_id", "skill_slug", name="uq_repo_skill"),)


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
