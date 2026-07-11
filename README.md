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

The only public Phase 1 application endpoint is `GET /api/health` (plus framework
documentation routes). Chat, Agent, upload, public CRUD, matching, continuous
workers, Qdrant, CI, and cloud deployment remain out of scope for Plan 2.

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

## Current limitations (after Plan 3 Batch02)

- No public chat transport; the SSE contract and Agent runtime are not yet exposed by FastAPI.
- No CV/JD extraction, profile approval, matching, ranking, or evaluation UI.
- No public profile/job CRUD, authentication, continuous outbox worker, Qdrant,
  CI, or cloud deployment.
- Graph rebuild data-load stages after clear+schema are intentionally incomplete.
- Outbox repository is durable and replay-safe; no background poller ships in
  Phase 1 (claim only at explicit lifecycle points in later plans).

## Plan 3 handoff (Master Phase 2)

Plan 3 receives these **stable primitives** and must reuse them rather than
recreate them:

- Runnable frontend/backend/Neo4j Compose services and the typed root
  configuration contract (`backend/app/config.py`, root `.env` / `.env.example`).
- Async SQLite session lifecycle (`DatabaseSessionManager`) and all eleven
  application tables via the reviewed Alembic head.
- Conversation, message, agent-run, tool-execution, memory, attachment,
  candidate/job, and graph-outbox tables ready for repositories.
- Contained attachment storage (`FilesystemAttachmentStorage` +
  `AttachmentRepository`).
- Neo4j client lifecycle, idempotent `ensure_graph_schema`, and rebuild command
  skeleton.
- Transactional, replay-safe graph outbox repository (enqueue/claim/mark
  synced/failed; no continuous worker).
- Sanitized `GET /api/health` and the local lint/type-check/test/migration/Compose
  commands documented above.

Plan 3 owns chat transport and Agent runtime. It must not implement CV/JD domain
workflows before their dedicated plans, and it must not re-benchmark Phase 0
adapter decisions.
