"""Pydantic models shared by the API, agents, extractor, verifier and matcher.

All public models use camelCase aliases so responses match the frontend
contract. Internally the code works with snake_case attributes.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from .cleaning import clean_value

Category: TypeAlias = Literal[
    "scholarship",
    "bursary",
    "award",
    "fellowship",
    "research_award",
    "competition_prize",
]
Verification: TypeAlias = Literal["dated", "rolling", "cycle", "unconfirmed"]
PrefillKey: TypeAlias = Literal["fullName", "province", "school", "field", "year", "incomeRange", "status"]
FieldType: TypeAlias = Literal["text", "textarea", "select"]
Fit: TypeAlias = Literal["strong", "good", "weak"]

CATEGORIES: frozenset[str] = frozenset(
    {
        "scholarship",
        "bursary",
        "award",
        "fellowship",
        "research_award",
        "competition_prize",
    }
)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def category_value(value: object) -> str:
    """Coerce a model value to the award-category enum.

    Persisted hunts from before the enum existed stored ``grant``, ``tax_credit``
    and ``other``; they stay loadable as ``award``.
    """

    cleaned = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned in CATEGORIES:
        return cleaned
    return "award"


def _coerce_iso_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 10:
        cleaned = cleaned[:10]
    if not ISO_DATE.match(cleaned):
        return None
    try:
        date.fromisoformat(cleaned)
    except ValueError:
        return None
    return cleaned


class ApiModel(BaseModel):
    """Base for models exposed over the API."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        extra="ignore",
    )


class CleanTextModel(ApiModel):
    """Strip private-use glyphs from every text field before it is stored."""

    @model_validator(mode="after")
    def _strip_private_use(self) -> CleanTextModel:
        for name in type(self).model_fields:
            value = getattr(self, name)
            cleaned = clean_value(value)
            if cleaned is not value:
                object.__setattr__(self, name, cleaned)
        return self


class ResumePayload(ApiModel):
    """A PDF resume sent as a data URL so Gemini can read it directly."""

    name: str = ""
    data_url: str = ""


class ResumePreview(ApiModel):
    """Stateless summary returned by /api/resume/preview."""

    characters: int = 0
    strengths: list[str] = Field(default_factory=list)
    angles: list[str] = Field(default_factory=list)
    stated_school: str | None = None
    stated_program: str | None = None
    stated_year: str | None = None


class Profile(ApiModel):
    full_name: str
    province: str
    school: str
    field: str
    year: str
    income_range: str
    status: str
    resume: ResumePayload | None = None


class FormField(ApiModel):
    """Retained for API compatibility; programs never generate these now."""

    id: str
    label: str
    type: FieldType
    required: bool
    options: list[str] | None = None
    prefill_key: PrefillKey | None = None
    max_chars: int | None = None


class Program(CleanTextModel):
    id: str
    name: str
    provider: str
    source_site_id: str
    source_site: str
    url: str
    apply_url: str
    apply_url_is_aggregator: bool = False
    amount_max: float | None = None
    amount_label: str
    deadline: str | None = None
    deadline_label: str | None = None
    verification: Verification
    fit: Fit
    deadline_quote: str | None = None
    evidence_quotes: list[str] = Field(default_factory=list)
    resume_evidence: list[str] = Field(default_factory=list)
    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    about: str
    education_level: list[str]
    requirements: list[str]
    why_qualify: str
    next_step: str
    matched_on: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    weak_reason: str = ""
    model_id: str = ""
    form_fields: list[FormField] = Field(default_factory=list)
    from_cache: bool = False
    checked_at: datetime
    found_at: datetime

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, value: object) -> str:
        return category_value(value)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tier(self) -> Literal["A", "B"]:
        """Tier A has a confirmed deadline or cycle; tier B needs a date check."""

        return "B" if self.verification == "unconfirmed" else "A"


class Eligibility(CleanTextModel):
    level_of_study: list[str] = Field(default_factory=list)
    year_of_study: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    provinces: list[str] = Field(default_factory=list)
    fields_of_study: list[str] = Field(default_factory=list)
    citizenship: list[str] = Field(default_factory=list)
    identity_restrictions: list[str] = Field(default_factory=list)
    financial_need: str | None = None
    min_grade_text: str | None = None

    @field_validator(
        "level_of_study",
        "year_of_study",
        "institutions",
        "provinces",
        "fields_of_study",
        "citizenship",
        "identity_restrictions",
        mode="before",
    )
    @classmethod
    def _coerce_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[\n;,]+", value) if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


