# JobAgent Plan 11 Execution Tasks

## Purpose

Translate `docs/plans/Plan_11.md` into the mandatory repair chain for the five
verified desktop functional failures: browser DELETE transport, activation-driven
CV Manager and saved-JD cache coherence, truthful explicitly named `save_job`
execution, and empty extraction-summary parity. Preserve the implemented Plan 10
architecture and finish with fresh automated and desktop-only evidence.

## Project Context Notes

- Root `README.md` was read completely before derivation. It defines JobAgent as a
  local single-user React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, and ShopAIKey
  application with a root-only ignored `.env`, exactly three Compose services,
  synthetic automated tests, and desktop development at `localhost:5173`.
- The current user explicitly invoked `task-writing-agent` for `Plan_11.md`. That
  instruction authorizes this task file and supersedes only Plan 11's planning-phase
  statement that a fresh portfolio review must precede task writing; it does not
  expand repair scope, authorize product execution, or claim acceptance.
- Primary authority is `docs/plans/Plan_11.md`. The approved failure report and
  functional matrix supply reproduction evidence; `docs/plans/Master_plan.md` and
  `docs/plans/Plan_10.md` supply compatible architecture and ownership constraints.
- The shared structural validator passed on 2026-07-18 with contiguous
  `Plan_1.md` through `Plan_11.md` and no errors. All ten canonical Plan 10 task
  markers are checked; execution still requires the matching immutable
  A1/A2/Orchestrator acceptance evidence rather than inferring acceptance from
  checkbox text alone.
- Existing root-cause owners were confirmed at `backend/app/main.py`,
  `backend/app/agent/prompt.py`, `backend/app/agent/graph.py`,
  `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`,
  `frontend/src/features/observability/state.ts`,
  `frontend/src/features/observability/ObservabilitySidebar.tsx`,
  `frontend/src/features/jobs/savedJobsState.ts`,
  `frontend/src/features/jobs/types.ts`, and
  `frontend/src/features/jobs/SavedJobDetail.tsx`. Extend these owners; do not
  create parallel CORS, cache, parser, Agent, or acceptance-report owners.
- `frontend/AGENTS.md` applies to frontend repairs: search and reuse first, keep
  modules focused, preserve Astryx composition and tokens, and avoid unrelated
  layout work. Plan 11 requires no new Astryx component and explicitly excludes
  mobile/responsive implementation and acceptance.
- The worktree already contains the user's modified `docs/plans/Plan_10.md` and
  untracked `docs/plans/Plan_11.md`,
  `docs/acceptance/full_functional_failure_report.md`, and
  `docs/acceptance/full_functional_test_matrix.md`. Preserve them. This authoring
  pass creates only `docs/tasks/task_11.md`.
- Automated tests use fakes and make no real provider call. Only the final desktop
  task may use configured local services and synthetic/public test data. Never
  expose `.env` values, credentials, raw CV/JD bodies, provider transcripts, SQL,
  Cypher, storage paths, databases, or personal screenshots in task evidence.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_11.md`.
- Supporting: `docs/acceptance/full_functional_failure_report.md`,
  `docs/acceptance/full_functional_test_matrix.md`,
  `docs/plans/Master_plan.md`, and `docs/plans/Plan_10.md`.
- Context only: `README.md`, `frontend/AGENTS.md`, `docs/tasks/task_10.md`,
  existing code/tests, and `infrastructure/docker-compose.yml`.

### Source Section Index

- `Plan_11.md` > `## Objective`, `## Master Requirement Coverage`,
  `## Prerequisites`, `## Scope`, and `## Out of Scope` -> F11-01 through
  F11-06, mandatory repair boundary, prerequisites, and exclusions.
- `Plan_11.md` > `### Browser DELETE transport` -> exact GET/POST/DELETE CORS
  allowlist and representative CV/Job preflight contract.
- `Plan_11.md` > `### Activation and cache coherence` -> one activation fan-out,
  CV Manager reload generation, retained safe data, saved-JD non-destructive
  invalidation, and no automatic evaluation.
- `Plan_11.md` > heading “### Truthful named `save_job` execution” -> exact-name gate,
  one bounded repair decision, truthful fallback, ToolResult-derived outcome, and
  unchanged one-Agent topology.
- `Plan_11.md` > `### Empty extraction summary parity` -> string-contract parity,
  strict parser preservation, and visible fallback.
- `Plan_11.md` > `## Implementation`, `## Verification`, and
  `## Completion Contract` -> test-first order, full gates, five original desktop
  reproductions, evidence hygiene, and completion conditions.
- `full_functional_failure_report.md` > `## F-01` through `## F-05` -> approved
  symptoms, exact reproductions, current evidence, and root-cause locations.
