"""Keyboard builders for the Telegram bot (spec §3.1, §3.5).

Provides persistent reply keyboard (main 5-button) and inline
keyboards for draft/saved meal actions, goals, timezone, and stats.
"""

from __future__ import annotations


from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


# ---------------------------------------------------------------------------
# Persistent reply keyboard (spec §3.1)
# ---------------------------------------------------------------------------


def main_keyboard() -> ReplyKeyboardMarkup:
    """5-button persistent reply keyboard shown after /start."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Stats"), KeyboardButton(text="🎯 Goals")],
            [KeyboardButton(text="☁️ Help"), KeyboardButton(text="🕘 History")],
            [KeyboardButton(text="✏️ Add Meal")],
        ],
        resize_keyboard=True,
    )


# ---------------------------------------------------------------------------
# Inline keyboards for meal actions (spec §3.5)
# ---------------------------------------------------------------------------


def draft_actions_keyboard(meal_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard for a draft (before saving): Save / Edit / Delete."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Save", callback_data=f"draft_save:{meal_id}"),
                InlineKeyboardButton(text="✏️ Edit", callback_data=f"draft_edit:{meal_id}"),
                InlineKeyboardButton(text="🛑 Delete", callback_data=f"draft_delete:{meal_id}"),
            ],
        ],
    )


def saved_actions_keyboard(meal_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard for a saved meal: Edit / Delete."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Edit", callback_data=f"saved_edit:{meal_id}"),
                InlineKeyboardButton(text="🛑 Delete", callback_data=f"saved_delete:{meal_id}"),
            ],
        ],
    )


# ---------------------------------------------------------------------------
# Stats inline keyboard
# ---------------------------------------------------------------------------


def stats_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for choosing a stats period."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Today", callback_data="stats:today"),
                InlineKeyboardButton(text="Weekly", callback_data="stats:weekly"),
                InlineKeyboardButton(text="4 Weeks", callback_data="stats:4weeks"),
            ],
        ],
    )


# ---------------------------------------------------------------------------
# Goal selection (spec §3.2 /goals)
# ---------------------------------------------------------------------------


def goal_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for goal selection."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏋️ Maintenance", callback_data="goal:maintenance")],
            [InlineKeyboardButton(text="📉 Deficit", callback_data="goal:deficit")],
            [InlineKeyboardButton(text="💪 Bulk", callback_data="goal:bulk")],
        ],
    )


# ---------------------------------------------------------------------------
# Timezone selection
# ---------------------------------------------------------------------------

_TZ_CITIES: list[tuple[str, str]] = [
    ("🇬🇧 London", "Europe/London"),
    ("🇩🇪 Berlin", "Europe/Berlin"),
    ("🇨🇿 Prague", "Europe/Prague"),
    ("🇫🇮 Helsinki", "Europe/Helsinki"),
    ("🇷🇺 Moscow", "Europe/Moscow"),
    ("🇦🇪 Dubai", "Asia/Dubai"),
    ("🇰🇿 Almaty", "Asia/Almaty"),
    ("🇮🇳 Kolkata", "Asia/Kolkata"),
    ("🇹🇭 Bangkok", "Asia/Bangkok"),
    ("🇨🇳 Shanghai", "Asia/Shanghai"),
    ("🇯🇵 Tokyo", "Asia/Tokyo"),
    ("🇦🇺 Sydney", "Australia/Sydney"),
    ("🇺🇸 New York", "America/New_York"),
    ("🇺🇸 Chicago", "America/Chicago"),
    ("🇺🇸 Denver", "America/Denver"),
    ("🇺🇸 Los Angeles", "America/Los_Angeles"),
]


def timezone_city_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard with popular cities (IANA timezones)."""
    rows = []
    for label, iana in _TZ_CITIES:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"tz_city:{iana}")])
    rows.append(
        [InlineKeyboardButton(text="⏱ Choose UTC offset instead", callback_data="tz_offset_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_offset_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard with UTC offsets from UTC-12 to UTC+14."""
    rows = []
    # Group in rows of 4
    offsets = list(range(-12, 15))  # -12 to +14
    for i in range(0, len(offsets), 4):
        chunk = offsets[i : i + 4]
        row = []
        for off in chunk:
            sign = "+" if off >= 0 else ""
            label = f"UTC{sign}{off}"
            minutes = off * 60
            row.append(InlineKeyboardButton(text=label, callback_data=f"tz_offset:{minutes}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🏙 Choose city instead", callback_data="tz_city_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# History delete button
# ---------------------------------------------------------------------------


def history_delete_keyboard(meal_id: str) -> InlineKeyboardMarkup:
    """Single delete button for a history entry."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Delete", callback_data=f"hist_delete:{meal_id}")],
        ],
    )


# ---------------------------------------------------------------------------
# Help — change timezone inline button (spec §3.3)
# ---------------------------------------------------------------------------


def help_change_tz_keyboard() -> InlineKeyboardMarkup:
    """Inline button shown under /help text."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕒 Change Time Zone", callback_data="tz_city_menu")],
        ],
    )


# ---------------------------------------------------------------------------
# Language selection (FEAT-13)
# ---------------------------------------------------------------------------


def language_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for EN/RU language selection."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:EN"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:RU"),
            ],
        ],
    )
