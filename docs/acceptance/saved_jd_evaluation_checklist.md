# Saved JD Evaluation Checklist (Plan 10)

Synthetic-data-only local release evidence for zero-result chat recovery,
source-bound save-and-evaluate, revision-keyed current/stale evaluation,
exact Job deletion preservation, desktop/mobile layout, and console hygiene.
Not a task progress tracker. No task checkboxes. Evidence tables use only
`Requirement | Evidence | Status | Date (UTC)`.

Owners: Batch08 (08A) owns this checklist and final regression/Compose/direct
smoke evidence. Product behavior is frozen from Batch01–07; this file records
observation procedure and sanitized results only.

**plan_id:** plan10 · **run:** plan10-20260718T010917Z · **HEAD:**
`e429c1033202b22555f77c4f0f390a42e874e5d1` · **Observation date (UTC):**
2026-07-18

## Preconditions

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Plan 10 product tasks (01A)–(07A) accepted before this gate | Batch01–07 product on HEAD `e429c10` (allowlists include five `/api/jobs*` routes); prior Batch08 a1 blocked only on stale allowlists now fixed | PASS | 2026-07-18 |
| Root `.env` present, ignored, and never printed | `Test-Path .env` true; values not echoed in this checklist or A1 report | PASS | 2026-07-18 |
| Loopback Compose stack: frontend, backend, neo4j only | `infrastructure/docker-compose.yml` three services; ports `127.0.0.1:5173/8000/7474/7687`; all healthy | PASS | 2026-07-18 |
| Health before smoke | `Invoke-RestMethod http://127.0.0.1:8000/api/health` → overall/sqlite/filesystem/neo4j all `available`; no secrets in body | PASS | 2026-07-18 |
| Synthetic CV/JD fixtures only for new smoke inputs | Tracked PDFs under `backend/tests/fixtures/cv/` (`digital_cv_02`…`05` used); synthetic flamingo/quantum JD text only; residual volume active name observed but not used as new synthetic input | PASS | 2026-07-18 |

## Data and secret prohibition

- Never record raw PDF bytes, full JD/CV bodies, storage paths, file hashes
  beyond abbreviated display, prompts, checkpoints, provider payloads, tool
  arguments, stack traces, SQL/Cypher, or any `.env` secret values.
- Evidence cells may hold abbreviated UUIDs, states (`none|current|stale`),
  outcome codes (`created|reused|unavailable|existing`), HTTP status codes,
  counts, Content-Type, stable error codes, and console “no relevant error”.
- Do not use real CVs/JDs as smoke inputs. Do not tune models. Do not alter
  backend/frontend/infrastructure/`.env` to force acceptance.
- Do not paste provider transcripts or LLM text bodies into evidence cells.

## Synthetic inputs

| Input id | Source | Purpose |
|---|---|---|
| cv-fixture-02 | `backend/tests/fixtures/cv/digital_cv_02.pdf` | Approved activation via archived reprocess to force evaluation-context stale |
| cv-fixture-03..05 | `backend/tests/fixtures/cv/digital_cv_03.pdf` … `05` | Staged synthetic uploads (inventory); not required for final delete path |
| residual-volume-active | Prior volume active attachment `2870d35a…` (non-fixture original_name) | Pre-smoke active profile only; not a new synthetic input |
| synth-jd-zero | Ephemeral synthetic “Quantum Flamingo Trainer” JD text (not committed) | Live `match_jobs` count=0 source for save-and-evaluate binding |

## Procedure (direct smoke)

Observation mode for this gate: public HTTP against the Compose backend
(`http://127.0.0.1:8000`) plus frontend shell reachability
(`http://127.0.0.1:5173`). API paths match chat, CV Manager, and saved-JD
clients. Desktop/mobile a11y dual-evidenced by focused vitest when live
browser screenshots are unavailable. Any required failure stops acceptance;
do not patch product/config.

1. Start stack:
   `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180`
