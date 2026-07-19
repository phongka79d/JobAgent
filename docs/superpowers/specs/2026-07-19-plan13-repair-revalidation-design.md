# Plan 13 Repair And Revalidation Design

**Date:** 2026-07-19  
**Status:** Draft for user review after the approved Plan 13 direction  
**Change type:** `bugfix`  
**Master impact:** `none`

## Context and confirmed root causes

The current product HEAD passes the focused unit tests added for Plan 12, but a
fresh desktop run still exposes one functional regression, one accessibility
defect, and several evidence gaps. The investigation followed the durable
run/tool records, the provider-visible schema, and the browser/API boundary; it
did not infer a failure from the UI alone.

### Passive pasted-JD confirmation

Three fresh recognizable English/Vietnamese inputs, including the 4,771-character
MISA JD, were classified by the deterministic boundary as
`obvious_jd=true` with no opt-out. Each run ended with the fixed
`No confirmation was created and the JD was not saved.` response and
`tool_count=0`:

```text
4971481e-0e7b-42ca-8d7b-184d314be2e9
d1fab78d-a4ff-4a9d-ad06-75d5cd229c8a
5a12595d-7af4-4b64-a03b-433c08d87293
```

The local graph predicate correctly rejects a mixed call such as
`{text: <non-empty>, source: "current_message"}` and allows one repair. The
failure is that the LLM-visible `save_job` schema is generated from the
function annotations in `backend/app/tools/jobs.py:368-388`. Its inspected
provider shape has no source union (`required=[]`, nullable `url/text/source`,
and a generic preview object), so the provider can emit the same invalid mixed
call again on the repair. `backend/app/agent/graph.py:833` then correctly refuses
to dispatch it, but the user receives a refusal instead of the confirmation
interrupt. The ingestion owner was not reached; this is a provider-boundary and
repair-contract defect, not a persistence or graph-sync defect.

### Active-CV source dialog

The dialog displays the exact evidence, retains focus, closes correctly, opens
the retained PDF, and performs no evidence fetch. Its outer Astryx `Dialog` in
`frontend/src/features/chat/components/ActiveCvSourceDialog.tsx:209` has no
explicit `aria-label` or `aria-labelledby`. `DialogHeader` renders a heading but
does not expose an ID, so the browser accessibility tree reports an unnamed
`dialog`; `getByRole('dialog', {name: 'Nguồn từ CV'})` finds zero elements.

### Evidence and coverage gaps

- `docs/acceptance/full_functional_test_matrix.md` has no P12 identifiers or
  rows for `current_message`, `job_save_confirmation`, or `Nguồn`, and it has no
  status/date/commit/evidence columns.
- Plan 1's required negative diagnostic paths (timeout, 429, malformed response,
  missing model, dimension mismatch, and ordering mismatch) are not each forced
  by deterministic tests; the PDF diagnostic has no negative threshold test.
- Archived-CV activation/reprocess/delete browser paths for Plans 9/11 were not
  rerun in the latest session because only one active CV remained.
- Plan 12's live pre-action extraction/embedding/evaluation/Neo4j counters were
  inferred from the absence of mutations rather than recorded directly.

The jsdom `window.scrollTo` warning, duplicate synthetic React key, Vite bundle
size warning, `aiosqlite` datetime deprecation, and bare-host `python`/`pypdf`
environment mismatch are documented non-blocking warnings. They are not part of
this repair unless a later approved change expands scope.

## Goals

1. Make a clear passive JD reliably reach the existing confirmation card while
   preserving the one-Agent/one-decision/one-ToolNode topology and the six-pass
   bound.
2. Keep the strict runtime source contract and zero pre-confirmation side
   effects; malformed provider calls must never be silently ingested.
3. Give the active-CV source dialog the accessible name `Nguồn từ CV` without
   changing its evidence order, focus behavior, or network behavior.
4. Close the identified automated/manual evidence gaps with deterministic,
   disposable, current-HEAD records.
5. Preserve all Plan 11 repairs and existing direct URL/text, saved-JD,
   evaluation, CV-manager, and matching behavior.

## Non-goals and boundaries

- No new public endpoint, database/Alembic migration, dependency, tool name,
  Agent/node/ToolNode, queue, worker, evaluation path, or public schema.
- No change to the fixed English/Vietnamese marker or opt-out lists and no
  general intent classifier. Ambiguous text still receives normal conversation
  or a truthful refusal.
- No silent text/url stripping in the runtime validator. A provider call that
  remains invalid after the bounded repair is refused without dispatch.
