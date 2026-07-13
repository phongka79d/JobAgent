# JobAgent Plan 2 Execution Tasks

## Purpose

Translate `docs/plans/Plan_2.md` into the mandatory, sequential work needed to
establish the Phase 1 application foundation. These tasks configure the pinned
projects, make SQLite/Alembic the complete source of truth, add filesystem and
Neo4j infrastructure primitives, expose only the health endpoint, and prove the
three-service local runtime. They do not implement production CV, JD, chat,
Agent, approval, matching, or provider behavior.

## Project Context Notes

- Root `README.md` was read before task derivation. It records all Phase 0
  batches as passed and identifies `docs/feasibility/phase_0_report.md` as the
  approved handoff for Plan 2.
- The current repository is intentionally minimal: `backend/` is an installable
  Python scaffold, `frontend/` is the pinned Astryx 0.1.4 feasibility render,
  and `infrastructure/` contains only feasibility scripts and placeholders.
- `docs/feasibility/phase_0_report.md` records
  `PHASE_0_OVERALL=PASS`, the exact Phase 0 pins, compatible intended Phase 1
  versions, and the clean bootstrap `python -m pip install -e .\backend`.
- The report does not assign exact versions to every newly required settings or
  test-tooling package. Tasks (01A) and (01B) therefore require compatibility
  verification followed by exact pins, while preserving every locked package,
  model, provider, and embedding dimension.
- The user-supplied root agent rules apply: search before writing, reuse or
  refactor shared logic, keep modules focused and ordinarily below 300 lines,
  prefer the smallest working implementation, and inspect all callers when
  changing shared behavior.
- `frontend/AGENTS.md` also applies to frontend work: discover Astryx APIs with
  the pinned CLI, use public components and tokens, and do not invent props,
  internal imports, raw layout elements, or a second styling system.
- Existing verification entry points include `npm ci`, `npm run build`,
  `python infrastructure/scripts/verify_pdf_extraction.py`, and
  `python infrastructure/scripts/diagnose_shopaikey.py`. Plan 2 must preserve
  these Phase 0 artifacts, but must not repeat live feasibility work.

## Authority and Scope

### Primary Source

- Primary authority: `docs/plans/Plan_2.md`.
- Supporting architecture authority cited by that plan:
  `docs/plans/Master_plan.md`.
- Prerequisite evidence: `docs/feasibility/phase_0_report.md`.
- Repository context only: root `README.md`, root `.env.example`,
  `backend/pyproject.toml`, `frontend/package.json`, and
  `frontend/AGENTS.md`.

### Source Section Index

- `docs/plans/Plan_2.md > ## 1. Objective` -> Phase outcome and exit boundary.
- `docs/plans/Plan_2.md > ## 3. Prerequisites from Prior Phases` -> accepted
  Phase 0 handoff.
- `docs/plans/Plan_2.md > ## 4. Scope` -> mandatory Phase 1 capabilities.
- `docs/plans/Plan_2.md > ## 5. Out of Scope` -> prohibited production
  behavior and infrastructure.
- `docs/plans/Plan_2.md > ## 6. Target Directory Structure` -> module and
  ownership boundaries.
- `docs/plans/Plan_2.md > ## 7. Technical Specifications` -> settings,
  database, storage, graph, health, and Compose contracts.
- `docs/plans/Plan_2.md > ## 8. Implementation Steps` -> execution order and
  reuse/SRP requirements.
- `docs/plans/Plan_2.md > ## 9. Verification & Testing Plan` -> required local
  evidence and failure gates.
- `docs/plans/Plan_2.md > ## 10. Handoff Notes for Plan 3 / Master Phase 2` ->
  exact downstream artifacts and reuse boundary.
- `docs/plans/Master_plan.md > ## 6. SQLite Database Contract` -> exact table,
  constraint, index, foreign-key, migration, transaction, and identity rules.
- `docs/plans/Master_plan.md > ## 8. Neo4j Derived Model > ### 8.3 Constraints
  and indexes` -> exact graph constraints and vector index.
- `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary` -> health is the
  only public endpoint owned by this phase.
- `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.1 Layout` and
  `### 15.3 Chat components` -> pinned Astryx shell foundation and discovery
  rule, without Phase 2 chat behavior.
- `docs/plans/Master_plan.md > ## 22. Local Demo Safeguards` and
  `## 23. Environment Configuration` -> loopback binding, secret hygiene, and
  one-root-environment rules.
- `docs/plans/Master_plan.md > ## 24. Local Testing Strategy` -> database,
  graph, health, and single-purpose local command evidence.
- `docs/plans/Master_plan.md > ## 25. Implementation Phases > ### Phase 1 —
  Foundation, Docker, and source-of-truth data` -> mandatory phase exit gate.

### Approved Architecture and Constraints

- SQLite is authoritative for every application record and state; Neo4j is an
  initialized, rebuildable derived index and owns no independent application ID.
- Alembic owns all nine application tables, named constraints, indexes, foreign
  keys, and singleton seeds. Runtime application code never calls
  `Base.metadata.create_all()` and Alembic never owns LangGraph checkpoint
  tables.
- One cached Pydantic Settings object reads runtime configuration from the
  user-owned root `.env`; `.env.example` is documentation-only, and nested
  frontend/backend environment files are prohibited.
- Shared UUID, UTC, settings, SQLAlchemy session, storage, and Neo4j driver logic
  must each have one owner and be reused by later phases.
- Uploaded bytes live under `FILES_DIR`; only UUID-derived relative paths are
  stored. SQLite and files share one application volume, while Neo4j data/logs
  use separate persistent volumes.
