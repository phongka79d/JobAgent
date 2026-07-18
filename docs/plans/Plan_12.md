# Plan_12: Readable Agent Responses, Active-CV Sources, And JD Save Confirmation

## Objective

Make Agent answers clear for non-technical users and visibly attributable when
the answer is based on the active CV. Assistant messages render through the
pinned Astryx Markdown component, begin with the direct answer, and use only a
small number of meaningful groups when more detail is needed. User and system
messages remain literal.

When the durable run contains a successful bounded `read_active_cv` ToolResult,
the supported answer shows one adjacent **Nguồn** citation. Activating it opens
an accessible dialog containing exactly the entry/chunk records read by the
Agent, in original tool-call order, plus **Mở CV gốc** for the same attachment.
No valid evidence means no citation.

When the user passively pastes a recognizable English or Vietnamese JD, keep the
exact durable user message unsaved and show one concise
`job_save_confirmation` card with **Lưu JD** and **Không lưu**. No Job row,
extraction, embedding, evaluation, or Neo4j mutation may begin before the first
accepted action. **Lưu JD** resumes the same `save_job` invocation and ingests
the exact initiating durable message once; **Không lưu** completes truthfully
with `committed=false` and zero mutation. A confirmed save does not evaluate the
Job automatically.

The phase is complete only when raw Markdown markers no longer clutter Agent
answers, a question such as “Tôi có mấy Certificate?” produces a direct
evidence-backed answer and one working source dialog, restart/history hydration
preserves both citations and interrupted JD cards, missing/failed/malformed
evidence never creates a citation, and both JD confirmation branches preserve
the existing direct URL/text save and explicit evaluation paths.

## Source of Truth

- `docs/plans/Master_plan.md` Version 1.9: `### 7.5 Tool execution result`,
  `### 11.2 Pasted-text confirmation boundary`, `### 12.1 One Agent, one
  controlled loop` through `### 12.6 Tool loop limits`, `### 13.4 save_job`,
  `### 13.7 read_active_cv`, `### 14.2 SSE contract`, `### 15.3 Chat
  components` through `### 15.7 Readable Agent responses and pasted-JD
  confirmation`, `## 20. Failure and Recovery Policy`, and `## 24. Local
  Testing Strategy`.
- `docs/plans/Plan_5.md`: implemented direct URL/text `save_job`,
  persistence-first ingestion, exact-hash return/retry, compact ToolResult, and
  durable `(run_id, tool_call_id)` replay.
- `docs/plans/Plan_9.md`: implemented document-first extraction, compact
  active-CV outline, bounded `read_active_cv`, durable ToolResult ownership, and
  retained-PDF endpoint.
- `docs/plans/Plan_11.md`: completed desktop-reliability baseline and successor
  handoff, including the bounded exact-name `save_job` repair and ToolResult-
  derived outcome narration that this phase must preserve.
- `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md`:
  user-approved passive-paste recognition, exact durable source binding,
  pre-mutation interrupt, compact card, save/cancel semantics, and no automatic
  evaluation.
- `frontend/package.json` and pinned Astryx `0.1.4` public APIs: `Markdown`,
  `Citation`, `Dialog`, `DialogHeader`, `Card`, `MetadataList`, `Badge`,
  `ButtonGroup`, layout primitives, and `Button`.
- **Approved changes (2026-07-18):** render Agent output cleanly for
  non-technical users; lead with the answer; use the selected hybrid layout;
  show one source control beside an active-CV-backed answer; open the exact
  evidence read by the Agent and allow opening the original CV; and ask whether
  to save a passively pasted recognizable JD before any mutation. Skip mobile.
- **Change type:** `feature`.
- **Master impact:** `amendment`, explicitly authorized by the user and applied
  as Master Version 1.9. The amendment changes passive raw-JD text from immediate
  acceptance to conditional `save_job(source='current_message')` confirmation
  and adds one frontend confirmation-card kind. It preserves the architecture,
  database schema, stack, deployment rules, public endpoints, seven-tool
  registry, and product boundary.

## Master Requirement Coverage

