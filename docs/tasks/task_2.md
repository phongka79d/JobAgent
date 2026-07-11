# JobAgent Plan 2 Phase 1 Execution Tasks

## Purpose

Turn `docs/plans/Plan_2.md` into an executable Phase 1 workflow that produces a
runnable local frontend, backend, SQLite source of truth, attachment storage,
Neo4j derived-data foundation, durable graph outbox, and sanitized health
boundary. This task file does not authorize chat, Agent, ingestion, matching,
public CRUD, worker, CI, or deployment behavior from later plans.

## Project Context Notes

- README status: root `README.md` was read successfully. It records Phase 0 as
  complete and explicitly authorizes Plan 2 to consume the locked decisions
  without re-running compatibility benchmarks.
- The repository currently contains only the Phase 0 compatibility scaffold:
  `backend/` has evaluation code, `frontend/` has the Astryx compatibility pin,
  and `infrastructure/` contains empty placeholder directories.
- Locked inputs include Python `>=3.13`, FastAPI `0.139.0`, Pydantic `2.12.5`,
  LangGraph `1.2.9`, Neo4j driver `6.2.0`, Astryx `0.1.4`, pypdf `6.12.2`,
  ShopAIKey `gpt-4o-mini`, and `text-embedding-3-small` at 1536 dimensions.
- React, TypeScript, Vite, SQLAlchemy 2, aiosqlite, Alembic, settings, server,
  and quality-tool versions are not yet installed. Their compatible resolutions
  must be locked when their owning scaffold task adds them; locked Phase 0
  adapter versions must not be changed incidentally.
- Root `.env.example` already contains the complete master-plan variable names;
  the real root `.env` is user-owned and ignored. No nested application `.env`
  file is permitted.
- `frontend/AGENTS.md` applies to frontend work: discover Astryx APIs through the
  pinned CLI, use public components and tokens, and keep the Phase 1 UI minimal.
- Repository searches found no existing Plan 2 settings, database, storage,
  graph, API, frontend application, or Docker implementation to reuse.
- No material conflict was found between the current README, the final Phase 0
  feasibility handoff, `Plan_2.md`, and the controlling master-plan sections.

## Authority and Scope

### Primary Source

- Primary source: `docs/plans/Plan_2.md`.
- Controlling references named by that source: `docs/plans/Master_plan.md`
  sections 3-6, 8, and 20-25, plus the approved Phase 0 handoff in
  `docs/plans/Plan_1.md` and
  `backend/evaluation/reports/phase_0_feasibility.md`.
- Source precedence: current user instruction -> `docs/plans/Plan_2.md` -> its
  named controlling references -> README and compatible repository evidence.

### Source Section Index

- `docs/plans/Plan_2.md` > `## 1. Objective` -> required runnable local
  foundation and durable data boundaries.
- `docs/plans/Plan_2.md` > `## 3. Prerequisites from Prior Phases` -> binding
  Phase 0 gates, decisions, scaffolds, and ignore rules.
- `docs/plans/Plan_2.md` > `## 4. Scope` -> mandatory backend, frontend,
  Compose, persistence, graph, outbox, health, and local-command outcomes.
- `docs/plans/Plan_2.md` > `## 5. Out of Scope` -> later-phase behavior that
  must not enter this implementation.
- `docs/plans/Plan_2.md` > `## 6. Target Directory Structure` -> likely module
  ownership and permission to split focused source modules.
- `docs/plans/Plan_2.md` > `### 7.1 Configuration contract` -> exact root
  variables, Compose loading, and prohibition on nested environment files.
- `docs/plans/Plan_2.md` > `### 7.2 SQLite ownership and schema` -> tables,
  identifiers, timestamps, foreign keys, JSON boundaries, status dimensions,
  migration safety, and checkpointer exclusion.
- `docs/plans/Plan_2.md` > `### 7.3 Attachment storage interface` -> storage
  protocol, service-generated contained paths, and policy boundary.
- `docs/plans/Plan_2.md` > `### 7.4 Graph schema bootstrap` -> constraints,
  vector index, idempotency, and rebuildable derived-data rule.
- `docs/plans/Plan_2.md` > `### 7.5 Outbox contracts` -> transactional enqueue,
  bounded claims, replay safety, state transitions, payload safety, and no worker.
- `docs/plans/Plan_2.md` > `### 7.6 Health boundary` -> component reporting and
  required sanitization.
- `docs/plans/Plan_2.md` > `## 8. Implementation Steps` -> required work
  sequence and focused test coverage.
- `docs/plans/Plan_2.md` > `## 9. Verification & Testing Plan` -> local exit
  evidence for quality, migration, Compose, health, persistence, graph, and scope.
- `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack` -> approved
  technologies and FastAPI version floor.
- `docs/plans/Master_plan.md` > `### 4.1 Ownership rules` -> SQLite, Neo4j,
  uploaded-file, frontend, and application-service ownership.
- `docs/plans/Master_plan.md` > `### 6.1 Application tables` -> essential table
  fields and responsibilities.
- `docs/plans/Master_plan.md` > `### 6.3 Job status dimensions` -> independent
  job-processing, quality, graph-sync, and record status domains.
