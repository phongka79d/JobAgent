"""Deterministic explanation generation from components and skill paths."""

from __future__ import annotations

from types import MappingProxyType

from app.schemas.job_post import JdQuality
from app.schemas.matching import MAX_EXPLANATION_LINES, MatchSkillPath
from app.schemas.score_breakdown import (
    COMPONENT_ORDER,
    ComponentValue,
    HybridScoreBreakdown,
    ScoreComponentName,
)
from app.services.explanations import generate_explanation_lines
from app.services.matching import SEED_CONFIG_VERSION


def _breakdown(
    *,
    final: float = 0.75,
    skill_available: bool = True,
) -> HybridScoreBreakdown:
    components: list[ComponentValue] = []
    weights: dict[str, float] = {}
    for name in COMPONENT_ORDER:
        if name is ScoreComponentName.SKILL_SCORE and not skill_available:
            components.append(
                ComponentValue(name=name, available=False, value=None)
            )
            continue
        value = 0.8 if name is ScoreComponentName.SEMANTIC_SIMILARITY else 1.0
        if name is ScoreComponentName.SKILL_SCORE:
            value = 0.6
        components.append(ComponentValue(name=name, available=True, value=value))
        weights[name.value] = {
            "semantic_similarity": 0.30,
            "skill_score": 0.40,
            "seniority_score": 0.10,
            "experience_score": 0.10,
            "location_score": 0.05,
            "work_mode_score": 0.05,
        }[name.value]
    if not skill_available:
        # renormalized remaining (seed mass without skill 0.40 → 0.60)
        weights = {
            "semantic_similarity": 0.30 / 0.60,
            "seniority_score": 0.10 / 0.60,
            "experience_score": 0.10 / 0.60,
            "location_score": 0.05 / 0.60,
            "work_mode_score": 0.05 / 0.60,
        }
    return HybridScoreBreakdown(
        components=tuple(components),
        effective_weights=MappingProxyType(weights),
        base_score=final,
        final_score=final,
        quality=JdQuality.FULL,
        quality_multiplier=1.0,
        seed_config_version=SEED_CONFIG_VERSION,
    )


def test_explanation_order_components_then_skills() -> None:
    matched = [
        MatchSkillPath(
            canonical_key="python",
            display_name="Python",
            match_kind="direct",
            strength=1.0,
        )
    ]
    related = [
        MatchSkillPath(
            canonical_key="kubernetes",
            display_name="Kubernetes",
            match_kind="verified_related",
            strength=0.6,
            related_path=["python", "kubernetes"],
        )
    ]
    missing = [
        MatchSkillPath(
            canonical_key="java",
            display_name="Java",
            match_kind="no_match",
            strength=0.0,
        )
    ]
    lines = generate_explanation_lines(
        _breakdown(),
        matched_required=matched,
        related=related,
        missing_required=missing,
    )
    assert lines
    assert lines[0].startswith("Semantic similarity:")
    # Component block first (6 or with unavailable markers), then skills
    joined = "\n".join(lines)
    assert "Matched required: Python" in joined
    assert "Related verified skill: Kubernetes" in joined
    assert "python → kubernetes" in joined
    assert "Missing required: Java" in joined
    # No raw evidence bodies
    assert "document" not in joined.lower()
    assert "snippet" not in joined.lower()


def test_unavailable_component_line_present() -> None:
    lines = generate_explanation_lines(_breakdown(skill_available=False))
    skill_lines = [line for line in lines if line.startswith("Skill coverage:")]
    assert skill_lines
    assert "unavailable" in skill_lines[0]


def test_truncation_is_prefix_stable() -> None:
    matched = [
        MatchSkillPath(
            canonical_key=f"skill_{i}",
            display_name=f"Skill {i}",
            match_kind="direct",
            strength=1.0,
        )
        for i in range(20)
    ]
    full = generate_explanation_lines(_breakdown(), matched_required=matched)
    truncated = generate_explanation_lines(
        _breakdown(),
        matched_required=matched,
        max_lines=5,
    )
    assert len(truncated) == 5
    assert truncated == full[:5]
    assert len(full) <= MAX_EXPLANATION_LINES


def test_deterministic_identical_for_same_inputs() -> None:
    kwargs = {
        "matched_required": [
            MatchSkillPath(
                canonical_key="python",
                display_name="Python",
                match_kind="direct",
                strength=1.0,
            )
        ],
        "related": [],
        "missing_required": [],
    }
    a = generate_explanation_lines(_breakdown(), **kwargs)  # type: ignore[arg-type]
    b = generate_explanation_lines(_breakdown(), **kwargs)  # type: ignore[arg-type]
    assert a == b


def test_no_provisional_or_raw_path_claims() -> None:
    lines = generate_explanation_lines(
        _breakdown(),
        related=[
            MatchSkillPath(
                canonical_key="docker",
                display_name="Docker",
                match_kind="verified_related",
                strength=0.6,
                related_path=["python", "docker"],
            )
        ],
    )
    joined = "\n".join(lines).lower()
    assert "provisional" not in joined
    assert "llm" not in joined
    assert "unsupported" not in joined
