"""Tests for the single ToolNode graph, loop guard, and error boundary."""

from __future__ import annotations

import ast
from pathlib import Path

from app.agent.graph import (
    DEFAULT_TOOL_LOOP_LIMIT,
    NODE_AGENT_DECISION,
    NODE_AWAIT_APPROVAL,
    NODE_CLEANUP_CHECKPOINT,
    NODE_INCREMENT_ITERATION,
    NODE_LOAD_CONTEXT,
    NODE_PERSIST_RESPONSE,
    NODE_TOOLS,
    TOOL_EXECUTION_FAILED,
    TOOL_LOOP_LIMIT_EXCEEDED,
    build_agent_graph,
    has_successful_run_outcome,
    initial_graph_state,
)
from app.agent.prompt import DOMAIN_REDIRECT_MESSAGE
from app.tools.registry import ToolRegistry
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from tests.fakes.agent_tools import (
    ScriptedDecision,
    decision_text,
    decision_with_tool,
    make_counting_tool,
    make_echo_label_tool,
    make_failing_tool,
    scripted_tool_then_done,
)


def _nodes(graph: object) -> set[str]:
    # CompiledStateGraph exposes builder nodes via get_graph / nodes.
    nodes = getattr(graph, "nodes", None)
    if isinstance(nodes, dict):
        return set(nodes) - {"__start__", "__end__"}
    inner = getattr(graph, "builder", None) or getattr(graph, "_graph", None)
    if inner is not None and hasattr(inner, "nodes"):
        return set(inner.nodes) - {"__start__", "__end__"}
    raise AssertionError("cannot inspect compiled graph nodes")


def test_single_stategraph_topology_nodes() -> None:
    graph = build_agent_graph(
        tools=[make_echo_label_tool()],
        decision=ScriptedDecision([decision_text("hello")]),
    )
    nodes = _nodes(graph)
    assert NODE_LOAD_CONTEXT in nodes
    assert NODE_AGENT_DECISION in nodes
    assert NODE_TOOLS in nodes
    assert NODE_INCREMENT_ITERATION in nodes
    assert NODE_AWAIT_APPROVAL in nodes
    assert NODE_PERSIST_RESPONSE in nodes
    assert NODE_CLEANUP_CHECKPOINT in nodes
    # No multi-agent / handoff nodes.
    assert "handoff" not in nodes
    assert "supervisor" not in nodes
    assert "worker" not in nodes


def test_source_has_one_stategraph_and_one_toolnode() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "app" / "agent" / "graph.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    stategraph_calls = 0
    toolnode_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "StateGraph":
                stategraph_calls += 1
            if name == "ToolNode":
                toolnode_calls += 1
    assert stategraph_calls == 1
    assert toolnode_calls == 1
    assert "StateGraph" in source
    assert "ToolNode" in source
    # Ensure we actually reference the prebuilt ToolNode class.
    assert ToolNode is not None
    assert StateGraph is not None


def test_no_tool_completion() -> None:
    decision = ScriptedDecision([decision_text("plain answer")])
    graph = build_agent_graph(tools=[make_echo_label_tool()], decision=decision)
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Help me improve my CV summary",
        )
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 0
    assert out["final_assistant_text"] == "plain answer"
    assert out["run_outcome"] == "completed"
    assert out["response_persisted"] is True
    assert out["checkpoint_cleaned"] is True
    assert has_successful_run_outcome(out)
    assert decision.calls  # model was invoked once


def test_one_tool_then_completion() -> None:
    decision = scripted_tool_then_done(labels=["a"])
    tool = make_echo_label_tool()
    graph = build_agent_graph(tools=[tool], decision=decision)
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Match my profile to jobs",
        )
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 1
    assert out["final_assistant_text"] == "finished after tools"
    assert has_successful_run_outcome(out)
    # Tool result present in turn messages.
    contents = [getattr(m, "content", None) for m in out["messages_for_this_turn"]]
    assert any(c == "echo:a" for c in contents)


def test_multiple_tools_sequential() -> None:
    decision = scripted_tool_then_done(labels=["a", "b", "c"])
    calls: list[str] = []
    graph = build_agent_graph(tools=[make_counting_tool(calls)], decision=decision)
    # Override scripted tool name to count_tick
    decision.results = [
        decision_with_tool("count_tick", label="a", tool_call_id="c0"),
        decision_with_tool("count_tick", label="b", tool_call_id="c1"),
        decision_with_tool("count_tick", label="c", tool_call_id="c2"),
        decision_text("all done"),
    ]
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Update job preferences and match jobs",
        )
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 3
    assert calls == ["a", "b", "c"]
    assert out["final_assistant_text"] == "all done"
    assert has_successful_run_outcome(out)


