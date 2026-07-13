# Plan 4 — Master Phase 3: CV, Candidate Profile, and Approval Workflow

> **Numbering:** `Plan_4.md` implements **Master Plan Phase 3**. It adds profile-domain behavior to the generic Agent/runtime contracts from Plan 3.

## 1. Objective

Implement the complete one-active-PDF/one-active-profile workflow: validated upload, exact file-hash reuse, pypdf extraction, structured Candidate/Profile/Preference proposals, deterministic skill normalization, in-chat human approval, constraint-safe replacement, sidebar state, and direct Candidate/Skill synchronization to Neo4j.

No profile or preference write may reach the active singleton records without the existing LangGraph interrupt/resume path. Rejection must preserve the current draft for correction, replacement failures must preserve the previous active profile, and post-commit file/Neo4j failures must never corrupt SQLite truth.

## 2. Source of Truth

- `docs/plans/Master_plan.md` Sections 2.1–2.2: one active PDF, no version history, no OCR/DOCX/image CV, approval, corrections, and structured preferences.
- Sections 6.2–6.4: attachment/profile/draft/preference tables, state transitions, duplicate handling, approval transaction, and cleanup boundaries.
- Sections 7.1–7.3: `SkillRef`, Candidate/Profile/Preference schemas, evidence, confidence, proficiency, and separation of facts/preferences.
- Sections 8–10: Candidate/Skill graph model, deterministic normalization, CV pipeline, approval semantics, replacement order, and sync failure behavior.
- Sections 12.2–12.5: interrupted-run blocking, compact candidate context, structured memory, and job-specific tool boundary.
- Sections 13.1–13.3 and 13.7: the three profile tools and authorization matrix.
- Sections 14–15: CV/profile public endpoints, sidebar, attachment token, approval card, and control disabling.
- Sections 20–22 and 24: stable failure codes, direct sync, safeguards, and profile tests.
- Section 25, “Phase 3 — CV, Candidate Profile, and approval workflow”: tasks and exit gate.

## 3. Prerequisites from Prior Phases

- [ ] Attachment/profile/draft/preference tables and all constraints are at Alembic head.
- [ ] Shared settings expose `FILES_DIR`, `MAX_PDF_SIZE_MB=10`, and `MAX_PDF_PAGES=10`.
- [ ] Attachment storage supports safe UUID-relative paths, atomic creation, existence/open, and explicit best-effort deletion.
- [ ] Generic chat turns, tool replay, typed SSE, interrupt/resume, terminal no-op behavior, and checkpoint cleanup pass.
- [ ] The interrupted-run guard rejects new chat turns before persistence.
- [ ] Neo4j driver/constraints exist; no Candidate sync implementation exists yet.
- [ ] Pinned pypdf behavior and `NO_EXTRACTABLE_TEXT` quality rule are recorded by Plan 1.

## 4. Scope

- Implement `POST /api/attachments/cv`, `GET /api/profile`, and `GET /api/profile/cv`.
- Apply the approval-pending guard before persisting any CV upload bytes or metadata.
- Validate MIME, `%PDF-` magic bytes, maximum 10 MB, maximum 10 pages, and extractable digital text without OCR.
- Compute SHA-256 while streaming and implement active/staged/failed same-file reuse plus different-staged replacement cleanup.
- Implement pypdf layout extraction and stable PDF failure codes.
- Define exact Candidate, skill, experience, education, language, preference, and draft Pydantic contracts.
- Implement one shared deterministic normalizer and a small manually approved `skills_seed.yaml`; later JD and matching phases must reuse it.
- Implement structured CV extraction through the verified ShopAIKey schema strategy, Pydantic validation, and at most one repair.
- Implement `propose_profile_from_cv`, `propose_profile_update`, and interrupt-guarded `commit_profile_draft` as the first production Agent tools.
- Implement `save_profile` and `request_changes` resume semantics using the same interrupted tool invocation.
- Implement the final atomic profile/preferences/attachment/draft transaction and post-commit cleanup.
- Load compact approved Candidate Profile/Preferences into Agent context; never inject raw CV text.
- Synchronize Candidate/Skill nodes and seed relationships directly after a successful profile commit.
- Implement sidebar upload/view/download state, chat attachment token behavior, approval card, disabled approval controls, and request-change composer focus.
- Add profile/CV unit, integration, Agent, graph, and frontend tests.

