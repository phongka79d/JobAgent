"""Saved-JD list/detail reads and source-bound mutations (Plan 10 / Master §14).

Reads: Job paging, server-side evaluation context hashing, and
``job_evaluations.lookup_for_job`` so list/detail currentness matches write-side
rules without mutating rows or calling providers/Neo4j/scoring.

Mutations: authorize save-and-evaluate from the durable initiating user message
whose completed run contains a successful zero-count ``match_jobs`` result;
delegate URL/text ingestion, exact evaluation, and complete deletion to accepted
owners. Routes only map status/errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from urllib.parse import urlparse

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    ChatMessage,
)
from app.db.models.job_evaluations import JobEvaluation
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_PROCESSED,
    JobPost,
)
from app.db.session import session_scope
from app.graph.consistency import AsyncGraphReadDriver
from app.graph.sync_shared import AsyncGraphDriver
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import job_evaluations as eval_repo
from app.repositories import profiles as profiles_repo
from app.repositories import saved_jobs as saved_jobs_repo
from app.repositories import tool_executions as tools_repo
from app.schemas.job_evaluations import (
    SAVED_JOBS_LIMIT_MAX,
    SAVED_JOBS_LIMIT_MIN,
    EvaluateJobResponse,
    EvaluationCurrentnessLiteral,
    EvaluationRowStateLiteral,
    JobEvaluationRecord,
    JobEvaluationView,
    ReextractJobResponse,
    SaveAndEvaluateResponse,
    SavedJobDetail,
    SavedJobListItem,
    SavedJobListPage,
    SaveEvaluationOutcomeLiteral,
    SaveIngestOutcomeLiteral,
    decode_saved_jobs_cursor,
    encode_saved_jobs_cursor,
    evaluation_view_from_record,
    record_from_row,
)
from app.schemas.jobs import (
    JOB_INGEST_OUTCOME_CREATED,
    JOB_INGEST_OUTCOME_RETRIED,
    JOB_INGEST_OUTCOME_RETURNED,
    JobIngestOutcome,
    JobPostExtraction,
    parse_job_post_extraction,
)
from app.schemas.matching import parse_match_jobs_result_data
from app.schemas.tools import parse_tool_result
from app.services.evaluation_context import (
    MATCHING_CONTRACT_VERSION,
    EvaluationContextFacts,
    evaluation_context_hash,
)
from app.services.jd_extraction import StructuredJdInvoker
from app.services.jd_ingestion import (
    JdIngestionError,
    UrlFetcher,
    ingest_raw_text,
    ingest_url,
)
from app.services.job_deletion import (
    ERROR_JOB_DELETE_GRAPH_FAILED,
    JobDeleteError,
    delete_job,
)
from app.services.job_deletion import (
    ERROR_JOB_NOT_FOUND as DELETE_JOB_NOT_FOUND,
)
from app.services.job_evaluation import (
    ERROR_ACTIVE_PROFILE_REQUIRED,
    ERROR_JOB_NOT_SCORABLE,
    evaluate_job,
)
from app.services.job_projection import EmbeddingClient, JobSyncFn
from app.services.job_reextraction import (
    ERROR_JOB_REEXTRACT_CONFLICT,
    JobReextractError,
    reextract_job,
)
from app.services.skill_normalization import SkillNormalizer
from app.services.url_fetch import validate_url_scheme

logger = logging.getLogger(__name__)

ERROR_JOB_NOT_FOUND: str = "JOB_NOT_FOUND"
ERROR_JD_SOURCE_NOT_RECOVERABLE: str = "JD_SOURCE_NOT_RECOVERABLE"
JOB_NOT_FOUND_MESSAGE: str = "The requested Job was not found."
JD_SOURCE_NOT_RECOVERABLE_MESSAGE: str = (
    "The initiating chat message cannot authorize save-and-evaluate. "
    "Provide the durable user message whose completed run contains a "
    "successful zero-result match_jobs outcome."
)

# Stable tool name — avoid importing tools.matching (heavy Agent dependency).
_MATCH_JOBS_NAME: str = "match_jobs"

_SCORABLE_QUALITIES = frozenset({JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL})
SourceKind = Literal["url", "text"]


class SavedJobsServiceError(Exception):
    """Stable application error for saved-JD read and mutation paths."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class _SharedContextRevisions:
    """Active profile/CV/prefs facts shared across Jobs for context hashing."""

    active_attachment_id: str
    cv_source_hash: str
    profile_revision: datetime
    preferences_revision: datetime


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _title_company(row: JobPost) -> tuple[str | None, str | None]:
    title: str | None = None
    company: str | None = None
    extraction = row.extraction_json
    if isinstance(extraction, dict):
        raw_title = extraction.get("title")
        raw_company = extraction.get("company")
        if isinstance(raw_title, str):
            title = raw_title
        if isinstance(raw_company, str):
            company = raw_company
    return title, company


