# CV Profiles and Multi-Conversation Design

**Date:** 2026-07-23
**Status:** Approved design
**Scope:** Replace the singleton CV/profile/conversation model with one durable profile per CV and multiple independently selectable conversations per profile.

## 1. Context

JobAgent currently has one singleton `candidate_profile` row, one singleton
`job_preferences` row, and one singleton conversation whose ID is `main`.
Messages, Agent runs, history hydration, context loading, and frontend state all
assume that singleton. CV attachments may be retained as active or archived,
but only the active attachment owns the approved profile used by chat and
matching.

The new product model is:

```text
CV Attachment 1 ── 1 Profile
Profile       1 ── N Conversation
Conversation  1 ── N ChatMessage
ChatMessage   1 ── 0..1 AgentRun
AgentRun      1 ── N ToolExecution
Profile       1 ── N JobEvaluation
Saved Job remains global
```

Each profile retains its extracted CV artifacts. Selecting a profile must be a
local read/selection operation and must never re-run extraction, embeddings, or
provider calls.

## 2. Goals

- Create one durable profile for every approved CV.
- Preserve multiple profiles and allow exactly one to be selected at a time.
- Store the complete extracted CV document, chunks, source hash, extraction
  version, candidate profile, location, and skills for each profile.
- Allow each profile to own multiple independent conversations.
- Allow users to create, select, and permanently delete conversations after an
  explicit confirmation.
- Allow profile rename, selection, explicit re-extraction, and permanent
  deletion.
- Display the persisted candidate name, location, and extracted skills as
  Astryx-based profile metadata and tags.
- Keep Saved Jobs global while making evaluation results profile-specific.
- Preserve existing Agent topology, tool count, SSE vocabulary, deterministic
  scoring, explicit approval, and explicit evaluation behavior.

## 3. Non-goals

- No multi-user accounts, authentication, authorization, or cloud sync.
- No automatic CV extraction when selecting an existing profile.
- No automatic Job evaluation when selecting or re-extracting a profile.
- No LLM-generated conversation titles.
- No soft delete, trash, restore, or retention window for conversations or
  profiles.
- No compatibility migration for existing user data; the rollout uses an
  explicit destructive reset.
- No custom design system alongside Astryx.

## 4. Data model

### 4.1 Profiles

Replace the singleton approved-profile model with a multi-row `profiles` table:

| Field | Contract |
| --- | --- |
| `id` | UUID primary key |
| `attachment_id` | Unique, non-null FK to one retained CV attachment |
| `display_name` | User-editable, non-empty, bounded string |
| `profile_json` | Complete validated extracted candidate profile |
| `location` | Nullable normalized display projection from `profile_json` |
| `extraction_version` | Non-empty version of the persisted extraction |
| `source_hash` | Hash of the persisted canonical CV source |
| `state` | `ready` or `deleting`; deletion failures remain retryable |
| `created_at` / `updated_at` | Aware timestamps |
| `last_opened_at` | Updated when the profile is selected |

`attachment_id` is the one-to-one CV constraint. Profile JSON remains the
authoritative candidate fact document. `location` is a query/display
projection and must equal the validated profile value. Skill tags are read
from validated persisted profile skills; the frontend does not infer or
normalize them.

The validated candidate-profile contract gains optional `full_name` and
`location` fields. The document/profile extractor may populate them only from
directly supported CV text; it must return null instead of inferring missing
identity or location. Phone numbers, email addresses, street addresses, and
other contact details are neither required nor exposed by the profile-list
contract. The semantic guard covers these two fields before persistence.

The default `display_name` is the extracted candidate name. If no usable name
exists, it falls back to the sanitized original CV filename. Renaming changes
only `display_name`, never extracted facts or source identity.

### 4.2 Persisted extraction ownership

The existing CV document and chunk tables remain authoritative and become
profile-owned through the profile's unique attachment:

- `cv_documents` stores the approved structured document, extraction version,
  and source hash.
- `attachment_text_chunks` stores ordered source chunks.
- `profiles.profile_json` stores approved candidate facts and skills.
- The retained PDF remains in attachment storage.

