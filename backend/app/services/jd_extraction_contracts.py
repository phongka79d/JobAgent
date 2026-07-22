from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedJobSkillItem(BaseModel):
    """LLM skill row before deterministic SkillRef normalization."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description=(
            "Concise semantic label for one atomic professional capability, "
            "supported by verbatim evidence; never invent an unsupported skill."
        )
    )
    confidence: float
    evidence: list[str] = Field(
        description=(
            "Short verbatim snippets copied from the retained JD source; "
            "never paraphrase."
        )
    )


class ExtractedJobPost(BaseModel):
    """LLM structured output for JD facts (validated again downstream)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None
    company: str | None
    summary: str
    responsibilities: list[str]
    required_skills: list[ExtractedJobSkillItem]
    preferred_skills: list[ExtractedJobSkillItem]
    seniority: Literal["intern", "junior", "mid", "senior", "lead", "unknown"]
    min_experience_years: float | None
    max_experience_years: float | None
    location: str | None
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"]
    extraction_confidence: float
