# JobAgent

Local single-user MVP that helps one candidate chat with an agent to upload a CV,
approve a profile, save job descriptions, and receive deterministic evidence-backed
job matches. JobAgent is intentionally narrow: one conversation, one active profile,
one root environment, and a three-service Docker Compose stack on loopback ports.

This README is the local release and maintainer guide. It is sufficient for a
fresh clone plus one ignored root `.env`. Plan 7 final current-output release
verification is complete: dated PASS evidence for Automated Coverage through
Final Rerun lives in `docs/acceptance/local_release_checklist.md` on product
HEAD `1fdc93b`.

**Current status (Plan 11 complete — Batch01+Batch02 accepted, commit-ready on
product HEAD `04fa5f8` / P11B1):** Plan 11 resolves desktop failures F-01 through
F-05 without architecture or product-scope expansion. Batch01 delivered the four
root-cause repairs with focused regressions: CORS allowlist exactly
`GET`/`POST`/`DELETE`; Save Profile activation fans out once to profile refresh,
observability generation-backed CV Manager reload, and non-destructive saved-JD
currentness invalidation (no automatic evaluate); explicitly named `save_job`
turns get one bounded decision-node repair or fixed no-action text and
ToolResult-derived narration; empty extraction summaries parse and render
`No summary available` while MatchResult stays non-empty. Batch02 (`02A`) final
desktop reverification on that accepted code passed every focused/full static,
unit, build, plan-structure, and scope-hygiene gate; disposable Compose project
`jobagent-plan11-smoke` reached three-service health `overall=available`; original
F-01–F-05 reproductions passed with sanitized Origin-bearing API/network/backend
evidence (DELETE preflight+actual deletes, activation stale without evaluate POST,
nonblank CV history rows, one durable named duplicate `save_job` returned path,
empty-summary detail + `JOB_NOT_SCORABLE`); named smoke volumes were removed and
the normal `infrastructure` stack restored healthy. No product edits in Batch02.
Plan 10 Batch08 remains the prior accepted product baseline on HEAD `e429c10`.

Plan 8 Batch01–Batch04 (retention/chunks, observability APIs, accessible lazy
sidebar inspector, and synthetic local smoke) remain the reuse baseline. Plan 9
Batch01–Batch07 remain as delivered: SQLite document foundation, document-first
extraction and atomic drafts, approval-gated reprocess/activation, retryable
non-active CV deletion (exact `CV.id` graph branch via `graph/delete_cv.py`),
owned CV graph projection/rebuild (`graph/sync_cv.py` fixed labels `CV` /
`CVSection` / `CVEntry`, exclusive active `PROJECTS_TO`, provider-free rebuild,
bounded observability caps and document-revision staleness), bounded active-CV
Agent retrieval (`active_cv_context` outline injection, pure
`section`/`search`/`chunk` reader, seventh tool `read_active_cv` on the existing
single ToolNode with durable ownership/replay/redaction), and the accessible
**CV Manager** sidebar (typed reprocess/delete transport, sidebar-local
pending/error state, focused cache invalidation, sole `streamCvReprocess` SSE
path, panel/dialog action matrix, CV-branch graph display without changing D3
simulation/viewport semantics). Six typed `GET /api/observability/*` routes
remain. Synthetic observability smoke evidence remains in
`docs/acceptance/observability_sidebar_checklist.md`. Plan 9 CV Manager release
evidence remains in `docs/acceptance/cv_manager_checklist.md`.

Plan 10 Batch01 added structural-only evaluation persistence and pure
server-side context/currentness: Alembic head `0004_add_job_evaluations`, ORM/
schema/repository for one validated `MatchResult` per
`(job_id, evaluation_context_hash)`, named FKs with `CASCADE` from `job_posts`
and `attachments`, and `evaluation_context` deriving stable sorted JSON +
SHA-256 plus `none|current|stale` without rewriting history.

Plan 10 Batch02 completes shared exact-Job scoring and idempotent evaluation
orchestration: pure `match_scoring` projects top-N and single-Job results
through the same component/explanation owners (no formula fork); exact
`retrieve_exact_job_candidate` cosine read scores a Job outside vector top-50;
`evaluate_job` reuses a current context row with zero repeat provider/graph/
explanation work, otherwise runs consistency → embed once → exact score
outside SQLite transactions → context revalidation → short insert (or race
reload), returning safe codes including `EVALUATION_CONTEXT_CHANGED`.

Plan 10 Batch03 completes retry-safe exact Job deletion (P9-JD-05): one
application coordinator (`services/job_deletion.py`) verifies SQLite existence,
idempotently deletes only `(:Job {id: $job_id})` via allowlisted
`graph/delete_job.py` (missing graph node is success), then deletes the SQLite
Job so `job_evaluations` cascade; graph failures preserve SQLite for retry;
shared Skills, seed edges, Candidate/CV branches, and unrelated Jobs survive;
repeat after complete deletion returns `JOB_NOT_FOUND` without mutation.

