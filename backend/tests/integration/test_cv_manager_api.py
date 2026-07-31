"""Integration tests for CV Manager reprocess API (Plan 9 03A).

Covers eligibility, SSE approval contract, ownership, draft-only pending state,
Request Changes preservation, Save Profile switch/same-active refresh, and
stable error codes without mutation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_DELETING,
    ATTACHMENT_STATE_FAILED,
)
from app.db.models.profiles import Profile
from app.db.session import build_async_engine, get_session_factory
from app.repositories import attachments as att_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as prof_repo
from app.repositories import workspace_state as workspace_repo
from app.services.cv_manager_projection import allowed_actions
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage
from app.tools.profile import (
    build_commit_profile_draft_tool,
    build_propose_profile_from_cv_tool,
)
from app.tools.registry import ToolRegistry

from tests.fakes.fake_chat_model import FakeChatModel
from tests.support.db_migration import run_async, session_factory
from tests.support.health import install_fake_driver, prepare_health_env
from tests.support.public_api import (
    ai_text,
    client_with_fake_chat,
    parse_profile_reextract_wire,
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
                contacts=[],
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


def _override_direct_reextract(
    client: Any,
    *,
    storage: AttachmentStorage,
    invoker: _CoveringDocumentInvoker,
    normalizer: SkillNormalizer,
) -> None:
    """Route CV Manager tests through the direct typed re-extraction owner."""
    from app.api.dependencies import get_profile_reextract_deps

    client.app.dependency_overrides[get_profile_reextract_deps] = lambda: (
        SimpleNamespace(
            session_factory=get_session_factory(),
            storage=storage,
            document_invoker=invoker,
            normalizer=normalizer,
            graph_driver=None,
        )
    )


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
def reprocess_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
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


async def _seed_ready_profile_owner(session: Any, attachment_id: str) -> str:
    profile = await prof_repo.upsert_active_profile(
        session,
        active_attachment_id=attachment_id,
        profile_json=_approval_profile_json(),
    )
    await conversations_repo.create_for_profile(session, profile_id=profile.id)
    return profile.id


async def _seed_cv_manager_matrix(
    db_path: Path, storage: AttachmentStorage
) -> dict[str, str]:
    engine = build_async_engine(db_path)
    factory = session_factory(engine)
    try:
        async with factory() as session:

            async def seed(
                marker: str, name: str, *, state: str = ATTACHMENT_STATE_FAILED
            ) -> Any:
                aid = new_uuid()
                row = await att_repo.create_staged(
                    session,
                    file_hash=f"manager-{marker}",
                    original_name=name,
                    size_bytes=32,
                    storage_path=_write_real_pdf(storage, aid),
                    page_count=1,
                    attachment_id=aid,
                )
                if state == ATTACHMENT_STATE_ACTIVE:
                    await att_repo.mark_active(session, aid, page_count=1)
                elif state == ATTACHMENT_STATE_ARCHIVED:
                    await att_repo.mark_active(session, aid, page_count=1)
                    await att_repo.mark_archived(session, aid)
                elif state == ATTACHMENT_STATE_DELETING:
                    await att_repo.mark_deleting(session, aid)
                else:
                    await att_repo.mark_failed(
                        session, aid, failure_code="NO_EXTRACTABLE_TEXT"
                    )
                return row

            archived = await seed(
                "archived", "archived.pdf", state=ATTACHMENT_STATE_ARCHIVED
            )
            await prof_repo.create_profile(
                session,
                attachment_id=archived.id,
                display_name="Archived profile",
                profile_json=_approval_profile_json(),
                location=None,
                extraction_version="v1",
                source_hash="manager-archived-source",
            )
            active = await seed("active", "active.pdf", state=ATTACHMENT_STATE_ACTIVE)
            active_profile = await prof_repo.create_profile(
                session,
                attachment_id=active.id,
                display_name="Active profile",
                profile_json=_approval_profile_json(),
                location=None,
                extraction_version="v1",
                source_hash="manager-active-source",
            )
            pending = await seed("pending", "pending.pdf")
            await prof_repo.create_pending_profile(
                session,
                attachment_id=pending.id,
                display_name="Pending profile",
            )
            deleting = await seed(
                "deleting", "deleting.pdf", state=ATTACHMENT_STATE_DELETING
            )
            deleting_profile = await prof_repo.create_profile(
                session,
                attachment_id=deleting.id,
                display_name="Deleting profile",
                profile_json=_approval_profile_json(),
                location=None,
                extraction_version="v1",
                source_hash="manager-deleting-source",
            )
            deleting_profile.state = "deleting"
            failed_ready = await seed("failed-ready", "failed-ready.pdf")
            await prof_repo.create_profile(
                session,
                attachment_id=failed_ready.id,
                display_name="Failed ready profile",
                profile_json=_approval_profile_json(),
                location=None,
                extraction_version="v1",
                source_hash="manager-failed-ready-source",
            )
            orphan = await seed("orphan", "orphan.pdf")
            await workspace_repo.set_active_profile_id(session, active_profile.id)
            await session.commit()
            return {
                "active": active.id,
                "archived": archived.id,
                "pending": pending.id,
                "deleting": deleting.id,
                "failed_ready": failed_ready.id,
                "orphan": orphan.id,
            }
    finally:
        await engine.dispose()


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
        assert resp.json()["detail"] == "Not Found"


def test_cv_manager_list_projects_actions_without_storage_or_hash(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    ids = run_async(_seed_cv_manager_matrix(db_path, AttachmentStorage(files_dir)))
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text("noop")]), ToolRegistry([])
    ) as client:
        response = client.get("/api/cvs")

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()["items"]}
    assert by_id[ids["active"]]["allowed_actions"] == [
        "preview",
        "download",
        "reextract",
    ]
    assert by_id[ids["archived"]]["allowed_actions"] == [
        "preview",
        "download",
        "activate_profile",
    ]
    assert by_id[ids["pending"]]["allowed_actions"] == ["retry_upload"]
    assert by_id[ids["deleting"]]["allowed_actions"] == []
    assert by_id[ids["failed_ready"]]["allowed_actions"] == []
    assert by_id[ids["orphan"]]["allowed_actions"] == ["delete_cv"]
    assert all(
        "storage_path" not in item and "file_hash" not in item
        for item in by_id.values()
    )


def test_cv_manager_file_route_validates_disposition_and_ownership(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    ids = run_async(_seed_cv_manager_matrix(db_path, AttachmentStorage(files_dir)))
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text("noop")]), ToolRegistry([])
    ) as client:
        inline = client.get("/api/cvs/" + ids["active"] + "/file")
        attachment = client.get(
            "/api/cvs/" + ids["active"] + "/file?disposition=attachment"
        )
        invalid = client.get("/api/cvs/" + ids["active"] + "/file?disposition=download")
        pending = client.get("/api/cvs/" + ids["pending"] + "/file")

    assert inline.status_code == 200
    assert inline.headers["content-disposition"] == (
        "inline; filename=\"active.pdf\"; filename*=UTF-8''active.pdf"
    )
    assert inline.headers["x-content-type-options"] == "nosniff"
    assert inline.content.startswith(b"%PDF-")
    assert attachment.status_code == 200
    assert attachment.headers["content-disposition"] == (
        "attachment; filename=\"active.pdf\"; filename*=UTF-8''active.pdf"
    )
    assert invalid.status_code == 422
    assert pending.status_code == 404


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
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Not Found"


def test_reprocess_missing_file_no_mutation(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()

    async def _seed() -> tuple[str, str]:
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
                profile_id = await _seed_ready_profile_owner(session, att_id)
                await session.commit()
            return att_id, profile_id
        finally:
            await engine.dispose()

    att_id, profile_id = run_async(_seed())
    registry = ToolRegistry([])
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text("noop")]), registry
    ) as client:
        resp = client.post(f"/api/profiles/{profile_id}/reextract", json={})
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "CV_FILE_UNAVAILABLE"

    async def _assert() -> None:
        factory = get_session_factory()
        async with factory() as session:
            att = await att_repo.get_by_id(session, att_id)
            assert att is not None
            assert att.state == ATTACHMENT_STATE_ACTIVE
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert await prof_repo.get_draft_for_profile(session, profile.id) is None
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

    async def _seed() -> tuple[str, str]:
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
                profile_id = await _seed_ready_profile_owner(session, att_id)
                await session.commit()
            return att_id, profile_id
        finally:
            await engine.dispose()

    att_id, profile_id = run_async(_seed())
    factory = get_session_factory()
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[]), ToolRegistry([])
    ) as client:
        _override_direct_reextract(
            client,
            storage=storage,
            invoker=invoker,
            normalizer=normalizer,
        )
        resp = client.post(f"/api/profiles/{profile_id}/reextract", json={})
        assert resp.status_code == 200, resp.text
        events = parse_profile_reextract_wire(resp.text)
        names = _event_names(events)
        assert names[0] == "reextract_progress"
        assert names[-1] == "reextract_review_ready"
        assert not ({"run_started", "tool_status", "approval_required"} & set(names))
        operation_id = events[-1]["operation_id"]
        review = client.get(
            f"/api/profiles/{profile_id}/reextract-draft",
            params={"operation_id": operation_id},
        )
        assert review.status_code == 200, review.text
        assert review.json()["profile_id"] == profile_id
        assert review.json()["revision"] == events[-1]["payload"]["revision"]

    async def _assert_pending() -> None:
        from app.db.models.chat import AgentRun, ChatMessage, ToolExecution
        from sqlalchemy import func, select

        async with factory() as session:
            draft = await prof_repo.get_draft_for_profile(session, profile_id)
            assert draft is not None
            assert draft.source_attachment_id == att_id
            assert draft.target_profile_id == profile_id
            doc = await cv_doc_repo.get_draft(session, att_id)
            assert doc is not None
            att = await att_repo.get_by_id(session, att_id)
            assert att is not None
            assert att.state == ATTACHMENT_STATE_ACTIVE
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert profile.id == profile_id
            assert profile.active_attachment_id == att_id
            for model in (AgentRun, ChatMessage, ToolExecution):
                count = await session.scalar(select(func.count()).select_from(model))
                assert int(count or 0) == 0

    run_async(_assert_pending())
    assert invoker.calls >= 1


def test_reextract_rechecks_active_profile_before_creating_run_or_provider_work(
    reprocess_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.models.chat import AgentRun, ChatMessage
    from app.services import chat_turns
    from app.services.chat_turns import ChatTurnError
    from sqlalchemy import func, select

    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    pdf = _cv_fixture("digital_cv_01.pdf")

    async def _seed() -> tuple[str, str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            other_attachment_id = new_uuid()
            target_attachment_id = new_uuid()
            other_rel = _write_real_pdf(storage, other_attachment_id)
            target_rel = _write_real_pdf(storage, target_attachment_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="active-drift-other",
                    original_name="other.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=other_rel,
                    page_count=1,
                    attachment_id=other_attachment_id,
                )
                await att_repo.mark_active(session, other_attachment_id)
                await att_repo.mark_archived(session, other_attachment_id)
                other_profile = await prof_repo.create_profile(
                    session,
                    attachment_id=other_attachment_id,
                    display_name="Other",
                    profile_json=_approval_profile_json(),
                    location=None,
                    extraction_version="existing-v1",
                    source_hash="other-source",
                )
                await conversations_repo.create_for_profile(
                    session, profile_id=other_profile.id
                )
                await att_repo.create_staged(
                    session,
                    file_hash="active-drift-target",
                    original_name="target.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=target_rel,
                    page_count=1,
                    attachment_id=target_attachment_id,
                )
                await att_repo.mark_active(session, target_attachment_id)
                target_profile = await prof_repo.create_profile(
                    session,
                    attachment_id=target_attachment_id,
                    display_name="Target",
                    profile_json=_approval_profile_json(),
                    location=None,
                    extraction_version="existing-v1",
                    source_hash="target-source",
                )
                conversation = await conversations_repo.create_for_profile(
                    session, profile_id=target_profile.id
                )
                from app.repositories import workspace_state as workspace_repo

                await workspace_repo.set_active_profile_id(session, target_profile.id)
                await session.commit()
                return (
                    target_attachment_id,
                    target_profile.id,
                    conversation.id,
                )
        finally:
            await engine.dispose()

    attachment_id, target_profile_id, conversation_id = run_async(_seed())
    factory = get_session_factory()
    real_assert = chat_turns.assert_cv_reprocessable

    async def _switch_after_route_precheck(**kwargs: Any) -> None:
        await real_assert(**kwargs)
        async with factory() as session:
            profiles = await prof_repo.list_profiles(session)
            other_profile = next(row for row in profiles if row.id != target_profile_id)
            from app.repositories import workspace_state as workspace_repo

            await workspace_repo.set_active_profile_id(session, other_profile.id)
            await session.commit()

    monkeypatch.setattr(
        chat_turns, "assert_cv_reprocessable", _switch_after_route_precheck
    )
    model = FakeChatModel(responses=[ai_text("must not run")])

    async def _exercise() -> None:
        with pytest.raises(ChatTurnError) as exc_info:
            _ = [
                event
                async for event in chat_turns.stream_cv_reprocess(
                    attachment_id=attachment_id,
                    target_profile_id=target_profile_id,
                    conversation_id=conversation_id,
                    storage=storage,
                    model=model,
                    registry=ToolRegistry([]),
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
        assert exc_info.value.code == "PROFILE_NOT_READY"
        assert model.invoke_count == 0
        async with factory() as session:
            assert (
                int(
                    (
                        await session.execute(
                            select(func.count()).select_from(AgentRun)
                        )
                    ).scalar_one()
                )
                == 0
            )
            assert (
                int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ChatMessage)
                        )
                    ).scalar_one()
                )
                == 0
            )
            assert await prof_repo.get_draft_for_profile(
                session, target_profile_id
            ) is None

    run_async(_exercise())


def test_reprocess_approval_required_blocks_second(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    invoker = _CoveringDocumentInvoker()
    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _seed() -> tuple[str, str]:
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
                profile_id = await _seed_ready_profile_owner(session, att_id)
                await session.commit()
            return att_id, profile_id
        finally:
            await engine.dispose()

    att_id, profile_id = run_async(_seed())
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[]), ToolRegistry([])
    ) as client:
        _override_direct_reextract(
            client,
            storage=storage,
            invoker=invoker,
            normalizer=normalizer,
        )
        first = client.post(f"/api/profiles/{profile_id}/reextract", json={})
        assert first.status_code == 200
        assert _event_names(parse_profile_reextract_wire(first.text))[-1] == (
            "reextract_review_ready"
        )
        second = client.post(f"/api/profiles/{profile_id}/reextract", json={})
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "PROFILE_REVIEW_PENDING"


def test_legacy_attachment_reprocess_route_is_not_available(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, _files_dir = reprocess_env
    with client_with_fake_chat(
        db_path,
        FakeChatModel(responses=[]),
        ToolRegistry([]),
    ) as client:
        response = client.post(f"/api/cvs/{new_uuid()}/reprocess")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


def test_reprocess_same_active_save_refreshes_document(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    invoker = _CoveringDocumentInvoker()
    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _seed() -> tuple[str, str]:
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
                profile_id = await _seed_ready_profile_owner(session, att_id)
                await session.commit()
            return att_id, profile_id
        finally:
            await engine.dispose()

    att_id, profile_id = run_async(_seed())
    factory = get_session_factory()
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[]), ToolRegistry([])
    ) as client:
        _override_direct_reextract(
            client,
            storage=storage,
            invoker=invoker,
            normalizer=normalizer,
        )
        propose = client.post(f"/api/profiles/{profile_id}/reextract", json={})
        assert propose.status_code == 200
        events = parse_profile_reextract_wire(propose.text)
        assert _event_names(events)[-1] == "reextract_review_ready"
        operation_id = events[-1]["operation_id"]
        review = client.get(
            f"/api/profiles/{profile_id}/reextract-draft",
            params={"operation_id": operation_id},
        )
        assert review.status_code == 200, review.text
        save = client.post(
            f"/api/profiles/{profile_id}/reextract-draft/approve",
            json={
                "operation_id": operation_id,
                "revision": review.json()["revision"],
            },
        )
        assert save.status_code == 200
        assert save.json()["approved"] is True

    async def _assert() -> None:
        async with factory() as session:
            att = await att_repo.get_by_id(session, att_id)
            assert att is not None
            assert att.state == ATTACHMENT_STATE_ACTIVE
            profile = await prof_repo.get_active_profile(session)
            assert profile is not None
            assert profile.active_attachment_id == att_id
            assert await prof_repo.get_draft_for_profile(session, profile.id) is None
            doc = await cv_doc_repo.get_document(session, att_id)
            assert doc is not None
            assert doc.source_hash

    run_async(_assert())


def test_cv_manager_file_route_encodes_unicode_original_name(
    reprocess_env: tuple[Path, Path],
) -> None:
    db_path, files_dir = reprocess_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment_id = new_uuid()
                await att_repo.create_staged(
                    session,
                    file_hash="unicode-name",
                    original_name="CV \u0110\u1eb7ng.pdf",
                    size_bytes=32,
                    storage_path=_write_real_pdf(storage, attachment_id),
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id, page_count=1)
                await _seed_ready_profile_owner(session, attachment_id)
                await session.commit()
                return attachment_id
        finally:
            await engine.dispose()

    attachment_id = run_async(_seed())
    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text("noop")]), ToolRegistry([])
    ) as client:
        inline = client.get(f"/api/cvs/{attachment_id}/file")
        attachment = client.get(f"/api/cvs/{attachment_id}/file?disposition=attachment")

    expected_filename_star = "filename*=UTF-8''CV%20%C4%90%E1%BA%B7ng.pdf"
    for response, disposition in (
        (inline, "inline"),
        (attachment, "attachment"),
    ):
        assert response.status_code == 200
        header = response.headers["content-disposition"]
        assert header.startswith(f'{disposition}; filename="CV __ng.pdf"; ')
        assert expected_filename_star in header
        assert all(ord(char) < 128 for char in header)


def test_cv_manager_active_ready_policy_never_allows_activation() -> None:
    ready_owner = Profile(state="ready")

    assert allowed_actions(
        state=ATTACHMENT_STATE_ACTIVE,
        owner=ready_owner,
        is_active=False,
        file_available=True,
    ) == ["preview", "download"]


def test_inactive_archived_cv_never_projects_reextract() -> None:
    ready_owner = Profile(state="ready")

    assert allowed_actions(
        state=ATTACHMENT_STATE_ARCHIVED,
        owner=ready_owner,
        is_active=False,
        file_available=True,
    ) == ["preview", "download", "activate_profile"]
