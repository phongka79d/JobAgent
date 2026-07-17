"""Flush-only persistence for approved and draft CV document rows.

Persists only serialized document/profile/outline artifacts supplied by the
service boundary. Never validates Pydantic shapes, never commits, and never
implements extraction, approval, or deletion lifecycle business logic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.cv_documents import CVDocument, CVDocumentDraft


class CVDocumentRepositoryError(Exception):
    """Base error for CV document repository invariant violations."""


def _require_nonempty_str(value: object, field: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise CVDocumentRepositoryError(f"{field} must be a non-empty string")
    return value


def _require_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CVDocumentRepositoryError(f"{field} must be a mapping")
    return value


async def get_document(
    session: AsyncSession,
    attachment_id: str,
) -> CVDocument | None:
    """Return the approved document for *attachment_id*, or ``None``."""
    return await session.get(CVDocument, attachment_id)


async def upsert_document(
    session: AsyncSession,
    *,
    attachment_id: str,
    document_json: dict[str, Any],
    profile_json: dict[str, Any],
    outline_json: dict[str, Any],
    extraction_version: str,
    source_hash: str,
) -> CVDocument:
    """Insert or replace the approved document row for *attachment_id*.

    Does not validate JSON document shapes. Does not finalize the caller's
    unit of work.
    """
    attachment_id = _require_nonempty_str(attachment_id, "attachment_id")
    document_json = _require_mapping(document_json, "document_json")
    profile_json = _require_mapping(profile_json, "profile_json")
    outline_json = _require_mapping(outline_json, "outline_json")
    extraction_version = _require_nonempty_str(
        extraction_version, "extraction_version"
    )
    source_hash = _require_nonempty_str(source_hash, "source_hash")

    now = utc_now()
    row = await session.get(CVDocument, attachment_id)
    if row is None:
        row = CVDocument(
            attachment_id=attachment_id,
            document_json=document_json,
            profile_json=profile_json,
            outline_json=outline_json,
            extraction_version=extraction_version,
            source_hash=source_hash,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.document_json = document_json
        row.profile_json = profile_json
        row.outline_json = outline_json
        row.extraction_version = extraction_version
        row.source_hash = source_hash
        row.updated_at = now
    await session.flush()
    return row


async def delete_document(session: AsyncSession, attachment_id: str) -> bool:
    """Delete the approved document for *attachment_id* if present.

    Returns ``True`` when a row was deleted. Does not finalize the unit of work.
    """
    row = await session.get(CVDocument, attachment_id)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def get_draft(
    session: AsyncSession,
    attachment_id: str,
) -> CVDocumentDraft | None:
    """Return the draft document for *attachment_id*, or ``None``."""
    return await session.get(CVDocumentDraft, attachment_id)


async def upsert_draft(
    session: AsyncSession,
    *,
    attachment_id: str,
    document_json: dict[str, Any],
    profile_json: dict[str, Any],
    outline_json: dict[str, Any],
    extraction_version: str,
    source_hash: str,
) -> CVDocumentDraft:
    """Insert or replace the draft document row for *attachment_id*.

    Does not validate JSON document shapes. Does not finalize the caller's
    unit of work.
    """
    attachment_id = _require_nonempty_str(attachment_id, "attachment_id")
    document_json = _require_mapping(document_json, "document_json")
    profile_json = _require_mapping(profile_json, "profile_json")
    outline_json = _require_mapping(outline_json, "outline_json")
    extraction_version = _require_nonempty_str(
        extraction_version, "extraction_version"
    )
    source_hash = _require_nonempty_str(source_hash, "source_hash")

    now = utc_now()
    row = await session.get(CVDocumentDraft, attachment_id)
    if row is None:
        row = CVDocumentDraft(
            attachment_id=attachment_id,
            document_json=document_json,
            profile_json=profile_json,
            outline_json=outline_json,
            extraction_version=extraction_version,
            source_hash=source_hash,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.document_json = document_json
        row.profile_json = profile_json
        row.outline_json = outline_json
        row.extraction_version = extraction_version
        row.source_hash = source_hash
        row.updated_at = now
    await session.flush()
    return row


async def delete_draft(session: AsyncSession, attachment_id: str) -> bool:
    """Delete the draft document for *attachment_id* if present.

    Returns ``True`` when a row was deleted. Does not finalize the unit of work.
    """
    row = await session.get(CVDocumentDraft, attachment_id)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True
