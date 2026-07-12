---

# Task Review Report - 01A

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
same_task_repair

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch01 - Validated Candidate Contracts and Persistence
- Task ID: 01A
- Task title: Define strict Candidate, preference, and profile-draft contracts
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: `backend/app/schemas/__init__.py`; seven reported implementation/test paths were cross-checked directly because six are untracked and therefore absent from ordinary `git diff`; `docs/reports/report_4_execute_agent.md` and `docs/tasks/task_4.md` are also untracked orchestration artifacts.

## Files Reviewed
- `backend/app/schemas/candidate.py`: in scope - repaired validators require calendar-year, date-range, month-year, or explicit-duration cues before accepting precise years.
- `backend/app/schemas/preferences.py`: in scope - exact preference fields/enums and profile separation are implemented.
- `backend/app/schemas/profile_draft.py`: in scope - omit-versus-replace serialization and bounded approval summary are implemented.
- `backend/app/schemas/__init__.py`: in scope - new contracts are exported.
- `backend/tests/schemas/test_candidate.py`: in scope - includes the required non-timeline rejection cases and explicit timeline/date-range acceptance cases.
- `backend/tests/schemas/test_preferences.py`: in scope - preference enum and separation coverage is present.
- `backend/tests/schemas/test_profile_draft.py`: in scope - draft serialization and extra-field coverage is present.
- `backend/app/db/models/profile.py`: dependency evidence - accepted opaque JSON storage boundary exists.
- `docs/plans/Plan_4.md` and `docs/plans/Master_plan.md`: source requirements reviewed.

## Validations Reviewed
- Command/check: `cd backend; python -m pytest -q tests/schemas/test_candidate.py tests/schemas/test_preferences.py tests/schemas/test_profile_draft.py`
- Required: yes
- Reported result: 70 passed in 0.95s
- Rerun result: 70 passed in 0.90s
- Status: passed
- Notes: The repaired suite covers both prior failing non-timeline examples and accepted date-range/duration evidence.

- Command/check: `cd backend; python -m ruff check app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py tests/schemas`
- Required: yes
- Reported result: passed
- Rerun result: All checks passed
- Status: passed
- Notes: None.

- Command/check: `cd backend; python -m mypy app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py`
- Required: yes
- Reported result: passed
- Rerun result: Success, no issues found in 3 source files
- Status: passed
- Notes: None.

- Command/check: targeted Python validation of precise skill and total-experience years with the prior non-timeline evidence examples
- Required: yes - directly probes the task's precise-years acceptance rule
- Reported result: both examples rejected by repaired tests
- Rerun result: `skill_non_timeline_rejected=True`; `profile_non_timeline_rejected=True`
- Status: passed
- Notes: `Python listed in skills` and `Worked as engineer` no longer authorize precise years.

- Command/check: `git diff --check`
- Required: no
- Reported result: not reported
- Rerun result: passed (line-ending warning only)
- Status: passed
- Notes: No whitespace errors.

## Acceptance Review
- Task acceptance: The exact named fields/enums, confidence bounds, nested display-fact boundary, profile/preference separation, draft omission semantics, and precise-years timeline-evidence rule are implemented and validated.
- Status: satisfied
- Evidence: The repaired validators detect explicit calendar/duration cues, reject both prior non-timeline examples, preserve `null` for unknown years, and pass all 70 focused schema tests plus Ruff and mypy.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- `backend/app/schemas/candidate.py` is 465 lines, above the repository's preferred 300-line focus guideline; this is non-blocking for the accepted contract task.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

---

---

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: Prior A2 rejection, repaired timeline detection, new negative/positive tests, all required validations, git evidence, and Task 01A checkbox integrity.
- repairs verified: Arbitrary nonempty evidence no longer authorizes precise skill or total-experience years; explicit date-range/duration evidence remains accepted; unknown years remain representable as `null`.
- remaining issues: None blocking or major.
- updated outcome: ACCEPTED (prior outcome: REJECTED).

---

# Task Review Report - 02A

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
same_task_repair

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch02 - Safe PDF Intake to Profile Draft
- Task ID: 02A
- Task title: Implement the fail-closed PDF text and deterministic PII boundary
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: the six reported service/export/test/fixture paths and the execution report were classified as in scope.

## Files Reviewed
- `backend/app/services/pdf_text.py`: in scope - layout-only pypdf extraction, page ceiling, usable-character gate, and stable errors.
- `backend/app/services/pii_redaction.py`: in scope - deterministic email/address handling and conservative 10-15 digit contiguous phone recognition are implemented.
- `backend/app/services/__init__.py`: in scope - exports the internal boundary.
- `backend/tests/services/test_pdf_text.py`: in scope - extraction/page/no-text/error coverage.
- `backend/tests/services/test_pii_redaction.py`: in scope - includes formatted and contiguous phone regression cases plus false-positive boundaries.
- `backend/tests/fixtures/cv_pdfs/__init__.py`: in scope test fixture package marker.

