"""Unit tests for hybrid aggregation, ranking, and seed weights (Plan 6 §7.4–7.5)."""

from __future__ import annotations

import json
import math
from types import MappingProxyType
from uuid import UUID

import pytest
from app.schemas.job_post import JdQuality, JobSeniority, JobWorkMode
from app.schemas.matching import MAX_MATCH_RESULTS, MAX_RANK_INPUTS
from app.schemas.preferences import TargetSeniority, WorkMode
from app.schemas.score_breakdown import (
    WEIGHT_SUM_TOLERANCE,
    ScoreComponentName,
)
from app.services.matching import (
    QUALITY_MULTIPLIER_FULL,
    QUALITY_MULTIPLIER_PARTIAL,
    SEED_CONFIG_VERSION,
    SEED_WEIGHTS,
    MatchingAggregationError,
    MatchingRankError,
    RankedJobCandidate,
    aggregate_hybrid_score,
    quality_multiplier,
    rank_match_results,
    renormalize_effective_weights,
    score_job_components,
    validate_seed_weights,
)
from app.services.skill_match_contracts import (
    MatchKind,
    SkillComponentResult,
    SkillMatchEvidence,
)


def _assert_weights_sum_to_one(weights: dict[str, float]) -> None:
    if not weights:
        return
    total = sum(weights.values())
    assert math.isfinite(total)
    assert abs(total - 1.0) <= WEIGHT_SUM_TOLERANCE


def _assert_finite_unit(value: float | None) -> None:
    if value is None:
        return
    assert math.isfinite(value)
    assert 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# Seed configuration identity
# ---------------------------------------------------------------------------


def test_seed_weights_are_versioned_immutable_and_locked() -> None:
    assert SEED_CONFIG_VERSION == "hybrid_seed_v1"
    assert isinstance(SEED_WEIGHTS, MappingProxyType)
    assert dict(SEED_WEIGHTS) == {
        "semantic_similarity": 0.30,
        "skill_score": 0.40,
        "seniority_score": 0.10,
        "experience_score": 0.10,
        "location_score": 0.05,
        "work_mode_score": 0.05,
    }
    assert abs(sum(SEED_WEIGHTS.values()) - 1.0) <= WEIGHT_SUM_TOLERANCE
    with pytest.raises(TypeError):
        SEED_WEIGHTS["skill_score"] = 0.99  # type: ignore[index]


def test_seed_contains_no_tuned_held_out_markers() -> None:
    # Configuration identity is the seed version only; no held-out/tuned tag.
    assert "held_out" not in SEED_CONFIG_VERSION
    assert "tuned" not in SEED_CONFIG_VERSION
    assert "grid" not in SEED_CONFIG_VERSION


# ---------------------------------------------------------------------------
# Quality multipliers
# ---------------------------------------------------------------------------


def test_quality_multipliers_exact() -> None:
    assert quality_multiplier(JdQuality.FULL) == QUALITY_MULTIPLIER_FULL
    assert quality_multiplier(JdQuality.PARTIAL) == QUALITY_MULTIPLIER_PARTIAL
    assert quality_multiplier(JdQuality.UNSCORABLE) is None
    assert quality_multiplier("full") == 1.00
    assert quality_multiplier("partial") == 0.85


# ---------------------------------------------------------------------------
# Renormalization
# ---------------------------------------------------------------------------


def test_renormalize_all_available_matches_seed() -> None:
    names = [name.value for name in ScoreComponentName]
    effective = renormalize_effective_weights(names)
    _assert_weights_sum_to_one(effective)
    for name, weight in SEED_WEIGHTS.items():
        assert effective[name] == pytest.approx(weight)


def test_renormalize_drops_unavailable_not_zero_weight() -> None:
    # Drop skill (0.40) and location (0.05) → remaining 0.55
    available = [
        "semantic_similarity",
        "seniority_score",
        "experience_score",
        "work_mode_score",
    ]
    effective = renormalize_effective_weights(available)
    assert "skill_score" not in effective
    assert "location_score" not in effective
    _assert_weights_sum_to_one(effective)
    assert effective["semantic_similarity"] == pytest.approx(0.30 / 0.55)
    assert effective["seniority_score"] == pytest.approx(0.10 / 0.55)


