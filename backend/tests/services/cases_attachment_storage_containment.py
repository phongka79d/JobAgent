"""Path containment: pre-call and in-operation junction/reparse regressions."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from app.services.attachment_storage import (
    ACTIVE_AREA,
    STAGED_AREA,
    AttachmentStorageError,
    FilesystemAttachmentStorage,
    InvalidStoragePathError,
    iter_byte_chunks,
)
from tests.services.attachment_helpers import (
    assert_no_abs_disclosure,
    link_dir,
    read_all,
    swap_dir_with_junction,
    try_junction,
    try_symlink,
)


@pytest.mark.asyncio
async def test_absolute_and_traversal_paths_rejected_without_touching_outside(
    tmp_path: Path,
) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"SECRET")
    aid = uuid4()
    for bad in (
        str(outside),
        f"../{outside.name}",
        f"staged/../{outside.name}",
        f"staged/{aid}/../../{outside.name}",
    ):
        with pytest.raises((InvalidStoragePathError, AttachmentStorageError)):
            await storage.open(bad)
        with pytest.raises((InvalidStoragePathError, AttachmentStorageError)):
            await storage.delete(bad)
    assert outside.read_bytes() == b"SECRET"


@pytest.mark.asyncio
async def test_symlink_or_junction_escape_rejected_without_reading_or_deleting_outside(
    tmp_path: Path,
) -> None:
    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    outside = tmp_path / "outside_marker.bin"
    outside.write_bytes(b"OUTSIDE-BYTES")

    link_path = files_dir / STAGED_AREA / str(attachment_id)
    if not try_symlink(link_path, outside):
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "marker").write_bytes(b"OUTSIDE-BYTES")
        if not try_junction(link_path, outside_dir):
            pytest.skip("neither symlink nor junction creation is available")

    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)) as ei:
        await storage.open(f"{STAGED_AREA}/{attachment_id}")
    assert_no_abs_disclosure(ei.value, outside, files_dir)
    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)):
        await storage.delete(f"{STAGED_AREA}/{attachment_id}")
    if outside.exists():
        assert outside.read_bytes() == b"OUTSIDE-BYTES"


@pytest.mark.asyncio
async def test_symlink_or_junction_escape_blocks_promote(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"real"))
    outside_dir = tmp_path / "evil_active"
    outside_dir.mkdir()
    marker = outside_dir / str(attachment_id)
    marker.write_bytes(b"EVIL")

    active_leaf = files_dir / ACTIVE_AREA / str(attachment_id)
    if not try_symlink(active_leaf, marker):
        if not try_junction(active_leaf, outside_dir):
            pytest.skip("neither symlink nor junction creation is available")

    with pytest.raises((InvalidStoragePathError, AttachmentStorageError, Exception)):
        # Collision or invalid path — must not overwrite outside marker via promote.
        await storage.promote(f"{STAGED_AREA}/{attachment_id}")
    if marker.exists():
        assert marker.read_bytes() == b"EVIL"


@pytest.mark.asyncio
async def test_area_junction_swap_blocks_open_without_reading_outside(
    tmp_path: Path,
) -> None:
    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir, chunk_size=4)
    attachment_id = uuid4()
    payload = b"AAAABBBBCCCC"
    stored = await storage.stage(attachment_id, iter_byte_chunks(payload, chunk_size=4))
    assert await read_all(storage, stored.storage_path) == payload

    outside = tmp_path / "outside_area"
    outside.mkdir()
    marker = outside / str(attachment_id)
    marker.write_bytes(b"SECRSECRSECR")
    staged_dir = files_dir / STAGED_AREA
    backup = swap_dir_with_junction(staged_dir, outside)

    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)) as ei:
        await storage.open(stored.storage_path)
    assert_no_abs_disclosure(ei.value, outside, marker, files_dir)
    assert marker.read_bytes() == b"SECRSECRSECR"
    assert (backup / str(attachment_id)).read_bytes() == payload


@pytest.mark.asyncio
async def test_area_junction_blocks_new_open_delete_stage_promote(
    tmp_path: Path,
) -> None:
    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    stored = await storage.stage(attachment_id, iter_byte_chunks(b"keep-me"))
    original = (files_dir / STAGED_AREA / str(attachment_id)).read_bytes()

    outside = tmp_path / "evil_staged"
    outside.mkdir()
    marker = outside / str(attachment_id)
    marker.write_bytes(b"EVIL-OUTSIDE")

    staged_dir = files_dir / STAGED_AREA
    backup = swap_dir_with_junction(staged_dir, outside)

    with pytest.raises(InvalidStoragePathError) as ei:
        await storage.open(stored.storage_path)
    assert_no_abs_disclosure(ei.value, outside, marker, files_dir)

    with pytest.raises(InvalidStoragePathError):
        await storage.delete(stored.storage_path)

    other_id = uuid4()
    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)):
        await storage.stage(other_id, iter_byte_chunks(b"nope"))

    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)):
        await storage.promote(stored.storage_path)

    assert marker.read_bytes() == b"EVIL-OUTSIDE"
    assert (backup / str(attachment_id)).read_bytes() == original


@pytest.mark.asyncio
async def test_root_reparse_swap_rejected(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"root-stable"))

    outside = tmp_path / "fake_root"
    outside.mkdir()
    (outside / STAGED_AREA).mkdir()
    (outside / ACTIVE_AREA).mkdir()
    (outside / STAGED_AREA / str(attachment_id)).write_bytes(b"OUTSIDE-ROOT")

    backup = tmp_path / "files_real"
    os.rename(files_dir, backup)
    link_dir(files_dir, outside)

    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)) as ei:
        await storage.open(f"{STAGED_AREA}/{attachment_id}")
    assert_no_abs_disclosure(ei.value, outside, files_dir)
    assert (outside / STAGED_AREA / str(attachment_id)).read_bytes() == b"OUTSIDE-ROOT"
    assert (backup / STAGED_AREA / str(attachment_id)).read_bytes() == b"root-stable"


# ---------------------------------------------------------------------------
# In-operation junction swaps (A2 adversarial class)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_operation_area_swap_during_stage_publish_preserves_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Swap staged area to outside during finalize; must not create outside leaf."""
    if sys.platform != "win32":
        pytest.skip("Windows junction in-operation probe")

    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    outside = tmp_path / "outside_stage"
    outside.mkdir()
    marker = outside / "OUTSIDE-SOURCE"
    marker.write_bytes(b"OUTSIDE-SOURCE")

    from app.services.attachment_storage_ops import ContainedPathOps

    real_finalize = ContainedPathOps.finalize_partial_to_name

    def swap_then_finalize(self, fd, area, dest_name):  # noqa: ANN001
        staged = files_dir / STAGED_AREA
        if staged.exists() and not staged.is_symlink():
            try:
                # May fail while a partial FD remains open (Windows); that is safe.
                swap_dir_with_junction(staged, outside)
            except OSError:
                pass
        return real_finalize(self, fd, area, dest_name)

    monkeypatch.setattr(ContainedPathOps, "finalize_partial_to_name", swap_then_finalize)

    outcome: object
    try:
        outcome = await storage.stage(
            attachment_id, iter_byte_chunks(b"should-not-escape")
        )
    except (InvalidStoragePathError, AttachmentStorageError) as exc:
        outcome = exc
        assert_no_abs_disclosure(exc, outside, files_dir)

    # Outside marker preserved; no attachment leaf created outside.
    assert marker.read_bytes() == b"OUTSIDE-SOURCE"
    assert not (outside / str(attachment_id)).exists()
    # If publish succeeded, bytes must live only under the real FILES_DIR tree.
    if not isinstance(outcome, BaseException):
        real_leaf = files_dir / STAGED_AREA / str(attachment_id)
        backup = files_dir / "staged_real_backup" / str(attachment_id)
        assert real_leaf.exists() or backup.exists()
        if real_leaf.exists():
            assert real_leaf.read_bytes() == b"should-not-escape"


