# Plan 3 — Master Phase 2: Chat Transport, Agent Runtime, and Persistence

> **Numbering:** `Plan_3.md` implements **Master Plan Phase 2**. It consumes the source-of-truth schema and runtime foundation from Plan 2 without changing them.

## Objective

Deliver one persistent conversation over a complete React–FastAPI–LangGraph–SSE path. The phase owns conversation/history persistence, per-turn run lifecycle, durable tool execution/replay, typed SSE, the single controlled Agent loop, ShopAIKey chat integration, a base Astryx chat interface, and generic interrupt/resume mechanics proved by a test-only synthetic tool.

The result must answer greetings/general questions naturally without tool calls, stream validated events, survive an interrupt across a request boundary, replay durable terminal tool results idempotently, and remove terminal checkpoints while retaining application history.

## Source of Truth

- `docs/plans/Master_plan.md` Sections 4.1 and 6.2–6.5: ownership, chat/run/tool tables, transactions, replay identity, history joins, and checkpoint ownership.
- Sections 7.5 and 12.1–12.6: `ToolResult`, one controlled graph, per-turn runs, Agent state, bounded memory, conversation policy, and six-iteration limit.
- Section 13 introduction and authorization principles: compact candidate context, durable `(run_id, tool_call_id)` identity, and no separate idempotency keys. Domain tool implementations remain later.
- Section 14 and 14.1–14.2: public chat/history/resume endpoints, pagination, interrupted-run blocking, and exact SSE status vocabulary.
- Sections 15.1, 15.3–15.4: base Astryx chat shell and concise tool activity.
- Sections 16.1–16.2: verified `ChatOpenAI` adapter behavior through ShopAIKey.
- Sections 20 and 24: controlled failure, local test cases, fake provider use, and no real provider calls in normal tests.
- Section 25, “Phase 2 — Chat transport, Agent runtime, and persistence”: tasks and exit gate.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| Legacy Plan 3 scope | Master Phase 2: Chat Transport, Agent Runtime, and Persistence | Preserve the historical phase scope and outputs below. | Existing Verification section and accepted evidence. |

## Prerequisites

- [ ] Plan 1 compatibility report is PASS and identifies the exact ShopAIKey schema/tool/streaming mode and pinned Astryx APIs.
- [ ] Plan 2 Docker Compose starts frontend, backend, and Neo4j; health reports the foundation state.
- [ ] Alembic owns `conversation`, `chat_messages`, `agent_runs`, and `tool_executions` with the exact Master status values and constraints.
- [ ] `conversation(id='main')` is seeded; async sessions have required PRAGMAs.
- [ ] Shared settings, UUID, UTC, and Neo4j/session lifecycle modules exist and must be reused.

## Scope

- Define Pydantic contracts for messages, history pages/cursors, run metadata, `ToolResult`, and every SSE event.
- Implement repositories for one conversation, deterministic cursor history, Agent runs, and tool executions.
- Join durable tool activity to the initiating user turn during history hydration; never persist `role='tool'` messages.
- Enforce idempotent tool replay by `(run_id, tool_call_id)` and exact `pending → running → completed|failed` transitions.
- Implement `GET /api/chat/history`, `POST /api/chat/turns`, and `POST /api/chat/runs/{run_id}/resume`.
- Create user message and run atomically; persist assistant message and terminal run atomically.
- Define one validated client-facing SSE stream owned by FastAPI.
- Implement the one-node-decision/one-`ToolNode` LangGraph loop, bounded context, six-iteration limit, and controlled error boundary.
- Use one per-turn `AsyncSqliteSaver` lifecycle and delete terminal run checkpoints only.
- Implement the verified ShopAIKey `ChatOpenAI` adapter and conversation-first prompt.
- Prove interrupt/resume and terminal no-op resume with a side-effect-free, test-only synthetic tool injected into the graph during integration tests.
- Implement base Astryx conversation layout, message list, composer, streaming reducer, tool activity, error/disconnected states, and history pagination.
- Ensure general conversation creates no tool execution or JobAgent domain mutation.

## Out of Scope

- PDF upload, attachment state transitions, profile/draft schemas, profile approval UI, or Candidate graph synchronization.
- The six production JobAgent tool implementations; the production Phase 2 registry is empty and the synthetic tool exists only in tests.
- JD URL/text ingestion, extraction, quality, embeddings, graph rebuild, saved-job UI, matching, or match cards.
- A second Agent, agent handoffs, classifier model, full-history/64K injection, general-purpose tools, or general long-term memory extraction.
- Persisted provider `ToolMessage` rows, duplicated tool results in chat messages, a second idempotency key, or permanent checkpoints.
- WebSockets, provider-owned client streaming, public CRUD endpoints, background workers, or cloud tracing dependencies.

