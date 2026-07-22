# JobAgent

## Overview

JobAgent is a local, single-user CV/JD chat and deterministic matching MVP. It
combines a React/Astryx chat interface, a FastAPI/LangGraph backend, SQLite
application state, retained PDF files, a rebuildable Neo4j projection, and
ShopAIKey chat and embedding APIs.

The supported runtime is one Docker Compose project with exactly three services:

- `frontend` on `127.0.0.1:5173`
- `backend` on `127.0.0.1:8000`
- `neo4j` on `127.0.0.1:7474` (HTTP) and `127.0.0.1:7687` (Bolt)

SQLite and retained files live together in the backend `app_data` volume.
Neo4j uses separate data and log volumes. All published ports are loopback-only;
this repository is not configured as a public or multi-user service.

## Current Baseline

The last committed product baseline is **Plan 15 Batch03** at commit
`b98e606e` (`P15B3: Complete`), after Batch01 (`5208ea50`) and Batch02
(`186c7b8`):

- Batch01: pure semantic guard, guarded extractor integration, synthetic golden
  fixture, and ingestion routing through the guarded path.
- Batch02: revision-checked same-ID extraction replacement, staged re-extraction
  coordinator (provider/embedding outside transactions; CAS on `id` +
  `updated_at`), and strict `POST /api/jobs/{job_id}/reextract` with coupled
  graph partial-success response.
- Batch03: complete saved-JD extraction detail groups, accessible
  `JobReextractDialog`, and sole-owner non-optimistic re-extraction through
  `useSavedJobsState` in `ObservabilitySidebar` (graph-generation invalidation
  reused; no second state owner).

**Plan 15 Batch04** (Diagnostic and Release Evidence) is on the working tree over
that base: bounded live synthetic JD diagnostic
(`infrastructure/scripts/diagnose_jd_extraction.py`), README command docs,
append-only sanitized acceptance ledger rows, and test-only allowlist/fixture
hygiene so full backend gates stay green after the re-extract route and semantic
guard.

Scope, acceptance, and design authority:

- [Plan 15](docs/plans/Plan_15.md)
- [Task 15](docs/tasks/task_15.md)
- [JD extraction quality guard design](docs/superpowers/specs/2026-07-21-jd-extraction-quality-guard-design.md)
- [Plan 14](docs/plans/Plan_14.md)
- [Task 14](docs/tasks/task_14.md)
- [Acceptance documents](docs/acceptance/)

## What This Repository Does

This is a full-stack local application workspace. A user can:

1. Chat normally with one persistent conversation.
2. Upload a digital-text PDF CV, extract its complete document structure, review
   a derived profile draft, and explicitly approve or revise it.
3. Retain and inspect CV versions, reprocess active or archived CVs, and delete
   eligible non-active CVs.
4. Paste a JD or provide a public HTTP(S) URL, explicitly confirm passive pasted
   text before saving, and retain exact-hash-deduplicated Jobs.
5. Explicitly evaluate a saved Job against the current approved CV/profile and
   inspect deterministic score components and skill gaps.
6. Browse CV history and chunk lists, open retained CVs and chunk
   details, inspect Agent runs and saved Jobs, and view a bounded Neo4j graph.

Runtime behavior is authoritative in source code and configuration. The
[Master Plan](docs/plans/Master_plan.md) defines stable product contracts;
incremental plans, task files, and acceptance documents explain why and how the
accepted baseline was reached.

## Repository Structure

```text
.
├── backend/          # FastAPI, Agent, services, persistence, graph, tests
├── frontend/         # React/Astryx UI, typed clients, reducer, tests
├── infrastructure/   # Compose, images, graph seed, diagnostics, rebuild wrapper
├── docs/             # Plans, tasks, acceptance, reviews, reports, designs
├── .env.example      # Tracked non-runtime environment template
└── README.md         # Current architecture and operations guide
```

- [`backend/`](backend/) owns the FastAPI API, LangGraph Agent, domain services,
  SQLAlchemy repositories and models, Alembic migrations, retained-file access,
  Neo4j synchronization/rebuild logic, ShopAIKey adapters, and backend tests.
- [`frontend/`](frontend/) owns the React/Astryx chat, CV Manager, saved-JD and
  observability panels, the single SSE reducer, typed API clients, and frontend
  tests.
- [`infrastructure/`](infrastructure/) owns Docker Compose, backend/frontend
  Dockerfiles, Neo4j skill seed data, provider/PDF diagnostics, and graph rebuild
  wrappers.
- [`docs/`](docs/) owns the Master Plan, incremental plans, execution tasks,
  acceptance evidence, reviews, reports, and approved design specifications.
- `.agent/` is ignored workflow evidence/state. It is not product source and must
  never be staged in product commits.

Dependency, build, cache, and runtime locations such as `.venv/`,
`node_modules/`, `dist/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`,
`data/`, and Docker volumes are not version-controlled project source. In the
local runtime, `app_data` remains authoritative for SQLite and retained files;
Neo4j volumes contain derived graph data and logs.

## Architecture

