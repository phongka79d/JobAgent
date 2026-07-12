"""Graph-level profile approval, correction injection, and guarded commit."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.agent.approval import (
    enrich_resume_value,
    parse_resume_command,
    profile_display_summary,
    sanitize_profile_approval_fields,
)
from app.agent.graph import build_agent_graph, initial_graph_state
from app.agent.lifecycle import extract_interrupt_payload, result_is_graph_interrupt
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.attachment_storage import (
    FilesystemAttachmentStorage,
    iter_byte_chunks,
)
from app.services.profile_service import ProfileCommitService
from app.services.shopaikey_chat import DecisionResult
from app.tools.profile_commit import (
    ProfileCommitToolService,
    create_profile_commit_tool,
)
from app.tools.profile_draft import (
    ProfileDraftToolService,
    create_profile_draft_tools,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from tests.fakes.agent_tools import ScriptedDecision, decision_text, tool_call
from tests.tools.profile_tool_helpers import preferences, profile, temporary_db


class _FakeCv:
    def __init__(self, database: Any, attachment_id: UUID) -> None:
        self.database = database
        self.attachment_id = attachment_id

    async def propose_profile_from_cv(self, attachment_id: UUID) -> Any:
        async with self.database.session_scope() as session:
            proposed = profile("From CV draft")
            return await ProfileDraftRepository(session).create(
                ProfileDraftDocument(
                    profile=proposed,
                    approval_summary=build_approval_summary(proposed),
                ),
                source_attachment_id=self.attachment_id,
            )


async def _active_source(
    database: Any, storage: FilesystemAttachmentStorage
) -> UUID:
    attachment_id = uuid4()
    staged = await storage.stage(attachment_id, iter_byte_chunks(b"%PDF-1.4 a"))
    async with database.session_scope() as session:
        from app.repositories.attachments import (
            AttachmentRepository,
            StagedAttachmentInput,
        )

        await AttachmentRepository(session).add_staged(
            StagedAttachmentInput(
                id=attachment_id,
                file_hash=attachment_id.hex,
                original_name="cv.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                storage_path=staged.storage_path,
                page_count=1,
            )
        )
        await AttachmentRepository(session).mark_active(
            attachment_id,
            storage_path=await storage.promote(staged.storage_path),
        )
    return attachment_id


def test_parse_resume_and_enrich_bind_idempotency_key() -> None:
    assert parse_resume_command(True).action == "approve"
    assert parse_resume_command("yes").action == "approve"
    correct = parse_resume_command(
        {"action": "correct", "text": "  Prefer remote  ", "idempotency_key": "r1"}
    )
    assert correct.action == "correct"
    assert correct.correction_text == "Prefer remote"
    enriched = enrich_resume_value(
        {"action": "correct", "text": "fix title"},
        resume_idempotency_key="resume-9",
    )
    assert enriched["idempotency_key"] == "resume-9"
    assert enriched["action"] == "correct"


def test_sanitize_keeps_display_lists_and_internal_draft() -> None:
    payload = sanitize_profile_approval_fields(
        {
            "kind": "approval_required",
            "approval_kind": "profile_draft",
            "draft_id": "11111111-1111-1111-1111-111111111111",
            "summary": "Review proposed Engineer",
            "skill_names": ["Python", "SQL"],
            "experience_count": 2,
            "has_preference_changes": False,
        }
    )
    assert payload["draft_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["skill_names"] == ["Python", "SQL"]
    display = profile_display_summary(payload)
    assert "draft_id" not in display
    assert display["approval_kind"] == "profile_draft"
    assert display["skill_names"] == ["Python", "SQL"]


@pytest.mark.asyncio
async def test_approve_resume_runs_one_guarded_commit(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        attachment_id = await _active_source(database, storage)
        draft_tools = create_profile_draft_tools(
            ProfileDraftToolService(database, _FakeCv(database, attachment_id))
        )
        commit_tool = create_profile_commit_tool(
            ProfileCommitToolService(ProfileCommitService(database, storage))
        )
        tools = [*draft_tools, commit_tool]
        decision = ScriptedDecision(
            [
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "propose_profile_from_cv",
                            arguments={"attachment_id": str(attachment_id)},
                            tool_call_id="c_propose",
                        ),
                    ),
                    response_model="fake",
                ),
                decision_text("Profile saved"),
            ]
        )
        checkpointer = MemorySaver()
        graph = build_agent_graph(
            tools=tools,
            decision=decision,
            checkpointer=checkpointer,
        )
        config = {"configurable": {"thread_id": "thread-approve-1"}}
        first = await graph.ainvoke(
            initial_graph_state(
                conversation_id="conv-1",
                run_id="run-approve-1",
                user_text="Create profile from CV",
                attachment_ids=[str(attachment_id)],
            ),
            config=config,
        )
        assert result_is_graph_interrupt(first)
        pending = extract_interrupt_payload(first)
        assert pending is not None
        draft_id = pending.get("draft_id")
        assert isinstance(draft_id, str)

        second = await graph.ainvoke(
            Command(
                resume=enrich_resume_value(
                    True, resume_idempotency_key="approve-key-1"
                )
            ),
            config=config,
        )
        assert second.get("run_outcome") == "completed"
        assert second.get("final_assistant_text") == "Profile saved"
        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is not None
            assert await ProfileDraftRepository(session).get(UUID(draft_id)) is None


@pytest.mark.asyncio
async def test_correction_injects_text_updates_same_draft_and_reinterrupts(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        attachment_id = await _active_source(database, storage)
        draft_tools = create_profile_draft_tools(
            ProfileDraftToolService(database, _FakeCv(database, attachment_id))
        )
        commit_tool = create_profile_commit_tool(
            ProfileCommitToolService(ProfileCommitService(database, storage))
        )
        tools = [*draft_tools, commit_tool]

        # First decision proposes; after correction, update then final text unused.
        decision = ScriptedDecision(
            [
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "propose_profile_from_cv",
                            arguments={"attachment_id": str(attachment_id)},
                            tool_call_id="c_propose",
                        ),
                    ),
                    response_model="fake",
                ),
            ]
        )
        checkpointer = MemorySaver()
        graph = build_agent_graph(
            tools=tools,
            decision=decision,
            checkpointer=checkpointer,
        )
        config = {"configurable": {"thread_id": "thread-correct-1"}}
        first = await graph.ainvoke(
            initial_graph_state(
                conversation_id="conv-1",
                run_id="run-correct-1",
                user_text="Create profile from CV",
                attachment_ids=[str(attachment_id)],
            ),
            config=config,
        )
        pending = extract_interrupt_payload(first)
        assert pending is not None
        draft_id = str(pending["draft_id"])

        # After correction resume, scripted decision updates same draft.
        corrected_profile = profile("Corrected senior engineer")
        decision.results.append(
            DecisionResult(
                content="",
                tool_calls=(
                    tool_call(
                        "propose_profile_update",
                        arguments={
                            "draft_id": draft_id,
                            "profile": corrected_profile.model_dump(mode="json"),
                            "preferences": preferences("Staff").model_dump(
                                mode="json"
                            ),
                        },
                        tool_call_id="c_update",
                    ),
                ),
                response_model="fake",
            )
        )

        second = await graph.ainvoke(
            Command(
                resume=enrich_resume_value(
                    {"action": "correct", "text": "Make me a senior engineer"},
                    resume_idempotency_key="correct-key-1",
                )
            ),
            config=config,
        )
        assert result_is_graph_interrupt(second)
        second_pending = extract_interrupt_payload(second)
        assert second_pending is not None
        assert second_pending.get("draft_id") == draft_id
        assert "senior" in str(second_pending.get("summary", "")).lower() or (
            second_pending.get("current_title") is not None
        )

        # Correction text must be present in turn messages for the model path.
        messages = second.get("messages_for_this_turn") or []
        human_texts = [
            getattr(m, "content", "")
            for m in messages
            if type(m).__name__ == "HumanMessage"
            or (
                isinstance(m, dict)
                and str(m.get("role", "")).lower() == "user"
            )
        ]
        assert any("senior engineer" in str(t).lower() for t in human_texts)

        async with database.session_scope() as session:
            # Approved singleton still untouched before approve.
            assert await ProfileRepository(session).get() is None
            draft = await ProfileDraftRepository(session).get(UUID(draft_id))
            assert draft is not None
            assert draft.document.profile.summary == "Corrected senior engineer"


@pytest.mark.asyncio
async def test_direct_forged_commit_tool_call_via_graph_changes_nothing(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        attachment_id = await _active_source(database, storage)
        document = ProfileDraftDocument(
            profile=profile("Pending only"),
            approval_summary=build_approval_summary(profile("Pending only")),
        )
        async with database.session_scope() as session:
            draft = await ProfileDraftRepository(session).create(
                document, source_attachment_id=attachment_id
            )
            draft_id = draft.id

        commit_tool = create_profile_commit_tool(
            ProfileCommitToolService(ProfileCommitService(database, storage))
        )
        decision = ScriptedDecision(
            [
                DecisionResult(
                    content="",
                    tool_calls=(
                        tool_call(
                            "commit_profile_draft",
                            arguments={
                                "draft_id": str(draft_id),
                                "idempotency_key": "forged-1",
                            },
                            tool_call_id="c_forged",
                        ),
                    ),
                    response_model="fake",
                ),
            ]
        )
        graph = build_agent_graph(tools=[commit_tool], decision=decision)
        out = await graph.ainvoke(
            initial_graph_state(
                conversation_id="c",
                run_id="r-forged",
                user_text="Please save my candidate profile draft",
            )
        )
        # Unauthorized tool result is a structured failure (not a silent commit).
        assert out.get("run_outcome") == "failed" or out.get("error") is not None
        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is None
            assert await ProfileDraftRepository(session).get(draft_id) is not None
