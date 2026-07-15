"""Unit tests for exact Plan 6 match ordering and result limits."""

from __future__ import annotations

import pytest
from app.db.models.jobs import JOB_JD_QUALITY_FULL
from app.services.match_components import (
    MatchScoreComponents,
    ScoredMatchCandidate,
    order_scored_match_candidates,
    rank_match_candidates,
)


def _components(
    job_id: str,
    *,
    semantic_similarity: float,
    skill_score: float | None = None,
) -> MatchScoreComponents:
    return MatchScoreComponents(
        job_id=job_id,
        semantic_similarity=semantic_similarity,
        skill_score=skill_score,
        seniority_score=None,
        experience_score=None,
        location_score=None,
        work_mode_score=None,
        jd_quality=JOB_JD_QUALITY_FULL,
    )


def _scored(
    job_id: str,
    *,
    final_score: float,
    skill_score: float | None,
    semantic_similarity: float,
) -> ScoredMatchCandidate:
    return ScoredMatchCandidate(
        components=_components(
            job_id,
            semantic_similarity=semantic_similarity,
            skill_score=skill_score,
        ),
        base_score=final_score,
        final_score=final_score,
        quality_multiplier=1.0,
        effective_weights={"semantic_similarity": 1.0},
    )


def test_ordering_uses_unrounded_final_score() -> None:
    ordered = order_scored_match_candidates(
        [
            _scored(
                "job-b",
                final_score=0.5000000001,
                skill_score=None,
                semantic_similarity=0.5000000001,
            ),
            _scored(
                "job-a",
                final_score=0.5000000002,
                skill_score=None,
                semantic_similarity=0.5000000002,
            ),
        ],
        limit=2,
    )

    assert [candidate.components.job_id for candidate in ordered] == [
        "job-a",
        "job-b",
    ]


def test_ordering_applies_skill_semantic_and_job_id_tie_breaks() -> None:
    ordered = order_scored_match_candidates(
        [
            _scored(
                "skill-null",
                final_score=0.70,
                skill_score=None,
                semantic_similarity=1.00,
            ),
            _scored(
                "skill-low",
                final_score=0.70,
                skill_score=0.40,
                semantic_similarity=1.00,
            ),
            _scored(
                "skill-high",
                final_score=0.70,
                skill_score=0.90,
                semantic_similarity=0.10,
            ),
            _scored(
                "semantic-low",
                final_score=0.60,
                skill_score=0.40,
                semantic_similarity=0.20,
            ),
            _scored(
                "semantic-high",
                final_score=0.60,
                skill_score=0.40,
                semantic_similarity=0.80,
            ),
            _scored(
                "job-id-b",
                final_score=0.50,
                skill_score=0.10,
                semantic_similarity=0.30,
            ),
            _scored(
                "job-id-a",
                final_score=0.50,
                skill_score=0.10,
                semantic_similarity=0.30,
            ),
        ],
        limit=10,
    )

    assert [candidate.components.job_id for candidate in ordered] == [
        "skill-high",
        "skill-low",
        "skill-null",
        "semantic-high",
        "semantic-low",
        "job-id-a",
        "job-id-b",
    ]


def test_rank_match_candidates_scores_orders_and_bounds_to_limit() -> None:
    ordered = rank_match_candidates(
        [
            _components("job-low", semantic_similarity=0.10),
            _components("job-high", semantic_similarity=0.90),
            _components("job-mid", semantic_similarity=0.50),
        ],
        limit=2,
    )

    assert [candidate.components.job_id for candidate in ordered] == [
        "job-high",
        "job-mid",
    ]
    assert len(ordered) == 2


@pytest.mark.parametrize("limit", [0, 11, True])
def test_rank_match_candidates_rejects_limit_outside_one_to_ten(
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="limit"):
        rank_match_candidates(
            [_components("job-1", semantic_similarity=0.50)],
            limit=limit,
        )
