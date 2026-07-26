"""Deterministic baseline and source fact-bank projection."""

from __future__ import annotations

import pytest
from app.schemas.cv_document import CVDocument, CVEntry, CVSection
from app.schemas.profile import CandidateProfile
from app.services.cv_tailoring_projection import (
    project_tailoring_baseline,
    select_section_context,
    source_fact_id,
)

_ATTACHMENT_ID = "11111111-1111-4111-8111-111111111111"


def _entry(
    entry_id: str,
    ordinal: int,
    body: str,
    source_ordinal: int,
    **overrides: object,
) -> CVEntry:
    payload = {
        "id": entry_id,
        "ordinal": ordinal,
        "title": None,
        "subtitle": None,
        "date_text": None,
        "location": None,
        "body": body,
        "bullets": [],
        "attributes": {},
        "source_chunk_ordinals": [source_ordinal],
    }
    payload.update(overrides)
    return CVEntry.model_validate(payload)


def _document() -> CVDocument:
    specifications = [
        (
            "summary",
            "Summary",
            "summary",
            _entry("sum-1", 0, "Public-service systems specialist.", 0),
        ),
        (
            "experience",
            "Experience",
            "experience",
            _entry(
                "exp-1",
                0,
                "Improved planning workflows.",
                1,
                title="Operations Analyst",
                subtitle="Synthetic Transit Lab",
                date_text="2022–2025",
                location="Ha Noi",
                bullets=["Reduced review time by 20%."],
                attributes={
                    "portfolio_url": "https://example.test/work",
                    "tools": ["Python", "SQL"],
                    "key/with space": "synthetic value",
                    "empty_values": [],
                },
            ),
        ),
        ("skills", "Skills", "skills", _entry("skill-1", 0, "Python, SQL", 2)),
        (
            "awards",
            "Awards",
            "awards",
            _entry("award-1", 0, "Synthetic civic award", 3),
        ),
        ("other", "Community", "other", _entry("other-1", 0, "Volunteer mentor", 4)),
    ]
    sections = [
        CVSection(
            id=section_id,
            ordinal=ordinal,
            heading=heading,
            kind=kind,  # type: ignore[arg-type]
            entries=[entry],
            source_chunk_ordinals=[ordinal],
        )
        for ordinal, (section_id, heading, kind, entry) in enumerate(specifications)
    ]
    return CVDocument(
        attachment_id=_ATTACHMENT_ID,
        detected_languages=["en"],
        sections=sections,
        extraction_warnings=[],
        extraction_confidence=0.9,
    )


def _profile() -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "full_name": "Synthetic Candidate",
            "location": "Ha Noi",
            "phone": "+84 900 000 001",
            "email": "person@example.test",
            "github_url": None,
            "summary": "Public-service systems specialist.",
            "current_title": "Operations Analyst",
            "total_experience_years": 3.0,
            "skills": [
                {
                    "skill": {
                        "canonical_key": "python",
                        "display_name": "Python",
                        "aliases": [],
                        "category": "language",
                    },
                    "confidence": 0.9,
                    "proficiency": "advanced",
                    "years": 3.0,
                    "source": "cv",
                    "excluded": False,
                    "evidence": ["Python"],
                },
                {
                    "skill": {
                        "canonical_key": "legacy-tool",
                        "display_name": "Legacy Tool",
                        "aliases": [],
                        "category": None,
                    },
                    "confidence": 0.8,
                    "proficiency": "unknown",
                    "years": None,
                    "source": "user_correction",
                    "excluded": True,
                    "evidence": ["excluded"],
                },
            ],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.9,
        }
    )


def test_source_fact_ids_are_stable_and_revision_bound() -> None:
    first = source_fact_id(
        source_hash="revision-a",
        section_id="summary",
        entry_id="sum-1",
        field_path="body",
    )
    assert first == source_fact_id(
        source_hash="revision-a",
        section_id="summary",
        entry_id="sum-1",
        field_path="body",
    )
    assert first != source_fact_id(
        source_hash="revision-b",
        section_id="summary",
        entry_id="sum-1",
        field_path="body",
    )


def test_projector_preserves_dynamic_sections_values_and_header() -> None:
    baseline = project_tailoring_baseline(
        _document(), profile=_profile(), source_hash="revision-a"
    )
    assert [section.id for section in baseline.content.sections] == [
        "summary",
        "experience",
        "skills",
        "awards",
        "other",
    ]
    assert [section.heading for section in baseline.content.sections] == [
        "Summary",
        "Experience",
        "Skills",
        "Awards",
        "Community",
    ]
    assert baseline.content.header.full_name == "Synthetic Candidate"
    assert baseline.content.header.phone == "+84900000001"
    experience = baseline.content.sections[1].items[0]
    assert experience.title is not None
    assert experience.title.text == "Operations Analyst"
    assert [attribute.name for attribute in experience.attributes] == [
        "portfolio_url",
        "tools",
        "key/with space",
    ]
    assert [value.text for value in experience.attributes[1].values] == [
        "Python",
        "SQL",
    ]
    field_paths = {evidence.field_path for evidence in baseline.fact_bank.values()}
    assert "bullets[0]" in field_paths
    assert "attributes.portfolio_url[0]" in field_paths
    assert "attributes.tools[1]" in field_paths
    assert "attributes.key%2Fwith%20space[0]" in field_paths
    assert baseline.approved_skill_labels == ("Python",)
    assert baseline.fact_bank


def test_projection_is_stable_and_source_revision_changes_fact_ids() -> None:
    first = project_tailoring_baseline(
        _document(), profile=_profile(), source_hash="revision-a"
    )
    repeated = project_tailoring_baseline(
        _document(), profile=_profile(), source_hash="revision-a"
    )
    changed = project_tailoring_baseline(
        _document(), profile=_profile(), source_hash="revision-b"
    )
    assert first == repeated
    assert set(first.fact_bank) != set(changed.fact_bank)


def test_empty_structural_text_has_no_fact_and_reference_marker_has_no_task_two_route(
) -> None:
    document = _document()
    summary = document.sections[0]
    empty_entry = summary.entries[0].model_copy(update={"body": ""})
    document = document.model_copy(
        update={
            "sections": [
                summary.model_copy(update={"entries": [empty_entry]}),
                *document.sections[1:],
            ]
        }
    )
    format_reference = {"marker": "REFERENCE_ONLY_SENTINEL_7429"}

    baseline = project_tailoring_baseline(
        document,
        profile=_profile(),
        source_hash="revision-a",
    )

    marker = format_reference["marker"]
    sections, facts = select_section_context(baseline, section_ids=["summary"])

    assert baseline.content.sections[0].items[0].body.source_fact_ids == []
    assert marker not in baseline.content.model_dump_json()
    assert marker not in str([section.model_dump(mode="json") for section in sections])
    assert marker not in str(
        [evidence.model_dump(mode="json") for evidence in facts.values()]
    )


def test_select_section_context_rejects_unknown_or_duplicate_and_hides_others() -> None:
    baseline = project_tailoring_baseline(
        _document(), profile=_profile(), source_hash="revision-a"
    )
    sections, facts = select_section_context(
        baseline,
        section_ids=["experience", "awards"],
    )
    assert [section.id for section in sections] == ["experience", "awards"]
    assert {fact.section_id for fact in facts.values()} == {"experience", "awards"}
    assert "Volunteer mentor" not in str(sections)
    with pytest.raises(ValueError):
        select_section_context(baseline, section_ids=["missing"])
    with pytest.raises(ValueError):
        select_section_context(baseline, section_ids=["awards", "awards"])
