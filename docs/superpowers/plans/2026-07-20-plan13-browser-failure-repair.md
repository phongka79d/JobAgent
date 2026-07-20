# Plan 13 Browser Failure Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair BROWSER-F01 through BROWSER-F09, rebuild the normal Docker stack without deleting volumes, and prove the repaired behavior through automated gates and the visible frontend.

**Architecture:** Keep strict runtime validators and the existing one-Agent/one-decision/one-ToolNode graph. Add deterministic tool calls only at already unambiguous turn boundaries, preserve request-scoped attachment provenance through the graph, and align CV Manager actions with backend state eligibility.

**Tech Stack:** Python 3.12, FastAPI, LangGraph/LangChain, SQLAlchemy/SQLite, React 19, TypeScript, Vitest/Testing Library, Astryx, Docker Compose, in-app browser.

---

## File map

- Modify `backend/app/agent/graph.py`: canonical `save_job` dispatch and the one approved active-CV evidence auto-call.
- Modify `backend/tests/unit/test_agent_graph.py`: RED/GREEN graph regressions and topology assertions.
- Modify `backend/app/agent/context.py`: replace merged durable/request attachment IDs with request-only normalization.
- Modify `backend/app/services/chat_turns.py`: pass request-scoped IDs to graph state while retaining durable IDs in working memory.
- Modify `backend/app/services/attachment_resolve.py`: make one current-turn attachment authoritative and fail closed for a mismatched multi-ID request.
- Create `backend/tests/unit/test_attachment_resolve.py`: focused database-backed resolver regressions.
- Modify `backend/app/tools/profile.py`: use the effective current-turn ID in tool execution and sanitized durable argument metadata.
- Modify `backend/tests/unit/test_profile_extraction.py`: active-A/staged-B tool-boundary regression.
- Modify `frontend/src/features/observability/CvManagerPanel.tsx`: state-valid reprocess actions.
- Modify `frontend/src/test/cv-manager.test.tsx`: four-state action matrix regressions.
- Append only to `docs/acceptance/plan13_acceptance_ledger.md` and `docs/acceptance/cv_manager_checklist.md` after fresh browser evidence exists; preserve every historical failure row.

## Task 1: Canonical `save_job` dispatch

**Files:**

- Modify: `backend/tests/unit/test_agent_graph.py`
- Modify: `backend/app/agent/graph.py`

- [ ] **Step 1: Replace provider-dependent expectations with failing canonical-dispatch tests**

Add the exact acceptance command once near the graph-test helpers:

```python
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
```

Replace the passive provider-repair success assertion and sole-URL legacy
assertion with these tests. Keep the existing opt-out, ambiguous-prose,
malformed named-call, sanitized-log, schema, topology, and loop-limit tests.

```python
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
    assert model.invoke_count == 1  # narration after the direct tool result
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
    assert model.invoke_count == 2  # initial named path + one bounded repair
    assert out["tool_iteration_count"] == 0
    assert out[MESSAGES_KEY][-1].content == NAMED_SAVE_JOB_NO_ACTION_TEXT
```

The sole-URL graph invokes the model once only after the direct tool result
because direct URL narration remains model-owned. Passive and approved explicit
text use existing deterministic ToolResult projection and therefore invoke it
zero times.

- [ ] **Step 2: Run the four tests and verify RED for the observed reasons**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q `
  tests/unit/test_agent_graph.py::test_obvious_jd_dispatches_canonical_current_message_without_provider `
  tests/unit/test_agent_graph.py::test_sole_url_dispatches_exact_url_without_provider `
  tests/unit/test_agent_graph.py::test_approved_explicit_text_dispatches_exact_text `
  tests/unit/test_agent_graph.py::test_near_miss_explicit_text_remains_model_driven
