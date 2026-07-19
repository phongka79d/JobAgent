# Passive `save_job` Tool-Call Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent malformed passive-JD `save_job` calls from reaching `ToolNode` and use one bounded repair to obtain a strict `source="current_message"` call.

**Architecture:** Keep `SaveJobInput` as the sole source-mode and preview validator. The decision node validates both the initial passive-JD response and the one repair response before dispatch; direct URL/text, explicitly named saves, and frontend behavior remain unchanged.

**Tech Stack:** Python 3.11+, Pydantic 2, LangChain/LangGraph, pytest, Ruff, mypy

---

### Task 1: Reproduce malformed initial and repair calls

**Files:**
- Modify: `backend/tests/unit/test_agent_graph.py:1024-1153`
- Test: `backend/tests/unit/test_agent_graph.py`

- [x] **Step 1: Add the failing initial-call regression test**

Insert this test after `test_passive_first_tool_success_projects_without_repair`:

```python
def test_passive_malformed_first_save_job_call_is_discarded_and_repaired_once() -> None:
    """Mixed text/current-message first call is discarded and repaired once."""
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
            _ai_text("Created successfully."),
        ]
    )
    bundle = _bundle(model, [save_job_current_message_tool])
    out = bundle.compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )

    assert out["error"] is None
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 2
    ai_calls = [
        m
        for m in out[MESSAGES_KEY]
        if isinstance(m, AIMessage) and (m.tool_calls or [])
    ]
    assert len(ai_calls) == 1
    assert ai_calls[0].tool_calls[0]["id"] == "cm-repair"
    assert ai_calls[0].tool_calls[0]["args"] == {
        "source": "current_message"
    }
    assert "job-cm-1" in str(out[MESSAGES_KEY][-1].content)
```

- [x] **Step 2: Run the initial-call test and verify RED**

Run from `backend/`:

```powershell
pytest tests/unit/test_agent_graph.py::test_passive_malformed_first_save_job_call_is_discarded_and_repaired_once -q
```

Expected: FAIL because the current graph dispatches `malformed-first` directly,
so `model.invoke_count` is `1` and the stored tool call is not `cm-repair`.

- [x] **Step 3: Add the failing invalid-repair regression test**

Insert this test after `test_passive_one_repair_success_discards_plain_text`:

```python
def test_passive_malformed_repair_call_yields_no_confirmation_without_tools() -> None:
    """A mixed text/current-message repair never reaches ToolNode."""
    jd = _obvious_passive_jd()
    model = FakeChatModel(
        responses=[
            _ai_text("Saving now."),
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

    assert out["tool_iteration_count"] == 0
    assert model.invoke_count == 2
    assert not any(isinstance(m, ToolMessage) for m in out[MESSAGES_KEY])
    assert not any(
        isinstance(m, AIMessage) and (m.tool_calls or [])
        for m in out[MESSAGES_KEY]
    )
    assert out[MESSAGES_KEY][-1].content == PASSIVE_JD_NO_CONFIRMATION_TEXT
```

- [x] **Step 4: Run the invalid-repair test and verify RED**

Run from `backend/`:

```powershell
pytest tests/unit/test_agent_graph.py::test_passive_malformed_repair_call_yields_no_confirmation_without_tools -q
```

Expected: FAIL because the current `_is_sole_current_message_save_job_call`
checks only for the presence of `source="current_message"`; the lax test tool
therefore executes and increments `tool_iteration_count` to `1`.

### Task 2: Validate every passive-JD call with `SaveJobInput`

**Files:**
- Modify: `backend/app/agent/graph.py:19-59`
- Modify: `backend/app/agent/graph.py:546-552`
- Modify: `backend/app/agent/graph.py:819-839`
- Test: `backend/tests/unit/test_agent_graph.py`

- [x] **Step 1: Import the authoritative schema and validation exception**

Add the third-party import:

```python
from pydantic import ValidationError
```

Add the application import:

```python
from app.schemas.jobs import SAVE_JOB_SOURCE_CURRENT_MESSAGE, SaveJobInput
```

Remove the duplicated module constant:

```python
SAVE_JOB_SOURCE_CURRENT_MESSAGE: str = "current_message"
```

Keep `SAVE_JOB_CANCEL_OUTCOME` unchanged because cancellation narration remains
owned by this graph module in the current scope.

