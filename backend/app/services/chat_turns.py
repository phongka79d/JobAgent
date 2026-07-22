"""Durable chat-turn and interrupt/resume orchestration (Plan 3 §7.2 / §7.6).

Short explicit transactions only: create user+running run, terminal
assistant+complete, durable failure, interrupt projection, resume claim, and
terminal no-op. Graph/provider execution and SSE yield never hold an open
application transaction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.context import (
    load_active_cv_context,
    load_candidate_context,
    load_profile_working_memory_messages,
    load_recent_context,
    normalize_turn_attachment_ids,
)
from app.agent.graph import AgentGraphBundle
from app.agent.runner import TerminalOutcome, stream_agent_run
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
)
from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    AGENT_RUN_STATE_FAILED,
    AGENT_RUN_STATE_INTERRUPTED,
    AGENT_RUN_STATE_RUNNING,
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_USER,
    AgentRun,
    ChatMessage,
)
from app.db.session import get_session_factory, session_scope
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.schemas.sse import SseEvent, build_sse_event
from app.storage.attachments import AttachmentStorage
from app.tools.registry import ToolRegistry

# Stable application codes (not domain workflow names).
ERROR_APPROVAL_ACTION_REQUIRED: str = "APPROVAL_ACTION_REQUIRED"
ERROR_INVALID_APPROVAL_ACTION: str = "INVALID_APPROVAL_ACTION"
ERROR_RUN_NOT_FOUND: str = "RUN_NOT_FOUND"
ERROR_RUN_NOT_RESUMABLE: str = "RUN_NOT_RESUMABLE"
ERROR_CV_ATTACHMENT_NOT_FOUND: str = "CV_ATTACHMENT_NOT_FOUND"
ERROR_CV_NOT_REPROCESSABLE: str = "CV_NOT_REPROCESSABLE"
ERROR_CV_FILE_UNAVAILABLE: str = "CV_FILE_UNAVAILABLE"
ERROR_CHUNKS_UNAVAILABLE: str = "CHUNKS_UNAVAILABLE"

_REPROCESS_ELIGIBLE_STATES: frozenset[str] = frozenset(
    {ATTACHMENT_STATE_ACTIVE, ATTACHMENT_STATE_ARCHIVED}
)


class ChatTurnError(Exception):
    """Application error with a stable code for transport mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CreatedTurn:
    """Result of the atomic user-message + running-run create."""

    user_message_id: str
    run_id: str
    content: str


