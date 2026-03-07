from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from skrisk.api import create_app
from skrisk.config import Settings
from skrisk.storage.database import create_sqlite_session_factory, init_db


@pytest.mark.asyncio
async def test_frontend_shell_reports_missing_build_cleanly(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'frontend-shell.db'}"
    session_factory = create_sqlite_session_factory(database_url)
    await init_db(session_factory)
    app = create_app(
        session_factory,
        settings=Settings(
            database_url=database_url,
            frontend_dist_root=tmp_path / "missing-build",
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 503
    assert "SK Risk frontend build not found" in response.text
    assert "npm run build" in response.text