2. Confirm health `overall=available`.
3. Greeting turn without tools (`POST /api/chat/turns`).
4. Synthetic JD chat turn that completes with durable `match_jobs` `ok` and
   `count=0` (zero-result recovery precondition).
5. Negative control: `POST /api/jobs/save-and-evaluate` with random UUID →
   `JD_SOURCE_NOT_RECOVERABLE`.
6. One-click recovery equivalent: `POST /api/jobs/save-and-evaluate` with the
   durable initiating `source_message_id` only (no replacement text).
7. `GET /api/jobs` and `GET /api/jobs/{job_id}` — compact redacted list/detail
   with `evaluation_state=current` and latest score present.
8. Same-context `POST /api/jobs/{job_id}/evaluate` twice → `outcome=reused`,
   state remains `current` (no false re-score requirement).
9. Activate approved different synthetic CV (`digital_cv_02` reprocess →
   `save_profile`) without calling evaluate → list/detail show `stale`
   (`Cần đánh giá lại` UI contract dual-evidenced by vitest + API state).
10. Explicit `POST /api/jobs/{job_id}/evaluate` → `outcome=created` then second
    call `reused` with `current`.
11. `DELETE /api/jobs/{job_id}` → `204`; detail/list gone; repeat delete
    `JOB_NOT_FOUND`; profile/CV and shared graph edges preserved.
12. Frontend: shell HTTP 200; main JS asset HTTP 200; bundle exposes saved-JD
    Vietnamese labels; proportions/a11y dual-evidenced by focused vitest.
13. Console/network: no relevant error (no Traceback/secret patterns on observed
    SSE/API bodies; health GETs 200).
14. Cleanup: leave Compose stack usable; do not delete user `.env`; do not commit
    volume data or temp JD text.

## Direct smoke evidence

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Greeting without tools | `POST /api/chat/turns` status 200; SSE `run_started`…`run_completed`; `tool_status` absent; no secret patterns | PASS | 2026-07-18 |
| Successful zero-result `match_jobs` (recovery precondition) | History user `54b9c4de…` run `completed`; tool `match_jobs` status `completed` ok=true count=0; no secret patterns | PASS | 2026-07-18 |
| Source binding rejects unbound id | Random UUID `POST /api/jobs/save-and-evaluate` → detail code `JD_SOURCE_NOT_RECOVERABLE` | PASS | 2026-07-18 |
| One-click save-and-evaluate from initiating message | `source_message_id=54b9c4de…` → HTTP 200; `ingest_outcome=created`; `evaluation_outcome=created`; job `56e5bc2c…`; evaluation_state=`current`; no `raw_content`/secrets in body | PASS | 2026-07-18 |
| List/detail redaction + current state | `GET /api/jobs` count=1 state=`current`; detail latest evaluation present with score; bodies omit `raw_content`/embedding fields | PASS | 2026-07-18 |
| Same-context reuse (no re-score outcome) | Two `POST /api/jobs/{id}/evaluate` → both `outcome=reused` state=`current` | PASS | 2026-07-18 |
| CV/context change marks stale without auto recompute | Archived `digital_cv_02` reprocess → approval → `save_profile`; active becomes fixture `digital_cv_02.pdf`; job list/detail `evaluation_state=stale` with no evaluate call in between | PASS | 2026-07-18 |
| Explicit re-evaluate after stale | `POST evaluate` → `outcome=created` state=`current`; immediate second call `outcome=reused` state=`current` | PASS | 2026-07-18 |
| Complete Job delete + preservation | `DELETE` HTTP **204**; subsequent GET/DELETE → `JOB_NOT_FOUND`; list count=0; profile still present active=`digital_cv_02.pdf`; graph remained `ready` (edges 19→16; shared residual edges preserved) | PASS | 2026-07-18 |
| Zero-result / saved-JD UI copy and tab order | Live shell HTTP 200; asset `/assets/index-CLpt-Tsf.js` HTTP 200 (652783 bytes); bundle contains `JD đã lưu`, `Chưa có kết quả đánh giá`, `Lưu JD & đánh giá lại`, `Cần đánh giá lại`, `Đánh giá lại`, `Đánh giá với CV`, `Xoá JD`, `Agent runs`; vitest navigation/panel/empty-card suites green | PASS | 2026-07-18 |
| Desktop/mobile layout and a11y | Dual evidence: (1) focused vitest `observability-navigation` / `saved-jobs-panel` / `empty-match-card` (desktop proportions, mobile drawer, labels, delete confirmation); (2) live FE shell+asset 200 on Compose `5173` | PASS | 2026-07-18 |
| Console/network: no relevant secret/traceback | Observed health/list/detail/evaluate/delete/SSE bodies without Traceback/api_key/password patterns; required GETs 200; delete 204 | PASS | 2026-07-18 |
| No raw CV/JD/paths/prompts/secrets recorded | Evidence cells sanitized only (abbreviated ids, outcomes, counts, status codes) | PASS | 2026-07-18 |

