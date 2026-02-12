"""Aiogram outer middlewares for DB session, logging, activity, and timezone gate.

``DBSessionMiddleware`` injects an ``AsyncSession`` into handler data
(key ``"session"``), committing on success and rolling back on error.

``LoggingMiddleware`` sets logging contextvars from the incoming update
so structured log lines automatically include ``tg_user_id``,
``chat_id``, ``message_id``.

``ActivityMiddleware`` updates ``last_activity_at`` for every user
interaction after the handler completes successfully.

``TimezoneGateMiddleware`` intercepts all user input when timezone is not
set and redirects to the onboarding flow (spec D2/FEAT-03).
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards import timezone_city_keyboard
from app.db.repos import UserRepo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context vars for logging (accessible via logging extra / filters)
# ---------------------------------------------------------------------------
ctx_tg_user_id: ContextVar[int | None] = ContextVar("tg_user_id", default=None)
ctx_chat_id: ContextVar[int | None] = ContextVar("chat_id", default=None)
ctx_message_id: ContextVar[int | None] = ContextVar("message_id", default=None)


# ---------------------------------------------------------------------------
# DB session middleware
# ---------------------------------------------------------------------------


class DBSessionMiddleware(BaseMiddleware):
    """Inject an ``AsyncSession`` into handler data, manage commit/rollback.

    Register as an **outer** middleware on the dispatcher so every
    handler (message, callback, etc.) gets a session via ``data["session"]``.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


# ---------------------------------------------------------------------------
# Logging context middleware
# ---------------------------------------------------------------------------


class LoggingMiddleware(BaseMiddleware):
    """Extract Telegram IDs from the update and set context vars.

    This makes ``tg_user_id``, ``chat_id``, ``message_id`` available
    to the JSON log formatter without explicit ``extra=`` in every call.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract IDs from the raw Update object.
        if isinstance(event, Update):
            msg = event.message or (event.callback_query.message if event.callback_query else None)
            user = None
            if event.message and event.message.from_user:
                user = event.message.from_user
            elif event.callback_query and event.callback_query.from_user:
                user = event.callback_query.from_user

            tok_uid = ctx_tg_user_id.set(user.id if user else None)
            tok_cid = ctx_chat_id.set(msg.chat.id if msg else None)  # type: ignore[union-attr]
            tok_mid = ctx_message_id.set(msg.message_id if msg else None)  # type: ignore[union-attr]
        else:
            tok_uid = ctx_tg_user_id.set(None)
            tok_cid = ctx_chat_id.set(None)
            tok_mid = ctx_message_id.set(None)

        try:
            return await handler(event, data)
        finally:
            ctx_tg_user_id.reset(tok_uid)
            ctx_chat_id.reset(tok_cid)
            ctx_message_id.reset(tok_mid)


# ---------------------------------------------------------------------------
# Activity tracking middleware (FEAT-11)
# ---------------------------------------------------------------------------


class ActivityMiddleware(BaseMiddleware):
    """Update ``last_activity_at`` on every successful user interaction.

    Registered as an **update-level outer** middleware *after*
    ``DBSessionMiddleware`` so a session is available, and *after*
    ``LoggingMiddleware`` for consistency.

    The touch is executed **after** the downstream handler returns
    successfully, inside a SAVEPOINT (``begin_nested``) so that a
    failed touch rolls back only the savepoint — never the main
    transaction.  Failures are silently logged.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        # Only touch activity for real user updates.
        if not isinstance(event, Update):
            return result

        tg_user_id = self._extract_user_id(event)
        if tg_user_id is None:
            return result

        session: AsyncSession | None = data.get("session")
        if session is None:
            return result

        try:
            async with session.begin_nested():
                await UserRepo.touch_activity(session, tg_user_id)
        except Exception:
            logger.warning(
                "Failed to touch activity for user %s",
                tg_user_id,
                exc_info=True,
            )

        return result

    @staticmethod
    def _extract_user_id(update: Update) -> int | None:
        """Extract the Telegram user ID from an Update."""
        if update.message and update.message.from_user:
            return update.message.from_user.id
        if update.callback_query and update.callback_query.from_user:
            return update.callback_query.from_user.id
        return None