```

Expected RED: passive invokes the fake provider/refuses, sole URL has no tool
call, and explicit text takes the provider-generated mixed/named path. The
near-miss characterization may already pass and must remain green.

- [ ] **Step 3: Add the narrow parser and canonical call helper**

In `backend/app/agent/graph.py`, add constants beside the existing exact-name
regex and the following pure helpers beside `_request_names_save_job`:

```python
_EXPLICIT_SAVE_JOB_TEXT_COMMAND = re.compile(
    r'^Please call save_job exactly once with text="([^"\r\n]+)" '
    r'Do not use source=current_message and do not call match_jobs\.$'
)


def _canonical_tool_call(name: str, args: dict[str, Any], prefix: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": f"{prefix}-{uuid4()}",
                "type": "tool_call",
            }
        ],
    )


def _approved_explicit_save_job_text(user_text: str) -> str | None:
    # ponytail: only the Plan 13 acceptance command is deterministic. If more
    # command forms are approved, replace this regex with a typed command grammar.
    matched = _EXPLICIT_SAVE_JOB_TEXT_COMMAND.fullmatch(user_text.strip())
    if matched is None:
        return None
    text = matched.group(1)
    return text if text.strip() else None


def _canonical_save_job_dispatch(
    user_text: str,
    *,
    save_job_available: bool,
    clear_opt_out: bool,
    named_save: bool,
    save_job_already: bool,
) -> AIMessage | None:
    if (
        not save_job_available
        or clear_opt_out
        or save_job_already
        or not user_text.strip()
    ):
        return None
    if message_is_sole_http_url(user_text):
        return _canonical_tool_call(
            SAVE_JOB_NAME, {"url": user_text.strip()}, "canonical-save-url"
        )
    direct_text = _approved_explicit_save_job_text(user_text)
    if direct_text is not None:
        return _canonical_tool_call(
            SAVE_JOB_NAME, {"text": direct_text}, "canonical-save-text"
        )
    if not named_save and message_is_obvious_jd(user_text):
        return _canonical_tool_call(
            SAVE_JOB_NAME,
            {"source": SAVE_JOB_SOURCE_CURRENT_MESSAGE},
            "canonical-save-current-message",
        )
    return None
```

In `decision_node`, after existing durable `save_job` ToolResult projection and
before `_build_model_messages`/`chat.invoke`, return the canonical call and apply
the existing loop-limit guard:

```python
        canonical_save = _canonical_save_job_dispatch(
            user_text,
            save_job_available=save_job_available,
            clear_opt_out=clear_opt_out,
            named_save=named_save,
            save_job_already=save_job_already,
        )
        if canonical_save is not None:
            updates: dict[str, Any] = {MESSAGES_KEY: [canonical_save]}
            if int(state.get("tool_iteration_count") or 0) >= limit:
                updates["error"] = ERROR_TOOL_LOOP_LIMIT_EXCEEDED
            return updates
```

Leave `SaveJobInput`, `_is_sole_current_message_save_job_call`, ToolNode, and
the old bounded model-refusal path intact as defense for non-canonical requests.

- [ ] **Step 4: Run focused graph tests and make them GREEN**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q tests/unit/test_agent_graph.py
```

Expected GREEN: all graph tests pass after updating only provider-dependent
expectations that are intentionally superseded by canonical dispatch.

- [ ] **Step 5: Commit the isolated backend graph change**

```powershell
git add -- backend/app/agent/graph.py backend/tests/unit/test_agent_graph.py
git commit -m "fix: canonicalize unambiguous job save turns"
```

## Task 2: Active-CV evidence auto-call

**Files:**

- Modify: `backend/tests/unit/test_agent_graph.py`
- Modify: `backend/app/agent/graph.py`

- [ ] **Step 1: Add a RED regression for the approved question**

Add a test-only tool near the other test tools:

```python
@tool("read_active_cv")
def read_active_cv_tool(mode: str, section_id: str) -> dict[str, Any]:
    return {
        "ok": True,
        "code": None,
        "summary": "Read active CV experience section",
        "data": {
            "records": [
                {
                    "kind": "entry",
                    "section_id": section_id,
                    "title": "Senior Software Engineer",
                    "company": "Northwind Labs",
                }
            ]
        },
    }
```

Then add:

```python
def test_recent_role_question_reads_experience_before_narration() -> None:
    section_id = "cv-document-v1:s0:experience"
    outline = {
        "attachment_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "reprocess_required": False,
        "sections": [
            {
                "id": section_id,
                "ordinal": 0,
                "heading": "Experience",
                "kind": "experience",
                "entry_count": 1,
                "source_chunk_range": [0, 0],
            }
        ],
    }
    model = FakeChatModel(
        responses=[_ai_text("Senior Software Engineer at Northwind Labs")]
    )
    out = _bundle(model, [read_active_cv_tool]).compiled.invoke(
        initial_graph_state(
            run_id=RUN_ID,
            user_text="What is the most recent role and company in my CV?",
            active_cv_context=outline,
        )
    )
    calls = [
        call
        for message in out[MESSAGES_KEY]
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
    ]
    assert calls == [
        {
            "name": "read_active_cv",
            "args": {"mode": "section", "section_id": section_id},
            "id": calls[0]["id"],
            "type": "tool_call",
        }
    ]
    assert out["tool_iteration_count"] == 1
    assert model.invoke_count == 1
    assert out[MESSAGES_KEY][-1].content == (
        "Senior Software Engineer at Northwind Labs"
    )
```

Add a companion characterization proving a different CV question remains
model-driven and does not auto-call the tool.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q `
  tests/unit/test_agent_graph.py::test_recent_role_question_reads_experience_before_narration
```

Expected RED: the fake model answers directly and no `read_active_cv` call is
present.

- [ ] **Step 3: Implement the one-question evidence helper**

Import `READ_ACTIVE_CV_NAME` from `app.tools.active_cv`, then add:

```python
_RECENT_ROLE_AND_COMPANY_QUESTION = (
    "What is the most recent role and company in my CV?"
)


def _turn_already_called_tool(messages: Sequence[Any], tool_name: str) -> bool:
    for item in messages:
        if isinstance(item, AIMessage):
            if any(_tool_call_name(call) == tool_name for call in item.tool_calls or []):
                return True
        if isinstance(item, ToolMessage) and getattr(item, "name", None) == tool_name:
            return True
    return False


def _experience_section_id(state: AgentGraphState) -> str | None:
    context = state.get("active_cv_context")
    sections = context.get("sections") if isinstance(context, dict) else None
    if not isinstance(sections, list):
        return None
    for section in sections:
        if not isinstance(section, dict) or section.get("kind") != "experience":
            continue
        section_id = section.get("id")
        if isinstance(section_id, str) and section_id.strip():
            return section_id.strip()
    return None


def _auto_read_recent_role(
    state: AgentGraphState,
    *,
    read_active_cv_available: bool,
) -> AIMessage | None:
    if not read_active_cv_available:
        return None
    if _initiating_user_text(state).strip() != _RECENT_ROLE_AND_COMPANY_QUESTION:
        return None
    messages = list(state.get(MESSAGES_KEY) or [])
    if _turn_already_called_tool(messages, READ_ACTIVE_CV_NAME):
        return None
    section_id = _experience_section_id(state)
    if section_id is None:
        return None
    return _canonical_tool_call(
        READ_ACTIVE_CV_NAME,
        {"mode": "section", "section_id": section_id},
        "canonical-read-active-cv",
    )
```

Compute `read_active_cv_available` once from `tool_names`. In `decision_node`,
after auto-commit and before any model invocation, return the evidence call with
the same loop-limit guard. On the next pass `_turn_already_called_tool` prevents
a loop and the model narrates from the durable ToolMessage.

