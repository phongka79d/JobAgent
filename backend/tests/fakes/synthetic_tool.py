"""Test-only synthetic interrupting tool (never production-registered).

Uses LangGraph ``interrupt()`` to pause mid-tool, keeps a durable tool row at
``running`` until resume, then applies one side effect and one terminal
``ToolResult``. Side-effect free except for the explicit counter used by
integration tests to prove single invocation across a request boundary.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from time import perf_counter
from typing import Annotated, Any

from app.db.models.chat import (
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
    TOOL_EXECUTION_STATUS_PENDING,
    TOOL_EXECUTION_STATUS_RUNNING,
)
from app.repositories import tool_executions as tool_repo
from app.schemas.tools import ToolResult
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Approval kind for the compact projection (generic; not a domain workflow).
SYNTHETIC_APPROVAL_KIND: str = "synthetic_approval"
SYNTHETIC_TOOL_NAME: str = "synthetic_interrupt"
SYNTHETIC_ALLOWED_ACTIONS: tuple[str, str] = ("approve", "reject")


def build_approval_projection(
    *,
    tool_call_id: str,
    card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact ``pending_approval`` / ``approval_required`` projection."""
    return {
        "kind": SYNTHETIC_APPROVAL_KIND,
        "allowed_actions": list(SYNTHETIC_ALLOWED_ACTIONS),
        "card": {
            "tool_name": SYNTHETIC_TOOL_NAME,
            "tool_call_id": tool_call_id,
            **(card or {}),
        },
    }


def build_synthetic_interrupt_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    side_effect_counter: MutableMapping[str, int],
    tool_name: str = SYNTHETIC_TOOL_NAME,
) -> Any:
    """Build a LangChain tool that interrupts, then finishes once on resume.

    Parameters
    ----------
    session_factory:
        Short async sessions for durable get-or-create / terminal store only.
        Never held open across ``interrupt()``.
    side_effect_counter:
        Mutable map; ``side_effect_counter['n']`` increments exactly once when
        the side effect runs after resume (not before interrupt returns).
    """
    if "n" not in side_effect_counter:
        side_effect_counter["n"] = 0

    @tool(tool_name)
    async def synthetic_interrupt(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
    ) -> dict[str, Any]:
        """Pause for a synthetic approval decision, then finish once."""
        run_id = state.get("run_id")
        if not isinstance(run_id, str) or run_id.strip() == "":
            return ToolResult(
                ok=False,
                code="SYNTHETIC_MISSING_RUN_ID",
                summary="synthetic tool requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        # Claim durable row before interrupt; stay running across the pause.
        async with session_factory() as session:
            row, _created = await tool_repo.get_or_create_pending(
                session,
                run_id=run_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments_summary_json={"synthetic": True},
            )
            if row.status in (
                TOOL_EXECUTION_STATUS_COMPLETED,
                TOOL_EXECUTION_STATUS_FAILED,
            ):
                # Exact identity replay — no second side effect.
                stored = tool_repo.load_stored_result(row)
                await session.commit()
                return stored.model_dump(mode="json")
            if row.status == TOOL_EXECUTION_STATUS_PENDING:
                await tool_repo.mark_running(session, row.id)
            elif row.status != TOOL_EXECUTION_STATUS_RUNNING:
                await session.rollback()
                return ToolResult(
                    ok=False,
                    code="SYNTHETIC_BAD_STATUS",
                    summary=f"unexpected tool status {row.status!r}",
                    data=None,
                ).model_dump(mode="json")
            execution_id = row.id
            await session.commit()

        # Pause before any side effect (checkpoint retained across request).
        decision = interrupt(
            build_approval_projection(tool_call_id=tool_call_id)
        )

        started = perf_counter()
        # Single side effect only after interrupt returns a decision.
        side_effect_counter["n"] = int(side_effect_counter.get("n", 0)) + 1
        action = decision if isinstance(decision, str) else str(decision)

        if action == "approve":
            result = ToolResult(
                ok=True,
                code=None,
                summary="synthetic approval accepted",
                data={"action": "approve", "committed": True},
            )
        elif action == "reject":
            result = ToolResult(
                ok=True,
                code=None,
                summary="synthetic approval rejected without commit",
                data={"action": "reject", "committed": False},
            )
        else:
            result = ToolResult(
                ok=False,
                code="SYNTHETIC_INVALID_DECISION",
                summary=f"unsupported synthetic decision {action!r}",
                data={"action": action},
            )
        duration_ms = max(0, int((perf_counter() - started) * 1000))

        async with session_factory() as session:
            row = await tool_repo.get_by_id(session, execution_id)
            if row is None:
                await session.rollback()
                return result.model_dump(mode="json")
            if row.status in (
                TOOL_EXECUTION_STATUS_COMPLETED,
                TOOL_EXECUTION_STATUS_FAILED,
            ):
                stored = tool_repo.load_stored_result(row)
                await session.commit()
                return stored.model_dump(mode="json")
            if result.ok:
                await tool_repo.complete_execution(
                    session,
                    execution_id,
                    result=result,
                    duration_ms=duration_ms,
                )
            else:
                await tool_repo.fail_execution(
                    session,
                    execution_id,
                    result=result,
                    duration_ms=duration_ms,
                )
            await session.commit()

        return result.model_dump(mode="json")

    return synthetic_interrupt


__all__ = [
    "SYNTHETIC_ALLOWED_ACTIONS",
    "SYNTHETIC_APPROVAL_KIND",
    "SYNTHETIC_TOOL_NAME",
    "build_approval_projection",
    "build_synthetic_interrupt_tool",
]
