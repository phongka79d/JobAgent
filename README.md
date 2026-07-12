# JobAgent

## Project status

**Phase 0 is COMPLETE.** All required compatibility gates are evidence-backed
**PASS**. **Plan 2 is AUTHORIZED** to consume the locked decisions below without
re-benchmarking Phase 0 gates.

**Plan 2 Phase 1 local foundation is evidence-backed** across Batches 01–05:

| Batch | Outcome |
|---|---|
| Batch01 | Runnable FastAPI + React/TypeScript/Vite scaffolds and one typed root configuration contract |
| Batch02 | SQLite application metadata and repeatable initial Alembic migration |
| Batch03 | Contained staged/active attachment filesystem persistence |
| Batch04 | Idempotent Neo4j schema primitives, durable replay-safe graph outbox, rebuild skeleton |
| Batch05 | Production-shaped Compose (frontend/backend/Neo4j), sanitized `GET /api/health`, green local quality + live exit evidence |

**Plan 3 Phase 2 chat transport / Agent runtime is evidence-backed** across
Batches 01–04 (see Phase 2 quality gates and Plan 4 handoff below). Normal
automated tests use injected fakes and never call ShopAIKey.

Re-running live three-service Compose exit checks requires a populated ignored
root `.env` (especially a non-empty `NEO4J_PASSWORD`). Do not paste secret
values into reports, commits, or chat.

Phase 0 evidence destination:
`backend/evaluation/reports/phase_0_feasibility.md` (final decision table at EOF).

## Architecture and persistence boundaries

Exactly three product working folders:

- `frontend/`: production-shaped Astryx React/TypeScript/Vite shell (static nginx
  image under Compose). Talks only to FastAPI. Only `VITE_`-prefixed public
  configuration is published to frontend assets.
- `backend/`: FastAPI foundation, typed root settings, SQLite metadata, attachment
  storage, Neo4j client/schema, graph outbox, sanitized health, and Phase 0
  diagnostics.
- `infrastructure/`: Dockerfiles, Compose definition, Neo4j placeholders, and
  the graph rebuild command skeleton.

Root documentation and configuration files are not a fourth working folder.

Persistence ownership:

| Store | Role |
|---|---|
| SQLite (`SQLITE_PATH`) | Only canonical application source of truth (eleven application tables + Alembic version) |
| Filesystem (`FILES_DIR`) | Uploaded attachment bytes under service-owned `staged/` and `active/` paths |
| Neo4j | Derived, fully rebuildable graph data only; never the sole copy of canonical state |

Public application endpoints after Plan 4 Batch02:

- `GET /api/health`
- `POST /api/attachments/cv`
- `GET /api/chat/history`
- `POST /api/chat/turns`
- `POST /api/chat/runs/{run_id}/resume`

(plus framework documentation routes). Upload, public profile/job CRUD, matching
UI, continuous workers, Qdrant, CI, and cloud deployment remain out of scope.

## Locked dependency decisions

| Area | Decision |
|---|---|
| Python | `>=3.13` (Phase 0 host: 3.13.7) |
| Frontend gate | Astryx `@astryxdesign/core` and `@astryxdesign/cli` exact `0.1.4` |
| Frontend product | React `19.2.7`, TypeScript `5.9.3`, Vite `7.3.6` (current lockfile) |
| ShopAIKey chat adapter | `langchain-openai==1.0.3`; model `gpt-4o-mini`; tools `bind_tools` + tool-result round trip; schema `strict_schema`; streaming `streaming_text` |
| Validation | `pydantic==2.12.5` |
| PDF | `pypdf==6.12.2`; digital mode `layout`; image-only exact `NO_EXTRACTABLE_TEXT` |
| Embeddings | ShopAIKey `text-embedding-3-small` / 1536 / float / no E5 prefixes |
| FastAPI | `fastapi==0.139.0` (meets master floor ≥ `0.135.0`) |
| LangGraph | `langgraph==1.2.9` (optional extra / later execution plans) |
| Neo4j driver | `neo4j==6.2.0` |
| Compose Neo4j image | `neo4j:5.26-community` |

