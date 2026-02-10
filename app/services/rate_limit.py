"""Per-user rate limiting and concurrency guard (spec §5.7).

Both primitives are **in-memory only**.  In a multi-instance deployment
they must be replaced with a shared store (e.g. Redis).  For a single
Railway container the current approach is sufficient.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class RateLimiter:
    """Sliding-window rate limiter keyed by ``tg_user_id``.

    Uses a simple list of timestamps per user.  Old entries outside the
    window are lazily pruned on every ``check()`` call.

    Args:
        max_per_minute: Maximum allowed requests within a 60-second window.
    """

    def __init__(self, max_per_minute: int = 6) -> None:
        self._max = max_per_minute
        self._windows: dict[int, list[float]] = defaultdict(list)

    def check(self, tg_user_id: int) -> bool:
        """Record a request and return ``True`` if within the limit.

        Returns:
            ``True`` — request is allowed; ``False`` — rate-limited.
        """
        now = time.monotonic()
        window = self._windows[tg_user_id]

        # Prune timestamps older than 60 seconds.
        cutoff = now - 60.0
        self._windows[tg_user_id] = window = [t for t in window if t > cutoff]

        if len(window) >= self._max:
            return False

        window.append(now)
        return True


class ConcurrencyGuard:
    """Per-user concurrency limiter (max 1 in-flight OpenAI call).

    Usage::

        async with guard(tg_user_id) as acquired:
            if not acquired:
                await message.reply("Too many requests …")
                return
            # … do OpenAI call …
    """

    def __init__(self) -> None:
        self._active: set[int] = set()
        self._lock = asyncio.Lock()

    async def acquire(self, tg_user_id: int) -> bool:
        """Try to acquire a slot for *tg_user_id*.

        Returns:
            ``True`` if the slot was acquired, ``False`` if another
            request is already in-flight for this user.
        """
        async with self._lock:
            if tg_user_id in self._active:
                return False
            self._active.add(tg_user_id)
            return True

    async def release(self, tg_user_id: int) -> None:
        """Release the slot for *tg_user_id*."""
        async with self._lock:
            self._active.discard(tg_user_id)

    def __call__(self, tg_user_id: int) -> _ConcurrencyContext:
        """Return an async context manager for *tg_user_id*."""
        return _ConcurrencyContext(self, tg_user_id)


class _ConcurrencyContext:
    """Async context manager returned by ``ConcurrencyGuard(user_id)``."""

    def __init__(self, guard: ConcurrencyGuard, tg_user_id: int) -> None:
        self._guard = guard
        self._uid = tg_user_id
        self.acquired = False

    async def __aenter__(self) -> _ConcurrencyContext:
        self.acquired = await self._guard.acquire(self._uid)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.acquired:
            await self._guard.release(self._uid)
