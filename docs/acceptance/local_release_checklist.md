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

Disposable clean-checkout Compose proof is owned by later Plan 7 task (04A).
Do not reuse developer volumes.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|

## Failure and Recovery

Live failure/recovery matrix evidence is owned by later Plan 7 task (04B).

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|

## Fresh Graph Rebuild

Disposable Neo4j volume rebuild evidence is owned by later Plan 7 task (04B).

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|

## Manual Demo

Manual Compose demo evidence is owned by later Plan 7 task (04B).

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|

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
