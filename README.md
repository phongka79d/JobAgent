# JobAgent

JobAgent has completed Phase 0 feasibility validation, Plan 2 / Master Phase 1
foundation work, Plan 3 / Master Phase 2 (persistent conversation over the
React–FastAPI–LangGraph–SSE path), and Plan 4 / Master Phase 3 (profile domain
through React/Astryx CV approval UI): Batch01 (profile domain and extraction
foundations), Batch02 (staged CV upload and profile proposal pipeline), Batch03
(approved profile truth, Candidate sync, production profile tools, and
profile/CV reads), and Batch04 (shared CV upload/sidebar and durable in-chat
approval). Plan 5 / Master Phase 4 is also complete: Batch01 (Job contracts and
durable input primitives), Batch02 (validated extraction, locked embeddings,
and persistence-first text/URL ingestion), Batch03 (derived graph sync,
production Job tools, live status, and rebuild), and Batch04 (durable compact
saved-job chat display). The repository contains
a pinned backend core (including Phase 2 LangGraph/LangChain pins), the complete
SQLite/Alembic source-of-truth schema,
validated chat/ToolResult/SSE contracts, message/run/tool repositories, tool
replay and history-hydration services, bounded Agent state/context with compact
approved candidate memory, a verified ShopAIKey ChatOpenAI adapter and
conversation-first prompt, one injected-registry decision/ToolNode graph with a
six-pass loop guard, request-scoped `AsyncSqliteSaver` checkpoints and Agent
runner streaming, atomic chat-turn/interrupt/resume services, thin public
history/turn/resume SSE endpoints, a typed React/Astryx conversation client
(SSE parser, single streaming reducer, history/load-older, concise tool
activity, failure states), durable compact saved-job cards, profile sidebar,
shared multipart CV upload, and restart-safe Save Profile / Request Changes
approval cards, UUID-rooted
attachment storage with bounded multipart CV staging, Neo4j foundation
primitives plus idempotent Candidate/Skill graph sync, exact Candidate Profile /
skill / preference / draft Pydantic contracts, the sole skill taxonomy loader and
normalizer, focused attachment/profile/Job repositories over the existing schema,
strict Job extraction contracts, deterministic JD quality classification,
bounded HTTP/HTTPS JD acquisition with pinned Trafilatura, fake-testable
structured JD extraction over one shared bounded provider-retry owner, one
locked ShopAIKey embedding adapter plus deterministic v1 Job text, durable
SQLite-first text/URL ingestion with exact-hash return/retry semantics, a single
production pypdf extraction and meaningful-text owner, structured CV
extraction/draft proposal and interrupt-guarded commit tools (three production
profile tools registered), constraint-safe SQLite-first approval, thin profile
and active-CV read APIs, one health API, and a three-service local Docker Compose
runtime. Plan 5 is complete through Batch04 with direct Job/Skill graph sync,
five production Agent tools with live tool status, a provider-free Neo4j rebuild
command, and restart-safe compact `save_job` results in chat. Plan 6 / Master
Phase 5 Batch01 is complete (Candidate v1 embedding text, revision consistency,
and top-50 retrieval foundations). Plan 6 Batch02 is complete: pure deterministic
skill coverage, preference components, hybrid weight renormalization with quality
multipliers, unrounded ordering, and evidence-consistent match response schemas.
Plan 6 Batch03 is complete: one read-only matching orchestrator composes those
owners in consistency-first order, and replay-safe `match_jobs` is registered as
the sixth production Agent tool. Plan 6 Batch04 is complete: durable
backend-ordered Astryx match cards with collapsible score breakdowns through the
existing chat/history truth path, plus the disposable manual JD acceptance
checklist under `docs/acceptance/manual_jd_checklist.md`. Plan 6 / Master Phase 5
is complete. Plan 7 Batch01 (focused automated contract closure) is complete:
Plan 7 matrix 7.1 and failure-recovery 7.3 automated rows for persistent data,
CV/profile, matching, frontend, conversation/Agent/SSE, JD, rebuild, and
write-tool/approval/terminal-resume idempotency map to named fake-backed tests;
coverage gaps closed under `backend/tests/**` and `frontend/src/test/**` only
(shared structured-output fake, matching/rebuild assertions, frontend
disconnect/status cases, identity replay). No product feature, schema, endpoint,
tool, or production `backend/app/**` change. Remaining Plan 7 work: Batch02
public-boundary E2E smoke, Batch03 safeguards/README release guide, Batch04
live release evidence, Batch05 final gate.

## Repository layout

- `frontend/` - React, TypeScript, Vite, and Astryx 0.1.4 application with the
  Plan 3 conversation client (chat page, SSE/API client, reducer, UI tests),
  Plan 4 profile feature (`features/profile`: typed transport, `CvSidebar`,
  `ApprovalCard`), Plan 5 saved-job feature (`features/jobs`: strict compact
  result parsing and `SavedJobCard`), Plan 6 match cards (`matchResult.ts`,
  `MatchCard`, `ScoreBreakdown` over durable `match_jobs` ToolResult data),
  shared CV attach/upload over the existing chat shell, lint, type-check, test,
  and build commands.
