# JobAgent Plan 12 Execution Tasks

## Purpose

Translate `docs/plans/Plan_12.md` into the mandatory implementation and evidence
chain for readable assistant responses, truthful active-CV provenance, and
pre-mutation confirmation of passively pasted English/Vietnamese JDs. Preserve
the accepted Plan 11 desktop baseline, existing durable ownership, direct
URL/text save and explicit evaluation paths, and the one-Agent architecture.

## Project Context Notes

- Root `README.md` was read completely before derivation. It defines JobAgent as a
  local single-user React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, and ShopAIKey
  application with one ignored root `.env`, exactly three Compose services,
  fake-backed automated tests, and desktop development at `localhost:5173`.
- The README reports Plan 11 Batch01 and Batch02 complete on product HEAD
  `04fa5f8`. Execution still requires the Orchestrator to verify matching
  immutable A1/A2/A3 evidence and acceptance events rather than inferring
  acceptance from README prose or task checkboxes.
- The current user explicitly invoked `task-writing-agent` for `Plan_12.md`.
  That instruction authorizes this task-file derivation and supersedes only the
  plan's planning-phase instruction to wait for another portfolio review; it
  does not authorize product implementation, change approved scope, or claim
  portfolio acceptance.
- `docs/plans/Plan_12.md` is the primary authority. Master Version 1.9 and the
  user-approved pasted-JD design are aligned supporting authority. The shared
  structure validator passed on 2026-07-18 with contiguous `Plan_1.md` through
  `Plan_12.md`, `valid: true`, and no errors.
- Existing backend owners were confirmed at `backend/app/agent/prompt.py`,
  `backend/app/agent/graph.py`, `backend/app/schemas/jobs.py`,
  `backend/app/tools/jobs.py`, `backend/app/services/tool_execution.py`,
  `backend/app/repositories/agent_runs.py`, and
  `backend/app/repositories/chat_messages.py`. The new focused
  `backend/app/services/job_save_confirmation.py` owner and its unit test do not
  yet exist.
- Existing frontend owners were confirmed at
  `frontend/src/features/chat/history.ts`,
  `frontend/src/features/chat/components/ChatMessageRow.tsx`,
  `frontend/src/features/chat/components/ChatMessages.tsx`,
  `frontend/src/features/chat/components/ChatToolActivity.tsx`,
  `frontend/src/features/chat/ChatPage.tsx`, and
  `frontend/src/features/observability/api.ts`. The planned focused Markdown,
  evidence, dialog, and JD-confirmation modules/tests do not yet exist.
- `frontend/AGENTS.md` applies to every frontend task: inspect the pinned Astryx
  0.1.4 kit and component documentation before implementation, compose public
  components instead of guessed props or hand-built layout primitives, use
  component props/tokens for styling, and avoid unrelated layout work.
- The worktree already contains the user's modified
  `docs/plans/Master_plan.md` and `docs/plans/Plan_11.md`, plus untracked
  `docs/plans/Plan_12.md` and
  `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md`.
  Preserve them. This authoring pass creates only `docs/tasks/task_12.md`.
- Automated tests use fakes and synthetic fixtures; they must not call a live
  provider. Only the final desktop task may use configured local services and
  synthetic/public test inputs. Never place `.env` values, raw CV/JD bodies,
  prompts, provider transcripts, storage paths, database contents, or personal
  screenshots in evidence.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_12.md`.
- Supporting:
  `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md`,
  `docs/plans/Master_plan.md` Version 1.9, `docs/plans/Plan_5.md`,
  `docs/plans/Plan_9.md`, `docs/plans/Plan_11.md`, and
  `frontend/package.json`.
- Context only: `README.md`, `frontend/AGENTS.md`,
  `docs/tasks/task_11.md`, existing implementation/tests, and
  `infrastructure/docker-compose.yml`.

### Source Section Index

- `Plan_12.md` > `## Objective`, `## Master Requirement Coverage`,
  `## Prerequisites`, `## Scope`, and `## Out of Scope` -> mandatory
  P12-RSP, P12-CV, P12-JD, and P12-REG outcomes, prerequisites, and exclusions.
- `Plan_12.md` > `### Response Policy And Active-CV Tool Use` -> direct-answer
  response policy, bounded grouping, active-CV body-evidence rules, passive-JD
  tool policy, direct-path compatibility, and no automatic evaluation.
- `Plan_12.md` > `### Passive-JD Recognition And One Bounded Repair` -> fixed
  normalization, thresholds, markers, opt-out precedence, exact-name precedence,
  sole-URL exclusion, one repair, truthful refusal, and required `ponytail:`
  limitation.
- `Plan_12.md` > `### Current-Message Source And Save-Tool Contract` and
  `### Pre-Mutation Interrupt, Save, Cancel, And Replay` -> strict input union,
  durable initiating-message ownership, redacted pending projection,
  pre-side-effect interrupt, same-execution resume, cancellation, replay, and
  direct-ingestion compatibility.
- `Plan_12.md` > `### Assistant-Only Astryx Markdown` -> assistant-only compact
  Markdown rendering and literal user/system behavior.
- `Plan_12.md` > `### Strict Active-CV Evidence Projection`,
  `### Evidence Binding And Citation Placement`, and `### Source Dialog` ->
  durable evidence allowlists, same-row binding, exact-one citation, exact
  record-order dialog, partial disclosure, retained-PDF action, and no hidden
  fetch.
- `Plan_12.md` > `### Strict JD Confirmation Projection And Card` -> strict
  pending projection, exact two-action card, shared resume/locking/recovery,
  presentation-only Review JD label, committed-only invalidation, and
  cancellation gating.
- `Plan_12.md` > `### Ownership And Invariants` -> exclusive backend/frontend
  owners, durable truth boundaries, file-size constraint, and architecture
  invariants.
- `Plan_12.md` > `## Implementation`, `## Verification`, and
  `## Completion Contract` -> test-first execution order, focused/full gates,
  desktop-only procedures, evidence hygiene, and binary completion conditions.
- `2026-07-18-pasted-jd-save-confirmation-design.md` > `## Recognition Boundary`,
  `## Tool And Interrupt Contract`, `## Frontend Contract`,
  `## Error And Recovery Behavior`, and `## Testing` -> approved confirmation
  semantics and non-goals.
- `Master_plan.md` > `### 6.4 Transaction boundaries`,
  `### 7.5 Tool execution result`, `### 11.2 Pasted-text confirmation boundary`,
  `### 12.1 One Agent, one controlled loop` through
  `### 12.6 Tool loop limits`, heading `### 13.4 \`save_job\``,
  heading `### 13.7 \`read_active_cv\``, `### 14.2 SSE contract`,
  `### 15.3 Chat components` through
  `### 15.7 Readable Agent responses and pasted-JD confirmation`,
  `## 20. Failure and Recovery Policy`, and `## 24. Local Testing Strategy` ->
  synchronized architecture, ownership, failure, and validation authority.

### Approved Architecture and Constraints

- Keep one React/Astryx frontend, one FastAPI application, one LangGraph Agent,
  one decision node, one ToolNode, exactly seven registered tools, and
  `TOOL_LOOP_LIMIT=6`.
- Keep SQLite as the durable source of truth, Neo4j as a derived index,
  `tool_executions.result_json` as the sole durable evidence owner, and
  `chat_messages.content` as the sole durable assistant-text owner.
- Keep the current public endpoints, SSE event envelope, database schema,
  migrations, dependencies, provider/model, active-CV reader/cursor contract,
  ingestion/evaluation owners, and direct URL/text save behavior unchanged.
- Passive current-message save confirmation must interrupt before Job,
  extraction, embedding, evaluation, or graph side effects; save and cancel
  resume the same durable execution, and confirmed save never evaluates
  automatically.
- Assistant content alone uses pinned Astryx Markdown. User/system text and
  existing tool, profile, saved-job, zero-result, and match cards remain literal
  and behaviorally unchanged.
