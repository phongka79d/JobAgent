"""Unit tests for exact Plan 6 preference component scores."""

from __future__ import annotations

import pytest
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_JD_QUALITY_UNSCORABLE,
)
from app.services.match_components import (
    MatchScoreComponents,
    compute_experience_score,
    compute_location_score,
    compute_seniority_score,
    compute_work_mode_score,
    normalize_location_for_match,
    score_match_candidate,
)

_BASE_WEIGHTS = {
    "semantic_similarity": 0.30,
    "skill_score": 0.40,
    "seniority_score": 0.10,
    "experience_score": 0.10,
    "location_score": 0.05,
    "work_mode_score": 0.05,
}
_OPTIONAL_COMPONENTS = (
    "skill_score",
    "seniority_score",
    "experience_score",
    "location_score",
    "work_mode_score",
)
_MISSING_COMPONENT_CASES = [
    tuple(
        component
        for index, component in enumerate(_OPTIONAL_COMPONENTS)
        if mask & (1 << index)
    )
    for mask in range(1 << len(_OPTIONAL_COMPONENTS))
]


def _candidate(
    *,
    jd_quality: str = JOB_JD_QUALITY_FULL,
    semantic_similarity: float = 0.70,
    skill_score: float | None = 0.80,
    seniority_score: float | None = 0.50,
    experience_score: float | None = 0.25,
    location_score: float | None = 1.00,
    work_mode_score: float | None = 0.00,
) -> MatchScoreComponents:
    return MatchScoreComponents(
        job_id="job-1",
        semantic_similarity=semantic_similarity,
        skill_score=skill_score,
        seniority_score=seniority_score,
        experience_score=experience_score,
        location_score=location_score,
        work_mode_score=work_mode_score,
        jd_quality=jd_quality,
    )


def _expected_base_score(values: dict[str, float | None]) -> float:
    available = {name: value for name, value in values.items() if value is not None}
    total_weight = sum(_BASE_WEIGHTS[name] for name in available)
    return sum(
        value * (_BASE_WEIGHTS[name] / total_weight)
        for name, value in available.items()
    )


def test_seniority_score_unavailable_for_unknown_jd_or_empty_preferences() -> None:
    assert compute_seniority_score("unknown", ["senior"]) is None
    assert compute_seniority_score("senior", []) is None


def test_seniority_score_uses_exact_membership_without_ladder() -> None:
    assert compute_seniority_score("senior", ["mid", "senior"]) == 1.0
    assert compute_seniority_score("senior", ["lead"]) == 0.0


@pytest.mark.parametrize(
    ("candidate_years", "minimum_years"),
    [
        (None, 3.0),
        (5.0, None),
    ],
)
def test_experience_score_unavailable_for_missing_inputs(
    candidate_years: float | None, minimum_years: float | None
) -> None:
    assert compute_experience_score(candidate_years, minimum_years) is None


@pytest.mark.parametrize(
    ("candidate_years", "minimum_years", "expected"),
    [
        (0.0, 0.0, 1.0),
        (3.0, 3.0, 1.0),
        (6.0, 3.0, 1.0),
        (1.5, 3.0, 0.5),
        (-1.0, 3.0, 0.0),
    ],
)
def test_experience_score_uses_minimum_only_and_clamps_ratio(
    candidate_years: float, minimum_years: float, expected: float
) -> None:
    assert compute_experience_score(candidate_years, minimum_years) == expected


def test_location_normalizer_nfkc_collapses_whitespace_and_casefolds() -> None:
    assert normalize_location_for_match(" \uff22ERLIN\t  Mitte ") == "berlin mitte"


@pytest.mark.parametrize("job_location", [None, "", " \t\n "])
def test_location_score_unavailable_for_missing_or_blank_job_location(
    job_location: str | None,
) -> None:
    assert compute_location_score(job_location, ["Berlin"]) is None


def test_location_score_unavailable_for_empty_or_blank_preferences() -> None:
    assert compute_location_score("Berlin", []) is None
    assert compute_location_score("Berlin", [" ", "\t"]) is None


def test_location_score_uses_exact_membership_after_minimal_normalization() -> None:
    assert compute_location_score("\uff22erlin", ["  berlin  "]) == 1.0
    assert compute_location_score("New-York", ["New York"]) == 0.0
    assert compute_location_score("SF", ["San Francisco"]) == 0.0


def test_work_mode_score_unavailable_for_unknown_jd_or_empty_preferences() -> None:
    assert compute_work_mode_score("unknown", ["remote"]) is None
    assert compute_work_mode_score("remote", []) is None


def test_work_mode_score_uses_exact_membership() -> None:
    assert compute_work_mode_score("hybrid", ["remote", "hybrid"]) == 1.0
    assert compute_work_mode_score("onsite", ["remote", "hybrid"]) == 0.0


@pytest.mark.parametrize("missing_components", _MISSING_COMPONENT_CASES)
def test_hybrid_score_renormalizes_every_missing_component_combination(
    missing_components: tuple[str, ...],
) -> None:
    values: dict[str, float | None] = {
        "semantic_similarity": 0.70,
        "skill_score": 0.80,
        "seniority_score": 0.50,
        "experience_score": 0.25,
        "location_score": 1.00,
        "work_mode_score": 0.00,
    }
    for component in missing_components:
        values[component] = None

    result = score_match_candidate(
        _candidate(
            semantic_similarity=values["semantic_similarity"] or 0.0,
            skill_score=values["skill_score"],
            seniority_score=values["seniority_score"],
            experience_score=values["experience_score"],
            location_score=values["location_score"],
            work_mode_score=values["work_mode_score"],
        )
    )

    available_components = {
        name for name, value in values.items() if value is not None
    }
    assert set(result.effective_weights) == available_components
    assert sum(result.effective_weights.values()) == pytest.approx(1.0)
    assert result.base_score == pytest.approx(_expected_base_score(values))
    assert result.final_score == pytest.approx(result.base_score)


def test_partial_quality_multiplier_applies_after_unrounded_base_score() -> None:
    full = score_match_candidate(_candidate(jd_quality=JOB_JD_QUALITY_FULL))
    partial = score_match_candidate(_candidate(jd_quality=JOB_JD_QUALITY_PARTIAL))

    assert partial.quality_multiplier == 0.85
    assert partial.base_score == pytest.approx(full.base_score)
    assert partial.final_score == pytest.approx(full.base_score * 0.85)


def test_unscorable_quality_is_rejected_without_final_score() -> None:
    with pytest.raises(ValueError, match="unscorable"):
        score_match_candidate(_candidate(jd_quality=JOB_JD_QUALITY_UNSCORABLE))
