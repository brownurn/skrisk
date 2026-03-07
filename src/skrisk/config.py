"""Runtime configuration for SK Risk."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(slots=True, frozen=True)
class Settings:
    database_url: str = "sqlite+aiosqlite:///./skrisk.db"
    mirror_root: Path = Path("data/mirrors")
    archive_root: Path = Path("data/archive")
    skills_sh_base_url: str = "https://skills.sh"
    scan_interval_hours: int = 72
    default_branch: str = "main"

    @classmethod
    def from_env(cls) -> "Settings":
        """Compatibility helper for callers expecting a classmethod."""

        return load_settings()


def load_settings() -> Settings:
    """Load runtime settings from environment variables."""

    return Settings(
        database_url=os.getenv("SKRISK_DATABASE_URL", "sqlite+aiosqlite:///./skrisk.db"),
        mirror_root=Path(os.getenv("SKRISK_MIRROR_ROOT", "data/mirrors")),
        archive_root=Path(os.getenv("SKRISK_ARCHIVE_ROOT", "data/archive")),
        skills_sh_base_url=os.getenv("SKRISK_SKILLS_SH_BASE_URL", "https://skills.sh"),
        scan_interval_hours=int(os.getenv("SKRISK_SCAN_INTERVAL_HOURS", "72")),
        default_branch=os.getenv("SKRISK_DEFAULT_BRANCH", "main"),
    )
