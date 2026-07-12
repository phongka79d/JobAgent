"""Bounded MatchResult transport contracts (Plan 6 §7.5).

Owns top-10 bounds, full component inventory, skill paths, and fail-closed URLs.
Embedding inputs live in ``matching``; formulas live in services.
"""

from __future__ import annotations

import math
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.candidate import (
    MAX_CANONICAL_KEY_LEN,
    MAX_DISPLAY_NAME_LEN,
    MAX_ORG_LEN,
    MAX_TITLE_LEN,
)
from app.schemas.job_post import MAX_LOCATION_LEN
from app.schemas.job_tools import MAX_SOURCE_URL_LEN, safe_public_source_url
from app.schemas.score_breakdown import (
    COMPONENT_ORDER,
    WEIGHT_SUM_TOLERANCE,
    ScoreComponentName,
)

MATCH_RESULT_CONTRACT_VERSION: Final[str] = "match_result_v1"
MAX_RANK_INPUTS: Final[int] = 50
MAX_MATCH_RESULTS: Final[int] = 10
MAX_EXPLANATION_LINES: Final[int] = 16
MAX_EXPLANATION_LINE_LEN: Final[int] = 256
MAX_MATCH_SKILL_ITEMS: Final[int] = 30
MAX_RELATED_PATH_KEYS: Final[int] = 4
MAX_COMPONENT_ENTRIES: Final[int] = len(COMPONENT_ORDER)
VisibleMatchKind = Literal["direct", "verified_alias", "verified_related", "no_match"]