- Active-CV provenance is derived only from successful durable
  `read_active_cv` ToolResults belonging to the same row. The UI shows exactly
  what the Agent read, performs no evidence fetch, and shows no citation for
  invalid, empty, failed, unrelated, or revision-conflicting evidence.
- New parsing, projection, and presentation logic belongs in the focused owners
  named by Plan 12. Do not grow `ChatPage.tsx`, `ChatMessageRow.tsx`,
  `backend/app/tools/jobs.py`, or `backend/app/agent/graph.py` with reusable
  logic that belongs in those modules.
- Security work, mobile/narrow-layout work or evidence, migrations, endpoints,
  dependency changes, new stores/reducers, classifiers, tools, Agents, nodes,
  evaluation behavior, and unrelated redesign remain out of scope.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Backend current-message confirmation plus Agent policy/recognition | (01A), (01B), (01C) | Accepted Plan 11 baseline |
| Batch02 | Strict durable active-CV evidence projection and row selector | (02A) | Batch01 and accepted Plan 9 reader contract |
| Batch03 | Assistant Markdown, exact-one citation, and exact-evidence dialog | (03A) | Batch02 |
| Batch04 | Strict restart-safe pasted-JD confirmation card and shared resume flow | (04A) | Batch01 and Batch03 |
| Batch05 | Full automated gates and desktop-only acceptance evidence | (05A) | Batch01 through Batch04 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md`
  report.
- A2 reviews one executed task, writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a2/<batch-id>/<task-id>/A2-a<attempt>.md`
  report, and the Orchestrator checks the canonical checkbox only after
  `ACCEPTED`.
- A3 runs only after every task in the selected batch has matching A1 evidence,
  A2 evidence, an Orchestrator `ACCEPTED` event, and a checked canonical task
  marker; it writes only
  `.agent/<plan-id>/<run-id>/report/a3/<batch-id>/A3-a<attempt>.md`.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Backend Agent Policy and Pasted-JD Confirmation

### Goal

Add the strict durable current-message save contract first, then compose the
conclusion-first/active-CV response policy and bounded passive-JD recognition
into the existing decision node without changing topology or direct save paths.

### Dependencies

- Plan 11 has matching accepted A1/A2 evidence, Orchestrator decisions, checked
  canonical markers, and accepted Batch02 scope evidence.
- Existing `agent_runs.get_run`, `chat_messages.get_by_id`,
  `execute_tool(..., allow_running_reentry=True)`,
  `commit_profile_draft` interrupt/resume, direct `save_job` ingestion, and
  terminal replay contracts remain green.
- Task (01B) consumes the schema/service foundation from (01A). Task (01C)
  begins only after (01B) is accepted because it emits and narrates the
  production `source='current_message'` invocation.

### Scope Boundary

Own only the new strict job-confirmation service, the existing Job schema/tool,
the existing prompt/decision postconditions, and directly required backend tests.
Exclude repositories, runner/checkpoint internals, API/SSE envelope, ingestion,
evaluation, active-CV reader, graph/database schema, migrations, dependencies,
provider/model, tool registry/count, Agent state/topology, and loop-limit changes.

### Tasks

