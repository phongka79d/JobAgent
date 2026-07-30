"""Source-grounding guard shared by AI and manual tailoring edits."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.cv_tailoring import (
    SourceBoundText,
    TailoredCVContent,
    TailoredItemPatch,
    TailoredPatchSet,
    TailoredSectionPatch,
)
from app.services.cv_tailoring_guard import (
    guard_manual_tailored_content,
    guard_tailored_patch,
)
from app.services.cv_tailoring_projection import project_tailoring_baseline

from tests.unit.test_cv_tailoring_projection import _document, _profile


@dataclass
class RecordingSemanticChecker:
    result: bool = True

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def supports(self, *, output_text: str, cited_evidence: list[str]) -> bool:
        self.calls.append((output_text, tuple(cited_evidence)))
        return self.result


def _baseline():
    return project_tailoring_baseline(
        _document(), profile=_profile(), source_hash="revision-a"
    )


def _bound(text: str, *fact_ids: str) -> SourceBoundText:
    return SourceBoundText(text=text, source_fact_ids=list(fact_ids))


def _patch_for(section_id: str, *, body: str, fact_ids: list[str]) -> TailoredPatchSet:
    baseline = _baseline()
    source = next(
        section
        for section in baseline.content.sections
        if section.id == section_id
    )
    item = source.items[0]
    return TailoredPatchSet(
        sections=[
            TailoredSectionPatch(
                section_id=section_id,
                items=[
                    TailoredItemPatch(
                        source_entry_id=item.source_entry_id,
                        title=item.title,
                        subtitle=item.subtitle,
                        date_text=item.date_text,
                        location=item.location,
                        body=_bound(body, *fact_ids),
                        bullets=item.bullets,
                        attributes=item.attributes,
                    )
                ],
            )
        ]
    )


def _body_fact_id(section_id: str) -> str:
    baseline = _baseline()
    return next(
        fact_id
        for fact_id, evidence in baseline.fact_bank.items()
        if evidence.section_id == section_id and evidence.field_path == "body"
    )


def test_truthful_reorder_or_omission_preserves_untargeted_sections() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    patch = _patch_for(
        "summary",
        body="Public-service systems specialist.",
        fact_ids=[fact_id],
    )
    guarded, issues = guard_tailored_patch(
        patch,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )
    assert issues == ()
    assert guarded is not None
    assert guarded.sections[1:] == baseline.content.sections[1:]

    omitted, omitted_issues = guard_tailored_patch(
        TailoredPatchSet(
            sections=[TailoredSectionPatch(section_id="summary", items=[])]
        ),
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )
    assert omitted_issues == ()
    assert omitted is not None
    assert omitted.sections[0].items == []


def test_unknown_cross_section_and_empty_provenance_are_rejected() -> None:
    baseline = _baseline()
    cases = [
        _patch_for("summary", body="Invented employer", fact_ids=["sf_missing"]),
        _patch_for(
            "summary",
            body="Synthetic civic award",
            fact_ids=[_body_fact_id("awards")],
        ),
        _patch_for("summary", body="Unsupported text", fact_ids=[]),
    ]
    expected = {"UNKNOWN_FACT", "CROSS_SECTION_FACT", "EMPTY_PROVENANCE"}
    observed: set[str] = set()
    for patch in cases:
        guarded, issues = guard_tailored_patch(
            patch,
            parent=baseline.content,
            allowed_section_ids=["summary"],
            fact_bank=baseline.fact_bank,
            approved_skill_labels=baseline.approved_skill_labels,
            semantic_checker=None,
        )
        assert guarded is None
        observed.update(issue.code for issue in issues)
    assert expected <= observed


def test_invented_number_link_and_approved_skill_are_rejected() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    for body in (
        "Improved by 35%",
        "Worked through 2030",
        "See https://invented.test",
        "Contact invented@example.test",
        "Used Python",
    ):
        guarded, issues = guard_tailored_patch(
            _patch_for("summary", body=body, fact_ids=[fact_id]),
            parent=baseline.content,
            allowed_section_ids=["summary"],
            fact_bank=baseline.fact_bank,
            approved_skill_labels=baseline.approved_skill_labels,
            semantic_checker=None,
        )
        assert guarded is None
        assert any(issue.code == "UNSUPPORTED_ANCHOR" for issue in issues)


def test_anchor_matching_uses_exact_tokens_not_substrings() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    original = baseline.fact_bank[fact_id]
    cases = [
        ("Improved by 20%", "Improved by 120%", baseline.approved_skill_labels),
        ("Used SQL", "Used NoSQL", ("SQL",)),
    ]
    for output, source, skills in cases:
        fact_bank = dict(baseline.fact_bank)
        fact_bank[fact_id] = original.model_copy(update={"source_text": source})
        guarded, issues = guard_tailored_patch(
            _patch_for("summary", body=output, fact_ids=[fact_id]),
            parent=baseline.content,
            allowed_section_ids=["summary"],
            fact_bank=fact_bank,
            approved_skill_labels=skills,
            semantic_checker=None,
        )
        assert guarded is None
        assert any(issue.code == "UNSUPPORTED_ANCHOR" for issue in issues)


def test_unknown_entry_attribute_and_target_coverage_are_rejected() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    unknown_entry = _patch_for(
        "summary",
        body="Public-service systems specialist.",
        fact_ids=[fact_id],
    )
    unknown_entry.sections[0].items[0].source_entry_id = "missing-entry"
    guarded, issues = guard_tailored_patch(
        unknown_entry,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )
    assert guarded is None
    assert any(issue.code == "SECTION_IDENTITY_CHANGED" for issue in issues)

    experience_fact = _body_fact_id("experience")
    changed_attribute = _patch_for(
        "experience",
        body="Improved planning workflows.",
        fact_ids=[experience_fact],
    )
    changed_attribute.sections[0].items[0].attributes[0].name = "renamed"
    guarded, issues = guard_tailored_patch(
        changed_attribute,
        parent=baseline.content,
        allowed_section_ids=["experience"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )
    assert guarded is None
    assert any(issue.code == "ATTRIBUTE_IDENTITY_CHANGED" for issue in issues)

    guarded, issues = guard_tailored_patch(
        _patch_for("summary", body="x", fact_ids=[fact_id]),
        parent=baseline.content,
        allowed_section_ids=["summary", "awards"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )
    assert guarded is None
    assert issues[0].code == "SECTION_IDENTITY_CHANGED"


def test_patch_section_bound_reports_content_bounds_before_identity() -> None:
    baseline = _baseline()
    patch = TailoredPatchSet(
        sections=[
            TailoredSectionPatch(section_id="summary", items=[])
            for _ in range(21)
        ]
    )

    guarded, issues = guard_tailored_patch(
        patch,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )

    assert guarded is None
    assert issues[0].code == "CONTENT_BOUNDS_EXCEEDED"


def test_semantic_checker_rejects_invented_employer_or_institution() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    checker = RecordingSemanticChecker(result=False)
    for body in ("Worked for Invented Employer", "Studied at Invented Institute"):
        guarded, issues = guard_tailored_patch(
            _patch_for("summary", body=body, fact_ids=[fact_id]),
            parent=baseline.content,
            allowed_section_ids=["summary"],
            fact_bank=baseline.fact_bank,
            approved_skill_labels=baseline.approved_skill_labels,
            semantic_checker=checker,
        )
        assert guarded is None
        assert any(issue.code == "UNSUPPORTED_ANCHOR" for issue in issues)


def test_semantic_checker_only_receives_changed_field_and_cited_evidence() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    checker = RecordingSemanticChecker(result=True)
    guarded, issues = guard_tailored_patch(
        _patch_for(
            "summary",
            body="Specialist in public-service systems.",
            fact_ids=[fact_id],
        ),
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=checker,
    )
    assert issues == ()
    assert guarded is not None
    assert checker.calls == [
        (
            "Specialist in public-service systems.",
            ("Public-service systems specialist.",),
        )
    ]


def test_changed_non_substring_fails_closed_without_a_semantic_checker() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")

    guarded, issues = guard_tailored_patch(
        _patch_for(
            "summary",
            body="Specialist in public-service systems.",
            fact_ids=[fact_id],
        ),
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )

    assert guarded is None
    assert any(issue.code == "UNSUPPORTED_ANCHOR" for issue in issues)


def test_manual_paraphrase_uses_deterministic_checks_without_provider_veto() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    manual = baseline.content.model_copy(deep=True)
    manual.sections[0].items[0].body = _bound(
        "Specialist in public-service systems.", fact_id
    )
    checker = RecordingSemanticChecker(result=False)

    guarded, issues = guard_manual_tailored_content(
        manual,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=checker,
    )

    assert issues == ()
    assert guarded is not None
    assert checker.calls == []


def test_manual_unsupported_claim_is_rejected_even_without_provider_veto() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    manual = baseline.content.model_copy(deep=True)
    manual.sections[0].items[0].body = _bound(
        "Led a banking migration program.", fact_id
    )
    checker = RecordingSemanticChecker(result=False)

    guarded, issues = guard_manual_tailored_content(
        manual,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=checker,
    )

    assert guarded is None
    assert any(issue.code == "UNSUPPORTED_ANCHOR" for issue in issues)
    assert checker.calls == []


def test_duplicate_fact_ids_are_rejected_after_in_memory_mutation() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    patch = _patch_for(
        "summary",
        body="Public-service systems specialist.",
        fact_ids=[fact_id],
    )
    patch.sections[0].items[0].body.source_fact_ids.append(fact_id)

    guarded, issues = guard_tailored_patch(
        patch,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )

    assert guarded is None
    assert any(issue.code == "UNKNOWN_FACT" for issue in issues)


def test_source_bound_text_limits_are_rechecked_after_in_memory_mutation() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    checker = RecordingSemanticChecker(result=True)

    oversized_text = _patch_for(
        "summary",
        body="Public-service systems specialist.",
        fact_ids=[fact_id],
    )
    oversized_text.sections[0].items[0].body.text = "x" * 4_001

    oversized_provenance = _patch_for(
        "summary",
        body="Public-service systems specialist.",
        fact_ids=[fact_id],
    )
    oversized_provenance.sections[0].items[0].body.source_fact_ids = [
        fact_id
    ] * 65

    for patch in (oversized_text, oversized_provenance):
        guarded, issues = guard_tailored_patch(
            patch,
            parent=baseline.content,
            allowed_section_ids=["summary"],
            fact_bank=baseline.fact_bank,
            approved_skill_labels=baseline.approved_skill_labels,
            semantic_checker=checker,
        )

        assert guarded is None
        assert issues[0].code == "CONTENT_BOUNDS_EXCEEDED"


def test_manual_content_uses_the_shared_guard_and_ignores_caller_item_ids() -> None:
    baseline = _baseline()
    fact_id = _body_fact_id("summary")
    manual = baseline.content.model_copy(deep=True)
    manual.sections[0].items[0].id = "caller-controlled-id"
    manual.sections[0].items[0].body = _bound("Used Python", fact_id)

    guarded, issues = guard_manual_tailored_content(
        manual,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )

    assert guarded is None
    assert any(issue.code == "UNSUPPORTED_ANCHOR" for issue in issues)


def test_manual_content_rejects_section_identity_changes_and_preserves_parent_header(
) -> None:
    baseline = _baseline()
    manual = baseline.content.model_copy(deep=True)
    manual.sections[0].heading = "Changed Summary"

    guarded, issues = guard_manual_tailored_content(
        manual,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )

    assert guarded is None
    assert any(issue.code == "SECTION_IDENTITY_CHANGED" for issue in issues)

    changed_header = baseline.content.model_copy(deep=True)
    changed_header.header.full_name = "Changed Candidate"
    header_guarded, header_issues = guard_manual_tailored_content(
        changed_header,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )
    assert header_guarded is None
    assert header_issues[0].path == "header"

    unchanged = TailoredCVContent.model_validate(baseline.content.model_dump())
    unchanged.sections[0].items[0].id = "caller-controlled-id"
    format_reference = {"marker": "REFERENCE_ONLY_SENTINEL_7429"}
    preserved, preserved_issues = guard_manual_tailored_content(
        unchanged,
        parent=baseline.content,
        allowed_section_ids=["summary"],
        fact_bank=baseline.fact_bank,
        approved_skill_labels=baseline.approved_skill_labels,
        semantic_checker=None,
    )
    assert preserved_issues == ()
    assert preserved is not None
    assert preserved.header == baseline.content.header
    assert preserved.sections[0].items[0].id == baseline.content.sections[0].items[0].id
    assert format_reference["marker"] not in preserved.model_dump_json()
