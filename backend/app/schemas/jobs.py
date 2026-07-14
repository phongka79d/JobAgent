"""Job extraction Pydantic contracts (Plan 5 §7.1 / Master §7.4).

Validated-model boundary for ``job_posts.extraction_json``
---------------------------------------------------------
ORM rows store opaque JSON. Before every write of ``extraction_json``, services
must validate a full ``JobPostExtraction`` and only persist
``model_dump(mode="json")`` of the accepted model.

Extraction contains facts and short source evidence only. The LLM must not
assign aliases, relationships, or ``jd_quality``. Authoritative quality lives
in ``job_posts.jd_quality`` via ``app.services.jd_quality`` after validation.

No ORM, provider, filesystem, graph, route, or Agent behavior lives here.
"""

from __future__ import annotations

from typing import Any, Literal

from app.schemas.common import StrictModelConfig
from app.schemas.skills import SkillRef
from pydantic import BaseModel, Field

# Exact enum vocabularies from Master §7.4 (job extraction only).
JobSeniority = Literal["intern", "junior", "mid", "senior", "lead", "unknown"]
JobWorkMode = Literal["remote", "hybrid", "onsite", "unknown"]


class JobSkill(BaseModel):
    """One skill assertion on a job extraction (Master §7.4)."""

    model_config = StrictModelConfig

    skill: SkillRef
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]


class JobPostExtraction(BaseModel):
    """Structured JD facts stored in ``extraction_json``.

    Distinct from the SQLAlchemy ``app.db.models.jobs.JobPost`` row type, which
    owns the table and opaque JSON column. ``jd_quality`` is never a field here.
    """

    model_config = StrictModelConfig

    title: str | None
    company: str | None
    summary: str
    responsibilities: list[str]
    required_skills: list[JobSkill]
    preferred_skills: list[JobSkill]
    seniority: JobSeniority
    min_experience_years: float | None
    max_experience_years: float | None
    location: str | None
    work_mode: JobWorkMode
    extraction_confidence: float = Field(ge=0.0, le=1.0)


def parse_job_post_extraction(payload: Any) -> JobPostExtraction:
    """Parse and validate full ``JobPostExtraction`` before extraction_json write."""
    return JobPostExtraction.model_validate(payload)
