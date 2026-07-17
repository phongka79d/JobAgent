"""Add CV documents, ownership columns, deleting state, and chunk CASCADE.

Revision ID: 0003_add_cv_documents_and_ownership
Revises: 0002_add_attachment_text_chunks
Create Date: 2026-07-17

Structural only: no provider, filesystem, Neo4j, or document-row synthesis.
Preserves every existing application and checkpoint row.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_cv_documents_and_ownership"
down_revision: str | None = "0002_add_attachment_text_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Parent table rebuilds with live child FK rows require deferred FK checks.
    # PRAGMA foreign_keys cannot change inside an open multi-statement transaction.
    with op.get_context().autocommit_block():
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))

    try:
        # attachments.state: add deleting (existing staged/active/archived/failed kept).
        # Bare CHECK name "state" matches 0001/0002 SQLite batch history.
        with op.batch_alter_table("attachments") as batch_op:
            batch_op.drop_constraint("state", type_="check")
            batch_op.create_check_constraint(
                "state",
                "state IN ("
                "'staged', 'active', 'archived', 'failed', 'deleting'"
                ")",
            )

        # Chunk ownership: RESTRICT -> CASCADE via SQLite table rebuild.
        with op.batch_alter_table(
            "attachment_text_chunks",
            recreate="always",
        ) as batch_op:
            batch_op.drop_constraint(
                "fk_attachment_text_chunks__attachment_id",
                type_="foreignkey",
            )
            batch_op.create_foreign_key(
                "fk_attachment_text_chunks__attachment_id",
                "attachments",
                ["attachment_id"],
                ["id"],
                ondelete="CASCADE",
            )

        op.create_table(
            "cv_documents",
            sa.Column("attachment_id", sa.Text(), nullable=False),
            sa.Column("document_json", sa.JSON(), nullable=False),
            sa.Column("profile_json", sa.JSON(), nullable=False),
            sa.Column("outline_json", sa.JSON(), nullable=False),
            sa.Column("extraction_version", sa.Text(), nullable=False),
            sa.Column("source_hash", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("attachment_id", name="pk_cv_documents"),
            sa.ForeignKeyConstraint(
                ["attachment_id"],
                ["attachments.id"],
                name="fk_cv_documents__attachment_id",
                ondelete="CASCADE",
            ),
        )

        op.create_table(
            "cv_document_drafts",
            sa.Column("attachment_id", sa.Text(), nullable=False),
            sa.Column("document_json", sa.JSON(), nullable=False),
            sa.Column("profile_json", sa.JSON(), nullable=False),
            sa.Column("outline_json", sa.JSON(), nullable=False),
            sa.Column("extraction_version", sa.Text(), nullable=False),
            sa.Column("source_hash", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "attachment_id", name="pk_cv_document_drafts"
            ),
            sa.ForeignKeyConstraint(
                ["attachment_id"],
                ["attachments.id"],
                name="fk_cv_document_drafts__attachment_id",
                ondelete="CASCADE",
            ),
        )

        with op.batch_alter_table("chat_messages") as batch_op:
            batch_op.add_column(
                sa.Column("source_attachment_id", sa.Text(), nullable=True)
            )
            batch_op.add_column(
                sa.Column(
                    "redacted_at", sa.DateTime(timezone=True), nullable=True
                )
            )
            batch_op.create_foreign_key(
                "fk_chat_messages__source_attachment_id",
                "attachments",
                ["source_attachment_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index(
                "ix_chat_messages__source_attachment_id",
                ["source_attachment_id"],
                unique=False,
            )

        with op.batch_alter_table("agent_runs") as batch_op:
            batch_op.add_column(
                sa.Column("source_attachment_id", sa.Text(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_agent_runs__source_attachment_id",
                "attachments",
                ["source_attachment_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_index(
                "ix_agent_runs__source_attachment_id",
                ["source_attachment_id"],
                unique=False,
            )

        with op.batch_alter_table("tool_executions") as batch_op:
            batch_op.add_column(
                sa.Column("source_attachment_id", sa.Text(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_tool_executions__source_attachment_id",
                "attachments",
                ["source_attachment_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_index(
                "ix_tool_executions__source_attachment_id",
                ["source_attachment_id"],
                unique=False,
            )
    finally:
        with op.get_context().autocommit_block():
            op.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))

    try:
        with op.batch_alter_table("tool_executions") as batch_op:
            batch_op.drop_index("ix_tool_executions__source_attachment_id")
            batch_op.drop_constraint(
                "fk_tool_executions__source_attachment_id",
                type_="foreignkey",
            )
            batch_op.drop_column("source_attachment_id")

        with op.batch_alter_table("agent_runs") as batch_op:
            batch_op.drop_index("ix_agent_runs__source_attachment_id")
            batch_op.drop_constraint(
                "fk_agent_runs__source_attachment_id",
                type_="foreignkey",
            )
            batch_op.drop_column("source_attachment_id")

        with op.batch_alter_table("chat_messages") as batch_op:
            batch_op.drop_index("ix_chat_messages__source_attachment_id")
            batch_op.drop_constraint(
                "fk_chat_messages__source_attachment_id",
                type_="foreignkey",
            )
            batch_op.drop_column("redacted_at")
            batch_op.drop_column("source_attachment_id")

        op.drop_table("cv_document_drafts")
        op.drop_table("cv_documents")

        with op.batch_alter_table(
            "attachment_text_chunks",
            recreate="always",
        ) as batch_op:
            batch_op.drop_constraint(
                "fk_attachment_text_chunks__attachment_id",
                type_="foreignkey",
            )
            batch_op.create_foreign_key(
                "fk_attachment_text_chunks__attachment_id",
                "attachments",
                ["attachment_id"],
                ["id"],
                ondelete="RESTRICT",
            )

        conn = op.get_bind()
        count = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM attachments WHERE state = 'deleting'"
            )
        ).scalar_one()
        if int(count) > 0:
            raise RuntimeError(
                "cannot downgrade 0003 while deleting attachments exist"
            )

        with op.batch_alter_table("attachments") as batch_op:
            batch_op.drop_constraint("state", type_="check")
            batch_op.create_check_constraint(
                "state",
                "state IN ('staged', 'active', 'archived', 'failed')",
            )
    finally:
        with op.get_context().autocommit_block():
            op.execute(sa.text("PRAGMA foreign_keys=ON"))
