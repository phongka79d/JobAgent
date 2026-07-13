# JobAgent Plan 3 Execution Tasks

## Purpose

Translate `docs/plans/Plan_3.md` into the mandatory, sequential work needed to
deliver one persistent conversation over the React-FastAPI-LangGraph-SSE path.
These tasks own durable chat/run/tool state, one controlled Agent loop,
interrupt/resume and checkpoint cleanup, typed SSE, the verified ShopAIKey chat
adapter, and the base Astryx chat client. They do not implement production
CV/JD/profile/matching tools or alter the Plan 2 schema.

## Project Context Notes

- Root `README.md` was read before task derivation. It records Phase 0 as PASS
  and Plan 2 / Master Phase 1 as complete, including the exact SQLite schema,
  root-environment settings, UUID/UTC helpers, async sessions, health route,
  Astryx shell, and three-service Compose runtime that Plan 3 must reuse.
- The repository already owns `conversation`, `chat_messages`, `agent_runs`, and
  `tool_executions` in `backend/app/db/models/chat.py` and migration
  `0001_initial_schema`; runtime code must add repositories and services without
  calling `create_all()` or changing those tables/status values.
- `backend/pyproject.toml` already pins the Phase 1 stack. The Phase 0 report
  records intended pins for LangGraph, LangChain, LangChain Core, and
  `langchain-openai`; the SQLite checkpointer package is required by the approved
  plan but has no recorded exact pin, so (01A) must compatibility-check and
  exact-pin it before use rather than changing the locked stack.
- `backend/app/core/settings.py` already provides the masked ShopAIKey settings,
  model, temperature, SQLite path, and six-iteration limit. CORS in
  `backend/app/main.py` already reads the single `FRONTEND_ORIGIN` but currently
  permits only `GET`, so Plan 3 must extend the existing boundary for its POST
  routes without adding another configuration owner.
- `frontend/AGENTS.md` applies to UI work: run the pinned Astryx CLI before using
  components, use public component APIs and design tokens, and do not invent
  props, raw layout elements, internal imports, or another styling system.
- Phase 0 proved public Astryx chat composition at 0.1.4. Its optional
  `ChatToolCalls` visual status prop uses `pending | running | complete | error`,
  while Plan 3 requires application state and visible status vocabulary to stay
  `pending | running | completed | failed`. Frontend tasks must preserve the
  exact JobAgent statuses and use a documented composition without introducing
  `complete`/`error` aliases into application state.
- The user-supplied root agent rules apply: search before writing, reuse or
  safely refactor shared logic, keep files focused and ordinarily below 300
  lines, prefer the smallest working diff, and inspect every caller when shared
  behavior changes.

## Authority and Scope

### Primary Source

- Primary authority: `docs/plans/Plan_3.md`.
- Supporting architecture authority cited by that plan:
  `docs/plans/Master_plan.md`.
- Prerequisite compatibility evidence:
  `docs/feasibility/phase_0_report.md`.
- Repository context only: root `README.md`, `backend/pyproject.toml`,
  `backend/app/core/settings.py`, `backend/app/db/models/chat.py`,
  `backend/app/db/session.py`, `backend/app/main.py`, `frontend/package.json`,
  `frontend/src/app/App.tsx`, and `frontend/AGENTS.md`.

### Source Section Index

- `docs/plans/Plan_3.md > ## 1. Objective` -> complete persistent-conversation
  outcome and terminal-checkpoint/history boundary.
- `docs/plans/Plan_3.md > ## 3. Prerequisites from Prior Phases` -> required
  Phase 0 compatibility and Plan 2 foundation artifacts.
- `docs/plans/Plan_3.md > ## 4. Scope` and `## 5. Out of Scope` -> mandatory
  runtime/client capabilities and prohibited domain work.
- `docs/plans/Plan_3.md > ## 6. Target Directory Structure` -> ownership and
  module boundaries.
- `docs/plans/Plan_3.md > ## 7. Technical Specifications` -> durable contracts,
  repositories, history, Agent state/graph, checkpoints, SSE, endpoints, and UI.
- `docs/plans/Plan_3.md > ## 8. Implementation Steps` -> implementation order
  and fake-only normal-test rule.
- `docs/plans/Plan_3.md > ## 9. Verification & Testing Plan` -> required backend,
  frontend, integration, and controlled-failure evidence.
- `docs/plans/Plan_3.md > ## 10. Handoff Notes for Plan 4 / Master Phase 3` ->
  reusable artifacts and the production-tool boundary.
- `docs/plans/Master_plan.md > ### 4.1 Ownership rules` and
  `## 6. SQLite Database Contract > ### 6.2 Application table schemas` through
  `### 6.5 Migration and checkpoint ownership` -> durable ownership,
  transactions, replay identity, history joins, and checkpoint isolation.
- `docs/plans/Master_plan.md > ### 7.5 Tool execution result` and
  `## 12. Agent Architecture` -> exact result/state, one graph, bounded memory,
  conversation policy, and loop limit.
- `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary` through
  `### 14.2 SSE contract` -> endpoints, pagination, interruption guard, and SSE.
- `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.1 Layout`,
  `### 15.3 Chat components`, and `### 15.4 Tool activity display` -> Astryx
  client composition and concise tool rendering.
- `docs/plans/Master_plan.md > ## 16. ShopAIKey Integration > ### 16.1 Configuration`
  and `### 16.2 Startup/diagnostic compatibility checks` -> verified adapter
  configuration and provider-failure boundary.
- `docs/plans/Master_plan.md > ## 20. Failure and Recovery Policy`,
  `## 24. Local Testing Strategy`, and
  `## 25. Implementation Phases > ### Phase 2 — Chat transport, Agent runtime,
  and persistence` -> fake-backed tests, exit cases, and phase gate.
- `docs/feasibility/phase_0_report.md > ## Astryx component matrix`,
  `## ShopAIKey chat and embedding gate`, and
  `## Dependency decision record` -> exact public UI APIs, provider mode, and
  approved dependency pins.

