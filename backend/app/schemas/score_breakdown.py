"""Strict hybrid score breakdown contracts (Plan 6 §7.3–7.4 / Master §18.2–18.3).

Owns component name identity, unavailable-distinct-from-zero values, effective
weight maps, and base/final score results only. Formulas live in services.
Seed weights and quality multipliers are versioned configuration, not optimality
claims. Match-result transport maps reuse ``COMPONENT_ORDER`` and these types.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.schemas.job_post import JdQuality

# Documented tolerance for proving effective weights sum to one after
# renormalization (Plan 6 §7.4 / Master §18.3).
WEIGHT_SUM_TOLERANCE: Final[float] = 1e-9


class ScoreComponentName(StrEnum):
    """Locked hybrid component names (Master §18.2 order)."""

    SEMANTIC_SIMILARITY = "semantic_similarity"
    SKILL_SCORE = "skill_score"
    SENIORITY_SCORE = "seniority_score"
    EXPERIENCE_SCORE = "experience_score"
    LOCATION_SCORE = "location_score"
    WORK_MODE_SCORE = "work_mode_score"


COMPONENT_ORDER: Final[tuple[ScoreComponentName, ...]] = (
    ScoreComponentName.SEMANTIC_SIMILARITY,
    ScoreComponentName.SKILL_SCORE,
    ScoreComponentName.SENIORITY_SCORE,
    ScoreComponentName.EXPERIENCE_SCORE,
    ScoreComponentName.LOCATION_SCORE,
    ScoreComponentName.WORK_MODE_SCORE,
)


@dataclass(frozen=True, slots=True)
class ComponentValue:
    """One score component: availability is distinct from a zero value.

    When ``available`` is False, ``value`` is always None (not 0.0).
    When ``available`` is True, ``value`` is a finite float in ``[0, 1]``.
    """

    name: ScoreComponentName
    available: bool
    value: float | None


@dataclass(frozen=True, slots=True)
class HybridScoreBreakdown:
    """Strict component/effective-weight breakdown with base and final scores.

    ``effective_weights`` contains only available components (unavailable names
    are absent, never silently zero-weighted). ``base_score`` is the weighted
    sum before the quality multiplier; ``final_score`` is base × multiplier.
    Unscorable Jobs and all-unavailable inputs yield None scores.
    """

    components: tuple[ComponentValue, ...]
    effective_weights: Mapping[str, float]
    base_score: float | None
    final_score: float | None
    quality: JdQuality
    quality_multiplier: float | None
    seed_config_version: str

    def component_map(self) -> dict[str, ComponentValue]:
        return {item.name.value: item for item in self.components}

    def ordered_components(self) -> tuple[ComponentValue, ...]:
        """Return components in locked ``COMPONENT_ORDER`` (stable for transport)."""
        by_name = self.component_map()
        ordered: list[ComponentValue] = []
        for name in COMPONENT_ORDER:
            item = by_name.get(name.value)
            if item is not None:
                ordered.append(item)
        return tuple(ordered)


__all__ = [
    "COMPONENT_ORDER",
    "WEIGHT_SUM_TOLERANCE",
    "ComponentValue",
    "HybridScoreBreakdown",
    "ScoreComponentName",
]
