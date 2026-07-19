# Plan 13 Repair And Revalidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable passive pasted-JD confirmation, give the active-CV evidence dialog an accessible name, and close the audited diagnostic/browser/evidence gaps without changing JobAgent's architecture or public product contracts.

**Architecture:** Keep `SaveJobInput` as the runtime source-of-truth and give the existing `save_job` tool a strict provider-visible three-branch schema. The existing decision node performs one forced, source-only repair before its truthful refusal; the existing ToolNode/interrupt path remains the sole mutation path. The frontend adds only an `aria-label` to the existing Astryx dialog, while deterministic diagnostic tests and a dated acceptance ledger provide fresh release evidence.

**Tech Stack:** Python 3.13, Pydantic v2, LangChain/LangGraph, FastAPI/pytest, React 19, TypeScript, Astryx 0.1.4, Vitest/Testing Library, Docker Compose, SQLite, Neo4j.

**Approved design:** `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md`

**Planning/execution gate:** This planning turn creates neither product code nor
`docs/tasks/task_13.md`. First obtain independent approval of the complete
Plans 1-13 portfolio; then `task-writing-agent` must create and approve the
canonical `docs/tasks/task_13.md` contract. Only after that contract exists may
an A1 worker execute this implementation plan, followed by A2 review and A3
batch-scope audit.

**Commit policy for every task below:** In the canonical A1/A2/A3 workflow, task
workers and reviewers do not stage or commit; A3/orchestrator owns commit
readiness and the final commit. A task's shown `git add`/`git commit` commands
are therefore conditional: run them only in a separately authorized,
non-orchestrated execution where the user explicitly delegated commit ownership.

---

## File map

### Backend/provider boundary

- Modify `backend/app/schemas/jobs.py`: own the exact provider-visible `save_job` JSON schema beside the existing runtime models and bounds.
- Modify `backend/app/tools/jobs.py`: attach that provider schema to the existing tool without changing its name, implementation, injected state, or runtime `SaveJobInput` validation.
- Modify `backend/app/adapters/shopaikey_chat.py`: allow one optional forced tool choice for a bounded repair binding.
- Modify `backend/app/agent/graph.py`: build the passive-repair binding from the same base model/tool and use it for exactly one repair invocation.
- Modify `backend/tests/unit/test_shopaikey_chat.py`: inspect the real OpenAI-format provider schema and forced-tool binding.
- Modify `backend/tests/unit/test_agent_graph.py`: cover strict passive repair/refusal/topology behavior.
- Modify `backend/tests/fakes/fake_chat_model.py`: add the shared bind-aware
  passive-JD fake used by unit and public-path regression tests.
- Modify `backend/tests/unit/test_job_save_confirmation.py`: retain runtime union/preview boundary coverage.
- Modify `backend/tests/integration/test_job_tools.py`: prove strict tool schema preserves injected state, interrupt, save/cancel, replay, and side-effect counts.
- Modify `backend/tests/integration/test_chat_api.py`: prove public SSE produces a confirmation for a repaired obvious JD.

### Frontend accessibility

- Modify `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx`: give the outer Astryx `Dialog` the exact accessible name.
- Modify `frontend/src/test/active-cv-source.test.tsx`: assert the dialog role/name and preserve evidence/no-fetch behavior.
- Modify `frontend/src/test/assistant-response.test.tsx`: retain trigger, close, Escape, and focus-return coverage.

### Diagnostics and evidence

- Create `backend/tests/unit/test_phase0_diagnostics.py`: deterministic failure-path tests for the ShopAIKey and pypdf diagnostics.
- Modify `infrastructure/scripts/verify_pdf_extraction.py` only if the tests need a pure aggregate helper; do not change its success contract or add OCR.
- Modify `infrastructure/scripts/shopaikey_diag/*.py` only when a failing case proves a mapping/redaction defect; reuse existing codes and `emit_failure`.
- Modify `docs/acceptance/full_functional_test_matrix.md`: add the Plan 12/13 supplement and ledger link.
- Create `docs/acceptance/plan13_acceptance_ledger.md`: dated status/evidence owner for every Plan 13 and revalidated P12 row.
- Modify `docs/acceptance/cv_manager_checklist.md`: add the fresh disposable archived-CV browser rerun reference.

## Task 1: Lock the provider-visible `save_job` schema

**Files:**

- Modify: `backend/tests/unit/test_shopaikey_chat.py`
- Modify: `backend/tests/unit/test_job_save_confirmation.py`
- Modify: `backend/app/schemas/jobs.py`
- Modify: `backend/app/tools/jobs.py`
- Modify: `backend/app/agent/graph.py`

- [ ] **Step 1: Write a failing provider-schema test**

Add a test that inspects the actual OpenAI-format tool payload, not only
`SaveJobInput.model_json_schema()`:

```python
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.schemas.jobs import (
    SAVE_JOB_PREVIEW_COMPANY_MAX,
    SAVE_JOB_PREVIEW_SKILL_MAX,
    SAVE_JOB_PREVIEW_SKILLS_MAX,
    SAVE_JOB_PREVIEW_TITLE_MAX,
)
from app.tools.jobs import SAVE_JOB_NAME, save_job_openai_tool_schema


def test_save_job_provider_schema_has_exact_source_union() -> None:
    spec = convert_to_openai_tool(save_job_openai_tool_schema())
    assert spec["function"]["name"] == SAVE_JOB_NAME
    params = spec["function"]["parameters"]

    assert params["type"] == "object"
    branches = {
        tuple(branch["required"]): branch for branch in params["oneOf"]
    }
    assert set(branches) == {("url",), ("text",), ("source",)}
    assert all(branch["additionalProperties"] is False for branch in params["oneOf"])

    url = branches[("url",)]
    text = branches[("text",)]
    current = branches[("source",)]
    assert url["type"] == text["type"] == current["type"] == "object"
    assert set(url["properties"]) == {"url"}
    assert url["properties"]["url"] == {"type": "string", "minLength": 1}
    assert set(text["properties"]) == {"text"}
    assert text["properties"]["text"] == {"type": "string", "minLength": 1}
    assert set(current["properties"]) == {"source", "preview"}
    assert current["properties"]["source"] == {
        "type": "string",
        "const": "current_message",
    }
    preview = current["properties"]["preview"]
    assert preview["type"] == "object"
    assert preview["additionalProperties"] is False
    assert set(preview["properties"]) == {"title", "company", "skills"}
    assert preview["properties"]["title"]["anyOf"][0]["maxLength"] == (
        SAVE_JOB_PREVIEW_TITLE_MAX
    )
    assert preview["properties"]["company"]["anyOf"][0]["maxLength"] == (
        SAVE_JOB_PREVIEW_COMPANY_MAX
    )
    skills = preview["properties"]["skills"]
    assert skills["maxItems"] == SAVE_JOB_PREVIEW_SKILLS_MAX
    assert skills["items"]["minLength"] == 1
    assert skills["items"]["maxLength"] == SAVE_JOB_PREVIEW_SKILL_MAX

    rendered = str(params)
    assert "tool_call_id" not in rendered
    assert "state" not in rendered
```

Also parameterize runtime `SaveJobInput` tests for non-empty URL, non-empty text,
source-only, mixed source, preview on direct mode, unknown keys, and over-limit
preview. These tests must continue to assert that runtime validation is stricter
than provider hints.

- [ ] **Step 2: Run the tests and verify the provider-schema test fails**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py -q
```

Expected: FAIL because the current provider schema has no `oneOf`, exposes
nullable generic `source`, and does not encode preview/source exclusivity.

- [ ] **Step 3: Add the minimal provider schema owner**

In `backend/app/schemas/jobs.py`, add one immutable JSON-schema builder using the
existing preview bounds:

```python
def save_job_provider_schema() -> dict[str, Any]:
    preview = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {
                "anyOf": [
                    {"type": "string", "maxLength": SAVE_JOB_PREVIEW_TITLE_MAX},
                    {"type": "null"},
                ]
            },
            "company": {
                "anyOf": [
                    {"type": "string", "maxLength": SAVE_JOB_PREVIEW_COMPANY_MAX},
                    {"type": "null"},
                ]
            },
            "skills": {
                "type": "array",
                "maxItems": SAVE_JOB_PREVIEW_SKILLS_MAX,
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": SAVE_JOB_PREVIEW_SKILL_MAX,
                },
            },
        },
    }
    return {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string", "minLength": 1},
                },
                "required": ["url"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                },
                "required": ["text"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {
                        "type": "string",
                        "const": SAVE_JOB_SOURCE_CURRENT_MESSAGE,
                    },
                    "preview": preview,
                },
                "required": ["source"],
            },
        ],
    }
