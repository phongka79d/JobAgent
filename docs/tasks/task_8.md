# JobAgent Plan 8 Execution Tasks

## Purpose

Translate `docs/plans/Plan_8.md` into the mandatory implementation chain for immutable archived-CV history, deterministic CV chunks, bounded read-only observability APIs and graph state, and the accessible sidebar inspector. Preserve the single-user local MVP, existing profile/chat workflows, SQLite source of truth, and Neo4j as a derived index.

## Project Context Notes

- Root `README.md` was read completely before derivation. It defines React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, ShopAIKey, root-only `.env`, and current backend/frontend/Compose commands.
- Primary authority is `docs/plans/Plan_8.md`; it names `docs/superpowers/specs/2026-07-16-observability-sidebar-design.md` as the approved supporting design.
- No nested `AGENTS.md` was found. User rules apply: search/reuse before writing, inspect callers, keep modules focused, avoid duplication, and repair root behavior.
- Verified owners are attachment model/repository, `profile_approval`, `profile_extraction`, `attachment_resolve`, chat history, graph consistency/driver modules, FastAPI routes, `CvSidebar`, `App.tsx`, and profile API/types. Observability remains outside the Agent graph and chat SSE reducer.
- The active migration tree is `backend/migrations/versions/`; Plan 8's target structure names `backend/alembic/versions/`. This material path conflict is a gate in `(01A)`: never create a second migration chain.
- `docs/acceptance/observability_sidebar_checklist.md` and Plan 8 target files are absent. Reuse existing helpers, fixtures, fakes, and API patterns.
- Root `.env` is user-managed. Do not read, print, copy, or commit its values. Automated tests use fakes; only the final synthetic local smoke may use configured local services.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_8.md`.
- Supporting: `docs/superpowers/specs/2026-07-16-observability-sidebar-design.md`.
- Context only: `README.md`, repository owners, `infrastructure/docker-compose.yml`, and Plan 7 test conventions.

### Source Section Index

- `Plan_8.md` > `## Objective`, `## Prerequisites`, `## Scope`, and `## Out of Scope` -> outcome, prerequisites, exclusions.
- `Plan_8.md` > `## Target Directory Structure` -> focused paths.
- `Plan_8.md` > `### Persistence And Extraction` -> archive/chunk/transaction rules.
- `Plan_8.md` > `### Read-Only API Contract` -> endpoints, cursors, redaction, graph rules.
- `Plan_8.md` > `### Frontend State And Interaction` -> state, cache, accessibility, fallback.
- `Plan_8.md` > `### Ownership And Safety`, `## Implementation`, `## Verification`, and `## Completion Contract` -> boundaries, validation, gate.
- Supporting design > `## User Experience`, `## Architecture`, `## Data Contracts`, `## Safety And Privacy`, and `## Verification` -> tab UX, read isolation, redaction, focused evidence.

### Approved Architecture and Constraints

- Preserve React/Astryx -> FastAPI -> one LangGraph Agent -> focused services/repositories/adapters, SQLite truth, and rebuildable derived Neo4j.
- Observability is bounded, typed, read-only, and never mutates SQLite/files/Neo4j/chat/Agent/tools/rebuild or exposes arbitrary Cypher.
- Archived CVs are immutable inspection records, not selectable profile versions. Do not expose raw PDF except retained-file stream, paths, raw documents, embeddings, prompts, checkpoints, provider data, tool arguments, stacks, or secrets.
- Reuse current cursor/error/graph/route/test patterns. Do not add another state store, visualization dependency, worker, queue, authorization system, or graph model.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Retained CV history and canonical extraction chunks | (01A) | Plan 7 baseline and migration-path resolution |
| Batch02 | Source/derived observability read contracts | (02A), (02B) | Batch01 |
| Batch03 | Accessible lazy sidebar inspector | (03A) | Batch02 |
| Batch04 | Synthetic direct smoke and final regression evidence | (04A) | Batch03 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes, and writes only `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md`.
- A2 reviews one executed task, writes only `.agent/<plan-id>/<run-id>/report/a2/<batch-id>/<task-id>/A2-a<attempt>.md`, and the Orchestrator checks the canonical checkbox only after `ACCEPTED`.
- A3 runs only after all task markers and matching A1/A2/Orchestrator acceptance evidence exist; it writes only `.agent/<plan-id>/<run-id>/report/a3/<batch-id>/A3-a<attempt>.md`.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.
## Mandatory Batch01 - Retained CV and Canonical Chunk Persistence

