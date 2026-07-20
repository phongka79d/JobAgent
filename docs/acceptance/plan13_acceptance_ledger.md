# Plan 13 Acceptance Ledger

Dated Plan 13 execution supplement for every P12 revalidation and P13 repair
requirement. This ledger preserves immutable pre-repair baseline failures and
records later work only through append-only attempt rows. It does not replace
historical Plan 6 evidence in `manual_jd_checklist.md` or historical Plan 9
evidence in `cv_manager_checklist.md`.

**plan_id:** plan13 · **Compose project (browser):** `jobagent-plan13-smoke` ·
**Matrix owner:** [`full_functional_test_matrix.md`](full_functional_test_matrix.md) ·
**Two-CV browser procedure:** [`cv_manager_checklist.md`](cv_manager_checklist.md)
Plan 13 section (`P13-CV-01`)

## Rules

- Initial requirement status is `NOT RUN`. After execution only `PASS`, `FAIL`,
  `BLOCKED`, or `SKIPPED (reason)` is allowed on requirement rows.
- Candidate identity is the base HEAD plus a SHA-256 content-manifest fingerprint
  over every modified, deleted, or untracked product, test, dependency, and
  configuration path before A3 (deleted paths use literal `DELETED`). Append-only
  acceptance evidence paths are excluded from that fingerprint. The A3 handoff
  reports the eventual committed SHA; this ledger must not require a
  self-referential SHA inside that same commit.
- Each procedure/command cell declares `Evidence owner: automated`, `browser`, or
  `mixed`. Automated-only schema, diagnostic, fake-counter, and regression rows
  link exact command output and are never presented as browser observations.
  Browser execution covers only browser-owned rows and the browser slice of mixed
  rows.
- Automated fake/wrapper spies own exact ingestion/extraction/embedding/
  evaluation/Neo4j-sync counters. Browser evidence owns only observable SQLite
  Job/evaluation deltas, Neo4j Job/active-CV deltas, durable run/tool state,
  network, console, and sanitized backend logs. Browser rows must not claim
  automated fake or provider counters.
- Reruns append to **Execution attempts**; they never overwrite earlier attempt
  rows or rewrite **Preserved pre-repair failures**. A requirement row may
  summarize an accepted result only when it links every earlier attempt.
- Non-blocking environment/tooling warnings live only in **Non-blocking warnings
  (out of scope)** and never replace or dilute functional PASS/FAIL rows.
- Never record raw JD/CV bodies, provider transcripts, prompts, credentials,
  authorization headers, storage paths, SQL/Cypher, or personal data.

## Requirement rows

