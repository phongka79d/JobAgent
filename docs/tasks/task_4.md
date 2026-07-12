# JobAgent Plan 4 Phase 3 Execution Tasks

## Purpose

Execute Master Phase 3 as reviewable units that turn one validated PDF CV into
an explicitly approved Candidate Profile and Job Preferences state, expose that
state through the existing chat and Astryx shell, and synchronize only derived
Candidate/Skill graph data. The phase must reuse the accepted Plan 2 and Plan 3
storage, Agent, SSE, approval, and frontend seams and stop before JD ingestion
or matching.

## Project Context Notes

- Root `README.md` was read. It records Plan 2 Batches 01-05 and Plan 3
  Batches 01-04 as evidence-backed, so the unchecked prerequisite markers in
  `docs/plans/Plan_4.md` are stale planning state rather than new work.
- SQLite remains the canonical application source of truth, attachment bytes
  remain under the contained filesystem store, and Neo4j remains derived and
  fully rebuildable. The frontend communicates only with FastAPI.
- The accepted schema already contains attachment, Candidate Profile, profile
  draft, Job Preferences, and graph outbox tables. Existing repositories own
  staged/active attachment metadata and replay-safe outbox mechanics; existing
  services own contained stage/promote/delete/open filesystem operations.
- Plan 3 already owns the one `StateGraph`, `ToolNode`, eight-event SSE union,
  same-run interrupt/resume and request idempotency, chat attachment IDs,
  frontend parser/reducer, generic approval control, and single `AppShell`.
  Plan 4 extends those seams and does not create alternatives.
- No production Candidate schema, profile repository, CV ingestion service, PII
  redactor, skill normalizer/seed, profile tool, or Candidate graph projector
  exists. Despite Plan 4's “reuse” wording, this phase owns the first shared
  skill-normalization seam; Plan 5 must reuse it.
- `ExperienceItem`, `EducationItem`, and `LanguageItem` fields are not enumerated
  by Plan 4 or the Master Plan. Task (01A) therefore owns the smallest explicit
  display-fact and source-evidence contracts and may not invent preference,
  scoring, or trusted-relationship fields.
- Plan 4's Candidate graph rule is more specific than the Master's general UUID
  wording: graph identity reuses the existing approved singleton row ID and
  never invents a second Candidate identity or adds a UUID solely for Neo4j.
- The existing unique outbox identity does not requeue a terminal singleton
  Candidate event. Task (03A) must repair that shared root behavior after
  inspecting every caller, so repeated approvals remain processable without
  duplicate outbox rows or graph entities.
- For post-commit old-file cleanup, the unreferenced prior `Attachment` row and
  its contained service path are the durable retry record. This is sufficient
  repository state, so no cleanup table or attachment-history feature is
  authorized.
- Active-context-only profile/preference corrections retain the current active
  attachment and skip filesystem promotion. Preferences are preserved when a
  draft does not contain preference changes.
- The existing approval transport records correction resume data but does not
  feed it back to the model/tool path, and the generic SSE approval payload
  discards domain summary data. Batch04 must fix those root seams without
  creating a second graph or event.
- The declared backend limits already exist in typed root settings:
  `MAX_PDF_SIZE_MB=10` and `MAX_PDF_PAGES=10`. The accepted Phase 0 PDF gate
  uses pypdf `layout` extraction and maps zero non-whitespace characters to
  `NO_EXTRACTABLE_TEXT`.
- FastAPI multipart parsing is not a declared runtime dependency. The upload
  task may add one exact compatible `python-multipart` pin; it must not build a
  custom multipart parser.
- Backend quality commands run from `backend/`: `python -m ruff check app tests`,
  `python -m mypy app`, and `python -m pytest -q`. Frontend commands run from
  `frontend/`: `npm run check:astryx`, `npm run lint`,
  `npm run typecheck`, `npm run test -- --run`, and `npm run build`.
- The user-provided root rules require search-before-write, caller inspection,
  reuse before addition, focused modules, no duplicated business logic, and the
  shortest source-compliant diff. Existing graph/chat/frontend seam files over
  300 lines receive only thin integration edits; new domain logic belongs in
  focused Plan 4 modules.
- `frontend/AGENTS.md` requires Astryx CLI discovery, documented component APIs,
  the existing `AppShell` frame, component/token styling, and no raw layout
  `div` elements, undocumented props, `xstyle`, or hard-coded visual values.
- Normal automated tests use fakes and local temporary files and never call the
  real ShopAIKey or require a live Neo4j instance. Real secrets remain only in
  the ignored root `.env` and never enter tests, logs, reports, diffs, SSE, or
  durable summaries.

## Authority and Scope

### Primary Source

`docs/plans/Plan_4.md` is the user-named primary source. Its objective, scope,
technical specifications, implementation steps, verification plan, and Plan 5
handoff are authoritative. Referenced sections of
`docs/plans/Master_plan.md`, the accepted Plan 3 handoff, the root `README.md`,
and repository evidence refine execution details without expanding Phase 3.

### Source Section Index

- `docs/plans/Plan_4.md` > `## 1. Objective` -> complete phase outcome.
- `docs/plans/Plan_4.md` > `## 4. Scope` -> mandatory backend, graph, and frontend work.
- `docs/plans/Plan_4.md` > `## 5. Out of Scope` -> prohibited later-phase and editor work.
- `docs/plans/Plan_4.md` > `## 6. Target Directory Structure` -> likely ownership and module boundaries.
- `docs/plans/Plan_4.md` > `### 7.1 Upload and file lifecycle` -> upload, duplicate, active read, and safe metadata contracts.
- `docs/plans/Plan_4.md` > `### 7.2 Candidate and preference contracts` -> Candidate, skill, preference, and evidence rules.
- `docs/plans/Plan_4.md` > `### 7.3 Processing pipeline` -> pypdf, redaction, provider, repair, normalization, and draft order.
- `docs/plans/Plan_4.md` > `### 7.4 Tool behavior and authorization` -> four tools, same-draft corrections, and guarded writes.
- `docs/plans/Plan_4.md` > `### 7.5 Atomic replacement` -> promotion, transaction, compensation, cleanup retry, and no-gap rule.
- `docs/plans/Plan_4.md` > `### 7.6 Candidate graph synchronization` -> Candidate/Skill projection and prohibited trust.
- `docs/plans/Plan_4.md` > `## 9. Verification & Testing Plan` -> failure, persistence, replay, UI, and exit evidence.
- `docs/plans/Plan_4.md` > `## 10. Handoff Notes for Plan 5 (Master Phase 4)` -> stable Phase 4 inputs and ownership limits.
- `docs/plans/Master_plan.md` > `### 6.2 Profile storage rule` -> singleton, draft, approval, and no-history ownership.
- `docs/plans/Master_plan.md` > `### 7.1 Shared skill contract` -> canonical skill fields and evidence.
- `docs/plans/Master_plan.md` > `### 7.2 Candidate Profile` -> Candidate and CandidateSkill fields.
- `docs/plans/Master_plan.md` > `### 7.3 Job Preferences` -> separate explicit preference contract.
- `docs/plans/Master_plan.md` > `## 9. Skill Normalization` -> seed, canonicalization, provisional, and correction rules.
- `docs/plans/Master_plan.md` > `## 10. CV Ingestion and Approval Flow` -> shared upload, processing, approval UI, and atomic replacement.
- `docs/plans/Master_plan.md` > ``### 13.1 `get_candidate_context``` through ``### 13.4 `commit_profile_draft``` -> exact Plan 4 tool contracts.
- `docs/plans/Master_plan.md` > `### 13.8 Tool authorization matrix` -> state-dependent tool availability.
- `docs/plans/Master_plan.md` > `## 14. Public FastAPI Boundary` -> exact seven-route application surface after Phase 3.
- `docs/plans/Master_plan.md` > `### 15.1 Layout` through `### 15.4 Tool activity display` -> sidebar, chat, approval, and sanitization UX.
- `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` -> bounded and fail-closed behavior.
- `docs/plans/Master_plan.md` > `## 21. SQLite-to-Neo4j Synchronization` -> same-transaction outbox, bounded processing, replay, and Candidate rebuild slice.
- `docs/plans/Master_plan.md` > `### 22.3 Untrusted content` and `### 22.4 Logging` -> authorization and privacy boundaries.
- `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` -> fake/local validation boundary.
- `docs/plans/Master_plan.md` > `### Phase 3 — CV, Candidate Profile, and approval workflow` -> mandatory phase tasks and exit gate.
- `docs/plans/Plan_3.md` > `## 10. Handoff Notes for Plan 4 (Master Phase 3)` -> stable Agent, SSE, registry, and frontend seams.
- `README.md` > `## Plan 4 handoff (Master Phase 3) — stable seams only` -> accepted repository locations and prohibited alternate paths.

