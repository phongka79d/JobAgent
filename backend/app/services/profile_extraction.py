"""Structured CV profile extraction via ShopAIKey (Plan 4 §7.4 / Plan 8).

Owns the LLM-backed Candidate Profile extraction path:

* pypdf layout/normal text from :mod:`app.services.pdf_extraction`
* pure deterministic chunking (``MAX_CHUNK_CHARS=1200``, zero overlap)
* exact ``"\\n\\n"`` join of ascending chunks as the sole model document input
* locked ``gpt-4o-mini`` via the ShopAIKey adapter and
  ``with_structured_output(..., method='json_schema', strict=True)``
* at most one schema-repair request when structured output is invalid
* at most one timeout/rate-limit retry
* deterministic skill normalization through the sole normalizer
* explicit canonical chunk persistence call for the successful draft-input txn

Raw extracted CV text is transient outside canonical chunk rows: never logged
or returned in tool/public contracts. Callers pass file paths or openable
sources only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final, Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.shopaikey_chat import LOCKED_CHAT_MODEL, build_shopaikey_chat
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories.attachment_text_chunks import ChunkWrite
from app.schemas.profile import (
    CandidateProfile,
    CandidateSkill,
    EducationItem,
    ExperienceItem,
    JobPreferences,
    LanguageItem,
    ProfileDraftPayload,
    parse_candidate_profile,
    parse_profile_draft_payload,
)
from app.schemas.skills import SkillRef
from app.services.pdf_extraction import (
    NO_EXTRACTABLE_TEXT,
    PdfMalformedError,
    extract_pdf_text,
)
from app.services.provider_retry import (
    FAILURE_PROVIDER_ERROR,
    FAILURE_PROVIDER_RATE_LIMIT,
    FAILURE_PROVIDER_TIMEOUT,
    ProviderRetryError,
    classify_provider_error,
    invoke_with_provider_retry,
)
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)

# Stable failure codes (attachment / tool surfaces).
# Provider codes are owned by provider_retry; re-exported for callers/tests.
FAILURE_NO_EXTRACTABLE_TEXT: Final[str] = NO_EXTRACTABLE_TEXT
FAILURE_MALFORMED_PDF: Final[str] = "MALFORMED_PDF"
FAILURE_INVALID_STRUCTURED_OUTPUT: Final[str] = "INVALID_STRUCTURED_OUTPUT"
FAILURE_EMPTY_CHUNKS: Final[str] = "EMPTY_CHUNKS"

STRUCTURED_OUTPUT_METHOD: Final[str] = "json_schema"
STRUCTURED_OUTPUT_STRICT: Final[bool] = True
EXTRACTION_SCHEMA_STRATEGY: Final[str] = "strict_json_schema"

# Deterministic chunker contract (Plan 8 Persistence And Extraction).
MAX_CHUNK_CHARS: Final[int] = 1200
CHUNK_OVERLAP: Final[int] = 0
CHUNK_JOIN: Final[str] = "\n\n"

_MAX_EVIDENCE_SNIPPET_LEN: Final[int] = 240
_MAX_REPAIR_ATTEMPTS: Final[int] = 1

_SYSTEM_PROMPT: Final[str] = (
    "You extract a Candidate Profile from CV text. Return only structured JSON "
    "matching the schema. Rules: (1) facts only — never invent job preferences; "
    "(2) evidence must be short verbatim snippets from the CV; (3) do not invent "
    "precise years or proficiency without explicit evidence — use null years and "
    "proficiency 'unknown' when unsure; (4) skill names are free-text labels only "
    "(aliases/categories are filled by a separate normalizer); (5) source is always "
    "'cv' and excluded is always false for extraction."
)


class ProfileExtractionError(Exception):
    """Extraction failed with a stable application failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- LLM-facing extraction schema (no Field min/max; strict JSON schema safe) ---


class ExtractedSkillItem(BaseModel):
    """LLM skill row before deterministic SkillRef normalization."""

    name: str
    confidence: float
    proficiency: Literal["beginner", "intermediate", "advanced", "unknown"]
    years: float | None
    evidence: list[str]