Normal automated tests use fakes or temporary local files and never call
ShopAIKey. Optional Phase 0 live diagnostics remain separate (see below).

## Local prerequisites

```powershell
python --version
node --version
npm --version
docker compose version
```

All application configuration comes from the **single root** `.env` contract.
Copy names from `.env.example`, populate required non-placeholder values
(especially `NEO4J_PASSWORD`, `SHOPAIKEY_API_KEY`, and path/URI fields), and do
**not** create nested `frontend/.env` or `backend/.env` files.

## Required local quality commands (Phase 1)

These are the primary Plan 2 quality gates. They do not require live Docker or
provider network calls when using the documented synthetic/fake test suites.

### Backend

```powershell
cd backend
python -m pip install -e ".[test]"
python -m ruff check app tests
python -m mypy app
python -m pytest -q
```

Local non-Compose server (loads root `.env` at startup only):

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm ci --ignore-scripts
npm run check:astryx
npm run lint
npm run typecheck
npm run test -- --run
npm run build
npm run dev
```

The Vite dev server binds to `http://127.0.0.1:5173`. Only `VITE_API_BASE_URL`
is published to frontend code.

### SQLite migrations

SQLite is the canonical store. The reviewed initial head creates the eleven Plan
2 application tables. LangGraph checkpoint tables are **not** application
metadata.

Apply or re-apply head (safe against an already-initialized file; no automatic
downgrade):

```powershell
cd backend
python -m alembic -c alembic.ini upgrade head
```

Migration integration checks use temporary SQLite files only and do not read the
user-owned root `.env`:

```powershell
cd backend
python -m pytest -q tests/integration/test_migrations.py
```

### Attachment, graph, outbox, and health focused suites

```powershell
cd backend
python -m pytest -q tests/services/test_attachment_storage.py tests/repositories/test_attachments.py
python -m pytest -q tests/graph tests/repositories/test_graph_outbox.py tests/infrastructure/test_rebuild_graph.py
python -m pytest -q tests/api/test_health.py tests/test_lifecycle.py
```

### Graph rebuild skeleton

Default is dry-run (non-destructive). Destructive clear of JobAgent-derived
labels only requires `--confirm-destructive`. Later data-load stages remain
explicitly incomplete (non-zero exit) so a partial skeleton cannot be mistaken
for a full rebuild.

```powershell
python infrastructure/scripts/rebuild_graph.py --help
python infrastructure/scripts/rebuild_graph.py
```

## Docker Compose (three-service local runtime)

From the repository root. Compose loads the **single root** env file via
`--env-file` (never bake `.env` into images).

Static validation without real secrets:

```powershell
docker compose --env-file .env.example -f infrastructure/docker-compose.yml config
docker compose --env-file .env.example -f infrastructure/docker-compose.yml build
```

Live startup (requires populated root `.env`, especially non-empty
`NEO4J_PASSWORD`):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
```

Expected services: `frontend`, `backend`, `neo4j` only. Host publications:

- Backend API: `http://127.0.0.1:8000`
- Frontend static: `http://127.0.0.1:5173` (container port 8080)
- Neo4j: internal network only (no default host ports)

Named volumes (persist across ordinary restart and plain `down`):

- `jobagent_backend_data` → SQLite + `FILES_DIR` under `/data`
- `jobagent_neo4j_data` → Neo4j store

Sanitized health (overall + `sqlite` / `filesystem` / `neo4j` component states
only; no credentials, URIs, paths, or stack traces):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health | ConvertTo-Json -Depth 4
```

Apply migrations against the Compose backend volume (paths come from root env;
default example uses `/data/jobagent.db`):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec backend python -m alembic -c alembic.ini upgrade head
```

Idempotent Neo4j schema setup is performed best-effort at backend startup and
again inside the Neo4j health probe when connectivity is up. Re-running schema
must not create duplicate constraints/indexes.