```text
React/Astryx UI
  -> typed fetch/SSE clients
  -> FastAPI routes
  -> application services / Agent runner
  -> LangGraph Agent and seven tools
  -> SQLite + retained files (authoritative)
  -> Neo4j (derived/rebuildable)
  -> ShopAIKey chat and embeddings
```

The boundaries are intentionally narrow:

- [`frontend/src/main.tsx`](frontend/src/main.tsx) installs Astryx styles and the
  neutral theme, then mounts the [application shell](frontend/src/app/App.tsx).
- [`backend/app/main.py`](backend/app/main.py) owns application lifespan, CORS,
  shared SQLite/storage/Neo4j resources, and route registration. Startup does
  not create schemas; the backend container runs Alembic before Uvicorn.
- API modules validate transport inputs and delegate. Business rules stay in
  `backend/app/services/`; persistence details stay in repositories and graph
  modules.
- [`backend/app/agent/graph.py`](backend/app/agent/graph.py) owns one decision
  node and one ToolNode loop. [`backend/app/tools/registry.py`](backend/app/tools/registry.py)
  registers exactly seven production tools.
- [`backend/app/agent/runner.py`](backend/app/agent/runner.py) owns request-scoped
  checkpointing and typed SSE publication. Application services persist durable
  run/message/tool truth before terminal checkpoint cleanup.
- SQLite owns raw inputs, canonical records, chat/run/tool history, drafts,
  evaluations, and revision truth. Retained PDF files are authoritative file
  artifacts. Post-commit Neo4j synchronization is attempted immediately;
  failures leave SQLite/files authoritative and the Neo4j projection
  rebuildable.
- The frontend never calls SQLite, Neo4j, or ShopAIKey directly. Agent tools call
  Python services directly rather than calling FastAPI back over HTTP.

## Main Workflows

### 1. CV upload, extraction, approval, and activation

1. [`CvSidebar`](frontend/src/features/profile/CvSidebar.tsx) or
   [`ChatPage`](frontend/src/features/chat/ChatPage.tsx) sends the PDF through the
   shared upload client to `POST /api/attachments/cv`.
2. The [attachment upload route](backend/app/api/attachments.py) delegates to the
   [CV upload service](backend/app/services/cv_upload.py), which checks the
   interrupted-run guard before reading bytes, validates PDF MIME/magic/size/page
   limits, hashes while staging, and returns an attachment ID after exact-hash
   reuse or retry. Upload staging does not itself start extraction.
3. The [application shell](frontend/src/app/App.tsx) schedules a follow-up chat
   turn after a sidebar upload. A composer upload remains a pending attachment in
   [`ChatPage`](frontend/src/features/chat/ChatPage.tsx) until the user submits a
   message. That subsequent Agent turn carries the attachment ID and invokes the
   proposal/extraction path.
4. The [PDF extraction service](backend/app/services/pdf_extraction.py) owns PDF
   text extraction, while the
   [profile extraction service](backend/app/services/profile_extraction.py) owns
   deterministic chunking and document-first orchestration. Document extraction
   and projection details belong to the
   [CV document extraction service](backend/app/services/cv_document_extraction.py)
   and [CV document projection service](backend/app/services/cv_document_projection.py).
5. The [profile draft service](backend/app/services/profile_drafts.py) atomically
   persists the chunks, document draft, and profile draft before the profile
   confirmation interrupt. The UI displays **Save Profile** and **Request
   Changes** from the durable approval projection.
6. Resume continues the same run and tool identity. Requesting changes preserves
   the draft; saving delegates to the
   [profile approval service](backend/app/services/profile_approval.py).
7. Approval commits the selected attachment/document/profile/preferences in one
   constraint-safe SQLite transaction, retains the former PDF as archived, then
   attempts to project the active Candidate/Skill/CV branch to Neo4j. A graph
   failure never rolls back committed SQLite truth.

### 2. Chat turn, Agent loop, and durable history

1. [`ChatPage`](frontend/src/features/chat/ChatPage.tsx) sends a message and
   attachment IDs through the [chat SSE client](frontend/src/lib/api/chat.ts) to
   `POST /api/chat/turns`.
2. The [chat routes](backend/app/api/chat.py) prime the service stream so
   pre-stream failures remain JSON errors; they then frame only validated SSE
   events.
3. The [chat-turn service](backend/app/services/chat_turns.py) creates the
   durable user message and `running` run in a short transaction, then loads
   bounded recent, approved candidate, and active-CV outline context.
4. The [Agent runner](backend/app/agent/runner.py) streams the
   Agent/decision/ToolNode loop from the [Agent graph](backend/app/agent/graph.py).
   Tools persist durable execution state and publish compact `tool_status`
   events; no application transaction is held across provider calls or SSE.
5. Completion, failure, or interruption is persisted before checkpoint cleanup.
   Interrupted checkpoints remain resumable; completed/failed checkpoints for
   that run are deleted after durable terminal commit.
6. The frontend sends every event through
   [`frontend/src/features/chat/reducer.ts`](frontend/src/features/chat/reducer.ts)
   and rehydrates terminal history from SQLite. A disconnect never invents
   completion or a tool result.

