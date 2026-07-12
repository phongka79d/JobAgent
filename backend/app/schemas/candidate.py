"""Authoritative Candidate Profile and skill contracts (Plan 4 §7.2).

Implements exact Master Plan §7.1 / §7.2 named fields for ``SkillRef``,
``CandidateSkill``, and ``CandidateProfile``.

Nested ``ExperienceItem``, ``EducationItem``, and ``LanguageItem`` field names
are **not** enumerated by Plan 4 or the Master Plan. This module owns the
smallest explicit inventory that carries only displayable CV facts plus short
source evidence. It deliberately omits:

- address-derived or inferred job preferences
- scoring / ranking / match fields
- graph trust (``RELATED_TO``, verified-edge weight, etc.)
- raw document bodies, bytes, or storage paths
- provider-control or repair-loop fields

Opaque provider extras are rejected via ``extra="forbid"`` on every model.
"""

from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Bounds (display + evidence only; not scoring ceilings)
# ---------------------------------------------------------------------------

MAX_CANONICAL_KEY_LEN: Final[int] = 128
MAX_DISPLAY_NAME_LEN: Final[int] = 256
MAX_CATEGORY_LEN: Final[int] = 128
MAX_SUMMARY_LEN: Final[int] = 4_000
MAX_TITLE_LEN: Final[int] = 256
MAX_ORG_LEN: Final[int] = 256
MAX_DATE_RANGE_LEN: Final[int] = 64
MAX_ITEM_SUMMARY_LEN: Final[int] = 2_000
MAX_LANGUAGE_NAME_LEN: Final[int] = 128
MAX_LANGUAGE_PROFICIENCY_LEN: Final[int] = 64
MAX_CREDENTIAL_LEN: Final[int] = 256
MAX_FIELD_OF_STUDY_LEN: Final[int] = 256

MAX_EVIDENCE_SNIPPET_LEN: Final[int] = 256
MAX_EVIDENCE_ITEMS: Final[int] = 8
MAX_ALIASES: Final[int] = 32
MAX_SKILLS: Final[int] = 100
MAX_EXPERIENCES: Final[int] = 50
MAX_EDUCATION_ITEMS: Final[int] = 30
MAX_LANGUAGES: Final[int] = 20

# Years are display estimates only; absurd magnitudes fail closed.
MAX_YEARS: Final[float] = 80.0

# Timeline evidence must show a date range, calendar year(s), or explicit
# duration — not an arbitrary nonempty evidence string (Plan 4 §7.2 /
# Master §7.2: precise years require timeline evidence).
_YEAR_TOKEN: Final[re.Pattern[str]] = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_YEAR_RANGE: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)(?:19|20)\d{2}\s*[-–—/to]+\s*(?:(?:19|20)\d{2}|present|now|current)"
    r"|(?:present|now|current)\s*[-–—/to]+\s*(?:19|20)\d{2}",
    re.IGNORECASE,
)
_DURATION_YEARS: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)\d{1,2}(?:\.\d+)?\s*(?:\+)?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_MONTH_YEAR: Final[re.Pattern[str]] = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)


def _text_has_timeline_evidence(text: str) -> bool:
    """Return True when *text* contains calendar/duration timeline cues."""
    snippet = text.strip()
    if not snippet:
        return False
    if _YEAR_RANGE.search(snippet):
        return True
    if _DURATION_YEARS.search(snippet):
        return True
    if _MONTH_YEAR.search(snippet):
        return True
    if _YEAR_TOKEN.search(snippet):
        return True
    return False


def _evidence_list_has_timeline(evidence: list[str]) -> bool:
    return any(_text_has_timeline_evidence(item) for item in evidence)


class SkillStatus(StrEnum):
    """Whether a skill alias is seed-verified or provisional."""

    VERIFIED = "verified"
    PROVISIONAL = "provisional"


class SkillProficiency(StrEnum):
    """Candidate skill proficiency; ``unknown`` is an explicit allowed value."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    UNKNOWN = "unknown"


class SkillSource(StrEnum):
    """Provenance of a CandidateSkill row."""

    CV = "cv"
    USER_CORRECTION = "user_correction"


class CandidateSchemaBase(BaseModel):
    """Shared strict config for Candidate domain documents."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _require_finite(value: float, *, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _validate_confidence(value: float) -> float:
    number = _require_finite(value, field_name="confidence")
    if number < 0.0 or number > 1.0:
        raise ValueError("confidence must be in [0, 1]")
    return number


