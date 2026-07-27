# JobAgent Product UX and Trust Repair Design

**Date:** 2026-07-27
**Status:** Approved design; written specification awaiting user review
**Scope:** Repair the user-facing workspace, CV lifecycle, tailored-CV workflow,
saved-Job presentation, chat trust signals, artifact delivery, accessibility,
and responsive layout without replacing the current React/Astryx or FastAPI
architecture.

## 1. Context

A fresh frontend-only audit at `http://localhost:5173` exercised profiles,
conversations, saved Jobs, deterministic match results, active-CV evidence,
tailored-CV creation and revision, CV Manager, downloads, and the existing
technical panels. The audit found that the main tailored-CV workspace swap now
works: opening a tailored CV replaces the chat workspace and **Back to chat**
restores chat. The remaining problems are broader product-trust and usability
failures rather than one isolated layout defect.

The highest-impact observed behaviors were:

- returning to JobAgent after a source-download navigation could show one
  profile as active while rendering another profile's conversations and chat;
- CV re-extraction created synthetic English user messages, including an
  attachment UUID, and used the chat interrupt flow for a product action;
- profile approval asked the user to review a proposal without consistently
  showing the proposed data;
- AI and manual tailoring could create immutable versions whose content was
  equal to the parent, while grounding failures exposed only a generic message;
- CV Manager's generic **Delete** affordance could lead to whole-profile
  deletion rather than deletion of the selected CV;
- `.tex` navigation could replace the JobAgent tab with a browser-blocked page,
  while PDF preview and download semantics were inconsistent;
- generated PDFs repeated section headings already present as item titles;
- raw UUIDs, floating-point scores, internal component names, chunk/token data,
  Neo4j details, and Agent-run codes were visible in the normal product UI;
- English and Vietnamese product copy was mixed throughout the same flows; and
- session/Job/conversation labels and multi-column layout made normal objects
  difficult to distinguish.

The repository already has the correct high-level ownership model: one
`useProfileWorkspaceState`, one `useSavedJobsState`, one
`useCvTailoringState`, one chat reducer/SSE owner, source-grounded tailoring,
immutable versions, retained CV files, and explicit profile approval. This
design keeps those owners and changes the contracts at their existing seams.

## 2. Authority and contract relationship

This design is a substantial corrective increment over the implemented
multi-profile and Plan 17 tailoring baseline. It preserves the stable
architecture in:

- `docs/superpowers/specs/2026-07-23-cv-profile-conversation-design.md`;
- `docs/superpowers/specs/2026-07-26-cv-tailoring-latex-design.md`;
- `docs/plans/Plan_17.md`; and
- the root `README.md` runtime ownership description.

It intentionally amends four user-visible Plan 17 choices:

1. A later AI/manual revision that is byte-for-byte equal at the validated
   structured-content level is a successful `no_change` outcome, not a new
   immutable version.
2. PDF preview and PDF download are separate actions; source download is an
   advanced action.
3. The technical observability panels are no longer part of the product
   frontend.
4. CV re-extraction is a direct profile lifecycle workflow, not a synthetic
   chat turn.

Initial tailoring session generation still creates Version 1 and its artifacts
even when its content is equal to the approved baseline. Version 1 is the first
durable derivative artifact; `no_change` applies only to later mutations with a
non-null parent version.

## 3. Goals

- Never render conversation, saved-Job, or tailored-CV state from a profile
  other than the server-authoritative active profile.
- Re-extract an active or archived CV without creating user-visible or durable
  synthetic chat messages.
- Show a recoverable, typed profile review before approval and keep approved
  profile/CV truth unchanged until explicit approval.
- Avoid duplicate tailored versions and artifact compilation when content did
  not change.
- Turn grounding failures into privacy-safe, field-level recovery guidance.
- Make destructive action labels match the exact resource they delete.
- Reduce the main navigation to the three user tasks: Overview, Saved Jobs, and
  Tailored CVs.
- Keep CV lifecycle management available through progressive disclosure from
  Overview.
