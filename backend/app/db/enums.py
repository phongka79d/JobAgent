"""Independent enumerated domains for SQLite application columns.

Job status dimensions must not be conflated into a single status field.
Values match Master_plan section 6.3 and Plan_2 section 7.2 exactly.
"""

from __future__ import annotations

from enum import StrEnum


class AttachmentState(StrEnum):
    """Lifecycle of staged/active CV file metadata (bytes live on disk)."""

    STAGED = "staged"
    ACTIVE = "active"


class ProfileDraftState(StrEnum):
    """Temporary profile/preference draft awaiting explicit approval."""

    PENDING = "pending"
    DISCARDED = "discarded"


class ProcessingStatus(StrEnum):
    """JD ingestion processing lifecycle (independent of quality/sync/record)."""

    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class JdQuality(StrEnum):
    """JD scoring readiness classification (independent of processing)."""

    FULL = "full"
    PARTIAL = "partial"
    UNSCORABLE = "unscorable"


class GraphSyncStatus(StrEnum):
    """SQLite-to-Neo4j synchronization state for a job record."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class RecordStatus(StrEnum):
    """Whether a job row is the active canonical record or an ignored duplicate."""

    ACTIVE = "active"
    IGNORED_DUPLICATE = "ignored_duplicate"


class JobSourceType(StrEnum):
    """How raw JD content entered the system."""

    URL = "url"
    TEXT = "text"


class MessageRole(StrEnum):
    """Chat message author role for application conversation history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class AgentRunState(StrEnum):
    """One LangGraph run per user turn (application-owned, not checkpoint tables)."""

    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolExecutionStatus(StrEnum):
    """Tool observability outcome for a single tool call within a run."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OutboxStatus(StrEnum):
    """Durable graph sync outbox row state."""

    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
