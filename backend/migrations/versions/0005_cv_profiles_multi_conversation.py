"""Replace singleton CV/profile/chat state with multi-profile conversations.

Revision ID: 0005_cv_profiles_multi_conversation
Revises: 0004_add_job_evaluations
Create Date: 2026-07-23

This is an intentionally destructive local-MVP reset boundary. Existing
application data must be reset before upgrading; checkpoint-like tables are
outside this migration's ownership and remain untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_cv_profiles_multi_conversation"
down_revision: str | None = "0004_add_job_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_DATA_TABLES = (
    "attachments",
    "attachment_text_chunks",
    "cv_documents",
    "cv_document_drafts",
    "candidate_profile",
    "profile_drafts",
    "job_posts",
    "chat_messages",
    "agent_runs",
    "tool_executions",
    "job_evaluations",
)
_RESET_GUIDANCE = (
    "Reset the local SQLite database and retained files, then rerun migrations."
)


def _assert_legacy_data_is_empty(connection: sa.Connection) -> None:
    populated: list[str] = []
    for table_name in _LEGACY_DATA_TABLES:
        count = connection.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table_name}"')
        ).scalar_one()
        if int(count):
            populated.append(table_name)

    non_seed_conversations = connection.execute(
        sa.text("SELECT COUNT(*) FROM conversation WHERE id <> 'main'")
    ).scalar_one()
    if int(non_seed_conversations):
        populated.append("conversation(non-seed)")

    non_seed_preferences = connection.execute(
        sa.text("SELECT COUNT(*) FROM job_preferences WHERE id <> 'active'")
    ).scalar_one()
    if int(non_seed_preferences):
        populated.append("job_preferences(non-seed)")

    if populated:
        raise RuntimeError(
            "Destructive schema migration refused because application data exists "
            f"in {', '.join(populated)}. {_RESET_GUIDANCE}"
        )


def _create_profiles() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("attachment_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("extraction_version", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profiles"),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_profiles__attachment_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("attachment_id", name="uq_profiles__attachment_id"),
    )
    op.create_table(
        "profile_preferences",
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("profile_id", name="pk_profile_preferences"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_profile_preferences__profile_id",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "workspace_state",
        sa.Column("id", sa.Text(), server_default="main", nullable=False),
        sa.Column("active_profile_id", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspace_state"),
        sa.ForeignKeyConstraint(
            ["active_profile_id"],
            ["profiles.id"],
            name="fk_workspace_state__active_profile_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("id = 'main'", name="singleton_id"),
    )
    op.create_table(
        "profile_drafts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_attachment_id", sa.Text(), nullable=True),
        sa.Column("target_profile_id", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profile_drafts"),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name="fk_profile_drafts__source_attachment_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_profile_id"],
            ["profiles.id"],
            name="fk_profile_drafts__target_profile_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "source_attachment_id",
            name="uq_profile_drafts__source_attachment_id",
        ),
    )


def _create_chat() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_conversations__profile_id",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_payload", sa.JSON(), nullable=True),
        sa.Column("source_attachment_id", sa.Text(), nullable=True),
        sa.Column("redacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_chat_messages__conversation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name="fk_chat_messages__source_attachment_id",
            ondelete="SET NULL",
        ),
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
    op.create_index(
        "ix_chat_messages__source_attachment_id",
        "chat_messages",
        ["source_attachment_id"],
        unique=False,
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_message_id", sa.Text(), nullable=False),
        sa.Column("source_attachment_id", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), server_default="running", nullable=False),
        sa.Column("pending_approval_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["chat_messages.id"],
            name="fk_agent_runs__user_message_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name="fk_agent_runs__source_attachment_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_message_id", name="uq_agent_runs__user_message_id"
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
    op.create_index("ix_agent_runs__state", "agent_runs", ["state"], unique=False)
    op.create_index(
        "ix_agent_runs__source_attachment_id",
        "agent_runs",
        ["source_attachment_id"],
        unique=False,
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("source_attachment_id", sa.Text(), nullable=True),
        sa.Column("tool_call_id", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("arguments_summary_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tool_executions"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_tool_executions__run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name="fk_tool_executions__source_attachment_id",
            ondelete="CASCADE",
        ),
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
    op.create_index(
        "ix_tool_executions__source_attachment_id",
        "tool_executions",
        ["source_attachment_id"],
        unique=False,
    )


def _create_job_evaluations() -> None:
    op.create_table(
        "job_evaluations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("evaluation_context_hash", sa.Text(), nullable=False),
        sa.Column("job_revision", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile_revision", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preferences_revision", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cv_source_hash", sa.Text(), nullable=False),
        sa.Column("matching_contract_version", sa.Text(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_job_evaluations"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_posts.id"],
            name="fk_job_evaluations__job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_job_evaluations__profile_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "job_id",
            "profile_id",
            "evaluation_context_hash",
            name="uq_job_evaluations__job_profile_context",
        ),
    )
    op.create_index(
        "ix_job_evaluations__job_created_at",
        "job_evaluations",
        ["job_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_evaluations__profile_id",
        "job_evaluations",
        ["profile_id"],
        unique=False,
    )


def upgrade() -> None:
    connection = op.get_bind()
    _assert_legacy_data_is_empty(connection)

    for table_name in (
        "tool_executions",
        "agent_runs",
        "chat_messages",
        "job_evaluations",
        "conversation",
        "job_preferences",
        "candidate_profile",
        "profile_drafts",
    ):
        op.drop_table(table_name)

    _create_profiles()
    _create_chat()
    _create_job_evaluations()
    op.execute(
        sa.text(
            "INSERT INTO workspace_state (id, active_profile_id, updated_at) "
            "VALUES ('main', NULL, CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade across the destructive multi-profile reset boundary is unsupported."
    )
