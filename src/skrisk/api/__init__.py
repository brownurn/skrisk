"""FastAPI application factory for SK Risk."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse

from skrisk.api.routes import build_router
from skrisk.config import Settings, load_settings
from skrisk.storage.database import create_session_factory, init_db


def create_app(session_factory=None, *, settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI app with storage-bound routes."""
    settings = settings or load_settings()

    if session_factory is None:
        session_factory = create_session_factory(settings.database_url)

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

    app.include_router(build_router(session_factory))

    frontend_dist_root = settings.frontend_dist_root.resolve()

    def frontend_index_response() -> Response:
        index_path = frontend_dist_root / "index.html"
        if not index_path.exists():
            return HTMLResponse(
                (
                    "<html><body><h1>SK Risk frontend build not found.</h1>"
                    "<p>Run <code>cd frontend && npm install && npm run build</code> "
                    "before starting <code>skrisk serve</code>.</p></body></html>"
                ),
                status_code=503,
            )
        return FileResponse(index_path)

    def resolve_frontend_asset(full_path: str) -> Path | None:
        candidate = (frontend_dist_root / full_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(frontend_dist_root)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> Response:
        return frontend_index_response()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_route(full_path: str) -> Response:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        asset_path = resolve_frontend_asset(full_path)
        if asset_path is not None:
            return FileResponse(asset_path)

        return frontend_index_response()

    return app
