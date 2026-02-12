"""Tests for auto-save meal flow (Step 06, spec D1/FEAT-05).

Verifies:
- Meals are saved immediately after OpenAI analysis (no draft step).
- No draft_store, draft_save, draft_edit, draft_delete exist.
- Saved message includes Today's Stats and Edit/Delete keyboard.
- Edit flow updates existing meal directly.
- Idempotency check prevents duplicate saves.
- Reject actions are handled correctly.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import meal as meal_module
from app.bot.handlers.meal import _handle_analysis_result
from app.db.models import MealEntry, User
from app.services.nutrition_ai import NutritionAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    text: str = "chicken salad",
    tg_user_id: int = 111,
    chat_id: int = 222,
    message_id: int = 333,
) -> AsyncMock:
    """Build a fake Message."""
    msg = AsyncMock()
    msg.text = text
    msg.from_user = MagicMock()
    msg.from_user.id = tg_user_id
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.message_id = message_id
    msg.reply = AsyncMock()
    msg.answer = AsyncMock()
    return msg


def _make_analysis(action: str = "save") -> NutritionAnalysis:
    """Build a minimal NutritionAnalysis."""
    return NutritionAnalysis(
        action=action,
        meal_name="Chicken Salad",
        calories_kcal=350,
        protein_g=30.0,
        carbs_g=10.0,
        fat_g=15.0,
        likely_ingredients=[],
    )


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        tg_user_id=111,
        tz_mode="offset",
        tz_offset_minutes=180,
    )


def _make_meal(user: User) -> MealEntry:
    return MealEntry(
        id=uuid.uuid4(),
        user_id=user.id,
        tg_chat_id=222,
        tg_message_id=333,
        source="text",
    )


# ---------------------------------------------------------------------------
# Tests: Draft mode fully removed
# ---------------------------------------------------------------------------


class TestDraftRemoved:
    def test_no_draft_store(self) -> None:
        """draft_store should not exist in the meal module."""
        assert not hasattr(meal_module, "draft_store")

    def test_no_draft_data_class(self) -> None:
        """DraftData should not exist in the meal module."""
        assert not hasattr(meal_module, "DraftData")

    def test_no_draft_save_handler(self) -> None:
        """Original on_draft_save should not exist (replaced by legacy fallback)."""
        assert not hasattr(meal_module, "on_draft_save")

    def test_no_draft_edit_handler(self) -> None:
        """Original on_draft_edit should not exist (replaced by legacy fallback)."""
        assert not hasattr(meal_module, "on_draft_edit")

    def test_no_draft_delete_handler(self) -> None:
        """Original on_draft_delete should not exist (replaced by legacy fallback)."""
        assert not hasattr(meal_module, "on_draft_delete")

    def test_legacy_draft_fallbacks_exist(self) -> None:
        """Legacy fallback handlers should exist for backward compat."""
        assert hasattr(meal_module, "on_legacy_draft_save")
        assert hasattr(meal_module, "on_legacy_draft_edit")
        assert hasattr(meal_module, "on_legacy_draft_delete")


# ---------------------------------------------------------------------------
# Tests: Auto-save on analysis result
# ---------------------------------------------------------------------------


class TestAutoSave:
    @pytest.mark.asyncio
    async def test_save_creates_meal_immediately(self) -> None:
        """action='save' → MealRepo.create is called, reply with saved text."""
        msg = _make_message()
        analysis = _make_analysis(action="save")
        user = _make_user()
        fake_meal = _make_meal(user)

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.today_stats") as mock_stats,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.exists_by_message = AsyncMock(return_value=False)
            mock_meal_repo.create = AsyncMock(return_value=fake_meal)
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 350,
                "protein_g": 30.0,
                "carbs_g": 10.0,
                "fat_g": 15.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await _handle_analysis_result(
                msg, session, analysis, source="text", original_text="chicken salad"
            )

        # MealRepo.create should have been called
        mock_meal_repo.create.assert_called_once()
        # Reply should contain saved message with edit/delete
        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args.args[0]
        assert "Saved" in reply_text
        assert "Chicken Salad" in reply_text
        assert "Today's Stats" in reply_text
        # Should have saved_actions_keyboard
        assert "reply_markup" in msg.reply.call_args.kwargs

    @pytest.mark.asyncio
    async def test_reject_unrecognized(self) -> None:
        """action='reject_unrecognized' → no DB call, reply with error."""
        msg = _make_message()
        analysis = _make_analysis(action="reject_unrecognized")

        session = AsyncMock(spec=AsyncSession)
        await _handle_analysis_result(msg, session, analysis, source="text")

        msg.reply.assert_called_once()
        assert "recognize" in msg.reply.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_reject_custom(self) -> None:
        """action='reject_other' → reply with user_message."""
        msg = _make_message()
        analysis = _make_analysis(action="reject_not_food")
        analysis.user_message = "That doesn't look like food."

        session = AsyncMock(spec=AsyncSession)
        await _handle_analysis_result(msg, session, analysis, source="text")

        msg.reply.assert_called_once()
        assert "food" in msg.reply.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_idempotency_check_blocks_duplicate(self) -> None:
        """If meal already exists for this message, reply with 'Already saved'."""
        msg = _make_message()
        analysis = _make_analysis(action="save")
        user = _make_user()

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.exists_by_message = AsyncMock(return_value=True)

            session = AsyncMock(spec=AsyncSession)
            await _handle_analysis_result(
                msg, session, analysis, source="text", original_text="food"
            )

        mock_meal_repo.create.assert_not_called()
        msg.reply.assert_called_once()
        assert "Already saved" in msg.reply.call_args.args[0]

    @pytest.mark.asyncio
    async def test_edit_updates_existing_meal(self) -> None:
        """edit_meal_id set → MealRepo.update is called, not create."""
        msg = _make_message()
        analysis = _make_analysis(action="save")
        user = _make_user()
        existing_meal_id = uuid.uuid4()

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.today_stats") as mock_stats,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.update = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 350,
                "protein_g": 30.0,
                "carbs_g": 10.0,
                "fat_g": 15.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await _handle_analysis_result(
                msg,
                session,
                analysis,
                source="text",
                original_text="updated description",
                edit_meal_id=existing_meal_id,
            )

        # MealRepo.update called, not create
        mock_meal_repo.update.assert_called_once()
        mock_meal_repo.create.assert_not_called()
        # Reply shows saved message
        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args.args[0]
        assert "Saved" in reply_text

    @pytest.mark.asyncio
    async def test_no_from_user_returns_early(self) -> None:
        """Message without from_user returns silently."""
        msg = _make_message()
        msg.from_user = None
        analysis = _make_analysis(action="save")

        session = AsyncMock(spec=AsyncSession)
        await _handle_analysis_result(msg, session, analysis, source="text")

        msg.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_saved_text_contains_stats(self) -> None:
        """Reply should contain both meal info and Today's Stats."""
        msg = _make_message()
        analysis = _make_analysis(action="save")
        analysis.meal_name = "Grilled Salmon"
        analysis.calories_kcal = 450
        user = _make_user()
        fake_meal = _make_meal(user)

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.today_stats") as mock_stats,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.exists_by_message = AsyncMock(return_value=False)
            mock_meal_repo.create = AsyncMock(return_value=fake_meal)
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 450,
                "protein_g": 30.0,
                "carbs_g": 10.0,
                "fat_g": 15.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await _handle_analysis_result(
                msg, session, analysis, source="text", original_text="salmon"
            )

        reply_text = msg.reply.call_args.args[0]
        assert "Grilled Salmon" in reply_text
        assert "450kcal" in reply_text
        assert "Today's Stats" in reply_text


