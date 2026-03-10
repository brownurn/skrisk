from __future__ import annotations

from skrisk.storage.database import create_session_factory


def test_create_session_factory_normalizes_sqlite_urls(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'skrisk.db'}")

    assert str(session_factory.engine.url).startswith("sqlite+aiosqlite:///")


def test_create_session_factory_normalizes_postgres_urls() -> None:
    session_factory = create_session_factory("postgresql://skrisk:secret@db.example/skrisk")

    assert session_factory.engine.url.drivername == "postgresql+asyncpg"
