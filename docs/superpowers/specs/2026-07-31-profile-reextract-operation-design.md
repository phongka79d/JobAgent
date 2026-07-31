# Durable Profile Re-extraction Ownership and Recovery Design

**Date:** 2026-07-31
**Status:** Architecture direction approved; written specification awaiting user review
**Scope:** Profile CV re-extraction, profile-draft ownership, concurrent CV upload,
recovery UX, and the local Docker migration rollout

## 1. Evidence and problem statement

The current direct re-extraction workflow fixed the earlier chat side effects,
but it still treats a request-scoped SSE generator as the operation owner. The
operation ID exists only in emitted events. No durable row claims the profile
before PDF/provider work starts, and the frontend does not include that work in
the App-owned upload lock.

The 2026-07-31 reproduction used the running `jobagentlatest` Compose project,
the public APIs, source tracing, and backend logs. The in-app Browser runtime was
not available during this audit, so API behavior and persisted state were used
instead of claiming browser evidence. The following failures are confirmed:

1. Starting re-extraction and then uploading a new CV can overlap. Depending on
   ordering, upload either succeeds while extraction is still executing or is
   rejected only after a draft appears.
2. `ProfileReextractionCoordinator` creates an in-memory operation ID after its
   preflight. Duplicate requests therefore have no database-enforced claim
   before provider work.
3. `profiles.get_current_draft()` selects the newest `profile_drafts` row across
   the whole database. Reads, updates, approval, discard, upload, Agent context,
   and deletion can consequently observe a draft owned by another profile.
4. Draft publication and approval check the draft revision, but do not compare
   the captured `profiles.updated_at` and `workspace_state.updated_at`. Active
   profile or approved profile truth can change while extraction is in flight.
5. Cancelling the re-extraction SSE request has produced `CancelledError`,
   `sqlite3.OperationalError: no active connection`, and SQLAlchemy warnings
   about connections not returned to the pool.
6. Closing CV Manager aborts the request, increments the local generation, and
   leaves re-extraction state unsuitable for truthful reopen/reload recovery.
7. Duplicate re-extract clicks are suppressed only by request-local frontend
   state. Another tab or process can repeat the expensive work.
8. CV Manager advertises `reextract` for an inactive archived CV although the
   endpoint accepts only the active ready profile and returns
   `PROFILE_NOT_READY`.

The observed upload `409 PROFILE_REVIEW_PENDING` is valid once a review draft
exists, but it is too late to coordinate the preceding work. The root issue is
missing durable operation ownership, compounded by global draft lookup and
request-local UI state.

## 2. Goals

- Claim one profile re-extraction durably before the first SSE event and before
  PDF/provider work.
- Make every profile draft read, write, approval, and delete explicitly scoped
  to its owning profile.
- Serialize re-extraction publication against profile changes, active-profile
  changes, and concurrent upload by compare-and-swap checks.
- Preserve approved profile/CV truth and every pre-existing valid draft on all
  failures.
- Recover running, review-ready, interrupted, failed, and stale operations after
  drawer close, disconnect, reload, or backend restart.
- Disable both Overview/sidebar and chat-composer CV uploads while the current
  tab owns active re-extraction, while retaining backend enforcement for other
  tabs and direct API callers.
- Keep review, approve, discard, retry, loading, success, and error states
  explicit at the point where the user attempted the action.
- Rebuild the current local Docker project with a verified application-data
  backup, rehearsed migration, and tested rollback path.

## 3. Non-goals

- No worker, queue, scheduler, background extraction service, or fourth Compose
  service.
- No second extraction implementation and no new provider/model.
- No automatic approval, silent draft discard, inferred ownership backfill, or
  automatic retry after provider failure.
- No changes to approved Job, evaluation, matching, Tailored CV, LaTeX, or Neo4j
  business contracts. Neo4j remains a derived projection refreshed only after
  profile approval.
- No historical operation dashboard, notification center, or cross-device
  synchronization.
- No replacement of the public Agent-facing symbolic `draft_id='current'`.
  It remains a logical name resolved under the exact current profile, not a
  database-wide singleton.

## 4. Alternatives considered

### 4.1 Selected: operation table, profile-scoped drafts, and CAS

Add a durable `profile_reextract_operations` owner, tie re-extraction drafts to
that owner, and verify captured profile/workspace revisions at publication and
approval. This addresses process, tab, request, and database races at their
authoritative boundaries.

### 4.2 Rejected: lock fields on `workspace_state`

Adding operation fields to the singleton would couple profile extraction state
to active selection and make recovery/deletion semantics harder to isolate. It
would also lack a stable operation identity for review and cancellation.

### 4.3 Rejected: frontend or in-memory mutex only

A React flag or Python lock cannot coordinate multiple tabs, multiple backend
workers, reloads, restarts, or direct API calls. It also cannot own a review
after the SSE connection disappears.

## 5. Locked invariants

1. A `profile_drafts` row has exactly one non-null `target_profile_id`; at most
   one draft exists for a profile.
2. `source_attachment_id` stays nullable. Agent/profile-only corrections are
   valid drafts and must not be forced to impersonate CV extraction.
3. A re-extraction draft has one non-null, unique
   `reextract_operation_id`. An ordinary initial-upload or Agent-only draft has
   a null operation ID.
