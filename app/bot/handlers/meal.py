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
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters import format_meal_saved, format_today_stats
from app.bot.keyboards import (
    all_main_button_texts,
    edit_feedback_keyboard,
    main_keyboard,
    saved_actions_keyboard,
)
from app.core.time import today_local, user_timezone
from app.db.repos import MealRepo, UserRepo
from app.i18n import t
from app.reports.stats import today_stats
from app.services.nutrition_ai import NutritionAIService, NutritionAnalysis, sanity_check
from app.services.precheck import (
    REJECT_NOT_TEXT_OR_PHOTO,
    check_message_type,
    check_photo_size,
    check_text,
)
from app.services.rate_limit import ConcurrencyGuard, RateLimiter

logger = logging.getLogger(__name__)

router = Router(name="meal")

# Module-level singletons (initialized in factory.py)
rate_limiter: RateLimiter | None = None
concurrency_guard: ConcurrencyGuard | None = None
ai_service: NutritionAIService | None = None
max_photo_bytes: int = 5 * 1024 * 1024
edit_window_hours: int = 48
delete_window_hours: int = 48
EDIT_TIMEOUT: int = 300  # seconds (5 min)

_timeout_tasks: dict[int, asyncio.Task[None]] = {}


# ---------------------------------------------------------------------------
# FSM for edit flow
# ---------------------------------------------------------------------------


class EditMealStates(StatesGroup):
    """FSM states for editing a saved meal.

    FSM data contract (set by on_saved_edit, consumed by helpers):
        edit_meal_id: str          -- UUID of meal being edited
        prompt_chat_id: int        -- chat where prompt message lives
        prompt_message_id: int     -- message_id of the prompt message
        session_token: str         -- uuid4 hex to invalidate stale callbacks
        deadline: float            -- UTC timestamp when session expires
    """

    waiting_for_text = State()


# ---------------------------------------------------------------------------
# Edit-session lifecycle helpers (FEAT-04)
# ---------------------------------------------------------------------------


async def _timeout_coro(
    user_id: int,
    chat_id: int,
    message_id: int,
    session_token: str,  # noqa: ARG001
    bot: Bot,
    lang: str,
) -> None:
    """Sleep until deadline, then edit prompt to timeout status."""
    try:
        await asyncio.sleep(EDIT_TIMEOUT)
    except asyncio.CancelledError:
        return

    # Verify this task is still the active one for this user
    if _timeout_tasks.get(user_id) is not asyncio.current_task():
        return

    _timeout_tasks.pop(user_id, None)

    try:
        await bot.edit_message_text(
            text=t("edit_feedback_timeout", lang),
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )
    except TelegramBadRequest as exc:
        logger.debug("Timeout edit failed (message gone?): %s", exc)
    except Exception:
        logger.exception("Unexpected error editing timeout message")


def start_timeout_task(
    user_id: int,
    chat_id: int,
    msg_id: int,
    session_token: str,
    bot: Bot,
    lang: str,
) -> None:
    """Start (or restart) the edit-session timeout for a user."""
    cancel_timeout_task(user_id)
    task = asyncio.create_task(
        _timeout_coro(user_id, chat_id, msg_id, session_token, bot, lang),
        name=f"edit_timeout_{user_id}",
    )
    _timeout_tasks[user_id] = task


def cancel_timeout_task(user_id: int) -> None:
    """Cancel any active timeout task for the given user (no-op if none)."""
    task = _timeout_tasks.pop(user_id, None)
    if task is not None and not task.done():
        task.cancel()


async def finalize_edit_session(state: FSMContext, user_id: int) -> None:
    """Cancel timeout and fully clear the edit FSM state."""
    cancel_timeout_task(user_id)
    await state.clear()


# ---------------------------------------------------------------------------
# /add command + "✏️ Add Meal" button
# ---------------------------------------------------------------------------


