"""Integration tests for attachment repositories and CV upload API (Plan 4).

Repository primitives (01C) plus ``POST /api/attachments/cv`` bounded upload,
exact-hash lifecycle, interrupt guard, and cleanup (02A). Uses migrated
temporary SQLite and temporary FILES_DIR.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.db.session import build_async_engine, get_session_factory
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import profiles as profile_repo
from app.repositories.attachments import (
    AttachmentNotFoundError,
    AttachmentRepositoryError,
    InvalidAttachmentTransitionError,
)
from app.schemas.attachments import CvUploadResponse
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from tests.support.db_migration import (
    cleanup_isolated_sqlite,
    run_async,
    session_factory,
)
from tests.support.health import (
    FakeDriver,
    health_client,
    install_fake_driver,
    prepare_health_env,
    public_api_routes,
)


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    """Migrated isolated SQLite file (Alembic head + singleton seeds)."""
    return migrated_sqlite


async def _create_staged(
    session: object,
    *,
    file_hash: str = "hash-a",
    storage_path: str = "a/b/c.pdf",
    page_count: int | None = None,
    original_name: str = "cv.pdf",
    size_bytes: int = 100,
) -> Attachment:
    return await att_repo.create_staged(
        session,  # type: ignore[arg-type]
        file_hash=file_hash,
        original_name=original_name,
        size_bytes=size_bytes,
        storage_path=storage_path,
        page_count=page_count,
    )


# ---------------------------------------------------------------------------
# Hash / state reads
# ---------------------------------------------------------------------------


def test_create_staged_and_exact_hash_lookup(db_path: Path) -> None:
    """Exact file_hash lookup returns the staged row; missing hash is None."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session,
                    file_hash="abc123",
                    storage_path="uu/id.pdf",
                    page_count=2,
                )
                assert row.state == ATTACHMENT_STATE_STAGED
                assert row.mime_type == ATTACHMENT_MIME_TYPE_PDF
                assert row.failure_code is None
                assert row.id
                await session.commit()
                att_id = row.id

            async with factory() as session:
                found = await att_repo.get_by_file_hash(session, "abc123")
                assert found is not None
                assert found.id == att_id
                assert found.file_hash == "abc123"
                assert found.state == ATTACHMENT_STATE_STAGED

                missing = await att_repo.get_by_file_hash(session, "no-such-hash")
                assert missing is None

                by_id = await att_repo.get_by_id(session, att_id)
                assert by_id is not None
                assert by_id.file_hash == "abc123"

                assert await att_repo.get_by_id(session, new_uuid()) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_get_active_none_then_one(db_path: Path) -> None:
    """Active read is None until a staged row is promoted."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                assert await att_repo.get_active(session) is None
                staged = await _create_staged(
                    session, file_hash="h1", storage_path="p1.pdf", page_count=1
                )
                await session.commit()
                staged_id = staged.id

            async with factory() as session:
                active = await att_repo.mark_active(session, staged_id)
                assert active.state == ATTACHMENT_STATE_ACTIVE
                assert active.page_count == 1
                await session.commit()

            async with factory() as session:
                found = await att_repo.get_active(session)
                assert found is not None
                assert found.id == staged_id
                assert found.state == ATTACHMENT_STATE_ACTIVE
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------


def test_staged_to_active_and_failed_to_staged_retry(db_path: Path) -> None:
    """Allowed path: staged → failed → staged (retry) then staged → active."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session, file_hash="hf", storage_path="fail.pdf"
                )
                await session.commit()
                att_id = row.id

            async with factory() as session:
                failed = await att_repo.mark_failed(
                    session, att_id, failure_code="NO_EXTRACTABLE_TEXT"
                )
                assert failed.state == ATTACHMENT_STATE_FAILED
                assert failed.failure_code == "NO_EXTRACTABLE_TEXT"
                assert failed.updated_at.tzinfo is not None

                retried = await att_repo.retry_as_staged(session, att_id)
                assert retried.state == ATTACHMENT_STATE_STAGED
                assert retried.failure_code is None

                # After retry, can fail again then activate with page_count.
                await att_repo.mark_failed(
                    session, att_id, failure_code="PARSE_ERROR"
                )
                await att_repo.retry_as_staged(session, att_id)
                activated = await att_repo.mark_active(
                    session, att_id, page_count=4
                )
                assert activated.state == ATTACHMENT_STATE_ACTIVE
                assert activated.page_count == 4
                assert activated.failure_code is None
                await session.commit()

            # Separate path: page_count already present on create → active.
            async with factory() as session:
                only = await _create_staged(
                    session,
                    file_hash="only",
                    storage_path="only.pdf",
                    page_count=2,
                )
                # Replace prior active: delete first (no profile FK yet).
                prior = await att_repo.get_active(session)
                assert prior is not None
                await att_repo.delete(session, prior.id)
                done = await att_repo.mark_active(session, only.id)
                assert done.state == ATTACHMENT_STATE_ACTIVE
                assert done.page_count == 2
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_mark_active_requires_page_count(db_path: Path) -> None:
    """Active transition without page_count is rejected; state stays staged."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session, file_hash="npc", storage_path="npc.pdf"
                )
                assert row.page_count is None
                with pytest.raises(AttachmentRepositoryError):
                    await att_repo.mark_active(session, row.id)
                reloaded = await att_repo.get_by_id(session, row.id)
                assert reloaded is not None
                assert reloaded.state == ATTACHMENT_STATE_STAGED
                assert reloaded.page_count is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_mark_failed_requires_failure_code(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session, file_hash="nfc", storage_path="nfc.pdf"
                )
                with pytest.raises(AttachmentRepositoryError):
                    await att_repo.mark_failed(session, row.id, failure_code="")
                with pytest.raises(AttachmentRepositoryError):
                    await att_repo.mark_failed(
                        session, row.id, failure_code="   "
                    )
                reloaded = await att_repo.get_by_id(session, row.id)
                assert reloaded is not None
                assert reloaded.state == ATTACHMENT_STATE_STAGED
                assert reloaded.failure_code is None
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Invalid transitions — no mutation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("setup", "action"),
    [
        ("active", "mark_active"),
        ("active", "mark_failed"),
        ("active", "retry_as_staged"),
        ("failed", "mark_active"),
        ("failed", "mark_failed"),
        ("staged", "retry_as_staged"),
    ],
)
def test_forbidden_attachment_transitions(
    db_path: Path, setup: str, action: str
) -> None:
    """Skipped, backward, and terminal transitions raise without mutating."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session,
                    file_hash=f"h-{setup}-{action}",
                    storage_path=f"p-{setup}-{action}.pdf",
                    page_count=1 if setup == "active" else None,
                )
                if setup == "active":
                    await att_repo.mark_active(session, row.id)
                elif setup == "failed":
                    await att_repo.mark_failed(
                        session, row.id, failure_code="SEED"
                    )
                await session.commit()
                att_id = row.id
                expected_state = {
                    "active": ATTACHMENT_STATE_ACTIVE,
                    "failed": ATTACHMENT_STATE_FAILED,
                    "staged": ATTACHMENT_STATE_STAGED,
                }[setup]

            async with factory() as session:
                before = await att_repo.get_by_id(session, att_id)
                assert before is not None
                before_state = before.state
                before_code = before.failure_code
                before_pages = before.page_count
                before_updated = before.updated_at

                with pytest.raises(InvalidAttachmentTransitionError):
                    if action == "mark_active":
                        await att_repo.mark_active(
                            session, att_id, page_count=2
                        )
                    elif action == "mark_failed":
                        await att_repo.mark_failed(
                            session, att_id, failure_code="X"
                        )
                    elif action == "retry_as_staged":
                        await att_repo.retry_as_staged(session, att_id)

                after = await att_repo.get_by_id(session, att_id)
                assert after is not None
                assert after.state == before_state == expected_state
                assert after.failure_code == before_code
                assert after.page_count == before_pages
                assert after.updated_at == before_updated
        finally:
            await engine.dispose()

    run_async(_body())


