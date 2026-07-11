# JobAgent

## Phase 0 status

This repository currently contains only the Phase 0 compatibility scaffold.
Product services, data stores, Agent behavior, and user interface flows have
not been implemented.

Batch01 established the readiness baseline. Batch02 locked Astryx core and CLI
at `0.1.4` and verified all 16 required public components. Batch03 locked the
ShopAIKey compatibility gate: chat model `gpt-4o-mini`, tool mode
`bind_tools` with tool-result round trip, structured output `strict_schema`
(max one repair per attempt), and streaming characterized as supported
(`streaming_text`). Batch04 locked the pypdf extraction gate: digital CV mode
`layout`, image-only fixtures classify as exact `NO_EXTRACTABLE_TEXT` (no OCR),
with a frozen 4/5 digital success criterion and metrics-only aggregate evidence.
The embedding compatibility gate is still pending.

## Repository layout

- `frontend/`: minimal frontend package scaffold; no UI flow exists.
- `backend/`: minimal Python package and evaluation scaffold; no service exists.
- `infrastructure/`: empty Docker, Neo4j, and script placeholders only.

## Local prerequisites

Check the tools used by Phase 0 with these single-purpose commands:

```powershell
python --version
node --version
npm --version
docker compose version
```

Run the focused Astryx compatibility gate from `frontend/` after installing the
exact lockfile:

```powershell
npm ci --ignore-scripts
npm run check:astryx
```

Install backend Phase 0 dependencies from `backend/` (includes pinned `pypdf`),
then run the focused fake-provider ShopAIKey suite and synthetic PDF benchmark
tests (no network, no private corpus required):

```powershell
cd backend
python -m pip install -e ".[test]"
python -m pytest -q
```

Optional local pypdf benchmark against the ignored private fixture corpus
(metrics-only aggregate; never commits PDFs or document text):

```powershell
python -m evaluation.benchmark_pdf_extraction
```

Run that module from `backend/` after private manifests/PDFs exist under the
ignored `backend/evaluation/private/` path. Safe committed inputs are the
fixture manifest under `backend/evaluation/fixtures/` and aggregate metrics
under `backend/evaluation/reports/`.

The isolated live ShopAIKey diagnostic (uses the ignored root `.env` only;
requires user-owned `SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`, and `LLM_MODEL`):

```powershell
python backend/scripts/check_shopaikey_compatibility.py
```

There is no application run or build command yet.

## Configuration and private inputs

`.env.example` documents the root configuration contract. Real credentials
belong only in the ignored root `.env`; nested frontend or backend `.env` files
are unsupported. Private evaluation inputs (including PDF corpora) belong in
ignored locations such as `backend/evaluation/private/`; committed manifests
and aggregate reports contain only generic identifiers, digests, and
non-identifying metrics — never raw document text or real PDFs.
