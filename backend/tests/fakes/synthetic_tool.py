"""Test-only synthetic interrupting tool (never production-registered).

Uses LangGraph ``interrupt()`` to pause mid-tool, keeps a durable tool row at
``running`` until resume, then applies one side effect and one terminal
``ToolResult``. Side-effect free except for the explicit counter used by
integration tests to prove single invocation across a request boundary.

Durable transitions and request-scoped ``tool_status`` publication go through
the shared :func:`~app.services.tool_execution.execute_tool` owner (same seam
as production tools). No parallel executor or status vocabulary.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Annotated, Any

from app.schemas.tools import ToolResult
from app.services.tool_execution import execute_tool
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

        async def _invoke() -> ToolResult:
            # Pause before any side effect (checkpoint retained across request).
            decision = interrupt(
                build_approval_projection(tool_call_id=tool_call_id)
            )

            # Single side effect only after interrupt returns a decision.
            side_effect_counter["n"] = int(side_effect_counter.get("n", 0)) + 1
            action = decision if isinstance(decision, str) else str(decision)

            if action == "approve":
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="synthetic approval accepted",
                    data={"action": "approve", "committed": True},
                )
            if action == "reject":
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="synthetic approval rejected without commit",
                    data={"action": "reject", "committed": False},
                )
            return ToolResult(
                ok=False,
                code="SYNTHETIC_INVALID_DECISION",
                summary=f"unsupported synthetic decision {action!r}",
                data={"action": action},
            )

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            invoke=_invoke,
            arguments_summary_json={"synthetic": True},
            session_factory=session_factory,
            allow_running_reentry=True,
        )
        return result.model_dump(mode="json")

    return synthetic_interrupt


__all__ = [
    "SYNTHETIC_ALLOWED_ACTIONS",
    "SYNTHETIC_APPROVAL_KIND",
    "SYNTHETIC_TOOL_NAME",
    "build_approval_projection",
    "build_synthetic_interrupt_tool",
]
