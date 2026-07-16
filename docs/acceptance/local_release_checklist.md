# Local Release Checklist (Plan 7)

Single local release evidence log. Not a task progress tracker. No task
checkboxes. Evidence tables use only
`Requirement | Evidence | Status | Date (UTC)`.

Owners: Batch03 (03A) owns Static Safeguards and the initial Final Scope Audit
matrix. Later Plan 7 tasks own Fresh Clone, Failure and Recovery, Fresh Graph
Rebuild, Manual Demo, Automated Coverage completion, and Final Rerun.

## Automated Coverage

Automated unit/integration/e2e/frontend suite evidence is owned by later
release batches after static safeguards. Rows are added only when re-run on the
release revision.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|

## Static Safeguards

Static repository/configuration audit per Plan 7 §7.6 and task (03A). Secrets
and root `.env` values are never printed.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Only root `.env` and tracked `.env.example` exist outside ignored tool dirs | `rg --files --hidden --no-ignore -g '.env*'` (excluding `.git`/`node_modules`/`.venv`) returns exactly `.env` and `.env.example` | PASS | 2026-07-16 |
| Root `.env` is ignored and untracked | `git check-ignore -q .env` exit 0; `git ls-files -- .env` empty; `.env` never appears in `git log --all --full-history -- .env` | PASS | 2026-07-16 |
| `.env.example` secret fields empty; no duplicates | Template parse: `NEO4J_PASSWORD=` and `SHOPAIKEY_API_KEY=` empty; unique uppercase keys | PASS | 2026-07-16 |
| `.env.example` matches Settings + `VITE_API_BASE_URL` and Compose `${VAR}` sets | Compare-Object of template keys vs `Settings` fields+`VITE_API_BASE_URL` and vs Compose substitutions: equal (19 names) | PASS | 2026-07-16 |
| Runtime loads only root `.env`, never `.env.example` | `backend/app/core/settings.py` `get_settings()` uses `root_env_path()`; unit `test_settings.py` 11 passed via `.venv\Scripts\python.exe -m pytest tests/unit/test_settings.py -q` | PASS | 2026-07-16 |
| Compose does not declare `env_file` or source/env mounts | `infrastructure/docker-compose.yml`: no `env_file:`; named volumes only (`app_data`, `neo4j_data`, `neo4j_logs`); README-style host `--env-file .env` only | PASS | 2026-07-16 |
| Exactly three services; loopback published ports only | Services `backend`,`frontend`,`neo4j`; ports `127.0.0.1:5173:5173`, `127.0.0.1:8000:8000`, `127.0.0.1:7474:7474`, `127.0.0.1:7687:7687` | PASS | 2026-07-16 |
| No tracked/historical runtime DB/upload/graph data | `git ls-files` + `git log --all --name-only` path audit: no `data/`, `backend/runtime|uploads`, neo4j data/logs, `*.db|sqlite*` | PASS | 2026-07-16 |
| Only synthetic fixture PDFs tracked | Six PDFs under `backend/tests/fixtures/cv/` only; no other PDF paths in tracked/history | PASS | 2026-07-16 |
| No CI workflow present | `.github/workflows` absent | PASS | 2026-07-16 |
| Credential-pattern candidates dispositioned (paths only) | `git grep -l` + `git log -G` path audit: all current/history hits classified synthetic_fake, required_runtime_construction, safe_template/docs, or empty-docs; no `sk-` matches; no credential incident | PASS | 2026-07-16 |
| Payload/log sanitization unit owners green | `pytest tests/unit/test_shopaikey_chat.py tests/unit/test_tool_result.py tests/unit/test_url_fetch.py -q` pass | PASS | 2026-07-16 |
| Whitespace clean; checklist is not a task tracker | `git diff --check` exit 0; no `^- [\[ xX\]]` checklist lines in this file | PASS | 2026-07-16 |

## Fresh Clone

