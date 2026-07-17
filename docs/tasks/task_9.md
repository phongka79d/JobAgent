# JobAgent Plan 9 Execution Tasks

## Purpose

Translate `docs/plans/Plan_9.md` into the mandatory implementation chain for complete per-CV document extraction, approval-gated CV reprocessing and activation, retryable non-active CV deletion, CV-owned Neo4j projection, bounded active-CV Agent reads, and the CV Manager frontend. Preserve the single-user local MVP, the existing one-Agent/SSE/approval path, SQLite as source of truth, Neo4j as a derived index, and the implemented observability UI refresh.

## Project Context Notes

- Root `README.md` was read completely before derivation. It defines the React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, ShopAIKey, root-only `.env`, three-service Compose, and current validation boundaries.
- The user explicitly accepted Plan 9's fresh-review gate and authorized resolution of minor planning ambiguities. That current instruction permits this task file but does not expand Plan 9 scope.
- Primary authority is `docs/plans/Plan_9.md`. Supporting authority is `docs/plans/Master_plan.md` Version 1.7, `docs/plans/Plan_8.md`, and `docs/superpowers/plans/2026-07-16-observability-sidebar-ui-refresh.md`.
- Repository evidence confirms the active migration root is `backend/migrations/versions/` with head `0002_add_attachment_text_chunks`; `0003_add_cv_documents_and_ownership.py` is the likely next revision. Do not create a second migration chain.
- Existing reuse owners include deterministic chunking/provider retry in `profile_extraction.py` and `provider_retry.py`, approval in `profile_approval.py`, normal chat/SSE creation in `chat_turns.py` and `agent/runner.py`, checkpoint deletion in `agent/checkpoint.py`, attachment storage in `storage/attachments.py`, durable tool execution in `tool_execution.py`, graph sync/rebuild/observability modules, and the observability sidebar's typed client/cache/panels.
- Several current owners already exceed the repository's 300-line target: profile extraction/approval, Agent context, graph observability, and frontend observability state/types. Plan 9 work must extract focused modules and delegate from those owners; it must not grow them or duplicate their business rules.
- `frontend/AGENTS.md` applies to Batch07: inspect the pinned Astryx 0.1.4 CLI documentation before using components, preserve the established shell, use components/tokens instead of raw layout/styling, and do not invent props.
- The worktree already contains user changes to `docs/plans/Master_plan.md`, `docs/plans/Plan_8.md`, and the untracked `docs/plans/Plan_9.md`. Preserve them. This authoring pass creates only `docs/tasks/task_9.md`.
- Root `.env`, local databases, uploads, and Neo4j volumes are user-managed and must never be read into evidence, printed, copied, or committed. Automated tests use fakes; only Batch08 may use configured local services and synthetic CVs.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_9.md`.
- Supporting: `docs/plans/Master_plan.md` Version 1.7, `docs/plans/Plan_8.md`, and `docs/superpowers/plans/2026-07-16-observability-sidebar-ui-refresh.md`.
- Context only: `README.md`, repository owners/tests, `frontend/AGENTS.md`, and `infrastructure/docker-compose.yml`.

### Source Section Index

- `Plan_9.md` > `## Objective`, `## Prerequisites`, `## Scope`, and `## Out of Scope` -> mandatory outcome, reuse baseline, and exclusions.
- `Plan_9.md` > `## Target Directory Structure` -> focused ownership and anti-God-file boundary.
- `Plan_9.md` > `### Migration And Compatibility` -> document/ownership schema, cascade, lifecycle, and legacy behavior.
- `Plan_9.md` > `### Document-First Extraction` -> bounded extraction, consolidation, coverage, projection, and atomic draft publication.
- `Plan_9.md` > `### Reprocessing And Approval` -> active/archived reprocess, interrupt/resume reuse, and approval-only activation.
- `Plan_9.md` > `### Complete Non-Active Deletion` -> one retryable cross-store deletion coordinator and preservation rules.
- `Plan_9.md` > `### Neo4j Projection And Rebuild` -> fixed CV graph model, active branch, exact deletion, rebuild, and staleness.
- `Plan_9.md` > `### Bounded Agent Retrieval` -> compact context and seventh active-only bounded tool.
- `Plan_9.md` > `### Frontend CV Manager` -> action states, confirmation, focused invalidation, accessibility, and UI preservation.
- `Plan_9.md` > `## Implementation` and `## Verification` -> execution order and required evidence matrix.
- `Master_plan.md` > `### 6.2 Application table schemas` through `### 6.6 Neo4j identity mapping` -> exact SQLite rows, constraints, transactions, deletion rules, and graph IDs.
- `Master_plan.md` > `### 7.2 Candidate Profile`, `## 8. Neo4j Derived Model`, `## 10. CV Ingestion and Approval Flow`, `## 12. Agent Architecture`, `## 13. Agent-Facing Tool Contracts`, `## 14. Public FastAPI Boundary`, and `## 15. Frontend UX Plan` -> canonical data and behavior contracts.
- `Master_plan.md` > `## 20. Failure and Recovery Policy`, `## 21. Direct SQLite-to-Neo4j Synchronization`, `## 24. Local Testing Strategy`, and `### Phase 8 - CV Manager, document-first extraction, and bounded active-CV reads` -> failure, rebuild, testing, and exit gates.
- `Plan_8.md` > `### Next Consumer` and `### Historical Completion Contract` -> implemented retained-CV/chunk/API/sidebar baseline that Plan 9 extends rather than reopens.
- UI refresh > `## Scope And File Map` and `### Task 10: Full Regression, Compose, And Final Browser Acceptance` -> implemented module split, D3 interaction, desktop/mobile layout, and visual regression baseline.

### Approved Architecture and Constraints

- Keep one React/Astryx client, one FastAPI application, one LangGraph Agent with one `ToolNode` and a six-iteration guard, one SQLite source of truth, one derived Neo4j index, and ShopAIKey as the only model provider.
- A CV becomes active only after fresh document-first extraction and the existing explicit approval resume. Reprocessing writes drafts only; failures and Request Changes preserve the current active CV/profile/document.
- SQLite stores complete approved/draft `CVDocument` data and raw chunks. Neo4j receives only fixed labels and bounded safe properties; no dynamic labels, PDF/chunk bodies, arbitrary attributes, or arbitrary Cypher.
- The active CV is never deletable. One coordinator owns idempotent non-active deletion across SQLite, checkpoints, file storage, exact CV graph data, CV-owned runs/tools, and redacted chat markers.
- Prompt context contains only active identity/revision and a compact outline. `read_active_cv` is the only Agent-facing CV body path and resolves the active attachment server-side.
- Reuse existing parser, chunker, provider retry, Pydantic, skill normalizer, cursor, SSE, approval, storage, checkpoint, repository, graph, and frontend cache patterns. Search all callers before changing a shared owner.
- Preserve the implemented resizable `13/47/40` desktop shell, vertical rail, mobile drawer, Astryx components/colors, D3 graph controls, semantic fallback, and chat reducer. Do not rebuild or replace them.
- No OCR/DOCX, second Agent, vector store for CV text, semantic CV search, profile-version selector, direct activation, cross-CV search, worker/queue, distributed transaction, generic audit/soft-delete framework, or production security subsystem.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | CV document, lifecycle, and ownership persistence | (01A) | Accepted Plan 8 baseline |
| Batch02 | Complete document-first extraction and atomic drafts | (02A), (02B) | Batch01 |
| Batch03 | Approval-gated active/archived reprocessing and activation | (03A) | Batch02 |
| Batch04 | Retryable complete non-active CV deletion | (04A) | Batch03 |
| Batch05 | CV-owned graph sync, rebuild, and active observability | (05A), (05B) | Batch04 |
| Batch06 | Compact context and bounded active-CV Agent retrieval | (06A), (06B) | Batch05 |
| Batch07 | Accessible CV Manager client state and interface | (07A), (07B) | Batch06 |
| Batch08 | Synthetic direct smoke and final regression evidence | (08A) | Batch07 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md`
  report.
- A2 reviews one executed task, writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a2/<batch-id>/<task-id>/A2-a<attempt>.md`
  report, and the Orchestrator checks the canonical checkbox only after
  `ACCEPTED`.
- A3 runs only after every task in the selected batch has matching A1 evidence,
  A2 evidence, an Orchestrator `ACCEPTED` event, and a checked canonical task
  marker; it writes only
  `.agent/<plan-id>/<run-id>/report/a3/<batch-id>/A3-a<attempt>.md`.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - CV Document and Ownership Persistence

### Goal

Add the data-preserving SQLite foundation for approved/draft CV documents, explicit CV ownership, deleting lifecycle, and exact cascades without external calls or legacy-data synthesis.

### Dependencies

- Plan 8 retention/chunk/API/sidebar artifacts are accepted and remain the reuse baseline.
- Before edits, record the current repository revision and existing affected-test result so pre-existing failures are distinguishable.

### Scope Boundary

Own one Alembic revision, ORM models, flush-only repositories, and direct migration/schema tests. Exclude extraction behavior, approval/reprocessing, deletion coordination, graph writes, Agent/tools, frontend, and runtime data backfill.

### Tasks

