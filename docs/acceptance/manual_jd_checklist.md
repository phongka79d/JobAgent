# Manual JD Acceptance Checklist (Plan 6 / Master §19)

Disposable local observation checklist only. Not a dataset, benchmark, metric,
grid search, ablation, model-selection project, or evaluation report. No weight
tuning. Secrets and raw CV/JD bodies are not recorded.

- **Stack:** isolated Compose project `jobagent-plan6-acceptance`
- **Observation mode:** API-equivalent HTTP against isolated backend
  (`http://127.0.0.1:8000`) plus frontend reachability
  (`http://127.0.0.1:5173` HTTP 200). No browser-native UI session was used.
- **Observation date:** 2026-07-15 (UTC)
- **Profile input:** fixture CV `backend/tests/fixtures/cv/digital_cv_01.pdf`
  (Ava Synthetic / backend engineer; skills Python, TypeScript, SQL, React,
  Docker, PostgreSQL)
- **Approved profile evidence:** `GET /api/profile` after
  `propose_profile_from_cv` + `commit_profile_draft`/`save_profile`;
  attachment `35df9d96-a31c-4ed6-902b-d17f19380ea1`

## Observation table

| # | Source item | Input id (sanitized) | Result | Observed evidence (sanitized) | Date (UTC) |
|---|---|---|---|---|---|
| 1 | Public URL creates a saved job | `url:https://httpbin.org/html` (input-url-httpbin) | PASS | `save_job` ok; job_id `1642e1f4-6928-4520-8816-5e30eb7c842b`; processing_status=`processed`; jd_quality=`unscorable`; outcome=`created`; source_url retained; sqlite_committed=true | 2026-07-15 |
| 2 | Pasted text creates a saved job | `text:full-senior-backend` (input-text-full) | PASS | `save_job` ok; job_id `5417e535-0042-4f80-9d0b-ba9d8fd2f099`; title=`Senior Backend Engineer`; company=`Northwind Analytics`; processing_status=`processed`; jd_quality=`full`; outcome=`created`; sync_ok=true | 2026-07-15 |
| 3 | Full JD quality classification | input-text-full | PASS | jd_quality=`full`; summary reported as Saved job description (processed/full) | 2026-07-15 |
| 4 | Partial JD quality classification | `text:partial-python-scripts` (input-text-partial) | PASS | job_id `f836e976-ae65-48d3-bcd1-bb146ae257d5`; jd_quality=`partial`; processing_status=`processed`; outcome=`created`; title=null | 2026-07-15 |
| 5 | Unscorable JD quality classification | `text:contact-only-hr` (input-text-unscorable); also URL rows | PASS | text job_id `747c81e5-eb2e-4cd1-83ad-b9ce60124a75` jd_quality=`unscorable`; URL `https://example.com` job_id `dca14e17-c1cb-4ed8-afa4-051f778cf51e` also unscorable processed | 2026-07-15 |
| 6 | Extracted fields look reasonable | input-text-full | PASS | title/company present; location=`Remote (US)`; work_mode=`remote` (seen on match); required skills included PostgreSQL/Docker/SQL; preferred TypeScript/React; seniority/experience components later unavailable on match due empty prefs/profile seniority fields | 2026-07-15 |
| 7 | Exact duplicate returns existing non-failed Job | re-submit input-text-full | PASS | outcome=`returned`; same job_id `5417e535-0042-4f80-9d0b-ba9d8fd2f099`; summary: Returned existing job for exact content match (processed/full); no reprocess to a new id | 2026-07-15 |
| 8 | Failed exact match retries same row | `text:retry-probe` (input-text-retry-probe) | PASS | In-container production ingest with invalid key: job_id `b0ecf6b4-c7cf-47b2-bec0-dd823663231c`, outcome=`created`, processing_status=`failed`, failure_code=`PROVIDER_ERROR`. Same content with valid key: same job_id, outcome=`retried`, processing_status=`processed`, jd_quality=`partial`. Subsequent chat `save_job` same text: outcome=`returned`, same job_id. Note: chat-only under invalid key cannot invoke tools (run fails first); failed-row content retry observed via production ingest path + chat return. | 2026-07-15 |
| 9 | Matching returns plausible ordering for active profile | `match_jobs` limit=10 after rebuild | PASS | Top result Senior Backend Engineer (full, score ~0.826) above partial Python scripts (~0.762) and other scorable partials; unscorable jobs excluded from ranking set; post-rebuild count=5 ordered results | 2026-07-15 |
| 10 | Score / matched / related / missing skills / unavailable agree with profile and JD | match run `4994ba24-ce03-4eb5-a165-1d64686cdd6e` | PASS | Profile skills Python/TypeScript/SQL/React/Docker/PostgreSQL. Top job matched required PostgreSQL/Docker/SQL (direct); preferred TypeScript/React matched; missing required `Python with production FastAPI experience` (extractor key not exact `python`); related_skills empty; components seniority/experience/location/work_mode null with renormalized effective_weights on semantic+skill only; quality_multiplier=1.0 for full and 0.85 for partial — agrees with stored qualities | 2026-07-15 |
| 11 | URL failure produces documented fallback (not false success) | `url:https://this-host-does-not-exist-plan6-acceptance.invalid/jd`; `ftp://files.example.com/jd.txt`; pdf dummy URL | PASS | URL_FETCH_UNAVAILABLE / URL_UNSUPPORTED_SCHEME; ok=false; processing_status=`failed`; paste_instruction present (paste JD text); sqlite_committed=true for failed placeholders; assistant did not claim success when tool returned ok=false | 2026-07-15 |
| 12 | Extraction / provider failure produces documented fallback | invalid `SHOPAIKEY_API_KEY` override on isolated backend; also PROVIDER_ERROR ingest | PASS | Backend force-recreate with process override `invalid-plan6-acceptance` (never printed real key). Chat save/match attempts: run state=`failed`, error_code=`AGENT_EXECUTION_FAILED`, zero tool_executions (LLM+tools unavailable under invalid key). In-container text ingest under invalid key: failure_code=`PROVIDER_ERROR`, status=`failed`. No false successful ranking under outage. | 2026-07-15 |
| 13 | Provider restore recovers matching | force-recreate backend from root `.env` | PASS | After restore, health overall=`available`; `match_jobs` ok with ranked results (run `fa1b5850-843f-41b3-ae99-2fdacfebb9a5`) | 2026-07-15 |
| 14 | Neo4j unavailable during Job sync | stop isolated neo4j; save new text JD | PASS | job_id `1166b0e8-bf85-4adb-9269-e9ac4f31cb36`; sqlite_committed=true; sync_ok=false; code=`NEO4J_SYNC_FAILED`; rebuild_instruction present; processing_status=`processed` (SQLite truth kept) | 2026-07-15 |
| 15 | Neo4j unavailable during matching | match while neo4j stopped | PASS | code=`NEO4J_UNAVAILABLE`; results=[]; count=0; no partial ranking | 2026-07-15 |
| 16 | Neo4j restart then revision mismatch | start isolated neo4j; match before rebuild | PASS | code=`NEO4J_REBUILD_REQUIRED`; results=[]; rebuild_instruction includes local rebuild command; no ranking from stale graph | 2026-07-15 |
| 17 | Isolated graph rebuild then matching succeeds | `python -m app.graph.rebuild` in isolated backend | PASS | Rebuild exit 0: Candidate=1 Job=5 Skill=19 HAS_SKILL=6 REQUIRES=11 PREFERS=2 RELATED_TO=4. Subsequent `match_jobs` ok with 5 ordered results | 2026-07-15 |

