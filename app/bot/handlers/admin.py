"""Admin command handlers (FEAT-12 / D8).

Provides simple in-chat admin controls guarded by ``ADMIN_IDS``.
Non-admin users always receive ``Not authorized.``

Commands:
- ``/admin_ping`` — liveness check
- ``/admin_stats`` — user and meal counts
- ``/admin_limits`` — current configuration limits
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import MealEntry, User

router = Router(name="admin")

# Module-level settings wired by factory.py
admin_ids: list[int] = []

NOT_AUTHORIZED = "Not authorized."


def _is_admin(tg_user_id: int | None) -> bool:
    """Check if the Telegram user ID is in the admin list."""
    if tg_user_id is None:
        return False
    return tg_user_id in admin_ids


@router.message(Command("admin_ping"))
async def cmd_admin_ping(message: Message) -> None:
    """Liveness check for admins."""
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.reply(NOT_AUTHORIZED)
        return

    await message.reply("pong")


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message, session: AsyncSession) -> None:
    """Show basic bot statistics."""
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.reply(NOT_AUTHORIZED)
        return

    # Total users
    total_users_result = await session.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar_one()

    # Total active (non-deleted) meals
    total_meals_result = await session.execute(
        select(func.count(MealEntry.id)).where(MealEntry.is_deleted.is_(False))
    )
    total_meals = total_meals_result.scalar_one()

    # Meals logged today (UTC)
    today = date.today()
    today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    today_meals_result = await session.execute(
        select(func.count(MealEntry.id)).where(
            MealEntry.is_deleted.is_(False),
            MealEntry.consumed_at_utc >= today_start,
        )
    )
    today_meals = today_meals_result.scalar_one()

    text = (
        f"📊 Bot Statistics\n"
        f"Users: {total_users}\n"
        f"Meals (total): {total_meals}\n"
        f"Meals (today UTC): {today_meals}"
    )
    await message.reply(text)


@router.message(Command("admin_limits"))
async def cmd_admin_limits(message: Message) -> None:
    """Show current configuration limits."""
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.reply(NOT_AUTHORIZED)
        return

    settings = get_settings()

    text = (
        f"⚙️ Configuration Limits\n"
        f"Rate limit: {settings.RATE_LIMIT_PER_MINUTE}/min\n"
        f"Max concurrent: {settings.MAX_CONCURRENT_PER_USER}\n"
        f"Edit window: {settings.EDIT_WINDOW_HOURS}h\n"
        f"Delete window: {settings.DELETE_WINDOW_HOURS}h\n"
        f"Purge after: {settings.PURGE_DELETED_AFTER_DAYS}d\n"
        f"Reminder inactivity: {settings.REMINDER_INACTIVITY_HOURS}h\n"
        f"Reminder cooldown: {settings.REMINDER_COOLDOWN_HOURS}h\n"
        f"OpenAI model: {settings.OPENAI_MODEL}\n"
        f"OpenAI timeout: {settings.OPENAI_TIMEOUT_SECONDS}s\n"
        f"Max photo: {settings.MAX_PHOTO_BYTES // 1024}KB"
    )
    await message.reply(text)
