# Frontend Functional E2E Audit Design

## Purpose

Validate every user-facing frontend function implemented through Plans 1-12 against
the live three-service JobAgent stack. The audit uses synthetic data, correlates
browser behavior with backend logs, and reports confirmed functional failures only.

Security testing, security findings, source-level code review, performance testing,
and features explicitly excluded by the plans are outside this audit.

## Execution Model

Use the production frontend in a real browser against the Compose frontend, backend,
SQLite/filesystem, Neo4j, and configured ShopAIKey provider. Do not replace API or SSE
responses with browser route mocks. Existing automated suites may be run as supporting
evidence, but they do not replace browser execution.

Use a disposable Compose project and synthetic fixtures where practical. If the normal
stack must be stopped because published ports conflict, record its initial state and
restore it after the audit. Do not use real CVs, JDs, or other personal data.

## Evidence Rules

For each test case:

1. Exercise the workflow through the visible frontend.
2. Check the resulting UI state and user-visible error behavior.
3. Inspect browser console and relevant requests/responses.
4. Correlate the action with timestamped backend logs.
5. For persistence-sensitive workflows, reload or restart and verify hydrated state.
6. Record a failure only when expected and actual functional behavior demonstrably
   differ or when the workflow cannot complete because of a project defect.

Provider, network, or environment failures are not product failures unless the UI or
backend handles them contrary to the applicable plan contract. An unexecutable case
is recorded separately from a product failure.

## Functional Test Matrix

### E01: Shell And Runtime

- Load the production frontend and confirm a nonblank Astryx application shell.
- Confirm the frontend can reach the configured backend and the backend reports the
  expected runtime component state.
- Check for startup console errors and failed boot requests.

### E02: Greeting, Streaming, And Durable History

- Send a greeting and observe composer locking, streamed assistant text, and terminal
  completion without a tool card.
- Reload and confirm the completed turn hydrates from durable history.
- Exercise older-history loading when enough history exists.

### E03: Chat Failure And Disconnect Recovery

- Exercise a controlled stream/backend interruption.
- Confirm the frontend shows a truthful failure or disconnected state without false
  completion.
- Restore the service, reload history, and confirm durable terminal truth with no
  duplicate side effect.

### E04: CV Upload Validation And Shared Upload Path

- Upload a valid synthetic digital PDF from each implemented upload entry point.
- Verify the attachment token, processing state, and approval proposal.
- Exercise implemented invalid-file behavior using synthetic invalid MIME, malformed,
  oversized, too-many-page, and image-only inputs where fixtures are available.

### E05: Profile Approval And Request Changes

- While approval is pending, verify composer, upload, and decision locks.
- Choose Request Changes, confirm focus returns to the composer, submit a correction,
  and obtain a new proposal.
- Save Profile once and confirm repeated actions cannot produce another mutation.
- Reload and confirm the active profile, active CV, and history remain coherent.

### E06: Direct JD Save, Duplicate, And Failure Display

- Save synthetic JD text through the explicit direct path.
- Save a controlled public URL when the configured environment permits it.
- Repeat exact content and confirm the UI reports the existing durable Job rather than
  a second Job.
- Exercise an unavailable or unsupported URL and confirm truthful fallback guidance.

### E07: Matching And Explanation

- Request matching before an approved profile and confirm upload/approval guidance.
- With an approved profile and scorable synthetic Jobs, request matches.
- Verify backend order, maximum result count, display score, matched/related/missing
  skills, source action, quality state, and collapsible component breakdown.
- Exercise unavailable or stale graph handling and confirm no partial result cards.

### E08: Observability Navigation And Responsive Shell

- Exercise Overview, CV Manager, LLM chunks, Neo4j graph, Agent runs, and saved-JD
  navigation.
- Verify expanded/collapsed desktop state and implemented mobile drawer behavior,
  including keyboard dismissal and composer usability.
- Confirm lazy loading, refresh, loading, empty, and safe-error states remain scoped to
  the selected panel.

### E09: Retained CV, Chunks, Runs, And Graph

- Open a retained synthetic CV from the frontend.
- Select CV history, paginate when available, open chunk detail, and inspect Agent-run
  history.
