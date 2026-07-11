"""Canonical service-path grammar tests (authoritative UUID-leaf validator)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from app.services.attachment_storage import (
    InvalidStoragePathError,
    parse_service_storage_path,
    require_canonical_service_path,
)
from tests.services.attachment_helpers import assert_no_abs_disclosure


def test_parse_accepts_canonical_uuid_service_paths() -> None:
    aid = uuid4()
    assert parse_service_storage_path(f"staged/{aid}") == ("staged", str(aid))
    assert parse_service_storage_path(f"active/{aid}") == ("active", str(aid))


def test_parse_rejects_non_uuid_leaves() -> None:
    for bad in ("staged/abc", "active/abc-def", "staged/not-a-uuid"):
        with pytest.raises(InvalidStoragePathError):
            parse_service_storage_path(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "staged",
        "staged/",
        "other/x",
        "../staged/x",
        "staged/../active",
        "staged/a/b",
        "staged\\x",
        "/staged/x",
        "\\staged\\x",
        "C:/staged/x",
        "C:\\staged\\x",
        "staged/x.partial",
        "staged/.",
        "staged/..",
        "  staged/x",
        "staged/x  ",
        "staged/x\x00y",
        "staged/CON",
        "staged/nul",
        "staged/%2e%2e",
    ],
)
def test_parse_rejects_traversal_absolute_and_malformed(bad: str) -> None:
    with pytest.raises(InvalidStoragePathError) as ei:
        parse_service_storage_path(bad)
    assert_no_abs_disclosure(ei.value, Path.cwd())


def test_parse_rejects_noncanonical_uuid_spellings() -> None:
    aid = uuid4()
    with pytest.raises(InvalidStoragePathError):
        parse_service_storage_path(f"staged/{str(aid).upper()}")
    with pytest.raises(InvalidStoragePathError):
        parse_service_storage_path(f"staged/{{{aid}}}")
    with pytest.raises(InvalidStoragePathError):
        parse_service_storage_path(f"staged/urn:uuid:{aid}")


def test_require_canonical_matches_attachment_id() -> None:
    aid = uuid4()
    assert (
        require_canonical_service_path(f"staged/{aid}", aid, expected_area="staged")
        == f"staged/{aid}"
    )
    with pytest.raises(InvalidStoragePathError):
        require_canonical_service_path(f"staged/{aid}", aid, expected_area="active")
    with pytest.raises(InvalidStoragePathError):
        require_canonical_service_path(f"staged/{uuid4()}", aid, expected_area="staged")


def test_windows_absolute_variants_rejected() -> None:
    if sys.platform != "win32":
        pytest.skip("windows-specific absolute forms")
    for bad in (r"C:\Windows\System32\drivers\etc\hosts", r"\\?\C:\secrets"):
        with pytest.raises(InvalidStoragePathError):
            parse_service_storage_path(bad)
