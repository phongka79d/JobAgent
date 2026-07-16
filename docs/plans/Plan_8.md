# Plan_8: Read-Only Observability Sidebar

## Objective

Deliver a read-only, responsive left-sidebar inspector that lets the single local
user review immutable archived CV uploads and retained PDFs, the exact persisted
CV text chunks sent to profile extraction, historical Agent runs, and a bounded
derived Neo4j Candidate/Job/Skill snapshot without changing the existing chat,
tool, approval, matching, or graph-rebuild workflows.

## Source of Truth

- `docs/plans/Master_plan.md`: `## 2. Locked Product Scope`, `## 6. SQLite Database Contract`, `## 8. Neo4j Derived Model`, `## 10. CV Ingestion and Approval Flow`, `## 12. Agent Architecture`, `## 14. Public FastAPI Boundary`, `## 15. Frontend UX Plan`, `## 24. Local Testing Strategy`, and `### Phase 7 - Read-only observability sidebar`.
- `docs/superpowers/specs/2026-07-16-observability-sidebar-design.md`: approved user-experience, privacy, API, and verification decisions.
- `docs/plans/Plan_7.md`: released local-stack baseline and handoff boundary.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| M8-01 | 2.1 in scope; 6.4 and 10 CV flow | Immutable archived-CV history, retained-file stream/unavailable behavior, and unchanged active-CV selection. | Approval, API integration, and direct FE smoke. |
| M8-02 | 6.2 `attachment_text_chunks`; 10.2 processing | Deterministic parsed-CV chunk projections persist with a migration and are linked to their attachment. | Migration, repository, and extraction transaction tests. |
| M8-03 | 14 API rules | Bounded, typed, read-only observability APIs validate IDs/cursors and redact internal data. | API contract, pagination, and redaction tests. |
| M8-04 | 8 derived model; 14 API rules | A bounded Candidate/Job/Skill graph snapshot reports healthy, stale, or unavailable state without mutation or arbitrary Cypher. | Graph adapter unit/integration tests and direct FE fallback check. |
| M8-05 | 15.1, 15.2, 15.6 | Existing sidebar supports accessible expanded/collapsed states and lazy inspector tabs. | Frontend component, accessibility, mobile-layout, and build checks. |
| M8-06 | 24 local testing strategy | Existing chat/SSE, approval, matching, and release behavior remains unaffected. | Existing regression suites plus new focused checks. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Plan_7 | Local three-service Compose baseline, release checks, and current sidebar/chat behavior | Existing frontend/backend validation commands run before and after this phase. |
| Plan_4 | Attachment, CV extraction, profile approval, and current `CvSidebar` ownership | Trace extraction and attachment callers before adding chunk persistence. |
| Plan_3 | Durable `agent_runs`, `tool_executions`, chat history, API router conventions, and SSE reducer boundary | Verify read models do not alter the chat reducer or Agent graph. |
| Plan_5 and Plan_6 | Direct Neo4j synchronization, revision/staleness behavior, and Job/Candidate/Skill labels | Reuse current graph adapters; never add a second graph model or query surface. |

## Scope

- Amend the attachment lifecycle with an Alembic migration so a replaced active CV becomes immutable `archived` history, retains its file/chunks, and can never be restored as active.
- Add an Alembic migration and typed SQLite model/repository for deterministic CV text chunks.
- Persist chunks only for successful parsed digital-PDF extraction and only in the existing approved extraction/draft-input transaction boundary.
- Add a dedicated observability read-model service, schemas, and FastAPI router for cursor-paginated CV history, retained-CV streaming, chunk list/detail, Agent-run history, and a bounded graph snapshot.
- Refactor the existing sidebar composition into focused sidebar-local components with `Overview`, `CV history`, `LLM chunks`, `Neo4j graph`, and `Agent runs` tabs.
- Support an accessible expanded/collapsed sidebar state, lazy tab fetches, per-tab cache, and independent loading, empty, stale, unavailable, and safe-error states.
- Add focused backend/frontend tests and a direct local FE smoke procedure using synthetic CVs only.

