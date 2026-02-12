"""Timezone selection handlers (spec §4).

Supports two flows:
1. City list — popular IANA timezones.
2. UTC offset — from UTC-12 to UTC+14.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters import format_today_stats
from app.bot.keyboards import main_keyboard, timezone_city_keyboard, timezone_offset_keyboard
from app.core.time import today_local, user_timezone
from app.db.repos import UserRepo
from app.i18n import t
from app.reports.stats import today_stats

router = Router(name="timezone")


# ---------------------------------------------------------------------------
# Menu navigation
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "tz_city_menu")
async def show_city_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the city selection keyboard."""
    if callback.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, callback.from_user.id)
        lang = user.language
    await callback.message.edit_text(  # type: ignore[union-attr]
        t("tz_choose_city", lang), reply_markup=timezone_city_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "tz_offset_menu")
async def show_offset_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the UTC offset selection keyboard."""
    if callback.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, callback.from_user.id)
        lang = user.language
    await callback.message.edit_text(  # type: ignore[union-attr]
        t("tz_choose_offset", lang), reply_markup=timezone_offset_keyboard(lang)
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# City selection
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("tz_city:"))
async def on_city_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle IANA city timezone selection."""
    if callback.data is None or callback.from_user is None:
        return
    iana = callback.data.split(":", 1)[1]

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    await UserRepo.update_timezone(
        session,
        user.id,
        tz_mode="city",
        tz_name=iana,
        tz_offset_minutes=None,
    )

    # Spec D3/FEAT-04: exact confirmation message.
    await callback.message.edit_text(  # type: ignore[union-attr]
        t("tz_saved", lang).format(tz=iana)
    )

    # Show Today's Stats (zeros for new users) + main keyboard.
    tz = user_timezone("city", iana, None)
    local_today = today_local(tz)
    stats = await today_stats(session, user.id, local_today)
    stats_text = format_today_stats(stats, lang)
    await callback.message.answer(  # type: ignore[union-attr]
        stats_text, reply_markup=main_keyboard(lang)
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# UTC offset selection
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("tz_offset:"))
async def on_offset_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle UTC offset timezone selection."""
    if callback.data is None or callback.from_user is None:
        return
    minutes = int(callback.data.split(":", 1)[1])
    hours = minutes // 60
    sign = "+" if hours >= 0 else ""

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    await UserRepo.update_timezone(
        session,
        user.id,
        tz_mode="offset",
        tz_name=None,
        tz_offset_minutes=minutes,
    )

    # Spec D3/FEAT-04: exact confirmation message.
    tz_label = f"UTC{sign}{hours}"
    await callback.message.edit_text(  # type: ignore[union-attr]
        t("tz_saved", lang).format(tz=tz_label)
    )

    # Show Today's Stats (zeros for new users) + main keyboard.
    tz = user_timezone("offset", None, minutes)
    local_today = today_local(tz)
    stats = await today_stats(session, user.id, local_today)
    stats_text = format_today_stats(stats, lang)
    await callback.message.answer(  # type: ignore[union-attr]
        stats_text, reply_markup=main_keyboard(lang)
    )
    await callback.answer()
