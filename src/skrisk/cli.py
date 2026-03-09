"""Command-line entrypoints for SK Risk."""

from __future__ import annotations

import asyncio

import click
import uvicorn

from skrisk.api import create_app
from skrisk.config import load_settings
from skrisk.collectors.skills_sh import SkillSitemapEntry
from skrisk.collectors.skillsmp import SkillsMpClient
from skrisk.scheduler import next_scan_time
from skrisk.services.intel_sync import AbuseChSyncService
from skrisk.services.skillsmp_discovery import SkillsMpDiscoveryService
from skrisk.services.sync import GitHubSkillLoader, RegistrySnapshot, RegistrySyncService, SkillsShClient
from skrisk.services.vt_triage import VTTriageService
from skrisk.storage.database import create_sqlite_session_factory, init_db
from skrisk.storage.repository import SkillRepository


@click.group()
def cli() -> None:
    """SK Risk command group."""


@cli.command("next-scan")
@click.option("--hours", default=72, show_default=True, type=int)
def next_scan(hours: int) -> None:
    """Print the next scheduled scan time."""
    click.echo(next_scan_time(interval_hours=hours).isoformat())


@cli.command("init-db")
def init_db_command() -> None:
    """Create the configured database tables."""

    settings = load_settings()
    session_factory = create_sqlite_session_factory(settings.database_url)
    asyncio.run(init_db(session_factory))
    click.echo(f"Initialized database at {settings.database_url}")


@cli.command("init-dirs")
def init_dirs() -> None:
    """Create local data directories used by SK Risk."""
    settings = load_settings()
    settings.mirror_root.mkdir(parents=True, exist_ok=True)
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    click.echo(f"{settings.mirror_root}\n{settings.archive_root}")


@cli.command("sync-registry")
@click.option(
    "--source",
    "source_name",
    default="skills.sh",
    show_default=True,
    type=click.Choice(["skills.sh", "skillsmp"]),
)
@click.option("--query", type=str)
@click.option("--page", default=1, show_default=True, type=click.IntRange(min=1))
def sync_registry_command(source_name: str, query: str | None, page: int) -> None:
    """Fetch the public registry and persist the latest snapshots."""

    settings = load_settings()

    async def _run() -> None:
        session_factory = create_sqlite_session_factory(settings.database_url)
        await init_db(session_factory)
        settings.mirror_root.mkdir(parents=True, exist_ok=True)
        snapshot = await _fetch_registry_snapshot(
            settings=settings,
            source_name=source_name,
            query=query,
            page=page,
        )
        loader = GitHubSkillLoader(settings.mirror_root)
        summary = await RegistrySyncService(
            session_factory=session_factory,
            analyzer=SkillAnalyzer(),
        ).ingest_registry_snapshot(
            sitemap_entries=snapshot.sitemap_entries,
            audit_rows=snapshot.audit_rows,
            skill_loader=loader,
            total_skills_reported=snapshot.total_skills,
            pages_fetched=snapshot.pages_fetched,
        )
        click.echo(
            "Discovered "
            f"{len(snapshot.sitemap_entries)} unique skills from "
            f"{snapshot.total_skills or len(snapshot.sitemap_entries)} reported rows; "
            f"synchronized {summary['skills_seen']} skills across {summary['repos_seen']} repos"
        )

    from skrisk.analysis.analyzer import SkillAnalyzer

    asyncio.run(_run())


@cli.command("seed-registry")
@click.option(
    "--source",
    "source_name",
    default="skills.sh",
    show_default=True,
    type=click.Choice(["skills.sh", "skillsmp"]),
)
@click.option("--query", type=str)
@click.option("--page", default=1, show_default=True, type=click.IntRange(min=1))
def seed_registry_command(source_name: str, query: str | None, page: int) -> None:
    """Fetch the public registry and seed repo/skill metadata without deep repo analysis."""

    settings = load_settings()

    async def _run() -> None:
        session_factory = create_sqlite_session_factory(settings.database_url)
        await init_db(session_factory)
        snapshot = await _fetch_registry_snapshot(
            settings=settings,
            source_name=source_name,
            query=query,
            page=page,
        )
        summary = await RegistrySyncService(
            session_factory=session_factory,
            analyzer=SkillAnalyzer(),
        ).seed_registry_snapshot(
            sitemap_entries=snapshot.sitemap_entries,
            audit_rows=snapshot.audit_rows,
            total_skills_reported=snapshot.total_skills,
            pages_fetched=snapshot.pages_fetched,
        )
        click.echo(
            "Seeded "
            f"{summary['skills_seeded']} skills across {summary['repos_seeded']} repos "
            f"from {snapshot.total_skills or len(snapshot.sitemap_entries)} reported rows"
        )

    from skrisk.analysis.analyzer import SkillAnalyzer

    asyncio.run(_run())


