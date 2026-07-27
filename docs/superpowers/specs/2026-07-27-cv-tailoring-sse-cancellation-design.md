# CV Tailoring SSE Cancellation Repair

## Context

Creating a tailored CV can return a successful SSE response header and persist a
new tailoring session before the stream completes. In the observed failure, the
client disconnected after that point. The persisted session remained
`generating` and its run remained `running`. Every later creation request was
then rejected by the activity gate with `TAILORING_START_BLOCKED` and HTTP 400.

The coordinator already catches `asyncio.CancelledError` and `GeneratorExit`,
but its terminal persistence awaits run inside the request's cancelled scope.
The cancellation can therefore interrupt `_fail_generation()` before the
session and run reach a durable terminal state. The chat runner already solves
the equivalent problem by shielding its close-time terminal work.

## Decision

Apply the existing chat-runner cancellation pattern to the CV-tailoring
coordinator. Cancellation cleanup will execute inside an AnyIO shielded cancel
scope, persist the session/run terminal state, and delete the exact run
checkpoint only after terminal persistence succeeds. The original cancellation
is then re-raised so a disconnect is never reported as success.

No frontend, request schema, endpoint shape, public status mapping, database
schema, or generation behavior changes.

## Data Flow

1. `POST /api/cv-tailoring/sessions` prepares a durable session and run.
2. The response primes and emits `run_started` through the existing SSE owner.
3. If the client disconnects, the response closes the coordinator iterator.
4. The coordinator catches cancellation or generator close and enters a
   shielded cleanup block.
5. `_fail_generation()` atomically marks an initial session `failed` (or restores
   an existing versioned session to `ready`) and marks its running run `failed`.
6. The exact checkpoint is removed only when that durable transition succeeds.
7. The cancellation propagates; a subsequent create is no longer blocked by an
   orphaned active row.

## Current Runtime Repair

After the code and regression test pass, repair only the already observed
orphaned tailoring session/run through the existing repository transition
methods (`mark_session_failed` and `fail_run`) in one application transaction.
Do not edit SQLite directly, delete unrelated sessions, or infer success for the
cancelled generation. Remove its exact checkpoint only after the transaction
succeeds.

## Test Strategy

Add one integration regression test at the real ASGI/SSE disconnect boundary:

- prepare a tailoring session with disposable SQLite and synthetic fakes;
- open the existing SSE response and disconnect after `run_started`;
- verify the test fails against current code because cleanup is cancelled;
- after the fix, assert the session and run are durably `failed`;
- assert the profile activity gate is unblocked;
- assert checkpoint cleanup happens only after durable failure.

Run the focused coordinator/SSE/API tests, then Ruff, Mypy, the relevant backend
suite, and `git diff --check`. Rebuild the backend container, repair the single
orphan, and verify a fresh create request no longer returns
`TAILORING_START_BLOCKED` before completing browser acceptance.

## Alternatives Rejected

- Returning HTTP 409 or handling the error only in the frontend would expose a
  clearer symptom but leave the orphaned active state unchanged.
- Reusing or silently deleting the pending session on every create would blur
  ownership and could race a genuinely active generation.
- A general startup sweep is broader than the observed disconnect bug and is
  not required for this focused repair.

## Non-Goals

- Resuming a cancelled tailoring generation.
- Adding queues, workers, retries, or new public maintenance endpoints.
- Changing the one-active-run business rule.
- Refactoring unrelated SSE, chat, profile, or saved-JD code.
