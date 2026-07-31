"""Add durable profile re-extraction operations and scoped draft ownership.

Revision ID: 0008_profile_reextract_ownership
Revises: 0007_add_cv_tailoring
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision: str = "0008_profile_reextract_ownership"
down_revision: str | None = "0007_add_cv_tailoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _reject_ambiguous_drafts(connection: sa.Connection) -> None:
    checks = (
        (
            "profile_drafts.target_profile_id is null or orphaned",
            "SELECT 1 FROM profile_drafts draft "
            "LEFT JOIN profiles profile ON profile.id = draft.target_profile_id "
            "WHERE draft.target_profile_id IS NULL OR profile.id IS NULL LIMIT 1",
        ),
        (
            "profile_drafts.target_profile_id is duplicated",
            "SELECT 1 FROM profile_drafts GROUP BY target_profile_id "
            "HAVING COUNT(*) > 1 LIMIT 1",
        ),
        (
            "profile_drafts.source_attachment_id is orphaned",
            "SELECT 1 FROM profile_drafts draft "
            "LEFT JOIN attachments attachment "
            "ON attachment.id = draft.source_attachment_id "
            "WHERE draft.source_attachment_id IS NOT NULL "
            "AND attachment.id IS NULL LIMIT 1",
        ),
    )
    for message, statement in checks:
        if connection.execute(sa.text(statement)).fetchone() is not None:
            raise CommandError(
                f"Migration 0008 refused: {message}. Restore a verified backup "
                "or repair ownership explicitly before retrying."
            )
    if connection.execute(sa.text("PRAGMA foreign_key_check")).fetchone() is not None:
        raise CommandError(
            "Migration 0008 refused: foreign_key_check reported existing "
            "violations. Restore a verified backup or repair them before retrying."
        )


def upgrade() -> None:
    connection = op.get_bind()
    _reject_ambiguous_drafts(connection)

    op.create_table(
        "profile_reextract_operations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("source_attachment_id", sa.Text(), nullable=False),
        sa.Column(
            "base_profile_updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "base_workspace_updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profile_reextract_operations"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_profile_reextract_operations__profile_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_attachment_id"],
            ["attachments.id"],
            name="fk_profile_reextract_operations__source_attachment_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('running', 'review_ready', 'interrupted', 'failed', 'stale')",
            name="state",
        ),
        sa.CheckConstraint(
            "state IN ('interrupted', 'failed', 'stale') AND error_code IS NOT NULL "
            "OR state IN ('running', 'review_ready') AND error_code IS NULL",
            name="error_coupling",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_profile_reextract_operations_actionable "
        "ON profile_reextract_operations (profile_id) "
        "WHERE state IN ('running', 'review_ready')"
    )
    op.create_index(
        "ix_profile_reextract_operations_recovery",
        "profile_reextract_operations",
        ["profile_id", "updated_at", "id"],
    )

    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("profile_drafts", recreate="always") as batch_op:
        batch_op.alter_column(
            "target_profile_id", existing_type=sa.Text(), nullable=False
        )
        batch_op.add_column(
            sa.Column("reextract_operation_id", sa.Text(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_profile_drafts__reextract_operation_id",
            "profile_reextract_operations",
            ["reextract_operation_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_unique_constraint(
            "uq_profile_drafts__target_profile_id", ["target_profile_id"]
        )
        batch_op.create_unique_constraint(
            "uq_profile_drafts__reextract_operation_id", ["reextract_operation_id"]
        )
        batch_op.create_check_constraint(
            "reextract_source_coupling",
            "reextract_operation_id IS NULL OR source_attachment_id IS NOT NULL",
        )
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT 1 FROM profile_reextract_operations LIMIT 1")
    ).fetchone() is not None:
        raise CommandError(
            "Migration 0008 downgrade refused: profile_reextract_operations "
            "contains durable rows. Restore the verified pre-migration backup."
        )
    if connection.execute(
        sa.text(
            "SELECT 1 FROM profile_drafts "
            "WHERE reextract_operation_id IS NOT NULL LIMIT 1"
        )
    ).fetchone() is not None:
        raise CommandError(
            "Migration 0008 downgrade refused: profile_drafts references an "
            "operation. Restore the verified pre-migration backup."
        )

    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("profile_drafts", recreate="always") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_profile_drafts__reextract_source_coupling"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("uq_profile_drafts__reextract_operation_id"), type_="unique"
        )
        batch_op.drop_constraint(
            op.f("uq_profile_drafts__target_profile_id"), type_="unique"
        )
        batch_op.drop_constraint(
            op.f("fk_profile_drafts__reextract_operation_id"), type_="foreignkey"
        )
        batch_op.drop_column("reextract_operation_id")
        batch_op.alter_column(
            "target_profile_id", existing_type=sa.Text(), nullable=True
        )
    op.execute("PRAGMA foreign_keys=ON")
    op.drop_index(
        "ix_profile_reextract_operations_recovery",
        table_name="profile_reextract_operations",
    )
    op.drop_index(
        "uq_profile_reextract_operations_actionable",
        table_name="profile_reextract_operations",
    )
    op.drop_table("profile_reextract_operations")
