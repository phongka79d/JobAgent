# Plan_11: Desktop Functional Reliability Repairs

## Objective

Resolve all five verified desktop failures in
`docs/acceptance/full_functional_failure_report.md` without changing JobAgent's
product scope or architecture. The completed phase must make frontend CV and Job
deletion reach the existing backend coordinators, keep CV Manager and saved-JD
currentness coherent after approved activation, prevent a named `save_job` request
from reporting an unexecuted mutation, and render valid processed-unscorable Job
detail payloads.

The repairs are complete only when each original reproduction passes, the matching
backend/frontend regression suites remain green, and a fresh desktop Compose run
shows no false success, blank post-activation panel, or manual-refresh dependency.

## Source of Truth

- `docs/acceptance/full_functional_failure_report.md`: approved 2026-07-18
  failure evidence `F-01` through `F-05`.
- `docs/acceptance/full_functional_test_matrix.md`: original functional test IDs
  and expected behavior for the affected surfaces.
- `docs/plans/Master_plan.md`: `## 6. SQLite Database Contract`,
  `## 7. Pydantic Data Contracts`, `## 12. Agent Architecture`,
  `## 13. Agent-Facing Tool Contracts`, `## 14. Public FastAPI Boundary`,
  `## 15. Frontend UX Plan`, `## 17. Embedding and Retrieval`,
  `## 20. Failure and Recovery Policy`, and `## 24. Local Testing Strategy`.
- `docs/plans/Plan_10.md`: implemented saved-JD, evaluation-currentness,
  exact-deletion, sidebar-cache, and zero-result recovery baseline.

- **Approved change:** the current user explicitly requested a plan that resolves
  every failure in the failure report.
- **Change type:** `bugfix`.
- **Master impact:** `none`. The Master already requires both DELETE routes,
  activation-driven cache invalidation without automatic evaluation, tool-backed
  Job mutation, truthful failures, and `JobPostExtraction.summary: str`. This
  phase restores those contracts and changes no architecture, schema, stack,
  deployment rule, public payload, or product boundary.

## Master Requirement Coverage

| Requirement ID | Failure/test source | Master section | Owned outcome | Verification evidence |
|---|---|---|---|---|
| F11-01 | F-01; CVM-009, SJD-013 | 14, 14.1 | Browser preflight permits the implemented CV and Job DELETE requests; existing coordinators remain sole mutation owners. | CORS integration test plus desktop confirmed-delete smoke. |
| F11-02 | F-02; SJD-006, SJD-009 | 6.2, 15.6, 17.5 | Approved CV/profile activation invalidates and reloads saved-JD list/selected detail so server-derived `stale` appears without evaluating automatically. | Frontend composition/state tests, request-method assertions, and desktop activation smoke. |
| F11-03 | F-03; FE-008, CVM-001, CVM-005 | 10.5, 15.2, 15.6 | An open CV Manager transitions through truthful loading and automatically renders the post-activation rows. | Reducer/component tests and desktop Make active smoke. |
| F11-04 | F-04; CHAT-005, JD-003 | 12.5-12.6, 13.4, 20 | An explicit named `save_job` request executes one durable tool call or reports that no mutation occurred; duplicate outcome comes from ToolResult. | Agent graph/prompt tests, existing dedupe tests, and durable desktop run evidence. |
| F11-05 | F-05; JD-005, SJD-003 | 7.4, 7.7, 15.2 | Frontend detail parsing accepts an empty extraction summary allowed by the backend and renders a graceful fallback for unscorable Jobs. | Parser/panel tests plus desktop unscorable-detail smoke. |
| F11-06 | All five failures | 24, 27 | Focused and full local gates pass with only in-scope repairs. | Ruff, mypy, pytest, Vitest, ESLint, TypeScript, Vite build, Compose health, and plan validation. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Plan_10 | Current seven-tool Agent, saved-JD state/parsers/panels, CV Manager state, and deletion services | Run focused current tests and reproduce each reported failing boundary before repair. |
| Failure QA | Failure-only report and 113-case matrix | Preserve both documents as evidence inputs; do not rewrite a failure as passing history. |
| Backend runtime | Public DELETE routes, ToolResult persistence/replay, Job exact dedupe, and valid empty-summary payload | Trace all callers before changing shared middleware, graph decisions, or schemas. |
| Frontend runtime | `handleProfileSaved`, activation/invalidation keys, sidebar-local caches, and strict parsers | Confirm request-order guards and successful-data retention remain reusable. |
| Local environment | Desktop frontend `localhost:5173`, backend `localhost:8000`, synthetic data, and preserved developer volumes | Use a named disposable project for destructive verification and restore the normal stack afterward. |

