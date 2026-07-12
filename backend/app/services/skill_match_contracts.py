"""Skill-matching contracts and bounded evidence helpers (Plan 6 §7.2).

Owns locked strengths/weights, match kinds, edge/evidence result types, and
snippet bounding only. Matching and coverage live in ``skill_matching``.
Reuses shared ``SkillRef`` identity; does not normalize skills or query Neo4j.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.schemas.candidate import MAX_EVIDENCE_ITEMS, MAX_EVIDENCE_SNIPPET_LEN

# ---------------------------------------------------------------------------
# Locked strengths and skill-component weights (Plan 6 §7.2 / Master §18.1)
# ---------------------------------------------------------------------------

STRENGTH_DIRECT: Final[float] = 1.0
STRENGTH_VERIFIED_ALIAS: Final[float] = 1.0
STRENGTH_VERIFIED_RELATED: Final[float] = 0.6
STRENGTH_NONE: Final[float] = 0.0

REQUIRED_COVERAGE_WEIGHT: Final[float] = 0.80
PREFERRED_COVERAGE_WEIGHT: Final[float] = 0.20

MAX_RELATED_SOURCE_LEN: Final[int] = MAX_EVIDENCE_SNIPPET_LEN
MAX_MATCH_EVIDENCE_SNIPPETS: Final[int] = MAX_EVIDENCE_ITEMS


class MatchKind(StrEnum):
    """Strongest permitted path kind for one Job skill against Candidate skills."""

    DIRECT = "direct"
    VERIFIED_ALIAS = "verified_alias"
    VERIFIED_RELATED = "verified_related"
    PROVISIONAL = "provisional"
    NO_MATCH = "no_match"


# ---------------------------------------------------------------------------
# Bounded evidence types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifiedRelatedEdge:
    """One undirected verified ``RELATED_TO`` fact for matching (no raw docs).

    ``verified`` must be the boolean ``True`` for score-bearing use. Truthy
    strings/ints (e.g. ``'true'``, ``1``) must not contribute strength.
    ``source`` is a short taxonomy/label string only — never a document body.
    """

    from_key: str
    to_key: str
    source: str
    verified: bool
    weight: float | None = None


@dataclass(frozen=True, slots=True)
class SkillMatchEvidence:
    """Bounded strongest-path evidence for one Job skill."""

    job_canonical_key: str
    job_display_name: str
    candidate_canonical_key: str | None
    match_kind: MatchKind
    strength: float
    related_path: tuple[str, ...] = ()
    source: str | None = None
    evidence_snippets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillComponentResult:
    """Deterministic skill component: availability, score, and evidence lists.

    ``available`` is False only when both required and preferred lists are empty
    after stable deduplication; then ``skill_score`` and both coverages are
    None (unavailable is distinct from zero).
    """

    available: bool
    skill_score: float | None
    required_coverage: float | None
    preferred_coverage: float | None
    matched: tuple[SkillMatchEvidence, ...]
    related: tuple[SkillMatchEvidence, ...]
    missing_required: tuple[SkillMatchEvidence, ...]


# ---------------------------------------------------------------------------
# Relationship status and evidence helpers
# ---------------------------------------------------------------------------


def is_verified_relationship_status(value: object) -> bool:
    """Fail closed: only the boolean ``True`` is a verified relationship status."""
    return value is True


def bound_snippet(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_EVIDENCE_SNIPPET_LEN:
        return cleaned[:MAX_EVIDENCE_SNIPPET_LEN]
    return cleaned


def bound_snippets(items: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for item in items:
        if len(out) >= MAX_MATCH_EVIDENCE_SNIPPETS:
            break
        snippet = bound_snippet(item)
        if snippet is not None:
            out.append(snippet)
    return tuple(out)


def bound_source(source: object) -> str:
    if not isinstance(source, str):
        return ""
    cleaned = source.strip()
    if not cleaned:
        return ""
    if len(cleaned) > MAX_RELATED_SOURCE_LEN:
        return cleaned[:MAX_RELATED_SOURCE_LEN]
    return cleaned


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
    "bound_snippet",
    "bound_snippets",
    "bound_source",
    "is_verified_relationship_status",
]
