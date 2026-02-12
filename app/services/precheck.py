"""Pre-API filtering pipeline (spec §5).

Rejects obvious non-food inputs *before* calling OpenAI to save
budget and reduce latency.  The checks are deliberately conservative
— false rejects are worse than letting borderline messages through.

Reject messages are returned as i18n keys (``"precheck_*"``).
The caller resolves them via ``t(key, lang)`` for localization.
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
        reject_key: i18n key for the reject message (``None`` when passed).
    """

    passed: bool
    reject_key: str | None = None


# ---------------------------------------------------------------------------
# Reject i18n keys (spec §5.1–5.6)
# ---------------------------------------------------------------------------

REJECT_NOT_TEXT_OR_PHOTO = "precheck_not_text_or_photo"
REJECT_WATER = "precheck_water"
REJECT_VAGUE = "precheck_vague"
REJECT_PHOTO_TOO_LARGE = "precheck_photo_too_large"

# ---------------------------------------------------------------------------
# Keyword sets (lowercased, stripped)
# ---------------------------------------------------------------------------

_WATER_EXACT: set[str] = {"вода", "water", "стакан воды", "попил воды"}

_MEDICINE_KEYWORDS: set[str] = {"лекарство", "таблетка", "ibuprofen", "paracetamol"}

_VAGUE_WORDS: set[str] = {"вкусняшка", "еда", "поел", "ням", "что-то"}


def _has_alnum(text: str) -> bool:
    """Return True if *text* contains at least one Unicode letter or digit.

    Uses ``str.isalnum()`` which covers all scripts (Latin, Cyrillic,
    CJK, Arabic, etc.), unlike a Latin/Cyrillic-only regex.
    """
    return any(c.isalnum() for c in text)


# Regex: contains any digit.
_HAS_DIGIT = re.compile(r"\d")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_message_type(*, has_text: bool, has_photo: bool) -> PrecheckResult:
    """§5.1 — reject if the update is neither text nor photo."""
    if has_text or has_photo:
        return PrecheckResult(passed=True)
    return PrecheckResult(passed=False, reject_key=REJECT_NOT_TEXT_OR_PHOTO)


def check_text(text: str, *, has_photo: bool) -> PrecheckResult:
    """Run text-level checks §5.2–5.5 in order.

    Args:
        text: The message text (or caption for photos).
        has_photo: Whether the message contains a photo attachment.

    Returns:
        ``PrecheckResult`` — passed or rejected with an i18n key.
    """
    normalized = text.strip().lower()

    # §5.2 — empty / junk (only emoji/punctuation).
    if not normalized or not _has_alnum(normalized):
        return PrecheckResult(passed=False, reject_key=REJECT_NOT_TEXT_OR_PHOTO)

    # §5.3 — water-only exact match.
    if normalized in _WATER_EXACT:
        return PrecheckResult(passed=False, reject_key=REJECT_WATER)

    # §5.4 — medicine keywords.
    for kw in _MEDICINE_KEYWORDS:
        if kw in normalized:
            return PrecheckResult(passed=False, reject_key=REJECT_NOT_TEXT_OR_PHOTO)

    # §5.5 — vague text-only (no photo, no digits, matches curated list).
    if not has_photo and not _HAS_DIGIT.search(normalized) and normalized in _VAGUE_WORDS:
        return PrecheckResult(passed=False, reject_key=REJECT_VAGUE)

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
    return PrecheckResult(passed=False, reject_key=REJECT_PHOTO_TOO_LARGE)
