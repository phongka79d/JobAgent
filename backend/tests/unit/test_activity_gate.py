from pathlib import Path

import pytest
from app.core.time import utc_now
from app.db.models.attachments import Attachment
from app.db.models.chat import AgentRun, ChatMessage, Conversation
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import cv_tailoring as tailoring_repo
from app.repositories import observability as observability_repo
from app.repositories.agent_runs import AgentRunRepositoryError
from app.services.activity_gate import (
    ActivityBlockedError,
    assert_conversation_idle,
    assert_profile_idle,
    assert_tailoring_start_allowed,
    assert_workspace_idle,
)
from sqlalchemy.exc import IntegrityError

from tests.support.db_migration import run_async, session_factory


def test_activity_blocked_error_exposes_only_stable_code_and_summary() -> None:
    error = ActivityBlockedError("PROFILE_SWITCH_BLOCKED", "finish active run")
    assert error.code == "PROFILE_SWITCH_BLOCKED"
    assert error.summary == "finish active run"
    assert str(error) == "finish active run"


def test_tailoring_start_gate_is_part_of_the_public_service_contract() -> None:
    assert callable(assert_tailoring_start_allowed)


@pytest.mark.parametrize(
    ("run_kind", "user_message_id", "tailoring_session_id", "parent_run_id"),
    [
        ("chat", None, None, None),
        ("chat", "message", "session", None),
        ("chat", "message", None, "parent"),
        ("cv_tailoring", "message", "session", None),
        ("cv_tailoring", None, None, None),
        ("unknown", "message", None, None),
    ],
)
def test_agent_run_owner_xor_rejects_invalid_shapes(
    run_kind: str,
    user_message_id: str | None,
    tailoring_session_id: str | None,
    parent_run_id: str | None,
) -> None:
    with pytest.raises(AgentRunRepositoryError):
        runs_repo.validate_run_owner_xor(
            run_kind=run_kind,
            user_message_id=user_message_id,
            tailoring_session_id=tailoring_session_id,
            parent_run_id=parent_run_id,
        )


def test_parented_tailoring_allows_only_its_named_main_run(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment = Attachment(
                    file_hash="c" * 64,
                    original_name="synthetic.pdf",
                    mime_type="application/pdf",
                    size_bytes=10,
                    page_count=1,
                    storage_path="synthetic.pdf",
                    state="archived",
                )
                session.add(attachment)
                await session.flush()
                profile = Profile(
                    attachment_id=attachment.id,
                    display_name="Synthetic Candidate",
                    profile_json={"summary": "Synthetic"},
                    location=None,
                    extraction_version="cv-document-v1",
                    source_hash="source-a",
                    state="ready",
                )
                session.add(profile)
                await session.flush()
                conversation = Conversation(profile_id=profile.id, title="Synthetic")
                session.add(conversation)
                await session.flush()
                message = ChatMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content="Create a tailored CV",
                    structured_payload=None,
                )
                session.add(message)
                await session.flush()
                parent = await runs_repo.create_run(
                    session, user_message_id=message.id
                )
                other_attachment = Attachment(
                    file_hash="e" * 64,
                    original_name="other.pdf",
                    mime_type="application/pdf",
                    size_bytes=10,
                    page_count=1,
                    storage_path="other.pdf",
                    state="archived",
                )
                session.add(other_attachment)
                await session.flush()
                other_profile = Profile(
                    attachment_id=other_attachment.id,
                    display_name="Other Candidate",
                    profile_json={"summary": "Other"},
                    location=None,
                    extraction_version="cv-document-v1",
                    source_hash="source-other",
                    state="ready",
                )
                session.add(other_profile)
                await session.flush()
                other_conversation = Conversation(
                    profile_id=other_profile.id, title="Other"
                )
                session.add(other_conversation)
                await session.flush()
                other_message = ChatMessage(
                    conversation_id=other_conversation.id,
                    role="user",
                    content="Other work",
                    structured_payload=None,
                )
                session.add(other_message)
                await session.flush()
                other_run = await runs_repo.create_run(
                    session, user_message_id=other_message.id
                )
                await runs_repo.complete_run(session, other_run.id)
                await session.commit()
                profile_id = profile.id
                attachment_id = attachment.id
                profile_updated_at = profile.updated_at
                parent_id = parent.id
                other_run_id = other_run.id

            async with factory() as session:
                await assert_tailoring_start_allowed(
                    session,
                    profile_id=profile_id,
                    parent_run_id=parent_id,
                )
                other_run = await runs_repo.get_run(session, other_run_id)
                assert other_run is not None
                other_run.state = "running"
                other_run.completed_at = None
                await session.flush()
                with pytest.raises(ActivityBlockedError):
                    await assert_tailoring_start_allowed(
                        session,
                        profile_id=profile_id,
                        parent_run_id=parent_id,
                    )
                other_run.state = "completed"
                other_run.completed_at = utc_now()
                await session.flush()
                tailoring = await tailoring_repo.create_session(
                    session,
                    profile_id=profile_id,
                    source_attachment_id=attachment_id,
                    source_hash="source-a",
                    profile_updated_at=profile_updated_at,
                    job_id=None,
                    job_updated_at=None,
                    job_label_json=None,
                    instruction="Synthetic instruction",
                    template_version="latex-cv-v1",
                )
                child = await runs_repo.create_tailoring_run(
                    session,
                    tailoring_session_id=tailoring.id,
                    parent_run_id=parent_id,
                )
                assert child.user_message_id is None
                assert await runs_repo.resolve_run_owner(session, child.id) is None
                assert await runs_repo.list_run_ids_for_tailoring_session(
                    session, tailoring.id
                ) == [child.id]
                assert child.id in await runs_repo.list_tailoring_run_ids_for_profile(
                    session, profile_id
                )
                chat_history = await observability_repo.list_runs_before(
                    session, limit=10
                )
                chat_run_ids = {run.id for run in chat_history}
                assert chat_run_ids == {parent_id, other_run_id}
                assert child.id not in chat_run_ids
                with pytest.raises(ActivityBlockedError):
                    await assert_tailoring_start_allowed(
                        session,
                        profile_id=profile_id,
                        parent_run_id=parent_id,
                    )
                child.parent_run_id = child.id
                with pytest.raises(
                    IntegrityError, match="invalid tailoring parent run"
                ):
                    await session.flush()
                await session.rollback()
        finally:
            await engine.dispose()

    run_async(_body())


