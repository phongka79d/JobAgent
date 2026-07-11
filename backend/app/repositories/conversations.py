"""Singleton conversation and bounded message-history repository.

Caller owns the ``AsyncSession`` transaction: methods flush only and never
commit or roll back. Exactly one application conversation row exists
(``SINGLETON_PK``). Message history is durable application state; Agent
runtime context must use the bounded recent window, never full history.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import SINGLETON_PK, utc_now
from app.db.enums import MessageRole
from app.db.models.conversation import ChatMessage, Conversation

# Hard ceilings so repository callers cannot load unbounded Agent context or
# accept pathological payloads. History reads remain ordered and optional-
# limited; Agent context always requires an explicit positive bound.
_MAX_HISTORY_LIMIT = 500
_MAX_CONTEXT_LIMIT = 100
_MAX_CONTENT_LEN = 32_768
_MAX_PAYLOAD_DEPTH = 6
_MAX_PAYLOAD_NODES = 200
_MAX_STRING_LEN = 2048
_MAX_COLLECTION_LEN = 100

_ALLOWED_ROLES: frozenset[str] = frozenset(role.value for role in MessageRole)

# Structured card/payload keys must not smuggle secrets, filesystem paths, or
# raw document bodies into durable message rows.
_PROHIBITED_KEY_TOKENS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "authorization",
        "credential",
        "credentials",
        "bearer",
        "auth",
        "connection_string",
        "neo4j_password",
        "shopaikey",
        "storage_path",
        "file_path",
        "filepath",
        "filesystem_path",
        "absolute_path",
        "relative_path",
        "path",
        "attachment",
        "filename",
        "file_name",
        "directory",
        "folder",
        "raw_document",
        "raw_content",
        "raw_text",
        "full_text",
        "document",
        "document_bytes",
        "pdf_bytes",
        "file_bytes",
        "content_bytes",
        "blob",
        "binary",
        "pdf",
        "cv",
        "resume",
        "job_description",
        "jd_text",
        "cv_text",
        "transcript",
        "transcription",
    }
)


class ConversationRepositoryError(Exception):
    """Conversation/message operation failed without disclosing payload values."""


class ConversationNotFoundError(ConversationRepositoryError):
    """Singleton conversation row is missing when required."""


class ConversationDuplicateError(ConversationRepositoryError):
    """Reserved for uniqueness conflicts that cannot be resolved in-repository.

    ``ensure_singleton`` is conflict-safe and does not raise this error; it
    remains exported for callers and message-path integrity mapping stability.
    """


class ConversationPayloadError(ConversationRepositoryError):
    """Structured payload failed closed validation."""


class ConversationMessageError(ConversationRepositoryError):
    """Message role, content, or identity failed validation."""


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _key_is_prohibited(key: str) -> bool:
    normalized = _normalize_key(key)
    if not normalized:
        return True
    if normalized in _PROHIBITED_KEY_TOKENS:
        return True
    return any(token in normalized for token in _PROHIBITED_KEY_TOKENS)


def _string_looks_like_path(value: str) -> bool:
    if not value:
        return False
    stripped = value.strip().strip("\"'")
    lower = stripped.lower()
    if "file:" in lower:
        return True
    if len(stripped) >= 2 and stripped[1] == ":" and stripped[0].isalpha():
        return True
    if stripped.startswith("\\\\") or stripped.startswith("//"):
        return True
    if stripped.startswith("/"):
        return True
    if stripped.startswith("./") or stripped.startswith("../"):
        return True
    if "\\" in stripped:
        return True
    return False


def _string_looks_like_secret_or_document(value: str) -> bool:
    if len(value) > _MAX_STRING_LEN:
        return True
    stripped = value.strip().strip("\"'")
    upper = value.upper()
    if stripped.lower().startswith(("basic ", "bearer ", "digest ", "token ")):
        return True
    if "BEGIN PRIVATE KEY" in upper or "BEGIN RSA PRIVATE KEY" in upper:
        return True
    return False


def validate_structured_payload(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate optional structured card/payload data for a message row.

    ``None`` is allowed (no card). Empty mappings are allowed. Nested JSON-
    serializable structures are accepted with depth/size ceilings. Prohibited
    keys and path/secret/document categories fail closed without logging values.
    """
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ConversationPayloadError("payload must be a mapping")

    nodes = 0

    def walk(value: Any, *, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_PAYLOAD_NODES:
            raise ConversationPayloadError("payload too large")
        if depth > _MAX_PAYLOAD_DEPTH:
            raise ConversationPayloadError("payload too deep")

        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):  # noqa: PLR0124
                raise ConversationPayloadError("invalid numeric value")
            return value
        if isinstance(value, str):
            if _string_looks_like_path(value):
                raise ConversationPayloadError("filesystem path not permitted")
            if _string_looks_like_secret_or_document(value):
                raise ConversationPayloadError("prohibited content category")
            return value
        if isinstance(value, Mapping):
            if len(value) > _MAX_COLLECTION_LEN:
                raise ConversationPayloadError("payload too large")
            out: dict[str, Any] = {}
            for raw_key, raw_val in value.items():
                if not isinstance(raw_key, str):
                    raise ConversationPayloadError("payload keys must be strings")
                if _key_is_prohibited(raw_key):
                    raise ConversationPayloadError("prohibited payload key")
                out[raw_key] = walk(raw_val, depth=depth + 1)
            return out
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            if len(value) > _MAX_COLLECTION_LEN:
                raise ConversationPayloadError("payload too large")
            return [walk(item, depth=depth + 1) for item in value]
        if isinstance(value, (bytes, bytearray)):
            raise ConversationPayloadError("raw document bytes not permitted")
        raise ConversationPayloadError("unsupported payload value type")

    validated = walk(dict(payload), depth=0)
    if not isinstance(validated, dict):
        raise ConversationPayloadError("payload must be a mapping")
    return validated