## Validations Reviewed
- Command/check: required focused pytest, Ruff, and mypy commands
- Required: yes
- Reported result: 26 passed; Ruff passed; mypy passed
- Rerun result: 26 passed in 1.24s; Ruff passed; mypy passed
- Status: passed
- Notes: extraction, redaction, formatted/contiguous phone, privacy, and failure gates passed.

- Command/check: targeted `redact_pii` probe for `5551234567`, `0901234567`, `02079460958`, `447911123456`, plus documented short-number false positives
- Required: yes - verifies the prior rejected acceptance boundary
- Reported result: passed
- Rerun result: all phone sentinels removed; years, room numbers, and short level values retained
- Status: passed
- Notes: the repair addresses the root cause without broad numeric redaction.

## Acceptance Review
- Task acceptance: the PDF extraction and deterministic PII boundary now satisfies the task, including the previously missing contiguous local-phone forms.
- Status: satisfied
- Evidence: all required reruns and the targeted prior-failure probe passed; provider-blocking and sanitized error coverage remain green.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

---

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: Prior 02A rejection, repaired phone recognition, new contiguous-number regression, required validations, targeted prior-failure probes, git evidence, and 02A checkbox integrity.
- repairs verified: Common contiguous local/international-without-plus phone numbers are removed while years, room numbers, short numeric codes, and technology labels remain intact.
- remaining issues: None blocking or major.
- updated outcome: ACCEPTED (prior outcome: REJECTED_WITH_WARNINGS).

---


---

# Task Review Report - 01B

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
orchestrated

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch01 - Validated Candidate Contracts and Persistence
- Task ID: 01B
- Task title: Establish deterministic skill normalization and an approval-only seed
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: `backend/app/services/__init__.py` and `backend/pyproject.toml` are tracked modifications; the four new implementation/test/seed paths are untracked and were cross-checked directly. Existing accepted 01A files and orchestration artifacts were identified separately in the shared working tree.

## Files Reviewed
- `backend/app/services/skill_normalization.py`: in scope - implements seed loading, alias resolution, provisional keys, exclusions, deterministic deduplication, and ordering; repaired common Unicode separators now collapse consistently while `+` and `#` remain meaningful.
- `backend/app/data/skills_seed.yaml`: in scope - valid empty approval-only production seed.
- `backend/app/services/__init__.py`: in scope - exports the shared normalization seam.
- `backend/pyproject.toml`: in scope - exact PyYAML/runtime stub pins and YAML package data are present.
- `backend/tests/services/test_skill_normalization.py`: in scope - now covers 29 cases, including ASCII hyphen/en dash/em dash/middle-dot equivalence and `+`/`#` preservation.
- `backend/tests/fixtures/skills_seed_test.yaml`: in scope - synthetic aliases are isolated to tests.
- `backend/app/schemas/candidate.py`: dependency evidence - accepted 01A `SkillRef` and `CandidateSkill` contracts are reused.
- `docs/plans/Plan_4.md` and `docs/plans/Master_plan.md`: source requirements reviewed.

## Validations Reviewed
- Command/check: `cd backend; python -m pytest -q tests/services/test_skill_normalization.py`
- Required: yes
- Reported result: 29 passed in 0.99s
- Rerun result: 29 passed in 0.91s
- Status: passed
- Notes: The repaired regression cases pass with the full focused suite.

- Command/check: `cd backend; python -m ruff check app/services/skill_normalization.py tests/services/test_skill_normalization.py`
- Required: yes
- Reported result: All checks passed
- Rerun result: All checks passed
- Status: passed
- Notes: None.

- Command/check: `cd backend; python -m mypy app/services/skill_normalization.py`
- Required: yes
- Reported result: Success, no issues found in 1 source file
- Rerun result: Success, no issues found in 1 source file
- Status: passed
- Notes: None.

- Command/check: targeted comparison/canonical-key probe for ASCII hyphen versus Unicode en dash/em dash and middle dot
- Required: yes - directly probes source-required punctuation normalization and deterministic semantic keys
- Reported result: passed; all listed variants map to `ci cd` / `ci_cd` and meaningful `+`/`#` labels remain intact
- Rerun result: passed; `CI-CD`, `CI\u2013CD`, `CI\u2014CD`, and `CI\u00b7CD` all map to `ci cd` / `ci_cd`; `C++` and `C#` preserve their symbols in both forms.
- Status: passed
- Notes: The prior Unicode punctuation gap is closed without broadening verification trust.

