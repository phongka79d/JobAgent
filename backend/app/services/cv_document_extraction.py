"""Bounded document-first CV extraction (Plan 9 / Master §10.2).

Owns batching, structured section/entry extraction, hierarchical consolidation,
deterministic IDs, coverage recovery, and CVDocument validation. Reuses the
parser/chunker owners, provider-retry loop, and structured-output adapter.

Does not persist drafts, open DB sessions, or project CandidateProfile.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, ValidationError

from app.adapters.shopaikey_chat import LOCKED_CHAT_MODEL, build_shopaikey_chat
from app.core.settings import get_settings
from app.schemas.cv_document import (
    CV_SECTION_KINDS,
    CVDocument,
    CVEntry,
    CVSection,
    CVSectionKind,
    parse_cv_document,
)
from app.services.profile_extraction import (
    CHUNK_JOIN,
    FAILURE_EMPTY_CHUNKS,
    CanonicalChunk,
)
from app.services.provider_retry import (
    FAILURE_PROVIDER_ERROR,
    FAILURE_PROVIDER_RATE_LIMIT,
    FAILURE_PROVIDER_TIMEOUT,
    ProviderRetryError,
    invoke_with_provider_retry,
)

logger = logging.getLogger(__name__)

EXTRACTION_VERSION: Final[str] = "cv-document-v1"
DEFAULT_BATCH_MAX_CHARS: Final[int] = 6000
STRUCTURED_OUTPUT_METHOD: Final[str] = "json_schema"
STRUCTURED_OUTPUT_STRICT: Final[bool] = True
_MAX_REPAIR_ATTEMPTS: Final[int] = 1
_HEADING_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")

FAILURE_INVALID_STRUCTURED_OUTPUT: Final[str] = "INVALID_STRUCTURED_OUTPUT"
FAILURE_COVERAGE: Final[str] = "COVERAGE_AUDIT_FAILED"

_BATCH_SYSTEM: Final[str] = (
    "You extract ordered CV section/entry fragments from a bounded chunk batch. "
    "Return only structured JSON. Rules: (1) preserve original headings exactly; "
    "(2) use kind from the allowed enum — unknown meaningful headings use kind "
    "'other' (never coerce certifications, GPA, awards, or projects into skills); "
    "(3) every entry/section must list source_chunk_ordinals from the provided "
    "batch only; (4) keep source order; (5) facts only — do not invent content."
)

_CONSOLIDATE_SYSTEM: Final[str] = (
    "You consolidate CV section fragments into one ordered document outline. "
    "Merge adjacent fragments that share the same original heading/kind, preserve "
    "entry content and source_chunk_ordinals, keep source order, and never coerce "
    "certifications or unknown sections into skills. Return only structured JSON."
)

SectionKindLiteral = Literal[
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


class CVDocumentExtractionError(Exception):
    """Document extraction failed with a stable application failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- LLM-facing schemas (strict JSON schema safe; no Field ge/le) ---


class ExtractedEntryFragment(BaseModel):
    """LLM entry fragment before deterministic ID assignment."""

    model_config = ConfigDict(extra="forbid")

    title: str | None
    subtitle: str | None
    date_text: str | None
    location: str | None
    body: str
    bullets: list[str]
    attributes: dict[str, str]
    source_chunk_ordinals: list[int]


class ExtractedSectionFragment(BaseModel):
    """LLM section fragment from one batch or consolidation step."""

    model_config = ConfigDict(extra="forbid")

    heading: str
    kind: SectionKindLiteral
    entries: list[ExtractedEntryFragment]
    source_chunk_ordinals: list[int]


class ExtractedBatchDocument(BaseModel):
    """Structured batch extraction payload."""

    model_config = ConfigDict(extra="forbid")

    detected_languages: list[str]
    sections: list[ExtractedSectionFragment]
    extraction_warnings: list[str]
    extraction_confidence: float


class ExtractedConsolidation(BaseModel):
    """Structured consolidation payload over section fragments."""

    model_config = ConfigDict(extra="forbid")

    detected_languages: list[str]
    sections: list[ExtractedSectionFragment]
    extraction_warnings: list[str]
    extraction_confidence: float


