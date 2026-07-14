"""SQLAlchemy contract for the ``job_posts`` application table.

Static column, CHECK, unique, and index invariants only. Configuration-
dependent embedding length/finiteness, transitions, deduplication services,
extraction, provider calls, graph sync, and scoring belong to later phases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, column
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base

# Single production owners for job source/status/quality invariants.
JOB_SOURCE_TYPE_URL = "url"
JOB_SOURCE_TYPE_TEXT = "text"
JOB_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        JOB_SOURCE_TYPE_URL,
        JOB_SOURCE_TYPE_TEXT,
    }
)

JOB_PROCESSING_STATUS_RECEIVED = "received"
JOB_PROCESSING_STATUS_PROCESSING = "processing"
JOB_PROCESSING_STATUS_PROCESSED = "processed"
JOB_PROCESSING_STATUS_FAILED = "failed"
JOB_PROCESSING_STATUSES: frozenset[str] = frozenset(
    {
        JOB_PROCESSING_STATUS_RECEIVED,
        JOB_PROCESSING_STATUS_PROCESSING,
        JOB_PROCESSING_STATUS_PROCESSED,
        JOB_PROCESSING_STATUS_FAILED,
    }
)
JOB_PROCESSING_STATUS_DEFAULT = JOB_PROCESSING_STATUS_RECEIVED

JOB_JD_QUALITY_FULL = "full"
JOB_JD_QUALITY_PARTIAL = "partial"
JOB_JD_QUALITY_UNSCORABLE = "unscorable"
JOB_JD_QUALITIES: frozenset[str] = frozenset(
    {
        JOB_JD_QUALITY_FULL,
        JOB_JD_QUALITY_PARTIAL,
        JOB_JD_QUALITY_UNSCORABLE,
    }
)

# Compact list_compact query bounds (repository + tool validation share these).
JOB_COMPACT_QUERY_LIMIT_MIN = 1
JOB_COMPACT_QUERY_LIMIT_MAX = 50

_SCORABLE_PROCESSED = (
    (column("processing_status") == JOB_PROCESSING_STATUS_PROCESSED)
    & column("jd_quality").in_((JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL))
)
_EMBEDDING_ALL_PRESENT = (
    column("embedding_json").is_not(None)
    & column("embedding_model").is_not(None)
    & column("embedding_dimensions").is_not(None)
)
_EMBEDDING_ALL_ABSENT = (
    column("embedding_json").is_(None)
    & column("embedding_model").is_(None)
    & column("embedding_dimensions").is_(None)
)


class JobPost(Base):
    """One job-post row: URL/text source through processed or failed terminal state."""

    __tablename__ = "job_posts"
    __table_args__ = (
        CheckConstraint(
            column("source_type").in_(
                (JOB_SOURCE_TYPE_URL, JOB_SOURCE_TYPE_TEXT),
            ),
            name="source_type",
        ),
        CheckConstraint(
            (
                (column("source_type") == JOB_SOURCE_TYPE_URL)
                & column("source_url").is_not(None)
            )
            | (
                (column("source_type") == JOB_SOURCE_TYPE_TEXT)
                & column("raw_content").is_not(None)
                & column("source_url").is_(None)
            ),
            name="url_text_coupling",
        ),
        CheckConstraint(
            (
                column("raw_content").is_(None)
                & column("raw_content_hash").is_(None)
            )
            | (
                column("raw_content").is_not(None)
                & column("raw_content_hash").is_not(None)
            ),
            name="raw_content_hash_coupling",
        ),
        CheckConstraint(
            column("processing_status").in_(
                (
                    JOB_PROCESSING_STATUS_RECEIVED,
                    JOB_PROCESSING_STATUS_PROCESSING,
                    JOB_PROCESSING_STATUS_PROCESSED,
                    JOB_PROCESSING_STATUS_FAILED,
                )
            ),
            name="processing_status",
        ),
        CheckConstraint(
            column("jd_quality").is_(None)
            | column("jd_quality").in_(
                (
                    JOB_JD_QUALITY_FULL,
                    JOB_JD_QUALITY_PARTIAL,
                    JOB_JD_QUALITY_UNSCORABLE,
                )
            ),
            name="jd_quality",
        ),
        CheckConstraint(
            (column("processing_status") != JOB_PROCESSING_STATUS_PROCESSED)
            | (
                column("extraction_json").is_not(None)
                & column("jd_quality").is_not(None)
            ),
            name="processed_requires_extraction_quality",
        ),
        CheckConstraint(
            (
                (column("processing_status") == JOB_PROCESSING_STATUS_FAILED)
                & column("failure_code").is_not(None)
            )
            | (
                (column("processing_status") != JOB_PROCESSING_STATUS_FAILED)
                & column("failure_code").is_(None)
            ),
            name="failure_coupling",
        ),
        CheckConstraint(
            _EMBEDDING_ALL_ABSENT | _EMBEDDING_ALL_PRESENT,
            name="embedding_all_or_none",
        ),
        CheckConstraint(
            column("embedding_dimensions").is_(None)
            | (column("embedding_dimensions") > 0),
            name="embedding_dimensions_positive",
        ),
        CheckConstraint(
            (_SCORABLE_PROCESSED & _EMBEDDING_ALL_PRESENT)
            | (~_SCORABLE_PROCESSED & _EMBEDDING_ALL_ABSENT),
            name="processed_scorable_embedding",
        ),
        Index(
            "ix_job_posts__processing_quality",
            "processing_status",
            "jd_quality",
        ),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=new_uuid,
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        unique=True,
    )
    extraction_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    processing_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=JOB_PROCESSING_STATUS_DEFAULT,
        server_default=JOB_PROCESSING_STATUS_DEFAULT,
    )
    jd_quality: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