## Target Directory Structure

```text
JobAgent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── chat.py
│   │   │   └── dependencies.py
│   │   ├── agent/
│   │   │   ├── checkpoint.py
│   │   │   ├── context.py
│   │   │   ├── graph.py
│   │   │   ├── prompt.py
│   │   │   ├── runner.py
│   │   │   └── state.py
│   │   ├── adapters/
│   │   │   └── shopaikey_chat.py
│   │   ├── repositories/
│   │   │   ├── agent_runs.py
│   │   │   ├── chat_messages.py
│   │   │   └── tool_executions.py
│   │   ├── schemas/
│   │   │   ├── chat.py
│   │   │   ├── common.py
│   │   │   ├── sse.py
│   │   │   └── tools.py
│   │   ├── services/
│   │   │   ├── chat_history.py
│   │   │   ├── chat_turns.py
│   │   │   └── tool_execution.py
│   │   └── tools/
│   │       └── registry.py
│   └── tests/
│       ├── fakes/
│       │   ├── fake_chat_model.py
│       │   └── synthetic_tool.py
│       ├── integration/
│       │   ├── test_chat_api.py
│       │   ├── test_chat_history.py
│       │   ├── test_interrupt_resume.py
│       │   └── test_tool_replay.py
│       └── unit/
│           ├── test_agent_context.py
│           ├── test_sse_contract.py
│           └── test_tool_result.py
└── frontend/
    └── src/
        ├── features/chat/
        │   ├── ChatPage.tsx
        │   ├── components/
        │   │   ├── ChatMessages.tsx
        │   │   └── ChatToolActivity.tsx
        │   ├── history.ts
        │   ├── reducer.ts
        │   └── types.ts
        ├── lib/api/
        │   └── chat.ts
        ├── lib/sse/
        │   ├── parser.ts
        │   └── stream.ts
        └── test/
            ├── chat-page.test.tsx
            └── sse-reducer.test.ts
```

Keep transport, orchestration, persistence, and UI rendering separate. Do not put Agent execution in the API route or database writes in graph nodes.

## Technical Specifications

### 7.1 Durable result and status contracts

`ToolResult` is exactly:

```text
ok: bool
code: str | None
summary: str
data: dict[str, JSONValue] | None
```

- `ok=true` requires `code=null`, terminal tool status `completed`, and no `error_code`.
- `ok=false` requires a stable non-null `code`, terminal status `failed`, and equal `tool_executions.error_code`.
- `data` may contain compact IDs/counts/card payloads, never raw CV/JD bodies.
- Every terminal tool execution stores a validated result and duration.
- Re-entering `(run_id, tool_call_id)` returns that exact stored result without invoking the service or creating another row.

Status values must remain exact:

```text
run: running | interrupted | completed | failed
tool: pending | running | completed | failed
```

Do not introduce frontend aliases such as `complete` or `error`.

### 7.2 Repository and transaction rules

- `chat_messages.py` inserts/list messages only. History order is `(created_at, id)`.
- `agent_runs.py` creates a run for one unique user message, enforces allowed transitions, stores/clears `pending_approval_json`, and marks terminal completion/error.
- `tool_executions.py` owns get-or-create by `(run_id, tool_call_id)`, transitions, result storage, and replay reads.
- `chat_turns.py` creates the user message plus `agent_runs(state='running')` in one short transaction before graph execution.
- On terminal success, it creates the assistant message and sets run `completed`/`completed_at` in one short transaction.
- On unrecoverable execution failure, it sets run `failed`, `error_code`, and `completed_at`; any persisted user turn remains.
- No transaction remains open while calling ShopAIKey, executing the graph, or yielding SSE.

### 7.3 History cursor and hydration

`GET /api/chat/history?limit=50&before=<opaque_cursor>` uses `limit` in `1..100`.

- The opaque URL-safe cursor encodes only the oldest returned `(created_at, id)` pair and is validated before use.
- Query messages where `(created_at, id)` is lexicographically earlier than the cursor, ordered newest first, with `limit + 1`.
- Use the extra row to determine `next_cursor`, remove it, then reverse the page to chronological order.
- A malformed timestamp, UUID, shape, or encoding returns FastAPI `422`.
- Each user message item attaches runs/tool executions through `agent_runs.user_message_id`; tool activity is not emitted as a message role.
- Response shape is exactly `{items, next_cursor}` with `next_cursor=null` when no older page exists.

