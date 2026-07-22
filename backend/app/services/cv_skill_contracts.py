"""Strict provider contracts and immutable Candidate-skill source DTOs."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.cv_document import CVSection

DEFAULT_SKILL_BATCH_MAX_CHARS: Final[int] = 6000
FAILURE_INVALID_STRUCTURED_OUTPUT: Final[str] = "INVALID_STRUCTURED_OUTPUT"
MAX_ASSERTIONS_PER_BATCH: Final[int] = 200
MAX_EVIDENCE_PER_ASSERTION: Final[int] = 8
MAX_EVIDENCE_LENGTH: Final[int] = 240
MAX_SOURCE_ENTRY_IDS: Final[int] = 20
MAX_GUARD_ISSUES: Final[int] = 20

SkillProficiency = Literal["beginner", "intermediate", "advanced", "unknown"]
PromptAttribute = str | tuple[str, ...]


class CandidateSkillExtractionError(Exception):
    """Candidate skill extraction failed with a stable safe code/message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ExtractedCandidateSkillAssertion(BaseModel):
    """Strict internal provider assertion before normalization/persistence."""

    model_config = ConfigDict(extra="forbid")

    name: str
    confidence: float
    proficiency: SkillProficiency
    years: float | None
    evidence: list[str]
    source_entry_ids: list[str]

    @model_validator(mode="after")
    def _bounded_shape(self) -> ExtractedCandidateSkillAssertion:
        if not self.name.strip() or len(self.name) > 160:
            raise ValueError("name must be non-blank and at most 160 characters")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.years is not None and self.years < 0:
            raise ValueError("years must be non-negative")
        if not 1 <= len(self.evidence) <= MAX_EVIDENCE_PER_ASSERTION:
            raise ValueError("evidence count is out of bounds")
        if any(
            not item.strip() or len(item) > MAX_EVIDENCE_LENGTH
            for item in self.evidence
        ):
            raise ValueError("evidence must contain short non-blank snippets")
        if not 1 <= len(self.source_entry_ids) <= MAX_SOURCE_ENTRY_IDS:
            raise ValueError("source_entry_ids count is out of bounds")
        if len(set(self.source_entry_ids)) != len(self.source_entry_ids):
            raise ValueError("source_entry_ids must be unique")
        return self


class ExtractedCandidateSkillBatch(BaseModel):
    """Strict provider response for one bounded source batch."""

    model_config = ConfigDict(extra="forbid")

    assertions: list[ExtractedCandidateSkillAssertion]

    @model_validator(mode="after")
    def _bounded_assertions(self) -> ExtractedCandidateSkillBatch:
        if len(self.assertions) > MAX_ASSERTIONS_PER_BATCH:
            raise ValueError("assertion count exceeds batch bound")
        return self


class StructuredCandidateSkillInvoker(Protocol):
    """Fake-testable structured Candidate skill provider boundary."""

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        schema_name: str,
        is_repair: bool = False,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class CandidateSkillSourceRecord:
    """One source-ordered, allowlisted CV entry projection or fragment."""

    source_order: int
    section_id: str
    section_heading: str
    section_kind: str
    entry_id: str
    entry_ordinal: int
    title: str | None
    subtitle: str | None
    date_text: str | None
    location: str | None
    body: str
    bullets: tuple[str, ...]
    attributes: tuple[tuple[str, PromptAttribute], ...]

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "section_heading": self.section_heading,
            "section_kind": self.section_kind,
            "entry_id": self.entry_id,
            "entry_ordinal": self.entry_ordinal,
            "title": self.title,
            "subtitle": self.subtitle,
            "date_text": self.date_text,
            "location": self.location,
            "body": self.body,
            "bullets": list(self.bullets),
            "attributes": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in self.attributes
            },
        }

    def source_text(self) -> str:
        values = [
            self.title or "",
            self.subtitle or "",
            self.date_text or "",
            self.location or "",
            self.body,
            *self.bullets,
        ]
        for _, value in self.attributes:
            values.extend(value if isinstance(value, tuple) else (value,))
        return "\n".join(item for item in values if item)


@dataclass(frozen=True, slots=True)
class CandidateSkillBatch:
    records: tuple[CandidateSkillSourceRecord, ...]
    serialized_records: str

    @property
    def char_count(self) -> int:
        return len(self.serialized_records)

    @property
    def entry_ids(self) -> frozenset[str]:
        return frozenset(record.entry_id for record in self.records)

    def source_text_for(self, entry_ids: Sequence[str]) -> str:
        selected = set(entry_ids)
        return "\n".join(
            record.source_text()
            for record in self.records
            if record.entry_id in selected
        )


@dataclass(frozen=True, slots=True)
class CandidateSkillEntryContext:
    section: CVSection
    source_order: int
    substantive_text: str
    metadata_values: tuple[str, ...]


def serialize_source_records(
    records: Sequence[CandidateSkillSourceRecord],
) -> str:
    return json.dumps(
        [record.as_prompt_dict() for record in records],
        ensure_ascii=False,
        separators=(",", ":"),
    )


__all__ = [
    "CandidateSkillBatch",
    "CandidateSkillEntryContext",
    "CandidateSkillExtractionError",
    "CandidateSkillSourceRecord",
    "DEFAULT_SKILL_BATCH_MAX_CHARS",
    "ExtractedCandidateSkillAssertion",
    "ExtractedCandidateSkillBatch",
    "FAILURE_INVALID_STRUCTURED_OUTPUT",
    "MAX_EVIDENCE_LENGTH",
    "MAX_EVIDENCE_PER_ASSERTION",
    "MAX_GUARD_ISSUES",
    "StructuredCandidateSkillInvoker",
]
