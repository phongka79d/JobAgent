"""Bounded active-only CV reader for Agent evidence pages (Master §13.7).

Resolves the active attachment server-side. Supports ``section``, ``search``,
and ``chunk`` modes with independent ``max_results`` / ``max_chars`` caps,
stable source order, truncation metadata, and opaque cursors bound to the
active attachment, source hash, mode, selector, and last stable identity.

Never accepts a caller-supplied attachment ID. Never returns PDF bytes, storage
paths, archived document bodies, or unbounded whole-CV dumps.

Legacy active CVs (no ``cv_documents`` row): ``section`` fails with
``CV_DOCUMENT_REPROCESS_REQUIRED``; ``search`` / ``chunk`` read existing
chunks only.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.active_cv_context import LEGACY_EXTRACTION_VERSION
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as profile_repo
from app.schemas.cv_document import parse_cv_document
from app.schemas.tools import ToolResult

ReadMode = Literal["section", "search", "chunk"]

DEFAULT_MAX_RESULTS: int = 5
MIN_MAX_RESULTS: int = 1
MAX_MAX_RESULTS: int = 10
DEFAULT_MAX_CHARS: int = 6000
MIN_MAX_CHARS: int = 500
MAX_MAX_CHARS: int = 12_000

ERROR_NO_ACTIVE_CV: str = "NO_ACTIVE_CV"
ERROR_ACTIVE_CV_CHANGED: str = "ACTIVE_CV_CHANGED"
ERROR_CV_DOCUMENT_REPROCESS_REQUIRED: str = "CV_DOCUMENT_REPROCESS_REQUIRED"
ERROR_INVALID_INPUT: str = "INVALID_READ_ACTIVE_CV_INPUT"
ERROR_MALFORMED_CURSOR: str = "MALFORMED_CURSOR"
ERROR_SECTION_NOT_FOUND: str = "SECTION_NOT_FOUND"
ERROR_CHUNK_NOT_FOUND: str = "CHUNK_NOT_FOUND"
ACTIVE_CV_CHANGED_SUMMARY: str = (
    "Active CV selection or revision changed; request a new page"
)

_CURSOR_KEYS: frozenset[str] = frozenset(
    {"v", "attachment_id", "source_hash", "mode", "selector", "after"}
)
_CURSOR_VERSION: int = 1

# Ceiling for local O(n) scan: one active CV's entries + chunks only.
_LOCAL_SEARCH_ENTRY_CHUNK_CEILING: int = 2_000


@dataclass(frozen=True, slots=True)
class _ActiveTarget:
    attachment_id: str
    extraction_version: str
    source_hash: str
    reprocess_required: bool
    document_json: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class ActiveCvIdentity:
    attachment_id: str
    source_hash: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One ordered candidate record before pagination/caps."""

    identity: str
    record: dict[str, Any]
    text_for_budget: str


