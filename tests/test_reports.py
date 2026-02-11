"""Tests for app.reports.stats — aggregation queries."""

from __future__ import annotations

import datetime as _dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.reports.stats import four_week_stats, today_stats, weekly_stats
from tests.conftest import make_meal


# ---------------------------------------------------------------------------
# today_stats
# ---------------------------------------------------------------------------
class TestTodayStats:
    async def test_two_meals_sum(self, session: AsyncSession, test_user: User):
        day = _dt.date(2024, 6, 15)
        session.add(make_meal(test_user, day, calories=300, protein=20, carbs=30, fat=10))
        session.add(make_meal(test_user, day, calories=200, protein=10, carbs=20, fat=5))
        await session.flush()

        result = await today_stats(session, test_user.id, day)
        assert result["calories_kcal"] == 500
        assert result["protein_g"] == 30.0
        assert result["carbs_g"] == 50.0
        assert result["fat_g"] == 15.0

    async def test_no_meals_returns_zeros(self, session: AsyncSession, test_user: User):
        result = await today_stats(session, test_user.id, _dt.date(2024, 6, 15))
        assert result["calories_kcal"] == 0
        assert result["protein_g"] == 0.0
        assert result["carbs_g"] == 0.0
        assert result["fat_g"] == 0.0

    async def test_deleted_meal_excluded(self, session: AsyncSession, test_user: User):
        day = _dt.date(2024, 6, 15)
        session.add(make_meal(test_user, day, calories=300))
        session.add(make_meal(test_user, day, calories=200, is_deleted=True))
        await session.flush()

        result = await today_stats(session, test_user.id, day)
        assert result["calories_kcal"] == 300


# ---------------------------------------------------------------------------
# weekly_stats
# ---------------------------------------------------------------------------
class TestWeeklyStats:
    async def test_7_days_with_gaps(self, session: AsyncSession, test_user: User):
        base = _dt.date(2024, 6, 15)
        dates = [base - _dt.timedelta(days=i) for i in range(7)]

        # Add meals only for day 0 and day 3
        session.add(make_meal(test_user, dates[0], calories=400))
        session.add(make_meal(test_user, dates[3], calories=600))
        await session.flush()

        result = await weekly_stats(session, test_user.id, dates)
        assert len(result) == 7
        assert result[0]["calories_kcal"] == 400  # day 0
        assert result[1]["calories_kcal"] == 0  # day 1 — no data
        assert result[3]["calories_kcal"] == 600  # day 3

    async def test_empty_dates(self, session: AsyncSession, test_user: User):
        result = await weekly_stats(session, test_user.id, [])
        assert result == []


# ---------------------------------------------------------------------------
# four_week_stats
# ---------------------------------------------------------------------------
class TestFourWeekStats:
    async def test_averages_divided_by_7(self, session: AsyncSession, test_user: User):
        # Week Mon Jun 10 - Sun Jun 16, 2024
        mon = _dt.date(2024, 6, 10)
        sun = _dt.date(2024, 6, 16)

        # Add 700 kcal total for the week -> 100 avg/day
        session.add(make_meal(test_user, _dt.date(2024, 6, 12), calories=700))
        await session.flush()

        result = await four_week_stats(session, test_user.id, [(mon, sun)])
        assert len(result) == 1
        assert result[0]["avg_calories_kcal"] == 100.0

    async def test_empty_week_returns_zeros(self, session: AsyncSession, test_user: User):
        mon = _dt.date(2024, 6, 10)
        sun = _dt.date(2024, 6, 16)

        result = await four_week_stats(session, test_user.id, [(mon, sun)])
        assert result[0]["avg_calories_kcal"] == 0.0
        assert result[0]["avg_protein_g"] == 0.0

    async def test_four_weeks(self, session: AsyncSession, test_user: User):
        from app.core.time import last_28_days_weeks

        today = _dt.date(2024, 6, 19)
        weeks = last_28_days_weeks(today)

        result = await four_week_stats(session, test_user.id, weeks)
        assert len(result) == len(weeks)
        # All zeros since no meals
        for week in result:
            assert week["avg_calories_kcal"] == 0.0
