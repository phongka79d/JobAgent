"""Matching pipeline orchestration for the ``match_jobs`` tool.

Owns profile load, embed, retrieve, score/rank, and derived score-cache writes.
Tool input schema and LangChain wrapper live in ``match_jobs`` so each module
stays under the focused 300-line ceiling without duplicating formulas.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Final
from uuid import UUID

from app.db.session import DatabaseSessionManager
from app.repositories.job_posts import JobPostRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.matching import (
    MAX_MATCH_RESULTS,
    MAX_RANK_INPUTS,
    CandidateEmbeddingError,
    MatchResult,
    MatchResultCollection,
)
from app.schemas.preferences import JobPreferences
from app.services.embeddings import EmbeddingsClientLike, JobEmbeddingService
from app.services.matching import (
    RankedJobCandidate,
    rank_match_results,
    score_job_components,
)
from app.services.matching_text import embed_candidate
from app.services.retrieval import (
    MAX_RELATED_SKILL_KEYS,
    RetrievalCandidate,
    RetrievalError,
    RetrievalGraphClient,
    query_verified_related_edges,
    retrieve_top_job_candidates,
)
from app.services.skill_matching import (
    VerifiedRelatedEdge,
    compute_skill_component,
)

DEFAULT_MATCH_LIMIT: Final[int] = MAX_MATCH_RESULTS

PROFILE_REQUIRED_GUIDANCE: Final[str] = (
    "Upload a CV and approve a Candidate Profile before matching jobs."
)


def tool_error(code: str) -> str:
    """Sanitized code-only tool error payload."""
    return f'ERROR:{{"code":"{code}","ok":false}}'


def _profile_required_payload(*, limit: int) -> str:
    payload = {
        "ok": True,
        "status": "profile_required",
        "code": "PROFILE_REQUIRED",
        "guidance": PROFILE_REQUIRED_GUIDANCE,
        "count": 0,
        "limit": limit,
        "results": [],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _success_payload(
    collection: MatchResultCollection,
    *,
    limit: int,
) -> str:
    results = [item.model_dump(mode="json") for item in collection.results]
    payload = {
        "ok": True,
        "status": "matched",
        "count": len(results),
        "limit": limit,
        "contract_version": collection.contract_version,
        "seed_config_version": collection.seed_config_version,
        "results": results,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _collect_related_skill_keys(
    profile: CandidateProfile,
    candidates: Sequence[RetrievalCandidate],
) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        key = raw.strip()
        if not key or key in seen:
            return
        if len(keys) >= MAX_RELATED_SKILL_KEYS:
            return
        seen.add(key)
        keys.append(key)

    for skill in profile.skills:
        if skill.excluded:
            continue
        _add(skill.skill.canonical_key)
    for cand in candidates:
        for job_skill in (
            *cand.extraction.required_skills,
            *cand.extraction.preferred_skills,
        ):
            _add(job_skill.skill.canonical_key)
            if len(keys) >= MAX_RELATED_SKILL_KEYS:
                return keys
    return keys


def _score_candidates(
    *,
    profile: CandidateProfile,
    preferences: JobPreferences,
    candidates: Sequence[RetrievalCandidate],
    related_edges: Sequence[VerifiedRelatedEdge],
) -> list[RankedJobCandidate]:
    ranked: list[RankedJobCandidate] = []
    for cand in candidates:
        extraction = cand.extraction
        skill_component = compute_skill_component(
            required_skills=extraction.required_skills,
            preferred_skills=extraction.preferred_skills,
            candidate_skills=profile.skills,
            related_edges=related_edges,
        )
        skill_score = (
            skill_component.skill_score if skill_component.available else None
        )
        work_mode = extraction.work_mode
        work_mode_str = (
            work_mode.value if work_mode is not None and hasattr(work_mode, "value") else None
        )
        if work_mode_str is None and isinstance(work_mode, str):
            work_mode_str = work_mode
        quality = extraction.jd_quality
        breakdown = score_job_components(
            semantic_similarity=cand.semantic_similarity,
            skill_score=skill_score,
            job_seniority=extraction.seniority,
            target_seniorities=preferences.target_seniority,
            candidate_years=profile.total_experience_years,
            min_experience_years=extraction.min_experience_years,
            job_location=extraction.location,
            preferred_locations=preferences.preferred_locations,
            job_work_mode=extraction.work_mode,
            acceptable_work_modes=preferences.acceptable_work_modes,
            quality=quality,
        )
        ranked.append(
            RankedJobCandidate(
                job_id=cand.job_id,
                title=extraction.title,
                company=extraction.company,
                location=extraction.location,
                work_mode=work_mode_str,
                source_url=cand.record.source_url,
                breakdown=breakdown,
                skill_component=skill_component,
            )
        )
    return ranked


class MatchJobsToolService:
    """Thin orchestration wrapper over profile, embed, retrieve, score, cache."""

    def __init__(
        self,
        database: DatabaseSessionManager,
        graph_client: RetrievalGraphClient,
        embedding_service: JobEmbeddingService,
        *,
        embeddings_client: EmbeddingsClientLike | None = None,
    ) -> None:
        self._database = database
        self._graph = graph_client
        self._embedding_service = embedding_service
        self._embeddings_client = embeddings_client
        self.embed_calls: int = 0
        self.graph_retrieve_calls: int = 0
        self.cache_write_calls: int = 0

    async def execute(
        self,
        *,
        limit: int | None = None,
        saved_job_ids: list[UUID] | None = None,
    ) -> str:
        effective_limit = DEFAULT_MATCH_LIMIT if limit is None else limit
        if (
            not isinstance(effective_limit, int)
            or isinstance(effective_limit, bool)
            or effective_limit < 1
        ):
            return tool_error("MATCH_JOBS_INVALID_INPUT")
        if effective_limit > MAX_MATCH_RESULTS:
            effective_limit = MAX_MATCH_RESULTS

        try:
            async with self._database.session_scope() as session:
                profile_record = await ProfileRepository(session).get()
                preferences = await PreferencesRepository(session).get()
        except Exception:
            return tool_error("MATCH_JOBS_FAILED")

        if profile_record is None:
            # Guidance only — zero embed / graph / cache side effects.
            return _profile_required_payload(limit=effective_limit)

        profile = profile_record.profile
        prefs = preferences if preferences is not None else JobPreferences()

        try:
            self.embed_calls += 1
            embedded = embed_candidate(
                profile,
                embedding_service=self._embedding_service,
                preferences=prefs,
                client=self._embeddings_client,
            )
        except CandidateEmbeddingError as exc:
            return tool_error(exc.code.value.upper())
        except Exception:
            return tool_error("MATCH_JOBS_EMBED_FAILED")

        try:
            self.graph_retrieve_calls += 1
            candidates = await retrieve_top_job_candidates(
                query_vector=embedded.values,
                database=self._database,
                graph_client=self._graph,
                embedding_service=self._embedding_service,
                saved_job_ids=saved_job_ids,
                retry_outbox=True,
                limit=MAX_RANK_INPUTS,
            )
        except RetrievalError as exc:
            return tool_error(exc.code.value.upper())
        except Exception:
            return tool_error("MATCH_JOBS_RETRIEVAL_FAILED")

        try:
            related_keys = _collect_related_skill_keys(profile, candidates)
            related_edges = await query_verified_related_edges(
                self._graph,
                related_keys,
            )
            ranked = _score_candidates(
                profile=profile,
                preferences=prefs,
                candidates=candidates,
                related_edges=related_edges,
            )
            collection = rank_match_results(ranked, limit=effective_limit)
        except RetrievalError as exc:
            return tool_error(exc.code.value.upper())
        except Exception:
            return tool_error("MATCH_JOBS_SCORE_FAILED")

        try:
            await self._persist_score_caches(collection.results)
        except Exception:
            # Cache is derived; ranking already succeeded — do not claim failure
            # after a successful match, but never leave partial success opaque.
            return tool_error("MATCH_JOBS_CACHE_FAILED")

        return _success_payload(collection, limit=effective_limit)

    async def _persist_score_caches(self, results: Sequence[MatchResult]) -> None:
        if not results:
            return
        async with self._database.session_scope() as session:
            jobs = JobPostRepository(session)
            for item in results:
                self.cache_write_calls += 1
                await jobs.set_score_cache(item.job_id, item)


__all__ = [
    "DEFAULT_MATCH_LIMIT",
    "PROFILE_REQUIRED_GUIDANCE",
    "MatchJobsToolService",
    "tool_error",
]
