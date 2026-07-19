# Plan 13 Repair And Revalidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable passive pasted-JD confirmation, give the active-CV evidence dialog an accessible name, and close the audited diagnostic/browser/evidence gaps without changing JobAgent's architecture or public product contracts.

**Architecture:** Keep `SaveJobInput` as the runtime source-of-truth and give the existing `save_job` tool a strict provider-visible three-branch schema. The existing decision node performs one forced, source-only repair before its truthful refusal; the existing ToolNode/interrupt path remains the sole mutation path. The frontend adds only an `aria-label` to the existing Astryx dialog, while deterministic diagnostic tests and a dated acceptance ledger provide fresh release evidence.

**Tech Stack:** Python 3.13, Pydantic v2, LangChain/LangGraph, FastAPI/pytest, React 19, TypeScript, Astryx 0.1.4, Vitest/Testing Library, Docker Compose, SQLite, Neo4j.

**Approved design:** `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md`

---

## File map

### Backend/provider boundary

- Modify `backend/app/schemas/jobs.py`: own the exact provider-visible `save_job` JSON schema beside the existing runtime models and bounds.
- Modify `backend/app/tools/jobs.py`: attach that provider schema to the existing tool without changing its name, implementation, injected state, or runtime `SaveJobInput` validation.
- Modify `backend/app/adapters/shopaikey_chat.py`: allow one optional forced tool choice for a bounded repair binding.
- Modify `backend/app/agent/graph.py`: build the passive-repair binding from the same base model/tool and use it for exactly one repair invocation.
- Modify `backend/tests/unit/test_shopaikey_chat.py`: inspect the real OpenAI-format provider schema and forced-tool binding.
- Modify `backend/tests/unit/test_agent_graph.py`: cover strict passive repair/refusal/topology behavior.
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

from app.tools.jobs import save_job_openai_tool_schema


def test_save_job_provider_schema_has_exact_source_union() -> None:
    spec = convert_to_openai_tool(save_job_openai_tool_schema())
    params = spec["function"]["parameters"]

    assert params["type"] == "object"
    assert params["additionalProperties"] is False
    assert len(params["oneOf"]) == 3
    assert {tuple(branch["required"]) for branch in params["oneOf"]} == {
        ("url",),
        ("text",),
        ("source",),
    }
    assert params["properties"]["source"] == {
        "type": "string",
        "const": "current_message",
    }
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
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string", "minLength": 1},
            "text": {"type": "string", "minLength": 1},
            "source": {"type": "string", "const": SAVE_JOB_SOURCE_CURRENT_MESSAGE},
            "preview": preview,
        },
        "oneOf": [
            {
                "required": ["url"],
                "not": {"anyOf": [
                    {"required": ["text"]},
                    {"required": ["source"]},
                    {"required": ["preview"]},
                ]},
            },
            {
                "required": ["text"],
                "not": {"anyOf": [
                    {"required": ["url"]},
                    {"required": ["source"]},
                    {"required": ["preview"]},
                ]},
            },
            {
                "required": ["source"],
                "not": {"anyOf": [
                    {"required": ["url"]},
                    {"required": ["text"]},
                ]},
            },
        ],
    }
```

In `backend/app/tools/jobs.py`, wrap those parameters in one OpenAI-format
definition and reuse a single description constant:

```python
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

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/integration/test_job_tools.py -q
```

Expected: PASS; provider schema is strict, injected fields remain server-owned,
and runtime validation still rejects malformed calls.

- [ ] **Step 5: Commit the provider-boundary contract**

```powershell
git add backend/app/schemas/jobs.py backend/app/tools/jobs.py backend/app/agent/graph.py backend/tests/unit/test_shopaikey_chat.py backend/tests/unit/test_job_save_confirmation.py backend/tests/integration/test_job_tools.py
git commit -m "fix: constrain provider save_job source modes"
```

## Task 2: Make the one passive repair use the strict source-only tool

**Files:**

- Modify: `backend/app/adapters/shopaikey_chat.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/tests/unit/test_shopaikey_chat.py`
- Modify: `backend/tests/unit/test_agent_graph.py`

- [ ] **Step 1: Add failing tests for the repair binding**

Add a capture model test proving a forced binding contains only `save_job` and
uses its exact registered name:

```python
def test_bind_chat_tools_accepts_one_forced_tool_choice() -> None:
    model = CaptureBindModel()
    tool = save_job_openai_tool_schema()

    bound = bind_chat_tools(model, [tool], tool_choice="save_job")

    assert bound is model.bound
    assert model.last_tools == [tool]
    assert model.last_kwargs == {"tool_choice": "save_job"}
```

Add graph cases for:

1. Plain text then valid `{source: "current_message"}` repair → one ToolNode pass.
2. Mixed `text+source` first response then valid repair → one ToolNode pass.
3. Mixed first and mixed repair → fixed refusal, zero ToolNode passes.
4. Opt-out, sole URL, named `save_job`, greeting, and six-pass tests unchanged.

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

- [ ] **Step 5: Run focused graph/provider tests**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py -q
```