4. A running operation is persisted before the first SSE event. No provider,
   PDF parsing, or document publication runs before the claim commits.
5. No SQLAlchemy session or transaction remains open across PDF parsing,
   provider work, an SSE yield, filesystem I/O, or Neo4j I/O.
6. A re-extraction can publish a review only while its operation is still
   `running` and both captured profile/workspace revisions still match.
7. Approval requires the exact profile ID, operation ID, and draft revision.
   Repeating, crossing, or replaying any identity is a conflict, never an
   overwrite.
8. Approved profile/CV truth changes only through the existing atomic profile
   approval transaction. Re-extraction itself changes only operation, draft,
   document-draft, and chunk staging data.
9. Duplicate content is prevented by the existing structured full-document
   merge and canonical deduplication path. Re-extraction replaces a proposal;
   it never appends extracted arrays or prose to an existing payload.
10. A failure never deletes or rewrites a valid draft owned by another profile
    or operation.
11. Re-extraction claim and final upload persistence use the same short SQLite
    `BEGIN IMMEDIATE` lifecycle transaction pattern. The pre-byte upload check
    is an optimization; the in-transaction check is the concurrency boundary.

## 6. Data model and migration 0008

### 6.1 `profile_reextract_operations`

Migration `0008_profile_reextract_ownership` adds this table:

| Column | Type | Null | Contract |
| --- | --- | --- | --- |
| `id` | `TEXT` | No | Server UUID primary key; public operation identity |
| `profile_id` | `TEXT` | No | FK to `profiles.id`, `ON DELETE CASCADE` |
| `source_attachment_id` | `TEXT` | No | Retained CV captured at claim; FK to `attachments.id`, `ON DELETE RESTRICT` |
| `state` | `TEXT` | No | `running`, `review_ready`, `interrupted`, `failed`, or `stale` |
| `base_profile_updated_at` | timezone datetime | No | Captured ready-profile revision |
| `base_workspace_updated_at` | timezone datetime | No | Captured workspace selection revision |
| `error_code` | `TEXT` | Yes | Safe stable code for `interrupted`, `failed`, or `stale`; no provider payload |
| `created_at` | timezone datetime | No | Claim time |
| `updated_at` | timezone datetime | No | Last durable transition |

Constraints and indexes:

- a check constraint limits `state` to the five values above;
- `error_code` is null for `running`/`review_ready` and non-null for terminal
  recovery states;
- a partial unique index on `profile_id` for
  `state IN ('running', 'review_ready')` prevents two actionable operations for
  one profile; and
- an index on `(profile_id, updated_at, id)` supports deterministic recovery.

Operation rows are recovery metadata, not user content. Successful approval or
discard removes the matching draft first and then its operation in the same
SQLite transaction. Failed/interrupted/stale rows remain visible until the user
retries. A new claim deletes prior terminal rows for that profile only after
proving none owns a draft, then inserts the replacement operation in the same
transaction. This prevents an older failure from reappearing after the newer
operation is approved or discarded.

### 6.2 `profile_drafts`

SQLite requires a table rebuild to make ownership structural. The rebuilt table
keeps all existing columns and rows, with these changes:

- `target_profile_id` becomes non-null;
- `UNIQUE(target_profile_id)` enforces one pending draft per profile;
- nullable `reextract_operation_id` is added with a unique constraint and FK to
  `profile_reextract_operations.id` using `ON DELETE RESTRICT`; and
- a check requires `source_attachment_id IS NOT NULL` whenever
  `reextract_operation_id IS NOT NULL`.

`source_attachment_id` remains nullable and retains its existing uniqueness and
attachment ownership behavior.

Profile deletion remains blocked while an operation is actionable or owns a
draft. When deletion is otherwise allowed, its transaction removes terminal
operation metadata with no draft before deleting the profile/attachment rows,
so the new restrictive source-attachment FK cannot create a cleanup dead end.

### 6.3 Migration safety

Before rebuilding `profile_drafts`, migration 0008 checks for:

- null or orphaned `target_profile_id` values;
- more than one row for a target profile;
- orphaned source attachments; and
- pre-existing foreign-key violations.

If any check fails, the migration aborts before changing either table and emits
safe recovery guidance. It does not infer a profile from active state, attachment
order, timestamps, or draft JSON; it does not delete a row. Existing valid rows
copy byte-for-byte with `reextract_operation_id=NULL`.

Before and after the rebuild, migration tests snapshot `sqlite_master.sql` plus
`PRAGMA table_info`, `index_list`, `index_info`, `foreign_key_list`, and the
trigger list for `profile_drafts`. They verify every pre-existing column,
default, FK action, unique index, named constraint represented in table SQL, and
trigger remains unless this design explicitly changes it. They also run
`PRAGMA foreign_key_check`, compare row counts, and compare canonical JSON and
all scalar values.

Downgrade is supported only when the operation table is empty and no draft
references an operation. Tests separately prove: (a) downgrade refusal on a
populated operation and operation-linked draft leaves schema/data unchanged;
and (b) empty-operation downgrade followed by re-upgrade succeeds and preserves
ordinary drafts. Production rollback restores the verified pre-migration volume
backup instead of guessing a reverse data transformation.

## 7. Repository and ownership contracts