### 3. Pasted JD confirmation and save

1. The initiating user message is persisted as a normal chat turn. The Agent
   uses semantic intent plus the approved deterministic precedence in the
   [Agent graph](backend/app/agent/graph.py) to distinguish analysis, opt-out,
   direct URL/text saves, and passive pasted-JD save intent.
2. Passive save intent becomes one canonical `save_job` call with
   `source='current_message'`. The
   [JD save confirmation service](backend/app/services/job_save_confirmation.py)
   reloads the exact durable initiating message and builds a bounded confirmation
   projection without copying raw JD text into SSE or pending state.
3. The action labels owned by
   the [JD confirmation UI contract](frontend/src/features/chat/jobSaveConfirmation.ts)
   are **Không lưu** and **Lưu JD**. **Không lưu** cancels the same interrupted
   tool execution with no Job, extraction, embedding, evaluation, or Neo4j
   mutation. **Lưu JD** resumes that same run/tool identity and accepts the
   durable current-message content.
4. The [JD ingestion service](backend/app/services/jd_ingestion.py) computes the
   exact SHA-256 content hash and selects one branch: an existing non-failed Job
   returns immediately without extraction, guard, embedding, or graph sync; an
   existing failed Job retries in place; otherwise a new Job row is created and
   processed.
5. Retry/new processing calls the shared
   [JD extraction service](backend/app/services/jd_extraction.py): locked
   structured provider output, pure
   [semantic guard](backend/app/services/jd_extraction_guard.py) before
   SkillNormalizer projection, and at most one sanitized schema-or-guard repair.
   ShopAIKey embedding and terminal persistence follow only after an accepted
   extraction. Only a newly processed scorable Job attempts post-commit Neo4j
   synchronization. Saving alone does **not** automatically evaluate the Job.

### 4. Explicit saved-Job evaluation

1. The [saved-JD panel](frontend/src/features/jobs/SavedJobsPanel.tsx), backed by
   [saved-JD state](frontend/src/features/jobs/savedJobsState.ts), uses the
   [saved-Job API client](frontend/src/features/jobs/api.ts) to call
   `POST /api/jobs/{job_id}/evaluate`.
2. The separate zero-result match recovery in
   [`ChatPage`](frontend/src/features/chat/ChatPage.tsx) is owned by
   [`useSavedJobRecovery`](frontend/src/features/chat/useSavedJobRecovery.ts) and
   calls `POST /api/jobs/save-and-evaluate` through the same typed client.
3. The [saved-Job routes](backend/app/api/jobs.py) delegate to the saved-JD
   service and [Job evaluation service](backend/app/services/job_evaluation.py).
4. The evaluation service derives a revision-keyed context from the exact Job,
   active attachment, approved profile/preferences, CV source hash, and scoring
   contract. An existing current result is returned before provider or graph
   work.
5. A new result passes the Candidate/Job consistency gate, embeds the Candidate
   once, retrieves the exact Job from Neo4j, reuses deterministic scoring, then
   rechecks the context before persisting.
6. The frontend currentness contract in
   [saved-Job types](frontend/src/features/jobs/types.ts) and the
   [saved-Job detail view](frontend/src/features/jobs/SavedJobDetail.tsx) expose
   `none`, `current`, or `stale`. CV/profile/preference changes only mark prior
   results stale; recomputation requires another explicit action.

### 4b. Explicit same-ID re-extraction (Plan 15 Batch02)

1. `POST /api/jobs/{job_id}/reextract` accepts only an absent or empty JSON body
   (`extra='forbid'`); the server reloads the retained Job by ID and never takes
   client replacement fields.
2. The [re-extraction coordinator](backend/app/services/job_reextraction.py)
   stages guarded extraction, quality classification, and locked embedding
   outside SQLite transactions; only a `full` or `partial` result reaches one
   revision-checked repository CAS update
   ([jobs repository](backend/app/repositories/jobs.py)).
3. Successful replacement advances `job_posts.updated_at`, preserves identity,
   source, raw content/hash, and all evaluation rows, and projects prior
   evaluations as `stale` with zero evaluation/scoring calls.
4. After SQLite commit, same-ID `sync_job` runs. Graph failure keeps SQLite truth
   and returns HTTP 200 with `sync_ok=false`, `NEO4J_SYNC_FAILED`, and the safe
   rebuild instruction. Pre-commit failures use `detail={code, summary}` only.
5. In the UI, saved-JD detail renders metadata, ordered responsibilities,
   required/preferred skills (with confidence), extraction confidence, and
   collapsed evidence with explicit empty states. **Re-extract JD** opens
   [`JobReextractDialog`](frontend/src/features/jobs/JobReextractDialog.tsx),
   which names the Job and states identity/raw preservation, pre-commit
   preservation, stale-on-success, and no automatic evaluation. Confirm runs
   only through the sole
   [`useSavedJobsState`](frontend/src/features/jobs/savedJobsState.ts) owner
   wired from
   [`ObservabilitySidebar`](frontend/src/features/observability/ObservabilitySidebar.tsx):
   non-optimistic compact-row patch, forced detail GET, currentness refresh,
   and graph-generation bump; graph-warning success still refreshes SQLite
   views and shows rebuild guidance; pre-commit failure preserves cached
   list/detail and shows only a safe summary.

