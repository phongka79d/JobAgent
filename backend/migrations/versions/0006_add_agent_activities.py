"""Add the durable Agent activity timeline projection.

Revision ID: 0006_add_agent_activities
Revises: 0005_cv_profiles_multi_conversation
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_agent_activities"
down_revision: str | None = "0005_cv_profiles_multi_conversation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_activities",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("technical_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_agent_activities"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_agent_activities__run_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_activities__run_sequence",
        ),
        sa.CheckConstraint("sequence >= 0", name="sequence_non_negative"),
        sa.CheckConstraint("label != ''", name="label_non_empty"),
        sa.CheckConstraint(
            "technical_name IS NULL OR technical_name != ''",
            name="technical_name_non_empty",
        ),
        sa.CheckConstraint("kind IN ('assistant', 'tool')", name="kind"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="status",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'failed') AND completed_at IS NOT NULL "
            "OR status NOT IN ('completed', 'failed') AND completed_at IS NULL",
            name="completed_at_coupling",
        ),
        sa.CheckConstraint(
            "status = 'failed' AND error_code IS NOT NULL "
            "OR status != 'failed' AND error_code IS NULL",
            name="error_coupling",
        ),
    )
    op.create_index(
        "ix_agent_activities__run_sequence",
        "agent_activities",
        ["run_id", "sequence"],
        unique=False,
    )
    op.create_index(
        "ix_agent_activities__run_status",
        "agent_activities",
        ["run_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_activities__run_status", table_name="agent_activities"
    )
    op.drop_index(
        "ix_agent_activities__run_sequence", table_name="agent_activities"
    )
    op.drop_table("agent_activities")