## Pre-live automated gates (2026-07-15)

| Gate | Result |
|---|---|
| `backend` pytest representation/skill | PASS |
| `backend` pytest components/order/explanations | PASS |
| `backend` pytest match revisions/jobs integration | PASS |
| `frontend` match-card vitest (18 tests) | PASS |
| `frontend` typecheck | PASS |
| `frontend` production build | PASS |

## Environment / procedure notes

1. Isolated up:
   `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance up --build -d`
2. Health: `Invoke-RestMethod http://127.0.0.1:8000/api/health` → overall/sqlite/filesystem/neo4j `available` (no connection secrets in body).
3. Provider failure override (isolated backend only): process env
   `SHOPAIKEY_API_KEY=invalid-plan6-acceptance` with `--force-recreate backend`; host env var removed in `finally`.
4. Provider restore: `--force-recreate backend` from ignored root `.env` only.
5. Graph stop/start/rebuild used only project `jobagent-plan6-acceptance`.
6. Frontend shell reachable at port 5173 (HTTP 200). Match card field agreement observed via durable `tool_executions` history payloads (API-equivalent), not a browser screenshot.
7. No product code changes, no weight tuning, no secrets printed.

## Ranking / evidence notes

- Representative successful ranking is plausible for a backend-focused profile versus a senior backend full JD above thinner partial JDs.
- Display/order uses backend array order; scores left unrounded in ToolResult data.
- One normalization observation (not a formula-tuning request): JD required skill string “Python with production FastAPI experience” normalized to a non-`python` key and appears under missing_required_skills despite candidate Python skill. Ordering remained reasonable.