- No mobile/security/penetration work and no cleanup of the listed non-blocking
  warnings.
- Plan 11 F-01 through F-05 are historical inputs, not reopened work; their
  accepted coordinators and contracts remain the baseline.
- Real CV/JD bodies, provider transcripts, secrets, databases, and browser
  profiles remain outside Git.

## Options considered

### A — Strict provider boundary plus bounded repair (selected)

Expose a real mutually-exclusive source union to the provider, keep
`SaveJobInput` as the server-side authority, validate the complete AI tool call
before `ToolNode`, and use one forced/explicit repair decision for an obvious
passive JD. If the repaired call is still invalid, return the existing fixed
truthful refusal. This addresses the actual provider→ToolNode boundary without
adding a route or state store. It also makes the malformed-call path observable
and testable before any mutation.

### B — Add a separate confirmation endpoint/agent flow

This would isolate the card transport but would duplicate interrupt/resume and
introduce a public contract/state owner. It conflicts with Master 1.9 and is
rejected.

### C — Add more free-form retries or keyword heuristics

This may improve one provider transcript but does not constrain the schema and
can create repeated model calls or false saves. It is rejected in favor of one
bounded repair and deterministic validation.

## Selected design

### 1. Provider-visible `save_job` source union

Create one focused LLM-facing argument schema/adapter in the existing Job tool
owner. The provider schema is an object with `additionalProperties=false` and
three mutually-exclusive branches:

```text
URL branch:             required url; no text/source/preview
explicit-text branch:   required text; no url/source/preview
current-message branch: required source='current_message'; optional bounded preview;
                        no url/text
```

The schema must omit injected `tool_call_id` and `state` fields from the
provider-facing contract. The existing `SaveJobInput` remains the runtime
validator and the only ingestion input model; the adapter translates the
validated branch to that model without changing public URL/text semantics.
`preview` remains presentation-only and never becomes a canonical Job fact.

The provider-schema test inspects the actual `convert_to_openai_tool`/bound
tool payload, not only a Pydantic model. It asserts branch `required` keys,
`source` const, forbidden extras, preview bounds, and absence of injected state.
The compatibility gate uses the ordinary function-calling mode already proven
by Plan 1; it must fail loudly if the provider rejects the branch schema rather
than silently reverting to the permissive nullable shape.

### 2. Bounded passive-JD repair and dispatch gate

Keep `message_is_obvious_jd`, `message_has_clear_opt_out`, and the exact
initiating-message resolver in `job_save_confirmation.py`. In the existing
decision node:

1. Apply opt-out precedence.
2. Preserve Plan 11's exact-name `save_job` path.
3. For an obvious non-URL passive JD, validate the first AI response against
   the strict sole-current-message predicate.
4. If invalid, make exactly one repair invocation with an explicit
   source-only example and a provider tool-choice constraint for `save_job`.
5. Validate the repaired response again. Only a single valid
   `save_job(source='current_message', preview?)` call reaches `ToolNode`.
6. If it is still invalid, emit the existing fixed no-confirmation text and no
   tool execution.

Record only sanitized repair diagnostics (reason category and call shape, never
raw JD text or provider payloads). This keeps one model repair, one decision
node, and the existing six-pass counter. A fake-provider regression must include
both repeated mixed-source calls (refusal/no side effect) and a valid strict
repair (confirmation appears), so the test cannot pass by weakening validation.

### 3. Confirmation and side-effect proof

Reuse the current `save_job` interrupt/resume implementation unchanged except
for the provider schema/dispatch seam. Acceptance must prove:

- Before **Lưu JD**, the same tool execution is `running`, the pending card is
  bounded/redacted, and Job rows, extraction calls, embedding calls, evaluation
  calls, and Neo4j writes are all zero.
- **Lưu JD** reloads the exact durable initiating message once and preserves
  `created|returned|retried` plus the existing SavedJobCard.
- **Không lưu** returns `committed=false`, `outcome=cancelled`, no Job/card/
  invalidation, and zero ingestion/provider/graph side effects.
- Repeated resume and terminal replay perform no second side effect; direct
  URL/text and explicit **Lưu JD & đánh giá lại** remain unchanged.

Counters are gathered with fake seams in automated tests and sanitized
provider/SQLite/Neo4j observations in the disposable browser run; no product
observability endpoint is added.

### 4. Dialog accessible name

