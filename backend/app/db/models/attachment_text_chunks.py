"""SQLAlchemy contract for ``attachment_text_chunks``.

One immutable parsed-text row per ``(attachment_id, ordinal)``: the exact
canonical segments sent to structured profile extraction. No provider
metadata, PDF bytes, or mutable update path beyond replace-on-write.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base

# List/detail preview bound (Plan 8 Persistence And Extraction).
CHUNK_PREVIEW_MAX_CHARS: int = 240


class AttachmentTextChunk(Base):
    """One ordered parsed-CV text segment linked to an attachment."""

    __tablename__ = "attachment_text_chunks"
    __table_args__ = (
        UniqueConstraint(
            "attachment_id",
            "ordinal",
            name="uq_attachment_text_chunks__attachment_ordinal",
        ),
        CheckConstraint(
            "ordinal >= 0",
            name="ordinal_non_negative",
        ),
        CheckConstraint(
            "char_count > 0",
            name="char_count_positive",
        ),
        CheckConstraint(
            "token_estimate >= 0",
            name="token_estimate_non_negative",
        ),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default=new_uuid,
    )
    attachment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("attachments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    preview: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