| Requirement ID | Master/approved source | Owned outcome | Verification evidence |
|---|---|---|---|
| P12-RSP-01 | Master 12.5; approved response layout | The Agent leads with a direct answer; simple answers use no heading; longer answers use at most three short user-facing groups. | Prompt contract tests and desktop response samples. |
| P12-RSP-02 | Master 15.3; Astryx 0.1.4 | Assistant-only content renders semantic Markdown with compact spacing and streaming support, while user/system content stays literal. | Component tests for headings, emphasis, lists, user literals, and streaming. |
| P12-CV-01 | Master 12.4, 13.7 | Questions asserting facts or counts from the active CV use the narrowest `read_active_cv` mode; the outline is navigation, not final body evidence. | Prompt/tool tests and Certificate-count desktop smoke. |
| P12-CV-02 | Master 7.5, 14 | Durable history retains only a strict frontend projection of successful `read_active_cv` evidence; `tool_executions` remains the sole durable owner. | Projection, hydration, restart, and forbidden-key tests. |
| P12-CV-03 | Approved source layout | Exactly one **Nguồn** citation is placed with the lead answer when at least one valid evidence page belongs to that row. | Assistant-row interaction and exact-one tests. |
| P12-CV-04 | Master 13.7; existing retained-file route | The source dialog shows the exact records returned to the Agent and opens the same attachment’s retained PDF without fetching new evidence. | Dialog record-order, truncation, no-fetch, and URL tests. |
| P12-CV-05 | Master 20, 24 | Failed, malformed, empty, mismatched-revision, non-CV, or stream-only tool state never produces a source citation or false provenance. | Negative parser/UI/reducer tests. |
| P12-JD-01 | Master 11.2, 12.5; approved design | The LLM is the primary passive-JD recognizer; clear opt-outs suppress tool repair/card/mutation, and one narrow obvious-JD repair covers structured English/Vietnamese text without deterministically forcing ambiguous text. | Prompt/decision tests for recognition, thresholds, marker diversity, opt-outs, explicit paths, and one repair only. |
| P12-JD-02 | Master 6.4, 12.2-12.3, 13.4 | `source='current_message'` resolves `agent_runs.user_message_id` from injected `run_id`, reloads that durable user message server-side, and interrupts before any ingestion side effect. | Source-ownership, lookup-failure, pre-interrupt call-count, pending-row, and no-raw-projection tests. |
| P12-JD-03 | Master 14.2, 15.3-15.7 | One strict `job_save_confirmation` card projection exposes only tool identity, source mode, bounded text length, and bounded title/company/up-to-five-skill preview; the frontend renders exactly two actions. | Backend projection/SSE tests plus frontend parser/card malformed-payload and exact-copy tests. |
| P12-JD-04 | Master 7.5, 12.2, 13.4, 20 | Save/cancel resume the same `save_job` execution; save ingests the exact durable source once, cancel returns `committed=false`/`outcome='cancelled'`, and terminal/repeated actions do not repeat work. | Interrupt/resume, execution-identity, branch call-count, duplicate-click, and terminal-replay integration tests. |
| P12-JD-05 | Master 11.2, 17.5, 24 | Confirmed save reuses direct persistence-first deduplication and existing result cards but issues no evaluation; direct URL/text saves and public **Lưu JD & đánh giá lại** remain explicit compatible paths. | Direct-path regressions, saved-card/cancellation gating, no-evaluate assertions, and desktop acceptance. |
| P12-REG-01 | Master 12.1, 12.6, 24 | One Agent, one decision node, one ToolNode, seven tools, six-pass limit, existing profile approval, saved-JD/evaluation flows, and desktop behavior remain unchanged. | Existing graph/backend/frontend/full-suite gates. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Plan_11 | Green desktop reliability baseline, current assistant-row composition, automatic terminal history rehydrate, exact-name `save_job` repair, ToolResult-derived narration, and unchanged user volumes | Run current focused backend/frontend tests before edits; preserve positive exact-name behavior while letting a clear opt-out win. |
| Plan_5 | Direct URL/text `save_job`, persistence-first ingest, exact dedupe/retry, argument redaction, and durable execution replay | Trace every tool/schema/registry caller before extending the input union; reuse the current ingestion owner after confirmation. |
| Plan_9 | Successful `read_active_cv` data containing attachment/revision/mode/records and bounded entry/chunk text | Inspect all reader/tool/history callers; do not change the reader contract without a newly reproduced defect. |
| Plans 3-4 | `agent_runs.user_message_id`, `chat_messages.get_by_id`, `tool_executions.result_json`, `interrupt/resume`, `allow_running_reentry`, generic `approval_required`, and terminal no-op replay | Confirm the same run/tool/checkpoint identity can host the second approval kind without a new endpoint or state store. |
| Frontend baseline | `ChatMessageRow`, `toolsForAssistantDisplay`, pending-approval recovery, shared resume handler/lock, `history.projectToolResultData`, and terminal `history/rehydrate` | Reuse these association, transport, locking, and durable-truth owners; do not overload the profile parser. |
| Astryx 0.1.4 | Public `Markdown`, `Citation`, `Dialog`, `Card`, `MetadataList`, `Badge`, `ButtonGroup`, and `Button` contracts | Inspect the installed component documentation before implementation. |
| Local desktop stack | Frontend `http://localhost:5173`, backend `http://localhost:8000`, active synthetic CV, two synthetic JDs, retained-PDF route, and observable JD extraction/embedding/graph call seams | Use synthetic data and desktop viewport only; establish Job/evaluation/graph counts before each JD branch. |

## Scope

- Strengthen the existing system prompt with conclusion-first, low-clutter,
  non-technical response rules.
- Require narrow `read_active_cv` evidence for factual active-CV assertions and
  counts, including necessary bounded pagination for a genuine count request.
- Render assistant content with Astryx Markdown using compact density, shifted
  heading levels, and the existing streaming flag.
- Keep user messages, system messages, tool summaries, existing profile/saved-
  job/match cards, and profile approval behavior literal and unchanged.
- Add one strict source-owned parser/projector for bounded `read_active_cv`
  ToolResult data and chain it into the existing durable history projection.
- Bind valid evidence to the same assistant row through the existing durable
  user-run/tool relationship.
- Add one **Nguồn** citation beside the lead answer and one accessible dialog
  showing the exact records read plus **Mở CV gốc**.
- Extend the existing `save_job` input with the mutually exclusive passive
  `source='current_message'` mode and a strictly bounded presentation preview.
- Resolve the exact initiating user message from injected `run_id`, reuse the
  current `save_job` durable execution, and interrupt before Job persistence, JD
  extraction/embedding, evaluation, or graph work with
  `kind='job_save_confirmation'`.
- Add one narrow deterministic decision repair for obvious structured English/
  Vietnamese JDs after a plain-text model miss, with clear opt-out precedence and
  the existing positive exact-named `save_job` path ahead of passive repair.
- Add one strict frontend parser and Astryx `JobSaveConfirmationCard` that reuses
  the existing approval SSE, resume transport, composer lock, first-click lock,
  and history/restart recovery.
- Make cancellation a successful no-mutation ToolResult and reuse existing
  save-job result/card invalidation only after a confirmed committed save.
- Add focused backend/frontend tests, full regression gates, and desktop-only
  direct acceptance for readable responses, CV sources, and both JD branches at
  `localhost:5173`.

## Out of Scope

- Changes to `read_active_cv`, active-CV storage, extraction, cursor semantics,
  ToolResult persistence, chat-history response shape, or any public endpoint.
- Copying ToolResult data into `chat_messages`, structured assistant payloads,
  a second frontend store, local storage, or a new provenance database.
- Fetching referenced chunk ordinals on dialog open, automatically loading more
  pages, or presenting evidence the Agent did not actually read.
- Citations for Candidate Profile outline/context, saved jobs, match results,
  general knowledge, web sources, failed tools, or other tool names.
- A second Agent/node/ToolNode, classifier model, typed response API,
  provider/model change, tool-count change, or relaxation of the six-pass limit.
- Treating ambiguous text as a JD, expanding the repair into a general intent
  classifier, or growing the marker/opt-out lists without measured evidence and
  a newly approved contract.
- Persisting preview guesses as canonical Job fields; exposing raw JD text,
  message IDs, URLs, hashes, arguments, prompts, credentials, or provider data in
  pending approval, SSE, frontend state, or user-facing tool activity.
- Adding confirmation to a sole public URL, an explicit direct URL/text
  `save_job` request, or the public **Lưu JD & đánh giá lại** action.
