"""Ingestion helpers that turn a local checkout into persisted snapshots."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from skrisk.analysis.analyzer import SkillAnalyzer
from skrisk.collectors.github import discover_skills_in_checkout
from skrisk.storage.repository import SkillRepository


TEXT_FILE_SUFFIXES = {
    ".md",
    ".txt",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".yaml",
    ".yml",
}


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
    registry_urls = registry_urls or {}
    analyzer = SkillAnalyzer()

    repo_id = await repository.upsert_skill_repo(
        publisher=publisher,
        repo=repo,
        source_url=source_url,
        registry_rank=None,
    )
    discovered_skills = discover_skills_in_checkout(checkout_root)
    repo_snapshot_id = await repository.record_repo_snapshot(
        repo_id=repo_id,
        commit_sha=commit_sha,
        default_branch=default_branch,
        discovered_skill_count=len(discovered_skills),
    )

    for discovered in discovered_skills:
        skill_root = checkout_root / discovered.relative_path
        files = _read_text_files(skill_root)
        report = analyzer.analyze_skill(
            publisher=publisher,
            repo=repo,
            skill_slug=discovered.slug,
            files=files,
        )
        skill_id = await repository.upsert_skill(
            repo_id=repo_id,
            skill_slug=discovered.slug,
            title=discovered.slug,
            relative_path=discovered.relative_path,
            registry_url=registry_urls.get(
                discovered.slug,
                f"https://skills.sh/{publisher}/{repo}/{discovered.slug}",
            ),
        )
        await repository.record_skill_snapshot(
            skill_id=skill_id,
            repo_snapshot_id=repo_snapshot_id,
            folder_hash=_folder_hash(files),
            version_label=f"{default_branch}@{commit_sha}",
            skill_text=files.get("SKILL.md", ""),
            referenced_files=sorted(files),
            extracted_domains=report.domains,
            risk_report={
                "severity": report.severity,
                "score": report.score,
                "categories": [finding.category for finding in report.findings],
            },
        )


def _read_text_files(skill_root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_FILE_SUFFIXES and path.name != "SKILL.md":
            continue
        files[path.relative_to(skill_root).as_posix()] = path.read_text(encoding="utf-8")
    return files


def _folder_hash(files: dict[str, str]) -> str:
    digest = sha256()
    for relative_path, content in sorted(files.items()):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
