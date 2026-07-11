"""Cross-area and same-area publication with non-overwrite and POSIX rollback.

Owns promote-style publish and the POSIX link+unlink rollback used by partial
finalization. Descriptor create/open and public unlink live in sibling modules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.services.attachment_storage_containment import (
    RootContainment,
    is_link_like,
    path_exists_lexically,
    reraise_os,
)
from app.services.attachment_storage_errors import (
    AttachmentStorageCollisionError,
    AttachmentStorageError,
    AttachmentStorageIOError,
    InvalidStoragePathError,
    safe_message,
    sanitize_os_error,
)
from app.services.attachment_storage_fd import fsync_fd

if sys.platform == "win32":
    from app.services import attachment_storage_windows as _win
    from app.services import attachment_storage_windows_mutate as _win_mut


class ContainedPublishOps(RootContainment):
    """Root-scoped publication, partial finalization, and POSIX rollback."""

    def finalize_partial_to_name(self, fd: int, area: str, dest_name: str) -> None:
        """Fsync open partial FD and publish to dest_name; closes FD on success."""
        fsync_fd(fd)
        if sys.platform == "win32":
            self._finalize_partial_win(fd, area, dest_name)
            return
        self._finalize_partial_posix(fd, area, dest_name)

    def _finalize_partial_win(self, fd: int, area: str, dest_name: str) -> None:
        parent = self.open_area_dir_handle_win(area)
        domain_error: AttachmentStorageError | None = None
        try:
            parent_final = _win.final_path_from_handle(parent)
            if not _win.path_under_root(parent_final, self.root_real):
                domain_error = InvalidStoragePathError(safe_message("invalid path"))
            else:
                src_final = _win.final_path_from_fd(fd)
                if not _win.path_under_root(src_final, self.root_real):
                    domain_error = InvalidStoragePathError(safe_message("invalid path"))
                elif not _win.path_under_root(src_final, parent_final):
                    domain_error = InvalidStoragePathError(safe_message("invalid path"))
                else:
                    dest_path = os.path.join(parent_final, dest_name)
                    if _win.get_file_attributes(dest_path) is not None:
                        domain_error = AttachmentStorageCollisionError(
                            safe_message("collision")
                        )
                    else:
                        handle = __import__("msvcrt").get_osfhandle(fd)
                        _win_mut.rename_handle_under_parent(
                            handle, parent, dest_name, replace_if_exists=False
                        )
        except AttachmentStorageError as exc:
            domain_error = exc
        finally:
            _win.close_handle(parent)
        if domain_error is not None:
            raise domain_error
        os_error: OSError | None = None
        try:
            os.close(fd)
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)

    def _finalize_partial_posix(self, fd: int, area: str, dest_name: str) -> None:
        area_dir = self.area_dir(area)
        proc = Path(f"/proc/self/fd/{fd}")
        if not proc.exists():
            raise AttachmentStorageIOError(safe_message("io failed"))
        os_error: OSError | None = None
        src: Path | None = None
        try:
            src = Path(os.path.realpath(proc))
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        assert src is not None
        if not self.is_under_root_path(src):
            raise InvalidStoragePathError(safe_message("invalid path"))
        dest = area_dir / dest_name
        os_error = None
        try:
            os.close(fd)
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        self._publish_posix(src, dest)

    def publish_across_areas(
        self, src_area: str, src_name: str, dest_area: str, dest_name: str
    ) -> None:
        """Publish from one area to another without overwrite (promote)."""
        dest_area_dir = self.area_dir(dest_area)
        if path_exists_lexically(dest_area_dir / dest_name):
            raise AttachmentStorageCollisionError(safe_message("collision"))

        if sys.platform == "win32":
            self._publish_windows_across(src_area, src_name, dest_area, dest_name)
        else:
            src = self.area_dir(src_area) / src_name
            dest = dest_area_dir / dest_name
            if path_exists_lexically(dest) or is_link_like(dest):
                raise AttachmentStorageCollisionError(safe_message("collision"))
            self._publish_posix(src, dest)

    def _publish_windows_across(
        self, src_area: str, src_name: str, dest_area: str, dest_name: str
    ) -> None:
        src_parent = self.open_area_dir_handle_win(src_area)
        domain_error: AttachmentStorageError | None = None
        try:
            src_parent_final = _win.final_path_from_handle(src_parent)
            src_path = os.path.join(src_parent_final, src_name)
            src_handle = _win.open_existing_for_rename(src_path)
            try:
                src_final = _win.final_path_from_handle(src_handle)
                if not _win.path_under_root(src_final, self.root_real):
                    domain_error = InvalidStoragePathError(safe_message("invalid path"))
                else:
                    dest_parent = self.open_area_dir_handle_win(dest_area)
                    try:
                        dest_parent_final = _win.final_path_from_handle(dest_parent)
                        if not _win.path_under_root(dest_parent_final, self.root_real):
                            domain_error = InvalidStoragePathError(
                                safe_message("invalid path")
                            )
                        else:
                            _win_mut.rename_handle_under_parent(
                                src_handle,
                                dest_parent,
                                dest_name,
                                replace_if_exists=False,
                            )
                    except AttachmentStorageError as exc:
                        domain_error = exc
                    finally:
                        _win.close_handle(dest_parent)
            except AttachmentStorageError as exc:
                domain_error = exc
            finally:
                _win.close_handle(src_handle)
        except AttachmentStorageError as exc:
            domain_error = exc
        finally:
            _win.close_handle(src_parent)
        if domain_error is not None:
            raise domain_error

    def _publish_posix(self, src: Path, dest: Path) -> None:
        if not self.is_under_root_path(src.parent) or not self.is_under_root_path(
            dest.parent
        ):
            raise InvalidStoragePathError(safe_message("invalid path"))
        if is_link_like(src) or is_link_like(dest):
            raise InvalidStoragePathError(safe_message("invalid path"))
        if path_exists_lexically(dest):
            raise AttachmentStorageCollisionError(safe_message("collision"))
        os_error: OSError | None = None
        try:
            os.link(src, dest)
        except FileExistsError:
            os_error = FileExistsError()
        except OSError as exc:
            os_error = exc
        if isinstance(os_error, FileExistsError):
            raise AttachmentStorageCollisionError(safe_message("collision"))
        reraise_os(os_error)

        unlink_error: OSError | None = None
        try:
            os.unlink(src)
        except OSError as exc:
            unlink_error = exc
        if unlink_error is not None:
            try:
                os.unlink(dest)
            except OSError:
                pass
            raise sanitize_os_error(unlink_error)
