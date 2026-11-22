"""Warm the cache with the demo hunt before any demo or judging.

Usage:
    python scripts/warmup.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.hunt import manager
from app.models import Profile

DEMO_PROFILE = Profile(
    full_name="Alex Chen",
    province="Ontario",
    school="Western University",
    field="Engineering",
    year="2nd",
    income_range="$30k–$60k",
    status="Citizen",
)


async def _run() -> int:
    hunt_id = manager.start(DEMO_PROFILE)
    state = manager.get(hunt_id)
    assert state is not None
    print(f"warmup hunt {hunt_id} starting")
    _, queue = state.subscribe()

    failed = False
    while True:
        line = await queue.get()
        if line is None:
            break
        payload = json.loads(line)
        event_type = payload.get("type")
        if event_type == "hunt_error":
            failed = True
            print(f"hunt_error: {payload.get('message', '')}")
        elif event_type in {"site_done", "site_failed"}:
            print(f"{event_type}: {payload.get('siteId', '')}")
        elif event_type == "hunt_complete":
            print(f"hunt_complete: {payload.get('programCount', 0)} programs")

    return 1 if failed else 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
