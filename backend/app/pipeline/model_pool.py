"""Pooled Gemini models with per-model pacing, daily quotas and failover.

Every usable free-tier model is a separate lane. Each lane has a sliding
60-second request and token window, a Pacific-midnight daily counter and its own
capability flags, so one slow or rejected model never stops the hunt. The
dispatcher picks the lane whose pacer can accept the call soonest, and fails a
call over to the next lane instead of retrying a model that just failed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google import genai
from google.genai import types

from ..config import ConfigError, settings
from ..threads import run_daemon
from .gemini import (
    GeminiBudget,
    GeminiBudgetExceeded,
    GeminiModelError,
    GeminiPoolExhausted,
)

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60.0
WORKING_FRACTION = 0.9
DAILY_RESERVE = 12
CHARS_PER_TOKEN = 4
OUTPUT_TOKEN_ALLOWANCE = 1_500
RETRY_DOWNGRADE_SECONDS = 60.0
RETRY_DOWNGRADE_FACTOR = 0.8
MAX_ATTEMPTS_PER_MODEL = 4
DAILY_LIMIT_MESSAGE = "Gemini daily limit reached; showing the results found so far"
USAGE_PATH = Path(__file__).resolve().parents[2] / "data" / "gemini_usage.json"

try:
    PACIFIC_TZ: tzinfo = ZoneInfo("America/Los_Angeles")
except ZoneInfoNotFoundError:  # pragma: no cover - only on a system without tzdata
    PACIFIC_TZ = timezone(timedelta(hours=-8))
    logger.warning("America/Los_Angeles timezone data is unavailable; using a fixed UTC-8 date")


@dataclass(frozen=True)
class ModelSpec:
    """One model's free-tier limits, straight from the dashboard."""

    name: str
    rpm: int
    tpm: int
    rpd: int

    @property
    def working_rpm(self) -> int:
        return max(1, int(self.rpm * WORKING_FRACTION))

    @property
    def working_tpm(self) -> int:
        return max(1, int(self.tpm * WORKING_FRACTION))


DEFAULT_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec("Gemini 3.1 Flash Lite", 15, 250_000, 500),
    ModelSpec("Gemini 3.5 Flash Lite", 15, 250_000, 500),
    ModelSpec("Gemini 2.5 Flash Lite", 10, 250_000, 20),
    ModelSpec("Gemini 2.5 Flash", 5, 250_000, 20),
    ModelSpec("Gemini 3 Flash", 5, 250_000, 20),
    ModelSpec("Gemini 3.6 Flash", 5, 250_000, 20),
    ModelSpec("Gemini 3.8 Flash", 5, 250_000, 20),
    ModelSpec("Gemini 4 Hydrogen", 5, 250_000, 20),
)

QUALITY_ORDER: tuple[str, ...] = (
    "Gemini 3.8 Flash",
    "Gemini 4 Hydrogen",
    "Gemini 3.6 Flash",
    "Gemini 3 Flash",
    "Gemini 2.5 Flash",
    "Gemini 3.1 Flash Lite",
    "Gemini 3.5 Flash Lite",
)

EXTRACTION_PRIMARIES: tuple[str, ...] = (
    "Gemini 3.1 Flash Lite",
    "Gemini 3.5 Flash Lite",
)

EXTRACTION_ORDER: tuple[str, ...] = (
    *EXTRACTION_PRIMARIES,
    "Gemini 2.5 Flash Lite",
    "Gemini 2.5 Flash",
    "Gemini 3 Flash",
    "Gemini 3.6 Flash",
    "Gemini 3.8 Flash",
    "Gemini 4 Hydrogen",
)

DAILY_QUOTA_MARKERS = ("per day", "perday", "per-day", "requests per day", "daily quota", "daily limit")
SCHEMA_REJECTION_MARKERS = ("response_json_schema", "response schema", "json schema", "responsejsonschema")
MODEL_ORDER_WORDS = frozenset({"gemini", "models", "model", "preview"})
QUALITY_ONLY_WORDS = frozenset({"lite", "pro", "exp", "image", "tts", "audio", "live", "vision", "embedding"})


