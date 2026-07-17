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

Transaction failure rolls back to the prior active profile/CV. Neo4j failure
never rolls SQLite back; sync failure returns ``NEO4J_SYNC_FAILED`` plus
rebuild guidance while accurately reporting committed SQLite truth.

Archived → active is allowed only inside this approval path for a reprocessed
archived CV. No file moves at approval. No raw CV text in results/logs.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    Attachment,
)
from app.db.models.profiles import (
    CANDIDATE_PROFILE_ID,
    PROFILE_DRAFT_ID,
)
from app.graph.sync_candidate import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
    CandidateSyncError,
    sync_candidate,
)
from app.graph.sync_cv import CvSyncError, sync_cv
from app.repositories import attachments as att_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as profile_repo
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


@asynccontextmanager
async def _short_transaction(
    factory: async_sessionmaker[AsyncSession],
) -> Any:
    """Commit on success; roll back on any error. No external I/O inside."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _prefs_equal(a: JobPreferences, b: JobPreferences) -> bool:
    return a.model_dump(mode="json") == b.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class _Preflight:
    draft: ProfileDraftPayload
    draft_row_source_attachment_id: str | None
    new_attachment: Attachment | None
    new_storage_path: str | None
    old_attachment_id: str | None
    old_storage_path: str | None
    active_attachment_id_for_profile: str
    preferences_changed: bool
    current_prefs: JobPreferences
    document_bundle: DocumentDraftBundle | None


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
) -> _Preflight:
    """Validate draft and attachment prerequisites.

    When *check_files* is True (outer preflight only), confirm the source PDF
    exists on disk. Inside an open SQLite transaction, pass ``check_files=False``
    and ``storage=None`` so the write unit never spans filesystem I/O.
    """
    draft_row = await profile_repo.get_current_draft(session)
    if draft_row is None:
        raise ProfileApprovalError(
            "No current profile draft to approve",
            code=ERROR_DRAFT_NOT_FOUND,
        )

    try:
        draft = parse_profile_draft_payload(draft_row.draft_json)
    except ValidationError as exc:
        raise ProfileApprovalError(
            "Current draft failed full ProfileDraftPayload validation",
            code=ERROR_DRAFT_INVALID,
        ) from exc

    source_id = draft_row.source_attachment_id
    new_attachment: Attachment | None = None
    new_storage_path: str | None = None
    old_attachment_id: str | None = None
    old_storage_path: str | None = None
    document_bundle: DocumentDraftBundle | None = None

    active_profile = await profile_repo.get_active_profile(session)
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

        if active_profile is not None:
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

    prefs_row = await profile_repo.get_job_preferences(session)
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
        draft_row_source_attachment_id=source_id,
        new_attachment=new_attachment,
        new_storage_path=new_storage_path,
        old_attachment_id=old_attachment_id,
        old_storage_path=old_storage_path,
        active_attachment_id_for_profile=active_attachment_id_for_profile,
        preferences_changed=preferences_changed,
        current_prefs=current_prefs,
        document_bundle=document_bundle,
    )


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
    expected_attachment_id: str,
) -> None:
    """Require one active attachment referenced by candidate_profile('active')."""
    profile = await profile_repo.get_active_profile(session)
    if profile is None:
        raise ProfileApprovalError(
            "candidate_profile('active') missing after approval writes",
            code=ERROR_INVARIANT_VIOLATION,
        )
    if profile.id != CANDIDATE_PROFILE_ID:
        raise ProfileApprovalError(
            "candidate_profile singleton id invariant broken",
            code=ERROR_INVARIANT_VIOLATION,
        )
    if profile.active_attachment_id != expected_attachment_id:
        raise ProfileApprovalError(
            "candidate_profile.active_attachment_id does not match approved "
            "attachment",
            code=ERROR_INVARIANT_VIOLATION,
        )

    stmt = select(Attachment).where(Attachment.state == ATTACHMENT_STATE_ACTIVE)
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

    draft = await profile_repo.get_current_draft(session)
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
) -> datetime:
    """Apply constraint-safe ordering inside one open session (no commit here)."""
    profile_json = preflight.draft.candidate_profile.model_dump(mode="json")
    target_att_id = preflight.active_attachment_id_for_profile

    # 1. Upsert active profile (repoint first so old attachment can be archived).
    await profile_repo.upsert_active_profile(
        session,
        active_attachment_id=target_att_id,
        profile_json=profile_json,
    )
    if failpoint == "after_profile_upsert":
        raise RuntimeError("failpoint:after_profile_upsert")

    # 2. Preferences only when changed.
    if preflight.preferences_changed:
        await profile_repo.upsert_job_preferences(
            session,
            preferences_json=preflight.draft.job_preferences.model_dump(
                mode="json"
            ),
        )

    # 3–4. CV-backed: archive prior active when IDs differ; activate selected.
    # Profile already repointed so FK RESTRICT on candidate_profile is satisfied.
    if preflight.new_attachment is not None:
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
        if preflight.document_bundle is not None:
            try:
                await promote_document_draft(session, preflight.document_bundle)
            except ActivationError as exc:
                raise _activation_to_approval_error(exc) from exc

    # 5. Delete profile draft.
    await profile_repo.delete_current_draft(session)

    # 6. Final invariant, then caller commits.
    await _assert_final_invariant(session, expected_attachment_id=target_att_id)

    if failpoint == "before_commit":
        raise RuntimeError("failpoint:before_commit")

    # Refresh updated_at after all writes.
    refreshed = await profile_repo.get_active_profile(session)
    assert refreshed is not None
    return refreshed.updated_at


async def commit_approved_draft(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: AttachmentStorage,
    normalizer: SkillNormalizer,
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
                read_session, storage, check_files=True
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
    preferences_updated = preflight.preferences_changed
    profile_model: CandidateProfile = preflight.draft.candidate_profile

    # ---- SQLite transaction (DB only — no filesystem / Neo4j) ----
    try:
        async with _short_transaction(session_factory) as session:
            # Re-validate DB rows only inside the transaction (no storage I/O).
            live = await _load_preflight(
                session, storage=None, check_files=False
            )
            if (
                live.draft_row_source_attachment_id
                != preflight.draft_row_source_attachment_id
                or live.active_attachment_id_for_profile != target_att_id
            ):
                raise ProfileApprovalError(
                    "Draft or attachment changed during approval preflight",
                    code=ERROR_APPROVAL_TRANSACTION_FAILED,
                )
            profile_updated_at = await _run_sqlite_approval(
                session, live, failpoint=failpoint
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
        await sync_candidate(
            driver,
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
    )
