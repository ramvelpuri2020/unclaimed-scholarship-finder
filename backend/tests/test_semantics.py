"""Offline checks for the rules that decide matches and deadlines."""

from __future__ import annotations

from datetime import date

from app.models import Eligibility, ExtractedDeadline, ExtractedProgram, Profile
from app.pipeline.extractor import ExtractedPage
from app.pipeline.reader import Page
from app.pipeline.verify import (
    VerifyResult,
    VerifyState,
    _eligibility_reason,
    _institution_matches,
    _is_entrance_award,
    _quote_ok,
    _rescue_deadline,
    _year_matches,
    clean_display_quote,
    verify_pages,
)


def _profile(year: str = "1st year") -> Profile:
    return Profile(
        full_name="",
        province="Ontario",
        school="Western University",
        field="Engineering",
        year=year,
        income_range="",
        status="Canadian citizen",
    )


def test_entering_second_year_matches_a_first_year_student() -> None:
    assert _year_matches(["entering their second year in the Faculty of Engineering"], "1st year")


def test_entering_third_year_rejects_a_first_year_student() -> None:
    assert not _year_matches(["entering third year"], "1st year")


def test_current_year_wording_matches_same_year() -> None:
    assert _year_matches(["second year students"], "2nd year")
    assert not _year_matches(["second year students"], "1st year")


def test_year_ranges() -> None:
    assert _year_matches(["students in years 2-4"], "2nd year")
    assert _year_matches(["years 2 to 4"], "3rd year")
    assert not _year_matches(["years 2-4"], "1st year")


def test_year_or_above() -> None:
    assert _year_matches(["second year or above"], "3rd year")
    assert not _year_matches(["second year or above"], "1st year")


def test_year_item_without_a_year_is_not_a_restriction() -> None:
    assert _year_matches(["undergraduate students in good standing"], "1st year")


def test_emco_style_award_is_not_dropped_for_entering_second_year() -> None:
    program = ExtractedProgram(
        name="EMCO Corporation Entrepreneurial Scholarship",
        eligibility=Eligibility(
            level_of_study=["undergraduate"],
            year_of_study=["students entering their second year in the Faculty of Engineering"],
            institutions=["Western University"],
            provinces=["Ontario"],
        ),
    )
    assert _eligibility_reason(program, _profile()) is None


def test_quote_matching_ignores_markdown_and_unicode() -> None:
    assert _quote_ok("**Deadline:** October 1, 2026", "Deadline: October 1, 2026")
    assert _quote_ok("the university\u2019s award", "the university's award")
    assert _quote_ok("a\u00a0need-based bursary", "a need-based bursary")
    assert _quote_ok("Apply through [the portal](https://example.com)", "Apply through the portal")
    assert not _quote_ok("a different award", "This page lists one award.")


def test_display_quote_strips_markdown_markers() -> None:
    assert clean_display_quote("**Deadline:** October 1, 2026") == "Deadline: October 1, 2026"
    assert clean_display_quote("> Applications close [here](https://example.com).") == (
        "Applications close here."
    )


def test_deadline_rescue_stays_inside_the_programs_own_section() -> None:
    text = (
        "## EMCO Corporation Entrepreneurial Scholarship\n"
        "Open to students entering their second year. Applications close October 1, 2026.\n\n"
        "## Other Award\n"
        "Applications close March 1, 2027.\n"
    )
    rescued = _rescue_deadline(
        text,
        date(2026, 1, 5),
        program_name="EMCO Corporation Entrepreneurial Scholarship",
        other_names=["Other Award"],
    )
    assert rescued.section is not None
    assert "Other Award" not in rescued.section
    assert rescued.date_value == date(2026, 10, 1)


def test_first_year_wording_matches_a_current_first_year_student() -> None:
    assert _year_matches(["open to first-year students"], "1st year")
    assert _year_matches(["year 1"], "1st")
    assert _year_matches(["1st year"], "first year")


def test_second_year_wording_matches_a_current_second_year_student() -> None:
    assert _year_matches(["second year"], "2nd year")
    assert _year_matches(["years 2-4"], "2nd year")
    assert not _year_matches(["entering first year"], "2nd year")


