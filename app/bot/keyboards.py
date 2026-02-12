"""Keyboard builders for the Telegram bot (spec §3.1, §3.5).

Provides persistent reply keyboard (main 5-button) and inline
keyboards for draft/saved meal actions, goals, timezone, and stats.

All user-facing labels are resolved via ``t(key, lang)`` for i18n.
"""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.i18n import t


# ---------------------------------------------------------------------------
# Persistent reply keyboard (spec §3.1)
# ---------------------------------------------------------------------------


def main_keyboard(lang: str = "EN") -> ReplyKeyboardMarkup:
    """5-button persistent reply keyboard shown after /start."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("kb_stats", lang)), KeyboardButton(text=t("kb_goals", lang))],
            [KeyboardButton(text=t("kb_help", lang)), KeyboardButton(text=t("kb_history", lang))],
            [KeyboardButton(text=t("kb_add_meal", lang))],
        ],
        resize_keyboard=True,
    )


# ---------------------------------------------------------------------------
# Inline keyboards for meal actions (spec §3.5)
# ---------------------------------------------------------------------------


def draft_actions_keyboard(meal_id: str, lang: str = "EN") -> InlineKeyboardMarkup:
    """Inline keyboard for a draft (before saving): Save / Edit / Delete."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("kb_save", lang), callback_data=f"draft_save:{meal_id}"
                ),
                InlineKeyboardButton(
                    text=t("kb_edit", lang), callback_data=f"draft_edit:{meal_id}"
                ),
                InlineKeyboardButton(
                    text=t("kb_delete", lang), callback_data=f"draft_delete:{meal_id}"
                ),
            ],
        ],
    )


def saved_actions_keyboard(meal_id: str, lang: str = "EN") -> InlineKeyboardMarkup:
    """Inline keyboard for a saved meal: Edit / Delete."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("kb_edit", lang), callback_data=f"saved_edit:{meal_id}"
                ),
                InlineKeyboardButton(
                    text=t("kb_delete", lang), callback_data=f"saved_delete:{meal_id}"
                ),
            ],
        ],
    )


# ---------------------------------------------------------------------------
# Stats inline keyboard
# ---------------------------------------------------------------------------


def stats_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    """Inline keyboard for choosing a stats period."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("kb_today", lang), callback_data="stats:today"),
                InlineKeyboardButton(text=t("kb_weekly", lang), callback_data="stats:weekly"),
                InlineKeyboardButton(text=t("kb_4weeks", lang), callback_data="stats:4weeks"),
            ],
        ],
    )


# ---------------------------------------------------------------------------
# Goal selection (spec §3.2 /goals)
# ---------------------------------------------------------------------------


def goal_inline_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    """Inline keyboard for goal selection."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=t("goal_maintenance", lang), callback_data="goal:maintenance",
            )],
            [InlineKeyboardButton(
                text=t("goal_deficit", lang), callback_data="goal:deficit",
            )],
            [InlineKeyboardButton(
                text=t("goal_bulk", lang), callback_data="goal:bulk",
            )],
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


def timezone_city_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    """Inline keyboard with popular cities (IANA timezones)."""
    rows = []
    for label, iana in _TZ_CITIES:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"tz_city:{iana}")])
    rows.append(
        [InlineKeyboardButton(
            text=t("kb_choose_offset", lang), callback_data="tz_offset_menu",
        )]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_offset_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
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
    rows.append(
        [InlineKeyboardButton(text=t("kb_choose_city", lang), callback_data="tz_city_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# History delete button
# ---------------------------------------------------------------------------


def history_delete_keyboard(meal_id: str, lang: str = "EN") -> InlineKeyboardMarkup:
    """Single delete button for a history entry."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=t("kb_delete", lang), callback_data=f"hist_delete:{meal_id}",
            )],
        ],
    )


# ---------------------------------------------------------------------------
# Help — change timezone inline button (spec §3.3)
# ---------------------------------------------------------------------------


def help_change_tz_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    """Inline button shown under /help text."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=t("kb_change_tz", lang), callback_data="tz_city_menu",
            )],
        ],
    )


# ---------------------------------------------------------------------------
# Language selection (FEAT-13)
# ---------------------------------------------------------------------------


def language_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for EN/RU language selection.

    Labels are always bilingual — not localized.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:EN"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:RU"),
            ],
        ],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def all_main_button_texts() -> set[str]:
    """Return all possible main keyboard button texts across all locales.

    Used by meal.py catch-all handler to avoid treating button presses
    as meal input.
    """
    from app.i18n.locales.en import STRINGS as EN
    from app.i18n.locales.ru import STRINGS as RU

    keys = ("kb_stats", "kb_goals", "kb_help", "kb_history", "kb_add_meal")
    texts: set[str] = set()
    for k in keys:
        texts.add(EN[k])
        texts.add(RU[k])
    return texts
