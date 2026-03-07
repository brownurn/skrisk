"""Command-line entrypoints for SK Risk."""

from __future__ import annotations

import asyncio

import click
import uvicorn

from skrisk.api import create_app
from skrisk.config import load_settings
from skrisk.scheduler import next_scan_time
from skrisk.services.sync import GitHubSkillLoader, RegistrySyncService, SkillsShClient
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
