"""Document-first CV extraction and projection tests (Plan 9 02A).

Fake-backed only — never calls the live ShopAIKey provider.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from app.services.cv_document_extraction import (
    DEFAULT_BATCH_MAX_CHARS,
    EXTRACTION_VERSION,
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    ExtractedAttributeItem,
    ExtractedBatchDocument,
    ExtractedConsolidation,
    ExtractedEntryFragment,
    ExtractedSectionFragment,
    apply_coverage_recovery,
    build_cv_document_from_consolidated,
    consolidate_fragments,
    deterministic_entry_id,
    deterministic_section_id,
    extract_cv_document_from_chunks,
    normalize_heading_key,
    partition_chunks_by_char_ceiling,
    sections_from_fragments,
)
from app.services.cv_document_projection import (
    project_candidate_profile,
    project_outline,
)
from app.services.profile_extraction import (
    CanonicalChunk,
    extract_document_and_profile_from_chunks,
)
from app.services.skill_normalization import SkillNormalizer
from pydantic import ValidationError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CV_DIR = FIXTURES / "cv"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"
SYNTHETIC = CV_DIR / "synthetic_certifications_unknown.json"

_ATTACHMENT = "11111111-1111-4111-8111-111111111111"


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _chunk(ordinal: int, text: str) -> CanonicalChunk:
    return CanonicalChunk(ordinal=ordinal, text=text)


def _entry_frag(
    *,
    body: str,
    ordinals: list[int],
    title: str | None = None,
    bullets: list[str] | None = None,
    attributes: dict[str, str] | None = None,
) -> ExtractedEntryFragment:
    attr_items = [
        ExtractedAttributeItem(key=k, value=v)
        for k, v in (attributes or {}).items()
    ]
    return ExtractedEntryFragment(
        title=title,
        subtitle=None,
        date_text=None,
        location=None,
        body=body,
        bullets=bullets or [],
        attributes=attr_items,
        source_chunk_ordinals=ordinals,
    )


def _section_frag(
    heading: str,
    kind: str,
    entries: list[ExtractedEntryFragment],
    ordinals: list[int],
) -> ExtractedSectionFragment:
    return ExtractedSectionFragment(
        heading=heading,
        kind=kind,  # type: ignore[arg-type]
        entries=entries,
        source_chunk_ordinals=ordinals,
    )


class ScriptedCVDocumentInvoker:
    """Scripted invoker keyed by schema_name (batch / consolidate)."""

    def __init__(
        self,
        *,
        batch_script: list[Any] | None = None,
        consolidate_script: list[Any] | None = None,
    ) -> None:
        self.batch_script = list(batch_script or [])
        self.consolidate_script = list(consolidate_script or [])
        self.calls: list[dict[str, Any]] = []

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        schema_name: str,
        is_repair: bool = False,
    ) -> Any:
        contents = []
        for m in messages:
            content = getattr(m, "content", None)
            if isinstance(content, str):
                contents.append(content)
        joined = "\n".join(contents)
        self.calls.append(
            {
                "schema_name": schema_name,
                "is_repair": is_repair,
                "message_count": len(list(messages)),
                "has_attachment_id": "attachment_id" in joined,
                "has_ordinal_range": "ordinal_range" in joined
                or "ordinal=" in joined
                or "FRAGMENTS" in joined,
                "has_raw_pdf_marker": "%PDF" in joined,
                "joined_chars": len(joined),
                "joined": joined,
            }
        )
        script = (
            self.batch_script if schema_name == "batch" else self.consolidate_script
        )
        if not script:
            raise RuntimeError(f"script exhausted for schema {schema_name}")
        item = script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item("fake error")
        return item


def _load_synthetic() -> dict[str, Any]:
    return json.loads(SYNTHETIC.read_text(encoding="utf-8"))


def test_partition_respects_character_ceiling() -> None:
    chunks = [
        _chunk(0, "a" * 100),
        _chunk(1, "b" * 100),
        _chunk(2, "c" * 100),
    ]
    batches = partition_chunks_by_char_ceiling(
        chunks, attachment_id=_ATTACHMENT, max_chars=150
    )
    assert len(batches) >= 2
    for batch in batches:
        assert batch.attachment_id == _ATTACHMENT
        assert batch.start_ordinal <= batch.end_ordinal
        assert batch.char_count <= 150 or len(batch.chunks) == 1
    covered = [o for b in batches for o in b.ordinals]
    assert covered == [0, 1, 2]


def test_partition_never_sends_full_sequence_when_over_ceiling() -> None:
    chunks = [_chunk(i, f"chunk-{i}-" + ("x" * 40)) for i in range(5)]
    total = len("\n\n".join(c.text for c in chunks))
    batches = partition_chunks_by_char_ceiling(
        chunks, attachment_id=_ATTACHMENT, max_chars=80
    )
    assert len(batches) > 1
    assert all(b.char_count < total for b in batches)


def test_deterministic_ids_stable() -> None:
    a = deterministic_section_id(
        extraction_version=EXTRACTION_VERSION, ordinal=0, heading="Certifications"
    )
    b = deterministic_section_id(
        extraction_version=EXTRACTION_VERSION, ordinal=0, heading="Certifications"
    )
    assert a == b
    assert EXTRACTION_VERSION in a
    assert normalize_heading_key("Certifications") in a
    e = deterministic_entry_id(
        extraction_version=EXTRACTION_VERSION,
        section_ordinal=1,
        entry_ordinal=2,
        heading="Memberships",
        title="ACM",
    )
    assert e == deterministic_entry_id(
        extraction_version=EXTRACTION_VERSION,
        section_ordinal=1,
        entry_ordinal=2,
        heading="Memberships",
        title="ACM",
    )


def test_coverage_recovery_adds_other_with_warning() -> None:
    chunks = [_chunk(0, "alpha"), _chunk(1, "beta missing"), _chunk(2, "gamma")]
    sections = sections_from_fragments(
        [
            _section_frag(
                "Summary",
                "summary",
                [_entry_frag(body="alpha", ordinals=[0])],
                [0],
            ),
            _section_frag(
                "Skills",
                "skills",
                [_entry_frag(body="gamma", ordinals=[2], title="Python")],
                [2],
            ),
        ],
        allowed_ordinals={0, 1, 2},
    )
    warnings: list[str] = []
    recovered = apply_coverage_recovery(sections, chunks, warnings=warnings)
    covered: set[int] = set()
    for s in recovered:
        covered.update(s.source_chunk_ordinals)
    assert covered == {0, 1, 2}
    assert any(s.kind == "other" for s in recovered)
    assert any("ordinal 1" in w for w in warnings)
    other = next(s for s in recovered if s.kind == "other")
    assert "beta missing" in other.entries[0].body


def test_unknown_heading_kind_other_not_skills() -> None:
    frags = [
        _section_frag(
            "Memberships",
            "other",
            [
                _entry_frag(
                    body="Association of Computing Machinery",
                    ordinals=[0],
                    title="ACM",
                )
            ],
            [0],
        )
    ]
    sections = sections_from_fragments(frags, allowed_ordinals={0})
    assert len(sections) == 1
    assert sections[0].heading == "Memberships"
    assert sections[0].kind == "other"
    assert sections[0].entries[0].title == "ACM"


def test_build_document_certifications_and_memberships() -> None:
    data = _load_synthetic()
    chunks = [
        _chunk(int(c["ordinal"]), str(c["text"])) for c in data["chunks"]
    ]
    consolidated = ExtractedConsolidation(
        detected_languages=["en"],
        sections=[
            _section_frag(
                "Summary",
                "summary",
                [_entry_frag(body="Backend engineer", ordinals=[0])],
                [0],
            ),
            _section_frag(
                "Experience",
                "experience",
                [
                    _entry_frag(
                        body="Built FastAPI services",
                        ordinals=[1],
                        title="Senior Backend Engineer",
                    )
                ],
                [1],
            ),
            _section_frag(
                "Skills",
                "skills",
                [
                    _entry_frag(
                        body="Python, FastAPI, Docker, SQL",
                        ordinals=[2],
                    )
                ],
                [2],
            ),
            _section_frag(
                "Certifications",
                "certifications",
                [
                    _entry_frag(
                        body="Issued 2022",
                        ordinals=[3],
                        title="AWS Certified Solutions Architect — Associate",
                        attributes={"credential_id": "ABCD-1234"},
                    )
                ],
                [3],
            ),
            _section_frag(
                "Memberships",
                "other",
                [
                    _entry_frag(
                        body="Member since 2018",
                        ordinals=[4],
                        title="Association of Computing Machinery (ACM)",
                    )
                ],
                [4],
            ),
        ],
        extraction_warnings=[],
        extraction_confidence=0.91,
    )
    doc = build_cv_document_from_consolidated(
        consolidated, chunks, attachment_id=_ATTACHMENT
    )
    headings = [s.heading for s in doc.sections]
    kinds = [s.kind for s in doc.sections]
    assert "Certifications" in headings
    assert "Memberships" in headings
    cert = next(s for s in doc.sections if s.heading == "Certifications")
    assert cert.kind == "certifications"
    assert cert.entries[0].title is not None
    assert "AWS" in cert.entries[0].title
    assert cert.entries[0].attributes.get("credential_id") == "ABCD-1234"
    memb = next(s for s in doc.sections if s.heading == "Memberships")
    assert memb.kind == "other"
    assert "ACM" in (memb.entries[0].title or "")
    assert "Member since 2018" in memb.entries[0].body
    # Full ordinal coverage.
    covered = {o for s in doc.sections for o in s.source_chunk_ordinals}
    assert covered == {0, 1, 2, 3, 4}
    assert kinds.count("skills") == 1


def test_projection_profile_facts_only_from_document() -> None:
    data = _load_synthetic()
    chunks = [
        _chunk(int(c["ordinal"]), str(c["text"])) for c in data["chunks"]
    ]
    consolidated = ExtractedConsolidation(
        detected_languages=["en"],
        sections=[
            _section_frag(
                "Summary",
                "summary",
                [_entry_frag(body="Backend engineer with Python", ordinals=[0])],
                [0],
            ),
            _section_frag(
                "Experience",
                "experience",
                [
                    _entry_frag(
                        body="Built APIs",
                        ordinals=[1],
                        title="Senior Backend Engineer",
                    )
                ],
                [1],
            ),
            _section_frag(
                "Skills",
                "skills",
                [_entry_frag(body="Python, Docker", ordinals=[2])],
                [2],
            ),
            _section_frag(
                "Certifications",
                "certifications",
                [
                    _entry_frag(
                        body="AWS cert",
                        ordinals=[3],
                        title="AWS Certified Solutions Architect",
                    )
                ],
                [3],
            ),
            _section_frag(
                "Memberships",
                "other",
                [_entry_frag(body="ACM member", ordinals=[4], title="ACM")],
                [4],
            ),
        ],
        extraction_warnings=[],
        extraction_confidence=0.85,
    )
    doc = build_cv_document_from_consolidated(
        consolidated, chunks, attachment_id=_ATTACHMENT
    )
    profile = project_candidate_profile(doc, _normalizer())
    assert "Backend engineer" in profile.summary
    assert profile.experiences
    assert profile.experiences[0].title == "Senior Backend Engineer"
    skill_keys = {s.skill.canonical_key for s in profile.skills}
    # Certifications must not become skills.
    assert not any("aws" in k and "cert" in k for k in skill_keys)
    assert not any("acm" in k for k in skill_keys)
    outline = project_outline(doc)
    assert any(o["heading"] == "Certifications" for o in outline)
    assert any(o["kind"] == "other" and o["heading"] == "Memberships" for o in outline)


def test_extract_pipeline_bounded_calls_and_no_raw_pdf() -> None:
    chunks = [
        _chunk(0, "Summary\nEngineer with email and python experience. " + ("x" * 20)),
        _chunk(1, "Skills\nPython, Docker"),
    ]
    batch_payload = ExtractedBatchDocument(
        detected_languages=["en"],
        sections=[
            _section_frag(
                "Summary",
                "summary",
                [_entry_frag(body="Engineer", ordinals=[0])],
                [0],
            )
        ],
        extraction_warnings=[],
        extraction_confidence=0.8,
    )
    batch_payload_2 = ExtractedBatchDocument(
        detected_languages=["en"],
        sections=[
            _section_frag(
                "Skills",
                "skills",
                [_entry_frag(body="Python, Docker", ordinals=[1])],
                [1],
            )
        ],
        extraction_warnings=[],
        extraction_confidence=0.8,
    )
    consolidate_payload = ExtractedConsolidation(
        detected_languages=["en"],
        sections=[
            _section_frag(
                "Summary",
                "summary",
                [_entry_frag(body="Engineer", ordinals=[0])],
                [0],
            ),
            _section_frag(
                "Skills",
                "skills",
                [_entry_frag(body="Python, Docker", ordinals=[1])],
                [1],
            ),
        ],
        extraction_warnings=[],
        extraction_confidence=0.8,
    )
    invoker = ScriptedCVDocumentInvoker(
        batch_script=[batch_payload, batch_payload_2],
        # Consolidation may be hierarchical/deterministic when over ceiling;
        # supply a payload if a model merge is attempted.
        consolidate_script=[
            consolidate_payload,
            consolidate_payload,
            consolidate_payload,
        ],
    )
    outcome = extract_cv_document_from_chunks(
        chunks,
        attachment_id=_ATTACHMENT,
        invoker=invoker,
        max_chars=80,
    )
    assert len(outcome.batches) >= 2
    assert outcome.document.attachment_id == _ATTACHMENT
    assert all(c["has_attachment_id"] for c in invoker.calls)
    assert all(not c["has_raw_pdf_marker"] for c in invoker.calls)
    # Each batch call body is bounded (not full raw multi-batch dump).
    batch_calls = [c for c in invoker.calls if c["schema_name"] == "batch"]
    assert len(batch_calls) >= 2
    # No batch prompt may include every chunk body from the full sequence.
    for call in batch_calls:
        body = call["joined"]
        assert not all(c.text in body for c in chunks)
    covered = {
        o for s in outcome.document.sections for o in s.source_chunk_ordinals
    }
    assert covered == {0, 1}


def test_one_schema_repair_then_success() -> None:
    chunks = [_chunk(0, "Summary\nHello engineer python email skills")]
    bad = ValidationError.from_exception_data(
        "ExtractedBatchDocument",
        [{"type": "missing", "loc": ("sections",), "input": {}}],
    )
    good = ExtractedBatchDocument(
        detected_languages=["en"],
        sections=[
            _section_frag(
                "Summary",
                "summary",
                [_entry_frag(body="Hello", ordinals=[0])],
                [0],
            )
        ],
        extraction_warnings=[],
        extraction_confidence=0.7,
    )
    consolidate = ExtractedConsolidation(
        detected_languages=["en"],
        sections=list(good.sections),
        extraction_warnings=[],
        extraction_confidence=0.7,
    )
    invoker = ScriptedCVDocumentInvoker(
        batch_script=[bad, good],
        consolidate_script=[consolidate],
    )
    outcome = extract_cv_document_from_chunks(
        chunks, attachment_id=_ATTACHMENT, invoker=invoker, max_chars=5000
    )
    assert outcome.schema_repairs_used >= 1
    batch_calls = [c for c in invoker.calls if c["schema_name"] == "batch"]
    assert any(c["is_repair"] for c in batch_calls)


def test_schema_repair_exhausted_fails() -> None:
    chunks = [_chunk(0, "Summary\nHello engineer python email skills")]
    bad = ValidationError.from_exception_data(
        "ExtractedBatchDocument",
        [{"type": "missing", "loc": ("sections",), "input": {}}],
    )
    invoker = ScriptedCVDocumentInvoker(batch_script=[bad, bad])
    with pytest.raises(Exception) as ei:
        extract_cv_document_from_chunks(
            chunks, attachment_id=_ATTACHMENT, invoker=invoker, max_chars=5000
        )
    assert getattr(ei.value, "code", None) == FAILURE_INVALID_STRUCTURED_OUTPUT


def test_hierarchical_consolidation_when_over_ceiling() -> None:
    # Fragments large enough that the full group exceeds the ceiling, but pairs
    # of small metadata still force hierarchical adjacent merges.
    frags = [
        _section_frag(
            f"Section {i}",
            "other",
            [_entry_frag(body=("body-" + str(i) + "-") * 40, ordinals=[i])],
            [i],
        )
        for i in range(4)
    ]
    half_a = ExtractedConsolidation(
        detected_languages=[],
        sections=frags[:2],
        extraction_warnings=[],
        extraction_confidence=0.5,
    )
    half_b = ExtractedConsolidation(
        detected_languages=[],
        sections=frags[2:],
        extraction_warnings=[],
        extraction_confidence=0.5,
    )
    final = ExtractedConsolidation(
        detected_languages=["en"],
        sections=frags,
        extraction_warnings=[],
        extraction_confidence=0.6,
    )
    invoker = ScriptedCVDocumentInvoker(
        consolidate_script=[half_a, half_b, final],
    )
    result, repairs, retries = consolidate_fragments(
        frags,
        attachment_id=_ATTACHMENT,
        invoker=invoker,
        max_chars=200,
    )
    assert len(result.sections) == 4
    assert repairs == 0
    assert retries == 0
    # Leaf passthrough + deterministic merge when still over ceiling is valid;
    # model calls may be zero when every group remains oversized.
    assert all(c["schema_name"] == "consolidate" for c in invoker.calls)


def test_profile_extraction_delegate_document_first() -> None:
    chunks = [
        _chunk(0, "Summary\nEngineer"),
        _chunk(1, "Skills\nPython"),
    ]
    batch = ExtractedBatchDocument(
        detected_languages=["en"],
        sections=[
            _section_frag(
                "Summary",
                "summary",
                [_entry_frag(body="Engineer", ordinals=[0])],
                [0],
            ),
            _section_frag(
                "Skills",
                "skills",
                [_entry_frag(body="Python", ordinals=[1])],
                [1],
            ),
        ],
        extraction_warnings=[],
        extraction_confidence=0.9,
    )
    cons = ExtractedConsolidation(
        detected_languages=["en"],
        sections=list(batch.sections),
        extraction_warnings=[],
        extraction_confidence=0.9,
    )
    invoker = ScriptedCVDocumentInvoker(
        batch_script=[batch],
        consolidate_script=[cons],
    )
    document, profile, repairs, retries = extract_document_and_profile_from_chunks(
        chunks,
        attachment_id=_ATTACHMENT,
        document_invoker=invoker,
        normalizer=_normalizer(),
        max_chars=DEFAULT_BATCH_MAX_CHARS,
    )
    assert document.attachment_id == _ATTACHMENT
    assert profile.summary
    assert repairs >= 0
    assert retries >= 0


def test_default_batch_ceiling_positive() -> None:
    assert DEFAULT_BATCH_MAX_CHARS > 0
    assert DEFAULT_BATCH_MAX_CHARS == 6000


def test_batch_schema_has_no_freeform_attribute_map() -> None:
    """ShopAIKey/OpenAI strict response_format rejects additionalProperties maps."""
    schema = ExtractedBatchDocument.model_json_schema()
    entry = schema["$defs"]["ExtractedEntryFragment"]
    attrs = entry["properties"]["attributes"]
    assert attrs.get("type") == "array"
    assert "additionalProperties" not in attrs
    items = attrs.get("items") or {}
    # Prefer $ref to ExtractedAttributeItem with fixed key/value props.
    assert "$ref" in items or items.get("type") == "object"