- `docs/plans/Master_plan.md` > `### 8.3 Constraints and indexes` -> exact graph
  uniqueness and 1536-dimensional cosine vector index.
- `docs/plans/Master_plan.md` > `### 8.4 Graph safety rules` -> derived-only,
  canonical identity, ignored-duplicate, and rebuild requirements.
- `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` -> bounded
  failure behavior, especially persistence during Neo4j unavailability.
- `docs/plans/Master_plan.md` > `## 21. SQLite-to-Neo4j Synchronization` ->
  transactional outbox, retry, idempotency, and rebuild contracts.
- `docs/plans/Master_plan.md` > `## 22. Security and Privacy` -> localhost,
  secret, untrusted-data, and logging boundaries.
- `docs/plans/Master_plan.md` > `## 23. Environment Configuration` -> exact
  single-root configuration contract.
- `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` -> local-only,
  fake-provider, integration, and command requirements.
- `docs/plans/Master_plan.md` > `## 25. Implementation Phases` -> Phase 1 tasks
  and exit gate.
- `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)` ->
  locked compatibility inputs and no-rebenchmark rule.

### Approved Architecture and Constraints

- Keep exactly three product working folders: `frontend/`, `backend/`, and
  `infrastructure/`; root files own project-wide configuration and documentation.
- SQLite is the only canonical application store. Neo4j is derived and fully
  rebuildable, and uploaded bytes live in persistent filesystem storage rather
  than SQLite blobs.
- The frontend communicates only with FastAPI and receives only `VITE_`-prefixed
  public configuration. Backend and provider secrets never enter frontend assets.
- Preserve the single root `.env`/`.env.example` contract. Never create, inspect,
  log, or commit real credentials while implementing these tasks.
- Use UUIDs except documented singleton rows, UTC timestamps, explicit foreign
  keys, and repository-boundary validation for structured JSON.
- Keep the four job status dimensions independent. Do not model LangGraph-owned
  checkpoint tables in application metadata.
- Use the selected 1536-dimensional embedding contract for the cosine Job vector
  index. Do not add another provider, vector store, parser, UI system, or model.
- Outbox enqueue participates in the caller's SQLite transaction; replay is
  idempotent; polling is bounded and invoked only at explicit lifecycle points.
  Do not create a continuous worker or worker service.
- Bind published frontend/backend ports to `127.0.0.1`. Keep Neo4j ports internal
  unless an explicit localhost-only development profile is added.
- Search before adding helpers, refactor reusable logic instead of duplicating it,
  keep modules focused, and prefer the minimum source-supported implementation.
- Normal automated tests use fakes or local containers and never call ShopAIKey.
  Validation remains local-only; do not add CI configuration.
- The only public Phase 1 application endpoint is `GET /api/health`. Chat, file
  upload, CRUD, Agent, extraction, matching, and synchronization payload generation
  remain outside this task file.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Runnable backend/frontend scaffolds and one typed root configuration contract | (01A), (01B) | None |
| Batch02 | Complete SQLite source-of-truth schema with repeatable migration lifecycle | (02A), (02B) | Batch01 |
| Batch03 | Contained staged/active attachment persistence | (03A) | Batch02 |
| Batch04 | Idempotent Neo4j schema, durable outbox, and safe rebuild entrypoint | (04A), (04B), (04C) | Batch02 |
| Batch05 | Production-shaped local Compose runtime, sanitized health, and Phase 1 exit evidence | (05A), (05B), (05C) | Batch03, Batch04 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_2_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_2_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Application Scaffolds and Root Configuration

### Goal

Replace the Phase 0-only scaffolds with minimal runnable backend and frontend
projects that consume the locked decisions and share one validated root
configuration contract.

### Dependencies

- Phase 0 final decision table remains all-pass and Plan 2 remains authorized.
- Existing Phase 0 diagnostics, fixtures, and locked adapter evidence remain
  available and must not be reimplemented.

### Scope Boundary

This batch owns project scaffolding, dependency locking, local quality commands,
typed settings, and a minimal neutral frontend shell. It does not own persistence,
health component checks, public product flows, or Agent behavior.

### Tasks

