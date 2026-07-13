"""Unit tests for the injected-registry one-decision/one-ToolNode graph."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from app.agent.graph import (
    DECISION_NODE_NAME,
    ERROR_TOOL_LOOP_LIMIT_EXCEEDED,
    MESSAGES_KEY,
    TOOLS_NODE_NAME,
    AgentGraphBundle,
    build_agent_graph,
    initial_graph_state,
)
from app.agent.state import AGENT_STATE_FIELDS
from app.tools.registry import ToolRegistry, production_registry
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from tests.fakes.fake_chat_model import FakeChatModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_AGENT = BACKEND_ROOT / "app" / "agent"
APP_TOOLS = BACKEND_ROOT / "app" / "tools"
RUN_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


@tool
def echo_tool(text: str) -> str:
    """Echo the provided text (test-only injected tool)."""
    return f"echo:{text}"


@tool
def fail_tool(reason: str = "boom") -> dict[str, Any]:
    """Return a failed ToolResult-shaped payload (test-only)."""
    return {
        "ok": False,
        "code": "TEST_TOOL_FAILED",
        "summary": f"Tool failed: {reason}",
        "data": None,
    }


@tool
def counter_tool() -> str:
    """Side-effect-free counter tool for loop-limit tests."""
    return "tick"


def _ai_text(content: str) -> AIMessage:
    return AIMessage(content=content)


def _ai_tool_call(
    name: str,
    args: dict[str, Any],
    call_id: str = "call-1",
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def _bundle(
    model: FakeChatModel,
    tools: list[Any] | None = None,
    *,
    tool_loop_limit: int = 6,
) -> AgentGraphBundle:
    registry = ToolRegistry(tools or [])
    return build_agent_graph(
        model=model,
        registry=registry,
        tool_loop_limit=tool_loop_limit,
    )


# ---------------------------------------------------------------------------
# Topology / registry
# ---------------------------------------------------------------------------


def test_production_registry_is_empty() -> None:
    reg = production_registry()
    assert reg.is_empty()
    assert reg.list_tools() == []
    assert reg.tool_names() == []


def test_graph_has_exactly_one_decision_and_one_tool_node() -> None:
    model = FakeChatModel(responses=[_ai_text("hello")])
    bundle = _bundle(model, [echo_tool])
    assert isinstance(bundle.tool_node, ToolNode)
    assert isinstance(bundle.tool_node, ToolNode)
    assert bundle.decision_node_name == DECISION_NODE_NAME
    assert bundle.tools_node_name == TOOLS_NODE_NAME
    assert bundle.tool_loop_limit == 6

    # Compiled graph exposes agent + tools (+ start/end handled by runtime).
    graph_nodes = set(bundle.compiled.get_graph().nodes)
    assert DECISION_NODE_NAME in graph_nodes
    assert TOOLS_NODE_NAME in graph_nodes
    # No extra application nodes beyond the single decision + single ToolNode.
    app_nodes = {
        n
        for n in graph_nodes
        if n not in {"__start__", "__end__", "START", "END"}
    }
    assert app_nodes == {DECISION_NODE_NAME, TOOLS_NODE_NAME}


def test_initial_graph_state_matches_agent_state_keys() -> None:
    state = initial_graph_state(run_id=RUN_ID, user_text="hi")
    assert set(state) == AGENT_STATE_FIELDS
    assert state["conversation_id"] == "main"
    assert state["run_id"] == RUN_ID
    assert state["tool_iteration_count"] == 0
    assert state["error"] is None
    assert state["candidate_context"] == []
    assert isinstance(state["messages_for_this_turn"][0], HumanMessage)


# ---------------------------------------------------------------------------
# Direct answer / tool round-trip
# ---------------------------------------------------------------------------


def test_direct_response_terminates_without_tools() -> None:
    model = FakeChatModel(responses=[_ai_text("Hello! How can I help?")])
    bundle = _bundle(model, tools=[])  # empty registry path
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="Xin chào")
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 0
    assert model.invoke_count == 1
    last = out[MESSAGES_KEY][-1]
    assert isinstance(last, AIMessage)
    assert last.content == "Hello! How can I help?"
    assert not (last.tool_calls or [])
    # No ToolMessages on a pure direct answer.
    assert not any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])


def test_tool_round_trip_then_final_answer() -> None:
    model = FakeChatModel(
        responses=[
            _ai_tool_call("echo_tool", {"text": "abc"}, call_id="c1"),
            _ai_text("You said abc"),
        ]
    )
    bundle = _bundle(model, [echo_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="echo abc")
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 2
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert "echo:abc" in str(tool_msgs[0].content)
    assert out[MESSAGES_KEY][-1].content == "You said abc"


def test_failed_tool_result_reaches_next_model_input() -> None:
    """Failed ToolResult content is visible to the next decision pass."""
    model = FakeChatModel(
        responses=[
            _ai_tool_call("fail_tool", {"reason": "nope"}, call_id="f1"),
            _ai_text("The tool failed truthfully: TEST_TOOL_FAILED"),
        ]
    )
    bundle = _bundle(model, [fail_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="please fail")
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 2
    # Second model call must include the failed tool payload (truthful input).
    second_prompt = model.call_log[1]
    joined = " ".join(
        m.content if isinstance(m.content, str) else str(m.content)
        for m in second_prompt
    )
    assert "TEST_TOOL_FAILED" in joined
    assert "ok" in joined.lower() or "failed" in joined.lower()
    assert "The tool failed truthfully" in str(out[MESSAGES_KEY][-1].content)


def test_injected_tools_without_changing_graph_construction() -> None:
    model = FakeChatModel(
        responses=[
            _ai_tool_call("echo_tool", {"text": "x"}, call_id="c1"),
            _ai_text("done"),
        ]
    )
    # Same factory; only registry content differs from production empty.
    empty = build_agent_graph(
        model=FakeChatModel(responses=[_ai_text("direct")]),
        registry=production_registry(),
    )
    injected = build_agent_graph(
        model=model,
        registry=ToolRegistry([echo_tool]),
    )
    assert empty.decision_node_name == injected.decision_node_name
    assert empty.tools_node_name == injected.tools_node_name
    assert isinstance(empty.tool_node, ToolNode)
    assert isinstance(injected.tool_node, ToolNode)
    assert empty.registry.is_empty()
    assert not injected.registry.is_empty()
    assert injected.registry.tool_names() == ["echo_tool"]


# ---------------------------------------------------------------------------
# Six-pass guard
# ---------------------------------------------------------------------------


def test_six_tool_passes_allowed_then_direct_answer() -> None:
    """Exactly six ToolNode passes succeed when the seventh LLM turn is text."""
    responses: list[AIMessage] = [
        _ai_tool_call("counter_tool", {}, call_id=f"c{i}") for i in range(1, 7)
    ]
    responses.append(_ai_text("finished after six"))
    model = FakeChatModel(responses=responses)
    bundle = _bundle(model, [counter_tool], tool_loop_limit=6)
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="loop")
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 6
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 6
    assert out[MESSAGES_KEY][-1].content == "finished after six"
    assert model.invoke_count == 7  # 6 tool decisions + 1 final


def test_seventh_tool_pass_emits_stable_controlled_failure() -> None:
    """When a seventh pass would exceed limit=6, fail without running tools."""
    responses = [
        _ai_tool_call("counter_tool", {}, call_id=f"c{i}") for i in range(1, 8)
    ]
    model = FakeChatModel(responses=responses)
    bundle = _bundle(model, [counter_tool], tool_loop_limit=6)
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="overflow")
    )
    assert out["error"] == ERROR_TOOL_LOOP_LIMIT_EXCEEDED
    assert out["error"] == "TOOL_LOOP_LIMIT_EXCEEDED"
    # Six successful tool passes only — seventh never executes.
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 6
    assert out["tool_iteration_count"] == 6
    # Model was asked for a 7th decision (which requested tools) then stopped.
    assert model.invoke_count == 7


def test_custom_limit_of_one() -> None:
    model = FakeChatModel(
        responses=[
            _ai_tool_call("counter_tool", {}, call_id="c1"),
            _ai_tool_call("counter_tool", {}, call_id="c2"),
        ]
    )
    bundle = _bundle(model, [counter_tool], tool_loop_limit=1)
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="once")
    )
    assert out["error"] == ERROR_TOOL_LOOP_LIMIT_EXCEEDED
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert out["tool_iteration_count"] == 1


# ---------------------------------------------------------------------------
# No persistence / transport / synthetic leakage in shipped modules
# ---------------------------------------------------------------------------


def _source_tree_text(root: Path) -> str:
    parts: list[str] = []
    for path in sorted(root.rglob("*.py")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_graph_and_registry_source_has_no_transport_or_persistence() -> None:
    graph_path = APP_AGENT / "graph.py"
    registry_path = APP_TOOLS / "registry.py"
    graph_text = graph_path.read_text(encoding="utf-8")
    registry_text = registry_path.read_text(encoding="utf-8")
    combined = graph_text + "\n" + registry_text

    # No FastAPI / router wiring in graph or registry modules.
    assert "include_router" not in combined
    assert "APIRouter" not in combined
    assert "from fastapi" not in combined
    assert "import fastapi" not in combined

    # No session/persistence in graph or registry (durable work is services).
    for banned in (
        "AsyncSession",
        "session_scope",
        "sqlalchemy",
        "create_engine",
        "execute_tool",
    ):
        assert banned not in graph_text
        assert banned not in registry_text

    # Production registry ships no test-only or domain tool registration.
    assert "production_registry" in registry_text
    assert "ToolRegistry()" in registry_text
    # Ensure list_tools default is empty construction, not a preloaded catalog.
    assert "propose_profile" not in registry_text
    assert "match_jobs" not in registry_text


def test_single_stategraph_and_toolnode_in_graph_module() -> None:
    graph_path = APP_AGENT / "graph.py"
    tree = ast.parse(graph_path.read_text(encoding="utf-8"))
    stategraph_calls = 0
    toolnode_bases: list[str] = []
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
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name == "ToolNode":
                    toolnode_bases.append(node.name)
    assert stategraph_calls == 1
    # Exactly one ToolNode subclass used for the guarded tools node.
    assert toolnode_bases == ["_CountingToolNode"]


def test_graph_nodes_do_not_import_db_or_api() -> None:
    """Import graph and confirm it does not pull FastAPI/SQLAlchemy sessions."""
    import app.agent.graph as graph_mod
    import app.tools.registry as reg_mod

    for mod in (graph_mod, reg_mod):
        names = set(dir(mod))
        assert "AsyncSession" not in names
        assert "APIRouter" not in names
        assert "include_router" not in names


# ---------------------------------------------------------------------------
# System prompt uses injected tool names only
# ---------------------------------------------------------------------------


def test_empty_registry_model_prompt_has_no_tools() -> None:
    model = FakeChatModel(responses=[_ai_text("ok")])
    bundle = build_agent_graph(model=model, registry=production_registry())
    bundle.compiled.invoke(initial_graph_state(run_id=RUN_ID, user_text="hi"))
    assert model.invoke_count == 1
    system = model.call_log[0][0]
    assert "Registered JobAgent tools: none" in str(system.content)
    assert "echo_tool" not in str(system.content)
    assert "synthetic" not in str(system.content).lower()
