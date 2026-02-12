"""Tests for processing messages (Step 07, spec D4/FEAT-06).

Verifies:
- New analysis sends "Combobulating..." processing message.
- Edit re-analysis sends "Analysing again with your feedback..." processing message.
- Processing message is edited in place with final output.
- Error paths edit processing message with error text.
- proc_msg=None falls back to message.reply.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.meal import (
    MSG_PROCESSING_EDIT,
    MSG_PROCESSING_NEW,
    MSG_UNRECOGNIZED,
    _analyze_with_typing,
    _handle_analysis_result,
)
from app.db.models import MealEntry, User
from app.services.nutrition_ai import NutritionAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(tg_user_id: int = 111) -> AsyncMock:
    msg = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = tg_user_id
    msg.chat = MagicMock()
    msg.chat.id = 222
    msg.message_id = 333
    msg.reply = AsyncMock()
    return msg


def _make_proc_msg() -> AsyncMock:
    proc = AsyncMock()
    proc.edit_text = AsyncMock()
    return proc


def _make_analysis(action: str = "save") -> NutritionAnalysis:
    return NutritionAnalysis(
        action=action,
        meal_name="Test Meal",
        calories_kcal=300,
        protein_g=20.0,
        carbs_g=30.0,
        fat_g=10.0,
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
# Tests: Processing message constants
# ---------------------------------------------------------------------------


class TestProcessingConstants:
    def test_new_processing_message(self) -> None:
        assert "Combobulating" in MSG_PROCESSING_NEW

    def test_edit_processing_message(self) -> None:
        assert "Analysing again" in MSG_PROCESSING_EDIT
        assert "feedback" in MSG_PROCESSING_EDIT


# ---------------------------------------------------------------------------
# Tests: proc_msg editing
# ---------------------------------------------------------------------------


class TestProcMsgEditing:
    @pytest.mark.asyncio
    async def test_save_edits_proc_msg(self) -> None:
        """On save, processing message is edited with saved result."""
        msg = _make_message()
        proc = _make_proc_msg()
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
                "calories_kcal": 300,
                "protein_g": 20.0,
                "carbs_g": 30.0,
                "fat_g": 10.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await _handle_analysis_result(
                msg, session, analysis, source="text",
                original_text="food", proc_msg=proc,
            )

        # proc_msg.edit_text should be called, NOT message.reply
        proc.edit_text.assert_called_once()
        msg.reply.assert_not_called()
        # Check content
        edit_text = proc.edit_text.call_args.args[0]
        assert "Saved" in edit_text
        assert "Today's Stats" in edit_text

    @pytest.mark.asyncio
    async def test_reject_edits_proc_msg(self) -> None:
        """On reject, processing message is edited with error."""
        msg = _make_message()
        proc = _make_proc_msg()
        analysis = _make_analysis(action="reject_unrecognized")

        session = AsyncMock(spec=AsyncSession)
        await _handle_analysis_result(
            msg, session, analysis, source="text", proc_msg=proc,
        )

        proc.edit_text.assert_called_once()
        msg.reply.assert_not_called()
        assert "recognize" in proc.edit_text.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_reject_custom_edits_proc_msg(self) -> None:
        """Custom reject edits processing message."""
        msg = _make_message()
        proc = _make_proc_msg()
        analysis = _make_analysis(action="reject_not_food")
        analysis.user_message = "Not food"

        session = AsyncMock(spec=AsyncSession)
        await _handle_analysis_result(
            msg, session, analysis, source="text", proc_msg=proc,
        )

        proc.edit_text.assert_called_once()
        assert "Not food" in proc.edit_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_no_proc_msg_falls_back_to_reply(self) -> None:
        """Without proc_msg, falls back to message.reply."""
        msg = _make_message()
        analysis = _make_analysis(action="reject_unrecognized")

        session = AsyncMock(spec=AsyncSession)
        await _handle_analysis_result(
            msg, session, analysis, source="text", proc_msg=None,
        )

        msg.reply.assert_called_once()
        assert "recognize" in msg.reply.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_idempotency_edits_proc_msg(self) -> None:
        """Duplicate save edits processing message with 'Already saved'."""
        msg = _make_message()
        proc = _make_proc_msg()
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
                msg, session, analysis, source="text",
                original_text="food", proc_msg=proc,
            )

        proc.edit_text.assert_called_once()
        assert "Already saved" in proc.edit_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_edit_meal_edits_proc_msg(self) -> None:
        """Edit flow edits processing message with updated result."""
        msg = _make_message()
        proc = _make_proc_msg()
        analysis = _make_analysis(action="save")
        user = _make_user()
        meal_id = uuid.uuid4()

        with (
            patch("app.bot.handlers.meal.UserRepo") as mock_user_repo,
            patch("app.bot.handlers.meal.MealRepo") as mock_meal_repo,
            patch("app.bot.handlers.meal.today_stats") as mock_stats,
        ):
            mock_user_repo.get_or_create = AsyncMock(return_value=user)
            mock_meal_repo.update = AsyncMock()
            mock_stats.return_value = {
                "date": date.today(),
                "calories_kcal": 300,
                "protein_g": 20.0,
                "carbs_g": 30.0,
                "fat_g": 10.0,
            }

            session = AsyncMock(spec=AsyncSession)
            await _handle_analysis_result(
                msg, session, analysis, source="text",
                original_text="updated", edit_meal_id=meal_id, proc_msg=proc,
            )

        proc.edit_text.assert_called_once()
        assert "Saved" in proc.edit_text.call_args.args[0]


# ---------------------------------------------------------------------------
# Tests: Throttle edits proc_msg (P2 review fix)
# ---------------------------------------------------------------------------


class TestThrottleEditsProcMsg:
    @pytest.mark.asyncio
    async def test_concurrency_guard_edits_proc_msg_with_throttle(self) -> None:
        """When concurrency guard rejects, proc_msg shows throttle text, not unrecognized."""
        msg = _make_message()
        proc = _make_proc_msg()
        bot = AsyncMock()

        # Fake concurrency guard that rejects (acquired=False)
        class FakeCtx:
            acquired = False

        class FakeGuard:
            def __call__(self, uid: int):  # noqa: ANN204
                return self

            async def __aenter__(self):  # noqa: ANN204
                return FakeCtx()

            async def __aexit__(self, *args: object) -> None:
                pass

        with (
            patch("app.bot.handlers.meal.ai_service", new=MagicMock()),
            patch("app.bot.handlers.meal.concurrency_guard", new=FakeGuard()),
        ):
            result = await _analyze_with_typing(
                msg, bot, lambda svc: svc.analyze_text("food"),
                proc_msg=proc,
            )

        assert result is None
        proc.edit_text.assert_called_once()
        assert "wait" in proc.edit_text.call_args.args[0].lower()
        msg.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrency_guard_replies_without_proc_msg(self) -> None:
        """Without proc_msg, throttle falls back to message.reply."""
        msg = _make_message()
        bot = AsyncMock()

        class FakeCtx:
            acquired = False

        class FakeGuard:
            def __call__(self, uid: int):  # noqa: ANN204
                return self

            async def __aenter__(self):  # noqa: ANN204
                return FakeCtx()

            async def __aexit__(self, *args: object) -> None:
                pass

        with (
            patch("app.bot.handlers.meal.ai_service", new=MagicMock()),
            patch("app.bot.handlers.meal.concurrency_guard", new=FakeGuard()),
        ):
            result = await _analyze_with_typing(
                msg, bot, lambda svc: svc.analyze_text("food"),
                proc_msg=None,
            )

        assert result is None
        msg.reply.assert_called_once()
        assert "wait" in msg.reply.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_no_ai_service_edits_proc_msg(self) -> None:
        """When ai_service is None, proc_msg shows unrecognized text."""
        msg = _make_message()
        proc = _make_proc_msg()
        bot = AsyncMock()

        with patch("app.bot.handlers.meal.ai_service", new=None):
            result = await _analyze_with_typing(
                msg, bot, lambda svc: svc.analyze_text("food"),
                proc_msg=proc,
            )

        assert result is None
        proc.edit_text.assert_called_once()
        assert proc.edit_text.call_args.args[0] == MSG_UNRECOGNIZED
        msg.reply.assert_not_called()
