# JobAgent

JobAgent has completed Phase 0 feasibility validation, Plan 2 / Master Phase 1
foundation work, Plan 3 / Master Phase 2 (persistent conversation over the
React–FastAPI–LangGraph–SSE path), Plan 4 / Master Phase 3 Batch01 (profile
domain and extraction foundations), Plan 4 Batch02 (staged CV upload and
profile proposal pipeline), and Plan 4 Batch03 (approved profile truth, Candidate
sync, production profile tools, and profile/CV reads). The repository contains a
pinned backend core (including Phase 2 LangGraph/LangChain pins), the complete
SQLite/Alembic source-of-truth schema, validated chat/ToolResult/SSE contracts,
message/run/tool repositories, tool replay and history-hydration services,
bounded Agent state/context with compact approved candidate memory, a verified
ShopAIKey ChatOpenAI adapter and conversation-first prompt, one injected-registry
decision/ToolNode graph with a six-pass loop guard, request-scoped
`AsyncSqliteSaver` checkpoints and Agent runner streaming, atomic
chat-turn/interrupt/resume services, thin public history/turn/resume SSE
endpoints, a typed React/Astryx conversation client (SSE parser, single streaming
reducer, history/load-older, concise tool activity, failure states), UUID-rooted
attachment storage with bounded multipart CV staging, Neo4j foundation
primitives plus idempotent Candidate/Skill graph sync, exact Candidate Profile /
skill / preference / draft Pydantic contracts, the sole skill taxonomy loader and
normalizer, focused attachment and profile repositories over the existing schema,
a single production pypdf extraction and meaningful-text owner, structured CV
extraction/draft proposal and interrupt-guarded commit tools (three production
profile tools registered), constraint-safe SQLite-first approval, thin profile
and active-CV read APIs, one health API, and a three-service local Docker Compose
runtime. Job/matching tools and profile UI remain later Plan 4 batches and later
plans.

## Repository layout

- `frontend/` - React, TypeScript, Vite, and Astryx 0.1.4 application with the
  Plan 3 conversation client (chat page, SSE/API client, reducer, UI tests),
  lint, type-check, test, and build commands.
- `backend/` - installable pinned Python application package with one settings
  boundary, shared UUID/UTC conventions, async SQLite sessions, nine SQLAlchemy
  tables, the explicit Alembic initial migration, atomic attachment storage
  (including stream-to-temp then UUID promote), Neo4j lifecycle/schema setup and
  Candidate/Skill sync under `app/graph/`, `GET /api/health`, Phase 2
  chat/tool/SSE Pydantic contracts, Plan 4 profile/skill/draft and attachment
  response contracts under `app/schemas/`, focused chat/run/tool and
  attachment/profile repositories, history/tool services, skill normalizer,
  pypdf extraction, CV upload, profile extraction, draft proposal, and SQLite-
  first profile approval owners under `app/services/`, Agent state/context
  loader (compact approved candidate memory), ShopAIKey chat adapter/prompt,
  production registry of exactly three profile tools under `app/tools/`, one
  StateGraph factory, request-scoped checkpoint/runner lifecycle, chat-turn/
  resume orchestration with interrupt-guarded commit, thin public chat history/
  turn/resume routes, `POST /api/attachments/cv`, and `GET /api/profile` plus
  `GET /api/profile/cv`.
- `infrastructure/` - Docker Compose, backend/frontend Dockerfiles, retained
  local feasibility scripts, and the approved Neo4j skills taxonomy seed
  (`neo4j/skills_seed.yaml`).
- `docs/feasibility/phase_0_report.md` - reproducible compatibility evidence.

## Configuration

Keep one user-managed `.env` at the repository root. It is ignored by Git and must
not be copied into tracked files. `.env.example` documents the supported variable
names and safe defaults; secret fields are intentionally empty, and applications
must not load `.env.example` at runtime. The frontend may consume only
`VITE_API_BASE_URL`. Nested `frontend/.env` and `backend/.env` files are not used.