@cli.command("scan-due")
@click.option("--limit-repos", default=100, show_default=True, type=click.IntRange(min=1))
def scan_due_command(limit_repos: int) -> None:
    """Scan a bounded set of repos that are due for analysis."""

    settings = load_settings()

    async def _run() -> None:
        session_factory = create_sqlite_session_factory(settings.database_url)
        await init_db(session_factory)
        settings.mirror_root.mkdir(parents=True, exist_ok=True)

        repository = SkillRepository(session_factory)
        due_repos = await repository.list_due_repos()
        due_repos = sorted(due_repos, key=_repo_sort_key)[:limit_repos]
        if not due_repos:
            click.echo("No due repos")
            return

        tracked_entries = await repository.list_registry_entries_for_repo_ids(
            [row["id"] for row in due_repos]
        )
        filtered_entries = [
            SkillSitemapEntry(
                publisher=row["publisher"],
                repo=row["repo"],
                skill_slug=row["skill_slug"],
                url=row["registry_url"],
                weekly_installs=row["weekly_installs"],
                source=row.get("source", "skills.sh"),
                source_native_id=row.get("source_native_id"),
                view=row.get("view", "all-time"),
            )
            for row in tracked_entries
        ]
        registry_observation_context_by_skill = {
            (row["publisher"], row["repo"], row["skill_slug"]): {
                "observed_at": row["weekly_installs_observed_at"],
                "registry_rank": row["registry_rank"],
                "registry_sync_run_id": row["registry_sync_run_id"],
            }
            for row in tracked_entries
        }
        loader = GitHubSkillLoader(settings.mirror_root)
        summary = await RegistrySyncService(
            session_factory=session_factory,
            analyzer=SkillAnalyzer(),
        ).ingest_registry_snapshot(
            sitemap_entries=filtered_entries,
            audit_rows=[],
            skill_loader=loader,
            record_directory_fetch=False,
            registry_observation_context_by_skill=registry_observation_context_by_skill,
        )
        click.echo(
            f"Scanned {summary['skills_seen']} skills across {summary['repos_seen']} repos "
            f"from {len(due_repos)} due repos"
        )

    from skrisk.analysis.analyzer import SkillAnalyzer

    asyncio.run(_run())


@cli.command("sync-skillsmp-discovery")
@click.argument("urls", nargs=-1)
def sync_skillsmp_discovery_command(urls: tuple[str, ...]) -> None:
    """Discover skillsmp detail pages from category/detail URLs and seed them."""

    if not urls:
        raise click.ClickException("Provide at least one skillsmp category or detail URL")

    settings = load_settings()

    async def _run() -> None:
        session_factory = create_sqlite_session_factory(settings.database_url)
        await init_db(session_factory)
        settings.archive_root.mkdir(parents=True, exist_ok=True)

        discovery = await SkillsMpDiscoveryService(settings=settings).discover_from_urls(list(urls))
        summary = await RegistrySyncService(
            session_factory=session_factory,
            analyzer=SkillAnalyzer(),
        ).seed_registry_snapshot(
            sitemap_entries=discovery.entries,
            audit_rows=[],
            total_skills_reported=len(discovery.entries),
            pages_fetched=len(discovery.archived_pages),
        )
        click.echo(
            f"Discovered {len(discovery.entries)} skills from {len(discovery.archived_pages)} archived pages; "
            f"seeded {summary['skills_seeded']} skills across {summary['repos_seeded']} repos"
        )

    from skrisk.analysis.analyzer import SkillAnalyzer

    asyncio.run(_run())


