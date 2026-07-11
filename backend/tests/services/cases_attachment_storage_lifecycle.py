"""Stage / promote / open / delete lifecycle and collision tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from app.services.attachment_storage import (
    ACTIVE_AREA,
    STAGED_AREA,
    AttachmentStorageCollisionError,
    AttachmentStorageNotFoundError,
    AttachmentStorageStateError,
    FilesystemAttachmentStorage,
    StoredFile,
    iter_byte_chunks,
    parse_service_storage_path,
)
from tests.services.attachment_helpers import assert_no_abs_disclosure, read_all


@pytest.mark.asyncio
async def test_stage_open_round_trip_and_chunking(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files", chunk_size=8)
    attachment_id = uuid4()
    payload = b"0123456789abcdef"
    stored = await storage.stage(
        attachment_id, iter_byte_chunks(payload, chunk_size=8)
    )
    assert isinstance(stored, StoredFile)
    assert stored.storage_path == f"{STAGED_AREA}/{attachment_id}"
    assert stored.size_bytes == len(payload)
    assert await read_all(storage, stored.storage_path) == payload


@pytest.mark.asyncio
async def test_promote_returns_active_path_and_moves_bytes(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"promote-me"))
    active = await storage.promote(f"{STAGED_AREA}/{attachment_id}")
    assert active == f"{ACTIVE_AREA}/{attachment_id}"
    assert await read_all(storage, active) == b"promote-me"
    with pytest.raises(AttachmentStorageNotFoundError):
        await storage.open(f"{STAGED_AREA}/{attachment_id}")


@pytest.mark.asyncio
async def test_delete_is_idempotent_and_missing_open_raises(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    stored = await storage.stage(attachment_id, iter_byte_chunks(b"bye"))
    await storage.delete(stored.storage_path)
    await storage.delete(stored.storage_path)
    with pytest.raises(AttachmentStorageNotFoundError) as ei:
        await storage.open(stored.storage_path)
    assert_no_abs_disclosure(ei.value, tmp_path / "files")


@pytest.mark.asyncio
async def test_promote_non_staged_and_missing(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"x"))
    active = await storage.promote(f"{STAGED_AREA}/{attachment_id}")
    with pytest.raises(AttachmentStorageStateError):
        await storage.promote(active)
    missing = uuid4()
    with pytest.raises(AttachmentStorageNotFoundError):
        await storage.promote(f"{STAGED_AREA}/{missing}")


@pytest.mark.asyncio
async def test_interrupted_stage_cleans_partial_and_leaves_no_promoted(
    tmp_path: Path,
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()

    async def boom() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("inject-fail")

    with pytest.raises(RuntimeError):
        await storage.stage(attachment_id, boom())
    staged = tmp_path / "files" / STAGED_AREA
    assert list(staged.glob(f"{attachment_id}*")) == []
    assert list((tmp_path / "files" / ACTIVE_AREA).iterdir()) == []


@pytest.mark.asyncio
async def test_cancelled_stage_cleans_partial(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    gate = asyncio.Event()

    async def blocked() -> AsyncIterator[bytes]:
        yield b"x"
        await gate.wait()
        yield b"y"

    task = asyncio.create_task(storage.stage(attachment_id, blocked()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    staged = tmp_path / "files" / STAGED_AREA
    assert list(staged.glob(f"{attachment_id}*")) == []


@pytest.mark.asyncio
async def test_empty_content_stage_round_trip(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    stored = await storage.stage(attachment_id, iter_byte_chunks(b""))
    assert stored.size_bytes == 0
    assert await read_all(storage, stored.storage_path) == b""


@pytest.mark.asyncio
async def test_empty_chunks_in_stream_are_skipped_predictably(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()

    async def with_empties() -> AsyncIterator[bytes]:
        yield b""
        yield b"ab"
        yield b""
        yield b"cd"
        yield b""

    stored = await storage.stage(attachment_id, with_empties())
    assert stored.size_bytes == 4
    assert await read_all(storage, stored.storage_path) == b"abcd"


@pytest.mark.asyncio
async def test_stage_never_accepts_user_path_authority(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    stored = await storage.stage(attachment_id, iter_byte_chunks(b"abc"))
    assert stored.storage_path == f"{STAGED_AREA}/{attachment_id}"
    assert Path(stored.storage_path).parts == (STAGED_AREA, str(attachment_id))


@pytest.mark.asyncio
async def test_all_stored_paths_resolve_under_files_dir(tmp_path: Path) -> None:
    root = (tmp_path / "files").resolve()
    storage = FilesystemAttachmentStorage(root)
    ids = [uuid4() for _ in range(3)]
    for i, attachment_id in enumerate(ids):
        stored = await storage.stage(
            attachment_id, iter_byte_chunks(f"body-{i}".encode())
        )
        area, name = parse_service_storage_path(stored.storage_path)
        resolved = (root / area / name).resolve()
        assert resolved.is_relative_to(root)
        if i == 0:
            active = await storage.promote(stored.storage_path)
            a_area, a_name = parse_service_storage_path(active)
            assert (root / a_area / a_name).resolve().is_relative_to(root)


@pytest.mark.asyncio
async def test_repeated_stage_collision_preserves_existing_bytes(
    tmp_path: Path,
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    first = await storage.stage(attachment_id, iter_byte_chunks(b"first-bytes"))
    staged_path = tmp_path / "files" / STAGED_AREA / str(attachment_id)
    assert staged_path.read_bytes() == b"first-bytes"

    with pytest.raises(AttachmentStorageCollisionError) as ei:
        await storage.stage(attachment_id, iter_byte_chunks(b"second-bytes"))
    assert_no_abs_disclosure(ei.value, tmp_path / "files")
    assert staged_path.read_bytes() == b"first-bytes"
    assert first.storage_path == f"{STAGED_AREA}/{attachment_id}"
    assert await read_all(storage, first.storage_path) == b"first-bytes"


@pytest.mark.asyncio
async def test_promote_collision_preserves_active_and_staged(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"active-original"))
    active = await storage.promote(f"{STAGED_AREA}/{attachment_id}")
    active_path = tmp_path / "files" / ACTIVE_AREA / str(attachment_id)
    assert active_path.read_bytes() == b"active-original"

    await storage.stage(attachment_id, iter_byte_chunks(b"staged-second"))
    staged_path = tmp_path / "files" / STAGED_AREA / str(attachment_id)
    assert staged_path.read_bytes() == b"staged-second"

    with pytest.raises(AttachmentStorageCollisionError):
        await storage.promote(f"{STAGED_AREA}/{attachment_id}")

    assert active_path.read_bytes() == b"active-original"
    assert staged_path.read_bytes() == b"staged-second"
    assert await read_all(storage, active) == b"active-original"


@pytest.mark.asyncio
async def test_concurrent_stage_collision_one_winner(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    gate = asyncio.Event()

    async def delayed(payload: bytes) -> AsyncIterator[bytes]:
        await gate.wait()
        yield payload

    t1 = asyncio.create_task(storage.stage(attachment_id, delayed(b"writer-one")))
    t2 = asyncio.create_task(storage.stage(attachment_id, delayed(b"writer-two")))
    await asyncio.sleep(0.05)
    gate.set()
    results = await asyncio.gather(t1, t2, return_exceptions=True)

    successes = [r for r in results if isinstance(r, StoredFile)]
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], AttachmentStorageCollisionError)
    body = (tmp_path / "files" / STAGED_AREA / str(attachment_id)).read_bytes()
    assert body in {b"writer-one", b"writer-two"}
    assert await read_all(storage, successes[0].storage_path) == body
