# JobAgent

JobAgent has completed Phase 0 feasibility validation and the first two Plan 2
foundation batches. The repository now contains a pinned backend core, the complete
SQLite/Alembic source-of-truth schema, and a minimal Astryx application shell.
Production CV, job, chat, Agent, approval, and matching workflows remain out of
scope while the rest of Plan 2 is implemented.

## Repository layout

- `frontend/` - minimal React, TypeScript, Vite, and Astryx 0.1.4 application
  shell with lint, type-check, render-test, and build commands.
- `backend/` - installable pinned Python application package with one settings
  boundary, shared UUID/UTC conventions, async SQLite sessions, nine SQLAlchemy
  tables, and the explicit Alembic initial migration.
- `infrastructure/` - local feasibility scripts and future local-service folders.
- `docs/feasibility/phase_0_report.md` - reproducible compatibility evidence.

## Configuration

Keep one user-managed `.env` at the repository root. It is ignored by Git and must
not be copied into tracked files. `.env.example` documents the supported variable
names and safe defaults; secret fields are intentionally empty, and applications
must not load `.env.example` at runtime. The frontend may consume only
`VITE_API_BASE_URL`.

## Backend foundation verification

From the repository root:

```powershell
python -m pip install -e .\backend
Set-Location backend
python -m ruff check .
python -m mypy app
python -m pytest tests/unit/test_settings.py tests/unit/test_core_conventions.py -q
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

All four Phase 0 batches passed. Plan 2 Batches 1-2 add the exact-pinned backend
foundation, cached root-environment settings, shared UUID/UTC helpers, minimal
neutral Astryx shell, async SQLite boundary, all nine application tables, exact
constraints/indexes/FKs, and idempotent Alembic singleton seeds. Storage, Neo4j,
health, and Compose remain in later Plan 2 batches. Phase 0 evidence remains
recorded in `docs/feasibility/phase_0_report.md` and is not repeated.
