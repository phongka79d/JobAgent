"""Idempotent CV / CVSection / CVEntry graph synchronization (Plan 9 / Master §8).

After SQLite approval of a retained CV document, projects one fixed-label
branch into Neo4j:

* ``MERGE`` ``CV{id=<attachment UUID>}`` with allowlisted metadata only
* Replace only that CV's ``CVSection`` / ``CVEntry`` owned nodes
* Stable ordinal order; entry ``preview`` is a bounded safe prefix
* When *is_active*, clear all ``PROJECTS_TO`` edges and attach this CV once
* When not active, ensure this CV has no ``PROJECTS_TO`` (archived branch)

Never copies full entry bodies, bullets lists, arbitrary attributes, chunk
text, or PDF bytes. Shared driver protocol, failure codes, timestamp/result
helpers live in :mod:`app.graph.sync_shared`. Domain skill projection stays
in :mod:`app.graph.sync_candidate`.

Callers inject an async Neo4j driver (real or fake). Failures raise
:class:`CvSyncError` with stable code ``NEO4J_SYNC_FAILED``; they must not
roll back committed SQLite state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.graph.sync_shared import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
    consume_result,
    iso_utc,
)
from app.schemas.cv_document import CVDocument, CVEntry, CVSection

# Same bound as attachment chunk list previews (Plan 8 Persistence).
CV_ENTRY_PREVIEW_MAX_CHARS: Final[int] = 240

# Fixed allowlisted labels / relationships for static review.
_ALLOWED_LABELS: frozenset[str] = frozenset({"CV", "CVSection", "CVEntry", "Candidate"})
_ALLOWED_RELS: frozenset[str] = frozenset(
    {"HAS_SECTION", "HAS_ENTRY", "PROJECTS_TO"}
)

# Forbidden property keys on graph payloads (raw content stays SQLite-only).
_FORBIDDEN_ENTRY_KEYS: frozenset[str] = frozenset(
    {"body", "bullets", "attributes", "location", "source_chunk_ordinals"}
)


class CvSyncError(Exception):
    """Raised when CV graph synchronization fails.

    Carries stable ``code`` (always :data:`NEO4J_SYNC_FAILED` for this owner)
    and developer rebuild guidance. Never embeds secrets or raw CV text.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = NEO4J_SYNC_FAILED,
        rebuild_instruction: str = NEO4J_REBUILD_INSTRUCTION,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.rebuild_instruction = rebuild_instruction
        self.message = message


def bounded_entry_preview(
    text: str,
    *,
    max_chars: int = CV_ENTRY_PREVIEW_MAX_CHARS,
) -> str:
    """Bounded display-safe preview (exact prefix; no ellipsis mutation)."""
    if max_chars < 0:
        raise CvSyncError("max_chars must be >= 0")
    if not isinstance(text, str):
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def scoped_section_id(attachment_id: str, section_id: str) -> str:
    """Master §6.6: ``CVSection.id = '<attachment_id>:<section_id>'``."""
    return f"{attachment_id}:{section_id}"


def scoped_entry_id(attachment_id: str, section_id: str, entry_id: str) -> str:
    """Master §6.6: ``CVEntry.id = '<attachment_id>:<section_id>:<entry_id>'``."""
    return f"{attachment_id}:{section_id}:{entry_id}"


def _preview_source(entry: CVEntry) -> str:
    """Derive preview text without storing body/bullets arrays in Neo4j."""
    body = entry.body.strip() if isinstance(entry.body, str) else ""
    if body:
        return body
    if entry.bullets:
        return " ".join(b for b in entry.bullets if isinstance(b, str) and b.strip())
    return ""


def _section_row(attachment_id: str, section: CVSection) -> dict[str, Any]:
    return {
        "id": scoped_section_id(attachment_id, section.id),
        "heading": section.heading,
        "kind": section.kind,
        "ordinal": int(section.ordinal),
        "entry_count": len(section.entries),
    }


def _entry_row(
    attachment_id: str,
    section: CVSection,
    entry: CVEntry,
) -> dict[str, Any]:
    row = {
        "id": scoped_entry_id(attachment_id, section.id, entry.id),
        "section_id": scoped_section_id(attachment_id, section.id),
        "ordinal": int(entry.ordinal),
        "title": entry.title,
        "subtitle": entry.subtitle,
        "date_text": entry.date_text,
        "preview": bounded_entry_preview(_preview_source(entry)),
    }
    for key in _FORBIDDEN_ENTRY_KEYS:
        if key in row:
            raise CvSyncError(f"forbidden CV entry property {key!r}")
    return row


