# JobAgent Plan 4 Execution Tasks

## Purpose

Translate `docs/plans/Plan_4.md` into the mandatory, sequential work needed to
deliver one active PDF CV, one approved Candidate Profile, structured Job
Preferences, correction-preserving drafts, interrupt-guarded approval, direct
Candidate/Skill synchronization, and the corresponding sidebar/chat workflow.
These tasks extend the generic Plan 3 runtime without changing the existing
SQLite schema or introducing JD, matching, OCR, history, worker, or public
profile-write functionality.

## Project Context Notes

- Root `README.md` was read before task derivation. It records Phase 0, Plan 2,
  and Plan 3 as complete, including the exact SQLite/Alembic schema, root
  settings, attachment storage, Neo4j lifecycle/schema, generic Agent graph,
  tool replay service, interrupt/resume transport, typed SSE, and React chat
  client that Plan 4 must reuse.
- `backend/app/db/models/attachments.py` and
  `backend/app/db/models/profiles.py` already own the required attachment,
  Candidate Profile, draft, and Job Preferences columns and constraints at
  migration `0001_initial_schema`; Plan 4 requires no migration.
- `backend/app/core/settings.py` already exposes `FILES_DIR`,
  `MAX_PDF_SIZE_MB=10`, and `MAX_PDF_PAGES=10` through the single root
  environment boundary. `backend/app/storage/attachments.py` already owns safe
  UUID-relative paths, atomic byte writes, open/existence checks, and explicit
  best-effort deletion; upload work must extend/reuse that owner for streaming
  rather than duplicate path or atomicity logic.
- The Phase 0 PDF diagnostic is currently the sole owner of the approved
  meaningful-text rule. Production PDF extraction must move that rule into a
  reusable application owner and make the diagnostic consume the same logic so
  the rule is not copied.
- Plan 3 currently ships an empty production tool registry, empty
  `candidate_context`, and generic interruption metadata. Plan 4 must register
  only the three profile tools and extend the existing replay, ToolNode,
  runner, and resume paths at their shared roots; it must not add a second
  executor, graph, idempotency key, or status vocabulary.
- The pinned backend already contains `pypdf==6.14.2`; the active environment
  contains `python-multipart==0.0.30`, but it is not a declared direct backend
  dependency. If FastAPI multipart upload uses it, the upload task must declare
  that exact already-installed pin instead of relying on a transitive package.
- `frontend/AGENTS.md` applies to UI work: use Astryx 0.1.4 CLI discovery before
  writing UI, compose public components rather than raw layout elements, use
  component props/design tokens, and do not invent props, internal imports, raw
  visual values, or a second styling system.
- Existing shared orchestration/client files are already large. Profile-domain
  logic belongs in the focused Plan 4 modules named below; edits to existing
  chat runner, service, reducer, and page owners should be limited to root-level
  integration or a narrow safe split, not more embedded business logic or
  unrelated cleanup.
- The user-supplied root agent rules apply: search before writing, reuse or
  safely refactor existing logic, inspect all callers of shared behavior,
  avoid duplicate business rules and god files, prefer standard library or
  installed dependencies, and make the smallest source-aligned diff.

## Authority and Scope

### Primary Source

- Primary authority: `docs/plans/Plan_4.md`.
- Supporting architecture authority cited by that plan:
  `docs/plans/Master_plan.md`.
- Prerequisite compatibility authority:
  `docs/feasibility/phase_0_report.md`.
- Repository context only: root `README.md`, `backend/pyproject.toml`,
  `backend/app/core/settings.py`, `backend/app/storage/attachments.py`,
  `backend/app/db/models/attachments.py`,
  `backend/app/db/models/profiles.py`, `backend/app/agent/`,
  `backend/app/services/chat_turns.py`,
  `backend/app/services/tool_execution.py`, `backend/app/tools/registry.py`,
  `backend/app/api/dependencies.py`, `backend/app/main.py`,
  `frontend/src/features/chat/`, `frontend/src/lib/api/chat.ts`,
  `frontend/src/app/App.tsx`, and `frontend/AGENTS.md`.

### Source Section Index

- `docs/plans/Plan_4.md > ## 1. Objective` -> complete one-active-CV/profile
  outcome, mandatory approval, rollback safety, and post-commit failure boundary.
- `docs/plans/Plan_4.md > ## 3. Prerequisites from Prior Phases` -> required
  schema, settings, storage, chat, interruption, graph, and PDF evidence.
- `docs/plans/Plan_4.md > ## 4. Scope` and `## 5. Out of Scope` -> mandatory
  profile capabilities and prohibited history, parser, CRUD, worker, JD, and
  matching expansion.
- `docs/plans/Plan_4.md > ## 6. Target Directory Structure` -> focused module,
  test, frontend, and authoritative taxonomy ownership.
- `docs/plans/Plan_4.md > ## 7. Technical Specifications` -> exact schemas,
  normalization, upload/hash states, extraction, tools, approval transaction,
  graph sync, API, and frontend behavior.
- `docs/plans/Plan_4.md > ## 8. Implementation Steps` -> source-supported work
  order and required root-caller/reuse inspection.
- `docs/plans/Plan_4.md > ## 9. Verification & Testing Plan` -> required local
  backend/frontend tests, restart/manual evidence, and failure handling.
- `docs/plans/Plan_4.md > ## 10. Handoff Notes for Plan 5 / Master Phase 4` ->
  artifacts later JD/matching work must reuse.
- `docs/plans/Master_plan.md > ### 2.1 In scope` and `### 2.2 Explicitly out of
  scope` -> locked single-user/MVP product boundary.
- `docs/plans/Master_plan.md > ### 6.2 Application table schemas` through
  `### 6.4 Transaction boundaries` -> singleton rows, attachment transitions,
  foreign keys, validated JSON, approval ordering, and post-commit work.
- `docs/plans/Master_plan.md > ### 7.1 Shared skill contract` through
  `### 7.3 Job Preferences` -> exact Profile/Skill/Preference/Draft field
  contracts and facts/preferences separation.
- `docs/plans/Master_plan.md > ## 8. Neo4j Derived Model`, `## 9. Skill
  Normalization`, and `## 10. CV Ingestion and Approval Flow` -> graph identity,
  taxonomy, duplicate handling, approval, and replacement guarantees.
- `docs/plans/Master_plan.md > ### 12.2 Per-turn runs` through
  `### 12.5 Conversation and tool policy`, `### 13.1
  propose_profile_from_cv` through `### 13.3 commit_profile_draft`, and
  `### 13.7 Tool authorization matrix` -> compact context, interrupted-run
  behavior, and exact first production tools.
- `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary` and
  `## 15. Frontend UX Plan` -> exact seven endpoints, upload/turn split,
  approval guard, sidebar, chat attachment, and Astryx composition.
- `docs/plans/Master_plan.md > ## 20. Failure and Recovery Policy` through
  `## 22. Local Demo Safeguards`, `## 24. Local Testing Strategy`, and
  `## 25. Implementation Phases > ### Phase 3 — CV, Candidate Profile, and
  approval workflow` -> stable failures, SQLite-first sync, local safeguards,
  test coverage, and Phase 3 exit gate.
- `docs/feasibility/phase_0_report.md > ## pypdf extraction gate` and
  `## ShopAIKey chat and embedding gate` -> reusable meaningful-text rule,
  no-OCR evidence, and verified strict JSON-schema strategy.

### Approved Architecture and Constraints