- `full_functional_test_matrix.md` >
  `### Application shell, navigation, and responsive behavior`,
  `### Chat, SSE, history, and tool activity`,
  `### CV Manager and bounded active-CV access`,
  `### JD ingestion, matching, and result cards`, and
  `### Saved-JD library, evaluations, and zero-result recovery`
  -> affected functional IDs and expected behavior. Mobile/responsive rows are not
  part of Plan 11 evidence.
- `Master_plan.md` > `### 6.2 Application table schemas`,
  `### 7.4 Job extraction`, `### 7.7 Saved JD and evaluation views`,
  `### 10.5 CV Manager reprocessing and deletion`,
  `### 12.5 Conversation and tool policy`, `### 12.6 Tool loop limits`,
  heading “### 13.4 `save_job`”, `### 14.1 API rules`, `### 15.2 Sidebar`,
  `### 15.6 Observability sidebar boundaries`,
  `### 17.5 Explicit saved-JD evaluation flow`,
  `## 20. Failure and Recovery Policy`, `## 24. Local Testing Strategy`, and
  `## 27. Definition of Done` -> retained architecture, schema, UX, and release
  constraints.

### Approved Architecture and Constraints

- Keep one React/Astryx frontend, one FastAPI application, one LangGraph Agent,
  one decision node, one ToolNode, the existing seven registered tools, and the
  six-pass tool-loop limit.
- Keep SQLite as source of truth and Neo4j as a derived index. Existing CV and Job
  deletion coordinators remain the sole mutation owners; this phase changes only
  browser permission to reach them.
- `App.handleProfileSaved` remains the sole successful approval composition event.
  Reuse the existing observability and sidebar-local saved-JD state owners, latest
  request guards, abort behavior, selection, and successful-data retention.
- Activation refreshes server-derived currentness but never evaluates a Job or
  inserts a `job_evaluations` row automatically.
- A named `save_job` request receives only the source-approved narrow deterministic
  postcondition. Do not add Agent state, a node, an intent classifier, claim
  heuristics, a provider/model change, or unbounded retries.
- Backend `JobPostExtraction.summary` remains a required string that may be empty.
  Do not change schemas, migrations, persisted rows, evaluation scoring, or the
  separately non-empty MatchResult summary.
- Security testing, mobile/responsive work, new endpoints, dependencies, stores,
  workers, queues, product features, and fixes outside F-01 through F-05 are
  excluded.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Root-cause functional repairs with focused regressions | (01A), (01B), (01C), (01D) | Accepted Plan 10 baseline |
| Batch02 | Fresh full gates and all five desktop reproductions | (02A) | Batch01 |

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

## Mandatory Batch01 - Root-Cause Functional Repairs

### Goal

Repair the four independent ownership boundaries that cause F-01 through F-05 and
lock each root cause with focused automated regressions before any full desktop
reverification.

### Dependencies

- The Plan 10 implementation baseline has matching A1/A2 evidence, Orchestrator
  acceptance decisions, checked canonical tasks, and accepted batch-scope evidence.
- The Plan 11 structure validator passes and the approved failure report remains
  unchanged as the reproduction baseline.
- Tasks (01A), (01B), (01C), and (01D) have disjoint primary ownership and may run
  independently after the shared Plan 10 prerequisite.

### Scope Boundary

Own only CORS method permission, the existing activation/cache composition path,
the existing Agent prompt/decision postcondition, frontend extraction parsing and
fallback rendering, and their focused tests. Exclude coordinator, persistence,
schema, scoring, provider, infrastructure, security, responsive/mobile, and
unrelated UI changes.

### Tasks

