"""Root/area containment and path-identity helpers for attachment storage."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.services.attachment_storage_errors import (
    AttachmentStorageError,
    InvalidStoragePathError,
    safe_message,
    sanitize_os_error,
)
from app.services.attachment_storage_paths import ALLOWED_AREAS

if sys.platform == "win32":
    from app.services import attachment_storage_windows as _win


def reraise_os(exc: OSError | None) -> None:
    """Raise sanitized OS error outside an ``except`` block (no context leak)."""
    if exc is not None:
        raise sanitize_os_error(exc)


def is_link_like(path: Path) -> bool:
    """True if path is a symlink, Windows junction, or other reparse link."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
    except OSError:
        return True
    if sys.platform == "win32":
        try:
            if _win.is_reparse_path(str(path)):
                return True
        except Exception:
            return True
    return False


def path_exists_lexically(path: Path) -> bool:
    """Existence check that treats dangling links as present."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        if sys.platform == "win32" and _win.is_reparse_path(str(path)):
            return True
        return path.exists()
    except OSError:
        return False


class RootContainment:
    """FILES_DIR identity and area-directory verification."""

    def __init__(self, root: Path) -> None:
        self._root = root
        os_error: OSError | None = None
        try:
            self._root_real = os.path.realpath(root)
        except OSError as exc:
            os_error = exc
            self._root_real = ""
        reraise_os(os_error)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def root_real(self) -> str:
        return self._root_real

    def ensure_layout(self) -> None:
        os_error: OSError | None = None
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        for area in ALLOWED_AREAS:
            area_dir = self._root / area
            os_error = None
            try:
                area_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                os_error = exc
            reraise_os(os_error)
            if is_link_like(area_dir):
                raise InvalidStoragePathError(safe_message("invalid path"))
        self.assert_root_stable()

    def assert_root_stable(self) -> None:
        if is_link_like(self._root):
            raise InvalidStoragePathError(safe_message("invalid path"))
        os_error: OSError | None = None
        real = ""
        try:
            real = os.path.realpath(self._root)
        except OSError as exc:
            os_error = exc
        reraise_os(os_error)
        if os.path.normcase(real) != os.path.normcase(self._root_real):
            raise InvalidStoragePathError(safe_message("invalid path"))
        if sys.platform == "win32":
            handle = _win.open_directory_handle(str(self._root))
            domain_error: AttachmentStorageError | None = None
            try:
                final = _win.final_path_from_handle(handle)
                if not _win.path_under_root(final, self._root_real):
                    domain_error = InvalidStoragePathError(safe_message("invalid path"))
            except AttachmentStorageError as exc:
                domain_error = exc
            finally:
                _win.close_handle(handle)
            if domain_error is not None:
                raise domain_error

    def is_under_root_path(self, path: Path) -> bool:
        try:
            path.relative_to(self._root)
        except ValueError:
            return False
        try:
            real_root = Path(os.path.realpath(self._root))
            real_path = Path(os.path.realpath(path))
            real_path.relative_to(real_root)
        except (OSError, ValueError):
            return False
        return True

    def area_dir(self, area: str) -> Path:
        """Return area directory path after containment verification."""
        self.assert_root_stable()
        if area not in ALLOWED_AREAS:
            raise InvalidStoragePathError(safe_message("invalid path"))
        area_dir = self._root / area
        if not path_exists_lexically(area_dir):
            os_error: OSError | None = None
            try:
                area_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                os_error = exc
            reraise_os(os_error)
        if is_link_like(area_dir):
            raise InvalidStoragePathError(safe_message("invalid path"))
        if sys.platform == "win32":
            handle = _win.open_directory_handle(str(area_dir))
            domain_error: AttachmentStorageError | None = None
            try:
                final = _win.final_path_from_handle(handle)
                if not _win.path_under_root(final, self._root_real):
                    domain_error = InvalidStoragePathError(safe_message("invalid path"))
            except AttachmentStorageError as exc:
                domain_error = exc
            finally:
                _win.close_handle(handle)
            if domain_error is not None:
                raise domain_error
        else:
            os_error = None
            resolved = area_dir
            try:
                resolved = area_dir.resolve(strict=True)
            except OSError as exc:
                os_error = exc
            reraise_os(os_error)
            if not self.is_under_root_path(resolved):
                raise InvalidStoragePathError(safe_message("invalid path"))
            if is_link_like(resolved):
                raise InvalidStoragePathError(safe_message("invalid path"))
        return area_dir

    def open_area_dir_handle_win(self, area: str) -> int:
        """Windows: open verified area directory HANDLE (caller closes)."""
        area_dir = self.area_dir(area)
        handle = _win.open_directory_handle(str(area_dir))
        domain_error: AttachmentStorageError | None = None
        try:
            final = _win.final_path_from_handle(handle)
            if not _win.path_under_root(final, self._root_real):
                domain_error = InvalidStoragePathError(safe_message("invalid path"))
        except AttachmentStorageError as exc:
            domain_error = exc
        if domain_error is not None:
            _win.close_handle(handle)
            raise domain_error
        return handle
