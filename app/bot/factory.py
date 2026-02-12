"""Bot and dispatcher factory.

Creates and wires together all aiogram components:
- Bot instance
- Dispatcher with all routers
- Middlewares (DB session, logging, timezone gate)
- Service singletons (rate limiter, concurrency guard, OpenAI)
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import admin, goals, history, meal, start, stats, stubs, timezone
from app.bot.middlewares import (
    ActivityMiddleware,
    DBSessionMiddleware,
    LoggingMiddleware,
    TimezoneGateMiddleware,
)
from app.core.config import Settings
from app.services.nutrition_ai import NutritionAIService
from app.services.rate_limit import ConcurrencyGuard, RateLimiter


def create_bot(settings: Settings) -> Bot:
    """Create a configured ``Bot`` instance.

    Args:
        settings: Application settings with BOT_TOKEN.

    Returns:
        An aiogram ``Bot``.
    """
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    """Create and wire the ``Dispatcher`` with all routers and middlewares.

    Args:
        settings: Application settings.

    Returns:
        A fully-configured aiogram ``Dispatcher``.
    """
    dp = Dispatcher(storage=MemoryStorage())

    # --- DB session middleware ---
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    dp.update.outer_middleware(DBSessionMiddleware(session_factory))

    # --- Logging middleware ---
    dp.update.outer_middleware(LoggingMiddleware())

    # --- Activity tracking middleware (FEAT-11) ---
    # Must be after DBSessionMiddleware (needs session).
    dp.update.outer_middleware(ActivityMiddleware())

    # --- Timezone onboarding gate (spec D2) ---
    # Must be registered AFTER DBSessionMiddleware (needs session in data).
    dp.update.outer_middleware(TimezoneGateMiddleware())

    # --- Wire service singletons into meal handler module ---
    meal.rate_limiter = RateLimiter(max_per_minute=settings.RATE_LIMIT_PER_MINUTE)
    meal.concurrency_guard = ConcurrencyGuard()
    meal.max_photo_bytes = settings.MAX_PHOTO_BYTES
    meal.edit_window_hours = settings.EDIT_WINDOW_HOURS
    meal.delete_window_hours = settings.DELETE_WINDOW_HOURS

    openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    meal.ai_service = NutritionAIService(
        client=openai_client,
        model=settings.OPENAI_MODEL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )

    # --- Wire admin handler settings ---
    admin.admin_ids = settings.admin_ids_list

    # --- Register routers (order matters for catch-all) ---
    # Commands and specific handlers first
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(goals.router)
    dp.include_router(timezone.router)
    dp.include_router(stats.router)
    dp.include_router(history.router)
    dp.include_router(stubs.router)
    # Meal router last — it has catch-all text/photo handlers
    dp.include_router(meal.router)

    return dp
