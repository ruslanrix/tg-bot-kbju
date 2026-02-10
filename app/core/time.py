"""Timezone and date utilities for per-user day boundaries.

Day boundaries are 00:00–23:59 in the user's local time (spec §4).
Each meal stores ``local_date`` computed at save time using the user's
current timezone; existing meals are never re-bucketed.
"""

from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo


def user_timezone(
    tz_mode: str | None,
    tz_name: str | None,
    tz_offset_minutes: int | None,
) -> _dt.tzinfo:
    """Build a timezone object from the user's settings.

    Args:
        tz_mode: ``"city"`` for IANA name, ``"offset"`` for fixed UTC offset.
        tz_name: IANA timezone name (e.g. ``"Asia/Almaty"``).
        tz_offset_minutes: Signed offset from UTC in minutes.

    Returns:
        A ``ZoneInfo`` (city mode) or ``datetime.timezone`` (offset mode).
        Falls back to UTC if settings are incomplete.
    """
    if tz_mode == "city" and tz_name:
        return ZoneInfo(tz_name)
    if tz_mode == "offset" and tz_offset_minutes is not None:
        return _dt.timezone(_dt.timedelta(minutes=tz_offset_minutes))
    return _dt.timezone.utc


def now_local(tz: _dt.tzinfo) -> _dt.datetime:
    """Current wall-clock time in the given timezone."""
    return _dt.datetime.now(tz)


def today_local(tz: _dt.tzinfo) -> _dt.date:
    """Today's date in the given timezone."""
    return now_local(tz).date()


def local_date_from_utc(utc_dt: _dt.datetime, tz: _dt.tzinfo) -> _dt.date:
    """Convert a UTC datetime to a local date in *tz*.

    Args:
        utc_dt: Datetime in UTC (aware or naive — treated as UTC).
        tz: Target timezone.

    Returns:
        The local ``date`` in *tz*.
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=_dt.timezone.utc)
    return utc_dt.astimezone(tz).date()


def week_bounds(d: _dt.date) -> tuple[_dt.date, _dt.date]:
    """Return the Monday–Sunday range containing *d*.

    Returns:
        ``(monday, sunday)`` inclusive.
    """
    monday = d - _dt.timedelta(days=d.weekday())  # weekday(): Mon=0
    sunday = monday + _dt.timedelta(days=6)
    return monday, sunday


def last_7_days(today: _dt.date) -> list[_dt.date]:
    """Return the last 7 dates ending with *today* (descending order).

    Example: if today is Wed Jun 19, returns [Jun 19, Jun 18, ..., Jun 13].
    """
    return [today - _dt.timedelta(days=i) for i in range(7)]


def last_28_days_weeks(today: _dt.date) -> list[tuple[_dt.date, _dt.date]]:
    """Split the last 28 days into 4 Mon–Sun week ranges.

    The most recent week contains *today*; weeks go backwards.
    Each week is exactly Mon–Sun (7 days).  The 28-day window is
    computed as ``[today - 27 … today]``, then grouped by ISO week.

    Returns:
        A list of 4 ``(monday, sunday)`` tuples, newest first.
    """
    # Find the Monday of the week containing `today`.
    current_monday = today - _dt.timedelta(days=today.weekday())

    weeks: list[tuple[_dt.date, _dt.date]] = []
    for i in range(4):
        mon = current_monday - _dt.timedelta(weeks=i)
        sun = mon + _dt.timedelta(days=6)
        weeks.append((mon, sun))

    return weeks  # newest week first