- Command/check: `git diff --check`
- Required: no
- Reported result: not reported
- Rerun result: passed (line-ending warnings only)
- Status: passed
- Notes: No whitespace errors.

## Acceptance Review
- Task acceptance: Alias verification, provisional status, empty production seed, stable output ordering, evidence/source preservation, exclusions, and common Unicode punctuation normalization are implemented and validated.
- Status: satisfied
- Evidence: All 29 focused tests, Ruff, mypy, and the independent separator/symbol probe pass; semantic separator variants produce identical deterministic keys and only seed aliases become verified.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- `backend/app/services/skill_normalization.py` is 506 lines, above the repository's preferred 300-line focus guideline; this is non-blocking because it remains one bounded normalization/seed seam.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: Prior 01B rejection, repaired separator regex, new regression tests, all required validations, independent Unicode-separator and `+`/`#` probes, git evidence, and checkbox integrity.
- repairs verified: ASCII hyphen, en dash, em dash, and middle dot now produce identical comparison and provisional canonical keys; C++ and C# labels preserve their meaningful symbols.
- remaining issues: None blocking or major; the previously noted 506-line focus guideline remains non-blocking.
- updated outcome: ACCEPTED (prior outcome: REJECTED_WITH_WARNINGS).

---

# Task Review Report - 01C

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
same_task_repair

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch01 - Validated Candidate Contracts and Persistence
- Task ID: 01C
- Task title: Implement validated profile, preference, draft, and compact-context repositories
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: all ten A1-reported repository, service, export, and test paths were inspected; untracked files were read directly because ordinary `git diff` omits them.

## Files Reviewed
- `backend/app/repositories/profiles.py`: in scope - validates singleton opaque JSON on read/write and uses caller-owned transactions.
- `backend/app/repositories/preferences.py`: in scope - validates singleton preferences and preserves omission by requiring an explicit replace call.
- `backend/app/repositories/profile_drafts.py`: in scope - validates pending drafts and supports same-row correction, state checks, discard, and delete.
- `backend/app/repositories/__init__.py`: in scope - exports the new repository boundary.
- `backend/app/services/profile_context.py`: in scope - creates a bounded, fixed-field approved display projection without evidence, raw document bodies, contact fields, paths, or provider payloads.
- `backend/app/services/chat_context.py`: in scope - replaces direct profile/preference ORM parsing with the shared validated projection.
- `backend/tests/repositories/test_profiles.py`: in scope - singleton, invalid JSON/write, retention, and rollback coverage.
- `backend/tests/repositories/test_preferences.py`: in scope - singleton, omission, invalid JSON/write, and delete coverage.
- `backend/tests/repositories/test_profile_drafts.py`: in scope - create/load/correct/state/privacy/rollback coverage.
- `backend/tests/services/test_context_assembly.py`: in scope - shared projection, bounds, invalid storage, and privacy coverage.

## Validations Reviewed
- Command/check: `cd backend; python -m pytest -q tests/repositories/test_profiles.py tests/repositories/test_preferences.py tests/repositories/test_profile_drafts.py tests/services/test_context_assembly.py`
- Required: yes
- Reported result: 33 passed in 4.18s
- Rerun result: 33 passed in 4.05s
- Status: passed
- Notes: repository, rollback, same-draft, and compact-context cases passed.

- Command/check: `cd backend; python -m ruff check app/repositories app/services/profile_context.py app/services/chat_context.py tests/repositories tests/services/test_context_assembly.py`
- Required: yes
- Reported result: passed
- Rerun result: All checks passed
- Status: passed
- Notes: None.

- Command/check: `cd backend; python -m mypy app/repositories app/services/profile_context.py app/services/chat_context.py`
- Required: yes
- Reported result: passed
- Rerun result: Success, no issues found in 11 source files
- Status: passed
- Notes: None.

## Acceptance Review
- Task acceptance: validated singleton/profile/preference and pending-draft persistence boundaries are real, caller-transaction-owned, and reused by chat through one compact projection.
- Status: satisfied
- Evidence: direct code inspection, caller search, and all required reruns passed; approved state remains separate from pending draft writes.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.
# Task Review Report - 02B

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Mode
same_task_repair

## Batch
Mandatory Batch02 - Safe PDF Intake to Profile Draft

## Task
02B - Expose one streaming, deduplicating staged-CV upload boundary

## Review Outcome
ACCEPTED

## Evidence Reviewed
- Read root `README.md`, the complete 02B task entry, the matching A1 execution report block, and cited upload/API source sections in `Plan_4.md` and `Master_plan.md`.
- Inspected `git status --short`, `git diff --stat`, `git diff`, every A1-reported file, the accepted attachment repository/storage boundaries, and all relevant callers/search results.
- A1 status is `complete`; the selected report identity and reported changed-file scope match 02B.