- [x] (01A): Establish strict JD confirmation schemas and service boundaries
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_12.md` > `## Mandatory Batch01 - Backend Agent Policy and Pasted-JD Confirmation` > `(01A)`
  - Source of Truth: `docs/plans/Plan_12.md` > `### Passive-JD Recognition And One Bounded Repair`, `### Current-Message Source And Save-Tool Contract`, and `### Ownership And Invariants`; `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Recognition Boundary` and `## Tool And Interrupt Contract`; `docs/plans/Master_plan.md` > heading `### 13.4 \`save_job\`` and `### 6.4 Transaction boundaries`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_12.md` > `(01A)` -> task authority
    - source-recognition-boundary: repository `docs/plans/Plan_12.md` > `### Passive-JD Recognition And One Bounded Repair` -> exact pure predicate and opt-out authority
    - source-current-message: repository `docs/plans/Plan_12.md` > `### Current-Message Source And Save-Tool Contract` -> strict input, source, and redaction authority
    - approved-service-design: repository `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Recognition Boundary` and `## Tool And Interrupt Contract` -> approved pure recognition/source/projection vocabulary
    - source-repositories: repository `backend/app/repositories/agent_runs.py` > `get_run` and `backend/app/repositories/chat_messages.py` > `get_by_id` -> durable initiating-message lookup owners
    - schema-owner: repository `backend/app/schemas/jobs.py` > `SaveJobInput` and `SaveJobResultData` -> existing strict Job input/result vocabulary
    - validation-confirmation-unit: repository `docs/plans/Plan_12.md` > `## Verification` > `Prompt, recognition, topology` -> source/recognition boundary evidence
  - Source Requirements:
    - Extend strict `SaveJobInput` to exactly one of public URL, explicit non-empty text, or `source='current_message'`; allow bounded preview only for current-message mode and keep cancellation separate from `created | returned | retried`.
    - Resolve `run_id -> agent_runs.user_message_id -> chat_messages` in one short read transaction, require the main-conversation non-empty user message, and return stable safe lookup/ownership failures before side effects.
    - Own pure Unicode-aware normalization, clear opt-out, sole-URL, and exact source-defined obvious-JD predicates in the new focused service. Preserve marker diversity/thresholds and include the required `ponytail:` limitation and upgrade path.
    - Build only the strict bounded pending projection and successful cancellation ToolResult/model; no provider, tool, interrupt, ingestion, evaluation, graph, or frontend dependency belongs in this service.
    - Pending/source helpers expose no raw JD, message ID, URL, hash, arguments, prompt, provider, credential, storage, or stack data. Preview remains presentation-only and never becomes a canonical Job fact.
  - Dependencies: Accepted Plan 11 baseline; no earlier Plan 12 task.
  - User Action: None; automated validation uses fake providers, temporary data, and existing synthetic fixtures.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/schemas/jobs.py`, `backend/app/services/job_save_confirmation.py`, `backend/tests/unit/test_job_save_confirmation.py`
  - Allowed Files: the three listed schema/service/unit-test files only; repositories/models/session owners are read-only refs. Exclude Job tools, `backend/app/services/tool_execution.py`, profile tools, Agent prompt/graph/state/runner, API/SSE, ingestion/extraction/evaluation/graph owners, settings, migrations, runtime data, dependencies, and frontend.
  - Agent Work:
    1. Trace every `SaveJobInput`/result consumer, existing repository lookup, direct save caller, and pending projection contract before editing; reuse repositories rather than wrapping or modifying them.
    2. Add failing tests for the three-way union, preview bounds/extras/blanks, cancellation-model separation, every recognition threshold/marker/opt-out/sole-URL boundary, durable source role/conversation/content failures, and forbidden projection data.
    3. Implement the strict models and focused dependency-direction-safe service; graph and tool may later import it, but it must not import `app.tools.jobs`.
    4. Prove one short source read, exact safe codes, exact content returned only to the tool caller, bounded presentation projection, no side-effect dependency, required `ponytail:` comment, and service length below 300 lines.
  - Output: One strict schema/service foundation owns passive-JD predicates, exact durable source resolution, bounded pending projection, and cancellation construction.
  - A1 Outcome: Save-job input and confirmation helpers strictly validate the three source modes, resolve the exact initiating message, expose only bounded safe projection data, and construct truthful cancellation without any side-effect dependency.
  - A2 Review Focus: All schema callers, strict union/preview/cancellation separation, predicate thresholds/order, repository ownership and transaction length, safe codes, forbidden projection fields, dependency direction, no tool/provider/ingestion work, required `ponytail:` comment, service size, evidence freshness, and feature scope.
  - A3 Batch Evidence: Foundation rows for P12-JD-01, P12-JD-02, P12-JD-03, and P12-JD-04 plus exclusive schema/service ownership.
  - Acceptance:
    - Exactly one input source validates; preview is current-message-only, bounded, extra-forbid, trimmed, and never enters canonical Job facts.
    - Missing/wrong/empty/non-main initiating messages return the specified safe code with no Job, extraction, embedding, evaluation, or graph call.
    - Pure predicates satisfy every fixed character/line/marker/opt-out/sole-URL boundary and the source-required `ponytail:` limitation without provider or tool work.
    - The projection contains only approved bounded fields; cancellation validates separately as `{committed:false, outcome:'cancelled'}` and cannot parse as a saved Job outcome.
    - Repositories, tools, Agent, API/SSE, ingestion/evaluation, registry, endpoints, database schema, and dependencies remain unchanged; the focused service is below 300 lines.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_job_save_confirmation.py -q` -> PASS evidence: exit `0` with schema/predicate/source/projection/cancellation boundaries; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app/schemas/jobs.py app/services/job_save_confirmation.py tests/unit/test_job_save_confirmation.py --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path, dependency-direction, schema-consumer, payload, migration, registry, and file-length inspection -> PASS evidence: exit `0`, only allowed files changed, no forbidden payload or architecture drift, and the new service is below 300 lines; freshness: final attempt only.
  - Blocked Condition: Missing accepted Plan 11 schema/repository refs is `BLOCKED_MISSING_REF`; conflicting source/recognition authority is `BLOCKED_SOURCE_CONFLICT`; a root foundation requiring tool/Agent/repository/API or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/schemas/jobs.py`, `backend/app/services/job_save_confirmation.py`, `backend/tests/unit/test_job_save_confirmation.py`

- [x] (01B): Integrate current-message interrupt, save, cancel, and replay into save_job
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_12.md` > `## Mandatory Batch01 - Backend Agent Policy and Pasted-JD Confirmation` > `(01B)`
  - Source of Truth: `docs/plans/Plan_12.md` > `### Current-Message Source And Save-Tool Contract`, `### Pre-Mutation Interrupt, Save, Cancel, And Replay`, and `### Ownership And Invariants`; `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Tool And Interrupt Contract` and `## Error And Recovery Behavior`; `docs/plans/Master_plan.md` > heading `### 13.4 \`save_job\`` and `### 14.2 SSE contract`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_12.md` > `(01B)` -> task authority
    - source-interrupt-replay: repository `docs/plans/Plan_12.md` > `### Pre-Mutation Interrupt, Save, Cancel, And Replay` -> exact tool branch/replay authority
    - confirmation-foundation: repository `backend/app/services/job_save_confirmation.py` and `backend/app/schemas/jobs.py` -> accepted (01A) helpers/contracts to consume without reopening
    - profile-interrupt-owner: repository `backend/app/tools/profile.py` > `build_commit_profile_draft_tool` -> accepted interrupt/running-reentry pattern
    - execution-owner: repository `backend/app/services/tool_execution.py` > `execute_tool` -> durable execution/replay authority
    - ingestion-owner: repository `backend/app/services/jd_ingestion.py` > `ingest_raw_text` and `ingest_url` -> accepted exact-content/direct ingestion owners
    - validation-backend-jd: repository `docs/plans/Plan_12.md` > `## Verification` > `Backend JD tool and resume` -> required evidence
  - Source Requirements:
    - Extend the existing `save_job` signature/delegation for accepted current-message schema fields without registering a tool or changing URL/text semantics.
    - Resolve the initiating message and apply the shared opt-out write precondition for every source mode. A clear opt-out returns the accepted cancellation result without interrupt/card/dependency/mutation.
    - For valid current-message mode, keep arguments summary exactly `{source: current_message}`, persist only the accepted bounded card/actions, interrupt before constructing provider/ingestion dependencies, and enable running re-entry only for this mode.
    - Save reloads the same durable source immediately before existing `ingest_raw_text`; cancel constructs no provider/normalizer/embedding/graph dependency and returns the accepted successful no-save result.
    - Preserve one `(run_id, tool_call_id)` execution through interrupt/resume, terminal replay/no-op, `created | returned | retried`, direct URL/text/dedupe behavior, and zero evaluation calls.
  - Dependencies: Task (01A) accepted; no edit to its schema/service foundation.
  - User Action: None; integration tests use fakes and temporary data.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/tools/jobs.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_chat_api.py`
  - Allowed Files: the three listed Job-tool/integration-test files only; consume (01A) read-only. Exclude schema/service foundation, `backend/app/services/tool_execution.py`, chat-turn/runner/checkpoint/repository/API/SSE owners, profile tools, ingestion/evaluation/graph services, registry, settings, migrations, dependencies, frontend, and runtime data.
  - Agent Work:
    1. Trace `build_save_job_tool`, arguments summaries, direct ingestion, (01A) helpers, profile interrupt, `execute_tool`, runner resume, pending history/SSE, and terminal replay callers before editing.
    2. Add failing integration tests for one running execution at interrupt, exact pending/SSE keys, no raw identifiers, zero pre-action dependency calls, and current-message-only running re-entry.
    3. Add failing branch tests for durable-source reload, exact one save, cancel with zero dependencies, duplicate/terminal resume, opt-out precondition across source modes, direct URL/text compatibility, dedupe outcomes, and zero evaluation.
    4. Implement only the minimal tool orchestration over accepted owners; leave generic execution, runner, repository, API, ingestion, and evaluation layers unchanged.
  - Output: The existing `save_job` tool hosts one pre-mutation current-message interrupt and resumes the same durable execution through exact save or cancel.
  - A1 Outcome: save_job current-message mode interrupts before dependencies, exposes only the approved card, reloads and ingests the exact durable source once on save, and cancels/replays without mutation or evaluation.
  - A2 Review Focus: Every Job-tool caller, arguments/pending redaction, opt-out precondition, dependency construction order, running-reentry scope, exact source reload, same identity, branch call counts, replay, direct/dedupe compatibility, no generic-owner edit/evaluation, evidence freshness, and feature scope.
  - A3 Batch Evidence: P12-JD-02, backend projection portion of P12-JD-03, P12-JD-04, P12-JD-05, and tool/interrupt/replay ownership rows.
  - Acceptance:
    - Before either action, one durable execution is `running`, the approved pending projection contains no raw JD/message ID/URL/hash/prompt/provider data, and Job/extraction/embedding/evaluation/graph call counts are zero.
    - Save reloads and ingests the exact durable message once and preserves `created | returned | retried`; cancel returns the exact successful no-save ToolResult with zero mutation/dependency calls.
    - Opt-out produces no card/mutation for every source mode; current-message alone permits running re-entry.
    - Repeated/terminal actions do not repeat work; direct URL/text saves, exact dedupe/retry, profile approval, public saved-JD actions, registry count, endpoints, schemas, and evaluation paths remain unchanged.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py -q` -> PASS evidence: exit `0` with source/redaction/pre-interrupt/save/cancel/replay/direct/dedupe/no-evaluate assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app/tools/jobs.py tests/integration/test_job_tools.py tests/integration/test_chat_api.py --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path, generic-owner, arguments/pending, public-route, migration, dependency, registry-size, and evaluation-call inspection -> PASS evidence: exit `0`, only allowed files changed, and no forbidden payload or architecture drift; freshness: final attempt only.
  - Blocked Condition: Missing accepted (01A) foundation is `BLOCKED_MISSING_REF`; conflicting interrupt/replay authority is `BLOCKED_SOURCE_CONFLICT`; a root implementation requiring a generic execution/runner/repository/API/ingestion or other out-of-bound edit is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/tools/jobs.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_chat_api.py`

- [x] (01C): Enforce readable, evidence-backed, and bounded passive-JD Agent decisions
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_12.md` > `## Mandatory Batch01 - Backend Agent Policy and Pasted-JD Confirmation` > `(01C)`
  - Source of Truth: `docs/plans/Plan_12.md` > `### Response Policy And Active-CV Tool Use`, `### Passive-JD Recognition And One Bounded Repair`, `### Pre-Mutation Interrupt, Save, Cancel, And Replay`, and `### Ownership And Invariants`; `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Recognition Boundary`; `docs/plans/Master_plan.md` > `### 12.5 Conversation and tool policy`, `### 12.6 Tool loop limits`, and heading `### 13.7 \`read_active_cv\``.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_12.md` > `(01C)` -> task authority
    - source-response-policy: repository `docs/plans/Plan_12.md` > `### Response Policy And Active-CV Tool Use` -> response/CV/passive-JD policy authority
    - source-recognition: repository `docs/plans/Plan_12.md` > `### Passive-JD Recognition And One Bounded Repair` -> exact predicate/order/repair authority
    - approved-recognition: repository `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Recognition Boundary` -> approved narrow heuristic
    - prompt-owner: repository `backend/app/agent/prompt.py` > `build_system_prompt` -> current system-policy owner
    - decision-owner: repository `backend/app/agent/graph.py` > existing decision node and named `save_job` helpers -> Plan 11 postcondition/topology owner
    - confirmation-owner: repository `backend/app/services/job_save_confirmation.py` -> accepted (01A) pure predicates to consume without reopening
    - current-message-tool: repository `backend/app/tools/jobs.py` > `build_save_job_tool` -> accepted (01B) production current-message invocation
    - validation-agent-policy: repository `docs/plans/Plan_12.md` > `## Verification` > `Prompt, recognition, topology` -> required evidence
  - Source Requirements:
    - Prompt responses lead with the answer, use no heading for one/two facts, use at most three short user-language groups when needed, hide internals, and preserve all Plan 11 truthfulness rules.
    - Active-CV facts, values, quotes, and genuine counts use the narrowest `read_active_cv` mode; count pagination follows `next_cursor` only as needed within six passes, and the outline is never final body evidence.
    - Passive recognizable JDs request `save_job(source='current_message')`, remain explicitly unsaved pending the card, respect opt-outs, keep sole-URL/explicit direct-save paths, and never auto-evaluate or call `match_jobs` after confirmed passive save.
    - Apply deterministic order: global clear opt-out, positive exact-name Plan 11 path, sole-URL exclusion, then the fixed 300-non-whitespace/five-line/two-distinct-marker obvious-JD predicate. Add exactly one repair after a plain-text miss and fixed truthful refusal after repair failure.
    - Reuse (01A)'s predicates and required `ponytail:` comment, derive named/current-message/cancellation narration only from validated ToolResult, and keep one Agent/decision/ToolNode, seven tools, unchanged state, and six passes.
  - Dependencies: Tasks (01A) and (01B) accepted with the strict foundation and production current-message tool contract.
  - User Action: None; model behavior tests use deterministic fakes.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/agent/prompt.py`, `backend/app/agent/graph.py`, `backend/tests/unit/test_shopaikey_chat.py`, `backend/tests/unit/test_agent_graph.py`
  - Allowed Files: the four listed prompt/decision/unit-test files only; consume accepted (01A)/(01B) owners read-only. Exclude confirmation schema/service, Job tools/integration tests, Agent state/runner/topology/registry, active-CV reader, repositories, API/SSE, provider/model/settings, ingestion/evaluation, dependencies, migrations, and frontend.
  - Agent Work:
    1. Trace prompt construction, initiating-message selection, named-save postcondition, decision exits, tool-call history, ToolResult parsing/narration, and loop counting; inspect every caller before changing shared logic.
    2. Add failing prompt tests for conclusion-first/simple/long response rules, user language, active-CV narrow reads/count pagination, no invented citation/source link, passive current-message wording, opt-outs, direct paths, and no automatic evaluation.
    3. Add failing decision tests for opt-out-over-exact-name, positive exact-name-over-passive, sole URL/ambiguity, first-tool success, one repair success/refusal, unrelated turns, cancellation narration, and unchanged topology/pass count; consume (01A)'s exhaustive pure predicate evidence instead of duplicating it.
    4. Extend only the prompt and existing decision node minimally over (01A)'s tested predicates, retaining Plan 11 behavior and its required `ponytail:` limitation.
    5. Prove discarded model claims are never persisted, no repair loops or calls another tool, and final save/cancel wording comes only from validated durable outcomes.
  - Output: The existing Agent produces direct low-clutter answers, reads active-CV body evidence before factual claims, and creates at most one truthful passive-JD confirmation attempt.
  - A1 Outcome: The one existing Agent follows conclusion-first/CV-evidence policy and deterministically repairs only an obvious passive JD into one current-message save call while opt-outs, direct paths, ToolResult truth, seven tools, and six passes remain intact.
  - A2 Review Focus: Prompt completeness without duplication, exact predicate thresholds/list/order, Unicode/line handling, Plan 11 exact-name callers, first-response discard, one repair/refusal, ToolResult-derived narration, no automatic follow-up, required `ponytail:` comment, unchanged topology/state/tool count/limit, focused evidence freshness, and feature scope.
  - A3 Batch Evidence: P12-RSP-01, P12-CV-01, Agent portions of P12-JD-01/P12-JD-04/P12-JD-05, and P12-REG-01 Agent invariants.
  - Acceptance:
    - Prompt tests contain every response/CV/passive-JD rule without weakening existing general-conversation, profile, failure, or named-save truthfulness.
    - The fixed predicate accepts only source-defined obvious structured English/Vietnamese text and rejects every boundary miss, repeated-single-marker case, sole URL, ambiguous prose, greeting, and clear opt-out.
    - A clear opt-out suppresses exact-name/passive repair and mutation; otherwise positive exact-name behavior precedes passive repair, and only one sole valid current-message save call may be repaired.
    - Repair refusal produces fixed truthful no-confirmation/no-save text; saved/cancelled final narration agrees with validated ToolResult and never triggers automatic matching/evaluation.
    - Agent state, node/ToolNode topology, tool schemas/registry count, direct URL/text behavior, durable replay, and `TOOL_LOOP_LIMIT=6` remain unchanged.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py -q` -> PASS evidence: exit `0` with response/CV/JD prompt, accepted predicate boundaries, precedence, one-repair/refusal, narration, topology, seven-tool, and six-pass assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app/agent/prompt.py app/agent/graph.py tests/unit/test_shopaikey_chat.py tests/unit/test_agent_graph.py --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path, topology, registry-size, prompt-duplication, and file-length inspection -> PASS evidence: exit `0`, only allowed files changed for (01C), and shared owners remain focused; freshness: final attempt only.
  - Blocked Condition: Missing accepted (01A)/(01B) contracts is `BLOCKED_MISSING_REF`; conflicting prompt/recognition authority is `BLOCKED_SOURCE_CONFLICT`; a root implementation requiring service/tool/state/topology/registry/provider or out-of-bound changes is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/agent/prompt.py`, `backend/app/agent/graph.py`, `backend/tests/unit/test_shopaikey_chat.py`, `backend/tests/unit/test_agent_graph.py`

## Mandatory Batch02 - Durable Active-CV Evidence Projection

### Goal

Project only valid successful durable `read_active_cv` records into frontend
history and select one revision-consistent evidence bundle through the existing
assistant-row tool association, without changing backend data or client state
architecture.

### Dependencies

- Batch01 is accepted so active-CV factual answers follow the evidence policy.
- The accepted Plan 9 `read_active_cv` ToolResult, durable history join, retained
  PDF route, and Plan 11 terminal rehydrate contracts remain green.

### Scope Boundary

Own one focused active-CV evidence parser/projector/selector, its chain in
`history.projectToolResultData`, and focused projection/hydration tests. Exclude
backend reader/history changes, chat response shape, reducer/state shape, UI
rendering, dialogs, network fetches, sidebar state, and JD confirmation.

### Tasks

- [ ] (02A): Project and bind strict durable active-CV evidence
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_12.md` > `## Mandatory Batch02 - Durable Active-CV Evidence Projection` > `(02A)`
  - Source of Truth: `docs/plans/Plan_12.md` > `### Strict Active-CV Evidence Projection`, `### Evidence Binding And Citation Placement`, and `### Ownership And Invariants`; `docs/plans/Master_plan.md` > `### 7.5 Tool execution result`, heading `### 13.7 \`read_active_cv\``, and `### 14.2 SSE contract`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_12.md` > `(02A)` -> task authority
    - source-evidence-projection: repository `docs/plans/Plan_12.md` > `### Strict Active-CV Evidence Projection` -> field/record/cap authority
    - source-evidence-binding: repository `docs/plans/Plan_12.md` > `### Evidence Binding And Citation Placement` -> same-row/status/revision authority
    - history-owner: repository `frontend/src/features/chat/history.ts` > `projectToolResultData` and `toolViewToActivity` -> durable projection/terminal hydration owner
    - row-association-owner: repository `frontend/src/features/chat/components/ChatMessageRow.tsx` > `toolsForAssistantDisplay` -> canonical assistant-row association to consume without duplicating
    - uuid-owner: repository `frontend/src/features/chat/types.ts` > `isUuidV4` and JSON types -> existing validation primitives
    - validation-source-projection: repository `docs/plans/Plan_12.md` > `## Verification` > `Frontend source projection` -> required evidence
  - Source Requirements:
    - Create the sole active-CV evidence vocabulary for valid pages/entry/chunk records, enforcing UUID, mode, count, string/list, ordering, page-size, and character bounds while retaining only source-approved fields.
    - Derive `has_more` from non-null `next_cursor`, then discard the cursor. Unknown/forbidden fields never enter client activity; required vocabulary/type failures return `null`.
    - Chain the projector after existing save/match projectors. Stream `tool_status` remains `resultData=null`; only durable terminal history supplies evidence.
    - Select only completed successful exact-name `read_active_cv` pages belonging to the row's existing tool association; require at least one record and agreement on attachment/extraction/source revision across valid pages.
    - Ignore failed/malformed pages when another valid page exists, suppress all evidence for conflicting valid revisions, preserve page/record order and exact content, and never borrow global/neighboring state or fetch/normalize/summarize records.
  - Dependencies: Batch01 accepted; accepted Plan 9 reader/history contract available.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/chat/activeCvEvidence.ts`, `frontend/src/features/chat/history.ts`, `frontend/src/test/active-cv-source.test.tsx`, `frontend/src/test/sse-reducer.test.ts`
  - Allowed Files: the four listed projection/history/test files only; exclude `ChatMessageRow.tsx`, `ChatPage.tsx`, reducer/types shape, observability API/state, backend, package/dependency files, CSS, source dialog/rendering, and JD confirmation.
  - Agent Work:
    1. Trace the exact durable `read_active_cv` result shape, all history projectors, `ClientToolActivity.resultData`, terminal rehydrate, and `toolsForAssistantDisplay`; reuse `isUuidV4` and current JSON types.
    2. Add failing tests for every valid record kind and boundary, exact content/order, page caps, derived `has_more`, forbidden-key stripping, required-field failures, failed/empty/non-CV/stream-only tools, consistent multipage evidence, row isolation, and conflicting revisions.
    3. Implement the focused parser/projector/selector and add one projection-chain call without changing generic state or reducer shapes.
    4. Prove initial/restart/terminal hydration yields the same bundle and transient stream state yields none.
  - Output: Each assistant row can receive one strict ordered bundle representing only successful durable active-CV evidence read for that row.
  - A1 Outcome: Terminal history projects bounded allowlisted read_active_cv records and selects them only for the owning assistant row and one consistent CV revision, while stream/failed/malformed/conflicting evidence yields none.
  - A2 Review Focus: Every field/record boundary, forbidden-key behavior, exact content/order, projector precedence, terminal-only source, completed-success gating, row callers, revision conflict handling, no reducer/backend/fetch change, focused evidence freshness, and feature scope.
  - A3 Batch Evidence: P12-CV-02, parser/binding portions of P12-CV-05, and durable history/file ownership rows.
  - Acceptance:
    - Valid entry, entry-match, chunk, and chunk-match pages project only approved fields with exact order/content, bounded counts/chars, and derived `has_more`; cursor and forbidden fields are absent.
    - Missing/invalid required fields, failed/non-CV tools, empty record sets, and stream-only activity produce no evidence bundle.
    - Multiple valid pages preserve durable tool order only when attachment/extraction/source revision agrees; conflicting valid revisions suppress the whole bundle.
    - Evidence never crosses an assistant/user/run boundary and initial, terminal-rehydrate, refresh, and restart projection are deterministic without a new store or fetch.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/active-cv-source.test.tsx src/test/sse-reducer.test.ts` -> PASS evidence: exit `0` with allowlist/boundary/order/status/revision/stream/terminal/restart assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path and state-shape inspection -> PASS evidence: exit `0`, only allowed files changed, and no reducer/history API/network/store duplication; freshness: final attempt only.
  - Blocked Condition: Missing accepted reader/history refs is `BLOCKED_MISSING_REF`; a durable result-shape conflict is `BLOCKED_SOURCE_CONFLICT`; a root implementation requiring backend, reducer/state, UI, or out-of-bound changes is `BLOCKED_SCOPE_CONFLICT`; unavailable Node/npm tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/chat/activeCvEvidence.ts`, `frontend/src/features/chat/history.ts`, `frontend/src/test/active-cv-source.test.tsx`, `frontend/src/test/sse-reducer.test.ts`

## Mandatory Batch03 - Readable Assistant Responses and CV Source Dialog

### Goal

Render assistant-only semantic Markdown and compose one adjacent active-CV source
control/dialog from Batch02 evidence while preserving literal user/system
messages, existing row/card order, accessibility, and zero hidden evidence fetch.

### Dependencies

- Task (02A) and Batch02 A3 are accepted with deterministic evidence bundles.
- Pinned Astryx 0.1.4 public APIs and the existing retained-PDF URL owner are
  available; no dependency upgrade is authorized.

### Scope Boundary

Own the focused assistant renderer, source dialog, minimal message-row composition,
and directly required component tests. Exclude persisted/reducer content mutation,
history projection changes, backend, observability/sidebar state, custom Markdown
or modal implementations, package/CSS/framework changes, existing card behavior,
and mobile/responsive work.

### Tasks

- [ ] (03A): Render assistant Markdown with one exact active-CV source dialog
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_12.md` > `## Mandatory Batch03 - Readable Assistant Responses and CV Source Dialog` > `(03A)`
  - Source of Truth: `docs/plans/Plan_12.md` > `### Assistant-Only Astryx Markdown`, `### Evidence Binding And Citation Placement`, `### Source Dialog`, and `### Ownership And Invariants`; `docs/plans/Master_plan.md` > `### 15.3 Chat components` and `### 15.7 Readable Agent responses and pasted-JD confirmation`; `frontend/AGENTS.md` > Astryx workflow and rules.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_12.md` > `(03A)` -> task authority
    - source-markdown: repository `docs/plans/Plan_12.md` > `### Assistant-Only Astryx Markdown` -> renderer contract
    - source-citation: repository `docs/plans/Plan_12.md` > `### Evidence Binding And Citation Placement` -> exact-one placement authority
    - source-dialog: repository `docs/plans/Plan_12.md` > `### Source Dialog` -> exact evidence/accessibility/original-CV authority
    - astryx-rules: repository `frontend/AGENTS.md` > `WORKFLOW` and `RULES` -> pinned component discovery/composition authority
    - composition-owner: repository `frontend/src/features/chat/components/ChatMessageRow.tsx` > `ChatMessageRow` -> existing row/card order owner
    - retained-url-owner: repository `frontend/src/features/observability/api.ts` > `getRetainedCvUrl` -> original-PDF URL owner to reuse without editing
    - validation-response-source: repository `docs/plans/Plan_12.md` > `## Verification` > `Frontend response rendering`, `Desktop active-CV source`, and `Desktop original/history` -> required evidence
  - Source Requirements:
    - Assistant content uses public Astryx `Markdown` with compact density, heading level 4, and the existing streaming flag; user and system content remain literal.
    - An ephemeral display-only transform places exactly one Astryx Citation labelled `Nguồn` after the first safe direct-answer paragraph, never inside code/link/list syntax or persisted/reducer/history text; fall back after the body when no safe lead exists.
    - One local dialog renders every selected page/record in durable order without deduplication, shows exact entry/chunk content and available metadata, and discloses partial evidence for page/record truncation or additional pages.
    - The dialog performs zero evidence/chunk requests and opens the evidence attachment through existing `getRetainedCvUrl` with `_blank` and `noopener,noreferrer`, not the currently active sidebar CV.
    - Use pinned Astryx Citation/Dialog/layout primitives and preserve keyboard activation, close/Escape, title focus, trigger-focus restoration, scrolling, message variants, tool activity, saved/match/zero-result/profile cards, failures, and keys.
  - Dependencies: Task (02A) and Batch02 accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/chat/components/AssistantResponse.tsx`, `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/test/assistant-response.test.tsx`, `frontend/src/test/active-cv-source.test.tsx`, `frontend/src/test/chat-page.test.tsx`
  - Allowed Files: the seven listed renderer/dialog/composition/test files only; consume but do not edit Batch02's `activeCvEvidence.ts` or `history.ts`, `frontend/src/features/observability/api.ts`, Astryx/package manifests, reducer/types/state, ChatPage logic, existing card owners, CSS, backend, and mobile/responsive owners.
  - Agent Work:
    1. Run `npx astryx build "assistant Markdown with inline active-CV citation and source dialog"`, then inspect `npx astryx component Markdown`, `npx astryx component Citation`, `npx astryx component Dialog`, `npx astryx component DialogHeader`, and each selected layout/text/button primitive before writing UI.
    2. Trace assistant/user/system rendering, streaming, row/tool/card order, Batch02 selector, retained URL construction, and existing component tests; do not guess public props or duplicate owners.
    3. Add failing tests for semantic headings/emphasis/lists/links/code, compact/heading/stream props, literal user/system markers, safe/fallback citation placement, exact-one behavior, hidden marker, exact record/page order, partial notice, no fetch, historical attachment URL, and dialog keyboard/focus/close behavior.
    4. Implement the two focused presentation owners and delegate from `ChatMessageRow`; use Astryx layout/components and tokens, with no persisted content mutation or new state store.
    5. Re-run focused/static tests and existing row/card regressions affected by composition.
  - Output: Assistant prose renders cleanly and each valid active-CV-backed answer exposes one accessible exact-evidence source dialog.
  - A1 Outcome: Assistant-only content renders compact streaming Astryx Markdown and one evidence-backed Nguồn control opens the exact durable records and original retained CV, while user/system text and existing cards remain unchanged.
  - A2 Review Focus: Astryx public API use, semantic/literal role split, marker safety and non-persistence, exact-one citation, bundle callers, record order/content, partial notice, zero fetch, retained attachment URL/options, keyboard/focus behavior, row/card regressions, no package/CSS/mobile changes, focused evidence freshness, and feature scope.
  - A3 Batch Evidence: P12-RSP-02, P12-CV-03, P12-CV-04, UI/negative portions of P12-CV-05, and Astryx/row ownership rows.
  - Acceptance:
    - Normal assistant Markdown renders semantically with compact density, shifted headings, and streaming support; raw syntax is not shown, while identical user/system syntax stays literal.
    - A row with one or more valid consistent evidence pages renders exactly one `Nguồn`; no safe lead uses the deterministic post-body fallback, and the reserved marker never appears or mutates stored/client state.
    - The dialog preserves page and record order/content, displays source-approved metadata and partial status, never fetches more evidence, and opens the answer's retained attachment with the required browser options.
    - Empty/failed/malformed/unrelated/conflicting/stream-only evidence shows no citation; refresh/history behavior and existing tool/card/approval/failure ordering remain green.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/assistant-response.test.tsx src/test/active-cv-source.test.tsx src/test/chat-page.test.tsx` -> PASS evidence: exit `0` with Markdown role/stream semantics, exact-one placement, exact dialog/no-fetch/original-CV, accessibility, negative evidence, and history assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run src/test/empty-match-card.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/approval-card.test.tsx` -> PASS evidence: exit `0` with existing assistant-row cards/actions/order unchanged; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path, dependency, persisted-marker, network-call, raw-element/style, and responsive-scope inspection -> PASS evidence: exit `0`, only allowed files changed, and no custom Markdown/modal/fetch/package/CSS/mobile path exists; freshness: final attempt only.
  - Blocked Condition: Missing accepted Batch02 bundle or pinned component docs is `BLOCKED_MISSING_REF`; an Astryx/source-placement conflict is `BLOCKED_SOURCE_CONFLICT`; a root implementation requiring history/reducer/backend/package/CSS/mobile or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Node/npm/Astryx tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/chat/components/AssistantResponse.tsx`, `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/test/assistant-response.test.tsx`, `frontend/src/test/active-cv-source.test.tsx`, `frontend/src/test/chat-page.test.tsx`

