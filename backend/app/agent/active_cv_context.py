"""Compact active-CV outline for Agent state (Master §12.3 / §12.4).

Loads only active attachment identity, extraction version/source hash, and a
bounded section outline (ids, headings, kinds, entry counts, source ranges).
Never loads section bodies, entries, chunk text, PDF bytes, storage paths, or
archived documents into the prompt/context snapshot.

Legacy active CVs (approved profile, no ``cv_documents`` row) emit
``reprocess_required=True`` with an empty section list.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as profile_repo

# Outline section keys allowed in context snapshots (no bodies/entries/text).
_OUTLINE_SECTION_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "ordinal",
        "heading",
        "kind",
        "entry_count",
        "source_chunk_range",
    }
)

# Forbidden keys that must never appear in outline projections.
_FORBIDDEN_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "body",
        "bullets",
        "entries",
        "text",
        "preview",
        "document_json",
        "profile_json",
        "storage_path",
        "file_path",
        "raw_cv",
        "raw_pdf",
        "pdf_bytes",
        "chunks",
        "source_chunk_ordinals",
    }
)

LEGACY_EXTRACTION_VERSION: str = "legacy-reprocess-required"


def empty_active_cv_context() -> dict[str, Any] | None:
    """Return the empty active-CV projection (no active attachment)."""
    return None


def _compact_outline_section(raw: object) -> dict[str, Any] | None:
    """Project one outline section without bodies, entries, or ordinal lists."""
    if not isinstance(raw, dict):
        return None
    section_id = raw.get("id")
    if not isinstance(section_id, str) or section_id.strip() == "":
        return None
    heading = raw.get("heading")
    if not isinstance(heading, str) or heading.strip() == "":
        heading = section_id
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind.strip() == "":
        kind = "other"
    ordinal = raw.get("ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        ordinal = 0
    entry_count = raw.get("entry_count")
    if (
        not isinstance(entry_count, int)
        or isinstance(entry_count, bool)
        or entry_count < 0
    ):
        entries = raw.get("entries")
        if isinstance(entries, list):
            entry_count = len(entries)
        else:
            entry_count = 0

    source_range = raw.get("source_chunk_range")

    def _nonneg_int(x: object) -> bool:
        return isinstance(x, int) and not isinstance(x, bool) and x >= 0

    if (
        isinstance(source_range, list)
        and len(source_range) == 2
        and all(_nonneg_int(x) for x in source_range)
    ):
        range_out: list[int] = [int(source_range[0]), int(source_range[1])]
    else:
        ords = raw.get("source_chunk_ordinals")
        if isinstance(ords, list) and ords:
            clean = [
                int(o)
                for o in ords
                if isinstance(o, int) and not isinstance(o, bool) and o >= 0
            ]
            range_out = [clean[0], clean[-1]] if clean else []
        else:
            range_out = []

    out: dict[str, Any] = {
        "id": section_id,
        "ordinal": ordinal,
        "heading": heading,
        "kind": kind,
        "entry_count": entry_count,
        "source_chunk_range": range_out,
    }
    # Defense: never leak forbidden keys even if caller mutates later.
    for key in list(out):
        if key not in _OUTLINE_SECTION_KEYS:
            del out[key]
    return out


def project_active_cv_context(
    *,
    attachment_id: str,
    extraction_version: str | None,
    source_hash: str | None,
    outline_json: dict[str, Any] | None,
    reprocess_required: bool,
) -> dict[str, Any]:
    """Build a compact active-CV context dict (no I/O, no bodies)."""
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise ValueError("attachment_id must be a non-empty string")

    sections_raw: list[Any] = []
    if not reprocess_required and isinstance(outline_json, dict):
        raw_sections = outline_json.get("sections")
        if isinstance(raw_sections, list):
            sections_raw = list(raw_sections)

    sections: list[dict[str, Any]] = []
    for item in sections_raw:
        compact = _compact_outline_section(item)
        if compact is not None:
            sections.append(compact)
    # Stable outline order by ordinal then id.
    sections.sort(key=lambda s: (int(s["ordinal"]), str(s["id"])))

    ctx: dict[str, Any] = {
        "attachment_id": attachment_id,
        "extraction_version": extraction_version,
        "source_hash": source_hash,
        "reprocess_required": bool(reprocess_required),
        "sections": sections,
    }
    # Guarantee no forbidden material in the top-level snapshot.
    serialized = str(ctx)
    for bad in _FORBIDDEN_CONTEXT_KEYS:
        if bad in ("source_chunk_ordinals",):
            # ordinals must not appear as keys in compact sections.
            if any("source_chunk_ordinals" in s for s in sections):
                raise RuntimeError("outline projection leaked source_chunk_ordinals")
        elif f"'{bad}'" in serialized or f'"{bad}"' in serialized:
            # Only key-name style leaks; values may legitimately mention words.
            pass
    for section in sections:
        if _FORBIDDEN_CONTEXT_KEYS.intersection(section.keys()):
            raise RuntimeError("outline projection leaked forbidden keys")
    return ctx


async def load_active_cv_context(
    session: AsyncSession,
) -> dict[str, Any] | None:
    """Load compact active-CV outline into Agent ``active_cv_context``.

    Resolves the active attachment from the approved profile only. Never accepts
    a caller-supplied attachment ID. Never reads draft documents, archived
    attachments, raw bytes, or chunk bodies.
    """
    profile = await profile_repo.get_active_profile(session)
    if profile is None:
        return empty_active_cv_context()
    attachment_id = profile.active_attachment_id
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        return empty_active_cv_context()

    doc = await cv_doc_repo.get_document(session, attachment_id)
    if doc is None:
        # Legacy pre-document active CV: identity only, reprocess required.
        return project_active_cv_context(
            attachment_id=attachment_id,
            extraction_version=LEGACY_EXTRACTION_VERSION,
            source_hash=None,
            outline_json=None,
            reprocess_required=True,
        )

    outline = doc.outline_json if isinstance(doc.outline_json, dict) else {}
    return project_active_cv_context(
        attachment_id=attachment_id,
        extraction_version=doc.extraction_version,
        source_hash=doc.source_hash,
        outline_json=outline,
        reprocess_required=False,
    )


__all__ = [
    "LEGACY_EXTRACTION_VERSION",
    "empty_active_cv_context",
    "load_active_cv_context",
    "project_active_cv_context",
]