## Changed Files Review
- `backend/pyproject.toml`: in scope; adds the exact `python-multipart==0.0.30` runtime dependency.
- `backend/app/api/attachments.py`: in scope; exposes the single multipart CV upload route with sanitized errors and response schema.
- `backend/app/main.py`: in scope; registers only the attachment router.
- `backend/app/schemas/attachments.py`: in scope; exposes only the six permitted metadata fields.
- `backend/app/services/cv_ingestion.py`: in scope; reuses chunked storage, canonical paths, hash lookup, repository writes, and cleanup operations.
- `backend/tests/api/test_attachments.py`: in scope; covers the public success response and one stable MIME error.
- `backend/tests/api/test_health.py`: in scope; updates the authorized route inventory.
- `backend/tests/services/test_cv_ingestion.py`: in scope; now covers the complete prior A2 repair matrix.

## Validations Reviewed
- Command/check: `python -m pytest -q tests/services/test_cv_ingestion.py tests/api/test_attachments.py tests/repositories/test_attachments.py tests/services/test_attachment_storage.py`
- Required: yes
- Reported result: 80 passed, 1 skipped
- Rerun result: 86 passed, 1 skipped in 4.90s
- Status: passed
- Notes: existing focused and regression tests pass.

- Command/check: `python -m ruff check app/api/attachments.py app/services/cv_ingestion.py app/repositories/attachments.py tests/api/test_attachments.py tests/services/test_cv_ingestion.py`
- Required: yes
- Reported result: passed
- Rerun result: All checks passed
- Status: passed

- Command/check: `python -m mypy app/api/attachments.py app/services/cv_ingestion.py`
- Required: yes
- Reported result: passed
- Rerun result: Success, no issues found in 2 source files
- Status: passed

- Command/check: `python -m pytest -q tests/api/test_health.py`
- Required: no
- Reported result: 11 passed
- Rerun result: 11 passed in 1.41s
- Status: passed

- Command/check: independent four-way concurrent identical-upload probe
- Required: supports the racing-duplicate acceptance condition
- Reported result: not separately reported as a probe
- Rerun result: all four calls returned one attachment ID; one staged file and one metadata row remained
- Status: passed

## Acceptance Review
- The production boundary is real, scoped, streamed to a configured 10 MiB ceiling, contained, deduplicating, and sanitized; no provider/profile/approval/active-replacement work was introduced.
- The repaired tests now cover malformed PDF parsing, valid image-only page counting, four-way concurrent identical-upload races, cancellation during streaming, partial-stream failure cleanup, and the sanitized malformed-PDF API response.
- Status: satisfied; every prior A2 repair instruction is covered by executable regression evidence and fresh required validations.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: The five prior missing regression scenarios, sanitized malformed-PDF API behavior, exact required 02B pytest/Ruff/mypy commands, health tests, git evidence, and 02B checkbox integrity.
- repairs verified: Malformed and failed/cancelled streams leave zero rows and staged/partial files; valid image-only PDFs retain page count; four concurrent identical uploads resolve to one ID, one row, and one contained staged object; malformed API responses expose only the stable code.
- remaining issues: None blocking, major, or minor.
- updated outcome: ACCEPTED (prior outcome: REJECTED_WITH_WARNINGS).

---

# Task Review Report - 02C

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
orchestrated

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch02 - Safe PDF Intake to Profile Draft
- Task ID: 02C
- Task title: Produce a normalized pending profile draft with one repair ceiling
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: the 02C service, extraction boundary, service export, focused tests, and fake fixture were inspected; concurrent 02A/02B batch files were not reviewed as 02C implementation.

## Files Reviewed
- `backend/app/services/cv_ingestion.py`: in scope - keeps the authoritative attachment validation, layout extraction, deterministic redaction, one adapter call, and transactional pending-draft insert in one service method.
- `backend/app/services/profile_extraction.py`: in scope - grounds nested CV facts in redacted evidence, rejects provider contact PII, normalizes skills, and builds the bounded preference-omitting draft.
- `backend/app/services/__init__.py`: in scope - exports the new internal service boundaries only.
- `backend/tests/services/test_profile_extraction.py`: in scope - covers success, one schema repair, provider/invalid/evidence failures, timeline evidence, exclusions, active inputs, preference omission, and contact-sentinel privacy checks.
- `backend/tests/fakes/profile_extraction.py`: in scope - fake strict-schema provider records requests without network access.
- `backend/app/services/shopaikey_chat.py`: inspected dependency, unchanged - its locked strict structured mode owns the sole schema-repair ceiling.

