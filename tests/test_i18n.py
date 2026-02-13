"""Tests for the i18n module (Step 15).

Verifies:
- ``t(key, lang)`` returns correct EN and RU strings.
- Unknown language falls back to English.
- Unknown key returns the key itself.
- All EN keys have corresponding RU translations.
- ``supported_languages()`` returns correct list.
"""

from __future__ import annotations

import pytest

from app.i18n import DEFAULT_LANG, t, supported_languages
from app.i18n.locales.en import STRINGS as EN_STRINGS
from app.i18n.locales.ru import STRINGS as RU_STRINGS


# ---------------------------------------------------------------------------
# Basic t() behaviour
# ---------------------------------------------------------------------------


class TestTranslationHelper:
    """Test the t(key, lang) function."""

    def test_en_returns_english(self) -> None:
        """t(key, 'EN') returns the English string."""
        assert t("welcome_back", "EN") == EN_STRINGS["welcome_back"]

    def test_ru_returns_russian(self) -> None:
        """t(key, 'RU') returns the Russian string."""
        assert t("welcome_back", "RU") == RU_STRINGS["welcome_back"]

    def test_en_and_ru_differ(self) -> None:
        """EN and RU strings for the same key are different."""
        assert t("welcome_back", "EN") != t("welcome_back", "RU")

    def test_case_insensitive_lang(self) -> None:
        """Language code is case-insensitive."""
        assert t("welcome_back", "en") == EN_STRINGS["welcome_back"]
        assert t("welcome_back", "Ru") == RU_STRINGS["welcome_back"]
        assert t("welcome_back", "rU") == RU_STRINGS["welcome_back"]

    def test_none_lang_defaults_to_en(self) -> None:
        """None language falls back to English."""
        assert t("welcome_back", None) == EN_STRINGS["welcome_back"]

    def test_no_lang_defaults_to_en(self) -> None:
        """Omitted lang parameter falls back to English."""
        assert t("welcome_back") == EN_STRINGS["welcome_back"]

    def test_unknown_lang_falls_back_to_en(self) -> None:
        """Unknown language code falls back to English."""
        assert t("welcome_back", "FR") == EN_STRINGS["welcome_back"]
        assert t("welcome_back", "DE") == EN_STRINGS["welcome_back"]
        assert t("welcome_back", "ZZ") == EN_STRINGS["welcome_back"]

    def test_unknown_key_returns_key(self) -> None:
        """Unknown key returns the key string itself."""
        assert t("nonexistent_key_xyz", "EN") == "nonexistent_key_xyz"
        assert t("nonexistent_key_xyz", "RU") == "nonexistent_key_xyz"

    def test_unknown_key_unknown_lang_returns_key(self) -> None:
        """Unknown key + unknown language returns the key itself."""
        assert t("no_such_key", "FR") == "no_such_key"

    def test_empty_string_key_returns_empty(self) -> None:
        """Empty string key returns empty string (not found in any locale)."""
        assert t("", "EN") == ""


# ---------------------------------------------------------------------------
# Format string placeholders
# ---------------------------------------------------------------------------


class TestFormatStrings:
    """Test that format strings with placeholders work correctly."""

    def test_edit_window_expired_en(self) -> None:
        """EN edit window expired message accepts hours placeholder."""
        msg = t("msg_edit_window_expired", "EN").format(hours=48)
        assert "48" in msg

    def test_edit_window_expired_ru(self) -> None:
        """RU edit window expired message accepts hours placeholder."""
        msg = t("msg_edit_window_expired", "RU").format(hours=48)
        assert "48" in msg

    def test_delete_window_expired_format(self) -> None:
        """Delete window expired message accepts hours placeholder."""
        msg = t("msg_delete_window_expired", "EN").format(hours=24)
        assert "24" in msg

    def test_goal_set_confirmation_format(self) -> None:
        """Goal set confirmation accepts label placeholder."""
        msg = t("goal_set_confirmation", "EN").format(label="Maintenance")
        assert "Maintenance" in msg

    def test_tz_saved_format(self) -> None:
        """Timezone saved message accepts tz placeholder."""
        msg = t("tz_saved", "EN").format(tz="Europe/Moscow")
        assert "Europe/Moscow" in msg
        msg_ru = t("tz_saved", "RU").format(tz="Europe/Moscow")
        assert "Europe/Moscow" in msg_ru


# ---------------------------------------------------------------------------
# Locale completeness
# ---------------------------------------------------------------------------


