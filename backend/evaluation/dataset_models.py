"""Versioned Plan 6 evaluation row and envelope contracts.

Row models carry IDs, labels, tokens, and digests only — never document bodies
or contact fields. Privacy normalization is delegated to ``dataset_privacy``.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from evaluation.dataset_privacy import (
    MAX_DIGEST_HEX_LEN,
    MAX_NOTES_LEN,
    MAX_SAFE_ID_LEN,
    MAX_SKILL_LIST,
    MAX_TOKEN_LEN,
    normalize_digest_hex,
    normalize_safe_id,
    normalize_token,
    normalize_token_list,
)

# ---------------------------------------------------------------------------
# Protocol identity and locked counts (Master §19 / Plan 6 §7.6)
# ---------------------------------------------------------------------------

PROTOCOL_ID: Final[Literal["plan6_matching_evaluation_v1"]] = (
    "plan6_matching_evaluation_v1"
)
SCHEMA_VERSION: Final[int] = 1
SPLIT_SCHEME: Final[Literal["fixed_seeded_60_20_20"]] = "fixed_seeded_60_20_20"
DEFAULT_SPLIT_SEED: Final[int] = 20260711

RELEVANCE_MIN: Final[int] = 150
RELEVANCE_MAX: Final[int] = 200
EXTRACTION_MIN: Final[int] = 30
TOOL_SCENARIOS_MIN: Final[int] = 50

RELEVANCE_LABEL_MIN: Final[int] = 0
RELEVANCE_LABEL_MAX: Final[int] = 3

SplitName = Literal["development", "validation", "held_out_test"]
AccessRole = Literal["tuning", "sealed_test"]

ToolScenarioCategory = Literal[
    "cv_upload",
    "profile_correction",
    "approval",
    "rejection",
    "jd_url_ingestion",
    "jd_text_ingestion",
    "duplicate_job",
    "match_with_profile",
    "match_without_profile",
    "unrelated_conversation",
    "tool_failure",
    "prompt_injection",
]

REQUIRED_TOOL_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "cv_upload",
        "profile_correction",
        "approval",
        "rejection",
        "jd_url_ingestion",
        "jd_text_ingestion",
        "duplicate_job",
        "match_with_profile",
        "match_without_profile",
        "unrelated_conversation",
        "tool_failure",
        "prompt_injection",
    }
)


class RelevanceLabelItem(BaseModel):
    """One public-JD relevance label (0-3). Entity ID only; no JD body."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    entity_id: str = Field(min_length=1, max_length=MAX_SAFE_ID_LEN)
    relevance: int = Field(ge=RELEVANCE_LABEL_MIN, le=RELEVANCE_LABEL_MAX)
    label_provenance: Literal["private_local", "synthetic"] = "private_local"

    @field_validator("entity_id")
    @classmethod
    def _entity_id(cls, value: str) -> str:
        return normalize_safe_id(value, field_name="entity_id")


