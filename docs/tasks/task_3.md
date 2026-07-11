# JobAgent Plan 3 Phase 2 Execution Tasks

## Purpose

Execute Master Phase 2 as reviewable units that establish the single persistent
conversation, controlled LangGraph runtime, validated SSE boundary, and base
Astryx chat experience. The phase must reuse Plan 2 infrastructure and stop
before CV/profile, JD, matching, or other later-phase domain implementations.

## Project Context Notes

- Root `README.md` was read. It records Phase 0 complete and Plan 2 Batches
  01-05 evidence-backed, with Plan 3 authorized to reuse the current FastAPI,
  React/TypeScript/Vite, SQLite, filesystem, Neo4j, Compose, and root-settings
  primitives.
- SQLite remains the only canonical application store. Neo4j remains derived,
  and the frontend communicates only with FastAPI.
- Existing Plan 2 models already own `conversation`, `chat_messages`,
  `agent_runs`, and `tool_executions`; LangGraph checkpoint tables remain
  library-owned and short-lived.
- Backend quality commands run from `backend/`: `python -m ruff check app tests`,
  `python -m mypy app`, and `python -m pytest -q`. Frontend commands run from
  `frontend/`: `npm run check:astryx`, `npm run lint`, `npm run typecheck`,
  `npm run test -- --run`, and `npm run build`.
- Current repository evidence places the backend extension points under
  `backend/app/{api,db,repositories,schemas,services}` and the minimal neutral
  frontend shell under `frontend/src/app/`.
- The user-provided root agent rules require search-before-write, reuse, focused
  modules, shortest working diffs, and caller inspection for shared behavior.
  `frontend/AGENTS.md` additionally requires Astryx CLI discovery before UI work,
  Astryx layout components instead of raw layout elements, and documented public
  component APIs only.
- Normal automated tests use fakes and must not call ShopAIKey. Real credentials
  stay only in the ignored root `.env` and must never enter reports, logs, diffs,
  or test fixtures.

## Authority and Scope

### Primary Source

`docs/plans/Plan_3.md` is the user-named primary source. Its objective, scope,
technical specifications, implementation steps, verification plan, and Plan 4
handoff are authoritative for this task document. Referenced sections of
`docs/plans/Master_plan.md`, the completed Plan 2 handoff in `README.md`, and
repository evidence refine execution details without expanding Plan 3 scope.

### Source Section Index

- `docs/plans/Plan_3.md` > `## 1. Objective` -> phase outcome.
- `docs/plans/Plan_3.md` > `## 4. Scope` -> mandatory backend and frontend work.
- `docs/plans/Plan_3.md` > `## 5. Out of Scope` -> later-phase exclusions.
- `docs/plans/Plan_3.md` > `## 6. Target Directory Structure` -> likely ownership and file split.
- `docs/plans/Plan_3.md` > `### 7.1 Persistent conversation and run lifecycle` -> durable ordering, IDs, disconnect, and cleanup.
- `docs/plans/Plan_3.md` > `### 7.2 Agent state` -> bounded state and large-document exclusion.
- `docs/plans/Plan_3.md` > `### 7.3 Graph topology and limits` -> one controlled loop and deterministic failures.
- `docs/plans/Plan_3.md` > `### 7.4 Public chat contracts` -> history, turn, resume, and idempotency boundary.
- `docs/plans/Plan_3.md` > `### 7.5 SSE event contract` -> exact public event union and sanitization.
- `docs/plans/Plan_3.md` > `### 7.6 ShopAIKey adapter and prompt boundary` -> locked adapter mode, retries, and domain policy.
- `docs/plans/Plan_3.md` > `### 7.7 Frontend state` -> pure reducer and conflicting-send behavior.
- `docs/plans/Plan_3.md` > `## 9. Verification & Testing Plan` -> fake/live boundaries and phase exit evidence.
- `docs/plans/Plan_3.md` > `## 10. Handoff Notes for Plan 4 (Master Phase 3)` -> stable seams and prohibited alternate paths.
- `docs/plans/Master_plan.md` > `### 4.1 Ownership rules` -> store, frontend, and tool call boundaries.
- `docs/plans/Master_plan.md` > `## 12. Agent Architecture` -> single Agent, per-turn runs, memory, policy, and loop ceiling.
- `docs/plans/Master_plan.md` > `### 14.2 SSE contract` -> FastAPI-owned public stream.
- `docs/plans/Master_plan.md` > `### 15.3 Chat components` -> required Astryx chat components.
- `docs/plans/Master_plan.md` > `### 15.4 Tool activity display` -> sanitized tool presentation.
- `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` -> `ChatOpenAI`, custom base URL, and verified schema fallback.
- `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` -> bounded retry and controlled failure rules.
- `docs/plans/Master_plan.md` > `### 22.3 Untrusted content` -> document delimiters and authorization source.
- `docs/plans/Master_plan.md` > `### 22.4 Logging` -> allowed observability and prohibited data.
- `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` -> local-only fake-backed validation.
- `docs/plans/Master_plan.md` > `### Phase 2 — Chat transport, Agent runtime, and persistence` -> mandatory tasks and exit gate.