- Remove developer diagnostics and internal identifiers from the frontend.
- Standardize all application chrome and product copy in English while
  preserving source CV/JD text and technical skill names as stored.
- Make preview/download behavior honest and keep every failed download inside
  JobAgent.
- Produce PDFs without redundant source-owned item titles that duplicate their
  section heading.
- Preserve accessibility, narrow-viewport behavior, durable recovery, source
  grounding, and existing backend data authority.

## 4. Non-goals

- No frontend rewrite, router, global state library, i18n library, or second
  design system.
- No new authentication, authorization, multi-user, cloud-sync, worker, queue,
  or Compose service.
- No removal of backend observability APIs or operational diagnostics.
- No change to saved-Job evaluation math, embeddings, matching order, approved
  CV/JD source truth, or Neo4j authority boundaries.
- No arbitrary direct editing of approved profile facts from the tailored-CV
  editor.
- No arbitrary LaTeX editor, template upload, provider-generated LaTeX, or
  compile-on-read behavior.
- No automatic retry of a grounding failure with the same instruction.
- No general promise that arbitrary freeform model prose is factually perfect.
  The enforceable mutation path is the grounded Tailoring Coordinator and
  mutation success is rendered only from durable results.
- No deletion of backend run/chunk/graph data merely because their normal-user
  frontend panels are removed.

## 5. Locked product decisions

The following decisions were approved in conversation:

- Deliver all three audit groups in one implementation plan with independently
  testable milestones.
- Keep the current architecture and apply a contract-first full-stack repair.
- A later tailoring no-op does not create a version.
- Expose separate **Preview PDF** and **Download PDF** actions; place `.tex`
  under an advanced disclosure and download it without leaving the app.
- Remove LLM chunks, Neo4j graph, and Agent runs entirely from the frontend.
- Use English for all product UI copy.
- Move CV re-extraction out of chat into a direct CV Manager workflow with
  progress, review diff, and Save/Discard.
- CV Manager never deletes a CV owned by an active or archived profile because
  the current data model requires every profile to retain exactly one CV.
  Whole-profile deletion is available only from the Profile menu. Direct CV
  deletion is limited to genuinely unowned staged/failed attachments.
- **Edit Profile Information** opens the direct Re-extract/Profile Review
  workflow.
- Grounding failures identify the section, item/field, and a friendly reason,
  with **View source**, **Undo change**, and **Try again** recovery actions.
- Use the simplified navigation **Overview → Saved Jobs → Tailored CVs**.
- Expose CV Manager through an Overview **Manage CVs** action rather than a
  fourth primary navigation item.

## 6. Architecture overview

The existing ownership graph remains:

```text
App
├── useProfileWorkspaceState   # active profile + selected conversation
├── useSavedJobsState          # one active-profile-scoped saved-Job owner
├── useCvTailoringState        # one active-profile-scoped tailoring owner
├── ChatPage/chatReducer       # one conversation/SSE owner
└── main workspace             # chat or tailored-CV editor
```

This design adds bounded units rather than replacement state:

```text
browser pageshow
  -> workspace rehydrate
  -> server active profile + owned conversation
  -> scoped Saved Jobs/Tailoring reset
  -> render ChatPage only after ownership matches

Manage CVs
  -> ProfileReextractionCoordinator
  -> existing extraction + profile/document draft services
  -> safe review projection
  -> explicit approve or discard

Tailoring mutation
  -> existing guard / fixed Tailoring Agent
  -> canonical parent equality check
     -> changed: render, compile, promote, CAS version
     -> no_change: terminal success, no files/version
     -> invalid: bounded safe issues, preserve local draft
```

No new persistent state owner is introduced. Existing singleton
`profile_drafts('current')` and attachment-owned `cv_document_drafts` remain the
durable re-extraction review state.

## 7. Workspace consistency and browser restoration

### 7.1 State contract

`ProfileWorkspaceState` gains an explicit lifecycle:

```ts
type WorkspacePhase = 'rehydrating' | 'ready' | 'error';
```

The workspace is renderable only when all of the following are true:

- `phase === 'ready'`;
- `activeProfileId` belongs to the loaded profile list or is null;
- a non-null selected conversation belongs to `activeProfileId`; and
- the conversation list contains no row owned by another profile.

The reducer must fail closed when a server response violates those couplings.
It never retains old conversations after active-profile identity changes.

### 7.2 Initial load and `pageshow`

The existing initial `reload()` remains. A narrowly scoped lifecycle hook beside
`workspaceState.ts` listens for `pageshow`. When the page is restored from the
back-forward cache, it starts authoritative rehydration:

1. increment request generation and abort/ignore older requests;
2. set phase to `rehydrating` and clear selected conversation/conversation rows;
3. fetch profiles and server-authoritative active profile;
4. fetch conversations for exactly that profile;
5. validate ownership and publish one ready state; and
6. leave the prior state unavailable if either request fails.

The hook does not encode profile or conversation identity into a URL and does
not create a second navigation model.

### 7.3 App composition

`App` renders a workspace loading/error state instead of `ChatPage` while
rehydrating. `ChatPage` is keyed by both profile and conversation identity, not
conversation ID alone. A profile-scope change also:

- returns the main workspace to chat;
- closes any old-profile CV manager/review surface;
- lets `useSavedJobsState` and `useCvTailoringState` clear through their existing
  profile scope keys; and
- prevents an old editor/session promise from reopening after the change.

## 8. Direct CV re-extraction and profile review

### 8.1 Ownership

A new backend `ProfileReextractionCoordinator` owns direct re-extraction. It
uses the existing:

- CV reprocess precondition checks;
- PDF/document extraction services;
- profile projection and semantic guards;
- `profile_drafts('current')` and `cv_document_drafts` publication;
- `commit_approved_draft` transaction; and
- Candidate/CV graph synchronization after approval.

It does not invoke the Main Agent, create a `ChatMessage`, create a chat
`AgentRun`, create a `ToolExecution`, or add a conversation row.

### 8.2 Public API

The existing route retains its URL but receives new direct semantics:

```text
POST   /api/profiles/{profile_id}/reextract
GET    /api/profiles/{profile_id}/reextract-draft
POST   /api/profiles/{profile_id}/reextract-draft/approve
DELETE /api/profiles/{profile_id}/reextract-draft
```

`POST .../reextract` streams a feature-specific bounded event vocabulary:

```text
reextract_progress
reextract_review_ready
reextract_failed
```

Progress stages are a closed set:

```text
validating_source
extracting_document
projecting_profile
publishing_review
```

Each event contains only a stage, safe English message, and optional profile
identity needed to reconcile the request. It contains no source text, provider
payload, file path, attachment UUID in display copy, prompt, or stack trace.

### 8.3 Durable review projection

`GET .../reextract-draft` returns a strict `ProfileReextractReview` containing:

- profile ID and stable draft revision;
- current and proposed public profile summaries;
- changed scalar fields from an allowlist;
- skills added and removed;
- experience, education, language, and certification count changes;
- extraction confidence change when available; and
- whether approval and discard are currently allowed.

The projection may contain the user's validated public profile values, but not
raw PDF text, chunks, fact IDs, CVDocument JSON, source paths, or provider data.

### 8.4 Approval, discard, conflict, and cancellation

- Approval validates the draft still targets the requested ready profile and
  calls `commit_approved_draft`. The approved profile/CV changes only inside
  that existing transaction.
- Discard deletes the matching profile draft and document draft in one short
  transaction. It does not change the approved profile, attachment state,
  conversations, saved Jobs, evaluations, or graph.
- A published current draft is a durable workspace gate. Profile switching,
  another upload, another re-extraction, and profile deletion are blocked until
  approval or discard.
- Cancellation before atomic draft publication leaves no new draft and preserves
  approved truth. If the client disconnects after publication, the review is
  recovered with `GET .../reextract-draft`.
- A failure preserves the prior approved profile/CV and any previously valid
  matching draft. The UI offers **Retry** or **Discard draft** according to the
  authoritative server state.

