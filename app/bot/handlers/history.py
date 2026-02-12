"""History command handler (spec §9).

Shows the last 20 non-deleted meals with inline delete buttons.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters import format_history_entry
from app.bot.keyboards import history_delete_keyboard
from app.db.repos import MealRepo, UserRepo
from app.i18n import t

router = Router(name="history")


@router.message(Command("history"))
async def cmd_history(message: Message, session: AsyncSession) -> None:
    """Handle /history — show recent meals with delete buttons."""
    await _show_history(message, session)


@router.message(lambda m: m.text in ("🕘 History", "🕘 История"))
async def btn_history(message: Message, session: AsyncSession) -> None:
    """Handle the 🕘 History reply keyboard button (EN or RU label)."""
    await _show_history(message, session)


async def _show_history(message: Message, session: AsyncSession) -> None:
    """Fetch and display recent meals."""
    if message.from_user is None:
        return

    user = await UserRepo.get_or_create(session, message.from_user.id)
    lang = user.language
    meals = await MealRepo.list_recent(session, user.id, limit=20)

    if not meals:
        await message.answer(t("fmt_no_meals", lang))
        return

    for meal in meals:
        text = format_history_entry(
            meal_name=meal.meal_name,
            calories_kcal=meal.calories_kcal,
            protein_g=meal.protein_g,
            carbs_g=meal.carbs_g,
            fat_g=meal.fat_g,
            local_date=meal.local_date,
        )
        await message.answer(
            text,
            reply_markup=history_delete_keyboard(str(meal.id), lang),
        )