### Goal

Replace active-CV deletion on approved replacement with immutable archival and persist exact deterministic parsed-text chunks used by successful structured profile extraction.

### Dependencies

- Plan 7 baseline and existing attachment/profile tests are green.
- Before dispatch, Orchestrator records a resolution of Plan 8's `backend/alembic/versions/` target versus configured `backend/migrations/versions/`. A1 must not create a second root.

### Scope Boundary

Own attachment schema/lifecycle, chunk persistence, and direct tests only. Exclude restoration/deletion APIs, historic backfill, observability routes, Agent behavior, provider calls, and frontend work.

### Tasks

- [x] (01A): Archive replaced CVs and persist canonical successful-extraction chunks
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_8.md` > `## Mandatory Batch01 - Retained CV and Canonical Chunk Persistence` > `(01A)`
  - Source of Truth: `docs/plans/Plan_8.md` > `### Persistence And Extraction`, `### Ownership And Safety`, and `## Implementation` items 1-2.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_8.md` > `(01A)` -> task authority
    - source-persistence: repository `docs/plans/Plan_8.md` > `### Persistence And Extraction` -> archive/chunk/transaction contract
    - attachment-owner: repository `backend/app/db/models/attachments.py` and `backend/app/repositories/attachments.py` -> states/transitions
    - approval-owner: repository `backend/app/services/profile_approval.py` -> replacement transaction/cleanup
    - extraction-owner: repository `backend/app/services/profile_extraction.py` -> parsed text/draft transaction
    - validation: repository `docs/plans/Plan_8.md` > `## Verification` -> required focused tests
  - Source Requirements:
    - Archive former active only after profile repointing; retain file, metadata, chunks; never restore as active.
    - Add `archived` without changing existing `staged`/`failed` rows and preserve one active attachment.
    - Store only successful parsed digital-PDF chunks: nonempty, source-ordered, 1200-char maximum, zero overlap, paragraph then whitespace split, preview/char/token/timestamp metadata, exact `"\n\n"` model-input join.
    - Parse/chunk/model/repair/draft-validation failure writes no chunks; historic no-row attachments are unavailable, never backfilled.
  - Dependencies: Recorded migration-path resolution; no earlier task.
  - User Action: None after migration-path resolution; do not disclose `.env`.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: resolved migration `<revision>_add_attachment_text_chunks.py`, `backend/app/db/models/attachments.py`, `backend/app/db/models/attachment_text_chunks.py`, `backend/app/repositories/attachments.py`, `backend/app/repositories/attachment_text_chunks.py`, `backend/app/services/profile_approval.py`, `backend/app/services/profile_extraction.py`, `backend/tests/unit/test_attachment_text_chunks.py`, `backend/tests/unit/test_profile_extraction.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/integration/test_migrations.py`
  - Allowed Files: resolved migration root and listed attachment/profile/test files; exclude API, Agent, tools, graph, frontend, infrastructure, and unrelated migrations.
  - Agent Work:
    1. Search attachment-transition, active-selection, approval-cleanup, duplicate/retry, resolver, and extraction callers; reuse current UUID/time/transaction/storage helpers.
    2. Add one resolved migration, focused model/repository operations, and archive-after-repoint behavior; ensure archived rows are never processable/active.
    3. Add pure chunking and persist the canonical sequence in the existing successful extraction/draft-input transaction.
    4. Add migration/unit/integration cases for retention, active selection, canonical input/order, empty text, rollback/no rows, and historic unavailable data.
  - Output: Replacements retain immutable archived CVs and successful digital-PDF extraction persists its canonical chunk sequence.
  - A1 Outcome: Archived files/chunks remain safe while exactly the chunks passed to structured extraction persist.
  - A2 Review Focus: Migration root, all lifecycle callers, no old-file deletion, state/index invariants, rollback, exact model input, and focused tests; reject restore/backfill/provider/observability scope.
  - A3 Batch Evidence: M8-01/M8-02 migration, lifecycle, chunk-repository, and extraction-transaction evidence.
  - Acceptance:
    - The resolved migration upgrades the configured database, preserves `staged`/`failed`, accepts `archived`, retains one-active constraint, and creates UUID/attachment-ordinal-unique chunk rows with required metadata/FK.
    - Approved replacement repoints then archives the former active row, retains storage/chunks, leaves one active row, and exposes no restore path.
    - Successful extraction stores nonempty ascending chunks and sends their exact `"\n\n"` join; all specified failures write no rows.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_attachment_text_chunks.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_migrations.py -q` -> PASS: exit `0`; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS: exit `0`; freshness: final attempt only.
  - Blocked Condition: Irreconcilable migration roots are `BLOCKED_SOURCE_CONFLICT`; missing Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: resolved migration, listed attachment/profile modules, and listed focused tests.
## Mandatory Batch02 - Bounded Observability Read Contracts

### Goal

Expose typed cursor-paginated SQLite projections and a bounded derived graph snapshot through read-only APIs with safe errors and no write path.

### Dependencies

- `(01A)` is accepted. Archive/chunk rows and historic-unavailable distinction supply CV history/chunk reads.
- `(02B)` extends `(02A)` schemas/service/router and reuses its safe-error contract.

### Scope Boundary

Own read models, schemas, routes, graph projection, and direct tests. Exclude Agent/tools, chat-history behavior, attachment writes, graph sync/rebuild, and frontend state.

### Tasks

- [ ] (02A): Implement typed read-only CV, chunk, and run observability APIs
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_8.md` > `## Mandatory Batch02 - Bounded Observability Read Contracts` > `(02A)`
  - Source of Truth: `docs/plans/Plan_8.md` > `### Read-Only API Contract`, `### Ownership And Safety`, and `## Implementation` items 3-4.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_8.md` > `(02A)` -> task authority
    - source-api: repository `docs/plans/Plan_8.md` > `### Read-Only API Contract` -> endpoint/cursor/redaction contract
    - cursor-owner: repository `backend/app/services/chat_history.py` and `backend/app/repositories/chat_messages.py` -> cursor/limit-plus-one pattern
    - file-owner: repository `backend/app/api/profile.py` and `backend/app/storage/attachments.py` -> safe retained-file stream
    - run-owner: repository `backend/app/repositories/agent_runs.py` and `backend/app/repositories/tool_executions.py` -> durable run/tool projection
    - validation: repository `docs/plans/Plan_8.md` > `## Verification` -> API test
  - Source Requirements:
    - Provide `1..50` opaque-cursor CV history, chunk list/detail, and run history using stable chronological `limit + 1` pages, `422` malformed cursors, and empty valid post-final pages.
    - Stream retained active/archived PDF only with sanitized filename; use safe errors for unknown/missing file.
    - Full chunk text is selected-detail only; historic no rows return `CHUNKS_UNAVAILABLE`; prohibit paths, JSON PDF bytes, prompts, checkpoints, provider data, stacks, embeddings, tool arguments, and secrets.
  - Dependencies: `(01A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/schemas/observability.py`, `backend/app/repositories/observability.py`, `backend/app/services/observability.py`, `backend/app/api/observability.py`, `backend/app/main.py`, `backend/tests/integration/test_observability_api.py`
  - Allowed Files: listed observability/registration/test files and reusable support fixture only; exclude attachment writes, Agent, tools, graph, frontend, unrelated routers.
  - Agent Work:
    1. Search and reuse cursor/error/file-stream/run-tool/router owners.
    2. Add focused schemas, cross-table repository projections, a no-mutation service, and thin registered routes.
    3. Test page limits/cursors/final pages, selection, file availability, historic unavailable, safe errors, and redaction.
  - Output: Registered retained-CV, selected-chunk, and durable-run inspection APIs with typed pagination/redaction.
  - A1 Outcome: Bounded CV/chunk/run data and retained streams are served without internal exposure or mutation.
  - A2 Review Focus: Thin routes, no write/Agent/provider path, cursor ordering, identifier validation, forbidden-field absence, and all failure branches.
  - A3 Batch Evidence: M8-03 API/cursor/redaction/retained-file/chunk/run evidence.
  - Acceptance:
    - Five non-graph `/api/observability` routes expose only documented fields/codes and cause no mutation.
    - Collections use `limit + 1`, safe cursor behavior, and documented final-page behavior.
    - Retained streams are `application/pdf` with sanitized filename; file/chunk/run responses satisfy safe error/redaction contracts.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_observability_api.py -q` -> PASS: exit `0`; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS: both exit `0`; freshness: final attempt only.
  - Blocked Condition: A needed write/Agent/graph change is `BLOCKED_SCOPE_CONFLICT`; unavailable API tooling is `BLOCKED_ENVIRONMENT`.
  - Files: listed observability modules, registration, and API test.

- [ ] (02B): Add the bounded read-only Neo4j graph snapshot
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_8.md` > `## Mandatory Batch02 - Bounded Observability Read Contracts` > `(02B)`
  - Source of Truth: `docs/plans/Plan_8.md` > `### Read-Only API Contract`, `### Ownership And Safety`, and `## Implementation` items 3-4.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_8.md` > `(02B)` -> task authority
    - source-graph: repository `docs/plans/Plan_8.md` > `### Read-Only API Contract` -> statuses, allowlists, caps, sorting, fallback
    - graph-consistency: repository `backend/app/graph/consistency.py` -> stale contract
    - graph-access: repository `backend/app/graph/driver.py`, `backend/app/graph/retrieval.py`, `backend/app/graph/sync_shared.py` -> current graph conventions
    - validation: repository `docs/plans/Plan_8.md` > `## Verification` -> graph tests
  - Source Requirements:
    - Only `ready | stale | unavailable`; stale/unavailable empty with safe guidance, no active profile ready/empty with `NO_ACTIVE_PROFILE`.
    - Allowlist Candidate/Job/Skill and `HAS_SKILL`/`REQUIRES`/`PREFERS`/`RELATED_TO` only; no arbitrary Cypher or mutation.
    - Cap/order one Candidate, 20 jobs, 40 skills, 100 post-selection sorted edges; return truncation/omitted metadata.
  - Dependencies: `(02A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 5400
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/graph/observability.py`, Batch02 observability schema/service/router, `backend/tests/unit/test_observability_graph.py`, `backend/tests/integration/test_observability_api.py`
  - Allowed Files: `backend/app/graph/observability.py`, `backend/app/schemas/observability.py`, `backend/app/services/observability.py`, `backend/app/api/observability.py`, `backend/tests/unit/test_observability_graph.py`, `backend/tests/integration/test_observability_api.py`, and focused graph fakes only; exclude sync/rebuild/retrieval mutation, Agent/tools, attachment writes, frontend, infrastructure.
  - Agent Work:
    1. Search current driver, consistency, labels/properties, and fakes; add no graph type/write helper.
    2. Implement one allowlisted projection selecting nodes before edges and calculating all metadata.
    3. Extend only Batch02 read contract for `/api/observability/graph`; test states, sorting/caps, allowlists, and no mutation.
  - Output: A cap-aware allowlisted Candidate/Job/Skill graph snapshot.
  - A1 Outcome: The API returns a deterministic snapshot or typed empty safe state without arbitrary graph access.
  - A2 Review Focus: Status vocabulary, no write/rebuild path, query allowlist, cap/order/truncation arithmetic, revision reuse, and tests.
  - A3 Batch Evidence: M8-04 bounded graph/stale/unavailable/no-active/no-mutation evidence.
  - Acceptance:
    - Graph API accepts no query/filter/expansion/mutation input and returns documented schema only.
    - Ready response observes all node/edge caps/order/allowlists/metadata; stale, unavailable, and no-active states match the plan.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_observability_graph.py tests/integration/test_observability_api.py -q` -> PASS: exit `0`; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS: both exit `0`; freshness: final attempt only.
  - Blocked Condition: Required sync/rebuild changes or new graph types are `BLOCKED_SCOPE_CONFLICT`; unavailable fixtures/tooling is `BLOCKED_ENVIRONMENT`.
  - Files: listed graph/observability modules and focused tests.
## Mandatory Batch03 - Accessible Lazy Sidebar Inspector

### Goal

Retain existing CV/profile controls while adding cached Overview, CV history, LLM chunks, Neo4j graph, and Agent runs tabs in an accessible responsive sidebar.

### Dependencies

- `(02A)` and `(02B)` are accepted; their typed API/error contracts are the sole new frontend source.

### Scope Boundary

Own sidebar composition, typed client/state, styles, and focused UI tests. Exclude chat SSE reducer/history reconciliation, upload/approval semantics, backend responses, and graph visualization dependencies.

### Tasks

- [ ] (03A): Compose the observability tabs into the existing accessible CV sidebar
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_8.md` > `## Mandatory Batch03 - Accessible Lazy Sidebar Inspector` > `(03A)`
  - Source of Truth: `docs/plans/Plan_8.md` > `### Frontend State And Interaction`, `## Scope`, and `## Implementation` items 5-6; supporting design > `## User Experience`, `## Architecture`, `## Data Contracts`, and `## Verification`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_8.md` > `(03A)` -> task authority
    - source-sidebar: repository `docs/plans/Plan_8.md` > `### Frontend State And Interaction` -> state/cache/accessibility
    - source-design: repository `docs/superpowers/specs/2026-07-16-observability-sidebar-design.md` > `## User Experience` and `## Data Contracts` -> tabs/privacy
    - sidebar-owner: repository `frontend/src/features/profile/CvSidebar.tsx` and `frontend/src/app/App.tsx` -> overview/composition
    - client-owner: repository `frontend/src/features/profile/api.ts` and `types.ts` -> typed no-path convention
    - chat-boundary: repository `frontend/src/features/chat/` and `frontend/src/test/sse-reducer.test.ts` -> unchanged reducer
    - validation: repository `docs/plans/Plan_8.md` > `## Verification` -> frontend checks
  - Source Requirements:
    - Current owner keeps profile/upload state. New sidebar state owns only collapse/tab/selection/cache/request state; Overview is default.
    - Fetch non-overview tabs only on first select or explicit refresh, cache successful query results, retain safe prior data after error, and render independent loading/empty/stale/unavailable/safe-error states.
    - Full text requires explicit chunk expansion; retained-file action requires `file_available`; graph is React/CSS semantic fallback with returned truncation data.
    - Collapse/expand is a real `aria-expanded` control with visible focus, mobile Escape, and no composer overlap.
  - Dependencies: `(02A)`, `(02B)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/observability/api.ts`, `frontend/src/features/observability/types.ts`, `frontend/src/features/observability/state.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/features/observability/CvHistoryPanel.tsx`, `frontend/src/features/observability/ChunkPanel.tsx`, `frontend/src/features/observability/GraphPanel.tsx`, `frontend/src/features/observability/RunHistoryPanel.tsx`, `frontend/src/features/observability/observability.css`, `frontend/src/test/observability-sidebar.test.tsx`, `frontend/src/test/observability-api.test.ts`, `frontend/src/test/cv-sidebar.test.tsx`
  - Allowed Files: `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/observability/**`, `frontend/src/test/observability-sidebar.test.tsx`, `frontend/src/test/observability-api.test.ts`, `frontend/src/test/cv-sidebar.test.tsx`, and required test setup only; exclude chat feature/reducer, backend, package manifests, and non-sidebar styles unless a proven layout constraint is approved.
  - Agent Work:
    1. Search existing Astryx/sidebar/upload APIs, render helpers, styles, and profile client patterns; preserve overview and shared upload/interaction lock.
    2. Build focused observability client/types/state/panels with sidebar-local selection/cache/request state.
    3. Refactor only sidebar composition for safe file action, selected detail, semantic graph fallback, and documented states.
    4. Add accessibility/mobile behavior and focused API/sidebar tests; run regression/build checks.
  - Output: Accessible bounded observability inspector without a second chat/profile state path.
  - A1 Outcome: Responsive cached safe sidebar works without chat/SSE or approval changes.
  - A2 Review Focus: State ownership, no dependency/state duplication, lazy/cache/error states, safe display, keyboard/mobile/composer behavior, and validation evidence.
  - A3 Batch Evidence: M8-05 plus frontend M8-06 accessibility, cache, and regression evidence.
  - Acceptance:
    - Overview preserves upload/replace/download/interaction lock; new tabs are lazy, query-cached, and safe after failed requests.
    - Chunks/file/graph behavior obeys selected-detail, `file_available`, and bounded semantic-fallback contracts.
    - Collapse has `aria-expanded`, focus, Escape, and no composer overlap; SSE reducer/history remain unchanged.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/observability-sidebar.test.tsx src/test/observability-api.test.ts src/test/cv-sidebar.test.tsx` -> PASS: exit `0`; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS: all exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS: exit `0`; freshness: final attempt only.
  - Blocked Condition: Missing required safe typed state is `BLOCKED_SOURCE_CONFLICT`; needed chat/profile owner change is `BLOCKED_SCOPE_CONFLICT`; unavailable Node tooling is `BLOCKED_ENVIRONMENT`.
  - Files: listed App/sidebar/observability modules and tests.

## Mandatory Batch04 - Synthetic Local Observability Release Evidence

### Goal

Document and execute the synthetic-data-only local smoke and final regression evidence.

### Dependencies

- `(01A)`, `(02A)`, `(02B)`, and `(03A)` are accepted with final-attempt evidence.
- Root `.env`, Docker/Compose, loopback ports, and live provider setup are already usable without exposing values.

### Scope Boundary

Own the new checklist and fresh evidence only. Do not add product behavior, alter API/schema, tune models, use real CVs, or create a separate runtime.

### Tasks

- [ ] (04A): Publish and run the synthetic-data observability sidebar checklist and final regressions
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_8.md` > `## Mandatory Batch04 - Synthetic Local Observability Release Evidence` > `(04A)`
  - Source of Truth: `docs/plans/Plan_8.md` > `## Implementation` item 7, `## Verification`, and `## Completion Contract`; supporting design > `## Verification`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_8.md` > `(04A)` -> task authority
    - source-verification: repository `docs/plans/Plan_8.md` > `## Verification` -> automated/Compose/direct-FE/scope gates
    - source-completion: repository `docs/plans/Plan_8.md` > `## Completion Contract` -> final safety gate
    - release-checklist: repository `docs/acceptance/local_release_checklist.md` -> evidence/data-safety convention
    - runtime-compose: repository `infrastructure/docker-compose.yml` -> three-service stack
  - Source Requirements:
    - Synthetic checklist covers archive replacement, retained open/download, canonical chunk expansion, runs, ready/truncated/fallback graph, mobile collapse, console inspection.
    - Run focused/backend/frontend/static/build, Compose health, direct smoke, and scope hygiene without raw PDFs, paths, prompts, secrets, or stacks.
  - Dependencies: All previous task IDs accepted.
  - User Action: Before direct smoke, existing root `.env` values must support local Compose/live extraction. Do not provide or record values; missing/invalid setup blocks rather than expands configuration scope.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 10800
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/observability_sidebar_checklist.md`.
  - Allowed Files: `docs/acceptance/observability_sidebar_checklist.md` only; exclude backend, frontend, infrastructure, configuration, `.env`, database/upload artifacts, and existing evidence.
  - Agent Work:
    1. Verify accepted reports and source coverage, then write preconditions, synthetic inputs, expected safe observations, fallbacks, mobile/accessibility, console, cleanup, and data/secret prohibition.
    2. Run Plan 8 backend/API/graph and existing affected backend checks, frontend full checks, and scope hygiene.
    3. Start existing Compose with root `.env`, verify health, execute checklist with synthetic CVs, and retain sanitized results only.
    4. Stop/report the first required failure or unsafe exposure; do not modify code/config to force acceptance.
  - Output: `docs/acceptance/observability_sidebar_checklist.md` and sanitized A1 final-gate evidence.
  - A1 Outcome: Synthetic checklist and evidence demonstrate safe archived-CV, chunk, run, and graph inspection without regression.
  - A2 Review Focus: Checklist coverage, evidence freshness/sanitization, all command results, no code/config/secret change, and correct blocking of missing live setup.
  - A3 Batch Evidence: M8-06 and completion gate: checklist, regression/static/build, Compose/direct-FE/console, and scope hygiene.
  - Acceptance:
    - Checklist covers all mandated synthetic observations and prohibits raw documents/paths/prompts/stacks/secrets.
    - All required commands pass final attempt; Compose reports `overall=available`; direct smoke has no relevant console error.
    - Any unavailable service/credential, failed validation, unsafe payload, or failed smoke is blocked, not accepted.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_attachment_text_chunks.py tests/unit/test_observability_graph.py tests/integration/test_observability_api.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py -q; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS: all exit `0`; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS: all exit `0`; freshness: final attempt only.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180; Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS: health `overall=available`, no secrets; freshness: final attempt only.
    - Required: Execute `docs/acceptance/observability_sidebar_checklist.md` with synthetic CVs -> PASS: mandatory observations pass and console has no relevant error; freshness: final attempt only.
    - Required: `git diff --check` and review against `docs/plans/Plan_8.md` -> PASS: exit `0`, approved scope, no data/secrets/arbitrary graph access; freshness: final attempt only.
  - Blocked Condition: Missing user-managed stack/provider setup is `BLOCKED_USER_ACTION`; unavailable Docker/browser/ports/toolchain is `BLOCKED_ENVIRONMENT`; failed required validation or unsafe payload is `BLOCKED_SCOPE_CONFLICT`. Do not accept partial evidence.
  - Files: `docs/acceptance/observability_sidebar_checklist.md`