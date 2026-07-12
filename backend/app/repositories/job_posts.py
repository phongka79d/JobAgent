"""Persistence-first JobPost repository (caller-owned transactions).

Exact-hash dedup before extraction; normalized-key ignored-duplicate after
extraction; independent status dimensions; compact read model without raw JD,
hashes, embeddings, or error internals. Methods flush only and never commit
or roll back.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_uuid, utc_now
from app.db.enums import (
    GraphSyncStatus,
    JdQuality,
    JobSourceType,
    ProcessingStatus,
    RecordStatus,
)
from app.db.models.jobs import JobPost
from app.schemas.job_post import JobPostExtraction
from app.services.jd_source import hash_canonical_text

# ---------------------------------------------------------------------------
# Bounds and identity
# ---------------------------------------------------------------------------

NORMALIZED_KEY_VERSION: Final[str] = "v1"
DEFAULT_LIST_LIMIT: Final[int] = 10
MAX_LIST_LIMIT: Final[int] = 50
MAX_ERROR_CODE_LEN: Final[int] = 64
MAX_ERROR_MESSAGE_LEN: Final[int] = 1024
MAX_SOURCE_URL_LEN: Final[int] = 2048
HASH_HEX_LEN: Final[int] = 64
MAX_QUALITY_REASONS: Final[int] = 50
MAX_QUALITY_REASON_LEN: Final[int] = 256

_HASH_HEX_RE = re.compile(r"^[a-f0-9]{64}$")
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_PATH_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_AUTH_SCHEME_RE = re.compile(
    r"^(?:Basic|Bearer|Digest|Token|Negotiate|NTLM)\s+\S+",
    re.IGNORECASE,
)
_URI_USERINFO_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s?#\"']*:[^/\s?#\"']*@",
)
_SECRET_VALUE_MARKERS: tuple[str, ...] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)

# processing_status finite state machine (independent of other dimensions).
_ALLOWED_PROCESSING_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    ProcessingStatus.RECEIVED.value: frozenset({ProcessingStatus.PROCESSING.value}),
    ProcessingStatus.PROCESSING.value: frozenset(
        {
            ProcessingStatus.PROCESSED.value,
            ProcessingStatus.FAILED.value,
        }
    ),
    ProcessingStatus.PROCESSED.value: frozenset(),
    ProcessingStatus.FAILED.value: frozenset(),
}

_ALLOWED_GRAPH_SYNC: Final[frozenset[str]] = frozenset(
    s.value for s in GraphSyncStatus
)
_ALLOWED_SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    s.value for s in JobSourceType
)
_ALLOWED_JD_QUALITY: Final[frozenset[str]] = frozenset(q.value for q in JdQuality)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class JobPostRepositoryError(Exception):
    """Job persistence failed without disclosing raw JD content."""


class JobPostNotFoundError(JobPostRepositoryError):
    """No job_posts row exists for the requested identity."""


class JobPostStateError(JobPostRepositoryError):
    """Requested status transition is not allowed for the current row state."""


class JobPostValidationError(JobPostRepositoryError):
    """Input, identity, JSON, or failure payload failed closed validation."""


class JobPostDuplicateError(JobPostRepositoryError):
    """Reserved for unresolved uniqueness conflicts (exact races resolve soft)."""


# ---------------------------------------------------------------------------
# Compact public read model (no raw content / hash / embeddings / errors)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JobPostRecord:
    """Compact validated Job view for repository and tool consumers.

    Deliberately omits ``raw_content``, ``raw_content_hash``, embedding
    identity, and error internals so read paths cannot dump the JD corpus.
    """

    id: UUID
    source_type: str
    source_url: str | None
    processing_status: str
    jd_quality: str | None
    quality_reasons: list[str] | None
    graph_sync_status: str
    record_status: str
    duplicate_of_job_id: UUID | None
    extraction: JobPostExtraction | None
    score_cache: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CreateReceivedResult:
    """Outcome of exact-hash create-or-return."""

    record: JobPostRecord
    created: bool


# ---------------------------------------------------------------------------
# Normalized identity (company + title + location)
# ---------------------------------------------------------------------------


def normalize_job_identity_component(value: str | None) -> str | None:
    """Normalize one company/title/location component for identity matching.

    NFC, whitespace collapse, casefold; empty after normalize → ``None``.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise JobPostValidationError("invalid identity component")
    text = unicodedata.normalize("NFC", value)
    text = " ".join(text.split())
    text = text.casefold().strip()
    return text or None


