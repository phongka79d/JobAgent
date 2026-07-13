"""Initial application schema: nine tables, constraints, indexes, singleton seeds.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-13

Owns only application tables from Master Plan Section 6. Never creates, alters,
or drops LangGraph checkpoint tables. Seeds conversation(main) and
job_preferences(active) only; never seeds candidate_profile.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.seed import ensure_singleton_seeds_on_connection

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Dependency order: independent roots first, then FK children.
    op.create_table(
        "attachments",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "state",
            sa.Text(),
            server_default="staged",
            nullable=False,
        ),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_attachments"),
        sa.UniqueConstraint("file_hash", name="uq_attachments__file_hash"),
        sa.UniqueConstraint("storage_path", name="uq_attachments__storage_path"),
        sa.CheckConstraint(
            "mime_type = 'application/pdf'",
            name="mime_type",
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="size_bytes_positive",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="page_count_positive",
        ),
        sa.CheckConstraint(
            "state IN ('staged', 'active', 'failed')",
            name="state",
        ),
        sa.CheckConstraint(
            "state = 'failed' AND failure_code IS NOT NULL "
            "OR state != 'failed' AND failure_code IS NULL",
            name="failure_coupling",
        ),
        sa.CheckConstraint(
            "state != 'active' OR page_count IS NOT NULL",
            name="active_requires_page_count",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_attachments__single_active "
        "ON attachments (state) WHERE state = 'active'"
    )

    op.create_table(
        "conversation",
        sa.Column(
            "id",
            sa.Text(),
            server_default="main",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_conversation"),
        sa.CheckConstraint(
            "id = 'main'",
            name="singleton_id",
        ),
    )

    op.create_table(
        "job_posts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("raw_content_hash", sa.Text(), nullable=True),
        sa.Column("extraction_json", sa.JSON(), nullable=True),
        sa.Column(
            "processing_status",
            sa.Text(),
            server_default="received",
            nullable=False,
        ),
        sa.Column("jd_quality", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("embedding_json", sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_job_posts"),
        sa.UniqueConstraint(
            "raw_content_hash",
            name="uq_job_posts__raw_content_hash",
        ),
        sa.CheckConstraint(
            "source_type IN ('url', 'text')",
            name="source_type",
        ),
        sa.CheckConstraint(
            "source_type = 'url' AND source_url IS NOT NULL "
            "OR source_type = 'text' AND raw_content IS NOT NULL "
            "AND source_url IS NULL",
            name="url_text_coupling",
        ),
        sa.CheckConstraint(
            "raw_content IS NULL AND raw_content_hash IS NULL "
            "OR raw_content IS NOT NULL AND raw_content_hash IS NOT NULL",
            name="raw_content_hash_coupling",
        ),
        sa.CheckConstraint(
            "processing_status IN "
            "('received', 'processing', 'processed', 'failed')",
            name="processing_status",
        ),
        sa.CheckConstraint(
            "jd_quality IS NULL OR "
            "jd_quality IN ('full', 'partial', 'unscorable')",
            name="jd_quality",
        ),
        sa.CheckConstraint(
            "processing_status != 'processed' OR "
            "extraction_json IS NOT NULL AND jd_quality IS NOT NULL",
            name="processed_requires_extraction_quality",
        ),
        sa.CheckConstraint(
            "processing_status = 'failed' AND failure_code IS NOT NULL "
            "OR processing_status != 'failed' AND failure_code IS NULL",
            name="failure_coupling",
        ),
        sa.CheckConstraint(
            "embedding_json IS NULL AND embedding_model IS NULL "
            "AND embedding_dimensions IS NULL OR "
            "embedding_json IS NOT NULL AND embedding_model IS NOT NULL "
            "AND embedding_dimensions IS NOT NULL",
            name="embedding_all_or_none",
        ),
        sa.CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions > 0",
            name="embedding_dimensions_positive",
        ),
        sa.CheckConstraint(
            "processing_status = 'processed' AND "
            "jd_quality IN ('full', 'partial') AND "
            "embedding_json IS NOT NULL AND embedding_model IS NOT NULL "
            "AND embedding_dimensions IS NOT NULL OR "
            "NOT (processing_status = 'processed' AND "
            "jd_quality IN ('full', 'partial')) AND "
            "embedding_json IS NULL AND embedding_model IS NULL "
            "AND embedding_dimensions IS NULL",
            name="processed_scorable_embedding",
        ),
    )
    op.create_index(
        "ix_job_posts__processing_quality",
        "job_posts",
        ["processing_status", "jd_quality"],
        unique=False,
    )

    op.create_table(
        "job_preferences",
        sa.Column(
            "id",
            sa.Text(),
            server_default="active",
            nullable=False,
        ),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_job_preferences"),
        sa.CheckConstraint(
            "id = 'active'",
            name="singleton_id",
        ),
    )

    op.create_table(
        "candidate_profile",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("active_attachment_id", sa.Text(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["active_attachment_id"],
            ["attachments.id"],
            name="fk_candidate_profile__active_attachment_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_candidate_profile"),
        sa.UniqueConstraint(
            "active_attachment_id",
            name="uq_candidate_profile__active_attachment_id",
        ),
        sa.CheckConstraint(
            "id = 'active'",
            name="singleton_id",
        ),
    )

    op.create_table(
        "profile_drafts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_attachment_id", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name="fk_profile_drafts__source_attachment_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profile_drafts"),
        sa.UniqueConstraint(
            "source_attachment_id",
            name="uq_profile_drafts__source_attachment_id",
        ),
        sa.CheckConstraint(
            "id = 'current'",
            name="singleton_id",
        ),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name="fk_chat_messages__conversation_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="role",
        ),
        sa.CheckConstraint(
            "content != '' OR structured_payload IS NOT NULL",
            name="content_payload_coupling",
        ),
    )
    op.create_index(
        "ix_chat_messages__conversation_created_at",
        "chat_messages",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_message_id", sa.Text(), nullable=False),
        sa.Column(
            "state",
            sa.Text(),
            server_default="running",
            nullable=False,
        ),
        sa.Column("pending_approval_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["chat_messages.id"],
            name="fk_agent_runs__user_message_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.UniqueConstraint(
            "user_message_id",
            name="uq_agent_runs__user_message_id",
        ),
        sa.CheckConstraint(
            "state IN ('running', 'interrupted', 'completed', 'failed')",
            name="state",
        ),
        sa.CheckConstraint(
            "state = 'interrupted' AND pending_approval_json IS NOT NULL "
            "OR state != 'interrupted' AND pending_approval_json IS NULL",
            name="pending_approval_coupling",
        ),
        sa.CheckConstraint(
            "state IN ('completed', 'failed') AND completed_at IS NOT NULL "
            "OR (state NOT IN ('completed', 'failed')) AND completed_at IS NULL",
            name="completed_at_coupling",
        ),
    )
    op.create_index(
        "ix_agent_runs__state",
        "agent_runs",
        ["state"],
        unique=False,
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("tool_call_id", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("arguments_summary_json", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_tool_executions__run_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tool_executions"),
        sa.UniqueConstraint(
            "run_id",
            "tool_call_id",
            name="uq_tool_executions__run_tool_call",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="status",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'failed') AND duration_ms IS NOT NULL "
            "AND result_json IS NOT NULL OR "
            "(status NOT IN ('completed', 'failed')) AND duration_ms IS NULL "
            "AND result_json IS NULL",
            name="terminal_result_duration",
        ),
        sa.CheckConstraint(
            "status = 'failed' AND error_code IS NOT NULL "
            "OR status != 'failed' AND error_code IS NULL",
            name="error_coupling",
        ),
    )
    op.create_index(
        "ix_tool_executions__run_status",
        "tool_executions",
        ["run_id", "status"],
        unique=False,
    )

    # Singleton seeds (idempotent); never seed candidate_profile.
    ensure_singleton_seeds_on_connection(op.get_bind())


def downgrade() -> None:
    # Application tables only — never touch checkpoint-like tables.
    op.drop_index("ix_tool_executions__run_status", table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_index("ix_agent_runs__state", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(
        "ix_chat_messages__conversation_created_at",
        table_name="chat_messages",
    )
    op.drop_table("chat_messages")
    op.drop_table("profile_drafts")
    op.drop_table("candidate_profile")
    op.drop_table("job_preferences")
    op.drop_index(
        "ix_job_posts__processing_quality",
        table_name="job_posts",
    )
    op.drop_table("job_posts")
    op.drop_table("conversation")
    op.execute("DROP INDEX IF EXISTS uq_attachments__single_active")
    op.drop_table("attachments")
