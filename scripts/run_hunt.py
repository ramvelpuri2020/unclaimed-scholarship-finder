"""Run one live hunt and print the acceptance-report metrics.

Usage:
    python scripts/run_hunt.py --demo --resume backend/data/resume.pdf
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
load_dotenv(BACKEND_ROOT / ".env")


def _demo_profile(resume_path: Path | None) -> dict[str, object]:
    profile: dict[str, object] = {
        "fullName": "Alex Chen",
        "province": "Ontario",
        "school": "Western University",
        "field": "Engineering",
        "year": "2nd",
        "incomeRange": "$50,000-$75,000",
        "status": "Canadian citizen",
    }
    if resume_path is not None:
        data = base64.b64encode(resume_path.read_bytes()).decode("ascii")
        profile["resume"] = {
            "name": resume_path.name,
            "dataUrl": f"data:application/pdf;base64,{data}",
        }
    return profile


def _print_events(events: list[str], limit: int = 16) -> None:
    if not events:
        return
    print("\nRecent events:")
    for raw in events[-limit:]:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "hunt_error":
            print(f"  ERROR: {event.get('message')}")
        elif kind == "site_progress":
            print(f"  {event.get('siteId')}: {event.get('message')}")
        elif kind == "program_found":
            program = event.get("program") or {}
            print(f"  found: {program.get('name')} · {program.get('provider')}")
        elif kind == "hunt_complete":
            print(f"  complete: {event.get('programCount')} programs")


def _print_funnel(stats: dict[str, Any]) -> None:
    print("\nFunnel")
    print(f"  candidates          {stats.get('candidates', 0)}")
    print(f"  selected_pages      {stats.get('selected_pages', 0)}")
    print(f"  fetched             {stats.get('fetched', 0)}")
    print(f"  reader_tinyfish     {stats.get('reader_tinyfish', 0)}")
    print(f"  reader_http         {stats.get('reader_http', 0)}")
    print(f"  unreadable_pages    {stats.get('unreadable_pages', 0)}")
    prefilters = stats.get("prefiltered")
    if isinstance(prefilters, dict) and prefilters:
        for reason, count in sorted(prefilters.items()):
            print(f"  {reason:20} {count}")
    else:
        print("  prefiltered         0")
    print(f"  fetch_errors        {stats.get('fetch_errors', 0)}")
    print(f"  sent_to_extraction  {stats.get('sent_to_extraction', 0)}")
    print(f"  extraction_calls    {stats.get('extraction_calls', 0)}")
    print(f"  zero_program_calls  {stats.get('zero_program_calls', 0)}")
    print(f"  extraction_failures {stats.get('extraction_failures', 0)}")
    print(f"  extracted           {stats.get('extracted', 0)}")
    print(f"  verified            {stats.get('verified', 0)}")


def _print_timing(stats: dict[str, Any]) -> None:
    print("\nTiming")
    print(f"  elapsed_seconds       {stats.get('elapsed_seconds')}")
    print(f"  stop_reason           {stats.get('stop_reason')}")
    print(f"  first_fetch_seconds   {stats.get('first_fetch_seconds')}")
    print(f"  first_extract_seconds {stats.get('first_extract_seconds')}")
    print(f"  first_verified_seconds {stats.get('first_verified_seconds')}")
    result_seconds = stats.get("result_seconds")
    if isinstance(result_seconds, list):
        for threshold in (1, 5, 10, 15):
            value = result_seconds[threshold - 1] if len(result_seconds) >= threshold else None
            print(f"  result #{threshold:<12} {value if value is not None else 'not reached'}")
    seconds = stats.get("extraction_seconds")
    if isinstance(seconds, list) and seconds:
        average = sum(float(item) for item in seconds) / len(seconds)
        print(f"  extraction_avg_seconds {average:.3f}")
        print(f"  extraction_max_seconds {max(float(item) for item in seconds):.3f}")
    rate_limit = stats.get("rate_limit")
    if isinstance(rate_limit, dict):
        print("\nRate limits")
        print(f"  initial_limit        {rate_limit.get('initial_limit')}")
        print(f"  effective_limit      {rate_limit.get('effective_limit')}")
        print(f"  429_count            {rate_limit.get('rate_limit_count')}")
        print(f"  total_wait_seconds   {rate_limit.get('total_wait_seconds')}")


def _print_drops(stats: dict[str, Any]) -> None:
    print("\nDrop reasons")
    dropped = stats.get("dropped")
    if isinstance(dropped, dict) and dropped:
        for reason, count in sorted(dropped.items()):
            print(f"  {reason:24} {count}")
    else:
        print("  none")


def _print_weak_examples(stats: dict[str, Any]) -> None:
    print("\nFirst weak_fit decisions")
    examples = stats.get("weak_fit_examples")
    if not isinstance(examples, list) or not examples:
        print("  none")
        return
    for index, item in enumerate(examples[:12], start=1):
        print(f"\n  {index}. {item.get('name')}")
        print(f"     provider:   {item.get('provider')}")
        print(f"     url:        {item.get('url')}")
        print(f"     weakReason: {item.get('weakReason') or '-'}")
        gaps = item.get("gaps") or []
        matched = item.get("matchedOn") or []
        print(f"     gaps:       {', '.join(str(value) for value in gaps) or '-'}")
        print(f"     matchedOn:  {', '.join(str(value) for value in matched) or '-'}")


def _print_rescued(stats: dict[str, Any]) -> None:
    print("\nDeadline/rolling rescues")
    rescued = stats.get("rescued_deadlines")
    if not isinstance(rescued, list) or not rescued:
        print("  none")
        return
    for item in rescued:
        print(f"  {item.get('name')} · {item.get('provider')}")
        print(f"    date:  {item.get('date')}")
        print(f"    quote: {item.get('quote')}")
        print(f"    url:   {item.get('url')}")


def _print_results(programs: list[object]) -> None:
    print("\nVerified results")
    if not programs:
        print("  none")
        return
    for index, program in enumerate(programs, start=1):
        amount = getattr(program, "amount_max", None)
        amount_text = (
            f"${amount:,.0f}"
            if isinstance(amount, (int, float))
            else str(getattr(program, "amount_label", "varies"))
        )
        deadline = getattr(program, "deadline", None)
        verification = str(getattr(program, "verification", "unknown"))
        deadline_or_type = str(deadline) if deadline else verification
        matched = getattr(program, "matched_on", None)
        print(f"\n{index}. {getattr(program, 'name', '')}")
        print(f"   provider:      {getattr(program, 'provider', '')}")
        print(f"   amount:        {amount_text}")
        print(f"   deadline/type: {deadline_or_type}")
        print(f"   deadlineQuote: {getattr(program, 'deadline_quote', None) or '-'}")
        print(f"   url:           {getattr(program, 'url', '')}")
        print(f"   matchedOn:     {', '.join(str(item) for item in matched) if matched else '-'}")


async def run_demo(resume_path: Path | None) -> int:
    missing = [name for name in ("TINYFISH_API_KEY", "GEMINI_API_KEY") if not os.environ.get(name)]
    if missing:
        print("Cannot run the live hunt without: " + ", ".join(missing))
        print("Stages not run: planning, discovery, reading, extraction, verification.")
        print("No mock or padded results were produced.")
        return 0

    if resume_path is not None and not resume_path.exists():
        print(f"Resume not found: {resume_path}")
        return 2

    sys.path.insert(0, str(BACKEND_ROOT))
    from app.hunt import manager
    from app.models import Profile

    profile = Profile.model_validate(_demo_profile(resume_path))
    hunt_id = manager.start(profile)
    state = manager.get(hunt_id)
    if state is None:
        print("Hunt was not created.")
        return 1

    print(f"Hunt {hunt_id} started for {profile.full_name} ({profile.school}, {profile.field}, {profile.year})")
    if resume_path is None:
        print("No resume supplied; matching runs on profile facts only.")
    else:
        print(f"Resume supplied: {resume_path.name}")

    started = time.monotonic()
    _, queue = state.subscribe()
    while True:
        line = await queue.get()
        if line is None:
            break
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "site_progress":
            print(f"  [{time.monotonic() - started:5.1f}s] {event.get('siteId')}: {event.get('message')}")
        elif kind == "program_found":
            program = event.get("program") or {}
            print(f"  [{time.monotonic() - started:5.1f}s] FOUND: {program.get('name')}")
        elif kind == "hunt_error":
            print(f"  [{time.monotonic() - started:5.1f}s] ERROR: {event.get('message')}")
            return 1
        elif kind == "hunt_complete":
            print(
                f"  [{time.monotonic() - started:5.1f}s] complete: "
                f"{event.get('programCount')} awards, "
                f"{event.get('verifiedCount', 0)} confirmed, "
                f"{event.get('unconfirmedCount', 0)} to check"
            )

    elapsed = time.monotonic() - started
    print(f"\nObserved elapsed: {elapsed:.1f}s, status: {state.status}")
    _print_funnel(state.stats)
    _print_timing(state.stats)
    _print_drops(state.stats)
    _print_weak_examples(state.stats)
    _print_rescued(state.stats)
    _print_events(state.events)
    _print_results(list(state.results))
    if state.status == "running":
        print("The hunt is still running after the script wait window.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Unclaimed scholarship hunt.")
    parser.add_argument("--demo", action="store_true", help="Use the built-in demo student profile.")
    parser.add_argument("--resume", type=Path, default=None, help="Optional PDF resume for the demo profile.")
    args = parser.parse_args()
    if not args.demo:
        print("Only --demo is supported.")
        return 2
    return asyncio.run(run_demo(args.resume))


if __name__ == "__main__":
    raise SystemExit(main())
