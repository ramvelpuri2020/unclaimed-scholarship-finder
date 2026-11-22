"""Hunt orchestration: scoring, continuous rounds, streaming and persistence.

Candidates are only ever ordered, never dropped. A supervisor starts a new
round the moment both queues drain, so a hunt finishes as soon as its supply is
exhausted instead of idling to the wall clock.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import json
import logging
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import ValidationError

from . import diagnostics
from .agents import FatalHuntError
from .cleaning import strip_private_use
from .config import settings
from .models import (
    HuntCompleteEvent,
    HuntErrorEvent,
    HuntEventBase,
    Profile,
    Program,
    ProgramFoundEvent,
    SiteDoneEvent,
    SiteProgressEvent,
    SiteStartedEvent,
    event_json,
    utc_now,
)
from .pipeline.discovery import (
    Candidate,
    discover,
    is_blocked_url,
    normalise_url,
)
from .pipeline.extractor import ExtractedPage, extract_pages
from .pipeline.gemini import (
    GeminiBudget,
    GeminiBudgetExceeded,
    GeminiError,
    GeminiModelError,
    GeminiPoolExhausted,
    RateLimitGate,
)
from .pipeline.matcher import build_program
from .pipeline.model_pool import DAILY_LIMIT_MESSAGE, get_pool
from .pipeline.page_selector import neutral_order, score_candidates
from .pipeline.planner import PlannedQuery, plan_queries, unverified_based_on_count
from .pipeline.prefilter import prefilter_reason
from .pipeline.reader import Page, PageReader, reading_label
from .pipeline.resume_text import compact_resume_text, prepare_resume_text
from .pipeline.verify import VerifyState, verify_pages
from .summary import drops_message

logger = logging.getLogger(__name__)

HUNTS_DIR: Path = Path(__file__).resolve().parents[1] / "data" / "hunts"
FIT_ORDER = {"strong": 0, "good": 1, "weak": 2}
ALLOWED_STOP_REASONS = frozenset(
    {"target_met", "exhausted", "wall_clock", "gemini_call_budget", "gemini_daily_limit"}
)
SUPERVISOR_INTERVAL = 0.5
NEXT_ROUND_MIN_REMAINING = 30.0
NEXT_ROUND_MIN_CALLS = 8
ROUND_1_QUERIES = 16
LATER_ROUND_QUERIES = 12
ROUND_SCHEDULE = (0.0, 35.0, 70.0, 105.0)
PLANNER_TIMEOUT_SECONDS = 45.0
PLANNER_OUTER_SECONDS = 50.0
MAX_PLANNING_FAILURES = 3
SELECTOR_TIMEOUT_SECONDS = 40.0
PACE_NOTICE_SECONDS = 20.0
PENDING_PAGE_LIMIT = 48
WORKER_IDLE_SLEEP = 0.1
MAX_ANGLE_ROWS = 40

Status = Literal["running", "complete", "error"]


@dataclass(frozen=True)
class QueuedUrl:
    url: str
    depth: int = 0
    score: int = 0
    angle: str = ""
    based_on: str = ""
    round: int = 0


class UrlQueue:
    """A deduplicated priority queue: highest candidate score first."""

    def __init__(self) -> None:
        self._items: list[tuple[int, int, QueuedUrl]] = []
        self._sequence = itertools.count()
        self._condition = asyncio.Condition()
        self.in_flight = 0

    async def put(self, items: list[QueuedUrl]) -> None:
        if not items:
            return
        async with self._condition:
            for item in items:
                heapq.heappush(self._items, (-item.score, next(self._sequence), item))
            self._condition.notify_all()

    async def take(self, size: int) -> list[QueuedUrl]:
        async with self._condition:
            batch: list[QueuedUrl] = []
            while self._items and len(batch) < size:
                batch.append(heapq.heappop(self._items)[2])
            self.in_flight += len(batch)
            return batch

    async def done(self, count: int = 1) -> None:
        async with self._condition:
            self.in_flight = max(0, self.in_flight - count)
            self._condition.notify_all()

    async def reprioritize(self, scores: dict[str, int]) -> None:
        """Re-heap queued URLs from late Gemini scores; in-flight items are kept."""

        if not scores:
            return
        async with self._condition:
            updated: list[tuple[int, int, QueuedUrl]] = []
            for _, sequence, item in self._items:
                score = scores.get(item.url)
                if score is not None and int(score) != item.score:
                    item = replace(item, score=int(score))
                updated.append((-item.score, sequence, item))
            heapq.heapify(updated)
            self._items = updated
            self._condition.notify_all()

    def qsize(self) -> int:
        return len(self._items)


class PageQueue:
    """A priority queue of fetched pages ordered by their candidate score."""

    def __init__(self) -> None:
        self._items: list[tuple[int, int, Page]] = []
        self._sequence = itertools.count()
        self._condition = asyncio.Condition()
        self.in_flight = 0

    async def put(self, page: Page) -> None:
        async with self._condition:
            heapq.heappush(self._items, (-page.score, next(self._sequence), page))
            self._condition.notify_all()

    async def take(self) -> Page | None:
        async with self._condition:
            if not self._items:
                return None
            page = heapq.heappop(self._items)[2]
            self.in_flight += 1
            return page

    async def take_many(self, size: int) -> list[Page]:
        async with self._condition:
            batch: list[Page] = []
            while self._items and len(batch) < size:
                batch.append(heapq.heappop(self._items)[2])
            self.in_flight += len(batch)
            return batch

    async def done(self, count: int = 1) -> None:
        async with self._condition:
            self.in_flight = max(0, self.in_flight - count)
            self._condition.notify_all()

    def qsize(self) -> int:
        return len(self._items)

    def pending(self) -> int:
        return len(self._items) + self.in_flight


@dataclass
class HuntState:
    hunt_id: str
    profile: Profile
    resume_compact: str = ""
    resume_text: str = ""
    started: float = 0.0
    started_at_iso: str = ""
    events: list[str] = field(default_factory=list)
    queued_urls: set[str] = field(default_factory=set)
    backlog: list[QueuedUrl] = field(default_factory=list)
    results: list[Program] = field(default_factory=list)
    unconfirmed: list[Program] = field(default_factory=list)
    seen: dict[tuple[str, str], Program] = field(default_factory=dict)
    seen_urls: set[str] = field(default_factory=set)
    stats: dict[str, Any] = field(default_factory=dict)
    status: Status = "running"
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
    runner: asyncio.Task[None] | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    commit_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    verify_state: VerifyState = field(default_factory=VerifyState)
    rate_gate: RateLimitGate | None = None
    active_fetches: int = 0
    active_extractions: int = 0
    active_round: int = 0
    last_pacing_notice: float = 0.0

    def subscribe(self) -> tuple[list[str], asyncio.Queue[str | None]]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        if self.status == "running":
            self.subscribers.add(queue)
        return list(self.events), queue

    def unsubscribe(self, queue: asyncio.Queue[str | None]) -> None:
        self.subscribers.discard(queue)


def _empty_stats() -> dict[str, Any]:
    return {
        "queries": 0,
        "candidates": 0,
        "selected_pages": 0,
        "pages_queued": 0,
        "fetched": 0,
        "fetch_errors": 0,
        "reader_tinyfish": 0,
        "reader_http": 0,
        "unreadable_pages": 0,
        "tinyfish_limit_errors": 0,
        "prefiltered": {},
        "sent_to_extraction": 0,
        "extraction_calls": 0,
        "extraction_failures": 0,
        "zero_program_calls": 0,
        "extraction_seconds": [],
        "extraction_pages": [],
        "extraction_models": [],
        "average_pages_per_extraction_call": 0.0,
        "results_by_model": {},
        "models_used": {},
        "gemini": {},
        "pacing_notices": 0,
        "chunks": 0,
        "followed_links": 0,
        "extracted": 0,
        "verified": 0,
        "unconfirmed": 0,
        "matched": 0,
        "dropped": {},
        "weak_fit_examples": [],
        "weak_reasons": {},
        "rescued_deadlines": [],
        "rounds": [],
        "angle_outcomes": {},
        "max_rounds": settings.max_rounds,
        "planning_failures": 0,
        "gemini_calls": 0,
        "rate_limit": {},
        "effective_extract_concurrency": None,
        "stop_reason": None,
        "elapsed_seconds": None,
        "first_fetch_seconds": None,
        "first_extract_seconds": None,
        "first_verified_seconds": None,
        "result_seconds": [],
        "list_agent": None,
    }


def _state_key(name: str, provider: str) -> tuple[str, str]:
    """Normalized identity used to merge tiers: name plus provider."""

    def normalise(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    return (normalise(name), normalise(provider))


def _program_rank(program: Program) -> tuple[int, float]:
    """Lower is better: tier A first, then the higher-confidence entry."""

    return (1 if program.verification == "unconfirmed" else 0, -program.confidence)


def _round_records(state: HuntState) -> list[dict[str, Any]]:
    rounds = state.stats.get("rounds")
    if not isinstance(rounds, list):
        rounds = []
        state.stats["rounds"] = rounds
    return rounds


def _current_round(state: HuntState) -> dict[str, Any] | None:
    rounds = _round_records(state)
    if 0 <= state.active_round < len(rounds):
        return rounds[state.active_round]
    return None


def _round_record(state: HuntState, round_number: int | None) -> dict[str, Any] | None:
    if round_number is None:
        return _current_round(state)
    for record in _round_records(state):
        if int(record.get("round", 0)) == int(round_number):
            return record
    return None


def _bump_round(
    state: HuntState,
    key: str,
    amount: int = 1,
    round_number: int | None = None,
) -> None:
    record = _round_record(state, round_number)
    if record is not None:
        record[key] = int(record.get(key, 0)) + amount


def _angle_outcomes(state: HuntState) -> dict[str, dict[str, int]]:
    table = state.stats.get("angle_outcomes")
    if not isinstance(table, dict):
        table = {}
        state.stats["angle_outcomes"] = table
    return table


def _bump_angle(state: HuntState, angle: str, key: str, amount: int = 1) -> None:
    name = angle.strip() or "unspecified"
    table = _angle_outcomes(state)
    row = table.get(name)
    if not isinstance(row, dict):
        row = {"queries": 0, "candidates": 0, "read": 0, "extracted": 0, "verified": 0}
        table[name] = row
    row[key] = int(row.get(key, 0)) + amount


def _angle_table(state: HuntState) -> list[dict[str, Any]]:
    table = _angle_outcomes(state)
    rows: list[dict[str, Any]] = []
    for angle, row in table.items():
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "angle": angle,
                "queries": int(row.get("queries", 0)),
                "candidates": int(row.get("candidates", 0)),
                "read": int(row.get("read", 0)),
                "extracted": int(row.get("extracted", 0)),
                "verified": int(row.get("verified", 0)),
            }
        )
    rows.sort(key=lambda item: (-int(item["extracted"]), str(item["angle"])))
    return rows[:MAX_ANGLE_ROWS]


def _merge_weak_reason(stats: dict[str, Any], reason: str) -> None:
    text = strip_private_use(reason).strip()
    if not text:
        return
    counts = stats.get("weak_reasons")
    if not isinstance(counts, dict):
        counts = {}
        stats["weak_reasons"] = counts
    counts[text] = int(counts.get(text, 0)) + 1


def _top_weak_reasons(state: HuntState) -> list[str]:
    counts = state.stats.get("weak_reasons")
    if not isinstance(counts, dict):
        return []
    ranked = sorted(counts.items(), key=lambda item: -int(item[1]))
    return [f"{text} ({count})" for text, count in ranked[:10]]


def publish(state: HuntState, event: HuntEventBase) -> None:
    """Append an event, fan it out, and close subscribers on a terminal event."""

    if state.status != "running":
        return
    stamped = event.model_copy(
        update={"t": round(max(0.0, time.perf_counter() - state.started), 1)}
    )
    line = event_json(stamped)
    state.events.append(line)
    for queue in list(state.subscribers):
        queue.put_nowait(line)
    if event.type == "hunt_complete":
        state.status = "complete"
        _close_subscribers(state)
    elif event.type == "hunt_error":
        state.status = "error"
        _close_subscribers(state)


def _close_subscribers(state: HuntState) -> None:
    for queue in list(state.subscribers):
        queue.put_nowait(None)
    state.subscribers.clear()


def _persist(state: HuntState) -> None:
    if state.status == "running":
        return
    HUNTS_DIR.mkdir(parents=True, exist_ok=True)
    path = HUNTS_DIR / f"{state.hunt_id}.json"
    temporary = path.with_suffix(".tmp")
    payload = {
        "huntId": state.hunt_id,
        "status": state.status,
        "startedAt": state.started_at_iso,
        "events": state.events,
        "results": [program.model_dump(mode="json", by_alias=True) for program in state.results],
        "unconfirmed": [
            program.model_dump(mode="json", by_alias=True) for program in state.unconfirmed
        ],
        "stats": state.stats,
    }
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        logger.warning("Could not persist hunt %s: %s", state.hunt_id, exc)


def _load_persisted(hunt_id: str) -> HuntState | None:
    path = HUNTS_DIR / f"{hunt_id}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read persisted hunt %s: %s", hunt_id, exc)
        return None
    persisted_status = payload.get("status")
    status: Status = "complete" if persisted_status == "complete" else "error"
    events = [line for line in payload.get("events", []) if isinstance(line, str)]
    results: list[Program] = []
    for item in payload.get("results", []):
        try:
            results.append(Program.model_validate(item))
        except ValidationError as exc:
            logger.warning("Skipping invalid persisted program in %s: %s", hunt_id, exc)
    unconfirmed: list[Program] = []
    for item in payload.get("unconfirmed", []):
        try:
            unconfirmed.append(Program.model_validate(item))
        except ValidationError as exc:
            logger.warning("Skipping invalid persisted program in %s: %s", hunt_id, exc)
    stats = payload.get("stats")
    return HuntState(
        hunt_id=hunt_id,
        profile=Profile(
            full_name="",
            province="",
            school="",
            field="",
            year="",
            income_range="",
            status="",
        ),
        events=events,
        results=results,
        unconfirmed=unconfirmed,
        stats=stats if isinstance(stats, dict) else _empty_stats(),
        status=status,
        started_at_iso=str(payload.get("startedAt") or ""),
    )


def _merge_drops(stats: dict[str, Any], dropped: dict[str, int]) -> None:
    aggregate = stats.get("dropped")
    if not isinstance(aggregate, dict):
        aggregate = {}
        stats["dropped"] = aggregate
    for reason, count in dropped.items():
        aggregate[reason] = int(aggregate.get(reason, 0)) + count


def _merge_prefilter(stats: dict[str, Any], reason: str) -> None:
    aggregate = stats.get("prefiltered")
    if not isinstance(aggregate, dict):
        aggregate = {}
        stats["prefiltered"] = aggregate
    aggregate[reason] = int(aggregate.get(reason, 0)) + 1
    _merge_drops(stats, {reason: 1})


def _sort_results(results: list[Program]) -> list[Program]:
    return sorted(
        results,
        key=lambda program: (
            FIT_ORDER.get(program.fit, 3),
            -program.confidence,
            -(program.amount_max or 0),
            program.name.lower(),
        ),
    )


class HuntManager:
    """In-memory hunt registry with a JSON file for finished hunts."""

    def __init__(self) -> None:
        self._hunts: dict[str, HuntState] = {}

    def get(self, hunt_id: str) -> HuntState | None:
        state = self._hunts.get(hunt_id)
        if state is not None:
            return state
        state = _load_persisted(hunt_id)
        if state is not None:
            self._hunts[hunt_id] = state
        return state

    def start(self, profile: Profile) -> str:
        hunt_id = uuid4().hex[:12]
        state = HuntState(hunt_id=hunt_id, profile=profile, stats=_empty_stats())
        self._hunts[hunt_id] = state
        state.runner = asyncio.create_task(self._run(state))
        logger.info("hunt=%s created", hunt_id)
        return hunt_id

    async def _run(self, state: HuntState) -> None:
        started = time.perf_counter()
        state.started = started
        state.started_at_iso = utc_now().isoformat()
        recorder = diagnostics.begin(state.hunt_id, state.started_at_iso)
        deadline = started + settings.wall_timeout_seconds
        budget = GeminiBudget(settings.max_gemini_calls)
        gate = RateLimitGate(settings.extract_concurrency)
        state.rate_gate = gate
        pool = get_pool()
        if pool is not None:
            pool.begin_run()
        try:
            await self._execute(state, started, deadline, budget, gate)
        except FatalHuntError as exc:
            self._abort(state, str(exc))
        except GeminiPoolExhausted:
            self._request_stop(state, "gemini_daily_limit", DAILY_LIMIT_MESSAGE)
        except GeminiModelError as exc:
            self._abort(state, str(exc))
        except GeminiBudgetExceeded:
            self._request_stop(state, "gemini_call_budget", "Gemini call budget used; finishing with committed results")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("hunt=%s crashed", state.hunt_id)
            self._abort(state, f"The hunt could not finish: {exc}")
        finally:
            state.stats["gemini_calls"] = budget.used
            snapshot = gate.snapshot()
            state.stats["rate_limit"] = snapshot
            state.stats["effective_extract_concurrency"] = snapshot["effective_limit"]
            pool = get_pool()
            if pool is not None:
                state.stats["gemini"] = pool.snapshot()
            snapshot_models = state.stats.get("gemini")
            recorder.record_models(snapshot_models if isinstance(snapshot_models, dict) else None)

        if state.status == "running":
            self._finish(state, started)
        _persist(state)
        recorder.finish(str(state.stats.get("stop_reason") or ""))
        try:
            recorder.write()
        except OSError as exc:
            logger.warning("Could not write diagnostics for %s: %s", state.hunt_id, exc)
        diagnostics.clear()

    async def _execute(
        self,
        state: HuntState,
        started: float,
        deadline: float,
        budget: GeminiBudget,
        gate: RateLimitGate,
    ) -> None:
        self._start_stages(state)
        self._maybe_pacing_notice(state, force=True)
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            self._request_stop(state, "wall_clock")
            return

        resume = state.profile.resume
        recorder = diagnostics.active()
        used_ocr = False
        if resume is not None:
            if recorder is not None:
                recorder.stage_start("resume_local")
            try:
                state.resume_text, used_ocr = await asyncio.wait_for(
                    prepare_resume_text(resume, budget),
                    timeout=min(60.0, max(1.0, deadline - time.perf_counter())),
                )
                if recorder is not None:
                    recorder.stage_end(
                        "resume_local", result=f"chars={len(state.resume_text)}"
                    )
            except Exception as exc:  # noqa: BLE001 - a local read must not stop the hunt
                logger.warning(
                    "Could not prepare resume text: %s", exc.__class__.__name__
                )
                state.resume_text = ""
                if recorder is not None:
                    recorder.stage_end("resume_local", result="failed", success=False)

            state.resume_compact = compact_resume_text(
                state.resume_text, settings.resume_extract_chars
            )
            if state.resume_text:
                self._progress(
                    state,
                    "search",
                    f"Resume read: {len(state.resume_text)} characters",
                )
                if used_ocr:
                    logger.info(
                        "Resume read with OCR characters=%d", len(state.resume_text)
                    )
            else:
                self._progress(
                    state,
                    "search",
                    "Your resume could not be read; searching with your profile only",
                )
            logger.info(
                "Resume text characters=%d compact=%d",
                len(state.resume_text),
                len(state.resume_compact),
            )

        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            self._request_stop(state, "wall_clock")
            return

        url_queue = UrlQueue()
        page_queue = PageQueue()

        def reader_limit_notice() -> None:
            self._progress(
                state,
                "read",
                "TinyFish Fetch limit reached; reading pages directly",
                count=int(state.stats.get("fetched", 0)),
            )

        reader = PageReader(on_limit=reader_limit_notice)
        fetch_tasks = [
            asyncio.create_task(self._fetch_worker(state, url_queue, page_queue, started, reader))
            for _ in range(settings.fetch_concurrency)
        ]
        extract_tasks = [
            asyncio.create_task(
                self._extract_worker(state, page_queue, url_queue, started, budget, gate)
            )
            for _ in range(settings.extract_concurrency)
        ]
        supervisor = asyncio.create_task(
            self._supervise(state, started, deadline, budget, gate, url_queue, page_queue)
        )
        stop_task = asyncio.create_task(state.stop_event.wait())
        workers: list[asyncio.Task[Any]] = [*fetch_tasks, *extract_tasks]

        try:
            wait_seconds = max(0.0, deadline - time.perf_counter())
            watched = [*workers, supervisor, stop_task]
            done: set[asyncio.Task[Any]] = set()
            if wait_seconds > 0:
                done, _pending = await asyncio.wait(
                    watched,
                    timeout=wait_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            for task in done:
                if task is stop_task:
                    continue
                exception = task.exception()
                if exception is None:
                    continue
                if isinstance(exception, (FatalHuntError, GeminiModelError, GeminiBudgetExceeded)):
                    raise exception
                logger.error("hunt=%s task failed: %s", state.hunt_id, exception)
                self._request_stop(
                    state,
                    "exhausted",
                    "A worker stopped unexpectedly; finishing with committed results",
                )

            if state.stop_event.is_set():
                if not state.stats.get("stop_reason"):
                    state.stats["stop_reason"] = "target_met"
            else:
                self._request_stop(state, "wall_clock")
        finally:
            watched_tasks: list[asyncio.Task[Any]] = [*workers, supervisor, stop_task]
            watched_tasks.extend(state.tasks.values())
            for task in watched_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*watched_tasks, return_exceptions=True)
            await reader.aclose()
            state.tasks = {}

    def _drained(self, state: HuntState, url_queue: UrlQueue, page_queue: PageQueue) -> bool:
        return (
            url_queue.qsize() == 0
            and url_queue.in_flight == 0
            and page_queue.qsize() == 0
            and page_queue.in_flight == 0
            and state.active_fetches == 0
            and state.active_extractions == 0
        )

    async def _wait_for_drain(
        self,
        state: HuntState,
        deadline: float,
        url_queue: UrlQueue,
        page_queue: PageQueue,
    ) -> None:
        while not state.stop_event.is_set():
            if self._drained(state, url_queue, page_queue):
                return
            if deadline - time.perf_counter() <= 0:
                return
            await asyncio.sleep(SUPERVISOR_INTERVAL)

    async def _supervise(
        self,
        state: HuntState,
        started: float,
        deadline: float,
        budget: GeminiBudget,
        gate: RateLimitGate,
        url_queue: UrlQueue,
        page_queue: PageQueue,
    ) -> None:
        """Start rounds at 0, 35, 70 and 105 seconds when supply allows.

        A round whose planning spends its whole budget without returning queries
        is a planning failure, not a round: at most three are allowed per hunt,
        and a timed round only starts after a round that produced candidates.
        """

        rounds_done = 0
        planning_failures = 0
        while not state.stop_event.is_set():
            if rounds_done >= settings.max_rounds:
                await self._wait_for_drain(state, deadline, url_queue, page_queue)
                self._request_stop(state, "exhausted", "All planned rounds finished")
                return

            target = ROUND_SCHEDULE[min(rounds_done, len(ROUND_SCHEDULE) - 1)]
            while not state.stop_event.is_set():
                until_start = target - (time.perf_counter() - started)
                if until_start <= 0:
                    break
                await asyncio.sleep(min(SUPERVISOR_INTERVAL, until_start))
                self._maybe_pacing_notice(state)
            if state.stop_event.is_set():
                return

            records = _round_records(state)
            if rounds_done > 0 and records:
                if int(records[-1].get("candidates", 0)) <= 0:
                    self._request_stop(
                        state,
                        "exhausted",
                        "The previous round produced no candidates",
                    )
                    return
                if self._total_results(state) >= settings.stop_at_results:
                    self._request_stop(state, "target_met")
                    return
                if deadline - time.perf_counter() < NEXT_ROUND_MIN_REMAINING:
                    self._request_stop(state, "exhausted", "Not enough time left for another round")
                    return
                if budget.remaining < NEXT_ROUND_MIN_CALLS:
                    self._request_stop(state, "exhausted", "Gemini budget is spent")
                    return

            outcome = await self._run_round(
                state, rounds_done + 1, budget, gate, deadline, url_queue
            )
            if state.stop_event.is_set():
                return
            if outcome == "planned":
                rounds_done += 1
            else:
                planning_failures += 1
                state.stats["planning_failures"] = planning_failures
                if planning_failures >= MAX_PLANNING_FAILURES:
                    self._request_stop(
                        state,
                        "exhausted",
                        "Search planning failed repeatedly",
                    )
                    return
            if len(state.results) >= settings.stop_at_results:
                self._request_stop(state, "target_met")
                return

    async def _plan_once(
        self,
        state: HuntState,
        round_number: int,
        count: int,
        budget: GeminiBudget,
        gate: RateLimitGate,
        deadline: float,
        *,
        avoid_model: str | None = None,
    ) -> tuple[list[PlannedQuery], str | None]:
        """One planning attempt, retried once on a different model on failure."""

        avoid = avoid_model
        last_error: BaseException | None = None
        for _attempt in range(2):
            last_error = None
            remaining = deadline - time.perf_counter()
            timeout = max(5.0, min(PLANNER_TIMEOUT_SECONDS, remaining - 3.0))
            outer = max(timeout + 5.0, min(PLANNER_OUTER_SECONDS, remaining))
            try:
                queries = await asyncio.wait_for(
                    plan_queries(
                        state.profile,
                        state.resume_text,
                        budget,
                        round_number=round_number,
                        verified_count=len(state.results),
                        providers=[program.provider for program in state.results],
                        weak_reasons=_top_weak_reasons(state),
                        angle_table=_angle_table(state),
                        previous_angles=list(_angle_outcomes(state)),
                        count=count,
                        timeout=timeout,
                        gate=gate,
                        avoid_model=avoid,
                    ),
                    timeout=outer,
                )
            except (GeminiModelError, GeminiPoolExhausted, GeminiBudgetExceeded):
                raise
            except GeminiError as exc:
                last_error = exc
                logger.warning("Round %d planning attempt failed: %s", round_number, exc)
            except TimeoutError as exc:
                last_error = exc
                self._progress(
                    state,
                    "search",
                    f"Round {round_number}: planning timed out; retrying on another model",
                )
            recorder = diagnostics.active()
            used = recorder.model_for_stage("planner") if recorder is not None else None
            if last_error is None:
                return queries, used
            if used:
                avoid = used
            if deadline - time.perf_counter() <= 3.0:
                break
        if last_error is None:
            return [], None
        raise last_error

    async def _run_round(
        self,
        state: HuntState,
        round_number: int,
        budget: GeminiBudget,
        gate: RateLimitGate,
        deadline: float,
        url_queue: UrlQueue,
    ) -> str:
        recorder = diagnostics.active()
        remaining = deadline - time.perf_counter()
        if remaining <= 5.0:
            self._request_stop(state, "wall_clock")
            return "skipped"
        count = ROUND_1_QUERIES if round_number == 1 else LATER_ROUND_QUERIES
        self._progress(
            state,
            "search",
            f"Round {round_number}: planning {count} scholarship queries",
            count=0,
        )
        if recorder is not None:
            recorder.stage_start(f"round_{round_number}_planning")

        queries: list[PlannedQuery] = []
        used_model: str | None = None
        try:
            queries, used_model = await self._plan_once(
                state, round_number, count, budget, gate, deadline
            )
        except TimeoutError:
            queries = []
            self._progress(
                state,
                "search",
                f"Round {round_number}: planning timed out",
            )
        except GeminiBudgetExceeded:
            self._request_stop(state, "gemini_call_budget")
            return "failed"
        except GeminiPoolExhausted:
            self._request_stop(state, "gemini_daily_limit", DAILY_LIMIT_MESSAGE)
            return "failed"
        except GeminiModelError:
            raise
        except GeminiError as exc:
            logger.warning("Round %d planning failed: %s", round_number, exc)
            queries = []

        if recorder is not None:
            recorder.stage_end(
                f"round_{round_number}_planning",
                result=f"{len(queries)} queries" if queries else "no queries",
                success=bool(queries),
                model=str(used_model or ""),
            )
        if not queries:
            self._progress(
                state,
                "search",
                f"Round {round_number}: planning produced no queries",
            )
            return "failed"

        record: dict[str, Any] = {
            "round": round_number,
            "queries": 0,
            "candidates": 0,
            "selected": 0,
            "read": 0,
            "prefiltered": 0,
            "sent_to_extraction": 0,
            "extracted": 0,
            "verified": 0,
            "angles": [],
        }
        rounds = _round_records(state)
        rounds.append(record)
        state.active_round = len(rounds) - 1
        record["queries"] = len(queries)
        record["angles"] = sorted({query.angle for query in queries})[:12]
        unverified_based_on = unverified_based_on_count(queries)
        record["basedOnUnverified"] = unverified_based_on
        state.stats["planner_based_on_unverified"] = (
            int(state.stats.get("planner_based_on_unverified", 0)) + unverified_based_on
        )
        logger.info(
            "round=%d basedOn unverified=%d/%d",
            round_number,
            unverified_based_on,
            len(queries),
        )
        state.stats["queries"] = int(state.stats.get("queries", 0)) + len(queries)
        for query in queries:
            _bump_angle(state, query.angle, "queries")
        if queries:
            self._progress(
                state,
                "search",
                f"Round {round_number}: searching {len(queries)} planned queries",
                count=len(queries),
            )

        candidates: list[Candidate] = []
        remaining = deadline - time.perf_counter()
        if recorder is not None:
            recorder.stage_start(f"round_{round_number}_discovery")
        if remaining > 0:
            try:
                candidates = await asyncio.wait_for(
                    discover(queries, state.seen_urls, state.profile),
                    timeout=min(20.0, remaining),
                )
            except TimeoutError:
                candidates = []
            except Exception as exc:  # noqa: BLE001 - a search failure is not fatal
                logger.warning("Round %d discovery failed: %s", round_number, exc)
                candidates = []
        for candidate in candidates:
            state.seen_urls.add(normalise_url(candidate.url))
        record["candidates"] = len(candidates)
        state.stats["candidates"] = int(state.stats.get("candidates", 0)) + len(candidates)
        for candidate in candidates:
            _bump_angle(state, candidate.angle, "candidates")
        if recorder is not None:
            recorder.stage_end(
                f"round_{round_number}_discovery",
                result=f"{len(candidates)} candidates",
                success=bool(candidates),
            )
        self._progress(
            state,
            "search",
            f"Round {round_number}: found {len(candidates)} candidate pages",
            count=len(candidates),
        )

        ordered = neutral_order(candidates)
        claimed = self._claim_candidates(state, ordered, round_number)
        merged = [*state.backlog, *claimed]
        merged.sort(key=lambda item: (-item.score, item.round, item.url))
        limit = settings.max_pages_round_1 if round_number == 1 else settings.max_pages_later
        head = merged[:limit]
        state.backlog = merged[limit:]
        record["selected"] = len(head)
        state.stats["selected_pages"] = int(state.stats.get("selected_pages", 0)) + len(head)
        state.stats["pages_queued"] = int(state.stats.get("pages_queued", 0)) + len(head)
        await url_queue.put(head)
        self._progress(
            state,
            "search",
            (
                f"Round {round_number}: queued {len(head)} of {len(merged)} ranked pages "
                f"({len(state.backlog)} kept for later rounds)"
            ),
            count=len(head),
        )

        if settings.selector_enabled and candidates:
            task = asyncio.create_task(
                self._score_and_reprioritize(
                    state, candidates, url_queue, budget, gate, round_number
                )
            )
            state.tasks[f"selector-{round_number}"] = task
        return "planned"

    async def _score_and_reprioritize(
        self,
        state: HuntState,
        candidates: list[Candidate],
        url_queue: UrlQueue,
        budget: GeminiBudget,
        gate: RateLimitGate,
        round_number: int,
    ) -> None:
        """Gemini scoring that only re-orders URLs still waiting to be fetched."""

        recorder = diagnostics.active()
        name = f"round_{round_number}_selection"
        if recorder is not None:
            recorder.stage_start(name)
        try:
            scores = await asyncio.wait_for(
                score_candidates(
                    candidates,
                    state.profile,
                    state.resume_text,
                    budget,
                    timeout=SELECTOR_TIMEOUT_SECONDS,
                    gate=gate,
                ),
                timeout=SELECTOR_TIMEOUT_SECONDS + 5.0,
            )
        except TimeoutError:
            scores = {}
            self._progress(
                state,
                "search",
                f"Round {round_number}: page scoring timed out; keeping the current order",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - scoring is an optimisation only
            scores = {}
            logger.warning("Round %d page scoring failed: %s", round_number, exc)
        if scores:
            await url_queue.reprioritize(scores)
        if recorder is not None:
            recorder.stage_end(name, result=f"{len(scores)} scored", success=bool(scores))

    def _claim_candidates(
        self,
        state: HuntState,
        candidates: list[Candidate],
        round_number: int,
    ) -> list[QueuedUrl]:
        claimed: list[QueuedUrl] = []
        for candidate in candidates:
            normalized = normalise_url(candidate.url)
            if normalized in state.queued_urls or is_blocked_url(normalized):
                continue
            state.queued_urls.add(normalized)
            claimed.append(
                QueuedUrl(
                    url=normalized,
                    depth=0,
                    score=candidate.score,
                    angle=candidate.angle,
                    based_on=candidate.based_on,
                    round=round_number,
                )
            )
        return claimed

    def _claim_follow_links(
        self,
        state: HuntState,
        page: Page,
        urls: tuple[str, ...],
    ) -> list[QueuedUrl]:
        claimed: list[QueuedUrl] = []
        for url in urls:
            normalized = normalise_url(url)
            if normalized in state.queued_urls or is_blocked_url(normalized):
                continue
            state.queued_urls.add(normalized)
            claimed.append(
                QueuedUrl(
                    url=normalized,
                    depth=1,
                    score=page.score,
                    angle=page.angle,
                    based_on=page.based_on,
                    round=page.round,
                )
            )
        return claimed

    async def _fetch_worker(
        self,
        state: HuntState,
        url_queue: UrlQueue,
        page_queue: PageQueue,
        started: float,
        reader: PageReader,
    ) -> None:
        while not state.stop_event.is_set():
            if page_queue.pending() >= PENDING_PAGE_LIMIT:
                await asyncio.sleep(WORKER_IDLE_SLEEP)
                continue
            batch = await url_queue.take(settings.fetch_batch)
            if not batch:
                await asyncio.sleep(WORKER_IDLE_SLEEP)
                continue
            state.active_fetches += 1
            try:
                for queued in batch:
                    self._progress(
                        state,
                        "read",
                        reading_label(queued.url),
                        count=int(state.stats.get("fetched", 0)),
                    )
                try:
                    result = await reader.fetch_urls([queued.url for queued in batch])
                except Exception as exc:  # noqa: BLE001 - a bad batch must not kill the hunt
                    logger.warning("Fetch worker failed: %s", exc)
                    state.stats["fetch_errors"] = (
                        int(state.stats.get("fetch_errors", 0)) + len(batch)
                    )
                    continue
                state.stats["fetch_errors"] = (
                    int(state.stats.get("fetch_errors", 0)) + result.error_count
                )
                state.stats["reader_tinyfish"] = (
                    int(state.stats.get("reader_tinyfish", 0)) + result.tinyfish_pages
                )
                state.stats["reader_http"] = int(state.stats.get("reader_http", 0)) + result.http_pages
                state.stats["unreadable_pages"] = (
                    int(state.stats.get("unreadable_pages", 0)) + result.unreadable_count
                )
                state.stats["tinyfish_limit_errors"] = reader.tinyfish_limit_errors
                meta = {
                    queued.url: (
                        queued.depth,
                        queued.score,
                        queued.angle,
                        queued.based_on,
                        queued.round,
                    )
                    for queued in batch
                }
                for page in result.pages:
                    normalized = normalise_url(page.url)
                    depth, score, angle, based_on, round_number = meta.get(
                        normalized, (0, page.score, "", "", 0)
                    )
                    page = replace(
                        page,
                        depth=depth,
                        score=score,
                        angle=angle,
                        based_on=based_on,
                        round=round_number,
                    )
                    state.stats["fetched"] = int(state.stats.get("fetched", 0)) + 1
                    _bump_round(state, "read", 1, page.round)
                    _bump_angle(state, page.angle, "read")
                    if state.stats.get("first_fetch_seconds") is None:
                        state.stats["first_fetch_seconds"] = round(time.perf_counter() - started, 2)
                        recorder = diagnostics.active()
                        if recorder is not None:
                            recorder.mark("first_fetch")
                    await page_queue.put(page)
                    self._progress(
                        state,
                        "read",
                        f"Read {urlsplit(page.url).hostname or 'page'}{urlsplit(page.url).path or '/'}",
                        count=int(state.stats.get("fetched", 0)),
                    )
            finally:
                state.active_fetches -= 1
                await url_queue.done(len(batch))

    async def _extract_worker(
        self,
        state: HuntState,
        page_queue: PageQueue,
        url_queue: UrlQueue,
        started: float,
        budget: GeminiBudget,
        gate: RateLimitGate,
    ) -> None:
        while not state.stop_event.is_set():
            if budget.remaining <= 0:
                self._request_stop(
                    state,
                    "gemini_call_budget",
                    "Gemini call budget used; finishing with committed results",
                )
                return
            batch = await page_queue.take_many(settings.extract_pages_per_call)
            if not batch:
                await asyncio.sleep(WORKER_IDLE_SLEEP)
                continue
            state.active_extractions += 1
            pages: list[Page] = []
            try:
                for page in batch:
                    skipped = prefilter_reason(page)
                    if skipped is not None:
                        _merge_prefilter(state.stats, skipped)
                        _bump_round(state, "prefiltered", 1, page.round)
                        continue
                    pages.append(page)
                if not pages:
                    continue

                state.stats["sent_to_extraction"] = int(
                    state.stats.get("sent_to_extraction", 0)
                ) + len(pages)
                for page in pages:
                    _bump_round(state, "sent_to_extraction", 1, page.round)
                call_started = time.perf_counter()
                try:
                    extraction = await extract_pages(
                        pages, state.profile, state.resume_compact, budget, gate
                    )
                except GeminiBudgetExceeded:
                    state.stats["extraction_calls"] = (
                        int(state.stats.get("extraction_calls", 0)) + 1
                    )
                    state.stats["extraction_seconds"].append(
                        round(time.perf_counter() - call_started, 3)
                    )
                    self._request_stop(
                        state,
                        "gemini_call_budget",
                        "Gemini call budget used; finishing with committed results",
                    )
                    return
                except GeminiPoolExhausted:
                    self._request_stop(state, "gemini_daily_limit", DAILY_LIMIT_MESSAGE)
                    return
                except GeminiModelError:
                    raise
                except Exception as exc:  # noqa: BLE001 - one batch must not stop the hunt
                    state.stats["extraction_calls"] = (
                        int(state.stats.get("extraction_calls", 0)) + 1
                    )
                    state.stats["extraction_failures"] = (
                        int(state.stats.get("extraction_failures", 0)) + 1
                    )
                    state.stats["extraction_seconds"].append(
                        round(time.perf_counter() - call_started, 3)
                    )
                    logger.warning(
                        "Extraction worker failed pages=%d: %s", len(pages), exc
                    )
                    continue

                state.stats["extraction_calls"] = int(
                    state.stats.get("extraction_calls", 0)
                ) + max(1, extraction.calls)
                state.stats["extraction_seconds"].append(
                    round(time.perf_counter() - call_started, 3)
                )
                pages_stat = state.stats.setdefault("extraction_pages", [])
                if isinstance(pages_stat, list):
                    pages_stat.append(len(pages))
                models_stat = state.stats.setdefault("extraction_models", [])
                for model_id in extraction.models:
                    if isinstance(models_stat, list) and model_id not in models_stat:
                        models_stat.append(model_id)
                if not extraction.pages:
                    state.stats["extraction_failures"] = (
                        int(state.stats.get("extraction_failures", 0)) + 1
                    )
                    continue

                for extracted in extraction.pages:
                    if state.stop_event.is_set():
                        return
                    state.stats["chunks"] = (
                        int(state.stats.get("chunks", 0)) + extracted.chunks
                    )
                    if not extracted.programs:
                        state.stats["zero_program_calls"] = (
                            int(state.stats.get("zero_program_calls", 0)) + 1
                        )

                    state.stats["extracted"] = int(
                        state.stats.get("extracted", 0)
                    ) + len(extracted.programs)
                    _bump_round(
                        state,
                        "extracted",
                        len(extracted.programs),
                        extracted.page.round,
                    )
                    _bump_angle(
                        state, extracted.page.angle, "extracted", len(extracted.programs)
                    )
                    if state.stats.get("first_extract_seconds") is None:
                        state.stats["first_extract_seconds"] = round(
                            time.perf_counter() - started, 2
                        )
                        recorder = diagnostics.active()
                        if recorder is not None:
                            recorder.mark("first_extraction")

                    await self._commit(state, extracted, started)

                    if extracted.page.depth == 0 and extracted.follow_links:
                        follow = self._claim_follow_links(
                            state, extracted.page, extracted.follow_links
                        )
                        if follow:
                            state.stats["followed_links"] = (
                                int(state.stats.get("followed_links", 0)) + len(follow)
                            )
                            await url_queue.put(follow)
            finally:
                state.active_extractions -= 1
                await page_queue.done(len(batch))

    @staticmethod
    def _total_results(state: HuntState) -> int:
        return len(state.results) + len(state.unconfirmed)

    def _keep_best(self, state: HuntState, program: Program) -> bool:
        """Insert one program, deduped by normalized name plus provider.

        A later tier A copy replaces an earlier tier B one; within a tier the
        higher-confidence entry wins. Returns True for a new program or an
        upgrade, so the caller can publish it.
        """

        key = _state_key(program.name, program.provider)
        existing = state.seen.get(key)
        if existing is not None:
            if _program_rank(program) >= _program_rank(existing):
                _merge_drops(state.stats, {"duplicate": 1})
                return False
            if existing in state.results:
                state.results.remove(existing)
            elif existing in state.unconfirmed:
                state.unconfirmed.remove(existing)
        state.seen[key] = program
        if program.verification == "unconfirmed":
            state.unconfirmed.append(program)
        else:
            state.results.append(program)
        state.stats["verified"] = len(state.results)
        state.stats["unconfirmed"] = len(state.unconfirmed)
        state.stats["matched"] = self._total_results(state)
        return True

    async def _commit(self, state: HuntState, extracted: ExtractedPage, started: float) -> None:
        async with state.commit_lock:
            if state.stop_event.is_set():
                return
            result = verify_pages(
                [extracted],
                state.profile,
                state.verify_state,
                resume_text=state.resume_text,
            )
            _merge_drops(state.stats, result.dropped)
            recorder = diagnostics.active()
            if recorder is not None:
                for record in result.drop_records:
                    recorder.record_drop(
                        name=record.name,
                        provider=record.provider,
                        url=record.url,
                        reason=record.reason,
                        detail=record.detail,
                    )
            for example in result.weak_fit_examples:
                examples = state.stats.setdefault("weak_fit_examples", [])
                if isinstance(examples, list) and len(examples) < 12:
                    examples.append(
                        {
                            "name": example.name,
                            "provider": example.provider,
                            "url": example.url,
                            "weakReason": example.weak_reason,
                            "gaps": example.gaps,
                            "matchedOn": example.matched_on,
                        }
                    )
                _merge_weak_reason(state.stats, example.weak_reason)
            for verified in result.verified:
                if verified.deadline_rescued:
                    rescued = state.stats.setdefault("rescued_deadlines", [])
                    if isinstance(rescued, list):
                        rescued.append(
                            {
                                "name": verified.program.name,
                                "provider": verified.program.provider,
                                "date": verified.deadline_iso,
                                "quote": strip_private_use(verified.deadline_quote or ""),
                                "url": verified.page_url,
                            }
                        )
            confirmed = [item for item in result.verified if item.verification != "unconfirmed"]
            uncertain = [item for item in result.verified if item.verification == "unconfirmed"]
            _bump_angle(state, extracted.page.angle, "verified", len(confirmed))
            for unconfirmed in uncertain:
                if self._total_results(state) >= settings.stop_at_results:
                    self._request_stop(state, "target_met")
                    return
                program = build_program(unconfirmed, state.profile, extracted.model_id)
                self._keep_best(state, program)
            for verified in confirmed:
                if self._total_results(state) >= settings.stop_at_results:
                    self._request_stop(state, "target_met")
                    return
                program = build_program(verified, state.profile, extracted.model_id)
                if not self._keep_best(state, program):
                    continue
                _bump_round(state, "verified", 1, extracted.page.round)
                counts = state.stats.setdefault("results_by_model", {})
                if isinstance(counts, dict):
                    model_key = program.model_id or "unknown"
                    counts[model_key] = int(counts.get(model_key, 0)) + 1
                if state.stats.get("first_verified_seconds") is None:
                    state.stats["first_verified_seconds"] = round(
                        time.perf_counter() - started, 2
                    )
                    recorder = diagnostics.active()
                    if recorder is not None:
                        recorder.mark("first_verified")
                seconds = round(time.perf_counter() - started, 2)
                result_seconds = state.stats.get("result_seconds")
                if isinstance(result_seconds, list) and len(result_seconds) < settings.stop_at_results:
                    result_seconds.append(seconds)
                publish(state, ProgramFoundEvent(program=program))
                if self._total_results(state) >= settings.stop_at_results:
                    self._request_stop(state, "target_met")
                    return
            self._progress(
                state,
                "verify",
                (
                    f"{len(confirmed)} with a confirmed deadline on this page · "
                    f"{int(state.stats.get('extracted', 0))} extracted · "
                    f"{self._total_results(state)} eligible awards"
                ),
                count=self._total_results(state),
            )

    def _start_stages(self, state: HuntState) -> None:
        for site_id, name in (
            ("search", "Searching for scholarships"),
            ("read", "Reading scholarship pages"),
            ("verify", "Checking deadlines and eligibility"),
        ):
            publish(state, SiteStartedEvent(site_id=site_id, site_name=name))

    def _progress(
        self,
        state: HuntState,
        site_id: str,
        message: str,
        count: int | None = None,
    ) -> None:
        publish(state, SiteProgressEvent(site_id=site_id, message=message[:180], count=count))

    def _maybe_pacing_notice(self, state: HuntState, *, force: bool = False) -> None:
        pool = get_pool()
        if pool is None:
            return
        count = len(pool.usable)
        if count < 1:
            return
        now = time.perf_counter()
        if not force and now - state.last_pacing_notice < PACE_NOTICE_SECONDS:
            return
        state.last_pacing_notice = now
        state.stats["pacing_notices"] = int(state.stats.get("pacing_notices", 0)) + 1
        self._progress(
            state,
            "search",
            f"Gemini is pacing requests across {count} models",
        )

    def _request_stop(self, state: HuntState, reason: str, message: str | None = None) -> None:
        normalized = reason if reason in ALLOWED_STOP_REASONS else "exhausted"
        if not state.stats.get("stop_reason"):
            state.stats["stop_reason"] = normalized
        if message:
            self._progress(state, "verify", message, count=self._total_results(state))
        state.stop_event.set()

    def _finish(self, state: HuntState, started: float) -> None:
        combined: dict[tuple[str, str], Program] = {}
        for program in [*state.results, *state.unconfirmed]:
            key = _state_key(program.name, program.provider)
            current = combined.get(key)
            if current is None or _program_rank(program) < _program_rank(current):
                combined[key] = program
        ranked = list(combined.values())
        state.results = _sort_results(
            [program for program in ranked if program.verification != "unconfirmed"]
        )
        state.unconfirmed = _sort_results(
            [program for program in ranked if program.verification == "unconfirmed"]
        )
        state.seen = dict(combined)
        elapsed = time.perf_counter() - started
        total_awards = len(state.results) + len(state.unconfirmed)
        state.stats["elapsed_seconds"] = round(elapsed, 2)
        state.stats["program_count"] = total_awards
        state.stats["verified"] = len(state.results)
        state.stats["matched"] = total_awards
        state.stats["unconfirmed"] = len(state.unconfirmed)
        gemini = state.stats.get("gemini")
        if isinstance(gemini, dict):
            models = gemini.get("models")
            if isinstance(models, dict):
                state.stats["gemini_requests"] = sum(
                    int(detail.get("requests", 0))
                    for detail in models.values()
                    if isinstance(detail, dict)
                )
                state.stats["gemini_429"] = sum(
                    int(detail.get("rate_limits", 0))
                    for detail in models.values()
                    if isinstance(detail, dict)
                )
            else:
                state.stats["gemini_requests"] = 0
                state.stats["gemini_429"] = 0
        pages = state.stats.get("extraction_pages")
        calls = int(state.stats.get("extraction_calls", 0))
        if isinstance(pages, list) and calls > 0:
            state.stats["average_pages_per_extraction_call"] = round(
                sum(int(count) for count in pages) / calls, 2
            )
        total_amount = sum(
            program.amount_max or 0 for program in [*state.results, *state.unconfirmed]
        )

        stats = state.stats
        for site_id, count in (
            ("search", int(stats.get("queries", 0))),
            ("read", int(stats.get("fetched", 0))),
            ("verify", len(state.results)),
        ):
            publish(state, SiteDoneEvent(site_id=site_id, count=count))

        if stats.get("stop_reason") != "target_met":
            self._progress(
                state,
                "verify",
                f"Stopped at {int(elapsed)}s with {total_awards} awards",
                count=total_awards,
            )
        if int(stats.get("gemini_calls", 0)) >= settings.max_gemini_calls:
            self._progress(
                state,
                "verify",
                f"Gemini call budget reached ({settings.max_gemini_calls}); showing committed results",
                count=len(state.results),
            )
        stage_models = gemini.get("stage_models", {}) if isinstance(gemini, dict) else {}
        stage_models = stage_models if isinstance(stage_models, dict) else {}
        extraction_models = stats.get("extraction_models")
        extraction_models = extraction_models if isinstance(extraction_models, list) else []
        resume_label = (
            f"resume local text, {len(state.resume_text)} characters "
            f"(extraction {len(state.resume_compact)})"
        )
        models_used = {
            "resume": resume_label,
            "planner": str(stage_models.get("planner", "")),
            "selector": str(stage_models.get("selector", "")),
            "extraction": [str(model) for model in extraction_models],
        }
        stats["models_used"] = models_used
        self._progress(
            state,
            "verify",
            (
                f"Models used: {models_used['resume']}, "
                f"planner {models_used['planner'] or 'none'}, "
                f"selector {models_used['selector'] or 'none'}, "
                f"extraction {', '.join(models_used['extraction']) or 'none'}"
            ),
            count=len(state.results),
        )

        dropped = stats.get("dropped")
        dropped_counts = dropped if isinstance(dropped, dict) else {}
        self._progress(
            state,
            "verify",
            drops_message(total_awards, dropped_counts),
            count=total_awards,
        )

        publish(
            state,
            HuntCompleteEvent(
                total_amount=float(total_amount),
                program_count=total_awards,
                verified_count=len(state.results),
                unconfirmed_count=len(state.unconfirmed),
            ),
        )
        logger.info(
            "hunt=%s complete programs=%d unconfirmed=%d total=%.2f elapsed=%.1fs "
            "gemini_requests=%d gemini_429=%d stats=%s",
            state.hunt_id,
            len(state.results),
            len(state.unconfirmed),
            total_amount,
            elapsed,
            int(stats.get("gemini_requests", 0)),
            int(stats.get("gemini_429", 0)),
            stats,
        )

    def _abort(self, state: HuntState, message: str) -> None:
        logger.error("hunt=%s fatal: %s", state.hunt_id, message)
        state.stop_event.set()
        publish(state, HuntErrorEvent(message=message))
        current = asyncio.current_task()
        for task in state.tasks.values():
            if task is not current:
                task.cancel()


manager = HuntManager()
