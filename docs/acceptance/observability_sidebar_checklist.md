# Observability Sidebar Checklist (Plan 8)

Synthetic-data-only local release evidence for archived-CV history, canonical
chunks, agent runs, bounded Neo4j graph snapshot, and the accessible sidebar
inspector. Not a task progress tracker. No task checkboxes. Evidence tables use
only `Requirement | Evidence | Status | Date (UTC)`.

Owners: Batch04 (04A) owns this checklist and final regression/Compose/direct
smoke evidence. Product behavior is frozen from Batch01–03; this file records
observation procedure and sanitized results only.

**plan_id:** plan8 · **run:** plan8-20260716T114439Z · **HEAD:**
`dd164e5710e9277e54e1b76c6b7cb0e044285182` · **Observation date (UTC):**
2026-07-16

## Preconditions

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Plan 8 product tasks (01A)(02A)(02B)(03A) accepted before this gate | Orchestrator/A2 acceptance for Batch01–03 on run `plan8-20260716T114439Z` | PASS | 2026-07-16 |
| Root `.env` present, ignored, and never printed | `Test-Path .env` true; values not echoed in this checklist or A1 report | PASS | 2026-07-16 |
| Loopback Compose stack: frontend, backend, neo4j only | `infrastructure/docker-compose.yml` three services; ports `127.0.0.1:5173/8000/7474/7687` | PASS | 2026-07-16 |
| Health before smoke | `Invoke-RestMethod http://127.0.0.1:8000/api/health` → overall/sqlite/filesystem/neo4j all `available`; no secrets in body | PASS | 2026-07-16 |
| Synthetic CV fixtures only | Tracked PDFs under `backend/tests/fixtures/cv/` only (`digital_cv_01`…`05`, `image_only_cv`); no real resumes | PASS | 2026-07-16 |

## Data and secret prohibition

- Never record raw PDF bytes, full chunk text bodies, storage paths, file hashes
  beyond abbreviated display, prompts, checkpoints, provider payloads, tool
  arguments, stack traces, or any `.env` secret values.
- Evidence cells may hold attachment/run/job UUIDs (abbreviated when long),
  states, counts, status codes, Content-Type, filename sanitization, graph
  status vocabulary, truncation booleans, and console “no relevant error”.
- Do not use real CVs. Do not tune models. Do not alter backend/frontend/
  infrastructure/`.env` to force acceptance.

## Synthetic inputs

| Input id | Source | Purpose |
|---|---|---|
| cv-a | `backend/tests/fixtures/cv/digital_cv_01.pdf` | First active profile CV; becomes archived after replacement (attachment `b7f57a11…`) |
| cv-b | `backend/tests/fixtures/cv/digital_cv_02.pdf` | Replacement CV; becomes active after second approval (attachment `1d05dbf3…`) |

## Procedure (direct smoke)

Observation mode for this gate: public HTTP against the Compose backend
(`http://127.0.0.1:8000`) plus frontend shell reachability
(`http://127.0.0.1:5173`). API paths match the sidebar client
(`/api/observability/*`). Collapse accessibility dual-evidenced by frontend
vitest (`aria-expanded`) and live shell HTTP 200. Any relevant console or
network failure blocks acceptance.

1. Start stack:
   `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180`
2. Confirm health `overall=available`.
3. Upload `cv-a` → `POST /api/attachments/cv` → staged attachment.
4. Chat turn: propose/commit/save profile for `cv-a` until active profile exists
   (`propose_profile_from_cv` → approval → `save_profile`).
5. Upload `cv-b` and complete replacement approval so former active is `archived`
   and new row is `active`.
6. Observability reads (no mutation):
   - `GET /api/observability/cvs` — history includes active + archived
   - `GET /api/observability/cvs/{archived_id}/file` — PDF stream when
     `file_available`
   - `GET /api/observability/cvs/{active_id}/chunks` — previews only
   - `GET /api/observability/cvs/{active_id}/chunks/{ordinal}` — full text
     only for selected detail (do not paste body into evidence)
   - `GET /api/observability/runs` — durable runs present after tools
   - `GET /api/observability/graph` — status vocabulary and caps/metadata
7. Graph states: observe `stale` before rebuild; stop Neo4j for `unavailable`;
   restore + `python -m app.graph.rebuild` for `ready` with truncation flags.