- [x] (01A): Permit existing CV and Job DELETE requests through CORS
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_11.md` > `## Mandatory Batch01 - Root-Cause Functional Repairs` > `(01A)`
  - Source of Truth: `docs/plans/Plan_11.md` > `### Browser DELETE transport` and `## Implementation` items 1-2; `docs/acceptance/full_functional_failure_report.md` > `## F-01 — Desktop CV and Job deletion are blocked by CORS preflight`; `docs/plans/Master_plan.md` > `### 14.1 API rules`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_11.md` > `(01A)` -> task authority
    - source-delete-cors: repository `docs/plans/Plan_11.md` > `### Browser DELETE transport` -> exact middleware requirement
    - failure-f01: repository `docs/acceptance/full_functional_failure_report.md` > `## F-01 — Desktop CV and Job deletion are blocked by CORS preflight` -> reproduction and root-cause evidence
    - cors-owner: repository `backend/app/main.py` > `create_app` -> current explicit origin/method middleware owner
    - validation-delete-cors: repository `docs/plans/Plan_11.md` > `## Verification` > `Backend focused` and `F-01 desktop` -> required evidence
  - Source Requirements:
    - Keep the configured frontend origin, credentials, headers, and Starlette-owned OPTIONS behavior unchanged; make the explicit method allowlist exactly `GET`, `POST`, and `DELETE`.
    - Cover representative existing `/api/jobs/<job-id>` and `/api/cvs/<attachment-id>` DELETE preflights with successful status, echoed configured origin, and advertised DELETE while preserving GET/POST.
    - Do not change either frontend DELETE client, public route, or deletion coordinator unless a new focused failure proves a separate in-scope defect.
  - Dependencies: Accepted Plan 10 baseline; no earlier Plan 11 task.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/main.py`, `backend/tests/integration/test_chat_api.py`
  - Allowed Files: `backend/app/main.py` and `backend/tests/integration/test_chat_api.py` only; exclude API routers, CV/Job deletion services and repositories, frontend, infrastructure, settings, migrations, runtime data, and dependency changes.
  - Agent Work:
    1. Trace `create_app`, all CORS assertions, both public DELETE routes, and their frontend callers/coordinators to confirm F-01 stops at middleware and no shared mutation owner requires editing.
    2. Add failing Job and CV DELETE preflight assertions beside the existing GET/POST CORS contract.
    3. Extend the existing allowlist minimally, then prove representative DELETE and retained GET/POST behavior with final focused/static evidence.
  - Output: Browser preflight permits both already implemented DELETE flows without changing deletion behavior.
  - A1 Outcome: Configured-origin CV and Job DELETE preflights succeed and advertise DELETE while existing GET/POST CORS behavior remains green.
  - A2 Review Focus: Exact allowlist, unchanged origin/credential behavior, both representative preflights, actual route/caller trace, no coordinator or client edit, focused test freshness, and bugfix scope.
  - A3 Batch Evidence: F11-01 and F-01/CVM-009/SJD-013 transport rows plus exclusive CORS ownership evidence.
  - Acceptance:
    - `create_app` configures exactly GET, POST, and DELETE in the explicit method allowlist with the prior origin, credential, and header behavior intact.
    - Both representative DELETE preflights succeed, echo the configured origin, and advertise DELETE; existing GET/POST assertions still pass.
    - No CV/Job deletion route, client, service, repository, graph, or persistence logic changes.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_chat_api.py -q` -> PASS evidence: exit `0` with CV and Job DELETE preflight plus retained GET/POST assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app/main.py tests/integration/test_chat_api.py --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` and changed-path inspection -> PASS evidence: exit `0` and only the two allowed files changed for this task; freshness: final attempt only.
  - Blocked Condition: Missing accepted Plan 10 evidence is `BLOCKED_MISSING_REF`; a route/middleware authority conflict is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/main.py`, `backend/tests/integration/test_chat_api.py`

