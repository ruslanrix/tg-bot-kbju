"""Tests for app.services.rate_limit — rate limiter + concurrency guard."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from app.services.rate_limit import ConcurrencyGuard, RateLimiter


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_allows_up_to_max(self):
        rl = RateLimiter(max_per_minute=3)
        assert rl.check(1) is True
        assert rl.check(1) is True
        assert rl.check(1) is True

    def test_rejects_over_max(self):
        rl = RateLimiter(max_per_minute=3)
        for _ in range(3):
            rl.check(1)
        assert rl.check(1) is False

    def test_different_users_independent(self):
        rl = RateLimiter(max_per_minute=2)
        assert rl.check(1) is True
        assert rl.check(1) is True
        assert rl.check(1) is False  # user 1 limited
        assert rl.check(2) is True  # user 2 still ok

    def test_window_expires(self):
        rl = RateLimiter(max_per_minute=2)

        # Fill window at "time 0"
        with patch.object(time, "monotonic", return_value=100.0):
            assert rl.check(1) is True
            assert rl.check(1) is True
            assert rl.check(1) is False

        # 61 seconds later — window expired
        with patch.object(time, "monotonic", return_value=161.0):
            assert rl.check(1) is True

    def test_default_limit_is_6(self):
        rl = RateLimiter()
        for _ in range(6):
            assert rl.check(1) is True
        assert rl.check(1) is False


# ---------------------------------------------------------------------------
# ConcurrencyGuard
# ---------------------------------------------------------------------------


class TestConcurrencyGuard:
    async def test_first_acquire_succeeds(self):
        guard = ConcurrencyGuard()
        assert await guard.acquire(1) is True
        await guard.release(1)

    async def test_second_acquire_fails(self):
        guard = ConcurrencyGuard()
        assert await guard.acquire(1) is True
        assert await guard.acquire(1) is False
        await guard.release(1)

    async def test_release_allows_reacquire(self):
        guard = ConcurrencyGuard()
        assert await guard.acquire(1) is True
        await guard.release(1)
        assert await guard.acquire(1) is True
        await guard.release(1)

    async def test_different_users_independent(self):
        guard = ConcurrencyGuard()
        assert await guard.acquire(1) is True
        assert await guard.acquire(2) is True
        await guard.release(1)
        await guard.release(2)

    async def test_context_manager_acquires_and_releases(self):
        guard = ConcurrencyGuard()
        async with guard(1) as ctx:
            assert ctx.acquired is True
            # While inside, second acquire fails
            assert await guard.acquire(1) is False
        # After exit, acquire succeeds again
        assert await guard.acquire(1) is True
        await guard.release(1)

    async def test_context_manager_not_acquired(self):
        guard = ConcurrencyGuard()
        await guard.acquire(1)  # hold the slot
        async with guard(1) as ctx:
            assert ctx.acquired is False
        # Original still held — release it
        await guard.release(1)

    async def test_concurrent_tasks(self):
        guard = ConcurrencyGuard()
        results: list[bool] = []

        async def worker():
            async with guard(1) as ctx:
                results.append(ctx.acquired)
                if ctx.acquired:
                    await asyncio.sleep(0.05)

        await asyncio.gather(worker(), worker())
        assert results.count(True) == 1
        assert results.count(False) == 1
