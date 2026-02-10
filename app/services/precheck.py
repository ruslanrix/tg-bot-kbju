"""Pre-API filtering pipeline (spec §5).

Rejects obvious non-food inputs *before* calling OpenAI to save
budget and reduce latency.  The checks are deliberately conservative
— false rejects are worse than letting borderline messages through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrecheckResult:
    """Outcome of the pre-API filter pipeline.

    Attributes:
        passed: ``True`` when the message should proceed to OpenAI.
        reject_message: Human-readable reply when ``passed`` is False.
    """

    passed: bool
    reject_message: str | None = None


# ---------------------------------------------------------------------------
# Reject messages (spec §5.1–5.6)
# ---------------------------------------------------------------------------

MSG_NOT_TEXT_OR_PHOTO = "Please ✏️ write a food or drink or send me a 📸 photo."
MSG_WATER = (
    "I can't analyse that because it seems to just say 'вода', "
    "which means 'water'. Water doesn't contain calories or macros. 😀"
)
MSG_VAGUE = (
    "I can't analyse that because the text is not in English and "
    "lacks sufficient detail about the food item to make an estimation 😀"
)
MSG_PHOTO_TOO_LARGE = "The photo is too large. Please resend a clearer or smaller photo 📸"

# ---------------------------------------------------------------------------
# Keyword sets (lowercased, stripped)
# ---------------------------------------------------------------------------

_WATER_EXACT: set[str] = {"вода", "water", "стакан воды", "попил воды"}

_MEDICINE_KEYWORDS: set[str] = {"лекарство", "таблетка", "ibuprofen", "paracetamol"}

_VAGUE_WORDS: set[str] = {"вкусняшка", "еда", "поел", "ням", "что-то"}

# Regex: at least one letter or digit (not purely emoji/punctuation/whitespace).
_HAS_ALNUM = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]")

# Regex: contains any digit.
_HAS_DIGIT = re.compile(r"\d")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_message_type(*, has_text: bool, has_photo: bool) -> PrecheckResult:
    """§5.1 — reject if the update is neither text nor photo."""
    if has_text or has_photo:
        return PrecheckResult(passed=True)
    return PrecheckResult(passed=False, reject_message=MSG_NOT_TEXT_OR_PHOTO)


def check_text(text: str, *, has_photo: bool) -> PrecheckResult:
    """Run text-level checks §5.2–5.5 in order.

    Args:
        text: The message text (or caption for photos).
        has_photo: Whether the message contains a photo attachment.

    Returns:
        ``PrecheckResult`` — passed or rejected with a message.
    """
    normalized = text.strip().lower()

    # §5.2 — empty / junk (only emoji/punctuation).
    if not normalized or not _HAS_ALNUM.search(normalized):
        return PrecheckResult(passed=False, reject_message=MSG_NOT_TEXT_OR_PHOTO)

    # §5.3 — water-only exact match.
    if normalized in _WATER_EXACT:
        return PrecheckResult(passed=False, reject_message=MSG_WATER)

    # §5.4 — medicine keywords.
    for kw in _MEDICINE_KEYWORDS:
        if kw in normalized:
            return PrecheckResult(passed=False, reject_message=MSG_NOT_TEXT_OR_PHOTO)

    # §5.5 — vague text-only (no photo, no digits, matches curated list).
    if not has_photo and not _HAS_DIGIT.search(normalized) and normalized in _VAGUE_WORDS:
        return PrecheckResult(passed=False, reject_message=MSG_VAGUE)

    return PrecheckResult(passed=True)


def check_photo_size(file_size_bytes: int, max_bytes: int) -> PrecheckResult:
    """§5.6 — reject photos exceeding *max_bytes*.

    Args:
        file_size_bytes: ``PhotoSize.file_size`` reported by Telegram.
        max_bytes: Upper limit from ``Settings.MAX_PHOTO_BYTES``.

    Returns:
        ``PrecheckResult``.
    """
    if file_size_bytes <= max_bytes:
        return PrecheckResult(passed=True)
    return PrecheckResult(passed=False, reject_message=MSG_PHOTO_TOO_LARGE)