- The only public functional endpoint added in Plan 2 is
  `GET /api/health`. No production provider calls, CV/JD endpoints, chat/SSE,
  LangGraph execution, domain synchronization, rebuild command, or matching
  behavior belongs in these tasks.
- Docker Compose contains exactly `frontend`, `backend`, and `neo4j`.
  Services may listen on `0.0.0.0` inside containers, but every published host
  port is bound to `127.0.0.1`.
- No worker, queue, Redis, alternate database/vector store/design system,
  authentication, public deployment, CI, trigger, outbox, soft deletion, audit
  history, generic state table, or speculative abstraction may be introduced.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Pinned backend configuration and minimal Astryx frontend foundation | (01A), (01B) | Phase 0 PASS handoff |
| Batch02 | Complete SQLite/Alembic source-of-truth schema | (02A), (02B), (02C), (02D), (02E) | (01A) |
| Batch03 | Filesystem, Neo4j, and health-boundary primitives | (03A), (03B), (03C) | (01A), (02E) as noted per task |
| Batch04 | Reproducible three-service local runtime and Plan 3 handoff | (04A), (04B) | (01B), (02E), (03C) |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_2_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_2_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Pinned Application Foundations

### Goal

Turn the feasibility scaffolds into pinned, testable backend and frontend
foundations without implementing production workflows.

### Dependencies

- `docs/feasibility/phase_0_report.md` exists with
  `PHASE_0_OVERALL=PASS`.
- Existing backend pins and the Astryx 0.1.4 package/lockfile remain intact.

### Scope Boundary

This batch owns dependency manifests, local quality commands, settings and shared
ID/time helpers, and the minimal themed application shell. It does not own
database sessions/models/migrations, storage, Neo4j, Docker, health behavior, or
any production chat/CV/JD/Agent feature.

### Tasks

- [x] (01A): Configure the pinned backend, one-root settings, and shared core conventions
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.1 Settings and local environment`; `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.2 Shared database conventions`; `docs/plans/Plan_2.md > ## 9. Verification & Testing Plan > ### Automated commands`
  - Source Requirements:
    - Expand `backend/pyproject.toml` with only the exact-pinned Phase 1
      runtime and local quality dependencies used by Plan 2, preserving all
      proven Phase 0 pins.
    - Define one cached Pydantic v2 Settings model with every exact external
      name, type, and default from Section 7.1; runtime loading uses only the
      root `.env`, while process environment values remain testable overrides.
    - Keep secrets masked and single-source lowercase UUID v4 and timezone-aware
      UTC helpers for later models and repositories.
  - Dependencies: Phase 0 PASS handoff; no task dependency.
  - User Action: None. Tests must supply sanitized environment values and must
    not require or inspect the developer's real `.env`.
  - Agent Work:
    1. Search `backend/`, `infrastructure/scripts/`, manifests, and all
       callers for reusable configuration, UUID, UTC, and dependency patterns.
    2. Preserve the recorded pins; for a required settings/test-tooling package
       absent from the Phase 0 decision table, verify compatibility with the
       locked Python/Pydantic stack and then use one exact version with no
       alternative stack or unused dependency.
    3. Implement focused `settings.py`, `ids.py`, and `time.py` modules,
       plus the minimum Ruff, mypy, and pytest configuration needed by the
       plan's single-purpose commands.
    4. Add unit tests for all setting names/defaults/types, root-env resolution,
       environment override behavior, secret representation, UUID format, and
       UTC-aware timestamps; record exact command evidence.
  - Output: An installable pinned backend foundation with one validated settings
    object and reusable ID/time conventions.
  - Acceptance:
    - `backend/pyproject.toml` contains exact versions for every dependency
      used in this phase and does not add Phase 2 Agent/provider/extraction
      packages that Plan 2 does not execute.
    - The settings model exposes exactly the Section 7.1 external fields and
      defaults, locates only the root `.env`, never loads
      `.env.example`, and masks both secret fields in representations.
    - The shared helper returns lowercase UUID v4 text and the time helper
      returns timezone-aware UTC values; no competing helper exists.
    - Ruff, mypy, and the focused unit tests pass from the documented working
      directories.
  - Validation:
    - Required: `python -m pip install -e .\backend` -> the clean root
      bootstrap installs the pinned backend.
    - Required: `Set-Location backend; python -m ruff check .; python -m mypy app; python -m pytest tests/unit/test_settings.py tests/unit/test_core_conventions.py -q` -> all settings, secret, UUID, UTC, lint, and type evidence passes.
    - Required: `git ls-files | rg "(^|/)\.env$|frontend/\.env|backend/\.env"` -> no runtime environment file is tracked.
  - Blocked Condition: A required package cannot be exact-pinned compatibly with
    the Phase 0 Python/Pydantic pins; report the resolver evidence and stop
    instead of changing the locked stack.
  - Files: `backend/pyproject.toml`, `backend/app/core/settings.py`, `backend/app/core/ids.py`, `backend/app/core/time.py`, `backend/tests/unit/test_settings.py`, `backend/tests/unit/test_core_conventions.py`, root `.env.example` only if source-field drift is discovered

