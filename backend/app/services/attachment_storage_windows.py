"""Private Windows reparse/handle path adapter for contained attachment IO.

Platform internals only. Callers must not re-export handles or absolute paths.
Owns CreateFileW opens, GetFinalPathNameByHandleW resolution, and path
containment helpers. Handle mutations (delete/rename) live in
attachment_storage_windows_mutate. Fail-closed when final-path APIs are unavailable.
"""

from __future__ import annotations

import sys
from ctypes import (
    POINTER,
    create_unicode_buffer,
    windll,
    wintypes,
)
from typing import Final

from app.services.attachment_storage_errors import (
    AttachmentStorageCollisionError,
    AttachmentStorageIOError,
    AttachmentStorageNotFoundError,
    InvalidStoragePathError,
    safe_message,
    sanitize_os_error,
)

# Win32 constants
_GENERIC_READ: Final[int] = 0x80000000
_GENERIC_WRITE: Final[int] = 0x40000000
_DELETE: Final[int] = 0x00010000
_SYNCHRONIZE: Final[int] = 0x00100000
_FILE_SHARE_READ: Final[int] = 0x00000001
_FILE_SHARE_WRITE: Final[int] = 0x00000002
_FILE_SHARE_DELETE: Final[int] = 0x00000004
_CREATE_NEW: Final[int] = 1
_OPEN_EXISTING: Final[int] = 3
_FILE_ATTRIBUTE_NORMAL: Final[int] = 0x80
_FILE_FLAG_BACKUP_SEMANTICS: Final[int] = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT: Final[int] = 0x00200000
_FILE_ATTRIBUTE_REPARSE_POINT: Final[int] = 0x400
_INVALID_HANDLE_VALUE: Final[int] = -1

_ERROR_FILE_EXISTS: Final[int] = 80
_ERROR_ALREADY_EXISTS: Final[int] = 183
_ERROR_FILE_NOT_FOUND: Final[int] = 2
_ERROR_PATH_NOT_FOUND: Final[int] = 3
_ERROR_ACCESS_DENIED: Final[int] = 5


def raise_last_error() -> None:
    """Map GetLastError to a sanitized domain error (shared with mutate)."""
    err = windll.kernel32.GetLastError()
    if err in {_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND}:
        raise AttachmentStorageNotFoundError(safe_message("not found"))
    if err == _ERROR_ACCESS_DENIED:
        raise AttachmentStorageIOError(safe_message("permission denied"))
    if err in {_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS}:
        raise AttachmentStorageCollisionError(safe_message("collision"))
    raise AttachmentStorageIOError(safe_message("io failed"))


def normalize_win_path(path_str: str) -> str:
    """Strip ``\\\\?\\`` / ``\\\\?\\UNC\\`` prefixes for comparison."""
    if path_str.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path_str[8:]
    if path_str.startswith("\\\\?\\"):
        return path_str[4:]
    return path_str


def final_path_from_handle(handle: int) -> str:
    """Resolve final path for an open Windows HANDLE. Fail-closed on error."""
    if sys.platform != "win32":
        raise AttachmentStorageIOError(safe_message("io failed"))
    get_final = windll.kernel32.GetFinalPathNameByHandleW
    get_final.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    get_final.restype = wintypes.DWORD
    buf = create_unicode_buffer(32768)
    wrote = get_final(handle, buf, len(buf), 0)
    if wrote == 0 or wrote >= len(buf):
        # API absence or failure must reject - never fall back to stale checks.
        raise InvalidStoragePathError(safe_message("invalid path"))
    return normalize_win_path(buf.value)


def final_path_from_fd(fd: int) -> str:
    """Resolve final path for a C runtime FD via its OS handle."""
    import msvcrt

    try:
        handle = msvcrt.get_osfhandle(fd)
    except OSError as exc:
        raise sanitize_os_error(exc) from None
    return final_path_from_handle(handle)


def close_handle(handle: int) -> None:
    if handle and handle != _INVALID_HANDLE_VALUE:
        windll.kernel32.CloseHandle(wintypes.HANDLE(handle))


def open_directory_handle(path: str, *, open_reparse: bool = False) -> int:
    """Open a directory HANDLE. Does not follow path after open; caller verifies."""
    flags = _FILE_FLAG_BACKUP_SEMANTICS
    if open_reparse:
        flags |= _FILE_FLAG_OPEN_REPARSE_POINT
    handle = windll.kernel32.CreateFileW(
        path,
        _GENERIC_READ | _SYNCHRONIZE,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_EXISTING,
        flags,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise_last_error()
    return int(handle)


def open_file_handle(
    path: str,
    *,
    access: int,
    disposition: int,
    flags: int = _FILE_ATTRIBUTE_NORMAL,
) -> int:
    handle = windll.kernel32.CreateFileW(
        path,
        access | _SYNCHRONIZE,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        disposition,
        flags,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise_last_error()
    return int(handle)


def create_new_file_handle(path: str) -> int:
    """Create a new file exclusively (CREATE_NEW)."""
    return open_file_handle(
        path,
        access=_GENERIC_READ | _GENERIC_WRITE | _DELETE,
        disposition=_CREATE_NEW,
        flags=_FILE_ATTRIBUTE_NORMAL,
    )


def open_existing_file_handle(path: str, *, for_delete: bool = False) -> int:
    if for_delete:
        access = _GENERIC_READ | _GENERIC_WRITE | _DELETE
    else:
        access = _GENERIC_READ
    return open_file_handle(
        path,
        access=access,
        disposition=_OPEN_EXISTING,
        flags=_FILE_ATTRIBUTE_NORMAL,
    )


def open_existing_for_rename(path: str) -> int:
    """Open existing file with rights required for SetFileInformationByHandle rename."""
    return open_file_handle(
        path,
        access=_GENERIC_READ | _GENERIC_WRITE | _DELETE,
        disposition=_OPEN_EXISTING,
        flags=_FILE_ATTRIBUTE_NORMAL,
    )


def handle_to_fd(handle: int, flags: int) -> int:
    """Transfer HANDLE ownership into a CRT file descriptor."""
    import msvcrt

    os_error: OSError | None = None
    fd = -1
    try:
        fd = msvcrt.open_osfhandle(handle, flags)
    except OSError as exc:
        os_error = exc
    if os_error is not None:
        close_handle(handle)
        raise sanitize_os_error(os_error)
    return fd


def get_file_attributes(path: str) -> int | None:
    attrs = int(windll.kernel32.GetFileAttributesW(path))
    # INVALID_FILE_ATTRIBUTES is 0xFFFFFFFF; ctypes may surface it as signed -1.
    if attrs == -1 or attrs == 0xFFFFFFFF:
        return None
    return attrs & 0xFFFFFFFF


def is_reparse_path(path: str) -> bool:
    attrs = get_file_attributes(path)
    if attrs is None:
        return False
    return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)


def path_under_root(candidate: str, root_real: str) -> bool:
    """Case-normalized containment check for Windows final paths."""
    import os

    try:
        cand = os.path.normcase(os.path.normpath(normalize_win_path(candidate)))
        root = os.path.normcase(os.path.normpath(normalize_win_path(root_real)))
    except (OSError, TypeError, ValueError):
        return False
    if cand == root:
        return True
    prefix = root if root.endswith(os.sep) else root + os.sep
    return cand.startswith(prefix)


# Silence unused import warning for POINTER in strict type environments
_ = POINTER