## Mandatory Batch04 - Restart-Safe JD Save Confirmation UI

### Goal

Render one strict two-action confirmation card for the interrupted passive-JD
run and reuse the existing row association, resume endpoint, composer/first-click
locks, terminal history truth, and saved-result invalidation without adding a
store, reducer, endpoint, or evaluation action.

### Dependencies

- Batch01 backend pending/save/cancel/replay contract is accepted.
- Batch03 assistant-row composition is accepted; Batch04 extends those shared
  composition files rather than recreating or bypassing them.

### Scope Boundary

Own one focused JD pending-projection parser/selector, one Astryx card, minimal
shared row/resume/tool-label composition, and focused frontend tests. Exclude
backend, reducers or new state stores, resume/API endpoints, save/evaluation
transport, existing saved-job parser/card semantics, local storage, package/CSS,
and mobile/responsive work.

### Tasks

- [ ] (04A): Render and resume one strict pasted-JD confirmation card
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_12.md` > `## Mandatory Batch04 - Restart-Safe JD Save Confirmation UI` > `(04A)`
  - Source of Truth: `docs/plans/Plan_12.md` > `### Strict JD Confirmation Projection And Card`, `### Ownership And Invariants`, and `## Completion Contract`; `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Frontend Contract` and `## Error And Recovery Behavior`; `docs/plans/Master_plan.md` > `### 14.2 SSE contract` and `### 15.7 Readable Agent responses and pasted-JD confirmation`; `frontend/AGENTS.md` > Astryx workflow and rules.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_12.md` > `(04A)` -> task authority
    - source-jd-card: repository `docs/plans/Plan_12.md` > `### Strict JD Confirmation Projection And Card` -> strict projection/action/recovery authority
    - approved-frontend-contract: repository `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Frontend Contract` -> approved copy/card/shared-flow authority
    - row-owner: repository `frontend/src/features/chat/components/ChatMessageRow.tsx` > `profileCommitForRow`, `saveJobResultForTools`, and `ChatMessageRow` -> association/result/composition patterns to generalize minimally
    - resume-owner: repository `frontend/src/features/chat/ChatPage.tsx` > `approvalLockedRunIds`, `approvalInFlightRef`, and current approval resume handler -> shared first-click/composer/transport owner
    - activity-owner: repository `frontend/src/features/chat/components/ChatToolActivity.tsx` > friendly tool label projection -> presentation-only Review JD owner
    - validation-jd-card: repository `docs/plans/Plan_12.md` > `## Verification` > `Frontend JD confirmation` -> required evidence
  - Source Requirements:
    - Strictly accept only the exact `job_save_confirmation` kind/actions/card/source/bounds; reject missing, extra, duplicate, wrong-type, over-limit, or forbidden raw/message/URL/hash/argument/prompt/provider/stack fields.
    - Malformed projection uses the existing generic interrupted notice, exposes no JSON/action, and keeps the composer locked.
    - Render the exact Vietnamese heading/sentence and exactly `Lưu JD`, then `Không lưu`, using pinned Astryx Card/MetadataList/Badge/ButtonGroup/Button; omit absent optional preview rows and never invent Job facts.
    - Reuse the current generic resume endpoint, `approvalLockedRunIds`, `approvalInFlightRef`, composer lock, error behavior, durable recovery, and first-click rule. Both buttons lock before transport and an ambiguous transport error remains locked until refresh.
    - A valid interrupted row may label running `save_job` as `Review JD`; terminal state returns to normal. Cancel renders no SavedJobCard/invalidation; accepted terminal history with validated `sqlite_committed=true` renders existing save results and invalidates saved-JD state exactly once, never evaluates.
    - Live SSE, initial history, terminal rehydrate, refresh, and restart select one canonical card host without crossing message/run boundaries or adding a JD store/reducer/local-storage path.
  - Dependencies: Batch01 and Batch03 accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/chat/jobSaveConfirmation.ts`, `frontend/src/features/chat/components/JobSaveConfirmationCard.tsx`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/components/ChatToolActivity.tsx`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/test/job-save-confirmation.test.tsx`, `frontend/src/test/chat-page.test.tsx`, `frontend/src/test/sse-reducer.test.ts`, `frontend/src/test/approval-card.test.tsx`, `frontend/src/test/saved-job-card.test.tsx`
  - Allowed Files: the eleven listed parser/card/composition/test files only; extend Batch03's accepted row composition minimally. Exclude `history.ts`/`activeCvEvidence.ts`, reducer/types data shapes unless a source-proven prerequisite conflict is escalated, profile ApprovalCard implementation, saved-job API/parser/card/state owners, resume transport/API, package/dependency files, CSS, backend, local storage, and mobile/responsive owners.
  - Agent Work:
    1. Run `npx astryx build "compact pasted-JD save confirmation card"`, then inspect `npx astryx component Card`, `npx astryx component MetadataList`, `npx astryx component Badge`, `npx astryx component ButtonGroup`, and `npx astryx component Button`.
    2. Trace pending-approval stream/history association, generic recovery, profile action typing, composer lock, resume/in-flight callers, terminal rehydrate, save-result projection, invalidation callback, and tool labels before editing.
    3. Add failing parser/card tests for every allowed boundary/extra/forbidden key, optional preview, exact copy/order, keyboard actions, first-click/ambiguous-error lock, malformed fallback, Review JD lifecycle, and canonical live/restart host.
    4. Add failing integration-style component tests proving both actions use the same resume endpoint; cancel has no SavedJobCard/invalidation; only durable committed success produces existing SavedJobCard and one invalidation; no evaluate dispatch or cross-row action occurs.
    5. Implement the focused parser/card and minimal callback/row/tool-label generalization, keeping reusable logic outside already-large `ChatPage.tsx` and `ChatMessageRow.tsx`.
  - Output: Every valid interrupted passive-JD run renders one restart-safe confirmation card whose first action resumes the existing backend execution truthfully.
  - A1 Outcome: A strict one-host JD confirmation card survives live/history/restart state, locks both actions on first click, resumes save or cancel through the existing endpoint, and gates SavedJobCard/invalidation on durable committed success without evaluation.
  - A2 Review Focus: Exact strict vocabulary/forbidden fields, copy/order/accessibility, row/run association, profile approval compatibility, lock timing/error semantics, Review JD lifecycle, terminal durable proof, cancellation gating, exactly-one invalidation, no evaluate/store/reducer/endpoint/package/mobile change, focused evidence freshness, and feature scope.
  - A3 Batch Evidence: P12-JD-03, frontend portions of P12-JD-04/P12-JD-05, restart/history integration, and shared row/resume ownership rows.
  - Acceptance:
    - Only the exact source-defined pending projection renders the JD card; every malformed/extra/forbidden variant falls back safely and remains locked without exposing payload data.
    - The card uses the exact heading, sentence, optional bounded preview, and two actions in required order; both disable before one shared resume request and stay locked after ambiguous transport failure.
    - Live, refresh, initial history, and restart render exactly one card for the owning run; both actions use the existing endpoint and no action/evidence crosses rows.
    - Cancel completes with no SavedJobCard, saved-JD invalidation, or evaluate dispatch; only terminal rehydrate with validated committed save truth produces the existing result card and exactly one invalidation.
    - Profile approval, composer locking, tool activity, assistant source UI, saved/match/zero-result cards, and direct/explicit save/evaluation paths remain green without a new store or reducer.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/job-save-confirmation.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts` -> PASS evidence: exit `0` with strict projection, exact card/actions, locks, Review JD, live/restart host, branch gating, one invalidation, and no-evaluate assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run src/test/approval-card.test.tsx src/test/saved-job-card.test.tsx src/test/empty-match-card.test.tsx src/test/match-card.test.tsx` -> PASS evidence: exit `0` with existing approval/result/recovery/source row behavior unchanged; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path, payload, reducer/store, endpoint, evaluate-call, dependency, file-size, and responsive-scope inspection -> PASS evidence: exit `0`, only allowed files changed, and no forbidden raw data or parallel state/transport owner exists; freshness: final attempt only.
  - Blocked Condition: Missing accepted backend pending contract or Batch03 row composition is `BLOCKED_MISSING_REF`; a pending/action or durable-commit authority conflict is `BLOCKED_SOURCE_CONFLICT`; a root implementation requiring history/reducer schema, backend, API, saved-job state, package/CSS/mobile, or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Node/npm/Astryx tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/chat/jobSaveConfirmation.ts`, `frontend/src/features/chat/components/JobSaveConfirmationCard.tsx`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/components/ChatToolActivity.tsx`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/test/job-save-confirmation.test.tsx`, `frontend/src/test/chat-page.test.tsx`, `frontend/src/test/sse-reducer.test.ts`, `frontend/src/test/approval-card.test.tsx`, `frontend/src/test/saved-job-card.test.tsx`