### 7.4 Agent context and state

`AgentState` contains only:

```text
conversation_id
run_id
messages_for_this_turn
recent_context
candidate_context
attachment_ids
pending_approval
tool_iteration_count
error
```

- `conversation_id` is always `main`; `run_id` is also the LangGraph `thread_id`.
- Recent context is a bounded window selected by a documented prompt budget, never an unbounded/full-history dump.
- Candidate context is empty in this phase and becomes a compact approved profile/preferences projection in Plan 4.
- Attachment IDs and large-document IDs are references; raw documents never enter graph state.
- Increment `tool_iteration_count` before each `ToolNode` pass and fail with a controlled stable code once the configured limit of six would be exceeded.

### 7.5 Graph and model adapter

- Build one `StateGraph` with one LLM decision node and one `ToolNode`; route tool calls back to the LLM and direct responses to final persistence.
- Production Phase 2 has no domain tools. Tests inject one synthetic side-effect-free tool through the registry interface; it must not be available in the shipped prompt/registry.
- Use `ChatOpenAI` with `SHOPAIKEY_BASE_URL`, masked API key, `LLM_MODEL=gpt-4o-mini`, and temperature `0`, using exactly the schema/tool mode proven in Plan 1.
- The prompt permits greetings, casual/general knowledge, and job-related conversation, but restricts tool use to registered JobAgent capabilities. It instructs the model never to claim success after a failed `ToolResult`.
- No separate intent classifier is permitted.

### 7.6 Checkpoint lifecycle and interrupt/resume

- Open one `AsyncSqliteSaver` lifecycle per turn/resume request against the configured SQLite file and close it after execution.
- LangGraph alone owns its package-created checkpoint tables; Alembic and application repositories never modify them.
- Interrupted execution stores `agent_runs.state='interrupted'` and a compact `pending_approval_json` projection, then ends the HTTP request with `approval_required` without marking the running tool terminal.
- Resume atomically returns the run to `running` and clears the projection before graph execution continues with the same `thread_id`.
- A completed or failed run deletes only its own checkpoint data after durable terminal state is committed.
- Resuming a terminal run is a no-op stream containing the persisted terminal run state; it does not execute the graph, replay text deltas, or repeat a tool side effect.
- While any run is interrupted, a new chat turn returns `APPROVAL_ACTION_REQUIRED` before inserting a message/run. Plan 4 reuses the same guard for CV upload.

### 7.7 SSE contract and ordering

Every event contains `event_id` (UUID), `run_id`, timezone-aware UTC `timestamp`, and validated event-specific payload. Event names are exactly:

```text
run_started
assistant_status
tool_status
approval_required
text_delta
run_completed
run_failed
```

Required payload invariants:

- `run_started`: `state='running'`, `resumed: bool`.
- `tool_status`: durable tool ID/name, exact status, optional duration, concise summary/error code; emitted in durable transition order.
- `approval_required`: `state='interrupted'`, approval kind, allowed actions, and compact card payload.
- `text_delta`: non-empty ordered text fragment.
- `run_completed`: `state='completed'`.
- `run_failed`: `state='failed'`, stable error code, safe summary.

FastAPI owns framing and validates payloads before yielding. A normal direct-answer order is `run_started`, optional `assistant_status`, zero or more `text_delta`, then `run_completed`. Tool paths insert ordered `tool_status` events. A failed tool can still be followed by `run_completed` when the assistant truthfully explains failure.

### 7.8 Public endpoint behavior

- `POST /api/chat/turns` accepts one non-empty user message plus zero or more already-staged `attachment_ids`; it returns SSE.
- The route persists input/run first, then delegates to the runner. It contains no Agent/business logic.
- `POST /api/chat/runs/{run_id}/resume` accepts exactly one action, validates it against the run’s persisted allowed actions, and returns SSE.
- `GET /api/chat/history` returns the hydrated chronological page contract above.
- CORS permits only `FRONTEND_ORIGIN` in the local configuration.

### 7.9 Frontend reducer and UI

- The reducer is the only owner of client run/message/tool streaming state.
- It deduplicates events by `event_id`, appends text deltas in order, and maps exact tool statuses without aliases.
- On reconnect/history hydration, durable tool activity replaces transient state for completed turns.
- The base UI uses the pinned Astryx `ChatLayout`, `ChatMessageList`, `ChatMessage`, `ChatComposer`, `ChatToolCalls`, and `ChatSystemMessage` public APIs recorded in Plan 1.
- Tool activity shows friendly label, exact status, duration, and short outcome only; no raw arguments, documents, or stack trace.
- “Load older” uses `next_cursor`; disconnected/failed stream states are visible and do not falsely mark a run complete.

