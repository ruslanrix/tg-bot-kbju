"""Tests for edit-session timeout lifecycle helpers (Step 09, PR #36 review).

Covers:
- start_timeout_task: creates task, registers in _timeout_tasks
- start_timeout_task restart: cancels previous task before starting new one
- cancel_timeout_task: cancels running task, no-op when none
- finalize_edit_session: cancels timeout + clears FSM
- _timeout_coro: edits message on expiry, removes keyboard
- _timeout_coro: exits silently when cancelled
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.meal import (
    EDIT_TIMEOUT,
    _timeout_tasks,
    cancel_timeout_task,
    finalize_edit_session,
    start_timeout_task,
)


USER_ID = 42
CHAT_ID = 100
MSG_ID = 200
TOKEN = "test-token"


@pytest.fixture(autouse=True)
def _clean_timeout_tasks():
    """Ensure _timeout_tasks is clean before/after each test."""
    _timeout_tasks.clear()
    yield
    # Cancel any lingering tasks
    for task in _timeout_tasks.values():
        task.cancel()
    _timeout_tasks.clear()


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    return bot


class TestEditTimeout:
    """Constant value check."""

    def test_edit_timeout_is_300(self) -> None:
        assert EDIT_TIMEOUT == 300


class TestStartTimeoutTask:
    """Tests for start_timeout_task."""

    @pytest.mark.asyncio
    async def test_registers_task(self) -> None:
        bot = _make_bot()
        start_timeout_task(USER_ID, CHAT_ID, MSG_ID, TOKEN, bot, "EN")
        assert USER_ID in _timeout_tasks
        assert isinstance(_timeout_tasks[USER_ID], asyncio.Task)

    @pytest.mark.asyncio
    async def test_restart_cancels_previous(self) -> None:
        bot = _make_bot()
        start_timeout_task(USER_ID, CHAT_ID, MSG_ID, TOKEN, bot, "EN")
        first_task = _timeout_tasks[USER_ID]

        start_timeout_task(USER_ID, CHAT_ID, MSG_ID, "new-token", bot, "EN")
        second_task = _timeout_tasks[USER_ID]

        # Let the event loop process the cancellation
        await asyncio.sleep(0)

        assert first_task.cancelled() or first_task.done()
        assert second_task is not first_task
        assert not second_task.done()


class TestCancelTimeoutTask:
    """Tests for cancel_timeout_task."""

    @pytest.mark.asyncio
    async def test_cancels_running_task(self) -> None:
        bot = _make_bot()
        start_timeout_task(USER_ID, CHAT_ID, MSG_ID, TOKEN, bot, "EN")
        task = _timeout_tasks.get(USER_ID)
        assert task is not None

        cancel_timeout_task(USER_ID)
        assert USER_ID not in _timeout_tasks

        # Let the event loop process the cancellation
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    def test_noop_when_no_task(self) -> None:
        """Does not raise when user has no active timeout."""
        cancel_timeout_task(USER_ID)  # should not raise
        assert USER_ID not in _timeout_tasks

    def test_noop_for_unknown_user(self) -> None:
        cancel_timeout_task(999999)  # never started
        assert 999999 not in _timeout_tasks


class TestFinalizeEditSession:
    """Tests for finalize_edit_session."""

    @pytest.mark.asyncio
    async def test_cancels_timeout_and_clears_state(self) -> None:
        bot = _make_bot()
        start_timeout_task(USER_ID, CHAT_ID, MSG_ID, TOKEN, bot, "EN")

        state = AsyncMock()
        await finalize_edit_session(state, USER_ID)

        assert USER_ID not in _timeout_tasks
        state.clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_idempotent(self) -> None:
        """Can be called multiple times safely."""
        state = AsyncMock()
        await finalize_edit_session(state, USER_ID)
        await finalize_edit_session(state, USER_ID)
        assert state.clear.await_count == 2


class TestTimeoutCoro:
    """Tests for _timeout_coro behavior via start_timeout_task."""

    @pytest.mark.asyncio
    async def test_edits_message_on_expiry(self) -> None:
        """After EDIT_TIMEOUT, the coro edits the prompt message."""
        bot = _make_bot()

        with patch("app.bot.handlers.meal.EDIT_TIMEOUT", 0.01):
            start_timeout_task(USER_ID, CHAT_ID, MSG_ID, TOKEN, bot, "EN")
            task = _timeout_tasks[USER_ID]
            await task  # wait for completion

        bot.edit_message_text.assert_awaited_once()
        call_kwargs = bot.edit_message_text.call_args.kwargs
        assert call_kwargs["chat_id"] == CHAT_ID
        assert call_kwargs["message_id"] == MSG_ID
        assert call_kwargs["reply_markup"] is None
        assert "⏱" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_removes_from_registry_on_expiry(self) -> None:
        bot = _make_bot()

        with patch("app.bot.handlers.meal.EDIT_TIMEOUT", 0.01):
            start_timeout_task(USER_ID, CHAT_ID, MSG_ID, TOKEN, bot, "EN")
            await _timeout_tasks[USER_ID]

        assert USER_ID not in _timeout_tasks

    @pytest.mark.asyncio
    async def test_silent_exit_on_cancel(self) -> None:
        """Cancelled coro does not edit the message."""
        bot = _make_bot()
        start_timeout_task(USER_ID, CHAT_ID, MSG_ID, TOKEN, bot, "EN")
        cancel_timeout_task(USER_ID)

        # Give event loop a tick to process cancellation
        await asyncio.sleep(0.01)

        bot.edit_message_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_task_exits_silently(self) -> None:
        """If a second task replaced the first, the first exits without editing."""
        bot = _make_bot()

        with patch("app.bot.handlers.meal.EDIT_TIMEOUT", 10):
            start_timeout_task(USER_ID, CHAT_ID, MSG_ID, "token-1", bot, "EN")
            first_task = _timeout_tasks[USER_ID]

        # Replace with a second task — first is cancelled
        with patch("app.bot.handlers.meal.EDIT_TIMEOUT", 10):
            start_timeout_task(USER_ID, CHAT_ID, MSG_ID, "token-2", bot, "EN")

        # Let the event loop process the cancellation
        await asyncio.sleep(0)

        # First task was cancelled by the restart
        assert first_task.cancelled() or first_task.done()

        # Give event loop a tick — no message edit should happen
        await asyncio.sleep(0.02)
        bot.edit_message_text.assert_not_awaited()

        # Clean up second task
        cancel_timeout_task(USER_ID)