class ModelApi(Protocol):
    """The one SDK call the dispatcher needs; tests inject a fake."""

    def generate(self, model_id: str, contents: Any, config: dict[str, Any]) -> str: ...


class SdkApi:
    def __init__(self, client: genai.Client) -> None:
        self._client = client

    def generate(self, model_id: str, contents: Any, config: dict[str, Any]) -> str:
        response = self._client.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(**config),
        )
        return (response.text or "").strip()


def estimate_tokens(chars: int) -> int:
    """Rough prompt cost: one token per four characters plus the output budget."""

    return max(1, chars // CHARS_PER_TOKEN + OUTPUT_TOKEN_ALLOWANCE)


def pacific_today(now: datetime | None = None) -> str:
    moment = now or datetime.now(PACIFIC_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(PACIFIC_TZ).date().isoformat()


def load_specs() -> list[ModelSpec]:
    """Default dashboard limits, optionally overridden by GEMINI_POOL_JSON."""

    specs: list[ModelSpec] = list(DEFAULT_SPECS)
    by_name = {spec.name: index for index, spec in enumerate(specs)}
    raw = os.getenv("GEMINI_POOL_JSON", "").strip()
    if not raw:
        return specs
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"GEMINI_POOL_JSON must be valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ConfigError("GEMINI_POOL_JSON must be a JSON array of {name, rpm, tpm, rpd} objects.")
    for item in payload:
        if not isinstance(item, dict):
            raise ConfigError("Each GEMINI_POOL_JSON entry must be an object.")
        name = str(item.get("name", "")).strip()
        if not name:
            raise ConfigError("Each GEMINI_POOL_JSON entry needs a non-empty name.")
        current = specs[by_name[name]] if name in by_name else ModelSpec(name, 1, 1, 1)
        try:
            rpm = int(item.get("rpm", current.rpm))
            tpm = int(item.get("tpm", current.tpm))
            rpd = int(item.get("rpd", current.rpd))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"GEMINI_POOL_JSON limits for {name} must be integers.") from exc
        if min(rpm, tpm, rpd) < 1:
            raise ConfigError(f"GEMINI_POOL_JSON limits for {name} must be positive.")
        override = ModelSpec(name, rpm, tpm, rpd)
        if name in by_name:
            specs[by_name[name]] = override
        else:
            by_name[name] = len(specs)
            specs.append(override)
    return specs


def _words(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", text.lower()))


def normalize_model_name(name: str) -> tuple[str, ...]:
    return tuple(word for word in _words(name) if word not in MODEL_ORDER_WORDS)


def _version_words(words: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(word for word in words if word.isdigit())


def resolve_model_id(display_name: str, available: Sequence[tuple[str, bool]]) -> str | None:
    """Resolve a dashboard display name to a real model id.

    Case-insensitive, word-normalized matching: an exact word sequence wins,
    then the candidate with the fewest extra words, ignoring chat/image/audio
    variants unless the display name asked for them.
    """

    target = normalize_model_name(display_name)
    if not target:
        return None
    usable = [(model_id, ok) for model_id, ok in available if ok]
    exact = [model_id for model_id, _ in usable if normalize_model_name(model_id) == target]
    if exact:
        return min(exact, key=len)
    target_words = set(target)
    target_version = _version_words(target)
    candidates: list[tuple[int, int, str]] = []
    for model_id, _ in usable:
        normalized = normalize_model_name(model_id)
        words = set(normalized)
        if not target_words <= words:
            continue
        version = _version_words(normalized)
        if version[: len(target_version)] != target_version:
            continue
        extra_numbers = version[len(target_version) :]
        if any(len(number) < 2 for number in extra_numbers):
            continue
        extra = words - target_words
        if extra & QUALITY_ONLY_WORDS:
            continue
        candidates.append((len(extra), len(model_id), model_id))
    if not candidates:
        return None
    return min(candidates)[2]


class ModelPacer:
    """Sliding-window request and token pacing for one model.

    Requests wait for a slot instead of being sent and rejected. A 429 drops the
    effective rate by 20% for 60 seconds and honors Retry-After. Quality-tier
    waiters are served before extraction waiters.
    """

    def __init__(
        self,
        rpm: int,
        tpm: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        start: float | None = None,
    ) -> None:
        self.rpm_limit = max(1, int(rpm * WORKING_FRACTION))
        self.tpm_limit = max(1, int(tpm * WORKING_FRACTION))
        self._clock = clock
        self._events: deque[tuple[float, int]] = deque()
        self._penalty_until = 0.0
        self._locked_until = 0.0
        self._assign = asyncio.Lock()
        self._waiting: dict[int, int] = {1: 0, 0: 0}
        self._minute_start = clock() if start is None else start
        self.minute_counts: dict[int, int] = {}
        self.max_per_minute = 0
        self.requests = 0
        self.rate_limits = 0
        self.total_wait_seconds = 0.0

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= WINDOW_SECONDS:
            self._events.popleft()

    def _effective_limits(self, now: float) -> tuple[int, int]:
        factor = RETRY_DOWNGRADE_FACTOR if now < self._penalty_until else 1.0
        return (
            max(1, int(self.rpm_limit * factor)),
            max(1, int(self.tpm_limit * factor)),
        )

    def wait_seconds(self, now: float, tokens: int) -> float:
        """Seconds until this request can be sent without breaking a window."""

        self._prune(now)
        rpm, tpm = self._effective_limits(now)
        cooldown = max(0.0, self._locked_until - now)
        tokens = max(0, min(tokens, tpm))
        candidates = {now}
        for stored_at, _ in self._events:
            candidates.add(stored_at + WINDOW_SECONDS)
        for candidate in sorted(candidates):
            if candidate < now:
                continue
            live = [(at, cost) for at, cost in self._events if at > candidate - WINDOW_SECONDS]
            if len(live) < rpm and sum(cost for _, cost in live) + tokens <= tpm:
                return max(candidate - now, cooldown)
        return max(WINDOW_SECONDS, cooldown)

    def record(self, now: float, tokens: int) -> None:
        self._events.append((now, max(0, tokens)))
        self.requests += 1
        minute = int((now - self._minute_start) // WINDOW_SECONDS)
        self.minute_counts[minute] = self.minute_counts.get(minute, 0) + 1
        self.max_per_minute = max(self.max_per_minute, self.minute_counts[minute])

    def reset_stats(self) -> None:
        """Clear per-run counters without clearing the sliding window itself."""

        self.minute_counts.clear()
        self.max_per_minute = 0
        self.requests = 0
        self.rate_limits = 0
        self.total_wait_seconds = 0.0

    def record_429(self, now: float, retry_after: float | None) -> None:
        self.rate_limits += 1
        self._penalty_until = max(self._penalty_until, now + RETRY_DOWNGRADE_SECONDS)
        if retry_after is not None:
            self._locked_until = max(self._locked_until, now + min(max(retry_after, 0.0), 60.0))

    async def acquire(self, tokens: int, *, priority: int = 1) -> None:
        """Wait for a slot, then record it. priority 1 is quality, 0 extraction."""

        self._waiting[priority] += 1
        try:
            while True:
                async with self._assign:
                    now = self._clock()
                    if priority == 0 and self._waiting[1] > 0:
                        delay = 0.05
                    else:
                        delay = self.wait_seconds(now, tokens)
                        if delay <= 0.0:
                            self.record(self._clock(), tokens)
                            return
                started = self._clock()
                await asyncio.sleep(min(max(delay, 0.02), 1.0))
                self.total_wait_seconds += max(0.0, self._clock() - started)
        finally:
            self._waiting[priority] -= 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "requests_by_minute": {str(minute): count for minute, count in sorted(self.minute_counts.items())},
            "max_per_minute": self.max_per_minute,
            "rate_limits": self.rate_limits,
            "seconds_waiting": round(self.total_wait_seconds, 2),
            "working_rpm": self.rpm_limit,
            "working_tpm": self.tpm_limit,
        }


class UsageStore:
    """Per-model request counts for one Pacific day, persisted as counts + date."""

    def __init__(
        self,
        path: Path = USAGE_PATH,
        *,
        today: Callable[[], str] = pacific_today,
    ) -> None:
        self._path = path
        self._today = today
        self._lock = threading.Lock()
        self._day = today()
        self._counts: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict) or payload.get("date") != self._day:
            return
        counts = payload.get("counts")
        if not isinstance(counts, dict):
            return
        for key, value in counts.items():
            try:
                self._counts[str(key)] = max(0, int(value))
            except (TypeError, ValueError):
                continue

    def _roll(self) -> None:
        current = self._today()
        if current != self._day:
            self._day = current
            self._counts = {}

    def used(self, model_id: str) -> int:
        with self._lock:
            self._roll()
            return self._counts.get(model_id, 0)

    def increment(self, model_id: str) -> int:
        with self._lock:
            self._roll()
            self._counts[model_id] = self._counts.get(model_id, 0) + 1
            count = self._counts[model_id]
            self._save_locked()
            return count

    def mark_exhausted(self, model_id: str, rpd: int) -> None:
        with self._lock:
            self._roll()
            self._counts[model_id] = max(self._counts.get(model_id, 0), rpd)
            self._save_locked()

    def _save_locked(self) -> None:
        payload = {"date": self._day, "counts": dict(sorted(self._counts.items()))}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(self._path)
        except OSError as exc:
            logger.warning("Could not persist Gemini usage: %s", exc)

    def save(self) -> None:
        with self._lock:
            self._roll()
            self._save_locked()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            self._roll()
            return dict(self._counts)


OVERFLOW_RPM = 5
OVERFLOW_MAX_WAIT_SECONDS = 8.0


class _ModelFailed(Exception):
    """This model cannot serve the call; move to the next lane."""


@dataclass
class PooledModel:
    spec: ModelSpec
    model_id: str
    api: ModelApi
    pacer: ModelPacer
    json_schema: bool = True
    thinking: str = "unset"
    disabled: bool = False


def _status_of(exc: BaseException) -> object:
    return getattr(exc, "code", None) or getattr(exc, "status_code", None)


def _retry_after(exc: BaseException, message: str) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        for key in ("retry-after", "Retry-After"):
            try:
                value = headers.get(key)
            except AttributeError:
                value = None
            if value:
                try:
                    return max(0.0, min(60.0, float(str(value).strip())))
                except ValueError:
                    pass
    match = re.search(r"retry(?:\s+in|\s+after)?\s*[:=]?\s*(\d+(?:\.\d+)?)\s*s", message, re.IGNORECASE)
    if match:
        return max(0.0, min(60.0, float(match.group(1))))
    return None


def _is_daily_quota(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in DAILY_QUOTA_MARKERS)


def _mentions_schema(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in SCHEMA_REJECTION_MARKERS)


def _is_missing_model(message: str) -> bool:
    """True when the provider says this model id does not exist or is unsupported."""

    lowered = message.lower()
    if "model" not in lowered:
        return False
    return any(
        marker in lowered
        for marker in (
            "not found",
            "does not exist",
            "not supported",
            "unsupported model",
            "not available",
        )
    )


def _classify_failure(exc: BaseException) -> tuple[str, object]:
    """Map an SDK exception onto the diagnostics outcome vocabulary."""

    message = str(exc)
    lowered = message.lower()
    status = _status_of(exc)
    if _is_daily_quota(message):
        return "daily_quota", status
    if status in (429, "429", "RESOURCE_EXHAUSTED") or "resource_exhausted" in lowered:
        return "rate_limit", status
    if status in (404, "404", "NOT_FOUND"):
        return "model_not_found", status
    if _mentions_schema(message) or "thinking" in lowered:
        return "unsupported_param", status
    if _is_missing_model(message):
        return "model_not_found", status
    if isinstance(status, int) and status >= 500:
        return "server_error", status
    return "other", status


def _reserve_applies(model: PooledModel) -> bool:
    """20-per-day models that also serve quality calls keep 12 requests back."""

    return model.spec.name in QUALITY_ORDER and model.spec.rpd <= 20


class ModelPool:
    """Every resolved model, its pacer, and the dispatcher that uses them."""

    def __init__(
        self,
        models: Sequence[PooledModel],
        *,
        usage: UsageStore,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.models = list(models)
        self.usage = usage
        self.clock = clock
        self.failovers = 0
        self.model_failovers: dict[str, int] = {}
        self.stage_models: dict[str, str] = {}
        self.extraction_models: list[str] = []
        self.rate_limit_messages: dict[str, int] = {}

    def begin_run(self) -> None:
        """Start the per-hunt counters fresh; pacing history and daily use stay."""

        self.failovers = 0
        self.model_failovers = {}
        self.stage_models = {}
        self.extraction_models = []
        self.rate_limit_messages = {}
        for model in self.models:
            model.pacer.reset_stats()

    @property
    def usable(self) -> list[PooledModel]:
        return [model for model in self.models if not model.disabled]

    def quality_chain(self) -> list[PooledModel]:
        return [
            model
            for name in QUALITY_ORDER
            for model in self.models
            if model.spec.name == name and not model.disabled
        ]

    def extraction_chain(self) -> list[PooledModel]:
        return [
            model
            for name in EXTRACTION_ORDER
            for model in self.models
            if model.spec.name == name and not model.disabled
        ]

    def remaining_today(self, model: PooledModel) -> int:
        return max(0, model.spec.rpd - self.usage.used(model.model_id))

    def offered(self, model: PooledModel, tier: str) -> bool:
        if model.disabled:
            return False
        remaining = self.remaining_today(model)
        if remaining <= 0:
            return False
        return not (
            tier == "extraction" and _reserve_applies(model) and remaining <= DAILY_RESERVE
        )

    def candidates(self, tier: str, tokens: int) -> list[PooledModel]:
        """Available models for this tier, soonest able to accept first.

        Extraction may only overflow onto a 5-requests-per-minute model while
        its pacer wait is under ``OVERFLOW_MAX_WAIT_SECONDS``.
        """

        chain = self.quality_chain() if tier == "quality" else self.extraction_chain()
        now = self.clock()
        index = {id(model): position for position, model in enumerate(chain)}
        offered: list[PooledModel] = []
        for model in chain:
            if not self.offered(model, tier):
                continue
            wait = model.pacer.wait_seconds(now, tokens)
            if (
                tier == "extraction"
                and model.spec.rpm <= OVERFLOW_RPM
                and wait >= OVERFLOW_MAX_WAIT_SECONDS
            ):
                continue
            offered.append(model)
        offered.sort(key=lambda model: (model.pacer.wait_seconds(now, tokens), index[id(model)]))
        return offered

    async def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        budget: GeminiBudget,
        *,
        tier: str = "extraction",
        temperature: float = 0.2,
        timeout: float = 90.0,
        thinking_level: Any = None,
        contents: Any = None,
        stage: str | None = None,
        retry_invalid_json: bool = True,
        estimate_chars: int | None = None,
        avoid_model: str | None = None,
    ) -> Any:
        data, _ = await self.generate_json_with_model(
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
        )
        return data

    async def generate_json_with_model(
        self,
        prompt: str,
        schema: dict[str, Any],
        budget: GeminiBudget,
        *,
        tier: str = "extraction",
        temperature: float = 0.2,
        timeout: float = 90.0,
        thinking_level: Any = None,
        contents: Any = None,
        stage: str | None = None,
        retry_invalid_json: bool = True,
        estimate_chars: int | None = None,
        avoid_model: str | None = None,
        priority: int | None = None,
    ) -> tuple[Any, str]:
        chars = estimate_chars if estimate_chars is not None else len(prompt)
        tokens = estimate_tokens(chars)
        offered = self.candidates(tier, tokens)
        if avoid_model:
            without_used = [model for model in offered if model.model_id != avoid_model]
            if without_used:
                offered = without_used
        if not offered:
            raise GeminiPoolExhausted(DAILY_LIMIT_MESSAGE)

        last_reason = "no model accepted the call"
        for model in offered:
            try:
                data = await self._attempt(
                    model,
                    prompt=prompt,
                    schema=schema,
                    budget=budget,
                    temperature=temperature,
                    timeout=timeout,
                    thinking_level=thinking_level,
                    contents=contents,
                    retry_invalid_json=retry_invalid_json,
                    tokens=tokens,
                    tier=tier,
                    priority=priority,
                    stage=stage,
                )
            except GeminiBudgetExceeded:
                raise
            except _ModelFailed as exc:
                last_reason = str(exc)
                self.failovers += 1
                self.model_failovers[model.model_id] = (
                    self.model_failovers.get(model.model_id, 0) + 1
                )
                logger.warning(
                    "Gemini model failed id=%s reason=%s; failing over",
                    model.model_id,
                    last_reason,
                )
                continue
            if stage:
                self.stage_models[stage] = model.model_id
            if tier == "extraction" and model.model_id not in self.extraction_models:
                self.extraction_models.append(model.model_id)
            return data, model.model_id

        logger.warning("Every Gemini model in tier=%s failed: %s", tier, last_reason)
        raise GeminiPoolExhausted(DAILY_LIMIT_MESSAGE)

    async def _attempt(
        self,
        model: PooledModel,
        *,
        prompt: str,
        schema: dict[str, Any],
        budget: GeminiBudget,
        temperature: float,
        timeout: float,
        thinking_level: Any,
        contents: Any,
        retry_invalid_json: bool,
        tokens: int,
        tier: str,
        priority: int | None = None,
        stage: str | None = None,
    ) -> Any:
        strict = False
        attempt = 0
        wait_priority = priority if priority is not None else (1 if tier == "quality" else 0)
        while attempt < MAX_ATTEMPTS_PER_MODEL:
            attempt += 1
            config: dict[str, Any] = {
                "response_mime_type": "application/json",
                "temperature": temperature,
            }
            prompt_text = prompt
            if model.json_schema:
                config["response_json_schema"] = schema
            else:
                prompt_text = (
                    f"{prompt}\n\nReturn only JSON that matches this JSON Schema exactly:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}"
                )
            if strict:
                prompt_text += "\n\nOutput valid JSON only. No prose, no markdown fences, no comments."
            level = self._thinking_level(model, thinking_level)
            if level is not None:
                try:
                    config["thinking_config"] = types.ThinkingConfig(thinking_level=level)
                except TypeError:
                    config.pop("thinking_config", None)

            wall_started = time.monotonic()
            try:
                budget.reserve()
            except GeminiBudgetExceeded:
                self._note_call(
                    model,
                    stage,
                    wall_started,
                    "budget",
                    None,
                    "Gemini request budget exhausted",
                    failover=False,
                )
                raise
            self.usage.increment(model.model_id)
            await model.pacer.acquire(tokens, priority=wait_priority)
            try:
                text = await asyncio.wait_for(
                    run_daemon(
                        model.api.generate,
                        model.model_id,
                        self._contents_for(contents, prompt_text, prompt),
                        config,
                    ),
                    timeout=timeout,
                )
            except TimeoutError as exc:
                self._note_call(model, stage, wall_started, "timeout", None, "timeout", failover=True)
                raise _ModelFailed("timeout") from exc
            except Exception as exc:
                outcome, status = _classify_failure(exc)
                downgrade = self._handle_error(model, exc)
                self._note_call(
                    model,
                    stage,
                    wall_started,
                    outcome,
                    status,
                    str(exc),
                    failover=not downgrade,
                )
                if downgrade:
                    continue
                raise _ModelFailed(str(exc)[:180]) from exc

            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                if retry_invalid_json and not strict:
                    strict = True
                    self._note_call(
                        model, stage, wall_started, "invalid_json", None, str(exc), failover=False
                    )
                    logger.info("Gemini returned invalid JSON from %s; retrying strictly", model.model_id)
                    continue
                self._note_call(
                    model, stage, wall_started, "invalid_json", None, str(exc), failover=True
                )
                raise _ModelFailed(f"invalid_json: {exc}") from exc
            self._note_call(model, stage, wall_started, "ok", None, "", failover=False)
            return data
        self._note_call(
            model,
            stage,
            time.monotonic(),
            "other",
            None,
            "capability retries exhausted",
            failover=True,
        )
        raise _ModelFailed("capability_retries_exhausted")

    def _note_call(
        self,
        model: PooledModel,
        stage: str | None,
        wall_started: float,
        outcome: str,
        status: object,
        error: str,
        *,
        failover: bool,
    ) -> None:
        from .. import diagnostics

        recorder = diagnostics.active()
        if recorder is None:
            return
        elapsed = max(0.0, time.monotonic() - wall_started)
        recorder.record_call(
            stage=stage or "unspecified",
            model=model.model_id,
            t_start=max(0.0, recorder.t() - elapsed),
            seconds=elapsed,
            outcome=outcome,
            status=status if isinstance(status, int | str) else None,
            error=error,
            failover=failover,
        )

    @staticmethod
    def _contents_for(contents: Any, prompt_text: str, prompt: str) -> Any:
        if contents is None:
            return prompt_text
        if prompt_text == prompt:
            return contents
        try:
            parts = list(contents.parts or [])
        except AttributeError:
            return prompt_text
        parts.append(types.Part.from_text(text=prompt_text[len(prompt) :].strip()))
        return types.Content(role="user", parts=parts)

    @staticmethod
    def _thinking_level(model: PooledModel, requested: Any) -> Any:
        if requested is None:
            return None
        if model.thinking == "off":
            return None
        level = getattr(types, "ThinkingLevel", None)
        if level is None:
            # Older SDKs expose neither the enum nor a thinking_level kwarg.
            return None
        if model.thinking == "unset":
            model.thinking = "minimal" if "MINIMAL" in str(requested) else "low"
        return level.LOW if model.thinking == "low" else level.MINIMAL

    def _handle_error(self, model: PooledModel, exc: BaseException) -> bool:
        """Return True when the same model should be retried with a downgrade."""

        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        status = _status_of(exc)
        now = self.clock()

        if _is_daily_quota(message):
            self.usage.mark_exhausted(model.model_id, model.spec.rpd)
            model.pacer.record_429(now, _retry_after(exc, message))
            self._note_rate_limit(message)
            logger.warning("Gemini daily quota reached id=%s: %s", model.model_id, message[:200])
            return False

        if status in (429, "429", "RESOURCE_EXHAUSTED") or "resource_exhausted" in lowered:
            model.pacer.record_429(now, _retry_after(exc, message))
            self._note_rate_limit(message)
            logger.warning("Gemini 429 id=%s: %s", model.model_id, message[:200])
            return False

        if model.json_schema and _mentions_schema(message):
            model.json_schema = False
            logger.warning(
                "Gemini rejected response_json_schema for %s; writing the schema into the prompt",
                model.model_id,
            )
            return True

        if model.thinking in {"minimal", "low"} and "thinking" in lowered:
            model.thinking = "low" if model.thinking == "minimal" else "off"
            logger.warning(
                "Gemini rejected thinking_level for %s; now using %s",
                model.model_id,
                model.thinking,
            )
            return True

        if status in (404, "404", "NOT_FOUND") or _is_missing_model(message):
            model.disabled = True
            logger.warning(
                "Gemini model unavailable id=%s; disabled for this process: %s",
                model.model_id,
                message[:200],
            )
            return False

        return False

    def _note_rate_limit(self, message: str) -> None:
        key = " ".join(message.split())[:200]
        self.rate_limit_messages[key] = self.rate_limit_messages.get(key, 0) + 1

    async def probe_primaries(self) -> list[str]:
        """Probe the two extraction primaries with one tiny JSON call each."""

        primaries = [model for model in self.extraction_chain()[:2] if not model.disabled]
        if not primaries:
            return []
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        }
        failed: list[str] = []

        async def probe(model: PooledModel) -> None:
            try:
                await self._attempt(
                    model,
                    prompt='Return JSON exactly as {"ok": true}.',
                    schema=schema,
                    budget=GeminiBudget(1),
                    temperature=0.0,
                    timeout=10.0,
                    thinking_level=None,
                    contents=None,
                    retry_invalid_json=False,
                    tokens=64,
                    tier="extraction",
                    stage="probe",
                )
            except Exception as exc:  # noqa: BLE001 - a failed probe only disables that model
                model.disabled = True
                failed.append(model.model_id)
                logger.warning(
                    "Gemini startup probe failed id=%s; disabled for this process: %s",
                    model.model_id,
                    exc,
                )

        await asyncio.gather(*(probe(model) for model in primaries), return_exceptions=True)
        return failed

    def snapshot(self) -> dict[str, Any]:
        models: dict[str, Any] = {}
        for model in self.models:
            detail = model.pacer.snapshot()
            detail.update(
                {
                    "display_name": model.spec.name,
                    "rpd": model.spec.rpd,
                    "failovers": int(self.model_failovers.get(model.model_id, 0)),
                    "used_today": self.usage.used(model.model_id),
                    "remaining_today": self.remaining_today(model),
                    "disabled": model.disabled,
                    "json_schema": model.json_schema,
                    "thinking": model.thinking,
                }
            )
            models[model.model_id] = detail
        return {
            "model_count": len(self.usable),
            "models": models,
            "failovers": self.failovers,
            "rate_limit_messages": dict(self.rate_limit_messages),
            "seconds_waiting": round(
                sum(model.pacer.total_wait_seconds for model in self.models), 2
            ),
            "stage_models": dict(self.stage_models),
            "extraction_models": list(self.extraction_models),
        }


_pool: ModelPool | None = None


def set_pool(pool: ModelPool | None) -> None:
    global _pool
    _pool = pool


def get_pool() -> ModelPool | None:
    return _pool


def require_pool() -> ModelPool:
    if _pool is None:
        raise GeminiModelError("Gemini model pool is not initialised.")
    return _pool


def _list_available(client: genai.Client) -> list[tuple[str, bool]]:
    available: list[tuple[str, bool]] = []
    for model in client.models.list():
        name = str(getattr(model, "name", "") or "").strip()
        if not name:
            continue
        actions = getattr(model, "supported_actions", None)
        if not actions:
            actions = getattr(model, "supported_generation_methods", None)
        supported = (
            any("generatecontent" in str(action).lower().replace("_", "") for action in actions)
            if actions
            else True
        )
        available.append((name.removeprefix("models/"), supported))
    return available


def _log_table(models: Sequence[PooledModel], usage: UsageStore) -> None:
    logger.info(
        "Gemini model pool: %d usable model(s)", sum(1 for model in models if not model.disabled)
    )
    logger.info(
        "  %-22s %-30s %4s %8s %4s %5s",
        "display",
        "model id",
        "rpm",
        "tpm",
        "rpd",
        "used",
    )
    for model in models:
        logger.info(
            "  %-22s %-30s %4d %8d %4d %5d",
            model.spec.name,
            model.model_id,
            model.spec.working_rpm,
            model.spec.working_tpm,
            model.spec.rpd,
            usage.used(model.model_id),
        )


async def initialise_pool(client: genai.Client | None = None) -> ModelPool:
    """Resolve every dashboard model against the live list API and arm the pool."""

    sdk = client or genai.Client(api_key=settings.gemini_api_key)
    try:
        available = await run_daemon(_list_available, sdk)
    except Exception as exc:
        raise GeminiModelError(f"Could not list Gemini models: {exc}") from exc

    specs = load_specs()
    usage = UsageStore(USAGE_PATH)
    models: list[PooledModel] = []
    for spec in specs:
        model_id = resolve_model_id(spec.name, available)
        if model_id is None:
            logger.warning(
                "Gemini model %s did not resolve to a model that supports generateContent; dropping it",
                spec.name,
            )
            continue
        models.append(
            PooledModel(
                spec=spec,
                model_id=model_id,
                api=SdkApi(sdk),
                pacer=ModelPacer(spec.working_rpm, spec.working_tpm),
            )
        )

    extraction_names = {model.spec.name for model in models}
    if not extraction_names & set(EXTRACTION_ORDER):
        raise ConfigError(
            "No Gemini extraction model resolved. The models list API returned no model for "
            "Gemini 3.1 Flash Lite, Gemini 3.5 Flash Lite or any overflow model. "
            "Check GEMINI_API_KEY and GEMINI_POOL_JSON."
        )

    _log_table(models, usage)
    pool = ModelPool(models, usage=usage)
    set_pool(pool)
    logger.info(
        "Gemini pool ready quality=%s extraction=%s",
        [model.model_id for model in pool.quality_chain()],
        [model.model_id for model in pool.extraction_chain()],
    )
    return pool
