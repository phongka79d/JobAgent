# JobAgent Plan 14 Execution Tasks

## Purpose

Translate `docs/plans/Plan_14.md` into the mandatory implementation and evidence
chain for intent-aware long pasted-JD confirmation. Passive save intent must
reach the existing **Lưu JD / Không lưu** current-message flow without exact
phrases or five-line formatting, while analysis-only and opt-out turns stay
ordinary conversation and no malformed provider arguments reach `ToolNode`.

## Project Context Notes

- Root `README.md` was read completely before derivation. JobAgent is a local
  single-user React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, and ShopAIKey app
  with one ignored root `.env`, exactly three Compose services on loopback ports,
  fake-backed automated tests, and synthetic-only browser evidence.
- README reports Plan 13 Batch01–Batch04 A3 PASS on worktree (Batch04 base
  `175c404`) with Plan 12 Batch01–Batch05 accepted baseline on product HEAD
  `887d4f6`. Final commits remain orchestrator-owned. Observed repository HEAD
  during this authoring pass was `611e2e9` (intent-aware design/docs commit);
  execution must verify Plan 13 acceptance evidence rather than infer it only
  from README prose.
- The current user invoked `task-writing-agent` for `docs/plans/Plan_14.md`. This
  authorizes creation of this task contract only. It does not authorize product
  implementation, expand scope, or mark any task accepted.
- Primary authority is `docs/plans/Plan_14.md`. Supporting design
  `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` matches
  commit `611e2e9` and is aligned with the plan. Plan 13 remains the consumed
  provider-schema, strict `SaveJobInput`, one-ToolNode, and current-message
  confirmation baseline.
- Confirmed existing owners: `backend/app/agent/prompt.py`,
  `backend/app/agent/graph.py` (`_canonical_tool_call`,
  `_is_sole_current_message_save_job_call`, passive repair path),
  `backend/app/services/job_save_confirmation.py` (opt-out, sole-URL, obvious-JD
  predicates including five-line gate and 300 non-whitespace helper), and named
  unit/integration tests under `backend/tests/`. No frontend product file is
  expected to change.
- Automated tests use fakes and synthetic fixtures. Browser smoke may use the
  normal root `.env` stack with synthetic content only. Never record secrets,
  raw JD/CV bodies, prompts, provider payloads, authorization headers, or
  personal data.
- No root `AGENTS.md` was present. Applicable frontend Astryx rules are
  irrelevant because no frontend product edit is in scope.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_14.md`.
- Supporting:
  `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` (commit
  `611e2e9`),
  `docs/superpowers/specs/2026-07-19-save-job-passive-call-repair-design.md`,
  `docs/plans/Plan_13.md` (historical handoff), and
  `docs/plans/Master_plan.md` Version 1.9 sections cited by Plan 14.
- Context only: `README.md`, accepted Plan 12/13 task contracts and owners,
  existing prompt/graph/confirmation implementation and tests, and
  `infrastructure/docker-compose.yml`.

### Source Section Index

- `Plan_14.md` > `## Objective`, `## Master Requirement Coverage`,
  `## Prerequisites`, `## Scope`, and `## Out of Scope` -> mandatory P14-JD and
  P14-REG outcomes, dependencies, and exclusions.
- `Plan_14.md` > `### Intent and precedence` -> opt-out, sole URL, legacy exact
  command, and LLM semantic passive/analysis precedence.
- `Plan_14.md` > `### Canonical passive dispatch` -> sole `save_job` as positive
  intent, discard mixed provider args, emit one canonical
  `source='current_message'` call, multi-tool/invalid refusal, and
  `SaveJobInput` authority before `ToolNode`.
- `Plan_14.md` > `### Bounded semantic reconsideration` -> 300 non-whitespace
  gate for one extra model call only, not a JD classifier; skip opt-out/URL/
  legacy; at most one reconsideration per turn.
- `Plan_14.md` > `### Safety and compatibility` -> unchanged ordinary provider
  schema, no raw JD in logs/SSE/pending, zero pre-confirmation side effects,
  one Agent/one ToolNode/seven tools/six passes.
- `Plan_14.md` > `## Implementation`, `## Verification`, `## Handoff Contract`,
  and `## Completion Contract` -> test-first sequence, exact commands, handoffs,
  and binary completion.