- Automatic evaluation after confirmed save, a new evaluation action, or any
  scoring/currentness change.
- A new Markdown parser, custom HTML renderer, CSS framework, dependency, or
  hand-built layout where an installed Astryx component exists.
- Security testing/work, mobile/narrow-layout changes or evidence, database/
  Alembic migrations, a new public endpoint or SSE envelope, unrelated UI
  redesign, or fixes outside this response/source/JD-confirmation scope.
- Strict projection allowlist/forbidden-key assertions in this plan are functional
  payload-shape tests, not penetration, abuse, or security testing.
- Creating `docs/tasks/task_12.md`, implementing product code, or claiming
  portfolio approval during this planning phase.

## Target Directory Structure

```text
backend/
  app/
    agent/
      graph.py
      prompt.py
    schemas/
      jobs.py
    services/
      job_save_confirmation.py
    tools/
      jobs.py
  tests/
    unit/
      test_shopaikey_chat.py
      test_agent_graph.py
      test_job_save_confirmation.py
    integration/
      test_active_cv_tool.py
      test_chat_api.py
      test_job_tools.py
frontend/src/
  features/
    chat/
      activeCvEvidence.ts
      history.ts
      jobSaveConfirmation.ts
      ChatPage.tsx
      components/
        AssistantResponse.tsx
        ActiveCvSourceDialog.tsx
        JobSaveConfirmationCard.tsx
        ChatMessageRow.tsx
        ChatMessages.tsx
        ChatToolActivity.tsx
  test/
    assistant-response.test.tsx
    active-cv-source.test.tsx
    job-save-confirmation.test.tsx
    chat-page.test.tsx
    sse-reducer.test.ts
docs/
  plans/
    Master_plan.md                            # Version 1.9 amendment already applied
    Plan_11.md                               # terminal boundary changed only
    Plan_12.md
  superpowers/specs/
    2026-07-18-pasted-jd-save-confirmation-design.md  # approved design source
```

Names may align with an equivalent focused owner found during the required
search-before-write pass. `ChatMessageRow.tsx` and `ChatPage.tsx` must delegate
rather than absorb Markdown, evidence, JD projection, or card responsibilities.
Reuse `getRetainedCvUrl` from the existing observability API owner, the existing
pending-approval row association, and the current resume/first-click lock instead
of creating parallel URL, interrupt, or state owners. Repository files are not
targets: current `agent_runs.get_run` and `chat_messages.get_by_id` already own
the exact durable source lookup. Keep the new confirmation service focused and
below the repository's 300-line target; do not further grow the already-large Job
tool or Agent graph with reusable parsing/source/projection logic.

## Technical Specifications

### Response Policy And Active-CV Tool Use

Extend `build_system_prompt` in its current owner; do not add response logic to
the graph or API route.

- Put the direct answer in the first sentence or short first paragraph. Do not
  lead with process narration, tool names, repeated restatements, or a heading.
- A simple answer of one or two facts uses no heading and no unnecessary list.
- When more structure is genuinely useful, use at most three short Markdown
  groups with labels adapted to the user’s language (for example `Điểm chính`
  and `Đề xuất`). Do not nest heading pyramids or repeat a conclusion section.
- Prefer short paragraphs and compact bullets. Use valid Markdown, not raw HTML,
  pseudo-JSON, developer logs, or escaped formatting instructions.
- Keep the response language aligned with the user. Hide internal selectors,
  cursor values, hashes, and tool mechanics unless the user explicitly asks.
- Treat `active_cv_context` as identity/outline navigation only. Before asserting
  a value, item, quote, or count that depends on CV entries/body text, call
  `read_active_cv` using the narrowest matching section/search/chunk mode.
- For a count such as Certificates, read the matching section and follow
  `next_cursor` only when needed to finish that genuine count, still within the
  existing six-pass limit. Do not report outline `entry_count` as body evidence.
- After successful evidence, answer from the returned records and lead with the
  result (for example, `Bạn có 3 chứng chỉ.`). Do not ask the model to invent a
  source URL, citation token, or source label; frontend provenance is derived
  solely from the durable ToolResult.
- When the current message is predominantly a passively pasted recognizable JD,
  call `save_job` with `source='current_message'` and optional bounded preview;
  state that it remains unsaved and wait for the card decision.
- A sole public URL or an explicit direct URL/text save request keeps the
  existing direct input path. A clear `không lưu`, `đừng lưu`, `không cần lưu`,
  `do not save`, or `don't save` instruction suppresses both confirmation and
  mutation. Ambiguous text stays normal conversation or receives clarification.
- After confirmed `save_job`, report only the durable ToolResult outcome and do
  not call `match_jobs` or claim an evaluation unless the user separately asks
  through an existing explicit evaluation path.
- Existing exact-name save truthfulness, failed-tool truthfulness, profile
  approval, registered-tool allowlist, and general-conversation rules remain
  unchanged.

Prompt tests must assert these rules are present only where appropriate and that
the production registry remains seven tools. Decision tests must prove a clear
opt-out wins globally, the Plan 11 exact-name repair wins over passive-JD repair
for positive requests, and neither repair can loop. Normal automated tests
continue to use fakes; the real provider is
exercised only by explicit local acceptance.

### Passive-JD Recognition And One Bounded Repair

The LLM remains the primary recognizer. Put the fixed pure normalization,
opt-out, sole-URL, and obvious-JD predicates in focused
`services/job_save_confirmation.py`; the same module owns exact initiating-
message resolution and strict pending-projection construction. Both the decision
node and Job tool reuse this boundary. It performs no provider, ingestion,
evaluation, graph, or interrupt work. Extend the current single decision node;
do not add a classifier, state field, node, model call type, or tool.

Evaluate deterministic postconditions in this order:

1. When the initiating user text contains one of the approved clear opt-outs
   after Unicode-aware case folding, suppress both exact-name/passive save repair
   and any mutation-success narration.
2. Otherwise preserve the existing exact registered-name `save_job` gate and its
   direct URL/text repair/narration contract.
