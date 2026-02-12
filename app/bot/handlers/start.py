"""/start and /help command handlers (spec §3.2–3.3)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import help_change_tz_keyboard, main_keyboard, timezone_city_keyboard
from app.db.repos import UserRepo
from app.i18n import t

router = Router(name="start")


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Handle /start — register user and show main keyboard or onboarding."""
    if message.from_user is None:
        return
    user = await UserRepo.get_or_create(session, message.from_user.id)
    lang = user.language

    if user.tz_mode is None:
        # New user or timezone not set — show onboarding (spec FEAT-03).
        await message.answer(t("onboarding_a", lang))
        await message.answer(
            t("onboarding_b", lang),
            reply_markup=timezone_city_keyboard(lang),
        )
    else:
        # Returning user — normal welcome.
        await message.answer(
            t("welcome_back", lang),
            reply_markup=main_keyboard(lang),
        )


# ---------------------------------------------------------------------------
# /help + "☁️ Help" button
# ---------------------------------------------------------------------------


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession) -> None:
    """Handle /help — show help text with Change TZ button."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("help_text", lang), reply_markup=help_change_tz_keyboard(lang))


@router.message(lambda m: m.text in ("☁️ Help", "☁️ Помощь"))
async def btn_help(message: Message, session: AsyncSession) -> None:
    """Handle the ☁️ Help reply keyboard button (EN or RU label)."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("help_text", lang), reply_markup=help_change_tz_keyboard(lang))
