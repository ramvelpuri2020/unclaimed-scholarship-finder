"""Text cleanup shared by extraction, verification and persisted API models."""

from __future__ import annotations

import re
from typing import Any

_PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")


def strip_private_use(value: str) -> str:
    """Remove Unicode private-use glyphs that fonts or scraped pages leave behind."""

    return _PRIVATE_USE_RE.sub("", value)


def clean_value(value: Any) -> Any:
    """Recursively strip private-use glyphs from strings, lists and dictionaries."""

    if isinstance(value, str):
        return strip_private_use(value)
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(clean_value(item) for item in value)
    if isinstance(value, dict):
        return {key: clean_value(item) for key, item in value.items()}
    return value
