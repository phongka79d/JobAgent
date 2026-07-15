"""Unit tests for compact match schemas and explanation projection (Plan 6 02D)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.schemas.jobs import JobSkill
from app.schemas.matching import (
    MatchJobsResultData,
    MatchResult,
    MatchSkillEvidence,
    parse_match_jobs_result_data,
    parse_match_result,
)
from app.schemas.profile import CandidateSkill
from app.schemas.skills import SkillRef
from app.services.match_components import (
    MatchScoreComponents,
    score_match_candidate,
)
from app.services.match_explanations import (
    MatchExplanationInput,
    project_match_jobs_result,
    project_match_result,
)
from app.services.skill_matching import compute_skill_coverage
from app.services.skill_normalization import SkillNormalizer
from pydantic import ValidationError

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"

PROHIBITED_FIELD_NAMES = frozenset(
    {
        "raw_content",
        "embedding_json",
        "profile_json",
        "draft_json",
        "storage_path",
        "provider_response",
        "api_key",
    }
)


@pytest.fixture
def normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(FIXTURE_PATH)


def _ref(
    canonical_key: str,
    *,
    display_name: str | None = None,
    aliases: list[str] | None = None,
) -> SkillRef:
    return SkillRef(
        canonical_key=canonical_key,
        display_name=display_name or canonical_key.title(),
        aliases=list(aliases or []),
        category=None,
    )


def _candidate(
    canonical_key: str,
    *,
    display_name: str | None = None,
    evidence: list[str] | None = None,
) -> CandidateSkill:
    return CandidateSkill(
        skill=_ref(canonical_key, display_name=display_name),
        confidence=0.9,
        proficiency="advanced",
        years=3.0,
        source="cv",
        excluded=False,
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


def _scored(
    *,
    job_id: str = "job-1",
    semantic: float = 0.8,
    skill_score: float | None = 0.52,
    seniority: float | None = 1.0,
    experience: float | None = 1.0,
    location: float | None = None,
    work_mode: float | None = 1.0,
    jd_quality: str = "full",
):
    return score_match_candidate(
        MatchScoreComponents(
            job_id=job_id,
            semantic_similarity=semantic,
            skill_score=skill_score,
            seniority_score=seniority,
            experience_score=experience,
            location_score=location,
            work_mode_score=work_mode,
            jd_quality=jd_quality,
        )
    )


def _input(
    normalizer: SkillNormalizer,
    *,
    job_id: str = "job-1",
    title: str | None = "Backend Engineer",
    company: str | None = "Acme",
    location: str | None = "Remote",
    work_mode: str = "remote",
    source_url: str | None = "https://example.com/jobs/1",
    required: list[JobSkill] | None = None,
    preferred: list[JobSkill] | None = None,
    candidates: list[CandidateSkill] | None = None,
    location_score: float | None = None,
) -> MatchExplanationInput:
    coverage = compute_skill_coverage(
        candidates
        or [
            _candidate("python", display_name="Python", evidence=["used Python"]),
            _candidate(
                "typescript",
                display_name="TypeScript",
                evidence=["used TypeScript"],
            ),
        ],
        required_skills=required
        or [
            _job("python", display_name="Python", evidence=["requires Python"]),
            _job("sql", display_name="SQL", evidence=["requires SQL"]),
        ],
        preferred_skills=preferred
        or [
            _job("react", display_name="React", evidence=["prefers React"]),
        ],
        normalizer=normalizer,
    )
    return MatchExplanationInput(
        scored=_scored(
            job_id=job_id,
            skill_score=coverage.skill_score,
            location=location_score,
        ),
        skill_coverage=coverage,
        title=title,
        company=company,
        location=location,
        work_mode=work_mode,  # type: ignore[arg-type]
        source_url=source_url,
    )


def test_projection_is_deterministic_and_validates(
    normalizer: SkillNormalizer,
) -> None:
    item = _input(normalizer)
    first = project_match_result(item)
    second = project_match_result(item)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.summary == second.summary
    assert first.summary != ""

    parsed = parse_match_result(first.model_dump(mode="json"))
    assert parsed == first


def test_direct_related_and_missing_evidence_trace_to_facts(
    normalizer: SkillNormalizer,
) -> None:
    item = _input(normalizer)
    result = project_match_result(item)

    assert len(result.matched_required_skills) == 1
    direct = result.matched_required_skills[0]
    assert direct.match_type == "direct"
    assert direct.job_skill_key == "python"
    assert direct.candidate_skill_key == "python"
    assert direct.strength == 1.0
    assert direct.job_evidence == ["requires Python"]
    assert direct.candidate_evidence == ["used Python"]
    assert direct.relationship_from_key is None

    assert len(result.related_skills) == 1
    related = result.related_skills[0]
    assert related.match_type == "related"
    assert related.job_skill_key == "react"
    assert related.candidate_skill_key == "typescript"
    assert related.strength == 0.6
    assert related.relationship_from_key == "typescript"
    assert related.relationship_to_key == "react"
    assert related.relationship_weight == 0.7
    assert related.relationship_source == "seed"
    assert related.job_evidence == ["prefers React"]

    assert len(result.missing_required_skills) == 1
    missing = result.missing_required_skills[0]
    assert missing.job_skill_key == "sql"
    assert missing.job_evidence == ["requires SQL"]

    assert result.matched_preferred_skills == []
    assert "Python" in result.summary
    assert "SQL" in result.summary
    assert "React" in result.summary
    assert "seed weight 0.7" in result.summary


def test_preferred_direct_match_and_unavailable_components(
    normalizer: SkillNormalizer,
) -> None:
    item = _input(
        normalizer,
        required=[_job("python", display_name="Python")],
        preferred=[_job("typescript", display_name="TypeScript")],
        candidates=[
            _candidate("python", display_name="Python"),
            _candidate("typescript", display_name="TypeScript"),
        ],
        location_score=None,
    )
    # Force more unavailable components on the scored side.
    scored = _scored(
        skill_score=item.skill_coverage.skill_score,
        seniority=None,
        experience=None,
        location=None,
        work_mode=None,
        jd_quality="partial",
    )
    item = MatchExplanationInput(
        scored=scored,
        skill_coverage=item.skill_coverage,
        title=item.title,
        company=item.company,
        location=None,
        work_mode="unknown",
        source_url=None,
    )
    result = project_match_result(item)

    assert result.quality_multiplier == 0.85
    assert result.components.seniority_score is None
    assert result.components.experience_score is None
    assert result.components.location_score is None
    assert result.components.work_mode_score is None
    assert "seniority_score" not in result.effective_weights
    assert "semantic_similarity" in result.effective_weights
    assert "skill_score" in result.effective_weights
    assert sum(result.effective_weights.values()) == pytest.approx(1.0)

    assert len(result.matched_required_skills) == 1
    assert result.matched_required_skills[0].match_type == "direct"
    assert len(result.matched_preferred_skills) == 1
    assert result.matched_preferred_skills[0].job_skill_key == "typescript"
    assert result.related_skills == []
    assert result.missing_required_skills == []
    assert "Unavailable components:" in result.summary
    assert "seniority_score" in result.summary
    assert result.source_url is None
    assert result.location is None


def test_gaps_only_required_zero_strength_not_preferred(
    normalizer: SkillNormalizer,
) -> None:
    item = _input(
        normalizer,
        required=[_job("python", display_name="Python")],
        preferred=[_job("go", display_name="Go")],
        candidates=[_candidate("python", display_name="Python")],
    )
    result = project_match_result(item)

    assert result.missing_required_skills == []
    assert result.matched_preferred_skills == []
    assert all(skill.job_skill_key != "go" for skill in result.related_skills)
    assert "Go" not in result.summary or "Missing" not in result.summary


def test_no_invented_skills_or_raw_payload_fields(
    normalizer: SkillNormalizer,
) -> None:
    item = _input(normalizer)
    result = project_match_result(item)
    payload = result.model_dump(mode="json")

    assert "embeddings" not in payload
    assert "raw_content" not in payload
    assert "embedding_json" not in payload
    assert all(name not in MatchResult.model_fields for name in PROHIBITED_FIELD_NAMES)
    assert all(
        name not in MatchSkillEvidence.model_fields for name in PROHIBITED_FIELD_NAMES
    )
    assert all(
        name not in MatchJobsResultData.model_fields for name in PROHIBITED_FIELD_NAMES
    )

    # Only skills present in 02A facts appear.
    all_keys = {
        *(s.job_skill_key for s in result.matched_required_skills),
        *(s.job_skill_key for s in result.matched_preferred_skills),
        *(s.job_skill_key for s in result.related_skills),
        *(s.job_skill_key for s in result.missing_required_skills),
    }
    assert all_keys == {"python", "sql", "react"}


def test_schema_rejects_extra_fields_and_invalid_relationship_coupling() -> None:
    with pytest.raises(ValidationError):
        MatchResult.model_validate(
            {
                "job_id": "j1",
                "title": None,
                "company": None,
                "location": None,
                "work_mode": "remote",
                "source_url": None,
                "final_score": 0.5,
                "quality_multiplier": 1.0,
                "components": {
                    "semantic_similarity": 0.5,
                    "skill_score": None,
                    "seniority_score": None,
                    "experience_score": None,
                    "location_score": None,
                    "work_mode_score": None,
                },
                "effective_weights": {"semantic_similarity": 1.0},
                "matched_required_skills": [],
                "matched_preferred_skills": [],
                "related_skills": [],
                "missing_required_skills": [],
                "summary": "ok",
                "raw_content": "secret",
            }
        )

    with pytest.raises(ValidationError):
        MatchSkillEvidence(
            job_skill_key="python",
            job_skill_display_name="Python",
            match_type="direct",
            strength=1.0,
            candidate_skill_key="python",
            candidate_skill_display_name="Python",
            job_evidence=["j"],
            candidate_evidence=["c"],
            relationship_from_key="python",
            relationship_to_key="python",
            relationship_weight=1.0,
            relationship_source="seed",
        )

    with pytest.raises(ValidationError):
        MatchSkillEvidence(
            job_skill_key="react",
            job_skill_display_name="React",
            match_type="related",
            strength=0.6,
            candidate_skill_key="typescript",
            candidate_skill_display_name="TypeScript",
            job_evidence=["j"],
            candidate_evidence=["c"],
        )


def test_project_match_jobs_result_preserves_order_and_count(
    normalizer: SkillNormalizer,
) -> None:
    first = _input(normalizer, job_id="job-a", title="A")
    second = _input(normalizer, job_id="job-b", title="B", company="Beta")
    data = project_match_jobs_result([first, second], limit=10)

    assert data.count == 2
    assert data.limit == 10
    assert [item.job_id for item in data.results] == ["job-a", "job-b"]
    assert data.results[0].summary == project_match_result(first).summary
    assert data.results[1].summary == project_match_result(second).summary

    parsed = parse_match_jobs_result_data(data.model_dump(mode="json"))
    assert parsed == data

    again = project_match_jobs_result([first, second], limit=10)
    assert again.model_dump(mode="json") == data.model_dump(mode="json")


def test_empty_skill_lists_do_not_invent_gaps_or_matches(
    normalizer: SkillNormalizer,
) -> None:
    coverage = compute_skill_coverage(
        [_candidate("python")],
        required_skills=[],
        preferred_skills=[],
        normalizer=normalizer,
    )
    scored = _scored(skill_score=coverage.skill_score, location=1.0)
    item = MatchExplanationInput(
        scored=scored,
        skill_coverage=coverage,
        title="Empty Skills Role",
        company="Co",
        location="Berlin",
        work_mode="onsite",
        source_url="https://example.com/x",
    )
    result = project_match_result(item)

    assert result.matched_required_skills == []
    assert result.matched_preferred_skills == []
    assert result.related_skills == []
    assert result.missing_required_skills == []
    assert result.components.skill_score is None
    assert "skill_score" not in result.effective_weights
    assert "Matched required" not in result.summary
    assert "Missing required" not in result.summary
    assert "Unavailable components: skill_score" in result.summary


def test_related_required_precedes_related_preferred_in_order(
    normalizer: SkillNormalizer,
) -> None:
    item = _input(
        normalizer,
        required=[_job("fastapi", display_name="FastAPI")],
        preferred=[_job("react", display_name="React")],
        candidates=[
            _candidate("python", display_name="Python"),
            _candidate("typescript", display_name="TypeScript"),
        ],
    )
    result = project_match_result(item)
    assert [s.job_skill_key for s in result.related_skills] == ["fastapi", "react"]
    assert result.matched_required_skills == []
    assert result.missing_required_skills == []