### Approved Architecture and Constraints

- Maintain one canonical Candidate Profile singleton, optional explicit Job
  Preferences singleton, and temporary validated drafts in SQLite. Do not add
  profile history or persist an unapproved proposal as active state.
- Reuse the existing Candidate singleton ID for Neo4j identity. The more
  specific Plan 4 rule controls Phase 3; do not add a parallel Candidate UUID.
- Keep uploaded bytes in the existing contained staged/active filesystem
  service. User filenames and paths are display metadata only and never path
  authority.
- Both sidebar and chat uploads call `POST /api/attachments/cv`. Sidebar success
  immediately starts the existing chat turn with the non-PII text
  “Create a candidate profile draft from the attached CV.” and the returned
  attachment ID. Chat-composer upload creates a removable token and submits the
  ID with the user's next turn.
- Reuse pypdf layout extraction and the locked zero-usable-character
  `NO_EXTRACTABLE_TEXT` rule. Do not add OCR, alternate parsers, embedded-content
  execution, or an unstated text-quality heuristic.
- Deterministically redact email, phone, and labeled address/contact-address
  lines before any external call. A redaction error is fail-closed.
- Provider extraction uses the locked ShopAIKey `gpt-4o-mini` structured mode,
  Pydantic validation, and at most one repair. Tests use fakes only.
- No production alias becomes verified unless it is present in the checked-in
  approved seed. Unknown skills receive deterministic provisional keys, user
  exclusions persist, and no LLM-created `RELATED_TO` edge is trusted.
- Keep the current active profile/CV usable until approval. A staged source is
  promoted before SQLite commit and restored to staged on pre-commit failure.
  An active-context correction skips promotion and retains its attachment.
- The prior active attachment row remains as an unreferenced durable cleanup
  record until old bytes and then metadata are safely removed. Public reads use
  only the singleton's `active_attachment_id`, so cleanup retry never exposes
  multiple active CVs.
- Every approved graph-derived change creates or requeues Candidate sync work
  in the same SQLite transaction. Immediate/startup processing is bounded;
  Neo4j failure never rolls back canonical SQLite state or spins continuously.
- Preserve the one Plan 3 graph, tool registry, conversation, chat API, SSE
  event names, reducer, and `AppShell`. Add a bounded typed profile approval
  payload through `approval_required` rather than creating another event or
  approval path.
- Tool authorization comes from application run/draft state, never LLM
  arguments, CV text, or a public HTTP mutation. Tools call repositories and
  services directly and never call back into FastAPI.
- Public application routes after Phase 3 are exactly `GET /api/health`,
  `POST /api/attachments/cv`, `GET /api/profile`, `GET /api/profile/cv`,
  `GET /api/chat/history`, `POST /api/chat/turns`, and
  `POST /api/chat/runs/{run_id}/resume`, plus framework documentation routes.
- No JD ingestion, Job graph data, matching, full profile editor, background
  poller, Qdrant, CI, cloud deployment, or direct frontend/store/provider access
  belongs to this task document.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Validated Candidate contracts and reusable persistence boundaries | (01A), (01B), (01C) | Accepted Plan 2/Plan 3 handoff |
| Batch02 | One safe PDF intake-to-profile-draft pipeline | (02A), (02B), (02C) | Batch01 |
| Batch03 | Replay-safe Candidate graph sync and atomic approved replacement | (03A), (03B) | Batch02 |
| Batch04 | Four production tools on the existing approval/resume seam | (04A), (04B) | Batch03 |
| Batch05 | Public approved-profile reads and shared Astryx CV experience | (05A), (05B), (05C) | Batch04 |
| Batch06 | Phase 3 exit proof and stable Plan 5 handoff | (06A) | Batch05 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_4_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_4_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.
- In orchestrated mode A1 execution and repair run on Grok unless the user sets
  `A1_RUNTIME: codex`. Codex writes `.agent/handoff/a1_request.md` and invokes
  `python $env:USERPROFILE\.codex\skills\orchestrator-agent\scripts\run_a1_grok.py --cwd <REPO> --envelope-file .agent\handoff\a1_request.md`;
  A2, A3, commit control, and next-batch approval remain on Codex.

## Mandatory Batch01 - Validated Candidate Contracts and Persistence

### Goal

Establish one strict Candidate/Profile/Preference/draft vocabulary, one shared
skill-normalization seam, and validated repositories that later services and
tools can reuse without duplicating canonical business rules.

### Dependencies

Plan 2 and Plan 3 are accepted. Their current migration head, async session
manager, profile/attachment models, compact chat-context seam, and local quality
commands are present.

### Scope Boundary

This batch owns typed domain contracts, normalization, validated repositories,
and compact approved context. It does not read PDF bytes, call ShopAIKey, expose
routes, execute tools, commit drafts, or touch Neo4j.

### Tasks

