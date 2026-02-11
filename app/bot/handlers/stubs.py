"""Stub command handlers (spec §2 — out of scope).

/feedback and /subscription are placeholders for future features.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="stubs")


@router.message(Command("feedback"))
async def cmd_feedback(message: Message) -> None:
    """Handle /feedback — stub."""
    await message.answer("Thanks! Feedback feature coming soon. 🗣️")


@router.message(Command("subscription"))
async def cmd_subscription(message: Message) -> None:
    """Handle /subscription — stub."""
    await message.answer("Subscription management coming soon. 🧾")
