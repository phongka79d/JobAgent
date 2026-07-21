# Plan_9: CV Manager And Complete Active-CV Retrieval

## Objective

Replace the implemented read-only CV History experience with a CV Manager that can
reprocess an active or archived CV through the existing approval flow, select the
approved CV as the single active source, and completely delete a non-active CV and
its owned SQLite/file/Neo4j/run data. Change CV extraction to a document-first,
bounded pipeline that retains every known and unknown section before deriving the
Candidate Profile, then give the single Agent active-only, bounded document access
without injecting the whole CV into each prompt.

## Source of Truth

- `docs/plans/Master_plan.md` Version 1.7 plus the current Section 23
  configuration contract: Sections 2, 6-8, 10, 12-15, 20-21, 23-25, and the
  Phase 8 exit gate. Master Version 2.0 preserves these five CV setting names.
- `docs/plans/Plan_8.md`: implemented deterministic chunk persistence,
  observability API, retained PDF stream, run history, graph read model, and
  successor handoff.
- `docs/superpowers/plans/2026-07-16-observability-sidebar-ui-refresh.md`:
  implemented resizable shell, vertical tab rail, compact list panels, interactive
  D3 graph, mobile drawer, frontend module split, and visual verification baseline.
- The current repository implementation is the reuse baseline. Existing service,
  repository, graph, cursor, SSE, approval, and frontend state patterns must be
  searched before any new helper is introduced.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| M9-01 | 6.2, 7.2, 10.2 | Complete ordered `CVDocument` with dynamic sections is extracted before `CandidateProfile`; Certifications and unknown headings survive. | Schema, batch/coverage, projection, and synthetic-CV tests. |
| M9-02 | 6.2-6.4, 10.3-10.5 | Active/archived reprocessing uses a separate document draft and existing approval interrupt; active selection changes only after approval. | Approval, interrupt/resume, rollback, and API integration tests. |
| M9-03 | 6.3-6.4, 10.5, 20 | Active deletion is rejected; non-active deletion removes owned relational, file, checkpoint/run/tool, chat, and graph data through a retryable lifecycle. | Deletion fault-injection and cross-store integration tests. |
| M9-04 | 8, 14.1, 21 | Neo4j projects fixed `CV`, `CVSection`, and `CVEntry` labels, graph view roots at the active CV, and deletion preserves shared Jobs/Skills. | Graph sync/delete/rebuild/observability tests. |
| M9-05 | 12-13 | Prompt context includes only a compact active outline; seventh tool `read_active_cv` enforces active-only modes, cursors, result limits, and character caps. | Prompt snapshot, authorization, pagination, and cursor invalidation tests. |
| M9-06 | 14 | Dedicated reprocess/delete routes reuse application services and preserve the existing SSE/approval contract. | Public API schema/status/idempotency tests. |
| M9-07 | 15 | CV History becomes CV Manager with active badge, Make active/Re-extract/Delete actions, confirmation, and focused cache invalidation. | Frontend interaction/accessibility/error tests. |
| M9-08 | 15.1, 15.6 | Completed observability UI refresh, proportions, colors, components, graph controls, and responsive behavior remain intact. | Existing frontend regression suite and desktop/mobile screenshots. |
| M9-09 | 20, 24 | Failure paths preserve the prior active CV, never publish partial extraction, and never report partial deletion as success. | Unit/integration fault tests and direct FE smoke. |
| M9-10 | 23, 24 | Document extraction/consolidation and bounded active-CV reads consume the five exact Plan 2-owned Settings values without redefining their names/defaults or using the obsolete single batch variable. | Settings-consumer unit tests, override tests, rendered Compose inspection, and the Plan 2 → Plan 9 handoff. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Plans 1-7 | Stable SQLite, one Agent, SSE, approval, profile, job, matching, direct graph sync, Compose, and local release baseline | Run current backend/frontend suites before migration work and retain failures as baseline evidence. |
| Plan_2 | Sole external configuration owner for `CV_EXTRACT_BATCH_MAX_CHARS=12000`, `CV_CONSOLIDATE_BATCH_MAX_CHARS=12000`, `CV_READ_DEFAULT_MAX_CHARS=6000`, `CV_READ_HARD_MAX_CHARS=12000`, and `CV_READ_MAX_RESULTS=10`, including Settings, `.env.example`, and backend Compose wiring | Run Settings tests and inspect rendered Compose; block on missing/renamed variables or any application/template/Compose owner for `CV_DOCUMENT_BATCH_MAX_CHARS`. |
| Plan_8 | `attachment_text_chunks`, observability routes/services, retained PDF stream, run projection, and bounded graph response | Trace every attachment/chunk/profile/run/graph caller before changing ownership or delete rules. |
| Implemented UI refresh | Resizable sidebar, vertical rail, D3 graph, pan/zoom/fit/reset, mobile drawer, focused modules/tests, and current `13fr 47fr` sidebar columns | Capture baseline desktop/mobile screenshots; do not plan or implement this UI again. |
| Local services | Existing SQLite data, retained files, and Neo4j may contain pre-Phase-8 CVs without document snapshots | Migration must be data-preserving and must not call ShopAIKey. |

