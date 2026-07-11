"""Shared helpers for attachment storage tests (not collected as tests)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.services.attachment_storage import FilesystemAttachmentStorage


def assert_no_abs_disclosure(exc: BaseException, *paths: Path) -> None:
    """Public exception surfaces must not leak absolute paths or outside names."""
    assert exc.__cause__ is None
    assert exc.__context__ is None

    surfaces = [str(exc), repr(exc)]
    blob = "\n".join(surfaces)
    for path in paths:
        assert str(path) not in blob
        assert path.as_posix() not in blob
        try:
            assert str(path.resolve()) not in blob
        except OSError:
            pass
        text = str(path)
        if len(text) >= 2 and text[1] == ":":
            assert text not in blob


async def read_all(storage: FilesystemAttachmentStorage, rel: str) -> bytes:
    stream = await storage.open(rel)
    parts: list[bytes] = []
    async for chunk in stream:
        parts.append(chunk)
    return b"".join(parts)


def try_symlink(
    link: Path, target: Path, *, target_is_directory: bool = False
) -> bool:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
        return True
    except OSError:
        return False


def try_junction(link: Path, target: Path) -> bool:
    """Create a Windows directory junction (no admin required)."""
    if sys.platform != "win32":
        return False
    if link.exists() or link.is_symlink():
        return False
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and link.exists()


def link_dir(link: Path, target: Path) -> str:
    """Create symlink or junction; return kind or skip."""
    if try_symlink(link, target, target_is_directory=True):
        return "symlink"
    if try_junction(link, target):
        return "junction"
    pytest.skip("neither symlink nor junction creation is available")


def swap_dir_with_junction(real_dir: Path, outside: Path) -> Path:
    """Replace real_dir with a junction to outside; return backup path of real bytes."""
    backup = real_dir.with_name(real_dir.name + "_real_backup")
    if backup.exists():
        raise RuntimeError("backup path already exists")
    os.rename(real_dir, backup)
    kind = link_dir(real_dir, outside)
    assert kind in {"symlink", "junction"}
    return backup
