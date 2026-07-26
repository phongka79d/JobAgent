"""Retry-safe mark, checkpoint/artifact cleanup, and finalize deletion."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpoint import delete_run_checkpoints, open_checkpointer
from app.db.models.chat import AGENT_RUN_STATE_INTERRUPTED, AGENT_RUN_STATE_RUNNING
from app.db.session import session_scope
from app.repositories import agent_runs as runs_repo
from app.repositories import cv_tailoring as tailoring_repo
from app.schemas.cv_tailoring import TailoringDeleteResponse
from app.services.cv_tailoring import (
    TAILORING_SESSION_NOT_FOUND,
    TailoringError,
)
from app.storage.cv_tailoring import TailoringArtifactStorage

TAILORING_DELETE_FAILED = "TAILORING_DELETE_FAILED"


async def delete_tailoring_session(
    *,
    session_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    sqlite_path: str | Path,
    storage: TailoringArtifactStorage,
) -> TailoringDeleteResponse:
    try:
        async with session_scope(session_factory) as session:
            owner = await tailoring_repo.get_session(session, session_id)
            if owner is None:
                raise TailoringError(
                    TAILORING_SESSION_NOT_FOUND,
                    "Tailoring session was not found",
                )
            run_ids = await runs_repo.list_run_ids_for_tailoring_session(
                session, owner.id
            )
            for run_id in run_ids:
                run = await runs_repo.get_run(session, run_id)
                if run is not None and run.state in {
                    AGENT_RUN_STATE_RUNNING,
                    AGENT_RUN_STATE_INTERRUPTED,
                }:
                    raise TailoringError(
                        TAILORING_DELETE_FAILED,
                        "Tailoring session still has active work",
                    )
            profile_id = owner.profile_id
            await tailoring_repo.mark_session_deleting(session, owner.id)

        async with open_checkpointer(sqlite_path) as saver:
            await delete_run_checkpoints(saver, run_ids)
        if not storage.delete_session(
            profile_id=profile_id, session_id=session_id
        ):
            raise TailoringError(
                TAILORING_DELETE_FAILED,
                "Tailoring session deletion failed",
            )

        async with session_scope(session_factory) as session:
            await tailoring_repo.delete_session(session, session_id)
        return TailoringDeleteResponse(deleted_session_id=session_id)
    except TailoringError:
        raise
    except Exception as exc:
        raise TailoringError(
            TAILORING_DELETE_FAILED,
            "Tailoring session deletion failed",
        ) from exc


__all__ = ["TAILORING_DELETE_FAILED", "delete_tailoring_session"]
