"""Bounded provider invocation and one sanitized Candidate-skill repair."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, Final

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.services.cv_skill_contracts import (
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    CandidateSkillBatch,
    CandidateSkillExtractionError,
    ExtractedCandidateSkillBatch,
    StructuredCandidateSkillInvoker,
)
from app.services.provider_retry import ProviderRetryError, invoke_with_provider_retry
from app.services.skill_assertion_guard import (
    StructuralSkillIssue,
    structural_issue,
)

_MAX_REPAIR_ATTEMPTS: Final[int] = 1

_SYSTEM_PROMPT: Final[str] = (
    "Extract explicit professional capabilities, tools, methods, platforms, and "
    "domain practices from every supplied CV entry record. Return one atomic source "
    "label per assertion with confidence, supported proficiency/years, short verbatim "
    "evidence, and existing source_entry_ids. Do not emit headings, group/category "
    "labels, employers, role titles, degrees, certificate titles, achievements, or "
    "generic nouns by themselves. Do not emit aliases, categories, or relationships. "
    "Preserve source order and return only structured JSON."
)

GuardCandidateBatch = Callable[
    [ExtractedCandidateSkillBatch],
    tuple[StructuralSkillIssue, ...],
]


def _coerce_batch(raw: Any) -> ExtractedCandidateSkillBatch:
    if isinstance(raw, ExtractedCandidateSkillBatch):
        return raw
    if isinstance(raw, str):
        return ExtractedCandidateSkillBatch.model_validate_json(raw)
    return ExtractedCandidateSkillBatch.model_validate(raw)


def _messages(
    batch: CandidateSkillBatch,
    issues: Sequence[StructuralSkillIssue] = (),
) -> list[Any]:
    repair = ""
    if issues:
        safe = [
            {
                "code": issue.code,
                "field_path": issue.field_path,
                "count": issue.count,
            }
            for issue in issues
        ]
        repair = "\nSANITIZED ISSUES START\n" + json.dumps(
            safe,
            separators=(",", ":"),
        )
    return [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "CV ENTRY RECORDS START\n"
                + batch.serialized_records
                + "\nCV ENTRY RECORDS END"
                + repair
            )
        ),
    ]


def invoke_candidate_skill_batch(
    batch: CandidateSkillBatch,
    *,
    invoker: StructuredCandidateSkillInvoker,
    guard: GuardCandidateBatch,
) -> tuple[ExtractedCandidateSkillBatch, int, int]:
    """Invoke one batch with shared retries and at most one sanitized repair."""
    repairs = 0
    retries_total = 0
    issues: tuple[StructuralSkillIssue, ...] = ()
    while True:
        messages = _messages(batch, issues)

        def _call() -> Any:
            return invoker.invoke_structured(
                messages,
                schema_name="candidate_skills",
                is_repair=repairs > 0,
            )

        try:
            raw, retries = invoke_with_provider_retry(_call)
            retries_total += retries
            extracted = _coerce_batch(raw)
            issues = guard(extracted)
            if not issues:
                return extracted, repairs, retries_total
        except ProviderRetryError as exc:
            raise CandidateSkillExtractionError(exc.code, exc.message) from exc
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            error_count = len(exc.errors()) if isinstance(exc, ValidationError) else 1
            issues = (
                structural_issue(
                    "SCHEMA_VALIDATION_FAILED",
                    "assertions",
                    count=max(1, error_count),
                ),
            )
        if repairs >= _MAX_REPAIR_ATTEMPTS:
            raise CandidateSkillExtractionError(
                FAILURE_INVALID_STRUCTURED_OUTPUT,
                "Candidate skill output invalid after one repair attempt",
            )
        repairs += 1


__all__ = ["invoke_candidate_skill_batch"]