The global draft helpers are removed. All callers must use explicit methods:

```text
get_draft_for_profile(session, profile_id)
get_draft_for_operation(session, profile_id, operation_id)
upsert_draft_for_profile(session, profile_id, ..., reextract_operation_id=None)
delete_draft_for_profile(session, profile_id, expected_revision=None,
                         expected_operation_id=None)
```

The upsert must preserve an existing `reextract_operation_id` when an Agent
adds user-requested corrections to that same profile draft. It may set an
operation ID only during atomic re-extraction publication and may never move a
draft between profiles or operations.

Every existing caller is migrated, including Agent context/tools, initial CV
extraction, profile update, approval, profile projection, upload response,
attachment resolution, activity gates, CV Manager deletion, profile deletion,
and direct re-extraction. No compatibility helper may select the newest global
row.

The public Agent tool continues to accept `draft_id='current'`. Its graph state
already contains the expected profile ID; repository lookup resolves the draft
for that profile and rejects an ownership mismatch.

## 8. Operation state machine

| From | To | Trigger | Durable effect |
| --- | --- | --- | --- |
| none | `running` | Claim succeeds | Capture profile, attachment, and workspace revisions |
| `running` | `review_ready` | CAS publication succeeds | Write chunks/document draft/profile draft and operation transition atomically |
| `running` | `interrupted` | Disconnect, generator close, or startup recovery | Fresh shielded transaction; no draft publication |
| `running` | `failed` | PDF/provider/validation/storage failure | Persist safe code; preserve approved truth and prior drafts |
| `running` | `stale` | Profile/workspace/draft CAS conflict | Persist conflict; never publish over newer truth |
| `review_ready` | `stale` | Status/review reconciliation or approval CAS conflict | Retain review for explicit discard; disable approval |
| `review_ready` | removed | Approval succeeds | Consume operation and draft in the approval transaction |
| `review_ready` | removed | User discards | Delete matching document/profile draft and operation atomically |

`running` blocks another re-extraction and lifecycle mutations such as CV
upload, profile activation, and profile deletion. A `review_ready` draft keeps
the existing review gate. `interrupted` and `failed` do not block upload or a
new retry. A `stale` operation without a draft does not block; a stale operation
with its preserved review blocks only until the user explicitly discards it.

On retry, the service creates a new operation after proving there is no
actionable operation or draft. It removes only prior terminal operation metadata
for that profile with no linked draft. An operation ID that was superseded or
consumed cannot be selected as the current status or review.

## 9. Backend workflow

### 9.1 Claim

`ProfileReextractionCoordinator` opens one short, shielded SQLite
`BEGIN IMMEDIATE` transaction and:

1. validates the profile is the active ready profile;
2. verifies no incomplete profile setup, pending profile draft, active
   re-extraction, chat/tailoring activity forbidden by the existing gate, or
   conflicting lifecycle mutation exists;
3. removes only superseded terminal operation rows for this profile that have
   no linked draft;
4. reloads the profile attachment ownership;
5. captures `profiles.updated_at` and `workspace_state.updated_at`; and
6. inserts the `running` operation.

The upload service uses the same immediate-write transaction for its final
gate, attachment/profile/conversation inserts, and active-workspace update.
Both sides acquire the SQLite writer reservation before reading lifecycle
gates. The upload check immediately before its first application insert must
query actionable re-extraction operations as well as incomplete profiles,
workspace activity, and pending drafts. The earlier check before reading upload
bytes remains, but never substitutes for this persistence-boundary check.

SQLite writer serialization plus the partial unique index makes concurrent
claims and upload persistence deterministic. An integrity or busy-snapshot
conflict is rolled back and mapped to a stable lifecycle 409, never a 500. An
integrity conflict between duplicate claims maps to
`PROFILE_REEXTRACT_IN_PROGRESS`, not a 500.

The retained-file existence check follows the claim without an open database
session. A missing file transitions that exact operation to `failed`.

### 9.2 Stage without publication

The current document-first extraction path is split at its existing natural
boundary:

- a shared staging function loads/validates the retained PDF and returns the
  bounded chunks, CV document data, projected profile draft, extraction
  metadata, and source hash in memory; and
- a publication function owns the short atomic database write.

Initial upload and direct re-extraction call the same staging logic. This is a
refactor of ownership, not a second parser or extraction path.

### 9.3 CAS publication

The re-extraction publication transaction checks all of the following before a
write:

- operation ID/profile/source attachment match and state is `running`;
- the ready profile still owns the captured attachment and its `updated_at`
  equals `base_profile_updated_at`;
- workspace active profile is still the operation profile and
  `workspace_state.updated_at` equals `base_workspace_updated_at`;
- no profile-scoped draft already exists; and
- no incomplete upload profile appeared while extraction was staged.

Only then does it replace the attachment's canonical chunks, upsert its
document draft, insert the operation-linked profile draft, and transition the
operation to `review_ready` in one transaction. Any failed predicate rolls the
whole transaction back and transitions the operation to `stale` in a separate
short transaction.

This closes all interleavings, including an upload that passed its pre-byte
gate before re-extraction claimed:

- if re-extraction claims first, upload's pre-persistence gate sees `running`
  and removes its temporary/finalized file without creating application rows;