- `backend/` - installable pinned Python application package with one settings
  boundary, shared UUID/UTC conventions, async SQLite sessions, nine SQLAlchemy
  tables, the explicit Alembic initial migration, atomic attachment storage
  (including stream-to-temp then UUID promote), Neo4j lifecycle/schema setup,
  Candidate/Job/Skill sync, and provider-free rebuild under `app/graph/`,
  `GET /api/health`, Phase 2
  chat/tool/SSE Pydantic contracts, Plan 4 profile/skill/draft and attachment
  response contracts plus Plan 5 Job extraction and embedding contracts and Plan 6
  compact match response contracts under `app/schemas/` (`matching.py`), focused
  chat/run/tool and attachment/profile/Job repositories, history/tool
  services, skill normalizer, pure skill matching and match component/score/
  explanation owners (`skill_matching.py`, `match_components.py`,
  `match_explanations.py`), read-only matching orchestrator
  (`services/matching.py`), revision consistency and top-50 retrieval under
  `app/graph/`, deterministic JD quality classification, bounded
  URL text acquisition, structured JD extraction, deterministic embedding text
  (Job and Candidate v1), persistence-first JD ingestion, pypdf extraction, CV
  upload, profile extraction, draft proposal, and SQLite-first profile approval
  owners under `app/services/`, Agent state/context
  loader (compact approved candidate memory), ShopAIKey chat and locked embedding
  adapters, production registry of exactly six tools (three profile plus
  `save_job` / `query_jobs` / `match_jobs`) under `app/tools/`, one StateGraph factory,
  request-scoped checkpoint/runner lifecycle, chat-turn/
  resume orchestration with interrupt-guarded commit, thin public chat history/
  turn/resume routes, `POST /api/attachments/cv`, and `GET /api/profile` plus
  `GET /api/profile/cv`.
- `infrastructure/` - Docker Compose, backend/frontend Dockerfiles, retained
  local feasibility scripts, and the approved Neo4j skills taxonomy seed
  (`neo4j/skills_seed.yaml`).
- `docs/feasibility/phase_0_report.md` - reproducible compatibility evidence.

## Configuration

Keep one user-managed `.env` at the repository root. It is ignored by Git and must
not be copied into tracked files. `.env.example` documents the supported variable
names and safe defaults; secret fields are intentionally empty, and applications
must not load `.env.example` at runtime. The frontend may consume only
`VITE_API_BASE_URL`. Nested `frontend/.env` and `backend/.env` files are not used.

## Backend foundation verification

From the repository root:

```powershell
python -m pip install -e .\backend
Set-Location backend
python -m ruff check .
python -m mypy app
python -m pytest tests/unit -q
python -m pytest tests/integration -q
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

## Storage, graph, and health verification

From `backend/`:

```powershell
python -m pytest tests/unit/test_storage.py tests/unit/test_graph_setup.py -q
python -m pytest tests/integration/test_health.py -q
python -m pytest tests/integration/test_neo4j_setup.py tests/integration/test_compose_runtime.py -q
python -m ruff check app/storage app/graph app/api app/schemas/health.py app/main.py
python -m mypy app
```

Attachment paths are UUID-derived and confined beneath `FILES_DIR`; complete
writes become visible through atomic replacement. Neo4j setup owns only three
idempotent uniqueness constraints and one 1536-dimensional cosine vector index.
`GET /api/health` reports `available | unavailable` for SQLite, filesystem, and
Neo4j without exposing connection details. Public functional routes are exactly
the seven Master endpoints: health, Plan 4 `POST /api/attachments/cv`,
`GET /api/profile`, `GET /api/profile/cv`, and Plan 3 chat history/turn/resume.
Live Neo4j/Compose integration tests skip when the stack or process credentials
are unavailable.

## Neo4j graph rebuild (provider-free, choice C)

Neo4j is a derived index. After restoring Neo4j or when direct Candidate/Job
sync fails, rebuild JobAgent graph data from SQLite **stored embeddings only**.
Rebuild does **not** call ShopAIKey, does **not** re-embed, and does **not**
mutate SQLite. Before any delete it validates every processed `full|partial`
embedding against the locked model/dimensions and exact finite vector length;
mismatch exits non-zero with configuration-restoration guidance.

**Destructive boundary:** only JobAgent labels `Candidate`, `Job`, and `Skill`
(and their relationships) are cleared. There is no unrestricted
`MATCH (n) DETACH DELETE n`. Unrelated labels in the same database are
preserved. Printed relationship counts are endpoint-scoped
(`Candidate→Skill`, `Job→Skill`, `Skill→Skill`) so unrelated same-type edges
do not inflate totals.

**Exclusive runtime contract (choice C only):** rebuild is authorized only
inside the Compose backend container with `APP_ENV=local`,
`NEO4J_URI=bolt://neo4j:7687`, and `SQLITE_PATH=/data/jobagent.db`. Host
loopback Bolt targets and host-side destructive invocation are refused.

**Canonical live command** (repository root; stack already up; uses the backend
container’s authoritative `/data` SQLite volume and Compose `neo4j` service):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.graph.rebuild
```

Expected: exit `0`, printed counts for `Candidate`, `Job`, `Skill`,
`HAS_SKILL`, `REQUIRES`, `PREFERS`, and `RELATED_TO`. Failures exit non-zero.

Thin host wrapper (help/version only; never runs rebuild; no-arg exits
non-zero and prints the canonical Compose command):

```powershell
python infrastructure/scripts/rebuild_neo4j.py --help
```

Fake-backed rebuild gates (from `backend/`):

```powershell
python -m pytest tests/integration/test_graph_rebuild_contracts.py tests/integration/test_graph_rebuild_preflight.py tests/integration/test_graph_rebuild_behavior.py tests/integration/test_graph_rebuild_cli.py tests/integration/test_job_sync.py tests/integration/test_candidate_sync.py tests/unit/test_graph_setup.py -q
```

**Local-demo limitations:** single-user Compose on loopback ports; no production
auth, multi-tenant isolation, or SSRF/URL threat model. Public URL JD fetch and
provider diagnostics remain separate optional flows and are never invoked by
rebuild.

## Astryx and conversation client verification

From `frontend/`:

```powershell
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run dev -- --host 127.0.0.1
npx astryx component AppShell
npx astryx component ChatLayout
npx astryx component ChatMessage
npx astryx component ChatComposer
npx astryx component ChatToolCalls
```

The frontend talks only to FastAPI via `VITE_API_BASE_URL`, keeps streaming state
in one reducer with `event_id` deduplication, hydrates durable history as truth,
and uses pinned public Astryx chat and shell APIs (`AppShell`, `SideNav`,
`ChatComposer`, `Card`, `ButtonGroup`, and related public components). Shared
`uploadCv` stages PDFs for sidebar and composer; turns send attachment IDs only.
Active CV view/download opens `GET /api/profile/cv` by URL only. Profile-commit
interrupts render one in-chat approval card; resume uses the existing
`streamChatResume` path once per accepted action. Application run/tool statuses
remain `running|interrupted|completed|failed` and
`pending|running|completed|failed` (no `complete`/`error` aliases in client
state). Phase 0 public-component matrix evidence remains in
`docs/feasibility/phase_0_report.md`.

## Local Docker Compose

From the repository root, with a filled-in ignored root `.env` (including a real
`NEO4J_PASSWORD`):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

The isolated test project used for Phase 1 exit evidence is
`jobagent-plan2-test`:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test up --build -d
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test exec backend alembic current
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test exec backend alembic upgrade head
docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan2-test up -d --force-recreate
```

Compose runs exactly `frontend`, `backend`, and `neo4j`. Host ports are published
only on `127.0.0.1` (`5173`, `8000`, `7474`, `7687`). SQLite and files share the
application volume; Neo4j data and logs use separate volumes. Do not mount the
source tree or root `.env` into containers.

## PDF extraction verification

Production pypdf digital-text extraction, layout mode, page-count parsing, and
the meaningful-text rule live only in `backend/app/services/pdf_extraction.py`.
The Phase 0 diagnostic reuses that owner (no local threshold/marker copy). The
repository includes five synthetic digital CVs and one full-page raster-only
synthetic CV under `backend/tests/fixtures/cv/`. From the repository root:

```powershell
python infrastructure/scripts/verify_pdf_extraction.py
```

From `backend/` after editable install:

```powershell
python -m pytest tests/unit/test_pdf_extraction.py -q
```

The diagnostic runs pypdf normal and layout extraction via the production owner,
requires at least four of five digital fixtures to contain meaningful CV text,
and requires the raster-only fixture to return `NO_EXTRACTABLE_TEXT`. OCR is
intentionally unsupported.

## ShopAIKey verification

Place a valid `SHOPAIKEY_API_KEY` only in the ignored root `.env`, keep the locked
model and dimension values from `.env.example`, and run from the repository root:

```powershell
python infrastructure/scripts/diagnose_shopaikey.py
```

This command calls the real provider. It checks model discovery, chat, function
calling, the tool-result round trip, structured schema output, ordered terminal
streaming, and scalar/batch 1536-dimensional embeddings. Its embedding checks
reuse the production locked model/dimension and finite-vector validators. Output
is sanitized and must end with `SHOPAIKEY_COMPATIBILITY=PASS` before later phases
use the contract.

## Phase status

All four Phase 0 batches passed. Plan 2 / Master Phase 1 is complete: exact-pinned
backend foundation, cached root-environment settings, shared UUID/UTC helpers,
minimal neutral Astryx shell, async SQLite boundary, all nine application tables,
exact constraints/indexes/FKs, idempotent Alembic singleton seeds, atomic
attachment storage, Neo4j lifecycle/base schema, three-component health boundary,
and the loopback-bound three-service Compose runtime. Phase 0 evidence remains
recorded in `docs/feasibility/phase_0_report.md` and is not repeated.

Plan 3 / Master Phase 2 Batch01 is complete: exact Phase 2 runtime pins
(`langgraph`, `langchain`, `langchain-core`, `langchain-openai`,
`langgraph-checkpoint-sqlite`), validated chat/history/resume, `ToolResult`, and
seven-event SSE contracts; message and agent-run repositories; durable tool
transitions with exact `(run_id, tool_call_id)` replay; opaque cursor history
pagination and durable tool hydration.

Plan 3 Batch02 is complete: exact nine-field `AgentState` and prompt-budget
bounded recent-context loading; verified ShopAIKey `ChatOpenAI` adapter from
root settings (custom base URL, `gpt-4o-mini`, temperature zero, Phase 0 tool
mode) with conversation-first prompt; one injected-registry `StateGraph` with a
single decision node and one `ToolNode`, six-pass tool-loop guard, and empty
production registry (tests inject fakes only).

Plan 3 Batch03 is complete: request-scoped `AsyncSqliteSaver` on the application
SQLite file with `run_id` as `thread_id`; runner streaming of validated SSE
events and terminal per-run checkpoint cleanup; atomic chat-turn create and
terminal success/failure/interrupt services; generic interrupt/resume with
test-only synthetic tool; thin FastAPI routes `GET /api/chat/history`,
`POST /api/chat/turns`, and `POST /api/chat/runs/{run_id}/resume` with CORS
restricted to `FRONTEND_ORIGIN` for `GET`/`POST`.

Plan 3 Batch04 is complete: typed client SSE/history contracts and single
streaming reducer (`frontend/src/features/chat/`, `frontend/src/lib/api/`,
`frontend/src/lib/sse/`); base Astryx chat page under `AppShell` with history
pagination, ordered streamed text, in-flight composer lock, concise tool
activity (exact JobAgent status text), and visible failed/disconnected/interrupted
states. Plan 3 / Master Phase 2 is complete.

Plan 4 / Master Phase 3 Batch01 is complete: exact `SkillRef`, `CandidateSkill`,
experience/education/language, `CandidateProfile`, `JobPreferences`, and
`ProfileDraftPayload` contracts under `app/schemas/`; user-approved production
taxonomy at `infrastructure/neo4j/skills_seed.yaml` with one deterministic
normalizer under `app/services/skill_normalization.py`; focused attachment and
singleton profile/draft/preferences repositories (no schema migration); and one
production pypdf extraction/meaningful-text owner under
`app/services/pdf_extraction.py` shared with the Phase 0 diagnostic.

Plan 4 Batch02 is complete: bounded multipart `POST /api/attachments/cv` with
interrupt guard, MIME/`%PDF-`/size/page validation, exact-hash active/staged/
failed-retry/new lifecycle, and stream-to-temp then UUID promote storage;
structured CV extraction via locked ShopAIKey `with_structured_output` (fake-
testable, at most one schema repair and one timeout/rate retry) under
`app/services/profile_extraction.py`; singleton draft proposal orchestration
under `app/services/profile_drafts.py` (`propose_profile_from_cv` and correction-
preserving `propose_profile_update`); compact tool factories under
`app/tools/profile.py`; and `python-multipart==0.0.30` as a direct backend pin.

