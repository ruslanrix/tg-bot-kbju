"""Tests for TimezoneGateMiddleware (spec D2 / FEAT-03).

Verifies that:
- Users without timezone are intercepted and shown onboarding.
- /start and /help bypass the gate.
- Timezone callbacks bypass the gate.
- Users WITH timezone pass through normally.
- OpenAI is never called for users without timezone.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.middlewares import (
    ONBOARDING_TEXT_A,
    ONBOARDING_TEXT_B,
    TimezoneGateMiddleware,
    _ALLOWED_COMMANDS,
    _TZ_CALLBACK_PREFIXES,
)
from app.db.models import User


# ---------------------------------------------------------------------------
# Helpers to build fake Update objects
# ---------------------------------------------------------------------------

def _make_user(tg_id: int = 111) -> MagicMock:
    user = MagicMock()
    user.id = tg_id
    return user


def _make_message_update(
    text: str = "chicken salad",
    tg_user_id: int = 111,
    has_photo: bool = False,
) -> MagicMock:
    """Build a fake Update with a message."""
    from aiogram.types import Update

    msg = AsyncMock()
    msg.text = text
    msg.from_user = _make_user(tg_user_id)
    msg.answer = AsyncMock()
    msg.photo = [MagicMock()] if has_photo else None

    update = MagicMock(spec=Update)
    update.message = msg
    update.callback_query = None
    return update


def _make_callback_update(
    data: str = "goal:maintenance",
    tg_user_id: int = 111,
) -> MagicMock:
    """Build a fake Update with a callback_query."""
    from aiogram.types import Update

    cb = AsyncMock()
    cb.data = data
    cb.from_user = _make_user(tg_user_id)
    cb.answer = AsyncMock()
    cb.message = AsyncMock()
    cb.message.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = cb
    return update


def _make_db_user(tz_mode: str | None = None) -> User:
    """Build a fake User ORM object."""
    user = User(
        id=uuid.uuid4(),
        tg_user_id=111,
        tz_mode=tz_mode,
    )
    return user


# ---------------------------------------------------------------------------
# Tests: _extract_user_id
# ---------------------------------------------------------------------------


class TestExtractUserId:
    def test_from_message(self) -> None:
        update = _make_message_update(tg_user_id=42)
        assert TimezoneGateMiddleware._extract_user_id(update) == 42

    def test_from_callback(self) -> None:
        update = _make_callback_update(tg_user_id=99)
        assert TimezoneGateMiddleware._extract_user_id(update) == 99

    def test_no_user(self) -> None:
        from aiogram.types import Update

        update = MagicMock(spec=Update)
        update.message = None
        update.callback_query = None
        assert TimezoneGateMiddleware._extract_user_id(update) is None


# ---------------------------------------------------------------------------
# Tests: _is_always_allowed
# ---------------------------------------------------------------------------


class TestIsAlwaysAllowed:
    def test_start_command_allowed(self) -> None:
        update = _make_message_update(text="/start")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_start_with_payload_allowed(self) -> None:
        update = _make_message_update(text="/start some_payload")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_start_with_botname_blocked(self) -> None:
        """'/start@mybot' should NOT bypass — strict match mirrors Command() defaults."""
        update = _make_message_update(text="/start@mybot")
        assert TimezoneGateMiddleware._is_always_allowed(update) is False

    def test_start_uppercase_blocked(self) -> None:
        """'/START' should NOT bypass — strict case match."""
        update = _make_message_update(text="/START")
        assert TimezoneGateMiddleware._is_always_allowed(update) is False

    def test_help_command_allowed(self) -> None:
        update = _make_message_update(text="/help")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_help_uppercase_blocked(self) -> None:
        """'/HELP' should NOT bypass — strict case match."""
        update = _make_message_update(text="/HELP")
        assert TimezoneGateMiddleware._is_always_allowed(update) is False

    def test_other_command_blocked(self) -> None:
        update = _make_message_update(text="/stats")
        assert TimezoneGateMiddleware._is_always_allowed(update) is False

    def test_regular_text_blocked(self) -> None:
        update = _make_message_update(text="chicken rice")
        assert TimezoneGateMiddleware._is_always_allowed(update) is False

    def test_tz_city_callback_allowed(self) -> None:
        update = _make_callback_update(data="tz_city:Europe/Moscow")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_tz_offset_callback_allowed(self) -> None:
        update = _make_callback_update(data="tz_offset:180")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_tz_city_menu_callback_allowed(self) -> None:
        update = _make_callback_update(data="tz_city_menu")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_tz_offset_menu_callback_allowed(self) -> None:
        update = _make_callback_update(data="tz_offset_menu")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_goal_callback_blocked(self) -> None:
        update = _make_callback_update(data="goal:deficit")
        assert TimezoneGateMiddleware._is_always_allowed(update) is False

    def test_stats_callback_blocked(self) -> None:
        update = _make_callback_update(data="stats:today")
        assert TimezoneGateMiddleware._is_always_allowed(update) is False


# ---------------------------------------------------------------------------
# Tests: full middleware __call__ (integration-style)
# ---------------------------------------------------------------------------


class TestMiddlewareCall:
    @pytest.mark.asyncio
    async def test_user_with_tz_passes_through(self) -> None:
        """User with timezone set → handler is called normally."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock(return_value="ok")
        update = _make_message_update(text="chicken salad")
        user = _make_db_user(tz_mode="city")

        with patch("app.bot.middlewares.UserRepo") as mock_repo:
            mock_repo.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock()
            data: dict[str, Any] = {"session": session}
            result = await mw(handler, update, data)

        handler.assert_called_once_with(update, data)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_user_without_tz_intercepted_message(self) -> None:
        """User without timezone → message intercepted, onboarding shown."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock()
        update = _make_message_update(text="chicken salad")
        user = _make_db_user(tz_mode=None)

        with patch("app.bot.middlewares.UserRepo") as mock_repo:
            mock_repo.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock()
            data: dict[str, Any] = {"session": session}
            result = await mw(handler, update, data)

        # Handler should NOT be called.
        handler.assert_not_called()
        assert result is None

        # Onboarding messages should be sent.
        calls = update.message.answer.call_args_list
        assert len(calls) == 2
        assert calls[0].args[0] == ONBOARDING_TEXT_A
        assert calls[1].args[0] == ONBOARDING_TEXT_B
        # Second message should have timezone keyboard.
        assert "reply_markup" in calls[1].kwargs

    @pytest.mark.asyncio
    async def test_user_without_tz_callback_intercepted(self) -> None:
        """User without timezone → non-TZ callback intercepted."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock()
        update = _make_callback_update(data="goal:maintenance")
        user = _make_db_user(tz_mode=None)

        with patch("app.bot.middlewares.UserRepo") as mock_repo:
            mock_repo.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock()
            data: dict[str, Any] = {"session": session}
            result = await mw(handler, update, data)

        handler.assert_not_called()
        assert result is None
        # Should answer the callback with an alert containing "timezone".
        update.callback_query.answer.assert_called_once()
        call_str = str(update.callback_query.answer.call_args)
        assert "timezone" in call_str.lower()

    @pytest.mark.asyncio
    async def test_start_command_bypasses_gate(self) -> None:
        """/start command should bypass the gate even without TZ."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock(return_value="started")
        update = _make_message_update(text="/start")
        data: dict[str, Any] = {"session": AsyncMock()}

        result = await mw(handler, update, data)

        handler.assert_called_once_with(update, data)
        assert result == "started"

    @pytest.mark.asyncio
    async def test_help_command_bypasses_gate(self) -> None:
        """/help command should bypass the gate even without TZ."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock(return_value="helped")
        update = _make_message_update(text="/help")
        data: dict[str, Any] = {"session": AsyncMock()}

        result = await mw(handler, update, data)

        handler.assert_called_once()
        assert result == "helped"

    @pytest.mark.asyncio
    async def test_tz_callback_bypasses_gate(self) -> None:
        """Timezone selection callback should bypass the gate."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock(return_value="tz_set")
        update = _make_callback_update(data="tz_city:Europe/London")
        data: dict[str, Any] = {"session": AsyncMock()}

        result = await mw(handler, update, data)

        handler.assert_called_once()
        assert result == "tz_set"

    @pytest.mark.asyncio
    async def test_no_user_in_update_passes_through(self) -> None:
        """Update without from_user (e.g. channel post) passes through."""
        from aiogram.types import Update

        mw = TimezoneGateMiddleware()
        handler = AsyncMock(return_value="ok")
        update = MagicMock(spec=Update)
        update.message = None
        update.callback_query = None
        data: dict[str, Any] = {"session": AsyncMock()}

        result = await mw(handler, update, data)

        handler.assert_called_once()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_session_passes_through(self) -> None:
        """If session is missing from data, let handler deal with it."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock(return_value="ok")
        update = _make_message_update(text="food")
        data: dict[str, Any] = {}  # No session

        await mw(handler, update, data)

        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_photo_message_intercepted_without_tz(self) -> None:
        """Photo message without TZ should be intercepted."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock()
        update = _make_message_update(text="", has_photo=True)
        user = _make_db_user(tz_mode=None)

        with patch("app.bot.middlewares.UserRepo") as mock_repo:
            mock_repo.get_or_create = AsyncMock(return_value=user)
            session = AsyncMock()
            data: dict[str, Any] = {"session": session}
            await mw(handler, update, data)

        handler.assert_not_called()
        # Onboarding shown.
        assert update.message.answer.call_count == 2

    @pytest.mark.asyncio
    async def test_non_update_event_passes_through(self) -> None:
        """Non-Update events (e.g. ErrorEvent) pass through."""
        mw = TimezoneGateMiddleware()
        handler = AsyncMock(return_value="ok")
        event = MagicMock()  # Not an Update instance
        data: dict[str, Any] = {}

        result = await mw(handler, event, data)

        handler.assert_called_once()
        assert result == "ok"


# ---------------------------------------------------------------------------
# Tests: onboarding text constants
# ---------------------------------------------------------------------------


class TestOnboardingTexts:
    def test_text_a_contains_photo_instruction(self) -> None:
        assert "📸" in ONBOARDING_TEXT_A
        assert "pic of your meal" in ONBOARDING_TEXT_A

    def test_text_b_contains_timezone_prompt(self) -> None:
        assert "time zone" in ONBOARDING_TEXT_B
        assert "🌍" in ONBOARDING_TEXT_B

    def test_allowed_commands_include_start_and_help(self) -> None:
        assert "/start" in _ALLOWED_COMMANDS
        assert "/help" in _ALLOWED_COMMANDS

    def test_tz_callback_prefixes(self) -> None:
        assert "tz_city:" in _TZ_CALLBACK_PREFIXES
        assert "tz_offset:" in _TZ_CALLBACK_PREFIXES
        assert "tz_city_menu" in _TZ_CALLBACK_PREFIXES
        assert "tz_offset_menu" in _TZ_CALLBACK_PREFIXES
