"""/version command handler (FEAT-14/D11).

Returns the current application version read from ``pyproject.toml``.
Available to all users, bypasses timezone gate.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.version import get_version

router = Router(name="version")


@router.message(Command("version"))
async def cmd_version(message: Message) -> None:
    """Handle /version — reply with the current app version."""
    version = get_version()
    await message.reply(f"🤖 KBJU Bot v{version}")