- [x] (01B): Repair activation-driven CV Manager and saved-JD cache coherence
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_11.md` > `## Mandatory Batch01 - Root-Cause Functional Repairs` > `(01B)`
  - Source of Truth: `docs/plans/Plan_11.md` > `### Activation and cache coherence` and `## Implementation` item 3; `docs/acceptance/full_functional_failure_report.md` > `## F-02 — Saved-JD evaluation currentness stays falsely current after CV activation` and `## F-03 — CV Manager becomes blank after activation while its tab is open`; `docs/plans/Master_plan.md` > `### 10.5 CV Manager reprocessing and deletion`, `### 15.2 Sidebar`, `### 15.6 Observability sidebar boundaries`, and `### 17.5 Explicit saved-JD evaluation flow`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_11.md` > `(01B)` -> task authority
    - source-activation-cache: repository `docs/plans/Plan_11.md` > `### Activation and cache coherence` -> fan-out, generation, retention, and no-evaluation authority
    - failures-f02-f03: repository `docs/acceptance/full_functional_failure_report.md` > `## F-02 — Saved-JD evaluation currentness stays falsely current after CV activation` and `## F-03 — CV Manager becomes blank after activation while its tab is open` -> reproductions and root causes
    - composition-owner: repository `frontend/src/app/App.tsx` and `frontend/src/features/profile/CvSidebar.tsx` -> successful Save Profile signal ownership
    - cache-owners: repository `frontend/src/features/observability/state.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, and `frontend/src/features/jobs/savedJobsState.ts` -> existing reducer/cache/request-order ownership
    - validation-activation-cache: repository `docs/plans/Plan_11.md` > `## Verification` > `Frontend focused` and `F-02/F-03 desktop` -> required evidence
  - Source Requirements:
    - `App.handleProfileSaved` bumps profile refresh, observability activation, and the existing saved-JD invalidation signal exactly once after successful approval.
    - Observability activation invalidation preserves attachment selection and last safe CV rows, invalidates CV/chunk/run/graph currentness, advances a reducer-owned generation, and makes an already-open CV Manager issue one guarded history reload with a truthful loading presentation instead of header-only idle output.
    - Saved-JD invalidation is a reducer signal, not a destructive `ObservabilitySidebar` remount; it preserves selection and safe list/detail data, marks the list and cached selected detail non-current, and forces one list/detail GET when open or lazy refresh on next selection when closed.
    - Server responses remain authoritative for `none | current | stale`. Activation issues no evaluate POST and creates no evaluation row; zero-result save/evaluate invalidation continues to use the same signal.
  - Dependencies: Accepted Plan 10 baseline; no earlier Plan 11 task.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/observability/state.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/test/approval-card.test.tsx`, `frontend/src/test/observability-state.test.tsx`, `frontend/src/test/observability-sidebar.test.tsx`, `frontend/src/test/cv-manager.test.tsx`, `frontend/src/test/saved-jobs-state.test.tsx`
  - Allowed Files: the listed five frontend owners and five focused tests only; allow a narrow prop/type export inside those files, but exclude job parsers/detail presentation owned by (01D), CSS, chat state/SSE, backend, package/dependency files, a new store/cache library, and mobile/responsive work.
  - Agent Work:
    1. Trace every `handleProfileSaved`, `activationKey`, `savedJobsInvalidateKey`, `cv_invalidate_activation`, list/detail load, selected-tab effect, latest-request, and abort caller before editing; reuse existing reducer and successful-data retention patterns.
    2. Add failing composition/reducer/component tests for one three-way activation fan-out, retained CV rows plus loading, automatic open-tab CV history reload, preserved saved-JD selection/data, open-tab list/detail refetch, closed-tab lazy refresh, and zero evaluate requests.
    3. Implement reducer-owned generations/non-current transitions and pass the existing invalidation signal through composition without remounting the sidebar or adding another state owner.
    4. Prove stale/aborted responses cannot win, safe data survives refresh errors, currentness comes only from GET responses, and zero-result invalidation remains functional.
  - Output: One coherent activation event automatically refreshes open CV Manager and saved-JD currentness without blanking safe data or recomputing evaluations.
  - A1 Outcome: Save Profile activation fans out once, an open CV Manager reloads without becoming blank, and saved-JD list/detail refresh to server-derived stale while retaining selection and issuing no evaluate request.
  - A2 Review Focus: Sole composition event, exact increment/refetch counts, reducer ownership, retained loading/error states, open/closed tab behavior, latest-request and abort guards, no remount/second store/automatic evaluation, zero-result compatibility, focused/static evidence, and bugfix scope.
  - A3 Batch Evidence: F11-02/F11-03 and F-02/F-03/SJD-006/SJD-009/FE-008/CVM-001/CVM-005 rows plus activation/cache ownership evidence.
  - Acceptance:
    - One successful Save Profile completion increments all three existing refresh/invalidation signals exactly once; unsuccessful or unrelated turns do not.
    - With CV Manager open, activation retains renderable prior rows or the established skeleton with loading state, automatically performs one fresh history GET, and renders the returned sole-active/archived rows without manual refresh.
    - Saved-JD invalidation preserves selection and last safe list/selected detail, forces one list and selected-detail GET when open, and defers the same refresh until next use when closed.
    - Activation performs no evaluation request and no client-derived stale rewrite; request-order/abort guards and zero-result invalidation remain green.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/approval-card.test.tsx src/test/observability-state.test.tsx src/test/observability-sidebar.test.tsx src/test/cv-manager.test.tsx src/test/saved-jobs-state.test.tsx` -> PASS evidence: exit `0` with exact fan-out, generation, retained-data, automatic-refetch, open/closed-tab, no-evaluate, and request-order assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` and changed-path inspection -> PASS evidence: exit `0` and only allowed composition/state/test owners changed; freshness: final attempt only.
  - Blocked Condition: Missing accepted Plan 10 state owners/evidence is `BLOCKED_MISSING_REF`; conflicting automatic-evaluation or currentness authority is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable Node/npm tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/observability/state.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/test/approval-card.test.tsx`, `frontend/src/test/observability-state.test.tsx`, `frontend/src/test/observability-sidebar.test.tsx`, `frontend/src/test/cv-manager.test.tsx`, `frontend/src/test/saved-jobs-state.test.tsx`

