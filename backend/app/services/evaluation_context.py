"""Pure canonical evaluation context hashing and currentness derivation.

Server-side facts only: Job revision, active attachment, approved CV source
hash, profile/preferences revisions, and matching-contract version. Clients
never supply hashes, revision fields, or none|current|stale state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

# Explicit matching/scoring/explanation contract version for context keys.
MATCHING_CONTRACT_VERSION = "match_v1"

EvaluationCurrentness = Literal["none", "current", "stale"]

_CONTEXT_KEYS = (
    "active_attachment_id",
    "cv_source_hash",
    "job_id",
    "job_revision",
    "matching_contract_version",
    "preferences_revision",
    "profile_revision",
)


class EvaluationContextError(Exception):
    """Raised when context facts are incomplete or non-canonical."""


@dataclass(frozen=True, slots=True)
class EvaluationContextFacts:
    """Server-loaded revision tuple used for one evaluation context key."""

    job_id: str
    job_revision: datetime
    active_attachment_id: str
    cv_source_hash: str
    profile_revision: datetime
    preferences_revision: datetime
    matching_contract_version: str = MATCHING_CONTRACT_VERSION


def _require_nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise EvaluationContextError(f"{name} must be a non-empty string")
    return value


def _canonical_timestamp(value: datetime, *, field: str) -> str:
    if not isinstance(value, datetime):
        raise EvaluationContextError(f"{field} must be a datetime")
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise EvaluationContextError(f"{field} must be timezone-aware UTC")
    if offset.total_seconds() != 0:
        raise EvaluationContextError(f"{field} must be UTC (offset zero)")
    return value.astimezone(UTC).isoformat()


def _normalized_payload(facts: EvaluationContextFacts) -> dict[str, str]:
    payload = {
        "job_id": _require_nonempty("job_id", facts.job_id),
        "job_revision": _canonical_timestamp(
            facts.job_revision, field="job_revision"
        ),
        "active_attachment_id": _require_nonempty(
            "active_attachment_id", facts.active_attachment_id
        ),
        "cv_source_hash": _require_nonempty(
            "cv_source_hash", facts.cv_source_hash
        ),
        "profile_revision": _canonical_timestamp(
            facts.profile_revision, field="profile_revision"
        ),
        "preferences_revision": _canonical_timestamp(
            facts.preferences_revision, field="preferences_revision"
        ),
        "matching_contract_version": _require_nonempty(
            "matching_contract_version", facts.matching_contract_version
        ),
    }
    # Guard against accidental key drift from sort_keys contract.
    if frozenset(payload) != frozenset(_CONTEXT_KEYS):
        raise EvaluationContextError("canonical context keys are incomplete")
    return payload


def canonical_evaluation_context_bytes(facts: EvaluationContextFacts) -> bytes:
    """Return stable sorted JSON bytes for the evaluation context tuple."""
    payload = _normalized_payload(facts)
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def evaluation_context_hash(facts: EvaluationContextFacts) -> str:
    """Return the SHA-256 hex digest of the canonical context bytes."""
    return hashlib.sha256(canonical_evaluation_context_bytes(facts)).hexdigest()


def derive_evaluation_currentness(
    *,
    has_any_row: bool,
    has_exact_context_hash: bool,
) -> EvaluationCurrentness:
    """Derive ``none | current | stale`` without mutating history.

    ``current`` wins when an exact hash row exists even if older rows remain.
    ``stale`` means rows exist for the Job but none match the current hash.
    ``none`` means the Job has no evaluation rows.
    """
    if has_exact_context_hash:
        return "current"
    if has_any_row:
        return "stale"
    return "none"


__all__ = [
    "MATCHING_CONTRACT_VERSION",
    "EvaluationContextError",
    "EvaluationContextFacts",
    "EvaluationCurrentness",
    "canonical_evaluation_context_bytes",
    "derive_evaluation_currentness",
    "evaluation_context_hash",
]