## Backend foundation verification

From the repository root:

```powershell
python -m pip install -e .\backend
Set-Location backend
python -m ruff check .
python -m mypy app
python -m pytest tests/unit -q
python -m pytest tests/integration -q
```

## SQLite and migration verification

From `backend/`:

```powershell
python -m pytest tests/integration/test_database_pragmas.py -q
python -m pytest tests/integration/test_database_contract.py tests/integration/test_migrations.py -q
alembic upgrade head
alembic current
alembic upgrade head
```

Alembic owns exactly the nine application tables and seeds only
`conversation('main')` and `job_preferences('active')`. Runtime code never calls
`Base.metadata.create_all()`, and checkpoint-like tables remain outside Alembic
ownership.

## Storage, graph, and health verification

From `backend/`:

```powershell
python -m pytest tests/unit/test_storage.py tests/unit/test_graph_setup.py -q
python -m pytest tests/integration/test_health.py -q
python -m pytest tests/integration/test_neo4j_setup.py tests/integration/test_compose_runtime.py -q
python -m ruff check app/storage app/graph app/api app/schemas/health.py app/main.py
python -m mypy app
```

Attachment paths are UUID-derived and confined beneath `FILES_DIR`; complete
writes become visible through atomic replacement. Neo4j setup owns only three
idempotent uniqueness constraints and one 1536-dimensional cosine vector index.
`GET /api/health` reports `available | unavailable` for SQLite, filesystem, and
Neo4j without exposing connection details. Public functional routes are exactly
the seven Master endpoints: health, Plan 4 `POST /api/attachments/cv`,
`GET /api/profile`, `GET /api/profile/cv`, and Plan 3 chat history/turn/resume.
Live Neo4j/Compose integration tests skip when the stack or process credentials
are unavailable.

## Astryx and conversation client verification

From `frontend/`:

```powershell
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run dev -- --host 127.0.0.1
npx astryx component AppShell
npx astryx component ChatLayout
npx astryx component ChatMessage
npx astryx component ChatComposer
npx astryx component ChatToolCalls
```

The frontend talks only to FastAPI via `VITE_API_BASE_URL`, keeps streaming state
in one reducer with `event_id` deduplication, hydrates durable history as truth,
and uses pinned public Astryx chat APIs. Application run/tool statuses remain
`running|interrupted|completed|failed` and `pending|running|completed|failed`
(no `complete`/`error` aliases in client state). Phase 0 public-component matrix
evidence remains in `docs/feasibility/phase_0_report.md`.

## Local Docker Compose

From the repository root, with a filled-in ignored root `.env` (including a real
`NEO4J_PASSWORD`):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