Stop services **without** deleting named volumes:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml down
```

(Do not add `-v` for ordinary shutdowns if you need persistence evidence.)

## Optional Phase 0 live diagnostics

These are **not** required Plan 2 quality gates. They need ignored root secrets
and/or private corpora and must never print credentials or document text.

```powershell
cd frontend
npm ci --ignore-scripts
npm run check:astryx
```

```powershell
cd backend
python -m evaluation.benchmark_pdf_extraction
python -m evaluation.benchmark_embeddings
```

```powershell
python backend/scripts/check_shopaikey_compatibility.py
```

## Configuration and private inputs

`.env.example` documents the root configuration contract, including
`EMBEDDING_MODEL=text-embedding-3-small` and `EMBEDDING_DIMENSIONS=1536`.
Real credentials belong only in the ignored root `.env`. Nested frontend or
backend `.env` files are unsupported. Private evaluation inputs belong in
ignored locations such as `backend/evaluation/private/`. Committed manifests and
aggregate reports contain only generic identifiers, digests, and non-identifying
metrics — never raw document text, real PDFs, private labels, or secrets.

## Plan 4 progress (Batches01-02)

Batch01 establishes the validated Candidate persistence and context foundation;
it does not yet ingest or upload CV files:

- Strict Candidate Profile, Job Preferences, pending-draft, and bounded approval-summary contracts validate opaque SQLite JSON at repository boundaries.
- Deterministic skill normalization uses an approval-only packaged YAML seed; unknown skills remain provisional, with stable keys and explicit exclusion preservation.
- Singleton profile/preferences and pending-draft repositories use caller-owned transactions, while chat context reuses one compact approved projection without raw document bodies, contact fields, storage paths, or provider payloads.

Focused Batch01 verification:

```powershell
cd backend
python -m pytest -q tests/schemas/test_candidate.py tests/schemas/test_preferences.py tests/schemas/test_profile_draft.py
python -m pytest -q tests/services/test_skill_normalization.py
python -m pytest -q tests/repositories/test_profiles.py tests/repositories/test_preferences.py tests/repositories/test_profile_drafts.py tests/services/test_context_assembly.py
python -m ruff check app/repositories app/schemas app/services/profile_context.py app/services/skill_normalization.py app/services/chat_context.py tests/repositories tests/schemas tests/services/test_skill_normalization.py tests/services/test_context_assembly.py
python -m mypy app/repositories app/schemas app/services/profile_context.py app/services/skill_normalization.py app/services/chat_context.py
```

Batch02 adds the safe intake-to-pending-draft pipeline:

- `POST /api/attachments/cv` streams one PDF into contained staged storage,
  validates the configured size/page limits, and returns sanitized attachment
  metadata with deduplication.
- PDF text extraction is layout-only and fail-closed; deterministic PII
  redaction happens before the fake-backed structured extraction boundary.
- Candidate extraction uses the locked structured adapter with its single
  schema-repair ceiling, normalizes skills, and writes only a pending profile
  draft. Approved profile/preferences and attachment state remain unchanged.

## Plan 3 progress (Batch01)

Batch01 establishes the durable chat and SSE contract foundation only:

- Singleton conversation/history, Agent-run/idempotency, and sanitized tool-execution repositories now use the existing SQLite transaction boundary.
- The additive Plan 3 Alembic head adds durable turn/resume idempotency fields without application-owned LangGraph checkpoint tables.
- Backend owns an exact validated eight-event SSE union and producer-side ordering boundary; no public chat route exists yet.

Focused Batch01 verification:

```powershell
cd backend
python -m pytest -q tests/repositories/test_conversations.py tests/repositories/test_agent_runs.py tests/repositories/test_tool_executions.py tests/integration/test_migrations.py tests/schemas/test_sse.py
python -m ruff check app/db app/repositories app/schemas tests/repositories tests/schemas tests/integration/test_migrations.py
python -m mypy app/db app/repositories app/schemas
```

## Plan 3 progress (Batch02)

Batch02 adds the controlled runtime behind the existing contract:

- The typed ShopAIKey adapter uses the locked model/modes, fake-backed tests, and bounded repair/retry failures.
- One LangGraph `StateGraph` and one `ToolNode` use an empty-by-default production tool registry, a six-iteration guard, and a production approval interrupt/resume seam.
- Per-run `AsyncSqliteSaver` checkpoints retain interrupted work, resume on the same durable thread, and are deleted only after final assistant persistence.

Focused Batch02 verification:

```powershell
cd backend
python -m pytest -q tests/services/test_shopaikey_chat.py tests/agent/test_state.py tests/agent/test_prompt.py tests/services/test_context_assembly.py tests/agent/test_graph.py tests/tools/test_registry.py tests/integration/test_agent_lifecycle.py
python -m ruff check app/agent app/tools app/services/shopaikey_chat.py app/services/chat_context.py app/services/chat_service.py tests/agent tests/tools tests/services/test_shopaikey_chat.py tests/services/test_context_assembly.py tests/integration/test_agent_lifecycle.py
python -m mypy app/agent app/tools app/services/shopaikey_chat.py app/services/chat_context.py app/services/chat_service.py
```

## Plan 3 progress (Batch03)

Batch03 exposes the durable runtime through the public chat surface and a base
Astryx chat UI:

- Public FastAPI routes are limited to `GET /api/chat/history`, `POST /api/chat/turns`, and `POST /api/chat/runs/{run_id}/resume`; POST routes stream the validated SSE union.
- The frontend uses the existing `VITE_API_BASE_URL` boundary, an incremental SSE parser, a pure run/event reducer, history hydration, duplicate filtering, and disconnect/approval states.
- The first screen is an Astryx chat experience with hydrated messages, partial assistant text, sanitized tool activity, approval/correction resume controls, and no profile/job/upload UI.

Focused Batch03 verification:

```powershell
cd backend
python -m pytest -q tests/api/test_chat.py tests/integration/test_chat_transport.py tests/test_lifecycle.py
python -m ruff check app/api/chat.py app/schemas/chat.py app/main.py tests/api/test_chat.py tests/integration/test_chat_transport.py
python -m mypy app/api/chat.py app/schemas/chat.py app/main.py

