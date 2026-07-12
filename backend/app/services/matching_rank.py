"""Top-10 ranking and MatchResult assembly (Plan 6 §7.4–7.5).

Owns pure ranking of scored candidates, skill-path projection, and validated
MatchResult construction with deterministic explanations. Aggregation lives in
``matching_aggregate``. No LLM scoring, graph lookup, or Job mutation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.schemas.job_post import JdQuality
from app.schemas.job_tools import safe_public_source_url
from app.schemas.matching import (
    MATCH_RESULT_CONTRACT_VERSION,
    MAX_MATCH_RESULTS,
    MAX_MATCH_SKILL_ITEMS,
    MAX_RANK_INPUTS,
    MatchComponentEntry,
    MatchResult,
    MatchResultCollection,
    MatchSkillPath,
)
from app.schemas.score_breakdown import HybridScoreBreakdown
from app.services.explanations import generate_explanation_lines
from app.services.matching_aggregate import SEED_CONFIG_VERSION
from app.services.skill_match_contracts import (
    MatchKind,
    SkillComponentResult,
    SkillMatchEvidence,
)


class MatchingRankError(ValueError):
    """Invalid ranking inputs (bounds / identity); fail closed."""


@dataclass(frozen=True, slots=True)
class RankedJobCandidate:
    """One scored Job ready for pure ranking (no graph/LLM/mutation side effects).

    ``breakdown`` must already be produced by hybrid aggregation. Skill evidence
    is optional but required for skill-path explanations when present.
    """

    job_id: UUID
    title: str | None
    company: str | None
    location: str | None
    work_mode: str | None
    source_url: str | None
    breakdown: HybridScoreBreakdown
    skill_component: SkillComponentResult | None = None


def _skill_path_from_evidence(
    evidence: SkillMatchEvidence,
    *,
    allowed_kinds: frozenset[MatchKind],
) -> MatchSkillPath | None:
    """Project internal evidence to the public path surface (no raw snippets)."""
    if evidence.match_kind not in allowed_kinds:
        return None
    if evidence.match_kind is MatchKind.PROVISIONAL:
        return None

    kind = evidence.match_kind.value
    if kind not in {"direct", "verified_alias", "verified_related", "no_match"}:
        return None

    related_path: list[str] = []
    if evidence.match_kind is MatchKind.VERIFIED_RELATED:
        related_path = [str(item) for item in evidence.related_path if str(item).strip()]
        if len(related_path) < 2:
            # Fail closed: related without explicit path never appears.
            return None

    strength = float(evidence.strength)
    if not math.isfinite(strength):
        return None
    if strength < 0.0:
        strength = 0.0
    elif strength > 1.0:
        strength = 1.0

    try:
        return MatchSkillPath(
            canonical_key=evidence.job_canonical_key,
            display_name=evidence.job_display_name,
            match_kind=kind,  # type: ignore[arg-type]
            strength=strength,
            related_path=related_path,
            candidate_canonical_key=evidence.candidate_canonical_key,
        )
    except Exception:
        return None


def _bound_skill_list(
    items: Sequence[SkillMatchEvidence],
    *,
    allowed_kinds: frozenset[MatchKind],
) -> list[MatchSkillPath]:
    out: list[MatchSkillPath] = []
    seen: set[str] = set()
    for evidence in items:
        path = _skill_path_from_evidence(evidence, allowed_kinds=allowed_kinds)
        if path is None:
            continue
        if path.canonical_key in seen:
            continue
        seen.add(path.canonical_key)
        out.append(path)
        if len(out) >= MAX_MATCH_SKILL_ITEMS:
            break
    return out


def project_skill_paths(
    skill_component: SkillComponentResult | None,
) -> tuple[list[MatchSkillPath], list[MatchSkillPath], list[MatchSkillPath]]:
    """Bound matched/related/missing paths; drop provisional and raw bodies."""
    if skill_component is None:
        return [], [], []
    matched = _bound_skill_list(
        skill_component.matched,
        allowed_kinds=frozenset({MatchKind.DIRECT, MatchKind.VERIFIED_ALIAS}),
    )
    related = _bound_skill_list(
        skill_component.related,
        allowed_kinds=frozenset({MatchKind.VERIFIED_RELATED}),
    )
    # Missing required: strength-zero only; map provisional/no_match → no_match.
    missing: list[MatchSkillPath] = []
    seen: set[str] = set()
    for evidence in skill_component.missing_required:
        if evidence.strength != 0.0:
            continue
        if evidence.match_kind not in {
            MatchKind.NO_MATCH,
            MatchKind.PROVISIONAL,
        }:
            # Only strength-zero missing; never promote related/direct here.
            if evidence.match_kind in {
                MatchKind.DIRECT,
                MatchKind.VERIFIED_ALIAS,
                MatchKind.VERIFIED_RELATED,
            }:
                continue
        key = evidence.job_canonical_key.strip()
        if not key or key in seen:
            continue
        try:
            path = MatchSkillPath(
                canonical_key=key,
                display_name=evidence.job_display_name,
                match_kind="no_match",
                strength=0.0,
                related_path=[],
                candidate_canonical_key=None,
            )
        except Exception:
            continue
        seen.add(key)
        missing.append(path)
        if len(missing) >= MAX_MATCH_SKILL_ITEMS:
            break
    return matched, related, missing


def _component_entries(breakdown: HybridScoreBreakdown) -> list[MatchComponentEntry]:
    weights = dict(breakdown.effective_weights)
    entries: list[MatchComponentEntry] = []
    for component in breakdown.ordered_components():
        weight = weights.get(component.name.value)
        if component.available and component.value is not None:
            # Available entries require a finite effective weight on the
            # transport contract; omit incomplete rows fail-closed upstream.
            if weight is None or not math.isfinite(float(weight)):
                continue
            entries.append(
                MatchComponentEntry(
                    name=component.name.value,
                    available=True,
                    value=float(component.value),
                    effective_weight=float(weight),
                )
            )
        else:
            entries.append(
                MatchComponentEntry(
                    name=component.name.value,
                    available=False,
                    value=None,
                    effective_weight=None,
                )
            )
    return entries


def build_match_result(candidate: RankedJobCandidate) -> MatchResult | None:
    """Assemble one validated MatchResult; None when unscored/invalid."""
    breakdown = candidate.breakdown
    if breakdown.final_score is None:
        return None
    quality = breakdown.quality
    if quality is JdQuality.UNSCORABLE:
        return None
    if quality not in {JdQuality.FULL, JdQuality.PARTIAL}:
        return None

    matched, related, missing = project_skill_paths(candidate.skill_component)
    explanation = generate_explanation_lines(
        breakdown,
        matched_required=matched,
        related=related,
        missing_required=missing,
    )
    source = safe_public_source_url(candidate.source_url)
    try:
        return MatchResult(
            job_id=candidate.job_id,
            title=candidate.title,
            company=candidate.company,
            location=candidate.location,
            work_mode=candidate.work_mode,
            final_score=float(breakdown.final_score),
            quality=quality.value,  # type: ignore[arg-type]
            components=_component_entries(breakdown),
            matched_required_skills=matched,
            related_skills=related,
            missing_required_skills=missing,
            explanation_lines=list(explanation),
            source_url=source,
            seed_config_version=breakdown.seed_config_version,
            contract_version=MATCH_RESULT_CONTRACT_VERSION,
        )
    except Exception:
        return None


def rank_match_results(
    candidates: Sequence[RankedJobCandidate],
    *,
    limit: int = MAX_MATCH_RESULTS,
    seed_config_version: str = SEED_CONFIG_VERSION,
) -> MatchResultCollection:
    """Stable-sort by final score desc + Job-ID asc; return at most 10 results.

    Pure ranking layer: no model calls, no vector lookup, no Job mutation.
    Accepts at most ``MAX_RANK_INPUTS`` (50) candidates; excess fails closed.
    """
    if limit < 0:
        raise MatchingRankError("limit must be non-negative")
    if limit > MAX_MATCH_RESULTS:
        limit = MAX_MATCH_RESULTS
    if len(candidates) > MAX_RANK_INPUTS:
        raise MatchingRankError(
            f"rank inputs exceed {MAX_RANK_INPUTS} (got {len(candidates)})"
        )

    built: list[MatchResult] = []
    for candidate in candidates:
        result = build_match_result(candidate)
        if result is None:
            continue
        if result.seed_config_version != seed_config_version:
            # Keep only results matching the collection config identity.
            continue
        built.append(result)

    # Descending final score, ascending Job-ID for ties (stable across input order).
    built.sort(key=lambda item: (-item.final_score, item.job_id))
    top = built[:limit]
    return MatchResultCollection(
        results=top,
        contract_version=MATCH_RESULT_CONTRACT_VERSION,
        seed_config_version=seed_config_version,
    )


__all__ = [
    "MatchingRankError",
    "RankedJobCandidate",
    "build_match_result",
    "project_skill_paths",
    "rank_match_results",
]