@router.message(Command("add"))
async def cmd_add(message: Message, session: AsyncSession) -> None:
    """Handle /add — prompt user to enter food."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(
        t("add_prompt", lang),
        reply_markup=main_keyboard(lang),
    )


@router.message(lambda m: m.text in ("✏️ Add Meal", "✏️ Добавить"))
async def btn_add_meal(message: Message, session: AsyncSession) -> None:
    """Handle ✏️ Add Meal reply keyboard button (EN or RU label)."""
    if message.from_user is None:
        lang = "EN"
    else:
        user = await UserRepo.get_or_create(session, message.from_user.id)
        lang = user.language
    await message.answer(
        t("add_prompt", lang),
        reply_markup=main_keyboard(lang),
    )


# ---------------------------------------------------------------------------
# Photo handler
# ---------------------------------------------------------------------------


@router.message(F.photo)
async def handle_photo(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Process a photo message as a meal input."""
    if message.from_user is None:
        return

    user = await UserRepo.get_or_create(session, message.from_user.id)
    lang = user.language

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
        await message.reply(t(result.reject_key or "", lang))
        return

    # Text precheck on caption (if any)
    caption = message.caption or ""
    if caption:
        text_result = check_text(caption, has_photo=True)
        if not text_result.passed:
            await message.reply(t(text_result.reject_key or "", lang))
            return

    # Rate limit + concurrency
    if not await _check_limits(message, lang):
        return

    # Send processing message (spec D4/FEAT-06)
    proc_msg = await message.reply(t("msg_processing_new", lang))

    # Typing heartbeat + OpenAI call
    analysis = await _analyze_with_typing(
        message, bot, lambda svc: _do_photo_analysis(svc, bot, photo.file_id, caption, lang=lang),
        proc_msg=proc_msg,
        lang=lang,
    )
    if analysis is None:
        return

    await _handle_analysis_result(
        message, session, analysis, source="photo",
        photo_file_id=photo.file_id, proc_msg=proc_msg, lang=lang,
    )


async def _do_photo_analysis(
    svc: NutritionAIService, bot: Bot, file_id: str, caption: str, *, lang: str = "EN"
) -> NutritionAnalysis:
    """Download photo and send to OpenAI."""
    file = await bot.get_file(file_id)
    if file.file_path is None:
        return NutritionAnalysis(action="reject_unrecognized")

    from io import BytesIO

    buf = BytesIO()
    await bot.download_file(file.file_path, buf)
    photo_bytes = buf.getvalue()

    return await svc.analyze_photo(photo_bytes, caption=caption or None, lang=lang)


# ---------------------------------------------------------------------------
# Text handler (catch-all for non-command text)
# ---------------------------------------------------------------------------

# Texts that are reply keyboard buttons — handled elsewhere.
# Collect from ALL locales to avoid treating localized buttons as meal input.
_BUTTON_TEXTS: set[str] = all_main_button_texts()


@router.message(F.text)
async def handle_text(message: Message, session: AsyncSession, bot: Bot, state: FSMContext) -> None:
    """Process free text as a meal input (or edit correction)."""
    if message.from_user is None or not message.text:
        return

    # Skip button texts (both EN and RU)
    if message.text in _BUTTON_TEXTS:
        return

    # Check if we're in edit-flow FSM
    current_state = await state.get_state()
    if current_state == EditMealStates.waiting_for_text.state:
        await _handle_edit_text(message, session, bot, state)
        return

    user = await UserRepo.get_or_create(session, message.from_user.id)
    lang = user.language

    # §5.1 — message type gate (text is ok)
    # §5.2–5.5 — text checks
    text_result = check_text(message.text, has_photo=False)
    if not text_result.passed:
        await message.reply(t(text_result.reject_key or "", lang))
        return

    # Rate limit + concurrency
    if not await _check_limits(message, lang):
        return

    # Send processing message (spec D4/FEAT-06)
    proc_msg = await message.reply(t("msg_processing_new", lang))

    # Typing heartbeat + OpenAI call
    analysis = await _analyze_with_typing(
        message, bot, lambda svc: svc.analyze_text(message.text or "", lang=lang),
        proc_msg=proc_msg,
        lang=lang,
    )
    if analysis is None:
        return

    await _handle_analysis_result(
        message, session, analysis, source="text",
        original_text=message.text, proc_msg=proc_msg, lang=lang,
    )


# ---------------------------------------------------------------------------
# Non-text/non-photo handler (spec §5.1)
# ---------------------------------------------------------------------------


@router.message()
async def handle_unsupported(message: Message, session: AsyncSession) -> None:
    """Reject stickers, voice, video, etc."""
    result = check_message_type(has_text=bool(message.text), has_photo=bool(message.photo))
    if not result.passed:
        lang = "EN"
        if message.from_user:
            user = await UserRepo.get_or_create(session, message.from_user.id)
            lang = user.language
        await message.reply(t(result.reject_key or REJECT_NOT_TEXT_OR_PHOTO, lang))