class TestLocaleCompleteness:
    """Verify both locales have matching keys."""

    def test_all_en_keys_exist_in_ru(self) -> None:
        """Every EN key must have a corresponding RU translation."""
        missing = set(EN_STRINGS.keys()) - set(RU_STRINGS.keys())
        assert missing == set(), f"RU locale missing keys: {missing}"

    def test_all_ru_keys_exist_in_en(self) -> None:
        """No orphan RU keys — every RU key must exist in EN."""
        orphan = set(RU_STRINGS.keys()) - set(EN_STRINGS.keys())
        assert orphan == set(), f"RU locale has orphan keys not in EN: {orphan}"

    def test_no_empty_en_values(self) -> None:
        """No EN string should be empty."""
        empty = [k for k, v in EN_STRINGS.items() if not v]
        assert empty == [], f"EN locale has empty values for keys: {empty}"

    def test_no_empty_ru_values(self) -> None:
        """No RU string should be empty."""
        empty = [k for k, v in RU_STRINGS.items() if not v]
        assert empty == [], f"RU locale has empty values for keys: {empty}"

    def test_format_placeholders_match(self) -> None:
        """EN and RU format strings must have the same placeholders."""
        import re

        placeholder_re = re.compile(r"\{(\w+)\}")
        mismatched: list[str] = []
        for key in EN_STRINGS:
            en_placeholders = set(placeholder_re.findall(EN_STRINGS[key]))
            ru_val = RU_STRINGS.get(key, "")
            ru_placeholders = set(placeholder_re.findall(ru_val))
            if en_placeholders != ru_placeholders:
                mismatched.append(
                    f"{key}: EN={en_placeholders}, RU={ru_placeholders}"
                )
        assert mismatched == [], "Placeholder mismatch:\n" + "\n".join(mismatched)


# ---------------------------------------------------------------------------
# Supported languages helper
# ---------------------------------------------------------------------------


class TestSupportedLanguages:
    """Test supported_languages() helper."""

    def test_returns_en_and_ru(self) -> None:
        """Must include EN and RU."""
        langs = supported_languages()
        assert "EN" in langs
        assert "RU" in langs

    def test_returns_sorted(self) -> None:
        """List is sorted alphabetically."""
        langs = supported_languages()
        assert langs == sorted(langs)

    def test_default_lang_is_en(self) -> None:
        """Default language constant is EN."""
        assert DEFAULT_LANG == "EN"


# ---------------------------------------------------------------------------
# Key coverage: ensure all expected key groups exist
# ---------------------------------------------------------------------------


class TestKeyCoverage:
    """Verify that key groups are present in EN locale."""

    @pytest.mark.parametrize(
        "key",
        [
            "onboarding_a",
            "onboarding_b",
            "onboarding_tz_alert",
            "welcome_back",
            "help_text",
            "add_prompt",
            "msg_unrecognized",
            "msg_throttle",
            "msg_sanity_fail",
            "msg_edit_window_expired",
            "msg_delete_window_expired",
            "msg_processing_new",
            "msg_processing_edit",
            "meal_not_found",
            "edit_send_corrected",
            "already_saved",
            "deleted_label",
            "draft_expired",
            "fmt_saved_prefix",
            "fmt_draft_prefix",
            "fmt_calories",
            "fmt_macros",
            "fmt_protein",
            "fmt_carbs",
            "fmt_fat",
            "fmt_totals",
            "fmt_weight",
            "fmt_volume",
            "fmt_caffeine",
            "fmt_likely_ingredients",
            "fmt_today_stats_header",
            "fmt_weekly_stats_header",
            "fmt_4week_stats_header",
            "fmt_week_label",
            "fmt_no_meals",
            "kb_stats",
            "kb_goals",
            "kb_help",
            "kb_history",
            "kb_add_meal",
            "kb_save",
            "kb_edit",
            "kb_delete",
            "kb_today",
            "kb_weekly",
            "kb_4weeks",
            "kb_change_tz",
            "kb_choose_offset",
            "kb_choose_city",
            "goals_prompt",
            "goal_maintenance",
            "goal_deficit",
            "goal_bulk",
            "goal_set_confirmation",
            "tz_choose_city",
            "tz_choose_offset",
            "tz_saved",
            "stats_choose_period",
            "stub_feedback",
            "stub_subscription",
            "reminder_text",
            "nav_arrow",
            "edit_feedback_prompt",
            "edit_feedback_photo_warning",
            "edit_feedback_timeout",
            "edit_feedback_updated",
            "edit_feedback_replaced",
            "edit_feedback_ok",
            "edit_feedback_deleted",
            "kb_edit_ok",
            "kb_edit_delete",
            "fmt_unit_g",
            "fmt_unit_kcal",
        ],
    )
    def test_key_exists_in_en(self, key: str) -> None:
        """Each expected key exists in EN locale."""
        assert key in EN_STRINGS, f"Missing EN key: {key}"

    @pytest.mark.parametrize(
        "key",
        [
            "onboarding_a",
            "onboarding_b",
            "welcome_back",
            "help_text",
            "add_prompt",
            "msg_unrecognized",
            "msg_throttle",
            "msg_processing_new",
            "kb_stats",
            "kb_goals",
            "kb_help",
            "kb_history",
            "kb_add_meal",
            "goals_prompt",
            "tz_saved",
            "reminder_text",
            "edit_feedback_prompt",
            "edit_feedback_photo_warning",
            "edit_feedback_timeout",
            "edit_feedback_updated",
            "edit_feedback_replaced",
            "edit_feedback_ok",
            "edit_feedback_deleted",
            "kb_edit_ok",
            "kb_edit_delete",
        ],
    )
    def test_key_differs_en_ru(self, key: str) -> None:
        """Key has distinct EN and RU values (not just copied)."""
        assert EN_STRINGS[key] != RU_STRINGS[key], (
            f"EN and RU are identical for key '{key}' — likely not translated"
        )