- [x] (01C): Enforce truthful explicitly named save_job execution
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_11.md` > `## Mandatory Batch01 - Root-Cause Functional Repairs` > `(01C)`
  - Source of Truth: `docs/plans/Plan_11.md` > heading “### Truthful named `save_job` execution” and `## Implementation` item 4; `docs/acceptance/full_functional_failure_report.md` > `## F-04 — Agent claims a duplicate URL Job was created without calling a tool`; `docs/plans/Master_plan.md` > `### 12.5 Conversation and tool policy`, `### 12.6 Tool loop limits`, heading “### 13.4 `save_job`”, and `## 20. Failure and Recovery Policy`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_11.md` > `(01C)` -> task authority
    - source-named-save: repository `docs/plans/Plan_11.md` > heading “### Truthful named `save_job` execution” -> exact-name repair/fallback/result authority
    - failure-f04: repository `docs/acceptance/full_functional_failure_report.md` > `## F-04 — Agent claims a duplicate URL Job was created without calling a tool` -> exact initiating request and false-success evidence
    - agent-owner: repository `backend/app/agent/prompt.py` and `backend/app/agent/graph.py` -> existing prompt, decision node, topology, and loop ownership
    - result-owner: repository `backend/tests/integration/test_job_tools.py` -> save/dedupe/ToolResult contract evidence
    - validation-named-save: repository `docs/plans/Plan_11.md` > `## Verification` > `Backend focused` and `F-04 desktop` -> required evidence
  - Source Requirements:
    - Strengthen the existing prompt so an explicit registered write-tool request cannot produce a mutation-success claim before a ToolResult exists.
    - In the existing decision node, narrowly detect the exact registered `save_job` name in the initiating user request and whether it has already been called this turn. If the first decision is plain text, discard it and make exactly one bounded repair decision requiring one valid `save_job` call and no other tool.
    - If repair still omits the required sole call, terminate with fixed truthful no-action text and never persist the model's mutation claim. After execution, derive final mutation narration from validated ToolResult summary/compact outcome so `returned` cannot be described as `created`.
    - Preserve Agent state, one decision node, one ToolNode, registered schemas, durable execution/replay, normal greeting/tool paths, and the six-pass limit. Add the required `ponytail:` comment beside the intentionally narrow exact-name gate and its typed-intent upgrade path.
  - Dependencies: Accepted Plan 10 baseline; no earlier Plan 11 task.
  - User Action: None; automated validation must use injected fakes and existing synthetic fixtures.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/agent/prompt.py`, `backend/app/agent/graph.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/integration/test_job_tools.py`
  - Allowed Files: the listed prompt/graph owners and two focused tests only; exclude Agent state schemas, graph topology/node count, tool registry/schema/implementation, runner/persistence, API/SSE, provider/settings, ingestion/dedupe services, frontend, dependencies, and loop-limit changes.
  - Agent Work:
    1. Trace initiating-message construction, every decision-node exit, tool-call history, ToolMessage/ToolResult parsing, final assistant persistence, replay, save-job outcome vocabulary, and all graph callers before changing shared logic.
    2. Add failing fake-model tests for direct false text, exactly one repaired sole `save_job` call, repair refusal/invalid call, ToolResult-derived `returned` narration, already-called behavior, and unaffected greeting/normal-tool/loop-limit paths; retain exact dedupe integration coverage.
    3. Strengthen the prompt and implement the smallest decision-node postcondition without state or topology changes, including the source-required `ponytail:` limitation comment.
    4. Prove no discarded false claim is persisted, no repair executes another tool, one save call remains durable/replay-safe, and the final outcome agrees with validated ToolResult.
  - Output: Explicitly named `save_job` turns execute one durable truthful mutation path or return fixed no-action text.
  - A1 Outcome: A named save_job request can no longer complete with unsupported mutation prose: it executes exactly one valid save_job call and reports ToolResult outcome, or truthfully reports that no action occurred.
  - A2 Review Focus: Exact initiating-turn/name gate, first-response discard, one bounded repair, sole-tool enforcement, fixed fallback, ToolResult validation/projection, `returned` versus `created` truth, persistence/replay callers, required `ponytail:` comment, unchanged topology/state/limit, focused evidence, and bugfix scope.
  - A3 Batch Evidence: F11-04 and F-04/CHAT-005/JD-003 truthfulness, durable-call, dedupe, and Agent-topology rows.
  - Acceptance:
    - A first plain-text response to the report's exact named request is discarded and followed by at most one repair decision; only one valid `save_job` call may execute.
    - A repair that omits the required sole call produces fixed truthful no-action text, persists no created/reused claim, and invokes no tool.
    - A successful tool path derives final wording from validated ToolResult summary/compact outcome; exact duplicate `returned` preserves Job identity/count and is never narrated as newly created.
    - Greetings, unnamed normal turns, other valid tools, durable replay, one-node/one-ToolNode topology, Agent state shape, and six-pass limit remain unchanged.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_agent_graph.py tests/integration/test_job_tools.py -q` -> PASS evidence: exit `0` with direct-text repair, refusal, sole-call, ToolResult projection, exact dedupe, replay, unaffected-path, and topology assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app/agent/prompt.py app/agent/graph.py tests/unit/test_agent_graph.py tests/integration/test_job_tools.py --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` and changed-path/topology inspection -> PASS evidence: exit `0`, only allowed files changed, one decision node/one ToolNode remain, and the `ponytail:` comment is present; freshness: final attempt only.
  - Blocked Condition: Missing accepted Agent/ToolResult baseline evidence is `BLOCKED_MISSING_REF`; conflicting tool-result or persistence authority is `BLOCKED_SOURCE_CONFLICT`; a truthful root fix requiring state, topology, registry, runner, or other out-of-bound changes is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/agent/prompt.py`, `backend/app/agent/graph.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/integration/test_job_tools.py`

