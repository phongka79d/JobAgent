# Pasted JD Save Confirmation Design

## Status

Approved by the user on 2026-07-18. The user explicitly authorized the required
Master and Plan 12 amendments.

## Objective

When the user pastes a recognizable raw Job Description into chat, JobAgent
automatically reviews it, shows a concise non-canonical preview, and asks whether
to save it. No Job, extraction, embedding, evaluation, or Neo4j mutation occurs
until the user confirms.

## User Flow

1. The user pastes a raw JD into the normal chat composer.
2. The Agent recognizes a likely JD and requests a save confirmation through the
   existing `save_job` tool without performing ingestion.
3. Chat displays a compact card:
   - **Đã nhận diện nội dung JD**
   - Best-effort title, company, and at most five key skills when the Agent can
     identify them clearly.
   - **JD này chưa được lưu. Bạn có muốn lưu JD này không?**
   - **Lưu JD** and **Không lưu** actions.
4. **Lưu JD** resumes the same run/tool invocation and loads the exact initiating
   user message as the source. Existing persistence-first ingestion, extraction,
   exact-hash deduplication, embedding, and Neo4j synchronization then run once.
5. **Không lưu** resumes the same invocation, performs no Job ingestion, JD
   extraction/embedding, evaluation, or graph work, and completes truthfully
   with **JD chưa được lưu**.
6. A successful save renders the existing saved-job result and reports `created`,
   `returned`, or `retried` from ToolResult. It does not automatically evaluate
   the Job against the active CV.

A recognizable passive raw-JD paste always receives the confirmation card.
Existing deterministic non-Agent actions such as **Lưu JD & đánh giá lại**
remain explicit user actions
and do not add another confirmation. A public URL save keeps its existing direct
flow. If the user explicitly asks `save_job` to save supplied text, the existing
direct tool path remains available; the passive-paste path uses the new durable
current-message source.

## Recognition Boundary

The LLM remains the primary JD recognizer; no classifier model is added. Prompt
policy requires `save_job(source='current_message')` when the current message is
predominantly a pasted JD and no explicit non-save instruction is present.

Add one narrow deterministic repair in the existing decision node for obvious
English/Vietnamese JD-shaped text:

- Not a sole URL.
- At least 300 non-whitespace characters.
- At least five non-empty lines.
- At least two distinct markers from the bounded allowlist:
  `job description`, `responsibilities`, `requirements`, `qualifications`,
  `skills`, `about the role`, `mô tả công việc`, `trách nhiệm`, `yêu cầu`,
  `kỹ năng`, `quyền lợi`, or `mô tả vị trí`.
- Skip the repair when the message contains a clear opt-out such as `không lưu`,
  `đừng lưu`, `không cần lưu`, `do not save`, or `don't save`.

Reuse that fixed opt-out predicate as a `save_job` precondition for every source
mode by resolving the initiating message from injected `run_id`. If the model
calls the tool despite a clear opt-out, return the same truthful no-save
cancellation result without creating a confirmation or ingestion side effect.

If the first model decision is plain text despite this boundary, run exactly one
bounded repair decision requiring the existing `save_job` tool with
`source='current_message'`. If repair still fails, return fixed truthful text
stating that no save confirmation was created and the JD was not saved.

`ponytail:` this heuristic is a narrow fallback for clearly structured local-demo
JDs. If measured false positives/negatives remain material, replace it with a
typed composer intent instead of expanding keyword lists.

## Tool And Interrupt Contract

Keep the registered tool name and total count unchanged. Extend `save_job` source
selection to exactly one of:

```text
url: public HTTP(S) URL
text: explicit raw text supplied for a direct save request
source: current_message for a passive pasted-JD confirmation
```

For `source='current_message'`, the tool resolves `agent_runs.user_message_id`
from the injected `run_id` and loads the exact durable chat message server-side.
The LLM and frontend never provide a message ID.

Before any JD ingestion side effect, the tool validates the source and calls the
existing LangGraph `interrupt()` path. The running tool execution remains under
the same `(run_id, tool_call_id)` identity. The pending projection is:

```text
kind: job_save_confirmation
allowed_actions: [save_job, cancel_save_job]
card:
  tool_name: save_job
  tool_call_id: <current call>
  source: current_message
  text_length: <bounded integer>
  preview:
    title: string | null
    company: string | null
    skills: list[string], maximum 5
```

Preview fields are optional, bounded, presentation-only Agent estimates. They are
not persisted as Job facts and canonical extraction after save may differ. For
the current-message confirmation mode, raw JD text, message IDs, URLs, hashes,
prompts, credentials, and provider data never enter `pending_approval_json`, SSE
card payloads, arguments summaries, or frontend confirmation state. Existing
direct URL/text argument-summary compatibility is not changed by this design.

On `save_job`, reload the source message and run the existing ingestion owner.
On `cancel_save_job`, return a successful no-mutation ToolResult with
`committed=false` and `outcome='cancelled'`. Terminal replay and duplicate button
clicks remain idempotent.

## Frontend Contract

Reuse the current generic `approval_required` event, chat reducer, resume endpoint,
composer lock, and terminal history hydration. Add one focused
`JobSaveConfirmationCard`; do not overload the profile approval parser.

The card uses pinned Astryx `Card`, `MetadataList`, `Badge`, `ButtonGroup`, and
`Button`. It presents friendly Vietnamese copy, disables both actions after the
first click, and maps the two buttons to the existing resume transport. Tool
activity may display **Review JD** while interrupted and returns to normal
**Save Job** outcome wording after resume.

The cancellation result does not render a SavedJobCard. A successful direct save
continues to use the existing strict save-job result projection/card and invalidates
the saved-JD sidebar only after committed success.

## Error And Recovery Behavior

- Ambiguous/non-JD text receives normal conversation or a clarification, not a
  forced card.
- Source lookup failure returns a stable safe error and performs no mutation.
- Cancel creates no Job row and makes zero extraction/embedding/Neo4j calls.
- Save uses current duplicate/retry and persistence-first failure rules.
- Provider/graph failure after confirmed save remains truthful; any already
  committed SQLite row follows existing recovery contracts.
- New turns and uploads remain blocked while confirmation is interrupted.
- Repeated resume after terminal state remains a no-op.

## Testing

Backend tests cover prompt recognition, narrow repair/no-repair cases, exact source
resolution, no pre-confirmation side effects, both resume actions, duplicate action
idempotency, cancellation call counts, direct URL/text compatibility, deduplication,
and one-Agent/one-ToolNode/seven-tool/six-pass invariants.

Frontend tests cover exact card copy, optional preview fields, both buttons,
composer lock, one accepted action, cancellation without SavedJobCard, save success
with existing result cards, history/restart recovery, and safe malformed projection.

Desktop acceptance pastes one synthetic English JD and one Vietnamese JD at
`localhost:5173`, confirms no Job database or JD extraction/embedding/graph
activity before a click (the normal Agent recognition call is expected),
checks both cancellation and save/deduplication, and verifies no automatic
evaluation. Mobile and security testing remain excluded.

## Planning Impact

This changes the Master `save_job` contract from unconditional no-approval to a
conditional pasted-JD confirmation and adds a new approval-card kind. It requires
Master Version 1.9, a synchronized Plan 11 successor handoff, and a revised Plan 12
scope/requirements/implementation/verification contract. It adds no migration,
public endpoint, dependency, Agent, ToolNode, tool name, worker, or evaluation flow.