- if upload commits first, workspace/profile publication CAS fails and the
  re-extraction cannot overwrite or publish against the new workspace; and
- neither transaction can read a clear gate and then commit behind the other,
  because both gate-and-write units hold the immediate SQLite writer lock.

### 9.4 Review, cumulative edits, and deduplication

Review lookup requires both profile ID and operation ID. The response compares
the approved profile with the exact operation-linked draft. Agent edits for the
same profile may continue to merge into that draft, preserving the operation
ID and advancing its draft revision while the operation is `review_ready`.
Agent updates against an operation-linked `stale` draft return
`PROFILE_REEXTRACT_STALE` without changing the draft.

`ProfileReextractReview` includes `operation_id` and
`operation_state='review_ready'|'stale'` in addition to the draft revision. For
`review_ready`, the response always has `can_approve=true` and
`can_discard=true`. For `stale`, it always has `can_approve=false` and
`can_discard=true`; the current returned draft revision is the required discard
revision. A client-supplied flag cannot change these values.

Before operation status or review is projected, one short transaction reconciles
its captured profile/workspace CAS. If a `review_ready` operation no longer
matches, that transaction persists `stale` before building the response. Thus
the API never returns the contradictory combination
`operation_state='review_ready'` with `can_approve=false`. Reconciliation is
idempotent, changes only operation metadata, and approval still repeats the CAS.

All cumulative updates continue through `ProfileDraftPayload`, the structured
field/skill merge, and `_dedupe_profile_draft_payload`. Duplicate normalized
skills, repeated structured entries, repeated list values, and repeated prose
units are removed before publication. Re-extraction never concatenates one
extraction result with another.

### 9.5 Approval and discard

Direct approval carries `{operation_id, revision}`. The common profile approval
service reloads the exact profile draft and operation, rechecks operation state,
draft revision, captured profile revision, and captured workspace revision, and
then runs the existing SQLite-first approval transaction. This check applies
even if an operation-linked draft is approved through the Agent tool, preventing
an orphaned operation or a weaker alternate path.

Successful SQLite approval removes the draft and operation in the same
transaction. Neo4j synchronization remains post-commit; failure reports the
existing committed-success warning and rebuild guidance.

Discard carries the same operation ID and revision. It deletes only the exact
profile draft, matching CV document draft, and operation. Approved profile/CV,
conversations, Jobs, evaluations, retained PDF, and Neo4j truth are unchanged.

## 10. Cancellation and restart recovery

- Claim, publication, failure transition, and cancellation finalization each
  use their own short cancellation-shielded database scope.
- The coordinator catches `asyncio.CancelledError` and `GeneratorExit`, then
  enters `anyio.CancelScope(shield=True)`. Inside that scope it opens a fresh
  `session_scope`, compare-and-swap transitions only its still-`running`
  operation to `interrupted`, commits, and awaits the session context manager's
  complete close. Only after leaving the shield does it re-raise the original
  cancellation/generator close.
- Cancellation finalization errors are safely logged without replacing the
  original cancellation. The fresh session is still opened and closed inside
  the shield; if the state CAS itself cannot commit, startup recovery remains
  responsible for the `running` row.
- No cancelled request reuses a session that was active when cancellation
  arrived. This is the required fix for the observed aiosqlite connection
  cleanup errors.
- Backend startup deterministically changes leftover `running` rows to
  `interrupted`, because no request-scoped extraction survives a process
  restart. It does not touch `review_ready` drafts.
- Closing CV Manager only hides the drawer. It does not abort the re-extraction
  controller or clear operation state. Reopening refreshes authoritative status.
- A browser reload/disconnect may interrupt the request; on return, the UI loads
  the durable status and offers Retry. If publication committed first, it loads
  Review changes instead.

No disconnect is reported as success, and no in-memory flag is used as recovery
truth.

The implementation must use a small coordinator-owned finalization helper with
the `CancelScope` outside the full session context. `asyncio.shield()` around
only the UPDATE, or shielding only `iterator.aclose()`, is insufficient because
session rollback/close could still execute in the cancelled scope.

The startup transition relies on the locked local runtime: one backend service
running one Uvicorn process. A future multi-process or multi-host deployment
would require a separately designed lease/heartbeat contract and is outside
this increment.

## 11. Public API contract

The existing route remains the creation/stream boundary, with one read endpoint
added for recovery:

```text
POST   /api/profiles/{profile_id}/reextract
GET    /api/profiles/{profile_id}/reextract-operation
GET    /api/profiles/{profile_id}/reextract-draft?operation_id={operation_id}
POST   /api/profiles/{profile_id}/reextract-draft/approve
DELETE /api/profiles/{profile_id}/reextract-draft
```

`POST .../reextract` persists the operation before returning its first existing
`reextract_progress` event. Every event retains the same operation ID. A second
claim returns HTTP 409 with `PROFILE_REEXTRACT_IN_PROGRESS`; a published review
returns `PROFILE_REVIEW_PENDING`.

`GET .../reextract-operation` returns either `operation: null` or a strict safe
projection with operation/profile IDs, state, safe error code/summary,
`review_revision` when present, and server-owned `can_review`, `can_retry`, and
`can_discard` flags. It returns no source text, path, provider payload, prompt,
chunks, or document JSON.