- SQLite remains the profile source of truth. The only singleton identities are
  `candidate_profile('active')`, `profile_drafts('current')`, and
  `job_preferences('active')`; there is no profile/CV/draft history.
- Every JSON write validates the complete corresponding Pydantic model first.
  Facts and preferences stay separate, evidence stays short, and precise
  proficiency/years are not inferred without evidence.
- One production taxonomy file at `infrastructure/neo4j/skills_seed.yaml` and
  one loader/normalizer service own aliases, canonical keys, categories, and
  approved relationships. Unknown skills receive no inferred alias/category or
  `RELATED_TO` edge.
- CV bytes are validated and staged once at a UUID-derived path. Approval
  changes database state but never moves the file. Raw extracted text remains
  transient and never enters chat rows, tool logs, checkpoints, Agent context,
  or Neo4j.
- A different staged CV/draft remains intact until a new extraction succeeds.
  The prior active profile/CV remains intact until the replacement transaction
  commits. File deletion and Neo4j synchronization occur only after SQLite
  commit and never roll committed truth back.
- `commit_profile_draft` uses the existing LangGraph interrupt/checkpoint and
  the existing `(run_id, tool_call_id)` replay identity. Its tool execution
  stays `running` while interrupted and terminalizes that same row after one
  allowed resume action.
- The application keeps one Agent graph, one ToolNode, one runner, one chat
  reducer, and exact run/tool status vocabularies. Profile tools receive hidden
  execution context through existing injected/runtime seams, not through
  LLM-visible arguments.
- API routes remain transport-only; repositories own focused persistence,
  services own validation/transactions/orchestration, graph nodes own no
  database or HTTP logic, and no transaction spans provider, filesystem,
  Neo4j, or SSE work.
- Normal automated tests use synthetic CVs, fake ShopAIKey responses, temporary
  migrated SQLite, and fake/injected Neo4j behavior. Real credentials, the
  ignored root `.env`, live Neo4j, Compose, and provider smoke checks are never
  required for mandatory task acceptance.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Exact profile contracts plus reusable normalization, repository, and PDF primitives | (01A), (01B), (01C), (01D) | Plan 2 schema and Plan 3 runtime complete |
| Batch02 | Validated staged CV upload and correction-safe profile proposals | (02A), (02B), (02C) | Batch01 artifacts as noted |
| Batch03 | Interrupt-approved SQLite truth, Candidate graph sync, compact Agent context, and profile reads | (03A), (03B), (03C) | Batch02 |
| Batch04 | Shared React/Astryx CV upload, sidebar, attachment, and approval workflow | (04A), (04B) | Batch03; (02A) upload contract |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_4_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_4_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Profile Domain and Extraction Foundations

### Goal

Establish exact validated profile-domain contracts and the single reusable
normalization, persistence, and PDF-quality owners before any upload or active
profile behavior is exposed.

### Dependencies

- Plan 2 migration `0001_initial_schema` and its profile/attachment models are
  present and unchanged.
- Plan 3 shared schema, UUID/UTC, async-session, storage, and fake-test patterns
  pass their existing tests.

### Scope Boundary

This batch owns Pydantic contracts, the authoritative taxonomy/normalizer,
focused repositories, and pypdf text-quality primitives. It does not expose an
upload route, call ShopAIKey, create a draft, write active profile state,
register production tools, synchronize Neo4j data, or build frontend UI.

### Tasks