The existing chat-based initial upload and first profile approval remain in
scope as an existing workflow. Their approval card must show the actual bounded
proposed profile summary rather than an empty fallback, but initial upload is
not migrated to the new direct coordinator in this increment.

## 9. Tailored-CV mutation outcomes

### 9.1 Canonical equality

The backend is authoritative for no-op detection. Parent and candidate content
are parsed through the same strict `TailoredCVContent` schema and compared using
their canonical JSON-mode structured representation. Renderer output, PDF bytes,
timestamps, provenance ordering, and UI formatting do not participate in the
comparison.

The comparison happens after the AI patch is applied and validated, or after a
manual request is parsed, but before rendering, compilation, staging, file
promotion, and version CAS.

### 9.2 Outcomes

Later manual and AI mutations use this discriminated result:

```text
version_created
no_change
grounding_failed
conflict
compile_failed
```

`version_created` preserves the current immutable-version behavior.

`no_change`:

- completes the AI run successfully when one exists;
- leaves `latest_version_number`, session update time, version rows, and artifact
  files unchanged;
- returns the unchanged parent version identity;
- produces the English UI message **AI found no source-supported changes to
  apply.** or **There are no changes to save.**; and
- is recoverable after a stream disconnect by comparing the known parent with
  the fetched completed session detail.

The frontend also performs a local canonical equality check to disable an
obvious manual no-op, but the backend check remains mandatory.

### 9.3 Transport

Manual mutation returns a typed JSON response with `outcome` and either the new
version or unchanged parent identity.

AI mutation keeps the existing SSE event names. Its terminal completion payload
adds a strict safe `outcome` projection. No additional stream or state owner is
created.

## 10. Grounding issue projection and recovery

### 10.1 Safe server mapping

Internal `GroundingIssue(code, path)` values are never sent directly to the
browser. The coordinator maps allowlisted issue codes and validated paths to at
most ten `TailoringUserIssue` values:

```ts
type TailoringUserIssue = {
  section_id: string;
  section_heading: string;
  item_index: number | null;
  field: 'title' | 'subtitle' | 'date' | 'location' | 'body' |
         'bullet' | 'attribute' | 'section';
  reason: 'not_in_source' | 'belongs_to_another_section' |
          'structure_changed' | 'required_source_missing' |
          'unsupported_value';
};
```

If an internal issue cannot be mapped safely, the server returns one generic
section-level issue. It never exposes rejected text, fact IDs, guard paths,
provider output, prompts, CV/JD source, or technical exception names.

AI failure persists only this bounded projection through the existing durable
activity mechanism so session detail recovery can expose the same safe issues
without a new table. Manual failure returns the same issue shape in the HTTP
error response and preserves the local draft.

### 10.2 Editor behavior

The editor keeps the selected parent content alongside the draft. For each
issue it:

- marks the matching field and connects the message with `aria-describedby`;
- **View source** expands and focuses the existing evidence disclosure for that
  section;
- **Undo change** restores the affected field/item from the selected parent;
  and
- **Try again** reopens the scoped AI dialog with the previous instruction so
  the user can revise it. It never automatically submits the identical request.

## 11. Product information architecture

### 11.1 Primary navigation

The primary product navigation is exactly:

```text
Overview
Saved Jobs
Tailored CVs
```

Overview continues to own profiles, conversations, active-CV summary, and CV
upload. It adds **Manage CVs**, which opens the CV lifecycle surface as
progressive disclosure instead of a fourth primary tab.

### 11.2 Frontend technical-panel removal

LLM chunks, Neo4j graph, and Agent runs are removed from:

- navigation and tab contracts;
- frontend composition and lazy-load effects;
- frontend API/state/types used only by those panels;
- product CSS; and
- frontend tests whose sole purpose is those deleted screens.

CV Manager is first separated from the observability feature into its own
bounded feature module. Shared generic utilities are retained only when a
remaining product feature uses them. Backend observability endpoints, services,
repositories, tests, and operations remain unchanged.

### 11.3 Manage CVs action matrix

The selected-CV action matrix is explicit:

| CV state | Allowed actions |
| --- | --- |
| Active | Preview, Download, Re-extract |
| Archived | Preview, Download, Make active/Re-extract |
| Unowned staged/failed attachment | Retry when supported, or Delete CV |
| Deleting | No duplicate action; show progress/retry state |

A profile-owned active or archived CV cannot be deleted through CV Manager.
The direct `/api/cvs/{id}` delete path is exposed only for attachments that the
server confirms are unowned and staged/failed. Whole-profile deletion is
available only from the Profile menu and is labeled **Delete profile and all
data**. CV Manager never calls `workspace.deleteProfile`, and the frontend does
not infer deletion eligibility from display state alone.

**Edit Profile Information** in the tailored editor opens Manage CVs directly
at the Re-extract/Profile Review workflow. It does not merely return to the chat
composer and does not enable direct mutation of approved header facts.

## 12. Naming and display contracts

### 12.1 Saved Job display label

A backend-owned pure presentation helper derives one safe display label in this
order:

1. `title · company` when both exist;
2. title or company when one exists;
3. the first bounded meaningful sentence of the validated JD summary; or
4. `Untitled saved job · <saved date>`.

UUIDs remain transport identity and may appear only in developer/API evidence,
not as the primary product label. Saved-Job list, detail, delete/re-extract
dialogs, match cards, and tailoring entry points use the same projection.

### 12.2 Tailoring session label

New Job-backed sessions snapshot the derived saved-Job display label in the
existing `job_label_json`. The schema adds an optional bounded `display_label`
for backward compatibility, so no migration is needed. An old session without
that field derives its label from title/company/instruction and finally
`Untitled tailored CV · <created date>`.

The editor header, session list, delete dialog, and download filenames use the
same helper. They do not maintain separate fallback logic.

### 12.3 Conversation title

The first non-empty ordinary user message updates a `New chat` title through
the existing backend deterministic normalization/truncation path. Upload,
re-extraction, approval, and other system actions neither create a synthetic
conversation title nor overwrite a user-derived title.

## 13. Saved Jobs, matching, chat activity, and mutation trust

### 13.1 Match presentation

- Percentages are rounded consistently for list, detail, and chat cards.
- Raw floating-point values, UUIDs, internal score keys, and
  `Unavailable components` prose are not rendered.
- **Why this score** groups matched, related, and missing skills.
- Unavailable dimensions use English explanations such as **Not enough CV/JD
  information to score experience**.
- The quality multiplier is shown only with a short explanation of how it
  reduces confidence in incomplete JD extraction.

Scoring data and formula remain unchanged.

### 13.2 Explicit CV-tailoring intent

The Main Agent prompt and decision tests require explicit requests to edit,
tailor, or generate a CV to call `create_tailored_cv`, including the existing
instruction-only path when no saved Job is selected. Freeform assistant text is
not a substitute for a created version.

JD requirements absent from the approved CV are described as gaps. They are
never stated as candidate experience or inserted into a derivative version.
The existing Tailoring Guard remains the final mutation authority.

State-changing success UI is rendered only from a successful durable ToolResult
or direct API result. The implementation does not add a broad natural-language
claim classifier; prompt and decision-path regressions cover the bounded
tailoring intent, while persistence remains deterministically guarded.

### 13.3 Activity presentation

Chat activity uses a user-facing mapping owned in one presentation module.
Internal tool symbols, raw error codes, and engineering timing rows are not
rendered. The disclosure label changes between **View activity** and
**Hide activity**. Durable tool/run records are unchanged.

## 14. Artifact delivery and PDF rendering

### 14.1 Preview and download

- The embedded PDF viewer continues to use the inline PDF endpoint.
- **Preview PDF** opens the inline PDF in a new tab when requested.
- **Download PDF** fetches the authenticated/owned artifact as a blob and
  triggers a browser download with a safe product filename.
- **Advanced → Download LaTeX source** uses the same fetch-to-blob helper.
- A failed fetch shows a bounded English error and never changes the JobAgent
  location.

