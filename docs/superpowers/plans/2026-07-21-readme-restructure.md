# JobAgent README Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the oversized chronological root README with a current, source-backed onboarding and operations guide for maintainers and AI agents.

**Architecture:** Rewrite only the repository-root `README.md`. Organize it around present-tense component ownership, end-to-end workflows, configuration, operations, validation, failure recovery, and AI-agent guidance; move detailed release history behind links into `docs/`.

**Tech Stack:** Markdown, FastAPI/Python evidence, React/Vite/TypeScript evidence, Docker Compose, SQLite, Neo4j, LangGraph, ShopAIKey, PowerShell validation.

---

### Task 1: Replace historical orientation with current architecture and workflows

**Files:**
- Modify: `README.md`
- Reference: `docs/superpowers/specs/2026-07-21-readme-restructure-design.md`
- Reference: `docs/plans/Master_plan.md`
- Reference: `docs/plans/Plan_14.md`
- Reference: `backend/app/main.py`
- Reference: `frontend/src/app/App.tsx`
- Reference: `infrastructure/docker-compose.yml`

- [ ] **Step 1: Reconfirm the current implementation boundary**

Run:

```powershell
git status --short
git log -3 --oneline
rg -n '^#|^##|^###' README.md
```

Expected: clean worktree before the README edit; the accepted Plan 14 Batch02
commit is in recent history; the old README still contains a long status history
before the operational sections.

- [ ] **Step 2: Read the authoritative current owners**

Read these files before drafting:

```text
backend/app/main.py
backend/app/core/settings.py
backend/app/api/attachments.py
backend/app/api/chat.py
backend/app/api/cvs.py
backend/app/api/jobs.py
backend/app/api/observability.py
backend/app/api/profile.py
backend/app/agent/graph.py
backend/app/agent/runner.py
backend/app/tools/registry.py
backend/app/services/chat_turns.py
backend/app/services/cv_upload.py
backend/app/services/profile_approval.py
backend/app/services/job_save_confirmation.py
backend/app/services/jd_ingestion.py
backend/app/services/job_evaluation.py
frontend/src/main.tsx
frontend/src/app/App.tsx
frontend/src/features/chat/ChatPage.tsx
frontend/src/features/profile/CvSidebar.tsx
frontend/src/features/jobs/api.ts
frontend/src/features/observability/api.ts
frontend/src/lib/api/chat.ts
infrastructure/docker-compose.yml
.env.example
```

Expected: every runtime statement used in the README is traceable to one of
these owners or to an explicitly linked plan/acceptance document.

- [ ] **Step 3: Replace the README with the approved present-tense structure**

Use this exact top-level heading order:

```markdown
# JobAgent

## Overview
## Current Baseline
## What This Repository Does
## Repository Structure
## Architecture
## Main Workflows
## Frontend
## Backend
## Data, Storage, and External Services
## Configuration
## Setup
## Running the Project
## Testing and Validation
## Failure and Recovery
## Development Notes for AI Agents
## Known Gaps and Limitations
## Documentation Map
```

Write the first nine sections with these concrete facts:

- JobAgent is a local, single-user CV/JD chat and deterministic matching MVP.
- Runtime topology is exactly frontend, backend, and Neo4j on loopback ports;
  SQLite and retained files live in the backend data volume.
- Current baseline is Plan 14 complete at commit `c8aa1da`; detailed evidence
  lives in Plan 14, task 14, and acceptance documents rather than the README.
- `backend/` owns the FastAPI API, Agent, domain services, persistence, graph,
  migrations, provider adapters, and tests.
- `frontend/` owns the React/Astryx chat, CV Manager, saved-JD, observability,
  SSE reducer, typed API clients, and tests.
- `infrastructure/` owns Compose, Dockerfiles, Neo4j seed data, provider/PDF
  diagnostics, and graph rebuild wrappers.
- `docs/` owns Master Plan, incremental plans, execution tasks, acceptance
  evidence, reviews, reports, and design specs.
- `.agent/` is workflow evidence/state and must never be staged in product
  commits.

Use this architecture flow:

```text
React/Astryx UI
  -> typed fetch/SSE clients
  -> FastAPI routes
  -> application services / Agent runner
  -> LangGraph Agent and seven tools
  -> SQLite + retained files (authoritative)
  -> Neo4j (derived/rebuildable)
  -> ShopAIKey chat and embeddings
```