## Validations Reviewed
- Command/check: `python -m pytest -q tests/services/test_profile_extraction.py tests/services/test_cv_ingestion.py tests/repositories/test_profile_drafts.py tests/services/test_shopaikey_chat.py`
- Required: yes
- Reported result: 55 passed
- Rerun result: 55 passed in 4.04s
- Status: passed
- Notes: focused extraction, privacy, repair, normalization, draft, and adapter tests passed.

- Command/check: `python -m ruff check app/services/cv_ingestion.py app/services/profile_extraction.py app/services/shopaikey_chat.py tests/services/test_profile_extraction.py tests/services/test_cv_ingestion.py`
- Required: yes
- Reported result: passed
- Rerun result: All checks passed
- Status: passed
- Notes: focused lint passed.

- Command/check: `python -m mypy app/services/cv_ingestion.py app/services/profile_extraction.py app/services/shopaikey_chat.py`
- Required: yes
- Reported result: passed
- Rerun result: Success: no issues found in 3 source files
- Status: passed
- Notes: focused type check passed.

## Acceptance Review
- Task acceptance: satisfied
- Status: satisfied
- Evidence: only redacted text enters the sole `invoke_structured(CandidateProfile, ...)` call; extraction/redaction failure paths run before that call. The reused adapter enforces strict Pydantic output and exactly one schema repair. The post-provider boundary verifies evidence, rejects contact PII, applies shared skill normalization, omits preferences, and persists only a pending draft after attachment revalidation. No approved-profile, preference, or attachment-state writer is called.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

---

# Task Review Report - batch_scope

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
batch_scope_repair

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync
- Task ID: batch_scope
- Task title: Remove historical report edits from the Batch03 candidate
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from the repair: `docs/reports/report_4_execute_agent.md` only; the wider dirty tree is the accepted Batch03 candidate.

## Files Reviewed
- `docs/reports/report_4_execute_agent.md`: in scope - the four A3-identified historical 01C byte substitutions no longer appear in the diff; accepted 03A/03B and current batch-scope evidence remain.
- `docs/tasks/task_4.md`: inspected only - 03A and 03B remain checked.

## Validations Reviewed
- Command/check: targeted historical report byte comparison, Batch03 checkbox inspection, and `git diff --check`
- Required: yes
- Reported result: passed
- Rerun result: the first execution-report diff hunk is now the current batch-scope block; 03A/03B are checked; no whitespace errors
- Status: passed

## Acceptance Review
- Task acceptance: satisfied
- Status: satisfied
- Evidence: The repair is limited to A3's four historical execution-report byte findings; it modifies no implementation, tests, configuration, task tracking, or accepted Batch03 behavior.

## Progress Tracking
- Selected task checkbox before review: n/a
- Checkbox updated by reviewer: no
- Checkbox final state: n/a
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: no
- Batch can be marked complete by A2: no
- A3 can rerun: yes
- Next action: rerun_a3

## Repair Instructions
- None.

## Re-Review / Repair Verification Log

### 2026-07-12 (Batch03 scope repair)
- what was re-checked: the exact four historical byte positions, current execution-report diff boundaries, Batch03 checkbox state, and `git diff --check`.
- repairs verified: no pre-Batch03 historical substitution remains dirty; 03A/03B and the current batch-scope evidence remain intact.
- remaining issues: None blocking or major.
- updated outcome: ACCEPTED; A3 may rerun.

---

# Task Review Report - 03A

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
orchestrated

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync
- Task ID: 03A
- Task title: Implement coalescing Candidate outbox work and idempotent graph projection
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: `backend/app/graph/__init__.py`, `backend/app/main.py`, `backend/app/repositories/graph_outbox.py`, `backend/app/repositories/profiles.py`, `backend/app/graph/candidate_sync.py`, `infrastructure/scripts/rebuild_graph.py`, `backend/tests/repositories/test_graph_outbox.py`, `backend/tests/graph/test_candidate_sync.py`, `backend/tests/integration/test_candidate_sync.py`, `backend/tests/infrastructure/test_rebuild_graph.py`, `backend/tests/test_lifecycle.py`, and `docs/reports/report_4_execute_agent.md`.

