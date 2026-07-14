"""Unit tests for structured CV extraction and propose_profile_from_cv (02B).

Fake-backed only — never calls the live ShopAIKey provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import ATTACHMENT_STATE_FAILED
from app.db.models.profiles import CANDIDATE_PROFILE_ID, PROFILE_DRAFT_ID
from app.db.session import build_async_engine
from app.repositories import attachments as att_repo
from app.repositories import profiles as profile_repo
from app.schemas.tools import ToolResult
from app.services.pdf_extraction import (
    NO_EXTRACTABLE_TEXT,
    PdfTextExtraction,
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
    ExtractedCandidateProfile,
    ExtractedSkillItem,
    ProfileExtractionError,
    ShopAIKeyStructuredProfileInvoker,
    build_draft_from_extracted,
    classify_provider_error,
    compact_draft_summary,
    empty_job_preferences,
    extract_profile_from_pdf,
    extracted_to_candidate_profile,
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


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _valid_extracted(**overrides: Any) -> ExtractedCandidateProfile:
    base: dict[str, Any] = {
        "summary": "Backend engineer with Python and FastAPI experience.",
        "current_title": "Senior Backend Engineer",
        "total_experience_years": 6.0,
        "skills": [
            {
                "name": "Python",
                "confidence": 0.9,
                "proficiency": "advanced",
                "years": 5.0,
                "evidence": ["5 years Python"],
            },
            {
                "name": "React.js",
                "confidence": 0.7,
                "proficiency": "intermediate",
                "years": 2.0,
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
    return ExtractedCandidateProfile.model_validate(base)


class FakeStructuredInvoker:
    """Scripted invoker: returns payloads or raises in order."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedCandidateProfile | dict[str, Any]:
        self.calls.append(
            {
                "is_repair": is_repair,
                "message_count": len(list(messages)),
                # Assert no accidental persistence of raw text via call log dumps
                # in ToolResult — we only record counts.
            }
        )
        if not self.script:
            raise RuntimeError("fake invoker script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item("fake error")
        return item


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


def test_shopaikey_invoker_uses_with_structured_output() -> None:
    """Production invoker binds strict json_schema structured output (no network)."""
    fake_model = MagicMock()
    bound = MagicMock()
    fake_model.with_structured_output.return_value = bound
    bound.invoke.return_value = _valid_extracted()

    invoker = ShopAIKeyStructuredProfileInvoker(model=fake_model)
    assert invoker.model_name  # may fall back to locked default
    fake_model.with_structured_output.assert_called_once()
    kwargs = fake_model.with_structured_output.call_args
    assert kwargs.kwargs.get("method") == "json_schema"
    assert kwargs.kwargs.get("strict") is True
    assert kwargs.args[0] is ExtractedCandidateProfile or (
        kwargs.kwargs.get("schema") is ExtractedCandidateProfile
    )

    result = invoker.invoke_structured([MagicMock()])
    assert isinstance(result, ExtractedCandidateProfile)
    assert result.current_title == "Senior Backend Engineer"


def test_normalize_skills_and_empty_preferences() -> None:
    extracted = _valid_extracted()
    draft = build_draft_from_extracted(extracted, _normalizer())
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


def test_valid_extraction_from_digital_fixture() -> None:
    pdf = CV_DIR / "digital_cv_01.pdf"
    invoker = FakeStructuredInvoker([_valid_extracted()])
    outcome = extract_profile_from_pdf(
        pdf, invoker=invoker, normalizer=_normalizer()
    )
    assert outcome.schema_repairs_used == 0
    assert outcome.provider_retries_used == 0
    assert outcome.draft.candidate_profile.summary
    assert len(invoker.calls) == 1
    assert invoker.calls[0]["is_repair"] is False


def test_no_extractable_text_short_circuit() -> None:
    pdf = CV_DIR / "image_only_cv.pdf"
    invoker = FakeStructuredInvoker([_valid_extracted()])
    with pytest.raises(ProfileExtractionError) as ei:
        extract_profile_from_pdf(pdf, invoker=invoker, normalizer=_normalizer())
    assert ei.value.code == FAILURE_NO_EXTRACTABLE_TEXT
    assert ei.value.code == NO_EXTRACTABLE_TEXT
    assert invoker.calls == []


def test_exactly_one_schema_repair_then_success() -> None:
    invoker = FakeStructuredInvoker(
        [
            ValidationError.from_exception_data(
                "ExtractedCandidateProfile",
                [
                    {
                        "type": "missing",
                        "loc": ("summary",),
                        "input": {},
                    }
                ],
            ),
            _valid_extracted(),
        ]
    )
    # Bypass PDF: inject meaningful extraction.
    fake_pdf = PdfTextExtraction(
        page_count=1,
        normal_text="x" * 100 + " email engineer python",
        layout_text="name email experience engineer skills python docker",
        normal_is_meaningful=True,
        layout_is_meaningful=True,
    )
    outcome = extract_profile_from_pdf(
        b"%PDF-fake",
        invoker=invoker,
        normalizer=_normalizer(),
        extract_text_fn=lambda _s: fake_pdf,
    )
    assert outcome.schema_repairs_used == 1
    assert len(invoker.calls) == 2
    assert invoker.calls[0]["is_repair"] is False
    assert invoker.calls[1]["is_repair"] is True


def test_schema_repair_exhausted_fails() -> None:
    bad = ValidationError.from_exception_data(
        "ExtractedCandidateProfile",
        [{"type": "missing", "loc": ("summary",), "input": {}}],
    )
    invoker = FakeStructuredInvoker([bad, bad])
    fake_pdf = PdfTextExtraction(
        page_count=1,
        normal_text="name email experience engineer skills python " + ("z" * 80),
        layout_text="name email experience engineer skills python " + ("z" * 80),
        normal_is_meaningful=True,
        layout_is_meaningful=True,
    )
    with pytest.raises(ProfileExtractionError) as ei:
        extract_profile_from_pdf(
            b"%PDF-fake",
            invoker=invoker,
            normalizer=_normalizer(),
            extract_text_fn=lambda _s: fake_pdf,
        )
    assert ei.value.code == FAILURE_INVALID_STRUCTURED_OUTPUT
    assert len(invoker.calls) == 2


def test_exactly_one_timeout_retry_then_success() -> None:
    invoker = FakeStructuredInvoker([APITimeoutError("timeout"), _valid_extracted()])
    fake_pdf = PdfTextExtraction(
        page_count=1,
        normal_text="name email experience engineer skills python " + ("a" * 80),
        layout_text="name email experience engineer skills python " + ("a" * 80),
        normal_is_meaningful=True,
        layout_is_meaningful=True,
    )
    outcome = extract_profile_from_pdf(
        b"%PDF-fake",
        invoker=invoker,
        normalizer=_normalizer(),
        extract_text_fn=lambda _s: fake_pdf,
    )
    assert outcome.provider_retries_used == 1
    assert len(invoker.calls) == 2


def test_timeout_retry_exhausted() -> None:
    invoker = FakeStructuredInvoker(
        [APITimeoutError("t1"), APITimeoutError("t2")]
    )
    fake_pdf = PdfTextExtraction(
        page_count=1,
        normal_text="name email experience engineer skills python " + ("b" * 80),
        layout_text="name email experience engineer skills python " + ("b" * 80),
        normal_is_meaningful=True,
        layout_is_meaningful=True,
    )
    with pytest.raises(ProfileExtractionError) as ei:
        extract_profile_from_pdf(
            b"%PDF-fake",
            invoker=invoker,
            normalizer=_normalizer(),
            extract_text_fn=lambda _s: fake_pdf,
        )
    assert ei.value.code == FAILURE_PROVIDER_TIMEOUT
    assert len(invoker.calls) == 2


def test_rate_limit_retry_once() -> None:
    invoker = FakeStructuredInvoker(
        [RateLimitError("rate"), _valid_extracted()]
    )
    fake_pdf = PdfTextExtraction(
        page_count=1,
        normal_text="name email experience engineer skills python " + ("c" * 80),
        layout_text="name email experience engineer skills python " + ("c" * 80),
        normal_is_meaningful=True,
        layout_is_meaningful=True,
    )
    outcome = extract_profile_from_pdf(
        b"%PDF-fake",
        invoker=invoker,
        normalizer=_normalizer(),
        extract_text_fn=lambda _s: fake_pdf,
    )
    assert outcome.provider_retries_used == 1
    assert classify_provider_error(RateLimitError("x")) == FAILURE_PROVIDER_RATE_LIMIT


def test_raw_cv_text_absent_from_compact_outputs() -> None:
    draft = build_draft_from_extracted(_valid_extracted(), _normalizer())
    compact = compact_draft_summary(draft)
    dumped = str(compact)
    assert "CV TEXT" not in dumped
    assert "---" not in dumped
    args = arguments_summary_for_propose_cv("att-1")
    assert args == {"attachment_id": "att-1"}


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
    invoker = FakeStructuredInvoker([_valid_extracted()])
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
                profile_json = extracted_to_candidate_profile(
                    _valid_extracted(), normalizer
                ).model_dump(mode="json")
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
    invoker = FakeStructuredInvoker([_valid_extracted()])
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"
    draft = build_draft_from_extracted(_valid_extracted(), normalizer)

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
    invoker = FakeStructuredInvoker([_valid_extracted()])
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"
    old_draft = build_draft_from_extracted(
        _valid_extracted(summary="old draft summary"), normalizer
    )

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
            assert invoker.calls  # provider used once

            async with factory() as session:
                draft_row = await profile_repo.get_current_draft(session)
                assert draft_row is not None
                assert draft_row.source_attachment_id == new_id
                assert draft_row.draft_json["candidate_profile"]["summary"]
                assert await att_repo.get_by_id(session, old_id) is None
                assert await att_repo.get_by_id(session, new_id) is not None
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
    invoker = FakeStructuredInvoker([])  # unused — no text path
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
    invoker = FakeStructuredInvoker(
        [APITimeoutError("t1"), APITimeoutError("t2")]
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
    invoker = FakeStructuredInvoker([_valid_extracted()])
    normalizer = _normalizer()
    pdf = CV_DIR / "digital_cv_01.pdf"

    # Production registry: three profile tools then save_job and query_jobs.
    prod_names = production_registry().tool_names()
    assert PROPOSE_PROFILE_FROM_CV_NAME in prod_names
    assert prod_names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
    ]
    assert "match_jobs" not in prod_names

    async def _ainvoke_with_identity(
        tool_fn: Any,
        *,
        run_id: str,
        tool_call_id: str,
        attachment_id: str,
    ) -> ToolResult:
        """ToolCall shape so InjectedToolCallId / InjectedState resolve."""
        raw = await tool_fn.ainvoke(
            {
                "type": "tool_call",
                "id": tool_call_id,
                "name": tool_fn.name,
                "args": {
                    "attachment_id": attachment_id,
                    "state": {"run_id": run_id},
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
            assert set(props) == {"attachment_id"}
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


def test_digital_fixture_still_extracts_text_for_pipeline() -> None:
    """Sanity: real pypdf path remains usable for proposal pipeline tests."""
    extraction = extract_pdf_text(CV_DIR / "digital_cv_01.pdf")
    assert extraction.has_meaningful_text
    assert extraction.preferred_text


def test_invalid_skill_row_filtered_by_empty_name() -> None:
    extracted = _valid_extracted(
        skills=[
            ExtractedSkillItem(
                name="   ",
                confidence=0.5,
                proficiency="unknown",
                years=None,
                evidence=[],
            ),
            ExtractedSkillItem(
                name="Python",
                confidence=0.9,
                proficiency="advanced",
                years=3.0,
                evidence=["Python"],
            ),
        ]
    )
    profile = extracted_to_candidate_profile(extracted, _normalizer())
    assert len(profile.skills) == 1