def test_renormalize_all_unavailable_empty() -> None:
    assert renormalize_effective_weights([]) == {}


def test_invalid_seed_weights_rejected() -> None:
    with pytest.raises(MatchingAggregationError):
        validate_seed_weights({})
    with pytest.raises(MatchingAggregationError):
        validate_seed_weights({"unknown_component": 1.0})
    with pytest.raises(MatchingAggregationError):
        validate_seed_weights({"skill_score": -0.1})
    with pytest.raises(MatchingAggregationError):
        validate_seed_weights({"skill_score": float("nan")})
    with pytest.raises(MatchingAggregationError):
        validate_seed_weights(
            {
                "semantic_similarity": 0.0,
                "skill_score": 0.0,
                "seniority_score": 0.0,
                "experience_score": 0.0,
                "location_score": 0.0,
                "work_mode_score": 0.0,
            }
        )


def test_incomplete_seed_map_rejected_by_validate_and_aggregate() -> None:
    """Configured seeds must include all six locked keys (missing ≠ zero)."""
    incomplete = {
        "semantic_similarity": 0.30,
        "skill_score": 0.40,
        # intentionally omit seniority/experience/location/work_mode
    }
    with pytest.raises(MatchingAggregationError, match="missing locked components"):
        validate_seed_weights(incomplete)

    component_values = {name.value: 1.0 for name in ScoreComponentName}
    with pytest.raises(MatchingAggregationError, match="missing locked components"):
        aggregate_hybrid_score(
            component_values,
            quality=JdQuality.FULL,
            seed_weights=incomplete,
        )


def test_complete_default_and_custom_seed_maps_renormalize() -> None:
    """Full default and full custom maps remain valid for renormalization."""
    default_cleaned = validate_seed_weights(SEED_WEIGHTS)
    assert default_cleaned == dict(SEED_WEIGHTS)

    custom = {
        "semantic_similarity": 0.20,
        "skill_score": 0.20,
        "seniority_score": 0.20,
        "experience_score": 0.20,
        "location_score": 0.10,
        "work_mode_score": 0.10,
    }
    assert validate_seed_weights(custom) == custom

    all_names = [name.value for name in ScoreComponentName]
    default_effective = renormalize_effective_weights(all_names)
    _assert_weights_sum_to_one(default_effective)
    for name, weight in SEED_WEIGHTS.items():
        assert default_effective[name] == pytest.approx(weight)

    custom_effective = renormalize_effective_weights(
        all_names,
        seed_weights=custom,
    )
    _assert_weights_sum_to_one(custom_effective)
    for name, weight in custom.items():
        assert custom_effective[name] == pytest.approx(weight)

    # Drop skill (0.20) → remaining mass 0.80
    partial = [n for n in all_names if n != "skill_score"]
    partial_effective = renormalize_effective_weights(
        partial,
        seed_weights=custom,
    )
    assert "skill_score" not in partial_effective
    _assert_weights_sum_to_one(partial_effective)
    assert partial_effective["semantic_similarity"] == pytest.approx(0.20 / 0.80)
    assert partial_effective["location_score"] == pytest.approx(0.10 / 0.80)

    component_values = {name.value: 1.0 for name in ScoreComponentName}
    result = aggregate_hybrid_score(
        component_values,
        quality=JdQuality.FULL,
        seed_weights=custom,
    )
    _assert_weights_sum_to_one(dict(result.effective_weights))
    assert result.base_score == pytest.approx(1.0)
    assert result.final_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Aggregation + quality
# ---------------------------------------------------------------------------


def test_full_quality_applies_once_after_aggregation() -> None:
    values = {
        "semantic_similarity": 1.0,
        "skill_score": 1.0,
        "seniority_score": 1.0,
        "experience_score": 1.0,
        "location_score": 1.0,
        "work_mode_score": 1.0,
    }
    result = aggregate_hybrid_score(values, quality=JdQuality.FULL)
    _assert_weights_sum_to_one(dict(result.effective_weights))
    assert result.base_score == pytest.approx(1.0)
    assert result.final_score == pytest.approx(1.0)
    assert result.quality_multiplier == 1.00
    assert result.seed_config_version == SEED_CONFIG_VERSION
    for component in result.components:
        assert component.available is True
        assert component.value == 1.0


