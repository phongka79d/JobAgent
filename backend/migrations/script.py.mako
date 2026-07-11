"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """Apply schema changes (forward only for the reviewed initial revision)."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Reverse schema changes.

    Intentionally not used by local automation. JobAgent documents a
    single-purpose upgrade path only; do not wire automatic destructive
    downgrade/reset into scripts or tests.
    """
    ${downgrades if downgrades else "pass"}
