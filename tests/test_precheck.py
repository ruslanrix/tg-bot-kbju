"""Tests for app.services.precheck — pre-API input filtering."""

from __future__ import annotations

import pytest

from app.services.precheck import (
    REJECT_NOT_TEXT_OR_PHOTO,
    REJECT_PHOTO_TOO_LARGE,
    REJECT_VAGUE,
    REJECT_WATER,
    check_message_type,
    check_photo_size,
    check_text,
)

# ---------------------------------------------------------------------------
# §5.1 — message type gate
# ---------------------------------------------------------------------------


class TestMessageType:
    def test_text_passes(self):
        r = check_message_type(has_text=True, has_photo=False)
        assert r.passed

    def test_photo_passes(self):
        r = check_message_type(has_text=False, has_photo=True)
        assert r.passed

    def test_photo_with_caption_passes(self):
        r = check_message_type(has_text=True, has_photo=True)
        assert r.passed

    def test_sticker_rejected(self):
        r = check_message_type(has_text=False, has_photo=False)
        assert not r.passed
        assert r.reject_key == REJECT_NOT_TEXT_OR_PHOTO


# ---------------------------------------------------------------------------
# §5.2 — empty / junk text
# ---------------------------------------------------------------------------


class TestEmptyJunk:
    def test_empty_string(self):
        r = check_text("", has_photo=False)
        assert not r.passed

    def test_whitespace_only(self):
        r = check_text("   ", has_photo=False)
        assert not r.passed

    def test_only_emoji(self):
        r = check_text("🍕🍔🥗", has_photo=False)
        assert not r.passed
        assert r.reject_key == REJECT_NOT_TEXT_OR_PHOTO

    def test_only_punctuation(self):
        r = check_text("!!!???...", has_photo=False)
        assert not r.passed

    def test_chinese_food_passes(self):
        """Chinese food name should not be rejected as junk."""
        r = check_text("饺子", has_photo=False)
        assert r.passed

    def test_japanese_food_passes(self):
        r = check_text("ラーメン", has_photo=False)
        assert r.passed

    def test_arabic_food_passes(self):
        r = check_text("فلافل", has_photo=False)
        assert r.passed

    def test_korean_food_passes(self):
        r = check_text("김치", has_photo=False)
        assert r.passed

    def test_thai_food_passes(self):
        r = check_text("ผัดไทย", has_photo=False)
        assert r.passed


# ---------------------------------------------------------------------------
# §5.3 — water-only
# ---------------------------------------------------------------------------


class TestWater:
    @pytest.mark.parametrize("text", ["вода", "water", "стакан воды", "попил воды"])
    def test_water_rejected(self, text: str):
        r = check_text(text, has_photo=False)
        assert not r.passed
        assert r.reject_key == REJECT_WATER

    def test_water_case_insensitive(self):
        r = check_text("Вода", has_photo=False)
        assert not r.passed
        assert r.reject_key == REJECT_WATER

    def test_vodka_not_rejected(self):
        """'водка' must NOT be a false positive for 'вода'."""
        r = check_text("водка", has_photo=False)
        assert r.passed

    def test_water_with_lemon_not_rejected(self):
        """Compound phrase is not in the exact-match set."""
        r = check_text("вода с лимоном", has_photo=False)
        assert r.passed


# ---------------------------------------------------------------------------
# §5.4 — medicine
# ---------------------------------------------------------------------------


class TestMedicine:
    @pytest.mark.parametrize("text", ["лекарство", "таблетка", "ibuprofen", "paracetamol"])
    def test_medicine_rejected(self, text: str):
        r = check_text(text, has_photo=False)
        assert not r.passed
        assert r.reject_key == REJECT_NOT_TEXT_OR_PHOTO

    def test_medicine_in_sentence(self):
        r = check_text("выпил таблетка утром", has_photo=False)
        assert not r.passed

    def test_pizza_not_rejected(self):
        r = check_text("pizza", has_photo=False)
        assert r.passed


# ---------------------------------------------------------------------------
# §5.5 — vague text-only
# ---------------------------------------------------------------------------


class TestVague:
    @pytest.mark.parametrize("text", ["вкусняшка", "еда", "поел", "ням", "что-то"])
    def test_vague_text_rejected(self, text: str):
        r = check_text(text, has_photo=False)
        assert not r.passed
        assert r.reject_key == REJECT_VAGUE

    def test_vague_with_photo_passes(self):
        """Vague words with a photo should NOT be rejected (§5.5 applies only to text-only)."""
        r = check_text("еда", has_photo=True)
        assert r.passed

    def test_vague_with_digits_passes(self):
        """Vague word + number → pass (user provided quantity)."""
        r = check_text("еда 500г", has_photo=False)
        assert r.passed

    def test_real_short_food_passes(self):
        """Short but valid food names must not be rejected."""
        for food in ["pizza", "burger", "плов", "шаурма"]:
            r = check_text(food, has_photo=False)
            assert r.passed, f"{food!r} should pass"


# ---------------------------------------------------------------------------
# §5.6 — photo size
# ---------------------------------------------------------------------------


class TestPhotoSize:
    def test_within_limit(self):
        r = check_photo_size(1_000_000, max_bytes=5_000_000)
        assert r.passed

    def test_exactly_at_limit(self):
        r = check_photo_size(5_000_000, max_bytes=5_000_000)
        assert r.passed

    def test_over_limit(self):
        r = check_photo_size(10_000_000, max_bytes=5_000_000)
        assert not r.passed
        assert r.reject_key == REJECT_PHOTO_TOO_LARGE
