"""Structured CV extraction orchestration (Plan 4 / Plan 8 / Plan 9 adapter).

Owns shared chunking, PDF→chunk preparation, and the document-first publication
artifacts used by draft proposal. Document extraction and profile projection
live in focused modules; this module reuses parser, provider-retry, and
normalizer owners without duplicating them:

* pypdf layout/normal text from :mod:`app.services.pdf_extraction`
* pure deterministic chunking (``MAX_CHUNK_CHARS=1200``, zero overlap)
* exact ``"\\n\\n"`` join of ascending chunks for model/document input
* SHA-256 ``source_hash`` over that canonical joined text
* provider-retry and one schema-repair via :mod:`app.services.provider_retry`
* skill normalization via :mod:`app.services.skill_normalization`
* document-first path delegates to
  :mod:`app.services.cv_document_extraction` and
  :mod:`app.services.cv_document_projection`

Raw extracted CV text is transient outside canonical chunk rows: never logged
or returned in tool/public contracts. Callers pass file paths or openable
sources only. Atomic DB publication of chunks + document/profile drafts is
owned by :mod:`app.services.profile_drafts`.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories.attachment_text_chunks import ChunkWrite
from app.schemas.profile import (
    CandidateProfile,
    JobPreferences,
    ProfileDraftPayload,
    parse_profile_draft_payload,
)
from app.services.cv_chunk_contracts import (
    CHUNK_JOIN,
    FAILURE_EMPTY_CHUNKS,
    CanonicalChunk,
)
from app.services.pdf_extraction import (
    NO_EXTRACTABLE_TEXT,
    PdfMalformedError,
    extract_pdf_text,
)
from app.services.provider_retry import (
    FAILURE_PROVIDER_ERROR,
    FAILURE_PROVIDER_RATE_LIMIT,
    FAILURE_PROVIDER_TIMEOUT,
    classify_provider_error,
)
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)

# Stable failure codes (attachment / tool surfaces).
# Provider codes are owned by provider_retry; re-exported for callers/tests.
FAILURE_NO_EXTRACTABLE_TEXT: Final[str] = NO_EXTRACTABLE_TEXT
FAILURE_MALFORMED_PDF: Final[str] = "MALFORMED_PDF"
FAILURE_INVALID_STRUCTURED_OUTPUT: Final[str] = "INVALID_STRUCTURED_OUTPUT"

STRUCTURED_OUTPUT_METHOD: Final[str] = "json_schema"
STRUCTURED_OUTPUT_STRICT: Final[bool] = True
EXTRACTION_SCHEMA_STRATEGY: Final[str] = "strict_json_schema"

# Deterministic chunker contract (Plan 8 Persistence And Extraction).
MAX_CHUNK_CHARS: Final[int] = 1200
CHUNK_OVERLAP: Final[int] = 0


class ProfileExtractionError(Exception):
    """Extraction failed with a stable application failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class DocumentPublicationArtifacts:
    """Complete pre-persistence artifacts for atomic draft publication.

    Built only after parse, chunk, document extraction, coverage, projection,
    profile validation, and source-hash computation succeed outside any DB
    transaction. No repository or session work lives here.
    """

    draft: ProfileDraftPayload
    document_json: dict[str, Any]
    profile_json: dict[str, Any]
    outline_json: dict[str, Any]
    extraction_version: str
    source_hash: str
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


def compute_canonical_source_hash(chunks: Sequence[CanonicalChunk]) -> str:
    """SHA-256 hex of the canonical ordered chunk text (Master §6.2)."""
    joined = join_chunks_for_model(chunks)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def is_document_structured_invoker(invoker: Any) -> bool:
    """True when *invoker* accepts the document ``schema_name`` contract."""
    if invoker is None:
        return False
    method = getattr(invoker, "invoke_structured", None)
    if method is None or not callable(method):
        return False
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False
    return "schema_name" in params


def resolve_document_invoker(invoker: Any = None) -> Any:
    """Prefer a document-capable invoker; else build the production document invoker.

    Profile-first invokers (no ``schema_name``) are ignored so the proposal path
    never re-enters the superseded raw-chunks-to-profile model contract.
    """
    if is_document_structured_invoker(invoker):
        return invoker
    from app.services.cv_document_extraction import (
        ShopAIKeyStructuredCVDocumentInvoker,
    )

    return ShopAIKeyStructuredCVDocumentInvoker()


def build_draft_from_candidate_profile(
    profile: CandidateProfile,
) -> ProfileDraftPayload:
    """Wrap a projected profile with empty job preferences for draft storage."""
    return parse_profile_draft_payload(
        {
            "candidate_profile": profile.model_dump(mode="json"),
            "job_preferences": empty_job_preferences().model_dump(mode="json"),
        }
    )


def _parse_and_chunk_pdf(
    source: Path | str | bytes | BinaryIO,
    *,
    extract_text_fn: Callable[[Any], Any] | None = None,
) -> tuple[list[CanonicalChunk], str]:
    """Parse PDF and emit canonical chunks (no provider, no persistence)."""
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

    chunks = chunk_parsed_text(extraction.preferred_text)
    model_input = join_chunks_for_model(chunks)
    logger.debug(
        "cv publication prep pages=%s strategy=%s chunks=%s",
        extraction.page_count,
        EXTRACTION_SCHEMA_STRATEGY,
        len(chunks),
    )
    return chunks, model_input


