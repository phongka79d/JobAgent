"""Transactional, replay-safe graph sync outbox repository.

Caller owns the ``AsyncSession`` transaction: enqueue and state transitions
flush only and never commit, roll back, or start background work. Continuous
polling, worker services, and domain-specific Candidate/Job payload builders
are intentionally out of scope.

Logical identity is ``(operation, entity_id)``. Replaying the same identity
returns the existing durable row without resetting attempts or terminal state.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OutboxStatus
from app.db.models.outbox import GraphSyncOutbox

# Hard ceiling on a single claim batch (lifecycle callers still pass limit).
_MAX_CLAIM_LIMIT = 500
_MAX_OPERATION_LEN = 64
_MAX_ENTITY_ID_LEN = 64
_MAX_ERROR_LEN = 1024
_MAX_PAYLOAD_DEPTH = 6
_MAX_PAYLOAD_NODES = 200
_MAX_STRING_LEN = 2048
_MAX_COLLECTION_LEN = 100

_OPERATION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_ENTITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")

# Normalized key tokens / substrings that must never appear in payloads.
# Category-oriented: substring match catches alternate spellings
# (document_text, attachment_ref, file_path, auth_token, ...) without enumerating
# every key name.
_PROHIBITED_KEY_TOKENS: frozenset[str] = frozenset(
    {
        # Credentials / auth material
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
        "auth_header",
        "auth",
        "connection_string",
        "neo4j_password",
        "shopaikey",
        # Filesystem / service paths and attachment locations
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
        # Raw document / content dumps (any spelling of the category)
        "raw_document",
        "raw_content",
        "raw_text",
        "full_text",
        "document",
        "document_bytes",
        "pdf_bytes",
        "file_bytes",
        "content_bytes",
        "content",
        "body",
        "blob",
        "binary",
        "pdf",
        "cv",
        "resume",
        "job_description",
        "jd_text",
        "cv_text",
        # Alternate raw-document categories (transcripts, notes dumps, etc.)
        "transcript",
        "transcription",
    }
)

_PATH_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
# Service-relative attachment grammar used by attachment storage (active|staged/<id>).
_SERVICE_REL_PATH_RE = re.compile(
    r"^(?:active|staged)/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
# Multi-segment relative paths (forward slash), excluding URI schemes.
_RELATIVE_PATH_RE = re.compile(r"^(?![A-Za-z][A-Za-z0-9+.-]*://)[^/\s]+(?:/[^/\s]+)+$")
# HTTP auth schemes and similar credential-bearing value shapes.
_AUTH_SCHEME_RE = re.compile(
    r"^(?:Basic|Bearer|Digest|Token|Negotiate|NTLM)\s+\S+",
    re.IGNORECASE,
)
# Credential-bearing URI userinfo anywhere in the value (scheme://user:password@host...).
# Unanchored so jdbc:/dsn-prefixed and mid-string connection URIs also fail closed.
_URI_USERINFO_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s?#\"']*:[^/\s?#\"']*@",
)
# Credential label assignment under ordinary keys: Password: x, password = y,
# X-Api-Key = z, api_key=v. Case-insensitive labels; optional whitespace around
# ':' or '='. Also matches after a leading quote or prefix on the same value.
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?:^|[\s\"'=])(?:password|passwd|secret|token|api[_-]?key|x[_-]?api[_-]?key|"
    r"authorization|access[_-]?key|private[_-]?key|credential|credentials|"
    r"auth[_-]?token|session[_-]?token|auth)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
# PEM / key-material body markers (not label assignments; those use the regex).
_SECRET_VALUE_MARKERS: tuple[str, ...] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)


class GraphOutboxRepositoryError(Exception):
    """Outbox operation failed without disclosing payload or secret values."""


class GraphOutboxNotFoundError(GraphOutboxRepositoryError):
    """No outbox row exists for the requested identity."""


class GraphOutboxStateError(GraphOutboxRepositoryError):
    """Requested status transition is not allowed for the current row state."""


class GraphOutboxDuplicateError(GraphOutboxRepositoryError):
    """Uniqueness conflict on (operation, entity_id); caller must roll back."""


class GraphOutboxPayloadError(GraphOutboxRepositoryError):
    """Payload failed closed validation (prohibited keys or content category)."""


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
    """Detect absolute and relative filesystem/service path shapes.

    Covers drive-letter, UNC, all POSIX absolute forms (root and
    single-component included), ``file:`` filesystem URIs (whole-value or
    embedded), parent-relative, backslash, multi-segment forward-slash
    relative, and attachment service paths (``active/<uuid>``,
    ``staged/<uuid>``). Never logs the value.
    """
    if not value:
        return False
    stripped = value.strip().strip("\"'")
    lower = stripped.lower()
    # Filesystem URI scheme anywhere (file:/, file://, file:///..., embedded).
    if "file:" in lower:
        return True
    if _PATH_DRIVE_RE.match(stripped):
        return True
    if stripped.startswith("\\\\") or stripped.startswith("//"):
        return True
    # Any POSIX absolute path: "/", "/tmp", "/var/log/app", etc.
    if stripped.startswith("/"):
        return True
    if stripped.startswith("./") or stripped.startswith("../"):
        return True
    if "\\" in stripped:
        return True
    # Attachment service-relative grammar (active|staged/<uuid>).
    if _SERVICE_REL_PATH_RE.match(stripped):
        return True
    # Any multi-segment relative path using forward slashes.
    if _RELATIVE_PATH_RE.match(stripped):
        return True
    return False


def _string_looks_like_secret_or_document(value: str) -> bool:
    """Detect credential-bearing and oversized raw-document string values.

    Includes auth schemes, PEM/key material markers, URI userinfo credentials
    (including mid-string / jdbc-prefixed forms), and credential label
    assignments with ':' or '=' (optional whitespace) under ordinary keys.
    Never logs the value.
    """
    if len(value) > _MAX_STRING_LEN:
        return True
    stripped = value.strip().strip("\"'")
    if _AUTH_SCHEME_RE.match(stripped):
        return True
    # search (not match) so userinfo works mid-string and after prefixes.
    if _URI_USERINFO_RE.search(stripped):
        return True
    if _CREDENTIAL_ASSIGNMENT_RE.search(stripped):
        return True
    for marker in _SECRET_VALUE_MARKERS:
        if marker in value:
            return True
    return False


def validate_outbox_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and shallow-copy a structured outbox payload.

    Permits SQLite identifiers and nested canonical structured data only.
    Rejects prohibited keys and content categories. Never logs payload values.
    """
    if not isinstance(payload, Mapping):
        raise GraphOutboxPayloadError("payload must be a mapping")
    if not payload:
        raise GraphOutboxPayloadError("payload must not be empty")

    nodes = 0

    def walk(value: Any, *, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_PAYLOAD_NODES:
            raise GraphOutboxPayloadError("payload too large")
        if depth > _MAX_PAYLOAD_DEPTH:
            raise GraphOutboxPayloadError("payload too deep")

        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):  # noqa: PLR0124
                raise GraphOutboxPayloadError("invalid numeric value")
            return value
        if isinstance(value, str):
            if _string_looks_like_path(value):
                raise GraphOutboxPayloadError("filesystem path not permitted")
            if _string_looks_like_secret_or_document(value):
                raise GraphOutboxPayloadError("prohibited content category")
            return value
        if isinstance(value, Mapping):
            if len(value) > _MAX_COLLECTION_LEN:
                raise GraphOutboxPayloadError("payload too large")
            out: dict[str, Any] = {}
            for raw_key, raw_val in value.items():
                if not isinstance(raw_key, str):
                    raise GraphOutboxPayloadError("payload keys must be strings")
                if _key_is_prohibited(raw_key):
                    raise GraphOutboxPayloadError("prohibited payload key")
                out[raw_key] = walk(raw_val, depth=depth + 1)
            return out
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if len(value) > _MAX_COLLECTION_LEN:
                raise GraphOutboxPayloadError("payload too large")
            return [walk(item, depth=depth + 1) for item in value]
        if isinstance(value, (bytes, bytearray)):
            raise GraphOutboxPayloadError("raw document bytes not permitted")
        raise GraphOutboxPayloadError("unsupported payload value type")

    validated = walk(dict(payload), depth=0)
    if not isinstance(validated, dict):
        raise GraphOutboxPayloadError("payload must be a mapping")
    return validated


