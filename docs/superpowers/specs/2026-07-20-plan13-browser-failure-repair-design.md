# Plan 13 Browser Failure Repair Design

**Date:** 2026-07-20  
**Status:** Approved by the user  
**Change type:** `bugfix`  
**Source evidence:** `.agent/plan13/plan13-20260719T152938Z/report/a2/batch05/05B/A2-a2.md`

## Problem statement

The disposable 05B browser run restored the normal Docker stack safely but found
nine product failures. A newly uploaded CV B was shadowed by active CV A, the CV
Manager exposed an action that the backend rejects for staged rows, one explicit
active-CV question bypassed `read_active_cv`, four clear passive JDs did not reach
the existing confirmation interrupt, and the sole-URL/direct-text paths reached
`save_job` with multiple mutually exclusive sources.

The common failure mode is that the live provider may return arguments that are
syntactically shaped like the provider schema but semantically conflict with the
deterministic current-turn facts. Runtime validation correctly rejects those
calls, so weakening `SaveJobInput` would hide the symptom and permit ambiguous
mutation. The repair instead canonicalizes only inputs whose intent and source
are already unambiguous at a deterministic boundary.

## Goals

1. Make the current turn's single staged attachment authoritative for CV upload
   proposal and keep reprocess ownership attached to `AgentRun.source_attachment_id`.
2. Make CV Manager actions match backend reprocess eligibility for every state.
3. Require durable active-CV evidence for the exact approved recent-role/company
   question before the model narrates an answer.
4. Route clear passive JDs, a sole URL, and the approved explicit-text command to
   exactly one valid `save_job` source without relying on provider argument choice.
5. Preserve the existing interrupt/card, save/cancel/replay, direct-save,
   observability, source-dialog, and error contracts.
6. Rebuild the normal Docker project without deleting its volumes and rerun the
   ordered 05B matrix through the visible frontend.

## Non-goals and invariants

- Do not add an endpoint, migration, dependency, model, worker, state store, or
  evaluation path.
- Keep one Agent decision node, one `ToolNode`, exactly seven production tools,
  and `TOOL_LOOP_LIMIT=6`.
- Keep `SaveJobInput` as the strict runtime authority. Do not silently strip
  invalid provider arguments at the tool boundary.
- Do not broaden the existing obvious-JD marker/opt-out classifier or turn this
  repair into a general natural-language intent parser.
- Do not hard-code fixture content, job facts, CV facts, database identifiers,
  or browser run identifiers in production.
- Preserve normal Docker volumes and all pre-existing user/workflow edits.

## Selected design

### 1. Deterministic canonical tool dispatch

Add a small pure dispatch helper in the existing Agent graph owner. It examines
only the initiating user message and current turn state, and returns either no
override or one canonical `AIMessage` tool call. The call still flows through
the existing `ToolNode`, durable execution wrapper, validation, and
interrupt/resume machinery.

The supported cases are deliberately narrow and ordered after opt-out
precedence:

1. **Passive obvious JD:** when the existing classifier says `obvious_jd=true`
   and no clear opt-out exists, emit exactly
   `save_job(source="current_message")`. Do not include URL, text, or preview.
2. **Sole URL:** when the trimmed initiating message is exactly one HTTP(S) URL,
   emit exactly `save_job(url=the_exact_trimmed_user_url)`.
3. **Approved explicit text:** accept only the exact command shape used by the
   acceptance plan: a named `save_job` request containing one
   `text="..."` argument followed by the exact constraints
   `Do not use source=current_message and do not call match_jobs.` Emit exactly
   `save_job(text=the_characters_inside_the_quoted_value)`. The parser does not
   interpret escapes or other prose forms. A `ponytail:` comment records this
   intentional limitation and the upgrade path to a real command grammar if
   more forms are approved.

All other named-tool requests, ambiguous prose, greetings, and malformed command
syntax stay on the existing model-driven/bounded-refusal path. Canonical calls
use fresh tool-call IDs and the registered `save_job` name. They are returned
from the existing decision node, so graph topology and the six-pass limit remain
unchanged.

### 2. Current-turn CV attachment ownership

In `propose_profile_from_cv`, normalize `state.attachment_ids` first. When it
contains exactly one staged attachment, that attachment is authoritative for the
upload-triggered proposal. A model-provided attachment UUID for active CV A must
not override staged CV B.

