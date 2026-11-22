"""Deterministic quote, freshness, eligibility and duplicate checks.

Verification is the only place that removes a program: the extraction model
reports facts and fit, and this module proves them against the page text. Quote
comparison is Unicode- and markdown-insensitive, deadlines are rescued only from
the program's own section of a page, and resume evidence must appear verbatim in
the resume text read locally from the PDF.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urlsplit

from ..cleaning import strip_private_use
from ..models import Eligibility, ExtractedProgram, Profile
from .extractor import ExtractedPage

logger = logging.getLogger(__name__)

MAX_DEADLINE_DAYS = 420
MAX_RESUME_EVIDENCE = 6
MAX_QUOTE_CHARS = 220
SECTION_MAX_CHARS = 1_500
DEADLINE_WINDOW_CHARS = 120
MIN_EVIDENCE_CHARS = 8

ALLOWED_LEVEL_TERMS = ("undergraduate", "bachelor", "baccalaureate", "college", "diploma", "associate")
PROVINCE_ALIASES = {
    "on": "ontario",
    "ontario": "ontario",
    "bc": "british columbia",
    "british columbia": "british columbia",
    "ab": "alberta",
    "alberta": "alberta",
    "qc": "quebec",
    "quebec": "quebec",
    "mb": "manitoba",
    "manitoba": "manitoba",
    "sk": "saskatchewan",
    "saskatchewan": "saskatchewan",
    "ns": "nova scotia",
    "nova scotia": "nova scotia",
    "nb": "new brunswick",
    "new brunswick": "new brunswick",
    "nl": "newfoundland and labrador",
    "newfoundland and labrador": "newfoundland and labrador",
    "pe": "prince edward island",
    "prince edward island": "prince edward island",
}
SCHOOL_ALIASES = {
    "university of western ontario": "western university",
    "uwo": "western university",
    "western": "western university",
}
GENERIC_INSTITUTION_MARKERS = (
    "any canadian university",
    "any university",
    "all canadian universities",
    "canadian universities",
    "universities across canada",
    "students across canada",
    "open to students from any",
    "ceab-accredited",
)
YEAR_ALIASES = {
    "1": ("1st", "first", "year 1", "first year", "freshman"),
    "2": ("2nd", "second", "year 2", "second year", "sophomore"),
    "3": ("3rd", "third", "year 3", "third year", "junior"),
    "4": ("4th", "fourth", "year 4", "fourth year", "senior"),
    "5": ("5th", "fifth", "year 5", "fifth year"),
}
YEAR_NUMBER_WORDS = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
}
YEAR_MENTION_RE = re.compile(r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|[1-5])\b")
YEAR_RANGE_RE = re.compile(r"\byears?\s*([1-5])\s*(?:-|to|through)\s*([1-5])\b")
YEAR_RANGE_WORD_RE = re.compile(
    r"\b(first|second|third|fourth|fifth)\s*(?:-|to|through)\s*(first|second|third|fourth|fifth)\b"
)
ENTERING_RE = re.compile(r"\b(entering|incoming|proceeding to|advancing to|continuing into)\b")
AT_LEAST_RE = re.compile(r"\b(or (?:above|older|higher|greater|beyond)|and (?:above|up|over)|at least)\b")
YEAR_OPEN_MARKERS = (
    "any year",
    "all years",
    "all undergraduate years",
    "any level",
    "any undergraduate year",
    "regardless of year",
    "no year requirement",
    "open to all years",
    "continuing students",
    "continuing student",
    "first-year and upper-year",
    "first-year and upper year",
    "first year and upper-year",
)
ENTRANCE_MARKERS = (
    "entrance scholarship",
    "entrance award",
    "entrance bursary",
    "entrance prize",
    "admission scholarship",
    "admission award",
    "incoming student",
    "incoming students",
    "secondary school",
    "high school",
    "entering university for the first time",
    "first-time university",
    "entering first year",
)
CONTINUING_MARKERS = (
    "continuing student",
    "continuing students",
    "current student",
    "current students",
    "returning student",
    "returning students",
    "upper-year",
    "upper year",
)
MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
MONTH_FIRST_RE = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
DAY_FIRST_RE = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{MONTH_PATTERN})\.?,?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
ISO_DATE_RE = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b")
TRIGGER_RE = re.compile(
    r"\b(?:deadline|due|closing date|closes|closed|closing|apply by|applications close|"
    r"application closes|applications due|application deadline|submit by|application dates)\b",
    re.IGNORECASE,
)
ROLLING_PHRASES = (
    "no fixed deadline",
    "no deadline",
    "rolling",
    "year-round",
    "ongoing",
    "accepted throughout the year",
    "accepted at any time",
)
UNKNOWN_WEAK_MARKERS = (
    "unknown",
    "not stated",
    "not specified",
    "unclear",
    "not mentioned",
    "does not state",
    "no information",
    "not provided",
)
QUOTE_SENTENCE_ENDS = (". ", "! ", "? ")
QUOTE_MARKDOWN_BREAKS = ("\n", "###", "##", "#", "**", "__")
PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
QUOTE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u202f": " ",
        "\u2007": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\t": " ",
    }
)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _plain_text(value: str) -> str:
    """Unicode- and markdown-neutral prose used for display quotes."""

    text = unicodedata.normalize("NFKC", strip_private_use(value))
    text = text.translate(QUOTE_TRANSLATION)
    for character in ZERO_WIDTH_CHARS:
        text = text.replace(character, "")
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    for marker in ("**", "__", "`", "##", "#", ">", "*", "_"):
        text = text.replace(marker, "")
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_compare(value: str) -> str:
    """Normalize page text and quotes before a substring comparison."""

    return _plain_text(value).lower()


def clean_display_quote(value: str, limit: int = MAX_QUOTE_CHARS) -> str:
    """Return one readable quote without markdown, capped at the display limit."""

    text = _plain_text(value)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].strip()
    return text


def _quote_ok(quote: str | None, text: str) -> bool:
    if not quote:
        return False
    return normalize_for_compare(quote) in normalize_for_compare(text)


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _provider(program: ExtractedProgram, page_url: str) -> str:
    if program.provider.strip():
        return program.provider.strip()
    return (urlsplit(page_url).hostname or "unknown").removeprefix("www.")


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    lowered = _norm(value)
    return any(term in lowered for term in terms)


def _year_tokens(profile_year: str) -> tuple[str, ...]:
    cleaned = profile_year.strip().lower()
    if cleaned.startswith("grad"):
        return ("graduate", "master", "masters", "phd", "doctoral")
    for number, aliases in YEAR_ALIASES.items():
        if number in cleaned or any(alias in cleaned for alias in aliases):
            return aliases
    return (cleaned,) if cleaned else ()


def _profile_year_number(profile_year: str) -> int | None:
    cleaned = _norm(profile_year)
    if not cleaned or cleaned.startswith("grad"):
        return None
    for number, aliases in YEAR_ALIASES.items():
        if number in cleaned or any(alias in cleaned for alias in aliases):
            return int(number)
    return None


def _year_ranges(value: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = [
        (int(low), int(high)) for low, high in YEAR_RANGE_RE.findall(value)
    ]
    ranges.extend(
        (YEAR_NUMBER_WORDS[low], YEAR_NUMBER_WORDS[high])
        for low, high in YEAR_RANGE_WORD_RE.findall(value)
    )
    return ranges


def _mentioned_years(value: str) -> set[int]:
    return {
        YEAR_NUMBER_WORDS[match.group(1)]
        for match in YEAR_MENTION_RE.finditer(value)
        if match.group(1) in YEAR_NUMBER_WORDS
    }


def _year_matches(items: list[str], profile_year: str) -> bool:
    """Match award year wording against the student's current year.

    "Entering year N" targets a student currently in year N-1; "year N students"
    targets a student currently in year N. Ranges and "or above" wording are
    supported. An item that names no year at all is treated as no restriction,
    because a false negative costs more than a false positive here.
    """

    if not items:
        return True
    if any(_norm(item) in {"all", "any", "all years", "any year", "any level"} for item in items):
        return True
    if any(_contains_any(item, YEAR_OPEN_MARKERS) for item in items):
        return True

    profile_number = _profile_year_number(profile_year)
    tokens = _year_tokens(profile_year)
    for item in items:
        lowered = _norm(item)
        if not lowered:
            continue
        if profile_number is None:
            if _contains_any(item, tokens) or _contains_any(
                item, ("graduate", "master", "phd", "doctoral")
            ):
                return True
            continue
        entering = bool(ENTERING_RE.search(lowered))
        target = profile_number + 1 if entering else profile_number
        ranges = _year_ranges(lowered)
        if ranges:
            if any(low <= target <= high for low, high in ranges):
                return True
            if AT_LEAST_RE.search(lowered) and any(target >= low for low, _ in ranges):
                return True
            continue
        years = _mentioned_years(lowered)
        if years:
            if target in years:
                return True
            if AT_LEAST_RE.search(lowered) and target >= min(years):
                return True
            continue
        return True
    return False


def _canonical_school(value: str) -> str:
    normalized = _norm(value)
    return SCHOOL_ALIASES.get(normalized, normalized)


def _institution_matches(items: list[str], school: str) -> bool:
    if not items:
        return True
    normalized_school = _canonical_school(school)
    for item in items:
        normalized = _norm(item)
        if normalized in {"all", "any", "open to all"}:
            return True
        if any(marker in normalized for marker in GENERIC_INSTITUTION_MARKERS):
            return True
        canonical = SCHOOL_ALIASES.get(normalized, normalized)
        if canonical in normalized_school or normalized_school in canonical:
            return True
    return False


def _province_matches(items: list[str], province: str) -> bool:
    if not items:
        return True
    if any(_norm(item) in {"all", "any", "canada"} for item in items):
        return True
    student = PROVINCE_ALIASES.get(_norm(province), _norm(province))
    for item in items:
        normalized = PROVINCE_ALIASES.get(_norm(item), _norm(item))
        if normalized == student or normalized in student or student in normalized:
            return True
    return False


def _level_matches(items: list[str]) -> bool:
    if not items:
        return True
    if any(_norm(item) in {"all", "any"} for item in items):
        return True
    return any(_contains_any(item, ALLOWED_LEVEL_TERMS) for item in items)


def _citizenship_matches(items: list[str], status: str) -> bool:
    if not items:
        return True
    if any(_norm(item) in {"all", "any", "all students", "open to all"} for item in items):
        return True
    normalized_status = _norm(status)
    status_terms = [normalized_status]
    if "canadian" in normalized_status:
        status_terms.extend(["canada", "domestic", "permanent resident"])
    if "permanent" in normalized_status:
        status_terms.extend(["pr", "permanent resident"])
    for item in items:
        normalized = _norm(item)
        if any(term and (term in normalized or normalized in term) for term in status_terms):
            return True
    return False


def _identity_restricted(items: list[str]) -> bool:
    meaningful = [
        item
        for item in items
        if _norm(item) not in {"none", "no restrictions", "n/a", "not applicable", "all", "any"}
    ]
    return bool(meaningful)


def _cycle_label_matches(label: str | None, today: date) -> bool:
    if not label:
        return False
    lowered = _norm(label)
    year = today.year
    next_year = year + 1
    tokens = (
        f"{year}-{next_year}",
        f"{year}-{str(next_year)[2:]}",
        str(next_year),
        f"{next_year}-{next_year + 1}",
        f"{next_year}-{str(next_year + 1)[2:]}",
    )
    return any(token in lowered for token in tokens)


def _deadline(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _quote_near(text: str, start: int, end: int) -> str:
    """Return one sentence or line around a match, capped and markdown-trimmed."""

    text = strip_private_use(text)
    if not text:
        return ""
    start = max(0, min(start, len(text) - 1))
    end = max(start, min(end, len(text)))
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)

    prefix = text[line_start:start]
    sentence_starts = [prefix.rfind(marker) for marker in QUOTE_SENTENCE_ENDS]
    sentence_start = max(sentence_starts)
    if sentence_start >= 0:
        line_start += sentence_start + 2

    suffix = text[end:line_end]
    cut = len(suffix)
    for marker in (*QUOTE_SENTENCE_ENDS, *QUOTE_MARKDOWN_BREAKS):
        found = suffix.find(marker)
        if found >= 0:
            cut = min(cut, found + (1 if marker in QUOTE_SENTENCE_ENDS else 0))
    finish = end + cut
    quote = text[line_start:finish].strip()

    if len(quote) > MAX_QUOTE_CHARS:
        date_offset = max(0, start - line_start)
        window_start = line_start + max(0, date_offset - 100)
        quote = text[window_start:finish].strip()
        if len(quote) > MAX_QUOTE_CHARS:
            quote = quote[:MAX_QUOTE_CHARS].rsplit(" ", 1)[0].strip()
    return quote


def _deadline_quote(quote: str | None, text: str, deadline: date) -> str:
    """Reduce a model quote to the single line/sentence containing its date."""

    source = strip_private_use(quote or "")
    for parsed, start, end in _date_matches(source):
        if parsed == deadline:
            return clean_display_quote(_quote_near(source, start, end))
    for parsed, start, end in _date_matches(strip_private_use(text)):
        if parsed == deadline:
            return clean_display_quote(_quote_near(text, start, end))
    return clean_display_quote(_quote_near(source, 0, min(len(source), 1)))


def _parse_date(match: re.Match[str]) -> date | None:
    try:
        raw_month = match.group("month")
        month = int(raw_month) if raw_month.isdigit() else MONTHS[raw_month[:3].lower()]
        day = int(match.group("day"))
        year = int(match.group("year"))
        return date(year, month, day)
    except (KeyError, TypeError, ValueError):
        return None


def _date_matches(window: str) -> list[tuple[date, int, int]]:
    found: list[tuple[date, int, int]] = []
    for regex in (MONTH_FIRST_RE, DAY_FIRST_RE, ISO_DATE_RE):
        for match in regex.finditer(window):
            parsed = _parse_date(match)
            if parsed is not None:
                found.append((parsed, match.start(), match.end()))
    return found


def _name_pattern(name: str) -> re.Pattern[str] | None:
    """Build a whitespace- and punctuation-tolerant pattern for a program name."""

    words = re.findall(r"[A-Za-z0-9]+", name)
    if not words:
        return None
    if len(words) == 1 and len(words[0]) < 5:
        return None
    joined = r"[\W_]{0,3}".join(re.escape(word) for word in words)
    return re.compile(joined, re.IGNORECASE)


def _program_section(
    text: str,
    name: str,
    other_names: list[str],
    *,
    single_program: bool,
    max_chars: int = SECTION_MAX_CHARS,
) -> str | None:
    """Return the page text that belongs to one program, or None."""

    if single_program:
        return text
    pattern = _name_pattern(name)
    if pattern is None:
        return None
    match = pattern.search(text)
    if match is None:
        return None
    end = min(len(text), match.end() + max_chars)
    for other in other_names:
        if _name_key(other) == _name_key(name):
            continue
        other_pattern = _name_pattern(other)
        if other_pattern is None:
            continue
        other_match = other_pattern.search(text, match.end())
        if other_match is not None:
            end = min(end, other_match.start())
    return text[match.start() : max(end, match.end())]


@dataclass(frozen=True)
class DeadlineRescue:
    found_dates: bool = False
    date_value: date | None = None
    quote: str | None = None
    section: str | None = None


def _deadline_keyword_dates(source: str) -> list[tuple[date, str]]:
    """Dates within 120 characters after a deadline keyword in one section."""

    found: list[tuple[date, str]] = []
    for trigger in TRIGGER_RE.finditer(source):
        window_start = trigger.end()
        window = source[window_start : window_start + DEADLINE_WINDOW_CHARS]
        for parsed, offset, end_offset in _date_matches(window):
            quote = _quote_near(source, window_start + offset, window_start + end_offset)
            if quote:
                found.append((parsed, quote))
    return found


def _rescue_deadline(
    text: str,
    today: date,
    *,
    program_name: str,
    other_names: list[str],
    single_program: bool = False,
) -> DeadlineRescue:
    """Find a usable deadline inside the program's own section of the page.

    Only dates that follow a deadline keyword in that section count. A section
    with no deadline date of its own is not stale: the program becomes
    unconfirmed. Dates elsewhere on the page (news items, copyright years) are
    never considered.
    """

    section = _program_section(
        text,
        program_name,
        other_names,
        single_program=single_program,
    )
    if section is None:
        return DeadlineRescue()
    source = strip_private_use(section)
    candidates = _deadline_keyword_dates(source)
    if not candidates:
        return DeadlineRescue(section=section)

    usable = [
        (parsed, quote)
        for parsed, quote in candidates
        if today <= parsed <= today + timedelta(days=MAX_DEADLINE_DAYS)
    ]
    if not usable:
        return DeadlineRescue(found_dates=True, section=section)
    parsed, quote = min(usable, key=lambda item: item[0])
    return DeadlineRescue(found_dates=True, date_value=parsed, quote=quote, section=section)


def _rolling_quote(program: ExtractedProgram, text: str, section: str | None) -> str | None:
    """Return a rolling/no-deadline quote from the program's own section."""

    if program.rolling and program.rolling_quote and _quote_ok(program.rolling_quote, text):
        raw = strip_private_use(program.rolling_quote)
        source = strip_private_use(section) if section else strip_private_use(text)
        offset = source.find(raw)
        quote = _quote_near(source, offset, offset + len(raw)) if offset >= 0 else raw
        cleaned = clean_display_quote(quote)
        if len(cleaned) >= 20:
            return cleaned
    if not section:
        return None
    source = strip_private_use(section)
    lowered = source.lower()
    for phrase in ROLLING_PHRASES:
        match = re.search(rf"\b{re.escape(phrase)}\b", lowered)
        if match is not None:
            quote = clean_display_quote(_quote_near(source, match.start(), match.end()))
            if quote and len(quote) >= 20:
                return quote
    return None


