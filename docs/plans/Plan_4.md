# Plan 4 - Master Phase 3: CV, Candidate Profile, and Approval Workflow

## 1. Objective

Implement the complete PDF CV-to-approved-profile flow with shared sidebar/chat upload, deterministic validation and PII redaction, structured extraction, draft-based corrections, interrupt-protected approval, atomic active-file/profile replacement, durable preferences, and Candidate graph synchronization.

## 2. Source of Truth

- `Master_plan.md` sections 6.2 and 7.1-7.3, profile ownership and Pydantic contracts.
- Sections 9-10, skill normalization corrections and CV approval flow.
- Tool contracts 13.1-13.4 and authorization matrix 13.8.
- Public endpoints in section 14 and CV UX in section 15.
- Failure, synchronization, privacy, environment, and test rules in sections 20-24.
- Section 25, **Phase 3 - CV, Candidate Profile, and approval workflow**.
- `Plan_3.md` owns the Agent, SSE, interrupt/resume, and frontend chat seams reused here.

## 3. Prerequisites from Prior Phases

- [ ] The attachment, profile, preference, draft, and outbox tables are migrated.
- [ ] Staged/active attachment storage and path containment are tested.
- [ ] Chat turn, resume, SSE, tool registry, and interrupt support pass Plan 3 tests.
- [ ] The selected pypdf mode and ShopAIKey structured-output mode are locked by Plan 1.
- [ ] Neo4j Candidate/Skill constraints and outbox repository are available.

## 4. Scope

- Implement PDF upload and active-CV download endpoints.
- Validate MIME, magic bytes, 10 MB limit, 10-page limit, and extractable digital text.
- Implement streaming SHA-256 duplicate detection and staged file lifecycle.
- Extract pypdf text, redact contact PII deterministically, and block external calls on redaction failure.
- Implement Candidate Profile, CandidateSkill, nested experience/education/language, Job Preferences, and draft schemas.
- Implement `get_candidate_context`, `propose_profile_from_cv`, `propose_profile_update`, and guarded `commit_profile_draft`.
- Support request-changes updates to the same draft and approval through LangGraph resume.
- Atomically replace the singleton profile/preferences and active PDF with rollback/compensation.
- Enqueue and process Candidate/Skill graph synchronization.
- Implement sidebar state, chat attachment token, approval card, and idempotent action buttons.

## 5. Out of Scope

- OCR, DOCX/image CVs, multiple active CVs, profile history, or a full profile editor.
- JD ingestion, Job extraction, duplicate jobs, Job graph nodes, or matching.
- Automatic profile writes, preference inference from an address, or commit without approval.
- New public profile mutation endpoints; business writes remain Agent tools.
- Trusted graph relationships inferred automatically by the LLM.

## 6. Target Directory Structure

```text
JobAgent/
|-- backend/
|   |-- app/
|   |   |-- api/{attachments.py,profile.py}
|   |   |-- tools/{candidate_context.py,profile_draft.py,profile_commit.py}
|   |   |-- services/{cv_ingestion.py,pdf_text.py,pii_redaction.py,profile_service.py}
|   |   |-- repositories/{profiles.py,profile_drafts.py,preferences.py}
|   |   |-- schemas/{candidate.py,preferences.py,profile_draft.py}
|   |   `-- graph/candidate_sync.py
|   `-- tests/{fixtures,unit,integration}/
`-- frontend/
    `-- src/features/
        |-- profile/{api,components,state}/
        `-- chat/components/
```

Reuse the existing attachment storage, outbox, Agent registry, SSE, and chat components. Extraction orchestration belongs in one CV service, not in routes or tool wrappers.

## 7. Technical Specifications

### 7.1 Upload and file lifecycle

`POST /api/attachments/cv` accepts one multipart PDF and returns an `attachment_id` plus sanitized metadata. Validate declared MIME and `%PDF-` magic bytes while streaming; reject over 10 MB before promotion. After staging, pypdf must confirm at most 10 pages. Hash bytes with SHA-256. A matching file hash returns the existing valid staged/active attachment rather than creating duplicate storage.

`GET /api/profile/cv` streams only the current active PDF with safe content headers. `GET /api/profile` returns approved profile/preferences and safe active attachment metadata; it never returns raw PDF text.

### 7.2 Candidate and preference contracts

Implement the master fields exactly:

```text
SkillRef(canonical_key, display_name, aliases, category, status, confidence, evidence)
CandidateSkill(skill, proficiency, years, source, excluded, evidence)
CandidateProfile(summary, current_title, total_experience_years, skills,
                 experiences, education, languages, extraction_confidence)
JobPreferences(target_roles, preferred_locations, acceptable_work_modes,
               target_seniority)
