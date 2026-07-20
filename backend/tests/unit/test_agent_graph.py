"""Unit tests for the injected-registry one-decision/one-ToolNode graph."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from app.agent.graph import (
    DECISION_NODE_NAME,
    ERROR_TOOL_LOOP_LIMIT_EXCEEDED,
    MESSAGES_KEY,
    NAMED_SAVE_JOB_NO_ACTION_TEXT,
    PASSIVE_JD_NO_CONFIRMATION_TEXT,
    PASSIVE_JD_REPAIR_TOOL_CHOICE,
    TOOLS_NODE_NAME,
    AgentGraphBundle,
    _build_model_messages,
    _format_attachment_ids_block,
    build_agent_graph,
    initial_graph_state,
)
from app.agent.state import AGENT_STATE_FIELDS
from app.services import job_save_confirmation as conf
from app.tools.jobs import SAVE_JOB_NAME, save_job_openai_tool_schema
from app.tools.registry import ToolRegistry, production_registry
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from tests.fakes.fake_chat_model import (
    CANONICAL_SAVE_JOB_TOOL_CHOICE,
    FakeChatModel,
    PassiveJdBindingAwareFake,
)

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


# F-04 exact initiating request (failure report reproduction text).
F04_NAMED_SAVE_JOB_REQUEST = (
    "Use save_job once again with the exact URL https://example.com and "
    "report whether the existing Job is reused. Do not call other tools."
)

_SAVE_JOB_RETURNED_PAYLOAD: dict[str, Any] = {
    "ok": True,
    "code": None,
    "summary": "Returned existing job for exact content match (processed/full)",
    "data": {
        "job_id": "job-dup-1",
        "title": "Backend Engineer",
        "company": "Acme",
        "source_url": "https://example.com",
        "processing_status": "processed",
        "jd_quality": "full",
        "outcome": "returned",
        "sqlite_committed": True,
        "sync_ok": True,
        "failure_code": None,
        "rebuild_instruction": None,
        "paste_instruction": None,
    },
}


@tool(SAVE_JOB_NAME)
def save_job_tool(
    url: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Test-only save_job returning a validated returned ToolResult shape."""
    del text
    payload = dict(_SAVE_JOB_RETURNED_PAYLOAD)
    data = dict(payload["data"])  # type: ignore[arg-type]
    data["source_url"] = url
    payload["data"] = data
    return payload


