"""Stats command and callback handlers (spec §8)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters import format_four_week_stats, format_today_stats, format_weekly_stats
from app.bot.keyboards import stats_keyboard
from app.core.time import last_7_days, last_28_days_weeks, today_local, user_timezone
from app.db.repos import UserRepo
from app.i18n import t
from app.reports.stats import four_week_stats, today_stats, weekly_stats

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    """Handle /stats — show period selection keyboard."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("stats_choose_period", lang), reply_markup=stats_keyboard(lang))


@router.message(lambda m: m.text in ("📊 Stats", "📊 Статистика"))
async def btn_stats(message: Message, session: AsyncSession) -> None:
    """Handle 📊 Stats reply keyboard button (EN or RU label)."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("stats_choose_period", lang), reply_markup=stats_keyboard(lang))


@router.callback_query(F.data == "stats:today")
async def on_stats_today(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show Today's Stats."""
    if callback.from_user is None:
        return
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)

    stats = await today_stats(session, user.id, local_d)
    text = format_today_stats(stats, lang)

    await callback.message.edit_text(text)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "stats:weekly")
async def on_stats_weekly(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show Weekly Stats (last 7 days)."""
    if callback.from_user is None:
        return
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)

    dates = last_7_days(local_d)
    stats = await weekly_stats(session, user.id, dates)
    text = format_weekly_stats(stats, lang)

    await callback.message.edit_text(text)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "stats:4weeks")
async def on_stats_4weeks(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show 4-Week Stats (daily averages)."""
    if callback.from_user is None:
        return
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)

    weeks = last_28_days_weeks(local_d)
    stats = await four_week_stats(session, user.id, weeks)
    text = format_four_week_stats(stats, lang)

    await callback.message.edit_text(text)  # type: ignore[union-attr]
    await callback.answer()
