"""Typed API and domain response schemas."""

from __future__ import annotations

from app.schemas.candidate import (
    CandidateProfile,
    CandidateSkill,
    EducationItem,
    ExperienceItem,
    LanguageItem,
    SkillProficiency,
    SkillRef,
    SkillSource,
    SkillStatus,
)
from app.schemas.chat import (
    HISTORY_LIMIT_MAX,
    HistoryMessage,
    HistoryResponse,
    ResumeRequest,
    TurnRequest,
)
from app.schemas.health import (
    ComponentHealth,
    ComponentState,
    HealthResponse,
    OverallStatus,
    overall_status,
)
from app.schemas.preferences import JobPreferences, TargetSeniority, WorkMode
from app.schemas.profile_draft import (
    ProfileApprovalSummary,
    ProfileDraftDocument,
    build_approval_summary,
)
from app.schemas.sse import (
    SSEEvent,
    SSEEventOrderValidator,
    SSEEventType,
    SSEOrderError,
    SSESchemaError,
    ToolDisplayStatus,
    parse_sse_event,
    serialize_sse_event,
    serialize_sse_event_json,
    validate_sse_event_order,
)

__all__ = [
    "HISTORY_LIMIT_MAX",
    "CandidateProfile",
    "CandidateSkill",
    "ComponentHealth",
    "ComponentState",
    "EducationItem",
    "ExperienceItem",
    "HealthResponse",
    "HistoryMessage",
    "HistoryResponse",
    "JobPreferences",
    "LanguageItem",
    "OverallStatus",
    "ProfileApprovalSummary",
    "ProfileDraftDocument",
    "ResumeRequest",
    "SSEEvent",
    "SSEEventOrderValidator",
    "SSEEventType",
    "SSEOrderError",
    "SSESchemaError",
    "SkillProficiency",
    "SkillRef",
    "SkillSource",
    "SkillStatus",
    "TargetSeniority",
    "ToolDisplayStatus",
    "TurnRequest",
    "WorkMode",
    "build_approval_summary",
    "overall_status",
    "parse_sse_event",
    "serialize_sse_event",
    "serialize_sse_event_json",
    "validate_sse_event_order",
]
