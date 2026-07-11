"""Canonical job post records with independent status dimensions.

``processing_status``, ``jd_quality``, ``graph_sync_status``, and
``record_status`` are separate columns with independent allowed values.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, new_uuid
from app.db.enums import (
    GraphSyncStatus,
    JobSourceType,
    ProcessingStatus,
    RecordStatus,
)


class JobPost(Base, TimestampMixin):
    """Canonical JD record or ignored-duplicate row (raw inputs retained)."""

    __tablename__ = "job_posts"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('url', 'text')",
            name="job_source_type",
        ),
        CheckConstraint(
            "processing_status IN "
            "('received', 'processing', 'processed', 'failed')",
            name="processing_status",
        ),
        CheckConstraint(
            "jd_quality IS NULL OR jd_quality IN "
            "('full', 'partial', 'unscorable')",
            name="jd_quality",
        ),
        CheckConstraint(
            "graph_sync_status IN "
            "('not_required', 'pending', 'synced', 'failed')",
            name="graph_sync_status",
        ),
        CheckConstraint(
            "record_status IN ('active', 'ignored_duplicate')",
            name="record_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)

    source_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=JobSourceType.TEXT.value,
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    # Present only when company+title+location are sufficient (Plan 5 / master).
    normalized_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        index=True,
    )

    # Extracted structured fields as opaque JSON; Pydantic validation later.
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    quality_reasons: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    score_cache: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    processing_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProcessingStatus.RECEIVED.value,
        index=True,
    )
    jd_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    graph_sync_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=GraphSyncStatus.NOT_REQUIRED.value,
        index=True,
    )
    record_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RecordStatus.ACTIVE.value,
        index=True,
    )

    duplicate_of_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
