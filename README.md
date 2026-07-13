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

## Phase status

Batch 01 establishes the scaffold, environment contract, pinned Astryx lockfile,
minimal render, and public component evidence. PDF and ShopAIKey compatibility gates
remain owned by the later Phase 0 batches in `docs/tasks/task_1.md`.