class MatchingSchemaBase(BaseModel):
    """Strict extra-forbid base for match transport documents."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MatchComponentEntry(MatchingSchemaBase):
    """One component value plus effective weight when available."""

    name: str = Field(..., min_length=1, max_length=64)
    available: bool
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_weight: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def _known_component(cls, value: str) -> str:
        cleaned = value.strip()
        allowed = {item.value for item in ScoreComponentName}
        if cleaned not in allowed:
            raise ValueError(f"unknown component name: {cleaned}")
        return cleaned

    @model_validator(mode="after")
    def _availability_consistency(self) -> MatchComponentEntry:
        if not self.available:
            if self.value is not None or self.effective_weight is not None:
                raise ValueError("unavailable component must omit value and weight")
            return self
        if self.value is None:
            raise ValueError("available component requires a finite unit value")
        weight = self.effective_weight
        if weight is None or not math.isfinite(weight):
            raise ValueError("available component requires a finite effective weight")
        return self


class MatchSkillPath(MatchingSchemaBase):
    """Bounded skill path for cards/explanations — no raw evidence bodies."""

    canonical_key: str = Field(..., min_length=1, max_length=MAX_CANONICAL_KEY_LEN)
    display_name: str = Field(..., min_length=1, max_length=MAX_DISPLAY_NAME_LEN)
    match_kind: VisibleMatchKind
    strength: float = Field(..., ge=0.0, le=1.0)
    related_path: list[str] = Field(default_factory=list, max_length=MAX_RELATED_PATH_KEYS)
    candidate_canonical_key: str | None = Field(default=None, max_length=MAX_CANONICAL_KEY_LEN)

    @field_validator("canonical_key", "display_name")
    @classmethod
    def _required_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("empty skill identity")
        return cleaned

    @field_validator("candidate_canonical_key")
    @classmethod
    def _optional_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("related_path")
    @classmethod
    def _bound_path(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            token = item.strip()
            if not token:
                continue
            if len(token) > MAX_CANONICAL_KEY_LEN:
                token = token[:MAX_CANONICAL_KEY_LEN]
            cleaned.append(token)
            if len(cleaned) >= MAX_RELATED_PATH_KEYS:
                break
        return cleaned

    @model_validator(mode="after")
    def _kind_rules(self) -> MatchSkillPath:
        if self.match_kind == "verified_related":
            if len(self.related_path) < 2:
                raise ValueError("verified_related requires an explicit path")
            if self.strength <= 0.0:
                raise ValueError("verified_related strength must be positive")
        if self.match_kind in {"direct", "verified_alias"} and self.strength <= 0.0:
            raise ValueError("matched skills require positive strength")
        if self.match_kind == "no_match" and self.strength != 0.0:
            raise ValueError("missing required skills must have strength 0")
        return self


class MatchResult(MatchingSchemaBase):
    """Transparent top-match result: full locked component inventory required."""

    job_id: UUID
    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    company: str | None = Field(default=None, max_length=MAX_ORG_LEN)
    location: str | None = Field(default=None, max_length=MAX_LOCATION_LEN)
    work_mode: str | None = Field(default=None, max_length=64)
    final_score: float = Field(..., ge=0.0, le=1.0)
    quality: Literal["full", "partial"]
    components: list[MatchComponentEntry] = Field(
        ...,
        min_length=MAX_COMPONENT_ENTRIES,
        max_length=MAX_COMPONENT_ENTRIES,
    )
    matched_required_skills: list[MatchSkillPath] = Field(
        default_factory=list, max_length=MAX_MATCH_SKILL_ITEMS
    )
    related_skills: list[MatchSkillPath] = Field(
        default_factory=list, max_length=MAX_MATCH_SKILL_ITEMS
    )
    missing_required_skills: list[MatchSkillPath] = Field(
        default_factory=list, max_length=MAX_MATCH_SKILL_ITEMS
    )
    explanation_lines: list[str] = Field(
        default_factory=list, max_length=MAX_EXPLANATION_LINES
    )
    source_url: str | None = Field(default=None, max_length=MAX_SOURCE_URL_LEN)
    seed_config_version: str = Field(..., min_length=1, max_length=64)
    contract_version: str = Field(
        default=MATCH_RESULT_CONTRACT_VERSION, min_length=1, max_length=64
    )

    @field_validator("title", "company", "location", "work_mode")
    @classmethod
    def _optional_display(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(str(value).strip().split())
        return cleaned or None

    @field_validator("source_url")
    @classmethod
    def _safe_source_url(cls, value: str | None) -> str | None:
        return safe_public_source_url(value)

    @field_validator("explanation_lines", mode="before")
    @classmethod
    def _bound_explanations(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            text = " ".join(item.strip().split())
            if not text:
                continue
            if len(text) > MAX_EXPLANATION_LINE_LEN:
                text = text[:MAX_EXPLANATION_LINE_LEN]
            cleaned.append(text)
            if len(cleaned) >= MAX_EXPLANATION_LINES:
                break
        return cleaned

    @field_validator("seed_config_version", "contract_version")
    @classmethod
    def _version_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("empty version identity")
        return cleaned

    @model_validator(mode="after")
    def _component_inventory(self) -> MatchResult:
        expected = {name.value for name in COMPONENT_ORDER}
        names = [entry.name for entry in self.components]
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError(
                "components must list each locked COMPONENT_ORDER entry exactly once"
            )

        available_weights: list[float] = []
        for entry in self.components:
            if not entry.available:
                continue
            weight = entry.effective_weight
            if weight is None or not math.isfinite(weight):
                raise ValueError("available component requires a finite effective weight")
            available_weights.append(weight)
        if not available_weights:
            raise ValueError("scored result requires at least one available component")
        if abs(sum(available_weights) - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError("effective available weights must sum to one within tolerance")

        for path in self.related_skills:
            if path.match_kind != "verified_related":
                raise ValueError("related_skills must be verified_related only")
        for path in self.matched_required_skills:
            if path.match_kind not in {"direct", "verified_alias"}:
                raise ValueError("matched_required_skills must be direct/alias only")
        for path in self.missing_required_skills:
            if path.match_kind != "no_match":
                raise ValueError("missing_required_skills must be no_match only")
        return self


class MatchResultCollection(MatchingSchemaBase):
    """Ordered top-10 match results with contract/config identity."""

    results: list[MatchResult] = Field(default_factory=list, max_length=MAX_MATCH_RESULTS)
    contract_version: str = Field(
        default=MATCH_RESULT_CONTRACT_VERSION, min_length=1, max_length=64
    )
    seed_config_version: str = Field(..., min_length=1, max_length=64)

    @field_validator("contract_version", "seed_config_version")
    @classmethod
    def _version_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("empty version identity")
        return cleaned

    @model_validator(mode="after")
    def _bound_and_identity(self) -> MatchResultCollection:
        if len(self.results) > MAX_MATCH_RESULTS:
            raise ValueError("results exceed top-10 cap")
        for item in self.results:
            if item.contract_version != self.contract_version:
                raise ValueError("result contract_version mismatch")
            if item.seed_config_version != self.seed_config_version:
                raise ValueError("result seed_config_version mismatch")
        return self


__all__ = [
    "MATCH_RESULT_CONTRACT_VERSION",
    "MAX_COMPONENT_ENTRIES",
    "MAX_EXPLANATION_LINE_LEN",
    "MAX_EXPLANATION_LINES",
    "MAX_MATCH_RESULTS",
    "MAX_MATCH_SKILL_ITEMS",
    "MAX_RANK_INPUTS",
    "MAX_RELATED_PATH_KEYS",
    "MatchComponentEntry",
    "MatchResult",
    "MatchResultCollection",
    "MatchSkillPath",
    "MatchingSchemaBase",
    "VisibleMatchKind",
]