- [x] (01A): Define the exact Candidate Profile, Skill, Preference, and Draft contracts
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.1 Profile and skill schemas`; `docs/plans/Master_plan.md > ## 7. Pydantic Data Contracts > ### 7.1 Shared skill contract`; `docs/plans/Master_plan.md > ## 7. Pydantic Data Contracts > ### 7.2 Candidate Profile`; `docs/plans/Master_plan.md > ## 7. Pydantic Data Contracts > ### 7.3 Job Preferences`
  - Source Requirements:
    - Implement exact `SkillRef`, `CandidateSkill`, `ExperienceItem`,
      `EducationItem`, `LanguageItem`, `CandidateProfile`, `JobPreferences`, and
      `ProfileDraftPayload` fields/nullability/enums, with both confidence
      values constrained to `[0, 1]`.
    - Evidence is a list of short source snippets; facts and preferences remain
      separate, and precise years/proficiency are not invented without evidence.
    - The complete corresponding model must validate before any later
      `profile_json`, `draft_json`, or `preferences_json` write.
  - Dependencies: Existing `backend/app/schemas/common.py` strict/shared types.
  - User Action: None.
  - Agent Work:
    1. Search all current Pydantic models, enum/shared-type owners, ORM JSON
       fields, and serialization callers; reuse strict configuration and common
       primitives instead of adding parallel validators or status types.
    2. Add failing focused schema tests for exact fields, nullability, enum and
       confidence rejection, nested full-document validation, evidence shape,
       and fact/preference separation.
    3. Implement the smallest focused schema modules and serialization behavior
       required by those tests; do not add extraction, persistence, graph, or
       API logic to schema files.
    4. Inspect every profile/draft/preferences JSON caller and document the
       validated-model boundary later services must use.
  - Output: Strict reusable profile-domain Pydantic contracts for every later
    draft, approval, API, context, and graph path.
  - Acceptance:
    - Model fields and allowed enum values exactly match the cited Master
      contracts; unknown fields and out-of-range confidence values fail.
    - A complete `ProfileDraftPayload` round-trips through JSON without merging
      profile facts into Job Preferences or losing correction/exclusion fields.
    - No ORM, provider, filesystem, graph, route, or Agent behavior exists in
      the schema modules.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_profile_schemas.py -q` -> exact valid/invalid contract cases pass.
    - Required: `Set-Location backend; python -m ruff check app/schemas/profile.py app/schemas/skills.py tests/unit/test_profile_schemas.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "profile_json|draft_json|preferences_json|CandidateProfile|ProfileDraftPayload" backend/app backend/tests` -> JSON writers and schema ownership are reviewable with no competing contract.
  - Blocked Condition: None.
  - Files: `backend/app/schemas/profile.py`, `backend/app/schemas/skills.py`, `backend/tests/unit/test_profile_schemas.py`

- [x] (01B): Create the authoritative approved taxonomy and sole deterministic skill normalizer
  - Source of Truth: `docs/plans/Plan_4.md > ## 6. Target Directory Structure`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.2 Skill normalization ownership`; `docs/plans/Master_plan.md > ## 8. Neo4j Derived Model > ### 8.4 Graph safety rules`; `docs/plans/Master_plan.md > ## 9. Skill Normalization`
  - Source Requirements:
    - One production taxonomy defines canonical display names, aliases,
      optional categories, and only manually approved weighted relationships.
    - One service performs Unicode normalization, whitespace collapse,
      comparison lowercasing, punctuation/separator normalization, approved
      alias resolution, and deterministic unknown canonical-key derivation.
    - The LLM never supplies aliases/relationships. Unknown skills receive
      empty aliases, no category, and no related edge. Later JD/matching work
      must reuse this same parser/service.
  - Dependencies: (01A) `SkillRef` contract.
  - User Action: Before production taxonomy acceptance, the user must explicitly
    approve the canonical entries, aliases, and each `RELATED_TO` pair/weight;
    test-only synthetic taxonomy data needs no external approval.
  - Agent Work:
    1. Search manifests, fixtures, CV demo skills, and all normalization-like
       helpers before writing; prove no equivalent application owner or direct
       backend YAML dependency already exists.
    2. Propose the smallest demo-grounded production taxonomy for user approval.
       Do not infer aliases, relationships, or weights from an LLM response.
    3. After approval, create `infrastructure/neo4j/skills_seed.yaml` as the sole
       production source and a smaller test fixture. Prefer JSON-compatible YAML
       parsed with the standard library over a new YAML dependency; if used,
       document with a `ponytail:` comment that the ceiling is this small
       approved taxonomy and the upgrade path is a direct pinned YAML parser
       only when richer YAML syntax is actually required.
    4. Implement one loader/normalizer with deterministic collision validation,
       canonical ordering, unknown handling, correction/exclusion preservation,
       and reusable approved relationship projections; add focused tests for
       Unicode, whitespace, case, punctuation, aliases, unknowns, and repeats.
  - Output: One user-approved taxonomy and one deterministic normalization API
    shared by profiles, later jobs, and graph synchronization.
  - Acceptance:
    - Production code loads only `infrastructure/neo4j/skills_seed.yaml` through
      the single service; test code may inject the smaller fixture through the
      same parser path.
    - Equivalent inputs resolve to one stable `SkillRef`; unknown inputs are
      deterministic and receive no invented metadata/relationship.
    - Duplicate/colliding canonical keys or aliases and invalid relationship
      endpoints/weights fail deterministically before use.
    - No second normalizer, copied taxonomy, LLM-generated alias, or automatic
      related-skill edge exists.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_skill_normalization.py -q` -> deterministic loader/normalizer and invalid-seed cases pass.
    - Required: `Set-Location backend; python -m ruff check app/services/skill_normalization.py tests/unit/test_skill_normalization.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "skills_seed|canonical_key|Unicode|unicodedata|RELATED_TO|aliases" backend/app backend/tests infrastructure/neo4j` -> exactly one production taxonomy/parser/normalization implementation is reviewable.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when exact production taxonomy
    entries, aliases, relationship endpoints, or weights have not been
    explicitly approved; do not substitute generated values or silently omit
    the source-required seed relationships.
  - Files: `infrastructure/neo4j/skills_seed.yaml`, `backend/tests/fixtures/skills_seed.yaml`, `backend/app/services/skill_normalization.py`, `backend/tests/unit/test_skill_normalization.py`

- [x] (01C): Implement focused attachment and profile repositories over the existing schema
  - Source of Truth: `docs/plans/Plan_4.md > ## 6. Target Directory Structure`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.3 Upload validation and exact-hash state handling`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.6 Approval decisions and atomic commit`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.2 Application table schemas`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.3 Foreign-key and deletion rules`
  - Source Requirements:
    - Reuse existing `Attachment`, `CandidateProfile`, `ProfileDraft`, and
      `JobPreferences` models, async sessions, UUIDs, UTC timestamps, singleton
      IDs, constraints, and state constants without a schema migration.
    - Repositories expose only focused retrieval/mutation primitives needed for
      exact hash lookup, state transitions, active/draft/preferences reads, and
      later service-owned transactions.
    - Business validation, cross-row transaction ordering, provider work,
      filesystem cleanup, graph sync, and commit/rollback remain service-owned.
  - Dependencies: (01A); Plan 2 schema at Alembic head.
  - User Action: None.
  - Agent Work:
    1. Search all model/session/repository patterns and callers; reuse existing
       transaction ownership, UUID/UTC helpers, state constants, and error style.
    2. Add temporary-migrated-SQLite tests for hash/state reads and allowed
       transitions, singleton active/draft/preferences reads/upserts/deletes,
       timestamps, missing rows, and constraint-visible failures.
    3. Implement narrow attachment/profile repository modules without commits,
       provider/filesystem/graph calls, JSON-shape duplication, or new state
       transition vocabularies.
    4. Inspect every caller of any shared transition refactor and verify existing
       Plan 2/3 persistence tests remain valid.
  - Output: Focused repository primitives that later CV and approval services
    can compose inside short service-owned transactions.
  - Acceptance:
    - Repository operations use only the existing four profile-family tables and
      preserve singleton IDs, attachment state constants, UUIDs, and UTC updates.
    - Exact-hash lookup and each permitted attachment transition are explicit;
      invalid transitions do not mutate state.
    - Repositories neither commit/rollback nor touch files, provider clients,
      checkpoints, routes, Neo4j, or unvalidated raw CV text.
    - Migration/schema files remain unchanged.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_cv_api.py tests/integration/test_profile_approval.py -q` -> repository-focused migrated-database cases pass before higher services are added.
    - Required: `Set-Location backend; python -m pytest tests/unit/test_attachment_profile_models.py tests/integration/test_database_contract.py tests/integration/test_migrations.py -q` -> existing schema and migration contracts do not regress.
    - Required: `Set-Location backend; python -m ruff check app/repositories/attachments.py app/repositories/profiles.py tests/integration/test_cv_api.py tests/integration/test_profile_approval.py; python -m mypy app` -> focused lint and typing pass.
    - Required: `git diff -- backend/migrations backend/app/db/models` -> no Plan 4 migration or schema drift is present.
  - Blocked Condition: None.
  - Files: `backend/app/repositories/attachments.py`, `backend/app/repositories/profiles.py`, `backend/tests/integration/test_cv_api.py`, `backend/tests/integration/test_profile_approval.py`

- [x] (01D): Promote the proven pypdf extraction and meaningful-text rule into one production owner
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.3 Upload validation and exact-hash state handling`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.4 PDF/profile extraction`; `docs/plans/Plan_4.md > ## 9. Verification & Testing Plan`; `docs/feasibility/phase_0_report.md > ## pypdf extraction gate`
  - Source Requirements:
    - Use only pinned pypdf digital-text extraction, including layout mode, and
      the exact proven meaningful-text rule; image-only/insufficient text maps
      to `NO_EXTRACTABLE_TEXT` and never calls OCR or another parser.
    - Parsing exposes page count/malformed failures for upload validation while
      raw extracted text remains transient service data.
    - The feasibility diagnostic and production path must consume one rule
      implementation rather than copying thresholds, markers, or normalization.
  - Dependencies: Existing Phase 0 synthetic CV fixtures and pypdf pin.
  - User Action: None.
  - Agent Work:
    1. Search the diagnostic, fixtures, dependency manifest, and every pypdf/text
       quality caller; identify the exact constants/helpers to relocate.
    2. Add focused unit tests for valid digital fixtures, image-only input,
       malformed input, page counts, normal/layout outcomes, stable
       `NO_EXTRACTABLE_TEXT`, and absence of OCR/alternate-parser calls.
    3. Implement `pdf_extraction.py` as the production owner and refactor the
       Phase 0 diagnostic to import/reuse it while preserving diagnostic output
       and aggregate feasibility behavior.
    4. Inspect all callers and ensure no raw extracted text is logged, serialized,
       persisted, or returned by a public contract.
  - Output: One reusable pypdf parsing/extraction/quality boundary shared by
    production CV services and retained feasibility evidence.
  - Acceptance:
    - All five digital fixtures preserve the recorded gate behavior and the
      raster-only fixture returns `NO_EXTRACTABLE_TEXT` with no OCR path.
    - The maximum-page decision can be made from parsed page count before final
      attachment row/file creation.
    - Production and diagnostic code have one meaningful-text implementation;
      no threshold/marker copy or alternate PDF parser is introduced.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_pdf_extraction.py -q` -> parsing, layout, quality, and failure cases pass.
    - Required: `python infrastructure/scripts/verify_pdf_extraction.py` -> retained diagnostic ends with `PYPDF_COMPATIBILITY=PASS` and image-only `NO_EXTRACTABLE_TEXT`.
    - Required: `Set-Location backend; python -m ruff check app/services/pdf_extraction.py tests/unit/test_pdf_extraction.py ../infrastructure/scripts/verify_pdf_extraction.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "MIN_NON_WHITESPACE_CHARS|IDENTITY_MARKERS|EXPERIENCE_MARKERS|SKILLS_MARKERS|ocr|tesseract|PdfReader" backend infrastructure/scripts` -> one quality-rule owner, pypdf-only extraction, and no OCR implementation are reviewable.
  - Blocked Condition: None.
  - Files: `backend/app/services/pdf_extraction.py`, `backend/tests/unit/test_pdf_extraction.py`, `infrastructure/scripts/verify_pdf_extraction.py`

## Mandatory Batch02 - Staged CV and Profile Proposal Pipeline

### Goal

Accept only validated bounded PDF input, resolve exact hashes safely, and turn a
valid staged CV or explicit correction into one fully validated singleton draft
without mutating approved profile/preferences.

### Dependencies

- Batch01 contracts, taxonomy/normalizer, repositories, and PDF primitives.
- Existing interrupted-run guard, root settings, attachment storage, fake model
  seam, and migrated temporary-database test harness.

### Scope Boundary

This batch owns upload/staging, structured extraction, draft replacement, and
the two proposal tools. It does not activate a profile, resume approval,
terminalize `commit_profile_draft`, sync Neo4j, expose profile reads, or add UI.

### Tasks

- [x] (02A): Implement bounded CV upload, exact-hash lifecycle, and the shared upload endpoint
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.3 Upload validation and exact-hash state handling`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.8 API and frontend behavior`; `docs/plans/Master_plan.md > ## 10. CV Ingestion and Approval Flow > ### 10.1 Upload`; `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary > ### 14.1 API rules`
  - Source Requirements:
    - Reject an interrupted approval with `APPROVAL_ACTION_REQUIRED` before the
      application reads or persists upload bytes/metadata.
    - Stream into a bounded temporary file while hashing; enforce declared
      `application/pdf`, `%PDF-` magic, positive size up to 10 MB, valid pypdf
      structure, and `1..10` pages before any final UUID file/row exists.
    - Active hash returns existing attachment/profile; current staged hash
      returns existing attachment/draft; failed hash reuses the same row/file,
      resets it to staged, clears failure, and explicitly signals retry; a new
      hash atomically finalizes one UUID file then inserts one staged row.
    - A different existing staged CV/draft remains untouched until the later
      proposal succeeds. Sidebar and chat uploads share this one endpoint.
  - Dependencies: (01C), (01D); existing `AttachmentStorage` and
    `get_interrupted_run` guard.
  - User Action: None.
  - Agent Work:
    1. Search storage, guard, repository, settings, route/dependency, upload-test,
       and manifest callers. If using FastAPI multipart, declare the already
       installed exact `python-multipart==0.0.30` direct dependency.
    2. Add failing API/service tests for guard-before-read, MIME/magic/zero/size/
       malformed/page-limit rejection, no final artifact on rejection, each
       active/staged/failed/new hash branch, write/row failure cleanup, and safe
       filenames/responses.
    3. Safely refactor the storage owner with only the streaming/temp-to-UUID
       primitive required, then implement focused attachment response schemas,
       upload service orchestration, and a thin multipart route.
    4. Register the route in the existing application, inspect all storage and
       interruption callers, and prove no request path deletes or replaces a
       different staged draft during upload.
  - Output: `POST /api/attachments/cv` with bounded, atomic, exact-hash staging
    behavior and compact attachment/profile-or-draft metadata.
  - Acceptance:
    - Interrupted approval returns `APPROVAL_ACTION_REQUIRED` with no application
      upload read, temp/final file, attachment row, message, or run mutation.
    - Unsupported, empty, oversized, malformed, or over-page input leaves no
      final file/row; no partial bytes become visible at a UUID path.
    - Every hash branch returns the source-required existing/retry/new state and
      creates no duplicate row/file/extraction/draft.
    - New storage paths derive only from lowercase UUID v4; original filenames
      are display metadata and cannot escape `FILES_DIR` or inject headers.
    - Route code contains validation/delegation only and does not call provider,
      graph, checkpoint, Neo4j, or active-profile write logic.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_cv_api.py tests/unit/test_storage.py tests/unit/test_pdf_extraction.py -q` -> all upload validation/hash/atomicity/guard cases pass.
    - Required: `Set-Location backend; python -m ruff check app/api/attachments.py app/schemas/attachments.py app/services/cv_upload.py app/storage/attachments.py app/repositories/attachments.py tests/integration/test_cv_api.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "APPROVAL_ACTION_REQUIRED|UploadFile|request\.stream|MAX_PDF|%PDF-|sha256|write_bytes|temp|delete\(" backend/app backend/tests/integration/test_cv_api.py` -> validation order, one storage owner, guard, and cleanup behavior are reviewable.
  - Blocked Condition: None.
  - Files: `backend/pyproject.toml` only if declaring multipart, `backend/app/storage/attachments.py`, `backend/app/schemas/attachments.py`, `backend/app/repositories/attachments.py`, `backend/app/services/cv_upload.py`, `backend/app/api/attachments.py`, `backend/app/main.py`, `backend/tests/integration/test_cv_api.py`

- [x] (02B): Implement structured CV extraction and `propose_profile_from_cv`
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.4 PDF/profile extraction`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.5 Tool contracts and authorization`; `docs/plans/Master_plan.md > ## 10. CV Ingestion and Approval Flow > ### 10.2 Processing`; `docs/plans/Master_plan.md > ## 13. Agent-Facing Tool Contracts > ### 13.1 propose_profile_from_cv`; `docs/feasibility/phase_0_report.md > ## ShopAIKey chat and embedding gate`
  - Source Requirements:
    - Active attachment returns the approved profile without extraction/draft;
      a staged attachment already backing `profile_drafts('current')` returns
      that draft; only another valid staged attachment runs extraction.
    - Extract layout text, apply the proven quality rule, use locked
      `gpt-4o-mini` with verified strict JSON schema, validate the complete
      payload, make at most one schema-repair request when invalid, and run the
      sole deterministic skill normalizer.
    - Timeout/rate-limit retry occurs once; no meaningful text or exhausted
      provider/schema failure marks the staged row failed with a stable code and
      retains its file for exact-hash retry/deletion.
    - Only after successful validation may the singleton draft replace a prior
      CV-backed draft; then remove the prior unreferenced staged row and
      best-effort delete its file. Tool/log output contains IDs and compact
      summaries only.
  - Dependencies: (01A), (01B), (01C), (01D), (02A).
  - User Action: None for required fake-backed validation. No live provider call
    is part of task acceptance.
  - Agent Work:
    1. Search the ShopAIKey adapter/diagnostic, schema generation, tool result,
       attachment/draft, normalizer, and provider-failure callers; reuse the
       verified adapter/configuration and do not add another client/model.
    2. Add fake-provider tests for valid extraction, no-text short-circuit,
       strict-schema success, exactly one repair, exactly one timeout/rate retry,
       exhausted failures, active/draft reuse, compact outputs, and absence of
       persisted raw text.
    3. Implement a focused extraction service and draft proposal orchestration,
       validating `ProfileDraftPayload` before its short upsert transaction and
       performing prior staged cleanup only after the new draft succeeds.
    4. Add the compact `propose_profile_from_cv` tool boundary in
       `app/tools/profile.py` without active writes or production registration;
       inspect every raw-text and JSON writer before returning evidence.
  - Output: A fake-testable structured CV-to-draft pipeline and compact first
    profile proposal tool.
  - Acceptance:
    - Valid digital CV input produces one fully validated normalized current
      draft; active/current-draft inputs reuse existing truth without provider
      calls or duplicate artifacts.
    - Invalid structured output performs no more than one repair; timeout/rate
      handling performs no more than one retry; exhausted failure never creates
      an approval/success claim.
    - Failed extraction leaves the same attachment/file in `failed` state with a
      stable code; successful replacement removes only the former unreferenced
      staged row and best-effort cleans only its file.
    - Raw CV text is absent from Agent state/checkpoints, chat/tool rows,
      `ToolResult`, logs, and Neo4j; compact payloads contain IDs/summaries only.
    - No active profile/preferences/attachment mutation or second preference
      tool occurs.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_profile_extraction.py tests/unit/test_profile_schemas.py tests/unit/test_skill_normalization.py tests/integration/test_profile_approval.py -q` -> fake extraction, retry/repair, reuse, replacement, and draft cases pass.
    - Required: `Set-Location backend; python -m ruff check app/services/profile_extraction.py app/services/profile_drafts.py app/tools/profile.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py; python -m mypy app` -> focused lint and typing pass.
    - Required: `rg -n "raw.*(cv|pdf|text)|extract_text|with_structured_output|repair|retry|draft_json|arguments_summary_json|ToolResult" backend/app backend/tests` -> transient text, bounded retry/repair, validated draft, and compact result boundaries are reviewable.
  - Blocked Condition: The fake-backed implementation cannot reproduce the
    already verified strict JSON-schema request shape with the locked adapter;
    report exact local evidence rather than switching model/provider or adding
    unlimited/hidden fallback behavior.
  - Files: `backend/app/services/profile_extraction.py`, `backend/app/services/profile_drafts.py`, `backend/app/tools/profile.py`, `backend/tests/unit/test_profile_extraction.py`, `backend/tests/integration/test_profile_approval.py`

- [x] (02C): Implement correction-preserving `propose_profile_update` for profile and preferences
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.2 Skill normalization ownership`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.5 Tool contracts and authorization`; `docs/plans/Master_plan.md > ## 9. Skill Normalization > ### 9.3 User corrections`; `docs/plans/Master_plan.md > ## 13. Agent-Facing Tool Contracts > ### 13.2 propose_profile_update`
  - Source Requirements:
    - Apply requested profile and/or preference changes to the current draft or
      a copy of current approved profile/preferences and upsert only
      `profile_drafts('current')`.
    - Validate the complete `ProfileDraftPayload`; explicit skill corrections
      use `source='user_correction'`, exclusions remain present with
      `excluded=true`, and the same CV cannot silently re-add them.
    - This one tool covers both facts and Job Preferences. It never writes the
      active singleton records and does not add a separate preference tool.
  - Dependencies: (01A), (01B), (01C), (02B).
  - User Action: None.
  - Agent Work:
    1. Search every draft/profile/preferences writer and tool schema; reuse the
       draft service, normalizer, repository, and compact ToolResult boundary.
    2. Add tests for current-draft updates, active-context copy, preference-only
       updates with null source attachment, profile corrections, exclusions,
       invalid/partial payload rollback, and repeated corrections.
    3. Extend the focused draft service and `app/tools/profile.py` with one
       compact update tool, validating the whole merged document before the
       singleton upsert and preserving source attachment/corrections correctly.
    4. Inspect all callers to prove no active JSON, attachment state, old profile
       version, raw text, or standalone preference tool is created.
  - Output: One validated correction path for profile facts and Job Preferences
    that always returns to approval through the current draft.
  - Acceptance:
    - Both draft-backed and active-context updates yield one validated current
      draft with correct nullable source attachment semantics.
    - Explicit corrections/exclusions survive repeated updates and restart
      persistence; invalid requested changes leave prior draft/active truth
      unchanged.
    - Tool input/output is compact and contains no raw CV text, secrets, or
      unvalidated document; no active record changes before approval.
    - Production source contains no separate preference tool or profile write
      CRUD path.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_profile_schemas.py tests/unit/test_skill_normalization.py tests/integration/test_profile_approval.py -q` -> update/correction/exclusion and rollback cases pass.
    - Required: `Set-Location backend; python -m ruff check app/services/profile_drafts.py app/tools/profile.py tests/integration/test_profile_approval.py; python -m mypy app` -> focused lint and typing pass.
    - Required: `rg -n "propose_profile_update|preference.*tool|user_correction|excluded|profile_json|preferences_json|draft_json" backend/app backend/tests` -> one update tool, preserved corrections, and draft-only writes are reviewable.
  - Blocked Condition: None.
  - Files: `backend/app/services/profile_drafts.py`, `backend/app/tools/profile.py`, `backend/tests/integration/test_profile_approval.py`

## Mandatory Batch03 - Approved Profile Truth, Sync, and Read Integration

### Goal

Commit a validated draft only through the existing interrupted invocation,
preserve SQLite truth under every failure, synchronize the derived Candidate
graph, and expose approved compact context/read behavior.

### Dependencies

- Batch02 staged upload and complete proposal/update behavior.
- Plan 3 replay, interrupt/resume, checkpoint cleanup, SSE, dependency injection,
  Agent graph, and empty production registry remain the only runtime owners.

### Scope Boundary

This batch owns the approval transaction, post-commit cleanup/sync, guarded
commit resume semantics, production profile-tool registration, compact approved
context, and profile reads. It does not implement frontend actions, profile
write CRUD, JD/Job graph behavior, embeddings, rebuild completion, or matching.

### Tasks

- [ ] (03A): Implement the constraint-safe approval transaction and idempotent Candidate/Skill synchronization
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.6 Approval decisions and atomic commit`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.7 Candidate graph synchronization`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.4 Transaction boundaries`; `docs/plans/Master_plan.md > ## 10. CV Ingestion and Approval Flow > ### 10.4 Approved replacement`; `docs/plans/Master_plan.md > ## 21. Direct SQLite-to-Neo4j Synchronization`
  - Source Requirements:
    - Before opening the transaction, validate the complete draft, staged source
      attachment state/file, and cross-row prerequisites. In one transaction,
      upsert active profile, update validated preferences when changed, repoint
      replacement, remove the old attachment row, mark the new one active,
      delete the draft, and assert one active attachment referenced by profile.
    - Transaction failure rolls back to the old active profile/CV and leaves the
      new attachment staged. No history is created and no file moves at approval.
    - After commit, best-effort delete only the old PDF and directly synchronize
      Candidate/non-excluded Skill/seed relationships. Cleanup or Neo4j failure
      never rolls SQLite back; sync failure returns `NEO4J_SYNC_FAILED` plus the
      rebuild instruction and accurately reports committed SQLite truth.
    - Candidate sync is parameterized/idempotent, uses `id='active'` and profile
      `updated_at`, rebuilds only this Candidate's `HAS_SKILL`, omits exclusions,
      and loads only approved seed `RELATED_TO` relationships.
  - Dependencies: (01A), (01B), (01C), (02C).
  - User Action: None for required fake/injected Neo4j tests. A live local Neo4j
    probe is optional and requires user-managed process credentials.
  - Agent Work:
    1. Search every profile/attachment transaction, storage delete, graph driver,
       Cypher, taxonomy, timestamp, and failure-code caller; reuse the existing
       session/storage/driver owners and fake-driver pattern.
    2. Add failpoint-driven integration tests for first approval, replacement
       ordering, missing file/state, each transaction failure, final invariant,
       cleanup failure, sync failure after commit, exclusions, seed edges, and
       repeated identical Candidate sync.
    3. Implement the focused approval service with preflight, one short SQLite
       transaction, explicit committed outcome, and post-commit cleanup; implement
       parameterized `sync_candidate.py` through the injected async driver.
    4. Inspect all transaction/graph/file callers and prove no open transaction
       spans filesystem or Neo4j work and no sync path receives raw CV text.
  - Output: A constraint-safe SQLite-first approval primitive plus idempotent
    Candidate/Skill/seed graph synchronization and truthful partial-failure result.
  - Acceptance:
    - Successful first/replacement approval ends with one active attachment,
      profile pointing to it, validated preferences, no current draft, and no
      previous profile/attachment row.
    - Every pre-commit/transaction failure preserves the prior active truth and
      staged replacement; no old PDF is deleted and no Neo4j write runs.
    - Cleanup failure leaves valid committed SQLite and is reported; Neo4j
      failure returns `NEO4J_SYNC_FAILED` with rebuild guidance and does not
      misstate or roll back the profile commit.
    - Repeated sync yields one Candidate and stable Skill/HAS_SKILL/RELATED_TO
      data; excluded skills exist only in SQLite approved JSON.
    - Cypher uses parameters for runtime values and emits no secrets/raw CV text.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_profile_approval.py tests/integration/test_candidate_sync.py -q` -> transaction, rollback, cleanup, sync, exclusion, and idempotency cases pass.
    - Required: `Set-Location backend; python -m ruff check app/services/profile_approval.py app/graph/sync_candidate.py tests/integration/test_profile_approval.py tests/integration/test_candidate_sync.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "begin|commit|rollback|delete\(|NEO4J_SYNC_FAILED|MERGE|HAS_SKILL|RELATED_TO|source_updated_at|raw.*(cv|pdf|text)" backend/app/services/profile_approval.py backend/app/graph/sync_candidate.py backend/tests/integration` -> transaction/post-commit boundaries and parameterized derived sync are reviewable.
    - Optional: `Set-Location backend; python -m pytest tests/integration/test_neo4j_setup.py tests/integration/test_candidate_sync.py -q` -> with live process credentials, local schema and Candidate sync pass; unavailable live Neo4j does not block required acceptance.
  - Blocked Condition: None for fake-backed acceptance; missing live Neo4j
    credentials/connectivity blocks only the optional probe.
  - Files: `backend/app/services/profile_approval.py`, `backend/app/graph/sync_candidate.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/integration/test_candidate_sync.py`

- [ ] (03B): Integrate interrupt-guarded `commit_profile_draft` with the existing replay/resume runtime
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.5 Tool contracts and authorization`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.6 Approval decisions and atomic commit`; `docs/plans/Master_plan.md > ## 10. CV Ingestion and Approval Flow > ### 10.3 Chat approval`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.2 Per-turn runs`; `docs/plans/Master_plan.md > ## 13. Agent-Facing Tool Contracts > ### 13.3 commit_profile_draft`; `docs/plans/Master_plan.md > ## 13. Agent-Facing Tool Contracts > ### 13.7 Tool authorization matrix`
  - Source Requirements:
    - `commit_profile_draft('current')` validates authorization/draft and calls
      `interrupt()` before any active profile/preference side effect. Durable
      pending metadata includes `kind='profile_commit'`, `draft_id='current'`,
      and exactly `save_profile|request_changes`; the existing tool execution
      remains `running`.
    - Resume continues the same run, checkpoint, tool invocation, and
      `(run_id, tool_call_id)` identity. `request_changes` completes that tool/run
      with `ToolResult(ok=true, data={'committed': false})`, preserves the draft,
      clears pending/checkpoint, and leaves correction to a new turn.
    - `save_profile` calls (03A); success completes the same tool with
      `ToolResult(ok=true)`. Commit/sync failure terminalizes it as failed with
      the matching stable code and text that distinguishes pre-commit failure
      from committed-SQLite/failed-derived-sync.
    - Terminal resume is the existing no-op stream. Production registers only
      the three profile tools; `match_jobs` remains unavailable in Plan 4.
  - Dependencies: (02B), (02C), (03A); existing Plan 3 executor/graph/runner/
    chat resume/checkpoint/SSE contracts.
  - User Action: None for required fake-backed tests.
  - Agent Work:
    1. Search every caller of `execute_tool`, `_CountingToolNode`, injected state/
       tool-call identity, interrupt projection normalization, `claim_resume`,
       runner terminal callbacks, checkpoint deletion, registry construction,
       and dependency injection before changing their shared roots.
    2. Add full-path fake tests proving authorization, pre-side-effect interrupt,
       durable `draft_id`, one running execution across pause/restart, both
       actions, one terminal tool status, checkpoint cleanup, exact replay, and
       terminal no-op behavior.
    3. Extend the single existing executor/ToolNode path to support an
       interrupting invocation re-entered under the same identity; inject
       `run_id`/tool-call ID/state through the pinned LangGraph/LangChain hidden
       argument facilities so they do not appear in LLM-visible schemas.
    4. Implement guarded commit/action handling and register the three focused
       tools through the existing request dependency seam with injected session,
       storage, extraction, and graph dependencies; keep generic synthetic tests
       working and inspect all callers for duplicate execution/status paths.
  - Output: The first production tool registry and complete persisted
    propose/commit/approve/request-change lifecycle over the existing graph/SSE path.
  - Acceptance:
    - No active profile/preference/attachment side effect occurs before
      `interrupt()` returns `save_profile`; unauthorized or missing-draft commit
      fails before interruption/side effects.
    - One `tool_executions` row remains `running` while interrupted and becomes
      exactly one terminal completed/failed row after the accepted action;
      history/SSE expose exact Plan 3 statuses only.
    - `request_changes` preserves the validated draft, completes the original
      run/tool, deletes only its checkpoint, and a new correction run can update
      the same draft and interrupt again after restart.
    - `save_profile` reflects (03A) truth, including an accurate failed
      ToolResult when Neo4j sync fails after SQLite commit; replay never repeats
      SQLite/file/Neo4j side effects.
    - Production registry contains exactly the three profile tools with compact
      schemas; no internal execution IDs, separate preference tool, `save_job`,
      `query_jobs`, `match_jobs`, synthetic tool, or second idempotency path.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py tests/integration/test_agent_runner.py tests/integration/test_chat_api.py -q` -> full interrupt, actions, replay, persistence, SSE, restart, and cleanup cases pass with fakes.
    - Required: `Set-Location backend; python -m ruff check app/tools/profile.py app/tools/registry.py app/services/tool_execution.py app/services/chat_turns.py app/agent/graph.py app/agent/runner.py app/api/dependencies.py tests/integration/test_profile_approval.py tests/integration/test_interrupt_resume.py; python -m mypy app` -> focused runtime lint and typing pass.
    - Required: `rg -n "propose_profile_from_cv|propose_profile_update|commit_profile_draft|interrupt\(|draft_id|allowed_actions|execute_tool|tool_call_id|production_registry|match_jobs|request_changes|save_profile" backend/app backend/tests` -> exact tool set, one identity path, durable projection, and action semantics are reviewable.
  - Blocked Condition: The pinned ToolNode/injected-argument/interrupt runtime
    cannot preserve the single `(run_id, tool_call_id)` execution across resume;
    report a minimal reproducible failing test and installed-version evidence
    rather than adding another graph, executor, result row, or idempotency key.
  - Files: `backend/app/tools/profile.py`, `backend/app/tools/registry.py`, `backend/app/services/tool_execution.py`, `backend/app/services/chat_turns.py`, `backend/app/agent/graph.py`, `backend/app/agent/runner.py`, `backend/app/api/dependencies.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/integration/test_interrupt_resume.py`, `backend/tests/integration/test_tool_replay.py`, `backend/tests/integration/test_agent_runner.py`, `backend/tests/integration/test_chat_api.py`

- [ ] (03C): Load compact approved candidate context and expose profile/CV reads
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.4 PDF/profile extraction`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.8 API and frontend behavior`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.3 Agent state`; `docs/plans/Master_plan.md > ## 12. Agent Architecture > ### 12.4 Memory policy`; `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary`
  - Source Requirements:
    - Load a compact projection of the current approved Candidate Profile and
      Job Preferences into the existing `candidate_context` before graph
      execution; never inject raw CV text, full files, or a new state/memory table.
    - `GET /api/profile` returns validated active profile/preferences plus active
      attachment metadata or an explicit empty state and never PDF bytes.
    - `GET /api/profile/cv` streams only the active stored PDF with safe content
      disposition/original display filename; no public profile write CRUD exists.
    - Application public surface becomes exactly health, attachment upload,
      profile/profile-CV reads, and the three Plan 3 chat endpoints.
  - Dependencies: (01A), (01C), (02A), (03A), (03B).
  - User Action: None.
  - Agent Work:
    1. Search the empty candidate-context builder, initial graph state, model
       message assembly, runner/chat callers, profile repositories, storage open,
       existing response schemas, routers, and every public route registration.
    2. Add tests for no-profile and active-profile reads, safe filename/bytes,
       missing/inconsistent file safety, exact route set, compact bounded context,
       approved-profile use during pending replacement, and raw-field exclusion.
    3. Implement one compact validated context loader and thread its result
       through the existing state/runner/model-input path before graph execution,
       outside any long-lived transaction and without changing the nine fields.
    4. Implement focused profile response schemas/service and thin read/stream
       routes, register them once, and inspect all context/route/file callers for
       raw CV, header injection, transaction, and public-write leaks.
  - Output: Durable approved candidate memory for Agent decisions plus safe
    profile metadata and active-PDF read endpoints.
  - Acceptance:
    - New turns receive current approved compact profile/preferences after a
      backend restart; while replacement is pending they still receive the old
      approved profile, not the draft.
    - Candidate context stays within the existing nine-field state and prompt
      budget policy and contains no raw document, file path, secret, history
      dump, or unapproved draft.
    - Empty/profile responses validate exactly; CV read returns only the active
      file with safe display disposition and never exposes `storage_path`.
    - Public application routes are exactly the seven Master endpoints; no
      profile PUT/PATCH/DELETE or other functional route exists.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_agent_context.py tests/integration/test_cv_api.py tests/integration/test_chat_api.py tests/integration/test_profile_approval.py -q` -> compact context, reads, route set, restart, and pending-replacement cases pass.
    - Required: `Set-Location backend; python -m ruff check app/agent/context.py app/agent/graph.py app/agent/runner.py app/services/chat_turns.py app/schemas/profile.py app/api/profile.py app/main.py tests/unit/test_agent_context.py tests/integration/test_cv_api.py tests/integration/test_chat_api.py; python -m mypy app` -> focused lint and typing pass.
    - Required: `rg -n "candidate_context|raw_(cv|pdf|text|content)|storage_path|Content-Disposition|@router\.(get|post|put|patch|delete)|include_router" backend/app backend/tests` -> compact-memory, safe-file, and exact public-route boundaries are reviewable.
  - Blocked Condition: None.
  - Files: `backend/app/agent/context.py`, `backend/app/agent/graph.py`, `backend/app/agent/runner.py`, `backend/app/services/chat_turns.py`, `backend/app/schemas/profile.py`, `backend/app/api/profile.py`, `backend/app/main.py`, `backend/tests/unit/test_agent_context.py`, `backend/tests/integration/test_cv_api.py`, `backend/tests/integration/test_chat_api.py`

## Mandatory Batch04 - React and Astryx CV Approval Workflow

### Goal

Expose the one-CV/profile lifecycle through the existing single React chat state:
shared upload and attachment IDs, sidebar status/download, durable approval card,
single accepted action, correct control locks, and request-change focus.

### Dependencies

- (02A) shared upload contract and all Batch03 approval/profile read behavior.
- Existing Plan 3 typed history/SSE API, single reducer, ChatPage, failure states,
  and exact status vocabulary.
- Pinned Astryx 0.1.4 public CLI/component evidence and `frontend/AGENTS.md`.

### Scope Boundary

This batch owns profile API/types/components and minimal integration with the
existing chat shell/reducer. It does not add a full editor, CV history, drag/drop
system, raw PDF preview, profile write CRUD, JD/Job/match UI, a second stream
store, custom design system, or internal Astryx imports.

### Tasks

- [ ] (04A): Implement typed profile transport, shared CV attachment flow, and sidebar state
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.3 Upload validation and exact-hash state handling`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.8 API and frontend behavior`; `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary > ### 14.1 API rules`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.1 Layout`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.2 Sidebar`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.3 Chat components`
  - Source Requirements:
    - One typed frontend API consumes profile empty/active state, multipart CV
      upload, active CV view/download, and the existing turn stream using only
      `VITE_API_BASE_URL`.
    - Sidebar shows only active filename, profile state, upload/replace, and
      view/download. Sidebar and chat attachments call the same upload endpoint;
      a successful sidebar upload immediately starts a normal concise chat turn
      carrying only the returned `attachment_id`.
    - Chat attachment UI renders a compact PDF token and submits only attachment
      IDs. Upload is disabled while a run is active/interrupted and surfaces
      stable backend failures without exposing paths/raw bytes.
  - Dependencies: (02A), (03C); existing `streamChatTurn` attachment ID contract
    and single chat reducer.
  - User Action: None for required frontend tests. Browser download/manual
    provider behavior is optional.
  - Agent Work:
    1. Run pinned Astryx discovery in the order required by `frontend/AGENTS.md`:
       `build` for the CV/sidebar/chat attachment workflow, relevant layout/
       token docs/templates, then public `AppShell`, `SideNav`, and
       `ChatComposer` component commands; inspect current App/ChatPage/API/tests.
    2. Add typed transport/profile state tests for empty/active load, safe upload
       errors, active download URL, same endpoint for both entry points, one
       follow-up turn, attachment IDs only, and pending/in-flight upload lock.
    3. Implement focused `features/profile` types/API/sidebar and minimally wire
       the documented sidebar plus ChatComposer PDF-token API into the existing
       App/ChatPage/reducer owner; keep profile fetch/upload state out of the SSE
       reducer unless it is actual stream state.
    4. Inspect all frontend API, upload, composer, reducer, and layout callers for
       duplicated endpoints/state, raw document/path leakage, undocumented
       Astryx props, raw layout/style values, and out-of-scope controls.
  - Output: A responsive approved-profile sidebar and one shared typed CV upload/
    attachment-to-chat path over the existing conversation client.
  - Acceptance:
    - Empty and active sidebar states contain only the four source-approved
      information/actions and use documented public Astryx composition.
    - Sidebar and composer uploads invoke the same API function; successful
      upload sends one concise normal turn with the returned ID and no PDF body,
      file path, duplicate stream store, or direct profile write.
    - Active CV view/download uses only `GET /api/profile/cv`; unsafe filenames,
      storage paths, raw PDF bytes, and secret data never enter UI state/logs.
    - Upload/replace is disabled for connecting, streaming, or interrupted state
      and visibly reports stable API errors without false success.
    - No full editor, history/version list, JD/match UI, raw layout element,
      internal Astryx import, or second design system is introduced.
  - Validation:
    - Required: `Set-Location frontend; npx astryx build "CV sidebar upload and chat PDF attachment"; npx astryx docs layout; npx astryx component AppShell; npx astryx component SideNav; npx astryx component ChatComposer` -> pinned public layout/sidebar/attachment APIs are documented before implementation.
    - Required: `Set-Location frontend; npm test -- --run src/test/cv-sidebar.test.tsx src/test/chat-page.test.tsx; npm run lint; npm run typecheck; npm run build` -> sidebar, shared upload, token, lock, lint, typing, and build pass.
    - Required: `Set-Location backend; python -m pytest tests/integration/test_cv_api.py tests/integration/test_chat_api.py -q` -> frontend-consumed upload/profile/chat contracts pass with fakes.
    - Required: `rg -n "attachments/cv|/profile/cv|attachment_ids|File|Blob|storage_path|@astryxdesign/.*/(src|dist)/|#[0-9A-Fa-f]{3,8}|<div" frontend/src` -> one API path, ID-only turn, safe data, and Astryx rules are reviewable.
  - Blocked Condition: A required Astryx 0.1.4 sidebar or composer attachment
    capability has no documented public composition. Report exact CLI evidence;
    do not invent props, use internal modules, raw layout elements, or add a
    substitute component library.
  - Files: `frontend/src/features/profile/types.ts`, `frontend/src/features/profile/api.ts`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/app/App.tsx`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/lib/api/chat.ts`, `frontend/src/test/cv-sidebar.test.tsx`, `frontend/src/test/chat-page.test.tsx`, `frontend/src/app/theme.css` only for source-required token-based layout adjustments