def encode_active_cv_cursor(
    *,
    attachment_id: str,
    source_hash: str,
    mode: str,
    selector: str,
    after: str,
) -> str:
    """Encode a revision-bound opaque cursor (URL-safe base64 JSON)."""
    payload = {
        "v": _CURSOR_VERSION,
        "attachment_id": attachment_id,
        "source_hash": source_hash,
        "mode": mode,
        "selector": selector,
        "after": after,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_active_cv_cursor(cursor: str) -> dict[str, Any]:
    """Decode and validate an opaque active-CV cursor.

    Raises ``ValueError`` for malformed encoding or shape.
    """
    if not isinstance(cursor, str) or cursor.strip() == "":
        raise ValueError("cursor encoding is malformed")
    text = cursor.strip()
    if any(ch in text for ch in ("+", "/", " ", "\n", "\r", "\t")):
        raise ValueError("cursor encoding is malformed")
    pad = "=" * (-len(text) % 4)
    try:
        raw = base64.b64decode(text + pad, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("cursor encoding is malformed") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor encoding is malformed") from exc
    if not isinstance(data, dict) or set(data.keys()) != _CURSOR_KEYS:
        raise ValueError("cursor shape is invalid")
    if data.get("v") != _CURSOR_VERSION:
        raise ValueError("cursor version is unsupported")
    for key in ("attachment_id", "source_hash", "mode", "selector", "after"):
        val = data.get(key)
        if not isinstance(val, str):
            raise ValueError("cursor shape is invalid")
        if key != "source_hash" and val.strip() == "":
            raise ValueError("cursor shape is invalid")
    return data


def _fail(code: str, summary: str, *, data: dict[str, Any] | None = None) -> ToolResult:
    return ToolResult(ok=False, code=code, summary=summary, data=data)


def _success(
    *,
    attachment_id: str,
    extraction_version: str,
    source_hash: str | None,
    mode: str,
    records: list[dict[str, Any]],
    returned_chars: int,
    truncated: bool,
    next_cursor: str | None,
    summary: str,
) -> ToolResult:
    return ToolResult(
        ok=True,
        code=None,
        summary=summary,
        data={
            "attachment_id": attachment_id,
            "extraction_version": extraction_version,
            "source_hash": source_hash,
            "mode": mode,
            "records": records,
            "returned_chars": returned_chars,
            "truncated": truncated,
            "next_cursor": next_cursor,
        },
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _validate_bounds(
    max_results: int,
    max_chars: int,
) -> str | None:
    if (
        not isinstance(max_results, int)
        or isinstance(max_results, bool)
        or max_results < MIN_MAX_RESULTS
        or max_results > MAX_MAX_RESULTS
    ):
        return (
            f"max_results must be an integer in "
            f"{MIN_MAX_RESULTS}..{MAX_MAX_RESULTS}"
        )
    if (
        not isinstance(max_chars, int)
        or isinstance(max_chars, bool)
        or max_chars < MIN_MAX_CHARS
        or max_chars > MAX_MAX_CHARS
    ):
        return (
            f"max_chars must be an integer in "
            f"{MIN_MAX_CHARS}..{MAX_MAX_CHARS}"
        )
    return None


async def _resolve_active_target(session: AsyncSession) -> _ActiveTarget | ToolResult:
    profile = await profile_repo.get_active_profile(session)
    if profile is None:
        return _fail(ERROR_NO_ACTIVE_CV, "No active CV/profile is available")
    attachment_id = profile.active_attachment_id
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        return _fail(ERROR_NO_ACTIVE_CV, "No active CV attachment is available")

    doc = await cv_doc_repo.get_document(session, attachment_id)
    if doc is None:
        return _ActiveTarget(
            attachment_id=attachment_id,
            extraction_version=LEGACY_EXTRACTION_VERSION,
            source_hash="",
            reprocess_required=True,
            document_json=None,
        )
    return _ActiveTarget(
        attachment_id=attachment_id,
        extraction_version=doc.extraction_version,
        source_hash=doc.source_hash,
        reprocess_required=False,
        document_json=(
            doc.document_json if isinstance(doc.document_json, dict) else None
        ),
    )


async def resolve_active_cv_identity(
    session: AsyncSession,
) -> ActiveCvIdentity | ToolResult:
    resolved = await _resolve_active_target(session)
    if isinstance(resolved, ToolResult):
        return resolved
    return ActiveCvIdentity(
        attachment_id=resolved.attachment_id,
        source_hash=resolved.source_hash,
    )


def _bind_cursor(
    *,
    cursor: str | None,
    target: _ActiveTarget,
    mode: str,
    selector: str,
) -> tuple[str | None, ToolResult | None]:
    """Return (after_identity, error)."""
    if cursor is None:
        return None, None
    try:
        payload = decode_active_cv_cursor(cursor)
    except ValueError:
        return None, _fail(
            ERROR_MALFORMED_CURSOR,
            "Cursor encoding or shape is invalid",
        )

    if (
        payload["attachment_id"] != target.attachment_id
        or payload["source_hash"] != target.source_hash
    ):
        return None, _fail(
            ERROR_ACTIVE_CV_CHANGED,
            ACTIVE_CV_CHANGED_SUMMARY,
        )
    if payload["mode"] != mode or payload["selector"] != selector:
        return None, _fail(
            ERROR_MALFORMED_CURSOR,
            "Cursor does not match the current mode or selector",
        )
    after = payload["after"]
    return after if after else None, None


def _page_candidates(
    candidates: list[_Candidate],
    *,
    after: str | None,
    max_results: int,
    max_chars: int,
    attachment_id: str,
    source_hash: str,
    mode: str,
    selector: str,
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    """Apply after-cursor skip, result cap, and character cap."""
    start = 0
    if after is not None:
        found = False
        for i, cand in enumerate(candidates):
            if cand.identity == after:
                start = i + 1
                found = True
                break
        if not found:
            # Stale identity after revision-equivalent content change.
            start = len(candidates)

    window = candidates[start:]
    records: list[dict[str, Any]] = []
    used = 0
    truncated = False
    last_identity: str | None = None
    stop_index = -1

    for idx, cand in enumerate(window):
        if len(records) >= max_results:
            break
        remaining = max_chars - used
        if remaining <= 0:
            break
        text = cand.text_for_budget
        record = dict(cand.record)
        if len(text) > remaining:
            # Oversized single record: truncate text fields in place.
            _truncate_record_text(record, remaining)
            record["record_truncated"] = True
            records.append(record)
            used += remaining
            truncated = True
            last_identity = cand.identity
            stop_index = idx
            break
        records.append(record)
        used += len(text)
        last_identity = cand.identity
        stop_index = idx

    next_cursor: str | None = None
    has_more = stop_index >= 0 and (stop_index + 1) < len(window)
    # Also more when we stopped due to max_results with remaining window.
    if len(records) >= max_results and (start + len(records)) < len(candidates):
        has_more = True
    if truncated and last_identity is not None:
        has_more = True
        # Cursor advances past truncated record so the agent does not re-read it.
        next_cursor = encode_active_cv_cursor(
            attachment_id=attachment_id,
            source_hash=source_hash,
            mode=mode,
            selector=selector,
            after=last_identity,
        )
    elif has_more and last_identity is not None:
        next_cursor = encode_active_cv_cursor(
            attachment_id=attachment_id,
            source_hash=source_hash,
            mode=mode,
            selector=selector,
            after=last_identity,
        )

    return records, used, truncated, next_cursor


def _truncate_record_text(record: dict[str, Any], budget: int) -> None:
    """Truncate primary text fields to fit *budget* characters total."""
    if budget <= 0:
        if "body" in record:
            record["body"] = ""
        if "text" in record:
            record["text"] = ""
        if "excerpt" in record:
            record["excerpt"] = ""
        return
    remaining = budget
    for key in ("body", "text", "excerpt"):
        val = record.get(key)
        if not isinstance(val, str):
            continue
        if len(val) <= remaining:
            remaining -= len(val)
        else:
            record[key] = val[:remaining]
            remaining = 0
    bullets = record.get("bullets")
    if isinstance(bullets, list) and remaining == 0:
        record["bullets"] = []


def _entry_search_blob(entry: Any) -> str:
    parts: list[str] = []
    for attr in ("title", "subtitle", "date_text", "location", "body"):
        val = getattr(entry, attr, None)
        if isinstance(val, str):
            parts.append(val)
    for bullet in getattr(entry, "bullets", ()) or ():
        if isinstance(bullet, str):
            parts.append(bullet)
    attrs = getattr(entry, "attributes", None) or {}
    if isinstance(attrs, dict):
        for value in attrs.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(x for x in value if isinstance(x, str))
    return " ".join(parts)


def _entry_record(section_id: str, entry: Any) -> tuple[dict[str, Any], str]:
    body = entry.body if isinstance(entry.body, str) else ""
    bullets = [b for b in (entry.bullets or ()) if isinstance(b, str)]
    title = entry.title if isinstance(entry.title, str) else None
    subtitle = entry.subtitle if isinstance(entry.subtitle, str) else None
    record = {
        "kind": "entry",
        "section_id": section_id,
        "entry_id": entry.id,
        "ordinal": entry.ordinal,
        "title": title,
        "subtitle": subtitle,
        "date_text": entry.date_text if isinstance(entry.date_text, str) else None,
        "location": entry.location if isinstance(entry.location, str) else None,
        "body": body,
        "bullets": bullets,
        "source_chunk_ordinals": list(entry.source_chunk_ordinals or ()),
    }
    text_for_budget = body + "".join(bullets)
    if title:
        text_for_budget = title + text_for_budget
    return record, text_for_budget


def _chunk_record(ordinal: int, text: str) -> tuple[dict[str, Any], str]:
    record = {
        "kind": "chunk",
        "ordinal": ordinal,
        "text": text,
        "char_count": len(text),
    }
    return record, text


def _section_candidates(
    document_json: dict[str, Any],
    section_id: str,
) -> list[_Candidate] | ToolResult:
    try:
        document = parse_cv_document(document_json)
    except Exception:
        return _fail(ERROR_INVALID_INPUT, "Active CV document is invalid")
    section = next((s for s in document.sections if s.id == section_id), None)
    if section is None:
        return _fail(
            ERROR_SECTION_NOT_FOUND,
            f"Section {section_id!r} was not found on the active CV",
        )
    out: list[_Candidate] = []
    for entry in section.entries:
        record, text = _entry_record(section.id, entry)
        out.append(
            _Candidate(
                identity=f"entry:{entry.id}",
                record=record,
                text_for_budget=text,
            )
        )
    return out


async def _search_candidates(
    session: AsyncSession,
    target: _ActiveTarget,
    query: str,
) -> list[_Candidate]:
    """Scan structured entries then chunks in stable source order."""
    # ponytail: O(n) structured-entry/chunk search is intentional for one
    # bounded local active CV (ceiling: 2000 combined entry+chunk rows). Acceptable
    # because only the single active CV is scanned per call. Upgrade to SQLite FTS
    # when measured document size exceeds that local contract.
    query_norm = _normalize_text(query)
    out: list[_Candidate] = []
    scanned = 0

    if target.document_json is not None and not target.reprocess_required:
        try:
            document = parse_cv_document(target.document_json)
        except Exception:
            document = None
        if document is not None:
            for section in document.sections:
                for entry in section.entries:
                    scanned += 1
                    if scanned > _LOCAL_SEARCH_ENTRY_CHUNK_CEILING:
                        break
                    blob = _entry_search_blob(entry)
                    if query_norm and query_norm in _normalize_text(blob):
                        record, text = _entry_record(section.id, entry)
                        # Prefer a short excerpt for search hits.
                        excerpt = blob if len(blob) <= 400 else blob[:400]
                        record = dict(record)
                        record["kind"] = "entry_match"
                        record["excerpt"] = excerpt
                        out.append(
                            _Candidate(
                                identity=f"entry:{entry.id}",
                                record=record,
                                text_for_budget=excerpt + text,
                            )
                        )
                if scanned > _LOCAL_SEARCH_ENTRY_CHUNK_CEILING:
                    break

    chunks = await chunk_repo.list_for_attachment(session, target.attachment_id)
    for row in chunks:
        scanned += 1
        if scanned > _LOCAL_SEARCH_ENTRY_CHUNK_CEILING:
            break
        text = row.text if isinstance(row.text, str) else ""
        if query_norm and query_norm in _normalize_text(text):
            record, budget_text = _chunk_record(row.ordinal, text)
            record = dict(record)
            record["kind"] = "chunk_match"
            excerpt = text if len(text) <= 400 else text[:400]
            record["excerpt"] = excerpt
            out.append(
                _Candidate(
                    identity=f"chunk:{row.ordinal}",
                    record=record,
                    text_for_budget=excerpt,
                )
            )
    return out


async def _chunk_candidates(
    session: AsyncSession,
    target: _ActiveTarget,
    chunk_ordinal: int,
) -> list[_Candidate] | ToolResult:
    chunks = await chunk_repo.list_for_attachment(session, target.attachment_id)
    if not chunks:
        return _fail(ERROR_CHUNK_NOT_FOUND, "Active CV has no text chunks")
    # Page starts at the requested ordinal (inclusive) in ascending order.
    ordered = [c for c in chunks if c.ordinal >= chunk_ordinal]
    if not ordered:
        return _fail(
            ERROR_CHUNK_NOT_FOUND,
            f"No chunk at or after ordinal {chunk_ordinal}",
        )
    out: list[_Candidate] = []
    for row in ordered:
        text = row.text if isinstance(row.text, str) else ""
        record, budget_text = _chunk_record(row.ordinal, text)
        out.append(
            _Candidate(
                identity=f"chunk:{row.ordinal}",
                record=record,
                text_for_budget=budget_text,
            )
        )
    return out


def _selector_for(
    mode: str,
    *,
    section_id: str | None,
    query: str | None,
    chunk_ordinal: int | None,
) -> str:
    if mode == "section":
        return f"section:{section_id}"
    if mode == "search":
        return f"search:{_normalize_text(query or '')}"
    return f"chunk:{chunk_ordinal if chunk_ordinal is not None else 0}"


async def read_active_cv(
    session: AsyncSession,
    *,
    mode: str,
    section_id: str | None = None,
    query: str | None = None,
    chunk_ordinal: int | None = None,
    cursor: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_chars: int = DEFAULT_MAX_CHARS,
    expected_identity: ActiveCvIdentity | None = None,
    expected_no_active: bool = False,
) -> ToolResult:
    """Read one bounded page of active-CV evidence.

    Resolves the active attachment server-side. Callers must not pass
    attachment IDs. Returns a validated :class:`ToolResult`.
    """
    bound_err = _validate_bounds(max_results, max_chars)
    if bound_err is not None:
        return _fail(ERROR_INVALID_INPUT, bound_err)

    if mode not in ("section", "search", "chunk"):
        return _fail(
            ERROR_INVALID_INPUT,
            "mode must be one of: section, search, chunk",
        )

    if mode == "section":
        if not isinstance(section_id, str) or section_id.strip() == "":
            return _fail(
                ERROR_INVALID_INPUT,
                "section mode requires a non-empty section_id",
            )
        section_id = section_id.strip()
    elif mode == "search":
        if not isinstance(query, str) or query.strip() == "":
            return _fail(
                ERROR_INVALID_INPUT,
                "search mode requires a non-empty query",
            )
        query = query.strip()
    else:
        if cursor is None:
            if (
                not isinstance(chunk_ordinal, int)
                or isinstance(chunk_ordinal, bool)
                or chunk_ordinal < 0
            ):
                return _fail(
                    ERROR_INVALID_INPUT,
                    "chunk mode requires a non-negative chunk_ordinal",
                )
        elif chunk_ordinal is None:
            chunk_ordinal = 0
        elif (
            not isinstance(chunk_ordinal, int)
            or isinstance(chunk_ordinal, bool)
            or chunk_ordinal < 0
        ):
            return _fail(
                ERROR_INVALID_INPUT,
                "chunk_ordinal must be a non-negative integer when provided",
            )

    resolved = await _resolve_active_target(session)
    if isinstance(resolved, ToolResult):
        return resolved
    target = resolved
    actual_identity = ActiveCvIdentity(
        attachment_id=target.attachment_id,
        source_hash=target.source_hash,
    )
    if expected_no_active or (
        expected_identity is not None and actual_identity != expected_identity
    ):
        return _fail(ERROR_ACTIVE_CV_CHANGED, ACTIVE_CV_CHANGED_SUMMARY)

    selector = _selector_for(
        mode,
        section_id=section_id,
        query=query,
        chunk_ordinal=chunk_ordinal,
    )
    after, cursor_err = _bind_cursor(
        cursor=cursor,
        target=target,
        mode=mode,
        selector=selector,
    )
    if cursor_err is not None:
        return cursor_err

    if mode == "section":
        if target.reprocess_required or target.document_json is None:
            return _fail(
                ERROR_CV_DOCUMENT_REPROCESS_REQUIRED,
                "Active CV has no structured document; reprocess is required "
                "before section reads",
                data={
                    "attachment_id": target.attachment_id,
                    "reprocess_required": True,
                },
            )
        assert section_id is not None
        built = _section_candidates(target.document_json, section_id)
        if isinstance(built, ToolResult):
            return built
        candidates = built
    elif mode == "search":
        assert query is not None
        candidates = await _search_candidates(session, target, query)
    else:
        assert chunk_ordinal is not None
        built_chunks = await _chunk_candidates(session, target, chunk_ordinal)
        if isinstance(built_chunks, ToolResult):
            return built_chunks
        candidates = built_chunks

    records, returned_chars, truncated, next_cursor = _page_candidates(
        candidates,
        after=after,
        max_results=max_results,
        max_chars=max_chars,
        attachment_id=target.attachment_id,
        source_hash=target.source_hash,
        mode=mode,
        selector=selector,
    )

    source_hash_out: str | None = (
        None if target.reprocess_required else target.source_hash
    )
    count = len(records)
    summary = (
        f"Returned {count} active CV record(s) for mode={mode}"
        + (" (truncated)" if truncated else "")
    )
    return _success(
        attachment_id=target.attachment_id,
        extraction_version=target.extraction_version,
        source_hash=source_hash_out,
        mode=mode,
        records=records,
        returned_chars=returned_chars,
        truncated=truncated,
        next_cursor=next_cursor,
        summary=summary,
    )


__all__ = [
    "DEFAULT_MAX_CHARS",
    "DEFAULT_MAX_RESULTS",
    "ERROR_ACTIVE_CV_CHANGED",
    "ACTIVE_CV_CHANGED_SUMMARY",
    "ActiveCvIdentity",
    "ERROR_CHUNK_NOT_FOUND",
    "ERROR_CV_DOCUMENT_REPROCESS_REQUIRED",
    "ERROR_INVALID_INPUT",
    "ERROR_MALFORMED_CURSOR",
    "ERROR_NO_ACTIVE_CV",
    "ERROR_SECTION_NOT_FOUND",
    "MAX_MAX_CHARS",
    "MAX_MAX_RESULTS",
    "MIN_MAX_CHARS",
    "MIN_MAX_RESULTS",
    "decode_active_cv_cursor",
    "encode_active_cv_cursor",
    "read_active_cv",
    "resolve_active_cv_identity",
]