`GET .../reextract-draft` returns only the draft linked to the requested
operation. Its strict body includes `operation_id`, `operation_state`, and the
server-owned action flags. A stale review is still readable and discardable at
its current returned draft revision, but never approvable. Status/review reads
first persist the idempotent `review_ready` to `stale` reconciliation when live
CAS no longer matches. The approval endpoint repeats
the state/CAS checks and returns `409 PROFILE_REEXTRACT_STALE` even if a stale or
forged client submits `can_approve=true`.

Approve body:

```json
{"operation_id":"<uuid>","revision":"<aware UTC datetime>"}
```

Discard query parameters contain the same operation ID and revision. Missing,
cross-profile, stale, or replayed identities return a typed 404/409 without
mutating a row.

`GET /api/profile` continues to expose the active profile's pending review and
adds the correlated nullable operation ID for `source='reextract'`. A nullable
safe re-extraction-operation projection covers `running`, `interrupted`,
`failed`, or stale-without-review recovery. This lets Overview show the pending
action without requiring the user to discover CV Manager first.

## 12. Frontend state and UX

### 12.1 One operation owner

`useCvManagerState` keeps the typed operation projection and exact operation ID.
It does not infer completion from stream close. Stream events update progress;
terminal state is reconciled through the status/review GETs.

The App receives a re-extraction lock callback from the CV Manager controller.
The lock is combined with server-projected profile state and passed to both:

- the Overview/sidebar upload input; and
- the chat-composer PDF upload input.

Backend gates remain authoritative when another tab has the operation.

### 12.2 Drawer and recovery behavior

- Close hides the drawer and restores focus; it does not call `AbortController`
  for re-extraction.
- Reopen and application rehydrate load operation status before showing an
  action.
- `running`: stable progress/status, uploads disabled, Refresh available.
- `review_ready`: Review changes with Save profile and Discard review.
- `interrupted`: clear interruption message with Retry; uploads are allowed.
- `failed`: safe error with Retry; a pre-existing valid review is never cleared.
- `stale` with review: explain that the source profile changed, disable Save,
  and offer Discard review followed by Retry.
- Success is shown only after authoritative approval/discard and profile refresh.

When upload receives `PROFILE_REEXTRACT_IN_PROGRESS` or
`PROFILE_REVIEW_PENDING`, the error surface beside that upload includes a
single direct **Review changes** or **Check re-extraction** action. It opens the
exact active-profile operation; the user is not told to search another page.

### 12.3 CV action policy

The backend CV Manager projection exposes `reextract` only when the item owns
the server-authoritative active ready profile and the retained file is
available. Inactive archived CVs may expose Preview, Download, and Activate
profile as applicable, but not Re-extract. The frontend renders only the exact
projected actions.

## 13. Error and recovery matrix

| Failure | Durable state | User action | Preserved data |
| --- | --- | --- | --- |
| Duplicate start | Existing operation unchanged | Open status/review | All data |
| Upload during `running` | Upload not persisted | Wait or check status | Existing profile, operation, files |
| Upload wins race | Operation becomes `stale` | Retry after current action | New upload plus prior approved truth |
| Provider/PDF failure | `failed` | Retry | Approved truth and prior draft |
| SSE disconnect | `interrupted` unless review already committed | Retry or Review changes | Approved truth and committed review |
| Backend restart | Orphan `running` becomes `interrupted` | Retry | All durable data |
| Draft/profile/workspace CAS mismatch | `stale` | Discard stale review, then Retry | Newer truth and stale proposal |
| Approval transaction failure | `review_ready` | Retry or Discard | Approved truth and review |
| Graph sync after approval fails | Operation consumed; approval committed | Run supported graph rebuild | Committed SQLite/files truth |
| Discard conflict | Review unchanged | Reload current review | Approved truth and review |

## 14. Deterministic test matrix

### Backend unit and repository tests

- Profile A and B can each be queried only by explicit owner; no repository
  function has a newest-global-row fallback.
- Draft target uniqueness, nullable source attachment, operation uniqueness,
  state/error coupling, and operation/draft FK behavior pass.
- Claim is idempotently rejected for duplicate requests and maps integrity
  errors to a stable 409.
- Action projection omits Re-extract for every inactive archived profile.
- Agent updates preserve operation ownership and canonical deduplication.

### Backend integration and ASGI tests

- Migration upgrade on empty and populated valid fixtures preserves complete
  schema metadata, row/scalar/JSON values, and passes
  `PRAGMA foreign_key_check`; null, duplicate, and orphan fixtures fail before
  mutation. Populated-operation downgrade refuses without mutation, while the
  allowed empty-operation downgrade/re-upgrade path also passes.
- Barrier-controlled re-extract versus upload tests cover both commit orderings
  plus the exact interleaving where upload passes its pre-byte gate,
  re-extraction commits its claim, and upload reaches its final
  `BEGIN IMMEDIATE` gate. They assert no orphan profile, attachment, draft, or
  operation and no leaked finalized file.
- Two concurrent re-extract requests perform exactly one staging/provider call.
- Profile/workspace revision changes before publication and approval produce
  conflicts without overwriting newer truth.
- Disconnect after the first SSE event leaves `interrupted`, returns every
  connection to the pool, and emits no `no active connection` warning.