def _validate_years(value: float | None, *, field_name: str = "years") -> float | None:
    if value is None:
        return None
    number = _require_finite(value, field_name=field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    if number > MAX_YEARS:
        raise ValueError(f"{field_name} exceeds maximum")
    return number


def _normalize_evidence(value: list[str]) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("evidence must be a list of short strings")
    if len(value) > MAX_EVIDENCE_ITEMS:
        raise ValueError("too many evidence snippets")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("evidence items must be strings")
        snippet = item.strip()
        if not snippet:
            raise ValueError("evidence snippets must be non-empty")
        if len(snippet) > MAX_EVIDENCE_SNIPPET_LEN:
            raise ValueError("evidence snippet too long")
        cleaned.append(snippet)
    return cleaned


def _normalize_string_list(
    value: list[str],
    *,
    max_items: int,
    max_item_len: int,
    field_name: str,
    allow_empty_list: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    if len(value) > max_items:
        raise ValueError(f"too many {field_name} items")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} items must be strings")
        text = item.strip()
        if not text:
            raise ValueError(f"{field_name} items must be non-empty")
        if len(text) > max_item_len:
            raise ValueError(f"{field_name} item too long")
        cleaned.append(text)
    if not allow_empty_list and not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned


class SkillRef(CandidateSchemaBase):
    """Shared skill identity, aliases, status, confidence, and evidence."""

    canonical_key: str = Field(..., min_length=1, max_length=MAX_CANONICAL_KEY_LEN)
    display_name: str = Field(..., min_length=1, max_length=MAX_DISPLAY_NAME_LEN)
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)
    category: str | None = Field(default=None, max_length=MAX_CATEGORY_LEN)
    status: SkillStatus
    confidence: float
    evidence: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)

    @field_validator("canonical_key", "display_name")
    @classmethod
    def _require_nonblank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()

    @field_validator("category")
    @classmethod
    def _optional_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, value: list[str]) -> list[str]:
        return _normalize_string_list(
            value,
            max_items=MAX_ALIASES,
            max_item_len=MAX_DISPLAY_NAME_LEN,
            field_name="aliases",
        )

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _validate_confidence(value)

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: list[str]) -> list[str]:
        return _normalize_evidence(value)


class CandidateSkill(CandidateSchemaBase):
    """One skill on a Candidate Profile with proficiency, years, and source."""

    skill: SkillRef
    proficiency: SkillProficiency
    years: float | None = None
    source: SkillSource
    excluded: bool = False
    evidence: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)

    @field_validator("years")
    @classmethod
    def _years(cls, value: float | None) -> float | None:
        return _validate_years(value, field_name="years")

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: list[str]) -> list[str]:
        return _normalize_evidence(value)

    @model_validator(mode="after")
    def _precise_years_require_timeline_evidence(self) -> CandidateSkill:
        # Precise years require actual timeline cues (date range, year, or
        # explicit duration). Arbitrary nonempty evidence is not enough;
        # callers represent unknown by omitting years.
        if self.years is not None and not _evidence_list_has_timeline(self.evidence):
            raise ValueError(
                "precise years require timeline evidence; use years=null for unknown"
            )
        return self


class ExperienceItem(CandidateSchemaBase):
    """Smallest display-fact experience row + short source evidence.

    Source inventory gap (documented, not invented mandatory fields beyond
    display/evidence): title, organization, date_range, summary, evidence only.
    """

    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    organization: str | None = Field(default=None, max_length=MAX_ORG_LEN)
    date_range: str | None = Field(default=None, max_length=MAX_DATE_RANGE_LEN)
    summary: str | None = Field(default=None, max_length=MAX_ITEM_SUMMARY_LEN)
    evidence: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)

    @field_validator("title", "organization", "date_range", "summary")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: list[str]) -> list[str]:
        return _normalize_evidence(value)


