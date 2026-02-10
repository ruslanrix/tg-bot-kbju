"""Database repositories — thin CRUD layer over SQLAlchemy models.

Every query that returns meal data filters ``is_deleted=False``
unless explicitly noted otherwise.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
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