Plan 4 Batch03 is complete: constraint-safe SQLite-first approval under
`app/services/profile_approval.py` with post-commit best-effort old-PDF cleanup
and parameterized Candidate/Skill/seed sync under `app/graph/sync_candidate.py`;
interrupt-guarded `commit_profile_draft` over the existing replay/resume path
with production registration of exactly three profile tools; compact approved
`candidate_context` loaded into new chat turns; and thin
`GET /api/profile` / `GET /api/profile/cv` reads (no profile write CRUD).

Plan 4 Batch04 is complete: typed profile transport under
`frontend/src/features/profile/` (parsers reject storage paths), shared
`uploadCv` for sidebar and chat composer, `CvSidebar` (active filename, profile
state, upload/replace, view/download via public Astryx), composer PDF token with
attachment-ID-only turns, and durable `ApprovalCard` (Save Profile / Request
Changes) wired through ChatMessages/ChatPage with single `streamChatResume`,
composer focus on request-changes, sidebar refresh on save, and history
hydration of pending approval. Plan 4 / Master Phase 3 is complete.

Plan 5 / Master Phase 4 Batch01 is complete: strict `JobSkill` and
`JobPostExtraction` contracts; one deterministic `full|partial|unscorable`
quality owner; bounded HTTP/HTTPS text acquisition with a controlled total
timeout, streamed size cap, MIME allowlist, no redirects/cookies/auth, and the
direct `trafilatura==2.1.0` pin; plus focused flush-only `job_posts` creation,
exact-hash/ID reads, legal transitions, failed-row retry clearing, protected
temporary URL-placeholder deletion, terminal writes, and compact deterministic
queries.

Plan 5 Batch02 is complete: the profile and JD domains share one sanitized,
hard-capped provider retry/error owner while retaining separate prompts and
schema repair; structured JD extraction validates and normalizes every skill;
the sole production embedding adapter enforces `text-embedding-3-small`, 1536
finite floats, float encoding, and ordered scalar/batch results; deterministic
v1 Job text has one whitespace owner; and raw-text/URL ingestion commits input
before external work, performs exact-hash return or same-row failed retry, and
retains durable source data on later failure.

Plan 5 Batch03 is complete: scorable terminal Jobs synchronize idempotently to
derived Neo4j Job/Skill state after SQLite commits; `save_job` and `query_jobs`
bring the production registry to exactly five replay-safe tools; all five tools
publish durable post-commit `pending|running|completed|failed` status live over
the existing SSE path; and the choice-C Compose rebuild restores scoped
Candidate/Job/Skill state from stored SQLite embeddings without provider calls
or SQLite writes.

Plan 5 Batch04 is complete: durable chat history strictly retains only the
compact `save_job` result projection; terminal turns rehydrate the existing
single reducer so live and restarted conversations share one truth path; and
the public Astryx saved-job card shows truthful processing, quality, outcome,
failure, and sync-failure details without raw JD, embeddings, or ranking UI.
Plan 5 / Master Phase 4 is complete.

Plan 6 / Master Phase 5 Batch01 is complete: deterministic Candidate v1 embedding
text reuses the shared whitespace/embedding-text owner; read-only SQLite/Neo4j
revision snapshots reject unavailable or revision-inconsistent graph state; and
top-50 Job vector retrieval hydrates authoritative SQLite Job facts without a
second semantic model or reranker.

Plan 6 Batch02 is complete: pure skill coverage over non-excluded Candidate skills
with fixed strengths `1.0` (direct/canonical) / `0.6` (seed `RELATED_TO`) / `0.0`
and `0.80/0.20` renormalization; exact seniority, minimum-experience, location
(NFKC/whitespace/casefold membership), and work-mode components; hybrid base
weights (`0.30/0.40/0.10/0.10/0.05/0.05`) with unavailable-component
renormalization, full/partial quality multipliers (`1.00`/`0.85`), unrounded
four-key order, and caller limit `1..10`; plus strict `extra="forbid"` match
response schemas and a pure facts-to-explanation projector. Batch02 opens no
database or graph connections, calls no provider/LLM for scores, registers no
tools, renders no UI, and adds no score cache or ranking persistence.

Plan 6 Batch03 is complete: `app/services/matching.py` orchestrates profile
precondition, revision consistency, Candidate embed/validate, top-50 retrieval,
deterministic scoring/explanation, and top-limit projection (`1..10`, default
10); failures return zero partial results and no score cache. `app/tools/matching.py`
exposes replay-safe `match_jobs` through the existing `(run_id, tool_call_id)`
executor; `production_registry` is exactly the three profile tools, `save_job`,
`query_jobs`, then `match_jobs`. No new endpoint, SSE event/status, second
registry/executor, graph repair, or dedicated score persistence outside
`tool_executions.result_json` was added.

Plan 6 Batch04 is complete: strict frontend projection of durable `match_jobs`
`ToolResult.data` (backend `schemas/matching.py` sole JSON authority), public
Astryx `MatchCard` / collapsible `ScoreBreakdown` (≤10 cards, backend order,
display-only rounding, `safeHttpUrl`, Token skill groups), thin history and
single-assistant-host integration with friendly `Match Jobs` label, and
`docs/acceptance/manual_jd_checklist.md` with dated Master §19 observations
from isolated Compose project `jobagent-plan6-acceptance` (API-equivalent mode
labeled; no weight tuning, benchmark, or product-code changes in 04B).

## Plan 6 Batch02 scoring verification

From `backend/` after editable install (use `py -3` on hosts where `python` is
not on PATH):

