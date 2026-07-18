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

from sqlalchemy import and_, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.chat import (
    CHAT_MESSAGE_ROLES,
    CONVERSATION_ID,
    ChatMessage,
)

# Locale-neutral chat marker after CV deletion (Master §6.2 chat_messages).
CV_DELETED_MARKER: str = "[CV deleted]"


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


async def get_by_id(
    session: AsyncSession,
    message_id: str,
) -> ChatMessage | None:
    """Return the chat message with primary key *message_id*, or ``None``.

    Does not finalize the caller's unit of work.
    """
    if not isinstance(message_id, str) or message_id.strip() == "":
        return None
    return await session.get(ChatMessage, message_id.strip())


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


async def list_by_source_attachment_id(
    session: AsyncSession,
    attachment_id: str,
) -> list[ChatMessage]:
    """Return main messages with explicit ``source_attachment_id`` ownership.

    Does not finalize the caller's unit of work.
    """
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise ChatMessageRepositoryError(
            "attachment_id must be a non-empty string"
        )
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == CONVERSATION_ID,
            ChatMessage.source_attachment_id == attachment_id.strip(),
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_with_structured_payload(
    session: AsyncSession,
) -> list[ChatMessage]:
    """Return main messages that still carry a structured payload.

    Used by the deletion ownership resolver for historical shapes when
    ``source_attachment_id`` was not stamped. Does not finalize the unit of work.
    """
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == CONVERSATION_ID,
            ChatMessage.structured_payload.is_not(None),
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def redact_for_cv_deletion(
    session: AsyncSession,
    message_id: str,
    *,
    redacted_at: datetime | None = None,
) -> ChatMessage:
    """Replace CV-linked content with the fixed marker and clear ownership.

    Sets ``content`` to ``[CV deleted]``, clears ``structured_payload`` and
    ``source_attachment_id`` with SQL NULL, and stamps ``redacted_at``.
    Idempotent when already redacted with the marker. Does not finalize the
    caller's unit of work.
    """
    row = await session.get(ChatMessage, message_id)
    if row is None:
        raise ChatMessageRepositoryError(f"message {message_id!r} not found")
    now = redacted_at if redacted_at is not None else utc_now()
    row.content = CV_DELETED_MARKER
    row.structured_payload = null()
    row.source_attachment_id = None
    row.redacted_at = now
    row.updated_at = now
    await session.flush()
    return row
