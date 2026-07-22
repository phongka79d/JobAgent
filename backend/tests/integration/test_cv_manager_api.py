"""Integration tests for CV Manager reprocess API (Plan 9 03A).

Covers eligibility, SSE approval contract, ownership, draft-only pending state,
Request Changes preservation, Save Profile switch/same-active refresh, and
stable error codes without mutation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
)
from app.db.models.profiles import PROFILE_DRAFT_ID
from app.db.session import build_async_engine, get_session_factory
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as prof_repo
from app.repositories import tool_executions as tool_repo
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage
from app.tools.profile import (
    PROFILE_COMMIT_ACTIONS,
    PROFILE_COMMIT_KIND,
    PROPOSE_PROFILE_FROM_CV_NAME,
    build_commit_profile_draft_tool,
    build_propose_profile_from_cv_tool,
)
from app.tools.registry import ToolRegistry

from tests.fakes.fake_chat_model import FakeChatModel
from tests.support.db_migration import run_async, session_factory
from tests.support.health import install_fake_driver, prepare_health_env
from tests.support.public_api import (
    ai_text,
    ai_tool_call,
    client_with_fake_chat,
    override_chat_deps,
    parse_sse_wire,
)


def _cv_fixture(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "cv" / name


def _skills_fixture() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"


class _CoveringDocumentInvoker:
    """Document-first invoker covering ordinals found in prompts."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke_structured(
        self,
        messages: Any,
        *,
        schema_name: str,
        is_repair: bool = False,
    ) -> Any:
        del is_repair
        from app.services.cv_document_extraction import (
            ExtractedBatchDocument,
            ExtractedConsolidation,
            ExtractedEntryFragment,
            ExtractedSectionFragment,
        )

        self.calls += 1
        joined = "\n".join(
            getattr(m, "content", "")
            for m in list(messages)
            if isinstance(getattr(m, "content", None), str)
        )
        if schema_name == "candidate_skills":
            serialized = joined.split(
                "CV ENTRY RECORDS START\n",
                maxsplit=1,
            )[1].split("\nCV ENTRY RECORDS END", maxsplit=1)[0]
            records = json.loads(serialized)
            skill_record = next(
                record for record in records if record.get("body") == "Python"
            )
            return {
                "assertions": [
                    {
                        "name": "Python",
                        "confidence": 0.9,
                        "proficiency": "advanced",
                        "years": None,
                        "evidence": ["Python"],
                        "source_entry_ids": [skill_record["entry_id"]],
                    }
                ]
            }
        ordinals = sorted(
            {int(m) for m in re.findall(r"\[ordinal=(\d+)\]", joined)}
        ) or [0]
        first = ordinals[0]
        sections = [
            ExtractedSectionFragment(
                heading="Summary",
                kind="summary",
                entries=[
                    ExtractedEntryFragment(
                        title="Backend Engineer",
                        subtitle=None,
                        date_text=None,
                        location=None,
                        body="Integration-test backend engineer.",
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
                        body="Python",
                        bullets=["Python"],
                        attributes=[],
                        source_chunk_ordinals=ordinals,
                    )
                ],
                source_chunk_ordinals=ordinals,
            ),
        ]
        if schema_name == "batch":
            return ExtractedBatchDocument(
                detected_languages=["en"],
                sections=sections,
                extraction_warnings=[],
                extraction_confidence=0.8,
            )
        return ExtractedConsolidation(
            detected_languages=["en"],
            sections=sections,
            extraction_warnings=[],
            extraction_confidence=0.8,
        )


def _event_names(events: list[dict[str, Any]]) -> list[str]:
    return [e["event"] for e in events]


def _write_real_pdf(storage: AttachmentStorage, attachment_id: str) -> str:
    pdf = _cv_fixture("digital_cv_01.pdf")
    return storage.write_bytes(attachment_id, pdf.read_bytes())


def _approval_profile_json() -> dict[str, Any]:
    return {
        "summary": "Backend engineer",
        "current_title": "Backend Engineer",
        "total_experience_years": 4.0,
        "skills": [
            {
                "skill": {
                    "canonical_key": "python",
                    "display_name": "Python",
                    "aliases": ["python3"],
                    "category": "language",
                },
                "confidence": 0.9,
                "proficiency": "advanced",
                "years": 4.0,
                "source": "cv",
                "excluded": False,
                "evidence": ["Python backend"],
            }
        ],
        "experiences": [
            {
                "title": "Engineer",
                "company": "Co",
                "start_date_text": "2020",
                "end_date_text": "present",
                "summary": "APIs",
            }
        ],
        "education": [
            {
                "institution": "U",
                "degree": "BSc",
                "field": "CS",
                "graduation_year": 2019,
            }
        ],
        "languages": [{"name": "English", "proficiency": "fluent"}],
        "extraction_confidence": 0.8,
    }