def test_exactly_six_tool_iterations_allowed() -> None:
    labels = [f"t{i}" for i in range(DEFAULT_TOOL_LOOP_LIMIT)]
    calls: list[str] = []
    results = [
        decision_with_tool("count_tick", label=label, tool_call_id=f"c{i}")
        for i, label in enumerate(labels)
    ]
    results.append(decision_text("ok at six"))
    decision = ScriptedDecision(results=results)
    graph = build_agent_graph(
        tools=[make_counting_tool(calls)],
        decision=decision,
        tool_loop_limit=DEFAULT_TOOL_LOOP_LIMIT,
    )
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Run job matching tools for skill gaps",
        )
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 6
    assert len(calls) == 6
    assert out["run_outcome"] == "completed"
    assert has_successful_run_outcome(out)


def test_seventh_tool_blocked_with_loop_limit_code() -> None:
    """Stop before a seventh tool execution with TOOL_LOOP_LIMIT_EXCEEDED."""
    calls: list[str] = []
    # Script asks for 7 tool rounds; guard must block the 7th before ToolNode.
    results = [
        decision_with_tool("count_tick", label=f"t{i}", tool_call_id=f"c{i}")
        for i in range(7)
    ]
    results.append(decision_text("should not complete as success from tools"))
    decision = ScriptedDecision(results=results)
    graph = build_agent_graph(
        tools=[make_counting_tool(calls)],
        decision=decision,
        tool_loop_limit=6,
    )
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Match jobs with many tool steps",
        )
    )
    assert out["error"] is not None
    assert out["error"]["code"] == TOOL_LOOP_LIMIT_EXCEEDED
    assert out["tool_iteration_count"] == 6
    assert len(calls) == 6  # seventh never executed
    assert out["run_outcome"] == "failed"
    assert not has_successful_run_outcome(out)
    assert out["final_assistant_text"] is None


def test_structured_tool_failure_not_converted_to_success() -> None:
    decision = ScriptedDecision(
        results=[
            decision_with_tool("fail_tool", label="x", tool_call_id="c0"),
            # Malicious follow-up that would claim success if the graph allowed it.
            decision_text("Everything succeeded perfectly"),
        ]
    )
    graph = build_agent_graph(tools=[make_failing_tool()], decision=decision)
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Save a job description URL",
        )
    )
    assert out["error"] is not None
    assert out["error"]["code"] == TOOL_EXECUTION_FAILED
    assert out["run_outcome"] == "failed"
    assert not has_successful_run_outcome(out)
    assert out["final_assistant_text"] is None
    # Scripted success text must not become the terminal success outcome.
    assert out.get("final_assistant_text") != "Everything succeeded perfectly"
    # Decision should not be re-invoked after structured failure to invent success.
    # (failure is detected after tools; next agent_decision short-circuits)
    assert len(decision.calls) == 1


def test_structured_failure_payload_from_tool_return() -> None:
    decision = ScriptedDecision(
        results=[
            decision_with_tool("echo_label", label="bad", tool_call_id="c0"),
            decision_text("pretend ok"),
        ]
    )
    graph = build_agent_graph(
        tools=[make_echo_label_tool(fail=True)],
        decision=decision,
    )
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Parse my CV attachment",
        )
    )
    assert out["error"] is not None
    assert out["error"]["code"] == TOOL_EXECUTION_FAILED
    assert not has_successful_run_outcome(out)


def test_unrelated_message_redirect_zero_tools() -> None:
    decision = ScriptedDecision([decision_text("should not be used")])
    graph = build_agent_graph(tools=[make_echo_label_tool()], decision=decision)
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="What is the weather in Paris today?",
        )
    )
    assert out["domain_redirect"] is True
    assert out["final_assistant_text"] == DOMAIN_REDIRECT_MESSAGE
    assert out["tool_iteration_count"] == 0
    assert decision.calls == []  # no provider decision
    assert has_successful_run_outcome(out)


def test_registry_injection_empty_production_default() -> None:
    registry = ToolRegistry()
    decision = ScriptedDecision([decision_text("no tools bound")])
    graph = build_agent_graph(registry=registry, decision=decision)
    out = graph.invoke(
        initial_graph_state(
            conversation_id="c1",
            run_id="r1",
            user_text="Tell me about skill gaps for my profile",
        )
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 0
    # Decision saw zero tools from empty registry.
    assert decision.calls[0]["tool_count"] == 0


def test_default_tool_loop_limit_constant() -> None:
    assert DEFAULT_TOOL_LOOP_LIMIT == 6
    assert TOOL_LOOP_LIMIT_EXCEEDED == "TOOL_LOOP_LIMIT_EXCEEDED"
