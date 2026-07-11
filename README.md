# JobAgent

## Project status

**Phase 0 is COMPLETE.** All required compatibility gates are evidence-backed
**PASS**. **Plan 2 is AUTHORIZED** to consume the locked decisions below without
re-benchmarking Phase 0 gates.

**Plan 2 Batch01 is COMPLETE.** The repository now has runnable local FastAPI and
React/TypeScript/Vite foundations with one typed root configuration contract.

**Plan 2 Batch02 is COMPLETE.** SQLite application metadata (02A) and a
repeatable initial Alembic migration (02B) are available under `backend/`.

**Plan 2 Batch03 is COMPLETE.** Contained filesystem attachment storage and
caller-transactional staged/active metadata operations are available under
`backend/`. MIME/content inspection, parsing, profile replacement, upload
endpoints, health checks, Agent behavior, and user workflows remain for later
plans and Plan 2 batches.

Batch01–Batch05 locked the scaffold and four compatibility gates (Astryx,
ShopAIKey chat, pypdf extraction, ShopAIKey embeddings). Batch06 pinned exact
dependency decisions, removed temporary demo/cache artifacts, completed global
safety checks, and enforced the Phase 0 exit gate (**06C**).

Evidence destination:
`backend/evaluation/reports/phase_0_feasibility.md` (final decision table at EOF).

## Repository layout

Exactly three product working folders:

- `frontend/`: runnable neutral Astryx React/TypeScript/Vite shell; no product workflows.
- `backend/`: runnable FastAPI foundation, typed settings, SQLite metadata,
  contained attachment persistence, and Phase 0 diagnostics.
- `infrastructure/`: empty Docker, Neo4j, and script placeholders only.

Root documentation and configuration files are not a fourth working folder.

## Locked dependency decisions (for Plan 2)

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
| LangGraph (Plan 2 only) | `langgraph==1.2.9` via optional extra `plan2` |
| Neo4j driver (Plan 2 only) | `neo4j==6.2.0` via optional extra `plan2` |

The backend default install now includes the Batch01 application foundation.
Optional `plan2` extras retain later-batch LangGraph and Neo4j pins; normal tests
remain fake/synthetic and do not call ShopAIKey.

Plan 2 must consume these decisions without repeating benchmarks or adding
alternate provider/UI/parser/embedding stacks. If a future re-validation fails,
revise only the affected adapter decision.

## Local prerequisites

Single-purpose tool checks:

```powershell
python --version
node --version
npm --version
docker compose version
```

## Batch01 application commands

All application configuration comes from the root `.env` contract. Populate the
required values from `.env.example`; do not create nested application `.env`
files.

### Backend

```powershell
cd backend
python -m pip install -e ".[test]"
python -m ruff check app tests
python -m mypy app
python -m pytest -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Backend SQLite migration (Batch02)

SQLite is the canonical application source of truth. The reviewed initial head
creates exactly the eleven Plan 2 application tables; LangGraph checkpoint
tables remain outside application metadata and are owned by its checkpointer.

Single-purpose command to apply the reviewed application schema to the
configured SQLite file (`SQLITE_PATH` from the root `.env` contract, or set in
the process environment). Safe to re-run against an already-initialized
persistent file; there is no automatic downgrade or destructive reset path.

```powershell
cd backend
python -m alembic -c alembic.ini upgrade head
```

Migration integration checks (temporary SQLite files only; does not read the
user-owned root `.env`):

```powershell
cd backend
python -m pytest -q tests/integration/test_migrations.py
```

### Backend attachment persistence (Batch03)

Attachment bytes are stored under the configured `FILES_DIR` in service-owned
`staged/<uuid>` and `active/<uuid>` paths; SQLite stores metadata and the
service path, not file blobs. `FilesystemAttachmentStorage` owns contained
stage, promote, open, and delete mechanics, while `AttachmentRepository`
participates in the caller's transaction for staged/active metadata changes.
Neither interface accepts user path authority or applies MIME, magic-byte,
page-count, parsing, approval, or profile-replacement policy.

Focused attachment checks (temporary files and SQLite databases only):

```powershell
cd backend
python -m pytest -q tests/services/test_attachment_storage.py tests/repositories/test_attachments.py
```

The Batch01 backend intentionally exposes only FastAPI's generated documentation
routes. `GET /api/health` is added in a later Plan 2 batch.

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

The frontend dev server binds to `http://127.0.0.1:5173`. Only
`VITE_API_BASE_URL` is published to frontend code.

## Phase 0 single-purpose commands

All validation is **local-only**. No CI is configured.

### Frontend Astryx resolution

From `frontend/` after installing the exact lockfile:

```powershell
cd frontend
npm ci --ignore-scripts
npm run check:astryx
```

### Backend focused tests (fakes/synthetic only; no network)

From `backend/`:

```powershell
cd backend
python -m pip install -e ".[test]"
python -m pytest -q
```

### Optional local PDF benchmark (private ignored corpus)

Metrics-only aggregate; never commits PDFs or document text:

```powershell
cd backend
python -m evaluation.benchmark_pdf_extraction
```

### Optional live ShopAIKey embedding benchmark (validation slice only)

Requires ignored root `.env` and private labeled records; writes aggregate
metrics only:

```powershell
cd backend
python -m evaluation.benchmark_embeddings
```

### Optional live ShopAIKey chat diagnostic

Uses ignored root `.env` only (`SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`,
`LLM_MODEL`). Exits non-zero on required capability failure; must not print
secrets:

```powershell
python backend/scripts/check_shopaikey_compatibility.py
```

## Configuration and private inputs

`.env.example` documents the root configuration contract, including
`EMBEDDING_MODEL=text-embedding-3-small` and `EMBEDDING_DIMENSIONS=1536`.
Real credentials belong only in the ignored root `.env`; nested frontend or
backend `.env` files are unsupported. Private evaluation inputs (PDF corpora
and labeled retrieval records) belong in ignored locations such as
`backend/evaluation/private/`; committed manifests and aggregate reports
contain only generic identifiers, digests, and non-identifying metrics —
never raw document text, real PDFs, or private label text.