The backend keeps safe content types, ownership checks, and filenames. It does
not compile on read.

### 14.2 Redundant headings

The renderer always emits the source-owned section heading. For each item, it
normalizes Unicode case and whitespace for comparison only. An item title that
equals its containing section heading is omitted from presentation. The stored
structured content and provenance remain unchanged.

Names such as a job title, project title, certificate, institution, or award are
still rendered when they do not equal the section heading. Empty rendered
sections remain governed by the current source-section preservation contract.

Renderer unit tests and a synthetic real-compiler/PDF acceptance case prove
that SUMMARY, EDUCATION, TECHNICAL SKILLS, and PROJECTS do not repeat their
heading while genuine item titles remain.

## 15. Layout and responsive behavior

- Opening a tailored-CV editor automatically reduces the secondary sidebar to
  the navigation rail and records its prior selected tab/collapse state.
- Editor context, session label, version, currentness, and actions live in the
  editor header rather than another persistent column.
- Desktop uses one content pane plus one PDF preview pane.
- Narrow/mobile view uses accessible **Content** and **Preview** tabs.
- Manage CVs uses a side panel on desktop and a full-screen drawer on narrow
  viewports.
- Only the content region and native PDF viewer own scrolling. Session lists,
  JD detail, editor, and app shell do not create competing nested viewport
  scrollbars.
- Returning to chat or a list restores the previous sidebar selection/collapse
  state.

No raw pixel/color values or alternate design system are introduced. Astryx
components/tokens and `frontend/AGENTS.md` discovery rules remain mandatory.

## 16. English copy and accessibility

The product has no locale selector in this increment. English copy is grouped
in feature-local `copy.ts` modules for profile/workspace, CV Manager, Saved Jobs,
Tailoring, and Chat. Source CV/JD content, names, and technical skill labels are
not translated.

Dates use one explicit English locale instead of the browser default.

Accessibility requirements:

- every dialog/alert dialog has an accessible name, focus trap, Escape behavior,
  and focus restoration;
- no button is nested inside another button;
- icon-only controls have visible tooltip and `aria-label`;
- disabled actions expose a reason;
- loading, no-change, success, and error states use appropriate live regions;
- field issues use `aria-describedby` and focusable recovery actions;
- list rows and tabs expose correct selected/expanded state;
- reduced motion disables nonessential pulsing/transition behavior; and
- keyboard order covers the primary navigation, Manage CVs, editor, evidence,
  preview/download, dialogs, and recovery actions.

## 17. Error and recovery policy

| Failure | Required user-visible behavior | Preserved state |
| --- | --- | --- |
| Workspace rehydrate failure | Block stale content; show Retry | Last server state remains unrendered |
| Re-extract pre-publication failure | Safe English summary; Retry | Approved profile/CV and prior valid draft |
| Re-extract review conflict | Reload current review | Approved profile/CV |
| Re-extract approval transaction failure | Keep review; Retry/Discard | Approved profile/CV |
| Graph sync failure after approval | Report committed profile plus rebuild guidance | Committed SQLite/profile/CV truth |
| Tailoring no-op | Informational message | Parent version and artifacts |
| Tailoring grounding failure | Field issues and recovery actions | Local draft and parent version/PDF |
| Tailoring parent conflict | Preserve draft; Reload latest | Local draft and latest server version |
| Compile failure | Safe message | Local draft and prior PDF |
| Artifact download failure | Toast/banner; remain in app | Editor/session state |
| Eligible CV delete failure | Keep row and retry state | Selected unowned CV; every profile remains unchanged |

Refresh actions retain prior successful list/detail content until a validated
replacement response arrives. No error path clears a valid resource into a
blank panel.

## 18. Privacy and security boundaries

- No new frontend surface displays chunks, contacts outside their owned profile
  review/header, graph identifiers, Agent-run identifiers, tool payloads, or raw
  provider output.
- Grounding projections are bounded allowlisted metadata, not source excerpts.
- Re-extract progress and errors contain no attachment UUID in display copy.
- Artifact downloads keep server ownership validation and never accept a client
  filesystem path.
