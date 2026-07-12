"""Authoritative Job extraction and skill-relationship contracts (Plan 5 §7.2).

Implements exact Master Plan §7.4 named fields for ``JobPostExtraction`` and a
minimal ``JobSkill`` that wraps the shared ``SkillRef`` with relationship-level
confidence and evidence only (Master §8.2 ``REQUIRES`` / ``PREFERS`` props).

Deliberately omits:

- scoring weights, match strengths, or hybrid-score fields
- trusted graph relationships (``RELATED_TO``, verified-edge weight, etc.)
- raw document bodies, hashes, or storage paths
- provider-control or repair-loop fields

Opaque provider extras are rejected via ``extra="forbid"`` on every model.
Salary is display-only and does not participate in scoring readiness.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.candidate import (
    MAX_CANONICAL_KEY_LEN,
    MAX_CATEGORY_LEN,
    MAX_DISPLAY_NAME_LEN,
    MAX_EVIDENCE_ITEMS,
    MAX_EVIDENCE_SNIPPET_LEN,
    MAX_ORG_LEN,
    MAX_SKILLS,
    MAX_SUMMARY_LEN,
    MAX_TITLE_LEN,
    MAX_YEARS,
    SkillRef,
    _normalize_evidence,
    _normalize_string_list,
    _validate_confidence,
    _validate_years,
)

# ---------------------------------------------------------------------------
# Bounds (display + evidence only; not scoring ceilings)
# ---------------------------------------------------------------------------

MAX_RESPONSIBILITIES: Final[int] = 50
MAX_RESPONSIBILITY_LEN: Final[int] = 1_000
MAX_REQUIREMENT_ITEMS: Final[int] = 30
MAX_REQUIREMENT_ITEM_LEN: Final[int] = 512
MAX_LOCATION_LEN: Final[int] = 256
MAX_SALARY_TEXT_LEN: Final[int] = 256
MAX_JOB_FAMILY_LEN: Final[int] = 256


class JobSeniority(StrEnum):
    """JD seniority label; ``unknown`` is an explicit allowed value."""

    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    UNKNOWN = "unknown"


class JobWorkMode(StrEnum):
    """JD work arrangement; ``unknown`` is an explicit allowed value."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    """JD employment type; ``unknown`` is an explicit allowed value."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


class JdQuality(StrEnum):
    """Deterministic scoring-readiness classification (Master §7.5)."""

    FULL = "full"
    PARTIAL = "partial"
    UNSCORABLE = "unscorable"


class JobSchemaBase(BaseModel):
    """Shared strict config for Job domain documents."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JobSkill(JobSchemaBase):
    """One required/preferred skill on a Job with relationship confidence.

    Wraps shared ``SkillRef`` identity; adds only relationship-level
    ``confidence`` and short source-grounded ``evidence`` (no match weight).
    """

    skill: SkillRef
    confidence: float
    evidence: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _validate_confidence(value)

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: list[str]) -> list[str]:
        return _normalize_evidence(value)


class JobPostExtraction(JobSchemaBase):
    """Strict structured Job extraction (Master §7.4 field inventory exactly).

    ``jd_quality`` is part of the extraction document but must be overwritten by
    the deterministic classifier after grounding; reasons live outside this
    object. ``salary_text`` is display-only.
    """

    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    company: str | None = Field(default=None, max_length=MAX_ORG_LEN)
    summary: str = Field(default="", max_length=MAX_SUMMARY_LEN)
    responsibilities: list[str] = Field(
        default_factory=list,
        max_length=MAX_RESPONSIBILITIES,
    )
    required_skills: list[JobSkill] = Field(
        default_factory=list,
        max_length=MAX_SKILLS,
    )
    preferred_skills: list[JobSkill] = Field(
        default_factory=list,
        max_length=MAX_SKILLS,
    )
    seniority: JobSeniority = JobSeniority.UNKNOWN
    min_experience_years: float | None = None
    max_experience_years: float | None = None
    location: str | None = Field(default=None, max_length=MAX_LOCATION_LEN)
    work_mode: JobWorkMode = JobWorkMode.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    education_requirements: list[str] = Field(
        default_factory=list,
        max_length=MAX_REQUIREMENT_ITEMS,
    )
    language_requirements: list[str] = Field(
        default_factory=list,
        max_length=MAX_REQUIREMENT_ITEMS,
    )
    salary_text: str | None = Field(default=None, max_length=MAX_SALARY_TEXT_LEN)
    job_family: str | None = Field(default=None, max_length=MAX_JOB_FAMILY_LEN)
    extraction_confidence: float
    jd_quality: JdQuality

    @field_validator("title", "company", "location", "salary_text", "job_family")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("summary must be a string")
        return value.strip()

    @field_validator("responsibilities")
    @classmethod
    def _responsibilities(cls, value: list[str]) -> list[str]:
        return _normalize_string_list(
            value,
            max_items=MAX_RESPONSIBILITIES,
            max_item_len=MAX_RESPONSIBILITY_LEN,
            field_name="responsibilities",
        )

    @field_validator("education_requirements", "language_requirements")
    @classmethod
    def _requirement_lists(cls, value: list[str]) -> list[str]:
        return _normalize_string_list(
            value,
            max_items=MAX_REQUIREMENT_ITEMS,
            max_item_len=MAX_REQUIREMENT_ITEM_LEN,
            field_name="requirements",
        )

    @field_validator("min_experience_years", "max_experience_years")
    @classmethod
    def _experience_years(cls, value: float | None) -> float | None:
        return _validate_years(value, field_name="experience_years")

    @field_validator("extraction_confidence")
    @classmethod
    def _extraction_confidence(cls, value: float) -> float:
        return _validate_confidence(value)

    @model_validator(mode="after")
    def _experience_range_order(self) -> JobPostExtraction:
        if (
            self.min_experience_years is not None
            and self.max_experience_years is not None
            and self.min_experience_years > self.max_experience_years
        ):
            raise ValueError(
                "min_experience_years must not exceed max_experience_years"
            )
        return self


__all__ = [
    "MAX_CANONICAL_KEY_LEN",
    "MAX_CATEGORY_LEN",
    "MAX_DISPLAY_NAME_LEN",
    "MAX_EVIDENCE_ITEMS",
    "MAX_EVIDENCE_SNIPPET_LEN",
    "MAX_JOB_FAMILY_LEN",
    "MAX_LOCATION_LEN",
    "MAX_ORG_LEN",
    "MAX_REQUIREMENT_ITEM_LEN",
    "MAX_REQUIREMENT_ITEMS",
    "MAX_RESPONSIBILITIES",
    "MAX_RESPONSIBILITY_LEN",
    "MAX_SALARY_TEXT_LEN",
    "MAX_SKILLS",
    "MAX_SUMMARY_LEN",
    "MAX_TITLE_LEN",
    "MAX_YEARS",
    "EmploymentType",
    "JdQuality",
    "JobPostExtraction",
    "JobSchemaBase",
    "JobSeniority",
    "JobSkill",
    "JobWorkMode",
    "SkillRef",
]
