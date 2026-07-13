# Plan 2 — Master Phase 1: Foundation, Docker, and Source-of-Truth Data

> **Numbering:** `Plan_2.md` implements **Master Plan Phase 1**. It starts only after every Plan 1 / Master Phase 0 feasibility gate passes.

## 1. Objective

Establish the runnable local application foundation: pinned backend/frontend projects, one-root-environment configuration, Docker Compose, SQLite/Alembic as the complete source of truth, persistent file storage, and Neo4j as an initialized rebuildable index. This phase owns all application table definitions and infrastructure invariants, but no production Agent, CV, JD, approval, or matching behavior.

At completion, the three services start locally, migrations work on fresh and initialized volumes, the health boundary reports SQLite/filesystem/Neo4j state, and database/graph constraints are proved idempotent.

## 2. Source of Truth

- `docs/plans/Master_plan.md` Sections 2–5: scope, locked stack, ownership rules, and repository structure.
- Section 6 in full: SQLite conventions, all nine application tables, constraints, indexes, foreign keys, transaction boundaries, singleton seeds, migration/checkpoint ownership, and Neo4j identity mapping.
- Sections 8.1–8.4: Neo4j nodes, relationships, uniqueness constraints, vector index, and graph safety rules.
- Sections 14 and 14.1: `GET /api/health` is the only public functional endpoint owned in this phase.
- Sections 15.1 and 15.3: Astryx shell/theme foundation and pinned public APIs.
- Sections 21.1 and 21.2: SQLite-first ownership and idempotent Neo4j setup; domain sync remains later.
- Sections 22–23: local bind safeguards and the exact one-root-`.env` contract.
- Sections 24.1–24.2 and 24.5: database/infrastructure tests and local commands.
- Section 25, “Phase 1 — Foundation, Docker, and source-of-truth data”: tasks and exit gate.

## 3. Prerequisites from Prior Phases

- [ ] `docs/feasibility/phase_0_report.md` exists and every ShopAIKey, Astryx, pypdf, and embedding gate is PASS.
- [ ] `frontend/package-lock.json` pins the verified Astryx version and the minimal frontend builds.
- [ ] `backend/pyproject.toml` and the feasibility report identify compatible pinned dependency versions, including FastAPI `>=0.135.0`.
- [ ] `.env.example` uses the Master Section 23 names and the developer’s root `.env` remains ignored.
- [ ] The ShopAIKey diagnostic and PDF fixtures continue to pass; this phase does not replace them.

## 4. Scope

- Configure FastAPI, Pydantic v2 settings, SQLAlchemy 2 async sessions, aiosqlite, Alembic batch mode, and local lint/type/test commands.
- Configure React, TypeScript, Vite, and the pinned Astryx neutral theme without building chat features.
- Build backend/frontend Dockerfiles and local Docker Compose for frontend, backend, and Neo4j Community.
- Load every runtime value from the single root `.env`; keep `.env.example` documentation-only.
- Persist SQLite/files under one application volume and Neo4j data under its own volume.
- Implement all application SQLAlchemy models, named constraints, indexes, foreign keys, and allowed static invariants from Master Section 6.
- Create Alembic migrations for all application-owned tables and singleton seeds; never call `create_all()` at runtime.
- Enable `foreign_keys=ON`, WAL, and `busy_timeout=5000` on every application connection.
- Implement UUID/UTC helpers used by models and repositories without duplicating them later.
- Implement an attachment storage abstraction rooted at `FILES_DIR` with UUID-relative paths and atomic file creation support.
- Implement Neo4j driver lifecycle, health check, uniqueness constraints, and a cosine vector index with 1536 dimensions.
- Implement `GET /api/health` for SQLite, filesystem, and Neo4j component status.
- Add focused unit/integration tests for settings, migrations, constraints, PRAGMAs, storage, graph setup, and container health.

## 5. Out of Scope

- Chat history, SSE, LangGraph, Agent runs, tool execution services, or ShopAIKey production calls.
- Public CV upload/profile endpoints beyond the health endpoint.
- File parsing, extraction, hash reuse policy, draft/approval services, or Candidate synchronization.
- URL/JD ingestion, embeddings, Job synchronization, rebuild behavior, or matching.
- Frontend chat shell, sidebar behavior, approval cards, saved-job cards, or match cards.
- Application `create_all()`, database triggers, soft deletion, audit history, generic key-value state, score caches, outbox tables, workers, queues, or sync-state machines.
- Authentication, public deployment, CI, and production security systems.

