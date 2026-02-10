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
    calories_kcal: int


class NutritionAnalysis(BaseModel):
    """Structured response from OpenAI (spec §6.1).

    When ``action`` is ``"save"`` all nutrition fields are populated.
    For ``reject_*`` actions only ``user_message`` matters (except
    ``reject_unrecognized`` where the bot uses a fixed reply).
    """

    action: ActionType
    meal_name: str | None = None
    calories_kcal: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    weight_g: int | None = None
    volume_ml: int | None = None
    caffeine_mg: int | None = None
    likely_ingredients: list[Ingredient] = Field(default_factory=list)
    user_message: str | None = None
    confidence: float = 0.0


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