class StructuredCVDocumentInvoker(Protocol):
    """Fake-testable structured CV document extraction call surface."""

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        schema_name: str,
        is_repair: bool = False,
    ) -> Any:
        """Return structured payload for the named schema or raise."""
        ...


@dataclass(frozen=True, slots=True)
class ChunkBatch:
    """One bounded ordinal range of ascending chunks for a single model call."""

    attachment_id: str
    start_ordinal: int
    end_ordinal: int
    chunks: tuple[CanonicalChunk, ...]

    @property
    def char_count(self) -> int:
        if not self.chunks:
            return 0
        return len(CHUNK_JOIN.join(c.text for c in self.chunks))

    @property
    def ordinals(self) -> list[int]:
        return [c.ordinal for c in self.chunks]


@dataclass(frozen=True, slots=True)
class CVDocumentExtractionOutcome:
    """Validated CVDocument plus extraction diagnostics (no DB / profile)."""

    document: CVDocument
    schema_repairs_used: int
    provider_retries_used: int
    batches: tuple[ChunkBatch, ...]
    extraction_version: str


def batch_max_chars_from_settings() -> int:
    """Return the configured batch character ceiling."""
    try:
        value = int(get_settings().CV_DOCUMENT_BATCH_MAX_CHARS)
    except Exception:
        return DEFAULT_BATCH_MAX_CHARS
    return value if value > 0 else DEFAULT_BATCH_MAX_CHARS


def normalize_heading_key(heading: str) -> str:
    """Normalize a heading for deterministic ID material (not display)."""
    collapsed = " ".join(heading.split()).strip().lower()
    slug = _HEADING_SLUG_RE.sub("-", collapsed).strip("-")
    return slug or "section"


def deterministic_section_id(
    *,
    extraction_version: str,
    ordinal: int,
    heading: str,
) -> str:
    """Stable section id from version, ordinal, and normalized heading."""
    return f"{extraction_version}:s{ordinal}:{normalize_heading_key(heading)}"


def deterministic_entry_id(
    *,
    extraction_version: str,
    section_ordinal: int,
    entry_ordinal: int,
    heading: str,
    title: str | None,
) -> str:
    """Stable entry id from version, ordinals, and normalized heading/title."""
    material = title if title and title.strip() else heading
    return (
        f"{extraction_version}:s{section_ordinal}:e{entry_ordinal}:"
        f"{normalize_heading_key(material)}"
    )


def partition_chunks_by_char_ceiling(
    chunks: Sequence[CanonicalChunk],
    *,
    attachment_id: str,
    max_chars: int | None = None,
) -> list[ChunkBatch]:
    """Partition ascending chunks into bounded batches by character ceiling.

    Every batch carries attachment ID and exact inclusive ordinal range.
    Never joins the full sequence when it would exceed *max_chars*.
    A single chunk larger than the ceiling forms its own batch (still not a
    raw PDF body).
    """
    if max_chars is None:
        max_chars = batch_max_chars_from_settings()
    if max_chars <= 0:
        raise CVDocumentExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "CV_DOCUMENT_BATCH_MAX_CHARS must be > 0",
        )
    if not chunks:
        raise CVDocumentExtractionError(
            FAILURE_EMPTY_CHUNKS,
            "cannot partition empty chunk sequence",
        )
    ordered = sorted(chunks, key=lambda c: c.ordinal)
    for i, chunk in enumerate(ordered):
        if chunk.ordinal != i:
            raise CVDocumentExtractionError(
                FAILURE_EMPTY_CHUNKS,
                "chunk ordinals must be contiguous ascending from 0",
            )
        if chunk.text == "":
            raise CVDocumentExtractionError(
                FAILURE_EMPTY_CHUNKS,
                "empty chunk rejected",
            )

    batches: list[ChunkBatch] = []
    current: list[CanonicalChunk] = []
    current_chars = 0
    for chunk in ordered:
        piece_len = len(chunk.text)
        if not current:
            current = [chunk]
            current_chars = piece_len
            continue
        joined_extra = len(CHUNK_JOIN) + piece_len
        if current_chars + joined_extra <= max_chars:
            current.append(chunk)
            current_chars += joined_extra
            continue
        batches.append(
            ChunkBatch(
                attachment_id=attachment_id,
                start_ordinal=current[0].ordinal,
                end_ordinal=current[-1].ordinal,
                chunks=tuple(current),
            )
        )
        current = [chunk]
        current_chars = piece_len
    if current:
        batches.append(
            ChunkBatch(
                attachment_id=attachment_id,
                start_ordinal=current[0].ordinal,
                end_ordinal=current[-1].ordinal,
                chunks=tuple(current),
            )
        )
    return batches