class ExtractedDeadline(CleanTextModel):
    """One deadline candidate returned by the model."""

    date_iso: str | None = None
    quote: str | None = None
    label: str | None = None

    @field_validator("date_iso", mode="before")
    @classmethod
    def _coerce_date_iso(cls, value: object) -> str | None:
        return _coerce_iso_date(value)

    @field_validator("quote", "label", mode="before")
    @classmethod
    def _coerce_text(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class ExtractedProgram(CleanTextModel):
    """One program extracted from a single page by Gemini."""

    name: str
    provider: str = ""
    description: str = ""
    amount_text: str | None = None
    amount_max: float | None = None
    deadlines: list[ExtractedDeadline] = Field(default_factory=list)
    cycle_label: str | None = None
    rolling: bool = False
    rolling_quote: str | None = None
    open_status_quote: str | None = None
    apply_url: str | None = None
    how_to_apply: str | None = None
    eligibility: Eligibility = Field(default_factory=Eligibility)
    eligibility_quotes: list[str] = Field(default_factory=list)
    fit: Fit = "weak"
    confidence: float = 0.5
    matched_on: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    why_qualify: str = ""
    next_step: str = ""
    weak_reason: str = ""
    category: Category = "scholarship"
    student_award: bool = True
    resume_evidence: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _require_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("program name is empty")
        return cleaned

    @field_validator("amount_max", mode="before")
    @classmethod
    def _coerce_amount(cls, value: object) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            digits = re.sub(r"[^0-9.]", "", value)
            if not digits:
                return None
            try:
                return float(digits)
            except ValueError:
                return None
        return None

    @field_validator("rolling", "student_award", mode="before")
    @classmethod
    def _coerce_bool(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "y", "1"}
        return False

    @field_validator("eligibility_quotes", mode="before")
    @classmethod
    def _coerce_quotes(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator("fit", mode="before")
    @classmethod
    def _normalise_fit(cls, value: object) -> str:
        cleaned = str(value or "").strip().lower()
        return cleaned if cleaned in {"strong", "good", "weak"} else "weak"

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_confidence(cls, value: object) -> float:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.5
        if number > 1.0:
            number = number / 100.0 if number <= 100.0 else 1.0
        return max(0.0, min(1.0, number))

    @field_validator("why_qualify", "next_step", "weak_reason", mode="before")
    @classmethod
    def _coerce_match_text(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, value: object) -> str:
        return category_value(value)

    @field_validator("matched_on", "gaps", "resume_evidence", mode="before")
    @classmethod
    def _coerce_match_lists(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


class ListedAward(ApiModel):
    name: str
    detail_url: str | None = None

    @field_validator("name")
    @classmethod
    def _require_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("award name is empty")
        return cleaned


class PageExtraction(ApiModel):
    index: int
    is_list_page: bool = False
    programs: list[ExtractedProgram] = Field(default_factory=list)


class MatchJudgement(ApiModel):
    index: int
    fit: str = "weak"
    confidence: float = 0.5
    matched_on: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    why_qualify: str = ""
    next_step: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_confidence(cls, value: object) -> float:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.5
        if number > 1.0:
            number = number / 100.0 if number <= 100.0 else 1.0
        return max(0.0, min(1.0, number))

    @field_validator("fit", mode="before")
    @classmethod
    def _normalise_fit(cls, value: object) -> str:
        cleaned = str(value or "").strip().lower()
        return cleaned if cleaned in {"strong", "good", "weak"} else "weak"

    @field_validator("why_qualify", "next_step", mode="before")
    @classmethod
    def _coerce_text(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("matched_on", "gaps", mode="before")
    @classmethod
    def _coerce_criteria(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


class HuntEventBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    type: str = ""
    t: float | None = None


class SiteStartedEvent(HuntEventBase):
    type: Literal["site_started"] = "site_started"
    site_id: str
    site_name: str
    streaming_url: str | None = None


class SiteProgressEvent(HuntEventBase):
    type: Literal["site_progress"] = "site_progress"
    site_id: str
    message: str
    count: int | None = None


class ProgramFoundEvent(HuntEventBase):
    type: Literal["program_found"] = "program_found"
    program: Program


class SiteDoneEvent(HuntEventBase):
    type: Literal["site_done"] = "site_done"
    site_id: str
    count: int


class SiteFailedEvent(HuntEventBase):
    type: Literal["site_failed"] = "site_failed"
    site_id: str
    used_cache: bool = False


class HuntErrorEvent(HuntEventBase):
    type: Literal["hunt_error"] = "hunt_error"
    message: str


class HuntCompleteEvent(HuntEventBase):
    type: Literal["hunt_complete"] = "hunt_complete"
    total_amount: float
    program_count: int
    verified_count: int = 0
    unconfirmed_count: int = 0


HuntEvent: TypeAlias = Annotated[
    SiteStartedEvent | SiteProgressEvent | ProgramFoundEvent | SiteDoneEvent | SiteFailedEvent | HuntErrorEvent | HuntCompleteEvent,
    Field(discriminator="type"),
]

TERMINAL_EVENT_TYPES: frozenset[str] = frozenset({"hunt_complete", "hunt_error"})


class StartHuntResponse(ApiModel):
    hunt_id: str


class HuntMeta(ApiModel):
    """Small, contact-free description of a saved hunt."""

    hunt_id: str
    status: str
    started_at: str | None = None
    elapsed_seconds: float | None = None


def event_json(event: HuntEventBase) -> str:
    """Serialise one event as a single JSON line."""

    return event.model_dump_json(by_alias=True, exclude_none=True)


def utc_now() -> datetime:
    return datetime.now(UTC)