```

Each `oneOf` entry above is a complete object branch with its own
`properties`, `required`, and `additionalProperties=False`. Do not replace it
with a shared nullable root property bag: branch-local properties are what make
URL, explicit text, and current-message mutually exclusive at the provider
boundary.

In `backend/app/tools/jobs.py`, wrap those parameters in one OpenAI-format
definition and reuse a single description constant:

```python
SAVE_JOB_DESCRIPTION: str = (
    "Save a public job URL, pasted JD text, or the current user message. "
    "Provide exactly one of url, text, or source='current_message'. "
    "Current-message mode pauses for confirmation before ingestion; optional "
    "preview is presentation-only. Returns compact status only, never raw JD."
)


def save_job_openai_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": SAVE_JOB_NAME,
            "description": SAVE_JOB_DESCRIPTION,
            "parameters": save_job_provider_schema(),
        },
    }
```

Use that same constant on the existing decorator as
`@tool(SAVE_JOB_NAME, description=SAVE_JOB_DESCRIPTION)`; retain the function
body, injected arguments, and docstring. This prevents the runtime and
provider-only definitions from drifting while still leaving the original
`BaseTool` in ToolNode.

Do not attach the dict as the runtime tool's `args_schema`: ToolNode must keep the
original tool instance and its function annotations so LangGraph continues to
inject `tool_call_id` and `state`. Bind the strict definition only to the model;
keep `_invoke`, `execute_tool`, `allow_running_reentry`, and
`SaveJobInput.model_validate` unchanged.

- [ ] **Step 4: Prove injection and runtime validation still work**

In `build_agent_graph`, create model bindings separately from ToolNode tools:

```python
provider_tools = [
    save_job_openai_tool_schema()
    if candidate.name == SAVE_JOB_NAME
    else candidate
    for candidate in tools
]
chat = bind_chat_tools(base_chat, provider_tools)
```

Add an integration assertion that invokes the unchanged runtime tool through
ToolNode with `state.run_id` and a tool-call ID. It must reach
`approval_required` for a valid source-only call and must return
`INVALID_JOB_INPUT` for a direct invocation with mixed non-empty sources.
Also assert `bundle.tool_node.tools_by_name[SAVE_JOB_NAME] is runtime_tool`, while
the fake model's binding log contains the strict dictionary definition. This is
the executable proof that the model sees the strict definition but ToolNode
still owns the original `BaseTool` with injected `tool_call_id` and state.

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/integration/test_job_tools.py -q
```

Expected: PASS; provider schema is strict, injected fields remain server-owned,
and runtime validation still rejects malformed calls.

- [ ] **Step 5: Run one live synthetic provider-schema probe**

From the repository root, make one bounded synthetic call. It must not contain a
real JD or print provider content:

```powershell
@'
import sys
sys.path.insert(0, "backend")

from app.adapters.shopaikey_chat import build_shopaikey_chat
from app.schemas.jobs import SaveJobInput
from app.tools.jobs import SAVE_JOB_NAME, save_job_openai_tool_schema

model = build_shopaikey_chat().bind_tools(
    [save_job_openai_tool_schema()],
    tool_choice=SAVE_JOB_NAME,
)

def fail() -> None:
    print("SAVE_JOB_PROVIDER_SCHEMA_PROBE=FAIL", file=sys.stderr)
    raise SystemExit(1)

try:
    message = model.invoke(
        "This is a synthetic compatibility probe. Call save_job using only "
        "source=current_message; do not include url or text."
    )
    calls = list(message.tool_calls or [])
    if len(calls) != 1 or calls[0]["name"] != SAVE_JOB_NAME:
        fail()
    validated = SaveJobInput.model_validate(calls[0]["args"])
    if (
        validated.source != "current_message"
        or validated.url is not None
        or validated.text is not None
    ):
        fail()
except SystemExit:
    raise
except Exception:
    fail()
print("SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS")
'@ | & '.\.venv\Scripts\python.exe' -
```

Expected: exit 0 and only `SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS`. Run this probe
before Task 2. A provider schema rejection or malformed call blocks all further
implementation/release work; there is no permissive-schema fallback, hidden
retry, model switch, or argument stripping.

- [ ] **Step 6: Conditionally commit the provider-boundary contract**

Skip this step in the canonical A1/A2/A3 workflow. Run it only when the global
commit policy above explicitly permits worker-owned commits:

```powershell
git add backend/app/schemas/jobs.py backend/app/tools/jobs.py backend/app/agent/graph.py backend/tests/unit/test_shopaikey_chat.py backend/tests/unit/test_job_save_confirmation.py backend/tests/integration/test_job_tools.py
git commit -m "fix: constrain provider save_job source modes"
```

## Task 2: Make the one passive repair use the strict source-only tool

**Files:**

- Modify: `backend/app/adapters/shopaikey_chat.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/tests/fakes/fake_chat_model.py`
- Modify: `backend/tests/unit/test_shopaikey_chat.py`
- Modify: `backend/tests/unit/test_agent_graph.py`

- [ ] **Step 1: Add failing tests for the repair binding**

Extend the existing adapter test's `ChatOpenAI.bind_tools` monkeypatch so the
test is self-contained and proves a forced binding contains only `save_job`:

```python
def test_bind_chat_tools_accepts_one_forced_tool_choice(monkeypatch) -> None:
    model = build_shopaikey_chat(_settings())
    bound_result = object()
    recorded: dict[str, Any] = {}

    def _fake_bind(self: Any, tools: list[Any], **kwargs: Any) -> object:
        recorded["self"] = self
        recorded["tools"] = tools
        recorded["kwargs"] = kwargs
        return bound_result

    monkeypatch.setattr(ChatOpenAI, "bind_tools", _fake_bind)
    tool = save_job_openai_tool_schema()

    bound = bind_chat_tools(model, [tool], tool_choice="save_job")

    assert bound is bound_result
    assert recorded == {
        "self": model,
        "tools": [tool],
        "kwargs": {"tool_choice": "save_job"},
    }
```

In the existing unforced binding test, add
`assert recorded["kwargs"] == {}` so ordinary seven-tool conversation never
inherits the repair-only choice.

In `backend/tests/fakes/fake_chat_model.py`, add one shared fake used by both
`test_agent_graph.py` and `test_chat_api.py`. Its valid repair is deliberately
binding-dependent, not a scripted second response:

