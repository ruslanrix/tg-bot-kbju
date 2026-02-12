"""Database repositories — thin CRUD layer over SQLAlchemy models.

Every query that returns meal data filters ``is_deleted=False``
unless explicitly noted otherwise.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MealEntry, User


# ---------------------------------------------------------------------------
# UserRepo
# ---------------------------------------------------------------------------
class UserRepo:
    """CRUD operations for the ``users`` table."""

    @staticmethod
    async def get_or_create(session: AsyncSession, tg_user_id: int) -> User:
        """Return an existing user or create a new one.

        Args:
            session: Active async session.
            tg_user_id: Telegram user ID.

        Returns:
            The ``User`` row (new or existing).
        """
        stmt = select(User).where(User.tg_user_id == tg_user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = User(tg_user_id=tg_user_id)
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def update_goal(session: AsyncSession, user_id: uuid.UUID, goal: str) -> User:
        """Set the user's goal label (maintenance / deficit / bulk).

        Returns:
            The updated ``User``.
        """
        stmt = update(User).where(User.id == user_id).values(goal=goal).returning(User)
        result = await session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def update_timezone(
        session: AsyncSession,
        user_id: uuid.UUID,
        tz_mode: str,
        tz_name: str | None,
        tz_offset_minutes: int | None,
    ) -> User:
        """Update the user's timezone settings.

        Returns:
            The updated ``User``.
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                tz_mode=tz_mode,
                tz_name=tz_name,
                tz_offset_minutes=tz_offset_minutes,
            )
            .returning(User)
        )
        result = await session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def update_language(
        session: AsyncSession,
        user_id: uuid.UUID,
        language: str,
    ) -> User:
        """Set the user's UI language (e.g. ``"EN"``, ``"RU"``).

        Returns:
            The updated ``User``.
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(language=language.upper())
            .returning(User)
        )
        result = await session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def touch_activity(session: AsyncSession, tg_user_id: int) -> None:
        """Update ``last_activity_at`` to now for a given Telegram user.

        This is a lightweight fire-and-forget update used by the activity
        tracking middleware.  If the user doesn't exist yet, this is a no-op
        (the user will be created later by ``get_or_create``).
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(User)
            .where(User.tg_user_id == tg_user_id)
            .values(last_activity_at=now)
        )
        await session.execute(stmt)

    @staticmethod
    async def claim_inactive_users(
        session: AsyncSession,
        inactivity_cutoff: datetime,
        cooldown_cutoff: datetime,
    ) -> list[User]:
        """Atomically claim users eligible for an inactivity reminder.

        In a single ``UPDATE … RETURNING`` statement this method:
        1. Selects users matching eligibility criteria.
        2. Sets ``last_reminder_at = now()`` on those rows.
        3. Returns the claimed ``User`` objects.

        Because the update is atomic, concurrent ``/tasks/remind``
        calls cannot claim the same users (the second caller sees the
        already-updated ``last_reminder_at`` and skips them).

        Eligible means:
        - ``tz_mode`` is set (user completed onboarding)
        - ``last_activity_at`` is not NULL and older than *inactivity_cutoff*
        - ``last_reminder_at`` is NULL **or** older than *cooldown_cutoff*
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(User)
            .where(
                User.tz_mode.is_not(None),
                User.last_activity_at.is_not(None),
                User.last_activity_at < inactivity_cutoff,
                (User.last_reminder_at.is_(None)) | (User.last_reminder_at < cooldown_cutoff),
            )
            .values(last_reminder_at=now)
            .returning(User)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# MealRepo
# ---------------------------------------------------------------------------
class MealRepo:
    """CRUD operations for the ``meal_entries`` table."""

    @staticmethod
    async def create(session: AsyncSession, **fields: Any) -> MealEntry:
        """Insert a new meal entry.

        Args:
            session: Active async session.
            **fields: Column values matching ``MealEntry`` attributes.

        Returns:
            The created ``MealEntry``.
        """
        meal = MealEntry(**fields)
        session.add(meal)
        await session.flush()
        return meal

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MealEntry | None:
        """Fetch a non-deleted meal by its primary key.

        Returns:
            The ``MealEntry`` or ``None`` if not found / deleted.
        """
        stmt = select(MealEntry).where(
            MealEntry.id == meal_id,
            MealEntry.user_id == user_id,
            MealEntry.is_deleted.is_(False),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        session: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID,
        **fields: Any,
    ) -> MealEntry:
        """Update an existing meal entry (e.g. after edit flow).

        Only non-deleted meals can be updated.

        Returns:
            The updated ``MealEntry``.
        """
        stmt = (
            update(MealEntry)
            .where(
                MealEntry.id == meal_id,
                MealEntry.user_id == user_id,
                MealEntry.is_deleted.is_(False),
            )
            .values(**fields)
            .returning(MealEntry)
        )
        result = await session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def soft_delete(
        session: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Mark a meal as deleted (soft-delete).

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(MealEntry)
            .where(
                MealEntry.id == meal_id,
                MealEntry.user_id == user_id,
                MealEntry.is_deleted.is_(False),
            )
            .values(is_deleted=True, deleted_at=now)
        )
        result = await session.execute(stmt)
        return result.rowcount > 0  # type: ignore[union-attr]

    @staticmethod
    async def exists_by_message(
        session: AsyncSession,
        tg_chat_id: int,
        tg_message_id: int,
    ) -> bool:
        """Check if a meal already exists for this message (idempotency).

        Checks ALL meals (including soft-deleted) to prevent
        unique-constraint violations.
        """
        stmt = select(MealEntry.id).where(
            MealEntry.tg_chat_id == tg_chat_id,
            MealEntry.tg_message_id == tg_message_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def list_recent(
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
    ) -> list[MealEntry]:
        """Return the most recent non-deleted meals.

        Args:
            session: Active async session.
            user_id: Owner's user ID.
            limit: Maximum number of meals to return (default 20).

        Returns:
            List of ``MealEntry`` ordered by ``consumed_at_utc`` descending.
        """
        stmt = (
            select(MealEntry)
            .where(
                MealEntry.user_id == user_id,
                MealEntry.is_deleted.is_(False),
            )
            .order_by(MealEntry.consumed_at_utc.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def hard_delete_deleted_before(
        session: AsyncSession,
        cutoff: datetime,
    ) -> int:
        """Permanently remove soft-deleted meals older than *cutoff*.

        Only rows with ``is_deleted=True`` **and** ``deleted_at < cutoff``
        are removed.

        Args:
            session: Active async session.
            cutoff: UTC datetime threshold.

        Returns:
            Number of rows permanently deleted.
        """
        stmt = delete(MealEntry).where(
            MealEntry.is_deleted.is_(True),
            MealEntry.deleted_at < cutoff,
        )
        result = await session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]
