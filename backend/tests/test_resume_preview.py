"""Offline checks for the stateless resume preview's failure paths."""

from __future__ import annotations

import asyncio

import pytest

from app.models import ResumePayload
from app.pipeline import resume_preview
from app.pipeline.gemini import GeminiBudget, GeminiPoolExhausted


def _resume() -> ResumePayload:
    return ResumePayload(name="resume.pdf", data_url="data:application/pdf;base64,JVBERi0=")


def _budget() -> GeminiBudget:
    return GeminiBudget(resume_preview.PREVIEW_BUDGET)


def test_preview_falls_back_to_local_text_when_models_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        resume_preview,
        "read_resume_text",
        lambda resume: "Built a bridge inspection robot for a student design team. " * 6,
    )

    async def unavailable(*args: object, **kwargs: object) -> None:
        raise GeminiPoolExhausted("Gemini daily limit reached; showing the results found so far")

    monkeypatch.setattr(resume_preview, "read_resume_profile", unavailable)
    preview = asyncio.run(resume_preview.preview_resume(_resume(), _budget()))

    assert preview.characters > resume_preview.MIN_RESUME_TEXT_CHARS
    assert preview.angles == []
    assert preview.strengths == []


def test_preview_reports_unreadable_when_text_and_models_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resume_preview, "read_resume_text", lambda resume: "")

    async def unavailable(*args: object, **kwargs: object) -> None:
        raise GeminiPoolExhausted("all models failed")

    monkeypatch.setattr(resume_preview, "read_resume_profile", unavailable)
    with pytest.raises(ValueError) as caught:
        asyncio.run(resume_preview.preview_resume(_resume(), _budget()))
    assert "couldn't read your resume" in str(caught.value)


def test_preview_survives_a_local_read_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(resume: ResumePayload) -> str:
        raise OSError("malformed pdf")

    monkeypatch.setattr(resume_preview, "read_resume_text", broken)

    async def unavailable(*args: object, **kwargs: object) -> None:
        raise GeminiPoolExhausted("all models failed")

    monkeypatch.setattr(resume_preview, "read_resume_profile", unavailable)
    with pytest.raises(ValueError):
        asyncio.run(resume_preview.preview_resume(_resume(), _budget()))


def test_preview_budget_covers_a_failover_chain() -> None:
    assert resume_preview.PREVIEW_BUDGET >= 6