@cli.command("sync-intel")
@click.option("--provider", default="abusech", show_default=True, type=click.Choice(["abusech"]))
def sync_intel_command(provider: str) -> None:
    """Fetch bulk threat-intelligence feeds and persist the latest snapshots."""

    settings = load_settings()

    async def _run() -> None:
        session_factory = create_sqlite_session_factory(settings.database_url)
        await init_db(session_factory)
        settings.archive_root.mkdir(parents=True, exist_ok=True)

        if provider != "abusech":
            raise click.ClickException(f"Unsupported provider: {provider}")

        summary = await AbuseChSyncService(
            session_factory=session_factory,
            settings=settings,
        ).sync_all()
        click.echo(
            "Synchronized "
            f"{summary['feed_runs']} feed runs, "
            f"{summary['indicators_upserted']} indicators, "
            f"{summary['observations_recorded']} observations"
        )

    asyncio.run(_run())


@cli.command("enrich-vt")
@click.option("--limit", default=25, show_default=True, type=click.IntRange(min=1))
def enrich_vt_command(limit: int) -> None:
    """Process a bounded batch of queued VirusTotal lookups."""

    settings = load_settings()

    async def _run() -> None:
        session_factory = create_sqlite_session_factory(settings.database_url)
        await init_db(session_factory)
        settings.archive_root.mkdir(parents=True, exist_ok=True)

        summary = await VTTriageService(
            session_factory=session_factory,
            settings=settings,
        ).run_once(limit=limit)
        click.echo(
            f"{summary['lookups_completed']} VT lookups completed, "
            f"{summary['lookups_failed']} failed, "
            f"{summary['lookups_skipped_budget']} skipped for budget"
        )

    try:
        asyncio.run(_run())
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command("serve")
@click.option("--host", default=None, type=str)
@click.option("--port", default=None, type=int)
def serve(host: str | None, port: int | None) -> None:
    """Run the FastAPI app."""
    settings = load_settings()
    uvicorn.run(
        create_app(),
        host=host or "127.0.0.1",
        port=port or 8080,
    )


@cli.command("collect-once")
def collect_once() -> None:
    """Alias for a single registry sync cycle."""

    async def _run() -> None:
        settings = load_settings()
        session_factory = create_sqlite_session_factory(settings.database_url)
        await init_db(session_factory)
        settings.mirror_root.mkdir(parents=True, exist_ok=True)
        snapshot = await SkillsShClient(settings.skills_sh_base_url).fetch_snapshot()
        loader = GitHubSkillLoader(settings.mirror_root)
        summary = await RegistrySyncService(
            session_factory=session_factory,
            analyzer=SkillAnalyzer(),
        ).ingest_registry_snapshot(
            sitemap_entries=snapshot.sitemap_entries,
            audit_rows=snapshot.audit_rows,
            skill_loader=loader,
            total_skills_reported=snapshot.total_skills,
            pages_fetched=snapshot.pages_fetched,
        )
        click.echo(summary)

    from skrisk.analysis.analyzer import SkillAnalyzer

    asyncio.run(_run())


def _repo_sort_key(row: dict) -> tuple[int, int, str, str]:
    rank = row.get("registry_rank")
    return (
        1 if rank is None else 0,
        rank or 0,
        row["publisher"],
        row["repo"],
    )


async def _fetch_registry_snapshot(
    *,
    settings,
    source_name: str,
    query: str | None,
    page: int,
) -> RegistrySnapshot:
    if source_name == "skills.sh":
        return await SkillsShClient(settings.skills_sh_base_url).fetch_snapshot()

    if source_name != "skillsmp":
        raise click.ClickException(f"Unsupported registry source: {source_name}")
    if not query:
        raise click.ClickException("skillsmp registry sync requires --query")

    search_page = await SkillsMpClient(
        api_key=settings.skillsmp_api_key,
        base_url=settings.skillsmp_base_url,
    ).fetch_search_page(query, page=page)
    return RegistrySnapshot(
        sitemap_entries=search_page.entries,
        audit_rows=[],
        total_skills=search_page.total,
        pages_fetched=1,
    )
