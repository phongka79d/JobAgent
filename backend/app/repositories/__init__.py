"""Repository layer for SQLite application metadata (caller-owned transactions)."""

from __future__ import annotations

from app.repositories.agent_runs import (
    AgentRunDuplicateError,
    AgentRunNotFoundError,
    AgentRunRepository,
    AgentRunRepositoryError,
    AgentRunStateError,
    AgentRunValidationError,
    langgraph_thread_id,
    sanitize_run_error,
)
from app.repositories.conversations import (
    ConversationDuplicateError,
    ConversationMessageError,
    ConversationNotFoundError,
    ConversationPayloadError,
    ConversationRepository,
    ConversationRepositoryError,
    validate_structured_payload,
)
from app.repositories.preferences import (
    PreferencesNotFoundError,
    PreferencesRepository,
    PreferencesRepositoryError,
    PreferencesValidationError,
)
from app.repositories.profile_drafts import (
    ProfileDraftNotFoundError,
    ProfileDraftRecord,
    ProfileDraftRepository,
    ProfileDraftRepositoryError,
    ProfileDraftStateError,
    ProfileDraftValidationError,
)
from app.repositories.profiles import (
    ApprovedProfileRecord,
    ProfileNotFoundError,
    ProfileRepository,
    ProfileRepositoryError,
    ProfileValidationError,
)
from app.repositories.tool_executions import (
    ToolExecutionNotFoundError,
    ToolExecutionRepository,
    ToolExecutionRepositoryError,
    ToolExecutionStateError,
    ToolExecutionValidationError,
    sanitize_arguments_summary,
    sanitize_error_code,
)

__all__ = [
    "AgentRunDuplicateError",
    "AgentRunNotFoundError",
    "AgentRunRepository",
    "AgentRunRepositoryError",
    "AgentRunStateError",
    "AgentRunValidationError",
    "ApprovedProfileRecord",
    "ConversationDuplicateError",
    "ConversationMessageError",
    "ConversationNotFoundError",
    "ConversationPayloadError",
    "ConversationRepository",
    "ConversationRepositoryError",
    "PreferencesNotFoundError",
    "PreferencesRepository",
    "PreferencesRepositoryError",
    "PreferencesValidationError",
    "ProfileDraftNotFoundError",
    "ProfileDraftRecord",
    "ProfileDraftRepository",
    "ProfileDraftRepositoryError",
    "ProfileDraftStateError",
    "ProfileDraftValidationError",
    "ProfileNotFoundError",
    "ProfileRepository",
    "ProfileRepositoryError",
    "ProfileValidationError",
    "ToolExecutionNotFoundError",
    "ToolExecutionRepository",
    "ToolExecutionRepositoryError",
    "ToolExecutionStateError",
    "ToolExecutionValidationError",
    "langgraph_thread_id",
    "sanitize_arguments_summary",
    "sanitize_error_code",
    "sanitize_run_error",
    "validate_structured_payload",
]