def build_normalized_job_key(
    company: str | None,
    title: str | None,
    location: str | None,
) -> str | None:
    """Build a versioned SHA-256 identity when all three components are nonblank.

    Uses length-delimited normalized components so adjacent concatenations
    cannot collide. Returns ``None`` when any component is insufficient
    (exact-hash dedup only in that case).
    """
    company_n = normalize_job_identity_component(company)
    title_n = normalize_job_identity_component(title)
    location_n = normalize_job_identity_component(location)
    if not company_n or not title_n or not location_n:
        return None
    # Length-delimited so "ab"+"c" != "a"+"bc".
    payload = (
        f"{len(company_n)}:{company_n}\0"
        f"{len(title_n)}:{title_n}\0"
        f"{len(location_n)}:{location_n}"
    )
    digest = hashlib.sha256(
        f"{NORMALIZED_KEY_VERSION}\0{payload}".encode()
    ).hexdigest()
    return f"{NORMALIZED_KEY_VERSION}:{digest}"


# ---------------------------------------------------------------------------
# Sanitization / validation helpers
# ---------------------------------------------------------------------------


def _string_looks_like_path(value: str) -> bool:
    if not value:
        return False
    stripped = value.strip().strip("\"'")
    lower = stripped.lower()
    if "file:" in lower:
        return True
    if _PATH_DRIVE_RE.match(stripped):
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


def _string_looks_like_secret(value: str) -> bool:
    stripped = value.strip().strip("\"'")
    if _AUTH_SCHEME_RE.match(stripped):
        return True
    if _URI_USERINFO_RE.search(stripped):
        return True
    upper = value.upper()
    for marker in _SECRET_VALUE_MARKERS:
        if marker in upper:
            return True
    return False


def sanitize_job_error_code(error_code: str | None) -> str:
    """Normalize a stable UPPER_SNAKE failure code for durable storage."""
    if error_code is None or not isinstance(error_code, str):
        raise JobPostValidationError("invalid error_code")
    cleaned = error_code.strip().upper().replace("-", "_").replace(" ", "_")
    if not cleaned:
        raise JobPostValidationError("invalid error_code")
    if len(cleaned) > MAX_ERROR_CODE_LEN:
        cleaned = cleaned[:MAX_ERROR_CODE_LEN]
    if not _ERROR_CODE_RE.fullmatch(cleaned):
        raise JobPostValidationError("invalid error_code")
    return cleaned


def sanitize_job_error_message(message: str | None) -> str | None:
    """Sanitize a short failure message; path/secret-shaped values collapse."""
    if message is None:
        return None
    if not isinstance(message, str):
        raise JobPostValidationError("invalid error_message")
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > MAX_ERROR_MESSAGE_LEN:
        cleaned = cleaned[:MAX_ERROR_MESSAGE_LEN]
    if _string_looks_like_path(cleaned) or _string_looks_like_secret(cleaned):
        return "job_processing_failed"
    return cleaned


def _validate_uuid(value: UUID, *, name: str) -> UUID:
    if not isinstance(value, UUID):
        raise JobPostValidationError(f"invalid {name}")
    return value


def _validate_content_hash(value: str) -> str:
    if not isinstance(value, str) or not _HASH_HEX_RE.fullmatch(value):
        raise JobPostValidationError("invalid raw_content_hash")
    return value


def _validate_raw_content(raw_content: str) -> str:
    if not isinstance(raw_content, str):
        raise JobPostValidationError("invalid raw_content")
    if not raw_content or not raw_content.strip():
        raise JobPostValidationError("invalid raw_content")
    return raw_content


def _validate_source_type(source_type: str | JobSourceType) -> str:
    if isinstance(source_type, JobSourceType):
        return source_type.value
    if not isinstance(source_type, str):
        raise JobPostValidationError("invalid source_type")
    normalized = source_type.strip().lower()
    if normalized not in _ALLOWED_SOURCE_TYPES:
        raise JobPostValidationError("invalid source_type")
    return normalized


