# Plan_14: Intent-Aware Long Pasted-JD Confirmation

## Objective

Make passive JD saving depend on the LLM's semantic intent rather than an exact
Vietnamese command, line wrapping, or a five-line formatting heuristic. A large
message that the LLM identifies as a pasted JD must enter the existing
pre-mutation **Lưu JD / Không lưu** confirmation flow. Analysis-only requests
must remain ordinary conversation, and no malformed provider argument may reach
the runtime `save_job` validator or `ToolNode`.

## Source of Truth

- `docs/plans/Master_plan.md`: `### 11.2 Pasted-text confirmation boundary`,
  `## 12. Agent Architecture`, `### 13.4 save_job`, `### 15.7 Readable Agent
  responses and pasted-JD confirmation`, `## 20 Failure and Recovery Policy`,
  `## 24 Local Testing Strategy`, and `### Phase 10 - Readable Agent responses,
  active-CV sources, and pasted-JD save confirmation`.
- `docs/plans/Plan_13.md`: completed provider-visible schema, strict runtime
  validation, one ToolNode, current-message interrupt, and release evidence
  boundary.
- `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md`:
  approved user-intent rules, confirmation requirement, and selected hybrid
  LLM-first design.
- `docs/superpowers/specs/2026-07-19-save-job-passive-call-repair-design.md`:
  existing source-only validation and no-side-effect principles.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| P14-JD-01 | 11.2, 12.5, 15.7 | A pure large pasted JD or a natural-language save request reaches the existing current-message confirmation without requiring an exact phrase or newline layout. | Graph/prompt tests plus the original one-line Vietnamese browser paste. |
| P14-JD-02 | 13.4, 20 | Mixed `save_job` arguments are rejected before `ToolNode`; a positive passive save intent is converted to one canonical source-only call. | Red/green malformed-call test, strict `SaveJobInput` assertions, and zero pre-confirmation side-effect spies. |
| P14-JD-03 | 12.5, 20, 24 | Analysis-only, opt-out, URL, and legacy direct-command paths remain truthful and do not create a confirmation or mutation. | Intent-precedence unit/integration tests and direct-path regression suite. |
| P14-REG-01 | 12.1, 12.6, 24, 27 | One Agent, one decision node, one ToolNode, seven tools, six passes, existing card/resume/dedupe/evaluation behavior, and local Docker operation remain unchanged. | Full backend/frontend gates, plan validator, Compose health, and browser logs/state. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Plan_13 | Compatible ordinary provider schema, strict runtime `SaveJobInput`, current-message interrupt/resume, and sanitized release baseline | Run the focused graph/job-tool tests and reproduce the one-line mixed-call failure before editing. |
| Approved design | `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` at commit `611e2e9` | Confirm the user-intent matrix and confirmation-before-mutation rule are unchanged. |
| Existing runtime | `production_registry`, `bind_chat_tools`, `_canonical_tool_call`, and the current confirmation card | Search all callers and preserve the one-Agent/one-ToolNode topology. |
| Local environment | Root `.env`, `.venv`, Docker Compose, and synthetic/fake test seams | Use fakes for automated tests and preserve normal user volumes during browser verification. |

## Scope

- Strengthen the existing Agent prompt so it distinguishes a pure pasted JD,
  an explicit natural-language save request, an analysis-only request, a
  combined analyse-and-save request, and a clear opt-out.
- Extend the existing decision node to validate passive model decisions before
  dispatch. When the model expresses one passive `save_job` intent but includes
  mixed/placeholder source fields, discard those provider arguments and emit
  exactly one canonical `source='current_message'` call for confirmation.
- Add one bounded semantic reconsideration for a sufficiently large message when
  the first model response contains no tool call. The second decision may return
  a normal answer or a valid source-only call; there is no unbounded retry.
- Reuse `SaveJobInput` and `_is_sole_current_message_save_job_call` as the runtime
  authority. No raw model `url`/`text` values are forwarded to the current-message
  ToolNode path.
- Add test-first graph, prompt, integration, and no-side-effect coverage for the
  original one-line Vietnamese JD shape and the approved intent matrix.
- Run focused/full automated gates, build the Docker images, start the existing
  stack, and perform a desktop browser check of confirmation/cancel/save behavior.

## Out of Scope

- New public endpoint, SSE event, database table/migration, dependency, tool name,
  Agent node, ToolNode, state field, worker, queue, provider model, or deployment
  service.
- A separate classifier model, a growing JD keyword/opt-out list, or making line
  count a semantic JD decision.
