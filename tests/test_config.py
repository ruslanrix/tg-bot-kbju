"""Tests for app.core.config.Settings validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_REQUIRED = {
    "BOT_TOKEN": "test-token",
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "OPENAI_API_KEY": "sk-test",
}


def _make(**overrides: object) -> Settings:
    env = {**_REQUIRED, **overrides}
    return Settings(**env)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
class TestDefaults:
    def test_edit_window_default(self) -> None:
        s = _make()
        assert s.EDIT_WINDOW_HOURS == 48

    def test_delete_window_default(self) -> None:
        s = _make()
        assert s.DELETE_WINDOW_HOURS == 48

    def test_purge_deleted_default(self) -> None:
        s = _make()
        assert s.PURGE_DELETED_AFTER_DAYS == 30

    def test_tasks_secret_default_empty(self) -> None:
        s = _make()
        assert s.TASKS_SECRET == ""

    def test_reminder_inactivity_default(self) -> None:
        s = _make()
        assert s.REMINDER_INACTIVITY_HOURS == 6

    def test_reminder_cooldown_default(self) -> None:
        s = _make()
        assert s.REMINDER_COOLDOWN_HOURS == 6

    def test_admin_ids_default_empty(self) -> None:
        s = _make()
        assert s.ADMIN_IDS == ""
        assert s.admin_ids_list == []


# ---------------------------------------------------------------------------
# Positive-value validation
# ---------------------------------------------------------------------------
class TestPositiveValidation:
    @pytest.mark.parametrize(
        "field",
        [
            "EDIT_WINDOW_HOURS",
            "DELETE_WINDOW_HOURS",
            "PURGE_DELETED_AFTER_DAYS",
            "REMINDER_INACTIVITY_HOURS",
            "REMINDER_COOLDOWN_HOURS",
        ],
    )
    def test_zero_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError, match="must be positive"):
            _make(**{field: 0})

    @pytest.mark.parametrize(
        "field",
        [
            "EDIT_WINDOW_HOURS",
            "DELETE_WINDOW_HOURS",
            "PURGE_DELETED_AFTER_DAYS",
            "REMINDER_INACTIVITY_HOURS",
            "REMINDER_COOLDOWN_HOURS",
        ],
    )
    def test_negative_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError, match="must be positive"):
            _make(**{field: -1})

    @pytest.mark.parametrize(
        "field",
        [
            "EDIT_WINDOW_HOURS",
            "DELETE_WINDOW_HOURS",
            "PURGE_DELETED_AFTER_DAYS",
            "REMINDER_INACTIVITY_HOURS",
            "REMINDER_COOLDOWN_HOURS",
        ],
    )
    def test_positive_accepted(self, field: str) -> None:
        s = _make(**{field: 1})
        assert getattr(s, field) == 1


# ---------------------------------------------------------------------------
# TASKS_SECRET validation
# ---------------------------------------------------------------------------
class TestTasksSecret:
    def test_empty_allowed(self) -> None:
        s = _make(TASKS_SECRET="")
        assert s.TASKS_SECRET == ""

    def test_valid_secret(self) -> None:
        s = _make(TASKS_SECRET="abcdefgh")
        assert s.TASKS_SECRET == "abcdefgh"

    def test_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least 8 characters"):
            _make(TASKS_SECRET="short")


# ---------------------------------------------------------------------------
# ADMIN_IDS parsing
# ---------------------------------------------------------------------------
class TestAdminIds:
    def test_empty_string(self) -> None:
        s = _make(ADMIN_IDS="")
        assert s.admin_ids_list == []

    def test_single_id(self) -> None:
        s = _make(ADMIN_IDS="123456789")
        assert s.admin_ids_list == [123456789]

    def test_multiple_ids(self) -> None:
        s = _make(ADMIN_IDS="111,222,333")
        assert s.admin_ids_list == [111, 222, 333]

    def test_spaces_stripped(self) -> None:
        s = _make(ADMIN_IDS=" 111 , 222 , 333 ")
        assert s.admin_ids_list == [111, 222, 333]

    def test_trailing_comma_ignored(self) -> None:
        s = _make(ADMIN_IDS="111,222,")
        assert s.admin_ids_list == [111, 222]

    def test_invalid_string_rejected(self) -> None:
        with pytest.raises(ValidationError, match="comma-separated list of integers"):
            _make(ADMIN_IDS="not_a_number")

    def test_raw_string_stored(self) -> None:
        s = _make(ADMIN_IDS="42,99")
        assert s.ADMIN_IDS == "42,99"

    def test_env_var_csv_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify CSV format works when loaded from environment variables."""
        monkeypatch.setenv("BOT_TOKEN", "test-token")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ADMIN_IDS", "111,222,333")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.admin_ids_list == [111, 222, 333]