### 5. CV and Job deletion

1. CV deletion enters through the [CV routes](backend/app/api/cvs.py) and
   [CV Manager service](backend/app/services/cv_manager.py). Active CV deletion is
   rejected; eligible rows use explicit CV ownership to clean checkpoints,
   retained files, chunks/documents/drafts, CV-scoped history, and graph data.
2. Partial CV cleanup retains retryable deletion state and returns a stable safe
   error. SQLite finalization occurs only after required owned cleanup succeeds.
3. Job deletion enters through the [saved-Job routes](backend/app/api/jobs.py) and
   the [Job deletion service](backend/app/services/job_deletion.py).
   It removes the exact Job branch from Neo4j first, then finalizes the SQLite
   Job/evaluation cascade.
4. A Job graph failure preserves SQLite for a safe retry. Shared Skill seed data,
   Candidate/CV data, other Jobs, and unrelated chat history are preserved.

### 6. Observability and graph rebuild

1. The sidebar uses the
   [observability API client](frontend/src/features/observability/api.ts) for
   cursor-paginated CV history, chunk lists, and Agent runs; exact retained-file
   and chunk-detail reads; and a bounded graph snapshot.
2. The [observability routes](backend/app/api/observability.py) expose read-only
   endpoints and delegate to the
   [observability service](backend/app/services/observability.py).
   The graph response is an allowlisted `ready`, `stale`, or `unavailable`
   projection; clients cannot submit Cypher.
3. If Neo4j is missing or stale, the explicit
   [graph rebuild entrypoint](backend/app/graph/rebuild.py) reads authoritative
   SQLite and stored embeddings/documents, clears only JobAgent-owned graph
   labels and relationships, and recreates the projection. It does not call
   ShopAIKey or mutate SQLite.

## Frontend

The frontend is React 19 + TypeScript + Vite with Astryx 0.1.4 and the neutral
theme. The [application shell](frontend/src/app/App.tsx) composes one `AppShell`,
the resizable CV/observability/saved-JD sidebar, and `ChatPage`.

Key ownership rules:

- `features/chat/` owns history hydration, composer/attachments, approval cards,
  assistant Markdown, active-CV evidence, tool activity, empty match recovery,
  and the only chat/SSE reducer.
- `features/profile/` owns active/draft profile reads, CV upload presentation,
  active-PDF access, and approval presentation.
- `features/observability/` owns CV Manager, chunks, run history, bounded graph
  presentation, request/cache state, and deletion UI.
- `features/jobs/` owns typed saved-JD contracts, list/detail/currentness state,
  complete extraction detail groups, explicit evaluation/re-evaluation,
  confirmation-based same-ID re-extraction (`JobReextractDialog` +
  `confirmReextract`), deterministic match cards, and deletion UI. The sole
  `useSavedJobsState` instance lives in `ObservabilitySidebar` and is passed
  into `SavedJobsPanel` by props only.
- `lib/api/chat.ts` owns the frontend API origin and chat/resume/reprocess SSE
  transports; `lib/sse/` validates and consumes stream frames.

[`frontend/AGENTS.md`](frontend/AGENTS.md) contains mandatory Astryx guidance.
Use the CLI to inspect components before changing UI code; do not invent
component props or introduce a second stream store.

## Backend

The backend is Python 3.11+ with FastAPI, Pydantic v2, SQLAlchemy/aiosqlite,
Alembic, LangGraph, pypdf, Trafilatura, Neo4j, and OpenAI-compatible ShopAIKey
adapters. The production container currently uses Python 3.13.7.

The main layers are:

- `app/api/`: thin HTTP/SSE transport and safe error mapping.
- `app/agent/`: prompt/context construction, the one-Agent graph, checkpoints,
  and the request-scoped runner.
- `app/tools/`: seven Agent-facing tools and durable execution wrappers.
- `app/services/`: CV/JD ingestion, approval, evaluation, matching,
  same-ID re-extraction (`job_reextraction`), observability, and deletion
  orchestration.
- `app/repositories/`, `app/db/`, `app/schemas/`: persistence access, database
  models/session ownership, and validated public/domain contracts.
- `app/graph/`: constraints, consistency gates, retrieval, focused sync/delete,
  and the explicit rebuild.
- `app/adapters/`: ShopAIKey chat and embedding boundaries.
- `migrations/`: the only SQLite schema evolution path. Do not use `create_all()`
  or add schema creation to application startup.
- `tests/`: fake-backed unit, integration, and end-to-end coverage plus synthetic
  committed fixtures.

The public API is registered in [`backend/app/main.py`](backend/app/main.py).
There is no public profile CRUD: profile writes flow through the Agent approval
interrupt. Public saved-JD mutations are deliberately limited to explicit
save-and-evaluate, evaluate, re-extract, and delete routes.

## Data, Storage, and External Services

