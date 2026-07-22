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
    "Extract every source-supported professional capability, tool, method, platform, "
    "and domain practice from every supplied CV entry record; do not omit capabilities "
    "that are directly evidenced by the source. Return one concise semantic skill "
    "label per atomic capability. Each label must be supported by short verbatim "
    "evidence copied from its referenced records; never invent an unsupported skill. "
    "Return one assertion per distinct capability and merge repeated occurrences, "
    "source_entry_ids, and unique evidence in source order. Return confidence and only "
    "source-supported proficiency/years. Do not emit headings, group/category labels, "
    "employers, role titles, degrees, certificate titles, achievements, or generic "
    "nouns by themselves. Do not emit aliases, categories, or relationships. Preserve "
    "source order and return only structured JSON."
)

_REPAIR_INSTRUCTION: Final[str] = (
    "Previous structured output failed validation. Return a complete replacement "
    "candidate skill batch matching the schema, including every valid assertion from "
    "the supplied records. Use one concise semantic skill label supported by its "
    "evidence. Copy each evidence snippet exactly from the supplied source records. "
    "Omit any assertion whose evidence cannot be grounded in its referenced source "
    "entries. Keep one atomic capability per row, merge duplicate capabilities, "
    "preserve source order, and use only existing source_entry_ids."
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
        repair = (
            "\nREPAIR INSTRUCTIONS START\n"
            + _REPAIR_INSTRUCTION
            + "\nREPAIR INSTRUCTIONS END"
            + "\nSANITIZED ISSUES START\n"
            + json.dumps(
                safe,
                separators=(",", ":"),
            )
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