def _coerce_batch(raw: Any) -> ExtractedBatchDocument:
    if isinstance(raw, ExtractedBatchDocument):
        return raw
    if isinstance(raw, BaseModel):
        return ExtractedBatchDocument.model_validate(raw.model_dump())
    if isinstance(raw, str):
        return ExtractedBatchDocument.model_validate(json.loads(raw))
    return ExtractedBatchDocument.model_validate(raw)


def _coerce_consolidation(raw: Any) -> ExtractedConsolidation:
    if isinstance(raw, ExtractedConsolidation):
        return raw
    if isinstance(raw, BaseModel):
        return ExtractedConsolidation.model_validate(raw.model_dump())
    if isinstance(raw, str):
        return ExtractedConsolidation.model_validate(json.loads(raw))
    return ExtractedConsolidation.model_validate(raw)


def _filter_ordinals(
    ordinals: Sequence[int], allowed: set[int]
) -> list[int]:
    cleaned = sorted({int(o) for o in ordinals if int(o) in allowed})
    return cleaned


def _normalize_section_kind(kind: str) -> CVSectionKind:
    key = kind.strip().lower()
    if key in CV_SECTION_KINDS:
        return key  # type: ignore[return-value]
    return "other"


def _entry_from_fragment(
    frag: ExtractedEntryFragment,
    *,
    extraction_version: str,
    section_ordinal: int,
    entry_ordinal: int,
    heading: str,
    allowed_ordinals: set[int],
) -> CVEntry | None:
    sources = _filter_ordinals(frag.source_chunk_ordinals, allowed_ordinals)
    body = frag.body if isinstance(frag.body, str) else ""
    bullets = [b for b in frag.bullets if isinstance(b, str)]
    attrs: dict[str, str | list[str]] = {
        k: v for k, v in frag.attributes.items() if isinstance(k, str) and k
    }
    # Drop empty decorative entries with no content.
    if (
        not body.strip()
        and not bullets
        and not (frag.title or "").strip()
        and not attrs
    ):
        return None
    if not sources:
        # Retain content under nearest allowed ordinal when model omitted sources.
        if allowed_ordinals:
            sources = [min(allowed_ordinals)]
        else:
            return None
    return CVEntry(
        id=deterministic_entry_id(
            extraction_version=extraction_version,
            section_ordinal=section_ordinal,
            entry_ordinal=entry_ordinal,
            heading=heading,
            title=frag.title,
        ),
        ordinal=entry_ordinal,
        title=frag.title,
        subtitle=frag.subtitle,
        date_text=frag.date_text,
        location=frag.location,
        body=body,
        bullets=bullets,
        attributes=attrs,
        source_chunk_ordinals=sources,
    )


