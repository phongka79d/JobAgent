# Plan_10: Saved JD Library And Revision-Keyed Evaluations

## Objective

Deliver a deterministic saved-JD experience on top of the completed Plan 9 baseline:
a successful zero-result match renders one actionable recovery card; one explicit click
saves/deduplicates and evaluates the initiating JD; the sidebar exposes compact saved
JD list/detail/actions; and SQLite reuses exactly one evaluation for the same Job and
current CV/profile/preferences/matching revision. Older results remain visible as
**Cần đánh giá lại** until the user explicitly recomputes them, and complete JD
deletion removes only that Job and its evaluations/graph relationships while
preserving shared Skills and all unrelated data.

## Source of Truth

- `docs/plans/Master_plan.md`: `## 1. Project Objective`
- `docs/plans/Master_plan.md`: `## 2. Locked Product Scope`
- `docs/plans/Master_plan.md`: `## 6. SQLite Database Contract`
- `docs/plans/Master_plan.md`: `### 7.7 Saved JD and evaluation views`
- `docs/plans/Master_plan.md`: `## 14. Public FastAPI Boundary`
- `docs/plans/Master_plan.md`: `## 15. Frontend UX Plan`
- `docs/plans/Master_plan.md`: `### 17.5 Explicit saved-JD evaluation flow`
- `docs/plans/Master_plan.md`: `## 18. Matching Formula`
- `docs/plans/Master_plan.md`: `## 21. Direct SQLite-to-Neo4j Synchronization`
- `docs/plans/Master_plan.md`: `## 24. Local Testing Strategy`
- `docs/plans/Master_plan.md`: `### Phase 9 - Saved JD library and revision-keyed evaluations`
- Approved 2026-07-17 change: zero-match recovery card, `JD đã lưu` below
  `Agent runs`, one evaluation per JD and CV/profile revision, explicit stale
  recomputation, complete JD deletion, and concise titles/actions.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| P9-JD-01 | Sections 1, 14, 15.5 | A successful `match_jobs` payload with `count=0` renders **Chưa có kết quả đánh giá** and one-click **Lưu JD & đánh giá lại**, bound to its initiating user message. | Backend source-binding integration tests plus frontend empty/pending/success/error card tests and direct FE smoke. |
| P9-JD-02 | Sections 2.1, 7.7, 14, 15.2 | `JD đã lưu` appears directly below `Agent runs` and provides a bounded compact list, selected detail, persisted evidence/score, and explicit view/evaluate/re-evaluate/delete actions. | API redaction/pagination tests, sidebar navigation/state/component tests, and desktop/mobile inspection. |
| P9-JD-03 | Sections 6.2-6.4, 17.5 | `job_evaluations` stores one validated result per `(job_id, evaluation_context_hash)` and derives `none | current | stale` without rewriting history or automatically recomputing. | Migration/database tests, context-hash unit tests, revision-change integration tests, and provider call-count assertions. |
| P9-JD-04 | Sections 14.1, 17.5, 18 | Public routes and Agent tools reuse existing ingestion, deduplication, consistency, scoring, and explanation owners; exact-Job evaluation is independent of LLM tool chaining and top-50 retrieval membership. | Service/API tests prove exact-hash/current-context reuse and shared component/explanation parity. |
| P9-JD-05 | Sections 6.3-6.4, 14.1, 21 | Complete delete removes the SQLite Job and all evaluations plus exact Neo4j Job node/incident Job relationships, while preserving shared Skills, seed edges, Candidate/CV branches, and unrelated Jobs. | Cross-store deletion integration tests with Neo4j fault/retry and preservation assertions. |
| P9-JD-06 | Sections 15.1-15.6 | Titles, labels, badges, pending states, confirmation, and errors remain concise, accessible, and non-overlapping in the existing Astryx desktop/mobile shell. | Focused frontend tests, screenshot/manual checklist, keyboard/focus checks, and clean browser console. |
| P9-JD-07 | Sections 24, 27 | The full local backend/frontend/Compose demo remains green with no real provider calls in normal tests and no out-of-scope infrastructure or redesign. | Full lint/type/test/build suites, Compose health check, direct FE acceptance, and scope hygiene checks. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Plans 1-4 | Migrated SQLite, durable chat/run/tool records, active Candidate Profile, approved preferences, and revision timestamps | Run current migration/database/chat/profile baselines and inspect every caller of changed models/services. |
| Plan 5 | `job_posts`, exact-hash JD ingestion, compact repository rows, direct Job graph sync, and `save_job`/`query_jobs` adapters | Confirm URL/text ingestion and duplicate/retry tests pass before adding public routes. |
| Plan 6 | Candidate embedding, graph consistency/retrieval, deterministic components/explanations, `MatchResult`, `match_jobs`, and match cards | Run focused matching backend/frontend suites and identify one shared exact-Job scoring seam before refactoring. |
| Plan_8 | Cursor/redaction conventions and sidebar-local API/state/cache/navigation patterns | Reuse the existing cursor helpers, safe projections, panel primitives, and request-order protection. |
| Plan_9 | Active CV/document source hash, profile/CV lifecycle, exact CV ownership deletion, CV Manager, and completed responsive shell | Verify Plan 9 tests pass and treat its lifecycle/approval/graph work as immutable input. |
| Master Version 1.8 | Authorized schema, public API, UX, revision, deletion, and Phase 9 amendment | Confirm the plan set passes the shared structural validator before task writing. |
| Local test environment | Python 3.13 backend, frontend dependencies, Docker Compose, and disposable Neo4j/SQLite fixtures | Verify documented baseline commands without using real CV/JD data or a real ShopAIKey call in automated tests. |

