"""Attachment metadata only — uploaded PDF bytes live on the filesystem."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid
from app.db.enums import AttachmentState


class Attachment(Base, TimestampMixin):
    """Staged and active CV file metadata (no content blobs)."""

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "state IN ('staged', 'active')",
            name="attachment_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)
    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Service-generated path under FILES_DIR; never user-supplied as authority.
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AttachmentState.STAGED.value,
    )