def test_missing_attachment_transition_raises(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                missing = new_uuid()
                with pytest.raises(AttachmentNotFoundError):
                    await att_repo.mark_active(session, missing, page_count=1)
                with pytest.raises(AttachmentNotFoundError):
                    await att_repo.mark_failed(
                        session, missing, failure_code="X"
                    )
                with pytest.raises(AttachmentNotFoundError):
                    await att_repo.retry_as_staged(session, missing)
                with pytest.raises(AttachmentNotFoundError):
                    await att_repo.delete(session, missing)
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Delete, timestamps, constraints
# ---------------------------------------------------------------------------


def test_delete_attachment_row(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session, file_hash="del", storage_path="del.pdf"
                )
                await session.commit()
                att_id = row.id

            async with factory() as session:
                await att_repo.delete(session, att_id)
                await session.commit()

            async with factory() as session:
                assert await att_repo.get_by_id(session, att_id) is None
                count = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM attachments")
                    )
                ).scalar_one()
                assert int(count) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_updated_at_advances_on_transition(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session, file_hash="ts", storage_path="ts.pdf", page_count=1
                )
                # Pin created/updated then transition later.
                past = datetime(2020, 1, 1, tzinfo=UTC)
                row.created_at = past
                row.updated_at = past
                await session.flush()
                await session.commit()
                att_id = row.id

            async with factory() as session:
                active = await att_repo.mark_active(session, att_id)
                assert active.updated_at > past
                assert active.updated_at.tzinfo is not None
                # created_at preserved
                assert active.created_at == past or (
                    active.created_at.replace(tzinfo=UTC) == past
                    if active.created_at.tzinfo is None
                    else active.created_at == past
                )
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_duplicate_hash_and_second_active_constraints(db_path: Path) -> None:
    """Unique file_hash and single-active partial unique surface IntegrityError."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _create_staged(
                    session, file_hash="dup", storage_path="d1.pdf"
                )
                await session.commit()

            async with factory() as session:
                with pytest.raises(IntegrityError):
                    await _create_staged(
                        session, file_hash="dup", storage_path="d2.pdf"
                    )
                    await session.commit()
                await session.rollback()

            async with factory() as session:
                a1 = await _create_staged(
                    session,
                    file_hash="a1",
                    storage_path="a1.pdf",
                    page_count=1,
                )
                a2 = await _create_staged(
                    session,
                    file_hash="a2",
                    storage_path="a2.pdf",
                    page_count=1,
                )
                await att_repo.mark_active(session, a1.id)
                await session.commit()
                a2_id = a2.id

            async with factory() as session:
                with pytest.raises(IntegrityError):
                    await att_repo.mark_active(session, a2_id)
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    run_async(_body())


def test_repositories_do_not_commit(db_path: Path) -> None:
    """Flush-only mutations remain uncommitted until the caller commits."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session, file_hash="nc", storage_path="nc.pdf"
                )
                att_id = row.id
                # Do not commit; open a separate connection and assert empty.
                async with factory() as other:
                    n = (
                        await other.execute(
                            text("SELECT COUNT(*) FROM attachments")
                        )
                    ).scalar_one()
                    assert int(n) == 0
                await session.rollback()

            async with factory() as session:
                assert await att_repo.get_by_id(session, att_id) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_repository_source_has_no_commit_or_io() -> None:
    """Static evidence: no session finalization, storage, or provider calls."""
    src = inspect.getsource(att_repo)
    assert "session.commit" not in src
    assert "session.rollback" not in src
    assert "session_scope" not in src
    assert "get_session_factory" not in src
    assert "create_async_engine" not in src
    assert "httpx" not in src
    assert "shopaikey" not in src.lower()
    assert "neo4j" not in src.lower()
    assert "FILES_DIR" not in src
    assert "write_bytes" not in src
    assert "create_all" not in src

    # Transition map uses only existing state constants.
    assert "ATTACHMENT_STATE_STAGED" in src
    assert "ATTACHMENT_STATE_ACTIVE" in src
    assert "ATTACHMENT_STATE_FAILED" in src
    # No invented states.
    assert "processing" not in src
    assert "deleted" not in src