- [ ] **Step 4: Verify graph behavior and invariants GREEN**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q tests/unit/test_agent_graph.py
```

Expected GREEN and the existing registry/topology tests still prove seven tools,
one decision node, one ToolNode, and limit six.

- [ ] **Step 5: Commit the active-CV evidence change**

```powershell
git add -- backend/app/agent/graph.py backend/tests/unit/test_agent_graph.py
git commit -m "fix: require evidence for approved active CV question"
```

## Task 3: Preserve upload-turn attachment ownership

**Files:**

- Create: `backend/tests/unit/test_attachment_resolve.py`
- Modify: `backend/tests/unit/test_profile_extraction.py`
- Modify: `backend/app/agent/context.py`
- Modify: `backend/app/services/chat_turns.py`
- Modify: `backend/app/services/attachment_resolve.py`
- Modify: `backend/app/tools/profile.py`

- [ ] **Step 1: Add RED resolver tests**

Create `backend/tests/unit/test_attachment_resolve.py` using the repository's
`migrated_sqlite`, `run_async`, and `session_factory` helpers. Seed active A and
staged B, then assert:

```python
def test_single_turn_attachment_overrides_model_supplied_active_id(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            active_id = new_uuid()
            staged_id = new_uuid()
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="active-a",
                    original_name="a.pdf",
                    size_bytes=10,
                    storage_path=f"{active_id}.pdf",
                    page_count=1,
                    attachment_id=active_id,
                )
                await att_repo.mark_active(session, active_id)
                await att_repo.create_staged(
                    session,
                    file_hash="staged-b",
                    original_name="b.pdf",
                    size_bytes=10,
                    storage_path=f"{staged_id}.pdf",
                    page_count=1,
                    attachment_id=staged_id,
                )
                await session.commit()
            async with factory() as session:
                resolved = await resolve_attachment_id_for_propose(
                    session,
                    active_id,
                    turn_attachment_ids=[staged_id],
                )
                assert resolved == staged_id
        finally:
            await engine.dispose()

    run_async(_body())
```

Add a second test with two turn IDs and an outside requested UUID, expecting
`None`, while a requested member resolves normally.

- [ ] **Step 2: Run resolver tests and verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q tests/unit/test_attachment_resolve.py
```

Expected RED: the current resolver returns active A because it prioritizes the
model-supplied processable UUID.

- [ ] **Step 3: Change resolver precedence at the source**

In `resolve_attachment_id_for_propose`, normalize current-turn UUIDs before the
requested UUID and implement this order:

```python
    turn_candidates: list[str] = []
    for item in turn_attachment_ids or ():
        if not isinstance(item, str):
            continue
        value = item.strip()
        if looks_like_attachment_uuid(value) and value not in turn_candidates:
            turn_candidates.append(value)

    raw = requested.strip() if isinstance(requested, str) else ""
    if turn_candidates:
        if raw in turn_candidates:
            return raw if await _is_processable(session, raw) else None
        if len(turn_candidates) == 1:
            only = turn_candidates[0]
            return only if await _is_processable(session, only) else None
        return None

    if raw and raw.lower() not in _PLACEHOLDER_IDS and looks_like_attachment_uuid(raw):
        if await _is_processable(session, raw):
            return raw
        return None
```

Keep current-draft/newest-staged/active fallback unchanged when no request-turn
ID exists.

- [ ] **Step 4: Make graph state request-scoped and retain durable working memory**

Replace `merge_turn_attachment_ids` in `backend/app/agent/context.py` with this
pure normalizer and update `__all__`:

```python
def normalize_turn_attachment_ids(
    turn_attachment_ids: Sequence[str] | None,
) -> list[str]:
    """Return unique non-empty request IDs without durable-state widening."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in turn_attachment_ids or ():
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
```

In `backend/app/services/chat_turns.py`, import the new helper and replace the DB
union with:

```python
        effective_attachment_ids = normalize_turn_attachment_ids(attachment_ids)
```

Do not remove `load_profile_working_memory_messages`: it remains the separate
durable staged/active context and prevents loss of later-turn recovery.

- [ ] **Step 5: Add and run the active-A/staged-B tool regression RED**

Extend the `_ainvoke_with_identity` helper in
`backend/tests/unit/test_profile_extraction.py` with an optional
`attachment_ids` argument and inject it into state:

```python
                    "state": {
                        "run_id": run_id,
                        "attachment_ids": list(attachment_ids or ()),
                    },
```