### Approved Architecture and Constraints

- SQLite is authoritative for messages, run metadata, and durable tool status;
  LangGraph checkpoints are temporary package-owned continuation state.
- The only replay identity is `(run_id, tool_call_id)`. Provider ToolMessages
  remain in graph state/checkpoints and are never persisted as chat-message rows.
- API routes remain transport-only. Repositories own persistence, services own
  transactions/orchestration, graph nodes own no database writes, and no
  transaction remains open during provider/graph execution or SSE yielding.
- One `StateGraph` contains one LLM decision node and one `ToolNode`; production
  Plan 3 registers no domain tools. Only tests inject the side-effect-free
  synthetic interrupting tool.
- Run states are exactly `running | interrupted | completed | failed`; tool
  states are exactly `pending | running | completed | failed`. No aliases,
  second Agent, classifier, full-history injection, or second idempotency key.
- One per-turn/resume `AsyncSqliteSaver` uses the application SQLite file and the
  run ID as `thread_id`; only terminal-run checkpoint data is deleted.
- Normal automated tests use fakes and never call the real ShopAIKey API. The
  retained live diagnostic is an optional compatibility smoke check requiring a
  user-managed ignored root `.env`.
- The frontend talks only to FastAPI, keeps streaming state in one reducer,
  deduplicates by `event_id`, hydrates durable history as truth, and uses only
  the pinned Astryx public APIs.
- No schema migration, CV upload/profile/JD/matching behavior, production domain
  tool, Neo4j domain sync, worker, WebSocket, public CRUD, or cloud tracing
  belongs in these tasks.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Validated contracts and durable conversation/run/tool persistence | (01A), (01B), (01C), (01D) | Plan 2 complete; Phase 0 PASS |
| Batch02 | Bounded single-Agent graph with verified ShopAIKey adapter | (02A), (02B), (02C) | Batch01 artifacts as noted |
| Batch03 | Durable turn/resume lifecycle exposed through typed SSE endpoints | (03A), (03B), (03C) | Batch01, Batch02 |
| Batch04 | Exact-status React/Astryx conversation client and Phase 2 UI path | (04A), (04B) | Batch03 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_3_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_3_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Durable Chat Contracts and Persistence

### Goal

Establish validated public/durable contracts and focused repositories for the
single conversation before Agent or transport execution is introduced.

### Dependencies

- Phase 0 compatibility gates are PASS.
- Plan 2 schema, settings, async session, UUID, and UTC owners are present and
  remain unchanged.

### Scope Boundary

This batch owns Phase 2 dependency pins, Pydantic contracts, message/run/tool
repositories, replay, cursor pagination, and history hydration. It does not own
LangGraph execution, provider calls, checkpoints, FastAPI routes, or frontend UI.

### Tasks

- [x] (01A): Pin the Phase 2 runtime dependencies and define validated chat, ToolResult, and SSE contracts
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.1 Durable result and status contracts`; `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.7 SSE contract and ordering`; `docs/feasibility/phase_0_report.md > ## Dependency decision record`
  - Source Requirements:
    - Preserve every installed pin and add only the exact Phase 2 LangGraph,
      LangChain, `ChatOpenAI`, and SQLite-checkpointer packages actually used.
    - Define exact chat/history/run/resume, recursive JSON value, `ToolResult`,
      and all seven SSE event contracts with UUID event IDs, run IDs, aware UTC
      timestamps, exact states, and event-specific payload invariants.
    - Enforce `ToolResult` success/failure coupling and reject frontend/backend
      status aliases at validation boundaries.
  - Dependencies: Phase 0 dependency decision record and Plan 2 settings/schema;
    no task dependency.
  - User Action: None. Do not read or require the real root `.env` for tests.
  - Agent Work:
    1. Search manifests, schema modules, database constants, diagnostic code, and
       imports for reusable pins, JSON types, status constants, UUID, and UTC
       logic before adding dependencies or definitions.
    2. Add the recorded exact Phase 2 pins; compatibility-check and exact-pin the
       required SQLite checkpointer package because the source records no
       version, stopping if it requires changing a locked dependency.
    3. Implement focused Pydantic modules for common/chat/tool/SSE contracts,
       reusing the database status constants without creating another vocabulary.
    4. Add unit tests for every result/status/payload coupling, timestamp/UUID
       requirement, non-empty delta, limit/action validation, and invalid alias.
  - Output: An installable exact-pinned backend with one validated contract
    boundary shared by persistence, Agent runtime, SSE routes, and client types.
  - Acceptance:
    - `backend/pyproject.toml` retains existing pins and includes only exact
      compatible Phase 2 packages used by this plan.
    - `ToolResult` has exactly `ok`, `code`, `summary`, and `data`; terminal
      success/failure coupling is validated and raw document payloads are not
      represented by a special escape type.
    - All seven event names and exact run/tool states validate, while
      `complete` and `error` fail as application statuses.
    - Chat/history/resume inputs enforce non-empty messages, `limit` in 1..100,
      and exactly one approval action without exposing secrets.
  - Validation:
    - Required: `python -m pip install -e .\backend` -> the exact-pinned Phase 2
      backend resolves without changing the locked foundation stack.
    - Required: `Set-Location backend; python -m pytest tests/unit/test_tool_result.py tests/unit/test_sse_contract.py -q` -> all valid and invalid contract cases pass.
    - Required: `Set-Location backend; python -m ruff check app/schemas tests/unit/test_tool_result.py tests/unit/test_sse_contract.py; python -m mypy app` -> focused lint and full application typing pass.
  - Blocked Condition: A required SQLite checkpointer version cannot coexist
    with the approved exact pins; return resolver evidence and stop rather than
    upgrading or introducing a substitute stack.
  - Files: `backend/pyproject.toml`, `backend/app/schemas/common.py`, `backend/app/schemas/chat.py`, `backend/app/schemas/tools.py`, `backend/app/schemas/sse.py`, `backend/tests/unit/test_tool_result.py`, `backend/tests/unit/test_sse_contract.py`