- `2026-07-20-intent-aware-pasted-jd-design.md` > `## User-facing contract`,
  `## Selected design`, `## Testing and acceptance`, and `## Scope and files` ->
  approved intent matrix, hybrid LLM-first design, and ownership boundaries.

### Approved Architecture and Constraints

- This increment is a `bugfix` with no Master amendment. Keep public endpoints,
  SSE envelopes, schema/migrations, dependencies, provider/model, Compose
  topology, stores, frontend card/resume transport, and deployment rules
  unchanged.
- Keep one LangGraph Agent, one decision node, one ToolNode, exactly seven
  runtime tools, unchanged graph state/routing, and `TOOL_LOOP_LIMIT=6`.
- Keep ordinary provider-visible `save_job` schema and strict runtime
  `SaveJobInput` authoritative. Never weaken exact-one-source validation or
  silently ingest mixed provider `url`/`text` into the tool path.
- LLM owns semantic pure-paste versus analysis decisions. Five-line count,
  exact Vietnamese save phrases (other than the repository legacy technical
  command), and growing JD keyword lists must not be the semantic owner.
- The 300 non-whitespace character gate only decides whether one extra model
  reconsideration is spent; it is not a JD classifier.
- Clear opt-out wins and suppresses both canonicalization and confirmation.
  Sole HTTP(S) URL and the exact legacy `Please call save_job ...` direct-text
  command retain existing direct paths.
- A sole passive `save_job` intent is replaced with
  `_canonical_tool_call(SAVE_JOB_NAME, {"source": "current_message"}, ...)`
  before ToolNode. Invalid multi-tool or still-invalid repair returns the fixed
  no-confirmation text with zero ToolNode work.
- Confirmation remains pre-mutation. Before confirmation, zero Job, ingestion,
  extraction, embedding, evaluation, Neo4j, and SQLite mutation side effects.
  Save/cancel/replay keep one durable `(run_id, tool_call_id)` execution and no
  automatic evaluation.
- Raw JD/provider arguments, prompts, and previews stay out of logs, pending
  state, SSE payloads, and arguments summaries.
- A1 and A2 do not update task checkboxes or commit. A3 audits accepted batch
  evidence; commit readiness remains Orchestrator-owned.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Semantic prompt policy plus graph intent validation, canonical source dispatch, and bounded reconsideration with focused unit/integration proof | (01A), (01B) | Accepted Plan 13 provider/runtime/confirmation baseline and Plan 14 authorization |
| Batch02 | Full automated gates, plan validation, Docker health, and browser cancel/save smoke | (02A) | Batch01 |

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

## Mandatory Batch01 - Intent-Aware Prompt and Passive Graph Dispatch

### Goal

Make passive JD confirmation depend on LLM semantic intent plus graph-side
canonical source ownership so large formatting-collapsed pastes and natural-
language save requests reach the existing current-message interrupt, while
analysis-only, opt-out, sole-URL, and legacy direct paths remain truthful.

### Dependencies

- Accepted Plan 13 baseline: compatible ordinary provider schema, strict runtime
  `SaveJobInput`, current-message interrupt/resume, one ToolNode, and sanitized
  rejection behavior.
- Approved design
  `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` at commit
  `611e2e9` with unchanged user-intent matrix and confirmation-before-mutation.
- Existing owners: `production_registry`, `bind_chat_tools`,
  `_canonical_tool_call`, `_is_sole_current_message_save_job_call`,
  `SaveJobInput`, and the current confirmation card/resume path.
- Task order is (01A) then (01B). (01B) consumes the accepted prompt policy and
  must not recreate a second semantic owner.

### Scope Boundary

- This batch owns only Agent prompt semantic save-versus-analysis policy, graph
  pre-ToolNode passive intent validation/canonicalization/bounded
  reconsideration, optional reuse/extension of the large-text helper in
  `job_save_confirmation.py`, and directly required unit/integration tests.
- It does not own endpoints, SSE shapes, provider schema combinators, registry
  topology, Agent state, frontend card/resume transport, ingestion/evaluation
  implementations, migrations, dependencies, or release browser/Docker
  evidence (Batch02).

### Tasks

