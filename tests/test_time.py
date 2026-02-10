"""Tests for app.core.time — timezone and date utilities."""

from __future__ import annotations

import datetime as _dt

from app.core.time import (
    last_7_days,
    last_28_days_weeks,
    local_date_from_utc,
    user_timezone,
    week_bounds,
)


# ---------------------------------------------------------------------------
# user_timezone
# ---------------------------------------------------------------------------
class TestUserTimezone:
    def test_city_mode(self):
        tz = user_timezone("city", "Asia/Almaty", None)
        # Asia/Almaty is UTC+5 (no DST historically)
        now = _dt.datetime(2024, 6, 15, 12, 0, tzinfo=_dt.timezone.utc)
        local = now.astimezone(tz)
        assert local.utcoffset() == _dt.timedelta(hours=5)

    def test_offset_mode(self):
        tz = user_timezone("offset", None, 180)  # UTC+3
        assert tz.utcoffset(None) == _dt.timedelta(minutes=180)

    def test_fallback_to_utc(self):
        tz = user_timezone(None, None, None)
        assert tz == _dt.timezone.utc

    def test_city_mode_missing_name_falls_back(self):
        tz = user_timezone("city", None, None)
        assert tz == _dt.timezone.utc


# ---------------------------------------------------------------------------
# local_date_from_utc
# ---------------------------------------------------------------------------
class TestLocalDateFromUtc:
    def test_almaty_next_day(self):
        """22:00 UTC = 03:00+5 next day in Almaty."""
        utc_dt = _dt.datetime(2024, 6, 15, 22, 0, tzinfo=_dt.timezone.utc)
        tz = user_timezone("city", "Asia/Almaty", None)
        assert local_date_from_utc(utc_dt, tz) == _dt.date(2024, 6, 16)

    def test_almaty_same_day(self):
        """18:00 UTC = 23:00+5 same day in Almaty."""
        utc_dt = _dt.datetime(2024, 6, 15, 18, 0, tzinfo=_dt.timezone.utc)
        tz = user_timezone("city", "Asia/Almaty", None)
        assert local_date_from_utc(utc_dt, tz) == _dt.date(2024, 6, 15)

    def test_midnight_boundary_just_before(self):
        """18:59 UTC = 23:59+5 still June 15."""
        utc_dt = _dt.datetime(2024, 6, 15, 18, 59, tzinfo=_dt.timezone.utc)
        tz = user_timezone("offset", None, 300)  # UTC+5
        assert local_date_from_utc(utc_dt, tz) == _dt.date(2024, 6, 15)

    def test_midnight_boundary_just_after(self):
        """19:01 UTC = 00:01+5 June 16."""
        utc_dt = _dt.datetime(2024, 6, 15, 19, 1, tzinfo=_dt.timezone.utc)
        tz = user_timezone("offset", None, 300)  # UTC+5
        assert local_date_from_utc(utc_dt, tz) == _dt.date(2024, 6, 16)

    def test_naive_utc_dt_treated_as_utc(self):
        """Naive datetime should be treated as UTC."""
        utc_dt = _dt.datetime(2024, 6, 15, 22, 0)  # naive
        tz = user_timezone("offset", None, 300)
        assert local_date_from_utc(utc_dt, tz) == _dt.date(2024, 6, 16)

    def test_negative_offset(self):
        """Test UTC-5: 03:00 UTC = 22:00 previous day in UTC-5."""
        utc_dt = _dt.datetime(2024, 6, 15, 3, 0, tzinfo=_dt.timezone.utc)
        tz = user_timezone("offset", None, -300)  # UTC-5
        assert local_date_from_utc(utc_dt, tz) == _dt.date(2024, 6, 14)


# ---------------------------------------------------------------------------
# week_bounds
# ---------------------------------------------------------------------------
class TestWeekBounds:
    def test_wednesday(self):
        wed = _dt.date(2024, 6, 19)  # Wednesday
        mon, sun = week_bounds(wed)
        assert mon == _dt.date(2024, 6, 17)  # Monday
        assert sun == _dt.date(2024, 6, 23)  # Sunday
        assert mon.weekday() == 0
        assert sun.weekday() == 6

    def test_monday(self):
        mon_date = _dt.date(2024, 6, 17)  # Monday
        mon, sun = week_bounds(mon_date)
        assert mon == mon_date

    def test_sunday(self):
        sun_date = _dt.date(2024, 6, 23)  # Sunday
        mon, sun = week_bounds(sun_date)
        assert sun == sun_date


# ---------------------------------------------------------------------------
# last_7_days
# ---------------------------------------------------------------------------
class TestLast7Days:
    def test_returns_7_dates(self):
        today = _dt.date(2024, 6, 19)
        days = last_7_days(today)
        assert len(days) == 7

    def test_first_is_today(self):
        today = _dt.date(2024, 6, 19)
        days = last_7_days(today)
        assert days[0] == today

    def test_last_is_6_days_ago(self):
        today = _dt.date(2024, 6, 19)
        days = last_7_days(today)
        assert days[-1] == _dt.date(2024, 6, 13)

    def test_descending_order(self):
        today = _dt.date(2024, 6, 19)
        days = last_7_days(today)
        for i in range(len(days) - 1):
            assert days[i] > days[i + 1]


# ---------------------------------------------------------------------------
# last_28_days_weeks
# ---------------------------------------------------------------------------
class TestLast28DaysWeeks:
    def test_returns_4_weeks(self):
        today = _dt.date(2024, 6, 19)  # Wednesday
        weeks = last_28_days_weeks(today)
        assert len(weeks) == 4

    def test_all_weeks_are_mon_sun(self):
        today = _dt.date(2024, 6, 19)
        weeks = last_28_days_weeks(today)
        for mon, sun in weeks:
            assert mon.weekday() == 0, f"{mon} is not Monday"
            assert sun.weekday() == 6, f"{sun} is not Sunday"
            assert (sun - mon).days == 6

    def test_newest_week_contains_today(self):
        today = _dt.date(2024, 6, 19)  # Wednesday
        weeks = last_28_days_weeks(today)
        mon, sun = weeks[0]
        assert mon <= today <= sun

    def test_weeks_are_consecutive_backwards(self):
        today = _dt.date(2024, 6, 19)
        weeks = last_28_days_weeks(today)
        for i in range(len(weeks) - 1):
            current_mon, _ = weeks[i]
            prev_mon, _ = weeks[i + 1]
            assert (current_mon - prev_mon).days == 7
