"""Stats command and callback handlers (spec §8)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters import format_four_week_stats, format_today_stats, format_weekly_stats
from app.bot.keyboards import main_keyboard, stats_keyboard
from app.core.time import last_7_days, last_28_days_weeks, today_local, user_timezone
from app.db.repos import UserRepo
from app.reports.stats import four_week_stats, today_stats, weekly_stats

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Handle /stats — show period selection keyboard."""
    await message.answer("Choose a stats period:", reply_markup=stats_keyboard())


@router.message(lambda m: m.text == "📊 Stats")
async def btn_stats(message: Message) -> None:
    """Handle 📊 Stats reply keyboard button."""
    await message.answer("Choose a stats period:", reply_markup=stats_keyboard())


@router.callback_query(F.data == "stats:today")
async def on_stats_today(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show Today's Stats."""
    if callback.from_user is None:
        return
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)

    stats = await today_stats(session, user.id, local_d)
    text = format_today_stats(stats)

    await callback.message.edit_text(text)  # type: ignore[union-attr]
    await callback.message.answer("👇", reply_markup=main_keyboard())  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "stats:weekly")
async def on_stats_weekly(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show Weekly Stats (last 7 days)."""
    if callback.from_user is None:
        return
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)

    dates = last_7_days(local_d)
    stats = await weekly_stats(session, user.id, dates)
    text = format_weekly_stats(stats)

    await callback.message.edit_text(text)  # type: ignore[union-attr]
    await callback.message.answer("👇", reply_markup=main_keyboard())  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "stats:4weeks")
async def on_stats_4weeks(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show 4-Week Stats (daily averages)."""
    if callback.from_user is None:
        return
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)

    weeks = last_28_days_weeks(local_d)
    stats = await four_week_stats(session, user.id, weeks)
    text = format_four_week_stats(stats)

    await callback.message.edit_text(text)  # type: ignore[union-attr]
    await callback.message.answer("👇", reply_markup=main_keyboard())  # type: ignore[union-attr]
    await callback.answer()