```powershell
python -m pytest tests/unit/test_skill_matching.py tests/unit/test_skill_normalization.py tests/unit/test_match_components.py tests/unit/test_match_ordering.py tests/unit/test_match_explanations.py -q
python -m ruff check app/services/skill_matching.py app/services/match_components.py app/schemas/matching.py app/services/match_explanations.py tests/unit/test_skill_matching.py tests/unit/test_match_components.py tests/unit/test_match_ordering.py tests/unit/test_match_explanations.py
python -m mypy app
```

These gates exercise skill strengths and empty-list renormalization, preference
components, hybrid quality/order/limit behavior, and deterministic compact
explanations without live ShopAIKey, Neo4j, or browser calls.

## Matching orchestration and sixth tool verification (Plan 6 Batch03)

From `backend/` after editable install (use `py -3` on hosts where `python` is
not on PATH):

```powershell
python -m pytest tests/integration/test_match_revisions.py tests/integration/test_match_jobs.py -q
python -m pytest tests/integration/test_tool_replay.py tests/integration/test_agent_runner.py tests/integration/test_chat_history.py -q
python -m pytest tests/integration/test_job_tools.py tests/integration/test_interrupt_resume.py tests/integration/test_profile_approval.py tests/unit/test_agent_graph.py tests/unit/test_shopaikey_chat.py tests/unit/test_profile_extraction.py -q
python -m ruff check app/services/matching.py app/tools/matching.py app/tools/registry.py app/api/dependencies.py app/agent/graph.py app/agent/prompt.py tests/fakes/embeddings.py tests/integration/test_match_jobs.py
python -m mypy app
```

These gates use migrated temporary SQLite, the shared counting
`FakeEmbeddingClient`, and controlled Neo4j fakes. They require no live
ShopAIKey, public URL, browser, or Neo4j service for Batch03 acceptance.

## Durable match cards and manual JD acceptance (Plan 6 Batch04)

From `frontend/`:

```powershell
npm test -- --run src/test/match-card.test.tsx src/test/saved-job-card.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts src/test/approval-card.test.tsx
npm run lint
npm run typecheck
npm run build
```

These gates verify strict `match_jobs` parsing (≤10, backend order, display-only
rounding, safe/absent source URL, skill groups, unavailable components and
effective weights), exact-one terminal/history host rendering, friendly Match
Jobs label, and regression coverage for saved-job, approval, SSE, and chat page
paths. No second client store, reducer, SSE event, or API path is added.

Manual JD acceptance observations live only in
`docs/acceptance/manual_jd_checklist.md` (disposable local checklist; not a
dataset, metric, or evaluation report). Full live re-run needs a user-managed
ignored root `.env`, Docker, free loopback ports, and an isolated Compose
project such as `jobagent-plan6-acceptance` (tear down only that named project
after observations). Automated Plan 6 backend representation/skill, component/
order/explanation, and match revision/tool gates remain the fake-backed
pre-live requirements.

## Plan 3 progress and constraints

Plan 3 reuses Plan 2 foundation primitives without duplicating them:

- Settings: one cached Pydantic settings object from the root `.env` only.
- Database: async SQLAlchemy sessions, Alembic-owned schema at
  `0001_initial_schema`, PRAGMAs, and singleton seeds.
- Core helpers: lowercase UUID v4 and timezone-aware UTC helpers.
- Storage: UUID-relative paths under `FILES_DIR` with atomic write support.
- Graph: Neo4j driver lifecycle plus idempotent uniqueness constraints and the
  cosine/1536 vector index (no domain sync yet).
- API status: `GET /api/health` plus Plan 3 chat history/turn/resume; no other
  public functional routes. CORS allows only configured `FRONTEND_ORIGIN` for
  `GET` and `POST`.
- Runtime: Compose services `frontend`, `backend`, and `neo4j` on loopback ports.
- Chat persistence (Batch01): contracts under `app/schemas/`, repositories under
  `app/repositories/`, and history/tool services under `app/services/` on the
  existing conversation/run/tool tables (no schema migration).
- Agent runtime (Batch02): state/context under `app/agent/`, ShopAIKey factory
  under `app/adapters/shopaikey_chat.py`, empty `production_registry()` under
  `app/tools/`, and graph factory under `app/agent/graph.py`. Graph nodes do not
  open DB sessions, call FastAPI, or construct the provider outside the adapter.
  Normal tests use fakes only; optional live ShopAIKey smoke remains separate.
- Turn/resume transport (Batch03): checkpoint lifecycle under
  `app/agent/checkpoint.py`, runner under `app/agent/runner.py`, chat-turn
  orchestration under `app/services/chat_turns.py`, and thin routes under
  `app/api/chat.py` with dependency injection in `app/api/dependencies.py`.
  Package-owned checkpoint tables are never managed by Alembic or application
  repositories. Synthetic interrupt tools live only under `backend/tests/fakes/`.
- Conversation client (Batch04): types/history/reducer under
  `frontend/src/features/chat/`, API client under `frontend/src/lib/api/chat.ts`,
  SSE parser/stream under `frontend/src/lib/sse/`, and `ChatPage` composition
  wired into `frontend/src/app/App.tsx` via public Astryx Chat* components only.
  No second client state store, approval cards, or domain-tool UI in Plan 3.

Plan 3 must not call `create_all()`, alter status vocabulary, add independent
graph IDs, or introduce production CV/JD/matching tools without a later plan.
Schema changes require an explicit migration and Master alignment.

## Plan 4 Batch01 progress and constraints

Plan 4 Batch01 reuses Plan 2/3 primitives without duplicating them:

- Profile contracts: `app/schemas/skills.py` and `app/schemas/profile.py` own
  exact field sets, enums, confidence `[0, 1]`, and strict `extra="forbid"`.
  Later services must validate these models before any `profile_json`,
  `draft_json`, or `preferences_json` write.
- Skill taxonomy: production seed is only
  `infrastructure/neo4j/skills_seed.yaml`; tests may inject the smaller fixture
  through the same parser. One normalizer owns Unicode/whitespace/case/
  punctuation/alias resolution and unknown `canonical_key` derivation; the LLM
  never supplies aliases or relationships.