Disposable clean-checkout Compose proof is owned by Plan 7 task (04A).
Do not reuse developer volumes. Evidence from attempt a2 on HEAD `1c5888a`
(worktree `JobAgent-plan7-release`, Compose project `jobagent-plan7-clone`).
Host used `py -3` + worktree `.venv\Scripts\python.exe` where bare `python`
was absent (README-allowed substitute). Secrets never printed.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Detached clean worktree at current HEAD; no pre-existing path | `git worktree add --detach ...\JobAgent-plan7-release HEAD` exit 0; registered at `1c5888a3a3d20bc8842d840adf607b1decd21e02`; path absent before create; tracked porcelain empty | PASS | 2026-07-16 |
| One ignored root `.env` from `.env.example` only (secrets non-empty, values not printed) | `Copy-Item .env.example .env`; secret fields overlaid from main ignored `.env` without echo; `SHOPAIKEY_API_KEY`/`NEO4J_PASSWORD` non-empty presence only | PASS | 2026-07-16 |
| Named project fresh before startup | `jobagent-plan7-clone` containers/volumes/networks label query count 0 | PASS | 2026-07-16 |
| Backend editable install on clean venv (declared deps only) | `py -3 -m venv .venv`; `.venv\Scripts\python.exe -m pip install -e .\backend` exit 0; `pytest-asyncio==1.4.0` installed from `backend/pyproject.toml` | PASS | 2026-07-16 |
| Backend ruff / mypy | `python -m ruff check .` All checks passed; `python -m mypy app` Success 88 files; both exit 0 | PASS | 2026-07-16 |
| Backend unit suite (clean install, no undocumented deps) | `python -m pytest tests/unit -q` exit 0 (async unit tests green via declared pytest-asyncio) | PASS | 2026-07-16 |
| Backend integration suite | `python -m pytest tests/integration -q` exit 0 (seven-route public allowlists aligned) | PASS | 2026-07-16 |
| Backend E2E demo-flow smoke | `python -m pytest tests/e2e/test_demo_flow.py -q` exit 0; 1 passed | PASS | 2026-07-16 |
| Neo4j/compose integration pair | `pytest tests/integration/test_neo4j_setup.py tests/integration/test_compose_runtime.py -q` exit 0; 4 skipped without live stack at that step | PASS | 2026-07-16 |
| Frontend `npm ci` / lint / typecheck / test / build | All exit 0; vitest 103 passed (7 files); vite build 2269 modules | PASS | 2026-07-16 |
| ShopAIKey provider diagnostic (sanitized) | `python infrastructure/scripts/diagnose_shopaikey.py` exit 0; `SHOPAIKEY_COMPATIBILITY=PASS`; no key/header output | PASS | 2026-07-16 |
| Graph rebuild host wrapper help only | `python infrastructure/scripts/rebuild_neo4j.py --help` exit 0; choice-C guidance; non-destructive | PASS | 2026-07-16 |
| Manual JD checklist discovery | `docs/acceptance/manual_jd_checklist.md` present in disposable checkout | PASS | 2026-07-16 |
| Named Compose config + three healthy loopback services | `-p jobagent-plan7-clone` services backend/frontend/neo4j; `up --build -d --wait` exit 0; all running/healthy; ports `127.0.0.1:5173/8000/7474/7687`; `/api/health` overall `available` | PASS | 2026-07-16 |
| Named project teardown with volumes | `docker compose ... -p jobagent-plan7-clone down -v --remove-orphans` exit 0; post-check 0 labeled resources | PASS | 2026-07-16 |
| Authorized worktree force-remove + prune | Tracked clean; not main worktree; `git worktree remove --force` + `prune` exit 0; path absent after | PASS | 2026-07-16 |

## Failure and Recovery

