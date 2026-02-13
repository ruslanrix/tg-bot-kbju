"""Full FEAT-04 test coverage — edit feedback flow (Step 13).

Covers:
1. Edit start: prompt message + two-button keyboard + FSM binding
2. Feedback text routing: "120 г", "вода", "поел" routed to edit flow
3. Photo-in-edit-state: rejection prompt, continued waiting
4. edit_ok callback: cancels state, edits prompt, no meal changes
5. edit_delete callback: soft-deletes, cancels state, edits prompt
6. Stale callback protection: no active session → alert, no side effects
7. Second edit cancelling first: old prompt marked as replaced
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.meal import (
    EditMealStates,
    _handle_edit_text,
    handle_photo,
    on_edit_delete,
    on_edit_ok,
    on_saved_edit,
)
from app.db.models import MealEntry, User
from app.i18n import t


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(tg_user_id: int = 111) -> User:
    return User(
        id=uuid.uuid4(),
        tg_user_id=tg_user_id,
        tz_mode="offset",
        tz_offset_minutes=180,
    )


def _make_meal(user: User, consumed_hours_ago: float = 1.0) -> MealEntry:
    consumed_at = datetime.now(timezone.utc) - timedelta(hours=consumed_hours_ago)
    return MealEntry(
        id=uuid.uuid4(),
        user_id=user.id,
        tg_chat_id=222,
        tg_message_id=333,
        source="text",
        original_text="chicken breast 200g",
        meal_name="Chicken Breast",
        calories_kcal=330,
        protein_g=62.0,
        carbs_g=0.0,
        fat_g=7.2,
        local_date=consumed_at.date(),
        consumed_at_utc=consumed_at,
    )


def _make_saved_edit_callback(
    meal_id: uuid.UUID, tg_user_id: int = 111
) -> AsyncMock:
    """Build a fake CallbackQuery for saved_edit:<meal_id>."""
    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = tg_user_id
    cb.data = f"saved_edit:{meal_id}"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    prompt_msg = MagicMock()
    prompt_msg.chat = MagicMock()
    prompt_msg.chat.id = 222
    prompt_msg.message_id = 999
    cb.message.answer = AsyncMock(return_value=prompt_msg)
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    cb.bot.edit_message_text = AsyncMock()
    return cb


def _make_edit_ok_callback(
    meal_id: uuid.UUID, tg_user_id: int = 111
) -> AsyncMock:
    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = tg_user_id
    cb.data = f"edit_ok:{meal_id}"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_edit_delete_callback(
    meal_id: uuid.UUID, tg_user_id: int = 111
) -> AsyncMock:
    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = tg_user_id
    cb.data = f"edit_delete:{meal_id}"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_text_message(text: str = "updated chicken", tg_user_id: int = 111) -> AsyncMock:
    msg = AsyncMock()
    msg.text = text
    msg.photo = None
    msg.from_user = MagicMock()
    msg.from_user.id = tg_user_id
    msg.chat = MagicMock()
    msg.chat.id = 222
    msg.message_id = 444
    msg.reply = AsyncMock()
    msg.answer = AsyncMock()
    return msg


def _make_photo_message(tg_user_id: int = 111) -> AsyncMock:
    msg = AsyncMock()
    msg.text = None
    msg.caption = None
    photo = MagicMock()
    photo.file_size = 1024
    photo.file_id = "photo123"
    msg.photo = [photo]
    msg.from_user = MagicMock()
    msg.from_user.id = tg_user_id
    msg.chat = MagicMock()
    msg.chat.id = 222
    msg.message_id = 555
    msg.reply = AsyncMock()
    msg.answer = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# 1. Edit start: prompt message + keyboard + FSM binding
# ---------------------------------------------------------------------------


class TestEditStartPrompt:
    """on_saved_edit sends new prompt message with keyboard and binds FSM."""

    @pytest.mark.asyncio
    async def test_sends_prompt_with_keyboard(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_saved_edit_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.edit_window_hours", 48),
            patch("app.bot.handlers.meal.start_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            session = AsyncMock(spec=AsyncSession)
            await on_saved_edit(cb, session, state)

        # New prompt message sent (not edit of original)
        cb.message.answer.assert_called_once()
        kwargs = cb.message.answer.call_args.kwargs
        assert kwargs.get("reply_markup") is not None
        # Original meal message NOT edited
        cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_fsm_state_and_data_bound(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_saved_edit_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.edit_window_hours", 48),
            patch("app.bot.handlers.meal.start_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            session = AsyncMock(spec=AsyncSession)
            await on_saved_edit(cb, session, state)

        state.set_state.assert_called_once()
        data = state.update_data.call_args.kwargs
        assert data["edit_meal_id"] == str(meal.id)
        assert "session_token" in data
        assert "prompt_chat_id" in data
        assert "prompt_message_id" in data
        assert "deadline" in data

    @pytest.mark.asyncio
    async def test_starts_timeout_task(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_saved_edit_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.edit_window_hours", 48),
            patch("app.bot.handlers.meal.start_timeout_task") as mock_start,
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            session = AsyncMock(spec=AsyncSession)
            await on_saved_edit(cb, session, state)

        mock_start.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Feedback text routing — precheck-rejected text must pass in edit state
# ---------------------------------------------------------------------------


class TestFeedbackTextRouting:
    """Text like 'вода', 'поел', '120 г' must be treated as feedback, not rejected."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("text", ["вода", "поел", "120 г", "ням"])
    async def test_precheck_rejected_text_passes_in_edit_state(self, text: str) -> None:
        """Text that check_text would reject is processed as feedback."""
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=1.0)
        msg = _make_text_message(text)

        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "edit_meal_id": str(meal.id),
            "prompt_chat_id": 222,
            "prompt_message_id": 999,
        })
        state.clear = AsyncMock()
        bot = AsyncMock()

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal._check_limits", return_value=True),
            patch("app.bot.handlers.meal._analyze_with_typing", return_value=None) as mock_analyze,
            patch("app.bot.handlers.meal.edit_window_hours", 48),
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            session = AsyncMock(spec=AsyncSession)
            await _handle_edit_text(msg, session, bot, state)

        # Processing message was sent (msg_processing_edit)
        proc_reply = msg.reply.call_args_list[0]
        assert t("msg_processing_edit", "EN") in proc_reply.args[0]
        # _analyze_with_typing was called (reached OpenAI, not rejected)
        mock_analyze.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Photo in edit state — rejection + continued waiting