## Completeness reminder

Mandatory Master §19 categories covered above: URL save; pasted-text save; full; partial; unscorable; extracted fields; exact duplicate return; failed-row retry; plausible ranking; score/evidence/gap agreement; URL/extraction/provider/Neo4j failures.

---

## Plan 15 Batch04 (04B) same-candidate release evidence

Disposable sanitized observation only. Synthetic retained JD data only. No raw JD
bodies, provider payloads, secrets, SQL/Cypher, screenshots, or runtime paths.

### Attempt A1-a1 (historical — superseded by A1-a2 PASS below)

- **plan_id / run / attempt:** plan15 · plan15-20260721T130225Z · 04B A1-a1
- **Candidate HEAD:** `b98e606e4c3548db6dcf30e3c6c283ff9b67321f`
- **Uncommitted Plan 15 allowed delta (read-only for 04B product code):** `README.md` (04A), `infrastructure/scripts/diagnose_jd_extraction.py` (04A); 04B product edit is this checklist append only
- **Observation date (UTC):** 2026-07-21
- **Stack:** normal three-service Compose (`infrastructure/docker-compose.yml`) rebuild + wait; health overall/sqlite/filesystem/neo4j all `available`
- **Browser origin:** `http://localhost:5173/` (CORS-aligned with built `VITE_API_BASE_URL`); synthetic job id prefix `b62f6f20…`
- **Overall gate result:** **BLOCKED / incomplete release** — full backend `pytest -q` failed (18 tests); repair is outside 04B docs-only scope

### Automated and live gates (same candidate)

| Gate | Result | Sanitized evidence |
|---|---|---|
| Focused backend Plan 15 pytest subset | PASS | exit 0 (all selected unit/integration dots green) |
| Backend ruff | PASS | exit 0; All checks passed |
| Backend mypy | PASS | exit 0; Success: no issues found in 127 source files |
| Full backend pytest | **FAIL** | exit 1; 18 failed (route allowlists missing `POST /api/jobs/{job_id}/reextract`; `test_job_tools` / e2e demo FakeJdInvoker payloads ungrounded under semantic guard → PROVIDER_ERROR / call-count mismatch) |
| Focused frontend saved-JD vitest | PASS | 4 files / 57 tests passed |
| Full frontend vitest | PASS | 27 files / 332 tests passed |
| Frontend lint / typecheck / build | PASS | all exit 0 |
| Plan structure Plans 1–15 | PASS | `valid: true`, contiguous Plan_1…Plan_15, no errors |
| Live synthetic JD diagnostic (04A) | PASS | exit 0; live_case_count=3; en_sectioned_atomic/vi_one_line_nfkc/en_contact_only PASS; JD_EXTRACTION_DIAGNOSTIC=PASS; no source/provider/secret print |
| Docker Compose build/start/health | PASS | `up --build -d --wait --wait-timeout 180` exit 0; `/api/health` overall/sqlite/filesystem/neo4j=`available` |
| Scope hygiene (04B product edit) | PASS for 04B owner | this file only for 04B; combined tree still carries 04A diagnostic+README and orchestrator checkbox on `docs/tasks/task_15.md` (not edited by 04B) |