def build_cv_graph_payload(
    document: CVDocument,
    *,
    original_name: str,
    extraction_version: str,
    source_updated_at: datetime,
) -> dict[str, Any]:
    """Build parameterized Cypher payload for one approved CV document.

    Sections/entries are stably ordered by ordinal. Payload contains only
    Master-allowlisted properties (no body/bullets/attributes/chunks).
    """
    if not isinstance(document, CVDocument):
        raise CvSyncError("document must be a validated CVDocument")
    if not isinstance(original_name, str) or original_name.strip() == "":
        raise CvSyncError("original_name must be a non-empty string")
    if not isinstance(extraction_version, str) or extraction_version.strip() == "":
        raise CvSyncError("extraction_version must be a non-empty string")
    if not isinstance(source_updated_at, datetime):
        raise CvSyncError(
            "source_updated_at must be a datetime from cv_documents.updated_at"
        )

    attachment_id = str(document.attachment_id)
    sections_sorted = sorted(document.sections, key=lambda s: s.ordinal)
    section_rows = [_section_row(attachment_id, s) for s in sections_sorted]
    entry_rows: list[dict[str, Any]] = []
    for section in sections_sorted:
        for entry in sorted(section.entries, key=lambda e: e.ordinal):
            entry_rows.append(_entry_row(attachment_id, section, entry))

    return {
        "cv_id": attachment_id,
        "original_name": original_name,
        "extraction_version": extraction_version,
        "source_updated_at": iso_utc(source_updated_at),
        "candidate_id": CANDIDATE_PROFILE_ID,
        "sections": section_rows,
        "entries": entry_rows,
    }


def assert_payload_safe(payload: Mapping[str, Any]) -> None:
    """Raise when *payload* embeds forbidden raw-content keys."""
    for entry in payload.get("entries", []):
        if not isinstance(entry, Mapping):
            raise CvSyncError("entry payload rows must be mappings")
        for key in _FORBIDDEN_ENTRY_KEYS:
            if key in entry:
                raise CvSyncError(f"forbidden CV entry property {key!r}")
        preview = entry.get("preview")
        if isinstance(preview, str) and len(preview) > CV_ENTRY_PREVIEW_MAX_CHARS:
            raise CvSyncError("entry preview exceeds bound")
    for section in payload.get("sections", []):
        if not isinstance(section, Mapping):
            raise CvSyncError("section payload rows must be mappings")
        if "source_chunk_ordinals" in section:
            raise CvSyncError("section source_chunk_ordinals must not enter Neo4j")


# Fixed Cypher templates (parameters only; no runtime string interpolation).
MERGE_CV_CYPHER: str = (
    "MERGE (cv:CV {id: $cv_id}) "
    "SET cv.original_name = $original_name, "
    "    cv.extraction_version = $extraction_version, "
    "    cv.source_updated_at = $source_updated_at "
    "RETURN cv.id AS id"
)

CLEAR_CV_OWNED_CYPHER: str = (
    "MATCH (cv:CV {id: $cv_id}) "
    "OPTIONAL MATCH (cv)-[:HAS_SECTION]->(sec:CVSection) "
    "OPTIONAL MATCH (sec)-[:HAS_ENTRY]->(entry:CVEntry) "
    "DETACH DELETE entry, sec"
)

MERGE_SECTIONS_CYPHER: str = (
    "UNWIND $sections AS row "
    "MATCH (cv:CV {id: $cv_id}) "
    "MERGE (sec:CVSection {id: row.id}) "
    "SET sec.heading = row.heading, "
    "    sec.kind = row.kind, "
    "    sec.ordinal = row.ordinal, "
    "    sec.entry_count = row.entry_count "
    "MERGE (cv)-[:HAS_SECTION]->(sec)"
)

MERGE_ENTRIES_CYPHER: str = (
    "UNWIND $entries AS row "
    "MATCH (sec:CVSection {id: row.section_id}) "
    "MERGE (entry:CVEntry {id: row.id}) "
    "SET entry.ordinal = row.ordinal, "
    "    entry.title = row.title, "
    "    entry.subtitle = row.subtitle, "
    "    entry.date_text = row.date_text, "
    "    entry.preview = row.preview "
    "MERGE (sec)-[:HAS_ENTRY]->(entry)"
)

