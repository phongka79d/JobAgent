"""Unit tests for JD confirmation schemas and service (Plan 12 01A)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_USER,
)
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.schemas.jobs import (
    JOB_INGEST_OUTCOMES,
    SAVE_JOB_CANCEL_OUTCOME,
    SAVE_JOB_PREVIEW_COMPANY_MAX,
    SAVE_JOB_PREVIEW_SKILL_MAX,
    SAVE_JOB_PREVIEW_SKILLS_MAX,
    SAVE_JOB_PREVIEW_TITLE_MAX,
    SAVE_JOB_SOURCE_CURRENT_MESSAGE,
    SaveJobCancellationData,
    SaveJobInput,
    SaveJobPreview,
    SaveJobResultData,
)
from app.schemas.tools import ToolResult
from app.services import job_save_confirmation as conf
from pydantic import ValidationError

from tests.support.db_migration import run_async, session_factory

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = BACKEND_ROOT / "app" / "services" / "job_save_confirmation.py"

# Forbidden keys that must never appear in pending projection dumps.
_FORBIDDEN_PROJECTION_KEYS: frozenset[str] = frozenset(
    {
        "raw",
        "raw_jd",
        "message_id",
        "user_message_id",
        "url",
        "source_url",
        "hash",
        "content_hash",
        "arguments",
        "prompt",
        "provider",
        "credential",
        "api_key",
        "password",
        "storage",
        "storage_path",
        "stack",
        "traceback",
        "content",
        "text",
    }
)


def _markers(*names: str) -> str:
    return "\n".join(names)


def _pad_non_ws(base: str, minimum: int = conf.OBVIOUS_JD_MIN_NON_WS_CHARS) -> str:
    """Append non-whitespace padding until *minimum* non-ws chars."""
    body = base
    while conf._non_whitespace_char_count(body) < minimum:  # noqa: SLF001
        body += "x"
    return body


def _obvious_jd_body(
    *,
    markers: tuple[str, str] = ("responsibilities", "requirements"),
    min_lines: int = conf.OBVIOUS_JD_MIN_NON_EMPTY_LINES,
    min_chars: int = conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
) -> str:
    lines = [markers[0], markers[1], "line three", "line four", "line five"]
    while len(lines) < min_lines:
        lines.append(f"extra line {len(lines)}")
    body = "\n".join(lines)
    return _pad_non_ws(body, min_chars)


# ---------------------------------------------------------------------------
# SaveJobInput three-way union
# ---------------------------------------------------------------------------


def test_save_job_input_accepts_url_only() -> None:
    model = SaveJobInput.model_validate({"url": "https://example.com/job"})
    assert model.url == "https://example.com/job"
    assert model.text is None
    assert model.source is None
    assert model.preview is None


def test_save_job_input_accepts_text_only() -> None:
    model = SaveJobInput.model_validate({"text": "Senior Engineer role"})
    assert model.text == "Senior Engineer role"
    assert model.url is None
    assert model.source is None


def test_save_job_input_accepts_current_message_without_preview() -> None:
    model = SaveJobInput.model_validate(
        {"source": SAVE_JOB_SOURCE_CURRENT_MESSAGE}
    )
    assert model.source == "current_message"
    assert model.url is None
    assert model.text is None
    assert model.preview is None


def test_save_job_input_rejects_empty_and_dual_and_triple_sources() -> None:
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate({})
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate({"url": "", "text": "  "})
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate(
            {"url": "https://a.example", "text": "body"}
        )
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate(
            {
                "url": "https://a.example",
                "source": SAVE_JOB_SOURCE_CURRENT_MESSAGE,
            }
        )
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate(
            {
                "text": "body",
                "source": SAVE_JOB_SOURCE_CURRENT_MESSAGE,
            }
        )
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate(
            {
                "url": "https://a.example",
                "text": "body",
                "source": SAVE_JOB_SOURCE_CURRENT_MESSAGE,
            }
        )


def test_save_job_input_rejects_unknown_source_and_extras() -> None:
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate({"source": "history"})
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate(
            {"source": SAVE_JOB_SOURCE_CURRENT_MESSAGE, "extra": True}
        )


def test_preview_only_with_current_message() -> None:
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate(
            {
                "url": "https://example.com/j",
                "preview": {"title": "T"},
            }
        )
    with pytest.raises(ValidationError):
        SaveJobInput.model_validate(
            {"text": "direct paste", "preview": {"title": "T"}}
        )
    ok = SaveJobInput.model_validate(
        {
            "source": SAVE_JOB_SOURCE_CURRENT_MESSAGE,
            "preview": {
                "title": " Backend ",
                "company": "  ",
                "skills": [" Python ", "", "  Docker  "],
            },
        }
    )
    assert ok.preview is not None
    assert ok.preview.title == "Backend"
    assert ok.preview.company is None
    assert ok.preview.skills == ["Python", "Docker"]


def test_preview_bounds_and_extras() -> None:
    with pytest.raises(ValidationError):
        SaveJobPreview.model_validate(
            {"title": "t" * (SAVE_JOB_PREVIEW_TITLE_MAX + 1)}
        )
    with pytest.raises(ValidationError):
        SaveJobPreview.model_validate(
            {"company": "c" * (SAVE_JOB_PREVIEW_COMPANY_MAX + 1)}
        )
    with pytest.raises(ValidationError):
        SaveJobPreview.model_validate(
            {
                "skills": ["ok"] * (SAVE_JOB_PREVIEW_SKILLS_MAX + 1),
            }
        )
    with pytest.raises(ValidationError):
        SaveJobPreview.model_validate(
            {"skills": ["s" * (SAVE_JOB_PREVIEW_SKILL_MAX + 1)]}
        )
    with pytest.raises(ValidationError):
        SaveJobPreview.model_validate({"title": "T", "raw_jd": "nope"})
    bounded = SaveJobPreview.model_validate(
        {
            "title": "t" * SAVE_JOB_PREVIEW_TITLE_MAX,
            "company": "c" * SAVE_JOB_PREVIEW_COMPANY_MAX,
            "skills": ["s" * SAVE_JOB_PREVIEW_SKILL_MAX]
            * SAVE_JOB_PREVIEW_SKILLS_MAX,
        }
    )
    assert len(bounded.skills) == SAVE_JOB_PREVIEW_SKILLS_MAX


def test_preview_preserves_skill_order() -> None:
    preview = SaveJobPreview.model_validate(
        {"skills": ["Zeta", "Alpha", "Mid"]}
    )
    assert preview.skills == ["Zeta", "Alpha", "Mid"]


# ---------------------------------------------------------------------------
# Cancellation model separation
# ---------------------------------------------------------------------------


def test_cancellation_model_not_ingest_outcome() -> None:
    cancel = SaveJobCancellationData(
        committed=False, outcome=SAVE_JOB_CANCEL_OUTCOME
    )
    dumped = cancel.model_dump(mode="json")
    assert dumped == {"committed": False, "outcome": "cancelled"}
    assert "cancelled" not in JOB_INGEST_OUTCOMES
    with pytest.raises(ValidationError):
        SaveJobCancellationData.model_validate(
            {"committed": True, "outcome": "cancelled"}
        )
    with pytest.raises(ValidationError):
        SaveJobCancellationData.model_validate(
            {"committed": False, "outcome": "created"}
        )
    with pytest.raises(ValidationError):
        SaveJobResultData.model_validate(
            {
                "job_id": new_uuid(),
                "processing_status": "processed",
                "outcome": "cancelled",
                "sqlite_committed": False,
            }
        )
    with pytest.raises(ValidationError):
        SaveJobResultData.model_validate(dumped)


def test_build_cancellation_tool_result_shape() -> None:
    result = conf.build_cancellation_tool_result()
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.code is None
    assert result.summary == conf.CANCEL_SUMMARY
    assert result.data == {"committed": False, "outcome": "cancelled"}
    SaveJobCancellationData.model_validate(result.data)
    with pytest.raises(ValidationError):
        SaveJobResultData.model_validate(result.data)


# ---------------------------------------------------------------------------
# Pure recognition predicates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "không lưu",
        "đừng lưu",
        "không cần lưu",
        "do not save",
        "don't save",
        "Please DO NOT SAVE this",
        "KHÔNG LƯU giúp tôi",
        "ĐỪNG LƯU",
    ],
)
def test_opt_out_phrases_detected(phrase: str) -> None:
    assert conf.message_has_clear_opt_out(phrase) is True


def test_opt_out_absent_on_normal_text() -> None:
    assert conf.message_has_clear_opt_out("Please save this job for me") is False
    assert conf.message_has_clear_opt_out(_obvious_jd_body()) is False


def test_sole_http_url_boundaries() -> None:
    assert conf.message_is_sole_http_url("https://example.com/jobs/1") is True
    assert conf.message_is_sole_http_url("HTTP://EXAMPLE.COM/A") is True
    assert conf.message_is_sole_http_url("  https://x.test/y  ") is True
    assert conf.message_is_sole_http_url("http://localhost:8000/j") is True
    assert conf.message_is_sole_http_url("ftp://example.com/x") is False
    assert conf.message_is_sole_http_url("see https://example.com/x") is False
    assert conf.message_is_sole_http_url("https://example.com/x\nmore") is False
    assert conf.message_is_sole_http_url("") is False
    assert conf.message_is_sole_http_url("not a url") is False


def test_obvious_jd_meets_thresholds() -> None:
    body = _obvious_jd_body()
    assert conf.message_is_obvious_jd(body) is True


def test_obvious_jd_rejects_short_char_boundary() -> None:
    # Exactly under the non-whitespace ceiling with enough lines/markers.
    lines = [
        "responsibilities",
        "requirements",
        "line3",
        "line4",
        "line5",
    ]
    body = "\n".join(lines)
    # Pad to exactly min-1 non-ws chars.
    target = conf.OBVIOUS_JD_MIN_NON_WS_CHARS - 1
    while conf._non_whitespace_char_count(body) < target:  # noqa: SLF001
        body += "y"
    # Trim if overshot.
    while conf._non_whitespace_char_count(body) > target:  # noqa: SLF001
        body = body[:-1]
    assert conf._non_whitespace_char_count(body) == target  # noqa: SLF001
    assert conf.message_is_obvious_jd(body) is False
    assert conf.message_is_obvious_jd(_pad_non_ws(body, target + 1)) is True


def test_obvious_jd_rejects_line_boundary() -> None:
    # Four non-empty lines only, enough chars and markers.
    body = _pad_non_ws(
        "responsibilities\nrequirements\nline3\nline4",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf._non_empty_line_count(body) == 4  # noqa: SLF001
    assert conf.message_is_obvious_jd(body) is False
    five = _pad_non_ws(
        "responsibilities\nrequirements\nline3\nline4\nline5",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(five) is True


def test_obvious_jd_rejects_single_marker_repetition() -> None:
    lines = ["responsibilities"] * 6
    body = _pad_non_ws("\n".join(lines), conf.OBVIOUS_JD_MIN_NON_WS_CHARS)
    assert conf.message_is_obvious_jd(body) is False


def test_obvious_jd_accepts_english_and_vietnamese_markers_crlf() -> None:
    en = _pad_non_ws(
        "Job Description\r\nResponsibilities\r\nline3\r\nline4\r\nline5",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(en) is True
    vi = _pad_non_ws(
        "Mô tả công việc\nYêu cầu\nline3\nline4\nline5",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(vi) is True
    vi2 = _pad_non_ws(
        "trách nhiệm\nkỹ năng\nline3\nline4\nline5",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(vi2) is True
    vi3 = _pad_non_ws(
        "quyền lợi\nmô tả vị trí\nline3\nline4\nline5",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(vi3) is True
    about = _pad_non_ws(
        "about the role\nqualifications\nline3\nline4\nline5",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(about) is True
    skills = _pad_non_ws(
        "skills\nrequirements\nline3\nline4\nline5",
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(skills) is True


def test_obvious_jd_rejects_ambiguous_prose() -> None:
    prose = _pad_non_ws(
        "\n".join(
            [
                "I am looking for advice about my career",
                "Please help me improve my resume",
                "What roles fit a backend engineer",
                "I enjoy APIs and databases",
                "Thanks for your help today",
            ]
        ),
        conf.OBVIOUS_JD_MIN_NON_WS_CHARS,
    )
    assert conf.message_is_obvious_jd(prose) is False


def test_ponytail_comment_present_on_obvious_jd_helper() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert "ponytail:" in source
    assert "typed composer intent" in source
    assert "false positive" in source or "false positives" in source


# ---------------------------------------------------------------------------
# Durable source resolution
# ---------------------------------------------------------------------------


async def _seed_run_with_message(
    factory: Any,
    *,
    content: str,
    role: str = CHAT_MESSAGE_ROLE_USER,
) -> tuple[str, str]:
    async with factory() as session:
        msg = await messages_repo.insert_message(
            session, role=role, content=content
        )
        run = await runs_repo.create_run(session, user_message_id=msg.id)
        await session.commit()
        return run.id, msg.id


def test_resolve_initiating_message_success(migrated_sqlite: Path) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)

    async def _body() -> None:
        try:
            run_id, msg_id = await _seed_run_with_message(
                factory, content="Exact durable JD body"
            )
            async with factory() as session:
                result = await conf.resolve_initiating_user_message(
                    session, run_id
                )
            assert isinstance(result, conf.InitiatingMessage)
            assert result.content == "Exact durable JD body"
            # Content only — no message id on the success type.
            assert conf.InitiatingMessage.__dataclass_fields__.keys() == {
                "content"
            }
            assert msg_id  # seed sanity
        finally:
            await engine.dispose()

    run_async(_body())


def test_resolve_missing_run(migrated_sqlite: Path) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)

    async def _body() -> None:
        try:
            async with factory() as session:
                result = await conf.resolve_initiating_user_message(
                    session, new_uuid()
                )
            assert isinstance(result, conf.SourceLookupFailure)
            assert result.code == conf.ERROR_CURRENT_MESSAGE_NOT_FOUND
        finally:
            await engine.dispose()

    run_async(_body())


def test_resolve_empty_run_id(migrated_sqlite: Path) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)

    async def _body() -> None:
        try:
            async with factory() as session:
                result = await conf.resolve_initiating_user_message(
                    session, "   "
                )
            assert isinstance(result, conf.SourceLookupFailure)
            assert result.code == conf.ERROR_CURRENT_MESSAGE_NOT_FOUND
        finally:
            await engine.dispose()

    run_async(_body())


def test_resolve_wrong_role(migrated_sqlite: Path) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)

    async def _body() -> None:
        try:
            run_id, _ = await _seed_run_with_message(
                factory,
                content="assistant text",
                role=CHAT_MESSAGE_ROLE_ASSISTANT,
            )
            async with factory() as session:
                result = await conf.resolve_initiating_user_message(
                    session, run_id
                )
            assert isinstance(result, conf.SourceLookupFailure)
            assert result.code == conf.ERROR_INVALID_CURRENT_MESSAGE
        finally:
            await engine.dispose()

    run_async(_body())


def test_resolve_empty_content(migrated_sqlite: Path) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)

    async def _body() -> None:
        try:
            async with factory() as session:
                # Empty content allowed only with structured_payload on insert.
                msg = await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="",
                    structured_payload={"kind": "marker"},
                )
                run = await runs_repo.create_run(
                    session, user_message_id=msg.id
                )
                await session.commit()
                run_id = run.id
            async with factory() as session:
                result = await conf.resolve_initiating_user_message(
                    session, run_id
                )
            assert isinstance(result, conf.SourceLookupFailure)
            assert result.code == conf.ERROR_INVALID_CURRENT_MESSAGE
        finally:
            await engine.dispose()

    run_async(_body())


def test_resolve_missing_message_row(migrated_sqlite: Path) -> None:
    """Missing chat_messages row yields CURRENT_MESSAGE_NOT_FOUND (repo None)."""
    from unittest.mock import AsyncMock, patch

    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)

    async def _body() -> None:
        try:
            run_id, _ = await _seed_run_with_message(
                factory, content="present body"
            )
            async with factory() as session:
                with patch.object(
                    messages_repo,
                    "get_by_id",
                    new=AsyncMock(return_value=None),
                ):
                    result = await conf.resolve_initiating_user_message(
                        session, run_id
                    )
            assert isinstance(result, conf.SourceLookupFailure)
            assert result.code == conf.ERROR_CURRENT_MESSAGE_NOT_FOUND
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Projection safety
# ---------------------------------------------------------------------------


def test_projection_approved_fields_only() -> None:
    content = _obvious_jd_body()
    preview = SaveJobPreview.model_validate(
        {
            "title": "Engineer",
            "company": "Acme",
            "skills": ["Python", "SQL"],
        }
    )
    tool_call_id = new_uuid()
    projection = conf.build_job_save_confirmation_projection(
        tool_call_id=tool_call_id,
        content=content,
        preview=preview,
    )
    assert projection["kind"] == conf.JOB_SAVE_CONFIRMATION_KIND
    assert projection["allowed_actions"] == list(
        conf.JOB_SAVE_CONFIRMATION_ACTIONS
    )
    card = projection["card"]
    assert set(card) == {
        "tool_name",
        "tool_call_id",
        "source",
        "text_length",
        "preview",
    }
    assert card["tool_name"] == "save_job"
    assert card["tool_call_id"] == tool_call_id
    assert card["source"] == "current_message"
    assert card["text_length"] == len(content)
    assert card["preview"] == {
        "title": "Engineer",
        "company": "Acme",
        "skills": ["Python", "SQL"],
    }
    blob = str(projection)
    assert content not in blob
    for key in _FORBIDDEN_PROJECTION_KEYS:
        assert key not in projection
        assert key not in card
        assert key not in card["preview"]


def test_projection_text_length_cap_and_default_preview() -> None:
    huge = "a" * (conf.TEXT_LENGTH_CAP + 50)
    projection = conf.build_job_save_confirmation_projection(
        tool_call_id="call-1",
        content=huge,
        preview=None,
    )
    assert projection["card"]["text_length"] == conf.TEXT_LENGTH_CAP
    assert projection["card"]["preview"] == {
        "title": None,
        "company": None,
        "skills": [],
    }


def test_projection_rejects_empty_tool_call_id() -> None:
    with pytest.raises(ValueError):
        conf.build_job_save_confirmation_projection(
            tool_call_id="  ",
            content="x",
        )


# ---------------------------------------------------------------------------
# Dependency direction / size / ownership hygiene
# ---------------------------------------------------------------------------


def test_service_does_not_import_tools_jobs() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("app.tools"), mod
            assert "tools.jobs" not in mod
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("app.tools")
    # Runtime: module object must not reference tools.jobs.
    assert "app.tools.jobs" not in getattr(conf, "__dict__", {})
    assert not any(
        name.startswith("app.tools")
        for name in getattr(conf, "__dict__", {})
    )


def test_service_line_count_under_300() -> None:
    lines = SERVICE_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 300


def test_resolve_uses_repository_getters() -> None:
    source = inspect.getsource(conf.resolve_initiating_user_message)
    assert "get_run" in source
    assert "get_by_id" in source
    assert "interrupt" not in source
    assert "ingest" not in source
    assert "embedding" not in source