- [x] (01B): Replace the feasibility render with the pinned minimal Astryx application shell
  - Source of Truth: `docs/plans/Plan_2.md > ## 4. Scope`; `docs/plans/Plan_2.md > ## 6. Target Directory Structure`; `docs/plans/Plan_2.md > ## 8. Implementation Steps`; `docs/plans/Plan_2.md > ## 9. Verification & Testing Plan > ### Automated commands`
  - Source Requirements:
    - Keep React, TypeScript, Vite, Astryx core/CLI, and the neutral theme pinned
      to the Phase 0 lockfile while adding exact-pinned local lint/type/test
      tooling.
    - The frontend reads only `VITE_API_BASE_URL`; no nested frontend
      environment file or backend-only variable may enter the client bundle.
    - Replace the Phase 0 component-matrix proof with a minimal responsive
      `AppShell` foundation and neutral theme only; no chat, sidebar,
      approval, saved-job, or match behavior belongs here.
    - Use documented public Astryx APIs and token-based styling under the
      applicable `frontend/AGENTS.md` rules.
  - Dependencies: Phase 0 PASS handoff; no task dependency.
  - User Action: None.
  - Agent Work:
    1. Search the current frontend, lockfile, and Phase 0 report before adding
       packages or components; reuse the verified public CSS and
       `AppShell` imports.
    2. Run the pinned Astryx discovery/documentation commands for the minimal
       shell and theme; do not guess props or introduce undocumented internals.
    3. Move the application shell into the focused `src/app/` boundary, add
       only token-based theme adjustments required for the foundation, and add
       exact `lint`, `typecheck`, and `test` scripts with minimum
       compatible exact-pinned tooling.
    4. Add one focused render test proving the shell and neutral theme setup,
       then run the complete frontend command set.
  - Output: A minimal, pinned, tested Astryx-neutral frontend foundation ready
    for Plan 3 to extend.
  - Acceptance:
    - `package-lock.json` still resolves all three Astryx packages to 0.1.4,
      every added package is exact-pinned, and all five required scripts
      (`dev`, `lint`, `typecheck`, `test`, `build`) exist.
    - The runtime render uses the documented `AppShell` and neutral-theme
      public imports, contains no Phase 0 diagnostic UI, and implements no
      production chat/sidebar/card behavior.
    - Custom styles use Astryx tokens and the frontend contains no second design
      system, raw hard-coded visual scale, or undocumented component import.
    - Clean install, lint, type-check, tests, and production build all pass.
  - Validation:
    - Required: `Set-Location frontend; npm ci; npm run lint; npm run typecheck; npm test -- --run; npm run build` -> the lockfile and all local frontend gates pass.
    - Required: `Set-Location frontend; npx astryx component AppShell` -> the pinned CLI documents the public shell API used by the implementation.
    - Required: `rg -n "Phase0AstryxProof|Phase 0 diagnostic|@astryxdesign/.*/(src|dist)/" frontend/src` -> no feasibility component or internal Astryx import remains.
  - Blocked Condition: The required minimal shell cannot compile using the
    already-proven Astryx 0.1.4 public API, or required lint/test tooling cannot
    be exact-pinned without changing the locked frontend stack.
  - Files: `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/main.tsx`, `frontend/src/app/App.tsx`, `frontend/src/app/theme.css`, `frontend/src/test/setup.ts`, `frontend/src/app/App.test.tsx`, `frontend/vite.config.ts`, frontend lint configuration if required by the selected minimum tool

## Mandatory Batch02 - Complete SQLite Source of Truth

### Goal

Implement the shared async SQLite boundary, all nine exact SQLAlchemy table
contracts, and an idempotent Alembic head with singleton seeds.

### Dependencies

- (01A) supplies the pinned backend, settings, UUID helper, UTC helper, and local
  quality commands.

### Scope Boundary

This batch owns database metadata, connections, static database invariants,
migrations, and singleton seeds. It does not own write repositories, state
transition services, provider calls, file writes, graph synchronization,
LangGraph checkpoints, or public CRUD endpoints.

### Tasks

- [x] (02A): Implement the async SQLite session boundary and required connection PRAGMAs
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.2 Shared database conventions`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.1 Global conventions`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.4 Transaction boundaries`
  - Source Requirements:
    - Own one SQLAlchemy 2 async engine/session factory for
      `sqlite+aiosqlite` at `SQLITE_PATH`.
    - Apply and verify `foreign_keys=ON`, `journal_mode=WAL`, and
      `busy_timeout=5000` on every application connection.
    - Provide one declarative base/naming convention and transaction primitives;
      never call `create_all()` or hide external work inside a transaction.
  - Dependencies: (01A).
  - User Action: None.
  - Agent Work:
    1. Search all backend and diagnostic code for existing SQLite, session, or
       naming logic and inspect future callers named by Plan 2.
    2. Implement the focused declarative-base and async session modules using
       the shared settings object; keep connection-event logic single-sourced.
    3. Add temporary-file integration tests that open multiple application
       connections and verify all three PRAGMAs and foreign-key enforcement.
    4. Run focused tests plus lint/type checks and inspect every session-factory
       caller before finalizing the public boundary.
  - Output: One reusable async SQLite engine/session boundary with enforced
    connection invariants.
  - Acceptance:
    - Every application connection reports foreign keys enabled, WAL mode, and a
      5000 ms busy timeout against a temporary SQLite file.
    - The engine uses the configured `SQLITE_PATH` and async
      `sqlite+aiosqlite` URL; tests do not touch the developer database.
    - There is one declarative base and one session factory, with no runtime
      `create_all()` call or duplicated PRAGMA setup.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_database_pragmas.py -q` -> all connection and foreign-key checks pass on a temporary file.
    - Required: `Set-Location backend; python -m ruff check app/db tests/integration/test_database_pragmas.py; python -m mypy app` -> the database boundary passes lint and type checks.
  - Blocked Condition: SQLAlchemy/aiosqlite cannot apply the three required
    PRAGMAs on every connection with the pinned versions; report the minimal
    reproduction without switching database technology.
  - Files: `backend/app/db/base.py`, `backend/app/db/session.py`, `backend/tests/integration/test_database_pragmas.py`

