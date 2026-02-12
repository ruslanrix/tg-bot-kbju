"""Tests for inactivity reminder task endpoint (Step 13).

Verifies:
- UserRepo.get_inactive_users eligibility/cooldown logic.
- UserRepo.update_last_reminder sets last_reminder_at.
- /tasks/remind endpoint auth, sends reminders, handles failures.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repos import UserRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    tg_user_id: int,
    *,
    tz_mode: str | None = "offset",
    last_activity_at: datetime | None = None,
    last_reminder_at: datetime | None = None,
) -> User:
    """Create a User instance for testing."""
    return User(
        id=uuid.uuid4(),
        tg_user_id=tg_user_id,
        tz_mode=tz_mode,
        tz_offset_minutes=180,
        last_activity_at=last_activity_at,
        last_reminder_at=last_reminder_at,
    )


# ---------------------------------------------------------------------------
# DB integration tests: get_inactive_users
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)
INACTIVITY_CUTOFF = NOW - timedelta(hours=6)
COOLDOWN_CUTOFF = NOW - timedelta(hours=6)


class TestGetInactiveUsers:
    """Test UserRepo.get_inactive_users with real SQLite DB."""

    async def test_eligible_user_returned(self, session: AsyncSession) -> None:
        """User inactive >6h, no reminder → eligible."""
        user = _make_user(111, last_activity_at=NOW - timedelta(hours=8))
        session.add(user)
        await session.flush()

        result = await UserRepo.get_inactive_users(session, INACTIVITY_CUTOFF, COOLDOWN_CUTOFF)
        assert len(result) == 1
        assert result[0].tg_user_id == 111

    async def test_recently_active_user_excluded(self, session: AsyncSession) -> None:
        """User active 2h ago → not eligible."""
        user = _make_user(222, last_activity_at=NOW - timedelta(hours=2))
        session.add(user)
        await session.flush()

        result = await UserRepo.get_inactive_users(session, INACTIVITY_CUTOFF, COOLDOWN_CUTOFF)
        assert len(result) == 0

    async def test_recently_reminded_user_excluded(self, session: AsyncSession) -> None:
        """User inactive but reminded 2h ago → still in cooldown."""
        user = _make_user(
            333,
            last_activity_at=NOW - timedelta(hours=8),
            last_reminder_at=NOW - timedelta(hours=2),
        )
        session.add(user)
        await session.flush()

        result = await UserRepo.get_inactive_users(session, INACTIVITY_CUTOFF, COOLDOWN_CUTOFF)
        assert len(result) == 0

    async def test_old_reminder_user_eligible(self, session: AsyncSession) -> None:
        """User inactive, last reminder >6h ago → eligible again."""
        user = _make_user(
            444,
            last_activity_at=NOW - timedelta(hours=10),
            last_reminder_at=NOW - timedelta(hours=8),
        )
        session.add(user)
        await session.flush()

        result = await UserRepo.get_inactive_users(session, INACTIVITY_CUTOFF, COOLDOWN_CUTOFF)
        assert len(result) == 1

    async def test_no_activity_user_excluded(self, session: AsyncSession) -> None:
        """User with NULL last_activity_at → excluded (never active)."""
        user = _make_user(555, last_activity_at=None)
        session.add(user)
        await session.flush()

        result = await UserRepo.get_inactive_users(session, INACTIVITY_CUTOFF, COOLDOWN_CUTOFF)
        assert len(result) == 0

    async def test_no_timezone_user_excluded(self, session: AsyncSession) -> None:
        """User without timezone (tz_mode=None) → excluded."""
        user = _make_user(666, tz_mode=None, last_activity_at=NOW - timedelta(hours=8))
        session.add(user)
        await session.flush()

        result = await UserRepo.get_inactive_users(session, INACTIVITY_CUTOFF, COOLDOWN_CUTOFF)
        assert len(result) == 0

    async def test_mixed_users(self, session: AsyncSession) -> None:
        """Mix of eligible and ineligible users → only eligible returned."""
        eligible = _make_user(700, last_activity_at=NOW - timedelta(hours=10))
        active = _make_user(701, last_activity_at=NOW - timedelta(hours=1))
        cooldown = _make_user(
            702,
            last_activity_at=NOW - timedelta(hours=10),
            last_reminder_at=NOW - timedelta(hours=1),
        )
        no_tz = _make_user(703, tz_mode=None, last_activity_at=NOW - timedelta(hours=10))

        session.add_all([eligible, active, cooldown, no_tz])
        await session.flush()

        result = await UserRepo.get_inactive_users(session, INACTIVITY_CUTOFF, COOLDOWN_CUTOFF)
        tg_ids = {u.tg_user_id for u in result}
        assert tg_ids == {700}


# ---------------------------------------------------------------------------
# DB integration tests: update_last_reminder
# ---------------------------------------------------------------------------


class TestUpdateLastReminder:
    """Test UserRepo.update_last_reminder."""

    async def test_sets_last_reminder_at(self, session: AsyncSession) -> None:
        """update_last_reminder sets last_reminder_at to approximately now."""
        user = _make_user(800, last_activity_at=NOW - timedelta(hours=10))
        session.add(user)
        await session.flush()

        before = datetime.now(timezone.utc).replace(tzinfo=None)
        await UserRepo.update_last_reminder(session, user.id)
        await session.flush()

        result = await session.execute(select(User).where(User.id == user.id))
        updated = result.scalar_one()
        assert updated.last_reminder_at is not None
        # SQLite strips tzinfo
        ts = (
            updated.last_reminder_at.replace(tzinfo=None)
            if updated.last_reminder_at.tzinfo
            else updated.last_reminder_at
        )
        assert ts >= before


# ---------------------------------------------------------------------------
# HTTP endpoint tests: /tasks/remind
# ---------------------------------------------------------------------------


class TestRemindEndpoint:
    """Test the /tasks/remind endpoint auth and behaviour."""

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_403(self) -> None:
        """Wrong X-Tasks-Secret → 403."""
        with patch("app.web.main.get_settings") as mock_settings:
            mock_settings.return_value.TASKS_SECRET = "correct-secret-123"
            from app.web.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/tasks/remind",
                    headers={"X-Tasks-Secret": "wrong-secret"},
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_header_returns_403(self) -> None:
        """No X-Tasks-Secret header → 403."""
        with patch("app.web.main.get_settings") as mock_settings:
            mock_settings.return_value.TASKS_SECRET = "correct-secret-123"
            from app.web.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/tasks/remind")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_tasks_secret_returns_403(self) -> None:
        """Empty TASKS_SECRET → 403."""
        with patch("app.web.main.get_settings") as mock_settings:
            mock_settings.return_value.TASKS_SECRET = ""
            from app.web.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/tasks/remind",
                    headers={"X-Tasks-Secret": "anything"},
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_secret_sends_reminders(self) -> None:
        """Valid secret → sends reminders to eligible users, returns count."""
        import app.web.main as web_main

        mock_session = AsyncMock(spec=AsyncSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        original_factory = web_main._session_factory
        original_bot = web_main._bot
        web_main._session_factory = MagicMock(return_value=mock_ctx)

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock()
        web_main._bot = mock_bot

        # Create mock eligible users
        user1 = MagicMock()
        user1.id = uuid.uuid4()
        user1.tg_user_id = 111
        user2 = MagicMock()
        user2.id = uuid.uuid4()
        user2.tg_user_id = 222

        try:
            with (
                patch("app.web.main.get_settings") as mock_settings,
                patch("app.web.main.UserRepo") as mock_user_repo,
            ):
                mock_settings.return_value.TASKS_SECRET = "my-secret-12345"
                mock_settings.return_value.REMINDER_INACTIVITY_HOURS = 6
                mock_settings.return_value.REMINDER_COOLDOWN_HOURS = 6
                mock_user_repo.get_inactive_users = AsyncMock(return_value=[user1, user2])
                mock_user_repo.update_last_reminder = AsyncMock()

                transport = ASGITransport(app=web_main.app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/tasks/remind",
                        headers={"X-Tasks-Secret": "my-secret-12345"},
                    )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["sent"] == 2
            assert data["failed"] == 0
            assert mock_bot.send_message.call_count == 2
            assert mock_user_repo.update_last_reminder.call_count == 2
        finally:
            web_main._session_factory = original_factory
            web_main._bot = original_bot

    @pytest.mark.asyncio
    async def test_partial_send_failure(self) -> None:
        """One send fails → still sends to others, reports failure count."""
        import app.web.main as web_main

        mock_session = AsyncMock(spec=AsyncSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        original_factory = web_main._session_factory
        original_bot = web_main._bot
        web_main._session_factory = MagicMock(return_value=mock_ctx)

        mock_bot = AsyncMock()
        # First call succeeds, second raises
        mock_bot.send_message = AsyncMock(
            side_effect=[None, RuntimeError("Telegram API error")]
        )
        web_main._bot = mock_bot

        user1 = MagicMock()
        user1.id = uuid.uuid4()
        user1.tg_user_id = 111
        user2 = MagicMock()
        user2.id = uuid.uuid4()
        user2.tg_user_id = 222

        try:
            with (
                patch("app.web.main.get_settings") as mock_settings,
                patch("app.web.main.UserRepo") as mock_user_repo,
            ):
                mock_settings.return_value.TASKS_SECRET = "my-secret-12345"
                mock_settings.return_value.REMINDER_INACTIVITY_HOURS = 6
                mock_settings.return_value.REMINDER_COOLDOWN_HOURS = 6
                mock_user_repo.get_inactive_users = AsyncMock(return_value=[user1, user2])
                mock_user_repo.update_last_reminder = AsyncMock()

                transport = ASGITransport(app=web_main.app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/tasks/remind",
                        headers={"X-Tasks-Secret": "my-secret-12345"},
                    )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["sent"] == 1
            assert data["failed"] == 1
            # Only 1 update_last_reminder (for the successful send)
            assert mock_user_repo.update_last_reminder.call_count == 1
        finally:
            web_main._session_factory = original_factory
            web_main._bot = original_bot

    @pytest.mark.asyncio
    async def test_no_eligible_users(self) -> None:
        """No eligible users → returns 0 sent, 0 failed."""
        import app.web.main as web_main

        mock_session = AsyncMock(spec=AsyncSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        original_factory = web_main._session_factory
        original_bot = web_main._bot
        web_main._session_factory = MagicMock(return_value=mock_ctx)
        web_main._bot = AsyncMock()

        try:
            with (
                patch("app.web.main.get_settings") as mock_settings,
                patch("app.web.main.UserRepo") as mock_user_repo,
            ):
                mock_settings.return_value.TASKS_SECRET = "my-secret-12345"
                mock_settings.return_value.REMINDER_INACTIVITY_HOURS = 6
                mock_settings.return_value.REMINDER_COOLDOWN_HOURS = 6
                mock_user_repo.get_inactive_users = AsyncMock(return_value=[])
                mock_user_repo.update_last_reminder = AsyncMock()

                transport = ASGITransport(app=web_main.app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/tasks/remind",
                        headers={"X-Tasks-Secret": "my-secret-12345"},
                    )

            assert resp.status_code == 200
            data = resp.json()
            assert data["sent"] == 0
            assert data["failed"] == 0
        finally:
            web_main._session_factory = original_factory
            web_main._bot = original_bot