## Scope

- Add the `job_evaluations` migration/model/schema/repository and exact revision-key
  builder defined by Master Version 1.8.
- Refactor only the necessary matching seams so top-N `match_jobs` and exact saved-JD
  evaluation share graph consistency, Candidate embedding, score components, quality
  multiplier, and deterministic explanation logic.
- Add bounded list/detail, combined save-and-evaluate, explicit evaluate, and complete
  delete APIs as thin adapters over existing application services.
- Add the zero-result chat card and bind its CTA to the durable initiating user
  message, never to inferred latest text or a second Agent decision.
- Add `JD đã lưu` below `Agent runs`, with a compact list, selected detail, currentness
  state, persisted result, confirmation, and per-JD actions.
- Add exact Neo4j Job deletion plus SQLite cascade and retry-safe false-success
  prevention.
- Extend focused/full automated tests and one synthetic direct FE acceptance checklist.
- Update only documentation needed to describe commands and the completed Phase 9
  behavior after implementation.

## Out of Scope

- Rewriting Plan 9 CV extraction, approval, CV Manager, active-CV reading, or CV graph
  ownership.
- A new scoring formula, learned weights, reranking, benchmark dataset, ranking metric,
  or LLM-generated numerical score.
- Automatic/background evaluation after CV, profile, preference, Job, or scoring
  revision changes; bulk evaluation; scheduled refresh; or notification services.
- Depending on the LLM to choose or chain `save_job` and `match_jobs` for the recovery
  CTA, or adding a second Agent/tool loop.
- Editing a saved JD, importing/discovering jobs automatically, application tracking,
  auto-apply, cover letters, or multi-user ownership.
- Persisting top-N query pages, retrieval rankings, raw CV/JD text in evaluation rows,
  prompts, provider responses, or embeddings in evaluation payloads.
- Returning raw JD text or extraction evidence bodies in compact list responses.
- Adding Redis, Celery, a worker, outbox, sync ledger, new vector store, authentication,
  cloud deployment, CI, or a visual redesign of the existing shell.
- Backfilling historical evaluations for existing Jobs during migration or startup.
- Creating `docs/tasks/task_10.md`, executing product changes, or claiming portfolio
  approval during this planning phase.

## Target Directory Structure