- [x] (01D): Accept and render valid empty extraction summaries
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_11.md` > `## Mandatory Batch01 - Root-Cause Functional Repairs` > `(01D)`
  - Source of Truth: `docs/plans/Plan_11.md` > `### Empty extraction summary parity` and `## Implementation` item 5; `docs/acceptance/full_functional_failure_report.md` > `## F-05 — Unscorable saved-JD detail is rejected by the frontend parser`; `docs/plans/Master_plan.md` > `### 7.4 Job extraction`, `### 7.7 Saved JD and evaluation views`, and `### 15.2 Sidebar`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_11.md` > `(01D)` -> task authority
    - source-empty-summary: repository `docs/plans/Plan_11.md` > `### Empty extraction summary parity` -> parser/fallback authority
    - failure-f05: repository `docs/acceptance/full_functional_failure_report.md` > `## F-05 — Unscorable saved-JD detail is rejected by the frontend parser` -> valid payload and root-cause evidence
    - parser-owner: repository `frontend/src/features/jobs/types.ts` > `parseJobPostExtraction` -> strict extraction parser owner
    - view-owner: repository `frontend/src/features/jobs/SavedJobDetail.tsx` > `SavedJobDetailView` -> selected-detail presentation owner
    - validation-empty-summary: repository `docs/plans/Plan_11.md` > `## Verification` > `Frontend focused` and `F-05 desktop` -> required evidence
  - Source Requirements:
    - Keep backend `JobPostExtraction.summary` unchanged as a required string that may be empty; do not migrate or rewrite stored rows.
    - Keep extraction key/type/forbidden-field validation strict while accepting empty or whitespace-only string summary values; do not relax the independent non-empty MatchResult summary contract.
    - Render concise `No summary available` fallback when the accepted extraction summary trims empty while keeping metadata, source, quality, and controlled `JOB_NOT_SCORABLE` behavior visible.
  - Dependencies: Accepted Plan 10 baseline; no earlier Plan 11 task.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/SavedJobDetail.tsx`, `frontend/src/test/saved-jobs-api.test.ts`, `frontend/src/test/saved-jobs-panel.test.tsx`
  - Allowed Files: the listed parser/detail owners and two focused tests only; exclude backend schemas/models/data, MatchResult parser/formatters, saved-JD state/cache owned by (01B), CSS, package/dependency files, and unrelated panels.
  - Agent Work:
    1. Trace backend `JobPostExtraction.summary`, saved-detail transport, `parseJobPostExtraction`, the separate MatchResult parser, and every detail renderer/test before editing.
    2. Add failing parser tests for empty/whitespace string acceptance plus retained non-string/extra-key rejection, and panel tests for fallback with other metadata/source still visible.
    3. Replace only the extraction-summary non-empty assertion with the existing strict string check and add the concise view fallback without changing stored or returned data.
    4. Prove MatchResult empty summary remains rejected and controlled unscorable evaluation behavior is unchanged.
  - Output: Every backend-valid processed-unscorable detail parses and renders a useful fallback instead of an invalid-payload alert.
  - A1 Outcome: Saved-JD extraction accepts an empty string summary and renders No summary available while retaining strict payload validation and the non-empty MatchResult contract.
  - A2 Review Focus: Exact extraction-versus-MatchResult boundary, strict key/type/forbidden-field checks, whitespace fallback, retained metadata/source/quality, no backend/data/state/CSS changes, focused/static evidence, and bugfix scope.
  - A3 Batch Evidence: F11-05 and F-05/JD-005/SJD-003 parser-parity, graceful-detail, and schema-preservation rows.
  - Acceptance:
    - `parseJobPostExtraction` accepts empty and whitespace-only string summaries but still rejects missing/non-string summary, malformed fields, forbidden fields, and extra keys.
    - `SavedJobDetailView` displays `No summary available` for a summary that trims empty while rendering the remaining extraction metadata and source.
    - The MatchResult parser still rejects an empty summary; backend schemas, migrations, persisted rows, and `JOB_NOT_SCORABLE` handling are unchanged.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx` -> PASS evidence: exit `0` with empty/whitespace extraction parsing, strict rejection, fallback rendering, retained metadata, and MatchResult non-empty assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` and changed-path inspection -> PASS evidence: exit `0` and only the four allowed frontend files changed; freshness: final attempt only.
  - Blocked Condition: A backend string-contract conflict is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable Node/npm tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/SavedJobDetail.tsx`, `frontend/src/test/saved-jobs-api.test.ts`, `frontend/src/test/saved-jobs-panel.test.tsx`