- LaTeX remains fixed, escaped, and compiled without shell escape.
- Technical backend endpoints remain loopback-local under the existing runtime
  contract; removing their frontend panels is not an authorization boundary.
- Tests and documentation use only tracked synthetic fixtures and sanitized
  values.

## 19. File and unit boundaries

The implementation plan must preserve one owner per rule and is expected to use
these boundaries:

- `frontend/src/features/profile/workspaceState.ts`: authoritative profile and
  conversation state plus rehydration lifecycle.
- A small workspace lifecycle hook beside `workspaceState.ts`: `pageshow`
  subscription only.
- `frontend/src/app/App.tsx`: composition, scope reset, main-workspace and
  sidebar-rail transition.
- A new `frontend/src/features/cv-manager/` module: moved typed CV list/detail,
  actions, re-extraction review, API, state, dialogs, and copy.
- Existing profile sidebar/overview modules: simplified primary navigation and
  Manage CVs entry.
- Existing Saved Jobs modules plus one shared display-label projection contract.
- Existing Tailoring state/editor plus feature-local copy and issue/no-op types.
- One shared frontend artifact download helper under `frontend/src/lib/api/`.
- A new backend profile-reextraction schema/service module using existing
  extraction/draft/approval owners.
- Existing profile API routes with direct re-extraction semantics and review
  endpoints.
- Existing tailoring coordinator/guard/API schemas and renderer at their current
  convergence seams.
- Existing Main Agent prompt/decision tests for bounded CV-tailoring intent.

Debug-only frontend modules are deleted only after CV Manager dependencies are
extracted. Backend observability files are not modified for removal.

No database table or migration is planned. If implementation discovery proves
that a durable invariant cannot be met with existing profile/document drafts,
Agent activities, and tailoring metadata, work stops before adding a migration
and requests explicit scope approval.

## 20. Delivery milestones

This remains one implementation plan with dependency-ordered milestones:

1. Workspace ownership and browser restoration.
2. Product navigation, CV Manager extraction, technical-panel removal, and
   English copy foundation.
3. Direct profile re-extraction/review/approve/discard.
4. Tailoring no-op and safe grounding issue contracts.
5. Artifact actions, renderer correction, editor layout, and responsive states.
6. Saved-Job/match labels, chat-tailoring intent, conversation titles, and
   activity presentation.
7. Full accessibility, regression, build, and browser acceptance.

Each milestone starts with a failing focused test, makes the minimum production
change, passes focused gates, and receives its own intentional commit. Public
frontend/backend contract changes land together in the same milestone.

## 21. Testing strategy

### 21.1 Frontend

- Workspace reducer/hook tests for `pageshow`, request ordering, ownership
  mismatch, rehydrate failure, and profile switch during in-flight requests.
- App integration proving ChatPage never renders old-profile history and is
  remounted exactly once after coherent rehydration.
- Product navigation tests proving only three primary items exist.
- Manage CVs action-matrix, direct re-extract progress/recovery/diff,
  approve/discard, deletion-scope, and focus tests.
- Tailoring state tests for manual/AI `no_change`, disconnected recovery,
  field issues, undo, source focus, prompt preservation, and no duplicate
  version selection.
- Artifact tests proving preview opens separately and downloads never change
  `window.location`.
- Saved-Job/match/chat activity and conversation-title presentation tests.
- Desktop split, narrow tabs/drawer, sidebar restoration, keyboard, live-region,
  reduced-motion, and no-overlap tests.
- Static source tests proving removed technical tabs/components are not imported
  and no second workspace/saved-Job/tailoring state owner exists.

### 21.2 Backend

- Direct re-extraction preconditions, zero-chat-side-effect assertions, staged
  publication, disconnect recovery, safe review projection, approval, discard,
  conflict, and prior-truth preservation.
- Assertions that direct re-extraction creates zero `ChatMessage`, chat
  `AgentRun`, `ToolExecution`, and conversation rows.