## Scope

- Add approved and draft per-CV document persistence plus explicit CV ownership on
  extraction chat messages/runs.
- Refactor the existing profile extraction path into bounded document extraction,
  coverage/consolidation, and document-to-profile projection modules; reuse the
  parser, chunker, provider retry, Pydantic, and skill normalizer.
- Consume the five Plan 2-owned CV Settings in extraction, consolidation, and
  active-CV read services; add focused override tests proving each value changes
  only its named runtime bound.
- Add active/archived reprocessing and preserve the existing LangGraph
  interrupt/resume approval card and singleton draft lock.
- Add retryable complete deletion for non-active CVs, including safe chat markers
  and exact CV-owned graph deletion.
- Extend direct graph sync, rebuild, consistency/read projection, and graph UI data
  types for the active CV branch and dynamic sections/entries.
- Add compact active-CV outline context and the read-only `read_active_cv` tool.
- Convert `CvHistoryPanel` to a focused CV Manager panel and add only the action,
  confirmation, and state behavior required by this increment.
- Add migrations, focused automated tests, and a synthetic-data-only direct FE
  checklist covering extraction, activation, Agent reads, graph selection, and
  deletion.

## Out of Scope

- Editing CV section/entry content in place, directly selecting a profile snapshot,
  or activating a CV without fresh extraction and approval.
- More than one active CV/profile, multiple career personas, archived-CV Agent
  search, cross-CV comparison, or automatic rollback.
- OCR, DOCX/image CV support, a new parser, a vector database for CV text, semantic
  CV retrieval, or a second Agent.
- Loading all retained CVs, every active-CV chunk, or an unbounded section into the
  prompt or one tool response.
- Dynamic Neo4j labels based on user headings, arbitrary Cypher, raw PDF/chunk bodies
  in Neo4j, or deletion of shared Job/Skill nodes.
- Rebuilding the observability shell, changing its colors/components, replacing D3,
  or changing the completed desktop/mobile navigation design.
- Background workers, queues, distributed transactions, generic audit/event stores,
  or a new soft-delete framework.
- Renaming the five CV variables, redefining their defaults/template/Compose
  ownership, retaining `CV_DOCUMENT_BATCH_MAX_CHARS` as an alias, or adding a
  second configuration source. Those external contracts belong to Plan 2.

## Target Directory Structure

```text
backend/
  migrations/versions/<revision>_add_cv_documents_and_ownership.py
  app/
    api/cvs.py
    agent/context.py                         # compact active outline
    agent/prompt.py                          # bounded-read policy only
    db/models/cv_documents.py
    db/models/chat.py                        # attachment ownership/redaction fields
    graph/sync_cv.py
    graph/delete_cv.py
    graph/observability.py                   # active CV branch
    graph/rebuild_snapshot.py
    graph/rebuild_target.py
    repositories/cv_documents.py
    repositories/chat_messages.py
    repositories/agent_runs.py
    schemas/cv_document.py
    schemas/cv_manager.py
    schemas/observability.py
    services/cv_document_extraction.py
    services/cv_document_projection.py
    services/cv_manager.py
    services/active_cv_reader.py
    services/profile_extraction.py           # orchestration adapter; shrink/split
    services/profile_approval.py
    tools/active_cv.py
    tools/registry.py
  tests/
    unit/test_cv_document.py
    unit/test_cv_document_extraction.py
    unit/test_active_cv_reader.py
    unit/test_cv_graph.py
    integration/test_cv_manager_api.py
    integration/test_cv_manager_deletion.py
    integration/test_active_cv_tool.py
frontend/src/
  features/observability/
    api.ts
    types.ts
    state.ts
    CvManagerPanel.tsx
    CvDeleteDialog.tsx
    GraphPanel.tsx
  test/cv-manager.test.tsx
  test/cv-manager-api.test.ts
docs/acceptance/cv_manager_checklist.md
```

