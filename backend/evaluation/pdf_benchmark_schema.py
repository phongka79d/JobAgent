"""Typed schemas for the focused pypdf extraction benchmark (Phase 0).

Aggregate and per-run records intentionally exclude raw document text.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParserMode(StrEnum):
    NORMAL = "normal"
    LAYOUT = "layout"


class ExtractionOutcome(StrEnum):
    EXTRACTED_TEXT = "EXTRACTED_TEXT"
    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"


class BenchmarkRecord(BaseModel):
    """One fixture × mode measurement. No raw document text fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_id: str = Field(min_length=1)
    page_count: int = Field(ge=0)
    parser_mode: ParserMode
    extracted_character_count: int = Field(ge=0)
    elapsed_milliseconds: int = Field(ge=0)
    outcome: ExtractionOutcome

    @field_validator("fixture_id")
    @classmethod
    def fixture_id_is_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("fixture_id must be non-empty")
        return stripped


class ModeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parser_mode: ParserMode
    record_count: int = Field(ge=0)
    extracted_text_count: int = Field(ge=0)
    no_extractable_text_count: int = Field(ge=0)
    extraction_error_count: int = Field(ge=0)
    total_extracted_characters: int = Field(ge=0)
    total_elapsed_milliseconds: int = Field(ge=0)


class AggregateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    fixture_ids_in_order: list[str]
    modes_in_order: list[ParserMode]
    by_mode: list[ModeSummary]


class AggregateBenchmarkResult(BaseModel):
    """Machine-readable aggregate artifact (safe metrics only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    data_class: Literal["safe_aggregate"] = "safe_aggregate"
    manifest_id: str | None = None
    frozen_manifest_path: str
    path_mapping_source: str
    parser_library: str = "pypdf"
    parser_modes: list[ParserMode]
    ocr_used: Literal[False] = False
    alternate_parser_used: Literal[False] = False
    records: list[BenchmarkRecord]
    summary: AggregateSummary
