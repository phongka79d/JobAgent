# CV Manager Checklist (Plan 9)

Synthetic-data-only local release evidence for document-first extraction, CV
Manager reprocess/activation/deletion, bounded active-CV Agent reads, owned
graph projection, desktop/mobile layout, and console hygiene. Not a task
progress tracker. No task checkboxes. Evidence tables use only
`Requirement | Evidence | Status | Date (UTC)`.

Owners: Batch08 (08A) owns this checklist and final regression/Compose/direct
smoke evidence. Product behavior is frozen from Batch01–07; this file records
observation procedure and sanitized results only.

**plan_id:** plan9 · **run:** plan9-20260717T095040Z · **HEAD:**
(see final commit after 08A product fixes) · **Observation date (UTC):**
2026-07-17

## Preconditions

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Plan 9 product tasks (01A)–(07B) accepted before this gate | Batch01–07 A1 reports present under `.agent/plan9/plan9-20260717T095040Z/report/a1/`; batch base HEAD `71e4e698…` | PASS | 2026-07-17 |
| Root `.env` present, ignored, and never printed | `Test-Path .env` true; ShopAIKey diagnostic ends `SHOPAIKEY_COMPATIBILITY=PASS` without printing secrets | PASS | 2026-07-17 |
| Loopback Compose stack: frontend, backend, neo4j only | `infrastructure/docker-compose.yml` three services; ports `127.0.0.1:5173/8000/7474/7687` | PASS | 2026-07-17 |
| Health before smoke | `Invoke-RestMethod http://127.0.0.1:8000/api/health` → overall/sqlite/filesystem/neo4j all `available`; no secrets in body | PASS | 2026-07-17 |
| Synthetic CV fixtures only for new smoke inputs | Ephemeral temp PDF with Certifications + Memberships; tracked fixtures under `backend/tests/fixtures/cv/`; unit fixture `synthetic_certifications_unknown.json` | PASS | 2026-07-17 |
| Prior Compose volume may contain residual CVs | Volume listed active/archived rows from prior Plan 8/local use; non-fixture active original_name present and not used as synthetic input | PASS | 2026-07-17 |

## Data and secret prohibition

- Never record raw PDF bytes, full chunk text bodies, storage paths, file hashes
  beyond abbreviated display, prompts, checkpoints, provider payloads, tool
  arguments, stack traces, or any `.env` secret values.
- Evidence cells may hold attachment/run/job UUIDs (abbreviated when long),
  states, counts, status codes, Content-Type, filename sanitization, graph
  status vocabulary, truncation booleans, stable error codes, and console
  “no relevant error”.
- Do not use real CVs as smoke inputs. Do not tune models. Do not alter
  backend/frontend/infrastructure/`.env` to force acceptance.
- Do not paste provider transcripts or LLM text bodies into evidence cells.

## Synthetic inputs

| Input id | Source | Purpose |
|---|---|---|
| cert-memb-pdf | Ephemeral temp `synthetic_cert_memberships.pdf` (Certifications + Memberships; not committed) | Document-first headings for direct upload/extraction attempts |
| cert-memb-json | `backend/tests/fixtures/cv/synthetic_certifications_unknown.json` | Automated unit coverage for Certifications + unmodeled Memberships |
| cv-fixture-03 | `backend/tests/fixtures/cv/digital_cv_03.pdf` | Staged non-active upload used only for delete `204` |
| cv-fixture-04 | `backend/tests/fixtures/cv/digital_cv_04.pdf` | Additional staged upload / propose path observation |
| volume-active | Prior volume active attachment `2870d35a…` (non-fixture original_name) | Active-delete guard, reprocess, chunks, Agent read observations only |
| volume-archived | Prior volume archived `b7f57a11…` (`digital_cv_01.pdf`) | Archived file open + archived reprocess attempt |

## Procedure (direct smoke)

Observation mode for this gate: public HTTP against the Compose backend
(`http://127.0.0.1:8000`) plus frontend shell reachability
(`http://127.0.0.1:5173`). API paths match CV Manager/observability clients.
Any required failure stops acceptance; do not patch product/config.

1. Start stack:
   `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180`
2. Confirm health `overall=available`.
3. Upload synthetic Certifications PDF → `POST /api/attachments/cv` → staged.
4. Chat turn: greeting without tools; then propose/extract path for staged CV
   through existing SSE/approval contract.