Expected: PASS; each malformed passive decision gets at most one repair, invalid
calls never reach ToolNode, and tool topology/count/loop assertions remain exact.

- [ ] **Step 6: Commit the bounded repair**

```powershell
git add backend/app/adapters/shopaikey_chat.py backend/app/agent/graph.py backend/tests/unit/test_shopaikey_chat.py backend/tests/unit/test_agent_graph.py
git commit -m "fix: bind passive JD repair to save_job"
```

## Task 3: Prove confirmation, branch call counts, and durable replay

**Files:**

- Modify: `backend/tests/integration/test_job_tools.py`
- Modify: `backend/tests/integration/test_chat_api.py`

- [ ] **Step 1: Add a public-path failing confirmation test**

Use a clear five-line, 300+ character JD and a fake model whose first decision is
mixed-source and whose repair is source-only. Assert the public turn ends with:

```python
assert event_names[-1] == "approval_required"
approval = events[-1]["data"]["payload"]
assert approval["kind"] == "job_save_confirmation"
assert approval["allowed_actions"] == ["save_job", "cancel_save_job"]
assert approval["card"]["source"] == "current_message"
assert "text" not in str(approval)
assert "message_id" not in str(approval)
```

The current product should fail this test when it follows the permissive provider
shape/refusal path.

- [ ] **Step 2: Add explicit zero-side-effect spies before confirmation**

Instrument the existing fake seams and assert all counters remain zero:

```python
assert counters == {
    "ingest_raw_text": 0,
    "jd_extraction": 0,
    "embedding": 0,
    "evaluation": 0,
    "neo4j_sync": 0,
}
assert job_count == 0
assert evaluation_count == 0
assert tool_row.status == "running"
```

Do not infer these counts only from a missing SavedJobCard.

- [ ] **Step 3: Exercise both resume branches and replay**

Extend the same fixture:

- `cancel_save_job`: counters stay zero; terminal ToolResult is
  `committed=false`, `outcome=cancelled`; no Job row.
- `save_job`: exact durable message is loaded once; ingest count is one;
  evaluation count is zero; the first run creates and the repeated content run
  returns the same Job.
- repeated terminal resume: no additional provider, SQLite, or graph call.
- direct URL/text paths: no passive confirmation and existing outcomes remain
  `created|returned|retried`.

- [ ] **Step 4: Run the focused integration gate**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py -q
```

Expected: PASS with one durable running execution before action, exact save/cancel
outcomes, zero automatic evaluation, and no duplicate side effects.

- [ ] **Step 5: Commit the public-path regression coverage**

```powershell
git add backend/tests/integration/test_job_tools.py backend/tests/integration/test_chat_api.py
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

- [ ] **Step 5: Commit the accessibility repair**

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
  `infrastructure/scripts/verify_pdf_extraction.py`

- [ ] **Step 1: Create deterministic ShopAIKey failure tests**

Add `infrastructure/scripts` to `sys.path`, import the focused owners, and
parameterize stable codes:

```python
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (httpx.ReadTimeout("slow"), "TIMEOUT"),
        (_status_error(429), "RATE_LIMIT"),
        (ValueError("not-json"), "MALFORMED_RESPONSE"),
    ],
)
def test_diagnostic_normalizes_transport_failures(error, expected_code):
    mapped = classify_http_error(error, "basic_chat", "test-secret")
    assert mapped.code == expected_code
```

Add focused fake payloads for missing chat/embedding model IDs, 1535-dimensional
vectors, reversed/duplicate indices, and malformed non-stream JSON. For each
`runner.main()` failure, capture output and assert:

```python
assert exit_code != 0
assert f"ERROR={expected_code}:" in captured.err
assert "SHOPAIKEY_COMPATIBILITY=FAIL" in captured.out
assert "test-secret" not in captured.out + captured.err
assert "Authorization" not in captured.out + captured.err
```

- [ ] **Step 2: Add pypdf negative aggregate tests**

Monkeypatch the existing evaluators; do not create new PDFs:

```python
def test_pdf_gate_fails_below_four_digital_passes(monkeypatch, capsys):
    monkeypatch.setattr(diag, "evaluate_digital", digital_evaluator(3))
    monkeypatch.setattr(diag, "evaluate_image_only", rejected_image_row)
    assert diag.main() == 1
    output = capsys.readouterr()
    assert "digital_below_threshold:3/5" in output.err
    assert "PYPDF_COMPATIBILITY=FAIL" in output.out


def test_pdf_gate_fails_when_image_only_is_accepted(monkeypatch, capsys):
    monkeypatch.setattr(diag, "evaluate_digital", digital_evaluator(5))
    monkeypatch.setattr(diag, "evaluate_image_only", accepted_image_row)
    assert diag.main() == 1
    output = capsys.readouterr()
    assert "image_only_not_rejected:UNEXPECTED_TEXT" in output.err
    assert "PYPDF_COMPATIBILITY=FAIL" in output.out
```

Also assert no OCR package/function/import is introduced.

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

- [ ] **Step 5: Commit diagnostic coverage**

