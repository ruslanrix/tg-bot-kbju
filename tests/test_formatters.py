"""Tests for app.bot.formatters (Step 08, D5/FEAT-07).

Verifies:
- Weight/volume/caffeine totals shown when present.
- Per-ingredient weight/volume shown in ingredient lines.
- Backward compat: no totals section when all fields are None.
"""

from __future__ import annotations

from app.bot.formatters import format_meal_draft, format_meal_saved
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
# Total weight / volume / caffeine
# ---------------------------------------------------------------------------


class TestTotalsSection:
    def test_weight_shown(self) -> None:
        text = format_meal_saved(_make_analysis(weight_g=300))
        assert "Weight: 300g" in text
        assert "Totals" in text

    def test_volume_shown(self) -> None:
        text = format_meal_saved(_make_analysis(volume_ml=250))
        assert "Volume: 250ml" in text

    def test_caffeine_shown(self) -> None:
        text = format_meal_saved(_make_analysis(caffeine_mg=95))
        assert "Caffeine: 95mg" in text

    def test_all_totals_shown(self) -> None:
        text = format_meal_saved(
            _make_analysis(weight_g=350, volume_ml=200, caffeine_mg=80)
        )
        assert "Weight: 350g" in text
        assert "Volume: 200ml" in text
        assert "Caffeine: 80mg" in text

    def test_no_totals_when_all_none(self) -> None:
        """When weight/volume/caffeine are all None, Totals section is omitted."""
        text = format_meal_saved(
            _make_analysis(weight_g=None, volume_ml=None, caffeine_mg=None)
        )
        assert "Totals" not in text

    def test_draft_also_shows_totals(self) -> None:
        text = format_meal_draft(_make_analysis(weight_g=200))
        assert "Weight: 200g" in text
        assert "Totals" in text


# ---------------------------------------------------------------------------
# Per-ingredient weight / volume
# ---------------------------------------------------------------------------


class TestIngredientFormatting:
    def test_ingredient_with_weight(self) -> None:
        ing = Ingredient(name="rice", amount="1 cup", calories_kcal=200, weight_g=180)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "rice (1 cup, 200kcal, 180g)" in text

    def test_ingredient_with_volume(self) -> None:
        ing = Ingredient(name="milk", amount="1 glass", calories_kcal=90, volume_ml=250)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "milk (1 glass, 90kcal, 250ml)" in text

    def test_ingredient_with_both(self) -> None:
        ing = Ingredient(
            name="soup", amount="1 bowl", calories_kcal=150,
            weight_g=350, volume_ml=300,
        )
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "soup (1 bowl, 150kcal, 350g, 300ml)" in text

    def test_ingredient_without_weight_volume(self) -> None:
        """Backward compat: no weight/volume in ingredient line."""
        ing = Ingredient(name="chicken", amount="100g", calories_kcal=165)
        text = format_meal_saved(_make_analysis(likely_ingredients=[ing]))
        assert "chicken (100g, 165kcal)" in text
        # No trailing "g" or "ml" beyond the amount
        assert "chicken (100g, 165kcal)" in text


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
