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
| P12-RSP-01 | Master 12.5; Plan 12 Objective; approved response layout | Evidence owner: mixed. Prompt contract tests and desktop response samples; record candidate identity and sanitized outcome links. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-RSP-02 | Master 15.3; Astryx 0.1.4; Plan 12 | Evidence owner: automated. Component tests for headings, emphasis, lists, user literals, and streaming. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-CV-01 | Master 12.4, 13.7; Plan 12 | Evidence owner: mixed. Prompt/tool tests and Certificate-count desktop smoke for narrowest `read_active_cv` mode. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-CV-02 | Master 7.5, 14; Plan 12 | Evidence owner: automated. Projection, hydration, restart, and forbidden-key tests for strict frontend evidence projection. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-CV-03 | Approved source layout; Plan 12 | Evidence owner: mixed. Assistant-row interaction and exact-one **Nguồn** citation tests; browser observation of citation placement. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-CV-04 | Master 13.7; retained-file route; Plan 12 | Evidence owner: mixed. Dialog record-order, truncation, no-fetch, and retained-PDF URL tests plus browser no-fetch observation. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-CV-05 | Master 20, 24; Plan 12 | Evidence owner: automated. Negative parser/UI/reducer tests that bad tool state never produces false provenance. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-JD-01 | Master 11.2, 12.5; Plan 12 passive-JD design | Evidence owner: mixed. Prompt/decision tests for recognition, thresholds, markers, opt-outs, explicit paths, and one repair only; browser passive-JD recognition slice. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-JD-02 | Master 6.4, 12.2-12.3, 13.4; Plan 12 | Evidence owner: automated. Source-ownership, lookup-failure, pre-interrupt call-count, pending-row, and no-raw-projection tests for `source='current_message'`. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-JD-03 | Master 14.2, 15.3-15.7; Plan 12 | Evidence owner: mixed. Backend projection/SSE and frontend parser/card tests for strict `job_save_confirmation`; browser card/actions observation. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-JD-04 | Master 7.5, 12.2, 13.4, 20; Plan 12 | Evidence owner: mixed. Interrupt/resume, execution-identity, branch call-count, duplicate-click, terminal-replay integration tests; browser save/cancel terminal slice. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-JD-05 | Master 11.2, 17.5, 24; Plan 12 | Evidence owner: mixed. Direct-path regressions, saved-card/cancellation gating, no-evaluate assertions, and desktop acceptance for confirmed save without evaluation. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P12-REG-01 | Master 12.1, 12.6, 24; Plan 12 | Evidence owner: mixed. Existing graph/backend/frontend/full-suite gates proving one Agent/decision/ToolNode, seven tools, six-pass limit, and desktop regressions. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P13-JD-01 | Master 11.2, 13.4; Plan 13 Provider-visible source contract | Evidence owner: automated. Inspect actual provider-bound payload; focused pytest on provider/runtime/ToolNode owners; early side-effect-free inline `.venv` probe printing only `SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS` or `SAVE_JOB_PROVIDER_SCHEMA_PROBE=FAIL`. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P13-JD-02 | Master 12.1-12.6, 20; Plan 13 One bounded strict repair | Evidence owner: automated. Binding-aware RED fake, exact normal/repair binding arguments, first/repair invocation counts, sanitized `caplog` (`passive_jd_call_rejected`), refusal checks, topology assertions. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P13-JD-03 | Master 6.4, 11.2, 13.4, 15.7; Plan 13 Confirmation, side effects, and durable truth | Evidence owner: mixed. Public SSE/integration spies for exact durable lookup boundaries and automated counters; browser-owned durable state/delta/network/console slice only. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P13-A11Y-01 | Plan 12 Objective/Scope; Master 15.3, 15.7; Plan 13 Source dialog accessibility | Evidence owner: mixed. Testing Library `getByRole('dialog', {name: 'Nguồn từ CV'})` plus evidence/no-fetch/PDF/close/Escape/focus regressions; browser accessibility observation. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P13-DIAG-01 | Master 16.2, 17.2, 24; Plan 13 Deterministic diagnostic coverage | Evidence owner: automated. Fake-backed timeout/429/malformed/model-absence/dimension/ordering and PDF aggregate negatives; project-interpreter positive pypdf and final ShopAIKey diagnostic pair. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P13-CV-01 | Master 10.5, 15.2, 24.4; Plan 13 two-CV browser evidence | Evidence owner: browser. Named project `jobagent-plan13-smoke`; fixtures `digital_cv_01.pdf` (A) and `digital_cv_02.pdf` (B); exact A/B lifecycle in [`cv_manager_checklist.md`](cv_manager_checklist.md) Plan 13 section. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |
| P13-EVID-01 | Master 24, 27; Plan 13 Traceability and browser evidence | Evidence owner: mixed. This ledger plus matrix supplement; immutable `BASE-PJD-01..03`; append-only attempts; separate warnings; frozen-candidate automated and browser evidence with first-failure retention. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); scaffold only. |
| P13-REG-01 | Master 12.1, 12.6, 24, 27; Plan 13 regression gate | Evidence owner: mixed. Focused/full backend/frontend/static/build/Compose/browser/structure/scope gates on the frozen candidate. | NOT RUN | — | — | — | Seeded by Plan 13 Batch04 (04A); no execution claim. |

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
| — | — | — | — | — | — | — | No Plan 13 execution attempts yet. Seeded empty by Batch04 (04A). |

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
