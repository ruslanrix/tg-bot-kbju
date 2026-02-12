"""Tests for purge task endpoint and hard_delete_deleted_before (Step 11).

Verifies:
- MealRepo.hard_delete_deleted_before removes only old soft-deleted rows.
- Active records are untouched.
- Recently soft-deleted records survive.
- /tasks/purge endpoint auth via X-Tasks-Secret header and behaviour.
- Task engine disposal on shutdown.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MealEntry, User
from app.db.repos import MealRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meal(
    user: User,
    *,
    is_deleted: bool = False,
    deleted_at: datetime | None = None,
) -> MealEntry:
    """Build a MealEntry with explicit deleted_at control."""
    return MealEntry(
        id=uuid.uuid4(),
        user_id=user.id,
        tg_chat_id=user.tg_user_id,
        tg_message_id=uuid.uuid4().int % (2**63),
        source="text",
        consumed_at_utc=datetime.now(timezone.utc),
        local_date=date.today(),
        meal_name="Test meal",
        calories_kcal=400,
        protein_g=25.0,
        carbs_g=40.0,
        fat_g=15.0,
        is_deleted=is_deleted,
        deleted_at=deleted_at,
    )


# ---------------------------------------------------------------------------
# DB integration tests: hard_delete_deleted_before
# ---------------------------------------------------------------------------


class TestHardDeleteDeletedBefore:
    """Test MealRepo.hard_delete_deleted_before with real SQLite DB."""

    async def test_deletes_old_soft_deleted(self, session: AsyncSession, test_user: User) -> None:
        """Soft-deleted meal with deleted_at 60 days ago → hard-deleted."""
        old_deleted = _make_meal(
            test_user,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        session.add(old_deleted)
        await session.flush()

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        count = await MealRepo.hard_delete_deleted_before(session, cutoff)

        assert count == 1

        # Verify row is gone
        result = await session.execute(
            select(MealEntry).where(MealEntry.id == old_deleted.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_preserves_active_records(self, session: AsyncSession, test_user: User) -> None:
        """Active (non-deleted) meals are never touched."""
        active = _make_meal(test_user, is_deleted=False)
        session.add(active)
        await session.flush()

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        count = await MealRepo.hard_delete_deleted_before(session, cutoff)

        assert count == 0

        # Verify row still exists
        result = await session.execute(
            select(MealEntry).where(MealEntry.id == active.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_preserves_recently_deleted(self, session: AsyncSession, test_user: User) -> None:
        """Soft-deleted meal with deleted_at 5 days ago → preserved."""
        recent_deleted = _make_meal(
            test_user,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        session.add(recent_deleted)
        await session.flush()

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        count = await MealRepo.hard_delete_deleted_before(session, cutoff)

        assert count == 0

        # Verify row still exists
        result = await session.execute(
            select(MealEntry).where(MealEntry.id == recent_deleted.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_mixed_records(self, session: AsyncSession, test_user: User) -> None:
        """Mix of old deleted, recent deleted, and active → only old deleted purged."""
        old_deleted = _make_meal(
            test_user,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        recent_deleted = _make_meal(
            test_user,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        active = _make_meal(test_user, is_deleted=False)

        session.add_all([old_deleted, recent_deleted, active])
        await session.flush()

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        count = await MealRepo.hard_delete_deleted_before(session, cutoff)

        assert count == 1

        # Old deleted gone
        result = await session.execute(
            select(MealEntry).where(MealEntry.id == old_deleted.id)
        )
        assert result.scalar_one_or_none() is None

        # Recent deleted preserved
        result = await session.execute(
            select(MealEntry).where(MealEntry.id == recent_deleted.id)
        )
        assert result.scalar_one_or_none() is not None

        # Active preserved
        result = await session.execute(
            select(MealEntry).where(MealEntry.id == active.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_no_rows_returns_zero(self, session: AsyncSession, test_user: User) -> None:
        """Empty table → returns 0."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        count = await MealRepo.hard_delete_deleted_before(session, cutoff)
        assert count == 0

    async def test_exactly_at_cutoff_preserved(self, session: AsyncSession, test_user: User) -> None:
        """Meal deleted exactly at cutoff → preserved (< not <=)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        at_cutoff = _make_meal(
            test_user,
            is_deleted=True,
            deleted_at=cutoff,
        )
        session.add(at_cutoff)
        await session.flush()

        count = await MealRepo.hard_delete_deleted_before(session, cutoff)
        assert count == 0


# ---------------------------------------------------------------------------
# HTTP endpoint tests: /tasks/purge (X-Tasks-Secret header)
# ---------------------------------------------------------------------------


class TestPurgeEndpoint:
    """Test the /tasks/purge endpoint auth via header and behaviour."""

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_403(self) -> None:
        """Wrong X-Tasks-Secret header → 403."""
        with patch("app.web.main.get_settings") as mock_settings:
            mock_settings.return_value.TASKS_SECRET = "correct-secret-123"
            from app.web.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/tasks/purge",
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
                resp = await client.post("/tasks/purge")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_tasks_secret_returns_403(self) -> None:
        """Empty TASKS_SECRET (disabled) → always 403."""
        with patch("app.web.main.get_settings") as mock_settings:
            mock_settings.return_value.TASKS_SECRET = ""
            from app.web.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/tasks/purge",
                    headers={"X-Tasks-Secret": "anything"},
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_secret_calls_purge(self) -> None:
        """Valid X-Tasks-Secret → calls hard_delete_deleted_before, returns count."""
        import app.web.main as web_main

        mock_session = AsyncMock(spec=AsyncSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        original_factory = web_main._session_factory
        web_main._session_factory = MagicMock(return_value=mock_ctx)

        try:
            with (
                patch("app.web.main.get_settings") as mock_settings,
                patch("app.web.main.MealRepo") as mock_repo,
            ):
                mock_settings.return_value.TASKS_SECRET = "my-secret-12345"
                mock_settings.return_value.PURGE_DELETED_AFTER_DAYS = 30
                mock_repo.hard_delete_deleted_before = AsyncMock(return_value=5)

                transport = ASGITransport(app=web_main.app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/tasks/purge",
                        headers={"X-Tasks-Secret": "my-secret-12345"},
                    )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["deleted_count"] == 5
            mock_repo.hard_delete_deleted_before.assert_called_once()
        finally:
            web_main._session_factory = original_factory


# ---------------------------------------------------------------------------
# Shutdown cleanup test
# ---------------------------------------------------------------------------


class TestTaskEngineDispose:
    """Verify task engine is disposed on shutdown."""

    @pytest.mark.asyncio
    async def test_engine_disposed_on_shutdown(self) -> None:
        """Lifespan shutdown disposes task engine and clears references."""
        import app.web.main as web_main

        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        original_engine = web_main._task_engine
        original_factory = web_main._session_factory
        web_main._task_engine = mock_engine
        web_main._session_factory = MagicMock()

        try:
            with (
                patch("app.web.main.get_settings") as mock_settings,
                patch("app.web.main._run_migrations"),
                patch("app.web.main.create_async_engine", return_value=mock_engine),
                patch("app.web.main.async_sessionmaker", return_value=MagicMock()),
                patch("app.web.main.create_bot") as mock_create_bot,
                patch("app.web.main.create_dispatcher") as mock_create_dp,
                patch("app.web.main.setup_logging"),
            ):
                mock_settings.return_value.DATABASE_URL = "sqlite+aiosqlite://"
                mock_settings.return_value.LOG_LEVEL = "INFO"
                mock_settings.return_value.use_webhook = False
                mock_bot = AsyncMock()
                mock_create_bot.return_value = mock_bot
                mock_dp = AsyncMock()
                mock_dp.start_polling = AsyncMock()
                mock_dp.stop_polling = AsyncMock()
                mock_create_dp.return_value = mock_dp

                async with web_main.lifespan(web_main.app):
                    pass  # go through startup + shutdown

            mock_engine.dispose.assert_called_once()
            assert web_main._task_engine is None
            assert web_main._session_factory is None
        finally:
            web_main._task_engine = original_engine
            web_main._session_factory = original_factory