## 5. Out of Scope

- Multiple active CVs, CV/profile history, draft history/status tables, full profile editor, or public profile write CRUD.
- DOCX, images, OCR, alternate PDF parsers, or real user fixtures in Git.
- JD ingestion/extraction, Job graph nodes, production embeddings, graph rebuild completion, or matching.
- A separate preference tool, memory-fact table, general-purpose memory extraction, or unapproved writes inferred from conversation.
- Moving files during approval, deleting the old active profile before commit, rolling back SQLite because Neo4j/file cleanup failed, or continuously retrying graph sync.
- Additional Agents, worker services, outbox/queue/sync-state tables, or a second idempotency mechanism.

## 6. Target Directory Structure

```text
JobAgent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── attachments.py
│   │   │   └── profile.py
│   │   ├── graph/
│   │   │   └── sync_candidate.py
│   │   ├── repositories/
│   │   │   ├── attachments.py
│   │   │   └── profiles.py
│   │   ├── schemas/
│   │   │   ├── attachments.py
│   │   │   ├── profile.py
│   │   │   └── skills.py
│   │   ├── services/
│   │   │   ├── cv_upload.py
│   │   │   ├── pdf_extraction.py
│   │   │   ├── profile_approval.py
│   │   │   ├── profile_drafts.py
│   │   │   ├── profile_extraction.py
│   │   │   └── skill_normalization.py
│   │   └── tools/
│   │       └── profile.py
│   └── tests/
│       ├── fixtures/
│       │   └── skills_seed.yaml
│       ├── integration/
│       │   ├── test_candidate_sync.py
│       │   ├── test_cv_api.py
│       │   └── test_profile_approval.py
│       └── unit/
│           ├── test_pdf_extraction.py
│           ├── test_profile_schemas.py
│           └── test_skill_normalization.py
├── frontend/
│   └── src/
│       ├── features/profile/
│       │   ├── ApprovalCard.tsx
│       │   ├── CvSidebar.tsx
│       │   ├── api.ts
│       │   └── types.ts
│       └── test/
│           ├── approval-card.test.tsx
│           └── cv-sidebar.test.tsx
└── infrastructure/
    └── neo4j/
        └── skills_seed.yaml
```

Use one authoritative runtime taxonomy file at `infrastructure/neo4j/skills_seed.yaml`. Test-specific seed data may be a smaller fixture, but production normalization and graph synchronization must load through the same parser/service rather than duplicate logic.

## 7. Technical Specifications

### 7.1 Profile and skill schemas

Implement the Master Section 7 contracts exactly:

```text
SkillRef
- canonical_key: str
- display_name: str
- aliases: list[str]
- category: str | None

CandidateSkill
- skill: SkillRef
- confidence: float in [0, 1]
- proficiency: beginner | intermediate | advanced | unknown
- years: float | None
- source: cv | user_correction
- excluded: bool
- evidence: list[str]

CandidateProfile
- summary: str
- current_title: str | None
- total_experience_years: float | None
- skills: list[CandidateSkill]
- experiences: list[ExperienceItem]
- education: list[EducationItem]
- languages: list[LanguageItem]
- extraction_confidence: float in [0, 1]

JobPreferences
- target_roles: list[str]
- preferred_locations: list[str]
- acceptable_work_modes: list[remote | hybrid | onsite]
- target_seniority: list[intern | junior | mid | senior | lead | unknown]

ProfileDraftPayload
- candidate_profile: CandidateProfile
- job_preferences: JobPreferences
```

`ExperienceItem`, `EducationItem`, and `LanguageItem` use the exact fields/nullability from Master Section 7.2. Evidence must be short source snippets. Precise years/proficiency are not inferred without evidence. Profile facts and preferences remain separate; a CV address never becomes a preferred location automatically.

