"""Logging setup: stderr plus a rotating file log with secret redaction.

Every handler on the root logger gets a redaction filter, so an API key, an
email address or a phone number can never reach ``backend/data/logs/backend.log``
even if a caller passes one to ``logger.info``.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR: Path = Path(__file__).resolve().parents[1] / "data" / "logs"
LOG_FILE: Path = LOG_DIR / "backend.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
REDACTED = "[redacted]"

_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)\b(?:sk|pk|tf|key|tok)_[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._\-+/=]{12,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\b\s*[=:]\s*\S+"),
    re.compile(r"\b[a-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{48,}\b"),
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def _redact_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 10 <= len(digits) <= 15:
        return REDACTED
    return match.group(0)


def redact_text(text: str, *, max_chars: int | None = None) -> str:
    """Return ``text`` with API keys, emails, phones and long tokens masked."""

    if not text:
        return text
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    redacted = _EMAIL.sub(REDACTED, redacted)
    redacted = _PHONE.sub(_redact_phone, redacted)
    if max_chars is not None:
        redacted = redacted[:max_chars]
    return redacted


class RedactionFilter(logging.Filter):
    """Filter that redacts the rendered message before it is written."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never let logging break a hunt
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Add the rotating file handler and the redaction filter to the root logger."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    redaction = RedactionFilter()
    has_file_handler = any(
        isinstance(handler, RotatingFileHandler) for handler in root.handlers
    )
    if not has_file_handler:
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler.setLevel(level)
        root.addHandler(handler)
    for existing in root.handlers:
        if redaction not in existing.filters:
            existing.addFilter(redaction)
    if root.level > level:
        root.setLevel(level)