class EducationItem(CandidateSchemaBase):
    """Smallest display-fact education row + short source evidence."""

    institution: str | None = Field(default=None, max_length=MAX_ORG_LEN)
    credential: str | None = Field(default=None, max_length=MAX_CREDENTIAL_LEN)
    field_of_study: str | None = Field(default=None, max_length=MAX_FIELD_OF_STUDY_LEN)
    date_range: str | None = Field(default=None, max_length=MAX_DATE_RANGE_LEN)
    evidence: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)

    @field_validator("institution", "credential", "field_of_study", "date_range")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: list[str]) -> list[str]:
        return _normalize_evidence(value)


class LanguageItem(CandidateSchemaBase):
    """Smallest display-fact language row + short source evidence."""

    language: str = Field(..., min_length=1, max_length=MAX_LANGUAGE_NAME_LEN)
    proficiency: str | None = Field(
        default=None,
        max_length=MAX_LANGUAGE_PROFICIENCY_LEN,
    )
    evidence: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("language must be a non-empty string")
        return value.strip()

    @field_validator("proficiency")
    @classmethod
    def _proficiency_display(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: list[str]) -> list[str]:
        return _normalize_evidence(value)


class CandidateProfile(CandidateSchemaBase):
    """Approved or proposed Candidate Profile facts (not job preferences)."""

    summary: str = Field(..., min_length=1, max_length=MAX_SUMMARY_LEN)
    current_title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    total_experience_years: float | None = None
    skills: list[CandidateSkill] = Field(default_factory=list, max_length=MAX_SKILLS)
    experiences: list[ExperienceItem] = Field(
        default_factory=list,
        max_length=MAX_EXPERIENCES,
    )
    education: list[EducationItem] = Field(
        default_factory=list,
        max_length=MAX_EDUCATION_ITEMS,
    )
    languages: list[LanguageItem] = Field(
        default_factory=list,
        max_length=MAX_LANGUAGES,
    )
    extraction_confidence: float

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("summary must be a non-empty string")
        return value.strip()

    @field_validator("current_title")
    @classmethod
    def _current_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("total_experience_years")
    @classmethod
    def _total_years(cls, value: float | None) -> float | None:
        return _validate_years(value, field_name="total_experience_years")

    @field_validator("extraction_confidence")
    @classmethod
    def _extraction_confidence(cls, value: float) -> float:
        return _validate_confidence(value)

    @model_validator(mode="after")
    def _precise_total_years_need_timeline(self) -> CandidateProfile:
        if self.total_experience_years is None:
            return self
        # Timeline evidence: at least one experience with a date_range that
        # itself has timeline cues, or evidence snippets with date/duration
        # content. Non-timeline evidence alone does not authorize precise years.
        has_timeline = any(
            (
                item.date_range is not None
                and _text_has_timeline_evidence(item.date_range)
            )
            or _evidence_list_has_timeline(item.evidence)
            for item in self.experiences
        )
        if not has_timeline:
            raise ValueError(
                "precise total_experience_years require timeline evidence "
                "on experiences; use null for unknown"
            )
        return self


__all__ = [
    "MAX_ALIASES",
    "MAX_CANONICAL_KEY_LEN",
    "MAX_CATEGORY_LEN",
    "MAX_CREDENTIAL_LEN",
    "MAX_DATE_RANGE_LEN",
    "MAX_DISPLAY_NAME_LEN",
    "MAX_EDUCATION_ITEMS",
    "MAX_EVIDENCE_ITEMS",
    "MAX_EVIDENCE_SNIPPET_LEN",
    "MAX_EXPERIENCES",
    "MAX_FIELD_OF_STUDY_LEN",
    "MAX_ITEM_SUMMARY_LEN",
    "MAX_LANGUAGE_NAME_LEN",
    "MAX_LANGUAGE_PROFICIENCY_LEN",
    "MAX_LANGUAGES",
    "MAX_ORG_LEN",
    "MAX_SKILLS",
    "MAX_SUMMARY_LEN",
    "MAX_TITLE_LEN",
    "MAX_YEARS",
    "CandidateProfile",
    "CandidateSchemaBase",
    "CandidateSkill",
    "EducationItem",
    "ExperienceItem",
    "LanguageItem",
    "SkillProficiency",
    "SkillRef",
    "SkillSource",
    "SkillStatus",
]