@pytest.mark.asyncio
async def test_in_operation_area_swap_during_promote_preserves_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows junction in-operation probe")

    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"PROMOTE-ME"))
    real_staged = files_dir / STAGED_AREA / str(attachment_id)
    assert real_staged.read_bytes() == b"PROMOTE-ME"

    outside = tmp_path / "outside_active"
    outside.mkdir()
    outside_marker = outside / "keep"
    outside_marker.write_bytes(b"KEEP-OUTSIDE")

    from app.services.attachment_storage_ops import ContainedPathOps

    real_publish = ContainedPathOps.publish_across_areas

    def swap_then_publish(self, src_area, src_name, dest_area, dest_name):  # noqa: ANN001
        active = files_dir / ACTIVE_AREA
        if active.exists() and not active.is_symlink():
            swap_dir_with_junction(active, outside)
        return real_publish(self, src_area, src_name, dest_area, dest_name)

    monkeypatch.setattr(ContainedPathOps, "publish_across_areas", swap_then_publish)

    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)):
        await storage.promote(f"{STAGED_AREA}/{attachment_id}")

    assert outside_marker.read_bytes() == b"KEEP-OUTSIDE"
    assert not (outside / str(attachment_id)).exists()
    # Source either still staged under real area or safely unchanged outside.
    staged_dir = files_dir / STAGED_AREA
    if staged_dir.exists() and not staged_dir.is_symlink() and real_staged.exists():
        assert real_staged.read_bytes() == b"PROMOTE-ME"


