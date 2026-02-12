"""Tests for user activity tracking (Step 12).

Verifies:
- UserRepo.touch_activity updates last_activity_at.
- ActivityMiddleware fires after successful handler execution.
- ActivityMiddleware is silent on failures (doesn't break handler flow).
- Non-user updates and missing sessions are gracefully skipped.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.middlewares import ActivityMiddleware
from app.db.models import User
from app.db.repos import UserRepo


# ---------------------------------------------------------------------------
# DB integration tests: UserRepo.touch_activity
# ---------------------------------------------------------------------------


class TestTouchActivity:
    """Test UserRepo.touch_activity with real SQLite DB."""

    async def test_updates_last_activity(self, session: AsyncSession, test_user: User) -> None:
        """touch_activity sets last_activity_at to approximately now."""
        assert test_user.last_activity_at is None

        before = datetime.now(timezone.utc).replace(tzinfo=None)
        await UserRepo.touch_activity(session, test_user.tg_user_id)
        await session.flush()

        # Re-fetch from DB to verify
        result = await session.execute(select(User).where(User.id == test_user.id))
        user = result.scalar_one()
        assert user.last_activity_at is not None
        # SQLite strips tzinfo, so compare naive datetimes
        ts = user.last_activity_at.replace(tzinfo=None) if user.last_activity_at.tzinfo else user.last_activity_at
        assert ts >= before
        assert ts <= datetime.now(timezone.utc).replace(tzinfo=None)

    async def test_updates_existing_timestamp(self, session: AsyncSession, test_user: User) -> None:
        """Subsequent touch_activity updates to a newer timestamp."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        test_user.last_activity_at = old_time
        await session.flush()

        await UserRepo.touch_activity(session, test_user.tg_user_id)
        await session.flush()

        result = await session.execute(select(User).where(User.id == test_user.id))
        user = result.scalar_one()
        assert user.last_activity_at is not None
        assert user.last_activity_at > old_time

    async def test_noop_for_nonexistent_user(self, session: AsyncSession) -> None:
        """touch_activity is a silent no-op if user doesn't exist."""
        # Should not raise
        await UserRepo.touch_activity(session, 999999999)
        await session.flush()


# ---------------------------------------------------------------------------
# Middleware unit tests: ActivityMiddleware
# ---------------------------------------------------------------------------


def _make_message_update(tg_user_id: int) -> MagicMock:
    """Create a mock Update with a message from a user."""
    from aiogram.types import Update

    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = tg_user_id
    update.callback_query = None
    # Make isinstance check work
    update.__class__ = Update
    return update


def _make_callback_update(tg_user_id: int) -> MagicMock:
    """Create a mock Update with a callback_query from a user."""
    from aiogram.types import Update

    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = MagicMock()
    update.callback_query.from_user = MagicMock()
    update.callback_query.from_user.id = tg_user_id
    update.__class__ = Update
    return update


def _make_update_no_user() -> MagicMock:
    """Create a mock Update with no user info."""
    from aiogram.types import Update

    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = None
    update.__class__ = Update
    return update