Names may align with an equivalent existing owner discovered during implementation,
but business rules must not be duplicated. New focused modules should remain below
the repository's 300-line target; existing oversized extraction/draft modules must
be reduced or delegated to rather than expanded.

## Technical Specifications

### CV Configuration Consumption

- Consume, without renaming or redefining defaults, the five validated Settings
  members produced by Plan 2:

  ```text
  CV_EXTRACT_BATCH_MAX_CHARS=12000
  CV_CONSOLIDATE_BATCH_MAX_CHARS=12000
  CV_READ_DEFAULT_MAX_CHARS=6000
  CV_READ_HARD_MAX_CHARS=12000
  CV_READ_MAX_RESULTS=10
  ```

- `CV_EXTRACT_BATCH_MAX_CHARS` bounds the raw ascending chunk-text payload sent
  to each extraction batch. `CV_CONSOLIDATE_BATCH_MAX_CHARS` independently bounds
  each fragment consolidation/merge payload; neither value is reused for the
  other stage.
- `CV_READ_DEFAULT_MAX_CHARS` is the server-selected response character cap when
  a valid tool call omits `max_chars`. `CV_READ_HARD_MAX_CHARS` is the absolute
  accepted response cap; a requested larger value is rejected by the existing
  typed input boundary rather than silently bypassing it.
- `CV_READ_MAX_RESULTS` is the absolute item-count cap for `section` and `search`;
  `chunk` remains exactly one selected chunk page. A smaller valid caller value is
  respected independently from the character cap.
- Service constructors/functions receive these values from the one cached
  Settings owner or explicit test seams. Do not import module-level duplicate
  constants, read `.env` inside services, or accept client overrides beyond the
  existing bounded tool fields.
- Override tests must change one setting at a time and prove the corresponding
  extraction, consolidation, default-read, hard-read, or result-count boundary
  changes while the other four behaviors remain fixed. No test calls a real
  provider or uses a real CV.

### Migration And Compatibility

- Add `cv_documents` and `cv_document_drafts` exactly as defined by Master Section
  6.2. Add `source_attachment_id`/`redacted_at` to chat messages and
  `source_attachment_id` to Agent runs/tool executions with named constraints and
  indexes.
- Change chunk ownership to `ON DELETE CASCADE` through SQLite batch migration and
  add attachment state `deleting`. Preserve all existing rows and singleton data.
- The migration is structural and deterministic: it makes zero provider, file,
  or Neo4j calls and does not synthesize a sectioned document from legacy chunks.
- New extraction/read tools and CV-derived messages always write explicit attachment
  ownership. For historical CV runs/messages/tools, implement one shared ownership
  resolver using existing validated structured payload/tool-result shapes; do not
  parse free-form chat text with regex.
- A pre-Phase-8 active CV without `cv_documents` remains active and usable. CV
  Manager displays `reprocess_required`; graph emits its active `CV` metadata node
  without section children; `read_active_cv` supports search/chunk over existing
  chunks while section mode returns `CV_DOCUMENT_REPROCESS_REQUIRED`. Re-extract and
  approve upgrades it without changing attachment identity.

### Document-First Extraction

- Keep `pypdf`, the existing deterministic chunker, provider retry wrapper, and
  structured-output adapter. Search their callers before extracting shared logic.
- Partition the full ascending chunk sequence into bounded batches using
  `CV_EXTRACT_BATCH_MAX_CHARS`. Every batch carries attachment ID and exact
  ordinal range.
- Each batch returns ordered `CVSection` fragments and `CVEntry` values with source
  chunk ordinals. Preserve original headings. Unknown headings use `kind='other'`;
  never coerce certificates, GPA, awards, projects, or other facts into skills.
- Perform one logical consolidation stage over all fragments. If its input exceeds
  `CV_CONSOLIDATE_BATCH_MAX_CHARS`, merge adjacent fragment groups hierarchically
  under that independent ceiling, then make one final bounded merge. No model call
  receives the complete raw PDF body merely because the CV is small enough.
- Validate each structured model boundary and allow at most the existing one repair.
  Stable deterministic IDs derive from extraction version, section/entry ordinal,
  and normalized original heading, not model-generated UUIDs.
- Run a deterministic coverage audit after consolidation. Every source chunk ordinal
  must be referenced. Any unreferenced meaningful chunk becomes an ordered
  `kind='other'` recovery entry with an extraction warning, so source content is not
  silently discarded.