- Tailoring equality tests for manual/AI no-op with zero compile, storage,
  version-insert, and CAS calls; initial Version 1 remains mandatory.
- Safe issue mapping/bounds/privacy tests and durable AI issue recovery through
  existing activity storage.
- Renderer golden tests for redundant-heading suppression and genuine-title
  preservation, plus synthetic real `pdflatex` evidence.
- Saved-Job display-label projection and tailoring snapshot compatibility tests.
- Main Agent prompt/decision regressions for explicit CV-tailoring intent and
  unsupported JD skills as gaps.
- Existing profile approval, tailoring, matching, evaluation, graph, deletion,
  migration, and full-suite regressions.

### 21.3 Browser acceptance

Using only synthetic data:

- switch between two profiles, navigate to an artifact, return with browser
  Back, and prove no cross-profile content is rendered;
- create/select/delete conversations and verify deterministic English titles;
- open Manage CVs, re-extract, review a diff, discard, retry, and approve;
- prove no synthetic technical message appears in chat;
- create a tailored CV, exercise an AI no-op and manual no-op, then create a real
  grounded version;
- force a safe grounding failure and use all three recovery actions;
- preview/download PDF and download advanced `.tex` without leaving JobAgent;
- inspect a generated PDF with non-repeated headings;
- verify that only an unowned staged/failed CV can be deleted directly and that
  profile-owned CV deletion is available only through profile deletion;
- inspect Saved Jobs and match explanations without UUID/raw-score/internal
  component text;
- verify only Overview, Saved Jobs, and Tailored CVs remain;
- repeat critical workflows at desktop and narrow viewport with keyboard-only
  navigation.

## 22. Acceptance criteria

The increment is complete only when:

1. Chat, Saved Jobs, and Tailored CVs never render data owned by a profile other
   than the server-authoritative active profile.
2. Returning through browser Back/Forward rehydrates before rendering profile
   content.
3. CV re-extraction creates no chat message, chat Agent run, Tool execution, or
   conversation title side effect.
4. Re-extraction review survives refresh/disconnect after draft publication and
   approved truth changes only after explicit approval.
5. Discard removes only the matching drafts and leaves approved/profile-related
   product data unchanged.
6. Later manual/AI no-op mutations create no version, TeX, PDF, or session
   revision change.
7. Initial tailoring still creates Version 1 and downloadable artifacts.
8. Grounding errors identify safe section/item/field/reason metadata and expose
   all approved recovery actions without leaking private/internal data.
9. CV Manager can directly delete only a server-confirmed unowned staged/failed
   attachment. Active and archived profile-owned CVs expose no direct delete;
   whole-profile deletion is available only from the Profile menu with exact
   English scope copy.
10. The frontend primary navigation contains exactly Overview, Saved Jobs, and
    Tailored CVs; no technical panel remains reachable or bundled as product UI.
11. Application chrome is English, while source CV/JD content is preserved.
12. Saved Jobs, tailoring sessions, dialogs, and match cards use human-readable
    labels rather than UUIDs.
13. Match presentation contains no raw float or internal component names and
    agrees with unchanged backend scoring.
14. Preview and download actions are distinct; PDF and LaTeX downloads never
    navigate the JobAgent tab.
15. Generated PDFs do not repeat an item title equal to its section heading and
    still render real item titles.
16. Tailored editor desktop/narrow layouts have coherent scroll ownership,
    keyboard order, focus recovery, and reduced-motion behavior.
17. Full backend/frontend/static/build/browser/diff gates pass with synthetic
    data and no unrelated dependency, migration, service, or architecture
    change.

## 23. Planning constraints

The implementation plan must:

- be one document, as explicitly requested, but retain the milestone ordering
  in this design;
- give exact files, test names, commands, expected failures/passes, and commit
  boundaries;
- use TDD for each behavior change;
- preserve the current user-owned dirty working-tree changes unless separately
  resolved;
- avoid speculative abstractions or unrelated cleanup;
- repeat full code snippets where the implementing engineer needs them; and
- stop for approval rather than inventing a database migration, dependency, or
  public-contract expansion outside this specification.