- [x] (01A): Define strict Candidate, preference, and profile-draft contracts
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.2 Candidate and preference contracts`; `docs/plans/Master_plan.md` > `### 7.1 Shared skill contract`; `docs/plans/Master_plan.md` > `### 7.2 Candidate Profile`; `docs/plans/Master_plan.md` > `### 7.3 Job Preferences`
  - Source Requirements:
    - Implement the exact named `SkillRef`, `CandidateSkill`, `CandidateProfile`, and `JobPreferences` fields, enums, confidence bounds, evidence rules, and profile/preference separation.
    - Define the smallest explicit experience, education, and language models that carry displayable CV facts plus short source evidence; do not infer preferences or add scoring fields.
    - Represent one pending draft as a validated Candidate Profile plus only explicitly proposed preference changes and safe approval-summary data.
  - Dependencies: Accepted `backend/app/db/models/profile.py` JSON storage boundary
  - User Action: None
  - Agent Work:
    1. Search all current profile/context JSON readers and the Phase 0 structured-schema patterns before defining models; document the source's missing nested-field inventory without copying opaque provider data through.
    2. Implement focused Pydantic modules with strict extra-field rejection, bounded strings/lists/evidence, finite confidence/years validation, exact enums, and a draft envelope that distinguishes omitted preference changes from an explicit replacement.
    3. Add schema tests for valid minimal/full documents, every enum and bound, non-finite/negative years, invented evidence/extra keys, nested display facts, preference separation, and safe serialization.
  - Output: One authoritative typed Candidate/Profile/Preference/draft contract for repositories, provider extraction, tools, SSE summaries, and frontend response mapping.
  - Acceptance:
    - All source-enumerated fields and values validate exactly, confidence stays in `[0,1]`, and precise years without timeline evidence are rejected or represented as unknown.
    - Nested items expose only explicit display facts and source evidence; they contain no address-derived preference, score, graph trust, raw document, or provider-control fields.
    - Draft serialization distinguishes “preferences unchanged” from a validated preference replacement and rejects untyped provider extras.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/schemas/test_candidate.py tests/schemas/test_preferences.py tests/schemas/test_profile_draft.py` -> strict contracts, bounds, nesting, and separation tests pass.
    - Required: `cd backend; python -m ruff check app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py tests/schemas; python -m mypy app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py` -> focused schema lint and strict typing pass.
  - Blocked Condition: A source owner requires an exact nested experience/education/language field inventory beyond the documented display-fact/evidence boundary; record `BLOCKED_BY_SOURCE_DECISION` rather than inventing additional mandatory fields.
  - Files: `backend/app/schemas/candidate.py`, `backend/app/schemas/preferences.py`, `backend/app/schemas/profile_draft.py`, `backend/app/schemas/__init__.py`, `backend/tests/schemas/test_candidate.py`, `backend/tests/schemas/test_preferences.py`, `backend/tests/schemas/test_profile_draft.py`

- [x] (01B): Establish deterministic skill normalization and an approval-only seed
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.2 Candidate and preference contracts`; `docs/plans/Plan_4.md` > `### 7.3 Processing pipeline`; `docs/plans/Master_plan.md` > `## 9. Skill Normalization`
  - Source Requirements:
    - Normalize Unicode, whitespace, case, punctuation, and common separators before comparison.
    - Resolve only checked-in approved aliases as verified; generate deterministic canonical keys and provisional status for unknown skills.
    - Preserve explicit user exclusions/corrections and never re-add the same excluded skill from the same CV without new approval.
  - Dependencies: (01A) provides `SkillRef` and `CandidateSkill`
  - User Action: None; an initially empty production seed is valid when no aliases have documented approval.
  - Agent Work:
    1. Search the repository for any normalizer, alias data, graph canonical-key logic, or installed YAML parser; reuse shared normalization primitives and do not fabricate a production taxonomy.
    2. Implement one pure focused normalizer and checked-in `skills_seed.yaml` loader. If no direct YAML dependency exists, add one exact compatible pin rather than a custom parser.
    3. Make the normalizer accept existing/excluded canonical keys, deduplicate aliases deterministically, and keep evidence/source/exclusion fields intact.
    4. Add tests with a synthetic approved seed for aliases, Unicode/separators, duplicates, provisional keys, stable ordering, exclusions, malformed seed data, and empty production seed behavior.
  - Output: The first shared Candidate skill-normalization seam that Plan 5 can reuse unchanged.
  - Acceptance:
    - The same semantic input and seed always produce the same canonical key and ordering.
    - No alias is `verified` unless the approved seed says so; unresolved skills are `provisional` and no trusted `RELATED_TO` relationship is created.
    - An excluded corrected skill is not recreated from the same extraction input.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_skill_normalization.py` -> alias, provisional, correction, malformed-seed, and determinism tests pass.
    - Required: `cd backend; python -m ruff check app/services/skill_normalization.py tests/services/test_skill_normalization.py; python -m mypy app/services/skill_normalization.py` -> focused normalization quality passes.
  - Blocked Condition: A non-empty alias or relationship is requested without an approved repository source; keep it absent and report `BLOCKED_BY_USER_ACTION` for seed approval.
  - Files: `backend/app/services/skill_normalization.py`, `backend/app/data/skills_seed.yaml`, `backend/app/services/__init__.py`, `backend/pyproject.toml`, `backend/tests/services/test_skill_normalization.py`, `backend/tests/fixtures/skills_seed_test.yaml`

- [x] (01C): Implement validated profile, preference, draft, and compact-context repositories
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.2 Candidate and preference contracts`; `docs/plans/Plan_4.md` > `### 7.4 Tool behavior and authorization`; `docs/plans/Master_plan.md` > `### 6.2 Profile storage rule`; `docs/plans/Master_plan.md` > ``### 13.1 `get_candidate_context```
  - Source Requirements:
    - Validate every opaque JSON read/write at the Pydantic boundary and preserve the singleton/no-history model.
    - Create or update one pending draft without modifying approved profile/preferences.
    - Return a bounded approved context without raw PDF text, contact PII, internal storage paths, or provider payloads.
  - Dependencies: (01A), accepted profile/draft/preference ORM models, and `DatabaseSessionManager`
  - User Action: None
  - Agent Work:
    1. Search all current direct ORM profile/preference reads, especially `ChatContextAssembler`, and all session/repository patterns; refactor callers to one validated projection instead of adding parallel JSON parsing.
    2. Implement caller-owned-transaction repositories for singleton load/replace, optional preference preservation/replacement, pending-draft create/load/update/delete, state checks, and active-context source attachment retention.
    3. Extract a focused compact approved-context service and make the existing chat context reuse it with no raw CV content.
    4. Add repository/service tests for invalid stored JSON, singleton behavior, same-draft correction, active-context drafts, rollback, omitted preferences, bounded projection, and privacy exclusions.
  - Output: One validated persistence/context boundary for every later profile service and tool.
  - Acceptance:
    - Invalid JSON never crosses the repository as an approved domain object and failed writes leave no partial singleton or draft change.
    - Repeated correction updates the same pending draft; active profile/preferences remain byte-for-byte unchanged until commit.
    - The shared compact context contains approved display facts/preferences only and is used by existing chat assembly and the future read tool.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/repositories/test_profiles.py tests/repositories/test_preferences.py tests/repositories/test_profile_drafts.py tests/services/test_context_assembly.py` -> validation, draft, singleton, rollback, and context tests pass.
    - Required: `cd backend; python -m ruff check app/repositories app/services/profile_context.py app/services/chat_context.py tests/repositories tests/services/test_context_assembly.py; python -m mypy app/repositories app/services/profile_context.py app/services/chat_context.py` -> focused persistence/context quality passes.
  - Blocked Condition: The accepted profile/draft/preference tables or current migration head are absent or materially differ from the accepted Plan 2 contract; restore or reconcile that prerequisite before execution.
  - Files: `backend/app/repositories/profiles.py`, `backend/app/repositories/preferences.py`, `backend/app/repositories/profile_drafts.py`, `backend/app/repositories/__init__.py`, `backend/app/services/profile_context.py`, `backend/app/services/chat_context.py`, `backend/tests/repositories/test_profiles.py`, `backend/tests/repositories/test_preferences.py`, `backend/tests/repositories/test_profile_drafts.py`, `backend/tests/services/test_context_assembly.py`

## Mandatory Batch02 - Safe PDF Intake to Profile Draft

### Goal

Build one service-owned pipeline from contained PDF bytes through deterministic
redaction and validated structured extraction to a pending draft, with one
shared upload boundary for sidebar and chat callers.

### Dependencies

Batch01 is accepted. Existing root PDF limits, attachment repository/storage,
locked pypdf/ShopAIKey decisions, and fake-test seams remain available.

### Scope Boundary

This batch owns staged CV validation, extraction, redaction, provider
structured output, normalization, and draft creation. It does not approve or
commit a draft, change the active CV/profile, expose profile reads, invoke
Neo4j, or build frontend UI.

### Tasks

- [x] (02A): Implement the fail-closed PDF text and deterministic PII boundary
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.3 Processing pipeline`; `docs/plans/Plan_4.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 10.2 Processing`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Extract with pypdf `layout` mode, enforce at most ten pages through typed settings, and return exact `NO_EXTRACTABLE_TEXT` for zero usable digital text with no OCR fallback.
    - Deterministically remove email, phone, and labeled address/contact-address lines before any external processing.
    - A parse or redaction failure exposes only a stable code and prevents provider invocation.
  - Dependencies: Accepted pypdf pin, Phase 0 benchmark behavior, and root PDF settings
  - User Action: None
  - Agent Work:
    1. Search `backend/evaluation/benchmark_pdf_extraction.py` and current PDF tests before writing; reuse its layout-mode and non-whitespace yield semantics without importing evaluation-only orchestration.
    2. Implement focused PDF extraction/page validation and PII redaction modules with bounded outputs and stable sanitized errors; never log or return raw text outside the internal service boundary.
    3. Add synthetic PDF and pure redaction tests for valid/malformed/over-page/image-only files, multiline contacts, Unicode, false-positive boundaries, redaction failure, and sentinel absence from exceptions/logs.
  - Output: One internal redacted-text boundary safe for structured extraction.
  - Acceptance:
    - Layout extraction reports page count and returns `NO_EXTRACTABLE_TEXT` exactly when the locked usable-character count is zero.
    - Every required contact sentinel is absent after redaction while non-contact experience, education, and skill text remains available.
    - No provider adapter can be called when parsing, page validation, or redaction fails.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_pdf_text.py tests/services/test_pii_redaction.py` -> extraction, page, no-text, redaction, and leakage tests pass.
    - Required: `cd backend; python -m ruff check app/services/pdf_text.py app/services/pii_redaction.py tests/services/test_pdf_text.py tests/services/test_pii_redaction.py; python -m mypy app/services/pdf_text.py app/services/pii_redaction.py` -> focused privacy-boundary quality passes.
  - Blocked Condition: The accepted pypdf version or layout extraction API differs from the locked Phase 0 evidence; stop as `BLOCKED_BY_DEPENDENCY_CONFLICT` rather than selecting another parser or OCR.
  - Files: `backend/app/services/pdf_text.py`, `backend/app/services/pii_redaction.py`, `backend/app/services/__init__.py`, `backend/tests/services/test_pdf_text.py`, `backend/tests/services/test_pii_redaction.py`, `backend/tests/fixtures/cv_pdfs/*`

- [x] (02B): Expose one streaming, deduplicating staged-CV upload boundary
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.1 Upload and file lifecycle`; `docs/plans/Plan_4.md` > `### 7.3 Processing pipeline`; `docs/plans/Master_plan.md` > `### 10.1 Upload`; `docs/plans/Master_plan.md` > `## 14. Public FastAPI Boundary`
  - Source Requirements:
    - `POST /api/attachments/cv` accepts one multipart PDF and returns an attachment ID plus sanitized metadata.
    - Validate declared MIME, leading `%PDF-` magic, ten-megabyte streamed size, page limit, contained path, and SHA-256 without loading an unbounded file into memory.
    - Return an existing valid staged/active attachment for the same hash and leave no duplicate bytes or row.
  - Dependencies: (02A), accepted `AttachmentRepository`, `FilesystemAttachmentStorage`, and typed root settings
  - User Action: None
  - Agent Work:
    1. Search every attachment repository/storage caller and existing containment test before editing; reuse chunked staging, canonical service paths, lookup-by-hash, and cleanup operations.
    2. Add one exact compatible `python-multipart` runtime pin, then implement a thin route and one `cv_ingestion` intake method that streams validation/hash/size, stages bytes, confirms PDF pages, and owns cleanup on every failure/race.
    3. Treat a duplicate as valid only when metadata state/path is canonical and contained bytes can be opened; never return a broken metadata-only duplicate.
    4. Return only attachment ID, safe original filename, MIME, size, page count, and state; map failures to stable codes without paths, PDF text, stack traces, or hash disclosure.
    5. Add service/API tests for unsupported MIME, bad magic, over-size, over-page, traversal-like names, malformed/image-only page parsing, valid PDF, sequential/concurrent duplicate races, missing duplicate bytes, cancellation, and partial cleanup.
  - Output: The only public CV upload endpoint and one reusable staged-attachment result contract.
  - Acceptance:
    - Valid bytes create exactly one contained staged object and one metadata row; repeated/racing identical uploads resolve to one valid staged/active attachment.
    - Every invalid or cancelled upload leaves no partial file, orphan new row, promoted file, or leaked path/hash/text.
    - The route performs no provider call, profile write, approval, or active-file replacement.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_cv_ingestion.py tests/api/test_attachments.py tests/repositories/test_attachments.py tests/services/test_attachment_storage.py` -> streaming, limits, containment, duplicate, cleanup, and regression tests pass.
    - Required: `cd backend; python -m ruff check app/api/attachments.py app/services/cv_ingestion.py app/repositories/attachments.py tests/api/test_attachments.py tests/services/test_cv_ingestion.py; python -m mypy app/api/attachments.py app/services/cv_ingestion.py` -> focused upload quality passes.
  - Blocked Condition: FastAPI multipart parsing cannot be added as one direct pinned dependency compatible with the accepted stack; report `BLOCKED_BY_DEPENDENCY_CONFLICT` and do not hand-roll multipart parsing.
  - Files: `backend/pyproject.toml`, `backend/app/api/attachments.py`, `backend/app/api/__init__.py`, `backend/app/main.py`, `backend/app/services/cv_ingestion.py`, `backend/app/schemas/attachments.py`, `backend/app/repositories/attachments.py`, `backend/tests/api/test_attachments.py`, `backend/tests/services/test_cv_ingestion.py`, `backend/tests/fixtures/cv_pdfs/*`

- [x] (02C): Produce a normalized pending profile draft with one repair ceiling
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.3 Processing pipeline`; `docs/plans/Plan_4.md` > `### 7.4 Tool behavior and authorization`; `docs/plans/Master_plan.md` > `### 10.2 Processing`; `docs/plans/Master_plan.md` > ``### 13.2 `propose_profile_from_cv```; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Run redacted text through locked `gpt-4o-mini` structured extraction, strict Pydantic validation, and at most one schema repair.
    - Normalize extracted skills, preserve short redacted evidence, and create a pending draft without modifying approved state.
    - Never infer Job Preferences from a CV address or send unredacted contact data externally.
  - Dependencies: (01A), (01B), (01C), (02A), and a valid staged/active attachment from (02B)
  - User Action: None; normal validation uses an injected fake provider only.
  - Agent Work:
    1. Search the accepted ShopAIKey adapter/structured-schema diagnostics and every proposed CV orchestration caller; reuse `ShopAIKeyChatAdapter.invoke_structured` and keep all pipeline order in the single `cv_ingestion` service.
    2. Implement strict Candidate extraction from redacted text using the adapter's existing application-owned single-repair ceiling, evidence validation, shared normalization, and transactional pending-draft persistence; do not wrap it in a second repair loop.
    3. Keep existing approved profile/preferences unchanged and preserve a valid source attachment for both new-CV and active-context correction paths.
    4. Add fake-backed tests for success, invalid first output then one repair, repair failure, provider failure, invented/missing evidence, precise years without timeline evidence, exclusions, no preference inference, and unique contact sentinels absent from fake requests, errors, logs, and draft JSON.
  - Output: One service method that turns a valid attachment ID into a sanitized pending profile draft and bounded approval summary.
  - Acceptance:
    - The fake provider receives only deterministically redacted text and is never called after a prior pipeline failure.
    - Exactly zero or one repair call occurs, and invalid final output creates no draft or approved-state change.
    - A valid result is normalized and stored as one validated pending draft; active profile/preferences and attachment state remain unchanged.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_profile_extraction.py tests/services/test_cv_ingestion.py tests/repositories/test_profile_drafts.py tests/services/test_shopaikey_chat.py` -> structured output, repair ceiling, normalization, privacy, and draft tests pass.
    - Required: `cd backend; python -m ruff check app/services/cv_ingestion.py app/services/profile_extraction.py app/services/shopaikey_chat.py tests/services/test_profile_extraction.py tests/services/test_cv_ingestion.py; python -m mypy app/services/cv_ingestion.py app/services/profile_extraction.py app/services/shopaikey_chat.py` -> focused extraction quality passes.
  - Blocked Condition: The accepted ShopAIKey structured-output mode or model pin is unavailable or conflicts with Phase 0 evidence; report `BLOCKED_BY_PROVIDER_COMPATIBILITY` without calling another model or adding an unapproved fallback.
  - Files: `backend/app/services/cv_ingestion.py`, `backend/app/services/profile_extraction.py`, `backend/app/services/shopaikey_chat.py`, `backend/app/services/__init__.py`, `backend/tests/services/test_profile_extraction.py`, `backend/tests/services/test_cv_ingestion.py`, `backend/tests/services/test_shopaikey_chat.py`, `backend/tests/fakes/profile_extraction.py`

## Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync

### Goal

Make every approved singleton change replay-safe for derived Candidate/Skill
data and replace profile/preferences/CV atomically without exposing a missing or
partially approved state.

### Dependencies

Batch02 is accepted. Validated repositories/drafts, the staged/active storage
facade, graph constraints/client, and graph outbox repository are available.

### Scope Boundary

This batch owns Candidate projection/outbox processing and the guarded commit
service's canonical side effects. It does not expose Agent tools, public profile
routes, frontend UI, Job/JobFamily graph data, matching, embeddings, or a
continuous worker.

### Tasks

- [x] (03A): Implement coalescing Candidate outbox work and idempotent graph projection
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.6 Candidate graph synchronization`; `docs/plans/Master_plan.md` > `### 8.4 Graph safety rules`; `docs/plans/Master_plan.md` > `## 21. SQLite-to-Neo4j Synchronization`
  - Source Requirements:
    - Requeue graph work in the same transaction for every approved Candidate change and attempt bounded processing after commit and at startup.
    - Use the approved singleton row ID for `Candidate`, `Skill.canonical_key` for skills, and Neo4j `MERGE` for active `HAS_SKILL` relationships.
    - Excluded skills create no active score-bearing relationship; aliases remain properties, unknowns remain provisional, and no LLM-created `RELATED_TO` edge is trusted.
  - Dependencies: (01B), (01C), existing graph uniqueness constraints/client, and `GraphOutboxRepository`
  - User Action: None; required tests use a fake graph client.
  - Agent Work:
    1. Search every outbox enqueue/claim/requeue caller and graph query helper before changing shared behavior; identify the root singleton replay failure rather than adding a Candidate-only duplicate queue.
    2. Refactor the existing unique `(operation, entity_id)` enqueue path so a later transaction safely coalesces/requeues the latest canonical Candidate state, including terminal failed/synced rows, without resetting unrelated callers or leaking profile payloads.
    3. Keep outbox payloads identifier-only and load the current validated Candidate from SQLite during processing; legitimate skill text such as `CI/CD` must not be misclassified as a storage path.
    4. Implement a focused Candidate projector/processor that replaces stale Candidate skill relationships, merges current non-excluded skills, and marks outbox status with bounded sanitized failures.
    5. Add bounded startup retry and the Candidate-only stage of graph rebuild while leaving Job/JobFamily/embedding stages explicitly incomplete for later phases.
    6. Add repository/fake-graph tests for two successive approvals, pending coalescing, failed/synced requeue, rollback, Neo4j unavailability, replay, stale relationship removal, exclusions, provisional/alias properties, and no duplicate nodes/edges.
  - Output: A repeatable identifier-only Candidate sync event and idempotent Candidate/Skill graph projection.
  - Acceptance:
    - Two successive Candidate changes each become processable sync work even though the logical singleton identity is unchanged, with no duplicate outbox row or stale terminal state.
    - Replaying or restarting produces one Candidate, one Skill per canonical key, and the exact current non-excluded `HAS_SKILL` set.
    - Neo4j failure leaves canonical SQLite data intact and work retryable; no raw CV/profile document, contact PII, storage path, or trusted `RELATED_TO` edge enters the outbox/graph.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py tests/infrastructure/test_rebuild_graph.py tests/test_lifecycle.py` -> coalescing, replay, projection, rebuild-slice, and startup tests pass.
    - Required: `cd backend; python -m ruff check app/repositories/graph_outbox.py app/graph/candidate_sync.py tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py; python -m mypy app/repositories/graph_outbox.py app/graph/candidate_sync.py` -> focused sync quality passes.
    - Optional: `cd backend; python -m pytest -q -m neo4j tests/integration/test_candidate_sync.py` -> live local Neo4j replay observation when the user has supplied ignored root credentials.
  - Blocked Condition: Correct repeated singleton sync requires weakening accepted uniqueness/transaction guarantees or adding a second canonical Candidate identity; stop as `BLOCKED_BY_ARCHITECTURE_CONFLICT` rather than using process memory or duplicate graph identities.
  - Files: `backend/app/repositories/graph_outbox.py`, `backend/app/graph/candidate_sync.py`, `backend/app/graph/__init__.py`, `backend/app/main.py`, `infrastructure/scripts/rebuild_graph.py`, `backend/tests/repositories/test_graph_outbox.py`, `backend/tests/graph/test_candidate_sync.py`, `backend/tests/integration/test_candidate_sync.py`, `backend/tests/infrastructure/test_rebuild_graph.py`, `backend/tests/test_lifecycle.py`

- [x] (03B): Atomically commit a draft with filesystem compensation and cleanup retry
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.5 Atomic replacement`; `docs/plans/Master_plan.md` > `### 6.2 Profile storage rule`; `docs/plans/Master_plan.md` > `### 10.4 Atomic replacement`; `docs/plans/Master_plan.md` > `### 21.1 Outbox rule`
  - Source Requirements:
    - Keep the previous approved profile/CV usable until final approval and never expose an intermediate no-profile state.
    - Promote a staged source before SQLite commit; in one transaction replace singleton profile, replace preferences only when proposed, mark the new active attachment, delete the draft, and enqueue Candidate sync.
    - Restore staged bytes and old approved state on any pre-commit failure; retain a retryable cleanup record if only post-commit old-file cleanup fails.
  - Dependencies: (01C), (02C), (03A), and accepted attachment storage/repository transaction ownership
  - User Action: None
  - Agent Work:
    1. Search all filesystem promote/delete/open and attachment/profile repository callers before extending them; reuse canonical service paths and add only the narrow inverse/prepare operation required for compensation.
    2. Implement a focused `profile_service` unit of work for staged-CV commits, already-active hash duplicates, and active-context corrections. Active-context changes keep the current file; omitted preferences preserve the current singleton.
    3. For a staged source, promote first, execute validated singleton/draft/attachment/outbox changes in one SQLite transaction, and restore the source to a usable staged state if commit fails.
    4. After commit, delete the old unreferenced bytes and then metadata. If deletion fails, leave that unreferenced attachment row/path as the durable bounded cleanup-retry record and keep the newly committed active path valid.
    5. Add failure injection at validation, promotion, each repository mutation/flush, outbox enqueue, commit, compensation, and old cleanup; prove the previous profile/CV remains usable before commit and the new profile/CV remains usable after a cleanup-only failure.
  - Output: One transaction-owned profile commit service with recoverable draft/file compensation and identifier-only graph enqueue.
  - Acceptance:
    - Success leaves exactly one singleton profile pointing to the intended active attachment, applies only proposed preferences, removes the draft, and creates/requeues Candidate sync in the same commit.
    - Every failure before SQLite commit preserves the prior approved singleton/file and a recoverable pending draft/source; no intermediate public read sees a missing profile or file.
    - A post-commit old-file cleanup failure does not roll back the new approved state and leaves a durable unreferenced attachment record that a later bounded cleanup pass removes safely.
    - Active-context-only corrections and already-active duplicate sources commit without moving/deleting the current active PDF.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_profile_service.py tests/integration/test_profile_replacement.py tests/repositories/test_attachments.py tests/repositories/test_graph_outbox.py` -> success, duplicate/active-context, failure injection, compensation, cleanup retry, and enqueue tests pass.
    - Required: `cd backend; python -m ruff check app/services/profile_service.py app/services/attachment_storage.py app/repositories tests/services/test_profile_service.py tests/integration/test_profile_replacement.py; python -m mypy app/services/profile_service.py app/services/attachment_storage.py app/repositories` -> focused transaction/compensation quality passes.
  - Blocked Condition: The accepted storage facade cannot restore a promoted file or the unreferenced attachment row cannot safely represent pending cleanup without a schema redesign; stop as `BLOCKED_BY_ARCHITECTURE_CONFLICT` before changing canonical state.
  - Files: `backend/app/services/profile_service.py`, `backend/app/services/attachment_storage.py`, `backend/app/services/attachment_storage_ops.py`, `backend/app/repositories/attachments.py`, `backend/app/repositories/profiles.py`, `backend/app/repositories/preferences.py`, `backend/app/repositories/profile_drafts.py`, `backend/tests/services/test_profile_service.py`, `backend/tests/integration/test_profile_replacement.py`, `backend/tests/repositories/test_attachments.py`

## Mandatory Batch04 - Production Tools and Approval Workflow

### Goal

Expose the four Plan 4 domain tools through the existing registry and make the
existing interrupt/resume path carry bounded profile approval, same-draft
correction, and application-owned commit authorization.

### Dependencies

Batch03 is accepted. Draft production, compact context, atomic commit, same-run
resume/idempotency, the one Agent graph, and the exact SSE union are available.

### Scope Boundary

This batch owns the four tool wrappers, dependency injection, tool-state
authorization, typed approval payload, and backend request-changes loop. It does
not create HTTP tool endpoints, another graph/event, frontend rendering, Job
tools, or later matching behavior.

### Tasks

- [x] (04A): Register compact-context and draft-proposal tools through one service seam
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.4 Tool behavior and authorization`; `docs/plans/Master_plan.md` > ``### 13.1 `get_candidate_context```; `docs/plans/Master_plan.md` > ``### 13.2 `propose_profile_from_cv```; `docs/plans/Master_plan.md` > ``### 13.3 `propose_profile_update```; `docs/plans/Master_plan.md` > `### 13.8 Tool authorization matrix`
  - Source Requirements:
    - `get_candidate_context` is read-only and returns compact approved profile/preferences without raw CV text.
    - `propose_profile_from_cv(attachment_id)` validates attachment state and creates a draft but never commits.
    - `propose_profile_update` updates the same pending draft or creates one from active context, validates profile/preference changes, and never writes approved state.
  - Dependencies: (01C), (02C), accepted tool registry/factory injection, and existing ChatService graph build seam
  - User Action: None
  - Agent Work:
    1. Search all registry/graph construction and context/draft callers before adding tools; reuse dependency injection and do not put domain persistence in `graph.py` or call FastAPI from a tool.
    2. Implement focused LangChain tool factories backed by compact-context, CV ingestion, and draft repositories/services, with strict input schemas and sanitized bounded results.
    3. Replace the empty production registry factory with a dependency-injected Plan 4 registry containing only these three tools at this task boundary; retain fake tool injection for tests and reserve later Job tool names.
    4. Enforce the authorization matrix from current application state and attachment/draft ownership, not model claims, and emit one approval-required marker/summary for every valid proposal.
    5. Add tests for state availability, invalid/stale IDs, read-only context, same-draft corrections, active-context preference changes, no approved write, sanitized results, registry names, and no internal HTTP call.
  - Output: Three real production tools that reuse one context/draft pipeline and stage approval without committing.
  - Acceptance:
    - Tool availability follows the source matrix, inputs are strict, and invalid/stale state fails closed with stable sanitized outcomes.
    - Every proposal produces or updates one validated pending draft and leaves approved profile/preferences/CV unchanged.
    - The production registry contains only Plan 4 tools implemented so far; no synthetic or Job/matching tool is exposed.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/tools/test_candidate_context.py tests/tools/test_profile_draft.py tests/tools/test_registry.py tests/services/test_context_assembly.py` -> tool contract, authorization, draft, registry, and privacy tests pass.
    - Required: `cd backend; python -m ruff check app/tools/candidate_context.py app/tools/profile_draft.py app/tools/registry.py tests/tools; python -m mypy app/tools/candidate_context.py app/tools/profile_draft.py app/tools/registry.py` -> focused tool quality passes.
  - Blocked Condition: The accepted graph/registry cannot receive service dependencies without a second global registry or HTTP callback; stop as `BLOCKED_BY_ARCHITECTURE_CONFLICT` and preserve the Plan 3 seam.
  - Files: `backend/app/tools/candidate_context.py`, `backend/app/tools/profile_draft.py`, `backend/app/tools/registry.py`, `backend/app/tools/__init__.py`, `backend/app/services/chat_service.py`, `backend/app/main.py`, `backend/tests/tools/test_candidate_context.py`, `backend/tests/tools/test_profile_draft.py`, `backend/tests/tools/test_registry.py`

- [x] (04B): Guard commit and same-draft corrections with typed same-run approval
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.4 Tool behavior and authorization`; `docs/plans/Master_plan.md` > `### 10.3 Chat approval`; `docs/plans/Master_plan.md` > ``### 13.4 `commit_profile_draft```; `docs/plans/Plan_3.md` > `## 10. Handoff Notes for Plan 4 (Master Phase 3)`
  - Source Requirements:
    - `commit_profile_draft(draft_id, idempotency_key)` runs only from valid application-owned interrupt approval state and refuses direct, stale, mismatched, or duplicate unauthorized execution.
    - `approval_required` carries a bounded sanitized profile/preference summary without changing the accepted eight event names.
    - “Request Changes” sends the next composer correction into the same run/draft, validates it through `propose_profile_update`, and returns a fresh approval summary.
  - Dependencies: (03B), (04A), accepted checkpoint/same-run resume, resume idempotency, SSE serializer, and graph approval marker
  - User Action: None
  - Agent Work:
    1. Search the current approval marker, graph interrupt extraction, `ResumeRequest`, ChatService resume flow, tool execution context, and every approval test; fix the root gap where correction text is stored but not fed back to model/tool state.
    2. Define one bounded discriminated profile approval payload with only display-safe summary fields; extend the existing backend SSE payload compatibly and keep internal draft/run authorization data out of the displayed summary.
    3. Add an application-owned approval context that binds run, pending draft, action, and resume idempotency key. Reuse LangGraph state injection where supported; the LLM/document cannot manufacture the context.
    4. Implement approve resume as exactly one guarded commit. Implement correction resume by injecting the nonblank correction into the same checkpointed run/draft, updating that draft once, and interrupting again with a new summary.
    5. Register `commit_profile_draft` alongside the three (04A) tools through the existing registry and add direct-call, forged/mismatched, duplicate-key, disconnect/retry, correction-loop, no-write-before-approve, and sanitized-payload tests.
  - Output: Four real Plan 4 tools on one typed, idempotent, application-authorized interrupt/resume workflow.
  - Acceptance:
    - Direct or forged commit execution changes nothing; only an approve resume for the matching pending run/draft can commit.
    - Replaying the same resume idempotency key returns the durable outcome without a second commit, file operation, outbox requeue, or tool record.
    - A correction resumes the same run, updates the same draft, preserves approved state, and produces another valid `approval_required` event.
    - The SSE union still contains exactly the accepted eight event names and exposes no raw CV text, contact PII, tool arguments, storage paths, or internal authorization token.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/tools/test_profile_commit.py tests/agent/test_profile_approval.py tests/integration/test_profile_approval.py tests/api/test_chat.py tests/schemas/test_sse.py` -> authorization, same-run correction, idempotency, SSE, and no-write tests pass.
    - Required: `cd backend; python -m ruff check app/agent app/tools/profile_commit.py app/schemas/sse.py app/schemas/chat.py app/services/chat_service.py tests/agent/test_profile_approval.py tests/tools/test_profile_commit.py tests/integration/test_profile_approval.py; python -m mypy app/agent app/tools/profile_commit.py app/schemas/sse.py app/schemas/chat.py app/services/chat_service.py` -> focused approval quality passes.
  - Blocked Condition: Commit authorization can be derived only from LLM-controlled arguments or would require a second graph/conversation/HTTP tool path; stop as `BLOCKED_BY_SECURITY_ARCHITECTURE`.
  - Files: `backend/app/agent/approval.py`, `backend/app/agent/graph.py`, `backend/app/agent/state.py`, `backend/app/tools/profile_commit.py`, `backend/app/tools/registry.py`, `backend/app/schemas/profile_draft.py`, `backend/app/schemas/sse.py`, `backend/app/schemas/chat.py`, `backend/app/services/chat_service.py`, `backend/app/api/chat.py`, `backend/tests/tools/test_profile_commit.py`, `backend/tests/agent/test_profile_approval.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/api/test_chat.py`, `backend/tests/schemas/test_sse.py`

## Mandatory Batch05 - Public Reads and Shared Astryx CV Experience

### Goal

Expose only sanitized approved profile/CV reads and integrate one shared upload,
sidebar state, composer token, and profile approval experience into the accepted
frontend shell.

### Dependencies

Batch04 is accepted. The upload, profile read models, four-tool approval payload,
same-run correction behavior, and accepted frontend transport/reducer are stable.

### Scope Boundary

This batch owns the two profile GET routes and their typed frontend consumers,
shared upload state, sidebar/composer integration, and profile approval card. It
does not add public profile mutations, a full editor, direct storage access, JD
UI, matching cards, or another application shell.

### Tasks

- [x] (05A): Expose sanitized approved profile and active-CV read endpoints
  - Source of Truth: `docs/plans/Plan_4.md` > `### 7.1 Upload and file lifecycle`; `docs/plans/Master_plan.md` > `## 14. Public FastAPI Boundary`; `docs/plans/Master_plan.md` > `### 14.1 API rules`
  - Source Requirements:
    - `GET /api/profile` returns only approved profile/preferences and safe active attachment metadata.
    - `GET /api/profile/cv` streams only the singleton-referenced active PDF with safe content headers.
    - Neither route returns raw PDF text, storage paths, contact-only extraction data, draft data, or a mutation surface.
  - Dependencies: (01C), (03B), existing contained storage open method, and FastAPI lifecycle/router patterns
  - User Action: None
  - Agent Work:
    1. Search health/chat response and streaming patterns plus every profile/attachment read caller; reuse validated repositories and service-relative path authority.
    2. Define one strict safe profile response, including a deterministic documented no-profile state, and implement thin GET routes that resolve the active file only through `candidate_profile.active_attachment_id`.
    3. Sanitize filename/content-disposition and failure envelopes; stale unreferenced cleanup rows must never be downloadable.
    4. Add API tests for no profile, active profile with/without preferences, safe metadata, invalid stored JSON, missing/mismatched bytes, headers, chunked download, and prohibited-field/sentinel absence.
  - Output: Two read-only profile endpoints completing the seven-route public boundary.
  - Acceptance:
    - `GET /api/profile` has one typed deterministic no-profile/active contract and never exposes a draft, raw text, path, hash, or provider payload.
    - `GET /api/profile/cv` streams only the current singleton-referenced active bytes with `application/pdf` and safe filename headers; stale/unreferenced rows are inaccessible.
    - No public profile PUT/PATCH/DELETE/commit route exists.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/api/test_profile.py tests/api/test_attachments.py tests/test_lifecycle.py` -> profile state, safe metadata/download, route, and lifecycle tests pass.
    - Required: `cd backend; python -m ruff check app/api/profile.py app/schemas/profile.py tests/api/test_profile.py; python -m mypy app/api/profile.py app/schemas/profile.py` -> focused read API quality passes.
  - Blocked Condition: The committed singleton references a non-contained or irrecoverably missing active file; return the sanitized failure and report `BLOCKED_BY_DATA_INTEGRITY` rather than serving another attachment row.
  - Files: `backend/app/api/profile.py`, `backend/app/api/__init__.py`, `backend/app/schemas/profile.py`, `backend/app/main.py`, `backend/tests/api/test_profile.py`, `backend/tests/test_lifecycle.py`

- [x] (05B): Add one typed profile client, upload state, and responsive CV sidebar
  - Source of Truth: `docs/plans/Plan_4.md` > `## 4. Scope`; `docs/plans/Plan_4.md` > `### 7.1 Upload and file lifecycle`; `docs/plans/Master_plan.md` > `### 14.1 API rules`; `docs/plans/Master_plan.md` > `### 15.1 Layout`; `docs/plans/Master_plan.md` > `### 15.2 Sidebar`
  - Source Requirements:
    - Sidebar and chat upload use the same endpoint/client and shared attachment state.
    - Sidebar shows only active filename, profile state, upload/replace action, and active-CV view/download.
    - Sidebar upload immediately starts an existing chat turn with the returned attachment ID; the frontend never reads a store/provider directly.
  - Dependencies: (02B), (04B), (05A), accepted `VITE_API_BASE_URL` reader, chat API injection seam, and single `AppShell`
  - User Action: None
  - Agent Work:
    1. Run `npx astryx build "CV profile sidebar and approval workflow"`, then run `npx astryx component AppShell`, `npx astryx component SideNav`, `npx astryx component FileInput`, `npx astryx component StatusDot`, and `npx astryx component Token` before editing UI.
    2. Search chat API URL/error helpers and current `ChatShell` responsibilities; extract shared HTTP helpers and a focused chat controller/hook rather than duplicating logic or growing files already over 300 lines.
    3. Implement strict runtime-parsed profile/upload contracts, one `uploadCv` client, one `fetchProfile` client, one safe CV URL helper, and one shared upload state machine for idle/uploading/uploaded/error/removal/replacement.
    4. Add `ProfileSidebar` through the existing `AppShell.sideNav`/responsive seam using documented defaults/tokens. Do not force a raw 256px value when the pinned component has no documented width prop.
    5. On sidebar success, call the existing turn transport once with the source-approved deterministic text and returned attachment ID; refresh profile state after an approved commit.
    6. Add API/state/component tests for safe parsing/errors, multipart body, both callers sharing one uploader, immediate sidebar turn, replacement/error recovery, active CV link, responsive shell, and no duplicate upload request.
  - Output: One typed frontend profile boundary and responsive sidebar sharing upload state with chat.
  - Acceptance:
    - Sidebar and composer import the same upload client/state contract; neither duplicates multipart, base-URL, error, or attachment business logic.
    - A successful sidebar upload sends exactly one turn with the deterministic non-PII text and returned attachment ID.
    - Sidebar renders only source-authorized fields/actions in the existing shell and uses documented Astryx APIs/tokens with no raw layout element or direct store/provider call.
  - Validation:
    - Required: `cd frontend; npm run test -- --run src/features/profile src/features/chat/api.test.ts src/test/app.chat.test.tsx` -> client, shared state, sidebar, turn, and shell tests pass.
    - Required: `cd frontend; npm run check:astryx; npm run lint; npm run typecheck` -> pinned Astryx compatibility, lint, and typing pass.
    - Optional: `cd frontend; npm run dev` plus the repository layout inspection at 1440x900 and 390x844 -> sidebar/profile states are visually usable when a browser is available.
  - Blocked Condition: The pinned Astryx package lacks a documented shell/sidebar/file-input API required by the accepted design; report `BLOCKED_BY_ASTRYX_CONTRACT` with CLI evidence before introducing a raw custom layout.
  - Files: `frontend/src/lib/http.ts`, `frontend/src/features/profile/contracts.ts`, `frontend/src/features/profile/api.ts`, `frontend/src/features/profile/api.test.ts`, `frontend/src/features/profile/state/uploadState.ts`, `frontend/src/features/profile/state/uploadState.test.ts`, `frontend/src/features/profile/components/ProfileSidebar.tsx`, `frontend/src/features/profile/components/ProfileSidebar.test.tsx`, `frontend/src/features/chat/api.ts`, `frontend/src/features/chat/components/useChatController.ts`, `frontend/src/features/chat/components/ChatShell.tsx`, `frontend/src/app/App.tsx`, `frontend/scripts/check-astryx-compatibility.mjs`, `frontend/scripts/inspect-chat-layout.mjs`

- [x] (05C): Integrate the composer CV token and profile-specific approval card
  - Source of Truth: `docs/plans/Plan_4.md` > `## 4. Scope`; `docs/plans/Plan_4.md` > `### 7.4 Tool behavior and authorization`; `docs/plans/Plan_4.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 10.3 Chat approval`; `docs/plans/Master_plan.md` > `### 15.3 Chat components`
  - Source Requirements:
    - Chat upload renders a PDF attachment token and submits its attachment ID through the existing turn request.
    - A profile approval summary uses Astryx `ButtonGroup` with “Save Profile” and “Request Changes”.
    - Request Changes focuses the main composer; its next correction updates the same draft and returns another approval card. Each action is idempotently disabled.
  - Dependencies: (04B), (05B), accepted chat contracts/reducer/API, and bounded backend profile approval payload
  - User Action: None
  - Agent Work:
    1. Run `npx astryx component ChatComposer`, `npx astryx component ChatComposerDrawer`, `npx astryx component ChatComposerInput`, `npx astryx component Token`, `npx astryx component Card`, `npx astryx component MetadataList`, `npx astryx component ButtonGroup`, and `npx astryx component Button`, then search current generic approval/reducer callers.
    2. Add a removable PDF token using the shared (05B) uploader/state; include the attachment ID on the user's next normal turn and never put file bytes/path/hash into chat state.
    3. Extend the existing typed SSE contract/reducer with the bounded profile approval payload and render a profile-specific summary card while retaining generic approval behavior for non-profile interrupts.
    4. Replace the profile flow's inline correction textarea: Request Changes enters correction mode and focuses the main composer; its next nonblank submit uses the existing same-run `correct` resume and matching draft.
    5. Disable an approval instance on its first in-flight action and never re-enable it after accepted resume. A corrected draft's new interrupt creates a new actionable card; duplicate clicks/keys cannot send twice.
    6. Add raw-SSE, reducer, component, and full transport tests for token add/remove/send, sanitized payload rendering, Save Profile, composer focus/correction, fresh reapproval, disconnect/error, and in-flight/post-success disable behavior.
  - Output: A shared chat CV token and source-compliant profile approval/correction experience on the existing transport.
  - Acceptance:
    - Chat and sidebar upload use the exact same client/state; a chat token submits one attachment ID with one user turn and is removable before send.
    - Profile approval renders only typed sanitized profile/preference summary fields and the exact source actions; no raw CV, contact PII, internal ID/path, or tool arguments appear.
    - Save and Request Changes each send at most one resume; correction uses the focused main composer, updates the same draft/run, and a new approval remains independently actionable.
    - Existing ordinary chat, generic approval, duplicate filtering, failure, and disconnect behavior remains green.
  - Validation:
    - Required: `cd frontend; npm run test -- --run src/features/profile/components src/features/chat/components src/features/chat/reducer.test.ts src/features/chat/api.test.ts src/test/chat-transport.integration.test.tsx` -> token, approval, correction, idempotency, and transport tests pass.
    - Required: `cd frontend; npm run check:astryx; npm run lint; npm run typecheck; npm run build` -> component compatibility and production build pass.
    - Optional: `cd frontend; npm run dev` plus layout inspection at 1440x900 and 390x844 -> token, card, focus, disabled, and corrected-card states are visually verified when a browser is available.
  - Blocked Condition: The finalized backend profile approval payload or same-run correction contract from (04B) is absent or materially differs; restore that accepted contract before frontend implementation rather than guessing wire fields.
  - Files: `frontend/src/features/chat/contracts.ts`, `frontend/src/features/chat/reducer.ts`, `frontend/src/features/chat/reducer.test.ts`, `frontend/src/features/chat/api.ts`, `frontend/src/features/chat/api.test.ts`, `frontend/src/features/chat/components/ChatComposerPanel.tsx`, `frontend/src/features/chat/components/ChatComposerPanel.test.tsx`, `frontend/src/features/chat/components/ChatApproval.tsx`, `frontend/src/features/chat/components/ChatApproval.test.tsx`, `frontend/src/features/chat/components/ProfileApprovalCard.tsx`, `frontend/src/features/chat/components/ProfileApprovalCard.test.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/components/ChatMessages.test.tsx`, `frontend/src/features/chat/components/ChatShell.tsx`, `frontend/src/features/chat/components/ChatShell.test.tsx`, `frontend/src/test/chat-transport.integration.test.tsx`, `frontend/scripts/check-astryx-compatibility.mjs`, `frontend/scripts/inspect-chat-layout.mjs`

## Mandatory Batch06 - Phase 3 Exit Proof and Plan 5 Handoff

### Goal

Prove the complete fake-backed CV-to-approved-profile slice, all source-required
privacy/rollback/replay gates, the exact public surface, and the stable inputs
that Plan 5 may consume.

### Dependencies

Every Batch01-Batch05 task is A2-accepted and checked with matching execution
and review evidence.

### Scope Boundary

This batch owns cross-component proof and root README handoff documentation. It
may repair only defects exposed by that proof within Plan 4 scope; it does not
add JD ingestion, Job graph data, matching, live-provider requirements, or
future hardening features.

### Tasks

- [ ] (06A): Prove the full profile workflow and publish the Plan 5 handoff
  - Source of Truth: `docs/plans/Plan_4.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_4.md` > `## 10. Handoff Notes for Plan 5 (Master Phase 4)`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy`; `docs/plans/Master_plan.md` > `### Phase 3 — CV, Candidate Profile, and approval workflow`
  - Source Requirements:
    - Prove shared sidebar/chat upload, draft-only proposal/correction, guarded approval, atomic replacement, restart persistence, PII isolation, and replay-safe Candidate sync.
    - The phase exits only when no profile write occurs without approval, PII leakage has zero failures, and every failed pre-commit replacement preserves the previous active profile/CV.
    - Publish only the stable approved profile/preferences, normalization, redaction/extraction, tool authorization, outbox/sync, and structured card seams for Plan 5.
  - Dependencies: All earlier Plan 4 tasks and accepted Plan 2/Plan 3 full transport fixtures
  - User Action: None for required proof. Live ShopAIKey/Neo4j/Compose observation uses only a user-populated ignored root `.env` and is optional.
  - Agent Work:
    1. Search existing full chat transport fixtures, route inventories, secret scans, README handoffs, and every shared seam changed by Plan 4; reuse them instead of creating a second test harness.
    2. Add one backend fake-backed integration flow: upload a synthetic digital PDF, assert provider redaction, create/correct the same draft, reject direct commit, approve once, persist profile/preferences/file, enqueue/process Candidate sync, replay duplicate keys/outbox, restart, and re-read the approved state.
    3. Failure-inject every replacement boundary and prove the old state before commit and new state after cleanup-only failure. Include over-limit/type/magic/path/no-text/repair/provider/Neo4j failures with sanitized outcomes.
    4. Add one frontend integration flow from raw SSE through the real parser/reducer/shell for sidebar upload, composer token, proposal card, Request Changes, fresh card, Save Profile, duplicate actions, profile refresh, errors, and disconnect.
    5. Update accepted Plan 3 route/registry assertions, verify production has exactly the four Plan 4 tools and no synthetic/raw-document exposure, and prove application routes are exactly the seven authorized routes.
    6. Update root `README.md` with evidence-backed Plan 4 batch status, focused/full local commands, current limitations, and the precise Plan 5 handoff. Do not claim optional live observations that were not run.
  - Output: Reproducible Phase 3 exit evidence and a current root README authorizing only the stable Plan 5 inputs.
  - Acceptance:
    - Full fake-backed backend/frontend flows pass with zero real provider calls and zero contact sentinel leakage across requests, SSE, history, durable rows, outbox, logs, errors, and graph parameters.
    - Unauthorized/direct/duplicate actions cause zero extra profile, file, draft, tool, or outbox effects; restart retains approved corrections/preferences.
    - Every pre-commit injected failure leaves the prior profile/CV readable; cleanup-only failure leaves the new state readable and retryable.
    - Candidate outbox replay produces no duplicate nodes/relationships and no excluded active skill edge.
    - Root `README.md` truthfully records Plan 4 completion evidence, exact commands/routes, remaining limitations, and the Plan 5 ownership boundary.
  - Validation:
    - Required: `cd backend; python -m ruff check app tests; python -m mypy app; python -m pytest -q; python -m pytest -q tests/integration/test_full_profile_workflow.py` -> all backend quality gates and focused full workflow pass without network calls.
    - Required: `cd frontend; npm ci --ignore-scripts; npm run check:astryx; npm run lint; npm run typecheck; npm run test -- --run; npm run test -- --run src/test/profile-workflow.integration.test.tsx; npm run build` -> all frontend gates and focused profile workflow pass.
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml config` -> static three-service configuration resolves without real secrets.
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml build` -> production images include Plan 4 runtime dependencies and build successfully; if Docker is unavailable, record exact `BLOCKED_BY_ENVIRONMENT` evidence rather than claiming PASS.
    - Required: `rg -n "synthetic|echo_label|raw_cv|document_text|contact_address|propose_profile_from_cv|commit_profile_draft|save_job|match_jobs" backend/app frontend/src; rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api; git diff --check` -> reviewed exposure/route inventory and clean diff evidence are recorded, with domain names present only where authorized.
    - Optional: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d` followed by one user-observed upload/approve/read flow -> local live observation only when the user supplies ignored secrets; never required for acceptance.
  - Blocked Condition: A required local command cannot run because Docker/tooling is unavailable; record `BLOCKED_BY_ENVIRONMENT` for that command. Any functional, privacy, authorization, rollback, replay, or route failure remains an implementation defect and is not an environment blocker.
  - Files: `backend/tests/integration/test_full_profile_workflow.py`, `backend/tests/fixtures/cv_pdfs/*`, `frontend/src/test/profile-workflow.integration.test.tsx`, `README.md`, and only the narrow Plan 4 implementation/test files required to repair failures exposed by this task

## Optional Future Tracks

No optional implementation track is authorized by Plan 4. OCR, DOCX/image CVs,
multiple active CVs, profile history, a full profile editor, JD/Job behavior,
matching, continuous workers, Qdrant, CI, cloud deployment, and trusted
LLM-created graph relationships remain outside the mandatory Phase 3 batch
chain. Live provider, Neo4j, browser, or Compose observations may be recorded as
optional validation only and do not replace fake-backed acceptance.