def _clean_program(program: ExtractedProgram, text: str) -> ExtractedProgram:
    deadlines = [
        deadline
        for deadline in program.deadlines
        if deadline.date_iso and deadline.quote and _quote_ok(deadline.quote, text)
    ]
    rolling_quote = program.rolling_quote if _quote_ok(program.rolling_quote, text) else None
    open_quote = program.open_status_quote if _quote_ok(program.open_status_quote, text) else None
    quotes = [quote for quote in program.eligibility_quotes if _quote_ok(quote, text)]
    fit = program.fit
    if fit == "strong" and len(program.matched_on) < 2:
        fit = "good"
    if fit == "weak":
        weak_reason = _norm(program.weak_reason)
        if not weak_reason or any(marker in weak_reason for marker in UNKNOWN_WEAK_MARKERS):
            fit = "good"
    return _sets_null(
        program,
        deadlines=deadlines,
        rolling_quote=rolling_quote,
        open_status_quote=open_quote,
        rolling=program.rolling if rolling_quote else False,
        eligibility_quotes=quotes,
        fit=fit,
        weak_reason=program.weak_reason if fit == "weak" else "",
        resume_evidence=[
            clean_display_quote(quote) for quote in program.resume_evidence if clean_display_quote(quote)
        ],
    )


def _looks_like_phone(value: str) -> bool:
    for match in PHONE_RE.finditer(value):
        if len(re.sub(r"\D", "", match.group(0))) >= 10:
            return True
    return False