def _validate_operation(operation: str) -> str:
    if not isinstance(operation, str) or not _OPERATION_RE.fullmatch(operation):
        raise GraphOutboxRepositoryError("invalid operation")
    if len(operation) > _MAX_OPERATION_LEN:
        raise GraphOutboxRepositoryError("invalid operation")
    return operation


def _validate_entity_id(entity_id: str) -> str:
    if not isinstance(entity_id, str) or not _ENTITY_ID_RE.fullmatch(entity_id):
        raise GraphOutboxRepositoryError("invalid entity_id")
    if len(entity_id) > _MAX_ENTITY_ID_LEN:
        raise GraphOutboxRepositoryError("invalid entity_id")
    return entity_id


def _sanitize_error(message: str | None) -> str | None:
    if message is None:
        return None
    if not isinstance(message, str):
        raise GraphOutboxRepositoryError("invalid error message")
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > _MAX_ERROR_LEN:
        cleaned = cleaned[:_MAX_ERROR_LEN]
    # Avoid retaining path-shaped fragments in error text.
    if _string_looks_like_path(cleaned) or _string_looks_like_secret_or_document(
        cleaned
    ):
        return "sync_failed"
    return cleaned


class GraphOutboxRepository:
    """Narrow graph outbox operations on a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, outbox_id: UUID) -> GraphSyncOutbox | None:
        """Load one outbox row by primary key, or None."""
        return await self._session.get(GraphSyncOutbox, outbox_id)

    async def get_by_identity(
        self,
        operation: str,
        entity_id: str,
    ) -> GraphSyncOutbox | None:
        """Load the durable row for a logical operation identity, or None."""
        operation = _validate_operation(operation)
        entity_id = _validate_entity_id(entity_id)
        result = await self._session.execute(
            select(GraphSyncOutbox).where(
                GraphSyncOutbox.operation == operation,
                GraphSyncOutbox.entity_id == entity_id,
            )
        )
        return result.scalar_one_or_none()

    async def enqueue(
        self,
        *,
        operation: str,
        entity_id: str,
        payload: Mapping[str, Any],
    ) -> GraphSyncOutbox:
        """Insert a pending outbox row in the caller's transaction.

        Does not commit. Replaying the same ``(operation, entity_id)`` returns
        the existing row without mutating attempts, status, payload, or error.
        Concurrent uniqueness conflicts raise ``GraphOutboxDuplicateError``
        after a failed flush; the session remains unusable until the caller
        rolls back.
        """
        operation = _validate_operation(operation)
        entity_id = _validate_entity_id(entity_id)
        safe_payload = validate_outbox_payload(payload)

        existing = await self.get_by_identity(operation, entity_id)
        if existing is not None:
            return existing

        row = GraphSyncOutbox(
            operation=operation,
            entity_id=entity_id,
            payload=safe_payload,
            status=OutboxStatus.PENDING.value,
            attempts=0,
            last_error=None,
        )
        self._session.add(row)
        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise GraphOutboxDuplicateError(
                "duplicate outbox operation identity"
            ) from None
        return row

    async def claim_pending(self, *, limit: int) -> list[GraphSyncOutbox]:
        """Return a bounded, deterministically ordered batch of pending rows.

        Order is ``created_at ASC, id ASC``. Does not mutate rows, commit, or
        start a timer/worker. Callers invoke this only at explicit lifecycle
        points (startup, pre-match, post-transaction processing).
        """
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise GraphOutboxRepositoryError("invalid claim limit")
        if limit < 1 or limit > _MAX_CLAIM_LIMIT:
            raise GraphOutboxRepositoryError("invalid claim limit")

        result = await self._session.execute(
            select(GraphSyncOutbox)
            .where(GraphSyncOutbox.status == OutboxStatus.PENDING.value)
            .order_by(
                GraphSyncOutbox.created_at.asc(),
                GraphSyncOutbox.id.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_synced(self, outbox_id: UUID) -> GraphSyncOutbox:
        """Transition pending or failed work to synced. Does not commit."""
        row = await self.get_by_id(outbox_id)
        if row is None:
            raise GraphOutboxNotFoundError("outbox row not found")
        if row.status == OutboxStatus.SYNCED.value:
            return row
        if row.status not in (
            OutboxStatus.PENDING.value,
            OutboxStatus.FAILED.value,
        ):
            raise GraphOutboxStateError("invalid state transition")
        row.status = OutboxStatus.SYNCED.value
        row.last_error = None
        await self._session.flush()
        return row

    async def mark_failed(
        self,
        outbox_id: UUID,
        *,
        error: str | None = None,
    ) -> GraphSyncOutbox:
        """Record a visible failed attempt. Does not commit.

        Increments ``attempts`` and stores a sanitized short error (or None).
        Leaves durable retryable evidence when Neo4j is unavailable.
        """
        row = await self.get_by_id(outbox_id)
        if row is None:
            raise GraphOutboxNotFoundError("outbox row not found")
        if row.status == OutboxStatus.SYNCED.value:
            raise GraphOutboxStateError("invalid state transition")
        if row.status not in (
            OutboxStatus.PENDING.value,
            OutboxStatus.FAILED.value,
        ):
            raise GraphOutboxStateError("invalid state transition")

        row.status = OutboxStatus.FAILED.value
        row.attempts = int(row.attempts) + 1
        row.last_error = _sanitize_error(error)
        await self._session.flush()
        return row

    async def requeue_failed(self, outbox_id: UUID) -> GraphSyncOutbox:
        """Move failed work back to pending for a later explicit claim.

        Preserves attempt count and last_error so retry limits stay visible.
        Does not commit and does not start a poller.
        """
        row = await self.get_by_id(outbox_id)
        if row is None:
            raise GraphOutboxNotFoundError("outbox row not found")
        if row.status != OutboxStatus.FAILED.value:
            raise GraphOutboxStateError("invalid state transition")
        row.status = OutboxStatus.PENDING.value
        await self._session.flush()
        return row
