"""Technical page-health checks that run before any Gemini extraction call."""

from __future__ import annotations

from .reader import Page

BOT_WALL_TERMS = (
    "client challenge",
    "access denied",
    "just a moment",
    "enable javascript",
    "captcha",
    "sign in to continue",
    "log in to continue",
    "login required",
    "login wall",
)
MIN_TEXT_CHARS = 500


def prefilter_reason(page: Page) -> str | None:
    """Return only technical unreadability reasons; relevance belongs to Gemini."""

    text = page.text.strip()
    if len(text) < MIN_TEXT_CHARS:
        return "prefilter_short_text"

    haystack = f"{page.title}\n{text}".lower()
    if any(term in haystack for term in BOT_WALL_TERMS):
        return "prefilter_bot_wall"
    return None
