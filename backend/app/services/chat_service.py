"""Chat execution service: durable turns, resume, and checkpoint lifecycle.

Owns application write ordering for Plan 3 §7.1:
1. Persist user message before run creation/execution.
2. One durable agent run / LangGraph thread id per turn; resume reuses it.
3. Persist validated final assistant message before completed-checkpoint cleanup.
4. Retain application run outcome and sanitized tool records after cleanup.
5. On disconnect/cancel, advance only to a safe durable state; reconnect uses
   history/run state and never replays writes for the same idempotency key.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal
from uuid import UUID

from langchain_core.messages import ToolMessage
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import (
    DecisionPort,
    build_agent_graph,
    initial_graph_state,
)
from app.agent.lifecycle import (
    CheckpointLifecycleError,
    delete_completed_thread_checkpoints,
    extract_interrupt_payload,
    open_async_sqlite_saver,
    result_is_graph_interrupt,
    thread_run_config,
)
from app.db.enums import AgentRunState, MessageRole
from app.db.models.conversation import AgentRun, ChatMessage, ToolExecution
from app.db.session import DatabaseSessionManager
from app.repositories.agent_runs import (
    AgentRunRepository,
    AgentRunStateError,
    AgentRunValidationError,
    langgraph_thread_id,
)
from app.repositories.conversations import (
    ConversationMessageError,
    ConversationRepository,
    ConversationRepositoryError,
)
from app.repositories.tool_executions import (
    ToolExecutionRepository,
    ToolExecutionValidationError,
)
from app.services.chat_context import ChatContextAssembler, ChatContextError

RunOutcomeKind = Literal[
    "completed",
    "interrupted",
    "failed",
    "replay",
    "disconnected",
]

GraphFactory = Callable[[Any], Any]
# Async callable: (compiled_graph, input_or_command, config) -> result mapping
GraphRunner = Callable[
    [Any, Any, dict[str, Any]],
    Coroutine[Any, Any, Mapping[str, Any]],
]

_MAX_ASSISTANT_CONTENT: Final[int] = 32_768
_DEFAULT_RECENT_LIMIT: Final[int] = 20
# Allowlisted durable/public tool outcome token (never tool args/results/docs).
PUBLIC_TOOL_OUTCOME_COMPLETED: Final[str] = "completed"


class ChatServiceError(Exception):
    """Chat execution failed without disclosing secrets or raw provider bodies."""


class ChatServiceValidationError(ChatServiceError):
    """Caller input failed closed validation before durable writes."""


class ChatServiceStateError(ChatServiceError):
    """Run is not in a state that allows the requested action."""


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    """Durable outcome of one turn start or resume attempt."""

    run_id: UUID
    thread_id: str
    state: str
    outcome: RunOutcomeKind
    user_message_id: UUID | None
    assistant_message_id: UUID | None
    final_text: str | None
    error: str | None
    pending_approval: dict[str, Any] | None
    replayed: bool
    checkpoints_deleted: bool


def _validate_user_text(text: str) -> str:
    if not isinstance(text, str):
        raise ChatServiceValidationError("invalid user text")
    cleaned = text.strip()
    if not cleaned:
        raise ChatServiceValidationError("invalid user text")
    if len(cleaned) > _MAX_ASSISTANT_CONTENT:
        raise ChatServiceValidationError("user text too large")
    return cleaned


def _validate_assistant_text(text: str) -> str:
    if not isinstance(text, str):
        raise ChatServiceValidationError("invalid assistant text")
    cleaned = text.strip()
    if not cleaned:
        raise ChatServiceValidationError("invalid assistant text")
    if len(cleaned) > _MAX_ASSISTANT_CONTENT:
        cleaned = cleaned[:_MAX_ASSISTANT_CONTENT]
    return cleaned


async def _default_graph_runner(
    graph: Any,
    payload: Any,
    config: dict[str, Any],
) -> Mapping[str, Any]:
    result = await graph.ainvoke(payload, config=config)
    if not isinstance(result, Mapping):
        return {}
    return result


class ChatService:
    """Application owner of turn execution and per-run checkpoint cleanup."""

    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        *,
        sqlite_path: str | Path,
        decision: DecisionPort | None = None,
        tools: Sequence[Any] | None = None,
        graph_factory: GraphFactory | None = None,
        graph_runner: GraphRunner | None = None,
        recent_context_limit: int = _DEFAULT_RECENT_LIMIT,
    ) -> None:
        self._db = session_manager
        self._sqlite_path = Path(sqlite_path)
        self._decision = decision
        self._tools = list(tools) if tools is not None else None
        self._graph_factory = graph_factory
        self._graph_runner = graph_runner or _default_graph_runner
        self._recent_limit = recent_context_limit

    def _compile_graph(self, checkpointer: Any) -> Any:
        if self._graph_factory is not None:
            return self._graph_factory(checkpointer)
        return build_agent_graph(
            tools=self._tools,
            decision=self._decision,
            checkpointer=checkpointer,
        )

    async def start_turn(
        self,
        *,
        user_text: str,
        turn_idempotency_key: str,
        attachment_ids: Sequence[str] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> ChatTurnResult:
        """Persist user message + run, execute graph, finalize durable outcome.

        Duplicate ``turn_idempotency_key`` returns the existing run outcome
        without a second message, run, tool write, or graph execution.
        """
        safe_text = _validate_user_text(user_text)
        safe_attachments = list(attachment_ids or ())

        prepared = await self._prepare_new_turn(
            user_text=safe_text,
            turn_idempotency_key=turn_idempotency_key,
            attachment_ids=safe_attachments,
        )
        if prepared.early is not None:
            return prepared.early

        assert prepared.run_id is not None
        assert prepared.thread_id is not None
        assert prepared.user_message_id is not None
        assert prepared.graph_input is not None

        return await self._execute_and_finalize(
            run_id=prepared.run_id,
            thread_id=prepared.thread_id,
            user_message_id=prepared.user_message_id,
            graph_input=prepared.graph_input,
            cancel_event=cancel_event,
            is_resume=False,
        )

    async def resume_run(
        self,
        *,
        run_id: UUID,
        resume_idempotency_key: str,
        resume_value: Any = True,
        cancel_event: asyncio.Event | None = None,
    ) -> ChatTurnResult:
        """Resume an interrupted production-graph run with the same thread identity.

        Uses ``Command(resume=...)`` against the original LangGraph ``thread_id``
        (application run id) so ``await_approval`` / ``request_human_approval``
        continues on the durable checkpoint. Duplicate
        ``resume_idempotency_key`` for the same run returns the durable outcome
        without replaying graph writes.
        """
        if not isinstance(run_id, UUID):
            raise ChatServiceValidationError("invalid run_id")

        prepared = await self._prepare_resume(
            run_id=run_id,
            resume_idempotency_key=resume_idempotency_key,
            resume_value=resume_value,
        )
        if prepared.early is not None:
            return prepared.early

        assert prepared.run_id is not None
        assert prepared.thread_id is not None
        assert prepared.graph_input is not None

        return await self._execute_and_finalize(
            run_id=prepared.run_id,
            thread_id=prepared.thread_id,
            user_message_id=prepared.user_message_id,
            graph_input=prepared.graph_input,
            cancel_event=cancel_event,
            is_resume=True,
        )

    async def handle_disconnect(self, run_id: UUID) -> ChatTurnResult:
        """Advance a non-terminal run to a safe durable state after disconnect.

        Prefer ``interrupted`` when the run already awaited approval; otherwise
        mark ``failed`` with a sanitized disconnect code. Never replays graph
        execution or writes duplicate assistant messages.
        """
        if not isinstance(run_id, UUID):
            raise ChatServiceValidationError("invalid run_id")

        async with self._db.session_scope() as session:
            runs = AgentRunRepository(session)
            run = await runs.get_by_id(run_id)
            if run is None:
                raise ChatServiceStateError("agent run not found")

            if run.state == AgentRunState.COMPLETED.value:
                return await self._snapshot_result(
                    session,
                    run,
                    outcome="replay",
                    replayed=True,
                    checkpoints_deleted=False,
                )
            if run.state == AgentRunState.FAILED.value:
                return await self._snapshot_result(
                    session,
                    run,
                    outcome="failed",
                    replayed=True,
                    checkpoints_deleted=False,
                )
            if run.state == AgentRunState.INTERRUPTED.value:
                return await self._snapshot_result(
                    session,
                    run,
                    outcome="interrupted",
                    replayed=True,
                    checkpoints_deleted=False,
                )

            # pending/running: fail closed to a durable inspectable state.
            try:
                run = await runs.mark_failed(
                    run.id,
                    error="client_disconnected",
                )
            except AgentRunStateError:
                run = await runs.get_by_id(run_id)
                if run is None:
                    raise ChatServiceStateError("agent run not found") from None
            return await self._snapshot_result(
                session,
                run,
                outcome="disconnected",
                replayed=False,
                checkpoints_deleted=False,
            )

    # --- prepare / execute internals -----------------------------------------

    @dataclass(slots=True)
    class _Prepared:
        early: ChatTurnResult | None = None
        run_id: UUID | None = None
        thread_id: str | None = None
        user_message_id: UUID | None = None
        graph_input: Any | None = None

    async def _prepare_new_turn(
        self,
        *,
        user_text: str,
        turn_idempotency_key: str,
        attachment_ids: list[str],
    ) -> ChatService._Prepared:
        async with self._db.session_scope() as session:
            conv = ConversationRepository(session)
            runs = AgentRunRepository(session)

            try:
                existing = await runs.get_by_turn_idempotency_key(
                    turn_idempotency_key
                )
            except AgentRunValidationError as exc:
                raise ChatServiceValidationError("invalid turn_idempotency_key") from exc

            if existing is not None:
                return ChatService._Prepared(
                    early=await self._snapshot_result(
                        session,
                        existing,
                        outcome="replay",
                        replayed=True,
                        checkpoints_deleted=False,
                    )
                )

            try:
                user_msg = await conv.append_message(
                    role=MessageRole.USER,
                    content=user_text,
                )
                run = await runs.create_for_turn(
                    message_id=user_msg.id,
                    turn_idempotency_key=turn_idempotency_key,
                )
            except (
                ConversationRepositoryError,
                ConversationMessageError,
                AgentRunValidationError,
            ) as exc:
                raise ChatServiceValidationError("turn prepare failed") from exc

            # Race: another writer may have created the run for this key after
            # our pre-check; still return without a second graph execution when
            # the run is no longer pending.
            if run.state != AgentRunState.PENDING.value:
                return ChatService._Prepared(
                    early=await self._snapshot_result(
                        session,
                        run,
                        outcome="replay",
                        replayed=True,
                        checkpoints_deleted=False,
                    )
                )

            try:
                run = await runs.mark_running(run.id)
            except AgentRunStateError as exc:
                raise ChatServiceStateError("cannot start run") from exc

            try:
                assembler = ChatContextAssembler(session)
                agent_state = await assembler.assemble(
                    run_id=run.id,
                    current_turn_content=user_text,
                    attachment_ids=attachment_ids,
                    recent_limit=self._recent_limit,
                    current_message_id=user_msg.id,
                )
            except ChatContextError as exc:
                await runs.mark_failed(run.id, error="context_assembly_failed")
                raise ChatServiceError("context assembly failed") from exc

            graph_input = initial_graph_state(
                conversation_id=agent_state["conversation_id"],
                run_id=str(run.id),
                user_text=user_text,
                recent_context=agent_state["recent_context"],
                candidate_context=agent_state["candidate_context"],
                attachment_ids=agent_state["attachment_ids"],
            )
            return ChatService._Prepared(
                run_id=run.id,
                thread_id=langgraph_thread_id(run),
                user_message_id=user_msg.id,
                graph_input=graph_input,
            )

    async def _prepare_resume(
        self,
        *,
        run_id: UUID,
        resume_idempotency_key: str,
        resume_value: Any,
    ) -> ChatService._Prepared:
        async with self._db.session_scope() as session:
            runs = AgentRunRepository(session)
            try:
                run = await runs.get_by_id(run_id)
            except AgentRunValidationError as exc:
                raise ChatServiceValidationError("invalid run_id") from exc
            if run is None:
                raise ChatServiceStateError("agent run not found")

            # Terminal outcomes: never re-execute.
            if run.state in {
                AgentRunState.COMPLETED.value,
                AgentRunState.FAILED.value,
            }:
                return ChatService._Prepared(
                    early=await self._snapshot_result(
                        session,
                        run,
                        outcome="replay",
                        replayed=True,
                        checkpoints_deleted=False,
                    )
                )

            prior_key = run.resume_idempotency_key
            try:
                run = await runs.apply_resume(
                    run_id,
                    resume_idempotency_key=resume_idempotency_key,
                )
            except AgentRunValidationError as exc:
                raise ChatServiceValidationError(
                    "invalid resume_idempotency_key"
                ) from exc
            except AgentRunStateError:
                refreshed = await runs.get_by_id(run_id)
                if refreshed is None:
                    raise ChatServiceStateError("agent run not found") from None
                # Same key already bound to a terminal/durable outcome.
                if refreshed.resume_idempotency_key == resume_idempotency_key:
                    return ChatService._Prepared(
                        early=await self._snapshot_result(
                            session,
                            refreshed,
                            outcome="replay",
                            replayed=True,
                            checkpoints_deleted=False,
                        )
                    )
                raise ChatServiceStateError("cannot resume run") from None

            if run.state in {
                AgentRunState.COMPLETED.value,
                AgentRunState.FAILED.value,
            }:
                return ChatService._Prepared(
                    early=await self._snapshot_result(
                        session,
                        run,
                        outcome="replay",
                        replayed=True,
                        checkpoints_deleted=False,
                    )
                )

            if run.state != AgentRunState.RUNNING.value:
                return ChatService._Prepared(
                    early=await self._snapshot_result(
                        session,
                        run,
                        outcome="replay",
                        replayed=True,
                        checkpoints_deleted=False,
                    )
                )

            # Fresh interrupt claim uses Command(resume=...). Same-key after a
            # prior claim that never finished still continues the thread without
            # re-applying the interrupt payload (idempotent; no second write).
            if prior_key == resume_idempotency_key:
                return ChatService._Prepared(
                    early=await self._snapshot_result(
                        session,
                        run,
                        outcome="replay",
                        replayed=True,
                        checkpoints_deleted=False,
                    )
                )

            return ChatService._Prepared(
                run_id=run.id,
                thread_id=langgraph_thread_id(run),
                user_message_id=run.message_id,
                graph_input=Command(resume=resume_value),
            )

    async def _execute_and_finalize(
        self,
        *,
        run_id: UUID,
        thread_id: str,
        user_message_id: UUID | None,
        graph_input: Any,
        cancel_event: asyncio.Event | None,
        is_resume: bool,
    ) -> ChatTurnResult:
        del is_resume  # reserved for future SSE differentiation
        config = thread_run_config(thread_id)

        if cancel_event is not None and cancel_event.is_set():
            return await self.handle_disconnect(run_id)

        graph_result: Mapping[str, Any] | None = None
        graph_error: str | None = None
        cancelled = False
        raw: Any = None

        try:
            async with open_async_sqlite_saver(self._sqlite_path) as saver:
                graph = self._compile_graph(saver)
                run_coro = self._graph_runner(graph, graph_input, config)
                if cancel_event is None:
                    raw = await run_coro
                else:
                    # Race graph work against client disconnect signal.
                    task: asyncio.Task[Mapping[str, Any]] = asyncio.create_task(
                        run_coro
                    )
                    cancel_waiter = asyncio.create_task(cancel_event.wait())
                    try:
                        done, _pending = await asyncio.wait(
                            {task, cancel_waiter},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if cancel_waiter in done and not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                            cancelled = True
                        else:
                            raw = await task
                    finally:
                        if not cancel_waiter.done():
                            cancel_waiter.cancel()
                            try:
                                await cancel_waiter
                            except asyncio.CancelledError:
                                pass
                if not cancelled:
                    if not isinstance(raw, Mapping):
                        graph_error = "invalid_graph_result"
                    else:
                        graph_result = raw
        except asyncio.CancelledError:
            cancelled = True
        except CheckpointLifecycleError:
            graph_error = "checkpoint_failed"
        except Exception:
            graph_error = "graph_execution_failed"

        if cancelled:
            return await self.handle_disconnect(run_id)

        return await self._finalize_from_graph(
            run_id=run_id,
            thread_id=thread_id,
            user_message_id=user_message_id,
            graph_result=graph_result,
            graph_error=graph_error,
        )

    async def _finalize_from_graph(
        self,
        *,
        run_id: UUID,
        thread_id: str,
        user_message_id: UUID | None,
        graph_result: Mapping[str, Any] | None,
        graph_error: str | None,
    ) -> ChatTurnResult:
        checkpoints_deleted = False
        assistant_message_id: UUID | None = None
        final_text: str | None = None
        pending_approval: dict[str, Any] | None = None
        outcome: RunOutcomeKind = "failed"
        error_code: str | None = graph_error

        if graph_result is not None and result_is_graph_interrupt(graph_result):
            pending_approval = extract_interrupt_payload(graph_result)
            async with self._db.session_scope() as session:
                runs = AgentRunRepository(session)
                run = await runs.get_by_id(run_id)
                if run is None:
                    raise ChatServiceStateError("agent run not found")
                if run.state == AgentRunState.RUNNING.value:
                    run = await runs.mark_interrupted(run.id)
                return await self._snapshot_result(
                    session,
                    run,
                    outcome="interrupted",
                    replayed=False,
                    checkpoints_deleted=False,
                    pending_approval_override=pending_approval,
                )

        if graph_result is not None and graph_error is None:
            run_outcome = graph_result.get("run_outcome")
            err = graph_result.get("error")
            text = graph_result.get("final_assistant_text")
            if isinstance(err, Mapping) and err.get("code"):
                error_code = str(err.get("code"))
            if run_outcome == "completed" and err is None and text is not None:
                try:
                    final_text = _validate_assistant_text(str(text))
                    outcome = "completed"
                    error_code = None
                except ChatServiceValidationError:
                    outcome = "failed"
                    error_code = "invalid_assistant_output"
            elif run_outcome == "failed" or err is not None:
                outcome = "failed"
                if error_code is None:
                    error_code = "run_failed"
            else:
                # Interrupt-less incomplete result.
                if result_is_graph_interrupt(graph_result):
                    outcome = "interrupted"
                else:
                    outcome = "failed"
                    if error_code is None:
                        error_code = "incomplete_run"

        async with self._db.session_scope() as session:
            runs = AgentRunRepository(session)
            conv = ConversationRepository(session)
            tools_repo = ToolExecutionRepository(session)
            run = await runs.get_by_id(run_id)
            if run is None:
                raise ChatServiceStateError("agent run not found")

            # Already terminal (parallel finalize): do not rewrite.
            if run.state in {
                AgentRunState.COMPLETED.value,
                AgentRunState.FAILED.value,
            }:
                return await self._snapshot_result(
                    session,
                    run,
                    outcome="replay",
                    replayed=True,
                    checkpoints_deleted=False,
                )

            if graph_result is not None:
                await self._persist_tool_records(
                    tools_repo,
                    run_id=run_id,
                    graph_result=graph_result,
                )

            if outcome == "completed" and final_text is not None:
                # Final validated assistant message BEFORE checkpoint cleanup.
                try:
                    assistant = await conv.append_message(
                        role=MessageRole.ASSISTANT,
                        content=final_text,
                    )
                    assistant_message_id = assistant.id
                except (ConversationRepositoryError, ConversationMessageError):
                    failed_run = await runs.mark_failed(
                        run_id, error="assistant_persist_failed"
                    )
                    return await self._snapshot_result(
                        session,
                        failed_run,
                        outcome="failed",
                        replayed=False,
                        checkpoints_deleted=False,
                    )
                if run.state == AgentRunState.RUNNING.value:
                    run = await runs.mark_completed(run_id)
                outcome = "completed"
            else:
                if run.state in {
                    AgentRunState.RUNNING.value,
                    AgentRunState.PENDING.value,
                    AgentRunState.INTERRUPTED.value,
                }:
                    run = await runs.mark_failed(
                        run_id,
                        error=error_code or "run_failed",
                    )
                outcome = "failed"

            snapshot = await self._snapshot_result(
                session,
                run,
                outcome=outcome,
                replayed=False,
                checkpoints_deleted=False,
                assistant_message_id=assistant_message_id,
                final_text=final_text,
            )

        if outcome == "completed":
            # Cleanup only after durable assistant + completed state commit.
            try:
                await delete_completed_thread_checkpoints(
                    self._sqlite_path,
                    thread_id,
                )
                checkpoints_deleted = True
            except CheckpointLifecycleError:
                checkpoints_deleted = False
            return ChatTurnResult(
                run_id=snapshot.run_id,
                thread_id=snapshot.thread_id,
                state=snapshot.state,
                outcome=snapshot.outcome,
                user_message_id=snapshot.user_message_id or user_message_id,
                assistant_message_id=snapshot.assistant_message_id,
                final_text=snapshot.final_text,
                error=snapshot.error,
                pending_approval=snapshot.pending_approval,
                replayed=False,
                checkpoints_deleted=checkpoints_deleted,
            )

        return ChatTurnResult(
            run_id=snapshot.run_id,
            thread_id=snapshot.thread_id,
            state=snapshot.state,
            outcome=snapshot.outcome,
            user_message_id=snapshot.user_message_id or user_message_id,
            assistant_message_id=snapshot.assistant_message_id,
            final_text=snapshot.final_text,
            error=snapshot.error,
            pending_approval=snapshot.pending_approval,
            replayed=False,
            checkpoints_deleted=False,
        )

    async def _persist_tool_records(
        self,
        tools_repo: ToolExecutionRepository,
        *,
        run_id: UUID,
        graph_result: Mapping[str, Any],
    ) -> None:
        """Record sanitized tool observability from graph turn messages.

        Never stores ``ToolMessage`` / tool-result bodies, raw arguments, or
        document text. Durable ``arguments_summary`` is restricted to a
        generic allowlisted status token for public SSE mapping.
        """
        messages = graph_result.get("messages_for_this_turn") or ()
        if not isinstance(messages, Sequence):
            return

        # Avoid duplicate tool rows on partial re-finalize: skip if any exist.
        existing = await tools_repo.list_for_run(run_id)
        if existing:
            return

        for item in messages:
            name: str | None = None
            failed = False
            if isinstance(item, ToolMessage):
                name = str(item.name or "tool")
                content = item.content
                text = content if isinstance(content, str) else str(content)
                status = getattr(item, "status", None)
                if status == "error" or (
                    text
                    and (
                        text.startswith("ERROR:")
                        or '"ok": false' in text.lower()
                        or '"ok":false' in text.lower()
                    )
                ):
                    failed = True
            elif isinstance(item, Mapping) and str(item.get("role", "")).lower() == "tool":
                name = str(item.get("name") or "tool")
                content = item.get("content", "")
                text = content if isinstance(content, str) else str(content)
                if text and (
                    text.startswith("ERROR:")
                    or '"ok": false' in text.lower()
                    or '"ok":false' in text.lower()
                ):
                    failed = True
            else:
                continue

            # Tool names from LangGraph must be repository-safe; skip unknowns.
            safe_name = "".join(
                ch if (ch.isalnum() or ch == "_") else "_" for ch in (name or "tool")
            )
            if not safe_name or not safe_name[0].isalpha():
                safe_name = f"t_{safe_name}" if safe_name else "tool"
            safe_name = safe_name[:128]
            try:
                row = await tools_repo.start(
                    agent_run_id=run_id,
                    tool_name=safe_name,
                    arguments_summary=None,
                )
                if failed:
                    await tools_repo.fail(
                        row.id,
                        error_code="TOOL_EXECUTION_FAILED",
                        duration_ms=0,
                    )
                else:
                    # Generic allowlisted status only — never result/argument body.
                    await tools_repo.finish(
                        row.id,
                        duration_ms=0,
                        arguments_summary=PUBLIC_TOOL_OUTCOME_COMPLETED,
                    )
            except (ToolExecutionValidationError, Exception):
                # Observability must not fail the durable turn outcome.
                continue

    async def _snapshot_result(
        self,
        session: AsyncSession,
        run: AgentRun | None,
        *,
        outcome: RunOutcomeKind,
        replayed: bool,
        checkpoints_deleted: bool,
        pending_approval_override: dict[str, Any] | None = None,
        assistant_message_id: UUID | None = None,
        final_text: str | None = None,
    ) -> ChatTurnResult:
        if run is None:
            raise ChatServiceStateError("agent run not found")

        user_message_id = run.message_id
        # Latest assistant message after this user turn (if any).
        if assistant_message_id is None or final_text is None:
            assistant_message_id, final_text = await self._latest_assistant_after(
                session,
                user_message_id=user_message_id,
                known_id=assistant_message_id,
                known_text=final_text,
            )

        pending: dict[str, Any] | None = pending_approval_override
        if pending is None and run.pending_approval:
            pending = {"kind": "approval_required"}

        return ChatTurnResult(
            run_id=run.id,
            thread_id=langgraph_thread_id(run),
            state=run.state,
            outcome=outcome,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            final_text=final_text,
            error=run.error,
            pending_approval=pending,
            replayed=replayed,
            checkpoints_deleted=checkpoints_deleted,
        )

    async def _latest_assistant_after(
        self,
        session: AsyncSession,
        *,
        user_message_id: UUID,
        known_id: UUID | None,
        known_text: str | None,
    ) -> tuple[UUID | None, str | None]:
        if known_id is not None and known_text is not None:
            return known_id, known_text

        user_msg = await session.get(ChatMessage, user_message_id)
        if user_msg is None:
            return known_id, known_text

        result = await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id == user_msg.conversation_id,
                ChatMessage.role == MessageRole.ASSISTANT.value,
                ChatMessage.created_at >= user_msg.created_at,
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return known_id, known_text
        return row.id, row.content


async def count_messages(session: AsyncSession) -> int:
    """Test/helper: total chat_messages rows."""
    result = await session.execute(select(func.count()).select_from(ChatMessage))
    return int(result.scalar_one())


async def count_tool_executions(session: AsyncSession, run_id: UUID) -> int:
    """Test/helper: tool_executions for one run."""
    result = await session.execute(
        select(func.count())
        .select_from(ToolExecution)
        .where(ToolExecution.agent_run_id == run_id)
    )
    return int(result.scalar_one())


__all__ = [
    "ChatService",
    "ChatServiceError",
    "ChatServiceStateError",
    "ChatServiceValidationError",
    "ChatTurnResult",
    "count_messages",
    "count_tool_executions",
]
