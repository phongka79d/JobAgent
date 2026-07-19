# JobAgent Plan 13 Execution Tasks

## Purpose

Translate `docs/plans/Plan_13.md` into the mandatory implementation and evidence
chain for reliable passive pasted-JD confirmation, the accessible active-CV source
dialog name, deterministic diagnostic coverage, and frozen-candidate release
revalidation. Preserve the accepted Plan 12 behavior, all Plan 11 repairs, and the
existing one-Agent, one-ToolNode, seven-tool architecture.

## Project Context Notes

- Root `README.md` was read completely before derivation. It defines JobAgent as a
  local single-user React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, and ShopAIKey
  application with one ignored root `.env`, exactly three fixed-port Compose
  services, fake-backed automated tests, and synthetic-only release evidence.
- The README reports Plan 12 Batch01 through Batch05 accepted on product HEAD
  `887d4f6`, with final orchestrator commit still pending. That baseline is context;
  future execution must verify the matching immutable A1/A2/A3 evidence and
  Orchestrator decisions rather than infer acceptance from README prose. The
  repository HEAD observed during this correction was `b938310`; this task contract
  does not claim that it is the same candidate as the README product baseline.
- The current user explicitly invoked `task-writing-agent` for `Plan_13.md`. This
  authorizes creation of this task contract and supersedes only the plan's
  planning-stage instruction to wait for another portfolio review. It does not
  authorize implementation, expand scope, or mark any task accepted.
- `docs/plans/Plan_13.md` is the primary authority. Its approved ShopAIKey
  compatibility correction supersedes conflicting provider `oneOf`/`const`/
  nested-`anyOf`, provider unknown-field, branch-local-required, and string
  forced-choice passages in the supporting design/implementation documents. Their
  otherwise aligned behavior, test, ownership, and conditional commit guidance
  remains supporting input and does not override the handoff contract below.
- The shared plan validator passed during task derivation on 2026-07-19 with
  contiguous `Plan_1.md` through `Plan_13.md`, `valid: true`, and no errors.
- Existing backend owners were confirmed at `backend/app/schemas/jobs.py`,
  `backend/app/tools/jobs.py`, `backend/app/adapters/shopaikey_chat.py`,
  `backend/app/agent/graph.py`, and the named unit/integration test files.
  `backend/tests/unit/test_phase0_diagnostics.py` does not yet exist.
- Existing frontend owners were confirmed at
  `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx` and its named
  tests. `frontend/AGENTS.md` applies: inspect the pinned Astryx 0.1.4 public
  component contract before editing UI, reuse public component props, and avoid
  unrelated layout or styling work.
- Existing acceptance owners were confirmed at
  `docs/acceptance/full_functional_test_matrix.md` and
  `docs/acceptance/cv_manager_checklist.md`.
  `docs/acceptance/plan13_acceptance_ledger.md` does not yet exist.
- This correction pass changes only `docs/plans/Plan_13.md` and
  `docs/tasks/task_13.md`. A fresh orchestration run will consume them; abandoned
  `.agent` evidence is not revised or reused as authority. Product code, supporting
  design/implementation documents, Plan 12, README, and unrelated paths remain
  untouched by this pass.
- Automated tests use fakes and synthetic fixtures. Only the explicitly named
  provider probes and disposable browser release task may use configured local
  services. Never record `.env` values, raw CV/JD bodies, prompts, provider
  transcripts, authorization headers, databases, uploads, or personal data.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_13.md`.
- Supporting:
  `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md`,
  `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md`,
  `docs/plans/Plan_1.md`, `docs/plans/Plan_12.md`, and
  `docs/plans/Master_plan.md` Version 1.9.
- Provider format reference:
  [ShopAIKey OpenAI Format - Function Calling](https://shopaikey.com/docs/openai-format).
  Its documented ordinary object shape supports the approved compatibility
  correction; it does not make unsupported combinators mandatory.
- Context only: `README.md`, `frontend/AGENTS.md`, `docs/tasks/task_12.md`,
  existing implementation/tests, acceptance documents, and
  `infrastructure/docker-compose.yml`.

### Source Section Index

- `Plan_13.md` > `## Objective`, `## Master Requirement Coverage`,
  `## Prerequisites`, `## Scope`, and `## Out of Scope` -> mandatory P13-JD,
  P13-A11Y, P13-DIAG, P13-CV, P13-EVID, and P13-REG outcomes, dependencies, and
  exclusions.
- `Plan_13.md` > `### Provider-visible source contract` -> compatible ordinary
  provider object, required `ponytail:` limitation/upgrade comment, model-only
  binding, unchanged runtime `BaseTool`, strict runtime validation, and early
  no-fallback provider probe.
- `Plan_13.md` > `### One bounded strict repair` -> repair-only tool choice,
  exact canonical forced-choice object, binding-aware regression, one invocation,
  fixed refusal, precedence, sanitized logging, and topology invariants.
- `Plan_13.md` > `### Confirmation, side effects, and durable truth` -> exact
  pre-interrupt/re-entry read boundaries, fake-spy ownership, zero pre-action and
  cancel domain side effects, fresh-content save, dedupe, replay, and direct-path
  behavior.
- `Plan_13.md` > `### Source dialog accessibility` -> exact outer Astryx dialog
  name and unchanged evidence, PDF, close, Escape, focus, and no-fetch behavior.
- `Plan_13.md` > `### Deterministic diagnostic coverage` -> exact diagnostic
  failure mappings, PDF negative aggregates, redaction, no OCR, and project-
  interpreter positive gates.
- `Plan_13.md` > `### Traceability and browser evidence` -> exact P12/P13 IDs,
  ledger schema, immutable baseline failures, append-only attempts, warning
  separation, candidate identity, two-CV flow, passive-JD fixtures/order, and
  evidence ownership.
- `Plan_13.md` > `### Compose preflight, isolation, and restoration` -> fixed-port
  inspection, exact normal-project stop boundary, named smoke startup/teardown,
  and prior-state restoration.
- `Plan_13.md` > `### Ownership and invariants`, `## Implementation`,
  `## Verification`, `## Handoff Contract`, and `## Completion Contract` -> file
  ownership, test-first sequence, exact commands, frozen-candidate evidence,
  handoffs, and binary completion conditions.
- `2026-07-19-plan13-repair-revalidation-design.md` > `## Selected design`,
  `## Error handling and recovery`, `## Acceptance gates`, and
  `## Ownership and file boundaries` -> approved root-cause design and narrow
  repair boundaries.
- `2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 1` through
  `## Task 8` and `## Completion conditions` -> detailed test-first examples and
  command sequencing subordinate to the primary Plan 13 contract; conflicting
  provider-schema and string forced-choice examples are superseded.

### Approved Architecture and Constraints

- This increment is a `bugfix` with Master impact `none`. Keep the existing public
  endpoints, SSE envelopes, schema/migrations, dependencies, provider/model,
  Compose topology, stores, and deployment rules unchanged.
- Keep one LangGraph Agent, one decision node, one ToolNode, exactly seven runtime
  tools, unchanged graph state and routing, and `TOOL_LOOP_LIMIT=6`.
- Keep `SaveJobInput` and the original runtime `save_job` `BaseTool` authoritative
  for exactly-one-source/unknown-field/source/preview validation, injected state,
  interrupt, execution, and replay. The provider-visible schema is one compatible
  ordinary object and must never become a second runtime tool or ingestion path.
- Normal binding has no forced choice. A clear passive JD receives at most one
  repair bound only to the compatible `save_job` definition with exact canonical
  choice `{"type":"function","function":{"name":"save_job"}}`. Invalid first/
  repaired calls never dispatch, and logging is limited to the approved shape-only
  fields.
- The provider-schema owner must include a `ponytail:` comment documenting the
  deliberate absence of unverified combinators and the upgrade path after
  ShopAIKey verifies support.
- Current-message confirmation remains pre-mutation. The initial interrupt and
  save/cancel re-entry each perform one durable lookup; save consumes the fresh
  re-entry content without a third reload, while cancellation performs no
  ingestion or mutation. No path evaluates automatically.
- The active-CV dialog change is the outer Astryx `Dialog` accessible name only;
  evidence projection, history, reducer, fetching, record order, retained-file
  behavior, and focus semantics remain unchanged.
- Diagnostic production code changes are conditional on a deterministic failing
  test proving a mapping/redaction root cause. Do not add OCR, fixtures,
  dependencies, permissive fallbacks, retries, or model switching.
- Acceptance evidence distinguishes automated fake/provider counters from
  browser-observable durable state and deltas. First failures and immutable
  baseline evidence are preserved; warning rows never dilute functional status.
- Browser acceptance uses only the named `jobagent-plan13-smoke` project and
  synthetic inputs. Normal volumes are never removed, and unrelated fixed-port
  owners are never stopped or changed.
- A1 and A2 do not update task checkboxes or commit. A3 audits accepted batch
  evidence; commit readiness and final commits remain Orchestrator-owned.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Compatible provider contract, strict runtime authority, one bounded repair, and exact durable confirmation behavior | (01A), (01B), (01C) | Accepted Plan 12 baseline and current Plan 13 authorization |
| Batch02 | Accessible active-CV source dialog name with preserved behavior | (02A) | Batch01 |
| Batch03 | Deterministic redacted ShopAIKey and PDF diagnostic failure coverage | (03A) | Batch02 |
| Batch04 | Complete P12/P13 traceability and append-only evidence scaffold | (04A) | Batch03 |
| Batch05 | Frozen-candidate automated and disposable browser release evidence | (05A), (05B) | Batch01 through Batch04 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md`
  report.
- A2 reviews one executed task, writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a2/<batch-id>/<task-id>/A2-a<attempt>.md`
  report, and the Orchestrator checks the canonical checkbox only after
  `ACCEPTED`.
- A3 runs only after every task in the selected batch has matching A1 evidence,
  A2 evidence, an Orchestrator `ACCEPTED` event, and a checked canonical task
  marker; it writes only
  `.agent/<plan-id>/<run-id>/report/a3/<batch-id>/A3-a<attempt>.md`.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.
- After final Batch05 acceptance and the Orchestrator-owned commit, the final A3
  handoff reports that committed SHA and fresh committed plan/diff revalidation;
  the ledger does not require a self-referential same-commit SHA.

## Mandatory Batch01 - Reliable Passive-JD Provider and Confirmation Boundary

### Goal

Repair the provider-to-Agent boundary and current-message lookup flow so every
valid obvious passive JD reaches the existing confirmation path without weakening
runtime validation, adding mutation, or changing direct URL/text behavior.

### Dependencies

- Accepted Plan 12 backend confirmation/Agent baseline and its repository owners.
- Approved Plan 13 primary/design sources and the current user authorization.
- Task order is (01A), then (01B), then (01C); later tasks consume earlier owners
  rather than recreating their contracts.

### Scope Boundary