```python
from langchain_core.runnables import Runnable, RunnableLambda


class PassiveJdBindingAwareFake(FakeChatModel):
    """Emit a valid repair only for the full strict schema plus forced save_job."""

    mixed_text: str
    preview_value: str
    argument_value: str
    provider_payload_value: str
    permit_valid_repair: bool = True
    binding_log: list[tuple[list[Any], dict[str, Any]]] = Field(default_factory=list)

    @staticmethod
    def _has_full_strict_save_job_schema(tools: list[Any]) -> bool:
        if len(tools) != 1 or not isinstance(tools[0], dict):
            return False
        try:
            function = tools[0]["function"]
            params = function["parameters"]
            one_of = params["oneOf"]
        except (KeyError, TypeError):
            return False
        if function.get("name") != "save_job" or len(one_of) != 3:
            return False

        branches: dict[tuple[str, ...], dict[str, Any]] = {}
        for branch in one_of:
            if (
                not isinstance(branch, dict)
                or branch.get("type") != "object"
                or branch.get("additionalProperties") is not False
                or not isinstance(branch.get("properties"), dict)
            ):
                return False
            required = branch.get("required")
            if not isinstance(required, list):
                return False
            branches[tuple(required)] = branch
        if set(branches) != {("url",), ("text",), ("source",)}:
            return False

        url_props = branches[("url",)]["properties"]
        text_props = branches[("text",)]["properties"]
        current_props = branches[("source",)]["properties"]
        if url_props != {"url": {"type": "string", "minLength": 1}}:
            return False
        if text_props != {"text": {"type": "string", "minLength": 1}}:
            return False
        if set(current_props) != {"source", "preview"}:
            return False
        if current_props["source"] != {
            "type": "string",
            "const": "current_message",
        }:
            return False
        preview = current_props["preview"]
        try:
            preview_props = preview["properties"]
            title_max = preview_props["title"]["anyOf"][0]["maxLength"]
            company_max = preview_props["company"]["anyOf"][0]["maxLength"]
            skills = preview_props["skills"]
        except (KeyError, IndexError, TypeError):
            return False
        return (
            preview.get("type") == "object"
            and preview.get("additionalProperties") is False
            and set(preview_props) == {"title", "company", "skills"}
            and title_max == 160
            and company_max == 160
            and skills.get("maxItems") == 5
            and skills.get("items")
            == {"type": "string", "minLength": 1, "maxLength": 80}
        )

    def _bound_response(
        self,
        messages: list[BaseMessage],
        tools: list[Any],
        kwargs: dict[str, Any],
    ) -> AIMessage:
        self.call_log.append(list(messages))
        strict_and_forced = (
            self._has_full_strict_save_job_schema(tools)
            and kwargs.get("tool_choice") == "save_job"
        )
        valid = self.permit_valid_repair and strict_and_forced
        args = (
            {"source": "current_message"}
            if valid
            else {
                "text": self.mixed_text,
                "source": "current_message",
                "preview": {
                    "title": self.preview_value,
                    "company": self.argument_value,
                },
            }
        )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "save_job",
                    "args": args,
                    "id": f"bind-aware-{len(self.call_log)}",
                    "type": "tool_call",
                }
            ],
            additional_kwargs={
                "provider_payload": self.provider_payload_value,
            },
        )

    def bind_tools(
        self,
        tools: Sequence[Any],
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        bound_tools = list(tools)
        bound_kwargs = dict(kwargs)
        self.binding_log.append((bound_tools, bound_kwargs))
        return RunnableLambda(
            lambda messages: self._bound_response(
                list(messages), bound_tools, bound_kwargs
            )
        )
```

The strict-schema predicate above checks all three complete branch objects,
their exact property sets, current-message const, and preview bounds. With the
current graph there is no forced repair binding, so this fake emits mixed calls
twice and the positive regression is RED. It can return source-only only when
both the strict schema and `tool_choice='save_job'` are present.

Add graph cases for:

1. Plain text then valid `{source: "current_message"}` repair → one ToolNode pass.
2. Mixed `text+source` first response then valid repair → one ToolNode pass.
3. Mixed first and mixed repair → fixed refusal, zero ToolNode passes.
4. Opt-out, sole URL, named `save_job`, greeting, and six-pass tests unchanged.

Instantiate the positive cases with
`PassiveJdBindingAwareFake(mixed_text=jd, preview_value="Synthetic Engineer",
argument_value="Plan13 Labs",
provider_payload_value="PROVIDER-PAYLOAD-SENTINEL-DO-NOT-LOG",
permit_valid_repair=True)`. Use the same explicit fields with
`permit_valid_repair=False` for the repeated-mixed refusal. Retain scripted
`FakeChatModel` only for unrelated precedence/topology cases.

Add this concrete `caplog` sentinel test; it invokes the graph directly and
does not reference any undefined helper:

```python
import logging

from tests.fakes.fake_chat_model import PassiveJdBindingAwareFake


def test_passive_repair_diagnostics_never_log_content_or_arguments(caplog) -> None:
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
    caplog.set_level(logging.WARNING, logger="app.agent.graph")

    out = _bundle(model, [save_job_current_message_tool]).compiled.invoke(
        initial_graph_state(run_id=RUN_ID, user_text=jd)
    )

    assert out[MESSAGES_KEY][-1].content == PASSIVE_JD_NO_CONFIRMATION_TEXT
    repair_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.agent.graph"
        and record.getMessage().startswith("passive_jd_call_rejected")
    ]
    shape = (
        "call_count=1 tool_names=('save_job',) "
        "argument_keys=('preview', 'source', 'text')"
    )
    assert repair_logs == [
        f"passive_jd_call_rejected reason=invalid_first_call {shape}",
        f"passive_jd_call_rejected reason=invalid_repair_call {shape}",
    ]
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
```

- [ ] **Step 2: Run the repair tests and verify failure**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_agent_graph.py -k "bind_chat_tools or passive or opt_out or topology" -q
```

Expected: FAIL because `bind_chat_tools` has no `tool_choice` parameter and the
decision node currently reuses the all-tools unforced binding.

- [ ] **Step 3: Extend the existing binding helper minimally**

In `backend/app/adapters/shopaikey_chat.py`:

```python
def bind_chat_tools(
    model: BaseChatModel,
    tools: Sequence[Any] | None = None,
    *,
    tool_choice: str | None = None,
) -> BaseChatModel | Runnable[Any, Any]:
    if not tools:
        return model
    kwargs: dict[str, Any] = {}
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    return model.bind_tools(list(tools), **kwargs)
```

Do not set strict mode globally or change normal direct-conversation binding.

- [ ] **Step 4: Build one repair runnable from the same model**

In `build_agent_graph`, retain the unbound base model and the already-built strict
provider definitions long enough to create:

```python
save_job_available = SAVE_JOB_NAME in set(tool_names)
chat = bind_chat_tools(base_chat, provider_tools)
save_job_provider_tool = (
    save_job_openai_tool_schema()
    if save_job_available
    else None
)
passive_repair_chat = (
    bind_chat_tools(
        base_chat,
        [save_job_provider_tool],
        tool_choice=SAVE_JOB_NAME,
    )
    if save_job_provider_tool is not None
    else None
)
```

Use `passive_repair_chat.invoke(repair_messages)` exactly once in the obvious-JD
branch. Keep `_is_sole_current_message_save_job_call` as the pre-dispatch gate.
Keep `PASSIVE_JD_NO_CONFIRMATION_TEXT` when that single repaired response is still
invalid. Do not synthesize or normalize a mixed provider call.

Add one focused shape-only diagnostic helper in `graph.py`:

```python
import logging


logger = logging.getLogger(__name__)


