"""Constraint-safe profile approval transaction (Plan 4 §7.6, Master §6.4/§10.4).

Owns ``commit_approved_draft`` / SQLite-first approval:

1. **Preflight** (no open write transaction): validate the complete draft,
   staged/archived/active source attachment + file + document draft/hash when
   a CV is present, and cross-row prerequisites.
2. **One short SQLite transaction**: upsert active profile, update preferences
   when changed, repoint profile, archive former active only when IDs differ,
   activate the selected attachment, promote document draft → ``cv_documents``,
   delete both drafts, assert one-active invariant, commit.
3. **Post-commit** (never open SQLite txn across these): synchronize
   Candidate/Skill and the active CV branch graph data. Former active
   PDF/chunks stay retained under ``archived`` state (no previous-file cleanup).

Transaction failure triggers ``session_scope`` rollback to the prior active
profile/CV. Neo4j failure never rolls SQLite back; sync failure returns
``NEO4J_SYNC_FAILED`` plus
rebuild guidance while accurately reporting committed SQLite truth.

Archived → active is allowed only inside this approval path for a reprocessed
archived CV. No file moves at approval. No raw CV text in results/logs.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.time import utc_now
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    Attachment,
)
from app.db.models.profiles import (
    PROFILE_DRAFT_ID,
    PROFILE_STATE_PENDING,
    PROFILE_STATE_READY,
)
from app.db.session import session_scope
from app.graph.sync_candidate import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
    CandidateSyncError,
    sync_candidate,
)
from app.graph.sync_cv import CvSyncError, sync_cv
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profile_reextract_operations as operation_repo
from app.repositories import profiles as profile_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.cv_document import CVDocument, parse_cv_document
from app.schemas.profile import (
    CandidateProfile,
    JobPreferences,
    ProfileDraftPayload,
    parse_job_preferences,
    parse_profile_draft_payload,
)
from app.services.profile_activation import (
    ActivationError,
    DocumentDraftBundle,
    activate_selected_attachment,
    assert_source_attachment_eligible,
    load_document_draft_bundle,
    promote_document_draft,
)
from app.services.profile_identity_guard import guard_optional_identity_fields
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage

logger = logging.getLogger(__name__)

# Stable application codes for preflight / transaction / post-commit outcomes.
ERROR_DRAFT_NOT_FOUND: str = "DRAFT_NOT_FOUND"
ERROR_DRAFT_INVALID: str = "DRAFT_INVALID"
ERROR_ATTACHMENT_NOT_FOUND: str = "ATTACHMENT_NOT_FOUND"
ERROR_ATTACHMENT_NOT_STAGED: str = "ATTACHMENT_NOT_STAGED"
ERROR_ATTACHMENT_FILE_MISSING: str = "ATTACHMENT_FILE_MISSING"
ERROR_ACTIVE_PROFILE_MISSING: str = "ACTIVE_PROFILE_MISSING"
ERROR_ACTIVE_ATTACHMENT_MISSING: str = "ACTIVE_ATTACHMENT_MISSING"
ERROR_APPROVAL_TRANSACTION_FAILED: str = "APPROVAL_TRANSACTION_FAILED"
ERROR_INVARIANT_VIOLATION: str = "APPROVAL_INVARIANT_VIOLATION"
ERROR_DOCUMENT_DRAFT_NOT_FOUND: str = "DOCUMENT_DRAFT_NOT_FOUND"
ERROR_DOCUMENT_DRAFT_INVALID: str = "DOCUMENT_DRAFT_INVALID"
_UNSET_OPERATION = object()

# Failpoint names for deterministic integration tests only.
Failpoint = Literal[
    "before_commit",
    "after_profile_upsert",
    "after_old_attachment_archive",
    "after_old_attachment_delete",  # alias kept for older test call sites
    "cleanup",
    "sync",
]


class ProfileApprovalError(Exception):
    """Pre-commit approval failure (SQLite not committed)."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ApprovalCommitResult:
    """Outcome of save_profile SQLite + post-commit cleanup/sync.

    When ``sqlite_committed`` is True the approved profile/preferences/attachment
    truth is durable regardless of ``cleanup_ok`` / ``sync_ok``.
    """

    ok: bool
    code: str | None
    summary: str
    sqlite_committed: bool
    cleanup_ok: bool
    sync_ok: bool
    active_attachment_id: str | None
    profile_updated_at: datetime | None
    previous_attachment_id: str | None
    preferences_updated: bool
    data: dict[str, Any]
    profile_id: str | None = None
    conversation_id: str | None = None


