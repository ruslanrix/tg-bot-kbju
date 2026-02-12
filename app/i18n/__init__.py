"""Internationalization module (FEAT-13).

Provides the ``t(key, lang)`` translation helper that looks up locale
strings from ``app/i18n/locales/{lang}.py`` dictionaries.

Fallback behaviour:
- Unknown *lang* → falls back to English.
- Unknown *key* → returns the key itself (safe for debugging).

Usage::

    from app.i18n import t

    text = t("welcome_back", "RU")      # → "С возвращением! ..."
    text = t("welcome_back", "EN")      # → "Welcome back! ..."
    text = t("welcome_back", "FR")      # → EN fallback
    text = t("nonexistent_key", "EN")   # → "nonexistent_key"
"""

from __future__ import annotations

from app.i18n.locales.en import STRINGS as EN_STRINGS
from app.i18n.locales.ru import STRINGS as RU_STRINGS

# Registry of supported locales.  The key is the canonical upper-case
# language code stored in ``users.language``.
_LOCALES: dict[str, dict[str, str]] = {
    "EN": EN_STRINGS,
    "RU": RU_STRINGS,
}

# Default / fallback language.
DEFAULT_LANG = "EN"


def t(key: str, lang: str | None = None) -> str:
    """Return the localised string for *key* in *lang*.

    Parameters
    ----------
    key:
        Locale key defined in ``locales/en.py`` / ``locales/ru.py``.
    lang:
        Two-letter language code (case-insensitive).  ``None`` or an
        unknown language falls back to English.

    Returns
    -------
    str
        The translated string, or the *key* itself if not found in any
        locale (prevents runtime errors, easy to spot in UI).
    """
    code = (lang or DEFAULT_LANG).upper()

    # Try requested locale first.
    locale = _LOCALES.get(code)
    if locale is not None:
        value = locale.get(key)
        if value is not None:
            return value

    # Fallback to English.
    if code != DEFAULT_LANG:
        value = EN_STRINGS.get(key)
        if value is not None:
            return value

    # Key not found in any locale — return key itself.
    return key


def supported_languages() -> list[str]:
    """Return sorted list of supported language codes."""
    return sorted(_LOCALES.keys())