def _passive_call_shape(
    message: AIMessage | None,
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    calls = list(message.tool_calls or []) if message is not None else []
    names = tuple(_tool_call_name(call) for call in calls)
    argument_keys = tuple(
        sorted(
            {
                str(key)
                for call in calls
                for key in _tool_call_args(call)
            }
        )
    )
    return len(calls), names, argument_keys


def _log_passive_call_rejection(
    reason: Literal["invalid_first_call", "invalid_repair_call"],
    message: AIMessage | None,
) -> None:
    call_count, tool_names, argument_keys = _passive_call_shape(message)
    logger.warning(
        "passive_jd_call_rejected reason=%s call_count=%d "
        "tool_names=%s argument_keys=%s",
        reason,
        call_count,
        tool_names,
        argument_keys,
    )
```

Call `_log_passive_call_rejection("invalid_first_call", response)` immediately
before the one repair and
`_log_passive_call_rejection("invalid_repair_call", response)` immediately
before the fixed refusal. Those four fields are the complete allowlist. Never
pass the AI message, call object, arguments, argument values, raw user/JD text,
preview, provider payload/response, repair messages, or prompt to the logger.

- [ ] **Step 5: Run focused graph/provider tests**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py -q
```

Expected: PASS; each malformed passive decision gets at most one repair, invalid
calls never reach ToolNode, and tool topology/count/loop assertions remain exact.

- [ ] **Step 6: Conditionally commit the bounded repair**

Skip this step in the canonical A1/A2/A3 workflow. Run it only when the global
commit policy explicitly permits worker-owned commits:

```powershell
git add backend/app/adapters/shopaikey_chat.py backend/app/agent/graph.py backend/tests/fakes/fake_chat_model.py backend/tests/unit/test_shopaikey_chat.py backend/tests/unit/test_agent_graph.py
git commit -m "fix: bind passive JD repair to save_job"
```

## Task 3: Prove confirmation, branch call counts, and durable replay

**Files:**

- Modify: `backend/app/tools/jobs.py`
- Modify: `backend/tests/integration/test_job_tools.py`
- Modify: `backend/tests/integration/test_chat_api.py`

- [ ] **Step 1: Add a binding-aware public-path failing confirmation test**

Use a clear five-line, 300+ character synthetic JD and
`PassiveJdBindingAwareFake` from Task 2. It returns mixed-source on the first
decision and source-only on repair only when the binding has the full strict
union plus forced `save_job`. Assert the public turn ends with:

```python
assert event_names[-1] == "approval_required"
approval = events[-1]["payload"]
assert approval["kind"] == "job_save_confirmation"
assert approval["allowed_actions"] == ["save_job", "cancel_save_job"]
assert approval["card"]["source"] == "current_message"
assert "text" not in str(approval)
assert "message_id" not in str(approval)
```

Before Tasks 1-2, this test is RED because the permissive/unforced binding makes
the fake repeat the mixed call and no `approval_required` event appears.

- [ ] **Step 2: Add exact source-read and side-effect spies**

Use the existing fake invoker/embedder/sync owners and wrap the actual imported
ingest/source functions. Patch the saved-JD evaluation seam to fail if passive
save dispatches it. Add `monkeypatch: pytest.MonkeyPatch` to the existing
`test_save_job_current_message_interrupts_before_dependencies` and public
interrupt/cancel/save test signatures:

```python
from unittest.mock import AsyncMock

import app.tools.jobs as jobs_tools
from app.services import job_evaluation, saved_jobs
from app.services.job_save_confirmation import InitiatingMessage


real_ingest_raw_text = jobs_tools.ingest_raw_text
ingest_spy = AsyncMock(wraps=real_ingest_raw_text)
monkeypatch.setattr(jobs_tools, "ingest_raw_text", ingest_spy)

evaluation_spy = AsyncMock(
    side_effect=AssertionError("passive save must not evaluate")
)
monkeypatch.setattr(saved_jobs, "evaluate_job", evaluation_spy)
monkeypatch.setattr(job_evaluation, "evaluate_job", evaluation_spy)

real_resolve = jobs_tools.resolve_initiating_user_message
source_reads: list[tuple[str, str | None]] = []

async def recording_resolve(session, run_id):
    resolved = await real_resolve(session, run_id)
    content = resolved.content if isinstance(resolved, InitiatingMessage) else None
    source_reads.append((run_id, content))
    return resolved

monkeypatch.setattr(
    jobs_tools,
    "resolve_initiating_user_message",
    recording_resolve,
)
```

Immediately after `approval_required`, assert one and only one durable source
lookup occurred before the interrupt and every automated side-effect spy is zero:

```python
assert source_reads == [(run_id, _PUBLIC_JD_MESSAGE)]
assert ingest_spy.await_count == 0
assert len(invoker.calls) == 0          # JD extraction
assert len(embedder.calls) == 0         # embedding
assert evaluation_spy.await_count == 0  # evaluation dispatch
assert sync.calls == 0                  # Neo4j sync call
assert job_count == 0
assert evaluation_count == 0
assert tool_row.status == "running"
```

These are automated fake/wrapper counters. Do not infer them from a missing
SavedJobCard, and do not later claim that a live browser observed these fake
counters.

- [ ] **Step 3: Make current-message opt-out reuse the pre-interrupt lookup**

The current implementation calls `_resolve_opt_out` and then resolves the same
current message again before interrupt. Refactor only the branch placement so
current-message mode performs one source read, applies opt-out to that resolved
content, and builds the confirmation from it; direct URL/text retain the shared
lookup helper. Remove the current unconditional `_resolve_opt_out` call before
the source-mode branch; otherwise the pre-interrupt count remains two:

```python
if validated.source == SAVE_JOB_SOURCE_CURRENT_MESSAGE:
    async with factory() as session:
        resolved = await resolve_initiating_user_message(session, run_id)
    if isinstance(resolved, SourceLookupFailure):
        return ToolResult(
            ok=False,
            code=resolved.code,
            summary=resolved.summary,
            data=None,
        )
    assert isinstance(resolved, InitiatingMessage)
    if message_has_clear_opt_out(resolved.content):
        return build_cancellation_tool_result()

    decision = interrupt(
        build_job_save_confirmation_projection(
            tool_call_id=tool_call_id,
            content=resolved.content,
            preview=validated.preview,
        )
    )
    action = decision if isinstance(decision, str) else str(decision)
    if action == ACTION_CANCEL_SAVE_JOB:
        return build_cancellation_tool_result()
    if action != ACTION_SAVE_JOB:
        return ToolResult(
            ok=False,
            code=ERROR_INVALID_APPROVAL_ACTION,
            summary=f"unsupported approval action {action!r}",
            data={"action": action},
        )
    return await _ingest_current_message_content(
        factory=factory,
        content=resolved.content,
        invoker=invoker,
        normalizer=normalizer,
        embedding_client=embedding_client,
        driver=driver,
        job_sync_fn=job_sync_fn,
    )

opt_out = await _resolve_opt_out(factory, run_id)
if opt_out is not None:
    return opt_out
return await _ingest_with_deps(
    factory=factory,
    url=validated.url,
    text=validated.text,
    invoker=invoker,
    normalizer=normalizer,
    embedding_client=embedding_client,
    url_fetcher=url_fetcher,
    driver=driver,
    job_sync_fn=job_sync_fn,
)
```

Delete the separate post-decision `reloaded` resolver block. LangGraph
re-enters the tool from the start after `stream_resume` has
accepted the action, so the branch's one `resolved` lookup is the one fresh
accepted-resume reload and its content flows directly to ingest. The complete
save contract is one initial pre-interrupt lookup plus one re-entry reload (two
source-message reads total), never one total lookup and never a third explicit
reload. Direct-mode behavior is only moved, not changed.

- [ ] **Step 4: Exercise cancel, accepted save, dedupe, and replay**

Extend the same fixture:

- `cancel_save_job`: counters stay zero; terminal ToolResult is
  `committed=false`, `outcome=cancelled`; no Job row. LangGraph re-entry performs
  one fresh source read before the resumed interrupt returns cancel, so
  `len(source_reads) == 2`, but there is no ingest/extraction/embed/evaluate/
  graph side effect.
- `save_job`: there was exactly one source lookup before interrupt and exactly
  one re-entry reload after the accepted resume (`len(source_reads) == 2`);
  both resolve the same run and exact durable body. Ingest/extraction/embedding/
  Neo4j sync counts become one, evaluation stays zero, and the first run creates.
- repeated terminal resume: source reads remain two and there is no additional
  ingest, extraction, embedding, evaluation, SQLite, or graph call.
- repeated content in a new confirmed run returns the same Job identity through
  exact-hash dedupe; record that run's own one pre-interrupt lookup plus one
  accepted reload separately.
- direct URL/text paths: no passive confirmation and existing outcomes remain
  `created|returned|retried`.

- [ ] **Step 5: Run the focused integration gate**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py -q
```

Expected: PASS with one durable running execution before action, exact save/cancel
outcomes, one pre-interrupt lookup plus one accepted-save reload, zero automatic
evaluation, and no duplicate side effects.

- [ ] **Step 6: Conditionally commit the public-path regression coverage**

Skip this step in the canonical A1/A2/A3 workflow. Run it only when the global
commit policy explicitly permits worker-owned commits:

```powershell
git add backend/app/tools/jobs.py backend/tests/integration/test_job_tools.py backend/tests/integration/test_chat_api.py
git commit -m "test: prove passive JD confirmation side effects"
```

## Task 4: Name the active-CV source dialog accessibly

**Files:**

- Modify: `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx`
- Modify: `frontend/src/test/active-cv-source.test.tsx`
- Modify: `frontend/src/test/assistant-response.test.tsx`

- [ ] **Step 1: Add the failing role/name assertion**

After opening the citation, assert:

```tsx
const dialog = screen.getByRole('dialog', {name: 'Nguồn từ CV'});
expect(dialog).toHaveAttribute('aria-label', 'Nguồn từ CV');
expect(within(dialog).getByText('Nguồn từ CV')).toBeInTheDocument();
```

Keep existing assertions for exact records, partial disclosure, original-CV
action, zero network fetch, Escape, close button, and trigger-focus restoration.

- [ ] **Step 2: Run the focused test and verify it fails**

```powershell
Set-Location frontend
npm test -- --run src/test/active-cv-source.test.tsx src/test/assistant-response.test.tsx
```

Expected: FAIL because the native dialog has no accessible name.

- [ ] **Step 3: Add the minimal accessible name**

In `ActiveCvSourceDialog.tsx`:

```tsx
<Dialog
  isOpen={isOpen}
  onOpenChange={onOpenChange}
  purpose="info"
  aria-label={ACTIVE_CV_SOURCE_DIALOG_TITLE}
  width={520}
  maxHeight="75vh"
  data-testid="jobagent-active-cv-source-dialog"
>
```

Do not replace `DialogHeader`, alter focus code, or add a hand-built modal.

- [ ] **Step 4: Run frontend source/dialog gates**

```powershell
Set-Location frontend
npm test -- --run src/test/active-cv-source.test.tsx src/test/assistant-response.test.tsx src/test/chat-page.test.tsx
npm run typecheck
```

Expected: PASS; the dialog is found by exact role/name and existing evidence
behavior remains unchanged.

- [ ] **Step 5: Conditionally commit the accessibility repair**

Skip this step in the canonical A1/A2/A3 workflow. Run it only when the global
commit policy explicitly permits worker-owned commits:

```powershell
git add frontend/src/features/chat/components/ActiveCvSourceDialog.tsx frontend/src/test/active-cv-source.test.tsx frontend/src/test/assistant-response.test.tsx
git commit -m "fix: name active CV source dialog"
```

## Task 5: Add deterministic Plan 1 negative diagnostic tests

**Files:**

- Create: `backend/tests/unit/test_phase0_diagnostics.py`
- Modify only if a failing test proves a defect:
  `infrastructure/scripts/shopaikey_diag/common.py`
- Modify only if a failing test proves a defect:
  `infrastructure/scripts/shopaikey_diag/runner.py`
- Modify only if a failing test proves a defect:
  `infrastructure/scripts/shopaikey_diag/embeddings.py`
- Modify only if a failing test proves a defect:
  `infrastructure/scripts/shopaikey_diag/chat_checks.py`
- Modify only if a failing test proves a defect:
  `infrastructure/scripts/verify_pdf_extraction.py`

- [ ] **Step 1: Create deterministic ShopAIKey failure tests**

Add `infrastructure/scripts` to `sys.path`, import `shopaikey_diag.chat_checks`,
`common`, `embeddings`, and `runner`, then use these concrete helpers so every
failure also exercises the common terminal/redaction formatter:

```python
import ast
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "infrastructure" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import verify_pdf_extraction as pdf_diag  # noqa: E402
from shopaikey_diag import chat_checks, common, embeddings, runner  # noqa: E402


SECRET = "test-secret-never-print"
SETTINGS = common.Settings(
    base_url="https://provider.invalid/v1",
    api_key=SECRET,
    llm_model=common.LOCKED_CHAT_MODEL,
    embedding_model=common.LOCKED_EMBED_MODEL,
    embedding_dimensions=common.LOCKED_DIMENSIONS,
)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
    response = httpx.Response(status, request=request, text="synthetic failure")
    return httpx.HTTPStatusError("synthetic status", request=request, response=response)


def _assert_terminal_failure(error: common.DiagnosticError, capsys) -> None:
    assert common.emit_failure(
        code=error.code,
        capability=error.capability,
        detail=error.detail,
        secret=SECRET,
    ) != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert f"ERROR={error.code}:" in captured.err
    assert "SHOPAIKEY_COMPATIBILITY=FAIL" in captured.out
    assert SECRET not in combined
    assert "Authorization" not in combined
    assert "Bearer " not in combined


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (httpx.ReadTimeout("slow"), "TIMEOUT"),
        (_status_error(429), "RATE_LIMIT"),
        (ValueError("not-json"), "MALFORMED_RESPONSE"),
    ],
)
def test_diagnostic_normalizes_transport_failures(error, expected_code, capsys):
    mapped = common.classify_http_error(error, "basic_chat", SECRET)
    assert mapped.code == expected_code
    _assert_terminal_failure(mapped, capsys)