## Scope

- Extend the existing CORS method allowlist only for the public DELETE methods
  already consumed by the frontend.
- Repair the one approved-profile activation signal so profile, observability, and
  evaluation-currentness owners all invalidate once.
- Make the selected observability panel consume activation invalidation and reload
  without losing every renderable state.
- Preserve saved-JD selection and last safe data while list/detail currentness is
  refreshed from the server; do not recompute an evaluation.
- Add a bounded deterministic postcondition for an explicitly named `save_job`
  request while preserving the one decision node, one ToolNode, and six-pass limit.
- Align the saved-JD extraction parser and detail presentation with the existing
  backend/Master string contract.
- Add focused regression tests and rerun the five desktop reproductions.

## Out of Scope

- Security, penetration, abuse, authorization, or new origin-policy testing.
- Mobile, narrow-viewport, drawer, or responsive-layout implementation and manual
  acceptance. Existing full-suite tests may remain, but this phase adds no mobile
  evidence or mobile-specific change.
- Changes to CV/Job deletion coordinators, graph deletion semantics, SQLite/Alembic,
  evaluation hashing/scoring, or automatic evaluation.
- A second frontend store, global cache library, new endpoint, worker, queue, Agent,
  classifier model, generic claim detector, or provider/model change.
- Tightening the backend summary schema or rewriting persisted unscorable Jobs.
- Product fixes outside `F-01` through `F-05`, security findings, or task/product
  execution during this planning phase.

## Target Directory Structure

```text
backend/
  app/
    main.py
    agent/
      prompt.py
      graph.py
  tests/
    unit/test_agent_graph.py
    integration/
      test_chat_api.py
      test_job_tools.py
frontend/src/
  app/App.tsx
  features/
    profile/CvSidebar.tsx
    observability/
      state.ts
      ObservabilitySidebar.tsx
    jobs/
      savedJobsState.ts
      types.ts
      SavedJobDetail.tsx
  test/
    approval-card.test.tsx
    observability-state.test.tsx
    observability-sidebar.test.tsx
    cv-manager.test.tsx
    saved-jobs-api.test.ts
    saved-jobs-state.test.tsx
    saved-jobs-panel.test.tsx
docs/
  acceptance/
    full_functional_failure_report.md   # immutable failure input
    full_functional_test_matrix.md      # regression IDs/procedures
  plans/
    Plan_10.md                          # terminal boundary changed to handoff only
    Plan_11.md
```

Use equivalent existing test owners when a listed assertion already belongs there.
Do not create a parallel cache, parser, CORS, Agent, or acceptance-report owner.

## Technical Specifications

### Browser DELETE transport

- In `backend/app/main.py`, keep the configured frontend origin and credential
  behavior unchanged and make the explicit method allowlist exactly cover
  `GET`, `POST`, and `DELETE`. Starlette owns `OPTIONS` preflight handling.
- Add one focused CORS contract covering representative Job and CV DELETE
  preflights. Each must return a successful preflight, echo the configured origin,
  and advertise `DELETE`; existing GET/POST behavior remains green.
- Do not alter frontend DELETE clients or either deletion coordinator unless a new
  failing test proves a separate defect.

### Activation and cache coherence