- This batch owns only the compatible provider-visible object, strict runtime
  validation authority, model binding substitution, repair-only binding/decision
  behavior, sanitized rejection diagnostics, and the bounded current-message
  lookup-flow correction with directly required tests.
- It does not own endpoints, SSE shapes, persistence schemas, ingestion/extraction/
  embedding/evaluation implementations, registry topology, Agent state, prompt
  policy, frontend behavior, or release documentation.

### Tasks

- [x] (01A): Bind a ShopAIKey-compatible provider save_job object while preserving strict runtime authority
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch01 - Reliable Passive-JD Provider and Confirmation Boundary` > `(01A)`
  - Source of Truth: `docs/plans/Plan_13.md` > `## Source of Truth` > `Approved ShopAIKey compatibility correction (2026-07-19)`, `### Provider-visible source contract`, `## Implementation` steps 1-2, and `## Verification` rows `Provider schema/runtime` and `Early live schema compatibility`; [ShopAIKey OpenAI Format - Function Calling](https://shopaikey.com/docs/openai-format). The supporting Plan 13 design/implementation passages remain subordinate where they conflict with this corrected provider shape.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(01A)` -> task authority
    - source-provider-contract: repository `docs/plans/Plan_13.md` > `### Provider-visible source contract` -> required provider/runtime separation
    - source-provider-implementation: repository `docs/plans/Plan_13.md` > `## Implementation` step 2 -> exact early probe authority
    - existing-runtime-contract: repository `docs/tasks/task_12.md` > `(01A)` and `(01B)` -> accepted runtime schema/tool/interrupt ownership
    - existing-provider-pattern: repository `infrastructure/scripts/shopaikey_diag/tools_schema.py` > `check_tools_schema` -> working ShopAIKey ordinary-object binding pattern
    - owner-save-input: repository `backend/app/schemas/jobs.py` > `SaveJobInput` and preview bounds -> reuse/runtime authority
    - validation-provider: repository `docs/plans/Plan_13.md` > `## Verification` > `Provider schema/runtime` and `Early live schema compatibility` -> validation authority
  - Source Requirements:
    - Add one reusable parameters builder with one provider-visible `type='object'` and exactly `url`, `text`, `source`, and bounded `preview` properties. Do not require provider-side `oneOf`, `const`, nested `anyOf`, branch-local `required`, or unknown-field enforcement.
    - Wrap that parameters object in one OpenAI-format `save_job` definition and reuse one description constant with the existing runtime decorator.
    - Bind the compatible dictionary only to the model with no normal forced choice; keep the original registry `BaseTool`, injected state/tool-call ID, `SaveJobInput`, ToolNode execution, interrupt, and replay unchanged.
    - Keep `SaveJobInput` authoritative for exactly one source, `source='current_message'`, unknown fields, preview-only-current-message rules, unknown preview fields, and bounds. Inspect the actual provider-bound payload and independently test those runtime rejections; do not use OpenAI `strict=True` or a fallback schema.
    - Add a `ponytail:` comment at the provider-schema owner documenting that ShopAIKey has not verified the omitted combinators and that they may be restored only after documented or sanitized-probe verification.
    - Immediately after implementation and before (01B), run the exact side-effect-free inline `.venv` probe embedded in Plan 13 Implementation step 2. It must emit only its PASS marker, dispatch no ToolNode, contain no real JD/provider payload, and block on rejection or malformed output.
  - Dependencies: Accepted Plan 12 baseline; no earlier Plan 13 task.
  - User Action: Before the early live probe, make a usable ignored root `.env` and provider access available without sharing values. Missing or invalid provider setup blocks the probe and all later Batch01 work.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/schemas/jobs.py`, `backend/app/tools/jobs.py`, `backend/app/agent/graph.py`, `backend/tests/unit/test_shopaikey_chat.py`, `backend/tests/unit/test_job_save_confirmation.py`, `backend/tests/integration/test_job_tools.py`
  - Allowed Files: the six listed schema/tool/graph/test files only; edits in `backend/app/agent/graph.py` are limited to provider-definition substitution. Exclude repair binding/logging (owned by (01B)), current-message lookup refactor (owned by (01C)), registry/state/runner/prompt, services/repositories/API, settings, migrations, dependencies, frontend, acceptance docs, runtime data, and `.env`.
  - Agent Work:
    1. Inspect `SaveJobInput`, preview constants, the existing decorated `save_job`, `shopaikey_diag/tools_schema.py`, graph model binding, ToolNode construction, and every direct schema/runtime caller; reuse the accepted owners and working provider pattern.
    2. Add failing actual-provider-payload and strict runtime-validation tests, including ordinary property shape, combinator absence, no normal forced choice, original ToolNode `BaseTool` identity, and injected-field absence.
    3. Implement the minimum compatible provider parameters/function definition plus required `ponytail:` comment and substitute it only in model binding; do not attach it as the runtime tool schema.
    4. Run the focused fake-backed provider/runtime tests and resolve only root causes within this task's boundary.
    5. Run the exact early inline provider probe once, record only its terminal marker/exit evidence, and stop with the mapped blocker if it fails.
  - Output: One ShopAIKey-compatible provider-visible `save_job` object is model-bound while the original runtime tool and strict validator remain authoritative.
  - A1 Outcome: The model receives the compatible ordinary save-job property schema with no normal forced choice, ToolNode retains the original injected runtime tool, `SaveJobInput` rejects every invalid source/unknown/preview case, and the early synthetic provider probe passes without fallback or side effects.
  - A2 Review Focus: Exact ordinary properties/bounds and combinator absence, actual bound payload, `ponytail:` limitation/upgrade path, description reuse, provider-only placement, no normal forced choice, all runtime callers, original `BaseTool` identity, injected-field absence, strict runtime exactly-one/mixed/unknown/source/preview rejection, probe freshness/sanitization, no fallback, no out-of-scope graph/tool changes, and bugfix hard gates.
  - A3 Batch Evidence: Provider-contract and owner rows for P13-JD-01 plus the provider/runtime portions of P13-REG-01.
  - Acceptance:
    - The actual model-bound definition is one ordinary object with exactly `url`, `text`, `source`, and bounded `preview` properties, omits injected fields and required provider combinators, and the normal binding has no forced choice.
    - The required `ponytail:` comment names the provider limitation and the verified-upgrade path.
    - The original runtime `BaseTool` is the identical ToolNode owner and `SaveJobInput` rejects zero/multiple sources, invalid source, unknown fields, direct-preview, unknown preview fields, and over-limit values.
    - Direct URL/text and current-message runtime paths retain their accepted public behavior and no second tool/ingestion path exists.
    - The exact early inline probe exits zero with only its PASS marker; any rejection/malformed output blocks with no fallback, retry, model switch, or argument stripping.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/integration/test_job_tools.py -q` -> PASS evidence: exit `0` and compatible bound-payload/no-normal-choice plus strict runtime/ToolNode assertions; freshness: final attempt only
    - Required: execute the exact standalone PowerShell `.venv` probe in `docs/plans/Plan_13.md` > `## Implementation` step 2 from the repository root -> PASS evidence: exit `0` and only `SAVE_JOB_PROVIDER_SCHEMA_PROBE=PASS`; freshness: immediately after final (01A) implementation and before (01B)
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: after the last task edit
  - Blocked Condition: Missing/unreadable accepted schema/tool refs or ShopAIKey Function Calling reference is `BLOCKED_MISSING_REF`; disagreement between the corrected compatible provider object and strict runtime authority is `BLOCKED_SOURCE_CONFLICT`; a root fix requiring repair, service/repository/API/registry/state/config/dependency or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Python tooling is `BLOCKED_ENVIRONMENT`; missing provider credential/access for the required early probe is `BLOCKED_USER_ACTION`; provider rejection or malformed probe output is `BLOCKED_ENVIRONMENT` and must not enable a fallback, retry/model switch, argument stripping, or unapproved schema change.
  - Files: `backend/app/schemas/jobs.py`, `backend/app/tools/jobs.py`, `backend/app/agent/graph.py`, `backend/tests/unit/test_shopaikey_chat.py`, `backend/tests/unit/test_job_save_confirmation.py`, `backend/tests/integration/test_job_tools.py`

