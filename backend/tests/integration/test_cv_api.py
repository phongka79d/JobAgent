"""Integration tests for attachment repository primitives (pre-API layer).

Uses a migrated temporary SQLite file (Alembic head). Covers exact file-hash
lookup, allowed attachment state transitions, invalid transitions that leave
state untouched, missing rows, UTC timestamp updates, and constraint-visible
failures. Higher CV upload routes/services are out of scope for task 01C.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.db.session import build_async_engine
from app.repositories import attachments as att_repo
from app.repositories.attachments import (
    AttachmentNotFoundError,
    AttachmentRepositoryError,
    InvalidAttachmentTransitionError,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from tests.support.db_migration import run_async, session_factory


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
