"""Bounded all-section Candidate skill assertion extraction."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from app.schemas.cv_document import CVDocument, CVEntry, CVSection
from app.services.skill_normalization import SkillNormalizer

_ATTACHMENT = "00000000-0000-4000-8000-000000000016"
_SEED = Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"


def _module() -> ModuleType:
    assert importlib.util.find_spec("app.services.cv_skill_projection") is not None, (
        "Candidate skill projection module is missing"
    )
    return importlib.import_module("app.services.cv_skill_projection")


class ScriptedSkillInvoker:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        schema_name: str,
        is_repair: bool = False,
    ) -> Any:
        joined = "\n".join(
            content
            for message in messages
            if isinstance((content := getattr(message, "content", None)), str)
        )
        self.calls.append(
            {
                "schema_name": schema_name,
                "is_repair": is_repair,
                "joined": joined,
            }
        )
        if not self.script:
            raise RuntimeError("skill script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _entry(
    entry_id: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    body: str = "",
    bullets: list[str] | None = None,
) -> CVEntry:
    return CVEntry(
        id=entry_id,
        ordinal=0,
        title=title,
        subtitle=subtitle,
        date_text=None,
        location=None,
        body=body,
        bullets=list(bullets or []),
        attributes={},
        source_chunk_ordinals=[0],
    )


def _section(
    section_id: str,
    ordinal: int,
    heading: str,
    kind: str,
    entry: CVEntry,
) -> CVSection:
    return CVSection(
        id=section_id,
        ordinal=ordinal,
        heading=heading,
        kind=kind,  # type: ignore[arg-type]
        entries=[entry],
        source_chunk_ordinals=[0],
    )


def _document(*sections: CVSection) -> CVDocument:
    return CVDocument(
        attachment_id=_ATTACHMENT,
        detected_languages=["en"],
        sections=list(sections),
        extraction_warnings=[],
        extraction_confidence=0.9,
    )


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(_SEED)


def _assertion(
    name: str,
    evidence: str,
    entry_id: str,
    *,
    confidence: float = 0.8,
    proficiency: str = "unknown",
    years: float | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "confidence": confidence,
        "proficiency": proficiency,
        "years": years,
        "evidence": [evidence],
        "source_entry_ids": [entry_id],
    }


def test_extracts_atomic_skills_from_every_section_kind() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    assert callable(extract)
    document = _document(
        _section(
            "summary",
            0,
            "Profile",
            "summary",
            _entry(
                "summary-entry",
                body="Campaign Strategy leader with SEO experience.",
            ),
        ),
        _section(
            "experience",
            1,
            "Work History",
            "experience",
            _entry(
                "experience-entry",
                title="Finance Manager",
                body="Owned Revenue Forecasting for regional planning.",
            ),
        ),
        _section(
            "other",
            2,
            "Community Practice",
            "other",
            _entry(
                "other-entry",
                body="Applied Stakeholder Facilitation across partner groups.",
            ),
        ),
        _section(
            "projects",
            3,
            "Selected Work",
            "projects",
            _entry(
                "project-entry",
                body="Used Journey Mapping and Service Design/Research in discovery.",
            ),
        ),
        _section(
            "certifications",
            4,
            "Learning",
            "certifications",
            _entry(
                "certification-entry",
                title="Professional Certificate",
                body="Coursework applied Financial Modelling to planning cases.",
            ),
        ),
        _section(
            "bilingual",
            5,
            "Thực hành",
            "other",
            _entry(
                "bilingual-entry",
                body="Phụ trách Hoạch định ngân sách cho hoạt động khu vực.",
            ),
        ),
    )
    invoker = ScriptedSkillInvoker(
        [
            {
                "assertions": [
                    _assertion(
                        "Campaign Strategy",
                        "Campaign Strategy leader",
                        "summary-entry",
                    ),
                    _assertion("SEO", "SEO experience", "summary-entry"),
                    _assertion(
                        "Revenue Forecasting",
                        "Revenue Forecasting",
                        "experience-entry",
                    ),
                    _assertion(
                        "Stakeholder Facilitation",
                        "Stakeholder Facilitation",
                        "other-entry",
                    ),
                    _assertion(
                        "Journey Mapping",
                        "Journey Mapping",
                        "project-entry",
                    ),
                    _assertion(
                        "Service Design/Research",
                        "Service Design/Research",
                        "project-entry",
                    ),
                    _assertion(
                        "Financial Modelling",
                        "Financial Modelling",
                        "certification-entry",
                    ),
                    _assertion(
                        "Hoạch định ngân sách",
                        "Hoạch định ngân sách",
                        "bilingual-entry",
                    ),
                ]
            }
        ]
    )

    outcome = extract(document, invoker=invoker, normalizer=_normalizer())

    assert [item.skill.canonical_key for item in outcome.skills] == [
        "campaign_strategy",
        "seo",
        "revenue_forecasting",
        "stakeholder_facilitation",
        "journey_mapping",
        "service_design_research",
        "financial_modelling",
        "hoạch_định_ngân_sách",
    ]
    assert [call["schema_name"] for call in invoker.calls] == ["candidate_skills"]
    joined = invoker.calls[0]["joined"]
    for heading in (
        "Profile",
        "Work History",
        "Community Practice",
        "Selected Work",
        "Learning",
        "Thực hành",
    ):
        assert heading in joined
    assert _ATTACHMENT not in joined


def test_name_grounded_in_selected_entry_does_not_need_to_repeat_in_evidence() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    assert callable(extract)
    document = _document(
        _section(
            "experience",
            0,
            "Work History",
            "experience",
            _entry(
                "experience-entry",
                body="Audience Segmentation improved retention across the region.",
            ),
        )
    )
    source_grounded = {
        "assertions": [
            _assertion(
                "Audience Segmentation",
                "improved retention across the region",
                "experience-entry",
            )
        ]
    }
    evidence_repeats_name = {
        "assertions": [
            _assertion(
                "Audience Segmentation",
                "Audience Segmentation improved retention",
                "experience-entry",
            )
        ]
    }
    invoker = ScriptedSkillInvoker([source_grounded, evidence_repeats_name])

    outcome = extract(document, invoker=invoker, normalizer=_normalizer())

    assert [item.skill.canonical_key for item in outcome.skills] == [
        "audience_segmentation"
    ]
    assert outcome.schema_repairs_used == 0
    assert [call["is_repair"] for call in invoker.calls] == [False]


def test_semantic_skill_label_with_grounded_evidence_is_accepted() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    assert callable(extract)
    document = _document(
        _section(
            "experience",
            0,
            "Work History",
            "experience",
            _entry(
                "experience-entry",
                body="Led stakeholder workshops across regional partner groups.",
            ),
        )
    )
    semantic_label = {
        "assertions": [
            _assertion(
                "Stakeholder Facilitation",
                "Led stakeholder workshops across regional partner groups",
                "experience-entry",
            )
        ]
    }
    literal_fallback = {
        "assertions": [
            _assertion(
                "stakeholder workshops",
                "stakeholder workshops across regional partner groups",
                "experience-entry",
            )
        ]
    }
    invoker = ScriptedSkillInvoker([semantic_label, literal_fallback])

    outcome = extract(document, invoker=invoker, normalizer=_normalizer())

    assert [item.skill.canonical_key for item in outcome.skills] == [
        "stakeholder_facilitation"
    ]
    assert outcome.schema_repairs_used == 0
    assert [call["is_repair"] for call in invoker.calls] == [False]


def test_evidence_remains_grounded_when_name_is_present_in_selected_entry() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    error_type = getattr(module, "CandidateSkillExtractionError", None)
    assert callable(extract)
    assert error_type is not None
    document = _document(
        _section(
            "experience",
            0,
            "Work History",
            "experience",
            _entry(
                "experience-entry",
                body="Audience Segmentation improved retention across the region.",
            ),
        )
    )
    ungrounded_evidence = {
        "assertions": [
            _assertion(
                "Audience Segmentation",
                "invented outcome outside the selected entry",
                "experience-entry",
            )
        ]
    }
    invoker = ScriptedSkillInvoker([ungrounded_evidence, ungrounded_evidence])

    with pytest.raises(error_type) as exc_info:
        extract(document, invoker=invoker, normalizer=_normalizer())

    assert exc_info.value.code == "INVALID_STRUCTURED_OUTPUT"
    assert [call["is_repair"] for call in invoker.calls] == [False, True]
    diagnostics = invoker.calls[1]["joined"].split(
        "SANITIZED ISSUES START",
        maxsplit=1,
    )[1]
    assert "EVIDENCE_NOT_IN_SOURCE" in diagnostics
    assert "invented outcome outside the selected entry" not in diagnostics


def test_invalid_heading_only_batch_gets_one_sanitized_repair() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    assert callable(extract)
    document = _document(
        _section(
            "skills",
            0,
            "Core Competencies",
            "skills",
            _entry("skills-entry", body="SEO and content planning"),
        )
    )
    invoker = ScriptedSkillInvoker(
        [
            {
                "assertions": [
                    _assertion(
                        "Core Competencies",
                        "Core Competencies",
                        "skills-entry",
                    )
                ]
            },
            {"assertions": [_assertion("SEO", "SEO", "skills-entry")]},
        ]
    )

    outcome = extract(document, invoker=invoker, normalizer=_normalizer())

    assert [item.skill.canonical_key for item in outcome.skills] == ["seo"]
    assert outcome.schema_repairs_used == 1
    assert [call["is_repair"] for call in invoker.calls] == [False, True]
    repair = invoker.calls[1]["joined"]
    diagnostics = repair.split("SANITIZED ISSUES START", maxsplit=1)[1]
    assert "HEADING_ONLY_SKILL" in diagnostics
    assert "Core Competencies" not in diagnostics
    assert "SEO and content planning" not in diagnostics
    lowered_repair = repair.lower()
    for required_instruction in (
        "complete replacement",
        "semantic skill label supported by its evidence",
        "copy each evidence snippet exactly",
        "omit any assertion whose evidence cannot be grounded",
    ):
        assert required_instruction in lowered_repair


def test_second_invalid_batch_fails_without_partial_skills() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    error_type = getattr(module, "CandidateSkillExtractionError", None)
    assert callable(extract)
    assert error_type is not None
    document = _document(
        _section(
            "summary",
            0,
            "Profile",
            "summary",
            _entry("summary-entry", body="Campaign planning"),
        )
    )
    invalid = {
        "assertions": [
            _assertion("Invented Capability", "not in source", "summary-entry")
        ]
    }
    invoker = ScriptedSkillInvoker([invalid, invalid])

    with pytest.raises(error_type) as exc_info:
        extract(document, invoker=invoker, normalizer=_normalizer())

    assert exc_info.value.code == "INVALID_STRUCTURED_OUTPUT"
    assert "Invented Capability" not in str(exc_info.value)
    assert "not in source" not in str(exc_info.value)
    assert [call["is_repair"] for call in invoker.calls] == [False, True]


def test_cross_batch_duplicates_merge_evidence_and_conflicts_safely() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    assert callable(extract)
    first_body = "Revenue Forecasting for annual budgets. " + ("A" * 280)
    second_body = "Revenue Forecasting for quarterly plans. " + ("B" * 280)
    document = _document(
        _section(
            "first",
            0,
            "Planning",
            "experience",
            _entry("first-entry", body=first_body),
        ),
        _section(
            "second",
            1,
            "Operations",
            "projects",
            _entry("second-entry", body=second_body),
        ),
    )
    invoker = ScriptedSkillInvoker(
        [
            {
                "assertions": [
                    _assertion(
                        "Revenue Forecasting",
                        "Revenue Forecasting for annual budgets",
                        "first-entry",
                        confidence=0.6,
                        proficiency="advanced",
                        years=3.0,
                    )
                ]
            },
            {
                "assertions": [
                    _assertion(
                        "Revenue Forecasting",
                        "Revenue Forecasting for quarterly plans",
                        "second-entry",
                        confidence=0.9,
                        proficiency="intermediate",
                        years=3.0,
                    )
                ]
            },
        ]
    )

    outcome = extract(
        document,
        invoker=invoker,
        normalizer=_normalizer(),
        max_chars=700,
    )

    assert len(invoker.calls) == 2
    assert len(outcome.skills) == 1
    skill = outcome.skills[0]
    assert skill.skill.canonical_key == "revenue_forecasting"
    assert skill.confidence == 0.9
    assert skill.proficiency == "unknown"
    assert skill.years == 3.0
    assert skill.evidence == [
        "Revenue Forecasting for annual budgets",
        "Revenue Forecasting for quarterly plans",
    ]


def test_metadata_only_certificate_title_is_not_a_skill() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    error_type = getattr(module, "CandidateSkillExtractionError", None)
    assert callable(extract)
    assert error_type is not None
    document = _document(
        _section(
            "certifications",
            0,
            "Certifications",
            "certifications",
            _entry(
                "cert-entry",
                title="Certified Revenue Professional",
                body="Issued by Example Board",
            ),
        )
    )
    invalid = {
        "assertions": [
            _assertion(
                "Certified Revenue Professional",
                "Certified Revenue Professional",
                "cert-entry",
            )
        ]
    }

    with pytest.raises(error_type):
        extract(
            document,
            invoker=ScriptedSkillInvoker([invalid, invalid]),
            normalizer=_normalizer(),
        )


def test_unknown_clear_enumeration_cannot_approve_itself_as_atomic() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    error_type = getattr(module, "CandidateSkillExtractionError", None)
    assert callable(extract)
    assert error_type is not None
    document = _document(
        _section(
            "skills",
            0,
            "Capabilities",
            "skills",
            _entry(
                "skills-entry",
                body="Campaign Strategy, Content Planning",
            ),
        )
    )
    invalid = {
        "assertions": [
            _assertion(
                "Campaign Strategy, Content Planning",
                "Campaign Strategy, Content Planning",
                "skills-entry",
            )
        ]
    }

    with pytest.raises(error_type):
        extract(
            document,
            invoker=ScriptedSkillInvoker([invalid, invalid]),
            normalizer=_normalizer(),
        )


def test_source_group_prefix_cannot_be_persisted_as_a_skill() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    error_type = getattr(module, "CandidateSkillExtractionError", None)
    assert callable(extract)
    assert error_type is not None
    document = _document(
        _section(
            "skills",
            0,
            "Capabilities",
            "skills",
            _entry(
                "skills-entry",
                body="Campaign Methods: Audience Research and measurement",
            ),
        )
    )
    invalid = {
        "assertions": [
            _assertion(
                "Campaign Methods",
                "Campaign Methods",
                "skills-entry",
            )
        ]
    }

    with pytest.raises(error_type):
        extract(
            document,
            invoker=ScriptedSkillInvoker([invalid, invalid]),
            normalizer=_normalizer(),
        )


def test_batch_cannot_claim_an_entry_that_was_not_sent_in_that_batch() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    error_type = getattr(module, "CandidateSkillExtractionError", None)
    assert callable(extract)
    assert error_type is not None
    document = _document(
        _section(
            "first",
            0,
            "First",
            "experience",
            _entry(
                "first-entry",
                body="First capability context. " + ("A" * 260),
            ),
        ),
        _section(
            "second",
            1,
            "Second",
            "projects",
            _entry(
                "second-entry",
                body="Second Capability evidence. " + ("B" * 260),
            ),
        ),
    )
    invalid = {
        "assertions": [
            _assertion(
                "Second Capability",
                "Second Capability",
                "second-entry",
            )
        ]
    }

    with pytest.raises(error_type):
        extract(
            document,
            invoker=ScriptedSkillInvoker([invalid, invalid]),
            normalizer=_normalizer(),
            max_chars=500,
        )


def test_prompt_uses_the_bounded_structured_entry_projection() -> None:
    module = _module()
    extract = getattr(module, "extract_candidate_skills_from_document", None)
    assert callable(extract)
    entry = CVEntry(
        id="entry-1",
        ordinal=0,
        title="Role title",
        subtitle="Organisation",
        date_text="2024",
        location="Remote",
        body="Applied a source-grounded capability.",
        bullets=["Improved a measured outcome"],
        attributes={"method": "Structured practice", "tools": ["Tool A"]},
        source_chunk_ordinals=[0],
    )
    invoker = ScriptedSkillInvoker([{"assertions": []}])

    extract(
        _document(_section("section-1", 0, "History", "experience", entry)),
        invoker=invoker,
        normalizer=_normalizer(),
    )

    joined = invoker.calls[0]["joined"]
    serialized = joined.split("CV ENTRY RECORDS START\n", maxsplit=1)[1].split(
        "\nCV ENTRY RECORDS END",
        maxsplit=1,
    )[0]
    records = json.loads(serialized)
    assert records == [
        {
            "section_id": "section-1",
            "section_heading": "History",
            "section_kind": "experience",
            "entry_id": "entry-1",
            "entry_ordinal": 0,
            "title": "Role title",
            "subtitle": "Organisation",
            "date_text": "2024",
            "location": "Remote",
            "body": "Applied a source-grounded capability.",
            "bullets": ["Improved a measured outcome"],
            "attributes": {
                "method": "Structured practice",
                "tools": ["Tool A"],
            },
        }
    ]
    assert _ATTACHMENT not in joined


def test_candidate_schema_requires_semantic_labels_with_source_evidence() -> None:
    import app.services.cv_skill_contracts as contracts
    import app.services.cv_skill_provider as provider

    prompt = provider._SYSTEM_PROMPT.lower()
    assert "concise semantic skill label" in prompt
    assert "supported by" in prompt
    assert "verbatim evidence" in prompt
    assert "one assertion per distinct capability" in prompt

    fields = contracts.ExtractedCandidateSkillAssertion.model_fields
    name_description = (fields["name"].description or "").lower()
    evidence_description = (fields["evidence"].description or "").lower()
    source_ids_description = (fields["source_entry_ids"].description or "").lower()
    assert "concise semantic" in name_description
    assert "supported by" in name_description
    assert "exact contiguous" not in name_description
    assert "verbatim" in evidence_description
    assert "never paraphrase" in evidence_description
    assert "every evidence snippet" in source_ids_description


def test_profile_extraction_exposes_no_profile_first_skill_producer() -> None:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "profile_extraction.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    public_definitions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert public_definitions.isdisjoint(
        {
            "ExtractedCandidateProfile",
            "ExtractedSkillItem",
            "ShopAIKeyStructuredProfileInvoker",
            "StructuredProfileInvoker",
            "build_draft_from_extracted",
            "extract_profile_from_pdf",
            "extracted_to_candidate_profile",
        }
    )