class ExtractedCandidateProfile(BaseModel):
    """LLM structured output for CV facts (validated again as CandidateProfile)."""

    summary: str
    current_title: str | None
    total_experience_years: float | None
    skills: list[ExtractedSkillItem]
    experiences: list[ExperienceItem]
    education: list[EducationItem]
    languages: list[LanguageItem]
    extraction_confidence: float


class StructuredProfileInvoker(Protocol):
    """Fake-testable structured extraction call surface.

    Production uses ShopAIKey ``with_structured_output``; tests inject fakes
    that never touch the network.
    """

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedCandidateProfile | dict[str, Any]:
        """Return structured profile payload or raise provider/validation errors."""
        ...


@dataclass(frozen=True, slots=True)
class CanonicalChunk:
    """One nonempty source-ordered text segment for model input + persistence."""

    ordinal: int
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def token_estimate(self) -> int:
        return chunk_repo.token_estimate_for_chars(self.char_count)

    @property
    def preview(self) -> str:
        return chunk_repo.preview_for_text(self.text)


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    """Validated draft payload after extraction + normalization (no DB work).

    ``chunks`` is the exact ascending sequence joined with :data:`CHUNK_JOIN`
    for the model input. Persistence is a separate explicit call.
    """

    draft: ProfileDraftPayload
    schema_repairs_used: int
    provider_retries_used: int
    chunks: tuple[CanonicalChunk, ...]
    model_input_text: str


def empty_job_preferences() -> JobPreferences:
    """CV extraction never invents preferences (facts/preferences separation)."""
    return JobPreferences(
        target_roles=[],
        preferred_locations=[],
        acceptable_work_modes=[],
        target_seniority=[],
    )


def _clip_evidence(snippets: list[str]) -> list[str]:
    clipped: list[str] = []
    for item in snippets:
        text = " ".join(str(item).split())
        if not text:
            continue
        if len(text) > _MAX_EVIDENCE_SNIPPET_LEN:
            text = text[:_MAX_EVIDENCE_SNIPPET_LEN]
        clipped.append(text)
    return clipped


def extracted_to_candidate_profile(
    extracted: ExtractedCandidateProfile,
    normalizer: SkillNormalizer,
) -> CandidateProfile:
    """Map LLM extraction to validated CandidateProfile with normalized skills."""
    skills: list[CandidateSkill] = []
    for row in extracted.skills:
        name = " ".join(row.name.split())
        if not name:
            continue
        ref: SkillRef = normalizer.normalize_name(name)
        # Clamp confidence defensively before full model validation.
        conf = float(row.confidence)
        if conf < 0.0:
            conf = 0.0
        elif conf > 1.0:
            conf = 1.0
        skills.append(
            CandidateSkill(
                skill=ref,
                confidence=conf,
                proficiency=row.proficiency,
                years=row.years,
                source="cv",
                excluded=False,
                evidence=_clip_evidence(list(row.evidence)),
            )
        )

    ext_conf = float(extracted.extraction_confidence)
    if ext_conf < 0.0:
        ext_conf = 0.0
    elif ext_conf > 1.0:
        ext_conf = 1.0

    raw_profile = {
        "summary": extracted.summary,
        "current_title": extracted.current_title,
        "total_experience_years": extracted.total_experience_years,
        "skills": [s.model_dump(mode="json") for s in skills],
        "experiences": [e.model_dump(mode="json") for e in extracted.experiences],
        "education": [e.model_dump(mode="json") for e in extracted.education],
        "languages": [lang.model_dump(mode="json") for lang in extracted.languages],
        "extraction_confidence": ext_conf,
    }
    return parse_candidate_profile(raw_profile)


def build_draft_from_extracted(
    extracted: ExtractedCandidateProfile,
    normalizer: SkillNormalizer,
) -> ProfileDraftPayload:
    """Build a fully validated ProfileDraftPayload (empty preferences)."""
    profile = extracted_to_candidate_profile(extracted, normalizer)
    return parse_profile_draft_payload(
        {
            "candidate_profile": profile.model_dump(mode="json"),
            "job_preferences": empty_job_preferences().model_dump(mode="json"),
        }
    )