def _prefs_equal(a: JobPreferences, b: JobPreferences) -> bool:
    return a.model_dump(mode="json") == b.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class _Preflight:
    draft: ProfileDraftPayload
    draft_updated_at: datetime
    draft_row_source_attachment_id: str | None
    new_attachment: Attachment | None
    new_storage_path: str | None
    old_attachment_id: str | None
    old_storage_path: str | None
    active_attachment_id_for_profile: str
    preferences_changed: bool
    current_prefs: JobPreferences
    document_bundle: DocumentDraftBundle | None
    target_profile_id: str
    target_profile_state: str
    draft_reextract_operation_id: str | None


def _activation_to_approval_error(exc: ActivationError) -> ProfileApprovalError:
    code_map = {
        "DOCUMENT_DRAFT_NOT_FOUND": ERROR_DOCUMENT_DRAFT_NOT_FOUND,
        "DOCUMENT_DRAFT_INVALID": ERROR_DOCUMENT_DRAFT_INVALID,
        "ATTACHMENT_NOT_FOUND": ERROR_ATTACHMENT_NOT_FOUND,
        "ATTACHMENT_NOT_STAGED": ERROR_ATTACHMENT_NOT_STAGED,
    }
    return ProfileApprovalError(
        exc.message,
        code=code_map.get(exc.code, ERROR_APPROVAL_TRANSACTION_FAILED),
    )