def _validate_role(role: str | MessageRole) -> str:
    if isinstance(role, MessageRole):
        return role.value
    if not isinstance(role, str):
        raise ConversationMessageError("invalid role")
    normalized = role.strip().lower()
    if normalized not in _ALLOWED_ROLES:
        raise ConversationMessageError("invalid role")
    return normalized


def _validate_content(content: str) -> str:
    if not isinstance(content, str):
        raise ConversationMessageError("invalid content")
    # Preserve intentional internal whitespace; reject blank-only content.
    if not content.strip():
        raise ConversationMessageError("invalid content")
    if len(content) > _MAX_CONTENT_LEN:
        raise ConversationMessageError("content too large")
    return content


def _validate_positive_limit(limit: int, *, ceiling: int, name: str) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ConversationRepositoryError(f"invalid {name}")
    if limit < 1 or limit > ceiling:
        raise ConversationRepositoryError(f"invalid {name}")
    return limit


class ConversationRepository:
    """Narrow conversation and message operations on a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_singleton(self) -> Conversation | None:
        """Load the application conversation row, or None if not yet created."""
        return await self._session.get(Conversation, SINGLETON_PK)

    async def ensure_singleton(self) -> Conversation:
        """Return the sole application conversation, creating it if missing.

        Idempotent and conflict-safe: repeated or concurrent callers each
        receive the same ``SINGLETON_PK`` row without requiring a caller
        retry. First-create uses SQLite ``INSERT … ON CONFLICT DO NOTHING``
        then select so a uniqueness race never poisons the session. Never
        commits or rolls back (caller owns the transaction boundary).
        """
        existing = await self.get_singleton()
        if existing is not None:
            return existing

        # Core insert applies timestamps explicitly (Python column defaults are
        # ORM-instance only). ON CONFLICT avoids IntegrityError on the race.
        now = utc_now()
        stmt = (
            sqlite_insert(Conversation)
            .values(id=SINGLETON_PK, created_at=now, updated_at=now)
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

        row = await self.get_singleton()
        if row is None:
            # Should not occur after a successful conflict-safe ensure on a
            # healthy schema; surface without leaving a partial second row.
            raise ConversationNotFoundError(
                "conversation singleton missing after ensure"
            )
        return row

    async def get_message(self, message_id: UUID) -> ChatMessage | None:
        """Load one chat message by primary key, or None."""
        return await self._session.get(ChatMessage, message_id)

    async def append_message(
        self,
        *,
        role: str | MessageRole,
        content: str,
        structured_payload: Mapping[str, Any] | None = None,
        conversation_id: int | None = None,
    ) -> ChatMessage:
        """Append one validated message to the singleton conversation.

        Does not commit. Ensures the singleton conversation exists first.
        Role and structured payload are validated before flush so invalid
        writes never become durable. On integrity failure after flush the
        session is left for the caller to roll back (no partial durable row).
        """
        safe_role = _validate_role(role)
        safe_content = _validate_content(content)
        safe_payload = validate_structured_payload(structured_payload)

        conversation = await self.ensure_singleton()
        if conversation_id is not None and conversation_id != conversation.id:
            raise ConversationMessageError("invalid conversation_id")

        row = ChatMessage(
            conversation_id=conversation.id,
            role=safe_role,
            content=safe_content,
            structured_payload=safe_payload,
        )
        self._session.add(row)
        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise ConversationRepositoryError("message write failed") from None
        return row

    async def list_history(self, *, limit: int | None = None) -> list[ChatMessage]:
        """Return application history in stable chronological order.

        Order is ``created_at ASC, id ASC``. When ``limit`` is set it must be
        in ``1.._MAX_HISTORY_LIMIT`` and returns the oldest ``limit`` messages
        in that order. Callers needing the Agent prompt window must use
        ``list_recent_for_context`` instead of loading full history.
        """
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == SINGLETON_PK)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        if limit is not None:
            safe_limit = _validate_positive_limit(
                limit, ceiling=_MAX_HISTORY_LIMIT, name="limit"
            )
            stmt = stmt.limit(safe_limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_for_context(self, *, limit: int) -> list[ChatMessage]:
        """Return a bounded recent window for Agent runtime context.

        Requires an explicit positive ``limit`` (``1.._MAX_CONTEXT_LIMIT``).
        Selects the newest messages by ``created_at DESC, id DESC``, then
        returns them in chronological order (``created_at ASC, id ASC``) so
        the Agent path never receives unbounded full history.
        """
        safe_limit = _validate_positive_limit(
            limit, ceiling=_MAX_CONTEXT_LIMIT, name="limit"
        )
        # Newest-first selection, then reverse for stable chronological context.
        newest_first = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == SINGLETON_PK)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(safe_limit)
        )
        result = await self._session.execute(newest_first)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows
