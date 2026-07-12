# JobAgent

## Project status

**Phase 0 is COMPLETE.** All required compatibility gates are evidence-backed
**PASS**. **Plan 2 is AUTHORIZED** to consume the locked decisions below without
re-benchmarking Phase 0 gates.

**Plan 2 Phase 1 local foundation is evidence-backed** across Batches 01–05:

| Batch | Outcome |
|---|---|
| Batch01 | Runnable FastAPI + React/TypeScript/Vite scaffolds and one typed root configuration contract |
| Batch02 | SQLite application metadata and repeatable initial Alembic migration |
| Batch03 | Contained staged/active attachment filesystem persistence |
| Batch04 | Idempotent Neo4j schema primitives, durable replay-safe graph outbox, rebuild skeleton |
| Batch05 | Production-shaped Compose (frontend/backend/Neo4j), sanitized `GET /api/health`, green local quality + live exit evidence |

**Plan 3 Phase 2 chat transport / Agent runtime is evidence-backed** across
Batches 01–04 (see Phase 2 quality gates and Plan 4 handoff below). Normal
automated tests use injected fakes and never call ShopAIKey.

Re-running live three-service Compose exit checks requires a populated ignored
root `.env` (especially a non-empty `NEO4J_PASSWORD`). Do not paste secret
values into reports, commits, or chat.

Phase 0 evidence destination:
`backend/evaluation/reports/phase_0_feasibility.md` (final decision table at EOF).

## Architecture and persistence boundaries

Exactly three product working folders:

- `frontend/`: production-shaped Astryx React/TypeScript/Vite shell (static nginx
  image under Compose). Talks only to FastAPI. Only `VITE_`-prefixed public
  configuration is published to frontend assets.
- `backend/`: FastAPI foundation, typed root settings, SQLite metadata, attachment
  storage, Neo4j client/schema, graph outbox, sanitized health, and Phase 0
  diagnostics.
- `infrastructure/`: Dockerfiles, Compose definition, Neo4j placeholders, and
  the graph rebuild command skeleton.

Root documentation and configuration files are not a fourth working folder.

Persistence ownership:

| Store | Role |
|---|---|
| SQLite (`SQLITE_PATH`) | Only canonical application source of truth (eleven application tables + Alembic version) |
| Filesystem (`FILES_DIR`) | Uploaded attachment bytes under service-owned `staged/` and `active/` paths |
| Neo4j | Derived, fully rebuildable graph data only; never the sole copy of canonical state |

Public application endpoints after Plan 4 (exactly seven application routes):

- `GET /api/health`
- `POST /api/attachments/cv`
- `GET /api/profile`
- `GET /api/profile/cv`
- `GET /api/chat/history`
- `POST /api/chat/turns`
- `POST /api/chat/runs/{run_id}/resume`

(plus framework documentation routes). Public profile mutations, public job
CRUD, matching UI, continuous workers, Qdrant, CI, and cloud deployment remain
out of scope.

## Locked dependency decisions

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
| LangGraph | `langgraph==1.2.9` (optional extra / later execution plans) |
| Neo4j driver | `neo4j==6.2.0` |
| Compose Neo4j image | `neo4j:5.26-community` |
| HTTP fetch (Plan 5) | `httpx==0.28.1` (SSRF-safe bounded fetch; no ambient proxy/cookies/auth) |
| HTML main text (Plan 5) | `trafilatura==2.1.0` (URL path only; paste path is plain text) |

Normal automated tests use fakes or temporary local files and never call
ShopAIKey. Optional Phase 0 live diagnostics remain separate (see below).

## Local prerequisites

```powershell
python --version
node --version
npm --version
docker compose version
```

All application configuration comes from the **single root** `.env` contract.
Copy names from `.env.example`, populate required non-placeholder values
(especially `NEO4J_PASSWORD`, `SHOPAIKEY_API_KEY`, and path/URI fields), and do
**not** create nested `frontend/.env` or `backend/.env` files.

## Required local quality commands (Phase 1)

These are the primary Plan 2 quality gates. They do not require live Docker or
provider network calls when using the documented synthetic/fake test suites.

### Backend

```powershell
cd backend
python -m pip install -e ".[test]"
python -m ruff check app tests
python -m mypy app
python -m pytest -q
```

Local non-Compose server (loads root `.env` at startup only):

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

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

The Vite dev server binds to `http://127.0.0.1:5173`. Only `VITE_API_BASE_URL`
is published to frontend code.

### SQLite migrations

SQLite is the canonical store. The reviewed initial head creates the eleven Plan
2 application tables. LangGraph checkpoint tables are **not** application
metadata.

Apply or re-apply head (safe against an already-initialized file; no automatic
downgrade):

```powershell
cd backend
python -m alembic -c alembic.ini upgrade head
```

Migration integration checks use temporary SQLite files only and do not read the
user-owned root `.env`:

```powershell
cd backend
python -m pytest -q tests/integration/test_migrations.py
```

### Attachment, graph, outbox, and health focused suites

```powershell
cd backend
python -m pytest -q tests/services/test_attachment_storage.py tests/repositories/test_attachments.py
python -m pytest -q tests/graph tests/repositories/test_graph_outbox.py tests/infrastructure/test_rebuild_graph.py
python -m pytest -q tests/api/test_health.py tests/test_lifecycle.py
```

### Graph rebuild (Candidate + active/scorable Jobs)

Default is dry-run (non-destructive). Destructive clear of JobAgent-derived
labels only requires `--confirm-destructive`. A successful rebuild recreates
schema constraints/vector index, the accepted Candidate projection, and every
active full/partial Job projection (with recomputed 1536-vectors), then verifies
ID/count parity before marking Job/outbox sync state. Ignored duplicates and
unscorable Jobs stay excluded.

```powershell
python infrastructure/scripts/rebuild_graph.py --help
python infrastructure/scripts/rebuild_graph.py
```

## Docker Compose (three-service local runtime)

From the repository root. Compose loads the **single root** env file via
`--env-file` (never bake `.env` into images).

Static validation without real secrets:

```powershell
docker compose --env-file .env.example -f infrastructure/docker-compose.yml config
docker compose --env-file .env.example -f infrastructure/docker-compose.yml build
```

Live startup (requires populated root `.env`, especially non-empty
`NEO4J_PASSWORD`):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
```

Expected services: `frontend`, `backend`, `neo4j` only. Host publications:

- Backend API: `http://127.0.0.1:8000`
- Frontend static: `http://127.0.0.1:5173` (container port 8080)
- Neo4j: internal network only (no default host ports)

Named volumes (persist across ordinary restart and plain `down`):

- `jobagent_backend_data` → SQLite + `FILES_DIR` under `/data`
- `jobagent_neo4j_data` → Neo4j store

Sanitized health (overall + `sqlite` / `filesystem` / `neo4j` component states
only; no credentials, URIs, paths, or stack traces):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health | ConvertTo-Json -Depth 4
```

Apply migrations against the Compose backend volume (paths come from root env;
default example uses `/data/jobagent.db`):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec backend python -m alembic -c alembic.ini upgrade head
```

Idempotent Neo4j schema setup is performed best-effort at backend startup and
again inside the Neo4j health probe when connectivity is up. Re-running schema
must not create duplicate constraints/indexes.

Stop services **without** deleting named volumes:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml down
```

(Do not add `-v` for ordinary shutdowns if you need persistence evidence.)

## Optional Phase 0 live diagnostics

These are **not** required Plan 2 quality gates. They need ignored root secrets
and/or private corpora and must never print credentials or document text.

```powershell
cd frontend
npm ci --ignore-scripts
npm run check:astryx
```

```powershell
cd backend
python -m evaluation.benchmark_pdf_extraction
python -m evaluation.benchmark_embeddings
```

```powershell
python backend/scripts/check_shopaikey_compatibility.py
```

## Configuration and private inputs

`.env.example` documents the root configuration contract, including
`EMBEDDING_MODEL=text-embedding-3-small` and `EMBEDDING_DIMENSIONS=1536`.
Real credentials belong only in the ignored root `.env`. Nested frontend or
backend `.env` files are unsupported. Private evaluation inputs belong in
ignored locations such as `backend/evaluation/private/`. Committed manifests and
aggregate reports contain only generic identifiers, digests, and non-identifying
metrics — never raw document text, real PDFs, private labels, or secrets.

## Plan 4 progress (Batches01-06) — Phase 3 exit

**Plan 4 Phase 3 (CV, Candidate Profile, approval workflow) is evidence-backed
across Batches 01–06.** Normal automated tests use injected fakes and temporary
local files only — zero real ShopAIKey calls and zero live Neo4j requirements.

| Batch | Outcome |
|---|---|
| Batch01 | Strict Candidate/Preference/draft contracts, skill normalization, repositories |
| Batch02 | Safe PDF intake, layout extraction, PII redaction, pending-draft extraction |
| Batch03 | Atomic approved replacement + replay-safe Candidate graph outbox/sync |
| Batch04 | Four production tools on the existing approval/resume seam |
| Batch05 | Public profile reads + shared Astryx sidebar/composer CV experience |
| Batch06 | Full fake-backed backend/frontend exit proof + Plan 5 handoff |

Batch01 establishes the validated Candidate persistence and context foundation;
it does not yet ingest or upload CV files:

- Strict Candidate Profile, Job Preferences, pending-draft, and bounded approval-summary contracts validate opaque SQLite JSON at repository boundaries.
- Deterministic skill normalization uses an approval-only packaged YAML seed; unknown skills remain provisional, with stable keys and explicit exclusion preservation.
- Singleton profile/preferences and pending-draft repositories use caller-owned transactions, while chat context reuses one compact approved projection without raw document bodies, contact fields, storage paths, or provider payloads.

Focused Batch01 verification:

```powershell
cd backend
python -m pytest -q tests/schemas/test_candidate.py tests/schemas/test_preferences.py tests/schemas/test_profile_draft.py
python -m pytest -q tests/services/test_skill_normalization.py
python -m pytest -q tests/repositories/test_profiles.py tests/repositories/test_preferences.py tests/repositories/test_profile_drafts.py tests/services/test_context_assembly.py
python -m ruff check app/repositories app/schemas app/services/profile_context.py app/services/skill_normalization.py app/services/chat_context.py tests/repositories tests/schemas tests/services/test_skill_normalization.py tests/services/test_context_assembly.py
python -m mypy app/repositories app/schemas app/services/profile_context.py app/services/skill_normalization.py app/services/chat_context.py
```

Batch02 adds the safe intake-to-pending-draft pipeline:

- `POST /api/attachments/cv` streams one PDF into contained staged storage,
  validates the configured size/page limits, and returns sanitized attachment
  metadata with deduplication.
- PDF text extraction is layout-only and fail-closed; deterministic PII
  redaction happens before the fake-backed structured extraction boundary.
- Candidate extraction uses the locked structured adapter with its single
  schema-repair ceiling, normalizes skills, and writes only a pending profile
  draft. Approved profile/preferences and attachment state remain unchanged.

Batch03 adds atomic approved-state replacement and replay-safe Candidate graph
synchronization behind the pending-draft boundary:

- Approved profile changes enqueue one identifier-only, coalescing Candidate
  outbox identity in the same SQLite transaction; bounded startup/rebuild
  processing reloads current canonical state and idempotently replaces the
  non-excluded `HAS_SKILL` projection.
- `ProfileCommitService` promotes staged bytes before commit, atomically replaces
  profile/preference/draft/attachment state, compensates every pre-commit
  failure including cancellation, and retains durable cleanup work when only
  old-file cleanup fails.

Focused Batch03 verification:

```powershell
cd backend
python -m pytest -q tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py tests/infrastructure/test_rebuild_graph.py tests/test_lifecycle.py
python -m pytest -q tests/services/test_profile_service.py tests/integration/test_profile_replacement.py tests/repositories/test_attachments.py tests/repositories/test_graph_outbox.py
python -m ruff check app/repositories/graph_outbox.py app/graph/candidate_sync.py app/services/profile_service.py app/services/attachment_storage.py tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py tests/services/test_profile_service.py tests/integration/test_profile_replacement.py
python -m mypy app/repositories/graph_outbox.py app/graph/candidate_sync.py app/services/profile_service.py app/services/attachment_storage.py app/repositories
```

Batch04 exposes the four production Candidate tools through the existing
LangGraph registry and approval/resume seam:

- `get_candidate_context`, `propose_profile_from_cv`, and
  `propose_profile_update` reuse the bounded context and pending-draft services;
  proposal tools never write approved state.
- `commit_profile_draft` accepts only application-owned authorization from a
  matching approve resume. Replayed resume keys are idempotent per run/draft.
- Request Changes feeds the correction back into the same checkpointed run and
  pending draft, then emits another bounded `approval_required` payload. The
  public SSE union remains exactly eight event names and excludes internal
  draft/run authorization data.

Focused Batch04 verification:

```powershell
cd backend
python -m pytest -q tests/tools/test_candidate_context.py tests/tools/test_profile_draft.py tests/tools/test_registry.py tests/services/test_context_assembly.py
python -m pytest -q tests/tools/test_profile_commit.py tests/agent/test_profile_approval.py tests/integration/test_profile_approval.py tests/api/test_chat.py tests/schemas/test_sse.py
python -m ruff check app/agent app/tools app/schemas/sse.py app/schemas/chat.py app/services/chat_service.py tests/agent/test_profile_approval.py tests/tools tests/integration/test_profile_approval.py
python -m mypy app/agent app/tools app/schemas/sse.py app/schemas/chat.py app/services/chat_service.py
```

Batch05 adds the public read surface and shared Astryx CV experience:

- `GET /api/profile` returns the approved profile/preferences with safe active
  attachment metadata, while `GET /api/profile/cv` streams only the active PDF.
- Sidebar and composer uploads reuse one typed client and shared upload state;
  the sidebar starts a turn immediately, while the composer holds a removable
  CV token until the next message is submitted.
- Profile proposals use a bounded approval card. **Save Profile** resumes the
  guarded approval, while **Request Changes** sends the next composer message
  through the same-run correction workflow before presenting a fresh card.

Batch06 proves the complete Phase 3 slice end-to-end with fakes only:

- Backend full workflow: synthetic digital PDF upload → redacted structured
  extraction → same-draft correction → unauthorized commit rejected → one
  approval → profile/preferences/active file persisted → Candidate outbox
  process/replay (no duplicate nodes/edges, no excluded skill edges) → restart
  re-read of approved state
  (`backend/tests/integration/test_full_profile_workflow.py`).
- Replacement failure injection: every pre-commit boundary leaves the prior
  profile/CV readable; cleanup-only failure leaves the new state readable and
  retryable. Upload/pipeline failures return sanitized codes with zero contact
  sentinel leakage across requests, SSE, history, durable rows, outbox, and logs.
- Frontend full workflow: raw SSE through the real parser/reducer/shell for
  sidebar upload, composer token, proposal card, Request Changes, Save Profile,
  duplicate actions, errors, and disconnect
  (`frontend/src/test/profile-workflow.integration.test.tsx`).
- Production exposure: exactly four Candidate tools; application routes are
  exactly the seven authorized paths above; synthetic tools and later Job tools
  remain absent from production modules.

### Phase 3 quality gates (evidence-backed commands)

Backend (no ShopAIKey network calls):

```powershell
cd backend
python -m ruff check app tests
python -m mypy app
python -m pytest -q
python -m pytest -q tests/integration/test_full_profile_workflow.py
```

Frontend:

```powershell
cd frontend
npm ci --ignore-scripts
npm run check:astryx
npm run lint
npm run typecheck
npm run test -- --run
npm run test -- --run src/test/profile-workflow.integration.test.tsx
npm run build
```

Compose static (uses `.env.example`; no live secrets required):

```powershell
docker compose --env-file .env.example -f infrastructure/docker-compose.yml config
docker compose --env-file .env.example -f infrastructure/docker-compose.yml build
```

Production exposure / route inventory scans (domain names present only where
authorized; four Candidate tools and the seven application routes are allowed):

```powershell
rg -n "synthetic|echo_label|raw_cv|document_text|contact_address|propose_profile_from_cv|commit_profile_draft|save_job|match_jobs" backend/app frontend/src
rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api
git diff --check
```

Optional live observation (user-owned root `.env` only; not required for
acceptance and not claimed as run by this handoff):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
# Then one user-observed upload/approve/read flow against real secrets.
```

## Plan 3 progress (Batch01)

Batch01 establishes the durable chat and SSE contract foundation only:

- Singleton conversation/history, Agent-run/idempotency, and sanitized tool-execution repositories now use the existing SQLite transaction boundary.
- The additive Plan 3 Alembic head adds durable turn/resume idempotency fields without application-owned LangGraph checkpoint tables.
- Backend owns an exact validated eight-event SSE union and producer-side ordering boundary; no public chat route exists yet.

Focused Batch01 verification:

```powershell
cd backend
python -m pytest -q tests/repositories/test_conversations.py tests/repositories/test_agent_runs.py tests/repositories/test_tool_executions.py tests/integration/test_migrations.py tests/schemas/test_sse.py
python -m ruff check app/db app/repositories app/schemas tests/repositories tests/schemas tests/integration/test_migrations.py
python -m mypy app/db app/repositories app/schemas
```

## Plan 3 progress (Batch02)

Batch02 adds the controlled runtime behind the existing contract:

- The typed ShopAIKey adapter uses the locked model/modes, fake-backed tests, and bounded repair/retry failures.
- One LangGraph `StateGraph` and one `ToolNode` use an empty-by-default production tool registry, a six-iteration guard, and a production approval interrupt/resume seam.
- Per-run `AsyncSqliteSaver` checkpoints retain interrupted work, resume on the same durable thread, and are deleted only after final assistant persistence.

Focused Batch02 verification:

```powershell
cd backend
python -m pytest -q tests/services/test_shopaikey_chat.py tests/agent/test_state.py tests/agent/test_prompt.py tests/services/test_context_assembly.py tests/agent/test_graph.py tests/tools/test_registry.py tests/integration/test_agent_lifecycle.py
python -m ruff check app/agent app/tools app/services/shopaikey_chat.py app/services/chat_context.py app/services/chat_service.py tests/agent tests/tools tests/services/test_shopaikey_chat.py tests/services/test_context_assembly.py tests/integration/test_agent_lifecycle.py
python -m mypy app/agent app/tools app/services/shopaikey_chat.py app/services/chat_context.py app/services/chat_service.py
```

## Plan 3 progress (Batch03)

Batch03 exposes the durable runtime through the public chat surface and a base
Astryx chat UI:

- Public FastAPI routes are limited to `GET /api/chat/history`, `POST /api/chat/turns`, and `POST /api/chat/runs/{run_id}/resume`; POST routes stream the validated SSE union.
- The frontend uses the existing `VITE_API_BASE_URL` boundary, an incremental SSE parser, a pure run/event reducer, history hydration, duplicate filtering, and disconnect/approval states.
- The first screen is an Astryx chat experience with hydrated messages, partial assistant text, sanitized tool activity, approval/correction resume controls, and no profile/job/upload UI.

Focused Batch03 verification:

```powershell
cd backend
python -m pytest -q tests/api/test_chat.py tests/integration/test_chat_transport.py tests/test_lifecycle.py
python -m ruff check app/api/chat.py app/schemas/chat.py app/main.py tests/api/test_chat.py tests/integration/test_chat_transport.py
python -m mypy app/api/chat.py app/schemas/chat.py app/main.py

cd frontend
npm run check:astryx
npm run test -- --run src/features/chat/reducer.test.ts src/lib/sse/parser.test.ts src/features/chat/api.test.ts src/features/chat/components src/test/app.chat.test.tsx
npm run lint
npm run typecheck
npm run build
```

## Plan 3 progress (Batch04) — Phase 2 transport proof

Batch04 proves the complete local frontend-to-Agent transport with injected
fakes only, confirms production has no synthetic tool, and records the stable
Plan 4 handoff. Public tool outcomes are fail-closed to short allowlisted status
tokens only; raw tool arguments/results never enter durable
`arguments_summary` or SSE.

- Full-path backend fixture: real FastAPI routes → `ChatService` → production
  LangGraph + `ToolNode` → validated SSE → durable history/run/tool rows and
  completed-checkpoint cleanup (`backend/tests/integration/test_full_chat_transport.py`).
  Proofs include unique raw-argument sentinel absence across parsed SSE, raw
  wire, history, durable tool rows, and captured logs; instrumented approval
  tool action and durable tool-row counts stay exactly one after duplicate
  turn/resume keys.
- Full-path frontend fixture: raw SSE frames through real
  `streamChatTurn` / `streamChatResume` (parser) into the pure reducer and
  ChatShell for ordinary completion, tool activity, approval/resume,
  duplicates, failure, and disconnect
  (`frontend/src/test/chat-transport.integration.test.tsx`).
- At the Phase 2 handoff, synthetic `echo_label` / approval helpers existed only
  under `backend/tests/` and the production registry was empty. Plan 4 Batch04
  replaces that empty startup registry with the four Candidate tools above.
- The Phase 2 public route proof covered health plus the three chat endpoints;
  Plan 4 Batch02 subsequently added `POST /api/attachments/cv`.

### Phase 2 quality gates (evidence-backed commands)

Backend (no ShopAIKey network calls):

```powershell
cd backend
python -m ruff check app tests
python -m mypy app
python -m pytest -q
python -m pytest -q tests/integration/test_full_chat_transport.py
```

Frontend:

```powershell
cd frontend
npm ci --ignore-scripts
npm run check:astryx
npm run lint
npm run typecheck
npm run test -- --run
npm run test -- --run src/test/chat-transport.integration.test.tsx
npm run build
```

Compose static (uses `.env.example`; no live secrets required):

```powershell
docker compose --env-file .env.example -f infrastructure/docker-compose.yml config
docker compose --env-file .env.example -f infrastructure/docker-compose.yml build
```

Production exposure / route inventory scans (expected: no production
`echo_label` or future Job/matching tool; the four Candidate tools and the
health, CV attachment, and chat routes are allowed):

```powershell
rg -n "synthetic|echo_label|propose_profile_from_cv|commit_profile_draft|save_job|match_jobs" backend/app frontend/src
rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api
git diff --check
```

Optional live observation (user-owned root `.env` only; not required for
acceptance):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
# Then one ordinary chat turn through the UI against the production adapter.
```

## Current limitations (after Plan 5 / Phase 4 exit)

- Phase 3 CV-to-approved-profile workflow is complete for local fake-backed
  proof: shared upload, redaction/extraction, draft-only proposal/correction,
  guarded approval, atomic replacement, Candidate graph sync, public profile
  reads, and the shared Astryx sidebar/composer experience.
- **Plan 5 Phase 4 (JD ingestion through graph sync + chat card) is
  evidence-backed across Batches 01–06.** Fake-backed exit proof covers
  acquisition (URL/raw/SSRF/HTML paste), persistence-first extraction and
  failure retention, exact/normalized duplicates and authorized `force_new`,
  shared Candidate/Job skill normalization, locked embeddings, six production
  tools, seven routes, Job outbox replay, complete rebuild parity, sanitized
  saved-Job chat card, and zero raw/secret leakage in tests. See Plan 5 Batch
  sections and Phase 4 exit gates below.
- Matching, ranking, score generation, evaluation UI, OCR/DOCX/image CVs,
  profile history, and a full profile editor remain out of scope (Plan 6+).
- No public profile/job CRUD mutations, authentication, continuous outbox
  worker, Qdrant, CI, or cloud deployment.
- Production registers exactly six tools: the four Plan 4 Candidate tools plus
  `save_job` and `query_jobs`. `match_jobs` remains reserved only (not
  implemented or registered).
- Graph rebuild reconstructs Candidate plus active full/partial Jobs (with
  vectors) from SQLite and verifies ID/count parity; ignored/unscorable Jobs
  remain excluded. Online Job sync is bounded startup/explicit process only.
- Outbox repository is durable and replay-safe; no background poller ships yet.
- Optional live ShopAIKey/Neo4j/Compose observation is **not** required for
  Phase 4 acceptance and is **not claimed** here. Normal automated tests use
  fakes only. Optional live observation needs a user-populated ignored root
  `.env` and is never required for acceptance.

## Plan 5 progress (Batch01) — safe public JD input acquisition

**Plan 5 Batch01 is evidence-backed.** Normal automated tests use injected DNS
and transport fakes only — no public network fetches and no ShopAIKey calls.

| Batch | Outcome |
|---|---|
| Batch01 | DNS/redirect-aware URL policy, bounded HTTP retrieval, deterministic URL-or-paste JD text acquisition |
| Batch02 | Grounded Job extraction, deterministic JD quality, persistence-first JobPost repository and duplicate primitives |
| Batch03 | Shared Candidate/Job skill normalization + versioned Job text and locked ShopAIKey embeddings |
| Batch04 | Persistence-first `JDIngestionService` + Agent-facing `save_job` / `query_jobs` (six production tools) |
| Batch05 | Replay-safe Job/Skill/JobFamily outbox projection + complete Candidate/Job rebuild parity |
| Batch06 | Sanitized saved-Job chat card + full fake-backed Phase 4 exit proof + Plan 6 handoff |

Batch01 establishes the controlled acquisition foundation only:

- Credential-free HTTP/HTTPS policy blocks localhost, metadata, and forbidden
  IPv4/IPv6 classes; every DNS answer and redirect target is re-validated
  (`backend/app/security/url_policy.py`).
- Bounded fetch uses pinned `httpx`, at most three redirects, configured
  timeout/body ceilings, `text/html|text/plain` only, and code-only failures
  (`backend/app/services/url_fetcher.py`).
- Exactly one URL or raw pasted JD produces canonical Unicode text plus SHA-256
  content hash; HTML uses Trafilatura main text only; blank extraction returns
  `JD_TEXT_REQUIRED` with no browser/alternate-parser fallback
  (`backend/app/services/jd_source.py`).

Focused Batch01 verification:

```powershell
cd backend
python -m pytest -q tests/security/test_url_policy.py tests/services/test_url_fetcher.py tests/services/test_jd_source.py
python -m ruff check app/security app/services/url_fetcher.py app/services/jd_source.py tests/security tests/services/test_url_fetcher.py tests/services/test_jd_source.py
python -m mypy app/security app/services/url_fetcher.py app/services/jd_source.py
```

## Plan 5 progress (Batch02) — validated Job records and persistence

**Plan 5 Batch02 is evidence-backed.** Schema/quality/extraction tests use fakes
only (no real ShopAIKey). Repository tests use temporary SQLite only.

Batch02 turns acquired JD text into a strict grounded extraction and a durable
SQLite Job record:

- `JobPostExtraction` / `JobSkill` strict contracts reuse shared `SkillRef`
  bounds; salary remains display-only; extra fields forbidden
  (`backend/app/schemas/job_post.py`).
- Deterministic `full|partial|unscorable` quality classifier stores non-full
  reasons outside the extraction object
  (`backend/app/services/jd_quality.py`).
- Structured extraction reuses the locked ShopAIKey adapter ceilings, untrusted
  JD delimiting, evidence grounding, and contact-PII fail-closed redaction
  (`backend/app/services/jd_extraction.py`).
- Caller-owned `JobPostRepository` persists novel raw content before LLM work,
  enforces exact-hash no-insert plus normalized-key duplicate marking, independent
  status dimensions, sanitized failures, and compact bounded reads (default 10 /
  max 50) without raw content
  (`backend/app/repositories/job_posts.py`).

Focused Batch02 verification:

```powershell
cd backend
python -m pytest -q tests/schemas/test_job_post.py tests/services/test_jd_quality.py tests/services/test_jd_extraction.py tests/services/test_shopaikey_chat.py tests/services/test_pii_redaction.py
python -m pytest -q tests/repositories/test_job_posts.py tests/db/test_models.py tests/integration/test_migrations.py
python -m ruff check app/schemas/job_post.py app/services/jd_quality.py app/services/jd_extraction.py app/repositories/job_posts.py tests/schemas/test_job_post.py tests/services/test_jd_quality.py tests/services/test_jd_extraction.py tests/repositories/test_job_posts.py
python -m mypy app/schemas/job_post.py app/services/jd_quality.py app/services/jd_extraction.py app/repositories/job_posts.py
```

## Plan 5 progress (Batch03) — shared normalization and locked embeddings

**Plan 5 Batch03 is evidence-backed.** Normalization and embedding tests use
injected fakes / temporary fixtures only — zero live ShopAIKey embedding calls
for acceptance.

Batch03 reuses one Candidate/Job skill identity pipeline and adds a production
Job embedding adapter on the locked ShopAIKey contract:

- Shared `resolve_skill_ref` + Candidate path preserve exclusion semantics;
  Job adapters `normalize_job_skills` / `normalize_job_skill_lists` normalize
  nested `SkillRef`s, preserve relationship confidence/evidence, reuse existing
  canonical keys, and dedupe required/preferred lists deterministically
  (`backend/app/services/skill_normalization.py`). Production seed remains empty
  unless approved alias evidence is supplied.
- Versioned Job embedding text (`job_embedding_text_v1`) is built only from
  title, summary, responsibilities, required skills, and preferred skills —
  no E5 prefixes, salary, company/location, URL, HTML, or match features
  (`backend/app/services/embeddings.py`).
- Injectable `JobEmbeddingService` locks ShopAIKey `text-embedding-3-small` /
  1536 finite floats, batch size ≤16, stable order, one transient retry, and
  sanitized fail-closed errors. Phase 0 `benchmark_embeddings.py` reuses the
  same production contract primitives so diagnostics cannot silently diverge.

Focused Batch03 verification:

```powershell
cd backend
python -m pytest -q tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py tests/services/test_profile_extraction.py tests/graph/test_candidate_sync.py
python -m pytest -q tests/services/test_embeddings.py tests/test_embedding_benchmark.py
python -m ruff check app/services/skill_normalization.py app/services/embeddings.py evaluation/benchmark_embeddings.py tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py tests/services/test_embeddings.py tests/test_embedding_benchmark.py
python -m mypy app/services/skill_normalization.py app/services/embeddings.py
```

## Plan 5 progress (Batch04) — Agent-facing Job workflow

**Plan 5 Batch04 is evidence-backed.** Ingestion and tool tests use injected
fakes / temporary SQLite only — no public network fetches and no ShopAIKey
calls for acceptance.

Batch04 composes acquisition, extraction, normalization, quality, and
duplicate policy behind one service and two thin Agent tools:

- `JDIngestionService` is persistence-first: novel raw content commits before
  the first LLM call; exact-hash hits do zero new work; normalized duplicates
  default to ignored/`not_required`; extraction failures retain sanitized
  `failed` rows (`backend/app/services/jd_ingestion.py`).
- Active full/partial Jobs store locked embedding model/dimension identity and
  enqueue one identifier-only `upsert_job` outbox row in the same transaction;
  ignored/unscorable records never do. Vectors and Job graph projection remain
  later-batch work.
- `save_job` validates exactly one URL/raw-text input plus optional `force_new`.
  Override is authorized only from an explicit current-turn “separate position”
  / “distinct position” declaration outside the JD payload; unauthorized
  overrides fail before service mutation and emit no durable audit token
  (`backend/app/tools/save_job.py`).
- `query_jobs` supports one Job ID or bounded filters (default 10 / max 50)
  over compact repository views; it never returns raw JD content and never
  computes scores (`backend/app/tools/query_jobs.py`).
- Production registry is exactly six tools; `match_jobs` stays reserved only.
  Public application routes remain the seven authorized paths (no Job HTTP
  endpoints).

Focused Batch04 verification:

```powershell
cd backend
python -m pytest -q tests/services/test_jd_ingestion.py tests/repositories/test_job_posts.py tests/repositories/test_graph_outbox.py
python -m pytest -q tests/tools/test_save_job.py tests/tools/test_query_jobs.py tests/tools/test_registry.py tests/agent/test_graph.py tests/agent/test_prompt.py tests/api/test_chat.py
python -m ruff check app/services/jd_ingestion.py app/tools app/main.py tests/services/test_jd_ingestion.py tests/tools
python -m mypy app/services/jd_ingestion.py app/tools app/main.py
```

## Plan 5 progress (Batch05) — rebuildable Job graph projection

**Plan 5 Batch05 is evidence-backed.** Job sync and rebuild tests use injected
Neo4j/embedding fakes and temporary SQLite only — zero live Neo4j and zero
ShopAIKey calls for acceptance.

Batch05 projects identifier-only Job outbox work into Neo4j and completes the
safe rebuild pipeline for Candidate plus active/scorable Jobs:

- `process_job_sync_outbox` reloads by Job ID, embeds only active full/partial
  rows, and `MERGE`s Job/Skill/JobFamily with owned `REQUIRES`/`PREFERS`/
  `IN_FAMILY` edges (no trusted `RELATED_TO`). Payload remains
  `{"job_id"}` only (`backend/app/graph/job_sync.py`).
- Startup runs a bounded best-effort Job outbox batch after Candidate sync;
  embedding/Neo4j failure leaves canonical Job `processed` with retryable sync
  state and never continuous-polls (`backend/app/main.py`).
- Rebuild CLI stays thin: focused load/project modules reuse the online
  projector, recompute vectors, verify ID/count parity, and mark Job/outbox
  sync only after verified success (`backend/app/graph/rebuild_jobs.py`,
  `backend/app/graph/rebuild_verify.py`, `infrastructure/scripts/rebuild_graph.py`).
- Ignored duplicates and unscorable Jobs remain absent from Neo4j and from
  rebuild eligibility.

Focused Batch05 verification:

```powershell
cd backend
python -m pytest -q tests/graph/test_job_sync.py tests/integration/test_job_sync.py tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py tests/test_lifecycle.py
python -m pytest -q tests/infrastructure/test_rebuild_graph.py tests/graph/test_job_sync.py tests/graph/test_candidate_sync.py tests/integration/test_job_sync.py
python -m ruff check app/graph tests/graph tests/infrastructure/test_rebuild_graph.py ../infrastructure/scripts/rebuild_graph.py
python -m mypy app/graph
python ../infrastructure/scripts/rebuild_graph.py --help
python ../infrastructure/scripts/rebuild_graph.py
```

## Plan 5 progress (Batch06) — chat presentation and Phase 4 exit

**Plan 5 Batch06 is evidence-backed.** Saved-Job presentation reuses the existing
eight-event SSE / final-message / history seam. Phase 4 exit proof uses injected
fakes and temporary SQLite only — zero real ShopAIKey, public URL, or live Neo4j
calls for acceptance.

Batch06 delivers:

- One bounded `saved_job` card payload on `run_completed` and durable assistant
  `structured_payload` (kind, job_id, title/company/location/work mode/
  employment, quality/reasons preview, processing/duplicate/graph state,
  validated public source URL only). Raw JD and tool bodies never persist
  (`backend/app/schemas/job_tools.py`, `backend/app/services/chat_service.py`).
- Astryx `SavedJobCard` + sanitized Job tool activity labels on the existing
  `AppShell` / `ChatMessages` path (`frontend/src/features/jobs/`).
- Full fake-backed backend workflow proof: public URL and raw text, SSRF
  rejection, HTML paste-required outcome, persistence-before-extraction and
  failure retention, full/partial/unscorable, exact no-reprocess, normalized
  ignore, unauthorized/authorized `force_new` audit token, `query_jobs`,
  pending/failure/replay sync, restart recovery, and rebuild ID/count parity
  excluding ignored/unscorable (`backend/tests/integration/test_full_job_workflow.py`).
- Frontend raw-SSE → parser → reducer → shell proof for Job tool status, saved
  card, duplicate/unscorable/graph-failure outcomes, history hydration, malformed
  payload, disconnect, and duplicate events
  (`frontend/src/test/job-workflow.integration.test.tsx`).
- Production exposure remains exactly **six tools** and **seven application
  routes**; `match_jobs`, matching/ranking, and public Job CRUD stay absent.

Focused Batch06 / Phase 4 exit verification:

```powershell
cd backend
python -m ruff check app tests
python -m mypy app
python -m pytest -q
python -m pytest -q tests/integration/test_full_job_workflow.py

