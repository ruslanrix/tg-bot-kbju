"""Stats aggregation queries for reports (spec §8).

All functions exclude soft-deleted meals and return zeros when
no data exists for the requested period.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TypedDict

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MealEntry


class DayStats(TypedDict):
    """Nutrition totals for a single day."""

    date: date
    calories_kcal: int
    protein_g: float
    carbs_g: float
    fat_g: float


class WeekAvgStats(TypedDict):
    """Average daily nutrition for a Mon-Sun week."""

    week_start: date
    week_end: date
    avg_calories_kcal: float
    avg_protein_g: float
    avg_carbs_g: float
    avg_fat_g: float


def _active_meals_filter():  # noqa: ANN202
    """Common WHERE clause for non-deleted meals."""
    return MealEntry.is_deleted.is_(False)


async def today_stats(
    session: AsyncSession,
    user_id: uuid.UUID,
    local_date: date,
) -> DayStats:
    """Sum of calories and macros for a specific local date.

    Returns zeros if no meals exist for the date.
    """
    stmt = select(
        func.coalesce(func.sum(MealEntry.calories_kcal), 0).label("calories_kcal"),
        func.coalesce(func.sum(MealEntry.protein_g), 0.0).label("protein_g"),
        func.coalesce(func.sum(MealEntry.carbs_g), 0.0).label("carbs_g"),
        func.coalesce(func.sum(MealEntry.fat_g), 0.0).label("fat_g"),
    ).where(
        MealEntry.user_id == user_id,
        MealEntry.local_date == local_date,
        _active_meals_filter(),
    )
    row = (await session.execute(stmt)).one()
    return DayStats(
        date=local_date,
        calories_kcal=int(row.calories_kcal),
        protein_g=float(row.protein_g),
        carbs_g=float(row.carbs_g),
        fat_g=float(row.fat_g),
    )


async def weekly_stats(
    session: AsyncSession,
    user_id: uuid.UUID,
    dates: list[date],
) -> list[DayStats]:
    """Per-day totals for a list of dates (typically last 7 days).

    Days with no meals get zeros.  Results are returned in the
    same order as *dates*.
    """
    if not dates:
        return []

    # Fetch sums grouped by local_date for the requested range.
    stmt = (
        select(
            cast(MealEntry.local_date, Date).label("day"),
            func.coalesce(func.sum(MealEntry.calories_kcal), 0).label("calories_kcal"),
            func.coalesce(func.sum(MealEntry.protein_g), 0.0).label("protein_g"),
            func.coalesce(func.sum(MealEntry.carbs_g), 0.0).label("carbs_g"),
            func.coalesce(func.sum(MealEntry.fat_g), 0.0).label("fat_g"),
        )
        .where(
            MealEntry.user_id == user_id,
            MealEntry.local_date.in_(dates),
            _active_meals_filter(),
        )
        .group_by(MealEntry.local_date)
    )
    result = await session.execute(stmt)

    # Build a lookup dict of actual sums.
    by_date: dict[date, DayStats] = {}
    for row in result:
        by_date[row.day] = DayStats(
            date=row.day,
            calories_kcal=int(row.calories_kcal),
            protein_g=float(row.protein_g),
            carbs_g=float(row.carbs_g),
            fat_g=float(row.fat_g),
        )

    # Return in requested order, filling zeros for missing days.
    return [
        by_date.get(
            d,
            DayStats(date=d, calories_kcal=0, protein_g=0.0, carbs_g=0.0, fat_g=0.0),
        )
        for d in dates
    ]


async def four_week_stats(
    session: AsyncSession,
    user_id: uuid.UUID,
    week_ranges: list[tuple[date, date]],
) -> list[WeekAvgStats]:
    """Average daily nutrition for each Mon-Sun week (spec §8.3).

    For each week, total calories/macros are divided by 7 to produce
    a per-day average (including zero-days).

    Args:
        session: Active async session.
        user_id: Owner's user ID.
        week_ranges: List of ``(monday, sunday)`` tuples, newest first.

    Returns:
        List of ``WeekAvgStats`` in the same order as *week_ranges*.
    """
    results: list[WeekAvgStats] = []

    for mon, sun in week_ranges:
        stmt = select(
            func.coalesce(func.sum(MealEntry.calories_kcal), 0).label("calories_kcal"),
            func.coalesce(func.sum(MealEntry.protein_g), 0.0).label("protein_g"),
            func.coalesce(func.sum(MealEntry.carbs_g), 0.0).label("carbs_g"),
            func.coalesce(func.sum(MealEntry.fat_g), 0.0).label("fat_g"),
        ).where(
            MealEntry.user_id == user_id,
            MealEntry.local_date >= mon,
            MealEntry.local_date <= sun,
            _active_meals_filter(),
        )
        row = (await session.execute(stmt)).one()
        results.append(
            WeekAvgStats(
                week_start=mon,
                week_end=sun,
                avg_calories_kcal=round(int(row.calories_kcal) / 7, 1),
                avg_protein_g=round(float(row.protein_g) / 7, 1),
                avg_carbs_g=round(float(row.carbs_g) / 7, 1),
                avg_fat_g=round(float(row.fat_g) / 7, 1),
            )
        )

    return results
