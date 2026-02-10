"""Async database session management.

Provides an async engine and session factory configured from
``Settings.DATABASE_URL``.  Use ``get_session()`` as an async
context manager to obtain a scoped session.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _init() -> async_sessionmaker[AsyncSession]:
    """Lazily initialise the engine and session factory."""
    global _engine, _session_factory  # noqa: PLW0603
    if _session_factory is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async session; commit on success, rollback on error."""
    factory = _init()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
