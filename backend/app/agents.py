"""TinyFish browser agents for award index pages.

Only list/index pages use an agent. The agent returns names and detail URLs; it
does not decide eligibility and it never submits forms.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

from pydantic import ValidationError
from tinyfish import (
    AuthenticationError,
    BrowserProfile,
    CompleteEvent,
    PaymentRequiredError,
    ProgressEvent,
    RunStatus,
    StartedEvent,
    StreamingUrlEvent,
    TinyFish,
)

from .config import settings
from .models import HuntEventBase, ListedAward, SiteProgressEvent, SiteStartedEvent
from .threads import run_daemon

logger = logging.getLogger(__name__)

Emit = Callable[[HuntEventBase], None]

AGENT_GOAL = (
    "Read this awards index page only. Do not log in, do not submit a form, and do not apply. "
    "Return a JSON object with an awards array. Each item must have the individual award name and "
    "the absolute or relative detailUrl for that award. Follow pagination on this index and include "
    "every individual award you can see, up to 30. Do not return navigation links, generic financial "
    "aid advice, or government programs. Use only facts visible on the page and never guess a URL."
)

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "awards": {
            "type": "array",
            "maxItems": 30,
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "detailUrl": {"type": "string", "nullable": True},
                },
            },
        }
    },
    "required": ["awards"],
}


class FatalHuntError(RuntimeError):
    """Raised when the whole hunt must stop (bad key, no credits)."""


@dataclass(frozen=True)
class AgentOutcome:
    awards: list[ListedAward]
    failed: bool
    error: str | None = None


@dataclass
class _ThreadResult:
    awards: list[ListedAward] = field(default_factory=list)
    error: str | None = None
    exception: BaseException | None = None


_client: TinyFish | None = None


def _get_client() -> TinyFish:
    global _client
    if _client is None:
        _client = TinyFish()
    return _client


def _describe_exception(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _parse_awards(payload: Any) -> list[ListedAward]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict):
        raw = payload.get("awards", payload.get("programs", []))
    elif isinstance(payload, list):
        raw = payload
    else:
        raw = []
    if not isinstance(raw, list):
        return []

    awards: list[ListedAward] = []
    for item in raw[:30]:
        try:
            award = ListedAward.model_validate(item)
        except ValidationError as exc:
            logger.warning("Skipping invalid listed award: %s", exc)
            continue
        awards.append(award)
    return awards


def _run_stream(source_url: str, source_id: str, source_name: str, emit: Emit) -> _ThreadResult:
    completed: list[CompleteEvent] = []

    def on_started(event: StartedEvent) -> None:
        run_id = getattr(event, "run_id", None) or getattr(event, "runId", None)
        logger.info("List agent started siteId=%s run_id=%s", source_id, run_id)
        emit(SiteStartedEvent(site_id=source_id, site_name=source_name))

    def on_streaming_url(event: StreamingUrlEvent) -> None:
        emit(
            SiteStartedEvent(
                site_id=source_id,
                site_name=source_name,
                streaming_url=event.streaming_url,
            )
        )

    def on_progress(event: ProgressEvent) -> None:
        message = event.purpose.strip()[:140]
        if message:
            emit(SiteProgressEvent(site_id=source_id, message=message))

    def on_complete(event: CompleteEvent) -> None:
        completed.append(event)

    try:
        with _get_client().agent.stream(
            goal=AGENT_GOAL,
            url=source_url,
            output_schema=OUTPUT_SCHEMA,
            browser_profile=BrowserProfile.LITE,
            on_started=on_started,
            on_streaming_url=on_streaming_url,
            on_progress=on_progress,
            on_complete=on_complete,
        ) as stream:
            for _ in stream:
                pass
    except Exception as exc:  # noqa: BLE001 - the SDK raises several unrelated error types
        return _ThreadResult(error=_describe_exception(exc), exception=exc)

    if not completed:
        return _ThreadResult(error="Agent stream ended without a completion event.")

    final = completed[-1]
    if final.status != RunStatus.COMPLETED:
        error = getattr(final.error, "message", None) or f"Agent finished with status {final.status}."
        return _ThreadResult(error=str(error))
    if final.result_json is None:
        return _ThreadResult(error="Agent returned no structured output.")

    try:
        awards = _parse_awards(final.result_json)
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        return _ThreadResult(error=f"Could not read agent output: {_describe_exception(exc)}", exception=exc)
    return _ThreadResult(awards=awards)


async def _drain(queue: asyncio.Queue[tuple[str, Any]], emit: Emit) -> _ThreadResult:
    while True:
        kind, payload = await queue.get()
        if kind == "event":
            emit(payload)
        elif kind == "done":
            assert isinstance(payload, _ThreadResult)
            return payload


async def _run_once(source_url: str, source_id: str, source_name: str, emit: Emit) -> _ThreadResult:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    closed = threading.Event()

    def push(function: Callable[..., None], *args: object) -> None:
        try:
            loop.call_soon_threadsafe(function, *args)
        except RuntimeError:
            return

    def thread_emit(event: HuntEventBase) -> None:
        if closed.is_set():
            return
        push(queue.put_nowait, ("event", event))

    def worker() -> None:
        result = _run_stream(source_url, source_id, source_name, thread_emit)
        push(queue.put_nowait, ("done", result))

    thread_task = asyncio.create_task(run_daemon(worker))
    try:
        return await asyncio.wait_for(_drain(queue, emit), timeout=settings.list_agent_timeout_seconds)
    except TimeoutError:
        closed.set()
        logger.info("List agent timed out siteId=%s after %.0fs", source_id, settings.list_agent_timeout_seconds)
        return _ThreadResult(error=f"Agent timed out after {settings.list_agent_timeout_seconds:.0f}s.")
    finally:
        # The SDK call cannot be cancelled from this thread; keep the process alive
        # without exposing a rejected task exception.
        thread_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)


async def run_list_agent(
    source_url: str,
    source_id: str,
    source_name: str,
    emit: Emit,
    semaphore: asyncio.Semaphore,
) -> AgentOutcome:
    """Run one list-page agent, honouring the shared concurrency semaphore."""

    async with semaphore:
        result = await _run_once(source_url, source_id, source_name, emit)
        if result.exception is not None:
            if isinstance(result.exception, AuthenticationError):
                raise FatalHuntError("TinyFish rejected the API key.")
            if isinstance(result.exception, PaymentRequiredError):
                raise FatalHuntError("TinyFish credits are used up.")
        if result.error is None:
            return AgentOutcome(awards=result.awards, failed=False)
        logger.warning("List agent siteId=%s failed: %s", source_id, result.error)
        return AgentOutcome(awards=[], failed=True, error=result.error)


def resolve_detail_url(page_url: str, detail_url: str | None) -> str | None:
    if not detail_url:
        return None
    resolved = urljoin(page_url, detail_url.strip())
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return resolved
