"""Offline checks for resume text preparation and prompt routing."""

from __future__ import annotations

import asyncio

import pytest

from app import hunt as hunt_module
from app.models import Profile, ResumePayload
from app.pipeline import extractor, planner, resume_text
from app.pipeline.gemini import GeminiBudget
from app.pipeline.page_selector import SCORE_INSTRUCTION
from app.pipeline.planner import (
    RESUME_INSTRUCTION,
    _clean_queries,
    plan_queries,
    unverified_based_on_count,
)
from app.pipeline.reader import Page
from app.pipeline.verify import _clean_resume_evidence


def _profile() -> Profile:
    return Profile(
        full_name="",
        province="Ontario",
        school="Western University",
        field="Engineering",
        year="2nd year",
        income_range="",
        status="Canadian citizen",
    )


def _page() -> Page:
    return Page(
        url="https://example.edu/awards",
        final_url="https://example.edu/awards",
        title="Awards",
        text="Engineering scholarship open to undergraduate students.",
    )


def _full_and_compact() -> tuple[str, str]:
    education = "Education\n" + (
        "Bachelor of Engineering Science with coursework in design and circuits. " * 50
    )
    projects = "\nProjects\n" + (
        "Designed a bridge inspection robot for a student design team. " * 12
    )
    marker = "UNIQUE_FULL_RESUME_MARKER"
    full = education + projects + f"\nSkills\n{marker}\n" + ("Python, CAD and MATLAB. " * 200)
    return full, resume_text.compact_resume_text(full, 3_500)


def test_planner_receives_full_text_and_extraction_receives_only_compact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full, compact = _full_and_compact()
    assert len(compact) <= 3_500
    assert "UNIQUE_FULL_RESUME_MARKER" not in compact

    captured: dict[str, str] = {}

    async def fake_plan_json(prompt: str, *args: object, **kwargs: object) -> dict[str, object]:
        captured["planner"] = prompt
        return {"queries": []}

    monkeypatch.setattr(planner, "generate_json", fake_plan_json)
    asyncio.run(
        plan_queries(_profile(), full, GeminiBudget(5), count=3, timeout=1.0)
    )
    assert full.strip() in captured["planner"]
    assert RESUME_INSTRUCTION in captured["planner"]

    extraction_prompts: list[str] = []

    async def fake_extract_json(
        prompt: str, *args: object, **kwargs: object
    ) -> tuple[dict[str, object], str]:
        extraction_prompts.append(prompt)
        return {"pages": []}, "fake-model"

    monkeypatch.setattr(extractor, "generate_json_with_model", fake_extract_json)
    asyncio.run(
        extractor.extract_pages([_page()], _profile(), compact, GeminiBudget(5))
    )
    assert extraction_prompts
    assert all("UNIQUE_FULL_RESUME_MARKER" not in prompt for prompt in extraction_prompts)
    assert compact in extraction_prompts[0]


def test_page_ranking_prompt_uses_the_new_instruction() -> None:
    assert "Score 0 to 5 how likely this page is to list scholarships" in SCORE_INSTRUCTION
    assert "using the resume to judge fit" in SCORE_INSTRUCTION
    assert "Score 0 for news, advice, startup credits" in SCORE_INSTRUCTION


def test_local_text_never_calls_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resume_text, "read_resume_text", lambda _: "x" * 500)

    async def forbidden(*args: object, **kwargs: object) -> str:
        raise AssertionError("OCR must not run when the PDF has a text layer")

    monkeypatch.setattr(resume_text, "ocr_resume_text", forbidden)
    resume = ResumePayload(name="resume.pdf", data_url="data:application/pdf;base64,JVBERi0=")
    text, used_ocr = asyncio.run(resume_text.prepare_resume_text(resume, GeminiBudget(1)))
    assert len(text) == 500
    assert used_ocr is False
    assert not hasattr(hunt_module, "read_resume_profile")


def test_contact_and_profile_lines_are_removed_but_headings_and_breaks_kept() -> None:
    raw = (
        "ALEX CHEN\n"
        "alex@example.com\n"
        "+1 (519) 555-1234\n"
        "12 Main Street\n"
        "M5V 2T6\n"
        "https://linkedin.com/in/alex-chen\n"
        "https://github.com/alex-chen\n"
        "EDUCATION\n"
        "Western University\n"
        "EXPERIENCE\n"
        "Engineering Intern\n"
    )
    text = resume_text.sanitise_resume_text(raw)
    assert text.splitlines()[0] == "ALEX CHEN"
    assert "EDUCATION" in text and "EXPERIENCE" in text
    assert "Western University" in text and "Engineering Intern" in text
    for removed in (
        "alex@example.com",
        "555-1234",
        "12 Main Street",
        "M5V 2T6",
        "linkedin.com",
        "github.com",
    ):
        assert removed not in text
    assert "\n" in text


def test_unverifiable_based_on_is_counted_but_kept() -> None:
    raw = {
        "queries": [
            {
                "query": "robotics engineering scholarship",
                "angle": "robotics",
                "basedOn": "Built a bridge inspection robot",
                "scope": "school",
            },
            {
                "query": "olympic scholarship",
                "angle": "sport",
                "basedOn": "Won an Olympic gold medal",
                "scope": "other",
            },
        ]
    }
    resume = "Education\nBuilt a bridge inspection robot for a student design team."
    queries = _clean_queries(raw, 10, resume)
    assert len(queries) == 2
    assert queries[0].based_on_verified is True
    assert queries[1].based_on_verified is False
    assert unverified_based_on_count(queries) == 1


def test_resume_evidence_outside_the_resume_is_dropped() -> None:
    resume = "Projects\nBuilt a bridge inspection robot for a student design team."
    kept = _clean_resume_evidence(
        [
            "Built a bridge inspection robot for a student design team.",
            "Won an Olympic gold medal in rowing.",
        ],
        resume,
    )
    assert kept == ["Built a bridge inspection robot for a student design team."]


def test_compact_resume_follows_section_priority() -> None:
    text = (
        "Skills\nPython\n"
        "Education\nBSc Engineering\n"
        "Experience\nEngineering Intern\n"
        "Projects\nBridge Robot\n"
        "Awards\nDean's List\n"
        "Volunteering\nFood Bank\n"
    )
    compact = resume_text.compact_resume_text(text, 500)
    positions = {
        name: compact.index(name)
        for name in ("Education", "Projects", "Experience", "Volunteering", "Awards", "Skills")
    }
    assert (
        positions["Education"]
        < positions["Projects"]
        < positions["Experience"]
        < positions["Volunteering"]
        < positions["Awards"]
        < positions["Skills"]
    )