def _coerce_extracted(raw: Any) -> ExtractedCandidateProfile:
    if isinstance(raw, ExtractedCandidateProfile):
        return raw
    if isinstance(raw, BaseModel):
        return ExtractedCandidateProfile.model_validate(raw.model_dump())
    if isinstance(raw, str):
        return ExtractedCandidateProfile.model_validate(json.loads(raw))
    return ExtractedCandidateProfile.model_validate(raw)


class ShopAIKeyStructuredProfileInvoker:
    """Production invoker: ShopAIKey + strict JSON schema structured output."""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model if model is not None else build_shopaikey_chat()
        # Verified Phase 0 strategy: response_format json_schema with strict=true.
        self._structured = self._model.with_structured_output(
            ExtractedCandidateProfile,
            method=STRUCTURED_OUTPUT_METHOD,
            strict=STRUCTURED_OUTPUT_STRICT,
        )

    @property
    def model_name(self) -> str:
        name = getattr(self._model, "model_name", None)
        if isinstance(name, str) and name:
            return name
        return LOCKED_CHAT_MODEL

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedCandidateProfile:
        del is_repair  # repair is encoded in the message list by the caller
        result = self._structured.invoke(list(messages))
        return _coerce_extracted(result)


def _build_messages(cv_text: str, *, repair_error: str | None) -> list[Any]:
    # Canonical joined chunk text appears only in this transient prompt.
    messages: list[Any] = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Extract the Candidate Profile from the following CV text.\n\n"
                f"--- CV TEXT START ---\n{cv_text}\n--- CV TEXT END ---"
            )
        ),
    ]
    if repair_error is not None:
        messages.append(
            HumanMessage(
                content=(
                    "Your previous structured output failed validation with this "
                    f"error:\n{repair_error}\n"
                    "Repair: return one valid ExtractedCandidateProfile JSON object "
                    "only. Keep evidence short and do not invent preferences."
                )
            )
        )
    return messages


def _split_oversized_segment(segment: str, max_chars: int) -> list[str]:
    """Split one oversized segment on whitespace into <= max_chars pieces."""
    if len(segment) <= max_chars:
        return [segment] if segment else []
    parts: list[str] = []
    remaining = segment
    while remaining:
        if len(remaining) <= max_chars:
            parts.append(remaining)
            break
        window = remaining[:max_chars]
        # Prefer last whitespace in the window; else hard-cut at max_chars.
        split_at = max(window.rfind(" "), window.rfind("\t"), window.rfind("\n"))
        if split_at <= 0:
            split_at = max_chars
        piece = remaining[:split_at].rstrip()
        if not piece:
            # No progress with whitespace trim — hard cut.
            piece = remaining[:max_chars]
            remaining = remaining[max_chars:]
        else:
            remaining = remaining[split_at:].lstrip()
        if piece:
            parts.append(piece)
    return parts


def chunk_parsed_text(
    text: str,
    *,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[CanonicalChunk]:
    """Pure deterministic paragraph-then-whitespace chunker.

    Emits nonempty ascending ordinals, max *max_chars* each, zero *overlap*.
    Never calls a provider. Raises :class:`ProfileExtractionError` when no
    nonempty chunks can be produced.
    """
    if overlap != 0:
        raise ProfileExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "CHUNK_OVERLAP must be 0 for canonical extraction chunks",
        )
    if max_chars <= 0:
        raise ProfileExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "MAX_CHUNK_CHARS must be > 0",
        )
    if not isinstance(text, str) or text.strip() == "":
        raise ProfileExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "parsed text produced no nonempty chunks",
        )

    # Paragraph split first (source order); empty paragraphs dropped.
    paragraphs = [p.strip() for p in text.split("\n\n")]
    paragraphs = [p for p in paragraphs if p]

    packed: list[str] = []
    current = ""
    for para in paragraphs:
        pieces = _split_oversized_segment(para, max_chars)
        for piece in pieces:
            if not piece:
                continue
            if not current:
                current = piece
                continue
            candidate = f"{current}\n\n{piece}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                packed.append(current)
                current = piece
    if current:
        packed.append(current)

    chunks = [
        CanonicalChunk(ordinal=i, text=body)
        for i, body in enumerate(packed)
        if body
    ]
    if not chunks:
        raise ProfileExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "parsed text produced no nonempty chunks",
        )
    for chunk in chunks:
        if len(chunk.text) > max_chars:
            raise ProfileExtractionError(
                FAILURE_EMPTY_CHUNKS,
                f"chunk ordinal {chunk.ordinal} exceeds MAX_CHUNK_CHARS",
            )
        if chunk.text == "":
            raise ProfileExtractionError(
                FAILURE_EMPTY_CHUNKS,
                "empty chunk rejected",
            )
    return chunks