| Data or service | Owner/location | Contract |
| --- | --- | --- |
| SQLite application DB | `app_data:/data/jobagent.db` | Authoritative canonical state, chat/runs/tools, drafts, Jobs, evaluations, checkpoints |
| Retained CV files | `app_data:/data/files` | Authoritative UUID-relative PDF artifacts; never SQLite blobs |
| Neo4j graph | `neo4j_data:/data` | Derived Candidate/CV/Job/Skill projection and vector index; rebuildable |
| Neo4j logs | `neo4j_logs:/logs` | Local container logs; not repository evidence |
| ShopAIKey chat | Configured OpenAI-compatible base URL | Agent decisions and structured extraction |
| ShopAIKey embeddings | Same provider, locked model/dimensions | Candidate and scorable Job embeddings |
| Root `.env` | Ignored, user-managed | The only runtime environment file; never commit or print it |
| Synthetic PDF fixtures | `backend/tests/fixtures/cv/` | The only CV-like artifacts intended for Git |

SQLite commits first. Post-commit Neo4j synchronization is attempted afterward
and may fail independently. Runtime databases, uploads, real CV/JD content,
graph dumps, provider transcripts, and secrets must remain outside Git.

## Configuration

The backend [settings owner](backend/app/core/settings.py) reads only the
repository-root `.env`; process environment variables take precedence. The
tracked [.env.example](.env.example) is documentation only and is never loaded
as runtime configuration. The supported Compose workflow interpolates its
inputs from the root `.env`, while Vite consumes `VITE_API_BASE_URL` when the
frontend image is built.

In the table, **Compose input; Settings default** means the Python setting has a
default, but Compose still passes an explicitly interpolated value. Keep every
Compose input populated: a missing or blank interpolation can replace the
Python default.

| Variable | Required | Purpose | Evidence |
| --- | --- | --- | --- |
| `APP_ENV` | Compose input; Settings default | Runtime environment selector and local rebuild guard | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `FRONTEND_ORIGIN` | Yes | Allowed browser origin for backend CORS | [Settings](backend/app/core/settings.py), [application](backend/app/main.py) |
| `VITE_API_BASE_URL` | Yes, at frontend build | Browser-visible backend API origin | [frontend image](infrastructure/docker/frontend.Dockerfile), [API client](frontend/src/lib/api/chat.ts) |
| `SQLITE_PATH` | Yes | Authoritative SQLite database path | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `FILES_DIR` | Yes | Retained CV file root | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `NEO4J_URI` | Yes | Neo4j Bolt connection target | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `NEO4J_USER` | Yes | Neo4j authentication username | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `NEO4J_PASSWORD` | Yes, secret | Neo4j authentication password | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `SHOPAIKEY_BASE_URL` | Yes | OpenAI-compatible provider base URL | [Settings](backend/app/core/settings.py), [diagnostic](infrastructure/scripts/diagnose_shopaikey.py) |
| `SHOPAIKEY_API_KEY` | Yes, secret | Provider credential for live chat and embeddings | [Settings](backend/app/core/settings.py), [diagnostic](infrastructure/scripts/diagnose_shopaikey.py) |
| `LLM_MODEL` | Compose input; Settings default | Chat, tool-choice, and structured-extraction model | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `LLM_TEMPERATURE` | Compose input; Settings default | LLM sampling temperature | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `EMBEDDING_MODEL` | Compose input; Settings default | Candidate and Job embedding model | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `EMBEDDING_DIMENSIONS` | Compose input; Settings default | Locked embedding vector width | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `MAX_PDF_SIZE_MB` | Compose input; Settings default | Maximum accepted PDF upload size | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `MAX_PDF_PAGES` | Compose input; Settings default | Maximum accepted PDF page count | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `URL_FETCH_TIMEOUT_SECONDS` | Compose input; Settings default | Public JD URL request timeout | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `URL_MAX_RESPONSE_MB` | Compose input; Settings default | Maximum public JD URL response size | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |
| `TOOL_LOOP_LIMIT` | Compose input; Settings default | Maximum Agent tool-loop passes | [Settings](backend/app/core/settings.py), [Compose](infrastructure/docker-compose.yml) |

### Pending CV configuration alignment

The amended plan portfolio makes Plan 2 the sole external owner and Plan 9 the
runtime consumer of this exact five-variable contract:

| Variable | Required target behavior | Runtime consumer | Planning authority |
| --- | --- | --- | --- |
| `CV_EXTRACT_BATCH_MAX_CHARS=12000` | Root-template entry, validated Settings default, and explicit backend Compose pass-through | Raw ordered CV extraction batches | [Plan 2](docs/plans/Plan_2.md), [Plan 9](docs/plans/Plan_9.md) |
| `CV_CONSOLIDATE_BATCH_MAX_CHARS=12000` | Root-template entry, validated Settings default, and explicit backend Compose pass-through | Fragment consolidation/merge batches | [Plan 2](docs/plans/Plan_2.md), [Plan 9](docs/plans/Plan_9.md) |
| `CV_READ_DEFAULT_MAX_CHARS=6000` | Root-template entry, validated Settings default, and explicit backend Compose pass-through | Default bounded active-CV response size | [Plan 2](docs/plans/Plan_2.md), [Plan 9](docs/plans/Plan_9.md) |
| `CV_READ_HARD_MAX_CHARS=12000` | Root-template entry, validated Settings default, and explicit backend Compose pass-through | Absolute active-CV response size | [Plan 2](docs/plans/Plan_2.md), [Plan 9](docs/plans/Plan_9.md) |
| `CV_READ_MAX_RESULTS=10` | Root-template entry, validated Settings default, and explicit backend Compose pass-through | Absolute section/search result count | [Plan 2](docs/plans/Plan_2.md), [Plan 9](docs/plans/Plan_9.md) |

