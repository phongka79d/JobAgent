# Plan_13: Passive JD Reliability, Source Dialog Accessibility, And Release Revalidation

## Objective

Repair the current Plan 12 desktop baseline so every clear passively pasted
English/Vietnamese JD reaches the existing pre-mutation confirmation boundary,
the active-CV evidence dialog has the accessible name **Nguồn từ CV**, and the
identified diagnostic/browser/traceability gaps receive deterministic evidence for
one frozen candidate identity.

The phase must fix the provider-to-Agent boundary rather than weaken runtime
validation: the provider sees one ShopAIKey-compatible ordinary `type='object'`
`save_job` schema with `url`, `text`, `source`, and bounded `preview` properties,
while `SaveJobInput` remains the strict authority for source exclusivity, unknown
fields, and preview rules. The normal binding has no forced choice; the existing
decision node makes at most one source-only repair using the canonical OpenAI
function-choice object. Only a runtime-validated
`save_job(source='current_message', preview?)` call reaches the existing
ToolNode/interrupt path. Invalid repaired calls retain the fixed truthful refusal.
Before confirmation, cancel, save, duplicate, and replay paths preserve the exact
durable-source and side-effect contracts already owned by Plan 12.

This is a `bugfix` increment with **Master impact: none**. Master Version 1.9
already requires recognizable passive JDs to show the unsaved confirmation,
requires zero pre-action mutation and the evidence-backed source dialog, and
requires the diagnostic/failure behavior being revalidated. Plan 12's accepted
Objective/Scope plus the approved Plan 13 design require that dialog's accessible
name. No architecture, public API, database schema, stack, deployment, tool count,
or product boundary is changed.

## Source of Truth

- `docs/plans/Master_plan.md`: `## 1. Project Objective`, specifically readable
  active-CV answers and confirmed passive JD saving.
- `docs/plans/Master_plan.md`: `### 6.4 Transaction boundaries`,
  `### 11.2 Pasted-text confirmation boundary`, `## 12. Agent Architecture`,
  `### 13.4 save_job`, `### 14.2 SSE contract`, and
  `### 15.7 Readable Agent responses and pasted-JD confirmation`.
- `docs/plans/Master_plan.md`: `### 16.2 Startup/diagnostic compatibility checks`,
  `## 20. Failure and Recovery Policy`, `## 24. Local Testing Strategy`,
  `### Phase 10 - Readable Agent responses, active-CV sources, and pasted-JD
  save confirmation`, and `## 27. Definition of Done`.
- `docs/plans/Plan_12.md`: implemented current-message source, strict runtime
  input, one repair/refusal, interrupt/save/cancel/replay, active-CV evidence,
  Astryx dialog/card, and desktop verification baseline.
- `docs/plans/Plan_11.md`: accepted exact-name `save_job`, CV Manager, saved-JD,
  deletion, activation/currentness, and truthful desktop repairs that remain
  immutable inputs.
- `docs/plans/Plan_1.md`: provider diagnostic and pypdf positive/negative exit
  contracts whose deterministic negative tests are completed in this phase.
- `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md`:
  approved provider-boundary, accessibility, diagnostics, and evidence design.
- `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md`:
  test-first implementation sequence, exact commands, and commit boundaries.