def _validated_extraction(row: JobPost) -> JobPostExtraction | None:
    payload = row.extraction_json
    if payload is None:
        return None
    try:
        return parse_job_post_extraction(payload)
    except (ValidationError, ValueError, TypeError):
        return None


def _record_from_orm(row: JobEvaluation) -> JobEvaluationRecord:
    return record_from_row(
        id=row.id,
        job_id=row.job_id,
        active_attachment_id=row.active_attachment_id,
        evaluation_context_hash=row.evaluation_context_hash,
        job_revision=row.job_revision,
        profile_revision=row.profile_revision,
        preferences_revision=row.preferences_revision,
        cv_source_hash=row.cv_source_hash,
        matching_contract_version=row.matching_contract_version,
        result_json=row.result_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _load_shared_context(
    session: AsyncSession,
) -> _SharedContextRevisions | None:
    """Load active approved profile/CV/prefs facts, or ``None`` if incomplete."""
    profile_row = await profiles_repo.get_active_profile(session)
    if profile_row is None:
        return None
    prefs_row = await profiles_repo.get_job_preferences(session)
    if prefs_row is None:
        return None
    attachment_id = profile_row.active_attachment_id
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        return None
    cv_doc = await cv_doc_repo.get_document(session, attachment_id)
    if cv_doc is None or not isinstance(cv_doc.source_hash, str):
        return None
    if cv_doc.source_hash.strip() == "":
        return None
    return _SharedContextRevisions(
        active_attachment_id=attachment_id,
        cv_source_hash=cv_doc.source_hash,
        profile_revision=_as_aware_utc(profile_row.updated_at),
        preferences_revision=_as_aware_utc(prefs_row.updated_at),
    )


def _context_hash_for_job(
    job: JobPost,
    shared: _SharedContextRevisions | None,
) -> str | None:
    if shared is None:
        return None
    facts = EvaluationContextFacts(
        job_id=job.id,
        job_revision=_as_aware_utc(job.updated_at),
        active_attachment_id=shared.active_attachment_id,
        cv_source_hash=shared.cv_source_hash,
        profile_revision=shared.profile_revision,
        preferences_revision=shared.preferences_revision,
        matching_contract_version=MATCHING_CONTRACT_VERSION,
    )
    return evaluation_context_hash(facts)


async def _lookup_state(
    session: AsyncSession,
    *,
    job_id: str,
    current_context_hash: str | None,
) -> tuple[EvaluationCurrentnessLiteral, JobEvaluationRecord | None]:
    """Derive none|current|stale and the relevant evaluation without writes.

    Without a current context hash (no active profile/CV), exact-current is
    impossible: any stored evaluation is ``stale``; otherwise ``none``.
    """
    if current_context_hash is not None:
        lookup = await eval_repo.lookup_for_job(
            session,
            job_id=job_id,
            current_context_hash=current_context_hash,
        )
        return lookup.currentness, lookup.evaluation

    latest = await eval_repo.get_latest_for_job(session, job_id)
    if latest is None:
        return "none", None
    return "stale", _record_from_orm(latest)


def _list_item(
    row: JobPost,
    *,
    evaluation_state: EvaluationCurrentnessLiteral,
    evaluation: JobEvaluationRecord | None,
) -> SavedJobListItem:
    title, company = _title_company(row)
    latest_score: float | None = None
    if evaluation is not None:
        latest_score = evaluation.result.final_score
    return SavedJobListItem(
        id=row.id,
        title=title,
        company=company,
        processing_status=row.processing_status,  # type: ignore[arg-type]
        jd_quality=row.jd_quality,  # type: ignore[arg-type]
        source_type=row.source_type,  # type: ignore[arg-type]
        source_url=row.source_url,
        created_at=_as_aware_utc(row.created_at),
        updated_at=_as_aware_utc(row.updated_at),
        evaluation_state=evaluation_state,
        latest_score=latest_score,
    )


def _evaluation_view(
    evaluation: JobEvaluationRecord | None,
    *,
    evaluation_state: EvaluationCurrentnessLiteral,
) -> JobEvaluationView | None:
    if evaluation is None or evaluation_state == "none":
        return None
    state: EvaluationRowStateLiteral = (
        "current" if evaluation_state == "current" else "stale"
    )
    return evaluation_view_from_record(evaluation, evaluation_state=state)


async def get_saved_jobs_page(
    session: AsyncSession,
    *,
    limit: int = 50,
    before: str | None = None,
) -> SavedJobListPage:
    """Load one newest-first compact saved-JD page with derived currentness.

    *limit* must be in ``1..50``. *before* is a validated opaque cursor or
    ``None`` for the newest page. Does not mutate rows or run external work.
    Does not finalize the caller's unit of work.
    """
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise SavedJobsServiceError(
            "INVALID_LIMIT",
            "limit must be an integer in 1..50",
        )
    if limit < SAVED_JOBS_LIMIT_MIN or limit > SAVED_JOBS_LIMIT_MAX:
        raise SavedJobsServiceError(
            "INVALID_LIMIT",
            "limit must be an integer in 1..50",
        )

    cursor_pair: tuple[datetime, str] | None = None
    if before is not None:
        cursor_pair = decode_saved_jobs_cursor(before)

    newest_first = await saved_jobs_repo.list_jobs_before(
        session,
        limit=limit + 1,
        before=cursor_pair,
    )
    has_older = len(newest_first) > limit
    page = newest_first[:limit]

    next_cursor: str | None = None
    if has_older and page:
        oldest = page[-1]
        next_cursor = encode_saved_jobs_cursor(
            _as_aware_utc(oldest.created_at),
            oldest.id,
        )

    shared = await _load_shared_context(session)
    items: list[SavedJobListItem] = []
    for row in page:
        context_hash = _context_hash_for_job(row, shared)
        state, evaluation = await _lookup_state(
            session,
            job_id=row.id,
            current_context_hash=context_hash,
        )
        items.append(
            _list_item(row, evaluation_state=state, evaluation=evaluation)
        )

    return SavedJobListPage(items=items, next_cursor=next_cursor)


async def get_saved_job_detail(
    session: AsyncSession,
    job_id: str,
) -> SavedJobDetail:
    """Load one selected Job with validated extraction and latest evaluation.

    Unknown IDs raise :class:`SavedJobsServiceError` with ``JOB_NOT_FOUND``.
    Does not mutate rows or run external work. Does not finalize the caller's
    unit of work.
    """
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise SavedJobsServiceError(ERROR_JOB_NOT_FOUND, JOB_NOT_FOUND_MESSAGE)

    row = await saved_jobs_repo.get_by_id(session, job_id)
    if row is None:
        raise SavedJobsServiceError(ERROR_JOB_NOT_FOUND, JOB_NOT_FOUND_MESSAGE)

    shared = await _load_shared_context(session)
    context_hash = _context_hash_for_job(row, shared)
    state, evaluation = await _lookup_state(
        session,
        job_id=row.id,
        current_context_hash=context_hash,
    )
    compact = _list_item(row, evaluation_state=state, evaluation=evaluation)
    return SavedJobDetail(
        compact=compact,
        extraction=_validated_extraction(row),
        raw_content=row.raw_content if isinstance(row.raw_content, str) else None,
        latest_evaluation=_evaluation_view(
            evaluation, evaluation_state=state
        ),
    )


def _map_ingest_outcome(outcome: JobIngestOutcome | str) -> SaveIngestOutcomeLiteral:
    """Map internal created|returned|retried to public created|existing|retried."""
    if outcome == JOB_INGEST_OUTCOME_RETURNED:
        return "existing"
    if outcome == JOB_INGEST_OUTCOME_RETRIED:
        return "retried"
    if outcome == JOB_INGEST_OUTCOME_CREATED:
        return "created"
    # Defensive fallback for unexpected values — never invent success.
    return "created"


def _is_sole_public_http_url(content: str) -> bool:
    """True when *content* is exactly one valid public HTTP(S) URL."""
    stripped = content.strip()
    if stripped == "" or any(ch.isspace() for ch in stripped):
        return False
    if validate_url_scheme(stripped) is not None:
        return False
    try:
        parsed = urlparse(stripped)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    return True


def _resolve_source_kind(content: str) -> tuple[SourceKind, str]:
    """Sole public HTTP(S) URL → url; otherwise complete durable message text."""
    if _is_sole_public_http_url(content):
        return "url", content.strip()
    return "text", content


async def _authorize_zero_result_source(
    session: AsyncSession,
    source_message_id: str,
) -> str:
    """Return durable user message content when zero-result match_jobs authorizes.

    Fails before any ingestion when the message/run/tool relationship is invalid.
    Never returns message content in error text.
    """
    if not isinstance(source_message_id, str) or source_message_id.strip() == "":
        raise SavedJobsServiceError(
            ERROR_JD_SOURCE_NOT_RECOVERABLE,
            JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
        )

    message: ChatMessage | None = await messages_repo.get_by_id(
        session, source_message_id.strip()
    )
    if message is None:
        raise SavedJobsServiceError(
            ERROR_JD_SOURCE_NOT_RECOVERABLE,
            JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
        )
    if message.role != CHAT_MESSAGE_ROLE_USER:
        raise SavedJobsServiceError(
            ERROR_JD_SOURCE_NOT_RECOVERABLE,
            JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
        )
    content = message.content
    if not isinstance(content, str) or content.strip() == "":
        raise SavedJobsServiceError(
            ERROR_JD_SOURCE_NOT_RECOVERABLE,
            JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
        )

    run = await runs_repo.get_run_by_user_message_id(session, message.id)
    if run is None or run.state != AGENT_RUN_STATE_COMPLETED:
        raise SavedJobsServiceError(
            ERROR_JD_SOURCE_NOT_RECOVERABLE,
            JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
        )

    tools = await tools_repo.list_for_run_ids(session, [run.id])
    for tool_row in tools:
        if tool_row.tool_name != _MATCH_JOBS_NAME:
            continue
        if tool_row.status != TOOL_EXECUTION_STATUS_COMPLETED:
            continue
        if tool_row.result_json is None:
            continue
        try:
            tool_result = parse_tool_result(tool_row.result_json)
        except (ValidationError, ValueError, TypeError):
            continue
        if not tool_result.ok or tool_result.data is None:
            continue
        try:
            match_data = parse_match_jobs_result_data(tool_result.data)
        except (ValidationError, ValueError, TypeError):
            continue
        if match_data.count == 0:
            return content

    raise SavedJobsServiceError(
        ERROR_JD_SOURCE_NOT_RECOVERABLE,
        JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
    )


async def _project_job_item(
    session: AsyncSession,
    job_id: str,
) -> tuple[JobPost, SavedJobListItem, JobEvaluationView | None]:
    """Load Job row and compact list item with currentness projection."""
    row = await saved_jobs_repo.get_by_id(session, job_id)
    if row is None:
        raise SavedJobsServiceError(ERROR_JOB_NOT_FOUND, JOB_NOT_FOUND_MESSAGE)
    shared = await _load_shared_context(session)
    context_hash = _context_hash_for_job(row, shared)
    state, evaluation = await _lookup_state(
        session,
        job_id=row.id,
        current_context_hash=context_hash,
    )
    item = _list_item(row, evaluation_state=state, evaluation=evaluation)
    view = _evaluation_view(evaluation, evaluation_state=state)
    return row, item, view


def _job_is_scorable(row: JobPost) -> bool:
    return (
        row.processing_status == JOB_PROCESSING_STATUS_PROCESSED
        and row.jd_quality in _SCORABLE_QUALITIES
    )


async def save_and_evaluate_from_source(
    source_message_id: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    graph_driver: AsyncGraphDriver | None,
    invoker: StructuredJdInvoker,
    embedding_client: EmbeddingClient,
    normalizer: SkillNormalizer | None = None,
    url_fetcher: UrlFetcher | None = None,
    job_sync_fn: JobSyncFn | None = None,
) -> SaveAndEvaluateResponse:
    """Authorize durable zero-result source, ingest, then evaluate when scorable.

    Never accepts client JD text, never infers the latest chat message, and never
    claims evaluation success when scoring is unavailable. Does not open a SQLite
    transaction across ingestion or evaluation external work.
    """
    skill_normalizer = (
        normalizer if normalizer is not None else SkillNormalizer.production()
    )

    # 1) Durable source authorization — short session, no external work.
    async with session_scope(session_factory) as session:
        content = await _authorize_zero_result_source(session, source_message_id)

    kind, payload = _resolve_source_kind(content)

    # 2) Existing ingestion / exact-hash owner (own short transactions).
    try:
        if kind == "url":
            ingest = await ingest_url(
                payload,
                invoker=invoker,
                normalizer=skill_normalizer,
                embedding_client=embedding_client,
                session_factory=session_factory,
                url_fetcher=url_fetcher,
                graph_driver=graph_driver,
                job_sync_fn=job_sync_fn,
            )
        else:
            ingest = await ingest_raw_text(
                payload,
                invoker=invoker,
                normalizer=skill_normalizer,
                embedding_client=embedding_client,
                session_factory=session_factory,
                graph_driver=graph_driver,
                job_sync_fn=job_sync_fn,
            )
    except JdIngestionError as exc:
        logger.info("save-and-evaluate ingestion rejected code=%s", exc.code)
        raise SavedJobsServiceError(
            ERROR_JD_SOURCE_NOT_RECOVERABLE,
            JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
        ) from exc

    ingest_outcome = _map_ingest_outcome(ingest.outcome)

    # 3) Project Job; evaluate only when scorable; never false evaluation success.
    async with session_scope(session_factory) as session:
        row, job_item, _ = await _project_job_item(session, ingest.job_id)

    if not _job_is_scorable(row):
        code = ingest.failure_code or ERROR_JOB_NOT_SCORABLE
        return SaveAndEvaluateResponse(
            ingest_outcome=ingest_outcome,
            job=job_item,
            evaluation_outcome="unavailable",
            evaluation=None,
            code=code,
        )

    if graph_driver is None:
        return SaveAndEvaluateResponse(
            ingest_outcome=ingest_outcome,
            job=job_item,
            evaluation_outcome="unavailable",
            evaluation=None,
            code="NEO4J_UNAVAILABLE",
        )

    eval_result = await evaluate_job(
        session_factory=session_factory,
        job_id=ingest.job_id,
        graph_driver=cast(AsyncGraphReadDriver, graph_driver),
        embedding_client=embedding_client,
        normalizer=skill_normalizer,
    )

    if (
        not eval_result.ok
        or eval_result.evaluation is None
        or eval_result.outcome is None
    ):
        async with session_scope(session_factory) as session:
            _, job_item, _ = await _project_job_item(session, ingest.job_id)
        return SaveAndEvaluateResponse(
            ingest_outcome=ingest_outcome,
            job=job_item,
            evaluation_outcome="unavailable",
            evaluation=None,
            code=eval_result.error_code or ERROR_JOB_NOT_SCORABLE,
        )

    eval_outcome: SaveEvaluationOutcomeLiteral = eval_result.outcome
    async with session_scope(session_factory) as session:
        _, job_item, view = await _project_job_item(session, ingest.job_id)
    # Prefer the just-created/reused evaluation as current projection.
    current_view = evaluation_view_from_record(
        eval_result.evaluation,
        evaluation_state="current",
    )
    if view is not None and view.id == eval_result.evaluation.id:
        current_view = view if view.evaluation_state == "current" else current_view

    return SaveAndEvaluateResponse(
        ingest_outcome=ingest_outcome,
        job=job_item.model_copy(
            update={
                "evaluation_state": "current",
                "latest_score": eval_result.evaluation.result.final_score,
            }
        ),
        evaluation_outcome=eval_outcome,
        evaluation=current_view,
        code=None,
    )


async def evaluate_saved_job(
    job_id: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    graph_driver: AsyncGraphDriver | None,
    embedding_client: EmbeddingClient,
    normalizer: SkillNormalizer | None = None,
) -> EvaluateJobResponse:
    """Explicit current-context evaluation via the accepted evaluation owner."""
    skill_normalizer = (
        normalizer if normalizer is not None else SkillNormalizer.production()
    )
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise SavedJobsServiceError(ERROR_JOB_NOT_FOUND, JOB_NOT_FOUND_MESSAGE)
    if graph_driver is None:
        raise SavedJobsServiceError(
            "NEO4J_UNAVAILABLE",
            "Neo4j is unavailable for job evaluation.",
        )

    result = await evaluate_job(
        session_factory=session_factory,
        job_id=job_id.strip(),
        graph_driver=cast(AsyncGraphReadDriver, graph_driver),
        embedding_client=embedding_client,
        normalizer=skill_normalizer,
    )
    if not result.ok or result.evaluation is None or result.outcome is None:
        code = result.error_code or ERROR_JOB_NOT_SCORABLE
        message = result.message or "Evaluation could not be completed."
        # Safe summaries only — evaluation owner already avoids raw JD/SQL.
        raise SavedJobsServiceError(code, message)

    async with session_scope(session_factory) as session:
        _, job_item, _ = await _project_job_item(session, job_id.strip())

    view = evaluation_view_from_record(
        result.evaluation,
        evaluation_state="current",
    )
    return EvaluateJobResponse(
        outcome=result.outcome,
        job=job_item.model_copy(
            update={
                "evaluation_state": "current",
                "latest_score": result.evaluation.result.final_score,
            }
        ),
        evaluation=view,
    )


async def delete_saved_job(
    job_id: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    graph_driver: AsyncGraphDriver | None,
    graph_delete_fn: object | None = None,
    graph_absent_fn: object | None = None,
) -> None:
    """Complete Job deletion via the accepted graph-first coordinator."""
    if graph_driver is None:
        raise SavedJobsServiceError(
            ERROR_JOB_DELETE_GRAPH_FAILED,
            "Exact Job graph deletion failed; SQLite Job and evaluations were "
            "preserved. Restore Neo4j connectivity and retry DELETE.",
        )
    try:
        kwargs: dict[str, object] = {
            "driver": graph_driver,
            "session_factory": session_factory,
        }
        if graph_delete_fn is not None:
            kwargs["graph_delete_fn"] = graph_delete_fn
        if graph_absent_fn is not None:
            kwargs["graph_absent_fn"] = graph_absent_fn
        await delete_job(job_id, **kwargs)  # type: ignore[arg-type]
    except JobDeleteError as exc:
        code = (
            ERROR_JOB_NOT_FOUND
            if exc.code == DELETE_JOB_NOT_FOUND
            else exc.code
        )
        raise SavedJobsServiceError(code, exc.message) from exc


async def reextract_saved_job(
    job_id: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    invoker: StructuredJdInvoker,
    embedding_client: EmbeddingClient,
    graph_driver: AsyncGraphDriver | None = None,
    normalizer: SkillNormalizer | None = None,
    job_sync_fn: JobSyncFn | None = None,
) -> ReextractJobResponse:
    """Explicit same-ID re-extraction via the accepted (02A) coordinator.

    Does not accept client replacement data. Does not call evaluation or
    matching. Projects one current saved-list row after SQLite commit; graph
    failure remains HTTP success with coupled ``sync_ok``/code/rebuild fields.
    """
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise SavedJobsServiceError(ERROR_JOB_NOT_FOUND, JOB_NOT_FOUND_MESSAGE)
    jid = job_id.strip()
    skill_normalizer = (
        normalizer if normalizer is not None else SkillNormalizer.production()
    )

    try:
        result = await reextract_job(
            jid,
            invoker=invoker,
            normalizer=skill_normalizer,
            embedding_client=embedding_client,
            session_factory=session_factory,
            graph_driver=graph_driver,
            job_sync_fn=job_sync_fn,
        )
    except JobReextractError as exc:
        logger.info(
            "saved-job reextract failed job_id=%s code=%s",
            jid,
            exc.code,
        )
        raise SavedJobsServiceError(exc.code, exc.message) from exc

    async with session_scope(session_factory) as session:
        _, job_item, _ = await _project_job_item(session, result.job_id)

    logger.info(
        "saved-job reextract ok job_id=%s sync_ok=%s",
        result.job_id,
        result.sync_ok,
    )
    return ReextractJobResponse(
        outcome="updated",
        job=job_item,
        sync_ok=result.sync_ok,
        code=result.sync_code,
        rebuild_instruction=result.rebuild_instruction,
    )


__all__ = [
    "ERROR_ACTIVE_PROFILE_REQUIRED",
    "ERROR_JD_SOURCE_NOT_RECOVERABLE",
    "ERROR_JOB_DELETE_GRAPH_FAILED",
    "ERROR_JOB_NOT_FOUND",
    "ERROR_JOB_NOT_SCORABLE",
    "ERROR_JOB_REEXTRACT_CONFLICT",
    "JD_SOURCE_NOT_RECOVERABLE_MESSAGE",
    "JOB_NOT_FOUND_MESSAGE",
    "SavedJobsServiceError",
    "delete_saved_job",
    "evaluate_saved_job",
    "get_saved_job_detail",
    "get_saved_jobs_page",
    "reextract_saved_job",
    "save_and_evaluate_from_source",
]
