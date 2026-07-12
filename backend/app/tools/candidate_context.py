"""Read-only compact Candidate context tool."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict

from app.db.session import DatabaseSessionManager
from app.services.profile_context import ProfileContextError, ProfileContextService


class CandidateContextInput(BaseModel):
    """Strict empty input for the read-only context tool."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["approved"] = "approved"


class CandidateContextToolService:
    """Load the approved compact projection through one database boundary."""

    def __init__(self, database: DatabaseSessionManager) -> None:
        self._database = database

    async def load(self) -> dict[str, Any]:
        try:
            async with self._database.session_scope() as session:
                context = await ProfileContextService(session).load_optional_context_dict()
        except ProfileContextError:
            return {"status": "error", "code": "CANDIDATE_CONTEXT_INVALID"}
        if context is None or context.get("profile") is None:
            return {"status": "error", "code": "CANDIDATE_CONTEXT_UNAVAILABLE"}
        return {"status": "ok", "context": context}


def create_candidate_context_tool(
    service: CandidateContextToolService,
) -> StructuredTool:
    """Create the strict read-only LangChain tool wrapper."""

    async def _load(scope: Literal["approved"] = "approved") -> dict[str, Any]:
        del scope
        return await service.load()

    return StructuredTool.from_function(
        coroutine=_load,
        name="get_candidate_context",
        description="Read the bounded approved Candidate profile and preferences.",
        args_schema=CandidateContextInput,
    )


__all__ = [
    "CandidateContextInput",
    "CandidateContextToolService",
    "create_candidate_context_tool",
]