def _clean_resume_evidence(items: list[str], resume_text: str) -> list[str]:
    """Keep only verbatim resume lines without contact details."""

    if not resume_text:
        return []
    haystack = normalize_for_compare(resume_text)
    kept: list[str] = []
    for item in items:
        line = clean_display_quote(item)
        if len(line) < MIN_EVIDENCE_CHARS:
            continue
        if "@" in line or _looks_like_phone(line):
            continue
        if normalize_for_compare(line) not in haystack:
            continue
        if line not in kept:
            kept.append(line)
        if len(kept) >= MAX_RESUME_EVIDENCE:
            break
    return kept


def _is_entrance_award(program: ExtractedProgram) -> bool:
    """True for awards aimed at high-school or first-time university entrants.

    These are never suitable for a student already enrolled in a university
    program, whatever year they are in. Awards that explicitly continue a
    current student's funding are excluded from this rule.
    """

    eligibility = program.eligibility
    # Description is deliberately excluded: list pages often mention their
    # entrance awards in the same paragraph as the undergraduate awards.
    blob = " ".join(
        [
            program.name,
            *eligibility.level_of_study,
            *eligibility.year_of_study,
            *eligibility.institutions,
            program.weak_reason,
        ]
    )
    lowered = _norm(blob)
    if any(marker in lowered for marker in CONTINUING_MARKERS):
        return False
    return any(marker in lowered for marker in ENTRANCE_MARKERS)