# ---------------------------------------------------------------------------
# Tests: Legacy draft callback fallbacks
# ---------------------------------------------------------------------------


class TestLegacyDraftFallbacks:
    @pytest.mark.asyncio
    async def test_legacy_draft_save_shows_alert(self) -> None:
        """Pressing old Save button shows 'draft expired' alert."""
        from app.bot.handlers.meal import on_legacy_draft_save

        cb = AsyncMock()
        cb.from_user = MagicMock()
        cb.from_user.id = 111
        cb.answer = AsyncMock()
        session = AsyncMock(spec=AsyncSession)
        with patch("app.bot.handlers.meal.UserRepo") as mock_repo:
            mock_repo.get_or_create = AsyncMock(return_value=_make_user())
            await on_legacy_draft_save(cb, session)
        cb.answer.assert_called_once()
        call_args = cb.answer.call_args
        assert "expired" in call_args.args[0].lower()
        assert call_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_legacy_draft_edit_shows_alert(self) -> None:
        """Pressing old Edit button shows 'draft expired' alert."""
        from app.bot.handlers.meal import on_legacy_draft_edit

        cb = AsyncMock()
        cb.from_user = MagicMock()
        cb.from_user.id = 111
        cb.answer = AsyncMock()
        session = AsyncMock(spec=AsyncSession)
        with patch("app.bot.handlers.meal.UserRepo") as mock_repo:
            mock_repo.get_or_create = AsyncMock(return_value=_make_user())
            await on_legacy_draft_edit(cb, session)
        cb.answer.assert_called_once()
        assert "expired" in cb.answer.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_legacy_draft_delete_shows_alert(self) -> None:
        """Pressing old Delete button shows 'draft expired' alert."""
        from app.bot.handlers.meal import on_legacy_draft_delete

        cb = AsyncMock()
        cb.from_user = MagicMock()
        cb.from_user.id = 111
        cb.answer = AsyncMock()
        session = AsyncMock(spec=AsyncSession)
        with patch("app.bot.handlers.meal.UserRepo") as mock_repo:
            mock_repo.get_or_create = AsyncMock(return_value=_make_user())
            await on_legacy_draft_delete(cb, session)