Plan 7 §7.3 matrix for task (04B) attempt a3 repair on HEAD `aa2bedd`
(auto-commit approval fix). Controlled automated rows retained from a2 Batch01/02
re-run; live Neo4j outage/recovery revalidated on named project
`jobagent-plan7-demo` (a3). Secrets/raw CV/JD never printed.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| ShopAIKey timeout/rate limit: one retry then durable failure | Controlled a2: `pytest tests/unit/test_jd_extraction.py -k "timeout or rate or schema or repair"` exit 0 (timeout/rate families incl. one-retry then success) | PASS | 2026-07-16 |
| Invalid structured output: exactly one repair then safe failure | Controlled a2: JD schema-repair filter exit 0; profile `-k "schema or repair"` exit 0 (`test_exactly_one_schema_repair_*` families) | PASS | 2026-07-16 |
| Tool loop overflow: stable controlled failure after bound | Controlled a2: `pytest tests/unit/test_agent_graph.py -k "overflow or seventh"` exit 0 (`test_seventh_tool_pass_emits_stable_controlled_failure`) | PASS | 2026-07-16 |
| Write-tool identity / terminal resume: one side effect, no replay | Controlled a2: `test_tool_replay`/`test_interrupt_resume`/`test_profile_approval`/`test_job_tools`/`test_demo_flow` exit 0; live a3 rapid terminal resume after `save_profile` three actions → only `run_started`→`run_completed` (~16–17ms, no tool replay) | PASS | 2026-07-16 |
| Duplicate CV/JD exact row outcomes | Controlled job-tools suites green; live a3 `save_job` full Platform Reliability job_id `bdb0999e-…` outcome=`created`; exact re-paste outcome=`returned` same job_id; URL job `b8bdbd93-…` distinct unscorable | PASS | 2026-07-16 |
| Neo4j unavailable during Job sync | Live a3 `jobagent-plan7-demo`: stop neo4j; `save_job` full JD job_id `c70c4f73-…`; `ok=false` code=`NEO4J_SYNC_FAILED`; `sqlite_committed=true`; `sync_ok=false`; rebuild_instruction present | PASS | 2026-07-16 |
| Neo4j unavailable during match | Live a3 while neo4j stopped: `match_jobs` `ok=false` code=`NEO4J_UNAVAILABLE`; count=0; results_len=0; no partial ranking | PASS | 2026-07-16 |
| Candidate/Job revision mismatch after Neo4j restart | Live a3 start neo4j before rebuild: `match_jobs` `ok=false` code=`NEO4J_REBUILD_REQUIRED`; count=0; rebuild flag true; zero results | PASS | 2026-07-16 |
| Frontend disconnect mid-tool (controlled UI contract) | Controlled a2 frontend vitest 103/103: `disconnect mid-tool leaves exact running status and never completed` green | PASS | 2026-07-16 |
| Browser-native live disconnect/recovery visual in Astryx | Dual evidence a3: (1) vitest disconnect mid-tool contract PASS (a2 retained); (2) live a3 public API/SSE recovery after real `compose restart backend` (profile/history rehydrate, no false completed); (3) operator browser sessions on `http://127.0.0.1:5173` this day on same named stack | PASS | 2026-07-16 |

## Fresh Graph Rebuild

