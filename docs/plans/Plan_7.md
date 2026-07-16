# Plan 7 — Master Phase 6: Polish and Local Release

> **Numbering:** `Plan_7.md` implements **Master Plan Phase 6** and records the completed local-release baseline. The later approved Plan 8 observability increment consumes this baseline; it does not rewrite or expand Plan 7's historical scope.

## Objective

Prove and document the clean local MVP release baseline. Complete remaining unit/integration/frontend/end-to-end coverage, exercise outage/invalid/disconnect/duplicate/idempotency paths, rebuild Neo4j from a fresh volume, audit environment/secrets/data/scope, and create the root README with exact setup, commands, architecture, demo, verification, and limitations.

The completed baseline starts from a fresh clone plus one root `.env`, runs the complete demo without database edits, preserves real data outside Git, reports failures truthfully, and contains none of the Master’s excluded infrastructure or features. Plan 8 is the separately approved successor phase and owns only its read-only observability scope.

## Source of Truth

- `docs/plans/Master_plan.md` Sections 1–5: product objective, complexity guardrail, locked scope/stack, ownership, and final repository shape.
- Sections 6–21: all persisted contracts, tools/endpoints/events, UX, providers, matching, failure behavior, direct sync, and rebuild behavior to be verified rather than redesigned.
- Sections 22–23: local safeguards, loopback port publication, secret handling, and the single root environment.
- Section 24 in full: local-only unit/integration/frontend/end-to-end strategy and README command requirements.
- Section 25, “Phase 6 — Polish and local release”: final tasks and exit gate.
- Sections 26–29: delivery guardrail, Definition of Done, future work exclusions, and final narrow product statement.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| Legacy Plan 7 scope | Master Phase 6: Polish and Local Release | Preserve the historical phase scope and outputs below. | Existing Verification section and accepted evidence. |

## Prerequisites

- [ ] Plans 1–6 exit gates pass with no unresolved implementation defect.
- [ ] The six production tools, seven public endpoints, exact SSE statuses, and complete frontend demo flow exist.
- [ ] Feature-level unit/integration/frontend tests pass with fake external providers.
- [ ] ShopAIKey compatibility diagnostic passes separately with the real configured provider.
- [ ] Direct Candidate/Job graph sync and the non-provider rebuild command pass.
- [ ] Manual JD acceptance is complete and contains no unresolved false-success/ranking inconsistency.

## Scope

- Fill only missing test coverage from Master Section 24; reuse existing fixtures/fakes/helpers.
- Add one automated local end-to-end smoke test for the locked greeting → CV → approval → JD → matching sequence.
- Exercise ShopAIKey outage, Neo4j outage, invalid structured output, SSE disconnect, upload/JD duplicates, terminal resume, and every write-tool replay/idempotency path.
- Verify approval buttons and all write tools produce one durable side effect per `(run_id, tool_call_id)`.
- Verify graph rebuild on a fresh disposable Neo4j volume and revision-safe matching afterward.
- Verify a fresh-clone-style startup using the documented root `.env` and Docker Compose only.
- Audit that root `.env` is the only runtime environment file and `.env.example` is safe documentation.
- Audit tracked files/history diff for secrets, authorization headers, runtime databases, uploaded data, and real CV/JD content.
- Create root `README.md` with architecture, setup, exact single-purpose commands, demo flow, manual checklist, failure/rebuild steps, and limitations.
- Perform and record a final requirements/scope audit against Master Sections 2.2, 22, 27, and 28.
- Repair only in-scope defects discovered by these checks, preserving earlier ownership/contracts.

## Out of Scope

- New product features, tools, endpoints, schemas, tables, Agent types, infrastructure services, or architectural refactors unrelated to a verified defect.
- Authentication, multi-user/multi-conversation support, OCR/DOCX, discovery/crawling, browser automation, auto-apply, tracking, cover letters, interview preparation, or public cloud deployment.
- Qdrant, reranking, alternate embeddings/models/dimensions, Redis/Celery/Kafka/workers, outbox/queues/sync ledgers, LangSmith, or CI workflows.
- Benchmark datasets, evaluation metrics/reports, statistical weight tuning, generalized memory, production security pipelines, or production threat modeling.
- Real data committed as tests/demo assets or destructive cleanup of the developer’s normal volumes during release verification.

## Target Directory Structure

```text
JobAgent/
├── README.md
├── .env.example
├── .gitignore
├── backend/
│   └── tests/
│       ├── e2e/
│       │   └── test_demo_flow.py
│       ├── integration/         # update focused existing tests only where final matrix reveals a gap
│       └── unit/                # update focused existing tests only where final matrix reveals a gap
├── frontend/
│   └── src/test/                # update focused existing tests only where final matrix reveals a gap
├── infrastructure/
│   ├── docker-compose.yml
│   └── scripts/
│       ├── diagnose_shopaikey.py
│       └── rebuild_neo4j.py
└── docs/
    └── acceptance/
        ├── local_release_checklist.md
        └── manual_jd_checklist.md
```

Do not create a second test harness when existing fakes, fixtures, API clients, Compose services, or package scripts can cover a check. Production-file edits are allowed only for a reproduced in-scope defect and must remain in the owning focused module.

## Technical Specifications

### 7.1 Final automated coverage matrix

The final suite must prove, with existing focused tests wherever possible:

| Area | Required evidence |
|---|---|
| Pydantic/data | Exact schemas, enum/status vocabularies, UUID/UTC/singleton conventions, `ToolResult` coupling, finite embedding limits. |
| SQLite/Alembic | Fresh/initialized migration, PRAGMAs, named checks/indexes/FKs/cascades/seeds, no runtime `create_all()`, no checkpoint ownership collision. |
| Conversation/Agent | Direct general conversation without tools, SSE event order/schema, bounded context, six-tool limit, interrupt/resume, checkpoint cleanup, cursor pagination/422. |
| Idempotency | One side effect/result per repeated `(run_id, tool_call_id)`, one accepted approval decision, terminal resume no-op, exact duplicate CV/JD policies. |
| CV/Profile | PDF limits/magic/text, active/staged/failed hash reuse, draft approval/change loop, rollback-safe replacement, restart persistence, Candidate sync. |
| JD | URL/text persistence-first behavior, extraction/repair, quality, exact return/retry, locked embeddings, Job sync, raw retention on failure. |
| Matching | Revision rejection, unavailable graph, retrieval limit, all score components/renormalization/quality/ties, evidence-consistent top results. |
| Frontend | SSE reducer, exact tool statuses, history hydration/load older, approval/sidebar state, saved/match cards, error/disconnect states. |
| Rebuild | Fresh graph recreation from SQLite/stored embeddings, counts, no provider call/SQLite mutation, mismatch non-zero behavior. |

Normal automated tests must use fake ShopAIKey chat/embedding adapters and controlled HTTP/Neo4j fixtures. Only the explicit diagnostic/manual compatibility check may call the real provider.

### 7.2 End-to-end smoke contract

`backend/tests/e2e/test_demo_flow.py` runs through the public boundary with dependency-overridden fake chat/extraction/embedding adapters and disposable SQLite/files/Neo4j state:

```text
Send greeting
→ natural assistant response, no tool calls
→ continue same conversation
→ upload synthetic digital PDF
→ start attachment chat turn
→ create validated profile draft
→ receive approval_required
→ save profile through resume
→ submit synthetic JD text
→ save/extract/embed/sync Job
→ request match
→ receive ordered score and skill gaps
```

Assertions include durable messages/runs/tools, one active CV/profile, deleted draft/checkpoints, processed scorable Job, matching source revisions, exact tool statuses, terminal events, and absence of false-success text. The test must not read or mutate the developer database/volumes or call real ShopAIKey.

The manual Compose demo repeats the same user-visible sequence with the real configured provider and pinned Astryx UI.

### 7.3 Failure and recovery matrix

Record evidence in `docs/acceptance/local_release_checklist.md` for:

- ShopAIKey timeout/rate limit: one retry, durable relevant failure, truthful response.
- Invalid structured output: exactly one repair request, then safe failure.
- Neo4j unavailable during sync: SQLite commit retained, `NEO4J_SYNC_FAILED`, rebuild instruction.
- Neo4j unavailable during match: `NEO4J_UNAVAILABLE`, no partial ranking.
- Candidate/Job revision mismatch: `NEO4J_REBUILD_REQUIRED`, no matching-path repair.
- SSE/client disconnect: visible frontend state; durable run/tool truth hydrates correctly.
- Duplicate active/staged/failed CV and processed/failed JD cases: exact row/file/side-effect counts.
- Repeated Save/Request Changes and terminal resume: one accepted action, no graph/tool replay.
- Repeated every write tool identity: one stored `ToolResult` and one SQLite side effect.
- Tool loop overflow: stable controlled run failure after configured bound.

Do not add hidden model switching, unlimited retry, background recovery, or partial ranking to make a failure check pass.

### 7.4 Fresh graph and fresh-clone verification

Use a disposable Compose project/volume name, never the developer’s normal data:

1. Start SQLite/backend with seeded synthetic accepted data.
2. Start a fresh empty Neo4j volume.
3. Run the existing rebuild command.
4. Compare printed Candidate/Job/Skill/relationship counts with SQLite source records.
5. Run matching and confirm revision check passes.
6. Tear down only the explicitly named disposable release-test project/volumes.

Fresh-clone-style verification uses a clean exported checkout or separate disposable worktree, copies only `.env.example` to a new untracked root `.env`, supplies local secret values, then follows README commands without undocumented setup/database edits.

### 7.5 README contract

Root `README.md` must be sufficient for a new maintainer/agent and contain:

1. JobAgent purpose and narrow MVP scope.
2. Architecture and ownership: React/Astryx → FastAPI → one LangGraph Agent → services → SQLite source of truth / Neo4j derived index / ShopAIKey.
3. Repository layout and responsibility boundaries.
4. Prerequisites and root `.env` setup from `.env.example`.
5. Exact dependency/bootstrap and Docker Compose startup commands.
6. Exact single-purpose commands for backend lint, type-check, unit/integration/E2E tests; frontend lint/type/test/build; Neo4j integration; provider diagnostic; graph rebuild; manual JD acceptance.
7. Complete demo flow including greeting, upload, approval/change, JD URL/text, matching, and explanations.
8. Data persistence locations and safe local cleanup instructions that distinguish disposable test volumes from user data.
9. Failure/recovery behavior and the rebuild command.
10. Local-demo safeguards and explicit limitations/out-of-scope list, including no authentication/public exposure and no production security claim.
11. Testing policy: local only, synthetic committed fixtures, real data outside Git, no CI.

Commands in README must be executed verbatim during this phase. No placeholder command is permitted.

### 7.6 Environment, secret, and data audit

- Root `.env` is ignored and is the only runtime environment file.
- `.env.example` contains all and only documented variable names with safe/empty secret values; Compose must not load it as runtime configuration.
- No API keys, authorization headers, real CV/JD content, SQLite files, uploaded PDFs, Neo4j volumes/logs, or generated provider responses are tracked.
- Container services listen on `0.0.0.0` internally while all published application/Neo4j ports bind only `127.0.0.1`.
- Runtime logs and error payloads contain stable codes/safe summaries, not keys, raw documents, or stack traces exposed to the UI.

If a credential is found, stop release verification, remove it from the current diff/tracked state, rotate it outside this plan, and do not echo its value in reports.

### 7.7 Final scope audit

Search source, manifests, Compose, migrations, docs, and UI for every Master Section 2.2/27 exclusion. The final report must explicitly confirm absence of:

```text
auth/multi-user/multiple conversations/profile history
DOCX/image CV/OCR/crawler/browser automation/auto-apply/tracking
cover letters/interview prep/public cloud
Qdrant/reranking/alternate embeddings
Redis/Celery/Kafka/workers/outbox/queue/sync state machine
multiple agents/agent handoffs/64K memory/LangSmith
CI workflows/evaluation datasets or metrics/production security subsystem
```

Future-work documentation is allowed only when clearly labeled non-MVP and not implemented/configured.

## Implementation

- [ ] Re-read Master Section 24 and map each required check to an existing test; add only the missing focused cases.
- [ ] Implement the disposable full-flow E2E test using existing fakes/fixtures/API contracts.
- [ ] Execute the full failure/recovery matrix and repair reproduced in-scope defects in their owning modules.
- [ ] Verify every write tool/approval/duplicate path for one durable side effect and truthful terminal status.
- [ ] Run graph rebuild against a fresh disposable Neo4j volume, compare counts, and verify matching consistency.
- [ ] Audit environment files, Compose bindings, ignored/tracked runtime data, logs, and secret-safe payloads.
- [ ] Create the root README with every exact required command and execute each command verbatim.
- [ ] Perform a fresh-clone-style Compose startup and the manual full demo without database edits.
- [ ] Complete `local_release_checklist.md` and retain the completed manual JD checklist.
- [ ] Run the final explicit out-of-scope search/audit and remove any accidental scope expansion.
- [ ] Re-run all backend/frontend/provider-diagnostic/Compose checks after the final repair; do not claim completion from stale output.

## Verification

### Full local automated suite

```powershell
Set-Location backend
python -m ruff check .
python -m mypy app
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/e2e/test_demo_flow.py -q
```

Expected: every command exits `0`; normal tests make zero real ShopAIKey calls and use only disposable data.

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Expected: clean lockfile install and all reducer/history/profile/job/match/failure UI tests plus production build pass.

### Explicit provider and graph checks

```powershell
python infrastructure/scripts/diagnose_shopaikey.py
python infrastructure/scripts/rebuild_neo4j.py
```

Expected: provider diagnostic ends `SHOPAIKEY_COMPATIBILITY=PASS`; rebuild prints source-consistent counts, calls no provider, mutates no SQLite rows, and exits `0`.

### Compose/release checks

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build
```

Expected: only frontend/backend/Neo4j services, loopback-only published ports, healthy dependencies, persistent local data, and complete manual demo through the UI.

Run all exact README commands from the fresh-clone-style checkout. Expected: no undocumented step or manual database edit is necessary.

### Repository checks

```powershell
git status --short
git diff --check
git ls-files
```

Expected: only intended source/docs/synthetic fixtures are tracked or modified; no whitespace errors, secrets, `.env`, database, runtime upload, or real data files.

Review `docs/acceptance/local_release_checklist.md`: every item has dated PASS evidence or the release remains incomplete.

### Failure handling

- Any failed command, scope finding, secret/data finding, false-success path, or fresh-start failure blocks completion.
- Repair the root cause in the owning module and grep/search all callers before concluding the fix is safe.
- Do not weaken a test, suppress a provider/graph failure, or add excluded infrastructure to achieve PASS.

## Handoff Contract

### Consumes
- docs/plans/Master_plan.md and all completed Plans 1-6 release artifacts.

### Produces
- The documented local-release baseline and verification matrix that Plan 8 consumes as historical completion evidence; Plan 8 alone owns the approved observability increment.

### Next Consumer
Plan_8.md consumes the released baseline and must add the approved observability sidebar without reimplementing prior phases.

### Historical Completion Contract

The JobAgent MVP is complete only when all of the following are simultaneously true:

- A fresh clone plus one root `.env` starts frontend, backend, and Neo4j through documented Docker Compose commands.
- The user can converse naturally, upload one PDF CV from sidebar/chat, review/change/approve a validated profile, and retain approved corrections across restart.
- The user can save public URL/raw-text JDs with durable success/failure and exact duplicate/retry semantics.
- Scorable Jobs and the active Candidate synchronize directly to a rebuildable Neo4j index.
- Matching refuses unavailable/stale graph state and otherwise returns deterministic evidence-backed top results with skill gaps/component breakdown.
- Tool activity, approval state, stream failures, and durable history hydrate truthfully with exact status values.
- Unit, integration, frontend, E2E, provider compatibility, graph rebuild, manual JD acceptance, and full manual demo checks pass from current output.
- Real data/secrets/runtime state remain outside Git, ports remain local-only, and README limitations make no production-security claim.
- Every explicit out-of-scope item remains absent.

This historical completion evidence remains valid for the Phase 6 baseline. The approved Master Phase 7 and `Plan_8.md` are its explicit successor; no other future work may be inferred from this handoff.
