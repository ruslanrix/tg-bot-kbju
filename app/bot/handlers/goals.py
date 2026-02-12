"""Goal selection handler (spec §3.2 /goals)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import goal_inline_keyboard, main_keyboard
from app.db.repos import UserRepo

router = Router(name="goals")


@router.message(Command("goals"))
async def cmd_goals(message: Message) -> None:
    """Handle /goals — show goal selection keyboard."""
    await message.answer("Choose your goal:", reply_markup=goal_inline_keyboard())


@router.message(lambda m: m.text == "🎯 Goals")
async def btn_goals(message: Message) -> None:
    """Handle the 🎯 Goals reply keyboard button."""
    await message.answer("Choose your goal:", reply_markup=goal_inline_keyboard())


@router.callback_query(F.data.startswith("goal:"))
async def on_goal_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle goal selection callback."""
    if callback.data is None or callback.from_user is None:
        return
    goal = callback.data.split(":", 1)[1]  # maintenance / deficit / bulk

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    await UserRepo.update_goal(session, user.id, goal)

    label = {"maintenance": "🏋️ Maintenance", "deficit": "📉 Deficit", "bulk": "💪 Bulk"}.get(
        goal, goal
    )
    await callback.message.edit_text(f"Goal set to {label} ✅")  # type: ignore[union-attr]
    await callback.message.answer("👇", reply_markup=main_keyboard())  # type: ignore[union-attr]
    await callback.answer()