def test_diagnostic_rejects_malformed_nonstream_json(capsys) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, request=request, text="{not-json")
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(common.DiagnosticError) as caught:
            common.request_json(
                client,
                "POST",
                f"{SETTINGS.base_url}/chat/completions",
                secret=SECRET,
                capability="basic_chat",
            )
    assert caught.value.code == common.CODE_MALFORMED
    _assert_terminal_failure(caught.value, capsys)


def test_diagnostic_rejects_missing_chat_and_embedding_models(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(chat_checks, "request_json", lambda *_a, **_k: {"data": []})
    with pytest.raises(common.DiagnosticError) as caught:
        chat_checks.check_model_discovery(object(), SETTINGS)
    assert caught.value.code == common.CODE_MODEL_ABSENCE
    assert common.LOCKED_CHAT_MODEL in caught.value.detail
    assert common.LOCKED_EMBED_MODEL in caught.value.detail
    _assert_terminal_failure(caught.value, capsys)


@pytest.mark.parametrize(
    ("data", "expected_count", "expected_code"),
    [
        ([{"index": 0, "embedding": [0.0] * 1535}], 1, "DIMENSION_MISMATCH"),
        (
            [
                {"index": 1, "embedding": [0.0] * 1536},
                {"index": 0, "embedding": [1.0] * 1536},
            ],
            2,
            "ORDERING_MISMATCH",
        ),
        (
            [
                {"index": 0, "embedding": [0.0] * 1536},
                {"index": 0, "embedding": [1.0] * 1536},
            ],
            2,
            "ORDERING_MISMATCH",
        ),
    ],
)
def test_diagnostic_rejects_dimension_and_index_order(
    data, expected_count, expected_code, capsys
) -> None:
    with pytest.raises(common.DiagnosticError) as caught:
        embeddings._validate_data(
            data,
            expected_count=expected_count,
            capability="scalar_batch_embeddings",
        )
    assert caught.value.code == expected_code
    _assert_terminal_failure(caught.value, capsys)
```

```python
def test_runner_rejects_unlocked_missing_chat_model(monkeypatch, capsys) -> None:
    bad = common.Settings(
        base_url=SETTINGS.base_url,
        api_key=SECRET,
        llm_model="missing-chat-model",
        embedding_model=SETTINGS.embedding_model,
        embedding_dimensions=SETTINGS.embedding_dimensions,
    )
    monkeypatch.setattr(runner, "load_settings", lambda **_kwargs: bad)

    assert runner.main() == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "ERROR=MODEL_ABSENCE:" in captured.err
    assert "failed_capability=config" in captured.out
    assert "SHOPAIKEY_COMPATIBILITY=FAIL" in captured.out
    assert SECRET not in combined
    assert "Authorization" not in combined
    assert "Bearer " not in combined
```

The lower-level cases own provider-payload/embedding mappings; this case owns
CLI orchestration. Production diagnostic code changes are allowed only if one
of these RED cases proves the existing mapping or redaction is wrong.

- [ ] **Step 2: Add pypdf negative aggregate tests**

Monkeypatch the existing evaluators; do not create new PDFs. Define every row
factory in the test file:

```python
def _digital_row(path: Path, success: bool) -> dict[str, object]:
    return {
        "name": path.name,
        "kind": "digital",
        "pages": 1,
        "normal_non_ws": 400 if success else 0,
        "layout_non_ws": 400 if success else 0,
        "normal_norm_len": 400 if success else 0,
        "layout_norm_len": 400 if success else 0,
        "normal_ok": success,
        "layout_ok": success,
        "success": success,
        "status": "PASS" if success else "FAIL",
    }


def _digital_evaluator(pass_count: int):
    passing = set(pdf_diag.DIGITAL_FIXTURES[:pass_count])
    return lambda path: _digital_row(path, path.name in passing)


def _image_row(path: Path, *, accepted: bool) -> dict[str, object]:
    return {
        "name": path.name,
        "kind": "image_only",
        "pages": 1,
        "normal_non_ws": 400 if accepted else 0,
        "layout_non_ws": 0,
        "normal_norm_len": 400 if accepted else 0,
        "layout_norm_len": 0,
        "normal_ok": accepted,
        "layout_ok": False,
        "accepted": accepted,
        "status": "UNEXPECTED_TEXT" if accepted else pdf_diag.NO_EXTRACTABLE_TEXT,
    }


def test_pdf_gate_fails_below_four_digital_passes(monkeypatch, capsys):
    monkeypatch.setattr(pdf_diag, "evaluate_digital", _digital_evaluator(3))
    monkeypatch.setattr(
        pdf_diag,
        "evaluate_image_only",
        lambda path: _image_row(path, accepted=False),
    )
    assert pdf_diag.main() == 1
    output = capsys.readouterr()
    assert "digital_below_threshold:3/5" in output.err
    assert "PYPDF_COMPATIBILITY=FAIL" in output.out


def test_pdf_gate_fails_when_image_only_is_accepted(monkeypatch, capsys):
    monkeypatch.setattr(pdf_diag, "evaluate_digital", _digital_evaluator(5))
    monkeypatch.setattr(
        pdf_diag,
        "evaluate_image_only",
        lambda path: _image_row(path, accepted=True),
    )
    assert pdf_diag.main() == 1
    output = capsys.readouterr()
    assert "image_only_not_rejected:UNEXPECTED_TEXT" in output.err
    assert "PYPDF_COMPATIBILITY=FAIL" in output.out


def test_pdf_diagnostic_introduces_no_ocr_dependency() -> None:
    tree = ast.parse(
        (REPO_ROOT / "infrastructure/scripts/verify_pdf_extraction.py").read_text(
            encoding="utf-8"
        )
    )
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".", 1)[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(
        {"pytesseract", "ocrmypdf", "easyocr", "pdf2image"}
    )
```

No OCR/parser fallback or new fixture is introduced.

- [ ] **Step 3: Run the diagnostic tests**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_phase0_diagnostics.py tests/unit/test_embedding_adapter.py tests/unit/test_pdf_extraction.py -q
```

Expected: all required timeout/429/malformed/missing-model/dimension/ordering/PDF
negative cases pass without a network call.

- [ ] **Step 4: Run the real diagnostics once with the project interpreter**

From the repository root:

```powershell
& '.\.venv\Scripts\python.exe' infrastructure/scripts/verify_pdf_extraction.py
& '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_shopaikey.py
```

Expected: `PYPDF_COMPATIBILITY=PASS` and
`SHOPAIKEY_COMPATIBILITY=PASS`. The ShopAIKey command is the one intentional live
provider call for this task; output must contain no secret/header.

- [ ] **Step 5: Conditionally commit diagnostic coverage**

Skip this step in the canonical A1/A2/A3 workflow. Run it only when the global
commit policy explicitly permits worker-owned commits:

```powershell
git add backend/tests/unit/test_phase0_diagnostics.py
git add infrastructure/scripts/shopaikey_diag/common.py infrastructure/scripts/shopaikey_diag/runner.py infrastructure/scripts/shopaikey_diag/embeddings.py infrastructure/scripts/shopaikey_diag/chat_checks.py infrastructure/scripts/verify_pdf_extraction.py
git commit -m "test: cover Phase 0 diagnostic failures"
```

Before committing, unstage unchanged diagnostic files so the commit contains only
the new test plus any root-cause repair actually required.

## Task 6: Create the Plan 13 traceability and evidence contract

**Files:**

- Create: `docs/acceptance/plan13_acceptance_ledger.md`
- Modify: `docs/acceptance/full_functional_test_matrix.md`
- Modify: `docs/acceptance/cv_manager_checklist.md`

- [ ] **Step 1: Add Plan 12/13 cases to the functional matrix**

Append a section with these exact IDs:

```text
P12-RSP-01, P12-RSP-02
P12-CV-01, P12-CV-02, P12-CV-03, P12-CV-04, P12-CV-05
P12-JD-01, P12-JD-02, P12-JD-03, P12-JD-04, P12-JD-05
P12-REG-01
P13-JD-01, P13-JD-02, P13-JD-03, P13-A11Y-01
P13-DIAG-01, P13-CV-01, P13-EVID-01, P13-REG-01
```

Each row names automated/browser method, expected behavior, and the Plan 13 ledger
as execution evidence. Do not mark the matrix itself PASS.

- [ ] **Step 2: Create the dated ledger with explicit status columns**

Start the ledger with:

```markdown
| ID | Requirement/source | Procedure or command | Status | Date (UTC) | HEAD / Compose project | Failure/log evidence | Resolution/notes |
|---|---|---|---|---|---|---|---|
```

Add one requirement row for every ID above. Before execution, use `NOT RUN`;
after execution, use only `PASS`, `FAIL`, `BLOCKED`, or `SKIPPED (reason)`.
Record actual run IDs and sanitized counts; never paste raw JD/CV/provider
content.

Immediately below the requirement table, seed a **Preserved pre-repair failures**
table. These rows are historical evidence and must never be edited into PASS:

```markdown
| Attempt ID | UTC date | Product HEAD / project | Run ID | Observed result | Root cause / disposition |
|---|---|---|---|---|---|
| BASE-PJD-01 | 2026-07-19 | `887d4f6` / pre-repair audit stack | `4971481e-0e7b-42ca-8d7b-184d314be2e9` | FAIL: `tool_count=0`; fixed no-confirmation response | Provider-visible `save_job` schema was permissive; preserve and rerun a new synthetic attempt after repair. |
| BASE-PJD-02 | 2026-07-19 | `887d4f6` / pre-repair audit stack | `d1fab78d-a4ff-4a9d-ad06-75d5cd229c8a` | FAIL: `tool_count=0`; fixed no-confirmation response | Same provider-boundary failure; preserve this first result. |
| BASE-PJD-03 | 2026-07-19 | `887d4f6` / pre-repair audit stack | `5a12595d-7af4-4b64-a03b-433c08d87293` | FAIL: `tool_count=0`; fixed no-confirmation response | Long MISA-like case; preserve this first result and use only synthetic content in Git. |
```

Add a second **Execution attempts** table keyed by `P12-*`/`P13-*` plus an
attempt suffix (`P13-JD-02-A1`, `P13-JD-02-A2`). A rerun appends a row; it never
overwrites A1. The requirement row may summarize the latest accepted outcome
only when it links all prior attempts.

Finally add a separate **Non-blocking warnings (out of scope)** table with
`warning`, `command/surface`, `classification`, `behavioral impact`, and
`disposition` columns. Put jsdom `window.scrollTo`, duplicate synthetic React
key, Vite bundle size, `aiosqlite` datetime deprecation, and bare-host
Python/pypdf environment warnings there only. Never mix them into functional
FAIL rows or use them to excuse a failed command.

- [ ] **Step 3: Add the archived-CV rerun contract**

Add a Plan 13 section to `cv_manager_checklist.md` that references ledger row
`P13-CV-01` and requires this exact sequence:

1. Upload/approve synthetic CV A.
2. Upload/approve synthetic CV B; A becomes archived.
3. Reprocess archived A and approve it active.
4. Verify bounded active-CV evidence and active graph branch use A.
5. Delete archived B through the browser confirmation.
6. Verify B's row/file/owned graph/run data disappear while A and shared Jobs/
   Skills remain.

- [ ] **Step 4: Validate documentation links and conditionally commit**

```powershell
rg -n "P12-|P13-|current_message|job_save_confirmation|Nguồn" docs/acceptance/full_functional_test_matrix.md docs/acceptance/plan13_acceptance_ledger.md docs/acceptance/cv_manager_checklist.md
git diff --check
```

In the canonical A1/A2/A3 workflow, stop after validation. Only when the global
commit policy explicitly permits worker-owned commits, run:

```powershell
git add docs/acceptance/full_functional_test_matrix.md docs/acceptance/plan13_acceptance_ledger.md docs/acceptance/cv_manager_checklist.md
git commit -m "docs: add Plan 13 acceptance ledger"
```

Expected: every P12/Plan13 requirement has a traceable execution row and no stale
PASS claim exists before the run.

## Task 7: Run focused/full gates and browser acceptance

**Files:**

- Modify: `docs/acceptance/plan13_acceptance_ledger.md`
- Modify: `docs/acceptance/cv_manager_checklist.md`

- [ ] **Step 1: Run backend focused and full gates on the final candidate**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py tests/unit/test_phase0_diagnostics.py -q
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py tests/integration/test_active_cv_tool.py tests/integration/test_cv_manager_api.py tests/integration/test_cv_manager_deletion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q
Set-Location ..
```

Expected: every command exits 0; normal tests make no real provider call.

- [ ] **Step 2: Run frontend focused and full gates**

```powershell
Set-Location frontend
npm test -- --run src/test/active-cv-source.test.tsx src/test/assistant-response.test.tsx src/test/job-save-confirmation.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts
npm test -- --run src/test/cv-manager.test.tsx src/test/cv-manager-api.test.ts src/test/empty-match-card.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/approval-card.test.tsx
npm test -- --run
npm run lint
npm run typecheck
npm run build
Set-Location ..
```

Expected: all tests/static/build pass. Record `window.scrollTo`, duplicate
synthetic key, bundle-size, and deprecation messages as non-blocking warnings only
when they do not fail a command or change behavior.

- [ ] **Step 3: Validate scope and plan structure**

```powershell
python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json
git diff --check
git status --short
```

Expected: plan structure valid; no migration, endpoint, dependency, tool-count,
Agent/ToolNode, evaluation, security, mobile, real-data, or secret drift.

- [ ] **Step 4: Preflight fixed ports and start the named disposable stack**

```powershell
$composeArgs = @("--env-file", ".env", "-f", "infrastructure/docker-compose.yml")
$normalProject = "infrastructure"
$smokeProject = "jobagent-plan13-smoke"
$statePath = Join-Path ([System.IO.Path]::GetTempPath()) "jobagent-plan13-stack-state.json"
$expectedServices = @("backend", "frontend", "neo4j")

if (Test-Path -LiteralPath $statePath) {
    throw "A prior Plan 13 stack-state file exists; recover that attempt before starting"
}

$configuredServices = @(
    docker compose @composeArgs config --services | Where-Object { $_ }
)
if (@(Compare-Object ($expectedServices | Sort-Object) ($configuredServices | Sort-Object)).Count -ne 0) {
    throw "Compose must contain exactly backend, frontend, and neo4j"
}

$existingSmokeServices = @(
    docker compose @composeArgs -p $smokeProject ps -a --services |
        Where-Object { $_ }
)
if ($existingSmokeServices.Count -ne 0) {
    throw "Preserve and inspect the existing jobagent-plan13-smoke attempt before rerunning"
}

$normalRunning = @(
    docker compose @composeArgs -p $normalProject ps --status running --services |
        Where-Object { $_ }
)
$unexpectedNormal = @($normalRunning | Where-Object { $_ -notin $expectedServices })
if ($unexpectedNormal.Count -ne 0 -or $normalRunning.Count -notin @(0, 3)) {
    throw "Normal workspace stack is partial or unexpected; do not change it automatically"
}

@{
    normal_project = $normalProject
    normal_was_running = ($normalRunning.Count -eq 3)
} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8

if ($normalRunning.Count -eq 3) {
    docker compose @composeArgs -p $normalProject stop frontend backend neo4j
    if ($LASTEXITCODE -ne 0) {
        docker compose @composeArgs -p $normalProject up -d --wait --wait-timeout 180
        Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue
        throw "Could not stop only the normal workspace containers"
    }
}

$fixedPorts = @(5173, 8000, 7474, 7687)
$listeners = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $fixedPorts }
)
if ($listeners.Count -ne 0) {
    if ($normalRunning.Count -eq 3) {
        docker compose @composeArgs -p $normalProject up -d --wait --wait-timeout 180
    }
    Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue
    throw "A non-smoke process still owns one of fixed ports 5173/8000/7474/7687"
}