async def _load_preflight(
    session: AsyncSession,
    storage: AttachmentStorage | None,
    *,
    check_files: bool,
    expected_profile_id: str,
    expected_draft_updated_at: datetime | None = None,
) -> _Preflight:
    """Validate draft and attachment prerequisites.

    When *check_files* is True (outer preflight only), confirm the source PDF
    exists on disk. Inside an open SQLite transaction, pass ``check_files=False``
    and ``storage=None`` so the write unit never spans filesystem I/O.
    """
    draft_row = await profile_repo.get_draft_for_profile(
        session, expected_profile_id
    )
    if draft_row is None:
        raise ProfileApprovalError(
            "No current profile draft to approve",
            code=ERROR_DRAFT_NOT_FOUND,
        )
    if expected_draft_updated_at is not None:
        actual_revision = (
            draft_row.updated_at.replace(tzinfo=UTC)
            if draft_row.updated_at.tzinfo is None
            else draft_row.updated_at.astimezone(UTC)
        )
        expected_revision = (
            expected_draft_updated_at.replace(tzinfo=UTC)
            if expected_draft_updated_at.tzinfo is None
            else expected_draft_updated_at.astimezone(UTC)
        )
        if actual_revision != expected_revision:
            raise ProfileApprovalError(
                "The review changed; reload it before approving",
                code="PROFILE_REEXTRACT_CONFLICT",
            )

    try:
        draft = parse_profile_draft_payload(draft_row.draft_json)
    except ValidationError as exc:
        raise ProfileApprovalError(
            "Current draft failed full ProfileDraftPayload validation",
            code=ERROR_DRAFT_INVALID,
        ) from exc

    source_id = draft_row.source_attachment_id
    target_profile_id = draft_row.target_profile_id
    if target_profile_id is None:
        raise ProfileApprovalError(
            "Current profile draft has no explicit owner",
            code="PROFILE_INCONSISTENT",
        )
    target_profile = await profile_repo.get_profile(session, target_profile_id)
    if target_profile is None or target_profile.state not in {
        PROFILE_STATE_PENDING,
        PROFILE_STATE_READY,
    }:
        raise ProfileApprovalError(
            "Target profile is not ready",
            code="PROFILE_NOT_READY",
        )
    target_profile_state = target_profile.state
    if source_id is not None and source_id != target_profile.attachment_id:
        raise ProfileApprovalError(
            "Re-extraction attachment does not belong to target profile",
            code="PROFILE_INCONSISTENT",
        )
    new_attachment: Attachment | None = None
    new_storage_path: str | None = None
    old_attachment_id: str | None = None
    old_storage_path: str | None = None
    document_bundle: DocumentDraftBundle | None = None

    active_profile = target_profile
    active_att = await att_repo.get_active(session)

    if source_id is not None:
        new_attachment = await att_repo.get_by_id(session, source_id)
        if new_attachment is None:
            raise ProfileApprovalError(
                f"Draft source attachment {source_id!r} not found",
                code=ERROR_ATTACHMENT_NOT_FOUND,
            )
        try:
            assert_source_attachment_eligible(new_attachment)
            document_bundle = await load_document_draft_bundle(
                session, attachment_id=source_id
            )
        except ActivationError as exc:
            raise _activation_to_approval_error(exc) from exc
        if check_files:
            if storage is None:
                raise ProfileApprovalError(
                    "Storage owner required for attachment file preflight",
                    code=ERROR_ATTACHMENT_FILE_MISSING,
                )
            if not storage.exists(new_attachment.storage_path):
                raise ProfileApprovalError(
                    "Source attachment file is missing from storage",
                    code=ERROR_ATTACHMENT_FILE_MISSING,
                )
        new_storage_path = new_attachment.storage_path
        active_attachment_id_for_profile = source_id

        if target_profile_state == PROFILE_STATE_PENDING:
            if active_att is not None and active_att.id != source_id:
                old_attachment_id = active_att.id
                old_storage_path = active_att.storage_path
        elif active_profile is not None:
            old_id = active_profile.active_attachment_id
            if old_id != source_id:
                old_attachment_id = old_id
                old_row = await att_repo.get_by_id(session, old_id)
                if old_row is not None:
                    old_storage_path = old_row.storage_path
    else:
        # Preference / correction-only draft: keep existing active attachment.
        if active_profile is None:
            raise ProfileApprovalError(
                "Cannot approve a draft without a source CV when no active "
                "profile exists",
                code=ERROR_ACTIVE_PROFILE_MISSING,
            )
        if active_att is None:
            raise ProfileApprovalError(
                "Active attachment missing for profile without draft CV source",
                code=ERROR_ACTIVE_ATTACHMENT_MISSING,
            )
        active_attachment_id_for_profile = active_profile.active_attachment_id

    prefs_row = await profile_repo.get_profile_preferences(session, target_profile_id)
    if prefs_row is None:
        current_prefs = JobPreferences(
            target_roles=[],
            preferred_locations=[],
            acceptable_work_modes=[],
            target_seniority=[],
        )
    else:
        try:
            current_prefs = parse_job_preferences(prefs_row.preferences_json)
        except ValidationError:
            # Seed/legacy invalid shape treated as always-changed so we rewrite
            # with the validated draft document.
            current_prefs = JobPreferences(
                target_roles=[],
                preferred_locations=[],
                acceptable_work_modes=[],
                target_seniority=[],
            )
    preferences_changed = not _prefs_equal(draft.job_preferences, current_prefs)

    return _Preflight(
        draft=draft,
        draft_updated_at=draft_row.updated_at,
        draft_row_source_attachment_id=source_id,
        new_attachment=new_attachment,
        new_storage_path=new_storage_path,
        old_attachment_id=old_attachment_id,
        old_storage_path=old_storage_path,
        active_attachment_id_for_profile=active_attachment_id_for_profile,
        preferences_changed=preferences_changed,
        current_prefs=current_prefs,
        document_bundle=document_bundle,
        target_profile_id=target_profile_id,
        target_profile_state=target_profile_state,
        draft_reextract_operation_id=draft_row.reextract_operation_id,
    )


async def _validate_operation_linked_approval(
    session: AsyncSession,
    *,
    preflight: _Preflight,
    expected_profile_id: str,
    expected_operation_id: str | None | object,
) -> Any:
    operation_id = preflight.draft_reextract_operation_id
    if expected_operation_id is _UNSET_OPERATION:
        expected_operation_id = operation_id
    if operation_id is None:
        if expected_operation_id is not None:
            raise ProfileApprovalError(
                "Ordinary draft cannot consume a re-extraction operation",
                code="PROFILE_REEXTRACT_CONFLICT",
            )
        return None
    if expected_operation_id != operation_id:
        raise ProfileApprovalError(
            "Re-extraction operation identity changed",
            code="PROFILE_REEXTRACT_CONFLICT",
        )
    operation = await operation_repo.get_operation(
        session, profile_id=expected_profile_id, operation_id=operation_id
    )
    profile = await profile_repo.get_profile(session, expected_profile_id)
    workspace = await workspace_repo.get_state(session)
    if (
        operation is None
        or profile is None
        or workspace is None
        or operation.state != "review_ready"
        or profile.updated_at != operation.base_profile_updated_at
        or workspace.active_profile_id != expected_profile_id
        or workspace.updated_at != operation.base_workspace_updated_at
    ):
        raise ProfileApprovalError(
            "Re-extraction review is stale",
            code="PROFILE_REEXTRACT_STALE",
        )
    return operation


