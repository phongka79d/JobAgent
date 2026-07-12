"""Matching input and result contracts for Phase 5.

Owns:
- Versioned Candidate embedding surface (Plan 6 §7.1)
- Public re-exports of bounded MatchResult contracts (Plan 6 §7.5)

Match-result transport types live in ``matching_result`` so this module stays
focused on Candidate embedding identity/errors while preserving stable imports
from ``app.schemas.matching``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.schemas.matching_result import (
    MATCH_RESULT_CONTRACT_VERSION,
    MAX_COMPONENT_ENTRIES,
    MAX_EXPLANATION_LINE_LEN,
    MAX_EXPLANATION_LINES,
    MAX_MATCH_RESULTS,
    MAX_MATCH_SKILL_ITEMS,
    MAX_RANK_INPUTS,
    MAX_RELATED_PATH_KEYS,
    MatchComponentEntry,
    MatchingSchemaBase,
    MatchResult,
    MatchResultCollection,
    MatchSkillPath,
    VisibleMatchKind,
)

# ---------------------------------------------------------------------------
# Representation identity
# ---------------------------------------------------------------------------

CANDIDATE_TEXT_REPRESENTATION_VERSION: Final[str] = "candidate_embedding_text_v1"


# ---------------------------------------------------------------------------
# Sanitized failure surface
# ---------------------------------------------------------------------------


class CandidateEmbeddingErrorCode(StrEnum):
    """Stable, non-sensitive Candidate embedding failure codes."""

    REDACTION_FAILED = "candidate_redaction_failed"
    INVALID_INPUT = "candidate_embedding_invalid_input"
    TIMEOUT = "embedding_timeout"
    RATE_LIMIT = "embedding_rate_limit"
    CANCELLED = "embedding_cancelled"
    PROVIDER_ERROR = "embedding_provider_error"
    CONFIG = "embedding_config_error"
    MODEL_MISMATCH = "model_mismatch"
    VECTOR_COUNT_MISMATCH = "vector_count_mismatch"
    ORDERING_VIOLATION = "ordering_violation"
    DIMENSION_MISMATCH = "dimension_mismatch"
    NON_FINITE_VALUE = "non_finite_value"
    EMPTY_BATCH = "empty_batch"
    BATCH_SIZE_EXCEEDED = "batch_size_exceeded"
    DUPLICATE_VECTOR_INDEX = "duplicate_vector_index"


class CandidateEmbeddingError(Exception):
    """Sanitized Candidate embedding failure (code-only str/repr; no source text)."""

    def __init__(self, code: CandidateEmbeddingErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"CandidateEmbeddingError(code={self.code.value!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


# ---------------------------------------------------------------------------
# Embedding input surface
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CandidateEmbeddingFields:
    """Minimal Candidate surface for embedding text (no contact/storage/raw CV).

    Field order for representation assembly is fixed by the versioned builder:
    target roles, profile summary, verified non-excluded skills, experience
    titles, then remaining preference tokens (locations, work modes, seniority).
    """

    target_roles: tuple[str, ...] = ()
    summary: str = ""
    verified_skills: tuple[str, ...] = ()
    experience_titles: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    acceptable_work_modes: tuple[str, ...] = ()
    target_seniority: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateEmbeddingResult:
    """One validated Candidate vector plus locked model/version identity.

    ``values`` is exactly 1536 finite floats produced by the shared adapter.
    """

    index: int
    values: tuple[float, ...]
    model: str
    dimensions: int
    representation_version: str
    encoding: str = "float"

    @property
    def identity(self) -> dict[str, object]:
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "representation_version": self.representation_version,
            "encoding": self.encoding,
        }


__all__ = [
    "CANDIDATE_TEXT_REPRESENTATION_VERSION",
    "MATCH_RESULT_CONTRACT_VERSION",
    "MAX_COMPONENT_ENTRIES",
    "MAX_EXPLANATION_LINE_LEN",
    "MAX_EXPLANATION_LINES",
    "MAX_MATCH_RESULTS",
    "MAX_MATCH_SKILL_ITEMS",
    "MAX_RANK_INPUTS",
    "MAX_RELATED_PATH_KEYS",
    "CandidateEmbeddingError",
    "CandidateEmbeddingErrorCode",
    "CandidateEmbeddingFields",
    "CandidateEmbeddingResult",
    "MatchComponentEntry",
    "MatchResult",
    "MatchResultCollection",
    "MatchSkillPath",
    "MatchingSchemaBase",
    "VisibleMatchKind",
]
