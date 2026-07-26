"""UUID-scoped filesystem owner for rendered CV-tailoring artifacts."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.storage.attachments import PathEscapeError

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_ARTIFACT_FILENAMES = frozenset({"resume.tex", "resume.pdf"})


@dataclass(frozen=True, slots=True)
class TailoringArtifactPaths:
    tex_relative_path: str
    pdf_relative_path: str


class TailoringArtifactStorage:
    """Same-filesystem staging and immutable artifact promotion under FILES_DIR."""

    def __init__(self, files_dir: str | Path) -> None:
        self._files_root = Path(files_dir).expanduser().resolve()
        self._root = self._files_root / "cv-tailoring"

    @property
    def root(self) -> Path:
        return self._root

    def create_staging_dir(self, *, version_id: str) -> Path:
        version_id = self._require_uuid("version_id", version_id)
        self._ensure_root()
        staging_root = self._root / ".staging"
        staging_root.mkdir(exist_ok=True)
        self._assert_under_root(staging_root.resolve())
        staging = staging_root / version_id
        staging.mkdir(exist_ok=False)
        if staging.stat().st_dev != self._root.stat().st_dev:
            self._remove_tree(staging)
            raise OSError("tailoring staging must share the artifact filesystem")
        return staging

    def promote(
        self,
        *,
        profile_id: str,
        session_id: str,
        version_id: str,
        staged_tex: Path,
        staged_pdf: Path,
    ) -> TailoringArtifactPaths:
        profile_id = self._require_uuid("profile_id", profile_id)
        session_id = self._require_uuid("session_id", session_id)
        version_id = self._require_uuid("version_id", version_id)
        self._ensure_root()
        staging = self._root / ".staging" / version_id
        final_dir = self._safe_version_dir(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
        )
        created_final = False
        try:
            tex = self._require_staged_file(
                staged_tex,
                staging=staging,
                filename="resume.tex",
            )
            pdf = self._require_staged_file(
                staged_pdf,
                staging=staging,
                filename="resume.pdf",
            )
            root_device = self._root.stat().st_dev
            if tex.stat().st_dev != root_device or pdf.stat().st_dev != root_device:
                raise OSError(
                    "tailoring staging must share the artifact filesystem"
                )
            if final_dir.exists():
                raise FileExistsError("tailoring artifact version already exists")
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            self._assert_under_root(final_dir.parent.resolve())
            final_dir.mkdir()
            created_final = True
            os.replace(tex, final_dir / "resume.tex")
            os.replace(pdf, final_dir / "resume.pdf")
        except Exception:
            if created_final:
                self._remove_tree(final_dir)
            raise
        finally:
            self._remove_tree(staging)

        prefix = PurePosixPath(
            "cv-tailoring", profile_id, session_id, version_id
        )
        return TailoringArtifactPaths(
            tex_relative_path=(prefix / "resume.tex").as_posix(),
            pdf_relative_path=(prefix / "resume.pdf").as_posix(),
        )

    def open_artifact(self, *, relative_path: str) -> BinaryIO:
        path = self.resolve_artifact(relative_path=relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"tailoring artifact not found: {relative_path}")
        return path.open("rb")

    def resolve_artifact(self, *, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path:
            raise PathEscapeError("relative_path must be a non-empty string")
        if "\\" in relative_path or "\x00" in relative_path:
            raise PathEscapeError("unsafe tailoring artifact path")
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 5:
            raise PathEscapeError("unsafe tailoring artifact path")
        prefix, profile_id, session_id, version_id, filename = pure.parts
        if prefix != "cv-tailoring" or filename not in _ARTIFACT_FILENAMES:
            raise ValueError("unexpected tailoring artifact path")
        self._require_uuid("profile_id", profile_id)
        self._require_uuid("session_id", session_id)
        self._require_uuid("version_id", version_id)
        candidate = self._root / profile_id / session_id / version_id / filename
        if candidate.is_symlink():
            raise PathEscapeError("tailoring artifact symlinks are rejected")
        resolved = candidate.resolve()
        self._assert_under_root(resolved)
        return resolved

    def delete_version(
        self, *, profile_id: str, session_id: str, version_id: str
    ) -> bool:
        profile_id = self._require_uuid("profile_id", profile_id)
        session_id = self._require_uuid("session_id", session_id)
        version_id = self._require_uuid("version_id", version_id)
        version_dir = self._safe_version_dir(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
        )
        if not self._remove_tree(version_dir):
            return False
        self._remove_empty_parents(version_dir.parent, stop=self._root)
        return True

    def delete_session(self, *, profile_id: str, session_id: str) -> bool:
        profile_id = self._require_uuid("profile_id", profile_id)
        session_id = self._require_uuid("session_id", session_id)
        candidate = (self._root / profile_id / session_id).resolve()
        self._assert_under_root(candidate)
        if not self._remove_tree(candidate):
            return False
        self._remove_empty_parents(candidate.parent, stop=self._root)
        return True

    def _safe_version_dir(
        self, *, profile_id: str, session_id: str, version_id: str
    ) -> Path:
        candidate = (self._root / profile_id / session_id / version_id).resolve()
        self._assert_under_root(candidate)
        return candidate

    def _require_staged_file(
        self, path: Path, *, staging: Path, filename: str
    ) -> Path:
        if not isinstance(path, Path):
            raise TypeError(f"staged {filename} must be a Path")
        if path.name != filename:
            raise ValueError(f"staged artifact must be named {filename}")
        if path.is_symlink():
            raise PathEscapeError("staged artifact symlinks are rejected")
        resolved = path.expanduser().resolve()
        expected_parent = staging.resolve()
        self._assert_under_root(resolved)
        if resolved.parent != expected_parent or not resolved.is_file():
            raise PathEscapeError("staged artifact is outside its version directory")
        return resolved

    def _ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._resolved_root()

    def _assert_under_root(self, candidate: Path) -> None:
        try:
            candidate.relative_to(self._resolved_root())
        except ValueError as exc:
            raise PathEscapeError("path escapes tailoring artifact root") from exc

    def _resolved_root(self) -> Path:
        if self._root.is_symlink():
            raise PathEscapeError("tailoring artifact root cannot be a symlink")
        resolved = self._root.resolve()
        try:
            resolved.relative_to(self._files_root)
        except ValueError as exc:
            raise PathEscapeError(
                "tailoring artifact root escapes FILES_DIR"
            ) from exc
        return resolved

    @staticmethod
    def _require_uuid(name: str, value: str) -> str:
        if not isinstance(value, str) or not _UUID_V4_RE.fullmatch(value):
            raise ValueError(f"{name} must be a lowercase UUID v4 string")
        return value

    def _remove_tree(self, path: Path) -> bool:
        try:
            if path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.exists():
                resolved = path.resolve()
                self._assert_under_root(resolved)
                shutil.rmtree(resolved)
        except (OSError, PathEscapeError):
            return False
        return not path.exists()

    @staticmethod
    def _remove_empty_parents(start: Path, *, stop: Path) -> None:
        current = start
        while current != stop:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent


__all__ = ["TailoringArtifactPaths", "TailoringArtifactStorage"]