Before every `profile_json`, `draft_json`, or `preferences_json` write, validate the full corresponding Pydantic object.

### 7.2 Skill normalization ownership

`skill_normalization.py` is the sole business implementation for both CV and later JD skills:

1. Unicode normalize.
2. Trim/collapse whitespace.
3. Lowercase for comparison.
4. Normalize punctuation/common separators.
5. Resolve an approved alias from `skills_seed.yaml`.
6. Otherwise derive one deterministic canonical key and assign no related-skill edge.

The taxonomy defines canonical display names, aliases, optional category, and manually approved weighted relationships only. The LLM never supplies aliases/relationships. Unknown skills may become canonical skills with empty aliases/category and no `RELATED_TO` edge.

For an explicit correction, set `source='user_correction'`; excluded skills remain in the approved profile with `excluded=true` and must not be re-added from the same CV without another explicit approval. Do not persist previous profile versions.

### 7.3 Upload validation and exact-hash state handling

`POST /api/attachments/cv` performs this order:

1. Check for an interrupted approval and return `APPROVAL_ACTION_REQUIRED` before reading/persisting the new upload.
2. Stream to a bounded temporary file while computing SHA-256; reject over 10 MB without a final file/row.
3. Require declared MIME `application/pdf` and `%PDF-` magic bytes.
4. Open with pypdf, require `1..MAX_PDF_PAGES`, and reject malformed/oversized files before final storage/row creation.
5. Resolve the hash against `attachments`:
   - Active: delete temp, return existing attachment plus approved-profile summary; no extraction/draft.
   - Current staged: delete temp, return existing attachment/draft.
   - Failed: delete temp, reuse row/file, change to `staged`, clear `failure_code`, and signal explicit retry.
   - New: move atomically to its UUID path, insert `staged` row with page count.
6. Leave any different CV-backed draft/staged attachment intact until the new attachment has been extracted successfully. The proposal service owns replacement of that prior staged state.

Unsupported/oversized/malformed inputs create no final file or attachment row. A later parse/extraction failure changes the staged row to `failed`, stores a stable code, and retains its file for same-file retry/deletion.

Both sidebar and chat attachment paths use this endpoint. A successful sidebar upload immediately starts a normal chat turn containing only the returned `attachment_id` and concise user intent.

### 7.4 PDF/profile extraction

The profile proposal pipeline is:

```text
attachment_id
→ validate staged/active/draft state
→ pypdf layout text extraction
→ Plan 1 meaningful-text validation
→ gpt-4o-mini structured extraction
→ Pydantic validation
→ at most one schema-repair request when invalid
→ shared deterministic skill normalization
→ upsert profile_drafts(id='current')
→ commit_profile_draft interrupt
```

- No meaningful digital text returns `NO_EXTRACTABLE_TEXT` and marks the attachment failed; never call OCR.
- Provider timeout/rate limit retries once, then stores a stable failure.
- Raw extracted CV text is transient service data; it is not stored in LangGraph state, chat messages, tool logs, or Neo4j.
- `arguments_summary_json` and `ToolResult.data` contain only IDs and compact summaries.

### 7.5 Tool contracts and authorization

`propose_profile_from_cv(attachment_id)`:

- Active attachment returns the existing approved profile without a draft or extraction.
- Staged attachment already referenced by `profile_drafts('current')` returns that draft.
- Other valid staged attachment runs the proposal pipeline. Only after successful extraction/validation does it replace `profile_drafts('current')`; it then removes the prior unreferenced staged attachment row and best-effort deletes that prior staged file before returning `draft_id='current'` plus summary.
- It never commits active profile/preferences.

`propose_profile_update(draft_id or active context, requested changes)`:

- Applies profile and/or preference changes to the current draft or an active-context copy.
- Validates the complete `ProfileDraftPayload`, preserves explicit corrections/exclusions, and upserts the singleton draft.
- It is the only update tool; do not add a separate preference tool.

`commit_profile_draft(draft_id='current')`:

