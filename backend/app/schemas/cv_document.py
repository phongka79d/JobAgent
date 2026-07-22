"""Strict CVDocument / CVSection / CVEntry contracts (Master §7.2).

Validated boundary for ``document_json`` and extraction service outputs.
Dynamic section kinds and original headings are first-class; unknown headings
use ``kind='other'`` without requiring schema or Candidate Profile changes.

No ORM, provider, filesystem, graph, route, or Agent behavior lives here.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from app.schemas.common import StrictModelConfig, UuidStr
from pydantic import BaseModel, Field, field_validator, model_validator

# Exact section-kind vocabulary from Master §7.2.
CVSectionKind = Literal[
    "summary",
    "experience",
    "education",
    "skills",
    "languages",
    "certifications",
    "projects",
    "awards",
    "publications",
    "volunteering",
    "interests",
    "references",
    "other",
]

CV_SECTION_KINDS: Final[frozenset[str]] = frozenset(
    {
        "summary",
        "experience",
        "education",
        "skills",
        "languages",
        "certifications",
        "projects",
        "awards",
        "publications",
        "volunteering",
        "interests",
        "references",
        "other",
    }
)

AttributeValue = str | list[str]


def _require_sorted_unique_nonneg(values: list[int], *, field_name: str) -> list[int]:
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values):
        raise ValueError(f"{field_name} must contain non-negative integers")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must be unique")
    if values != sorted(values):
        raise ValueError(f"{field_name} must be ascending")
    return values


class CVEntry(BaseModel):
    """One ordered entry inside a CV section (Master §7.2)."""

    model_config = StrictModelConfig

    id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    title: str | None
    subtitle: str | None
    date_text: str | None
    location: str | None
    body: str
    bullets: list[str]
    attributes: dict[str, AttributeValue]
    source_chunk_ordinals: list[int]

    @field_validator("source_chunk_ordinals")
    @classmethod
    def _source_ordinals(cls, value: list[int]) -> list[int]:
        return _require_sorted_unique_nonneg(
            value, field_name="source_chunk_ordinals"
        )

    @field_validator("attributes")
    @classmethod
    def _attribute_values(
        cls, value: dict[str, AttributeValue]
    ) -> dict[str, AttributeValue]:
        for key, item in value.items():
            if not isinstance(key, str) or key == "":
                raise ValueError("attribute names must be non-empty strings")
            if isinstance(item, list):
                if any(not isinstance(x, str) for x in item):
                    raise ValueError("attribute list values must be strings")
            elif not isinstance(item, str):
                raise ValueError("attribute values must be str or list[str]")
        return value


class CVSection(BaseModel):
    """One ordered CV section with original heading and kind (Master §7.2)."""

    model_config = StrictModelConfig

    id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    heading: str = Field(min_length=1)
    kind: CVSectionKind
    entries: list[CVEntry]
    source_chunk_ordinals: list[int]

    @field_validator("source_chunk_ordinals")
    @classmethod
    def _source_ordinals(cls, value: list[int]) -> list[int]:
        return _require_sorted_unique_nonneg(
            value, field_name="source_chunk_ordinals"
        )

    @model_validator(mode="after")
    def _entry_order_and_sources(self) -> CVSection:
        for i, entry in enumerate(self.entries):
            if entry.ordinal != i:
                raise ValueError(
                    "section entries must have contiguous ordinals from 0"
                )
            for ord_ in entry.source_chunk_ordinals:
                if ord_ not in self.source_chunk_ordinals:
                    # Entry sources must be subset of section sources when both set.
                    # Empty section sources with entry sources is invalid identity.
                    raise ValueError(
                        "entry source_chunk_ordinals must be subset of section "
                        "source_chunk_ordinals"
                    )
        # Section sources must equal the union of entry sources when entries exist.
        if self.entries:
            union: set[int] = set()
            for entry in self.entries:
                union.update(entry.source_chunk_ordinals)
            if set(self.source_chunk_ordinals) != union:
                raise ValueError(
                    "section source_chunk_ordinals must equal the union of "
                    "entry source_chunk_ordinals"
                )
        return self


class CVDocument(BaseModel):
    """Complete ordered per-CV extraction (Master §7.2 ``document_json``)."""

    model_config = StrictModelConfig

    attachment_id: UuidStr
    detected_languages: list[str]
    sections: list[CVSection]
    extraction_warnings: list[str]
    extraction_confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _section_order(self) -> CVDocument:
        for i, section in enumerate(self.sections):
            if section.ordinal != i:
                raise ValueError(
                    "document sections must have contiguous ordinals from 0"
                )
        return self


def parse_cv_document(payload: Any) -> CVDocument:
    """Parse and validate a full ``CVDocument`` before document_json write."""
    return CVDocument.model_validate(payload)


__all__ = [
    "AttributeValue",
    "CV_SECTION_KINDS",
    "CVDocument",
    "CVEntry",
    "CVSection",
    "CVSectionKind",
    "parse_cv_document",
]