cd ..\frontend
npm ci --ignore-scripts
npm run check:astryx
npm run lint
npm run typecheck
npm run test -- --run
npm run test -- --run src/test/job-workflow.integration.test.tsx
npm run build

cd ..
docker compose --env-file .env.example -f infrastructure/docker-compose.yml config
docker compose --env-file .env.example -f infrastructure/docker-compose.yml build
```

Optional live Compose observation (not required; do not claim unless run with a
user-populated ignored root `.env`):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
# Then one user-observed public-URL or raw-text save/query chat flow.
```

## Plan 6 progress (Batches 01–03) — matching tool and bounded transport

**Plan 6 Batches 01–03 are evidence-backed.** Normal validation uses injected
graph/database fakes and pure inputs only — no live Neo4j, ShopAIKey, or LLM
call is required or claimed.

- Candidate vectors use a versioned, redacted representation through the locked
  embedding adapter; graph retrieval is bounded to 50 Job IDs and rechecks
  canonical SQLite eligibility before any matching work.
- Matching uses shared skill normalization with direct/verified-alias strength
  1.0, verified `RELATED_TO` strength 0.6, and fail-closed provisional or
  unverified paths. Required/preferred coverage, non-skill components, hybrid
  seed weights, missing-value renormalization, and quality multipliers are all
  deterministic and versioned.