- [ ] (01A): Strengthen Agent prompt semantic save-versus-analysis policy
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_14.md` > `## Mandatory Batch01 - Intent-Aware Prompt and Passive Graph Dispatch` > `(01A)`
  - Source of Truth: `docs/plans/Plan_14.md` > `## Objective`, `### Intent and precedence`, `## Scope`, and `## Implementation` steps 3-4; `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` > `## User-facing contract` and `## Selected design` decision flow steps 1-2.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_14.md` > `(01A)` -> task authority
    - source-intent-precedence: repository `docs/plans/Plan_14.md` > `### Intent and precedence` -> semantic intent matrix
    - source-design-user-contract: repository `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` > `## User-facing contract` -> pure paste / NL save / analysis / analyse-and-save / opt-out
    - owner-prompt: repository `backend/app/agent/prompt.py` > `save_job` / passive pasted job description sections -> existing prompt owner to extend
    - validation-prompt: repository `docs/plans/Plan_14.md` > `## Verification` > `Focused backend` and tests in `backend/tests/unit/test_shopaikey_chat.py` -> prompt/binding contract regressions
  - Source Requirements:
    - Strengthen the existing system prompt so the model distinguishes: pure pasted JD (passive current-message confirmation), explicit natural-language save request (same confirmation), analysis-only request (no `save_job`), combined analyse-and-save (answer plus save confirmation for the save part), and clear opt-out (no `save_job`).
    - Pure large pasted JD or natural-language save intent must not require an exact Vietnamese command or newline layout.
    - Analysis/summarise/compare-without-save must instruct the model not to call `save_job`.
    - Preserve existing opt-out phrasing guidance, sole public HTTP(S) URL and explicit direct url/text path guidance, no auto `match_jobs`/evaluate after passive save, and ToolResult-only success claims.
    - Do not add a separate classifier model, growing keyword list, or make line count a semantic JD decision in the prompt.
  - Dependencies: Accepted Plan 13 baseline; no earlier Plan 14 task.
  - User Action: None; automated validation uses fakes and existing fixtures.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/agent/prompt.py`, `backend/tests/unit/test_shopaikey_chat.py`
  - Allowed Files: the two listed prompt/unit-test files only. Exclude `graph.py`, confirmation service (except read-only refs), tools/schemas, API, frontend, migrations, dependencies, acceptance docs, runtime data, and `.env`.
  - Agent Work:
    1. Inspect the current passive-JD and `save_job` truthfulness prompt sections and every prompt assertion in `test_shopaikey_chat.py`; reuse the existing builder rather than adding a second prompt path.
    2. Add failing prompt-contract tests for pure paste, natural-language save, analysis-only, analyse-and-save, and opt-out language requirements without asserting graph dispatch behavior owned by (01B).
    3. Implement the smallest prompt wording change that encodes the approved intent matrix and preserves direct URL/legacy and no-auto-evaluation guidance.
    4. Run focused prompt/binding unit tests and static checks on the allowed files only.
  - Output: System prompt encodes semantic pure-paste versus analysis versus save versus opt-out policy without formatting or exact-phrase requirements.
  - A1 Outcome: Prompt contract tests prove the model instructions distinguish pure paste, natural-language save, analysis-only, analyse-and-save, and opt-out while preserving opt-out/direct-path and no-auto-evaluation rules.
  - A2 Review Focus: Exact intent-matrix coverage, no line-count/exact-phrase semantic owner, no classifier/keyword-list growth, unchanged direct URL/legacy guidance, no graph/tool/schema edits, no secrets or raw-JD fixtures, bugfix scope, and validation freshness.
  - A3 Batch Evidence: Prompt-policy ownership row for P14-JD-01 and analysis/opt-out portions of P14-JD-03.
  - Acceptance:
    - Prompt text instructs pure pasted JD and natural-language save requests to use passive `source='current_message'` confirmation behavior without requiring exact command phrases or newline layout.
    - Prompt text instructs analysis-only requests not to call `save_job`, and analyse-and-save to cover both the answer and confirmation-gated save.
    - Clear opt-out, sole URL/direct path, ToolResult-only claims, and no automatic `match_jobs`/evaluate guidance remain present.
    - Only allowed prompt/test files change; registry, topology, schemas, tools, and frontend remain untouched.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_shopaikey_chat.py -q` -> PASS evidence: exit `0` with new/updated prompt intent-matrix assertions green; freshness: final attempt only.
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app/agent/prompt.py tests/unit/test_shopaikey_chat.py --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path inspection -> PASS evidence: exit `0` and only allowed files changed; freshness: final attempt only.
  - Blocked Condition: Missing accepted Plan 13 prompt/owner refs is `BLOCKED_MISSING_REF`; design/plan conflict on intent matrix is `BLOCKED_SOURCE_CONFLICT`; root fix requiring graph/tool/schema/frontend edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/agent/prompt.py`, `backend/tests/unit/test_shopaikey_chat.py`

- [ ] (01B): Canonicalize passive save_job intent and add bounded large-message reconsideration
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_14.md` > `## Mandatory Batch01 - Intent-Aware Prompt and Passive Graph Dispatch` > `(01B)`
  - Source of Truth: `docs/plans/Plan_14.md` > `### Intent and precedence`, `### Canonical passive dispatch`, `### Bounded semantic reconsideration`, `### Safety and compatibility`, `## Implementation` steps 1-6, and `## Verification` rows `Red reproduction` and `Focused backend`; `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` > `## Selected design` decision flow steps 1-5 and `## Testing and acceptance`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_14.md` > `(01B)` -> task authority
    - source-canonical-dispatch: repository `docs/plans/Plan_14.md` > `### Canonical passive dispatch` -> sole save intent and source-only rewrite
    - source-reconsideration: repository `docs/plans/Plan_14.md` > `### Bounded semantic reconsideration` -> 300 non-ws extra call gate
    - source-design-selected: repository `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` > `## Selected design` -> hybrid LLM-first design
    - owner-graph: repository `backend/app/agent/graph.py` > decision node, `_canonical_tool_call`, `_is_sole_current_message_save_job_call`, passive repair path -> implementation owner
    - owner-confirmation: repository `backend/app/services/job_save_confirmation.py` > opt-out/sole-URL/large-text helpers -> reuse only
    - accepted-prompt: repository `docs/tasks/task_14.md` > `(01A)` and `backend/app/agent/prompt.py` -> accepted semantic policy to consume
    - validation-focused: repository `docs/plans/Plan_14.md` > `## Verification` > `Red reproduction` and `Focused backend` -> validation authority
  - Source Requirements:
    - Before production edits, reproduce the original one-line mixed-call failure with a red graph test (`-k one_line_intent` or equivalent) that uses a 300+ non-whitespace one-line Vietnamese JD whose fake model emits mixed `text` plus `source='current_message'` (and empty placeholder if needed).
    - After opt-out, sole URL, and legacy exact direct-command precedence, inspect the first model response before `ToolNode`. In passive context, a sole `save_job` call is positive save intent even when optional provider fields are mixed, blank, or runtime-invalid; discard those arguments and emit exactly one canonical `source='current_message'` call via existing `_canonical_tool_call`.
    - Never forward raw model `url`/`text` values on the current-message ToolNode path. Validate the canonical call with `SaveJobInput` before execution; keep exact-one-source, preview bounds, opt-out, `run_id`, replay identity, and interrupt rules unchanged.
    - If the response has multiple tools or cannot be safely interpreted as one passive save intent, make at most one semantic repair; a still-invalid repair returns the fixed truthful no-confirmation response and zero ToolNode work.
    - If the first response has no tool call and the message has at least 300 non-whitespace characters, issue one additional normal-model reconsideration choosing between a normal answer and a source-only save confirmation. Skip reconsideration for opt-outs, sole URLs, and the exact legacy direct command. At most one reconsideration per user turn. The 300-character gate is not a JD classifier and must not use line count, exact phrases, or marker diversity as the semantic decision.
    - Five-line / formatting heuristics must not remain the owner of passive semantic confirmation for large one-line pastes. Analysis-only and opt-out must not create confirmation or mutation. Direct URL and legacy exact technical command paths remain compatible.
    - Preserve one Agent, one decision node, one ToolNode, seven tools, six passes, existing card/resume/dedupe/evaluation behavior, and zero pre-confirmation side effects (Job, ingestion, extraction, embedding, evaluation, Neo4j, SQLite mutation). Sanitized logs/argument summaries never include raw JD/provider payloads.
    - Reuse `SaveJobInput`, `_canonical_tool_call`, `_is_sole_current_message_save_job_call`, the current source resolver, and confirmation tool. Extend `job_save_confirmation.py` only if a coarse large-text helper is required; do not add a classifier model or second tool path.
  - Dependencies: Accepted (01A) prompt policy; accepted Plan 13 provider/runtime/confirmation baseline.
  - User Action: None for automated focused gates; use fakes only.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/agent/graph.py`, `backend/app/services/job_save_confirmation.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/unit/test_job_save_confirmation.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/integration/test_job_tools.py`
  - Allowed Files: the six listed graph/service/test files only. Prompt may be read-only reference; prompt edits belong to (01A). Exclude provider schema redesign, tools/registry topology changes, Agent state/runner redesign, API/SSE, frontend, migrations, dependencies, acceptance docs, runtime data, and `.env`.
  - Agent Work:
    1. Inspect current decision order, `_canonical_save_job_dispatch`, passive obvious-JD repair, `_is_sole_save_job_call` / `_is_sole_current_message_save_job_call`, confirmation interrupt path, and all callers; record the red one-line mixed-call assertion before production edits.
    2. Add failing unit tests for: one-line Vietnamese mixed-source positive intent; pure paste / natural-language save / analysis-only / analyse-and-save / opt-out / sole URL / legacy direct command; bounded no-tool reconsideration; malformed multi-tool refusal; zero pre-confirmation side-effect spies; sanitized logs.
    3. Implement the smallest graph (and optional large-text helper) changes: post-model sole-`save_job` canonicalization, bounded 300 non-ws reconsideration, precedence skips, and fixed invalid refusal with zero ToolNode work.
    4. Green the focused unit suites, then run affected integration tests for interrupt/resume, cancel, save, dedupe, terminal replay, and no automatic evaluation; fix only at this task's owning boundary.
    5. Inspect sanitized logs/argument summaries and changed-path hygiene; prove raw JD sentinels never leave the durable user message path.
  - Output: Decision node converts passive sole `save_job` intent into one canonical current-message confirmation call, supports one large-message reconsideration, and refuses unsafe calls without ToolNode side effects.
  - A1 Outcome: One-line and intent-matrix graph/integration tests pass with canonical `source='current_message'` confirmation only, analysis/opt-out/direct paths unchanged, zero pre-confirmation mutations, and no malformed provider args reaching ToolNode.
  - A2 Review Focus: Red-before-green evidence, sole-call canonicalization vs multi-tool refusal, 300-char reconsideration bounds/skips, no five-line semantic ownership for one-line paste, `SaveJobInput` authority, zero side-effect spies, topology invariants (1 Agent/1 ToolNode/7 tools/6 passes), sanitized logs, integration interrupt/cancel/save/dedupe/no-eval, allowed-file scope, and bugfix hard gates.
  - A3 Batch Evidence: Owning rows for P14-JD-01, P14-JD-02, P14-JD-03, and topology portions of P14-REG-01 plus exclusive graph decision ownership for this increment.
  - Acceptance:
    - A 300+ non-whitespace one-line Vietnamese-style JD whose model emits mixed `text`/`source` (and empty placeholder if present) produces exactly one canonical `source='current_message'` call and enters confirmation without `INVALID_JOB_INPUT` or ToolNode receipt of mixed fields.
    - Pure paste and natural-language save intents reach current-message confirmation; analysis-only and clear opt-out produce no confirmation and no mutation; sole URL and legacy exact direct command retain direct paths.
    - No-tool first response on a sufficiently large non-opt-out non-URL non-legacy message gets at most one reconsideration; valid source-only enters confirmation; normal text returns as final answer; invalid tool response yields fixed no-confirmation text and zero ToolNode work.
    - Fake spies show zero pre-confirmation Job/ingestion/extraction/embedding/evaluation/Neo4j/SQLite mutation calls; logs omit raw JD/provider payloads.
    - One Agent, one decision node, one ToolNode, seven tools, and `TOOL_LOOP_LIMIT=6` remain; no new endpoint, migration, dependency, tool, Agent node, or frontend product file.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_graph.py -q -k one_line_intent` -> PASS evidence: exit `0` on final green attempt after recorded red baseline; freshness: final attempt only (A1 must report the prior red observation).
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_graph.py tests/unit/test_job_save_confirmation.py tests/unit/test_shopaikey_chat.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py -q` -> PASS evidence: exit `0` with intent precedence, canonical dispatch, strict validation, confirmation/cancel/replay, no side effects, and direct paths; freshness: final attempt only.
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app/agent/graph.py app/services/job_save_confirmation.py tests/unit/test_agent_graph.py tests/unit/test_job_save_confirmation.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` plus changed-path, topology, side-effect-spy, and sanitized-log inspection -> PASS evidence: exit `0`, only allowed files plus already-accepted (01A) prompt/test files if present, no secrets/raw JD exposure, no topology/schema drift; freshness: final attempt only.
  - Blocked Condition: Missing accepted (01A) or Plan 13 owners is `BLOCKED_MISSING_REF`; plan/design conflict on dispatch ownership is `BLOCKED_SOURCE_CONFLICT`; root fix requiring provider combinators, new tools/endpoints, frontend, or other out-of-bound edits is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/agent/graph.py`, `backend/app/services/job_save_confirmation.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/unit/test_job_save_confirmation.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/integration/test_job_tools.py`

## Mandatory Batch02 - Release Gates and Browser Confirmation Smoke

### Goal

Prove the Batch01 intent-aware confirmation boundary on full automated gates, a
healthy rebuilt Compose stack, and a desktop browser cancel-plus-synthetic-save
smoke without expanding product scope or exposing raw JD content.

### Dependencies

- Batch01 tasks (01A) and (01B) accepted with matching A1/A2 evidence and
  Orchestrator `ACCEPTED` decisions.
- Local root `.env`, Docker Compose, free loopback ports, and browser access for
  smoke. Automated full gates remain fake-backed.

### Scope Boundary

- This batch owns only full backend/frontend gates, shared plan-structure
  validation, Docker rebuild/health, desktop browser confirmation/cancel/save
  evidence, scope hygiene, and reporting. No product feature expansion.
- It does not reopen Plan 11/13 accessibility, diagnostics, CV lifecycle,
  saved-JD API, release-ledger schema, mobile, security, or warning-cleanup work.

### Tasks

- [ ] (02A): Run full gates, Docker health, and browser confirmation smoke
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_14.md` > `## Mandatory Batch02 - Release Gates and Browser Confirmation Smoke` > `(02A)`
  - Source of Truth: `docs/plans/Plan_14.md` > `## Verification` rows `Backend static/full`, `Frontend regression/build`, `Plan structure`, `Docker health`, `Browser confirmation`, and `Scope hygiene`; `## Implementation` steps 7-9; and `## Completion Contract`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_14.md` > `(02A)` -> task authority
    - source-verification: repository `docs/plans/Plan_14.md` > `## Verification` -> exact release commands and expected evidence
    - source-completion: repository `docs/plans/Plan_14.md` > `## Completion Contract` -> binary release completion conditions
    - compose-owner: repository `infrastructure/docker-compose.yml` -> three-service stack
    - validation-health: repository `README.md` > health check via `GET /api/health` -> health evidence shape
  - Source Requirements:
    - Run full backend ruff/mypy/pytest and full frontend test/lint/typecheck/build with no topology/schema drift and existing confirmation/history/card behavior green.
    - Run shared plan-structure validator for contiguous Plans 1-14 with only Plan 14 terminal as defined by the validator expectations in Plan 14.
    - Rebuild and start Docker with root `.env`; verify overall, SQLite, filesystem, and Neo4j available via `GET /api/health`.
    - Desktop browser: open `http://localhost:5173/`, paste the original one-line JD shape, observe one confirmation card, choose **Không lưu** once (no Job/evaluation), then repeat with synthetic content and choose **Lưu JD** for existing result/dedupe path. Capture network, durable state, console, and sanitized-log evidence without exposing the JD body.
    - Leave the normal three-service stack healthy for the user, preserve volumes, and report commit/build/health/test evidence. Scope hygiene must show only Plan 14 owners, necessary tests/evidence, and no secrets/runtime data/new service/endpoint/migration/duplicate store.
  - Dependencies: Accepted Batch01 (01A) and (01B).
  - User Action: Provide a usable ignored root `.env` (without sharing values), Docker Desktop/Compose available, free loopback ports `5173`/`8000`/`7474`/`7687`, and desktop browser access. Missing environment is blocking for Docker/browser portions only after automated gates are otherwise attempted.
  - Runtime Policy:
    - check_after_seconds: 1200
    - timeout_seconds: 10800
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: evidence-only reports under `.agent/<plan-id>/<run-id>/`; product edits only if a Batch01 regression is proven and repaired within Batch01 owners with Orchestrator scope approval. No intentional product file change in this task.
  - Allowed Files: `.agent/<plan-id>/<run-id>/**` evidence/report paths written by the assigned A1 report location only. Product/test repairs required by a discovered regression must return as `BLOCKED_SCOPE_CONFLICT` unless the Orchestrator reopens Batch01 owners; do not edit frontend product files, new endpoints, migrations, dependencies, or acceptance-ledger schemas in this task.
  - Agent Work:
    1. Run full backend static/full pytest and full frontend test/lint/typecheck/build; record exit codes and summaries without secrets.
    2. Run plan-structure validator for `docs/plans` and record JSON validity / contiguous plan evidence.
    3. Rebuild and start Compose with root `.env`, wait for health, and record `GET /api/health` availability fields.
    4. Perform desktop browser cancel then synthetic confirmed-save smoke per Plan 14 Verification; record card, action lock, no pre-confirmation mutation, cancel emptiness, save/dedupe path, console, and sanitized logs without pasting raw JD bodies.
    5. Confirm stack remains up with volumes preserved; run `git diff --check` and short status/path review for scope hygiene.
  - Output: Fresh full-gate, plan-validator, Compose health, and browser cancel/save smoke evidence for Plan 14 completion.
  - A1 Outcome: Full automated gates pass, plan validator accepts Plans 1-14, Compose health is available, browser cancel and synthetic save behave correctly without raw-JD exposure, and the normal stack is left healthy with preserved volumes.
  - A2 Review Focus: Fresh final-attempt gate exits, plan contiguity, health payload fields, browser evidence completeness (one card, lock, cancel zero mutation, save path, no console errors, sanitized logs), volume preservation, no product scope expansion, and no secret/raw-JD leakage in reports.
  - A3 Batch Evidence: Release rows for P14-REG-01 and end-to-end confirmation of P14-JD-01 through P14-JD-03 on the integrated stack.
  - Acceptance:
    - Backend ruff, mypy, and full pytest exit `0`; frontend test, lint, typecheck, and build exit `0`.
    - Plan-structure validator reports contiguous Plans 1-14 with the Plan 14 terminal expectation from the plan.
    - Compose stack is healthy with overall/SQLite/filesystem/Neo4j available; stack is left running and volumes are preserved.
    - Browser smoke shows one confirmation card for the one-line paste, **Không lưu** with no Job/evaluation, and one synthetic **Lưu JD** using the existing result/dedupe path with no console errors or raw-JD logs.
    - Scope hygiene shows no secrets, runtime data, new service, endpoint, migration, or duplicate store; no frontend product requirement remains open for this plan.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` -> PASS evidence: valid contiguous Plans 1-14 per Plan 14 expectation; freshness: final attempt only.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` then `Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS evidence: services healthy; overall/SQLite/filesystem/Neo4j available; freshness: final attempt only.
    - Required: Desktop browser procedure in Plan 14 Verification `Browser confirmation` at `http://localhost:5173/` -> PASS evidence: one card, cancel with zero Job/evaluation, synthetic confirmed save on existing path, no console errors, sanitized logs without raw JD; freshness: final attempt only.
    - Required: `git diff --check; git status --short` plus changed-path review -> PASS evidence: exit `0` for diff check and scope limited to Plan 14 owners/evidence; freshness: final attempt only.
  - Blocked Condition: Missing usable root `.env`, Docker, free ports, or browser access after automated gates is `BLOCKED_ENVIRONMENT` or `BLOCKED_USER_ACTION` as applicable; product regression requiring out-of-batch edits is `BLOCKED_SCOPE_CONFLICT`; missing Plan 14 verification authority is `BLOCKED_MISSING_REF`.
  - Files: `.agent/<plan-id>/<run-id>/report/a1/**` (evidence only); no intentional product file ownership.

## Optional Future Tracks

This track is not part of the mandatory MVP batch chain.

- Provider-side schema combinators after ShopAIKey verifies support.
- Separate classifier model or typed composer intent replacing residual heuristics.
- Mobile, security acceptance, or Plan 11/13 reopened accessibility/diagnostics/
  CV/release-ledger work.
