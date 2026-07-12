"""Candidate compact-context tool authorization and privacy."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.repositories.preferences import PreferencesRepository
from app.repositories.profiles import ProfileRepository
from app.tools.candidate_context import (
    CandidateContextToolService,
    create_candidate_context_tool,
)
from pydantic import ValidationError
from tests.tools.profile_tool_helpers import (
    active_attachment,
    preferences,
    profile,
    temporary_db,
)


@pytest.mark.asyncio
async def test_context_tool_is_read_only_and_returns_compact_approved_state(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(
                profile(), active_attachment_id=attachment_id
            )
            await PreferencesRepository(session).replace(preferences())

        tool = create_candidate_context_tool(CandidateContextToolService(database))
        result = await tool.ainvoke({})

        assert result["status"] == "ok"
        assert result["context"]["profile"]["summary"] == "Backend engineer"
        serialized = str(result).lower()
        for forbidden in ("raw_text", "storage_path", "email", "phone"):
            assert forbidden not in serialized
        async with database.session_scope() as session:
            assert (await ProfileRepository(session).get()).profile == profile()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_context_tool_fails_closed_without_approved_profile(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        tool = create_candidate_context_tool(CandidateContextToolService(database))
        assert await tool.ainvoke({}) == {
            "status": "error",
            "code": "CANDIDATE_CONTEXT_UNAVAILABLE",
        }


@pytest.mark.asyncio
async def test_context_tool_rejects_extra_model_arguments(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        tool = create_candidate_context_tool(CandidateContextToolService(database))
        with pytest.raises(ValidationError):
            await tool.ainvoke({"raw_cv": "secret"})
