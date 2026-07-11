"""Candidate profile, draft, and job preference singletons / drafts.

Structured JSON columns (profile_json, draft_json, preferences_json) are opaque
at the ORM boundary. Validated Pydantic documents are enforced by repositories
in later plans — no generic unvalidated public repository API is defined here.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import SINGLETON_PK, Base, TimestampMixin, new_uuid
from app.db.enums import ProfileDraftState


class CandidateProfile(Base, TimestampMixin):
    """Singleton current approved Candidate Profile (no historical snapshots)."""

    __tablename__ = "candidate_profile"
    __table_args__ = (
        CheckConstraint(f"id = {SINGLETON_PK}", name="singleton_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_PK)
    active_attachment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Opaque JSON document; validate at repository boundary (later plans).
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ProfileDraft(Base, TimestampMixin):
    """Temporary profile/preference proposal awaiting approval."""

    __tablename__ = "profile_drafts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'discarded')",
            name="profile_draft_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)
    source_attachment_id: Mapped[UUID] = mapped_column(
        ForeignKey("attachments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    draft_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProfileDraftState.PENDING.value,
    )


class JobPreferences(Base, TimestampMixin):
    """Singleton target roles, locations, work modes, and level preferences."""

    __tablename__ = "job_preferences"
    __table_args__ = (
        CheckConstraint(f"id = {SINGLETON_PK}", name="singleton_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_PK)
    preferences_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