# ---------------------------------------------------------------------------


class TestPhotoInEditState:
    """Photo during edit state gets rejection warning, FSM stays active."""

    @pytest.mark.asyncio
    async def test_photo_rejected_with_warning(self) -> None:
        user = _make_user()
        msg = _make_photo_message()
        state = AsyncMock()
        state.get_state = AsyncMock(
            return_value=EditMealStates.waiting_for_text.state
        )
        bot = AsyncMock()

        with patch("app.bot.handlers.meal.UserRepo") as ur:
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await handle_photo(msg, session, bot, state)

        # Should reply with photo warning
        msg.reply.assert_called_once()
        warning_text = msg.reply.call_args.args[0]
        assert warning_text == t("edit_feedback_photo_warning", "EN")

    @pytest.mark.asyncio
    async def test_photo_does_not_clear_fsm(self) -> None:
        """FSM state remains active after photo rejection."""
        user = _make_user()
        msg = _make_photo_message()
        state = AsyncMock()
        state.get_state = AsyncMock(
            return_value=EditMealStates.waiting_for_text.state
        )
        bot = AsyncMock()

        with patch("app.bot.handlers.meal.UserRepo") as ur:
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await handle_photo(msg, session, bot, state)

        # FSM should NOT be cleared — still waiting for text
        state.clear.assert_not_called()
        state.set_state.assert_not_called()


# ---------------------------------------------------------------------------
# 4. edit_ok callback
# ---------------------------------------------------------------------------


class TestEditOkCallback:
    """✅ OK button finalizes session, edits prompt, never modifies meal."""

    @pytest.mark.asyncio
    async def test_ok_edits_prompt_to_ok_status(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_edit_ok_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"edit_meal_id": str(meal.id)})
        state.clear = AsyncMock()

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_ok(cb, session, state)

        # Prompt edited to OK status
        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args.args[0]
        assert text == t("edit_feedback_ok", "EN")
        # reply_markup=None (keyboard removed)
        assert cb.message.edit_text.call_args.kwargs.get("reply_markup") is None

    @pytest.mark.asyncio
    async def test_ok_clears_fsm(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_edit_ok_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"edit_meal_id": str(meal.id)})
        state.clear = AsyncMock()

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_ok(cb, session, state)

        state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_ok_never_modifies_meal(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_edit_ok_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"edit_meal_id": str(meal.id)})
        state.clear = AsyncMock()

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_ok(cb, session, state)

        # No meal modifications
        mr.update.assert_not_called()
        mr.soft_delete.assert_not_called()


# ---------------------------------------------------------------------------
# 5. edit_delete callback
# ---------------------------------------------------------------------------