def test_first_year_text_alone_is_not_a_conflict() -> None:
    assert _year_matches(["open to first-year and upper-year students"], "3rd year")
    assert _year_matches(["continuing students"], "2nd year")


def _page(text: str) -> Page:
    return Page(
        url="https://example.edu/awards",
        final_url="https://example.edu/awards",
        title="Awards",
        text=text,
    )


def _verify(text: str, program: ExtractedProgram, year: str = "2nd year") -> VerifyResult:
    return verify_pages(
        [ExtractedPage(page=_page(text), is_list_page=False, programs=[program])],
        _profile(year),
        VerifyState(),
        today=date(2026, 1, 5),
    )


def test_entrance_award_is_recognised() -> None:
    program = ExtractedProgram(
        name="President's Entrance Scholarship",
        provider="Western University",
        description="An entrance scholarship for students applying from high school.",
        eligibility=Eligibility(level_of_study=["undergraduate"], year_of_study=["entering first year"]),
        fit="good",
        confidence=0.9,
    )
    assert _is_entrance_award(program)


def test_institution_matches_western_alias_and_national_pages() -> None:
    assert _institution_matches(["University of Western Ontario"], "Western University")
    assert _institution_matches(["Canadian universities"], "Western University")
    assert not _institution_matches(["University of Toronto"], "Western University")


def test_description_mentioning_entrance_does_not_drop_an_undergraduate_award() -> None:
    program = ExtractedProgram(
        name="Ontario Undergraduate Scholarships",
        provider="Engineers Foundation Ontario",
        description=(
            "The foundation awards two entrance scholarships and several undergraduate "
            "scholarships at each partner school."
        ),
        eligibility=Eligibility(level_of_study=["undergraduate"], year_of_study=["all years"]),
        fit="good",
        confidence=0.8,
    )
    assert not _is_entrance_award(program)


def test_entrance_award_is_dropped_by_the_verifier() -> None:
    text = (
        "## President's Entrance Scholarship\n"
        "For students applying from high school. Applications close March 1, 2027.\n"
    )
    program = ExtractedProgram(
        name="President's Entrance Scholarship",
        provider="Western University",
        description="An entrance scholarship for students applying from high school.",
        deadlines=[
            ExtractedDeadline(
                date_iso="2027-03-01",
                quote="Applications close March 1, 2027",
                label="Deadline",
            )
        ],
        eligibility=Eligibility(level_of_study=["undergraduate"], institutions=["Western University"]),
        fit="good",
        confidence=0.9,
        student_award=True,
    )
    result = _verify(text, program, year="1st year")
    assert result.dropped.get("entrance_award") == 1
    assert result.verified == []


def test_program_without_any_deadline_is_unconfirmed() -> None:
    text = (
        "## Open Undergraduate Award\n"
        "Open to all undergraduate students at Western University who are in good standing.\n"
    )
    program = ExtractedProgram(
        name="Open Undergraduate Award",
        provider="Western University",
        eligibility=Eligibility(level_of_study=["undergraduate"], institutions=["Western University"]),
        fit="good",
        confidence=0.85,
        student_award=True,
    )
    result = _verify(text, program)
    assert [item.verification for item in result.verified] == ["unconfirmed"]
    assert result.verified[0].deadline_iso is None


def test_page_with_only_past_dates_is_never_included() -> None:
    text = "## Past Award\nApplications closed March 1, 2024.\n"
    program = ExtractedProgram(
        name="Past Award",
        provider="Western University",
        eligibility=Eligibility(level_of_study=["undergraduate"], institutions=["Western University"]),
        fit="good",
        confidence=0.85,
        student_award=True,
    )
    result = _verify(text, program)
    assert result.verified == []
    assert result.dropped.get("stale_or_unverified") == 1


def test_missing_program_name_never_rescues_a_deadline() -> None:
    rescued = _rescue_deadline(
        "A page about something else. Applications close March 1, 2027.",
        date(2026, 1, 5),
        program_name="EMCO Scholarship",
        other_names=[],
    )
    assert rescued.section is None
    assert rescued.date_value is None
