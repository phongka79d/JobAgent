"""Focused CV activation helpers for approval (Plan 9 / Master §6.4 §10.4).

Owns attachment activation order and document-draft promotion used inside the
single SQLite approval transaction. Does not open sessions, commit, sync Neo4j,
or perform filesystem I/O. Callers supply an open session and preflight data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import cv_documents as cv_doc_repo
from app.services.profile_extraction import (
    CanonicalChunk,
    compute_canonical_source_hash,
)


class ActivationError(Exception):
    """Activation preflight or in-transaction invariant failure."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class DocumentDraftBundle:
    """Validated document-draft rows coupled to a CV-backed profile draft."""

    attachment_id: str
    document_json: dict[str, Any]
    profile_json: dict[str, Any]
    outline_json: dict[str, Any]
    extraction_version: str
    source_hash: str


async def load_document_draft_bundle(
    session: AsyncSession,
    *,
    attachment_id: str,
) -> DocumentDraftBundle:
    """Load and couple document draft + source hash for *attachment_id*.

    Requires a ``cv_document_drafts`` row and matching ordered chunk hash.
    """
    doc_draft = await cv_doc_repo.get_draft(session, attachment_id)
    if doc_draft is None:
        raise ActivationError(
            "CV-backed draft requires a matching cv_document_drafts row",
            code="DOCUMENT_DRAFT_NOT_FOUND",
        )
    if not isinstance(doc_draft.source_hash, str) or not doc_draft.source_hash:
        raise ActivationError(
            "Document draft is missing source_hash",
            code="DOCUMENT_DRAFT_INVALID",
        )
    rows = await chunk_repo.list_for_attachment(session, attachment_id)
    if not rows:
        raise ActivationError(
            "Document draft source chunks are missing",
            code="DOCUMENT_DRAFT_INVALID",
        )
    canonical = tuple(
        CanonicalChunk(ordinal=int(row.ordinal), text=str(row.text))
        for row in rows
    )
    try:
        expected = compute_canonical_source_hash(canonical)
    except Exception as exc:
        raise ActivationError(
            "Document draft source chunks failed hash coupling",
            code="DOCUMENT_DRAFT_INVALID",
        ) from exc
    if expected != doc_draft.source_hash:
        raise ActivationError(
            "Document draft source_hash does not match stored chunks",
            code="DOCUMENT_DRAFT_INVALID",
        )
    if not isinstance(doc_draft.document_json, dict):
        raise ActivationError(
            "Document draft document_json must be an object",
            code="DOCUMENT_DRAFT_INVALID",
        )
    if not isinstance(doc_draft.profile_json, dict):
        raise ActivationError(
            "Document draft profile_json must be an object",
            code="DOCUMENT_DRAFT_INVALID",
        )
    if not isinstance(doc_draft.outline_json, dict):
        raise ActivationError(
            "Document draft outline_json must be an object",
            code="DOCUMENT_DRAFT_INVALID",
        )
    if (
        not isinstance(doc_draft.extraction_version, str)
        or not doc_draft.extraction_version.strip()
    ):
        raise ActivationError(
            "Document draft extraction_version is required",
            code="DOCUMENT_DRAFT_INVALID",
        )
    return DocumentDraftBundle(
        attachment_id=attachment_id,
        document_json=dict(doc_draft.document_json),
        profile_json=dict(doc_draft.profile_json),
        outline_json=dict(doc_draft.outline_json),
        extraction_version=doc_draft.extraction_version,
        source_hash=doc_draft.source_hash,
    )


def assert_source_attachment_eligible(attachment: Attachment) -> None:
    """CV-backed drafts may target staged, archived, or active reprocess rows."""
    if attachment.state not in (
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_ACTIVE,
    ):
        raise ActivationError(
            f"Draft source attachment state {attachment.state!r} is not "
            "eligible for approval",
            code="ATTACHMENT_NOT_STAGED",
        )
    if attachment.page_count is None or attachment.page_count <= 0:
        raise ActivationError(
            "Source attachment requires page_count > 0 before activation",
            code="ATTACHMENT_NOT_STAGED",
        )


async def activate_selected_attachment(
    session: AsyncSession,
    *,
    attachment_id: str,
    old_attachment_id: str | None,
) -> None:
    """Archive prior active when IDs differ; activate selected CV.

    * Staged → active via repository transition.
    * Archived → active only here (approval of reprocessed archived CV).
    * Already active (same-ID re-extract) leaves lifecycle unchanged.
    """
    if old_attachment_id is not None and old_attachment_id != attachment_id:
        await att_repo.mark_archived(session, old_attachment_id)

    current = await att_repo.get_by_id(session, attachment_id)
    if current is None:
        raise ActivationError(
            "Approved attachment disappeared during transaction",
            code="ATTACHMENT_NOT_FOUND",
        )

    if current.state == ATTACHMENT_STATE_ACTIVE:
        return

    if current.state == ATTACHMENT_STATE_STAGED:
        await att_repo.mark_active(
            session,
            attachment_id,
            page_count=current.page_count,
        )
        return

    if current.state == ATTACHMENT_STATE_ARCHIVED:
        # Master §6.2: archived → active only inside reprocess approval.
        if current.page_count is None or current.page_count <= 0:
            raise ActivationError(
                "Archived attachment requires page_count > 0 to activate",
                code="ATTACHMENT_NOT_STAGED",
            )
        current.state = ATTACHMENT_STATE_ACTIVE
        current.failure_code = None
        current.updated_at = utc_now()
        await session.flush()
        return

    raise ActivationError(
        f"Attachment in unexpected state {current.state!r}",
        code="ATTACHMENT_NOT_STAGED",
    )


async def promote_document_draft(
    session: AsyncSession,
    bundle: DocumentDraftBundle,
) -> None:
    """Upsert approved ``cv_documents`` from the draft bundle and delete draft."""
    await cv_doc_repo.upsert_document(
        session,
        attachment_id=bundle.attachment_id,
        document_json=bundle.document_json,
        profile_json=bundle.profile_json,
        outline_json=bundle.outline_json,
        extraction_version=bundle.extraction_version,
        source_hash=bundle.source_hash,
    )
    await cv_doc_repo.delete_draft(session, bundle.attachment_id)


__all__ = [
    "ActivationError",
    "DocumentDraftBundle",
    "activate_selected_attachment",
    "assert_source_attachment_eligible",
    "load_document_draft_bundle",
    "promote_document_draft",
]
