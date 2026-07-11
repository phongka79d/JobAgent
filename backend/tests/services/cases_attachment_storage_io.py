"""Short-write, invalid-chunk, fsync/write/close, and OS-error sanitization tests."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from app.services.attachment_storage import (
    PARTIAL_SUFFIX,
    STAGED_AREA,
    AttachmentStorageError,
    AttachmentStorageInvalidContentError,
    AttachmentStorageIOError,
    AttachmentStorageNotFoundError,
    FilesystemAttachmentStorage,
    iter_byte_chunks,
)
from tests.services.attachment_helpers import assert_no_abs_disclosure, read_all


@pytest.mark.asyncio
async def test_short_writes_are_looped_until_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    original_write = os.write

    def short_write(fd: int, data: bytes | memoryview) -> int:
        view = memoryview(data) if not isinstance(data, memoryview) else data
        if len(view) <= 1:
            return original_write(fd, view)
        return original_write(fd, view[:1])

    monkeypatch.setattr(os, "write", short_write)
    payload = b"abcdef"
    stored = await storage.stage(attachment_id, iter_byte_chunks(payload, chunk_size=6))
    assert stored.size_bytes == 6
    assert await read_all(storage, stored.storage_path) == payload


@pytest.mark.asyncio
async def test_zero_write_raises_sanitized_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()

    def zero_write(fd: int, data: bytes | memoryview) -> int:
        return 0

    monkeypatch.setattr(os, "write", zero_write)
    with pytest.raises(AttachmentStorageIOError) as ei:
        await storage.stage(attachment_id, iter_byte_chunks(b"data"))
    assert_no_abs_disclosure(ei.value, tmp_path / "files")
    assert not (tmp_path / "files" / STAGED_AREA / str(attachment_id)).exists()


@pytest.mark.asyncio
async def test_invalid_chunk_type_raises_domain_error(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()

    async def bad_chunks() -> AsyncIterator[object]:
        yield b"ok"
        yield "not-bytes"  # type: ignore[misc]

    with pytest.raises(AttachmentStorageInvalidContentError) as ei:
        await storage.stage(attachment_id, bad_chunks())  # type: ignore[arg-type]
    assert_no_abs_disclosure(ei.value, tmp_path / "files")
    assert not (tmp_path / "files" / STAGED_AREA / str(attachment_id)).exists()
    partials = list((tmp_path / "files" / STAGED_AREA).glob(f"*{PARTIAL_SUFFIX}"))
    assert partials == []


@pytest.mark.asyncio
async def test_fsync_failure_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    files_dir = tmp_path / "files"

    def boom_fsync(fd: int) -> None:
        raise OSError(5, "I/O error", str(files_dir / "partial.partial"))

    monkeypatch.setattr(os, "fsync", boom_fsync)
    with pytest.raises(AttachmentStorageIOError) as ei:
        await storage.stage(attachment_id, iter_byte_chunks(b"data"))
    assert_no_abs_disclosure(ei.value, files_dir)
    assert ei.value.__cause__ is None
    assert ei.value.__context__ is None
    assert not (files_dir / STAGED_AREA / str(attachment_id)).exists()


@pytest.mark.asyncio
async def test_write_oserror_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    files_dir = tmp_path / "files"

    def boom_write(fd: int, data: bytes | memoryview) -> int:
        raise OSError(28, "No space left on device", str(files_dir / "x.partial"))

    monkeypatch.setattr(os, "write", boom_write)
    with pytest.raises(AttachmentStorageIOError) as ei:
        await storage.stage(attachment_id, iter_byte_chunks(b"data"))
    assert_no_abs_disclosure(ei.value, files_dir)
    assert ei.value.__cause__ is None
    assert ei.value.__context__ is None


@pytest.mark.asyncio
async def test_os_error_on_stage_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    files_dir = tmp_path / "files"

    if sys.platform == "win32":
        from app.services import attachment_storage_windows as win_mod

        def boom_create(path: str) -> int:
            raise PermissionError(13, "Permission denied", str(files_dir / "blocked"))

        monkeypatch.setattr(win_mod, "create_new_file_handle", boom_create)
    else:

        def boom_open(path, flags, mode=0o777):  # noqa: ANN001
            raise PermissionError(13, "Permission denied", str(files_dir / "blocked"))

        monkeypatch.setattr(os, "open", boom_open)

    with pytest.raises(AttachmentStorageError) as ei:
        await storage.stage(attachment_id, iter_byte_chunks(b"x"))
    assert_no_abs_disclosure(ei.value, files_dir)
    assert str(files_dir) not in str(ei.value)
    assert ei.value.__cause__ is None


@pytest.mark.asyncio
async def test_delete_permission_failure_raises_not_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    stored = await storage.stage(attachment_id, iter_byte_chunks(b"locked"))
    target = tmp_path / "files" / STAGED_AREA / str(attachment_id)

    if sys.platform == "win32":
        from app.services import attachment_storage_windows_mutate as win_mut

        def boom_dispose(handle: int) -> None:
            raise PermissionError(13, "Permission denied", str(target))

        monkeypatch.setattr(win_mut, "dispose_delete", boom_dispose)
    else:

        def boom_unlink(path):  # noqa: ANN001
            raise PermissionError(13, "Permission denied", str(target))

        monkeypatch.setattr(os, "unlink", boom_unlink)

    with pytest.raises(AttachmentStorageError) as ei:
        await storage.delete(stored.storage_path)
    assert_no_abs_disclosure(ei.value, target, tmp_path / "files")
    assert target.exists()


@pytest.mark.asyncio
async def test_deferred_open_removal_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the leaf vanishes between validation and open, raise sanitized not-found."""
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    stored = await storage.stage(attachment_id, iter_byte_chunks(b"gone-soon"))
    target = tmp_path / "files" / STAGED_AREA / str(attachment_id)

    if sys.platform == "win32":
        from app.services import attachment_storage_windows as win_mod

        real_open = win_mod.open_file_handle

        def unlink_then_open(path: str, *, access: int, disposition: int, flags: int = 0x80) -> int:
            if Path(path).name == str(attachment_id):
                if target.exists():
                    target.unlink()
                raise FileNotFoundError(2, "No such file", str(target))
            return real_open(path, access=access, disposition=disposition, flags=flags)

        monkeypatch.setattr(win_mod, "open_file_handle", unlink_then_open)
    else:
        real_open = os.open

        def unlink_then_open(path, flags, mode=0o777):  # noqa: ANN001
            if Path(path) == target:
                target.unlink()
                raise FileNotFoundError(2, "No such file", str(target))
            return real_open(path, flags, mode)

        monkeypatch.setattr(os, "open", unlink_then_open)

    with pytest.raises(AttachmentStorageNotFoundError) as ei:
        await storage.open(stored.storage_path)
    assert_no_abs_disclosure(ei.value, target, tmp_path / "files")
    assert ei.value.__cause__ is None


