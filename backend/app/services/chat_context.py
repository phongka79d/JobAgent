"""Bounded chat context assembly for Agent runs.

Reuses Plan 2/4 validated profile/preferences via ``ProfileContextService``,
MemoryFact rows, and ConversationRepository message bounds. Does not create
alternate memory storage. Optional profile/preferences/memory are absent when
rows do not exist.

Large PDF/JD bodies stay out of Agent state: only attachment IDs and structured
compact slices are assembled into ``AgentState``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import (
    AgentState,
    AgentStateError,
    initial_agent_state,
    validate_agent_state,
)
from app.db.models.memory import MemoryFact
from app.repositories.conversations import ConversationRepository
from app.services.profile_context import ProfileContextError, ProfileContextService

# Default and hard ceilings for the recent window (repository max is 100).
DEFAULT_RECENT_CONTEXT_LIMIT: Final[int] = 20
MAX_RECENT_CONTEXT_LIMIT: Final[int] = 100
MAX_MEMORY_FACTS: Final[int] = 50
MAX_ATTACHMENT_IDS: Final[int] = 32

# Keys stripped from memory value_json so raw document bodies never enter
# candidate_context even if later writers store them.
_STRIP_BODY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "pdf_body",
        "pdf_bytes",
        "pdf_text",
        "jd_body",
        "jd_text",
        "job_description_body",
        "job_description_text",
        "cv_body",
        "cv_text",
        "resume_body",
        "resume_text",
        "raw_document",
        "raw_content",
        "raw_text",
        "full_text",
        "document_body",
        "document_text",
        "document_bytes",
        "file_bytes",
        "content_bytes",
    }
)


class ChatContextError(ValueError):
    """Context assembly failed without disclosing payload values."""


@dataclass(frozen=True, slots=True)
class ContextMessage:
    """Bounded message view for Agent state (no large document bodies)."""

    role: str
    content: str
    message_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.message_id is not None:
            out["message_id"] = self.message_id
        return out


def _normalize_attachment_ids(attachment_ids: Sequence[str] | None) -> list[str]:
    if not attachment_ids:
        return []
    if len(attachment_ids) > MAX_ATTACHMENT_IDS:
        raise ChatContextError("too many attachment_ids")
    out: list[str] = []
    for item in attachment_ids:
        if not isinstance(item, str) or not item.strip():
            raise ChatContextError("invalid attachment_id")
        value = item.strip()
        if len(value) > 128 or any(ch in value for ch in "\n\r"):
            raise ChatContextError("invalid attachment_id")
        # IDs only — reject whitespace-bearing strings (document dumps).
        if any(ch.isspace() for ch in value):
            raise ChatContextError("invalid attachment_id")
        out.append(value)
    return out


def _sanitize_structured_mapping(
    data: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a shallow-cleaned dict without forbidden body keys."""
    if data is None:
        return None
    if not isinstance(data, Mapping):
        return None
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        normalized = key.strip().lower().replace("-", "_")
        if normalized in _STRIP_BODY_KEYS:
            continue
        if any(token in normalized for token in ("pdf_body", "jd_body", "cv_body", "raw_document", "document_body")):
            continue
        if isinstance(value, Mapping):
            nested = _sanitize_structured_mapping(value)
            cleaned[key] = nested if nested is not None else {}
        elif isinstance(value, str) and len(value) > 8_192:
            # Drop oversized strings that may be accidental document dumps.
            continue
        elif isinstance(value, (bytes, bytearray)):
            continue
        else:
            cleaned[key] = value
    return cleaned


def _message_to_context(row: Any) -> ContextMessage:
    return ContextMessage(
        role=str(row.role),
        content=str(row.content),
        message_id=str(row.id) if getattr(row, "id", None) is not None else None,
    )


