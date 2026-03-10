"""Git-backed skill discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
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
    ".",
    "skills",
    "skills/.curated",
    "skills/.experimental",
    "skills/.system",
    ".agents/skills",
    ".agent/skills",
    ".augment/skills",
    ".claude/skills",
    ".codebuddy/skills",
    ".commandcode/skills",
    ".continue/skills",
    ".cortex/skills",
    ".crush/skills",
    ".factory/skills",
    ".goose/skills",
    ".iflow/skills",
    ".junie/skills",
    ".kiro/skills",
    ".kilocode/skills",
    ".kode/skills",
    ".mcpjam/skills",
    ".mux/skills",
    ".neovate/skills",
    ".openhands/skills",
    ".pi/skills",
    ".pochi/skills",
    ".qoder/skills",
    ".qwen/skills",
    ".roo/skills",
    ".trae/skills",
    ".vibe/skills",
    ".windsurf/skills",
    ".zencoder/skills",
)

PLUGIN_MANIFEST_PATHS = (
    ".claude-plugin/marketplace.json",
    ".claude-plugin/plugin.json",
)
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(?P<name>[^\n]+)$", re.MULTILINE)


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
        if relative_location == ".":
            skill_file = root / "SKILL.md"
            if skill_file.exists():
                discovered.append(
                    DiscoveredSkill(
                        slug=_skill_slug_from_file(skill_file),
                        relative_path=".",
                    )
                )
                seen_paths.add(".")
            continue

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
                    slug=_skill_slug_from_file(skill_file),
                    relative_path=relative_path,
                )
            )

    for relative_path in _plugin_manifest_skill_paths(root):
        if relative_path in seen_paths:
            continue
        skill_file = root / relative_path / "SKILL.md"
        if not skill_file.exists():
            continue
        seen_paths.add(relative_path)
        discovered.append(
            DiscoveredSkill(
                slug=_skill_slug_from_file(skill_file),
                relative_path=relative_path,
            )
        )

    return sorted(discovered, key=lambda skill: skill.slug)


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
            branch = _current_or_default_branch(destination)
            subprocess.run(["git", "-C", str(destination), "checkout", branch], check=True)
            subprocess.run(["git", "-C", str(destination), "reset", "--hard", f"origin/{branch}"], check=True)
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


def _skill_slug_from_file(skill_file: Path) -> str:
    try:
        content = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return skill_file.parent.name
    match = FRONTMATTER_NAME_RE.search(content)
    if match:
        return match.group("name").strip().strip('"').strip("'")
    return skill_file.parent.name


def _plugin_manifest_skill_paths(root: Path) -> set[str]:
    discovered: set[str] = set()
    for manifest_path in PLUGIN_MANIFEST_PATHS:
        full_path = root / manifest_path
        if not full_path.exists():
            continue
        try:
            payload = json.loads(full_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        plugin_root = payload.get("metadata", {}).get("pluginRoot", ".")
        plugins = payload.get("plugins", [])
        for plugin in plugins:
            if not isinstance(plugin, dict):
                continue
            raw_skill_paths = plugin.get("skills", [])
            if not isinstance(raw_skill_paths, list):
                continue
            for raw_skill_path in raw_skill_paths:
                if not isinstance(raw_skill_path, str):
                    continue
                resolved = (root / plugin_root / raw_skill_path).resolve()
                try:
                    discovered.add(resolved.relative_to(root.resolve()).as_posix())
                except ValueError:
                    continue
    return discovered


def _current_or_default_branch(destination: Path) -> str:
    current_branch = (
        subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    if current_branch != "HEAD":
        return current_branch

    remote_head = (
        subprocess.run(
            ["git", "-C", str(destination), "symbolic-ref", "refs/remotes/origin/HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    return remote_head.rsplit("/", maxsplit=1)[-1]