- Automatic saving, automatic evaluation, `match_jobs` chaining, changes to the
  confirmation card/resume transport, or changes to direct URL/legacy exact
  `save_job` command semantics.
- Provider-side schema combinators, weakening strict runtime validation, silently
  ingesting mixed arguments, or rewriting stored chat/JD content.
- Reopening Plan 11/13 accessibility, diagnostics, CV lifecycle, saved-JD API,
  release-ledger, mobile, security, or warning-cleanup work.

## Target Directory Structure

```text
backend/
  app/agent/prompt.py                 # semantic save-versus-analysis policy
  app/agent/graph.py                  # bounded intent validation/dispatch
  app/services/job_save_confirmation.py  # reuse/extend large-text helper only if needed
  tests/unit/test_agent_graph.py      # red/green intent and malformed-call cases
  tests/unit/test_shopaikey_chat.py   # prompt/binding contract regressions
  tests/unit/test_job_save_confirmation.py
  tests/integration/test_chat_api.py
  tests/integration/test_job_tools.py
docs/plans/Plan_13.md                 # historical handoff only
docs/plans/Plan_14.md
```

No frontend product file is expected to change; the existing confirmation card
and SSE/resume contracts are exercised unchanged through the browser.

## Technical Specifications

### Intent and precedence

1. Clear opt-out wins and suppresses both canonicalization and confirmation.
2. A sole HTTP(S) URL retains its direct URL path.
3. The repository's exact technical `Please call save_job ...` acceptance
   command retains its legacy direct-text path.
4. For other turns, the normal LLM receives the full durable message and the
   semantic prompt policy. A pure pasted JD or natural-language request to save a
   JD is passive and requires current-message confirmation. A request to analyse,
   summarise, compare, or otherwise work on a JD without saving must not call
   `save_job`.

### Canonical passive dispatch

- Inspect the first model response before `ToolNode`.
- In passive context, a sole `save_job` call is positive save intent even when
  its optional provider fields are mixed, blank, or otherwise runtime-invalid.
- Do not pass those arguments to the tool. Replace the complete call with the
  existing `_canonical_tool_call(SAVE_JOB_NAME, {"source":
  "current_message"}, ...)` shape and retain the existing confirmation
  interrupt/source ownership path.
- If the response contains multiple tools or cannot be safely interpreted as one
  passive save intent, make at most one semantic repair; a still-invalid repair
  returns the existing truthful no-confirmation response and zero ToolNode work.
- The canonical call is validated by `SaveJobInput` before execution. Runtime
  exact-one-source, preview bounds, opt-out, `run_id`, replay identity, and
  interrupt rules remain unchanged.

### Bounded semantic reconsideration

- If the first response has no tool call, and the message has at least 300
  non-whitespace characters, issue one additional normal-model reconsideration
  with an instruction to choose between a normal answer and a source-only save
  confirmation based on the user's semantic intent.
- The 300-character gate only controls whether an extra model call is spent; it
  is not a JD classifier and does not inspect line count, exact phrases, or
  marker diversity.
- A valid source-only response enters confirmation. A normal-text response is
  returned as the final answer. An invalid tool response produces the fixed
  no-confirmation text and never reaches `ToolNode`.
- The reconsideration is skipped for opt-outs, sole URLs, and the exact legacy
  direct command. At most one reconsideration occurs per user turn.

### Safety and compatibility

- The existing provider-visible ordinary schema is unchanged; this plan fixes
  the graph boundary rather than adding unsupported provider combinators.
- Raw JD/provider arguments, prompts, and previews remain absent from logs,
  pending state, SSE payloads, and arguments summaries.
- Before confirmation, fake spies must show zero Job rows, ingestion, extraction,
  embedding, evaluation, Neo4j, and SQLite mutation calls. Save/cancel/replay
  continue using one durable `(run_id, tool_call_id)` execution.
- Preserve tool loop count/topology and all existing direct URL/text, dedupe,
  saved-JD, profile, matching, and evaluation behavior.

## Implementation

1. Run the current focused baseline and reproduce the original one-line failure;
   record the exact expected red assertion without changing production code.
2. Add a failing graph test with a 300+ character one-line Vietnamese JD whose
   fake model emits `text` plus `source='current_message'` and an empty
   placeholder field. Assert the current code dispatches no invalid call and the
   desired test is red before implementation.
