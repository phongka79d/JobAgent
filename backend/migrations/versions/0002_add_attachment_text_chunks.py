"""Add archived attachment state and attachment_text_chunks table.

Revision ID: 0002_add_attachment_text_chunks
Revises: 0001_initial_schema
Create Date: 2026-07-16

Extends attachments.state with immutable ``archived`` without converting
existing staged/failed/active rows. Creates ``attachment_text_chunks`` for
canonical successful-extraction text segments (UUID PK, attachment+ordinal
unique, RESTRICT FK).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_attachment_text_chunks"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite: batch recreate to replace the state CHECK (add archived).
    # Constraint was created in 0001 with bare name "state" (ck_ naming is
    # applied by SQLAlchemy metadata, not by the raw Alembic DDL name).
    with op.batch_alter_table("attachments") as batch_op:
        batch_op.drop_constraint("state", type_="check")
        batch_op.create_check_constraint(
            "state",
            "state IN ('staged', 'active', 'archived', 'failed')",
        )

    op.create_table(
        "attachment_text_chunks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("attachment_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("preview", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_attachment_text_chunks"),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_attachment_text_chunks__attachment_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "attachment_id",
            "ordinal",
            name="uq_attachment_text_chunks__attachment_ordinal",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ordinal_non_negative",
        ),
        sa.CheckConstraint(
            "char_count > 0",
            name="char_count_positive",
        ),
        sa.CheckConstraint(
            "token_estimate >= 0",
            name="token_estimate_non_negative",
        ),
    )


def downgrade() -> None:
    op.drop_table("attachment_text_chunks")

    # Refuse downgrade while archived rows exist (would violate restored CHECK).
    conn = op.get_bind()
    count = conn.execute(
        sa.text("SELECT COUNT(*) FROM attachments WHERE state = 'archived'")
    ).scalar_one()
    if int(count) > 0:
        raise RuntimeError(
            "cannot downgrade 0002 while archived attachments exist"
        )

    with op.batch_alter_table("attachments") as batch_op:
        batch_op.drop_constraint("state", type_="check")
        batch_op.create_check_constraint(
            "state",
            "state IN ('staged', 'active', 'failed')",
        )
