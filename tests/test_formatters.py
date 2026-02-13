"""Tests for app.bot.formatters (FIX-02, FIX-03, Step 07).

Verifies:
- Ingredient lines show only grams + kcal (localized units).
- No Totals/Итого block in output.
- Caffeine appears after calories, before macros (only when present).
- EN/RU locale formatting.
"""

from __future__ import annotations

import datetime as _dt
import re

from app.bot.formatters import format_meal_draft, format_meal_saved, format_weekly_stats
from app.i18n import t as tr
from app.services.nutrition_ai import Ingredient, NutritionAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis(**overrides: object) -> NutritionAnalysis:
    defaults = {
        "action": "save",
        "meal_name": "Test Meal",
        "calories_kcal": 400,
        "protein_g": 25.0,
        "carbs_g": 40.0,
        "fat_g": 15.0,
        "likely_ingredients": [],
    }
    defaults.update(overrides)
    return NutritionAnalysis(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FIX-03: No Totals block; caffeine repositioned
# ---------------------------------------------------------------------------


class TestNoTotalsBlock:
    """Totals/Итого section must never appear."""

    def test_no_totals_with_weight(self) -> None:
        text = format_meal_saved(_make_analysis(weight_g=300))
        assert "Totals" not in text

    def test_no_totals_with_volume(self) -> None:
        text = format_meal_saved(_make_analysis(volume_ml=250))
        assert "Totals" not in text

    def test_no_totals_with_caffeine(self) -> None:
        text = format_meal_saved(_make_analysis(caffeine_mg=95))
        assert "Totals" not in text

    def test_no_totals_with_all(self) -> None:
        text = format_meal_saved(
            _make_analysis(weight_g=350, volume_ml=200, caffeine_mg=80)
        )
        assert "Totals" not in text
        assert "Итого" not in text

    def test_no_totals_draft(self) -> None:
        text = format_meal_draft(_make_analysis(weight_g=200))
        assert "Totals" not in text

    def test_no_weight_volume_in_body(self) -> None:
        """Weight/Volume labels must not appear in meal body."""
        text = format_meal_saved(
            _make_analysis(weight_g=350, volume_ml=200)
        )
        assert "Weight:" not in text
        assert "Volume:" not in text
        assert "Вес:" not in text
        assert "Объём:" not in text


class TestCaffeinePlacement:
    """Caffeine appears after calories, before macros."""

    def test_caffeine_shown_when_present(self) -> None:
        text = format_meal_saved(_make_analysis(caffeine_mg=95))
        assert "Caffeine: 95mg" in text

    def test_caffeine_omitted_when_none(self) -> None:
        text = format_meal_saved(_make_analysis(caffeine_mg=None))
        assert "Caffeine" not in text
        assert "Кофеин" not in text

    def test_caffeine_after_calories_before_macros(self) -> None:
        text = format_meal_saved(_make_analysis(caffeine_mg=95))
        cal_pos = text.index("400kcal")
        caff_pos = text.index("Caffeine")
        macros_pos = text.index("Macros")
        assert cal_pos < caff_pos < macros_pos

    def test_caffeine_ru_locale(self) -> None:
        text = format_meal_saved(_make_analysis(caffeine_mg=95), lang="RU")
        assert "Кофеин: 95mg" in text


# ---------------------------------------------------------------------------
# FIX-02: Ingredient line format — grams + kcal only
# ---------------------------------------------------------------------------


class TestIngredientFormat:
    """Ingredient lines show: • Name (Xg, Ykcal)."""

    def test_with_weight(self) -> None:
        ing = Ingredient(name="rice", amount="1 cup", calories_kcal=200, weight_g=180)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "• rice (180g, 200kcal)" in text

    def test_volume_converted_to_grams(self) -> None:
        """volume_ml is converted to grams at 1:1."""
        ing = Ingredient(name="milk", amount="1 glass", calories_kcal=90, volume_ml=250)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "• milk (250g, 90kcal)" in text

    def test_weight_preferred_over_volume(self) -> None:
        ing = Ingredient(
            name="soup", amount="1 bowl", calories_kcal=150,
            weight_g=350, volume_ml=300,
        )
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "• soup (350g, 150kcal)" in text

    def test_no_weight_no_volume_omits_grams(self) -> None:
        """When weight and volume are unknown, grams are omitted entirely."""
        ing = Ingredient(name="chicken", amount="100g", calories_kcal=165)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "• chicken (165kcal)" in text
        # Ingredient line must not contain fabricated "0g"
        lines = text.split("\n")
        ing_lines = [l for l in lines if l.startswith("•") and "chicken" in l]
        for line in ing_lines:
            assert "0g" not in line

    def test_rounding(self) -> None:
        ing = Ingredient(name="rice", amount="1 cup", calories_kcal=200, weight_g=180.7)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "• rice (181g, 200kcal)" in text

    def test_no_ml_in_output(self) -> None:
        """Output must never contain 'ml' in ingredient lines."""
        ing = Ingredient(name="milk", amount="1 glass", calories_kcal=90, volume_ml=250)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        # Find ingredient section and check no ml
        lines = text.split("\n")
        ing_lines = [l for l in lines if l.startswith("•") and "milk" in l]
        for line in ing_lines:
            assert "ml" not in line

    def test_no_cup_in_output(self) -> None:
        """Raw amount descriptors like 'cup' must not appear."""
        ing = Ingredient(name="rice", amount="1 cup", calories_kcal=200, weight_g=180)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        lines = text.split("\n")
        ing_lines = [l for l in lines if l.startswith("•") and "rice" in l]
        for line in ing_lines:
            assert "cup" not in line


class TestIngredientFormatRU:
    """RU locale uses г/ккал."""

    def test_ru_units(self) -> None:
        ing = Ingredient(name="рис", amount="1 стакан", calories_kcal=200, weight_g=180)
        text = format_meal_saved(
            _make_analysis(likely_ingredients=[ing]), lang="RU"
        )
        assert "• рис (180г, 200ккал)" in text

    def test_ru_volume_converted(self) -> None:
        ing = Ingredient(name="молоко", amount="1 стакан", calories_kcal=90, volume_ml=250)
        text = format_meal_saved(
            _make_analysis(likely_ingredients=[ing]), lang="RU"
        )
        assert "• молоко (250г, 90ккал)" in text


# ---------------------------------------------------------------------------
# Basic formatting checks
# ---------------------------------------------------------------------------


class TestBasicFormatting:
    def test_saved_header(self) -> None:
        text = format_meal_saved(_make_analysis())
        assert text.startswith("✅ Saved. You added: Test Meal")

    def test_draft_header(self) -> None:
        text = format_meal_draft(_make_analysis())
        assert text.startswith("🍽 Draft: Test Meal")

    def test_macros_present(self) -> None:
        text = format_meal_saved(_make_analysis())
        assert "Protein: 25.0g" in text
        assert "Carbs: 40.0g" in text
        assert "Fat: 15.0g" in text

    def test_calories_present(self) -> None:
        text = format_meal_saved(_make_analysis())
        assert "400kcal" in text

    def test_macros_ru(self) -> None:
        text = format_meal_saved(_make_analysis(), lang="RU")
        assert "Белки: 25.0г" in text
        assert "Углеводы: 40.0г" in text
        assert "Жиры: 15.0г" in text

    def test_calories_ru(self) -> None:
        text = format_meal_saved(_make_analysis(), lang="RU")
        assert "400ккал" in text


# ---------------------------------------------------------------------------
# Weekly stats formatting (v1.1.3 Step 04)
# ---------------------------------------------------------------------------


def _make_day_stats(d: _dt.date, cal: int = 0, p: float = 0, c: float = 0, f: float = 0):
    """Build a DayStats dict for testing."""
    return {"date": d, "calories_kcal": cal, "protein_g": p, "carbs_g": c, "fat_g": f}


class TestWeeklyStatsFormat:
    """Weekly stats output must match exact locale-aware template."""

    _base = _dt.date(2024, 6, 19)  # Wednesday
    _days = [
        _make_day_stats(_dt.date(2024, 6, 19), 1850, 120.5, 200.3, 65.7),
        _make_day_stats(_dt.date(2024, 6, 18), 1600, 100.0, 180.0, 55.0),
        _make_day_stats(_dt.date(2024, 6, 17), 2000, 140.0, 220.0, 70.0),
        _make_day_stats(_dt.date(2024, 6, 16), 0, 0.0, 0.0, 0.0),
        _make_day_stats(_dt.date(2024, 6, 15), 1500, 90.0, 170.0, 50.0),
        _make_day_stats(_dt.date(2024, 6, 14), 1700, 110.0, 190.0, 60.0),
        _make_day_stats(_dt.date(2024, 6, 13), 1900, 130.0, 210.0, 68.0),
    ]

    def test_en_exact_template(self) -> None:
        text = format_weekly_stats(self._days, "EN")
        assert "Wed 19.06: 1850 kcal | P/C/F 120/200/65" in text

    def test_ru_weekday_abbreviation(self) -> None:
        text = format_weekly_stats(self._days, "RU")
        assert "Ср 19.06:" in text  # Среда

    def test_ru_kcal_unit(self) -> None:
        text = format_weekly_stats(self._days, "RU")
        assert "1850 ккал" in text

    def test_ru_macro_label(self) -> None:
        text = format_weekly_stats(self._days, "RU")
        assert "Б/У/Ж 120/200/65" in text

    def test_date_format_dd_mm(self) -> None:
        """Dates should be DD.MM, not English strftime."""
        text = format_weekly_stats(self._days, "EN")
        assert "19.06" in text
        assert "Jun" not in text
        assert "Wed Jun" not in text

    def test_integer_only_values(self) -> None:
        """No decimal points in numeric stats values."""
        text = format_weekly_stats(self._days, "EN")
        # 120.5 should display as 120, not 120.5
        assert "120.5" not in text
        # No trailing .0 on numbers (but DD.MM dates are fine)
        assert "100.0" not in text
        assert "55.0" not in text

    def test_zero_day_shown(self) -> None:
        """Zero-meal day should be shown, not omitted."""
        text = format_weekly_stats(self._days, "EN")
        assert "Sun 16.06: 0 kcal | P/C/F 0/0/0" in text

    def test_slash_macro_format(self) -> None:
        """Old P:{x}g C:{y}g F:{z}g format must not appear."""
        text = format_weekly_stats(self._days, "EN")
        assert "P:" not in text
        assert "C:" not in text
        assert "F:" not in text

    def test_exactly_7_data_lines(self) -> None:
        text = format_weekly_stats(self._days, "EN")
        # Pattern: DOW DD.MM: ...
        data_lines = re.findall(r"^\w+ \d{2}\.\d{2}:", text, re.MULTILINE)
        assert len(data_lines) == 7

    def test_header_present(self) -> None:
        text = format_weekly_stats(self._days, "EN")
        assert tr("fmt_weekly_stats_header", "EN") in text

    def test_ru_header_present(self) -> None:
        text = format_weekly_stats(self._days, "RU")
        assert tr("fmt_weekly_stats_header", "RU") in text
