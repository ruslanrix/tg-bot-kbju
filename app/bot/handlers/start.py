"""/start and /help command handlers (spec §3.2–3.3)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import help_change_tz_keyboard, main_keyboard, timezone_city_keyboard
from app.bot.middlewares import ONBOARDING_TEXT_A, ONBOARDING_TEXT_B
from app.db.repos import UserRepo

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

    if user.tz_mode is None:
        # New user or timezone not set — show onboarding (spec FEAT-03).
        await message.answer(ONBOARDING_TEXT_A)
        await message.answer(
            ONBOARDING_TEXT_B,
            reply_markup=timezone_city_keyboard(),
        )
    else:
        # Returning user — normal welcome.
        await message.answer(
            "Welcome back! 🍽 Send me a photo or description of your food.",
            reply_markup=main_keyboard(),
        )


# ---------------------------------------------------------------------------
# /help + "☁️ Help" button
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "Hi. Every time you eat, send me a 📸 pic of your meal (or drink). "
    "I'll guess the macros, calories, caffeine and ingredients to help you "
    "keep track of your diet.\n\n"
    "Tip: Pin this chat so it stays at the top for easy access.\n"
    "Tip: You can write stuff like yesterday or two days ago when logging "
    "meals that you forgot to add before.\n\n"
    "Commands\n"
    "ℹ️ /help — What you're looking at now\n"
    "✍️ /add — Manually write any meal or drink without a photo\n"
    "📊 /stats — See your daily, weekly or monthly stats\n"
    "🎯 /goals — Set your calorie and macro goals\n"
    "🕘 /history — See your meal history and delete meals\n"
    "🗣️ /feedback — Send feedback to my maker\n"
    "🧾 /subscription — Manage your subscription\n\n"
    "🌍 Remember to change your time zone if you moved countries."
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help — show help text with Change TZ button."""
    await message.answer(HELP_TEXT, reply_markup=help_change_tz_keyboard())


@router.message(lambda m: m.text == "☁️ Help")
async def btn_help(message: Message) -> None:
    """Handle the ☁️ Help reply keyboard button."""
    await message.answer(HELP_TEXT, reply_markup=help_change_tz_keyboard())
