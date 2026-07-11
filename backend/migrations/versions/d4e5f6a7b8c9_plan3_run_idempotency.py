"""Plan 3 additive run request-idempotency columns on agent_runs.

Revision ID: d4e5f6a7b8c9
Revises: c885a5846d85
Create Date: 2026-07-11 20:00:00.000000

Adds only:
- agent_runs.turn_idempotency_key (nullable unique) for durable turn replay
- agent_runs.resume_idempotency_key (nullable) for durable resume replay

Does not recreate tables, drop columns, or touch LangGraph checkpoint objects.
Compatible with a fresh empty file and an already-initialized Plan 2 schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c885a5846d85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add minimum durable idempotency columns to existing agent_runs table."""
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("turn_idempotency_key", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("resume_idempotency_key", sa.String(length=128), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_agent_runs_turn_idempotency_key"),
            ["turn_idempotency_key"],
            unique=True,
        )


def downgrade() -> None:
    """Reverse additive columns.

    Not wired into local automation. JobAgent documents a single-purpose
    ``upgrade head`` path only; do not add automatic destructive downgrade
    or volume-reset commands.
    """
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_runs_turn_idempotency_key"))
        batch_op.drop_column("resume_idempotency_key")
        batch_op.drop_column("turn_idempotency_key")