- Exercise graph ready, stale, unavailable, and truncated presentation when practical.
- Verify graph selection, fit/reset, pan/zoom, and semantic fallback remain usable.

### E10: CV Reprocess And Activation

- Reprocess active and archived CVs through the existing SSE/approval path.
- Exercise Request Changes and Save Profile.
- Confirm the active CV changes only after approval and dependent panels refresh
  without becoming blank.

### E11: CV Deletion

- Verify active CV deletion remains unavailable or truthfully rejected.
- Confirm deletion of a non-active CV through the frontend confirmation flow.
- Exercise a retryable failure only when it can be induced without corrupting retained
  user state, and confirm no false success.

### E12: Active-CV Answer And Source Dialog

- Ask a factual count question against a synthetic active CV with known records.
- Confirm a direct answer, exactly one adjacent source control, and an accessible
  dialog containing exactly the durable records read in tool-call order.
- Open the original retained PDF, close and reopen the dialog, reload the page, and
  confirm durable citation hydration without an extra evidence fetch.

### E13: Negative Provenance

- Exercise available failed, malformed, empty, non-CV, and conflicting-revision
  evidence fixtures or durable states.
- Confirm none produces a source control or false provenance marker.

### E14: Zero-Match Recovery

- Produce a successful zero-match result from a synthetic initiating JD.
- Confirm exactly one recovery card and source-bound Save JD & Evaluate action.
- Exercise successful and retryable-unavailable outcomes and confirm result/card reuse.

### E15: Saved-JD List, Detail, And Evaluation States

- Browse the saved-JD list and selected detail.
- Exercise no-evaluation, current, and stale states.
- Confirm a CV/profile revision change marks stale without an automatic evaluation
  request, then explicitly evaluate and verify the persisted result.
- Confirm processed-unscorable detail with an empty summary renders fallback metadata
  and a truthful unscorable evaluation result.

### E16: Saved-JD Deletion

- Delete a Job through the frontend confirmation flow and verify it disappears safely.
- Exercise retry behavior for a graph-side failure only when it can be induced safely.
- Confirm unrelated visible Job/profile/CV state remains available.

### E17: Assistant Markdown And Literal Messages

- Send a simple non-CV question and a longer question that needs grouping.
- Confirm the direct answer appears first, raw Markdown markers are not visible, and
  longer content uses no more than the planned grouping.
- Confirm user and system text remain literal.

### E18: Passive JD Cancel Across Reload

- Paste an obvious synthetic English JD without an explicit save command.
- Confirm a bounded confirmation card appears before mutation.
- Reload before deciding, confirm card recovery, choose Do Not Save, and verify no
  SavedJobCard, evaluation, or graph mutation is reported.

### E19: Passive JD Save And Dedupe

- Paste an obvious synthetic Vietnamese JD and choose Save JD.
- Repeat the same passive paste and confirm again.
- Confirm each run has its own confirmation, both outcomes reference the same Job, and
  no automatic evaluation UI/request occurs.

### E20: Passive JD Boundaries

- Send a sole supported URL, an explicit direct save request, a JD with an opt-out
  phrase, and ambiguous long prose.
- Confirm direct paths bypass passive confirmation, opt-out produces no card/mutation,
  and ambiguous prose is not forced into a save flow.

## Failure Report Contract

The final report contains only confirmed failures and unexecuted cases. Each confirmed
failure contains:

- ID, feature, affected plan, and severity.
- Preconditions and exact reproduction steps.
- Expected and actual frontend behavior.
- Browser console/network evidence.
- Correlated backend log evidence and stable error code when present.
- Reproducibility and user impact.

Passing cases are not listed individually. If no functional failures are observed, the
report says so and lists only cases that could not be executed. Security observations
are omitted even if encountered incidentally.

## Completion Criteria

- Every matrix case is executed or explicitly marked unexecuted with a concrete reason.
- The normal Compose stack is restored to its initial running/stopped state.
- Temporary synthetic test resources are removed where deletion is part of the tested
  workflow or where cleanup is safe.
- The failure-only report is written under `docs/reports/` and summarized to the user.
