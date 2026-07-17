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

**Current status (Plan 9 Batch02 on worktree):** Plan 8 Batch01–Batch04
(retention/chunks, observability APIs, accessible lazy sidebar inspector, and
synthetic local smoke) remain the reuse baseline. Plan 9 Batch01 added the
data-preserving SQLite foundation (`0003_add_cv_documents_and_ownership`):
`cv_documents` / `cv_document_drafts`, deleting lifecycle, ownership columns,
and flush-only document repositories. Plan 9 Batch02 completes document-first
extraction and atomic draft publication: strict `CVDocument` schemas, bounded
batch/consolidate/coverage extraction (`CV_DOCUMENT_BATCH_MAX_CHARS`, default
6000), pure document-to-profile projection, and `propose_profile_from_cv`
publishing `profile_drafts('current')` + `cv_document_drafts` + canonical
chunks in one short transaction only after provider/coverage/projection/
source-hash succeed outside any write txn (or rolls all back). Profile facts
derive only from the validated document; certifications and unknown headings
remain document content (`kind=other`). Reprocess/approval activation,
deletion coordination, graph CV branches, Agent active-CV tools, and frontend
CV Manager remain later batches. Six typed `GET /api/observability/*` routes
and the CV sidebar inspector from Plan 8 are unchanged. Synthetic observability
smoke evidence remains in `docs/acceptance/observability_sidebar_checklist.md`.

## Purpose and scope

JobAgent provides:

- Natural conversation through a React/Astryx chat UI over FastAPI SSE.
- Multipart PDF CV upload (sidebar or chat), document-first structured draft
  proposal (bounded CVDocument extract → projected profile → atomic draft/
  chunk publish), and interrupt-guarded Save Profile / Request Changes approval.
- Immutable archived prior CVs after approved replacement (retained PDF bytes and
  metadata; not selectable profile versions) and canonical parsed-text chunks
  for successful digital-PDF extraction.
- Read-only observability APIs for CV history, retained-file stream, selected
  chunk text, durable Agent-run history, and a bounded Neo4j graph snapshot
  (typed status, allowlisted labels/edges, hard caps, safe errors/redaction),
  with a matching accessible sidebar inspector (lazy tabs, query cache, safe
  display, semantic graph list fallback—no graph visualization dependency).
- Job description save from public URL or raw text, with durable extract/embed/
  sync outcomes and exact-hash duplicate/retry semantics.
- Hybrid top-N matching with skill coverage, preference components, quality
  multipliers, and collapsible score explanations in chat.
- Derived Neo4j Candidate/Job/Skill index rebuildable from SQLite stored
  embeddings without calling the provider.

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
| `frontend/` | Astryx chat shell, CV sidebar + observability inspector (`features/observability/**`), approval/saved-job/match cards, single SSE reducer, typed API clients |
| `backend/app/api/` | Thin public routes: health, CV upload, profile reads, chat history/turn/resume, read-only observability |
| `backend/app/agent/` | Agent state/context, graph factory, request-scoped checkpoint/runner |
| `backend/app/tools/` | Production registry of exactly six tools (three profile + `save_job` / `query_jobs` / `match_jobs`) |
| `backend/app/services/` | Domain orchestration (CV document extraction/projection, profile approval/extraction/drafts, JD, matching, tool execution, history, observability assembly) |
| `backend/app/repositories/` | Flush-only SQLite persistence (including `attachment_text_chunks`, `cv_documents` / `cv_document_drafts`, ownership kwargs) and observability cross-table read projections |
| `backend/app/graph/` | Neo4j lifecycle, Candidate/Job sync, revision consistency, provider-free rebuild, allowlisted observability projection |
| `backend/app/adapters/` | ShopAIKey chat and locked embedding transports |
| `backend/app/core/settings.py` | Sole runtime settings model; loads only root `.env` |
| `backend/migrations/versions/` | Sole Alembic migration chain (`script_location = migrations` in `backend/alembic.ini`) |
| `infrastructure/` | Compose, Dockerfiles, Neo4j skills seed, host diagnostics and rebuild help wrapper |

SQLite is the sole durable source of truth for profiles, attachments (including
immutable `archived` history and `deleting` lifecycle), attachment text chunks,
per-CV approved/draft documents, jobs, messages, runs, and tool results (with
optional CV ownership columns). Neo4j is a derived Candidate/Job/Skill index and
vector retrieval surface. ShopAIKey is the only external model provider.

Public functional endpoints (Master §14 core plus Plan 8 observability):

- `GET /api/health`
- `POST /api/attachments/cv`
- `GET /api/profile`
- `GET /api/profile/cv`
- `GET /api/chat/history`
- `POST /api/chat/turns`
- `POST /api/chat/runs/{run_id}/resume`
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

Focused Plan 9 Batch01 CV document and ownership persistence gate (migration
head `0003`, schema/ownership cascades, no document synthesis, ORM parity):

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

Neo4j is a derived index. Rebuild restores JobAgent `Candidate`, `Job`, and
`Skill` labels from SQLite **stored embeddings only**. It does not call
ShopAIKey, does not re-embed, and does not mutate SQLite. Destructive scope is
limited to those JobAgent labels and their relationships; there is no
unrestricted `MATCH (n) DETACH DELETE n`.

**Exclusive runtime contract (choice C):** rebuild is authorized only inside the
Compose backend container with `APP_ENV=local`, `NEO4J_URI=bolt://neo4j:7687`,
and `SQLITE_PATH=/data/jobagent.db`. Host loopback Bolt targets and host-side
destructive invocation are refused.

Canonical live command (repository root; stack already up):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.graph.rebuild
```

Expected: exit `0` with printed counts for `Candidate`, `Job`, `Skill`,
`HAS_SKILL`, `REQUIRES`, `PREFERS`, and `RELATED_TO`. Failures exit non-zero.

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
| Neo4j down during Candidate/Job sync | SQLite commit retained; result reports `NEO4J_SYNC_FAILED` | Restore Neo4j; run choice-C rebuild if graph is empty/stale |
| Neo4j down during match | `NEO4J_UNAVAILABLE`; no partial ranking | Restore Neo4j; re-run match |
| Candidate/Job revision mismatch | `NEO4J_REBUILD_REQUIRED`; no matching-path repair | Choice-C rebuild from SQLite embeddings |
| SSE / client disconnect | Visible frontend disconnect/failure; durable run/tool truth remains | Reload history; do not force-replay terminal tools |
| Duplicate CV / JD identity | Exact-hash reuse or failed-row retry on the same identity | Re-upload or re-save only when intentionally new content |
| Repeated Save / Request Changes / terminal resume | One accepted action; no graph/tool replay side effects | Use a new turn for a new decision |
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
  (Plan 7 baseline) and `docs/acceptance/observability_sidebar_checklist.md`
  (Plan 8 synthetic observability smoke).

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
  `docs/acceptance/local_release_checklist.md` and Plan 8 observability smoke
  in `docs/acceptance/observability_sidebar_checklist.md`, not by expanding
  this README into historical batch notes.