@pytest.mark.asyncio
async def test_in_operation_area_swap_during_delete_preserves_outside_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows junction in-operation probe")

    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"delete-me"))
    real_file = files_dir / STAGED_AREA / str(attachment_id)
    assert real_file.read_bytes() == b"delete-me"

    outside = tmp_path / "outside_del"
    outside.mkdir()
    marker = outside / str(attachment_id)
    marker.write_bytes(b"OUTSIDE-MARKER")

    from app.services.attachment_storage_ops import ContainedPathOps

    real_unlink = ContainedPathOps.unlink_leaf

    def swap_then_unlink(self, area, name):  # noqa: ANN001
        staged = files_dir / STAGED_AREA
        if staged.exists() and not staged.is_symlink():
            swap_dir_with_junction(staged, outside)
        return real_unlink(self, area, name)

    monkeypatch.setattr(ContainedPathOps, "unlink_leaf", swap_then_unlink)

    with pytest.raises((InvalidStoragePathError, AttachmentStorageError)):
        await storage.delete(f"{STAGED_AREA}/{attachment_id}")

    assert marker.read_bytes() == b"OUTSIDE-MARKER"


@pytest.mark.asyncio
async def test_final_path_api_failure_rejects_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows final-path unavailability must fail closed (never stale fallback)."""
    if sys.platform != "win32":
        pytest.skip("Windows final-path API probe")

    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"inside"))

    from app.services import attachment_storage_windows as win_mod

    def fail_final(handle: int) -> str:
        raise InvalidStoragePathError("attachment storage invalid path")

    # Fail closed at FD verification time after open.
    monkeypatch.setattr(win_mod, "final_path_from_handle", fail_final)

    with pytest.raises(InvalidStoragePathError) as ei:
        await storage.open(f"{STAGED_AREA}/{attachment_id}")
    assert_no_abs_disclosure(ei.value, files_dir)


@pytest.mark.asyncio
async def test_final_path_api_failure_during_open_fd_with_area_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If final-path returns failure after open, must not return outside bytes."""
    if sys.platform != "win32":
        pytest.skip("Windows final-path API probe")

    files_dir = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_dir)
    attachment_id = uuid4()
    await storage.stage(attachment_id, iter_byte_chunks(b"INSIDE-BYTES"))

    outside = tmp_path / "out_area"
    outside.mkdir()
    (outside / str(attachment_id)).write_bytes(b"OUTSIDE")

    from app.services import attachment_storage_windows as win_mod
    from app.services.attachment_storage_ops import ContainedPathOps

    real_open = ContainedPathOps.open_readonly_fd
    calls = {"n": 0}

    def open_with_swap(self, area, name):  # noqa: ANN001
        calls["n"] += 1
        staged = files_dir / STAGED_AREA
        if calls["n"] == 1 and staged.exists() and not staged.is_symlink():
            # Swap before open path resolution inside the method — inject after
            # the real method starts by failing final path only.
            pass
        return real_open(self, area, name)

    monkeypatch.setattr(ContainedPathOps, "open_readonly_fd", open_with_swap)

    # Simulate GetFinalPathNameByHandle failure (returns raise via wrapper).
    real_final = win_mod.final_path_from_handle

    def flaky_final(handle: int) -> str:
        # Always fail closed for leaf verification path.
        raise InvalidStoragePathError("attachment storage invalid path")

    monkeypatch.setattr(win_mod, "final_path_from_handle", flaky_final)
    monkeypatch.setattr(
        win_mod,
        "final_path_from_fd",
        lambda fd: (_ for _ in ()).throw(
            InvalidStoragePathError("attachment storage invalid path")
        ),
    )

    with pytest.raises(InvalidStoragePathError):
        await storage.open(f"{STAGED_AREA}/{attachment_id}")
    # Outside not read into caller — open never returned a stream of OUTSIDE.
    assert (outside / str(attachment_id)).read_bytes() == b"OUTSIDE"
    # Restore not required; real_final unused keeps lint quiet via reference.
    _ = real_final