- [x] (02B): Define the attachment and profile-family SQLAlchemy contracts
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.3 Application table ownership`; `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.4 Foreign keys, seeds, and migration ownership`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.2 Application table schemas > #### attachments`, `#### candidate_profile`, `#### profile_drafts`, and `#### job_preferences`
  - Source Requirements:
    - Define exactly `attachments`, `candidate_profile`,
      `profile_drafts`, and `job_preferences` with their specified columns,
      defaults, singleton checks, JSON fields, named constraints, uniqueness,
      partial active index, and attachment foreign-key delete actions.
    - Reuse the shared base, UUID, and UTC conventions; add no history/status
      tables, service transitions, configuration-dependent checks, or cross-row
      behavior.
  - Dependencies: (02A).
  - User Action: None.
  - Agent Work:
    1. Search the model package, metadata, migration placeholders, and all named
       future callers before defining a new base, mixin, enum, or helper.
    2. Implement focused attachment and profile model modules; refactor a truly
       shared timestamp/constraint pattern only when it removes duplication
       without hiding the source contract.
    3. Add metadata-level unit tests for exact columns, nullability, defaults,
       names, singleton checks, partial index predicate, foreign keys, and delete
       actions; leave runtime migration behavior to (02E).
    4. Run focused tests and inspect the modules for single responsibility and
       accidental future-phase behavior.
  - Output: Exact SQLAlchemy metadata for the attachment/profile portion of the
    nine-table application schema.
  - Acceptance:
    - The four model tables contain exactly the approved columns and static
      invariants, including unique hash/path, the one-active partial index,
      fixed singleton IDs, and exact RESTRICT/CASCADE relationships.
    - JSON shape, allowed transitions, attachment/profile cross-row state, PDF
      limits, approval writes, and file operations are not implemented as
      database checks or model side effects.
    - No duplicate ID/timestamp/base helper or additional application table is
      introduced.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_attachment_profile_models.py -q` -> metadata assertions cover every approved field, constraint, index, and FK.
    - Required: `Set-Location backend; python -m ruff check app/db/models/attachments.py app/db/models/profiles.py tests/unit/test_attachment_profile_models.py; python -m mypy app` -> focused model code passes quality gates.
  - Blocked Condition: The SQLAlchemy metadata cannot express an exact named
    invariant or SQLite partial-index predicate with the pinned stack; report
    the unsupported invariant rather than weakening it.
  - Files: `backend/app/db/models/__init__.py`, `backend/app/db/models/attachments.py`, `backend/app/db/models/profiles.py`, `backend/tests/unit/test_attachment_profile_models.py`

- [x] (02C): Define the exact job-post SQLAlchemy contract
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.3 Application table ownership`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.2 Application table schemas > #### job_posts`
  - Source Requirements:
    - Define only `job_posts` with the exact columns, status/quality values,
      URL/text and hash coupling, processed/failure coupling, all-or-none
      embedding fields, processed/scorable embedding rules, exact-hash
      uniqueness, and processing-quality index.
    - Keep configuration-dependent dimension/finiteness checks, transitions,
      deduplication services, extraction, embeddings, graph sync, and scoring
      outside the model task.
  - Dependencies: (02A).
  - User Action: None.
  - Agent Work:
    1. Search current and planned job-model callers and reuse the shared
       base/ID/time conventions.
    2. Implement the focused job model with named static checks and indexes,
       using SQLAlchemy JSON/Boolean/text conventions exactly as applicable.
    3. Add metadata-level unit tests for every column, enum value, coupling
       rule, unique/index name, and absence of extra fields.
    4. Run focused quality gates and inspect the final module for future-phase
       behavior or a duplicated hash/embedding helper.
  - Output: Exact SQLAlchemy metadata for `job_posts`.
  - Acceptance:
    - `job_posts` has exactly the approved schema and static constraints, and
      uses only the immutable source status/quality values.
    - The database permits embeddings only for processed full/partial rows and
      requires all three embedding fields together, without hard-coding the
      configurable length into a migration check.
    - No score cache, transition service, extraction, provider, graph, or
      duplicate business policy is added.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_job_post_model.py -q` -> every job metadata invariant passes.
    - Required: `Set-Location backend; python -m ruff check app/db/models/jobs.py tests/unit/test_job_post_model.py; python -m mypy app` -> focused model code passes quality gates.
  - Blocked Condition: An approved null-coupling or embedding-state invariant
    cannot be represented as a named SQLite check through the pinned SQLAlchemy
    stack; report the exact mismatch and do not shift a required static check to
    future service code.
  - Files: `backend/app/db/models/jobs.py`, `backend/tests/unit/test_job_post_model.py`

- [x] (02D): Define the conversation, message, run, and tool-execution SQLAlchemy contracts
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.3 Application table ownership`; `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.4 Foreign keys, seeds, and migration ownership`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.2 Application table schemas > #### conversation`, `#### chat_messages`, `#### agent_runs`, and `#### tool_executions`
  - Source Requirements:
    - Define the four exact chat-family tables with the singleton conversation,
      content/payload coupling, deterministic history index, run-state coupling,
      unique user-message run, exact tool statuses, run/tool-call uniqueness,
      terminal-result/duration/error coupling, and exact cascades.
    - Model storage contracts only; no chat endpoint, SSE, LangGraph state,
      tool execution service, approval flow, or checkpoint table belongs here.
  - Dependencies: (02A).
  - User Action: None.
  - Agent Work:
    1. Search the model tree and all named future chat/Agent callers before
       introducing any shared state value or helper.
    2. Implement the focused chat model module using the existing base/ID/time
       owners and exact immutable values from the source.
    3. Add metadata-level tests for columns, constraints, indexes, uniqueness,
       foreign keys, cascades, and the absence of a persisted tool-role message.
    4. Run focused tests and inspect for accidental Agent/SSE/checkpoint logic.
  - Output: Exact SQLAlchemy metadata for the four chat persistence tables.
  - Acceptance:
    - The four tables contain exactly the approved fields, constraint/index
      names, coupling checks, and CASCADE relationships.
    - Tool status values are exactly
      `pending | running | completed | failed`; run and message values match
      the immutable Plan 2 lists without aliases.
    - No checkpoint table, durable provider ToolMessage, public API, Agent
      orchestration, or second idempotency mechanism is introduced.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_chat_models.py -q` -> every chat-family metadata invariant passes.
    - Required: `Set-Location backend; python -m ruff check app/db/models/chat.py tests/unit/test_chat_models.py; python -m mypy app` -> focused model code passes quality gates.
  - Blocked Condition: An exact source coupling, unique rule, or cascade cannot
    be represented by the pinned SQLAlchemy/SQLite stack; report the specific
    contract failure instead of adding service or checkpoint behavior.
  - Files: `backend/app/db/models/chat.py`, `backend/tests/unit/test_chat_models.py`

- [x] (02E): Create the idempotent initial Alembic schema and singleton seeds
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.4 Foreign keys, seeds, and migration ownership`; `docs/plans/Plan_2.md > ## 9. Verification & Testing Plan > ### Automated commands`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.3 Foreign-key and deletion rules`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.5 Migration and checkpoint ownership`
  - Source Requirements:
    - Configure Alembic batch mode and create one initial revision that builds
      all nine application tables in dependency order with every approved named
      constraint/index/FK.
    - Seed `conversation('main')` and `job_preferences('active')`
      idempotently in one transaction, with exactly four empty preference lists;
      never seed `candidate_profile`.
    - Provide the normal-startup singleton safeguard after migrations are
      applied, while never calling `create_all()` or creating/altering/dropping
      LangGraph checkpoint tables.
  - Dependencies: (02B), (02C), (02D).
  - User Action: None. Migration tests must use isolated temporary SQLite files
    and sanitized settings.
  - Agent Work:
    1. Search existing Alembic/configuration files, all model metadata, and every
       seed caller; compare the final metadata against Master Section 6 before
       writing the revision.
    2. Configure Alembic for the shared async SQLite URL and batch rendering,
       then implement `0001_initial_schema.py` explicitly with exact names,
       partial index, dependency order, delete actions, and singleton inserts.
    3. Implement one reusable idempotent singleton-seed safeguard for later
       startup use; do not make application startup run migrations.
    4. Add integration tests that run upgrade on fresh and initialized temporary
       files, prove every table/constraint/index/FK/cascade/seed and PRAGMA,
       reject invalid rows, preserve unrelated fake checkpoint tables, and
       confirm candidate-profile absence.
    5. Run the complete database/migration suite twice and inspect all runtime
       callers for prohibited `create_all()`.
  - Output: Alembic head `0001_initial_schema` and an idempotent singleton
    safeguard that establish the complete SQLite source of truth.
  - Acceptance:
    - A fresh upgrade creates exactly the nine application tables and required
      singleton rows; upgrading an initialized database at head is a no-op and
      never duplicates seeds.
    - Database inspection and invalid-write tests prove all approved named
      constraints, indexes, partial uniqueness, cascades/RESTRICT behavior, and
      required PRAGMAs.
    - `candidate_profile` has no seed row, checkpoint-like unrelated tables
      survive, and no runtime or migration path calls
      `Base.metadata.create_all()`.
    - The empty preferences JSON contains exactly
      `target_roles`, `preferred_locations`,
      `acceptable_work_modes`, and `target_seniority`, each an empty list.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_database_contract.py tests/integration/test_migrations.py -q` -> the fresh/head migration, full schema contract, seeds, cascades, and checkpoint-preservation evidence passes.
    - Required: `Set-Location backend; python -m ruff check app/db migrations tests/integration/test_database_contract.py tests/integration/test_migrations.py; python -m mypy app` -> migration-owned runtime code and tests pass quality gates.
    - Required: `rg -n "create_all\(" backend/app backend/migrations` -> no runtime or migration invocation exists.
  - Blocked Condition: Migration output differs from the exact approved model
    contract, a required SQLite invariant is not enforceable, or an upgrade
    would alter an existing non-application/checkpoint table; stop rather than
    compensating in repositories.
  - Files: `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_initial_schema.py`, `backend/app/db/seed.py`, `backend/tests/integration/test_database_contract.py`, `backend/tests/integration/test_migrations.py`

## Mandatory Batch03 - Storage, Graph, and Health Primitives

### Goal

Add the filesystem-only attachment boundary, the idempotent Neo4j base contract,
and the single public health endpoint on top of the authoritative SQLite schema.

### Dependencies

- (01A) supplies settings and shared core helpers.
- (02E) supplies the migrated database and singleton-seed safeguard required by
  application startup and health checks.

### Scope Boundary

This batch owns low-level file operations, Neo4j lifecycle/schema setup, FastAPI
lifespan wiring, and component health reporting. It does not parse PDFs, mutate
attachment/job/profile state, synchronize domain nodes, rebuild the graph,
expose CRUD/chat endpoints, call ShopAIKey, or run Agent behavior.

### Tasks

- [ ] (03A): Implement the UUID-rooted atomic attachment storage boundary
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.5 Attachment storage`; `docs/plans/Plan_2.md > ## 9. Verification & Testing Plan > ### Automated commands`
  - Source Requirements:
    - Root every file under configured `FILES_DIR`, generate database-facing
      relative paths from the shared application UUID rather than the display
      filename, and reject path traversal.
    - Atomically create files through a temporary sibling and final replacement,
      with existence/open/delete primitives for later services.
    - Keep deletion best-effort only when explicitly called and keep parsing,
      hashing, draft creation, and database state outside this module.
  - Dependencies: (01A).
  - User Action: None. Tests use a temporary directory and sanitized settings.
  - Agent Work:
    1. Search the repository and all planned storage callers for existing path,
       UUID, atomic-write, open, or delete logic; reuse the shared UUID owner.
    2. Implement the smallest focused filesystem abstraction using standard
       library path and atomic-replace primitives before considering any new
       dependency.
    3. Add unit tests for UUID-relative naming, complete atomic writes,
       interrupted-write cleanup, traversal/absolute-path rejection,
       existence/open behavior, and explicit best-effort deletion.
    4. Run focused quality gates and inspect all path-accepting methods to prove
       display filenames and untrusted relative paths cannot escape the root.
  - Output: A reusable filesystem-only attachment store rooted at
    `FILES_DIR`.
  - Acceptance:
    - Stored paths are relative, UUID-derived, and always resolve beneath the
      configured root; original/display filenames never control a path.
    - Successful writes become visible only after complete atomic replacement,
      and failed writes leave no final partial file.
    - Existence/open/delete work only within the root, deletion occurs only when
      called, and the module imports no PDF parser, ORM model, or business
      service.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_storage.py -q` -> all atomicity, path-safety, and file-operation cases pass.
    - Required: `Set-Location backend; python -m ruff check app/storage/attachments.py tests/unit/test_storage.py; python -m mypy app` -> the storage boundary passes quality gates.
  - Blocked Condition: The target filesystem cannot provide atomic sibling
    replacement semantics required by the supported local runtime; report the
    platform evidence instead of weakening atomicity.
  - Files: `backend/app/storage/__init__.py`, `backend/app/storage/attachments.py`, `backend/tests/unit/test_storage.py`

- [ ] (03B): Implement the Neo4j driver lifecycle and idempotent base schema
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.6 Neo4j base contract`; `docs/plans/Master_plan.md > ## 8. Neo4j Derived Model > ### 8.3 Constraints and indexes`; `docs/plans/Master_plan.md > ## 8. Neo4j Derived Model > ### 8.4 Graph safety rules`
  - Source Requirements:
    - Own the official async driver lifecycle and connectivity check, using the
      shared settings and parameterized Cypher for runtime data.
    - Idempotently create unique constraints for `Candidate.id`, `Job.id`,
      and `Skill.canonical_key`, plus one cosine vector index on
      `Job.embedding` at exactly 1536 dimensions.
    - Fix identities to Candidate `active`, SQLite Job UUID, and normalized
      Skill canonical key; add no CV/JD synchronization or independent graph ID.
  - Dependencies: (01A).
  - User Action: None for required unit validation; live Neo4j evidence belongs
    to (04B).
  - Agent Work:
    1. Search the repository, settings, dependency manifest, and all named graph
       callers before adding driver/setup helpers; keep lifecycle and schema
       statements in their focused owners.
    2. Implement async open/close/connectivity behavior and fixed,
       `IF NOT EXISTS` schema statements. Never interpolate runtime values or
       secrets into Cypher/logs; fixed DDL identifiers/options may remain
       source constants.
    3. Add deterministic fake-driver unit tests that verify lifecycle,
       connectivity outcomes, exact constraint/index statements, repeat-safe
       setup, cosine similarity, and 1536 dimensions.
    4. Inspect every driver/setup caller and run focused quality gates; defer
       domain nodes, relationships, rebuild, and sync to later plans.
  - Output: One Neo4j driver owner and one repeat-safe JobAgent graph-schema
    initializer.
  - Acceptance:
    - Driver lifecycle and connectivity use the configured URI/user/secret
      without exposing the password.
    - Repeated setup issues only idempotent creation for the three exact unique
      constraints and one exact cosine/1536 vector index.
    - No graph domain write, seed relationship, sync/retry/rebuild behavior,
      second identifier, or SQLite mutation exists.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_graph_setup.py -q` -> lifecycle, failure, exact DDL, and repeated-setup cases pass with the fake driver.
    - Required: `Set-Location backend; python -m ruff check app/graph tests/unit/test_graph_setup.py; python -m mypy app` -> graph primitives pass quality gates.
    - Required: `rg -n "HAS_SKILL|REQUIRES|PREFERS|RELATED_TO|source_updated_at|rebuild" backend/app/graph` -> no later-phase synchronization or rebuild behavior is present.
  - Blocked Condition: The pinned Neo4j driver or approved Community version
    cannot express an idempotent 1536-dimensional cosine vector index; report
    exact compatibility evidence instead of changing model/dimensions or adding
    another vector store.
  - Files: `backend/app/graph/__init__.py`, `backend/app/graph/driver.py`, `backend/app/graph/constraints.py`, `backend/tests/unit/test_graph_setup.py`

- [ ] (03C): Expose the validated three-component health boundary and application lifecycle
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.7 Health endpoint`; `docs/plans/Plan_2.md > ## 4. Scope`; `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary > ### 14.1 API rules`
  - Source Requirements:
    - Expose only `GET /api/health` with a validated overall status and exact
      `available | unavailable` states for SQLite, filesystem, and Neo4j.
    - SQLite uses a trivial configured-session query, filesystem verifies the
      directory can be created/accessed without writing user data, and Neo4j
      calls the driver's connectivity check.
    - Wire startup/shutdown to the existing singleton safeguard and separately
      invoked idempotent graph initialization after migrations are applied;
      health itself must not mutate schema.
  - Dependencies: (02E), (03A), (03B).
  - User Action: None. Required endpoint tests use dependency overrides/fakes
    and temporary SQLite/filesystem resources.
  - Agent Work:
    1. Search for FastAPI, settings, seed, session, storage, and graph lifecycle
       owners and inspect every planned application entry-point caller.
    2. Implement the minimal application lifespan and focused health
       schema/check functions, reusing existing owners and configured
       `FRONTEND_ORIGIN`; do not run Alembic or `create_all()` at startup.
    3. Reuse `available | unavailable` for the overall field: it is
       `available` only when all three components are available, avoiding an
       unapproved third status vocabulary.
    4. Add integration tests for all-available and each individual unavailable
       dependency, validated payload shape, non-mutating filesystem check,
       startup idempotence, shutdown cleanup, and absence of any other public
       functional route.
    5. Run focused quality gates and inspect logs/payloads for secrets, paths, or
       connection details.
  - Output: A FastAPI application with idempotent resource lifecycle and the
    single public `GET /api/health` boundary.
  - Acceptance:
    - The health payload validates and reports only the exact three components;
      overall is available exactly when all are available, and one unavailable
      dependency is represented without crashing or changing SQLite ownership.
    - Health performs no schema mutation and writes no user-data probe file;
      startup never runs migrations or `create_all()`.
    - Lifespan opens/closes shared resources once, runs singleton and graph
      safeguards idempotently after migration availability, and leaks no secret
      or connection detail.
    - No CV/profile/chat/job endpoint, SSE route, provider client, or Agent
      behavior is exposed.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_health.py -q` -> lifecycle, all component states, non-mutation, payload, and route-scope cases pass.
    - Required: `Set-Location backend; python -m ruff check app/api app/schemas/health.py app/main.py tests/integration/test_health.py; python -m mypy app` -> API/lifecycle code passes quality gates.
    - Required: `rg -n "@(app|router)\.(get|post|put|patch|delete)" backend/app` -> the only public functional route is `GET /api/health`.
  - Blocked Condition: The health contract cannot report a dependency failure
    without startup termination or schema mutation; report the failing
    lifecycle/component boundary rather than suppressing the error.
  - Files: `backend/app/api/__init__.py`, `backend/app/api/health.py`, `backend/app/schemas/health.py`, `backend/app/main.py`, `backend/tests/integration/test_health.py`

## Mandatory Batch04 - Reproducible Local Runtime and Handoff

### Goal

Containerize the completed foundations, prove fresh and initialized local
operation with persistent data and loopback-only ports, and document the exact
Plan 3 handoff.

### Dependencies

- (01B) supplies the buildable frontend.
- (02E) supplies Alembic head and SQLite singleton initialization.
- (03C) supplies backend lifecycle and health reporting.

### Scope Boundary

This batch owns Dockerfiles, Compose topology, runtime wiring, Compose-backed
Phase 1 integration evidence, and root README command/status updates. It may
repair only container/integration wiring it owns. A failure in an earlier
accepted domain contract must return to that owning task; this batch must not
silently broaden its diff into CV/JD/chat/Agent behavior.

### Tasks

- [ ] (04A): Build the exact three-service Docker Compose topology
  - Source of Truth: `docs/plans/Plan_2.md > ## 7. Technical Specifications > ### 7.8 Docker Compose contract`; `docs/plans/Plan_2.md > ## 9. Verification & Testing Plan > ### Automated commands`; `docs/plans/Master_plan.md > ## 22. Local Demo Safeguards`; `docs/plans/Master_plan.md > ## 23. Environment Configuration`
  - Source Requirements:
    - Build backend/frontend Dockerfiles and one Compose file containing exactly
      `frontend`, `backend`, and Neo4j Community.
    - Load the single root `.env`, pass explicit service variables, keep
      `.env.example` documentation-only, and never add/mount nested env files.
    - Persist SQLite/files together in one application data volume and Neo4j
      data/logs in their own volumes; bind every host port to `127.0.0.1`.
    - Backend waits for Neo4j health, all services listen on `0.0.0.0`
      internally, and component health does not transfer authority from SQLite.
    - The backend container applies `alembic upgrade head` before starting the
      ASGI application; it never substitutes runtime `create_all()`.
  - Dependencies: (01B), (02E), (03C).
  - User Action: Before live Compose validation, create or update the ignored
    root `.env` from `.env.example`, provide a valid local
    `NEO4J_PASSWORD`, and ensure the configured loopback ports are free. Do
    not provide any secret value to an agent or commit the file.
  - Agent Work:
    1. Search existing infrastructure placeholders, manifests, settings,
       application entry points, and frontend build/runtime configuration before
       defining commands, images, variables, ports, health checks, or volumes.
    2. Implement focused backend/frontend Dockerfiles with pinned base images
       and non-interactive reproducible installs; pin a Neo4j Community image
       compatible with the approved driver/vector contract rather than using a
       floating tag.
    3. Implement the exact Compose topology, explicit root-env interpolation,
       volumes, loopback publication, health checks, and health-based backend
       dependency. Do not mount the root env file or source tree into runtime
       containers.
    4. Validate the fully resolved Compose model and built images, then inspect
       the rendered configuration for extra services, non-loopback ports,
       secret expansion in tracked artifacts, and incorrect volume ownership.
  - Output: Reproducible images and a three-service local Compose topology with
    persistent application/Neo4j data and safe host bindings.
  - Acceptance:
    - Resolved Compose contains exactly the three approved services, uses no
      floating image/dependency tag, and passes only the documented environment
      names to the owning service.
    - Every published application and Neo4j port explicitly binds
      `127.0.0.1`; backend/frontend listen on `0.0.0.0` only inside their
      containers.
    - SQLite and `FILES_DIR` resolve inside one application volume; Neo4j
      data/logs persist separately; no runtime data or env file is mounted into
      Git-tracked paths.
    - Backend dependency and all container health checks use the approved health
      boundaries without adding a fourth service.
  - Validation:
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml config --services` -> the service-name set is exactly `frontend`, `backend`, and `neo4j`.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml config` -> configuration resolves with explicit variables, volumes, health checks, and loopback bindings.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml build` -> both application images build reproducibly.
    - Required: `git ls-files | rg "(^|/)\.env$|frontend/\.env|backend/\.env|(^|/)(data|runtime|uploads)/"` -> no runtime env or data path is tracked.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when the ignored root
    `.env`, valid local Neo4j password, free ports, Docker engine, or required
    base images are unavailable; never print secrets or substitute an extra
    service/provider.
  - Files: `infrastructure/docker/backend.Dockerfile`, `infrastructure/docker/frontend.Dockerfile`, `infrastructure/docker-compose.yml`, `frontend/vite.config.ts` only if required for container host binding, root `.env.example` only if an approved variable is missing

- [ ] (04B): Prove the Phase 1 exit gate and publish the Plan 3 local handoff
  - Source of Truth: `docs/plans/Plan_2.md > ## 9. Verification & Testing Plan`; `docs/plans/Plan_2.md > ## 10. Handoff Notes for Plan 3 / Master Phase 2`; `docs/plans/Master_plan.md > ## 24. Local Testing Strategy > ### 24.5 Local verification commands`; `docs/plans/Master_plan.md > ## 25. Implementation Phases > ### Phase 1 — Foundation, Docker, and source-of-truth data`
  - Source Requirements:
    - Prove frontend, backend, and Neo4j become healthy on empty isolated volumes
      and again on initialized volumes; prove migrations/seeds and graph schema
      setup are idempotent.
    - Verify SQLite/filesystem/Neo4j all report available, data survives
      container recreation, host ports remain loopback-only, and secrets/runtime
      data never enter Git or health/log output.
    - Update root `README.md` with the current Phase 1 status, architecture,
      single-root environment contract, and single-purpose local commands only
      after the corresponding evidence passes.
  - Dependencies: (04A).
  - User Action: Keep the ignored root `.env` and Docker engine available as
    required by (04A), and confirm the test project's configured loopback ports
    are free. Real ShopAIKey calls are neither required nor permitted.
  - Agent Work:
    1. Search all existing unit/integration tests and README commands before
       adding evidence; reuse prior checks and add only the missing
       Compose-backed Neo4j/health coverage.
    2. Add focused live-local integration cases that run graph setup twice and
       inspect the three uniqueness constraints plus cosine/1536 index, and
       exercise the health endpoint against the three running services.
    3. Use a uniquely named Compose test project/volumes, run the full backend,
       frontend, migration, Compose, and health gates, recreate containers
       without deleting volumes, and confirm singleton counts and persisted
       application data remain correct.
    4. Inspect resolved port bindings, Git status, health payloads, and sanitized
       logs. Do not rerun the live ShopAIKey diagnostic or modify Phase 0
       feasibility artifacts.
    5. Update only the root README documentation/status and focused
       integration-test harness owned by this task. If a failure requires a
       prior domain-contract repair, stop and return the exact evidence to the
       orchestrator instead of editing that task's owned behavior.
  - Output: Reproducible Phase 1 exit evidence, current root README commands, and
    an explicit reusable foundation handoff for Plan 3.
  - Acceptance:
    - All backend unit/integration, lint, type, migration, frontend, and build
      commands pass with the pinned manifests.
    - On isolated empty volumes the three services become healthy; after
      container recreation on the same volumes they become healthy again,
      Alembic remains at head, singleton rows remain singular, and persistent
      data remains.
    - Live-local inspection proves exactly three Neo4j uniqueness constraints
      and one cosine vector index at 1536 dimensions after repeated setup.
    - `GET /api/health` reports all three components and overall as available;
      resolved host bindings are loopback-only and no secret/runtime data is
      tracked or emitted.
    - Root `README.md` accurately records Phase 1 completion, folder/ownership
      boundaries, the one-root-env rule, and exact single-purpose commands for
      backend, frontend, migrations, Neo4j/health, retained feasibility checks,
      and full Compose startup.
    - The handoff exposes settings/session/ID/time/storage/driver primitives and
      exact schema/status contracts without adding any Plan 3 behavior.
  - Validation:
    - Required: `Set-Location backend; python -m ruff check .; python -m mypy app; python -m pytest tests/unit -q; python -m pytest tests/integration -q` -> every backend Phase 1 gate passes without a real provider call.
    - Required: `Set-Location frontend; npm ci; npm run lint; npm run typecheck; npm test -- --run; npm run build` -> every frontend foundation gate passes.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test up --build -d` -> the isolated three-service runtime starts on fresh volumes.
    - Required: `Invoke-RestMethod http://127.0.0.1:8000/api/health` -> overall, SQLite, filesystem, and Neo4j report `available`.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test exec backend alembic current; docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test exec backend alembic upgrade head` -> initialized runtime remains at head without duplicate seeds.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test up -d --force-recreate; Invoke-RestMethod http://127.0.0.1:8000/api/health` -> the same persistent volumes recover healthy after container recreation.
    - Required: `git status --short; git ls-files | rg "(^|/)\.env$|frontend/\.env|backend/\.env|(^|/)(data|runtime|uploads)/"` -> only scoped source/docs/test changes exist and no secret/runtime artifact is tracked.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when Docker, the ignored root
    environment, local Neo4j credential, or ports are unavailable. Otherwise,
    any failed migration/schema/graph/health invariant returns to its earlier
    owning task with exact evidence and blocks Plan 3; do not compensate in the
    README or integration harness.
  - Files: `backend/tests/integration/test_neo4j_setup.py`, `backend/tests/integration/test_compose_runtime.py`, root `README.md`