def _validate_source_url(source_url: str | None, *, source_type: str) -> str | None:
    if source_url is None:
        return None
    if not isinstance(source_url, str):
        raise JobPostValidationError("invalid source_url")
    cleaned = source_url.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_SOURCE_URL_LEN:
        raise JobPostValidationError("invalid source_url")
    if _string_looks_like_secret(cleaned) or "://" in cleaned and "@" in cleaned.split(
        "://", 1
    )[1].split("/", 1)[0]:
        raise JobPostValidationError("invalid source_url")
    if source_type == JobSourceType.TEXT.value and cleaned:
        # Text source may still carry a display URL; allow non-secret URLs.
        pass
    return cleaned


def _validate_extraction(data: Any) -> JobPostExtraction:
    if isinstance(data, JobPostExtraction):
        # Round-trip so storage form matches read path.
        try:
            return JobPostExtraction.model_validate(data.model_dump(mode="json"))
        except ValidationError as exc:
            raise JobPostValidationError("invalid extracted_json") from exc
    if not isinstance(data, dict):
        raise JobPostValidationError("invalid extracted_json")
    try:
        return JobPostExtraction.model_validate(data)
    except ValidationError as exc:
        raise JobPostValidationError("invalid extracted_json") from exc


def _validate_quality_reasons(reasons: Any) -> list[str] | None:
    if reasons is None:
        return None
    if not isinstance(reasons, list):
        raise JobPostValidationError("invalid quality_reasons")
    if len(reasons) > MAX_QUALITY_REASONS:
        raise JobPostValidationError("invalid quality_reasons")
    cleaned: list[str] = []
    for item in reasons:
        if not isinstance(item, str):
            raise JobPostValidationError("invalid quality_reasons")
        text = " ".join(item.strip().split())
        if not text:
            continue
        if len(text) > MAX_QUALITY_REASON_LEN:
            text = text[:MAX_QUALITY_REASON_LEN]
        cleaned.append(text)
    return cleaned


def _validate_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIST_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise JobPostValidationError("invalid limit")
    if limit < 1:
        raise JobPostValidationError("invalid limit")
    if limit > MAX_LIST_LIMIT:
        raise JobPostValidationError("limit exceeds maximum")
    return limit