### Approved Architecture and Constraints

- Maintain exactly one application conversation and one `StateGraph` with one
  LLM decision node and one `ToolNode`; do not add multi-agent or alternate chat
  paths.
- Persist the user message before run creation/execution, create one run/thread
  identity per turn, reuse it for resume, and persist assistant history only from
  validated final output.
- Use bounded application context. Never place raw CV/JD bodies in Agent state,
  SSE, tool summaries, or logs.
- FastAPI owns the exact eight-event SSE stream. Provider streaming remains an
  internal adapter capability.
- Enforce at most six tool executions, one structured-output repair, and one
  timeout/rate-limit retry; the LLM never controls retries.
- Reuse Plan 2 settings, async sessions, models, migration chain, application
  lifecycle, CORS policy, and Compose services. Any schema evolution must be the
  minimum additive change required for durable Plan 3 idempotency or run state.
- Register runtime seams for later domain tools but do not implement or expose
  the seven production domain tools in this phase. The transport-proof tool is
  synthetic and test-only.
- Public application routes after this phase are `/api/health` and the three
  chat routes only, plus framework documentation routes.
- Do not add public CRUD, upload, CV/profile/JD behavior, matching, workers,
  Qdrant, CI, cloud deployment, or direct frontend/provider/store access.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Durable chat and SSE contracts | (01A), (01B), (01C) | Plan 2 accepted handoff |
| Batch02 | Controlled Agent runtime and lifecycle | (02A), (02B), (02C), (02D) | Batch01 |
| Batch03 | Public SSE API and base Astryx chat experience | (03A), (03B), (03C) | Batch02 |
| Batch04 | Full transport proof and Plan 4 handoff | (04A) | Batch03 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_3_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_3_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Durable Chat and SSE Contracts

### Goal

Establish repository and public event contracts that later runtime and transport
work can consume without duplicating persistence, ordering, or sanitization logic.

### Dependencies

Plan 2 is accepted and its current migration head, async session manager,
conversation models, root settings, and local quality commands are available.

### Scope Boundary

This batch owns repository behavior, the minimum required additive persistence
change, and typed SSE schemas. It does not create LangGraph execution, provider
calls, HTTP chat routes, or frontend behavior.

### Tasks