## Out of Scope

- Authentication, sharing, multi-user isolation, public exposure, profile rollback, or mutable profile/CV versioning. Archived uploads are immutable inspection records, not selectable profile versions.
- Raw PDF bytes, storage paths, source file dumps, provider prompts/headers, checkpoints, embeddings, secrets, stack traces, or tool arguments in UI/API payloads.
- Arbitrary Cypher, graph editing, graph rebuild controls, new Neo4j labels, or mutation of SQLite/Neo4j through observability routes.
- A second chat/SSE store, changes to Agent tool selection, changes to approval semantics, background workers, queues, or new third-party visualization libraries.
- Backfilling chunks for historical attachments whose parsed text was never persisted; those rows expose a typed unavailable state instead.

## Target Directory Structure

```text
backend/
  alembic/versions/<revision>_add_attachment_text_chunks.py
  app/
    api/observability.py
    graph/observability.py
    repositories/attachment_text_chunks.py
    repositories/observability.py
    schemas/observability.py
    services/observability.py
    services/profile_approval.py                   # archive former active attachment only
    services/profile_extraction.py                 # canonical chunk persistence/input only
  tests/
    unit/test_attachment_text_chunks.py
    unit/test_observability_graph.py
    integration/test_observability_api.py
frontend/src/
  app/App.tsx                                      # compose sidebar state only
  features/profile/CvSidebar.tsx                   # retain overview actions; delegate inspector composition
  features/observability/
    api.ts
    types.ts
    state.ts
    ObservabilitySidebar.tsx
    CvHistoryPanel.tsx
    ChunkPanel.tsx
    GraphPanel.tsx
    RunHistoryPanel.tsx
    observability.css
  test/observability-sidebar.test.tsx
  test/observability-api.test.ts
docs/
  acceptance/observability_sidebar_checklist.md
```

## Technical Specifications

### Persistence And Extraction

- A replacement transaction changes the previous `active` attachment to `archived`
  after profile repointing, retains its file/chunks/metadata, and marks the new row
  active. `profile_approval.py` owns this transition; no route restores or deletes
  archived rows. The migration adds the state without converting existing `staged`
  or `failed` rows; archival history begins with replacements under this contract.
- `attachment_text_chunks` uses one UUID row per `(attachment_id, ordinal)` with
  a unique constraint, source-order ordinal, full parsed text, a 240-character
  preview, character count, `ceil(char_count / 4)` token estimate, and UTC timestamp.
- The pure deterministic chunker uses `MAX_CHUNK_CHARS=1200`, `CHUNK_OVERLAP=0`,
  and paragraph then whitespace split points. It rejects empty chunks, never calls
  a provider, and emits the canonical ascending ordinal sequence.
- The profile extraction flow joins that exact sequence using `"\n\n"` and sends
  no other document text to the structured profile-extraction model. It persists
  the same rows in the successful extraction/draft-input transaction. When parse,
  chunking, model, repair, or draft validation fails, no chunk rows are written.
- Existing historical attachments without chunk rows are not backfilled. Their
  chunk-list and chunk-detail endpoints return `CHUNKS_UNAVAILABLE` with a safe
  summary and no synthetic content.

### Read-Only API Contract

All collection endpoints accept `limit` in `1..50` and an opaque cursor derived
from `(created_at, id)` or `(created_at, ordinal)`. They query `limit + 1`, return
stable chronological results with `next_cursor`, and return `422` for malformed
cursors. Cursors do not expire: a well-formed cursor after the final row returns
an empty page and `next_cursor=null`. All error payloads use stable application
codes and safe summaries.