cd frontend
npm run check:astryx
npm run test -- --run src/features/chat/reducer.test.ts src/lib/sse/parser.test.ts src/features/chat/api.test.ts src/features/chat/components src/test/app.chat.test.tsx
npm run lint
npm run typecheck
npm run build
```

## Plan 3 progress (Batch04) — Phase 2 transport proof

Batch04 proves the complete local frontend-to-Agent transport with injected
fakes only, confirms production has no synthetic tool, and records the stable
Plan 4 handoff. Public tool outcomes are fail-closed to short allowlisted status
tokens only; raw tool arguments/results never enter durable
`arguments_summary` or SSE.

- Full-path backend fixture: real FastAPI routes → `ChatService` → production
  LangGraph + `ToolNode` → validated SSE → durable history/run/tool rows and
  completed-checkpoint cleanup (`backend/tests/integration/test_full_chat_transport.py`).
  Proofs include unique raw-argument sentinel absence across parsed SSE, raw
  wire, history, durable tool rows, and captured logs; instrumented approval
  tool action and durable tool-row counts stay exactly one after duplicate
  turn/resume keys.
- Full-path frontend fixture: raw SSE frames through real
  `streamChatTurn` / `streamChatResume` (parser) into the pure reducer and
  ChatShell for ordinary completion, tool activity, approval/resume,
  duplicates, failure, and disconnect
  (`frontend/src/test/chat-transport.integration.test.tsx`).
- Synthetic `echo_label` / approval helpers exist only under `backend/tests/`;
  production registry remains empty by default.
- Public application routes remain exactly:
  `GET /api/health`, `GET /api/chat/history`, `POST /api/chat/turns`,
  `POST /api/chat/runs/{run_id}/resume`.

### Phase 2 quality gates (evidence-backed commands)

Backend (no ShopAIKey network calls):

```powershell
cd backend
python -m ruff check app tests
python -m mypy app
python -m pytest -q
python -m pytest -q tests/integration/test_full_chat_transport.py
```

Frontend:

```powershell
cd frontend
npm ci --ignore-scripts
npm run check:astryx
npm run lint
npm run typecheck
npm run test -- --run
npm run test -- --run src/test/chat-transport.integration.test.tsx
npm run build
```

Compose static (uses `.env.example`; no live secrets required):

```powershell
docker compose --env-file .env.example -f infrastructure/docker-compose.yml config
docker compose --env-file .env.example -f infrastructure/docker-compose.yml build
```

Production exposure / route inventory scans (expected: no production
`echo_label` tool; domain names may appear only as reserved later-phase
constants in `backend/app/tools/registry.py`; routes only health + chat):

```powershell
rg -n "synthetic|echo_label|propose_profile_from_cv|commit_profile_draft|save_job|match_jobs" backend/app frontend/src
rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api
git diff --check
```

Optional live observation (user-owned root `.env` only; not required for
acceptance):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
# Then one ordinary chat turn through the UI against the production adapter.
```