- [x] (01A): Implement singleton conversation and bounded message history repositories
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.1 Persistent conversation and run lifecycle`; `docs/plans/Plan_3.md` > `### 7.2 Agent state`; `docs/plans/Master_plan.md` > `### 12.2 Per-turn runs`; `docs/plans/Master_plan.md` > `### 12.4 Memory policy`
  - Source Requirements:
    - Ensure exactly one application conversation through an idempotent repository operation.
    - Persist ordered user/assistant application history and load only a bounded recent window for runtime context.
    - Keep structured payloads repository-validated and never use complete history as the prompt context.
  - Dependencies: Plan 2 accepted `Conversation` and `ChatMessage` models plus `DatabaseSessionManager`
  - User Action: None
  - Agent Work:
    1. Search current models, repositories, session patterns, and all conversation/message callers; reuse the Plan 2 transaction boundary and singleton constant.
    2. Implement focused singleton, append, ordered-history, and bounded-recent-history repository methods with deterministic ordering.
    3. Add repository tests for first/repeated singleton creation, concurrent-safe uniqueness behavior, role/payload validation, ordering, bounds, and rollback on failure.
  - Output: One reusable conversation/message persistence boundary for history and Agent context.
  - Acceptance:
    - Repeated singleton creation returns the same row and cannot create a second conversation.
    - Message reads are stable and ordered; the context method enforces its requested bound without loading unbounded history into the Agent path.
    - Invalid roles or structured payloads fail before durable commit, and failed writes leave no partial message.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/repositories/test_conversations.py` -> singleton, ordering, bounds, validation, and rollback tests pass.
    - Required: `cd backend; python -m ruff check app/repositories/conversations.py tests/repositories/test_conversations.py; python -m mypy app/repositories/conversations.py` -> focused lint and strict typing pass.
  - Blocked Condition: The accepted Plan 2 conversation schema or migration head is absent or materially differs from the repository model contract; restore or reconcile the accepted Plan 2 artifact before execution.
  - Files: `backend/app/repositories/conversations.py`, `backend/app/repositories/__init__.py`, `backend/tests/repositories/test_conversations.py`

- [x] (01B): Implement durable Agent run, request-idempotency, and tool execution repositories
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.1 Persistent conversation and run lifecycle`; `docs/plans/Plan_3.md` > `### 7.4 Public chat contracts`; `docs/plans/Plan_3.md` > `### 7.5 SSE event contract`; `docs/plans/Master_plan.md` > `### 6.1 Application tables`
  - Source Requirements:
    - Create one durable Agent run per persisted user turn and reuse the same run/thread identity for resume.
    - Resolve duplicate turn and resume idempotency keys to the existing run outcome without repeating writes.
    - Persist state transitions, pending approval, sanitized failures, and sanitized tool execution timing/status only.
  - Dependencies: (01A) and the accepted Plan 2 `AgentRun` and `ToolExecution` models
  - User Action: None
  - Agent Work:
    1. Inspect the current models, migration, enum values, repository patterns, and every prospective run/tool caller before selecting the minimum durable idempotency representation.
    2. Extend only existing Plan 2 chat/run persistence through a reviewed additive Alembic revision when required; do not recreate tables or add later-phase domain storage.
    3. Implement transactional run creation/lookup/state transitions and tool start/finish/fail operations that normalize persisted error data and expose stable run identity for the LangGraph thread.
    4. Add migration and repository tests for new/existing databases, duplicate turn/resume keys, same-run resume, invalid transitions, replay, rollback, and secret/raw-argument exclusion.
  - Output: Replay-safe application run and sanitized tool observability repositories.
  - Acceptance:
    - A user message has at most one Agent run, and durable duplicate request keys return that run without a second message, run, resume action, or tool execution.
    - Run transitions reject invalid or stale state changes and retain a resumable interrupted outcome.
    - Tool records contain only approved identifiers, status, timing, short sanitized summaries, and error codes.
    - Any additive migration upgrades both a fresh file and the accepted initialized schema without destructive table recreation.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/repositories/test_agent_runs.py tests/repositories/test_tool_executions.py tests/integration/test_migrations.py` -> idempotency, transitions, sanitization, and migration compatibility pass.
    - Required: `cd backend; python -m ruff check app/db app/repositories tests/repositories tests/integration/test_migrations.py; python -m mypy app/db app/repositories` -> focused schema/repository quality passes.
  - Blocked Condition: The source-required durable duplicate handling cannot be represented safely without a material application-schema redesign beyond additive Plan 3 persistence; stop and request architecture approval rather than using process memory.
  - Files: `backend/app/db/models/conversation.py`, `backend/app/db/enums.py`, `backend/app/repositories/agent_runs.py`, `backend/app/repositories/tool_executions.py`, `backend/migrations/versions/*_plan3_run_idempotency.py`, `backend/tests/repositories/test_agent_runs.py`, `backend/tests/repositories/test_tool_executions.py`, `backend/tests/integration/test_migrations.py`

- [x] (01C): Define the exact validated SSE event union and ordering boundary
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.5 SSE event contract`; `docs/plans/Plan_3.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 14.2 SSE contract`; `docs/plans/Master_plan.md` > `### 15.4 Tool activity display`
  - Source Requirements:
    - Support exactly `run_started`, `assistant_status`, `tool_started`, `tool_completed`, `approval_required`, `text_delta`, `run_completed`, and `run_failed`.
    - Require `event_id`, `run_id`, `timestamp`, and one event-specific validated payload on every event.
    - Expose only friendly tool labels, approved display states, duration, and short sanitized outcomes.
  - Dependencies: (01B) provides stable run and tool terminology
  - User Action: None
  - Agent Work:
    1. Search existing Pydantic schema and sanitization patterns and verify all future backend/frontend consumers of event names.
    2. Implement a discriminated Pydantic union, payload models, deterministic event serialization, and a single ordering/state validation boundary.
    3. Add tests for every valid event, unknown/mismatched payload rejection, required common fields, legal ordering, terminal events, duplicates, and prohibited data leakage.
  - Output: One authoritative backend SSE schema/serialization contract consumable by API and frontend types.
  - Acceptance:
    - The union accepts all and only the eight source-defined event types with typed event-specific payloads.
    - Ordering rejects events before `run_started`, events after a terminal event, and approval/tool/text sequences inconsistent with the declared run state.
    - Serialized events cannot include raw arguments, document bodies, secrets, headers, stack traces, or internal-only IDs in display payloads.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/schemas/test_sse.py` -> union, serialization, ordering, terminal, and leakage tests pass.
    - Required: `cd backend; python -m ruff check app/schemas/sse.py tests/schemas/test_sse.py; python -m mypy app/schemas/sse.py` -> focused schema quality passes.
  - Blocked Condition: None
  - Files: `backend/app/schemas/sse.py`, `backend/app/schemas/__init__.py`, `backend/tests/schemas/test_sse.py`

## Mandatory Batch02 - Controlled Agent Runtime and Lifecycle

### Goal

Build the verified provider boundary, bounded prompt context, single controlled
tool loop, and per-run checkpoint lifecycle behind application-service seams.

### Dependencies

All Batch01 tasks are accepted. Plan 1 provider decisions and Plan 2 settings,
database session lifecycle, and production package installation remain stable.

### Scope Boundary

This batch owns internal Agent execution only. It registers no production domain
tool implementation, exposes no HTTP route, and does not place synthetic tools in
the production registry or application startup path.

### Tasks

- [x] (02A): Implement the production ShopAIKey chat adapter with bounded failures
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.6 ShopAIKey adapter and prompt boundary`; `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Construct `ChatOpenAI` from the typed root base URL/key/model with temperature zero and `bind_tools()`.
    - Reuse the verified `strict_schema` and `streaming_text` decisions without re-benchmarking or silently changing model/schema mode.
    - Allow at most one structured-output repair and one timeout/rate-limit retry, then return a controlled sanitized failure.
  - Dependencies: (01C), Plan 1 locked `langchain-openai==1.0.3` compatibility evidence, and Plan 2 `Settings`
  - User Action: None for required fake-backed validation; do not read the real root `.env` in tests.
  - Agent Work:
    1. Search and reuse the Phase 0 ShopAIKey constructor, binding, schema, streaming, exception-sanitization, and fake patterns rather than duplicating provider logic.
    2. Implement a narrow injectable production adapter for decision calls, tool binding, validated final text streaming, schema repair, and deterministic provider retry classification.
    3. Add socket-blocked/fake tests for configuration, binding, ordered text, repair/retry ceilings, no model switching, cancellation, and secret-safe failures.
  - Output: One testable ShopAIKey chat adapter with the locked compatibility behavior.
  - Acceptance:
    - Production construction uses only typed backend settings, the locked model/base URL, temperature zero, and `bind_tools()`.
    - Schema repair and transient retry each stop at one; other failures are not retried or converted to success.
    - Required tests perform no provider network request and expose no key, Authorization header, raw provider body, or credential-bearing URL.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_shopaikey_chat.py` -> fake/socket-blocked adapter, streaming, repair, retry, and redaction tests pass.
    - Required: `cd backend; python -m ruff check app/services/shopaikey_chat.py tests/services/test_shopaikey_chat.py; python -m mypy app/services/shopaikey_chat.py` -> focused adapter quality passes.
  - Blocked Condition: The installed locked provider package no longer exposes the already-verified constructor, binding, strict-schema, or streaming behavior; report the concrete compatibility conflict without changing versions or modes.
  - Files: `backend/app/services/shopaikey_chat.py`, `backend/tests/services/test_shopaikey_chat.py`, existing Phase 0 diagnostic helpers only when refactoring is required to eliminate duplicated adapter logic

- [x] (02B): Implement bounded Agent state, context assembly, and domain prompt policy
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.2 Agent state`; `docs/plans/Plan_3.md` > `### 7.6 ShopAIKey adapter and prompt boundary`; `docs/plans/Master_plan.md` > `### 12.3 Agent state`; `docs/plans/Master_plan.md` > `### 12.4 Memory policy`; `docs/plans/Master_plan.md` > `### 12.5 Domain policy`; `docs/plans/Master_plan.md` > `### 22.3 Untrusted content`
  - Source Requirements:
    - Define the exact Plan 3 state fields and keep large document bodies out of state.
    - Assemble approved profile/preferences when available, relevant memory facts, current turn, and a bounded recent window.
    - Delimit CV/JD text as untrusted data and redirect unrelated messages with the master-defined brief response and zero tool calls.
  - Dependencies: (01A), (01B), and (02A)
  - User Action: None
  - Agent Work:
    1. Search existing models/repositories and inspect every context caller; reuse structured records and message bounds instead of creating alternate memory storage.
    2. Implement focused Agent state typing, context assembly, prompt construction, document delimiters, and the domain redirect policy without a classifier model.
    3. Add tests for exact state keys, bounded context, missing optional context, current-turn inclusion, ID-only large-content references, malicious embedded instructions, and unrelated-message zero-tool behavior.
  - Output: Deterministic bounded Agent inputs and one domain/system prompt boundary.
  - Acceptance:
    - State contains the source-defined fields and no raw PDF/JD body field or unbounded history.
    - Prompt construction marks embedded document instructions untrusted and cannot grant tool authorization from document text.
    - Unrelated input returns exactly the approved brief redirect through policy behavior and invokes no tool/provider retry loop.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/agent/test_state.py tests/agent/test_prompt.py tests/services/test_context_assembly.py` -> state, bounds, delimiter, injection, and redirect tests pass.
    - Required: `cd backend; python -m ruff check app/agent app/services/chat_context.py tests/agent tests/services/test_context_assembly.py; python -m mypy app/agent app/services/chat_context.py` -> focused Agent context quality passes.
  - Blocked Condition: Approved profile/preferences or memory repositories are not yet implemented; treat them as absent optional context through existing Plan 2 models, and block only if doing so prevents the current-turn/bounded-history contract.
  - Files: `backend/app/agent/state.py`, `backend/app/agent/prompt.py`, `backend/app/services/chat_context.py`, `backend/tests/agent/test_state.py`, `backend/tests/agent/test_prompt.py`, `backend/tests/services/test_context_assembly.py`

- [x] (02C): Build the single ToolNode graph, registry seam, loop guard, and error boundary
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.3 Graph topology and limits`; `docs/plans/Plan_3.md` > `## 4. Scope`; `docs/plans/Plan_3.md` > `## 5. Out of Scope`; `docs/plans/Master_plan.md` > `### 12.1 One Agent, one controlled loop`; `docs/plans/Master_plan.md` > `### 12.6 Tool loop limits`
  - Source Requirements:
    - Build one `StateGraph` with the specified context, decision, `ToolNode`, iteration, persistence, cleanup, and end topology.
    - Stop before a seventh tool execution with `TOOL_LOOP_LIMIT_EXCEEDED`; never let the LLM own retries or turn structured failure into success.
    - Provide only the registration/runtime seam for later domain tools and use synthetic tools in tests only.
  - Dependencies: (01B), (02A), and (02B)
  - User Action: None
  - Agent Work:
    1. Search installed dependency declarations and existing graph/service patterns; promote the locked `langgraph==1.2.9` into the production dependency set and add only the directly compatible SQLite checkpointer package required by (02D), with exact versions recorded.
    2. Implement a focused tool registry contract, graph builder, decision/tool routing, explicit iteration increment/guard, and normalized error boundary using injected adapters/services.
    3. Add fake-model and synthetic-tool tests for no-tool completion, one/multiple tools, exactly six executions, pre-seventh failure, structured tool failure, registry isolation, and absence of production domain tools.
  - Output: One reusable controlled Agent graph and empty-by-default production tool registry seam.
  - Acceptance:
    - Repository inspection finds one `StateGraph`, one decision node, and one `ToolNode` path with no multi-agent/handoff implementation.
    - Six tool executions are allowed and the seventh is prevented with the exact controlled code; failed tools cannot produce a successful run outcome.
    - Synthetic tools exist only in test fixtures/injection, and production contains no implementation of the seven later-phase tools.
    - Production image/package installation includes the runtime graph and SQLite checkpoint dependencies.
  - Validation:
    - Required: `cd backend; python -m pip install -e ".[test]"; python -m pip check` -> production and test dependency sets resolve.
    - Required: `cd backend; python -m pytest -q tests/agent/test_graph.py tests/tools/test_registry.py` -> topology, loop, failure, and registry isolation tests pass.
    - Required: `cd backend; python -m ruff check app/agent app/tools tests/agent tests/tools; python -m mypy app/agent app/tools` -> focused graph/registry quality passes.
    - Required: `rg -n "def (get_candidate_context|propose_profile_from_cv|propose_profile_update|commit_profile_draft|save_job|query_jobs|match_jobs)" backend/app` -> no production domain tool implementation is found.
  - Blocked Condition: No SQLite checkpointer release is compatible with locked `langgraph==1.2.9` and Python 3.13; report the dependency resolution evidence rather than changing the locked LangGraph version.
  - Files: `backend/pyproject.toml`, `backend/app/agent/graph.py`, `backend/app/tools/registry.py`, `backend/tests/agent/test_graph.py`, `backend/tests/tools/test_registry.py`, `backend/tests/fakes/agent_tools.py`

- [x] (02D): Implement per-run checkpoint, interrupt/resume, persistence, and cleanup lifecycle
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.1 Persistent conversation and run lifecycle`; `docs/plans/Plan_3.md` > `### 7.3 Graph topology and limits`; `docs/plans/Plan_3.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 12.2 Per-turn runs`
  - Source Requirements:
    - Create one `AsyncSqliteSaver` lifecycle per run/thread, resume an interrupt through the same identity across requests, and remove completed checkpoint rows.
    - Persist the final validated assistant message before checkpoint cleanup while retaining application run outcome and sanitized tool records.
    - On disconnect, advance only to a safe persisted state; reconnect relies on durable history/run state and never replays writes.
  - Dependencies: (01A), (01B), (01C), and (02C)
  - User Action: None
  - Agent Work:
    1. Inspect the database manager, application transaction owners, installed checkpointer API, and every graph caller; keep library checkpoint tables separate from application models/migrations.
    2. Implement the chat execution service and checkpoint owner for new run, interrupt, validated resume command, final persistence, failure, disconnect/cancellation, and completed cleanup ordering.
    3. Add integration tests using a temporary migrated SQLite file and injected graph/provider for request-boundary resume, same thread ID, idempotent resume, final-message-before-cleanup, failed/interrupted retention, completed cleanup, and disconnect recovery.
  - Output: Durable per-turn Agent execution lifecycle with short-lived checkpoints.
  - Acceptance:
    - A resumed interrupt uses the original application run and LangGraph thread identity after the first request has ended.
    - A completed run has one validated assistant message and no remaining checkpoint rows; application messages, outcome, and sanitized tool records remain.
    - Interrupted/failed/disconnected runs retain enough safe durable state to inspect or resume without duplicate application writes.
    - No application migration or ORM model owns LangGraph checkpoint tables.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/integration/test_agent_lifecycle.py` -> new run, interrupt/resume, idempotency, ordering, cleanup, failure, and disconnect cases pass on temporary SQLite.
    - Required: `cd backend; python -m ruff check app/agent/lifecycle.py app/services/chat_service.py tests/integration/test_agent_lifecycle.py; python -m mypy app/agent/lifecycle.py app/services/chat_service.py` -> focused lifecycle quality passes.
  - Blocked Condition: The compatible `AsyncSqliteSaver` API cannot share the configured SQLite database safely or cannot delete one completed thread without affecting other runs; stop with reproducible evidence rather than global checkpoint deletion.
  - Files: `backend/app/agent/lifecycle.py`, `backend/app/services/chat_service.py`, `backend/tests/integration/test_agent_lifecycle.py`

## Mandatory Batch03 - Public SSE API and Base Astryx Chat Experience

### Goal

Expose the durable Agent lifecycle through the three public chat routes and
consume the exact stream through a pure frontend reducer and usable Astryx shell.

### Dependencies

All Batch01 and Batch02 tasks are accepted. The existing health route, exact
CORS middleware, frontend environment contract, and neutral Astryx theme remain
the shared application foundation.

### Scope Boundary

This batch owns the chat API, SSE client state, and base chat presentation only.
It does not add upload/profile/sidebar domain behavior, job cards, matching, or
direct frontend access to backend stores/providers.

### Tasks

- [x] (03A): Expose history, turn, and same-run resume through validated SSE
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.4 Public chat contracts`; `docs/plans/Plan_3.md` > `### 7.5 SSE event contract`; `docs/plans/Plan_3.md` > `### 7.1 Persistent conversation and run lifecycle`; `docs/plans/Master_plan.md` > `## 14. Public FastAPI Boundary` > `### 14.1 API rules`
  - Source Requirements:
    - Implement only `GET /api/chat/history`, `POST /api/chat/turns`, and `POST /api/chat/runs/{run_id}/resume`; both POST routes return SSE.
    - Validate user text, bounded attachment IDs, approval/correction commands, and idempotency keys before writes.
    - Persist the user message first, stream only validated ordered events, and return existing run outcomes for duplicate keys without repeated writes.
  - Dependencies: (01C) and (02D)
  - User Action: None
  - Agent Work:
    1. Search current route/lifespan/CORS injection patterns and all chat service callers; keep the API layer limited to validation, dependency lookup, and streaming orchestration.
    2. Define request/history response schemas and implement the three routes against the existing repositories and chat service, including terminal replay for duplicates and safe disconnect handling.
    3. Register the router and update exact CORS methods without weakening origin matching or exposing any extra application endpoint.
    4. Add API/integration tests for hydration, bounds, validation-before-write, ordered SSE, duplicate turn/resume keys, same-run resume, terminal failures, disconnects, CORS, route inventory, and leakage.
  - Output: The complete public Plan 3 FastAPI chat boundary.
  - Acceptance:
    - OpenAPI exposes `/api/health` and exactly the three Plan 3 chat paths, with no public attachment/profile/job CRUD or synthetic-tool route.
    - Both POST responses use SSE and every decoded event validates through (01C) in legal order with one terminal outcome.
    - Invalid input writes nothing; duplicate idempotency keys produce no duplicate message, run, resume, tool call, or assistant result.
    - Responses/logs exclude raw tool arguments, document content, secrets, headers, stack traces, unsafe internal IDs, and provider exception text.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/api/test_chat.py tests/integration/test_chat_transport.py tests/test_lifecycle.py` -> route, SSE, idempotency, resume, disconnect, CORS, and leakage tests pass.
    - Required: `cd backend; python -m ruff check app/api/chat.py app/schemas/chat.py app/main.py tests/api/test_chat.py tests/integration/test_chat_transport.py; python -m mypy app/api/chat.py app/schemas/chat.py app/main.py` -> focused API quality passes.
    - Required: `rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api` -> only health and the three approved chat route declarations are found.
  - Blocked Condition: A required chat service dependency from Batch02 is not accepted or cannot be injected through the current FastAPI lifecycle without loading real settings/provider calls during import.
  - Files: `backend/app/api/chat.py`, `backend/app/schemas/chat.py`, `backend/app/main.py`, `backend/tests/api/test_chat.py`, `backend/tests/integration/test_chat_transport.py`, `backend/tests/test_lifecycle.py`

- [x] (03B): Implement the typed frontend SSE client, pure reducer, and history hydration
  - Source of Truth: `docs/plans/Plan_3.md` > `### 7.5 SSE event contract`; `docs/plans/Plan_3.md` > `### 7.7 Frontend state`; `docs/plans/Plan_3.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 14.2 SSE contract`
  - Source Requirements:
    - Parse the exact backend event union and reduce state purely by `run_id` and `event_id`.
    - Ignore duplicate events, preserve order, render partial assistant text, surface failures, and hydrate durable history.
    - Track approval/disconnect/terminal state so conflicting sends can be disabled by the UI.
  - Dependencies: (01C) and (03A)
  - User Action: None
  - Agent Work:
    1. Search current frontend API/env/test patterns and reuse the exact `VITE_API_BASE_URL` accessor; do not add a second config source or external SSE dependency unless already installed and necessary.
    2. Implement typed chat contracts, streaming fetch parser, history/turn/resume client calls, and a pure reducer with explicit run/event deduplication and ordering.
    3. Add tests for fragmented SSE frames, multiline data if supported by the contract, every event type, duplicates, out-of-order/foreign-run events, partial text, approval, terminal failure, disconnect, reconnect hydration, and abort cleanup.
  - Output: One typed frontend transport/state boundary independent of presentation components.
  - Acceptance:
    - The client calls only the three approved FastAPI chat paths through the existing public base URL.
    - Reducer transitions are pure and deterministic; replaying the same event ID has no effect, while ordered deltas produce exactly one assistant text stream.
    - Approval, active, failed, completed, and disconnected states are distinguishable and expose a reliable send-disabled decision.
  - Validation:
    - Required: `cd frontend; npm run test -- --run src/features/chat/reducer.test.ts src/lib/sse/parser.test.ts src/features/chat/api.test.ts` -> parser, reducer, API, hydration, duplicate, and disconnect tests pass.
    - Required: `cd frontend; npm run lint; npm run typecheck` -> frontend transport code passes lint and strict TypeScript checks.
  - Blocked Condition: The accepted backend SSE schema differs from the exact Plan 3 eight-event contract; reconcile (01C)/(03A) before implementing a divergent frontend parser.
  - Files: `frontend/src/features/chat/contracts.ts`, `frontend/src/features/chat/api.ts`, `frontend/src/features/chat/reducer.ts`, `frontend/src/features/chat/api.test.ts`, `frontend/src/features/chat/reducer.test.ts`, `frontend/src/lib/sse/parser.ts`, `frontend/src/lib/sse/parser.test.ts`

- [x] (03C): Build the base Astryx chat shell and sanitized tool activity UI
  - Source of Truth: `docs/plans/Plan_3.md` > `## 4. Scope`; `docs/plans/Plan_3.md` > `### 7.7 Frontend state`; `docs/plans/Master_plan.md` > `### 15.1 Layout`; `docs/plans/Master_plan.md` > `### 15.3 Chat components`; `docs/plans/Master_plan.md` > `### 15.4 Tool activity display`
  - Source Requirements:
    - Replace the placeholder with the base responsive Astryx `AppShell`/`ChatLayout`, message list, composer, system/failure states, and `ChatToolCalls` rendering.
    - Hydrate history, render partial assistant text, submit turns/resumes, and disable conflicting sends while active or awaiting approval.
    - Display only friendly tool label, `pending|running|complete|error`, duration, and short sanitized outcome.
  - Dependencies: (03B) and the pinned Astryx neutral theme
  - User Action: None
  - Agent Work:
    1. Run `npx astryx build "persistent AI chat with tool activity and approval"`, then inspect the documented templates and `ChatLayout`, `ChatMessageList`, `ChatMessage`, `ChatComposer`, `ChatToolCalls`, `ChatSystemMessage`, `ButtonGroup`, `Button`, `Banner`, and `Toast` APIs before editing UI.
    2. Split the placeholder shell into focused chat presentation/container components that consume (03B), use Astryx layout/tokens, and avoid undocumented props, raw layout elements, nested cards, or later-phase sidebar/profile/job UI.
    3. Implement loading, empty history, partial response, active tool, approval/resume, failure, disconnect, completed, and composer-disabled states with accessible controls.
    4. Add component/integration tests for hydration, submit, partial text, sanitized tool mapping, approval action/idempotent disable, failure/disconnect recovery, and absence of prohibited values.
  - Output: A usable responsive Plan 3 chat experience backed by the real frontend state boundary.
  - Acceptance:
    - The first screen is the chat experience, not a landing page or feature description, and it uses only documented pinned Astryx APIs.
    - Message/composer/tool/approval states remain legible and non-overlapping at desktop and mobile widths; controls do not resize from dynamic status text.
    - The UI never renders raw arguments, document content, secrets, headers, stack traces, or internal-only IDs.
    - No upload/profile/job/match feature or direct provider/store request is added.
  - Validation:
    - Required: `cd frontend; npm run check:astryx; npm run test -- --run src/features/chat/components src/test/app.chat.test.tsx` -> Astryx compatibility and chat component/state tests pass.
    - Required: `cd frontend; npm run lint; npm run typecheck; npm run build` -> full frontend quality and production build pass.
    - Required: `cd frontend; npm run dev`, then inspect `http://127.0.0.1:5173` at 1440x900 and 390x844 using deterministic test states -> chat layout, partial text, tool rows, approval controls, failures, and composer show no overlap, clipping, or prohibited content.
  - Blocked Condition: A source-required Astryx component or public prop is absent from pinned `0.1.4`; record the CLI evidence and use the closest documented Astryx composition without upgrading or swizzling unless separately approved.
  - Files: `frontend/src/app/App.tsx`, `frontend/src/features/chat/components/ChatShell.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/components/ChatComposerPanel.tsx`, `frontend/src/features/chat/components/ChatToolActivity.tsx`, `frontend/src/features/chat/components/ChatApproval.tsx`, `frontend/src/features/chat/components/*.test.tsx`, `frontend/src/test/app.chat.test.tsx`

## Mandatory Batch04 - Full Transport Proof and Plan 4 Handoff

### Goal

Prove the complete local frontend-to-Agent transport, remove all production
synthetic exposure, run phase-wide quality gates, and publish the stable Plan 4
handoff without implementing Plan 4 behavior.

### Dependencies

Every Batch01-Batch03 task is accepted.

### Scope Boundary

This batch may repair only Plan 3-owned defects exposed by exit validation and
update root documentation/report evidence. It must not add domain tools,
uploads, profile approval payloads, JD workflows, matching, or new architecture.

### Tasks

- [ ] (04A): Prove the synthetic tool and interrupt path end to end, then publish the Plan 4 handoff
  - Source of Truth: `docs/plans/Plan_3.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_3.md` > `## 10. Handoff Notes for Plan 4 (Master Phase 3)`; `docs/plans/Master_plan.md` > `### Phase 2 — Chat transport, Agent runtime, and persistence`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy`
  - Source Requirements:
    - Prove one synthetic tool across frontend, FastAPI, LangGraph, `ToolNode`, validated SSE, and frontend state/presentation.
    - Prove interrupt/resume across separate requests, duplicate-key no-replay, unrelated-message redirect with zero tools, and completed-checkpoint cleanup with durable history retained.
    - Remove any production exposure of the synthetic tool and hand Plan 4 the stable endpoints, event union, reducer/shell, graph, approval/idempotency, repository, context, and prompt seams.
  - Dependencies: (03A), (03B), (03C), and every earlier Plan 3 task
  - User Action: None for required fake-backed/local proof. A populated ignored root `.env` is needed only for optional live Compose/provider observation and must not be disclosed.
  - Agent Work:
    1. Add one deterministic test-only full-path fixture/harness that drives the real frontend client/reducer and backend API/graph/runtime with injected fake provider and synthetic tool, without real ShopAIKey calls.
    2. Exercise ordinary completion, tool activity, approval interrupt/resume in a second request, duplicate turn/resume keys, disconnect/reconnect, controlled failure, unrelated redirect, history retention, and checkpoint cleanup; repair only Plan 3-owned defects.
    3. Scan production code, routes, registry, build output, logs, SSE, and UI for synthetic-tool exposure, later-phase behavior, raw/private data, credentials, headers, internal IDs, and stack traces.
    4. Run full backend/frontend and Compose static gates, then update root `README.md` with evidence-backed Phase 2 commands, public chat surface, limitations, and the exact Plan 4 stable handoff.
  - Output: Green local Phase 2 transport evidence, no production synthetic tool, and a current Plan 4 handoff.
  - Acceptance:
    - The test-only synthetic path traverses all required layers and produces validated ordered UI-visible status/text without bypassing FastAPI, LangGraph, SSE, or the reducer.
    - Interrupt/resume survives the request boundary on the same run; duplicate keys repeat no write/tool action; unrelated messages execute zero tools.
    - Completed checkpoint rows are absent while conversation messages, run outcome, and sanitized tool records remain.
    - Production route/registry/build scans contain no synthetic tool, later-phase domain tool implementation, extra public route, or prohibited data.
    - README accurately records the Phase 2 runtime, commands, limitations, and Plan 4 seams without claiming CV/profile/JD/matching completion.
  - Validation:
    - Required: `cd backend; python -m ruff check app tests; python -m mypy app; python -m pytest -q` -> full backend suite passes without ShopAIKey network calls.
    - Required: `cd frontend; npm ci --ignore-scripts; npm run check:astryx; npm run lint; npm run typecheck; npm run test -- --run; npm run build` -> full frontend suite and build pass.
    - Required: `cd backend; python -m pytest -q tests/integration/test_full_chat_transport.py` -> tool, SSE, request-boundary resume, duplicate, redirect, history, and cleanup evidence passes.
    - Required: `cd frontend; npm run test -- --run src/test/chat-transport.integration.test.tsx` -> the exact SSE sequence reaches the reducer and UI with correct tool, text, approval, terminal, and duplicate behavior.
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml config; docker compose --env-file .env.example -f infrastructure/docker-compose.yml build` -> three-service configuration and production images include Plan 3 runtime without requiring live secrets.
    - Required: `rg -n "synthetic|echo_label|propose_profile_from_cv|commit_profile_draft|save_job|match_jobs" backend/app frontend/src; rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api; git diff --check` -> no production synthetic/domain implementation, only approved routes, and no whitespace errors.
    - Optional: start Compose with the populated ignored root `.env` and exercise one ordinary chat turn -> local services stream through the production adapter when user-owned credentials and provider access are available.
  - Blocked Condition: A required fake-backed/local exit gate fails after Plan 3-owned repair, or static Compose build cannot install the accepted runtime dependencies. Missing live credentials block only the optional observation, not required acceptance.
  - Files: `backend/tests/integration/test_full_chat_transport.py`, `frontend/src/test/chat-transport.integration.test.tsx`, focused Plan 3-owned code/tests when validation exposes a defect, `README.md`

## Optional Future Tracks

No optional implementation track is authorized by Plan 3. Everything in
`docs/plans/Plan_3.md` section 5 and all CV/profile, JD, matching, evaluation,
hardening, worker, CI, cloud, multi-conversation, or multi-agent work remains
outside the mandatory Phase 2 batch chain.
