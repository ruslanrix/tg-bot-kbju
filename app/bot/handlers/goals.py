"""Goal selection handler (spec §3.2 /goals)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import goal_inline_keyboard
from app.db.repos import UserRepo
from app.i18n import t

router = Router(name="goals")


@router.message(Command("goals"))
async def cmd_goals(message: Message, session: AsyncSession) -> None:
    """Handle /goals — show goal selection keyboard."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("goals_prompt", lang), reply_markup=goal_inline_keyboard(lang))


@router.message(lambda m: m.text in ("🎯 Goals", "🎯 Цели"))
async def btn_goals(message: Message, session: AsyncSession) -> None:
    """Handle the 🎯 Goals reply keyboard button (EN or RU label)."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("goals_prompt", lang), reply_markup=goal_inline_keyboard(lang))


@router.callback_query(F.data.startswith("goal:"))
async def on_goal_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle goal selection callback."""
    if callback.data is None or callback.from_user is None:
        return
    goal = callback.data.split(":", 1)[1]  # maintenance / deficit / bulk

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    await UserRepo.update_goal(session, user.id, goal)

    label = {
        "maintenance": t("goal_maintenance", lang),
        "deficit": t("goal_deficit", lang),
        "bulk": t("goal_bulk", lang),
    }.get(goal, goal)
    await callback.message.edit_text(  # type: ignore[union-attr]
        t("goal_set_confirmation", lang).format(label=label)
    )
    await callback.answer()
