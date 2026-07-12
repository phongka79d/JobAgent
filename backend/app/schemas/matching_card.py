"""Bounded match-results card for chat structured_payload / run_completed.

Reuses validated ``MatchResult`` items from the tool pipeline. Fail-closed
parsers never surface raw tool args, vectors, provider payloads, or secrets.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.matching_result import (
    MATCH_RESULT_CONTRACT_VERSION,
    MAX_MATCH_RESULTS,
    MatchingSchemaBase,
    MatchResult,
    MatchResultCollection,
)

KIND_MATCH_RESULTS: Final[str] = "match_results"

# Allowlisted public tool-activity outcome tokens for match_jobs (never raw body).
MATCH_JOBS_OUTCOME_MATCHES_FOUND: Final[str] = "matches_found"
MATCH_JOBS_OUTCOME_NO_MATCHES: Final[str] = "no_matches"
MATCH_JOBS_OUTCOME_PROFILE_REQUIRED: Final[str] = "profile_required"
MATCH_JOBS_OUTCOME_MATCH_FAILED: Final[str] = "match_failed"


class MatchResultsCardPayload(MatchingSchemaBase):
    """Minimal top-match card for live SSE and durable history.

    Discriminator ``kind=match_results`` extends the existing structured-payload
    tagged union alongside ``saved_job``. Contains only visible match fields.
    """

    kind: Literal["match_results"] = "match_results"
    contract_version: str = Field(
        default=MATCH_RESULT_CONTRACT_VERSION,
        min_length=1,
        max_length=64,
    )
    seed_config_version: str = Field(..., min_length=1, max_length=64)
    count: int = Field(..., ge=0, le=MAX_MATCH_RESULTS)
    results: list[MatchResult] = Field(
        default_factory=list,
        max_length=MAX_MATCH_RESULTS,
    )

    @field_validator("contract_version", "seed_config_version")
    @classmethod
    def _version_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("empty version identity")
        return cleaned

    @model_validator(mode="after")
    def _count_and_identity(self) -> MatchResultsCardPayload:
        if len(self.results) > MAX_MATCH_RESULTS:
            raise ValueError("results exceed top-10 cap")
        if self.count != len(self.results):
            raise ValueError("count must equal results length")
        for item in self.results:
            if item.contract_version != self.contract_version:
                raise ValueError("result contract_version mismatch")
            if item.seed_config_version != self.seed_config_version:
                raise ValueError("result seed_config_version mismatch")
        return self


def build_match_results_card(
    collection: MatchResultCollection,
) -> MatchResultsCardPayload:
    """Map a validated ranked collection to the shared chat card payload."""
    return MatchResultsCardPayload(
        kind="match_results",
        contract_version=collection.contract_version,
        seed_config_version=collection.seed_config_version,
        count=len(collection.results),
        results=list(collection.results),
    )


def try_parse_match_results_card(
    raw: Mapping[str, Any] | None,
) -> MatchResultsCardPayload | None:
    """Fail-closed parse of a match-results card (history / SSE / finalize)."""
    if raw is None or not isinstance(raw, Mapping):
        return None
    if str(raw.get("kind", "")).strip().lower() != KIND_MATCH_RESULTS:
        return None
    try:
        return MatchResultsCardPayload.model_validate(dict(raw))
    except Exception:
        return None


def parse_match_jobs_tool_body(
    text: str | None,
) -> MatchResultCollection | None:
    """Parse a successful ``match_jobs`` tool JSON body for card/outcome only.

    Returns a validated collection only for ``status=matched`` with ok truthy.
    ERROR bodies, profile guidance, and malformed payloads return ``None``.
    """
    if not text or not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped or stripped.startswith("ERROR:"):
        return None
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("ok") is False:
        return None
    status = str(data.get("status", "")).strip().lower()
    if status != "matched":
        return None
    results = data.get("results")
    if not isinstance(results, list):
        return None
    if len(results) > MAX_MATCH_RESULTS:
        return None
    contract = data.get("contract_version")
    seed = data.get("seed_config_version")
    if not isinstance(contract, str) or not contract.strip():
        return None
    if not isinstance(seed, str) or not seed.strip():
        return None
    try:
        return MatchResultCollection(
            results=results,
            contract_version=contract.strip(),
            seed_config_version=seed.strip(),
        )
    except Exception:
        return None


def match_jobs_public_outcome(text: str | None) -> str:
    """Map a ``match_jobs`` tool body to one allowlisted public outcome token."""
    if not text or not isinstance(text, str):
        return MATCH_JOBS_OUTCOME_MATCH_FAILED
    stripped = text.strip()
    if not stripped or stripped.startswith("ERROR:"):
        return MATCH_JOBS_OUTCOME_MATCH_FAILED
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError, ValueError):
        return MATCH_JOBS_OUTCOME_MATCH_FAILED
    if not isinstance(data, dict):
        return MATCH_JOBS_OUTCOME_MATCH_FAILED
    if data.get("ok") is False:
        return MATCH_JOBS_OUTCOME_MATCH_FAILED
    status = str(data.get("status", "")).strip().lower()
    if status == "profile_required":
        return MATCH_JOBS_OUTCOME_PROFILE_REQUIRED
    if status != "matched":
        return MATCH_JOBS_OUTCOME_MATCH_FAILED
    results = data.get("results")
    if not isinstance(results, list):
        return MATCH_JOBS_OUTCOME_MATCH_FAILED
    if len(results) == 0:
        return MATCH_JOBS_OUTCOME_NO_MATCHES
    return MATCH_JOBS_OUTCOME_MATCHES_FOUND


__all__ = [
    "KIND_MATCH_RESULTS",
    "MATCH_JOBS_OUTCOME_MATCH_FAILED",
    "MATCH_JOBS_OUTCOME_MATCHES_FOUND",
    "MATCH_JOBS_OUTCOME_NO_MATCHES",
    "MATCH_JOBS_OUTCOME_PROFILE_REQUIRED",
    "MatchResultsCardPayload",
    "build_match_results_card",
    "match_jobs_public_outcome",
    "parse_match_jobs_tool_body",
    "try_parse_match_results_card",
]