```powershell
git add backend/tests/unit/test_phase0_diagnostics.py infrastructure/scripts/shopaikey_diag infrastructure/scripts/verify_pdf_extraction.py
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
P13-PJD-01, P13-PJD-02, P13-A11Y-01, P13-DIAG-01,
P13-CV-01, P13-EVIDENCE-01
```

Each row names automated/browser method, expected behavior, and the Plan 13 ledger
as execution evidence. Do not mark the matrix itself PASS.

- [ ] **Step 2: Create the dated ledger with explicit status columns**

Start the ledger with:

```markdown
| ID | Requirement/source | Procedure or command | Status | Date (UTC) | HEAD / Compose project | Failure/log evidence | Resolution/notes |
|---|---|---|---|---|---|---|---|
```

Add one row for every ID above. Before execution, use `NOT RUN`; after execution,
replace it only with `PASS`, `FAIL`, `BLOCKED`, or `SKIPPED (reason)`. Record actual
run IDs and sanitized counters; never paste raw JD/CV/provider content.

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

- [ ] **Step 4: Validate documentation links and commit**

```powershell
rg -n "P12-|P13-|current_message|job_save_confirmation|Nguồn" docs/acceptance/full_functional_test_matrix.md docs/acceptance/plan13_acceptance_ledger.md docs/acceptance/cv_manager_checklist.md
git diff --check
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

- [ ] **Step 4: Start the named disposable stack**

```powershell
docker compose -p jobagent-plan13-smoke --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected: exactly frontend/backend/neo4j are healthy and health is `available`.

- [ ] **Step 5: Execute the browser flow as a user**

At desktop width in the in-app browser, perform and record:

1. Create the two-CV disposable state and complete the archived activation/delete
   sequence from Task 6.
2. Ask one active-CV fact question, click **Nguồn**, and verify the browser role is
   `dialog` with name **Nguồn từ CV**; close by button and Escape; verify focus
   returns and **Mở CV gốc** opens the retained attachment without an evidence
   fetch.
3. Paste three fresh obvious JDs: a short structured English fixture, a structured
   Vietnamese fixture, and the synthetic equivalent of the reported long MISA
   fixture. Each must show exactly one confirmation card.
4. Before action, record: one running `save_job` execution, zero Job/evaluation
   delta, zero Neo4j Job delta, and automated fake-spy counters all zero. Browser
   network must contain no evaluate request.
5. Cancel English; save Vietnamese; refresh/restart before one decision; repeat
   saved content to prove exact-hash return and one Job identity.
6. Send a sole URL, explicit direct text save, opt-out JD, and ambiguous prose;
   verify only the intended paths execute.
7. Capture console, network, visible failure copy, backend sanitized logs, actual
   run IDs, and before/after counts in the ledger.

Any failed row remains `FAIL` with the observed log and root-cause hypothesis. Do
not rerun silently and overwrite the first failure.

- [ ] **Step 6: Tear down only the disposable project**

```powershell
docker compose -p jobagent-plan13-smoke --env-file .env -f infrastructure/docker-compose.yml down --volumes --remove-orphans
```

Expected: only `jobagent-plan13-smoke` containers/volumes are removed; normal user
volumes are untouched.

- [ ] **Step 7: Update evidence rows and commit**

Replace `NOT RUN` with the actual result/date/HEAD/project/run IDs and concise
sanitized logs. Then:

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
Provider union -> Tasks 1, 2; P13-PJD-01
Repair/refusal -> Tasks 2, 3; P13-PJD-02
Zero side effects -> Task 3; P12-JD-02/04/05; P13-EVIDENCE-01
Dialog name -> Task 4; P13-A11Y-01
Plan 1 negatives -> Task 5; P13-DIAG-01
Archived-CV browser evidence -> Tasks 6, 7; P13-CV-01
Warnings/out-of-scope -> Task 7 ledger notes
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

Expected: all gates pass from the final working tree. The pre-existing unrelated
deletion of
`docs/superpowers/specs/2026-07-19-frontend-functional-e2e-audit-design.md`
remains untouched and is not staged by this plan.

- [ ] **Step 4: Commit only a necessary README/evidence correction**

If implementation changed an existing documented command or current-status claim,
update that exact paragraph and commit:

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
- Pre-action/cancel counters prove zero ingestion, extraction, embedding,
  evaluation, and Neo4j mutation; save/replay/dedupe counts are exact.
- The source dialog has accessible role/name **Nguồn từ CV** and preserves exact
  evidence, no-fetch, original-PDF, close/Escape/focus behavior.
- Plan 1 negative diagnostics and PDF gates have deterministic tests.
- Archived-CV activation/reprocess/delete and P12/Plan13 browser evidence are
  recorded with date, HEAD, Compose project, run IDs, failures, and resolution.
- Focused/full/static/build/Compose/browser/plan-validator/scope gates pass.
- No `task_13.md`, migration, endpoint, dependency, extra Agent/tool/node,
  automatic evaluation, security/mobile work, or non-blocking-warning cleanup is
  introduced by this implementation plan.