Selecting a profile reads these records only. It makes zero provider,
extraction, embedding, filesystem-write, or scoring calls.

Explicit **Re-extract CV** operates on the same profile and attachment. It
stages a new document/profile revision outside SQLite transactions, requires
the existing approval flow, then atomically replaces the persisted extraction
and profile facts. Conversations remain attached to the profile. Existing
durable chat results remain historical; evidence whose stored `source_hash`
does not equal the current profile revision is presented as stale rather than
silently rebound.

### 4.3 Profile preferences and active selection

Replace singleton job preferences with `profile_preferences`:

| Field | Contract |
| --- | --- |
| `profile_id` | Primary key and FK to `profiles.id` |
| `preferences_json` | Existing validated preference document |
| timestamps | Aware creation/update timestamps |

Add a singleton `workspace_state` row:

| Field | Contract |
| --- | --- |
| `id` | Fixed `main` singleton key |
| `active_profile_id` | Nullable FK to `profiles.id` |
| `updated_at` | Selection timestamp |

Only `workspace_state` identifies the active profile. Attachment `active` and
`archived` states continue to mirror that selection for compatibility with
retained-file and CV lifecycle services: the selected profile's attachment is
`active`, and other ready profile attachments are `archived`.

### 4.4 Conversations

Replace the singleton `conversation` row with multi-row `conversations`:

| Field | Contract |
| --- | --- |
| `id` | UUID primary key |
| `profile_id` | Non-null FK to `profiles.id` |
| `title` | Bounded deterministic display title |
| `created_at` / `updated_at` | Aware timestamps |
| `last_opened_at` | Updated on explicit selection |

`chat_messages.conversation_id` references a real conversation; it is no
longer forced to `main`. A conversation title starts as **Chat mới** and is
updated from the first non-empty user message by whitespace normalization and
bounded truncation. No provider call is used.

The selected conversation for a profile is the non-deleting conversation with
the greatest `last_opened_at`, then `updated_at`, then stable ID. Selecting an
older conversation updates `last_opened_at`, so switching away and back opens
the user's last selection. Every new profile receives one empty conversation
after approval.

Run and tool ownership remains normalized:

```text
ToolExecution → AgentRun → initiating ChatMessage → Conversation → Profile
```

`source_attachment_id` remains an evidence/deletion field but is not the
primary conversation ownership mechanism.

### 4.5 Saved Jobs and evaluations

Saved Jobs remain global and are visible from every profile. Job evaluations
gain explicit `profile_id` ownership in addition to the exact attachment,
profile/preferences revision, and scoring context already stored. Results from
one profile are never shown as current for another profile.

Deleting a profile deletes its evaluations but never deletes a Saved Job.

## 5. Backend services and API

### 5.1 Profile APIs

```text
GET    /api/profiles
GET    /api/profiles/{profile_id}
PATCH  /api/profiles/{profile_id}
POST   /api/profiles/{profile_id}/activate
DELETE /api/profiles/{profile_id}
```

- List/detail responses expose safe profile metadata, CV filename/state,
  location, bounded ordered skill tags, current extraction revision, and
  whether the profile is active.
- `PATCH` changes only `display_name` and rejects extra fields.
- Activation derives all context from the stored profile. It never accepts
  profile JSON, attachment ownership, or extracted text from the client.
- Delete delegates to a retryable profile-deletion coordinator.

CV upload/extraction keeps the current staged-draft and explicit Save Profile
flow. Successful first approval creates a new profile rather than replacing a
singleton profile, persists its extraction artifacts, creates preferences and
the first conversation, and activates it.

### 5.2 Conversation APIs

```text
GET    /api/profiles/{profile_id}/conversations
POST   /api/profiles/{profile_id}/conversations
POST   /api/conversations/{conversation_id}/select
DELETE /api/conversations/{conversation_id}

GET    /api/conversations/{conversation_id}/history
POST   /api/conversations/{conversation_id}/turns
POST   /api/chat/runs/{run_id}/resume
```

- Conversation list ordering is newest `last_opened_at` first with bounded
  cursor pagination.
- Create returns an empty selected conversation.
- Select updates `last_opened_at` only after ownership and activity checks.
- History is strictly scoped to the requested conversation.
- A turn receives only `conversation_id`; the backend resolves the owning
  profile and CV context from SQLite.
- Resume resolves the run's conversation/profile through durable ownership and
  rejects mismatches or deleted owners.
- SSE event names and payloads remain unchanged.

Deleting the last conversation leaves the profile with no durable messages and
returns a replacement empty conversation ID created in the same service
operation. The frontend immediately renders that blank conversation.

### 5.3 Switching profiles

Activation follows this sequence:

1. Load the target ready profile and current workspace state.
2. Reject if any current conversation has a `running` or `interrupted` run.
3. In one short SQLite transaction, archive the previous attachment, activate
   the target attachment, set `active_profile_id`, and update
   `last_opened_at`.
4. Return the target profile and its most recently selected conversation.
5. After commit, refresh or verify the derived Neo4j profile/CV projection from
   persisted data only.

The graph stores profile/CV branches keyed by profile identity. Matching and
evaluation queries include the active profile ID, preventing cross-profile
Candidate/CV reads. Switching performs no provider work. A graph refresh
failure preserves SQLite selection and returns safe rebuild guidance.

### 5.4 Activity gate

Profile switch, conversation switch, conversation creation, conversation
deletion, and profile deletion are rejected while a run is `running` or
`interrupted`. The frontend disables these actions, but the backend is the
authority. This avoids moving the visible context away from an SSE stream or
approval that still belongs to another conversation.

Stable errors include:

- `PROFILE_NOT_FOUND`
- `PROFILE_NOT_READY`
- `PROFILE_SWITCH_BLOCKED`
- `PROFILE_DELETE_BLOCKED`
- `CONVERSATION_NOT_FOUND`
- `CONVERSATION_PROFILE_MISMATCH`
- `CONVERSATION_SWITCH_BLOCKED`
- `CONVERSATION_DELETE_BLOCKED`

Errors use safe summaries and never include CV text, message content, provider
payloads, filesystem paths, or secrets.

## 6. Deletion semantics

### 6.1 Conversation deletion

The UI must show an Astryx confirmation dialog naming the conversation and
stating that deletion cannot be undone. On confirmation, the backend:

1. Rejects a running/interrupted owner.
2. Resolves all run IDs for the conversation.
3. Deletes their LangGraph checkpoints outside the application transaction.
4. In one transaction, deletes conversation messages; run/tool rows disappear
   through owned cascades.
5. Creates and returns an empty replacement if this was the last conversation.

Deletion is permanent. It does not touch the profile, CV, extraction artifacts,
preferences, evaluations, or global Saved Jobs.

### 6.2 Profile deletion

The UI must show an Astryx confirmation dialog naming the profile/CV and
stating that all its conversations will be permanently removed. The retryable
coordinator:

1. Rejects running/interrupted conversations.
2. Marks the profile and attachment `deleting`.
3. Deletes all owned checkpoints.
4. Removes the retained file and exact profile/CV graph branch.
5. In the final SQLite transaction, selects the most recently opened remaining
   ready profile when the deleted profile was active (or clears
   `active_profile_id` when none remains), then deletes conversations,
   messages, runs, tools, preferences, CV documents/chunks, profile-specific
   evaluations, the profile, and its attachment.

External cleanup failure leaves a retryable `deleting` profile and never
reports false success. Global Saved Jobs and unrelated profiles remain intact.

## 7. Frontend composition with Astryx

Astryx is mandatory for all new UI. Implementation must inspect the installed
Astryx 0.1.4 CLI documentation before choosing component imports or props.
Existing components and design tokens are reused; no parallel visual system is
introduced.

The sidebar has two coordinated levels:

1. **Profile list**
   - Candidate display name with active selection state.
   - Sanitized CV filename and persisted location.
   - Bounded skill tags; overflow is represented as `+N`.
   - Rename, explicit re-extract, and delete actions in an Astryx menu/dialog.

2. **Conversation list for the selected profile**
   - **Chat mới** action.
   - Deterministic title and last activity time.
   - Selection state and permanent-delete action.
   - Astryx confirmation dialog with accessible name and focus return.