def join_chunks_for_model(chunks: Sequence[CanonicalChunk]) -> str:
    """Join ascending chunk texts with exactly :data:`CHUNK_JOIN`."""
    if not chunks:
        raise ProfileExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "cannot join empty chunk sequence for model input",
        )
    ordered = sorted(chunks, key=lambda c: c.ordinal)
    for i, chunk in enumerate(ordered):
        if chunk.ordinal != i:
            raise ProfileExtractionError(
                FAILURE_EMPTY_CHUNKS,
                "chunk ordinals must be contiguous ascending from 0",
            )
        if chunk.text == "":
            raise ProfileExtractionError(
                FAILURE_EMPTY_CHUNKS,
                "empty chunk rejected in model join",
            )
    return CHUNK_JOIN.join(c.text for c in ordered)


def chunks_to_writes(chunks: Sequence[CanonicalChunk]) -> list[ChunkWrite]:
    """Map canonical chunks to repository write rows."""
    return [chunk_repo.build_chunk_write(c.ordinal, c.text) for c in chunks]


async def persist_canonical_chunks(
    session: AsyncSession,
    *,
    attachment_id: str,
    chunks: Sequence[CanonicalChunk],
) -> list[Any]:
    """Persist the exact canonical chunk sequence for *attachment_id*.

    Call only inside the successful extraction/draft-input transaction after
    draft validation succeeds. Replaces any prior rows for the attachment.
    Does not finalize the caller's unit of work.
    """
    if not chunks:
        raise ProfileExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "refuse to persist empty chunk sequence",
        )
    writes = chunks_to_writes(chunks)
    return await chunk_repo.replace_for_attachment(
        session, attachment_id, writes
    )


def _invoke_with_provider_retry(
    invoker: StructuredProfileInvoker,
    messages: Sequence[Any],
    *,
    is_repair: bool,
) -> tuple[ExtractedCandidateProfile, int]:
    """Call structured invoker via shared provider retry; map domain errors."""

    def _call() -> ExtractedCandidateProfile:
        raw = invoker.invoke_structured(messages, is_repair=is_repair)
        return _coerce_extracted(raw)

    try:
        return invoke_with_provider_retry(_call)
    except ProviderRetryError as exc:
        raise ProfileExtractionError(exc.code, exc.message) from exc