3. Add failing prompt/graph tests for pure paste, natural-language save,
   analysis-only, analyse-and-save, opt-out, sole URL, and the legacy direct
   command. Add the bounded no-tool reconsideration and malformed multi-tool
   refusal cases.
4. Implement the smallest prompt and graph changes in their existing owners;
   reuse `SaveJobInput`, `_canonical_tool_call`, the current source resolver, and
   confirmation tool rather than adding a helper path or classifier model.
5. Run the focused backend suites and inspect sanitized logs/argument summaries;
   verify raw JD sentinels never leave the durable user message.
6. Run affected integration tests for interrupt/resume, cancel, save, dedupe,
   terminal replay, and no automatic evaluation. Fix callers at the owning
   boundary only.
7. Run full backend and frontend lint/type/test/build gates plus the shared plan
   validator. Review changed paths, file lengths, and scope hygiene.
8. Rebuild and start Docker with the root `.env`; verify health, then use the
   browser as a user to paste the original one-line MISA JD, observe the
   confirmation card, choose **Không lưu** once, and run one confirmed-save smoke
   with synthetic content. Capture network, durable state, console, and
   sanitized-log evidence without exposing the JD body.
9. Leave the normal stack running for the user, preserve volumes, and report the
   exact commit/build/health/test evidence.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Red reproduction | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_graph.py -q -k one_line_intent` | New regression fails before production change for the expected mixed-source/line-gate reason. |
| Focused backend | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_graph.py tests/unit/test_job_save_confirmation.py tests/unit/test_shopaikey_chat.py tests/integration/test_chat_api.py tests/integration/test_job_tools.py -q` | Intent precedence, canonical source dispatch, strict validation, confirmation/cancel/replay, no side effects, and direct paths pass. |
| Backend static/full | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q` | All backend checks pass with fake providers and no topology/schema drift. |
| Frontend regression/build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Existing confirmation/history/card behavior remains green and production build succeeds. |
| Plan structure | `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` | Contiguous Plans 1-14; Plans 1-13 hand off normally and only Plan 14 is terminal. |
| Docker health | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` then `Invoke-RestMethod http://127.0.0.1:8000/api/health` | Backend/frontend/Neo4j healthy; overall, SQLite, filesystem, and Neo4j are available. |
| Browser confirmation | Open `http://localhost:5173/`, paste the original one-line JD, inspect the card, choose **Không lưu**, then repeat with synthetic data and choose **Lưu JD**. | One card, one action lock, no pre-confirmation mutation, cancel has no Job/evaluation, save uses the existing result/dedupe path, no console errors or raw-JD logs. |
| Scope hygiene | `git diff --check; git status --short` plus changed-path review | Only Plan 13 handoff, Plan 14, prompt/graph owners, tests, and necessary evidence change; no secrets, runtime data, new service, endpoint, migration, or duplicate store. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Plan_13 | Provider-compatible `save_job`, strict runtime validator, current-message confirmation, release baseline | Existing provider schema and ToolNode boundaries remain authoritative. |
| Approved design | `docs/superpowers/specs/2026-07-20-intent-aware-pasted-jd-design.md` | User-intent matrix and confirmation-before-mutation are fixed. |
| Master Version 1.9 | Sections 11.2, 12, 13.4, 15.7, 20, 24, Phase 10 | No Master amendment is required; this is an in-scope reliability correction. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| User/runtime | Intent-aware passive JD confirmation with strict source ownership | Original one-line paste shows confirmation; cancel/save behavior and logs are verified. |
| Future maintenance | Prompt/graph tests and documented precedence | Regression suite proves analysis, opt-out, direct, malformed, and long-paste paths. |
| Release handoff | Updated code, test/build evidence, healthy Docker stack | Commit, full gates, Compose health, and browser smoke are recorded. |

## Completion Contract

Plan 14 is complete only when a large one-line or otherwise formatting-collapsed
JD that the LLM recognizes as a passive save intent reaches the existing
confirmation card without `INVALID_JOB_INPUT`; the graph sends only a canonical
`source='current_message'` call and no malformed provider fields reach
`ToolNode`. Analysis-only and opt-out messages remain unsaved, direct URL and
legacy exact-command paths remain compatible, and every save still requires the
user's confirmation. Focused and full backend/frontend gates, static checks,
Docker rebuild/health, plan validation, scope hygiene, and a browser smoke with
cancel plus confirmed synthetic save all pass. The normal three-service stack is
left healthy for manual testing, existing volumes are preserved, and no new
endpoint, migration, dependency, tool, Agent node, evaluation path, or raw-data
exposure is introduced.