@pytest.fixture
def reprocess_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, Path]:
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    install_fake_driver(monkeypatch)
    return db_path, files_dir


def _build_registry(
    *,
    factory: Any,
    storage: AttachmentStorage,
    invoker: _CoveringDocumentInvoker,
    normalizer: SkillNormalizer,
) -> ToolRegistry:
    return ToolRegistry(
        [
            build_propose_profile_from_cv_tool(
                session_factory=factory,
                storage=storage,
                invoker=invoker,  # type: ignore[arg-type]
                normalizer=normalizer,
            ),
            build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                sync_fn=_noop_sync,
            ),
        ]
    )


async def _noop_sync(**kwargs: object) -> None:
    return None


def test_reprocess_unknown_attachment_404(reprocess_env: tuple[Path, Path]) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    registry = ToolRegistry([])
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text("noop")]), registry
    ) as client:
        missing = new_uuid()
        resp = client.post(f"/api/cvs/{missing}/reprocess")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "CV_ATTACHMENT_NOT_FOUND"


def test_reprocess_rejects_staged_and_failed(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()

    async def _seed() -> tuple[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            staged_id = new_uuid()
            failed_id = new_uuid()
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="staged-rp",
                    original_name="s.pdf",
                    size_bytes=10,
                    storage_path=_write_real_pdf(storage, staged_id),
                    page_count=1,
                    attachment_id=staged_id,
                )
                await att_repo.create_staged(
                    session,
                    file_hash="failed-rp",
                    original_name="f.pdf",
                    size_bytes=10,
                    storage_path=_write_real_pdf(storage, failed_id),
                    page_count=1,
                    attachment_id=failed_id,
                )
                await att_repo.mark_failed(
                    session, failed_id, failure_code="NO_EXTRACTABLE_TEXT"
                )
                await session.commit()
            return staged_id, failed_id
        finally:
            await engine.dispose()

    staged_id, failed_id = run_async(_seed())
    registry = ToolRegistry([])
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text("noop")]), registry
    ) as client:
        for att_id in (staged_id, failed_id):
            resp = client.post(f"/api/cvs/{att_id}/reprocess")
            assert resp.status_code == 409
            assert resp.json()["detail"]["code"] == "CV_NOT_REPROCESSABLE"


def test_reprocess_missing_file_no_mutation(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="miss-file",
                    original_name="m.pdf",
                    size_bytes=10,
                    storage_path=att_id,  # never written
                    page_count=1,
                    attachment_id=att_id,
                )
                await att_repo.mark_active(session, att_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=_approval_profile_json(),
                )
                await session.commit()
            return att_id
        finally:
            await engine.dispose()

    att_id = run_async(_seed())
    registry = ToolRegistry([])
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text("noop")]), registry
    ) as client:
        resp = client.post(f"/api/cvs/{att_id}/reprocess")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "CV_FILE_UNAVAILABLE"

    async def _assert() -> None:
        factory = get_session_factory()
        async with factory() as session:
            att = await att_repo.get_by_id(session, att_id)
            assert att is not None
            assert att.state == ATTACHMENT_STATE_ACTIVE
            assert await prof_repo.get_current_draft(session) is None
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert profile.active_attachment_id == att_id

    run_async(_assert())


