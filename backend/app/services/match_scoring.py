"""Pure single-Job and multi-Job scoring/projection (no I/O).

Shared by top-N matching and exact Job evaluation. Builds one component map
and one explanation projection from already-hydrated Job facts plus a semantic
similarity score. Provider, graph, and SQLite work stay outside this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from app.schemas.jobs import JobPostExtraction
from app.schemas.matching import MatchJobsResultData, MatchResult
from app.schemas.profile import CandidateProfile, JobPreferences
from app.services.match_components import (
    MatchScoreComponents,
    compute_experience_score,
    compute_location_score,
    compute_seniority_score,
    compute_work_mode_score,
    rank_match_candidates,
    score_match_candidate,
)
from app.services.match_explanations import (
    MatchExplanationInput,
    project_match_jobs_result,
    project_match_result,
)
from app.services.skill_matching import SkillCoverageResult, compute_skill_coverage
from app.services.skill_normalization import SkillNormalizer


class JobScoringFacts(Protocol):
    """Minimal hydrated Job surface required by pure scoring.

    Members are read-only so frozen retrieval dataclasses satisfy the protocol
    under mypy (settable Protocol attrs reject ``@dataclass(frozen=True)``).
    """

    @property
    def job_id(self) -> str: ...

    @property
    def semantic_similarity(self) -> float: ...

    @property
    def extraction(self) -> JobPostExtraction: ...

    @property
    def jd_quality(self) -> str: ...

    @property
    def source_url(self) -> str | None: ...


def build_match_score_components(
    *,
    profile: CandidateProfile,
    preferences: JobPreferences,
    job: JobScoringFacts,
    normalizer: SkillNormalizer,
) -> tuple[MatchScoreComponents, SkillCoverageResult]:
    """Build the sole component map and skill-coverage facts for one Job."""
    coverage = compute_skill_coverage(
        profile.skills,
        required_skills=job.extraction.required_skills,
        preferred_skills=job.extraction.preferred_skills,
        normalizer=normalizer,
    )
    components = MatchScoreComponents(
        job_id=job.job_id,
        semantic_similarity=job.semantic_similarity,
        skill_score=coverage.skill_score,
        seniority_score=compute_seniority_score(
            job.extraction.seniority,
            preferences.target_seniority,
        ),
        experience_score=compute_experience_score(
            profile.total_experience_years,
            job.extraction.min_experience_years,
        ),
        location_score=compute_location_score(
            job.extraction.location,
            preferences.preferred_locations,
        ),
        work_mode_score=compute_work_mode_score(
            job.extraction.work_mode,
            preferences.acceptable_work_modes,
        ),
        jd_quality=job.jd_quality,
    )
    return components, coverage


def score_single_job(
    *,
    profile: CandidateProfile,
    preferences: JobPreferences,
    job: JobScoringFacts,
    normalizer: SkillNormalizer,
) -> MatchExplanationInput:
    """Score one hydrated Job through the shared component/explanation owners."""
    components, coverage = build_match_score_components(
        profile=profile,
        preferences=preferences,
        job=job,
        normalizer=normalizer,
    )
    scored = score_match_candidate(components)
    return MatchExplanationInput(
        scored=scored,
        skill_coverage=coverage,
        title=job.extraction.title,
        company=job.extraction.company,
        location=job.extraction.location,
        work_mode=job.extraction.work_mode,
        source_url=job.source_url,
    )


def project_single_job_match(
    *,
    profile: CandidateProfile,
    preferences: JobPreferences,
    job: JobScoringFacts,
    normalizer: SkillNormalizer,
) -> MatchResult:
    """Project one exact Job MatchResult through the shared pure path."""
    return project_match_result(
        score_single_job(
            profile=profile,
            preferences=preferences,
            job=job,
            normalizer=normalizer,
        )
    )


def score_retrieved_candidates(
    *,
    profile: CandidateProfile,
    preferences: JobPreferences,
    candidates: Sequence[Any],
    normalizer: SkillNormalizer,
    limit: int,
) -> MatchJobsResultData:
    """Score many hydrated Jobs, rank to limit, project compact top-N data.

    Uses the same per-Job component map and explanation projection as the
    exact-Job path; ranking is the only multi-Job step. Each candidate must
    satisfy :class:`JobScoringFacts`.
    """
    components_by_id: dict[str, MatchScoreComponents] = {}
    coverage_by_id: dict[str, SkillCoverageResult] = {}
    meta_by_id: dict[str, Any] = {}

    for candidate in candidates:
        components, coverage = build_match_score_components(
            profile=profile,
            preferences=preferences,
            job=candidate,
            normalizer=normalizer,
        )
        components_by_id[candidate.job_id] = components
        coverage_by_id[candidate.job_id] = coverage
        meta_by_id[candidate.job_id] = candidate

    ranked = rank_match_candidates(
        list(components_by_id.values()),
        limit=limit,
    )
    explanation_inputs = [
        MatchExplanationInput(
            scored=scored,
            skill_coverage=coverage_by_id[scored.components.job_id],
            title=meta_by_id[scored.components.job_id].extraction.title,
            company=meta_by_id[scored.components.job_id].extraction.company,
            location=meta_by_id[scored.components.job_id].extraction.location,
            work_mode=meta_by_id[scored.components.job_id].extraction.work_mode,
            source_url=meta_by_id[scored.components.job_id].source_url,
        )
        for scored in ranked
    ]
    return project_match_jobs_result(explanation_inputs, limit=limit)


__all__ = [
    "JobScoringFacts",
    "build_match_score_components",
    "project_single_job_match",
    "score_retrieved_candidates",
    "score_single_job",
]