docker compose @composeArgs -p $smokeProject up --build -d --wait --wait-timeout 180
if ($LASTEXITCODE -ne 0) {
    docker compose @composeArgs -p $smokeProject down --volumes --remove-orphans
    if ($normalRunning.Count -eq 3) {
        docker compose @composeArgs -p $normalProject up -d --wait --wait-timeout 180
    }
    Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue
    throw "Disposable smoke stack failed to start"
}

$health = Invoke-RestMethod http://127.0.0.1:8000/api/health
if ($health.overall -ne "available") {
    throw "Disposable smoke health is not available; run Step 6 recovery"
}
```

Expected: exactly frontend/backend/neo4j are healthy and health is `available`.
Because Compose publishes fixed ports, the normal `infrastructure` project is
detected explicitly. If it was fully running, only its three containers are
stopped (never `down --volumes`); a partial normal stack blocks the run. Keep the
temporary state file until Step 6 so the prior normal state can be restored.

- [ ] **Step 5: Execute the browser flow as a user**

At desktop width, use the in-app browser and perform every product action through
the visible frontend at `http://localhost:5173`. The execution worker must use
`browser:control-in-app-browser` (or the current equivalent first-party browser
control skill) for clicks, typing, refresh, role inspection, network, and console
evidence; direct API calls do not substitute for these user actions:

1. Create the two-CV disposable state and complete the archived activation/delete
   sequence from Task 6.
2. Ask one active-CV fact question, click **Nguồn**, and verify the browser role is
   `dialog` with name **Nguồn từ CV**; close by button and Escape; verify focus
   returns and **Mở CV gốc** opens the retained attachment without an evidence
   fetch.
3. Paste a fresh short structured English synthetic JD containing the harmless
   token `P13-JD-EN-SENTINEL`. Verify exactly one card, capture its
   run/execution IDs and pre-action evidence, then click
   **KhÃ´ng lÆ°u**. Verify a terminal cancelled result and no SavedJobCard.
4. Paste a different structured Vietnamese synthetic JD containing
   `P13-JD-VI-SENTINEL`. While its card is still pending, refresh the page.
   Verify history rehydrates the same run ID, same
   running `save_job` execution ID, same bounded card, and both actions. Only then
   click **LÆ°u JD** and verify the terminal saved result.
5. Paste the exact same Vietnamese synthetic JD again, confirm it, and verify the
   returned/deduplicated outcome uses the same Job identity with no evaluation.
6. Paste the synthetic long MISA-like JD containing
   `P13-JD-LONG-SENTINEL` as the third distinct obvious-JD case. Verify one
   bounded card and then click **KhÃ´ng lÆ°u** so the case finishes with
   a terminal cancellation; do not leave this third run pending.
7. Before each card action, record browser-owned evidence only: SQLite Job and
   `job_evaluations` row deltas, Neo4j `:Job` node delta, durable run/tool state,
   network requests, browser console, and sanitized backend log lines. The
   network must contain no evaluate request. Exact extraction/embedding/
   evaluation/Neo4j-call counters belong only to Task 3 automated spies and must
   not be claimed as live browser observations.
8. Send the sole URL `https://example.com/jobs/plan13-synthetic-engineer` and
   verify it follows the existing direct-URL path without a passive card. Then
   send this exact explicit-direct-text request and verify it calls direct text,
   never `source=current_message`, shows no passive card, and never evaluates:

   ```text
   Please call save_job exactly once with text="Job title: Synthetic API Engineer. Company: Plan13 Labs. Responsibilities: build local APIs and deterministic tests. Requirements: Python, FastAPI, SQL, and Docker. Location: Hanoi. This is synthetic test data." Do not use source=current_message and do not call match_jobs.
   ```

9. Paste a structured synthetic JD ending with the exact line
   `KhÃ´ng lÆ°u JD nÃ y.` and verify opt-out creates no tool/card/mutation. Send the
   ambiguous prose `TÃ´i Ä‘ang suy nghÄ© vá» hÃ nh trÃ¬nh nghá» nghiá»‡p vÃ  cÃ¡ch há»c tá»‘t hÆ¡n trong nÄƒm nay.` repeated to more than 300 non-whitespace characters with
   no JD markers; verify normal conversation and zero forced save.
10. Record the exact browser network request order (including history GET after
    refresh and one resume POST after the click), visible copy, console, actual
    run IDs, and before/after counts in the append-only execution-attempt rows.
    Any unexpected console error, failed request, duplicate resume, or mismatch
    between visible and durable state makes that attempt FAIL; only the separately
    listed known warnings may remain non-blocking.

For SQLite/evaluation deltas and Neo4j `:Job` deltas, take sanitized support
snapshots before/after the browser action without invoking a mutation endpoint:

```powershell
$composeArgs = @("--env-file", ".env", "-f", "infrastructure/docker-compose.yml")
$smokeProject = "jobagent-plan13-smoke"
docker compose @composeArgs -p $smokeProject exec -T backend python -c "import sqlite3; c=sqlite3.connect('/data/jobagent.db'); print('jobs=' + str(c.execute('select count(*) from job_posts').fetchone()[0]) + ' evaluations=' + str(c.execute('select count(*) from job_evaluations').fetchone()[0]))"
docker compose @composeArgs -p $smokeProject exec -T neo4j sh -lc 'u="${NEO4J_AUTH%%/*}"; p="${NEO4J_AUTH#*/}"; cypher-shell -a bolt://127.0.0.1:7687 -u "$u" -p "$p" --format plain "MATCH (j:Job) RETURN count(j) AS jobs"'
$backendLogs = @(docker compose @composeArgs -p $smokeProject logs --no-color backend 2>&1)
$rawSentinels = @(
    "P13-JD-EN-SENTINEL",
    "P13-JD-VI-SENTINEL",
    "P13-JD-LONG-SENTINEL"
)
foreach ($sentinel in $rawSentinels) {
    if (($backendLogs -join "`n").Contains($sentinel)) {
        throw "Backend logs exposed synthetic raw-JD sentinel $sentinel"
    }
}
$repairLines = @($backendLogs | Select-String "passive_jd_call_rejected")
$invalidRepairLine = @(
    $repairLines | Where-Object {
        $_.Line -notmatch "reason=(invalid_first_call|invalid_repair_call) call_count=[0-9]+ tool_names=.* argument_keys=.*"
    }
)
if ($invalidRepairLine.Count -ne 0) {
    throw "Repair diagnostic log escaped the approved shape-only format"
}
$repairLines
```

Use the browser's **Agent runs** panel plus `/api/chat/history` and
`/api/observability/runs` network responses for durable execution state. Inspect
backend logs only for the fixed sanitized diagnostic fields and assert the
synthetic raw/preview/provider/prompt sentinels do not occur; do not paste a full
provider response, prompt, or JD into the ledger.

Any failed row remains `FAIL` with the observed log and root-cause hypothesis. Do
not rerun silently and overwrite the first failure.

- [ ] **Step 6: Tear down only smoke volumes and restore prior normal state**

```powershell
$composeArgs = @("--env-file", ".env", "-f", "infrastructure/docker-compose.yml")
$smokeProject = "jobagent-plan13-smoke"
$statePath = Join-Path ([System.IO.Path]::GetTempPath()) "jobagent-plan13-stack-state.json"
if (-not (Test-Path -LiteralPath $statePath)) {
    throw "Missing Plan 13 stack-state file; inspect projects before any teardown"
}
$prior = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json

docker compose @composeArgs -p $smokeProject down --volumes --remove-orphans
$smokeDownExit = $LASTEXITCODE

if ($prior.normal_was_running -eq $true) {
    docker compose @composeArgs -p $prior.normal_project up -d --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke teardown ran, but the prior normal workspace stack did not restore"
    }
    $restored = Invoke-RestMethod http://127.0.0.1:8000/api/health
    if ($restored.overall -ne "available") {
        throw "Restored normal stack is not healthy"
    }
}

Remove-Item -LiteralPath $statePath
if ($smokeDownExit -ne 0) {
    throw "Named smoke teardown failed; normal-stack restoration was still attempted"
}
```

Expected: only `jobagent-plan13-smoke` containers and its three named volumes are
removed. Normal workspace volumes are never deleted. If the normal
`infrastructure` stack was running before preflight, it is restored healthy; if
it was stopped, it remains stopped. Run this recovery step even when a browser
row fails or the smoke health check aborts acceptance.

- [ ] **Step 7: Update evidence rows and conditionally commit**

Replace `NOT RUN` with the actual result/date/HEAD/project/run IDs and concise
sanitized logs. Preserve earlier failed attempts rather than editing them into
passes. In the canonical A1/A2/A3 workflow, do not stage or commit. Only when the
global commit policy explicitly permits worker-owned commits, run:

```powershell
git add docs/acceptance/plan13_acceptance_ledger.md docs/acceptance/cv_manager_checklist.md
git commit -m "test: record Plan 13 release evidence"
```

Do not commit screenshots containing real data, databases, provider transcripts,
or secrets.

## Task 8: Final regression/scope review and handoff

**Files:**

- Review: every file changed by Tasks 1-7
- Modify only if evidence is stale: `README.md`
- Modify: `docs/acceptance/plan13_acceptance_ledger.md`

- [ ] **Step 1: Verify design requirement coverage**

Map every section of
`docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md` to one
completed task/ledger row. Required mappings:

```text
Provider union -> Tasks 1, 2; P13-JD-01
Repair/refusal -> Tasks 2, 3; P13-JD-02
Durable reads / zero side effects -> Task 3; P12-JD-02/04/05; P13-JD-03; P13-EVID-01
Dialog name -> Task 4; P13-A11Y-01
Plan 1 negatives -> Task 5; P13-DIAG-01
Archived-CV browser evidence -> Tasks 6, 7; P13-CV-01
Architecture/full regressions -> Tasks 2, 7, 8; P13-REG-01
Warnings/out-of-scope -> Task 6 separate non-blocking-warning table
```

- [ ] **Step 2: Inspect architectural invariants**

```powershell
rg -n "TOOL_LOOP_LIMIT|DECISION_NODE_NAME|TOOLS_NODE_NAME|SAVE_JOB_NAME" backend/app/agent/graph.py backend/app/tools/registry.py
rg -n "@router\.(get|post|delete|put|patch)" backend/app/api
git diff -- backend/migrations frontend/package.json frontend/package-lock.json infrastructure/docker-compose.yml
```

Expected: one Agent decision node, one ToolNode, seven tools, six passes, unchanged
public routes, no migration/package/Compose change.

- [ ] **Step 3: Run fresh final verification after the last edit**

Repeat the full backend/frontend commands from Task 7 and:

```powershell
python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json
git diff --check
git status --short
```

Expected: all gates pass from the final working tree. The approved canonical
`docs/tasks/task_13.md` exists before A1 execution but is not rewritten by this
implementation plan. The pre-existing unrelated deletion of
`docs/superpowers/specs/2026-07-19-frontend-functional-e2e-audit-design.md`
remains untouched and is not staged by this plan.

- [ ] **Step 4: Conditionally commit only a necessary README/evidence correction**

If implementation changed an existing documented command or current-status claim,
update that exact paragraph. In the canonical A1/A2/A3 workflow, leave the
reviewed files for A3/orchestrator. Only in an explicitly authorized
worker-commit workflow run:

```powershell
git add README.md docs/acceptance/plan13_acceptance_ledger.md
git commit -m "docs: finalize Plan 13 verification"
```

If README remains accurate, skip this commit and record `README unchanged` in the
ledger; do not create a no-op commit.

---

## Completion conditions

Implementation is complete only when all of these are true on the same final HEAD:

- Three fresh obvious JDs each produce one bounded confirmation card.
- Mixed provider calls never reach ToolNode; the single strict repair either
  produces `source='current_message'` or returns truthful refusal.
- The live schema probe accepts the full three-branch definition; unsupported
  provider schema is a blocking failure with no permissive fallback.
- Automated spies prove zero pre-action/cancel ingest, extraction, embedding,
  evaluation dispatch, and Neo4j sync calls; the first created save performs one
  of each required ingestion call, while replay/dedupe counts remain exact and
  evaluation remains zero.
- Current-message mode performs exactly one durable source lookup before
  the initial interrupt. Accepted save re-entry performs exactly one additional
  durable reload and ingests that fresh content (two reads total, never three).
  Cancel re-entry may perform the same fresh read but performs no ingestion or
  other side effect.
- Browser evidence separately proves SQLite Job/evaluation and Neo4j deltas,
  durable execution state, network/console behavior, and sanitized logs; it does
  not claim fake/provider call counters.
- The source dialog has accessible role/name **Nguồn từ CV** and preserves exact
  evidence, no-fetch, original-PDF, close/Escape/focus behavior.
- Plan 1 negative diagnostics and PDF gates have deterministic tests.
- Archived-CV activation/reprocess/delete and P12/Plan13 browser evidence are
  recorded with date, HEAD, Compose project, run IDs, failures, and resolution.
- Pending-card refresh/history rehydration is proved before action, and all three
  distinct obvious-JD runs end terminally (including cancellation of the long
  MISA-like case).
- Focused/full/static/build/Compose/browser/plan-validator/scope gates pass.
- The named smoke project alone loses volumes, and the prior normal workspace
  stack is restored to its exact running/stopped condition.
- The portfolio was approved and canonical `docs/tasks/task_13.md` was created
  before implementation. No migration, endpoint, dependency, extra
  Agent/tool/node, automatic evaluation, security/mobile work, or non-blocking-
  warning cleanup is introduced.