class TestActivityMiddleware:
    """Test ActivityMiddleware behavior."""

    @pytest.mark.asyncio
    async def test_touches_activity_on_message(self) -> None:
        """Message update → touch_activity called with correct tg_user_id."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(return_value="handler_result")
        event = _make_message_update(tg_user_id=12345)
        mock_session = AsyncMock(spec=AsyncSession)
        data: dict = {"session": mock_session}

        with patch.object(UserRepo, "touch_activity", new_callable=AsyncMock) as mock_touch:
            result = await middleware(handler, event, data)

        assert result == "handler_result"
        handler.assert_called_once_with(event, data)
        mock_touch.assert_called_once_with(mock_session, 12345)

    @pytest.mark.asyncio
    async def test_touches_activity_on_callback(self) -> None:
        """Callback update → touch_activity called with correct tg_user_id."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(return_value="cb_result")
        event = _make_callback_update(tg_user_id=67890)
        mock_session = AsyncMock(spec=AsyncSession)
        data: dict = {"session": mock_session}

        with patch.object(UserRepo, "touch_activity", new_callable=AsyncMock) as mock_touch:
            result = await middleware(handler, event, data)

        assert result == "cb_result"
        mock_touch.assert_called_once_with(mock_session, 67890)

    @pytest.mark.asyncio
    async def test_skips_non_update_events(self) -> None:
        """Non-Update events → handler called, no touch."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(return_value="ok")
        event = MagicMock()  # Not an Update
        data: dict = {"session": AsyncMock()}

        with patch.object(UserRepo, "touch_activity", new_callable=AsyncMock) as mock_touch:
            result = await middleware(handler, event, data)

        assert result == "ok"
        mock_touch.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_update_without_user(self) -> None:
        """Update without user info → handler called, no touch."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(return_value="ok")
        event = _make_update_no_user()
        data: dict = {"session": AsyncMock()}

        with patch.object(UserRepo, "touch_activity", new_callable=AsyncMock) as mock_touch:
            result = await middleware(handler, event, data)

        assert result == "ok"
        mock_touch.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_session(self) -> None:
        """No session in data → handler called, no touch."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(return_value="ok")
        event = _make_message_update(tg_user_id=12345)
        data: dict = {}

        with patch.object(UserRepo, "touch_activity", new_callable=AsyncMock) as mock_touch:
            result = await middleware(handler, event, data)

        assert result == "ok"
        mock_touch.assert_not_called()

    @pytest.mark.asyncio
    async def test_touch_failure_does_not_break_handler(self) -> None:
        """If touch_activity raises, handler result is still returned."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(return_value="important_result")
        event = _make_message_update(tg_user_id=12345)
        mock_session = AsyncMock(spec=AsyncSession)
        data: dict = {"session": mock_session}

        with patch.object(
            UserRepo, "touch_activity", new_callable=AsyncMock, side_effect=RuntimeError("DB error")
        ):
            result = await middleware(handler, event, data)

        # Handler result preserved despite touch failure
        assert result == "important_result"

    @pytest.mark.asyncio
    async def test_uses_savepoint_for_touch(self) -> None:
        """Touch runs inside begin_nested() savepoint."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(return_value="ok")
        event = _make_message_update(tg_user_id=12345)
        mock_session = AsyncMock(spec=AsyncSession)
        data: dict = {"session": mock_session}

        with patch.object(UserRepo, "touch_activity", new_callable=AsyncMock):
            await middleware(handler, event, data)

        # Verify begin_nested was used as async context manager
        mock_session.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_exception_propagates_without_touch(self) -> None:
        """If handler raises, exception propagates and no touch is attempted."""
        middleware = ActivityMiddleware()
        handler = AsyncMock(side_effect=ValueError("handler failed"))
        event = _make_message_update(tg_user_id=12345)
        data: dict = {"session": AsyncMock()}

        with patch.object(UserRepo, "touch_activity", new_callable=AsyncMock) as mock_touch:
            with pytest.raises(ValueError, match="handler failed"):
                await middleware(handler, event, data)

        # Touch should NOT be called when handler raises
        mock_touch.assert_not_called()


# ---------------------------------------------------------------------------
# Savepoint isolation test (P1 review fix)
# ---------------------------------------------------------------------------


class TestSavepointIsolation:
    """Verify failed touch doesn't corrupt the main transaction."""

    async def test_failed_touch_preserves_session(
        self, session: AsyncSession, test_user: User
    ) -> None:
        """DB error in touch_activity → savepoint rolls back, session still usable.

        Simulates the scenario from P1 review: if touch raises a DB error,
        the main transaction should remain intact and subsequent commits
        should succeed.
        """
        from sqlalchemy import select as sa_select

        # Perform a normal operation (update goal)
        test_user.goal = "deficit"
        await session.flush()

        # Now simulate a failed touch inside a savepoint
        try:
            async with session.begin_nested():
                # Force an error inside the savepoint
                raise RuntimeError("simulated touch DB failure")
        except RuntimeError:
            pass  # Middleware would catch this

        # Main session should still be usable — commit should work
        await session.commit()

        # Verify the goal update survived
        result = await session.execute(
            sa_select(User).where(User.id == test_user.id)
        )
        user = result.scalar_one()
        assert user.goal == "deficit"