class ChatContextAssembler:
    """Assemble bounded AgentState for one turn.

    Caller owns the ``AsyncSession`` transaction. Uses
    ``ConversationRepository.list_recent_for_context`` for the recent window,
    ``ProfileContextService`` for validated compact approved profile/preferences,
    and optional memory rows when present.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        conversation_repo: ConversationRepository | None = None,
        profile_context: ProfileContextService | None = None,
    ) -> None:
        self._session = session
        self._conversations = conversation_repo or ConversationRepository(session)
        self._profile_context = profile_context or ProfileContextService(session)

    async def load_optional_candidate_context(
        self,
        *,
        attachment_ids: Sequence[str] | None = None,
        memory_limit: int = MAX_MEMORY_FACTS,
    ) -> dict[str, Any] | None:
        """Load approved profile, preferences, and memory facts when available.

        Profile/preferences come from one validated compact projection — never
        parallel unvalidated JSON parsing. Missing rows yield ``None`` slices.
        """
        if memory_limit < 1 or memory_limit > MAX_MEMORY_FACTS:
            raise ChatContextError("invalid memory_limit")

        try:
            approved = await self._profile_context.load_compact_approved_context()
        except ProfileContextError as exc:
            raise ChatContextError(str(exc) or "profile context failed") from exc

        facts_result = await self._session.execute(
            select(MemoryFact)
            .order_by(MemoryFact.created_at.asc(), MemoryFact.id.asc())
            .limit(memory_limit)
        )
        fact_rows = list(facts_result.scalars().all())

        memory_facts: list[dict[str, Any]] = []
        for fact in fact_rows:
            entry: dict[str, Any] = {
                "key": fact.key,
                "value": fact.value_json,
                "source": fact.source,
            }
            # Never include raw body-shaped keys from value_json mappings.
            if isinstance(fact.value_json, Mapping):
                sanitized = _sanitize_structured_mapping(fact.value_json)
                entry["value"] = sanitized if sanitized is not None else {}
            memory_facts.append(entry)

        safe_ids = _normalize_attachment_ids(attachment_ids)

        profile = approved.profile
        preferences = approved.preferences
        active_attachment_id = approved.active_attachment_id

        if (
            profile is None
            and preferences is None
            and active_attachment_id is None
            and not memory_facts
            and not safe_ids
        ):
            return None

        context: dict[str, Any] = {}
        if profile is not None:
            context["profile"] = profile
        if preferences is not None:
            context["preferences"] = preferences
        if active_attachment_id is not None:
            # ID only — never storage paths.
            context["active_attachment_id"] = active_attachment_id
        if memory_facts:
            context["memory_facts"] = memory_facts
        if safe_ids:
            # ID-only large-content references (never bodies).
            context["attachment_ids"] = list(safe_ids)
        return context

    async def assemble(
        self,
        *,
        run_id: str | UUID,
        current_turn_content: str,
        current_turn_role: str = "user",
        attachment_ids: Sequence[str] | None = None,
        recent_limit: int = DEFAULT_RECENT_CONTEXT_LIMIT,
        pending_approval: Mapping[str, Any] | None = None,
        current_message_id: str | UUID | None = None,
        exclude_current_from_recent: bool = True,
        tool_iteration_count: int = 0,
        error: Mapping[str, Any] | None = None,
    ) -> AgentState:
        """Build validated AgentState for the current turn.

        Includes:
        - approved profile/preferences when available
        - relevant memory facts (bounded)
        - current turn in ``messages_for_this_turn``
        - bounded recent window via repository
        """
        if not isinstance(current_turn_content, str) or not current_turn_content.strip():
            raise ChatContextError("current turn content required")
        if recent_limit < 1 or recent_limit > MAX_RECENT_CONTEXT_LIMIT:
            raise ChatContextError("invalid recent_limit")

        safe_attachment_ids = _normalize_attachment_ids(attachment_ids)
        conversation = await self._conversations.ensure_singleton()
        conversation_id = str(conversation.id)
        run_id_str = str(run_id).strip()
        if not run_id_str:
            raise ChatContextError("run_id required")

        recent_rows = await self._conversations.list_recent_for_context(
            limit=recent_limit
        )
        recent: list[dict[str, Any]] = []
        current_id_str = (
            str(current_message_id).strip() if current_message_id is not None else None
        )
        for row in recent_rows:
            if exclude_current_from_recent and current_id_str is not None:
                if str(row.id) == current_id_str:
                    continue
            recent.append(_message_to_context(row).as_dict())

        turn_message: dict[str, Any] = {
            "role": current_turn_role,
            "content": current_turn_content,
        }
        if current_id_str is not None:
            turn_message["message_id"] = current_id_str

        candidate_context = await self.load_optional_candidate_context(
            attachment_ids=safe_attachment_ids,
        )

        try:
            state = initial_agent_state(
                conversation_id=conversation_id,
                run_id=run_id_str,
                messages_for_this_turn=[turn_message],
                recent_context=recent,
                candidate_context=candidate_context,
                attachment_ids=safe_attachment_ids,
                pending_approval=(
                    dict(pending_approval) if pending_approval is not None else None
                ),
                tool_iteration_count=tool_iteration_count,
                error=dict(error) if error is not None else None,
            )
        except AgentStateError as exc:
            raise ChatContextError(str(exc)) from None
        return validate_agent_state(state)
