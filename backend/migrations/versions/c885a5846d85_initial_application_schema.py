"""Initial application SQLite schema (eleven tables).

Revision ID: c885a5846d85
Revises:
Create Date: 2026-07-11 17:04:50.763563

Reviewed against app.db model metadata. Contains only application tables;
LangGraph checkpoint objects are intentionally excluded.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c885a5846d85"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the complete application schema at one head revision."""
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('staged', 'active')",
            name=op.f("ck_attachments_attachment_state"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
    )
    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_attachments_file_hash"),
            ["file_hash"],
            unique=True,
        )

    op.create_table(
        "conversation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_conversation_singleton_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation")),
    )

    op.create_table(
        "graph_sync_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'synced', 'failed')",
            name=op.f("ck_graph_sync_outbox_outbox_status"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_graph_sync_outbox_outbox_attempts_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_sync_outbox")),
    )
    with op.batch_alter_table("graph_sync_outbox", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_graph_sync_outbox_entity_id"),
            ["entity_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_graph_sync_outbox_operation"),
            ["operation"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_graph_sync_outbox_status"),
            ["status"],
            unique=False,
        )

    op.create_table(
        "job_posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("raw_content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_key", sa.String(length=512), nullable=True),
        sa.Column("extracted_json", sa.JSON(), nullable=True),
        sa.Column("quality_reasons", sa.JSON(), nullable=True),
        sa.Column("score_cache", sa.JSON(), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("jd_quality", sa.String(length=32), nullable=True),
        sa.Column("graph_sync_status", sa.String(length=32), nullable=False),
        sa.Column("record_status", sa.String(length=32), nullable=False),
        sa.Column("duplicate_of_job_id", sa.Uuid(), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "graph_sync_status IN "
            "('not_required', 'pending', 'synced', 'failed')",
            name=op.f("ck_job_posts_graph_sync_status"),
        ),
        sa.CheckConstraint(
            "jd_quality IS NULL OR jd_quality IN "
            "('full', 'partial', 'unscorable')",
            name=op.f("ck_job_posts_jd_quality"),
        ),
        sa.CheckConstraint(
            "processing_status IN "
            "('received', 'processing', 'processed', 'failed')",
            name=op.f("ck_job_posts_processing_status"),
        ),
        sa.CheckConstraint(
            "record_status IN ('active', 'ignored_duplicate')",
            name=op.f("ck_job_posts_record_status"),
        ),
        sa.CheckConstraint(
            "source_type IN ('url', 'text')",
            name=op.f("ck_job_posts_job_source_type"),
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_job_id"],
            ["job_posts.id"],
            name=op.f("fk_job_posts_duplicate_of_job_id_job_posts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_posts")),
    )
    with op.batch_alter_table("job_posts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_job_posts_duplicate_of_job_id"),
            ["duplicate_of_job_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_job_posts_graph_sync_status"),
            ["graph_sync_status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_job_posts_normalized_key"),
            ["normalized_key"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_job_posts_processing_status"),
            ["processing_status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_job_posts_raw_content_hash"),
            ["raw_content_hash"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_job_posts_record_status"),
            ["record_status"],
            unique=False,
        )

    op.create_table(
        "job_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "id = 1",
            name=op.f("ck_job_preferences_singleton_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_preferences")),
    )

    op.create_table(
        "memory_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=256), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_facts")),
    )
    with op.batch_alter_table("memory_facts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_memory_facts_key"),
            ["key"],
            unique=True,
        )

    op.create_table(
        "candidate_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("active_attachment_id", sa.Uuid(), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "id = 1",
            name=op.f("ck_candidate_profile_singleton_id"),
        ),
        sa.ForeignKeyConstraint(
            ["active_attachment_id"],
            ["attachments.id"],
            name=op.f("fk_candidate_profile_active_attachment_id_attachments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_profile")),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name=op.f("ck_chat_messages_message_role"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("fk_chat_messages_conversation_id_conversation"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_messages_conversation_id"),
            ["conversation_id"],
            unique=False,
        )

    op.create_table(
        "profile_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_attachment_id", sa.Uuid(), nullable=False),
        sa.Column("draft_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending', 'discarded')",
            name=op.f("ck_profile_drafts_profile_draft_state"),
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name=op.f("fk_profile_drafts_source_attachment_id_attachments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_drafts")),
    )
    with op.batch_alter_table("profile_drafts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_profile_drafts_source_attachment_id"),
            ["source_attachment_id"],
            unique=False,
        )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("pending_approval", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN "
            "('pending', 'running', 'interrupted', 'completed', 'failed')",
            name=op.f("ck_agent_runs_agent_run_state"),
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name=op.f("fk_agent_runs_message_id_chat_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_agent_runs_message_id"),
            ["message_id"],
            unique=True,
        )

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments_summary", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed')",
            name=op.f("ck_tool_executions_tool_execution_status"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_tool_executions_agent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_executions")),
    )
    with op.batch_alter_table("tool_executions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_tool_executions_agent_run_id"),
            ["agent_run_id"],
            unique=False,
        )


def downgrade() -> None:
    """Reverse schema changes.

    Not wired into local automation. JobAgent documents a single-purpose
    ``upgrade head`` path only; do not add automatic destructive downgrade
    or volume-reset commands.
    """
    with op.batch_alter_table("tool_executions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tool_executions_agent_run_id"))
    op.drop_table("tool_executions")

    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_runs_message_id"))
    op.drop_table("agent_runs")

    with op.batch_alter_table("profile_drafts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_profile_drafts_source_attachment_id"))
    op.drop_table("profile_drafts")

    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_messages_conversation_id"))
    op.drop_table("chat_messages")

    op.drop_table("candidate_profile")

    with op.batch_alter_table("memory_facts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_memory_facts_key"))
    op.drop_table("memory_facts")

    op.drop_table("job_preferences")

    with op.batch_alter_table("job_posts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_posts_record_status"))
        batch_op.drop_index(batch_op.f("ix_job_posts_raw_content_hash"))
        batch_op.drop_index(batch_op.f("ix_job_posts_processing_status"))
        batch_op.drop_index(batch_op.f("ix_job_posts_normalized_key"))
        batch_op.drop_index(batch_op.f("ix_job_posts_graph_sync_status"))
        batch_op.drop_index(batch_op.f("ix_job_posts_duplicate_of_job_id"))
    op.drop_table("job_posts")

    with op.batch_alter_table("graph_sync_outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_graph_sync_outbox_status"))
        batch_op.drop_index(batch_op.f("ix_graph_sync_outbox_operation"))
        batch_op.drop_index(batch_op.f("ix_graph_sync_outbox_entity_id"))
    op.drop_table("graph_sync_outbox")

    op.drop_table("conversation")

    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_attachments_file_hash"))
    op.drop_table("attachments")
