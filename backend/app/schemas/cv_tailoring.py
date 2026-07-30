"""Strict durable, provider, and public contracts for CV tailoring."""

from __future__ import annotations

from typing import Any, Literal

from app.schemas.agent_activity import AgentActivityPayload
from app.schemas.common import AwareUtcDatetime, StrictModelConfig, UuidStr
from app.schemas.contact import (
    normalize_email,
    normalize_github_profile_url,
    normalize_phone,
)
from app.schemas.cv_document import CVSectionKind
from pydantic import BaseModel, Field, field_validator, model_validator

TAILORING_TEMPLATE_VERSION = "latex-cv-v1"
TAILORING_SESSION_STATE_GENERATING = "generating"
TAILORING_SESSION_STATE_READY = "ready"
TAILORING_SESSION_STATE_FAILED = "failed"
TAILORING_SESSION_STATE_DELETING = "deleting"
TAILORING_SESSION_STATES = frozenset(
    {
        TAILORING_SESSION_STATE_GENERATING,
        TAILORING_SESSION_STATE_READY,
        TAILORING_SESSION_STATE_FAILED,
        TAILORING_SESSION_STATE_DELETING,
    }
)
TAILORING_CREATED_BY_AI = "ai"
TAILORING_CREATED_BY_USER = "user"
TAILORING_CREATED_BY_VALUES = frozenset(
    {TAILORING_CREATED_BY_AI, TAILORING_CREATED_BY_USER}
)
TAILORING_CURRENT = "current"
TAILORING_STALE = "stale"
CV_TAILORING_SESSION_HEADER = "X-CV-Tailoring-Session-Id"


