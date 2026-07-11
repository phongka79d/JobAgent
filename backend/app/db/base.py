"""SQLAlchemy declarative base, shared mixins, and identity helpers.

Application models register on ``Base.metadata``. LangGraph checkpoint tables
are intentionally excluded; the checkpointer owns those later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable naming for future Alembic autogenerate (02B).
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Documented singleton primary-key value for single-row tables.
SINGLETON_PK: int = 1


class UTCDateTime(TypeDecorator[datetime]):
    """Store and load timezone-aware UTC datetimes.

    SQLite may return naive datetimes; values are normalized to UTC on load.
    Naive values are rejected on bind so callers cannot accidentally persist
    local-wall-clock timestamps without an explicit timezone.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware UTC")
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utc_now() -> datetime:
    """Return the current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def new_uuid() -> UUID:
    """Generate a new UUID4 primary key."""
    return uuid4()


class Base(DeclarativeBase):
    """Shared declarative base for all application tables."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Created/updated UTC timestamps shared by application tables."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
