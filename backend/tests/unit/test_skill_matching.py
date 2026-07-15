"""Unit tests for pure skill matching and coverage (Plan 6 02A)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.schemas.jobs import JobSkill
from app.schemas.profile import CandidateSkill
from app.schemas.skills import SkillRef
from app.services.skill_matching import (
    MATCH_STRENGTH_DIRECT,
    MATCH_STRENGTH_NONE,
    MATCH_STRENGTH_RELATED,
    compute_skill_coverage,
    match_job_skill,
)
from app.services.skill_normalization import SkillNormalizer

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"
)


@pytest.fixture
def normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(FIXTURE_PATH)


def _ref(
    canonical_key: str,
    *,
    display_name: str | None = None,
    aliases: list[str] | None = None,
    category: str | None = None,
) -> SkillRef:
    return SkillRef(
        canonical_key=canonical_key,
        display_name=display_name or canonical_key.title(),
        aliases=list(aliases or []),
        category=category,
    )


def _candidate(
    canonical_key: str,
    *,
    display_name: str | None = None,
    aliases: list[str] | None = None,
    excluded: bool = False,
    evidence: list[str] | None = None,
) -> CandidateSkill:
    return CandidateSkill(
        skill=_ref(canonical_key, display_name=display_name, aliases=aliases),
        confidence=0.9,
        proficiency="advanced",
        years=3.0,
        source="cv",
        excluded=excluded,
        evidence=list(evidence or [f"candidate {canonical_key}"]),
    )


def _job(
    canonical_key: str,
    *,
    display_name: str | None = None,
    evidence: list[str] | None = None,
) -> JobSkill:
    return JobSkill(
        skill=_ref(canonical_key, display_name=display_name),
        confidence=0.8,
        evidence=list(evidence or [f"job {canonical_key}"]),
    )


def test_same_canonical_key_reports_direct_not_alias(
    normalizer: SkillNormalizer,
) -> None:
    candidate = _candidate(
        "python",
        display_name="Python",
        aliases=["python3", "py"],
        evidence=["candidate used python3"],
    )

    fact = match_job_skill(
        _job("python", display_name="Python"),
        [candidate],
        normalizer,
    )

    assert fact.match_type == "direct"
    assert fact.strength == MATCH_STRENGTH_DIRECT
    assert fact.candidate_skill == candidate
    assert fact.relationship is None


def test_related_match_uses_directed_seed_edge(
    normalizer: SkillNormalizer,
) -> None:
    fact = match_job_skill(_job("fastapi"), [_candidate("python")], normalizer)
    reverse = match_job_skill(_job("python"), [_candidate("fastapi")], normalizer)

    assert fact.match_type == "related"
    assert fact.strength == MATCH_STRENGTH_RELATED
    assert fact.relationship is not None
    assert fact.relationship.from_key == "python"
    assert fact.relationship.to_key == "fastapi"
    assert fact.relationship.weight == 0.6
    assert fact.relationship.source == "seed"

    assert reverse.match_type == "none"
    assert reverse.strength == MATCH_STRENGTH_NONE
    assert reverse.candidate_skill is None
    assert reverse.relationship is None


def test_related_formula_strength_is_fixed_while_seed_weight_is_metadata(
    normalizer: SkillNormalizer,
) -> None:
    fact = match_job_skill(_job("react"), [_candidate("typescript")], normalizer)

    assert fact.match_type == "related"
    assert fact.strength == MATCH_STRENGTH_RELATED
    assert fact.relationship is not None
    assert fact.relationship.weight == 0.7


def test_direct_precedence_and_exclusion(
    normalizer: SkillNormalizer,
) -> None:
    job = _job("fastapi")
    excluded_direct = _candidate("fastapi", excluded=True)
    related = _candidate("python")
    included_direct = _candidate("fastapi", evidence=["included direct"])

    excluded_fact = match_job_skill(job, [excluded_direct, related], normalizer)
    competing_fact = match_job_skill(job, [related, included_direct], normalizer)

    assert excluded_fact.match_type == "related"
    assert excluded_fact.candidate_skill == related
    assert excluded_fact.strength == MATCH_STRENGTH_RELATED

    assert competing_fact.match_type == "direct"
    assert competing_fact.candidate_skill == included_direct
    assert competing_fact.strength == MATCH_STRENGTH_DIRECT


def test_unknown_skills_get_no_inferred_relationship(
    normalizer: SkillNormalizer,
) -> None:
    unknown_candidate = _candidate("rust", display_name="Rust")

    no_match = match_job_skill(
        _job("go", display_name="Go"),
        [unknown_candidate],
        normalizer,
    )
    same_key = match_job_skill(
        _job("rust", display_name="Rust"),
        [unknown_candidate],
        normalizer,
    )

    assert no_match.match_type == "none"
    assert no_match.strength == MATCH_STRENGTH_NONE
    assert no_match.relationship is None

    assert same_key.match_type == "direct"
    assert same_key.strength == MATCH_STRENGTH_DIRECT


def test_deterministic_ties_keep_first_winning_candidate(
    normalizer: SkillNormalizer,
) -> None:
    first = _candidate("python", evidence=["first"])
    second = _candidate("python", evidence=["second"])

    fact = match_job_skill(_job("python"), [first, second], normalizer)

    assert fact.match_type == "direct"
    assert fact.candidate_skill == first


def test_skill_coverage_averages_lists_and_renormalizes_available_weights(
    normalizer: SkillNormalizer,
) -> None:
    result = compute_skill_coverage(
        [_candidate("python"), _candidate("typescript")],
        required_skills=[_job("python"), _job("sql")],
        preferred_skills=[_job("react")],
        normalizer=normalizer,
    )

    assert result.required_skill_coverage == pytest.approx(0.5)
    assert result.preferred_skill_coverage == pytest.approx(0.6)
    assert result.skill_score == pytest.approx(0.52)
    assert [fact.strength for fact in result.required_matches] == [
        MATCH_STRENGTH_DIRECT,
        MATCH_STRENGTH_NONE,
    ]
    assert [fact.strength for fact in result.preferred_matches] == [
        MATCH_STRENGTH_RELATED
    ]


@pytest.mark.parametrize(
    (
        "required_skills",
        "preferred_skills",
        "expected_required",
        "expected_preferred",
        "expected_score",
    ),
    [
        ([], [], None, None, None),
        ([], [_job("sql")], None, 0.0, 0.0),
        ([_job("sql")], [], 0.0, None, 0.0),
        ([_job("python")], [], 1.0, None, 1.0),
        ([], [_job("python")], None, 1.0, 1.0),
    ],
)
def test_empty_lists_are_unavailable_but_zero_matches_are_available(
    normalizer: SkillNormalizer,
    required_skills: list[JobSkill],
    preferred_skills: list[JobSkill],
    expected_required: float | None,
    expected_preferred: float | None,
    expected_score: float | None,
) -> None:
    result = compute_skill_coverage(
        [_candidate("python")],
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        normalizer=normalizer,
    )

    assert result.required_skill_coverage == expected_required
    assert result.preferred_skill_coverage == expected_preferred
    assert result.skill_score == expected_score