def _normalize_projection(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate compact approval projection shape for durable storage/SSE.

    Preserves optional ``draft_id`` when present (domain tools may include it).
    Does not interpret action names — callers supply allowed actions.
    """
    kind = raw.get("kind")
    actions = raw.get("allowed_actions")
    if not isinstance(kind, str) or kind.strip() == "":
        raise ChatTurnError(
            ERROR_RUN_NOT_RESUMABLE,
            "interrupt projection missing kind",
        )
    if not isinstance(actions, list) or not actions:
        raise ChatTurnError(
            ERROR_RUN_NOT_RESUMABLE,
            "interrupt projection missing allowed_actions",
        )
    cleaned: list[str] = []
    for item in actions:
        if not isinstance(item, str) or item.strip() == "":
            raise ChatTurnError(
                ERROR_RUN_NOT_RESUMABLE,
                "interrupt projection has invalid allowed_actions",
            )
        cleaned.append(item)
    card = raw.get("card")
    if card is None:
        card = {}
    if not isinstance(card, dict):
        raise ChatTurnError(
            ERROR_RUN_NOT_RESUMABLE,
            "interrupt projection card must be an object",
        )
    projection: dict[str, Any] = {
        "kind": kind,
        "allowed_actions": cleaned,
        "card": card,
    }
    draft_id = raw.get("draft_id")
    if isinstance(draft_id, str) and draft_id.strip() != "":
        projection["draft_id"] = draft_id
    return projection


async def get_interrupted_run(
    session: AsyncSession,
) -> AgentRun | None:
    """Return any currently interrupted run (at most one expected)."""
    stmt = (
        select(AgentRun)
        .where(AgentRun.state == AGENT_RUN_STATE_INTERRUPTED)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_chat_messages(session: AsyncSession) -> int:
    """Count durable chat_messages rows (for interruption-guard tests)."""
    stmt = select(func.count()).select_from(ChatMessage)
    return int((await session.execute(stmt)).scalar_one())


async def create_user_turn(
    *,
    message: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    source_attachment_id: str | None = None,
) -> CreatedTurn:
    """Atomically insert user message + ``running`` run, or reject interruption.

    Raises ``ChatTurnError(APPROVAL_ACTION_REQUIRED)`` **before** any insert when
    an interrupted run exists. Optional *source_attachment_id* stamps CV
    ownership on both the message and run rows (reprocess turns).
    """
    text = message.strip() if isinstance(message, str) else ""
    if text == "":
        raise ChatTurnError("EMPTY_MESSAGE", "message must be non-empty")
    owner: str | None = None
    if source_attachment_id is not None:
        if (
            not isinstance(source_attachment_id, str)
            or source_attachment_id.strip() == ""
        ):
            raise ChatTurnError(
                ERROR_CV_ATTACHMENT_NOT_FOUND,
                "source_attachment_id must be a non-empty attachment id",
            )
        owner = source_attachment_id.strip()

    factory = session_factory or get_session_factory()
    async with session_scope(factory) as session:
        interrupted = await get_interrupted_run(session)
        if interrupted is not None:
            raise ChatTurnError(
                ERROR_APPROVAL_ACTION_REQUIRED,
                "an interrupted run requires an approval action before a new turn",
            )
        user = await messages_repo.insert_message(
            session,
            role=CHAT_MESSAGE_ROLE_USER,
            content=text,
            source_attachment_id=owner,
        )
        run = await runs_repo.create_run(
            session,
            user_message_id=user.id,
            source_attachment_id=owner,
        )
        return CreatedTurn(
            user_message_id=user.id,
            run_id=run.id,
            content=text,
        )


async def assert_cv_reprocessable(
    *,
    attachment_id: str,
    storage: AttachmentStorage,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Validate reprocess preconditions without mutating state.

    Raises :class:`ChatTurnError` with stable codes for not-found, wrong state,
    missing retained file, or a conflicting interrupted run.
    """
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise ChatTurnError(
            ERROR_CV_ATTACHMENT_NOT_FOUND,
            "attachment_id is required",
        )
    att_id = attachment_id.strip()
    factory = session_factory or get_session_factory()
    async with factory() as session:
        interrupted = await get_interrupted_run(session)
        if interrupted is not None:
            raise ChatTurnError(
                ERROR_APPROVAL_ACTION_REQUIRED,
                "an interrupted run requires an approval action before reprocess",
            )
        row = await att_repo.get_by_id(session, att_id)
        if row is None:
            raise ChatTurnError(
                ERROR_CV_ATTACHMENT_NOT_FOUND,
                f"attachment {att_id!r} not found",
            )
        if row.state not in _REPROCESS_ELIGIBLE_STATES:
            raise ChatTurnError(
                ERROR_CV_NOT_REPROCESSABLE,
                f"attachment state {row.state!r} cannot be reprocessed",
            )
        if not storage.exists(row.storage_path):
            raise ChatTurnError(
                ERROR_CV_FILE_UNAVAILABLE,
                "retained CV file is unavailable for reprocess",
            )


async def persist_terminal_success(
    *,
    run_id: str,
    assistant_text: str | None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Atomically insert assistant message and mark run completed."""
    factory = session_factory or get_session_factory()
    content = assistant_text if assistant_text and assistant_text.strip() else ""
    async with session_scope(factory) as session:
        if content == "":
            content = "(no assistant text)"
        await messages_repo.insert_message(
            session,
            role=CHAT_MESSAGE_ROLE_ASSISTANT,
            content=content,
        )
        await runs_repo.complete_run(session, run_id)


async def persist_terminal_failure(
    *,
    run_id: str,
    error_code: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Mark run failed with stable code; retain the user turn."""
    code = error_code.strip() if isinstance(error_code, str) else ""
    if code == "":
        code = "AGENT_EXECUTION_FAILED"
    factory = session_factory or get_session_factory()
    async with session_scope(factory) as session:
        await runs_repo.fail_run(session, run_id, error_code=code)


async def persist_interrupt(
    *,
    run_id: str,
    pending_approval: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    """Store compact approval projection and set run to interrupted."""
    projection = _normalize_projection(pending_approval)
    factory = session_factory or get_session_factory()
    async with session_scope(factory) as session:
        await runs_repo.interrupt_run(
            session,
            run_id,
            pending_approval_json=projection,
        )
    return projection


async def claim_resume(
    *,
    run_id: str,
    action: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> tuple[AgentRun, str]:
    """Validate one action and atomically resume interrupted → running.

    Invalid actions leave the interrupted projection unchanged.
    """
    chosen = action.strip() if isinstance(action, str) else ""
    if chosen == "":
        raise ChatTurnError(
            ERROR_INVALID_APPROVAL_ACTION,
            "action must be a non-empty string",
        )

    factory = session_factory or get_session_factory()
    async with session_scope(factory) as session:
        run = await runs_repo.get_run(session, run_id)
        if run is None:
            raise ChatTurnError(ERROR_RUN_NOT_FOUND, f"run {run_id!r} not found")
        if run.state in (AGENT_RUN_STATE_COMPLETED, AGENT_RUN_STATE_FAILED):
            # Caller streams terminal no-op without mutation.
            return run, chosen
        if run.state != AGENT_RUN_STATE_INTERRUPTED:
            raise ChatTurnError(
                ERROR_RUN_NOT_RESUMABLE,
                f"run {run_id!r} is not interrupted (state={run.state!r})",
            )
        projection = run.pending_approval_json
        if not isinstance(projection, dict):
            raise ChatTurnError(
                ERROR_RUN_NOT_RESUMABLE,
                "interrupted run missing pending_approval projection",
            )
        allowed = projection.get("allowed_actions") or []
        if chosen not in allowed:
            raise ChatTurnError(
                ERROR_INVALID_APPROVAL_ACTION,
                f"action {chosen!r} is not allowed for this interrupt",
            )
        resumed = await runs_repo.resume_run(session, run_id)
        return resumed, chosen


def _approval_required_event(run_id: str, projection: dict[str, Any]) -> SseEvent:
    return build_sse_event(
        "approval_required",
        run_id,
        {
            "state": "interrupted",
            "kind": projection["kind"],
            "allowed_actions": list(projection["allowed_actions"]),
            "card": dict(projection.get("card") or {}),
        },
    )


def _terminal_noop_events(run: AgentRun) -> list[SseEvent]:
    """Persisted terminal state only — no graph, deltas, or tool replay."""
    run_id = run.id
    events = [
        build_sse_event(
            "run_started",
            run_id,
            {"state": "running", "resumed": True},
        )
    ]
    if run.state == AGENT_RUN_STATE_COMPLETED:
        events.append(
            build_sse_event("run_completed", run_id, {"state": "completed"})
        )
    elif run.state == AGENT_RUN_STATE_FAILED:
        events.append(
            build_sse_event(
                "run_failed",
                run_id,
                {
                    "state": "failed",
                    "error_code": run.error_code or "RUN_FAILED",
                    "summary": "Persisted terminal run state",
                },
            )
        )
    return events


async def _on_durable_terminal(
    outcome: TerminalOutcome,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    interrupt_holder: dict[str, Any],
) -> bool:
    """Persist durable truth for completed/failed/interrupted outcomes."""
    if outcome.kind == "completed":
        await persist_terminal_success(
            run_id=outcome.run_id,
            assistant_text=outcome.assistant_text,
            session_factory=session_factory,
        )
        return True
    if outcome.kind == "failed":
        await persist_terminal_failure(
            run_id=outcome.run_id,
            error_code=outcome.error_code or "AGENT_EXECUTION_FAILED",
            session_factory=session_factory,
        )
        return True
    if outcome.kind == "interrupted":
        if not isinstance(outcome.pending_approval, dict):
            await persist_terminal_failure(
                run_id=outcome.run_id,
                error_code="INTERRUPT_PROJECTION_MISSING",
                session_factory=session_factory,
            )
            return True
        projection = await persist_interrupt(
            run_id=outcome.run_id,
            pending_approval=outcome.pending_approval,
            session_factory=session_factory,
        )
        interrupt_holder["projection"] = projection
        return True
    return False


async def stream_chat_turn(
    *,
    message: str,
    model: BaseChatModel | Runnable[Any, Any] | None = None,
    registry: ToolRegistry | None = None,
    graph_bundle: AgentGraphBundle | None = None,
    attachment_ids: Sequence[str] | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    sqlite_path: str | Path | None = None,
    include_assistant_status: bool = False,
    source_attachment_id: str | None = None,
) -> AsyncIterator[SseEvent]:
    """Create a durable turn, run the graph, persist terminal/interrupt state.

    Blocks new turns while any run is interrupted (before insert). Optional
    *source_attachment_id* stamps CV ownership on the message/run pair.
    """
    factory = session_factory or get_session_factory()
    turn = await create_user_turn(
        message=message,
        session_factory=factory,
        source_attachment_id=source_attachment_id,
    )
    interrupt_holder: dict[str, Any] = {}

    # Load bounded recent + approved candidate + compact active-CV outline
    # before graph execution. Short read session only — never held open across
    # provider/graph work. Candidate context is the approved profile only;
    # draft/staged attachment working memory is injected as system
    # ContextMessages so later turns still see source_attachment_id UUIDs
    # (models otherwise invent "current"). Active outline is identity + section
    # headings only (never bodies/chunks); resolved server-side from the active
    # profile.
    async with factory() as session:
        recent_loaded = await load_recent_context(
            session,
            exclude_ids=frozenset({turn.user_message_id}),
        )
        candidate_context = await load_candidate_context(session)
        active_cv_context = await load_active_cv_context(session)
        working_memory = await load_profile_working_memory_messages(session)
        effective_attachment_ids = normalize_turn_attachment_ids(attachment_ids)
    # Graph state uses list[dict] channels; ContextMessage is a TypedDict.
    recent_context: list[dict[str, Any]] = [
        dict(m) for m in working_memory
    ] + [dict(m) for m in recent_loaded]

    async def on_terminal(outcome: TerminalOutcome) -> bool:
        return await _on_durable_terminal(
            outcome,
            session_factory=factory,
            interrupt_holder=interrupt_holder,
        )

    async for event in stream_agent_run(
        run_id=turn.run_id,
        user_text=turn.content,
        recent_context=recent_context,
        candidate_context=candidate_context,
        active_cv_context=active_cv_context,
        attachment_ids=effective_attachment_ids,
        model=model,
        registry=registry,
        graph_bundle=graph_bundle,
        sqlite_path=sqlite_path,
        on_durable_terminal=on_terminal,
        include_assistant_status=include_assistant_status,
        resumed=False,
    ):
        yield event

    projection = interrupt_holder.get("projection")
    if isinstance(projection, dict):
        yield _approval_required_event(turn.run_id, projection)


async def stream_cv_reprocess(
    *,
    attachment_id: str,
    storage: AttachmentStorage,
    model: BaseChatModel | Runnable[Any, Any] | None = None,
    registry: ToolRegistry | None = None,
    graph_bundle: AgentGraphBundle | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    sqlite_path: str | Path | None = None,
    include_assistant_status: bool = False,
) -> AsyncIterator[SseEvent]:
    """CV Manager reprocess: validate, create one CV-owned turn, stream SSE.

    Reuses the normal runner/SSE/approval contract. Active selection is not
    mutated here; only the Agent proposal/commit tools write drafts and the
    resume path activates on Save Profile.
    """
    factory = session_factory or get_session_factory()
    await assert_cv_reprocessable(
        attachment_id=attachment_id,
        storage=storage,
        session_factory=factory,
    )
    # Domain-agnostic user text; attachment_ids + ownership drive the tools.
    # Do not name tool symbols here (ownership boundary). CV-owned runs stamp
    # source_attachment_id so propose forces reprocess even if the model omits it.
    message = (
        f"Re-extract the retained CV for attachment {attachment_id} "
        "and prepare a new current draft for approval without reusing the "
        "existing approved profile as a no-extract short-circuit."
    )
    async for event in stream_chat_turn(
        message=message,
        model=model,
        registry=registry,
        graph_bundle=graph_bundle,
        attachment_ids=[attachment_id],
        session_factory=factory,
        sqlite_path=sqlite_path,
        include_assistant_status=include_assistant_status,
        source_attachment_id=attachment_id,
    ):
        yield event


async def stream_resume(
    *,
    run_id: str,
    action: str,
    model: BaseChatModel | Runnable[Any, Any] | None = None,
    registry: ToolRegistry | None = None,
    graph_bundle: AgentGraphBundle | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    sqlite_path: str | Path | None = None,
    include_assistant_status: bool = False,
) -> AsyncIterator[SseEvent]:
    """Resume an interrupted run, or emit terminal no-op for completed/failed.

    Invalid actions leave interruption unchanged. Terminal resume never executes
    the graph or replays text/tool side effects.
    """
    factory = session_factory or get_session_factory()
    run, chosen = await claim_resume(
        run_id=run_id,
        action=action,
        session_factory=factory,
    )

    if run.state in (AGENT_RUN_STATE_COMPLETED, AGENT_RUN_STATE_FAILED):
        for event in _terminal_noop_events(run):
            yield event
        return

    if run.state != AGENT_RUN_STATE_RUNNING:
        raise ChatTurnError(
            ERROR_RUN_NOT_RESUMABLE,
            f"run {run_id!r} not running after resume claim (state={run.state!r})",
        )

    interrupt_holder: dict[str, Any] = {}

    async def on_terminal(outcome: TerminalOutcome) -> bool:
        return await _on_durable_terminal(
            outcome,
            session_factory=factory,
            interrupt_holder=interrupt_holder,
        )

    async for event in stream_agent_run(
        run_id=run_id,
        resumed=True,
        resume_value=chosen,
        model=model,
        registry=registry,
        graph_bundle=graph_bundle,
        sqlite_path=sqlite_path,
        on_durable_terminal=on_terminal,
        include_assistant_status=include_assistant_status,
    ):
        yield event

    projection = interrupt_holder.get("projection")
    if isinstance(projection, dict):
        yield _approval_required_event(run_id, projection)


__all__ = [
    "ERROR_APPROVAL_ACTION_REQUIRED",
    "ERROR_CHUNKS_UNAVAILABLE",
    "ERROR_CV_ATTACHMENT_NOT_FOUND",
    "ERROR_CV_FILE_UNAVAILABLE",
    "ERROR_CV_NOT_REPROCESSABLE",
    "ERROR_INVALID_APPROVAL_ACTION",
    "ERROR_RUN_NOT_FOUND",
    "ERROR_RUN_NOT_RESUMABLE",
    "ChatTurnError",
    "CreatedTurn",
    "assert_cv_reprocessable",
    "claim_resume",
    "count_chat_messages",
    "create_user_turn",
    "get_interrupted_run",
    "persist_interrupt",
    "persist_terminal_failure",
    "persist_terminal_success",
    "stream_chat_turn",
    "stream_cv_reprocess",
    "stream_resume",
]