def _eligibility_reason(program: ExtractedProgram, profile: Profile) -> str | None:
    eligibility: Eligibility = program.eligibility
    if not _institution_matches(eligibility.institutions, profile.school):
        return "institution"
    if not _province_matches(eligibility.provinces, profile.province):
        return "province"
    if not _level_matches(eligibility.level_of_study):
        return "level"
    if not _year_matches(eligibility.year_of_study, profile.year):
        return "year"
    if not _citizenship_matches(eligibility.citizenship, profile.status):
        return "citizenship"
    if _identity_restricted(eligibility.identity_restrictions):
        return "identity_restriction"
    return None


def _choose_model_deadline(program: ExtractedProgram, today: date) -> tuple[date, str, str | None] | None:
    usable: list[tuple[date, str, str | None]] = []
    for extracted in program.deadlines:
        parsed = _deadline(extracted.date_iso)
        if parsed is not None and today <= parsed <= today + timedelta(days=MAX_DEADLINE_DAYS):
            usable.append((parsed, extracted.quote or "", extracted.label))
    if not usable:
        return None
    return min(usable, key=lambda item: item[0])


def _sets_null(program: ExtractedProgram, **updates: object) -> ExtractedProgram:
    return program.model_copy(update=updates)


@dataclass
class VerifyState:
    """Cross-round duplicate tracking; each tier has its own seen set."""

    seen: set[tuple[str, str]] = field(default_factory=set)
    unconfirmed_seen: set[tuple[str, str]] = field(default_factory=set)