def test_tailoring_run_and_manual_generating_session_block_all_owner_gates(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment = Attachment(
                    file_hash="d" * 64,
                    original_name="manual.pdf",
                    mime_type="application/pdf",
                    size_bytes=10,
                    page_count=1,
                    storage_path="manual.pdf",
                    state="archived",
                )
                session.add(attachment)
                await session.flush()
                profile = Profile(
                    attachment_id=attachment.id,
                    display_name="Manual Candidate",
                    profile_json={"summary": "Synthetic"},
                    location=None,
                    extraction_version="cv-document-v1",
                    source_hash="source-b",
                    state="ready",
                )
                session.add(profile)
                await session.flush()
                conversation = Conversation(profile_id=profile.id, title="Manual")
                session.add(conversation)
                await session.flush()
                tailoring = await tailoring_repo.create_session(
                    session,
                    profile_id=profile.id,
                    source_attachment_id=attachment.id,
                    source_hash=profile.source_hash,
                    profile_updated_at=profile.updated_at,
                    job_id=None,
                    job_updated_at=None,
                    job_label_json=None,
                    instruction="Manual compile",
                    template_version="latex-cv-v1",
                )
                await session.commit()
                profile_id = profile.id
                conversation_id = conversation.id
                tailoring_id = tailoring.id

            async with factory() as session:
                for gate in (
                    lambda: assert_workspace_idle(session),
                    lambda: assert_profile_idle(session, profile_id=profile_id),
                    lambda: assert_conversation_idle(
                        session, conversation_id=conversation_id
                    ),
                ):
                    with pytest.raises(ActivityBlockedError):
                        await gate()

                row = await tailoring_repo.get_session(session, tailoring_id)
                assert row is not None
                row.state = "ready"
                row.updated_at = utc_now()
                await session.flush()
                run = await runs_repo.create_tailoring_run(
                    session, tailoring_session_id=tailoring_id
                )
                assert isinstance(run, AgentRun) and run.user_message_id is None
                for gate in (
                    lambda: assert_workspace_idle(session),
                    lambda: assert_profile_idle(session, profile_id=profile_id),
                    lambda: assert_conversation_idle(
                        session, conversation_id=conversation_id
                    ),
                ):
                    with pytest.raises(ActivityBlockedError):
                        await gate()
        finally:
            await engine.dispose()

    run_async(_body())
