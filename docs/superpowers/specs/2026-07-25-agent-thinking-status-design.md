# Agent Thinking Status Timeline Design

**Date:** 2026-07-25
**Status:** Approved design
**Scope:** Replace the streaming assistant `…` placeholder with a durable,
backend-driven, expandable Agent activity timeline rendered with Astryx.

## 1. Context

The chat currently creates an empty streaming assistant message and renders
`…` while waiting for response content. The backend already emits
`assistant_status` and durable `tool_status` SSE events. The frontend validates
both, keeps the latest assistant status in `ChatState.assistantStatus`, and
stores tool activity on the run. However:

- the `…` placeholder does not explain what the Agent is doing;
- `assistant_status` is rendered as a separate system notice rather than inside
  the streaming assistant row;
- the backend currently emits only an initial generic assistant status;
- frontend tool labels contain workflow-specific mappings; and
- assistant status history is not durable, so it cannot be restored after a
  reload or conversation switch.

The requested experience is the approved visual option **B**: a compact,
ChatGPT-like current-status row with an optional expandable activity timeline.
When a run finishes, it remains as a collapsed summary that can be reopened.

## 2. Goals

- Replace the literal `…` waiting bubble with the latest real Agent activity.
- Emit activity only from actual run, graph/node, provider, or tool execution
  boundaries; never infer work from timers or frontend guesses.
- Keep workflow labels and status ownership in the backend.
- Use one normalized client activity model for live SSE and hydrated history.
- Persist the completed timeline across reloads and conversation switching.
- Show a backend-provided friendly label plus a smaller technical name in the
  expanded timeline.
- Render the feature through public Astryx components and design tokens.
- Provide a restrained thinking animation with reduced-motion support.
- Preserve accurate run semantics for completed, failed, interrupted, and
  disconnected states.

## 3. Non-goals

- No display of chain-of-thought, hidden reasoning, prompts, model traces, tool
  arguments, raw tool results, stack traces, or CV contents.
- No generic observability console inside chat.
- No frontend registry of Agent nodes, tools, or workflow-specific labels.
- No internationalization framework or locale negotiation in this change.
- No token-by-token activity events.
- No new frontend design system or custom replacement for Astryx.
- No retroactive reconstruction of assistant-phase history that was never
  persisted before this feature ships.

## 4. Selected architecture

The backend owns a normalized `AgentActivity` projection. Real execution
producers publish activity through one service, which persists the projection
and then exposes it through both the existing SSE stream and conversation
history. The frontend validates and normalizes that projection into the run,
then renders it without knowing the workflow.

```text
Run / graph node / provider / tool execution
  -> Agent activity publication service
  -> durable AgentActivity projection
  -> existing assistant_status or tool_status SSE envelope
  -> conversation history run.activities
  -> one frontend ClientAgentActivity model
  -> Astryx thinking status + collapsible timeline
```

`AgentRun` and `ToolExecution` remain authoritative for execution state and
tool results. `AgentActivity` owns only the safe, user-facing timeline
projection. Observability data is not used as the chat data source.

## 5. Activity contract

### 5.1 Canonical projection

Each user-visible activity has this contract:

| Field | Contract |
| --- | --- |
| `activity_id` | Stable UUID used to upsert one logical step |
| `run_id` | Owning durable Agent run UUID |
| `sequence` | Non-negative, monotonically assigned order within the run |
| `kind` | `assistant` or `tool` |
| `label` | Non-empty, bounded, display-ready backend label |
| `technical_name` | Optional bounded graph node, phase, or tool identifier |
| `state` | `pending`, `running`, `completed`, or `failed` |
| `started_at` | Aware UTC timestamp |
| `updated_at` | Aware UTC timestamp used for stale-update rejection |
| `completed_at` | Aware UTC timestamp only for terminal activities |
| `duration_ms` | Non-negative duration only when known |
| `error_code` | Optional stable safe code for failed activities |

The database enforces unique `(run_id, sequence)`, cascades activity deletion
with its owning run, and ensures an activity belongs to exactly one run.
Updating an activity preserves its ID and sequence.
The producer creates one activity for a meaningful phase and updates that row;
it does not create a new row for every progress tick or response token.

Tool activity links to its durable `ToolExecution` identity. Execution truth
continues to come from `ToolExecution`; the activity service copies only the
safe display projection after the tool transition commits. Assistant activity
is published at real runner, graph/node, or provider boundaries.

### 5.2 Label ownership and extensibility

The producer supplies the friendly label at the same backend boundary that
knows the work has actually started. A tool or graph node added later therefore
adds its display metadata beside its backend registration, without changing
frontend code.