@dataclass(frozen=True)
class WeakFitExample:
    name: str
    provider: str
    url: str
    weak_reason: str
    gaps: list[str]
    matched_on: list[str]


@dataclass
class VerifiedProgram:
    program: ExtractedProgram
    page_url: str
    page_text: str
    page_links: tuple[str, ...]
    verification: str
    evidence_quotes: list[str]
    deadline_iso: str | None = None
    deadline_quote: str | None = None
    deadline_label: str | None = None
    deadline_rescued: bool = False


@dataclass(frozen=True)
class DropRecord:
    """One discarded program, in the shape the diagnostics file stores."""

    name: str
    provider: str
    url: str
    reason: str
    detail: str = ""


@dataclass
class VerifyResult:
    verified: list[VerifiedProgram] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    weak_fit_examples: list[WeakFitExample] = field(default_factory=list)
    drop_records: list[DropRecord] = field(default_factory=list)


MAX_DROP_RECORDS = 200


def _drop(dropped: dict[str, int], reason: str) -> None:
    dropped[reason] = dropped.get(reason, 0) + 1


def _nearby_date_text(text: str, name: str) -> str:
    """Return the date text within 200 characters of the program name."""

    if not text or not name:
        return ""
    index = text.lower().find(name.strip().lower()[:80])
    if index < 0:
        window = text[:400]
    else:
        window = text[max(0, index - 200) : index + len(name) + 200]
    matches = _date_matches(strip_private_use(window))
    if not matches:
        return ""
    _, start, end = matches[0]
    return " ".join(window[start:end].split())[:200]


