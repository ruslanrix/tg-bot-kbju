"""Aiogram outer middlewares for DB session and logging context.

``DBSessionMiddleware`` injects an ``AsyncSession`` into handler data
(key ``"session"``), committing on success and rolling back on error.

``LoggingMiddleware`` sets logging contextvars from the incoming update
so structured log lines automatically include ``tg_user_id``,
``chat_id``, ``message_id``.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
