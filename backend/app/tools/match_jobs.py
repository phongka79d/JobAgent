"""Bounded read-only ``match_jobs`` Agent tool (Plan 6 / Master §13.7).

Requires an approved Candidate Profile, defaults to and caps at 10 results,
validates optional saved Job IDs (max 50), retries pending graph work before
retrieval, and returns sanitized guidance/failure states. Delegates embedding,
retrieval, scoring, and explanation to existing services — no formulas here.

Pipeline orchestration (profile load, embed, retrieve, score, cache) lives in
``match_jobs_pipeline`` so tool input/wrapper stay under the focused module
ceiling. Public imports remain on this module.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.matching import MAX_MATCH_RESULTS
from app.services.retrieval import MAX_RETRIEVAL_CANDIDATES
from app.tools.match_jobs_pipeline import (
    DEFAULT_MATCH_LIMIT,
    PROFILE_REQUIRED_GUIDANCE,
    MatchJobsToolService,
    tool_error,
)

MAX_SAVED_JOB_IDS: Final[int] = MAX_RETRIEVAL_CANDIDATES


class MatchJobsInput(BaseModel):
    """Strict LLM-visible args for top-N match with optional saved-ID filter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    limit: int | None = Field(default=None, ge=1, le=MAX_MATCH_RESULTS)
    saved_job_ids: list[UUID] | None = Field(
        default=None,
        max_length=MAX_SAVED_JOB_IDS,
    )

    @model_validator(mode="after")
    def _validate_saved_ids(self) -> MatchJobsInput:
        if self.limit is not None and (
            not isinstance(self.limit, int) or isinstance(self.limit, bool)
        ):
            raise ValueError("invalid limit")
        ids = self.saved_job_ids
        if ids is None:
            return self
        if not isinstance(ids, list):
            raise ValueError("invalid saved_job_ids")
        if len(ids) < 1:
            raise ValueError("saved_job_ids empty")
        if len(ids) > MAX_SAVED_JOB_IDS:
            raise ValueError("saved_job_ids exceed maximum")
        seen: set[UUID] = set()
        for item in ids:
            if not isinstance(item, UUID):
                raise ValueError("invalid saved_job_ids")
            if item in seen:
                raise ValueError("duplicate saved_job_ids")
            seen.add(item)
        return self


def create_match_jobs_tool(service: MatchJobsToolService) -> StructuredTool:
    """Create the strict read-only LangChain tool wrapper."""

    async def _match(
        limit: int | None = None,
        saved_job_ids: list[UUID] | None = None,
    ) -> str:
        try:
            parsed = MatchJobsInput(limit=limit, saved_job_ids=saved_job_ids)
        except ValidationError:
            return tool_error("MATCH_JOBS_INVALID_INPUT")
        return await service.execute(
            limit=parsed.limit,
            saved_job_ids=parsed.saved_job_ids,
        )

    return StructuredTool.from_function(
        coroutine=_match,
        name="match_jobs",
        description=(
            "Match the approved Candidate Profile to active saved jobs. "
            f"Defaults to top {DEFAULT_MATCH_LIMIT} (max {MAX_MATCH_RESULTS}). "
            f"Optional saved_job_ids filter (1–{MAX_SAVED_JOB_IDS} existing IDs). "
            "Requires an approved profile; retries pending graph work first."
        ),
        args_schema=MatchJobsInput,
    )


__all__ = [
    "DEFAULT_MATCH_LIMIT",
    "MAX_SAVED_JOB_IDS",
    "PROFILE_REQUIRED_GUIDANCE",
    "MatchJobsInput",
    "MatchJobsToolService",
    "create_match_jobs_tool",
]