def test_partial_multiplies_base_by_0_85() -> None:
    values = {
        "semantic_similarity": 1.0,
        "skill_score": 0.5,
        "seniority_score": 0.0,
        "experience_score": 1.0,
        "location_score": 0.0,
        "work_mode_score": 1.0,
    }
    result = aggregate_hybrid_score(values, quality=JdQuality.PARTIAL)
    expected_base = (
        0.30 * 1.0
        + 0.40 * 0.5
        + 0.10 * 0.0
        + 0.10 * 1.0
        + 0.05 * 0.0
        + 0.05 * 1.0
    )
    assert result.base_score == pytest.approx(expected_base)
    assert result.final_score == pytest.approx(expected_base * 0.85)
    assert result.quality_multiplier == 0.85
    _assert_finite_unit(result.base_score)
    _assert_finite_unit(result.final_score)


def test_unscorable_never_receives_final_score() -> None:
    values = {
        "semantic_similarity": 1.0,
        "skill_score": 1.0,
        "seniority_score": 1.0,
        "experience_score": 1.0,
        "location_score": 1.0,
        "work_mode_score": 1.0,
    }
    result = aggregate_hybrid_score(values, quality=JdQuality.UNSCORABLE)
    assert result.base_score is None
    assert result.final_score is None
    assert result.quality_multiplier is None
    assert result.quality is JdQuality.UNSCORABLE
    # Components may still be reported; aggregation does not produce a score.
    assert all(c.available for c in result.components)


def test_unavailable_components_absent_from_effective_weights() -> None:
    values = {
        "semantic_similarity": 0.8,
        "skill_score": None,  # unavailable
        "seniority_score": 1.0,
        "experience_score": None,
        "location_score": 0.0,  # available zero
        "work_mode_score": None,
    }
    result = aggregate_hybrid_score(values, quality=JdQuality.FULL)
    weights = dict(result.effective_weights)
    assert "skill_score" not in weights
    assert "experience_score" not in weights
    assert "work_mode_score" not in weights
    assert "location_score" in weights  # zero value still available
    _assert_weights_sum_to_one(weights)

    by_name = result.component_map()
    assert by_name["skill_score"].available is False
    assert by_name["skill_score"].value is None
    assert by_name["location_score"].available is True
    assert by_name["location_score"].value == 0.0

    # Remaining seed mass: 0.30 + 0.10 + 0.05 = 0.45
    expected_base = (
        (0.30 / 0.45) * 0.8 + (0.10 / 0.45) * 1.0 + (0.05 / 0.45) * 0.0
    )
    assert result.base_score == pytest.approx(expected_base)
    assert result.final_score == pytest.approx(expected_base)


def test_all_unavailable_yields_no_score() -> None:
    values = {name.value: None for name in ScoreComponentName}
    result = aggregate_hybrid_score(values, quality=JdQuality.FULL)
    assert dict(result.effective_weights) == {}
    assert result.base_score is None
    assert result.final_score is None
    assert result.quality_multiplier == 1.00
    assert all(not c.available and c.value is None for c in result.components)


def test_zero_is_not_unavailable() -> None:
    values = {
        "semantic_similarity": 0.0,
        "skill_score": 0.0,
        "seniority_score": 0.0,
        "experience_score": 0.0,
        "location_score": 0.0,
        "work_mode_score": 0.0,
    }
    result = aggregate_hybrid_score(values, quality=JdQuality.FULL)
    assert all(c.available and c.value == 0.0 for c in result.components)
    assert result.base_score == pytest.approx(0.0)
    assert result.final_score == pytest.approx(0.0)
    _assert_weights_sum_to_one(dict(result.effective_weights))