## Current limitations (after Plan 4 Batch02)

- Phase 2 chat transport, Agent runtime, SSE, and base chat shell are complete
  for local fake-backed proof. Plan 4 now also has safe CV staging, layout text
  extraction, deterministic PII redaction, and pending-draft extraction.
- No profile approval transport/UI, Candidate graph sync, JD ingestion,
  matching, ranking, or evaluation UI yet.
- No public profile/job CRUD, authentication, continuous outbox worker, Qdrant,
  CI, or cloud deployment.
- Production tool registry is empty; the seven Master §13 domain tools are
  reserved names only — Plan 4 registers real tools through the existing seam.
- Graph rebuild data-load stages after clear+schema remain intentionally
  incomplete.
- Outbox repository is durable and replay-safe; no background poller ships yet.

## Plan 4 handoff (Master Phase 3) — stable seams only

Plan 4 receives these **stable Phase 2 primitives** and must extend them rather
than recreate alternate graphs, conversations, SSE contracts, or tool HTTP
paths:

| Seam | Location / contract |
|---|---|
| Public chat endpoints | `GET /api/chat/history`, `POST /api/chat/turns`, `POST /api/chat/runs/{run_id}/resume` (`backend/app/api/chat.py`) |
| SSE event union | Eight-event validated union + order rules (`backend/app/schemas/sse.py`); frontend mirror (`frontend/src/features/chat/contracts.ts`) |
| Frontend transport / reducer / shell | `frontend/src/features/chat/{api,reducer,components}/` + `lib/sse/parser.ts` |
| One controlled LangGraph | `backend/app/agent/graph.py` — decision → `ToolNode` → iteration guard → approval interrupt → persist → checkpoint cleanup |
| Approval / idempotency | Same run/thread resume; turn + resume idempotency keys; no write replay (`ChatService`, `AgentRunRepository`) |
| Repositories | Conversation/messages, agent runs, tool executions (`backend/app/repositories/`) |
| Context assembly | Bounded recent window + attachment IDs only (`backend/app/services/chat_context.py`) |
| Prompt / domain redirect | System policy + untrusted document delimiters + zero-tool redirect (`backend/app/agent/prompt.py`) |
| Tool registration | Empty production registry; inject tools at graph build (`backend/app/tools/registry.py`) |
| ShopAIKey adapter | Locked model/modes (`backend/app/services/shopaikey_chat.py`); normal tests use fakes |
| Compose / config | Root `.env` contract, three-service Compose, sanitized `GET /api/health` |

Plan 4 must add CV/profile tools and approval payloads **through these seams**.
It must **not** create a second graph, second conversation path, alternate SSE
contract, direct frontend→store/provider access, or HTTP calls from tools back
into FastAPI.

## Prior phase handoff consumed by Plan 3

Plan 3 reused (and did not re-benchmark) Plan 2 / Phase 0 primitives:

- Runnable frontend/backend/Neo4j Compose services and the typed root
  configuration contract (`backend/app/config.py`, root `.env` / `.env.example`).
- Async SQLite session lifecycle (`DatabaseSessionManager`) and application
  tables via Alembic (including Plan 3 run-idempotency revision).
- Contained attachment storage, Neo4j client/schema, graph outbox skeleton.
- Sanitized `GET /api/health` and the local quality/Compose commands above.