The isolated test project used for Phase 1 exit evidence is
`jobagent-plan2-test`:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test up --build -d
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test exec backend alembic current
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test exec backend alembic upgrade head
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test up -d --force-recreate
```

Compose runs exactly `frontend`, `backend`, and `neo4j`. Host ports are published
only on `127.0.0.1` (`5173`, `8000`, `7474`, `7687`). SQLite and files share the
application volume; Neo4j data and logs use separate volumes. Do not mount the
source tree or root `.env` into containers.

## PDF extraction verification

Production pypdf digital-text extraction, layout mode, page-count parsing, and
the meaningful-text rule live only in `backend/app/services/pdf_extraction.py`.
The Phase 0 diagnostic reuses that owner (no local threshold/marker copy). The
repository includes five synthetic digital CVs and one full-page raster-only
synthetic CV under `backend/tests/fixtures/cv/`. From the repository root:

```powershell
python infrastructure/scripts/verify_pdf_extraction.py
```

From `backend/` after editable install:

```powershell
python -m pytest tests/unit/test_pdf_extraction.py -q
```

The diagnostic runs pypdf normal and layout extraction via the production owner,
requires at least four of five digital fixtures to contain meaningful CV text,
and requires the raster-only fixture to return `NO_EXTRACTABLE_TEXT`. OCR is
intentionally unsupported.

## ShopAIKey verification

Place a valid `SHOPAIKEY_API_KEY` only in the ignored root `.env`, keep the locked
model and dimension values from `.env.example`, and run from the repository root:

```powershell
python infrastructure/scripts/diagnose_shopaikey.py
```

This command calls the real provider. It checks model discovery, chat, function
calling, the tool-result round trip, structured schema output, ordered terminal
streaming, and scalar/batch 1536-dimensional embeddings. Output is sanitized and
must end with `SHOPAIKEY_COMPATIBILITY=PASS` before later phases use the contract.

## Phase status

All four Phase 0 batches passed. Plan 2 / Master Phase 1 is complete: exact-pinned
backend foundation, cached root-environment settings, shared UUID/UTC helpers,
minimal neutral Astryx shell, async SQLite boundary, all nine application tables,
exact constraints/indexes/FKs, idempotent Alembic singleton seeds, atomic
attachment storage, Neo4j lifecycle/base schema, three-component health boundary,
and the loopback-bound three-service Compose runtime. Phase 0 evidence remains
recorded in `docs/feasibility/phase_0_report.md` and is not repeated.

Plan 3 / Master Phase 2 Batch01 is complete: exact Phase 2 runtime pins
(`langgraph`, `langchain`, `langchain-core`, `langchain-openai`,
`langgraph-checkpoint-sqlite`), validated chat/history/resume, `ToolResult`, and
seven-event SSE contracts; message and agent-run repositories; durable tool
transitions with exact `(run_id, tool_call_id)` replay; opaque cursor history
pagination and durable tool hydration.

Plan 3 Batch02 is complete: exact nine-field `AgentState` and prompt-budget
bounded recent-context loading; verified ShopAIKey `ChatOpenAI` adapter from
root settings (custom base URL, `gpt-4o-mini`, temperature zero, Phase 0 tool
mode) with conversation-first prompt; one injected-registry `StateGraph` with a
single decision node and one `ToolNode`, six-pass tool-loop guard, and empty
production registry (tests inject fakes only).

Plan 3 Batch03 is complete: request-scoped `AsyncSqliteSaver` on the application
SQLite file with `run_id` as `thread_id`; runner streaming of validated SSE
events and terminal per-run checkpoint cleanup; atomic chat-turn create and
terminal success/failure/interrupt services; generic interrupt/resume with
test-only synthetic tool; thin FastAPI routes `GET /api/chat/history`,
`POST /api/chat/turns`, and `POST /api/chat/runs/{run_id}/resume` with CORS
restricted to `FRONTEND_ORIGIN` for `GET`/`POST`.

Plan 3 Batch04 is complete: typed client SSE/history contracts and single
streaming reducer (`frontend/src/features/chat/`, `frontend/src/lib/api/`,
`frontend/src/lib/sse/`); base Astryx chat page under `AppShell` with history
pagination, ordered streamed text, in-flight composer lock, concise tool
activity (exact JobAgent status text), and visible failed/disconnected/interrupted
states. Plan 3 / Master Phase 2 is complete.

Plan 4 / Master Phase 3 Batch01 is complete: exact `SkillRef`, `CandidateSkill`,
experience/education/language, `CandidateProfile`, `JobPreferences`, and
`ProfileDraftPayload` contracts under `app/schemas/`; user-approved production
taxonomy at `infrastructure/neo4j/skills_seed.yaml` with one deterministic
normalizer under `app/services/skill_normalization.py`; focused attachment and
singleton profile/draft/preferences repositories (no schema migration); and one
production pypdf extraction/meaningful-text owner under
`app/services/pdf_extraction.py` shared with the Phase 0 diagnostic.

Plan 4 Batch02 is complete: bounded multipart `POST /api/attachments/cv` with
interrupt guard, MIME/`%PDF-`/size/page validation, exact-hash active/staged/
failed-retry/new lifecycle, and stream-to-temp then UUID promote storage;
structured CV extraction via locked ShopAIKey `with_structured_output` (fake-
testable, at most one schema repair and one timeout/rate retry) under
`app/services/profile_extraction.py`; singleton draft proposal orchestration
under `app/services/profile_drafts.py` (`propose_profile_from_cv` and correction-
preserving `propose_profile_update`); compact tool factories under
`app/tools/profile.py`; and `python-multipart==0.0.30` as a direct backend pin.

Plan 4 Batch03 is complete: constraint-safe SQLite-first approval under
`app/services/profile_approval.py` with post-commit best-effort old-PDF cleanup
and parameterized Candidate/Skill/seed sync under `app/graph/sync_candidate.py`;
interrupt-guarded `commit_profile_draft` over the existing replay/resume path
with production registration of exactly three profile tools; compact approved
`candidate_context` loaded into new chat turns; and thin
`GET /api/profile` / `GET /api/profile/cv` reads (no profile write CRUD). Later
Plan 4 batches own profile UI and job/matching tools.

## Plan 3 progress and constraints

Plan 3 reuses Plan 2 foundation primitives without duplicating them:

- Settings: one cached Pydantic settings object from the root `.env` only.
- Database: async SQLAlchemy sessions, Alembic-owned schema at
  `0001_initial_schema`, PRAGMAs, and singleton seeds.
- Core helpers: lowercase UUID v4 and timezone-aware UTC helpers.
- Storage: UUID-relative paths under `FILES_DIR` with atomic write support.
- Graph: Neo4j driver lifecycle plus idempotent uniqueness constraints and the
  cosine/1536 vector index (no domain sync yet).
- API status: `GET /api/health` plus Plan 3 chat history/turn/resume; no other
  public functional routes. CORS allows only configured `FRONTEND_ORIGIN` for
  `GET` and `POST`.
- Runtime: Compose services `frontend`, `backend`, and `neo4j` on loopback ports.
- Chat persistence (Batch01): contracts under `app/schemas/`, repositories under
  `app/repositories/`, and history/tool services under `app/services/` on the
  existing conversation/run/tool tables (no schema migration).
- Agent runtime (Batch02): state/context under `app/agent/`, ShopAIKey factory
  under `app/adapters/shopaikey_chat.py`, empty `production_registry()` under
  `app/tools/`, and graph factory under `app/agent/graph.py`. Graph nodes do not
  open DB sessions, call FastAPI, or construct the provider outside the adapter.
  Normal tests use fakes only; optional live ShopAIKey smoke remains separate.
- Turn/resume transport (Batch03): checkpoint lifecycle under
  `app/agent/checkpoint.py`, runner under `app/agent/runner.py`, chat-turn
  orchestration under `app/services/chat_turns.py`, and thin routes under
  `app/api/chat.py` with dependency injection in `app/api/dependencies.py`.
  Package-owned checkpoint tables are never managed by Alembic or application
  repositories. Synthetic interrupt tools live only under `backend/tests/fakes/`.
- Conversation client (Batch04): types/history/reducer under
  `frontend/src/features/chat/`, API client under `frontend/src/lib/api/chat.ts`,
  SSE parser/stream under `frontend/src/lib/sse/`, and `ChatPage` composition
  wired into `frontend/src/app/App.tsx` via public Astryx Chat* components only.
  No second client state store, approval cards, or domain-tool UI in Plan 3.

Plan 3 must not call `create_all()`, alter status vocabulary, add independent
graph IDs, or introduce production CV/JD/matching tools without a later plan.
Schema changes require an explicit migration and Master alignment.

## Plan 4 Batch01 progress and constraints

Plan 4 Batch01 reuses Plan 2/3 primitives without duplicating them:

- Profile contracts: `app/schemas/skills.py` and `app/schemas/profile.py` own
  exact field sets, enums, confidence `[0, 1]`, and strict `extra="forbid"`.
  Later services must validate these models before any `profile_json`,
  `draft_json`, or `preferences_json` write.
- Skill taxonomy: production seed is only
  `infrastructure/neo4j/skills_seed.yaml`; tests may inject the smaller fixture
  through the same parser. One normalizer owns Unicode/whitespace/case/
  punctuation/alias resolution and unknown `canonical_key` derivation; the LLM
  never supplies aliases or relationships.
- Repositories: `app/repositories/attachments.py` and
  `app/repositories/profiles.py` are flush-only, session-caller-owned, and do
  not commit, touch filesystem/providers/Neo4j, or re-validate JSON shape.
- PDF extraction: sole quality rule and pypdf `PdfReader` usage live in
  `app/services/pdf_extraction.py`; raw extracted text remains transient
  service data (not a public API contract).
- Batch01 public surface was health plus Plan 3 chat history/turn/resume only
  (Batch02 adds CV upload; proposal tools stay unregistered).

## Plan 4 Batch02 progress and constraints

Plan 4 Batch02 reuses Batch01 contracts, repositories, PDF quality rule, and
Plan 3 interrupt/chat primitives without duplicating them:

- Upload: `app/services/cv_upload.py` and thin `app/api/attachments.py` own
  `POST /api/attachments/cv`. Guard interrupted approval before reading upload
  bytes; stream+hash into storage temp; enforce MIME, `%PDF-` magic, size, and
  page bounds before any final UUID file/row; exact-hash branches reuse or
  create staged state without deleting a different staged CV during upload.
- Extraction/proposal: `app/services/profile_extraction.py` and
  `app/services/profile_drafts.py` produce one validated
  `profile_drafts('current')` only; raw CV text is transient; failed extraction
  marks the same attachment `failed` and retains its file for retry.
- Tools: `propose_profile_from_cv` and `propose_profile_update` factories live
  under `app/tools/profile.py` and were registered in Batch03.
- Out of scope for Batch02: approval/commit, Neo4j Candidate sync, profile read
  routes, production tool registration, and frontend upload/approval UI.

## Plan 4 Batch03 progress and constraints

Plan 4 Batch03 reuses Batch02 upload/proposal primitives and Plan 3
interrupt/replay/chat transport without duplicating them:

- Approval: `app/services/profile_approval.py` validates draft/attachment/file
  outside the write unit, then commits one short SQLite transaction (active
  profile, preferences when changed, replacement ordering, draft delete, one-
  active invariant). Cleanup and Neo4j sync run only after commit; sync failure
  returns `NEO4J_SYNC_FAILED` with `sqlite_committed=true` and never rolls SQLite
  back.
- Graph sync: `app/graph/sync_candidate.py` MERGE Candidate `id='active'`, rebuilds
  this Candidate's `HAS_SKILL` for non-excluded skills only, loads approved seed
  `RELATED_TO`, and never receives raw CV text.
- Commit tool: `commit_profile_draft` interrupts before side effects; resume
  continues the same `(run_id, tool_call_id)` with `save_profile|request_changes`.
  Production registry is exactly the three profile tools (no `match_jobs`).
- Reads/memory: short-session load of compact approved profile/preferences into
  existing `candidate_context`; `app/api/profile.py` exposes metadata and active
  PDF stream only. Public surface is exactly the seven Master endpoints.
- Out of scope for Batch03: frontend upload/approval UI, profile write CRUD,
  JD/Job graph behavior, embeddings, rebuild completion, and matching tools.

## Profile domain and extraction foundations verification (Plan 4 Batch01)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_profile_schemas.py tests/unit/test_skill_normalization.py tests/unit/test_pdf_extraction.py -q
python -m pytest tests/integration/test_cv_api.py tests/integration/test_profile_approval.py -q
python -m ruff check app/schemas/profile.py app/schemas/skills.py app/services/skill_normalization.py app/services/pdf_extraction.py app/repositories/attachments.py app/repositories/profiles.py
python -m mypy app
```