### Browser re-extraction success (synthetic retained Job)

| Observation | Result | Sanitized evidence |
|---|---|---|
| Shell + Saved JDs tab | PASS | `http://localhost:5173/`; tab `jobagent-obs-tab-saved-jobs` |
| Extraction groups visible | PASS | metadata, responsibilities, required/preferred skills, evidence, source, evaluation all present |
| Confirm **Re-extract JD** once | PASS | dialog open → confirm; `POST /api/jobs/{id}/reextract` HTTP 200; dialog closed |
| Stable Job identity / source type | PASS | same Job id prefix `b62f6f20…`; `source_type=text` retained |
| Refreshed detail + stale evaluation | PASS | pre eval=`current` / no stale banner → post eval=`stale` + stale banner; extraction confidence refreshed (0.95→0.9); detail remains |
| No evaluate side effect | PASS | zero `POST …/evaluate` network calls on success path |
| Graph / rebuild | PASS | success path `sync_ok` implied by healthy reextract HTTP 200 without rebuild banner; Compose neo4j available |
| Console / privacy | PASS | no secret/raw-JD console dumps; no Traceback observed on success path |

### Controlled pre-commit failure browser check

| Observation | Result | Sanitized evidence |
|---|---|---|
| Controlled pre-commit seam | PASS | Playwright route fulfill `POST …/reextract` → HTTP 502 `detail.code=PROVIDER_ERROR` (synthetic summary only) |
| Dialog unlock / action re-enabled | PASS | dialog closed; re-extract control enabled after failure |
| Prior detail/evaluation preserved | PASS | detail present; source length unchanged; stale banner state unchanged |
| Safe error visible | PASS | action error surface + expected 502 console resource status only |
| No optimistic graph/evaluate | PASS | zero evaluate POSTs; no graph mutation call observed |

### Repair routing (not executed in 04B)

1. **Public route allowlists** (`backend/tests/integration/test_chat_api.py`, `test_health.py`, `test_cv_api.py` and related source-tree route scanners): add exact `POST /api/jobs/{job_id}/reextract` after Plan 15 02B API. Owner: post-02B allowlist repair (outside 04B).
2. **Agent save_job fakes** (`backend/tests/integration/test_job_tools.py`, e2e demo flow FakeJdInvoker payloads): ground title/company/responsibilities/skills/location evidence to the fixture JD text (same hygiene already applied in `test_saved_jobs_api.py`). Owner: post-01B guard regression in job-tool tests (outside 04B).

After those repairs on an unchanged product candidate, re-run full backend pytest then re-execute 04B gates and replace/amend this evidence row with a full PASS release entry.

### Attempt A1-a2 (authoritative release — supersedes A1-a1)

- **plan_id / run / attempt:** plan15 · plan15-20260721T130225Z · 04B A1-a2
- **Candidate HEAD:** `b98e606e4c3548db6dcf30e3c6c283ff9b67321f`
- **Uncommitted Plan 15 candidate delta (read-only for 04B except this checklist):** `README.md` + `infrastructure/scripts/diagnose_jd_extraction.py` (04A); orchestrator-applied test hygiene (`backend/tests/integration/test_chat_api.py`, `test_health.py`, `test_cv_api.py`, `test_job_tools.py`, `backend/tests/e2e/test_demo_flow.py`); `docs/tasks/task_15.md` orchestrator checkbox (not edited by 04B)
- **Observation date (UTC):** 2026-07-21
- **Stack:** normal three-service Compose (`infrastructure/docker-compose.yml`) `up --build -d --wait --wait-timeout 180`; health overall/sqlite/filesystem/neo4j all `available`
- **Browser origin:** `http://localhost:5173/`; synthetic job id prefix `b62f6f20…` (retained text JD with current evaluation before success path)
- **Overall gate result:** **PASS / complete same-candidate release** — every required automated, live-provider, Docker, browser success/failure, privacy, and scope gate green on this candidate