def _drop_program(
    result: VerifyResult,
    program: ExtractedProgram,
    url: str,
    reason: str,
    text: str = "",
    detail: str = "",
) -> None:
    """Count a drop and keep a contact-free record of why it happened."""

    _drop(result.dropped, reason)
    if len(result.drop_records) >= MAX_DROP_RECORDS:
        return
    extra = detail or (program.weak_reason if reason == "weak_fit" else "")
    if reason == "stale_or_unverified" and not extra:
        extra = _nearby_date_text(text, program.name)
    result.drop_records.append(
        DropRecord(
            name=program.name,
            provider=_provider(program, url),
            url=url,
            reason=reason,
            detail=" ".join(extra.split())[:200],
        )
    )


def verify_pages(
    pages: list[ExtractedPage],
    profile: Profile,
    state: VerifyState,
    today: date | None = None,
    resume_text: str = "",
) -> VerifyResult:
    """Verify quotes, freshness, eligibility and duplicates across rounds."""

    current = today or date.today()
    result = VerifyResult()
    for extracted_page in pages:
        text = extracted_page.page.text
        page_names = [program.name for program in extracted_page.programs]
        single_program = len(page_names) <= 1
        for raw_program in extracted_page.programs:
            program = _clean_program(raw_program, text)
            program = _sets_null(
                program,
                resume_evidence=_clean_resume_evidence(program.resume_evidence, resume_text),
            )
            if not program.student_award:
                _drop_program(result, program, extracted_page.page.url, "not_student_award")
                continue
            if _is_entrance_award(program):
                _drop_program(result, program, extracted_page.page.url, "entrance_award")
                continue
            if program.fit == "weak":
                _drop_program(
                    result,
                    program,
                    extracted_page.page.url,
                    "weak_fit",
                    text,
                )
                if len(result.weak_fit_examples) < 12:
                    result.weak_fit_examples.append(
                        WeakFitExample(
                            name=program.name,
                            provider=_provider(program, extracted_page.page.url),
                            url=extracted_page.page.url,
                            weak_reason=program.weak_reason,
                            gaps=list(program.gaps),
                            matched_on=list(program.matched_on),
                        )
                    )
                continue
            reason = _eligibility_reason(program, profile)
            if reason is not None:
                _drop_program(result, program, extracted_page.page.url, reason, text)
                continue

            chosen = _choose_model_deadline(program, current)
            verification: str | None = None
            deadline_iso: str | None = None
            deadline_quote: str | None = None
            deadline_label: str | None = None
            rescued = False
            section: str | None = None

            if chosen is not None:
                deadline_value, quote, label = chosen
                deadline_iso = deadline_value.isoformat()
                deadline_quote = _deadline_quote(quote, text, deadline_value)
                deadline_label = label
                verification = "dated"
            else:
                rescue = _rescue_deadline(
                    text,
                    current,
                    program_name=program.name,
                    other_names=page_names,
                    single_program=single_program,
                )
                section = rescue.section
                if rescue.found_dates and rescue.date_value is None:
                    _drop_program(
                        result,
                        program,
                        extracted_page.page.url,
                        "stale_or_unverified",
                        text,
                    )
                    continue
                if rescue.date_value is not None and rescue.quote:
                    deadline_iso = rescue.date_value.isoformat()
                    deadline_quote = clean_display_quote(rescue.quote)
                    verification = "dated"
                    rescued = True

            if verification is None:
                rolling_quote = _rolling_quote(program, text, section)
                if rolling_quote:
                    deadline_quote = rolling_quote
                    verification = "rolling"
                elif _cycle_label_matches(program.cycle_label, current) and program.open_status_quote:
                    verification = "cycle"

            if verification is None:
                verification = "unconfirmed"
                deadline_label = "Deadline not confirmed"

            provider = _provider(program, extracted_page.page.url)
            key = (_name_key(program.name), _name_key(provider))
            if verification == "unconfirmed":
                if key in state.unconfirmed_seen:
                    _drop_program(
                        result,
                        program,
                        extracted_page.page.url,
                        "duplicate",
                        text,
                    )
                    continue
                state.unconfirmed_seen.add(key)
            else:
                if key in state.seen:
                    _drop_program(
                        result,
                        program,
                        extracted_page.page.url,
                        "duplicate",
                        text,
                    )
                    continue
                state.seen.add(key)

            quotes: list[str] = []
            for evidence_quote in (
                deadline_quote,
                program.open_status_quote,
                *program.eligibility_quotes,
            ):
                cleaned_quote = clean_display_quote(evidence_quote) if evidence_quote else ""
                if cleaned_quote and cleaned_quote not in quotes:
                    quotes.append(cleaned_quote)
            result.verified.append(
                VerifiedProgram(
                    program=program,
                    page_url=extracted_page.page.url,
                    page_text=text,
                    page_links=tuple(extracted_page.page.links),
                    verification=verification,
                    evidence_quotes=quotes,
                    deadline_iso=deadline_iso,
                    deadline_quote=deadline_quote,
                    deadline_label=deadline_label,
                    deadline_rescued=rescued,
                )
            )

    logger.info(
        "verify verified=%d unconfirmed=%d dropped=%s",
        sum(1 for item in result.verified if item.verification != "unconfirmed"),
        sum(1 for item in result.verified if item.verification == "unconfirmed"),
        result.dropped,
    )
    return result