The frontend may map the four generic activity states to Astryx visual states.
It must not map `technical_name` values to labels or infer a current step from
message content. A backend generic humanization fallback may format a bounded
technical identifier when legacy durable tool history lacks a label, but the
frontend must not carry a workflow-specific fallback table.

### 5.3 Privacy boundary

The projection may contain only the fields above. Labels and technical names
must be bounded and sanitized. It must never contain:

- tool arguments or result payloads;
- prompts, hidden reasoning, provider messages, or raw model responses;
- CV text, JD text, contact details, or extracted document chunks;
- stack traces, exception strings, filesystem paths, credentials, or secrets.

## 6. SSE and history behavior

### 6.1 Backward-compatible transport

The existing `assistant_status` and `tool_status` event names remain. Their
payloads gain a canonical nested `activity` projection. Existing required
fields remain during this change so current consumers and tests do not lose
their contracts.

The legacy `assistant_status.message` value and `activity.label` come from the
same backend value. Existing tool identity/status fields and the nested tool
activity come from the same committed tool transition. They must not be
maintained by separate label owners.

Activity persistence completes before publication. Duplicate delivery is safe
because the frontend upserts by `activity_id`. When an older event arrives
after a newer update, the reducer keeps the record with the later `updated_at`.
Equal timestamps with identical content are idempotent; conflicting equal-time
updates are rejected rather than guessed. On hydration, durable history is
authoritative.

### 6.2 History hydration

`AgentRunView` gains ordered `activities`. Conversation history returns them
with the existing run/tool projection. The frontend history adapter and SSE
adapter both produce the same `ClientAgentActivity` type.

The existing rule that a durable run is attached to its initiating user
message remains unchanged. The existing assistant-row projection associates
that run with the corresponding assistant response and prevents duplicate
rendering.

Legacy runs without persisted assistant activities may show their durable tool
activities, projected by the backend with stable tool execution identity. They
do not invent missing assistant phases.

## 7. Backend publication behavior

Activity is emitted only when a backend producer can prove the corresponding
work boundary:

- the runner publishes a run-start/current-response activity when execution
  actually begins;
- graph/node or provider phases may publish their own activity when entered;
- the tool execution service publishes tool activity only after the durable
  status transition commits; and
- terminal cleanup completes or fails active activities consistently with the
  durable run outcome.

Adding a new producer uses the same publication service and contract. The
service assigns sequence on first creation and updates the same activity ID for
later state transitions.

An activity-persistence failure must not corrupt or roll back the Agent's core
work. The backend records a sanitized application error, emits no canonical
activity event for the failed write, and continues the run. Existing transport
and durable run/tool state remain available as the frontend fallback. The
product must not report a persisted timeline when persistence did not succeed.

## 8. Frontend state and composition

### 8.1 State ownership

`ClientRun` owns an ordered `activities` collection. The reducer upserts by
`activity_id`, rejects stale updates by `updated_at`, and orders by `sequence`.
The current visible status is the latest running activity, falling back to the
latest activity when none is running.

`ChatState.assistantStatus` is no longer the presentation owner. The
`assistant_status` reducer path adapts its canonical activity onto the run.
`StreamNotices` retains transport lifecycle notices such as connecting,
disconnected, and failed, but it no longer renders assistant activity as a
separate `ChatSystemMessage`.

Before the first backend activity arrives, the empty assistant row may show the
truthful transport fallback `Connecting…`. After run start, all Agent-work
labels come from backend activity. The literal `…` placeholder is removed.

### 8.2 Astryx component boundary

Implementation must first restore frontend dependencies and run the pinned
Astryx 0.1.4 discovery workflow from `frontend/AGENTS.md`:

```text
npx astryx build "streaming assistant status with expandable activity timeline"
npx astryx search "chat message status collapsible tool activity motion"
npx astryx component ChatMessage
npx astryx component ChatToolCalls
npx astryx component Collapsible
npx astryx component StatusDot
```

The final component choice must use documented public imports and props. The
intended composition is:

- existing Astryx `ChatMessage` and `ChatMessageBubble` for the assistant row;
- Astryx `Collapsible` for the summary/timeline disclosure;
- Astryx `ChatToolCalls` for the ordered activity rows when its documented
  contract supports the required generic items;
- Astryx `StatusDot`, `Text`, `HStack`, or `VStack` for state and layout; and
- Astryx tokens for all color, spacing, radius, typography, and motion values.

No raw layout `<div>`, raw color value, raw spacing value, Tailwind utility, or
parallel component system is introduced. If `ChatToolCalls` cannot represent
assistant activities after CLI verification, use documented Astryx list/stack
primitives rather than undocumented props or internal imports.

## 9. Approved UI behavior

