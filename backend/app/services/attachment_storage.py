"""Filesystem-backed attachment storage under FILES_DIR (public facade).

Implements Plan 2 storage mechanics only: staged/active locations, path
containment, chunked async staging with cleanup, and atomic non-overwriting
promotion. MIME/magic/page/profile policy belongs to Plan 4.

Public contract types, the orchestration facade, and re-exports of the
authoritative path grammar live here. Platform handle adapters and low-level
descriptor/publication primitives are private sibling modules.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.services.attachment_storage_errors import (
    AttachmentStorageCollisionError,
    AttachmentStorageError,
    AttachmentStorageInvalidContentError,
    AttachmentStorageIOError,
    AttachmentStorageNotFoundError,
    AttachmentStorageStateError,
    InvalidStoragePathError,
    safe_message,
    sanitize_os_error,
)
from app.services.attachment_storage_ops import (
    ContainedPathOps,
    coerce_chunk,
    write_all,
)
from app.services.attachment_storage_paths import (
    ACTIVE_AREA,
    ALLOWED_AREAS,
    DEFAULT_CHUNK_SIZE,
    PARTIAL_SUFFIX,
    STAGED_AREA,
    parse_service_storage_path,
    require_canonical_service_path,
    service_path_for,
)

# Re-export public error and path API for repository and tests.
__all__ = [
    "ACTIVE_AREA",
    "ALLOWED_AREAS",
    "DEFAULT_CHUNK_SIZE",
    "PARTIAL_SUFFIX",
    "STAGED_AREA",
    "AttachmentStorage",
    "AttachmentStorageCollisionError",
    "AttachmentStorageError",
    "AttachmentStorageInvalidContentError",
    "AttachmentStorageIOError",
    "AttachmentStorageNotFoundError",
    "AttachmentStorageStateError",
    "FilesystemAttachmentStorage",
    "InvalidStoragePathError",
    "StoredFile",
    "iter_byte_chunks",
    "parse_service_storage_path",
    "require_canonical_service_path",
]


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Result of a successful stage operation (service-relative path + size)."""

    storage_path: str
    size_bytes: int


class AttachmentStorage(Protocol):
    """Declared Plan 2 attachment storage contract."""

    async def stage(
        self, attachment_id: UUID, content: AsyncIterator[bytes]
    ) -> StoredFile: ...

    async def promote(self, storage_path: str) -> str: ...

    async def delete(self, storage_path: str) -> None: ...

    async def open(self, storage_path: str) -> AsyncIterator[bytes]: ...