def sections_from_fragments(
    fragments: Sequence[ExtractedSectionFragment],
    *,
    extraction_version: str = EXTRACTION_VERSION,
    allowed_ordinals: set[int] | None = None,
) -> list[CVSection]:
    """Map LLM fragments to ordered CVSection values with deterministic IDs."""
    sections: list[CVSection] = []
    for frag in fragments:
        heading = " ".join(frag.heading.split()).strip()
        if not heading:
            continue
        kind = _normalize_section_kind(frag.kind)
        allowed = allowed_ordinals
        if allowed is None:
            allowed = set(frag.source_chunk_ordinals)
        section_sources = _filter_ordinals(frag.source_chunk_ordinals, allowed)
        entries: list[CVEntry] = []
        for raw_entry in frag.entries:
            entry = _entry_from_fragment(
                raw_entry,
                extraction_version=extraction_version,
                section_ordinal=len(sections),
                entry_ordinal=len(entries),
                heading=heading,
                allowed_ordinals=allowed if allowed else set(section_sources),
            )
            if entry is not None:
                entries.append(entry)
        if not entries and not section_sources:
            # Empty decorative heading — omit.
            continue
        if entries:
            section_sources = sorted(
                {o for e in entries for o in e.source_chunk_ordinals}
            )
        # Re-number entry ordinals and re-derive IDs after drops.
        renumbered: list[CVEntry] = []
        for i, entry in enumerate(entries):
            renumbered.append(
                entry.model_copy(
                    update={
                        "ordinal": i,
                        "id": deterministic_entry_id(
                            extraction_version=extraction_version,
                            section_ordinal=len(sections),
                            entry_ordinal=i,
                            heading=heading,
                            title=entry.title,
                        ),
                    }
                )
            )
        sections.append(
            CVSection(
                id=deterministic_section_id(
                    extraction_version=extraction_version,
                    ordinal=len(sections),
                    heading=heading,
                ),
                ordinal=len(sections),
                heading=heading,
                kind=kind,
                entries=renumbered,
                source_chunk_ordinals=section_sources,
            )
        )
    return sections


def merge_adjacent_sections(sections: Sequence[CVSection]) -> list[CVSection]:
    """Deterministically merge adjacent sections with same kind + heading key."""
    if not sections:
        return []
    merged: list[CVSection] = []
    for section in sections:
        if not merged:
            merged.append(section)
            continue
        prev = merged[-1]
        same = (
            prev.kind == section.kind
            and normalize_heading_key(prev.heading)
            == normalize_heading_key(section.heading)
        )
        if not same:
            merged.append(section)
            continue
        entries = list(prev.entries) + list(section.entries)
        renumbered: list[CVEntry] = []
        for i, entry in enumerate(entries):
            renumbered.append(
                entry.model_copy(
                    update={
                        "ordinal": i,
                        "id": deterministic_entry_id(
                            extraction_version=EXTRACTION_VERSION,
                            section_ordinal=prev.ordinal,
                            entry_ordinal=i,
                            heading=prev.heading,
                            title=entry.title,
                        ),
                    }
                )
            )
        sources = sorted(
            {o for e in renumbered for o in e.source_chunk_ordinals}
        )
        merged[-1] = prev.model_copy(
            update={"entries": renumbered, "source_chunk_ordinals": sources}
        )
    # Re-ordinal sections after merges.
    result: list[CVSection] = []
    for i, section in enumerate(merged):
        entries = [
            e.model_copy(
                update={
                    "id": deterministic_entry_id(
                        extraction_version=EXTRACTION_VERSION,
                        section_ordinal=i,
                        entry_ordinal=e.ordinal,
                        heading=section.heading,
                        title=e.title,
                    )
                }
            )
            for e in section.entries
        ]
        result.append(
            section.model_copy(
                update={
                    "ordinal": i,
                    "id": deterministic_section_id(
                        extraction_version=EXTRACTION_VERSION,
                        ordinal=i,
                        heading=section.heading,
                    ),
                    "entries": entries,
                }
            )
        )
    return result