| ID | Requirement/source | Procedure or command | Status | Date (UTC) | HEAD / Compose project | Failure/log evidence | Resolution/notes |
|---|---|---|---|---|---|---|---|
| P12-RSP-01 | Master 12.5; Plan 12 Objective; approved response layout | Evidence owner: mixed. Prompt contract tests and desktop response samples; record candidate identity and sanitized outcome links. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-RSP-01-B1`) | Automated FE in `P12-RSP-01-A1`/`A2`; browser sample blocked in (05B) attempt `P12-RSP-01-B1` (no smoke start; normal stack left running). |
| P12-RSP-02 | Master 15.3; Astryx 0.1.4; Plan 12 | Evidence owner: automated. Component tests for headings, emphasis, lists, user literals, and streaming. | PASS | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | — | Attempts `P12-RSP-02-A1` (prior empty-manifest freeze; ruff later failed REG) + `P12-RSP-02-A2` on post-ruff freeze: focused assistant-response Vitest exit 0. |
| P12-CV-01 | Master 12.4, 13.7; Plan 12 | Evidence owner: mixed. Prompt/tool tests and Certificate-count desktop smoke for narrowest `read_active_cv` mode. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-CV-01-B1`) | Automated BE/FE in `P12-CV-01-A1`/`A2`; browser blocked in (05B) `P12-CV-01-B1`. |
| P12-CV-02 | Master 7.5, 14; Plan 12 | Evidence owner: automated. Projection, hydration, restart, and forbidden-key tests for strict frontend evidence projection. | PASS | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | — | Attempts `P12-CV-02-A1` + `P12-CV-02-A2`: active-cv-source / sse-reducer / chat-page focused Vitest exit 0. |
| P12-CV-03 | Approved source layout; Plan 12 | Evidence owner: mixed. Assistant-row interaction and exact-one **Nguồn** citation tests; browser observation of citation placement. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-CV-03-B1`) | Automated citation tests in `P12-CV-03-A1`/`A2`; browser blocked in (05B) `P12-CV-03-B1`. |
| P12-CV-04 | Master 13.7; retained-file route; Plan 12 | Evidence owner: mixed. Dialog record-order, truncation, no-fetch, and retained-PDF URL tests plus browser no-fetch observation. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-CV-04-B1`) | Automated dialog tests in `P12-CV-04-A1`/`A2`; browser blocked in (05B) `P12-CV-04-B1`. |
| P12-CV-05 | Master 20, 24; Plan 12 | Evidence owner: automated. Negative parser/UI/reducer tests that bad tool state never produces false provenance. | PASS | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | — | Attempts `P12-CV-05-A1` + `P12-CV-05-A2`: focused FE negative evidence paths exit 0. |
| P12-JD-01 | Master 11.2, 12.5; Plan 12 passive-JD design | Evidence owner: mixed. Prompt/decision tests for recognition, thresholds, markers, opt-outs, explicit paths, and one repair only; browser passive-JD recognition slice. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-JD-01-B1`) | Automated agent-graph/job-tools in `P12-JD-01-A1`/`A2`; browser blocked in (05B) `P12-JD-01-B1`. |
| P12-JD-02 | Master 6.4, 12.2-12.3, 13.4; Plan 12 | Evidence owner: automated. Source-ownership, lookup-failure, pre-interrupt call-count, pending-row, and no-raw-projection tests for `source='current_message'`. | PASS | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | — | Attempts `P12-JD-02-A1` + `P12-JD-02-A2`: focused job-tools/confirmation integration+unit exit 0. |
| P12-JD-03 | Master 14.2, 15.3-15.7; Plan 12 | Evidence owner: mixed. Backend projection/SSE and frontend parser/card tests for strict `job_save_confirmation`; browser card/actions observation. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-JD-03-B1`) | Automated BE/FE confirmation in `P12-JD-03-A1`/`A2`; browser blocked in (05B) `P12-JD-03-B1`. |
| P12-JD-04 | Master 7.5, 12.2, 13.4, 20; Plan 12 | Evidence owner: mixed. Interrupt/resume, execution-identity, branch call-count, duplicate-click, terminal-replay integration tests; browser save/cancel terminal slice. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-JD-04-B1`) | Automated chat_api/job_tools resume in `P12-JD-04-A1`/`A2`; browser blocked in (05B) `P12-JD-04-B1`. |
| P12-JD-05 | Master 11.2, 17.5, 24; Plan 12 | Evidence owner: mixed. Direct-path regressions, saved-card/cancellation gating, no-evaluate assertions, and desktop acceptance for confirmed save without evaluation. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P12-JD-05-B1`) | Automated direct-path/saved-card in `P12-JD-05-A1`/`A2`; browser blocked in (05B) `P12-JD-05-B1`. |
| P12-REG-01 | Master 12.1, 12.6, 24; Plan 12 | Evidence owner: mixed. Existing graph/backend/frontend/full-suite gates proving one Agent/decision/ToolNode, seven tools, six-pass limit, and desktop regressions. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | A1 ruff FAIL retained in `P12-REG-01-A1`; browser desktop slice blocked (`P12-REG-01-B1`) | Automated suites/topology/static PASS on `P12-REG-01-A2`; (05B) browser/desktop slice blocked without smoke mutation. |
| P13-JD-01 | Master 11.2, 13.4; Plan 13 Provider-visible source contract | Evidence owner: automated. Inspect actual provider-bound payload; focused pytest on provider/runtime/ToolNode owners; early side-effect-free inline `.venv` probe printing only `SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS` or `SAVE_JOB_PROVIDER_SCHEMA_PROBE=FAIL`. | PASS | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | — | Attempts `P13-JD-01-A1` + `P13-JD-01-A2`: `test_shopaikey_chat.py` + job_tools schema owners exit 0 on post-ruff freeze. |
| P13-JD-02 | Master 12.1-12.6, 20; Plan 13 One bounded strict repair | Evidence owner: automated. Binding-aware RED fake, exact normal/repair binding arguments, first/repair invocation counts, sanitized `caplog` (`passive_jd_call_rejected`), refusal checks, topology assertions. | PASS | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | — | Attempts `P13-JD-02-A1` + `P13-JD-02-A2`: `test_agent_graph.py` exit 0. |
| P13-JD-03 | Master 6.4, 11.2, 13.4, 15.7; Plan 13 Confirmation, side effects, and durable truth | Evidence owner: mixed. Public SSE/integration spies for exact durable lookup boundaries and automated counters; browser-owned durable state/delta/network/console slice only. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P13-JD-03-B1`) | Automated counters/SSE in `P13-JD-03-A1`/`A2`; browser durable deltas blocked in (05B) `P13-JD-03-B1`. |
| P13-A11Y-01 | Plan 12 Objective/Scope; Master 15.3, 15.7; Plan 13 Source dialog accessibility | Evidence owner: mixed. Testing Library `getByRole('dialog', {name: 'Nguồn từ CV'})` plus evidence/no-fetch/PDF/close/Escape/focus regressions; browser accessibility observation. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | Browser control surface unavailable (`P13-A11Y-01-B1`) | Automated dialog role/name in `P13-A11Y-01-A1`/`A2`; browser a11y blocked in (05B) `P13-A11Y-01-B1`. |
| P13-DIAG-01 | Master 16.2, 17.2, 24; Plan 13 Deterministic diagnostic coverage | Evidence owner: automated. Fake-backed timeout/429/malformed/model-absence/dimension/ordering and PDF aggregate negatives; project-interpreter positive pypdf and final ShopAIKey diagnostic pair. | PASS | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | — | Attempts `P13-DIAG-01-A1` + `P13-DIAG-01-A2`: negatives + fresh `PYPDF_COMPATIBILITY=PASS` / `SHOPAIKEY_COMPATIBILITY=PASS` on post-ruff freeze (prior freezes not reused). |
| P13-CV-01 | Master 10.5, 15.2, 24.4; Plan 13 two-CV browser evidence | Evidence owner: browser. Named project `jobagent-plan13-smoke`; fixtures `digital_cv_01.pdf` (A) and `digital_cv_02.pdf` (B); exact A/B lifecycle in [`cv_manager_checklist.md`](cv_manager_checklist.md) Plan 13 section. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` / project not started | In-app browser control tools unavailable in A1 session (`P13-CV-01-B1`) | (05A) freeze green on `05A-FREEZE-A2`; (05B) read-only preflight PASS; smoke not started; no browser matrix evidence. |
| P13-EVID-01 | Master 24, 27; Plan 13 Traceability and browser evidence | Evidence owner: mixed. This ledger plus matrix supplement; immutable `BASE-PJD-01..03`; append-only attempts; separate warnings; frozen-candidate automated and browser evidence with first-failure retention. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | A1 incomplete freeze retained in `P13-EVID-01-A1`; browser blocked in `P13-EVID-01-B1` | Automated freeze/traceability PASS on `P13-EVID-01-A2`. Browser evidence blocked in (05B); append-only attempt retained; README unchanged. |
| P13-REG-01 | Master 12.1, 12.6, 24, 27; Plan 13 regression gate | Evidence owner: mixed. Focused/full backend/frontend/static/build/Compose/browser/structure/scope gates on the frozen candidate. | BLOCKED | 2026-07-19 | `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` | A1 ruff FAIL retained in `P13-REG-01-A1`; browser/Compose lifecycle blocked (`P13-REG-01-B1`) | Attempt `P13-REG-01-A2` automated/static green; (05B) Compose read-only preflight PASS but smoke/browser not started due to missing browser control surface. |

