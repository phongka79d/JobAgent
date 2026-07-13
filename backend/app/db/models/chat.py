"""SQLAlchemy contracts for conversation, messages, runs, and tool executions.

Static column, CHECK, unique, index, and CASCADE FK invariants only. Chat
endpoints, SSE, LangGraph checkpoints, tool execution services, approval
flows, and provider ToolMessage persistence belong to later phases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    column,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base

# Fixed singleton conversation primary key (Master §6.1 / §6.2).
CONVERSATION_ID = "main"

# Single production owners for message/run/tool immutable status values.
CHAT_MESSAGE_ROLE_USER = "user"
CHAT_MESSAGE_ROLE_ASSISTANT = "assistant"
CHAT_MESSAGE_ROLE_SYSTEM = "system"
CHAT_MESSAGE_ROLES: frozenset[str] = frozenset(
    {CHAT_MESSAGE_ROLE_USER, CHAT_MESSAGE_ROLE_ASSISTANT, CHAT_MESSAGE_ROLE_SYSTEM}
)

AGENT_RUN_STATE_RUNNING = "running"
AGENT_RUN_STATE_INTERRUPTED = "interrupted"
AGENT_RUN_STATE_COMPLETED = "completed"
AGENT_RUN_STATE_FAILED = "failed"
AGENT_RUN_STATES: frozenset[str] = frozenset(
    {
        AGENT_RUN_STATE_RUNNING,
        AGENT_RUN_STATE_INTERRUPTED,
        AGENT_RUN_STATE_COMPLETED,
        AGENT_RUN_STATE_FAILED,
    }
)
AGENT_RUN_STATE_DEFAULT = AGENT_RUN_STATE_RUNNING

TOOL_EXECUTION_STATUS_PENDING = "pending"
TOOL_EXECUTION_STATUS_RUNNING = "running"
TOOL_EXECUTION_STATUS_COMPLETED = "completed"
TOOL_EXECUTION_STATUS_FAILED = "failed"
TOOL_EXECUTION_STATUSES: frozenset[str] = frozenset(
    {
        TOOL_EXECUTION_STATUS_PENDING,
        TOOL_EXECUTION_STATUS_RUNNING,
        TOOL_EXECUTION_STATUS_COMPLETED,
        TOOL_EXECUTION_STATUS_FAILED,
    }
)
TOOL_EXECUTION_STATUS_DEFAULT = TOOL_EXECUTION_STATUS_PENDING

_TERMINAL_RUN = column("state").in_(
    (AGENT_RUN_STATE_COMPLETED, AGENT_RUN_STATE_FAILED),
)
_TERMINAL_TOOL = column("status").in_(
    (TOOL_EXECUTION_STATUS_COMPLETED, TOOL_EXECUTION_STATUS_FAILED),
)


class Conversation(Base):
    """Exactly one conversation row after seed (singleton id ``main``)."""

    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint(column("id") == CONVERSATION_ID, name="singleton_id"),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=CONVERSATION_ID,
        server_default=CONVERSATION_ID,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ChatMessage(Base):
    """One user, assistant, or system message in the singleton conversation."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            column("role").in_(
                (
                    CHAT_MESSAGE_ROLE_USER,
                    CHAT_MESSAGE_ROLE_ASSISTANT,
                    CHAT_MESSAGE_ROLE_SYSTEM,
                )
            ),
            name="role",
        ),
        CheckConstraint(
            (column("content") != "") | column("structured_payload").is_not(None),
            name="content_payload_coupling",
        ),
        Index(
            "ix_chat_messages__conversation_created_at",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AgentRun(Base):
    """One Agent run bound uniquely to its initiating user message."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            column("state").in_(
                (
                    AGENT_RUN_STATE_RUNNING,
                    AGENT_RUN_STATE_INTERRUPTED,
                    AGENT_RUN_STATE_COMPLETED,
                    AGENT_RUN_STATE_FAILED,
                )
            ),
            name="state",
        ),
        CheckConstraint(
            (
                (column("state") == AGENT_RUN_STATE_INTERRUPTED)
                & column("pending_approval_json").is_not(None)
            )
            | (
                (column("state") != AGENT_RUN_STATE_INTERRUPTED)
                & column("pending_approval_json").is_(None)
            ),
            name="pending_approval_coupling",
        ),
        CheckConstraint(
            (_TERMINAL_RUN & column("completed_at").is_not(None))
            | (~_TERMINAL_RUN & column("completed_at").is_(None)),
            name="completed_at_coupling",
        ),
        Index("ix_agent_runs__state", "state"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    user_message_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=AGENT_RUN_STATE_DEFAULT,
        server_default=AGENT_RUN_STATE_DEFAULT,
    )
    pending_approval_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ToolExecution(Base):
    """Durable tool-call status and result for one Agent run."""

    __tablename__ = "tool_executions"
    __table_args__ = (
        CheckConstraint(
            column("status").in_(
                (
                    TOOL_EXECUTION_STATUS_PENDING,
                    TOOL_EXECUTION_STATUS_RUNNING,
                    TOOL_EXECUTION_STATUS_COMPLETED,
                    TOOL_EXECUTION_STATUS_FAILED,
                )
            ),
            name="status",
        ),
        CheckConstraint(
            column("duration_ms").is_(None) | (column("duration_ms") >= 0),
            name="duration_ms_non_negative",
        ),
        CheckConstraint(
            (
                _TERMINAL_TOOL
                & column("duration_ms").is_not(None)
                & column("result_json").is_not(None)
            )
            | (
                ~_TERMINAL_TOOL
                & column("duration_ms").is_(None)
                & column("result_json").is_(None)
            ),
            name="terminal_result_duration",
        ),
        CheckConstraint(
            (
                (column("status") == TOOL_EXECUTION_STATUS_FAILED)
                & column("error_code").is_not(None)
            )
            | (
                (column("status") != TOOL_EXECUTION_STATUS_FAILED)
                & column("error_code").is_(None)
            ),
            name="error_coupling",
        ),
        UniqueConstraint(
            "run_id",
            "tool_call_id",
            name="uq_tool_executions__run_tool_call",
        ),
        Index("ix_tool_executions__run_status", "run_id", "status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_call_id: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    arguments_summary_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TOOL_EXECUTION_STATUS_DEFAULT,
        server_default=TOOL_EXECUTION_STATUS_DEFAULT,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