Document these workflows as ordered steps with owning file links:

1. CV upload -> staged attachment -> PDF extraction/chunks -> document/profile
   draft -> confirmation interrupt -> activation -> graph projection.
2. Chat turn -> durable run/message -> SSE -> Agent/decision/ToolNode loop ->
   durable tool result -> terminal history projection.
3. Pasted JD -> semantic intent -> canonical current-message confirmation ->
   cancel or save -> exact hash dedupe -> extraction/embedding/graph sync; no
   automatic evaluation.
4. Explicit Job evaluation -> revision-keyed context -> exact Job retrieval and
   scoring -> persisted evaluation -> current/stale UI projection.
5. CV/Job deletion -> ownership or graph-first cleanup -> SQLite finalization
   with retry-safe failure behavior.
6. Observability reads and explicit Neo4j rebuild from authoritative SQLite.

- [ ] **Step 4: Check the first-half content against source ownership**

Run:

```powershell
rg -n '^## ' README.md
rg -n 'backend/|frontend/|infrastructure/|docs/' README.md
git diff -- README.md
```

Expected: all approved headings exist once, the main workflows cite concrete
owners, and the chronological Plan-by-Plan narrative is gone.

- [ ] **Step 5: Commit the architecture/workflow rewrite**

```powershell
git add README.md
git commit -m "docs: rewrite README architecture guide"
```

Expected: one commit containing only `README.md`.

### Task 2: Add source-backed configuration, operations, validation, and AI-agent guidance

**Files:**
- Modify: `README.md`
- Reference: `.env.example`
- Reference: `backend/app/core/settings.py`
- Reference: `backend/pyproject.toml`
- Reference: `frontend/package.json`
- Reference: `infrastructure/docker-compose.yml`
- Reference: `infrastructure/scripts/diagnose_shopaikey.py`
- Reference: `infrastructure/scripts/verify_pdf_extraction.py`
- Reference: `infrastructure/scripts/rebuild_neo4j.py`
- Reference: `frontend/AGENTS.md`

- [ ] **Step 1: Add the complete environment-variable table**

Document these exact variables without values:

```text
APP_ENV
FRONTEND_ORIGIN
VITE_API_BASE_URL
SQLITE_PATH
FILES_DIR
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
SHOPAIKEY_BASE_URL
SHOPAIKEY_API_KEY
LLM_MODEL
LLM_TEMPERATURE
EMBEDDING_MODEL
EMBEDDING_DIMENSIONS
MAX_PDF_SIZE_MB
MAX_PDF_PAGES
URL_FETCH_TIMEOUT_SECONDS
URL_MAX_RESPONSE_MB
TOOL_LOOP_LIMIT
CV_DOCUMENT_BATCH_MAX_CHARS
```

Use columns `Variable`, `Required`, `Purpose`, and `Evidence`. State that backend
settings load only the root `.env`, process environment wins, `.env.example` is
documentation-only, and Vite consumes `VITE_API_BASE_URL` at build time.

- [ ] **Step 2: Add exact setup and runtime commands**

Use these commands:

```powershell
Copy-Item .env.example .env
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -e .\backend
Set-Location frontend
npm ci
Set-Location ..
docker compose --env-file .env -f infrastructure/docker-compose.yml config --services
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Document confirmed endpoints and ports:

```text
Frontend: http://localhost:5173/
Backend health: http://127.0.0.1:8000/api/health
Neo4j Browser: http://127.0.0.1:7474/
Neo4j Bolt: bolt://127.0.0.1:7687
```

Do not tell users to run Alembic automatically at backend startup; migrations
are explicit and startup intentionally does not create or migrate schema.

- [ ] **Step 3: Add exact validation and diagnostic commands**

Document the full gates:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q

Set-Location ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build

Set-Location ..
python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json
& '.\.venv\Scripts\python.exe' infrastructure\scripts\verify_pdf_extraction.py
& '.\.venv\Scripts\python.exe' infrastructure\scripts\diagnose_shopaikey.py
& '.\.venv\Scripts\python.exe' infrastructure\scripts\rebuild_neo4j.py --help
```

Explain that provider diagnostics require configured live credentials; most
automated tests use fakes and synthetic fixtures. Link browser acceptance to
the relevant `docs/acceptance/` checklists instead of embedding raw data.

