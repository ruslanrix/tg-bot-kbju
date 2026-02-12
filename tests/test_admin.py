"""Tests for admin command handlers (Step 14).

Verifies:
- Admin commands respond correctly for admin users.
- Non-admin users always receive 'Not authorized.'.
- /admin_ping returns pong.
- /admin_stats returns user/meal counts.
- /admin_limits returns configuration limits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.bot.handlers.admin as admin_mod
from app.bot.handlers.admin import (
    NOT_AUTHORIZED,
    cmd_admin_limits,
    cmd_admin_ping,
    cmd_admin_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(tg_user_id: int) -> MagicMock:
    """Create a mock Message from a given user."""
    msg = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = tg_user_id
    msg.reply = AsyncMock()
    return msg


def _make_message_no_user() -> MagicMock:
    """Create a mock Message with no from_user."""
    msg = AsyncMock()
    msg.from_user = None
    msg.reply = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# /admin_ping
# ---------------------------------------------------------------------------


class TestAdminPing:
    """Test /admin_ping command."""

    @pytest.mark.asyncio
    async def test_admin_gets_pong(self) -> None:
        """Admin user → receives 'pong'."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]
        try:
            msg = _make_message(12345)
            await cmd_admin_ping(msg)
            msg.reply.assert_called_once_with("pong")
        finally:
            admin_mod.admin_ids = original

    @pytest.mark.asyncio
    async def test_non_admin_gets_not_authorized(self) -> None:
        """Non-admin user → receives 'Not authorized.'."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]
        try:
            msg = _make_message(99999)
            await cmd_admin_ping(msg)
            msg.reply.assert_called_once_with(NOT_AUTHORIZED)
        finally:
            admin_mod.admin_ids = original

    @pytest.mark.asyncio
    async def test_empty_admin_ids_blocks_all(self) -> None:
        """Empty admin_ids → all users blocked."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = []
        try:
            msg = _make_message(12345)
            await cmd_admin_ping(msg)
            msg.reply.assert_called_once_with(NOT_AUTHORIZED)
        finally:
            admin_mod.admin_ids = original

    @pytest.mark.asyncio
    async def test_no_from_user_blocked(self) -> None:
        """Message with no from_user → blocked."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]
        try:
            msg = _make_message_no_user()
            await cmd_admin_ping(msg)
            msg.reply.assert_called_once_with(NOT_AUTHORIZED)
        finally:
            admin_mod.admin_ids = original


# ---------------------------------------------------------------------------
# /admin_stats
# ---------------------------------------------------------------------------


class TestAdminStats:
    """Test /admin_stats command."""

    @pytest.mark.asyncio
    async def test_admin_gets_stats(self) -> None:
        """Admin user → receives stats with user/meal counts."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]

        mock_session = AsyncMock()
        # Mock 3 execute calls: total_users, total_meals, today_meals
        mock_result_users = MagicMock()
        mock_result_users.scalar_one.return_value = 42
        mock_result_meals = MagicMock()
        mock_result_meals.scalar_one.return_value = 150
        mock_result_today = MagicMock()
        mock_result_today.scalar_one.return_value = 7

        mock_session.execute = AsyncMock(
            side_effect=[mock_result_users, mock_result_meals, mock_result_today]
        )

        try:
            msg = _make_message(12345)
            await cmd_admin_stats(msg, session=mock_session)

            msg.reply.assert_called_once()
            text = msg.reply.call_args[0][0]
            assert "Users: 42" in text
            assert "Meals (total): 150" in text
            assert "Meals (today UTC): 7" in text
        finally:
            admin_mod.admin_ids = original

    @pytest.mark.asyncio
    async def test_non_admin_blocked(self) -> None:
        """Non-admin user → blocked, no DB queries."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]
        try:
            msg = _make_message(99999)
            mock_session = AsyncMock()
            await cmd_admin_stats(msg, session=mock_session)
            msg.reply.assert_called_once_with(NOT_AUTHORIZED)
            mock_session.execute.assert_not_called()
        finally:
            admin_mod.admin_ids = original

    @pytest.mark.asyncio
    async def test_today_uses_utc_not_local(self) -> None:
        """Verify today boundary is calculated via datetime.now(utc), not date.today()."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        try:
            msg = _make_message(12345)
            with patch("app.bot.handlers.admin.datetime", wraps=datetime) as mock_dt:
                await cmd_admin_stats(msg, session=mock_session)

            # datetime.now must be called with timezone.utc
            mock_dt.now.assert_called_once_with(timezone.utc)
        finally:
            admin_mod.admin_ids = original


# ---------------------------------------------------------------------------
# /admin_limits
# ---------------------------------------------------------------------------


class TestAdminLimits:
    """Test /admin_limits command."""

    @pytest.mark.asyncio
    async def test_admin_gets_limits(self) -> None:
        """Admin user → receives configuration limits."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]
        try:
            msg = _make_message(12345)

            with patch("app.bot.handlers.admin.get_settings") as mock_settings:
                s = mock_settings.return_value
                s.RATE_LIMIT_PER_MINUTE = 6
                s.MAX_CONCURRENT_PER_USER = 1
                s.EDIT_WINDOW_HOURS = 48
                s.DELETE_WINDOW_HOURS = 48
                s.PURGE_DELETED_AFTER_DAYS = 30
                s.REMINDER_INACTIVITY_HOURS = 6
                s.REMINDER_COOLDOWN_HOURS = 6
                s.OPENAI_MODEL = "gpt-4o-mini"
                s.OPENAI_TIMEOUT_SECONDS = 30
                s.MAX_PHOTO_BYTES = 5 * 1024 * 1024

                await cmd_admin_limits(msg)

            msg.reply.assert_called_once()
            text = msg.reply.call_args[0][0]
            assert "Rate limit: 6/min" in text
            assert "Edit window: 48h" in text
            assert "Delete window: 48h" in text
            assert "Purge after: 30d" in text
            assert "OpenAI model: gpt-4o-mini" in text
            assert "Max photo: 5120KB" in text
        finally:
            admin_mod.admin_ids = original

    @pytest.mark.asyncio
    async def test_non_admin_blocked(self) -> None:
        """Non-admin user → blocked, no settings read."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [12345]
        try:
            msg = _make_message(99999)

            with patch("app.bot.handlers.admin.get_settings") as mock_settings:
                await cmd_admin_limits(msg)
                mock_settings.assert_not_called()

            msg.reply.assert_called_once_with(NOT_AUTHORIZED)
        finally:
            admin_mod.admin_ids = original


# ---------------------------------------------------------------------------
# Multiple admins
# ---------------------------------------------------------------------------


class TestMultipleAdmins:
    """Test that multiple admin IDs are supported."""

    @pytest.mark.asyncio
    async def test_multiple_admins_allowed(self) -> None:
        """Both admin IDs can access commands."""
        original = admin_mod.admin_ids
        admin_mod.admin_ids = [111, 222]
        try:
            msg1 = _make_message(111)
            await cmd_admin_ping(msg1)
            msg1.reply.assert_called_once_with("pong")

            msg2 = _make_message(222)
            await cmd_admin_ping(msg2)
            msg2.reply.assert_called_once_with("pong")

            msg3 = _make_message(333)
            await cmd_admin_ping(msg3)
            msg3.reply.assert_called_once_with(NOT_AUTHORIZED)
        finally:
            admin_mod.admin_ids = original