def test_reprocess_active_sse_approval_and_ownership(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    invoker = _CoveringDocumentInvoker()
    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_real_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="active-rp",
                    original_name="a.pdf",
                    size_bytes=100,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await att_repo.mark_active(session, att_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=_approval_profile_json(),
                )
                await session.commit()
            return att_id
        finally:
            await engine.dispose()

    att_id = run_async(_seed())
    factory = get_session_factory()
    registry = _build_registry(
        factory=factory,
        storage=storage,
        invoker=invoker,
        normalizer=normalizer,
    )
    model = FakeChatModel(
        responses=[
            ai_tool_call(
                PROPOSE_PROFILE_FROM_CV_NAME,
                call_id="call-reprocess-active",
                args={"attachment_id": att_id, "reprocess": True},
            ),
        ]
    )
    with client_with_fake_chat(db_path, model, registry) as client:
        resp = client.post(f"/api/cvs/{att_id}/reprocess")
        assert resp.status_code == 200, resp.text
        events = parse_sse_wire(resp.text)
        names = _event_names(events)
        assert names[0] == "run_started"
        assert "tool_status" in names
        assert names[-1] == "approval_required"
        assert "run_completed" not in names
        approval = events[-1]
        assert approval["payload"]["kind"] == PROFILE_COMMIT_KIND
        assert approval["payload"]["allowed_actions"] == list(PROFILE_COMMIT_ACTIONS)
        run_id = approval["run_id"]

    async def _assert_pending() -> None:
        async with factory() as session:
            run = await runs_repo.get_run(session, run_id)
            assert run is not None
            assert run.state == "interrupted"
            assert run.source_attachment_id == att_id
            msgs = await messages_repo.list_messages(session)
            owned = [m for m in msgs if m.source_attachment_id == att_id]
            assert owned
            draft = await prof_repo.get_current_draft(session)
            assert draft is not None
            assert draft.source_attachment_id == att_id
            doc = await cv_doc_repo.get_draft(session, att_id)
            assert doc is not None
            att = await att_repo.get_by_id(session, att_id)
            assert att is not None
            assert att.state == ATTACHMENT_STATE_ACTIVE
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert profile.active_attachment_id == att_id
            # Prior approved document (if any) absent; active profile unchanged.
            tools = await tool_repo.list_for_run_ids(session, [run_id])
            propose_tools = [
                t for t in tools if t.tool_name == PROPOSE_PROFILE_FROM_CV_NAME
            ]
            assert propose_tools
            assert propose_tools[0].source_attachment_id == att_id

    run_async(_assert_pending())
    assert invoker.calls >= 1


def test_reprocess_approval_required_blocks_second(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    invoker = _CoveringDocumentInvoker()
    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_real_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="lock-rp",
                    original_name="a.pdf",
                    size_bytes=100,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await att_repo.mark_active(session, att_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=_approval_profile_json(),
                )
                await session.commit()
            return att_id
        finally:
            await engine.dispose()

    att_id = run_async(_seed())
    factory = get_session_factory()
    registry = _build_registry(
        factory=factory,
        storage=storage,
        invoker=invoker,
        normalizer=normalizer,
    )
    model = FakeChatModel(
        responses=[
            ai_tool_call(
                PROPOSE_PROFILE_FROM_CV_NAME,
                call_id="call-lock",
                args={"attachment_id": att_id, "reprocess": True},
            ),
        ]
    )
    with client_with_fake_chat(db_path, model, registry) as client:
        first = client.post(f"/api/cvs/{att_id}/reprocess")
        assert first.status_code == 200
        second = client.post(f"/api/cvs/{att_id}/reprocess")
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "APPROVAL_ACTION_REQUIRED"


def test_reprocess_archived_request_changes_and_save_switch(
    reprocess_env: tuple[Path, Path],
) -> None:
    """Archived reprocess: pending keeps prior active; Save Profile switches."""
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    invoker = _CoveringDocumentInvoker()
    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _seed() -> tuple[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            active_id = new_uuid()
            archived_id = new_uuid()
            active_rel = _write_real_pdf(storage, active_id)
            archived_rel = _write_real_pdf(storage, archived_id)
            async with factory() as session:
                # Create archived first, then active (one-active invariant).
                await att_repo.create_staged(
                    session,
                    file_hash="arch-old",
                    original_name="old.pdf",
                    size_bytes=100,
                    storage_path=archived_rel,
                    page_count=1,
                    attachment_id=archived_id,
                )
                await att_repo.mark_active(session, archived_id)
                await att_repo.mark_archived(session, archived_id)
                await att_repo.create_staged(
                    session,
                    file_hash="arch-active",
                    original_name="cur.pdf",
                    size_bytes=100,
                    storage_path=active_rel,
                    page_count=1,
                    attachment_id=active_id,
                )
                await att_repo.mark_active(session, active_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=active_id,
                    profile_json=_approval_profile_json(),
                )
                await session.commit()
            return active_id, archived_id
        finally:
            await engine.dispose()

    active_id, archived_id = run_async(_seed())
    factory = get_session_factory()
    registry = _build_registry(
        factory=factory,
        storage=storage,
        invoker=invoker,
        normalizer=normalizer,
    )
    model = FakeChatModel(
        responses=[
            ai_tool_call(
                PROPOSE_PROFILE_FROM_CV_NAME,
                call_id="call-arch-propose",
                args={"attachment_id": archived_id, "reprocess": True},
            ),
        ]
    )
    with client_with_fake_chat(db_path, model, registry) as client:
        propose = client.post(f"/api/cvs/{archived_id}/reprocess")
        assert propose.status_code == 200, propose.text
        events = parse_sse_wire(propose.text)
        assert _event_names(events)[-1] == "approval_required"
        run_id = events[-1]["run_id"]

        # Request Changes: archived stays archived; active unchanged.
        override_chat_deps(
            client,
            model=FakeChatModel(responses=[ai_text("changes noted")]),
            registry=registry,
            db_path=db_path,
        )
        rc = client.post(
            f"/api/chat/runs/{run_id}/resume",
            json={"action": "request_changes"},
        )
        assert rc.status_code == 200, rc.text
        assert "run_completed" in _event_names(parse_sse_wire(rc.text))

    async def _assert_after_rc() -> None:
        async with factory() as session:
            draft = await prof_repo.get_current_draft(session)
            assert draft is not None
            assert draft.source_attachment_id == archived_id
            assert draft.id == PROFILE_DRAFT_ID
            active = await att_repo.get_by_id(session, active_id)
            archived = await att_repo.get_by_id(session, archived_id)
            assert active is not None and active.state == ATTACHMENT_STATE_ACTIVE
            assert archived is not None and archived.state == ATTACHMENT_STATE_ARCHIVED
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert profile.active_attachment_id == active_id

    run_async(_assert_after_rc())

    # Re-enter reprocess → save_profile switch.
    model2 = FakeChatModel(
        responses=[
            ai_tool_call(
                PROPOSE_PROFILE_FROM_CV_NAME,
                call_id="call-arch-propose-2",
                args={"attachment_id": archived_id, "reprocess": True},
            ),
        ]
    )
    with client_with_fake_chat(db_path, model2, registry) as client:
        propose2 = client.post(f"/api/cvs/{archived_id}/reprocess")
        assert propose2.status_code == 200, propose2.text
        run_id2 = parse_sse_wire(propose2.text)[-1]["run_id"]
        override_chat_deps(
            client,
            model=FakeChatModel(responses=[ai_text("saved")]),
            registry=registry,
            db_path=db_path,
        )
        save = client.post(
            f"/api/chat/runs/{run_id2}/resume",
            json={"action": "save_profile"},
        )
        assert save.status_code == 200, save.text
        assert "run_completed" in _event_names(parse_sse_wire(save.text))

    async def _assert_switched() -> None:
        async with factory() as session:
            assert await prof_repo.get_current_draft(session) is None
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert profile.active_attachment_id == archived_id
            new_active = await att_repo.get_by_id(session, archived_id)
            old = await att_repo.get_by_id(session, active_id)
            assert new_active is not None
            assert new_active.state == ATTACHMENT_STATE_ACTIVE
            assert old is not None
            assert old.state == ATTACHMENT_STATE_ARCHIVED
            approved = await cv_doc_repo.get_document(session, archived_id)
            assert approved is not None
            assert await cv_doc_repo.get_draft(session, archived_id) is None

    run_async(_assert_switched())


def test_reprocess_same_active_save_refreshes_document(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    invoker = _CoveringDocumentInvoker()
    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_real_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="same-active",
                    original_name="a.pdf",
                    size_bytes=100,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await att_repo.mark_active(session, att_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=_approval_profile_json(),
                )
                await session.commit()
            return att_id
        finally:
            await engine.dispose()

    att_id = run_async(_seed())
    factory = get_session_factory()
    registry = _build_registry(
        factory=factory,
        storage=storage,
        invoker=invoker,
        normalizer=normalizer,
    )
    model = FakeChatModel(
        responses=[
            ai_tool_call(
                PROPOSE_PROFILE_FROM_CV_NAME,
                call_id="call-same",
                args={"attachment_id": att_id, "reprocess": True},
            ),
        ]
    )
    with client_with_fake_chat(db_path, model, registry) as client:
        propose = client.post(f"/api/cvs/{att_id}/reprocess")
        assert propose.status_code == 200
        run_id = parse_sse_wire(propose.text)[-1]["run_id"]
        override_chat_deps(
            client,
            model=FakeChatModel(responses=[ai_text("saved")]),
            registry=registry,
            db_path=db_path,
        )
        save = client.post(
            f"/api/chat/runs/{run_id}/resume",
            json={"action": "save_profile"},
        )
        assert save.status_code == 200

    async def _assert() -> None:
        async with factory() as session:
            att = await att_repo.get_by_id(session, att_id)
            assert att is not None
            assert att.state == ATTACHMENT_STATE_ACTIVE
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert profile.active_attachment_id == att_id
            assert await prof_repo.get_current_draft(session) is None
            doc = await cv_doc_repo.get_document(session, att_id)
            assert doc is not None
            assert doc.source_hash

    run_async(_assert())
