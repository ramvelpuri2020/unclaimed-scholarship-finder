"""Deterministic amount parsing for award text.

The extraction model sometimes returns a readable amount ("$1,000", "up to
$5,000") without the numeric maximum. This module derives the maximum from the
text without guessing: a figure only counts when it is written with a dollar
sign, and the largest such figure wins so a range reports its top end.
"""

from __future__ import annotations

import re

DOLLAR_AMOUNT_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")


def parse_amount_text(value: str | None) -> float | None:
    """Return the largest dollar figure in ``value``, or None when there is none."""

    text = (value or "").strip()
    if not text or "$" not in text:
        return None
    amounts: list[float] = []
    for raw in DOLLAR_AMOUNT_RE.findall(text):
        cleaned = raw.replace(",", "").rstrip(".")
        if not cleaned:
            continue
        try:
            amount = float(cleaned)
        except ValueError:
            continue
        if amount > 0:
            amounts.append(amount)
    return max(amounts) if amounts else None