- [ ] **Step 4: Add failure/recovery and AI-agent rules**

Include these project-specific rules:

- SQLite and retained files are source of truth; repair Neo4j by rebuild rather
  than editing graph state as an independent authority.
- Preserve the single Agent, one decision node, one ToolNode, seven tools, and
  `TOOL_LOOP_LIMIT=6` unless the Master Plan changes.
- Keep confirmation before CV profile activation and passive JD mutation.
- Do not auto-evaluate a saved JD; evaluation is explicit and revision-keyed.
- Search for owners and callers before adding helpers; coordinate API schemas,
  frontend parsers, SSE projections, and tests when contracts change.
- Ignore generated/dependency/cache folders including `.venv/`, `node_modules/`,
  `dist/`, coverage, `__pycache__/`, and tool caches.
- Read `frontend/AGENTS.md` before frontend work and use Astryx components/tokens.
- Never stage `.agent/`, root `.env`, runtime SQLite/files, retained CV/JD data,
  provider payloads, or secrets.
- Before claiming completion, run affected focused tests plus full gates in
  proportion to the change and inspect `git diff --check`/changed paths.

List known limitations explicitly: local single-user/no auth, PDF-only/no OCR,
live ShopAIKey dependency, loopback-only Compose, synthetic acceptance data,
and derived Neo4j state.

- [ ] **Step 5: Add the documentation map**

Link these authoritative entry points with one-line purposes:

```text
docs/plans/Master_plan.md
docs/plans/Plan_14.md
docs/tasks/task_14.md
docs/acceptance/local_release_checklist.md
docs/acceptance/cv_manager_checklist.md
docs/acceptance/saved_jd_evaluation_checklist.md
docs/acceptance/full_functional_test_matrix.md
docs/acceptance/plan13_acceptance_ledger.md
docs/superpowers/specs/2026-07-21-readme-restructure-design.md
```

- [ ] **Step 6: Commit the operations and AI-agent sections**

```powershell
git add README.md
git commit -m "docs: add README operations runbook"
```

Expected: one commit containing only `README.md`.

### Task 3: Validate the rewritten README against the repository

**Files:**
- Modify only if validation finds a documentation defect: `README.md`
- Validate: `README.md`

- [ ] **Step 1: Verify every Markdown repository path exists**

Run a PowerShell check that extracts backtick-wrapped relative paths beginning
with `backend/`, `frontend/`, `infrastructure/`, or `docs/`, strips optional
line/heading suffixes, and calls `Test-Path` from the repository root.

Expected: zero missing paths. Correct any README path typo at its source.

- [ ] **Step 2: Verify command and configuration evidence**

Run:

```powershell
Get-Content backend\pyproject.toml -Raw
Get-Content frontend\package.json -Raw
docker compose --env-file .env -f infrastructure/docker-compose.yml config --services
python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json
```

Expected: Compose lists exactly `neo4j`, `backend`, and `frontend`; plan JSON is
`valid: true`; documented package commands exist in the manifests.

- [ ] **Step 3: Scan for secrets, placeholders, and stale history language**

Run:

```powershell
rg -n 'TBD|TODO|PLACEHOLDER|CHANGE_ME' README.md
rg -n '(API_KEY|PASSWORD)\s*=\s*\S+' README.md
rg -n 'Batch0[1-9].*remain next|commit-ready on worktree' README.md
```

Expected: no placeholders, no assigned secret values, and no stale release
narrative. Variable names may appear only in the configuration table or prose.

- [ ] **Step 4: Verify structure, scope, and Markdown hygiene**

Run:

```powershell
rg -n '^## ' README.md
rg -n '^## Development Notes for AI Agents$' README.md
git diff --check
git status --short
git diff --stat HEAD~2..HEAD
```

Expected: all approved top-level sections exist exactly once; the mandatory AI
agent section exists; whitespace checks pass; only `README.md` changed across
the two implementation commits.

- [ ] **Step 5: Apply only validation-driven corrections**

If Steps 1–4 find a defect, edit only the affected README line, rerun the exact
failed check, then rerun `git diff --check`. Do not expand content or alter
runtime code during this step.

- [ ] **Step 6: Commit validation corrections when needed**

If README changed after Task 2:

```powershell
git add README.md
git commit -m "docs: validate README references"
```

If no correction was needed, record that Task 3 required no additional commit.
