"""Integration: same-run profile approval, correction, and resume idempotency."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.db.enums import AgentRunState
from app.db.models.conversation import AgentRun, ToolExecution
from app.db.models.outbox import GraphSyncOutbox
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.attachments import AttachmentRepository, StagedAttachmentInput
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.attachment_storage import (
    FilesystemAttachmentStorage,
    iter_byte_chunks,
)
from app.services.chat_service import ChatService
from app.services.profile_service import ProfileCommitService
from app.services.shopaikey_chat import DecisionResult
from app.tools.profile_commit import (
    ProfileCommitToolService,
    create_profile_commit_tool,
)
from app.tools.profile_draft import (
    ProfileDraftToolService,
    create_profile_draft_tools,
)
from sqlalchemy import func, select
from tests.fakes.agent_tools import ScriptedDecision, decision_text, tool_call
from tests.tools.profile_tool_helpers import preferences, profile

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


@contextmanager
def _sqlite_path_env(db_path: Path) -> Iterator[None]:
    previous = os.environ.get("SQLITE_PATH")
    os.environ["SQLITE_PATH"] = str(db_path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SQLITE_PATH", None)
        else:
            os.environ["SQLITE_PATH"] = previous


@asynccontextmanager
async def migrated_db(
    tmp_path: Path,
) -> AsyncIterator[tuple[Path, DatabaseSessionManager, FilesystemAttachmentStorage]]:
    db_path = tmp_path / "profile-approval.db"
    files_dir = tmp_path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    with _sqlite_path_env(db_path):
        command.upgrade(_alembic_config(), "head")
    manager = create_session_manager(db_path)
    storage = FilesystemAttachmentStorage(files_dir)
    try:
        yield db_path, manager, storage
    finally:
        await manager.dispose()


class _FakeCv:
    def __init__(self, database: DatabaseSessionManager, attachment_id: UUID) -> None:
        self.database = database
        self.attachment_id = attachment_id

    async def propose_profile_from_cv(self, attachment_id: UUID) -> Any:
        async with self.database.session_scope() as session:
            proposed = profile("Integration draft")
            return await ProfileDraftRepository(session).create(
                ProfileDraftDocument(
                    profile=proposed,
                    approval_summary=build_approval_summary(proposed),
                ),
                source_attachment_id=self.attachment_id,
            )


async def _seed_attachment(
    database: DatabaseSessionManager,
    storage: FilesystemAttachmentStorage,
) -> UUID:
    attachment_id = uuid4()
    staged = await storage.stage(attachment_id, iter_byte_chunks(b"%PDF-1.4 integ"))
    async with database.session_scope() as session:
        await AttachmentRepository(session).add_staged(
            StagedAttachmentInput(
                id=attachment_id,
                file_hash=attachment_id.hex,
                original_name="cv.pdf",
                mime_type="application/pdf",
                size_bytes=14,
                storage_path=staged.storage_path,
                page_count=1,
            )
        )
    return attachment_id


def _tools(
    database: DatabaseSessionManager,
    storage: FilesystemAttachmentStorage,
    attachment_id: UUID,
) -> list[Any]:
    draft = create_profile_draft_tools(
        ProfileDraftToolService(database, _FakeCv(database, attachment_id))
    )
    commit = create_profile_commit_tool(
        ProfileCommitToolService(ProfileCommitService(database, storage))
    )
    return [*draft, commit]


@pytest.mark.asyncio
async def test_integration_approve_commit_and_duplicate_resume_key(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, database, storage):
        attachment_id = await _seed_attachment(database, storage)
        tools = _tools(database, storage, attachment_id)
        decision = ScriptedDecision(
            [
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "propose_profile_from_cv",
                            arguments={"attachment_id": str(attachment_id)},
                            tool_call_id="c_p",
                        ),
                    ),
                    response_model="fake",
                ),
                decision_text("Saved profile after approval"),
            ]
        )
        service = ChatService(
            database,
            sqlite_path=db_path,
            decision=decision,
            tools=tools,
        )
        first = await service.start_turn(
            user_text="Create a candidate profile draft from the attached CV.",
            turn_idempotency_key="turn-profile-1",
            attachment_ids=[str(attachment_id)],
        )
        assert first.outcome == "interrupted"
        assert first.pending_approval is not None
        assert first.pending_approval.get("draft_id")
        # Display summary present; internal draft may be on interrupt payload.
        assert first.pending_approval.get("summary")
        run_id = first.run_id

        async with database.session_scope() as session:
            tools_before = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ToolExecution)
                    )
                ).scalar_one()
            )
            outbox_before = int(
                (
                    await session.execute(
                        select(func.count()).select_from(GraphSyncOutbox)
                    )
                ).scalar_one()
            )

        second = await service.resume_run(
            run_id=run_id,
            resume_idempotency_key="resume-approve-1",
            resume_value=True,
        )
        assert second.outcome == "completed"
        assert second.final_text == "Saved profile after approval"

        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is not None
            assert await ProfileDraftRepository(session).get_pending() is None
            tools_after = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ToolExecution)
                    )
                ).scalar_one()
            )
            outbox_after = int(
                (
                    await session.execute(
                        select(func.count()).select_from(GraphSyncOutbox)
                    )
                ).scalar_one()
            )
            assert tools_after >= tools_before
            # One Candidate sync enqueue from commit (may coalesce to one row).
            assert outbox_after >= outbox_before

        # Duplicate resume key: durable outcome, no second commit/tool/outbox.
        third = await service.resume_run(
            run_id=run_id,
            resume_idempotency_key="resume-approve-1",
            resume_value=True,
        )
        assert third.replayed is True
        assert third.outcome in {"replay", "completed"}
        async with database.session_scope() as session:
            tools_dup = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ToolExecution)
                    )
                ).scalar_one()
            )
            outbox_dup = int(
                (
                    await session.execute(
                        select(func.count()).select_from(GraphSyncOutbox)
                    )
                ).scalar_one()
            )
            assert tools_dup == tools_after
            assert outbox_dup == outbox_after
            run = await session.get(AgentRun, run_id)
            assert run is not None
            assert run.state == AgentRunState.COMPLETED.value


@pytest.mark.asyncio
async def test_integration_correction_loop_same_draft_then_approve(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, database, storage):
        attachment_id = await _seed_attachment(database, storage)
        tools = _tools(database, storage, attachment_id)
        decision = ScriptedDecision(
            [
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "propose_profile_from_cv",
                            arguments={"attachment_id": str(attachment_id)},
                            tool_call_id="c_p",
                        ),
                    ),
                    response_model="fake",
                ),
            ]
        )
        service = ChatService(
            database,
            sqlite_path=db_path,
            decision=decision,
            tools=tools,
        )
        first = await service.start_turn(
            user_text="Create profile",
            turn_idempotency_key="turn-correct-1",
            attachment_ids=[str(attachment_id)],
        )
        assert first.outcome == "interrupted"
        draft_id = str(first.pending_approval["draft_id"])  # type: ignore[index]

        corrected = profile("Corrected integration summary")
        decision.results.append(
            DecisionResult(
                content="",
                tool_calls=(
                    tool_call(
                        "propose_profile_update",
                        arguments={
                            "draft_id": draft_id,
                            "profile": corrected.model_dump(mode="json"),
                            "preferences": preferences("Lead").model_dump(
                                mode="json"
                            ),
                        },
                        tool_call_id="c_u",
                    ),
                ),
                response_model="fake",
            )
        )
        decision.results.append(decision_text("Committed after correction"))

        corrected_resume = await service.resume_run(
            run_id=first.run_id,
            resume_idempotency_key="resume-correct-1",
            resume_value={
                "action": "correct",
                "text": "Update summary to Corrected integration summary",
            },
        )
        assert corrected_resume.outcome == "interrupted"
        assert corrected_resume.pending_approval is not None
        assert corrected_resume.pending_approval.get("draft_id") == draft_id
        # Fresh approval summary after correction.
        assert corrected_resume.pending_approval.get("summary")

        async with database.session_scope() as session:
            # Still no approved write before final approve.
            assert await ProfileRepository(session).get() is None
            draft = await ProfileDraftRepository(session).get(UUID(draft_id))
            assert draft is not None
            assert draft.document.profile.summary == "Corrected integration summary"

        approved = await service.resume_run(
            run_id=first.run_id,
            resume_idempotency_key="resume-approve-after-correct",
            resume_value=True,
        )
        assert approved.outcome == "completed"
        async with database.session_scope() as session:
            row = await ProfileRepository(session).get()
            assert row is not None
            assert row.profile.summary == "Corrected integration summary"
