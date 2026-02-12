"""Stub command handlers (spec §2 — out of scope).

/feedback and /subscription are placeholders for future features.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repos import UserRepo
from app.i18n import t

router = Router(name="stubs")


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, session: AsyncSession) -> None:
    """Handle /feedback — stub."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("stub_feedback", lang))


@router.message(Command("subscription"))
async def cmd_subscription(message: Message, session: AsyncSession) -> None:
    """Handle /subscription — stub."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(t("stub_subscription", lang))
