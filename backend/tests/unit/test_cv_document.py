"""Strict CVDocument / CVSection / CVEntry schema tests (Plan 9 02A)."""

from __future__ import annotations

from typing import Any

import pytest
from app.schemas.cv_document import (
    CV_SECTION_KINDS,
    CVDocument,
    CVEntry,
    CVSection,
    parse_cv_document,
)
from pydantic import ValidationError

_ATTACHMENT = "11111111-1111-4111-8111-111111111111"


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "cv-document-v1:s0:e0:role",
        "ordinal": 0,
        "title": "Role",
        "subtitle": "Acme",
        "date_text": "2019",
        "location": None,
        "body": "Built APIs",
        "bullets": ["Python"],
        "attributes": {"team": "platform"},
        "source_chunk_ordinals": [0],
    }
    base.update(overrides)
    return base


def _section(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "cv-document-v1:s0:experience",
        "ordinal": 0,
        "heading": "Experience",
        "kind": "experience",
        "entries": [_entry()],
        "source_chunk_ordinals": [0],
    }
    base.update(overrides)
    return base


def _document(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "attachment_id": _ATTACHMENT,
        "detected_languages": ["en"],
        "sections": [_section()],
        "extraction_warnings": [],
        "extraction_confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_section_kinds_match_master_vocabulary() -> None:
    assert "certifications" in CV_SECTION_KINDS
    assert "other" in CV_SECTION_KINDS
    assert "memberships" not in CV_SECTION_KINDS


def test_valid_document_preserves_dynamic_content() -> None:
    cert_entry = _entry(
        id="cv-document-v1:s0:e0:aws",
        title="AWS Certified Solutions Architect",
        body="Issued 2022",
        bullets=[],
        attributes={"credential_id": "ABCD-1234"},
        source_chunk_ordinals=[1],
    )
    membership = _entry(
        id="cv-document-v1:s1:e0:acm",
        title="ACM",
        body="Member since 2018",
        bullets=[],
        attributes={},
        source_chunk_ordinals=[2],
    )
    doc = parse_cv_document(
        _document(
            sections=[
                _section(
                    id="cv-document-v1:s0:certifications",
                    ordinal=0,
                    heading="Certifications",
                    kind="certifications",
                    entries=[cert_entry],
                    source_chunk_ordinals=[1],
                ),
                _section(
                    id="cv-document-v1:s1:memberships",
                    ordinal=1,
                    heading="Memberships",
                    kind="other",
                    entries=[membership],
                    source_chunk_ordinals=[2],
                ),
            ]
        )
    )
    assert doc.sections[0].heading == "Certifications"
    assert doc.sections[0].kind == "certifications"
    assert doc.sections[0].entries[0].attributes["credential_id"] == "ABCD-1234"
    assert doc.sections[1].heading == "Memberships"
    assert doc.sections[1].kind == "other"
    assert doc.sections[1].entries[0].body == "Member since 2018"


def test_rejects_invalid_attachment_id() -> None:
    with pytest.raises(ValidationError):
        parse_cv_document(_document(attachment_id="not-a-uuid"))


def test_rejects_non_contiguous_section_ordinals() -> None:
    with pytest.raises(ValidationError):
        parse_cv_document(
            _document(
                sections=[
                    _section(ordinal=0),
                    _section(
                        id="cv-document-v1:s1:skills",
                        ordinal=2,
                        heading="Skills",
                        kind="skills",
                        entries=[
                            _entry(
                                id="x",
                                ordinal=0,
                                source_chunk_ordinals=[0],
                            )
                        ],
                        source_chunk_ordinals=[0],
                    ),
                ]
            )
        )


def test_rejects_unsorted_source_ordinals() -> None:
    with pytest.raises(ValidationError):
        CVEntry.model_validate(_entry(source_chunk_ordinals=[2, 1]))


def test_rejects_duplicate_source_ordinals() -> None:
    with pytest.raises(ValidationError):
        CVEntry.model_validate(_entry(source_chunk_ordinals=[1, 1]))


def test_rejects_negative_source_ordinal() -> None:
    with pytest.raises(ValidationError):
        CVEntry.model_validate(_entry(source_chunk_ordinals=[-1]))


def test_rejects_entry_sources_outside_section() -> None:
    with pytest.raises(ValidationError):
        CVSection.model_validate(
            _section(
                source_chunk_ordinals=[0],
                entries=[_entry(source_chunk_ordinals=[0, 1])],
            )
        )


def test_rejects_section_source_union_mismatch() -> None:
    with pytest.raises(ValidationError):
        CVSection.model_validate(
            _section(
                source_chunk_ordinals=[0, 1],
                entries=[_entry(source_chunk_ordinals=[0])],
            )
        )


def test_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        CVSection.model_validate(_section(kind="memberships"))


def test_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        parse_cv_document(_document(extraction_confidence=1.5))
    with pytest.raises(ValidationError):
        parse_cv_document(_document(extraction_confidence=-0.1))


def test_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        parse_cv_document(_document(extra_field=True))


def test_attribute_list_values_preserved() -> None:
    entry = CVEntry.model_validate(
        _entry(attributes={"topics": ["a", "b"], "note": "x"})
    )
    assert entry.attributes["topics"] == ["a", "b"]
    assert entry.attributes["note"] == "x"


def test_cv_document_model_fields() -> None:
    fields = set(CVDocument.model_fields)
    assert fields == {
        "attachment_id",
        "detected_languages",
        "sections",
        "extraction_warnings",
        "extraction_confidence",
    }