@tool(SAVE_JOB_NAME)
def save_job_created_tool(
    url: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Test-only save_job returning created outcome."""
    del text
    return {
        "ok": True,
        "code": None,
        "summary": "Saved job description (processed/full)",
        "data": {
            "job_id": "job-new-1",
            "title": "Backend Engineer",
            "company": "Acme",
            "source_url": url,
            "processing_status": "processed",
            "jd_quality": "full",
            "outcome": "created",
            "sqlite_committed": True,
            "sync_ok": True,
        },
    }


_SAVE_JOB_CANCEL_PAYLOAD: dict[str, Any] = {
    "ok": True,
    "code": None,
    "summary": conf.CANCEL_SUMMARY,
    "data": {
        "committed": False,
        "outcome": "cancelled",
    },
}


@tool(SAVE_JOB_NAME)
def save_job_current_message_tool(
    url: str | None = None,
    text: str | None = None,
    source: str | None = None,
    preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Test-only save_job accepting current_message source."""
    del url, text, preview
    if source == "current_message":
        return {
            "ok": True,
            "code": None,
            "summary": "Saved job description (processed/full)",
            "data": {
                "job_id": "job-cm-1",
                "title": "Backend Engineer",
                "company": "Acme",
                "source_url": None,
                "processing_status": "processed",
                "jd_quality": "full",
                "outcome": "created",
                "sqlite_committed": True,
                "sync_ok": True,
            },
        }
    return dict(_SAVE_JOB_RETURNED_PAYLOAD)


@tool(SAVE_JOB_NAME)
def save_job_cancel_tool(
    url: str | None = None,
    text: str | None = None,
    source: str | None = None,
    preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Test-only save_job that always returns successful cancellation."""
    del url, text, source, preview
    return dict(_SAVE_JOB_CANCEL_PAYLOAD)


def _obvious_passive_jd(
    *,
    markers: tuple[str, str] = ("responsibilities", "requirements"),
) -> str:
    """Obvious structured JD meeting 01A thresholds (reuse pure predicates)."""
    lines = [markers[0], markers[1], "line three", "line four", "line five"]
    body = "\n".join(lines)
    while conf._non_whitespace_char_count(body) < conf.OBVIOUS_JD_MIN_NON_WS_CHARS:  # noqa: SLF001
        body += "x"
    assert conf.message_is_obvious_jd(body)
    assert not conf.message_has_clear_opt_out(body)
    assert not conf.message_is_sole_http_url(body)
    return body


EXPLICIT_DIRECT_TEXT = (
    "Job title: Synthetic API Engineer. Company: Plan13 Labs. "
    "Responsibilities: build local APIs and deterministic tests. "
    "Requirements: Python, FastAPI, SQL, and Docker. Location: Hanoi. "
    "This is synthetic test data."
)
EXPLICIT_DIRECT_TEXT_REQUEST = (
    'Please call save_job exactly once with text="'
    + EXPLICIT_DIRECT_TEXT
    + '" Do not use source=current_message and do not call match_jobs.'
)


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


def test_production_registry_has_exactly_seven_tools() -> None:
    """Production registry: profile, jobs, match_jobs, read_active_cv."""
    reg = production_registry()
    assert not reg.is_empty()
    names = reg.tool_names()
    assert names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    ]
    assert "synthetic_interrupt" not in names


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
    assert state["active_cv_context"] is None
    assert isinstance(state["messages_for_this_turn"][0], HumanMessage)


def test_format_attachment_ids_block_lists_exact_uuids_only() -> None:
    att = "d4cae6c9-943c-4068-bd8a-5fad83ff0cff"
    block = _format_attachment_ids_block([att, " ", att, "other-id"])
    assert block is not None
    assert att in block
    assert "other-id" in block
    assert block.count(att) == 1  # deduped
    assert "storage_path" not in block
    assert _format_attachment_ids_block([]) is None
    assert _format_attachment_ids_block(None) is None


def test_build_model_messages_includes_staged_attachment_ids() -> None:
    att = "11111111-1111-4111-8111-111111111111"
    state = initial_graph_state(
        run_id=RUN_ID,
        user_text="I uploaded my CV. Please process the attached PDF.",
        attachment_ids=[att],
    )
    messages = _build_model_messages(state, "system prompt")
    texts = [str(getattr(m, "content", "")) for m in messages]
    assert any(att in t and "Staged attachment IDs" in t for t in texts)
    assert any(
        "I uploaded my CV. Please process the attached PDF." in t for t in texts
    )


def test_build_model_messages_omits_attachment_block_when_empty() -> None:
    state = initial_graph_state(run_id=RUN_ID, user_text="hello")
    messages = _build_model_messages(state, "system prompt")
    texts = [str(getattr(m, "content", "")) for m in messages]
    assert not any("Staged attachment IDs" in t for t in texts)


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


def test_auto_commit_helper_triggers_after_draft_propose() -> None:
    """After propose_profile_from_cv draft success, chain commit_profile_draft."""
    from app.agent.graph import _auto_commit_after_draft_tool

    propose_result = {
        "ok": True,
        "code": None,
        "summary": "created validated current profile draft from staged CV",
        "data": {
            "draft_id": "current",
            "attachment_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "kind": "new_draft",
        },
    }
    state = initial_graph_state(run_id=RUN_ID, user_text="process my cv")
    state[MESSAGES_KEY] = [
        _ai_tool_call(
            "propose_profile_from_cv",
            {"attachment_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
            call_id="c-propose",
        ),
        ToolMessage(
            content=str(propose_result).replace("'", '"'),
            tool_call_id="c-propose",
            name="propose_profile_from_cv",
        ),
    ]
    # Use proper JSON content
    state[MESSAGES_KEY][-1] = ToolMessage(
        content=(
            '{"ok": true, "code": null, '
            '"summary": "created validated current profile draft from staged CV", '
            '"data": {"draft_id": "current", "kind": "new_draft", '
            '"attachment_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}}'
        ),
        tool_call_id="c-propose",
        name="propose_profile_from_cv",
    )
    auto = _auto_commit_after_draft_tool(state, commit_available=True)
    assert auto is not None
    assert auto.tool_calls
    assert auto.tool_calls[0]["name"] == "commit_profile_draft"
    assert auto.tool_calls[0]["args"]["draft_id"] == "current"

    # Second time (commit already requested) must not loop.
    state[MESSAGES_KEY].append(auto)
    assert _auto_commit_after_draft_tool(state, commit_available=True) is None


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
    # Same factory; only registry content differs (production vs test tools).
    production = build_agent_graph(
        model=FakeChatModel(responses=[_ai_text("direct")]),
        registry=production_registry(),
    )
    injected = build_agent_graph(
        model=model,
        registry=ToolRegistry([echo_tool]),
    )
    assert production.decision_node_name == injected.decision_node_name
    assert production.tools_node_name == injected.tools_node_name
    assert isinstance(production.tool_node, ToolNode)
    assert isinstance(injected.tool_node, ToolNode)
    assert production.registry.tool_names() == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    ]
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

    # Graph nodes remain free of SQLAlchemy sessions and tool persistence.
    for banned in (
        "AsyncSession",
        "session_scope",
        "sqlalchemy",
        "create_engine",
        "execute_tool",
    ):
        assert banned not in graph_text

    # Registry may type-hint injected session_factory deps but must not open
    # sessions, run SQL, or host execute_tool / synthetic helpers.
    for banned in (
        "session_scope",
        "create_engine",
        "execute_tool",
        "synthetic_interrupt",
    ):
        assert banned not in registry_text
    assert "production_registry" in registry_text
    assert "build_production_profile_tools" in registry_text
    assert "build_production_job_tools" in registry_text
    assert "build_production_match_tools" in registry_text
    assert "build_production_active_cv_tools" in registry_text
    assert "ToolRegistry" in registry_text


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
    """Import graph and confirm it does not pull FastAPI routers."""
    import app.agent.graph as graph_mod
    import app.tools.registry as reg_mod

    # Graph must not surface session/router symbols.
    graph_names = set(dir(graph_mod))
    assert "AsyncSession" not in graph_names
    assert "APIRouter" not in graph_names
    assert "include_router" not in graph_names
    # Registry may type-hint AsyncSession for injected deps; still no FastAPI.
    reg_names = set(dir(reg_mod))
    assert "APIRouter" not in reg_names
    assert "include_router" not in reg_names


# ---------------------------------------------------------------------------
# System prompt uses injected tool names only
# ---------------------------------------------------------------------------


def test_empty_registry_model_prompt_has_no_tools() -> None:
    model = FakeChatModel(responses=[_ai_text("ok")])
    bundle = build_agent_graph(model=model, registry=ToolRegistry())
    bundle.compiled.invoke(initial_graph_state(run_id=RUN_ID, user_text="hi"))
    assert model.invoke_count == 1
    system = model.call_log[0][0]
    assert "Registered JobAgent tools: none" in str(system.content)
    assert "echo_tool" not in str(system.content)
    assert "synthetic" not in str(system.content).lower()


def test_production_registry_model_prompt_lists_seven_tools() -> None:
    model = FakeChatModel(responses=[_ai_text("ok")])
    bundle = build_agent_graph(model=model, registry=production_registry())
    bundle.compiled.invoke(initial_graph_state(run_id=RUN_ID, user_text="hi"))
    system = str(model.call_log[0][0].content)
    assert "propose_profile_from_cv" in system
    assert "propose_profile_update" in system
    assert "commit_profile_draft" in system
    assert "save_job" in system
    assert "query_jobs" in system
    assert "match_jobs" in system
    assert "read_active_cv" in system
    assert "narrowest mode" in system.lower()
    assert "synthetic" not in system.lower()
    # Explicit write-tool truthfulness for named save_job (F-04 / Plan 11).
    assert "save_job truthfulness" in system
    assert "before a ToolResult exists" in system
    assert "returned exact-duplicate" in system.lower() or "returned" in system


# ---------------------------------------------------------------------------
# F-04: truthful explicitly named save_job execution
# ---------------------------------------------------------------------------


def test_named_save_job_plain_text_is_discarded_and_repaired_once() -> None:
    """First plain-text mutation claim is discarded; one repair sole call runs."""
    model = FakeChatModel(
        responses=[
            _ai_text(
                "I created a new Job entry for https://example.com successfully."
            ),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"url": "https://example.com"},
                call_id="save-repair-1",
            ),
            # Would invent "created" after tool; projection must ignore it.
            _ai_text("Created a brand new Job for you."),
        ]
    )
    bundle = _bundle(model, [save_job_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=F04_NAMED_SAVE_JOB_REQUEST)
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 1
    # First plain text discarded + one repair decision + no final model call
    # (ToolResult projection). Fake may still have unused scripted responses.
    assert model.invoke_count == 2
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert getattr(tool_msgs[0], "name", None) == SAVE_JOB_NAME
    ai_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, AIMessage)]
    # Tool-call AI + projected final AI only; discarded false claim never stored.
    assert len(ai_msgs) == 2
    assert _has_tool_calls_local(ai_msgs[0])
    final = ai_msgs[-1]
    assert not (final.tool_calls or [])
    final_text = str(final.content)
    assert "returned" in final_text.lower() or "reused" in final_text.lower()
    assert "job-dup-1" in final_text
    assert "brand new" not in final_text.lower()
    assert "I created a new Job entry" not in " ".join(
        str(m.content) for m in out[MESSAGES_KEY] if isinstance(m, AIMessage)
    )


def _has_tool_calls_local(message: AIMessage) -> bool:
    return bool(message.tool_calls)


def test_named_save_job_repair_refusal_yields_fixed_no_action() -> None:
    """Repair that still omits sole save_job → fixed no-action, zero tools."""
    model = FakeChatModel(
        responses=[
            _ai_text("Created the job already; it was reused."),
            _ai_text("Still not calling tools; the job is created."),
        ]
    )
    bundle = _bundle(model, [save_job_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=F04_NAMED_SAVE_JOB_REQUEST)
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 0
    assert model.invoke_count == 2  # first + one repair
    assert not any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])
    final = out[MESSAGES_KEY][-1]
    assert isinstance(final, AIMessage)
    assert final.content == NAMED_SAVE_JOB_NO_ACTION_TEXT
    joined = " ".join(
        str(m.content) for m in out[MESSAGES_KEY] if isinstance(m, AIMessage)
    )
    assert "Created the job already" not in joined
    assert "Still not calling tools" not in joined


def test_named_save_job_invalid_repair_tool_is_no_action() -> None:
    """Repair that calls a non-save tool is rejected; no tool executes."""
    model = FakeChatModel(
        responses=[
            _ai_text("Done, job created."),
            _ai_tool_call("echo_tool", {"text": "nope"}, call_id="wrong-1"),
        ]
    )
    bundle = _bundle(model, [save_job_tool, echo_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=F04_NAMED_SAVE_JOB_REQUEST)
    )
    assert out["tool_iteration_count"] == 0
    assert not any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])
    assert out[MESSAGES_KEY][-1].content == NAMED_SAVE_JOB_NO_ACTION_TEXT


def test_named_save_job_sole_call_projects_returned_from_tool_result() -> None:
    """Successful sole save_job path projects returned, never 'created'."""
    model = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"url": "https://example.com"},
                call_id="save-1",
            ),
        ]
    )
    bundle = _bundle(model, [save_job_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=F04_NAMED_SAVE_JOB_REQUEST)
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 1  # projection skips second model call
    final = out[MESSAGES_KEY][-1]
    assert isinstance(final, AIMessage)
    text = str(final.content).lower()
    assert "returned" in text or "reused" in text
    assert "job-dup-1" in str(final.content)
    assert "no new job was created" in text
    # Must not narrate duplicate as newly created.
    assert "brand new" not in text
    assert not str(final.content).lower().startswith("created")


def test_named_save_job_created_outcome_projection() -> None:
    model = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"url": "https://example.com/new"},
                call_id="save-new",
            ),
        ]
    )
    bundle = _bundle(model, [save_job_created_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(
            run_id=RUN_ID,
            user_text=(
                "Please call save_job with url https://example.com/new "
                "and report the outcome."
            ),
        )
    )
    final = str(out[MESSAGES_KEY][-1].content)
    assert "job-new-1" in final
    assert "Saved job description" in final


def test_named_save_job_already_called_skips_second_repair() -> None:
    """After save_job ToolResult exists, projection does not re-invoke repair."""
    model = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"url": "https://example.com"},
                call_id="save-once",
            ),
            _ai_text("should not be used"),
        ]
    )
    bundle = _bundle(model, [save_job_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=F04_NAMED_SAVE_JOB_REQUEST)
    )
    assert model.invoke_count == 1
    assert out["tool_iteration_count"] == 1
    assert "job-dup-1" in str(out[MESSAGES_KEY][-1].content)


def test_unnamed_save_request_and_greeting_paths_unchanged() -> None:
    """Greetings and non-named turns stay on the normal decision path."""
    greet_model = FakeChatModel(responses=[_ai_text("Hello! How can I help?")])
    greet_bundle = _bundle(greet_model, [save_job_tool])
    greet_out = greet_bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="Xin chào")
    )
    assert greet_out["tool_iteration_count"] == 0
    assert greet_model.invoke_count == 1
    assert greet_out[MESSAGES_KEY][-1].content == "Hello! How can I help?"

    # Unnamed save-ish prose without the registered token is not gated.
    unnamed_model = FakeChatModel(
        responses=[_ai_text("I can help save that URL if you like.")]
    )
    unnamed_bundle = _bundle(unnamed_model, [save_job_tool])
    unnamed_out = unnamed_bundle.compiled.invoke(
        initial_graph_state(
            run_id=RUN_ID,
            user_text="Please save https://example.com for me.",
        )
    )
    assert unnamed_model.invoke_count == 1
    assert unnamed_out[MESSAGES_KEY][-1].content == (
        "I can help save that URL if you like."
    )
    assert not any(isinstance(m, ToolMessage) for m in unnamed_out[MESSAGES_KEY])


def test_normal_non_save_tool_path_unchanged() -> None:
    model = FakeChatModel(
        responses=[
            _ai_tool_call("echo_tool", {"text": "abc"}, call_id="e1"),
            _ai_text("You said abc"),
        ]
    )
    bundle = _bundle(model, [echo_tool, save_job_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="echo abc please")
    )
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 2
    assert out[MESSAGES_KEY][-1].content == "You said abc"


def test_named_save_job_gate_has_ponytail_and_topology_intact() -> None:
    graph_text = (APP_AGENT / "graph.py").read_text(encoding="utf-8")
    assert "ponytail:" in graph_text
    assert "mutation-intent contract" in graph_text
    assert "exact-name gate" in graph_text
    assert "NAMED_SAVE_JOB_NO_ACTION_TEXT" in graph_text

    model = FakeChatModel(responses=[_ai_text("hi")])
    bundle = _bundle(model, [save_job_tool])
    app_nodes = {
        n
        for n in bundle.compiled.get_graph().nodes
        if n not in {"__start__", "__end__", "START", "END"}
    }
    assert app_nodes == {DECISION_NODE_NAME, TOOLS_NODE_NAME}
    assert bundle.tool_loop_limit == 6


# ---------------------------------------------------------------------------
# Plan 12: passive-JD recognition precedence, one repair, narration
# ---------------------------------------------------------------------------


def test_opt_out_suppresses_exact_name_and_passive_repair() -> None:
    """Clear opt-out wins over exact-name repair and passive-JD repair."""
    # Exact-name token plus clear opt-out: no forced save_job repair.
    named_opt = (
        "Use save_job with url https://example.com but please don't save it."
    )
    assert conf.message_has_clear_opt_out(named_opt)
    model = FakeChatModel(
        responses=[
            _ai_text("I created the job successfully."),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"url": "https://example.com"},
                call_id="should-not-run",
            ),
        ]
    )
    bundle = _bundle(model, [save_job_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=named_opt)
    )
    assert out["tool_iteration_count"] == 0
    assert model.invoke_count == 1  # no repair invoke
    assert not any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])
    assert out[MESSAGES_KEY][-1].content == "I created the job successfully."

    # Obvious JD plus Vietnamese opt-out: no passive repair / mutation.
    jd_opt = _obvious_passive_jd() + "\nkhông lưu"
    assert conf.message_has_clear_opt_out(jd_opt)
    assert conf.message_is_obvious_jd(jd_opt)
    jd_model = FakeChatModel(
        responses=[
            _ai_text("Looks like a JD; I will not save it."),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"source": "current_message"},
                call_id="passive-should-not",
            ),
        ]
    )
    jd_bundle = _bundle(jd_model, [save_job_current_message_tool])
    jd_out = jd_bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd_opt)
    )
    assert jd_out["tool_iteration_count"] == 0
    assert jd_model.invoke_count == 1
    assert not any(isinstance(m, ToolMessage) for m in jd_out[MESSAGES_KEY])


def test_positive_exact_name_precedes_passive_jd_repair() -> None:
    """Positive exact-name Plan 11 path wins over passive current-message repair."""
    # Named token with obvious-JD-shaped text still uses exact-name repair
    # (url/text sole call), not source=current_message.
    body = (
        "Please call save_job for this posting:\n"
        + _obvious_passive_jd()
        + "\nurl https://example.com/role"
    )
    assert conf.message_is_obvious_jd(body)
    assert not conf.message_has_clear_opt_out(body)
    model = FakeChatModel(
        responses=[
            _ai_text("Saved already."),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"url": "https://example.com/role"},
                call_id="exact-1",
            ),
        ]
    )
    bundle = _bundle(model, [save_job_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=body)
    )
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 2  # first + exact-name repair
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    ai_with_calls = [
        m
        for m in out[MESSAGES_KEY]
        if isinstance(m, AIMessage) and (m.tool_calls or [])
    ]
    assert len(ai_with_calls) == 1
    args = ai_with_calls[0].tool_calls[0]["args"]
    assert args.get("url") == "https://example.com/role"
    assert args.get("source") != "current_message"
    final = str(out[MESSAGES_KEY][-1].content).lower()
    assert "returned" in final or "reused" in final


def test_sole_url_dispatches_direct_save_and_ambiguous_prose_stays_normal() -> None:
    sole_url = "https://example.com/jobs/backend-engineer"
    assert conf.message_is_sole_http_url(sole_url)
    url_model = FakeChatModel(responses=[_ai_text("I can open that link.")])
    url_bundle = _bundle(url_model, [save_job_current_message_tool])
    url_out = url_bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=sole_url)
    )
    assert url_model.invoke_count == 1
    assert url_out["tool_iteration_count"] == 1
    assert any(isinstance(m, ToolMessage) for m in url_out[MESSAGES_KEY])
    url_calls = [
        call
        for message in url_out[MESSAGES_KEY]
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
    ]
    assert len(url_calls) == 1
    assert url_calls[0]["args"] == {"url": sole_url}
    assert url_out[MESSAGES_KEY][-1].content == "I can open that link."

    # Long ambiguous prose without distinct JD markers is not forced.
    ambiguous = ("This is a long story about my career journey. " * 20).strip()
    assert conf._non_whitespace_char_count(ambiguous) >= 300  # noqa: SLF001
    assert not conf.message_is_obvious_jd(ambiguous)
    amb_model = FakeChatModel(responses=[_ai_text("Thanks for sharing.")])
    amb_bundle = _bundle(amb_model, [save_job_current_message_tool])
    amb_out = amb_bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=ambiguous)
    )
    assert amb_model.invoke_count == 1
    assert amb_out["tool_iteration_count"] == 0
    assert amb_out[MESSAGES_KEY][-1].content == "Thanks for sharing."


def test_passive_canonical_tool_success_projects_without_provider() -> None:
    """First decision already sole current-message: no repair, ToolResult narrates."""
    jd = _obvious_passive_jd()
    model = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"source": "current_message"},
                call_id="cm-first",
            ),
            _ai_text("I created a brand new job for you."),
        ]
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )
    assert out["error"] is None
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 0
    final = str(out[MESSAGES_KEY][-1].content)
    assert "job-cm-1" in final
    assert "brand new" not in final.lower()
    assert not any(
        isinstance(m, AIMessage)
        and "brand new" in str(m.content).lower()
        for m in out[MESSAGES_KEY]
    )


def test_passive_vietnamese_dispatch_discards_provider_script() -> None:
    """Plain-text miss → one current-message repair; discard never stored."""
    jd = _obvious_passive_jd(markers=("mô tả công việc", "yêu cầu"))
    model = FakeChatModel(
        responses=[
            _ai_text("I already saved this JD for you."),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {
                    "source": "current_message",
                    "preview": {"title": "Engineer", "company": None, "skills": []},
                },
                call_id="cm-repair",
            ),
            _ai_text("Created successfully."),
        ]
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 0
    joined = " ".join(
        str(m.content) for m in out[MESSAGES_KEY] if isinstance(m, AIMessage)
    )
    assert "I already saved this JD" not in joined
    assert "Created successfully." not in joined
    final = str(out[MESSAGES_KEY][-1].content)
    assert "job-cm-1" in final
    ai_calls = [
        m
        for m in out[MESSAGES_KEY]
        if isinstance(m, AIMessage) and (m.tool_calls or [])
    ]
    assert len(ai_calls) == 1
    assert ai_calls[0].tool_calls[0]["args"] == {"source": "current_message"}


def test_passive_malformed_provider_call_cannot_override_canonical_source() -> None:
    """Malformed first passive call is discarded; only a source-only repair runs."""
    jd = _obvious_passive_jd()
    model = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"text": jd, "source": "current_message"},
                call_id="malformed-first",
            ),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"source": "current_message"},
                call_id="cm-repair",
            ),
            _ai_text("I created a brand new job for you."),
        ]
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )

    assert out["error"] is None
    assert model.invoke_count == 0
    assert out["tool_iteration_count"] == 1
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert getattr(tool_msgs[0], "name", None) == SAVE_JOB_NAME
    ai_calls = [
        m
        for m in out[MESSAGES_KEY]
        if isinstance(m, AIMessage) and (m.tool_calls or [])
    ]
    assert len(ai_calls) == 1
    call = ai_calls[0].tool_calls[0]
    assert str(call["id"]).startswith("canonical-save-current-message-")
    assert call["args"] == {"source": "current_message"}
    final = str(out[MESSAGES_KEY][-1].content)
    assert "job-cm-1" in final
    assert "brand new" not in final.lower()


def test_passive_malformed_repair_script_cannot_block_confirmation() -> None:
    """A text-plus-source repair is rejected without executing save_job."""
    jd = _obvious_passive_jd()
    model = FakeChatModel(
        responses=[
            _ai_text("I already saved this JD for you."),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"text": jd, "source": "current_message"},
                call_id="malformed-repair",
            ),
        ]
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )

    assert out["error"] is None
    assert model.invoke_count == 0
    assert out["tool_iteration_count"] == 1
    assert any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])
    calls = [
        call
        for message in out[MESSAGES_KEY]
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
    ]
    assert len(calls) == 1
    assert calls[0]["args"] == {"source": "current_message"}


def test_passive_plain_text_provider_script_is_not_invoked() -> None:
    jd = _obvious_passive_jd()
    model = FakeChatModel(
        responses=[
            _ai_text("Looks like a job post."),
            _ai_text("Still not calling tools."),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"source": "current_message"},
                call_id="too-late",
            ),
        ]
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 0
    assert any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])
    assert "job-cm-1" in str(out[MESSAGES_KEY][-1].content)
    joined = " ".join(
        str(m.content) for m in out[MESSAGES_KEY] if isinstance(m, AIMessage)
    )
    assert "Looks like a job post" not in joined
    assert "Still not calling tools" not in joined


def test_passive_wrong_provider_tools_are_not_invoked() -> None:
    """Repair that calls another tool or non-CM save_job is refused."""
    jd = _obvious_passive_jd()
    model = FakeChatModel(
        responses=[
            _ai_text("Saving now."),
            _ai_tool_call("echo_tool", {"text": "nope"}, call_id="wrong"),
        ]
    )
    bundle = _bundle(model, [save_job_current_message_tool, echo_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )
    assert model.invoke_count == 0
    assert out["tool_iteration_count"] == 1
    assert "job-cm-1" in str(out[MESSAGES_KEY][-1].content)

    url_model = FakeChatModel(
        responses=[
            _ai_text("Saving now."),
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"url": "https://example.com"},
                call_id="url-not-cm",
            ),
        ]
    )
    url_bundle = _bundle(url_model, [save_job_current_message_tool])
    url_out = url_bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )
    assert url_model.invoke_count == 0
    assert url_out["tool_iteration_count"] == 1
    assert "job-cm-1" in str(url_out[MESSAGES_KEY][-1].content)


def test_cancellation_narration_from_tool_result_only() -> None:
    """Cancel ToolResult projects not-saved wording; never saved/created."""
    model = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                {"source": "current_message"},
                call_id="cancel-1",
            ),
            _ai_text("Job was created successfully."),
        ]
    )
    bundle = _bundle(model, [save_job_cancel_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=_obvious_passive_jd())
    )
    assert model.invoke_count == 0
    final = str(out[MESSAGES_KEY][-1].content)
    assert final == conf.CANCEL_SUMMARY
    assert "created" not in final.lower()
    assert "saved" not in final.lower() or "chưa được lưu" in final
    assert "Job was created successfully" not in " ".join(
        str(m.content) for m in out[MESSAGES_KEY] if isinstance(m, AIMessage)
    )


def test_unrelated_greeting_and_topology_six_pass_unchanged() -> None:
    """Unrelated turns, one Agent/decision/ToolNode, seven tools, six passes."""
    greet_model = FakeChatModel(responses=[_ai_text("Chào bạn!")])
    greet_bundle = _bundle(greet_model, [save_job_current_message_tool])
    greet_out = greet_bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text="Xin chào")
    )
    assert greet_model.invoke_count == 1
    assert greet_out["tool_iteration_count"] == 0
    assert greet_out[MESSAGES_KEY][-1].content == "Chào bạn!"

    # Service predicates remain the single owner (ponytail on message_is_obvious_jd).
    service_text = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "job_save_confirmation.py"
    ).read_text(encoding="utf-8")
    assert "ponytail:" in service_text
    assert "typed composer intent" in service_text

    graph_text = (APP_AGENT / "graph.py").read_text(encoding="utf-8")
    assert "message_is_obvious_jd" in graph_text
    assert "message_has_clear_opt_out" in graph_text
    assert "PASSIVE_JD_NO_CONFIRMATION_TEXT" in graph_text
    assert "StateGraph" in graph_text

    reg = production_registry()
    assert len(reg.tool_names()) == 7
    model = FakeChatModel(responses=[_ai_text("ok")])
    bundle = _bundle(model, [save_job_tool])
    app_nodes = {
        n
        for n in bundle.compiled.get_graph().nodes
        if n not in {"__start__", "__end__", "START", "END"}
    }
    assert app_nodes == {DECISION_NODE_NAME, TOOLS_NODE_NAME}
    assert bundle.tool_loop_limit == 6
    assert bundle.decision_node_name == DECISION_NODE_NAME
    assert bundle.tools_node_name == TOOLS_NODE_NAME


# ---------------------------------------------------------------------------
# Plan 13 (01B/05B): provider binding plus canonical passive dispatch
# ---------------------------------------------------------------------------


def test_passive_binding_aware_provider_is_bound_but_not_invoked() -> None:
    """Provider definitions remain compatible while canonical dispatch owns args."""
    jd = _obvious_passive_jd()
    model = PassiveJdBindingAwareFake(
        mixed_text=jd,
        preview_value="Synthetic Engineer",
        argument_value="Plan13 Labs",
        provider_payload_value="PROVIDER-PAYLOAD-SENTINEL-DO-NOT-LOG",
        permit_valid_repair=True,
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )

    assert out["error"] is None
    assert model.invoke_count == 0
    assert out["tool_iteration_count"] == 1
    tool_msgs = [m for m in out[MESSAGES_KEY] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert getattr(tool_msgs[0], "name", None) == SAVE_JOB_NAME
    ai_calls = [
        m
        for m in out[MESSAGES_KEY]
        if isinstance(m, AIMessage) and (m.tool_calls or [])
    ]
    assert len(ai_calls) == 1
    assert ai_calls[0].tool_calls[0]["args"] == {"source": "current_message"}
    final = str(out[MESSAGES_KEY][-1].content)
    assert "job-cm-1" in final

    # Two binds: normal multi-tool (no choice) + repair-only canonical choice.
    assert len(model.binding_log) == 2
    normal_tools, normal_kwargs = model.binding_log[0]
    repair_tools, repair_kwargs = model.binding_log[1]
    assert "tool_choice" not in normal_kwargs
    assert len(normal_tools) >= 1
    assert repair_tools == [save_job_openai_tool_schema()]
    assert repair_kwargs == {"tool_choice": CANONICAL_SAVE_JOB_TOOL_CHOICE}
    assert PASSIVE_JD_REPAIR_TOOL_CHOICE == CANONICAL_SAVE_JOB_TOOL_CHOICE


def test_passive_canonical_dispatch_ignores_binding_aware_mixed_output() -> None:
    """Provider mixed output cannot block a deterministic source-only call."""
    jd = _obvious_passive_jd()
    model = PassiveJdBindingAwareFake(
        mixed_text=jd,
        preview_value="Synthetic Engineer",
        argument_value="Plan13 Labs",
        provider_payload_value="PROVIDER-PAYLOAD-SENTINEL-DO-NOT-LOG",
        permit_valid_repair=False,
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )

    assert out["error"] is None
    assert model.invoke_count == 0
    assert out["tool_iteration_count"] == 1
    assert any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])
    calls = [
        call
        for message in out[MESSAGES_KEY]
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
    ]
    assert len(calls) == 1
    assert calls[0]["args"] == {"source": "current_message"}
    assert "job-cm-1" in str(out[MESSAGES_KEY][-1].content)


def test_passive_canonical_dispatch_logs_no_content_or_rejection(
    caplog: Any,
) -> None:
    """Canonical dispatch neither invokes the provider nor logs JD content."""
    raw_sentinel = "RAW-JD-SENTINEL-DO-NOT-LOG"
    preview_sentinel = "PREVIEW-SENTINEL-DO-NOT-LOG"
    argument_sentinel = "ARGUMENT-VALUE-SENTINEL-DO-NOT-LOG"
    provider_sentinel = "PROVIDER-PAYLOAD-SENTINEL-DO-NOT-LOG"
    prompt_sentinel = "PROMPT-SENTINEL-DO-NOT-LOG"
    jd = _obvious_passive_jd() + f"\n{raw_sentinel}\n{prompt_sentinel}"
    model = PassiveJdBindingAwareFake(
        mixed_text=jd,
        preview_value=preview_sentinel,
        argument_value=argument_sentinel,
        provider_payload_value=provider_sentinel,
        permit_valid_repair=False,
    )
    # Alembic migrations in other unit tests can disable existing loggers.
    graph_logger = logging.getLogger("app.agent.graph")
    was_disabled = graph_logger.disabled
    graph_logger.disabled = False
    try:
        with caplog.at_level(logging.WARNING, logger="app.agent.graph"):
            out = _bundle(model, [save_job_current_message_tool]).compiled.invoke(
                initial_graph_state(run_id=RUN_ID, user_text=jd)
            )
    finally:
        graph_logger.disabled = was_disabled

    assert "job-cm-1" in str(out[MESSAGES_KEY][-1].content)
    repair_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.agent.graph"
        and record.getMessage().startswith("passive_jd_call_rejected")
    ]
    assert repair_logs == []
    joined = "\n".join(record.getMessage() for record in caplog.records)
    for forbidden in (
        jd,
        raw_sentinel,
        preview_sentinel,
        argument_sentinel,
        provider_sentinel,
        prompt_sentinel,
        "current_message",
        "provider_payload",
        "Required repair:",
    ):
        assert forbidden not in joined


def test_obvious_jd_dispatches_canonical_current_message_without_provider() -> None:
    jd = _obvious_passive_jd()
    model = PassiveJdBindingAwareFake(
        mixed_text=jd,
        preview_value="Synthetic Engineer",
        argument_value="Plan13 Labs",
        provider_payload_value="PROVIDER-PAYLOAD-SENTINEL-DO-NOT-LOG",
        permit_valid_repair=False,
    )
    out = _bundle(model, [save_job_current_message_tool]).compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )
    calls = [
        call
        for message in out[MESSAGES_KEY]
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
    ]
    assert model.invoke_count == 0
    assert out["tool_iteration_count"] == 1
    assert len(calls) == 1
    assert calls[0]["name"] == SAVE_JOB_NAME
    assert calls[0]["args"] == {"source": "current_message"}


def test_sole_url_dispatches_exact_url_without_provider() -> None:
    sole_url = "https://example.com/jobs/plan13-synthetic-engineer"
    model = FakeChatModel(responses=[_ai_text("provider must not run")])
    out = _bundle(model, [save_job_tool]).compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=f"  {sole_url}  ")
    )
    calls = [
        call
        for message in out[MESSAGES_KEY]
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
    ]
    assert model.invoke_count == 1
    assert len(calls) == 1
    assert calls[0]["args"] == {"url": sole_url}


def test_approved_explicit_text_dispatches_exact_text() -> None:
    model = FakeChatModel(responses=[_ai_text("provider must not choose args")])
    out = _bundle(model, [save_job_created_tool]).compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=EXPLICIT_DIRECT_TEXT_REQUEST)
    )
    calls = [
        call
        for message in out[MESSAGES_KEY]
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
    ]
    assert model.invoke_count == 0
    assert len(calls) == 1
    assert calls[0]["args"] == {"text": EXPLICIT_DIRECT_TEXT}


def test_near_miss_explicit_text_remains_model_driven() -> None:
    request = EXPLICIT_DIRECT_TEXT_REQUEST.replace(
        "Do not use source=current_message", "Avoid current-message mode"
    )
    model = FakeChatModel(responses=[_ai_text("Please clarify.")])
    out = _bundle(model, [save_job_tool]).compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=request)
    )
    assert model.invoke_count == 2
    assert out["tool_iteration_count"] == 0
    assert out[MESSAGES_KEY][-1].content == NAMED_SAVE_JOB_NO_ACTION_TEXT