```text
backend/
  migrations/versions/
    <revision>_add_job_evaluations.py
  app/
    api/
      jobs.py
    db/models/
      job_evaluations.py
      jobs.py                         # relationship/cascade only if needed
    graph/
      delete_job.py
      retrieval.py                    # exact-Job semantic read seam
    repositories/
      job_evaluations.py
      jobs.py
    schemas/
      job_evaluations.py
      matching.py
    services/
      job_evaluation.py
      job_deletion.py
      matching.py
      match_components.py
      match_explanations.py
    main.py
  tests/
    unit/
      test_evaluation_context.py
      test_job_evaluation.py
      test_job_graph_deletion.py
    integration/
      test_saved_jobs_api.py
      test_job_evaluations.py
      test_job_deletion.py
      test_migrations.py
      test_database_contract.py
      test_match_jobs.py
frontend/src/
  features/
    chat/
      ChatPage.tsx
      components/
        ChatMessageRow.tsx
        EmptyMatchResultCard.tsx
    jobs/
      api.ts
      types.ts
      SavedJobsPanel.tsx
      SavedJobDetail.tsx
      JobDeleteDialog.tsx
      MatchCard.tsx
    observability/
      ObservabilitySidebar.tsx
      ObservabilityTabList.tsx
      state.ts
      types.ts
  test/
    empty-match-card.test.tsx
    saved-jobs-api.test.ts
    saved-jobs-panel.test.tsx
    saved-jobs-state.test.tsx
    observability-navigation.test.tsx
docs/acceptance/
  saved_jd_evaluation_checklist.md
README.md
```

Names may align with an equivalent existing focused owner discovered during the
required search-before-write pass. Reuse or safely refactor an existing module before
creating a duplicate. New source files stay below the repository's 300-line target;
split API, state, presentation, context-key, evaluation, and deletion responsibilities
rather than enlarging current files into God files.

## Technical Specifications

### Migration And Persistence

- Add `job_evaluations` exactly as Master Section 6.2 specifies, with named foreign
  keys, unique/index contracts, UTC timestamps, validated JSON, and cascades from
  both `job_posts` and `attachments`.
- The Alembic migration is structural only: preserve every existing Job and CV row,
  create no synthetic evaluation, and make zero provider, filesystem, or Neo4j calls.
- Register the model through the existing metadata/import owner and extend migration
  and database contract tests. Do not add a generic cache/history abstraction.
- Repository writes accept a validated `MatchResult` projection only. A uniqueness
  conflict on `(job_id, evaluation_context_hash)` reloads the committed winner.

### Evaluation Context And Currentness

- Implement one pure canonical context builder shared by write and read paths. It
  consumes server-loaded Job ID/revision, active attachment ID, approved CV source
  hash, Candidate Profile revision, Job Preferences revision, and one explicit
  matching-contract version; stable sorted JSON bytes are SHA-256 hashed.
- Never accept revision fields, context hash, or current/stale state from the client.
  `none` means no evaluation row for the Job, `current` means an exact current hash
  exists, and `stale` means rows exist but none match the current hash.
- List/detail queries derive state without updating every row after an active CV,
  profile, preference, or matching-contract change. The latest stored stale result may
  remain visible with **Cần đánh giá lại**, but it is never presented as current.
- Reuse a current row before Candidate embedding, Neo4j scoring, or explanation work.
  Test call counts, not only response equality.

### Shared Exact-Job Evaluation

- Search every caller of `match_jobs`, component builders, explanations, graph
  retrieval/consistency, and result projection before changing them. Extract the
  smallest shared single-Job scoring boundary and keep top-N ordering behavior intact.
- A new evaluation runs the existing full Candidate/Job graph consistency gate, then
  embeds the current Candidate and reads semantic similarity for the exact `Job.id`.
  It must not disappear merely because the Job is outside vector top 50.
- Reuse existing skill normalization/coverage, optional-component renormalization,
  quality multiplier, deterministic evidence/explanation, and `MatchResult`
  validation. Do not fork formulas or maintain a second component map.
- Provider and graph work occurs outside SQLite transactions. Persist only after the
  exact result and context still validate; if the context changed during computation,
  discard the candidate result and return a safe retryable `EVALUATION_CONTEXT_CHANGED`
  instead of storing it under the wrong revision.
- Preserve existing `NEO4J_UNAVAILABLE`, `NEO4J_REBUILD_REQUIRED`, embedding, active
  profile, unscorable Job, and invalid-result failure semantics without false success.

### Deterministic Saved-JD API

- `GET /api/jobs` uses the existing opaque cursor owner, `limit` in `1..50`, stable
  newest-first `(created_at, id)` paging, compact extraction metadata, latest score,
  and derived `none | current | stale`. It returns no raw JD/evidence body.