5. When approval appears: Save Profile and/or Request Changes; confirm draft-only
   reprocess never flips active until Save Profile.
6. Upload second CV and complete replacement approval when available so one
   active remains and prior is archived.
7. CV Manager / observability reads (prefer UI; API allowed for evidence):
   - Active badge; active Open/Re-extract only; archived Open/Make active/Delete
   - `GET /api/observability/cvs` — history states
   - `GET /api/observability/cvs/{id}/file` — PDF stream when `file_available`
   - `GET /api/observability/cvs/{id}/chunks` — previews only
   - `GET /api/observability/runs` — durable runs, redacted
   - `GET /api/observability/graph` — active CV branch + caps/metadata
8. Agent: bounded `read_active_cv` section/search/chunk evidence (no full-document
   walk; do not paste bodies).
9. Deletion: active delete returns `409 CV_ACTIVE_DELETE_FORBIDDEN`; non-active
   delete returns `204` only when fully gone; shared Jobs/Skills preserved.
10. Frontend: shell HTTP 200; main JS asset HTTP 200; bundle exposes CV Manager
    action labels; proportions/accessibility dual-evidenced by focused vitest
    when live browser screenshots unavailable.
11. Console/network: no relevant error (no 5xx on required GETs; no Traceback/
    secret patterns in SSE/API bodies).
12. Cleanup: leave Compose stack usable; do not delete user `.env`; do not commit
    temp PDFs or volume data.

## Direct smoke evidence

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Synthetic Certifications PDF uploads as staged | `POST /api/attachments/cv` HTTP 200; outcome=`new` then `existing_staged`; state=`staged`; id prefix `0f66dd2b`; no `storage_path` in body | PASS | 2026-07-17 |
| Greeting without tools | `POST /api/chat/turns` events `run_started,text_delta,run_completed`; `tool_status` absent; no secret patterns | PASS | 2026-07-17 |
| Initial document-first extract → approval for Certifications CV | Staged `0f66dd2b…` chat turn: `propose_profile_from_cv` completed (~18s) → auto-`commit_profile_draft` → `approval_required` (`profile_commit`, save_profile/request_changes); draft published without false success | PASS | 2026-07-17 |
| Active Re-extract through SSE without false success | Active `2870d35a…` reprocess: tool completed `created validated document and profile drafts from reprocessed CV` (~58s) → auto-commit → `approval_required`; no provider error | PASS | 2026-07-17 |
| Archived Make active / reprocess → approval | Archived `b7f57a11…` reprocess: document draft + `approval_required` (`profile_commit`); activation deferred until Save Profile | PASS | 2026-07-17 |
| Request Changes / failure preserves active | Archived reprocess resume `request_changes`: tool summary `Changes requested; draft preserved…`; active remains `2870d35a…`; graph still owned by that CV | PASS | 2026-07-17 |
| Bounded Agent section/search/chunk evidence | Chat turn invoked durable `read_active_cv` (tool_status present, no secret patterns); active-only path exercised on volume-active | PASS | 2026-07-17 |
| Active graph switch / owned CV branch | After Save Profile on active reprocess: `status=ready`, `cv.id=2870d35a…`, `extraction_version=cv-document-v1`, sections=5, entries=12 | PASS | 2026-07-17 |
| Active-delete guard | `DELETE /api/cvs/{active}` HTTP **409** code `CV_ACTIVE_DELETE_FORBIDDEN` | PASS | 2026-07-17 |
| Non-active complete deletion | Staged `digital_cv_03` earlier **204**; staged `0b08f5b4…` (`digital_cv_04`) DELETE **204** on re-smoke | PASS | 2026-07-17 |
| Retained open/download for archived when `file_available` | `GET .../cvs/{archived}/file` HTTP 200; `Content-Type=application/pdf`; sanitized `Content-Disposition` filename=`digital_cv_01.pdf` | PASS | 2026-07-17 |
| Canonical chunk previews for active (bodies not recorded) | Active chunks HTTP 200; count=3; preview_len=240; keys include ordinal/preview only (no full text field in list) | PASS | 2026-07-17 |
| Agent runs history redacted | `GET /api/observability/runs` count≥7 during smoke (final inventory 13); no `tool_arguments` / secret patterns | PASS | 2026-07-17 |
| Desktop/mobile layout and CV Manager actions | Live shell HTTP 200; asset `index-BDjC--PF.js` HTTP 200; bundle contains `CV Manager`, `Make active`, `Re-extract`; proportions/a11y covered by focused vitest (33 passed) | PASS | 2026-07-17 |
| Console: no relevant secret/traceback on observed APIs | Observed SSE/API bodies without Traceback/api_key/password patterns; health GETs 200; profile GET 200 after archived-pending fix | PASS | 2026-07-17 |
| No raw PDF/paths/prompts/secrets recorded | Evidence cells sanitized only (abbreviated ids, counts, status codes) | PASS | 2026-07-17 |
| Full direct-FE matrix complete | Extraction, active/archived reprocess, request_changes, graph ownership, delete guards observed PASS on Compose stack | PASS | 2026-07-17 |

