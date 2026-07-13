"""SQLAlchemy contracts for profile-family application tables.

Defines ``candidate_profile``, ``profile_drafts``, and ``job_preferences`` with
singleton ID checks, attachment foreign keys/delete actions, and JSON columns.
JSON document shape, approval writes, and attachment cross-row state are
enforced by services, not this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, column
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.time import utc_now
from app.db.base import Base

# Fixed singleton primary keys (Master §6.1 / §6.2) — single production owners.
CANDIDATE_PROFILE_ID = "active"
PROFILE_DRAFT_ID = "current"
JOB_PREFERENCES_ID = "active"

# Preference document keys (lists only; service validates writes).
JOB_PREFERENCE_KEYS: tuple[str, ...] = (
    "target_roles",
    "preferred_locations",
    "acceptable_work_modes",
    "target_seniority",
)


def _empty_job_preferences() -> dict[str, list[Any]]:
    """Return a fresh empty preferences document (four empty lists)."""
    return {key: [] for key in JOB_PREFERENCE_KEYS}


class CandidateProfile(Base):
    """Zero-or-one approved candidate profile row (singleton id ``active``)."""

    __tablename__ = "candidate_profile"
    __table_args__ = (
        CheckConstraint(
            column("id") == CANDIDATE_PROFILE_ID,
            name="singleton_id",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    active_attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
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


class ProfileDraft(Base):
    """Zero-or-one pending profile/preferences draft (singleton id ``current``)."""

    __tablename__ = "profile_drafts"
    __table_args__ = (
        CheckConstraint(
            column("id") == PROFILE_DRAFT_ID,
            name="singleton_id",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_attachment_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    draft_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
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


class JobPreferences(Base):
    """Exactly one preferences row after seed (singleton id ``active``)."""

    __tablename__ = "job_preferences"
    __table_args__ = (
        CheckConstraint(
            column("id") == JOB_PREFERENCES_ID,
            name="singleton_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=JOB_PREFERENCES_ID,
        server_default=JOB_PREFERENCES_ID,
    )
    preferences_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=_empty_job_preferences,
    )
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
