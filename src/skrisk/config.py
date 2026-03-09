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
    mewhois_url: str = "http://127.0.0.1:18191"
    meip_url: str = "http://127.0.0.1:18190"
    opensearch_url: str = "http://127.0.0.1:9200"
    opensearch_index_name: str = "skrisk-skills"
    neo4j_http_url: str = "http://127.0.0.1:7474"
    neo4j_database: str = "neo4j"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "skriskneo4j"
    require_search_runtime: bool = False
    require_graph_runtime: bool = False
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

    opensearch_port = os.getenv("SKRISK_OPENSEARCH_PORT", "9200")
    neo4j_http_port = os.getenv("SKRISK_NEO4J_HTTP_PORT", "7474")
    mewhois_port = os.getenv("SKRISK_MEWHOIS_PORT", "18191")
    meip_port = os.getenv("SKRISK_MEIP_PORT", "18190")

    return Settings(
        database_url=os.getenv("SKRISK_DATABASE_URL", "sqlite+aiosqlite:///./skrisk.db"),
        mirror_root=Path(os.getenv("SKRISK_MIRROR_ROOT", "data/mirrors")),
        archive_root=Path(os.getenv("SKRISK_ARCHIVE_ROOT", "data/archive")),
        frontend_dist_root=Path(os.getenv("SKRISK_FRONTEND_DIST_ROOT", "frontend/build")),
        skills_sh_base_url=os.getenv("SKRISK_SKILLS_SH_BASE_URL", "https://skills.sh"),
        skillsmp_base_url=os.getenv("SKRISK_SKILLSMP_BASE_URL", "https://skillsmp.com"),
        skillsmp_api_key=os.getenv("SKILLSMP_API_KEY"),
        mewhois_url=os.getenv("SKRISK_MEWHOIS_URL", f"http://127.0.0.1:{mewhois_port}"),
        meip_url=os.getenv("SKRISK_MEIP_URL", f"http://127.0.0.1:{meip_port}"),
        opensearch_url=os.getenv("SKRISK_OPENSEARCH_URL", f"http://127.0.0.1:{opensearch_port}"),
        opensearch_index_name=os.getenv("SKRISK_OPENSEARCH_INDEX_NAME", "skrisk-skills"),
        neo4j_http_url=os.getenv("SKRISK_NEO4J_HTTP_URL", f"http://127.0.0.1:{neo4j_http_port}"),
        neo4j_database=os.getenv("SKRISK_NEO4J_DATABASE", "neo4j"),
        neo4j_user=os.getenv("SKRISK_NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("SKRISK_NEO4J_PASSWORD", "skriskneo4j"),
        require_search_runtime=os.getenv("SKRISK_REQUIRE_OPENSEARCH", "0") == "1",
        require_graph_runtime=os.getenv("SKRISK_REQUIRE_NEO4J", "0") == "1",
        scan_interval_hours=int(os.getenv("SKRISK_SCAN_INTERVAL_HOURS", "72")),
        default_branch=os.getenv("SKRISK_DEFAULT_BRANCH", "main"),
        abusech_auth_key=os.getenv("ABUSECH_AUTH_KEY"),
        vt_api_key=os.getenv("VT_APIKEY"),
        vt_daily_budget=int(os.getenv("SKRISK_VT_DAILY_BUDGET", "450")),
    )
