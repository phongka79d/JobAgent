"""SQLAlchemy contract for the ``attachments`` application table.

Static column, CHECK, unique, and partial-index invariants only. JSON shape is
not applicable; allowed state transitions, MAX_PDF_PAGES, cross-row profile
coupling, and filesystem operations belong to later services/storage.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, column
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base

# Single production owners for attachment state/MIME invariants.
ATTACHMENT_STATE_STAGED = "staged"
ATTACHMENT_STATE_ACTIVE = "active"
ATTACHMENT_STATE_ARCHIVED = "archived"
ATTACHMENT_STATE_FAILED = "failed"
ATTACHMENT_STATE_DELETING = "deleting"
ATTACHMENT_STATES: frozenset[str] = frozenset(
    {
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_FAILED,
        ATTACHMENT_STATE_DELETING,
    }
)
ATTACHMENT_MIME_TYPE_PDF = "application/pdf"
ATTACHMENT_STATE_DEFAULT = ATTACHMENT_STATE_STAGED


class Attachment(Base):
    """One uploaded PDF attachment metadata row (lifecycle states incl. deleting)."""

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            column("mime_type") == ATTACHMENT_MIME_TYPE_PDF,
            name="mime_type",
        ),
        CheckConstraint(
            "size_bytes > 0",
            name="size_bytes_positive",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="page_count_positive",
        ),
        CheckConstraint(
            column("state").in_(
                (
                    ATTACHMENT_STATE_STAGED,
                    ATTACHMENT_STATE_ACTIVE,
                    ATTACHMENT_STATE_ARCHIVED,
                    ATTACHMENT_STATE_FAILED,
                    ATTACHMENT_STATE_DELETING,
                )
            ),
            name="state",
        ),
        CheckConstraint(
            (
                (column("state") == ATTACHMENT_STATE_FAILED)
                & column("failure_code").is_not(None)
            )
            | (
                (column("state") != ATTACHMENT_STATE_FAILED)
                & column("failure_code").is_(None)
            ),
            name="failure_coupling",
        ),
        CheckConstraint(
            (column("state") != ATTACHMENT_STATE_ACTIVE)
            | column("page_count").is_not(None),
            name="active_requires_page_count",
        ),
        Index(
            "uq_attachments__single_active",
            "state",
            unique=True,
            sqlite_where=(column("state") == ATTACHMENT_STATE_ACTIVE),
        ),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=new_uuid,
    )
    file_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=ATTACHMENT_STATE_DEFAULT,
        server_default=ATTACHMENT_STATE_DEFAULT,
    )
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
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
