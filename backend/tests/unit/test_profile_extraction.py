"""Unit tests for structured CV extraction and propose_profile_from_cv (02B).

Fake-backed only — never calls the live ShopAIKey provider.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import ATTACHMENT_STATE_FAILED
from app.db.models.profiles import CANDIDATE_PROFILE_ID, PROFILE_DRAFT_ID
from app.db.session import build_async_engine
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as profile_repo
from app.schemas.tools import ToolResult
from app.services.cv_document_extraction import (
    EXTRACTION_VERSION,
    ExtractedBatchDocument,
    ExtractedConsolidation,
    ExtractedEntryFragment,
    ExtractedSectionFragment,
    ShopAIKeyStructuredCVDocumentInvoker,
)
from app.services.cv_skill_contracts import ExtractedCandidateSkillBatch
from app.services.pdf_extraction import (
    NO_EXTRACTABLE_TEXT,
    extract_pdf_text,
)
from app.services.profile_drafts import (
    ERROR_ATTACHMENT_NOT_FOUND,
    arguments_summary_for_propose_cv,
    propose_profile_from_cv,
)
from app.services.profile_extraction import (
    EXTRACTION_SCHEMA_STRATEGY,
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    FAILURE_NO_EXTRACTABLE_TEXT,
    FAILURE_PROVIDER_RATE_LIMIT,
    FAILURE_PROVIDER_TIMEOUT,
    STRUCTURED_OUTPUT_METHOD,
    STRUCTURED_OUTPUT_STRICT,
    ProfileExtractionError,
    build_draft_from_candidate_profile,
    classify_provider_error,
    compact_draft_summary,
    compute_canonical_source_hash,
    empty_job_preferences,
    extract_document_publication_from_pdf,
    is_document_structured_invoker,
)
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage
from app.tools.profile import (
    PROPOSE_PROFILE_FROM_CV_NAME,
    build_propose_profile_from_cv_tool,
)
from app.tools.registry import production_registry
from pydantic import ValidationError

from tests.support.db_migration import run_async, session_factory

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CV_DIR = FIXTURES / "cv"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"

_ORDINAL_RE = re.compile(r"\[ordinal=(\d+)\]")


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _valid_profile(**overrides: Any) -> Any:
    from app.schemas.profile import parse_candidate_profile

    normalizer = _normalizer()
    base: dict[str, Any] = {
        "summary": "Backend engineer with Python and FastAPI experience.",
        "current_title": "Senior Backend Engineer",
        "total_experience_years": 6.0,
        "skills": [
            {
                "skill": normalizer.normalize_name("Python").model_dump(mode="json"),
                "confidence": 0.9,
                "proficiency": "advanced",
                "years": 5.0,
                "source": "cv",
                "excluded": False,
                "evidence": ["5 years Python"],
            },
            {
                "skill": normalizer.normalize_name("React.js").model_dump(mode="json"),
                "confidence": 0.7,
                "proficiency": "intermediate",
                "years": 2.0,
                "source": "cv",
                "excluded": False,
                "evidence": ["React.js on UI"],
            },
        ],
        "experiences": [
            {
                "title": "Engineer",
                "company": "Acme",
                "start_date_text": "2019-01",
                "end_date_text": "present",
                "summary": "Built APIs",
            }
        ],
        "education": [
            {
                "institution": "State U",
                "degree": "BSc",
                "field": "CS",
                "graduation_year": 2018,
            }
        ],
        "languages": [{"name": "English", "proficiency": "fluent"}],
        "extraction_confidence": 0.88,
    }
    base.update(overrides)
    return parse_candidate_profile(base)


def _valid_draft(**overrides: Any) -> Any:
    return build_draft_from_candidate_profile(_valid_profile(**overrides))


def _covering_sections(ordinals: list[int]) -> list[ExtractedSectionFragment]:
    if not ordinals:
        ordinals = [0]
    first = ordinals[0]
    rest = ordinals[1:] if len(ordinals) > 1 else ordinals
    sections = [
        ExtractedSectionFragment(
            heading="Summary",
            kind="summary",
            entries=[
                ExtractedEntryFragment(
                    title="Senior Backend Engineer",
                    subtitle=None,
                    date_text=None,
                    location=None,
                    body="Backend engineer with Python and FastAPI experience.",
                    bullets=[],
                    attributes=[],
                    source_chunk_ordinals=[first],
                )
            ],
            source_chunk_ordinals=[first],
        ),
        ExtractedSectionFragment(
            heading="Skills",
            kind="skills",
            entries=[
                ExtractedEntryFragment(
                    title=None,
                    subtitle=None,
                    date_text=None,
                    location=None,
                    body="Python, FastAPI, React.js",
                    bullets=["Python", "React.js"],
                    attributes=[],
                    source_chunk_ordinals=list(rest) if rest else [first],
                )
            ],
            source_chunk_ordinals=list(rest) if rest else [first],
        ),
        ExtractedSectionFragment(
            heading="Experience",
            kind="experience",
            entries=[
                ExtractedEntryFragment(
                    title="Engineer",
                    subtitle="Acme",
                    date_text="2019-01 – present",
                    location=None,
                    body="Built APIs",
                    bullets=[],
                    attributes=[],
                    source_chunk_ordinals=[first],
                )
            ],
            source_chunk_ordinals=[first],
        ),
    ]
    return sections


class CoveringDocumentInvoker:
    """Document invoker that covers ordinals mentioned in each prompt."""

    def __init__(
        self,
        script: list[Any] | None = None,
        *,
        skill_script: list[Any] | None = None,
    ) -> None:
        self.script = list(script or [])
        self.skill_script = list(skill_script or [])
        self.calls: list[dict[str, Any]] = []
        self.last_human_content: str | None = None

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        schema_name: str,
        is_repair: bool = False,
    ) -> Any:
        msg_list = list(messages)
        joined_parts: list[str] = []
        for m in msg_list:
            content = getattr(m, "content", None)
            if isinstance(content, str):
                joined_parts.append(content)
        joined = "\n".join(joined_parts)
        self.last_human_content = joined
        self.calls.append(
            {
                "schema_name": schema_name,
                "is_repair": is_repair,
                "message_count": len(msg_list),
            }
        )
        if schema_name == "candidate_skills":
            if self.skill_script:
                item = self.skill_script.pop(0)
                if isinstance(item, BaseException):
                    raise item
                if isinstance(item, type) and issubclass(item, BaseException):
                    raise item("fake error")
                if item is not None:
                    return item
            entry_match = re.search(
                r'"entry_id":"([^"]+)"[^}]*Python',
                joined,
                re.DOTALL,
            )
            assert entry_match is not None
            return {
                "assertions": [
                    {
                        "name": "Python",
                        "confidence": 0.9,
                        "proficiency": "advanced",
                        "years": None,
                        "evidence": ["Python"],
                        "source_entry_ids": [entry_match.group(1)],
                    }
                ]
            }
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, type) and issubclass(item, BaseException):
                raise item("fake error")
            return item
        ordinals = sorted({int(m.group(1)) for m in _ORDINAL_RE.finditer(joined)})
        if not ordinals:
            ordinals = [0]
        sections = _covering_sections(ordinals)
        if schema_name == "batch":
            return ExtractedBatchDocument(
                detected_languages=["en"],
                sections=sections,
                extraction_warnings=[],
                extraction_confidence=0.88,
            )
        return ExtractedConsolidation(
            detected_languages=["en"],
            sections=sections,
            extraction_warnings=[],
            extraction_confidence=0.88,
        )


class _TimeoutExc(Exception):
    """Named like APITimeoutError for classify_provider_error coverage."""


class APITimeoutError(_TimeoutExc):
    pass


class RateLimitError(Exception):
    status_code = 429


# ---------------------------------------------------------------------------
# Extraction pure unit paths
# ---------------------------------------------------------------------------


def test_strict_json_schema_strategy_constants() -> None:
    assert EXTRACTION_SCHEMA_STRATEGY == "strict_json_schema"
    assert STRUCTURED_OUTPUT_METHOD == "json_schema"
    assert STRUCTURED_OUTPUT_STRICT is True


def test_document_invoker_binds_candidate_skill_structured_output() -> None:
    """Production document invoker binds the guarded skill schema without network."""
    fake_model = MagicMock()
    fake_model.with_structured_output.side_effect = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]

    invoker = ShopAIKeyStructuredCVDocumentInvoker(model=fake_model)
    assert invoker.model_name  # may fall back to locked default
    calls = fake_model.with_structured_output.call_args_list
    assert len(calls) == 3
    assert all(call.kwargs.get("method") == "json_schema" for call in calls)
    assert all(call.kwargs.get("strict") is True for call in calls)
    schemas = [call.args[0] for call in calls]
    assert ExtractedCandidateSkillBatch in schemas


def test_normalize_skills_and_empty_preferences() -> None:
    draft = _valid_draft()
    keys = {s.skill.canonical_key for s in draft.candidate_profile.skills}
    # Fixture taxonomy should resolve Python; React.js via alias/fingerprint.
    assert "python" in keys or any("python" in k for k in keys)
    prefs = draft.job_preferences
    assert prefs.target_roles == []
    assert prefs.preferred_locations == []
    assert empty_job_preferences().acceptable_work_modes == []
    summary = compact_draft_summary(draft)
    assert summary["draft_id"] == "current"
    assert "evidence" not in summary
    assert "raw" not in str(summary).lower()


def test_extraction_failure_writes_no_chunk_rows(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    """Parse/model failure leaves attachment_text_chunks empty for the row."""
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    invoker = CoveringDocumentInvoker()  # never called on no-text
    pdf = CV_DIR / "image_only_cv.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = storage.write_bytes(att_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="no-text-hash",
                    original_name="img.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=_normalizer(),
            )
            assert result.tool_result.ok is False
            assert result.tool_result.code == FAILURE_NO_EXTRACTABLE_TEXT

            async with factory() as session:
                assert await chunk_repo.count_for_attachment(session, att_id) == 0
                assert await cv_doc_repo.get_draft(session, att_id) is None
                assert await profile_repo.get_current_draft(session) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_successful_propose_persists_chunks_document_and_profile_atomically(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    """Successful extraction stores document draft, profile draft, and chunks."""
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    invoker = CoveringDocumentInvoker()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = storage.write_bytes(att_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="ok-chunk-hash",
                    original_name="cv.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=_normalizer(),
            )
            assert result.tool_result.ok is True
            assert result.tool_result.data is not None
            assert result.tool_result.data["source_hash"]
            assert result.tool_result.data["extraction_version"] == EXTRACTION_VERSION
            assert invoker.calls  # batch + consolidate
            assert all("schema_name" in c for c in invoker.calls)

            async with factory() as session:
                from app.services.profile_extraction import CanonicalChunk

                rows = await chunk_repo.list_for_attachment(session, att_id)
                assert rows
                assert [r.ordinal for r in rows] == list(range(len(rows)))
                canon = tuple(
                    CanonicalChunk(ordinal=r.ordinal, text=r.text) for r in rows
                )
                source_hash = compute_canonical_source_hash(canon)

                draft_row = await profile_repo.get_current_draft(session)
                assert draft_row is not None
                assert draft_row.source_attachment_id == att_id
                assert "candidate_profile" in draft_row.draft_json

                doc_draft = await cv_doc_repo.get_draft(session, att_id)
                assert doc_draft is not None
                assert doc_draft.source_hash == source_hash
                assert doc_draft.source_hash == result.tool_result.data["source_hash"]
                assert doc_draft.extraction_version == EXTRACTION_VERSION
                assert doc_draft.document_json["attachment_id"] == att_id
                assert doc_draft.profile_json
                assert "sections" in doc_draft.outline_json
                assert (
                    draft_row.draft_json["candidate_profile"]["summary"]
                    == doc_draft.profile_json["summary"]
                )
                # Historic no-row attachment remains empty (no backfill).
                other = new_uuid()
                await att_repo.create_staged(
                    session,
                    file_hash="hist-empty",
                    original_name="h.pdf",
                    size_bytes=10,
                    storage_path=f"{other}.pdf",
                    page_count=1,
                    attachment_id=other,
                )
                await session.commit()
                assert await chunk_repo.count_for_attachment(session, other) == 0
                assert await cv_doc_repo.get_draft(session, other) is None
        finally:
            await engine.dispose()

    run_async(_body())


@pytest.mark.parametrize("failure_stage", ("document", "candidate_skills"))
def test_schema_repair_failure_does_not_persist_any_draft_artifacts(
    migrated_sqlite: Path,
    tmp_path: Path,
    failure_stage: str,
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    bad = ValidationError.from_exception_data(
        "ExtractedBatchDocument",
        [{"type": "missing", "loc": ("sections",), "input": {}}],
    )
    invoker = (
        CoveringDocumentInvoker(script=[bad, bad])
        if failure_stage == "document"
        else CoveringDocumentInvoker(
            skill_script=[
                {"assertions": "invalid"},
                {"assertions": "invalid"},
            ]
        )
    )
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = storage.write_bytes(att_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash=f"bad-schema-{failure_stage}",
                    original_name="cv.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=_normalizer(),
            )
            assert result.tool_result.ok is False
            assert result.tool_result.code == FAILURE_INVALID_STRUCTURED_OUTPUT
            async with factory() as session:
                assert await chunk_repo.count_for_attachment(session, att_id) == 0
                assert await cv_doc_repo.get_draft(session, att_id) is None
                assert await profile_repo.get_current_draft(session) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_publish_failpoint_rolls_back_all_draft_artifacts(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    """Transaction failpoint publishes none of the new artifacts."""
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    invoker = CoveringDocumentInvoker()
    pdf = CV_DIR / "digital_cv_01.pdf"
    prior_draft = _valid_draft()

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            prior_id = new_uuid()
            att_id = new_uuid()
            prior_rel = storage.write_bytes(prior_id, pdf.read_bytes())
            rel = storage.write_bytes(att_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="fp-prior",
                    original_name="prior.pdf",
                    size_bytes=10,
                    storage_path=prior_rel,
                    page_count=1,
                    attachment_id=prior_id,
                )
                await att_repo.create_staged(
                    session,
                    file_hash="fp-new",
                    original_name="cv.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await profile_repo.upsert_current_draft(
                    session,
                    draft_json=prior_draft.model_dump(mode="json"),
                    source_attachment_id=prior_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=_normalizer(),
                publish_failpoint="before_commit",
            )
            assert result.tool_result.ok is False
            assert result.tool_result.code == "DRAFT_PUBLISH_FAILED"

            async with factory() as session:
                # Prior draft truth preserved; no partial new artifacts.
                draft_row = await profile_repo.get_current_draft(session)
                assert draft_row is not None
                assert draft_row.source_attachment_id == prior_id
                assert await chunk_repo.count_for_attachment(session, att_id) == 0
                assert await cv_doc_repo.get_draft(session, att_id) is None
                assert await att_repo.get_by_id(session, prior_id) is not None
                assert await att_repo.get_by_id(session, att_id) is not None
            assert storage.exists(prior_rel)
            assert storage.exists(rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_document_publication_pure_path_has_matching_hash() -> None:
    invoker = CoveringDocumentInvoker()
    pdf = CV_DIR / "digital_cv_01.pdf"
    att_id = "11111111-1111-4111-8111-111111111111"
    artifacts = extract_document_publication_from_pdf(
        pdf,
        attachment_id=att_id,
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert artifacts.source_hash == compute_canonical_source_hash(artifacts.chunks)
    assert artifacts.document_json["attachment_id"] == att_id
    assert artifacts.extraction_version == EXTRACTION_VERSION
    assert "sections" in artifacts.outline_json
    assert artifacts.draft.candidate_profile.summary
    assert [
        item.skill.canonical_key for item in artifacts.draft.candidate_profile.skills
    ] == ["python"]
    assert [call["schema_name"] for call in invoker.calls].count(
        "candidate_skills"
    ) == 1
    assert is_document_structured_invoker(invoker) is True
    assert is_document_structured_invoker(object()) is False


def test_no_extractable_text_short_circuit() -> None:
    pdf = CV_DIR / "image_only_cv.pdf"
    invoker = CoveringDocumentInvoker()
    with pytest.raises(ProfileExtractionError) as ei:
        extract_document_publication_from_pdf(
            pdf,
            attachment_id=new_uuid(),
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_NO_EXTRACTABLE_TEXT
    assert ei.value.code == NO_EXTRACTABLE_TEXT
    assert invoker.calls == []


def test_exactly_one_schema_repair_then_success() -> None:
    invoker = CoveringDocumentInvoker(skill_script=[{"assertions": "invalid"}, None])
    outcome = extract_document_publication_from_pdf(
        CV_DIR / "digital_cv_01.pdf",
        attachment_id=new_uuid(),
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.schema_repairs_used == 1
    skill_calls = [
        call for call in invoker.calls if call["schema_name"] == "candidate_skills"
    ]
    assert [call["is_repair"] for call in skill_calls] == [False, True]


def test_schema_repair_exhausted_fails() -> None:
    invoker = CoveringDocumentInvoker(
        skill_script=[{"assertions": "invalid"}, {"assertions": "invalid"}]
    )
    with pytest.raises(ProfileExtractionError) as ei:
        extract_document_publication_from_pdf(
            CV_DIR / "digital_cv_01.pdf",
            attachment_id=new_uuid(),
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_INVALID_STRUCTURED_OUTPUT
    skill_calls = [
        call for call in invoker.calls if call["schema_name"] == "candidate_skills"
    ]
    assert len(skill_calls) == 2


def test_exactly_one_timeout_retry_then_success() -> None:
    invoker = CoveringDocumentInvoker(skill_script=[APITimeoutError("timeout"), None])
    outcome = extract_document_publication_from_pdf(
        CV_DIR / "digital_cv_01.pdf",
        attachment_id=new_uuid(),
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.provider_retries_used == 1
    skill_calls = [
        call for call in invoker.calls if call["schema_name"] == "candidate_skills"
    ]
    assert len(skill_calls) == 2


def test_timeout_retry_exhausted() -> None:
    invoker = CoveringDocumentInvoker(
        skill_script=[APITimeoutError("t1"), APITimeoutError("t2")]
    )
    with pytest.raises(ProfileExtractionError) as ei:
        extract_document_publication_from_pdf(
            CV_DIR / "digital_cv_01.pdf",
            attachment_id=new_uuid(),
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_PROVIDER_TIMEOUT
    skill_calls = [
        call for call in invoker.calls if call["schema_name"] == "candidate_skills"
    ]
    assert len(skill_calls) == 2


def test_rate_limit_retry_once() -> None:
    invoker = CoveringDocumentInvoker(skill_script=[RateLimitError("rate"), None])
    outcome = extract_document_publication_from_pdf(
        CV_DIR / "digital_cv_01.pdf",
        attachment_id=new_uuid(),
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.provider_retries_used == 1
    assert classify_provider_error(RateLimitError("x")) == FAILURE_PROVIDER_RATE_LIMIT


def test_raw_cv_text_absent_from_compact_outputs() -> None:
    draft = _valid_draft()
    compact = compact_draft_summary(draft)
    dumped = str(compact)
    assert "CV TEXT" not in dumped
    assert "---" not in dumped
    args = arguments_summary_for_propose_cv("att-1")
    assert args == {"attachment_id": "att-1", "reprocess": False}
    args_re = arguments_summary_for_propose_cv("att-1", reprocess=True)
    assert args_re == {"attachment_id": "att-1", "reprocess": True}


# ---------------------------------------------------------------------------
# propose_profile_from_cv orchestration (migrated SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture
def files_root(tmp_path: Path) -> Path:
    root = tmp_path / "files"
    root.mkdir()
    return root


def _write_pdf(storage: AttachmentStorage, attachment_id: str, src: Path) -> str:
    return storage.write_bytes(attachment_id, src.read_bytes())


def test_propose_active_reuses_profile_without_provider(
    migrated_sqlite: Path, files_root: Path
) -> None:
    storage = AttachmentStorage(files_root)
    invoker = CoveringDocumentInvoker()
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id, pdf)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="h-active",
                    original_name="cv.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await att_repo.mark_active(session, att_id, page_count=1)
                profile_json = _valid_profile().model_dump(mode="json")
                await profile_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=profile_json,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert result.kind == "active_profile"
            assert result.tool_result.ok is True
            assert result.tool_result.data is not None
            assert result.tool_result.data["profile_id"] == CANDIDATE_PROFILE_ID
            assert result.tool_result.data["reused"] is True
            assert invoker.calls == []

            async with factory() as session:
                assert await profile_repo.get_current_draft(session) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_existing_draft_reuse_without_provider(
    migrated_sqlite: Path, files_root: Path
) -> None:
    storage = AttachmentStorage(files_root)
    invoker = CoveringDocumentInvoker()
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"
    draft = _valid_draft()

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id, pdf)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="h-draft",
                    original_name="cv.pdf",
                    size_bytes=10,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await profile_repo.upsert_current_draft(
                    session,
                    draft_json=draft.model_dump(mode="json"),
                    source_attachment_id=att_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert result.kind == "existing_draft"
            assert result.tool_result.ok is True
            assert result.tool_result.data is not None
            assert result.tool_result.data["draft_id"] == PROFILE_DRAFT_ID
            assert result.tool_result.data["reused"] is True
            assert invoker.calls == []
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_new_draft_and_replace_prior_staged(
    migrated_sqlite: Path, files_root: Path
) -> None:
    storage = AttachmentStorage(files_root)
    invoker = CoveringDocumentInvoker()
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"
    old_draft = _valid_draft(summary="old draft summary")

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            old_id = new_uuid()
            new_id = new_uuid()
            old_rel = _write_pdf(storage, old_id, pdf)
            new_rel = _write_pdf(storage, new_id, pdf)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="h-old",
                    original_name="old.pdf",
                    size_bytes=10,
                    storage_path=old_rel,
                    page_count=1,
                    attachment_id=old_id,
                )
                await att_repo.create_staged(
                    session,
                    file_hash="h-new",
                    original_name="new.pdf",
                    size_bytes=10,
                    storage_path=new_rel,
                    page_count=1,
                    attachment_id=new_id,
                )
                await profile_repo.upsert_current_draft(
                    session,
                    draft_json=old_draft.model_dump(mode="json"),
                    source_attachment_id=old_id,
                )
                await session.commit()

            assert storage.exists(old_rel)
            result = await propose_profile_from_cv(
                attachment_id=new_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert result.kind == "new_draft"
            assert result.tool_result.ok is True
            assert result.tool_result.data is not None
            assert result.tool_result.data["draft_id"] == PROFILE_DRAFT_ID
            assert result.tool_result.data["reused"] is False
            assert result.tool_result.data["prior_staged_removed"] is True
            assert invoker.calls  # document batch/consolidate

            async with factory() as session:
                draft_row = await profile_repo.get_current_draft(session)
                assert draft_row is not None
                assert draft_row.source_attachment_id == new_id
                assert draft_row.draft_json["candidate_profile"]["summary"]
                doc_draft = await cv_doc_repo.get_draft(session, new_id)
                assert doc_draft is not None
                assert doc_draft.source_hash == result.tool_result.data["source_hash"]
                assert await att_repo.get_by_id(session, old_id) is None
                assert await att_repo.get_by_id(session, new_id) is not None
                # Prior document draft cascaded away with prior attachment.
                assert await cv_doc_repo.get_draft(session, old_id) is None
                # Active profile untouched
                assert await profile_repo.get_active_profile(session) is None

            assert not storage.exists(old_rel)
            assert storage.exists(new_rel)
            # Compact result has no raw CV body
            blob = str(result.tool_result.model_dump(mode="json"))
            assert "CV TEXT" not in blob
            raw_pdf_snippet = pdf.read_bytes()[:20]
            assert raw_pdf_snippet not in blob.encode("utf-8", errors="ignore")
        finally:
            await engine.dispose()

    run_async(_body())


def test_failed_extraction_marks_failed_retains_file(
    migrated_sqlite: Path, files_root: Path
) -> None:
    storage = AttachmentStorage(files_root)
    invoker = CoveringDocumentInvoker()  # unused — no text path
    normalizer = _normalizer()
    pdf = CV_DIR / "image_only_cv.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id, pdf)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="h-img",
                    original_name="img.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert result.tool_result.ok is False
            assert result.tool_result.code == FAILURE_NO_EXTRACTABLE_TEXT
            async with factory() as session:
                row = await att_repo.get_by_id(session, att_id)
                assert row is not None
                assert row.state == ATTACHMENT_STATE_FAILED
                assert row.failure_code == FAILURE_NO_EXTRACTABLE_TEXT
                assert await profile_repo.get_current_draft(session) is None
            assert storage.exists(rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_exhausted_provider_failure_no_success_claim(
    migrated_sqlite: Path, files_root: Path
) -> None:
    storage = AttachmentStorage(files_root)
    invoker = CoveringDocumentInvoker(
        script=[APITimeoutError("t1"), APITimeoutError("t2")]
    )
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id, pdf)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="h-to",
                    original_name="cv.pdf",
                    size_bytes=10,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert result.tool_result.ok is False
            assert result.tool_result.code == FAILURE_PROVIDER_TIMEOUT
            async with factory() as session:
                row = await att_repo.get_by_id(session, att_id)
                assert row is not None
                assert row.state == ATTACHMENT_STATE_FAILED
                assert await profile_repo.get_current_draft(session) is None
                assert await cv_doc_repo.get_draft(session, att_id) is None
                assert await chunk_repo.count_for_attachment(session, att_id) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_tool_boundary_compact_and_not_production_registered(
    migrated_sqlite: Path, files_root: Path
) -> None:
    import json

    from app.db.models.chat import CHAT_MESSAGE_ROLE_USER
    from app.repositories import agent_runs as runs_repo
    from app.repositories import chat_messages as messages_repo

    storage = AttachmentStorage(files_root)
    invoker = CoveringDocumentInvoker()
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"

    # Production registry: three profile tools, job tools, match, then CV read.
    prod_names = production_registry().tool_names()
    assert PROPOSE_PROFILE_FROM_CV_NAME in prod_names
    assert prod_names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    ]

    async def _ainvoke_with_identity(
        tool_fn: Any,
        *,
        run_id: str,
        tool_call_id: str,
        attachment_id: str,
        attachment_ids: Sequence[str] | None = None,
    ) -> ToolResult:
        """ToolCall shape so InjectedToolCallId / InjectedState resolve."""
        raw = await tool_fn.ainvoke(
            {
                "type": "tool_call",
                "id": tool_call_id,
                "name": tool_fn.name,
                "args": {
                    "attachment_id": attachment_id,
                    "state": {
                        "run_id": run_id,
                        "attachment_ids": list(attachment_ids or ()),
                    },
                },
            }
        )
        if isinstance(raw, str):
            payload = json.loads(raw)
        elif hasattr(raw, "content"):
            content = raw.content
            payload = json.loads(content) if isinstance(content, str) else content
        else:
            payload = raw
        return ToolResult.model_validate(payload)

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id, pdf)
            async with factory() as session:
                user = await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="propose from cv",
                )
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                await att_repo.create_staged(
                    session,
                    file_hash="h-tool",
                    original_name="cv.pdf",
                    size_bytes=10,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await session.commit()
                run_id = run.id

            tool_fn = build_propose_profile_from_cv_tool(
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert tool_fn.name == PROPOSE_PROFILE_FROM_CV_NAME
            # LLM-visible schema remains attachment_id only (injected hidden).
            from langchain_core.utils.function_calling import (
                convert_to_openai_tool,
            )

            oai = convert_to_openai_tool(tool_fn)
            props = (
                oai.get("function", {}).get("parameters", {}).get("properties")
                or {}
            )
            # Plan 9: optional reprocess flag is LLM-visible; injected hidden
            # fields remain excluded.
            assert set(props) == {"attachment_id", "reprocess"}
            assert "tool_call_id" not in props
            assert "state" not in props
            assert "run_id" not in props

            tr = await _ainvoke_with_identity(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_propose_cv_ok",
                attachment_id=att_id,
            )
            assert tr.ok is True
            assert tr.data is not None
            assert tr.data["draft_id"] == PROFILE_DRAFT_ID
            assert "raw" not in tr.data
            # Missing attachment (distinct tool_call_id → new durable execution)
            tr_miss = await _ainvoke_with_identity(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_propose_cv_miss",
                attachment_id=new_uuid(),
            )
            assert tr_miss.ok is False
            assert tr_miss.code == ERROR_ATTACHMENT_NOT_FOUND
        finally:
            await engine.dispose()

    run_async(_body())


def test_upload_turn_attachment_wins_over_active_model_argument(
    migrated_sqlite: Path, files_root: Path
) -> None:
    """A newly uploaded staged B cannot be shadowed by model-supplied A."""
    import json

    from app.db.models.chat import CHAT_MESSAGE_ROLE_USER
    from app.repositories import agent_runs as runs_repo
    from app.repositories import chat_messages as messages_repo
    from app.repositories import tool_executions as tool_repo

    storage = AttachmentStorage(files_root)
    invoker = CoveringDocumentInvoker()
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            active_id = new_uuid()
            staged_id = new_uuid()
            active_rel = _write_pdf(storage, active_id, pdf)
            staged_rel = _write_pdf(storage, staged_id, pdf)
            async with factory() as session:
                user = await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="upload B",
                )
                run = await runs_repo.create_run(session, user_message_id=user.id)
                await att_repo.create_staged(
                    session,
                    file_hash="active-a",
                    original_name="a.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=active_rel,
                    page_count=1,
                    attachment_id=active_id,
                )
                await att_repo.mark_active(session, active_id, page_count=1)
                await profile_repo.upsert_active_profile(
                    session,
                    active_attachment_id=active_id,
                    profile_json=_valid_profile().model_dump(mode="json"),
                )
                await att_repo.create_staged(
                    session,
                    file_hash="staged-b",
                    original_name="b.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=staged_rel,
                    page_count=1,
                    attachment_id=staged_id,
                )
                await session.commit()

            tool_fn = build_propose_profile_from_cv_tool(
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            raw = await tool_fn.ainvoke(
                {
                    "type": "tool_call",
                    "id": "call-upload-b",
                    "name": tool_fn.name,
                    "args": {
                        "attachment_id": active_id,
                        "state": {
                            "run_id": run.id,
                            "attachment_ids": [staged_id],
                        },
                    },
                }
            )
            if isinstance(raw, str):
                payload = json.loads(raw)
            elif hasattr(raw, "content"):
                payload = json.loads(raw.content)
            else:
                payload = raw
            result = ToolResult.model_validate(payload)
            assert result.ok is True
            assert result.data is not None
            assert result.data["attachment_id"] == staged_id

            async with factory() as session:
                draft = await profile_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id == staged_id
                active = await profile_repo.get_active_profile(session)
                assert active is not None
                assert active.active_attachment_id == active_id
                executions = await tool_repo.list_for_run_ids(session, [run.id])
                propose = [
                    item
                    for item in executions
                    if item.tool_name == PROPOSE_PROFILE_FROM_CV_NAME
                ]
                assert propose
                raw_summary = propose[0].arguments_summary_json
                summary = (
                    json.loads(raw_summary)
                    if isinstance(raw_summary, str)
                    else raw_summary
                )
                assert summary["attachment_id"] == staged_id
        finally:
            await engine.dispose()

    run_async(_body())


def test_digital_fixture_still_extracts_text_for_pipeline() -> None:
    """Sanity: real pypdf path remains usable for proposal pipeline tests."""
    extraction = extract_pdf_text(CV_DIR / "digital_cv_01.pdf")
    assert extraction.has_meaningful_text
    assert extraction.preferred_text
