"""Git-backed skill discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess


TEXT_FILE_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".js",
    ".ts",
    ".tsx",
}


SKILL_SEARCH_LOCATIONS = (
    "skills",
    "skills/.curated",
    "skills/.experimental",
    "skills/.system",
    ".agents/skills",
    ".agent/skills",
    ".claude/skills",
)


@dataclass(slots=True, frozen=True)
class DiscoveredSkill:
    """A skill directory discovered inside a checked-out repository."""

    slug: str
    relative_path: str


def discover_skills_in_checkout(root: Path) -> list[DiscoveredSkill]:
    """Discover skill directories using the official common search locations."""

    discovered: list[DiscoveredSkill] = []
    seen_paths: set[str] = set()

    for relative_location in SKILL_SEARCH_LOCATIONS:
        base = root / relative_location
        if not base.exists():
            continue
        for skill_file in sorted(base.rglob("SKILL.md")):
            skill_dir = skill_file.parent
            relative_path = skill_dir.relative_to(root).as_posix()
            if relative_path in seen_paths:
                continue
            seen_paths.add(relative_path)
            discovered.append(
                DiscoveredSkill(
                    slug=skill_dir.name,
                    relative_path=relative_path,
                )
            )

    return discovered


def load_skill_files(skill_root: Path) -> dict[str, str]:
    """Load the text files inside a skill directory for analysis."""

    files: dict[str, str] = {}
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(".") and path.name != "SKILL.md":
            continue
        if path.suffix and path.suffix.lower() not in TEXT_FILE_EXTENSIONS and path.name != "SKILL.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files[path.relative_to(skill_root).as_posix()] = text
    return files


def compute_folder_hash(files: dict[str, str]) -> str:
    """Compute a stable content hash for a skill snapshot."""

    digest = hashlib.sha256()
    for path, content in sorted(files.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def mirror_repo_snapshot(
    *,
    source_url: str,
    destination: Path,
    ref: str | None = None,
) -> tuple[Path, str]:
    """Clone a repo snapshot into the destination and return its checkout path and commit."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        subprocess.run(["git", "-C", str(destination), "fetch", "--depth", "1", "origin"], check=True)
        if ref:
            subprocess.run(["git", "-C", str(destination), "checkout", ref], check=True)
            subprocess.run(["git", "-C", str(destination), "pull", "--ff-only", "origin", ref], check=True)
    else:
        clone_command = ["git", "clone", "--depth", "1"]
        if ref:
            clone_command.extend(["--branch", ref])
        clone_command.extend([source_url, str(destination)])
        subprocess.run(clone_command, check=True)
    commit_sha = (
        subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    return destination, commit_sha
