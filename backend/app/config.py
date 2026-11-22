"""Environment configuration for the Unclaimed backend.

Every value is read once at import time. A missing API key raises
``ConfigError`` with the exact variable name so uvicorn fails loudly instead of
starting a service that cannot do any work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv()

REQUIRED_VARIABLES = ("TINYFISH_API_KEY", "GEMINI_API_KEY")


class ConfigError(RuntimeError):
    """Raised when the environment is not usable."""


@dataclass(frozen=True)
class Settings:
    """Validated runtime settings."""

    tinyfish_api_key: str
    gemini_api_key: str
    gemini_model: str
    cors_origins: tuple[str, ...]
    stop_at_results: int
    search_concurrency: int
    fetch_concurrency: int
    fetch_batch: int
    extract_concurrency: int
    per_url_timeout_ms: int
    max_page_chars: int
    plan_queries: int
    max_pages_round_1: int
    max_pages_later: int
    max_rounds: int
    max_gemini_calls: int
    extract_pages_per_call: int
    wall_timeout_seconds: float
    list_agent_timeout_seconds: float
    selector_enabled: bool
    resume_extract_chars: int


def _read_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {value}.")
    return value


def _read_float(name: str, default: float, minimum: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {value}.")
    return value


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _read_origins() -> tuple[str, ...]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    return origins or ("http://localhost:3000",)


def get_settings() -> Settings:
    """Build settings or raise a message naming the missing variables."""

    missing = [name for name in REQUIRED_VARIABLES if not os.getenv(name, "").strip()]
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(
            f"Missing required environment variable(s): {joined}. "
            "Copy backend/.env.example to backend/.env and fill in the values."
        )

    return Settings(
        tinyfish_api_key=os.environ["TINYFISH_API_KEY"].strip(),
        gemini_api_key=os.environ["GEMINI_API_KEY"].strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite",
        cors_origins=_read_origins(),
        stop_at_results=_read_int("STOP_AT_RESULTS", 40, 1),
        search_concurrency=_read_int("SEARCH_CONCURRENCY", 4, 1),
        fetch_concurrency=_read_int("FETCH_CONCURRENCY", 12, 1),
        fetch_batch=_read_int("FETCH_BATCH", 3, 1),
        extract_concurrency=_read_int("EXTRACT_CONCURRENCY", 12, 1),
        per_url_timeout_ms=_read_int("PER_URL_TIMEOUT_MS", 8_000, 500),
        max_page_chars=_read_int("MAX_PAGE_CHARS", 9_000, 1_000),
        plan_queries=_read_int("PLAN_QUERIES", 16, 1),
        max_pages_round_1=_read_int("MAX_PAGES_ROUND_1", 120, 1),
        max_pages_later=_read_int("MAX_PAGES_LATER", 50, 1),
        max_rounds=_read_int("MAX_ROUNDS", 4, 1),
        max_gemini_calls=_read_int("MAX_GEMINI_CALLS", 600, 1),
        extract_pages_per_call=_read_int("EXTRACT_PAGES_PER_CALL", 3, 1),
        wall_timeout_seconds=_read_float("WALL_TIMEOUT_SECONDS", 180.0, 1.0),
        list_agent_timeout_seconds=_read_float("LIST_AGENT_TIMEOUT_SECONDS", 60.0, 1.0),
        selector_enabled=_read_bool("SELECTOR_ENABLED", True),
        resume_extract_chars=_read_int("RESUME_EXTRACT_CHARS", 3_500, 500),
    )


settings: Settings = get_settings()