- `GET /api/jobs/{job_id}` returns the selected Job's validated extraction/source
  detail and latest/current evaluation projection. It never returns embeddings,
  prompts, credentials, storage paths, arbitrary graph properties, or provider data.
- `POST /api/jobs/save-and-evaluate` accepts only `source_message_id`. Load that exact
  durable user message and require its completed run to contain a validated successful
  `match_jobs` result with `count=0`. Treat a sole valid public HTTP(S) URL as URL
  input; otherwise use the complete configured-size-bounded message as raw text.
- The combined route delegates to existing URL/text ingestion and exact-hash
  deduplication, then the same exact evaluation service. Existing Job plus current
  context returns `reused`; failed/unscorable ingestion returns the persisted Job and
  `evaluation_outcome='unavailable'` with a safe code.
- `POST /api/jobs/{job_id}/evaluate` creates or reuses only the current context.
  `DELETE /api/jobs/{job_id}` delegates only to the deletion coordinator. Routes own
  validation/status mapping, not business logic.
- Use stable safe errors including `JOB_NOT_FOUND`, `JOB_NOT_SCORABLE`,
  `ACTIVE_PROFILE_REQUIRED`, `JD_SOURCE_NOT_RECOVERABLE`, and existing graph/provider
  codes. Error responses disclose no message content, raw JD, SQL, Cypher, or trace.

### Complete Job Deletion

- Search all Job repository, sync, consistency, rebuild, observability, matching, and
  UI callers before adding deletion. Keep one application-service coordinator.
- Verify the SQLite Job exists, then idempotently match only `(:Job {id: $job_id})`
  and detach/delete that node. Never match/delete a `Skill`, seed `RELATED_TO`,
  Candidate, CV, or another Job.
- Delete the SQLite `job_posts` row only after exact graph deletion succeeds; its
  evaluations cascade in the same short transaction. A missing graph node is an
  idempotent success, while unavailable/failed graph deletion preserves SQLite state
  and returns retry guidance.
- Return `204` only when the SQLite Job/evaluations no longer exist and the exact graph
  Job node is absent. Repeated calls after complete deletion return `JOB_NOT_FOUND` and
  never affect shared data.
- Invalidate the graph and selected saved-JD caches only after complete success.

### Zero-Result Chat UX

- Keep strict parsing of successful `match_jobs` ToolResult data. When `count=0`,
  render one card instead of `results.map(...)` producing no visible result.
- Card copy is exactly **Chưa có kết quả đánh giá** and **Lưu JD & đánh giá lại**.
  Add one short explanation; avoid nested/repeated headings or technical tool text.
- Resolve the initiating user message ID from the same durable row/run relationship
  already used for tool activity. Pass a narrow action callback through `ChatPage`;
  do not create a second chat store or infer from the latest composer value.
- Disable the CTA while pending. On current/created success, render the returned
  persisted match result through existing MatchCard/score components and invalidate
  the saved-JD cache. On unavailable/error, keep the card and show one safe retry or
  resubmit instruction without claiming evaluation succeeded.
- Do not render the recovery CTA for failed, malformed, non-`match_jobs`, or nonzero
  result payloads.

### Saved-JD Sidebar UX

- Extend the existing tab ID/type/list/state/API patterns; place `JD đã lưu` directly
  after `Agent runs`. Preserve tab rail sizing, keyboard behavior, mobile drawer,
  request-order guards, and successful-page cache semantics.
- Use a compact row with concise title, company, quality/processing badge, evaluation
  state, and latest score. Truncate visually long labels with accessible full text;
  omit duplicate panel/card headings and verify no title/action overlap.
- Maintain one selected detail. Show validated extraction/source information and the
  latest persisted MatchResult through existing score/evidence components. Do not
  duplicate match-card formatting or component-label maps.
- Show **Đánh giá với CV** when no current result exists, **Đánh giá lại** only when
  stale, and **Xoá JD** behind an accessible confirmation naming the Job. A current
  evaluation needs no redundant evaluate button.
- Keep list/detail state on failed requests. Disable duplicate actions while pending;
  refresh only affected list/detail/graph/chat projections on success and select a
  safe remaining row after deletion.
- Inspect pinned Astryx documentation before using a component/prop not already in the
  repository. Reuse existing buttons, badges, dialogs, skeletons, banners, spacing,
  colors, typography, and responsive primitives.

