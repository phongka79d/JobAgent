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

from app.db.models.attachments import ATTACHMENT_MIME_TYPE_PDF
from app.schemas.attachments import AttachmentPublic
from app.schemas.chat import ConversationSummary
from app.schemas.common import AwareUtcDatetime, StrictModelConfig, UuidStr
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

    full_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
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


# ---------------------------------------------------------------------------
# Public profile read contracts (GET /api/profile) — no PDF bytes / paths
# ---------------------------------------------------------------------------


class ProfileReadResponse(BaseModel):
    """``GET /api/profile`` body: active profile state or explicit empty.

    When ``present`` is false, profile/preferences/active_attachment are null
    and the client must not invent an approved CV. ``draft_present`` and
    ``pending_attachment`` may still describe an unapproved draft/staged CV so
    the sidebar can show pending state. When ``present`` is true, the three
    active nested objects are validated and populated. Never carries PDF bytes
    or ``storage_path``.
    """

    model_config = StrictModelConfig

    present: bool
    profile: CandidateProfile | None = None
    preferences: JobPreferences | None = None
    active_attachment: AttachmentPublic | None = None
    draft_present: bool = False
    pending_attachment: AttachmentPublic | None = None


class ProfileSkillTag(BaseModel):
    model_config = StrictModelConfig

    key: str
    label: str


ProfileAttachmentState = Literal["active", "archived", "deleting"]


class ProfileAttachmentMetadata(BaseModel):
    """Safe profile attachment metadata, including retryable deletion state."""

    model_config = StrictModelConfig

    id: UuidStr
    original_name: str = Field(min_length=1)
    mime_type: Literal["application/pdf"] = ATTACHMENT_MIME_TYPE_PDF  # type: ignore[assignment]
    size_bytes: int = Field(gt=0)
    page_count: int | None = Field(default=None, gt=0)
    state: ProfileAttachmentState
    failure_code: str | None = None


class ProfileListItem(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    display_name: str
    cv_filename: str
    attachment_state: ProfileAttachmentState
    location: str | None
    skill_tags: list[ProfileSkillTag]
    skill_count: int
    extraction_version: str
    source_hash: str
    state: Literal["ready", "deleting"]
    is_active: bool
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    last_opened_at: AwareUtcDatetime


class ProfileListResponse(BaseModel):
    model_config = StrictModelConfig

    items: list[ProfileListItem]
    active_profile_id: UuidStr | None


class ProfileDetail(ProfileListItem):
    model_config = StrictModelConfig

    profile: CandidateProfile
    preferences: JobPreferences
    attachment: ProfileAttachmentMetadata
    selected_conversation_id: UuidStr | None


class ProfileUpdateRequest(BaseModel):
    model_config = StrictModelConfig

    # ponytail: FastAPI validates Pydantic constraints before route-level trim.
    # The sole PATCH route therefore owns the normalized limit and stable error;
    # move it back here only when transport validation preserves both semantics.
    display_name: str = Field(min_length=1)


class SafeWarning(BaseModel):
    model_config = StrictModelConfig

    code: str
    summary: str
    guidance: str


class SelectionResponse(BaseModel):
    model_config = StrictModelConfig

    profile: ProfileDetail
    conversation: ConversationSummary | None
    warning: SafeWarning | None


def empty_profile_read_response(
    *,
    draft_present: bool = False,
    pending_attachment: AttachmentPublic | None = None,
) -> ProfileReadResponse:
    """Explicit empty/approved-absent public profile state."""
    return ProfileReadResponse(
        present=False,
        profile=None,
        preferences=None,
        active_attachment=None,
        draft_present=draft_present,
        pending_attachment=pending_attachment,
    )
