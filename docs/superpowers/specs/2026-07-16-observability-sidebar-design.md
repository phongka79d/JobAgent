# Observability Sidebar Design

## Objective

Give the single local user a read-only view of prior CV uploads, agent runs,
LLM-input chunk previews, and the derived JobAgent Neo4j graph without changing
the chat, tool, profile-approval, or graph-rebuild workflows.

## User Experience

The existing left sidebar remains the entry point for CV/profile state and gains
an inspector with these tabs:

| Tab | Default content | Detail behavior |
|---|---|---|
| Overview | Active profile and active CV summary | Existing actions remain available. |
| CV history | Prior uploads with processing state and metadata | A retained CV may be opened or downloaded. |
| LLM chunks | Attachment-scoped chunk list with fixed previews | A user expands one chunk to fetch and view its full text. |
| Neo4j graph | Bounded Candidate, Job, and Skill graph snapshot | Node and relationship details remain read-only. |
| Agent runs | Historical runs, tool calls, terminal status, and safe error codes | A row reveals only its structured execution details. |

The sidebar has explicit `expanded` and `collapsed` states. In collapsed state it
preserves a keyboard-accessible open control and compact active-profile/CV status.
It must work at narrow mobile widths without hiding the chat composer or trapping
focus.

## Architecture

Add an observability read-model boundary on the backend. It owns pagination,
identifier validation, output limits, safe error summaries, and the join between
SQLite source-of-truth records and a bounded Neo4j-derived snapshot. It must not
be called by the agent graph or mutate SQLite, uploaded files, Neo4j, or chat
history.

The frontend uses a dedicated typed API client and sidebar-local tab state. It
loads each tab only when selected, caches successfully loaded pages by query,
and keeps independent loading, empty, and error states. The chat SSE reducer and
its durable-history reconciliation remain unchanged.

## Data Contracts

| Resource | Returned data | Forbidden data |
|---|---|---|
| CV history | Attachment ID, filename, MIME type, size, timestamps, abbreviated hash, lifecycle status, retained-file availability | PDF bytes, filesystem paths |
| Chunk list/detail | Attachment ID, ordinal, character/token estimate, bounded preview; full text only for a selected authorized chunk | Raw PDF bytes, provider request metadata, secrets |
| Agent runs | Run ID, timestamps, terminal status, tool name/status/duration, typed safe code/summary, related attachment/job IDs | Checkpoints, prompts, stack traces, provider headers |
| Graph snapshot | Bounded JobAgent Candidate/Job/Skill node labels, safe display properties, relationship types, graph freshness state | Arbitrary Cypher, unrelated labels, embeddings, credentials |

Collection endpoints use bounded `limit` and opaque cursor pagination. Detail
endpoints validate the selected attachment, chunk, or run against the single
local user scope. A missing file, Neo4j outage, or stale graph produces a typed
safe UI state rather than an internal exception payload.

## Safety And Privacy

- The sidebar remains a local single-user inspection feature; it does not add
  authentication, tenancy, sharing, or public exposure.
- Full chunk text is opt-in per expanded row. Preview length is fixed and never
  treated as an executable prompt.
- The graph endpoint is read-only and never exposes an arbitrary query surface.
- Existing retention and deletion ownership for SQLite attachments and Neo4j
  derived data remains unchanged.

## Verification

- Backend tests cover pagination, identifier validation, output redaction,
  retained/missing attachment behavior, typed Neo4j unavailable/stale states,
  and non-mutation of source/derived stores.
- Frontend tests cover tab lazy loading, cache behavior, collapsed/expanded
  accessibility, preview-to-detail expansion, empty/loading/error states, and
  mobile layout.
- Direct FE smoke uploads multiple synthetic CVs, processes at least one, views
  a retained CV, expands a chunk, inspects historic runs, and checks graph
  fallback behavior.

## Planning Impact

This is a material product, API, and frontend capability change. It requires an
explicit amendment to `docs/plans/Master_plan.md`, a canonicalization of the
legacy `Plan_1.md` through `Plan_7.md` portfolio required by the shared validator,
an updated handoff in `Plan_7.md`, and a new canonical `Plan_8.md`.
