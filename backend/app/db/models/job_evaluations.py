"""SQLAlchemy contract for the ``job_evaluations`` application table.

Static column, unique, index, and CASCADE FK invariants only. Canonical
context hashing, MatchResult validation, and current/stale derivation belong
to services/repositories.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base


class JobEvaluation(Base):
    """One validated MatchResult projection for an exact Job evaluation context."""

    __tablename__ = "job_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "evaluation_context_hash",
            name="uq_job_evaluations__job_context",
        ),
        Index(
            "ix_job_evaluations__job_created_at",
            "job_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=new_uuid,
    )
    job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    active_attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_context_hash: Mapped[str] = mapped_column(Text, nullable=False)
    job_revision: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    profile_revision: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    preferences_revision: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    cv_source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    matching_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