- [x] (01B): Force one runtime-validated source-only passive repair with sanitized refusal evidence
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch01 - Reliable Passive-JD Provider and Confirmation Boundary` > `(01B)`
  - Source of Truth: `docs/plans/Plan_13.md` > `### One bounded strict repair`, `## Implementation` step 3, and `## Verification` row `Passive repair/topology`; `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md` > `### 2. Bounded passive-JD repair and dispatch gate`; `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 2: Make the one passive repair use the strict source-only tool`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(01B)` -> task authority
    - source-repair: repository `docs/plans/Plan_13.md` > `### One bounded strict repair` -> repair, precedence, logging, and topology authority
    - accepted-provider-owner: repository `docs/tasks/task_13.md` > `(01A)` -> compatible provider artifact and strict runtime-validator dependency
    - existing-decision-owner: repository `backend/app/agent/graph.py` > `_is_sole_current_message_save_job_call` and passive-JD decision branch -> reuse/root-cause owner
    - validation-repair: repository `docs/plans/Plan_13.md` > `## Verification` > `Passive repair/topology` -> validation authority
  - Source Requirements:
    - Extend the existing binding helper with an optional keyword-only tool choice that is omitted for normal binding and set to exactly `{"type":"function","function":{"name":"save_job"}}` only for the repair binding.
    - Build normal seven-capability and repair-only runnables from the same base model and accepted compatible provider definition; runtime validation remains the dispatch gate.
    - Preserve opt-out, exact-name, sole-URL, and obvious-JD precedence; validate both first and repaired responses before dispatch and make exactly one repair invocation.
    - A still-invalid repair returns the fixed truthful refusal with zero ToolNode passes; never synthesize, strip, or normalize mixed arguments.
    - Add a binding-aware RED fake that succeeds only for the expected compatible ordinary provider schema plus the exact canonical forced-choice object. Rejection logs use prefix `passive_jd_call_rejected`, reason allowlist `invalid_first_call|invalid_repair_call`, and exactly four observable fields: reason, integer `call_count`, `tool_names` list, and `argument_keys` list.
    - Keep Agent state, node/edge topology, tool iteration semantics, seven tools, and the six-pass guard unchanged.
  - Dependencies: Task (01A) accepted, including the compatible provider object, strict runtime-validation evidence, required `ponytail:` comment, and fresh PASS evidence from the early provider probe.
  - User Action: None; all repair/topology validation is fake-backed and must not call the provider.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/adapters/shopaikey_chat.py`, `backend/app/agent/graph.py`, `backend/tests/fakes/fake_chat_model.py`, `backend/tests/unit/test_shopaikey_chat.py`, `backend/tests/unit/test_agent_graph.py`
  - Allowed Files: the five listed adapter/graph/fake/unit-test files only; consume (01A)'s provider schema/runtime-validator/tool artifacts read-only. Exclude Job tool runtime flow/integration tests (owned by (01C)), prompt/state/runner/registry, services/repositories/API, settings, migrations, dependencies, frontend, acceptance docs, and runtime data.
  - Agent Work:
    1. Inspect every binding-helper and graph-decision caller plus accepted precedence/topology tests; reuse the existing sole-current-message predicate and fixed refusal.
    2. Add failing adapter and binding-aware graph tests for valid first/repair, repeated mixed calls, precedence, invocation counts, topology, six passes, and sentinel-safe `caplog` output.
    3. Implement the optional binding choice, exact canonical forced-choice object, one repair-only runnable, one invocation, and the fixed-shape rejection helper without moving or duplicating decision logic.
    4. Run the focused fake-backed gate and prove normal binding receives no forced tool-choice argument.
  - Output: The existing decision node makes at most one runtime-validated `save_job`-only repair and emits only safe shape diagnostics before truthful refusal.
  - A1 Outcome: An obvious passive JD dispatches one validated source-only save call after at most one binding-aware repair, while repeated malformed calls refuse with zero tools and unchanged precedence/topology.
  - A2 Review Focus: All binding callers, compatible provider-artifact reuse, exact normal omission and repair-only canonical choice, runtime pre-dispatch validation, exact invocation counts, precedence, fixed refusal, shape-only logging and sentinel absence, unchanged state/nodes/routes/tool count/loop limit, focused evidence freshness, and bugfix hard gates.
  - A3 Batch Evidence: Repair/refusal rows for P13-JD-02 and Agent/topology portions of P13-REG-01.
  - Acceptance:
    - Normal binding exposes all seven capabilities and omits `tool_choice`; repair binding exposes only the compatible `save_job` definition with exact `{"type":"function","function":{"name":"save_job"}}`.
    - Valid first or repaired source-only calls reach ToolNode once; a repeated invalid repair yields the fixed refusal and zero ToolNode passes.
    - Opt-out, exact-name save, sole URL, greeting, direct paths, and six-pass behavior remain unchanged.
    - Every rejection log starts `passive_jd_call_rejected`, uses only reason `invalid_first_call` or `invalid_repair_call`, contains exactly reason/integer `call_count`/`tool_names`/`argument_keys`, and contains no JD/preview/argument values, call objects, prompts, provider payloads/responses, secrets, or headers.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py -q` -> PASS evidence: exit `0`, binding-aware repair/refusal, sanitized `caplog`, precedence, topology, and six-pass assertions; freshness: final attempt only
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: after the last task edit
  - Blocked Condition: Missing accepted (01A) compatible provider/runtime-validator artifact, `ponytail:` comment, or probe evidence is `BLOCKED_MISSING_REF`; conflicting corrected choice/repair/precedence authority is `BLOCKED_SOURCE_CONFLICT`; a root fix requiring tool runtime/integration, prompt/state/runner/registry/service/API/provider settings or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/adapters/shopaikey_chat.py`, `backend/app/agent/graph.py`, `backend/tests/fakes/fake_chat_model.py`, `backend/tests/unit/test_shopaikey_chat.py`, `backend/tests/unit/test_agent_graph.py`

- [x] (01C): Correct current-message read boundaries and prove every confirmation side effect
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch01 - Reliable Passive-JD Provider and Confirmation Boundary` > `(01C)`
  - Source of Truth: `docs/plans/Plan_13.md` > `### Confirmation, side effects, and durable truth`, `## Implementation` step 4, and `## Verification` row `Public confirmation/branches`; `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md` > `### 3. Confirmation and side-effect proof`; `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 3: Prove confirmation, branch call counts, and durable replay`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(01C)` -> task authority
    - source-confirmation: repository `docs/plans/Plan_13.md` > `### Confirmation, side effects, and durable truth` -> durable lookup and side-effect authority
    - accepted-repair-owner: repository `docs/tasks/task_13.md` > `(01B)` -> binding-aware public-path dependency
    - existing-tool-owner: repository `backend/app/tools/jobs.py` > current-message `save_job` branch -> root-cause owner
    - validation-confirmation: repository `docs/plans/Plan_13.md` > `## Verification` > `Public confirmation/branches` -> validation authority
  - Source Requirements:
    - Reuse the first resolved durable message for current-message opt-out validation and pending-card construction; remove the unconditional duplicate pre-branch lookup.
    - On LangGraph re-entry, use exactly one fresh lookup as the content passed directly to ingestion; remove the separate post-decision reload so save has two reads total and never three.
    - Record the current cancel re-entry's second read as implementation evidence while preserving cancellation's product contract of zero `ingest_raw_text`, JD-extraction/embedding-provider, evaluation, Neo4j, Job-row, or evaluation-row side effects after normal Agent recognition/repair; durable terminal tool-result persistence remains required.
    - Add binding-aware public SSE/tool integration coverage for the strict pending card, one running execution, exact lookup counts, fresh-content save, cancel, dedupe, terminal replay, and direct URL/text compatibility.
    - Automated fakes/spies exclusively own exact ingestion, JD extraction, embedding, evaluation, Neo4j sync, Job-row, and evaluation-row counts; browser evidence must not claim these counters.
    - Preserve `created|returned|retried`, strict projection redaction, same durable identity, and zero automatic evaluation.
  - Dependencies: Tasks (01A) and (01B) accepted with the compatible provider object, strict runtime-validation authority, canonical repair choice, and repair artifacts.
  - User Action: None; integration tests use fakes and temporary SQLite/files only.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/tools/jobs.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_chat_api.py`
  - Allowed Files: the three listed Job-tool/integration-test files only; consume (01A)/(01B) schema, graph, and fake owners read-only. Exclude confirmation service/schema changes, generic execution/runner/checkpoint/repository/API/SSE owners, ingestion/extraction/embedding/evaluation/graph implementations, registry, settings, migrations, dependencies, frontend, acceptance docs, and runtime data.
  - Agent Work:
    1. Inspect every current-message, direct URL/text, opt-out, interrupt/re-entry, dedupe, and terminal replay caller before changing shared Job-tool logic.
    2. Add failing public-path and tool-integration assertions for exact lookup boundaries, running execution/card projection, fake-spy counters, database rows, save/cancel/dedupe/replay, and direct-path regressions.
    3. Refactor only lookup placement so the initial branch read feeds opt-out/card and the single re-entry read feeds ingestion directly; do not change result shapes or service owners.
    4. Run the focused integration gate and collect final-attempt counter, durable-state, and redaction evidence.
  - Output: Current-message confirmation uses one initial durable read and one re-entry read with exact save/cancel side effects and no third reload.
  - A1 Outcome: Public passive-JD confirmation reaches one running execution, save ingests the one freshly reloaded exact message once, cancel persists its terminal result without Job ingestion/evaluation/graph domain side effects, and dedupe/replay/direct paths remain truthful with zero automatic evaluation.
  - A2 Review Focus: Every Job-tool caller, initial/re-entry read placement, opt-out/card reuse, no third reload, interrupt timing, same execution/source identity, strict projection, exact fake/database counters, cancel zero domain side effects plus required durable terminal result, save/dedupe/replay outcomes, direct-path compatibility, no service/API/schema drift, evidence freshness, and bugfix hard gates.
  - A3 Batch Evidence: Confirmation/side-effect rows for P13-JD-03, automated-counter portions of P13-EVID-01, and direct/replay portions of P13-REG-01.
  - Acceptance:
    - Before action there is one running execution, one pre-interrupt lookup, a strict bounded card, zero Job/evaluation rows, and zero ingestion/extraction/embedding/evaluation/Neo4j calls.
    - Accepted save performs one fresh re-entry lookup, ingests that exact content once, creates or truthfully deduplicates one Job identity, syncs as expected, and never evaluates.
    - Cancel re-entry records two reads total and, after normal Agent recognition/repair, performs zero `ingest_raw_text`, JD-extraction/embedding-provider, evaluation, Neo4j, Job-row, or evaluation-row side effects while persisting the accepted terminal cancelled ToolResult.
    - Terminal replay performs no extra lookup or side effect; direct URL/text outcomes and public SSE/history contracts remain unchanged.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py -q` -> PASS evidence: exit `0`, strict confirmation/SSE, exact reads/counters/rows, save/cancel/dedupe/replay, direct paths, and zero-evaluation assertions; freshness: final attempt only
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: after the last task edit
  - Blocked Condition: Missing accepted (01A)/(01B) artifacts is `BLOCKED_MISSING_REF`; conflicting interrupt/source/replay authority is `BLOCKED_SOURCE_CONFLICT`; a root fix requiring service/schema/repository/API/runner/ingestion/evaluation/graph or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/tools/jobs.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_chat_api.py`

## Mandatory Batch02 - Accessible Active-CV Source Dialog

### Goal

Close the active-CV dialog naming defect with the smallest supported Astryx change
while preserving every accepted evidence, PDF, keyboard, focus, and no-fetch path.

### Dependencies

- Batch01 accepted with compatible provider, strict runtime-validation, canonical repair-choice, and confirmation evidence.
- Accepted Plan 12 dialog/evidence behavior remains an immutable input.

### Scope Boundary

- This batch owns one supported Astryx `aria-label` and its directly required
  role/focus regressions.
- It does not own evidence projection/history/reducer behavior, UI redesign,
  provider/product behavior, diagnostics, dependencies, or release evidence.

### Tasks

- [ ] (02A): Name the existing active-CV source dialog without behavior drift
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch02 - Accessible Active-CV Source Dialog` > `(02A)`
  - Source of Truth: `docs/plans/Plan_13.md` > `### Source dialog accessibility`, `## Implementation` step 5, and `## Verification` row `Dialog accessibility`; `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md` > `### 4. Dialog accessible name`; `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 4: Name the active-CV source dialog accessibly`; `frontend/AGENTS.md` > Astryx workflow and rules.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(02A)` -> task authority
    - source-dialog: repository `docs/plans/Plan_13.md` > `### Source dialog accessibility` -> exact accessible-name and preserved-behavior authority
    - existing-dialog-owner: repository `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx` > `ACTIVE_CV_SOURCE_DIALOG_TITLE` and outer `Dialog` -> reuse owner
    - frontend-astryx: repository `frontend/AGENTS.md` > Astryx workflow and rules -> component-use authority
    - validation-dialog: repository `docs/plans/Plan_13.md` > `## Verification` > `Dialog accessibility` -> validation authority
  - Source Requirements:
    - Add `aria-label={ACTIVE_CV_SOURCE_DIALOG_TITLE}` to the existing outer Astryx `Dialog`; do not replace `DialogHeader`, hand-build a modal, change a package, or add styling.
    - Add a failing exact `getByRole('dialog', {name: 'Nguồn từ CV'})` assertion and verify the label uses the existing title constant.
    - Add the source-required title/trigger focus assertions that are currently absent, while retaining exact page/record order, repeated records, partial notice, zero evidence/chunk fetch, retained PDF, close button, Escape, and scroll containment.
    - Keep evidence parser, history projector, assistant row, retained-file API, reducer, and backend unchanged.
  - Dependencies: Batch01 accepted; no earlier Batch02 implementation artifact.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx`, `frontend/src/test/active-cv-source.test.tsx`, `frontend/src/test/assistant-response.test.tsx`
  - Allowed Files: the three listed dialog/test files only. `frontend/src/test/chat-page.test.tsx` is validation-only. Exclude evidence parser/history/projector/reducer/types, row/page/network logic, observability APIs, package manifests, CSS, Astryx internals, mobile/responsive owners, backend, and acceptance docs.
  - Agent Work:
    1. Inspect the existing dialog/tests and the installed Astryx `Dialog` public contract using the `frontend/AGENTS.md` discovery workflow; reuse the title constant and supported `aria-*` prop.
    2. Add failing role/name plus missing title/trigger focus assertions without weakening the existing evidence/no-fetch/PDF/interaction regressions.
    3. Add only the outer dialog label and run the focused frontend gate plus validation-only chat-page regression.
  - Output: The existing exact-evidence source modal is exposed as `dialog` named **Nguồn từ CV** with unchanged composition and behavior.
  - A1 Outcome: Users and assistive technology can find the current active-CV source dialog by its exact accessible name while record, network, PDF, keyboard, scrolling, and focus behavior remains intact.
  - A2 Review Focus: Astryx public API evidence, label/title constant reuse, exact role/name, newly explicit focus assertions, record/order/partial/no-fetch/PDF/close/Escape regressions, absence of custom modal/layout/package/CSS changes, all UI callers, evidence freshness, and bugfix hard gates.
  - A3 Batch Evidence: Accessible-name and preserved-dialog behavior rows for P13-A11Y-01.
  - Acceptance:
    - Testing Library finds one `dialog` named exactly **Nguồn từ CV** and the outer element carries the matching supported label.
    - Exact evidence order/content, repeated records, partial disclosure, retained attachment action, and zero hidden fetch remain unchanged.
    - Close, Escape, scroll containment, title focus, and trigger-focus return are explicitly tested and pass.
    - No evidence/history/reducer/API/package/CSS/backend/mobile owner changes.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/active-cv-source.test.tsx src/test/assistant-response.test.tsx src/test/chat-page.test.tsx; npm run typecheck` -> PASS evidence: all commands exit `0` with exact role/name, focus, evidence/no-fetch/PDF/interaction regressions; freshness: final attempt only
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: after the last task edit
  - Blocked Condition: Missing/unreadable accepted dialog/component refs is `BLOCKED_MISSING_REF`; conflict between Astryx public props and the approved label contract is `BLOCKED_SOURCE_CONFLICT`; a root fix requiring parser/history/reducer/API/package/CSS/backend/mobile or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Node/npm/Astryx tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx`, `frontend/src/test/active-cv-source.test.tsx`, `frontend/src/test/assistant-response.test.tsx`

## Mandatory Batch03 - Deterministic Diagnostic Failure Coverage

### Goal

Close the Plan 1 diagnostic evidence gaps with deterministic fake-backed failure
tests and only source-proven mapping/redaction/aggregate repairs.

### Dependencies

- Batch01 and Batch02 accepted in the Plan 13 implementation sequence.
- Accepted Plan 1 diagnostic/PDF contracts and existing diagnostic owners remain
  immutable inputs unless a deterministic RED case proves a root cause.

### Scope Boundary

- This batch owns one new diagnostic test owner and conditional repairs to the
  existing diagnostic mappings/aggregation named by Plan 13.
- It does not own provider/product behavior, new fixtures/parsers/OCR,
  dependencies, frontend changes, or release ledger/browser execution.

### Tasks

- [ ] (03A): Add deterministic redacted ShopAIKey and PDF diagnostic failure coverage
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch03 - Deterministic Diagnostic Failure Coverage` > `(03A)`
  - Source of Truth: `docs/plans/Plan_13.md` > `### Deterministic diagnostic coverage`, `## Implementation` step 6, and `## Verification` rows `Diagnostic negatives` and `Positive diagnostics`; `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md` > `### 6. Deterministic diagnostic and archived-CV evidence`; `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 5: Add deterministic Plan 1 negative diagnostic tests`; `docs/plans/Plan_1.md` > `### 7.2 ShopAIKey diagnostic contract`, `### 7.3 PDF feasibility contract`, and `### Failure handling`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(03A)` -> task authority
    - source-diagnostics: repository `docs/plans/Plan_13.md` > `### Deterministic diagnostic coverage` -> exact negative/positive diagnostic authority
    - existing-provider-diag: repository `infrastructure/scripts/shopaikey_diag/` -> current failure-code/redaction owners
    - existing-pdf-diag: repository `infrastructure/scripts/verify_pdf_extraction.py` -> current aggregate/terminal-marker owner
    - validation-diagnostics: repository `docs/plans/Plan_13.md` > `## Verification` > `Diagnostic negatives` and `Positive diagnostics` -> validation authority
  - Source Requirements:
    - Create one focused fake-backed test owner for timeout, HTTP 429, malformed/non-stream JSON, missing configured models, unlocked missing chat model at the CLI gate, wrong vector dimension, and duplicate/out-of-order indexes.
    - Assert each exact failure code, capability, non-zero result/exit, terminal FAIL marker, and absence of secrets, authorization headers, and bearer values.
    - Force the PDF aggregate to three of five digital passes and separately to an accepted image-only row; both fail with the existing marker and no OCR/parser fallback or new fixture.
    - Change existing diagnostic production files only when a deterministic RED case proves a mapping, redaction, or pure aggregate root cause; otherwise leave them untouched.
    - Immediately before the positive pypdf and final general ShopAIKey diagnostics, record base HEAD plus the SHA-256 product/test/dependency/config manifest using the exact deterministic procedure defined in (05A); the earlier (01A) schema probe remains separate evidence.
  - Dependencies: Batch01 and task (02A) accepted; accepted Plan 1 diagnostic owners available.
  - User Action: Before the final positive ShopAIKey diagnostic, provide a usable ignored root `.env` and provider/network access without sharing values. Automated negative tests remain fake-backed and offline.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/unit/test_phase0_diagnostics.py`; conditional root-cause repair in `infrastructure/scripts/shopaikey_diag/common.py`, `infrastructure/scripts/shopaikey_diag/runner.py`, `infrastructure/scripts/shopaikey_diag/embeddings.py`, `infrastructure/scripts/shopaikey_diag/chat_checks.py`, `infrastructure/scripts/verify_pdf_extraction.py`
  - Allowed Files: create `backend/tests/unit/test_phase0_diagnostics.py`; edit only the five listed diagnostic production files when a failing test proves the named defect. Exclude existing `backend/tests/unit/test_embedding_adapter.py` and `backend/tests/unit/test_pdf_extraction.py` from edits; exclude fixtures, dependencies, settings, provider adapters, product services/API, frontend, acceptance docs, OCR/parser work, and runtime data.
  - Agent Work:
    1. Inspect and reuse existing failure classifiers, `DiagnosticError`, terminal emitters/redaction, embedding validation, and PDF aggregate owners before adding any helper.
    2. Add deterministic fake transport/payload/aggregate tests for every exact Plan 13 case, including CLI orchestration, redaction sentinels, and no-OCR dependency inspection.
    3. Run the negative gate; modify production diagnostics only for a reproduced root cause inside the conditional boundary and rerun to green.
    4. Run the exact candidate-identity procedure defined in (05A), then the project-interpreter pypdf diagnostic and the one final general provider diagnostic; capture only base HEAD/digest/path names and terminal/capability evidence, never file content or credentials.
  - Output: Every required Plan 1 diagnostic/PDF failure path has deterministic redacted coverage and the existing positive diagnostics remain compatible.
  - A1 Outcome: Fake-backed tests deterministically prove all required failure mappings and PDF rejection gates, while project-interpreter positive diagnostics pass without secrets, OCR, new fixtures, or permissive behavior.
  - A2 Review Focus: Exact code/capability/exit/marker tuples, fake transport ownership, runner-level config case, PDF aggregate rows, redaction sentinels, no network in automated tests, production-file conditionality/root cause, no OCR/fixture/dependency drift, positive output sanitization/freshness, and bugfix hard gates.
  - A3 Batch Evidence: Deterministic/positive diagnostic rows for P13-DIAG-01 and diagnostic-sanitization portions of P13-EVID-01.
  - Acceptance:
    - All seven named ShopAIKey failure cases produce the exact stable code/capability/non-zero/FAIL-marker evidence with secrets and headers absent.
    - Both PDF negative aggregates fail deterministically with the existing marker; no OCR dependency, parser fallback, or fixture is added.
    - Production diagnostic files change only when a RED test proves the corresponding root cause, and all existing diagnostic regressions remain green.
    - The project `.venv` pypdf and final general ShopAIKey diagnostics end PASS with sanitized output on the recorded base HEAD/content manifest; the (01A) schema probe remains separately recorded.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_phase0_diagnostics.py tests/unit/test_embedding_adapter.py tests/unit/test_pdf_extraction.py -q` -> PASS evidence: exit `0` and every exact negative/redaction/no-OCR assertion; freshness: final attempt only
    - Required: run the exact candidate-identity procedure defined in (05A) immediately before the positive diagnostics -> PASS evidence: base HEAD, SHA-256 digest, and bounded path list recorded in the A1 report without file contents; freshness: same working tree as both positive commands
    - Required: `& '.\.venv\Scripts\python.exe' infrastructure/scripts/verify_pdf_extraction.py` -> PASS evidence: exit `0` and terminal `PYPDF_COMPATIBILITY=PASS`; freshness: after final diagnostic/test edit
    - Required: `& '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_shopaikey.py` -> PASS evidence: exit `0`, terminal `SHOPAIKEY_COMPATIBILITY=PASS`, and no secret/header output; freshness: after final diagnostic/test edit
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: after the last task edit
  - Blocked Condition: Missing/unreadable Plan 1 or diagnostic refs is `BLOCKED_MISSING_REF`; conflicting code/capability/marker authority is `BLOCKED_SOURCE_CONFLICT`; a root fix requiring product adapter/settings/dependency/fixture/OCR or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/pypdf/test tooling is `BLOCKED_ENVIRONMENT`; missing provider credential/network for the required positive diagnostic is `BLOCKED_USER_ACTION`; unavailable permission to run that diagnostic is `BLOCKED_PERMISSION`.
  - Files: `backend/tests/unit/test_phase0_diagnostics.py`; conditional `infrastructure/scripts/shopaikey_diag/common.py`, `infrastructure/scripts/shopaikey_diag/runner.py`, `infrastructure/scripts/shopaikey_diag/embeddings.py`, `infrastructure/scripts/shopaikey_diag/chat_checks.py`, `infrastructure/scripts/verify_pdf_extraction.py`

