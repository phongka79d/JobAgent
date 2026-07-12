"""End-to-end fake-backed profile workflow proof (upload → approve → sync)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from app.db.enums import AgentRunState, AttachmentState
from app.db.models.conversation import AgentRun, ToolExecution
from app.db.models.outbox import GraphSyncOutbox
from app.db.session import create_session_manager
from app.graph.candidate_sync import (
    CANDIDATE_SYNC_OPERATION,
    process_candidate_sync_outbox,
    rebuild_candidate_projection,
)
from app.repositories.attachments import AttachmentRepository
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.sse import SSEEventOrderValidator, parse_sse_event
from app.services.profile_service import ProfileCommitService
from app.services.shopaikey_chat import DecisionResult
from app.tools.profile_commit import ProfileCommitToolService
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.fakes.agent_tools import ScriptedDecision, decision_text, tool_call
from tests.fixtures.cv_pdfs import build_synthetic_text_pdf
from tests.integration.profile_workflow.support import (
    CV_BODY,
    assert_no_contact,
    build_app,
    build_tools,
    extraction_payload,
    migrated_db,
    parse_sse_payloads,
    upload_cv,
)
from tests.integration.test_candidate_sync import StatefulCandidateGraph
from tests.tools.profile_tool_helpers import preferences, profile


@pytest.mark.asyncio
async def test_full_profile_workflow_upload_correct_approve_sync_restart(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.DEBUG)
    pdf = build_synthetic_text_pdf(CV_BODY)

    async with migrated_db(tmp_path) as (db_path, manager, settings, storage):
        tools, factory = build_tools(
            manager,
            storage,
            settings,
            extraction_responses=[extraction_payload()],
        )
        decision = ScriptedDecision(
            [
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "propose_profile_from_cv",
                            arguments={"attachment_id": "PLACEHOLDER"},
                            tool_call_id="c_propose",
                        ),
                    ),
                    response_model="fake",
                ),
            ]
        )
        application = build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            storage=storage,
            decision=decision,
            tools=tools,
        )

        with TestClient(application) as client:
            uploaded = upload_cv(client, pdf, name="../evil/cv.pdf")
            assert uploaded["status"] == 201
            attachment = uploaded["body"]
            assert set(attachment) == {
                "id",
                "original_name",
                "mime_type",
                "size_bytes",
                "page_count",
                "state",
            }
            assert attachment["original_name"] == "cv.pdf"
            assert attachment["state"] == "staged"
            attachment_id = attachment["id"]
            assert_no_contact(uploaded["text"], attachment)

            decision.results = [
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "propose_profile_from_cv",
                            arguments={"attachment_id": attachment_id},
                            tool_call_id="c_propose",
                        ),
                    ),
                    response_model="fake",
                ),
            ]

            turn = client.post(
                "/api/chat/turns",
                json={
                    "text": "Create a candidate profile draft from the attached CV.",
                    "idempotency_key": "pw-turn-1",
                    "attachment_ids": [attachment_id],
                },
            )
            assert turn.status_code == 200
            payloads = parse_sse_payloads(turn.text)
            typed = [parse_sse_event(p) for p in payloads]
            SSEEventOrderValidator().validate_sequence(typed)
            kinds = [p["event"] for p in payloads]
            assert kinds[0] == "run_started"
            assert "approval_required" in kinds
            assert "run_completed" not in kinds
            approval = next(p for p in payloads if p["event"] == "approval_required")
            assert approval["payload"]["approval_kind"] == "profile_draft"
            assert approval["payload"].get("summary")
            assert_no_contact(turn.text, payloads)
            run_id = UUID(payloads[0]["run_id"])

            assert len(factory.model.structured_calls) == 1
            assert_no_contact(repr(factory.model.structured_calls[0]))

            async with manager.session_scope() as session:
                assert await ProfileRepository(session).get() is None
                pending = await ProfileDraftRepository(session).get_pending()
                assert pending is not None
                draft_id = pending.id
                assert_no_contact(pending.document.to_storage_dict())
                assert pending.source_attachment_id == UUID(attachment_id)

            corrected = profile("Corrected integration summary").model_copy(
                update={
                    "skills": pending.document.profile.skills,
                    "experiences": pending.document.profile.experiences,
                }
            )
            prefs = preferences("Platform Lead")
            decision.results.append(
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "propose_profile_update",
                            arguments={
                                "draft_id": str(draft_id),
                                "profile": corrected.model_dump(mode="json"),
                                "preferences": prefs.model_dump(mode="json"),
                            },
                            tool_call_id="c_update",
                        ),
                    ),
                    response_model="fake",
                )
            )

            correct = client.post(
                f"/api/chat/runs/{run_id}/resume",
                json={
                    "action": "correct",
                    "correction_text": "Update summary to Corrected integration summary",
                    "idempotency_key": "pw-correct-1",
                },
            )
            assert correct.status_code == 200
            correct_payloads = parse_sse_payloads(correct.text)
            assert any(p["event"] == "approval_required" for p in correct_payloads)
            assert_no_contact(correct.text, correct_payloads)

            async with manager.session_scope() as session:
                assert await ProfileRepository(session).get() is None
                same = await ProfileDraftRepository(session).get(draft_id)
                assert same is not None
                assert same.document.profile.summary == "Corrected integration summary"
                assert same.document.replaces_preferences() is True

            commit_svc = ProfileCommitToolService(
                ProfileCommitService(manager, storage)
            )
            unauthorized = await commit_svc.commit_draft(
                draft_id=draft_id,
                idempotency_key="forged-direct",
                authorization=None,
            )
            assert "COMMIT_UNAUTHORIZED" in unauthorized
            async with manager.session_scope() as session:
                assert await ProfileRepository(session).get() is None
                assert await ProfileDraftRepository(session).get(draft_id) is not None
                tools_before = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ToolExecution)
                        )
                    ).scalar_one()
                )
                outbox_before = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(GraphSyncOutbox)
                        )
                    ).scalar_one()
                )

            decision.results.append(decision_text("Profile saved after approval"))
            approve = client.post(
                f"/api/chat/runs/{run_id}/resume",
                json={"action": "approve", "idempotency_key": "pw-approve-1"},
            )
            assert approve.status_code == 200
            approve_payloads = parse_sse_payloads(approve.text)
            assert any(p["event"] == "run_completed" for p in approve_payloads)
            text = "".join(
                p["payload"]["delta"]
                for p in approve_payloads
                if p["event"] == "text_delta"
            )
            assert "Profile saved" in text
            assert_no_contact(approve.text, approve_payloads)

            async with manager.session_scope() as session:
                approved = await ProfileRepository(session).get()
                assert approved is not None
                assert approved.profile.summary == "Corrected integration summary"
                assert approved.active_attachment_id == UUID(attachment_id)
                prefs_row = await PreferencesRepository(session).get()
                assert prefs_row is not None
                assert prefs_row.target_roles == ["Platform Lead"]
                assert await ProfileDraftRepository(session).get_pending() is None
                source = await AttachmentRepository(session).get_by_id(
                    UUID(attachment_id)
                )
                assert source is not None
                assert source.state == AttachmentState.ACTIVE.value
                outbox = await GraphOutboxRepository(session).get_by_identity(
                    CANDIDATE_SYNC_OPERATION, "1"
                )
                assert outbox is not None
                assert outbox.payload == {"candidate_id": "1"}
                tools_after = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ToolExecution)
                        )
                    ).scalar_one()
                )
                outbox_after = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(GraphSyncOutbox)
                        )
                    ).scalar_one()
                )
                assert tools_after >= tools_before
                assert outbox_after >= outbox_before

            profile_resp = client.get("/api/profile")
            assert profile_resp.status_code == 200
            profile_body = profile_resp.json()
            assert profile_body["state"] == "active"
            assert profile_body["profile"]["summary"] == "Corrected integration summary"
            assert profile_body["preferences"]["target_roles"] == ["Platform Lead"]
            assert profile_body["active_attachment"]["id"] == attachment_id
            assert_no_contact(profile_resp.text, profile_body)

            cv_resp = client.get("/api/profile/cv")
            assert cv_resp.status_code == 200
            assert cv_resp.content[:5] == b"%PDF-"
            hist = client.get("/api/chat/history")
            assert hist.status_code == 200
            assert_no_contact(hist.text, hist.json())

            graph = StatefulCandidateGraph()
            assert await process_candidate_sync_outbox(manager, graph) == 1
            assert graph.candidates == {"1"}
            assert ("1", "python") in graph.edges
            assert ("1", "zig") in graph.edges
            assert ("1", "obsolete_skill") not in graph.edges
            assert await process_candidate_sync_outbox(manager, graph) == 0
            assert await rebuild_candidate_projection(manager, graph) == 1
            assert graph.candidates == {"1"}
            assert graph.edges == {("1", "python"), ("1", "zig")}
            assert_no_contact(graph.skills)

            async with manager.session_scope() as session:
                tools_pre_dup = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ToolExecution)
                        )
                    ).scalar_one()
                )
                outbox_pre_dup = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(GraphSyncOutbox)
                        )
                    ).scalar_one()
                )
            dup = client.post(
                f"/api/chat/runs/{run_id}/resume",
                json={"action": "approve", "idempotency_key": "pw-approve-1"},
            )
            assert dup.status_code == 200
            async with manager.session_scope() as session:
                tools_post_dup = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ToolExecution)
                        )
                    ).scalar_one()
                )
                outbox_post_dup = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(GraphSyncOutbox)
                        )
                    ).scalar_one()
                )
                assert tools_post_dup == tools_pre_dup
                assert outbox_post_dup == outbox_pre_dup
                run = await session.get(AgentRun, run_id)
                assert run is not None
                assert run.state == AgentRunState.COMPLETED.value

            assert_no_contact(caplog.text)

        restarted = create_session_manager(db_path)
        try:
            async with restarted.session_scope() as session:
                approved = await ProfileRepository(session).get()
                assert approved is not None
                assert approved.profile.summary == "Corrected integration summary"
                prefs_row = await PreferencesRepository(session).get()
                assert prefs_row is not None
                assert prefs_row.target_roles == ["Platform Lead"]
                att = await AttachmentRepository(session).get_by_id(
                    UUID(attachment_id)
                )
                assert att is not None
                assert att.state == AttachmentState.ACTIVE.value
            tools2, _ = build_tools(
                restarted, storage, settings, extraction_responses=[]
            )
            app2 = build_app(
                manager=restarted,
                settings=settings,
                db_path=db_path,
                storage=storage,
                decision=ScriptedDecision([decision_text("noop")]),
                tools=tools2,
            )
            with TestClient(app2) as client2:
                again = client2.get("/api/profile")
                assert again.status_code == 200
                body = again.json()
                assert body["profile"]["summary"] == "Corrected integration summary"
                assert body["preferences"]["target_roles"] == ["Platform Lead"]
                assert_no_contact(again.text, body)
        finally:
            await restarted.dispose()