- Results are a bounded, stable top 10 with Job-ID tie breaks, full component
  weight transparency, bounded direct/related/missing skill paths, deterministic
  explanations, and only a validated public source URL. Ranking, explanations,
  and schemas make no model calls or Job mutations.
- Production exposure remains exactly six tools and seven public application
  routes. The seventh production tool, `match_jobs`, requires an approved
  profile, bounds results to ten, retries pending graph work before retrieval,
  and stores only validated derived score details for bounded `query_jobs`
  reads.
- Validated match-results cards reuse the existing eight-event SSE, final
  assistant payload, and history seam; no route, event name, raw tool result,
  or separate transport was added. Frontend presentation, evaluation datasets,
  and tuning remain later Plan 6 batches.

Focused Batch02 verification:

```powershell
cd backend
python -m pytest -q tests/services/test_retrieval.py tests/repositories/test_job_posts.py tests/graph/test_job_sync.py
python -m pytest -q tests/services/test_skill_matching.py tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py
python -m pytest -q tests/services/test_score_components.py tests/services/test_matching.py
python -m pytest -q tests/services/test_explanations.py tests/schemas/test_matching.py
python -m ruff check app/services/retrieval.py app/services/skill_matching.py app/services/skill_match_contracts.py app/services/skill_match_evidence.py app/services/skill_match_coverage.py app/services/score_components.py app/services/matching.py app/services/matching_aggregate.py app/services/matching_rank.py app/services/explanations.py app/schemas/matching.py app/schemas/matching_result.py app/schemas/score_breakdown.py tests/services/test_retrieval.py tests/services/test_skill_matching.py tests/services/test_score_components.py tests/services/test_matching.py tests/services/test_explanations.py tests/schemas/test_matching.py
python -m mypy app/services/retrieval.py app/services/skill_matching.py app/services/skill_match_contracts.py app/services/skill_match_evidence.py app/services/skill_match_coverage.py app/services/score_components.py app/services/matching.py app/services/matching_aggregate.py app/services/matching_rank.py app/services/explanations.py app/schemas/matching.py app/schemas/matching_result.py app/schemas/score_breakdown.py
```