def test_create_rejects_invalid_scalars(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(AttachmentRepositoryError):
                    await att_repo.create_staged(
                        session,
                        file_hash="",
                        original_name="x.pdf",
                        size_bytes=1,
                        storage_path="p.pdf",
                    )
                with pytest.raises(AttachmentRepositoryError):
                    await att_repo.create_staged(
                        session,
                        file_hash="h",
                        original_name="x.pdf",
                        size_bytes=0,
                        storage_path="p.pdf",
                    )
                with pytest.raises(AttachmentRepositoryError):
                    await att_repo.create_staged(
                        session,
                        file_hash="h",
                        original_name="x.pdf",
                        size_bytes=1,
                        storage_path="p.pdf",
                        page_count=0,
                    )
        finally:
            await engine.dispose()

    run_async(_body())


def test_uuid_ids_and_reload(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session, file_hash="uuid-h", storage_path="uuid.pdf"
                )
                # UUID v4 lowercase
                assert len(row.id) == 36
                assert row.id == row.id.lower()
                await session.commit()
                att_id = row.id

            async with factory() as session:
                reloaded = (
                    await session.execute(
                        select(Attachment).where(Attachment.id == att_id)
                    )
                ).scalar_one()
                assert reloaded.file_hash == "uuid-h"
                assert reloaded.state == ATTACHMENT_STATE_STAGED
        finally:
            await engine.dispose()

    run_async(_body())


def test_updated_at_not_advanced_when_transition_rejected(
    db_path: Path,
) -> None:
    """Invalid transition leaves updated_at unchanged after prior success."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await _create_staged(
                    session,
                    file_hash="rej-ts",
                    storage_path="rej-ts.pdf",
                    page_count=1,
                )
                active = await att_repo.mark_active(session, row.id)
                stamp = active.updated_at
                await session.commit()
                att_id = row.id

            async with factory() as session:
                with pytest.raises(InvalidAttachmentTransitionError):
                    await att_repo.mark_failed(
                        session, att_id, failure_code="NOPE"
                    )
                again = await att_repo.get_by_id(session, att_id)
                assert again is not None
                assert again.state == ATTACHMENT_STATE_ACTIVE
                # SQLite may drop tzinfo on reload; compare UTC-normalized values.
                again_utc = (
                    again.updated_at
                    if again.updated_at.tzinfo is not None
                    else again.updated_at.replace(tzinfo=UTC)
                )
                stamp_utc = (
                    stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)
                )
                assert again_utc == stamp_utc
        finally:
            await engine.dispose()

    run_async(_body())

# ---------------------------------------------------------------------------
# POST /api/attachments/cv — bounded upload / exact-hash lifecycle (02A)
# ---------------------------------------------------------------------------

CV_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cv"
DIGITAL_CV = CV_FIXTURES / "digital_cv_01.pdf"
DIGITAL_CV_B = CV_FIXTURES / "digital_cv_02.pdf"


def _minimal_pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def cv_api_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Path, FakeDriver]]:
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = install_fake_driver(monkeypatch)
    yield db_path, files_dir, fake
    cleanup_isolated_sqlite()


def _upload(
    client: TestClient,
    data: bytes,
    *,
    filename: str = "resume.pdf",
    content_type: str = "application/pdf",
) -> Any:
    return client.post(
        "/api/attachments/cv",
        files={"file": (filename, data, content_type)},
    )


def _attachment_count() -> int:
    async def _body() -> int:
        factory = get_session_factory()
        async with factory() as session:
            n = (
                await session.execute(select(func.count()).select_from(Attachment))
            ).scalar_one()
            return int(n)

    return run_async(_body())


def _message_count() -> int:
    async def _body() -> int:
        from app.db.models.chat import ChatMessage

        factory = get_session_factory()
        async with factory() as session:
            n = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            return int(n)

    return run_async(_body())


def test_upload_new_digital_cv_stages_row_and_uuid_file(
    cv_api_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db_path, files_dir, _fake = cv_api_env
    payload = DIGITAL_CV.read_bytes()
    with health_client() as client:
        response = _upload(client, payload, filename="My CV (final).pdf")
    assert response.status_code == 200, response.text
    body = CvUploadResponse.model_validate(response.json())
    assert body.outcome == "new"
    assert body.attachment.state == ATTACHMENT_STATE_STAGED
    assert body.attachment.mime_type == ATTACHMENT_MIME_TYPE_PDF
    assert body.attachment.size_bytes == len(payload)
    assert body.attachment.page_count == 1
    assert body.attachment.failure_code is None
    assert body.attachment.original_name == "My CV (final).pdf"
    assert "storage_path" not in response.json()["attachment"]
    assert "storage_path" not in response.text
    final = files_dir / body.attachment.id
    assert final.is_file()
    assert final.read_bytes() == payload
    leftovers = [p.name for p in files_dir.iterdir() if p.name.startswith(".upload.")]
    assert leftovers == []
    assert _attachment_count() == 1


def test_upload_rejects_interrupted_before_persist(
    cv_api_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, files_dir, _fake = cv_api_env

    async def _seed_interrupted() -> None:
        factory = get_session_factory()
        async with factory() as session:
            user = await messages_repo.insert_message(
                session, role="user", content="approve please"
            )
            run = await runs_repo.create_run(session, user_message_id=user.id)
            await runs_repo.interrupt_run(
                session,
                run.id,
                pending_approval_json={
                    "kind": "profile_commit",
                    "allowed_actions": ["save_profile", "request_changes"],
                    "card": {},
                },
            )
            await session.commit()

    run_async(_seed_interrupted())
    before_msg = _message_count()
    before_att = _attachment_count()
    before_files = list(files_dir.iterdir()) if files_dir.exists() else []
    payload = DIGITAL_CV.read_bytes()
    with health_client() as client:
        response = _upload(client, payload)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "APPROVAL_ACTION_REQUIRED"
    assert _message_count() == before_msg
    assert _attachment_count() == before_att
    after_files = list(files_dir.iterdir()) if files_dir.exists() else []
    assert after_files == before_files


def test_upload_rejects_invalid_mime_empty_magic_malformed_pages(
    cv_api_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, files_dir, _fake = cv_api_env
    with health_client() as client:
        r = _upload(client, DIGITAL_CV.read_bytes(), content_type="text/plain")
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "INVALID_MIME"

        r = _upload(client, b"not-a-pdf-at-all", content_type="application/pdf")
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "INVALID_PDF_MAGIC"

        r = _upload(client, b"", content_type="application/pdf")
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "EMPTY_UPLOAD"

        r = _upload(
            client,
            b"%PDF-1.4\nthis is not a valid pdf structure",
            content_type="application/pdf",
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "MALFORMED_PDF"

        r = _upload(client, _minimal_pdf_bytes(11), content_type="application/pdf")
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "PDF_TOO_MANY_PAGES"

    assert _attachment_count() == 0
    if files_dir.exists():
        uuidish = [
            p
            for p in files_dir.iterdir()
            if len(p.name) == 36 and p.name.count("-") == 4
        ]
        assert uuidish == []
        temps = [
            p
            for p in files_dir.iterdir()
            if ".upload." in p.name or p.name.endswith(".tmp")
        ]
        assert temps == []


def test_upload_rejects_oversized(
    cv_api_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, files_dir, _fake = cv_api_env
    monkeypatch.setenv("MAX_PDF_SIZE_MB", "1")
    from app.core.settings import clear_settings_cache

    clear_settings_cache()
    pad = b"%PDF-1.4\n" + (b"x" * (1024 * 1024 + 100))
    with health_client() as client:
        r = _upload(client, pad, content_type="application/pdf")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "PDF_TOO_LARGE"
    assert _attachment_count() == 0
    if files_dir.exists():
        assert list(files_dir.iterdir()) == []


def test_exact_hash_active_staged_failed_and_new(
    cv_api_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, files_dir, _fake = cv_api_env
    payload_a = DIGITAL_CV.read_bytes()
    payload_b = DIGITAL_CV_B.read_bytes()
    assert payload_a != payload_b

    with health_client() as client:
        r1 = _upload(client, payload_a, filename="a.pdf")
        assert r1.status_code == 200
        first = CvUploadResponse.model_validate(r1.json())
        assert first.outcome == "new"
        att_a = first.attachment.id

        r2 = _upload(client, payload_a, filename="a-again.pdf")
        assert r2.status_code == 200
        second = CvUploadResponse.model_validate(r2.json())
        assert second.outcome == "existing_staged"
        assert second.attachment.id == att_a
        assert _attachment_count() == 1

        r3 = _upload(client, payload_b, filename="b.pdf")
        assert r3.status_code == 200
        third = CvUploadResponse.model_validate(r3.json())
        assert third.outcome == "new"
        att_b = third.attachment.id
        assert att_b != att_a
        assert _attachment_count() == 2
        assert (files_dir / att_a).is_file()
        assert (files_dir / att_b).is_file()

    async def _fail_a() -> None:
        factory = get_session_factory()
        async with factory() as session:
            await att_repo.mark_failed(
                session, att_a, failure_code="NO_EXTRACTABLE_TEXT"
            )
            await session.commit()

    run_async(_fail_a())

    with health_client() as client:
        r4 = _upload(client, payload_a, filename="a-retry.pdf")
        assert r4.status_code == 200
        fourth = CvUploadResponse.model_validate(r4.json())
        assert fourth.outcome == "retry"
        assert fourth.attachment.id == att_a
        assert fourth.attachment.state == ATTACHMENT_STATE_STAGED
        assert fourth.attachment.failure_code is None
        assert _attachment_count() == 2

    async def _activate_b() -> None:
        factory = get_session_factory()
        async with factory() as session:
            await att_repo.mark_active(session, att_b, page_count=1)
            await profile_repo.upsert_active_profile(
                session,
                active_attachment_id=att_b,
                profile_json={
                    "summary": "Experienced engineer",
                    "current_title": "Senior Engineer",
                    "total_experience_years": 5.0,
                    "skills": [],
                    "experiences": [],
                    "education": [],
                    "languages": [],
                    "extraction_confidence": 0.9,
                },
            )
            await session.commit()

    run_async(_activate_b())

    with health_client() as client:
        r5 = _upload(client, payload_b, filename="b-active.pdf")
        assert r5.status_code == 200
        fifth = CvUploadResponse.model_validate(r5.json())
        assert fifth.outcome == "existing_active"
        assert fifth.attachment.id == att_b
        assert fifth.attachment.state == ATTACHMENT_STATE_ACTIVE
        assert fifth.profile is not None
        assert fifth.profile.present is True
        assert fifth.profile.current_title == "Senior Engineer"
        assert _attachment_count() == 2


def test_upload_filename_cannot_escape_or_inject(
    cv_api_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db, files_dir, _fake = cv_api_env
    evil = "../../etc/passwd\r\nX-Injected: yes.pdf"
    with health_client() as client:
        r = _upload(client, DIGITAL_CV.read_bytes(), filename=evil)
    assert r.status_code == 200
    body = CvUploadResponse.model_validate(r.json())
    assert ".." not in body.attachment.original_name
    assert "/" not in body.attachment.original_name
    assert "\\" not in body.attachment.original_name
    assert "\r" not in body.attachment.original_name
    assert "\n" not in body.attachment.original_name
    assert (files_dir / body.attachment.id).is_file()
    assert not (files_dir / "etc").exists()


def test_upload_row_failure_cleans_uuid_file(
    cv_api_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, files_dir, _fake = cv_api_env

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated row insert failure")

    import app.services.cv_upload as cv_mod

    monkeypatch.setattr(cv_mod.att_repo, "create_staged", boom)

    with health_client() as client:
        # Uncaught service failure surfaces as server exception after cleanup.
        with pytest.raises(RuntimeError, match="simulated row insert failure"):
            _upload(client, DIGITAL_CV.read_bytes())

    assert _attachment_count() == 0
    if files_dir.exists():
        uuid_files = [
            p for p in files_dir.iterdir() if len(p.name) == 36 and "-" in p.name
        ]
        assert uuid_files == []


def test_route_is_transport_thin_and_registered(
    cv_api_env: tuple[Path, Path, FakeDriver],
) -> None:
    src = (
        Path(__file__).resolve().parents[2] / "app" / "api" / "attachments.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "PdfReader",
        "sha256",
        "neo4j",
        "ChatOpenAI",
        "StateGraph",
        "AsyncSqliteSaver",
        "upsert_active_profile",
        "write_bytes",
    ):
        assert forbidden not in src, f"route leaked {forbidden!r}"
    assert "upload_cv_from_upload_file" in src
    assert "UploadFile" in src

    with health_client() as client:
        routes = public_api_routes(client.app)
    assert ("POST", "/api/attachments/cv") in routes


def test_sanitize_original_name_unit() -> None:
    from app.services.cv_upload import sanitize_original_name

    assert sanitize_original_name(None) == "cv.pdf"
    assert sanitize_original_name("") == "cv.pdf"
    assert sanitize_original_name("../../x.pdf") == "x.pdf"
    assert "\n" not in sanitize_original_name("a\r\nb.pdf")