Also reconfirm the retained Phase 0 diagnostic from the repository root:

```powershell
python infrastructure/scripts/verify_pdf_extraction.py
```

## Staged CV upload and profile proposal verification (Plan 4 Batch02)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/integration/test_cv_api.py tests/unit/test_storage.py tests/unit/test_pdf_extraction.py -q
python -m pytest tests/unit/test_profile_extraction.py tests/unit/test_profile_schemas.py tests/unit/test_skill_normalization.py tests/integration/test_profile_approval.py -q
python -m ruff check app/api/attachments.py app/schemas/attachments.py app/services/cv_upload.py app/services/profile_extraction.py app/services/profile_drafts.py app/tools/profile.py app/storage/attachments.py app/repositories/attachments.py
python -m mypy app
```

These upload and proposal tests use the temporary migrated SQLite harness and
fake structured-profile invokers. They do not require a live ShopAIKey call for
Batch02 acceptance.

## Approved profile truth, sync, and read verification (Plan 4 Batch03)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/integration/test_profile_approval.py tests/integration/test_candidate_sync.py -q
python -m pytest tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py tests/integration/test_agent_runner.py tests/integration/test_chat_api.py -q
python -m pytest tests/unit/test_agent_context.py tests/integration/test_cv_api.py -q
python -m ruff check app/services/profile_approval.py app/graph/sync_candidate.py app/tools/profile.py app/tools/registry.py app/services/tool_execution.py app/services/chat_turns.py app/agent/context.py app/agent/graph.py app/agent/runner.py app/api/profile.py app/main.py
python -m mypy app
```

