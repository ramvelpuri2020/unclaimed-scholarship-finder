"""Per-hunt diagnostics: timings, model calls, failovers and drop reasons.

The file is written next to the hunt JSON as ``<huntId>.diag.json``. It never
contains prompts, page text or resume text: calls store only the stage, model
id, timing, outcome classification and the first 160 characters of an error;
drops store only the program name, provider, URL, reason and either the model's
weak reason or a short date snippet taken from the page.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from .cleaning import strip_private_use
from .logging_setup import redact_text

HUNTS_DIR: Path = Path(__file__).resolve().parents[1] / "data" / "hunts"
MAX_CALLS = 400
MAX_DROPS = 500
MAX_ERROR_CHARS = 160
MAX_DETAIL_CHARS = 200
MAX_FIELD_CHARS = 120

OUTCOMES = frozenset(
    {
        "ok",
        "timeout",
        "rate_limit",
        "daily_quota",
        "model_not_found",
        "unsupported_param",
        "invalid_json",
        "server_error",
        "budget",
        "other",
    }
)


def _clean(value: object, limit: int) -> str:
    text = " ".join(strip_private_use(str(value or "")).split())
    return redact_text(text, max_chars=limit)


class HuntDiagnostics:
    """Thread-safe recorder for one hunt."""

    def __init__(self, hunt_id: str, started_at: str) -> None:
        self.hunt_id = hunt_id
        self.started_at = started_at
        self._started = time.perf_counter()
        self._lock = threading.Lock()
        self.calls: list[dict[str, Any]] = []
        self.stages: dict[str, dict[str, Any]] = {}
        self.drops: list[dict[str, Any]] = []
        self.failovers: list[dict[str, Any]] = []
        self.models: dict[str, Any] = {}
        self.first: dict[str, float] = {}
        self.stop_reason: str | None = None
        self.counts: dict[str, int] = {}

    def t(self) -> float:
        return round(time.perf_counter() - self._started, 3)

    def stage_start(self, name: str) -> None:
        with self._lock:
            self.stages[name] = {
                "start": self.t(),
                "end": None,
                "seconds": None,
                "result": None,
            }

    def stage_end(
        self,
        name: str,
        *,
        result: str | None = None,
        success: bool | None = None,
        **extra: Any,
    ) -> None:
        with self._lock:
            entry = self.stages.setdefault(
                name, {"start": self.t(), "end": None, "seconds": None, "result": None}
            )
            end = self.t()
            entry["end"] = end
            start = entry.get("start")
            if isinstance(start, int | float):
                entry["seconds"] = round(max(0.0, end - float(start)), 3)
            if result is not None:
                entry["result"] = _clean(result, MAX_FIELD_CHARS)
            if success is not None:
                entry["success"] = bool(success)
            for key, value in extra.items():
                entry[key] = _clean(value, MAX_DETAIL_CHARS) if isinstance(value, str) else value

    def mark(self, name: str) -> None:
        """Record the first occurrence of a milestone, in seconds from start."""

        with self._lock:
            self.first.setdefault(name, self.t())

    def bump(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self.counts[name] = int(self.counts.get(name, 0)) + amount

    def record_call(
        self,
        *,
        stage: str,
        model: str,
        t_start: float,
        seconds: float,
        outcome: str,
        status: object = None,
        error: str = "",
        failover: bool = False,
    ) -> None:
        classified = outcome if outcome in OUTCOMES else "other"
        call = {
            "stage": _clean(stage, 40),
            "model": _clean(model, 80),
            "t_start": round(float(t_start), 3),
            "seconds": round(float(seconds), 3),
            "outcome": classified,
            "status": status if isinstance(status, int | str) else None,
            "error": _clean(error, MAX_ERROR_CHARS),
            "failover": bool(failover),
        }
        with self._lock:
            if len(self.calls) < MAX_CALLS:
                self.calls.append(call)
            if failover:
                self.failovers.append(
                    {
                        "stage": call["stage"],
                        "model": call["model"],
                        "t": call["t_start"],
                        "outcome": classified,
                        "status": call["status"],
                        "error": call["error"],
                    }
                )

    def model_for_stage(self, stage: str) -> str | None:
        with self._lock:
            for call in reversed(self.calls):
                if call["stage"] == stage and call["model"]:
                    return str(call["model"])
        return None

    def record_drop(
        self,
        *,
        name: str,
        provider: str,
        url: str,
        reason: str,
        detail: str = "",
    ) -> None:
        entry = {
            "name": _clean(name, MAX_FIELD_CHARS),
            "provider": _clean(provider, MAX_FIELD_CHARS),
            "url": _clean(url, 300),
            "reason": _clean(reason, 60),
            "detail": _clean(detail, MAX_DETAIL_CHARS),
        }
        with self._lock:
            if len(self.drops) < MAX_DROPS:
                self.drops.append(entry)

    def record_models(self, snapshot: dict[str, Any] | None) -> None:
        if not isinstance(snapshot, dict):
            return
        models = snapshot.get("models")
        if not isinstance(models, dict):
            return
        summary: dict[str, Any] = {}
        for model_id, detail in models.items():
            if not isinstance(detail, dict):
                continue
            summary[str(model_id)] = {
                "requests": int(detail.get("requests", 0)),
                "failovers": int(detail.get("failovers", 0)),
                "rate_limits": int(detail.get("rate_limits", 0)),
                "seconds_waiting": float(detail.get("seconds_waiting", 0.0)),
                "max_per_minute": int(detail.get("max_per_minute", 0)),
                "disabled": bool(detail.get("disabled", False)),
            }
        with self._lock:
            self.models = summary

    def finish(self, stop_reason: str | None) -> None:
        with self._lock:
            self.stop_reason = _clean(stop_reason or "", 60) or None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "huntId": self.hunt_id,
                "startedAt": self.started_at,
                "stopReason": self.stop_reason,
                "calls": list(self.calls),
                "failovers": list(self.failovers),
                "stages": json.loads(json.dumps(self.stages, default=str)),
                "first": dict(self.first),
                "drops": list(self.drops),
                "models": dict(self.models),
                "counts": dict(self.counts),
            }

    def write(self, path: Path | None = None) -> Path:
        target = path or HUNTS_DIR / f"{self.hunt_id}.diag.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        temporary.replace(target)
        return target


_active: HuntDiagnostics | None = None
_active_lock = threading.Lock()


def begin(hunt_id: str, started_at: str) -> HuntDiagnostics:
    global _active
    diagnostics = HuntDiagnostics(hunt_id, started_at)
    with _active_lock:
        _active = diagnostics
    return diagnostics


def active() -> HuntDiagnostics | None:
    with _active_lock:
        return _active


def clear() -> None:
    global _active
    with _active_lock:
        _active = None