- [ShopAIKey OpenAI Format - Function Calling](https://shopaikey.com/docs/openai-format):
  provider-documented ordinary function schema and tool-binding format.
- **Approved ShopAIKey compatibility correction (2026-07-19):** the current user
  approved the ordinary provider object plus strict runtime-validation split after
  rereading the provider documentation. This correction in `Plan_13.md` supersedes
  conflicting provider-schema-shape and string forced-choice passages in the two
  supporting `docs/superpowers/` sources above; their otherwise aligned behavior,
  tests, and ownership guidance remain supporting input.
- **Approved change:** the current user approved the Plan 13 design on 2026-07-19
  and authorized replacing the Plan 12 terminal boundary with this successor.
- **Change type:** `bugfix`.
- **Master impact:** `none`; the cited Version 1.9 requirements already authorize
  every repaired behavior and explicitly forbid the same scope expansions listed
  below.

## Master Requirement Coverage

| Requirement ID | Master/approved source | Owned outcome | Verification evidence |
|---|---|---|---|
| P13-JD-01 | Master 11.2, 13.4; approved correction | The actual provider-visible `save_job` definition is one ShopAIKey-compatible ordinary object with `url`, `text`, `source`, and bounded `preview` properties and no required provider-side `oneOf`, `const`, nested `anyOf`, or unknown-field enforcement. Injected state stays absent, and `SaveJobInput` remains the strict runtime authority for exactly one source, unknown-field rejection, and preview rules. | OpenAI-format schema inspection, the standalone side-effect-free inline `.venv` probe immediately after provider-schema implementation, runtime validation, ToolNode injection, and direct-path tests. |
| P13-JD-02 | Master 12.1-12.6, 20; approved correction | An obvious passive JD receives at most one repair bound only to the compatible `save_job` definition with canonical OpenAI forced choice `{"type":"function","function":{"name":"save_job"}}`; one runtime-valid source-only call reaches ToolNode, while a still-invalid repair produces fixed no-confirmation text and zero tool execution. | Binding-aware RED fake, exact normal/repair binding arguments, first/repair invocation counts, sanitized `caplog` proof, refusal checks, and topology assertions. |
| P13-JD-03 | Master 6.4, 11.2, 13.4, 15.7 | Confirmation remains pre-mutation; save/cancel/replay use one durable execution and exact source, with zero automatic evaluation and exact side-effect counts. | Public SSE/integration branch spies prove one pre-interrupt lookup plus exactly one fresh accepted-save re-entry lookup. The current implementation's cancel re-entry also performs exactly one fresh lookup and records two reads total, but this is regression evidence rather than a new product precondition. Save-only ingestion, row/call counts, duplicate/terminal replay, and separately owned desktop state/delta evidence remain exact. |
| P13-A11Y-01 | Plan 12 Objective/Scope; Master 15.3, 15.7; approved design | The active-CV evidence modal is discoverable as `dialog` named **Nguồn từ CV** while exact records, partial notice, no-fetch behavior, original PDF, Escape/close/focus return remain unchanged. | Testing Library role/name and interaction tests plus browser accessibility observation. |
| P13-DIAG-01 | Master 16.2, 17.2, 24 | Timeout, 429, malformed response, missing model, dimension mismatch, ordering mismatch, `<4/5` digital PDF success, and accidental image-only acceptance each have deterministic non-zero/redacted diagnostic tests. | Fake transport/payload/aggregate tests and one sanitized project-interpreter diagnostic rerun. |
| P13-CV-01 | Master 10.5, 15.2, 24.4 | A disposable two-CV browser flow freshly proves archived reprocess/activation/delete, active evidence/graph selection, and shared-data preservation. | In-app browser actions, public network/events, sanitized state evidence, fixed-port Compose preflight/restoration, and named-project-only teardown. |
| P13-EVID-01 | Master 24, 27; approved design | P12 and P13 cases have a dated execution ledger with status, date, candidate identity/project, run IDs, failure/log evidence, resolution, explicit automated counters, and separately recorded browser-observable deltas/state. | Matrix supplement, seeded baseline failure IDs, `plan13_acceptance_ledger.md`, frozen-candidate full gates, failure-preserving rows, A3 commit reference, and a separate non-blocking-warning section. |
| P13-REG-01 | Master 12.1, 12.6, 24, 27 | One Agent, one decision node, one ToolNode, seven tools, six passes, existing APIs/schema/dependencies, direct URL/text, profile approval, saved-JD/evaluation, matching, and Plan 11 repairs remain green. | Focused/full backend/frontend/static/build/Compose/browser/structure/scope gates. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Plans 1-11 | Stable runtime, diagnostics, profile/CV lifecycle, Agent/tool persistence, direct JD ingestion, graph/matching, saved-JD actions, and accepted desktop repairs | Run current focused tests and preserve all unrelated behavior as regression input. |
| Plan_12 | Runtime `SaveJobInput`, current-message resolver, strict pending card, interrupt/save/cancel/replay, active-CV evidence/dialog, and one repair/refusal | Reproduce the provider-schema mismatch and unnamed dialog before changes; do not rewrite ingestion/evidence/card owners. |
| Approved design and implementation plan | Exact provider-boundary, accessibility, diagnostic, ledger, and browser decisions | Confirm no unresolved design choice or Master amendment is required. |
| Pre-append plan-set baseline | Plans 1-12 were contiguous with Plan 12 terminal | Retain the pre-append validator evidence; the current validator must see contiguous Plans 1-13 with only Plan 13 terminal. |
| Local project environment | `.venv` Python 3.13, frontend lockfile, root `.env`, Docker Compose, and synthetic fixtures | Use `.venv\Scripts\python.exe` for Python/package diagnostics; never use real data or normal user volumes for destructive checks. |

## Scope

- Add one provider-visible ShopAIKey-compatible OpenAI-format definition for the
  existing `save_job` tool: one ordinary object with `url`, `text`, `source`, and
  bounded `preview` properties, without provider-side combinator dependencies.
- Keep the original runtime tool instance for ToolNode injection/execution and
  keep `SaveJobInput` as the authoritative exactly-one-source, unknown-field, and
  preview validator.
- Bind the normal Agent model to the compatible provider definition without a
  forced choice. The single passive repair binds only that same `save_job`
  definition with `{"type":"function","function":{"name":"save_job"}}`;
  validate before dispatch and preserve one repair/refusal.
- Add the required `ponytail:` comment beside the provider-schema owner explaining
  that ShopAIKey has not verified `oneOf`/`const`/nested `anyOf` support and that
  provider combinators may be restored only after a documented compatibility probe.
- Run the standalone side-effect-free inline `.venv` compatibility probe from
  Implementation step 2 immediately after the compatible provider definition
  is implemented and before continuing with graph repair. It prints only
  `SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS|FAIL`, contains no real JD or provider
  payload, never dispatches ToolNode, and blocks on provider rejection or
  malformed output with no permissive fallback.
- Emit only fixed-shape sanitized repair diagnostics and add a `caplog` proof that
  source content, values, objects, provider payloads/responses, prompts, and
  secrets cannot enter those logs.
- Add public-path/integration coverage whose fake seams own exact counters for Job
  ingestion, JD extraction, embedding, evaluation, and Neo4j sync, plus automated
  Job/evaluation row and durable execution assertions before/after
  save/cancel/replay.
- Add `aria-label='Nguồn từ CV'` to the existing outer Astryx `Dialog` and a
  role/name assertion without changing dialog/evidence composition.
- Add deterministic Plan 1 negative diagnostic/PDF gate tests using fake
  transports/payloads/aggregates and the existing failure-code/redaction owners.
- Add a P12/P13 supplement to the functional matrix and a dated Plan 13 acceptance
  ledger with result/date/candidate-identity/project/run/failure/resolution fields.
- Recreate a disposable two-CV state and exercise archived reprocess/activation/
  delete plus Plan 12 source/passive-JD paths through the in-app browser as a user.
- Run focused/full/static/build/Compose/plan-structure/scope gates on the final
  candidate and record first failures rather than replacing them silently.

## Out of Scope

- New endpoint, SSE event/envelope, migration/table/column, dependency, tool name,
  Agent/node/ToolNode, state field, worker/queue, model/provider, or deployment rule.
- A second confirmation route/store/reducer, a general intent classifier, expanded
  marker/opt-out lists, unbounded retries, or silent mixed-call argument stripping.
- Automatic evaluation, scoring/currentness changes, saved-JD API changes, or
  changes to direct URL/text and **Lưu JD & đánh giá lại** semantics.
- Reimplementation of Plan 11 F-01 through F-05, CV/JD deletion coordinators,
  Plan 12 Markdown/evidence/card/history ownership, or active-CV reader contracts.
- Mobile/narrow-layout acceptance, security/penetration/abuse work, real data, or
  production hardening.
- Cleanup of non-blocking jsdom `window.scrollTo`, duplicate synthetic React key,
  Vite bundle-size, `aiosqlite` deprecation, or bare-host Python/pypdf environment
  warnings.
- Changing the five-batch/eight-task execution shape, marking task progress,
  running A1/A2/A3 implementation, or resuming the abandoned orchestration run
  during this correction pass. `docs/tasks/task_13.md` is revised only to match
  this corrected plan and remains fully unchecked for a fresh run.
- Treating the per-task commit snippets in the supporting implementation plan as
  unconditional authority. Later execution commits are owned by the
  orchestrator/A3 workflow; those snippets are conditional guidance only.
- Restoring, editing, staging, or otherwise absorbing the unrelated pre-existing
  deletion of
  `docs/superpowers/specs/2026-07-19-frontend-functional-e2e-audit-design.md`.

## Target Directory Structure

```text
README.md                        # update only when commands/status become stale; otherwise record unchanged
backend/
  app/
    adapters/shopaikey_chat.py
    agent/graph.py
    schemas/jobs.py
    tools/jobs.py
  tests/
    fakes/
      fake_chat_model.py
    unit/
      test_agent_graph.py
      test_job_save_confirmation.py
      test_phase0_diagnostics.py
      test_shopaikey_chat.py
    integration/
      test_chat_api.py
      test_job_tools.py
frontend/src/
  features/chat/components/ActiveCvSourceDialog.tsx
  test/
    active-cv-source.test.tsx
    assistant-response.test.tsx
infrastructure/scripts/
  verify_pdf_extraction.py          # conditional pure aggregate repair only
  shopaikey_diag/                 # each file below changes only for a reproduced mapping/redaction defect
    chat_checks.py
    common.py
    embeddings.py
    runner.py
docs/
  acceptance/
    full_functional_test_matrix.md
    plan13_acceptance_ledger.md
    cv_manager_checklist.md
  plans/
    Plan_12.md                    # terminal boundary converted to successor handoff only
    Plan_13.md
```

Existing equivalent owners remain preferred when the required search shows a
test/helper already belongs there. Do not duplicate runtime validation, tool
execution, interrupt, evidence, diagnostic-code, or browser-state logic.
The approved design and supporting implementation plan under `docs/superpowers/`
and `infrastructure/scripts/diagnose_shopaikey.py` are read-only inputs during
later execution; they are not implementation targets.

## Technical Specifications

### Provider-visible source contract

- The provider-visible parameters use the subset demonstrated by ShopAIKey's
  Function Calling documentation: one `type='object'` with ordinary `properties`.
  It does not set OpenAI `strict=True` and does not require provider support for
  `oneOf`, `const`, nested `anyOf`, branch-local `required`, or
  `additionalProperties=false`.
- Reuse the established ordinary-object binding pattern in
  `infrastructure/scripts/shopaikey_diag/tools_schema.py`; do not invent a second
  provider-format abstraction.
- `schemas/jobs.py` owns one JSON-schema parameters builder using the existing
  preview constants. Its top-level properties are exactly `url`, `text`, `source`,
  and `preview`. URL/text/source use ordinary string schemas and descriptions;
  preview remains an ordinary nested object with the existing title/company/skill/
  text-length bounds but no combinator or provider-side unknown-field dependency.
- Provider schema simplicity is not permission for mixed input. `SaveJobInput`
  remains the runtime authority and must reject zero/multiple sources, unknown
  fields, any `source` other than `current_message`, preview outside the
  current-message mode, unknown preview fields, and every existing over-limit
  value before ToolNode dispatch.
- The provider-schema owner includes a `ponytail:` comment stating the deliberate
  compatibility limitation and upgrade path: restore provider combinators only
  after ShopAIKey documents or a sanitized compatibility probe verifies them.
- `tools/jobs.py` wraps those parameters in one OpenAI-format function definition.
  One `SAVE_JOB_DESCRIPTION` constant supplies both that definition and the
  existing `@tool(SAVE_JOB_NAME, description=SAVE_JOB_DESCRIPTION)` decorator;
  the runtime body, injected arguments, and docstring remain unchanged. It does
  not create another LangChain tool or ingestion path.
- The compatible OpenAI-format definition is bound only to the model. Normal model
  binding substitutes it for provider-visible `save_job` without `tool_choice`,
  while ToolNode continues to receive the original registry `BaseTool`; injected
  `tool_call_id`/`state`, `SaveJobInput` runtime validation, execution/replay, and
  interrupt therefore work exactly as before.
- Tests inspect the actual OpenAI-format/bound payload and prove injected fields
  are absent and the provider schema contains the expected ordinary properties
  without `oneOf`, `const`, or nested `anyOf`. They also prove the model binding
  log contains the compatible dictionary with no normal forced choice
  while `bundle.tool_node.tools_by_name[SAVE_JOB_NAME]` remains the identical
  runtime `BaseTool`. Pydantic tests independently prove exactly-one-source,
  mixed/unknown/source/preview/bounds rejection.
- Immediately after this boundary is implemented, run the standalone inline
  `.venv` probe in Implementation step 2 against this exact compatible ordinary
  definition. It is side-effect-free, uses no real JD or provider payload,
  dispatches no ToolNode, and prints only
  `SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS|FAIL`. Provider rejection, malformed
  output, or failure to emit the forced synthetic
  `source='current_message'` call exits non-zero and blocks subsequent repair
  work; it must not rebuild or retry with the old permissive schema. The later
  positive `infrastructure/scripts/diagnose_shopaikey.py` command remains the
  final general compatibility rerun, not the owner of this early probe.

### One bounded strict repair

- Extend `bind_chat_tools` with an optional keyword-only `tool_choice`; omit the
  provider argument for every normal binding and pass exactly
  `{"type":"function","function":{"name":"save_job"}}` only for the passive
  repair binding.
- Build the normal and repair runnables from the same base chat model. The normal
  binding retains all seven registered capabilities with no forced choice; the
  repair binding exposes only the compatible `save_job` definition.
- Preserve decision precedence: clear opt-out, positive exact-name path, sole-URL
  exclusion, then obvious passive JD. The first response and repaired response
  both pass `_is_sole_current_message_save_job_call` before dispatch.
- Make exactly one repair model invocation. A still-invalid response yields
  `PASSIVE_JD_NO_CONFIRMATION_TEXT`, zero tool passes, and no mutation. Do not
  synthesize a call or strip non-empty mixed arguments.
- The regression fake is binding-aware: it emits a valid source-only repair only
  when the bound provider definition contains the expected compatible ordinary
  object properties **and** the binding carries the exact canonical forced-choice
  object; otherwise it repeats a mixed-source call. The test must fail when either
  binding condition is absent, so a scripted mixed-then-valid fake is insufficient
  as the RED case.
- Repair/refusal logging uses the prefix `passive_jd_call_rejected` and only a
  fixed rejection category (`invalid_first_call` or `invalid_repair_call`), integer
  call count, tool-name list, and argument-key-name list. It never logs raw JD text,
  preview content, argument values or argument/tool-call objects, provider request/
  response payloads, prompt content, credentials, authorization headers, or secrets.
  A sentinel-based `caplog` test must prove all prohibited content is absent while
  the four allowed fields remain observable.
- Keep `tool_iteration_count`, route logic, Agent state, graph nodes, and the
  configured six-pass guard unchanged.

### Confirmation, side effects, and durable truth

- The current-message tool must still resolve `run_id -> user_message_id -> exact
  durable user message`, interrupt before provider/ingestion dependencies, and
  remain one `running` tool execution.
- Source-read assertions distinguish the two required read boundaries: exactly one
  durable lookup chain occurs before the initial `interrupt()` to validate the
  initiating message/build the card, then accepted-save LangGraph re-entry performs
  exactly one fresh durable lookup before the resumed interrupt yields the action.
  Save therefore uses two lookup chains total and never a separate third reload.
  The current cancel re-entry performs the same one fresh lookup and its regression
  test records two reads total, but this implementation invariant is not a new
  product precondition. Cancellation remains defined by zero ingestion/mutation.
- The `tools/jobs.py` current-message branch reuses its initial lookup for opt-out
  validation and confirmation construction. On LangGraph re-entry, its one fresh
  lookup supplies the content passed directly to ingestion. Remove the former
  unconditional pre-branch lookup and separate post-decision reload; direct URL/
  text modes retain the shared opt-out lookup and their existing outcomes.
- Automated fake spies exclusively own exact `ingest_raw_text`, JD extraction,
  embedding, evaluation, and Neo4j sync call counters. Before action and after
  cancel every value is zero even though cancel re-entry performs the fresh source
  lookup. The first created save performs one ingestion, extraction, embedding, and
  Neo4j sync call and zero evaluation dispatches; replay and exact-hash dedupe retain
  their branch-specific zero-repeat counts. Automated database assertions separately
  own exact Job/evaluation row counts.
- Save uses that one fresh re-entry lookup as its ingestion source, preserves
  `created|returned|retried`, and never dispatches evaluate. Cancel uses the same
  current re-entry path but, after the normal Agent recognition/repair calls,
  performs zero `ingest_raw_text`, JD-extraction/embedding-provider, evaluation,
  Neo4j, or SQLite side effects. Repeated content returns one Job identity, and
  duplicate/terminal resume performs no explicit third reload or repeated work.
- Pending/SSE/history/card payloads retain the strict redaction/preview bounds;
  raw JD, message ID, URL/hash, prompt/provider data, and injected state never
  appear outside accepted existing owners.

### Source dialog accessibility

- Add `aria-label={ACTIVE_CV_SOURCE_DIALOG_TITLE}` to the current outer Astryx
  `Dialog`. Astryx `BaseProps` already supports `aria-*`; no package/internal or
  hand-built modal change is needed.
- Testing Library must find `getByRole('dialog', {name: 'Nguồn từ CV'})`.
- Existing exact record/page order, repeated-record preservation, partial notice,
  zero evidence/chunk network request, evidence attachment PDF, close button,
  Escape behavior, scroll containment, title focus, and trigger-focus return are
  separate mandatory assertions.

### Deterministic diagnostic coverage

- Use fake `httpx` exceptions/responses and existing diagnostic functions to force
  timeout, 429, malformed non-stream response, missing chat/embedding model,
  wrong vector dimension, and ordering/index mismatch. Every case asserts non-zero
  exit, stable code/capability, terminal FAIL marker, and secret/header redaction.

  | Deterministic case | Failure code | Capability | Terminal evidence |
  |---|---|---|---|
  | Timeout | `TIMEOUT` | `basic_chat` | Non-zero; `SHOPAIKEY_COMPATIBILITY=FAIL` |
  | HTTP 429 | `RATE_LIMIT` | `basic_chat` | Non-zero; `SHOPAIKEY_COMPATIBILITY=FAIL` |
  | Malformed transport/non-stream JSON | `MALFORMED_RESPONSE` | `basic_chat` | Non-zero; `SHOPAIKEY_COMPATIBILITY=FAIL` |
  | Missing configured chat/embedding model | `MODEL_ABSENCE` | `model_discovery` | Non-zero; `SHOPAIKEY_COMPATIBILITY=FAIL` |
  | Unlocked missing chat model at CLI gate | `MODEL_ABSENCE` | `config` | Exit `1`; `SHOPAIKEY_COMPATIBILITY=FAIL` |
  | Wrong vector dimension | `DIMENSION_MISMATCH` | `scalar_batch_embeddings` | Non-zero; `SHOPAIKEY_COMPATIBILITY=FAIL` |
  | Duplicate/out-of-order vector indexes | `ORDERING_MISMATCH` | `scalar_batch_embeddings` | Non-zero; `SHOPAIKEY_COMPATIBILITY=FAIL` |

- Force the pypdf aggregate with three of five digital passes and separately with
  an accepted image-only row. Both return non-zero with the existing FAIL markers;
  no OCR/parser fallback or new fixture is added.
- Use the project `.venv` interpreter for the standalone early blocking inline
  ShopAIKey schema probe, one final positive pypdf diagnostic, and the later final
  general `diagnose_shopaikey.py` compatibility rerun on the candidate. Only the
  inline probe owns the early strict-schema gate; the diagnostic script owns the
  final general rerun. These are intentional sanitized provider calls; normal
  automated tests remain fake-backed. Bare-host missing `pypdf` remains an
  environment classification, not a product change.

### Traceability and browser evidence

- `full_functional_test_matrix.md` adds rows with methods, expected behavior, and a
  ledger reference for exactly these IDs; it does not claim execution status:

  ```text
  P12-RSP-01, P12-RSP-02
  P12-CV-01, P12-CV-02, P12-CV-03, P12-CV-04, P12-CV-05
  P12-JD-01, P12-JD-02, P12-JD-03, P12-JD-04, P12-JD-05, P12-REG-01
  P13-JD-01, P13-JD-02, P13-JD-03, P13-A11Y-01, P13-DIAG-01,
  P13-CV-01, P13-EVID-01, P13-REG-01
  ```
- `plan13_acceptance_ledger.md` owns `ID`, requirement/source, procedure/command,
  status, UTC date, candidate identity/named Compose project for that attempt,
  failure/log evidence, and resolution/notes. Candidate identity is the base HEAD
  plus content-manifest fingerprint before A3. The A3 handoff reports the eventual
  committed SHA; the ledger must not require a self-referential SHA inside that same
  commit.
  Initial requirement status is `NOT RUN`; after execution only `PASS`, `FAIL`,
  `BLOCKED`, or `SKIPPED (reason)` is allowed.
- In each requirement row, the procedure/command field declares `Evidence owner:
  automated`, `browser`, or `mixed`. Automated-only schema, diagnostic, fake-counter,
  and regression rows link exact command output and are never presented as browser
  observations; browser execution covers only browser-owned rows and the browser
  slice of mixed rows.
- Seed the immutable **Preserved pre-repair failures** table with these exact rows;
  they contain no raw JD/provider content and are never rewritten as PASS:

| Attempt ID | UTC date | Product HEAD / project | Run ID | Observed result | Root cause / disposition |
|---|---|---|---|---|---|
| `BASE-PJD-01` | 2026-07-19 | `887d4f6` / pre-repair audit stack | `4971481e-0e7b-42ca-8d7b-184d314be2e9` | FAIL: `tool_count=0`; fixed no-confirmation response | Provider/Agent boundary reliability failure; schema shape alone was not proven as the sole root cause. Preserve and append a new synthetic repair attempt. |
| `BASE-PJD-02` | 2026-07-19 | `887d4f6` / pre-repair audit stack | `d1fab78d-a4ff-4a9d-ad06-75d5cd229c8a` | FAIL: `tool_count=0`; fixed no-confirmation response | Same observed boundary failure with root cause unresolved by this historical row; preserve the first result. |
| `BASE-PJD-03` | 2026-07-19 | `887d4f6` / pre-repair audit stack | `5a12595d-7af4-4b64-a03b-433c08d87293` | FAIL: `tool_count=0`; fixed no-confirmation response | Long MISA-like case; preserve the first result and use only synthetic rerun content. |

- Add a separate append-only **Execution attempts** table keyed by requirement and
  attempt suffix, for example `P13-JD-02-A1` and `P13-JD-02-A2`. A rerun appends
  rather than overwriting A1, and the requirement row may summarize an accepted
  result only when it links every earlier attempt.
- Keep jsdom `window.scrollTo`, duplicate synthetic React key, Vite bundle-size,
  `aiosqlite` deprecation, and bare-host Python/pypdf environment observations in
  a separate **Non-blocking warnings (out of scope)** table with `warning`,
  `command/surface`, `classification`, `behavioral impact`, and `disposition`
  columns. They never replace or dilute functional PASS/FAIL rows.
- `plan13_acceptance_ledger.md` is the dated Plan 13 supplement to the existing
  Master 19 `manual_jd_checklist.md`; it preserves rather than replaces the
  historical Plan 6 acceptance evidence.
- Browser acceptance uses `jobagent-plan13-smoke`, synthetic CVs/JDs, desktop
  `localhost:5173`, and user interactions. It records actual run IDs and sanitized
  counts but no raw bodies/provider transcripts/secrets.
- Browser evidence owns only observable SQLite Job/evaluation deltas, Neo4j Job/
  active-CV deltas, durable run/tool-execution state, network requests, console,
  and sanitized backend logs. It must not claim to observe the automated fake-spy
  or exact provider counters; those belong only to the automated gate above.
- Browser CV A is `backend/tests/fixtures/cv/digital_cv_01.pdf`; CV B is
  `backend/tests/fixtures/cv/digital_cv_02.pdf`. After A becomes active again, ask
  `What is the most recent role and company in my CV?`; the evidence-backed answer
  must be `Senior Software Engineer at Northwind Labs` from A, not B's
  `Data Engineer at Fabrikam Analytics`, and the dialog must display the exact
  returned record.
- The two-CV flow approves A, approves B (archiving A), reprocesses/approves A,
  proves active evidence/graph A, then deletes archived B and proves owned cleanup
  plus shared Job/Skill preservation.
- Use these complete synthetic passive-JD inputs; do not invent browser bodies at
  execution time:

  English cancel fixture:

  ```text
  P13-JD-EN-SENTINEL
  Job Description: Plan13 Labs is hiring a Synthetic Platform Engineer for a local portfolio team in Hanoi.
  Responsibilities: Build and maintain FastAPI services, design deterministic integration tests, review SQLite transactions, and keep Neo4j synchronization observable and retry-safe.
  Requirements: At least two years of Python backend experience, strong SQL knowledge, and practical Docker skills.
  Qualifications: Experience with REST APIs, pytest, Git, typed data models, and clear technical documentation.
  Skills: Python, FastAPI, SQL, Docker, pytest, Neo4j, and TypeScript collaboration.
  Location: Hanoi; hybrid work; this is entirely synthetic acceptance data.
  ```

  Vietnamese save/dedupe fixture:

  ```text
  P13-JD-VI-SENTINEL
  Mô tả công việc: Plan13 Labs tuyển Kỹ sư API Tổng hợp cho nhóm sản phẩm thử nghiệm tại Hà Nội.
  Trách nhiệm: Xây dựng dịch vụ FastAPI, viết kiểm thử tích hợp xác định, rà soát giao dịch SQLite và duy trì đồng bộ Neo4j an toàn khi chạy lại.
  Yêu cầu: Có kinh nghiệm Python backend, SQL, Docker, Git và mô hình dữ liệu có kiểu rõ ràng; biết phân tích lỗi đến nguyên nhân gốc.
  Kỹ năng: Python, FastAPI, SQL, Docker, pytest, Neo4j và phối hợp TypeScript.
  Quyền lợi: Môi trường học tập minh bạch, phản hồi rõ ràng và lịch làm việc hybrid.
  Địa điểm: Hà Nội; toàn bộ nội dung này là dữ liệu kiểm thử tổng hợp.
  ```

  Long MISA-like cancel fixture:

  ```text
  P13-JD-LONG-SENTINEL
  Mô tả vị trí: Công ty Phần mềm Tổng hợp tuyển Kỹ sư Nền tảng cho hệ thống quản trị doanh nghiệp dùng trong bài kiểm thử cục bộ.
  Mô tả công việc: Phân tích yêu cầu nghiệp vụ, thiết kế API ổn định, xây dựng luồng xử lý dữ liệu và phối hợp với nhóm giao diện để phát hành tính năng có thể kiểm chứng.
  Trách nhiệm: Viết mã Python và FastAPI dễ bảo trì; tạo kiểm thử đơn vị và tích hợp; theo dõi lỗi; rà soát giao dịch SQLite; kiểm tra đồng bộ Neo4j; ghi lại quyết định kỹ thuật và bằng chứng phát hành.
  Yêu cầu: Tối thiểu hai năm kinh nghiệm phát triển backend; sử dụng tốt SQL, Git và Docker; hiểu REST, mô hình dữ liệu, xử lý lỗi và nguyên tắc không lặp side effect.
  Kỹ năng: Python, FastAPI, SQL, Docker, pytest, Neo4j, TypeScript, phân tích hệ thống và giao tiếp kỹ thuật.
  Quyền lợi: Được hướng dẫn theo mục tiêu rõ ràng, tham gia đánh giá mã, học quy trình kiểm thử xác định và làm việc hybrid tại Hà Nội.
  Thông tin bổ sung: Không có dữ liệu người thật, không có bí mật và không yêu cầu tự động nộp hồ sơ; đây chỉ là JD tổng hợp cho Plan 13.
  ```

- The opt-out fixture is the complete English fixture followed by the exact final
  line `Không lưu JD này.`. The ambiguous fixture is these five exact lines; it
  exceeds 300 non-whitespace characters but contains none of the approved JD
  markers:

  ```text
  Tôi đang suy nghĩ về hành trình nghề nghiệp, cách học tốt hơn trong năm nay và những thói quen giúp bản thân duy trì sự tập trung, nhưng đây chỉ là chia sẻ cá nhân chứ không phải thông tin tuyển dụng.
  Tôi đang suy nghĩ về hành trình nghề nghiệp, cách học tốt hơn trong năm nay và những thói quen giúp bản thân duy trì sự tập trung, nhưng đây chỉ là chia sẻ cá nhân chứ không phải thông tin tuyển dụng.
  Tôi đang suy nghĩ về hành trình nghề nghiệp, cách học tốt hơn trong năm nay và những thói quen giúp bản thân duy trì sự tập trung, nhưng đây chỉ là chia sẻ cá nhân chứ không phải thông tin tuyển dụng.
  Tôi đang suy nghĩ về hành trình nghề nghiệp, cách học tốt hơn trong năm nay và những thói quen giúp bản thân duy trì sự tập trung, nhưng đây chỉ là chia sẻ cá nhân chứ không phải thông tin tuyển dụng.
  Tôi đang suy nghĩ về hành trình nghề nghiệp, cách học tốt hơn trong năm nay và những thói quen giúp bản thân duy trì sự tập trung, nhưng đây chỉ là chia sẻ cá nhân chứ không phải thông tin tuyển dụng.
  ```
- The passive-JD browser matrix uses this single terminal order:
  1. paste the English passive JD containing `P13-JD-EN-SENTINEL`, show its card,
     and cancel;
  2. paste the Vietnamese passive JD containing `P13-JD-VI-SENTINEL`, refresh
     while pending, verify the same
     run/execution/card and composer lock rehydrate from durable history, then save;
  3. repeat that exact Vietnamese JD, show and confirm its card, then verify the
     returned/deduplicated outcome uses the same Job identity with no evaluation;
  4. paste the long MISA-like JD containing `P13-JD-LONG-SENTINEL`, show its card,
     and cancel it, leaving no interrupted run;
  5. send the sole URL `https://example.com/jobs/plan13-synthetic-engineer` and
     verify the existing direct-URL/no-card path. Only routing, absence of passive
     confirmation, and zero evaluation are asserted; fetch/ingestion may terminate
     with the existing safe URL failure because this URL is not a live JD fixture;
     and
  6. use this exact explicit direct-text request, with no placeholder:

     ```text
     Please call save_job exactly once with text="Job title: Synthetic API Engineer. Company: Plan13 Labs. Responsibilities: build local APIs and deterministic tests. Requirements: Python, FastAPI, SQL, and Docker. Location: Hanoi. This is synthetic test data." Do not use source=current_message and do not call match_jobs.
     ```

     Record that it follows the direct text path without the passive card and never
     evaluates; then
  7. exercise the complete opt-out fixture and complete five-line ambiguous fixture
     above as separate terminal turns. Neither may be forced into a save.
- After the pending refresh, the browser network evidence must show the history GET
  and exactly one resume POST after the click. Any unexpected console error, failed
  request, duplicate resume, or visible/durable-state mismatch makes that attempt
  FAIL. Sanitized backend logs must contain none of the three JD sentinels and any
  `passive_jd_call_rejected` line must match only
  `reason=(invalid_first_call|invalid_repair_call) call_count=[0-9]+ tool_names=.* argument_keys=.*`;
  raw/preview/argument/provider/prompt sentinels must remain absent.
- Before final gates, freeze the product/test/config candidate and record its
  identity as the base HEAD plus a SHA-256 content-manifest fingerprint covering
  every modified, deleted, or untracked product, test, dependency, and configuration
  path, excluding append-only acceptance evidence; deleted paths use the literal
  manifest value `DELETED`. Later evidence-only ledger/checklist edits after that
  freeze require fresh structure/link/
  whitespace checks, not a repeated live provider/browser run. Any later product,
  test, dependency, or configuration edit invalidates the affected evidence and
  requires those gates to rerun. A3 reports the eventual committed SHA in its
  handoff and performs post-commit plan/diff revalidation. A separately authorized
  evidence-only follow-up may record that product commit as a parent reference.

### Compose preflight, isolation, and restoration

- Execute the smoke lifecycle as one PowerShell `try/finally` transaction. Before
  any stop, record `config --services`, `ps -a` state for every expected service,
  per-component/overall health, and PID/process/project ownership for every fixed
  port. The `finally` block always attempts named-smoke teardown and exact prior-
  normal-state restoration; if restoration fails, retain the recovery-state file
  and block acceptance rather than discarding the evidence needed to recover.
- `jobagent-plan13-smoke` uses the same fixed loopback ports as the normal workspace
  stack. Before startup, capture configured services from `config --services`, the
  normal `infrastructure` project's complete running/stopped and component-health
  state, and the process/project owners of ports `5173`, `8000`, `7474`, and
  `7687`. Block on partial/unexpected normal services, an unhealthy running normal
  stack, a pre-existing smoke project, or unrelated fixed-port ownership rather
  than changing any of them.
- When the known normal `infrastructure` stack is fully running and healthy, stop
  only its three containers with
  `docker compose --env-file .env -f infrastructure/docker-compose.yml -p infrastructure stop frontend backend neo4j`.
  Never run normal-project `down`, never remove or rename normal application/Neo4j
  volumes, and verify the fixed ports are free before smoke startup. If the normal
  stack was stopped, leave it stopped and require the ports already to be free.
- Start only `jobagent-plan13-smoke` with
  `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan13-smoke up --build -d --wait --wait-timeout 180`, verify exactly
  `frontend`, `backend`, and `neo4j` plus overall/SQLite/filesystem/Neo4j health,
  and use only synthetic data.
- In finally-style cleanup after success or failure, remove only the named smoke
  project and its named volumes with
  `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan13-smoke down --volumes --remove-orphans`.
  This is the only authorized volume deletion.
- Only when the normal stack was recorded as running, restore its three components
  with
  `docker compose --env-file .env -f infrastructure/docker-compose.yml -p infrastructure up -d --wait --wait-timeout 180`
  and verify the same services plus overall/SQLite/filesystem/Neo4j health. If it
  was stopped, leave it stopped. Never stop, delete, or restore an unrelated
  process/project.

### Ownership and invariants

- `schemas/jobs.py` owns provider parameters plus current runtime models;
  `tools/jobs.py` owns the one provider definition and the bounded current-message
  lookup-flow refactor while preserving runtime outcomes and injected execution;
  `adapters/shopaikey_chat.py` owns generic binding options; `agent/graph.py` owns
  the provider-definition substitution and single repair invocation.
- `ActiveCvSourceDialog.tsx` remains the sole dialog presenter; evidence parser,
  history projector, assistant row, retained-file API, and reducer remain unchanged.
- Existing Phase 0 diagnostic code owns failure codes/redaction. New tests reuse it
  and production changes occur only for a reproduced mismatch.
- One Agent, one decision node, one ToolNode, seven runtime tools, exact statuses,
  one durable replay identity, and `TOOL_LOOP_LIMIT=6` are invariant.
- This correction pass changes only `Plan_13.md` and `task_13.md`; it creates no
  product code and does not mutate abandoned `.agent` evidence. A fresh
  orchestrator run must consume the corrected unchecked task contract. The later
  orchestrator/A3 workflow owns execution commits; any commit commands in the
  supporting implementation plan apply only when that workflow explicitly
  authorizes them.

## Implementation

1. Run the current validator and focused backend/frontend baselines. Reproduce the
   provider/Agent no-confirmation failure, three historical runs, and unnamed dialog;
   do not claim the flat provider schema alone is causal, and save only sanitized
   evidence.
2. Add failing tests for the actual provider definition, runtime source authority,
   and ToolNode injection. Implement the compatible parameters/function definition and
   substitute it only at the normal model binding. Immediately after that
   provider-schema implementation task, run this standalone side-effect-free
   inline `.venv` probe before step 3:

   ```powershell
   @'
   import sys
   sys.path.insert(0, "backend")

   from app.adapters.shopaikey_chat import build_shopaikey_chat
   from app.schemas.jobs import SaveJobInput
   from app.tools.jobs import SAVE_JOB_NAME, save_job_openai_tool_schema

   model = build_shopaikey_chat().bind_tools(
       [save_job_openai_tool_schema()],
       tool_choice={
           "type": "function",
           "function": {"name": SAVE_JOB_NAME},
       },
   )

   def fail() -> None:
       print("SAVE_JOB_PROVIDER_SCHEMA_PROBE=FAIL", file=sys.stderr)
       raise SystemExit(1)

   try:
       message = model.invoke(
           "This is a synthetic compatibility probe. Call save_job using only "
           "source=current_message; do not include url or text."
       )
       calls = list(message.tool_calls or [])
       if len(calls) != 1 or calls[0]["name"] != SAVE_JOB_NAME:
           fail()
       validated = SaveJobInput.model_validate(calls[0]["args"])
       if (
           validated.source != "current_message"
           or validated.url is not None
           or validated.text is not None
       ):
           fail()
   except SystemExit:
       raise
   except Exception:
       fail()
   print("SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS")
   '@ | & '.\.venv\Scripts\python.exe' -
   ```

   The probe contains no real JD or provider payload, dispatches no ToolNode,
   prints only its PASS/FAIL marker, and stops this phase on rejection or malformed
   output. Do not enable a permissive fallback. The general
   `diagnose_shopaikey.py` command is deliberately deferred to the final positive
   diagnostic gate.
3. Add failing adapter/graph tests for forced source-only repair, repeated mixed
   calls, fixed refusal, opt-out/named/URL precedence, invocation counts, topology,
   loop count, binding-aware RED behavior, and sanitized `caplog` output. Implement
   the optional binding choice and single repair runnable.
4. Add public SSE/tool integration spies for confirmation, exact pending projection,
   one pre-interrupt lookup plus exactly one fresh accepted-save re-entry lookup
   (two reads total with no explicit third reload), the current cancel re-entry's
   exact one fresh lookup, save-only ingestion of fresh content, zero pre-action/cancel
   side-effect counters, exact save/dedupe, zero evaluation, and replay. Refactor
   only the current-message
   lookup flow: reuse the first resolved message for opt-out/card construction,
   pass the one re-entry lookup directly to ingestion, remove the unconditional
   pre-branch lookup and separate post-decision reload, and leave direct URL/text
   outcomes unchanged.
5. Add the failing dialog role/name assertion, apply the outer `aria-label`, and
   rerun every evidence/no-fetch/original/close/Escape/focus regression.
6. Add deterministic Plan 1 diagnostic/PDF negative tests. Change diagnostic code
   only for a failing mapping/redaction root cause, then run one positive project-
   interpreter diagnostic pair.
7. Add every exact P12/P13 functional-matrix ID listed above; create the acceptance
   ledger with `NOT RUN` requirement statuses, immutable `BASE-PJD-01..03` rows,
   append-only execution attempts, first-failure retention, and the separate
   five-column non-blocking-warning table; then add the two-CV Plan 13 rerun
   contract to the CV Manager checklist.
8. Run focused/full backend and frontend gates, static/type/build checks, and the
   shared plan validator. Fix only root causes in the owners above.
9. Run the fixed-port Compose preflight: capture configured services, normal-project
   running/health state, and fixed-port owners; block on partial, unexpected, or
   unrelated ownership; and, only when the known normal stack is fully running and
   healthy, use the exact normal-project `stop frontend backend neo4j` command from
   the Compose contract above. Start only `jobagent-plan13-smoke`, then execute the
   two-CV/source-dialog matrix and this exact terminal browser sequence: English
   card/cancel; Vietnamese pending refresh plus same run/execution/card rehydrate and
   save; exact Vietnamese repeat/confirm with returned same Job and no evaluation;
   long MISA-like card/cancel with no interrupted run; sole URL; the exact explicit
   direct-text request above; then separate opt-out and ambiguous turns. Record
   only browser-owned deltas/state/network/console/sanitized logs and preserve every
   failure attempt; automated fake-spy counters remain in automated evidence.
10. In finally-style cleanup, tear down only the named smoke project with
    `down --volumes --remove-orphans`. Restore the normal three components only when
    they were recorded as running, verify overall/SQLite/filesystem/Neo4j health,
    update the ledger from fresh evidence, run final scope/secret/data/architecture
    checks, and rerun all gates after the last edit. Never run normal-project
    `down`, and do not restore or stage the unrelated deleted spec. Update `README.md`
    only if a documented command or status became stale; otherwise record
    `README unchanged` in the ledger.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Provider schema/runtime | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/integration/test_job_tools.py -q` | Actual provider payload is one compatible ordinary object with exactly `url`/`text`/`source`/bounded `preview`, no required combinators, and no normal forced choice; injected state is absent/provider-owned; the original ToolNode `BaseTool`, strict runtime validation, and interrupt remain exact. |
| Early live schema compatibility | Immediately after the provider-schema implementation task and before repair work, run the standalone side-effect-free inline `.venv` probe embedded in Implementation step 2. | The probe contains no real JD/provider payload, dispatches no ToolNode, and prints only `SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS`; provider rejection/malformed output prints only the FAIL marker, exits non-zero, and blocks work with no permissive fallback. `diagnose_shopaikey.py` is not the owner of this early gate. |
| Passive repair/topology | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_graph.py -q` | The binding-aware fake is RED until both the compatible ordinary provider definition and exact canonical forced-choice object exist; normal binding has no forced choice; valid first/repair calls dispatch once; repeated malformed repair refuses with zero tools; sanitized `caplog`, precedence, topology, and six-pass regressions pass. |
| Public confirmation/branches | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py -q` | Confirmation SSE, running execution, strict card, one pre-interrupt lookup plus exactly one fresh accepted-save re-entry lookup (two reads total and no explicit third reload), and exactly one current cancel re-entry lookup (also two reads total as implementation evidence) are distinguished. Save ingests only fresh content; after normal recognition/repair, cancel performs zero `ingest_raw_text`, JD-extraction/embedding-provider, evaluation, Neo4j, or SQLite side effects. Exact fake-spy counts, dedupe/replay, direct paths, and no automatic evaluation pass. |
| Existing backend CV regressions | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_active_cv_tool.py tests/integration/test_cv_manager_api.py tests/integration/test_cv_manager_deletion.py -q` | Active-CV evidence, archived reprocess/activation/delete, and shared-data preservation owners remain green before browser acceptance. |
| Diagnostic negatives | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_phase0_diagnostics.py tests/unit/test_embedding_adapter.py tests/unit/test_pdf_extraction.py -q` | Every exact failure-code/capability/exit/terminal-marker tuple above and both PDF aggregate failures pass with redaction, no live call, and no OCR. |
| Positive diagnostics | `& '.\.venv\Scripts\python.exe' infrastructure/scripts/verify_pdf_extraction.py`; then `& '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_shopaikey.py` | pypdf and the final intentional live provider rerun end PASS without secrets/headers; the earlier strict-schema probe remains separately recorded. |
| Dialog accessibility | `Set-Location frontend; npm test -- --run src/test/active-cv-source.test.tsx src/test/assistant-response.test.tsx src/test/chat-page.test.tsx; npm run typecheck` | `dialog` named **Nguồn từ CV** plus exact evidence/no-fetch/PDF/partial/close/Escape/focus behavior pass. |
| Existing frontend regressions | `Set-Location frontend; npm test -- --run src/test/job-save-confirmation.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts src/test/cv-manager.test.tsx src/test/cv-manager-api.test.ts src/test/empty-match-card.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/approval-card.test.tsx` | Existing confirmation/history, CV Manager, saved-JD, match, zero-result, and profile-approval flows remain green. |
| Backend full/static | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q` | All backend gates pass with fakes and no architecture/public/schema drift. |
| Frontend full/build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Full suite/static/build pass; non-blocking warnings are separately classified. |
| Plan/traceability | `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json`; then `rg -n "P12-|P13-|current_message|job_save_confirmation|Nguồn|4971481e|d1fab78d|5a12595d" docs/acceptance` | Plan set is contiguous; P12/P13 cases and ledger/evidence links are complete; all three baseline failures remain; first failures are preserved; warnings are separate. |
| Compose preflight/disposable services | In one PowerShell `try/finally`, capture `config --services`, per-service `ps -a` state, normal `infrastructure` component/overall health, and PID/process/project owners of ports `5173/8000/7474/7687`; block on partial/unexpected/unhealthy/unrelated ownership. Only when the known normal stack is fully running and healthy, run `docker compose --env-file .env -f infrastructure/docker-compose.yml -p infrastructure stop frontend backend neo4j`, verify the ports are free, then start only `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan13-smoke up --build -d --wait --wait-timeout 180` and query health. | Configured/prior services, health, and port owners are recorded; `finally` always attempts named teardown/restoration and retains recovery state on restoration failure; normal-project `down` and normal-volume deletion never run; exactly three smoke services are healthy and overall/SQLite/filesystem/Neo4j are available. |
| Browser Plan 13 matrix | Execute browser-owned ledger rows and only the browser slice of mixed P12/P13 rows through the in-app browser at desktop width in this order: English card/cancel; Vietnamese pending refresh plus same run/execution/card rehydrate/save; exact Vietnamese repeat/confirm with returned same Job and no evaluation; long MISA-like card/cancel with no interrupted run; sole URL; the exact explicit direct-text request; then separate opt-out and ambiguous turns. Automated-only rows link their exact commands instead. | Two-CV lifecycle, named dialog, the canonical terminal sequence, sentinels, dedupe/direct/URL/opt-out/ambiguous paths, history-then-single-resume network order, SQLite/evaluation/Neo4j deltas, durable states, console/sanitized logs, and actual run IDs are recorded; no browser row claims fake/provider counters and no approval remains pending. |
| Named teardown and normal-stack restoration | In finally-style cleanup run `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan13-smoke down --volumes --remove-orphans`; only when preflight recorded the normal stack as running, restore it with `docker compose --env-file .env -f infrastructure/docker-compose.yml -p infrastructure up -d --wait --wait-timeout 180` and query health. | Only named smoke volumes are removed; normal volumes are preserved; previously running normal components return with overall/SQLite/filesystem/Neo4j available, while a previously stopped normal stack remains stopped. |
| Scope hygiene | `git diff --check`; inspect `git status --short`, changed paths, migrations, manifests, routes, registry, graph nodes, source lengths, tracked data/secrets, and the unrelated deleted-spec path. | No task-contract/progress drift during execution, restoration/staging of the unrelated deletion, migration/dependency/endpoint/store/Agent/tool/evaluation/security/mobile/warning-cleanup/real-data/secret drift. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Plans 1-11 | Stable local runtime, diagnostics, one-Agent tool execution, CV/Job lifecycle, graph/matching, saved-JD and accepted desktop fixes | Historical ownership remains unchanged. |
| Plan_12 | Readable output, active-CV evidence/dialog, strict runtime current-message confirmation, interrupt/save/cancel/replay, and desktop baseline | This phase repairs provider reliability/accessibility/evidence without reimplementing the feature. |
| Current user authorization | 2026-07-19 approval of the Plan 13 repair/revalidation design, Plan 12 terminal replacement, and ShopAIKey compatibility correction | Authorizes this bugfix phase with Master impact none, the corrected provider/runtime split, and the explicit exclusions above. |
| Approved design/implementation plan | Test-first and ownership contracts named in Source of Truth | Preserve their aligned behavior and evidence gates; corrected `Plan_13.md` provider-schema and forced-choice requirements supersede conflicting supporting passages. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Fresh portfolio review | Plan 12 successor boundary plus `Plan_13.md` and unchanged Master Version 1.9 | Shared validator passes; scope, requirements, ownership, verification, and completion are independently reviewable across Plans 1-13. |
| Fresh orchestration restart | Corrected `docs/tasks/task_13.md` | Five batches and eight unchecked canonical tasks map P13-JD-01 through P13-REG-01 to test-first A1/A2/A3 evidence; the new run does not consume abandoned run state as acceptance evidence. |
| Future A1/A2/A3 execution | ShopAIKey-compatible provider schema, strict runtime validation, one bounded repair, a11y fix, diagnostic tests, ledger, and browser release matrix | Evidence proves the provider/runtime boundary repair, exact counters, accessible dialog, archived-CV paths, frozen-candidate gates, an A3 commit reference, and no scope expansion. |

### Next Consumer

`Plan_14.md` consumes the completed Plan 13 provider/runtime boundary,
current-message confirmation, strict `SaveJobInput` contract, and the existing
single-Agent/ToolNode topology. It owns the approved intent-aware correction for
large pasted JD messages; it must not reimplement provider schema compatibility,
dialog accessibility, diagnostic failure mappings, CV lifecycle, or release
ledger ownership.

### Historical Completion Contract

Plan 13 is complete only when the actual provider-visible `save_job` definition is
one ShopAIKey-compatible `type='object'` with exactly `url`, `text`, `source`, and
bounded `preview` properties, without requiring provider-side `oneOf`, `const`,
nested `anyOf`, branch-local `required`, or unknown-field enforcement. The required
`ponytail:` comment records that limitation and the upgrade path after verified
ShopAIKey combinator support. The compatible schema is model-bound only with no
normal forced choice, while the original runtime `BaseTool` plus `SaveJobInput`
remain authoritative in ToolNode for exactly one source, unknown fields, source
value, preview mode, and bounds. Immediately after
provider-schema implementation, the standalone side-effect-free inline `.venv`
probe from Implementation step 2 must print only
`SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS` or block on rejection/malformed output with
only the FAIL marker and no permissive fallback; it contains no real JD/provider
payload and dispatches no ToolNode. The later positive `diagnose_shopaikey.py`
command remains the final general compatibility rerun.
Three fresh recognizable passive JDs must each produce one strict confirmation
card. A valid first/repair call reaches the single ToolNode once; a still-invalid
repair returns the fixed truthful refusal with zero tool execution. Binding-aware
RED coverage and sanitized diagnostics prove the repair depends on both the
compatible provider definition and exact canonical forced-choice object without
logging content, values, objects, provider payloads/responses, prompts, or secrets.
Opt-out, named save, sole URL, explicit text, ambiguous prose, seven-tool topology,
and six-pass behavior remain unchanged.

Before **Lưu JD**, the one execution is `running` and automated fake spies/counters
prove zero Job persistence, JD extraction, embedding, evaluation, and Neo4j
mutation. The initial interrupt uses exactly one durable lookup. Accepted-save
re-entry performs exactly one fresh durable lookup, so save uses two reads total and
no explicit third reload. The current cancel re-entry performs exactly the same one
fresh read because LangGraph re-enters the tool; the test records two reads total,
but that observation is not a new cancellation product precondition. Save ingests
the freshly reloaded exact message once, deduplicates
truthfully, and does not evaluate. **Không lưu** completes with
`committed=false`/`cancelled` and, after the normal Agent recognition/repair calls,
performs zero `ingest_raw_text`, JD-extraction/embedding-provider, evaluation,
Neo4j, or SQLite side effects. Automated fakes own exact service-call counters;
browser evidence owns only durable state, SQLite/evaluation/Neo4j deltas, network,
console, and sanitized logs. Duplicate/terminal resume performs no explicit third
reload or repeated work.

The active-CV source modal must be discoverable as `dialog` named **Nguồn từ CV**
and retain exact evidence order, partial disclosure, zero hidden fetch, original-CV
attachment, close/Escape/focus behavior, history, and restart truth. Every required
Plan 1 negative diagnostic and PDF gate must have deterministic redacted coverage.
The disposable two-CV reprocess/activation/delete flow and every P12/P13 browser row
must have dated attempt-specific HEAD/project ledger evidence with actual run IDs,
counters, failures, and resolutions. The ledger preserves the three audited failed
run IDs and every
first failure, keeps warnings separate, refreshes and rehydrates a still-pending card
before acting, and uses this terminal browser order: English card/cancel; Vietnamese
pending refresh plus same run/execution/card rehydrate/save; exact Vietnamese repeat/
confirm with returned same Job and no evaluation; long MISA-like card/cancel with no
interrupted run; sole URL; then this exact direct-text request:

```text
Please call save_job exactly once with text="Job title: Synthetic API Engineer. Company: Plan13 Labs. Responsibilities: build local APIs and deterministic tests. Requirements: Python, FastAPI, SQL, and Docker. Location: Hanoi. This is synthetic test data." Do not use source=current_message and do not call match_jobs.
```

The opt-out and ambiguous-prose turns follow that direct-text check and both finish
terminally without a forced save.

Fixed-port preflight captures configured services, prior normal running/component-
health state, and port owners; it blocks on partial/unexpected/unrelated ownership.
When the normal stack is fully running and healthy, only
`docker compose --env-file .env -f infrastructure/docker-compose.yml -p infrastructure stop frontend backend neo4j`
may stop it—normal-project `down` and normal-volume deletion never run. Finally-
style cleanup removes only named smoke volumes, and normal components are restored
and health-verified only when they were previously running.

Focused/full backend/frontend/static/build/Compose/browser/plan-validator/scope gates
must pass for the same frozen product/test/config candidate. Later evidence-only
ledger/checklist edits receive fresh structure/link/diff checks; any product, test,
dependency, or configuration edit invalidates and reruns the affected gates. A3
reports the final committed SHA in its handoff and revalidates the committed
plan/diff; the ledger has no self-referential same-commit SHA requirement. Non-blocking
warnings remain separately recorded, and no endpoint, migration, dependency,
tool/Agent/node, automatic evaluation, security/mobile work, real data, secret, or
unrelated fix is introduced. The corrected `Plan_13.md` and fully unchecked
`task_13.md` are the authoritative restart inputs; product code and abandoned
`.agent` evidence are unchanged by this correction. The next execution action is a
fresh orchestration run, and its A1/A2/A3 gates own acceptance and commits.