Pass `aria-label={ACTIVE_CV_SOURCE_DIALOG_TITLE}` to the existing outer Astryx
`Dialog`. `Dialog` inherits `aria-*` from its documented `BaseProps`, so this is
the smallest explicit naming contract and does not require changing the pinned
`DialogHeader`. Add a component assertion for
`getByRole('dialog', {name: 'Nguồn từ CV'})` and retain the existing
close/Escape/focus-return, original-PDF, record-order, partial-notice, and
zero-fetch assertions.

### 5. Evidence and release ledger

Add `docs/acceptance/plan13_acceptance_ledger.md` as the dated execution record.
It contains one row per new Plan 13 check and a cross-reference for every P12
requirement, with these mandatory columns:

```text
ID | requirement/source | procedure/command | status | date (UTC) |
HEAD/Compose project | failure/log evidence | resolution/notes
```

Add a short Plan 12 supplement section to
`full_functional_test_matrix.md` linking P12-RSP/CV/JD/REG IDs to this ledger;
do not rewrite historical rows or turn the failure-only report into a pass
diary. The ledger records the three passive-JD run IDs, dialog role/name result,
pre-action counters, browser network requests, and all warning classifications.

### 6. Deterministic diagnostic and archived-CV evidence

- Add fake-transport tests for each required Plan 1 provider failure mapping and
  the PDF `<4/5`/image-only negative gates. Assertions require non-zero exit,
  stable capability code, final `SHOPAIKEY_COMPATIBILITY=FAIL` or
  `PYPDF_COMPATIBILITY=FAIL`, and redaction.
- Provide a disposable two-CV fixture/procedure for the browser run: upload and
  approve CV A, upload/approve CV B, reprocess/activate archived A, then delete
  archived B. Record request/event order, active badge, retained PDF, graph/run
  state, and deletion result in the ledger. Tear down only the named disposable
  Compose project.

## Error handling and recovery

- Unsupported provider branch schema blocks the release gate; no permissive
  fallback, model switch, or hidden retry is allowed.
- A malformed first/repair call never reaches `ToolNode`; the user receives a
  fixed truthful no-confirmation result and can submit a new turn.
- Source lookup, validation, provider, ingestion, or graph failures preserve
  existing stable codes and durable truth. No new error envelope is introduced.
- Dialog naming failure is a frontend test failure; evidence content/network
  behavior remains a separate regression gate.
- If a disposable browser run is interrupted, retain its sanitized partial row
  as `INCOMPLETE` in the ledger and rerun with a new project; never mutate normal
  user volumes or mark the check PASS from stale output.

## Acceptance gates

The design is accepted for implementation only when all of the following are
proved on current HEAD after the repair:

1. Three new fresh obvious JDs each show one confirmation card and zero
   pre-action mutation; save/cancel/replay behavior is exact.
2. The provider-visible schema has strict source branches and the malformed-call
   tests prove no invalid dispatch.
3. `getByRole('dialog', {name: 'Nguồn từ CV'})` succeeds while all existing
   evidence/dialog behavior remains green.
4. Plan 1 negative diagnostics, archived-CV browser paths, and P12 counters have
   dated ledger evidence.
5. Backend/frontend focused and full gates, Compose health, plan validator, and
   scope hygiene pass. Non-blocking warnings are listed separately.

## Ownership and file boundaries

```text
backend/app/tools/jobs.py                 provider schema + dispatch adapter
backend/app/agent/graph.py                one bounded repair/validation gate
backend/app/services/job_save_confirmation.py
                                          pure predicates/projection/source lookup
backend/app/schemas/jobs.py               runtime source/preview/cancel contracts
frontend/src/features/chat/components/ActiveCvSourceDialog.tsx
                                          accessible dialog name/presentation
frontend/src/test/active-cv-source.test.tsx
frontend/src/test/job-save-confirmation.test.tsx
backend/tests/unit/test_agent_graph.py
backend/tests/unit/test_shopaikey_chat.py
backend/tests/unit/test_job_save_confirmation.py
backend/tests/integration/test_job_tools.py
backend/tests/integration/test_chat_api.py
infrastructure/scripts/diagnose_shopaikey.py
infrastructure/scripts/verify_pdf_extraction.py
backend/tests/unit/test_*diagnostic*.py
docs/acceptance/plan13_acceptance_ledger.md
docs/acceptance/full_functional_test_matrix.md
docs/acceptance/cv_manager_checklist.md
```

No task contract or product implementation is created by this design. The
incremental plan will convert these boundaries into bite-sized test-first tasks
after the written spec is reviewed.