- Derive `CandidateProfile` only from the validated `CVDocument`, using bounded
  section/profile fragments when needed. Then run the existing deterministic skill
  normalizer and profile validation. The approved document remains authoritative
  for facts that have no profile field.
- Persist chunks, `cv_document_drafts`, and the singleton `profile_drafts` row in one
  short transaction only after document, coverage, projection, and source-hash
  validation succeed. Provider calls occur outside the transaction.
- Tests must include a synthetic CV with Certifications plus at least one heading not
  present in the section-kind enum and assert exact retained heading/entry content.

### Reprocessing And Approval

- `POST /api/cvs/{id}/reprocess` accepts only active/archived attachments with a
  retained readable PDF and no conflicting interrupted run. It creates a normal
  CV-scoped user message/run and reuses the existing Agent runner, proposal service,
  SSE events, approval card, and resume endpoint.
- Reprocessing writes only draft rows. An archived target remains archived and the
  current Candidate/graph stay active. An active target keeps its current approved
  document/profile while the replacement draft is pending.
- Save Profile atomically archives the old active CV only when IDs differ, activates
  the selected CV, copies its document draft to `cv_documents`, updates the Candidate
  Profile, deletes both drafts, and verifies source hash plus one-active invariants.
- Request Changes preserves both drafts and keeps current active data unchanged. All
  error and idempotent resume behavior from Plan 4 remains intact.
- After commit, sync Candidate/Skill and the selected CV branch. A graph failure
  reports `NEO4J_SYNC_FAILED` without rolling SQLite back and is repairable by the
  existing rebuild command.

### Complete Non-Active Deletion

- `DELETE /api/cvs/{id}` rejects active state before any mutation. Eligible states
  are archived, failed, unreferenced staged, and retryable deleting.
- The CV Manager service is the only deletion coordinator. It first records
  `deleting`, redacts every linked chat message to `[CV deleted]`, clears structured
  payloads, and removes a matching draft in a short transaction.
- Delete matching LangGraph checkpoints by CV-scoped run IDs, remove the retained
  file through the existing attachment storage abstraction, and delete only the
  exact Neo4j `CV.id` branch. All operations are idempotent.
- The final transaction deletes CV-scoped runs so their tool executions cascade,
  deletes any directly CV-owned tool execution from otherwise unrelated runs, then
  deletes the attachment so chunks, approved/draft documents, and metadata cascade.
  Redacted chat rows remain with null attachment ownership.
- Preserve Candidate/current profile, all Jobs, all Skills, seed relationships,
  unrelated runs/tools/messages, and files for every other attachment. Graph delete
  queries may detach/delete only CVSection/CVEntry nodes reached from the exact CV.
- If any external cleanup fails, retain the `deleting` row with a stable code and
  return retry guidance. Return `204` only after all resources and the row are gone.
  Retrying the same deletion resumes cleanup and never reports false success.

### Neo4j Projection And Rebuild

- Add fixed allowlisted labels and identities from Master Section 8. User headings
  are properties, never labels. Keep full bodies, bullets, arbitrary attributes,
  chunks, and PDF bytes out of Neo4j.
- Sync all approved retained CV document branches so deletion is exact and rebuild is
  complete. Maintain exactly one `PROJECTS_TO` relationship from the active CV to
  Candidate; remove it from the prior CV during active sync.
- Bound entry `preview` with the existing safe text projection pattern. Stable sort
  sections/entries by ordinal before Cypher payload creation.
- Extend graph observability caps/types to include only the active CV branch. Preserve
  existing D3 simulation, semantic fallback, pan/zoom/fit/reset, stale/unavailable
  handling, and Job/Skill projection.
- Extend the rebuild snapshot/target rather than create a second rebuild path. It
  clears only JobAgent-owned labels, recreates constraints, and reconstructs CV
  branches from SQLite without provider calls.
- Matching consistency remains based on Candidate/Job revisions. Graph observability
  additionally checks active CV ID/document source hash and reports stale when that
  branch does not match SQLite.

### Bounded Agent Retrieval

- Extend current candidate context loading with `active_cv_context`: active attachment
  ID, document revision/source hash, and bounded outline only. Legacy documents emit
  the reprocess-required status and no synthetic section body.
- Register `read_active_cv` as the seventh tool in the existing single ToolNode and
  durable execution path. Do not add an Agent node or alter the six-iteration guard.