def extract_profile_from_pdf(
    source: Path | str | bytes | BinaryIO,
    *,
    invoker: StructuredProfileInvoker,
    normalizer: SkillNormalizer,
    extract_text_fn: Callable[[Any], Any] | None = None,
) -> ExtractionOutcome:
    """Extract + validate a ProfileDraftPayload from a PDF source.

    Deterministically chunks preferred PDF text, joins with :data:`CHUNK_JOIN`,
    and sends only that joined string to the structured model. Does **not**
    write chunk rows; callers must invoke :func:`persist_canonical_chunks`
    inside the successful draft-input transaction.

    Parameters
    ----------
    source:
        PDF path, bytes, or binary stream (same as pdf_extraction).
    invoker:
        Structured LLM invoker (production ShopAIKey or test fake).
    normalizer:
        Sole skill normalizer instance.
    extract_text_fn:
        Optional override for unit tests (defaults to extract_pdf_text).
    """
    extract = extract_text_fn if extract_text_fn is not None else extract_pdf_text
    try:
        extraction = extract(source)
    except PdfMalformedError as exc:
        raise ProfileExtractionError(
            FAILURE_MALFORMED_PDF,
            str(exc) or "PDF is malformed or unreadable",
        ) from exc

    if not extraction.has_meaningful_text or extraction.preferred_text is None:
        raise ProfileExtractionError(
            FAILURE_NO_EXTRACTABLE_TEXT,
            "PDF has no meaningful extractable digital text",
        )

    preferred = extraction.preferred_text
    chunks = chunk_parsed_text(preferred)
    cv_text = join_chunks_for_model(chunks)
    # Do not log cv_text or full extraction payloads.
    logger.debug(
        "profile extraction starting pages=%s strategy=%s chunks=%s",
        extraction.page_count,
        EXTRACTION_SCHEMA_STRATEGY,
        len(chunks),
    )

    repairs_used = 0
    provider_retries_total = 0
    repair_error: str | None = None

    while True:
        messages = _build_messages(cv_text, repair_error=repair_error)
        is_repair = repair_error is not None
        try:
            extracted, retries = _invoke_with_provider_retry(
                invoker, messages, is_repair=is_repair
            )
            provider_retries_total += retries
            draft = build_draft_from_extracted(extracted, normalizer)
            return ExtractionOutcome(
                draft=draft,
                schema_repairs_used=repairs_used,
                provider_retries_used=provider_retries_total,
                chunks=tuple(chunks),
                model_input_text=cv_text,
            )
        except ProfileExtractionError:
            raise
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if repairs_used >= _MAX_REPAIR_ATTEMPTS:
                raise ProfileExtractionError(
                    FAILURE_INVALID_STRUCTURED_OUTPUT,
                    "structured output invalid after one repair attempt",
                ) from exc
            repairs_used += 1
            repair_error = str(exc)[:500]
            continue


def compact_profile_summary(profile: CandidateProfile) -> dict[str, Any]:
    """IDs-and-counts summary only — no evidence bodies or raw CV text."""
    return {
        "current_title": profile.current_title,
        "skill_count": len(profile.skills),
        "experience_count": len(profile.experiences),
        "education_count": len(profile.education),
        "language_count": len(profile.languages),
        "extraction_confidence": profile.extraction_confidence,
        "summary_excerpt": (profile.summary or "")[:160],
    }


def compact_draft_summary(draft: ProfileDraftPayload) -> dict[str, Any]:
    """Compact draft summary for ToolResult.data / arguments_summary_json."""
    base = compact_profile_summary(draft.candidate_profile)
    base["draft_id"] = "current"
    base["preference_role_count"] = len(draft.job_preferences.target_roles)
    return base


__all__ = [
    "CHUNK_JOIN",
    "CHUNK_OVERLAP",
    "CanonicalChunk",
    "EXTRACTION_SCHEMA_STRATEGY",
    "ExtractedCandidateProfile",
    "ExtractedSkillItem",
    "ExtractionOutcome",
    "FAILURE_EMPTY_CHUNKS",
    "FAILURE_INVALID_STRUCTURED_OUTPUT",
    "FAILURE_MALFORMED_PDF",
    "FAILURE_NO_EXTRACTABLE_TEXT",
    "FAILURE_PROVIDER_ERROR",
    "FAILURE_PROVIDER_RATE_LIMIT",
    "FAILURE_PROVIDER_TIMEOUT",
    "MAX_CHUNK_CHARS",
    "ProfileExtractionError",
    "STRUCTURED_OUTPUT_METHOD",
    "STRUCTURED_OUTPUT_STRICT",
    "ShopAIKeyStructuredProfileInvoker",
    "StructuredProfileInvoker",
    "build_draft_from_extracted",
    "chunk_parsed_text",
    "chunks_to_writes",
    "classify_provider_error",
    "compact_draft_summary",
    "compact_profile_summary",
    "empty_job_preferences",
    "extract_profile_from_pdf",
    "extracted_to_candidate_profile",
    "join_chunks_for_model",
    "persist_canonical_chunks",
]