3. Do not classify a sole HTTP(S) URL as a passive JD.
4. Treat the text as an obvious-JD repair candidate only when it has at least
   300 non-whitespace characters, at least five non-empty lines, and at least two
   distinct case-insensitive markers from this fixed allowlist:
   `job description`, `responsibilities`, `requirements`, `qualifications`,
   `skills`, `about the role`, `mô tả công việc`, `trách nhiệm`, `yêu cầu`,
   `kỹ năng`, `quyền lợi`, `mô tả vị trí`.
5. If the first model decision for that candidate is plain text, discard it and
   perform exactly one repair decision requiring one sole valid
   `save_job(source='current_message')` call. If the repair still omits that
   call, terminate with fixed truthful user-language text saying no confirmation
   was created and the JD was not saved.

Do not repair when the first decision already has a tool call; normal tool
validation remains authoritative. Count marker presence, not repetitions, and
do not grow this list during implementation. Place a `ponytail:` comment beside
the helper: it is a narrow fallback for obvious structured local-demo JDs; if
measured false positives/negatives remain material, replace it with a typed
composer intent in a future approved increment instead of adding keywords.

The same clear-opt-out predicate is also a write precondition for every
`save_job` source mode. Resolve the initiating user message from injected
`run_id` for this instruction check even when URL/text arguments are direct. If a
model nevertheless calls the tool for a message containing an approved opt-out,
return the successful no-save cancellation ToolResult immediately without
interrupt, Job persistence, JD extraction/embedding, evaluation, graph work, or
a card.
The normal Agent recognition call is outside this ingestion-side-effect boundary.
This defense does not attempt to classify ambiguous text inside the tool.

Unit cases must cover every threshold boundary, CRLF/LF Vietnamese and English
text, repeated-one-marker rejection, sole URL, short/ambiguous prose, each
opt-out-over-exact-name and positive-exact-name-over-passive precedence,
first-model success, one repair success, repair
refusal, unrelated greetings, and the unchanged six-pass counter.

### Current-Message Source And Save-Tool Contract

Extend the existing strict `SaveJobInput` union and `save_job` signature without
registering another tool:

```text
url: non-empty public HTTP(S) URL | null
text: non-empty explicit raw text | null
source: current_message | null
preview:
  title: string | null, maximum 160 characters
  company: string | null, maximum 160 characters
  skills: list[string], maximum 5 values, each maximum 80 characters
```

Exactly one of `url`, `text`, or `source='current_message'` is required.
`preview` is accepted only with `source='current_message'`; trim surrounding
whitespace, convert blank strings to null/omitted values, preserve order, and
reject extra keys or over-limit values. Preview data is an LLM estimate used only
for presentation and never enters ingestion or canonical `job_posts` facts.
Keep `JobIngestOutcome` exactly `created | returned | retried`; define a separate
strict cancellation result model for `{committed: false, outcome: cancelled}` so
no downstream ingestion parser can mistake cancellation for a saved Job.

For the opt-out precondition and `source='current_message'` resolution, use the
injected graph `run_id` and existing repositories in one short read transaction:

1. Load `agent_runs.id=run_id`.
2. Read its `user_message_id` server-side.
3. Load that exact `chat_messages` row and require `role='user'`, the main
   conversation, and non-empty content.
4. Never accept a caller-supplied message ID or add a second raw-content copy to
   tool-call arguments/checkpoint metadata, graph fields, pending approval, SSE,
   or frontend. The initiating HumanMessage keeps the runner's existing current-
   turn/checkpoint behavior, but it is never used as the post-confirmation source
   of truth.

Use stable safe `CURRENT_MESSAGE_NOT_FOUND`/`INVALID_CURRENT_MESSAGE` failures
when lookup or ownership validation fails, with zero Job/JD-extraction/embedding/
evaluation/graph work.
The argument summary for this mode is exactly `{source: current_message}`; the
durable source length is resolved later for the card. It contains no preview
guesses, raw text, message ID, URL, hash, or prompt data. Existing URL/text
summaries and ingestion behavior remain compatible.

### Pre-Mutation Interrupt, Save, Cancel, And Replay

Follow `commit_profile_draft`'s accepted interrupt pattern inside the existing
`save_job` tool. Pass `allow_running_reentry=True` to shared `execute_tool` only
for `source='current_message'`; retain the existing running-identity rejection
for direct URL/text calls. URL/text paths do
not interrupt. The current-message invocation must validate and reload its
durable source, enforce the opt-out precondition, build the strict projection
below, and call LangGraph `interrupt()` before constructing provider clients or
invoking `ingest_raw_text`:

```text
kind: job_save_confirmation
allowed_actions: [save_job, cancel_save_job]
card:
  tool_name: save_job
  tool_call_id: <injected current call>
  source: current_message
  text_length: min(len(content), 1000000)
  preview:
    title: string | null
    company: string | null
    skills: list[string], maximum 5
```

On resume, accept only the action already validated against the durable pending
projection. For `save_job`, reload the same message through `run_id` immediately
before ingestion and pass its exact content to the existing persistence-first
`ingest_raw_text` owner. Do not trust preview or checkpoint text as source.
For `cancel_save_job`, return without creating provider/normalizer/embedding/
graph dependencies:

```text
ToolResult:
  ok: true
  code: null
  summary: JD chưa được lưu
  data:
    committed: false
    outcome: cancelled
```

The same `(run_id, tool_call_id)` row remains `running` at interrupt and becomes
one terminal `completed` row after either action. Existing replay returns its
stored ToolResult; rapid duplicate resume is accepted once or becomes the
current terminal no-op, never a second ingestion. A confirmed save keeps the
existing `created | returned | retried` result shape and no evaluation call is
added. Before another model decision, deterministically project final narration
from the validated ToolResult whenever this turn used the existing exact-named
path, called `save_job(source='current_message')`, or produced an opt-out
cancellation from any `save_job` mode. Cancellation must be described only as not
saved; it is never described as saved/created/reused and never produces a
saved-job payload. This postcondition also prevents an
automatic `match_jobs` follow-up after confirmed passive save.

### Assistant-Only Astryx Markdown

Create one focused `AssistantResponse` presentation component and compose it from
`ChatMessageRow`.

- Assistant text renders with Astryx `Markdown`, `density=compact`,
  `headingLevelStart={4}`, and `isStreaming={message.isStreaming}`. Use the
  pinned public API; do not import package internals.