- [x] (01A): Migrate CV document, lifecycle, and ownership persistence
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch01 - CV Document and Ownership Persistence` > `(01A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Migration And Compatibility` and `## Implementation` item 2; `docs/plans/Master_plan.md` > `### 6.2 Application table schemas`, `### 6.3 Foreign-key and deletion rules`, and `### 6.5 Migration and checkpoint ownership`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(01A)` -> task authority
    - source-persistence: repository `docs/plans/Plan_9.md` > `### Migration And Compatibility` -> migration and compatibility authority
    - master-schema: repository `docs/plans/Master_plan.md` > `### 6.2 Application table schemas` -> exact columns, enums, constraints, and indexes
    - migration-owner: repository `backend/migrations/versions/0002_add_attachment_text_chunks.py` and `backend/tests/support/db_migration.py` -> active revision/head conventions
    - model-owner: repository `backend/app/db/models/attachments.py`, `attachment_text_chunks.py`, `chat.py`, and `profiles.py` -> current ORM/FK conventions
    - validation-schema: repository `docs/plans/Plan_9.md` > `## Verification` > `Migration/schema` -> required evidence
  - Source Requirements:
    - Add `cv_documents` and `cv_document_drafts` exactly to the Master contract; add nullable `source_attachment_id` ownership and `redacted_at` fields with named constraints/indexes to chat/run/tool rows.
    - Add attachment state `deleting` and make chunk ownership `ON DELETE CASCADE` through SQLite batch migration while preserving every existing application and checkpoint row.
    - Use the configured `backend/migrations/versions/` chain; migration performs no provider, filesystem, or Neo4j call and does not synthesize `CVDocument` rows from historical chunks.
    - Preserve pre-Phase-8 active CV usability when no approved document row exists.
  - Dependencies: Accepted Plan 8 baseline; no earlier Plan 9 task.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/migrations/versions/0003_add_cv_documents_and_ownership.py`, `backend/app/db/models/attachments.py`, `backend/app/db/models/attachment_text_chunks.py`, `backend/app/db/models/cv_documents.py`, `backend/app/db/models/chat.py`, `backend/app/db/models/__init__.py`, `backend/app/repositories/cv_documents.py`, `backend/app/repositories/chat_messages.py`, `backend/app/repositories/agent_runs.py`, `backend/app/repositories/tool_executions.py`, `backend/tests/integration/test_migrations.py`, `backend/tests/integration/test_database_contract.py`, `backend/tests/support/db_migration.py`, `backend/tests/support/schema_parity.py`
  - Allowed Files: the listed migration/model/repository/test/support files plus one focused CV-document model test; exclude services, API, Agent, tools, graph, frontend, infrastructure, root environment files, and unrelated migrations.
  - Agent Work:
    1. Use `git grep` to trace every attachment/chunk/message/run/tool model and repository caller, current constraint naming, migration head, schema parity, and checkpoint-table exclusions.
    2. Add failing empty/existing-database migration and ORM contract tests, then implement the single data-preserving revision and focused models/repositories.
    3. Keep repositories flush-only, reuse UUID/UTC/JSON validation patterns, and expose only operations required by later approved tasks.
    4. Prove application rows survive, checkpoint tables are untouched, cascades/restrict/set-null rules match the Master, and migration code has no external-call import path.
  - Output: One upgraded SQLite schema with validated per-CV document rows, explicit ownership, deleting state, and exact deletion constraints.
  - A1 Outcome: Existing databases upgrade without data loss and expose the complete Plan 9 relational ownership contract.
  - A2 Review Focus: Revision-chain correctness, every named constraint/index/FK/cascade, existing-row preservation, no synthesized document, no external call, repository flush-only behavior, and caller compatibility.
  - A3 Batch Evidence: M9-01/M9-03 schema and ownership rows plus the migration-preservation and checkpoint-exclusion matrix.
  - Acceptance:
    - Empty and initialized databases upgrade to the new head with all Master-specified tables, fields, states, named constraints, indexes, and FK actions.
    - Existing attachments/chunks/profile/chat/runs/tools/checkpoints survive; no document row is invented and no provider/file/graph code is reachable from migration.
    - ORM/repository contracts persist only serialized artifacts supplied by the later Pydantic service boundary, expose ownership fields, and neither commit nor duplicate lifecycle business logic.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_migrations.py tests/integration/test_database_contract.py -q` -> PASS evidence: exit `0` with empty/existing upgrade, preservation, constraint, cascade, and no-provider assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_attachment_profile_models.py tests/unit/test_chat_models.py -q` -> PASS evidence: exit `0` with ORM/FK/index parity; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A conflicting migration head or schema authority is `BLOCKED_SOURCE_CONFLICT`; a root fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/Alembic/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/migrations/versions/0003_add_cv_documents_and_ownership.py`, `backend/app/db/models/{attachments,attachment_text_chunks,cv_documents,chat,__init__}.py`, `backend/app/repositories/{cv_documents,chat_messages,agent_runs,tool_executions}.py`, `backend/tests/{integration,unit,support}/**/*{migration,database_contract,model,schema_parity}*` within the bounded files named above.

## Mandatory Batch02 - Document-First Extraction and Draft Publication

### Goal

Extract every meaningful ordered CV section through bounded model calls, preserve known and unknown content in a validated `CVDocument`, derive the Candidate Profile only from that document, and atomically publish complete draft artifacts.

### Dependencies

- `(01A)` is accepted; document/draft tables and ownership fields are available.

### Scope Boundary

Own CV-document schemas, bounded extraction/consolidation/coverage, document-to-profile projection, and atomic extraction-draft integration. Exclude reprocess routes, approval/activation, deletion, graph projection, Agent retrieval/tool registration, and frontend.

### Tasks

- [x] (02A): Extract complete bounded CV documents and project Candidate Profiles
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch02 - Document-First Extraction and Draft Publication` > `(02A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Document-First Extraction` and `## Implementation` item 3; `docs/plans/Master_plan.md` > `### 7.2 Candidate Profile` and `### 10.2 Processing`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(02A)` -> task authority
    - source-extraction: repository `docs/plans/Plan_9.md` > `### Document-First Extraction` -> batching, consolidation, coverage, and projection authority
    - master-document: repository `docs/plans/Master_plan.md` > `### 7.2 Candidate Profile` -> exact `CVDocument`/section/entry contract
    - parser-chunker-owner: repository `backend/app/services/pdf_extraction.py`, `profile_extraction.py`, and `backend/app/repositories/attachment_text_chunks.py` -> parser/chunker reuse
    - retry-normalizer-owner: repository `backend/app/services/provider_retry.py` and `skill_normalization.py` -> retry and skill reuse
    - validation-document: repository `docs/plans/Plan_9.md` > `## Verification` > `Document extraction` -> required evidence
  - Source Requirements:
    - Partition the full ascending chunk sequence by a configured character ceiling; every call carries attachment ID and exact ordinal range and no call receives the complete raw PDF body.
    - Produce ordered sections/entries with original headings and source ordinals; Certifications remain certifications and unknown meaningful headings become `kind='other'` without coercion into skills.
    - Consolidate all fragments logically, using bounded adjacent hierarchical merges when needed, then perform deterministic full-ordinal coverage recovery and warnings.
    - Validate each model boundary with at most the existing one repair; derive stable IDs from extraction version, ordinals, and normalized original heading.
    - Derive `CandidateProfile` only from the validated document, then apply the existing deterministic normalizer and profile validation.
  - Dependencies: `(01A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 10800
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/schemas/cv_document.py`, `backend/app/services/cv_document_extraction.py`, `backend/app/services/cv_document_projection.py`, `backend/app/services/profile_extraction.py`, `backend/app/services/provider_retry.py`, `backend/app/core/settings.py`, `backend/tests/unit/test_cv_document.py`, `backend/tests/unit/test_cv_document_extraction.py`, `backend/tests/unit/test_profile_extraction.py`, synthetic fixtures under `backend/tests/fixtures/cv/`
  - Allowed Files: listed schemas/services/settings/tests and synthetic fixture files only; exclude repositories/migrations beyond read-only imports, API, approval, deletion, graph, Agent/tools, frontend, and environment values.
  - Agent Work:
    1. Use `git grep` to map every parser, chunker, structured invoker, provider-retry, extracted-profile, normalizer, settings, and test caller before moving shared logic.
    2. Add failing strict-schema, batch-ceiling, recursive-consolidation, deterministic-ID, coverage-recovery, projection, and repair-boundary tests, including one synthetic CV with Certifications and an unmodeled heading.
    3. Implement focused schema/extraction/projection modules; refactor the oversized `profile_extraction.py` to delegate rather than duplicate parser, retry, chunk, or normalization behavior.
    4. Prove stable source order, complete meaningful-content retention, bounded calls, one repair per boundary, and no persistence/network side effects in pure projection helpers.
  - Output: Validated complete `CVDocument` and derived `CandidateProfile` artifacts from bounded ordered chunks.
  - A1 Outcome: Every meaningful known or unknown CV section survives a bounded validated document-first pipeline before profile derivation.
  - A2 Review Focus: Raw-input bounds, hierarchical merge order, complete coverage, stable IDs, original-heading fidelity, certification/unknown handling, projection-only profile facts, one-repair rule, shared-helper reuse, and module size.
  - A3 Batch Evidence: M9-01/M9-09 schema, batching, coverage, unknown-section, projection, and failure-isolation evidence.
  - Acceptance:
    - Strict models reject invalid identity/order/source fields and preserve dynamic section content exactly as required.
    - No provider request receives an unbounded complete raw CV; every chunk ordinal is represented or recovered in ordered `other` content with a warning.
    - Candidate Profile facts come only from the validated document, and the synthetic Certifications/unmodeled-heading case retains exact heading and entry content.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_cv_document.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py -q` -> PASS evidence: exit `0` with bounds, coverage, deterministic IDs, unknown-section retention, projection, and failure assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Missing authoritative provider ceiling/structured-output seam is `BLOCKED_MISSING_REF`; a required new parser/provider is `BLOCKED_SCOPE_CONFLICT`; unavailable test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/schemas/cv_document.py`, `backend/app/services/{cv_document_extraction,cv_document_projection,profile_extraction,provider_retry}.py`, `backend/app/core/settings.py`, `backend/tests/unit/test_{cv_document,cv_document_extraction,profile_extraction}.py`, `backend/tests/fixtures/cv/**`.

- [x] (02B): Publish complete CV document and profile drafts atomically
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch02 - Document-First Extraction and Draft Publication` > `(02B)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Migration And Compatibility`, `### Document-First Extraction`, and `## Implementation` item 3; `docs/plans/Master_plan.md` > `### 6.4 Transaction boundaries`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(02B)` -> task authority
    - source-transaction: repository `docs/plans/Plan_9.md` > `### Document-First Extraction` -> atomic publication authority
    - master-transaction: repository `docs/plans/Master_plan.md` > `### 6.4 Transaction boundaries` -> exact extraction transaction
    - draft-owner: repository `backend/app/services/profile_drafts.py`, `backend/app/repositories/profiles.py`, and `backend/app/repositories/attachment_text_chunks.py` -> current singleton draft/chunk transaction
    - document-owner: repository `backend/app/repositories/cv_documents.py` from `(01A)` -> draft document persistence
    - validation-extraction: repository `docs/plans/Plan_9.md` > `## Verification` > `Document extraction` -> integration evidence
  - Source Requirements:
    - Perform provider calls, validation, coverage, projection, and source-hash computation outside a transaction.
    - Only after total success, atomically replace the attachment's chunks and `cv_document_drafts` and upsert `profile_drafts('current')` with matching attachment/profile/source hash.
    - Any parse/model/repair/document/coverage/projection/hash/persistence failure leaves prior chunks, approved document, drafts, and active profile truthful; never publish a partial extraction.
    - Preserve legacy active CV behavior without synthesizing a document; reprocessing is the later explicit upgrade path.
  - Dependencies: `(02A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/profile_extraction.py`, `backend/app/services/profile_drafts.py`, `backend/app/services/cv_document_extraction.py`, `backend/app/services/cv_document_projection.py`, `backend/app/repositories/attachment_text_chunks.py`, `backend/app/repositories/cv_documents.py`, `backend/app/repositories/profiles.py`, `backend/tests/unit/test_profile_extraction.py`, `backend/tests/integration/test_profile_approval.py`
  - Allowed Files: listed extraction/draft/repository/test files only; exclude public routes, approval commit behavior, deletion, graph, Agent/tools, frontend, migrations, and environment values.
  - Agent Work:
    1. Trace all `propose_profile_from_cv`, chunk replacement, draft upsert, and transaction callers; reuse the existing short-transaction/session pattern.
    2. Add failing success/fault tests across each pre-publication boundary and a transaction failpoint.
    3. Integrate `(02A)` artifacts into the current proposal path with one atomic write owner; remove superseded profile-first extraction logic rather than retaining a second path.
    4. Assert matching attachment IDs/source hashes/profile projections and no partial writes under every failure.
  - Output: One complete, source-consistent document/profile draft pair and chunk set published atomically.
  - A1 Outcome: The existing proposal flow publishes all CV draft artifacts together or leaves prior truth unchanged.
  - A2 Review Focus: Transaction duration, provider/I/O exclusion, one write owner, source-hash coupling, rollback/fault evidence, legacy compatibility, deleted duplicate logic, and all proposal callers.
  - A3 Batch Evidence: M9-01/M9-02/M9-09 atomic-draft, source-hash, rollback, and legacy-compatibility rows.
  - Acceptance:
    - Successful extraction stores one validated document draft, matching profile draft, and exact canonical chunk sequence in one short transaction.
    - Every specified failure publishes none of the new artifacts and preserves approved/current state.
    - The old raw-chunks-to-profile model path is absent; shared parser/retry/normalizer behavior has one owner.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_cv_document.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py -q` -> PASS evidence: exit `0` with atomic success/rollback and legacy assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A root transaction fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; unavailable database/test tooling is `BLOCKED_ENVIRONMENT`; conflicting draft ownership is `BLOCKED_SOURCE_CONFLICT`.
  - Files: `backend/app/services/{profile_extraction,profile_drafts,cv_document_extraction,cv_document_projection}.py`, `backend/app/repositories/{attachment_text_chunks,cv_documents,profiles}.py`, `backend/tests/unit/test_profile_extraction.py`, `backend/tests/integration/test_profile_approval.py`.

## Mandatory Batch03 - Approval-Gated CV Reprocessing and Activation

### Goal

Reprocess active or archived retained CVs through the normal CV-scoped run/SSE/interrupt path and change the single active CV only when the matching document/profile draft is explicitly approved.

### Dependencies

- `(02A)` and `(02B)` are accepted; complete draft artifacts and source hashes are authoritative.

### Scope Boundary

Own the dedicated reprocess route, CV-scoped turn creation, proposal/approval integration, activation transaction, and focused API/interrupt tests. Exclude deletion, complete CV graph projection/rebuild, Agent document reads, and frontend controls.

### Tasks

- [x] (03A): Reprocess active or archived CVs and activate only approved drafts
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch03 - Approval-Gated CV Reprocessing and Activation` > `(03A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Reprocessing And Approval` and `## Implementation` item 4; `docs/plans/Master_plan.md` > `### 10.3 Chat approval`, `### 10.4 Approved replacement`, `### 10.5 CV Manager reprocessing and deletion`, and `### 14.1 API rules`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(03A)` -> task authority
    - source-reprocess: repository `docs/plans/Plan_9.md` > `### Reprocessing And Approval` -> reprocess/approval authority
    - chat-turn-owner: repository `backend/app/services/chat_turns.py`, `backend/app/agent/runner.py`, and `backend/app/api/chat.py` -> normal run/SSE/interrupt path
    - proposal-owner: repository `backend/app/services/profile_drafts.py` and `backend/app/tools/profile.py` -> `reprocess=true` proposal and approval projection
    - approval-owner: repository `backend/app/services/profile_approval.py` and `backend/app/agent/checkpoint.py` -> commit/request-changes/idempotent resume
    - validation-reprocess: repository `docs/plans/Plan_9.md` > `## Verification` > `Reprocess/approval` -> required evidence
  - Source Requirements:
    - `POST /api/cvs/{attachment_id}/reprocess` accepts only active/archived rows with a readable retained PDF and no conflicting interrupted run, creates one normal CV-owned message/run, and returns the existing SSE/approval contract.
    - Reprocess writes drafts only. Active/document/profile/graph truth remains unchanged while pending, on failure, and after Request Changes.
    - Save Profile verifies file/source hash/draft coupling, archives the prior active only when IDs differ, activates the selected CV, approves its document/profile, clears both drafts, and ends with one active invariant.
    - Resume remains idempotent; after SQLite commit, existing sync behavior remains truthful and any graph failure returns `NEO4J_SYNC_FAILED` without rollback. Batch05 owns the complete CV branch projection.
  - Dependencies: `(02A)` and `(02B)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 10800
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/api/cvs.py`, `backend/app/main.py`, `backend/app/schemas/cv_manager.py`, `backend/app/services/chat_turns.py`, `backend/app/services/profile_drafts.py`, `backend/app/services/profile_approval.py`, focused activation helper if needed, `backend/app/tools/profile.py`, `backend/app/repositories/agent_runs.py`, `backend/app/repositories/tool_executions.py`, `backend/tests/integration/test_cv_manager_api.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/integration/test_interrupt_resume.py`
  - Allowed Files: listed CV route/schema/reprocess/approval/run/tool/test files and router registration only; exclude deletion coordinator, graph projection/rebuild/observability beyond existing sync invocation, Agent topology, active-CV reader, frontend, migrations, and infrastructure.
  - Agent Work:
    1. Use `git grep` to trace chat-turn creation, stream opening, upload-to-turn, proposal, singleton draft lock, interrupt/resume, approval preflight/transaction, sync, and terminal replay callers.
    2. Add failing public API/SSE tests for active/archive eligibility, missing file, conflicting approval, draft-only state, Request Changes, Save Profile switch/same-ID re-extract, rollback, sync failure, and repeated resume.
    3. Add one thin route and reuse the normal run/runner/proposal/approval services; extract focused activation logic instead of growing oversized owners or creating a second SSE path.
    4. Verify exact source ownership on message/run/tool rows and all one-active/file/hash/document/profile invariants before commit.
  - Output: Dedicated reprocess SSE action with approval-only active selection and unchanged failure/request-changes truth.
  - A1 Outcome: Active and archived CVs can be re-extracted through the existing approval flow without changing active truth before approval.
  - A2 Review Focus: Thin-route reuse, all proposal/approval callers, no second runner/SSE store, state eligibility, source ownership, singleton lock, transaction order, rollback, terminal replay, and truthful sync failure.
  - A3 Batch Evidence: M9-02/M9-06/M9-09 reprocess, interrupt, approval selection, rollback, idempotency, and API status rows.
  - Acceptance:
    - The route emits the normal validated SSE sequence and approval card from one CV-scoped run and records explicit attachment ownership.
    - Pending, failed, and Request Changes paths preserve the prior active attachment/document/profile; Save Profile alone performs the exact atomic switch or same-active document refresh.
    - Invalid state/file/chunk/lock conditions return stable safe codes without mutation, and repeated terminal resume produces no graph/tool replay.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_cv_manager_api.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py -q` -> PASS evidence: exit `0` with active/archive, SSE, approval, rollback, and idempotency assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A required second runner/SSE path or architecture change is `BLOCKED_SCOPE_CONFLICT`; unresolved approval ownership is `BLOCKED_SOURCE_CONFLICT`; unavailable test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/api/cvs.py`, `backend/app/main.py`, `backend/app/schemas/cv_manager.py`, `backend/app/services/{chat_turns,profile_drafts,profile_approval}.py` plus one focused activation helper, `backend/app/tools/profile.py`, `backend/app/repositories/{agent_runs,tool_executions}.py`, `backend/tests/integration/test_{cv_manager_api,profile_approval,interrupt_resume}.py`.

## Mandatory Batch04 - Retryable Complete Non-Active CV Deletion

### Goal

Delete one eligible non-active CV and every resource it owns across SQLite, checkpoints, storage, and Neo4j through one idempotent retryable coordinator while preserving active/shared/unrelated data.

### Dependencies

- `(03A)` is accepted; ownership, draft locks, active selection, and CV-scoped runs are established.

### Scope Boundary

Own deletion eligibility, legacy ownership resolution, chat redaction, exact graph-branch deletion, external cleanup sequencing, final relational cleanup, DELETE transport, and fault tests. Exclude graph sync/rebuild/observability, active selection, Agent retrieval, and frontend.

### Tasks

- [ ] (04A): Delete one non-active CV completely through the retryable coordinator
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch04 - Retryable Complete Non-Active CV Deletion` > `(04A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Complete Non-Active Deletion` and `## Implementation` item 5; `docs/plans/Master_plan.md` > `### 6.3 Foreign-key and deletion rules`, `### 6.4 Transaction boundaries`, `### 10.5 CV Manager reprocessing and deletion`, and `### 14.1 API rules`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(04A)` -> task authority
    - source-delete: repository `docs/plans/Plan_9.md` > `### Complete Non-Active Deletion` -> deletion authority
    - storage-owner: repository `backend/app/storage/attachments.py` and `backend/app/services/attachment_resolve.py` -> validated file ownership/removal
    - checkpoint-owner: repository `backend/app/agent/checkpoint.py` -> per-run checkpoint deletion
    - relational-owner: repository `backend/app/repositories/attachments.py`, `chat_messages.py`, `agent_runs.py`, and `tool_executions.py` -> transition/redaction/cascade owners
    - graph-owner: repository `backend/app/graph/sync_shared.py` and `backend/app/graph/driver.py` -> focused exact branch deletion conventions
    - validation-delete: repository `docs/plans/Plan_9.md` > `## Verification` > `Complete deletion` -> required fault evidence
  - Source Requirements:
    - Reject the active row before mutation; allow archived, failed, unreferenced staged, and retryable deleting rows, including confirmed cleanup of a CV-owned pending approval.
    - First mark `deleting`, redact every linked message to `[CV deleted]`, clear structured payload/ownership safely, and remove matching drafts in a short transaction.
    - Delete matching checkpoints by resolved CV-owned run IDs, remove the retained file through the existing storage abstraction, and delete only the exact `CV.id` branch; each operation is idempotent.
    - Finalize by deleting CV-scoped runs/tool cascades, directly CV-owned tools on unrelated runs, then the attachment/documents/chunks. Preserve active Candidate/profile, Jobs, Skills, seed edges, unrelated files/runs/tools/messages.
    - Historical ownership uses one shared resolver over validated structured payload/tool-result shapes; never regex free-form chat.
    - Any external failure retains a `deleting` row and stable retry code; return `204` only after all owned resources and metadata are gone.
  - Dependencies: `(03A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 10800
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/cv_manager.py`, focused ownership/deletion helper if needed, `backend/app/api/cvs.py`, `backend/app/schemas/cv_manager.py`, `backend/app/repositories/attachments.py`, `backend/app/repositories/chat_messages.py`, `backend/app/repositories/agent_runs.py`, `backend/app/repositories/tool_executions.py`, `backend/app/agent/checkpoint.py`, `backend/app/graph/delete_cv.py`, `backend/tests/integration/test_cv_manager_deletion.py`, `backend/tests/integration/test_cv_manager_api.py`
  - Allowed Files: listed deletion/API/schema/repository/checkpoint/graph-delete/test files only; exclude graph sync/rebuild/observability, profile activation/extraction, Agent graph/tools, frontend, migrations, infrastructure, and unrelated storage behavior.
  - Agent Work:
    1. Use `git grep` to trace every attachment delete/transition, storage removal, checkpoint cleanup, chat payload, run/tool projection, cascade, and graph-delete caller; identify validated legacy payload shapes.
    2. Add failing active-guard, pending-approval, legacy-owner, per-step fault injection, retry, already-complete, and cross-store preservation tests.
    3. Implement one focused coordinator with explicit short transactions and idempotent external steps; reuse repositories/storage/checkpoint/driver instead of duplicating I/O.
    4. Implement an exact allowlisted `CV.id` graph deletion and prove no broad detach/delete or shared-label removal is reachable.
    5. Verify every partial step remains safely retryable and transport returns `204` only after final absence.
  - Output: One safe retryable DELETE action that removes exactly one non-active CV's owned resources.
  - A1 Outcome: Eligible CV deletion is complete, idempotent, and failure-resumable without harming active, shared, or unrelated data.
  - A2 Review Focus: Root deletion owner/callers, active preguard, legacy resolver safety, transaction/external ordering, idempotency, fault matrix, graph query allowlist, false-success prevention, and preservation assertions.
  - A3 Batch Evidence: M9-03/M9-06/M9-09 deletion lifecycle, redaction, cross-store cleanup, retry, API, and preservation matrix.
  - Acceptance:
    - Active deletion causes no mutation and returns `409 CV_ACTIVE_DELETE_FORBIDDEN`.
    - Every eligible state reaches full absence only after chat redaction, draft/checkpoint/file/exact graph/run/tool/document/chunk/attachment cleanup; a repeated deleting request resumes safely.
    - Fault injection at each external boundary leaves truthful `deleting` metadata and retry guidance, and tests prove shared Jobs/Skills/Candidate/profile plus unrelated records/files survive.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_cv_manager_deletion.py -q` -> PASS evidence: exit `0` with active guard, every fault/retry boundary, cross-store absence, and preservation assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_cv_manager_api.py tests/integration/test_interrupt_resume.py -q` -> PASS evidence: exit `0` with status/idempotency/pending-approval compatibility; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A root cleanup fix outside Allowed Files is `BLOCKED_SCOPE_CONFLICT`; ambiguous historical ownership authority is `BLOCKED_AMBIGUOUS_REF`; unavailable filesystem/SQLite/Neo4j/checkpoint test seams are `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/services/cv_manager.py` plus one focused ownership/deletion helper, `backend/app/api/cvs.py`, `backend/app/schemas/cv_manager.py`, `backend/app/repositories/{attachments,chat_messages,agent_runs,tool_executions}.py`, `backend/app/agent/checkpoint.py`, `backend/app/graph/delete_cv.py`, `backend/tests/integration/test_{cv_manager_deletion,cv_manager_api}.py`.

## Mandatory Batch05 - Owned CV Graph Projection and Rebuild

### Goal

Project every approved retained CV through fixed graph identities, root observability at the active CV, preserve exact deletion ownership, and rebuild the complete derived model from SQLite without provider calls.

### Dependencies

- `(04A)` is accepted; exact CV branch deletion and all relational ownership rules are available.

### Scope Boundary

Own CV graph sync payloads, constraints, approval sync integration, rebuild snapshot/operations, active-CV consistency, bounded graph observability, schemas, and focused tests. Exclude SQLite schema/extraction, deletion coordination, Agent retrieval, and frontend rendering.

### Tasks

- [ ] (05A): Synchronize approved CV branches with fixed graph identities
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch05 - Owned CV Graph Projection and Rebuild` > `(05A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Neo4j Projection And Rebuild` and `## Implementation` item 6; `docs/plans/Master_plan.md` > `### 6.6 Neo4j identity mapping`, `## 8. Neo4j Derived Model`, and `### 21.1 Direct sync rule`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(05A)` -> task authority
    - source-graph: repository `docs/plans/Plan_9.md` > `### Neo4j Projection And Rebuild` -> CV graph authority
    - master-graph: repository `docs/plans/Master_plan.md` > `## 8. Neo4j Derived Model` -> fixed labels/properties/relationships
    - sync-owner: repository `backend/app/graph/sync_candidate.py`, `sync_job.py`, and `sync_shared.py` -> current direct-sync/parameter conventions
    - approval-owner: repository `backend/app/services/profile_approval.py` -> post-commit selected-CV sync integration
    - validation-cv-graph: repository `docs/plans/Plan_9.md` > `## Verification` > `Graph behavior` -> sync/delete evidence
  - Source Requirements:
    - Use fixed `CV`, `CVSection`, and `CVEntry` labels/IDs from Master; user headings are properties only.
    - Project every retained approved CV document with stable section/entry ordinal order and bounded safe entry preview; never copy bodies, bullets, arbitrary attributes, chunks, or PDF bytes.
    - Maintain exactly one `PROJECTS_TO` from the active CV to Candidate and remove it from the former active branch while preserving archived branches.
    - Reuse idempotent parameterized `MERGE`, shared skill projection, and SQLite-first/post-commit failure behavior.
  - Dependencies: `(04A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/graph/constraints.py`, `backend/app/graph/sync_cv.py`, `backend/app/graph/delete_cv.py`, `backend/app/graph/sync_shared.py`, `backend/app/services/profile_approval.py` or focused post-commit sync helper, `backend/tests/unit/test_cv_graph.py`, `backend/tests/integration/test_profile_approval.py`
  - Allowed Files: listed graph constraint/sync/delete/shared files, narrow approval sync integration, and focused tests only; exclude rebuild/observability until `(05B)`, SQLite extraction/schema, deletion coordinator, Agent/tools, frontend, and infrastructure.
  - Agent Work:
    1. Trace every Candidate/Job/Skill sync, constraint, Cypher-template, post-approval, and graph-delete caller; reuse shared timestamp/result/skill helpers.
    2. Add failing deterministic payload, fixed-label, preview-bound, idempotency, active-switch, archived-branch, exact-delete, and sync-failure tests.
    3. Implement one focused `sync_cv` owner and extend post-commit approval sync without copying Candidate/Skill business logic.
    4. Assert all Cypher is parameterized/allowlisted, payloads are stably ordered, and reruns converge to one active `PROJECTS_TO`.
  - Output: Idempotent complete approved-CV branches with exactly one active Candidate projection edge.
  - A1 Outcome: Approved retained CV documents synchronize through fixed safe graph identities and active selection is represented exactly once.
  - A2 Review Focus: Identity/property allowlists, payload bounds/order, no raw content, all sync/delete callers, idempotency, former-active edge removal, archived retention, and SQLite-first failure handling.
  - A3 Batch Evidence: M9-04/M9-09 fixed-label, safe-property, all-approved-branch, active-edge, exact-delete, and sync-failure rows.
  - Acceptance:
    - Sync creates only Master allowlisted CV nodes/edges with deterministic scoped IDs and safe bounded properties.
    - All approved documents remain rebuildable/deletable by attachment ID while exactly the active branch projects to Candidate.
    - Repeated sync/delete is idempotent and never removes shared Candidate/Job/Skill/seed data.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_cv_graph.py tests/integration/test_profile_approval.py tests/integration/test_cv_manager_deletion.py -q` -> PASS evidence: exit `0` with payload, activation, exact-delete, and preservation assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Required dynamic labels/raw graph content is `BLOCKED_SCOPE_CONFLICT`; conflicting graph identity authority is `BLOCKED_SOURCE_CONFLICT`; unavailable graph fakes/tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/graph/{constraints,sync_cv,delete_cv,sync_shared}.py`, `backend/app/services/profile_approval.py` plus one focused post-commit sync helper, `backend/tests/unit/test_cv_graph.py`, `backend/tests/integration/test_{profile_approval,cv_manager_deletion}.py`.

- [ ] (05B): Rebuild and observe the active CV branch without provider calls
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch05 - Owned CV Graph Projection and Rebuild` > `(05B)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Neo4j Projection And Rebuild` and `## Implementation` item 6; `docs/plans/Master_plan.md` > `### 14.1 API rules` and `### 21.3 Rebuild command`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(05B)` -> task authority
    - source-rebuild-observe: repository `docs/plans/Plan_9.md` > `### Neo4j Projection And Rebuild` -> rebuild/observability authority
    - rebuild-owner: repository `backend/app/graph/rebuild.py`, `rebuild_snapshot.py`, `rebuild_ops.py`, and `rebuild_target.py` -> sole current rebuild path
    - observability-owner: repository `backend/app/graph/observability.py`, `backend/app/services/observability.py`, and `backend/app/schemas/observability.py` -> bounded read projection
    - consistency-owner: repository `backend/app/graph/consistency.py` -> current Candidate/Job revision state
    - validation-graph: repository `docs/plans/Plan_9.md` > `## Verification` > `Graph behavior` -> required evidence
  - Source Requirements:
    - Extend the sole rebuild path to load every approved document, recreate fixed CV constraints/branches, and assign `PROJECTS_TO` only to active CV; call no provider and mutate no SQLite row.
    - Clear only JobAgent-owned labels/relationships and preserve the existing exclusive Compose target/embedding preflight.
    - Graph observability selects only the active CV branch plus existing Candidate/Job/Skill data under Master caps/order/allowlists and returns no full body/arbitrary attribute.
    - Staleness additionally compares active attachment ID and document source hash; legacy active CV emits its metadata node without sections and remains reprocess-required.
  - Dependencies: `(05A)` accepted.
  - User Action: None for automated fake-backed validation.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 9000
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/graph/rebuild.py`, `backend/app/graph/rebuild_snapshot.py`, `backend/app/graph/rebuild_ops.py`, `backend/app/graph/constraints.py`, `backend/app/graph/consistency.py`, `backend/app/graph/observability.py`, focused CV observability helper if needed, `backend/app/schemas/observability.py`, `backend/app/services/observability.py`, `backend/tests/unit/test_cv_graph.py`, `backend/tests/unit/test_observability_graph.py`, `backend/tests/integration/test_observability_api.py`, `backend/tests/integration/test_graph_rebuild_contracts.py`
  - Allowed Files: listed graph/rebuild/consistency/observability/schema/service/test files and focused extracted CV-observability module; exclude a second rebuild entry point, SQLite writes/migrations, deletion coordinator, Agent/tools, frontend, package manifests, and infrastructure.
  - Agent Work:
    1. Trace all rebuild snapshot/clear/count/constraint/target, graph consistency, observability query/parser, schema, and test callers.
    2. Add failing retained-document rebuild, active-edge, legacy-active, active-ID/hash stale, caps/order/allowlist, unavailable, and provider-prohibition tests.
    3. Extend existing snapshot/ops/observability owners; split CV projection/query parsing from the already oversized observability module instead of appending a second read model.
    4. Prove rebuild/reads use stored documents/embeddings only, preserve exclusive target safety, and report deterministic counts/truncation/status.
  - Output: Provider-free full CV graph rebuild and bounded active-CV observability with revision/hash truth.
  - A1 Outcome: The sole rebuild reconstructs every approved CV branch and observability safely exposes only the active bounded branch.
  - A2 Review Focus: One rebuild path, no provider/SQLite mutation, clear scope, constraints/counts, active-edge semantics, active ID/hash staleness, legacy state, caps/allowlists, module size, and current tests.
  - A3 Batch Evidence: M9-04/M9-08/M9-09 rebuild, active projection, stale/unavailable/legacy, cap, regression, and provider-prohibition matrix.
  - Acceptance:
    - Rebuild recreates all approved CV branches and only the active `PROJECTS_TO` using stored SQLite artifacts, with no provider call or SQLite mutation.
    - Ready observability includes at most one active CV, 20 sections, 60 entries, existing Candidate/Job/Skill caps, allowlisted edges, stable order, and complete truncation metadata.
    - Active ID/source-hash mismatch is stale; unavailable and legacy/no-active states are safe and typed; existing D3 response fields remain compatible.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_cv_graph.py tests/unit/test_observability_graph.py tests/integration/test_observability_api.py tests/integration/test_graph_rebuild_contracts.py -q` -> PASS evidence: exit `0` with rebuild, active branch, stale, caps, exact ownership, and no-provider assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A required second rebuild/read path is `BLOCKED_SCOPE_CONFLICT`; unresolved active-hash authority is `BLOCKED_SOURCE_CONFLICT`; unavailable graph/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/graph/{rebuild,rebuild_snapshot,rebuild_ops,constraints,consistency,observability}.py` plus one focused CV-observability helper, `backend/app/schemas/observability.py`, `backend/app/services/observability.py`, `backend/tests/unit/test_{cv_graph,observability_graph}.py`, `backend/tests/integration/test_{observability_api,graph_rebuild_contracts}.py`.

## Mandatory Batch06 - Bounded Active-CV Agent Retrieval

### Goal

Give the single Agent compact active-CV identity/outline context and one durable read-only tool that serves active-only section/search/chunk pages under independent result, character, and cursor bounds.

### Dependencies

- `(05A)` and `(05B)` are accepted; approved-document/legacy state and active source hashes are stable.

### Scope Boundary

Own compact context loading, active reader/cursors, the seventh tool, durable execution integration, prompt policy, and direct tests. Exclude graph topology changes, CV writes/deletion, public CV APIs, frontend, and alternate retrieval infrastructure.

### Tasks

- [ ] (06A): Load compact active outlines and serve bounded active-only reads
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch06 - Bounded Active-CV Agent Retrieval` > `(06A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Bounded Agent Retrieval` and `## Implementation` item 7; `docs/plans/Master_plan.md` > `### 12.3 Agent state`, `### 12.4 Memory policy`, and `### 13.7 read_active_cv`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(06A)` -> task authority
    - source-reader: repository `docs/plans/Plan_9.md` > `### Bounded Agent Retrieval` -> context/read/cursor authority
    - context-owner: repository `backend/app/agent/context.py` and `backend/app/agent/state.py` -> current candidate/recent-context boundary
    - document-owner: repository `backend/app/repositories/cv_documents.py` and `backend/app/repositories/attachment_text_chunks.py` -> approved document/chunk reads
    - cursor-owner: repository `backend/app/schemas/observability.py` and `backend/app/services/observability.py` -> opaque bounded cursor conventions
    - validation-reader: repository `docs/plans/Plan_9.md` > `## Verification` > `Agent bounded reads` -> required evidence
  - Source Requirements:
    - `active_cv_context` contains only active attachment ID, extraction version/source hash, bounded section IDs/headings/kinds/counts/ranges, and legacy reprocess-required state; never bodies/chunks.
    - Resolve active attachment server-side. Implement `section`, `search`, and `chunk` with strict selectors, stable source order, independent `max_results`/`max_chars` bounds, truncation, and opaque next cursor.
    - Bind cursor to active attachment/source hash/mode/selector/last stable identity and return `ACTIVE_CV_CHANGED` after selection/revision changes.
    - Legacy active CV supports bounded search/chunk over existing chunks and returns `CV_DOCUMENT_REPROCESS_REQUIRED` for section mode.
    - `ponytail:` O(n) structured-entry/chunk search is intentional for one bounded local CV; FTS is only a measured future upgrade.
  - Dependencies: `(05A)` and `(05B)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/active_cv_reader.py`, `backend/app/agent/active_cv_context.py`, `backend/app/agent/context.py`, `backend/app/agent/state.py`, `backend/app/repositories/cv_documents.py`, `backend/app/repositories/attachment_text_chunks.py`, `backend/app/schemas/cv_document.py`, `backend/tests/unit/test_active_cv_reader.py`, `backend/tests/unit/test_agent_context.py`
  - Allowed Files: listed active-reader/context/state/repository/schema/tests and one focused cursor helper; exclude tool registry/executor/prompt until `(06B)`, Agent graph topology, CV writes/API, graph, frontend, migrations, and new dependencies.
  - Agent Work:
    1. Trace every candidate/recent context load, initial state, prompt formatting, document/chunk list/detail, and cursor helper caller.
    2. Add failing outline-only, all-mode, selector/auth, legacy, result/character cap, oversized-record, pagination/order, malformed cursor, and active-switch invalidation tests.
    3. Extract active-CV context from the oversized generic context module and implement one pure/read-only service over approved document/chunk repositories.
    4. Keep search bounded/local with the required `ponytail:` ceiling comment and prove responses expose no archived body, PDF/path, prompt, or unbounded content.
  - Output: Compact active context and deterministic bounded active-only reader pages.
  - A1 Outcome: The Agent can load only an outline by default and a service can safely page active CV evidence under all documented bounds.
  - A2 Review Focus: Context/body separation, server-side active authorization, mode validation, cursor binding/invalidation, both caps, source order, legacy behavior, O(n) ceiling comment, no new retrieval dependency, and module split.
  - A3 Batch Evidence: M9-05/M9-09 context outline, active authorization, all-mode, cap, cursor, legacy, and no-full-prompt rows.
  - Acceptance:
    - Context snapshots never contain section bodies, entries, chunks, PDF bytes, paths, or archived data.
    - Reader modes return only active-CV records in stable order with independent result/character caps and correctly bound cursors/truncation metadata.
    - Active switch invalidates prior cursors, and legacy section/search/chunk behavior matches the exact typed contract.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/unit/test_active_cv_reader.py tests/unit/test_agent_context.py -q` -> PASS evidence: exit `0` with outline, authorization, mode, cap, cursor, legacy, and invalidation assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A required archived/vector/semantic retrieval path is `BLOCKED_SCOPE_CONFLICT`; ambiguous cursor revision authority is `BLOCKED_SOURCE_CONFLICT`; unavailable test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/services/active_cv_reader.py`, `backend/app/agent/{active_cv_context,context,state}.py`, `backend/app/repositories/{cv_documents,attachment_text_chunks}.py`, `backend/app/schemas/cv_document.py`, `backend/tests/unit/test_{active_cv_reader,agent_context}.py`.

- [ ] (06B): Register the seventh tool and enforce narrow durable read policy
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch06 - Bounded Active-CV Agent Retrieval` > `(06B)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Bounded Agent Retrieval` and `## Implementation` item 7; `docs/plans/Master_plan.md` > `### 12.1 One Agent, one controlled loop`, `### 12.6 Tool loop limits`, `### 13.7 read_active_cv`, and `### 13.8 Tool authorization matrix`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(06B)` -> task authority
    - source-tool: repository `docs/plans/Plan_9.md` > `### Bounded Agent Retrieval` -> tool/prompt/log authority
    - registry-owner: repository `backend/app/tools/registry.py` and `backend/app/tools/profile.py` -> production tool registration pattern
    - durable-owner: repository `backend/app/services/tool_execution.py` and `backend/app/repositories/tool_executions.py` -> replay/status/result contract
    - graph-prompt-owner: repository `backend/app/agent/graph.py` and `backend/app/agent/prompt.py` -> one ToolNode, iteration guard, and system policy
    - validation-tool: repository `docs/plans/Plan_9.md` > `## Verification` > `Agent bounded reads` -> integration/topology evidence
  - Source Requirements:
    - Register `read_active_cv` as exactly the seventh production tool in the existing registry/ToolNode/durable executor; add no Agent node and keep the maximum six tool iterations.
    - Use `(06A)` as the sole body-reading service. Persist source attachment ownership before result storage and replay terminal `ToolResult` by existing invocation identity.
    - Store selector/count metadata only in argument summaries/logs, never returned CV bodies; bounded body data exists only in validated result data and is deleted with CV ownership.
    - Prompt policy requests the narrowest mode, forbids automatic cursor exhaustion, and allows multiple pages only when genuinely required by the user.
  - Dependencies: `(06A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/tools/active_cv.py`, `backend/app/tools/registry.py`, `backend/app/tools/__init__.py`, `backend/app/services/tool_execution.py`, `backend/app/repositories/tool_executions.py`, `backend/app/agent/context.py`, `backend/app/agent/graph.py`, `backend/app/agent/prompt.py`, `backend/tests/integration/test_active_cv_tool.py`, `backend/tests/unit/test_agent_context.py`, `backend/tests/unit/test_agent_graph.py`, existing exact-six registry tests
  - Allowed Files: listed tool/registry/durable/context/graph/prompt/test files and exact-count expectation updates; exclude new Agent nodes/topology, CV reader behavior from `(06A)` except defect repair, CV writes/API, graph projection, frontend, settings loop limit, and new dependencies.
  - Agent Work:
    1. Use `git grep` to find every exact-six registry/prompt/test expectation, durable tool wrapper, source-ownership write, replay path, and ToolNode/iteration assertion.
    2. Add failing tool authorization, ownership, summary redaction, all-mode result, replay, failure, prompt snapshot, exact-seven registry, one-ToolNode, and six-iteration tests.
    3. Implement a thin tool adapter over `(06A)` and register it through existing dependency injection/durable execution; update only stale exact-count expectations.
    4. Prove logs omit document bodies and graph topology/loop limit remain unchanged.
  - Output: One seventh production tool with active-only bounded evidence and unchanged single-Agent topology.
  - A1 Outcome: `read_active_cv` executes and replays through the existing durable ToolNode path without exposing unbounded or non-active CV content.
  - A2 Review Focus: Exact-seven registry, one ToolNode/no node changes, six-iteration guard, authorization, durable identity/replay/status coupling, source ownership, log redaction, prompt policy, and all updated exact-count callers.
  - A3 Batch Evidence: M9-05 seventh-tool, durable replay, prompt, authorization, ownership/redaction, and topology-regression rows.
  - Acceptance:
    - Production registry exposes exactly seven named tools and the graph retains one decision node, one ToolNode, and the six-iteration limit.
    - `read_active_cv` returns only `(06A)` bounded data, persists active source ownership, and replays terminal results without another read.
    - Prompt/log snapshots prove compact-outline default, narrow mode guidance, no automatic cursor walk, and no body in argument summaries.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest tests/integration/test_active_cv_tool.py tests/unit/test_active_cv_reader.py tests/unit/test_agent_context.py tests/unit/test_agent_graph.py -q` -> PASS evidence: exit `0` with tool, replay, redaction, prompt, exact-seven, and unchanged-topology assertions; freshness: final attempt only.
    - Required: `Set-Location backend; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A required new Agent node/loop change is `BLOCKED_SCOPE_CONFLICT`; unresolved durable ownership/replay authority is `BLOCKED_SOURCE_CONFLICT`; unavailable test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/tools/{active_cv,registry,__init__}.py`, `backend/app/services/tool_execution.py`, `backend/app/repositories/tool_executions.py`, `backend/app/agent/{context,graph,prompt}.py`, `backend/tests/integration/test_active_cv_tool.py`, `backend/tests/unit/test_{active_cv_reader,agent_context,agent_graph}.py`, existing exact-six registry test files discovered in Agent Work.

## Mandatory Batch07 - CV Manager Frontend Actions

### Goal

Convert the implemented CV History experience into an accessible CV Manager with safe reprocess/delete actions and focused cache updates while preserving the refreshed shell, D3 graph, chat reducer, and responsive behavior.

### Dependencies

- `(03A)`, `(04A)`, `(05B)`, and `(06B)` are accepted; API/SSE/graph/status contracts are stable.

### Scope Boundary

Own typed CV Manager transport/parsing, sidebar-local action state, existing-SSE delegation, focused cache invalidation, panel/dialog composition, graph type extension, styles, and frontend tests. Exclude backend changes, shell/graph redesign, a second chat store, package upgrades, and new UI/graph dependencies.

### Tasks

- [ ] (07A): Add typed CV Manager actions and existing-SSE/cache integration
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch07 - CV Manager Frontend Actions` > `(07A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Frontend CV Manager` and `## Implementation` item 8; `docs/plans/Master_plan.md` > `### 15.6 Observability sidebar boundaries`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(07A)` -> task authority
    - source-frontend-state: repository `docs/plans/Plan_9.md` > `### Frontend CV Manager` -> action/cache/error authority
    - observability-client-owner: repository `frontend/src/features/observability/api.ts`, `types.ts`, and `state.ts` -> current typed client/cache
    - sse-owner: repository `frontend/src/lib/api/chat.ts`, `frontend/src/features/chat/ChatPage.tsx`, and `reducer.ts` -> sole stream/reducer path
    - composition-owner: repository `frontend/src/app/App.tsx` and `frontend/src/features/profile/CvSidebar.tsx` -> sidebar-to-chat callback ownership
    - validation-client: repository `docs/plans/Plan_9.md` > `## Verification` > `Frontend focused` -> typed action evidence
  - Source Requirements:
    - Add typed reprocess/delete calls and safe status parsing; reprocess feeds the normal SSE callbacks/reducer and focuses the existing approval card.
    - Track pending action per attachment, prevent duplicates, retain cached safe data after failure, and keep active selection unchanged until approved data refreshes.
    - On confirmed delete success invalidate only CV list, selected chunks, runs, profile summary, and graph; select a safe remaining row. Partial failure retains row/cache and safe retry guidance.
    - Extend existing graph/client types for fixed CV/section/entry nodes and edges without duplicating parsers or hidden-field inference.
  - Dependencies: `(03A)`, `(04A)`, `(05B)`, and `(06B)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/observability/api.ts`, focused `cvManagerTypes.ts`/`cvManagerState.ts` extracted from `types.ts`/`state.ts`, `frontend/src/features/observability/types.ts`, `frontend/src/features/observability/state.ts`, `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/lib/api/chat.ts` or existing SSE consumer, `frontend/src/test/cv-manager-api.test.ts`, `frontend/src/test/observability-api.test.ts`, `frontend/src/test/observability-state.test.tsx`, `frontend/src/test/sse-reducer.test.ts`
  - Allowed Files: listed typed client/state/SSE/composition/test files and focused extracted CV Manager type/state modules; exclude visual panel/dialog/styles until `(07B)`, backend, package manifests/lockfile, graph simulation/viewport behavior, and a second reducer/store.
  - Agent Work:
    1. Use `git grep` to trace every observability parser/fetch/cache/action, upload-to-chat callback, stream callback, approval focus, and graph type consumer.
    2. Add failing parser/transport, request-order, duplicate-action, SSE delegation, activation refresh, exact invalidation, partial-error, and safe-selection tests.
    3. Extract CV Manager-specific types/state from existing oversized modules and reuse the sole SSE parser/reducer; do not duplicate fetch/error/cache logic.
    4. Prove old lazy-cache/error semantics and unrelated tab/chat state remain unchanged.
  - Output: Typed CV Manager action/state layer connected to the existing chat stream and focused cache owners.
  - A1 Outcome: Reprocess/delete actions have safe deterministic client state without a second SSE or observability cache implementation.
  - A2 Review Focus: Parser redaction, one SSE reducer, action deduplication, race/request ordering, exact invalidation, safe fallback selection, prior-cache preservation, graph type compatibility, and reduced module size.
  - A3 Batch Evidence: M9-06/M9-07/M9-08 client transport, SSE reuse, pending/error, invalidation, and regression rows.
  - Acceptance:
    - Typed client rejects forbidden/internal fields and maps every documented reprocess/delete status safely.
    - Reprocess events traverse the current stream callbacks/reducer and approval focus; no second stream/store/reducer exists.
    - Success/failure/race tests prove only documented caches change and prior safe data/selection behavior remains truthful.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/cv-manager-api.test.ts src/test/observability-api.test.ts src/test/observability-state.test.tsx src/test/sse-reducer.test.ts` -> PASS evidence: exit `0` with transport/parser/cache/SSE assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: A required second SSE/cache owner is `BLOCKED_SCOPE_CONFLICT`; undocumented backend response ambiguity is `BLOCKED_SOURCE_CONFLICT`; unavailable Node tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/observability/{api,types,state,cvManagerTypes,cvManagerState}.ts`, `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/features/chat/reducer.ts`, `frontend/src/lib/api/chat.ts`, `frontend/src/test/{cv-manager-api,observability-api,observability-state,sse-reducer}.test.ts*`.

- [ ] (07B): Render the accessible CV Manager without redesigning the refreshed UI
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch07 - CV Manager Frontend Actions` > `(07B)`
  - Source of Truth: `docs/plans/Plan_9.md` > `### Frontend CV Manager` and `## Implementation` item 8; `docs/plans/Master_plan.md` > `### 15.1 Layout` and `### 15.2 Sidebar`; `docs/superpowers/plans/2026-07-16-observability-sidebar-ui-refresh.md` > `## Scope And File Map`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(07B)` -> task authority
    - source-ui: repository `docs/plans/Plan_9.md` > `### Frontend CV Manager` -> row/action/dialog/accessibility authority
    - refresh-baseline: repository `docs/superpowers/plans/2026-07-16-observability-sidebar-ui-refresh.md` > `## Scope And File Map` -> preserved shell/module/graph baseline
    - panel-owner: repository `frontend/src/features/observability/CvHistoryPanel.tsx`, `ObservabilitySidebar.tsx`, `ObservabilityTabList.tsx`, and `ObservabilityPanelHeader.tsx` -> current focused panel/navigation
    - graph-owner: repository `frontend/src/features/observability/GraphPanel.tsx`, `graphPresentation.ts`, and `GraphSemanticList.tsx` -> current D3/fallback projection
    - astryx-rules: repository `frontend/AGENTS.md` -> pinned component discovery/styling authority
    - validation-ui: repository `docs/plans/Plan_9.md` > `## Verification` > `Frontend focused` -> interaction/layout evidence
  - Source Requirements:
    - Rename the tab/panel to CV Manager. Show one Active badge; active row offers Open/Download and Re-extract, archived row offers Open/Download, Make active, and Delete, and active never exposes Delete.
    - Delete uses an accessible confirmation dialog naming the file and warning the scope; pending actions are disabled and partial failures retain the row/recovery message.
    - Reprocessing focuses the existing approval card and does not change active badge until approval-driven refresh.
    - Preserve vertical rail, `13/47/40` desktop proportions, resize/collapse/mobile drawer, typography/colors/list density/loading primitives, D3 simulation/pan/zoom/fit/reset, semantic fallback, and keyboard/focus behavior.
    - Inspect pinned Astryx documentation before adding dialog props or components; use existing icons/components/tooltips and token styling.
  - Dependencies: `(07A)` accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 10800
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/observability/CvManagerPanel.tsx`, `frontend/src/features/observability/CvDeleteDialog.tsx`, `frontend/src/features/observability/CvHistoryPanel.tsx` removed or compatibility-export only if required, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/features/observability/ObservabilityTabList.tsx`, `frontend/src/features/observability/GraphPanel.tsx`, `frontend/src/features/observability/graphPresentation.ts`, `frontend/src/features/observability/GraphSemanticList.tsx`, `frontend/src/features/observability/observability.css`, `frontend/src/test/cv-manager.test.tsx`, `frontend/src/test/observability-sidebar.test.tsx`, `frontend/src/test/observability-navigation.test.tsx`, `frontend/src/test/observability-panels.test.tsx`, `frontend/src/test/graph-interaction.test.tsx`
  - Allowed Files: listed focused observability panels/navigation/graph presentation/styles/tests plus shared synthetic observability fixtures; exclude AppShell/theme redesign, chat reducer/API behavior from `(07A)` except defect repair, graph simulation/viewport control semantics, backend, package manifests/lockfile, and new dependencies.
  - Agent Work:
    1. Run `npx astryx build "accessible CV manager list with destructive confirmation"`, then inspect the exact pinned dialog/button/list/status component docs; use `git grep` to trace current panel, icon, tooltip, cache-state, layout, graph, and test owners.
    2. Add failing active/archive action, confirmation/focus, duplicate disable, failure recovery, approval focus, graph CV node, desktop proportion, mobile, overlap, and keyboard tests.
    3. Replace the focused history panel with `CvManagerPanel`/`CvDeleteDialog` using `(07A)` state; remove stale history-only presentation instead of retaining duplicate logic.
    4. Extend only graph mapping/display metadata needed for fixed CV nodes; preserve simulation, controls, semantic fallback, and all established responsive styles.
  - Output: Accessible action-capable CV Manager within the unchanged refreshed observability shell.
  - A1 Outcome: Users can safely re-extract, make active through approval, and confirm non-active deletion without layout, graph, or chat regression.
  - A2 Review Focus: Action visibility/guard, confirmation semantics/focus, pending/error/cache states, Astryx rules, no duplicate history panel, active badge timing, D3/fallback preservation, desktop/mobile overlap, keyboard access, and no raw/internal data.
  - A3 Batch Evidence: M9-07/M9-08/M9-09 action/accessibility/error, active graph display, refreshed-layout, D3 interaction, and responsive regression rows.
  - Acceptance:
    - Active/archive rows expose exactly the permitted actions and one clear Active state; Delete cannot be initiated for active data.
    - Confirmation names the target and scope, duplicate input is disabled, partial failure stays visible/retryable, and success selects safely after focused invalidation.
    - Existing rail/resize/collapse/mobile/D3/fallback behavior, `13/47/40` proportions, chat composer clearance, and console hygiene tests remain green.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/cv-manager.test.tsx src/test/cv-manager-api.test.ts src/test/observability-sidebar.test.tsx src/test/observability-navigation.test.tsx src/test/observability-panels.test.tsx src/test/graph-interaction.test.tsx` -> PASS evidence: exit `0` with action, dialog, cache/error, graph, accessibility, and responsive assertions; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `git diff --check` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: Missing pinned Astryx component documentation is `BLOCKED_MISSING_REF`; a required shell/D3 redesign or new dependency is `BLOCKED_SCOPE_CONFLICT`; unavailable Node tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/observability/{CvManagerPanel,CvDeleteDialog,ObservabilitySidebar,ObservabilityTabList,GraphPanel,GraphSemanticList}.tsx`, `frontend/src/features/observability/graphPresentation.ts`, `frontend/src/features/observability/observability.css`, `frontend/src/test/{cv-manager,observability-sidebar,observability-navigation,observability-panels,graph-interaction}.test.ts*`, `frontend/src/test/support/observability.tsx`.

## Mandatory Batch08 - Synthetic CV Manager Release Evidence

### Goal

Publish and execute synthetic-data-only automated, Compose, direct frontend, desktop/mobile, console, deletion, graph, and bounded-Agent evidence for the complete Plan 9 increment.

### Dependencies

- Every task in Batch01 through Batch07 is accepted with matching final-attempt A1/A2 evidence.
- A user-managed root `.env`, Docker/Compose, free loopback ports, browser, and usable local ShopAIKey/Neo4j setup are available for the direct smoke. Values are never requested or recorded.

### Scope Boundary

Own `docs/acceptance/cv_manager_checklist.md` and fresh sanitized evidence only. Do not add or repair product behavior, change configuration/models, use real CVs, alter existing release evidence, or create another runtime.

### Tasks

- [ ] (08A): Publish and run the synthetic CV Manager checklist and final regressions
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_9.md` > `## Mandatory Batch08 - Synthetic CV Manager Release Evidence` > `(08A)`
  - Source of Truth: `docs/plans/Plan_9.md` > `## Implementation` item 9, `## Verification`, and `## Completion Contract`; `docs/plans/Master_plan.md` > `### 24.4 End-to-end smoke test` and `### Phase 8 - CV Manager, document-first extraction, and bounded active-CV reads`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_9.md` > `(08A)` -> task authority
    - source-verification: repository `docs/plans/Plan_9.md` > `## Verification` -> complete command/observation matrix
    - source-exit: repository `docs/plans/Master_plan.md` > `### Phase 8 - CV Manager, document-first extraction, and bounded active-CV reads` -> final exit gate
    - prior-checklist: repository `docs/acceptance/observability_sidebar_checklist.md` and `docs/acceptance/local_release_checklist.md` -> sanitized evidence conventions
    - runtime-compose: repository `infrastructure/docker-compose.yml` and `README.md` > `Setup and startup` -> existing three-service runtime
    - validation-checklist: repository `docs/plans/Plan_9.md` > `## Verification` > `Direct FE smoke` and `Scope hygiene` -> direct/manual evidence
  - Source Requirements:
    - Use synthetic digital PDFs containing Certifications and at least one unmodeled heading; never use or record real CV/JD data.
    - Cover initial extraction, active Re-extract, archived Make active through approval, Request Changes/failure preservation, bounded Agent section/search/chunk evidence, active graph switch, active-delete guard, archived deletion, and owned-data absence.
    - Verify refreshed desktop/mobile proportions, action/dialog accessibility, graph controls/fallback, cache/error recovery, browser console, health, and existing chat/matching/observability behavior.
    - Record only dated sanitized PASS/FAIL observations and stable codes/counts; prohibit PDF/chunk bodies, storage paths, prompts, tool bodies, checkpoints, stack traces, secrets, credentials, databases, and provider transcripts.
    - Any required command/smoke failure blocks acceptance; do not modify product/config to force a pass.
  - Dependencies: All prior Plan 9 task IDs accepted.
  - User Action: Before direct smoke, provide a locally usable ignored root `.env` and running Docker/browser prerequisites without sharing values. Missing/invalid setup blocks this task.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/cv_manager_checklist.md`.
  - Allowed Files: `docs/acceptance/cv_manager_checklist.md` only; exclude backend, frontend, infrastructure, package/config/environment files, existing acceptance evidence, databases/uploads, and generated real-data artifacts.
  - Agent Work:
    1. Verify every prior task acceptance/report and translate Plan 9's verification matrix into preconditions, synthetic fixtures, safe expected results, desktop/mobile/console checks, failure stops, cleanup, and evidence prohibitions.
    2. Run focused and full backend tests/static checks, full frontend tests/static/build, and scope hygiene on the accepted worktree.
    3. Start the existing Compose project with root `.env`, verify health, then execute the checklist through public UI/API/Agent boundaries only.
    4. Confirm active/archived selection, Agent reads, graph ownership, retryable deletion, unrelated Job/Skill preservation, layout screenshots, and console; record sanitized evidence only.
    5. Stop at the first required failure or unsafe disclosure and return the matching blocker; do not patch code/config in this docs-config task.
  - Output: `docs/acceptance/cv_manager_checklist.md` plus fresh sanitized A1 evidence for all Plan 9 gates.
  - A1 Outcome: Synthetic local evidence demonstrates the complete CV Manager/document-first/active-read flow without regression or sensitive-data exposure.
  - A2 Review Focus: Prior acceptance identity, checklist completeness, final-attempt freshness, synthetic-only inputs, command outputs, direct observations, screenshot/console evidence, sanitization, scope confinement, and truthful blocking.
  - A3 Batch Evidence: M9-01 through M9-09 final matrix: automated/static/build, Compose health, extraction/activation/read/graph/deletion direct smoke, UI accessibility/layout, console, and scope/data hygiene.
  - Acceptance:
    - Checklist covers every mandated synthetic success/failure/retry/preservation observation and contains no prohibited data.
    - All required automated/static/build commands pass on final attempt; Compose health reports `overall=available`; direct desktop/mobile smoke and console checks pass.
    - Active selection, bounded Agent evidence, active graph branch, active-delete guard, complete archived deletion, shared Job/Skill preservation, and no-regression observations all agree with repository/API state.
  - Validation:
    - Required: `Set-Location backend; py -3.13 -m pytest -q; py -3.13 -m ruff check app tests --no-cache; py -3.13 -m mypy app --no-incremental` -> PASS evidence: all exit `0` without real provider calls; freshness: final attempt only.
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all exit `0`; freshness: final attempt only.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180; Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS evidence: health `overall=available` with no secret output; freshness: final attempt only.
    - Required: Execute `docs/acceptance/cv_manager_checklist.md` with synthetic CVs -> PASS evidence: every mandatory extraction/reprocess/activation/read/graph/delete/desktop/mobile/console observation passes; freshness: final attempt only.
    - Required: `git diff --check` and review changed paths/tracked data against `docs/plans/Plan_9.md` -> PASS evidence: exit `0`, approved scope only, no real data/secrets/new Agent/vector store/worker/redesign; freshness: final attempt only.
  - Blocked Condition: Missing user-managed provider/Compose setup is `BLOCKED_USER_ACTION`; unavailable Docker/browser/ports/toolchains are `BLOCKED_ENVIRONMENT`; failed required validation, unsafe payload, or product defect is `BLOCKED_SCOPE_CONFLICT`. Do not accept partial evidence.
  - Files: `docs/acceptance/cv_manager_checklist.md` only.