- Validates tool authorization and draft existence.
- Calls `interrupt()` before any active-profile/preference side effect.
- Stores `pending_approval_json={kind:'profile_commit', draft_id:'current', allowed_actions:['save_profile','request_changes']}` while the existing tool execution remains `running`.
- Resumes the same invocation only with an allowed action.

All three tools reuse Plan 3 replay semantics and are registered with compact schemas. `match_jobs` remains unauthorized/unavailable until later; any existing approved profile used during a pending replacement remains the active context.

### 7.6 Approval decisions and atomic commit

`request_changes`:

- Completes the original run and running `commit_profile_draft` execution with `ToolResult(ok=true, code=null, data={'committed': false})`.
- Preserves `profile_drafts('current')`, clears pending approval, deletes the old checkpoint, and focuses the composer.
- The correction is a new chat turn/run and creates a new approval interrupt.

`save_profile` validates the complete draft, source attachment state/file, and cross-row prerequisites before opening a transaction. In one SQLite transaction:

1. Upsert `candidate_profile('active')` and point it to the staged attachment when a CV is present.
2. Upsert `job_preferences('active')` only with validated preferences when changed.
3. For replacement, remove the now-unreferenced previous attachment row.
4. Mark the new attachment `active`.
5. Delete `profile_drafts('current')`.
6. Assert exactly one active attachment exists and `candidate_profile.active_attachment_id` references it, then commit.

On transaction failure, roll back: prior profile/CV remains active and new attachment remains staged. After commit, best-effort delete the prior PDF and then synchronize Candidate/Skill graph data. File cleanup failure is reported without invalidating the committed profile. Neo4j failure returns `NEO4J_SYNC_FAILED` plus rebuild instruction without rolling SQLite back.

Successful save ends the tool `completed` with `ToolResult(ok=true)`. A commit/sync execution error ends it `failed` with matching stable code; payload/assistant text must accurately state when SQLite committed but derived sync failed.

Both approval buttons disable after the first accepted action. Repeating resume after terminal state uses Plan 3’s no-op terminal stream.

### 7.7 Candidate graph synchronization

After SQLite commit, `sync_candidate.py` uses parameterized idempotent Cypher to:

- `MERGE` `Candidate{id:'active'}` and set `source_updated_at` from `candidate_profile.updated_at`.
- Remove/rebuild only this Candidate’s `HAS_SKILL` relationships from approved non-excluded skills. Excluded corrections remain in SQLite profile JSON and are omitted from Neo4j so they cannot contribute to matching.
- `MERGE` canonical `Skill` nodes with display name, aliases, and category from the normalizer.
- Set `HAS_SKILL` properties `confidence`, `years`, `proficiency`, and evidence.
- Idempotently load seed `RELATED_TO{weight, source}` relationships from the authoritative taxonomy.

Neo4j never receives raw CV text and never becomes the profile source of truth. Re-running the same payload must be safe.

### 7.8 API and frontend behavior

- `GET /api/profile` returns active profile/preferences plus active attachment metadata, or an explicit empty state; it never returns stored PDF bytes.
- `GET /api/profile/cv` streams only the active PDF with safe content disposition/original display filename.
- Sidebar shows active filename, profile state, upload/replace action, and view/download action only.
- Chat attachments render as compact PDF tokens and send only attachment IDs with the following turn.
- Approval card uses pinned Astryx `Card`, `ButtonGroup`, and `Button`; it summarizes profile/preferences and exposes exactly Save Profile/Request Changes.
- While approval is pending, composer and upload controls are disabled. Request Changes re-enables/focuses composer after the terminal event.

## 8. Implementation Steps