class ExtractionAnnotationItem(BaseModel):
    """Manual extraction annotation over skill/seniority/mode/location tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    entity_id: str = Field(min_length=1, max_length=MAX_SAFE_ID_LEN)
    required_skills: list[str] = Field(default_factory=list, max_length=MAX_SKILL_LIST)
    preferred_skills: list[str] = Field(default_factory=list, max_length=MAX_SKILL_LIST)
    seniority: str = Field(min_length=1, max_length=MAX_TOKEN_LEN)
    work_mode: str = Field(min_length=1, max_length=MAX_TOKEN_LEN)
    location: str = Field(min_length=1, max_length=MAX_TOKEN_LEN)
    label_provenance: Literal["private_local", "synthetic"] = "private_local"

    @field_validator("entity_id")
    @classmethod
    def _entity_id(cls, value: str) -> str:
        return normalize_safe_id(value, field_name="entity_id")

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def _skills(cls, value: list[str], info: ValidationInfo) -> list[str]:
        field_name = info.field_name or "skills"
        return normalize_token_list(value, field_name=str(field_name))

    @field_validator("seniority", "work_mode", "location")
    @classmethod
    def _tokens(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "token"
        return normalize_token(value, field_name=str(field_name))


class ToolScenarioItem(BaseModel):
    """One tool-selection scenario. Outcomes are codes, not conversation bodies."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    scenario_id: str = Field(min_length=1, max_length=MAX_SAFE_ID_LEN)
    category: ToolScenarioCategory
    expected_tools: list[str] = Field(default_factory=list, max_length=16)
    expected_outcome: str = Field(min_length=1, max_length=MAX_TOKEN_LEN)
    prompt_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    label_provenance: Literal["private_local", "synthetic"] = "private_local"

    @field_validator("scenario_id")
    @classmethod
    def _scenario_id(cls, value: str) -> str:
        return normalize_safe_id(value, field_name="scenario_id")

    @field_validator("expected_tools")
    @classmethod
    def _tools(cls, value: list[str]) -> list[str]:
        return normalize_token_list(value, field_name="expected_tools", max_items=16)

    @field_validator("expected_outcome")
    @classmethod
    def _outcome(cls, value: str) -> str:
        return normalize_token(value, field_name="expected_outcome")

    @field_validator("prompt_digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        return normalize_digest_hex(value)


class CandidateReference(BaseModel):
    """One Candidate reference: digests only; no raw CV or contact fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    candidate_ref_id: str = Field(min_length=1, max_length=MAX_SAFE_ID_LEN)
    representation_version: str = Field(min_length=1, max_length=MAX_TOKEN_LEN)
    redacted_text_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    profile_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    preferences_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    label_provenance: Literal["private_local", "synthetic"] = "private_local"

    @field_validator("candidate_ref_id")
    @classmethod
    def _ref_id(cls, value: str) -> str:
        return normalize_safe_id(value, field_name="candidate_ref_id")

    @field_validator("representation_version")
    @classmethod
    def _rep_version(cls, value: str) -> str:
        return normalize_token(value, field_name="representation_version")

    @field_validator("redacted_text_digest", "profile_digest", "preferences_digest")
    @classmethod
    def _digests(cls, value: str) -> str:
        return normalize_digest_hex(value)


class RelevanceDataset(BaseModel):
    """Full relevance label set (private or synthetic)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    protocol_id: Literal["plan6_matching_evaluation_v1"] = PROTOCOL_ID
    split_seed: int = Field(default=DEFAULT_SPLIT_SEED, ge=0)
    items: list[RelevanceLabelItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_entities(self) -> RelevanceDataset:
        ids = [item.entity_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("relevance entity_id values must be unique")
        return self


class ExtractionDataset(BaseModel):
    """Full extraction annotation set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    protocol_id: Literal["plan6_matching_evaluation_v1"] = PROTOCOL_ID
    split_seed: int = Field(default=DEFAULT_SPLIT_SEED, ge=0)
    items: list[ExtractionAnnotationItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_entities(self) -> ExtractionDataset:
        ids = [item.entity_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("extraction entity_id values must be unique")
        return self


class ToolSelectionDataset(BaseModel):
    """Full tool-selection scenario set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    protocol_id: Literal["plan6_matching_evaluation_v1"] = PROTOCOL_ID
    split_seed: int = Field(default=DEFAULT_SPLIT_SEED, ge=0)
    items: list[ToolScenarioItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_scenarios(self) -> ToolSelectionDataset:
        ids = [item.scenario_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario_id values must be unique")
        return self


class AggregateDatasetManifest(BaseModel):
    """Aggregate-only inventory: counts and digests, never private rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    data_class: Literal["safe_aggregate"] = "safe_aggregate"
    protocol_id: Literal["plan6_matching_evaluation_v1"] = PROTOCOL_ID
    split_scheme: Literal["fixed_seeded_60_20_20"] = SPLIT_SCHEME
    split_seed: int = Field(default=DEFAULT_SPLIT_SEED, ge=0)
    relevance_count: int = Field(ge=0)
    extraction_count: int = Field(ge=0)
    tool_scenario_count: int = Field(ge=0)
    relevance_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    extraction_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    tool_selection_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    candidate_ref_digest: str = Field(min_length=64, max_length=MAX_DIGEST_HEX_LEN)
    notes: str = Field(default="", max_length=MAX_NOTES_LEN)

    @field_validator(
        "relevance_digest",
        "extraction_digest",
        "tool_selection_digest",
        "candidate_ref_digest",
    )
    @classmethod
    def _digest_fields(cls, value: str) -> str:
        return normalize_digest_hex(value)