This is an approved planning contract, not a claim that the current Plan 14
runtime already supports those variables. The current source still contains the
backend-only legacy `CV_DOCUMENT_BATCH_MAX_CHARS`; it is absent from
`.env.example` and Compose. Do not add either the five new names or the legacy
name to a local `.env` expecting them to affect the current Compose runtime.
Implementation must replace the legacy field, wire all five names through the
tracked template and backend Compose environment, add the Plan 2/Plan 9 tests,
and revalidate before this section moves into the supported-variable table.

## Setup

Run setup from the repository root in PowerShell. Copy the tracked template,
fill the local secret fields without printing them, create the project virtual
environment, install the backend and then install the locked frontend tree:

```powershell
Copy-Item .env.example .env
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -e .\backend
Set-Location frontend
npm ci
Set-Location ..
```

Keep `.env` ignored and local. Do not create nested backend or frontend env
files, and do not stage generated dependency directories.

## Running the Project

The supported runtime is the root Compose project. First validate its service
shape, then build and wait for the three health checks:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config --services
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

The confirmed local endpoints are:

| Surface | Endpoint |
| --- | --- |
| Frontend | `http://localhost:5173/` |
| Backend health | `http://127.0.0.1:8000/api/health` |
| Neo4j Browser | `http://127.0.0.1:7474/` |
| Neo4j Bolt | `bolt://127.0.0.1:7687` |

An HTTP 200 from health is not sufficient by itself: confirm `overall` and the
SQLite, filesystem, and Neo4j component states are all available.

SQLite application-schema migration is explicit. The
[backend container command](infrastructure/docker/backend.Dockerfile) runs
`alembic upgrade head` before it executes Uvicorn. The separate
[FastAPI lifespan](backend/app/main.py) does not create or migrate the SQLite
application schema; it may initialize required singleton data and, when Neo4j
is reachable, ensure idempotent Neo4j constraints and indexes. Do not add
`create_all()` or SQLite migration work to application startup.

## Testing and Validation

Run focused tests for the area changed, then use the full repository gates from
the root. These commands use the project virtual environment created above:

```powershell
Set-Location backend
# Plan 15 Batch01 focused backend subset (guard + extraction + ingestion)
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction_guard.py tests/unit/test_jd_extraction.py tests/unit/test_skill_normalization.py tests/unit/test_jd_quality.py tests/integration/test_job_ingestion.py -q
# Plan 15 Batch02 focused backend subset (CAS repo + re-extraction + API)
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_jobs_repository.py tests/integration/test_job_reextraction.py tests/integration/test_job_sync.py tests/integration/test_saved_jobs_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q

Set-Location ..\frontend
# Plan 15 Batch03 focused frontend subset (parser/detail/dialog/state/sidebar)
npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-sidebar.test.tsx
npm test -- --run
npm run lint
npm run typecheck
npm run build

Set-Location ..
python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json
& '.\.venv\Scripts\python.exe' infrastructure\scripts\verify_pdf_extraction.py
& '.\.venv\Scripts\python.exe' infrastructure\scripts\diagnose_shopaikey.py
$env:PYTHONPATH=(Resolve-Path 'backend').Path; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_jd_extraction.py --cases backend/tests/fixtures/jd_extraction_golden.json
$env:PYTHONPATH=(Resolve-Path 'backend').Path; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_cross_profession_skills.py --cases backend/tests/fixtures/skill_extraction_golden.json
& '.\.venv\Scripts\python.exe' infrastructure\scripts\rebuild_neo4j.py --help
```

The ShopAIKey diagnostic is a live network check and requires configured
provider credentials. It reports capability-level results without printing the
key. The PDF diagnostic uses committed synthetic fixtures. Most backend and
frontend automated tests use fakes, disposable stores, and synthetic fixtures;
they do not require or justify using real CV or JD content.

The JD extraction diagnostic is a separate explicit live-provider check over a
finite approved subset of the repository-authored synthetic golden fixture. It
requires valid root `.env` ShopAIKey credentials and network access, uses the
locked configured chat model and the production guarded extractor only, and
prints only case IDs with safe pass/fail codes (never source text, evidence,
prompts, provider payloads, secrets, or raw errors). It does not persist,
embed, sync graph state, or evaluate matches. Passing fake-provider unit tests
alone does not prove live semantic extraction quality; this command is not a
model benchmark or broad quality score.