### 9.1 Running, collapsed by default

The empty streaming assistant row displays:

- the latest backend activity label;
- a restrained pulse/status mark;
- a subtle shimmer across the running label; and
- a disclosure labelled `View activity · N steps` using the visible activity
  count.

The timeline is collapsed by default. Opening it does not affect Agent state,
scroll ownership, or focus outside the disclosure.

### 9.2 Expanded timeline

Rows appear in backend sequence order. Each row shows:

- the friendly backend label as primary text;
- `technical_name` and exact generic state as secondary text;
- duration when terminal and available; and
- a safe error code for failed activity when available.

Arguments, results, prompts, traces, and document content are never rendered.

### 9.3 Completed and interrupted runs

When the run completes, animation stops and the disclosure collapses to
`Completed · N steps`. It stays above the assistant response and can be opened
after reload or conversation switching.

An interrupted approval run is not completed or failed. It shows a static
`Waiting for your confirmation · N steps` summary and remains expandable.
Resuming the same run appends or updates activity on the same timeline.

When a run fails, the static summary becomes
`Unable to complete · N steps`. The expandable timeline remains available with
safe states and codes only.

### 9.4 Disconnect semantics

A transport disconnect never changes a durable run or activity to completed or
failed. The row shows `Connection lost — Agent may still be running` together
with the most recently known timeline. Reloaded durable history decides the
subsequent state.

### 9.5 Accessibility and motion

Current-status text uses a polite live region. Updates do not steal focus or
re-announce the full timeline. The disclosure has an accessible name, keyboard
operation, visible focus, and Astryx focus behavior.

Shimmer and pulse run only while an activity is running. Under
`prefers-reduced-motion: reduce`, animation stops; icon, text, and exact state
remain sufficient to understand progress. Animation never communicates the
only state signal.

## 10. Error handling

- Duplicate SSE events upsert harmlessly by `activity_id`.
- Stale updates cannot overwrite a newer `updated_at` projection.
- Invalid kind, state, timestamp, or identity fails schema validation and uses
  the existing safe stream-error path; raw payloads are not surfaced.
- Activity storage failure degrades the status feature but does not fail or
  roll back otherwise valid Agent work.
- Run terminal state is authoritative for the collapsed summary.
- Disconnect remains a transport condition and never false-terminalizes a run.
- Missing legacy activity renders the existing durable tool/run fallback; the
  frontend does not fabricate workflow labels.

## 11. Testing and verification

### Backend

- Schema and repository tests cover constraints, sequence allocation, stable
  upsert, ordering, stale updates, and cascade ownership.
- Publication tests prove activity is persisted before SSE emission.
- Runner/graph tests prove labels are emitted only at actual execution
  boundaries and terminal cleanup closes active activities.
- Tool tests prove the activity projection follows the committed durable tool
  transition and excludes arguments/results.
- SSE schema tests preserve legacy fields while validating nested activity.
- History tests hydrate ordered activities and legacy durable tool fallback.
- Privacy tests reject or exclude raw documents, provider payloads, exception
  text, paths, and secrets.

### Frontend

- Parser tests validate both SSE event kinds and the normalized activity shape.
- Reducer tests cover SSE/history parity, deduplication, stale updates, ordering,
  terminal states, interruption/resume, and conversation hydration.
- Component tests replace the `…` assertion with current activity, collapsed
  disclosure, expanded rows, technical secondary labels, completed persistence,
  failure, and disconnect behavior.
- Accessibility tests cover the polite live region, keyboard disclosure,
  accessible name, focus stability, and reduced-motion styling.
- Existing approval, job-card, match-card, recovery, and tool evidence tests
  prove the new timeline does not duplicate or steal their run/tool ownership.

### Integrated gates

- Backend Pytest, Ruff, and Mypy.
- Frontend Vitest, ESLint, TypeScript, and production build.
- Alembic upgrade against a fresh database plus migration-chain coverage.
- `git diff --check`.
- Docker Compose rebuild and health verification.
- Browser acceptance with a real Agent run:
  1. the `…` placeholder never appears;
  2. backend activity changes visibly as real phases/tools execute;
  3. the timeline expands and shows friendly plus technical labels;
  4. completion collapses and survives reload/conversation switching;
  5. interrupted approval resumes on the same timeline; and
  6. failure or disconnect never reports false completion.

## 12. Acceptance summary

The feature is complete when the assistant waiting row communicates real Agent
work through backend-owned activity, uses an expandable Astryx timeline, and
restores the completed timeline from durable history. The frontend must remain
workflow-agnostic, the literal `…` must be gone, animation must be restrained
and accessible, and no sensitive execution or document data may cross the
activity contract.
