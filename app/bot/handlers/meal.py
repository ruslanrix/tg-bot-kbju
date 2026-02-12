"""Meal input and management handlers (spec §3.4–3.8, §5, §6).

Handles:
- Text/photo → precheck → rate limit → OpenAI → immediate save
- Saved meal edit / delete callbacks
- Edit flow via FSM (StatesGroup)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters import format_meal_saved, format_today_stats
from app.bot.keyboards import main_keyboard, saved_actions_keyboard
from app.core.time import today_local, user_timezone
from app.db.repos import MealRepo, UserRepo
from app.reports.stats import today_stats
from app.services.nutrition_ai import NutritionAIService, NutritionAnalysis
from app.services.precheck import (
    MSG_NOT_TEXT_OR_PHOTO,
    check_message_type,
    check_photo_size,
    check_text,
)
from app.services.rate_limit import ConcurrencyGuard, RateLimiter

logger = logging.getLogger(__name__)

router = Router(name="meal")

# ---------------------------------------------------------------------------
# Reject message for unrecognized food (spec §5.9)
# ---------------------------------------------------------------------------

MSG_UNRECOGNIZED = "I couldn't recognize the food. Please try sending it again."
MSG_THROTTLE = "Too many requests. Please wait a bit and try again 🙂"

# Module-level singletons (initialized in factory.py)
rate_limiter: RateLimiter | None = None
concurrency_guard: ConcurrencyGuard | None = None
ai_service: NutritionAIService | None = None
max_photo_bytes: int = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# FSM for edit flow
# ---------------------------------------------------------------------------


class EditMealStates(StatesGroup):
    """FSM states for editing a saved meal."""

    waiting_for_text = State()


# ---------------------------------------------------------------------------
# /add command + "✏️ Add Meal" button
# ---------------------------------------------------------------------------


@router.message(Command("add"))
async def cmd_add(message: Message) -> None:
    """Handle /add — prompt user to enter food."""
    await message.answer(
        "What did you eat? Send me a text description or a 📸 photo.",
        reply_markup=main_keyboard(),
    )


@router.message(lambda m: m.text == "✏️ Add Meal")
async def btn_add_meal(message: Message) -> None:
    """Handle ✏️ Add Meal reply keyboard button."""
    await message.answer(
        "What did you eat? Send me a text description or a 📸 photo.",
        reply_markup=main_keyboard(),
    )


# ---------------------------------------------------------------------------
# Photo handler
# ---------------------------------------------------------------------------


@router.message(F.photo)
async def handle_photo(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Process a photo message as a meal input."""
    if message.from_user is None:
        return

    # §5.6 — photo size guard: prefer largest variant that fits the limit.
    # Telegram provides multiple sizes; iterate from largest to smallest.
    photo = None
    for candidate in reversed(message.photo):
        if candidate.file_size is None or candidate.file_size <= max_photo_bytes:
            photo = candidate
            break
    if photo is None:
        # All variants exceed the limit.
        result = check_photo_size(message.photo[-1].file_size or 0, max_photo_bytes)
        await message.reply(result.reject_message or "")
        return

    # Text precheck on caption (if any)
    caption = message.caption or ""
    if caption:
        text_result = check_text(caption, has_photo=True)
        if not text_result.passed:
            await message.reply(text_result.reject_message or "")
            return

    # Rate limit + concurrency
    if not await _check_limits(message):
        return

    # Typing heartbeat + OpenAI call
    analysis = await _analyze_with_typing(
        message, bot, lambda svc: _do_photo_analysis(svc, bot, photo.file_id, caption)
    )
    if analysis is None:
        return

    await _handle_analysis_result(
        message, session, analysis, source="photo", photo_file_id=photo.file_id
    )


async def _do_photo_analysis(
    svc: NutritionAIService, bot: Bot, file_id: str, caption: str
) -> NutritionAnalysis:
    """Download photo and send to OpenAI."""
    file = await bot.get_file(file_id)
    if file.file_path is None:
        return NutritionAnalysis(action="reject_unrecognized")

    from io import BytesIO

    buf = BytesIO()
    await bot.download_file(file.file_path, buf)
    photo_bytes = buf.getvalue()

    return await svc.analyze_photo(photo_bytes, caption=caption or None)


# ---------------------------------------------------------------------------
# Text handler (catch-all for non-command text)
# ---------------------------------------------------------------------------

# Texts that are reply keyboard buttons — handled elsewhere.
_BUTTON_TEXTS = {"📊 Stats", "🎯 Goals", "☁️ Help", "🕘 History", "✏️ Add Meal"}


