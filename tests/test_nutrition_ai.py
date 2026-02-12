"""Tests for app.services.nutrition_ai — OpenAI service (mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APITimeoutError

from app.services.nutrition_ai import (
    MAX_CAFFEINE_MG,
    MAX_CALORIES_KCAL,
    MAX_CARBS_G,
    MAX_FAT_G,
    MAX_PROTEIN_G,
    MAX_VOLUME_ML,
    MAX_WEIGHT_G,
    Ingredient,
    NutritionAIService,
    NutritionAnalysis,
    sanity_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(mock_client: AsyncMock | None = None) -> NutritionAIService:
    """Create a service with a mock OpenAI client."""
    client = mock_client or AsyncMock()
    return NutritionAIService(client=client, model="gpt-4o-mini", timeout=10.0)


def _mock_parse_response(analysis: NutritionAnalysis) -> AsyncMock:
    """Build a mock client whose beta.chat.completions.parse returns *analysis*."""
    client = AsyncMock()
    choice = MagicMock()
    choice.message.parsed = analysis
    response = MagicMock()
    response.choices = [choice]
    client.beta.chat.completions.parse.return_value = response
    return client


# ---------------------------------------------------------------------------
# action: save
# ---------------------------------------------------------------------------


class TestSaveAction:
    async def test_text_returns_analysis(self):
        expected = NutritionAnalysis(
            action="save",
            meal_name="Chicken breast",
            calories_kcal=250,
            protein_g=40.0,
            carbs_g=0.0,
            fat_g=8.0,
            weight_g=200,
            likely_ingredients=[
                Ingredient(name="chicken breast", amount="200g", calories_kcal=250),
            ],
            confidence=0.9,
        )
        client = _mock_parse_response(expected)
        svc = _make_service(client)

        result = await svc.analyze_text("chicken breast 200g")
        assert result.action == "save"
        assert result.calories_kcal == 250
        assert result.protein_g == 40.0
        assert len(result.likely_ingredients) == 1

    async def test_photo_returns_analysis(self):
        expected = NutritionAnalysis(
            action="save",
            meal_name="Pizza slice",
            calories_kcal=300,
            protein_g=12.0,
            carbs_g=35.0,
            fat_g=14.0,
            likely_ingredients=[
                Ingredient(name="pizza dough", amount="100g", calories_kcal=150),
                Ingredient(name="cheese", amount="30g", calories_kcal=100),
            ],
            confidence=0.8,
        )
        client = _mock_parse_response(expected)
        svc = _make_service(client)

        result = await svc.analyze_photo(b"\xff\xd8fake_jpeg", caption="pizza")
        assert result.action == "save"
        assert result.meal_name == "Pizza slice"

    async def test_photo_without_caption(self):
        expected = NutritionAnalysis(
            action="save",
            meal_name="Food",
            calories_kcal=100,
            protein_g=5.0,
            carbs_g=10.0,
            fat_g=3.0,
            confidence=0.5,
        )
        client = _mock_parse_response(expected)
        svc = _make_service(client)

        result = await svc.analyze_photo(b"\xff\xd8fake_jpeg")
        assert result.action == "save"


# ---------------------------------------------------------------------------
# reject_* actions
# ---------------------------------------------------------------------------


class TestRejectActions:
    @pytest.mark.parametrize(
        "action",
        [
            "reject_no_calories",
            "reject_not_food",
            "reject_insufficient_detail",
            "reject_unrecognized",
        ],
    )
    async def test_reject_actions_returned(self, action: str):
        expected = NutritionAnalysis(
            action=action,
            user_message="Some reason" if action != "reject_unrecognized" else None,
        )
        client = _mock_parse_response(expected)
        svc = _make_service(client)

        result = await svc.analyze_text("something")
        assert result.action == action


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_api_timeout_returns_reject_unrecognized(self):
        client = AsyncMock()
        client.beta.chat.completions.parse.side_effect = APITimeoutError(request=MagicMock())
        svc = _make_service(client)

        result = await svc.analyze_text("chicken")
        assert result.action == "reject_unrecognized"

    async def test_generic_openai_error_returns_reject_unrecognized(self):
        from openai import APIConnectionError

        client = AsyncMock()
        client.beta.chat.completions.parse.side_effect = APIConnectionError(request=MagicMock())
        svc = _make_service(client)

        result = await svc.analyze_text("chicken")
        assert result.action == "reject_unrecognized"

    async def test_unexpected_exception_returns_reject_unrecognized(self):
        client = AsyncMock()
        client.beta.chat.completions.parse.side_effect = ValueError("unexpected")
        svc = _make_service(client)

        result = await svc.analyze_text("chicken")
        assert result.action == "reject_unrecognized"

    async def test_none_parsed_returns_reject_unrecognized(self):
        """OpenAI returns a response but parsed is None (e.g. refusal)."""
        client = AsyncMock()
        choice = MagicMock()
        choice.message.parsed = None
        response = MagicMock()
        response.choices = [choice]
        client.beta.chat.completions.parse.return_value = response
        svc = _make_service(client)

        result = await svc.analyze_text("chicken")
        assert result.action == "reject_unrecognized"


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------


class TestNutritionAnalysisModel:
    def test_defaults(self):
        """Minimal valid instance with just action."""
        m = NutritionAnalysis(action="reject_unrecognized")
        assert m.action == "reject_unrecognized"
        assert m.likely_ingredients == []
        assert m.confidence == 0.0

    def test_full_save(self):
        m = NutritionAnalysis(
            action="save",
            meal_name="Rice",
            calories_kcal=200,
            protein_g=4.0,
            carbs_g=44.0,
            fat_g=0.5,
            weight_g=150,
            likely_ingredients=[
                Ingredient(name="rice", amount="150g", calories_kcal=200),
            ],
            confidence=0.95,
        )
        assert m.meal_name == "Rice"
        assert len(m.likely_ingredients) == 1

    def test_invalid_action_rejected(self):
        with pytest.raises(Exception):
            NutritionAnalysis(action="invalid_action")

    def test_negative_calories_rejected(self):
        with pytest.raises(Exception):
            NutritionAnalysis(action="save", calories_kcal=-100)

    def test_negative_protein_rejected(self):
        with pytest.raises(Exception):
            NutritionAnalysis(action="save", protein_g=-5.0)

    def test_negative_fat_rejected(self):
        with pytest.raises(Exception):
            NutritionAnalysis(action="save", fat_g=-1.0)

    def test_negative_carbs_rejected(self):
        with pytest.raises(Exception):
            NutritionAnalysis(action="save", carbs_g=-10.0)

    def test_negative_ingredient_calories_rejected(self):
        with pytest.raises(Exception):
            Ingredient(name="test", amount="100g", calories_kcal=-50)

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(Exception):
            NutritionAnalysis(action="save", confidence=1.5)

    def test_none_values_still_valid(self):
        """None values should still be accepted (for reject actions)."""
        m = NutritionAnalysis(action="reject_not_food")
        assert m.calories_kcal is None
        assert m.protein_g is None

    def test_zero_values_valid(self):
        """Zero is a valid non-negative value."""
        m = NutritionAnalysis(
            action="save",
            calories_kcal=0,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
        )
        assert m.calories_kcal == 0


# ---------------------------------------------------------------------------
# Ingredient per-item weight/volume (Step 08, D5/FEAT-07)
# ---------------------------------------------------------------------------


class TestIngredientWeightVolume:
    def test_ingredient_with_weight(self):
        ing = Ingredient(name="rice", amount="150g", calories_kcal=200, weight_g=150)
        assert ing.weight_g == 150
        assert ing.volume_ml is None

    def test_ingredient_with_volume(self):
        ing = Ingredient(name="milk", amount="200ml", calories_kcal=90, volume_ml=200)
        assert ing.volume_ml == 200
        assert ing.weight_g is None

    def test_ingredient_with_both(self):
        """Soup ingredient may have both weight and volume."""
        ing = Ingredient(
            name="soup", amount="300ml", calories_kcal=120,
            weight_g=320, volume_ml=300,
        )
        assert ing.weight_g == 320
        assert ing.volume_ml == 300

    def test_ingredient_defaults_none(self):
        """Without explicit weight/volume, defaults to None (backward compat)."""
        ing = Ingredient(name="chicken", amount="100g", calories_kcal=165)
        assert ing.weight_g is None
        assert ing.volume_ml is None

    def test_ingredient_negative_weight_rejected(self):
        with pytest.raises(Exception):
            Ingredient(name="x", amount="x", calories_kcal=0, weight_g=-1)

    def test_ingredient_negative_volume_rejected(self):
        with pytest.raises(Exception):
            Ingredient(name="x", amount="x", calories_kcal=0, volume_ml=-5)

    def test_ingredient_zero_weight_valid(self):
        ing = Ingredient(name="spice", amount="pinch", calories_kcal=0, weight_g=0)
        assert ing.weight_g == 0

    def test_ingredient_serialization_includes_fields(self):
        """model_dump() includes weight_g and volume_ml for JSONB storage."""
        ing = Ingredient(
            name="rice", amount="150g", calories_kcal=200,
            weight_g=150, volume_ml=None,
        )
        d = ing.model_dump()
        assert "weight_g" in d
        assert "volume_ml" in d
        assert d["weight_g"] == 150
        assert d["volume_ml"] is None


# ---------------------------------------------------------------------------
# Sanity checks (Step 08, D5/FEAT-07)
# ---------------------------------------------------------------------------


class TestSanityCheck:
    def test_normal_values_pass(self):
        a = NutritionAnalysis(
            action="save", calories_kcal=500, protein_g=30.0,
            carbs_g=50.0, fat_g=20.0, weight_g=300,
        )
        assert sanity_check(a) is None

    def test_reject_actions_always_pass(self):
        a = NutritionAnalysis(action="reject_not_food")
        assert sanity_check(a) is None

    def test_absurd_calories_rejected(self):
        a = NutritionAnalysis(action="save", calories_kcal=MAX_CALORIES_KCAL + 1)
        result = sanity_check(a)
        assert result is not None
        assert "Calories" in result

    def test_absurd_protein_rejected(self):
        a = NutritionAnalysis(action="save", protein_g=MAX_PROTEIN_G + 1)
        result = sanity_check(a)
        assert result is not None
        assert "Protein" in result

    def test_absurd_carbs_rejected(self):
        a = NutritionAnalysis(action="save", carbs_g=MAX_CARBS_G + 1)
        result = sanity_check(a)
        assert result is not None
        assert "Carbs" in result

    def test_absurd_fat_rejected(self):
        a = NutritionAnalysis(action="save", fat_g=MAX_FAT_G + 1)
        result = sanity_check(a)
        assert result is not None
        assert "Fat" in result

    def test_absurd_weight_rejected(self):
        a = NutritionAnalysis(action="save", weight_g=MAX_WEIGHT_G + 1)
        result = sanity_check(a)
        assert result is not None
        assert "Weight" in result

    def test_absurd_volume_rejected(self):
        a = NutritionAnalysis(action="save", volume_ml=MAX_VOLUME_ML + 1)
        result = sanity_check(a)
        assert result is not None
        assert "Volume" in result

    def test_absurd_caffeine_rejected(self):
        a = NutritionAnalysis(action="save", caffeine_mg=MAX_CAFFEINE_MG + 1)
        result = sanity_check(a)
        assert result is not None
        assert "Caffeine" in result

    def test_exactly_at_limit_passes(self):
        a = NutritionAnalysis(
            action="save",
            calories_kcal=MAX_CALORIES_KCAL,
            protein_g=MAX_PROTEIN_G,
            carbs_g=MAX_CARBS_G,
            fat_g=MAX_FAT_G,
            weight_g=MAX_WEIGHT_G,
            volume_ml=MAX_VOLUME_ML,
            caffeine_mg=MAX_CAFFEINE_MG,
        )
        assert sanity_check(a) is None

    def test_none_values_pass(self):
        """None fields should not trigger sanity failure."""
        a = NutritionAnalysis(action="save", calories_kcal=200)
        assert sanity_check(a) is None
