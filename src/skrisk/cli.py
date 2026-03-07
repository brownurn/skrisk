"""Command-line entrypoints for SK Risk."""

from __future__ import annotations

import asyncio

import click
import uvicorn

from skrisk.api import create_app
from skrisk.config import load_settings
from skrisk.scheduler import next_scan_time
from skrisk.services.intel_sync import AbuseChSyncService
from skrisk.services.sync import GitHubSkillLoader, RegistrySyncService, SkillsShClient
from skrisk.services.vt_triage import VTTriageService
from skrisk.storage.database import create_sqlite_session_factory, init_db


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
def sync_registry_command() -> None:
    """Fetch the public registry and persist the latest snapshots."""

    settings = load_settings()

    async def _run() -> None:
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
        )
        click.echo(
            f"Synchronized {summary['skills_seen']} skills across {summary['repos_seen']} repos"
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
        )
        click.echo(summary)

    from skrisk.analysis.analyzer import SkillAnalyzer

    asyncio.run(_run())