class SourceBoundText(BaseModel):
    model_config = StrictModelConfig

    text: str = Field(max_length=4_000)
    source_fact_ids: list[str] = Field(max_length=64)

    @field_validator("source_fact_ids")
    @classmethod
    def fact_ids_are_unique(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("source_fact_ids entries must be non-empty")
        if len(value) != len(set(value)):
            raise ValueError("source_fact_ids must be unique")
        return value


class TailoredAttribute(BaseModel):
    model_config = StrictModelConfig

    name: str = Field(min_length=1, max_length=120)
    values: list[SourceBoundText] = Field(min_length=1, max_length=30)


class TailoredItem(BaseModel):
    model_config = StrictModelConfig

    id: str = Field(min_length=1, max_length=200)
    source_entry_id: str | None = Field(default=None, max_length=200)
    title: SourceBoundText | None = None
    subtitle: SourceBoundText | None = None
    date_text: SourceBoundText | None = None
    location: SourceBoundText | None = None
    body: SourceBoundText
    bullets: list[SourceBoundText] = Field(max_length=30)
    attributes: list[TailoredAttribute] = Field(max_length=30)


class TailoredSection(BaseModel):
    model_config = StrictModelConfig

    id: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(ge=0)
    heading: str = Field(min_length=1, max_length=200)
    kind: CVSectionKind
    items: list[TailoredItem] = Field(max_length=30)


class TailoredHeaderSnapshot(BaseModel):
    model_config = StrictModelConfig

    full_name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=254)
    github_url: str | None = Field(default=None, max_length=500)

    @field_validator("full_name")
    @classmethod
    def full_name_is_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("full_name must be non-empty")
        return cleaned

    @field_validator("phone", "email", "github_url")
    @classmethod
    def normalize_contact(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        if info.field_name == "phone":
            return normalize_phone(value)
        if info.field_name == "email":
            return normalize_email(value)
        return normalize_github_profile_url(value)


class TailoredCVContent(BaseModel):
    model_config = StrictModelConfig

    header: TailoredHeaderSnapshot
    sections: list[TailoredSection] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def section_order_and_identity(self) -> TailoredCVContent:
        if [section.ordinal for section in self.sections] != list(
            range(len(self.sections))
        ):
            raise ValueError("sections must have contiguous ordinals")
        ids = [section.id for section in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("section ids must be unique")
        return self


class TailoringSourceRevision(BaseModel):
    model_config = StrictModelConfig

    profile_updated_at: AwareUtcDatetime
    source_hash: str = Field(min_length=1, max_length=128)
    job_updated_at: AwareUtcDatetime | None
    template_version: Literal["latex-cv-v1"]


class TailoredFactEvidence(BaseModel):
    model_config = StrictModelConfig

    fact_id: str = Field(min_length=1, max_length=35)
    section_id: str = Field(min_length=1, max_length=200)
    source_entry_id: str = Field(min_length=1, max_length=200)
    field_path: str = Field(min_length=1, max_length=200)
    source_text: str = Field(max_length=4_000)


class TailoringProvenance(BaseModel):
    model_config = StrictModelConfig

    targeted_section_ids: list[str] = Field(max_length=20)
    facts: list[TailoredFactEvidence] = Field(max_length=20_000)


class TailoredItemPatch(BaseModel):
    model_config = StrictModelConfig

    source_entry_id: str | None
    title: SourceBoundText | None
    subtitle: SourceBoundText | None
    date_text: SourceBoundText | None
    location: SourceBoundText | None
    body: SourceBoundText
    bullets: list[SourceBoundText]
    attributes: list[TailoredAttribute]


class TailoredSectionPatch(BaseModel):
    model_config = StrictModelConfig

    section_id: str
    items: list[TailoredItemPatch]


class TailoredPatchSet(BaseModel):
    model_config = StrictModelConfig

    sections: list[TailoredSectionPatch]


class CreateTailoringSessionRequest(BaseModel):
    model_config = StrictModelConfig

    job_id: UuidStr | None = None
    instruction: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def has_source(self) -> CreateTailoringSessionRequest:
        self.instruction = self.instruction.strip()
        if self.job_id is None and not self.instruction:
            raise ValueError("job_id or instruction is required")
        return self


class CreateTailoringAiVersionRequest(BaseModel):
    model_config = StrictModelConfig

    parent_version_id: UuidStr | None = None
    instruction: str = Field(default="", max_length=4_000)
    target_section_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def retry_or_scoped_edit(self) -> CreateTailoringAiVersionRequest:
        if self.parent_version_id is None and self.target_section_ids:
            raise ValueError("initial retry selects sections from the outline")
        if self.parent_version_id is not None and not self.target_section_ids:
            raise ValueError("later AI version requires selected sections")
        if self.parent_version_id is not None and not self.instruction.strip():
            raise ValueError("later AI version requires an instruction")
        self.instruction = self.instruction.strip()
        return self


class CreateTailoringManualVersionRequest(BaseModel):
    model_config = StrictModelConfig

    parent_version_id: UuidStr
    content: TailoredCVContent


class TailoringJobLabel(BaseModel):
    model_config = StrictModelConfig

    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=300)
    display_label: str | None = Field(default=None, max_length=140)


class TailoringVersionSummary(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    version_number: int = Field(ge=1)
    parent_version_id: UuidStr | None
    created_by: Literal["ai", "user"]
    page_count: int = Field(ge=1)
    page_warning: str | None
    created_at: AwareUtcDatetime


class TailoringSessionSummary(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    profile_id: UuidStr
    job_label: TailoringJobLabel | None
    instruction: str
    template_version: Literal["latex-cv-v1"]
    state: Literal["generating", "ready", "failed", "deleting"]
    currentness: Literal["current", "stale"]
    latest_version_number: int = Field(ge=0)
    error_code: str | None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime


class TailoringSessionListResponse(BaseModel):
    model_config = StrictModelConfig

    items: list[TailoringSessionSummary]


class TailoringUserIssue(BaseModel):
    model_config = StrictModelConfig

    section_id: str = Field(min_length=1, max_length=120)
    section_heading: str = Field(min_length=1, max_length=200)
    item_index: int | None = Field(default=None, ge=0, le=30)
    field: Literal[
        "title",
        "subtitle",
        "date",
        "location",
        "body",
        "bullet",
        "attribute",
        "section",
    ]
    reason: Literal[
        "not_in_source",
        "belongs_to_another_section",
        "structure_changed",
        "required_source_missing",
        "unsupported_value",
    ]


class TailoringRunSummary(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    state: Literal["running", "interrupted", "completed", "failed"]
    error_code: str | None
    activities: list[AgentActivityPayload]
    issues: list[TailoringUserIssue] = Field(default_factory=list, max_length=10)


class TailoringSessionDetailResponse(BaseModel):
    model_config = StrictModelConfig

    session: TailoringSessionSummary
    versions: list[TailoringVersionSummary]
    selected_version: TailoringVersionSummary | None
    content: TailoredCVContent | None
    evidence: list[TailoredFactEvidence]
    latest_run: TailoringRunSummary | None
    source_available: bool
    pdf_available: bool


TailoringMutationOutcome = Literal["version_created", "no_change"]


class TailoringVersionMutationResponse(BaseModel):
    model_config = StrictModelConfig

    outcome: TailoringMutationOutcome
    session_id: UuidStr
    version_id: UuidStr
    version_number: int = Field(ge=1)
    currentness: Literal["current"] = "current"

    @model_validator(mode="after")
    def identity_is_present(self) -> TailoringVersionMutationResponse:
        if not self.version_id or self.version_number < 1:
            raise ValueError("tailoring mutation requires version identity")
        return self


def canonical_tailored_content(content: TailoredCVContent) -> dict[str, Any]:
    return content.model_dump(mode="json", exclude_none=False)


def tailored_content_equal(left: TailoredCVContent, right: TailoredCVContent) -> bool:
    return canonical_tailored_content(left) == canonical_tailored_content(right)


class TailoringDeleteResponse(BaseModel):
    model_config = StrictModelConfig

    deleted_session_id: UuidStr


def parse_tailored_content(payload: Any) -> TailoredCVContent:
    return TailoredCVContent.model_validate(payload)


def parse_tailoring_provenance(payload: Any) -> TailoringProvenance:
    return TailoringProvenance.model_validate(payload)