| Endpoint | Response contract | Boundaries |
|---|---|---|
| `GET /api/observability/cvs` | attachment summaries, lifecycle status, abbreviated SHA-256, retained-file availability, and `next_cursor` | No PDF bytes or storage path. |
| `GET /api/observability/cvs/{attachment_id}/file` | validated `application/pdf` stream for an active or archived retained file | Sanitized filename only; `CV_ATTACHMENT_NOT_FOUND` or `CV_FILE_UNAVAILABLE` safe JSON errors. |
| `GET /api/observability/cvs/{attachment_id}/chunks` | ordinal, preview, char count, token estimate, and `next_cursor` | No full text in collection payload. |
| `GET /api/observability/cvs/{attachment_id}/chunks/{ordinal}` | one selected full-text chunk and its safe metadata | `404` for unknown attachment/chunk; `CHUNKS_UNAVAILABLE` for historic no-row data; no provider metadata. |
| `GET /api/observability/runs` | durable run timestamp/state, related IDs, tool status/duration, safe code/summary, and `next_cursor` | No checkpoint, prompt, stack trace, or tool arguments. |
| `GET /api/observability/graph` | `status`, bounded nodes/edges, truncation metadata, graph revision/freshness metadata, and safe summary | No arbitrary query; only Master allowlisted labels, properties, and relationship types. |

`graph.status` is exactly `ready | stale | unavailable`. `stale` represents the
existing revision-consistency failure; `unavailable` represents a graph adapter
failure. Both return an empty graph projection and safe recovery guidance. A ready
response contains at most one Candidate (`id`, `revision`), 20 Jobs (`id`, `title`,
`company`, `revision`) ordered by `id ASC`, and 40 Skills (`canonical_name`) ordered
by `canonical_name ASC`. After node selection, only `HAS_SKILL`, `REQUIRES`,
`PREFERS`, and `RELATED_TO` edges with `source_id`, `target_id`, and `type` are
serialized, sorted by `(type, source_id, target_id)`, and capped at 100. The
response always reports `nodes_truncated`, `edges_truncated`, `omitted_node_count`,
and `omitted_edge_count`. No active profile returns `ready`, an empty projection,
and `NO_ACTIVE_PROFILE`; no hidden fields are inferred by the frontend.

### Frontend State And Interaction

- Keep the existing profile/upload state in its current owner. New sidebar state
  owns only `isCollapsed`, selected tab, selected attachment, selected expanded
  chunk ordinal, per-tab page/cache, and per-tab request state.
- Default tab is `Overview`. `CV history` selects an attachment for `LLM chunks`
  and exposes Open/Download only when the safe `file_available` flag is true; the
  chunks tab presents an explicit empty selection state until one is chosen.
- Each tab fetches only when first selected or when its explicit refresh action is
  used. A successful response is cached by endpoint query; a failed request does
  not erase previous safe data.
- Render the graph with existing React/CSS primitives and a bounded semantic list
  fallback. Display truncation metadata exactly as returned; do not add a
  visualization dependency, canvas-only control surface, or client-side expansion.
- Collapse/expand uses a real button with `aria-expanded`, visible focus, Escape
  behavior for mobile overlay mode, and responsive widths that preserve the chat
  composer.

### Ownership And Safety

- `repositories/attachment_text_chunks.py` owns CRUD-like persistence limited to
  chunk rows; `repositories/observability.py` owns cross-table projections.
- `services/observability.py` owns pagination, authorization-by-single-user data
  scope, output redaction, and response assembly. `graph/observability.py` owns
  the allowlisted read-only Neo4j projection only.
- API routes are thin serializers. The Agent graph, tools, chat reducer, and graph
  rebuild command remain unchanged. `profile_approval.py` changes only the
  approved-replacement lifecycle from delete to archive, while
  `profile_extraction.py` adds the explicit canonical chunk persistence call.

## Implementation

1. Search current attachment, extraction, run/tool-execution, graph, sidebar, and
   API callers. Document the exact existing ownership boundary before edits.
2. Add the attachment archival/chunk migration, ORM/repository models, deterministic
   chunker, and transaction integration in profile approval/extraction. Add unit and
   migration coverage for one-active archival, archived-hash behavior, retained-file
   availability, canonical chunk-input identity, ordering, empty text, and historical
   no-chunk behavior.
3. Implement typed observability schemas, repositories, service, graph projection,
   and read-only API router. Reuse existing cursor, safe-error, graph revision, and
   attachment resolution patterns rather than duplicate them.
4. Add API integration tests for each endpoint, malformed and post-final cursor
   behavior, redaction, missing attachment/chunk, retained-file stream/unavailable
   state, run/tool projection, graph caps/truncation/allowlists, and `ready`,
   `stale`, `unavailable`, and no-active-profile graph states.
5. Split sidebar-only UI into focused components. Preserve current overview upload,
   replace, download, and interaction-lock behavior; add tabs, lazy fetch/cache,
   chunk expansion, semantic graph fallback, and collapse/mobile behavior.
6. Add frontend tests for API typing, initial overview, tab transitions, cache,
   empty/loading/error states, accessible collapse, chunk full-text expansion, and
   narrow layout. Run existing chat/profile/card suites to prove no regression.
7. Create the synthetic-data-only manual checklist. Run the full direct FE smoke
   with active-to-archived replacement, retained-CV open/download, one expanded
   canonical chunk, graph healthy/truncated/fallback states, mobile collapse, and
   browser-console inspection.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Migration and backend unit tests | `Set-Location backend; py -3.13 -m pytest tests/unit/test_attachment_text_chunks.py tests/unit/test_observability_graph.py -q` | Active-to-archived lifecycle, canonical chunk input, redaction, capped allowlisted graph projection, and no mutation. |
| Observability API integration | `Set-Location backend; py -3.13 -m pytest tests/integration/test_observability_api.py -q` | Cursor/post-final-page, retained-file stream/unavailable, selection, safe errors, history, graph caps/truncation, and graph-state contracts pass. |
| Existing affected backend suites | `Set-Location backend; py -3.13 -m pytest tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py -q` | Chunk persistence preserves extraction, approval, and resume behavior. |
| Backend static checks | `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` | No lint or type failures. |
| Frontend focused tests | `Set-Location frontend; npm test -- --run src/test/observability-sidebar.test.tsx src/test/observability-api.test.ts` | Tabs, cache, expansion, errors, and collapsed state pass. |
| Frontend regression and build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Full suite, lint, typecheck, and production build pass. |
| Local service smoke | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` | Frontend, backend, and Neo4j healthy. |
| Direct FE smoke | Execute `docs/acceptance/observability_sidebar_checklist.md` with synthetic CVs only. | Archived-CV history/open-download, expanded canonical chunk, runs, ready/truncated/fallback graph, mobile collapse, and console are verified. |
| Scope hygiene | `git diff --check` and review changed paths against this plan. | No real data, secrets, arbitrary graph access, or unrelated scope. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Plan_7 | Local release baseline and historical completion evidence | Existing Compose and user flows are stable before this phase. |
| Master amendment | Sections 2, 6, 14, 15, 24, and Phase 7 | Observability is a material but read-only local capability. |
| Approved design | `docs/superpowers/specs/2026-07-16-observability-sidebar-design.md` | Preview/full-text, history, graph, privacy, and sidebar decisions are fixed. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Task writing | `docs/tasks/task_8.md` derived from this plan | Task scopes map one-to-one to migration/read model/API/frontend/manual-smoke work. |
| Implementation orchestration | `plan_id: plan-8` batch contracts | A1/A2/A3 evidence follows the verification matrix above. |
| Local user | Bounded sidebar observability experience | Direct FE checklist passes without exposing prohibited data. |

## Completion Contract

Plan 8 is complete only when deterministic CV chunks are persisted safely for new
successful extractions; the read-only observability API and sidebar expose the
approved history, chunk, run, and graph views; all safe fallback/redaction and
accessibility requirements are verified; existing product flows remain green; and
the direct FE checklist proves the user can inspect the new surfaces on local
synthetic data without creating a new write path.
