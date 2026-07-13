"""Filesystem-only attachment storage rooted at ``FILES_DIR``.

Owns path safety and atomic create/replace primitives. Does not parse PDFs,
compute hashes, create drafts, or mutate database state.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO

# Lowercase UUID v4 text, matching ``app.core.ids.new_uuid`` output.
_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class PathEscapeError(ValueError):
    """Raised when a path is absolute, traverses, or escapes the storage root."""


class AttachmentStorage:
    """UUID-rooted atomic file store under a single configured root directory."""

    def __init__(self, files_dir: str | Path) -> None:
        self._root = Path(files_dir).expanduser().resolve()

    @property
    def root(self) -> Path:
        """Absolute resolved storage root (``FILES_DIR``)."""
        return self._root

    def ensure_root(self) -> None:
        """Create the storage root if missing (no user file content written)."""
        self._root.mkdir(parents=True, exist_ok=True)

    def relative_path_for(self, attachment_id: str) -> str:
        """Return the database-facing relative path derived only from the UUID.

        Display/original filenames never participate in path construction.
        """
        if not isinstance(attachment_id, str) or not _UUID_V4_RE.fullmatch(
            attachment_id
        ):
            raise ValueError(
                "attachment_id must be a lowercase UUID v4 string from new_uuid()"
            )
        return attachment_id

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a stored relative path strictly beneath the configured root."""
        segment = self._require_safe_relative(relative_path)
        candidate = (self._root / segment).resolve()
        self._assert_under_root(candidate)
        return candidate

    def create_temp_file(self) -> Path:
        """Create an empty temporary file under the storage root for streaming.

        Callers stream validated bytes into this path, then either
        :meth:`promote_temp` (new UUID final) or :meth:`discard_temp`. The
        temporary name is never a UUID final path, so partial streams are never
        visible as attachment files.
        """
        self.ensure_root()
        fd, tmp_name = tempfile.mkstemp(
            prefix=".upload.",
            suffix=".tmp",
            dir=str(self._root),
        )
        try:
            os.close(fd)
        except OSError:
            self._best_effort_unlink(Path(tmp_name))
            raise
        return Path(tmp_name)

    def promote_temp(self, temp_path: Path, attachment_id: str) -> str:
        """Atomically move a completed temp file onto the UUID-derived path.

        Returns the database-facing relative path. On failure the temp sibling
        is cleaned best-effort and no partial final file is left behind when
        replace did not succeed.
        """
        if not isinstance(temp_path, Path):
            raise TypeError("temp_path must be a Path")
        relative = self.relative_path_for(attachment_id)
        self.ensure_root()
        final_path = self.resolve_path(relative)
        temp_resolved = temp_path.expanduser().resolve()
        self._assert_under_root(temp_resolved)
        if not temp_resolved.is_file():
            raise FileNotFoundError(f"temp file not found: {temp_path}")
        try:
            os.replace(temp_resolved, final_path)
        except Exception:
            self._best_effort_unlink(temp_resolved)
            # If replace failed, ensure no half-written final if platform left one.
            if final_path.exists() and not final_path.is_file():
                self._best_effort_unlink(final_path)
            raise
        return relative

    def discard_temp(self, temp_path: Path | None) -> None:
        """Best-effort delete of a streaming temporary file under the root."""
        if temp_path is None:
            return
        try:
            resolved = temp_path.expanduser().resolve()
            self._assert_under_root(resolved)
        except (OSError, PathEscapeError, ValueError):
            # Still attempt unlink of the original path when resolution fails.
            self._best_effort_unlink(temp_path if isinstance(temp_path, Path) else None)
            return
        self._best_effort_unlink(resolved)

    def write_bytes(self, attachment_id: str, data: bytes) -> str:
        """Atomically write ``data`` and return the relative storage path.

        Bytes are written to a temporary sibling, then replaced onto the final
        path only after a complete flush. Failed writes clean the temporary
        sibling and leave no final partial file.
        """
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data must be bytes")
        relative = self.relative_path_for(attachment_id)
        self.ensure_root()
        final_path = self.resolve_path(relative)
        tmp_path: Path | None = None
        fd: int | None = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{relative}.",
                suffix=".tmp",
                dir=str(self._root),
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "wb") as handle:
                fd = None  # ownership transferred to the file object
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            # Atomic replace when source and destination share a filesystem.
            os.replace(tmp_path, final_path)
            tmp_path = None  # successfully consumed by replace
        except Exception:
            self._best_effort_unlink(tmp_path)
            raise
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._best_effort_unlink(tmp_path)
        return relative

    def exists(self, relative_path: str) -> bool:
        """Return whether a previously stored relative path exists under root."""
        return self.resolve_path(relative_path).is_file()

    def open(self, relative_path: str) -> BinaryIO:
        """Open a stored file for binary reading (caller must close)."""
        path = self.resolve_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"attachment file not found: {relative_path}")
        return path.open("rb")

    def delete(self, relative_path: str) -> bool:
        """Best-effort delete of a stored file. Callers must invoke explicitly.

        Returns True when the target is absent after the attempt, including when
        the file was already missing (idempotent success). Returns False only on
        OS errors during unlink or when the file remains present afterward.
        Invalid/escaping paths still raise :class:`PathEscapeError` so callers
        cannot probe outside the root.
        """
        path = self.resolve_path(relative_path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        return not path.exists()

    def _require_safe_relative(self, relative_path: str) -> str:
        if not isinstance(relative_path, str) or not relative_path:
            raise PathEscapeError("relative_path must be a non-empty string")
        if "\x00" in relative_path:
            raise PathEscapeError("null byte in path")
        # Reject absolute forms (POSIX, Windows drive, UNC-ish).
        if relative_path.startswith(("/", "\\")):
            raise PathEscapeError("absolute paths are rejected")
        if len(relative_path) >= 2 and relative_path[1] == ":":
            raise PathEscapeError("absolute paths are rejected")
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise PathEscapeError("absolute paths are rejected")
        # Only a single path segment may be stored; never trust nested/relative.
        if relative_path in {".", ".."}:
            raise PathEscapeError("path traversal is rejected")
        if "/" in relative_path or "\\" in relative_path:
            raise PathEscapeError("path traversal or multi-segment paths rejected")
        if candidate.name != relative_path:
            raise PathEscapeError("unsafe relative path")
        if ".." in candidate.parts:
            raise PathEscapeError("path traversal is rejected")
        return relative_path

    def _assert_under_root(self, candidate: Path) -> None:
        root = self._root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PathEscapeError("path escapes storage root") from exc

    @staticmethod
    def _best_effort_unlink(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
