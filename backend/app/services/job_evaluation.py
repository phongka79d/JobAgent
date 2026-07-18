"""Exact saved-Job evaluation orchestration (Plan 10 / Master §17.5).

Composes accepted context, repository, consistency, exact retrieval, and pure
scoring owners. Call order:

1. Resolve active approved profile/preferences, approved CV source, Job, and
   current context from SQLite; reject preconditions before provider work.
2. Return a validated current row before embed / graph scoring / explanations.
3. Full Candidate/Job consistency gate (no repair).
4. Embed Candidate once and exact-read + shared-score outside SQLite txs.
5. Revalidate context; on drift discard and return EVALUATION_CONTEXT_CHANGED.
6. Short insert transaction; uniqueness race reloads the committed winner.

Never holds SQLite open across provider or Neo4j work. Never auto-evaluates on
CV/profile/preference changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_INVALID_RESPONSE,
    EmbeddingAdapterError,
)
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_PROCESSED,
)
from app.db.session import session_scope
from app.graph.consistency import (
    NEO4J_REBUILD_REQUIRED,
    NEO4J_UNAVAILABLE,
    REBUILD_REQUIRED_INSTRUCTION,
    AsyncGraphReadDriver,
    GraphConsistencyResult,
    check_graph_revision_consistency,
)
from app.graph.retrieval import JobRetrievalError, retrieve_exact_job_candidate
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import job_evaluations as eval_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as profiles_repo
from app.schemas.embeddings import EmbeddingVectorError, validate_finite_vector
from app.schemas.job_evaluations import (
    JobEvaluationRecord,
    record_from_row,
    validate_match_result_payload,
)
from app.schemas.profile import (
    CandidateProfile,
    JobPreferences,
    parse_candidate_profile,
    parse_job_preferences,
)
from app.services.embedding_text import build_candidate_embedding_text_v1
from app.services.evaluation_context import (
    MATCHING_CONTRACT_VERSION,
    EvaluationContextFacts,
    evaluation_context_hash,
)
from app.services.jd_ingestion import EmbeddingClient
from app.services.match_scoring import project_single_job_match
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)

ERROR_ACTIVE_PROFILE_REQUIRED: str = "ACTIVE_PROFILE_REQUIRED"
ERROR_JOB_NOT_FOUND: str = "JOB_NOT_FOUND"
ERROR_JOB_NOT_SCORABLE: str = "JOB_NOT_SCORABLE"
ERROR_EVALUATION_CONTEXT_CHANGED: str = "EVALUATION_CONTEXT_CHANGED"
ERROR_INVALID_MATCH_RESULT: str = "INVALID_MATCH_RESULT"

EvaluationOutcome = Literal["created", "reused"]

_SCORABLE_QUALITIES = frozenset({JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL})

NO_PROFILE_EVAL_MESSAGE: str = (
    "Upload and approve a CV before evaluating a Job. Evaluation requires an "
    "active approved candidate profile and CV source."
)
JOB_NOT_FOUND_MESSAGE: str = "The requested Job was not found."
JOB_NOT_SCORABLE_MESSAGE: str = (
    "The requested Job is not scorable. Only processed full or partial Jobs "
    "can be evaluated."
)
CONTEXT_CHANGED_MESSAGE: str = (
    "The evaluation context changed during scoring. Discarded the candidate "
    "result; retry evaluation with the current context."
)
INVALID_RESULT_MESSAGE: str = (
    "Computed match result failed validation and was not persisted."
)


@dataclass(frozen=True, slots=True)
class JobEvaluationServiceResult:
    """Stable evaluation outcome: created/reused row or a safe failure."""

    ok: bool
    outcome: EvaluationOutcome | None
    error_code: str | None
    message: str
    rebuild_instruction: str | None
    evaluation: JobEvaluationRecord | None


@dataclass(frozen=True, slots=True)
class _ResolvedContext:
    """Server-loaded facts for one evaluation attempt."""

    job_id: str
    profile: CandidateProfile
    preferences: JobPreferences
    facts: EvaluationContextFacts
    context_hash: str


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _failure(
    *,
    error_code: str,
    message: str,
    rebuild_instruction: str | None = None,
) -> JobEvaluationServiceResult:
    return JobEvaluationServiceResult(
        ok=False,
        outcome=None,
        error_code=error_code,
        message=message,
        rebuild_instruction=rebuild_instruction,
        evaluation=None,
    )


def _success(
    *,
    outcome: EvaluationOutcome,
    evaluation: JobEvaluationRecord,
) -> JobEvaluationServiceResult:
    return JobEvaluationServiceResult(
        ok=True,
        outcome=outcome,
        error_code=None,
        message=(
            "Evaluation reused the current context result."
            if outcome == "reused"
            else "Evaluation created for the current context."
        ),
        rebuild_instruction=None,
        evaluation=evaluation,
    )


def _record(row: Any) -> JobEvaluationRecord:
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


def _consistency_failure(
    result: GraphConsistencyResult,
) -> JobEvaluationServiceResult:
    code = result.error_code or NEO4J_REBUILD_REQUIRED
    return _failure(
        error_code=code,
        message=result.message,
        rebuild_instruction=result.rebuild_instruction,
    )


async def _resolve_context(
    session: AsyncSession,
    *,
    job_id: str,
) -> _ResolvedContext | JobEvaluationServiceResult:
    """Load SQLite preconditions and current evaluation context facts."""
    if not isinstance(job_id, str) or job_id.strip() == "":
        return _failure(
            error_code=ERROR_JOB_NOT_FOUND,
            message=JOB_NOT_FOUND_MESSAGE,
        )

    profile_row = await profiles_repo.get_active_profile(session)
    if profile_row is None:
        return _failure(
            error_code=ERROR_ACTIVE_PROFILE_REQUIRED,
            message=NO_PROFILE_EVAL_MESSAGE,
        )

    prefs_row = await profiles_repo.get_job_preferences(session)
    if prefs_row is None:
        return _failure(
            error_code=ERROR_ACTIVE_PROFILE_REQUIRED,
            message=NO_PROFILE_EVAL_MESSAGE,
        )

    attachment_id = profile_row.active_attachment_id
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        return _failure(
            error_code=ERROR_ACTIVE_PROFILE_REQUIRED,
            message=NO_PROFILE_EVAL_MESSAGE,
        )

    cv_doc = await cv_doc_repo.get_document(session, attachment_id)
    if cv_doc is None or not isinstance(cv_doc.source_hash, str) or (
        cv_doc.source_hash.strip() == ""
    ):
        return _failure(
            error_code=ERROR_ACTIVE_PROFILE_REQUIRED,
            message=NO_PROFILE_EVAL_MESSAGE,
        )

    job = await jobs_repo.get_by_id(session, job_id)
    if job is None:
        return _failure(
            error_code=ERROR_JOB_NOT_FOUND,
            message=JOB_NOT_FOUND_MESSAGE,
        )

    if (
        job.processing_status != JOB_PROCESSING_STATUS_PROCESSED
        or job.jd_quality not in _SCORABLE_QUALITIES
    ):
        return _failure(
            error_code=ERROR_JOB_NOT_SCORABLE,
            message=JOB_NOT_SCORABLE_MESSAGE,
        )

    profile = parse_candidate_profile(profile_row.profile_json)
    preferences = parse_job_preferences(prefs_row.preferences_json)
    facts = EvaluationContextFacts(
        job_id=job.id,
        job_revision=_as_aware_utc(job.updated_at),
        active_attachment_id=attachment_id,
        cv_source_hash=cv_doc.source_hash,
        profile_revision=_as_aware_utc(profile_row.updated_at),
        preferences_revision=_as_aware_utc(prefs_row.updated_at),
        matching_contract_version=MATCHING_CONTRACT_VERSION,
    )
    return _ResolvedContext(
        job_id=job.id,
        profile=profile,
        preferences=preferences,
        facts=facts,
        context_hash=evaluation_context_hash(facts),
    )


async def evaluate_job(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    job_id: str,
    graph_driver: AsyncGraphReadDriver,
    embedding_client: EmbeddingClient,
    normalizer: SkillNormalizer | None = None,
) -> JobEvaluationServiceResult:
    """Evaluate one saved Job for the current server-derived context.

    Same ``(job_id, evaluation_context_hash)`` returns the existing row with
    zero provider, graph-scoring, or explanation work. A new context runs the
    full consistency gate, embeds once, exact-scores outside SQLite
    transactions, revalidates context, then persists in a short transaction.
    """
    skill_normalizer = (
        normalizer if normalizer is not None else SkillNormalizer.production()
    )

    # 1) Preconditions + current context — short SQLite scope only.
    async with session_scope(session_factory) as session:
        resolved = await _resolve_context(session, job_id=job_id)
        if isinstance(resolved, JobEvaluationServiceResult):
            return resolved

        existing = await eval_repo.get_by_job_context(
            session,
            job_id=resolved.job_id,
            evaluation_context_hash=resolved.context_hash,
        )
        if existing is not None:
            # 2) Current reuse — before embed / graph / explanation.
            return _success(outcome="reused", evaluation=_record(existing))

        # Snapshot facts for the compute path (no open session after this).
        profile = resolved.profile
        preferences = resolved.preferences
        facts = resolved.facts
        context_hash = resolved.context_hash
        resolved_job_id = resolved.job_id

    # 3) Full Candidate/Job consistency gate — no repair.
    async with session_scope(session_factory) as session:
        consistency = await check_graph_revision_consistency(
            session, graph_driver
        )
    if not consistency.is_consistent:
        return _consistency_failure(consistency)

    if resolved_job_id not in consistency.scorable_job_ids:
        # Consistent corpus does not include this Job (unscorable or absent).
        return _failure(
            error_code=ERROR_JOB_NOT_SCORABLE,
            message=JOB_NOT_SCORABLE_MESSAGE,
        )

    # 4a) Candidate embed + validate — outside any SQLite session/transaction.
    candidate_text = build_candidate_embedding_text_v1(profile, preferences)
    try:
        raw_vector = embedding_client.embed_text(candidate_text)
        candidate_vector = validate_finite_vector(raw_vector)
    except EmbeddingAdapterError as exc:
        logger.info("evaluate_job embedding failed code=%s", exc.code)
        return _failure(
            error_code=exc.code,
            message="Candidate embedding provider failed; retry evaluation later.",
        )
    except EmbeddingVectorError as exc:
        logger.info("evaluate_job embedding invalid code=%s", exc.code)
        return _failure(
            error_code=FAILURE_EMBEDDING_INVALID_RESPONSE,
            message=(
                "Candidate embedding response failed locked contract validation."
            ),
        )

    # 4b) Exact Job semantic read + SQLite hydration — short session only.
    try:
        async with session_scope(session_factory) as session:
            retrieved = await retrieve_exact_job_candidate(
                session,
                graph_driver,
                job_id=resolved_job_id,
                candidate_vector=candidate_vector,
                scorable_job_ids=consistency.scorable_job_ids,
            )
    except JobRetrievalError:
        logger.info(
            "evaluate_job exact retrieval failed; treating as rebuild required"
        )
        return _failure(
            error_code=NEO4J_REBUILD_REQUIRED,
            message=(
                "Neo4j exact Job retrieval is not consistent with SQLite "
                "scorable Jobs."
            ),
            rebuild_instruction=REBUILD_REQUIRED_INSTRUCTION,
        )
    except Exception:
        logger.info("evaluate_job exact retrieval graph unavailable")
        return _failure(
            error_code=NEO4J_UNAVAILABLE,
            message="Neo4j is unavailable for exact Job semantic retrieval.",
        )

    # 4c) Pure shared scoring / explanation (no I/O).
    try:
        match_result = project_single_job_match(
            profile=profile,
            preferences=preferences,
            job=retrieved,
            normalizer=skill_normalizer,
        )
        payload: Any
        if hasattr(match_result, "model_dump"):
            payload = match_result.model_dump(mode="json")
        else:
            payload = match_result
        validated = validate_match_result_payload(payload)
    except ValidationError:
        logger.info("evaluate_job computed MatchResult failed validation")
        return _failure(
            error_code=ERROR_INVALID_MATCH_RESULT,
            message=INVALID_RESULT_MESSAGE,
        )
    except Exception:
        logger.info("evaluate_job scoring failed")
        return _failure(
            error_code=ERROR_INVALID_MATCH_RESULT,
            message=INVALID_RESULT_MESSAGE,
        )

    if validated.job_id != resolved_job_id:
        return _failure(
            error_code=ERROR_INVALID_MATCH_RESULT,
            message=INVALID_RESULT_MESSAGE,
        )

    # 5) Revalidate exact context before persistence.
    async with session_scope(session_factory) as session:
        rechecked = await _resolve_context(session, job_id=resolved_job_id)
        if isinstance(rechecked, JobEvaluationServiceResult):
            # Preconditions vanished mid-flight — treat as context change.
            return _failure(
                error_code=ERROR_EVALUATION_CONTEXT_CHANGED,
                message=CONTEXT_CHANGED_MESSAGE,
            )
        if rechecked.context_hash != context_hash:
            return _failure(
                error_code=ERROR_EVALUATION_CONTEXT_CHANGED,
                message=CONTEXT_CHANGED_MESSAGE,
            )
        # Another concurrent writer may have already stored the current row.
        existing_after = await eval_repo.get_by_job_context(
            session,
            job_id=resolved_job_id,
            evaluation_context_hash=context_hash,
        )
        if existing_after is not None:
            return _success(
                outcome="reused", evaluation=_record(existing_after)
            )

        # 6) Short insert transaction; uniqueness race reloads winner.
        row, created = await eval_repo.insert_evaluation(
            session,
            job_id=facts.job_id,
            active_attachment_id=facts.active_attachment_id,
            evaluation_context_hash=context_hash,
            job_revision=facts.job_revision,
            profile_revision=facts.profile_revision,
            preferences_revision=facts.preferences_revision,
            cv_source_hash=facts.cv_source_hash,
            matching_contract_version=facts.matching_contract_version,
            result=validated,
        )
        return _success(
            outcome="created" if created else "reused",
            evaluation=_record(row),
        )


__all__ = [
    "ERROR_ACTIVE_PROFILE_REQUIRED",
    "ERROR_EVALUATION_CONTEXT_CHANGED",
    "ERROR_INVALID_MATCH_RESULT",
    "ERROR_JOB_NOT_FOUND",
    "ERROR_JOB_NOT_SCORABLE",
    "EvaluationOutcome",
    "JobEvaluationServiceResult",
    "evaluate_job",
]