## Files Reviewed
- `backend/app/repositories/graph_outbox.py`: in scope - opt-in coalescing preserves unrelated replay behavior, validates replacement payloads, preserves attempts, and adds bounded operation filtering/requeue.
- `backend/app/repositories/profiles.py`: in scope - every singleton replacement enqueues identifier-only Candidate work in the caller-owned transaction.
- `backend/app/graph/candidate_sync.py`: in scope - current approved state is reloaded from SQLite; one parameter-bound MERGE projection replaces active skill edges and records sanitized retry state.
- `backend/app/graph/__init__.py`: in scope - exports the focused Candidate synchronization seam.
- `backend/app/main.py`: in scope - performs one bounded best-effort startup retry.
- `infrastructure/scripts/rebuild_graph.py`: in scope - rebuilds the Candidate slice after clear/schema and leaves later graph stages explicitly incomplete.
- `backend/tests/repositories/test_graph_outbox.py`: in scope - covers pending coalescing and terminal identity requeue without duplicate rows.
- `backend/tests/graph/test_candidate_sync.py`: in scope - covers projection parameters, exclusions, privacy-safe payload, outage replay, slash-bearing skill text, and rebuild replay.
- `backend/tests/integration/test_candidate_sync.py`: in scope - covers successive approvals, exact current relationships, idempotency, rollback, and outage recovery.
- `backend/tests/infrastructure/test_rebuild_graph.py`: in scope - verifies the Candidate rebuild stage before deferred stages.
- `backend/tests/test_lifecycle.py`: in scope - verifies one bounded startup retry; the route-count assertion reflects the already accepted attachment route.
- `docs/reports/report_4_execute_agent.md`: in scope - matching 03A evidence block is materially accurate.

## Validations Reviewed
- Command/check: `cd backend; python -m pytest -q tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py tests/infrastructure/test_rebuild_graph.py tests/test_lifecycle.py`
- Required: yes
- Reported result: 57 passed
- Rerun result: 57 passed in 7.03s
- Status: passed
- Notes: fake-backed; no provider or live Neo4j access.

- Command/check: `cd backend; python -m ruff check app/repositories/graph_outbox.py app/graph/candidate_sync.py tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py`
- Required: yes
- Reported result: passed
- Rerun result: All checks passed
- Status: passed

- Command/check: `cd backend; python -m mypy app/repositories/graph_outbox.py app/graph/candidate_sync.py`
- Required: yes
- Reported result: passed
- Rerun result: Success; no issues found in 2 source files
- Status: passed

- Command/check: `cd backend; python -m pytest -q tests/repositories/test_profiles.py`
- Required: no
- Reported result: 7 passed
- Rerun result: 7 passed in 2.03s
- Status: passed
- Notes: confirms the root profile repository behavior remains compatible.

- Command/check: `git diff --check`
- Required: no
- Reported result: passed
- Rerun result: exit 0 with line-ending conversion warnings only
- Status: passed

## Acceptance Review
- Task acceptance: satisfied
- Status: satisfied
- Evidence: Successive approved singleton changes coalesce into one processable durable identity; the projector uses the singleton ID and canonical skill keys, removes stale active edges, excludes corrected skills, retains alias/provisional properties, and never emits trusted `RELATED_TO` edges. Graph failure commits sanitized retry evidence without changing canonical profile data. Startup and rebuild integration are bounded. The immediate post-commit processing seam is available for the dependent 03B commit service, which does not yet exist in production.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

---

# Task Review Report - 03B

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
same_task_repair

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync
- Task ID: 03B
- Task title: Atomically commit a draft with filesystem compensation and cleanup retry
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: the six A1-reported 03B implementation/test files and matching execution-report block were inspected separately from the accepted pre-existing 03A changes.

## Files Reviewed
- `backend/app/services/profile_service.py`: in scope - owns promotion, one SQLite transaction, compensation, and bounded cleanup; its repaired `BaseException` boundary compensates promoted bytes before re-raising cancellation unchanged.
- `backend/app/services/attachment_storage.py`: in scope - adds contained active-to-staged restore by reusing the existing cross-area publication primitive.
- `backend/app/repositories/attachments.py`: in scope - adds bounded active rows that exclude current profile and draft references.
- `backend/tests/services/test_profile_service.py`: in scope - covers ordinary mutation/commit/restore/cleanup failures and the repaired cancellation-after-promotion path.
- `backend/tests/integration/test_profile_replacement.py`: in scope - proves direct promote/restore only.
- `backend/tests/repositories/test_attachments.py`: in scope - proves referenced attachments are excluded from cleanup selection.
- `docs/reports/report_4_execute_agent.md`: in scope - the 03B block was updated in place with the repair, red/green regression evidence, and current required validation results.

## Validations Reviewed
- Command/check: `cd backend; python -m pytest -q tests/services/test_profile_service.py tests/integration/test_profile_replacement.py tests/repositories/test_attachments.py tests/repositories/test_graph_outbox.py`
- Required: yes
- Reported result: 59 passed in 6.51s
- Rerun result: 59 passed in 6.29s
- Status: passed
- Notes: the required suite now includes cancellation after filesystem promotion.

