"""FastAPI application for the Unclaimed backend."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import __version__
from .config import settings
from .hunt import HuntState, manager
from .logging_setup import configure_logging
from .models import (
    HuntMeta,
    Profile,
    Program,
    ResumePayload,
    ResumePreview,
    StartHuntResponse,
)
from .pipeline.gemini import GeminiBudget
from .pipeline.model_pool import get_pool, initialise_pool
from .pipeline.resume_preview import PREVIEW_BUDGET, preview_resume

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
configure_logging()
logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15.0


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fetch and Gemini calls are blocking SDKs; size the executor for both pools
    # plus planning, resume reading and the one optional browser agent.
    executor = ThreadPoolExecutor(
        max_workers=max(24, settings.fetch_concurrency + settings.extract_concurrency + 6),
        thread_name_prefix="unclaimed",
    )
    asyncio.get_running_loop().set_default_executor(executor)
    try:
        pool = await initialise_pool()
    except Exception as exc:
        logger.error("Gemini model pool failed to initialise: %s", exc)
        raise
    logger.info("Gemini model pool ready with %d usable model(s)", len(pool.usable))
    try:
        dropped = await pool.probe_primaries()
        logger.info(
            "Gemini startup probe dropped %d model(s)%s",
            len(dropped),
            f": {', '.join(dropped)}" if dropped else "",
        )
    except Exception as exc:  # noqa: BLE001 - the probe must never block startup
        logger.warning("Gemini startup probe could not run: %s", exc)
    logger.info(
        "Unclaimed API %s starting stop_at=%d search=%d fetch=%d batch=%d extract=%d "
        "per_url_ms=%d page_chars=%d plan=%d gemini_calls=%d wall=%.0fs list_agent_timeout=%.0fs",
        __version__,
        settings.stop_at_results,
        settings.search_concurrency,
        settings.fetch_concurrency,
        settings.fetch_batch,
        settings.extract_concurrency,
        settings.per_url_timeout_ms,
        settings.max_page_chars,
        settings.plan_queries,
        settings.max_gemini_calls,
        settings.wall_timeout_seconds,
        settings.list_agent_timeout_seconds,
    )
    try:
        yield
    finally:
        usage_pool = get_pool()
        if usage_pool is not None:
            usage_pool.usage.save()
        executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Unclaimed API", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in settings.cors_origins else list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_hunt(hunt_id: str) -> HuntState:
    state = manager.get(hunt_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown hunt id.")
    return state


@app.get("/api/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/hunt", response_model=StartHuntResponse)
async def start_hunt(profile: Profile) -> StartHuntResponse:
    hunt_id = manager.start(profile)
    return StartHuntResponse(hunt_id=hunt_id)


@app.post("/api/resume/preview", response_model=ResumePreview)
async def resume_preview(
    payload: Annotated[ResumePayload | str, Body()],
) -> ResumePreview:
    """Read an uploaded resume and return a contact-free preview.

    Stateless: the PDF is processed in memory, nothing is written to disk, and
    no part of the resume is echoed back beyond the counts and short themes.
    """

    if isinstance(payload, str):
        resume = ResumePayload(name="resume.pdf", data_url=payload)
    else:
        resume = payload
    try:
        return await preview_resume(resume, GeminiBudget(PREVIEW_BUDGET))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Resume preview failed: %s", exc.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="The resume preview could not finish. Try again in a moment.",
        ) from exc


async def _event_stream(request: Request, state: HuntState) -> AsyncIterator[str]:
    snapshot, queue = state.subscribe()
    try:
        for line in snapshot:
            yield f"data: {line}\n\n"

        if state.status != "running":
            return

        while True:
            if await request.is_disconnected():
                return
            try:
                async with asyncio.timeout(KEEPALIVE_SECONDS):
                    queued = await queue.get()
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if queued is None:
                return
            yield f"data: {queued}\n\n"
    finally:
        state.unsubscribe(queue)


@app.get("/api/hunt/{huntId}/events")
async def hunt_events(huntId: str, request: Request) -> StreamingResponse:
    state = _require_hunt(huntId)
    return StreamingResponse(
        _event_stream(request, state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/hunt/{huntId}/meta", response_model=HuntMeta)
async def hunt_meta(huntId: str) -> HuntMeta:
    """Contact-free metadata for a saved hunt, including its start time."""

    state = _require_hunt(huntId)
    elapsed = state.stats.get("elapsed_seconds")
    return HuntMeta(
        hunt_id=state.hunt_id,
        status=state.status,
        started_at=state.started_at_iso or None,
        elapsed_seconds=float(elapsed) if isinstance(elapsed, int | float) else None,
    )


@app.get("/api/hunt/{huntId}/results", response_model=list[Program])
async def hunt_results(huntId: str) -> list[Program]:
    """Tier A (confirmed deadline) results first, then every tier B award."""

    state = _require_hunt(huntId)
    if state.status == "running":
        return []
    return [*state.results, *state.unconfirmed]
