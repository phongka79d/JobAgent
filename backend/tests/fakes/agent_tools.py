"""Synthetic Agent tools and decision fakes for graph tests only.

These tools must never be registered in the production default registry or
application startup path. Domain tools (Master §13) are also not implemented
here — only transport/loop proof helpers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import StructuredTool

from app.services.shopaikey_chat import DecisionResult, ObservedToolCall


def make_echo_label_tool(*, fail: bool = False) -> StructuredTool:
    """Deterministic synthetic tool used only in tests."""

    def _echo(label: str) -> str:
        if fail:
            return f'ERROR: structured failure for {label}; {{"ok": false}}'
        return f"echo:{label}"

    return StructuredTool.from_function(
        func=_echo,
        name="echo_label",
        description="Synthetic test tool that echoes a short label.",
    )


def make_counting_tool(calls: list[str]) -> StructuredTool:
    """Synthetic tool that records each invocation for loop-limit tests."""

    def _tick(label: str) -> str:
        calls.append(label)
        return f"tick:{label}:{len(calls)}"

    return StructuredTool.from_function(
        func=_tick,
        name="count_tick",
        description="Synthetic counter tool for iteration tests.",
    )


def make_failing_tool() -> StructuredTool:
    """Synthetic tool that raises; ToolNode should surface a structured error."""

    def _boom(label: str) -> str:
        raise RuntimeError(f"synthetic boom: {label}")

    return StructuredTool.from_function(
        func=_boom,
        name="fail_tool",
        description="Synthetic tool that always raises.",
    )


def make_approval_request_tool() -> StructuredTool:
    """Synthetic tool that stages a graph-level approval interrupt.

    Returns the production ``APPROVAL_REQUIRED:`` marker so the controlled
    graph ``await_approval`` node calls ``request_human_approval`` / interrupt.
    Not registered in the production default registry.
    """

    def _propose(label: str) -> str:
        # Marker consumed by app.agent.graph._approval_request_from_tool_messages.
        return (
            "APPROVAL_REQUIRED:"
            f'{{"kind":"approval_required","tool":"propose_action","label":"{label}"}}'
        )

    return StructuredTool.from_function(
        func=_propose,
        name="propose_action",
        description="Synthetic tool that requests human approval before commit.",
    )


def make_approval_gated_commit_tool() -> StructuredTool:
    """Synthetic write tool that calls the production interrupt helper inline.

    Exercises Master §12.1 guarded-commit interrupt inside ToolNode using the
    production ``request_human_approval`` seam (not a separate test graph).
    """

    def _commit(label: str) -> str:
        from app.agent.graph import request_human_approval

        value = request_human_approval(
            {
                "kind": "approval_required",
                "tool": "gated_commit",
                "label": label,
            }
        )
        return f"committed:{value}:{label}"

    return StructuredTool.from_function(
        func=_commit,
        name="gated_commit",
        description="Synthetic commit tool gated by production approval interrupt.",
    )


@dataclass
class ScriptedDecision:
    """Fake decision port: scripted sequence of DecisionResult values.

    After the script is exhausted, returns a final no-tool completion so the
    graph can terminate. Never performs network I/O.
    """

    results: list[DecisionResult] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def invoke_decision(
        self,
        messages: Sequence[object],
        *,
        tools: Sequence[object] | None = None,
    ) -> DecisionResult:
        self.calls.append(
            {
                "message_count": len(list(messages)),
                "tool_count": len(list(tools or ())),
            }
        )
        if self._index < len(self.results):
            result = self.results[self._index]
            self._index += 1
            return result
        return DecisionResult(
            content="done",
            tool_calls=(),
            response_model="fake-model",
        )


def tool_call(
    name: str,
    *,
    arguments: dict[str, Any] | None = None,
    tool_call_id: str | None = None,
) -> ObservedToolCall:
    return ObservedToolCall(
        name=name,
        arguments=arguments or {},
        tool_call_id=tool_call_id,
    )


def decision_with_tool(
    name: str,
    *,
    label: str = "x",
    tool_call_id: str | None = None,
    content: str = "",
) -> DecisionResult:
    return DecisionResult(
        content=content,
        tool_calls=(
            tool_call(
                name,
                arguments={"label": label},
                tool_call_id=tool_call_id or f"call_{name}_{label}",
            ),
        ),
        response_model="fake-model",
    )


def decision_text(content: str) -> DecisionResult:
    return DecisionResult(
        content=content,
        tool_calls=(),
        response_model="fake-model",
    )


def scripted_tool_then_done(
    *,
    tool_name: str = "echo_label",
    labels: Sequence[str],
) -> ScriptedDecision:
    """N tool decisions (one call each) followed by final text."""
    results = [
        decision_with_tool(tool_name, label=label, tool_call_id=f"c{i}")
        for i, label in enumerate(labels)
    ]
    results.append(decision_text("finished after tools"))
    return ScriptedDecision(results=results)
