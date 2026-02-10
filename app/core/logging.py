"""Structured JSON logging for the application.

Provides a custom JSON formatter that outputs one JSON object per line
to stdout.  Extra fields (``tg_user_id``, ``chat_id``, ``event``, etc.)
are merged into each log record automatically.

Usage::

    from app.core.logging import setup_logging
    setup_logging("INFO")
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge well-known extra fields if present.
        for key in (
            "tg_user_id",
            "chat_id",
            "message_id",
            "update_id",
            "event",
            "request_id",
            "trace_id",
            "latency_ms",
            "model",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        # Include exception info when available.
        if record.exc_info and record.exc_info[1] is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the root logger to emit JSON lines to stdout.

    Args:
        log_level: Minimum log level name (e.g. ``"INFO"``, ``"DEBUG"``).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level.upper())

    # Silence noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