- [x] (01A): Establish the runnable FastAPI project and typed root settings
  - Source of Truth: `docs/plans/Plan_2.md` > `## 4. Scope`; `docs/plans/Plan_2.md` > `### 7.1 Configuration contract`; `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack`; `docs/plans/Master_plan.md` > `## 23. Environment Configuration`
  - Source Requirements:
    - Materialize an importable FastAPI application on Python `>=3.13` with FastAPI `0.139.0`, Pydantic v2, async SQLAlchemy 2, aiosqlite, Alembic, typed settings, and a production server command.
    - Load every master-plan variable from the root environment contract, validate required values and numeric bounds without logging values, and expose only explicitly safe configuration to callers.
    - Provide local backend lint, type-check, and test commands while preserving Phase 0 diagnostic dependencies and behavior.
  - Dependencies: None
  - User Action: None; tests must inject synthetic settings and must not read or modify the user's real root `.env`.
  - Agent Work:
    1. Search existing backend configuration and packaging before changing `pyproject.toml`; retain locked dependencies and reuse any compatible Phase 0 environment-loading behavior.
    2. Promote the approved Plan 2 runtime dependencies, add only required SQLAlchemy/settings/server/quality dependencies, and lock compatible exact resolutions without altering locked adapter versions.
    3. Create focused application/configuration modules, a minimal FastAPI app factory or app object, and documented local run/lint/type-check/test commands.
    4. Add tests for defaults, required secrets, URL/origin/model/dimension/range validation, root environment loading, safe serialization, and non-disclosure in errors.
  - Output: Importable FastAPI foundation, typed settings contract, exact backend dependency decisions, and executable backend quality commands.
  - Acceptance:
    - All variables from master section 23 are represented once with correct types/defaults or required-value rules; invalid settings fail without revealing secret values.
    - `backend/pyproject.toml` retains Phase 0 capabilities, contains the minimal production/test toolchain, and provides a runnable application import path.
    - No endpoint other than framework-generated documentation exists yet, and no ShopAIKey network call occurs during import, startup, or tests.
  - Validation:
    - Required: `cd backend; python -m pip install -e ".[test]"` -> the backend and exact selected dependencies install successfully.
    - Required: `cd backend; python -m pytest -q tests/test_config.py` -> settings and secret-safety tests pass without network access.
    - Required: `cd backend; python -m ruff check app tests` -> backend lint passes.
    - Required: `cd backend; python -m mypy app` -> backend application type-check passes.
  - Blocked Condition: A locked Phase 0 version cannot resolve with the required foundation stack; changing that locked adapter requires explicit approval rather than silent substitution.
  - Files: `backend/pyproject.toml`, backend lockfile if adopted, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/tests/test_config.py`

- [x] (01B): Materialize the React, TypeScript, Vite, and Astryx neutral frontend
  - Source of Truth: `docs/plans/Plan_2.md` > `## 4. Scope`; `docs/plans/Plan_2.md` > `## 6. Target Directory Structure`; `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`
  - Source Requirements:
    - Convert the Astryx-only Phase 0 scaffold into a runnable React/TypeScript/Vite application while keeping both Astryx packages pinned exactly at `0.1.4`.
    - Import the Astryx reset/theme CSS once, use a neutral theme and public component APIs, and expose only `VITE_API_BASE_URL` to frontend code.
    - Provide local frontend lint, type-check, test, build, and development commands without implementing later-phase UX.
  - Dependencies: None
  - User Action: None
  - Agent Work:
    1. Run the pinned Astryx discovery workflow from `frontend/AGENTS.md` and reuse the verified Phase 0 public API matrix instead of guessing component APIs.
    2. Add the minimum React/Vite application, a neutral Astryx shell with no product workflow, typed public environment access, and focused smoke tests.
    3. Install and lock compatible React/TypeScript/Vite and minimal quality/test dependencies while preserving exact Astryx pins and the existing compatibility command.
    4. Add deterministic lint, type-check, test, build, and dev scripts; verify that backend-only environment names and secrets cannot enter the client bundle.
  - Output: Runnable minimal frontend application and exact frontend lockfile with Astryx compatibility preserved.
  - Acceptance:
    - The application renders through public Astryx components with its required CSS and neutral theme, without chat, upload, profile, job, or matching behavior.
    - `package-lock.json` resolves exact Astryx `0.1.4`; all new product-stack versions are locked; no nested `.env` file or backend-only secret reference exists.
    - Frontend commands are single-purpose and the production build succeeds.
  - Validation:
    - Required: `cd frontend; npm ci --ignore-scripts` -> the exact lockfile installs.
    - Required: `cd frontend; npm run check:astryx` -> the locked public Astryx API matrix still passes.
    - Required: `cd frontend; npm run lint; npm run typecheck; npm run test -- --run; npm run build` -> all frontend quality gates pass.
    - Required: `rg -n "NEO4J_|SHOPAIKEY_|SQLITE_PATH|FILES_DIR" frontend/src` -> no backend-only configuration reference is found.
  - Blocked Condition: Astryx `0.1.4` cannot resolve or its locked public APIs no longer pass; the Astryx adapter decision must be re-approved before changing versions.
  - Files: `frontend/package.json`, `frontend/package-lock.json`, `frontend/index.html`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `frontend/src/app/`, `frontend/src/test/`

## Mandatory Batch02 - SQLite Source of Truth and Migrations

### Goal

Create the complete canonical application schema and a migration lifecycle that is
safe on fresh and already-initialized persistent SQLite storage.

### Dependencies

- (01A) provides typed settings, backend packaging, and quality commands.

### Scope Boundary

This batch owns database metadata, async engine/session lifecycle, and the initial
migration. It does not implement domain workflows, LangGraph checkpoints, public
CRUD, attachment file operations, or graph synchronization behavior.

### Tasks

