"""Regression tests: no standalone 👇 emoji in goals/stats callbacks (FIX-01).

Verifies that after goal selection and stats period selection, the bot
does NOT send a standalone pointing-down emoji message.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.goals import on_goal_selected
from app.bot.handlers.stats import on_stats_today, on_stats_weekly, on_stats_4weeks
from app.db.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(tg_user_id: int = 111, lang: str = "EN") -> User:
    return User(
        id=uuid.uuid4(),
        tg_user_id=tg_user_id,
        tz_mode="offset",
        tz_offset_minutes=180,
        language=lang,
    )


def _make_callback(data: str, tg_user_id: int = 111) -> AsyncMock:
    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = tg_user_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _assert_no_emoji(cb: AsyncMock) -> None:
    """Assert no call to message.answer contains standalone 👇."""
    for call in cb.message.answer.call_args_list:
        assert "👇" not in str(call), "Standalone 👇 emoji message must not be sent"


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------


class TestGoalNoEmoji:
    """After selecting a goal, no standalone 👇 message is sent."""

    @pytest.mark.asyncio
    async def test_goal_maintenance_no_emoji(self) -> None:
        user = _make_user()
        cb = _make_callback("goal:maintenance")

        with (
            patch("app.bot.handlers.goals.UserRepo") as mock_user_repo,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_user_repo.update_goal = AsyncMock()

            session = AsyncMock(spec=AsyncSession)
            await on_goal_selected(cb, session)

        cb.message.edit_text.assert_called_once()
        _assert_no_emoji(cb)

    @pytest.mark.asyncio
    async def test_goal_deficit_no_emoji(self) -> None:
        user = _make_user()
        cb = _make_callback("goal:deficit")

        with (
            patch("app.bot.handlers.goals.UserRepo") as mock_user_repo,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_user_repo.update_goal = AsyncMock()

            session = AsyncMock(spec=AsyncSession)
            await on_goal_selected(cb, session)

        cb.message.edit_text.assert_called_once()
        _assert_no_emoji(cb)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStatsNoEmoji:
    """After viewing stats, no standalone 👇 message is sent."""

    @pytest.mark.asyncio
    async def test_stats_today_no_emoji(self) -> None:
        user = _make_user()
        cb = _make_callback("stats:today")

        with (
            patch("app.bot.handlers.stats.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.stats.today_stats") as mock_stats,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_stats.return_value = {
                "date": "2026-01-01",
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_stats_today(cb, session)

        cb.message.edit_text.assert_called_once()
        _assert_no_emoji(cb)

    @pytest.mark.asyncio
    async def test_stats_weekly_no_emoji(self) -> None:
        user = _make_user()
        cb = _make_callback("stats:weekly")

        with (
            patch("app.bot.handlers.stats.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.stats.weekly_stats") as mock_stats,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_stats.return_value = []

            session = AsyncMock(spec=AsyncSession)
            await on_stats_weekly(cb, session)

        cb.message.edit_text.assert_called_once()
        _assert_no_emoji(cb)

    @pytest.mark.asyncio
    async def test_stats_4weeks_no_emoji(self) -> None:
        user = _make_user()
        cb = _make_callback("stats:4weeks")

        with (
            patch("app.bot.handlers.stats.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.stats.four_week_stats") as mock_stats,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_stats.return_value = []

            session = AsyncMock(spec=AsyncSession)
            await on_stats_4weeks(cb, session)

        cb.message.edit_text.assert_called_once()
        _assert_no_emoji(cb)