- Command/check: `cd backend; python -m ruff check app/services/profile_service.py app/services/attachment_storage.py app/repositories tests/services/test_profile_service.py tests/integration/test_profile_replacement.py`
- Required: yes
- Reported result: passed
- Rerun result: All checks passed
- Status: passed

- Command/check: `cd backend; python -m mypy app/services/profile_service.py app/services/attachment_storage.py app/repositories`
- Required: yes
- Reported result: passed
- Rerun result: Success; no issues found in 11 source files
- Status: passed

- Command/check: independent cancellation-after-promotion probe by injecting `asyncio.CancelledError` at `ProfileRepository.replace`
- Required: supports the every-pre-commit-failure acceptance condition
- Reported result: passed after first reproducing the prior unreadable staged path
- Rerun result: passed - cancellation was re-raised while metadata remained staged, the draft remained pending, and the canonical staged bytes were readable
- Status: passed
- Notes: the outer `BaseException` cleanup boundary now compensates before preserving non-`Exception` semantics.

- Command/check: `git diff --check`
- Required: no
- Reported result: passed
- Rerun result: passed with line-ending conversion warnings only
- Status: passed

## Acceptance Review
- Task acceptance: every pre-commit failure must preserve the prior approved singleton/file and a recoverable pending draft/source.
- Status: satisfied
- Evidence: the exact prior cancellation probe is now an automated passing regression; all 59 required tests plus Ruff and mypy pass, and no blocking or major issue remains.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: the prior cancellation finding, repaired production boundary, new regression, exact required pytest/Ruff/mypy commands, git evidence, report accuracy, and 03B checkbox integrity.
- repairs verified: post-promotion cancellation now restores readable staged bytes before propagating cancellation; the pending draft and canonical metadata remain consistent.
- remaining issues: None blocking, major, or minor.
- updated outcome: ACCEPTED (prior outcome: REJECTED).


---

# Task Review Report - 04A

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
same_task_repair

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch04 - Production Tools and Approval Workflow
- Task ID: 04A
- Task title: Register compact-context and draft-proposal tools through one service seam
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git: all A1-reported tool, registry, graph/service wiring, compatibility-test, focused-test, and execution-report paths were inspected, including untracked files.

## Files Reviewed
- `backend/app/tools/candidate_context.py`: in scope - strict read-only compact-context wrapper with stable unavailable/invalid outcomes.
- `backend/app/tools/profile_draft.py`: in scope - application-state-authorized CV/update proposals, same-draft retention, bounded marker, and no approved writes.
- `backend/app/tools/registry.py`, `backend/app/tools/__init__.py`: in scope - exact three-tool production factory and exports.
- `backend/app/main.py`, `backend/app/services/chat_service.py`, `backend/app/agent/graph.py`: in scope - inject the production registry through the existing one-graph seam.
- `backend/tests/tools/profile_tool_helpers.py`, `backend/tests/tools/test_candidate_context.py`, `backend/tests/tools/test_profile_draft.py`, `backend/tests/tools/test_registry.py`: in scope - focused authorization/privacy/strictness coverage.
- `backend/tests/agent/test_graph.py`: in scope - explicit empty registry remains available for synthetic graph tests.
- `backend/tests/integration/test_full_chat_transport.py`: in scope - repaired exposure scan permits exactly the current Candidate tools while retaining synthetic/04B/future-tool prohibitions.
- `docs/reports/report_4_execute_agent.md`: in scope - matching 04A block and repair log accurately report current validation evidence.

## Validations Reviewed
- Command/check: `cd backend; python -m pytest -q tests/tools/test_candidate_context.py tests/tools/test_profile_draft.py tests/tools/test_registry.py tests/services/test_context_assembly.py`
- Required: yes
- Reported result: 29 passed
- Rerun result: 29 passed
- Status: passed
- Notes: tool contracts, authorization, registry, and privacy coverage pass.

- Command/check: exact required Ruff and mypy commands
- Required: yes
- Reported result: passed
- Rerun result: passed
- Status: passed
- Notes: no focused lint or type errors.

- Command/check: `cd backend; python -m pytest -q tests/integration/test_full_chat_transport.py`
- Required: no, but the file is modified by 04A and contains the production exposure regression
- Reported result: targeted repaired exposure regression passed (1 passed, 7 deselected)
- Rerun result: targeted repaired exposure regression passed (1 passed, 7 deselected)
- Status: passed
- Notes: the separate route-inventory failure predates 04A and omits the accepted attachment route.