## Automated regression (final attempt)

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Backend ruff | `Set-Location backend; py -3.13 -m ruff check app tests --no-cache` → `All checks passed!`; exit 0 | PASS | 2026-07-18 |
| Backend mypy | `py -3.13 -m mypy app --no-incremental` → `Success: no issues found in 124 source files`; exit 0 | PASS | 2026-07-18 |
| Backend full suite | `py -3.13 -m pytest -q` exit 0 (all green; optional skips only; no real ShopAIKey required by suite) | PASS | 2026-07-18 |
| Frontend full test | `Set-Location frontend; npm test -- --run` exit 0; 24 files / 240 tests | PASS | 2026-07-18 |
| Frontend lint + typecheck + build | `npm run lint` exit 0; `npm run typecheck` exit 0; `npm run build` exit 0; vite 2475 modules; asset `index-BHqPCu2-.js` (host build) | PASS | 2026-07-18 |
| Plan structure validator | `python …/validate_plan_structure.py docs/plans --json` → `valid: true`; Plans 1–10 contiguous; `errors: []` | PASS | 2026-07-18 |
| Compose health `overall=available` | `up --build -d --wait --wait-timeout 180` exit 0; three services healthy; health overall/sqlite/filesystem/neo4j `available` | PASS | 2026-07-18 |
| Scope hygiene `git diff --check` + approved paths only | See A1 report final hygiene row; product writes limited to this checklist + README completed-behavior sections | PASS | 2026-07-18 |

## Compose health (sanitized)

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` | exit 0; services backend/frontend/neo4j healthy | PASS | 2026-07-18 |
| `Invoke-RestMethod http://127.0.0.1:8000/api/health` | `{"overall":"available","sqlite":"available","filesystem":"available","neo4j":"available"}` | PASS | 2026-07-18 |
| Frontend shell | `http://127.0.0.1:5173` HTTP 200; asset `/assets/index-CLpt-Tsf.js` HTTP 200 | PASS | 2026-07-18 |

## Cleanup

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| No product/config/`.env` mutation to force green | Docs-config only: this checklist + README completed-behavior/command updates; no backend/frontend/infrastructure edits in 08A a2 | PASS | 2026-07-18 |
| Stack left usable | Compose left running with health overall=`available` after smoke; volumes not destroyed | PASS | 2026-07-18 |
| Temp synthetic JD not committed | Ephemeral chat text only; not tracked in git | PASS | 2026-07-18 |

## Completeness reminder

Mandatory Plan 10 direct observations: zero-result recovery precondition;
exact initiating-message source binding; save/dedup/evaluate; same-context
reuse; stale after approved CV change without auto-run; explicit re-evaluate;
complete Job delete preservation; desktop/mobile/a11y/network/console; full
automated gates and plan-structure validator — all PASS above with synthetic
fixtures only.
