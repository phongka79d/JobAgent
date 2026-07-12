"""Deterministic non-skill score components (Plan 6 §7.3 / Master §18.2–18.3).

Each pure function returns a finite float in ``[0, 1]`` or ``None`` (unavailable).
Unavailable is distinct from zero. Reuses retrieval cosine clamping and Job
identity location normalization. Does not own skill coverage (02A) or hybrid
aggregation (matching service).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from app.repositories.job_posts import normalize_job_identity_component
from app.schemas.job_post import JobSeniority, JobWorkMode
from app.schemas.preferences import TargetSeniority, WorkMode
from app.services.retrieval import clamp_semantic_similarity

# Finite unit-interval clamp bounds shared by every component.
_UNIT_LO: Final[float] = 0.0
_UNIT_HI: Final[float] = 1.0


def _finite_unit(value: float) -> float:
    """Clamp a known-finite number into ``[0, 1]`` (never NaN/inf)."""
    if value < _UNIT_LO:
        return _UNIT_LO
    if value > _UNIT_HI:
        return _UNIT_HI
    return value


def _as_finite_non_negative(value: object) -> float | None:
    """Parse a finite non-negative numeric years-like value; else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        return None
    return number


def compute_semantic_similarity(cosine_score: object) -> float | None:
    """Clamp Neo4j cosine similarity to ``[0, 1]``; invalid → unavailable.

    Reuses the retrieval boundary clamp so extremes and non-finite values match
    retrieval semantics. ``None``/non-numeric are unavailable, not zero.
    """
    return clamp_semantic_similarity(cosine_score)


def compute_seniority_score(
    job_seniority: JobSeniority | str | None,
    target_seniorities: Sequence[TargetSeniority | str],
) -> float | None:
    """1 when Job seniority is in targets; 0 for known non-match.

    Unavailable for unknown Job seniority or empty targets. Membership is exact
    on enum/token string values (no fuzzy rank mapping).
    """
    if job_seniority is None:
        return None
    job_token = (
        job_seniority.value
        if isinstance(job_seniority, JobSeniority)
        else str(job_seniority).strip()
    )
    if not job_token or job_token == JobSeniority.UNKNOWN.value:
        return None

    targets: list[str] = []
    for item in target_seniorities:
        if item is None:
            continue
        token = (
            item.value if isinstance(item, TargetSeniority) else str(item).strip()
        )
        if token and token not in targets:
            targets.append(token)
    if not targets:
        return None

    return 1.0 if job_token in targets else 0.0


def compute_experience_score(
    candidate_years: object,
    min_experience_years: object,
) -> float | None:
    """1 when Candidate years meet the Job minimum; else ratio clamped to [0, 1].

    Unavailable when either side is unknown/non-finite, or when the minimum is
    zero or missing (cannot form a ratio against a zero requirement).
    """
    candidate = _as_finite_non_negative(candidate_years)
    minimum = _as_finite_non_negative(min_experience_years)
    if candidate is None or minimum is None:
        return None
    if minimum == 0.0:
        return None
    if candidate >= minimum:
        return 1.0
    return _finite_unit(candidate / minimum)


def compute_location_score(
    job_location: str | None,
    preferred_locations: Sequence[str],
) -> float | None:
    """1 for normalized equality with any preferred location; 0 for known miss.

    Uses Job identity location normalization (NFC, collapse whitespace,
    casefold). Unavailable when Job location is missing/empty after normalize
    or when preferred locations are empty after normalize.
    """
    job_norm = normalize_job_identity_component(job_location)
    if job_norm is None:
        return None

    preferred_norms: list[str] = []
    for item in preferred_locations:
        if not isinstance(item, str):
            continue
        norm = normalize_job_identity_component(item)
        if norm is not None and norm not in preferred_norms:
            preferred_norms.append(norm)
    if not preferred_norms:
        return None

    return 1.0 if job_norm in preferred_norms else 0.0


def compute_work_mode_score(
    job_work_mode: JobWorkMode | str | None,
    acceptable_work_modes: Sequence[WorkMode | str],
) -> float | None:
    """1 when Job mode is acceptable; 0 for a known non-match.

    Unavailable for unknown/missing Job mode or empty acceptable modes. Exact
    membership only (remote/hybrid/onsite tokens).
    """
    if job_work_mode is None:
        return None
    job_token = (
        job_work_mode.value
        if isinstance(job_work_mode, JobWorkMode)
        else str(job_work_mode).strip()
    )
    if not job_token or job_token == JobWorkMode.UNKNOWN.value:
        return None

    accepted: list[str] = []
    for item in acceptable_work_modes:
        if item is None:
            continue
        token = item.value if isinstance(item, WorkMode) else str(item).strip()
        if token and token not in accepted:
            accepted.append(token)
    if not accepted:
        return None

    return 1.0 if job_token in accepted else 0.0


__all__ = [
    "compute_experience_score",
    "compute_location_score",
    "compute_semantic_similarity",
    "compute_seniority_score",
    "compute_work_mode_score",
]
