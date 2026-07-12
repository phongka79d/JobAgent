"""Deterministic evidence-backed match explanations (Plan 6 §7.5).

Generates bounded explanation lines only from hybrid component values and
explicit skill paths. Never calls an LLM, never includes raw evidence bodies,
and never claims provisional or unsupported paths.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from app.schemas.matching import (
    MAX_EXPLANATION_LINE_LEN,
    MAX_EXPLANATION_LINES,
    MatchSkillPath,
)
from app.schemas.score_breakdown import (
    COMPONENT_ORDER,
    HybridScoreBreakdown,
    ScoreComponentName,
)
from app.services.skill_match_contracts import MatchKind

# Stable component labels for human-readable lines (not free-form narrative).
_COMPONENT_LABELS: Final[dict[str, str]] = {
    ScoreComponentName.SEMANTIC_SIMILARITY.value: "Semantic similarity",
    ScoreComponentName.SKILL_SCORE.value: "Skill coverage",
    ScoreComponentName.SENIORITY_SCORE.value: "Seniority match",
    ScoreComponentName.EXPERIENCE_SCORE.value: "Experience match",
    ScoreComponentName.LOCATION_SCORE.value: "Location match",
    ScoreComponentName.WORK_MODE_SCORE.value: "Work-mode match",
}

_KIND_LABELS: Final[dict[str, str]] = {
    MatchKind.DIRECT.value: "direct",
    MatchKind.VERIFIED_ALIAS.value: "verified alias",
    MatchKind.VERIFIED_RELATED.value: "verified RELATED_TO",
    MatchKind.NO_MATCH.value: "no match",
}


def _bound_line(text: str) -> str | None:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > MAX_EXPLANATION_LINE_LEN:
        cleaned = cleaned[:MAX_EXPLANATION_LINE_LEN]
    return cleaned


def _fmt_unit(value: float) -> str:
    # Fixed precision for deterministic JSON-compatible text.
    return f"{value:.4f}".rstrip("0").rstrip(".") if "." in f"{value:.4f}" else f"{value:.4f}"


def _component_lines(breakdown: HybridScoreBreakdown) -> list[str]:
    by_name = breakdown.component_map()
    weights = dict(breakdown.effective_weights)
    lines: list[str] = []
    for name in COMPONENT_ORDER:
        component = by_name.get(name.value)
        if component is None:
            continue
        label = _COMPONENT_LABELS.get(name.value, name.value)
        if not component.available or component.value is None:
            line = _bound_line(f"{label}: unavailable (excluded from weights)")
            if line is not None:
                lines.append(line)
            continue
        weight = weights.get(name.value)
        if weight is None:
            line = _bound_line(
                f"{label}: {_fmt_unit(component.value)} (no effective weight)"
            )
        else:
            line = _bound_line(
                f"{label}: {_fmt_unit(component.value)} "
                f"(effective weight {_fmt_unit(weight)})"
            )
        if line is not None:
            lines.append(line)
    return lines


def _skill_label(path: MatchSkillPath) -> str:
    name = path.display_name.strip() or path.canonical_key
    return name


def _matched_lines(matched: Sequence[MatchSkillPath]) -> list[str]:
    lines: list[str] = []
    for path in matched:
        kind = _KIND_LABELS.get(path.match_kind, path.match_kind)
        line = _bound_line(
            f"Matched required: {_skill_label(path)} ({kind}, "
            f"strength {_fmt_unit(path.strength)})"
        )
        if line is not None:
            lines.append(line)
    return lines


def _related_lines(related: Sequence[MatchSkillPath]) -> list[str]:
    lines: list[str] = []
    for path in related:
        # Only verified related paths may appear; path keys are the evidence.
        route = " → ".join(path.related_path) if path.related_path else path.canonical_key
        line = _bound_line(
            f"Related verified skill: {_skill_label(path)} via {route} "
            f"(strength {_fmt_unit(path.strength)})"
        )
        if line is not None:
            lines.append(line)
    return lines


def _missing_lines(missing: Sequence[MatchSkillPath]) -> list[str]:
    lines: list[str] = []
    for path in missing:
        line = _bound_line(
            f"Missing required: {_skill_label(path)} "
            f"(strength {_fmt_unit(path.strength)})"
        )
        if line is not None:
            lines.append(line)
    return lines


def generate_explanation_lines(
    breakdown: HybridScoreBreakdown,
    *,
    matched_required: Sequence[MatchSkillPath] = (),
    related: Sequence[MatchSkillPath] = (),
    missing_required: Sequence[MatchSkillPath] = (),
    max_lines: int = MAX_EXPLANATION_LINES,
) -> tuple[str, ...]:
    """Build ordered, truncated explanation lines from scores and skill paths.

    Order is fixed: components (COMPONENT_ORDER), matched, related, missing.
    Truncation preserves prefix order. Never includes raw evidence bodies.
    """
    if max_lines < 0:
        max_lines = 0
    if max_lines > MAX_EXPLANATION_LINES:
        max_lines = MAX_EXPLANATION_LINES

    ordered: list[str] = []
    ordered.extend(_component_lines(breakdown))
    ordered.extend(_matched_lines(matched_required))
    ordered.extend(_related_lines(related))
    ordered.extend(_missing_lines(missing_required))

    if not ordered:
        fallback = _bound_line(
            f"Final score {_fmt_unit(breakdown.final_score)}"
            if breakdown.final_score is not None
            else "No score components available"
        )
        if fallback is not None:
            ordered.append(fallback)

    return tuple(ordered[:max_lines])


__all__ = [
    "generate_explanation_lines",
]
