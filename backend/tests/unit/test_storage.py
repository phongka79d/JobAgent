"""Unit tests for UUID-rooted atomic attachment storage (Plan 2 §7.5)."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.storage.attachments import AttachmentStorage, PathEscapeError

# Forbidden imports: storage must stay filesystem-only.
_FORBIDDEN_IMPORT_PREFIXES = (
    "pypdf",
    "sqlalchemy",
    "app.db",
    "app.api",
    "app.graph",
    "fastapi",
)

# UUID v4 pattern used only to assert temps are not UUID finals.
_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


@pytest.fixture
def files_root(tmp_path: Path) -> Path:
    """Sanitized temporary FILES_DIR; never touches root .env or user data."""
    root = tmp_path / "files"
    root.mkdir()
    return root


@pytest.fixture
def store(files_root: Path) -> AttachmentStorage:
    return AttachmentStorage(files_root)


def test_relative_path_is_uuid_only_not_display_name(store: AttachmentStorage) -> None:
    attachment_id = new_uuid()
    display_name = "../../evil resume (final).pdf"
    relative = store.relative_path_for(attachment_id)
    assert relative == attachment_id
    assert display_name not in relative
    assert "/" not in relative
    assert "\\" not in relative
    assert relative == relative.lower()
    # Display name is not accepted as an attachment id / path key.
    with pytest.raises(ValueError):
        store.relative_path_for(display_name)


def test_write_returns_uuid_relative_path_and_ignores_display_name(
    store: AttachmentStorage, files_root: Path
) -> None:
    attachment_id = new_uuid()
    payload = b"%PDF-1.4 test-bytes"
    relative = store.write_bytes(attachment_id, payload)
    assert relative == attachment_id
    final = files_root / relative
    assert final.is_file()
    assert final.read_bytes() == payload
    # No file named after a display filename is created under the root.
    assert not any("resume" in p.name.lower() for p in files_root.iterdir())


def test_successful_write_visible_only_after_complete_replace(
    store: AttachmentStorage, files_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachment_id = new_uuid()
    final = files_root / attachment_id
    payload = b"complete-payload-xyz"
    seen_final_before_replace = False
    real_replace = os.replace

    def tracking_replace(src: Any, dst: Any) -> None:
        nonlocal seen_final_before_replace
        # Final path must not exist as the complete file until replace runs.
        seen_final_before_replace = final.exists()
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", tracking_replace)
    relative = store.write_bytes(attachment_id, payload)
    assert relative == attachment_id
    assert seen_final_before_replace is False
    assert final.is_file()
    assert final.read_bytes() == payload


def test_failed_write_cleans_temp_and_leaves_no_partial_final(
    store: AttachmentStorage, files_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachment_id = new_uuid()
    final = files_root / attachment_id

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        store.write_bytes(attachment_id, b"partial-should-not-land")

    assert not final.exists()
    leftovers = list(files_root.iterdir())
    assert leftovers == [], f"temporary siblings left behind: {leftovers}"


def test_interrupted_write_during_body_leaves_no_final(
    store: AttachmentStorage, files_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachment_id = new_uuid()
    final = files_root / attachment_id
    real_fdopen = os.fdopen

    def exploding_fdopen(*args: Any, **kwargs: Any) -> Any:
        handle = real_fdopen(*args, **kwargs)

        class Boom:
            def write(self, data: bytes) -> int:
                raise OSError("simulated disk full")

            def flush(self) -> None:
                return None

            def fileno(self) -> int:
                return handle.fileno()

            def __enter__(self) -> Boom:
                return self

            def __exit__(self, *exc: object) -> None:
                handle.close()

        return Boom()

    monkeypatch.setattr(os, "fdopen", exploding_fdopen)
    with pytest.raises(OSError, match="simulated disk full"):
        store.write_bytes(attachment_id, b"never-complete")

    assert not final.exists()
    assert list(files_root.iterdir()) == []


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.pdf",
        "..\\escape.pdf",
        "/etc/passwd",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "C:/Windows/System32/drivers/etc/hosts",
        "subdir/file.pdf",
        "a/../../b",
        "..",
        ".",
        "",
        "\x00uuid",
    ],
)
def test_path_accepting_methods_reject_traversal_and_absolute(
    store: AttachmentStorage, bad_path: str
) -> None:
    with pytest.raises(PathEscapeError):
        store.resolve_path(bad_path)
    with pytest.raises(PathEscapeError):
        store.exists(bad_path)
    with pytest.raises(PathEscapeError):
        store.open(bad_path)
    with pytest.raises(PathEscapeError):
        store.delete(bad_path)


def test_resolve_rejects_paths_that_escape_after_resolution(
    store: AttachmentStorage, files_root: Path
) -> None:
    # Single-segment names that cannot be our UUID policy still must stay under root.
    # Symlink-based escapes are covered when the resolved path leaves the root.
    outside = files_root.parent / "outside.txt"
    outside.write_bytes(b"secret")
    link_name = new_uuid()
    link_path = files_root / link_name
    try:
        link_path.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform/user")
    # If the platform follows the symlink on resolve, escape must be rejected.
    try:
        resolved = (files_root / link_name).resolve()
    except OSError:
        pytest.skip("could not resolve symlink")
    if resolved == outside.resolve():
        with pytest.raises(PathEscapeError):
            store.resolve_path(link_name)
    else:
        # Non-following platforms still keep the path under root.
        path = store.resolve_path(link_name)
        assert path == link_path.resolve()


def test_exists_and_open_behavior(
    store: AttachmentStorage, files_root: Path
) -> None:
    attachment_id = new_uuid()
    assert store.exists(attachment_id) is False
    with pytest.raises(FileNotFoundError):
        store.open(attachment_id)

    payload = b"readable-content"
    relative = store.write_bytes(attachment_id, payload)
    assert store.exists(relative) is True
    with store.open(relative) as handle:
        assert handle.read() == payload
    # Absolute resolved path stays under root.
    abs_path = store.resolve_path(relative)
    assert abs_path.is_relative_to(files_root.resolve())
    assert abs_path.read_bytes() == payload


def test_delete_is_best_effort_and_only_when_called(
    store: AttachmentStorage, files_root: Path
) -> None:
    attachment_id = new_uuid()
    relative = store.write_bytes(attachment_id, b"to-delete")
    final = files_root / relative
    assert final.is_file()

    # Deletion does not happen implicitly after write/open.
    with store.open(relative) as handle:
        assert handle.read() == b"to-delete"
    assert final.is_file()

    assert store.delete(relative) is True
    assert not final.exists()
    assert store.exists(relative) is False
    # Already-missing contract: delete is idempotent and returns True.
    assert store.delete(relative) is True
    never_written = new_uuid()
    assert store.exists(never_written) is False
    assert store.delete(never_written) is True


def test_delete_os_error_returns_false(
    store: AttachmentStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachment_id = new_uuid()
    relative = store.write_bytes(attachment_id, b"locked")
    original_unlink = Path.unlink

    def boom(self: Path, *args: Any, **kwargs: Any) -> None:
        # Fail only the stored file unlink; leave other Path.unlink uses alone.
        if self.name == relative:
            raise OSError("permission denied")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", boom)
    assert store.delete(relative) is False


def test_write_bytes_rejects_non_bytes(store: AttachmentStorage) -> None:
    with pytest.raises(TypeError):
        store.write_bytes(new_uuid(), "not-bytes")  # type: ignore[arg-type]


def test_create_temp_promote_and_discard(
    store: AttachmentStorage, files_root: Path
) -> None:
    """Streaming temp is never a UUID path; promote is atomic; discard cleans."""
    temp = store.create_temp_file()
    assert temp.is_file()
    assert (
        temp.parent == files_root.resolve()
        or temp.parent.resolve() == files_root.resolve()
    )
    assert not _UUID_V4_RE.fullmatch(temp.name)
    temp.write_bytes(b"%PDF-1.4 streamed")
    attachment_id = new_uuid()
    relative = store.promote_temp(temp, attachment_id)
    assert relative == attachment_id
    assert not temp.exists()
    final = files_root / attachment_id
    assert final.is_file()
    assert final.read_bytes() == b"%PDF-1.4 streamed"

    orphan = store.create_temp_file()
    orphan.write_bytes(b"to-discard")
    store.discard_temp(orphan)
    assert not orphan.exists()
    # UUID final untouched by discard of unrelated temp.
    assert final.is_file()


def test_promote_failed_leaves_no_final(
    store: AttachmentStorage, files_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp = store.create_temp_file()
    temp.write_bytes(b"data")
    attachment_id = new_uuid()
    final = files_root / attachment_id

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("simulated promote failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="simulated promote failure"):
        store.promote_temp(temp, attachment_id)
    assert not final.exists()


def test_module_has_no_parser_orm_or_service_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[2] / "app" / "storage" / "attachments.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
    for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
        for name in imported:
            assert not (
                name == forbidden or name.startswith(forbidden + ".")
            ), f"forbidden import {name!r} in attachments storage module"
    # Standard-library path/atomic primitives only for filesystem work.
    assert "os" in imported
    assert "tempfile" in imported
    assert "pathlib" in imported
