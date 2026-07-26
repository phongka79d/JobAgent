"""Add derivative CV-tailoring sessions and immutable versions.

Revision ID: 0007_add_cv_tailoring
Revises: 0006_add_agent_activities
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_cv_tailoring"
down_revision: str | None = "0006_add_agent_activities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cv_tailoring_sessions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("source_attachment_id", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("profile_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("job_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_label_json", sa.JSON(), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column(
            "template_version",
            sa.Text(),
            nullable=False,
            server_default="latex-cv-v1",
        ),
        sa.Column("state", sa.Text(), nullable=False, server_default="generating"),
        sa.Column(
            "latest_version_number", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cv_tailoring_sessions"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_cv_tailoring_sessions__profile_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name="fk_cv_tailoring_sessions__source_attachment_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_posts.id"],
            name="fk_cv_tailoring_sessions__job_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "state IN ('generating', 'ready', 'failed', 'deleting')", name="state"
        ),
        sa.CheckConstraint(
            "latest_version_number >= 0", name="latest_version_non_negative"
        ),
        sa.CheckConstraint(
            "state = 'failed' AND error_code IS NOT NULL "
            "OR state != 'failed' AND error_code IS NULL",
            name="error_coupling",
        ),
    )
    op.create_index(
        "ix_cv_tailoring_sessions__profile_updated",
        "cv_tailoring_sessions",
        ["profile_id", "updated_at"],
    )
    op.create_index(
        "ix_cv_tailoring_sessions__job_id",
        "cv_tailoring_sessions",
        ["job_id"],
    )
    op.create_index(
        "ix_cv_tailoring_sessions__state",
        "cv_tailoring_sessions",
        ["state"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_cv_tailoring_sessions__job_or_instruction
        BEFORE INSERT ON cv_tailoring_sessions
        BEGIN
          SELECT CASE WHEN NEW.job_id IS NULL AND trim(NEW.instruction) = ''
          THEN RAISE(ABORT, 'tailoring requires job or instruction') END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_cv_tailoring_sessions__ready_profile_insert
        BEFORE INSERT ON cv_tailoring_sessions
        BEGIN
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM profiles p
            WHERE p.id = NEW.profile_id
              AND p.state = 'ready'
              AND p.attachment_id = NEW.source_attachment_id
              AND p.source_hash = NEW.source_hash
          ) THEN RAISE(ABORT, 'tailoring source profile is not ready/current') END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_cv_tailoring_sessions__ready_profile_update
        BEFORE UPDATE OF profile_id, source_attachment_id, source_hash
        ON cv_tailoring_sessions
        BEGIN
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM profiles p
            WHERE p.id = NEW.profile_id
              AND p.state = 'ready'
              AND p.attachment_id = NEW.source_attachment_id
              AND p.source_hash = NEW.source_hash
          ) THEN RAISE(ABORT, 'tailoring source profile is not ready/current') END;
        END
        """
    )
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("agent_runs", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "run_kind", sa.Text(), nullable=False, server_default="chat"
            )
        )
        batch_op.alter_column(
            "user_message_id", existing_type=sa.Text(), nullable=True
        )
        batch_op.add_column(
            sa.Column("tailoring_session_id", sa.Text(), nullable=True)
        )
        batch_op.add_column(sa.Column("parent_run_id", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_runs__tailoring_session_id",
            "cv_tailoring_sessions",
            ["tailoring_session_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_agent_runs__parent_run_id",
            "agent_runs",
            ["parent_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "run_kind", "run_kind IN ('chat', 'cv_tailoring')"
        )
        batch_op.create_check_constraint(
            "owner_coupling",
            "(run_kind = 'chat' AND user_message_id IS NOT NULL "
            "AND tailoring_session_id IS NULL AND parent_run_id IS NULL) "
            "OR (run_kind = 'cv_tailoring' AND user_message_id IS NULL "
            "AND tailoring_session_id IS NOT NULL)",
        )
        batch_op.create_index(
            "ix_agent_runs__tailoring_session_id", ["tailoring_session_id"]
        )
        batch_op.create_index("ix_agent_runs__parent_run_id", ["parent_run_id"])
    op.execute("PRAGMA foreign_keys=ON")
    op.execute(
        """
        CREATE TRIGGER trg_agent_runs__tailoring_parent_insert
        BEFORE INSERT ON agent_runs
        BEGIN
          SELECT CASE WHEN NEW.parent_run_id IS NOT NULL AND NOT EXISTS (
            SELECT 1
            FROM agent_runs parent
            JOIN chat_messages message ON message.id = parent.user_message_id
            JOIN conversations conversation ON conversation.id = message.conversation_id
            JOIN cv_tailoring_sessions tailoring
              ON tailoring.id = NEW.tailoring_session_id
            WHERE parent.id = NEW.parent_run_id
              AND NEW.run_kind = 'cv_tailoring'
              AND parent.run_kind = 'chat'
              AND conversation.profile_id = tailoring.profile_id
              AND parent.id != NEW.id
          ) THEN RAISE(ABORT, 'invalid tailoring parent run') END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_runs__tailoring_parent_update
        BEFORE UPDATE OF run_kind, tailoring_session_id, parent_run_id ON agent_runs
        BEGIN
          SELECT CASE WHEN NEW.parent_run_id IS NOT NULL AND NOT EXISTS (
            SELECT 1
            FROM agent_runs parent
            JOIN chat_messages message ON message.id = parent.user_message_id
            JOIN conversations conversation ON conversation.id = message.conversation_id
            JOIN cv_tailoring_sessions tailoring
              ON tailoring.id = NEW.tailoring_session_id
            WHERE parent.id = NEW.parent_run_id
              AND NEW.run_kind = 'cv_tailoring'
              AND parent.run_kind = 'chat'
              AND conversation.profile_id = tailoring.profile_id
              AND parent.id != NEW.id
          ) THEN RAISE(ABORT, 'invalid tailoring parent run') END;
        END
        """
    )
    op.create_table(
        "cv_tailoring_versions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("source_revision_json", sa.JSON(), nullable=False),
        sa.Column("tex_relative_path", sa.Text(), nullable=False),
        sa.Column("pdf_relative_path", sa.Text(), nullable=False),
        sa.Column("tex_sha256", sa.Text(), nullable=False),
        sa.Column("pdf_sha256", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("page_warning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cv_tailoring_versions"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["cv_tailoring_sessions.id"],
            name="fk_cv_tailoring_versions__session_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "session_id",
            "version_number",
            name="uq_cv_tailoring_versions__session_version",
        ),
        sa.UniqueConstraint(
            "session_id",
            "id",
            name="uq_cv_tailoring_versions__session_id_id",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "parent_version_id"],
            ["cv_tailoring_versions.session_id", "cv_tailoring_versions.id"],
            name="fk_cv_tailoring_versions__session_parent",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("version_number > 0", name="version_positive"),
        sa.CheckConstraint("created_by IN ('ai', 'user')", name="created_by"),
        sa.CheckConstraint("page_count > 0", name="page_count_positive"),
        sa.CheckConstraint(
            "version_number = 1 AND parent_version_id IS NULL "
            "OR version_number > 1 AND parent_version_id IS NOT NULL",
            name="parent_coupling",
        ),
    )
    op.create_index(
        "ix_cv_tailoring_versions__session_created",
        "cv_tailoring_versions",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cv_tailoring_versions__session_created",
        table_name="cv_tailoring_versions",
    )
    op.drop_table("cv_tailoring_versions")
    op.execute("DROP TRIGGER IF EXISTS trg_agent_runs__tailoring_parent_update")
    op.execute("DROP TRIGGER IF EXISTS trg_agent_runs__tailoring_parent_insert")
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute(
        "DELETE FROM agent_activities WHERE run_id IN "
        "(SELECT id FROM agent_runs WHERE run_kind = 'cv_tailoring')"
    )
    op.execute(
        "DELETE FROM tool_executions WHERE run_id IN "
        "(SELECT id FROM agent_runs WHERE run_kind = 'cv_tailoring')"
    )
    op.execute("DELETE FROM agent_runs WHERE run_kind = 'cv_tailoring'")
    op.execute("DELETE FROM cv_tailoring_sessions")
    with op.batch_alter_table("agent_runs", recreate="always") as batch_op:
        batch_op.drop_index("ix_agent_runs__parent_run_id")
        batch_op.drop_index("ix_agent_runs__tailoring_session_id")
        batch_op.drop_constraint(
            op.f("ck_agent_runs__owner_coupling"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_agent_runs__run_kind"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("fk_agent_runs__parent_run_id"), type_="foreignkey"
        )
        batch_op.drop_constraint(
            op.f("fk_agent_runs__tailoring_session_id"), type_="foreignkey"
        )
        batch_op.drop_column("parent_run_id")
        batch_op.drop_column("tailoring_session_id")
        batch_op.alter_column(
            "user_message_id", existing_type=sa.Text(), nullable=False
        )
        batch_op.drop_column("run_kind")
    op.execute("PRAGMA foreign_keys=ON")
    op.execute("DROP TRIGGER IF EXISTS trg_cv_tailoring_sessions__ready_profile_update")
    op.execute("DROP TRIGGER IF EXISTS trg_cv_tailoring_sessions__ready_profile_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_cv_tailoring_sessions__job_or_instruction")
    op.drop_index(
        "ix_cv_tailoring_sessions__state", table_name="cv_tailoring_sessions"
    )
    op.drop_index(
        "ix_cv_tailoring_sessions__job_id", table_name="cv_tailoring_sessions"
    )
    op.drop_index(
        "ix_cv_tailoring_sessions__profile_updated",
        table_name="cv_tailoring_sessions",
    )
    op.drop_table("cv_tailoring_sessions")