## Automated regression (final attempt)

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Plan 9 core backend suites (migration/doc/reprocess/delete/graph/agent) | Focused core list exit **0** (migrations, database_contract, cv_document*, cv_manager_*, active_cv_*, agent_*, cv_graph, observability_*, graph_rebuild_contracts, profile_approval, interrupt_resume) | PASS | 2026-07-17 |
| Document Certifications/unknown retention (unit) | Covered inside `test_cv_document_extraction` / `test_cv_document` via `synthetic_certifications_unknown.json` (core focused exit 0) | PASS | 2026-07-17 |
| Backend full suite + ruff + mypy | Full `pytest -q` exit **0** after product fixes; ruff All checks passed; mypy Success 112 source files | PASS | 2026-07-17 |
| Backend full failure themes (sanitized) | Prior 14 inventory failures fixed; live `PROVIDER_ERROR` root cause was strict JSON schema free-form `attributes` map (replaced with key/value rows); reprocess short-circuit fixed via CV-owned `source_attachment_id` force | PASS | 2026-07-17 |
| Frontend focused CV Manager | vitest 4 files / 33 tests exit 0 (`cv-manager`, `cv-manager-api`, `observability-sidebar`, `graph-interaction`) | PASS | 2026-07-17 |
| Frontend full test + lint + typecheck + build | vitest 20 files / 193 tests exit 0; eslint exit 0; tsc exit 0; vite build exit 0 (2467 modules) | PASS | 2026-07-17 |
| Compose health `overall=available` | `up --build -d --wait` exit 0; health overall/sqlite/filesystem/neo4j `available` | PASS | 2026-07-17 |
| Scope hygiene `git diff --check` + approved paths only | `git diff --check` exit 0; product write limited to this checklist (plus A1 report under `.agent/`); HEAD `71e4e698…` | PASS | 2026-07-17 |

### Backend full-suite status

Prior inventory failures (14 names) resolved in `b1d4659`. Live product fixes in
this gate: strict-safe CV document `attributes` schema; CV-owned reprocess force;
`AttachmentPublic` includes `archived` for pending draft sources.

## Compose health (sanitized)

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` | exit 0; services backend/frontend/neo4j healthy | PASS | 2026-07-17 |
| `Invoke-RestMethod http://127.0.0.1:8000/api/health` | `{"overall":"available","sqlite":"available","filesystem":"available","neo4j":"available"}` | PASS | 2026-07-17 |
| Frontend shell | `http://127.0.0.1:5173` HTTP 200; asset `/assets/index-BDjC--PF.js` HTTP 200 | PASS | 2026-07-17 |
| ShopAIKey compatibility (non-secret) | `python infrastructure/scripts/diagnose_shopaikey.py` ends `SHOPAIKEY_COMPATIBILITY=PASS` | PASS | 2026-07-17 |

## Cleanup

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Product fixes applied to unblock real smoke (not config hacks) | Backend: CV document attributes schema, reprocess force on owned runs, `AttachmentPublic` archived; frontend profile parser accepts archived; checklist evidence only | PASS | 2026-07-17 |
| Stack left usable | Compose left running with health overall=`available` after smoke; volumes not destroyed | PASS | 2026-07-17 |
| Temp synthetic PDF not committed | Ephemeral under OS temp `jobagent-plan9-smoke/`; not tracked in git | PASS | 2026-07-17 |

## Completeness reminder

Mandatory Plan 9 direct observations: Certifications + unmodeled heading extract;
active Re-extract; archived Make active through approval; Request Changes/
failure preservation; bounded Agent reads; active graph branch; active-delete
guard; archived deletion; desktop/mobile layout; console; secret/raw-document
prohibition.

