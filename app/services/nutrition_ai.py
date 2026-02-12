"""OpenAI-powered nutrition analysis service (spec §6).

Sends text or photo to OpenAI and receives structured JSON with
nutrition estimates, likely ingredients, and an action decision
(save / reject_*).  All API errors are caught and mapped to
``reject_unrecognized``.
"""

from __future__ import annotations

import base64
import logging
from typing import Literal

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models (spec §6.1)
# ---------------------------------------------------------------------------

ActionType = Literal[
    "save",
    "reject_no_calories",
    "reject_not_food",
    "reject_insufficient_detail",
    "reject_unrecognized",
]


class Ingredient(BaseModel):
    """A single likely ingredient in the meal."""

    name: str
    amount: str
    calories_kcal: int = Field(ge=0)
    weight_g: int | None = Field(default=None, ge=0)
    volume_ml: int | None = Field(default=None, ge=0)


class NutritionAnalysis(BaseModel):
    """Structured response from OpenAI (spec §6.1).

    When ``action`` is ``"save"`` all nutrition fields are populated.
    For ``reject_*`` actions only ``user_message`` matters (except
    ``reject_unrecognized`` where the bot uses a fixed reply).

    All numeric nutrition fields enforce ``>= 0`` to prevent invalid
    data from reaching the database (e.g. on OpenAI model drift).
    """

    action: ActionType
    meal_name: str | None = None
    calories_kcal: int | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    weight_g: int | None = Field(default=None, ge=0)
    volume_ml: int | None = Field(default=None, ge=0)
    caffeine_mg: int | None = Field(default=None, ge=0)
    likely_ingredients: list[Ingredient] = Field(default_factory=list)
    user_message: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Sanity check limits (spec D5/FEAT-07)
# ---------------------------------------------------------------------------

# Maximum reasonable single-meal values — anything above is rejected as absurd.
MAX_CALORIES_KCAL = 5000
MAX_PROTEIN_G = 500.0
MAX_CARBS_G = 800.0
MAX_FAT_G = 400.0
MAX_WEIGHT_G = 10_000
MAX_VOLUME_ML = 5_000
MAX_CAFFEINE_MG = 2_000


def sanity_check(analysis: NutritionAnalysis) -> str | None:
    """Validate that a ``save`` analysis has reasonable values.

    Returns ``None`` when values are plausible, or an error string
    describing the first absurd value found.  Reject actions are
    always considered valid (no nutrition data to check).
    """
    if analysis.action != "save":
        return None

    checks: list[tuple[str, float | int | None, float | int]] = [
        ("Calories", analysis.calories_kcal, MAX_CALORIES_KCAL),
        ("Protein", analysis.protein_g, MAX_PROTEIN_G),
        ("Carbs", analysis.carbs_g, MAX_CARBS_G),
        ("Fat", analysis.fat_g, MAX_FAT_G),
        ("Weight", analysis.weight_g, MAX_WEIGHT_G),
        ("Volume", analysis.volume_ml, MAX_VOLUME_ML),
        ("Caffeine", analysis.caffeine_mg, MAX_CAFFEINE_MG),
    ]

    for label, value, limit in checks:
        if value is not None and value > limit:
            return f"{label} value ({value}) exceeds maximum ({limit})."

    return None


# ---------------------------------------------------------------------------
# System prompt (spec §6.2)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a nutrition analysis assistant. Analyze the food described or shown \
and return a structured JSON response.

Rules:
1. If the input is clearly food or drink, estimate nutrition and set action="save".
2. If the input has no calories (e.g. water, supplements), set action="reject_no_calories" \
with a brief user_message explaining why.
3. If the input is not food at all, set action="reject_not_food" with user_message.
4. If the food description lacks sufficient detail for a reasonable estimate, \
set action="reject_insufficient_detail" with user_message.
5. If you cannot recognize what was sent, set action="reject_unrecognized" \
(no user_message needed — the bot uses a fixed reply).
6. Prefer rejection over guessing when uncertain.
7. All numeric values must be non-negative. If values seem absurd, reject.
8. If the user provides explicit numbers (kcal, macros, weight, volume), \
trust and pass them through — do NOT overwrite. Still generate meal_name \
and likely_ingredients.
9. Always generate likely_ingredients when action="save" — this is required.
10. confidence should be 0.0–1.0 reflecting your certainty.
11. For each ingredient in likely_ingredients, provide weight_g (estimated grams) \
and/or volume_ml (estimated millilitres) when applicable. Estimate serving sizes \
even when the user does not specify them. Solid foods get weight_g, liquids get \
volume_ml, items like soup may have both.
12. Always provide total weight_g for solid meals and volume_ml for drinks/soups at \
the top level.
"""

# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NutritionAIService:
    """Facade for OpenAI nutrition analysis.

    Args:
        client: An ``AsyncOpenAI`` instance.
        model: Model name (e.g. ``"gpt-4o-mini"``).
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str = "gpt-4o-mini",
        timeout: float = 30.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout = timeout

    async def analyze_text(self, text: str) -> NutritionAnalysis:
        """Analyze a text description of a meal.

        Args:
            text: User-provided food description.

        Returns:
            Parsed ``NutritionAnalysis``.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        return await self._call(messages)

    async def analyze_photo(
        self,
        photo_bytes: bytes,
        caption: str | None = None,
    ) -> NutritionAnalysis:
        """Analyze a photo of a meal (with optional caption).

        Args:
            photo_bytes: Raw image bytes (JPEG/PNG).
            caption: Optional text caption from the user.

        Returns:
            Parsed ``NutritionAnalysis``.
        """
        b64 = base64.b64encode(photo_bytes).decode()
        content: list[dict] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            },
        ]
        if caption:
            content.insert(0, {"type": "text", "text": caption})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        return await self._call(messages)

    async def _call(self, messages: list[dict]) -> NutritionAnalysis:
        """Send request to OpenAI and parse the structured response.

        Any API error or malformed response is mapped to
        ``reject_unrecognized`` so the caller never sees exceptions.
        """
        try:
            response = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=messages,
                response_format=NutritionAnalysis,
                timeout=self._timeout,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                logger.warning("OpenAI returned empty parsed response")
                return NutritionAnalysis(action="reject_unrecognized")
            return parsed

        except OpenAIError as exc:
            logger.error("OpenAI API error: %s", exc, extra={"event": "openai_error"})
            return NutritionAnalysis(action="reject_unrecognized")
        except Exception as exc:
            logger.error(
                "Unexpected error during OpenAI call: %s",
                exc,
                extra={"event": "openai_error"},
            )
            return NutritionAnalysis(action="reject_unrecognized")