Seed active A with an approved profile plus staged B with a real fixture PDF.
Invoke the tool with model argument A and state `attachment_ids=[B]`. Assert the
result kind/data points to B, a current draft is sourced from B, A remains
active before approval, and the durable tool execution summary records B rather
than A.

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q `
  tests/unit/test_profile_extraction.py -k "turn_attachment or tool_boundary" 
```

Expected RED before the tool metadata correction: resolution may produce B
after Step 3, but the durable argument summary still records model-supplied A.

- [ ] **Step 6: Use the effective turn ID throughout the profile tool**

In `build_propose_profile_from_cv_tool`, normalize `turn_ids` and compute:

```python
        normalized_turn_ids = [
            item.strip()
            for item in turn_ids
            if isinstance(item, str) and item.strip()
        ]
        effective_attachment_id = attachment_id
        if not do_reprocess and len(dict.fromkeys(normalized_turn_ids)) == 1:
            effective_attachment_id = normalized_turn_ids[0]
```

Use `effective_attachment_id` for normal `resolve_attachment_id_for_propose`,
the normal error payload/summary, and `arguments_summary_for_propose_cv`. Keep
owned reprocess precedence and `AgentRun.source_attachment_id` behavior exactly
as it is.

- [ ] **Step 7: Run the focused attachment/profile suite GREEN**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q `
  tests/unit/test_attachment_resolve.py `
  tests/unit/test_profile_extraction.py `
  tests/integration/test_cv_manager_api.py `
  tests/integration/test_agent_runner.py
```

Expected GREEN: B owns the upload proposal; archived/active reprocess still owns
the attachment through `AgentRun.source_attachment_id`.

- [ ] **Step 8: Commit the attachment-provenance repair**

```powershell
git add -- `
  backend/app/agent/context.py `
  backend/app/services/chat_turns.py `
  backend/app/services/attachment_resolve.py `
  backend/app/tools/profile.py `
  backend/tests/unit/test_attachment_resolve.py `
  backend/tests/unit/test_profile_extraction.py
git commit -m "fix: preserve current turn CV attachment ownership"
```

## Task 4: CV Manager state/action matrix

**Files:**

- Modify: `frontend/src/test/cv-manager.test.tsx`
- Modify: `frontend/src/features/observability/CvManagerPanel.tsx`

- [ ] **Step 1: Inspect the Astryx pattern before UI code**

Run:

```powershell
Set-Location frontend
npx astryx build "CV Manager detail actions for active archived staged and failed lifecycle states"
```

Use the existing `Button`, `HStack`, and state-token layout; do not add wrappers,
dependencies, or custom styling.

- [ ] **Step 2: Add RED state-matrix tests**

Export `canReprocessCv` from the panel and extend the guard test:

```typescript
expect(canReprocessCv({...archivedItem(), state: 'active'})).toBe(true);
expect(canReprocessCv(archivedItem())).toBe(true);
expect(canReprocessCv({...archivedItem(), state: 'staged'})).toBe(false);
expect(canReprocessCv({...archivedItem(), state: 'failed'})).toBe(false);
```

Add a parameterized rendering regression:

```typescript
it.each(['staged', 'failed'] as const)(
  'does not expose reprocess for %s selection',
  (state) => {
    const item = {...archivedItem(), id: `${state}-attachment`, state};
    renderPanel({
      resource: {
        phase: 'ready',
        data: {items: [item], next_cursor: null},
        error: null,
        loaded: true,
      },
      selectedAttachmentId: item.id,
    });
    const actions = screen.getByTestId(`jobagent-obs-cv-actions-${item.id}`);
    expect(within(actions).queryByText('Make active')).toBeNull();
    expect(within(actions).queryByText('Re-extract')).toBeNull();
    expect(
      within(actions).getByTestId(`jobagent-obs-cv-delete-${item.id}`),
    ).toBeEnabled();
  },
);
```

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```powershell
Set-Location frontend
npm test -- --run src/test/cv-manager.test.tsx
```

Expected RED: staged and failed rows currently render **Make active**.

- [ ] **Step 4: Implement the smallest state gate**

Add:

```typescript
export function canReprocessCv(item: CvHistoryItem): boolean {
  return item.state === 'active' || item.state === 'archived';
}
```

Replace the binary active/non-active button branch with:

```tsx
{selectedItem.state === 'active' ? (
  <Button
    label="Re-extract"
    variant="secondary"
    size="sm"
    isDisabled={isSelectedPending || !selectedItem.file_available}
    isLoading={isReprocessPending}
    onClick={() => onReprocess(selectedItem)}
    data-testid={`jobagent-obs-cv-reextract-${selectedItem.id}`}
  />
) : selectedItem.state === 'archived' ? (
  <Button
    label="Make active"
    variant="secondary"
    size="sm"
    isDisabled={isSelectedPending || !selectedItem.file_available}
    isLoading={isReprocessPending}
    onClick={() => onReprocess(selectedItem)}
    data-testid={`jobagent-obs-cv-make-active-${selectedItem.id}`}
  />
) : null}
```

Do not broaden backend reprocess eligibility; staged uploads remain owned by the
normal approval flow.

- [ ] **Step 5: Run focused frontend tests GREEN**

Run:

```powershell
Set-Location frontend
npm test -- --run src/test/cv-manager.test.tsx src/test/cv-manager-api.test.ts
```

Expected GREEN with active and archived behavior unchanged.

- [ ] **Step 6: Commit the frontend state gate**

```powershell
git add -- `
  frontend/src/features/observability/CvManagerPanel.tsx `
  frontend/src/test/cv-manager.test.tsx
