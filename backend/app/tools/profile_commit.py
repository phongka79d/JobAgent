"""Guarded ``commit_profile_draft`` tool — application authorization only."""

from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import UUID

from langchain_core.tools import StructuredTool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.approval import authorization_matches
from app.services.profile_service import ProfileCommitError, ProfileCommitService


class CommitProfileDraftInput(BaseModel):
    """Strict LLM-visible args (InjectedState is not part of this schema)."""

    model_config = ConfigDict(extra="forbid")

    draft_id: UUID
    idempotency_key: str = Field(..., min_length=1, max_length=128)


def _error(code: str) -> str:
    return f'ERROR:{{"code":"{code}","ok":false}}'


class ProfileCommitToolService:
    """Commit a pending draft only when graph approval authorization matches."""

    def __init__(self, commits: ProfileCommitService) -> None:
        self._commits = commits
        # In-process same-run/draft replay only. Identity is (run, draft, key):
        # a bare resume key must not suppress a later authorized run/draft.
        # Durable same-key replay is owned by ChatService resume idempotency;
        # draft deletion also fails a second commit closed.
        self._consumed_identities: set[tuple[str, str, str]] = set()

    async def commit_draft(
        self,
        *,
        draft_id: UUID,
        idempotency_key: str,
        authorization: dict[str, Any] | None,
        run_id: str | None = None,
    ) -> str:
        key = idempotency_key.strip()
        if not key:
            return _error("COMMIT_UNAUTHORIZED")
        if not authorization_matches(
            authorization,
            draft_id=draft_id,
            idempotency_key=key,
            run_id=run_id,
        ):
            return _error("COMMIT_UNAUTHORIZED")
        identity = self._replay_identity(
            draft_id=draft_id,
            key=key,
            authorization=authorization,
            run_id=run_id,
        )
        if identity in self._consumed_identities:
            return json.dumps(
                {"ok": True, "status": "already_committed", "idempotent": True},
                separators=(",", ":"),
                sort_keys=True,
            )
        try:
            result = await self._commits.commit_draft(draft_id)
        except ProfileCommitError as exc:
            return _error(exc.code)
        self._consumed_identities.add(identity)
        return json.dumps(
            {
                "ok": True,
                "status": "committed",
                "cleanup_pending": result.cleanup_pending,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _replay_identity(
        *,
        draft_id: UUID,
        key: str,
        authorization: dict[str, Any] | None,
        run_id: str | None,
    ) -> tuple[str, str, str]:
        """Scope in-process idempotency to authorized run/draft/key."""
        run_scope = (run_id or "").strip()
        if not run_scope and isinstance(authorization, dict):
            run_scope = str(authorization.get("run_id") or "").strip()
        return (run_scope, str(draft_id), key)


def create_profile_commit_tool(service: ProfileCommitToolService) -> StructuredTool:
    """Register the guarded write tool; auth comes from InjectedState only.

    ``args_schema`` is intentionally omitted so LangGraph can inject state
    without failing ``extra=forbid`` validation. Public args are re-validated
    with ``CommitProfileDraftInput`` inside the coroutine.
    """

    async def _guarded_commit(
        draft_id: UUID,
        idempotency_key: str,
        state: Annotated[dict[str, Any], InjectedState],
    ) -> str:
        try:
            parsed = CommitProfileDraftInput(
                draft_id=draft_id,
                idempotency_key=idempotency_key,
            )
        except ValidationError:
            return _error("COMMIT_INVALID_INPUT")
        auth: dict[str, Any] | None = None
        run_id: str | None = None
        if isinstance(state, dict):
            raw_auth = state.get("approval_authorization")
            if isinstance(raw_auth, dict):
                auth = raw_auth
            raw_run = state.get("run_id")
            if isinstance(raw_run, str) and raw_run.strip():
                run_id = raw_run.strip()
        return await service.commit_draft(
            draft_id=parsed.draft_id,
            idempotency_key=parsed.idempotency_key,
            authorization=auth,
            run_id=run_id,
        )

    return StructuredTool.from_function(
        coroutine=_guarded_commit,
        name="commit_profile_draft",
        description=(
            "Commit a pending profile draft after human approval. "
            "Requires application-owned approval authorization."
        ),
    )


__all__ = [
    "CommitProfileDraftInput",
    "ProfileCommitToolService",
    "create_profile_commit_tool",
]
