# Plan 3 - Master Phase 2: Chat Transport, Agent Runtime, and Persistence

## 1. Objective

Deliver the reusable conversation and Agent execution spine: one persistent application conversation, per-turn LangGraph runs, validated SSE transport, controlled tool execution, interrupt/resume, sanitized tool activity, and the base Astryx chat shell.

## 2. Source of Truth

- `Master_plan.md` sections 4 and 6, architecture ownership and application persistence.
- Section 12, **Agent Architecture**.
- Sections 13-14, **Agent-Facing Tool Contracts** and **Public FastAPI Boundary**.
- Sections 15-16, base chat UX and verified ShopAIKey integration.
- Sections 20, 22-24, failure, security, environment, and tests.
- Section 25, **Phase 2 - Chat transport, Agent runtime, and persistence**.
- `Plan_2.md` owns the database, settings, health, and Compose foundation reused here.

## 3. Prerequisites from Prior Phases

- [ ] Plan 1 records a passing ShopAIKey tool-call/schema mode and Astryx component matrix.
- [ ] Plan 2 provides running frontend/backend/Neo4j services and an upgraded SQLite database.
- [ ] `conversation`, `chat_messages`, `agent_runs`, and `tool_executions` tables exist.
- [ ] Async database sessions and root settings are stable.
- [ ] The frontend has the pinned Astryx neutral theme.

## 4. Scope

- Implement repositories for the singleton conversation, messages, Agent runs, and tool executions.
- Define validated server-to-client SSE event models.
- Implement chat history, turn, and run-resume endpoints.
- Create one LangGraph `StateGraph` with one LLM decision node and one `ToolNode`.
- Enforce per-turn run/thread IDs, six-iteration limit, error boundaries, interrupt/resume, and completed-checkpoint cleanup.
- Implement the production ShopAIKey `ChatOpenAI` adapter using the verified Plan 1 mode.
- Add the domain-focused system policy and untrusted-document delimiters.
- Implement the frontend SSE parser/reducer, history hydration, base chat shell, and sanitized `ChatToolCalls` rendering.
- Prove the complete path with one local synthetic tool that is removed or test-only after verification.

## 5. Out of Scope

- PDF upload/parsing, Candidate Profile schemas, drafts, approval UI, or profile writes.
- JD URL fetching, extraction, deduplication, embedding, or graph synchronization.
- Production implementations of the seven domain tools; this phase creates only their registration/runtime seam.
- Matching, scoring, evaluation, and match cards.
- Multiple conversations, multiple agents, agent handoffs, permanent checkpoint memory, or full-history prompt injection.
- Public profile/job CRUD endpoints or direct frontend access to backend stores/providers.

## 6. Target Directory Structure

```text
JobAgent/
|-- backend/
|   |-- app/
|   |   |-- api/chat.py
|   |   |-- agent/{graph.py,state.py,lifecycle.py,prompt.py}
|   |   |-- tools/registry.py
|   |   |-- services/{chat_service.py,shopaikey_chat.py}
|   |   |-- repositories/{conversations.py,agent_runs.py,tool_executions.py}
|   |   `-- schemas/{chat.py,sse.py}
|   `-- tests/{unit,integration}/
`-- frontend/
    `-- src/
        |-- app/
        |-- features/chat/{api,reducer,components}/
        |-- lib/sse/
        `-- test/
```

The exact file split may vary to keep modules below the repository's focused-file target; API routes orchestrate services and do not duplicate run logic.

## 7. Technical Specifications

### 7.1 Persistent conversation and run lifecycle

- Ensure exactly one application `conversation` row through an idempotent repository method.
- Persist each user message before starting a run.
- Create one `agent_runs` row and one LangGraph `thread_id` per user turn; use the same run/thread when resuming an interrupt.
- Persist assistant messages only from validated final output.
- Delete completed run checkpoint rows after final persistence; retain messages, run outcome, and sanitized tool records.
- On disconnect, continue only long enough to reach a safe persisted run state; reconnect uses history/run state rather than replaying writes.

### 7.2 Agent state

```python
class AgentState(TypedDict):
    conversation_id: str
    run_id: str
    messages_for_this_turn: list[Any]
    recent_context: list[Any]
    candidate_context: dict[str, Any] | None
    attachment_ids: list[str]
    pending_approval: dict[str, Any] | None
    tool_iteration_count: int
    error: dict[str, Any] | None
