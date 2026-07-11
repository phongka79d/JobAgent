"""Durable SQLite-to-Neo4j synchronization outbox.

Payloads store SQLite IDs and canonical data only — never filesystem paths,
API keys, or raw document bytes. Processing semantics belong to later plans.

Logical operation identity is ``(operation, entity_id)``: unique so replays
cannot create a second durable row for the same graph operation.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, new_uuid
from app.db.enums import OutboxStatus


class GraphSyncOutbox(Base, TimestampMixin):
    """Transactional outbox row for graph-derived data changes."""

    __tablename__ = "graph_sync_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'synced', 'failed')",
            name="outbox_status",
        ),
        CheckConstraint("attempts >= 0", name="outbox_attempts_non_negative"),
        # Stable replay-safe identity: one logical operation per entity.
        UniqueConstraint(
            "operation",
            "entity_id",
            name="uq_graph_sync_outbox_operation_entity_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)
    # Stable operation identity for replay-safe processing (e.g. upsert_job).
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=OutboxStatus.PENDING.value,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
