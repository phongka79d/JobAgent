# JobAgent Plan 10 Execution Tasks

## Purpose

Translate `docs/plans/Plan_10.md` into the mandatory implementation chain for revision-keyed saved-JD evaluations, shared exact-Job scoring, deterministic saved-JD APIs, exact cross-store Job deletion, the saved-JD sidebar, the zero-result chat recovery action, and final local release evidence. Preserve the single-user local MVP, one Agent/tool loop, SQLite source of truth, derived Neo4j index, existing matching formula, and implemented Plan 9 shell.

## Project Context Notes

- Root `README.md` was read completely before derivation. It defines the React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, ShopAIKey, root-only `.env`, three-service Compose, synthetic-test, and local-validation boundaries.
- The current user explicitly invoked `task-writing-agent` for `Plan_10.md`. That instruction authorizes this task file and supersedes only the plan-phase statement that task writing awaited fresh review; it does not expand implementation scope or claim implementation acceptance.
- The shared structural validator passed on 2026-07-18 with contiguous `Plan_1.md` through `Plan_10.md`, no errors, and Plan 10 as the terminal plan.
- Primary authority is `docs/plans/Plan_10.md`. Supporting authority is `docs/plans/Master_plan.md` Version 1.8. Repository files and README supply paths and reuse evidence only.
- Plan 9 product tasks through Batch07 are checked in `docs/tasks/task_9.md`, while `(08A)` synthetic release evidence remains unchecked and README still identifies Batch08 as pending. Accepted Plan 9 final evidence is therefore an explicit prerequisite for Plan 10 execution, not an achievement of this authoring pass.
- Existing reuse owners include `services/jd_ingestion.py`, `repositories/jobs.py`, `services/matching.py`, `services/match_components.py`, `services/match_explanations.py`, `graph/consistency.py`, `graph/retrieval.py`, durable message/run/tool repositories, the shared history cursor codec, `features/jobs/MatchCard.tsx`, and the observability sidebar's typed request/cache patterns.
- Existing files already above the 300-line target include `jd_ingestion.py`, `repositories/jobs.py`, `matching.py`, `graph/consistency.py`, frontend observability state/types, `ChatPage.tsx`, `ChatMessageRow.tsx`, and `matchResult.ts`. Plan 10 work must extract focused owners or make only narrow delegating edits; it must not grow God files or fork their business logic.
- `frontend/AGENTS.md` applies to Batch05 through Batch07: start UI discovery with the pinned Astryx 0.1.4 CLI, inspect component documentation before use, keep layout in Astryx components, use tokens rather than raw styling, and preserve the existing shell.
- The worktree already contains user changes to `docs/plans/Master_plan.md`, `docs/plans/Plan_9.md`, and untracked `docs/plans/Plan_10.md`. Preserve them. This authoring pass creates only `docs/tasks/task_10.md`.
- Root `.env`, databases, uploads, Neo4j volumes, raw CV/JD bodies, provider transcripts, and credentials are user-managed and must never be printed, copied into reports, or committed. Automated tests use fakes; only Batch08 may use configured local services with synthetic data.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_10.md`.
- Supporting: `docs/plans/Master_plan.md` Version 1.8.
- Context only: `README.md`, `frontend/AGENTS.md`, `docs/tasks/task_9.md`, existing code/tests, and `infrastructure/docker-compose.yml`.

### Source Section Index

- `Plan_10.md` > `## Objective`, `## Master Requirement Coverage`, `## Prerequisites`, `## Scope`, and `## Out of Scope` -> mandatory outcomes, P9-JD-01 through P9-JD-07, dependencies, and exclusions.
- `Plan_10.md` > `## Target Directory Structure` -> focused ownership, search-before-write, and 300-line modularity boundary.
- `Plan_10.md` > `### Migration And Persistence` and `### Evaluation Context And Currentness` -> exact schema, canonical context, race handling, reuse, and stale-state rules.
- `Plan_10.md` > `### Shared Exact-Job Evaluation` -> shared consistency, semantic, component, explanation, and context-revalidation behavior.
- `Plan_10.md` > `### Deterministic Saved-JD API` -> bounded reads, durable source authorization, ingestion/evaluation reuse, thin routes, and safe errors.
- `Plan_10.md` > `### Complete Job Deletion` -> exact graph-first deletion, SQLite cascade, retry, verification, and preservation rules.
- `Plan_10.md` > `### Zero-Result Chat UX` and `### Saved-JD Sidebar UX` -> exact copy, durable row binding, action lifecycle, tab placement, accessibility, and focused cache invalidation.
- `Plan_10.md` > `## Implementation`, `## Verification`, `## Handoff Contract`, and `## Completion Contract` -> execution order, evidence matrix, consumed owners, and terminal acceptance.
- `Master_plan.md` > `### 6.2 Application table schemas`, `### 6.3 Foreign-key and deletion rules`, and `### 6.4 Transaction boundaries` -> canonical Job/evaluation rows, cascades, and external-call boundaries.
- `Master_plan.md` > `### 7.7 Saved JD and evaluation views`, `## 14. Public FastAPI Boundary`, and `## 15. Frontend UX Plan` -> public schemas, endpoints, redaction, tab, card, and action contracts.
- `Master_plan.md` > `### 17.5 Explicit saved-JD evaluation flow`, `## 18. Matching Formula`, and `## 21. Direct SQLite-to-Neo4j Synchronization` -> exact-Job evaluation sequence, invariant scoring, consistency, and graph safety.
- `Master_plan.md` > `## 24. Local Testing Strategy`, `### Phase 9 - Saved JD library and revision-keyed evaluations`, and `## 27. Definition of Done` -> required automated/manual evidence and exit gates.

### Approved Architecture and Constraints

- Keep one React/Astryx client, one FastAPI application, one LangGraph Agent with its existing ToolNode/loop, one SQLite source of truth, one derived Neo4j index, and ShopAIKey as the only model provider.
- Persist only validated compact `MatchResult` projections in `job_evaluations`. Do not persist raw CV/JD text, embeddings, prompts, provider responses, transient retrieval pages, or rankings there.
- Build one server-side canonical context hash from exact Job, active CV, approved CV source, profile, preference, and matching-contract revisions. Clients cannot submit revisions, hashes, or currentness.
- Reuse a current evaluation before any provider, graph scoring, or explanation work. New evaluation work occurs outside SQLite transactions and persists only after the context is revalidated.
- Refactor the existing matching root so top-N and exact-Job paths share formula, quality, evidence, and explanation owners. Do not add a second component map, scoring formula, Agent decision, or top-50 dependency.
- One service coordinates exact Job deletion: exact Neo4j Job first, SQLite Job/evaluations second, success only after both stores confirm absence. Shared Skills, seed relationships, Candidate/CV branches, and unrelated Jobs are immutable preservation targets.
- Extend the existing sidebar-local request/cache/navigation pattern and existing score components. Do not create a second chat store, observability architecture, matching renderer, or visual redesign.
- No background/bulk evaluation, worker/queue/outbox, authentication, CI, new vector store, edit/import/discovery workflow, alternate model, ranking metric, or historical backfill.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Evaluation persistence and canonical currentness | (01A) | Accepted Plan 9 baseline |
| Batch02 | Shared exact-Job scoring and idempotent evaluation service | (02A), (02B) | Batch01 |
| Batch03 | Retry-safe exact Job deletion | (03A) | Batch02 |
| Batch04 | Deterministic saved-JD public API | (04A), (04B) | Batch03 |
| Batch05 | Typed saved-JD client and sidebar-local action state | (05A) | Batch04 |
| Batch06 | Accessible saved-JD sidebar interface | (06A) | Batch05 |
| Batch07 | Durable zero-result chat recovery | (07A) | Batch06 |
| Batch08 | Synthetic direct smoke and final regression evidence | (08A) | Batch07 |

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

