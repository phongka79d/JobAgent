"""Integration tests for Plan 8 observability HTTP contracts.

Covers ``/api/observability`` routes: CV history, retained file stream, chunk
list/detail, run history, and the bounded Neo4j graph snapshot — cursor pages,
redaction, safe errors, graph status/caps, and no mutation.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
)
from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
)
from app.db.session import build_async_engine
from app.graph.consistency import NEO4J_REBUILD_REQUIRED, NEO4J_UNAVAILABLE
from app.graph.observability import CAP_EDGES, CAP_JOBS, CAP_SKILLS
from app.main import create_app
from app.repositories import agent_runs as runs_repo
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import profiles as profile_repo
from app.repositories import tool_executions as tool_repo
from app.repositories.attachment_text_chunks import build_chunk_write
from app.schemas.observability import (
    FILE_HASH_ABBREV_CHARS,
    ChunkDetail,
    ChunkListPage,
    CvHistoryPage,
    GraphSnapshot,
    RunHistoryPage,
    decode_chunk_cursor,
    decode_observability_cursor,
    encode_chunk_cursor,
    encode_observability_cursor,
)
from app.schemas.tools import ToolResult
from app.services.observability import ERROR_NO_ACTIVE_PROFILE
from app.storage.attachments import AttachmentStorage
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.db_migration import (
    cleanup_isolated_sqlite,
    run_async,
    session_factory,
)
from tests.support.graph_rebuild import seed_candidate
from tests.support.health import (
    FAKE_SHOPAIKEY,
    FakeDriver,
    install_fake_driver,
    prepare_health_env,
    public_api_routes,
)

T0 = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)

FORBIDDEN_RESPONSE_KEYS: frozenset[str] = frozenset(
    {
        "storage_path",
        "arguments_summary",
        "arguments_summary_json",
        "pending_approval",
        "pending_approval_json",
        "checkpoint",
        "prompt",
        "stack",
        "embedding",
        "embeddings",
        "SHOPAIKEY_API_KEY",
        "api_key",
    }
)


@pytest.fixture
def obs_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Path, FakeDriver]]:
    """Migrated temp SQLite + FILES_DIR + fake Neo4j for observability API."""
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = install_fake_driver(monkeypatch)
    yield db_path, files_dir, fake
    cleanup_isolated_sqlite()


def _client() -> TestClient:
    return TestClient(create_app())


def _assert_no_forbidden(payload: Any) -> None:
    """Recursively assert response JSON has no prohibited keys/secrets."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key not in FORBIDDEN_RESPONSE_KEYS, f"forbidden key {key!r}"
            assert key != "file_hash", "full file_hash must not appear"
            _assert_no_forbidden(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_forbidden(item)
    elif isinstance(payload, str):
        assert FAKE_SHOPAIKEY not in payload
        assert "stack" not in payload.lower() or payload in {
            # allow ordinary English words only when not a dump key path
        }


async def _table_counts(session: AsyncSession) -> dict[str, int]:
    """Return row counts for mutation-guard tables."""
    async def _count(table: str) -> int:
        return int(
            (await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
        )

    return {
        "attachments": await _count("attachments"),
        "chunks": await _count("attachment_text_chunks"),
        "runs": await _count("agent_runs"),
        "tools": await _count("tool_executions"),
    }


async def _seed_attachment(
    session: AsyncSession,
    storage: AttachmentStorage,
    *,
    state: str,
    created_at: datetime,
    file_hash: str,
    original_name: str = "resume.pdf",
    write_file: bool = True,
    page_count: int | None = 1,
    failure_code: str | None = None,
) -> str:
    """Insert one attachment. For ``archived``, no other row may be ``active``."""
    attachment_id = new_uuid()
    relative = storage.relative_path_for(attachment_id)
    if write_file:
        storage.write_bytes(attachment_id, b"%PDF-1.4 observability-test\n")
    row = await att_repo.create_staged(
        session,
        file_hash=file_hash,
        original_name=original_name,
        size_bytes=32,
        storage_path=relative,
        page_count=page_count if state != ATTACHMENT_STATE_FAILED else None,
        attachment_id=attachment_id,
    )
    if state == ATTACHMENT_STATE_ACTIVE:
        row = await att_repo.mark_active(
            session, attachment_id, page_count=page_count or 1
        )
    elif state == ATTACHMENT_STATE_ARCHIVED:
        await att_repo.mark_active(session, attachment_id, page_count=page_count or 1)
        row = await att_repo.mark_archived(session, attachment_id)
    elif state == ATTACHMENT_STATE_FAILED:
        row = await att_repo.mark_failed(
            session,
            attachment_id,
            failure_code=failure_code or "MALFORMED_PDF",
        )
    elif state != ATTACHMENT_STATE_STAGED:
        raise AssertionError(f"unsupported seed state {state!r}")
    row.created_at = created_at
    row.updated_at = created_at
    await session.flush()
    return attachment_id


async def _seed_chunks(
    session: AsyncSession,
    attachment_id: str,
    texts: list[str],
    *,
    base_time: datetime = T0,
) -> None:
    writes = [build_chunk_write(i, text) for i, text in enumerate(texts)]
    rows = await chunk_repo.replace_for_attachment(session, attachment_id, writes)
    for i, row in enumerate(rows):
        ts = base_time + timedelta(seconds=i)
        row.created_at = ts
    await session.flush()


async def _seed_run_with_tools(
    session: AsyncSession,
    *,
    created_at: datetime,
    attachment_id: str | None = None,
) -> str:
    msg = await messages_repo.insert_message(
        session,
        role=CHAT_MESSAGE_ROLE_USER,
        content="observability seed turn",
    )
    run = await runs_repo.create_run(session, user_message_id=msg.id)
    args: dict[str, Any] | None = None
    if attachment_id is not None:
        args = {"attachment_id": attachment_id, "secret_should_not_leak": "x"}
    tool, _created = await tool_repo.get_or_create_pending(
        session,
        run_id=run.id,
        tool_call_id=f"call-{run.id[:8]}",
        tool_name="propose_profile_from_cv",
        arguments_summary_json=args,
    )
    await tool_repo.mark_running(session, tool.id)
    result = ToolResult(
        ok=True,
        code=None,
        summary="profile draft proposed",
        data={"attachment_id": attachment_id} if attachment_id else None,
    )
    await tool_repo.complete_execution(
        session,
        tool.id,
        result=result,
        duration_ms=12,
    )
    run = await runs_repo.complete_run(session, run.id)
    run.created_at = created_at
    run.updated_at = created_at
    if run.completed_at is not None:
        run.completed_at = created_at
    await session.flush()
    return run.id


# ---------------------------------------------------------------------------
# Route inventory (observability routes including graph)
# ---------------------------------------------------------------------------


def test_observability_routes_registered(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, _files, _fake = obs_env
    with _client() as client:
        routes = public_api_routes(client.app)
    expected = {
        ("GET", "/api/observability/cvs"),
        ("GET", "/api/observability/cvs/{attachment_id}/file"),
        ("GET", "/api/observability/cvs/{attachment_id}/chunks"),
        ("GET", "/api/observability/cvs/{attachment_id}/chunks/{ordinal}"),
        ("GET", "/api/observability/runs"),
        ("GET", "/api/observability/graph"),
    }
    for item in expected:
        assert item in routes


def test_observability_routes_are_transport_thin() -> None:
    src = (
        Path(__file__).resolve().parents[2] / "app" / "api" / "observability.py"
    ).read_text(encoding="utf-8")
    for needle in (
        "StateGraph",
        "ChatOpenAI",
        "create_all",
        "AsyncSqliteSaver",
        "session.execute",
        "mark_active",
        "mark_archived",
        "replace_for_attachment",
    ):
        assert needle not in src, f"observability route leaked {needle!r}"


# ---------------------------------------------------------------------------
# CV history
# ---------------------------------------------------------------------------


def test_cv_history_empty_page(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, _files, _fake = obs_env
    with _client() as client:
        response = client.get("/api/observability/cvs")
    assert response.status_code == 200
    body = response.json()
    page = CvHistoryPage.model_validate(body)
    assert set(body.keys()) == {"items", "next_cursor"}
    assert page.items == []
    assert page.next_cursor is None
    _assert_no_forbidden(body)


def test_cv_history_pagination_and_post_final_cursor(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, files_dir, _fake = obs_env
    storage = AttachmentStorage(files_dir)

    async def _seed() -> list[str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        ids: list[str] = []
        try:
            async with factory() as session:
                for i in range(3):
                    aid = await _seed_attachment(
                        session,
                        storage,
                        state=ATTACHMENT_STATE_ARCHIVED
                        if i < 2
                        else ATTACHMENT_STATE_ACTIVE,
                        created_at=T0 + timedelta(minutes=i),
                        file_hash=f"hash-cv-{i:02d}-{'a' * 48}",
                        original_name=f"cv-{i}.pdf",
                    )
                    ids.append(aid)
                await session.commit()
        finally:
            await engine.dispose()
        return ids

    ids = run_async(_seed())
    with _client() as client:
        first = client.get("/api/observability/cvs", params={"limit": 2})
        assert first.status_code == 200
        page1 = CvHistoryPage.model_validate(first.json())
        assert len(page1.items) == 2
        assert page1.next_cursor is not None
        # Chronological within page (oldest → newest of the newest-2).
        assert page1.items[0].created_at <= page1.items[1].created_at
        assert page1.items[0].id == ids[1]
        assert page1.items[1].id == ids[2]
        for item in page1.items:
            assert item.file_available is True
            assert len(item.file_hash_abbreviated) == FILE_HASH_ABBREV_CHARS
            assert item.mime_type == ATTACHMENT_MIME_TYPE_PDF

        second = client.get(
            "/api/observability/cvs",
            params={"limit": 2, "before": page1.next_cursor},
        )
        assert second.status_code == 200
        page2 = CvHistoryPage.model_validate(second.json())
        assert len(page2.items) == 1
        assert page2.items[0].id == ids[0]
        assert page2.next_cursor is None

        # Well-formed post-final cursor → empty page, next_cursor null.
        oldest = page2.items[0]
        past = encode_observability_cursor(oldest.created_at, oldest.id)
        # Advance past by using a synthetic older cursor encoded from same row
        # (list_before is strict < so same-cursor excludes the row).
        post = client.get(
            "/api/observability/cvs",
            params={"limit": 2, "before": past},
        )
        assert post.status_code == 200
        page3 = CvHistoryPage.model_validate(post.json())
        assert page3.items == []
        assert page3.next_cursor is None
        _assert_no_forbidden(first.json())
        _assert_no_forbidden(second.json())


def test_cv_history_malformed_cursor_422(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, _files, _fake = obs_env
    with _client() as client:
        bad = client.get(
            "/api/observability/cvs",
            params={"before": "!!!not-base64!!!"},
        )
        assert bad.status_code == 422
        assert FAKE_SHOPAIKEY not in bad.text

        empty = client.get("/api/observability/cvs", params={"before": ""})
        assert empty.status_code == 422

        over = client.get("/api/observability/cvs", params={"limit": 51})
        assert over.status_code == 422

        under = client.get("/api/observability/cvs", params={"limit": 0})
        assert under.status_code == 422


def test_cv_history_missing_file_flags_unavailable(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, files_dir, _fake = obs_env
    storage = AttachmentStorage(files_dir)

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                aid = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ARCHIVED,
                    created_at=T0,
                    file_hash="missing-file-hash" + "0" * 40,
                    write_file=False,
                )
                await session.commit()
                return aid
        finally:
            await engine.dispose()

    aid = run_async(_seed())
    with _client() as client:
        response = client.get("/api/observability/cvs")
    assert response.status_code == 200
    page = CvHistoryPage.model_validate(response.json())
    assert len(page.items) == 1
    assert page.items[0].id == aid
    assert page.items[0].file_available is False
    assert page.items[0].state == ATTACHMENT_STATE_ARCHIVED


# ---------------------------------------------------------------------------
# Retained file stream
# ---------------------------------------------------------------------------


def test_retained_file_stream_and_safe_errors(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, files_dir, _fake = obs_env
    storage = AttachmentStorage(files_dir)

    async def _seed() -> tuple[str, str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                # Archive first (requires temporary active) before final active.
                missing_id = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ARCHIVED,
                    created_at=T0 + timedelta(minutes=1),
                    file_hash="missing-hash" + "b" * 49,
                    write_file=False,
                )
                staged_id = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_STAGED,
                    created_at=T0 + timedelta(minutes=2),
                    file_hash="staged-hash" + "c" * 50,
                )
                active_id = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ACTIVE,
                    created_at=T0,
                    file_hash="active-hash" + "a" * 50,
                    original_name="My Cool CV.pdf",
                )
                await session.commit()
                return active_id, missing_id, staged_id
        finally:
            await engine.dispose()

    active_id, missing_id, staged_id = run_async(_seed())
    with _client() as client:
        ok = client.get(f"/api/observability/cvs/{active_id}/file")
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("application/pdf")
        assert "attachment;" in ok.headers["content-disposition"].lower()
        assert "My Cool CV.pdf" in ok.headers["content-disposition"]
        assert b"%PDF-" in ok.content
        assert str(files_dir) not in ok.text
        assert "storage_path" not in ok.text

        missing = client.get(f"/api/observability/cvs/{missing_id}/file")
        assert missing.status_code == 404
        detail = missing.json()["detail"]
        assert detail["code"] == "CV_FILE_UNAVAILABLE"
        assert str(files_dir) not in missing.text

        staged = client.get(f"/api/observability/cvs/{staged_id}/file")
        assert staged.status_code == 404
        assert staged.json()["detail"]["code"] == "CV_ATTACHMENT_NOT_FOUND"

        unknown = client.get(f"/api/observability/cvs/{new_uuid()}/file")
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "CV_ATTACHMENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------


def test_chunk_list_detail_pagination_and_historic_unavailable(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, files_dir, _fake = obs_env
    storage = AttachmentStorage(files_dir)
    long_text = "Alpha chunk text for full-detail expansion. " * 5

    async def _seed() -> tuple[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                # Historic archive before the active chunked attachment.
                historic = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ARCHIVED,
                    created_at=T0 - timedelta(days=1),
                    file_hash="historic-hash" + "e" * 48,
                )
                with_chunks = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ACTIVE,
                    created_at=T0,
                    file_hash="chunked-hash" + "d" * 49,
                )
                await _seed_chunks(
                    session,
                    with_chunks,
                    [
                        "chunk-zero-preview-source",
                        "chunk-one-preview-source",
                        long_text,
                    ],
                )
                await session.commit()
                return with_chunks, historic
        finally:
            await engine.dispose()

    with_chunks, historic = run_async(_seed())
    with _client() as client:
        # Historic no rows → CHUNKS_UNAVAILABLE
        hist = client.get(f"/api/observability/cvs/{historic}/chunks")
        assert hist.status_code == 404
        assert hist.json()["detail"]["code"] == "CHUNKS_UNAVAILABLE"

        hist_detail = client.get(
            f"/api/observability/cvs/{historic}/chunks/0"
        )
        assert hist_detail.status_code == 404
        assert hist_detail.json()["detail"]["code"] == "CHUNKS_UNAVAILABLE"

        unknown = client.get(f"/api/observability/cvs/{new_uuid()}/chunks")
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "CV_ATTACHMENT_NOT_FOUND"

        page1_resp = client.get(
            f"/api/observability/cvs/{with_chunks}/chunks",
            params={"limit": 2},
        )
        assert page1_resp.status_code == 200
        page1 = ChunkListPage.model_validate(page1_resp.json())
        assert len(page1.items) == 2
        assert page1.items[0].ordinal == 0
        assert page1.items[1].ordinal == 1
        assert page1.next_cursor is not None
        # Collection must not include full text field.
        for raw in page1_resp.json()["items"]:
            assert "text" not in raw
            assert "preview" in raw
        _assert_no_forbidden(page1_resp.json())

        page2_resp = client.get(
            f"/api/observability/cvs/{with_chunks}/chunks",
            params={"limit": 2, "before": page1.next_cursor},
        )
        assert page2_resp.status_code == 200
        page2 = ChunkListPage.model_validate(page2_resp.json())
        assert len(page2.items) == 1
        assert page2.items[0].ordinal == 2
        assert page2.next_cursor is None

        # Post-final empty page.
        last = page2.items[0]
        past_cursor = encode_chunk_cursor(last.created_at, last.ordinal)
        post = client.get(
            f"/api/observability/cvs/{with_chunks}/chunks",
            params={"limit": 2, "before": past_cursor},
        )
        assert post.status_code == 200
        page3 = ChunkListPage.model_validate(post.json())
        assert page3.items == []
        assert page3.next_cursor is None

        detail_resp = client.get(
            f"/api/observability/cvs/{with_chunks}/chunks/2"
        )
        assert detail_resp.status_code == 200
        detail = ChunkDetail.model_validate(detail_resp.json())
        assert detail.ordinal == 2
        assert detail.text == long_text
        assert detail.char_count == len(long_text)
        _assert_no_forbidden(detail_resp.json())

        missing_ord = client.get(
            f"/api/observability/cvs/{with_chunks}/chunks/99"
        )
        assert missing_ord.status_code == 404
        assert missing_ord.json()["detail"]["code"] == "CHUNK_NOT_FOUND"

        bad_cursor = client.get(
            f"/api/observability/cvs/{with_chunks}/chunks",
            params={"before": "!!!bad!!!"},
        )
        assert bad_cursor.status_code == 422


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_run_history_redaction_pagination_and_related_ids(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, files_dir, _fake = obs_env
    storage = AttachmentStorage(files_dir)

    async def _seed() -> tuple[list[str], str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ACTIVE,
                    created_at=T0,
                    file_hash="run-att-hash" + "f" * 49,
                )
                run_ids: list[str] = []
                for i in range(3):
                    rid = await _seed_run_with_tools(
                        session,
                        created_at=T0 + timedelta(minutes=i),
                        attachment_id=att_id if i == 2 else None,
                    )
                    run_ids.append(rid)
                # Failed tool on last run for error_code/summary path.
                last = run_ids[-1]
                fail_tool, _ = await tool_repo.get_or_create_pending(
                    session,
                    run_id=last,
                    tool_call_id="call-fail-1",
                    tool_name="save_job",
                    arguments_summary_json={"url": "https://example.test/job"},
                )
                await tool_repo.mark_running(session, fail_tool.id)
                await tool_repo.fail_execution(
                    session,
                    fail_tool.id,
                    result=ToolResult(
                        ok=False,
                        code="URL_FETCH_FAILED",
                        summary="could not fetch job URL",
                        data=None,
                    ),
                    duration_ms=3,
                )
                await session.commit()
                return run_ids, att_id
        finally:
            await engine.dispose()

    run_ids, att_id = run_async(_seed())
    with _client() as client:
        empty_first = client.get("/api/observability/runs", params={"limit": 2})
        # DB already seeded — not empty.
        assert empty_first.status_code == 200
        page1 = RunHistoryPage.model_validate(empty_first.json())
        assert len(page1.items) == 2
        assert page1.next_cursor is not None
        # Chronological on page.
        assert page1.items[0].created_at <= page1.items[1].created_at
        assert page1.items[0].id == run_ids[1]
        assert page1.items[1].id == run_ids[2]

        newest = page1.items[1]
        assert att_id in newest.related_attachment_ids
        for tool in newest.tool_executions:
            dumped = tool.model_dump(mode="json")
            assert "arguments_summary" not in dumped
            assert "arguments" not in dumped
            assert "result" not in dumped
            if tool.tool_name == "propose_profile_from_cv":
                assert tool.status == TOOL_EXECUTION_STATUS_COMPLETED
                assert tool.summary == "profile draft proposed"
            if tool.tool_name == "save_job":
                assert tool.status == TOOL_EXECUTION_STATUS_FAILED
                assert tool.error_code == "URL_FETCH_FAILED"
                assert tool.summary == "could not fetch job URL"

        raw = empty_first.json()
        blob = json.dumps(raw)
        assert "secret_should_not_leak" not in blob
        assert "arguments_summary" not in blob
        assert "pending_approval" not in blob
        assert "https://example.test/job" not in blob
        _assert_no_forbidden(raw)

        page2_resp = client.get(
            "/api/observability/runs",
            params={"limit": 2, "before": page1.next_cursor},
        )
        assert page2_resp.status_code == 200
        page2 = RunHistoryPage.model_validate(page2_resp.json())
        assert len(page2.items) == 1
        assert page2.items[0].id == run_ids[0]
        assert page2.next_cursor is None

        past = encode_observability_cursor(
            page2.items[0].created_at, page2.items[0].id
        )
        post = client.get(
            "/api/observability/runs",
            params={"limit": 2, "before": past},
        )
        assert post.status_code == 200
        page3 = RunHistoryPage.model_validate(post.json())
        assert page3.items == []
        assert page3.next_cursor is None

        bad = client.get(
            "/api/observability/runs",
            params={"before": "not-a-cursor"},
        )
        assert bad.status_code == 422


def test_observability_reads_do_not_mutate(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, files_dir, _fake = obs_env
    storage = AttachmentStorage(files_dir)

    async def _seed_and_counts() -> dict[str, int]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                aid = await _seed_attachment(
                    session,
                    storage,
                    state=ATTACHMENT_STATE_ACTIVE,
                    created_at=T0,
                    file_hash="mut-hash" + "1" * 54,
                )
                await _seed_chunks(session, aid, ["only chunk"])
                await _seed_run_with_tools(
                    session, created_at=T0, attachment_id=aid
                )
                await session.commit()

            async with factory() as session:
                return await _table_counts(session)
        finally:
            await engine.dispose()

    before_counts = run_async(_seed_and_counts())

    async def _attachment_id() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await att_repo.get_active(session)
                assert row is not None
                return row.id
        finally:
            await engine.dispose()

    aid = run_async(_attachment_id())
    with _client() as client:
        assert client.get("/api/observability/cvs").status_code == 200
        assert client.get(f"/api/observability/cvs/{aid}/file").status_code == 200
        assert (
            client.get(f"/api/observability/cvs/{aid}/chunks").status_code == 200
        )
        assert (
            client.get(f"/api/observability/cvs/{aid}/chunks/0").status_code
            == 200
        )
        assert client.get("/api/observability/runs").status_code == 200
        # Graph may be ready/unavailable depending on fake; must not mutate SQLite.
        graph = client.get("/api/observability/graph")
        assert graph.status_code == 200

    async def _after() -> dict[str, int]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                return await _table_counts(session)
        finally:
            await engine.dispose()

    after_counts = run_async(_after())
    assert after_counts == before_counts


def test_cursor_helpers_roundtrip() -> None:
    mid = new_uuid()
    c = encode_observability_cursor(T0, mid)
    assert decode_observability_cursor(c) == (T0, mid)
    chunk_c = encode_chunk_cursor(T0, 3)
    assert decode_chunk_cursor(chunk_c) == (T0, 3)
    # Reject standard base64 alphabet.
    with pytest.raises(Exception):
        decode_chunk_cursor(
            base64.b64encode(b'{"created_at":"x","ordinal":0}').decode()
        )


# ---------------------------------------------------------------------------
# Bounded graph snapshot (02B)
# ---------------------------------------------------------------------------


class _GraphApiResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def data(self) -> list[dict[str, Any]]:
        return list(self._rows)

    async def consume(self) -> None:
        return None


class _GraphApiSession:
    def __init__(self, driver: GraphApiFakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _GraphApiSession:
        self._driver.session_enter += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit += 1

    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> _GraphApiResult:
        del kwargs
        self._driver.queries.append(query)
        params = dict(parameters) if parameters is not None else {}
        self._driver.parameters.append(params)
        upper = f" {' '.join(query.upper().split())} "
        # Lifespan may run idempotent schema DDL; record but do not fail startup.
        if " CREATE CONSTRAINT " in upper or " CREATE VECTOR INDEX " in upper:
            self._driver.schema_queries.append(query)
            return _GraphApiResult([])
        for token in (
            " MERGE ",
            " CREATE ",
            " DELETE ",
            " DETACH ",
            " SET ",
            " REMOVE ",
            " DROP ",
        ):
            if token in upper:
                self._driver.write_queries.append(query)
                raise AssertionError(f"write Cypher is not allowed: {query}")
        if self._driver.fail_all:
            raise OSError("simulated neo4j outage")
        return _GraphApiResult(self._driver.resolve(query, params))


class GraphApiFakeDriver:
    """Fake Neo4j driver for consistency + bounded observability projection."""

    def __init__(
        self,
        *,
        revision_candidates: Sequence[Mapping[str, Any]] | None = None,
        revision_jobs: Sequence[Mapping[str, Any]] | None = None,
        revision_active_cv: Sequence[Mapping[str, Any]] | None = None,
        proj_candidates: Sequence[Mapping[str, Any]] | None = None,
        proj_jobs: Sequence[Mapping[str, Any]] | None = None,
        proj_skills: Sequence[Mapping[str, Any]] | None = None,
        proj_edges: Sequence[Mapping[str, Any]] | None = None,
        proj_cvs: Sequence[Mapping[str, Any]] | None = None,
        proj_sections: Sequence[Mapping[str, Any]] | None = None,
        proj_entries: Sequence[Mapping[str, Any]] | None = None,
        fail_all: bool = False,
    ) -> None:
        self.revision_candidates = [dict(r) for r in (revision_candidates or ())]
        self.revision_jobs = [dict(r) for r in (revision_jobs or ())]
        self.revision_active_cv = [dict(r) for r in (revision_active_cv or ())]
        self.proj_candidates = [dict(r) for r in (proj_candidates or ())]
        self.proj_jobs = [dict(r) for r in (proj_jobs or ())]
        self.proj_skills = [dict(r) for r in (proj_skills or ())]
        self.proj_edges = [dict(r) for r in (proj_edges or ())]
        self.proj_cvs = [dict(r) for r in (proj_cvs or ())]
        self.proj_sections = [dict(r) for r in (proj_sections or ())]
        self.proj_entries = [dict(r) for r in (proj_entries or ())]
        self.fail_all = fail_all
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.write_queries: list[str] = []
        self.schema_queries: list[str] = []
        self.session_enter = 0
        self.session_exit = 0
        self.open_count = 0
        self.closed = False
        self.verify_calls = 0
        self.fail_connectivity = False

    async def verify_connectivity(self) -> None:
        self.verify_calls += 1
        if self.fail_connectivity or self.fail_all:
            raise OSError("simulated connectivity failure")

    async def close(self) -> None:
        self.closed = True

    def session(self, **config: Any) -> _GraphApiSession:
        del config
        return _GraphApiSession(self)

    def resolve(
        self, query: str, params: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        # Active CV consistency revision (PROJECTS_TO branch).
        if (
            "cv.source_updated_at AS source_updated_at" in query
            and "PROJECTS_TO" in query
        ):
            return list(self.revision_active_cv)
        # Consistency revision reads (source_updated_at alias).
        if "c.source_updated_at AS source_updated_at" in query:
            return list(self.revision_candidates)
        if "j.source_updated_at AS source_updated_at" in query:
            return list(self.revision_jobs)
        # Active CV projection counts / nodes.
        if "count(cv) AS total" in query and "PROJECTS_TO" in query:
            return [{"total": len(self.proj_cvs)}]
        if "count(sec) AS total" in query:
            return [{"total": len(self.proj_sections)}]
        if "count(entry) AS total" in query:
            return [{"total": len(self.proj_entries)}]
        if "cv.original_name AS original_name" in query:
            ordered = sorted(self.proj_cvs, key=lambda r: str(r.get("id", "")))
            return ordered[:1]
        if "sec.heading AS heading" in query:
            ordered = sorted(
                self.proj_sections,
                key=lambda r: (int(r.get("ordinal", 0)), str(r.get("id", ""))),
            )
            return ordered[:20]
        if "entry.preview AS preview" in query:
            ordered = sorted(
                self.proj_entries,
                key=lambda r: (
                    int(r.get("section_ordinal", 0)),
                    int(r.get("ordinal", 0)),
                    str(r.get("id", "")),
                ),
            )
            return ordered[:60]
        if "PROJECTS_TO|HAS_SECTION|HAS_ENTRY" in query:
            allowed = (
                set(params.get("cv_ids") or [])
                | set(params.get("section_ids") or [])
                | set(params.get("entry_ids") or [])
                | set(params.get("candidate_ids") or [])
            )
            out_cv: list[dict[str, Any]] = []
            for edge in self.proj_edges:
                etype = edge.get("type")
                if (
                    edge.get("source_id") in allowed
                    and edge.get("target_id") in allowed
                    and etype in {"PROJECTS_TO", "HAS_SECTION", "HAS_ENTRY"}
                ):
                    out_cv.append(dict(edge))
            return out_cv
        # Projection counts / nodes / edges.
        if "count(c) AS total" in query:
            return [{"total": len(self.proj_candidates)}]
        if "count(j) AS total" in query:
            return [{"total": len(self.proj_jobs)}]
        if "count(s) AS total" in query:
            return [{"total": len(self.proj_skills)}]
        if "c.source_updated_at AS revision" in query:
            ordered = sorted(
                self.proj_candidates, key=lambda r: str(r.get("id", ""))
            )
            return ordered[:1]
        if "j.title AS title" in query:
            ordered = sorted(self.proj_jobs, key=lambda r: str(r.get("id", "")))
            return ordered[:CAP_JOBS]
        if "s.canonical_key AS canonical_name" in query:
            ordered = sorted(
                self.proj_skills,
                key=lambda r: str(r.get("canonical_name", "")),
            )
            return ordered[:CAP_SKILLS]
        if "HAS_SKILL|REQUIRES|PREFERS|RELATED_TO" in query:
            allowed = set(params.get("candidate_ids") or []) | set(
                params.get("job_ids") or []
            ) | set(params.get("skill_keys") or [])
            out: list[dict[str, Any]] = []
            for edge in self.proj_edges:
                etype = edge.get("type")
                if (
                    edge.get("source_id") in allowed
                    and edge.get("target_id") in allowed
                    and etype
                    in {"HAS_SKILL", "REQUIRES", "PREFERS", "RELATED_TO"}
                ):
                    out.append(dict(edge))
            return out
        raise AssertionError(f"unscripted graph query: {query}")


def _iso_z(value: datetime) -> str:
    stamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def test_graph_no_active_profile_ready_empty(
    obs_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, _files, _fake = obs_env
    with _client() as client:
        response = client.get("/api/observability/graph")
    assert response.status_code == 200
    body = response.json()
    snap = GraphSnapshot.model_validate(body)
    assert snap.status == "ready"
    assert snap.code == ERROR_NO_ACTIVE_PROFILE
    assert snap.candidate is None
    assert snap.jobs == []
    assert snap.skills == []
    assert snap.edges == []
    assert snap.nodes_truncated is False
    assert snap.edges_truncated is False
    assert snap.omitted_node_count == 0
    assert snap.omitted_edge_count == 0
    _assert_no_forbidden(body)
    # No query/filter expansion accepted — extra params ignored without 422/500.
    with _client() as client:
        extra = client.get(
            "/api/observability/graph",
            params={"cypher": "MATCH (n) RETURN n", "limit": 99},
        )
    assert extra.status_code == 200
    assert GraphSnapshot.model_validate(extra.json()).code == ERROR_NO_ACTIVE_PROFILE


def test_graph_unavailable_when_neo4j_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path, _files = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = GraphApiFakeDriver(fail_all=True)
    install_fake_driver(monkeypatch, fake)  # type: ignore[arg-type]

    async def _seed() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            await seed_candidate(factory)
        finally:
            await engine.dispose()

    run_async(_seed())
    with _client() as client:
        response = client.get("/api/observability/graph")
    assert response.status_code == 200
    snap = GraphSnapshot.model_validate(response.json())
    assert snap.status == "unavailable"
    assert snap.code == NEO4J_UNAVAILABLE
    assert snap.candidate is None
    assert snap.jobs == []
    assert snap.edges == []
    assert snap.rebuild_instruction is None
    _assert_no_forbidden(response.json())


def test_graph_stale_when_revisions_diverge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path, _files = prepare_health_env(monkeypatch, tmp_path, migrate=True)

    async def _seed() -> tuple[str, datetime]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            await seed_candidate(factory)
            async with factory() as session:
                row = await profile_repo.get_active_profile(session)
                assert row is not None
                return row.id, row.updated_at
        finally:
            await engine.dispose()

    cand_id, cand_updated = run_async(_seed())
    # Graph candidate revision intentionally stale vs SQLite.
    fake = GraphApiFakeDriver(
        revision_candidates=[
            {
                "id": cand_id,
                "source_updated_at": "2000-01-01T00:00:00Z",
            }
        ],
        revision_jobs=[],
        proj_candidates=[
            {"id": cand_id, "revision": _iso_z(cand_updated)},
        ],
    )
    install_fake_driver(monkeypatch, fake)  # type: ignore[arg-type]

    with _client() as client:
        response = client.get("/api/observability/graph")
    assert response.status_code == 200
    snap = GraphSnapshot.model_validate(response.json())
    assert snap.status == "stale"
    assert snap.code == NEO4J_REBUILD_REQUIRED
    assert snap.candidate is None
    assert snap.jobs == []
    assert snap.skills == []
    assert snap.edges == []
    assert snap.rebuild_instruction is not None
    assert "rebuild" in snap.rebuild_instruction.lower()
    _assert_no_forbidden(response.json())
    assert fake.write_queries == []


def test_graph_ready_caps_order_and_truncation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path, _files = prepare_health_env(monkeypatch, tmp_path, migrate=True)

    async def _seed() -> tuple[str, datetime, list[tuple[str, datetime]]]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            await seed_candidate(factory)
            job_ids: list[str] = []
            for i in range(3):
                from tests.support.graph_rebuild import seed_scorable_job

                jid = await seed_scorable_job(
                    factory,
                    raw_hash=f"graph-job-hash-{i:02d}" + ("a" * 40),
                    raw_content=f"JD body {i}",
                )
                job_ids.append(jid)
            async with factory() as session:
                profile = await profile_repo.get_active_profile(session)
                assert profile is not None
                from app.db.models.jobs import JobPost
                from sqlalchemy import select

                rows = (
                    await session.execute(
                        select(JobPost).where(JobPost.id.in_(job_ids))
                    )
                ).scalars().all()
                job_revs = [(r.id, r.updated_at) for r in rows]
                return profile.id, profile.updated_at, job_revs
        finally:
            await engine.dispose()

    cand_id, cand_updated, job_revs = run_async(_seed())
    # Oversized projection corpus for truncation metadata.
    proj_jobs = [
        {
            "id": f"extra-job-{i:02d}",
            "title": f"Title {i:02d}",
            "company": f"Co {i:02d}",
            "revision": "2024-01-01T00:00:00Z",
        }
        for i in range(25)
    ]
    # Ensure SQLite job ids appear so consistency can pass with matching set.
    proj_jobs = [
        {
            "id": jid,
            "title": f"Seeded {jid[:8]}",
            "company": "SeedCo",
            "revision": _iso_z(updated),
        }
        for jid, updated in job_revs
    ] + proj_jobs
    proj_skills = [
        {"canonical_name": f"skill-{i:02d}"} for i in range(45)
    ]
    skill_names = sorted(s["canonical_name"] for s in proj_skills)[:CAP_SKILLS]
    job_ids_sorted = sorted(j["id"] for j in proj_jobs)[:CAP_JOBS]
    edges: list[dict[str, Any]] = []
    for s in skill_names:
        edges.append(
            {"source_id": cand_id, "target_id": s, "type": "HAS_SKILL"}
        )
    for jid in job_ids_sorted:
        for s in skill_names[:4]:
            edges.append(
                {"source_id": jid, "target_id": s, "type": "REQUIRES"}
            )
            edges.append(
                {"source_id": jid, "target_id": s, "type": "PREFERS"}
            )
    for i in range(len(skill_names) - 1):
        edges.append(
            {
                "source_id": skill_names[i],
                "target_id": skill_names[i + 1],
                "type": "RELATED_TO",
            }
        )
    # Disallowed edge type must not appear.
    edges.append(
        {
            "source_id": cand_id,
            "target_id": skill_names[0],
            "type": "OWNS",
        }
    )
    assert len(edges) > CAP_EDGES

    fake = GraphApiFakeDriver(
        revision_candidates=[
            {"id": cand_id, "source_updated_at": _iso_z(cand_updated)}
        ],
        revision_jobs=[
            {"id": jid, "source_updated_at": _iso_z(updated)}
            for jid, updated in job_revs
        ],
        proj_candidates=[{"id": cand_id, "revision": _iso_z(cand_updated)}],
        proj_jobs=proj_jobs,
        proj_skills=proj_skills,
        proj_edges=edges,
    )
    install_fake_driver(monkeypatch, fake)  # type: ignore[arg-type]

    with _client() as client:
        response = client.get("/api/observability/graph")
    assert response.status_code == 200
    body = response.json()
    snap = GraphSnapshot.model_validate(body)
    assert snap.status == "ready"
    assert snap.code is None
    assert snap.candidate is not None
    assert snap.candidate.id == cand_id
    assert len(snap.jobs) == CAP_JOBS
    assert [j.id for j in snap.jobs] == sorted(j.id for j in snap.jobs)
    assert len(snap.skills) == CAP_SKILLS
    assert [s.canonical_name for s in snap.skills] == sorted(
        s.canonical_name for s in snap.skills
    )
    assert len(snap.edges) == CAP_EDGES
    assert snap.nodes_truncated is True
    assert snap.edges_truncated is True
    assert snap.omitted_node_count > 0
    assert snap.omitted_edge_count > 0
    edge_keys = [(e.type, e.source_id, e.target_id) for e in snap.edges]
    assert edge_keys == sorted(edge_keys)
    for edge in snap.edges:
        assert edge.type in {
            "HAS_SKILL",
            "REQUIRES",
            "PREFERS",
            "RELATED_TO",
        }
    assert fake.write_queries == []
    _assert_no_forbidden(body)
    # Schema forbids undeclared fields.
    assert set(body.keys()) == {
        "status",
        "code",
        "summary",
        "rebuild_instruction",
        "cv",
        "sections",
        "entries",
        "candidate",
        "jobs",
        "skills",
        "edges",
        "nodes_truncated",
        "edges_truncated",
        "omitted_node_count",
        "omitted_edge_count",
        "checked_at",
    }
    # Existing D3 fields remain present and typed.
    assert body["cv"] is None or isinstance(body["cv"], dict)
    assert isinstance(body["sections"], list)
    assert isinstance(body["entries"], list)
