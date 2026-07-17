"""Integration tests for retryable non-active CV deletion (Plan 9 04A).

Active guard, eligible-state complete cleanup, per-step fault/retry, legacy
ownership redaction, and cross-store preservation of active/shared/unrelated data.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_DELETING,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
)
from app.db.session import build_async_engine
from app.graph.delete_cv import (
    DELETE_CV_BRANCH_CYPHER,
    assert_delete_cv_query_allowlisted,
    delete_cv_branch,
)
from app.repositories import agent_runs as runs_repo
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as prof_repo
from app.repositories import tool_executions as tool_repo
from app.repositories.attachment_text_chunks import build_chunk_write
from app.schemas.cv_manager import (
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN,
    ERROR_CV_ATTACHMENT_NOT_FOUND,
    ERROR_CV_DELETE_CHECKPOINT_FAILED,
    ERROR_CV_DELETE_FILE_FAILED,
    ERROR_CV_DELETE_FINALIZE_FAILED,
    ERROR_CV_DELETE_GRAPH_FAILED,
)
from app.schemas.tools import ToolResult
from app.services.cv_manager import CvDeleteError, delete_cv
from app.storage.attachments import AttachmentStorage
from langgraph.checkpoint.base import empty_checkpoint

from tests.fakes.fake_chat_model import FakeChatModel
from tests.fakes.graph_rebuild import FakeNeo4jDriver
from tests.support.db_migration import run_async, session_factory
from tests.support.health import install_fake_driver, prepare_health_env
from tests.support.public_api import ai_text, client_with_fake_chat


@pytest.fixture
def del_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Path]]:
    db_path, files = prepare_health_env(monkeypatch, tmp_path)
    install_fake_driver(monkeypatch)
    yield db_path, files


def _write_pdf(storage: AttachmentStorage, attachment_id: str) -> str:
    return storage.write_bytes(attachment_id, b"%PDF-1.4\n%delete-test\n")


async def _seed_attachment(
    session: Any,
    storage: AttachmentStorage,
    *,
    state: str,
    file_hash: str | None = None,
    page_count: int | None = 1,
) -> Any:
    """Seed one attachment. For archived, ensure no concurrent active row."""
    aid = new_uuid()
    rel = _write_pdf(storage, aid)
    row = await att_repo.create_staged(
        session,
        file_hash=file_hash or f"hash-{aid}",
        original_name=f"{state}.pdf",
        size_bytes=32,
        storage_path=rel,
        page_count=page_count,
        attachment_id=aid,
    )
    if state == ATTACHMENT_STATE_STAGED:
        return row
    if state == ATTACHMENT_STATE_FAILED:
        return await att_repo.mark_failed(
            session, aid, failure_code="NO_EXTRACTABLE_TEXT"
        )
    if state == ATTACHMENT_STATE_ACTIVE:
        return await att_repo.mark_active(session, aid, page_count=page_count or 1)
    if state == ATTACHMENT_STATE_ARCHIVED:
        await att_repo.mark_active(session, aid, page_count=page_count or 1)
        return await att_repo.mark_archived(session, aid)
    if state == ATTACHMENT_STATE_DELETING:
        await att_repo.mark_failed(session, aid, failure_code="NO_EXTRACTABLE_TEXT")
        return await att_repo.mark_deleting(session, aid)
    raise AssertionError(f"unsupported seed state {state!r}")


async def _seed_cv_document(session: Any, attachment_id: str) -> None:
    await cv_doc_repo.upsert_document(
        session,
        attachment_id=attachment_id,
        document_json={"sections": []},
        profile_json={"full_name": "Del"},
        outline_json={"sections": []},
        extraction_version="v1",
        source_hash="src-hash",
    )


async def _seed_chunk(session: Any, attachment_id: str) -> None:
    await chunk_repo.replace_for_attachment(
        session,
        attachment_id,
        [build_chunk_write(0, "chunk body")],
    )


def test_delete_cv_branch_cypher_is_allowlisted() -> None:
    assert_delete_cv_query_allowlisted(DELETE_CV_BRANCH_CYPHER)
    with pytest.raises(ValueError):
        assert_delete_cv_query_allowlisted("MATCH (n) DETACH DELETE n")
    with pytest.raises(ValueError):
        assert_delete_cv_query_allowlisted(
            "MATCH (j:Job {id: $cv_id}) DETACH DELETE j"
        )


def test_active_delete_forbidden_no_mutation(del_env: tuple[Path, Path]) -> None:
    db_path, files = del_env
    storage = AttachmentStorage(files)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                active = await _seed_attachment(
                    session, storage, state=ATTACHMENT_STATE_ACTIVE
                )
                await _seed_chunk(session, active.id)
                await session.commit()
                aid = active.id
                before_hash = active.file_hash

            driver = FakeNeo4jDriver()
            with pytest.raises(CvDeleteError) as ei:
                await delete_cv(
                    aid,
                    storage=storage,
                    session_factory=factory,
                    driver=driver,
                    sqlite_path=db_path,
                )
            assert ei.value.code == ERROR_CV_ACTIVE_DELETE_FORBIDDEN
            assert driver.queries == []

            async with factory() as session:
                row = await att_repo.get_by_id(session, aid)
                assert row is not None
                assert row.state == ATTACHMENT_STATE_ACTIVE
                assert row.file_hash == before_hash
                chunks = await chunk_repo.list_for_attachment(session, aid)
                assert len(chunks) == 1
            assert storage.exists(aid)
        finally:
            await engine.dispose()

    run_async(_body())


def test_complete_archived_deletion_and_preservation(
    del_env: tuple[Path, Path],
) -> None:
    db_path, files = del_env
    storage = AttachmentStorage(files)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                # Archived first (sole active briefly), then active + staged.
                archived = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ARCHIVED,
                    file_hash="h-arch",
                )
                active = await _seed_attachment(
                    session, storage, state=ATTACHMENT_STATE_ACTIVE, file_hash="h-act"
                )
                other = await _seed_attachment(
                    session, storage, state=ATTACHMENT_STATE_STAGED, file_hash="h-oth"
                )
                await _seed_cv_document(session, archived.id)
                await _seed_chunk(session, archived.id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=active.id,
                    profile_json={"full_name": "Keep"},
                )

                owned_msg = await messages_repo.insert_message(
                    session,
                    role="assistant",
                    content="CV summary for delete target",
                    source_attachment_id=archived.id,
                )
                legacy_msg = await messages_repo.insert_message(
                    session,
                    role="assistant",
                    content="legacy payload owner",
                    structured_payload={
                        "attachment_id": archived.id,
                        "kind": "note",
                    },
                )
                keep_msg = await messages_repo.insert_message(
                    session,
                    role="user",
                    content="unrelated chat",
                )
                cv_run = await runs_repo.create_run(
                    session,
                    user_message_id=owned_msg.id,
                    source_attachment_id=archived.id,
                )
                other_user = await messages_repo.insert_message(
                    session, role="user", content="other run turn"
                )
                other_run = await runs_repo.create_run(
                    session, user_message_id=other_user.id
                )
                await tool_repo.get_or_create_pending(
                    session,
                    run_id=cv_run.id,
                    tool_call_id="t-cv",
                    tool_name="propose_profile_from_cv",
                    source_attachment_id=archived.id,
                    arguments_summary_json={"attachment_id": archived.id},
                )
                cross, _ = await tool_repo.get_or_create_pending(
                    session,
                    run_id=other_run.id,
                    tool_call_id="t-cross",
                    tool_name="propose_profile_from_cv",
                    source_attachment_id=archived.id,
                    arguments_summary_json={"attachment_id": archived.id},
                )
                await tool_repo.mark_running(session, cross.id)
                await tool_repo.complete_execution(
                    session,
                    cross.id,
                    result=ToolResult(
                        ok=True,
                        code=None,
                        summary="ok",
                        data={"attachment_id": archived.id},
                    ),
                    duration_ms=1,
                )
                keep_tool, _ = await tool_repo.get_or_create_pending(
                    session,
                    run_id=other_run.id,
                    tool_call_id="t-keep",
                    tool_name="query_jobs",
                    arguments_summary_json={"q": "python"},
                )
                await session.commit()
                target = archived.id
                active_id = active.id
                other_id = other.id
                keep_msg_id = keep_msg.id
                legacy_id = legacy_msg.id
                owned_id = owned_msg.id
                other_run_id = other_run.id
                keep_tool_id = keep_tool.id
                cv_run_id = cv_run.id

            async with open_checkpointer(db_path) as saver:
                cfg = {
                    "configurable": {
                        "thread_id": cv_run_id,
                        "checkpoint_ns": "",
                    }
                }
                await saver.aput(cfg, empty_checkpoint(), {}, {})
                assert await thread_has_checkpoints(saver, cv_run_id)

            driver = FakeNeo4jDriver()
            driver.candidates.add("active")
            driver.jobs.add("job-1")
            driver.skills.add("python")

            result = await delete_cv(
                target,
                storage=storage,
                session_factory=factory,
                driver=driver,
                sqlite_path=db_path,
            )
            assert result.attachment_id == target
            assert any("CV" in q and "DETACH DELETE" in q for q in driver.queries)
            assert driver.candidates == {"active"}
            assert driver.jobs == {"job-1"}
            assert driver.skills == {"python"}

            async with factory() as session:
                assert await att_repo.get_by_id(session, target) is None
                assert await cv_doc_repo.get_document(session, target) is None
                assert await chunk_repo.list_for_attachment(session, target) == []
                act = await att_repo.get_by_id(session, active_id)
                assert act is not None and act.state == ATTACHMENT_STATE_ACTIVE
                oth = await att_repo.get_by_id(session, other_id)
                assert oth is not None and oth.state == ATTACHMENT_STATE_STAGED
                prof = await prof_repo.get_active_profile(session)
                assert prof is not None
                assert prof.active_attachment_id == active_id

                by_id = {m.id: m for m in await messages_repo.list_messages(session)}
                assert by_id[owned_id].content == "[CV deleted]"
                assert by_id[owned_id].structured_payload is None
                assert by_id[owned_id].source_attachment_id is None
                assert by_id[owned_id].redacted_at is not None
                assert by_id[legacy_id].content == "[CV deleted]"
                assert by_id[keep_msg_id].content == "unrelated chat"
                assert by_id[keep_msg_id].source_attachment_id is None

                assert await runs_repo.get_run(session, cv_run_id) is None
                assert await runs_repo.get_run(session, other_run_id) is not None
                assert await tool_repo.get_by_id(session, keep_tool_id) is not None
                remaining_tools = await tool_repo.list_for_run_ids(
                    session, [other_run_id]
                )
                assert {t.id for t in remaining_tools} == {keep_tool_id}

            assert not storage.exists(target)
            assert storage.exists(active_id)
            assert storage.exists(other_id)

            async with open_checkpointer(db_path) as saver:
                assert not await thread_has_checkpoints(saver, cv_run_id)

            with pytest.raises(CvDeleteError) as ei:
                await delete_cv(
                    target,
                    storage=storage,
                    session_factory=factory,
                    driver=driver,
                    sqlite_path=db_path,
                )
            assert ei.value.code == ERROR_CV_ATTACHMENT_NOT_FOUND
        finally:
            await engine.dispose()

    run_async(_body())


@pytest.mark.parametrize(
    "failpoint,code",
    [
        ("checkpoint", ERROR_CV_DELETE_CHECKPOINT_FAILED),
        ("file", ERROR_CV_DELETE_FILE_FAILED),
        ("graph", ERROR_CV_DELETE_GRAPH_FAILED),
        ("finalize", ERROR_CV_DELETE_FINALIZE_FAILED),
    ],
)
def test_fault_injection_retains_deleting_then_retry_succeeds(
    del_env: tuple[Path, Path],
    failpoint: str,
    code: str,
) -> None:
    db_path, files = del_env
    storage = AttachmentStorage(files)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _seed_attachment(
                    session, storage, state=ATTACHMENT_STATE_FAILED
                )
                await _seed_chunk(session, row.id)
                msg = await messages_repo.insert_message(
                    session,
                    role="assistant",
                    content="owned",
                    source_attachment_id=row.id,
                )
                run = await runs_repo.create_run(
                    session,
                    user_message_id=msg.id,
                    source_attachment_id=row.id,
                )
                await session.commit()
                aid = row.id
                run_id = run.id
                msg_id = msg.id

            driver = FakeNeo4jDriver()
            with pytest.raises(CvDeleteError) as ei:
                await delete_cv(
                    aid,
                    storage=storage,
                    session_factory=factory,
                    driver=driver,
                    sqlite_path=db_path,
                    failpoint=failpoint,  # type: ignore[arg-type]
                )
            assert ei.value.code == code
            assert "retry" in ei.value.message.lower()

            async with factory() as session:
                stuck = await att_repo.get_by_id(session, aid)
                assert stuck is not None
                assert stuck.state == ATTACHMENT_STATE_DELETING
                assert stuck.failure_code is None
                by_id = {m.id: m for m in await messages_repo.list_messages(session)}
                assert by_id[msg_id].content == "[CV deleted]"

            await delete_cv(
                aid,
                storage=storage,
                session_factory=factory,
                driver=driver,
                sqlite_path=db_path,
            )
            async with factory() as session:
                assert await att_repo.get_by_id(session, aid) is None
                assert await runs_repo.get_run(session, run_id) is None
            assert not storage.exists(aid)
        finally:
            await engine.dispose()

    run_async(_body())


def test_pending_approval_draft_cleanup(del_env: tuple[Path, Path]) -> None:
    db_path, files = del_env
    storage = AttachmentStorage(files)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                staged = await _seed_attachment(
                    session, storage, state=ATTACHMENT_STATE_STAGED
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json={
                        "profile": {"full_name": "Draft"},
                        "preferences": None,
                        "preferences_changed": False,
                    },
                    source_attachment_id=staged.id,
                )
                await cv_doc_repo.upsert_draft(
                    session,
                    attachment_id=staged.id,
                    document_json={"sections": []},
                    profile_json={"full_name": "Draft"},
                    outline_json={"sections": []},
                    extraction_version="v1",
                    source_hash="dhash",
                )
                msg = await messages_repo.insert_message(
                    session,
                    role="user",
                    content="extract this",
                    source_attachment_id=staged.id,
                )
                run = await runs_repo.create_run(
                    session,
                    user_message_id=msg.id,
                    source_attachment_id=staged.id,
                )
                await runs_repo.interrupt_run(
                    session,
                    run.id,
                    pending_approval_json={
                        "kind": "profile_commit",
                        "draft_id": "current",
                        "allowed_actions": ["save_profile", "request_changes"],
                        "card": {"attachment_id": staged.id},
                    },
                )
                await session.commit()
                aid = staged.id

            await delete_cv(
                aid,
                storage=storage,
                session_factory=factory,
                driver=FakeNeo4jDriver(),
                sqlite_path=db_path,
            )
            async with factory() as session:
                assert await att_repo.get_by_id(session, aid) is None
                assert await prof_repo.get_current_draft(session) is None
                assert await cv_doc_repo.get_draft(session, aid) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_delete_api_active_and_success(del_env: tuple[Path, Path]) -> None:
    db_path, files = del_env
    storage = AttachmentStorage(files)

    async def _seed() -> tuple[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                archived = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ARCHIVED,
                    file_hash="api-b",
                )
                active = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ACTIVE,
                    file_hash="api-a",
                )
                await session.commit()
                return active.id, archived.id
        finally:
            await engine.dispose()

    active_id, archived_id = run_async(_seed())

    model = FakeChatModel(responses=[ai_text("noop")])
    with client_with_fake_chat(db_path, model) as client:
        resp = client.delete(f"/api/cvs/{active_id}")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == ERROR_CV_ACTIVE_DELETE_FORBIDDEN

        resp2 = client.delete(f"/api/cvs/{archived_id}")
        assert resp2.status_code == 204
        assert resp2.content == b""

        resp3 = client.delete(f"/api/cvs/{archived_id}")
        assert resp3.status_code == 404
        assert resp3.json()["detail"]["code"] == ERROR_CV_ATTACHMENT_NOT_FOUND


def test_historical_tool_ownership_without_fk(del_env: tuple[Path, Path]) -> None:
    db_path, files = del_env
    storage = AttachmentStorage(files)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                target = await _seed_attachment(
                    session, storage, state=ATTACHMENT_STATE_ARCHIVED
                )
                user = await messages_repo.insert_message(
                    session, role="user", content="match jobs"
                )
                run = await runs_repo.create_run(session, user_message_id=user.id)
                tool, _ = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run.id,
                    tool_call_id="legacy-cv",
                    tool_name="propose_profile_from_cv",
                    arguments_summary_json={"attachment_id": target.id},
                )
                await tool_repo.mark_running(session, tool.id)
                await tool_repo.complete_execution(
                    session,
                    tool.id,
                    result=ToolResult(
                        ok=True,
                        code=None,
                        summary="drafted",
                        data={"attachment_id": target.id, "draft_id": "current"},
                    ),
                    duration_ms=3,
                )
                await session.commit()
                aid = target.id
                tool_id = tool.id
                run_id = run.id

            await delete_cv(
                aid,
                storage=storage,
                session_factory=factory,
                driver=FakeNeo4jDriver(),
                sqlite_path=db_path,
            )
            async with factory() as session:
                assert await att_repo.get_by_id(session, aid) is None
                assert await tool_repo.get_by_id(session, tool_id) is None
                assert await runs_repo.get_run(session, run_id) is not None
        finally:
            await engine.dispose()

    run_async(_body())


def test_delete_cv_branch_parameterized_and_idempotent() -> None:
    async def _body() -> None:
        driver = FakeNeo4jDriver()
        aid = new_uuid()
        await delete_cv_branch(driver, aid)
        await delete_cv_branch(driver, aid)
        assert len(driver.queries) == 2
        for q, p in zip(driver.queries, driver.parameters, strict=True):
            assert_delete_cv_query_allowlisted(q)
            assert p == {"cv_id": aid}

    run_async(_body())