#### Automated and live gates (same candidate, fresh A1-a2)

| Gate | Result | Sanitized evidence |
|---|---|---|
| Focused backend Plan 15 pytest subset | PASS | exit 0; all selected unit/integration tests green |
| Backend ruff | PASS | exit 0; All checks passed |
| Backend mypy | PASS | exit 0; Success: no issues found in 127 source files |
| Full backend pytest | PASS | exit 0; full suite green (hygiene applied in worktree; no product edit by 04B) |
| Focused frontend saved-JD vitest | PASS | 4 files / 57 tests passed |
| Full frontend vitest | PASS | 27 files / 332 tests passed |
| Frontend lint / typecheck / build | PASS | all exit 0 |
| Plan structure Plans 1–15 | PASS | `valid: true`, contiguous Plan_1…Plan_15, `errors: []` |
| Live synthetic JD diagnostic (04A) | PASS | exit 0; live_case_count=3; en_sectioned_atomic/vi_one_line_nfkc/en_contact_only PASS; JD_EXTRACTION_DIAGNOSTIC=PASS; no source/provider/secret print |
| Docker Compose build/start/health | PASS | compose exit 0; `/api/health` overall/sqlite/filesystem/neo4j=`available` |
| Scope hygiene (04B product edit) | PASS for 04B owner | 04B writes only this checklist; combined tree retains 04A diagnostic+README, orchestrator test hygiene, and task checkbox (not product repairs by 04B) |

#### Browser re-extraction success (synthetic retained Job)

| Observation | Result | Sanitized evidence |
|---|---|---|
| Shell + Saved JDs tab | PASS | `http://localhost:5173/`; tab `jobagent-obs-tab-saved-jobs` |
| Extraction groups visible | PASS | extraction, metadata, responsibilities, required/preferred skills, evidence, source, evaluation all present |
| Confirm **Re-extract JD** once | PASS | dialog open → confirm; `POST /api/jobs/{id}/reextract` HTTP 200; dialog closed; 1 success reextract POST |
| Stable Job identity / source type | PASS | same Job id prefix `b62f6f20…`; `source_type=text` retained; source length unchanged |
| Refreshed detail + stale evaluation | PASS | pre: no stale banner (current eval) → post: stale banner present; detail remains |
| No evaluate side effect | PASS | zero `POST …/evaluate` network calls on success path |
| Graph / rebuild | PASS | reextract HTTP 200 without rebuild/error surface; Compose neo4j available |
| Console / privacy | PASS | no secret/raw-JD/traceback console dumps on success path |

#### Controlled pre-commit failure browser check

| Observation | Result | Sanitized evidence |
|---|---|---|
| Controlled pre-commit seam | PASS | Playwright route fulfill `POST …/reextract` → HTTP 502 `detail.code=PROVIDER_ERROR` (synthetic summary only) |
| Dialog unlock / action re-enabled | PASS | dialog closed; re-extract control enabled after failure |
| Prior detail/evaluation preserved | PASS | detail present; source length unchanged; stale banner state unchanged |
| Safe error visible | PASS | action error surface shows safe PROVIDER_ERROR summary; console only expected 502 resource status |
| No optimistic graph/evaluate | PASS | zero evaluate POSTs; no graph mutation call observed |

#### Notes

- Residual live-provider variance remains possible on reextract; A1-a2 success path used one retained synthetic job after ensuring evaluation current.
- A1-a1 full-pytest red was resolved outside 04B via orchestrator test-only hygiene already present in the worktree; 04B re-verified full matrix freshly and did not edit tests/product.