def test_non_finite_component_treated_as_unavailable() -> None:
    values = {
        "semantic_similarity": float("nan"),
        "skill_score": float("inf"),
        "seniority_score": 1.0,
        "experience_score": 1.0,
        "location_score": 1.0,
        "work_mode_score": 1.0,
    }
    result = aggregate_hybrid_score(values, quality=JdQuality.FULL)
    by_name = result.component_map()
    assert by_name["semantic_similarity"].available is False
    assert by_name["skill_score"].available is False
    assert "semantic_similarity" not in result.effective_weights
    assert "skill_score" not in result.effective_weights
    _assert_weights_sum_to_one(dict(result.effective_weights))
    _assert_finite_unit(result.base_score)
    _assert_finite_unit(result.final_score)


# ---------------------------------------------------------------------------
# End-to-end component composition (reuses 02A skill score as input)
# ---------------------------------------------------------------------------


def test_score_job_components_full_happy_path() -> None:
    result = score_job_components(
        semantic_similarity=0.9,
        skill_score=0.8,  # from 02A; not recomputed here
        job_seniority=JobSeniority.SENIOR,
        target_seniorities=[TargetSeniority.SENIOR],
        candidate_years=5.0,
        min_experience_years=4.0,
        job_location="Berlin",
        preferred_locations=["Berlin"],
        job_work_mode=JobWorkMode.REMOTE,
        acceptable_work_modes=[WorkMode.REMOTE],
        quality=JdQuality.FULL,
    )
    by_name = result.component_map()
    assert by_name["semantic_similarity"].value == pytest.approx(0.9)
    assert by_name["skill_score"].value == pytest.approx(0.8)
    assert by_name["seniority_score"].value == 1.0
    assert by_name["experience_score"].value == 1.0
    assert by_name["location_score"].value == 1.0
    assert by_name["work_mode_score"].value == 1.0
    expected_base = (
        0.30 * 0.9
        + 0.40 * 0.8
        + 0.10 * 1.0
        + 0.10 * 1.0
        + 0.05 * 1.0
        + 0.05 * 1.0
    )
    assert result.base_score == pytest.approx(expected_base)
    assert result.final_score == pytest.approx(expected_base)
    _assert_weights_sum_to_one(dict(result.effective_weights))


def test_score_job_components_partial_experience_and_partial_quality() -> None:
    result = score_job_components(
        semantic_similarity=1.0,
        skill_score=None,  # skill unavailable (both lists empty in 02A)
        job_seniority=JobSeniority.UNKNOWN,  # unavailable
        target_seniorities=[TargetSeniority.MID],
        candidate_years=2.0,
        min_experience_years=4.0,  # ratio 0.5
        job_location=None,  # unavailable
        preferred_locations=["Berlin"],
        job_work_mode=JobWorkMode.ONSITE,
        acceptable_work_modes=[WorkMode.REMOTE],  # known zero
        quality=JdQuality.PARTIAL,
    )
    by_name = result.component_map()
    assert by_name["skill_score"].available is False
    assert by_name["seniority_score"].available is False
    assert by_name["location_score"].available is False
    assert by_name["experience_score"].value == pytest.approx(0.5)
    assert by_name["work_mode_score"].value == 0.0

    # Available: semantic 0.30, experience 0.10, work_mode 0.05 → total 0.45
    expected_base = (0.30 / 0.45) * 1.0 + (0.10 / 0.45) * 0.5 + (0.05 / 0.45) * 0.0
    assert result.base_score == pytest.approx(expected_base)
    assert result.final_score == pytest.approx(expected_base * 0.85)
    assert "skill_score" not in result.effective_weights
    _assert_weights_sum_to_one(dict(result.effective_weights))


def test_score_job_components_unscorable_blocked() -> None:
    result = score_job_components(
        semantic_similarity=1.0,
        skill_score=1.0,
        job_seniority=JobSeniority.MID,
        target_seniorities=[TargetSeniority.MID],
        candidate_years=3.0,
        min_experience_years=2.0,
        job_location="X",
        preferred_locations=["X"],
        job_work_mode=JobWorkMode.HYBRID,
        acceptable_work_modes=[WorkMode.HYBRID],
        quality=JdQuality.UNSCORABLE,
    )
    assert result.final_score is None
    assert result.base_score is None