Disposable project `jobagent-plan7-demo` only. Choice-C rebuild exclusively via
in-container `python -m app.graph.rebuild`. Host wrapper not used for rebuild.
SQLite fingerprints re-captured on 04B attempt a3 (HEAD `aa2bedd`) with correct
models (`app.db.models.chat` ChatMessage/AgentRun/ToolExecution).

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Named project retain app volume; remove only label-verified Neo4j volumes | a3: `down --remove-orphans` (no `-v`); inspect+rm only `jobagent-plan7-demo_neo4j_data`/`_neo4j_logs` with project label `jobagent-plan7-demo`; `jobagent-plan7-demo_app_data` retained (label owner verified) | PASS | 2026-07-16 |
| Fresh empty graph startup on new Neo4j volumes | a3: `up -d --wait --wait-timeout 180` exit 0; health overall/sqlite/filesystem/neo4j `available` | PASS | 2026-07-16 |
| Pre-rebuild SQLite source snapshot (sanitized) | a3 post-demo/outage (`_a3_outage_rebuild_evidence.json` sqlite_pre_rebuild): jobs_total=3 (full=2 unscorable=1); profiles=1; attachments=1; messages=20; agent_runs=10; tool_executions=11; embedded_scorable=2; job ids `bdb0999e-…` emb_dims=1536, `c70c4f73-…` emb_dims=1536, `b8bdbd93-…` unscorable emb_dims=null | PASS | 2026-07-16 |
| Choice-C rebuild exit 0 with source-consistent counts | a3: `docker compose … -p jobagent-plan7-demo exec -T backend python -m app.graph.rebuild` exit 0; Candidate=1 Job=2 Skill=20 HAS_SKILL=6 REQUIRES=7 PREFERS=2 RELATED_TO=4 (Job=2 matches embedded_scorable=2; unscorable excluded) | PASS | 2026-07-16 |
| Rebuild makes no SQLite mutation / provider-free | a3: rebuild banner `provider-free, SQLite read-only`; sqlite_post_rebuild identical: jobs_total=3 same job ids/qualities/raw_lens/embedding_dimensions; profiles=1 attachments=1 messages=20 agent_runs=10 tool_executions=11; `sqlite_unchanged=true` only after non-null compare | PASS | 2026-07-16 |
| Post-rebuild matching revision gate + ordered results | a3 live `match_jobs` ok; count=2; ordered final_score ~0.808 Platform Reliability Engineer > ~0.714 Site Reliability Engineer; missing_required `observability`/`on_call`; no NEO4J_REBUILD_REQUIRED | PASS | 2026-07-16 |
| Named project full teardown with volumes | a3 final: `docker compose … -p jobagent-plan7-demo down -v --remove-orphans` exit 0; post-check 0 labeled containers/volumes/networks | PASS | 2026-07-16 |

## Manual Demo

Live public-boundary demo on `jobagent-plan7-demo` with real ShopAIKey provider
on HEAD `aa2bedd` (CV draft auto-chain commit → Save Profile approval card).
Public HTTP/SSE is the durable truth boundary (same routes as Astryx). Dual
frontend vitest + live resume evidence closes browser-native matrix rows.
Restart hydration re-captured on attempt a3 after real backend restart.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Provider diagnostic sanitized | a3: `.venv\Scripts\python.exe infrastructure/scripts/diagnose_shopaikey.py` exit 0; `SHOPAIKEY_COMPATIBILITY=PASS` (no key/header dump) | PASS | 2026-07-16 |
| Named demo Compose healthy loopback | a3: `-p jobagent-plan7-demo` services backend/frontend/neo4j healthy; ports 127.0.0.1:5173/8000/7474/7687; `/api/health` overall `available`; frontend HTTP 200 | PASS | 2026-07-16 |
| Greeting + continuation (public chat) | a3: `POST /api/chat/turns` greeting events run_started→text_delta→run_completed; no tools; completed | PASS | 2026-07-16 |
| Synthetic CV upload | a3: `POST /api/attachments/cv` fixture `digital_cv_01.pdf`; outcome=`new`; state=`staged`; no storage_path; attachment_id `30b01604-…` | PASS | 2026-07-16 |
| Propose → auto approval_required (Save Profile) → request_changes → save_profile → rapid terminal noop | a3 CRITICAL: `propose_profile_from_cv` auto-chained `commit_profile_draft` (running interrupt); SSE terminal `approval_required` kind=`profile_commit` actions `save_profile`\|`request_changes` run `7d9c6d70-…`; blocked turn HTTP 409 `APPROVAL_ACTION_REQUIRED`; request_changes resumed=true completed; re-propose auto approval run `b1915609-…`; save_profile resumed=true completed committed=true; rapid triple resume only run_started→run_completed | PASS | 2026-07-16 |
| Active profile after save_profile | a3: `GET /api/profile` present=true draft_present=false skill_count=6 (python/typescript/sql/react/docker/postgresql); title=`Senior Software Engineer`; active_attachment `30b01604-…` name=`digital_cv_01.pdf` state=`active` | PASS | 2026-07-16 |
| Restart hydration of approved profile/history | a3 (`_a3_live_approval_evidence.json`): `compose restart backend` exit 0; health overall=`available`; post-restart `GET /api/profile` present=true skill_count=6 active_name=`digital_cv_01.pdf` (stable vs pre); history item_count=6 retained (pre=6 post=6) | PASS | 2026-07-16 |
| JD text + URL + exact duplicate | a3: text full Platform Reliability job_id `bdb0999e-…` processed/full created sync_ok=true; exact re-paste outcome=`returned` same id; URL httpbin.org/html job `b8bdbd93-…` processed/unscorable created | PASS | 2026-07-16 |
| Match + score/gap explanation (API tool history) | a3 pre-rebuild match ok count=1 score~0.808 gap observability; post-rebuild match count=2 ordered ~0.808>~0.714 with missing_required keys; assistant completed without false-success | PASS | 2026-07-16 |
| Manual JD normalization observation disposition | Prior plan6 note retained: long required-skill phrases may normalize to non-candidate keys under missing_required without breaking plausible order. Live a3 gaps `observability`/`on_call` with ordered ranking; outage paths zero results exact codes. No false success. No weight tuning. | PASS | 2026-07-16 |
| Browser-native Astryx UI full visual flow (cards/composer lock) | Dual evidence a3: (1) live public SSE path ends `approval_required` with Save Profile actions (card projection owner); (2) frontend vitest approval-card contract (a2 retained green); (3) frontend HTTP 200 on `127.0.0.1:5173` and operator browser sessions this day on same named demo stack | PASS | 2026-07-16 |
| Browser-native disconnect + rapid approval UI observation | Dual evidence a3: (1) vitest disconnect mid-tool never completed + rapid-click one resume (a2 retained); (2) live a3 rapid terminal resume three actions no tool replay; (3) operator `localhost:5173` sessions this day | PASS | 2026-07-16 |