class FilesystemAttachmentStorage:
    """Contained staged/active attachment bytes under a configured FILES_DIR."""

    def __init__(
        self,
        files_dir: str | Path,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        root = Path(files_dir).expanduser()
        self._root: Path = root.resolve(strict=False)
        self._chunk_size = chunk_size
        self._ops = ContainedPathOps(self._root)
        self._ops.ensure_layout()

    @property
    def files_dir(self) -> Path:
        """Resolved FILES_DIR root (for tests/health; not a public path API)."""
        return self._root

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

    def staged_path_for(self, attachment_id: UUID) -> str:
        """Return the service-relative staged path for an attachment id."""
        return service_path_for(STAGED_AREA, attachment_id)

    def active_path_for(self, attachment_id: UUID) -> str:
        """Return the service-relative active path for an attachment id."""
        return service_path_for(ACTIVE_AREA, attachment_id)

    async def stage(
        self, attachment_id: UUID, content: AsyncIterator[bytes]
    ) -> StoredFile:
        """Write content into the staged area using a temporary partial file.

        On cancellation or error the partial file is removed so staging never
        leaves a promoted partial under the active area. Publication never
        overwrites an existing staged logical object.
        """
        rel = self.staged_path_for(attachment_id)
        area, name = parse_service_storage_path(rel)
        if area != STAGED_AREA:
            raise AttachmentStorageStateError(safe_message("not staged"))

        # Collision check under verified area (sync critical section).
        def _precheck() -> None:
            area_dir = self._ops.area_dir(STAGED_AREA)
            dest = area_dir / name
            if self._ops_is_present(dest):
                raise AttachmentStorageCollisionError(safe_message("collision"))

        await asyncio.to_thread(_precheck)

        partial_name = f"{name}.{uuid4().hex}{PARTIAL_SUFFIX}"
        fd: int | None = None
        size = 0
        try:
            fd = await asyncio.to_thread(
                self._ops.create_partial_fd, STAGED_AREA, partial_name
            )

            async for raw in content:
                chunk = coerce_chunk(raw)
                if not chunk:
                    continue
                written = await asyncio.to_thread(write_all, fd, chunk)
                size += written

            # Final validation + fsync + handle rename; no await inside ops.
            await asyncio.to_thread(
                self._ops.finalize_partial_to_name, fd, STAGED_AREA, name
            )
            fd = None

            def _confirm() -> None:
                area_dir = self._ops.area_dir(STAGED_AREA)
                published = area_dir / name
                if not published.is_file() or self._ops_is_link(published):
                    raise AttachmentStorageIOError(safe_message("stage failed"))

            await asyncio.to_thread(_confirm)
            return StoredFile(storage_path=rel, size_bytes=size)
        except AttachmentStorageError:
            await asyncio.to_thread(self._abort, fd, STAGED_AREA, partial_name)
            raise
        except BaseException:
            await asyncio.to_thread(self._abort, fd, STAGED_AREA, partial_name)
            raise

    async def promote(self, storage_path: str) -> str:
        """Atomically move a staged object into the active area without overwrite."""
        area, name = parse_service_storage_path(storage_path)
        if area != STAGED_AREA:
            raise AttachmentStorageStateError(safe_message("not staged"))

        def _promote_sync() -> str:
            src_area = self._ops.area_dir(STAGED_AREA)
            src = src_area / name
            if self._ops_is_link(src):
                raise InvalidStoragePathError(safe_message("invalid path"))
            if not self._ops_is_present(src):
                raise AttachmentStorageNotFoundError(safe_message("not found"))
            if not src.is_file():
                raise InvalidStoragePathError(safe_message("invalid path"))
            self._ops.area_dir(ACTIVE_AREA)
            self._ops.publish_across_areas(STAGED_AREA, name, ACTIVE_AREA, name)
            active_rel = service_path_for(ACTIVE_AREA, UUID(name))
            published = self._ops.area_dir(ACTIVE_AREA) / name
            if not published.is_file() or self._ops_is_link(published):
                raise AttachmentStorageIOError(safe_message("promote failed"))
            return active_rel

        return await asyncio.to_thread(_promote_sync)

    async def delete(self, storage_path: str) -> None:
        """Delete a staged or active object. Missing targets are a no-op."""
        area, name = parse_service_storage_path(storage_path)

        def _delete_sync() -> None:
            self._ops.unlink_leaf(area, name)

        await asyncio.to_thread(_delete_sync)

    async def open(self, storage_path: str) -> AsyncIterator[bytes]:
        """Return an async iterator bound to a single open file descriptor."""
        area, name = parse_service_storage_path(storage_path)

        def _open_sync() -> int:
            return self._ops.open_readonly_fd(area, name)

        fd = await asyncio.to_thread(_open_sync)
        return self._iter_fd_chunks(fd)

    async def _iter_fd_chunks(self, fd: int) -> AsyncIterator[bytes]:
        """Yield file content from a stable FD; never reopen a pathname."""
        try:
            while True:
                try:
                    block = await asyncio.to_thread(self._read_fd, fd)
                except AttachmentStorageError:
                    raise
                if not block:
                    break
                yield block
        finally:
            try:
                await asyncio.to_thread(self._close_fd_quiet, fd)
            except Exception:
                pass

    def _read_fd(self, fd: int) -> bytes:
        try:
            return os_read(fd, self._chunk_size)
        except OSError as exc:
            raise sanitize_os_error(exc) from None

    @staticmethod
    def _close_fd_quiet(fd: int) -> None:
        import os

        try:
            os.close(fd)
        except OSError:
            pass

    def _abort(self, fd: int | None, area: str, partial_name: str) -> None:
        partial_path = self._root / area / partial_name
        self._ops.abort_fd(fd, partial_path)

    @staticmethod
    def _ops_is_present(path: Path) -> bool:
        from app.services.attachment_storage_containment import path_exists_lexically

        return path_exists_lexically(path)

    @staticmethod
    def _ops_is_link(path: Path) -> bool:
        from app.services.attachment_storage_containment import is_link_like

        return is_link_like(path)


def os_read(fd: int, n: int) -> bytes:
    import os

    return os.read(fd, n)


async def iter_byte_chunks(
    data: bytes, *, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> AsyncIterator[bytes]:
    """Yield ``data`` in chunks (test helper and small in-process sources)."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not data:
        return
    for offset in range(0, len(data), chunk_size):
        yield data[offset : offset + chunk_size]
