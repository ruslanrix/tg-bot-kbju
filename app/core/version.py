"""Single-source version helper (FEAT-14/D11).

Reads the application version from ``pyproject.toml`` so that
future bumps require updating only one place.
"""

from __future__ import annotations

import functools
from pathlib import Path

_PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"


@functools.cache
def get_version() -> str:
    """Return the project version string from *pyproject.toml*.

    The result is cached for the lifetime of the process so the file
    is read at most once.

    Returns:
        Version string, e.g. ``"1.1.0"``.

    Raises:
        RuntimeError: If ``pyproject.toml`` is missing or has no version field.
    """
    if not _PYPROJECT_PATH.exists():
        raise RuntimeError(f"pyproject.toml not found at {_PYPROJECT_PATH}")

    for line in _PYPROJECT_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version"):
            # Parse: version = "1.1.0"
            _, _, value = stripped.partition("=")
            return value.strip().strip('"').strip("'")

    raise RuntimeError("version field not found in pyproject.toml")