## Mandatory Batch01 - Evaluation Persistence and Canonical Currentness

### Goal

Add the structural-only evaluation schema, validated persistence boundary, and one pure canonical server-side context/currentness owner without backfill or external work.

### Dependencies

- `docs/tasks/task_9.md` `(08A)` and the Plan 9 batch-scope audit are accepted before implementation starts.
- The shared plan validator passes and the current backend/frontend baseline is recorded before edits.

### Scope Boundary

Own one Alembic revision, evaluation ORM/schema/repository, pure context-key logic, metadata registration, and direct migration/context tests. Exclude matching refactors, provider/graph evaluation work, API routes, deletion, and frontend.

### Tasks

- [x] (01A): Persist one validated evaluation per canonical Job context
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch01 - Evaluation Persistence and Canonical Currentness` > `(01A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Migration And Persistence`, `### Evaluation Context And Currentness`, and `## Implementation` item 2; `docs/plans/Master_plan.md` > `### 6.2 Application table schemas` > `job_evaluations`, `### 6.3 Foreign-key and deletion rules`, and `### 6.4 Transaction boundaries`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(01A)` -> task authority
    - source-persistence: repository `docs/plans/Plan_10.md` > `### Migration And Persistence` -> schema/repository authority
    - master-evaluations: repository `docs/plans/Master_plan.md` > `### 6.2 Application table schemas` > `job_evaluations` -> exact fields, keys, context tuple, and reuse contract
    - migration-owner: repository `backend/migrations/versions/0003_add_cv_documents_and_ownership.py` and `backend/tests/support/db_migration.py` -> current revision conventions
    - model-owner: repository `backend/app/db/models/jobs.py` and `backend/app/db/models/__init__.py` -> Job/metadata ownership
    - validation-persistence: repository `docs/plans/Plan_10.md` > `## Verification` > `Migration/database` and `Context/reuse` -> required evidence
  - Source Requirements:
    - Add every Master-specified column, named FK, unique key, index, UTC timestamp, validated JSON boundary, and cascades from `job_posts` and `attachments`.
    - Perform a structural-only migration that preserves existing Job/CV/checkpoint rows, creates no evaluation rows, and calls no provider, filesystem, or Neo4j owner.
    - Compute stable sorted canonical JSON bytes and SHA-256 from server-loaded Job/revision, active attachment, approved CV source hash, profile revision, preference revision, and one explicit matching-contract version.
    - Derive `none | current | stale` without mutating history; repository writes accept a validated `MatchResult`, and a unique-key race reloads the committed winner.
  - Dependencies: Accepted Plan 9 `(08A)` and batch audit; no earlier Plan 10 task.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/migrations/versions/0004_add_job_evaluations.py`, `backend/app/db/models/job_evaluations.py`, `backend/app/db/models/jobs.py`, `backend/app/db/models/__init__.py`, `backend/app/repositories/job_evaluations.py`, `backend/app/schemas/job_evaluations.py`, `backend/app/services/evaluation_context.py`, `backend/tests/unit/test_evaluation_context.py`, `backend/tests/integration/test_job_evaluations.py`, `backend/tests/integration/test_migrations.py`, `backend/tests/integration/test_database_contract.py`
  - Allowed Files: the listed migration/model/repository/schema/context/test files and existing migration test support; exclude matching, graph, API, Agent/tools, frontend, infrastructure, runtime data, and unrelated migrations.
  - Agent Work:
    1. Use `git grep` to trace the migration head, Job/attachment models, metadata imports, UTC/UUID/JSON conventions, all Job repository callers, and existing cursor/current-row patterns before editing.
    2. Add failing empty/existing-database, named constraint/index/cascade, no-backfill, canonical-hash, current/stale, validated-result, and uniqueness-race tests.
    3. Implement one focused model/repository/context boundary; safely refactor a shared convention rather than duplicating it, and keep new source files below 300 lines.
    4. Prove migration isolation, row preservation, deterministic canonical bytes, client non-authority, and flush/short-transaction behavior with final-attempt evidence.
  - Output: One migrated relational evaluation contract and pure current-context owner reusable by reads and writes.
  - A1 Outcome: Existing databases upgrade without data loss and expose exactly one validated evaluation per Job/context with deterministic current/stale derivation.
  - A2 Review Focus: Exact Master schema/names/cascades, no backfill/external call, canonical serialization stability, MatchResult validation, race reload, repository transaction discipline, and all model/repository callers.
  - A3 Batch Evidence: P9-JD-03 schema/currentness coverage plus the migration-preservation, context-key, and ownership rows.
  - Acceptance:
    - Empty and initialized databases upgrade to the next sole head with every specified column, constraint, index, and cascade while preserving all existing application and checkpoint rows.
    - No migration/startup path synthesizes evaluations or reaches provider, filesystem, or graph work.
    - The same canonical facts produce byte-identical JSON/hash; changing any named revision fact changes the hash; no client field participates.
    - Repository reads distinguish no rows, exact-current rows, and latest-stale rows without rewriting history; writes validate `MatchResult` and reload a concurrent winner.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_migrations.py tests/integration/test_database_contract.py tests/integration/test_job_evaluations.py -q` -> PASS evidence: exit `0` with preservation, named schema, cascade, race, and no-backfill assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_evaluation_context.py -q` -> PASS evidence: exit `0` with stable canonical bytes/hash and all revision-change cases; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Missing accepted Plan 9 final evidence is `BLOCKED_MISSING_REF`; a conflicting migration head/schema authority is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/Alembic/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/migrations/versions/0004_add_job_evaluations.py`, `backend/app/db/models/job_evaluations.py`, `backend/app/db/models/jobs.py`, `backend/app/db/models/__init__.py`, `backend/app/repositories/job_evaluations.py`, `backend/app/schemas/job_evaluations.py`, `backend/app/services/evaluation_context.py`, `backend/tests/unit/test_evaluation_context.py`, `backend/tests/integration/test_job_evaluations.py`, `backend/tests/integration/test_migrations.py`, `backend/tests/integration/test_database_contract.py`

## Mandatory Batch02 - Shared Exact-Job Scoring and Idempotent Evaluation

### Goal

Extract the smallest shared single-Job scoring boundary, preserve top-N results, and add one context-safe evaluation service that reuses current rows before external work.

### Dependencies

- `(01A)` is accepted with its migration, context, repository, and final validation evidence.

### Scope Boundary

Own matching-root refactoring, exact-Job graph similarity reads, and evaluation orchestration/tests. Exclude public routes, Job deletion, frontend, formula/weight changes, graph repair, and background evaluation.

### Tasks

- [x] (02A): Share exact-Job and top-N scoring without changing ranking behavior
  - Task Type: refactor
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch02 - Shared Exact-Job Scoring and Idempotent Evaluation` > `(02A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Shared Exact-Job Evaluation` and `## Implementation` item 3; `docs/plans/Master_plan.md` > `### 17.5 Explicit saved-JD evaluation flow` and `## 18. Matching Formula`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(02A)` -> task authority
    - source-shared-score: repository `docs/plans/Plan_10.md` > `### Shared Exact-Job Evaluation` -> shared-boundary authority
    - scoring-owner: repository `backend/app/services/matching.py` > `_score_retrieved_candidates` and `match_jobs` -> current orchestration/root seam
    - component-owner: repository `backend/app/services/match_components.py` and `backend/app/services/match_explanations.py` -> formula/order/explanation authority
    - graph-owner: repository `backend/app/graph/consistency.py` and `backend/app/graph/retrieval.py` -> consistency and semantic-read authority
    - validation-parity: repository `docs/plans/Plan_10.md` > `## Verification` > `Matching parity` -> required evidence
  - Source Requirements:
    - Search every caller of `match_jobs`, component/explanation builders, graph consistency/retrieval, and result projection before changing the root seam.
    - Keep existing top-N consistency, ordering, formula, renormalization, multiplier, evidence, explanation, and `MatchResult` validation behavior byte/semantically compatible.
    - Add an exact `Job.id` semantic read after the full Candidate/Job consistency gate; exact evaluation cannot depend on vector top-50 membership.
    - Maintain one component map and one explanation projection; no provider/graph/SQLite persistence belongs in the pure scoring boundary.
  - Dependencies: `(01A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/matching.py`, `backend/app/services/match_scoring.py`, `backend/app/services/match_components.py`, `backend/app/services/match_explanations.py`, `backend/app/graph/retrieval.py`, `backend/tests/unit/test_match_components.py`, `backend/tests/unit/test_match_explanations.py`, `backend/tests/unit/test_match_ordering.py`, `backend/tests/unit/test_job_evaluation.py`, `backend/tests/integration/test_match_jobs.py`
  - Allowed Files: the listed matching/retrieval/test files; exclude evaluation persistence, migrations, API, deletion, Agent/tool topology, frontend, settings/models, and unrelated graph owners.
  - Agent Work:
    1. Use `git grep` to enumerate every caller and test of matching, scoring, explanations, consistency, retrieval, and `MatchResult`; record current top-N fixtures and oversized-file seams.
    2. Add failing parity and exact-ID tests, including a scorable Job outside vector top 50 and exact provider/graph call assertions.
    3. Extract or expose the smallest pure single-Job scorer and exact semantic reader, delegating existing top-N logic to it without copying formulas or evidence maps.
    4. Run focused parity/static checks and inspect all callers for root compatibility rather than adding adapters that duplicate business logic.
  - Output: One shared pure scoring/projection boundary used by unchanged top-N matching and later exact evaluation.
  - A1 Outcome: Existing top-N outputs remain unchanged while one exact Job can be scored through the same component and explanation owners outside top-50 retrieval.
  - A2 Review Focus: Caller inventory, no formula/component/explanation fork, exact-ID query safety, full consistency reuse, top-N ordering parity, MatchResult validation, and refactor rubric behavior preservation.
  - A3 Batch Evidence: P9-JD-04 shared-scoring ownership plus exact-outside-top-50 and top-N parity rows.
  - Acceptance:
    - Existing top-N fixtures, ties, unavailable components, quality multipliers, and explanations remain unchanged.
    - Exact semantic retrieval targets only the requested `Job.id` and succeeds for a consistent scorable Job outside top 50.
    - Both paths call the same pure component/evidence/explanation owners and keep provider/graph I/O outside that boundary.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_match_components.py tests/unit/test_match_explanations.py tests/unit/test_match_ordering.py tests/integration/test_match_jobs.py tests/unit/test_job_evaluation.py -q` -> PASS evidence: exit `0` with parity and exact-outside-top-50 assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A formula/consistency source conflict is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/services/matching.py`, `backend/app/services/match_scoring.py`, `backend/app/services/match_components.py`, `backend/app/services/match_explanations.py`, `backend/app/graph/retrieval.py`, `backend/tests/unit/test_match_components.py`, `backend/tests/unit/test_match_explanations.py`, `backend/tests/unit/test_match_ordering.py`, `backend/tests/unit/test_job_evaluation.py`, `backend/tests/integration/test_match_jobs.py`

- [x] (02B): Evaluate one saved Job with current-context reuse and change detection
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch02 - Shared Exact-Job Scoring and Idempotent Evaluation` > `(02B)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Evaluation Context And Currentness`, `### Shared Exact-Job Evaluation`, and `## Implementation` item 4; `docs/plans/Master_plan.md` > `### 17.5 Explicit saved-JD evaluation flow`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(02B)` -> task authority
    - source-evaluation: repository `docs/plans/Plan_10.md` > `### Shared Exact-Job Evaluation` -> orchestration authority
    - context-owner: repository `backend/app/services/evaluation_context.py` and `backend/app/repositories/job_evaluations.py` -> accepted `(01A)` context/persistence artifacts
    - scoring-owner: repository `backend/app/services/match_scoring.py` and `backend/app/graph/retrieval.py` -> accepted `(02A)` exact scoring artifacts
    - validation-reuse: repository `docs/plans/Plan_10.md` > `## Verification` > `Context/reuse` and `Matching parity` -> required evidence
  - Source Requirements:
    - Resolve active approved profile/preferences, approved CV source, exact scorable Job, and current context from SQLite; reject preconditions before provider work.
    - Return a validated current row before Candidate embedding, graph scoring, or explanations; assert call counts, not only response equality.
    - For a new context, run the existing consistency gate, embed Candidate once, exact-read and shared-score outside SQLite transactions, then revalidate context before persistence.
    - Discard a result and return retryable `EVALUATION_CONTEXT_CHANGED` when context changes; reload a uniqueness winner; preserve safe graph/provider/profile/unscorable/invalid-result semantics.
  - Dependencies: `(01A)` and `(02A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/job_evaluation.py`, `backend/app/services/evaluation_context.py`, `backend/app/repositories/job_evaluations.py`, `backend/app/schemas/job_evaluations.py`, `backend/tests/unit/test_job_evaluation.py`, `backend/tests/integration/test_job_evaluations.py`, `backend/tests/integration/test_match_jobs.py`
  - Allowed Files: the listed evaluation service/context/repository/schema/test files and narrow fixes in accepted `(02A)` exact-scoring seams; exclude API, deletion, migration shape, Agent/tools, frontend, and unrelated ingestion/matching behavior.
  - Agent Work:
    1. Trace all accepted context/repository/scoring call sites and existing safe error/result patterns with `git grep` before adding orchestration.
    2. Add failing tests for no profile, unscorable Job, consistency/provider failures, current reuse, exact scoring, context change, invalid result, uniqueness race, and no open transaction during external work.
    3. Implement one focused evaluation service that composes accepted owners and rechecks the exact context before its short insert transaction.
    4. Prove zero repeated external calls on reuse and no false persisted success on every failure/race path.
  - Output: One deterministic exact-Job evaluation service returning `created` or `reused` for the current context.
  - A1 Outcome: A saved Job creates at most one validated result per context, reuses it without external work, and rejects mid-computation context drift safely.
  - A2 Review Focus: Call order/counts, server-loaded context, short transactions, context revalidation, race winner behavior, exact shared scorer use, safe error preservation, and hard-gate false-success risks.
  - A3 Batch Evidence: P9-JD-03/P9-JD-04 idempotency, context-change, exact-score, and external-call-boundary rows.
  - Acceptance:
    - Same Job/current context returns one row and performs zero repeat provider, graph-scoring, or explanation calls.
    - A new context uses the full consistency gate and exact shared scorer once, never holds SQLite open across external work, and persists only after exact context revalidation.
    - Context drift returns `EVALUATION_CONTEXT_CHANGED` without a new row; uniqueness races reload the committed winner; established safe failures never return success.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_evaluation_context.py tests/unit/test_job_evaluation.py tests/integration/test_job_evaluations.py tests/integration/test_match_jobs.py -q` -> PASS evidence: exit `0` with call-count, drift, race, exact-score, and failure assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Missing accepted `(01A)`/`(02A)` artifacts are `BLOCKED_MISSING_REF`; a required behavior change outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/services/job_evaluation.py`, `backend/app/services/evaluation_context.py`, `backend/app/repositories/job_evaluations.py`, `backend/app/schemas/job_evaluations.py`, `backend/tests/unit/test_job_evaluation.py`, `backend/tests/unit/test_evaluation_context.py`, `backend/tests/integration/test_job_evaluations.py`, `backend/tests/integration/test_match_jobs.py`

## Mandatory Batch03 - Retry-Safe Exact Job Deletion

### Goal

Delete one Job and its evaluations only after its exact Neo4j Job node is absent, with retry-safe failures and preservation of every shared or unrelated graph artifact.

### Dependencies

- Batch02 is accepted; evaluation cascades and currentness behavior are stable.

### Scope Boundary

Own exact Job graph deletion, focused SQLite delete primitives, one application coordinator, and deletion/preservation tests. Exclude routes, frontend cache invalidation, CV deletion, graph rebuild redesign, and generic deletion frameworks.

### Tasks

- [x] (03A): Coordinate exact graph-first and SQLite-second Job deletion
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch03 - Retry-Safe Exact Job Deletion` > `(03A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Complete Job Deletion` and `## Implementation` item 5; `docs/plans/Master_plan.md` > `### 6.4 Transaction boundaries`, `### 14.1 API rules`, and `## 21. Direct SQLite-to-Neo4j Synchronization`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(03A)` -> task authority
    - source-delete: repository `docs/plans/Plan_10.md` > `### Complete Job Deletion` -> deletion/preservation authority
    - graph-delete-pattern: repository `backend/app/graph/delete_cv.py` -> parameterization, allowlist, and idempotency pattern
    - job-owner: repository `backend/app/repositories/jobs.py`, `backend/app/graph/sync_job.py`, and `backend/app/graph/rebuild_ops.py` -> current Job ownership/callers
    - validation-delete: repository `docs/plans/Plan_10.md` > `## Verification` > `Complete delete` -> required evidence
  - Source Requirements:
    - Search every Job repository, sync, consistency, rebuild, observability, matching, and UI caller before implementing one coordinator.
    - Verify SQLite existence, idempotently match/delete only `(:Job {id: $job_id})`, and confirm absence before deleting SQLite; a missing graph node is success.
    - Let the Job row deletion cascade evaluations in one short transaction only after graph success; graph unavailable/failure preserves all SQLite state for retry.
    - Preserve every Skill, seed `RELATED_TO`, Candidate, CV branch, unrelated Job, and unrelated relationship; repeated complete deletion returns `JOB_NOT_FOUND` without mutation.
  - Dependencies: Batch02 accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/graph/delete_job.py`, `backend/app/services/job_deletion.py`, `backend/app/repositories/job_deletion.py`, `backend/app/repositories/jobs.py`, `backend/tests/unit/test_job_graph_deletion.py`, `backend/tests/integration/test_job_deletion.py`, `backend/tests/integration/test_graph_rebuild_contracts.py`
  - Allowed Files: the listed graph/service/repository/test files; allow a narrow existing Job repository delegation but do not grow it with orchestration; exclude API, frontend, CV deletion, migrations, graph rebuild behavior changes, and unrelated graph labels.
  - Agent Work:
    1. Use `git grep` to map every Job read/write/sync/rebuild/observability/matching/UI caller and study exact CV deletion safety before writing Job deletion.
    2. Add failing parameterization/allowlist/idempotency, graph-fault, SQLite-preservation, cascade, retry, and shared-data-preservation tests.
    3. Implement one focused exact graph function, one narrow SQLite primitive, and one coordinator with graph-first/SQLite-second/verify-absence semantics.
    4. Inspect all callers and graph queries for broad label/relationship deletion or false `204` capability, then run final focused/static evidence.
  - Output: One retry-safe complete Job deletion service with exact cross-store verification.
  - A1 Outcome: Deleting a Job removes only its exact graph node/incident relationships and SQLite row/evaluations, while graph failures preserve retryable SQLite truth.
  - A2 Review Focus: Query allowlist/parameterization, store ordering, exact absence checks, idempotency, cascade ownership, every preservation assertion, caller impact, and false-success hard gate.
  - A3 Batch Evidence: P9-JD-05 exact-delete, failure-preservation, retry, and shared-graph integrity rows.
  - Acceptance:
    - The graph operation can target only the supplied `Job.id`; missing exact node is idempotent success and broad/shared-label deletion is structurally rejected.
    - SQLite Job and evaluations remain after any graph failure and disappear together only after exact graph absence is confirmed.
    - Skills, seed edges, Candidate/CV branches, unrelated Jobs/relationships survive; a repeat after complete deletion returns `JOB_NOT_FOUND` without graph mutation.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_job_graph_deletion.py tests/integration/test_job_deletion.py tests/integration/test_graph_rebuild_contracts.py -q` -> PASS evidence: exit `0` with exact-query, retry, cascade, and preservation assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A root delete fix that requires altering CV/rebuild scope is `BLOCKED_SCOPE_CONFLICT`; ambiguous graph ownership is `BLOCKED_AMBIGUOUS_REF`; unavailable graph-test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/graph/delete_job.py`, `backend/app/services/job_deletion.py`, `backend/app/repositories/job_deletion.py`, `backend/app/repositories/jobs.py`, `backend/tests/unit/test_job_graph_deletion.py`, `backend/tests/integration/test_job_deletion.py`, `backend/tests/integration/test_graph_rebuild_contracts.py`

## Mandatory Batch04 - Deterministic Saved-JD Public API

### Goal

Expose bounded safe saved-JD reads and deterministic source-bound mutations as thin adapters over accepted ingestion, evaluation, and deletion owners.

### Dependencies

- Batch03 is accepted; evaluation, ingestion reuse, and deletion coordinators are available.

### Scope Boundary

Own saved-JD public schemas, list/detail read assembly, exact source authorization, thin routes/status mapping, router wiring, and API tests. Exclude frontend, Agent/tool changes, alternate ingestion/scoring, and raw/internal response fields.

### Tasks

- [ ] (04A): Serve bounded redacted saved-JD list and selected detail
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch04 - Deterministic Saved-JD Public API` > `(04A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Deterministic Saved-JD API` and `## Implementation` item 6; `docs/plans/Master_plan.md` > `### 7.7 Saved JD and evaluation views` and `### 14.1 API rules`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(04A)` -> task authority
    - source-api: repository `docs/plans/Plan_10.md` > `### Deterministic Saved-JD API` -> list/detail authority
    - cursor-owner: repository `backend/app/schemas/chat.py` > `encode_history_cursor` / `decode_history_cursor` and `backend/app/schemas/observability.py` alias pattern -> opaque cursor reuse
    - repository-owner: repository `backend/app/repositories/jobs.py` > `list_compact` and accepted `backend/app/repositories/job_evaluations.py` -> Job/evaluation reads
    - route-owner: repository `backend/app/api/observability.py` and `backend/app/main.py` -> thin route/router conventions
    - validation-api: repository `docs/plans/Plan_10.md` > `## Verification` > `Saved-JD API` -> required evidence
  - Source Requirements:
    - `GET /api/jobs` enforces `limit` `1..50`, stable newest-first `(created_at,id)` paging through the existing opaque cursor codec, compact metadata, latest score, and derived `none | current | stale`.
    - List responses omit raw JD/evidence bodies, embeddings, prompts, credentials, paths, graph properties, provider data, and historical arrays.
    - `GET /api/jobs/{job_id}` returns validated selected extraction/source detail plus latest/current evaluation; unknown IDs map to safe `JOB_NOT_FOUND`.
    - Read paths compute the same server-side context/currentness as writes and do not update evaluation rows or run external work.
  - Dependencies: Batch03 accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/api/jobs.py`, `backend/app/main.py`, `backend/app/services/saved_jobs.py`, `backend/app/repositories/saved_jobs.py`, `backend/app/repositories/jobs.py`, `backend/app/repositories/job_evaluations.py`, `backend/app/schemas/job_evaluations.py`, `backend/tests/integration/test_saved_jobs_api.py`
  - Allowed Files: the listed API/router/read-service/repository/schema/test files; `repositories/jobs.py` may only delegate an extracted query owner for existing callers; exclude mutation orchestration until `(04B)`, Agent/tools, matching/deletion internals, frontend, settings, and raw data fixtures.
  - Agent Work:
    1. Use `git grep` to trace cursor codecs, list/detail projections, currentness owners, safe errors, router wiring, and all Job compact-row callers.
    2. Add failing pagination/order/bounds/malformed-cursor, currentness, detail, not-found, JSON validation, and redaction tests.
    3. Implement focused read projections/service and thin GET routes, reusing the shared cursor/context owners; extract a focused saved-Job query owner and keep only a compatibility delegation if existing callers still enter through oversized `repositories/jobs.py`.
    4. Inspect serialized payloads for prohibited fields and prove reads perform no mutation/provider/graph scoring.
  - Output: Bounded `GET /api/jobs` and `GET /api/jobs/{job_id}` contracts with exact safe projections.
  - A1 Outcome: Saved Jobs can be paged and selected with server-derived evaluation state and no compact-list data leakage.
  - A2 Review Focus: Cursor reuse/order, limit/status mapping, list/detail schema accuracy, currentness parity, redaction/adversarial serialization, no external work, and read-only behavior.
  - A3 Batch Evidence: P9-JD-02/P9-JD-03 list/detail pagination, currentness, schema, and redaction rows.
  - Acceptance:
    - Stable cursor pages have no duplicates/skips for fixed data, reject malformed cursors with `422`, and return compact `none | current | stale` plus latest score.
    - Selected detail validates extraction/raw source only within the accepted bound and returns one latest evaluation projection; unknown Job is safe `JOB_NOT_FOUND`.
    - Prohibited internal/raw fields are absent from list responses and no GET path mutates data or calls provider/graph scoring.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_saved_jobs_api.py tests/integration/test_job_evaluations.py -q` -> PASS evidence: exit `0` with pagination, currentness, detail, error, and redaction assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A cursor/currentness authority conflict is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable API test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/api/jobs.py`, `backend/app/main.py`, `backend/app/services/saved_jobs.py`, `backend/app/repositories/saved_jobs.py`, `backend/app/repositories/jobs.py`, `backend/app/repositories/job_evaluations.py`, `backend/app/schemas/job_evaluations.py`, `backend/tests/integration/test_saved_jobs_api.py`

- [ ] (04B): Bind save/evaluate/delete mutations to accepted service owners
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch04 - Deterministic Saved-JD Public API` > `(04B)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Deterministic Saved-JD API`, `### Complete Job Deletion`, and `## Implementation` item 6; `docs/plans/Master_plan.md` > `### 14.1 API rules` and `### 17.5 Explicit saved-JD evaluation flow`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(04B)` -> task authority
    - source-mutations: repository `docs/plans/Plan_10.md` > `### Deterministic Saved-JD API` -> save/evaluate/delete authority
    - durable-source-owner: repository `backend/app/repositories/agent_runs.py` > `get_run_by_user_message_id`, `backend/app/repositories/tool_executions.py`, and `backend/app/services/chat_history.py` -> message/run/tool truth
    - ingestion-owner: repository `backend/app/services/jd_ingestion.py` > `ingest_raw_text` / `ingest_url` -> exact-hash ingestion authority
    - accepted-services: repository `backend/app/services/job_evaluation.py` and `backend/app/services/job_deletion.py` -> evaluation/deletion authority
    - validation-mutations: repository `docs/plans/Plan_10.md` > `## Verification` > `Saved-JD API`, `Complete delete`, and `Agent/chat regression` -> required evidence
  - Source Requirements:
    - `POST /api/jobs/save-and-evaluate` accepts only `source_message_id`, loads that exact durable user message, and requires its completed run to contain a validated successful `match_jobs` result with `count=0`.
    - Treat a sole valid public HTTP(S) URL as URL input; otherwise use the complete configured-size-bounded message. Never accept replacement text or infer the latest composer/message.
    - Delegate to existing ingestion/exact deduplication and the accepted exact evaluation service; return `created | existing | retried` ingestion and `created | reused | unavailable` evaluation outcomes without false success.
    - Explicit evaluate uses only current context; delete delegates only to the accepted coordinator; routes own validation/status mapping and safe errors without exposing message/JD/SQL/Cypher/trace data.
  - Dependencies: `(04A)` plus Batch02/Batch03 accepted services.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/api/jobs.py`, `backend/app/services/saved_jobs.py`, `backend/app/schemas/job_evaluations.py`, `backend/app/repositories/chat_messages.py`, `backend/app/repositories/agent_runs.py`, `backend/app/repositories/tool_executions.py`, `backend/tests/integration/test_saved_jobs_api.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_job_deletion.py`, `backend/tests/integration/test_chat_api.py`
  - Allowed Files: the listed route/source-authorization/schema/repository/test files and narrow dependency wiring; accepted ingestion/evaluation/deletion services may receive only root-cause compatibility fixes; exclude Agent graph/tool registration, alternate ingestion/scoring, frontend, migrations, and raw fixtures.
  - Agent Work:
    1. Use `git grep` to trace exact chat-message/run/tool ownership, terminal ToolResult validation, URL validation, ingestion callers, evaluation/deletion errors, and all route status patterns.
    2. Add failing source authorization, wrong/missing/malformed/nonzero/failed tool result, URL-versus-text, exact-hash reuse, unavailable ingestion, explicit reuse/staleness, delete, safe-error, and redaction tests.
    3. Implement one focused source-bound application service and thin POST/DELETE routes that delegate to accepted owners without a second Agent decision or transaction-spanning external call.
    4. Prove stable safe responses/statuses, existing-current zero external calls, unavailable persistence truth, exact deletion delegation, and existing Agent/tool compatibility.
  - Output: Deterministic combined save/evaluate, explicit evaluate, and complete delete HTTP actions.
  - A1 Outcome: The public API deterministically saves/evaluates only the initiating zero-result JD, reuses current results, and deletes through the exact coordinator.
  - A2 Review Focus: Durable source authorization, strict ToolResult parsing, no latest-message inference, URL/text bounds, ingestion/evaluation/deletion delegation, status/error redaction, Agent caller compatibility, and false-success risks.
  - A3 Batch Evidence: P9-JD-01/P9-JD-04/P9-JD-05 source-binding, reuse, safe-error, and thin-mutation rows.
  - Acceptance:
    - Only an exact durable initiating user message with a completed successful zero-count `match_jobs` result can authorize save-and-evaluate; all invalid relationships fail before ingestion.
    - Exact-hash ingestion and current evaluation reuse preserve their accepted outcomes/call counts; failed/unscorable ingestion returns persisted Job plus safe `unavailable` without claiming evaluation.
    - Explicit evaluation and delete expose accepted service behavior/statuses only; errors contain no message/JD body, SQL, Cypher, trace, prompt, path, or credential.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_saved_jobs_api.py tests/integration/test_job_evaluations.py tests/integration/test_job_ingestion.py tests/integration/test_job_deletion.py -q` -> PASS evidence: exit `0` with source binding, dedup, outcome, reuse, delete, and safe-error assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_agent_graph.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py tests/e2e/test_demo_flow.py -q` -> PASS evidence: exit `0` with one Agent/ToolNode and existing tool/chat compatibility; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Missing accepted service artifacts are `BLOCKED_MISSING_REF`; ambiguous durable source ownership is `BLOCKED_AMBIGUOUS_REF`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable API test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/api/jobs.py`, `backend/app/services/saved_jobs.py`, `backend/app/schemas/job_evaluations.py`, `backend/app/repositories/chat_messages.py`, `backend/app/repositories/agent_runs.py`, `backend/app/repositories/tool_executions.py`, `backend/tests/integration/test_saved_jobs_api.py`, `backend/tests/integration/test_job_evaluations.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_job_deletion.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/e2e/test_demo_flow.py`

## Mandatory Batch05 - Typed Saved-JD Client and Action State

### Goal

Add strict saved-JD transport/parser contracts and focused sidebar-local request/cache/action state without enlarging the existing observability God files.

### Dependencies

- Batch04 is accepted with stable public schemas, outcomes, errors, and pagination.

### Scope Boundary

Own focused saved-JD frontend types, client, request-order-safe state, cache invalidation, selection, and tests. Exclude panel rendering, tab composition, chat cards, and visual styling.

### Tasks

- [ ] (05A): Implement strict saved-JD transport, cache, selection, and action state
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch05 - Typed Saved-JD Client and Action State` > `(05A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Saved-JD Sidebar UX` and `## Implementation` item 7; `docs/plans/Master_plan.md` > `### 7.7 Saved JD and evaluation views` and `### 15.6 Observability sidebar boundaries`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(05A)` -> task authority
    - source-client-state: repository `docs/plans/Plan_10.md` > `### Saved-JD Sidebar UX` -> state/action authority
    - client-pattern: repository `frontend/src/features/observability/api.ts`, `useLatestRequest.ts`, and `cvManagerState.ts` -> safe transport/request/action patterns
    - cache-pattern: repository `frontend/src/features/observability/state.ts` -> successful-page cache and focused invalidation behavior to reuse without growing
    - result-owner: repository `frontend/src/features/jobs/matchResult.ts` -> strict persisted MatchResult parser/format authority
    - validation-client: repository `docs/plans/Plan_10.md` > `## Verification` > `Frontend focused` -> required evidence
  - Source Requirements:
    - Strictly parse list/detail/currentness/evaluation/outcome/error payloads and reject extra/malformed data without leaking raw internals.
    - Keep saved-JD state sidebar-local with independent list/detail/action loading/error state, successful-page cache semantics, and request-order guards.
    - Preserve list/detail data after failed requests, disable duplicate per-Job actions while pending, invalidate only affected list/detail/graph/chat projections after success, and choose a safe remaining row after deletion.
    - Reuse the accepted MatchResult parser/labels/formatters and existing request/cache patterns; do not create a second observability state architecture or grow `state.ts`/`matchResult.ts` with duplicate business logic.
  - Dependencies: Batch04 accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/jobs/api.ts`, `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/test/saved-jobs-api.test.ts`, `frontend/src/test/saved-jobs-state.test.tsx`
  - Allowed Files: the listed focused jobs client/types/state/tests and narrow reusable type exports; exclude observability panels/navigation, chat, MatchCard/ScoreBreakdown formatting, CSS, backend, and package/dependency changes.
  - Agent Work:
    1. Use `git grep` to trace observability API/parser/cache/request-order/action patterns and every MatchResult parser/formatter caller before writing new client state.
    2. Add failing strict parser, cursor, request-order, keep-data-on-error, pending deduplication, focused invalidation, and safe post-delete selection tests.
    3. Implement small focused jobs modules that reuse existing safe primitives or safely extract them rather than duplicating state/cache/error logic.
    4. Prove malformed/adversarial payload rejection and exact action/cache transitions with focused tests and static checks.
  - Output: A typed saved-JD frontend client and reusable sidebar-local state hook/reducer.
  - A1 Outcome: Saved-JD reads/actions have strict transport parsing, race-safe local state, focused invalidation, and stable selection without UI coupling.
  - A2 Review Focus: Parser allowlists, request ordering, stale response rejection, preserved successful data, action deduplication, cache scope, MatchResult reuse, file-size discipline, and no second state architecture.
  - A3 Batch Evidence: P9-JD-02/P9-JD-06 client schema, cache, pending/error, invalidation, and selection rows.
  - Acceptance:
    - List/detail/action responses are strictly parsed and malformed/extra/prohibited fields cannot enter state.
    - Older requests cannot overwrite newer data; failures retain prior successful list/detail; duplicate same-Job actions remain disabled while pending.
    - Success invalidates only documented projections and deletion selects a deterministic safe remaining item without duplicating observability or scoring state.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-state.test.tsx` -> PASS evidence: exit `0` with strict parser, request-order, cache, action, and selection assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A backend schema mismatch is `BLOCKED_SOURCE_CONFLICT`; a reusable-state extraction outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable Node/npm tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/jobs/api.ts`, `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/test/saved-jobs-api.test.ts`, `frontend/src/test/saved-jobs-state.test.tsx`

## Mandatory Batch06 - Accessible Saved-JD Sidebar Interface

### Goal

Place `JD đã lưu` directly after `Agent runs` and render a compact accessible list/detail/action experience through the accepted client state and existing score components.

### Dependencies

- `(05A)` is accepted with stable typed state/action callbacks.

### Scope Boundary

Own tab integration, compact saved-JD panels/dialog, existing component reuse, accessibility/responsive tests, and only necessary token styling. Exclude chat recovery, backend, scoring formatting duplication, shell redesign, and unrelated observability panels.

### Tasks

- [ ] (06A): Render compact saved-JD list, detail, evaluation, and deletion actions
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch06 - Accessible Saved-JD Sidebar Interface` > `(06A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Saved-JD Sidebar UX` and `## Implementation` item 7; `docs/plans/Master_plan.md` > `### 15.1 Layout`, `### 15.2 Sidebar`, and `### 15.6 Observability sidebar boundaries`; `frontend/AGENTS.md` > `WORKFLOW` and `RULES`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(06A)` -> task authority
    - source-sidebar: repository `docs/plans/Plan_10.md` > `### Saved-JD Sidebar UX` -> UI/action authority
    - navigation-owner: repository `frontend/src/features/observability/ObservabilityTabList.tsx`, `ObservabilitySidebar.tsx`, and `types.ts` -> tab order/composition authority
    - state-owner: repository `frontend/src/features/jobs/savedJobsState.ts` -> accepted `(05A)` state/action authority
    - score-owner: repository `frontend/src/features/jobs/MatchCard.tsx`, `ScoreBreakdown.tsx`, and `matchResult.ts` -> score/evidence rendering authority
    - design-authority: repository `frontend/AGENTS.md` -> pinned Astryx discovery/layout/component rules
    - validation-sidebar: repository `docs/plans/Plan_10.md` > `## Verification` > `Frontend focused` -> required evidence
  - Source Requirements:
    - Append `JD đã lưu` immediately after `Agent runs` while preserving rail sizing, keyboard behavior, mobile drawer, request cache, and the existing `13/47/40` shell.
    - Render compact rows with concise title/company, quality/processing badge, evaluation state, and latest score; stale rows display `Cần đánh giá lại`; truncate long labels visually with accessible full text and no overlap/redundant headings.
    - Maintain one selected detail with validated source/extraction and persisted `MatchResult` rendered through existing score/evidence components.
    - Show `Đánh giá với CV` for none, `Đánh giá lại` only for stale, no evaluate button for current, and `Xoá JD` behind an accessible Job-naming confirmation; preserve data on errors and disable duplicate pending actions.
  - Dependencies: `(05A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/jobs/SavedJobsPanel.tsx`, `frontend/src/features/jobs/SavedJobDetail.tsx`, `frontend/src/features/jobs/JobDeleteDialog.tsx`, `frontend/src/features/observability/observabilityTabs.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/features/observability/ObservabilityTabList.tsx`, `frontend/src/features/observability/types.ts`, `frontend/src/features/observability/observability.css`, `frontend/src/test/saved-jobs-panel.test.tsx`, `frontend/src/test/observability-navigation.test.tsx`
  - Allowed Files: the listed focused panel/dialog/navigation/type/style/tests and narrow sidebar composition; extract tab identity/configuration from oversized `types.ts` instead of growing it; exclude observability state God-file growth, chat, backend, package changes, graph controls, shell proportions, and duplicate MatchCard/score maps.
  - Agent Work:
    1. Run `npx astryx build "compact saved JD sidebar list detail actions"`, inspect every newly used component with `npx astryx component <Name>`, and use `git grep` to trace current tabs/panels/dialogs/score renderers.
    2. Add failing tab-order, keyboard/focus, list/detail/current-stale, pending/error, confirmation, truncation/a11y, narrow-layout, and no-overlap tests.
    3. Implement focused panel/detail/dialog modules with Astryx components/tokens, extract focused tab identity/configuration instead of growing oversized `types.ts`, and compose accepted state into the existing sidebar without duplicating score presentation.
    4. Run focused/full frontend checks and inspect changed source lengths, tab semantics, labels/actions, and existing shell/graph/CV Manager regressions.
  - Output: One accessible `JD đã lưu` sidebar tab with compact list, selected detail, persisted evidence, and explicit actions.
  - A1 Outcome: Users can inspect, evaluate/re-evaluate, and confirm deletion of saved JDs in the existing desktop/mobile sidebar without title/action overlap.
  - A2 Review Focus: Exact tab order/labels/action matrix, Astryx rule evidence, keyboard/focus/mobile behavior, current/stale correctness, MatchCard reuse, error/pending state, no overlap, and no shell redesign.
  - A3 Batch Evidence: P9-JD-02/P9-JD-06 tab, compact layout, accessibility, action, and persisted-evidence rows.
  - Acceptance:
    - `JD đã lưu` is directly after `Agent runs` and preserves existing vertical rail, keyboard selection, collapsed mode, drawer, proportions, and chat visibility.
    - Rows/details/actions match exact currentness rules, including visible `Cần đánh giá lại` for stale results, use one selected detail, name the Job in confirmation, and retain safe state on failures.
    - Existing score/evidence components and component labels are reused; long labels remain accessible and no visible title/action overlap or redundant heading is introduced; modified oversized owners do not grow unless an equivalent focused extraction reduces them in the same task.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-navigation.test.tsx src/test/match-card.test.tsx` -> PASS evidence: exit `0` with tab, action, a11y, layout, and renderer-reuse assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Missing pinned Astryx documentation/tooling is `BLOCKED_ENVIRONMENT`; undocumented required component behavior is `BLOCKED_MISSING_REF`; a root UI fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`.
  - Files: `frontend/src/features/jobs/SavedJobsPanel.tsx`, `frontend/src/features/jobs/SavedJobDetail.tsx`, `frontend/src/features/jobs/JobDeleteDialog.tsx`, `frontend/src/features/observability/observabilityTabs.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/features/observability/ObservabilityTabList.tsx`, `frontend/src/features/observability/types.ts`, `frontend/src/features/observability/observability.css`, `frontend/src/test/saved-jobs-panel.test.tsx`, `frontend/src/test/observability-navigation.test.tsx`, `frontend/src/test/match-card.test.tsx`

## Mandatory Batch07 - Durable Zero-Result Chat Recovery

### Goal

Replace a blank successful zero-result `match_jobs` projection with one source-bound recovery card that saves/evaluates deterministically and reuses accepted persisted-result/sidebar paths.

### Dependencies

- Batch06 is accepted; API, client, state invalidation, and MatchCard rendering are stable.

### Scope Boundary

Own strict zero-result presentation/action state, durable initiating-message projection, narrow callback wiring, targeted invalidation, and chat tests. Exclude failed/malformed/nonzero changes, Agent/tool logic, second stores, composer inference, and chat redesign.

### Tasks

- [ ] (07A): Bind the zero-result recovery card to its durable initiating message
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch07 - Durable Zero-Result Chat Recovery` > `(07A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `### Zero-Result Chat UX` and `## Implementation` item 8; `docs/plans/Master_plan.md` > `### 15.5 Match result card` and `### 15.6 Observability sidebar boundaries`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(07A)` -> task authority
    - source-zero-result: repository `docs/plans/Plan_10.md` > `### Zero-Result Chat UX` -> card/callback authority
    - durable-row-owner: repository `frontend/src/features/chat/components/ChatMessageRow.tsx` > `toolsForAssistantDisplay` and `matchJobsResultForTools`, plus `frontend/src/features/chat/history.ts` -> message/run/tool projection authority
    - chat-owner: repository `frontend/src/features/chat/ChatPage.tsx`, `ChatMessages.tsx`, and `frontend/src/app/App.tsx` -> sole chat state/callback wiring
    - client-result-owner: repository `frontend/src/features/jobs/api.ts`, `MatchCard.tsx`, and `matchResult.ts` -> accepted action/result authority
    - validation-empty-card: repository `docs/plans/Plan_10.md` > `## Verification` > `Frontend focused` and `Agent/chat regression` -> required evidence
  - Source Requirements:
    - Render exactly one card only for a strictly parsed successful `match_jobs` result with `count=0`; use heading `Chưa có kết quả đánh giá` and CTA `Lưu JD & đánh giá lại` plus one short nontechnical explanation.
    - Resolve `source_message_id` from the same durable user-message/run/tool relationship already used for displayed tool activity; never infer from latest composer text/message.
    - Pass one narrow action callback through `ChatPage`, disable the CTA while pending, and do not create a second chat/SSE/store path.
    - On created/current success, render the returned persisted result through existing `MatchCard`/score components and invalidate saved-JD caches; on unavailable/error, keep the card and show one safe retry/resubmit instruction without success claim.
    - Never render the recovery CTA for failed, malformed, non-`match_jobs`, or nonzero payloads.
  - Dependencies: Batch06 accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/chat/components/EmptyMatchResultCard.tsx`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/useSavedJobRecovery.ts`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/jobs/api.ts`, `frontend/src/test/empty-match-card.test.tsx`, `frontend/src/test/match-card.test.tsx`, `frontend/src/test/chat-page.test.tsx`
  - Allowed Files: the listed focused card/chat/callback/client/test files and narrow saved-JD invalidation wiring; exclude reducer/history store duplication, Agent/backend, nonzero MatchCard redesign, composer behavior, package changes, and unrelated sidebar/CV behavior.
  - Agent Work:
    1. Use `git grep` to trace durable user message IDs, run/tool projection to assistant rows, `match_jobs` strict parsing, ChatPage/App/sidebar callback patterns, and all MatchCard/cache invalidation callers.
    2. Add failing exact-copy, zero-only gating, durable-source selection, pending deduplication, created/reused/unavailable/error, persisted MatchCard reuse, and cache invalidation tests.
    3. Implement a focused card and recovery hook plus a narrow callback path using the existing durable relation and accepted jobs client; keep local action presentation separate from the sole chat reducer/SSE truth and keep oversized chat owners flat or smaller through extraction.
    4. Prove no CTA for invalid/failed/nonzero payloads, no latest-message inference, no duplicate heading/card/result, and no regression in existing durable chat hydration.
  - Output: One visible deterministic recovery card for every successful zero-result match.
  - A1 Outcome: A successful zero-result row can save/evaluate its exact initiating JD once and show the persisted MatchCard result without a second Agent decision.
  - A2 Review Focus: Strict zero-only gate, exact copy, durable message/run/tool binding, callback/store discipline, pending/error truthfulness, persisted renderer/cache reuse, nonzero/failed regressions, and oversized-file containment.
  - A3 Batch Evidence: P9-JD-01/P9-JD-06 zero-result visibility, deterministic source, lifecycle, renderer reuse, and safe-failure rows.
  - Acceptance:
    - Exactly one recovery card appears for valid successful `count=0`, with exact required copy; invalid/failed/nonmatching/nonzero payloads preserve existing behavior and never show the CTA.
    - The action submits only the exact durable initiating user message ID, stays disabled while pending, and cannot infer or submit composer/latest-message content.
    - Created/reused success displays the returned persisted result through existing MatchCard and invalidates affected saved-JD state; unavailable/error keeps truthful recovery UI without false success or a second chat store; modified oversized chat owners do not grow unless a focused extraction reduces them in the same task.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/empty-match-card.test.tsx src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-navigation.test.tsx src/test/match-card.test.tsx src/test/chat-page.test.tsx` -> PASS evidence: exit `0` with exact copy/gating/source/action/cache/render assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_saved_jobs_api.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py tests/e2e/test_demo_flow.py -q` -> PASS evidence: exit `0` with durable source and Agent/chat compatibility; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Ambiguous durable row ownership is `BLOCKED_AMBIGUOUS_REF`; a required second store/Agent change conflicts with authority and is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable frontend tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/chat/components/EmptyMatchResultCard.tsx`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/useSavedJobRecovery.ts`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/jobs/api.ts`, `frontend/src/test/empty-match-card.test.tsx`, `frontend/src/test/match-card.test.tsx`, `frontend/src/test/chat-page.test.tsx`, `frontend/src/test/saved-jobs-api.test.ts`, `frontend/src/test/saved-jobs-panel.test.tsx`, `frontend/src/test/saved-jobs-state.test.tsx`, `frontend/src/test/observability-navigation.test.tsx`

## Mandatory Batch08 - Synthetic Saved-JD Release Evidence

### Goal

Publish and execute synthetic-data-only focused/full, Compose, desktop/mobile, console, currentness, source-binding, and exact-deletion evidence for the complete Plan 10 increment.

### Dependencies

- Every task in Batch01 through Batch07 is accepted with matching final-attempt A1/A2 evidence.
- A user-managed root `.env`, Docker/Compose, free loopback ports, browser, and usable local ShopAIKey/Neo4j setup are available for direct smoke. Values are never requested or recorded.

### Scope Boundary

Own `docs/acceptance/saved_jd_evaluation_checklist.md`, completed-behavior README updates, and fresh sanitized evidence only. Do not repair product behavior, alter runtime configuration/models, use real CV/JD data, rewrite prior evidence, or create another runtime.

### Tasks

- [ ] (08A): Publish and run the synthetic saved-JD checklist and final regressions
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_10.md` > `## Mandatory Batch08 - Synthetic Saved-JD Release Evidence` > `(08A)`
  - Source of Truth: `docs/plans/Plan_10.md` > `## Implementation` items 9-10, `## Verification`, and `## Completion Contract`; `docs/plans/Master_plan.md` > `### 24.4 End-to-end smoke test`, `### Phase 9 - Saved JD library and revision-keyed evaluations`, and `## 27. Definition of Done`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_10.md` > `(08A)` -> task authority
    - validation-release: repository `docs/plans/Plan_10.md` > `## Verification` -> complete command/observation matrix
    - source-exit: repository `docs/plans/Master_plan.md` > `### Phase 9 - Saved JD library and revision-keyed evaluations` -> final exit gate
    - evidence-pattern: repository `docs/acceptance/cv_manager_checklist.md`, `observability_sidebar_checklist.md`, and `local_release_checklist.md` -> sanitized evidence conventions
    - runtime-owner: repository `README.md` > `Setup and startup` and `infrastructure/docker-compose.yml` -> existing three-service runtime
    - structure-validator: repository `docs/plans/Plan_10.md` > `## Verification` > `Plan structure` -> portfolio validation authority
  - Source Requirements:
    - Cover visible zero-result recovery, exact initiating-message binding, save/dedup/evaluate, same-context zero-call reuse, stale display after approved CV/profile/preference/version change, explicit re-evaluation, and complete Job deletion preservation.
    - Inspect desktop/mobile tab order, concise titles/actions, truncation, confirmation/focus/keyboard behavior, request lifecycle/network calls, browser console, and existing CV Manager/chat/graph behavior.
    - Run focused/full backend/frontend/static/build gates, three-service Compose health, shared plan validator, scope/secret/data hygiene, and source-file length/duplication review.
    - Record only dated sanitized PASS/FAIL observations and safe codes/counts; prohibit raw CV/JD bodies, paths, prompts, tool bodies, SQL/Cypher, stack traces, credentials, databases, provider transcripts, or screenshots containing personal data.
    - Update README only for verified completed behavior/commands. The current user-authorized existence of `docs/tasks/task_10.md` supersedes Plan 10's planning-phase “no task file” hygiene statement; product execution must not edit its authority except orchestrator-owned checkbox updates.
    - Any required command or smoke failure blocks acceptance; do not modify product/config during this docs/evidence task to force a pass.
  - Dependencies: All prior Plan 10 task IDs accepted.
  - User Action: Before direct smoke, provide a locally usable ignored root `.env` and running Docker/browser prerequisites without sharing values. Missing or invalid setup blocks this task.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/saved_jd_evaluation_checklist.md`, `README.md`
  - Allowed Files: `docs/acceptance/saved_jd_evaluation_checklist.md` and verified completed-behavior/command sections of `README.md`; exclude product code/tests/config, root `.env`, migrations, plan files, prior acceptance evidence, runtime data, screenshots with personal data, and task checkbox changes by A1.
  - Agent Work:
    1. Derive a concise synthetic checklist from Plan 10/Master verification and existing evidence conventions; inspect prior checklists for sanitization and exact PASS/FAIL row format.
    2. Run every focused/full command and the shared plan validator on final accepted product state; stop and report failures without repairing code/config.
    3. Start the documented Compose stack, use only synthetic CV/JD inputs, execute desktop/mobile/source-binding/currentness/delete/console/network checks, and record sanitized dated observations.
    4. Update README for only observed completed behavior/commands, run diff/status/secret/data/file-length/duplication hygiene, and preserve all prior evidence and user-owned files.
  - Output: One sanitized saved-JD acceptance checklist plus README commands/status grounded in fresh passing evidence.
  - A1 Outcome: The complete Plan 10 flow has fresh automated and direct synthetic PASS evidence with no secret or personal-data leakage.
  - A2 Review Focus: Final-attempt command freshness, every required checklist row, exact source/currentness/delete observations, desktop/mobile/a11y/console evidence, sanitization, README truthfulness, and no product repair in a docs-config task.
  - A3 Batch Evidence: P9-JD-01 through P9-JD-07 final validation, scope, data-hygiene, and local-demo readiness rows.
  - Acceptance:
    - Every required focused/full/static/build/plan-structure command passes on final product state and is recorded without stale output.
    - Direct synthetic evidence proves one-click source binding, current reuse, explicit stale recomputation, exact deletion preservation, concise accessible desktop/mobile UI, clean console, and healthy three-service runtime.
    - Evidence/README contain no secret, real personal data, raw document body, internal trace/query/path, false success, unrelated redesign, or unsupported completion claim.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental; py -3.13 -m pytest -q` -> PASS evidence: all exit `0` without real ShopAIKey calls; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` -> PASS evidence: exit `0`, `valid: true`, contiguous Plans 1-10, and no errors; freshness: final attempt only.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180; Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS evidence: three services healthy and API reports available; freshness: final attempt only.
    - Required: Execute every row in `docs/acceptance/saved_jd_evaluation_checklist.md` with synthetic CVs/JDs on desktop and mobile -> PASS evidence: dated sanitized PASS observations for source binding, reuse, stale/re-evaluate, delete preservation, layout/a11y/network/console; freshness: current Compose run only.
    - Required: `git diff --check; git status --short` plus inspection of changed paths, migrations, tracked data/secrets, duplicate scoring/state owners, and changed source file lengths -> PASS evidence: clean diff check and only approved source/evidence changes with no secret/personal/runtime data or new oversized owner; freshness: final attempt only.
  - Blocked Condition: Missing/invalid root environment, provider access, Docker, browser, or ports is `BLOCKED_USER_ACTION`; unavailable local command/runtime is `BLOCKED_ENVIRONMENT`; any required product/test/smoke failure needing code repair is `BLOCKED_SCOPE_CONFLICT`; any secret/personal-data exposure requires sanitization before evidence and remains `BLOCKED_SCOPE_CONFLICT` if safe evidence cannot be produced.
  - Files: `docs/acceptance/saved_jd_evaluation_checklist.md`, `README.md`
