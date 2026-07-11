"""Descriptor create/open and chunk write helpers.

Owns exclusive partial creation, readonly open, and low-level write/fsync/close
helpers. Partial finalization and cross-area publication live in
attachment_storage_publish; public unlink lives in attachment_storage_unlink.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.services.attachment_storage_containment import (
    is_link_like,
    path_exists_lexically,
    reraise_os,
)
from app.services.attachment_storage_errors import (
    AttachmentStorageError,
    AttachmentStorageInvalidContentError,
    AttachmentStorageIOError,
    AttachmentStorageNotFoundError,
    InvalidStoragePathError,
    safe_message,
)
from app.services.attachment_storage_paths import PARTIAL_SUFFIX
from app.services.attachment_storage_unlink import ContainedUnlinkOps

if sys.platform == "win32":
    from app.services import attachment_storage_windows as _win
    from app.services import attachment_storage_windows_mutate as _win_mut


def write_all(fd: int, data: bytes) -> int:
    """Loop ``os.write`` until every byte is persisted; return bytes written."""
    if not data:
        return 0
    view = memoryview(data)
    total = 0
    length = len(view)
    while total < length:
        os_error: OSError | None = None
        written = 0
        try:
            written = os.write(fd, view[total:])
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        if written <= 0:
            raise AttachmentStorageIOError(safe_message("short write"))
        total += written
    return total


def fsync_fd(fd: int) -> None:
    os_error: OSError | None = None
    try:
        os.fsync(fd)
    except OSError as exc:
        os_error = exc
    reraise_os(os_error)


def close_fd(fd: int) -> None:
    os_error: OSError | None = None
    try:
        os.close(fd)
    except OSError as exc:
        os_error = exc
    reraise_os(os_error)


def coerce_chunk(chunk: object) -> bytes:
    """Accept bytes-like chunks only; empty is predictable (zero-length bytes)."""
    if isinstance(chunk, bytes):
        return chunk
    if isinstance(chunk, bytearray):
        return bytes(chunk)
    if isinstance(chunk, memoryview):
        return chunk.tobytes()
    raise AttachmentStorageInvalidContentError(safe_message("invalid chunk"))


class ContainedFdOps(ContainedUnlinkOps):
    """Root-scoped descriptor create and readonly open.

    Inherits unlink for partial abort cleanup. Partial finalization
    (fsync + publish) lives on ContainedPublishOps.
    """

    def create_partial_fd(self, area: str, partial_name: str) -> int:
        """Create exclusive partial file under area; return contained FD."""
        if not partial_name.endswith(PARTIAL_SUFFIX):
            raise InvalidStoragePathError(safe_message("invalid path"))
        if "/" in partial_name or "\\" in partial_name:
            raise InvalidStoragePathError(safe_message("invalid path"))
        area_dir = self.area_dir(area)
        partial_path = area_dir / partial_name
        if path_exists_lexically(partial_path):
            self.best_effort_unlink(partial_path)

        if sys.platform == "win32":
            return self._create_partial_fd_win(area, partial_name)
        return self._posix_open_create_excl(partial_path)

    def _create_partial_fd_win(self, area: str, partial_name: str) -> int:
        parent = self.open_area_dir_handle_win(area)
        domain_error: AttachmentStorageError | None = None
        os_error: OSError | None = None
        fd = -1
        try:
            parent_final = _win.final_path_from_handle(parent)
            create_path = os.path.join(parent_final, partial_name)
            handle = 0
            try:
                handle = _win.create_new_file_handle(create_path)
            except AttachmentStorageError as exc:
                domain_error = exc
            except OSError as exc:
                os_error = exc
            if domain_error is None and os_error is None:
                try:
                    final = _win.final_path_from_handle(handle)
                    if not _win.path_under_root(final, self.root_real):
                        try:
                            _win_mut.dispose_delete(handle)
                        except AttachmentStorageError:
                            pass
                        _win.close_handle(handle)
                        domain_error = InvalidStoragePathError(
                            safe_message("invalid path")
                        )
                    else:
                        fd = _win.handle_to_fd(handle, os.O_RDWR)
                except AttachmentStorageError as exc:
                    try:
                        _win_mut.dispose_delete(handle)
                    except AttachmentStorageError:
                        pass
                    _win.close_handle(handle)
                    domain_error = exc
        finally:
            _win.close_handle(parent)
        reraise_os(os_error)
        if domain_error is not None:
            raise domain_error
        return fd

    def _posix_open_create_excl(self, path: Path) -> int:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        os_error: OSError | None = None
        fd = -1
        try:
            fd = os.open(path, flags, 0o600)
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        domain_error: AttachmentStorageError | None = None
        try:
            self._assert_fd_contained_posix(fd, path)
        except AttachmentStorageError as exc:
            domain_error = exc
        if domain_error is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            self.best_effort_unlink(path)
            raise domain_error
        return fd

    def _assert_fd_contained_posix(self, fd: int, expected: Path | None = None) -> None:
        os_error: OSError | None = None
        try:
            if hasattr(os, "fstat"):
                os.fstat(fd)
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        proc = Path(f"/proc/self/fd/{fd}")
        if proc.exists():
            real: Path | None = None
            try:
                real = Path(os.path.realpath(proc))
            except OSError as exc:
                os_error = exc
            reraise_os(os_error)
            assert real is not None
            if not self.is_under_root_path(real):
                raise InvalidStoragePathError(safe_message("invalid path"))
            return
        if expected is not None and not self.is_under_root_path(expected):
            raise InvalidStoragePathError(safe_message("invalid path"))

    def open_readonly_fd(self, area: str, name: str) -> int:
        """Open leaf for read after handle/final-path containment."""
        leaf = self.area_dir(area) / name
        if is_link_like(leaf):
            raise InvalidStoragePathError(safe_message("invalid path"))
        if not path_exists_lexically(leaf):
            raise AttachmentStorageNotFoundError(safe_message("not found"))

        if sys.platform == "win32":
            return self._open_readonly_fd_win(area, name)
        return self._open_readonly_fd_posix(leaf)

    def _open_readonly_fd_win(self, area: str, name: str) -> int:
        parent = self.open_area_dir_handle_win(area)
        domain_error: AttachmentStorageError | None = None
        os_error: OSError | None = None
        fd = -1
        try:
            parent_final = _win.final_path_from_handle(parent)
            open_path = os.path.join(parent_final, name)
            handle = 0
            try:
                handle = _win.open_file_handle(
                    open_path,
                    access=0x80000000,  # GENERIC_READ
                    disposition=3,  # OPEN_EXISTING
                )
            except AttachmentStorageError as exc:
                domain_error = exc
            except OSError as exc:
                os_error = exc
            if domain_error is None and os_error is None:
                try:
                    final = _win.final_path_from_handle(handle)
                    if not _win.path_under_root(final, self.root_real):
                        _win.close_handle(handle)
                        domain_error = InvalidStoragePathError(
                            safe_message("invalid path")
                        )
                    elif not _win.path_under_root(final, parent_final):
                        _win.close_handle(handle)
                        domain_error = InvalidStoragePathError(
                            safe_message("invalid path")
                        )
                    else:
                        fd = _win.handle_to_fd(handle, os.O_RDONLY)
                except AttachmentStorageError as exc:
                    _win.close_handle(handle)
                    domain_error = exc
        finally:
            _win.close_handle(parent)
        reraise_os(os_error)
        if domain_error is not None:
            raise domain_error
        return fd

    def _open_readonly_fd_posix(self, leaf: Path) -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        os_error: OSError | None = None
        fd = -1
        try:
            fd = os.open(leaf, flags)
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        domain_error: AttachmentStorageError | None = None
        try:
            self._assert_fd_contained_posix(fd, leaf)
        except AttachmentStorageError as exc:
            domain_error = exc
        if domain_error is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            raise domain_error
        return fd
