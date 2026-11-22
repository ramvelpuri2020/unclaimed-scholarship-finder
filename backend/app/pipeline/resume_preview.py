"""Stateless resume preview for the wizard.

The preview is computed from the uploaded PDF on every request. Nothing is
cached, nothing is stored, and no contact detail is returned: the response only
carries a character count, short strengths, scholarship angles and the school,
program and year the resume itself states.
"""

from __future__ import annotations

import logging

from ..models import ResumePayload, ResumePreview
from .gemini import GeminiBudget, GeminiBudgetExceeded, GeminiPoolExhausted
from .resume_profile import read_resume_profile
from .resume_text import MIN_RESUME_TEXT_CHARS, read_resume_text

logger = logging.getLogger(__name__)

UNREADABLE_MESSAGE = "We couldn't read your resume. Upload a PDF with selectable text."
# The quality chain starts with the busiest models, so a preview needs enough
# budget to reach a primary model after a few 503 failovers.
PREVIEW_BUDGET = 6


def _short(items: list[str], limit: int) -> list[str]:
    seen: list[str] = []
    for item in items:
        text = " ".join(str(item or "").split())
        if not text or text in seen:
            continue
        seen.append(text)
        if len(seen) >= limit:
            break
    return seen


async def preview_resume(resume: ResumePayload, budget: GeminiBudget) -> ResumePreview:
    """Read the resume fresh and return a contact-free preview."""

    if not resume.data_url.strip():
        raise ValueError("A PDF resume data URL is required.")

    try:
        text = read_resume_text(resume)
    except Exception as exc:  # noqa: BLE001 - an unreadable PDF is a recoverable failure
        logger.warning("Resume text read failed: %s", exc.__class__.__name__)
        text = ""

    profile = None
    try:
        profile = await read_resume_profile(resume, budget)
    except (GeminiBudgetExceeded, GeminiPoolExhausted) as exc:
        # The local text is still useful: the wizard can proceed with the
        # character count and no angles instead of seeing a 500.
        logger.warning("Resume preview model pass skipped: %s", exc.__class__.__name__)

    if profile is None and len(text) < MIN_RESUME_TEXT_CHARS:
        raise ValueError(UNREADABLE_MESSAGE)

    education = profile.education if profile is not None else None
    angles = [angle.angle for angle in profile.scholarship_angles] if profile is not None else []
    strengths = list(profile.strengths) if profile is not None else []
    return ResumePreview(
        characters=len(text),
        strengths=_short(strengths, 6),
        angles=_short(angles, 8),
        stated_school=(education.school if education is not None else None),
        stated_program=(education.program if education is not None else None),
        stated_year=(education.year_of_study if education is not None else None),
    )
