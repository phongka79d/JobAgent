"""Read-only matching orchestration (Plan 6 03A).

Composes accepted Batch01/02 owners in the exact consistency-first order:
approved profile precondition, revision consistency, Candidate embed/validate,
top-50 retrieval, deterministic scoring/explanation, then top-limit projection.

This service persists nothing, repairs no graph data, and returns either the
strict compact Batch02 response or one stable truthful failure with zero
results. Provider, Neo4j, and SQLite I/O never share an open SQLite
transaction with each other beyond the short scopes required by delegated
owners.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_INVALID_RESPONSE,
    EmbeddingAdapterError,
)
from app.db.seed import empty_job_preferences_document
from app.db.session import session_scope
from app.graph.consistency import (
    NEO4J_REBUILD_REQUIRED,
    NEO4J_UNAVAILABLE,
    REBUILD_REQUIRED_INSTRUCTION,
    AsyncGraphReadDriver,
    GraphConsistencyResult,
    check_graph_revision_consistency,
)
from app.graph.retrieval import JobRetrievalError, retrieve_job_candidates
from app.repositories import profiles as profiles_repo
from app.schemas.embeddings import EmbeddingVectorError, validate_finite_vector
from app.schemas.matching import MatchJobsResultData
from app.schemas.profile import (
    CandidateProfile,
    JobPreferences,
    parse_candidate_profile,
    parse_job_preferences,
)
from app.services.embedding_text import build_candidate_embedding_text_v1
from app.services.job_projection import EmbeddingClient
from app.services.match_scoring import score_retrieved_candidates
from app.services.profile_drafts import ERROR_ACTIVE_PROFILE_MISSING
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)

DEFAULT_MATCH_LIMIT: int = 10
MATCH_LIMIT_MIN: int = 1
MATCH_LIMIT_MAX: int = 10

NO_PROFILE_MATCH_MESSAGE: str = (
    "Upload and approve a CV before matching. Matching requires an active "
    "approved candidate profile."
)


@dataclass(frozen=True, slots=True)
class MatchJobsServiceResult:
    """Stable matching outcome: compact data and optional failure guidance.

    Failures always carry zero results in ``data`` (``count == 0``). Success
    may also return an empty result list when the scorable corpus is empty.
    """

    ok: bool
    error_code: str | None
    message: str
    rebuild_instruction: str | None
    data: MatchJobsResultData


def _empty_data(limit: int) -> MatchJobsResultData:
    return MatchJobsResultData(results=[], count=0, limit=limit)


def _failure(
    *,
    limit: int,
    error_code: str,
    message: str,
    rebuild_instruction: str | None = None,
) -> MatchJobsServiceResult:
    return MatchJobsServiceResult(
        ok=False,
        error_code=error_code,
        message=message,
        rebuild_instruction=rebuild_instruction,
        data=_empty_data(limit),
    )


def _success(data: MatchJobsResultData) -> MatchJobsServiceResult:
    return MatchJobsServiceResult(
        ok=True,
        error_code=None,
        message="Matching completed.",
        rebuild_instruction=None,
        data=data,
    )


def _validate_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError(
            f"limit must be an int in {MATCH_LIMIT_MIN}..{MATCH_LIMIT_MAX}"
        )
    if limit < MATCH_LIMIT_MIN or limit > MATCH_LIMIT_MAX:
        raise ValueError(
            f"limit must be in {MATCH_LIMIT_MIN}..{MATCH_LIMIT_MAX}, got {limit!r}"
        )


async def _load_approved_profile_and_preferences(
    session: AsyncSession,
) -> tuple[CandidateProfile, JobPreferences] | None:
    """Load approved profile/preferences only (never a pending draft)."""
    profile_row = await profiles_repo.get_active_profile(session)
    if profile_row is None:
        return None
    profile = parse_candidate_profile(profile_row.profile_json)

    prefs_row = await profiles_repo.get_job_preferences(session)
    if prefs_row is None:
        preferences = parse_job_preferences(empty_job_preferences_document())
    else:
        preferences = parse_job_preferences(prefs_row.preferences_json)
    return profile, preferences


def _consistency_failure(
    result: GraphConsistencyResult,
    *,
    limit: int,
) -> MatchJobsServiceResult:
    code = result.error_code or NEO4J_REBUILD_REQUIRED
    return _failure(
        limit=limit,
        error_code=code,
        message=result.message,
        rebuild_instruction=result.rebuild_instruction,
    )


async def match_jobs(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    graph_driver: AsyncGraphReadDriver,
    embedding_client: EmbeddingClient,
    normalizer: SkillNormalizer | None = None,
    limit: int = DEFAULT_MATCH_LIMIT,
) -> MatchJobsServiceResult:
    """Run consistency-first read-only matching and return compact results.

    Call order is fixed:

    1. Load approved profile/preferences; reject no-profile before provider work.
    2. Run revision consistency (zero partial results on stale/unavailable).
    3. Build, embed, and validate Candidate v1 outside SQLite transactions.
    4. Retrieve up to 50 revision-consistent Jobs.
    5. Score/explain deterministically and project top ``limit`` (default 10).

    During a pending profile replacement only the approved profile/preferences
    are used. The service never writes SQLite, Neo4j, or a score cache.
    """
    _validate_limit(limit)
    skill_normalizer = (
        normalizer if normalizer is not None else SkillNormalizer.production()
    )

    # 1) Profile precondition — short SQLite scope only (no provider/Neo4j).
    async with session_scope(session_factory) as session:
        loaded = await _load_approved_profile_and_preferences(session)
    if loaded is None:
        return _failure(
            limit=limit,
            error_code=ERROR_ACTIVE_PROFILE_MISSING,
            message=NO_PROFILE_MATCH_MESSAGE,
        )
    profile, preferences = loaded

    # 2) Revision consistency — delegated owner; zero results on failure.
    async with session_scope(session_factory) as session:
        consistency = await check_graph_revision_consistency(
            session, graph_driver
        )
    if not consistency.is_consistent:
        return _consistency_failure(consistency, limit=limit)

    # 3) Candidate embed + validate — outside any SQLite session/transaction.
    candidate_text = build_candidate_embedding_text_v1(profile, preferences)
    try:
        raw_vector = embedding_client.embed_text(candidate_text)
        candidate_vector = validate_finite_vector(raw_vector)
    except EmbeddingAdapterError as exc:
        logger.info("match_jobs embedding failed code=%s", exc.code)
        return _failure(
            limit=limit,
            error_code=exc.code,
            message="Candidate embedding provider failed; retry matching later.",
        )
    except EmbeddingVectorError as exc:
        logger.info("match_jobs embedding invalid code=%s", exc.code)
        return _failure(
            limit=limit,
            error_code=FAILURE_EMBEDDING_INVALID_RESPONSE,
            message="Candidate embedding response failed locked contract validation.",
        )

    # 4) Top-50 retrieval + SQLite hydration — short session around owner call.
    try:
        async with session_scope(session_factory) as session:
            retrieved = await retrieve_job_candidates(
                session,
                graph_driver,
                candidate_vector=candidate_vector,
                scorable_job_ids=consistency.scorable_job_ids,
            )
    except JobRetrievalError:
        logger.info("match_jobs retrieval failed; treating as rebuild required")
        return _failure(
            limit=limit,
            error_code=NEO4J_REBUILD_REQUIRED,
            message=(
                "Neo4j vector retrieval is not consistent with SQLite "
                "scorable Jobs."
            ),
            rebuild_instruction=REBUILD_REQUIRED_INSTRUCTION,
        )
    except Exception:
        logger.info("match_jobs retrieval graph unavailable")
        return _failure(
            limit=limit,
            error_code=NEO4J_UNAVAILABLE,
            message="Neo4j is unavailable for job vector retrieval.",
        )

    # 5) Pure scoring / explanation / top-limit projection (no I/O).
    data = score_retrieved_candidates(
        profile=profile,
        preferences=preferences,
        candidates=retrieved,
        normalizer=skill_normalizer,
        limit=limit,
    )
    return _success(data)


__all__ = [
    "DEFAULT_MATCH_LIMIT",
    "MATCH_LIMIT_MAX",
    "MATCH_LIMIT_MIN",
    "NO_PROFILE_MATCH_MESSAGE",
    "ERROR_ACTIVE_PROFILE_MISSING",
    "MatchJobsServiceResult",
    "match_jobs",
]
