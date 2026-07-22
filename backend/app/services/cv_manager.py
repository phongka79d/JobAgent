"""Retryable complete non-active CV deletion coordinator (Plan 9 / Master §6.4).

Owns eligibility, first-mark + chat redaction + draft cleanup, external
checkpoint/file/exact-graph steps, and final run/tool/attachment removal.
Preserves active Candidate/profile, Jobs, Skills, seed edges, and unrelated
rows/files. Returns success only when every owned resource is gone.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpoint import (
    delete_run_checkpoints,
    open_checkpointer,
)
from app.core.settings import get_settings
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_DELETING,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.db.session import get_session_factory, session_scope
from app.graph.delete_cv import CvGraphDeleteError, delete_cv_branch
from app.graph.sync_shared import AsyncGraphDriver
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import profiles as profile_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.cv_manager import (
    CV_DELETE_RETRY_SUMMARY,
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN,
    ERROR_CV_ATTACHMENT_NOT_FOUND,
    ERROR_CV_DELETE_CHECKPOINT_FAILED,
    ERROR_CV_DELETE_FILE_FAILED,
    ERROR_CV_DELETE_FINALIZE_FAILED,
    ERROR_CV_DELETE_GRAPH_FAILED,
)
from app.services.cv_deletion_ownership import (
    message_owns_attachment,
    tool_record_owns_attachment,
)
from app.storage.attachments import AttachmentStorage, PathEscapeError

logger = logging.getLogger(__name__)

_ELIGIBLE_STATES: frozenset[str] = frozenset(
    {
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_FAILED,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_DELETING,
    }
)

Failpoint = Literal[
    "after_mark",
    "checkpoint",
    "file",
    "graph",
    "finalize",
]

CheckpointerOpen = Callable[..., Any]
GraphDeleteFn = Callable[[AsyncGraphDriver, str], Awaitable[None]]


class CvDeleteError(Exception):
    """Stable-coded CV deletion failure for HTTP mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CvDeleteResult:
    """Successful complete deletion (row and owned resources absent)."""

    attachment_id: str


async def _resolve_owned_message_ids(
    session: AsyncSession,
    attachment_id: str,
) -> list[str]:
    """FK-owned messages plus historical structured-payload owners."""
    owned: list[str] = []
    seen: set[str] = set()
    for row in await messages_repo.list_by_source_attachment_id(
        session, attachment_id
    ):
        if row.id not in seen:
            seen.add(row.id)
            owned.append(row.id)
    for row in await messages_repo.list_with_structured_payload(session):
        if row.id in seen:
            continue
        if message_owns_attachment(
            source_attachment_id=row.source_attachment_id,
            structured_payload=row.structured_payload
            if isinstance(row.structured_payload, dict)
            else None,
            attachment_id=attachment_id,
        ):
            seen.add(row.id)
            owned.append(row.id)
    return owned


async def _resolve_cv_run_ids(
    session: AsyncSession,
    attachment_id: str,
) -> list[str]:
    """CV-scoped run IDs for checkpoint and final cascade deletion."""
    runs = await runs_repo.list_by_source_attachment_id(session, attachment_id)
    return [r.id for r in runs]


async def _resolve_owned_tool_ids(
    session: AsyncSession,
    attachment_id: str,
    *,
    cv_run_ids: set[str],
) -> list[str]:
    """Directly CV-owned tools, including those on unrelated runs.

    Tools on CV-scoped runs are deleted via run cascade; only tools that need
    an explicit delete (FK or historical structured ownership on other runs)
    are returned.
    """
    owned: list[str] = []
    seen: set[str] = set()
    for row in await tool_repo.list_by_source_attachment_id(
        session, attachment_id
    ):
        if row.id in seen:
            continue
        if row.run_id in cv_run_ids:
            # Cascade when the parent CV-scoped run is deleted.
            continue
        seen.add(row.id)
        owned.append(row.id)
    for row in await tool_repo.list_with_argument_or_result_json(session):
        if row.id in seen or row.run_id in cv_run_ids:
            continue
        if tool_record_owns_attachment(
            source_attachment_id=row.source_attachment_id,
            arguments_summary_json=row.arguments_summary_json
            if isinstance(row.arguments_summary_json, dict)
            else None,
            result_json=row.result_json
            if isinstance(row.result_json, dict)
            else None,
            attachment_id=attachment_id,
        ):
            # Only delete when not already cascading with a CV-scoped run.
            if row.run_id in cv_run_ids:
                continue
            seen.add(row.id)
            owned.append(row.id)
    return owned


