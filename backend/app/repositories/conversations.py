"""Profile-scoped conversation persistence and ownership resolution."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.chat import CHAT_MESSAGE_ROLE_USER, ChatMessage, Conversation
from app.db.models.profiles import (
    NEW_CONVERSATION_TITLE,
    PROFILE_STATE_READY,
    Profile,
)
from app.repositories import profiles as profiles_repo
from app.schemas.common import AwareUtcDatetime, StrictModelConfig, UuidStr
from app.services.conversation_titles import derive_conversation_title


class ConversationRepositoryError(Exception):
    """Conversation repository invariant violation."""


class _ConversationCursor(BaseModel):
    model_config = StrictModelConfig

    last_opened_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    id: UuidStr


@dataclass(frozen=True)
class ConversationListPage:
    rows: list[Conversation]
    next_cursor: str | None


@dataclass(frozen=True)
class ConversationOwner:
    conversation_id: str
    profile_id: str
    attachment_id: str


def encode_conversation_cursor(row: Conversation) -> str:
    point = _ConversationCursor(
        last_opened_at=row.last_opened_at,
        updated_at=row.updated_at,
        id=row.id,
    )
    raw = json.dumps(
        point.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
    ).encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_conversation_cursor(cursor: str) -> _ConversationCursor:
    if not isinstance(cursor, str) or not cursor.strip():
        raise ValueError("conversation cursor is malformed")
    text = cursor.strip()
    if any(char in text for char in ("+", "/", " ", "\n", "\r", "\t")):
        raise ValueError("conversation cursor is malformed")
    try:
        raw = base64.b64decode(
            text + "=" * (-len(text) % 4), altchars=b"-_", validate=True
        )
        data = json.loads(raw.decode())
        return _ConversationCursor.model_validate(data)
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        raise ValueError("conversation cursor is malformed") from exc


async def list_for_profile(
    session: AsyncSession,
    *,
    profile_id: str,
    limit: int,
    before: str | None,
) -> ConversationListPage:
    point = decode_conversation_cursor(before) if before is not None else None
    predicates = [Conversation.profile_id == profile_id]
    if point is not None:
        predicates.append(
            tuple_(
                Conversation.last_opened_at,
                Conversation.updated_at,
                Conversation.id,
            )
            < tuple_(
                literal(point.last_opened_at),
                literal(point.updated_at),
                literal(point.id),
            )
        )
    result = await session.execute(
        select(Conversation)
        .where(*predicates)
        .order_by(
            Conversation.last_opened_at.desc(),
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .limit(limit + 1)
    )
    rows = list(result.scalars().all())
    visible = rows[:limit]
    next_cursor = (
        encode_conversation_cursor(visible[-1]) if len(rows) > limit else None
    )
    return ConversationListPage(rows=visible, next_cursor=next_cursor)


async def get_owned(
    session: AsyncSession, *, conversation_id: str
) -> Conversation | None:
    return await session.get(Conversation, conversation_id)


async def resolve_owner(
    session: AsyncSession, conversation_id: str
) -> ConversationOwner | None:
    result = await session.execute(
        select(Conversation.id, Conversation.profile_id, Profile.attachment_id)
        .join(Profile, Conversation.profile_id == Profile.id)
        .where(Conversation.id == conversation_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    return ConversationOwner(
        conversation_id=row.id,
        profile_id=row.profile_id,
        attachment_id=row.attachment_id,
    )


async def create_for_profile(
    session: AsyncSession,
    *,
    profile_id: str,
    title: str = NEW_CONVERSATION_TITLE,
) -> Conversation:
    profile = await profiles_repo.get_profile(session, profile_id)
    if profile is None or profile.state != PROFILE_STATE_READY:
        raise ConversationRepositoryError("profile is not ready")
    now = utc_now()
    row = Conversation(
        id=new_uuid(),
        profile_id=profile_id,
        title=title,
        created_at=now,
        updated_at=now,
        last_opened_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def select_for_profile(
    session: AsyncSession,
    *,
    profile_id: str,
    conversation_id: str,
    now: datetime,
) -> Conversation:
    row = await session.get(Conversation, conversation_id)
    if row is None or row.profile_id != profile_id:
        raise ConversationRepositoryError("conversation profile mismatch")
    row.last_opened_at = now
    row.updated_at = now
    await session.flush()
    return row


async def most_recent_for_profile(
    session: AsyncSession, *, profile_id: str
) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.profile_id == profile_id)
        .order_by(
            Conversation.last_opened_at.desc(),
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_title_from_first_user_message(
    session: AsyncSession, *, conversation_id: str, message: str
) -> Conversation:
    row = await session.get(Conversation, conversation_id)
    if row is None:
        raise ConversationRepositoryError("conversation not found")
    prior = int(
        (
            await session.execute(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.role == CHAT_MESSAGE_ROLE_USER,
                    func.trim(ChatMessage.content) != "",
                )
            )
        ).scalar_one()
    )
    if row.title == NEW_CONVERSATION_TITLE and prior == 0:
        row.title = derive_conversation_title(message)
        row.updated_at = utc_now()
        await session.flush()
    return row
