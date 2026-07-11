"""Public unlink and best-effort abort cleanup for attachment storage.

Owns delete semantics (missing is ok; other failures raise sanitized errors)
and partial-FD abort cleanup. Descriptor and publication ops live in siblings.
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
    AttachmentStorageError,
    AttachmentStorageNotFoundError,
    InvalidStoragePathError,
    safe_message,
)

if sys.platform == "win32":
    from app.services import attachment_storage_windows as _win
    from app.services import attachment_storage_windows_mutate as _win_mut


class ContainedUnlinkOps(RootContainment):
    """Root-scoped public delete and abort cleanup."""

    def unlink_leaf(self, area: str, name: str) -> None:
        """Public delete: missing is ok; other failures raise sanitized errors."""
        leaf = self.area_dir(area) / name
        if is_link_like(leaf):
            raise InvalidStoragePathError(safe_message("invalid path"))
        if not path_exists_lexically(leaf):
            return
        if leaf.is_dir() and not leaf.is_symlink():
            raise InvalidStoragePathError(safe_message("invalid path"))

        if sys.platform == "win32":
            self._unlink_leaf_win(area, name)
            return
        os_error: OSError | None = None
        missing = False
        try:
            os.unlink(leaf)
        except FileNotFoundError:
            missing = True
        except OSError as exc:
            os_error = exc
        if missing:
            return
        reraise_os(os_error)

    def _unlink_leaf_win(self, area: str, name: str) -> None:
        parent = self.open_area_dir_handle_win(area)
        domain_error: AttachmentStorageError | None = None
        os_error: OSError | None = None
        try:
            parent_final = _win.final_path_from_handle(parent)
            open_path = os.path.join(parent_final, name)
            handle = 0
            missing = False
            try:
                handle = _win.open_existing_file_handle(open_path, for_delete=True)
            except AttachmentStorageNotFoundError:
                missing = True
            except AttachmentStorageError as exc:
                domain_error = exc
            except OSError as exc:
                os_error = exc
            if not missing and domain_error is None and os_error is None:
                try:
                    final = _win.final_path_from_handle(handle)
                    if not _win.path_under_root(final, self.root_real):
                        domain_error = InvalidStoragePathError(
                            safe_message("invalid path")
                        )
                    elif not _win.path_under_root(final, parent_final):
                        domain_error = InvalidStoragePathError(
                            safe_message("invalid path")
                        )
                    else:
                        try:
                            _win_mut.dispose_delete(handle)
                        except AttachmentStorageError as exc:
                            domain_error = exc
                        except OSError as exc:
                            os_error = exc
                except AttachmentStorageError as exc:
                    domain_error = exc
                finally:
                    _win.close_handle(handle)
        finally:
            _win.close_handle(parent)
        reraise_os(os_error)
        if domain_error is not None:
            raise domain_error

    def best_effort_unlink(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def abort_fd(self, fd: int | None, partial_path: Path | None = None) -> None:
        if fd is not None:
            if sys.platform == "win32":
                try:
                    handle = __import__("msvcrt").get_osfhandle(fd)
                    try:
                        _win_mut.dispose_delete(handle)
                    except Exception:
                        pass
                except Exception:
                    pass
            try:
                os.close(fd)
            except OSError:
                pass
        if partial_path is not None:
            self.best_effort_unlink(partial_path)
