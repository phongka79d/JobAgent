"""Unit tests for non-skill score components (Plan 6 §7.3)."""

from __future__ import annotations

import math

import pytest
from app.schemas.job_post import JobSeniority, JobWorkMode
from app.schemas.preferences import TargetSeniority, WorkMode
from app.services.score_components import (
    compute_experience_score,
    compute_location_score,
    compute_semantic_similarity,
    compute_seniority_score,
    compute_work_mode_score,
)


def _assert_unit_or_none(value: float | None) -> None:
    if value is None:
        return
    assert math.isfinite(value)
    assert 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# Semantic similarity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.0, 0.0),
        (1.0, 1.0),
        (0.42, 0.42),
        (-0.5, 0.0),
        (1.5, 1.0),
        (True, None),  # bool is not numeric for clamp
        ("0.5", None),
        (None, None),
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
    ],
)
def test_semantic_similarity_clamp_and_unavailable(
    raw: object,
    expected: float | None,
) -> None:
    result = compute_semantic_similarity(raw)
    _assert_unit_or_none(result)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Seniority
# ---------------------------------------------------------------------------


def test_seniority_exact_membership_hit() -> None:
    assert (
        compute_seniority_score(
            JobSeniority.SENIOR,
            [TargetSeniority.MID, TargetSeniority.SENIOR],
        )
        == 1.0
    )


def test_seniority_known_non_match_is_zero_not_unavailable() -> None:
    assert (
        compute_seniority_score(JobSeniority.JUNIOR, [TargetSeniority.SENIOR]) == 0.0
    )


def test_seniority_unknown_job_is_unavailable() -> None:
    assert (
        compute_seniority_score(
            JobSeniority.UNKNOWN,
            [TargetSeniority.SENIOR],
        )
        is None
    )


def test_seniority_empty_targets_unavailable() -> None:
    assert compute_seniority_score(JobSeniority.SENIOR, []) is None


def test_seniority_none_job_unavailable() -> None:
    assert compute_seniority_score(None, [TargetSeniority.SENIOR]) is None


def test_seniority_string_tokens_supported() -> None:
    assert compute_seniority_score("lead", ["lead", "senior"]) == 1.0
    assert compute_seniority_score("intern", ["senior"]) == 0.0


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------


def test_experience_meets_minimum_is_one() -> None:
    assert compute_experience_score(5.0, 3.0) == 1.0
    assert compute_experience_score(3.0, 3.0) == 1.0


def test_experience_partial_ratio_clamped() -> None:
    assert compute_experience_score(2.0, 4.0) == pytest.approx(0.5)
    assert compute_experience_score(0.0, 4.0) == pytest.approx(0.0)


def test_experience_missing_candidate_unavailable() -> None:
    assert compute_experience_score(None, 3.0) is None


def test_experience_missing_minimum_unavailable() -> None:
    assert compute_experience_score(5.0, None) is None


def test_experience_zero_minimum_unavailable() -> None:
    assert compute_experience_score(5.0, 0.0) is None


def test_experience_non_finite_unavailable() -> None:
    assert compute_experience_score(float("nan"), 3.0) is None
    assert compute_experience_score(3.0, float("inf")) is None
    assert compute_experience_score(-1.0, 3.0) is None


def test_experience_never_out_of_range() -> None:
    # Candidate far above minimum still clamps to 1.0
    assert compute_experience_score(100.0, 1.0) == 1.0


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


def test_location_normalized_equality_hit() -> None:
    assert (
        compute_location_score("  Berlin,  DE ", ["berlin, de", "Munich"])
        == 1.0
    )


def test_location_known_non_match_is_zero() -> None:
    assert compute_location_score("Paris", ["Berlin", "Munich"]) == 0.0


def test_location_missing_job_unavailable() -> None:
    assert compute_location_score(None, ["Berlin"]) is None
    assert compute_location_score("   ", ["Berlin"]) is None


def test_location_empty_preferred_unavailable() -> None:
    assert compute_location_score("Berlin", []) is None
    assert compute_location_score("Berlin", ["  ", ""]) is None


def test_location_casefold_and_whitespace() -> None:
    assert compute_location_score("NEW YORK", ["new york"]) == 1.0


# ---------------------------------------------------------------------------
# Work mode
# ---------------------------------------------------------------------------


def test_work_mode_membership_hit() -> None:
    assert (
        compute_work_mode_score(
            JobWorkMode.REMOTE,
            [WorkMode.REMOTE, WorkMode.HYBRID],
        )
        == 1.0
    )


def test_work_mode_known_non_match_is_zero() -> None:
    assert compute_work_mode_score(JobWorkMode.ONSITE, [WorkMode.REMOTE]) == 0.0


def test_work_mode_unknown_job_unavailable() -> None:
    assert (
        compute_work_mode_score(JobWorkMode.UNKNOWN, [WorkMode.REMOTE]) is None
    )


def test_work_mode_empty_acceptable_unavailable() -> None:
    assert compute_work_mode_score(JobWorkMode.REMOTE, []) is None


def test_work_mode_none_job_unavailable() -> None:
    assert compute_work_mode_score(None, [WorkMode.REMOTE]) is None


def test_work_mode_string_tokens() -> None:
    assert compute_work_mode_score("hybrid", ["hybrid"]) == 1.0
    assert compute_work_mode_score("onsite", ["remote"]) == 0.0
