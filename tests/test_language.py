"""Tests for language selection handler and repo (Step 16).

Verifies:
- /language command shows inline picker.
- lang:EN and lang:RU callbacks persist selection.
- Unknown language callback is rejected.
- Re-selection updates language cleanly.
- UserRepo.update_language round-trip.
- /language and lang: callbacks bypass timezone gate.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.bot.handlers.language import cmd_language, on_language_selected
from app.bot.keyboards import language_keyboard
from app.bot.middlewares import TimezoneGateMiddleware, _ALLOWED_COMMANDS, _TZ_CALLBACK_PREFIXES
from app.db.models import User
from app.db.repos import UserRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(tg_user_id: int = 111) -> AsyncMock:
    """Create a mock Message."""
    msg = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = tg_user_id
    msg.answer = AsyncMock()
    return msg


def _make_callback(data: str, tg_user_id: int = 111) -> AsyncMock:
    """Create a mock CallbackQuery."""
    cb = AsyncMock()
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = tg_user_id
    cb.message = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


# ---------------------------------------------------------------------------
# /language command
# ---------------------------------------------------------------------------


class TestCmdLanguage:
    """Test /language command."""

    @pytest.mark.asyncio
    async def test_shows_language_picker(self) -> None:
        """Command sends message with language keyboard."""
        msg = _make_message()
        await cmd_language(msg)
        msg.answer.assert_called_once()
        call_kwargs = msg.answer.call_args
        assert "language" in call_kwargs[0][0].lower() or "язык" in call_kwargs[0][0].lower()
        assert call_kwargs[1]["reply_markup"] is not None


# ---------------------------------------------------------------------------
# Language keyboard
# ---------------------------------------------------------------------------


class TestLanguageKeyboard:
    """Test language_keyboard builder."""

    def test_has_en_and_ru_buttons(self) -> None:
        """Keyboard contains EN and RU options."""
        kb = language_keyboard()
        buttons = kb.inline_keyboard[0]
        texts = [b.text for b in buttons]
        assert any("English" in t for t in texts)
        assert any("Русский" in t for t in texts)

    def test_callback_data(self) -> None:
        """Buttons have correct callback data."""
        kb = language_keyboard()
        buttons = kb.inline_keyboard[0]
        data = [b.callback_data for b in buttons]
        assert "lang:EN" in data
        assert "lang:RU" in data


# ---------------------------------------------------------------------------
# Language selection callback
# ---------------------------------------------------------------------------


class TestOnLanguageSelected:
    """Test lang: callback handler."""

    @pytest.mark.asyncio
    async def test_sets_en(self) -> None:
        """Selecting EN persists and confirms."""
        cb = _make_callback("lang:EN")
        mock_session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with patch.object(UserRepo, "get_or_create", return_value=mock_user) as mock_get, \
             patch.object(UserRepo, "update_language", return_value=mock_user) as mock_upd:
            await on_language_selected(cb, session=mock_session)

        mock_get.assert_called_once_with(mock_session, 111)
        mock_upd.assert_called_once_with(mock_session, mock_user.id, "EN")
        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args[0][0]
        assert "English" in text
        assert "✅" in text

    @pytest.mark.asyncio
    async def test_sets_ru(self) -> None:
        """Selecting RU persists and confirms."""
        cb = _make_callback("lang:RU")
        mock_session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with patch.object(UserRepo, "get_or_create", return_value=mock_user), \
             patch.object(UserRepo, "update_language", return_value=mock_user) as mock_upd:
            await on_language_selected(cb, session=mock_session)

        mock_upd.assert_called_once_with(mock_session, mock_user.id, "RU")
        text = cb.message.edit_text.call_args[0][0]
        assert "Русский" in text
        assert "✅" in text

    @pytest.mark.asyncio
    async def test_unknown_lang_rejected(self) -> None:
        """Unknown language code → alert, no DB write."""
        cb = _make_callback("lang:FR")
        mock_session = AsyncMock()

        with patch.object(UserRepo, "get_or_create") as mock_get:
            await on_language_selected(cb, session=mock_session)

        mock_get.assert_not_called()
        cb.answer.assert_called_once()
        assert cb.answer.call_args[1].get("show_alert") is True

    @pytest.mark.asyncio
    async def test_no_from_user_noop(self) -> None:
        """Callback with no from_user → noop."""
        cb = _make_callback("lang:EN")
        cb.from_user = None
        mock_session = AsyncMock()

        with patch.object(UserRepo, "get_or_create") as mock_get:
            await on_language_selected(cb, session=mock_session)

        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_data_noop(self) -> None:
        """Callback with no data → noop."""
        cb = _make_callback("lang:EN")
        cb.data = None
        mock_session = AsyncMock()

        with patch.object(UserRepo, "get_or_create") as mock_get:
            await on_language_selected(cb, session=mock_session)

        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_reselection_updates(self) -> None:
        """Changing language from EN to RU calls update_language with RU."""
        cb = _make_callback("lang:RU")
        mock_session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.language = "EN"  # Currently EN

        with patch.object(UserRepo, "get_or_create", return_value=mock_user), \
             patch.object(UserRepo, "update_language", return_value=mock_user) as mock_upd:
            await on_language_selected(cb, session=mock_session)

        mock_upd.assert_called_once_with(mock_session, mock_user.id, "RU")

    @pytest.mark.asyncio
    async def test_shows_main_keyboard_after(self) -> None:
        """After selection, main keyboard is shown."""
        cb = _make_callback("lang:EN")
        mock_session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with patch.object(UserRepo, "get_or_create", return_value=mock_user), \
             patch.object(UserRepo, "update_language", return_value=mock_user):
            await on_language_selected(cb, session=mock_session)

        cb.message.answer.assert_called_once()
        assert cb.message.answer.call_args[0][0] == "👇"


# ---------------------------------------------------------------------------
# DB integration — UserRepo.update_language
# ---------------------------------------------------------------------------


class TestUpdateLanguageDB:
    """Test UserRepo.update_language with real DB."""

    @pytest.mark.asyncio
    async def test_update_language_round_trip(self, session: Any) -> None:
        """Language is persisted and can be read back."""
        user = await UserRepo.get_or_create(session, 7001)
        assert user.language == "EN"  # Default

        updated = await UserRepo.update_language(session, user.id, "RU")
        assert updated.language == "RU"

        # Verify from DB
        result = await session.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one()
        assert db_user.language == "RU"

    @pytest.mark.asyncio
    async def test_update_language_case_insensitive(self, session: Any) -> None:
        """Language code is normalized to uppercase."""
        user = await UserRepo.get_or_create(session, 7002)
        updated = await UserRepo.update_language(session, user.id, "ru")
        assert updated.language == "RU"

    @pytest.mark.asyncio
    async def test_reselect_language(self, session: Any) -> None:
        """Re-selecting language updates cleanly."""
        user = await UserRepo.get_or_create(session, 7003)
        await UserRepo.update_language(session, user.id, "RU")
        updated = await UserRepo.update_language(session, user.id, "EN")
        assert updated.language == "EN"


# ---------------------------------------------------------------------------
# Timezone gate bypass
# ---------------------------------------------------------------------------


class TestTimezoneGateBypass:
    """Verify /language and lang: callbacks pass through timezone gate."""

    def test_language_command_in_allowed(self) -> None:
        """/language is in _ALLOWED_COMMANDS."""
        assert "/language" in _ALLOWED_COMMANDS

    def test_lang_callback_in_prefixes(self) -> None:
        """lang: callback prefix is in _TZ_CALLBACK_PREFIXES."""
        assert any(p.startswith("lang:") for p in _TZ_CALLBACK_PREFIXES)

    def test_language_command_bypasses_gate(self) -> None:
        """_is_always_allowed returns True for /language."""
        from tests.test_timezone_gate import _make_message_update

        update = _make_message_update(text="/language")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True

    def test_lang_callback_bypasses_gate(self) -> None:
        """_is_always_allowed returns True for lang: callback."""
        from tests.test_timezone_gate import _make_callback_update

        update = _make_callback_update(data="lang:EN")
        assert TimezoneGateMiddleware._is_always_allowed(update) is True
