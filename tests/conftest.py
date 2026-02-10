"""Shared test fixtures for async DB tests.

Uses an in-memory SQLite database (via aiosqlite) so tests run
without an external PostgreSQL instance.  JSONB columns are
rendered as plain JSON for SQLite compatibility.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, MealEntry, User

# ---------------------------------------------------------------------------
# Make JSONB work on SQLite by substituting it with JSON at DDL time.
# ---------------------------------------------------------------------------
_original_jsonb_compile = None


@pytest.fixture
async def engine():
    """Create an async in-memory SQLite engine with all tables.

    Patches JSONB → JSON so that SQLite can create the tables.
    """
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)

    # SQLite doesn't enforce FK by default; enable it.
    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Temporarily replace JSONB columns with JSON for DDL.
    jsonb_cols = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                jsonb_cols.append((col, col.type))
                col.type = JSON()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Restore original JSONB types so models stay Postgres-ready.
    for col, original_type in jsonb_cols:
        col.type = original_type

    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    """Yield an async session bound to the test engine."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()


@pytest.fixture
async def test_user(session: AsyncSession) -> User:
    """Create and return a test user."""
    user = User(
        id=uuid.uuid4(),
        tg_user_id=123456789,
        tz_mode="offset",
        tz_offset_minutes=300,  # UTC+5
    )
    session.add(user)
    await session.flush()
    return user


def make_meal(
    user: User,
    local_date: date,
    calories: int = 500,
    protein: float = 30.0,
    carbs: float = 50.0,
    fat: float = 20.0,
    is_deleted: bool = False,
    tg_chat_id: int | None = None,
    tg_message_id: int | None = None,
) -> MealEntry:
    """Helper to build a MealEntry instance for testing."""
    return MealEntry(
        id=uuid.uuid4(),
        user_id=user.id,
        tg_chat_id=tg_chat_id or user.tg_user_id,
        tg_message_id=tg_message_id or uuid.uuid4().int % (2**63),
        source="text",
        consumed_at_utc=datetime.now(timezone.utc),
        local_date=local_date,
        meal_name="Test meal",
        calories_kcal=calories,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        is_deleted=is_deleted,
        deleted_at=datetime.now(timezone.utc) if is_deleted else None,
    )