These tests use temporary migrated SQLite, fakes, and injected Neo4j drivers.
Live Neo4j is optional and does not block Batch03 acceptance. Public surface is
exactly health, CV upload, profile/profile-CV reads, and the three Plan 3 chat
endpoints; production registry contains exactly three profile tools.

## Durable chat contract verification (Batch01)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_tool_result.py tests/unit/test_sse_contract.py -q
python -m pytest tests/integration/test_chat_persistence.py tests/integration/test_tool_replay.py tests/integration/test_chat_history.py -q
python -m ruff check app/schemas app/repositories app/services
python -m mypy app
```

## Controlled Agent runtime verification (Batch02)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_agent_context.py tests/unit/test_shopaikey_chat.py tests/unit/test_agent_graph.py -q
python -m ruff check app/agent app/adapters/shopaikey_chat.py app/tools tests/fakes/fake_chat_model.py tests/unit/test_agent_context.py tests/unit/test_shopaikey_chat.py tests/unit/test_agent_graph.py
python -m mypy app
```

These unit tests use fakes and make no outbound ShopAIKey network calls. Optional
live reconfirmation remains `python infrastructure/scripts/diagnose_shopaikey.py`
from the repository root with a user-managed ignored root `.env`.

## Durable turn, resume, and SSE transport verification (Batch03)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/integration/test_agent_runner.py -q
python -m pytest tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q
python -m pytest tests/integration/test_chat_api.py tests/integration/test_chat_history.py -q
python -m ruff check app/agent/checkpoint.py app/agent/runner.py app/services/chat_turns.py app/api/chat.py app/api/dependencies.py app/main.py tests/fakes/synthetic_tool.py tests/integration/test_agent_runner.py tests/integration/test_interrupt_resume.py tests/integration/test_chat_api.py
python -m mypy app
```

These integration tests use fakes and a temporary migrated SQLite file. They do
not call the real ShopAIKey API. Public surface is health plus the three Plan 3
chat endpoints; production tool registration remains empty.

## React and Astryx conversation client verification (Batch04)

From `frontend/`:

```powershell
npm test -- --run src/test/sse-reducer.test.ts src/test/chat-page.test.tsx
npm run lint
npm run typecheck
npm run build
```

From `backend/` (fake-backed public API/Agent path; no provider call):

```powershell
python -m pytest tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q
```

Optional local UI smoke (user-managed ignored root `.env`, valid ShopAIKey,
Docker, free loopback ports):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
```

Then open the frontend and send a greeting; a natural persisted answer should
stream with no tool activity. Synthetic interrupt behavior remains test-only.
