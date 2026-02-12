"""Tests for User model new columns: language, last_activity_at, last_reminder_at."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repos import UserRepo


# ---------------------------------------------------------------------------
# language column
# ---------------------------------------------------------------------------
class TestLanguageColumn:
    @pytest.mark.asyncio
    async def test_default_language_is_en(self, session: AsyncSession) -> None:
        user = await UserRepo.get_or_create(session, tg_user_id=900001)
        assert user.language == "EN"

    @pytest.mark.asyncio
    async def test_language_round_trip(self, session: AsyncSession) -> None:
        user = await UserRepo.get_or_create(session, tg_user_id=900002)
        user.language = "RU"
        await session.flush()
        assert user.language == "RU"


# ---------------------------------------------------------------------------
# activity timestamps
# ---------------------------------------------------------------------------
class TestActivityTimestamps:
    @pytest.mark.asyncio
    async def test_last_activity_at_default_none(self, session: AsyncSession) -> None:
        user = await UserRepo.get_or_create(session, tg_user_id=900003)
        assert user.last_activity_at is None

    @pytest.mark.asyncio
    async def test_last_reminder_at_default_none(self, session: AsyncSession) -> None:
        user = await UserRepo.get_or_create(session, tg_user_id=900004)
        assert user.last_reminder_at is None

    @pytest.mark.asyncio
    async def test_last_activity_at_round_trip(self, session: AsyncSession) -> None:
        user = await UserRepo.get_or_create(session, tg_user_id=900005)
        now = datetime.now(timezone.utc)
        user.last_activity_at = now
        await session.flush()
        assert user.last_activity_at == now

    @pytest.mark.asyncio
    async def test_last_reminder_at_round_trip(self, session: AsyncSession) -> None:
        user = await UserRepo.get_or_create(session, tg_user_id=900006)
        now = datetime.now(timezone.utc)
        user.last_reminder_at = now
        await session.flush()
        assert user.last_reminder_at == now