- [ ] (04B): Render durable approval actions with one resume decision and request-change focus
  - Source of Truth: `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.6 Approval decisions and atomic commit`; `docs/plans/Plan_4.md > ## 7. Technical Specifications > ### 7.8 API and frontend behavior`; `docs/plans/Master_plan.md > ## 10. CV Ingestion and Approval Flow > ### 10.3 Chat approval`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.3 Chat components`; `docs/plans/Master_plan.md > ## 24. Local Testing Strategy > ### 24.3 Frontend tests`
  - Source Requirements:
    - A profile approval card summarizes profile/preferences and exposes exactly
      `Save Profile` and `Request Changes` using pinned public Astryx `Card`,
      `ButtonGroup`, and `Button` APIs.
    - Either action calls the existing resume stream once for the interrupted
      run. Both controls disable after the first accepted action; terminal
      replay remains harmless and frontend state keeps exact run/tool statuses.
    - Composer and upload stay disabled while approval is pending. A completed
      `request_changes` re-enables and focuses the composer; Save refreshes the
      approved sidebar state. History hydration after restart reconstructs the
      pending card from durable run metadata.
  - Dependencies: (03B), (03C), (04A); existing SSE parser/reducer/history and
    `streamChatResume` API.
  - User Action: None for required fake-backed tests. Optional full local smoke
    requires the user's ignored root `.env`, valid ShopAIKey key, Docker, and
    free loopback ports.
  - Agent Work:
    1. Run pinned Astryx discovery for the approval card and documented focus/
       ref behavior (`build`, relevant template/docs, `Card`, `ButtonGroup`,
       `Button`, and `ChatComposer`); inspect all approval/SSE/history/reducer and
       resume callers before changing shared state.
    2. Add UI tests for streamed and restart-hydrated profile cards, exact labels,
       one accepted action under rapid clicks, resume event ingestion through
       the same reducer, terminal no-op, pending locks, request-change focus,
       Save sidebar refresh, and failure/committed-sync-failure truthfulness.
    3. Implement a focused `ApprovalCard` and minimal ChatMessages/ChatPage wiring
       so resume uses the existing API/parser/reducer callbacks. Keep only local
       button-submission/focus state outside the reducer; do not add a competing
       run/tool/approval store.
    4. Run full frontend and fake-backed backend gates and inspect all component,
       status, action, history, and upload callers for duplicate decisions,
       undocumented Astryx APIs, raw data, false completion, or out-of-scope UI.
  - Output: A restart-safe in-chat profile approval/request-change loop over the
    same durable run, tool execution, SSE parser, and client reducer.
  - Acceptance:
    - Streamed and hydrated `profile_commit` interruptions render one compact
      card with exactly two source-approved actions and no raw CV content.
    - The first accepted action immediately disables both buttons and upload/
      composer controls; repeated clicks/resume cannot create a second tool,
      write, graph sync, or client terminal state.
    - `request_changes` completion preserves the card's draft server-side,
      removes pending UI lock, focuses the documented composer surface, and the
      next correction uses a new turn; Save refreshes active profile/sidebar.
    - Backend tool/run failures, including committed SQLite plus failed Neo4j
      sync, render truthful visible failure/outcome and never false success.
    - Client stream state remains in the existing reducer with exact
      `pending|running|completed|failed` tool values; no aliases, second store,
      full editor, JD, or match UI is added.
  - Validation:
    - Required: `Set-Location frontend; npx astryx build "in-chat profile approval card"; npx astryx component Card; npx astryx component ButtonGroup; npx astryx component Button; npx astryx component ChatComposer` -> pinned public card/action/focus APIs are documented before implementation.
    - Required: `Set-Location frontend; npm test -- --run src/test/approval-card.test.tsx src/test/cv-sidebar.test.tsx src/test/sse-reducer.test.ts src/test/chat-page.test.tsx; npm run lint; npm run typecheck; npm run build` -> approval, hydration, idempotent controls, focus, reducer, lint, typing, and build pass.
    - Required: `Set-Location backend; python -m pytest tests/integration/test_profile_approval.py tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py tests/integration/test_tool_replay.py -q` -> frontend-consumed approval/resume/replay contracts pass with fakes.
    - Required: `rg -n "Save Profile|Request Changes|save_profile|request_changes|streamChatResume|pendingApproval|focus|disabled|\bcomplete\b|\berror\b|@astryxdesign/.*/(src|dist)/" frontend/src` -> exact actions, single resume/reducer path, focus/lock, and public Astryx/status boundaries are reviewable; source-required error prose is reviewed separately from status values.
    - Required: `git status --short --untracked-files=all` -> no real CV, root `.env`, SQLite/checkpoint file, or runtime attachment is tracked; only intentional synthetic fixtures and source artifacts appear.
    - Optional: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d` -> after startup, manual synthetic CV upload, approval, restart, and correction confirm active state/history hydration and correction persistence; unavailable optional prerequisites do not block acceptance.
  - Blocked Condition: A required Astryx 0.1.4 public API cannot render the exact
    two actions or focus the composer without undocumented internals. Report the
    CLI evidence; do not invent props, manipulate internal DOM, or add another
    design/state system. Missing optional local-smoke prerequisites do not block
    required acceptance.
  - Files: `frontend/src/features/profile/ApprovalCard.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/reducer.ts`, `frontend/src/lib/api/chat.ts`, `frontend/src/test/approval-card.test.tsx`, `frontend/src/test/cv-sidebar.test.tsx`, `frontend/src/test/sse-reducer.test.ts`, `frontend/src/test/chat-page.test.tsx`
