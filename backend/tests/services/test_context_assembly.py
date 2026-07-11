"""Tests for bounded chat context assembly and optional context."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from app.agent.prompt import (
    DOMAIN_REDIRECT_MESSAGE,
    evaluate_domain_policy,
)
from app.agent.state import AGENT_STATE_KEY_SET, validate_agent_state
from app.db.base import SINGLETON_PK
from app.db.models.memory import MemoryFact
from app.db.models.profile import CandidateProfile, JobPreferences
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.conversations import ConversationRepository
from app.services.chat_context import (
    DEFAULT_RECENT_CONTEXT_LIMIT,
    ChatContextAssembler,
    ChatContextError,
)


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "context.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_assemble_current_turn_and_bounded_recent(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            for i in range(5):
                await repo.append_message(role="user", content=f"hist-{i}")
            current = await repo.append_message(
                role="user",
                content="Please review my CV skills",
            )
            run_id = uuid4()
            assembler = ChatContextAssembler(session, conversation_repo=repo)
            state = await assembler.assemble(
                run_id=run_id,
                current_turn_content=current.content,
                current_message_id=current.id,
                recent_limit=3,
                attachment_ids=["att-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
            )

            validated = validate_agent_state(state)
            assert frozenset(validated.keys()) == AGENT_STATE_KEY_SET
            assert validated["conversation_id"] == str(SINGLETON_PK)
            assert validated["run_id"] == str(run_id)
            assert len(validated["messages_for_this_turn"]) == 1
            assert (
                validated["messages_for_this_turn"][0]["content"]
                == "Please review my CV skills"
            )
            # Recent window is bounded and excludes the current message.
            assert len(validated["recent_context"]) <= 3
            recent_ids = {
                m.get("message_id") for m in validated["recent_context"]
            }
            assert str(current.id) not in recent_ids
            assert validated["attachment_ids"] == [
                "att-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            ]
            # Large content is ID-only in candidate_context.
            cc = validated["candidate_context"]
            assert cc is not None
            assert cc.get("attachment_ids") == [
                "att-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            ]
            assert "pdf_body" not in (cc or {})
            assert "jd_body" not in validated
            assert "cv_text" not in validated


@pytest.mark.asyncio
async def test_missing_optional_profile_preferences_memory(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            assembler = ChatContextAssembler(session)
            state = await assembler.assemble(
                run_id=uuid4(),
                current_turn_content="match me to jobs",
                recent_limit=DEFAULT_RECENT_CONTEXT_LIMIT,
            )
            assert state["candidate_context"] is None
            assert state["messages_for_this_turn"][0]["content"] == "match me to jobs"
            assert state["recent_context"] == []


@pytest.mark.asyncio
async def test_includes_profile_preferences_and_memory_when_present(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            session.add(
                CandidateProfile(
                    id=SINGLETON_PK,
                    profile_json={
                        "headline": "Backend engineer",
                        "cv_text": "SHOULD_BE_STRIPPED " * 50,
                        "skills": ["Python"],
                    },
                )
            )
            session.add(
                JobPreferences(
                    id=SINGLETON_PK,
                    preferences_json={
                        "roles": ["Backend"],
                        "jd_body": "SHOULD_BE_STRIPPED",
                    },
                )
            )
            session.add(
                MemoryFact(
                    key="preferred_stack",
                    value_json={"stack": "FastAPI", "raw_document": "NOPE"},
                    source="user",
                )
            )
            await session.flush()

            assembler = ChatContextAssembler(session)
            state = await assembler.assemble(
                run_id=uuid4(),
                current_turn_content="update my profile preferences",
            )
            cc = state["candidate_context"]
            assert cc is not None
            assert cc["profile"]["headline"] == "Backend engineer"
            assert "cv_text" not in cc["profile"]
            assert cc["preferences"]["roles"] == ["Backend"]
            assert "jd_body" not in cc["preferences"]
            facts = cc["memory_facts"]
            assert len(facts) == 1
            assert facts[0]["key"] == "preferred_stack"
            assert facts[0]["value"]["stack"] == "FastAPI"
            assert "raw_document" not in facts[0]["value"]


@pytest.mark.asyncio
async def test_recent_window_not_full_history(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            for i in range(15):
                await repo.append_message(role="user", content=f"msg-{i}")
            assembler = ChatContextAssembler(session, conversation_repo=repo)
            state = await assembler.assemble(
                run_id=uuid4(),
                current_turn_content="job matching please",
                recent_limit=5,
                exclude_current_from_recent=False,
            )
            assert len(state["recent_context"]) == 5
            contents = [m["content"] for m in state["recent_context"]]
            assert contents == [f"msg-{i}" for i in range(10, 15)]
            assert "msg-0" not in contents


@pytest.mark.asyncio
async def test_id_only_large_content_references(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att_id = "att-99999999-9999-9999-9999-999999999999"
            assembler = ChatContextAssembler(session)
            state = await assembler.assemble(
                run_id=uuid4(),
                current_turn_content="process my uploaded CV",
                attachment_ids=[att_id],
            )
            assert state["attachment_ids"] == [att_id]
            assert "pdf_body" not in state
            assert state["candidate_context"] is not None
            assert state["candidate_context"]["attachment_ids"] == [att_id]


@pytest.mark.asyncio
async def test_invalid_recent_limit(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            assembler = ChatContextAssembler(session)
            with pytest.raises(ChatContextError, match="invalid recent_limit"):
                await assembler.assemble(
                    run_id=uuid4(),
                    current_turn_content="hello jobs",
                    recent_limit=0,
                )
            with pytest.raises(ChatContextError, match="invalid recent_limit"):
                await assembler.assemble(
                    run_id=uuid4(),
                    current_turn_content="hello jobs",
                    recent_limit=101,
                )


@pytest.mark.asyncio
async def test_unrelated_turn_policy_zero_tools_no_provider_loop(
    tmp_path: Path,
) -> None:
    """Context assembly still produces state; domain policy short-circuits tools."""
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            assembler = ChatContextAssembler(session)
            user_text = "Who won the world cup in 2018?"
            state = await assembler.assemble(
                run_id=uuid4(),
                current_turn_content=user_text,
            )
            decision = evaluate_domain_policy(user_text)
            assert decision.redirect is True
            assert decision.response_text == DOMAIN_REDIRECT_MESSAGE
            assert decision.allow_tools is False
            assert decision.tool_calls == ()
            assert decision.invoke_provider_retry_loop is False
            # State remains bounded and valid even for unrelated turns.
            assert validate_agent_state(state)["tool_iteration_count"] == 0