- [ ] Define failing schema/normalizer tests, then implement the exact profile, preference, skill, and draft Pydantic models.
- [ ] Create the small authoritative skill taxonomy and one shared loader/normalizer; search before adding any normalization helper.
- [ ] Implement attachment/profile repositories using existing session/UUID/UTC primitives and no duplicated transition logic.
- [ ] Implement bounded upload validation, streaming hash, exact-hash state resolution, atomic storage, and different-staged cleanup.
- [ ] Implement pypdf layout extraction and reuse the Plan 1 meaningful-text rule.
- [ ] Implement structured profile extraction with fake provider tests, one retry/repair limits, evidence constraints, and shared normalization.
- [ ] Implement profile draft creation/update services and the first two profile tools.
- [ ] Implement `commit_profile_draft` through the existing interrupt/resume runner with exact pending projection/actions.
- [ ] Implement request-changes completion and the constraint-safe Save Profile transaction with rollback tests.
- [ ] Implement post-commit old-file cleanup reporting and idempotent Candidate/Skill/seed graph sync.
- [ ] Add profile context loading to the existing Agent context module without adding raw CV text.
- [ ] Implement the three public CV/profile routes and reuse the interrupted-run guard before upload persistence.
- [ ] Implement sidebar, attachment token, approval card, disabled/idempotent controls, and request-change focus.
- [ ] Add unit/integration/frontend tests for all state transitions, duplicates, approval branches, restart persistence, rollback, cleanup, and graph failure.

## 9. Verification & Testing Plan

### Backend commands

```powershell
Set-Location backend
python -m pytest tests/unit/test_profile_schemas.py tests/unit/test_skill_normalization.py tests/unit/test_pdf_extraction.py -q
python -m pytest tests/integration/test_cv_api.py tests/integration/test_profile_approval.py -q
python -m pytest tests/integration/test_candidate_sync.py -q
```

Expected evidence:

- Invalid PDFs are rejected before persistent row/file creation; image-only input returns `NO_EXTRACTABLE_TEXT` with no OCR.
- Active/staged same-file uploads return existing state; failed same-file upload retries the same row; a different staged file replaces only unreferenced staged state.
- No active profile/preference mutation occurs before Save Profile.
- Request Changes completes the original run/tool, deletes its checkpoint, preserves the draft, and a new correction run can update it.
- A failed replacement transaction leaves the prior profile/attachment active and the new attachment staged.
- Post-commit cleanup failure leaves valid SQLite state; Neo4j failure returns `NEO4J_SYNC_FAILED` without rollback.
- Repeated Candidate sync produces one Candidate and stable relationships.

### Frontend commands

```powershell
Set-Location frontend
npm test -- --run src/test/approval-card.test.tsx src/test/cv-sidebar.test.tsx
npm run typecheck
npm run build
```

Expected: shared sidebar/chat upload pipeline, active filename/view action, exact approval actions, one accepted decision, disabled controls during interrupt, and request-change focus behavior.

### Restart/manual checks

- Approve a synthetic CV and correction, restart the backend, and confirm active profile/preferences and history hydrate correctly.
- Attempt upload/new chat while approval is pending; confirm `APPROVAL_ACTION_REQUIRED` and no new file/message/row.
- Inspect Git to confirm real CV data and runtime files remain untracked.
- Verify raw CV text does not appear in chat/tool/checkpoint/Neo4j persisted payloads.

### Failure handling

- Unsupported/oversized/malformed files leave no persistent input.
- Parse/extraction failures retain a failed row/file for explicit same-file retry.
- Unauthorized commit fails before side effects.
- A failed provider/schema result never produces an approval card or success claim.

## 10. Handoff Notes for Plan 5 / Master Phase 4

Plan 5 receives:

- Approved singleton Candidate Profile and Job Preferences with durable correction semantics.
- One active/staged/failed attachment lifecycle and shared CV upload/profile approval UI.
- The authoritative profile/skill Pydantic models and sole deterministic skill normalizer/taxonomy loader.
- The first three registered production tools and exact interrupt/resume behavior.
- Compact approved candidate context for later Agent turns.
- Idempotent Candidate/Skill/seed synchronization using SQLite timestamps.

Plan 5 must reuse the skill normalizer, taxonomy, provider schema/repair policy, repository/session primitives, tool replay, and graph driver. It adds Job schemas/services/tools, production embeddings, Job sync, and rebuild; it must not reimplement profile approval, normalization, or Candidate synchronization.
