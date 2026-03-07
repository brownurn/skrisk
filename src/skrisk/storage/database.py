"""Async SQLAlchemy helpers for SK Risk."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from skrisk.storage.models import Base


def create_sqlite_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory and retain its engine for setup."""
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    setattr(session_factory, "engine", engine)
    setattr(session_factory, "_initialized", False)
    setattr(session_factory, "_init_lock", asyncio.Lock())
    return session_factory


async def init_db(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create all configured tables."""
    engine: AsyncEngine = getattr(session_factory, "engine")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    setattr(session_factory, "_initialized", True)


async def ensure_initialized(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create the schema on first use if it has not been initialized yet."""
    if getattr(session_factory, "_initialized", False):
        return

    lock: asyncio.Lock = getattr(session_factory, "_init_lock")
    async with lock:
        if getattr(session_factory, "_initialized", False):
            return
        await init_db(session_factory)
