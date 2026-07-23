"""Focused CV activation helpers for approval (Plan 9 / Master §6.4 §10.4).

Owns approval helpers plus the sole profile-selection coordinator. Selection
commits one short SQLite session, then refreshes the persisted Candidate/CV
graph branch after that session closes. It performs no filesystem, provider,
extraction, embedding, or scoring work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.time import utc_now
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.graph.sync_shared import NEO4J_REBUILD_INSTRUCTION, NEO4J_SYNC_FAILED
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import cv_documents as cv_doc_repo
from app.services.cv_chunk_contracts import CanonicalChunk
from app.services.profile_extraction import compute_canonical_source_hash

if TYPE_CHECKING:
    from app.schemas.cv_document import CVDocument
    from app.schemas.profile import CandidateProfile, SelectionResponse


class ActivationError(Exception):
    """Activation preflight or in-transaction invariant failure."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProfileActivationError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary


class ProfileGraphSyncError(Exception):
    """Safe post-commit wrapper for persisted profile graph refresh failures."""

    def __init__(self) -> None:
        super().__init__("profile graph synchronization failed")
        self.code = NEO4J_SYNC_FAILED
        self.summary = (
            "Profile selection was saved, but its graph projection could not be "
            "refreshed."
        )
        self.guidance = NEO4J_REBUILD_INSTRUCTION


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
        CanonicalChunk(ordinal=int(row.ordinal), text=str(row.text)) for row in rows
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
    * Archived → active only here (approval or durable profile selection).
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
        # Archived CVs reactivate only through an approved lifecycle owner.
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


async def activate_profile_by_id(
    *,
    profile_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    graph_driver: Any | None = None,
) -> SelectionResponse:
    """Commit workspace/profile selection before any optional derived refresh."""
    from app.db.models.profiles import PROFILE_STATE_READY
    from app.repositories import conversations as conversations_repo
    from app.repositories import profiles as profiles_repo
    from app.repositories import workspace_state as workspace_repo
    from app.schemas.profile import SafeWarning, SelectionResponse
    from app.services.activity_gate import ActivityBlockedError, assert_workspace_idle
    from app.services.conversations import project_conversation
    from app.services.profile_projection import (
        ProfileProjectionError,
        project_profile_detail,
    )

    async with session_factory() as session:
        try:
            try:
                await assert_workspace_idle(session)
            except ActivityBlockedError as exc:
                raise ProfileActivationError(exc.code, exc.summary) from exc
            profile = await profiles_repo.get_profile(session, profile_id)
            if profile is None:
                raise ProfileActivationError(
                    "PROFILE_NOT_FOUND", "profile not found"
                )
            if profile.state != PROFILE_STATE_READY:
                raise ProfileActivationError(
                    "PROFILE_NOT_READY", "profile is not ready"
                )
            incomplete = await profiles_repo.get_incomplete_profile(session)
            if incomplete is not None:
                raise ProfileActivationError(
                    "PROFILE_SETUP_IN_PROGRESS",
                    "finish or discard the pending profile setup first",
                )
            current_id = await workspace_repo.get_active_profile_id(session)
            current = (
                await profiles_repo.get_profile(session, current_id)
                if current_id
                else None
            )
            if current_id is not None and current is None:
                raise ProfileActivationError(
                    "PROFILE_INCONSISTENT", "active profile selection is inconsistent"
                )
            await activate_selected_attachment(
                session,
                attachment_id=profile.attachment_id,
                old_attachment_id=current.attachment_id if current else None,
            )
            await workspace_repo.set_active_profile_id(session, profile_id)
            profile.last_opened_at = utc_now()
            selected = await conversations_repo.most_recent_for_profile(
                session, profile_id=profile_id
            )
            detail = await project_profile_detail(
                session, profile, active_id=profile_id
            )
            conversation = None
            if selected is not None:
                conversation = project_conversation(selected, selected=True)
            await session.commit()
        except ProfileActivationError:
            await session.rollback()
            raise
        except (ActivationError, ProfileProjectionError) as exc:
            await session.rollback()
            raise ProfileActivationError(
                "PROFILE_INCONSISTENT", "profile selection data is inconsistent"
            ) from exc
        except Exception as exc:
            await session.rollback()
            raise ProfileActivationError(
                "PROFILE_INCONSISTENT", "profile selection could not be saved"
            ) from exc

    warning = None
    if graph_driver is not None:
        try:
            await refresh_profile_branch(
                graph_driver,
                profile_id=profile_id,
                session_factory=session_factory,
            )
        except ProfileGraphSyncError as exc:
            warning = SafeWarning(
                code=exc.code,
                summary=exc.summary,
                guidance=exc.guidance,
            )
    return SelectionResponse(
        profile=detail, conversation=conversation, warning=warning
    )


