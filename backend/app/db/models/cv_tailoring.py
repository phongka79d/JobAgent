"""Derivative CV-tailoring session and immutable-version ORM contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base
from app.schemas.cv_tailoring import (
    TAILORING_SESSION_STATE_GENERATING,
    TAILORING_TEMPLATE_VERSION,
)


class CVTailoringSession(Base):
    """One source-revision-bound derivative tailoring workspace."""

    __tablename__ = "cv_tailoring_sessions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('generating', 'ready', 'failed', 'deleting')",
            name="state",
        ),
        CheckConstraint(
            "latest_version_number >= 0",
            name="latest_version_non_negative",
        ),
        CheckConstraint(
            "state = 'failed' AND error_code IS NOT NULL "
            "OR state != 'failed' AND error_code IS NULL",
            name="error_coupling",
        ),
        Index(
            "ix_cv_tailoring_sessions__profile_updated",
            "profile_id",
            "updated_at",
        ),
        Index("ix_cv_tailoring_sessions__job_id", "job_id"),
        Index("ix_cv_tailoring_sessions__state", "state"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    profile_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    job_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("job_posts.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    job_label_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    template_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TAILORING_TEMPLATE_VERSION,
        server_default=TAILORING_TEMPLATE_VERSION,
    )
    state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TAILORING_SESSION_STATE_GENERATING,
        server_default=TAILORING_SESSION_STATE_GENERATING,
    )
    latest_version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CVTailoringVersion(Base):
    """One immutable rendered version belonging to a tailoring session."""

    __tablename__ = "cv_tailoring_versions"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "version_number",
            name="uq_cv_tailoring_versions__session_version",
        ),
        UniqueConstraint(
            "session_id",
            "id",
            name="uq_cv_tailoring_versions__session_id_id",
        ),
        ForeignKeyConstraint(
            ["session_id", "parent_version_id"],
            ["cv_tailoring_versions.session_id", "cv_tailoring_versions.id"],
            name="fk_cv_tailoring_versions__session_parent",
            ondelete="CASCADE",
        ),
        CheckConstraint("version_number > 0", name="version_positive"),
        CheckConstraint(
            "created_by IN ('ai', 'user')",
            name="created_by",
        ),
        CheckConstraint("page_count > 0", name="page_count_positive"),
        CheckConstraint(
            "version_number = 1 AND parent_version_id IS NULL "
            "OR version_number > 1 AND parent_version_id IS NOT NULL",
            name="parent_coupling",
        ),
        Index(
            "ix_cv_tailoring_versions__session_created",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("cv_tailoring_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_revision_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    tex_relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    tex_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


__all__ = ["CVTailoringSession", "CVTailoringVersion"]
