"""Add job_evaluations table for validated per-context MatchResult rows.

Revision ID: 0004_add_job_evaluations
Revises: 0003_add_cv_documents_and_ownership
Create Date: 2026-07-18

Structural only: no provider, filesystem, Neo4j, or evaluation-row synthesis.
Preserves every existing application and checkpoint row.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_job_evaluations"
down_revision: str | None = "0003_add_cv_documents_and_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_evaluations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("active_attachment_id", sa.Text(), nullable=False),
        sa.Column("evaluation_context_hash", sa.Text(), nullable=False),
        sa.Column("job_revision", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "profile_revision", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "preferences_revision",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
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
            ["active_attachment_id"],
            ["attachments.id"],
            name="fk_job_evaluations__active_attachment_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "job_id",
            "evaluation_context_hash",
            name="uq_job_evaluations__job_context",
        ),
    )
    op.create_index(
        "ix_job_evaluations__job_created_at",
        "job_evaluations",
        ["job_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_evaluations__job_created_at",
        table_name="job_evaluations",
    )
    op.drop_table("job_evaluations")