- [x] (01B): Implement focused message and Agent-run repositories
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.2 Repository and transaction rules`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.2 Application table schemas`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.4 Transaction boundaries`
  - Source Requirements:
    - Message persistence inserts/lists only for `conversation='main'`, never
      persists `role='tool'`, and orders by `(created_at, id)`.
    - Run persistence creates one run per unique user message, enforces only the
      approved transitions, couples pending approval to interruption, and sets
      terminal error/completion fields consistently.
    - Repository operations accept the existing async session so higher services
      can own the required short atomic transactions.
  - Dependencies: (01A); existing Plan 2 models/session factory.
  - User Action: None.
  - Agent Work:
    1. Search the Plan 2 session/model/test helpers and every future caller named
       by the plan; reuse the singleton ID, status constants, UUID, UTC, and
       migration-backed temporary database setup.
    2. Implement separate message and run repositories with narrow methods and
       explicit transition validation; do not commit inside operations that must
       participate in a service-owned transaction.
    3. Add integration tests for deterministic message ordering, forbidden tool
       messages, one-run-per-user-message, allowed/forbidden transitions,
       interruption projection storage/clearing, and terminal timestamps.
    4. Inspect repository callers and session lifetimes, then record SQL/database
       evidence showing no schema creation or provider work was introduced.
  - Output: Reusable async repositories for durable messages and per-turn runs.
  - Acceptance:
    - Message operations are confined to the singleton conversation, use the
      existing model, and expose deterministic `(created_at, id)` ordering.
    - Run methods reject skipped/backward transitions and maintain exact
      `pending_approval_json`, `error_code`, and `completed_at` coupling.
    - The repositories do not open hidden sessions, commit caller-owned units of
      work, call external services, or modify the migration/schema.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_chat_persistence.py -q` -> message/run repository invariants and transitions pass on a migrated temporary SQLite file.
    - Required: `Set-Location backend; python -m ruff check app/repositories/chat_messages.py app/repositories/agent_runs.py tests/integration/test_chat_persistence.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n 'create_all|role.*tool' backend/app/repositories backend/app/db/models/chat.py` -> review finds no runtime schema creation or persisted tool-role path.
  - Blocked Condition: The existing Plan 2 models or migration do not match the
    primary source's fields, constraints, or status values; report exact schema
    evidence and stop instead of adding a migration.
  - Files: `backend/app/repositories/chat_messages.py`, `backend/app/repositories/agent_runs.py`, `backend/tests/integration/test_chat_persistence.py`