The chat view remains the sole owner of SSE/reducer state. Profile and
conversation selection live above it in App composition and cause a keyed
history reset, not a second chat store. While the chat reducer is connecting,
streaming, or awaiting approval, profile/conversation actions are disabled.

On mobile, the same profile and conversation lists render in the Astryx
navigation drawer. Keyboard navigation, focus visibility, dialog focus trap,
Escape handling, and focus restoration follow Astryx behavior.

Empty states cover:

- No profiles: prompt to upload a CV.
- Profile with no messages: blank selected conversation with composer.
- Profile extraction unavailable/deleting: disable chat and show a safe status.
- No location or skills: explicit neutral metadata fallback, never fabricated
  tags.

## 8. Data flow

### 8.1 First profile creation

```text
Upload PDF
  → staged attachment
  → extract document/chunks/profile once
  → durable draft
  → user approves Save Profile
  → persist profile + extraction + preferences + first conversation
  → activate profile
  → project persisted branch to Neo4j
```

### 8.2 Returning to a profile

```text
Select profile
  → activity gate
  → SQLite selection transaction
  → load persisted profile/document/chunks
  → select most recently opened conversation
  → hydrate its history
```

This path has zero extraction, LLM, embedding, or scoring calls.

### 8.3 New chat

```text
Chat mới
  → activity gate
  → create/select empty conversation
  → user sends first message
  → derive bounded title locally
  → run Agent with owning profile context
  → persist and stream through existing SSE reducer
```

## 9. Destructive rollout

The user selected a clean start. Existing CVs, profiles, preferences, chats,
Saved Jobs, evaluations, retained files, checkpoints, and Neo4j data are not
migrated.

The release procedure must:

1. Warn that the operation permanently deletes all current application data.
2. Stop the Compose stack.
3. Remove the application and Neo4j named volumes.
4. Rebuild/start the stack so Alembic creates and upgrades the empty database
   through the new schema revision.
5. Verify that no retained files or graph records from the prior workspace
   remain.

The schema migration still supports an empty database running the full migration
chain. Documentation must not imply that legacy user rows are transformed.

## 10. Testing and acceptance

### Backend

- Schema constraints enforce one profile per attachment and conversation
  ownership.
- Profile activation selects exact persisted data and records zero provider,
  extraction, embedding, or scoring calls.
- Context/history cannot cross profile or conversation boundaries.
- Reload returns the active profile and last selected conversation.
- First-message title derivation is deterministic and bounded.
- Running/interrupted gates reject switch/create/delete operations.
- Conversation deletion removes checkpoints and owned durable rows only.
- Profile deletion removes all owned resources and evaluations while retaining
  global Saved Jobs and unrelated profiles.
- Re-extraction replaces the persisted profile revision while preserving
  conversations and marking old evidence stale.
- Graph reads and matching are scoped by profile identity.
- Migration tests validate the new schema from an empty database.

### Frontend

- Profile cards display persisted name, filename, location, and skill tags.
- Rename changes only display metadata.
- Switching profiles/chat lists resets and hydrates the correct reducer state.
- **Chat mới** creates one conversation and handles double clicks.
- Conversation and profile delete require named confirmation dialogs.
- Cancel performs no mutation; confirm performs one request.
- Deleting the current/last conversation selects the correct replacement.
- Streaming/approval locks every profile/conversation mutation control.
- Astryx keyboard, focus, Escape, mobile drawer, tag overflow, and empty states
  are covered.

### Integrated gates

- Full backend Pytest, Ruff, and Mypy.
- Full frontend Vitest, ESLint, TypeScript, and production build.
- Alembic upgrade on a fresh reset database.
- Docker Compose config/build/health.
- Browser smoke test for profile creation, switching, chat creation/selection,
  confirm deletion, reload persistence, and zero visible cross-profile history.

## 11. Acceptance summary

The design is complete when a user can maintain multiple CV-backed profiles,
switch instantly between persisted extractions, see attractive Astryx metadata
tags, maintain multiple isolated chats per profile, and permanently delete a
chat or profile only after confirmation. No selection action may trigger CV
extraction, and no operation may expose or mutate another profile's chat or
evaluation state.