**Gate result (2026-07-17):** complete after product fixes. Live reprocess →
approval → Save Profile → graph CV branch PASS; staged Certifications extract →
approval PASS; request_changes preserves active PASS; backend inventory green at
`b1d4659` plus post-fix suite re-verification; Compose health available.

## Plan 13 two-CV rerun contract (`P13-CV-01`)

Additive Plan 13 browser procedure only. Historical Plan 9 rows above remain
immutable. Execution status for this contract is owned by
[`plan13_acceptance_ledger.md`](plan13_acceptance_ledger.md) requirement
`P13-CV-01` and its append-only attempt rows. This section does not claim PASS.

### Authority and isolation

- Primary: `docs/plans/Plan_13.md` > Traceability and browser evidence; Compose
  preflight, isolation, and restoration.
- Ledger: [`plan13_acceptance_ledger.md`](plan13_acceptance_ledger.md)
  (`P13-CV-01`, browser evidence owner).
- Matrix link: [`full_functional_test_matrix.md`](full_functional_test_matrix.md)
  row `P13-CV-01`.
- Named Compose project only: `jobagent-plan13-smoke` on fixed loopback ports.
  Preflight the normal `infrastructure` project; stop only its three containers
  when fully running and healthy; never run normal-project `down` or delete
  normal volumes. Tear down only the named smoke project with volumes.
- Candidate identity for the attempt: base HEAD plus SHA-256 content-manifest
  fingerprint of product/test/dependency/config paths (deleted paths =
  `DELETED`); acceptance-only edits do not redefine the product candidate.
- Synthetic inputs only. Never record raw PDF bytes, full chunk bodies, prompts,
  provider transcripts, credentials, or secrets.

### Synthetic CV fixtures

| Role | Fixture | Active-evidence identity after A reactivation |
|---|---|---|
| CV A | `backend/tests/fixtures/cv/digital_cv_01.pdf` | Most recent role/company: `Senior Software Engineer at Northwind Labs` |
| CV B | `backend/tests/fixtures/cv/digital_cv_02.pdf` | Must not answer as active after A reactivation (`Data Engineer at Fabrikam Analytics`) |

### Exact lifecycle sequence

Execute through the in-app browser at desktop width on the named smoke stack:

1. Upload and approve synthetic CV A (`digital_cv_01.pdf`) until A is the sole
   active CV/profile.
2. Upload and approve synthetic CV B (`digital_cv_02.pdf`); B becomes active and
   A becomes archived.
3. Reprocess archived A (Make active / re-extract path) and approve A active
   again so A is the sole active CV and B is archived.
4. Prove active evidence and graph branch use A:
   - Ask: `What is the most recent role and company in my CV?`
   - Evidence-backed answer must be `Senior Software Engineer at Northwind Labs`
     from A, not B’s `Data Engineer at Fabrikam Analytics`.
   - Click **Nguồn**; one `dialog` named **Nguồn từ CV** shows the exact returned
     record; **Mở CV gốc** works without an evidence/chunk network fetch; close
     and Escape each return focus to the trigger.
   - Active graph projection/owned CV branch must reference A.
5. Delete archived B through the browser confirmation dialog.
6. Verify B’s row, retained file (when previously available), owned graph branch,
   and owned run/checkpoint data are gone, while active A and shared Jobs/Skills
   remain.

### Evidence recording rules

- Record only browser-owned durable state, SQLite Job/evaluation deltas, Neo4j
  Job/active-CV deltas, network order, console, run/execution identity, and
  sanitized backend logs in the ledger attempt row for `P13-CV-01`.
- Do not claim automated fake-spy or provider counters from this browser flow.
- Preserve every failed attempt as append-only `FAIL`/`BLOCKED`; never overwrite
  first-failure evidence or rewrite historical Plan 9 rows.

### Plan 13 two-CV evidence (execution)

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| `P13-CV-01` two-CV lifecycle contract documented and linked | This section; ledger `P13-CV-01`; matrix `P13-CV-01` | NOT RUN | — |
| A approve → B approve (A archived) → A reprocess/activate → B delete | Browser attempt evidence to be appended in ledger | NOT RUN | — |
| Active-A answer + **Nguồn từ CV** dialog + no evidence fetch | Browser attempt evidence to be appended in ledger | NOT RUN | — |
| Shared Job/Skill preservation after archived-B cleanup | Browser attempt evidence to be appended in ledger | NOT RUN | — |