async def _load_approved_cv_sync_inputs(
    factory: async_sessionmaker[AsyncSession],
    attachment_id: str,
) -> tuple[CVDocument, str, str, datetime] | None:
    """Load approved document + attachment metadata for post-commit CV sync.

    Returns ``None`` when no approved ``cv_documents`` row exists (preference-
    only approval or legacy profile without a retained document). Uses a short
    read-only session; never held open across Neo4j I/O.
    """
    async with factory() as session:
        row = await cv_doc_repo.get_document(session, attachment_id)
        if row is None:
            return None
        attachment = await att_repo.get_by_id(session, attachment_id)
        if attachment is None:
            raise CvSyncError(
                "Active attachment missing for approved CV graph sync"
            )
        try:
            document = parse_cv_document(row.document_json)
        except ValidationError as exc:
            raise CvSyncError(
                "Approved cv_documents.document_json failed CVDocument validation"
            ) from exc
        return (
            document,
            attachment.original_name,
            row.extraction_version,
            row.updated_at,
        )


async def _assert_final_invariant(
    session: AsyncSession,
    *,
    profile_id: str,
    expected_attachment_id: str,
    require_active_attachment: bool,
) -> None:
    """Require the approved profile and attachment rows are durable."""
    profile = await profile_repo.get_profile(session, profile_id)
    if profile is None:
        raise ProfileApprovalError(
            "approved profile missing after approval writes",
            code=ERROR_INVARIANT_VIOLATION,
        )
    if profile.attachment_id != expected_attachment_id:
        raise ProfileApprovalError(
            "profile attachment does not match approved "
            "attachment",
            code=ERROR_INVARIANT_VIOLATION,
        )

    if require_active_attachment:
        stmt = select(Attachment).where(
            Attachment.state == ATTACHMENT_STATE_ACTIVE
        )
        result = await session.execute(stmt)
        active_rows = list(result.scalars().all())
        if len(active_rows) != 1:
            raise ProfileApprovalError(
                f"expected exactly one active attachment, found {len(active_rows)}",
                code=ERROR_INVARIANT_VIOLATION,
            )
        if active_rows[0].id != expected_attachment_id:
            raise ProfileApprovalError(
                "active attachment id does not match profile pointer",
                code=ERROR_INVARIANT_VIOLATION,
            )

    draft = await profile_repo.get_draft_for_profile(session, profile_id)
    if draft is not None:
        raise ProfileApprovalError(
            "profile_drafts('current') still present after delete",
            code=ERROR_INVARIANT_VIOLATION,
        )


