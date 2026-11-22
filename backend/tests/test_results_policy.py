"""Offline checks for the results policy: freshness, tiers, amounts, wording."""

from __future__ import annotations

from datetime import date

from app.models import Eligibility, ExtractedProgram, Profile
from app.pipeline.amounts import parse_amount_text
from app.pipeline.extractor import ExtractedPage
from app.pipeline.matcher import build_program
from app.pipeline.reader import Page
from app.pipeline.verify import VerifiedProgram, VerifyState, verify_pages
from app.summary import completion_message, drops_message


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


def _page(text: str) -> Page:
    return Page(
        url="https://example.edu/awards",
        final_url="https://example.edu/awards",
        title="Awards",
        text=text,
    )


def _program(name: str, provider: str = "Western University") -> ExtractedProgram:
    return ExtractedProgram(
        name=name,
        provider=provider,
        eligibility=Eligibility(
            level_of_study=["undergraduate"],
            institutions=["Western University"],
            provinces=["Ontario"],
        ),
        fit="good",
        confidence=0.8,
        student_award=True,
    )


def _verify(text: str, programs: list[ExtractedProgram], today: date = date(2026, 1, 5)):
    return verify_pages(
        [ExtractedPage(page=_page(text), is_list_page=True, programs=programs)],
        _profile(),
        VerifyState(),
        today=today,
    )


def test_one_old_news_date_does_not_drop_undated_awards() -> None:
    text = (
        "Alumni news: the 2019 campaign raised $50,000. Posted January 3, 2024.\n\n"
        "## Alpha Engineering Award\nOpen to undergraduate students at Western University.\n\n"
        "## Beta Engineering Award\nOpen to undergraduate students at Western University.\n\n"
        "## Gamma Engineering Award\nOpen to undergraduate students at Western University.\n"
    )
    programs = [
        _program("Alpha Engineering Award"),
        _program("Beta Engineering Award"),
        _program("Gamma Engineering Award"),
    ]
    result = _verify(text, programs)
    assert [item.verification for item in result.verified] == [
        "unconfirmed",
        "unconfirmed",
        "unconfirmed",
    ]
    assert result.dropped.get("stale_or_unverified", 0) == 0


def test_awards_own_past_deadline_is_dropped() -> None:
    text = (
        "## Old Engineering Award\n"
        "Open to undergraduate students at Western University. Deadline: March 3, 2025.\n"
    )
    result = _verify(text, [_program("Old Engineering Award")])
    assert result.verified == []
    assert result.dropped.get("stale_or_unverified") == 1


def test_awards_own_future_deadline_is_verified() -> None:
    text = (
        "## New Engineering Award\n"
        "Open to undergraduate students at Western University. Deadline: March 3, 2027.\n"
    )
    result = _verify(text, [_program("New Engineering Award")], today=date(2026, 6, 1))
    assert [item.verification for item in result.verified] == ["dated"]
    assert result.verified[0].deadline_iso == "2027-03-03"


def test_unconfirmed_programs_have_no_cap() -> None:
    names = [f"Engineering Award {letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXY"]
    text = "\n".join(
        f"## {name}\nOpen to undergraduate students at Western University.\n" for name in names
    )
    result = _verify(text, [_program(name) for name in names])
    assert len(result.verified) == 25
    assert all(item.verification == "unconfirmed" for item in result.verified)


def test_amount_parsing_is_deterministic() -> None:
    assert parse_amount_text("$1,000") == 1000
    assert parse_amount_text("$500 - $2,000") == 2000
    assert parse_amount_text("up to $5,000") == 5000
    assert parse_amount_text("valued at $1,000") == 1000
    assert parse_amount_text("amount varies") is None
    assert parse_amount_text(None) is None


def _verified_program(amount_text: str | None, verification: str = "unconfirmed") -> VerifiedProgram:
    return VerifiedProgram(
        program=ExtractedProgram(
            name="Amount Award",
            provider="Western University",
            amount_text=amount_text,
            eligibility=Eligibility(
                level_of_study=["undergraduate"], institutions=["Western University"]
            ),
            fit="good",
        ),
        page_url="https://example.edu/awards",
        page_text="",
        page_links=(),
        verification=verification,
        evidence_quotes=[],
    )


def test_program_uses_parsed_amount_and_labels_unlisted_awards() -> None:
    parsed = build_program(_verified_program("up to $5,000"), _profile())
    assert parsed.amount_max == 5000
    assert parsed.amount_label == "up to $5,000"
    assert parsed.tier == "B"

    unlisted = build_program(_verified_program("Amount depends on need"), _profile())
    assert unlisted.amount_max is None
    assert unlisted.amount_label == "Amount varies"

    confirmed = build_program(_verified_program("$1,000", verification="dated"), _profile())
    assert confirmed.tier == "A"


def test_completion_message_counts_tiers_and_never_shows_zero_dollars() -> None:
    message = completion_message(40, 12, 28)
    assert message == "Found 40 awards: 12 with a confirmed deadline, 28 to check"
    empty = completion_message(0, 0, 0)
    assert "$" not in empty
    assert "0 awards" in empty


def test_drops_message_covers_every_bucket() -> None:
    message = drops_message(
        12,
        {
            "weak_fit": 3,
            "stale_or_unverified": 4,
            "institution": 2,
            "level": 1,
            "not_student_award": 5,
            "duplicate": 9,
        },
    )
    assert message == (
        "Eligible awards: 12. Dropped: 3 weak fit, 4 past-dated, "
        "3 other eligibility, 5 not student awards"
    )
