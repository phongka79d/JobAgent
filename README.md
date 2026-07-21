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

The current accepted product baseline is **Plan 14 complete** at commit
`c8aa1da` (`P14B2: Complete`). Detailed scope, execution, and acceptance
evidence remains in:

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
6. Browse paginated CV history and chunk lists, open retained CVs and chunk
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
   returns immediately without extraction, embedding, or graph sync; an existing
   failed Job retries in place; otherwise a new Job row is created and processed.
5. Retry/new processing performs structured extraction and ShopAIKey embedding
   outside transactions, then persists one terminal result. Only a newly
   processed scorable Job attempts post-commit Neo4j synchronization. Saving
   alone does **not** automatically evaluate the Job.

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
  explicit evaluation/re-evaluation, deterministic match cards, and deletion UI.
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
  observability, and deletion orchestration.
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
save-and-evaluate, evaluate, and delete routes.

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

## Setup

## Running the Project

## Testing and Validation

## Failure and Recovery

## Development Notes for AI Agents

## Known Gaps and Limitations

## Documentation Map