- Implement `section`, `search`, and `chunk` modes from Master Section 13.7. Resolve
  active attachment server-side; reject archived/staged IDs even if guessed.
- Enforce `max_results` and `max_chars` independently using
  `CV_READ_MAX_RESULTS`, `CV_READ_DEFAULT_MAX_CHARS`, and
  `CV_READ_HARD_MAX_CHARS`; return opaque cursor and truncation metadata, and bind
  each cursor to active attachment ID, source hash, mode, selector, and stable last
  ordinal/entry ID. An active switch invalidates it.
- Search normalized structured entries and ordered chunks with a simple bounded local
  scan and stable source order. `ponytail:` O(n) search is intentional for one local
  active CV; replace it with SQLite FTS only if measured document size later exceeds
  the bounded local contract.
- Prompt policy asks for the narrowest mode, forbids automatic cursor exhaustion,
  and allows multiple pages only when the user's request genuinely needs them.
  Tool logs store selectors/counts only, never returned CV bodies in argument summary.

### Frontend CV Manager

- Rename the tab label and focused panel from CV History to CV Manager while keeping
  the existing vertical rail, sidebar sizing, typography, colors, list density,
  loading primitives, mobile drawer, and current graph components.
- Show one clear Active badge. Archived rows expose Open/Download, Make active, and
  Delete; the active row exposes Open/Download and Re-extract, never Delete.
- Reprocess consumes the normal SSE stream in the existing chat reducer, focuses the
  approval card, and leaves active UI state unchanged until approval completes.
- Delete opens an accessible confirmation dialog containing the filename and scope
  warning. Disable duplicate actions while pending. On complete success, invalidate
  only CV list, selected chunks, runs, profile summary, and graph caches; choose a
  safe remaining selection. On partial failure, retain the row and recovery message.
- Preserve list/cache state on failed requests. Use existing icons/components and
  tooltips; inspect pinned Astryx documentation before introducing a dialog prop.
- Verify no text/action overlap at current desktop proportions and mobile widths.

## Implementation

1. Run the existing backend/frontend baseline. Verify the Plan 2 Settings,
   `.env.example`, and rendered backend Compose environment contain the five exact
   CV variables and no obsolete `CV_DOCUMENT_BATCH_MAX_CHARS`; block before CV work
   on any mismatch. Then search all attachment, chunk,
   extraction, approval, message/run/tool, checkpoint, storage, graph, observability,
   and sidebar callers. Record the existing ownership shapes needed for migration.
2. Add failing schema/migration/repository tests, then implement document tables,
   lifecycle enum, ownership fields, cascade rules, and legacy compatibility.
3. Add failing dynamic-section/batching/coverage/projection tests, split extraction
   responsibilities into focused modules, and integrate atomic draft persistence.
4. Add reprocess/approval tests and route; reuse current SSE runner, tool execution,
   interrupt, draft, approval, parser, retry, and normalizer contracts.
5. Add deletion fault tests, then implement the one retryable coordinator using
   existing repository, checkpoint, storage, and graph owners.
6. Add CV graph sync/delete/rebuild/observability tests and extend the existing graph
   modules and response types with the active CV branch.
7. Add active outline/tool tests, implement `read_active_cv`, register it in the
   existing ToolNode, and update prompt policy without changing loop topology.
8. Convert the focused history panel to CV Manager, add actions/dialog/cache updates,
   and extend frontend tests while preserving the implemented UI refresh.