## Implementation

1. Run the full current backend/frontend baseline and the shared plan validator.
   Search all Job ingestion/repository/model, matching/component/explanation,
   graph/rebuild/observability, chat-history/tool-result, sidebar/API/state, and card
   callers. Record reusable owners and oversized-file seams before editing.
2. Add failing migration/model/repository/context tests. Implement `job_evaluations`,
   named constraints/indexes/cascades, validated JSON, canonical context hashing, and
   current/stale lookup with no historical backfill.
3. Add failing exact-Job scoring and provider-call-count tests. Refactor the existing
   matching pipeline at its root so list matching and explicit evaluation share one
   component/explanation path while preserving current top-N outputs.
4. Add failing evaluation service tests for active-profile/scorable/context gates,
   current reuse, context change, uniqueness race, graph/provider failures, and exact
   result persistence; then implement the focused service.
5. Add failing exact graph deletion/preservation/fault tests. Implement one Job
   deletion coordinator and thin graph/repository operations with graph-first,
   SQLite-second completion semantics.
6. Add failing saved-JD API tests for pagination/redaction/detail/errors,
   message/run/zero-result source authorization, ingestion deduplication, explicit
   evaluate reuse/staleness, and complete deletion; then add thin routes and dependency
   wiring.
7. Add failing frontend API/parser/state/navigation tests. Extend the existing
   sidebar-local typed client/cache/reducer, append `JD đã lưu` below `Agent runs`, and
   implement compact list/selected detail/action/confirmation states in focused files.
8. Add failing chat tests for empty successful results and CTA lifecycle. Implement the
   concise zero-result card, durable initiating-message binding, save/evaluate action,
   existing MatchCard reuse, and targeted cache invalidation.
9. Run focused suites, then full lint/type/test/build. Fix root regressions across all
   callers rather than adding compatibility duplication.
10. Start the local Compose stack, execute the synthetic saved-JD checklist on desktop
    and mobile, inspect visible titles/actions, keyboard focus, network behavior,
    SQLite/Neo4j preservation, and browser console, then run scope/secret/data hygiene.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Existing baseline | `Set-Location backend; py -3.13 -m pytest -q`; `Set-Location ../frontend; npm test -- --run` | Plan 9 backend/frontend baseline is green before Phase 9 changes. |
