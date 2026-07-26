"""UUID-scoped path, promotion, read, and deletion contracts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.storage.attachments import PathEscapeError
from app.storage.cv_tailoring import TailoringArtifactStorage


@pytest.fixture
def files_root(tmp_path: Path) -> Path:
    root = tmp_path / "files"
    root.mkdir()
    return root


@pytest.fixture
def store(files_root: Path) -> TailoringArtifactStorage:
    return TailoringArtifactStorage(files_root)


def _stage(store: TailoringArtifactStorage, version_id: str) -> tuple[Path, Path]:
    staging = store.create_staging_dir(version_id=version_id)
    tex = staging / "resume.tex"
    pdf = staging / "resume.pdf"
    tex.write_text("synthetic tex", encoding="utf-8")
    pdf.write_bytes(b"%PDF-1.4 synthetic")
    return tex, pdf


def test_promote_returns_unique_relative_paths_and_opens_exact_artifacts(
    store: TailoringArtifactStorage, files_root: Path
) -> None:
    profile_id, session_id, version_id = new_uuid(), new_uuid(), new_uuid()
    staged_tex, staged_pdf = _stage(store, version_id)
    assert staged_tex.stat().st_dev == files_root.stat().st_dev

    paths = store.promote(
        profile_id=profile_id,
        session_id=session_id,
        version_id=version_id,
        staged_tex=staged_tex,
        staged_pdf=staged_pdf,
    )

    prefix = f"cv-tailoring/{profile_id}/{session_id}/{version_id}"
    assert paths.tex_relative_path == f"{prefix}/resume.tex"
    assert paths.pdf_relative_path == f"{prefix}/resume.pdf"
    with store.open_artifact(relative_path=paths.tex_relative_path) as handle:
        assert handle.read() == b"synthetic tex"
    with store.open_artifact(relative_path=paths.pdf_relative_path) as handle:
        assert handle.read().startswith(b"%PDF")
    assert not staged_tex.parent.exists()

    next_version = new_uuid()
    next_tex, next_pdf = _stage(store, next_version)
    next_paths = store.promote(
        profile_id=profile_id,
        session_id=session_id,
        version_id=next_version,
        staged_tex=next_tex,
        staged_pdf=next_pdf,
    )
    assert next_paths != paths


@pytest.mark.parametrize(
    "bad_id",
    ["", "not-a-uuid", "../escape", new_uuid().upper(), "0" * 36],
)
def test_all_id_components_require_lowercase_uuid_v4(
    store: TailoringArtifactStorage, bad_id: str
) -> None:
    good = new_uuid()
    with pytest.raises(ValueError):
        store.create_staging_dir(version_id=bad_id)
    with pytest.raises(ValueError):
        store.delete_version(
            profile_id=bad_id,
            session_id=good,
            version_id=good,
        )
    with pytest.raises(ValueError):
        store.delete_session(profile_id=good, session_id=bad_id)


@pytest.mark.parametrize(
    "bad_path",
    [
        "",
        "../resume.tex",
        "/tmp/resume.pdf",
        "C:/temp/resume.pdf",
        "cv-tailoring/not-a-uuid/x/y/resume.tex",
        "cv-tailoring/00000000-0000-4000-8000-000000000000/../resume.tex",
        f"cv-tailoring/{new_uuid()}/{new_uuid()}/{new_uuid()}/other.tex",
        f"cv-tailoring/{new_uuid()}/{new_uuid()}/{new_uuid()}/resume.log",
    ],
)
def test_resolve_and_open_reject_unowned_or_unexpected_paths(
    store: TailoringArtifactStorage, bad_path: str
) -> None:
    with pytest.raises((PathEscapeError, ValueError)):
        store.resolve_artifact(relative_path=bad_path)
    with pytest.raises((PathEscapeError, ValueError)):
        store.open_artifact(relative_path=bad_path)


def test_promote_rejects_unexpected_staged_names_and_existing_final(
    store: TailoringArtifactStorage
) -> None:
    profile_id, session_id, version_id = new_uuid(), new_uuid(), new_uuid()
    staging = store.create_staging_dir(version_id=version_id)
    wrong = staging / "payload.tex"
    wrong.write_text("x", encoding="utf-8")
    pdf = staging / "resume.pdf"
    pdf.write_bytes(b"pdf")
    with pytest.raises(ValueError, match="resume.tex"):
        store.promote(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
            staged_tex=wrong,
            staged_pdf=pdf,
        )
    assert not staging.exists()

    tex, pdf = _stage(store, version_id)
    store.promote(
        profile_id=profile_id,
        session_id=session_id,
        version_id=version_id,
        staged_tex=tex,
        staged_pdf=pdf,
    )
    tex, pdf = _stage(store, version_id)
    with pytest.raises(FileExistsError):
        store.promote(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
            staged_tex=tex,
            staged_pdf=pdf,
        )
    assert not tex.parent.exists()


def test_failed_second_replace_cleans_partial_final_and_staging(
    store: TailoringArtifactStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_id, session_id, version_id = new_uuid(), new_uuid(), new_uuid()
    tex, pdf = _stage(store, version_id)
    real_replace = os.replace
    calls = 0

    def fail_second(source: Any, destination: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated pdf promotion failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(OSError, match="pdf promotion"):
        store.promote(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
            staged_tex=tex,
            staged_pdf=pdf,
        )
    final_dir = store.root / profile_id / session_id / version_id
    assert not final_dir.exists()
    assert not tex.parent.exists()


def test_delete_version_and_session_are_repeatable_and_bounded(
    store: TailoringArtifactStorage
) -> None:
    profile_id, session_id, version_id = new_uuid(), new_uuid(), new_uuid()
    tex, pdf = _stage(store, version_id)
    paths = store.promote(
        profile_id=profile_id,
        session_id=session_id,
        version_id=version_id,
        staged_tex=tex,
        staged_pdf=pdf,
    )
    assert store.delete_version(
        profile_id=profile_id,
        session_id=session_id,
        version_id=version_id,
    )
    assert store.delete_version(
        profile_id=profile_id,
        session_id=session_id,
        version_id=version_id,
    )
    with pytest.raises(FileNotFoundError):
        store.open_artifact(relative_path=paths.tex_relative_path)
    assert store.delete_session(profile_id=profile_id, session_id=session_id)
    assert store.delete_session(profile_id=profile_id, session_id=session_id)


def test_symlink_escape_is_rejected(
    store: TailoringArtifactStorage, tmp_path: Path
) -> None:
    profile_id, session_id, version_id = new_uuid(), new_uuid(), new_uuid()
    outside = tmp_path / "outside"
    outside.mkdir()
    profile_path = store.root / profile_id
    store.root.mkdir(parents=True, exist_ok=True)
    try:
        profile_path.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    relative = f"cv-tailoring/{profile_id}/{session_id}/{version_id}/resume.tex"
    with pytest.raises(PathEscapeError):
        store.resolve_artifact(relative_path=relative)


def test_failed_promotion_never_cleans_through_a_symlinked_staging_parent(
    store: TailoringArtifactStorage, tmp_path: Path
) -> None:
    profile_id, session_id, version_id = new_uuid(), new_uuid(), new_uuid()
    outside = tmp_path / "outside-staging"
    outside_version = outside / version_id
    outside_version.mkdir(parents=True)
    tex = outside_version / "resume.tex"
    pdf = outside_version / "resume.pdf"
    sentinel = outside_version / "keep.txt"
    tex.write_text("outside", encoding="utf-8")
    pdf.write_bytes(b"outside")
    sentinel.write_text("must survive", encoding="utf-8")
    store.root.mkdir(parents=True, exist_ok=True)
    try:
        (store.root / ".staging").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    with pytest.raises(PathEscapeError):
        store.promote(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
            staged_tex=store.root / ".staging" / version_id / "resume.tex",
            staged_pdf=store.root / ".staging" / version_id / "resume.pdf",
        )
    assert sentinel.read_text(encoding="utf-8") == "must survive"


def test_cleanup_refuses_a_staging_directory_that_resolves_outside_root(
    store: TailoringArtifactStorage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_id, session_id, version_id = new_uuid(), new_uuid(), new_uuid()
    tex, pdf = _stage(store, version_id)
    staging = tex.parent
    sentinel = staging / "keep.txt"
    sentinel.write_text("must survive", encoding="utf-8")
    outside = tmp_path / "outside-resolution"
    outside.mkdir()
    real_resolve = Path.resolve

    def resolve_as_escape(self: Path, *args: Any, **kwargs: Any) -> Path:
        if self == staging:
            return outside
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_as_escape)
    with pytest.raises(PathEscapeError):
        store.promote(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
            staged_tex=tex,
            staged_pdf=pdf,
        )
    assert sentinel.read_text(encoding="utf-8") == "must survive"


def test_configured_artifact_root_cannot_resolve_outside_files_dir(
    files_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_root = files_root / "cv-tailoring"
    outside = tmp_path / "outside-root"
    outside.mkdir()
    real_resolve = Path.resolve

    def resolve_root_as_escape(self: Path, *args: Any, **kwargs: Any) -> Path:
        if self == configured_root:
            return outside
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_root_as_escape)
    escaped_store = TailoringArtifactStorage(files_root)
    with pytest.raises(PathEscapeError):
        escaped_store.create_staging_dir(version_id=new_uuid())
    assert list(outside.iterdir()) == []
