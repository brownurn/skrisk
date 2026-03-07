"""HTTP routes for the initial SK Risk API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from skrisk.config import load_settings
from skrisk.storage.database import ensure_initialized
from skrisk.storage.repository import SkillRepository


def build_router(session_factory: async_sessionmaker[AsyncSession]) -> APIRouter:
    """Build the router bound to a repository instance."""
    router = APIRouter()
    repository = SkillRepository(session_factory)
    settings = load_settings()

    @router.get("/api/stats")
    async def stats() -> dict[str, int]:
        await ensure_initialized(session_factory)
        return await repository.get_dashboard_stats()

    @router.get("/api/skills")
    async def list_skills(limit: int = 50, severity: str | None = None) -> list[dict]:
        await ensure_initialized(session_factory)
        return await repository.list_skills(limit=limit, severity=severity)

    @router.get("/api/skills/{publisher}/{repo}/{skill_slug}")
    async def skill_detail(publisher: str, repo: str, skill_slug: str) -> dict:
        await ensure_initialized(session_factory)
        detail = await repository.get_skill_detail(
            publisher=publisher,
            repo=repo,
            skill_slug=skill_slug,
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        return detail

    @router.get("/api/intel/feeds")
    async def intel_feeds(limit: int = 20) -> list[dict]:
        await ensure_initialized(session_factory)
        return await repository.list_intel_feed_runs(limit=limit)

    @router.get("/api/indicators")
    async def indicators(limit: int = 50, indicator_type: str | None = None) -> list[dict]:
        await ensure_initialized(session_factory)
        return await repository.list_indicators(limit=limit, indicator_type=indicator_type)

    @router.get("/api/indicators/{indicator_type}/{indicator_value:path}")
    async def indicator_detail(indicator_type: str, indicator_value: str) -> dict:
        await ensure_initialized(session_factory)
        detail = await repository.get_indicator_detail(indicator_type, indicator_value)
        if detail is None:
            raise HTTPException(status_code=404, detail="Indicator not found")
        return detail

    @router.get("/api/queue/vt")
    async def vt_queue() -> dict:
        await ensure_initialized(session_factory)
        return await repository.get_vt_queue_status(daily_budget=settings.vt_daily_budget)

    return router