- [ ] (02A): Implement the async SQLite lifecycle and complete application model metadata
  - Source of Truth: `docs/plans/Plan_2.md` > `### 7.2 SQLite ownership and schema`; `docs/plans/Master_plan.md` > `### 4.1 Ownership rules`; `docs/plans/Master_plan.md` > `### 6.1 Application tables`; `docs/plans/Master_plan.md` > `### 6.3 Job status dimensions`
  - Source Requirements:
    - Implement async SQLAlchemy 2 engine/session ownership for the configured SQLite path and all eleven master-defined application tables.
    - Use UUID identifiers except documented singleton rows, UTC timestamps, explicit foreign keys, and independent enumerated job status dimensions.
    - Preserve the exact independent values: `processing_status` = `received | processing | processed | failed`; `jd_quality` = `full | partial | unscorable`; `graph_sync_status` = `not_required | pending | synced | failed`; `record_status` = `active | ignored_duplicate`.
    - Keep raw inputs and canonical state in SQLite, keep uploaded bytes out of blobs, and exclude LangGraph-owned checkpoint tables.
  - Dependencies: (01A)
  - User Action: None
  - Agent Work:
    1. Search all backend schemas/evaluation code for reusable types or naming before defining model helpers; keep base, session, mixins, and domain model files focused.
    2. Implement engine/session lifecycle with SQLite-safe connection behavior, explicit transaction ownership, and test isolation.
    3. Define `attachments`, `candidate_profile`, `profile_drafts`, `job_preferences`, `job_posts`, `conversation`, `chat_messages`, `agent_runs`, `tool_executions`, `memory_facts`, and `graph_sync_outbox` with required fields, constraints, relationships, and indexes.
    4. Add metadata/session tests covering table inventory, singleton and uniqueness rules, foreign keys, UTC timestamps, JSON storage boundaries, independent statuses, and rollback behavior.
  - Output: Complete SQLAlchemy application metadata and stable async session boundary.
  - Acceptance:
    - SQLAlchemy metadata contains exactly the eleven application tables required by Plan 2 and contains no LangGraph checkpoint model.
    - Status values cannot be conflated, foreign-key enforcement is enabled, UUID/singleton rules are explicit, and session rollback does not leak partial state.
    - Structured JSON columns are not exposed through an unvalidated generic public repository API.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/db/test_models.py tests/db/test_session.py` -> schema and lifecycle tests pass against temporary SQLite files.
    - Required: `cd backend; python -m ruff check app/db tests/db; python -m mypy app/db` -> focused lint and type-check pass.
  - Blocked Condition: The plan and master source cannot be reconciled on a required field, identity, foreign key, or status contract without changing canonical ownership.
  - Files: `backend/app/db/base.py`, `backend/app/db/session.py`, `backend/app/db/models/*.py`, `backend/tests/db/test_models.py`, `backend/tests/db/test_session.py`

- [ ] (02B): Create and prove the repeatable initial Alembic migration
  - Source of Truth: `docs/plans/Plan_2.md` > `### 7.2 SQLite ownership and schema`; `docs/plans/Plan_2.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 24.2 Backend integration tests`; `docs/plans/Master_plan.md` > `## 25. Implementation Phases`
  - Source Requirements:
    - Produce one reviewed initial migration for the complete application metadata.
    - Upgrade a fresh SQLite file and safely rerun `upgrade head` against an already-initialized persistent file without destructive reset or duplicate objects.
    - Keep Alembic and runtime metadata aligned and leave LangGraph checkpoint creation to its later owner.
  - Dependencies: (02A)
  - User Action: None
  - Agent Work:
    1. Configure Alembic to consume the typed SQLite path and application metadata without importing network clients or reading the user's real `.env` in tests.
    2. Generate the initial revision, inspect every operation against the source schema, and remove autogenerated noise or accidental checkpoint objects.
    3. Add integration tests that upgrade a new temporary file, inspect tables/constraints/indexes, rerun the upgrade on the same file, and compare the migrated schema with model metadata.
    4. Document the single-purpose local migration command without adding an automatic destructive downgrade/reset path.
  - Output: Initial Alembic revision and repeatable local migration command.
  - Acceptance:
    - Fresh and second-run upgrades both succeed and produce the same eleven-table application schema at one head revision.
    - Migration operations preserve existing initialized data and contain no broad drop/reset behavior or LangGraph checkpoint tables.
    - Runtime metadata and migrated schema agree on required columns, foreign keys, uniqueness, indexes, and status constraints.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/integration/test_migrations.py` -> fresh, initialized, data-preservation, and metadata-parity checks pass.
    - Required: `cd backend; python -m alembic -c alembic.ini heads` -> exactly one expected head is reported.
  - Blocked Condition: Autogeneration or SQLite limitations cannot express a source-required constraint without a reviewed explicit migration operation.
  - Files: `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/*.py`, `backend/tests/integration/test_migrations.py`, `README.md`

## Mandatory Batch03 - Staged and Active Attachment Persistence

### Goal

Provide contained filesystem mechanics and metadata operations for staged and
active attachments without implementing Plan 4 validation or replacement policy.

### Dependencies

- (02B) provides the migrated attachment metadata table and transaction boundary.

### Scope Boundary

This batch owns storage-generated paths, staging/promotion/open/delete mechanics,
and staged/active metadata persistence. MIME inspection, magic bytes, page limits,
CV parsing, upload endpoints, approval, and active-profile replacement are excluded.

### Tasks

- [ ] (03A): Implement contained attachment storage and staged/active metadata operations
  - Source of Truth: `docs/plans/Plan_2.md` > `### 7.3 Attachment storage interface`; `docs/plans/Plan_2.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 4.1 Ownership rules`; `docs/plans/Master_plan.md` > `### 6.1 Application tables`
  - Source Requirements:
    - Implement async `stage`, `promote`, `delete`, and `open` behavior compatible with the declared `AttachmentStorage` protocol.
    - Generate all paths inside `FILES_DIR`, separate staged and active locations, reject traversal/symlink escapes, and never accept a user-supplied storage path.
    - Persist staged/active attachment metadata transactionally while leaving content-policy and profile-replacement decisions to Plan 4.
  - Dependencies: (02B)
  - User Action: None
  - Agent Work:
    1. Search for existing hashing, streaming, path, and repository helpers before adding focused storage/repository modules.
    2. Implement bounded-path resolution and chunked async staging with cleanup on interrupted writes; implement atomic promotion where the filesystem permits it.
    3. Implement narrow attachment metadata operations that accept validated metadata and service-generated paths, participate in caller-owned transactions, and enforce staged/active state transitions only.
    4. Add tests for round trips, chunking, missing files, idempotent cleanup, interrupted writes, traversal, absolute paths, symlink escapes, promotion, transaction rollback, and path non-disclosure.
  - Output: Filesystem-backed `AttachmentStorage` implementation and attachment metadata repository with staged/active mechanics.
  - Acceptance:
    - Every stored path resolves under `FILES_DIR`; traversal, absolute-path, and symlink escape attempts fail without reading or deleting outside content.
    - Staging never leaves a promoted partial file, promotion returns an active service path, and delete/open handle missing or invalid state predictably.
    - No MIME, magic-byte, page-count, parsing, approval, or profile replacement policy is implemented.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_attachment_storage.py tests/repositories/test_attachments.py` -> storage safety and metadata transaction tests pass.
    - Required: `cd backend; python -m ruff check app/services/attachment_storage.py app/repositories/attachments.py tests/services tests/repositories; python -m mypy app/services/attachment_storage.py app/repositories/attachments.py` -> focused quality checks pass.
  - Blocked Condition: The target filesystem cannot provide a safe contained staging/promotion operation and no source-compatible standard-library implementation is available.
  - Files: `backend/app/services/attachment_storage.py`, `backend/app/repositories/attachments.py`, `backend/tests/services/test_attachment_storage.py`, `backend/tests/repositories/test_attachments.py`

## Mandatory Batch04 - Derived Graph and Durable Synchronization Contracts

### Goal

Provide an idempotent Neo4j lifecycle/schema, a durable replay-safe SQLite outbox,
and a deliberately incomplete but safe graph rebuild entrypoint.

### Dependencies

- (02B) provides stable SQLite models and migrations.
- (01A) provides settings and backend lifecycle ownership.

### Scope Boundary

This batch owns generic graph infrastructure only. Candidate/Job payload builders,
continuous polling, a worker service, embeddings, domain synchronization, matching,
and full rebuild loaders remain deferred.

### Tasks

- [ ] (04A): Implement Neo4j lifecycle, health probe, and idempotent schema bootstrap
  - Source of Truth: `docs/plans/Plan_2.md` > `### 7.4 Graph schema bootstrap`; `docs/plans/Master_plan.md` > `### 8.3 Constraints and indexes`; `docs/plans/Master_plan.md` > `### 8.4 Graph safety rules`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Own the async Neo4j driver lifecycle and a bounded health probe without making Neo4j canonical.
    - Idempotently create unique constraints for `Candidate.id`, `Job.id`, `Skill.canonical_key`, and `JobFamily.canonical_key` plus a 1536-dimensional cosine vector index on `Job.embedding`.
    - Treat Neo4j unavailability as a component failure without losing or changing SQLite data.
  - Dependencies: (01A)
  - User Action: None for fake-based tests; a populated root `NEO4J_PASSWORD` is required only for optional live-container validation.
  - Agent Work:
    1. Search for existing provider/client lifecycle patterns and keep connection, schema, and query responsibilities in focused modules.
    2. Implement lazy startup/shutdown, bounded connectivity verification, sanitized error classification, and dependency-injectable driver/session boundaries.
    3. Implement named `IF NOT EXISTS` constraints and vector-index setup using the configured locked dimension and cosine similarity.
    4. Add fake-driver tests for query parameters, idempotent reruns, lifecycle closure, timeout/unavailability, and error redaction.
  - Output: Reusable Neo4j client and idempotent graph-schema bootstrap primitives.
  - Acceptance:
    - Two schema-setup runs issue only idempotent, parameter-safe operations and create no duplicate logical constraint or index.
    - The vector index uses the configured value fixed at 1536 and cosine similarity; no alternate graph/vector store or canonical-only graph state exists.
    - Health/lifecycle failures expose only sanitized codes/status and never credentials, URIs with credentials, queries containing data, or stack traces.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/graph/test_client.py tests/graph/test_schema.py` -> lifecycle, failure, exact-schema, and idempotency tests pass with fakes.
    - Required: `cd backend; python -m ruff check app/graph tests/graph; python -m mypy app/graph` -> focused graph quality checks pass.
    - Optional: run the schema test marked `neo4j` against the later Compose service -> confirms live server syntax and rerun behavior after (05A).
  - Blocked Condition: The selected Neo4j Community image/version cannot support the source-required vector-index syntax with driver `6.2.0`; changing graph technology or embedding dimensions requires approval.
  - Files: `backend/app/graph/client.py`, `backend/app/graph/schema.py`, `backend/tests/graph/test_client.py`, `backend/tests/graph/test_schema.py`

- [ ] (04B): Implement the transactional replay-safe graph outbox repository
  - Source of Truth: `docs/plans/Plan_2.md` > `### 7.5 Outbox contracts`; `docs/plans/Master_plan.md` > `## 21. SQLite-to-Neo4j Synchronization`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Support enqueue in the caller's SQLite transaction, bounded pending claims, mark-synced, and mark-failed with visible attempt count.
    - Give every logical operation stable replay-safe identity and keep pending/failed work durable while Neo4j is unavailable.
    - Permit only SQLite identifiers and canonical structured data in payloads; reject filesystem paths, credentials, and raw documents; do not poll continuously.
  - Dependencies: (02B)
  - User Action: None
  - Agent Work:
    1. Inspect the outbox model and all prospective callers before defining the narrow repository and payload contract; refactor the model migration only if a source-required idempotency field is missing.
    2. Implement deterministic operation identity, uniqueness conflict behavior, enqueue without internal commit, deterministic bounded claim ordering, and explicit synced/failed transitions.
    3. Validate structured payloads at the repository boundary and fail closed on prohibited keys/content categories without logging payload values.
    4. Add concurrency-aware tests for same-transaction rollback, duplicate enqueue, bounded claims, replay, attempt increments, failure recovery, ordering, and payload rejection.
  - Output: Durable generic outbox repository and validated replay-safe operation interface.
  - Acceptance:
    - Rolling back a canonical SQLite write also rolls back its enqueue; replaying the same operation creates one logical row and never resets attempts or terminal state unexpectedly.
    - Claims are bounded and deterministic, state transitions are persisted, and Neo4j failure leaves retryable SQLite evidence.
    - No timer, background loop, worker service, Candidate/Job payload builder, filesystem path, secret, or raw document is introduced.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/repositories/test_graph_outbox.py` -> transaction, idempotency, claim, replay, failure, and payload-safety tests pass.
    - Required: `cd backend; python -m ruff check app/repositories/graph_outbox.py tests/repositories/test_graph_outbox.py; python -m mypy app/repositories/graph_outbox.py` -> focused quality checks pass.
  - Blocked Condition: The approved SQLite schema lacks a field or uniqueness rule required for stable operation identity and cannot be corrected through the still-initial migration without contradicting the source.
  - Files: `backend/app/repositories/graph_outbox.py`, `backend/app/db/models/graph_outbox.py`, initial migration only if required, `backend/tests/repositories/test_graph_outbox.py`

- [ ] (04C): Add the safe graph rebuild command skeleton
  - Source of Truth: `docs/plans/Plan_2.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `### 8.4 Graph safety rules`; `docs/plans/Master_plan.md` > `### 21.4 Rebuild`
  - Source Requirements:
    - Provide one infrastructure command that can safely clear only JobAgent-derived graph data and recreate constraints/vector index.
    - Make the later SQLite loaders, embedding recomputation, entity verification, and sync-state updates explicit unimplemented stages rather than pretending the full rebuild exists.
    - Reuse the graph client/schema primitives and require deliberate destructive confirmation; never clear an entire Neo4j database indiscriminately.
  - Dependencies: (04A), (04B)
  - User Action: Explicitly confirm destructive execution only when running against a disposable/local JobAgent Neo4j database; no confirmation is needed for `--help` or dry-run validation.
  - Agent Work:
    1. Search for existing CLI/config patterns and reuse the backend graph lifecycle instead of duplicating driver or schema logic.
    2. Implement a dry-run-first command with explicit confirmation for clearing only the approved `Candidate`, `Job`, `Skill`, and `JobFamily` derived subgraph and then reapplying schema.
    3. Represent later loader/recompute/verification stages as named, explicit not-implemented boundaries that fail safely before any false success report.
    4. Add tests for help/dry-run, confirmation, scoped Cypher, schema reuse, failure exit codes, secret-safe output, and the deliberate unimplemented-stage result.
  - Output: Safe, testable graph rebuild skeleton with honest deferred stages.
  - Acceptance:
    - Default execution is non-destructive; destructive clearing requires an explicit flag/confirmation and contains no database-wide unlabeled delete.
    - Schema recreation delegates to (04A), and deferred data-loading stages are visible with non-success status rather than fabricated completion.
    - The command prints no password, credential-bearing URI, raw payload, or document content.
  - Validation:
    - Required: `python infrastructure/scripts/rebuild_graph.py --help` -> usage and safety controls are displayed without connecting or exposing configuration values.
    - Required: `cd backend; python -m pytest -q tests/infrastructure/test_rebuild_graph.py` -> dry-run, scope, confirmation, exit, reuse, and redaction tests pass.
  - Blocked Condition: A safe JobAgent-only deletion boundary cannot be expressed for the approved labels without risking unrelated graph data; destructive execution remains disabled pending an approved isolation rule.
  - Files: `infrastructure/scripts/rebuild_graph.py`, `backend/tests/infrastructure/test_rebuild_graph.py`

## Mandatory Batch05 - Composed Runtime, Health, and Exit Evidence

### Goal

Run the complete Phase 1 foundation through Docker Compose, expose a sanitized
component health boundary, prove persistence/idempotency, and document the exact
local commands for the Plan 3 handoff.

### Dependencies

- (03A) provides attachment/filesystem persistence.
- (04A), (04B), and (04C) provide graph and outbox primitives.
- All Batch01 and Batch02 tasks are accepted.

### Scope Boundary

This batch owns Dockerfiles, Compose wiring, application lifecycle integration,
health reporting, final local validation, and README updates. It must not add a
worker, CI, public product endpoint, provider call, or later-phase business flow.

### Tasks

- [ ] (05A): Create production-shaped Dockerfiles and local Compose services
  - Source of Truth: `docs/plans/Plan_2.md` > `## 4. Scope`; `docs/plans/Plan_2.md` > `### 7.1 Configuration contract`; `docs/plans/Plan_2.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 22.1 Network exposure`
  - Source Requirements:
    - Build frontend and backend images and compose frontend, backend, and Neo4j Community services from `infrastructure/docker-compose.yml`.
    - Load the single root environment contract, bind published frontend/backend ports to `127.0.0.1`, and keep Neo4j ports internal by default.
    - Persist SQLite/files and Neo4j data across ordinary container/service restarts; do not add a worker service.
  - Dependencies: (01A), (01B)
  - User Action: Before live startup, populate required non-placeholder values, especially `NEO4J_PASSWORD`, in the ignored root `.env`; do not paste values into reports or commands.
  - Agent Work:
    1. Search repository Docker/config patterns and reuse the exact application/package commands owned by Batch01.
    2. Create focused, production-shaped frontend/backend Dockerfiles with reproducible installs, non-root runtime where supported, correct build contexts, and no copied root secrets/private evaluation inputs.
    3. Pin a Neo4j Community image compatible with the approved driver/vector-index contract; define dependency/health ordering, internal networking, localhost-only publications, and named persistence volumes.
    4. Validate Compose interpolation with `.env.example`, image builds, root-env ownership, restart behavior, and absence of worker/extra datastore services.
  - Output: Reproducible three-service local Compose definition and persistent volume wiring.
  - Acceptance:
    - Compose defines exactly frontend, backend, and Neo4j services; frontend/backend publish only on `127.0.0.1`; Neo4j has no default host publication.
    - Backend receives backend-only variables at runtime, frontend build/runtime receives only approved public configuration, and no `.env` is copied into an image.
    - SQLite/files and Neo4j use named persistent storage that survives `restart` and `down` without the volume-removal flag.
  - Validation:
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml config` -> configuration resolves with three services, root env wiring, localhost publications, and named volumes.
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml build` -> frontend/backend images build from clean contexts without secret files.
    - Required: `rg -n "worker|qdrant|0\.0\.0\.0:" infrastructure/docker-compose.yml` -> no worker, Qdrant, or all-interface published binding is present.
    - Optional: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d` -> all services start when the user-owned root secrets are available.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` for live startup when the ignored root `.env` lacks a valid Neo4j password; static config/build validation remains required.
  - Files: `infrastructure/docker/backend.Dockerfile`, `infrastructure/docker/frontend.Dockerfile`, `infrastructure/docker-compose.yml`, `.dockerignore`, focused service config under `infrastructure/` only if required

- [ ] (05B): Integrate lifecycle dependencies and expose sanitized component health
  - Source of Truth: `docs/plans/Plan_2.md` > `### 7.6 Health boundary`; `docs/plans/Plan_2.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`; `docs/plans/Master_plan.md` > `## 22. Security and Privacy`
  - Source Requirements:
    - Expose `GET /api/health` with overall status and SQLite, filesystem, and Neo4j component states.
    - Integrate database, filesystem, graph schema/client startup and shutdown at the application lifecycle boundary without making Neo4j availability a prerequisite for preserving SQLite state.
    - Never expose credentials, connection strings, unsafe absolute paths, provider headers, stack traces, raw content, or secret-bearing exceptions.
  - Dependencies: (02B), (03A), (04A), (05A)
  - User Action: None for fake-based tests; live healthy-state validation requires the populated root `.env` from (05A).
  - Agent Work:
    1. Inspect every lifecycle owner and health caller before wiring them into the FastAPI lifespan; keep probe orchestration separate from component clients.
    2. Add typed health response schemas and bounded probes for SQLite connectivity, writable contained file storage, and Neo4j connectivity/schema setup.
    3. Define deterministic overall/component status behavior for healthy and degraded/unavailable states while keeping the endpoint responsive and output sanitized.
    4. Add API tests for complete healthy responses, each component failure, timeouts, cleanup, CORS exact origin, and leakage of paths, URIs, credentials, headers, exceptions, or stack traces.
  - Output: Lifecycle-managed foundation and sanitized `GET /api/health` endpoint.
  - Acceptance:
    - The endpoint reports all three named components and an overall state through a validated schema; each injected failure is visible only as a safe state/code.
    - Startup/shutdown closes database and graph resources, schema setup is idempotent, and Neo4j failure does not mutate or delete SQLite/filesystem state.
    - Route inspection finds no public endpoint other than `/api/health` plus framework documentation routes.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/api/test_health.py tests/test_lifecycle.py` -> healthy, degraded, timeout, cleanup, CORS, and leakage tests pass.
    - Required: `cd backend; python -m ruff check app/api app/schemas/health.py app/main.py tests/api tests/test_lifecycle.py; python -m mypy app/api app/schemas/health.py app/main.py` -> focused quality checks pass.
    - Optional: `Invoke-RestMethod http://127.0.0.1:8000/api/health | ConvertTo-Json -Depth 4` after Compose startup -> only overall and sanitized component fields are returned.
  - Blocked Condition: A required live component cannot start because user-owned root credentials are missing; fake-based behavior and sanitization tests must still complete.
  - Files: `backend/app/api/health.py`, `backend/app/schemas/health.py`, `backend/app/main.py`, `backend/tests/api/test_health.py`, `backend/tests/test_lifecycle.py`

- [ ] (05C): Prove the local foundation and publish the Plan 3 handoff commands
  - Source of Truth: `docs/plans/Plan_2.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_2.md` > `## 10. Handoff Notes for Plan 3 (Master Phase 2)`; `docs/plans/Master_plan.md` > `### 24.5 Local verification commands`; `docs/plans/Master_plan.md` > `## 25. Implementation Phases`
  - Source Requirements:
    - Prove backend/frontend quality, fresh and initialized migrations, three-service startup, sanitized health, persistent SQLite/files/Neo4j storage, schema idempotency, and replay-safe outbox behavior.
    - Document exact local lint, type-check, migration, test, build/start, health, graph-schema/rebuild, and shutdown commands.
    - Hand Plan 3 stable configuration, database, attachment, graph, outbox, and health primitives without adding Plan 3 behavior.
  - Dependencies: (05A), (05B), and every earlier Plan 2 task
  - User Action: Provide a valid ignored root `.env` and a working local Docker Compose runtime for required live exit checks; never disclose secret values in evidence.
  - Agent Work:
    1. Run the complete backend and frontend command sets, migration tests, scope scans, secret/private-data scans, and Compose config/build checks; repair only Plan 2-owned gaps.
    2. Start Compose, verify the sanitized health contract, run schema setup twice, exercise outbox replay, and record safe evidence that SQLite, files, and Neo4j data persist across service restart.
    3. Confirm no nested env, worker, public CRUD/chat/upload endpoint, LangGraph execution, ShopAIKey production call, CV/JD behavior, matching, Qdrant, CI, or cloud deployment exists.
    4. Update the root README from Phase 0-only status to the evidence-backed Phase 1 commands, architecture, persistence boundaries, current limitations, and exact Plan 3 handoff.
  - Output: Green local foundation evidence, current README, and an explicit reusable Plan 3 handoff.
  - Acceptance:
    - All required local commands pass; Compose starts the three services; health is sanitized; migration and schema reruns are idempotent; ordinary restart preserves all three persistence classes.
    - README commands match actual scripts/paths and distinguish required local checks from optional Phase 0 live diagnostics.
    - Git diff and route/service/dependency scans contain only Plan 2 scope, and no secret or private source data is tracked or reported.
  - Validation:
    - Required: `cd backend; python -m ruff check app tests; python -m mypy app; python -m pytest -q` -> full backend local quality suite passes without ShopAIKey network calls.
    - Required: `cd frontend; npm ci --ignore-scripts; npm run check:astryx; npm run lint; npm run typecheck; npm run test -- --run; npm run build` -> full frontend suite and build pass.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d` followed by the documented health, double-schema-setup, migration, outbox replay, and pre/post-restart persistence checks -> all Phase 1 exit evidence passes without printing secrets.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml down` -> services stop without deleting named volumes.
    - Required: `rg --files -g '.env' -g '**/.env' frontend backend` and `rg -n "(chat|attachments/cv|profiles|jobs|match)" backend/app/api infrastructure/docker-compose.yml` -> no nested env or later-phase public/service surface is found.
    - Required: `git status --short; git diff --check` -> only intended Plan 2/report/review changes are present and no whitespace errors are reported.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when valid local root credentials or Docker Compose are unavailable after all non-live validations pass; otherwise any failed required exit check is a technical failure and Plan 3 remains blocked.
  - Files: `README.md`, existing Plan 2-owned code/config/tests only when validation exposes a same-scope defect

## Optional Future Tracks

No optional implementation track is authorized by Plan 2. All items in
`docs/plans/Plan_2.md` section 5 and all Plan 3+ behavior remain outside the
mandatory Phase 1 batch chain.