9. Run focused and full validation, Compose smoke, and the synthetic direct FE
   checklist. Inspect desktop/mobile screenshots and browser console before handoff.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Configuration handoff | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_settings.py tests/unit/test_cv_document_extraction.py tests/unit/test_active_cv_reader.py -q`; then from root run `docker compose --env-file .env -f infrastructure/docker-compose.yml config` | Five exact Plan 2 variables/defaults are present in Settings/template/rendered backend env; one-at-a-time overrides affect only the named extraction/consolidation/read bound; obsolete `CV_DOCUMENT_BATCH_MAX_CHARS` is absent. |
| Migration/schema | `Set-Location backend; py -3.13 -m pytest tests/integration/test_migrations.py tests/integration/test_database_contract.py -q` | Existing data survives; document/ownership/cascade/state contracts pass with no provider call. |
| Document extraction | `Set-Location backend; py -3.13 -m pytest tests/unit/test_cv_document.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py -q` | Full chunk coverage, bounded calls, deterministic IDs, Certifications/unknown heading retention, and profile projection pass. |
| Reprocess/approval | `Set-Location backend; py -3.13 -m pytest tests/integration/test_cv_manager_api.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py -q` | Active/archived reprocess, request changes, approval switch, rollback, SSE, and idempotency pass. |
| Complete deletion | `Set-Location backend; py -3.13 -m pytest tests/integration/test_cv_manager_deletion.py -q` | Active guard, fault retry, file/SQLite/checkpoint/run/tool/chat/graph cleanup, and shared Job/Skill preservation pass. |
| Agent bounded reads | `Set-Location backend; py -3.13 -m pytest tests/unit/test_active_cv_reader.py tests/integration/test_active_cv_tool.py tests/unit/test_agent_context.py tests/unit/test_agent_graph.py -q` | Outline-only prompt, active authorization, all modes/caps/cursors, switch invalidation, and one ToolNode topology pass. |
| Graph behavior | `Set-Location backend; py -3.13 -m pytest tests/unit/test_cv_graph.py tests/unit/test_observability_graph.py tests/integration/test_observability_api.py tests/integration/test_graph_rebuild_contracts.py -q` | Active CV sections/entries, stale states, exact ownership deletion, and provider-free rebuild pass. |
| Backend full/static | `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental; py -3.13 -m pytest -q` | Lint, types, and full backend suite pass without real ShopAIKey calls. |
| Frontend focused | `Set-Location frontend; npm test -- --run src/test/cv-manager.test.tsx src/test/cv-manager-api.test.ts src/test/observability-sidebar.test.tsx src/test/graph-interaction.test.tsx` | Actions, confirmation, cache/error states, graph interactions, and responsive shell pass. |
| Frontend full/build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Existing UI refresh and all chat/profile/observability regressions remain green. |
| Local services | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` | Frontend, backend, and Neo4j are healthy on the documented local ports. |
| Direct FE smoke | Execute `docs/acceptance/cv_manager_checklist.md` with synthetic CVs containing Certifications and an unknown heading. | Re-extract, archive activation, Agent bounded evidence, active graph switch, active-delete guard, archived deletion, desktop/mobile layout, and console checks pass. |
| Scope hygiene | `git diff --check`; inspect changed paths and tracked data/secrets. | No unrelated redesign, duplicated business logic, real CV data, secrets, new Agent/vector store/worker, or out-of-scope infrastructure. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Plans 1-7 | Implemented local product, one-Agent approval flow, source-of-truth data, graph/matching, and release baseline | Existing behavior is preserved unless Master Version 1.7 explicitly amends it. |
| Plan_2 | Sole ownership of the five exact CV external names/defaults, Settings validation, `.env.example`, and backend Compose/process environment | Plan 9 consumes the five Settings members exactly and never creates another alias/default/env source. |
| Plan_8 | Deterministic chunks, retained PDF/history, run observability, graph read model, and sidebar module baseline | Read functionality is extended, not reimplemented. |
| UI refresh implementation | Resizable shell, tab rail, D3 graph, responsive drawer, tests, and current proportions | Phase 9 preserves colors, components, interaction model, and layout baseline. |
| Master amendment | Phase 8 schema, extraction, lifecycle, API, graph, Agent, UI, and recovery contracts | Master Version 1.7 takes precedence over historical immutable-CV/read-only constraints. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Fresh portfolio review | Updated `Master_plan.md`, amended `Plan_8.md` handoff, and this `Plan_9.md` | Structural validator passes and requirement/ownership/verification contracts are reviewable end to end. |
| Future task writing after approval | A reviewed Phase 8 implementation contract | Tasks may be derived only after a fresh plan review approves the complete portfolio. |
| Implementation orchestration after tasks | CV Manager/document-first/active-read batch boundary | Future A1/A2/A3 evidence must map to this verification matrix without reopening prior UI scope. |
| Future configuration maintenance | Effective extraction/consolidation/read consumers with one-at-a-time override coverage | Changes begin in Plan 2's external configuration owner and must rerun Plan 9 consumer tests; domain services never redefine the contract. |

### Next Consumer

`Plan_10.md` consumes the implemented CV Manager/document-first/active-read baseline,
the existing sidebar module and cache patterns, exact cross-store ownership rules,
and the verified matching/graph contracts. It must add only the authorized saved-JD
and revision-keyed-evaluation increment, and must not reimplement Plan 9 CV lifecycle,
approval, bounded retrieval, or graph projection ownership.