## 6. Target Directory Structure

```text
JobAgent/
├── .env                         # ignored developer runtime values
├── .env.example                 # exact variable names, safe placeholders
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── App.tsx
│   │   │   └── theme.css
│   │   ├── test/
│   │   │   └── setup.ts
│   │   └── main.tsx
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── health.py
│   │   ├── core/
│   │   │   ├── ids.py
│   │   │   ├── settings.py
│   │   │   └── time.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── seed.py
│   │   │   └── models/
│   │   │       ├── attachments.py
│   │   │       ├── chat.py
│   │   │       ├── jobs.py
│   │   │       └── profiles.py
│   │   ├── graph/
│   │   │   ├── constraints.py
│   │   │   └── driver.py
│   │   ├── storage/
│   │   │   └── attachments.py
│   │   └── main.py
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── tests/
│   │   ├── integration/
│   │   │   ├── test_database_contract.py
│   │   │   ├── test_health.py
│   │   │   ├── test_migrations.py
│   │   │   └── test_neo4j_setup.py
│   │   └── unit/
│   │       ├── test_settings.py
│   │       └── test_storage.py
│   ├── alembic.ini
│   └── pyproject.toml
└── infrastructure/
    ├── docker-compose.yml
    └── docker/
        ├── backend.Dockerfile
        └── frontend.Dockerfile
```

Each source module has one responsibility. Keep domain model modules focused and ordinarily below 300 lines; do not consolidate all tables, services, or graph behavior into a single file.

## 7. Technical Specifications

### 7.1 Settings and local environment

`backend/app/core/settings.py` defines one cached Pydantic Settings model with these exact external names and types:

```text
APP_ENV: str = "local"
FRONTEND_ORIGIN: str
SQLITE_PATH: str
FILES_DIR: str
NEO4J_URI: str
NEO4J_USER: str
NEO4J_PASSWORD: SecretStr
SHOPAIKEY_BASE_URL: AnyHttpUrl
SHOPAIKEY_API_KEY: SecretStr
LLM_MODEL: str = "gpt-4o-mini"
LLM_TEMPERATURE: float = 0
EMBEDDING_MODEL: str = "text-embedding-3-small"
EMBEDDING_DIMENSIONS: int = 1536
MAX_PDF_SIZE_MB: int = 10
MAX_PDF_PAGES: int = 10
URL_FETCH_TIMEOUT_SECONDS: int = 10
URL_MAX_RESPONSE_MB: int = 5
TOOL_LOOP_LIMIT: int = 6
```

The frontend reads only `VITE_API_BASE_URL`. Docker Compose loads the root `.env` and passes explicit variables to services. No frontend/backend `.env` files are allowed. Secrets must be masked by model representation and logs.

### 7.2 Shared database conventions