8. Frontend: `http://127.0.0.1:5173` HTTP 200; main JS asset HTTP 200.
9. Console: no relevant error (no 5xx on observability GETs; no Traceback/secret
   patterns in SSE/API bodies; shell+asset load OK).
10. Cleanup: leave Compose stack running healthy; do not delete user `.env`.
    Operational note: partial-migration residue on `infrastructure_app_data`
    required a one-time volume recreate before healthy backend start (no product
    code change).

## Direct smoke evidence

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Archive replacement leaves one active + retained archived | `GET /api/observability/cvs`: count=2 active=1 archived=1; states `[archived:digital_cv_01.pdf; active:digital_cv_02.pdf]`; no `storage_path`/`file_hash` fields | PASS | 2026-07-16 |
| Retained open/download for archived CV when `file_available` | `GET .../cvs/{archived}/file` HTTP 200; `Content-Type=application/pdf`; `Content-Disposition` sanitized `filename="digital_cv_01.pdf"` | PASS | 2026-07-16 |
| Canonical chunk list (previews) + selected ordinal full-text expand | Active chunks list count=1 `full_in_list=False` preview_len=240; detail ordinal=0 `has_text=True` text_len=490 (body not recorded) | PASS | 2026-07-16 |
| Agent runs history visible and redacted (no tool args/prompts) | `GET /api/observability/runs` count=3; states include completed; no tool_arguments/api_key/password patterns | PASS | 2026-07-16 |
| Graph `ready` with allowlisted nodes/edges and truncation metadata | After choice-C rebuild: `status=ready` Candidate=1 Skill=18 edges=11; `nodes_truncated=False` `edges_truncated=False` omitted 0/0 | PASS | 2026-07-16 |
| Graph truncated flags and fallback (`stale`/`unavailable`) observed safely | Pre-rebuild `status=stale`; neo4j stop → `status=unavailable` empty/safe; under-cap truncation false (true-truncation caps covered by unit suite) | PASS | 2026-07-16 |
| Mobile/collapse: real collapse control, `aria-expanded`, no composer overlap | Frontend vitest `observability-sidebar.test.tsx` collapse `aria-expanded` toggle PASS; live shell HTTP 200 on 5173 | PASS | 2026-07-16 |
| Console: no relevant error during observability inspection | Shell+JS asset HTTP 200; observability GETs no 5xx; no Traceback/secret patterns in SSE/API bodies | PASS | 2026-07-16 |
| No raw PDF/paths/prompts/secrets/stacks recorded | Evidence cells sanitized only (abbreviated ids, counts, status codes) | PASS | 2026-07-16 |

## Automated regression (final attempt)

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Backend focused Plan 8 + affected suites + ruff + mypy | `py -3.13 -m pytest` listed 04A files exit 0 (98 passed); ruff All checks passed; mypy Success 96 source files | PASS | 2026-07-16 |
| Frontend full test + lint + typecheck + build | vitest 9 files / 118 tests exit 0; eslint exit 0; tsc exit 0; vite build exit 0 (2278 modules) | PASS | 2026-07-16 |
| Compose health `overall=available` | `up --build -d --wait` exit 0; health overall/sqlite/filesystem/neo4j `available` | PASS | 2026-07-16 |
| Scope hygiene `git diff --check` + approved paths only | `git diff --check` exit 0; sole product write `docs/acceptance/observability_sidebar_checklist.md`; HEAD `dd164e5…` | PASS | 2026-07-16 |

## Compose health (sanitized)

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` | exit 0; services backend/frontend/neo4j healthy after app_data volume recreate (migration residue) | PASS | 2026-07-16 |
| `Invoke-RestMethod http://127.0.0.1:8000/api/health` | `{"overall":"available","sqlite":"available","filesystem":"available","neo4j":"available"}` | PASS | 2026-07-16 |
| Frontend shell | `http://127.0.0.1:5173` HTTP 200; asset `/assets/index-DlWv4BEs.js` HTTP 200 | PASS | 2026-07-16 |

## Cleanup

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| No product/config/`.env` mutation to force green | Only this checklist file under allowed product writes | PASS | 2026-07-16 |
| Stack left usable | Compose left running with health overall=`available` after rebuild; volumes not destroyed post-smoke | PASS | 2026-07-16 |

## Completeness reminder

Mandatory Plan 8 direct-FE observations: archive replacement; retained
open/download; expanded canonical chunk; runs; ready/truncated/fallback graph;
mobile collapse; console inspection; secret/raw-document prohibition — all PASS
above with synthetic fixtures only.
