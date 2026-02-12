"""Tests for timezone confirmation messages (Step 05, spec D3/FEAT-04).

Verifies:
- Confirmation message matches spec: "✅ Time zone saved: <TZ>. You can change it later."
- Today's Stats block is shown after timezone save.
- City and offset flows both produce the same UX pattern.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.timezone import on_city_selected, on_offset_selected
from app.db.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_callback(data: str, tg_user_id: int = 111) -> AsyncMock:
    """Build a fake CallbackQuery."""
    cb = AsyncMock()
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = tg_user_id
    cb.message = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_user(tz_mode: str | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        tg_user_id=111,
        tz_mode=tz_mode,
    )


# ---------------------------------------------------------------------------
# City selection confirmation
# ---------------------------------------------------------------------------


class TestCityConfirmation:
    @pytest.mark.asyncio
    async def test_confirmation_message_format(self) -> None:
        """City selection shows spec-mandated confirmation text."""
        cb = _make_callback("tz_city:Europe/Moscow")
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_city_selected(cb, session)

        # Check confirmation message.
        edit_call = cb.message.edit_text.call_args
        msg = edit_call.args[0] if edit_call.args else edit_call.kwargs.get("text", "")
        assert msg == "✅ Time zone saved: Europe/Moscow. You can change it later."

    @pytest.mark.asyncio
    async def test_todays_stats_shown_after_city_save(self) -> None:
        """Today's Stats block is sent as follow-up after city TZ save."""
        cb = _make_callback("tz_city:America/New_York")
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_city_selected(cb, session)

        # Follow-up answer should contain Today's Stats.
        answer_call = cb.message.answer.call_args
        stats_msg = answer_call.args[0] if answer_call.args else ""
        assert "Today's Stats" in stats_msg
        assert "Calories" in stats_msg
        # Should have main_keyboard.
        assert "reply_markup" in answer_call.kwargs

    @pytest.mark.asyncio
    async def test_city_save_calls_update_timezone(self) -> None:
        """City selection correctly calls UserRepo.update_timezone."""
        cb = _make_callback("tz_city:Asia/Tokyo")
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_city_selected(cb, session)

        mock_repo.update_timezone.assert_called_once_with(
            session,
            user.id,
            tz_mode="city",
            tz_name="Asia/Tokyo",
            tz_offset_minutes=None,
        )


# ---------------------------------------------------------------------------
# Offset selection confirmation
# ---------------------------------------------------------------------------


class TestOffsetConfirmation:
    @pytest.mark.asyncio
    async def test_confirmation_message_format_positive(self) -> None:
        """Positive UTC offset shows spec-mandated confirmation text."""
        cb = _make_callback("tz_offset:180")  # UTC+3
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_offset_selected(cb, session)

        edit_call = cb.message.edit_text.call_args
        msg = edit_call.args[0] if edit_call.args else edit_call.kwargs.get("text", "")
        assert msg == "✅ Time zone saved: UTC+3. You can change it later."

    @pytest.mark.asyncio
    async def test_confirmation_message_format_negative(self) -> None:
        """Negative UTC offset shows correct sign."""
        cb = _make_callback("tz_offset:-300")  # UTC-5
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_offset_selected(cb, session)

        edit_call = cb.message.edit_text.call_args
        msg = edit_call.args[0] if edit_call.args else edit_call.kwargs.get("text", "")
        assert msg == "✅ Time zone saved: UTC-5. You can change it later."

    @pytest.mark.asyncio
    async def test_confirmation_message_format_zero(self) -> None:
        """UTC+0 shows correct format."""
        cb = _make_callback("tz_offset:0")  # UTC+0
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_offset_selected(cb, session)

        edit_call = cb.message.edit_text.call_args
        msg = edit_call.args[0] if edit_call.args else edit_call.kwargs.get("text", "")
        assert msg == "✅ Time zone saved: UTC+0. You can change it later."

    @pytest.mark.asyncio
    async def test_todays_stats_shown_after_offset_save(self) -> None:
        """Today's Stats block is sent after offset TZ save."""
        cb = _make_callback("tz_offset:300")
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 250,
                "protein_g": 20.0,
                "carbs_g": 30.0,
                "fat_g": 10.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_offset_selected(cb, session)

        answer_call = cb.message.answer.call_args
        stats_msg = answer_call.args[0] if answer_call.args else ""
        assert "Today's Stats" in stats_msg
        assert "250kcal" in stats_msg

    @pytest.mark.asyncio
    async def test_offset_save_calls_update_timezone(self) -> None:
        """Offset selection correctly calls UserRepo.update_timezone."""
        cb = _make_callback("tz_offset:540")  # UTC+9
        user = _make_user()

        with (
            patch("app.bot.handlers.timezone.UserRepo") as mock_repo,
            patch("app.bot.handlers.timezone.today_stats") as mock_stats,
        ):
            mock_repo.get_or_create = AsyncMock(return_value=user)
            mock_repo.update_timezone = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await on_offset_selected(cb, session)

        mock_repo.update_timezone.assert_called_once_with(
            session,
            user.id,
            tz_mode="offset",
            tz_name=None,
            tz_offset_minutes=540,
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_city_no_data_no_from_user(self) -> None:
        """City callback with no data or from_user returns early."""
        cb = _make_callback("tz_city:Europe/London")
        cb.data = None
        session = AsyncMock(spec=AsyncSession)
        await on_city_selected(cb, session)
        cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_offset_no_data(self) -> None:
        """Offset callback with no data returns early."""
        cb = _make_callback("tz_offset:0")
        cb.data = None
        session = AsyncMock(spec=AsyncSession)
        await on_offset_selected(cb, session)
        cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_from_user_city(self) -> None:
        """City callback with no from_user returns early."""
        cb = _make_callback("tz_city:Europe/London")
        cb.from_user = None
        session = AsyncMock(spec=AsyncSession)
        await on_city_selected(cb, session)
        cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_from_user_offset(self) -> None:
        """Offset callback with no from_user returns early."""
        cb = _make_callback("tz_offset:60")
        cb.from_user = None
        session = AsyncMock(spec=AsyncSession)
        await on_offset_selected(cb, session)
        cb.message.edit_text.assert_not_called()