# ---------------------------------------------------------------------------
# Legacy draft callback fallbacks (backward compat after draft removal)
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("draft_save:"))
async def on_legacy_draft_save(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle legacy draft Save buttons from pre-deploy messages."""
    lang = await _get_lang(callback, session)
    await callback.answer(t("draft_expired", lang), show_alert=True)


@router.callback_query(F.data.startswith("draft_edit:"))
async def on_legacy_draft_edit(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle legacy draft Edit buttons from pre-deploy messages."""
    lang = await _get_lang(callback, session)
    await callback.answer(t("draft_expired", lang), show_alert=True)


@router.callback_query(F.data.startswith("draft_delete:"))
async def on_legacy_draft_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle legacy draft Delete buttons from pre-deploy messages."""
    lang = await _get_lang(callback, session)
    await callback.answer(t("draft_expired", lang), show_alert=True)


# ---------------------------------------------------------------------------
# Saved meal callbacks
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("saved_edit:"))
async def on_saved_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    """Trigger edit flow for a saved meal (with edit-window guard)."""
    if callback.from_user is None or callback.data is None:
        return
    meal_id_str = callback.data.split(":", 1)[1]

    try:
        meal_uuid = uuid.UUID(meal_id_str)
    except ValueError:
        await callback.answer(t("meal_not_found", "EN"), show_alert=True)
        return

    # Edit window guard (spec D6/FEAT-08)
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    meal = await MealRepo.get_by_id(session, meal_uuid, user.id)
    if meal is None:
        await callback.answer(t("meal_not_found", lang), show_alert=True)
        return

    age = datetime.now(timezone.utc) - meal.consumed_at_utc
    if age.total_seconds() > edit_window_hours * 3600:
        await callback.answer(
            t("msg_edit_window_expired", lang).format(hours=edit_window_hours),
            show_alert=True,
        )
        return

    user_id = callback.from_user.id

    # Cancel previous edit session if any (mark old prompt as replaced)
    prev_data = await state.get_data()
    prev_prompt_chat = prev_data.get("prompt_chat_id")
    prev_prompt_msg = prev_data.get("prompt_message_id")
    if prev_prompt_chat and prev_prompt_msg and callback.bot:
        try:
            await callback.bot.edit_message_text(
                text=t("edit_feedback_replaced", lang),
                chat_id=prev_prompt_chat,
                message_id=prev_prompt_msg,
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass  # old prompt already gone
    cancel_timeout_task(user_id)

    # Send new prompt message with feedback keyboard
    prompt_msg = await callback.message.answer(  # type: ignore[union-attr]
        t("edit_feedback_prompt", lang),
        reply_markup=edit_feedback_keyboard(meal_id_str, lang),
    )

    # Set FSM state with full data contract
    session_token = uuid.uuid4().hex
    await state.set_state(EditMealStates.waiting_for_text)
    await state.update_data(
        edit_meal_id=meal_id_str,
        prompt_chat_id=prompt_msg.chat.id,
        prompt_message_id=prompt_msg.message_id,
        session_token=session_token,
        deadline=datetime.now(timezone.utc).timestamp() + EDIT_TIMEOUT,
    )

    # Start 5-minute timeout
    start_timeout_task(
        user_id, prompt_msg.chat.id, prompt_msg.message_id,
        session_token, callback.bot, lang,  # type: ignore[arg-type]
    )

    await callback.answer()


@router.callback_query(F.data.startswith("saved_delete:"))
async def on_saved_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Soft-delete a saved meal (with delete-window guard)."""
    if callback.from_user is None or callback.data is None:
        return
    meal_id_str = callback.data.split(":", 1)[1]

    try:
        meal_uuid = uuid.UUID(meal_id_str)
    except ValueError:
        await callback.answer(t("meal_not_found", "EN"), show_alert=True)
        return

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    meal = await MealRepo.get_by_id(session, meal_uuid, user.id)
    if meal is None:
        await callback.answer(t("meal_not_found", lang), show_alert=True)
        return

    # Delete window guard (spec D6/D7/FEAT-09)
    age = datetime.now(timezone.utc) - meal.consumed_at_utc
    if age.total_seconds() > delete_window_hours * 3600:
        await callback.answer(
            t("msg_delete_window_expired", lang).format(hours=delete_window_hours),
            show_alert=True,
        )
        return

    deleted = await MealRepo.soft_delete(session, meal_uuid, user.id)
    if not deleted:
        await callback.answer(t("meal_not_found", lang), show_alert=True)
        return

    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)
    stats = await today_stats(session, user.id, local_d)
    stats_text = format_today_stats(stats, lang)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"{t('deleted_label', lang)}\n\n{stats_text}"
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# History delete callback
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("hist_delete:"))
async def on_history_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Soft-delete from history view (with delete-window guard)."""
    if callback.from_user is None or callback.data is None:
        return
    meal_id_str = callback.data.split(":", 1)[1]

    try:
        meal_uuid = uuid.UUID(meal_id_str)
    except ValueError:
        await callback.answer(t("meal_not_found", "EN"), show_alert=True)
        return

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    lang = user.language
    meal = await MealRepo.get_by_id(session, meal_uuid, user.id)
    if meal is None:
        await callback.answer(t("meal_not_found", lang), show_alert=True)
        return

    # Delete window guard (spec D6/D7/FEAT-09)
    age = datetime.now(timezone.utc) - meal.consumed_at_utc
    if age.total_seconds() > delete_window_hours * 3600:
        await callback.answer(
            t("msg_delete_window_expired", lang).format(hours=delete_window_hours),
            show_alert=True,
        )
        return

    deleted = await MealRepo.soft_delete(session, meal_uuid, user.id)
    if not deleted:
        await callback.answer(t("meal_not_found", lang), show_alert=True)
        return

    tz = user_timezone(user.tz_mode, user.tz_name, user.tz_offset_minutes)
    local_d = today_local(tz)
    stats = await today_stats(session, user.id, local_d)
    stats_text = format_today_stats(stats, lang)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"{t('deleted_label', lang)}\n\n{stats_text}"
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_lang(callback: CallbackQuery, session: AsyncSession) -> str:
    """Resolve user language from a callback query."""
    if callback.from_user is None:
        return "EN"
    user = await UserRepo.get_or_create(session, callback.from_user.id)
    return user.language


async def _check_limits(message: Message, lang: str = "EN") -> bool:
    """Check rate limit and concurrency guard. Reply if exceeded."""
    if message.from_user is None:
        return False
    uid = message.from_user.id

    if rate_limiter and not rate_limiter.check(uid):
        await message.reply(t("msg_throttle", lang))
        return False

    return True


async def _analyze_with_typing(
    message: Message,
    bot: Bot,
    analyze_fn: Any,
    *,
    proc_msg: Message | None = None,
    lang: str = "EN",
) -> NutritionAnalysis | None:
    """Run OpenAI analysis with typing heartbeat and concurrency guard.

    Returns the analysis result or ``None`` if throttled/errored.
    When *proc_msg* is provided, throttle and error messages are written
    into the processing message (edit in place) instead of sending a new reply.
    """

    async def _reply_or_edit(text: str) -> None:
        if proc_msg is not None:
            await proc_msg.edit_text(text)
        else:
            await message.reply(text)

    if message.from_user is None or ai_service is None:
        await _reply_or_edit(t("msg_unrecognized", lang))
        return None

    uid = message.from_user.id

    # Concurrency guard
    if concurrency_guard:
        async with concurrency_guard(uid) as ctx:
            if not ctx.acquired:
                await _reply_or_edit(t("msg_throttle", lang))
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
    proc_msg: Message | None = None,
    lang: str = "EN",
) -> None:
    """Handle an OpenAI analysis result — reject or save immediately.

    If *proc_msg* is provided, the processing message is edited in place
    with the final output (spec D4/FEAT-06). Otherwise, a new reply is sent.
    """
    if message.from_user is None:
        return

    async def _respond(text: str, **kwargs: Any) -> None:
        """Edit processing message or send new reply."""
        if proc_msg is not None:
            await proc_msg.edit_text(text, **kwargs)
        else:
            await message.reply(text, **kwargs)

    # Reject actions
    if analysis.action == "reject_unrecognized":
        await _respond(t("msg_unrecognized", lang))
        return
    if analysis.action.startswith("reject_"):
        await _respond(analysis.user_message or t("msg_unrecognized", lang))
        return

    # Sanity check (spec D5/FEAT-07) — reject absurd values
    sanity_error = sanity_check(analysis)
    if sanity_error is not None:
        logger.warning("Sanity check failed: %s", sanity_error)
        await _respond(t("msg_sanity_fail", lang))
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
            await _respond(t("already_saved", lang))
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
    saved_text = format_meal_saved(analysis, lang)
    stats = await today_stats(session, user.id, local_d)
    stats_text = format_today_stats(stats, lang)

    await _respond(
        f"{saved_text}\n\n{stats_text}",
        reply_markup=saved_actions_keyboard(meal_id_str, lang),
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

    await finalize_edit_session(state, message.from_user.id)

    user = await UserRepo.get_or_create(session, message.from_user.id)
    lang = user.language

    # Re-check edit window (P1: user may have waited after entering FSM)
    if edit_meal_id is not None:
        meal = await MealRepo.get_by_id(session, edit_meal_id, user.id)
        if meal is None:
            await message.reply(t("meal_not_found", lang))
            return
        age = datetime.now(timezone.utc) - meal.consumed_at_utc
        if age.total_seconds() > edit_window_hours * 3600:
            await message.reply(
                t("msg_edit_window_expired", lang).format(hours=edit_window_hours)
            )
            return

    # Precheck
    text_result = check_text(message.text, has_photo=False)
    if not text_result.passed:
        await message.reply(t(text_result.reject_key or "", lang))
        return

    # Rate limit
    if not await _check_limits(message, lang):
        return

    # Send edit-specific processing message (spec D4/FEAT-06)
    proc_msg = await message.reply(t("msg_processing_edit", lang))

    # OpenAI analysis (required per spec §3.7 — ingredients must be generated)
    analysis = await _analyze_with_typing(
        message, bot, lambda svc: svc.analyze_text(message.text or "", lang=lang),
        proc_msg=proc_msg,
        lang=lang,
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
        proc_msg=proc_msg,
        lang=lang,
    )