## Mandatory Batch04 - Plan 13 Traceability and Append-Only Evidence Contract

### Goal

Create the source-defined P12/P13 requirement map, dated ledger scaffold, immutable
failure history, append-only attempt structure, warning separation, and two-CV
browser rerun contract before final release execution.

### Dependencies

- Batch01 through Batch03 tasks accepted with matching A1/A2/A3 evidence.
- Existing functional matrix and historical CV Manager checklist remain preserved
  inputs, not progress sources to rewrite.

### Scope Boundary

- This batch owns only the new Plan 13 acceptance ledger and additive P12/P13
  sections in the two existing acceptance documents.
- It does not execute the release matrix, mark the functional matrix PASS, rewrite
  historical evidence, edit plan/task/product/test/config files, or publish a
  candidate result before fresh execution.

### Tasks

- [ ] (04A): Establish complete P12/P13 matrix, ledger, and two-CV rerun authority
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch04 - Plan 13 Traceability and Append-Only Evidence Contract` > `(04A)`
  - Source of Truth: `docs/plans/Plan_13.md` > `### Traceability and browser evidence` and `## Implementation` step 7; `docs/superpowers/specs/2026-07-19-plan13-repair-revalidation-design.md` > `### 5. Evidence and release ledger` and `### 6. Deterministic diagnostic and archived-CV evidence`; `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 6: Create the Plan 13 traceability and evidence contract`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(04A)` -> task authority
    - source-traceability: repository `docs/plans/Plan_13.md` > `### Traceability and browser evidence` -> exact ID/table/fixture/evidence authority
    - existing-functional-matrix: repository `docs/acceptance/full_functional_test_matrix.md` -> additive method/expectation owner
    - existing-cv-ledger: repository `docs/acceptance/cv_manager_checklist.md` -> historical evidence owner and additive rerun target
    - validation-traceability: repository `docs/plans/Plan_13.md` > `## Verification` > `Plan/traceability` -> validation authority
  - Source Requirements:
    - Add exactly P12-RSP-01/02, P12-CV-01 through 05, P12-JD-01 through 05, P12-REG-01, and P13-JD-01/02/03, P13-A11Y-01, P13-DIAG-01, P13-CV-01, P13-EVID-01, P13-REG-01 to the functional matrix with method, expected behavior, and ledger link but no execution status.
    - Create the ledger requirement table with ID, requirement/source, procedure/command including `Evidence owner: automated|browser|mixed`, status, UTC date, candidate identity/named project, failure/log evidence, and resolution/notes; seed every requirement status as `NOT RUN`.
    - Reproduce the three exact immutable `BASE-PJD-01..03` historical rows from the primary source without changing their dates, product/project identities, run IDs, observed failures, or dispositions.
    - Add a separate append-only execution-attempt table keyed by requirement plus attempt suffix; reruns append and requirement summaries link every earlier attempt.
    - Add the separate five-column non-blocking-warning table for only jsdom `window.scrollTo`, duplicate synthetic React key, Vite bundle-size, `aiosqlite` datetime deprecation, and bare-host Python/pypdf environment observations; it never replaces or excuses functional status.
    - Append, rather than rewrite, a Plan 13 CV Manager section with the exact synthetic A/B upload/approval, B archives A, archived-A reprocess/activation, A evidence/graph proof, archived-B deletion, and shared Job/Skill preservation sequence.
    - Encode candidate identity as base HEAD plus the source-defined SHA-256 product/test/dependency/config content-manifest fingerprint; the ledger does not require a self-referential same-commit SHA.
  - Dependencies: All Batch01 through Batch03 tasks accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `docs/acceptance/full_functional_test_matrix.md`, `docs/acceptance/plan13_acceptance_ledger.md`, `docs/acceptance/cv_manager_checklist.md`
  - Allowed Files: the three listed acceptance documents only. Create the ledger; append source-supported sections to the existing documents. Exclude historical-row rewrites, README, plans/tasks, product/tests/config, `.agent` workflow state, runtime data, screenshots, provider output, and the unrelated deleted specification.
  - Agent Work:
    1. Inspect existing matrix/checklist structure and preserve every historical row, status owner, and link convention.
    2. Add the exact source-listed P12/P13 method/expectation rows and create the ledger with all requirement rows at `NOT RUN`.
    3. Copy the three immutable baseline-failure rows exactly from Plan 13, then add empty append-only attempt and separate warning tables with the source-defined columns/rules.
    4. Append the exact Plan 13 two-CV rerun contract to the CV Manager checklist and link it to P13-CV-01.
    5. Run exact ID/link/structure/diff checks and prove no execution claim, raw content, secret, or historical rewrite was introduced.
  - Output: One authoritative additive documentation scaffold maps every P12/P13 requirement to its evidence owner and preserves immutable/append-only history.
  - A1 Outcome: The functional matrix, Plan 13 ledger, and CV Manager supplement provide complete source-linked `NOT RUN` requirements, immutable baseline failures, append-only attempts, warning separation, and the exact two-CV rerun contract.
  - A2 Review Focus: Exact ID completeness/uniqueness, matrix-without-status rule, every ledger column/evidence owner, initial statuses, exact immutable baseline rows, append-only semantics, warning names/columns/separation, two-CV order/preservation, candidate-identity semantics, historical content preservation, link validity, no sensitive content, and docs-config hard gates.
  - A3 Batch Evidence: Traceability/ledger ownership for P13-EVID-01, browser-procedure ownership for P13-CV-01, and evidence rows supporting every P12/P13 requirement.
  - Acceptance:
    - Every exact P12/P13 ID occurs once in the additive matrix and once as a ledger requirement row with a source-supported method/evidence owner.
    - All requirement rows begin `NOT RUN`; the matrix has no PASS claim and historical matrix/checklist rows are unchanged.
    - All three exact immutable baseline rows, the append-only execution-attempt table, and the separate five-column warning table are present and source-complete.
    - The CV Manager supplement contains the exact A/B lifecycle, active-A evidence/graph proof, archived-B cleanup, and shared-data preservation contract.
    - No raw fixture/provider content, credential, runtime database, personal screenshot, concrete orchestrator run artifact, or unrelated edit is introduced.
  - Validation:
    - Required: `rg -n "P12-|P13-|current_message|job_save_confirmation|Nguồn|BASE-PJD-01|BASE-PJD-02|BASE-PJD-03" docs/acceptance/full_functional_test_matrix.md docs/acceptance/plan13_acceptance_ledger.md docs/acceptance/cv_manager_checklist.md` -> PASS evidence: every exact requirement, ledger link, vocabulary term, and immutable attempt label is present; freshness: after the last documentation edit
    - Required: compare the `BASE-PJD-01..03` rows in `docs/acceptance/plan13_acceptance_ledger.md` byte-for-content against `docs/plans/Plan_13.md` > `### Traceability and browser evidence` -> PASS evidence: dates, product/project values, run IDs, observed results, and dispositions match exactly; freshness: final attempt only
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: after the last documentation edit
  - Blocked Condition: Missing/unreadable acceptance sources is `BLOCKED_MISSING_REF`; ambiguous existing status/history ownership is `BLOCKED_AMBIGUOUS_REF`; conflict over IDs, immutable evidence, candidate identity, or warning separation is `BLOCKED_SOURCE_CONFLICT`; a root change requiring plan/task/product/test/config or historical rewrite is `BLOCKED_SCOPE_CONFLICT`; unavailable repository search/diff tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `docs/acceptance/full_functional_test_matrix.md`, `docs/acceptance/plan13_acceptance_ledger.md`, `docs/acceptance/cv_manager_checklist.md`