## Plan 6 handoff (Master Phase 5) — stable seams only

Plan 6 receives these **stable Phase 4 outputs** and must extend them rather
than re-extract JDs, invent a second skill normalization path, score
ignored/unscorable records, or make SQLite subordinate to Neo4j:

| Seam | Location / contract |
|---|---|
| Active scorable Jobs | SQLite active `full\|partial` JobPosts with validated extraction JSON, quality reasons, embedding model/dimension identity (`backend/app/repositories/job_posts.py`, `backend/app/schemas/job_post.py`) |
| Ignored / unscorable exclusion | `ignored_duplicate` and `unscorable` rows retained in SQLite but never embed, sync, or score |
| Canonical Skills | Shared Candidate/Job SkillRef pipeline + provisional/verified seed (`backend/app/services/skill_normalization.py`, `backend/app/data/skills_seed.yaml`) |
| Job vectors / graph identity | Neo4j Job/Skill/JobFamily with 1536 cosine Job vector index; MERGE by SQLite ID / canonical key; rebuild parity (`backend/app/graph/job_sync.py`, `rebuild_jobs.py`, `rebuild_verify.py`) |
| query_jobs / tool result | Bounded Agent read of compact Job views; score details only when already present (`backend/app/tools/query_jobs.py`) |
| Saved-Job card / SSE | Eight-event SSE + optional `saved_job` on final message/history (`backend/app/schemas/sse.py`, `frontend/src/features/jobs/`) |
| Six production tools | `get_candidate_context`, `propose_profile_from_cv`, `propose_profile_update`, `commit_profile_draft`, `save_job`, `query_jobs` — no `match_jobs` |
| Seven public routes | Exactly the seven application routes listed under Architecture; no public Job CRUD |
| Outbox / rebuild | Identifier-only Candidate + Job outbox; complete rebuild from SQLite |
| Profile / transport primitives | Approved profile, approval resume, one LangGraph, root `.env`, Compose, sanitized health |

Plan 6 owns retrieval, deterministic scoring, explanations, tuning, evaluation,
and top-result presentation. It must **not** re-extract JDs, create a second
normalization path, score ignored/unscorable Jobs, add public Job CRUD, invent
a ninth SSE event, or replace SQLite as the canonical store.

## Plan 5 inputs consumed (stable Phase 3 seams)

Plan 5 extended these **stable Phase 3 outputs** rather than recreating profile
approval, skill canonicalization, or alternate outbox paths:

| Seam | Location / contract |
|---|---|
| Approved singleton profile + preferences | SQLite `CandidateProfile` / `JobPreferences` via `backend/app/repositories/profiles.py`, `preferences.py`; public reads `GET /api/profile`, `GET /api/profile/cv` |
| Skill normalization | Shared provisional/verified rules + seed (`backend/app/services/skill_normalization.py`) |
| Redaction / structured extraction | Deterministic PII redaction + locked ShopAIKey structured adapter |
| Tool authorization | Application-state auth for profile commit (extended for `force_new`) |
| Outbox / Candidate graph sync | Identifier-only Candidate outbox and projector (Job path added in Plan 5) |
| Structured card / SSE seams | Eight-event SSE union + profile approval payload |
| Shared upload / shell | One multipart client; single `AppShell` chat experience |
| Public application routes | Exactly the seven routes listed under Architecture |
| Phase 2 transport primitives | One LangGraph, turn/resume idempotency, checkpoint lifecycle, Compose/config/health |

## Plan 4 handoff consumed by Phase 3 (stable Phase 2 primitives)

Plan 4 extended these **stable Phase 2 primitives** rather than recreating
alternate graphs, conversations, SSE contracts, or tool HTTP paths:

| Seam | Location / contract |
|---|---|
| Public chat endpoints | `GET /api/chat/history`, `POST /api/chat/turns`, `POST /api/chat/runs/{run_id}/resume` (`backend/app/api/chat.py`) |
| SSE event union | Eight-event validated union + order rules (`backend/app/schemas/sse.py`); frontend mirror (`frontend/src/features/chat/contracts.ts`) |
| Frontend transport / reducer / shell | `frontend/src/features/chat/{api,reducer,components}/` + `lib/sse/parser.ts` |
| One controlled LangGraph | `backend/app/agent/graph.py` — decision → `ToolNode` → iteration guard → approval interrupt → persist → checkpoint cleanup |
| Approval / idempotency | Same run/thread resume; turn + resume idempotency keys; no write replay (`ChatService`, `AgentRunRepository`) |
| Repositories | Conversation/messages, agent runs, tool executions (`backend/app/repositories/`) |
| Context assembly | Bounded recent window + attachment IDs + compact approved profile context |
| Prompt / domain redirect | System policy + untrusted document delimiters + zero-tool redirect (`backend/app/agent/prompt.py`) |
| Tool registration | Plan 4 registers exactly four Candidate tools (`backend/app/tools/registry.py`) |
| ShopAIKey adapter | Locked model/modes (`backend/app/services/shopaikey_chat.py`); normal tests use fakes |
| Compose / config | Root `.env` contract, three-service Compose, sanitized `GET /api/health` |

## Prior phase handoff consumed by Plan 3

Plan 3 reused (and did not re-benchmark) Plan 2 / Phase 0 primitives:

- Runnable frontend/backend/Neo4j Compose services and the typed root
  configuration contract (`backend/app/config.py`, root `.env` / `.env.example`).
- Async SQLite session lifecycle (`DatabaseSessionManager`) and application
  tables via Alembic (including Plan 3 run-idempotency revision).
- Contained attachment storage, Neo4j client/schema, graph outbox skeleton.
- Sanitized `GET /api/health` and the local quality/Compose commands above.