```

`status` is `verified|provisional`; `proficiency` is `beginner|intermediate|advanced|unknown`; `source` is `cv|user_correction`. Confidence is in `[0,1]`, evidence is short and contact-redacted, and precise years require timeline evidence. Nested experience/education/language models must carry only displayable CV facts and source evidence; they must not infer preferences.

### 7.3 Processing pipeline

```text
attachment_id -> hash check -> pypdf layout extraction
-> extractable-text validation -> deterministic PII redaction
-> gpt-4o-mini structured extraction -> Pydantic validation
-> at most one schema repair -> normalized skills -> profile draft
-> approval_required interrupt
```

Redact email, phone, and labeled address/contact-address lines before external processing. If redaction fails, do not call ShopAIKey. If text is not meaningful, return `NO_EXTRACTABLE_TEXT`; no OCR fallback is allowed.

### 7.4 Tool behavior and authorization

- `get_candidate_context` is read-only and returns compact approved profile/preferences without raw CV text.
- `propose_profile_from_cv(attachment_id)` validates state, creates a draft, and never commits.
- `propose_profile_update(draft_id|active context, changes)` applies profile and preference corrections through Pydantic validation and creates/updates one draft.
- `commit_profile_draft(draft_id, idempotency_key)` requires valid interrupt approval state and refuses direct/duplicate unauthorized execution.

The next user correction after **Request Changes** updates the same draft and returns another approval summary.

### 7.5 Atomic replacement

Keep the old profile/CV active until final approval. In the guarded commit service: prepare a promotable staged file, begin one SQLite transaction, replace singleton profile/preferences, mark attachment states, delete the draft, and enqueue Candidate sync. Commit SQLite only when filesystem promotion succeeds. If a later file cleanup fails, retain a retryable cleanup record while the newly committed active path remains valid. Any failure before commit restores the old active file/profile and leaves the draft recoverable. Never expose an intermediate no-profile state.

### 7.6 Candidate graph synchronization

Outbox processing uses the approved singleton ID for `Candidate`, `Skill.canonical_key` for skills, and `MERGE` for `HAS_SKILL`. Excluded skills do not create active score-bearing relationships. Aliases remain Skill properties. Unknown skills are `provisional`; no LLM-created `RELATED_TO` relationship is trusted.

## 8. Implementation Steps

- [ ] Implement Candidate/Profile/Preference/draft Pydantic models and validation tests.
- [ ] Implement upload streaming, MIME/magic/size/page/hash validation, and safe metadata response.
- [ ] Implement pypdf extraction, meaningful-text gate, deterministic PII redaction, and leakage test adapter.
- [ ] Implement structured profile extraction and the single schema-repair ceiling.
- [ ] Reuse the skill normalization seam for verified aliases/provisional keys and user exclusions.
- [ ] Implement profile/preference/draft repositories and compact context service.
- [ ] Implement the four candidate/profile tools with authorization and sanitized outcomes.
- [ ] Add approval interrupt payload, request-changes loop, idempotent resume, and guarded commit service.
- [ ] Implement atomic/compensated profile and file replacement plus Candidate outbox processing.
- [ ] Implement profile GET/CV download and shared sidebar/chat upload behavior.
- [ ] Implement Astryx profile summary/approval card and disable buttons after success.
- [ ] Add unit, integration, and frontend tests for all success/failure/rollback paths.

## 9. Verification & Testing Plan

- Validate unsupported type, bad magic bytes, oversized, over-page-limit, path traversal, image-only, duplicate, and valid PDF cases.
- Unit-test PII patterns and assert zero redacted contact data reaches the fake ShopAIKey adapter.
- Test invalid extraction, one repair, repair failure, and no invented evidence.
- Verify sidebar and chat uploads call the same endpoint/pipeline.
- Verify proposal and correction create/update a draft but do not modify the approved singleton.
- Verify commit without valid approval is rejected and duplicate approval is idempotent.
- Failure-inject every replacement step and prove the previous approved profile/CV remains usable.
- Restart the backend and prove approved corrections/preferences persist.
- Replay Candidate outbox operations and prove no duplicate graph nodes/relationships.
- Frontend tests cover attachment state, approval payload, request changes, and button disable behavior.

The phase exits only when no profile write occurs without approval, PII leakage tests have zero failures, and replacement failure preserves the previous active profile.

## 10. Handoff Notes for Plan 5 (Master Phase 4)

Plan 5 receives:

- An approved singleton Candidate Profile and separate Job Preferences contract.
- Stable `SkillRef` normalization/provisional rules and Candidate graph data.
- Reusable ShopAIKey structured extraction, redaction boundary, tool authorization, outbox, and graph-sync patterns.
- Shared sanitized tool-status and structured chat-card seams.

Plan 5 owns only JD persistence/extraction/deduplication and Job graph synchronization. It must not alter profile approval semantics, create profile history, duplicate skill canonicalization, or bypass the outbox.