- Repositories: `app/repositories/attachments.py` and
  `app/repositories/profiles.py` are flush-only, session-caller-owned, and do
  not commit, touch filesystem/providers/Neo4j, or re-validate JSON shape.
- PDF extraction: sole quality rule and pypdf `PdfReader` usage live in
  `app/services/pdf_extraction.py`; raw extracted text remains transient
  service data (not a public API contract).
- Batch01 public surface was health plus Plan 3 chat history/turn/resume only
  (Batch02 adds CV upload; proposal tools stay unregistered).

## Plan 4 Batch02 progress and constraints

Plan 4 Batch02 reuses Batch01 contracts, repositories, PDF quality rule, and
Plan 3 interrupt/chat primitives without duplicating them:

- Upload: `app/services/cv_upload.py` and thin `app/api/attachments.py` own
  `POST /api/attachments/cv`. Guard interrupted approval before reading upload
  bytes; stream+hash into storage temp; enforce MIME, `%PDF-` magic, size, and
  page bounds before any final UUID file/row; exact-hash branches reuse or
  create staged state without deleting a different staged CV during upload.
- Extraction/proposal: `app/services/profile_extraction.py` and
  `app/services/profile_drafts.py` produce one validated
  `profile_drafts('current')` only; raw CV text is transient; failed extraction
  marks the same attachment `failed` and retains its file for retry.
- Tools: `propose_profile_from_cv` and `propose_profile_update` factories live
  under `app/tools/profile.py` and were registered in Batch03.
- Out of scope for Batch02: approval/commit, Neo4j Candidate sync, profile read
  routes, production tool registration, and frontend upload/approval UI.

## Plan 4 Batch03 progress and constraints

Plan 4 Batch03 reuses Batch02 upload/proposal primitives and Plan 3
interrupt/replay/chat transport without duplicating them:

- Approval: `app/services/profile_approval.py` validates draft/attachment/file
  outside the write unit, then commits one short SQLite transaction (active
  profile, preferences when changed, replacement ordering, draft delete, one-
  active invariant). Cleanup and Neo4j sync run only after commit; sync failure
  returns `NEO4J_SYNC_FAILED` with `sqlite_committed=true` and never rolls SQLite
  back.
- Graph sync: `app/graph/sync_candidate.py` MERGE Candidate `id='active'`, rebuilds
  this Candidate's `HAS_SKILL` for non-excluded skills only, loads approved seed
  `RELATED_TO`, and never receives raw CV text.
- Commit tool: `commit_profile_draft` interrupts before side effects; resume
  continues the same `(run_id, tool_call_id)` with `save_profile|request_changes`.
  Production registry is exactly the three profile tools (no `match_jobs`).
- Reads/memory: short-session load of compact approved profile/preferences into
  existing `candidate_context`; `app/api/profile.py` exposes metadata and active
  PDF stream only. Public surface is exactly the seven Master endpoints.
- Out of scope for Batch03: frontend upload/approval UI, profile write CRUD,
  JD/Job graph behavior, embeddings, rebuild completion, and matching tools.

## Plan 4 Batch04 progress and constraints

Plan 4 Batch04 reuses Plan 3 conversation client primitives and Batch02/03
upload/profile/resume contracts without duplicating them:

- Profile client: `frontend/src/features/profile/types.ts` and `api.ts` own
  empty/active profile parse, shared multipart `POST /api/attachments/cv`, and
  active CV URL for `GET /api/profile/cv` only (`VITE_API_BASE_URL`).
- Sidebar: `CvSidebar` composes public Astryx `SideNav`/`FileInput`/`Button` and
  shows only the four source-approved surfaces; successful sidebar upload starts
  one concise chat turn with the returned `attachment_id`.
- Chat attach: same `uploadCv`; composer shows a compact PDF token; turn body
  carries attachment IDs only; upload disabled while connecting/streaming/
  interrupted or while approval is pending.
- Approval: `ApprovalCard` uses public `Card`/`ButtonGroup`/`Button` with exact
  Save Profile / Request Changes labels and `save_profile` / `request_changes`
  resume actions once per interrupted run; stream and history hydration project
  `profile_commit` only; single `chatReducer` remains stream owner.
- Out of scope for Batch04: full profile editor, CV history/version list, raw
  PDF preview, profile write CRUD, JD/Job/match UI, second stream store, custom
  design system, and internal Astryx imports.

## Plan 5 Batch01 progress and constraints

Plan 5 Batch01 establishes Job input contracts and persistence primitives only:

- Contracts: `app/schemas/jobs.py` owns strict Job facts and reuses `SkillRef`;
  `app/services/jd_quality.py` is the sole deterministic quality classifier.
- URL acquisition: `app/services/url_fetch.py` accepts only HTTP/HTTPS HTML or
  plain text, streams within root settings, uses pinned Trafilatura for HTML,
  and returns sanitized paste-text fallbacks without browser/auth/cookie scope.
- Persistence: `app/repositories/jobs.py` is flush-only and caller-transaction-
  owned; compact queries exclude raw content, extraction bodies, hashes, and
  embeddings; deletion is limited to pristine received URL placeholders.
- Out of scope: provider extraction/repair, embeddings, end-to-end ingestion,
  Neo4j Job synchronization, production Job tools/routes, saved-job UI, and
  matching/ranking.

## Plan 5 Batch02 progress and constraints

Plan 5 Batch02 completes extraction, embeddings, and persistence-first Job
ingestion without exposing a new public route or production tool:

- Extraction: `app/services/provider_retry.py` owns the sanitized one-retry
  timeout/rate-limit policy used by profile and JD extraction; each domain keeps
  its own prompt, schema, coercion, and one-repair path. JD skills are resolved
  only through the existing `SkillNormalizer`.
- Embeddings: `app/adapters/shopaikey_embeddings.py` is the sole production
  transport; `app/schemas/embeddings.py` owns the locked model/dimension and
  finite ordered-vector contract; `app/services/embedding_text.py` owns the
  deterministic `build_job_embedding_text_v1` representation.
- Ingestion: `app/services/jd_ingestion.py` uses the database-owned
  `session_scope` with optional test injection, commits accepted text or a URL
  placeholder before external work, and reuses one downstream processor for
  exact-hash create/return/retry behavior. URL acquisition failures retain the
  placeholder and return the shared paste-text instruction.
- Out of scope: production Job tools/routes, Neo4j Job sync/rebuild, saved-job
  UI, site-specific/browser fetching, near-duplicate matching, and ranking.

## Plan 5 Batch03 progress and constraints

Plan 5 Batch03 completes derived graph projection, production Job tools, live
durable tool status, and the safe local rebuild boundary:

- Graph sync: `app/graph/sync_job.py` reuses focused shared seed/Skill
  primitives and runs only after a scorable SQLite terminal commit; sync failure
  preserves processed SQLite truth and returns `NEO4J_SYNC_FAILED`.
- Tools/status: production registration is exactly the three profile tools plus
  `save_job` and `query_jobs`. Every production tool uses the same durable
  `(run_id, tool_call_id)` execution/publication owner; live status is emitted
  only after its matching SQLite commit and carries no raw Job/profile data.
- Rebuild: focused `app/graph/rebuild*` modules preflight every stored scorable
  embedding before label-scoped deletion, reuse Candidate/Job sync, and print
  endpoint-scoped entity/relationship counts. The sole production skill seed
  remains `infrastructure/neo4j/skills_seed.yaml` and enters the backend image
  through a build-only named context.
- Runtime: destructive execution is restricted to the documented choice-C
  Compose command with `bolt://neo4j:7687` and `/data/jobagent.db`; the host
  wrapper is help/version only.
- Out of scope: public Job routes, matching/retrieval/ranking, workers/queues,
  alternate embeddings, and the Batch04 saved-job card.

## Job contracts and durable input verification (Plan 5 Batch01)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_jd_extraction.py tests/unit/test_jd_quality.py tests/unit/test_url_fetch.py -q
python -m pytest tests/integration/test_jobs_repository.py tests/unit/test_job_post_model.py -q
python -m ruff check app/schemas/jobs.py app/services/jd_quality.py app/services/url_fetch.py app/repositories/jobs.py tests/unit/test_jd_extraction.py tests/unit/test_jd_quality.py tests/unit/test_url_fetch.py tests/integration/test_jobs_repository.py
python -m mypy app
```

These tests use fake HTTP and migrated temporary SQLite databases; no live
provider, public URL, Neo4j, or browser call is required for Batch01 acceptance.

## Persistence-first Job extraction and embedding verification (Plan 5 Batch02)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_jd_extraction.py tests/unit/test_skill_normalization.py tests/unit/test_profile_extraction.py -q
python -m pytest tests/unit/test_embedding_adapter.py tests/unit/test_embedding_text.py -q
python -m pytest tests/unit/test_url_fetch.py tests/integration/test_job_ingestion.py tests/integration/test_jobs_repository.py tests/integration/test_database_pragmas.py -q
python -m ruff check app/services/provider_retry.py app/services/jd_extraction.py app/services/profile_extraction.py app/adapters/shopaikey_embeddings.py app/schemas/embeddings.py app/services/embedding_text.py app/db/session.py app/services/jd_ingestion.py tests/unit/test_jd_extraction.py tests/unit/test_profile_extraction.py tests/unit/test_embedding_adapter.py tests/unit/test_embedding_text.py tests/integration/test_job_ingestion.py tests/integration/test_database_pragmas.py
python -m mypy app
```

These gates use fake structured-output, embedding, and URL adapters plus migrated
temporary SQLite databases. They require no live provider, public URL, Neo4j,
browser, production tool registration, or public Job route.

## Derived Job graph, tools, status, and rebuild verification (Plan 5 Batch03)

From `backend/`:

```powershell
python -m pytest tests/integration/test_job_sync.py tests/integration/test_job_ingestion.py tests/integration/test_candidate_sync.py tests/unit/test_graph_setup.py -q
python -m pytest tests/integration/test_job_tools.py tests/integration/test_tool_replay.py tests/integration/test_interrupt_resume.py tests/integration/test_profile_approval.py tests/unit/test_agent_graph.py tests/unit/test_profile_extraction.py -q
python -m pytest tests/unit/test_sse_contract.py tests/integration/test_agent_runner.py tests/integration/test_chat_api.py tests/integration/test_chat_history.py -q
python -m pytest tests/integration/test_graph_rebuild_contracts.py tests/integration/test_graph_rebuild_preflight.py tests/integration/test_graph_rebuild_behavior.py tests/integration/test_graph_rebuild_cli.py tests/integration/test_compose_runtime.py tests/unit/test_skill_normalization.py -q
python -m ruff check app/graph app/tools app/services/tool_execution.py app/agent/runner.py tests/fakes/graph_rebuild.py tests/support/graph_rebuild.py tests/integration/test_graph_rebuild_contracts.py tests/integration/test_graph_rebuild_preflight.py tests/integration/test_graph_rebuild_behavior.py tests/integration/test_graph_rebuild_cli.py
python -m mypy app
```

These gates use migrated temporary SQLite and fake provider/Neo4j/tool seams.
The only required destructive live check is the explicitly authorized choice-C
command in `Neo4j graph rebuild (provider-free, choice C)` above; it targets the
local Compose stores and makes no ShopAIKey call or SQLite mutation.

## Durable saved-job chat display verification (Plan 5 Batch04)

From `frontend/`:

```powershell
npm test -- --run src/test/saved-job-card.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts src/test/approval-card.test.tsx
npm run lint
npm run typecheck
npm run build
```

From `backend/` (fake-backed durable Job tool/history contracts):

```powershell
python -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_history.py tests/integration/test_chat_api.py -q
```

These gates require no live provider, public URL, browser, or Neo4j service.
They verify strict compact result retention, exact-one terminal/restart card
rendering, truthful failure and sync-failure display, and the existing single
history/rehydrate state path.