- Use one async SQLAlchemy engine targeting `SQLITE_PATH` with `sqlite+aiosqlite`.
- On every application connection, set and verify `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, and `PRAGMA busy_timeout=5000`.
- Non-singleton IDs come from one shared lowercase UUID v4 helper and are stored as `TEXT`.
- Shared timestamps are timezone-aware UTC `DATETIME`; application code updates `updated_at` and no trigger does so.
- Every table defines `created_at` and `updated_at` as non-null.
- JSON columns use SQLAlchemy `JSON`; later write services must validate corresponding Pydantic models before persistence. Do not query inside JSON documents.
- Enums are `TEXT` plus named `CHECK` constraints. Booleans use SQLAlchemy `Boolean`/SQLite integer.
- Constraint/index names exactly follow Master Section 6.1: `pk_`, `fk_`, `uq_`, `ck_`, and `ix_` conventions.
- Never keep a transaction open across provider calls, URL reads, file writes, Neo4j writes, or SSE streaming.

### 7.3 Application table ownership

The initial migration and model modules must reproduce Master Section 6.2 exactly; no additional application columns or tables are permitted.

| Module | Tables | Mandatory database invariants |
|---|---|---|
| `attachments.py` | `attachments` | UUID PK, unique SHA-256 hash, unique relative storage path, MIME `application/pdf`, positive size/page constraints, `staged/active/failed`, failure coupling, partial unique one-active index. |
| `profiles.py` | `candidate_profile`, `profile_drafts`, `job_preferences` | Singleton IDs `active/current/active`; attachment FKs and delete rules; zero/one profile and draft; one seeded preferences row; JSON columns only. |
| `jobs.py` | `job_posts` | UUID PK; URL/text null coupling; exact content-hash uniqueness; received/processing/processed/failed rules; full/partial/unscorable quality; failure coupling; all-or-none embedding fields; processed/scorable embedding rules; processing-quality index. |
| `chat.py` | `conversation`, `chat_messages`, `agent_runs`, `tool_executions` | Singleton conversation; role/content coupling; deterministic history index; run state/pending approval/completion coupling; unique user-message run; exact tool statuses; unique `(run_id, tool_call_id)`; terminal result/duration/error coupling. |

Exact status values are immutable across phases:

```text
attachments.state: staged | active | failed
job_posts.processing_status: received | processing | processed | failed
job_posts.jd_quality: full | partial | unscorable
chat_messages.role: user | assistant | system
agent_runs.state: running | interrupted | completed | failed
tool_executions.status: pending | running | completed | failed
```

Static database checks enforce enum membership, singleton IDs, scalar ranges, and simple null coupling. Pydantic/services in later phases enforce JSON shape, finite/exact-length embeddings, configuration-dependent PDF/embedding limits, allowed transitions, and cross-row invariants.

### 7.4 Foreign keys, seeds, and migration ownership

Use exactly these delete actions:

```text
attachments -> candidate_profile.active_attachment_id: RESTRICT
attachments -> profile_drafts.source_attachment_id: CASCADE
conversation -> chat_messages.conversation_id: CASCADE
chat_messages -> agent_runs.user_message_id: CASCADE
agent_runs -> tool_executions.run_id: CASCADE
```

Migration `0001_initial_schema.py` must:

1. Create the nine application tables in dependency order.
2. Create every named constraint, unique/index definition, and partial unique index from Master Section 6.
3. Seed `conversation(id='main')` and `job_preferences(id='active')` idempotently in one transaction. Empty preferences contain exactly `target_roles`, `preferred_locations`, `acceptable_work_modes`, and `target_seniority`, all empty lists.
4. Not create `candidate_profile`; that row appears only after the first approved CV.
5. Use SQLite batch mode for future-compatible constraint changes.
6. Never create, alter, or drop LangGraph checkpoint tables.

Normal startup runs an idempotent singleton-seed safeguard after migrations are applied, but never `Base.metadata.create_all()`.

### 7.5 Attachment storage

`backend/app/storage/attachments.py` owns filesystem concerns only:

- Root all paths under `FILES_DIR` and expose only paths relative to that root for database storage.
- Generate the path from the application UUID, not the original filename.
- Reject path traversal and never trust the display filename as a path.
- Write to a temporary sibling and atomically replace the final file only after a complete write.
- Provide existence/open/delete operations used by later services; deletion is best effort only when explicitly requested by a service.
- Do not parse PDFs, compute profile drafts, or mutate attachment database state.

### 7.6 Neo4j base contract

Neo4j setup creates idempotently:

- Unique constraint on `Candidate.id`.
- Unique constraint on `Job.id`.
- Unique constraint on `Skill.canonical_key`.
- One cosine vector index on `Job.embedding` with `vector.dimensions=1536`.

The driver module owns connection lifecycle and executes parameterized Cypher only. It must not contain CV/JD sync logic yet. Neo4j identities are fixed as Candidate `active`, SQLite Job UUID, and normalized `Skill.canonical_key`; no independent graph IDs are allowed.

### 7.7 Health endpoint

`GET /api/health` returns a validated payload with overall status and three components:

```text
sqlite: available | unavailable
filesystem: available | unavailable
neo4j: available | unavailable
```

SQLite health performs a trivial query through the configured application session. Filesystem health verifies the configured directory can be created/accessed without writing user data. Neo4j health calls the driver’s connectivity check. An unavailable dependency is represented explicitly; no health check mutates schema except the separately invoked idempotent graph-initialization startup step.

### 7.8 Docker Compose contract

- Services: `frontend`, `backend`, and `neo4j` only; no worker, Redis, Celery, Kafka, or extra database.
- Backend and frontend listen on `0.0.0.0` inside containers.
- Publish application and Neo4j host ports on `127.0.0.1` only.
- Mount one persistent application data volume for SQLite and uploaded files, and persistent Neo4j data/log volumes.
- Backend depends on Neo4j health but treats Neo4j availability as a reported component state rather than changing SQLite ownership.
- Load the single root `.env`; never mount `.env.example` as runtime configuration.

## 8. Implementation Steps

- [ ] Expand the pinned backend project with settings, shared UUID/UTC utilities, FastAPI startup/shutdown, and local lint/type/test commands.
- [ ] Expand the frontend project with TypeScript/Vite scripts and the pinned Astryx neutral theme, keeping the UI to a minimal app shell.
- [ ] Implement the async SQLite engine/session factory and connection PRAGMAs.
- [ ] Search the repository before adding each shared helper; keep UUID, UTC, settings, and session logic single-sourced.
- [ ] Implement focused SQLAlchemy model modules for all Master Section 6 tables and exact invariants.
- [ ] Configure Alembic batch mode and write the initial migration with named constraints/indexes and singleton seeds.
- [ ] Prove migration upgrade works on a fresh database and is a no-op at head on an initialized database.
- [ ] Implement the filesystem-only attachment storage abstraction and path-safety tests.
- [ ] Implement Neo4j driver lifecycle, connectivity, constraints, and 1536-dimensional cosine vector index setup.
- [ ] Implement the validated health response and `GET /api/health` route.
- [ ] Build Dockerfiles and Compose with root-env loading, persistent volumes, health checks, and loopback-only published ports.
- [ ] Add unit/integration tests for settings, secrets masking, PRAGMAs, every constraint/index/FK, singleton seeding, storage, health, and idempotent graph setup.
- [ ] Run all local backend/frontend/migration/Compose checks and fix only Phase 1 scope failures.

## 9. Verification & Testing Plan

### Automated commands

Use the exact environment/bootstrap command locked in the Phase 0 report, then run the project’s single-purpose scripts:

```powershell
Set-Location backend
python -m ruff check .
python -m mypy app
python -m pytest tests/unit -q
python -m pytest tests/integration/test_database_contract.py tests/integration/test_migrations.py -q
```

Expected: lint/type checks pass; tests prove every named table constraint/index/FK, singleton seed, partial unique active-attachment rule, and all three PRAGMAs.

```powershell
alembic upgrade head
alembic current
alembic upgrade head
```

Expected: first command creates schema/seeds, `current` reports head, second upgrade succeeds without duplicating singleton rows or altering unrelated/checkpoint tables.

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Expected: all commands pass using the lockfile and pinned Astryx public imports.

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build
```