def test_aggregate_rejects_invalid_custom_weights() -> None:
    values = {name.value: 1.0 for name in ScoreComponentName}
    with pytest.raises(MatchingAggregationError):
        aggregate_hybrid_score(
            values,
            quality=JdQuality.FULL,
            seed_weights={"skill_score": float("nan")},
        )


# ---------------------------------------------------------------------------
# Top-10 ranking, ties, bounds, privacy (Plan 6 §7.4–7.5 / 02C)
# ---------------------------------------------------------------------------


def _uid(n: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{n:012d}")


def _scored_candidate(
    n: int,
    *,
    final_via_semantic: float,
    quality: JdQuality = JdQuality.FULL,
    title: str | None = None,
    source_url: str | None = "https://jobs.example.com/post",
    with_skills: bool = False,
) -> RankedJobCandidate:
    """Build a RankedJobCandidate with a controlled final score via semantic."""
    skill = 0.0
    breakdown = score_job_components(
        semantic_similarity=final_via_semantic,
        skill_score=skill,
        job_seniority=JobSeniority.UNKNOWN,
        target_seniorities=[],
        candidate_years=None,
        min_experience_years=None,
        job_location=None,
        preferred_locations=[],
        job_work_mode=None,
        acceptable_work_modes=[],
        quality=quality,
    )
    skill_component: SkillComponentResult | None = None
    if with_skills:
        skill_component = SkillComponentResult(
            available=True,
            skill_score=1.0,
            required_coverage=1.0,
            preferred_coverage=None,
            matched=(
                SkillMatchEvidence(
                    job_canonical_key="python",
                    job_display_name="Python",
                    candidate_canonical_key="python",
                    match_kind=MatchKind.DIRECT,
                    strength=1.0,
                    evidence_snippets=("RAW DOCUMENT BODY MUST NOT LEAK",),
                ),
            ),
            related=(
                SkillMatchEvidence(
                    job_canonical_key="kubernetes",
                    job_display_name="Kubernetes",
                    candidate_canonical_key="python",
                    match_kind=MatchKind.VERIFIED_RELATED,
                    strength=0.6,
                    related_path=("python", "kubernetes"),
                    source="taxonomy",
                    evidence_snippets=("secret raw path evidence",),
                ),
            ),
            missing_required=(
                SkillMatchEvidence(
                    job_canonical_key="java",
                    job_display_name="Java",
                    candidate_canonical_key=None,
                    match_kind=MatchKind.NO_MATCH,
                    strength=0.0,
                    evidence_snippets=("cv blob",),
                ),
                SkillMatchEvidence(
                    job_canonical_key="provisional_skill",
                    job_display_name="Provisional Skill",
                    candidate_canonical_key=None,
                    match_kind=MatchKind.PROVISIONAL,
                    strength=0.0,
                    evidence_snippets=("provisional raw",),
                ),
            ),
        )
    return RankedJobCandidate(
        job_id=_uid(n),
        title=title if title is not None else f"Job {n}",
        company="Acme",
        location="Berlin",
        work_mode="remote",
        source_url=source_url,
        breakdown=breakdown,
        skill_component=skill_component,
    )


def test_rank_caps_at_ten_and_drops_unscorable() -> None:
    candidates = [
        _scored_candidate(i, final_via_semantic=i / 100.0) for i in range(1, 16)
    ]
    candidates.append(
        _scored_candidate(99, final_via_semantic=1.0, quality=JdQuality.UNSCORABLE)
    )
    collection = rank_match_results(candidates)
    assert len(collection.results) == MAX_MATCH_RESULTS
    assert all(item.final_score is not None for item in collection.results)
    # Highest semantic inputs win; job 15 has semantic 0.15 → highest among 1..15
    assert collection.results[0].job_id == _uid(15)
    assert _uid(99) not in {item.job_id for item in collection.results}


def test_rank_stable_across_input_permutations() -> None:
    base = [
        _scored_candidate(1, final_via_semantic=0.5),
        _scored_candidate(2, final_via_semantic=0.9),
        _scored_candidate(3, final_via_semantic=0.5),
        _scored_candidate(4, final_via_semantic=0.2),
    ]
    orders = [
        base,
        list(reversed(base)),
        [base[2], base[0], base[3], base[1]],
        [base[1], base[3], base[0], base[2]],
    ]
    payloads: list[str] = []
    for order in orders:
        collection = rank_match_results(order)
        payloads.append(
            json.dumps(collection.model_dump(mode="json"), sort_keys=True)
        )
    assert payloads[0] == payloads[1] == payloads[2] == payloads[3]
    # Tie at 0.5: job_id ascending → 1 before 3
    ids = [item.job_id for item in rank_match_results(base).results]
    assert ids == [_uid(2), _uid(1), _uid(3), _uid(4)]


def test_job_id_tie_break_ascending() -> None:
    # Equal semantic → equal final after renormalization; order by UUID.
    tied = [
        _scored_candidate(30, final_via_semantic=0.7),
        _scored_candidate(10, final_via_semantic=0.7),
        _scored_candidate(20, final_via_semantic=0.7),
    ]
    collection = rank_match_results(list(reversed(tied)))
    assert [item.job_id for item in collection.results] == [
        _uid(10),
        _uid(20),
        _uid(30),
    ]


def test_rank_rejects_over_fifty_inputs() -> None:
    candidates = [
        _scored_candidate(i, final_via_semantic=0.1) for i in range(MAX_RANK_INPUTS + 1)
    ]
    with pytest.raises(MatchingRankError, match="exceed"):
        rank_match_results(candidates)


def test_rank_accepts_exactly_fifty_returns_ten() -> None:
    candidates = [
        _scored_candidate(i, final_via_semantic=i / 100.0)
        for i in range(1, MAX_RANK_INPUTS + 1)
    ]
    collection = rank_match_results(candidates)
    assert len(collection.results) == MAX_MATCH_RESULTS
    assert collection.results[0].job_id == _uid(MAX_RANK_INPUTS)


def test_privacy_no_raw_evidence_or_provisional_in_results() -> None:
    candidate = _scored_candidate(
        1,
        final_via_semantic=0.9,
        with_skills=True,
        source_url="https://user:pass@evil.example/secret",
    )
    collection = rank_match_results([candidate])
    assert len(collection.results) == 1
    result = collection.results[0]
    payload = json.dumps(result.model_dump(mode="json"))
    assert "RAW DOCUMENT" not in payload
    assert "secret raw" not in payload
    assert "cv blob" not in payload
    assert "provisional raw" not in payload
    assert "evidence_snippets" not in payload
    assert result.source_url is None  # credentials fail closed
    # Provisional missing mapped to no_match surface only if included as missing
    kinds = {p.match_kind for p in result.missing_required_skills}
    assert "provisional" not in kinds
    assert all(p.match_kind == "no_match" for p in result.missing_required_skills)
    assert any(p.canonical_key == "provisional_skill" for p in result.missing_required_skills)
    # Related path present without raw body
    assert result.related_skills[0].related_path == ["python", "kubernetes"]
    assert result.explanation_lines
    assert all("RAW" not in line for line in result.explanation_lines)


def test_identical_inputs_identical_json() -> None:
    c1 = _scored_candidate(5, final_via_semantic=0.55, with_skills=True)
    c2 = _scored_candidate(5, final_via_semantic=0.55, with_skills=True)
    a = rank_match_results([c1]).model_dump(mode="json")
    b = rank_match_results([c2]).model_dump(mode="json")
    assert a == b


def test_partial_quality_survives_ranking() -> None:
    candidate = _scored_candidate(
        7,
        final_via_semantic=1.0,
        quality=JdQuality.PARTIAL,
    )
    collection = rank_match_results([candidate])
    assert len(collection.results) == 1
    assert collection.results[0].quality == "partial"
    assert collection.results[0].final_score == pytest.approx(
        candidate.breakdown.final_score  # type: ignore[arg-type]
    )