@dataclass(frozen=True, slots=True)
class _ProfileGraphInputs:
    profile: CandidateProfile
    profile_updated_at: datetime
    document: CVDocument
    original_name: str
    extraction_version: str
    document_updated_at: datetime
    source_hash: str


async def _load_profile_graph_inputs(
    *,
    profile_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> _ProfileGraphInputs:
    from app.repositories import attachments as att_repo
    from app.repositories import cv_documents as cv_doc_repo
    from app.repositories import profiles as profiles_repo
    from app.schemas.cv_document import parse_cv_document
    from app.schemas.profile import parse_candidate_profile
    from app.services.cv_upload import sanitize_original_name

    async with session_factory() as session:
        profile_row = await profiles_repo.get_profile(session, profile_id)
        if profile_row is None:
            raise ProfileGraphSyncError()
        attachment = await att_repo.get_by_id(session, profile_row.attachment_id)
        document_row = await cv_doc_repo.get_document(
            session, profile_row.attachment_id
        )
        if attachment is None or document_row is None:
            raise ProfileGraphSyncError()
        try:
            profile = parse_candidate_profile(profile_row.profile_json)
            document = parse_cv_document(document_row.document_json)
        except (ValidationError, ValueError, TypeError) as exc:
            raise ProfileGraphSyncError() from exc
        if (
            document.attachment_id != profile_row.attachment_id
            or document_row.extraction_version != profile_row.extraction_version
            or document_row.source_hash != profile_row.source_hash
        ):
            raise ProfileGraphSyncError()
        return _ProfileGraphInputs(
            profile=profile,
            profile_updated_at=profile_row.updated_at,
            document=document,
            original_name=sanitize_original_name(attachment.original_name),
            extraction_version=document_row.extraction_version,
            document_updated_at=document_row.updated_at,
            source_hash=document_row.source_hash,
        )


async def refresh_profile_branch(
    graph_driver: Any,
    *,
    profile_id: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Refresh one persisted profile/CV graph branch after SQLite commit."""
    from app.db.session import get_session_factory
    from app.graph.sync_candidate import sync_candidate
    from app.graph.sync_cv import sync_cv
    from app.services.skill_normalization import SkillNormalizer

    try:
        factory = session_factory or get_session_factory()
        inputs = await _load_profile_graph_inputs(
            profile_id=profile_id, session_factory=factory
        )
        normalizer = SkillNormalizer.production()
        await sync_candidate(
            graph_driver,
            profile_id=profile_id,
            profile=inputs.profile,
            source_updated_at=inputs.profile_updated_at,
            normalizer=normalizer,
        )
        await sync_cv(
            graph_driver,
            profile_id=profile_id,
            document=inputs.document,
            original_name=inputs.original_name,
            extraction_version=inputs.extraction_version,
            source_updated_at=inputs.document_updated_at,
            source_hash=inputs.source_hash,
            is_active=True,
        )
    except ProfileGraphSyncError:
        raise
    except Exception as exc:
        raise ProfileGraphSyncError() from exc


__all__ = [
    "ActivationError",
    "ProfileActivationError",
    "ProfileGraphSyncError",
    "DocumentDraftBundle",
    "activate_selected_attachment",
    "assert_source_attachment_eligible",
    "load_document_draft_bundle",
    "promote_document_draft",
    "activate_profile_by_id",
    "refresh_profile_branch",
]
