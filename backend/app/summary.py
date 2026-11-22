"""Human-readable hunt summaries shared by the API, diagnostics and tests.

The wording never mentions money: a hunt can legitimately total $0 in listed
amounts, and "$0" reads like a failure even when forty awards were found.
"""

from __future__ import annotations

from collections.abc import Mapping


def completion_message(total: int, verified: int, unconfirmed: int) -> str:
    """Return the one-line completion summary used in the feed."""

    return (
        f"Found {total} awards: {verified} with a confirmed deadline, "
        f"{unconfirmed} to check"
    )


OTHER_ELIGIBILITY_REASONS = (
    "institution",
    "province",
    "level",
    "year",
    "citizenship",
    "identity_restriction",
    "entrance_award",
)


def drops_message(total: int, dropped: Mapping[str, int]) -> str:
    """Return the per-hunt drop tally: weak fit, past-dated, other, not awards."""

    weak_fit = int(dropped.get("weak_fit", 0))
    past_dated = int(dropped.get("stale_or_unverified", 0))
    other = sum(int(dropped.get(reason, 0)) for reason in OTHER_ELIGIBILITY_REASONS)
    not_awards = int(dropped.get("not_student_award", 0))
    return (
        f"Eligible awards: {total}. Dropped: {weak_fit} weak fit, "
        f"{past_dated} past-dated, {other} other eligibility, "
        f"{not_awards} not student awards"
    )
