"""Offline checks for pooled Gemini pacing, quotas, failover and batching."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from google.genai import types

from app.models import Profile
from app.pipeline.extractor import extract_pages
from app.pipeline.gemini import GeminiBudget, GeminiPoolExhausted
from app.pipeline.model_pool import (
    DAILY_LIMIT_MESSAGE,
    EXTRACTION_ORDER,
    QUALITY_ORDER,
    ModelPacer,
    ModelPool,
    ModelSpec,
    PooledModel,
    UsageStore,
    pacific_today,
    resolve_model_id,
    set_pool,
)
from app.pipeline.reader import Page

SPECS = {
    "Gemini 3.1 Flash Lite": ModelSpec("Gemini 3.1 Flash Lite", 15, 250_000, 500),
    "Gemini 3.5 Flash Lite": ModelSpec("Gemini 3.5 Flash Lite", 15, 250_000, 500),
    "Gemini 2.5 Flash Lite": ModelSpec("Gemini 2.5 Flash Lite", 10, 250_000, 20),
    "Gemini 2.5 Flash": ModelSpec("Gemini 2.5 Flash", 5, 250_000, 20),
    "Gemini 3 Flash": ModelSpec("Gemini 3 Flash", 5, 250_000, 20),
    "Gemini 3.6 Flash": ModelSpec("Gemini 3.6 Flash", 5, 250_000, 20),
    "Gemini 3.8 Flash": ModelSpec("Gemini 3.8 Flash", 5, 250_000, 20),
    "Gemini 4 Hydrogen": ModelSpec("Gemini 4 Hydrogen", 5, 250_000, 20),
}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeStatusError(RuntimeError):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.status_code = status


class FakeApi:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def generate(self, model_id: str, contents: Any, config: dict[str, Any]) -> str:
        self.calls.append({"model_id": model_id, "contents": contents, "config": config})
        return str(self.handler(model_id, contents, config))


def _model_id(name: str) -> str:
    return name.lower().replace(".", "-").replace(" ", "-")


def _pool(
    tmp_path: Path,
    clock: FakeClock,
    names: list[str],
    handler: Any,
    *,
    day: str = "2026-11-22",
) -> ModelPool:
    models = [
        PooledModel(
            spec=SPECS[name],
            model_id=_model_id(name),
            api=FakeApi(handler),
            pacer=ModelPacer(SPECS[name].rpm, SPECS[name].tpm, clock=clock),
        )
        for name in names
    ]
    usage = UsageStore(tmp_path / "usage.json", today=lambda: day)
    return ModelPool(models, usage=usage, clock=clock)


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


def test_no_model_exceeds_its_working_limits_in_any_window() -> None:
    clock = FakeClock()
    pacer = ModelPacer(15, 100_000, clock=clock)
    times: list[float] = []
    costs: list[int] = []
    for _ in range(80):
        clock.advance(pacer.wait_seconds(clock(), 2_000))
        pacer.record(clock(), 2_000)
        times.append(clock())
        costs.append(2_000)

    assert pacer.rpm_limit == 13
    assert pacer.tpm_limit == 90_000
    for index, start in enumerate(times):
        window = [cost for at, cost in zip(times, costs) if start <= at < start + 60.0]
        assert len(window) <= pacer.rpm_limit
        assert sum(window) <= pacer.tpm_limit
        if index == 0:
            assert len(window) == pacer.rpm_limit


def test_tier_chains_follow_the_required_order(tmp_path: Path) -> None:
    clock = FakeClock()
    pool = _pool(tmp_path, clock, list(SPECS), lambda *_: "{}")
    assert [model.spec.name for model in pool.quality_chain()] == list(QUALITY_ORDER)
    assert [model.spec.name for model in pool.extraction_chain()] == list(EXTRACTION_ORDER)


def test_extraction_waits_while_a_quality_waiter_is_pending() -> None:
    pacer = ModelPacer(600, 10_000_000)
    pacer._waiting[1] = 1

    async def blocked() -> None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(pacer.acquire(10, priority=0), timeout=0.25)

    async def allowed() -> None:
        pacer._waiting[1] = 0
        await asyncio.wait_for(pacer.acquire(10, priority=0), timeout=1.0)

    asyncio.run(blocked())
    asyncio.run(allowed())
    assert pacer.requests == 1


def test_daily_quota_429_marks_exhaustion_and_fails_over(tmp_path: Path) -> None:
    clock = FakeClock()
    first = _model_id("Gemini 3.1 Flash Lite")
    second = _model_id("Gemini 3.5 Flash Lite")

    def handler(model_id: str, contents: Any, config: dict[str, Any]) -> str:
        if model_id == first:
            raise FakeStatusError("429 RESOURCE_EXHAUSTED: requests per day quota exceeded", 429)
        return json.dumps({"ok": True})

    pool = _pool(tmp_path, clock, ["Gemini 3.1 Flash Lite", "Gemini 3.5 Flash Lite"], handler)
    data, used = asyncio.run(
        pool.generate_json_with_model("prompt", {"type": "object"}, GeminiBudget(10))
    )
    assert data == {"ok": True}
    assert used == second
    assert pool.failovers == 1
    assert pool.usage.used(first) == SPECS["Gemini 3.1 Flash Lite"].rpd
    exhausted = next(model for model in pool.models if model.model_id == first)
    assert not pool.offered(exhausted, "extraction")


def test_twenty_per_day_models_keep_a_twelve_request_reserve(tmp_path: Path) -> None:
    clock = FakeClock()
    pool = _pool(
        tmp_path / "reserved",
        clock,
        ["Gemini 3.1 Flash Lite", "Gemini 2.5 Flash"],
        lambda *_: "{}",
    )
    small = _model_id("Gemini 2.5 Flash")
    for _ in range(8):
        pool.usage.increment(small)
    assert pool.remaining_today(pool.models[1]) == 12
    assert small not in [model.model_id for model in pool.candidates("extraction", 1_000)]
    assert small in [model.model_id for model in pool.candidates("quality", 1_000)]

    open_pool = _pool(
        tmp_path / "open",
        FakeClock(),
        ["Gemini 3.1 Flash Lite", "Gemini 2.5 Flash"],
        lambda *_: "{}",
    )
    for _ in range(7):
        open_pool.usage.increment(small)
    assert open_pool.remaining_today(open_pool.models[1]) == 13
    assert small in [model.model_id for model in open_pool.candidates("extraction", 1_000)]


def test_pacific_date_rollover_resets_and_persists_counts(tmp_path: Path) -> None:
    day = {"value": "2026-11-22"}
    path = tmp_path / "usage.json"
    store = UsageStore(path, today=lambda: day["value"])
    store.increment("model-a")
    assert store.used("model-a") == 1

    day["value"] = "2026-11-23"
    assert store.used("model-a") == 0
    store.increment("model-a")
    store.save()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"date": "2026-11-23", "counts": {"model-a": 1}}


def test_pacific_midnight_governs_the_usage_date() -> None:
    assert pacific_today(datetime(2026, 11, 23, 6, 30, tzinfo=UTC)) == "2026-11-22"
    assert pacific_today(datetime(2026, 11, 23, 8, 30, tzinfo=UTC)) == "2026-11-23"


def test_model_names_resolve_by_normalized_words() -> None:
    available = [
        ("gemini-3.1-flash-lite", True),
        ("gemini-3.5-flash-lite", True),
        ("gemini-2.5-flash-lite", True),
        ("gemini-2.5-flash", True),
        ("gemini-3-flash", True),
        ("gemini-3.6-flash", True),
        ("gemini-3.8-flash", True),
        ("gemini-4-hydrogen", False),
    ]
    assert resolve_model_id("Gemini 3.1 Flash Lite", available) == "gemini-3.1-flash-lite"
    assert resolve_model_id("Gemini 3.5 Flash Lite", available) == "gemini-3.5-flash-lite"
    assert resolve_model_id("Gemini 2.5 Flash Lite", available) == "gemini-2.5-flash-lite"
    assert resolve_model_id("Gemini 2.5 Flash", available) == "gemini-2.5-flash"
    assert resolve_model_id("Gemini 3 Flash", available) == "gemini-3-flash"
    assert resolve_model_id("Gemini 4 Hydrogen", available) is None
    assert resolve_model_id("Gemini 2.5 Pro", available) is None


def test_a_different_version_never_satisfies_a_display_name() -> None:
    available = [("gemini-3.5-flash", True), ("gemini-3.1-flash-lite", True)]
    assert resolve_model_id("Gemini 3 Flash", available) is None
    assert resolve_model_id("Gemini 3.6 Flash", available) is None


def test_preview_and_build_suffixes_still_resolve() -> None:
    available = [("gemini-2.5-flash-preview-05-20", True)]
    assert resolve_model_id("Gemini 2.5 Flash", available) == "gemini-2.5-flash-preview-05-20"


@pytest.mark.skipif(
    not hasattr(types, "ThinkingLevel"),
    reason="installed google-genai has no ThinkingLevel enum",
)
def test_thinking_level_downgrades_then_is_dropped(tmp_path: Path) -> None:
    clock = FakeClock()
    seen: list[Any] = []

    def handler(model_id: str, contents: Any, config: dict[str, Any]) -> str:
        thinking = config.get("thinking_config")
        seen.append(getattr(thinking, "thinking_level", None))
        if thinking is not None:
            raise FakeStatusError("400 thinking_level is not supported for this model", 400)
        return json.dumps({"ok": True})

    pool = _pool(tmp_path, clock, ["Gemini 3.8 Flash"], handler)
    model = pool.models[0]
    asyncio.run(
        pool.generate_json(
            "prompt",
            {"type": "object"},
            GeminiBudget(10),
            tier="quality",
            thinking_level=types.ThinkingLevel.MINIMAL,
        )
    )
    assert model.thinking == "off"
    assert seen == [
        types.ThinkingLevel.MINIMAL,
        types.ThinkingLevel.LOW,
        None,
    ]


@pytest.mark.skipif(
    not hasattr(types, "ThinkingLevel"),
    reason="installed google-genai has no ThinkingLevel enum",
)
def test_thinking_minimal_falls_back_to_low(tmp_path: Path) -> None:
    clock = FakeClock()
    seen: list[Any] = []

    def handler(model_id: str, contents: Any, config: dict[str, Any]) -> str:
        thinking = config.get("thinking_config")
        level = getattr(thinking, "thinking_level", None)
        seen.append(level)
        if level == types.ThinkingLevel.MINIMAL:
            raise FakeStatusError("400 thinking_level MINIMAL is not supported", 400)
        return json.dumps({"ok": True})

    pool = _pool(tmp_path, clock, ["Gemini 3.8 Flash"], handler)
    asyncio.run(
        pool.generate_json(
            "prompt",
            {"type": "object"},
            GeminiBudget(10),
            tier="quality",
            thinking_level=types.ThinkingLevel.MINIMAL,
        )
    )
    assert pool.models[0].thinking == "low"
    assert seen == [types.ThinkingLevel.MINIMAL, types.ThinkingLevel.LOW]


def test_schema_rejection_moves_the_schema_into_the_prompt(tmp_path: Path) -> None:
    clock = FakeClock()
    seen: list[dict[str, Any]] = []

    def handler(model_id: str, contents: Any, config: dict[str, Any]) -> str:
        seen.append({"config": dict(config), "contents": contents})
        if "response_json_schema" in config:
            raise FakeStatusError("400 response_json_schema is not supported", 400)
        return json.dumps({"ok": True})

    pool = _pool(tmp_path, clock, ["Gemini 3.1 Flash Lite"], handler)
    data = asyncio.run(pool.generate_json("prompt", {"type": "object"}, GeminiBudget(10)))
    assert data == {"ok": True}
    assert pool.models[0].json_schema is False
    assert "response_json_schema" not in seen[-1]["config"]
    assert "JSON Schema" in str(seen[-1]["contents"])


def test_batch_omission_retries_that_page_on_another_model(tmp_path: Path) -> None:
    class FakePool:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def generate_json_with_model(
            self, prompt: str, schema: dict[str, Any], budget: GeminiBudget, **kwargs: Any
        ) -> tuple[Any, str]:
            self.calls.append({"schema": schema, "kwargs": kwargs})
            if "pages" in schema.get("properties", {}):
                return (
                    {
                        "pages": [
                            {
                                "pageIndex": 1,
                                "isListPage": False,
                                "programs": [{"name": "Award One"}],
                                "followLinks": [],
                            }
                        ]
                    },
                    "model-a",
                )
            return (
                {
                    "isListPage": False,
                    "programs": [{"name": "Award Two"}],
                    "followLinks": [],
                },
                "model-b",
            )

    fake = FakePool()
    set_pool(fake)  # type: ignore[arg-type]
    try:
        pages = [
            Page(url="https://one.example/awards", final_url="https://one.example/awards", title="A", text="alpha"),
            Page(url="https://two.example/awards", final_url="https://two.example/awards", title="B", text="beta"),
        ]
        batch = asyncio.run(extract_pages(pages, _profile(), "", GeminiBudget(10)))
    finally:
        set_pool(None)

    assert batch.calls == 2
    assert batch.models == ("model-a", "model-b")
    assert [result.page.url for result in batch.pages] == [
        "https://one.example/awards",
        "https://two.example/awards",
    ]
    assert [result.model_id for result in batch.pages] == ["model-a", "model-b"]
    assert [program.name for result in batch.pages for program in result.programs] == [
        "Award One",
        "Award Two",
    ]
    assert fake.calls[1]["kwargs"]["avoid_model"] == "model-a"


def test_begin_run_resets_per_run_counters_but_keeps_the_window(tmp_path: Path) -> None:
    clock = FakeClock()
    pool = _pool(tmp_path, clock, ["Gemini 3.1 Flash Lite"], lambda *_: "{}")
    pacer = pool.models[0].pacer
    for _ in range(pacer.rpm_limit):
        pacer.record(clock(), 1_000)
    pool.failovers = 3
    pool.rate_limit_messages = {"429": 2}
    pool.begin_run()
    assert pool.failovers == 0
    assert pool.rate_limit_messages == {}
    assert pacer.requests == 0
    assert pacer.wait_seconds(clock(), 1_000) > 0


def test_every_model_exhausted_raises_the_daily_limit_message(tmp_path: Path) -> None:
    clock = FakeClock()
    pool = _pool(
        tmp_path,
        clock,
        ["Gemini 3.1 Flash Lite", "Gemini 3.5 Flash Lite"],
        lambda *_: "{}",
    )
    for model in pool.models:
        pool.usage.mark_exhausted(model.model_id, model.spec.rpd)
    with pytest.raises(GeminiPoolExhausted) as caught:
        asyncio.run(pool.generate_json("prompt", {"type": "object"}, GeminiBudget(10)))
    assert str(caught.value) == DAILY_LIMIT_MESSAGE
    assert DAILY_LIMIT_MESSAGE == "Gemini daily limit reached; showing the results found so far"