- [x] **Step 2: Replace the source-presence check with strict schema validation**

Replace `_is_sole_current_message_save_job_call` with:

```python
def _is_sole_current_message_save_job_call(message: AIMessage | None) -> bool:
    """True for exactly one valid source-only current-message save_job call."""
    if not _is_sole_save_job_call(message):
        return False
    assert message is not None
    calls = list(message.tool_calls or [])
    try:
        args = SaveJobInput.model_validate(_tool_call_args(calls[0]))
    except ValidationError:
        return False
    return args.source == SAVE_JOB_SOURCE_CURRENT_MESSAGE
```

This reuses the production one-of, preview, and extra-field rules instead of
duplicating them in the graph.

- [x] **Step 3: Apply the same predicate to initial and repaired responses**

Replace the passive-JD block body at `backend/app/agent/graph.py:828-839` with:

```python
            if not _is_sole_current_message_save_job_call(response):
                repair_messages = list(prompt_messages) + [
                    SystemMessage(content=_PASSIVE_JD_REPAIR_INSTRUCTION)
                ]
                response = _normalize_ai_response(chat.invoke(repair_messages))
                if not _is_sole_current_message_save_job_call(response):
                    return {
                        MESSAGES_KEY: [
                            AIMessage(content=PASSIVE_JD_NO_CONFIRMATION_TEXT)
                        ]
                    }
```

Update the preceding comment from “one repair after plain-text miss only” to
“one repair after any invalid first decision” so the comment matches behavior.

- [x] **Step 4: Run both regression tests and verify GREEN**

Run from `backend/`:

```powershell
pytest tests/unit/test_agent_graph.py::test_passive_malformed_first_save_job_call_is_discarded_and_repaired_once tests/unit/test_agent_graph.py::test_passive_malformed_repair_call_yields_no_confirmation_without_tools -q
```

Expected: `2 passed`.

- [x] **Step 5: Run the full graph unit test file**

Run from `backend/`:

```powershell
pytest tests/unit/test_agent_graph.py -q
```

Expected: all graph tests pass, including existing valid-first-call,
plain-text-repair, opt-out, named-save, and loop-limit behavior.

### Task 3: Verify related contracts and repository quality

**Files:**
- Verify: `backend/app/agent/graph.py`
- Verify: `backend/tests/unit/test_agent_graph.py`
- Verify: `backend/tests/unit/test_job_save_confirmation.py`
- Verify: `backend/tests/integration/test_job_tools.py`

- [x] **Step 1: Run formatting and static checks for changed Python files**

Run from `backend/`:

```powershell
ruff check app/agent/graph.py tests/unit/test_agent_graph.py
ruff format --check app/agent/graph.py tests/unit/test_agent_graph.py
mypy app
```

Expected: `ruff check` and `mypy` exit `0`. `ruff format --check` reports
pre-existing formatting differences in both files; the same baseline check on
the prior commits reports those differences, so no unrelated whole-file
reformat is applied.

- [x] **Step 2: Run related schema and production-tool tests**

Run from `backend/`:

```powershell
pytest tests/unit/test_job_save_confirmation.py tests/integration/test_job_tools.py -q
```

Expected: all tests pass, proving source exclusivity, preview validation, direct
URL/text behavior, interrupt behavior, and persisted execution remain intact.

- [x] **Step 3: Run the full backend test suite**

Run from `backend/`:

```powershell
pytest -q
```

Expected: all backend tests pass with zero failures.

- [x] **Step 4: Review the final diff and whitespace**

Run from the repository root:

```powershell
git diff --check
git diff -- backend/app/agent/graph.py backend/tests/unit/test_agent_graph.py
git status --short
```

Expected: no whitespace errors; the production diff is limited to strict
passive-call validation and bounded repair; the pre-existing deleted audit
design file remains unrelated and unstaged.

- [x] **Step 5: Record the tested implementation plan without unrelated changes**

Run from the repository root:

```powershell
git add -- docs/superpowers/plans/2026-07-19-save-job-passive-call-repair.md
git commit -m "docs: record passive save_job implementation plan"
```

Expected: one documentation commit containing only this plan. The graph fix
and regression tests are already committed as `ebc7670` and `c8acd76`; do not
stage the pre-existing deleted frontend audit spec.