- User text remains the literal `ChatMessageBubble` child. Text such as
  `### not a heading` or `**literal**` entered by the user must remain visible
  exactly as typed. System messages remain literal `ChatSystemMessage` content.
- Preserve current bubble variants, tool activity ordering, saved-job/match
  cards, zero-result recovery, approval cards, run failures, and message keys.
- Links and code use Astryx Markdown’s existing sanitization/rendering. Add no
  `dangerouslySetInnerHTML`, HTML parser, or parallel Markdown implementation.
- Headings, emphasis, lists, links, and code markers must render semantically;
  raw `###`, `**`, and list syntax must not remain visible in normal assistant
  prose.
- The source-marker transform described below is presentation-only. It never
  mutates `message.content`, history payloads, reducer state, or the persisted
  assistant message.

### Strict Active-CV Evidence Projection

`frontend/src/features/chat/activeCvEvidence.ts` is the single parser, projector,
and row-level selector for `read_active_cv` evidence. Reuse `isUuidV4` and the
current JSON types; do not create another general validation framework.

A projected page is valid only when all required fields validate:

```text
attachment_id: UUID v4
extraction_version: non-empty string
source_hash: string | null
mode: section | search | chunk
returned_chars: integer in 0..12000
truncated: boolean
has_more: boolean derived from a non-null next_cursor
records: ordered list with 1..10 validated records
```

The projector reads the existing ToolResult data, strips `next_cursor` after
deriving `has_more`, and retains only the fields above plus exact record content.
Unknown top-level/record keys, arguments, storage paths, provider fields, prompts,
credentials, and stack data never enter `ClientToolActivity.resultData`. Required
field/type/vocabulary failures return `null`.

Allowed entry records are `entry | entry_match` and preserve:

```text
section_id, entry_id, ordinal, title, subtitle, date_text, location,
body, bullets, source_chunk_ordinals, optional excerpt, optional record_truncated
```

Allowed chunk records are `chunk | chunk_match` and preserve:

```text
ordinal, text, char_count, optional excerpt, optional record_truncated
```

Validate non-negative integer ordinals/counts, ordered non-negative source chunk
ordinals, string/list types, per-page result limit, and the existing character
ceiling. Preserve record and string content exactly after validation; do not
summarize, fetch, normalize, or concatenate evidence in the projection.

Chain this projector after the existing save-job and match-job projectors in
`history.projectToolResultData`. The generic `ClientToolActivity.resultData`
shape and reducer remain unchanged. Stream `tool_status` continues to carry
`resultData=null`; only terminal history hydration supplies evidence.

### Evidence Binding And Citation Placement

Use `toolsForAssistantDisplay` as the only association between an assistant row
and durable tools. `activeCvEvidenceForTools` selects successful pages in durable
tool order and returns a bundle only when:

1. each selected tool is named exactly `read_active_cv`, has
   `status='completed'`, has no `errorCode`, and has valid projected data;
2. at least one page contains a record; and
3. all selected successful pages agree on `attachment_id`,
   `extraction_version`, and `source_hash` (including consistent legacy `null`).

Ignore failed/malformed read pages when another valid page exists, but suppress
the entire citation when valid pages claim different attachment revisions. Never
borrow evidence from a neighboring user turn, another assistant host, current
global sidebar selection, or the latest message.

Render exactly one Astryx `Citation` labeled **Nguồn** for the bundle, even when
the Agent made multiple consistent page reads. Use Astryx Markdown’s `sources`
and custom citation component seam so the citation follows the first safe direct-
answer paragraph. The renderer may insert one reserved citation marker into an
ephemeral display copy after that paragraph; it must never insert inside a code
fence, link, list marker, or persisted text. If no safe lead paragraph exists,
render the citation immediately after the Markdown body as the deterministic
fallback.

The Citation activation must prevent anchor navigation and open the local source
dialog with normal keyboard behavior. The reserved marker itself must never be
visible or copied into the conversation. During live streaming no evidence exists
and no citation is shown; the current terminal `history/rehydrate` adds it after
durable truth arrives, and initial/restart history renders it identically.

### Source Dialog

`ActiveCvSourceDialog` owns only local open/closed state and read-only
presentation. Build it from the pinned Astryx `Dialog`, `DialogHeader`, `Layout`,
`LayoutContent`, `LayoutFooter`, `Button`, `VStack`/`HStack`, `Text`, and
supporting metadata components; do not hand-build modal/focus/layout primitives.

- Title the dialog **Nguồn từ CV** and explain briefly that it contains the
  evidence available to the Agent for this answer.
- Group multiple pages by durable tool-call order and preserve every record’s
  original order. Do not deduplicate records because repeated records are part of
  what the Agent actually received.
- Entry records show available title/subtitle/date/location, exact body, bullets,
  and source chunk ordinals in readable labels. Search entries also show the exact
  returned excerpt.
- Chunk records show the exact returned text and ordinal. Search chunks also show
  the exact returned excerpt.
- Show a clear partial-evidence notice when any page has `truncated`, `has_more`,
  or any record has `record_truncated`. Never imply the Agent read omitted pages.
- Do not display source hashes, cursors, internal tool names, JSON, or IDs as the
  primary user-facing copy. Stable IDs may be exposed only as subdued location
  metadata when needed to distinguish records.
- The dialog makes zero evidence/chunk API calls. It renders only the projected
  durable ToolResult records, so the displayed source cannot silently differ from
  what the Agent read.
- **Mở CV gốc** reuses `getRetainedCvUrl(attachment_id)` and
  `window.open(getRetainedCvUrl(attachment_id), '_blank',
  'noopener,noreferrer')`. It uses the
  attachment recorded for the answer, not whichever CV is active later.
- The close control, Escape behavior, title focus, trigger-focus restoration,
  scroll containment, and keyboard activation follow Astryx Dialog/Citation
  behavior and receive focused component tests.

### Strict JD Confirmation Projection And Card

`frontend/src/features/chat/jobSaveConfirmation.ts` is the sole parser for this
approval kind. It may also expose a focused selector built on the existing
stream/history row-association rules; do not duplicate the backward scan in a
second component. A valid projection requires:

```text
kind: exactly job_save_confirmation
allowed_actions: exactly save_job and cancel_save_job, with no duplicates
card.tool_name: exactly save_job
card.tool_call_id: non-empty string
card.source: exactly current_message
card.text_length: integer in 1..1000000
card.preview: object with only title, company, skills
  title/company: null or non-empty string <= 160 characters
  skills: 0..5 non-empty strings <= 80 characters each
```