def apply_coverage_recovery(
    sections: Sequence[CVSection],
    chunks: Sequence[CanonicalChunk],
    *,
    warnings: list[str],
    extraction_version: str = EXTRACTION_VERSION,
) -> list[CVSection]:
    """Ensure every chunk ordinal is represented; recover gaps as kind='other'."""
    ordered = sorted(chunks, key=lambda c: c.ordinal)
    all_ordinals = {c.ordinal for c in ordered}
    covered: set[int] = set()
    for section in sections:
        covered.update(section.source_chunk_ordinals)
        for entry in section.entries:
            covered.update(entry.source_chunk_ordinals)
    missing = sorted(all_ordinals - covered)
    if not missing:
        return list(sections)

    by_ord = {c.ordinal: c for c in ordered}
    recovered_entries: list[CVEntry] = []
    for ord_ in missing:
        chunk = by_ord[ord_]
        text = chunk.text.strip()
        if not text:
            warnings.append(f"empty unreferenced chunk ordinal {ord_} skipped")
            continue
        entry_ord = len(recovered_entries)
        recovered_entries.append(
            CVEntry(
                id=deterministic_entry_id(
                    extraction_version=extraction_version,
                    section_ordinal=len(sections),
                    entry_ordinal=entry_ord,
                    heading="Recovered content",
                    title=f"Chunk {ord_}",
                ),
                ordinal=entry_ord,
                title=f"Chunk {ord_}",
                subtitle=None,
                date_text=None,
                location=None,
                body=text,
                bullets=[],
                attributes={},
                source_chunk_ordinals=[ord_],
            )
        )
        warnings.append(
            f"unreferenced chunk ordinal {ord_} recovered as kind=other"
        )

    if not recovered_entries:
        return list(sections)

    result = list(sections)
    # Append or extend a trailing recovered-other section.
    if result and result[-1].kind == "other" and normalize_heading_key(
        result[-1].heading
    ) == normalize_heading_key("Recovered content"):
        base = result[-1]
        entries = list(base.entries)
        for entry in recovered_entries:
            i = len(entries)
            entries.append(
                entry.model_copy(
                    update={
                        "ordinal": i,
                        "id": deterministic_entry_id(
                            extraction_version=extraction_version,
                            section_ordinal=base.ordinal,
                            entry_ordinal=i,
                            heading=base.heading,
                            title=entry.title,
                        ),
                    }
                )
            )
        sources = sorted({o for e in entries for o in e.source_chunk_ordinals})
        result[-1] = base.model_copy(
            update={"entries": entries, "source_chunk_ordinals": sources}
        )
    else:
        section_ord = len(result)
        renumbered = [
            e.model_copy(
                update={
                    "ordinal": i,
                    "id": deterministic_entry_id(
                        extraction_version=extraction_version,
                        section_ordinal=section_ord,
                        entry_ordinal=i,
                        heading="Recovered content",
                        title=e.title,
                    ),
                }
            )
            for i, e in enumerate(recovered_entries)
        ]
        sources = sorted({o for e in renumbered for o in e.source_chunk_ordinals})
        result.append(
            CVSection(
                id=deterministic_section_id(
                    extraction_version=extraction_version,
                    ordinal=section_ord,
                    heading="Recovered content",
                ),
                ordinal=section_ord,
                heading="Recovered content",
                kind="other",
                entries=renumbered,
                source_chunk_ordinals=sources,
            )
        )
    return result


def _batch_prompt(batch: ChunkBatch) -> list[Any]:
    lines = [
        f"attachment_id: {batch.attachment_id}",
        f"ordinal_range: {batch.start_ordinal}..{batch.end_ordinal}",
        "chunks:",
    ]
    for chunk in batch.chunks:
        lines.append(f"[ordinal={chunk.ordinal}]")
        lines.append(chunk.text)
        lines.append("[/chunk]")
    body = "\n".join(lines)
    return [
        SystemMessage(content=_BATCH_SYSTEM),
        HumanMessage(
            content=(
                "Extract section/entry fragments from this bounded CV chunk "
                f"batch only.\n\n--- BATCH START ---\n{body}\n--- BATCH END ---"
            )
        ),
    ]


def _consolidation_prompt(
    fragments: Sequence[ExtractedSectionFragment],
    *,
    attachment_id: str,
) -> list[Any]:
    payload = json.dumps(
        [f.model_dump(mode="json") for f in fragments],
        ensure_ascii=False,
    )
    return [
        SystemMessage(content=_CONSOLIDATE_SYSTEM),
        HumanMessage(
            content=(
                f"attachment_id: {attachment_id}\n"
                "Consolidate these section fragments into one ordered document "
                f"outline.\n\n--- FRAGMENTS START ---\n{payload}\n"
                "--- FRAGMENTS END ---"
            )
        ),
    ]