```

Large PDF/JD bodies are referenced by IDs and never inserted into state. Context assembly includes approved profile/preferences when available, relevant memory facts, current turn, and a bounded recent window.

### 7.3 Graph topology and limits

```text
START -> load_context -> agent_decision
agent_decision -> ToolNode -> increment_iteration -> agent_decision
agent_decision -> persist_response -> cleanup_checkpoint -> END
```

Stop with a controlled `TOOL_LOOP_LIMIT_EXCEEDED` failure before a seventh tool execution. The LLM does not control retries. Application services own deterministic retry policy, and structured tool failures cannot be converted into success text.

### 7.4 Public chat contracts

Implement only:

```text
GET  /api/chat/history
POST /api/chat/turns
POST /api/chat/runs/{run_id}/resume
```

Turn input contains user text plus bounded attachment IDs; resume input contains the validated approval/correction command and idempotency key. Both POST endpoints return SSE. Duplicate idempotency keys return the existing run outcome and never repeat a write.

### 7.5 SSE event contract

Every event contains `event_id`, `run_id`, `timestamp`, and one validated payload. Supported event types are exactly:

```text
run_started | assistant_status | tool_started | tool_completed
approval_required | text_delta | run_completed | run_failed
```

FastAPI owns event ordering and client streaming. Provider streaming is an internal adapter capability. Tool events expose friendly label, `pending|running|complete|error`, duration, and short sanitized outcome only.

### 7.6 ShopAIKey adapter and prompt boundary

Use `ChatOpenAI` with the root base URL, locked model, temperature zero, and `bind_tools()`. Apply the verified schema mode and one-repair ceiling. Retry timeout/rate-limit failures once, then persist failure. Delimit CV/JD text as untrusted data. The system policy handles only CV, profile, preferences, JDs, saved jobs, matching, and skill gaps; unrelated messages receive the master-defined brief redirect without a tool call.

### 7.7 Frontend state

The SSE reducer must be a pure state transition keyed by `run_id` and `event_id`, ignore duplicate events, preserve order, render partial assistant text, map tool events to `ChatToolCalls`, surface failures, and disable conflicting sends while a run awaits approval.

## 8. Implementation Steps

- [ ] Implement singleton conversation and bounded-history repositories.
- [ ] Implement Agent run/tool-execution repositories and idempotency lookup.
- [ ] Define Pydantic SSE payload/event discriminated unions and ordering rules.
- [ ] Implement history hydration and the two SSE POST routes.
- [ ] Implement per-run AsyncSqliteSaver creation, resume lookup, and completed-checkpoint cleanup.
- [ ] Build the one-agent graph, ToolNode seam, iteration guard, and service error normalization.
- [ ] Implement the ShopAIKey adapter and domain/prompt-injection policy.
- [ ] Add a deterministic test-only tool and run it through the whole backend path.
- [ ] Implement the Astryx chat shell, composer, SSE client/reducer, message rendering, and sanitized tool display.
- [ ] Add backend integration and frontend reducer/component tests.
- [ ] Remove any production exposure of the synthetic tool after the end-to-end transport proof.

## 9. Verification & Testing Plan

- Unit-test SSE model validation, event ordering, context bounding, tool iteration guard, error normalization, and prompt delimiters.
- Integration-test history persistence, one run per turn, same-run resume, AsyncSqliteSaver lifecycle, and checkpoint cleanup.
- Use a fake ShopAIKey adapter in normal automated tests; real provider calls remain an explicit diagnostic only.
- Verify a synthetic tool traverses frontend -> FastAPI -> LangGraph -> ToolNode -> SSE -> frontend.
- Verify interrupt/resume works across separate requests and duplicate resume keys do not repeat execution.
- Verify unrelated messages produce the brief redirect and zero tool executions.
- Verify raw arguments, document content, secrets, headers, internal IDs, and stack traces never appear in SSE or logs.
- Frontend tests cover duplicate events, disconnect/error state, history hydration, tool mapping, and partial text.

The phase exits only when the transport proof works locally and completed checkpoints are removed while durable conversation history remains.

## 10. Handoff Notes for Plan 4 (Master Phase 3)

Plan 4 receives:

- Stable chat endpoints, SSE discriminated unions, frontend reducer, and Astryx chat shell.
- One controlled LangGraph tool loop with interrupt/resume and idempotency support.
- Tool registration and application-service seams.
- Durable conversation/run/tool observability repositories.
- Bounded context assembly and prompt-injection delimiters.

Plan 4 must add CV/profile tools and approval payloads through these seams. It must not create a second graph, second conversation path, alternate SSE contract, or direct HTTP calls from tools back into FastAPI.