- Disconnect after atomic publication recovers the exact review.
- Startup recovery changes only `running` operations to `interrupted`.
- Approve/discard reject wrong operation ID, wrong profile, stale revision, and
  replay; successful paths consume only matching rows.
- Stale review projection always returns `operation_state='stale'`,
  `can_approve=false`, and `can_discard=true`; direct and Agent approval both
  reject it server-side. Status/review GET atomically reconciles a broken live
  CAS to stale, stale Agent edits are rejected, and discard accepts only the
  current returned draft revision.
- Initial upload/Agent draft approval and cumulative correction regressions pass
  with the symbolic `draft_id='current'` contract unchanged.

### Frontend tests

- App-level integration proves re-extraction disables both upload inputs and
  reenables them for interrupted/failed terminal states.
- Closing CV Manager does not abort the stream or erase loading/review state.
- Reopen/reload renders running, review, interrupted, failed, and stale states
  from strict API parsing.
- Strict parsing rejects a stale review that advertises approval or omits its
  correlated operation ID.
- Upload 409 renders a direct pending action beside the failed control.
- Duplicate clicks and stale stream events cannot start or overwrite another
  operation generation.
- CV action tests prove an inactive archived item has no Re-extract button.
- Loading, success, error, focus restoration, keyboard, narrow viewport, and
  live-region behavior pass without overlap.

### Full and browser acceptance

- Backend full Pytest, Ruff, Mypy, migration, and database-contract gates pass.
- Frontend full Vitest, lint, typecheck, and production build pass.
- In a real browser with synthetic PDFs: start Re-extract, immediately attempt
  upload from Overview and chat, close/reopen CV Manager, reload during work,
  recover interruption/review, discard, retry, approve, and verify the active CV
  and lineage remain correct.
- Backend logs after the browser run contain no traceback, cancelled-session
  cleanup error, pool warning, or unexpected 5xx.

## 15. Docker backup, rehearsal, rebuild, and rollback

The implementation is not released directly onto the only authoritative
volume. Plan 18 adds one tracked PowerShell utility,
`infrastructure/scripts/app_data_snapshot.ps1`, with `Backup`, `Restore`, and
`Verify` actions. It must fail closed unless the exact volume name, Compose
project label, expected consumers, backend stopped state, archive SHA-256, and
restore confirmation all match. It archives the whole volume root, including
`jobagent.db`, WAL/SHM files, retained PDFs, and tailored artifacts. Restore is
all-or-nothing and verifies the resulting inventory before reporting success.
It never accepts a path inside the Git worktree for private backup output.

### 15.1 Fixed command prefix and preflight

All release commands run from the repository root in PowerShell with these
variables; no shortened Compose command is allowed:

```powershell
$ComposeArgs = @(
  '--env-file', '.env',
  '-f', 'infrastructure/docker-compose.yml',
  '-p', 'jobagentlatest'
)
$ReleaseSha = (git rev-parse --short=12 HEAD).Trim()
$AppVolume = 'jobagentlatest_app_data'
$CloneVolume = 'jobagentlatest_app_data_plan18_rehearsal'
$BackupRoot = Join-Path $HOME 'JobAgentBackups'
$BackupArchive = Join-Path $BackupRoot "jobagentlatest-plan18-$ReleaseSha.tar"

docker compose @ComposeArgs config --services
docker compose @ComposeArgs ps
docker volume inspect $AppVolume
docker ps -a --filter "volume=$AppVolume" --format '{{.Names}}'
```

Preflight requires exactly `neo4j`, `backend`, and `frontend`; the inspected
volume name must equal `$AppVolume`, its
`com.docker.compose.project` label must equal `jobagentlatest`, and its only
consumer must be `jobagentlatest-backend-1`. Any mismatch stops the release.
The clone volume and release-specific rollback/candidate tags must not already
exist; a rerun may continue only when their recorded IDs/hashes match the same
release manifest. Nothing silently reuses or overwrites them.
Record current container image IDs, Alembic revision, health response, selected
active profile, pending action, authoritative table counts, and retained-file
inventory.

### 15.2 Rollback tags and quiesced backup

Tag the images currently used by the running containers before any build:

```powershell
$BackendContainer = (docker compose @ComposeArgs ps -q backend).Trim()
$FrontendContainer = (docker compose @ComposeArgs ps -q frontend).Trim()
$BackendImageId = (docker inspect --format '{{.Image}}' $BackendContainer).Trim()
$FrontendImageId = (docker inspect --format '{{.Image}}' $FrontendContainer).Trim()
docker image tag $BackendImageId "jobagent-backend:pre-plan18-$ReleaseSha"
docker image tag $FrontendImageId "jobagent-frontend:pre-plan18-$ReleaseSha"
docker compose @ComposeArgs stop backend
& .\infrastructure\scripts\app_data_snapshot.ps1 `
  -Action Backup `
  -ProjectName jobagentlatest `
  -VolumeName $AppVolume `
  -ExpectedConsumer jobagentlatest-backend-1 `
  -ArchivePath $BackupArchive
$BackupSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $BackupArchive).Hash
$BackupSha256
```

The utility verifies the backend container exists and is stopped before opening
the volume read-only. Its manifest records archive hash/size, every relative
path and size, SQLite/WAL/SHM presence, table counts, active profile, pending
action, and source Alembic revision. The backend remains stopped throughout
candidate build and clone rehearsal. This creates one quiesced release window;
no post-backup application write can be lost by rollback.

### 15.3 Candidate build and isolated clone rehearsal

Build with pulled bases and give the resulting fixed-tag images immutable
candidate tags:

```powershell
docker compose @ComposeArgs build --pull backend frontend
docker image tag jobagent-backend:0.1.0 "jobagent-backend:plan18-$ReleaseSha"
docker image tag jobagent-frontend:0.1.0 "jobagent-frontend:plan18-$ReleaseSha"
$ExistingClone = docker volume ls `
  --filter "name=^$CloneVolume$" `
  --format '{{.Name}}'
if ($ExistingClone) { throw "Refusing to reuse clone volume $CloneVolume" }
docker volume create `
  --label jobagent.release.owner=jobagentlatest `
  --label jobagent.release.purpose=plan18-rehearsal `
  $CloneVolume
& .\infrastructure\scripts\app_data_snapshot.ps1 `
  -Action Restore `
  -ProjectName jobagentlatest `
  -VolumeName $CloneVolume `
  -ExpectedPurpose plan18-rehearsal `
  -ArchivePath $BackupArchive `
  -ExpectedArchiveSha256 $BackupSha256 `
  -ConfirmRestore
```

Rehearsal does not launch a second Compose stack and cannot collide with live
ports. It runs the candidate backend as one network-disabled, non-serving,
auto-removed container bound only to the explicitly named clone volume:

```powershell
docker run --rm --network none --env-file .env `
  --mount "type=volume,source=$CloneVolume,target=/data" `
  "jobagent-backend:plan18-$ReleaseSha" `
  alembic upgrade head
docker run --rm --network none --env-file .env `
  --mount "type=volume,source=$CloneVolume,target=/data,readonly" `
  "jobagent-backend:plan18-$ReleaseSha" `
  python -m app.services.profile_reextract_migration_smoke
& .\infrastructure\scripts\app_data_snapshot.ps1 `
  -Action Verify `
  -ProjectName jobagentlatest `
  -VolumeName $CloneVolume `
  -ExpectedPurpose plan18-rehearsal `
  -ArchivePath $BackupArchive `
  -ExpectedArchiveSha256 $BackupSha256 `
  -ExpectedAlembicRevision 0008_profile_reextract_ownership
```

The smoke command is provider-free and read-only. It verifies the expected
Alembic head, complete pre/post table inventory, retained files, active profile,
pending-action preservation, migration schema metadata, and
`PRAGMA foreign_key_check`. The clone volume remains isolated and retained
through production acceptance; it is not substituted for `$AppVolume`.

### 15.4 Production cutover and verification

Recheck the backup hash and exact stopped production volume against the
utility's recorded manifest before cutover, then stop the frontend and
recreate the image-changing services from the candidate images:

```powershell
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $BackupArchive).Hash -ne $BackupSha256) { throw 'Backup SHA-256 mismatch' }
docker volume inspect $AppVolume
docker ps -a --filter "volume=$AppVolume" --format '{{.Names}}'
& .\infrastructure\scripts\app_data_snapshot.ps1 `
  -Action Verify `
  -ProjectName jobagentlatest `
  -VolumeName $AppVolume `
  -ExpectedConsumer jobagentlatest-backend-1 `
  -ArchivePath $BackupArchive `
  -ExpectedArchiveSha256 $BackupSha256 `
  -ExpectedAlembicRevision 0007_add_cv_tailoring
docker compose @ComposeArgs stop frontend
docker compose @ComposeArgs up -d --wait --wait-timeout 180 `
  --force-recreate backend frontend
docker compose @ComposeArgs exec -T backend alembic current
docker compose @ComposeArgs ps
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/
```

Verification requires Alembic head `0008_profile_reextract_ownership`, exact
three-service topology, healthy API/frontend/Neo4j, matching active-profile and
retained-file inventory, no unexpected pending action, the real-browser
concurrency workflow, and backend/frontend logs with no traceback, cancellation
cleanup error, pool warning, or unexpected 5xx. Never run `down -v`.

### 15.5 Rollback

Rollback is triggered by migration, health, inventory, browser, or clean-log
failure. It keeps the backend stopped while restoring the verified whole-volume
snapshot, then restores the recorded image tags:

```powershell
docker compose @ComposeArgs stop frontend backend
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $BackupArchive).Hash -ne $BackupSha256) { throw 'Backup SHA-256 mismatch' }
& .\infrastructure\scripts\app_data_snapshot.ps1 `
  -Action Restore `
  -ProjectName jobagentlatest `
  -VolumeName $AppVolume `
  -ExpectedConsumer jobagentlatest-backend-1 `
  -ArchivePath $BackupArchive `
  -ExpectedArchiveSha256 $BackupSha256 `
  -ConfirmRestore
docker image tag "jobagent-backend:pre-plan18-$ReleaseSha" jobagent-backend:0.1.0
docker image tag "jobagent-frontend:pre-plan18-$ReleaseSha" jobagent-frontend:0.1.0
docker compose @ComposeArgs up -d --wait --wait-timeout 180 `
  --force-recreate backend frontend
docker compose @ComposeArgs exec -T backend alembic current
docker compose @ComposeArgs exec -T backend python -m app.graph.rebuild
docker compose @ComposeArgs ps
```