def _with_repair(messages: list[Any], repair_error: str | None) -> list[Any]:
    if repair_error is None:
        return messages
    return [
        *messages,
        HumanMessage(
            content=(
                "Your previous structured output failed validation with this "
                f"error:\n{repair_error}\n"
                "Repair: return one valid structured JSON object only."
            )
        ),
    ]


def _invoke_with_repair(
    invoker: StructuredCVDocumentInvoker,
    messages: list[Any],
    *,
    schema_name: str,
    coerce: Callable[[Any], Any],
) -> tuple[Any, int, int]:
    """Invoke with provider retry and at most one schema repair.

    Returns ``(coerced, repairs_used, provider_retries)``.
    """
    repairs_used = 0
    provider_retries = 0
    repair_error: str | None = None
    while True:
        msgs = _with_repair(messages, repair_error)
        is_repair = repair_error is not None

        def _call() -> Any:
            return invoker.invoke_structured(
                msgs, schema_name=schema_name, is_repair=is_repair
            )

        try:
            raw, retries = invoke_with_provider_retry(_call)
            provider_retries += retries
            return coerce(raw), repairs_used, provider_retries
        except ProviderRetryError as exc:
            raise CVDocumentExtractionError(exc.code, exc.message) from exc
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if repairs_used >= _MAX_REPAIR_ATTEMPTS:
                raise CVDocumentExtractionError(
                    FAILURE_INVALID_STRUCTURED_OUTPUT,
                    "structured output invalid after one repair attempt",
                ) from exc
            repairs_used += 1
            repair_error = str(exc)[:500]
            continue


class ShopAIKeyStructuredCVDocumentInvoker:
    """Production invoker: ShopAIKey + strict JSON schema for batch/consolidate."""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model if model is not None else build_shopaikey_chat()
        self._batch = self._model.with_structured_output(
            ExtractedBatchDocument,
            method=STRUCTURED_OUTPUT_METHOD,
            strict=STRUCTURED_OUTPUT_STRICT,
        )
        self._consolidate = self._model.with_structured_output(
            ExtractedConsolidation,
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
        schema_name: str,
        is_repair: bool = False,
    ) -> Any:
        del is_repair
        if schema_name == "batch":
            return self._batch.invoke(list(messages))
        if schema_name == "consolidate":
            return self._consolidate.invoke(list(messages))
        raise CVDocumentExtractionError(
            FAILURE_INVALID_STRUCTURED_OUTPUT,
            f"unknown structured schema {schema_name!r}",
        )


def _fragments_char_size(fragments: Sequence[ExtractedSectionFragment]) -> int:
    return len(
        json.dumps([f.model_dump(mode="json") for f in fragments], ensure_ascii=False)
    )


def consolidate_fragments(
    fragments: Sequence[ExtractedSectionFragment],
    *,
    attachment_id: str,
    invoker: StructuredCVDocumentInvoker,
    max_chars: int | None = None,
) -> tuple[ExtractedConsolidation, int, int]:
    """One logical consolidation; hierarchical adjacent merges when over ceiling."""
    if max_chars is None:
        max_chars = batch_max_chars_from_settings()
    items = list(fragments)
    if not items:
        return (
            ExtractedConsolidation(
                detected_languages=[],
                sections=[],
                extraction_warnings=["no section fragments to consolidate"],
                extraction_confidence=0.0,
            ),
            0,
            0,
        )

    size = _fragments_char_size(items)
    # Leaf already extracted: passthrough (avoids unbounded recursion / extra
    # calls when a single fragment still exceeds the ceiling).
    if len(items) == 1:
        return (
            ExtractedConsolidation(
                detected_languages=[],
                sections=items,
                extraction_warnings=[],
                extraction_confidence=1.0,
            ),
            0,
            0,
        )

    if size <= max_chars:
        result, repairs, retries = _invoke_with_repair(
            invoker,
            _consolidation_prompt(items, attachment_id=attachment_id),
            schema_name="consolidate",
            coerce=_coerce_consolidation,
        )
        return result, repairs, retries

    # Hierarchical: consolidate adjacent halves, then one final merge.
    mid = len(items) // 2
    left, r1, t1 = consolidate_fragments(
        items[:mid],
        attachment_id=attachment_id,
        invoker=invoker,
        max_chars=max_chars,
    )
    right, r2, t2 = consolidate_fragments(
        items[mid:],
        attachment_id=attachment_id,
        invoker=invoker,
        max_chars=max_chars,
    )
    combined = list(left.sections) + list(right.sections)
    warnings = list(left.extraction_warnings) + list(right.extraction_warnings)
    conf = min(
        float(left.extraction_confidence),
        float(right.extraction_confidence),
    )
    langs = list(
        dict.fromkeys([*left.detected_languages, *right.detected_languages])
    )
    # If still oversized, accept deterministic merge of the two sides.
    if _fragments_char_size(combined) > max_chars:
        warnings.append(
            "hierarchical consolidation used deterministic final merge"
        )
        return (
            ExtractedConsolidation(
                detected_languages=langs,
                sections=combined,
                extraction_warnings=warnings,
                extraction_confidence=conf,
            ),
            r1 + r2,
            t1 + t2,
        )
    final, r3, t3 = _invoke_with_repair(
        invoker,
        _consolidation_prompt(combined, attachment_id=attachment_id),
        schema_name="consolidate",
        coerce=_coerce_consolidation,
    )
    return final, r1 + r2 + r3, t1 + t2 + t3