The cross-profession skill diagnostic is the corresponding explicit live check
for Plan 16. It runs exactly three synthetic CVDocument cases and three synthetic
JD cases through the production guarded skill extractors and normalizer. It
performs no persistence, embedding, graph access, synchronization, or evaluation,
and prints only approved case IDs with status, aggregate skill count, and a safe
code. It requires valid root `.env` provider settings and the locked chat model;
do not add seed aliases or expose source/provider text to make it pass.

The host `rebuild_neo4j.py --help` command is non-destructive and prints the
authorized Compose rebuild command. It never opens the stores. Use the live
rebuild only for the recovery case described below.

Keep raw manual/browser data out of documentation and reports. Use the
[local release checklist](docs/acceptance/local_release_checklist.md),
[CV Manager checklist](docs/acceptance/cv_manager_checklist.md),
[saved-JD evaluation checklist](docs/acceptance/saved_jd_evaluation_checklist.md),
[full functional matrix](docs/acceptance/full_functional_test_matrix.md),
[cross-profession skill-map checklist](docs/acceptance/cross_profession_skill_map_checklist.md),
and [Plan 13 acceptance ledger](docs/acceptance/plan13_acceptance_ledger.md) for the
sanitized manual and browser procedures.

## Failure and Recovery

- **Health is degraded:** inspect the `overall`, `sqlite`, `filesystem`, and
  `neo4j` fields, then restore the failing dependency. A healthy HTTP transport
  with an unavailable component is not a healthy application. Preserve the
  named volumes while diagnosing.
- **An SSE stream disconnects:** the [reducer](frontend/src/features/chat/reducer.ts)
  treats it as nonterminal. Wait, then reload durable history; never infer
  completion or immediately repeat the action. Resume only if recovered history
  shows an interrupted approval.
- **A run reaches `TOOL_LOOP_LIMIT_EXCEEDED`:** the
  [Agent graph](backend/app/agent/graph.py) blocks the excess tool from executing,
  and the runner persists a durable terminal failure. Inspect durable history for
  tool behavior, then retry as a new bounded turn; do not raise the limit or
  resume the failed run.
- **Migration or backend start fails:** the Compose backend runs Alembic before
  Uvicorn, so a migration error prevents serving. Correct the configuration or
  migration issue and recreate the backend container; never bypass Alembic with
  `create_all()` or schema mutations in FastAPI startup.
- **Neo4j is unavailable, stale, or a post-commit sync fails:** SQLite and
  retained files remain authoritative. Restore Neo4j, then rebuild the derived
  projection from the running Compose backend:

  ```powershell
  docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.graph.rebuild
  ```

  The rebuild preflights stored embeddings, clears only JobAgent-owned graph
  labels and relationships, calls no provider, and does not mutate SQLite. Do
  not repair drift with independent Cypher edits or treat Neo4j as another
  source of truth.
- **Structured CV/JD/profile extraction hits a provider failure:** the shared
  [retry owner](backend/app/services/provider_retry.py) permits at most one
  application retry for timeouts or rate limits. JD extraction may use one
  shared repair attempt for schema validation failure or semantic-guard
  rejection, with fixed safe diagnostics only. Ordinary Agent chat and
  embedding requests have no promised application retry count. After a durable
  failure, restore availability and explicitly retry the user action; do not
  add unlimited retries, model switching, or hidden fallbacks.
- **A CV upload cannot be extracted:** use a digital-text PDF within the
  configured size and page limits. `NO_EXTRACTABLE_TEXT` is terminal for that
  attempt; there is no OCR path. Extraction failures publish no partial draft
  and preserve the approved active CV.
- **A public JD URL cannot be fetched:** paste the JD text through the supported
  confirmation flow. Do not bypass URL limits or add crawler behavior.
- **CV deletion is partial:** it remains retryable in `deleting`. Use the stable
  [coordinator](backend/app/services/cv_manager.py) error to identify
  checkpoint/SQLite access, retained-file storage, Neo4j, or final SQLite
  cleanup; restore that dependency, then retry the same deletion. The retry
  includes checkpoint cleanup and final run/tool/attachment deletion, not only
  file or graph cleanup. Never delete the active CV directly or report success
  while owned cleanup remains.
- **Job deletion cannot confirm graph removal:** the SQLite Job and evaluations
  are preserved. Restore Neo4j and retry the same delete; do not manually remove
  the SQLite row first.
- **A profile or passive-JD confirmation is interrupted:** resume the existing
  run with one allowed UI action. Never bypass confirmation with direct database
  or graph edits. CV activation and passive JD mutation occur only after the
  corresponding explicit approval.
- **Existing CV/JD skills predate the atomic Plan 16 contract:** do not edit
  SQLite JSON or Neo4j directly. Reprocess the CV in CV Manager and explicitly
  approve **Save Profile**; then use **Re-extract JD** for affected saved Jobs.
  Re-extraction preserves Job identity/raw source, advances its revision, and
  makes prior evaluations stale without recomputing them. If the selected map
  reports `NEO4J_REBUILD_REQUIRED`, run the provider-free rebuild command above,
  reload the map, and use explicit **Evaluate** only when a new score is wanted.

