"""Build the public Program from one verified page extraction."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlsplit

from ..models import CATEGORIES, Category, Profile, Program, utc_now
from .amounts import parse_amount_text
from .discovery import is_blocked_url, is_government_url
from .verify import VerifiedProgram

GENERIC_PROVIDER_WORDS = frozenset(
    {
        "award",
        "awards",
        "bursary",
        "canada",
        "college",
        "community",
        "foundation",
        "fund",
        "grant",
        "inc",
        "program",
        "scholarship",
        "scholarships",
        "society",
        "trust",
        "university",
    }
)


def _category(name: str, description: str) -> Category:
    """Fallback classification when extraction did not return a category."""

    lowered = f"{name} {description}".lower()
    if "bursary" in lowered:
        return "bursary"
    if "fellowship" in lowered:
        return "fellowship"
    if "research award" in lowered or "research scholarship" in lowered:
        return "research_award"
    if "competition" in lowered or "prize" in lowered:
        return "competition_prize"
    if "scholarship" in lowered:
        return "scholarship"
    return "award"


def _resolved_category(extracted: object) -> Category:
    value = str(getattr(extracted, "category", "")).strip()
    if value in CATEGORIES:
        return value  # type: ignore[return-value]
    return _category(
        str(getattr(extracted, "name", "")),
        str(getattr(extracted, "description", "")),
    )


def _program_id(page_url: str, name: str, provider: str) -> str:
    digest = hashlib.sha1(f"{page_url}|{name.lower()}|{provider.lower()}".encode()).hexdigest()
    return digest[:16]


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "unknown").removeprefix("www.")


def _provider_tokens(provider: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", provider.lower())
    tokens: list[str] = []
    for word in words:
        if len(word) < 4 or word in GENERIC_PROVIDER_WORDS or word in tokens:
            continue
        tokens.append(word)
    return tokens


def _provider_link(page_url: str, links: tuple[str, ...], provider: str) -> str | None:
    """Find an outbound link whose host or path matches the provider's name."""

    tokens = _provider_tokens(provider)
    if not tokens:
        return None
    page_host = _host(page_url)
    best: str | None = None
    best_score = 0
    for raw in links:
        if not raw.strip():
            continue
        resolved = urljoin(page_url, raw.strip())
        parsed = urlsplit(resolved)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        host = _host(resolved)
        if host == page_host or is_blocked_url(resolved) or is_government_url(resolved):
            continue
        host_key = re.sub(r"[^a-z0-9]+", "", host)
        path_key = re.sub(r"[^a-z0-9]+", "", parsed.path.lower())
        score = 0
        for token in tokens:
            if token in host_key:
                score += 4
            if token in path_key:
                score += 2
        if score > best_score:
            best = resolved
            best_score = score
    return best


def _requirements(verified: VerifiedProgram) -> list[str]:
    program = verified.program
    if program.eligibility_quotes:
        return program.eligibility_quotes[:6]
    eligibility = program.eligibility
    lines: list[str] = []
    for label, values in (
        ("Level", eligibility.level_of_study),
        ("Year", eligibility.year_of_study),
        ("School", eligibility.institutions),
        ("Province", eligibility.provinces),
        ("Field", eligibility.fields_of_study),
        ("Citizenship", eligibility.citizenship),
        ("Identity", eligibility.identity_restrictions),
    ):
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    if eligibility.financial_need:
        lines.append(f"Financial need: {eligibility.financial_need}")
    if eligibility.min_grade_text:
        lines.append(f"Grade: {eligibility.min_grade_text}")
    return lines[:6]


def build_program(verified: VerifiedProgram, profile: Profile, model_id: str = "") -> Program:
    """Convert verified extraction fields into the API/evidence shape."""

    del profile  # kept in the signature because fit already carries profile facts
    extracted = verified.program
    provider = extracted.provider.strip() or _host(verified.page_url)
    url = verified.page_url
    provider_link = _provider_link(url, verified.page_links, provider)
    apply_url = provider_link or url
    apply_url_is_aggregator = provider_link is None
    description = extracted.description.strip()
    about = f"{description} How to apply: {extracted.how_to_apply.strip()}" if extracted.how_to_apply else description
    deadline = verified.deadline_iso if verified.verification == "dated" else None
    deadline_label = verified.deadline_label
    if verified.verification == "rolling":
        deadline_label = "Rolling"
    elif verified.verification == "cycle":
        deadline_label = extracted.cycle_label or "Current cycle"
    elif verified.verification == "unconfirmed":
        deadline_label = "Deadline not confirmed"
    amount_max = extracted.amount_max
    if amount_max is None:
        amount_max = parse_amount_text(extracted.amount_text)
    amount_label = (extracted.amount_text or "").strip()
    if amount_max is None:
        amount_label = "Amount varies"
    elif not amount_label:
        amount_label = f"Up to ${amount_max:,.0f}"
    now = utc_now()
    why = extracted.why_qualify.strip()
    if not why:
        why = "The verified page criteria and your profile line up; confirm the remaining details on the official page."
    next_step = extracted.next_step.strip() or "Open the official page to confirm eligibility and apply."
    return Program(
        id=_program_id(url, extracted.name, provider),
        name=extracted.name,
        provider=provider,
        source_site_id=_host(url),
        source_site=provider,
        url=url,
        apply_url=apply_url,
        apply_url_is_aggregator=apply_url_is_aggregator,
        amount_max=amount_max,
        amount_label=amount_label,
        deadline=deadline,
        deadline_label=deadline_label,
        verification=verified.verification,  # type: ignore[arg-type]
        fit=extracted.fit,
        deadline_quote=verified.deadline_quote,
        evidence_quotes=verified.evidence_quotes,
        resume_evidence=extracted.resume_evidence,
        category=_resolved_category(extracted),
        confidence=extracted.confidence,
        description=description,
        about=about,
        education_level=extracted.eligibility.level_of_study,
        requirements=_requirements(verified),
        why_qualify=why,
        next_step=next_step,
        matched_on=extracted.matched_on,
        gaps=extracted.gaps,
        weak_reason=extracted.weak_reason,
        model_id=model_id,
        form_fields=[],
        from_cache=False,
        checked_at=now,
        found_at=now,
    )
