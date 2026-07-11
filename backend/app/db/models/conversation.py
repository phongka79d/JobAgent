"""Conversation, messages, agent runs, and tool execution observability."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import SINGLETON_PK, Base, TimestampMixin, new_uuid
from app.db.enums import AgentRunState, ToolExecutionStatus


class Conversation(Base, TimestampMixin):
    """Singleton application conversation."""

    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint(f"id = {SINGLETON_PK}", name="singleton_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_PK)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base, TimestampMixin):
    """UI history and application-level conversation record."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="message_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured card/payload data; validated by application layer later.
    structured_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    # One LangGraph application run per user-turn message (resume uses same row).
    agent_run: Mapped[AgentRun | None] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        uselist=False,
    )


class AgentRun(Base, TimestampMixin):
    """One LangGraph run per user turn (application row, not checkpoint tables).

    ``id`` is the stable LangGraph ``thread_id`` for the turn (resume reuses it).
    ``turn_idempotency_key`` makes duplicate turn POSTs resolve to the same run.
    ``resume_idempotency_key`` stores the last applied resume key so replay does
    not re-apply a resume action.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN "
            "('pending', 'running', 'interrupted', 'completed', 'failed')",
            name="agent_run_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AgentRunState.PENDING.value,
    )
    pending_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Durable client turn key; unique when present (nullable for pre-Plan-3 rows).
    turn_idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )
    # Last successfully applied resume key for this run (replay is a no-op write).
    resume_idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    message: Mapped[ChatMessage] = relationship(back_populates="agent_run")
    tool_executions: Mapped[list[ToolExecution]] = relationship(
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )

    @property
    def thread_id(self) -> str:
        """Stable LangGraph thread identity: string form of the durable run id."""
        return str(self.id)


class ToolExecution(Base, TimestampMixin):
    """Tool observability and evaluation (sanitized arguments only)."""

    __tablename__ = "tool_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'succeeded', 'failed')",
            name="tool_execution_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)
    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Sanitized summary only — never raw secrets or full untrusted documents.
    arguments_summary: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ToolExecutionStatus.STARTED.value,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    agent_run: Mapped[AgentRun] = relationship(back_populates="tool_executions")
