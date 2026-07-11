"""Durable memory facts not already represented by profile/preferences."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, new_uuid


class MemoryFact(Base, TimestampMixin):
    """Key/value job-related facts with opaque JSON values.

    UUID primary key satisfies the non-singleton identity rule; ``key`` is the
    durable business identity (required, unique, indexed).
    """

    __tablename__ = "memory_facts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        unique=True,
        index=True,
    )
    value_json: Mapped[dict[str, Any] | list[Any] | str | int | float | bool | None] = (
        mapped_column(JSON, nullable=False)
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False)