git commit -m "fix: gate CV Manager actions by lifecycle state"
```

## Task 5: Automated quality gates

**Files:**

- Verify all modified source/test files

- [ ] **Step 1: Run focused backend acceptance tests**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest -q `
  tests/unit/test_agent_graph.py `
  tests/unit/test_attachment_resolve.py `
  tests/unit/test_profile_extraction.py `
  tests/integration/test_cv_manager_api.py `
  tests/integration/test_agent_runner.py `
  tests/integration/test_chat_api.py `
  tests/integration/test_job_tools.py
```

Expected: zero failures.

- [ ] **Step 2: Run backend static and full gates**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q
```

Expected: all three commands exit 0. Record any warning separately from a test
failure.

- [ ] **Step 3: Run focused and full frontend gates**

```powershell
Set-Location frontend
npm test -- --run `
  src/test/cv-manager.test.tsx `
  src/test/cv-manager-api.test.ts `
  src/test/active-cv-source.test.tsx `
  src/test/job-save-confirmation.test.tsx `
  src/test/chat-page.test.tsx
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: all commands exit 0. Preserve the existing classification of known
non-blocking jsdom/Vite warnings unless a new functional failure appears.

- [ ] **Step 4: Verify scope and graph invariants**

```powershell
git diff --check
git status --short
rg -n "StateGraph\(|ToolNode\(|TOOL_LOOP_LIMIT" backend/app/agent/graph.py
& '.venv\Scripts\python.exe' -c "from app.tools.registry import production_registry; print(production_registry().tool_names())"
```

Expected: one `StateGraph`, one `ToolNode` owner, loop limit retained, and the
registry prints exactly seven tool names. No migration, dependency manifest, or
public route is changed.

## Task 6: Docker rebuild and visible-browser 05B revalidation

**Files:**

- Append: `docs/acceptance/plan13_acceptance_ledger.md`
- Append: `docs/acceptance/cv_manager_checklist.md`

- [ ] **Step 1: Capture normal-stack and volume identity before rebuild**

Run from the repository root:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p infrastructure config --services
docker compose --env-file .env -f infrastructure/docker-compose.yml -p infrastructure ps -a
docker volume ls --filter label=com.docker.compose.project=infrastructure
```

Expected: exactly backend/frontend/neo4j are known; record container health and
normal volume names. Stop if the project is partial, unhealthy, or fixed ports
belong to an unrelated process.

- [ ] **Step 2: Rebuild in place without deleting volumes**

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml `
  -p infrastructure up --build -d --wait --wait-timeout 180