def build_cv_document_from_consolidated(
    consolidated: ExtractedConsolidation,
    chunks: Sequence[CanonicalChunk],
    *,
    attachment_id: str,
    extraction_version: str = EXTRACTION_VERSION,
) -> CVDocument:
    """IDs, adjacent merge, coverage recovery, and strict validation."""
    allowed = {c.ordinal for c in chunks}
    sections = sections_from_fragments(
        consolidated.sections,
        extraction_version=extraction_version,
        allowed_ordinals=allowed,
    )
    sections = merge_adjacent_sections(sections)
    warnings = list(consolidated.extraction_warnings)
    sections = apply_coverage_recovery(
        sections,
        chunks,
        warnings=warnings,
        extraction_version=extraction_version,
    )
    conf = float(consolidated.extraction_confidence)
    if conf < 0.0:
        conf = 0.0
    elif conf > 1.0:
        conf = 1.0
    # Final coverage assertion.
    covered: set[int] = set()
    for section in sections:
        covered.update(section.source_chunk_ordinals)
    missing = allowed - covered
    if missing:
        raise CVDocumentExtractionError(
            FAILURE_COVERAGE,
            f"coverage audit failed for ordinals {sorted(missing)}",
        )
    return parse_cv_document(
        {
            "attachment_id": attachment_id,
            "detected_languages": list(consolidated.detected_languages),
            "sections": [s.model_dump(mode="json") for s in sections],
            "extraction_warnings": warnings,
            "extraction_confidence": conf,
        }
    )