Reject missing, extra, wrong-type, over-limit, or forbidden projection data
rather than coercing it into a card. In particular, any `text`, `raw_content`,
`message_id`, `user_message_id`, `url`, `source_url`, hash, arguments, prompt,
credential, provider, or stack key at the projection/card/preview levels makes
the JD card invalid. A malformed JD projection falls back to the existing safe
generic interrupted notice and keeps the composer locked; it never reveals JSON
or enables an unvalidated action.

Create `JobSaveConfirmationCard` from the pinned Astryx `Card`, `MetadataList`,
`Badge`, `ButtonGroup`, and `Button` APIs. It renders:

- Heading **Đã nhận diện nội dung JD**.
- Optional title/company metadata and at most five skill badges; omit missing
  preview rows without inventing placeholders.
- Bounded length metadata and the exact sentence **JD này chưa được lưu. Bạn có
  muốn lưu JD này không?**
- Exactly **Lưu JD** and **Không lưu**, in that order, mapped to `save_job` and
  `cancel_save_job` through the existing `POST /api/chat/runs/{run_id}/resume`
  transport.

Generalize the current approval callback type only enough to carry the two
approved action unions. Reuse `approvalLockedRunIds`, `approvalInFlightRef`,
composer lock, error handling, durable rehydrate, and first-accepted-click logic;
do not add a JD store or a second in-flight set. Both buttons disable before the
resume request starts. Preserve the existing ambiguous-transport behavior: surface
the safe error and keep both buttons locked for that page lifetime; a refresh may
recover the still-durable pending card when the backend did not accept the action.
Never auto-unlock and risk a second action. Backend replay/no-op remains
authoritative after acceptance or terminal completion.

While a valid JD confirmation owns the row, the existing tool activity may label
its running `save_job` item **Review JD** through a presentation-only override.
After save/cancel terminal hydration it returns to normal **Save Job** wording.
Cancellation renders neither `SavedJobCard` nor saved-JD invalidation. Confirmed
success continues through the existing strict save result projection/card. Fire
the existing `onSavedJobsInvalidated` composition callback exactly once only
after terminal rehydrate proves that this run's validated `save_job` ToolResult
has `sqlite_committed=true`; a terminal event or button action alone is not proof.
Never dispatch evaluate. Initial history, refresh/restart, and live SSE must
choose the same single card host and preserve exact-one action rendering.

### Ownership And Invariants

- `agent/prompt.py` owns response and passive-JD model policy;
  `services/job_save_confirmation.py` owns pure fixed recognition/opt-out,
  durable initiating-message resolution, bounded pending projection, and no-save
  result construction; `agent/graph.py` owns only the narrow post-decision repair
  and ToolResult-derived narration; `schemas/jobs.py` owns the strict input/
  preview/cancellation models; and `tools/jobs.py` owns `execute_tool`, interrupt,
  resume branch orchestration, and delegation to existing ingestion.
- The active-CV reader, runner/checkpoint owner, repositories, API routes,
  database/Alembic, public SSE event envelope, ingestion/extraction services, and
  evaluation owners remain unchanged unless a failing prerequisite proves the
  assumption false and portfolio review approves another amendment.
- `tool_executions.result_json` remains the sole durable owner of evidence.
  `chat_messages.content` remains the sole durable assistant text; neither copies
  the other.
- `history.ts` owns durable frontend projection. `activeCvEvidence.ts` owns the
  exact active-CV evidence vocabulary. `AssistantResponse.tsx` owns Markdown and
  citation placement. `ActiveCvSourceDialog.tsx` owns modal presentation.
  `ChatMessageRow.tsx` only composes these owners with existing cards/actions.
- `jobSaveConfirmation.ts` owns the JD pending-projection vocabulary and reuses
  row association; `JobSaveConfirmationCard.tsx` owns read-only preview/actions;
  `ChatPage.tsx` continues to own the one resume/in-flight lock. No JD store,
  separate reducer, second endpoint, or local-storage recovery is introduced.
- There is one citation and one dialog instance per evidence-backed assistant row.
  There is one JD confirmation card per interrupted passive-JD run. No global
  dialog/source store, sidebar coupling, or additional network cache is introduced.
- Historical answers keep the attachment revision used at answer time. An active
  CV switch does not relabel the source; later deletion follows the existing
  CV-owned run/tool cascade and naturally removes unavailable evidence on the next
  durable hydration.
- Raw JD text remains only in the initiating durable user message and, after
  confirmed acceptance, the existing Job ingestion store. Preview fields and
  pending state never become Job facts. Cancel adds no Job/evaluation/graph row;
  confirmed save adds no evaluation row or evaluate request.
- One Agent, one decision node, one ToolNode, seven registered tools, exact tool
  statuses, replay identity, and `TOOL_LOOP_LIMIT=6` are invariant.

## Implementation

1. Run the focused current backend/frontend baseline. Reproduce one raw-Markdown
   assistant answer, one active-CV fact/count answer with no source control, and
   one passive synthetic JD that currently saves or receives an ordinary answer
   without confirmation. Search all prompt/decision/tool/schema/repository,
   interrupt/resume, ToolResult/history, row/card, retained-file, and installed
   Astryx callers before editing; record the reusable owners named above.
2. Add failing prompt tests for direct-answer-first structure, simple/no-heading
   behavior, bounded longer structure, active-CV factual/count evidence, genuine
   count pagination, no invented source links, passive-JD current-message tool
   use, opt-outs, direct paths, unsaved wording, and no automatic evaluation.
   Update the existing prompt owner while retaining every Plan 11 truthfulness
   rule.
3. Add failing pure-recognition and decision tests for English/Vietnamese marker
   and line/character
   boundaries, opt-outs including exact-name-plus-opt-out, sole URL, ambiguity,
   positive exact-name precedence, first-model
   tool success, one repaired sole current-message call, refusal fallback, and
   unchanged topology/pass counting. Implement the smallest pure predicates and
   focused recognition owner plus one bounded branch in the current decision node;
   reuse the same opt-out predicate as the current-message tool precondition.