async def _phase_mark_and_redact(
    session: AsyncSession,
    attachment_id: str,
) -> tuple[Attachment, list[str]]:
    """Mark deleting, redact owned messages, clear matching draft.

    Returns the attachment row and CV-scoped run IDs for checkpoint cleanup.
    """
    row = await att_repo.get_by_id(session, attachment_id)
    if row is None:
        raise CvDeleteError(
            ERROR_CV_ATTACHMENT_NOT_FOUND,
            f"attachment {attachment_id!r} not found",
        )
    if row.state == ATTACHMENT_STATE_ACTIVE:
        raise CvDeleteError(
            ERROR_CV_ACTIVE_DELETE_FORBIDDEN,
            "active CV cannot be deleted; archive via replacement first",
        )
    if row.state not in _ELIGIBLE_STATES:
        raise CvDeleteError(
            ERROR_CV_ATTACHMENT_NOT_FOUND,
            f"attachment {attachment_id!r} is not eligible for deletion",
        )

    if row.state != ATTACHMENT_STATE_DELETING:
        row = await att_repo.mark_deleting(session, attachment_id)

    for message_id in await _resolve_owned_message_ids(session, attachment_id):
        await messages_repo.redact_for_cv_deletion(session, message_id)

    draft = await profile_repo.get_current_draft(session)
    if (
        draft is not None
        and isinstance(draft.source_attachment_id, str)
        and draft.source_attachment_id.strip() == attachment_id
    ):
        await profile_repo.delete_current_draft(session)

    run_ids = await _resolve_cv_run_ids(session, attachment_id)
    return row, run_ids


async def _phase_checkpoints(
    *,
    run_ids: list[str],
    sqlite_path: str | Path,
    checkpointer_open: CheckpointerOpen,
) -> None:
    if not run_ids:
        return
    try:
        async with checkpointer_open(sqlite_path) as saver:
            await delete_run_checkpoints(saver, run_ids)
    except Exception as exc:
        raise CvDeleteError(
            ERROR_CV_DELETE_CHECKPOINT_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        ) from exc


def _phase_file(storage: AttachmentStorage, storage_path: str) -> None:
    try:
        ok = storage.delete(storage_path)
    except PathEscapeError as exc:
        raise CvDeleteError(
            ERROR_CV_DELETE_FILE_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        ) from exc
    except Exception as exc:
        raise CvDeleteError(
            ERROR_CV_DELETE_FILE_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        ) from exc
    if not ok:
        raise CvDeleteError(
            ERROR_CV_DELETE_FILE_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        )


async def _phase_graph(
    *,
    driver: AsyncGraphDriver | None,
    attachment_id: str,
    graph_delete_fn: GraphDeleteFn,
) -> None:
    if driver is None:
        raise CvDeleteError(
            ERROR_CV_DELETE_GRAPH_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        )
    try:
        await graph_delete_fn(driver, attachment_id)
    except CvGraphDeleteError as exc:
        raise CvDeleteError(exc.code, CV_DELETE_RETRY_SUMMARY) from exc
    except CvDeleteError:
        raise
    except Exception as exc:
        raise CvDeleteError(
            ERROR_CV_DELETE_GRAPH_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        ) from exc


async def _phase_finalize(
    session: AsyncSession,
    attachment_id: str,
) -> None:
    run_ids = await _resolve_cv_run_ids(session, attachment_id)
    cv_run_set = set(run_ids)
    tool_ids = await _resolve_owned_tool_ids(
        session, attachment_id, cv_run_ids=cv_run_set
    )
    for tool_id in tool_ids:
        await tool_repo.delete_execution(session, tool_id)
    for run_id in run_ids:
        await runs_repo.delete_run(session, run_id)
    row = await att_repo.get_by_id(session, attachment_id)
    if row is None:
        return
    await att_repo.delete(session, attachment_id)