- `App.handleProfileSaved` remains the sole successful Save Profile composition
  event. It must bump profile refresh, observability activation, and the existing
  saved-JD invalidation signal exactly once.
- Extend observability state with one activation generation (or the equivalent
  existing reducer-owned token). `cv_invalidate_activation` invalidates the
  CV/chunk/run/graph resources, preserves attachment selection, retains last safe CV
  rows while a refresh is pending, and advances that generation.
- The lazy-load effect consumes the generation as well as tab/selection. If CV
  Manager is open, it issues one fresh history request and renders either retained
  rows with a loading indicator or the established skeleton before the response;
  `idle` header-only output is forbidden. Request-order and abort guards still win.
- Treat `savedJobsInvalidateKey` as an invalidation signal rather than a destructive
  component remount. Add one saved-JD reducer action that marks list and cached
  selected detail non-current while preserving selection and safe data. When the tab
  is open, force one list and selected-detail GET; when closed, keep lazy loading and
  refresh on next selection.
- Server responses remain authoritative for `none|current|stale`. Activation must
  issue no evaluate POST and create no `job_evaluations` row. The same signal must
  continue to handle zero-result save/evaluate invalidation.

### Truthful named `save_job` execution

- Strengthen the existing prompt: a request that explicitly names a registered write
  tool cannot be answered with a mutation-success claim before a ToolResult exists.
- In the existing decision node, detect the exact registered `save_job` name in the
  initiating user request and whether that tool has already been called this turn.
  If the first model decision is plain text, discard it and perform exactly one
  bounded repair decision requiring one valid `save_job` call and no other tool.
- If the repair still omits the required call, terminate with fixed truthful
  no-action text; never persist the model's created/reused claim. After the tool
  returns, project the final mutation outcome from the validated ToolResult summary
  and compact outcome, so `returned` cannot be narrated as a new Job.
- Reuse the existing ToolNode, tool schema, durable execution/replay, and loop count.
  Do not add state fields, a second graph node, intent classifier, or unbounded retry.
- Add a `ponytail:` comment beside the exact-name gate: it is intentionally narrow;
  if natural-language mutation reliability later remains insufficient, replace it
  with a typed mutation-intent contract rather than expanding keyword heuristics.

### Empty extraction summary parity

- Keep backend `JobPostExtraction.summary` unchanged as a required string that may
  be empty. No migration or stored-row rewrite is allowed.
- In `frontend/src/features/jobs/types.ts`, continue strict key/type/forbidden-field
  validation but accept an empty string for extraction summary. Do not relax the separate
  non-empty MatchResult summary contract.
- In `SavedJobDetail.tsx`, display a concise fallback such as
  `No summary available` when the accepted summary trims empty. Other extracted
  metadata, source, quality, and controlled `JOB_NOT_SCORABLE` behavior remain
  visible and unchanged.

## Implementation

1. Run the focused baseline and capture the five expected failures. Search all CORS,
   activation, cache, graph-decision, ToolResult, extraction-parser, and detail-view
   callers before editing.
2. Add failing DELETE preflight assertions, then extend the existing method allowlist
   minimally.
3. Add failing reducer/composition tests for saved-JD current-to-stale refresh and an
   open CV Manager activation. Implement the single activation fan-out, cache
   invalidation generations, retained loading state, and automatic refetch.
4. Add failing Agent tests for direct false text, one repaired `save_job` call,
   repair refusal, ToolResult-derived duplicate narration, and unaffected greeting/
   normal tool paths. Implement prompt and graph postconditions in existing owners.
5. Add failing empty-summary parser/panel tests, then align the frontend parser and
   fallback rendering without changing backend persistence.
6. Run focused backend/frontend suites and fix root regressions across every caller;
   do not add compatibility duplication.
7. Run full static/test/build gates and the shared plan validator.
8. Start a named disposable desktop stack, rerun only the five failure reproductions,
   inspect frontend state/network and sanitized backend logs, then tear down only the
   disposable project and restore the normal stack without deleting user volumes.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Backend focused | `Set-Location backend; py -3.13 -m pytest tests/unit/test_agent_graph.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py -q` | DELETE preflight, bounded named-tool repair, truthful fallback/result, and exact duplicate reuse pass. |