async def _run_sqlite_approval(
    session: AsyncSession,
    preflight: _Preflight,
    *,
    failpoint: str | None,
) -> tuple[datetime, str, str | None]:
    """Apply constraint-safe ordering inside one open session (no commit here)."""
    rows = await chunk_repo.list_for_attachment(
        session, preflight.active_attachment_id_for_profile
    )
    source_fragments = tuple(str(row.text) for row in rows)
    guarded_profile = guard_optional_identity_fields(
        preflight.draft.candidate_profile,
        source_fragments=source_fragments,
    )
    profile_json = guarded_profile.model_dump(mode="json")
    target_att_id = preflight.active_attachment_id_for_profile

    # 1. Promote the pending owner or replace the requested ready profile.
    # Both branches preserve the profile's durable conversations.
    profile_id = preflight.target_profile_id
    conversation_id: str | None = None
    if preflight.target_profile_state == PROFILE_STATE_PENDING:
        existing_profile = await profile_repo.get_profile(session, profile_id)
        if existing_profile is None or existing_profile.state != PROFILE_STATE_PENDING:
            raise ProfileApprovalError(
                "Target profile is not pending", code="PROFILE_NOT_READY"
            )
        if preflight.document_bundle is None:
            raise ProfileApprovalError(
                "Pending profile approval requires extracted CV data",
                code=ERROR_DOCUMENT_DRAFT_NOT_FOUND,
            )
        if preflight.new_attachment is None:
            raise ProfileApprovalError(
                "Pending profile attachment is missing",
                code=ERROR_ATTACHMENT_NOT_FOUND,
            )
        from app.services.profile_projection import project_display_name

        existing_profile.display_name = project_display_name(
            guarded_profile, preflight.new_attachment.original_name
        )
        existing_profile.profile_json = profile_json
        existing_profile.location = guarded_profile.location
        existing_profile.extraction_version = (
            preflight.document_bundle.extraction_version
        )
        existing_profile.source_hash = preflight.document_bundle.source_hash
        existing_profile.state = PROFILE_STATE_READY
        existing_profile.updated_at = utc_now()
        await session.flush()
        await workspace_repo.set_active_profile_id(session, profile_id)
        pending_conversation = await conversations_repo.most_recent_for_profile(
            session, profile_id=profile_id
        )
        if pending_conversation is None:
            raise ProfileApprovalError(
                "Pending profile conversation is missing",
                code="PROFILE_INCONSISTENT",
            )
        conversation_id = pending_conversation.id
    else:
        existing_profile = await profile_repo.get_profile(session, profile_id)
        if existing_profile is None or existing_profile.state != PROFILE_STATE_READY:
            raise ProfileApprovalError(
                "Target profile is not ready", code="PROFILE_NOT_READY"
            )
        existing_profile.profile_json = profile_json
        existing_profile.location = guarded_profile.location
        if preflight.document_bundle is not None:
            existing_profile.extraction_version = (
                preflight.document_bundle.extraction_version
            )
            existing_profile.source_hash = preflight.document_bundle.source_hash
        existing_profile.updated_at = utc_now()
        await session.flush()

    if failpoint == "after_profile_upsert":
        raise RuntimeError("failpoint:after_profile_upsert")

    # 2. Preferences only when changed.
    if preflight.target_profile_state == PROFILE_STATE_PENDING or (
        preflight.document_bundle is None and preflight.preferences_changed
    ):
        await profile_repo.upsert_profile_preferences(
            session,
            profile_id=profile_id,
            preferences_json=preflight.draft.job_preferences.model_dump(
                mode="json"
            ),
        )

    # 3–4. CV-backed: archive prior active when IDs differ; activate selected.
    # Profile already repointed so FK RESTRICT on candidate_profile is satisfied.
    if (
        preflight.target_profile_state == PROFILE_STATE_PENDING
        and preflight.new_attachment is not None
    ):
        if preflight.old_attachment_id is not None:
            await att_repo.mark_archived(session, preflight.old_attachment_id)
            if failpoint in (
                "after_old_attachment_archive",
                "after_old_attachment_delete",
            ):
                raise RuntimeError(f"failpoint:{failpoint}")
        try:
            # old already archived above when IDs differ.
            await activate_selected_attachment(
                session,
                attachment_id=target_att_id,
                old_attachment_id=None,
            )
        except ActivationError as exc:
            raise _activation_to_approval_error(exc) from exc

        # Promote document draft → approved cv_documents; clear document draft.
    # Promote a source-backed document revision without changing ready-profile
    # attachment selection/state.
    if preflight.document_bundle is not None:
        try:
            await promote_document_draft(session, preflight.document_bundle)
        except ActivationError as exc:
            raise _activation_to_approval_error(exc) from exc

    # 5. Delete profile draft.
    deleted = await profile_repo.delete_draft_for_profile(
        session,
        profile_id=profile_id,
        expected_revision=preflight.draft_updated_at,
    )
    if not deleted:
        raise ProfileApprovalError(
            "profile draft changed before delete",
            code=ERROR_INVARIANT_VIOLATION,
        )

    # 6. Final invariant, then caller commits.
    await _assert_final_invariant(
        session,
        profile_id=profile_id,
        expected_attachment_id=target_att_id,
        require_active_attachment=(
            preflight.target_profile_state == PROFILE_STATE_PENDING
        ),
    )

    if failpoint == "before_commit":
        raise RuntimeError("failpoint:before_commit")

    # Refresh updated_at after all writes.
    refreshed = await profile_repo.get_profile(session, profile_id)
    assert refreshed is not None
    return refreshed.updated_at, profile_id, conversation_id


