# JobAgent

## Phase 0 status

**Phase 0 is COMPLETE.** All required compatibility gates are evidence-backed
**PASS**. **Plan 2 is AUTHORIZED** to consume the locked decisions below without
re-benchmarking Phase 0 gates.

This repository still contains only the Phase 0 compatibility scaffold until
Plan 2 implements product services. Product services, data stores, Agent
behavior, and user interface flows have not been implemented yet.

Batch01–Batch05 locked the scaffold and four compatibility gates (Astryx,
ShopAIKey chat, pypdf extraction, ShopAIKey embeddings). Batch06 pinned exact
dependency decisions, removed temporary demo/cache artifacts, completed global
safety checks, and enforced the Phase 0 exit gate (**06C**).

Evidence destination:
`backend/evaluation/reports/phase_0_feasibility.md` (final decision table at EOF).

## Repository layout

Exactly three product working folders:

- `frontend/`: Astryx pin and public-component check only; no product UI.
- `backend/`: Python evaluation/diagnostic scaffold; no production service.
- `infrastructure/`: empty Docker, Neo4j, and script placeholders only.

Root documentation and configuration files are not a fourth working folder.

## Locked dependency decisions (for Plan 2)

| Area | Decision |
|---|---|
| Python | `>=3.13` (Phase 0 host: 3.13.7) |
| Frontend gate | Astryx `@astryxdesign/core` and `@astryxdesign/cli` exact `0.1.4` |
| Frontend product (Plan 2) | React + TypeScript + Vite (install versions when Plan 2 scaffolds the app) |
| ShopAIKey chat adapter | `langchain-openai==1.0.3`; model `gpt-4o-mini`; tools `bind_tools` + tool-result round trip; schema `strict_schema`; streaming `streaming_text` |
| Validation | `pydantic==2.12.5` |
| PDF | `pypdf==6.12.2`; digital mode `layout`; image-only exact `NO_EXTRACTABLE_TEXT` |
| Embeddings | ShopAIKey `text-embedding-3-small` / 1536 / float / no E5 prefixes |
| FastAPI (Plan 2 only) | `fastapi==0.139.0` (meets master floor ≥ `0.135.0`) via optional extra `plan2` |
| LangGraph (Plan 2 only) | `langgraph==1.2.9` via optional extra `plan2` |
| Neo4j driver (Plan 2 only) | `neo4j==6.2.0` via optional extra `plan2` |

Phase 0 installs gate packages only. Optional `plan2` extras record production
pins and are not required to run Phase 0 diagnostics.

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

## Phase 0 single-purpose commands

All validation is **local-only**. No CI is configured. Production application
run/build/start commands are **not yet available** (Plan 2 responsibility).

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
