"""Read-only observability assembly: pagination, redaction, graph snapshot.

Owns CV history, retained-file metadata, chunk list/detail, durable-run
projections, and typed graph status assembly for Plan 8. Never mutates SQLite,
storage, Neo4j, or chat state. Callers own the session and unit of work.
Graph Cypher projection lives in :mod:`app.graph.observability`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.attachment_text_chunks import AttachmentTextChunk
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    Attachment,
)
from app.db.models.chat import AgentRun, ToolExecution
from app.graph.consistency import (
    NEO4J_REBUILD_REQUIRED,
    NEO4J_UNAVAILABLE,
    REBUILD_REQUIRED_INSTRUCTION,
    AsyncGraphReadDriver,
    check_active_cv_consistency,
    check_graph_revision_consistency,
)
from app.graph.observability import (
    BoundedGraphProjection,
    GraphProjectionError,
    load_bounded_graph_projection,
)
from app.repositories import observability as obs_repo
from app.repositories import profiles as profile_repo
from app.schemas.observability import (
    ChunkDetail,
    ChunkListItem,
    ChunkListPage,
    CvHistoryItem,
    CvHistoryPage,
    GraphCandidateNode,
    GraphCvEntryNode,
    GraphCvNode,
    GraphCvSectionNode,
    GraphEdge,
    GraphJobNode,
    GraphSkillNode,
    GraphSnapshot,
    ObservabilityToolExecution,
    RunHistoryItem,
    RunHistoryPage,
    abbreviate_file_hash,
    decode_chunk_cursor,
    decode_observability_cursor,
    encode_chunk_cursor,
    encode_observability_cursor,
)
from app.schemas.tools import parse_tool_result
from app.storage.attachments import AttachmentStorage, PathEscapeError

# Stable application error codes (safe summaries only).
ERROR_CV_ATTACHMENT_NOT_FOUND: str = "CV_ATTACHMENT_NOT_FOUND"
ERROR_CV_FILE_UNAVAILABLE: str = "CV_FILE_UNAVAILABLE"
ERROR_CHUNKS_UNAVAILABLE: str = "CHUNKS_UNAVAILABLE"
ERROR_CHUNK_NOT_FOUND: str = "CHUNK_NOT_FOUND"
ERROR_NO_ACTIVE_PROFILE: str = "NO_ACTIVE_PROFILE"
ERROR_CV_REPROCESS_REQUIRED: str = "CV_REPROCESS_REQUIRED"

_RETAINED_FILE_STATES: frozenset[str] = frozenset(
    {ATTACHMENT_STATE_ACTIVE, ATTACHMENT_STATE_ARCHIVED}
)

# Safe top-level keys that may yield related IDs without exposing arguments.
_ATTACHMENT_ID_KEYS: frozenset[str] = frozenset(
    {"attachment_id", "source_attachment_id", "active_attachment_id"}
)
_JOB_ID_KEYS: frozenset[str] = frozenset({"job_id", "job_post_id"})


class ObservabilityServiceError(Exception):
    """Application error with a stable code for HTTP mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_aware_utc(value: datetime) -> datetime:
    aware = _as_aware_utc(value)
    assert aware is not None
    return aware


def _file_available(storage: AttachmentStorage, row: Attachment) -> bool:
    """Whether the retained relative storage path exists under FILES_DIR."""
    try:
        return storage.exists(row.storage_path)
    except (PathEscapeError, ValueError, OSError):
        return False


def _cv_item(row: Attachment, *, file_available: bool) -> CvHistoryItem:
    return CvHistoryItem(
        id=row.id,
        original_name=row.original_name,
        mime_type="application/pdf",
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        state=row.state,  # type: ignore[arg-type]
        failure_code=row.failure_code,
        file_hash_abbreviated=abbreviate_file_hash(row.file_hash),
        file_available=file_available,
        created_at=_require_aware_utc(row.created_at),
        updated_at=_require_aware_utc(row.updated_at),
    )


def _chunk_list_item(row: AttachmentTextChunk) -> ChunkListItem:
    return ChunkListItem(
        attachment_id=row.attachment_id,
        ordinal=row.ordinal,
        preview=row.preview,
        char_count=row.char_count,
        token_estimate=row.token_estimate,
        created_at=_require_aware_utc(row.created_at),
    )