## Development Notes for AI Agents

- Read the task contract, the relevant plan, and current runtime owners before
  editing. Prefer executable source and manifests over historical prose when
  they disagree.
- Search for existing owners, helpers, callers, and tests before adding logic.
  Preserve one business-rule owner and avoid parallel service or state paths.
- Keep the single LangGraph Agent, one decision node, one ToolNode, exactly
  seven production tools, and `TOOL_LOOP_LIMIT=6` unless the
  [Master Plan](docs/plans/Master_plan.md) is explicitly amended.
- Preserve confirmation before CV activation and before passive pasted-JD
  mutation. Never auto-evaluate a saved JD; evaluation is explicit and keyed to
  the exact Job, CV/profile/preferences, embedding, and scoring revision.
- When a contract changes, coordinate its Pydantic/domain schema, API response,
  frontend parser and type, SSE/history projection, owning callers, and focused
  tests. Do not update only one side of a transport boundary.
- Read [`frontend/AGENTS.md`](frontend/AGENTS.md) before UI work. Discover Astryx
  components with its CLI guidance, use Astryx components and design tokens,
  and do not invent component props or a second stream store.
- Ignore generated, dependency, coverage, bytecode, and tool-cache paths,
  including `.venv/`, `node_modules/`, `dist/`, `coverage`, `__pycache__/`,
  `.pytest_cache/`, `.mypy_cache/`, and `.ruff_cache/`.
- Never stage `.agent/`, root `.env`, runtime SQLite/files, retained CV/JD data,
  provider payloads, authorization material, or secrets. Only tracked synthetic
  fixtures belong in repository evidence.
- Keep changes within the authorized file list. Preserve public interfaces and
  unrelated behavior; do not mix cleanup, dependency upgrades, or speculative
  abstractions into a focused task.
- Before completion, run relevant focused tests plus the full gates in
  proportion to risk. Inspect `git diff --check`, `git status --short`, and every
  changed path; report skipped checks and residual risk rather than claiming
  unverified success.

## Known Gaps and Limitations

- JobAgent is a local, single-user MVP with no authentication, authorization,
  roles, or public deployment hardening.
- CV input is PDF-only and requires extractable digital text; DOCX, image CVs,
  and OCR are not supported.
- Live chat, structured extraction, and embeddings depend on configured
  ShopAIKey credentials, network access, model availability, and provider
  compatibility.
- The supported Compose services publish only to loopback. The stack is not a
  production or multi-host deployment.
- [URL fetching](backend/app/services/url_fetch.py) accepts only HTTP(S) URLs with a
  network location and enforces timeout/size/content bounds, but does not
  validate public destinations or reject private/internal targets. Avoid
  untrusted internal/private URLs and keep the service loopback-only.
- Acceptance examples and committed fixtures are synthetic. They are not a
  production evaluation dataset, quality metric, or substitute for testing with
  authorized domain data outside Git.
- Neo4j is derived state. Graph reads and matching can be unavailable until the
  projection is rebuilt from authoritative SQLite and retained documents.

## Documentation Map

- [Master Plan](docs/plans/Master_plan.md) — stable product scope,
  architecture, data contracts, failure policy, and definition of done.
- [Plan 15](docs/plans/Plan_15.md) — guarded JD extraction, safe re-extraction,
  and saved-JD completeness (Batch01–Batch03 committed; Batch04 diagnostic and
  release evidence on the working tree).
- [Task 15](docs/tasks/task_15.md) — Plan 15 batch/task contracts and validation.
- [Manual JD checklist](docs/acceptance/manual_jd_checklist.md) — includes dated
  Plan 15 Batch04 same-candidate release evidence (synthetic/sanitized only).
- [Plan 14](docs/plans/Plan_14.md) — prior committed intent-aware pasted-JD
  confirmation design and verification contract.
- [Task 14](docs/tasks/task_14.md) — executable task boundaries, acceptance
  criteria, and validation ownership for Plan 14.
- [Local release checklist](docs/acceptance/local_release_checklist.md) — local
  installation, Compose, diagnostics, recovery, rebuild, and demo evidence.
- [CV Manager checklist](docs/acceptance/cv_manager_checklist.md) — synthetic CV
  lifecycle, document extraction, activation, deletion, graph, and UI checks.
- [Saved-JD evaluation checklist](docs/acceptance/saved_jd_evaluation_checklist.md)
  — synthetic saved-JD, revision-currentness, explicit evaluation, and deletion
  checks.
- [Full functional test matrix](docs/acceptance/full_functional_test_matrix.md)
  — consolidated backend, frontend, Compose, API, and browser coverage contract.
- [Plan 13 acceptance ledger](docs/acceptance/plan13_acceptance_ledger.md) —
  append-only requirement outcomes, preserved failures, reruns, and warnings.
- [README restructure design](docs/superpowers/specs/2026-07-21-readme-restructure-design.md)
  — approved audience, information architecture, evidence hierarchy, and
  validation rules for this guide.