4. Add failing schema/tool tests for the exact three-way source union, preview
   bounds/forbidden extras, argument-summary redaction, missing run/message,
   wrong-role/empty-message rejection, and server-side
   `run_id → user_message_id → chat message` resolution. Extend existing job
   schema/tool owners; instantiate
   no provider or ingestion dependency before valid confirmation.
5. Add failing interrupt/resume integration tests proving the current-message tool
   stays one `running` execution, pending/SSE card keys are exact, raw source and
   message IDs are absent, and Job/extractor/embedding/evaluation/Neo4j call counts
   are zero before action. Implement `allow_running_reentry`, projection, and the
   pre-mutation interrupt by following the accepted profile-tool pattern.
6. Add failing branch/replay tests. Prove **Lưu JD** reloads and ingests the exact
   durable initiating message once, preserves `created|returned|retried`, and makes
   zero evaluation calls; prove **Không lưu** returns the exact cancellation
   ToolResult with zero mutation/dependency calls; prove duplicate/terminal resume
   is idempotent and direct URL/text behavior is unchanged. Implement only the two
   resume branches and adjust ToolResult-derived cancellation narration.
7. Add failing active-CV parser/projection tests for every valid record kind,
   boundary, allowlist, malformed field, forbidden extra, failed tool, empty
   record set, multiple consistent pages, and mismatched revisions. Implement the
   focused evidence module and chain it into the existing history projection.
8. Add failing assistant/user rendering tests. Extract `AssistantResponse`, render
   assistant-only compact streaming Astryx Markdown, and keep user/system content
   literal without changing cards or message ownership.
9. Add failing citation-placement and dialog tests. Implement the presentation-
   only lead-paragraph marker, exact-one **Nguồn** control, exact evidence
   rendering, partial notice, accessible open/close/focus, and reused retained-PDF
   action.
10. Add failing JD pending-projection/card tests for every field boundary,
    forbidden key, optional preview, exact Vietnamese copy/order, keyboard action,
    one-click disable, **Review JD** activity, malformed fallback, cancellation
    without SavedJobCard/invalidation, and confirmed success with the existing
    SavedJobCard plus exactly-one committed-only saved-JD invalidation. Implement
    the focused parser/card and minimally generalize the shared row selector,
    resume callback, and terminal rehydrate proof.
11. Add combined history/reducer/chat-page tests proving stream-null evidence shows
    no citation, terminal rehydrate adds durable CV evidence, live and restart
    hydration restore exactly one JD card and composer lock, both resume actions
    use the same endpoint, and neither evidence nor pending approval crosses a
    message/run boundary.
12. Run existing chat, named-`save_job`, direct ingestion/dedupe, saved-job,
    match/evaluation, zero-result, profile approval, and active-CV regression
    suites. Fix the root owner of any regression rather than adding a compatibility
    renderer, duplicate parser, second state path, or broadened recognizer.
13. Run full backend/frontend static/test/build gates and the shared plan
    validator. Inspect the diff for migrations, endpoint/dependency/tool-count
    drift, raw payload exposure, auto-evaluation, and owner size.
14. Start the documented local desktop stack and execute the synthetic readable-
    response, active-CV source, English-JD cancel, Vietnamese-JD save/dedupe, and
    refresh/restart checklist at `localhost:5173`. Inspect frontend network/state,
    sanitized backend logs, SQLite/Neo4j counts, and separate Agent-decision versus
    JD extraction/embedding provider-call evidence. Record
    desktop evidence only; do not add or run a mobile-layout acceptance pass.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Prompt, recognition, topology | `Set-Location backend; py -3.13 -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_job_save_confirmation.py tests/unit/test_agent_graph.py -q` | Direct-answer/CV/JD policy passes; opt-out-over-exact-name and positive-exact-name-over-passive precedence, marker/threshold/source/projection boundaries, tool-precondition reuse, one passive repair/refusal, cancellation narration, one Agent/decision/ToolNode, seven tools, and six passes are proven. |
