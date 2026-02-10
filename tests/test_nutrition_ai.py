"""Tests for app.services.nutrition_ai — OpenAI service (mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APITimeoutError

from app.services.nutrition_ai import (
    Ingredient,
    NutritionAIService,
    NutritionAnalysis,
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