- [x] (01C): Implement durable tool transitions and exact identity replay
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.1 Durable result and status contracts`; `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.2 Repository and transaction rules`; `docs/plans/Master_plan.md > ### 7.5 Tool execution result`
  - Source Requirements:
    - Own get-or-create and replay by `(run_id, tool_call_id)` only, with exact
      `pending -> running -> completed|failed` transitions.
    - Validate every terminal stored result; completed rows have successful
      results/no error code and failed rows have matching stable failure codes.
    - Re-entry returns the exact stored terminal result without invoking the
      service or inserting another row.
  - Dependencies: (01A), (01B).
  - User Action: None.
  - Agent Work:
    1. Search the model unique constraint, status constants, session helpers, and
       all planned tool/runner callers before designing the repository/service
       boundary; reuse existing transaction and time helpers.
    2. Implement the focused tool-execution repository and service wrapper with
       short durable transitions, validated result serialization, duration, and
       race-safe handling of the database uniqueness identity.
    3. Add a counted local stub side effect and integration tests proving a
       repeated identity stores one row, invokes once, and returns byte-for-byte
       equivalent validated result data for both success and failure.
    4. Test illegal transitions and mismatched result/error coupling, then inspect
       all callers to ensure no second idempotency key or duplicate status owner.
  - Output: One durable tool execution/replay boundary ready for `ToolNode` use.
  - Acceptance:
    - Exactly one row and one service invocation exist for repeated
      `(run_id, tool_call_id)` under the tested replay path.
    - Durable state moves only through approved statuses, each transition commits
      outside provider/graph work, and terminal duration/result fields are set.
    - Replay returns the stored validated `ToolResult`; it neither reconstructs a
      new result nor persists a tool message/chat duplicate.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_tool_replay.py -q` -> success/failure replay, invocation count, uniqueness, and transition cases pass.
    - Required: `Set-Location backend; python -m ruff check app/repositories/tool_executions.py app/services/tool_execution.py tests/integration/test_tool_replay.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "idempotency|tool_call_id|result_json" backend/app` -> review evidence shows `(run_id, tool_call_id)` and `tool_executions.result_json` are the only replay identity/result store.
  - Blocked Condition: The existing unique constraint or terminal null-coupling
    prevents the source-required transitions/results; report database evidence
    and stop rather than introducing an alternate key or migration.
  - Files: `backend/app/repositories/tool_executions.py`, `backend/app/services/tool_execution.py`, `backend/tests/integration/test_tool_replay.py`

- [x] (01D): Implement opaque cursor history pagination and durable tool hydration
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.3 History cursor and hydration`; `docs/plans/Plan_3.md > ## 9. Verification & Testing Plan > ### Backend commands`; `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary > ### 14.1 API rules`
  - Source Requirements:
    - Encode only the oldest returned `(created_at, id)` pair in a validated
      URL-safe opaque cursor and reject malformed encoding/shape/time/UUID.
    - Query lexicographically older messages newest-first with `limit + 1`, use
      the extra row for `next_cursor`, and return each page chronologically.
    - Attach runs and durable tool activity to initiating user messages through
      `agent_runs.user_message_id`; response shape is exactly
      `{items, next_cursor}` and never contains `role='tool'`.
  - Dependencies: (01A), (01B), (01C).
  - User Action: None.
  - Agent Work:
    1. Search the existing composite message index and repository query helpers;
       reuse the shared UUID/UTC/Pydantic boundaries and avoid a second ordering
       or serialization implementation.
    2. Implement focused cursor encode/decode and history hydration services,
       keeping database joins/batching bounded and repository ownership clear.
    3. Add migrated-database integration cases for equal timestamps/tie-break
       IDs, first/middle/final pages, limits 1 and 100, no-more-pages null cursor,
       malformed cursors, and user-turn run/tool hydration.
    4. Verify durable tool activity replaces transient history state and no tool
       result is copied into a chat message or emitted as a message role.
  - Output: Deterministic chronological history pages with durable run/tool
    metadata and opaque pagination.
  - Acceptance:
    - Pagination has no duplicates or gaps across tied timestamps and produces a
      cursor only when older rows exist.
    - Every malformed cursor class reaches a validation error suitable for the
      route's FastAPI `422` response.
    - Hydration joins only the initiating user turn to its runs/tool executions,
      returns exactly `items` and `next_cursor`, and contains no tool-role item.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_chat_history.py -q` -> cursor, ordering, pagination, malformed-input, and hydration cases pass.
    - Required: `Set-Location backend; python -m ruff check app/services/chat_history.py tests/integration/test_chat_history.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "ORDER BY|created_at|next_cursor|role.*tool" backend/app/repositories backend/app/services/chat_history.py` -> review evidence confirms one ordering contract and no tool-message persistence.
  - Blocked Condition: The existing `(conversation_id, created_at, id)` index or
    model timestamp/ID types do not support the exact lexicographic contract;
    report evidence and stop rather than changing schema in Plan 3.
  - Files: `backend/app/services/chat_history.py`, `backend/app/schemas/common.py`, `backend/app/schemas/chat.py`, `backend/tests/integration/test_chat_history.py`

## Mandatory Batch02 - Controlled Single-Agent Runtime

### Goal

Build the bounded Agent state, conversation-first model boundary, and one
injected-registry LangGraph loop without exposing transport routes.

### Dependencies

- Batch01 provides validated contracts and durable repository/service boundaries.
- Phase 0 provides the verified ShopAIKey mode and exact intended adapter pins.

### Scope Boundary

This batch owns context/state, prompt/model adapter, registry, graph topology,
loop limit, and controlled graph failures. It does not own HTTP/SSE framing,
application transaction orchestration, production tools, or frontend behavior.

### Tasks

- [x] (02A): Define exact Agent state and bounded recent-context loading
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.4 Agent context and state`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.3 Agent state`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.4 Memory policy`
  - Source Requirements:
    - `AgentState` contains only the nine named fields; conversation is `main`
      and run ID is the future LangGraph `thread_id`.
    - Load a documented prompt-budget-bounded recent window, never full history;
      candidate context is empty and raw CV/JD bodies never enter state.
    - Attachment and future large-document references remain IDs only.
  - Dependencies: (01A), (01B), (01D).
  - User Action: None.
  - Agent Work:
    1. Search message/history models and future runner/graph call sites for
       reusable contracts; choose the smallest source-supported deterministic
       budget rule and document its ceiling next to the owner.
    2. Implement the exact typed state and bounded context loader using repository
       ordering without duplicating history pagination or loading unbounded rows.
    3. Add unit tests for exact state keys, singleton conversation/run identity,
       boundary-size context selection, candidate emptiness, and exclusion of raw
       documents/irrelevant old messages.
    4. Inspect every state constructor/caller and record evidence that no extra
       memory/classifier/second-agent fields or full-history path exists.
  - Output: One compact, deterministic Agent input state and context loader.
  - Acceptance:
    - Runtime state exposes exactly `conversation_id`, `run_id`,
      `messages_for_this_turn`, `recent_context`, `candidate_context`,
      `attachment_ids`, `pending_approval`, `tool_iteration_count`, and `error`.
    - Context selection is bounded by one documented prompt budget and preserves
      deterministic recent ordering without loading an unbounded conversation.
    - Candidate context is empty and state contains only attachment IDs, never
      raw document bodies or generic long-term memory.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_agent_context.py -q` -> exact-shape and bounded-context cases pass.
    - Required: `Set-Location backend; python -m ruff check app/agent/state.py app/agent/context.py tests/unit/test_agent_context.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "full.history|64K|candidate_context|raw_(content|cv|jd)|AgentState" backend/app/agent` -> no unbounded/raw-document or extra Agent-state path exists.
  - Blocked Condition: The primary source does not provide enough information to
    choose a deterministic bounded prompt rule compatible with existing message
    fields; document the ambiguity and stop rather than defaulting to full history.
  - Files: `backend/app/agent/state.py`, `backend/app/agent/context.py`, `backend/tests/unit/test_agent_context.py`

- [x] (02B): Implement the verified ShopAIKey ChatOpenAI adapter and conversation-first prompt
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.5 Graph and model adapter`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.5 Conversation and tool policy`; `docs/plans/Master_plan.md > ## 16. ShopAIKey Integration > ### 16.1 Configuration`; `docs/feasibility/phase_0_report.md > ## ShopAIKey chat and embedding gate`
  - Source Requirements:
    - Build `ChatOpenAI` from the existing masked root settings with the custom
      base URL, `gpt-4o-mini`, temperature zero, and verified Phase 0 tool mode.
    - Prompt supports greetings, general knowledge, and job conversation while
      limiting tool use to injected registered JobAgent capabilities and never
      claiming success after a failed result.
    - No real provider call occurs in normal tests; no classifier or fallback
      provider/model is introduced.
  - Dependencies: (01A), (02A).
  - User Action: None for required validation. A live diagnostic remains optional
    and uses only a user-managed ignored root `.env`.
  - Agent Work:
    1. Search settings, the retained diagnostic, Phase 0 schema/tool evidence, and
       adapter call sites; reuse masked secrets/model settings and do not copy a
       second provider configuration loader.
    2. Implement the focused `ChatOpenAI` factory/adapter and conversation-first
       prompt builder, exposing injection seams for fake models and tool lists.
    3. Add fake/monkeypatched unit tests proving exact configuration, empty-tool
       direct conversation, tool-boundary wording, and truthful failed-result
       instructions without making network calls or printing secrets.
    4. Inspect every provider/model caller and record evidence that only the
       adapter owns construction and only the approved model/mode is used.
  - Output: One injectable, secret-safe ShopAIKey chat adapter and bounded prompt.
  - Acceptance:
    - Adapter construction uses the cached settings boundary, custom base URL,
      masked API key value, exact model, and temperature zero.
    - The prompt permits direct natural answers, enumerates only injected tools,
      forbids false success, and contains no synthetic/production domain tool
      when the registry is empty.
    - Required tests make zero outbound network calls and no logs/reprs expose a
      provider key or authorization header.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_shopaikey_chat.py -q` -> adapter configuration, prompt, injection, and secret tests pass using fakes.
    - Required: `Set-Location backend; python -m ruff check app/adapters/shopaikey_chat.py app/agent/prompt.py tests/unit/test_shopaikey_chat.py; python -m mypy app` -> focused lint and application typing pass.
    - Optional: `python infrastructure/scripts/diagnose_shopaikey.py` from the repository root -> separately reconfirms `SHOPAIKEY_COMPATIBILITY=PASS` when the user supplies a valid ignored credential; it is not normal-test evidence.
  - Blocked Condition: Required adapter behavior cannot use the Phase 0-approved
    exact pins/mode; report the sanitized cause without changing model/provider
    or exposing secrets. Missing credentials for the optional live smoke do not
    block required task acceptance.
  - Files: `backend/app/adapters/shopaikey_chat.py`, `backend/app/agent/prompt.py`, `backend/tests/unit/test_shopaikey_chat.py`

- [x] (02C): Build the injected-registry one-decision/one-ToolNode graph with a six-pass guard
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.5 Graph and model adapter`; `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.4 Agent context and state`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.1 One Agent, one controlled loop`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.6 Tool loop limits`
  - Source Requirements:
    - Build exactly one `StateGraph` with one LLM decision node and one
      `ToolNode`, routing tool calls back to the LLM and direct answers to final
      output.
    - Increment before each tool pass and stop with a stable controlled failure
      when a seventh pass would exceed the configured limit of six.
    - Production registry is empty; tests inject fakes only. Graph nodes contain
      no database writes, API calls back into FastAPI, or hidden transactions.
  - Dependencies: (01C), (02A), (02B).
  - User Action: None.
  - Agent Work:
    1. Search installed LangGraph APIs, existing graph modules, service boundaries,
       and all future runner callers; reuse the tool execution service rather
       than duplicating durable status/replay behavior.
    2. Implement the minimal registry interface and one graph topology with
       injected model/tools, exact state, decision/tool routing, iteration count,
       and a controlled stable error boundary.
    3. Add a deterministic fake chat model and unit tests for direct response,
       tool round-trip, failed ToolResult truthfulness input, six allowed passes,
       seventh-pass failure, and production empty-registry behavior.
    4. Inspect graph-node callers and imports to prove there is one Agent/graph,
       one ToolNode, and no persistence/transport/domain-tool leakage.
  - Output: A testable single-Agent graph factory with bounded tool execution.
  - Acceptance:
    - Graph inspection/tests show exactly one decision node and one `ToolNode`;
      tool calls loop back and direct responses terminate.
    - The counter increments before each tool pass, allows at most six, and emits
      one stable controlled failure beyond the limit.
    - Shipped registry contains zero production/synthetic tools, while injected
      test tools work without changing graph construction.
    - Graph nodes perform no direct SQLAlchemy/FastAPI/provider-construction work.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_agent_graph.py -q` -> topology, direct/tool, registry, error, and loop-limit cases pass.
    - Required: `Set-Location backend; python -m ruff check app/agent/graph.py app/tools/registry.py tests/fakes/fake_chat_model.py tests/unit/test_agent_graph.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "StateGraph|ToolNode|include_router|AsyncSession|session_scope|synthetic" backend/app/agent backend/app/tools` -> review evidence shows one graph/ToolNode and no transport, persistence, or shipped synthetic tool.
  - Blocked Condition: The exact-pinned LangGraph/LangChain APIs cannot express
    the approved graph/injection boundary without version changes; return the
    compile/test evidence to (01A) and stop.
  - Files: `backend/app/agent/graph.py`, `backend/app/tools/registry.py`, `backend/tests/fakes/fake_chat_model.py`, `backend/tests/unit/test_agent_graph.py`

## Mandatory Batch03 - Durable Turn, Resume, and SSE Transport

### Goal

Run the graph through request-scoped checkpoints, coordinate short durable
transactions, and expose history/turn/resume behavior through validated SSE.

### Dependencies

- Batch01 repositories/contracts and Batch02 graph/adapter are A2-accepted.

### Scope Boundary

This batch owns checkpointer/runner lifecycle, chat transaction services, generic
interrupt/resume mechanics, terminal cleanup/no-op replay, and thin FastAPI/SSE
routes. It does not own frontend state or production domain tools.

### Tasks

- [x] (03A): Implement request-scoped checkpoints, runner streaming, and terminal cleanup
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.6 Checkpoint lifecycle and interrupt/resume`; `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.7 SSE contract and ordering`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.5 Migration and checkpoint ownership`
  - Source Requirements:
    - Open/close one `AsyncSqliteSaver` lifecycle per turn/resume request against
      the configured application SQLite file and use `run_id` as `thread_id`.
    - Translate runner activity into validated typed events while preserving
      ordered deltas/tool transitions and controlled failures.
    - After durable terminal commit is confirmed, delete only that run's
      checkpoint; never let Alembic/application repositories manage checkpoint
      tables or delete another run's continuation.
  - Dependencies: (01A), (01C), (02C).
  - User Action: None.
  - Agent Work:
    1. Search the installed checkpointer API, SQLite path/session helpers, graph
       streaming APIs, and checkpoint callers; reuse configuration and avoid a
       second SQLite URL/path parser.
    2. Implement focused checkpoint lifecycle and runner modules with injected
       graph/model/registry, typed event construction, per-request close, and
       exact per-thread terminal deletion after a durable-terminal callback.
    3. Add temporary-SQLite tests for lifecycle closure, run/thread identity,
       ordered direct-answer events, controlled graph failure, per-run deletion,
       and preservation of another run's checkpoint.
    4. Inspect migration/repository code and runner transactions to prove
       checkpoint ownership isolation and no open application transaction during
       graph execution or event iteration.
  - Output: A request-scoped Agent runner that streams validated events and
    cleans only durably terminal checkpoints.
  - Acceptance:
    - Each invocation opens and closes exactly one checkpointer lifecycle on the
      configured SQLite file and uses the run ID as thread ID.
    - Direct-answer stream order is `run_started`, optional
      `assistant_status`, ordered non-empty `text_delta`, then terminal event;
      controlled failures produce `run_failed` with safe stable code/summary.
    - Terminal cleanup occurs only after the injected durable-commit signal and
      removes no other thread; interrupted checkpoints remain.
    - Alembic migration and application repositories contain no checkpoint-table
      create/update/drop logic.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_agent_runner.py -q` -> lifecycle, ordering, failure, cleanup, and isolation cases pass.
    - Required: `Set-Location backend; python -m ruff check app/agent/checkpoint.py app/agent/runner.py tests/integration/test_agent_runner.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "checkpoint|checkpoints|checkpoint_writes" backend/migrations backend/app/repositories` -> no Alembic/application repository owns package checkpoint tables.
  - Blocked Condition: The pinned checkpointer exposes no supported per-thread
    deletion mechanism needed by the approved lifecycle; return exact API/test
    evidence to (01A) instead of deleting the database or all checkpoints.
  - Files: `backend/app/agent/checkpoint.py`, `backend/app/agent/runner.py`, `backend/tests/integration/test_agent_runner.py`