## Mandatory Batch05 - Integrated Desktop Release Evidence

### Goal

Run every focused/full/static/build/plan gate and the source-defined
desktop-only readable-response, active-CV provenance, JD cancel/save/restart,
direct-path, and negative checks on final accepted code, producing sanitized
immutable evidence without repairing product code in the evidence task.

### Dependencies

- Batch01 through Batch04 each have matching final A1/A2 evidence, Orchestrator
  `ACCEPTED` events, checked canonical task markers, and accepted A3 batch audits.
- A usable ignored root `.env`, Docker, desktop browser, provider access where
  the manual Agent path requires it, synthetic active CV/JDs, retained-PDF route,
  and free documented ports are available without sharing secret values.

### Scope Boundary

Own final-attempt command execution, desktop-only observation, sanitized A1
evidence, verified named-disposable-stack lifecycle, and restoration of any
user-approved normal stack. Edit no repository file. Exclude product/test/docs
repairs, task checkbox changes by A1, acceptance-report rewrites, real/personal
data, raw payloads, security tests, and mobile/narrow-layout checks.

### Tasks

- [ ] (05A): Prove readable responses, CV provenance, and both JD branches on final code
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_12.md` > `## Mandatory Batch05 - Integrated Desktop Release Evidence` > `(05A)`
  - Source of Truth: `docs/plans/Plan_12.md` > `## Verification` and `## Completion Contract`; `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Testing`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` and `## 24. Local Testing Strategy`; `README.md` > setup, health, verification, data, and safe cleanup commands.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_12.md` > `(05A)` -> task authority
    - validation-plan12: repository `docs/plans/Plan_12.md` > `## Verification` -> complete automated/desktop evidence matrix
    - completion-plan12: repository `docs/plans/Plan_12.md` > `## Completion Contract` -> binary feature/invariant boundary
    - approved-desktop-tests: repository `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` > `## Testing` -> approved synthetic desktop cases
    - runtime-owner: repository `README.md` and `infrastructure/docker-compose.yml` -> three-service local runtime, data, and cleanup authority
    - structure-validator: repository `docs/plans/Plan_12.md` > `## Verification` > `Plan structure` -> contiguous plan validation authority
  - Source Requirements:
    - Run all focused backend/frontend commands, existing card/chat regressions, full Ruff/mypy/pytest/Vitest/ESLint/TypeScript/Vite gates, plan validator, health, and scope hygiene on the final accepted output.
    - At desktop `localhost:5173`, prove simple/long response layout, semantic Markdown, active-CV count evidence, one exact source dialog/original PDF, refresh/history persistence, and negative provenance.
    - Prove English-JD cancel/restart and Vietnamese-JD save/dedupe from baseline Job/evaluation/graph/provider counts: zero side effects before action, zero mutation after cancel, exact source once after save, one deduplicated Job, no evaluation, and truthful result cards.
    - Prove sole URL, explicit direct text, opt-out, ambiguous prose, profile approval, saved-JD evaluation, and other existing cards remain compatible; no mobile or security acceptance is performed.
    - Record only sanitized current-run facts in the assigned A1 report. Use a verified named disposable Compose project, remove only its resources, restore any previously approved normal stack, and make no repository edit.
  - Dependencies: All Batch01-Batch04 tasks and A3 audits accepted.
  - User Action: Before desktop validation, provide a usable ignored root `.env` and required Docker/browser/provider prerequisites without sharing values; ensure ports 5173, 8000, 7474, and 7687 are free or explicitly approve pausing and later restoring the known normal Compose project. Unknown project/volume targets block teardown.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: None in the repository; final evidence belongs only in the assigned `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md` report.
  - Allowed Files: no repository files; A1 may write only its assigned immutable A1 report under Artifact Root. Exclude product/tests/config/docs/tasks changes, `.env`, runtime databases/uploads, prior evidence, personal screenshots, and task checkbox updates by A1.
  - Agent Work:
    1. Confirm matching accepted evidence for every prior task/A3, inspect final changed paths and ownership, then run all focused and full automated/static/build/plan gates without repairing failures.
    2. Verify the project name/ports, establish sanitized baseline Job/evaluation/graph/provider-call counts, start `jobagent-plan12-smoke` from the existing Compose file, and confirm all three services plus API health.
    3. Execute the simple/long, active-CV source/original/history/negative, English cancel/restart, Vietnamese save/dedupe, direct URL/text, opt-out, ambiguous prose, and regression cases exactly at desktop size using only synthetic/public data.
    4. Inspect browser UI/network/state and sanitized backend/runtime evidence for action counts, durable execution identity, source attachment/order, provider-versus-ingestion calls, Job/evaluation/graph counts, no hidden fetch, no raw projection, and no auto-evaluation.
    5. After verifying the resolved project name, tear down only `jobagent-plan12-smoke` and its disposable resources, restore any normal stack using the user's prior approval, rerun health if restored, and write only the assigned sanitized report.
  - Output: Fresh final automated and desktop evidence that every Plan 12 requirement and preserved architecture invariant passes without scope expansion.
  - A1 Outcome: Final accepted code passes all required gates and synthetic desktop response/CV/JD cases with exact durable evidence, zero unauthorized side effects, safe teardown/restoration, and no repository edit.
  - A2 Review Focus: Accepted prior provenance, final-attempt freshness, every command exit, complete desktop matrix, exact UI/network/durable/count evidence, provider-versus-ingestion distinction, no hidden fetch/raw data/auto-evaluation, direct/profile/card regressions, plan/tool/topology/schema/dependency scope, sanitized evidence, safe project lifecycle, no repository edit, and feature hard gates.
  - A3 Batch Evidence: Final P12-RSP-01/02, P12-CV-01 through P12-CV-05, P12-JD-01 through P12-JD-05, P12-REG-01, integration, desktop, scope, secret/data hygiene, and local-demo readiness rows.
  - Acceptance:
    - Every focused/full/static/build/plan command passes from final accepted code with fakes and no live provider call in automated tests.
    - Simple and grouped assistant answers lead directly and render semantic Markdown; user/system literals remain unchanged and longer answers use no more than three groups.
    - The synthetic Certificate question performs bounded active-CV reads, answers the exact count, shows one source control with exact ordered records/partial truth, opens the evidence PDF, survives refresh/history, and makes no hidden evidence fetch; all negative provenance cases show none.
    - English cancel/restart and Vietnamese save/dedupe preserve one running execution/card per run, zero pre-action calls, exact save/cancel outcomes, one deduplicated Job, no cancel mutation, no evaluation request/row, and correct existing result-card/invalidation behavior.
    - Sole URL/direct text/profile/evaluation/saved-match/zero-result flows remain compatible; opt-out and ambiguity create no forced card/mutation; one Agent/decision/ToolNode, seven tools, six passes, endpoints, schema, dependencies, and desktop layout remain unchanged.
    - Evidence contains no secret, real/personal or raw CV/JD content, prompt/provider transcript, query, path, database, or unsupported claim; only the named disposable resources are removed and any approved normal stack is restored.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py -q` -> PASS evidence: exit `0` with prompt/recognition/topology coverage; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py tests/integration/test_active_cv_tool.py -q` -> PASS evidence: exit `0` with source/interrupt/branch/replay/direct-path and active-CV regressions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run src/test/active-cv-source.test.tsx src/test/assistant-response.test.tsx src/test/job-save-confirmation.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts` -> PASS evidence: exit `0` with projection/Markdown/source/dialog/JD/live/history/restart coverage; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run src/test/empty-match-card.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/approval-card.test.tsx` -> PASS evidence: exit `0` with existing card/action/row regressions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental; py -3.13 -m pytest -q` -> PASS evidence: all exit `0` with fakes and no real provider call; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0` with the pinned dependency set; freshness: final attempt only.
    - Required: `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` -> PASS evidence: exit `0`, `valid: true`, contiguous Plans 1-12, and no errors; freshness: final attempt only.
    - Required: `docker compose -p jobagent-plan12-smoke --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180; Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS evidence: named disposable frontend/backend/Neo4j services are healthy and API `overall` is `available`; freshness: current Compose run only.
    - Required: execute every desktop simple/long, active-CV source/original/history/negative, JD cancel/restart/save/dedupe/direct/opt-out case from `docs/plans/Plan_12.md` > `## Verification`, excluding mobile/security -> PASS evidence: sanitized current-run UI/network/durable/count observations satisfy every Acceptance bullet; freshness: current Compose run only.
    - Required: after verifying the resolved project name, run `docker compose -p jobagent-plan12-smoke --env-file .env -f infrastructure/docker-compose.yml down --volumes --remove-orphans` and restore any user-approved normal stack -> PASS evidence: only named disposable containers/networks/volumes are removed and prior normal health is restored; freshness: current run only.
    - Required: `git diff --check; git status --short` plus inspection of changed paths, file lengths, manifests, migrations, public routes, state/store owners, tool registry/topology, raw payloads, evaluation calls, tracked data/secrets, and mobile/security scope -> PASS evidence: diff check exits `0`, only accepted Plan 12 implementation/task plus pre-existing user-owned planning paths appear, and (05A) itself changed no repository file; freshness: final attempt only.
  - Blocked Condition: Missing accepted prior task/A3 evidence is `BLOCKED_MISSING_REF`; missing/invalid `.env`, provider access, occupied ports without pause approval, or unknown restore/teardown target is `BLOCKED_USER_ACTION`; unavailable Docker/browser/Python/Node/runtime is `BLOCKED_ENVIRONMENT`; unavailable browser or teardown permission is `BLOCKED_PERMISSION`; any gate/manual failure requiring a repository repair is `BLOCKED_SCOPE_CONFLICT` and returns to the owning earlier task rather than being fixed in (05A).
  - Files: None in the repository; assigned `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md` only.
