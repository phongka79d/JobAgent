"""Tests for bounded chat context assembly and compact approved context."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.agent.prompt import (
    DOMAIN_REDIRECT_MESSAGE,
    evaluate_domain_policy,
)
from app.agent.state import AGENT_STATE_KEY_SET, validate_agent_state
from app.db.base import SINGLETON_PK
from app.db.models.attachments import Attachment
from app.db.models.memory import MemoryFact
from app.db.models.profile import CandidateProfile as CandidateProfileRow
from app.db.models.profile import JobPreferences as JobPreferencesRow
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.conversations import ConversationRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences
from app.services.chat_context import (
    DEFAULT_RECENT_CONTEXT_LIMIT,
    ChatContextAssembler,
    ChatContextError,
)
from app.services.profile_context import ProfileContextError, ProfileContextService


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "context.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _minimal_profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Backend engineer.",
        "current_title": "Engineer",
        "total_experience_years": None,
        "skills": [],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.7,
    }
    data.update(overrides)
    return data


def _prefs(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "target_roles": ["Backend"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["mid"],
    }
    data.update(overrides)
    return data


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
async def test_includes_validated_compact_profile_preferences_and_memory(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att_id = uuid4()
            session.add(
                Attachment(
                    id=att_id,
                    file_hash=uuid4().hex,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=10,
                    storage_path=f"active/{att_id}",
                    state="active",
                )
            )
            await session.flush()

            profiles = ProfileRepository(session)
            prefs = PreferencesRepository(session)
            await profiles.replace(
                CandidateProfile.model_validate(
                    _minimal_profile(
                        summary="Backend engineer",
                        skills=[
                            {
                                "skill": {
                                    "canonical_key": "python",
                                    "display_name": "Python",
                                    "aliases": [],
                                    "category": None,
                                    "status": "provisional",
                                    "confidence": 0.8,
                                    "evidence": ["Python listed"],
                                },
                                "proficiency": "advanced",
                                "years": None,
                                "source": "cv",
                                "excluded": False,
                                "evidence": ["Python listed"],
                            }
                        ],
                    )
                ),
                active_attachment_id=att_id,
            )
            await prefs.replace(
                JobPreferences.model_validate(_prefs(target_roles=["Backend"]))
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
            assert cc["profile"]["summary"] == "Backend engineer"
            assert cc["profile"]["current_title"] == "Engineer"
            assert cc["profile"]["skills"][0]["display_name"] == "Python"
            # Compact projection excludes raw CV / evidence dumps / paths.
            assert "cv_text" not in cc["profile"]
            assert "evidence" not in cc["profile"]["skills"][0]
            assert "storage_path" not in cc
            assert cc["preferences"]["target_roles"] == ["Backend"]
            assert "jd_body" not in cc["preferences"]
            assert cc["active_attachment_id"] == str(att_id)
            facts = cc["memory_facts"]
            assert len(facts) == 1
            assert facts[0]["key"] == "preferred_stack"
            assert facts[0]["value"]["stack"] == "FastAPI"
            assert "raw_document" not in facts[0]["value"]


@pytest.mark.asyncio
async def test_compact_context_service_privacy_exclusions(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            profiles = ProfileRepository(session)
            prefs = PreferencesRepository(session)
            await profiles.replace(
                CandidateProfile.model_validate(_minimal_profile())
            )
            await prefs.replace(JobPreferences.model_validate(_prefs()))

            service = ProfileContextService(session)
            compact = await service.load_compact_approved_context()
            assert compact.profile is not None
            assert compact.preferences is not None
            blob = compact.as_dict()
            assert blob is not None
            serialized = str(blob).lower()
            for forbidden in (
                "pdf_body",
                "cv_text",
                "storage_path",
                "provider_payload",
                "contact_address",
                "email@",
                "/files/",
            ):
                assert forbidden not in serialized
            # No raw evidence lists in compact skill rows when skills present.
            for skill in compact.profile.get("skills", []):
                assert "evidence" not in skill


@pytest.mark.asyncio
async def test_invalid_stored_profile_fails_closed_in_chat_context(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            session.add(
                CandidateProfileRow(
                    id=SINGLETON_PK,
                    profile_json={
                        "headline": "Backend engineer",
                        "cv_text": "SHOULD_NOT_CROSS",
                        "skills": ["Python"],
                    },
                )
            )
            await session.flush()
            assembler = ChatContextAssembler(session)
            with pytest.raises(ChatContextError, match="invalid stored profile"):
                await assembler.assemble(
                    run_id=uuid4(),
                    current_turn_content="update my profile preferences",
                )


@pytest.mark.asyncio
async def test_invalid_stored_preferences_fails_closed(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            session.add(
                JobPreferencesRow(
                    id=SINGLETON_PK,
                    preferences_json={
                        "roles": ["Backend"],
                        "acceptable_work_modes": ["anywhere"],
                    },
                )
            )
            await session.flush()
            service = ProfileContextService(session)
            with pytest.raises(ProfileContextError, match="invalid stored preferences"):
                await service.load_compact_approved_context()


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