CLEAR_ALL_PROJECTS_TO_CYPHER: str = (
    "MATCH (:CV)-[r:PROJECTS_TO]->(c:Candidate {id: $candidate_id}) "
    "DELETE r"
)

MERGE_PROJECTS_TO_CYPHER: str = (
    "MATCH (cv:CV {id: $cv_id}) "
    "MATCH (c:Candidate {id: $candidate_id}) "
    "MERGE (cv)-[:PROJECTS_TO]->(c)"
)

CLEAR_THIS_CV_PROJECTS_TO_CYPHER: str = (
    "MATCH (cv:CV {id: $cv_id})-[r:PROJECTS_TO]->() "
    "DELETE r"
)


async def sync_cv(
    driver: AsyncGraphDriver,
    *,
    document: CVDocument,
    original_name: str,
    extraction_version: str,
    source_updated_at: datetime,
    is_active: bool,
) -> None:
    """Project one approved CV document onto Neo4j with fixed identities.

    When *is_active* is True, exactly one ``PROJECTS_TO`` edge from this CV
    to Candidate remains. When False, this CV never holds ``PROJECTS_TO``.
    Idempotent and parameterized. Raises :class:`CvSyncError` without
    mutating SQLite.
    """
    params = build_cv_graph_payload(
        document,
        original_name=original_name,
        extraction_version=extraction_version,
        source_updated_at=source_updated_at,
    )
    assert_payload_safe(params)

    try:
        async with driver.session() as session:
            result = await session.run(MERGE_CV_CYPHER, params)
            await consume_result(result)
            result = await session.run(CLEAR_CV_OWNED_CYPHER, params)
            await consume_result(result)
            if params["sections"]:
                result = await session.run(MERGE_SECTIONS_CYPHER, params)
                await consume_result(result)
            if params["entries"]:
                result = await session.run(MERGE_ENTRIES_CYPHER, params)
                await consume_result(result)
            if is_active:
                result = await session.run(CLEAR_ALL_PROJECTS_TO_CYPHER, params)
                await consume_result(result)
                result = await session.run(MERGE_PROJECTS_TO_CYPHER, params)
                await consume_result(result)
            else:
                result = await session.run(CLEAR_THIS_CV_PROJECTS_TO_CYPHER, params)
                await consume_result(result)
    except CvSyncError:
        raise
    except Exception as exc:
        raise CvSyncError(
            "CV branch Neo4j synchronization failed"
        ) from exc


def cypher_statement_templates() -> Sequence[str]:
    """Return fixed Cypher templates for static review (no runtime values)."""
    return (
        "MERGE (cv:CV {id: $cv_id})",
        "MATCH (cv:CV {id: $cv_id})",
        "MERGE (sec:CVSection {id: row.id})",
        "MERGE (cv)-[:HAS_SECTION]->(sec)",
        "MERGE (entry:CVEntry {id: row.id})",
        "MERGE (sec)-[:HAS_ENTRY]->(entry)",
        "MATCH (:CV)-[r:PROJECTS_TO]->(c:Candidate {id: $candidate_id})",
        "MERGE (cv)-[:PROJECTS_TO]->(c)",
        "MATCH (cv:CV {id: $cv_id})-[r:PROJECTS_TO]->()",
    )


__all__ = [
    "CLEAR_ALL_PROJECTS_TO_CYPHER",
    "CLEAR_CV_OWNED_CYPHER",
    "CLEAR_THIS_CV_PROJECTS_TO_CYPHER",
    "CV_ENTRY_PREVIEW_MAX_CHARS",
    "MERGE_CV_CYPHER",
    "MERGE_ENTRIES_CYPHER",
    "MERGE_PROJECTS_TO_CYPHER",
    "MERGE_SECTIONS_CYPHER",
    "AsyncGraphDriver",
    "CvSyncError",
    "NEO4J_REBUILD_INSTRUCTION",
    "NEO4J_SYNC_FAILED",
    "assert_payload_safe",
    "bounded_entry_preview",
    "build_cv_graph_payload",
    "cypher_statement_templates",
    "scoped_entry_id",
    "scoped_section_id",
    "sync_cv",
]