@pytest.mark.asyncio
async def test_errors_never_disclose_absolute_paths(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    missing_id = uuid4()
    abs_target = (tmp_path / "files" / STAGED_AREA / str(missing_id)).resolve()
    with pytest.raises(AttachmentStorageNotFoundError) as ei:
        await storage.open(f"{STAGED_AREA}/{missing_id}")
    assert_no_abs_disclosure(ei.value, abs_target, tmp_path / "files")


@pytest.mark.asyncio
async def test_open_binds_single_fd_and_ignores_pathname_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """open() must not reopen a mutable pathname per chunk (TOCTOU class)."""
    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir, chunk_size=4)
    attachment_id = uuid4()
    payload = b"AAAABBBBCCCC"
    stored = await storage.stage(attachment_id, iter_byte_chunks(payload, chunk_size=4))

    outside = tmp_path / "outside_marker.bin"
    outside.write_bytes(b"SECRSECRSECR")
    read_opens = {"count": 0}

    if sys.platform == "win32":
        from app.services import attachment_storage_windows as win_mod

        real_open = win_mod.open_file_handle

        def tracked_open(path: str, *, access: int, disposition: int, flags: int = 0x80) -> int:
            # Count leaf opens only (not directories).
            if Path(path).name == str(attachment_id):
                read_opens["count"] += 1
                if read_opens["count"] > 1:
                    return real_open(
                        str(outside), access=access, disposition=disposition, flags=flags
                    )
            return real_open(path, access=access, disposition=disposition, flags=flags)

        monkeypatch.setattr(win_mod, "open_file_handle", tracked_open)
    else:
        real_open = os.open

        def tracked_open(path, flags, mode=0o777):  # noqa: ANN001
            is_create = bool(flags & os.O_CREAT)
            is_write = bool(flags & (os.O_WRONLY | os.O_RDWR))
            if not is_create and not is_write:
                read_opens["count"] += 1
                if read_opens["count"] > 1:
                    return real_open(outside, flags, mode)
            return real_open(path, flags, mode)

        monkeypatch.setattr(os, "open", tracked_open)

    body = await read_all(storage, stored.storage_path)
    assert body == payload
    assert b"SECR" not in body
    assert read_opens["count"] == 1


@pytest.mark.asyncio
async def test_posix_link_unlink_failure_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POSIX publication must not succeed when source unlink fails after link."""
    if sys.platform == "win32":
        pytest.skip("POSIX link+unlink publication path")

    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"src-bytes"))
    staged = tmp_path / "files" / STAGED_AREA / str(attachment_id)
    active = tmp_path / "files" / "active" / str(attachment_id)
    real_unlink = os.unlink
    calls = {"n": 0}

    def flaky_unlink(path):  # noqa: ANN001
        calls["n"] += 1
        # First unlink is source cleanup after successful link — fail it.
        if calls["n"] == 1:
            raise OSError(16, "Device or resource busy", str(path))
        return real_unlink(path)

    monkeypatch.setattr(os, "unlink", flaky_unlink)
    with pytest.raises(AttachmentStorageIOError) as ei:
        await storage.promote(f"{STAGED_AREA}/{attachment_id}")
    assert_no_abs_disclosure(ei.value, tmp_path / "files")
    # No successful partial publish: either rolled back dest or kept only source.
    assert not (active.exists() and staged.exists())
    assert staged.exists() or not active.exists()