def extract_document_publication_from_pdf(
    source: Path | str | bytes | BinaryIO,
    *,
    attachment_id: str,
    invoker: Any,
    normalizer: SkillNormalizer,
    extract_text_fn: Callable[[Any], Any] | None = None,
    max_chars: int | None = None,
) -> DocumentPublicationArtifacts:
    """Document-first PDF pipeline producing complete draft publication artifacts.

    Performs provider calls, document validation, coverage, projection, and
    source-hash computation. Does **not** open a DB transaction or write rows.
    """
    from app.services.cv_document_extraction import (
        CVDocumentExtractionError,
        extract_cv_document_from_chunks,
    )
    from app.services.cv_document_projection import (
        project_candidate_profile,
        project_outline,
    )
    from app.services.cv_skill_projection import (
        CandidateSkillExtractionError,
        extract_candidate_skills_from_document,
    )

    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise ProfileExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "attachment_id is required for document-first extraction",
        )

    chunks, model_input = _parse_and_chunk_pdf(
        source, extract_text_fn=extract_text_fn
    )
    document_invoker = resolve_document_invoker(invoker)

    try:
        outcome = extract_cv_document_from_chunks(
            chunks,
            attachment_id=attachment_id,
            invoker=document_invoker,
            max_chars=max_chars,
        )
        skill_outcome = extract_candidate_skills_from_document(
            outcome.document,
            invoker=document_invoker,
            normalizer=normalizer,
            max_chars=max_chars,
        )
        profile = project_candidate_profile(
            outcome.document,
            skills=skill_outcome.skills,
        )
    except CVDocumentExtractionError as exc:
        raise ProfileExtractionError(exc.code, exc.message) from exc
    except CandidateSkillExtractionError as exc:
        raise ProfileExtractionError(exc.code, exc.message) from exc
    except (ValidationError, TypeError, ValueError) as exc:
        raise ProfileExtractionError(
            FAILURE_INVALID_STRUCTURED_OUTPUT,
            f"document projection or validation failed: {exc}",
        ) from exc

    draft = build_draft_from_candidate_profile(profile)
    outline_json: dict[str, Any] = {
        "sections": project_outline(outcome.document),
    }
    source_hash = compute_canonical_source_hash(chunks)
    return DocumentPublicationArtifacts(
        draft=draft,
        document_json=outcome.document.model_dump(mode="json"),
        profile_json=profile.model_dump(mode="json"),
        outline_json=outline_json,
        extraction_version=outcome.extraction_version,
        source_hash=source_hash,
        schema_repairs_used=(
            outcome.schema_repairs_used + skill_outcome.schema_repairs_used
        ),
        provider_retries_used=(
            outcome.provider_retries_used + skill_outcome.provider_retries_used
        ),
        chunks=tuple(chunks),
        model_input_text=model_input,
    )


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


def extract_document_and_profile_from_chunks(
    chunks: Sequence[CanonicalChunk],
    *,
    attachment_id: str,
    document_invoker: Any,
    normalizer: SkillNormalizer,
    max_chars: int | None = None,
) -> tuple[Any, CandidateProfile, int, int]:
    """Document-first pipeline: bounded CVDocument then projected profile.

    Delegates extraction and projection to their owning modules. No
    persistence or network beyond the injected document invoker.
    """
    from app.services.cv_document_extraction import (
        CVDocumentExtractionError,
        extract_cv_document_from_chunks,
    )
    from app.services.cv_document_projection import project_candidate_profile
    from app.services.cv_skill_projection import (
        CandidateSkillExtractionError,
        extract_candidate_skills_from_document,
    )

    try:
        outcome = extract_cv_document_from_chunks(
            chunks,
            attachment_id=attachment_id,
            invoker=document_invoker,
            max_chars=max_chars,
        )
        skill_outcome = extract_candidate_skills_from_document(
            outcome.document,
            invoker=document_invoker,
            normalizer=normalizer,
            max_chars=max_chars,
        )
        profile = project_candidate_profile(
            outcome.document,
            skills=skill_outcome.skills,
        )
    except CVDocumentExtractionError as exc:
        raise ProfileExtractionError(exc.code, exc.message) from exc
    except CandidateSkillExtractionError as exc:
        raise ProfileExtractionError(exc.code, exc.message) from exc
    return (
        outcome.document,
        profile,
        outcome.schema_repairs_used + skill_outcome.schema_repairs_used,
        outcome.provider_retries_used + skill_outcome.provider_retries_used,
    )


__all__ = [
    "CHUNK_JOIN",
    "CHUNK_OVERLAP",
    "CanonicalChunk",
    "DocumentPublicationArtifacts",
    "EXTRACTION_SCHEMA_STRATEGY",
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
    "build_draft_from_candidate_profile",
    "chunk_parsed_text",
    "chunks_to_writes",
    "classify_provider_error",
    "compact_draft_summary",
    "compact_profile_summary",
    "compute_canonical_source_hash",
    "empty_job_preferences",
    "extract_document_and_profile_from_chunks",
    "extract_document_publication_from_pdf",
    "is_document_structured_invoker",
    "join_chunks_for_model",
    "persist_canonical_chunks",
    "resolve_document_invoker",
]
