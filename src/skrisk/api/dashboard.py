"""HTML dashboard routes for SK Risk."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from skrisk.storage.database import ensure_initialized
from skrisk.storage.repository import SkillRepository


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard_overview(request: Request) -> HTMLResponse:
    await ensure_initialized(request.app.state.session_factory)
    repository = SkillRepository(request.app.state.session_factory)
    stats = await repository.get_dashboard_stats()
    top_skills = await repository.list_skills(limit=10, severity="critical")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "top_skills": top_skills,
        },
    )


@router.get("/skills/{publisher}/{repo}/{skill_slug}", response_class=HTMLResponse)
async def skill_detail_page(
    request: Request,
    publisher: str,
    repo: str,
    skill_slug: str,
) -> HTMLResponse:
    await ensure_initialized(request.app.state.session_factory)
    repository = SkillRepository(request.app.state.session_factory)
    detail = await repository.get_skill_detail(
        publisher=publisher,
        repo=repo,
        skill_slug=skill_slug,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return templates.TemplateResponse(
        request,
        "skill_detail.html",
        {
            "skill": detail,
        },
    )