## Mandatory Batch05 - Frozen-Candidate Release Revalidation

### Goal

Freeze one product/test/config candidate, prove it through fresh automated/static/
structure gates, then execute the exact named-project browser matrix with safe
cleanup/restoration and append-only release evidence.

### Dependencies

- Batch01 through Batch04 tasks and their batch audits accepted.
- Task (05A) freezes and proves the automated candidate before (05B) starts any
  fixed-port or browser work.
- The candidate remains identical across both tasks; any later product, test,
  dependency, or configuration edit invalidates affected evidence and returns work
  to the owning repair task.

### Scope Boundary

- This batch owns final gate execution and additive acceptance evidence only.
  Task (05A) may edit only the Plan 13 ledger. Task (05B) may edit the ledger, the
  additive Plan 13 CV checklist section, and `README.md` only if a documented
  command/status actually became stale.
- Neither task may repair product/tests/config, change plans/tasks, update canonical
  checkboxes, commit, absorb the unrelated deletion, expose secrets/content, or
  mutate any non-smoke external state outside the exact source-authorized normal-
  stack stop/restore transaction.

### Tasks

- [ ] (05A): Freeze the candidate and record fresh automated, static, and structure evidence
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch05 - Frozen-Candidate Release Revalidation` > `(05A)`
  - Source of Truth: `docs/plans/Plan_13.md` > `### Traceability and browser evidence` candidate-freeze rules, `## Implementation` step 8, `## Verification` rows from `Provider schema/runtime` through `Plan/traceability`, and `## Completion Contract`; `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 7: Run focused/full gates and browser acceptance` steps 1-3 and `## Task 8: Final regression/scope review and handoff` steps 1-3.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(05A)` -> task authority
    - source-freeze: repository `docs/plans/Plan_13.md` > `### Traceability and browser evidence` -> candidate identity/freshness authority
    - source-verification: repository `docs/plans/Plan_13.md` > `## Verification` -> exact automated/static/structure commands and PASS evidence
    - accepted-ledger-owner: repository `docs/tasks/task_13.md` > `(04A)` -> ledger structure dependency
    - validation-release-automation: repository `README.md` > verification commands and testing policy -> current command/environment context
  - Source Requirements:
    - Before final gates, record candidate identity as base HEAD plus a SHA-256 manifest over every modified/deleted/untracked non-acceptance product, test, dependency, and configuration path; deleted paths use literal `DELETED`.
    - Run the exact focused/full backend, focused/full frontend, lint, type, build, existing CV regressions, shared plan validator, traceability, diff, route/tool/topology, dependency/migration/Compose, secret/data, and scope checks on that candidate.
    - Reuse (03A)'s positive pypdf/provider evidence only when its recorded product/test/config manifest matches the frozen candidate; otherwise rerun the two exact project-interpreter commands before acceptance.
    - Append dated automated/mixed attempt rows and update only source-supported requirement summaries; preserve every earlier failure and keep known warnings in their separate table.
    - Make no product/test/config repair in this task. Any failed gate requiring such a change blocks and returns to the owning earlier task; after repair, freeze a new candidate and rerun affected gates.
  - Dependencies: Batch01 through Batch04 accepted and audited.
  - User Action: Make the project `.venv`, frontend dependencies, and any provider access needed for a stale/missing positive diagnostic available without sharing `.env` values.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/plan13_acceptance_ledger.md`
  - Allowed Files: `docs/acceptance/plan13_acceptance_ledger.md` only. All product/test/config/plan/task/README/checklist files are read-only; exclude `.env`, runtime data, screenshots, prior evidence rewrites, task checkbox updates, and the unrelated deleted specification. If a gate exposes a product defect, block instead of editing it here.
  - Agent Work:
    1. Verify all earlier accepted artifacts/evidence and compute the source-defined candidate identity before running gates. Enumerate changed non-acceptance paths from Git, sort repository-relative paths ordinally, hash each existing file with SHA-256, use `DELETED` for absent paths, hash the UTF-8 `path<TAB>value<LF>` manifest, and record the base HEAD, manifest digest, and path list without file contents.
    2. Run the exact Plan 13 focused backend/provider/repair/confirmation/CV/diagnostic gates, then backend ruff, mypy, and full pytest on the frozen candidate.
    3. Run the exact focused frontend dialog/confirmation/CV/card gates, then full Vitest, lint, typecheck, and build on the same candidate.
    4. Verify or conditionally refresh the positive diagnostic pair, then run the shared plan validator, traceability search, architecture/route/tool-count/loop/schema/dependency/Compose diffs, `git diff --check`, and scoped status review.
    5. Append final-attempt automated evidence to the ledger with the exact candidate identity and evidence-owner classification; retain every failed attempt and block on any required out-of-bound repair.
  - Output: One frozen candidate has fresh automated/static/structure evidence and an append-only ledger record ready for disposable browser validation.
  - A1 Outcome: The exact frozen product/test/config candidate passes all fake-backed backend/frontend/static/build/diagnostic/plan/scope gates, with candidate identity and every automated attempt recorded without repository repair.
  - A2 Review Focus: Accepted prior provenance, deterministic manifest construction/path coverage, candidate equality with reused diagnostic evidence, every command/exit/freshness, automated-vs-browser ownership, first-failure retention, warning separation, route/tool/topology/schema/dependency/Compose scope, no product edit or sensitive content, and docs-config hard gates.
  - A3 Batch Evidence: Frozen candidate and automated validation rows for P13-JD-01/02/03, P13-A11Y-01, P13-DIAG-01, P13-EVID-01, P13-REG-01, and the automated slices of all P12 requirements.
  - Acceptance:
    - The ledger records base HEAD plus a deterministic SHA-256 content-manifest fingerprint and bounded path list covering every changed product/test/dependency/config path while excluding append-only acceptance evidence.
    - Every required focused/full backend/frontend/static/build/CV/diagnostic/plan/traceability/scope command passes on that exact candidate with final-attempt evidence.
    - Reused positive diagnostic evidence has the identical candidate manifest, or the exact positive pair is rerun and passes after the final relevant edit.
    - Architecture remains one Agent/decision/ToolNode, seven tools, six passes, with no route, migration, dependency, schema, Compose, evaluation, security/mobile, real-data, secret, or unrelated drift.
    - The ledger preserves every prior attempt and contains no browser claim for fake/provider counters; no repository file outside the ledger changes in this task.
  - Validation:
    - Required: from the repository root run this deterministic candidate-identity procedure and record `$baseHead`, `$candidateManifestSha256`, and `$candidatePaths` in the A1 report and ledger without file contents:

      ```powershell
      $baseHead = (git rev-parse HEAD).Trim()
      $candidatePaths = [string[]]@(
          @(
              git diff --name-only --no-renames HEAD --
              git ls-files --others --exclude-standard
          ) |
              Where-Object {
                  $_ -and
                  $_ -notmatch '^docs/(acceptance|plans|tasks|superpowers)/' -and
                  $_ -ne 'README.md' -and
                  $_ -notmatch '^\.agent/'
              } |
              Select-Object -Unique
      )
      [Array]::Sort($candidatePaths, [StringComparer]::Ordinal)
      $manifestEntries = foreach ($path in $candidatePaths) {
          $value = if (Test-Path -LiteralPath $path -PathType Leaf) {
              (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
          } else {
              'DELETED'
          }
          "$path`t$value"
      }
      $manifestText = if ($manifestEntries.Count -gt 0) {
          ($manifestEntries -join "`n") + "`n"
      } else {
          ''
      }
      $sha256 = [System.Security.Cryptography.SHA256]::Create()
      try {
          $candidateManifestSha256 = [BitConverter]::ToString(
              $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($manifestText))
          ).Replace('-', '').ToLowerInvariant()
      } finally {
          $sha256.Dispose()
      }
      $baseHead
      $candidateManifestSha256
      $candidatePaths
      ```

      -> PASS evidence: stable repeated output on the unchanged working tree, all changed product/test/dependency/config paths represented, deleted paths mapped to `DELETED`, and acceptance/planning/orchestrator paths excluded; freshness: immediately before final gates
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py tests/unit/test_phase0_diagnostics.py -q; & '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py tests/integration/test_active_cv_tool.py tests/integration/test_cv_manager_api.py tests/integration/test_cv_manager_deletion.py -q; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q; Set-Location ..` -> PASS evidence: every command exits `0`; freshness: final candidate attempt only
    - Required: `Set-Location frontend; npm test -- --run src/test/active-cv-source.test.tsx src/test/assistant-response.test.tsx src/test/job-save-confirmation.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts; npm test -- --run src/test/cv-manager.test.tsx src/test/cv-manager-api.test.ts src/test/empty-match-card.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/approval-card.test.tsx; npm test -- --run; npm run lint; npm run typecheck; npm run build; Set-Location ..` -> PASS evidence: every command exits `0`; freshness: final candidate attempt only
    - Required: verify the accepted (03A) positive pypdf/provider evidence carries the same candidate manifest; when missing or different, run `& '.\.venv\Scripts\python.exe' infrastructure/scripts/verify_pdf_extraction.py; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_shopaikey.py` -> PASS evidence: matching manifest or fresh exit `0` terminal PASS markers with sanitized output; freshness: same frozen candidate
    - Required: `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json; rg -n "P12-|P13-|current_message|job_save_confirmation|Nguồn|BASE-PJD" docs/acceptance; rg -n "TOOL_LOOP_LIMIT|DECISION_NODE_NAME|TOOLS_NODE_NAME|SAVE_JOB_NAME" backend/app/agent/graph.py backend/app/tools/registry.py; rg -n "@router\.(get|post|delete|put|patch)" backend/app/api; git diff HEAD -- backend/migrations frontend/package.json frontend/package-lock.json infrastructure/docker-compose.yml; git diff --check HEAD --; git status --short` -> PASS evidence: validator `valid: true`, traceability complete, accepted topology/routes unchanged, HEAD-relative protected diffs empty, whitespace clean across staged/unstaged tracked changes, and staged/unstaged/untracked status scoped; freshness: after the final ledger edit
  - Blocked Condition: Missing accepted prior batch evidence/ledger is `BLOCKED_MISSING_REF`; ambiguous candidate-path classification or mismatched authority is `BLOCKED_AMBIGUOUS_REF`; a failed gate or root fix requiring any file outside the ledger is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/Node/npm/test/build/search/Git tooling is `BLOCKED_ENVIRONMENT`; missing credential/network for a required diagnostic refresh is `BLOCKED_USER_ACTION`; unavailable diagnostic permission is `BLOCKED_PERMISSION`.
  - Files: `docs/acceptance/plan13_acceptance_ledger.md`

