"""Message insert/list repository for the singleton conversation.

Persists only ``user | assistant | system`` roles for ``conversation='main'``.
Never persists provider ``tool`` roles. History order is ``(created_at, id)``.
Pagination uses the composite index
``(conversation_id, created_at, id)`` with newest-first ``limit`` fetches.
Callers own the async session and commit; this module never commits.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import (
    CHAT_MESSAGE_ROLES,
    CONVERSATION_ID,
    ChatMessage,
)


class ChatMessageRepositoryError(Exception):
    """Base error for message repository invariant violations."""


class InvalidMessageRoleError(ChatMessageRepositoryError):
    """Raised when a role is not one of the durable message roles."""


async def insert_message(
    session: AsyncSession,
    *,
    role: str,
    content: str,
    structured_payload: dict[str, Any] | None = None,
    source_attachment_id: str | None = None,
    redacted_at: datetime | None = None,
) -> ChatMessage:
    """Insert one message into the singleton conversation.

    Always sets ``conversation_id`` to :data:`CONVERSATION_ID`. Rejects the
    provider tool role and any other non-durable role before flush. Optional
    *source_attachment_id* / *redacted_at* expose CV ownership fields without
    lifecycle logic. Does not finalize the caller's unit of work.
    """
    if role not in CHAT_MESSAGE_ROLES:
        raise InvalidMessageRoleError(
            f"role must be one of {sorted(CHAT_MESSAGE_ROLES)}, got {role!r}"
        )
    if content == "" and structured_payload is None:
        raise ChatMessageRepositoryError(
            "message requires non-empty content or structured_payload"
        )
    if source_attachment_id is not None and (
        not isinstance(source_attachment_id, str)
        or source_attachment_id.strip() == ""
    ):
        raise ChatMessageRepositoryError(
            "source_attachment_id must be a non-empty string when set"
        )

    # Omit structured_payload when absent so the JSON column stays SQL NULL
    # (SQLAlchemy JSON maps Python None to JSON null by default).
    kwargs: dict[str, Any] = {
        "conversation_id": CONVERSATION_ID,
        "role": role,
        "content": content,
    }
    if structured_payload is not None:
        kwargs["structured_payload"] = structured_payload
    if source_attachment_id is not None:
        kwargs["source_attachment_id"] = source_attachment_id
    if redacted_at is not None:
        kwargs["redacted_at"] = redacted_at
    message = ChatMessage(**kwargs)
    session.add(message)
    await session.flush()
    return message


async def list_messages(session: AsyncSession) -> list[ChatMessage]:
    """Return all main-conversation messages ordered by ``(created_at, id)``.

    Only rows with ``conversation_id == 'main'`` are returned. Ordering is
    ascending on ``created_at`` then ``id`` for deterministic history.
    """
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == CONVERSATION_ID)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_messages_before(
    session: AsyncSession,
    *,
    limit: int,
    before: tuple[datetime, str] | None = None,
) -> list[ChatMessage]:
    """Return up to *limit* main messages newer-first for history pagination.

    When *before* is ``(created_at, id)``, only rows lexicographically earlier
    than that pair are included. Ordering is ``created_at DESC, id DESC`` so
    the caller can request ``limit + 1`` to detect an older page. Does not
    finalize the caller's unit of work.
    """
    if limit < 1:
        raise ChatMessageRepositoryError("limit must be >= 1")

    conditions = [ChatMessage.conversation_id == CONVERSATION_ID]
    if before is not None:
        before_created_at, before_id = before
        # Lexicographic (created_at, id) < cursor pair.
        conditions.append(
            or_(
                ChatMessage.created_at < before_created_at,
                and_(
                    ChatMessage.created_at == before_created_at,
                    ChatMessage.id < before_id,
                ),
            )
        )

    stmt = (
        select(ChatMessage)
        .where(*conditions)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
