"""Offline checks for diagnostics, the resume critical path and late scoring."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app import diagnostics
from app import hunt as hunt_module
from app.hunt import (
    HuntManager,
    HuntState,
    QueuedUrl,
    UrlQueue,
    _empty_stats,
    publish,
)
from app.models import Profile, ResumePayload, SiteProgressEvent
from app.pipeline.discovery import Candidate
from app.pipeline.gemini import (
    GeminiBudget,
    GeminiPoolExhausted,
    RateLimitGate,
)
from app.pipeline.model_pool import (
    ModelPacer,
    ModelPool,
    ModelSpec,
    PooledModel,
    UsageStore,
)
from app.pipeline.page_selector import neutral_order


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class FakeStatusError(RuntimeError):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.status_code = status


class FakeApi:
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    def generate(self, model_id: str, contents: Any, config: dict[str, Any]) -> str:
        return str(self.handler(model_id, contents, config))


def _profile() -> Profile:
    return Profile(
        full_name="",
        province="Ontario",
        school="Western University",
        field="Engineering",
        year="1st year",
        income_range="",
        status="Canadian citizen",
    )


def _pool(
    tmp_path: Path,
    clock: FakeClock,
    specs: list[tuple[str, str]],
    handler: Any,
) -> ModelPool:
    models = [
        PooledModel(
            spec=ModelSpec(name, 15, 250_000, 500),
            model_id=model_id,
            api=FakeApi(handler),
            pacer=ModelPacer(15, 250_000, clock=clock),
        )
        for name, model_id in specs
    ]
    return ModelPool(models, usage=UsageStore(tmp_path / "usage.json"), clock=clock)


def test_first_planner_call_receives_the_full_local_resume_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics.clear()
    seen: dict[str, Any] = {}
    full_text = "Built a bridge inspection robot for a student design team. " * 40

    async def fake_prepare(*args: Any, **kwargs: Any) -> tuple[str, bool]:
        return full_text, False

    async def fake_plan(*args: Any, **kwargs: Any) -> list[Any]:
        if "resume" not in seen:
            seen["resume"] = args[1]
        return []

    monkeypatch.setattr(hunt_module, "prepare_resume_text", fake_prepare)
    monkeypatch.setattr(hunt_module, "plan_queries", fake_plan)
    monkeypatch.setattr(
        hunt_module,
        "settings",
        replace(
            hunt_module.settings,
            wall_timeout_seconds=30.0,
            fetch_concurrency=1,
            extract_concurrency=1,
            max_rounds=1,
            selector_enabled=False,
        ),
    )

    profile = _profile().model_copy(
        update={
            "resume": ResumePayload(
                name="resume.pdf",
                data_url="data:application/pdf;base64,QUFBQQ==",
            )
        }
    )
    state = HuntState(hunt_id="resume-order", profile=profile, stats=_empty_stats())
    state.started = time.perf_counter()
    started = time.perf_counter()
    deadline = started + 30.0
    manager = HuntManager()

    asyncio.run(
        manager._execute(state, started, deadline, GeminiBudget(5), RateLimitGate(1))
    )

    assert seen["resume"] == full_text
    assert state.stats.get("planning_failures") == 3


def test_planner_timeout_fails_over_to_another_model(tmp_path: Path) -> None:
    diagnostics.clear()
    clock = FakeClock()

    def handler(model_id: str, contents: Any, config: dict[str, Any]) -> str:
        if model_id == "model-a":
            time.sleep(0.2)
        return json.dumps({"queries": []})

    pool = _pool(
        tmp_path,
        clock,
        [("Gemini 3.1 Flash Lite", "model-a"), ("Gemini 3.5 Flash Lite", "model-b")],
        handler,
    )
    data, used = asyncio.run(
        pool.generate_json_with_model(
            "prompt",
            {"type": "object"},
            GeminiBudget(5),
            tier="quality",
            timeout=0.05,
        )
    )
    assert data == {"queries": []}
    assert used == "model-b"
    assert pool.failovers == 1
    assert pool.model_failovers["model-a"] == 1


def test_late_scores_reprioritize_the_fetch_queue() -> None:
    async def scenario() -> list[str]:
        queue = UrlQueue()
        await queue.put(
            [
                QueuedUrl(url="https://a.example/one", score=5, angle="x", round=1),
                QueuedUrl(url="https://b.example/two", score=4, angle="y", round=1),
            ]
        )
        await queue.reprioritize(
            {"https://a.example/one": 1, "https://b.example/two": 5}
        )
        batch = await queue.take(2)
        return [item.url for item in batch]

    assert asyncio.run(scenario()) == ["https://b.example/two", "https://a.example/one"]


def test_neutral_order_interleaves_angles_and_caps_each_host() -> None:
    candidates = [
        Candidate(
            url=f"https://same.example/{index}",
            title="",
            snippet="",
            site_name="",
            angle="school" if index % 2 == 0 else "national",
        )
        for index in range(8)
    ]
    ordered = neutral_order(candidates)
    assert [item.angle for item in ordered[:2]] == ["school", "national"]
    assert len(ordered) == 8
    assert all(item.url for item in ordered)


def test_diagnostics_file_contains_no_resume_text_email_or_phone(tmp_path: Path) -> None:
    diagnostics.clear()
    recorder = diagnostics.HuntDiagnostics("redaction", "2026-11-22T10:00:00+00:00")
    recorder.record_call(
        stage="extraction",
        model="gemini-3.1-flash-lite",
        t_start=1.0,
        seconds=1.5,
        outcome="server_error",
        status=500,
        error=(
            "failed for alex@example.com or +1 (519) 555-1234 with key "
            "AIza" + "B" * 35
        ),
        failover=True,
    )
    recorder.record_drop(
        name="Sample Award",
        provider="Western University",
        url="https://example.edu/awards",
        reason="stale_or_unverified",
        detail="Applications closed March 1, 2024; contact alex@example.com",
    )
    path = tmp_path / "redaction.diag.json"
    recorder.write(path)
    text = path.read_text(encoding="utf-8")

    assert "alex@example.com" not in text
    assert "555-1234" not in text
    assert "AIza" not in text
    assert "B" * 35 not in text
    payload = json.loads(text)
    assert payload["calls"][0]["outcome"] == "server_error"
    assert payload["drops"][0]["reason"] == "stale_or_unverified"


def test_events_carry_seconds_since_start() -> None:
    diagnostics.clear()
    state = HuntState(hunt_id="timed", profile=_profile(), stats=_empty_stats())
    state.started = time.perf_counter() - 1.5
    publish(state, SiteProgressEvent(site_id="search", message="hello"))
    payload = json.loads(state.events[-1])
    assert "t" in payload
    assert 1.4 <= float(payload["t"]) <= 3.0


def test_a_disabled_model_stays_disabled_in_the_next_hunt(tmp_path: Path) -> None:
    diagnostics.clear()
    clock = FakeClock()

    def handler(model_id: str, contents: Any, config: dict[str, Any]) -> str:
        raise FakeStatusError(f"404 model {model_id} is not found", 404)

    pool = _pool(
        tmp_path,
        clock,
        [("Gemini 3.1 Flash Lite", "model-a"), ("Gemini 3.5 Flash Lite", "model-b")],
        handler,
    )
    with pytest.raises(GeminiPoolExhausted):
        asyncio.run(
            pool.generate_json_with_model(
                "prompt", {"type": "object"}, GeminiBudget(5), tier="quality"
            )
        )
    assert all(model.disabled for model in pool.models)

    pool.begin_run()
    assert all(model.disabled for model in pool.models)
    assert [model.model_id for model in pool.candidates("quality", 100)] == []