| Frontend focused | `Set-Location frontend; npm test -- --run src/test/approval-card.test.tsx src/test/observability-state.test.tsx src/test/observability-sidebar.test.tsx src/test/cv-manager.test.tsx src/test/saved-jobs-api.test.ts src/test/saved-jobs-state.test.tsx src/test/saved-jobs-panel.test.tsx` | Activation refetch/currentness, nonblank CV Manager, empty-summary parse/fallback, and existing request guards pass. |
| Backend full/static | `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental; py -3.13 -m pytest -q` | All backend tests pass with no real provider call. |
| Frontend full/build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Full desktop-relevant regressions and existing suite/build pass. |
| Local services | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180`; then `Invoke-RestMethod http://127.0.0.1:8000/api/health` | Frontend, backend, SQLite/filesystem, and Neo4j are available. |
| F-01 desktop | Run both sanitized DELETE preflights, then confirm one archived-CV and one Job deletion in the UI. | Preflights advertise DELETE; actual requests reach backend and successful rows disappear safely. |
| F-02/F-03 desktop | Keep saved-JD then CV Manager open across approved CV activation. | Automatic GETs occur; saved evaluation becomes stale without POST evaluate, and CV Manager shows loading then swapped rows rather than a blank panel. |
| F-04 desktop | Save one public test URL, then send the report's exact duplicate `save_job` request. | Exactly one Save Job activity/durable tool execution reports existing/returned; Job ID/count is unchanged and no unsupported success text appears. |
| F-05 desktop | Open the processed-unscorable public test Job whose extraction summary is empty. | Detail renders metadata plus fallback; no invalid-payload error; evaluation may still truthfully return `JOB_NOT_SCORABLE`. |
| Scope hygiene | `git diff --check`; inspect `git status --short` and changed paths. | No security/mobile work, migration, new dependency/store/Agent, raw data, secret, or unrelated fix. |
| Plan structure | `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` | Plans are contiguous through Plan 11; Plan 10 hands off normally and only Plan 11 is terminal. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Plans 1-9 | Local runtime, Agent/tool persistence, CV lifecycle, graph, observability, and release baselines | Historical ownership remains unchanged. |
| Plan_10 | Saved-JD APIs/state/UI, revision-keyed evaluations, exact Job deletion, and terminal product baseline | Repairs reuse these owners and do not redesign them. |
| Functional QA | Failure report and full test matrix | The five documented reproductions are the complete authorized repair scope. |
| Current user authorization | 2026-07-18 request to resolve all failures | Authorizes this bugfix plan and the required Plan 10 terminal-to-handoff conversion. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Fresh portfolio review | Updated Plan 10 boundary plus `Plan_11.md` | Shared structural validator passes and all five repair contracts are independently reviewable. |
| `task-writing-agent` after approval | `docs/tasks/task_11.md` | One authoritative task maps F11-01 through F11-06 to implementation and A1/A2/A3 evidence. |
| Future A1/A2/A3 execution | Focused repair sequence and regression boundary | Automated/full/desktop evidence proves all five failures resolved without scope expansion. |

## Completion Contract

Plan 11 is complete only when all five original desktop reproductions pass from
current output: both frontend deletes reach their accepted coordinators; approved
activation refreshes saved-JD currentness without recomputation; an open CV Manager
never becomes header-only; an explicitly named duplicate `save_job` request has one
durable truthful ToolResult or a truthful no-action response; and every valid
processed-unscorable detail renders despite an empty extraction summary. Focused and
full local gates, Compose health, desktop evidence, scope hygiene, and the contiguous
plan validator must pass. Security and mobile testing remain excluded, and no Master
amendment, schema migration, new product capability, task file, or product code is
created by this planning phase. The required next action is a fresh full portfolio
review before task writing or execution.