def _chunk_detail(row: AttachmentTextChunk) -> ChunkDetail:
    return ChunkDetail(
        attachment_id=row.attachment_id,
        ordinal=row.ordinal,
        text=row.text,
        preview=row.preview,
        char_count=row.char_count,
        token_estimate=row.token_estimate,
        created_at=_require_aware_utc(row.created_at),
    )


def _is_uuid_v4(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = uuid.UUID(value.strip().lower())
    except ValueError:
        return False
    return parsed.version == 4


def _collect_related_ids(
    tools: list[ToolExecution],
) -> tuple[list[str], list[str]]:
    """Extract related attachment/job UUIDs from safe summary maps only.

    Never returns full argument objects, result ``data``, or non-UUID values.
    """
    attachment_ids: list[str] = []
    job_ids: list[str] = []
    seen_att: set[str] = set()
    seen_job: set[str] = set()

    def _pull(mapping: dict[str, Any] | None) -> None:
        if not isinstance(mapping, dict):
            return
        for key, value in mapping.items():
            if key in _ATTACHMENT_ID_KEYS and _is_uuid_v4(value):
                text = str(value).strip().lower()
                if text not in seen_att:
                    seen_att.add(text)
                    attachment_ids.append(text)
            elif key in _JOB_ID_KEYS and _is_uuid_v4(value):
                text = str(value).strip().lower()
                if text not in seen_job:
                    seen_job.add(text)
                    job_ids.append(text)

    for tool in tools:
        _pull(tool.arguments_summary_json)
        if tool.result_json is not None and isinstance(tool.result_json, dict):
            data = tool.result_json.get("data")
            if isinstance(data, dict):
                _pull(data)
    return attachment_ids, job_ids


def _tool_summary(row: ToolExecution) -> str | None:
    """Safe terminal summary string only; never result data or arguments."""
    if row.result_json is None:
        return None
    try:
        parsed = parse_tool_result(row.result_json)
    except Exception:
        return None
    summary = parsed.summary
    if not isinstance(summary, str) or summary.strip() == "":
        return None
    return summary


def _tool_view(row: ToolExecution) -> ObservabilityToolExecution:
    return ObservabilityToolExecution(
        id=row.id,
        tool_name=row.tool_name,
        status=row.status,  # type: ignore[arg-type]
        duration_ms=row.duration_ms,
        error_code=row.error_code,
        summary=_tool_summary(row),
    )


def _run_view(run: AgentRun, tools: list[ToolExecution]) -> RunHistoryItem:
    related_att, related_job = _collect_related_ids(tools)
    return RunHistoryItem(
        id=run.id,
        user_message_id=run.user_message_id,
        state=run.state,  # type: ignore[arg-type]
        error_code=run.error_code,
        completed_at=_as_aware_utc(run.completed_at),
        created_at=_require_aware_utc(run.created_at),
        updated_at=_require_aware_utc(run.updated_at),
        related_attachment_ids=related_att,
        related_job_ids=related_job,
        tool_executions=[_tool_view(t) for t in tools],
    )


async def get_cv_history_page(
    session: AsyncSession,
    storage: AttachmentStorage,
    *,
    limit: int = 50,
    before: str | None = None,
) -> CvHistoryPage:
    """Load one chronological CV history page with opaque cursor pagination.

    *limit* must be in ``1..50``. *before* is a validated opaque cursor or
    ``None`` for the newest page. Does not finalize the caller's unit of work.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ObservabilityServiceError(
            "INVALID_LIMIT",
            "limit must be an integer in 1..50",
        )

    cursor_pair: tuple[datetime, str] | None = None
    if before is not None:
        cursor_pair = decode_observability_cursor(before)

    newest_first = await obs_repo.list_attachments_before(
        session,
        limit=limit + 1,
        before=cursor_pair,
    )
    has_older = len(newest_first) > limit
    page_newest_first = newest_first[:limit]
    page = list(reversed(page_newest_first))

    next_cursor: str | None = None
    if has_older and page:
        oldest = page[0]
        next_cursor = encode_observability_cursor(
            _require_aware_utc(oldest.created_at),
            oldest.id,
        )

    items = [
        _cv_item(row, file_available=_file_available(storage, row)) for row in page
    ]
    return CvHistoryPage(items=items, next_cursor=next_cursor)


async def resolve_retained_cv_file(
    session: AsyncSession,
    storage: AttachmentStorage,
    attachment_id: str,
) -> tuple[str, str, int]:
    """Resolve an active/archived retained PDF for streaming.

    Returns ``(storage_path, original_name, size_bytes)``. Raises
    :class:`ObservabilityServiceError` with ``CV_ATTACHMENT_NOT_FOUND`` or
    ``CV_FILE_UNAVAILABLE``. Never exposes the storage path in error messages.
    """
    row = await obs_repo.get_attachment(session, attachment_id)
    if row is None or row.state not in _RETAINED_FILE_STATES:
        raise ObservabilityServiceError(
            ERROR_CV_ATTACHMENT_NOT_FOUND,
            "CV attachment not found",
        )
    if not _file_available(storage, row):
        raise ObservabilityServiceError(
            ERROR_CV_FILE_UNAVAILABLE,
            "retained CV file is unavailable",
        )
    return row.storage_path, row.original_name, row.size_bytes


async def get_chunk_list_page(
    session: AsyncSession,
    attachment_id: str,
    *,
    limit: int = 50,
    before: str | None = None,
) -> ChunkListPage:
    """Load one ascending-ordinal chunk page for *attachment_id*.

    Historic attachments with zero chunk rows raise ``CHUNKS_UNAVAILABLE``.
    Unknown attachment raises ``CV_ATTACHMENT_NOT_FOUND``. Collection items
    never include full text.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ObservabilityServiceError(
            "INVALID_LIMIT",
            "limit must be an integer in 1..50",
        )

    attachment = await obs_repo.get_attachment(session, attachment_id)
    if attachment is None:
        raise ObservabilityServiceError(
            ERROR_CV_ATTACHMENT_NOT_FOUND,
            "CV attachment not found",
        )

    total = await obs_repo.count_chunks_for_attachment(session, attachment_id)
    if total == 0:
        raise ObservabilityServiceError(
            ERROR_CHUNKS_UNAVAILABLE,
            "chunk rows are unavailable for this attachment",
        )

    after_pair: tuple[datetime, int] | None = None
    if before is not None:
        after_pair = decode_chunk_cursor(before)

    ordered = await obs_repo.list_chunks_after(
        session,
        attachment_id,
        limit=limit + 1,
        after=after_pair,
    )
    has_more = len(ordered) > limit
    page = ordered[:limit]

    next_cursor: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_chunk_cursor(
            _require_aware_utc(last.created_at),
            last.ordinal,
        )

    return ChunkListPage(
        items=[_chunk_list_item(row) for row in page],
        next_cursor=next_cursor,
    )


async def get_chunk_detail(
    session: AsyncSession,
    attachment_id: str,
    ordinal: int,
) -> ChunkDetail:
    """Return one selected full-text chunk with safe metadata.

    Historic zero-row attachments raise ``CHUNKS_UNAVAILABLE``. Unknown
    attachment raises ``CV_ATTACHMENT_NOT_FOUND``. Missing ordinal when rows
    exist raises ``CHUNK_NOT_FOUND``.
    """
    if not isinstance(ordinal, int) or ordinal < 0:
        raise ObservabilityServiceError(
            ERROR_CHUNK_NOT_FOUND,
            "chunk not found",
        )

    attachment = await obs_repo.get_attachment(session, attachment_id)
    if attachment is None:
        raise ObservabilityServiceError(
            ERROR_CV_ATTACHMENT_NOT_FOUND,
            "CV attachment not found",
        )

    total = await obs_repo.count_chunks_for_attachment(session, attachment_id)
    if total == 0:
        raise ObservabilityServiceError(
            ERROR_CHUNKS_UNAVAILABLE,
            "chunk rows are unavailable for this attachment",
        )

    row = await obs_repo.get_chunk_by_ordinal(session, attachment_id, ordinal)
    if row is None:
        raise ObservabilityServiceError(
            ERROR_CHUNK_NOT_FOUND,
            "chunk not found",
        )
    return _chunk_detail(row)


async def get_run_history_page(
    session: AsyncSession,
    *,
    limit: int = 50,
    before: str | None = None,
) -> RunHistoryPage:
    """Load one chronological agent-run page with redacted tool projections.

    Never includes checkpoints, prompts, stack traces, or tool arguments.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ObservabilityServiceError(
            "INVALID_LIMIT",
            "limit must be an integer in 1..50",
        )

    cursor_pair: tuple[datetime, str] | None = None
    if before is not None:
        cursor_pair = decode_observability_cursor(before)

    newest_first = await obs_repo.list_runs_before(
        session,
        limit=limit + 1,
        before=cursor_pair,
    )
    has_older = len(newest_first) > limit
    page_newest_first = newest_first[:limit]
    page = list(reversed(page_newest_first))

    next_cursor: str | None = None
    if has_older and page:
        oldest = page[0]
        next_cursor = encode_observability_cursor(
            _require_aware_utc(oldest.created_at),
            oldest.id,
        )

    run_ids = [r.id for r in page]
    tools = await obs_repo.list_tool_executions_for_run_ids(session, run_ids)
    tools_by_run: dict[str, list[ToolExecution]] = {}
    for tool in tools:
        tools_by_run.setdefault(tool.run_id, []).append(tool)

    items = [_run_view(run, tools_by_run.get(run.id, [])) for run in page]
    return RunHistoryPage(items=items, next_cursor=next_cursor)


def _empty_graph_snapshot(
    *,
    status: str,
    code: str | None,
    summary: str,
    rebuild_instruction: str | None = None,
) -> GraphSnapshot:
    return GraphSnapshot(
        status=status,  # type: ignore[arg-type]
        code=code,
        summary=summary,
        rebuild_instruction=rebuild_instruction,
        cv=None,
        sections=[],
        entries=[],
        candidate=None,
        jobs=[],
        skills=[],
        edges=[],
        nodes_truncated=False,
        edges_truncated=False,
        omitted_node_count=0,
        omitted_edge_count=0,
        checked_at=utc_now(),
    )


def _ready_graph_snapshot(
    projection: BoundedGraphProjection,
    *,
    code: str | None = None,
    summary: str = (
        "Bounded active-CV + Candidate/Job/Skill graph snapshot is ready."
    ),
) -> GraphSnapshot:
    candidate: GraphCandidateNode | None = None
    if projection.candidate is not None:
        candidate = GraphCandidateNode(
            id=projection.candidate.id,
            revision=projection.candidate.revision,
        )
    cv: GraphCvNode | None = None
    if projection.cv is not None:
        cv = GraphCvNode(
            id=projection.cv.id,
            original_name=projection.cv.original_name,
            extraction_version=projection.cv.extraction_version,
            revision=projection.cv.revision,
        )
    return GraphSnapshot(
        status="ready",
        code=code,
        summary=summary,
        rebuild_instruction=None,
        cv=cv,
        sections=[
            GraphCvSectionNode(
                id=sec.id,
                heading=sec.heading,
                kind=sec.kind,
                ordinal=sec.ordinal,
                entry_count=sec.entry_count,
            )
            for sec in projection.sections
        ],
        entries=[
            GraphCvEntryNode(
                id=entry.id,
                section_id=entry.section_id,
                ordinal=entry.ordinal,
                title=entry.title,
                subtitle=entry.subtitle,
                date_text=entry.date_text,
                preview=entry.preview,
            )
            for entry in projection.entries
        ],
        candidate=candidate,
        jobs=[
            GraphJobNode(
                id=job.id,
                title=job.title,
                company=job.company,
                revision=job.revision,
            )
            for job in projection.jobs
        ],
        skills=[
            GraphSkillNode(canonical_name=skill.canonical_name)
            for skill in projection.skills
        ],
        edges=[
            GraphEdge(
                source_id=edge.source_id,
                target_id=edge.target_id,
                type=edge.type,
            )
            for edge in projection.edges
        ],
        nodes_truncated=projection.nodes_truncated,
        edges_truncated=projection.edges_truncated,
        omitted_node_count=projection.omitted_node_count,
        omitted_edge_count=projection.omitted_edge_count,
        checked_at=utc_now(),
    )


async def get_graph_snapshot(
    session: AsyncSession,
    driver: AsyncGraphReadDriver,
) -> GraphSnapshot:
    """Assemble a typed graph observability snapshot without mutation.

    Status vocabulary is exactly ``ready | stale | unavailable``:

    * no active SQLite profile → ``ready`` + empty + ``NO_ACTIVE_PROFILE``;
    * Candidate/Job or active-CV revision inconsistency → ``stale`` + empty
      + rebuild guidance;
    * adapter/projection failure → ``unavailable`` + empty + safe guidance;
    * otherwise ``ready`` with the cap-aware allowlisted projection (legacy
      active CV without document emits metadata only + ``CV_REPROCESS_REQUIRED``).
    """
    profile = await profile_repo.get_active_profile(session)
    if profile is None:
        return _empty_graph_snapshot(
            status="ready",
            code=ERROR_NO_ACTIVE_PROFILE,
            summary="No active candidate profile is available for graph inspection.",
        )

    consistency = await check_graph_revision_consistency(session, driver)
    if consistency.error_code == NEO4J_UNAVAILABLE:
        return _empty_graph_snapshot(
            status="unavailable",
            code=NEO4J_UNAVAILABLE,
            summary=(
                "Neo4j is unavailable; the graph snapshot cannot be loaded. "
                "Restore connectivity and retry."
            ),
        )
    if consistency.error_code == NEO4J_REBUILD_REQUIRED:
        return _empty_graph_snapshot(
            status="stale",
            code=NEO4J_REBUILD_REQUIRED,
            summary=(
                "Neo4j Candidate/Job revisions differ from SQLite; "
                "the graph snapshot is withheld until rebuild."
            ),
            rebuild_instruction=(
                consistency.rebuild_instruction or REBUILD_REQUIRED_INSTRUCTION
            ),
        )

    cv_consistency = await check_active_cv_consistency(session, driver)
    if cv_consistency.error_code == NEO4J_UNAVAILABLE:
        return _empty_graph_snapshot(
            status="unavailable",
            code=NEO4J_UNAVAILABLE,
            summary=(
                "Neo4j is unavailable; the graph snapshot cannot be loaded. "
                "Restore connectivity and retry."
            ),
        )
    if cv_consistency.error_code == NEO4J_REBUILD_REQUIRED:
        return _empty_graph_snapshot(
            status="stale",
            code=NEO4J_REBUILD_REQUIRED,
            summary=(
                "Neo4j active CV attachment ID or document source revision "
                "differs from SQLite; the graph snapshot is withheld until rebuild."
            ),
            rebuild_instruction=(
                cv_consistency.rebuild_instruction or REBUILD_REQUIRED_INSTRUCTION
            ),
        )

    try:
        projection = await load_bounded_graph_projection(driver)
    except GraphProjectionError:
        return _empty_graph_snapshot(
            status="unavailable",
            code=NEO4J_UNAVAILABLE,
            summary=(
                "Neo4j is unavailable; the graph snapshot cannot be loaded. "
                "Restore connectivity and retry."
            ),
        )
    except Exception:
        return _empty_graph_snapshot(
            status="unavailable",
            code=NEO4J_UNAVAILABLE,
            summary=(
                "Neo4j is unavailable; the graph snapshot cannot be loaded. "
                "Restore connectivity and retry."
            ),
        )

    # Legacy active CV: metadata node present, no sections → reprocess-required.
    if (
        projection.cv is not None
        and projection.cv.extraction_version == "legacy-reprocess-required"
    ):
        return _ready_graph_snapshot(
            projection,
            code=ERROR_CV_REPROCESS_REQUIRED,
            summary=(
                "Active CV is legacy metadata only (no structured sections); "
                "reprocess through CV Manager is required."
            ),
        )

    return _ready_graph_snapshot(projection)


__all__ = [
    "ERROR_CHUNK_NOT_FOUND",
    "ERROR_CHUNKS_UNAVAILABLE",
    "ERROR_CV_ATTACHMENT_NOT_FOUND",
    "ERROR_CV_FILE_UNAVAILABLE",
    "ERROR_CV_REPROCESS_REQUIRED",
    "ERROR_NO_ACTIVE_PROFILE",
    "ObservabilityServiceError",
    "get_chunk_detail",
    "get_chunk_list_page",
    "get_cv_history_page",
    "get_graph_snapshot",
    "get_run_history_page",
    "resolve_retained_cv_file",
]
