"""Integration tests for DB operations (spec §14.2).

Uses in-memory SQLite via conftest.py fixtures. Verifies:
- Idempotency unique constraint on (tg_chat_id, tg_message_id)
- Soft delete hides meals from stats and list_recent
- Update modifies existing record (same row ID)
- Today stats with mix of deleted + active meals
"""

from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repos import MealRepo
from app.reports.stats import today_stats
from tests.conftest import make_meal


class TestIdempotency:
    """Verify unique constraint on (tg_chat_id, tg_message_id)."""

    async def test_duplicate_message_raises(self, session: AsyncSession, test_user: User):
        """Inserting two meals with same (chat_id, message_id) should fail."""
        base_date = _dt.date(2024, 6, 15)
        session.add(make_meal(test_user, base_date, tg_chat_id=100, tg_message_id=200))
        await session.flush()

        session.add(make_meal(test_user, base_date, tg_chat_id=100, tg_message_id=200))
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_different_messages_ok(self, session: AsyncSession, test_user: User):
        """Different message IDs should be fine."""
        base_date = _dt.date(2024, 6, 15)
        session.add(make_meal(test_user, base_date, tg_chat_id=100, tg_message_id=200))
        session.add(make_meal(test_user, base_date, tg_chat_id=100, tg_message_id=201))
        await session.flush()  # no error


class TestSoftDelete:
    """Verify soft delete hides from queries."""

    async def test_soft_delete_hides_from_list_recent(self, session: AsyncSession, test_user: User):
        base_date = _dt.date(2024, 6, 15)
        meal = make_meal(test_user, base_date, calories=300)
        session.add(meal)
        await session.flush()

        meals = await MealRepo.list_recent(session, test_user.id)
        assert len(meals) == 1

        deleted = await MealRepo.soft_delete(session, meal.id, test_user.id)
        assert deleted is True

        meals = await MealRepo.list_recent(session, test_user.id)
        assert len(meals) == 0

    async def test_soft_delete_hides_from_today_stats(self, session: AsyncSession, test_user: User):
        base_date = _dt.date(2024, 6, 15)
        meal = make_meal(test_user, base_date, calories=500)
        session.add(meal)
        await session.flush()

        stats = await today_stats(session, test_user.id, base_date)
        assert stats["calories_kcal"] == 500

        await MealRepo.soft_delete(session, meal.id, test_user.id)

        stats = await today_stats(session, test_user.id, base_date)
        assert stats["calories_kcal"] == 0

    async def test_soft_delete_wrong_user(self, session: AsyncSession, test_user: User):
        """Soft-deleting another user's meal should return False."""
        base_date = _dt.date(2024, 6, 15)
        meal = make_meal(test_user, base_date, calories=300)
        session.add(meal)
        await session.flush()

        fake_user_id = uuid.uuid4()
        deleted = await MealRepo.soft_delete(session, meal.id, fake_user_id)
        assert deleted is False


class TestUpdate:
    """Verify update modifies existing record."""

    async def test_update_changes_fields(self, session: AsyncSession, test_user: User):
        base_date = _dt.date(2024, 6, 15)
        meal = make_meal(test_user, base_date, calories=300)
        session.add(meal)
        await session.flush()

        original_id = meal.id

        updated = await MealRepo.update(
            session,
            meal.id,
            test_user.id,
            meal_name="Updated Meal",
            calories_kcal=600,
            protein_g=40.0,
            carbs_g=50.0,
            fat_g=20.0,
        )

        assert updated.id == original_id  # same row
        assert updated.meal_name == "Updated Meal"
        assert updated.calories_kcal == 600

    async def test_update_reflected_in_stats(self, session: AsyncSession, test_user: User):
        base_date = _dt.date(2024, 6, 15)
        meal = make_meal(test_user, base_date, calories=300)
        session.add(meal)
        await session.flush()

        stats = await today_stats(session, test_user.id, base_date)
        assert stats["calories_kcal"] == 300

        await MealRepo.update(session, meal.id, test_user.id, calories_kcal=700)

        stats = await today_stats(session, test_user.id, base_date)
        assert stats["calories_kcal"] == 700


class TestMixedDeletedActive:
    """Stats with both deleted and active meals."""

    async def test_mixed_stats(self, session: AsyncSession, test_user: User):
        base_date = _dt.date(2024, 6, 15)

        meal1 = make_meal(test_user, base_date, calories=200)
        meal2 = make_meal(test_user, base_date, calories=300, tg_message_id=2)
        meal3 = make_meal(test_user, base_date, calories=400, tg_message_id=3)
        session.add_all([meal1, meal2, meal3])
        await session.flush()

        # Delete meal2
        await MealRepo.soft_delete(session, meal2.id, test_user.id)

        stats = await today_stats(session, test_user.id, base_date)
        assert stats["calories_kcal"] == 600  # 200 + 400 (meal2 excluded)

    async def test_exists_by_message_includes_deleted(self, session: AsyncSession, test_user: User):
        """Idempotency check should find even deleted meals."""
        base_date = _dt.date(2024, 6, 15)
        meal = make_meal(test_user, base_date, tg_chat_id=100, tg_message_id=200)
        session.add(meal)
        await session.flush()

        await MealRepo.soft_delete(session, meal.id, test_user.id)

        # Should still find it (prevents re-insert unique violation)
        exists = await MealRepo.exists_by_message(session, 100, 200)
        assert exists is True