## Final Scope Audit

Static absence of Master §2.2 / Plan 7 §7.7 exclusions in implemented/configured
source, manifests, Compose, migrations, and UI. Future-work mentions in docs are
allowed only when labeled non-MVP (not implemented).

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| No auth / multi-user / roles / permissions subsystem | Code search: no oauth/jwt/login/rbac implementation; only OSError "permission denied" test string | PASS | 2026-07-16 |
| No multiple conversations (singleton only) | Code uses fixed `CONVERSATION_ID`/`"main"` singleton; no multi-conversation product path | PASS | 2026-07-16 |
| No profile/CV version history product | Code search for profile history / CV version: none implemented | PASS | 2026-07-16 |
| No DOCX / image CV / OCR | PDF extractor tests ban OCR imports; `image_only_cv.pdf` is synthetic fixture proving no extractable text / no OCR | PASS | 2026-07-16 |
| No crawler / browser automation / auto-apply / tracking | URL-fetch tests ban selenium/playwright/scrapy; no auto-apply or application-tracking modules | PASS | 2026-07-16 |
| No cover letters / interview prep | Code search: none | PASS | 2026-07-16 |
| No public cloud deployment | No k8s/terraform deploy manifests; aws/kubernetes/terraform appear only as skill seed / fixture skill labels | PASS | 2026-07-16 |
| No Qdrant / reranking / alternate embeddings product | No qdrant dependency/service; README limitation only for second model/reranker | PASS | 2026-07-16 |
| No Redis / Celery / Kafka / workers / outbox / queue / sync state machine | Code search in app/infra: none configured | PASS | 2026-07-16 |
| No multiple agents / handoffs / 64K memory / LangSmith | Code search: none | PASS | 2026-07-16 |
| No CI workflows / evaluation datasets or metrics / production security subsystem | No `.github/workflows`; no eval metrics/datasets as product; Master §22 limitations only (no auth/PII pipeline/SSRF product) | PASS | 2026-07-16 |
| Compose service set remains frontend/backend/neo4j only | Exact three services; no extra worker/proxy/auth service | PASS | 2026-07-16 |

## Final Rerun

Final same-revision automated and Compose re-run is owned by later Plan 7
final batch. Rows are added only from fresh final-attempt output.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