## Preserved pre-repair failures

Immutable historical rows. Never rewrite these as PASS. Append new synthetic
repair attempts only under **Execution attempts**.

| Attempt ID | UTC date | Product HEAD / project | Run ID | Observed result | Root cause / disposition |
|---|---|---|---|---|---|
| `BASE-PJD-01` | 2026-07-19 | `887d4f6` / pre-repair audit stack | `4971481e-0e7b-42ca-8d7b-184d314be2e9` | FAIL: `tool_count=0`; fixed no-confirmation response | Provider/Agent boundary reliability failure; schema shape alone was not proven as the sole root cause. Preserve and append a new synthetic repair attempt. |
| `BASE-PJD-02` | 2026-07-19 | `887d4f6` / pre-repair audit stack | `d1fab78d-a4ff-4a9d-ad06-75d5cd229c8a` | FAIL: `tool_count=0`; fixed no-confirmation response | Same observed boundary failure with root cause unresolved by this historical row; preserve the first result. |
| `BASE-PJD-03` | 2026-07-19 | `887d4f6` / pre-repair audit stack | `5a12595d-7af4-4b64-a03b-433c08d87293` | FAIL: `tool_count=0`; fixed no-confirmation response | Long MISA-like case; preserve the first result and use only synthetic rerun content. |

