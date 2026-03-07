"""FastAPI application factory for SK Risk."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from skrisk.api.dashboard import router as dashboard_router
from skrisk.api.routes import build_router
from skrisk.config import load_settings
from skrisk.storage.database import create_sqlite_session_factory, init_db


def create_app(session_factory=None) -> FastAPI:
    """Create the FastAPI app with storage-bound routes."""
    if session_factory is None:
        settings = load_settings()
        session_factory = create_sqlite_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await init_db(session_factory)
        yield

    app = FastAPI(title="SK Risk", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.db_initialized = False

    @app.middleware("http")
    async def ensure_database(request, call_next):
        if not request.app.state.db_initialized:
            await init_db(session_factory)
            request.app.state.db_initialized = True
        return await call_next(request)

    app.include_router(dashboard_router)
    app.include_router(build_router(session_factory))
    return app