class TestEditDeleteCallback:
    """🛑 Delete button soft-deletes meal, finalizes session, edits prompt."""

    @pytest.mark.asyncio
    async def test_delete_soft_deletes_meal(self) -> None:
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=1.0)
        cb = _make_edit_delete_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"edit_meal_id": str(meal.id)})
        state.clear = AsyncMock()

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            mr.soft_delete = AsyncMock(return_value=True)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_delete(cb, session, state)

        mr.soft_delete.assert_called_once_with(session, meal.id, user.id)

    @pytest.mark.asyncio
    async def test_delete_edits_prompt_to_deleted_status(self) -> None:
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=1.0)
        cb = _make_edit_delete_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"edit_meal_id": str(meal.id)})
        state.clear = AsyncMock()

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            mr.soft_delete = AsyncMock(return_value=True)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_delete(cb, session, state)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args.args[0]
        assert text == t("edit_feedback_deleted", "EN")
        assert cb.message.edit_text.call_args.kwargs.get("reply_markup") is None

    @pytest.mark.asyncio
    async def test_delete_clears_fsm(self) -> None:
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=1.0)
        cb = _make_edit_delete_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"edit_meal_id": str(meal.id)})
        state.clear = AsyncMock()

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            mr.soft_delete = AsyncMock(return_value=True)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_delete(cb, session, state)

        state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_outside_window_blocked(self) -> None:
        user = _make_user()
        meal = _make_meal(user, consumed_hours_ago=72.0)
        cb = _make_edit_delete_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"edit_meal_id": str(meal.id)})

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.delete_window_hours", 48),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_delete(cb, session, state)

        mr.soft_delete.assert_not_called()
        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True


# ---------------------------------------------------------------------------
# 6. Stale callback protection
# ---------------------------------------------------------------------------


class TestStaleCallbackProtection:
    """Stale callbacks (no active session) are rejected with alert."""

    @pytest.mark.asyncio
    async def test_stale_ok_shows_timeout_alert(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_edit_ok_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})  # no active session

        with patch("app.bot.handlers.meal.UserRepo") as ur:
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_ok(cb, session, state)

        # Alert shown
        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True
        # Prompt NOT edited
        cb.message.edit_text.assert_not_called()
        # FSM NOT cleared (nothing to clear)
        state.clear.assert_not_called()

    @pytest.mark.asyncio
    async def test_stale_delete_shows_timeout_alert(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_edit_delete_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})  # no active session

        with patch("app.bot.handlers.meal.UserRepo") as ur:
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_delete(cb, session, state)

        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True
        cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_mismatched_meal_id_delete_rejected(self) -> None:
        """Delete callback with different meal_id than active session."""
        user = _make_user()
        meal = _make_meal(user)
        other_meal_id = uuid.uuid4()
        cb = _make_edit_delete_callback(other_meal_id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "edit_meal_id": str(meal.id),  # different from callback
        })

        with patch("app.bot.handlers.meal.UserRepo") as ur:
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_delete(cb, session, state)

        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True
        cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_mismatched_meal_id_ok_rejected(self) -> None:
        """OK callback with different meal_id than active session."""
        user = _make_user()
        meal = _make_meal(user)
        other_meal_id = uuid.uuid4()
        cb = _make_edit_ok_callback(other_meal_id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "edit_meal_id": str(meal.id),  # different from callback
        })

        with patch("app.bot.handlers.meal.UserRepo") as ur:
            ur.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock(spec=AsyncSession)
            await on_edit_ok(cb, session, state)

        # Alert shown, no finalize, no prompt edit
        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True
        cb.message.edit_text.assert_not_called()
        state.clear.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Second edit cancelling first
# ---------------------------------------------------------------------------


class TestSecondEditCancelsFirst:
    """Starting a new edit cancels previous session and marks old prompt."""

    @pytest.mark.asyncio
    async def test_old_prompt_marked_replaced(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_saved_edit_callback(meal.id)
        state = AsyncMock()
        # Simulate active session with previous prompt
        state.get_data = AsyncMock(return_value={
            "edit_meal_id": str(uuid.uuid4()),
            "prompt_chat_id": 222,
            "prompt_message_id": 888,
            "session_token": "old-token",
        })

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.edit_window_hours", 48),
            patch("app.bot.handlers.meal.start_timeout_task"),
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            session = AsyncMock(spec=AsyncSession)
            await on_saved_edit(cb, session, state)

        # Old prompt should be edited to "replaced" status
        cb.bot.edit_message_text.assert_called_once()
        call_kwargs = cb.bot.edit_message_text.call_args.kwargs
        assert call_kwargs["chat_id"] == 222
        assert call_kwargs["message_id"] == 888
        assert call_kwargs["reply_markup"] is None
        assert t("edit_feedback_replaced", "EN") in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_new_prompt_sent_after_cancel(self) -> None:
        user = _make_user()
        meal = _make_meal(user)
        cb = _make_saved_edit_callback(meal.id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "edit_meal_id": str(uuid.uuid4()),
            "prompt_chat_id": 222,
            "prompt_message_id": 888,
        })

        with (
            patch("app.bot.handlers.meal.UserRepo") as ur,
            patch("app.bot.handlers.meal.MealRepo") as mr,
            patch("app.bot.handlers.meal.edit_window_hours", 48),
            patch("app.bot.handlers.meal.start_timeout_task"),
            patch("app.bot.handlers.meal.cancel_timeout_task"),
        ):
            ur.get_or_create = AsyncMock(return_value=user)
            mr.get_by_id = AsyncMock(return_value=meal)
            session = AsyncMock(spec=AsyncSession)
            await on_saved_edit(cb, session, state)

        # New prompt still sent
        cb.message.answer.assert_called_once()
        state.set_state.assert_called_once()