The existing reprocess flow remains distinct: a reprocess turn owns the
attachment recorded by `AgentRun.source_attachment_id`, and that durable owner
continues to win for the reprocess run. With no single turn attachment and no
run-owned reprocess attachment, keep the existing resolver and ambiguity rules.
This fixes the source boundary without introducing a second attachment lookup
service.

### 3. CV Manager state/action matrix

Render reprocess actions only for backend-supported states:

| CV state | Reprocess action | Delete |
|---|---|---|
| `active` | **Re-extract** | hidden |
| `archived` | **Make active** | shown |
| `staged` | hidden | shown |
| `failed` | hidden | shown |

Open/download keeps its current `file_available` behavior. The frontend does not
invent a staged transition; the normal upload approval flow owns staged CVs.

### 4. Active-CV evidence dispatch

For the exact approved question
`What is the most recent role and company in my CV?`, and only when
`read_active_cv` is registered, emit a canonical
`read_active_cv(mode="section", section_id=the_first_experience_section_id_in_state)`
call before narration. Reuse the existing auto-tool-call pattern used by
`_auto_commit_after_draft_tool`: the first decision produces the tool call, the
next decision sees the durable tool result and allows the model to narrate from
that result.

Resolve the experience section identifier as the first `active_cv_outline`
entry whose `kind` is `experience`; do not add a second CV reader or fabricate a citation. The
normal `read_active_cv` result continues to own the `Nguồn` citation records and
the existing dialog/PDF/no-fetch behavior.

### 5. Error handling

- A canonical call is created only after all narrow predicates pass. Otherwise
  existing model repair/refusal behavior is unchanged.
- `SaveJobInput` still rejects multiple/empty/unknown sources, and a direct tool
  call outside the canonical syntax receives the existing stable failure.
- Zero or multiple staged attachments do not guess an upload owner; existing
  resolution/ambiguity handling remains authoritative.
- `staged` and `failed` rows expose no reprocess control, preventing the known
  deterministic 409 from the UI while leaving backend validation intact.
- If `read_active_cv` fails, its existing stable tool error is narrated; no
  answer or citation is fabricated.

## Test strategy

Follow RED-GREEN-REFACTOR for each behavior:

1. Agent unit tests prove passive English/Vietnamese/long JDs yield one
   source-only call even when the provider would return mixed fields; opt-out and
   ambiguous prose remain non-canonical.
2. Agent unit tests prove a sole URL preserves the exact URL, the approved
   explicit command preserves the exact text, and near-miss commands remain
   model-driven.
3. Integration coverage proves active A plus staged B proposes B and preserves
   `AgentRun.source_attachment_id` for reprocess.
4. Agent tests prove the approved CV question calls `read_active_cv` exactly
   once before narration and retains one decision node, one `ToolNode`, seven
   tools, and the six-pass limit.
5. Frontend component tests prove the four-state action matrix and that staged/
   failed rows cannot invoke reprocess.
6. Run focused and full backend/frontend tests, Ruff, mypy, ESLint, typecheck,
   production build, Docker rebuild/health, and the ordered visible-browser 05B
   flow. Record each browser failure with request/run/tool/log evidence and root
   cause; append rather than overwrite earlier failure history.

## Acceptance criteria

- Uploading CV B while A is active produces B's approval flow; approving B
  archives A, and later reprocessing A retains A as the run owner.
- CV Manager exposes only the state-valid actions in the table above and no
  staged/failed reprocess request can be initiated from the UI.
- The approved active-CV question has one successful `read_active_cv` execution,
  one visible `Nguồn` citation, and the existing named dialog/PDF/no-fetch/close/
  Escape/focus-return checks pass.
- English, Vietnamese, exact-repeat, and long passive JDs each reach one bounded
  confirmation card; refresh/save/dedupe/cancel behavior matches Plan 13.
- The sole URL and approved explicit-text command dispatch exactly one valid
  source and never fail with the observed multiple-source `INVALID_JOB_INPUT`.
- Opt-out and ambiguous prose remain non-mutating.
- All quality gates pass, the rebuilt normal Docker project is healthy, normal
  volumes are preserved, and the browser run finishes with no pending approval.