## Acceptance Review
- Task acceptance: the three real production tools are strict, state-authorized, privacy-bounded, dependency-injected through the existing graph seam, and fully covered by current required and compatibility evidence.
- Status: satisfied
- Evidence: 29 required tests, focused Ruff/mypy, and the repaired production exposure regression all pass.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- A separate pre-existing route inventory assertion in chat/full-transport tests omits `/api/attachments/cv`; this is not attributed to 04A.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: prior exposure-regression finding, exact required pytest/Ruff/mypy gates, repaired regex/name/comment, report accuracy, and 04A checkbox integrity.
- repairs verified: current three Candidate tools are permitted; synthetic, guarded commit, and future Job/query/matching tool bodies remain forbidden.
- remaining issues: no blocking or major issue; the unrelated stale route-inventory assertion remains a minor pre-existing observation.
- updated outcome: ACCEPTED (prior outcome: REJECTED_WITH_WARNINGS).

---

# Task Review Report - 04B

## Source Task File
docs/tasks/task_4.md

## Execution Report Reviewed
docs/reports/report_4_execute_agent.md

## Review Report File
docs/review/review_4_review_agent.md

## Mode
same_task_repair

## Final Outcome
ACCEPTED

## Reviewed Scope
- Batch: Mandatory Batch04 - Production Tools and Approval Workflow
- Task ID: 04B
- Task title: Guard commit and same-draft corrections with typed same-run approval
- Executor status reported: complete
- Repair scope: verify run/draft/key replay identity and removal of backend/tmp_forge_test only.

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from the repair: backend/app/tools/profile_commit.py, backend/tests/tools/test_profile_commit.py, and the matching execution-report update; backend/tmp_forge_test was removed.
- accepted uncommitted 04A and prior correct 04B changes were inspected as dependency evidence but not re-reviewed as new repair scope.

## Files Reviewed
- backend/app/tools/profile_commit.py: in scope - the in-process replay identity is now the authorized run, draft, and key tuple; bare client keys cannot collide across runs.
- backend/tests/tools/test_profile_commit.py: in scope - adds a real persistence-backed regression that commits two distinct authorized drafts using the same client key on different runs and keeps same-run/draft replay idempotent.
- backend/tmp_forge_test/: removed - absent from filesystem and full untracked git status.
- docs/reports/report_4_execute_agent.md: in scope - latest 04B same-task-repair block accurately reports the two repairs and validation results.

## Validations Reviewed
- Command/check: cd backend; python -m pytest -q tests/tools/test_profile_commit.py tests/agent/test_profile_approval.py tests/integration/test_profile_approval.py tests/api/test_chat.py tests/schemas/test_sse.py
- Required: yes
- Reported result: 74 passed in 7.42s
- Rerun result: 74 passed in 8.34s
- Status: passed
- Notes: Includes the new cross-run same-client-key regression.

- Command/check: exact required focused Ruff command
- Required: yes
- Reported result: passed
- Rerun result: All checks passed
- Status: passed
- Notes: None.

- Command/check: exact required focused mypy command
- Required: yes
- Reported result: passed
- Rerun result: Success; no issues found in 10 source files
- Status: passed
- Notes: None.

- Command/check: python -m pytest -q tests/tools/test_profile_commit.py -k same_client_key_commits_distinct_runs_and_stays_idempotent_per_run
- Required: yes - directly verifies the prior major finding
- Reported result: included in required group
- Rerun result: 1 passed, 4 deselected
- Status: passed
- Notes: Both distinct authorized drafts commit; replay of the original run/draft remains idempotent.

- Command/check: full git status and filesystem check for backend/tmp_forge_test/
- Required: yes - directly verifies the prior scope finding
- Reported result: absent
- Rerun result: absent
- Status: passed
- Notes: No scratch database or active-file artifact remains.

- Command/check: git diff --check
- Required: no
- Reported result: not reported
- Rerun result: passed with line-ending warnings only
- Status: passed
- Notes: No whitespace errors.

## Acceptance Review
- Task acceptance: both A2 repair instructions are fully satisfied and the original 04B authorization, same-run correction, replay, and eight-event SSE gates remain green.
- Status: satisfied
- Evidence: implementation/caller inspection, the persistence-backed collision regression, all 74 required tests, Ruff, mypy, and clean scratch-path evidence pass without blocking or major findings.

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None.

### Major
- None.

### Minor
- None.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None.

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: prior A2 rejection, scoped replay identity, cross-run same-key regression, exact required pytest/Ruff/mypy gates, full untracked status, scratch-path absence, execution-report accuracy, and 04B checkbox integrity.
- repairs verified: a valid key reused on a different authorized run/draft no longer suppresses the later commit; same run/draft replay remains idempotent; backend/tmp_forge_test is absent.
- remaining issues: None blocking, major, or minor.
- updated outcome: ACCEPTED (prior outcome: REJECTED).