## Profile domain and extraction foundations verification (Plan 4 Batch01)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_profile_schemas.py tests/unit/test_skill_normalization.py tests/unit/test_pdf_extraction.py -q
python -m pytest tests/integration/test_cv_api.py tests/integration/test_profile_approval.py -q
python -m ruff check app/schemas/profile.py app/schemas/skills.py app/services/skill_normalization.py app/services/pdf_extraction.py app/repositories/attachments.py app/repositories/profiles.py
python -m mypy app
```

Also reconfirm the retained Phase 0 diagnostic from the repository root:

```powershell
python infrastructure/scripts/verify_pdf_extraction.py
```

## Staged CV upload and profile proposal verification (Plan 4 Batch02)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/integration/test_cv_api.py tests/unit/test_storage.py tests/unit/test_pdf_extraction.py -q
python -m pytest tests/unit/test_profile_extraction.py tests/unit/test_profile_schemas.py tests/unit/test_skill_normalization.py tests/integration/test_profile_approval.py -q
python -m ruff check app/api/attachments.py app/schemas/attachments.py app/services/cv_upload.py app/services/profile_extraction.py app/services/profile_drafts.py app/tools/profile.py app/storage/attachments.py app/repositories/attachments.py
python -m mypy app
```

These upload and proposal tests use the temporary migrated SQLite harness and
fake structured-profile invokers. They do not require a live ShopAIKey call for
Batch02 acceptance.

## Approved profile truth, sync, and read verification (Plan 4 Batch03)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/integration/test_profile_approval.py tests/integration/test_candidate_sync.py -q
python -m pytest tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py tests/integration/test_agent_runner.py tests/integration/test_chat_api.py -q
python -m pytest tests/unit/test_agent_context.py tests/integration/test_cv_api.py -q
python -m ruff check app/services/profile_approval.py app/graph/sync_candidate.py app/tools/profile.py app/tools/registry.py app/services/tool_execution.py app/services/chat_turns.py app/agent/context.py app/agent/graph.py app/agent/runner.py app/api/profile.py app/main.py
python -m mypy app
```

These tests use temporary migrated SQLite, fakes, and injected Neo4j drivers.
Live Neo4j is optional and does not block Batch03 acceptance. Public surface is
exactly health, CV upload, profile/profile-CV reads, and the three Plan 3 chat
endpoints. At the Plan 4 gate the registry contained three profile tools; after
Plan 5 Batch03 it contained five; the current registry contains six after Plan 6
Batch03 (`match_jobs` last).

## React and Astryx CV approval workflow verification (Plan 4 Batch04)

From `frontend/`:

```powershell
npm ci
npm test -- --run src/test/approval-card.test.tsx src/test/cv-sidebar.test.tsx src/test/sse-reducer.test.ts src/test/chat-page.test.tsx
npm run lint
npm run typecheck
npm run build
```

Optional Astryx public-API discovery before UI changes:

```powershell
npx astryx build "CV sidebar upload and chat PDF attachment"
npx astryx component AppShell
npx astryx component SideNav
npx astryx component ChatComposer
npx astryx component Card
npx astryx component ButtonGroup
npx astryx component Button
```

From `backend/` (fake-backed contracts the frontend consumes; no provider call):

```powershell
python -m pytest tests/integration/test_cv_api.py tests/integration/test_chat_api.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q
```

These gates cover shared upload, sidebar lock/errors, ID-only turns, streamed and
history-hydrated approval cards, single resume under rapid click, request-change
focus, and truthful failure display. Optional full local UI smoke still needs the
user-managed ignored root `.env`, valid ShopAIKey key, Docker, and free loopback
ports.

## Durable chat contract verification (Batch01)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_tool_result.py tests/unit/test_sse_contract.py -q
python -m pytest tests/integration/test_chat_persistence.py tests/integration/test_tool_replay.py tests/integration/test_chat_history.py -q
python -m ruff check app/schemas app/repositories app/services
python -m mypy app
```

## Controlled Agent runtime verification (Batch02)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/unit/test_agent_context.py tests/unit/test_shopaikey_chat.py tests/unit/test_agent_graph.py -q
python -m ruff check app/agent app/adapters/shopaikey_chat.py app/tools tests/fakes/fake_chat_model.py tests/unit/test_agent_context.py tests/unit/test_shopaikey_chat.py tests/unit/test_agent_graph.py
python -m mypy app
```

These unit tests use fakes and make no outbound ShopAIKey network calls. Optional
live reconfirmation remains `python infrastructure/scripts/diagnose_shopaikey.py`
from the repository root with a user-managed ignored root `.env`.

## Durable turn, resume, and SSE transport verification (Batch03)

From `backend/` after `python -m pip install -e .\backend` from the repository
root:

```powershell
python -m pytest tests/integration/test_agent_runner.py -q
python -m pytest tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q
python -m pytest tests/integration/test_chat_api.py tests/integration/test_chat_history.py -q
python -m ruff check app/agent/checkpoint.py app/agent/runner.py app/services/chat_turns.py app/api/chat.py app/api/dependencies.py app/main.py tests/fakes/synthetic_tool.py tests/integration/test_agent_runner.py tests/integration/test_interrupt_resume.py tests/integration/test_chat_api.py
python -m mypy app
```

These integration tests use fakes and a temporary migrated SQLite file. They do
not call the real ShopAIKey API. Public surface is health plus the three Plan 3
chat endpoints; production tool registration remains empty.

## React and Astryx conversation client verification (Batch04)

From `frontend/`:

```powershell
npm test -- --run src/test/sse-reducer.test.ts src/test/chat-page.test.tsx
npm run lint
npm run typecheck
npm run build
```

From `backend/` (fake-backed public API/Agent path; no provider call):

```powershell
python -m pytest tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q
```

Optional local UI smoke (user-managed ignored root `.env`, valid ShopAIKey,
Docker, free loopback ports):

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d
```

Then open the frontend and send a greeting; a natural persisted answer should
stream with no tool activity. Synthetic interrupt behavior remains test-only.
