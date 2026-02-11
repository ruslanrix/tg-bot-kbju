"""Timezone selection handlers (spec §4).

Supports two flows:
1. City list — popular IANA timezones.
2. UTC offset — from UTC-12 to UTC+14.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import timezone_city_keyboard, timezone_offset_keyboard
from app.db.repos import UserRepo

router = Router(name="timezone")


# ---------------------------------------------------------------------------
# Menu navigation
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "tz_city_menu")
async def show_city_menu(callback: CallbackQuery) -> None:
    """Show the city selection keyboard."""
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🌍 Choose your city:", reply_markup=timezone_city_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "tz_offset_menu")
async def show_offset_menu(callback: CallbackQuery) -> None:
    """Show the UTC offset selection keyboard."""
    await callback.message.edit_text(  # type: ignore[union-attr]
        "⏱ Choose your UTC offset:", reply_markup=timezone_offset_keyboard()
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
    await UserRepo.update_timezone(
        session,
        user.id,
        tz_mode="city",
        tz_name=iana,
        tz_offset_minutes=None,
    )

    await callback.message.edit_text(f"Timezone set to {iana} ✅")  # type: ignore[union-attr]
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
    await UserRepo.update_timezone(
        session,
        user.id,
        tz_mode="offset",
        tz_name=None,
        tz_offset_minutes=minutes,
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Timezone set to UTC{sign}{hours} ✅"
    )
    await callback.answer()
