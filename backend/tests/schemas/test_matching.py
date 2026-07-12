"""Schema bounds and fail-closed rules for match result contracts."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from app.schemas.matching import (
    KIND_MATCH_RESULTS,
    MATCH_JOBS_OUTCOME_MATCH_FAILED,
    MATCH_JOBS_OUTCOME_MATCHES_FOUND,
    MATCH_JOBS_OUTCOME_NO_MATCHES,
    MATCH_JOBS_OUTCOME_PROFILE_REQUIRED,
    MATCH_RESULT_CONTRACT_VERSION,
    MAX_EXPLANATION_LINE_LEN,
    MAX_EXPLANATION_LINES,
    MAX_MATCH_RESULTS,
    MatchComponentEntry,
    MatchResult,
    MatchResultCollection,
    MatchResultsCardPayload,
    MatchSkillPath,
    build_match_results_card,
    match_jobs_public_outcome,
    parse_match_jobs_tool_body,
    try_parse_match_results_card,
)
from app.schemas.score_breakdown import COMPONENT_ORDER
from pydantic import ValidationError


def _component(
    name: str = "semantic_similarity",
    *,
    available: bool = True,
    value: float | None = 0.5,
    weight: float | None = 0.3,
) -> MatchComponentEntry:
    return MatchComponentEntry(
        name=name,
        available=available,
        value=value if available else None,
        effective_weight=weight if available else None,
    )


def _full_components(
    *,
    omit: str | None = None,
    available_override: dict[str, tuple[float, float]] | None = None,
    force_missing_weight: str | None = None,
) -> list[MatchComponentEntry]:
    """Build the locked six-component inventory with unit effective weights."""
    defaults: dict[str, tuple[float, float]] = {
        "semantic_similarity": (0.9, 0.3),
        "skill_score": (0.8, 0.4),
        "seniority_score": (1.0, 0.1),
        "experience_score": (1.0, 0.1),
        "location_score": (1.0, 0.05),
        "work_mode_score": (1.0, 0.05),
    }
    if available_override is not None:
        defaults = available_override
    entries: list[MatchComponentEntry] = []
    for name in COMPONENT_ORDER:
        key = name.value
        if omit is not None and key == omit:
            continue
        if key not in defaults:
            entries.append(
                MatchComponentEntry(
                    name=key,
                    available=False,
                    value=None,
                    effective_weight=None,
                )
            )
            continue
        value, weight = defaults[key]
        if force_missing_weight == key:
            # Bypass entry constructor so MatchResult sees available+None weight.
            entries.append(
                MatchComponentEntry.model_construct(
                    name=key,
                    available=True,
                    value=value,
                    effective_weight=None,
                )
            )
        else:
            entries.append(_component(key, value=value, weight=weight))
    return entries


def _result(
    job_id: UUID | None = None,
    *,
    score: float = 0.8,
    source_url: str | None = "https://example.com/jobs/1",
    seed: str = "hybrid_seed_v1",
    components: list[MatchComponentEntry] | None = None,
) -> MatchResult:
    return MatchResult(
        job_id=job_id or uuid4(),
        title="Engineer",
        company="Acme",
        location="Berlin",
        work_mode="remote",
        final_score=score,
        quality="full",
        components=components if components is not None else _full_components(),
        matched_required_skills=[
            MatchSkillPath(
                canonical_key="python",
                display_name="Python",
                match_kind="direct",
                strength=1.0,
            )
        ],
        related_skills=[
            MatchSkillPath(
                canonical_key="kubernetes",
                display_name="Kubernetes",
                match_kind="verified_related",
                strength=0.6,
                related_path=["python", "kubernetes"],
            )
        ],
        missing_required_skills=[
            MatchSkillPath(
                canonical_key="java",
                display_name="Java",
                match_kind="no_match",
                strength=0.0,
            )
        ],
        explanation_lines=["Semantic similarity: 0.9 (effective weight 0.3)"],
        source_url=source_url,
        seed_config_version=seed,
        contract_version=MATCH_RESULT_CONTRACT_VERSION,
    )


def test_match_result_accepts_valid_transparent_payload() -> None:
    result = _result()
    dumped = result.model_dump(mode="json")
    assert dumped["contract_version"] == MATCH_RESULT_CONTRACT_VERSION
    assert dumped["final_score"] == 0.8
    assert dumped["source_url"] == "https://example.com/jobs/1"
    assert dumped["matched_required_skills"][0]["match_kind"] == "direct"
    assert "evidence_snippets" not in dumped["matched_required_skills"][0]
    assert "evidence" not in dumped["matched_required_skills"][0]


def test_unsafe_source_url_fail_closed_to_none() -> None:
    for bad in (
        "http://localhost/secret",
        "https://127.0.0.1/x",
        "ftp://example.com/x",
        "https://user:pass@example.com/x",
        "not-a-url",
        "file:///etc/passwd",
    ):
        result = _result(source_url=bad)
        assert result.source_url is None


def test_component_unavailable_must_omit_value_and_weight() -> None:
    with pytest.raises(ValidationError):
        MatchComponentEntry(
            name="skill_score",
            available=False,
            value=0.0,
            effective_weight=None,
        )
    with pytest.raises(ValidationError):
        MatchComponentEntry(
            name="skill_score",
            available=True,
            value=None,
            effective_weight=0.4,
        )


def test_available_component_requires_effective_weight() -> None:
    with pytest.raises(ValidationError):
        MatchComponentEntry(
            name="semantic_similarity",
            available=True,
            value=0.5,
            effective_weight=None,
        )


def test_match_result_rejects_missing_component_inventory() -> None:
    with pytest.raises(ValidationError):
        _result(components=_full_components(omit="skill_score"))


def test_match_result_rejects_single_component_payload() -> None:
    with pytest.raises(ValidationError):
        MatchResult(
            job_id=uuid4(),
            final_score=0.5,
            quality="full",
            components=[
                MatchComponentEntry(
                    name="semantic_similarity",
                    available=True,
                    value=0.5,
                    effective_weight=1.0,
                )
            ],
            seed_config_version="hybrid_seed_v1",
            contract_version=MATCH_RESULT_CONTRACT_VERSION,
        )


def test_match_result_rejects_available_missing_effective_weight() -> None:
    with pytest.raises(ValidationError):
        _result(components=_full_components(force_missing_weight="skill_score"))


def test_match_result_rejects_invalid_weight_total() -> None:
    # All six available but weights sum to 1.1 (outside tolerance).
    bad = {
        "semantic_similarity": (0.9, 0.4),
        "skill_score": (0.8, 0.4),
        "seniority_score": (1.0, 0.1),
        "experience_score": (1.0, 0.1),
        "location_score": (1.0, 0.05),
        "work_mode_score": (1.0, 0.05),
    }
    with pytest.raises(ValidationError):
        _result(components=_full_components(available_override=bad))


def test_match_result_accepts_unavailable_with_renormalized_weights() -> None:
    # Location/work_mode unavailable; remaining seed 0.90 renormalized to 1.0.
    partial = {
        "semantic_similarity": (0.9, 0.30 / 0.90),
        "skill_score": (0.8, 0.40 / 0.90),
        "seniority_score": (1.0, 0.10 / 0.90),
        "experience_score": (1.0, 0.10 / 0.90),
    }
    result = _result(components=_full_components(available_override=partial))
    assert len(result.components) == len(COMPONENT_ORDER)
    available = [c for c in result.components if c.available]
    assert len(available) == 4
    assert all(c.effective_weight is not None for c in available)
    assert abs(sum(c.effective_weight or 0.0 for c in available) - 1.0) < 1e-9
    unavailable = [c for c in result.components if not c.available]
    assert {c.name for c in unavailable} == {"location_score", "work_mode_score"}
    assert all(c.effective_weight is None and c.value is None for c in unavailable)


def test_unknown_component_name_rejected() -> None:
    with pytest.raises(ValidationError):
        MatchComponentEntry(
            name="llm_score",
            available=True,
            value=0.5,
            effective_weight=0.5,
        )


def test_provisional_kind_not_accepted() -> None:
    with pytest.raises(ValidationError):
        MatchSkillPath(
            canonical_key="x",
            display_name="X",
            match_kind="provisional",  # type: ignore[arg-type]
            strength=0.0,
        )


def test_related_requires_explicit_path() -> None:
    with pytest.raises(ValidationError):
        MatchSkillPath(
            canonical_key="k8s",
            display_name="K8s",
            match_kind="verified_related",
            strength=0.6,
            related_path=["only_one"],
        )


def test_collection_caps_at_ten() -> None:
    results = [_result(score=1.0 - (i * 0.01)) for i in range(MAX_MATCH_RESULTS)]
    collection = MatchResultCollection(
        results=results,
        seed_config_version="hybrid_seed_v1",
    )
    assert len(collection.results) == MAX_MATCH_RESULTS
    with pytest.raises(ValidationError):
        MatchResultCollection(
            results=results + [_result()],
            seed_config_version="hybrid_seed_v1",
        )


def test_collection_rejects_version_mismatch() -> None:
    item = _result(seed="hybrid_seed_v1")
    with pytest.raises(ValidationError):
        MatchResultCollection(
            results=[item],
            seed_config_version="other_seed",
        )


def test_explanation_line_bounds() -> None:
    long_line = "x" * (MAX_EXPLANATION_LINE_LEN + 50)
    result = _result()
    result = result.model_copy(
        update={
            "explanation_lines": [long_line] + [f"line {i}" for i in range(40)],
        }
    )
    # Re-validate through model_validate for field validators
    parsed = MatchResult.model_validate(result.model_dump(mode="json"))
    assert len(parsed.explanation_lines) <= MAX_EXPLANATION_LINES
    assert all(len(line) <= MAX_EXPLANATION_LINE_LEN for line in parsed.explanation_lines)


def test_score_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        _result(score=1.5)
    with pytest.raises(ValidationError):
        _result(score=-0.1)


def test_match_results_card_from_collection_and_parse_roundtrip() -> None:
    collection = MatchResultCollection(
        results=[_result(), _result(score=0.7)],
        seed_config_version="hybrid_seed_v1",
    )
    card = build_match_results_card(collection)
    assert card.kind == KIND_MATCH_RESULTS
    assert card.count == 2
    dumped = card.model_dump(mode="json")
    parsed = try_parse_match_results_card(dumped)
    assert parsed is not None
    assert parsed.model_dump(mode="json") == dumped
    assert "raw_content" not in dumped
    assert "vector" not in str(dumped).lower()


def test_try_parse_match_results_card_fail_closed() -> None:
    assert try_parse_match_results_card(None) is None
    assert try_parse_match_results_card({"kind": "saved_job"}) is None
    assert try_parse_match_results_card({"kind": "match_results"}) is None
    oversized = {
        "kind": "match_results",
        "contract_version": MATCH_RESULT_CONTRACT_VERSION,
        "seed_config_version": "hybrid_seed_v1",
        "count": 11,
        "results": [_result().model_dump(mode="json") for _ in range(11)],
    }
    assert try_parse_match_results_card(oversized) is None
    bad_count = {
        "kind": "match_results",
        "contract_version": MATCH_RESULT_CONTRACT_VERSION,
        "seed_config_version": "hybrid_seed_v1",
        "count": 2,
        "results": [_result().model_dump(mode="json")],
    }
    assert try_parse_match_results_card(bad_count) is None


def test_parse_match_jobs_tool_body_success_and_failures() -> None:
    collection = MatchResultCollection(
        results=[_result()],
        seed_config_version="hybrid_seed_v1",
    )
    body = {
        "ok": True,
        "status": "matched",
        "count": 1,
        "limit": 10,
        "contract_version": collection.contract_version,
        "seed_config_version": collection.seed_config_version,
        "results": [collection.results[0].model_dump(mode="json")],
    }
    import json

    parsed = parse_match_jobs_tool_body(json.dumps(body))
    assert parsed is not None
    assert len(parsed.results) == 1
    assert parse_match_jobs_tool_body('ERROR:{"code":"X","ok":false}') is None
    assert parse_match_jobs_tool_body(
        json.dumps(
            {
                "ok": True,
                "status": "profile_required",
                "results": [],
                "contract_version": MATCH_RESULT_CONTRACT_VERSION,
                "seed_config_version": "hybrid_seed_v1",
            }
        )
    ) is None
    assert parse_match_jobs_tool_body('{"ok":false,"status":"matched"}') is None
    assert match_jobs_public_outcome(json.dumps(body)) == MATCH_JOBS_OUTCOME_MATCHES_FOUND
    empty = dict(body)
    empty["results"] = []
    empty["count"] = 0
    assert match_jobs_public_outcome(json.dumps(empty)) == MATCH_JOBS_OUTCOME_NO_MATCHES
    assert (
        match_jobs_public_outcome(
            json.dumps({"ok": True, "status": "profile_required", "results": []})
        )
        == MATCH_JOBS_OUTCOME_PROFILE_REQUIRED
    )
    assert (
        match_jobs_public_outcome('ERROR:{"code":"MATCH_JOBS_FAILED","ok":false}')
        == MATCH_JOBS_OUTCOME_MATCH_FAILED
    )


def test_match_results_card_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MatchResultsCardPayload.model_validate(
            {
                "kind": "match_results",
                "contract_version": MATCH_RESULT_CONTRACT_VERSION,
                "seed_config_version": "hybrid_seed_v1",
                "count": 0,
                "results": [],
                "raw_tool_body": "secret",
            }
        )


def test_json_roundtrip_stable() -> None:
    job_id = UUID("00000000-0000-4000-8000-000000000001")
    result = _result(job_id=job_id)
    payload = result.model_dump(mode="json")
    again = MatchResult.model_validate(payload).model_dump(mode="json")
    assert again == payload
