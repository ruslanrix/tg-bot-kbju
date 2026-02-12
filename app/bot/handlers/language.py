"""/language command handler (FEAT-13).

Allows users to select their preferred UI language (EN/RU).
The selection is persisted in ``users.language`` and used by the
``t()`` helper to pick the correct locale.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import language_keyboard, main_keyboard
from app.db.repos import UserRepo

router = Router(name="language")

_LANG_LABELS: dict[str, str] = {
    "EN": "🇬🇧 English",
    "RU": "🇷🇺 Русский",
}


@router.message(Command("language"))
async def cmd_language(message: Message) -> None:
    """Handle /language — show language picker.

    Prompt is bilingual by design (shown before language is known).
    """
    await message.answer(
        "Choose your language / Выберите язык:",
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data.startswith("lang:"))
async def on_language_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    """Handle language selection callback."""
    if callback.data is None or callback.from_user is None:
        return

    lang = callback.data.split(":", 1)[1].upper()
    if lang not in _LANG_LABELS:
        await callback.answer("Unknown language.", show_alert=True)
        return

    user = await UserRepo.get_or_create(session, callback.from_user.id)
    await UserRepo.update_language(session, user.id, lang)

    label = _LANG_LABELS[lang]
    await callback.message.edit_text(f"Language set to {label} ✅")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "👇", reply_markup=main_keyboard(lang)
    )
    await callback.answer()