## Execution attempts

Append-only. Key by requirement ID plus attempt suffix (for example
`P13-JD-02-A1`, then `P13-JD-02-A2`). A rerun adds a new row; it never overwrites
A1. Requirement-row summaries may reference every earlier attempt ID listed here.

| Attempt ID | Requirement ID | UTC date | Candidate identity (base HEAD + content-manifest SHA-256) / project | Run ID | Result | Failure/log evidence | Resolution/notes |
|---|---|---|---|---|---|---|---|
| `05A-FREEZE-A1` | P13-REG-01 / freeze identity | 2026-07-19 | base `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty path list: no non-acceptance product/test/dependency/config delta vs HEAD) / n/a | `plan13-20260719T152938Z` | PASS (identity) | — | Exact (05A) PowerShell procedure run twice with identical output; acceptance/plan/task/README/`.agent` paths excluded. |
| `P13-REG-01-A1` | P13-REG-01 | 2026-07-19 | base `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` / automated gates | `plan13-20260719T152938Z` | FAIL | Backend ruff exit `1` (5 errors: E501×2, I001×3) | BE unit+integration focused pytest exit 0; mypy exit 0; full pytest exit 0; FE focused+full Vitest exit 0; lint/typecheck/build exit 0; plan validator `valid: true`; topology/routes/protected-diff/status scoped. Static ruff fails freeze. No product edit in (05A). |
| `P12-REG-01-A1` | P12-REG-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | FAIL | Same ruff exit `1` | Topology constants present (`DECISION_NODE_NAME=agent`, `TOOLS_NODE_NAME=tools`, `TOOL_LOOP_LIMIT` default six, seven-tool registry docstring); full suites green except ruff. |
| `P13-JD-01-A1` | P13-JD-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS | — | `pytest tests/unit/test_shopaikey_chat.py` (+ focused unit bundle) exit 0. |
| `P13-JD-02-A1` | P13-JD-02 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS | — | `pytest tests/unit/test_agent_graph.py` (+ focused unit bundle) exit 0. |
| `P13-JD-03-A1` | P13-JD-03 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | `test_job_tools.py` + `test_chat_api.py` + confirmation unit exit 0; browser slice not run. |
| `P13-A11Y-01-A1` | P13-A11Y-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | `active-cv-source` / `assistant-response` / `chat-page` focused Vitest exit 0; browser a11y not run. |
| `P13-DIAG-01-A1` | P13-DIAG-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS | — | Focused `test_phase0_diagnostics` (+ embedding/pdf units in full suite) green; 03A positive evidence HEAD/manifest mismatch → reran `verify_pdf_extraction.py` (`PYPDF_COMPATIBILITY=PASS`) and `diagnose_shopaikey.py` (`SHOPAIKEY_COMPATIBILITY=PASS`, sanitized host only). |
| `P13-EVID-01-A1` | P13-EVID-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | FAIL | Freeze incomplete: ruff FAIL retained | Candidate identity + append-only attempts written; BASE-PJD immutable; plan validator `valid: true`; acceptance traceability search complete; browser evidence still pending. |
| `P12-RSP-01-A1` | P12-RSP-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | Focused assistant-response Vitest exit 0; browser samples pending. |
| `P12-RSP-02-A1` | P12-RSP-02 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS | — | Focused assistant-response component tests exit 0. |
| `P12-CV-01-A1` | P12-CV-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | BE active_cv_tool + FE active-cv-source exit 0; browser pending. |
| `P12-CV-02-A1` | P12-CV-02 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS | — | Focused FE evidence projection/hydration tests exit 0. |
| `P12-CV-03-A1` | P12-CV-03 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | Nguồn citation tests exit 0; browser pending. |
| `P12-CV-04-A1` | P12-CV-04 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | Dialog record-order/no-fetch/PDF tests exit 0; browser pending. |
| `P12-CV-05-A1` | P12-CV-05 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS | — | Negative provenance FE tests exit 0. |
| `P12-JD-01-A1` | P12-JD-01 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | agent_graph + job_tools focused exit 0; browser pending. |
| `P12-JD-02-A1` | P12-JD-02 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS | — | job_tools/confirmation current_message automated owners exit 0. |
| `P12-JD-03-A1` | P12-JD-03 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | job_save_confirmation BE/FE tests exit 0; browser pending. |
| `P12-JD-04-A1` | P12-JD-04 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | chat_api/job_tools interrupt-resume automated exit 0; browser pending. |
| `P12-JD-05-A1` | P12-JD-05 | 2026-07-19 | same as `05A-FREEZE-A1` | `plan13-20260719T152938Z` | PASS (automated only) | — | direct-path/saved-card/no-evaluate automated exit 0; browser pending. |
| `05A-FREEZE-A2` | P13-REG-01 / freeze identity | 2026-07-19 | base `1c8e3708150f832c80d0dc8500312c6642208a02` + manifest `152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33` (4 paths after accepted 05A-ruff hygiene: `backend/app/schemas/jobs.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/unit/test_phase0_diagnostics.py`, `backend/tests/unit/test_shopaikey_chat.py`; path hashes recorded in A1-a2 without file contents) / n/a | `plan13-20260719T152938Z` | PASS (identity) | — | Exact (05A) PowerShell procedure run twice with identical output; acceptance/plan/task/README/`.agent` paths excluded. Prior empty-manifest freeze `05A-FREEZE-A1` retained. |
| `P13-REG-01-A2` | P13-REG-01 | 2026-07-19 | same as `05A-FREEZE-A2` / automated gates | `plan13-20260719T152938Z` | PASS (automated only) | — | BE focused unit+integration pytest exit 0; `ruff check app tests --no-cache` exit 0 (`All checks passed!`); mypy exit 0 (125 files); full pytest exit 0; FE focused set1 5/114, set2 6/84, full 27/317 exit 0; lint/typecheck/build exit 0; plan validator `valid: true`; topology/routes/protected-diff empty; `git diff --check` exit 0; positive diagnostics rerun PASS. Compose/browser not started. A1 ruff FAIL retained. |
| `P12-REG-01-A2` | P12-REG-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | Topology: `DECISION_NODE_NAME=agent`, `TOOLS_NODE_NAME=tools`, `TOOL_LOOP_LIMIT` default six, seven-tool production registry docstring; full BE/FE suites + ruff green. Desktop/browser pending (05B). |
| `P13-JD-01-A2` | P13-JD-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS | — | Focused unit bundle including `test_shopaikey_chat.py` exit 0 on post-ruff freeze. |
| `P13-JD-02-A2` | P13-JD-02 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS | — | Focused unit bundle including `test_agent_graph.py` exit 0. |
| `P13-JD-03-A2` | P13-JD-03 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | `test_job_tools.py` + `test_chat_api.py` + confirmation unit exit 0; browser slice not run. |
| `P13-A11Y-01-A2` | P13-A11Y-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | `active-cv-source` / `assistant-response` / `chat-page` focused Vitest exit 0; browser a11y not run. |
| `P13-DIAG-01-A2` | P13-DIAG-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS | — | Focused `test_phase0_diagnostics` exit 0; fresh `verify_pdf_extraction.py` (`PYPDF_COMPATIBILITY=PASS`, digital_pass=5/5) and `diagnose_shopaikey.py` (`SHOPAIKEY_COMPATIBILITY=PASS`, sanitized `base_url_host=api.shopaikey.com` only). Prior freezes not reused (manifest changed). |
| `P13-EVID-01-A2` | P13-EVID-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | Candidate identity + append-only A2 attempts; BASE-PJD immutable; plan validator `valid: true`; acceptance traceability search complete; A1 FAIL retained; browser evidence still pending. |
| `P12-RSP-01-A2` | P12-RSP-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | Focused assistant-response Vitest exit 0; browser samples pending. |
| `P12-RSP-02-A2` | P12-RSP-02 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS | — | Focused assistant-response component tests exit 0. |
| `P12-CV-01-A2` | P12-CV-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | BE active_cv_tool + FE active-cv-source exit 0; browser pending. |
| `P12-CV-02-A2` | P12-CV-02 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS | — | Focused FE evidence projection/hydration tests exit 0. |
| `P12-CV-03-A2` | P12-CV-03 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | Nguồn citation tests exit 0; browser pending. |
| `P12-CV-04-A2` | P12-CV-04 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | Dialog record-order/no-fetch/PDF tests exit 0; browser pending. |
| `P12-CV-05-A2` | P12-CV-05 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS | — | Negative provenance FE tests exit 0. |
| `P12-JD-01-A2` | P12-JD-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | agent_graph + job_tools focused exit 0; browser pending. |
| `P12-JD-02-A2` | P12-JD-02 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS | — | job_tools/confirmation current_message automated owners exit 0. |
| `P12-JD-03-A2` | P12-JD-03 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | job_save_confirmation BE/FE tests exit 0; browser pending. |
| `P12-JD-04-A2` | P12-JD-04 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | chat_api/job_tools interrupt-resume automated exit 0; browser pending. |
| `P12-JD-05-A2` | P12-JD-05 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | PASS (automated only) | — | direct-path/saved-card/no-evaluate automated exit 0; browser pending. |
| `05B-PREFLIGHT-B1` | P13-REG-01 / Compose preflight | 2026-07-19 | same as `05A-FREEZE-A2` / normal project `infrastructure` | `plan13-20260719T152938Z` | PASS (read-only preflight) | — | Candidate identity reconfirmed identical before preflight. Configured services exact `backend`/`frontend`/`neo4j`. Normal project 3/3 running healthy; API health overall/sqlite/filesystem/neo4j available. Fixed ports 5173/8000/7474/7687 owned by Docker backend process mapped to project `infrastructure`. Smoke containers/volumes/networks empty. Recovery state file absent. No stop/start performed. |
| `P13-CV-01-B1` | P13-CV-01 | 2026-07-19 | same as `05A-FREEZE-A2` / smoke not started | `plan13-20260719T152938Z` | BLOCKED | In-app browser control surface unavailable in A1 session (no `node_repl`/`js` MCP; no browser MCP tools; Playwright not authorized substitute) | Read-only preflight green; normal stack left running; named smoke not started; no synthetic uploads; no browser matrix observations invented. |
| `P13-EVID-01-B1` | P13-EVID-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser-owned evidence missing; automated freeze retained | Append-only ledger/checklist BLOCKED rows only; BASE-PJD immutable; candidate identity unchanged after attempt; README unchanged. |
| `P13-REG-01-B1` | P13-REG-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser/Compose try-finally lifecycle not executed past read-only preflight | Automated A2 freeze retained; no product/test/config edit; normal volumes/networks preserved; smoke absent. |
| `P13-JD-03-B1` | P13-JD-03 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser durable-state slice unavailable | Automated A1/A2 retained. |
| `P13-A11Y-01-B1` | P13-A11Y-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser dialog observation unavailable | Automated A1/A2 retained. |
| `P12-RSP-01-B1` | P12-RSP-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser sample unavailable | Automated A1/A2 retained. |
| `P12-CV-01-B1` | P12-CV-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser slice unavailable | Automated A1/A2 retained. |
| `P12-CV-03-B1` | P12-CV-03 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser citation placement unavailable | Automated A1/A2 retained. |
| `P12-CV-04-B1` | P12-CV-04 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser no-fetch observation unavailable | Automated A1/A2 retained. |
| `P12-JD-01-B1` | P12-JD-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser passive-JD slice unavailable | Automated A1/A2 retained. |
| `P12-JD-03-B1` | P12-JD-03 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser card/actions unavailable | Automated A1/A2 retained. |
| `P12-JD-04-B1` | P12-JD-04 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser save/cancel terminal slice unavailable | Automated A1/A2 retained. |
| `P12-JD-05-B1` | P12-JD-05 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Browser direct-path/desktop slice unavailable | Automated A1/A2 retained. |
| `P12-REG-01-B1` | P12-REG-01 | 2026-07-19 | same as `05A-FREEZE-A2` | `plan13-20260719T152938Z` | BLOCKED | Desktop/browser slice unavailable | Automated A2 retained; A1 ruff FAIL retained. |

### Supplemental browser rerun evidence (append-only)

The historical `B1` blocked rows above are retained unchanged. The following
rows record the subsequent browser run on 2026-07-20 against the rebuilt
`infrastructure` Compose project (the existing user stack; no application or
Neo4j volume was removed). This supplemental run does not replace or close the
formal named-smoke `B1` gate.

Candidate identity for this rerun: base HEAD
`d00ca7471bb3ecfa43c9d2c99c2085a0ecd7e79c` plus manifest
`152fd891af508e1f820a740709285511d5446aa671a568ac8b99e6929762fb33`.
The four candidate paths are the same accepted 05A hygiene paths; acceptance
documents remain excluded from the fingerprint.

| Attempt ID | Requirement ID | UTC date | Candidate / project | Run ID(s) | Result | Sanitized evidence | Resolution/notes |
|---|---|---|---|---|---|---|---|
| `P13-CV-01-B2` | P13-CV-01 | 2026-07-20 | base `d00ca747…` + manifest `152fd891…` / `infrastructure` | `81a16774…`, `4e922bee…`, `e4db9189…` | PASS | Browser lifecycle: A approved; B approved and A archived; staged-B row exposed only Open/Delete; A reactivated and re-extracted; Save Profile made A active; archived B was deleted through the confirmation dialog. | Synthetic attachments only: A=`1adeb5a5…`, B=`de839dec…`; post-rebuild browser reload reconfirmed A active, B absent, and only Re-extract on selected A. |
| `P13-A11Y-01-B2` | P13-A11Y-01 | 2026-07-20 | same / `infrastructure` | `65af027c…` | PASS | Exactly one successful `read_active_cv`; answer was **Senior Software Engineer at Northwind Labs**. Citation opened a dialog named **Nguồn từ CV** with the returned records; **Mở CV gốc** produced retained-PDF HTTP 200; no chunks/evidence fetch occurred. Close and Escape each returned focus to the citation trigger. | Two returned records are the two experience entries in the active document, not two active attachments. |
| `P13-JD-03-B2` | P13-JD-03 | 2026-07-20 | same / `infrastructure` | `e5cfa5c0…`, `76d5199a…`, `444f2eb5…`, `23e4182d…`, `e3ea5946…`, `f885b4a4…`, `94b8206d…`, `017023a4…` | PASS | English confirmation/cancel; Vietnamese pending refresh/resume and exact dedupe; long synthetic JD confirmation/cancel; sole URL routed to safe `URL_FETCH_UNAVAILABLE`; exact direct-text request used `source=text` and created one synthetic job; opt-out and ambiguous prose were non-mutating. | No `INVALID_JOB_INPUT`, duplicate direct save, or evaluation side effect observed in the browser slice. |
| `P13-EVID-01-B2` | P13-EVID-01 | 2026-07-20 | same / `infrastructure` | `e4db9189…`, `65af027c…` | PASS | Durable evidence agrees with the UI: A is the sole active attachment/profile; B is absent after deletion; graph contains A and shared synthetic jobs/skills. Backend/frontend logs after rebuild contain zero error/exception/5xx/secret matches; the only pre-rebuild 404 was the intentional post-delete B file check. | Browser evidence records observable state only; provider/fake counters are not claimed. |
| `P13-REG-01-B2` | P13-REG-01 | 2026-07-20 | same / `infrastructure` | `e4db9189…`, `65af027c…` | PASS | Backend: Ruff pass, mypy pass (125 files), pytest `1193 passed, 3 skipped`; frontend: Vitest `320 passed`, lint/typecheck/build pass; plan validator `valid: true`; production registry count 7; Compose rebuild exit 0; health overall/SQLite/filesystem/Neo4j available; frontend HTTP 200. | Non-blocking warnings remain listed in the warnings table. |
| `P13-CV-01-B2-CLEANUP` | P13-CV-01 | 2026-07-20 | same / `infrastructure` | `4e922bee…` | PASS | After browser Delete CV: B row absent; B retained-file endpoint HTTP 404; B attachment/chunks/document/draft/source-message/tool/checkpoint/write counts are zero; A remains active; graph has no B node; shared synthetic Job/Skill nodes remain. | The historical B run shell is not CV-owned (`source_attachment_id` is null) and has zero tool/checkpoint rows; it is not treated as retained CV-owned data. |

## Non-blocking warnings (out of scope)

These observations never replace or dilute functional PASS/FAIL rows and are not
acceptance blockers for Plan 13 product requirements.

| warning | command/surface | classification | behavioral impact | disposition |
|---|---|---|---|---|
| jsdom `window.scrollTo` not implemented | Frontend Vitest / jsdom | environment/tooling | No product behavior change; scroll-related test noise only. | Out of scope; do not fail functional rows. |
| Duplicate synthetic React key | Frontend Vitest / React | test harness noise | Synthetic fixture keys only; does not indicate production key collisions. | Out of scope; keep separate from functional FAIL. |
| Vite bundle-size advisory | `npm run build` / Vite | build advisory | Bundle may exceed default size warning threshold without runtime failure. | Out of scope; record only; no product cleanup required by Plan 13. |
| `aiosqlite` datetime deprecation | Backend pytest / aiosqlite | dependency deprecation | Deprecation warning only; no observed functional SQLite contract break. | Out of scope; do not treat as functional FAIL. |
| Bare-host Python/pypdf environment | Host Python without project `.venv` / pypdf | environment classification | Missing bare-host `pypdf` is an environment classification, not a product defect; project-interpreter diagnostics remain the authority. | Out of scope; use project `.venv` for required diagnostics. |