@router.message(F.text)
async def handle_text(message: Message, session: AsyncSession, bot: Bot, state: FSMContext) -> None:
    """Process free text as a meal input (or edit correction)."""
    if message.from_user is None or not message.text:
        return

    # Skip button texts
    if message.text in _BUTTON_TEXTS:
        return

    # Check if we're in edit-flow FSM
    current_state = await state.get_state()
    if current_state == EditMealStates.waiting_for_text.state:
        await _handle_edit_text(message, session, bot, state)
        return

    # §5.1 — message type gate (text is ok)
    # §5.2–5.5 — text checks
    text_result = check_text(message.text, has_photo=False)
    if not text_result.passed:
        await message.reply(text_result.reject_message or "")
        return

    # Rate limit + concurrency
    if not await _check_limits(message):
        return

    # Typing heartbeat + OpenAI call
    analysis = await _analyze_with_typing(
        message, bot, lambda svc: svc.analyze_text(message.text or "")
    )
    if analysis is None:
        return

    await _handle_analysis_result(
        message, session, analysis, source="text", original_text=message.text
    )


# ---------------------------------------------------------------------------
# Non-text/non-photo handler (spec §5.1)
# ---------------------------------------------------------------------------


@router.message()
async def handle_unsupported(message: Message) -> None:
    """Reject stickers, voice, video, etc."""
    result = check_message_type(has_text=bool(message.text), has_photo=bool(message.photo))
    if not result.passed:
        await message.reply(result.reject_message or MSG_NOT_TEXT_OR_PHOTO)


# ---------------------------------------------------------------------------
# Legacy draft callback fallbacks (backward compat after draft removal)
# ---------------------------------------------------------------------------

_DRAFT_EXPIRED_MSG = "This draft has expired. Please send your meal again."


@router.callback_query(F.data.startswith("draft_save:"))
async def on_legacy_draft_save(callback: CallbackQuery) -> None:
    """Handle legacy draft Save buttons from pre-deploy messages."""
    await callback.answer(_DRAFT_EXPIRED_MSG, show_alert=True)


@router.callback_query(F.data.startswith("draft_edit:"))
async def on_legacy_draft_edit(callback: CallbackQuery) -> None:
    """Handle legacy draft Edit buttons from pre-deploy messages."""
    await callback.answer(_DRAFT_EXPIRED_MSG, show_alert=True)


@router.callback_query(F.data.startswith("draft_delete:"))
async def on_legacy_draft_delete(callback: CallbackQuery) -> None:
    """Handle legacy draft Delete buttons from pre-deploy messages."""
    await callback.answer(_DRAFT_EXPIRED_MSG, show_alert=True)


# ---------------------------------------------------------------------------
# Saved meal callbacks
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("saved_edit:"))
async def on_saved_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Trigger edit flow for a saved meal."""
    if callback.from_user is None or callback.data is None:
        return
    meal_id_str = callback.data.split(":", 1)[1]

    await state.set_state(EditMealStates.waiting_for_text)
    await state.update_data(edit_meal_id=meal_id_str)

    await callback.message.edit_text("Send corrected text for this meal:")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("saved_delete:"))
async def on_saved_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Soft-delete a saved meal and show updated Today's Stats."""
    if callback.from_user is None or callback.data is None:
        return
    meal_id_str = callback.data.split(":", 1)[1]

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    deleted = await MealRepo.soft_delete(session, uuid.UUID(meal_id_str), user.id)

    if not deleted:
        await callback.answer("Meal not found.", show_alert=True)
        return

    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)
    stats = await today_stats(session, user.id, local_d)
    stats_text = format_today_stats(stats)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"🗑️ Deleted.\n\n{stats_text}"
    )
    await callback.message.answer("👇", reply_markup=main_keyboard())  # type: ignore[union-attr]
    await callback.answer()