Rollback acceptance requires pre-migration Alembic revision
`0007_add_cv_tailoring`, the manifest's exact data/file inventory, healthy
services, correct active profile, and a successful derived-graph rebuild.
Rollback never deletes the source backup, never guesses row-level reversal,
never binds the clone volume to production, and never uses `down -v`.

## 16. File and module ownership map

Expected implementation boundaries:

- `backend/migrations/versions/0008_profile_reextract_ownership.py`: schema,
  preservation checks, copy, constraints, and guarded downgrade.
- `backend/app/db/models/`: operation model plus ProfileDraft ownership fields.
- `backend/app/repositories/profiles.py`: profile-scoped draft API only.
- A focused operation repository under `backend/app/repositories/`: claim,
  state CAS, recovery lookup, and consume operations.
- `backend/app/services/profile_drafts.py`: shared stage/publish boundary,
  scoped cumulative updates, and unchanged canonical deduplication.
- `backend/app/services/profile_reextraction.py`: durable orchestration, status,
  cancellation finalization, review, approve, and discard.
- `backend/app/services/profile_approval.py`: operation-aware common approval
  CAS and atomic consume.
- `backend/app/services/activity_gate.py`, `cv_upload.py`, profile activation/
  deletion, and `cv_manager_projection.py`: authoritative lock/action matrix.
- `backend/app/schemas/profile_reextraction.py`, `profile.py`, and
  `backend/app/api/profiles.py`: strict operation/review/API contracts.
- `backend/app/main.py` or its existing lifespan service boundary: startup
  transition from orphan `running` to `interrupted`.
- `backend/app/services/profile_reextract_migration_smoke.py`: provider-free,
  read-only clone-volume migration/inventory verification.
- `frontend/src/features/cv-manager/`: operation API/types/state/recovery UI and
  close semantics.
- `frontend/src/app/App.tsx`, profile overview/sidebar, and ChatPage: shared
  upload lock and direct pending action.
- Existing focused backend/frontend tests plus migration, ASGI concurrency,
  App integration, and browser acceptance evidence.
- `infrastructure/scripts/app_data_snapshot.ps1`: fail-closed whole-volume
  Backup/Restore/Verify utility used by rehearsal, cutover, and rollback.

The implementation plan must narrow this map to exact files after another
repository read. It must not add unrelated cleanup or rewrite the CV Manager.

## 17. Acceptance criteria

1. A committed operation exists before the first re-extraction event/provider
   call, and concurrent duplicate requests perform the expensive work once.
2. Re-extraction and upload are deterministic in both race orderings; neither
   can silently overwrite the other's authoritative state.
3. No production code selects, updates, approves, or deletes a profile draft
   without an explicit profile owner.
4. Migration 0008 preserves every valid draft and refuses ambiguous data before
   mutation; `source_attachment_id` remains nullable.
5. Publication and approval compare exact operation, draft, profile, and
   workspace revisions.
6. Cancellation/restart produces durable recovery state and no aiosqlite or
   SQLAlchemy connection-cleanup errors.
7. Closing/reopening CV Manager and browser reload expose the correct next
   action without inventing completion.
8. Both CV upload entry points are visibly locked during active re-extraction,
   and backend gates protect other tabs/direct callers.
9. Pending upload errors expose their exact Review/Check action in place.
10. Inactive archived CVs do not advertise an action the backend rejects.
11. Approval/discard preserve unrelated profile, draft, CV, Job, evaluation,
    conversation, retained-file, and graph data.
12. Full source, migration, Docker, browser, data-inventory, rollback-rehearsal,
    and clean-log gates pass on synthetic data.

## 18. Planning governance impact

This design changes SQLite schema, public API lifecycle, cancellation recovery,
and release/rollback behavior. It therefore requires a Version 2.4 amendment to
`docs/plans/Master_plan.md` and cannot be added as an unplanned repair under the
current terminal Plan 17 contract.

The planning portfolio update must:

- add the Version 2.4 durable profile re-extraction ownership amendment;
- explicitly supersede only the affected Master contracts: Section 6.1's
  database-wide `profile_drafts('current')` wording, Section 6.2 draft schema,
  Section 6.4 draft publication transaction, Section 10.5 CV reprocessing,
  Section 14 profile re-extraction APIs, Section 15.6 reprocessing state owner,
  Section 20 cancellation/recovery rows, and the terminal-authority sentence in
  Section 30.5;
- preserve Plan 17's completed tailoring objective and constraints;
- change only Plan 17's terminal-portfolio language into an explicit handoff to
  Plan 18;
- add `docs/plans/Plan_18.md` as the new terminal execution authority; and
- pass independent plan review before `docs/tasks/task_18.md` is created.

The order is fixed: commit this specification, obtain user approval of the
written file, invoke the incremental planning workflow, amend Master/Plan 17 and
create Plan 18, run independent portfolio review, and only then create Task 18.
The current Master and Plan 17 intentionally remain unchanged while this written
specification is awaiting review.

No production code, migration, task file, Docker volume, or image is changed at
the specification stage.
