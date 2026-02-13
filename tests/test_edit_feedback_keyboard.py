"""Tests for edit_feedback_keyboard builder (Step 08, PR #35 review).

Verifies:
- Button texts match i18n keys for EN and RU.
- callback_data uses correct format: edit_ok:<meal_id> / edit_delete:<meal_id>.
- Keyboard has exactly one row with two buttons.
"""

from __future__ import annotations

import pytest

from app.bot.keyboards import edit_feedback_keyboard
from app.i18n import t


SAMPLE_MEAL_ID = "abc-123-def"


class TestEditFeedbackKeyboard:
    """Unit tests for edit_feedback_keyboard()."""

    def test_returns_inline_keyboard(self) -> None:
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID)
        assert kb.inline_keyboard is not None

    def test_single_row_two_buttons(self) -> None:
        """Keyboard has exactly 1 row with 2 buttons."""
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID)
        assert len(kb.inline_keyboard) == 1
        assert len(kb.inline_keyboard[0]) == 2

    # ---- EN locale ----

    def test_en_ok_button_text(self) -> None:
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="EN")
        ok_btn = kb.inline_keyboard[0][0]
        assert ok_btn.text == t("kb_edit_ok", "EN")

    def test_en_delete_button_text(self) -> None:
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="EN")
        del_btn = kb.inline_keyboard[0][1]
        assert del_btn.text == t("kb_edit_delete", "EN")

    # ---- RU locale ----

    def test_ru_ok_button_text(self) -> None:
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="RU")
        ok_btn = kb.inline_keyboard[0][0]
        assert ok_btn.text == t("kb_edit_ok", "RU")

    def test_ru_delete_button_text(self) -> None:
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="RU")
        del_btn = kb.inline_keyboard[0][1]
        assert del_btn.text == t("kb_edit_delete", "RU")

    # ---- EN and RU texts differ ----

    def test_ok_text_differs_en_ru(self) -> None:
        kb_en = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="EN")
        kb_ru = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="RU")
        assert kb_en.inline_keyboard[0][0].text != kb_ru.inline_keyboard[0][0].text

    def test_delete_text_differs_en_ru(self) -> None:
        kb_en = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="EN")
        kb_ru = edit_feedback_keyboard(SAMPLE_MEAL_ID, lang="RU")
        assert kb_en.inline_keyboard[0][1].text != kb_ru.inline_keyboard[0][1].text

    # ---- callback_data format ----

    def test_ok_callback_data(self) -> None:
        """OK button callback_data = edit_ok:<meal_id>."""
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID)
        ok_btn = kb.inline_keyboard[0][0]
        assert ok_btn.callback_data == f"edit_ok:{SAMPLE_MEAL_ID}"

    def test_delete_callback_data(self) -> None:
        """Delete button callback_data = edit_delete:<meal_id>."""
        kb = edit_feedback_keyboard(SAMPLE_MEAL_ID)
        del_btn = kb.inline_keyboard[0][1]
        assert del_btn.callback_data == f"edit_delete:{SAMPLE_MEAL_ID}"

    @pytest.mark.parametrize("meal_id", ["uuid-1", "meal_42", "x"])
    def test_callback_data_with_various_ids(self, meal_id: str) -> None:
        """callback_data embeds the provided meal_id regardless of format."""
        kb = edit_feedback_keyboard(meal_id)
        assert kb.inline_keyboard[0][0].callback_data == f"edit_ok:{meal_id}"
        assert kb.inline_keyboard[0][1].callback_data == f"edit_delete:{meal_id}"