- [ ] (05B): Execute the named disposable browser matrix, restore prior state, and finalize evidence
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_13.md` > `## Mandatory Batch05 - Frozen-Candidate Release Revalidation` > `(05B)`
  - Source of Truth: `docs/plans/Plan_13.md` > `### Traceability and browser evidence`, `### Compose preflight, isolation, and restoration`, `### Ownership and invariants`, `## Implementation` steps 9-10, `## Verification` rows `Compose preflight/disposable services`, `Browser Plan 13 matrix`, `Named teardown and normal-stack restoration`, and `Scope hygiene`, plus `## Completion Contract`; `docs/superpowers/plans/2026-07-19-plan13-repair-revalidation-plan.md` > `## Task 7` browser/evidence intent and `## Task 8`, only where consistent with the primary source.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_13.md` > `(05B)` -> task authority
    - source-browser: repository `docs/plans/Plan_13.md` > `### Traceability and browser evidence` -> exact fixtures/order/evidence authority
    - source-compose: repository `docs/plans/Plan_13.md` > `### Compose preflight, isolation, and restoration` -> exact safety/recovery authority
    - accepted-candidate: repository `docs/tasks/task_13.md` > `(05A)` -> frozen manifest and automated evidence dependency
    - accepted-cv-contract: repository `docs/tasks/task_13.md` > `(04A)` -> two-CV/ledger ownership dependency
    - validation-browser: repository `docs/plans/Plan_13.md` > `## Verification` > Compose/browser/teardown/scope rows -> validation authority
  - Source Requirements:
    - Verify (05A)'s base HEAD/content manifest is unchanged before startup and after browser evidence; product/test/dependency/config drift invalidates the affected evidence.
    - Run one real PowerShell `try/finally` transaction that first records configured services, every normal-project service state and component/overall health, fixed-port PID/process/project owners, and existing smoke state. Block on partial, unexpected, unhealthy, pre-existing smoke, or unrelated ownership.
    - Only when the known normal `infrastructure` project is fully running and healthy, stop exactly `frontend backend neo4j` with the source command; never run normal-project `down` or delete/rename normal volumes. If normal was stopped, leave it stopped.
    - Start only `jobagent-plan13-smoke`, verify exactly three services plus overall/SQLite/filesystem/Neo4j availability, and use only the complete source-defined synthetic CV/JD fixtures.
    - Through the in-app browser at desktop width, execute the exact two-CV lifecycle, active-A evidence/dialog flow, and terminal passive-JD order: English card/cancel; Vietnamese pending refresh and same run/execution/card rehydrate/save; exact Vietnamese repeat/confirm/same Job; long case card/cancel; sole URL; exact explicit direct-text request; separate full opt-out; separate full ambiguous case.
    - For the active-A answer, click **Nguồn**, verify one `dialog` named **Nguồn từ CV** with the exact returned record, verify **Mở CV gốc** without an evidence/chunk fetch, close once with the close button and verify trigger-focus return, then reopen, close with Escape, and verify trigger-focus return again.
    - Record only browser-owned durable state, SQLite Job/evaluation and Neo4j deltas, network order, console, run/execution identity, and sanitized logs. Any repair line must match only `^passive_jd_call_rejected reason=(invalid_first_call|invalid_repair_call) call_count=[0-9]+ tool_names=.* argument_keys=.*$`; raw/preview/argument/provider/prompt sentinels remain absent. Never claim automated fake/provider counters or paste fixture/provider content.
    - Preserve every failed attempt. In `finally`, tear down only the named smoke project with volumes, restore the normal components only if recorded running, health-check restoration, and retain recovery evidence/block if restoration fails.
    - Append final ledger/checklist results. Update `README.md` only if a documented command or status is stale; otherwise record `README unchanged`. After acceptance-only edits rerun structure/link/diff checks, not live browser/provider work.
  - Dependencies: Task (05A) accepted with a frozen manifest and all earlier batches accepted/audited.
  - User Action: Provide a usable ignored root `.env`, Docker Compose/Linux engine, provider access, in-app browser-control permission, and known access to fixed ports without sharing values. Unknown external port/project ownership or denied browser/runtime permission blocks execution.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/plan13_acceptance_ledger.md`, `docs/acceptance/cv_manager_checklist.md`; conditional `README.md`
  - Allowed Files: the ledger and additive Plan 13 CV checklist section; `README.md` only for a proven stale command/status; and the exact OS-temporary `jobagent-plan13-stack-state.json` recovery file, retained on recovery failure and removed only after successful teardown/restoration. Runtime mutation is limited to source-authorized `jobagent-plan13-smoke` resources and temporary synthetic data plus exact stop/restore of the known normal three containers. Exclude product/tests/config/plans/tasks, historical evidence rewrites, normal volume deletion, unrelated processes/projects, `.env`, real data, screenshots/provider transcripts, checkbox updates, and the unrelated deleted specification.
  - Agent Work:
    1. Recompute and compare the (05A) candidate manifest; inspect accepted ledger/two-CV/browser contracts and load the in-app browser-control workflow before any runtime change.
    2. In one `try/finally`, run the exact read-only preflight commands in Validation to capture Compose services, complete normal running/stopped and health state, fixed-port listener PID/process plus Docker Compose project correlation, normal volume/network identity, and absent smoke containers/volumes/networks; block safely on every source-defined condition.
    3. Stop only the known healthy normal three containers when recorded running, verify ports free, start only `jobagent-plan13-smoke`, and verify exact services plus complete health.
    4. Perform every source-defined browser action in exact order with the complete fixed fixtures, including pending refresh/history-then-one-resume network order; active-A dialog role/name/record/no-fetch/PDF; close-button then Escape closure with trigger-focus return after each; two-CV activation/delete preservation; terminal cancellations; dedupe identity; direct paths; opt-out; and the ambiguous turn.
    5. Capture browser-owned deltas/state/network/console/sanitized logs and append attempt-specific ledger/checklist evidence without overwriting failures or claiming fake counters.
    6. In `finally`, tear down only named smoke volumes, restore and health-check the normal project only if recorded running, or leave it stopped as found; retain recovery state and block on failed teardown/restoration.
    7. Verify candidate identity unchanged, update README only when source-proven stale, then run final plan/link/whitespace/status/secret/data/architecture checks after the last evidence-only edit.
  - Output: Fresh disposable browser/Compose evidence completes the frozen candidate's ledger while the exact prior normal runtime state and user data are preserved.
  - A1 Outcome: The frozen candidate passes the exact two-CV, accessible-dialog, passive-JD/direct/opt-out browser matrix with durable sanitized evidence, named-only cleanup, and verified restoration of the prior normal state.
  - A2 Review Focus: Candidate equality, real `try/finally`, complete pre-stop service/health/port ownership, exact authorized stop/start/down/restore commands, fixture completeness/order, history/resume network order, durable/browser evidence ownership, no fake-counter claims, no raw content/secrets, failure retention, terminal runs, SQLite/evaluation/Neo4j deltas, cleanup/restoration, final link/diff checks, conditional README basis, no product edit, and docs-config hard gates.
  - A3 Batch Evidence: Browser/two-CV/Compose/cleanup rows for P13-CV-01 and P13-EVID-01; final integrated evidence for every P13 requirement, all P12 supplement rows, P13-REG-01, file ownership, scope, secret/data hygiene, release readiness, and the eventual Orchestrator-owned committed SHA with post-commit plan/diff revalidation in the final handoff.
  - Acceptance:
    - Preflight records exactly three configured services, complete prior normal state/health, fixed-port owners, and absent smoke state, and changes nothing on any partial/unexpected/unrelated condition.
    - The named smoke stack alone starts healthy and receives only synthetic data; the two-CV flow proves active A evidence/graph truth, archived B cleanup, and shared Job/Skill preservation.
    - The active-A source flow proves one `dialog` named **Nguồn từ CV**, its exact returned record, original-PDF action without evidence fetch, close-button focus return, and Escape focus return.
    - Every passive/direct/opt-out/ambiguous browser turn uses the exact complete source fixture and terminal order; pending refresh rehydrates the same run/execution/card and yields history GET followed by exactly one resume POST.
    - Browser evidence records only observable deltas/state/network/console/sanitized logs, no automatic evaluation request, no fake/provider-counter claim, no sentinel leakage, and no pending approval at finish; every repair log line has the exact `passive_jd_call_rejected` prefix, allowed reason, and four-field shape.
    - Every failure remains append-only. Named smoke volumes alone are removed, the normal project is restored healthy only when previously running or remains stopped when previously stopped, and recovery evidence is retained on failure.
    - Candidate manifest remains unchanged; final plan/traceability/diff/status/secret/data/architecture checks pass after evidence edits, and README is either narrowly corrected for proven staleness or recorded unchanged.
  - Validation:
    - Required: rerun the exact candidate-identity procedure from (05A) before preflight and after the last browser action -> PASS evidence: identical base HEAD, manifest digest, and candidate path list; freshness: both boundaries of this task
    - Required: at the start of one PowerShell `try/finally`, run and retain this exact read-only preflight evidence before any stop:

      ```powershell
      $composeArgs = @('--env-file', '.env', '-f', 'infrastructure/docker-compose.yml')
      $normalProject = 'infrastructure'
      $smokeProject = 'jobagent-plan13-smoke'
      $statePath = Join-Path ([System.IO.Path]::GetTempPath()) 'jobagent-plan13-stack-state.json'
      $preflightPassed = $false
      $normalRestoreRequired = $false
      $smokeStartedByAttempt = $false
      $expectedServices = @('backend', 'frontend', 'neo4j')
      $fixedPorts = @(5173, 8000, 7474, 7687)

      if (Test-Path -LiteralPath $statePath) {
          throw 'Recover the recorded Plan 13 stack attempt before starting another'
      }
      $configuredServices = @(docker compose @composeArgs config --services)
      if ($LASTEXITCODE -ne 0) { throw 'Compose service discovery failed' }
      $normalPs = @(docker compose @composeArgs -p $normalProject ps -a --format json)
      if ($LASTEXITCODE -ne 0) { throw 'Normal-project state discovery failed' }
      $smokePs = @(docker compose @composeArgs -p $smokeProject ps -a --format json)
      if ($LASTEXITCODE -ne 0) { throw 'Smoke-project state discovery failed' }
      $normalRows = @($normalPs | ForEach-Object { $_ | ConvertFrom-Json })
      $smokeRows = @($smokePs | ForEach-Object { $_ | ConvertFrom-Json })
      $normalServiceSetMatches = (
          $normalRows.Count -eq 0 -or
          @(Compare-Object (
              $expectedServices | Sort-Object
          ) (
              $normalRows.Service | Sort-Object
          )).Count -eq 0
      )
      $normalFullyRunningHealthy = (
          $normalRows.Count -eq 3 -and
          @($normalRows | Where-Object {
              $_.State -ne 'running' -or $_.Health -ne 'healthy'
          }).Count -eq 0
      )
      $normalFullyStopped = (
          $normalRows.Count -in @(0, 3) -and
          @($normalRows | Where-Object { $_.State -eq 'running' }).Count -eq 0
      )
      $listeners = @(
          Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
              Where-Object { $_.LocalPort -in $fixedPorts } |
              Select-Object LocalAddress, LocalPort, OwningProcess
      )
      $listenerProcesses = @(
          $listeners |
              Select-Object -ExpandProperty OwningProcess -Unique |
              ForEach-Object {
                  Get-Process -Id $_ -ErrorAction SilentlyContinue |
                      Select-Object Id, ProcessName, Path
              }
      )
      $dockerIds = @(docker ps -aq)
      if ($LASTEXITCODE -ne 0) { throw 'Docker container discovery failed' }
      $dockerPortProjects = @(
          $dockerIds | ForEach-Object {
              $inspectJson = @(docker inspect $_)
              if ($LASTEXITCODE -ne 0) { throw "Docker inspect failed for $_" }
              $inspected = @($inspectJson | ConvertFrom-Json)[0]
              [PSCustomObject]@{
                  Id = $inspected.Id
                  Name = $inspected.Name
                  Ports = ($inspected.NetworkSettings.Ports | ConvertTo-Json -Compress)
                  Project = $inspected.Config.Labels.'com.docker.compose.project'
              }
          }
      )
      $normalVolumes = @(
          docker volume ls --filter "label=com.docker.compose.project=$normalProject" --format '{{.Name}}'
      )
      if ($LASTEXITCODE -ne 0) { throw 'Normal-project volume discovery failed' }
      $normalNetworks = @(
          docker network ls --filter "label=com.docker.compose.project=$normalProject" --format '{{.Name}}'
      )
      if ($LASTEXITCODE -ne 0) { throw 'Normal-project network discovery failed' }
      $smokeVolumes = @(
          docker volume ls --filter "label=com.docker.compose.project=$smokeProject" --format '{{.Name}}'
      )
      if ($LASTEXITCODE -ne 0) { throw 'Smoke-project volume discovery failed' }
      $smokeNetworks = @(
          docker network ls --filter "label=com.docker.compose.project=$smokeProject" --format '{{.Name}}'
      )
      if ($LASTEXITCODE -ne 0) { throw 'Smoke-project network discovery failed' }
      $normalHealth = if ($normalFullyRunningHealthy) {
          Invoke-RestMethod http://127.0.0.1:8000/api/health
      } else {
          $null
      }
      $unrelatedListeners = @(
          $listeners | Where-Object {
              $publishedPort = [string]$_.LocalPort
              -not @($dockerPortProjects | Where-Object {
                  $_.Project -eq $normalProject -and
                  $_.Ports -match ('"HostPort":"' + [regex]::Escape($publishedPort) + '"')
              })
          }
      )

      if (@(Compare-Object ($expectedServices | Sort-Object) ($configuredServices | Sort-Object)).Count -ne 0) {
          throw 'Compose service set is not exactly backend/frontend/neo4j'
      }
      if (-not $normalServiceSetMatches -or (-not $normalFullyRunningHealthy -and -not $normalFullyStopped)) {
          throw 'Normal project is partial, unexpected, or unhealthy'
      }
      if (
          $normalHealth -ne $null -and
          (
              $normalHealth.overall -ne 'available' -or
              $normalHealth.sqlite -ne 'available' -or
              $normalHealth.filesystem -ne 'available' -or
              $normalHealth.neo4j -ne 'available'
          )
      ) {
          throw 'Normal project component health is unavailable'
      }
      if ($smokeRows.Count -ne 0 -or $smokeVolumes.Count -ne 0 -or $smokeNetworks.Count -ne 0) {
          throw 'A pre-existing Plan 13 smoke project must be preserved and inspected'
      }
      if ($unrelatedListeners.Count -ne 0) {
          throw 'An unrelated process/project owns a fixed port'
      }
      if (
          $normalFullyRunningHealthy -and
          @(Compare-Object ($fixedPorts | Sort-Object) (
              $listeners.LocalPort | Sort-Object -Unique
          )).Count -ne 0
      ) {
          throw 'Running normal project does not own the complete fixed-port set'
      }
      ```

      -> PASS evidence: configured services equal the expected set; `$normalServiceSetMatches` and exactly one of `$normalFullyRunningHealthy`/`$normalFullyStopped` is true; API health for a running normal stack reports overall/SQLite/filesystem/Neo4j available; `$smokeRows`, smoke volumes, and smoke networks are empty; every fixed-port listener is correlated to PID/process and the known normal Compose project or ports are free; normal volume/network identities are saved for post-finally comparison; freshness: immediately before any runtime change
    - Required: only after the preflight PASS, persist recovery state before the first mutation and set ownership flags around the exact native commands:

      ```powershell
      $recoveryState = [ordered]@{
          normal_project = $normalProject
          normal_was_running = $normalFullyRunningHealthy
          normal_restore_required = $false
          smoke_project = $smokeProject
          smoke_was_absent = $true
          smoke_start_attempted = $false
          normal_ps = $normalPs
          normal_volumes = $normalVolumes
          normal_networks = $normalNetworks
          fixed_port_listeners = $listeners
          fixed_port_processes = $listenerProcesses
          docker_port_projects = $dockerPortProjects
      }
      $recoveryState | ConvertTo-Json -Depth 8 |
          Set-Content -LiteralPath $statePath -Encoding utf8 -ErrorAction Stop
      if (-not (Test-Path -LiteralPath $statePath)) {
          throw 'Recovery state was not persisted'
      }
      $preflightPassed = $true

      if ($normalFullyRunningHealthy) {
          $recoveryState.normal_restore_required = $true
          $recoveryState | ConvertTo-Json -Depth 8 |
              Set-Content -LiteralPath $statePath -Encoding utf8 -ErrorAction Stop
          $normalRestoreRequired = $true
          docker compose @composeArgs -p $normalProject stop frontend backend neo4j
          if ($LASTEXITCODE -ne 0) { throw 'Normal-project stop failed' }
      }
      $remainingListeners = @(
          Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
              Where-Object { $_.LocalPort -in $fixedPorts }
      )
      if ($remainingListeners.Count -ne 0) {
          throw 'A fixed port remained occupied after authorized preflight/stop'
      }

      $recoveryState.smoke_start_attempted = $true
      $recoveryState | ConvertTo-Json -Depth 8 |
          Set-Content -LiteralPath $statePath -Encoding utf8 -ErrorAction Stop
      $smokeStartedByAttempt = $true
      docker compose @composeArgs -p $smokeProject up --build -d --wait --wait-timeout 180
      if ($LASTEXITCODE -ne 0) { throw 'Named smoke startup failed' }
      ```

      Then run `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan13-smoke ps -a --format json`, check its exit immediately, query `http://127.0.0.1:8000/api/health`, rerun the project-label volume/network queries with immediate exit checks, and inspect returned smoke resources with `docker volume inspect` / `docker network inspect` -> PASS evidence: exactly backend/frontend/neo4j healthy, overall/SQLite/filesystem/Neo4j available, exactly the Compose-defined `app_data`, `neo4j_data`, and `neo4j_logs` smoke volumes plus the smoke default network are project-owned, normal volume identities remain unchanged, and recovery state/flags prove this attempt owns every cleanup action; freshness: current attempt only
    - Required: execute the complete browser-owned rows and mixed-row browser slices in `docs/plans/Plan_13.md` > `### Traceability and browser evidence` through the in-app browser at desktop width -> PASS evidence: exact two-CV lifecycle; one active-A `dialog` named **Nguồn từ CV** with exact record, no evidence fetch, original PDF, close-button focus return, reopen/Escape focus return; exact terminal JD sequence; actual run/execution identities; history-then-single-resume network order; durable state/deltas; clean console; no raw sentinels; every `passive_jd_call_rejected` line matches only the exact allowed reason/call-count/tool-name/argument-key shape; and no pending approval; freshness: current named smoke attempt only
    - Required: use this ownership-gated `finally` contract; a preflight failure before this attempt owns smoke state must never run `down`:

      ```powershell
      $recoveryErrors = @()
      if ($preflightPassed -and $smokeStartedByAttempt) {
          docker compose @composeArgs -p $smokeProject down --volumes --remove-orphans
          if ($LASTEXITCODE -ne 0) {
              $recoveryErrors += 'Named smoke teardown failed'
          }
      }
      if ($preflightPassed -and $normalRestoreRequired) {
          docker compose @composeArgs -p $normalProject up -d --wait --wait-timeout 180
          if ($LASTEXITCODE -ne 0) {
              $recoveryErrors += 'Normal-project restoration failed'
          } else {
              try {
                  $restoredHealth = Invoke-RestMethod http://127.0.0.1:8000/api/health
                  if (
                      $restoredHealth.overall -ne 'available' -or
                      $restoredHealth.sqlite -ne 'available' -or
                      $restoredHealth.filesystem -ne 'available' -or
                      $restoredHealth.neo4j -ne 'available'
                  ) {
                      $recoveryErrors += 'Restored normal-project health is unavailable'
                  }
              } catch {
                  $recoveryErrors += 'Restored normal-project health query failed'
              }
          }
      }
      if ($preflightPassed) {
          $postSmokePs = @(docker compose @composeArgs -p $smokeProject ps -a --format json)
          if ($LASTEXITCODE -ne 0) { $recoveryErrors += 'Post-cleanup smoke state query failed' }
          $postNormalPs = @(docker compose @composeArgs -p $normalProject ps -a --format json)
          if ($LASTEXITCODE -ne 0) { $recoveryErrors += 'Post-cleanup normal state query failed' }
          $postNormalRows = @($postNormalPs | ForEach-Object { $_ | ConvertFrom-Json })
          $postSmokeVolumes = @(
              docker volume ls --filter "label=com.docker.compose.project=$smokeProject" --format '{{.Name}}'
          )
          if ($LASTEXITCODE -ne 0) { $recoveryErrors += 'Post-cleanup smoke volume query failed' }
          $postSmokeNetworks = @(
              docker network ls --filter "label=com.docker.compose.project=$smokeProject" --format '{{.Name}}'
          )
          if ($LASTEXITCODE -ne 0) { $recoveryErrors += 'Post-cleanup smoke network query failed' }
          $postNormalVolumes = @(
              docker volume ls --filter "label=com.docker.compose.project=$normalProject" --format '{{.Name}}'
          )
          if ($LASTEXITCODE -ne 0) { $recoveryErrors += 'Post-cleanup normal volume query failed' }
          $postNormalNetworks = @(
              docker network ls --filter "label=com.docker.compose.project=$normalProject" --format '{{.Name}}'
          )
          if ($LASTEXITCODE -ne 0) { $recoveryErrors += 'Post-cleanup normal network query failed' }
          if ($postSmokePs.Count -ne 0 -or $postSmokeVolumes.Count -ne 0 -or $postSmokeNetworks.Count -ne 0) {
              $recoveryErrors += 'Named smoke resources remain after cleanup'
          }
          if ($normalFullyRunningHealthy) {
              if (
                  $postNormalRows.Count -ne 3 -or
                  @($postNormalRows | Where-Object {
                      $_.State -ne 'running' -or $_.Health -ne 'healthy'
                  }).Count -ne 0
              ) {
                  $recoveryErrors += 'Prior running normal state was not restored'
              }
          } elseif (@($postNormalRows | Where-Object { $_.State -eq 'running' }).Count -ne 0) {
              $recoveryErrors += 'Prior stopped normal state was not preserved'
          }
          if (
              @(Compare-Object ($normalVolumes | Sort-Object) ($postNormalVolumes | Sort-Object)).Count -ne 0 -or
              @(Compare-Object ($normalNetworks | Sort-Object) ($postNormalNetworks | Sort-Object)).Count -ne 0
          ) {
              $recoveryErrors += 'Normal-project volume/network identity changed'
          }
          if ($recoveryErrors.Count -eq 0) {
              Remove-Item -LiteralPath $statePath
          }
      }
      if ($recoveryErrors.Count -ne 0) {
          throw ($recoveryErrors -join '; ')
      }
      ```

      -> PASS evidence: pre-existing smoke state is never removed; only smoke resources this attempt may have created are torn down; restoration is attempted even after teardown failure; named smoke containers/volumes/networks are absent; exact preflight normal volume/network identities and prior running/stopped state are preserved; and the recovery file is deleted only after every teardown/restoration/post-check succeeds, otherwise retained; freshness: same attempt even after a failure
    - Required: `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json; rg -n "P12-|P13-|current_message|job_save_confirmation|Nguồn|BASE-PJD" docs/acceptance; git diff --check HEAD --; git status --short` plus inspect changed paths, routes, migrations, manifests, registry, graph nodes, source lengths, tracked data/secrets, and the unrelated deleted-spec path -> PASS evidence: validator `valid: true`, links/evidence complete, whitespace clean across staged/unstaged tracked changes, changes confined to allowed evidence/conditional README, unrelated deletion untouched, and no scope/secret/data drift; freshness: after the last evidence-only edit
  - Blocked Condition: Missing accepted (05A) candidate/evidence or (04A) browser contract is `BLOCKED_MISSING_REF`; conflicting runtime/evidence authority is `BLOCKED_SOURCE_CONFLICT`; candidate drift, a required product/test/config repair, or any required edit outside allowed docs is `BLOCKED_SCOPE_CONFLICT`; missing/invalid `.env`, provider access, or required external setup is `BLOCKED_USER_ACTION`; unavailable Docker/browser/Python/Node/runtime, partial/unhealthy/unexpected normal services, a pre-existing smoke project/volume/network, unrelated fixed-port ownership, missing recovery-state evidence, failed smoke health, failed named teardown, or failed normal-state restoration is `BLOCKED_ENVIRONMENT`; denied permission to inspect/control the browser, Docker, known normal containers, or named smoke resources is `BLOCKED_PERMISSION`. Every blocked path preserves captured recovery evidence and must not trigger broader cleanup.
  - Files: `docs/acceptance/plan13_acceptance_ledger.md`, `docs/acceptance/cv_manager_checklist.md`; conditional `README.md`