# ---------------------------------------------------------------------------
# Timezone onboarding gate (spec D2 / FEAT-03)
# ---------------------------------------------------------------------------

# Onboarding messages shown to users who haven't set a timezone yet.
ONBOARDING_TEXT_A = (
    "Hi. Every time you eat, send me a 📸 pic of your meal (or drink). "
    "I'll guess the macros, calories, caffeine and ingredients to help you "
    "keep track of your diet."
)
ONBOARDING_TEXT_B = (
    "🌍 First I need to know your time zone so I can divide up your meals "
    "into days correctly. You can change it later."
)

# Callback data prefixes that the timezone flow uses — always allowed.
_TZ_CALLBACK_PREFIXES = ("tz_city:", "tz_offset:", "tz_city_menu", "tz_offset_menu")

# Commands that are allowed even without timezone.
_ALLOWED_COMMANDS = {"/start", "/help"}


class TimezoneGateMiddleware(BaseMiddleware):
    """Block user input until timezone is set (spec D2).

    Registered as an **update-level outer** middleware so it sees every
    incoming update *after* the DB session is available.

    **Allowed through without timezone:**
    - ``/start`` and ``/help`` commands (so the user can still interact)
    - All timezone selection callbacks (``tz_city:*``, ``tz_offset:*``, menus)

    **Intercepted when timezone is missing:**
    - Any other message (text, photo, command) → show onboarding + picker
    - Any non-timezone callback → answer with prompt to set timezone
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        # Determine the Telegram user ID from the update.
        tg_user_id = self._extract_user_id(event)
        if tg_user_id is None:
            # No user context (e.g. channel post) — let it through.
            return await handler(event, data)

        # Check if this update type is always allowed (before DB lookup).
        if self._is_always_allowed(event):
            return await handler(event, data)

        # Look up user timezone.  Session is already injected by DBSessionMiddleware.
        session: AsyncSession | None = data.get("session")
        if session is None:
            # Safety: if no session, let the handler deal with the error.
            return await handler(event, data)

        user = await UserRepo.get_or_create(session, tg_user_id)
        if user.tz_mode is not None:
            # Timezone is set — pass through.
            return await handler(event, data)

        # --- Timezone NOT set: intercept ---
        await self._send_onboarding(event)
        return None  # Do not call the downstream handler.

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_user_id(update: Update) -> int | None:
        """Extract the Telegram user ID from an Update."""
        if update.message and update.message.from_user:
            return update.message.from_user.id
        if update.callback_query and update.callback_query.from_user:
            return update.callback_query.from_user.id
        return None

    @staticmethod
    def _is_always_allowed(update: Update) -> bool:
        """Return True if this update should bypass the timezone gate."""
        # Allow /start and /help commands.
        # Match strictly: no case folding, no @bot suffix tolerance.
        # This mirrors aiogram's Command() defaults (ignore_case=False,
        # ignore_mention=False) so we don't accidentally let variants
        # like /START slip through to the catch-all meal handler.
        if update.message and update.message.text:
            text = update.message.text.strip()
            if text.startswith("/"):
                # Extract bare command: "/start payload" → "/start"
                cmd = text.split()[0]
                if cmd in _ALLOWED_COMMANDS:
                    return True

        # Allow timezone-related callbacks.
        if update.callback_query and update.callback_query.data:
            cb = update.callback_query.data
            if any(cb.startswith(prefix) for prefix in _TZ_CALLBACK_PREFIXES):
                return True

        return False

    @staticmethod
    async def _send_onboarding(update: Update) -> None:
        """Send the onboarding prompt to set timezone."""
        if update.message:
            await update.message.answer(ONBOARDING_TEXT_A)
            await update.message.answer(
                ONBOARDING_TEXT_B,
                reply_markup=timezone_city_keyboard(),
            )
        elif update.callback_query:
            # For non-timezone callbacks, answer the callback and prompt.
            await update.callback_query.answer(
                "Please set your timezone first.", show_alert=True
            )
            if update.callback_query.message:
                await update.callback_query.message.answer(  # type: ignore[union-attr]
                    ONBOARDING_TEXT_B,
                    reply_markup=timezone_city_keyboard(),
                )