## Mandatory Batch02 - Final Desktop Reverification

### Goal

Run every focused/full/static/build gate and reproduce F-01 through F-05 from fresh
output on a named disposable desktop stack, producing sanitized immutable evidence
without repairing product code in the evidence task.

### Dependencies

- Tasks (01A), (01B), (01C), and (01D) each have matching accepted final A1/A2
  evidence, checked canonical markers, and an accepted Batch01 A3 scope audit.
- A locally usable ignored root `.env`, Docker, a desktop browser, required ports,
  and any configured provider access are available without sharing secret values.

### Scope Boundary

Own final-attempt command execution, desktop-only browser/network/log observation,
sanitized A1 evidence, disposable-project teardown, and restoration of any
user-approved normal stack. Edit no repository file. Exclude repairs, acceptance
report rewrites, README updates, security tests, mobile/responsive checks, personal
data, and user-volume deletion.

### Tasks

- [ ] (02A): Prove all five desktop failures are resolved on final accepted code
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_11.md` > `## Mandatory Batch02 - Final Desktop Reverification` > `(02A)`
  - Source of Truth: `docs/plans/Plan_11.md` > `## Verification` and `## Completion Contract`; `docs/acceptance/full_functional_failure_report.md` > `## F-01` through `## F-05`; `docs/acceptance/full_functional_test_matrix.md` > `## Failure Evidence Rules`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` and `## 27. Definition of Done`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_11.md` > `(02A)` -> task authority
    - validation-plan11: repository `docs/plans/Plan_11.md` > `## Verification` -> complete command and desktop observation matrix
    - reproduction-failures: repository `docs/acceptance/full_functional_failure_report.md` > `## F-01` through `## F-05` -> original procedures and expected repaired behavior
    - evidence-rules: repository `docs/acceptance/full_functional_test_matrix.md` > `## Failure Evidence Rules` -> sanitized failure/evidence boundary
    - runtime-owner: repository `README.md` > setup/startup commands and `infrastructure/docker-compose.yml` -> existing three-service runtime
    - structure-validator: repository `docs/plans/Plan_11.md` > `## Verification` > `Plan structure` -> contiguous-plan validation authority
  - Source Requirements:
    - Run the focused and full Ruff, mypy, pytest, Vitest, ESLint, TypeScript, Vite build, health, plan-structure, and scope-hygiene gates on final accepted code.
    - In a named disposable Compose project, rerun the original five desktop reproductions at `http://localhost:5173` with only synthetic/public test inputs and inspect UI state, browser requests, console, and sanitized backend logs.
    - Prove both DELETE requests reach accepted coordinators; saved-JD becomes server-derived stale without evaluate POST; open CV Manager loads then renders rows; named duplicate `save_job` has one truthful durable execution or no-action response; and valid empty-summary detail renders fallback.
    - Tear down only the verified disposable project/volumes and restore any normal stack paused with prior user approval. Record evidence only in the assigned A1 report and do not edit product, tests, plans, acceptance reports, README, config, or runtime secrets.
  - Dependencies: All Batch01 task IDs and the Batch01 A3 audit accepted.
  - User Action: Before desktop validation, provide a usable ignored root `.env` and Docker/browser/provider prerequisites without sharing values; ensure ports 5173, 8000, 7474, and 7687 are free or explicitly approve pausing and later restoring the known normal Compose project. Missing setup or an unknown project/volume target blocks destructive teardown.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: None in the repository; final evidence belongs only in the assigned `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md` report.
  - Allowed Files: no repository files; A1 may write only its assigned immutable A1 report under Artifact Root. Exclude product/tests/config/docs changes, `.env`, runtime data, prior evidence, screenshots with personal data, and task checkbox changes by A1.
  - Agent Work:
    1. Confirm matching final accepted evidence for all Batch01 tasks, inspect final changed paths, and run focused then full backend/frontend/static/build/plan gates without repairing failures.
    2. Verify target project name and free ports, start `jobagent-plan11-smoke` from the existing Compose file, confirm three-service/API health, and use only synthetic CV fixtures plus public test JD inputs.
    3. Execute F-01, F-02/F-03, F-04, and F-05 exactly at desktop size; record sanitized status/method/count/code/currentness observations from the frontend, browser network/console, durable activity, and backend logs.
    4. Tear down only `jobagent-plan11-smoke` and its disposable volumes after verifying the resolved project name, restore any normal stack using the user's previously approved command, rerun health if restored, and write the assigned report without repository edits.
  - Output: Fresh sanitized automated and desktop evidence that all five Plan 11 failures are resolved with no scope expansion.
  - A1 Outcome: Final accepted code passes every required gate and all five original desktop reproductions in a disposable stack, with truthful sanitized evidence and no repository edit.
  - A2 Review Focus: Final-attempt freshness, accepted Batch01 provenance, all command exits, exact five reproductions, request methods/counts, durable ToolResult truth, no automatic evaluation, nonblank loading states, parser fallback, console/log observations, sanitized evidence, verified safe teardown/restoration, no repository edit, and bugfix hard gates.
  - A3 Batch Evidence: F11-01 through F11-06 final validation, integration, desktop regression, scope, secret/data hygiene, and local-demo readiness rows.
  - Acceptance:
    - Every focused/full/static/build/plan command passes from final accepted output with no real provider call in automated tests.
    - F-01 shows successful DELETE preflights and actual frontend CV/Job DELETE requests reaching the backend, with successful rows removed and safe remaining selection/empty state.
    - F-02/F-03 show automatic list/detail and CV-history GETs after activation, server-derived stale without evaluate POST/new evaluation, and retained loading followed by correct rows rather than header-only output.
    - F-04 shows exactly one Save Job durable activity/tool execution for the report's named duplicate request and unchanged Job identity/count with `returned` narration, or the fixed truthful no-action response with zero execution and no success claim.
    - F-05 renders extraction metadata and `No summary available` for the valid empty-summary unscorable Job without invalid-payload error; `JOB_NOT_SCORABLE` remains truthful if evaluation is attempted.
    - Evidence contains no secret, personal/raw document content, prompt/provider transcript, query, path, database, or unsupported claim; only the named disposable volumes are removed and any paused normal stack is restored.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_agent_graph.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py -q` -> PASS evidence: exit `0` with all focused backend repair assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run src/test/approval-card.test.tsx src/test/observability-state.test.tsx src/test/observability-sidebar.test.tsx src/test/cv-manager.test.tsx src/test/saved-jobs-api.test.ts src/test/saved-jobs-state.test.tsx src/test/saved-jobs-panel.test.tsx` -> PASS evidence: exit `0` with all focused frontend repair assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental; py -3.13 -m pytest -q` -> PASS evidence: all exit `0` without real provider calls; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` -> PASS evidence: exit `0`, `valid: true`, contiguous Plans 1-11, and no errors; freshness: final attempt only.
    - Required: `docker compose -p jobagent-plan11-smoke --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180; Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS evidence: the named disposable frontend, backend, and Neo4j services are healthy and API `overall` is `available`; freshness: current Compose run only.
    - Required: execute F-01 through F-05 from `docs/acceptance/full_functional_failure_report.md` at `http://localhost:5173`, excluding mobile/security checks -> PASS evidence: sanitized current-run browser/network/console/durable/backend observations satisfying every Acceptance bullet; freshness: current Compose run only.
    - Required: after verifying the resolved project name, run `docker compose -p jobagent-plan11-smoke --env-file .env -f infrastructure/docker-compose.yml down --volumes` and restore any user-approved normal stack -> PASS evidence: only named disposable containers/networks/volumes are removed and the prior normal health state is restored; freshness: current run only.
    - Required: `git diff --check; git status --short` plus inspection of changed paths, new dependencies/stores/nodes/migrations, tracked secrets/data, and security/mobile scope -> PASS evidence: diff check exits `0`, only accepted Plan 11 repair/task and pre-existing user-owned documentation paths appear, and (02A) itself changed no repository file; freshness: final attempt only.
  - Blocked Condition: Missing accepted Batch01/A3 evidence is `BLOCKED_MISSING_REF`; missing/invalid `.env`, provider access, occupied ports without pause approval, or unknown restore/teardown target is `BLOCKED_USER_ACTION`; unavailable Docker/browser/Python/Node/runtime is `BLOCKED_ENVIRONMENT`; unavailable browser or teardown permission is `BLOCKED_PERMISSION`; any required gate/reproduction failure needing a repository repair is `BLOCKED_SCOPE_CONFLICT` and must return to the owning Batch01 task rather than be fixed here.
  - Files: None in the repository; assigned `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md` only.
