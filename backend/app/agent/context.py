"""Bounded recent-context loading for Agent turns (Plan 3 §7.4 / Master §12.4).

Prompt-budget owner: this module. The model receives only a compact recent
window that fits the documented ceilings below — never an unbounded conversation
load and never a fixed sixty-four-kilotoken history dump.

Budget ceilings (deterministic, content-character based on ``ChatMessage.content``):

* ``RECENT_CONTEXT_MAX_MESSAGES`` — hard cap on rows fetched and selected.
* ``RECENT_CONTEXT_CHAR_BUDGET`` — max sum of ``len(content)`` across selected
  messages (UTF-8-agnostic Python code-point length).

Selection walks newest-first using repository ordering
``(created_at DESC, id DESC)`` via a single bounded ``list_messages_before``
query (limit = max messages). It never calls full-conversation list APIs.
Selected messages are returned oldest→newest for chronological prompt order.

Candidate profile/preferences context is empty in Phase 2; attachment and large
document references remain IDs only (handled in ``state`` / turn inputs).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import ContextMessage
from app.db.models.chat import CONVERSATION_ID
from app.repositories import chat_messages as messages_repo

# ---------------------------------------------------------------------------
# Documented prompt budget (owner: app.agent.context)
# ---------------------------------------------------------------------------
# Ceiling for how many prior durable messages may enter recent_context.
RECENT_CONTEXT_MAX_MESSAGES: int = 20
# Ceiling for total content characters across the selected recent window.
# Keeps the prompt bounded without relying on an unbounded history dump.
RECENT_CONTEXT_CHAR_BUDGET: int = 12_000


class _MessageLike(Protocol):
    """Minimal durable message shape needed for budget selection."""

    id: str
    role: str
    content: str


def apply_recent_context_budget(
    messages_newest_first: Sequence[_MessageLike],
    *,
    max_messages: int = RECENT_CONTEXT_MAX_MESSAGES,
    char_budget: int = RECENT_CONTEXT_CHAR_BUDGET,
    exclude_ids: frozenset[str] | None = None,
) -> list[ContextMessage]:
    """Select a budget-bounded window from newest-first durable messages.

    Parameters
    ----------
    messages_newest_first:
        Prior messages ordered by ``(created_at DESC, id DESC)``. Callers must
        not pass an unbounded full-conversation dump; the loader below enforces
        a hard fetch limit.
    max_messages:
        Hard count ceiling (documented prompt budget).
    char_budget:
        Hard sum-of-content-length ceiling (documented prompt budget).
    exclude_ids:
        Message IDs to skip (e.g. the current turn's user message).

    Returns
    -------
    list[ContextMessage]
        Selected rows in chronological order ``(oldest → newest)``, compact
        projections only (id, role, content). Structured payloads and raw
        document bodies are never copied into context.
    """
    if max_messages < 0:
        raise ValueError("max_messages must be >= 0")
    if char_budget < 0:
        raise ValueError("char_budget must be >= 0")

    skip = exclude_ids or frozenset()
    selected_rev: list[ContextMessage] = []
    used_chars = 0

    for row in messages_newest_first:
        if len(selected_rev) >= max_messages:
            break
        if row.id in skip:
            continue
        # Text content only — never structured_payload / document bodies.
        content = row.content if isinstance(row.content, str) else ""
        size = len(content)
        if selected_rev and used_chars + size > char_budget:
            # Stop before exceeding budget; keep already-selected newer rows.
            break
        if not selected_rev and size > char_budget:
            # Single oversized newest message: include truncated to budget so the
            # window stays within the documented character ceiling.
            content = content[:char_budget]
            size = len(content)
        selected_rev.append(
            ContextMessage(id=row.id, role=row.role, content=content)
        )
        used_chars += size

    # Chronological order for prompt assembly.
    selected_rev.reverse()
    return selected_rev


async def load_recent_context(
    session: AsyncSession,
    *,
    exclude_ids: frozenset[str] | None = None,
    max_messages: int = RECENT_CONTEXT_MAX_MESSAGES,
    char_budget: int = RECENT_CONTEXT_CHAR_BUDGET,
) -> list[ContextMessage]:
    """Load recent main-conversation messages within the documented budget.

    Uses a single bounded repository fetch (``limit=max_messages``) against the
    singleton conversation. Does not paginate through the whole conversation and
    does not use history-cursor hydration (that path is for the public API).
    """
    if max_messages < 1:
        return []

    # Bounded newest-first fetch only — hard stop at max_messages rows.
    rows = await messages_repo.list_messages_before(
        session,
        limit=max_messages,
        before=None,
    )
    # Repository already confines to conversation_id == main; assert invariant.
    for row in rows:
        if row.conversation_id != CONVERSATION_ID:
            raise RuntimeError(
                "recent context loader received non-main conversation row"
            )

    return apply_recent_context_budget(
        rows,
        max_messages=max_messages,
        char_budget=char_budget,
        exclude_ids=exclude_ids,
    )


def empty_candidate_context() -> list[dict[str, object]]:
    """Phase 2 candidate projection: always empty (Plan 4 fills compact cards)."""
    return []
