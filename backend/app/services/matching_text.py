"""Versioned Candidate embedding text builder and redacted embed path.

Owns deterministic Candidate representation assembly
(``candidate_embedding_text_v1``): target roles, profile summary, verified
non-excluded skills, experience titles, and preferences. Redacts through the
shared ``redact_pii`` boundary before any call into ``JobEmbeddingService``.
Does not construct a second provider/model/dimension stack.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from app.schemas.candidate import CandidateProfile, CandidateSkill, SkillStatus
from app.schemas.matching import (
    CANDIDATE_TEXT_REPRESENTATION_VERSION,
    CandidateEmbeddingError,
    CandidateEmbeddingErrorCode,
    CandidateEmbeddingFields,
    CandidateEmbeddingResult,
)
from app.schemas.preferences import JobPreferences
from app.services.embeddings import (
    EmbeddingsClientLike,
    JobEmbeddingError,
    JobEmbeddingErrorCode,
    JobEmbeddingService,
    normalize_embedding_text,
)
from app.services.pii_redaction import PiiRedactionError, redact_pii

# Soft ceiling after normalization; profile/preference contracts already bound
# each source field. This rejects pathological assemblies without truncating
# silently (fail closed).
MAX_CANDIDATE_EMBEDDING_TEXT_LEN: Final[int] = 16_384

_JOB_CODE_TO_CANDIDATE: Final[
    dict[JobEmbeddingErrorCode, CandidateEmbeddingErrorCode]
] = {
    JobEmbeddingErrorCode.TIMEOUT: CandidateEmbeddingErrorCode.TIMEOUT,
    JobEmbeddingErrorCode.RATE_LIMIT: CandidateEmbeddingErrorCode.RATE_LIMIT,
    JobEmbeddingErrorCode.CANCELLED: CandidateEmbeddingErrorCode.CANCELLED,
    JobEmbeddingErrorCode.PROVIDER_ERROR: CandidateEmbeddingErrorCode.PROVIDER_ERROR,
    JobEmbeddingErrorCode.CONFIG: CandidateEmbeddingErrorCode.CONFIG,
    JobEmbeddingErrorCode.MODEL_MISMATCH: CandidateEmbeddingErrorCode.MODEL_MISMATCH,
    JobEmbeddingErrorCode.VECTOR_COUNT_MISMATCH: (
        CandidateEmbeddingErrorCode.VECTOR_COUNT_MISMATCH
    ),
    JobEmbeddingErrorCode.ORDERING_VIOLATION: (
        CandidateEmbeddingErrorCode.ORDERING_VIOLATION
    ),
    JobEmbeddingErrorCode.DIMENSION_MISMATCH: (
        CandidateEmbeddingErrorCode.DIMENSION_MISMATCH
    ),
    JobEmbeddingErrorCode.NON_FINITE_VALUE: CandidateEmbeddingErrorCode.NON_FINITE_VALUE,
    JobEmbeddingErrorCode.EMPTY_BATCH: CandidateEmbeddingErrorCode.EMPTY_BATCH,
    JobEmbeddingErrorCode.BATCH_SIZE_EXCEEDED: (
        CandidateEmbeddingErrorCode.BATCH_SIZE_EXCEEDED
    ),
    JobEmbeddingErrorCode.DUPLICATE_VECTOR_INDEX: (
        CandidateEmbeddingErrorCode.DUPLICATE_VECTOR_INDEX
    ),
}


def _field_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def _join_list(items: Sequence[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return ", ".join(cleaned)


def _verified_non_excluded_skill_names(
    skills: Sequence[CandidateSkill],
) -> tuple[str, ...]:
    """Stable profile order; verified + not excluded; first display_name wins."""
    names: list[str] = []
    seen_keys: set[str] = set()
    for item in skills:
        if item.excluded:
            continue
        if item.skill.status is not SkillStatus.VERIFIED:
            continue
        key = item.skill.canonical_key
        if key in seen_keys:
            continue
        seen_keys.add(key)
        name = item.skill.display_name.strip()
        if name:
            names.append(name)
    return tuple(names)


def _experience_titles(profile: CandidateProfile) -> tuple[str, ...]:
    titles: list[str] = []
    for item in profile.experiences:
        title = _field_text(item.title)
        if title:
            titles.append(title)
    return tuple(titles)


def candidate_fields_from_profile(
    profile: CandidateProfile,
    preferences: JobPreferences | None = None,
) -> CandidateEmbeddingFields:
    """Project approved profile + preferences into embedding-only fields.

    Contact PII, storage paths, education, languages, evidence, raw CV, and
    attachment metadata are never included.
    """
    prefs = preferences if preferences is not None else JobPreferences()
    return CandidateEmbeddingFields(
        target_roles=tuple(role.strip() for role in prefs.target_roles if role.strip()),
        summary=_field_text(profile.summary),
        verified_skills=_verified_non_excluded_skill_names(profile.skills),
        experience_titles=_experience_titles(profile),
        preferred_locations=tuple(
            loc.strip() for loc in prefs.preferred_locations if loc.strip()
        ),
        acceptable_work_modes=tuple(mode.value for mode in prefs.acceptable_work_modes),
        target_seniority=tuple(level.value for level in prefs.target_seniority),
    )


def build_candidate_embedding_text(
    source: CandidateProfile | CandidateEmbeddingFields,
    preferences: JobPreferences | None = None,
) -> str:
    """Build versioned deterministic Candidate embedding text (pre-redaction).

    Source order is fixed as: target roles, profile summary, verified
    non-excluded skills, experience titles, preferences (locations, work modes,
    seniority). No E5 prefixes are added. Contact/storage/raw-CV fields never
    enter the assembly.
    """
    if isinstance(source, CandidateEmbeddingFields):
        if preferences is not None:
            raise CandidateEmbeddingError(CandidateEmbeddingErrorCode.INVALID_INPUT)
        fields = source
    else:
        fields = candidate_fields_from_profile(source, preferences)

    preference_tokens = (
        *fields.preferred_locations,
        *fields.acceptable_work_modes,
        *fields.target_seniority,
    )
    parts = [
        _join_list(fields.target_roles),
        _field_text(fields.summary),
        _join_list(fields.verified_skills),
        _join_list(fields.experience_titles),
        _join_list(preference_tokens),
    ]
    assembled = "\n".join(parts)
    text = normalize_embedding_text(assembled)
    if len(text) > MAX_CANDIDATE_EMBEDDING_TEXT_LEN:
        raise CandidateEmbeddingError(CandidateEmbeddingErrorCode.INVALID_INPUT)
    return text


def redact_candidate_embedding_text(text: str) -> str:
    """Apply deterministic PII redaction; fail closed with a code-only error.

    Never embeds source text into the exception. Callers must not invoke the
    embedding provider when this raises.
    """
    if not isinstance(text, str):
        raise CandidateEmbeddingError(CandidateEmbeddingErrorCode.INVALID_INPUT)
    try:
        redacted = redact_pii(text).text
    except PiiRedactionError:
        raise CandidateEmbeddingError(
            CandidateEmbeddingErrorCode.REDACTION_FAILED
        ) from None
    except Exception:
        raise CandidateEmbeddingError(
            CandidateEmbeddingErrorCode.REDACTION_FAILED
        ) from None
    return normalize_embedding_text(redacted)


def _map_job_embedding_error(exc: JobEmbeddingError) -> CandidateEmbeddingError:
    mapped = _JOB_CODE_TO_CANDIDATE.get(
        exc.code, CandidateEmbeddingErrorCode.PROVIDER_ERROR
    )
    return CandidateEmbeddingError(mapped)


def embed_candidate(
    source: CandidateProfile | CandidateEmbeddingFields,
    *,
    embedding_service: JobEmbeddingService,
    preferences: JobPreferences | None = None,
    client: EmbeddingsClientLike | None = None,
) -> CandidateEmbeddingResult:
    """Redact Candidate text then embed through the existing locked adapter.

    Redaction runs before client construction / provider request. Provider and
    validation failures surface as sanitized ``CandidateEmbeddingError`` codes
    only (no source text, secrets, or raw payloads).
    """
    plain = build_candidate_embedding_text(source, preferences)
    redacted = redact_candidate_embedding_text(plain)
    try:
        batch = embedding_service.embed_texts(
            [redacted],
            client=client,
            representation_version=CANDIDATE_TEXT_REPRESENTATION_VERSION,
        )
    except JobEmbeddingError as exc:
        raise _map_job_embedding_error(exc) from None

    if len(batch.vectors) != 1:
        raise CandidateEmbeddingError(
            CandidateEmbeddingErrorCode.VECTOR_COUNT_MISMATCH
        )
    vector = batch.vectors[0]
    return CandidateEmbeddingResult(
        index=vector.index,
        values=vector.values,
        model=batch.model,
        dimensions=batch.dimensions,
        representation_version=CANDIDATE_TEXT_REPRESENTATION_VERSION,
        encoding=batch.encoding,
    )


__all__ = [
    "CANDIDATE_TEXT_REPRESENTATION_VERSION",
    "MAX_CANDIDATE_EMBEDDING_TEXT_LEN",
    "build_candidate_embedding_text",
    "candidate_fields_from_profile",
    "embed_candidate",
    "redact_candidate_embedding_text",
]
