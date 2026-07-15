"""Strict compact match response contracts (Plan 6 §7.7).

Backend-owned JSON shapes for ordered match results. Field names are locked
for ToolResult.data / history / future frontend fixtures. Models use
``extra="forbid"`` and never carry raw CV/JD bodies, embeddings, provider
payloads, storage paths, or secrets.

Scoring rules live in ``skill_matching`` and ``match_components``; this module
only validates compact projection output.
"""

from __future__ import annotations

from typing import Any, Literal

from app.schemas.common import StrictModelConfig
from app.schemas.jobs import JobWorkMode
from pydantic import BaseModel, Field, model_validator

MatchSkillMatchType = Literal["direct", "related"]


class MatchSkillEvidence(BaseModel):
    """One matched skill with winning Candidate evidence (direct or related)."""

    model_config = StrictModelConfig

    job_skill_key: str
    job_skill_display_name: str
    match_type: MatchSkillMatchType
    strength: float
    candidate_skill_key: str
    candidate_skill_display_name: str
    job_evidence: list[str]
    candidate_evidence: list[str]
    relationship_from_key: str | None = None
    relationship_to_key: str | None = None
    relationship_weight: float | None = None
    relationship_source: str | None = None

    @model_validator(mode="after")
    def couple_match_type_and_relationship(self) -> MatchSkillEvidence:
        """Direct matches omit seed edges; related matches require seed fields."""
        if self.match_type == "direct":
            if any(
                value is not None
                for value in (
                    self.relationship_from_key,
                    self.relationship_to_key,
                    self.relationship_weight,
                    self.relationship_source,
                )
            ):
                raise ValueError(
                    "direct match evidence must not include relationship fields"
                )
            return self
        if (
            self.relationship_from_key is None
            or self.relationship_to_key is None
            or self.relationship_weight is None
            or self.relationship_source is None
            or self.relationship_source.strip() == ""
        ):
            raise ValueError(
                "related match evidence requires seed relationship fields"
            )
        return self


class MissingRequiredSkill(BaseModel):
    """Required Job skill with best match strength zero (gap only)."""

    model_config = StrictModelConfig

    job_skill_key: str
    job_skill_display_name: str
    job_evidence: list[str]


class MatchComponentScores(BaseModel):
    """Unrounded component values; unavailable components are explicit nulls."""

    model_config = StrictModelConfig

    semantic_similarity: float
    skill_score: float | None
    seniority_score: float | None
    experience_score: float | None
    location_score: float | None
    work_mode_score: float | None


class MatchResult(BaseModel):
    """One compact ordered match result for tool/history/UI surfaces."""

    model_config = StrictModelConfig

    job_id: str = Field(min_length=1)
    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: JobWorkMode
    source_url: str | None = None
    final_score: float
    quality_multiplier: float
    components: MatchComponentScores
    effective_weights: dict[str, float]
    matched_required_skills: list[MatchSkillEvidence]
    matched_preferred_skills: list[MatchSkillEvidence]
    related_skills: list[MatchSkillEvidence]
    missing_required_skills: list[MissingRequiredSkill]
    summary: str = Field(min_length=1)


class MatchJobsResultData(BaseModel):
    """Compact ``match_jobs`` ToolResult.data: ordered results plus bounds."""

    model_config = StrictModelConfig

    results: list[MatchResult]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def couple_count_to_results(self) -> MatchJobsResultData:
        if self.count != len(self.results):
            raise ValueError("count must equal len(results)")
        if self.count > self.limit:
            raise ValueError("count must not exceed limit")
        return self


def parse_match_result(payload: Any) -> MatchResult:
    """Parse and validate one compact match result."""
    return MatchResult.model_validate(payload)


def parse_match_jobs_result_data(payload: Any) -> MatchJobsResultData:
    """Parse and validate compact match_jobs result data."""
    return MatchJobsResultData.model_validate(payload)


__all__ = [
    "MatchComponentScores",
    "MatchJobsResultData",
    "MatchResult",
    "MatchSkillEvidence",
    "MatchSkillMatchType",
    "MissingRequiredSkill",
    "parse_match_jobs_result_data",
    "parse_match_result",
]
