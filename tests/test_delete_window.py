"""Tests for delete window enforcement (Step 10, D6/D7/FEAT-09).

Verifies:
- Delete inside window proceeds (soft-delete).
- Delete outside window is blocked with friendly message.
- Boundary conditions.
- Missing meal returns "not found".
- Invalid UUID handled gracefully.
- Window is configurable.
- Both saved_delete and hist_delete are guarded.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.meal import (
    MSG_DELETE_WINDOW_EXPIRED,
    on_history_delete,
    on_saved_delete,
)
from app.db.models import MealEntry, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_callback(
    meal_id: uuid.UUID,
    prefix: str = "saved_delete",
    tg_user_id: int = 111,
) -> AsyncMock:
    """Build a fake CallbackQuery for delete callbacks."""
    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = tg_user_id
    cb.data = f"{prefix}:{meal_id}"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_user(tg_user_id: int = 111) -> User:
    return User(
        id=uuid.uuid4(),
        tg_user_id=tg_user_id,
        tz_mode="offset",
        tz_offset_minutes=180,
    )


def _make_meal(
    user: User,
    consumed_hours_ago: float = 1.0,
) -> MealEntry:
    """Create a MealEntry consumed *consumed_hours_ago* hours in the past."""
    consumed_at = datetime.now(timezone.utc) - timedelta(hours=consumed_hours_ago)
    return MealEntry(
        id=uuid.uuid4(),
        user_id=user.id,
        tg_chat_id=222,
        tg_message_id=333,
        source="text",
        meal_name="Test Meal",
        calories_kcal=400,
        protein_g=25.0,
        carbs_g=40.0,
        fat_g=15.0,
        local_date=consumed_at.date(),
        consumed_at_utc=consumed_at,
    )


# ---------------------------------------------------------------------------
# Tests: on_saved_delete
# ---------------------------------------------------------------------------


class TestSavedDeleteWindow:
    """Delete window blocks deletes on old meals via saved_delete callback."""

    @pytest.mark.asyncio
    async def test_delete_inside_window_proceeds(self) -> None:
        """Meal consumed 1h ago — delete should proceed."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=1.0)
        cb = _make_callback(meal.id)

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.today_stats") as mock_stats,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=meal)
            mock_meal_repo.soft_delete = AsyncMock(return_value=True)
            mock_stats.return_value = {
                "date": meal.local_date,
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_saved_delete(cb, session)

        mock_meal_repo.soft_delete.assert_called_once()
        cb.message.edit_text.assert_called_once()
        assert "Deleted" in cb.message.edit_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_delete_outside_window_blocked(self) -> None:
        """Meal consumed 72h ago — delete should be blocked."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=72.0)
        cb = _make_callback(meal.id)

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=meal)

            session = AsyncMock(spec=AsyncSession)
            await on_saved_delete(cb, session)

        mock_meal_repo.soft_delete.assert_not_called()
        cb.answer.assert_called_once()
        assert "48" in cb.answer.call_args.args[0]
        assert cb.answer.call_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_delete_just_inside_boundary(self) -> None:
        """Meal consumed 47h59m ago — should still be allowed."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=47.0 + 59 / 60)
        cb = _make_callback(meal.id)

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.today_stats") as mock_stats,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=meal)
            mock_meal_repo.soft_delete = AsyncMock(return_value=True)
            mock_stats.return_value = {
                "date": meal.local_date,
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_saved_delete(cb, session)

        mock_meal_repo.soft_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_just_past_boundary_blocked(self) -> None:
        """Meal consumed 48h + 1min ago — should be blocked."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=48.0 + 1 / 60)
        cb = _make_callback(meal.id)

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=meal)

            session = AsyncMock(spec=AsyncSession)
            await on_saved_delete(cb, session)

        mock_meal_repo.soft_delete.assert_not_called()
        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_meal_not_found(self) -> None:
        """Non-existent or deleted meal — show 'not found' alert."""
        user = _make_user()
        cb = _make_callback(uuid.uuid4())

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=None)

            session = AsyncMock(spec=AsyncSession)
            await on_saved_delete(cb, session)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args.args[0].lower()
        assert cb.answer.call_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_invalid_uuid(self) -> None:
        """Corrupted callback_data with invalid UUID → 'Meal not found.' alert."""
        cb = AsyncMock()
        cb.from_user = MagicMock()
        cb.from_user.id = 111
        cb.data = "saved_delete:not-a-uuid"
        cb.answer = AsyncMock()

        session = AsyncMock(spec=AsyncSession)
        await on_saved_delete(cb, session)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args.args[0].lower()
        assert cb.answer.call_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_custom_window_blocks(self) -> None:
        """Custom window of 24h — meal at 25h should be blocked."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=25.0)
        cb = _make_callback(meal.id)

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.delete_window_hours", 24),
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=meal)

            session = AsyncMock(spec=AsyncSession)
            await on_saved_delete(cb, session)

        mock_meal_repo.soft_delete.assert_not_called()
        cb.answer.assert_called_once()
        assert "24" in cb.answer.call_args.args[0]

    @pytest.mark.asyncio
    async def test_no_from_user_returns_early(self) -> None:
        """CallbackQuery without from_user returns silently."""
        cb = _make_callback(uuid.uuid4())
        cb.from_user = None

        session = AsyncMock(spec=AsyncSession)
        await on_saved_delete(cb, session)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_data_returns_early(self) -> None:
        """CallbackQuery without data returns silently."""
        cb = _make_callback(uuid.uuid4())
        cb.data = None

        session = AsyncMock(spec=AsyncSession)
        await on_saved_delete(cb, session)

        cb.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: on_history_delete
# ---------------------------------------------------------------------------


class TestHistoryDeleteWindow:
    """Delete window also applies to hist_delete callback."""

    @pytest.mark.asyncio
    async def test_delete_inside_window_proceeds(self) -> None:
        """Meal consumed 1h ago via history — delete should proceed."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=1.0)
        cb = _make_callback(meal.id, prefix="hist_delete")

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.today_stats") as mock_stats,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=meal)
            mock_meal_repo.soft_delete = AsyncMock(return_value=True)
            mock_stats.return_value = {
                "date": meal.local_date,
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_history_delete(cb, session)

        mock_meal_repo.soft_delete.assert_called_once()
        cb.message.edit_text.assert_called_once()
        assert "Deleted" in cb.message.edit_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_delete_outside_window_blocked(self) -> None:
        """Meal consumed 72h ago via history — delete should be blocked."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=72.0)
        cb = _make_callback(meal.id, prefix="hist_delete")

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=meal)

            session = AsyncMock(spec=AsyncSession)
            await on_history_delete(cb, session)

        mock_meal_repo.soft_delete.assert_not_called()
        cb.answer.assert_called_once()
        assert "48" in cb.answer.call_args.args[0]
        assert cb.answer.call_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_meal_not_found(self) -> None:
        """Non-existent meal via history — show 'not found' alert."""
        user = _make_user()
        cb = _make_callback(uuid.uuid4(), prefix="hist_delete")

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.get_by_id = AsyncMock(return_value=None)

            session = AsyncMock(spec=AsyncSession)
            await on_history_delete(cb, session)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_invalid_uuid(self) -> None:
        """Invalid UUID via history — graceful handling."""
        cb = AsyncMock()
        cb.from_user = MagicMock()
        cb.from_user.id = 111
        cb.data = "hist_delete:garbage"
        cb.answer = AsyncMock()

        session = AsyncMock(spec=AsyncSession)
        await on_history_delete(cb, session)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args.args[0].lower()


# ---------------------------------------------------------------------------
# Tests: message format
# ---------------------------------------------------------------------------


class TestDeleteWindowMessage:
    """Verify the MSG_DELETE_WINDOW_EXPIRED format string."""

    def test_message_contains_hours(self) -> None:
        msg = MSG_DELETE_WINDOW_EXPIRED.format(hours=48)
        assert "48" in msg

    def test_message_contains_emoji(self) -> None:
        msg = MSG_DELETE_WINDOW_EXPIRED.format(hours=48)
        assert "⏳" in msg

    def test_message_mentions_deleted(self) -> None:
        msg = MSG_DELETE_WINDOW_EXPIRED.format(hours=24)
        assert "deleted" in msg.lower()
