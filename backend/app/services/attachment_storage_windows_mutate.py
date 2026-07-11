"""Windows handle mutation: disposition delete and handle-relative rename.

Platform internals only. Path open/final-path resolution lives in
attachment_storage_windows; this module owns SetFileInformationByHandle
mutations after callers have verified containment.
"""

from __future__ import annotations

import os
from ctypes import Structure, byref, sizeof, windll, wintypes
from typing import Final

from app.services.attachment_storage_errors import (
    InvalidStoragePathError,
    safe_message,
)
from app.services.attachment_storage_windows import (
    final_path_from_handle,
    raise_last_error,
)

_FileDispositionInfo: Final[int] = 4
_FileRenameInfo: Final[int] = 3


class _FILE_DISPOSITION_INFO(Structure):
    _fields_ = [("DeleteFile", wintypes.BOOLEAN)]


class _FILE_RENAME_INFO(Structure):
    # Layout matches Win32 FILE_RENAME_INFO with Flags/ReplaceIfExists union
    # stored as DWORD for natural alignment before HANDLE on 64-bit Windows.
    _fields_ = [
        ("ReplaceIfExists", wintypes.DWORD),
        ("RootDirectory", wintypes.HANDLE),
        ("FileNameLength", wintypes.DWORD),
        ("FileName", wintypes.WCHAR * 512),
    ]


def dispose_delete(handle: int) -> None:
    """Mark open file for delete-on-close via handle (no pathname)."""
    info = _FILE_DISPOSITION_INFO(True)
    ok = windll.kernel32.SetFileInformationByHandle(
        wintypes.HANDLE(handle),
        _FileDispositionInfo,
        byref(info),
        sizeof(info),
    )
    if not ok:
        raise_last_error()


def rename_handle_to_path(
    file_handle: int,
    dest_full_path: str,
    *,
    replace_if_exists: bool = False,
) -> None:
    """Rename open file handle to an absolute destination path.

    Destination must be derived from a verified parent directory final path
    (not a mutable service pathname) so junction swaps of area names cannot
    redirect the publication target.
    """
    if not dest_full_path or "\x00" in dest_full_path:
        raise InvalidStoragePathError(safe_message("invalid path"))
    if len(dest_full_path) >= 512:
        raise InvalidStoragePathError(safe_message("invalid path"))
    info = _FILE_RENAME_INFO()
    info.ReplaceIfExists = 1 if replace_if_exists else 0
    info.RootDirectory = wintypes.HANDLE(0)
    # FileNameLength is size in bytes of the name without trailing NUL.
    encoded = dest_full_path.encode("utf-16-le")
    info.FileNameLength = len(encoded)
    info.FileName = dest_full_path
    ok = windll.kernel32.SetFileInformationByHandle(
        wintypes.HANDLE(file_handle),
        _FileRenameInfo,
        byref(info),
        sizeof(info),
    )
    if not ok:
        raise_last_error()


def rename_handle_under_parent(
    file_handle: int,
    dest_parent_handle: int,
    dest_name: str,
    *,
    replace_if_exists: bool = False,
) -> None:
    """Rename open file into a verified parent directory using its final path."""
    if not dest_name or "/" in dest_name or "\\" in dest_name or dest_name in {
        ".",
        "..",
    }:
        raise InvalidStoragePathError(safe_message("invalid path"))
    parent_final = final_path_from_handle(dest_parent_handle)
    dest_full = os.path.join(parent_final, dest_name)
    rename_handle_to_path(
        file_handle, dest_full, replace_if_exists=replace_if_exists
    )