# ---------------------------------------------------------------------------
# History delete callback
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("hist_delete:"))
async def on_history_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Soft-delete from history view."""
    if callback.from_user is None or callback.data is None:
        return
    meal_id_str = callback.data.split(":", 1)[1]

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    await MealRepo.soft_delete(session, uuid.UUID(meal_id_str), user.id)

    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)
    stats = await today_stats(session, user.id, local_d)
    stats_text = format_today_stats(stats)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"🗑️ Deleted.\n\n{stats_text}"
    )
    await callback.message.answer("👇", reply_markup=main_keyboard())  # type: ignore[union-attr]
    await callback.answer()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _check_limits(message: Message) -> bool:
    """Check rate limit and concurrency guard. Reply if exceeded."""
    if message.from_user is None:
        return False
    uid = message.from_user.id

    if rate_limiter and not rate_limiter.check(uid):
        await message.reply(MSG_THROTTLE)
        return False

    return True


async def _analyze_with_typing(
    message: Message,
    bot: Bot,
    analyze_fn: Any,
) -> NutritionAnalysis | None:
    """Run OpenAI analysis with typing heartbeat and concurrency guard.

    Returns the analysis result or None if throttled/errored.
    """
    if message.from_user is None or ai_service is None:
        await message.reply(MSG_UNRECOGNIZED)
        return None

    uid = message.from_user.id

    # Concurrency guard
    if concurrency_guard:
        async with concurrency_guard(uid) as ctx:
            if not ctx.acquired:
                await message.reply(MSG_THROTTLE)
                return None
            return await _run_with_typing(message, bot, analyze_fn)
    else:
        return await _run_with_typing(message, bot, analyze_fn)


async def _run_with_typing(
    message: Message,
    bot: Bot,
    analyze_fn: Any,
) -> NutritionAnalysis:
    """Execute analysis with typing action heartbeat."""
    stop_typing = asyncio.Event()

    async def typing_heartbeat() -> None:
        while not stop_typing.is_set():
            try:
                await bot.send_chat_action(message.chat.id, "typing")
            except Exception:
                pass
            await asyncio.sleep(4)

    task = asyncio.create_task(typing_heartbeat())
    try:
        analysis = await analyze_fn(ai_service)
    finally:
        stop_typing.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    return analysis


async def _handle_analysis_result(
    message: Message,
    session: AsyncSession,
    analysis: NutritionAnalysis,
    *,
    source: str,
    original_text: str | None = None,
    photo_file_id: str | None = None,
    edit_meal_id: uuid.UUID | None = None,
) -> None:
    """Handle an OpenAI analysis result — reject or save immediately."""
    if message.from_user is None:
        return

    # Reject actions
    if analysis.action == "reject_unrecognized":
        await message.reply(MSG_UNRECOGNIZED)
        return
    if analysis.action.startswith("reject_"):
        await message.reply(analysis.user_message or MSG_UNRECOGNIZED)
        return

    # action == "save" → save to DB immediately (no draft)
    uid = message.from_user.id
    user = await UserRepo.get_or_create(session, uid)
    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)

    if edit_meal_id is not None:
        # Update existing meal
        await MealRepo.update(
            session,
            edit_meal_id,
            user.id,
            meal_name=analysis.meal_name or "Unknown",
            calories_kcal=analysis.calories_kcal or 0,
            protein_g=analysis.protein_g or 0.0,
            carbs_g=analysis.carbs_g or 0.0,
            fat_g=analysis.fat_g or 0.0,
            weight_g=analysis.weight_g,
            volume_ml=analysis.volume_ml,
            caffeine_mg=analysis.caffeine_mg,
            likely_ingredients_json=[i.model_dump() for i in analysis.likely_ingredients],
            raw_ai_response=analysis.model_dump(),
        )
        meal_id_str = str(edit_meal_id)
    else:
        # Idempotency check
        if await MealRepo.exists_by_message(session, message.chat.id, message.message_id):
            await message.reply("Already saved.")
            return

        # Create new meal
        meal = await MealRepo.create(
            session,
            user_id=user.id,
            tg_chat_id=message.chat.id,
            tg_message_id=message.message_id,
            source=source,
            original_text=original_text,
            photo_file_id=photo_file_id,
            consumed_at_utc=datetime.now(timezone.utc),
            local_date=local_d,
            tz_name_snapshot=user.tz_name,
            tz_offset_minutes_snapshot=user.tz_offset_minutes,
            meal_name=analysis.meal_name or "Unknown",
            calories_kcal=analysis.calories_kcal or 0,
            protein_g=analysis.protein_g or 0.0,
            carbs_g=analysis.carbs_g or 0.0,
            fat_g=analysis.fat_g or 0.0,
            weight_g=analysis.weight_g,
            volume_ml=analysis.volume_ml,
            caffeine_mg=analysis.caffeine_mg,
            likely_ingredients_json=[i.model_dump() for i in analysis.likely_ingredients],
            raw_ai_response=analysis.model_dump(),
        )
        meal_id_str = str(meal.id)

    # Show saved message + Today's Stats + Edit/Delete keyboard
    saved_text = format_meal_saved(analysis)
    stats = await today_stats(session, user.id, local_d)
    stats_text = format_today_stats(stats)

    await message.reply(
        f"{saved_text}\n\n{stats_text}",
        reply_markup=saved_actions_keyboard(meal_id_str),
    )


async def _handle_edit_text(
    message: Message, session: AsyncSession, bot: Bot, state: FSMContext
) -> None:
    """Handle corrected text in edit flow — re-analyze and update directly."""
    if message.from_user is None or not message.text:
        return

    data = await state.get_data()
    edit_meal_id_str = data.get("edit_meal_id")
    edit_meal_id = uuid.UUID(edit_meal_id_str) if edit_meal_id_str else None

    await state.clear()

    # Precheck
    text_result = check_text(message.text, has_photo=False)
    if not text_result.passed:
        await message.reply(text_result.reject_message or "")
        return

    # Rate limit
    if not await _check_limits(message):
        return

    # OpenAI analysis (required per spec §3.7 — ingredients must be generated)
    analysis = await _analyze_with_typing(
        message, bot, lambda svc: svc.analyze_text(message.text or "")
    )
    if analysis is None:
        return

    await _handle_analysis_result(
        message,
        session,
        analysis,
        source="text",
        original_text=message.text,
        edit_meal_id=edit_meal_id,
    )