| Backend JD tool and resume | `Set-Location backend; py -3.13 -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_api.py -q` | Three-way input validation, exact durable source lookup, strict redacted pending/SSE projection, no pre-confirmation calls, same-execution save/cancel, branch call counts, replay, direct URL/text compatibility, dedupe, and zero auto-evaluation pass. |
| Backend active-CV source | `Set-Location backend; py -3.13 -m pytest tests/integration/test_active_cv_tool.py -q` | Existing bounded active-only reads, record order, caps, cursors, and durable ToolResult shape remain green. |
| Frontend source projection | `Set-Location frontend; npm test -- --run src/test/active-cv-source.test.tsx src/test/sse-reducer.test.ts` | Exact record allowlists, bounds, forbidden-key stripping, completed-success gating, revision consistency, stream-null, terminal hydration, and restart behavior pass. |
| Frontend response rendering | `Set-Location frontend; npm test -- --run src/test/assistant-response.test.tsx src/test/chat-page.test.tsx` | Assistant Markdown is semantic/compact/stream-aware; user/system text is literal; one adjacent source control and accessible dialog behave correctly. |
| Frontend JD confirmation | `Set-Location frontend; npm test -- --run src/test/job-save-confirmation.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts` | Strict projection/forbidden keys, optional preview, exact two actions, one-click lock, **Review JD**, live/restart host, cancel-without-card/invalidation, committed-success SavedJobCard plus exactly-one invalidation, and no evaluate dispatch pass. |
| Existing chat/card regressions | `Set-Location frontend; npm test -- --run src/test/empty-match-card.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/approval-card.test.tsx` | Tool activity, saved/match/zero-result cards, profile approval actions, and assistant-row ordering remain unchanged. |
| Backend full/static | `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental; py -3.13 -m pytest -q` | All backend gates pass with fakes, no real provider call, and no topology/public-endpoint/database-schema change. |
| Frontend full/build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Full frontend suite and production build pass with the pinned dependency set. |
| Local services | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180`; then `Invoke-RestMethod http://127.0.0.1:8000/api/health` | Frontend, backend, SQLite/filesystem, and Neo4j are available on documented local ports. |
| Desktop simple/long answers | At `http://localhost:5173`, send one simple question and one longer non-CV question that needs grouping. | The direct answer comes first; simple response has no heading; longer response has at most three clear groups; raw Markdown symbols are not visible. |
| Desktop active-CV source | With a synthetic active CV containing a known Certificates section, ask `Tôi có mấy Certificate?`, then activate **Nguồn**. | Agent performs bounded `read_active_cv`, answers the exact count directly, one **Nguồn** appears with the lead answer, and the dialog shows exactly the returned records in order. |
| Desktop original/history | Click **Mở CV gốc**, close/reopen the dialog, refresh the page, and load the same turn from history. | The retained PDF URL uses the evidence attachment; focus returns correctly; citation and exact evidence survive durable hydration/restart without an extra chunk fetch. |
| Negative provenance | Exercise fixtures for failed/malformed/empty/non-CV tools and valid pages with conflicting revisions. | No **Nguồn** control appears and no source marker or false provenance is visible. |
| Desktop JD cancel/restart | Record Job/evaluation/graph/provider counts, paste an obvious synthetic English JD, inspect the card/network, refresh before deciding, then choose **Không lưu**. | The same bounded card returns after restart; no raw JD/message ID appears outside the user bubble; no side-effect call occurs before or after cancel; one durable execution completes with `committed=false`; no SavedJobCard appears. |
| Desktop JD save/dedupe | Paste an obvious synthetic Vietnamese JD, choose **Lưu JD**, then repeat the same passive paste and confirm again. | Each paste requires its own card; each accepted run ingests its own exact durable message once; first outcome creates and second returns the same Job; Job count is one; no evaluate request/row occurs; normal SavedJobCard/outcome wording appears. |
| Desktop direct/opt-out | Send a sole public test URL, one explicit direct `save_job` text request, one JD plus `không lưu`, and ambiguous long prose. | URL/direct paths remain compatible without the passive card; opt-out creates no card/mutation; ambiguous prose is not forced into confirmation. |
| Scope hygiene | `git diff --check`; inspect `git status --short`, changed paths, package manifests, migrations, public route lists, registry size, and source file lengths. | Only the authorized Version 1.9/Plan 11/Plan 12/spec planning edits and Plan 12 implementation owners are present; no task file, dependency, migration, endpoint, duplicate store/parser, second Agent/node/tool, auto-evaluation, raw-data leak, security/mobile work, real data, secret, or oversized owner exists. |
| Plan structure | `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` | Plans are contiguous through `Plan_12.md`; Plan 11 hands off normally and only Plan 12 is terminal. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Plans 1-9 | One-Agent chat, durable run/message/tool ownership, interrupt/resume, direct URL/text Job ingestion, active-CV retrieval, retained-PDF route, and Astryx UI baseline | Existing replay, ingestion, approval, and bounded-read contracts remain authoritative. |
| Plans 10-11 | Current assistant-row cards, generic resume/lock, terminal history rehydrate, saved-JD/CV reliability, bounded exact-name `save_job` repair, and desktop product baseline | This phase composes those owners without reopening their repair scope or weakening direct-save truthfulness. |
| Current user authorization | Approved hybrid response layout, adjacent active-CV source control, exact evidence dialog/original-CV action, automatic passive-JD review followed by **Lưu JD**/**Không lưu**, no automatic evaluation, and desktop-only acceptance | These selected behaviors and exclusions are fixed for Plan 12. |
| Approved design | `docs/superpowers/specs/2026-07-18-pasted-jd-save-confirmation-design.md` | Exact durable source binding, bounded card, pre-mutation interrupt, two resume branches, and explicit-path compatibility are normative. |
| Master amendment | Version 1.9 Sections 6.4, 11.2, 12, 13.4, 14.2, 15.7, 20, 24, and Phase 10 | The user authorized this amendment; no public endpoint, database schema, stack, deployment, tool-count, or evaluation-flow change is permitted. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Fresh portfolio review | Master Version 1.9, synchronized Plan 11 successor handoff, approved design spec, and revised `Plan_12.md` | Shared structural validator passes and the complete Plans 1-12 portfolio can be reviewed independently. |
| `task-writing-agent` after portfolio approval | `docs/tasks/task_12.md` derived from this plan | One authoritative task maps P12-RSP-01 through P12-RSP-02, P12-CV-01 through P12-CV-05, P12-JD-01 through P12-JD-05, and P12-REG-01 to implementation and A1/A2/A3 evidence. |
| Future A1 implementation | Prompt/decision/source/interrupt/card plus Markdown/CV projection/citation/dialog and test sequence | Implementation reuses exact owners and the verification matrix without adding endpoints, stores, tools, migrations, evaluations, or dependencies. |
| Future A2/A3 review | Independent functional/scope boundary | Evidence proves readable output, truthful CV provenance, exact source display, recognition boundaries, zero pre-confirmation mutation, correct save/cancel/replay, no auto-evaluation, and regression safety. |

## Completion Contract

Plan 12 is complete only when assistant messages render readable semantic Markdown
while user/system text remains literal; Agent responses lead with the answer and
use minimal grouping; factual active-CV answers obtain bounded body evidence; and
one **Nguồn** citation appears only beside an answer backed by successful durable
`read_active_cv` records. The dialog must show exactly what the Agent read, disclose
partial evidence, open the same retained CV, survive terminal history hydration and
restart, and perform no hidden evidence fetch. Failed, malformed, empty, unrelated,
or revision-conflicting tool state must show no citation.

A recognizable passive English/Vietnamese JD must create one strict unsaved
preview card unless a clear opt-out applies. Before **Lưu JD**, the same durable
`save_job` execution must be `running` and Job/extraction/embedding/evaluation/
Neo4j call counts must remain zero. Save must reload and ingest the exact
initiating durable user message once, preserve existing dedupe/result cards, and
make no evaluation request. **Không lưu** must complete with `committed=false`,
`outcome='cancelled'`, no SavedJobCard, and zero mutation. Malformed cards,
duplicate actions, terminal replay, restart/history, direct URL/text save,
profile approval, and **Lưu JD & đánh giá lại** must remain truthful and safe.

Focused and full backend/frontend gates, Compose health, desktop-only acceptance,
scope hygiene, and the contiguous plan validator must pass while one Agent, one
decision node, one ToolNode, seven tools, six passes, current public APIs/database
schema/dependencies, and durable ownership remain unchanged. Security and mobile
work stay excluded. This planning artifact creates no task or product code; the
required next action is a fresh full portfolio review before task writing or
execution.