async def commit_approved_draft(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: AttachmentStorage,
    normalizer: SkillNormalizer,
    expected_profile_id: str,
    expected_draft_updated_at: datetime | None = None,
    expected_operation_id: str | None | object = _UNSET_OPERATION,
    driver: AsyncGraphDriver | None = None,
    failpoint: str | None = None,
    sync_fn: Callable[..., Awaitable[None]] | None = None,
) -> ApprovalCommitResult:
    """Approve ``profile_drafts('current')`` with SQLite-first safety.

    Parameters
    ----------
    driver:
        Injected async Neo4j driver used by the default :func:`sync_candidate`
        path. Optional when *sync_fn* is provided.
    failpoint:
        Test-only hook name that raises inside the controlled path.
    sync_fn:
        Optional override for post-commit graph sync (defaults to Candidate
        plus active CV branch projection via :func:`sync_candidate` /
        :func:`sync_cv`).
    """
    # ---- Preflight (separate read session; file checks outside write txn) ----
    async with session_factory() as read_session:
        try:
            preflight = await _load_preflight(
                read_session,
                storage,
                check_files=True,
                expected_profile_id=expected_profile_id,
                expected_draft_updated_at=expected_draft_updated_at,
            )
        except ProfileApprovalError as exc:
            return ApprovalCommitResult(
                ok=False,
                code=exc.code,
                summary=exc.message,
                sqlite_committed=False,
                cleanup_ok=True,
                sync_ok=True,
                active_attachment_id=None,
                profile_updated_at=None,
                previous_attachment_id=None,
                preferences_updated=False,
                data={"sqlite_committed": False, "code": exc.code},
            )

    # Snapshot archive identity before the write transaction (file retained).
    old_attachment_id = preflight.old_attachment_id
    target_att_id = preflight.active_attachment_id_for_profile
    preferences_updated = preflight.target_profile_state == PROFILE_STATE_PENDING or (
        preflight.document_bundle is None and preflight.preferences_changed
    )

    # ---- SQLite transaction (DB only — no filesystem / Neo4j) ----
    try:
        async with session_scope(session_factory) as session:
            # Re-validate DB rows only inside the transaction (no storage I/O).
            live = await _load_preflight(
                session,
                storage=None,
                check_files=False,
                expected_profile_id=expected_profile_id,
                expected_draft_updated_at=expected_draft_updated_at,
            )
            if (
                live.draft_updated_at != preflight.draft_updated_at
                or live.draft_row_source_attachment_id
                != preflight.draft_row_source_attachment_id
                or live.active_attachment_id_for_profile != target_att_id
                ):
                raise ProfileApprovalError(
                    "Draft or attachment changed during approval preflight",
                    code=ERROR_APPROVAL_TRANSACTION_FAILED,
                )
            operation = await _validate_operation_linked_approval(
                session,
                preflight=live,
                expected_profile_id=expected_profile_id,
                expected_operation_id=expected_operation_id,
            )
            (
                profile_updated_at,
                approved_profile_id,
                created_conversation_id,
            ) = await _run_sqlite_approval(
                session, live, failpoint=failpoint
            )
            if operation is not None:
                deleted = await operation_repo.delete_operation(
                    session,
                    profile_id=expected_profile_id,
                    operation_id=operation.id,
                    expected_state="review_ready",
                )
                if not deleted:
                    raise ProfileApprovalError(
                        "Re-extraction operation changed during approval",
                        code="PROFILE_REEXTRACT_CONFLICT",
                    )
    except ProfileApprovalError as exc:
        return ApprovalCommitResult(
            ok=False,
            code=exc.code,
            summary=exc.message,
            sqlite_committed=False,
            cleanup_ok=True,
            sync_ok=True,
            active_attachment_id=None,
            profile_updated_at=None,
            previous_attachment_id=old_attachment_id,
            preferences_updated=False,
            data={"sqlite_committed": False, "code": exc.code},
        )
    except Exception as exc:
        logger.info(
            "profile approval transaction rolled back code=%s",
            ERROR_APPROVAL_TRANSACTION_FAILED,
        )
        return ApprovalCommitResult(
            ok=False,
            code=ERROR_APPROVAL_TRANSACTION_FAILED,
            summary="Approval transaction failed; prior active profile preserved",
            sqlite_committed=False,
            cleanup_ok=True,
            sync_ok=True,
            active_attachment_id=None,
            profile_updated_at=None,
            previous_attachment_id=old_attachment_id,
            preferences_updated=False,
            data={
                "sqlite_committed": False,
                "code": ERROR_APPROVAL_TRANSACTION_FAILED,
                "detail": type(exc).__name__,
            },
        )

    # ---- Post-commit: retained archive (no previous-file cleanup) ----
    # Archived metadata/PDF/chunks stay on disk for observability history.
    # Failpoint "cleanup" still forces cleanup_ok=False for regression tests
    # that assert SQLite commit independence from post-commit reporting.
    cleanup_ok = failpoint != "cleanup"

    # ---- Post-commit: Neo4j Candidate + active CV branch sync ----
    sync_ok = True
    sync_code: str | None = None
    sync_message: str | None = None
    rebuild = NEO4J_REBUILD_INSTRUCTION

    async def _default_sync() -> None:
        if driver is None:
            raise CandidateSyncError(
                "Neo4j driver not configured for Candidate sync"
            )
        async with session_factory() as committed_session:
            committed_profile = await profile_repo.get_profile(
                committed_session, approved_profile_id
            )
            if committed_profile is None:
                raise CandidateSyncError(
                    "Committed profile missing for Candidate sync"
                )
            try:
                profile_model = CandidateProfile.model_validate(
                    committed_profile.profile_json
                )
            except ValidationError as exc:
                raise CandidateSyncError(
                    "Committed profile invalid for Candidate sync"
                ) from exc
        await sync_candidate(
            driver,
            profile_id=approved_profile_id,
            profile=profile_model,
            source_updated_at=profile_updated_at,
            normalizer=normalizer,
        )
        cv_bundle = await _load_approved_cv_sync_inputs(
            session_factory, target_att_id
        )
        if cv_bundle is not None:
            document, original_name, extraction_version, doc_updated_at = (
                cv_bundle
            )
            await sync_cv(
                driver,
                profile_id=approved_profile_id,
                document=document,
                original_name=original_name,
                extraction_version=extraction_version,
                source_updated_at=doc_updated_at,
                is_active=True,
            )

    do_sync = sync_fn if sync_fn is not None else _default_sync
    try:
        if failpoint == "sync":
            raise CandidateSyncError("failpoint:sync")
        await do_sync()
    except (CandidateSyncError, CvSyncError) as exc:
        sync_ok = False
        sync_code = exc.code
        sync_message = exc.message
        rebuild = exc.rebuild_instruction
    except Exception:
        sync_ok = False
        sync_code = NEO4J_SYNC_FAILED
        sync_message = "Candidate/Skill/CV Neo4j synchronization failed"
        rebuild = NEO4J_REBUILD_INSTRUCTION

    data: dict[str, Any] = {
        "sqlite_committed": True,
        "draft_id": PROFILE_DRAFT_ID,
        "active_attachment_id": target_att_id,
        "profile_id": approved_profile_id,
        "conversation_id": created_conversation_id,
        "preferences_updated": preferences_updated,
        "previous_attachment_id": old_attachment_id,
        "previous_attachment_archived": old_attachment_id is not None,
        "cleanup_ok": cleanup_ok,
        "sync_ok": sync_ok,
        "profile_updated_at": profile_updated_at.isoformat(),
    }

    if not sync_ok:
        data["rebuild_instruction"] = rebuild
        return ApprovalCommitResult(
            ok=False,
            code=sync_code or NEO4J_SYNC_FAILED,
            summary=(
                "Profile committed to SQLite but Neo4j graph sync failed. "
                f"{rebuild}"
            ),
            sqlite_committed=True,
            cleanup_ok=cleanup_ok,
            sync_ok=False,
            active_attachment_id=target_att_id,
            profile_updated_at=profile_updated_at,
            previous_attachment_id=old_attachment_id,
            preferences_updated=preferences_updated,
            data={
                **data,
                "code": sync_code or NEO4J_SYNC_FAILED,
                "sync_message": sync_message,
            },
            profile_id=approved_profile_id,
            conversation_id=created_conversation_id,
        )

    summary = "Profile approved and synchronized"
    if old_attachment_id is not None:
        summary = (
            "Profile approved and synchronized; previous CV retained as archived"
        )

    return ApprovalCommitResult(
        ok=True,
        code=None,
        summary=summary,
        sqlite_committed=True,
        cleanup_ok=cleanup_ok,
        sync_ok=True,
        active_attachment_id=target_att_id,
        profile_updated_at=profile_updated_at,
        previous_attachment_id=old_attachment_id,
        preferences_updated=preferences_updated,
        data=data,
        profile_id=approved_profile_id,
        conversation_id=created_conversation_id,
    )
