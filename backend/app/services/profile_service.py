"""Atomic approved-profile replacement with filesystem compensation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.db.enums import AttachmentState, ProfileDraftState
from app.db.session import DatabaseSessionManager
from app.repositories.attachments import (
    AttachmentRepository,
    require_canonical_service_path,
)
from app.repositories.preferences import PreferencesRepository
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.services.attachment_storage import AttachmentStorage


class ProfileCommitError(Exception):
    """A profile commit failed without exposing persistence internals."""

    def __init__(self, code: str = "PROFILE_COMMIT_FAILED") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProfileCommitResult:
    """Approved attachment identity plus post-commit cleanup state."""

    active_attachment_id: UUID
    cleanup_pending: bool
    cleanup_attachment_id: UUID | None = None


class ProfileCommitService:
    """Own the filesystem/SQLite unit of work for one pending profile draft."""

    def __init__(
        self,
        database: DatabaseSessionManager,
        storage: AttachmentStorage,
    ) -> None:
        self._database = database
        self._storage = storage

    async def commit_draft(self, draft_id: UUID) -> ProfileCommitResult:
        promoted_active_path: str | None = None
        source_id: UUID | None = None
        old_attachment: tuple[UUID, str] | None = None
        try:
            async with self._database.session_scope() as session:
                drafts = ProfileDraftRepository(session)
                draft = await drafts.get(draft_id)
                if draft is None or draft.state != ProfileDraftState.PENDING.value:
                    raise ProfileCommitError("PROFILE_DRAFT_NOT_PENDING")

                attachments = AttachmentRepository(session)
                source = await attachments.get_by_id(draft.source_attachment_id)
                if source is None:
                    raise ProfileCommitError("PROFILE_SOURCE_NOT_FOUND")
                source_id = source.id
                source_state = str(source.state)
                if source_state not in {
                    AttachmentState.STAGED.value,
                    AttachmentState.ACTIVE.value,
                }:
                    raise ProfileCommitError("PROFILE_SOURCE_INVALID")
                require_canonical_service_path(
                    str(source.storage_path),
                    source.id,
                    expected_area=source_state,
                )

                profiles = ProfileRepository(session)
                previous = await profiles.get()
                if (
                    previous is not None
                    and previous.active_attachment_id is not None
                    and previous.active_attachment_id != source.id
                ):
                    old = await attachments.get_by_id(previous.active_attachment_id)
                    if old is not None:
                        require_canonical_service_path(
                            str(old.storage_path),
                            old.id,
                            expected_area=AttachmentState.ACTIVE.value,
                        )
                        old_attachment = (old.id, str(old.storage_path))

                active_path = str(source.storage_path)
                if source_state == AttachmentState.STAGED.value:
                    promoted_active_path = await self._storage.promote(active_path)
                    active_path = promoted_active_path
                    await attachments.mark_active(source.id, storage_path=active_path)

                await profiles.replace(
                    draft.document.profile,
                    active_attachment_id=source.id,
                    retain_embedding_model=True,
                )
                if draft.document.replaces_preferences():
                    assert draft.document.preferences is not None
                    await PreferencesRepository(session).replace(
                        draft.document.preferences
                    )
                if not await drafts.delete(draft.id):
                    raise ProfileCommitError("PROFILE_DRAFT_NOT_PENDING")
        except BaseException as exc:
            if promoted_active_path is not None and source_id is not None:
                await self._compensate_promotion(source_id, promoted_active_path)
            if not isinstance(exc, Exception):
                raise
            if isinstance(exc, ProfileCommitError):
                raise
            raise ProfileCommitError() from exc

        assert source_id is not None
        cleanup_pending = False
        cleanup_id: UUID | None = None
        if old_attachment is not None:
            cleanup_id, old_path = old_attachment
            cleanup_pending = not await self._cleanup_attachment(cleanup_id, old_path)
        return ProfileCommitResult(
            active_attachment_id=source_id,
            cleanup_pending=cleanup_pending,
            cleanup_attachment_id=cleanup_id if cleanup_pending else None,
        )

    async def retry_cleanup(self, *, limit: int = 20) -> int:
        """Remove one bounded slice of durable unreferenced attachment rows."""
        async with self._database.session_scope() as session:
            rows = await AttachmentRepository(session).list_unreferenced_active(
                limit=limit
            )
            cleanup = [(row.id, str(row.storage_path)) for row in rows]
        removed = 0
        for attachment_id, storage_path in cleanup:
            if await self._cleanup_attachment(attachment_id, storage_path):
                removed += 1
        return removed

    async def _compensate_promotion(
        self, attachment_id: UUID, active_path: str
    ) -> None:
        try:
            await self._storage.restore(active_path)
            return
        except Exception as restore_error:
            try:
                async with self._database.session_scope() as session:
                    await AttachmentRepository(session).mark_active(
                        attachment_id,
                        storage_path=active_path,
                    )
            except Exception as recovery_error:
                raise ProfileCommitError("PROFILE_COMPENSATION_FAILED") from recovery_error
            raise ProfileCommitError("PROFILE_COMMIT_FAILED") from restore_error

    async def _cleanup_attachment(
        self, attachment_id: UUID, storage_path: str
    ) -> bool:
        try:
            async with self._database.session_scope() as session:
                repository = AttachmentRepository(session)
                candidate = await repository.get_unreferenced_active(attachment_id)
                if candidate is None:
                    return True
                if str(candidate.storage_path) != storage_path:
                    return False
                await repository.delete(attachment_id)
                await self._storage.delete(storage_path)
        except Exception:
            return False
        return True


__all__ = [
    "ProfileCommitError",
    "ProfileCommitResult",
    "ProfileCommitService",
]