def extract_cv_document_from_chunks(
    chunks: Sequence[CanonicalChunk],
    *,
    attachment_id: str,
    invoker: StructuredCVDocumentInvoker,
    max_chars: int | None = None,
    extraction_version: str = EXTRACTION_VERSION,
) -> CVDocumentExtractionOutcome:
    """Bounded batch extraction → consolidation → coverage → validated document.

    No provider call receives the complete raw PDF body. Each batch includes
    attachment ID and exact ordinal range only.
    """
    if max_chars is None:
        max_chars = batch_max_chars_from_settings()
    batches = partition_chunks_by_char_ceiling(
        chunks, attachment_id=attachment_id, max_chars=max_chars
    )
    logger.debug(
        "cv document extraction attachment=%s batches=%s chunks=%s",
        attachment_id,
        len(batches),
        len(chunks),
    )

    all_fragments: list[ExtractedSectionFragment] = []
    languages: list[str] = []
    batch_warnings: list[str] = []
    confidences: list[float] = []
    repairs_total = 0
    retries_total = 0

    for batch in batches:
        allowed = set(batch.ordinals)
        extracted, repairs, retries = _invoke_with_repair(
            invoker,
            _batch_prompt(batch),
            schema_name="batch",
            coerce=_coerce_batch,
        )
        repairs_total += repairs
        retries_total += retries
        languages.extend(extracted.detected_languages)
        batch_warnings.extend(extracted.extraction_warnings)
        confidences.append(float(extracted.extraction_confidence))
        for section in extracted.sections:
            # Clamp ordinals to this batch only.
            clamped_entries = []
            for entry in section.entries:
                ords = _filter_ordinals(entry.source_chunk_ordinals, allowed)
                if not ords and allowed:
                    ords = [min(allowed)]
                clamped_entries.append(
                    entry.model_copy(update={"source_chunk_ordinals": ords})
                )
            sec_ords = _filter_ordinals(section.source_chunk_ordinals, allowed)
            if clamped_entries:
                sec_ords = sorted(
                    {o for e in clamped_entries for o in e.source_chunk_ordinals}
                )
            all_fragments.append(
                section.model_copy(
                    update={
                        "entries": clamped_entries,
                        "source_chunk_ordinals": sec_ords,
                    }
                )
            )

    if len(batches) == 1 and all_fragments:
        # Single batch: still run consolidation contract on fragments (not raw PDF).
        consolidated, r, t = consolidate_fragments(
            all_fragments,
            attachment_id=attachment_id,
            invoker=invoker,
            max_chars=max_chars,
        )
        repairs_total += r
        retries_total += t
    elif all_fragments:
        consolidated, r, t = consolidate_fragments(
            all_fragments,
            attachment_id=attachment_id,
            invoker=invoker,
            max_chars=max_chars,
        )
        repairs_total += r
        retries_total += t
    else:
        consolidated = ExtractedConsolidation(
            detected_languages=list(dict.fromkeys(languages)),
            sections=[],
            extraction_warnings=batch_warnings
            + ["no sections extracted from batches"],
            extraction_confidence=0.0,
        )

    # Merge batch-level languages/warnings into consolidation when empty.
    if not consolidated.detected_languages and languages:
        consolidated = consolidated.model_copy(
            update={"detected_languages": list(dict.fromkeys(languages))}
        )
    if batch_warnings:
        consolidated = consolidated.model_copy(
            update={
                "extraction_warnings": list(consolidated.extraction_warnings)
                + batch_warnings
            }
        )
    if confidences and consolidated.extraction_confidence == 0.0:
        consolidated = consolidated.model_copy(
            update={"extraction_confidence": min(confidences)}
        )

    document = build_cv_document_from_consolidated(
        consolidated,
        chunks,
        attachment_id=attachment_id,
        extraction_version=extraction_version,
    )
    return CVDocumentExtractionOutcome(
        document=document,
        schema_repairs_used=repairs_total,
        provider_retries_used=retries_total,
        batches=tuple(batches),
        extraction_version=extraction_version,
    )


__all__ = [
    "CHUNK_JOIN",
    "CVDocumentExtractionError",
    "CVDocumentExtractionOutcome",
    "ChunkBatch",
    "DEFAULT_BATCH_MAX_CHARS",
    "EXTRACTION_VERSION",
    "ExtractedBatchDocument",
    "ExtractedConsolidation",
    "ExtractedEntryFragment",
    "ExtractedSectionFragment",
    "FAILURE_COVERAGE",
    "FAILURE_EMPTY_CHUNKS",
    "FAILURE_INVALID_STRUCTURED_OUTPUT",
    "FAILURE_PROVIDER_ERROR",
    "FAILURE_PROVIDER_RATE_LIMIT",
    "FAILURE_PROVIDER_TIMEOUT",
    "ShopAIKeyStructuredCVDocumentInvoker",
    "StructuredCVDocumentInvoker",
    "apply_coverage_recovery",
    "batch_max_chars_from_settings",
    "build_cv_document_from_consolidated",
    "consolidate_fragments",
    "deterministic_entry_id",
    "deterministic_section_id",
    "extract_cv_document_from_chunks",
    "merge_adjacent_sections",
    "normalize_heading_key",
    "partition_chunks_by_char_ceiling",
    "sections_from_fragments",
]
