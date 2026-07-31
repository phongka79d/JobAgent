"""SQLAlchemy contracts for multi-profile workspace state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    column,
    literal_column,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base

WORKSPACE_STATE_ID = "main"
PROFILE_STATE_PENDING = "pending"
PROFILE_STATE_READY = "ready"
PROFILE_STATE_DELETING = "deleting"
PROFILE_STATES = frozenset(
    {PROFILE_STATE_PENDING, PROFILE_STATE_READY, PROFILE_STATE_DELETING}
)
PROFILE_SETUP_STATUS_AWAITING_EXTRACTION = "awaiting_extraction"
PROFILE_SETUP_STATUS_AWAITING_APPROVAL = "awaiting_approval"
PROFILE_SETUP_STATUS_EXTRACTION_FAILED = "extraction_failed"
PROFILE_DISPLAY_NAME_MAX = 120
CONVERSATION_TITLE_MAX = 120
PROFILE_SKILL_TAG_LIMIT = 12
NEW_CONVERSATION_TITLE = "New chat"

# ponytail: Legacy modules are migrated in Tasks 5 and 8, so these import-only
# aliases temporarily keep the application importable. Remove them when those
# callers use durable profile IDs; the upgrade path is profile-scoped lookup.
CANDIDATE_PROFILE_ID = "active"
PROFILE_DRAFT_ID = "current"
JOB_PREFERENCES_ID = "active"
JOB_PREFERENCE_KEYS: tuple[str, ...] = (
    "target_roles",
    "preferred_locations",
    "acceptable_work_modes",
    "target_seniority",
)


class Profile(Base):
    """One source-backed candidate profile owned by one attachment."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "(state = 'pending' "
            "AND profile_json IS NULL AND location IS NULL "
            "AND extraction_version IS NULL AND source_hash IS NULL) "
            "OR (state = 'ready' "
            "AND profile_json IS NOT NULL "
            "AND extraction_version IS NOT NULL AND source_hash IS NOT NULL) "
            "OR (state = 'deleting' AND ("
            "(profile_json IS NULL AND location IS NULL "
            "AND extraction_version IS NULL AND source_hash IS NULL) "
            "OR (profile_json IS NOT NULL "
            "AND extraction_version IS NOT NULL AND source_hash IS NOT NULL)))",
            name="state",
        ),
        Index(
            "uq_profiles__single_incomplete",
            literal_column("1"),
            unique=True,
            sqlite_where=column("profile_json").is_(None),
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    profile_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    @property
    def active_attachment_id(self) -> str:
        """Temporary read alias for callers migrated in Tasks 5 and 8."""
        return self.attachment_id


class ProfileDraft(Base):
    """Pending candidate/profile-preference draft for an attachment."""

    __tablename__ = "profile_drafts"
    __table_args__ = (
        UniqueConstraint(
            "target_profile_id", name="uq_profile_drafts__target_profile_id"
        ),
        UniqueConstraint(
            "reextract_operation_id",
            name="uq_profile_drafts__reextract_operation_id",
        ),
        CheckConstraint(
            "reextract_operation_id IS NULL OR source_attachment_id IS NOT NULL",
            name="reextract_source_coupling",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    source_attachment_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    target_profile_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    reextract_operation_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("profile_reextract_operations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    draft_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProfileReextractOperation(Base):
    """Durable, profile-owned direct CV re-extraction metadata."""

    __tablename__ = "profile_reextract_operations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running', 'review_ready', 'interrupted', 'failed', 'stale')",
            name="state",
        ),
        CheckConstraint(
            "state IN ('interrupted', 'failed', 'stale') AND error_code IS NOT NULL "
            "OR state IN ('running', 'review_ready') AND error_code IS NULL",
            name="error_coupling",
        ),
        Index(
            "uq_profile_reextract_operations_actionable",
            "profile_id",
            unique=True,
            sqlite_where=column("state").in_(("running", "review_ready")),
        ),
        Index(
            "ix_profile_reextract_operations_recovery",
            "profile_id",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    base_profile_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    base_workspace_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProfilePreference(Base):
    """Job preferences belonging to exactly one profile."""

    __tablename__ = "profile_preferences"

    profile_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    preferences_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    @property
    def id(self) -> str:
        """Temporary read alias for callers migrated in Task 5."""
        return self.profile_id


class WorkspaceState(Base):
    """Singleton pointer to the active profile for the local workspace."""

    __tablename__ = "workspace_state"
    __table_args__ = (
        CheckConstraint(column("id") == WORKSPACE_STATE_ID, name="singleton_id"),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=WORKSPACE_STATE_ID,
        server_default=WORKSPACE_STATE_ID,
    )
    active_profile_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


# ponytail: Type aliases keep legacy imports collectable while services are
# migrated task-by-task. Remove them after Tasks 5 and 8; no legacy tables or
# singleton writes are restored by these aliases.
CandidateProfile = Profile
JobPreferences = ProfilePreference
