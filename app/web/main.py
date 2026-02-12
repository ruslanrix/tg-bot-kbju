"""FastAPI application: webhook endpoint, health check, task endpoints, lifecycle.

Supports two modes determined by ``PUBLIC_URL``:
- **Webhook** (production): ``PUBLIC_URL`` set — registers webhook with
  Telegram, receives updates via ``POST /webhook/{secret}``.
- **Polling** (local dev): ``PUBLIC_URL`` empty — starts aiogram polling
  in background, no ngrok/tunnel needed.

Database migrations run automatically on startup via Alembic.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bot.factory import create_bot, create_dispatcher
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.repos import MealRepo

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dp: Dispatcher | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_migrations() -> None:
    """Run ``alembic upgrade head`` via subprocess.

    Uses subprocess because ``alembic/env.py`` calls ``asyncio.run()``
    internally — invoking it from an already-running event loop would
    raise ``RuntimeError``.
    """
    logger.info("Running database migrations", extra={"event": "migrations_start"})
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(
            "Migration failed: %s",
            result.stderr,
            extra={"event": "migrations_failed"},
        )
        raise RuntimeError(f"Alembic migration failed:\n{result.stderr}")
    logger.info("Database migrations complete", extra={"event": "migrations_done"})


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle manager.

    1. Configure logging.
    2. Run database migrations (``alembic upgrade head``).
    3. Create bot + dispatcher.
    4. If ``PUBLIC_URL`` is set → webhook mode; otherwise → polling mode.
    """
    global _bot, _dp, _session_factory  # noqa: PLW0603

    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    # --- Auto-migrate ---
    _run_migrations()

    # --- Create DB session factory for task endpoints ---
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # --- Create bot + dispatcher ---
    _bot = create_bot(settings)
    _dp = create_dispatcher(settings)

    polling_task: asyncio.Task[None] | None = None

    if settings.use_webhook:
        # --- Webhook mode (production) ---
        webhook_url = f"{settings.PUBLIC_URL}/webhook/{settings.WEBHOOK_SECRET}"
        await _bot.set_webhook(webhook_url)
        logger.info(
            "Webhook mode started",
            extra={"event": "webhook_set", "public_url": settings.PUBLIC_URL},
        )
    else:
        # --- Polling mode (local dev) ---
        await _bot.delete_webhook(drop_pending_updates=True)
        polling_task = asyncio.create_task(
            _dp.start_polling(_bot, handle_signals=False),
        )
        # Give polling a moment to fail on invalid token / network errors
        await asyncio.sleep(1)
        if polling_task.done():
            polling_task.result()  # raises stored exception
        logger.info(
            "Polling mode started (no PUBLIC_URL set)",
            extra={"event": "polling_started"},
        )

    yield

    # --- Shutdown ---
    if polling_task is not None:
        await _dp.stop_polling()
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task
        logger.info("Polling stopped", extra={"event": "polling_stopped"})

    if _bot:
        if settings.use_webhook:
            await _bot.delete_webhook()
        await _bot.session.close()
        logger.info("Bot session closed", extra={"event": "shutdown"})


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


# ---------------------------------------------------------------------------
# Task endpoints (protected by TASKS_SECRET)
# ---------------------------------------------------------------------------


@app.post("/tasks/purge/{secret}")
async def task_purge(secret: str) -> dict[str, object]:
    """Permanently delete soft-deleted meals older than retention period.

    Protected by ``TASKS_SECRET``. Returns 403 if secret is wrong or empty.
    """
    settings = get_settings()
    if not settings.TASKS_SECRET or secret != settings.TASKS_SECRET:
        return Response(status_code=403)  # type: ignore[return-value]

    if _session_factory is None:
        return Response(status_code=503)  # type: ignore[return-value]

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.PURGE_DELETED_AFTER_DAYS)

    async with _session_factory() as session:
        count = await MealRepo.hard_delete_deleted_before(session, cutoff)
        await session.commit()

    logger.info(
        "Purge completed: %d rows deleted",
        count,
        extra={"event": "purge_done", "deleted_count": count},
    )
    return {"status": "ok", "deleted_count": count}
