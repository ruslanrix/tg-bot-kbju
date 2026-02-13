"""Tests for /version command and version helper (Step 19, FEAT-14/D11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.version import get_version


# ---------------------------------------------------------------------------
# Version helper
# ---------------------------------------------------------------------------


class TestGetVersion:
    """Verify get_version reads from pyproject.toml."""

    def setup_method(self):
        """Clear the functools.cache between tests."""
        get_version.cache_clear()

    def test_returns_version_string(self):
        version = get_version()
        assert version == "1.1.3"

    def test_version_is_semver(self):
        version = get_version()
        parts = version.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_result_is_cached(self):
        v1 = get_version()
        v2 = get_version()
        assert v1 is v2  # Same object — cached

    def test_missing_pyproject_raises(self, tmp_path):
        """RuntimeError when pyproject.toml doesn't exist."""
        with patch("app.core.version._PYPROJECT_PATH", tmp_path / "missing.toml"):
            get_version.cache_clear()
            with pytest.raises(RuntimeError, match="not found"):
                get_version()

    def test_no_version_field_raises(self, tmp_path):
        """RuntimeError when pyproject.toml has no version field."""
        fake = tmp_path / "pyproject.toml"
        fake.write_text("[project]\nname = 'test'\n")
        with patch("app.core.version._PYPROJECT_PATH", fake):
            get_version.cache_clear()
            with pytest.raises(RuntimeError, match="version field not found"):
                get_version()


# ---------------------------------------------------------------------------
# /version handler
# ---------------------------------------------------------------------------


class TestVersionHandler:
    """Verify /version command replies with version string."""

    @pytest.mark.asyncio
    async def test_cmd_version_replies(self):
        from app.bot.handlers.version import cmd_version

        message = AsyncMock()
        message.reply = AsyncMock()

        await cmd_version(message)

        message.reply.assert_called_once()
        reply_text = message.reply.call_args.args[0]
        assert "1.1.3" in reply_text
        assert "KBJU Bot" in reply_text

    @pytest.mark.asyncio
    async def test_version_bypasses_timezone_gate(self):
        """Ensure /version is in the timezone gate bypass list."""
        from app.bot.middlewares import _ALLOWED_COMMANDS

        assert "/version" in _ALLOWED_COMMANDS