| Migration/database | `Set-Location backend; py -3.13 -m pytest tests/integration/test_migrations.py tests/integration/test_database_contract.py tests/integration/test_job_evaluations.py -q` | Existing data survives; named table/FKs/unique/index/cascades pass; migration performs no provider/graph/backfill work. |
| Context/reuse | `Set-Location backend; py -3.13 -m pytest tests/unit/test_evaluation_context.py tests/unit/test_job_evaluation.py tests/integration/test_job_evaluations.py -q` | Canonical hash is stable; same context creates one row and zero repeat provider/graph scoring calls; CV/profile/preference/version changes derive stale without auto-run. |
| Matching parity | `Set-Location backend; py -3.13 -m pytest tests/unit/test_match_components.py tests/unit/test_match_explanations.py tests/unit/test_match_ordering.py tests/integration/test_match_jobs.py tests/unit/test_job_evaluation.py -q` | Existing top-N results remain unchanged and exact Job evaluation shares formula/evidence owners even outside top 50. |
| Saved-JD API | `Set-Location backend; py -3.13 -m pytest tests/integration/test_saved_jobs_api.py tests/integration/test_job_evaluations.py tests/integration/test_job_ingestion.py -q` | List/detail bounds/redaction, durable zero-result source binding, exact-hash reuse, created/reused/unavailable responses, and safe errors pass. |
| Complete delete | `Set-Location backend; py -3.13 -m pytest tests/unit/test_job_graph_deletion.py tests/integration/test_job_deletion.py tests/integration/test_graph_rebuild_contracts.py -q` | Exact Job/evaluations/relationships disappear; Skill/seed/Candidate/CV/unrelated Job data survives; graph failure preserves SQLite and retry completes. |
| Agent/chat regression | `Set-Location backend; py -3.13 -m pytest tests/unit/test_agent_graph.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py tests/e2e/test_demo_flow.py -q` | One Agent/ToolNode behavior, durable tool results, existing save/query/match flows, and deterministic public recovery remain compatible. |
| Frontend focused | `Set-Location frontend; npm test -- --run src/test/empty-match-card.test.tsx src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-navigation.test.tsx src/test/match-card.test.tsx` | Exact Vietnamese copy, tab order, list/detail/current/stale, one-click lifecycle, result component reuse, confirmation, errors, and accessibility pass. |
| Backend full/static | `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental; py -3.13 -m pytest -q` | Lint, types, and all backend tests pass without real ShopAIKey calls. |
| Frontend full/build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Existing chat/CV Manager/observability/matching behavior and production build remain green. |
| Local services | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` | Frontend, backend, and Neo4j are healthy on documented local ports. |
| Direct FE smoke | Execute `docs/acceptance/saved_jd_evaluation_checklist.md` with synthetic JD/CVs on desktop and mobile. | Blank zero-match is gone; one click saves/evaluates; same context reuses; CV switch shows **Cần đánh giá lại** without auto-run; explicit rerun persists; delete preserves shared graph data; titles/actions do not overlap; console is clean. |
| Scope hygiene | `git diff --check`; inspect `git status --short`, changed paths, migrations, tracked data/secrets, and source file lengths. | No task file, duplicate business logic, raw personal data, secrets, auto-evaluation worker, second Agent, scoring redesign, unrelated UI redesign, or new oversized source file. |
| Plan structure | `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` | Plans are contiguous through `Plan_10.md`; Plans 1-9 hand off normally and only Plan 10 is terminal. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Plans 1-4 | Local runtime, migrated source-of-truth data, durable chat/run/tools, approved active profile/preferences | Existing ownership, transaction, SSE, approval, and safe-error contracts remain authoritative. |
| Plan 5 | Job ingestion, exact deduplication, repository, sync/rebuild, and compact saved-job projection | Public routes delegate to these owners instead of copying Agent-tool business logic. |
| Plan 6 | Matching consistency, semantic retrieval, components, explanations, result schema, and cards | Refactoring preserves existing top-N outputs and extracts only the shared exact-Job seam. |
| Plan_8 | Cursor/redaction/sidebar-local state/cache/navigation infrastructure | Saved-JD UX extends these patterns and does not create a second inspector architecture. |
| Plan_9 | Active CV/document revisions, CV Manager lifecycle, graph ownership, and responsive UI baseline | Evaluation currentness consumes approved revision facts without changing Plan 9 behavior. |
| Master Version 1.8 amendment | Phase 9 schema/API/UX/evaluation/deletion requirements and user-approved labels/actions | The amendment supersedes the former no-score-cache/no-public-job-CRUD/sidebar boundary only for the explicitly named saved-JD capabilities. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Fresh portfolio review | Updated `Master_plan.md`, Plan 9 successor handoff, and `Plan_10.md` | Shared structural validator passes; requirement ownership, dependencies, scope, technical contracts, and verification are reviewable across Plans 1-10. |
| `task-writing-agent` after portfolio approval | One Phase 9 task contract at `docs/tasks/task_10.md` | Task maps one authoritative checkbox and A1/A2/A3 evidence to P9-JD-01 through P9-JD-07 without reopening prior phases. |
| Future A1 implementation | Executable migration/service/API/frontend/test sequence | Task identifies reusable owners, test-first gates, exact commands, safe error/deletion contracts, and 300-line modularity ceiling. |
| Future A2/A3 review | Independent functional/scope acceptance boundary | Evidence proves one-context reuse, explicit stale recompute, deterministic recovery, exact deletion preservation, regression safety, and no out-of-scope infrastructure. |

## Completion Contract

Plan 10 planning is complete only when Master Version 1.8 explicitly authorizes the
saved-JD/revision-keyed-evaluation capability, Plan 9 hands its implemented baseline
to this phase, and the contiguous Plans 1-10 portfolio passes the shared structural
validator with Plan 10 as the sole terminal plan. Every approved zero-result card,
deterministic source binding, ingestion/scoring reuse, schema/currentness rule,
saved-JD list/detail/action, explicit stale recomputation, exact cross-store deletion,
concise responsive UX, failure/recovery behavior, and verification requirement has
one owner. No product code or `task_10.md` is created, and the required next action is
a fresh full portfolio review before task writing or execution.