Plan 10 Batch04 completes the deterministic saved-JD public API (P9-JD-01/02/04/05
API surface): bounded redacted `GET /api/jobs` and `GET /api/jobs/{job_id}` with
opaque newest-first cursor paging (`limit` 1..50), compact list projections,
server-derived `none|current|stale` + latest score, and safe `JOB_NOT_FOUND`;
plus source-bound `POST /api/jobs/save-and-evaluate` (durable zero-result
`match_jobs` authorization only), `POST /api/jobs/{job_id}/evaluate` (current-
context create/reuse), and `DELETE /api/jobs/{job_id}` (accepted graph-first
deletion coordinator). Thin routes delegate to accepted ingestion/evaluation/
deletion owners; public outcomes map internal ingest `returned` → `existing`.

Plan 10 Batch05 completes the typed saved-JD client and sidebar-local action
state (P9-JD-02/P9-JD-06 client schema/cache/pending/error/invalidation/
selection): strict allowlist parsers for list/detail/evaluation/outcome payloads
with forbidden-field rejection; focused transport for GET list/detail, POST
evaluate/save-and-evaluate, and DELETE; race-safe list/detail cache with
request-order guards and keep-data-on-error; per-Job pending action dedupe;
focused list/detail invalidation plus graph/chat generation bumps; and
deterministic post-delete selection. Evaluation `result` reuses
`parseMatchResult` (no second MatchResult parser); observability `state.ts` is
not grown.

Plan 10 Batch06 completes the accessible saved-JD sidebar interface
(P9-JD-02/P9-JD-06 tab/layout/a11y/action/evidence): `JD đã lưu` tab immediately
after `Agent runs` (focused `observabilityTabs.ts` extraction so oversized
`types.ts` shrinks); compact list/detail over accepted `useSavedJobsState`;
currentness action matrix (`Đánh giá với CV` / `Đánh giá lại` / no evaluate when
current, `Xoá JD` with Job-named confirmation); stale `Cần đánh giá lại` badge
and banner; persisted evaluation via existing `MatchCard`/`formatDisplayScore`
(no score-map fork); shell/rail/drawer/`13/47/40` proportions preserved.

Plan 10 Batch07 completes durable zero-result chat recovery
(P9-JD-01/P9-JD-06 zero-result rows): strict successful `match_jobs` `count=0`
gate only; exact card copy **Chưa có kết quả đánh giá** / **Lưu JD & đánh giá
lại**; durable initiating `source_message_id` from the same user/run/tool
projection as tool activity (no composer/latest inference); local
`useSavedJobRecovery` pending/error state outside chatReducer/SSE; created/
reused success reuses existing `MatchCard`; unavailable/error keeps truthful
retry UI; App→CvSidebar remount invalidates saved-JD sidebar caches.

Plan 10 Batch08 completes synthetic saved-JD release evidence (P9-JD-01 through
P9-JD-07 final validation): full backend ruff/mypy/pytest, full frontend
test/lint/typecheck/build, shared plan-structure validator through Plan 10,
three-service Compose health, and direct synthetic smoke for source-bound
save-and-evaluate, same-context reuse, stale-after-CV-change without auto-run,
explicit re-evaluate, exact Job delete preservation, and desktop/mobile
label/a11y dual evidence. Dated PASS rows live in
`docs/acceptance/saved_jd_evaluation_checklist.md` on product HEAD `e429c10`.

## Purpose and scope

JobAgent provides:

- Natural conversation through a React/Astryx chat UI over FastAPI SSE.
- Multipart PDF CV upload (sidebar or chat), document-first structured draft
  proposal (bounded CVDocument extract → projected profile → atomic draft/
  chunk publish), and interrupt-guarded Save Profile / Request Changes approval.
- Active/archived CV reprocess via `POST /api/cvs/{attachment_id}/reprocess`
  (normal SSE/approval contract; draft-only until Save Profile activation).
- Retryable complete non-active CV deletion via
  `DELETE /api/cvs/{attachment_id}` (active forbidden; SQLite/file/checkpoint/
  exact graph branch cleanup; `204` only when fully gone).
- Immutable archived prior CVs after approved replacement (retained PDF bytes and
  metadata; not selectable profile versions) and canonical parsed-text chunks
  for successful digital-PDF extraction.
- Read-only observability APIs for CV history, retained-file stream, selected
  chunk text, durable Agent-run history, and a bounded Neo4j graph snapshot
  (typed status, allowlisted labels/edges including active CV branch,
  hard caps, safe errors/redaction), with an accessible **CV Manager** sidebar
  (lazy tabs, query cache, reprocess/delete actions, focused invalidation,
  confirmation dialog, CV-branch graph display + semantic list fallback; D3
  simulation/pan/zoom/fit/reset semantics unchanged).
- Job description save from public URL or raw text, with durable extract/embed/
  sync outcomes and exact-hash duplicate/retry semantics.
- Retry-safe complete Job deletion service (exact Neo4j `Job.id` first, SQLite
  Job + evaluation cascade second; graph-fault preservation and shared-graph
  integrity) exposed via public `DELETE /api/jobs/{job_id}`.
