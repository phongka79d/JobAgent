"""Table-driven tests for pure skill matching and skill-component coverage."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from app.schemas.candidate import (
    MAX_EVIDENCE_SNIPPET_LEN,
    CandidateSkill,
    SkillProficiency,
    SkillRef,
    SkillSource,
    SkillStatus,
)
from app.schemas.job_post import JobSkill
from app.services.skill_matching import (
    PREFERRED_COVERAGE_WEIGHT,
    REQUIRED_COVERAGE_WEIGHT,
    STRENGTH_DIRECT,
    STRENGTH_NONE,
    STRENGTH_VERIFIED_ALIAS,
    STRENGTH_VERIFIED_RELATED,
    MatchKind,
    VerifiedRelatedEdge,
    combine_skill_score,
    compute_skill_component,
    coverage_mean,
    index_verified_related_edges,
    match_job_skill,
    match_skill_list,
)


def _ref(
    *,
    key: str,
    display: str | None = None,
    aliases: list[str] | None = None,
    status: SkillStatus = SkillStatus.VERIFIED,
    confidence: float = 0.9,
    evidence: list[str] | None = None,
) -> SkillRef:
    return SkillRef(
        canonical_key=key,
        display_name=display if display is not None else key.replace("_", " ").title(),
        aliases=aliases or [],
        category=None,
        status=status,
        confidence=confidence,
        evidence=evidence if evidence is not None else [f"Skill: {key}"],
    )


def _cand(
    *,
    key: str,
    display: str | None = None,
    aliases: list[str] | None = None,
    status: SkillStatus = SkillStatus.VERIFIED,
    excluded: bool = False,
    evidence: list[str] | None = None,
) -> CandidateSkill:
    return CandidateSkill(
        skill=_ref(
            key=key,
            display=display,
            aliases=aliases,
            status=status,
            evidence=evidence,
        ),
        proficiency=SkillProficiency.UNKNOWN,
        years=None,
        source=SkillSource.CV,
        excluded=excluded,
        evidence=[],
    )


def _job(
    *,
    key: str,
    display: str | None = None,
    aliases: list[str] | None = None,
    status: SkillStatus = SkillStatus.VERIFIED,
    evidence: list[str] | None = None,
) -> JobSkill:
    return JobSkill(
        skill=_ref(
            key=key,
            display=display,
            aliases=aliases,
            status=status,
            evidence=evidence,
        ),
        confidence=0.9,
        evidence=evidence if evidence is not None else [f"Required: {key}"],
    )


def _edge(
    a: str,
    b: str,
    *,
    verified: bool = True,
    source: str = "seed_taxonomy",
    weight: float | None = 0.5,
) -> VerifiedRelatedEdge:
    return VerifiedRelatedEdge(
        from_key=a,
        to_key=b,
        source=source,
        verified=verified,
        weight=weight,
    )


# ---------------------------------------------------------------------------
# Precedence: direct / alias / related / provisional
# ---------------------------------------------------------------------------


def test_direct_canonical_match_strength() -> None:
    evidence = match_job_skill(
        _job(key="python"),
        [_cand(key="python")],
    )
    assert evidence.match_kind is MatchKind.DIRECT
    assert evidence.strength == STRENGTH_DIRECT
    assert evidence.candidate_canonical_key == "python"
    assert evidence.related_path == ()


def test_direct_beats_related_path() -> None:
    evidence = match_job_skill(
        _job(key="python"),
        [_cand(key="python"), _cand(key="django")],
        related_edges=[_edge("python", "django")],
    )
    assert evidence.match_kind is MatchKind.DIRECT
    assert evidence.strength == STRENGTH_DIRECT
    assert evidence.candidate_canonical_key == "python"


def test_verified_alias_match_when_keys_differ() -> None:
    evidence = match_job_skill(
        _job(key="py", display="py", status=SkillStatus.PROVISIONAL),
        [_cand(key="python", aliases=["py", "python3"])],
    )
    assert evidence.match_kind is MatchKind.VERIFIED_ALIAS
    assert evidence.strength == STRENGTH_VERIFIED_ALIAS
    assert evidence.candidate_canonical_key == "python"


def test_verified_alias_beats_related() -> None:
    evidence = match_job_skill(
        _job(key="py", aliases=["python"], status=SkillStatus.VERIFIED),
        [_cand(key="python"), _cand(key="django")],
        related_edges=[_edge("py", "django")],
    )
    assert evidence.match_kind is MatchKind.VERIFIED_ALIAS
    assert evidence.strength == STRENGTH_VERIFIED_ALIAS
    assert evidence.candidate_canonical_key == "python"


def test_verified_related_strength_exactly_0_6() -> None:
    evidence = match_job_skill(
        _job(key="django"),
        [_cand(key="python")],
        related_edges=[_edge("django", "python", source="manual_confirm")],
    )
    assert evidence.match_kind is MatchKind.VERIFIED_RELATED
    assert evidence.strength == STRENGTH_VERIFIED_RELATED
    assert evidence.strength == 0.6
    assert evidence.related_path == ("django", "python")
    assert evidence.source == "manual_confirm"


def test_provisional_related_edge_contributes_zero() -> None:
    evidence = match_job_skill(
        _job(key="django"),
        [_cand(key="python")],
        related_edges=[_edge("django", "python", verified=False)],
    )
    assert evidence.strength == STRENGTH_NONE
    assert evidence.match_kind is MatchKind.NO_MATCH
    assert evidence.related_path == ()


def test_unverified_missing_from_index() -> None:
    index = index_verified_related_edges(
        [_edge("a", "b", verified=False), _edge("c", "d", verified=True)]
    )
    assert ("a", "b") not in index
    assert ("c", "d") in index


def test_truthy_non_bool_verified_cannot_yield_related_score() -> None:
    """Fail closed: only boolean True is verified; 'true' and 1 never score 0.6.

    Covers both the edge-list indexer path and a caller-supplied related_index.
    Boolean True continues to produce STRENGTH_VERIFIED_RELATED.
    """
    job = _job(key="django")
    cands = [_cand(key="python")]

    # Truthy string / int must not enter the index or produce related strength.
    # Construct deliberately mistyped verified values (runtime, not schema).
    string_edge = VerifiedRelatedEdge(
        from_key="django",
        to_key="python",
        source="seed",
        verified="true",  # type: ignore[arg-type]
        weight=0.5,
    )
    int_edge = VerifiedRelatedEdge(
        from_key="django",
        to_key="python",
        source="seed",
        verified=1,  # type: ignore[arg-type]
        weight=0.5,
    )
    assert index_verified_related_edges([string_edge]) == {}
    assert index_verified_related_edges([int_edge]) == {}

    evidence_string = match_job_skill(
        job, cands, related_edges=[string_edge]
    )
    evidence_int = match_job_skill(job, cands, related_edges=[int_edge])
    assert evidence_string.strength == STRENGTH_NONE
    assert evidence_string.match_kind is MatchKind.NO_MATCH
    assert evidence_int.strength == STRENGTH_NONE
    assert evidence_int.match_kind is MatchKind.NO_MATCH

    # Supplied related_index path must re-filter; cannot bypass fail-closed.
    pair = ("django", "python")
    evidence_index_string = match_job_skill(
        job,
        cands,
        related_index={pair: string_edge},
    )
    evidence_index_int = match_job_skill(
        job,
        cands,
        related_index={pair: int_edge},
    )
    assert evidence_index_string.strength == STRENGTH_NONE
    assert evidence_index_int.strength == STRENGTH_NONE

    # Boolean True still yields verified-related 0.6 on both paths.
    true_edge = _edge("django", "python", verified=True)
    evidence_true = match_job_skill(job, cands, related_edges=[true_edge])
    assert evidence_true.match_kind is MatchKind.VERIFIED_RELATED
    assert evidence_true.strength == STRENGTH_VERIFIED_RELATED
    assert evidence_true.strength == 0.6

    evidence_index_true = match_job_skill(
        job,
        cands,
        related_index={pair: true_edge},
    )
    assert evidence_index_true.match_kind is MatchKind.VERIFIED_RELATED
    assert evidence_index_true.strength == STRENGTH_VERIFIED_RELATED


def test_no_match_when_candidate_empty() -> None:
    evidence = match_job_skill(_job(key="python"), [])
    assert evidence.strength == STRENGTH_NONE
    assert evidence.match_kind is MatchKind.NO_MATCH
    assert evidence.candidate_canonical_key is None


def test_provisional_job_skill_no_match_typed() -> None:
    evidence = match_job_skill(
        _job(key="zig", status=SkillStatus.PROVISIONAL),
        [_cand(key="python")],
    )
    assert evidence.strength == STRENGTH_NONE
    assert evidence.match_kind is MatchKind.PROVISIONAL


def test_provisional_candidate_direct_match_still_allowed() -> None:
    """Same canonical key matches even when skills are provisional."""
    evidence = match_job_skill(
        _job(key="zig", status=SkillStatus.PROVISIONAL),
        [_cand(key="zig", status=SkillStatus.PROVISIONAL)],
    )
    assert evidence.match_kind is MatchKind.DIRECT
    assert evidence.strength == STRENGTH_DIRECT


def test_two_provisional_alias_surfaces_do_not_boost() -> None:
    """Alias strength requires at least one verified skill identity."""
    evidence = match_job_skill(
        _job(key="a", aliases=["shared"], status=SkillStatus.PROVISIONAL),
        [_cand(key="b", aliases=["shared"], status=SkillStatus.PROVISIONAL)],
    )
    assert evidence.strength == STRENGTH_NONE


# ---------------------------------------------------------------------------
# Exclusions, duplicates, bidirectional related
# ---------------------------------------------------------------------------


def test_excluded_candidate_skill_ignored() -> None:
    evidence = match_job_skill(
        _job(key="python"),
        [_cand(key="python", excluded=True)],
    )
    assert evidence.strength == STRENGTH_NONE


def test_bidirectional_related_paths_dedupe() -> None:
    edges = [
        _edge("python", "django"),
        _edge("django", "python"),  # reverse of same pair
    ]
    index = index_verified_related_edges(edges)
    assert len(index) == 1
    evidence = match_job_skill(
        _job(key="django"),
        [_cand(key="python")],
        related_edges=edges,
    )
    assert evidence.strength == STRENGTH_VERIFIED_RELATED
    assert evidence.related_path == ("django", "python")


def test_duplicate_job_skills_deduped_for_coverage() -> None:
    matches = match_skill_list(
        [_job(key="python"), _job(key="python"), _job(key="go")],
        [_cand(key="python")],
    )
    assert len(matches) == 2
    assert matches[0].job_canonical_key == "python"
    assert matches[0].strength == STRENGTH_DIRECT
    assert matches[1].job_canonical_key == "go"
    assert matches[1].strength == STRENGTH_NONE


def test_alias_collision_prefers_stable_candidate_key() -> None:
    """When two verified candidates alias-match, pick lower canonical_key."""
    evidence = match_job_skill(
        _job(key="js", display="js", status=SkillStatus.PROVISIONAL),
        [
            _cand(key="typescript", aliases=["js"]),
            _cand(key="javascript", aliases=["js"]),
        ],
    )
    assert evidence.match_kind is MatchKind.VERIFIED_ALIAS
    assert evidence.candidate_canonical_key == "javascript"


# ---------------------------------------------------------------------------
# Coverage and renormalization
# ---------------------------------------------------------------------------


def test_both_lists_empty_unavailable_not_zero() -> None:
    result = compute_skill_component(
        required_skills=[],
        preferred_skills=[],
        candidate_skills=[_cand(key="python")],
    )
    assert result.available is False
    assert result.skill_score is None
    assert result.required_coverage is None
    assert result.preferred_coverage is None
    assert result.matched == ()
    assert result.related == ()
    assert result.missing_required == ()


def test_required_only_renormalizes_within_component() -> None:
    result = compute_skill_component(
        required_skills=[_job(key="python"), _job(key="go")],
        preferred_skills=[],
        candidate_skills=[_cand(key="python")],
    )
    assert result.available is True
    assert result.preferred_coverage is None
    assert result.required_coverage == pytest.approx(0.5)
    # One-side empty → skill_score equals the remaining coverage (not 0.8 *).
    assert result.skill_score == pytest.approx(0.5)
    assert result.skill_score != pytest.approx(
        REQUIRED_COVERAGE_WEIGHT * 0.5 + PREFERRED_COVERAGE_WEIGHT * 0.0
    )


def test_preferred_only_renormalizes_within_component() -> None:
    result = compute_skill_component(
        required_skills=[],
        preferred_skills=[_job(key="python")],
        candidate_skills=[_cand(key="python")],
    )
    assert result.available is True
    assert result.required_coverage is None
    assert result.preferred_coverage == pytest.approx(1.0)
    assert result.skill_score == pytest.approx(1.0)


def test_both_sides_use_0_80_0_20_weights() -> None:
    result = compute_skill_component(
        required_skills=[_job(key="python")],  # 1.0
        preferred_skills=[_job(key="go")],  # 0.0
        candidate_skills=[_cand(key="python")],
    )
    assert result.available is True
    assert result.required_coverage == pytest.approx(1.0)
    assert result.preferred_coverage == pytest.approx(0.0)
    expected = REQUIRED_COVERAGE_WEIGHT * 1.0 + PREFERRED_COVERAGE_WEIGHT * 0.0
    assert result.skill_score == pytest.approx(expected)
    assert result.skill_score == pytest.approx(0.80)


def test_related_contributes_to_coverage_mean() -> None:
    result = compute_skill_component(
        required_skills=[_job(key="django")],
        preferred_skills=[],
        candidate_skills=[_cand(key="python")],
        related_edges=[_edge("django", "python")],
    )
    assert result.required_coverage == pytest.approx(0.6)
    assert result.skill_score == pytest.approx(0.6)
    assert len(result.related) == 1
    assert result.related[0].related_path == ("django", "python")
    assert result.missing_required == ()


def test_missing_required_are_strength_zero() -> None:
    result = compute_skill_component(
        required_skills=[_job(key="python"), _job(key="go"), _job(key="rust")],
        preferred_skills=[_job(key="kubernetes")],
        candidate_skills=[_cand(key="python")],
    )
    missing_keys = {m.job_canonical_key for m in result.missing_required}
    assert missing_keys == {"go", "rust"}
    assert all(m.strength == STRENGTH_NONE for m in result.missing_required)
    # Preferred miss is not listed as missing required.
    assert "kubernetes" not in missing_keys
    assert len(result.matched) == 1
    assert result.matched[0].job_canonical_key == "python"


def test_every_related_explanation_names_verified_bounded_path() -> None:
    result = compute_skill_component(
        required_skills=[_job(key="django"), _job(key="flask")],
        preferred_skills=[],
        candidate_skills=[_cand(key="python")],
        related_edges=[
            _edge("django", "python", source="seed"),
            _edge("flask", "python", source="user_confirm"),
            _edge("ignored", "python", verified=False, source="llm"),
        ],
    )
    assert len(result.related) == 2
    for item in result.related:
        assert item.match_kind is MatchKind.VERIFIED_RELATED
        assert item.strength == 0.6
        assert len(item.related_path) == 2
        assert item.related_path[0] == item.job_canonical_key
        assert item.related_path[1] == "python"
        assert item.source in {"seed", "user_confirm"}


# ---------------------------------------------------------------------------
# Evidence bounds
# ---------------------------------------------------------------------------


def test_evidence_snippets_are_bounded() -> None:
    long = "x" * (MAX_EVIDENCE_SNIPPET_LEN + 40)
    # SkillRef evidence is schema-bounded at construction; use match-time edge
    # source overflow via VerifiedRelatedEdge (retrieval also truncates).
    edge = VerifiedRelatedEdge(
        from_key="django",
        to_key="python",
        source=long,
        verified=True,
        weight=None,
    )
    # index_verified_related_edges bounds source
    index = index_verified_related_edges([edge])
    stored = index[("django", "python")]
    assert len(stored.source) == MAX_EVIDENCE_SNIPPET_LEN

    evidence = match_job_skill(
        _job(key="django"),
        [_cand(key="python")],
        related_edges=[edge],
    )
    assert evidence.source is not None
    assert len(evidence.source) <= MAX_EVIDENCE_SNIPPET_LEN
    for snippet in evidence.evidence_snippets:
        assert len(snippet) <= MAX_EVIDENCE_SNIPPET_LEN


def test_combine_skill_score_table() -> None:
    cases: Sequence[tuple[float | None, float | None, bool, float | None]] = [
        (None, None, False, None),
        (1.0, None, True, 1.0),
        (None, 0.5, True, 0.5),
        (1.0, 0.0, True, 0.80),
        (0.5, 0.5, True, 0.80 * 0.5 + 0.20 * 0.5),
    ]
    for required, preferred, available, score in cases:
        got_available, got_score = combine_skill_score(required, preferred)
        assert got_available is available
        if score is None:
            assert got_score is None
        else:
            assert got_score == pytest.approx(score)


def test_coverage_mean_empty_is_none() -> None:
    assert coverage_mean(()) is None


def test_strength_constants_locked() -> None:
    assert STRENGTH_DIRECT == 1.0
    assert STRENGTH_VERIFIED_ALIAS == 1.0
    assert STRENGTH_VERIFIED_RELATED == 0.6
    assert STRENGTH_NONE == 0.0
    assert REQUIRED_COVERAGE_WEIGHT == 0.80
    assert PREFERRED_COVERAGE_WEIGHT == 0.20
