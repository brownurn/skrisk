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
    frontend_dist_root: Path = Path("frontend/build")
    skills_sh_base_url: str = "https://skills.sh"
    skillsmp_base_url: str = "https://skillsmp.com"
    skillsmp_api_key: str | None = None
    scan_interval_hours: int = 72
    default_branch: str = "main"
    abusech_auth_key: str | None = None
    vt_api_key: str | None = None
    vt_daily_budget: int = 450

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
        frontend_dist_root=Path(os.getenv("SKRISK_FRONTEND_DIST_ROOT", "frontend/build")),
        skills_sh_base_url=os.getenv("SKRISK_SKILLS_SH_BASE_URL", "https://skills.sh"),
        skillsmp_base_url=os.getenv("SKRISK_SKILLSMP_BASE_URL", "https://skillsmp.com"),
        skillsmp_api_key=os.getenv("SKILLSMP_API_KEY"),
        scan_interval_hours=int(os.getenv("SKRISK_SCAN_INTERVAL_HOURS", "72")),
        default_branch=os.getenv("SKRISK_DEFAULT_BRANCH", "main"),
        abusech_auth_key=os.getenv("ABUSECH_AUTH_KEY"),
        vt_api_key=os.getenv("VT_APIKEY"),
        vt_daily_budget=int(os.getenv("SKRISK_VT_DAILY_BUDGET", "450")),
    )
