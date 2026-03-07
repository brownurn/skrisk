"""HTTP routes for the initial SK Risk API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from skrisk.storage.database import ensure_initialized
from skrisk.storage.repository import SkillRepository


def build_router(session_factory: async_sessionmaker[AsyncSession]) -> APIRouter:
    """Build the router bound to a repository instance."""
    router = APIRouter()
    repository = SkillRepository(session_factory)

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

    return router
