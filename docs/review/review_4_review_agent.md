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

## Re-Review / Repair Verification Log

### 2026-07-12
- what was re-checked: Prior A2 rejection, repaired timeline detection, new negative/positive tests, all required validations, git evidence, and Task 01A checkbox integrity.
- repairs verified: Arbitrary nonempty evidence no longer authorizes precise skill or total-experience years; explicit date-range/duration evidence remains accepted; unknown years remain representable as `null`.
- remaining issues: None blocking or major.
- updated outcome: ACCEPTED (prior outcome: REJECTED).

---

# Task Review Report - 01B

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
orchestrated

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