- [x] (03B): Implement atomic chat-turn and generic interrupt/resume services with a synthetic proof tool
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.2 Repository and transaction rules`; `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.6 Checkpoint lifecycle and interrupt/resume`; `docs/plans/Plan_3.md > ## 9. Verification & Testing Plan > ### Failure handling`
  - Source Requirements:
    - Atomically persist user message plus running run before graph execution;
      atomically persist assistant message plus terminal run after success; mark
      unrecoverable failure durably while retaining the user turn.
    - Interruption persists compact approval projection and ends with
      `approval_required`; resume atomically returns the same run to `running`,
      clears projection, validates one allowed action, and continues its thread.
    - Block new turns during any interruption before insert. Terminal resume is a
      no-op stream of persisted terminal state with no graph execution, text
      replay, or repeated side effect.
  - Dependencies: (01B), (01C), (03A).
  - User Action: None. The synthetic tool and fake model are test-only and make
    no provider/domain calls.
  - Agent Work:
    1. Search repository transition APIs, transaction/session owners, runner
       callbacks, and every turn/resume caller; reuse them without moving writes
       into graph nodes or keeping transactions open across graph/SSE work.
    2. Implement focused chat-turn orchestration for create, terminal success,
       failure, interruption guard/projection, action validation, resume, and
       terminal no-op using short explicit transactions.
    3. Add the side-effect-free synthetic interrupting tool only under tests and
       integration cases for both allowed decisions across a new request,
       single side effect/result, retained interrupt checkpoint, terminal cleanup,
       no-op terminal resume, and blocked new turn with zero inserted rows.
    4. Inspect every transaction/caller and failure path to verify durable truth
       survives disconnect/failure without false success or duplicate execution.
  - Output: Durable per-turn/resume application services with generic tested
    interruption semantics and no production tool registration.
  - Acceptance:
    - User/run creation and assistant/terminal completion are each one atomic
      transaction; no transaction spans provider/graph execution or SSE yield.
    - Both synthetic decision branches resume the same run/thread across a new
      request, invoke the side effect once, store one terminal result, and remove
      only their terminal checkpoint.
    - New-turn interruption guard returns `APPROVAL_ACTION_REQUIRED` before any
      insert, and invalid actions leave persisted interruption unchanged.
    - Resume of completed/failed run emits only persisted terminal run state and
      performs no graph/model/tool call or text-delta replay.
    - `backend/app/tools/registry.py` remains empty in production and the
      synthetic tool exists only under `backend/tests/fakes/`.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q` -> both branches, guard, replay, no-op, persistence, and cleanup cases pass.
    - Required: `Set-Location backend; python -m ruff check app/services/chat_turns.py tests/fakes/synthetic_tool.py tests/integration/test_interrupt_resume.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "synthetic|interrupt\(|pending_approval|APPROVAL_ACTION_REQUIRED" backend/app backend/tests/fakes` -> synthetic registration is test-only and generic production interruption code contains no domain workflow.
  - Blocked Condition: The runner/checkpointer cannot preserve an interrupt
    across a closed request lifecycle with the same run/thread ID; return exact
    evidence to (03A) and stop rather than retaining a process-global saver.
  - Files: `backend/app/services/chat_turns.py`, `backend/tests/fakes/synthetic_tool.py`, `backend/tests/integration/test_interrupt_resume.py`, `backend/tests/integration/test_tool_replay.py`

- [x] (03C): Expose thin history, turn, and resume endpoints with validated SSE framing
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.7 SSE contract and ordering`; `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.8 Public endpoint behavior`; `docs/plans/Plan_3.md > ## 9. Verification & Testing Plan > ### Backend commands`; `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary`
  - Source Requirements:
    - Expose only `GET /api/chat/history`, `POST /api/chat/turns`, and
      `POST /api/chat/runs/{run_id}/resume` in addition to existing health.
    - Routes validate input, delegate to services, and frame already validated
      SSE; they contain no Agent/business/database logic and keep no transaction
      open while yielding.
    - History returns `422` for malformed cursor; direct greetings/general
      answers persist one completed run, zero tool executions, and no tool or
      approval event. CORS remains restricted to `FRONTEND_ORIGIN`.
    - The injected synthetic tool must also traverse the public turn/resume SSE
      boundary in integration tests; it never enters production registration.
  - Dependencies: (01D), (03A), (03B).
  - User Action: None for required fake-backed tests.
  - Agent Work:
    1. Search the existing health router/application factory, CORS tests, FastAPI
       native SSE API, and service call sites; extend the existing application
       boundary without duplicating settings/dependencies/lifecycle owners.
    2. Implement dependency providers and a focused chat router for the three
       endpoints, validated SSE framing, path/query/body validation, safe error
       mapping, and only the necessary CORS method extension.
    3. Extend fake-backed API/history integration tests for exact URLs/shapes,
       direct-answer event order, durable user/assistant/run state, zero tools,
       malformed cursor `422`, interruption/resume delegation, failure safety,
       and permitted/disallowed origins.
    4. Inspect every route and service caller to prove transport thinness,
       client disconnect does not rewrite durable state, and no real provider or
       out-of-scope public route is reachable.
  - Output: The complete typed FastAPI chat/history/resume boundary over the
    durable Agent services.
  - Acceptance:
    - OpenAPI/application routes contain exactly health plus the three Plan 3
      functional endpoints; turn/resume responses use SSE and history shape is
      exactly `{items, next_cursor}`.
    - Every yielded event validates against (01A), includes common metadata, and
      follows direct/tool/interruption/terminal ordering rules.
    - A greeting/general question creates user+assistant messages and one
      completed run, creates no tool execution or domain mutation, and emits no
      `tool_status`/`approval_required`.
    - Fake-backed API integration drives the test-only synthetic tool through
      actual turn and resume endpoints, survives the request boundary, and
      observes one side effect/result plus terminal checkpoint cleanup.
    - Malformed cursor returns `422`; safe controlled errors expose no stack or
      secret; CORS allows only the configured frontend origin for required
      `GET`/`POST` behavior.
    - Route handlers contain no graph construction, business rules, SQLAlchemy
      writes, checkpoint table logic, or direct provider call.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_chat_api.py tests/integration/test_chat_history.py -q` -> endpoint, SSE, direct conversation, history, validation, CORS, and failure cases pass with fakes.
    - Required: `Set-Location backend; python -m pytest tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q` -> public lifecycle does not regress interrupt/replay guarantees.
    - Required: `Set-Location backend; python -m ruff check app/api/chat.py app/api/dependencies.py app/main.py tests/integration/test_chat_api.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "@router\.(get|post)|include_router|CORSMiddleware|AsyncSession|StateGraph|ChatOpenAI" backend/app/api backend/app/main.py` -> exact route/CORS scope and thin-handler evidence is reviewable.
  - Blocked Condition: The pinned FastAPI native SSE surface cannot frame the
    validated event contract or close cleanly on disconnect; return exact
    runtime/test evidence to (01A) rather than adding WebSockets/provider-owned
    streaming or an unapproved transport stack.
  - Files: `backend/app/api/chat.py`, `backend/app/api/dependencies.py`, `backend/app/main.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/integration/test_chat_history.py`

## Mandatory Batch04 - React and Astryx Conversation Client

### Goal

Consume the durable history and typed SSE boundary through one exact-status
frontend reducer and a pinned Astryx conversation interface.

### Dependencies

- (03C) exposes the final validated HTTP/SSE contract.
- The Plan 2 `AppShell`, neutral theme, frontend scripts, and lockfile remain the
  foundation.

### Scope Boundary

This batch owns client types, API/SSE transport, reducer, chat page, history
pagination, concise tool activity, and stream failure/disconnection states. It
does not own approval cards, sidebar/profile/JD/match UI, domain tools, or a
second client state store.

### Tasks

- [ ] (04A): Implement typed chat API/SSE parsing and the single streaming reducer
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.7 SSE contract and ordering`; `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.9 Frontend reducer and UI`; `docs/plans/Plan_3.md > ## 9. Verification & Testing Plan > ### Frontend commands`
  - Source Requirements:
    - Client types mirror exact backend event/run/tool/history contracts and
      accept no `complete`/`error` application status aliases.
    - One reducer owns message/run/tool streaming state, deduplicates by
      `event_id`, appends ordered deltas, and does not infer completion after
      failure/disconnect.
    - Durable history hydration replaces transient tool state for completed
      turns; API client reads only `VITE_API_BASE_URL` and supports history,
      turns, resume, and streamed failure handling.
  - Dependencies: (03C).
  - User Action: None.
  - Agent Work:
    1. Search current frontend types/state/API helpers and backend schemas before
       defining contracts; reuse the one environment boundary and avoid a second
       reducer, event vocabulary, or parser.
    2. Implement focused types, incremental SSE parser/stream helper, chat API
       client, history hydration, and pure reducer with event-ID deduplication and
       exact ordering/status rules.
    3. Add reducer/parser tests for split frames, ordered/malformed events,
       duplicates, direct/tool/interruption/terminal paths, durable hydration,
       load-older merge, and failed/disconnected states.
    4. Search all status/event consumers and record evidence that exact server
       vocabulary has one client owner and no aliases or false-terminal path.
  - Output: A typed, tested client transport and single durable-aware streaming
    state reducer ready for rendering.
  - Acceptance:
    - Client union contains exactly the seven events and exact run/tool statuses;
      unknown/malformed events fail safely without mutating state.
    - Duplicate event IDs are ignored, deltas append once in arrival order, and
      completed durable history replaces matching transient tool state.
    - Failure/disconnect remains visibly non-complete; history pages merge in
      chronological order without duplicates and preserve `next_cursor`.
    - API code reads only `VITE_API_BASE_URL`, calls only the three Plan 3 routes,
      and does not access provider/database/graph services.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/sse-reducer.test.ts` -> parsing, event, reducer, deduplication, history, and failure cases pass.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> frontend lint and exact client typing pass.
    - Required: `rg -n "complete|error|completed|failed|event_id|VITE_" frontend/src/features/chat frontend/src/lib` -> exact status ownership, deduplication, and environment boundary are reviewable with no aliases.
  - Blocked Condition: Backend contract from (03C) differs from the approved
    schema/event vocabulary; return the mismatch to (03C) instead of adding
    client aliases or permissive unknown-status handling.
  - Files: `frontend/src/features/chat/types.ts`, `frontend/src/features/chat/history.ts`, `frontend/src/features/chat/reducer.ts`, `frontend/src/lib/api/chat.ts`, `frontend/src/lib/sse/parser.ts`, `frontend/src/lib/sse/stream.ts`, `frontend/src/test/sse-reducer.test.ts`

- [ ] (04B): Build the base Astryx chat page with history, concise tool activity, and failure states
  - Source of Truth: `docs/plans/Plan_3.md > ## 7. Technical Specifications > ### 7.9 Frontend reducer and UI`; `docs/plans/Plan_3.md > ## 9. Verification & Testing Plan > ### Frontend commands`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.1 Layout`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.3 Chat components`; `docs/feasibility/phase_0_report.md > ## Astryx component matrix`
  - Source Requirements:
    - Extend the existing `AppShell` with pinned public `ChatLayout`,
      `ChatMessageList`, `ChatMessage`, `ChatComposer`, `ChatToolCalls`, and
      `ChatSystemMessage` APIs discovered through the local CLI.
    - Render history/load-older, ordered streamed text, disabled in-flight
      composer, friendly concise tool label/exact status/duration/outcome, and
      visible failed/disconnected/interrupted states.
    - Do not expose raw arguments/documents/stacks, invent Astryx props, create a
      second state owner, or implement later approval/domain/sidebar UI.
  - Dependencies: (04A).
  - User Action: None for required automated validation. The optional local
    Compose/provider smoke requires the user's ignored root `.env`, valid
    ShopAIKey credential, Docker, and free loopback ports.
  - Agent Work:
    1. Run Astryx discovery (`build`, relevant template/docs, and each named
       component command) under `frontend/AGENTS.md`; inspect the existing shell
       and reducer before selecting the smallest documented composition.
    2. Implement focused page/message/tool components and wire only the (04A)
       reducer/API owner into the Plan 2 shell. Preserve exact JobAgent statuses;
       because Astryx's optional visual status prop has a different vocabulary,
       use a documented composition that shows exact status text without adding
       `complete`/`error` to application state.
    3. Add UI tests for initial/history/load-older rendering, send/stream success,
       concise exact tool activity, in-flight disable, event deduplication as
       observed in UI, and failed/disconnected/interrupted visibility.
    4. Run the complete frontend gates and inspect component imports/styles/state
       callers for public APIs, token usage, one reducer, and absence of later UI.
  - Output: A responsive base Astryx conversation UI over the Plan 3 API/SSE path.
  - Acceptance:
    - Existing neutral `AppShell` contains the documented chat layout, message
      list/messages, composer, tool calls, and system status components through
      public Astryx 0.1.4 imports only.
    - Page loads chronological history, loads older pages by `next_cursor`, sends
      a turn, streams text once, and disables submission while a run is active.
    - Combined fake-backed backend API/Agent tests and frontend parser/reducer/UI
      tests cover the React-FastAPI-LangGraph-SSE contract for direct answers and
      synthetic interrupt/resume without a real provider call.
    - Tool activity shows friendly name, exact `pending|running|completed|failed`
      text, duration, and short outcome only; application/client state contains
      no `complete`/`error` aliases and no raw arguments/document/stack.
    - Failed, disconnected, and interrupted states remain visible and never
      render a false completed run; reducer remains the only streaming owner.
    - No profile approval card, PDF upload, sidebar, saved-job/match card, domain
      tool, internal Astryx import, raw visual scale, or second design system is
      introduced.
  - Validation:
    - Required: `Set-Location frontend; npx astryx component ChatLayout; npx astryx component ChatMessage; npx astryx component ChatComposer; npx astryx component ChatToolCalls` -> pinned public component APIs used by the page are documented before implementation.
    - Required: `Set-Location frontend; npm test -- --run src/test/sse-reducer.test.ts src/test/chat-page.test.tsx; npm run lint; npm run typecheck; npm run build` -> reducer, UI, lint, typing, and production build pass.
    - Required: `Set-Location backend; python -m pytest tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q` -> the fake-backed public API/Agent side of the direct and synthetic full-path contract passes without a provider call.
    - Required: `rg -n "@astryxdesign/.*/(src|dist)/|#[0-9A-Fa-f]{3,8}|\bcomplete\b|\berror\b|profile|match_jobs|save_job" frontend/src` -> no internal import/raw color/status alias/out-of-scope feature is introduced; any source-required error prose is reviewed separately from status values.
    - Optional: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d` followed by a greeting through the UI -> a valid user-managed provider setup streams a natural persisted answer with no tool activity; synthetic interrupt behavior remains test-only.
  - Blocked Condition: A required Astryx 0.1.4 component lacks a documented public
    composition that can display exact JobAgent status without polluting client
    state. Report the CLI evidence; do not invent props, aliases, or a substitute
    design system. Missing prerequisites for the optional local smoke do not
    block required task acceptance.
  - Files: `frontend/src/app/App.tsx`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/components/ChatToolActivity.tsx`, `frontend/src/test/chat-page.test.tsx`, `frontend/src/app/theme.css` only for source-required token-based chat layout adjustments