## Implementation

- [ ] Define and unit-test `ToolResult`, chat/history, and all SSE Pydantic contracts before implementing routes.
- [ ] Implement focused message, run, and tool-execution repositories using the existing async session factory.
- [ ] Implement get-or-replay tool execution behavior and prove a repeated identity causes one stored result and one side effect.
- [ ] Implement deterministic cursor encoding/decoding, history query, chronological reversal, and tool-activity hydration.
- [ ] Implement bounded recent-context loading and the exact `AgentState` definition.
- [ ] Implement the injected tool registry, one-loop graph, six-iteration guard, and error boundary.
- [ ] Implement the verified ShopAIKey `ChatOpenAI` adapter and conversation-first system prompt.
- [ ] Implement per-request checkpointer lifecycle, interrupt persistence, resume, terminal no-op, and terminal checkpoint deletion.
- [ ] Implement chat turn/history/resume services and thin FastAPI routes with typed SSE.
- [ ] Add a fake chat model and test-only synthetic interrupting tool; keep both outside production registration.
- [ ] Implement the frontend SSE parser/reducer, API client, base Astryx chat page, concise tool status, history load, and failure/disconnect states.
- [ ] Add integration tests for direct conversation, streaming order, history pagination, malformed cursor, interrupt/resume both branches, replay, and checkpoint cleanup.
- [ ] Run normal tests exclusively against fakes; rerun the real provider diagnostic separately only as a compatibility smoke check.

## Verification

### Backend commands

```powershell
Set-Location backend
python -m pytest tests/unit/test_tool_result.py tests/unit/test_sse_contract.py tests/unit/test_agent_context.py -q
python -m pytest tests/integration/test_chat_api.py tests/integration/test_chat_history.py -q
python -m pytest tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q
```

Expected:

- Invalid result/status coupling and invalid SSE statuses fail validation.
- Greeting/general-question turns persist user+assistant messages, create one completed run, create zero tool executions, and emit no `tool_status`/`approval_required`.
- History pagination is deterministic; malformed cursors return `422`; hydrated tool activity contains no `role='tool'` message.
- Both synthetic approval branches resume across a new request, terminate once, persist one tool result/side effect, and remove only their checkpoint.
- Repeating a terminal resume produces only persisted terminal state.

### Frontend commands

```powershell
Set-Location frontend
npm test -- --run src/test/sse-reducer.test.ts src/test/chat-page.test.tsx
npm run typecheck
npm run build
```

Expected: ordered/deduplicated events, exact statuses, history load, concise tool UI, disabled in-flight composer, and visible failed/disconnected states all pass.

### Local full-path check

Start Compose and send a greeting through the UI. Expected: natural response in the same conversation with streamed text and no tool activity. Run the synthetic integration profile only in the test environment; verify an interrupt survives a request boundary and both decisions finish without replay.

### Failure handling

- Provider timeout/malformed response becomes controlled run failure or a truthful completed explanation; never false success.
- Exceeding six tool iterations ends the run with a stable controlled failure.
- A new turn during interruption returns `APPROVAL_ACTION_REQUIRED` without persisting input.
- Stream disconnect does not rewrite durable run/tool state; hydration reflects the database truth.

## Handoff Contract

### Consumes
- docs/plans/Master_plan.md and the prior plan outputs named in Prerequisites.

### Produces
- The completed Master Phase 2: Chat Transport, Agent Runtime, and Persistence artifacts, scope decisions, and verification evidence preserved below.

### Next Consumer
Plan_4.md consumes the produced artifacts and must not reimplement this phase's owned work.

### Historical Handoff Notes

Plan 4 receives:

- One persistent conversation and deterministic hydrated history.
- Durable per-turn Agent runs and idempotent tool execution/replay keyed only by `(run_id, tool_call_id)`.
- Validated SSE contracts, thin chat/history/resume endpoints, and a working reducer/UI shell.
- One reusable LangGraph runner with injected tool registry, interrupt/resume, bounded context, six-iteration guard, and checkpoint cleanup.
- A verified ShopAIKey chat adapter and conversation-first prompt.
- The interrupted-run guard that must also protect CV uploads.

Plan 4 replaces no generic runtime behavior. It adds the first three production tools (`propose_profile_from_cv`, `propose_profile_update`, `commit_profile_draft`), compact approved candidate context, profile-specific approval actions/cards, and CV endpoints by reusing these contracts. The test-only synthetic tool remains excluded from production.
