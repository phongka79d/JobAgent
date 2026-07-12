"""Deterministic skill matching: direct, verified-alias, verified-related.

Public facade for Plan 6 §7.2 / Master §18.1. Implementation is split across
focused modules so no production source exceeds the focused-module ceiling:

- ``skill_match_contracts`` — strengths, weights, evidence types, bounds
- ``skill_match_evidence`` — RELATED_TO index and strongest-path matching
- ``skill_match_coverage`` — coverage means and skill-component aggregation

Reuses shared ``SkillRef`` identity and ``normalize_skill_match_key``; never
invents or persists ``RELATED_TO`` edges and never treats provisional/unverified
relationships as score-bearing.

Stable task-facing imports remain on this module.
"""

from __future__ import annotations

from app.services.skill_match_contracts import (
    MAX_MATCH_EVIDENCE_SNIPPETS,
    MAX_RELATED_SOURCE_LEN,
    PREFERRED_COVERAGE_WEIGHT,
    REQUIRED_COVERAGE_WEIGHT,
    STRENGTH_DIRECT,
    STRENGTH_NONE,
    STRENGTH_VERIFIED_ALIAS,
    STRENGTH_VERIFIED_RELATED,
    MatchKind,
    SkillComponentResult,
    SkillMatchEvidence,
    VerifiedRelatedEdge,
    is_verified_relationship_status,
)
from app.services.skill_match_coverage import (
    combine_skill_score,
    compute_skill_component,
    coverage_mean,
)
from app.services.skill_match_evidence import (
    index_verified_related_edges,
    match_job_skill,
    match_skill_list,
)

__all__ = [
    "MAX_MATCH_EVIDENCE_SNIPPETS",
    "MAX_RELATED_SOURCE_LEN",
    "PREFERRED_COVERAGE_WEIGHT",
    "REQUIRED_COVERAGE_WEIGHT",
    "STRENGTH_DIRECT",
    "STRENGTH_NONE",
    "STRENGTH_VERIFIED_ALIAS",
    "STRENGTH_VERIFIED_RELATED",
    "MatchKind",
    "SkillComponentResult",
    "SkillMatchEvidence",
    "VerifiedRelatedEdge",
    "combine_skill_score",
    "compute_skill_component",
    "coverage_mean",
    "index_verified_related_edges",
    "is_verified_relationship_status",
    "match_job_skill",
    "match_skill_list",
]
