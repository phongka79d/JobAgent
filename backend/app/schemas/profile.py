"""Candidate Profile, preferences, and draft Pydantic contracts (Master §7.2–7.3).

Validated-model boundary for JSON columns
-----------------------------------------
ORM rows store opaque JSON. Before every write of:

* ``candidate_profile.profile_json`` — validate a full ``CandidateProfile``
* ``profile_drafts.draft_json`` — validate a full ``ProfileDraftPayload``
* ``job_preferences.preferences_json`` — validate a full ``JobPreferences``

services must call ``model_validate`` / the ``parse_*`` helpers below and only
persist ``model_dump(mode="json")`` of the accepted model. Raw dict assembly
must not skip this boundary.

Profile facts and job preferences remain separate documents. A CV address never
becomes a preferred location automatically. Evidence is a list of short source
snippets; precise years/proficiency must not be invented without evidence.
Excluded skills stay in the profile with ``excluded=true``; corrections use
``source='user_correction'``.

No ORM, provider, filesystem, graph, route, or Agent behavior lives here.
"""

from __future__ import annotations

from typing import Any, Literal

from app.schemas.common import StrictModelConfig
from app.schemas.skills import SkillRef
from pydantic import BaseModel, Field

# Exact enum vocabularies from Master §7.2–7.3 (string Literals, not ORM types).
SkillProficiency = Literal["beginner", "intermediate", "advanced", "unknown"]
SkillSource = Literal["cv", "user_correction"]
WorkMode = Literal["remote", "hybrid", "onsite"]
TargetSeniority = Literal["intern", "junior", "mid", "senior", "lead", "unknown"]

ConfidenceFloat = float  # documented alias; fields use Field(ge=0, le=1)


class CandidateSkill(BaseModel):
    """One skill assertion on a candidate profile (Master §7.2)."""

    model_config = StrictModelConfig

    skill: SkillRef
    confidence: float = Field(ge=0.0, le=1.0)
    proficiency: SkillProficiency
    years: float | None
    source: SkillSource
    excluded: bool
    evidence: list[str]


class ExperienceItem(BaseModel):
    """One work experience entry.

    ``end_date_text`` is free-form text or null; the conventional value
    ``\"present\"`` means a current role (Master §7.2: ``str | present | None``).
    """

    model_config = StrictModelConfig

    title: str
    company: str | None
    start_date_text: str | None
    end_date_text: str | None
    summary: str


class EducationItem(BaseModel):
    """One education entry (Master §7.2)."""

    model_config = StrictModelConfig

    institution: str
    degree: str | None
    field: str | None
    graduation_year: int | None


class LanguageItem(BaseModel):
    """One language entry (Master §7.2)."""

    model_config = StrictModelConfig

    name: str
    proficiency: str | None


class CandidateProfile(BaseModel):
    """Approved or draft candidate facts (``profile_json`` payload).

    Distinct from the SQLAlchemy ``app.db.models.profiles.CandidateProfile`` row
    type, which owns the singleton table and opaque JSON column.
    """

    model_config = StrictModelConfig

    summary: str
    current_title: str | None
    total_experience_years: float | None
    skills: list[CandidateSkill]
    experiences: list[ExperienceItem]
    education: list[EducationItem]
    languages: list[LanguageItem]
    extraction_confidence: float = Field(ge=0.0, le=1.0)


class JobPreferences(BaseModel):
    """Job search preferences (``preferences_json`` payload).

    Distinct from the SQLAlchemy ``app.db.models.profiles.JobPreferences`` row
    type. Seeded empty document uses four empty lists with these exact keys.
    """

    model_config = StrictModelConfig

    target_roles: list[str]
    preferred_locations: list[str]
    acceptable_work_modes: list[WorkMode]
    target_seniority: list[TargetSeniority]


class ProfileDraftPayload(BaseModel):
    """Complete draft document stored in ``profile_drafts.draft_json``.

    Facts (``candidate_profile``) and preferences (``job_preferences``) stay
    separate nested objects and must not be merged on serialize/deserialize.
    """

    model_config = StrictModelConfig

    candidate_profile: CandidateProfile
    job_preferences: JobPreferences


def parse_candidate_profile(payload: Any) -> CandidateProfile:
    """Parse and validate a full ``CandidateProfile`` before ``profile_json`` write."""
    return CandidateProfile.model_validate(payload)


def parse_job_preferences(payload: Any) -> JobPreferences:
    """Parse and validate full ``JobPreferences`` before ``preferences_json`` write."""
    return JobPreferences.model_validate(payload)


def parse_profile_draft_payload(payload: Any) -> ProfileDraftPayload:
    """Parse and validate a full ``ProfileDraftPayload`` before ``draft_json`` write."""
    return ProfileDraftPayload.model_validate(payload)