def _optional_status_filter(
    value: str | None,
    *,
    allowed: frozenset[str],
    name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise JobPostValidationError(f"invalid {name}")
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise JobPostValidationError(f"invalid {name}")
    return normalized


def _score_cache_view(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise JobPostValidationError("invalid score_cache")
    return dict(value)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class JobPostRepository:
    """Narrow JobPost lifecycle on a caller-owned ``AsyncSession``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- internal row helpers ------------------------------------------------

    async def _get_row(self, job_id: UUID) -> JobPost | None:
        return await self._session.get(JobPost, job_id)

    async def _get_row_by_hash(self, content_hash: str) -> JobPost | None:
        result = await self._session.execute(
            select(JobPost).where(JobPost.raw_content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    def _to_record(self, row: JobPost) -> JobPostRecord:
        extraction: JobPostExtraction | None = None
        if row.extracted_json is not None:
            extraction = _validate_extraction(row.extracted_json)
        reasons = _validate_quality_reasons(row.quality_reasons)
        score = _score_cache_view(row.score_cache)
        return JobPostRecord(
            id=row.id,
            source_type=row.source_type,
            source_url=row.source_url,
            processing_status=row.processing_status,
            jd_quality=row.jd_quality,
            quality_reasons=reasons,
            graph_sync_status=row.graph_sync_status,
            record_status=row.record_status,
            duplicate_of_job_id=row.duplicate_of_job_id,
            extraction=extraction,
            score_cache=score,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # -- reads ---------------------------------------------------------------

    async def get_by_id(self, job_id: UUID) -> JobPostRecord | None:
        """Load one compact Job record by primary key, or ``None``."""
        job_id = _validate_uuid(job_id, name="job_id")
        row = await self._get_row(job_id)
        if row is None:
            return None
        return self._to_record(row)

    async def get_by_content_hash(self, content_hash: str) -> JobPostRecord | None:
        """Exact-hash lookup returning the compact record, or ``None``."""
        content_hash = _validate_content_hash(content_hash)
        row = await self._get_row_by_hash(content_hash)
        if row is None:
            return None
        return self._to_record(row)

    async def list_filtered(
        self,
        *,
        processing_status: str | None = None,
        jd_quality: str | None = None,
        record_status: str | None = None,
        graph_sync_status: str | None = None,
        limit: int | None = None,
    ) -> list[JobPostRecord]:
        """Bounded filtered list (default 10, max 50). Newest first.

        Never returns raw content or an unbounded corpus.
        """
        capped = _validate_limit(limit)
        proc = _optional_status_filter(
            processing_status,
            allowed=frozenset(s.value for s in ProcessingStatus),
            name="processing_status",
        )
        quality = _optional_status_filter(
            jd_quality,
            allowed=_ALLOWED_JD_QUALITY,
            name="jd_quality",
        )
        record = _optional_status_filter(
            record_status,
            allowed=frozenset(s.value for s in RecordStatus),
            name="record_status",
        )
        graph = _optional_status_filter(
            graph_sync_status,
            allowed=_ALLOWED_GRAPH_SYNC,
            name="graph_sync_status",
        )

        stmt = select(JobPost)
        if proc is not None:
            stmt = stmt.where(JobPost.processing_status == proc)
        if quality is not None:
            stmt = stmt.where(JobPost.jd_quality == quality)
        if record is not None:
            stmt = stmt.where(JobPost.record_status == record)
        if graph is not None:
            stmt = stmt.where(JobPost.graph_sync_status == graph)
        stmt = stmt.order_by(
            JobPost.created_at.desc(),
            JobPost.id.desc(),
        ).limit(capped)

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return [self._to_record(row) for row in rows]

    async def list_graph_eligible_page(
        self,
        *,
        after_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[JobPostRecord]:
        """Bounded page of active full|partial processed Jobs for rebuild.

        Keyset pagination on primary key (``id ASC``). Never returns raw
        content. Page size is capped at ``MAX_LIST_LIMIT`` (default 50).
        """
        capped = _validate_limit(limit if limit is not None else MAX_LIST_LIMIT)
        stmt = (
            select(JobPost)
            .where(
                JobPost.processing_status == ProcessingStatus.PROCESSED.value,
                JobPost.record_status == RecordStatus.ACTIVE.value,
                JobPost.jd_quality.in_(
                    (JdQuality.FULL.value, JdQuality.PARTIAL.value),
                ),
            )
            .order_by(JobPost.id.asc())
            .limit(capped)
        )
        if after_id is not None:
            cursor = _validate_uuid(after_id, name="after_id")
            stmt = stmt.where(JobPost.id > cursor)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return [self._to_record(row) for row in rows]

    # -- exact create / received ---------------------------------------------

    async def create_received(
        self,
        *,
        source_type: str | JobSourceType,
        raw_content: str,
        raw_content_hash: str | None = None,
        source_url: str | None = None,
    ) -> CreateReceivedResult:
        """Insert a novel ``received`` row, or return the exact-hash existing.

        Persists canonical raw content before any provider call. Concurrent
        identical hashes resolve via unique ``raw_content_hash`` +
        ``INSERT … ON CONFLICT DO NOTHING`` then select (no second row).
        Does not commit.
        """
        source = _validate_source_type(source_type)
        content = _validate_raw_content(raw_content)
        computed = hash_canonical_text(content)
        if raw_content_hash is not None:
            provided = _validate_content_hash(raw_content_hash)
            if provided != computed:
                raise JobPostValidationError("raw_content_hash mismatch")
            content_hash = provided
        else:
            content_hash = computed
        url = _validate_source_url(source_url, source_type=source)

        existing = await self._get_row_by_hash(content_hash)
        if existing is not None:
            return CreateReceivedResult(
                record=self._to_record(existing),
                created=False,
            )

        job_id = new_uuid()
        now = utc_now()
        stmt = (
            sqlite_insert(JobPost)
            .values(
                id=job_id,
                source_type=source,
                source_url=url,
                raw_content=content,
                raw_content_hash=content_hash,
                normalized_key=None,
                extracted_json=None,
                quality_reasons=None,
                score_cache=None,
                processing_status=ProcessingStatus.RECEIVED.value,
                jd_quality=None,
                graph_sync_status=GraphSyncStatus.NOT_REQUIRED.value,
                record_status=RecordStatus.ACTIVE.value,
                duplicate_of_job_id=None,
                embedding_model=None,
                embedding_dimensions=None,
                error_code=None,
                error_message=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["raw_content_hash"])
        )
        await self._session.execute(stmt)

        row = await self._get_row_by_hash(content_hash)
        if row is None:
            raise JobPostRepositoryError(
                "job post missing after conflict-safe create"
            )
        created = row.id == job_id
        return CreateReceivedResult(
            record=self._to_record(row),
            created=created,
        )

    # -- processing transitions ----------------------------------------------

    async def mark_processing(self, job_id: UUID) -> JobPostRecord:
        """``received`` → ``processing``. Does not commit."""
        job_id = _validate_uuid(job_id, name="job_id")
        row = await self._get_row(job_id)
        if row is None:
            raise JobPostNotFoundError("job post not found")
        self._assert_processing_transition(
            row.processing_status,
            ProcessingStatus.PROCESSING.value,
        )
        row.processing_status = ProcessingStatus.PROCESSING.value
        row.updated_at = utc_now()
        await self._session.flush()
        return self._to_record(row)

    async def mark_processed(
        self,
        job_id: UUID,
        *,
        extraction: JobPostExtraction | dict[str, Any],
        quality_reasons: list[str] | None = None,
        force_new: bool = False,
    ) -> JobPostRecord:
        """``processing`` → ``processed`` with validated extraction storage.

        When company/title/location all normalize nonblank and an active
        processed peer already owns that key, this row becomes
        ``ignored_duplicate`` / ``not_required`` with ``duplicate_of_job_id``
        unless ``force_new`` is true. Does not commit.
        """
        job_id = _validate_uuid(job_id, name="job_id")
        row = await self._get_row(job_id)
        if row is None:
            raise JobPostNotFoundError("job post not found")
        self._assert_processing_transition(
            row.processing_status,
            ProcessingStatus.PROCESSED.value,
        )
        if not isinstance(force_new, bool):
            raise JobPostValidationError("invalid force_new")

        validated = _validate_extraction(extraction)
        reasons = _validate_quality_reasons(quality_reasons)
        # full quality: reasons should be empty/None; non-full may carry reasons.
        storage = validated.model_dump(mode="json")
        quality_value = validated.jd_quality.value

        norm_key = build_normalized_job_key(
            validated.company,
            validated.title,
            validated.location,
        )

        row.extracted_json = storage
        row.jd_quality = quality_value
        row.quality_reasons = reasons
        row.normalized_key = norm_key
        row.processing_status = ProcessingStatus.PROCESSED.value
        row.error_code = None
        row.error_message = None
        row.updated_at = utc_now()
        # Default active until peer lookup decides otherwise.
        if row.record_status != RecordStatus.IGNORED_DUPLICATE.value:
            row.record_status = RecordStatus.ACTIVE.value
            row.duplicate_of_job_id = None

        await self._session.flush()

        if (
            norm_key is not None
            and not force_new
            and row.record_status == RecordStatus.ACTIVE.value
        ):
            peer = await self._find_active_peer_by_normalized_key(
                norm_key,
                exclude_id=row.id,
            )
            if peer is not None:
                row.record_status = RecordStatus.IGNORED_DUPLICATE.value
                row.duplicate_of_job_id = peer.id
                row.graph_sync_status = GraphSyncStatus.NOT_REQUIRED.value
                row.updated_at = utc_now()
                await self._session.flush()

        return self._to_record(row)

    async def mark_failed(
        self,
        job_id: UUID,
        *,
        error_code: str,
        error_message: str | None = None,
    ) -> JobPostRecord:
        """``processing`` → ``failed`` with sanitized code/message.

        Retains raw content on the row. Does not commit.
        """
        job_id = _validate_uuid(job_id, name="job_id")
        row = await self._get_row(job_id)
        if row is None:
            raise JobPostNotFoundError("job post not found")
        self._assert_processing_transition(
            row.processing_status,
            ProcessingStatus.FAILED.value,
        )
        code = sanitize_job_error_code(error_code)
        message = sanitize_job_error_message(error_message)
        row.processing_status = ProcessingStatus.FAILED.value
        row.error_code = code
        row.error_message = message
        row.updated_at = utc_now()
        await self._session.flush()
        return self._to_record(row)

    async def mark_ignored_duplicate(
        self,
        job_id: UUID,
        *,
        duplicate_of_job_id: UUID,
    ) -> JobPostRecord:
        """Mark a row as ``ignored_duplicate`` linked to a peer.

        Sets ``graph_sync_status=not_required``. Does not commit.
        """
        job_id = _validate_uuid(job_id, name="job_id")
        duplicate_of_job_id = _validate_uuid(
            duplicate_of_job_id, name="duplicate_of_job_id"
        )
        if job_id == duplicate_of_job_id:
            raise JobPostValidationError("invalid duplicate_of_job_id")
        row = await self._get_row(job_id)
        if row is None:
            raise JobPostNotFoundError("job post not found")
        peer = await self._get_row(duplicate_of_job_id)
        if peer is None:
            raise JobPostValidationError("duplicate_of_job_id not found")
        row.record_status = RecordStatus.IGNORED_DUPLICATE.value
        row.duplicate_of_job_id = duplicate_of_job_id
        row.graph_sync_status = GraphSyncStatus.NOT_REQUIRED.value
        row.updated_at = utc_now()
        await self._session.flush()
        return self._to_record(row)

    async def set_graph_sync_status(
        self,
        job_id: UUID,
        *,
        status: str | GraphSyncStatus,
    ) -> JobPostRecord:
        """Update independent ``graph_sync_status``. Does not commit."""
        job_id = _validate_uuid(job_id, name="job_id")
        row = await self._get_row(job_id)
        if row is None:
            raise JobPostNotFoundError("job post not found")
        if isinstance(status, GraphSyncStatus):
            value = status.value
        elif isinstance(status, str):
            value = status.strip().lower()
        else:
            raise JobPostValidationError("invalid graph_sync_status")
        if value not in _ALLOWED_GRAPH_SYNC:
            raise JobPostValidationError("invalid graph_sync_status")
        # Ignored duplicates must not become sync-eligible through this path.
        if (
            row.record_status == RecordStatus.IGNORED_DUPLICATE.value
            and value != GraphSyncStatus.NOT_REQUIRED.value
        ):
            raise JobPostStateError("ignored duplicate cannot require graph sync")
        row.graph_sync_status = value
        row.updated_at = utc_now()
        await self._session.flush()
        return self._to_record(row)

    async def set_embedding_identity(
        self,
        job_id: UUID,
        *,
        embedding_model: str | None,
        embedding_dimensions: int | None,
    ) -> JobPostRecord:
        """Store embedding model/dimension identity (not vectors). Does not commit.

        Compact reads still omit these fields; callers that need identity load
        the ORM row or a future narrow accessor. Validates bounded inputs.
        """
        job_id = _validate_uuid(job_id, name="job_id")
        row = await self._get_row(job_id)
        if row is None:
            raise JobPostNotFoundError("job post not found")
        if embedding_model is not None:
            if not isinstance(embedding_model, str) or not embedding_model.strip():
                raise JobPostValidationError("invalid embedding_model")
            model = embedding_model.strip()
            if len(model) > 128:
                raise JobPostValidationError("invalid embedding_model")
        else:
            model = None
        if embedding_dimensions is not None:
            if (
                not isinstance(embedding_dimensions, int)
                or isinstance(embedding_dimensions, bool)
                or embedding_dimensions <= 0
            ):
                raise JobPostValidationError("invalid embedding_dimensions")
            dims: int | None = embedding_dimensions
        else:
            dims = None
        row.embedding_model = model
        row.embedding_dimensions = dims
        row.updated_at = utc_now()
        await self._session.flush()
        return self._to_record(row)

    # -- private -------------------------------------------------------------

    def _assert_processing_transition(self, current: str, target: str) -> None:
        allowed = _ALLOWED_PROCESSING_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise JobPostStateError("invalid state transition")

    async def _find_active_peer_by_normalized_key(
        self,
        normalized_key: str,
        *,
        exclude_id: UUID,
    ) -> JobPost | None:
        """Oldest active processed peer with the same sufficient identity."""
        result = await self._session.execute(
            select(JobPost)
            .where(
                JobPost.normalized_key == normalized_key,
                JobPost.record_status == RecordStatus.ACTIVE.value,
                JobPost.processing_status == ProcessingStatus.PROCESSED.value,
                JobPost.id != exclude_id,
            )
            .order_by(JobPost.created_at.asc(), JobPost.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()


__all__ = [
    "DEFAULT_LIST_LIMIT",
    "MAX_LIST_LIMIT",
    "NORMALIZED_KEY_VERSION",
    "CreateReceivedResult",
    "JobPostDuplicateError",
    "JobPostNotFoundError",
    "JobPostRecord",
    "JobPostRepository",
    "JobPostRepositoryError",
    "JobPostStateError",
    "JobPostValidationError",
    "build_normalized_job_key",
    "normalize_job_identity_component",
    "sanitize_job_error_code",
    "sanitize_job_error_message",
]