Expected: Compose configuration resolves from the root env; frontend, backend, and Neo4j become healthy; no extra runtime service appears.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected: SQLite, filesystem, and Neo4j are `available` and overall health is successful.

### Manual verification

- Start once on empty volumes and once on already-initialized volumes.
- Inspect published port bindings and confirm they use `127.0.0.1`.
- Confirm application data survives container recreation and no runtime data enters Git.
- Confirm `.env` is the only runtime environment file and secrets are absent from logs/health payloads.
- Inspect representative source files for single responsibility; split any newly created source file that grows materially beyond 300 lines unless a generated migration is the unavoidable exception.

### Failure handling

- Migration/constraint mismatch blocks Plan 3; do not compensate in repositories.
- A non-idempotent Neo4j setup blocks Plan 3; fix setup rather than suppressing errors.
- Health may report an unavailable Neo4j instance, but SQLite must remain authoritative and usable.
- Any secret exposure or non-loopback host publication blocks the phase.

## 10. Handoff Notes for Plan 3 / Master Phase 2

Plan 3 receives:

- Runnable frontend/backend/Neo4j services under Docker Compose.
- One validated settings object and one root `.env` contract.
- All application tables, named constraints, indexes, foreign keys, and singleton seeds at Alembic head.
- Async application sessions with required PRAGMAs and shared UUID/UTC helpers.
- Filesystem attachment storage primitives, but no upload/parse behavior.
- Neo4j driver plus idempotent uniqueness/vector-index setup, but no domain synchronization.
- A minimal Astryx-themed frontend foundation and working local commands.

Plan 3 must reuse these primitives. It must not duplicate settings/session/ID/time/storage/driver logic, alter schema/status values, use `create_all()`, or add business writes through new public CRUD endpoints. Any schema change requires an explicit migration and Master alignment before later phase work proceeds.
