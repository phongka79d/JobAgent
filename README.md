# JobAgent

JobAgent is in Phase 0 feasibility work. The repository currently contains the
minimal backend/infrastructure scaffold and a pinned Astryx frontend used to verify
documented public component APIs. Production JobAgent workflows are intentionally
out of scope until every Phase 0 gate passes.

## Repository layout

- `frontend/` — minimal React, TypeScript, and Vite render using Astryx 0.1.4.
- `backend/` — installable Python package scaffold; later feasibility tasks add only
  the dependencies they require.
- `infrastructure/` — local feasibility scripts and future local-service folders.
- `docs/feasibility/phase_0_report.md` — reproducible compatibility evidence.

## Configuration

Keep one user-managed `.env` at the repository root. It is ignored by Git and must
not be copied into tracked files. `.env.example` documents the supported variable
names and safe defaults; secret fields are intentionally empty, and applications
must not load `.env.example` at runtime.

## Astryx verification

From `frontend/`:

```powershell
npm ci
npm run build
npm run dev -- --host 127.0.0.1
npx astryx --help
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

Batches 01 through 03 establish the scaffold, environment contract, pinned Astryx
lockfile, public component evidence, synthetic PDF/pypdf gate, and the seven-group
ShopAIKey compatibility gate. The clean-environment reproduction and final
dependency decision remain owned by Batch04 in `docs/tasks/task_1.md`.
