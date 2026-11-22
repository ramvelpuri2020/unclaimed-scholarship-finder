"""Gemini request budget, exceptions and the JSON entry points.

The actual model selection, pacing and failover live in ``model_pool``. These
functions are the stable surface the pipeline stages call, and they keep the
per-hunt request budget in one place.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Self

from google.genai import types

logger = logging.getLogger(__name__)


def minimal_thinking() -> Any:
    """The SDK's MINIMAL thinking level, or None when the SDK has no such enum."""

    level = getattr(types, "ThinkingLevel", None)
    if level is None:
        return None
    return getattr(level, "MINIMAL", None)


class GeminiError(RuntimeError):
    """A Gemini call failed, but the hunt can continue."""


class GeminiModelError(GeminiError):
    """No usable Gemini model is configured; the hunt must stop."""


class GeminiBudgetExceeded(GeminiError):
    """The hunt has spent its Gemini request budget."""


class GeminiPoolExhausted(GeminiError):
    """Every model in the requested tier is out of capacity today."""


class GeminiBudget:
    """Thread-safe request counter shared by every pipeline stage."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self.used = 0
        self._lock = threading.Lock()

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.limit - self.used)

    def reserve(self) -> None:
        with self._lock:
            if self.used >= self.limit:
                raise GeminiBudgetExceeded("Gemini request budget exhausted.")
            self.used += 1


class RateLimitGate:
    """Concurrency gate retained for pipeline call sites.

    Model pacers do the rate limiting now; this only bounds how many calls run
    at once so a burst of failures cannot fill the thread pool.
    """

    def __init__(self, limit: int, floor: int = 5, window: float = 10.0) -> None:
        self.initial_limit = max(1, limit)
        self.limit = self.initial_limit
        self.window = window
        self._semaphore = asyncio.Semaphore(self.initial_limit)

    async def __aenter__(self) -> Self:
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._semaphore.release()

    def snapshot(self) -> dict[str, float | int]:
        return {"initial_limit": self.initial_limit, "effective_limit": self.limit}


async def generate_json(
    prompt: str,
    schema: dict[str, Any],
    budget: GeminiBudget,
    *,
    temperature: float = 0.2,
    timeout: float = 90.0,
    thinking_level: Any = None,
    gate: RateLimitGate | None = None,
    use_slot: bool = False,
    retry_invalid_json: bool = True,
    tier: str = "extraction",
    stage: str | None = None,
    contents: Any = None,
    estimate_chars: int | None = None,
    avoid_model: str | None = None,
    priority: int | None = None,
) -> Any:
    """Dispatch one JSON call through the model pool."""

    data, _ = await generate_json_with_model(
        prompt,
        schema,
        budget,
        temperature=temperature,
        timeout=timeout,
        thinking_level=thinking_level,
        gate=gate,
        use_slot=use_slot,
        retry_invalid_json=retry_invalid_json,
        tier=tier,
        stage=stage,
        contents=contents,
        estimate_chars=estimate_chars,
        avoid_model=avoid_model,
        priority=priority,
    )
    return data


async def generate_json_with_model(
    prompt: str,
    schema: dict[str, Any],
    budget: GeminiBudget,
    *,
    temperature: float = 0.2,
    timeout: float = 90.0,
    thinking_level: Any = None,
    gate: RateLimitGate | None = None,
    use_slot: bool = False,
    retry_invalid_json: bool = True,
    tier: str = "extraction",
    stage: str | None = None,
    contents: Any = None,
    estimate_chars: int | None = None,
    avoid_model: str | None = None,
    priority: int | None = None,
) -> tuple[Any, str]:
    """Dispatch one call and report which model produced the answer."""

    del gate, use_slot  # pacing and capacity are handled by the model pool
    from .model_pool import require_pool

    pool = require_pool()
    return await pool.generate_json_with_model(
        prompt,
        schema,
        budget,
        tier=tier,
        temperature=temperature,
        timeout=timeout,
        thinking_level=thinking_level,
        contents=contents,
        stage=stage,
        retry_invalid_json=retry_invalid_json,
        estimate_chars=estimate_chars,
        avoid_model=avoid_model,
        priority=priority,
    )