docker compose --env-file .env -f infrastructure/docker-compose.yml `
  -p infrastructure ps
docker volume ls --filter label=com.docker.compose.project=infrastructure
```

Expected: all three services healthy and the before/after normal volume-name set
is identical. Never run `down --volumes`, `docker volume prune`, or delete a
normal-project volume.

- [ ] **Step 3: Verify API and capture sanitized logs**

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/api/health'
docker compose --env-file .env -f infrastructure/docker-compose.yml `
  -p infrastructure logs --no-color --tail 300 backend
```

Expected: overall, SQLite, filesystem, and Neo4j are available; logs have no
Traceback/HTTP 5xx/secret/raw JD/CV content.

- [ ] **Step 4: Execute the visible frontend CV sequence**

At desktop width through the in-app browser:

1. Upload `backend/tests/fixtures/cv/digital_cv_01.pdf`, approve A, and record
   run/tool IDs and active badge.
2. Upload `backend/tests/fixtures/cv/digital_cv_02.pdf`; prove the proposal and
   approval card own B, then approve B and prove A becomes archived.
3. In CV Manager prove staged/failed rows expose no reprocess action; active B
   shows **Re-extract**, archived A shows **Make active**.
4. Make A active through the existing reprocess/approval path and prove the run
   and proposal tool retain A as `source_attachment_id`.
5. Ask exactly `What is the most recent role and company in my CV?`; require one
   successful `read_active_cv`, answer `Senior Software Engineer at Northwind
   Labs`, one `Nguồn` citation, named source dialog, retained PDF open, zero
   evidence fetch, close button, Escape, and focus return.

For any failure, record the visible step, request/status, run/tool execution ID,
sanitized log line, durable state, and why the observed owner violated the
expected contract.

- [ ] **Step 5: Execute the visible frontend JD sequence**

Use the synthetic fixtures and exact order in `docs/plans/Plan_13.md`:

1. English passive JD → one card → cancel.
2. Vietnamese passive JD → refresh while pending → same run/execution/card
   rehydrates → save once.
3. Exact Vietnamese repeat → confirm → same Job returned with no evaluation.
4. Long MISA-like passive JD → one bounded card → cancel.
5. Sole URL `https://example.com/jobs/plan13-synthetic-engineer` → one URL source,
   no passive card; safe fetch failure is allowed but multiple-source
   `INVALID_JOB_INPUT` is not.
6. Exact `EXPLICIT_DIRECT_TEXT_REQUEST` from Task 1 → one text source, no passive
   card, no evaluation.
7. Approved opt-out and long ambiguous prose → no tool/card/mutation.

Require zero unexpected browser-console errors, no duplicate resume request,
no pending run at the end, and no raw fixture bodies in backend logs.

- [ ] **Step 6: Append fresh evidence without rewriting history**

Append a new dated attempt row for each R1-R6 result to
`docs/acceptance/plan13_acceptance_ledger.md`. Include UTC date, current HEAD,
Compose project `infrastructure`, actual run/tool IDs, PASS/FAIL, sanitized log
classification, and resolution. Append the CV action/source-dialog results to
`docs/acceptance/cv_manager_checklist.md`. Never alter the prior F01-F09 or
baseline failed-run rows.

- [ ] **Step 7: Run final evidence and scope checks**

```powershell
git diff --check
python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json
rg -n "BROWSER-F0[1-9]|R[1-6]|source_attachment_id|read_active_cv|current_message|INVALID_JOB_INPUT" `
  docs/acceptance/plan13_acceptance_ledger.md `
  docs/acceptance/cv_manager_checklist.md
docker compose --env-file .env -f infrastructure/docker-compose.yml `
  -p infrastructure ps
```

Expected: diff check clean, plan set valid, historical and fresh evidence both
present, and all normal services remain healthy with their original volumes.

## Completion gate

Do not claim completion until fresh command output proves all focused/full/static
gates, Docker build/health, and every browser acceptance item. If a browser item
still fails, report it as an actual remaining failure with its evidence and root
cause; do not infer PASS from unit tests.
