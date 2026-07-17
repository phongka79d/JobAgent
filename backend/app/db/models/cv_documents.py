"""SQLAlchemy contracts for approved and draft per-CV document rows.

``cv_documents`` holds the latest approved structured CV extraction;
``cv_document_drafts`` holds a pending reprocess/extraction draft.
JSON shape is validated by the Pydantic service boundary, not this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.time import utc_now
from app.db.base import Base


class CVDocument(Base):
    """Latest approved per-CV document and profile/outline projections."""

    __tablename__ = "cv_documents"

    attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    outline_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    extraction_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
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


class CVDocumentDraft(Base):
    """Pending per-CV document draft awaiting approval or correction."""

    __tablename__ = "cv_document_drafts"

    attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    outline_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    extraction_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
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
