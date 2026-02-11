"""FastAPI application: webhook endpoint, health check, lifecycle.

Spec §10: POST /webhook/{secret} receives Telegram updates,
GET /health returns ``{"status": "ok"}``.  On startup the bot
webhook is registered; on shutdown it is removed.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Request, Response

from app.bot.factory import create_bot, create_dispatcher
from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dp: Dispatcher | None = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle manager.

    On startup: configure logging, create bot + dispatcher, set webhook.
    On shutdown: delete webhook, close bot session.
    """
    global _bot, _dp  # noqa: PLW0603

    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    _bot = create_bot(settings)
    _dp = create_dispatcher(settings)

    webhook_url = f"{settings.PUBLIC_URL}/webhook/{settings.WEBHOOK_SECRET}"
    await _bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info("Webhook set to %s", webhook_url, extra={"event": "webhook_set"})

    yield

    if _bot:
        await _bot.delete_webhook()
        await _bot.session.close()
        logger.info("Webhook deleted, bot session closed", extra={"event": "shutdown"})


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request) -> Response:
    """Receive Telegram webhook updates.

    Validates the secret path parameter against ``WEBHOOK_SECRET``.
    """
    settings = get_settings()
    if secret != settings.WEBHOOK_SECRET:
        return Response(status_code=403)

    if _bot is None or _dp is None:
        return Response(status_code=503)

    data = await request.json()
    update = Update.model_validate(data, context={"bot": _bot})
    await _dp.feed_update(bot=_bot, update=update)

    return Response(status_code=200)