- Deterministic saved-JD public API: cursor-paginated redacted list/detail,
  source-bound save-and-evaluate, explicit current-context evaluate, and
  complete delete through thin FastAPI adapters over accepted service owners.
- Typed saved-JD frontend client and sidebar-local state (strict parsers,
  request-order cache, pending/error maps, focused invalidation, safe
  post-delete selection) composed into the accessible **JD đã lưu** sidebar
  tab (compact list/detail, currentness actions, Job-named delete
  confirmation, MatchCard reuse); no second observability state architecture.
- Hybrid top-N matching with skill coverage, preference components, quality
  multipliers, and collapsible score explanations in chat; successful zero-result
  `match_jobs` rows show one source-bound recovery card that save/evaluates the
  durable initiating message and reuses MatchCard on success.
- Compact active-CV outline in Agent prompt context plus durable
  `read_active_cv` tool for bounded section/search/chunk evidence (active-only,
  dual caps, cursors; no automatic full-document walk).
- Derived Neo4j Candidate/Job/Skill plus fixed CV/CVSection/CVEntry index
  rebuildable from SQLite stored artifacts/embeddings without calling the
  provider.

JobAgent does **not** provide authentication, multi-user or multi-conversation
support, OCR/DOCX CVs, crawlers, browser automation, auto-apply, cover letters,
interview prep, public cloud deployment, workers/queues, alternate embeddings,
or a production security subsystem. See [Safeguards and limitations](#safeguards-and-limitations).

## Architecture and ownership

Request path and ownership:

```text
React/Astryx UI  →  FastAPI public API  →  one LangGraph Agent
       → services / repositories / adapters
       → SQLite (source of truth) + Neo4j (derived index) + ShopAIKey (LLM/embeddings)
```

| Layer | Owns |
|---|---|
| `frontend/` | Astryx chat shell, CV sidebar + observability inspector (`features/observability/**` including `CvManagerPanel`/`cvManagerState`, focused `observabilityTabs.ts`, `SavedJobsPanel` composition), approval/saved-job/match cards, single SSE reducer (`streamCvReprocess` reuses chat path), typed observability API clients, typed saved-JD client/state/panel (`features/jobs/api.ts`, `types.ts` saved-JD parsers, `savedJobsState.ts`, `SavedJobsPanel`/`SavedJobDetail`/`JobDeleteDialog` reusing `MatchCard`) |
| `backend/app/api/` | Thin public routes: health, CV upload, CV reprocess SSE, CV delete, profile reads, chat history/turn/resume, saved-JD list/detail/save-evaluate/evaluate/delete (`api/jobs.py`), read-only observability |
| `backend/app/agent/` | Agent state/context (including outline-only `active_cv_context`), graph factory, request-scoped checkpoint/runner (including multi-run checkpoint delete) |
| `backend/app/tools/` | Production registry of exactly seven tools (three profile + `save_job` / `query_jobs` / `match_jobs` + `read_active_cv`) |
| `backend/app/services/` | Domain orchestration (CV document extraction/projection, reprocess turns, profile approval/activation/drafts, non-active CV deletion coordinator + structured ownership resolver, active-CV bounded reader, pure `evaluation_context` hash/currentness, pure `match_scoring` single/multi-Job projection, exact `evaluate_job` orchestration with current-context reuse, graph-first/SQLite-second `job_deletion` coordinator, saved-JD read assembly + source-bound mutation orchestration (`saved_jobs.py`), JD, top-N `match_jobs`, tool execution, history, observability assembly) |
| `backend/app/repositories/` | Flush-only SQLite persistence (including `attachment_text_chunks`, `cv_documents` / `cv_document_drafts`, ownership kwargs, delete redaction/list primitives, `job_evaluations` insert/race-reload/lookup, narrow Job `delete_by_id` + focused `job_deletion` cascade primitive, focused `saved_jobs` cursor-page queries, chat_messages `get_by_id`) and observability cross-table read projections |
| `backend/app/graph/` | Neo4j lifecycle, Candidate/Job/CV sync, exact CV-branch delete, exact Job-node delete (`delete_job.py` allowlisted `Job.id`), revision consistency (Candidate/Job + active-CV observability), top-50 vector retrieval + exact `Job.id` cosine semantic read, provider-free rebuild, allowlisted observability projection |
| `backend/app/adapters/` | ShopAIKey chat and locked embedding transports |
| `backend/app/core/settings.py` | Sole runtime settings model; loads only root `.env` |
| `backend/migrations/versions/` | Sole Alembic migration chain (`script_location = migrations` in `backend/alembic.ini`) |
| `infrastructure/` | Compose, Dockerfiles, Neo4j skills seed, host diagnostics and rebuild help wrapper |

SQLite is the sole durable source of truth for profiles, attachments (including
immutable `archived` history and `deleting` lifecycle), attachment text chunks,
per-CV approved/draft documents, jobs, validated per-context `job_evaluations`,
messages, runs, and tool results (with optional CV ownership columns). Neo4j is
a derived Candidate/Job/Skill and fixed CV-branch index plus vector retrieval
surface. ShopAIKey is the only external model provider.

Public functional endpoints (Master §14 core plus Plan 8 observability and Plan 10
saved-JD API):

- `GET /api/health`
- `POST /api/attachments/cv`
- `POST /api/cvs/{attachment_id}/reprocess`
- `DELETE /api/cvs/{attachment_id}`
- `GET /api/profile`
- `GET /api/profile/cv`
- `GET /api/chat/history`
- `POST /api/chat/turns`
- `POST /api/chat/runs/{run_id}/resume`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/save-and-evaluate`
- `POST /api/jobs/{job_id}/evaluate`
- `DELETE /api/jobs/{job_id}`
- `GET /api/observability/cvs`
- `GET /api/observability/cvs/{attachment_id}/file`
- `GET /api/observability/cvs/{attachment_id}/chunks`
- `GET /api/observability/cvs/{attachment_id}/chunks/{ordinal}`
- `GET /api/observability/runs`
- `GET /api/observability/graph`

## Repository layout

```text
.
├── README.md                 # This local release guide
├── .env.example              # Documented variable names; safe empty secrets
├── backend/                  # Installable FastAPI/LangGraph application + tests
├── frontend/                 # React/TypeScript/Vite/Astryx client
├── infrastructure/
│   ├── docker-compose.yml    # Exactly frontend, backend, neo4j
│   ├── docker/               # Backend and frontend Dockerfiles
│   ├── neo4j/skills_seed.yaml
│   └── scripts/              # Provider diagnostic, PDF diagnostic, rebuild help
└── docs/
    ├── acceptance/           # Release, observability smoke, and manual JD checklists
    ├── plans/                # Master and plan sources of truth
    └── tasks/                # Canonical task contracts
```

Responsibility boundaries:

- Nested `frontend/.env` and `backend/.env` are not used.
- Compose does not mount the source tree or load `.env.example` as runtime config.
- Host Compose invocations pass `--env-file .env` from the repository root.
- Real credentials, databases, uploads, and Neo4j volumes stay outside Git.

## Prerequisites and environment

Prerequisites:

- Python 3.11+ available as `python` (or substitute `py -3` where needed)
- Node.js with `npm` (lockfile-driven install)
- Docker with Compose v2
- Free loopback ports `5173`, `8000`, `7474`, and `7687`
- A user-managed ShopAIKey API key for live provider/demo paths only

One root environment only:

1. Copy the template at the repository root:

```powershell
Copy-Item .env.example .env
```

2. Edit the ignored root `.env` and set local secrets (`NEO4J_PASSWORD`,
   `SHOPAIKEY_API_KEY`). Leave locked model/dimension values from the template
   unless you intentionally change the embedding contract.
3. Do not commit `.env`. Do not create nested env files. Applications load only
   the repository-root `.env`; they never load `.env.example` at runtime.
4. The frontend may consume only `VITE_API_BASE_URL` from that root environment
   (Compose build arg / container env). All other backend settings are owned by
   `backend/app/core/settings.py`.

## Setup and startup

Working directory for every block below is the **repository root** unless a
command begins with `Set-Location`.

### Backend editable install

```powershell
python -m pip install -e .\backend
```

### Frontend dependencies

```powershell
Set-Location frontend
npm ci
Set-Location ..
```

### Compose configuration check (non-secret)

Validates the compose file and root `.env` substitutions without printing secret
values:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config --quiet
```

### Local stack startup (detached, health-wait)

Starts exactly three services (`frontend`, `backend`, `neo4j`) with published
ports bound only to `127.0.0.1`:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expect overall `available` when SQLite, filesystem, and Neo4j are ready. Open
`http://127.0.0.1:5173` for the UI.

### Named disposable project (release verification)

For clean-clone or disposable release runs, name the project explicitly so
teardown cannot touch normal developer volumes:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-clone config --quiet
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-clone up --build -d --wait --wait-timeout 180
```

## Verification commands

Run automated gates on a host with the backend editable install and frontend
`npm ci` complete. Normal unit/integration/E2E/frontend tests use fakes and
disposable data only; they must not require live ShopAIKey, live Neo4j, or a
browser.

### Backend lint, type-check, unit, integration, and E2E

From the repository root:

```powershell
Set-Location backend
python -m ruff check .
python -m mypy app
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/e2e/test_demo_flow.py -q
Set-Location ..
```

Focused Plan 10 Batch01 evaluation persistence and canonical currentness gate
(migration head `0004_add_job_evaluations`, named schema/cascades, no evaluation
backfill, stable context hash, `none|current|stale`, MatchResult validation,
unique-key race reload):

```powershell
Set-Location backend
py -3.13 -m pytest tests/integration/test_migrations.py tests/integration/test_database_contract.py tests/integration/test_job_evaluations.py -q
py -3.13 -m pytest tests/unit/test_evaluation_context.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 10 Batch02 shared exact-Job scoring and idempotent evaluation gate
(top-N parity, exact-outside-top-50 cosine read, pure shared scorer, current-
context reuse with zero repeat external calls, context drift
`EVALUATION_CONTEXT_CHANGED`, uniqueness race reload, safe failures):

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_match_components.py tests/unit/test_match_explanations.py tests/unit/test_match_ordering.py tests/unit/test_evaluation_context.py tests/unit/test_job_evaluation.py tests/integration/test_job_evaluations.py tests/integration/test_match_jobs.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 10 Batch03 retry-safe exact Job deletion gate (parameterized
allowlisted `(:Job {id: $job_id})` delete, graph-first/SQLite-second cascade,
graph-fault SQLite preservation, retry completion, missing-node success, repeat
`JOB_NOT_FOUND` without mutation, shared Skill/seed/Candidate/CV/other Job
survival, exact-delete ≠ rebuild `CLEAR_JOB_CYPHER`):

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_job_graph_deletion.py tests/integration/test_job_deletion.py tests/integration/test_graph_rebuild_contracts.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 10 Batch04 deterministic saved-JD public API gate (cursor list/detail
redaction and currentness, durable zero-result source binding, URL/text ingest
delegation, exact-hash/current-context reuse, unavailable without false success,
delete 204/`JOB_NOT_FOUND`, safe errors, Agent/chat/tool compatibility):

```powershell
Set-Location backend
py -3.13 -m pytest tests/integration/test_saved_jobs_api.py tests/integration/test_job_evaluations.py tests/integration/test_job_ingestion.py tests/integration/test_job_deletion.py -q
py -3.13 -m pytest tests/unit/test_agent_graph.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py tests/e2e/test_demo_flow.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 10 Batch05 typed saved-JD client and sidebar-local action state gate
(strict list/detail/evaluation/outcome parsers, transport, request-order, keep-
data-on-error, pending dedupe, focused invalidation, safe post-delete selection,
MatchResult reuse; no panel UI):

```powershell
Set-Location frontend
npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-state.test.tsx
npm run lint
npm run typecheck
Set-Location ..
git diff --check
```

Focused Plan 10 Batch06 accessible saved-JD sidebar interface gate (`JD đã lưu`
after Agent runs, compact list/detail/currentness actions, MatchCard reuse,
Job-named delete confirmation, navigation/shell preservation, full FE matrix):

```powershell
Set-Location frontend
npm test -- --run src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-navigation.test.tsx src/test/match-card.test.tsx
npm test -- --run
npm run lint
npm run typecheck
npm run build
Set-Location ..
git diff --check
```

Focused Plan 10 Batch07 durable zero-result chat recovery gate (exact Vietnamese
copy, zero-only gating, durable `source_message_id`, pending dedup, created/
reused MatchCard, unavailable/error truth, saved-JD invalidation, Agent/chat
API compatibility):

```powershell
Set-Location frontend
npm test -- --run src/test/empty-match-card.test.tsx src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-navigation.test.tsx src/test/match-card.test.tsx src/test/chat-page.test.tsx
npm test -- --run
npm run lint
npm run typecheck
npm run build
Set-Location ..\backend
py -3.13 -m pytest tests/integration/test_saved_jobs_api.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py tests/e2e/test_demo_flow.py -q
Set-Location ..
git diff --check
```

Plan 10 Batch08 full release gate (automated + Compose + synthetic checklist;
fresh final-attempt evidence only; no product/config edits):

```powershell
Set-Location backend
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
py -3.13 -m pytest -q
Set-Location ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
Set-Location ..
python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
# Execute every row in docs/acceptance/saved_jd_evaluation_checklist.md
# with synthetic CVs/JDs only (desktop/mobile dual-evidence allowed).
git diff --check
git status --short
```

Focused Plan 9 Batch01 CV document and ownership persistence gate (migration
head through `0003` contract paths, schema/ownership cascades, no document
synthesis, ORM parity; head is now `0004` with evaluations included):

```powershell
Set-Location backend
py -3.13 -m pytest tests/integration/test_migrations.py tests/integration/test_database_contract.py -q
py -3.13 -m pytest tests/unit/test_attachment_profile_models.py tests/unit/test_chat_models.py tests/unit/test_cv_document_models.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 9 Batch02 document-first extraction and atomic draft publication
gate (strict CVDocument, bounded batch/coverage/projection, atomic
chunks + document draft + profile draft, rollback/failpoint, source-hash):

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_cv_document.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 9 Batch03 approval-gated CV reprocess and activation gate
(active/archived eligibility, SSE/ownership, draft-only reprocess, Request
Changes preserve, Save Profile switch/same-ID refresh, rollback, sync failure,
terminal resume idempotency):

```powershell
Set-Location backend
py -3.13 -m pytest tests/integration/test_cv_manager_api.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 9 Batch04 retryable complete non-active CV deletion gate (active
guard, fault/retry matrix, chat redaction, checkpoint/file/exact-graph cleanup,
preservation of active/profile/Jobs/Skills/unrelated, API 204/404/409):

```powershell
Set-Location backend
py -3.13 -m pytest tests/integration/test_cv_manager_deletion.py -q
py -3.13 -m pytest tests/integration/test_cv_manager_api.py tests/integration/test_interrupt_resume.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 9 Batch05 owned CV graph projection, rebuild, and active
observability gate (fixed-label sync, exclusive `PROJECTS_TO`, exact-delete
compatibility, provider-free rebuild of all approved branches, active-CV caps/
order/allowlists, ID/document-revision staleness, legacy reprocess-required):

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_cv_graph.py tests/unit/test_observability_graph.py tests/integration/test_observability_api.py tests/integration/test_graph_rebuild_contracts.py tests/integration/test_profile_approval.py tests/integration/test_cv_manager_deletion.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 9 Batch06 bounded active-CV Agent retrieval gate (outline-only
context, production turn injection, active-only section/search/chunk reader,
seventh tool durable ownership/replay/redaction, prompt narrow-mode policy,
one ToolNode + six-iteration topology):

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_active_cv_reader.py tests/integration/test_active_cv_tool.py tests/unit/test_agent_context.py tests/unit/test_agent_graph.py tests/integration/test_agent_runner.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 9 Batch07 CV Manager frontend gate (typed reprocess/delete
transport, sidebar pending/error + focused invalidation, sole SSE reprocess
path, accessible panel/dialog action matrix, graph CV-branch display, layout/
D3 regression):

```powershell
Set-Location frontend
npm test -- --run src/test/cv-manager.test.tsx src/test/cv-manager-api.test.ts src/test/observability-sidebar.test.tsx src/test/observability-navigation.test.tsx src/test/observability-panels.test.tsx src/test/graph-interaction.test.tsx
npm test -- --run
npm run lint
npm run typecheck
npm run build
Set-Location ..
git diff --check
```

Focused Plan 8 Batch01 retention/chunk gate (archive lifecycle + canonical
chunks; still valid regression surface):

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_attachment_text_chunks.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_migrations.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
git diff --check
```

Focused Plan 8 Batch02 observability read-contract gate (CV/chunk/run APIs +
bounded graph snapshot + static checks):

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_observability_graph.py tests/integration/test_observability_api.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..
```

Focused Plan 8 Batch03 accessible lazy sidebar inspector gate (lazy tabs/cache,
safe parsers, collapse a11y, overview regression, full FE suite + static/build):

```powershell
Set-Location frontend
npm test -- --run src/test/observability-sidebar.test.tsx src/test/observability-api.test.ts src/test/cv-sidebar.test.tsx
npm test -- --run
npm run lint
npm run typecheck
npm run build
Set-Location ..
git diff --check
```

Plan 8 Batch04 synthetic observability release evidence (focused backend + full
frontend gates, Compose health, checklist direct smoke, scope hygiene). Run from
the repository root with a usable root `.env` and Docker Desktop Linux engine
when exercising Compose/smoke; automated tests remain fake-backed:

```powershell
Set-Location backend
py -3.13 -m pytest tests/unit/test_attachment_text_chunks.py tests/unit/test_observability_graph.py tests/integration/test_observability_api.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py -q
py -3.13 -m ruff check app tests --no-cache
py -3.13 -m mypy app --no-incremental
Set-Location ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
Set-Location ..
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
# Then execute docs/acceptance/observability_sidebar_checklist.md with synthetic CVs only
git diff --check
```

Dated PASS rows for the Batch04 synthetic observations live only in
`docs/acceptance/observability_sidebar_checklist.md`. Do not paste raw PDF
bytes, storage paths, prompts, secrets, or stack traces into evidence cells.

`tests/e2e/test_demo_flow.py` is the disposable public-boundary smoke: greeting →
CV upload → profile draft/approval resume → JD save/extract/embed/sync →
`match_jobs`, with durable DB/file/checkpoint assertions through public FastAPI
APIs only. It is fake-backed and must not read root `.env`, developer volumes,
live Neo4j, network, or a browser.

### Frontend lint, type-check, test, and build

From the repository root:

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
Set-Location ..
```

### Neo4j integration

From the repository root (skips live probes when the stack or process
credentials are unavailable):

```powershell
Set-Location backend
python -m pytest tests/integration/test_neo4j_setup.py tests/integration/test_compose_runtime.py -q
Set-Location ..
```

### ShopAIKey provider diagnostic

Requires a valid `SHOPAIKEY_API_KEY` in the ignored root `.env`. From the
repository root:

```powershell
python infrastructure/scripts/diagnose_shopaikey.py
```

Expected: sanitized output ending with `SHOPAIKEY_COMPATIBILITY=PASS`. The
script calls the real provider; it must not print API keys or authorization
headers.

### Graph rebuild (choice C only)

Neo4j is a derived index. Rebuild restores JobAgent `Candidate`, `Job`,
`Skill`, `CV`, `CVSection`, and `CVEntry` labels from SQLite **stored artifacts
and embeddings only**. It does not call ShopAIKey, does not re-embed, and does
not mutate SQLite. Destructive scope is limited to those JobAgent labels and
their relationships; there is no unrestricted `MATCH (n) DETACH DELETE n`.
Only the active CV receives `PROJECTS_TO`; all approved document branches are
recreated for exact delete/rebuild ownership.

**Exclusive runtime contract (choice C):** rebuild is authorized only inside the
Compose backend container with `APP_ENV=local`, `NEO4J_URI=bolt://neo4j:7687`,
and `SQLITE_PATH=/data/jobagent.db`. Host loopback Bolt targets and host-side
destructive invocation are refused.

Canonical live command (repository root; stack already up):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.graph.rebuild
```

Expected: exit `0` with printed counts for `Candidate`, `Job`, `Skill`, `CV`,
`CVSection`, `CVEntry`, `HAS_SKILL`, `REQUIRES`, `PREFERS`, `RELATED_TO`,
`PROJECTS_TO`, `HAS_SECTION`, and `HAS_ENTRY`. Failures exit non-zero.

Thin host wrapper (help/version only; never runs rebuild). From the repository
root:

```powershell
python infrastructure/scripts/rebuild_neo4j.py --help
```

No-argument host invocation exits non-zero and prints the canonical Compose
command. Do not document or use a host rebuild path.

### Manual JD acceptance

Observations live only in `docs/acceptance/manual_jd_checklist.md` (disposable
local checklist; not a dataset, metric, or evaluation report). Full live re-run
needs the ignored root `.env`, Docker, free loopback ports, and preferably a
named disposable Compose project. Automated matching/unit gates remain the
fake-backed pre-live requirements.

Release evidence for automated coverage, safeguards, demo, rebuild, and final
scope is recorded in `docs/acceptance/local_release_checklist.md`. Plan 8
synthetic observability sidebar smoke evidence is recorded in
`docs/acceptance/observability_sidebar_checklist.md`.

## Demo flow

With the Compose stack healthy and a valid ShopAIKey key configured:

1. Open `http://127.0.0.1:5173`.
2. Send a natural greeting; expect a streamed assistant reply with no tool
   activity required.
3. Upload one digital PDF CV from the sidebar or chat composer (MIME/`%PDF-`/
   size/page limits apply; OCR is unsupported).
4. Review the profile draft. Choose **Save Profile** or **Request Changes** once
   per interrupted run; resume uses the existing chat resume path.
5. Confirm sidebar/profile reads reflect the approved profile after restart
   (SQLite is truth; history hydrates durable state).
6. Save a job from a public HTTP(S) URL and/or paste raw JD text. Observe durable
   success, quality (`full|partial|unscorable`), and sync outcomes on the saved-
   job card. Exact-hash duplicates return the existing job; failed rows support
   retry without inventing a second identity.
7. Ask the agent to match jobs. Expect backend-ordered cards (≤10) with skill
   groups and collapsible score breakdowns. Matching refuses unavailable or
   revision-inconsistent graph state rather than returning partial rankings.
8. Optionally disconnect/refresh mid-stream: the UI should show a clear
   disconnect/failure state, and durable run/tool truth rehydrates from history.

Do not edit the database by hand to complete the demo. If Neo4j lags SQLite after
an outage, use the choice-C rebuild command in
[Failure and recovery](#failure-and-recovery).

## Data persistence and cleanup

### Persistence locations

| Data | Location | Lifetime |
|---|---|---|
| SQLite application DB | Compose volume `app_data` at container path `/data/jobagent.db` | Survives normal container restart |
| Attachment files | Compose volume `app_data` under `/data/files` (UUID-relative paths) | Survives normal container restart |
| Neo4j graph and logs | Compose volumes `neo4j_data`, `neo4j_logs` | Survives normal container restart |
| Root secrets | Ignored repository-root `.env` | User-managed; never committed |
| Synthetic test PDFs | Tracked only under `backend/tests/fixtures/cv/` | Committed fixtures only |

Runtime databases, uploads, Neo4j volumes, and real CV/JD content must remain
outside Git.

### Safe cleanup

**Default local stack (preserve user data):** stop containers without deleting
named volumes:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml down --remove-orphans
```

**Named disposable release project only:** remove containers **and** that
project's volumes. Use only when the project name is an intentional disposable
identifier (example: `jobagent-plan7-clone`). Never run volume deletion against
an unnamed default project if you need to keep developer data.

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-clone down -v --remove-orphans
```

Do not delete arbitrary Docker volumes, do not wipe unrelated projects, and do
not commit cleanup of real user CVs, JD text, or secrets.

## Failure and recovery

| Situation | Expected behavior | Recovery |
|---|---|---|
| ShopAIKey timeout / rate limit | One bounded retry, then durable failure with safe summary | Fix network/key/quota; retry the user action |
| Invalid structured LLM output | Exactly one schema repair attempt, then safe failure | Retry; do not add hidden model switching |
| Invalid profile-update validation | One concise terminal profile-update failure; unrelated matching is not attempted | Correct the requested changes and retry |
| Neo4j down during Candidate/Job/CV sync | SQLite commit retained; result reports `NEO4J_SYNC_FAILED` | Restore Neo4j; run choice-C rebuild if graph is empty/stale |
| Neo4j down during match | `NEO4J_UNAVAILABLE`; no partial ranking | Restore Neo4j; re-run match |
| Candidate/Job revision mismatch | `NEO4J_REBUILD_REQUIRED`; no matching-path repair | Choice-C rebuild from SQLite embeddings |
| Active CV ID/document revision mismatch (graph observability) | Graph snapshot `stale` / `NEO4J_REBUILD_REQUIRED` (matching still Candidate/Job-only) | Choice-C rebuild; re-open graph tab |
| Legacy active CV without structured document | Graph ready with metadata-only CV; `CV_REPROCESS_REQUIRED` | Re-extract through CV Manager and approve |
| SSE / client disconnect | Visible frontend disconnect/failure; durable run/tool truth remains | Reload history; do not force-replay terminal tools |
| Duplicate CV / JD identity | Exact-hash reuse or failed-row retry on the same identity | Re-upload or re-save only when intentionally new content |
| Repeated Save / Request Changes / terminal resume | One accepted action; no graph/tool replay side effects | Use a new turn for a new decision |
| Active CV delete attempted | `409 CV_ACTIVE_DELETE_FORBIDDEN`; no mutation | Archive via approved replacement first; never delete active |
| Non-active CV delete partial failure (checkpoint/file/graph/finalize) | Attachment stays `deleting`; stable retry code on the response; no false `204` | Retry the same `DELETE /api/cvs/{id}` until `204` |
| Tool loop overflow | Controlled run failure after configured `TOOL_LOOP_LIMIT` | Narrow the request; inspect durable tool statuses |
| Embedding model/dimension mismatch on rebuild | Rebuild exits non-zero before delete; no partial wipe | Restore locked embedding settings; re-run rebuild |

Choice-C rebuild (stack up; repository root):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.graph.rebuild
```

Host wrapper remains help-only:

```powershell
python infrastructure/scripts/rebuild_neo4j.py --help
```

## Safeguards and limitations

Local-demo safeguards:

- Exactly three Compose services: `frontend`, `backend`, `neo4j`.
- Published ports bind only `127.0.0.1` (`5173`, `8000`, `7474`, `7687`).
- One ignored root `.env`; template secrets empty; no Compose `env_file:` mount
  of the template.
- Logs and UI payloads use stable codes and safe summaries—not API keys, raw
  document bodies, or stack traces.
- Rebuild is choice-C only; host wrapper cannot destroy graph data.
- Release evidence owners: `docs/acceptance/local_release_checklist.md`
  (Plan 7 baseline), `docs/acceptance/observability_sidebar_checklist.md`
  (Plan 8 synthetic observability smoke),
  `docs/acceptance/cv_manager_checklist.md` (Plan 9 CV Manager smoke), and
  `docs/acceptance/saved_jd_evaluation_checklist.md` (Plan 10 saved-JD
  synthetic release smoke).

Explicit limitations (not production claims):

- Single-user local demo only; no authentication, authorization, multi-tenant
  isolation, or public exposure hardening.
- No production security subsystem, SSRF/URL threat model productization, or
  public cloud deployment guidance.
- PDF extraction is digital-text pypdf only; OCR/image/DOCX CVs are unsupported.
- URL JD fetch is bounded HTTP/HTTPS HTML/text with no browser, cookies, auth,
  or site-specific crawlers.
- Matching is deterministic hybrid scoring over stored embeddings—not a
  multi-agent or reranked retrieval product.
- No CI workflows ship with this repository.

Out of scope (must remain absent from implemented/configured product surface):

```text
auth/multi-user/multiple conversations/profile history
DOCX/image CV/OCR/crawler/browser automation/auto-apply/tracking
cover letters/interview prep/public cloud
Qdrant/reranking/alternate embeddings
Redis/Celery/Kafka/workers/outbox/queue/sync state machine
multiple agents/agent handoffs/64K memory/LangSmith
CI workflows/evaluation datasets or metrics/production security subsystem
```

## Testing policy

- **Local only.** Automated and manual verification runs on a developer or
  disposable local machine; this repository does not define CI pipelines.
- **Synthetic committed fixtures only.** Tracked PDFs live under
  `backend/tests/fixtures/cv/`. Do not commit real CVs, JD bodies, databases,
  uploads, Neo4j dumps, or provider transcripts.
- **Real data outside Git.** Root `.env`, Compose volumes, and user uploads are
  ignored/untracked runtime state.
- **Fakes by default.** Unit, integration, frontend, and E2E gates use fake
  providers/graph seams and temporary SQLite/files. Live ShopAIKey calls are
  limited to `python infrastructure/scripts/diagnose_shopaikey.py` and
  intentional Compose demos.
- **No placeholder commands.** Every fenced command above has a repository
  owner (package script, pytest path, Compose file, or infrastructure script).
- **Evidence, not phase diaries.** Completion status for release checks is
  recorded with dated PASS rows in
  `docs/acceptance/local_release_checklist.md`, Plan 8 observability smoke in
  `docs/acceptance/observability_sidebar_checklist.md`, Plan 9 CV Manager smoke
  in `docs/acceptance/cv_manager_checklist.md`, and Plan 10 saved-JD smoke in
  `docs/acceptance/saved_jd_evaluation_checklist.md`, not by expanding this
  README into historical batch notes.
