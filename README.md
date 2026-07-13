# JobAgent

JobAgent has completed Phase 0 feasibility validation and Plan 2 / Master Phase 1
foundation work. The repository now contains a pinned backend core, the complete
SQLite/Alembic source-of-truth schema, UUID-rooted attachment storage, Neo4j
foundation primitives, one health API, a minimal Astryx application shell, and a
three-service local Docker Compose runtime. Production CV, job, chat, Agent,
approval, and matching workflows remain out of scope for Plan 3 and later.

## Repository layout

- `frontend/` - minimal React, TypeScript, Vite, and Astryx 0.1.4 application
  shell with lint, type-check, render-test, and build commands.
- `backend/` - installable pinned Python application package with one settings
  boundary, shared UUID/UTC conventions, async SQLite sessions, nine SQLAlchemy
  tables, the explicit Alembic initial migration, atomic attachment storage,
  Neo4j lifecycle/schema setup, and `GET /api/health`.
- `infrastructure/` - Docker Compose, backend/frontend Dockerfiles, and retained
  local feasibility scripts.
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
Neo4j without exposing connection details or adding other functional routes.
Live Neo4j/Compose integration tests skip when the stack or process credentials
are unavailable.

## Astryx verification

From `frontend/`:

```powershell
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run dev -- --host 127.0.0.1
npx astryx component AppShell
```

The exact public-component documentation commands and observed props/imports are
recorded in `docs/feasibility/phase_0_report.md`.

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

The repository includes five synthetic digital CVs and one full-page raster-only
synthetic CV under `backend/tests/fixtures/cv/`. From the repository root:

```powershell
python infrastructure/scripts/verify_pdf_extraction.py
```

The diagnostic runs pypdf normal and layout extraction, requires at least four of
five digital fixtures to contain meaningful CV text, and requires the raster-only
fixture to return `NO_EXTRACTABLE_TEXT`. OCR is intentionally unsupported.

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

## Plan 3 handoff

Plan 3 / Master Phase 2 must reuse these foundation primitives without
duplicating them:

- Settings: one cached Pydantic settings object from the root `.env` only.
- Database: async SQLAlchemy sessions, Alembic-owned schema at
  `0001_initial_schema`, PRAGMAs, and singleton seeds.
- Core helpers: lowercase UUID v4 and timezone-aware UTC helpers.
- Storage: UUID-relative paths under `FILES_DIR` with atomic write support.
- Graph: Neo4j driver lifecycle plus idempotent uniqueness constraints and the
  cosine/1536 vector index (no domain sync yet).
- API status: only `GET /api/health` with `available | unavailable` components.
- Runtime: Compose services `frontend`, `backend`, and `neo4j` on loopback ports.

Plan 3 must not call `create_all()`, alter status vocabulary, add independent
graph IDs, or introduce production CV/JD/chat/Agent public behavior without a
later plan. Schema changes require an explicit migration and Master alignment.
