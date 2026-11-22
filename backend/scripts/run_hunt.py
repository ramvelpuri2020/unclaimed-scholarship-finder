"""Run a hunt in-process and print every event plus a final program table.

Usage:
    python scripts/run_hunt.py --demo
    python scripts/run_hunt.py --profile path/to/profile.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.hunt import manager
from app.models import Profile, Program

DEMO_PROFILE = Profile(
    full_name="Alex Chen",
    province="Ontario",
    school="Western University",
    field="Engineering",
    year="2nd",
    income_range="$30k–$60k",
    status="Citizen",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an Unclaimed hunt in this process.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Use the built-in demo profile (Alex Chen).")
    group.add_argument("--profile", type=Path, help="Path to a JSON file matching the Profile shape.")
    return parser.parse_args()


def _load_profile(args: argparse.Namespace) -> Profile:
    if args.demo:
        return DEMO_PROFILE
    raw = json.loads(args.profile.read_text(encoding="utf-8"))
    return Profile.model_validate(raw)


def _deadline(program: Program) -> str:
    if program.deadline:
        return program.deadline
    if program.deadline_label:
        return program.deadline_label
    return "-"


def _print_table(programs: list[Program]) -> None:
    if not programs:
        print("\nNo programs qualified for this profile.")
        return

    name_width = 46
    print(
        f"\n{'Name':<{name_width}} {'Amount':<22} {'Deadline':<12} {'Conf':>5}  Source"
    )
    print("-" * (name_width + 22 + 12 + 8 + 30))
    for program in programs:
        name = program.name if len(program.name) <= name_width else program.name[: name_width - 1] + "…"
        amount = program.amount_label if len(program.amount_label) <= 22 else program.amount_label[:21] + "…"
        print(
            f"{name:<{name_width}} {amount:<22} {_deadline(program):<12} "
            f"{program.confidence:>5.2f}  {program.source_site}"
        )


async def _run(profile: Profile) -> int:
    hunt_id = manager.start(profile)
    state = manager.get(hunt_id)
    assert state is not None
    print(f"hunt {hunt_id} starting for {profile.full_name} ({profile.school})")
    _, queue = state.subscribe()

    terminal_error = False
    while True:
        line = await queue.get()
        if line is None:
            break
        print(line)
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "hunt_error":
            terminal_error = True

    if terminal_error:
        print("\nHunt failed. See the hunt_error event above.")
        return 1

    _print_table(state.results)
    return 0


def main() -> int:
    args = _parse_args()
    profile = _load_profile(args)
    return asyncio.run(_run(profile))


if __name__ == "__main__":
    raise SystemExit(main())