async def delete_cv(
    attachment_id: str,
    *,
    storage: AttachmentStorage,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    driver: AsyncGraphDriver | None = None,
    sqlite_path: str | Path | None = None,
    checkpointer_open: CheckpointerOpen | None = None,
    graph_delete_fn: GraphDeleteFn | None = None,
    failpoint: Failpoint | None = None,
) -> CvDeleteResult:
    """Delete one eligible non-active CV completely (idempotent / resumable).

    Raises :class:`CvDeleteError` with a stable code. On external failure the
    attachment remains ``deleting`` and the same DELETE may be retried. Returns
    only after the attachment row and owned resources are gone.
    """
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise CvDeleteError(
            ERROR_CV_ATTACHMENT_NOT_FOUND,
            "attachment_id must be a non-empty UUID",
        )
    aid = attachment_id.strip()
    factory = session_factory or get_session_factory()
    open_cp = checkpointer_open or open_checkpointer
    graph_fn = graph_delete_fn or delete_cv_branch
    path_for_checkpoints: str | Path = (
        sqlite_path
        if sqlite_path is not None
        else get_settings().SQLITE_PATH
    )

    # Pre-guard active before any mutation (separate read so active rows never
    # enter the mark transaction).
    async with factory() as probe:
        existing = await att_repo.get_by_id(probe, aid)
        if existing is None:
            raise CvDeleteError(
                ERROR_CV_ATTACHMENT_NOT_FOUND,
                f"attachment {aid!r} not found",
            )
        if existing.state == ATTACHMENT_STATE_ACTIVE:
            raise CvDeleteError(
                ERROR_CV_ACTIVE_DELETE_FORBIDDEN,
                "active CV cannot be deleted; archive via replacement first",
            )
        if existing.state not in _ELIGIBLE_STATES:
            raise CvDeleteError(
                ERROR_CV_ATTACHMENT_NOT_FOUND,
                f"attachment {aid!r} is not eligible for deletion",
            )

    async with session_scope(factory) as session:
        _row, run_ids = await _phase_mark_and_redact(session, aid)
        storage_path = _row.storage_path
        if failpoint == "after_mark":
            raise RuntimeError("test failpoint after_mark")

    if failpoint == "checkpoint":
        raise CvDeleteError(
            ERROR_CV_DELETE_CHECKPOINT_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        )
    await _phase_checkpoints(
        run_ids=run_ids,
        sqlite_path=path_for_checkpoints,
        checkpointer_open=open_cp,
    )

    if failpoint == "file":
        raise CvDeleteError(
            ERROR_CV_DELETE_FILE_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        )
    _phase_file(storage, storage_path)

    if failpoint == "graph":
        raise CvDeleteError(
            ERROR_CV_DELETE_GRAPH_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        )
    await _phase_graph(
        driver=driver,
        attachment_id=aid,
        graph_delete_fn=graph_fn,
    )

    try:
        async with session_scope(factory) as session:
            if failpoint == "finalize":
                raise RuntimeError("test failpoint finalize")
            await _phase_finalize(session, aid)
    except CvDeleteError:
        raise
    except Exception as exc:
        logger.exception("CV delete finalize failed attachment=%s", aid)
        raise CvDeleteError(
            ERROR_CV_DELETE_FINALIZE_FAILED,
            CV_DELETE_RETRY_SUMMARY,
        ) from exc

    # Confirm absence (never report success while the row remains).
    async with factory() as session:
        gone = await att_repo.get_by_id(session, aid)
        if gone is not None:
            raise CvDeleteError(
                ERROR_CV_DELETE_FINALIZE_FAILED,
                CV_DELETE_RETRY_SUMMARY,
            )

    return CvDeleteResult(attachment_id=aid)


__all__ = [
    "CvDeleteError",
    "CvDeleteResult",
    "Failpoint",
    "delete_cv",
]
