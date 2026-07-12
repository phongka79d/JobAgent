---

# Task Execution Report - 01A

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
same_task_repair

## Batch
Mandatory Batch01 - Validated Candidate Contracts and Persistence

## Task
01A - Define strict Candidate, preference, and profile-draft contracts

## Status
complete

## Selected Scope
- Batch: Mandatory Batch01 - Validated Candidate Contracts and Persistence
- Task ID: 01A
- Task title: Define strict Candidate, preference, and profile-draft contracts
- Files allowed / repair scope: A2 same-task repair — `backend/app/schemas/candidate.py` (timeline evidence gate), `backend/tests/schemas/test_candidate.py` (rejection/acceptance cases). Original task files remain in scope for validation only.

## Source of Truth Used
- docs/plans/Plan_4.md > ### 7.2 Candidate and preference contracts
- docs/plans/Master_plan.md > ### 7.1 Shared skill contract
- docs/plans/Master_plan.md > ### 7.2 Candidate Profile
- docs/plans/Master_plan.md > ### 7.3 Job Preferences
- docs/review/review_4_review_agent.md (A2 REJECTED repair instructions for 01A)

## Supplemental Documents Used
- docs/plans/Plan_4.md
- docs/plans/Master_plan.md
- docs/tasks/task_4.md (01A block)

## Dependency and User Action Check
- Dependencies: Accepted `backend/app/db/models/profile.py` JSON storage boundary present (opaque profile_json / draft_json / preferences_json)
- User Action: None required
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_4.md
- docs/plans/Plan_4.md (§7.2)
- docs/plans/Master_plan.md (§7.1–7.3)
- docs/review/review_4_review_agent.md (A2 01A rejection)
- backend/app/db/models/profile.py
- backend/app/schemas/candidate.py
- backend/app/schemas/preferences.py
- backend/app/schemas/profile_draft.py
- backend/app/schemas/__init__.py
- backend/tests/schemas/test_candidate.py
- backend/tests/schemas/test_preferences.py
- backend/tests/schemas/test_profile_draft.py
- backend/app/schemas/chat.py
- backend/app/schemas/sse.py
- backend/app/schemas/health.py
- backend/app/services/chat_context.py
- backend/tests/services/test_context_assembly.py
- backend/scripts/check_shopaikey_compatibility.py (structured-schema extra=forbid pattern)
- backend/tests/schemas/test_sse.py

## Completed Work
- Documented source gap: Master/Plan 4 enumerate SkillRef, CandidateSkill, CandidateProfile, JobPreferences fields exactly; ExperienceItem / EducationItem / LanguageItem are not field-enumerated. Implemented the smallest display-fact + short evidence inventory only.
- Implemented `SkillRef`, `CandidateSkill`, `CandidateProfile` with exact enums (`verified|provisional`, `beginner|intermediate|advanced|unknown`, `cv|user_correction`), confidence in [0,1], finite non-negative years, and precise-years-require-timeline-evidence rules.
- Implemented nested `ExperienceItem`, `EducationItem`, `LanguageItem` with display facts + evidence only; `extra="forbid"` rejects preference/score/graph-trust/raw-document extras.
- Implemented separate `JobPreferences` with exact work-mode and seniority enums; profile documents reject preference fields and preference documents reject profile fields.
- Implemented `ProfileDraftDocument` + `ProfileApprovalSummary`: omit preferences key = unchanged; present validated preferences = explicit replacement; null preferences rejected; safe approval summary; `to_storage_dict` / `from_storage_dict` serialization.
- Exported new contracts from `backend/app/schemas/__init__.py`.
- Added schema tests for minimal/full documents, enums, bounds, non-finite/negative years, invented extras, nested display facts, preference separation, and omit-vs-replace draft serialization.
- **Same-task repair (A2 REJECTED):** Replaced nonempty-evidence checks with semantic timeline detection for precise `CandidateSkill.years` and `CandidateProfile.total_experience_years`. Added rejection tests for non-timeline evidence (`Python listed in skills`, `Worked as engineer`) and retained/added acceptance for date-range and duration timeline evidence.

## Files Created or Modified
- backend/app/schemas/candidate.py (created; repaired timeline evidence gate)
- backend/app/schemas/preferences.py (created)
- backend/app/schemas/profile_draft.py (created)
- backend/app/schemas/__init__.py (modified — exports)
- backend/tests/schemas/test_candidate.py (created; repaired with non-timeline rejection + timeline acceptance cases)
- backend/tests/schemas/test_preferences.py (created)
- backend/tests/schemas/test_profile_draft.py (created)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/schemas/test_candidate.py tests/schemas/test_preferences.py tests/schemas/test_profile_draft.py`
- required: yes
- result: passed
- evidence or reason: 70 passed in 0.95s (repair rerun; was 65 before repair)

- command/check: `cd backend; python -m ruff check app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py tests/schemas`
- required: yes
- result: passed
- evidence or reason: All checks passed!

- command/check: `cd backend; python -m mypy app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 3 source files

## Acceptance Check
- condition: All source-enumerated fields and values validate exactly, confidence stays in [0,1], and precise years without timeline evidence are rejected or represented as unknown.
- status: satisfied
- evidence: Enum/bound tests pass; skill years with empty or non-timeline evidence rejected; total_experience_years without experience date-range/timeline content rejected; years=null and explicit date-range/duration evidence allowed.

- condition: Nested items expose only explicit display facts and source evidence; they contain no address-derived preference, score, graph trust, raw document, or provider-control fields.
- status: satisfied
- evidence: Experience/Education/Language models limited to display + evidence; extra-key rejection tests pass.

- condition: Draft serialization distinguishes “preferences unchanged” from a validated preference replacement and rejects untyped provider extras.
- status: satisfied
- evidence: `to_storage_dict` omits preferences when unchanged and includes them on replacement; null preferences and provider extras rejected.

## Key Implementation Decisions
- Nested inventory: title/organization/date_range/summary/evidence (experience); institution/credential/field_of_study/date_range/evidence (education); language/proficiency-display/evidence (language). No invented scoring or preference fields.
- Draft preference semantics use Pydantic `model_fields_set` + storage helper that omits the key when unchanged (authoritative wire form for repositories).
- Shared string-list / evidence / finite-year helpers live on the candidate module; preferences and draft reuse them to avoid duplicated bounds logic.
- Timeline evidence is detected via calendar year tokens/ranges, month+year, or explicit duration phrases (`N years` / `N yrs`); arbitrary nonempty strings no longer authorize precise years.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: same_task_repair mode — A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files this repair: `backend/app/schemas/candidate.py`, `backend/tests/schemas/test_candidate.py` (plus report update)
- validations to rerun: the three required commands under Validation in task 01A
- risk areas: timeline regex is intentionally conservative (year/range/duration/month-year); draft omit-vs-replace still depends on `model_fields_set` / `to_storage_dict`
- next task readiness: ready for A2 re-review of 01A only

## Workflow Integrity Check
- single task ID executed: 01A
- mode: same_task_repair
- no sibling tasks implemented
- no commit or staging performed
- checkbox not updated (repair mode)

## Repair Log

### 2026-07-12 (same_task_repair after A2 REJECTED)
- reason for repair: A2 rejected 01A because precise skill and total-experience years accepted any nonempty evidence string instead of requiring actual timeline evidence.
- changes made:
  - `backend/app/schemas/candidate.py`: added `_text_has_timeline_evidence` / `_evidence_list_has_timeline`; `CandidateSkill` and `CandidateProfile` model validators now require year-range, calendar-year, month-year, or duration cues (experience `date_range` must itself contain timeline cues).
  - `backend/tests/schemas/test_candidate.py`: added rejection for non-timeline evidence (`Python listed in skills`, `Worked as engineer`); retained/added acceptance for date-range and duration timeline evidence.
- validations rerun:
  - `python -m pytest -q tests/schemas/test_candidate.py tests/schemas/test_preferences.py tests/schemas/test_profile_draft.py` → 70 passed
  - `python -m ruff check app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py tests/schemas` → All checks passed
  - `python -m mypy app/schemas/candidate.py app/schemas/preferences.py app/schemas/profile_draft.py` → Success: no issues found in 3 source files
- outcome: complete — A2 repair items addressed; required validations passed
---

# Task Execution Report - 01B

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
same_task_repair

## Batch
Mandatory Batch01 - Validated Candidate Contracts and Persistence

## Task
01B - Establish deterministic skill normalization and an approval-only seed

## Status
complete

## Selected Scope
- Batch: Mandatory Batch01 - Validated Candidate Contracts and Persistence
- Task ID: 01B
- Task title: Establish deterministic skill normalization and an approval-only seed
- Files allowed / repair scope: backend/app/services/skill_normalization.py, backend/tests/services/test_skill_normalization.py (A2 Unicode punctuation/separator normalization only; prior deliverables remain in place)

## Source of Truth Used
- docs/plans/Plan_4.md > ### 7.2 Candidate and preference contracts
- docs/plans/Plan_4.md > ### 7.3 Processing pipeline
- docs/plans/Master_plan.md > ## 9. Skill Normalization

## Supplemental Documents Used
- docs/plans/Plan_4.md
- docs/plans/Master_plan.md
- docs/tasks/task_4.md (01B block)
- docs/review/review_4_review_agent.md (A2 01B REJECTED_WITH_WARNINGS)

## Dependency and User Action Check
- Dependencies: (01A) SkillRef / CandidateSkill present in backend/app/schemas/candidate.py
- User Action: None; empty production seed is valid (no approved aliases yet)
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_4.md
- docs/plans/Plan_4.md
- docs/plans/Master_plan.md (§9)
- docs/review/review_4_review_agent.md (A2 01B findings)
- backend/app/services/skill_normalization.py
- backend/tests/services/test_skill_normalization.py
- backend/app/schemas/candidate.py
- backend/app/services/__init__.py
- backend/pyproject.toml
- backend/app/graph/schema.py (canonical_key uniqueness context only)
- repository search for normalizer / yaml / skills_seed (none present on first write)

## Completed Work
- Implemented pure focused skill normalizer: Unicode NFKC, whitespace collapse, casefold, separator/punctuation normalization, deterministic provisional keys, stable alias dedupe, and CandidateSkill list resolve/dedupe/order.
- Added checked-in empty production seed `backend/app/data/skills_seed.yaml` (approval-only; empty skills list is valid).
- Seed loader validates structure, rejects malformed YAML/types/duplicate alias conflicts, and rejects trusted relationship fields (`related_to` / relationships).
- Normalizer resolves only seed aliases as `verified`; unknowns are `provisional`; preserves proficiency/years/source/excluded/evidence; does not re-add excluded skills from CV input; creates no RELATED_TO edges.
- Pinned runtime `PyYAML==6.0.2` and test stub `types-PyYAML==6.0.12.20250915`; package-data includes `app/data/*.yaml`.
- Added synthetic test seed fixture and unit tests covering aliases, Unicode/separators, duplicates, provisional keys, stable ordering, exclusions, malformed seed, empty production seed, and determinism.
- Exported public seam from `app.services`.
- Repair: expanded `_SEPARATOR_RE` so common Unicode punctuation/separator variants (en dash, em dash, middle dot, soft hyphen, Unicode hyphen range, bullet, hyphenation point, minus sign) collapse like ASCII hyphen before comparison and provisional-key generation; preserved meaningful `+` and `#` labels.
- Repair: added regression tests for ASCII hyphen / en dash / em dash / middle-dot equivalence on match keys and provisional keys, plus `+`/`#` preservation.

## Files Created or Modified
- backend/app/services/skill_normalization.py (created; repaired separator set)
- backend/app/data/skills_seed.yaml (created)
- backend/app/services/__init__.py (modified — exports)
- backend/pyproject.toml (modified — PyYAML pin, package-data, types-PyYAML)
- backend/tests/services/test_skill_normalization.py (created; repaired Unicode dash/middle-dot coverage)
- backend/tests/fixtures/skills_seed_test.yaml (created)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_skill_normalization.py`
- required: yes
- result: passed
- evidence or reason: 29 passed in 0.99s (includes Unicode dash/middle-dot and +/# regression cases)

- command/check: `cd backend; python -m ruff check app/services/skill_normalization.py tests/services/test_skill_normalization.py`
- required: yes
- result: passed
- evidence or reason: All checks passed!

- command/check: `cd backend; python -m mypy app/services/skill_normalization.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 1 source file

## Acceptance Check
- condition: The same semantic input and seed always produce the same canonical key and ordering.
- status: satisfied
- evidence: Determinism test and stable sort-by-canonical_key; match-key/provisional-key tests for separators and Unicode, including ASCII hyphen vs en dash vs em dash vs middle dot all mapping to `ci cd` / `ci_cd` and `machine learning` / `machine_learning`.

- condition: No alias is verified unless the approved seed says so; unresolved skills are provisional and no trusted RELATED_TO relationship is created.
- status: satisfied
- evidence: Production empty seed marks all provisional; synthetic seed verifies only listed aliases; seed loader rejects related_to; model dumps have no related_to fields.

- condition: An excluded corrected skill is not recreated from the same extraction input.
- status: satisfied
- evidence: Exclusion tests drop CV re-adds for excluded keys and preserve a single user_correction exclusion row.

## Key Implementation Decisions
- Production seed intentionally empty (task allows empty when no aliases approved); tests use fixtures/skills_seed_test.yaml only.
- ASCII and common Unicode dash/separator punctuation collapse to whitespace; `+` and `#` retained for C++/C#-style labels.
- Existing canonical keys are reused when match forms align but remain provisional unless seed-verified.
- No fabricated production taxonomy or RELATED_TO graph trust.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: same_task_repair / orchestrated mode — A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files (this repair): skill_normalization.py, test_skill_normalization.py
- prior deliverables unchanged this repair: skills_seed.yaml, services/__init__.py, pyproject.toml, skills_seed_test.yaml
- validations to rerun: the two required commands under Validation in task 01B (pytest + ruff/mypy)
- risk areas: separator character set intentionally includes common Unicode dashes/middle dots while preserving +/#; provisional keys strip residual non-key characters after separator collapse
- next task readiness: ready for A2 re-review of 01B only; do not start 01C

## Workflow Integrity Check
- single task ID executed: 01B
- mode: same_task_repair
- no sibling tasks implemented
- no commit or staging performed
- checkbox not updated (orchestrated/repair mode)

## Repair Log

### 2026-07-12T09:29:20
- reason for repair: A2 REJECTED_WITH_WARNINGS — `normalize_skill_match_key` did not treat en dash, em dash, or middle dot as separators, so semantic variants produced divergent comparison and provisional keys (e.g. `CI-CD` -> `ci_cd` vs `CI\u2013CD` -> `cicd`).
- changes made: Expanded `_SEPARATOR_RE` in `backend/app/services/skill_normalization.py` to include soft hyphen, middle dot, Unicode hyphen range U+2010-U+2015 (en/em dash), bullet, hyphenation point, and minus sign, while keeping `+` and `#`. Added regression tests for match-key and provisional-key equivalence across ASCII hyphen / en dash / em dash / middle dot, plus +/# preservation.
- validations rerun: `python -m pytest -q tests/services/test_skill_normalization.py` (29 passed); `python -m ruff check app/services/skill_normalization.py tests/services/test_skill_normalization.py` (passed); `python -m mypy app/services/skill_normalization.py` (passed). Independent probe: all four separator variants map to `ci cd`/`ci_cd` and `machine learning`/`machine_learning`.
- outcome: complete — A2-listed punctuation normalization gap closed; required validations pass.

---

# Task Execution Report - 01C

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch01 - Validated Candidate Contracts and Persistence

## Task
01C - Implement validated profile, preference, draft, and compact-context repositories

## Status
complete

## Selected Scope
- Batch: Mandatory Batch01 - Validated Candidate Contracts and Persistence
- Task ID: 01C
- Task title: Implement validated profile, preference, draft, and compact-context repositories
- Files allowed / repair scope: backend/app/repositories/profiles.py, backend/app/repositories/preferences.py, backend/app/repositories/profile_drafts.py, backend/app/repositories/__init__.py, backend/app/services/profile_context.py, backend/app/services/chat_context.py, backend/tests/repositories/test_profiles.py, backend/tests/repositories/test_preferences.py, backend/tests/repositories/test_profile_drafts.py, backend/tests/services/test_context_assembly.py

## Source of Truth Used
- docs/plans/Plan_4.md > ### 7.2 Candidate and preference contracts
- docs/plans/Plan_4.md > ### 7.4 Tool behavior and authorization
- docs/plans/Master_plan.md > ### 6.2 Profile storage rule
- docs/plans/Master_plan.md > ### 13.1 get_candidate_context

## Supplemental Documents Used
- docs/plans/Plan_4.md
- docs/plans/Master_plan.md
- docs/tasks/task_4.md (01C block)

## Dependency and User Action Check
- Dependencies: (01A) schemas present; accepted profile/draft/preference ORM models and DatabaseSessionManager present
- User Action: None
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_4.md
- docs/plans/Plan_4.md
- docs/plans/Master_plan.md (�6.2, �7.x, �13.1)
- backend/app/db/models/profile.py
- backend/app/schemas/candidate.py
- backend/app/schemas/preferences.py
- backend/app/schemas/profile_draft.py
- backend/app/services/chat_context.py
- backend/app/repositories/attachments.py
- backend/app/repositories/conversations.py
- backend/app/repositories/__init__.py
- backend/tests/services/test_context_assembly.py
- backend/tests/repositories/* (patterns)

## Completed Work
- Implemented caller-owned-transaction ProfileRepository with Pydantic validation on every read/write, singleton load/replace, retain-active-attachment for active-context corrections, and fail-closed invalid JSON.
- Implemented PreferencesRepository singleton load/replace/delete; preservation is not-calling replace when drafts omit preferences.
- Implemented ProfileDraftRepository pending create/get/get_pending/update/discard/delete with omit-vs-replace draft document storage, same-draft correction, and source-attachment retention.
- Implemented focused ProfileContextService compact approved projection (display facts only; no evidence dumps, raw CV, paths, contact/provider fields).
- Refactored ChatContextAssembler to load approved profile/preferences only through ProfileContextService (no parallel ORM JSON parse).
- Exported new repositories from pp.repositories; kept profile_context as direct import to avoid package-level import cycles.
- Added repository tests for invalid JSON, singleton overwrite, rollback, retention, draft corrections, approved-state isolation, and omitted preferences.
- Updated context assembly tests for validated compact projection, privacy exclusions, and fail-closed invalid stored JSON.

## Files Created or Modified
- backend/app/repositories/profiles.py (created)
- backend/app/repositories/preferences.py (created)
- backend/app/repositories/profile_drafts.py (created)
- backend/app/repositories/__init__.py (modified � exports)
- backend/app/services/profile_context.py (created)
- backend/app/services/chat_context.py (modified � reuse compact context service)
- backend/app/services/__init__.py (inspected; profile_context not package-exported to avoid cycles)
- backend/tests/repositories/test_profiles.py (created)
- backend/tests/repositories/test_preferences.py (created)
- backend/tests/repositories/test_profile_drafts.py (created)
- backend/tests/services/test_context_assembly.py (modified)

## Tests or Validations Run
- command/check: cd backend; python -m pytest -q tests/repositories/test_profiles.py tests/repositories/test_preferences.py tests/repositories/test_profile_drafts.py tests/services/test_context_assembly.py
- required: yes
- result: passed
- evidence or reason: 33 passed in 4.18s

- command/check: cd backend; python -m ruff check app/repositories app/services/profile_context.py app/services/chat_context.py tests/repositories tests/services/test_context_assembly.py
- required: yes
- result: passed
- evidence or reason: All checks passed!

- command/check: cd backend; python -m mypy app/repositories app/services/profile_context.py app/services/chat_context.py
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 11 source files

## Acceptance Check
- condition: Invalid JSON never crosses the repository as an approved domain object and failed writes leave no partial singleton or draft change.
- status: satisfied
- evidence: ValidationError on invalid stored/inbound documents; FK integrity failure + caller rollback preserves prior profile; invalid draft update does not overwrite prior draft after rollback.

- condition: Repeated correction updates the same pending draft; active profile/preferences remain byte-for-byte unchanged until commit.
- status: satisfied
- evidence: same-draft update keeps one row and id; draft create/update tests assert profile_json/preferences_json unchanged.

- condition: The shared compact context contains approved display facts/preferences only and is used by existing chat assembly and the future read tool.
- status: satisfied
- evidence: ProfileContextService projects summary/title/skills/preferences without evidence/cv_text/storage_path; ChatContextAssembler loads via ProfileContextService; invalid stored profile raises ChatContextError.

## Key Implementation Decisions
- ORM vs schema name collisions resolved via aliases (CandidateProfileRow, etc.).
- Compact skill rows omit evidence snippets to keep chat/tool context free of CV-like excerpts while retaining display proficiency/years.
- profile_context repository imports are deferred inside methods to break schemas.chat ? chat_context ? profile_context ? repositories ? schemas package cycle.
- Preference preservation is intentional no-op (do not call replace), matching draft omit semantics from 01A.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode � A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files: profiles/preferences/profile_drafts repositories, profile_context service, chat_context wiring, four test modules, repositories/__init__ exports
- validations to rerun: the two required command groups under Validation in task 01C
- risk areas: compact projection intentionally drops evidence lists; get_pending returns most recent pending only; multiple concurrent pending drafts are not prevented at repository layer (commit/tool layer ownership later)
- next task readiness: ready for A2 review of 01C only

## Workflow Integrity Check
- single task ID executed: 01C
- mode: orchestrated
- no sibling tasks implemented
- no commit or staging performed
- checkbox not updated (orchestrated mode)

---

# Task Execution Report - 02A

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
same_task_repair

## Batch
Mandatory Batch02 - Safe PDF Intake to Profile Draft

## Task
02A - Implement the fail-closed PDF text and deterministic PII boundary

## Status
complete

## Selected Scope
- Batch: Mandatory Batch02 - Safe PDF Intake to Profile Draft
- Task ID: 02A
- Task title: Implement the fail-closed PDF text and deterministic PII boundary
- Files allowed / repair scope: A2 same-task repair — extend contiguous local phone recognition in pii_redaction + regression tests; rerun required focused pytest/Ruff/mypy. In-scope files: backend/app/services/pii_redaction.py, backend/tests/services/test_pii_redaction.py (prior 02A deliverables remain: pdf_text.py, services/__init__.py, test_pdf_text.py, tests/fixtures/cv_pdfs/*)

## Source of Truth Used
- docs/plans/Plan_4.md > ### 7.3 Processing pipeline
- docs/plans/Plan_4.md > ## 9. Verification & Testing Plan
- docs/plans/Master_plan.md > ### 10.2 Processing
- docs/plans/Master_plan.md > ## 20. Failure and Recovery Policy
- backend/evaluation/benchmark_pdf_extraction.py (layout mode + non-whitespace usable-character semantics)
- docs/review/review_4_review_agent.md (02A A2 REJECTED_WITH_WARNINGS repair instructions)

## Supplemental Documents Used
- docs/plans/Plan_4.md
- docs/plans/Master_plan.md
- docs/tasks/task_4.md (02A block)
- README.md (locked pypdf layout / NO_EXTRACTABLE_TEXT)

## Dependency and User Action Check
- Dependencies: Accepted pypdf==6.12.2 pin, Phase 0 layout benchmark behavior, root MAX_PDF_PAGES=10 settings present; prior 02A implementation present
- User Action: None required
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_4.md
- docs/plans/Plan_4.md (§7.3, §9)
- docs/plans/Master_plan.md (§10.2, §20)
- docs/review/review_4_review_agent.md (02A rejection: contiguous phones 5551234567 / 0901234567 / 02079460958)
- backend/app/services/pii_redaction.py
- backend/tests/services/test_pii_redaction.py
- backend/evaluation/benchmark_pdf_extraction.py (initial implementation)
- backend/tests/test_pdf_extraction_benchmark.py (synthetic PDF builders; initial)
- backend/app/config.py (MAX_PDF_PAGES / max_pdf_pages; initial)
- backend/app/services/__init__.py
- backend/app/services/attachment_storage_errors.py (stable-code error pattern; initial)
- backend/app/graph/errors.py (code-only exception pattern; initial)
- backend/pyproject.toml (pypdf pin; initial)

## Completed Work
- Implemented focused pdf_text service: pypdf layout-only extraction, DEFAULT_MAX_PDF_PAGES=10 matching typed settings, page-limit fail-closed (PAGE_LIMIT_EXCEEDED), zero usable non-whitespace characters maps to exact NO_EXTRACTABLE_TEXT, parse/source failures use PDF_PARSE_FAILED / INVALID_SOURCE. Exceptions are code-only (no raw PDF text in str/repr).
- Implemented focused pii_redaction service: deterministic email, phone, and colon-labeled address/contact-address line/inline removal; preserves experience/education/skills; fail-closed REDACTION_FAILED / INVALID_INPUT without embedding source text.
- Same-task repair: extended `_PHONE_RE` with a contiguous 10–15 digit alternative so common no-separator local/international-without-plus forms are redacted while years, room numbers, and short numeric codes remain (conservative digit-count boundary).
- Added synthetic CV PDF fixture builders under tests/fixtures/cv_pdfs for valid, image-only, multipage, and path-based cases.
- Added unit tests for extraction, page bounds, no-text, malformed PDF, redaction sentinels, Unicode, false-positive boundaries, leakage on exception surfaces, and provider-call blocking on failure.
- Same-task repair: added contiguous US/local and international-without-plus phone regression coverage while retaining formatted-number and false-positive assertions.
- Exported pdf_text / pii_redaction symbols from app.services package __init__.

## Files Created or Modified
- backend/app/services/pdf_text.py (created; prior 02A)
- backend/app/services/pii_redaction.py (created; repaired this run — contiguous phone branch)
- backend/app/services/__init__.py (modified — exports; prior 02A)
- backend/tests/services/test_pdf_text.py (created; prior 02A)
- backend/tests/services/test_pii_redaction.py (created; repaired this run — contiguous phone regression)
- backend/tests/fixtures/cv_pdfs/__init__.py (created; prior 02A)

## Tests or Validations Run
- command/check: cd backend; python -m pytest -q tests/services/test_pdf_text.py tests/services/test_pii_redaction.py
- required: yes
- result: passed
- evidence or reason: 26 passed in 0.97s (prior initial run: 25 passed; +1 contiguous-phone regression)

- command/check: cd backend; python -m ruff check app/services/pdf_text.py app/services/pii_redaction.py tests/services/test_pdf_text.py tests/services/test_pii_redaction.py
- required: yes
- result: passed
- evidence or reason: All checks passed!

- command/check: cd backend; python -m mypy app/services/pdf_text.py app/services/pii_redaction.py
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 2 source files

- command/check: targeted redact_pii probe for contiguous forms 5551234567, 0901234567, 02079460958, 447911123456 and false-positives 2019-2024 / Room 101 Building 2
- required: no (A2 acceptance probe; not a task Validation bullet)
- result: passed
- evidence or reason: all four contiguous phones removed (phones_removed=1 each); years and room numbers retained (phones_removed=0)

## Acceptance Check
- condition: Layout extraction reports page count and returns NO_EXTRACTABLE_TEXT exactly when the locked usable-character count is zero.
- status: satisfied
- evidence: valid PDF returns page_count + usable_character_count; image-only and whitespace-only raise PdfTextError with code/value NO_EXTRACTABLE_TEXT.

- condition: Every required contact sentinel is absent after redaction while non-contact experience, education, and skill text remains available.
- status: satisfied
- evidence: emails/phones (formatted and contiguous local/international-without-plus)/labeled address lines removed; Jane Doe / Acme / Python / FastAPI / Education / Skills preserved; false-positive years, Room 101, short codes, and C++/C#/CI/CD retained.

- condition: No provider adapter can be called when parsing, page validation, or redaction fails.
- status: satisfied
- evidence: tests gate provider_called/provider_calls on PdfTextError and PiiRedactionError paths; stable codes only on failure surfaces.

## Key Implementation Decisions
- Reused Phase 0 non-whitespace usable-character definition and layout mode without importing evaluation orchestration into app/.
- Address labels require a colon so compounds like english-address-keep are not redacted; inline labeled address stops at sentence terminator to keep following Skills text.
- max_pages defaults to DEFAULT_MAX_PDF_PAGES=10 mirroring Settings; callers may pass typed settings value later without coupling extract_pdf_text to full Settings loading.
- Raw extracted text lives only on PdfTextResult for the internal redaction boundary; public exceptions never carry document content.
- Contiguous phone alternative uses `\d{10,15}` (E.164-ish lower/upper bound) so separator-free local numbers match without redacting years or short codes below 10 digits.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: same_task_repair / orchestrated mode — A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files this repair: pii_redaction.py, test_pii_redaction.py (plus this report update)
- validations to rerun: the two required command groups under Validation in task 02A (pytest focused pair; ruff+mypy focused set)
- risk areas: contiguous phone lower bound is 10 digits by design; numbers shorter than 10 digits are not treated as phones; non-English address labels (e.g. Adresse) remain non-redacted by design
- next task readiness: ready for A2 re-review of 02A only; do not start 02B

## Workflow Integrity Check
- single task ID executed: 02A
- mode: same_task_repair
- no sibling tasks implemented
- no commit or staging performed
- checkbox not updated (repair/orchestrated mode)

## Repair Log

### 2026-07-12
- reason for repair: A2 REJECTED_WITH_WARNINGS — common contiguous local phone numbers (`5551234567`, `0901234567`, `02079460958`) survived redaction because the non-plus phone branch required separators.
- changes made: Extended `_PHONE_RE` in `backend/app/services/pii_redaction.py` with a contiguous `\d{10,15}` alternative; added `test_redacts_contiguous_local_and_international_without_plus_phones` covering US/local contiguous, international-without-plus, and retained formatted + false-positive cases in `backend/tests/services/test_pii_redaction.py`.
- validations rerun: focused pytest (26 passed), Ruff (All checks passed!), mypy (Success: no issues found in 2 source files); optional contiguous probe confirmed removal of A2 sample sentinels.
- outcome: complete — A2 repair items addressed; acceptance phone boundary now includes contiguous local forms.



---



# Task Execution Report - 02B



## Source Task File
docs/tasks/task_4.md



## Report File
docs/reports/report_4_execute_agent.md



## Mode
orchestrated



## Batch
Mandatory Batch02 - Safe PDF Intake to Profile Draft



## Task
02B - Expose one streaming, deduplicating staged-CV upload boundary



## Status
complete



## Selected Scope
- Batch: Mandatory Batch02 - Safe PDF Intake to Profile Draft
- Task ID: 02B
- Task title: Expose one streaming, deduplicating staged-CV upload boundary
- Files allowed / repair scope: upload dependency, route/schema/service wiring, directly required repository/storage regressions, API inventory test, and this report only



## Completed Work
- Added the exact compatible `python-multipart==0.0.30` runtime pin.
- Added `POST /api/attachments/cv` with a bounded 64 KiB upload stream and a sanitized staged-attachment response.
- Added one `CvIngestionService` boundary for MIME, PDF magic, streamed size/hash, page validation, filename sanitization, contained staging, valid staged/active deduplication, broken duplicate replacement, race cleanup, and sanitized stable errors.
- Added focused service/API tests and updated the existing authorized route inventory.



## Files Created or Modified
- backend/pyproject.toml
- backend/app/api/attachments.py
- backend/app/main.py
- backend/app/schemas/attachments.py
- backend/app/services/cv_ingestion.py
- backend/tests/api/test_attachments.py
- backend/tests/api/test_health.py
- backend/tests/services/test_cv_ingestion.py
- docs/reports/report_4_execute_agent.md



## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_cv_ingestion.py tests/api/test_attachments.py` before production edits
- required: yes (TDD red evidence)
- result: failed as expected
- evidence or reason: collection failed with `ModuleNotFoundError: app.services.cv_ingestion` before implementation.



- command/check: `cd backend; python -m pytest -q tests/services/test_cv_ingestion.py tests/api/test_attachments.py tests/repositories/test_attachments.py tests/services/test_attachment_storage.py`
- required: yes
- result: passed
- evidence or reason: 80 passed, 1 skipped in 4.16s.



- command/check: `cd backend; python -m ruff check app/api/attachments.py app/services/cv_ingestion.py app/repositories/attachments.py tests/api/test_attachments.py tests/services/test_cv_ingestion.py`
- required: yes
- result: passed
- evidence or reason: All checks passed.



- command/check: `cd backend; python -m mypy app/api/attachments.py app/services/cv_ingestion.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 2 source files.



- command/check: `cd backend; python -m pytest -q tests/api/test_health.py; python -m ruff check tests/api/test_health.py`
- required: no
- result: passed
- evidence or reason: 11 passed; route inventory and CORS regressions remain clean.



## Acceptance Check
- condition: Valid bytes create exactly one contained staged object and one metadata row; repeated identical uploads reuse it.
- status: satisfied
- evidence: focused service tests assert one staged file and equality of duplicate results.



- condition: Invalid uploads and broken duplicates leave no partial or duplicate bytes/rows and expose no path/hash/text.
- status: satisfied
- evidence: MIME, magic, size, page-limit, traversal-name, and missing-byte duplicate tests pass; route returns stable codes and the six safe metadata fields only.



- condition: The route performs no provider call, profile write, approval, or active replacement.
- status: satisfied
- evidence: route depends only on database session manager, contained attachment storage, settings limits, and the intake service.



## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode forbids A1 checkbox and batch-status changes.



## Notes for Review Agent
- changed files: backend/pyproject.toml, backend/app/api/attachments.py, backend/app/main.py, backend/app/schemas/attachments.py, backend/app/services/cv_ingestion.py, backend/tests/api/test_attachments.py, backend/tests/api/test_health.py, backend/tests/services/test_cv_ingestion.py
- validations to rerun: both exact required 02B command groups plus `python -m pytest -q tests/api/test_health.py`
- risk areas: duplicate race resolution relies on the accepted unique file-hash constraint and transaction rollback; page parsing buffers only the already bounded staged PDF (maximum configured 10 MiB).
- next task readiness: ready for A2 review of 02B only; do not start 02C.



## Workflow Integrity Check
- single task ID executed: 02B
- mode: orchestrated
- no sibling tasks implemented
- no commit or staging performed
- checkbox and batch status not updated
## Repair Log



### 2026-07-12
- reason for repair: A2 rejected 02B with warnings because the explicit regression matrix lacked malformed parsing, valid image-only page counting, concurrent duplicate races, cancellation, and partial-stream failure cleanup.
- changes made: Added focused service tests for all five scenarios and an API test for the stable sanitized `MALFORMED_PDF` response. The tests assert zero metadata rows and staged/partial files after malformed, cancelled, and failed streams, plus one shared attachment ID, one row, and one contained staged object after four concurrent identical uploads. No production behavior change was required because the new tests passed against the existing implementation.
- validations rerun: exact required pytest group passed with 86 passed and 1 skipped; exact Ruff group passed; exact mypy group passed; `python -m pytest -q tests/api/test_health.py` passed with 11 tests.
- outcome: complete - every A2 repair instruction is covered by executable regression tests and all required validations pass.



---



# Task Execution Report - 02C



## Source Task File
docs/tasks/task_4.md



## Report File
docs/reports/report_4_execute_agent.md



## Mode
orchestrated



## Batch
Mandatory Batch02 - Safe PDF Intake to Profile Draft



## Task
02C - Produce a normalized pending profile draft with one repair ceiling



## Status
complete



## Selected Scope
- Batch: Mandatory Batch02 - Safe PDF Intake to Profile Draft
- Task ID: 02C
- Task title: Produce a normalized pending profile draft with one repair ceiling
- Files allowed / repair scope: `backend/app/services/cv_ingestion.py`, `backend/app/services/profile_extraction.py`, `backend/app/services/__init__.py`, `backend/tests/services/test_profile_extraction.py`, `backend/tests/fakes/profile_extraction.py`



## Source of Truth Used
- docs/plans/Plan_4.md > ### 7.3 Processing pipeline
- docs/plans/Plan_4.md > ### 7.4 Tool behavior and authorization
- docs/plans/Master_plan.md > ### 10.2 Processing
- docs/plans/Master_plan.md > ### 13.2 `propose_profile_from_cv`
- docs/plans/Master_plan.md > ## 20. Failure and Recovery Policy



## Dependency and User Action Check
- Dependencies: 01A, 01B, 01C, 02A, and 02B are checked in `docs/tasks/task_4.md`; staged and active attachment seams are present.
- User Action: None required.
- Dependencies satisfied: yes



## Files Inspected Before Editing
- README.md
- docs/tasks/task_4.md
- docs/plans/Plan_4.md
- docs/plans/Master_plan.md
- backend/app/services/cv_ingestion.py
- backend/app/services/shopaikey_chat.py
- backend/app/services/skill_normalization.py
- backend/app/services/pdf_text.py
- backend/app/services/pii_redaction.py
- backend/app/schemas/candidate.py
- backend/app/schemas/profile_draft.py
- backend/app/repositories/attachments.py
- backend/app/repositories/profile_drafts.py
- backend/app/api/attachments.py
- backend/tests/services/test_cv_ingestion.py
- backend/tests/services/test_shopaikey_chat.py
- backend/tests/repositories/test_profile_drafts.py



## Completed Work
- Added `CvIngestionService.propose_profile_from_cv(attachment_id)` with the authoritative single pipeline order: valid staged/active attachment, layout text extraction, deterministic PII redaction, locked structured Candidate extraction, evidence validation, shared skill normalization, and transactional pending-draft creation.
- Reused `ShopAIKeyChatAdapter.invoke_structured(CandidateProfile, ...)`; its existing strict-schema, `gpt-4o-mini`, and single schema-repair ceiling remain the only repair loop.
- Added a focused profile-extraction boundary that rejects missing/invented evidence and provider-generated contact PII, normalizes Candidate skills, and constructs a bounded approval summary with preferences omitted.
- Draft creation never writes the approved profile/preferences or mutates staged/active attachment state. The attachment is revalidated at the persistence boundary and remains the source for both staged and active inputs.
- Added fake-backed tests for redaction leakage, success, one schema repair, repair failure, provider failure, invented/missing evidence, precise years without timeline evidence, exclusion preservation, active attachment inputs, no preference inference, and no pending draft on any invalid final result.



## Files Created or Modified
- backend/app/services/cv_ingestion.py
- backend/app/services/profile_extraction.py
- backend/app/services/__init__.py
- backend/tests/services/test_profile_extraction.py
- backend/tests/fakes/profile_extraction.py



## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_profile_extraction.py tests/services/test_cv_ingestion.py tests/repositories/test_profile_drafts.py tests/services/test_shopaikey_chat.py`
- required: yes
- result: passed
- evidence or reason: 55 passed in 3.83s.



- command/check: `cd backend; python -m ruff check app/services/cv_ingestion.py app/services/profile_extraction.py app/services/shopaikey_chat.py tests/services/test_profile_extraction.py tests/services/test_cv_ingestion.py`
- required: yes
- result: passed
- evidence or reason: All checks passed.



- command/check: `cd backend; python -m mypy app/services/cv_ingestion.py app/services/profile_extraction.py app/services/shopaikey_chat.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 3 source files.



- command/check: `git diff --check`
- required: no
- result: passed
- evidence or reason: no whitespace errors reported.



## Acceptance Check
- condition: The fake provider receives only deterministically redacted text and is not invoked after prior extraction/redaction failure.
- status: satisfied
- evidence: prompt construction receives only `redact_pii(...).text`; fake request, error/log surface, and stored draft checks exclude unique email/phone/address sentinels.



- condition: Exactly zero or one repair occurs, and invalid final output creates no draft or approved-state change.
- status: satisfied
- evidence: service delegates solely to adapter `invoke_structured`; fake tests assert initial plus one repair for invalid schema and zero pending drafts for repair, provider, evidence, and no-timeline failures.



- condition: A valid result is normalized and stored as one validated pending draft; active profile/preferences and attachment state remain unchanged.
- status: satisfied
- evidence: `ProfileDraftRepository.create` persists validated draft JSON in a session transaction; draft preferences are omitted, normalization/exclusion assertions pass, and staged/active attachment-state tests remain unchanged.



## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated A1 execution must not update progress tracking.



## Notes for Review Agent
- changed files: `backend/app/services/cv_ingestion.py`, `backend/app/services/profile_extraction.py`, `backend/app/services/__init__.py`, `backend/tests/services/test_profile_extraction.py`, `backend/tests/fakes/profile_extraction.py`
- validations to rerun: both required task commands above.
- risk areas: the provider adapter intentionally retains its shared one transient retry policy in addition to its one schema repair ceiling; this task adds no fallback model or second repair loop.
- next task readiness: can review



## Workflow Integrity Check
- single task ID executed: 02C
- mode: orchestrated
- no sibling tasks implemented
- no commit or staging performed
- checkbox and batch status not updated



---



# Task Execution Report - batch_scope



## Source Task File
docs/tasks/task_4.md



## Report File
docs/reports/report_4_execute_agent.md



## Mode
batch_scope_repair



## Batch
Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync



## Task
batch_scope - Remove historical report edits from the Batch03 candidate



## Status
complete



## Selected Scope
- Batch: Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync
- Task ID: batch_scope
- Task title: Remove historical report edits from the Batch03 candidate
- Files allowed / repair scope: Restore the four historical 01C character positions to the committed baseline while preserving the accepted 03A/03B execution evidence and all task checkboxes.



## Completed Work
- Restored the four pre-Batch03 01C character positions to their exact committed baseline values.
- Preserved the accepted 03A/03B execution evidence and Batch03 task checkbox state.



## Files Created or Modified
- docs/reports/report_4_execute_agent.md (restored historical baseline content; updated this batch-scope repair block)



## Tests or Validations Run
- command/check: Targeted `git diff -- docs/reports/report_4_execute_agent.md docs/review/review_4_review_agent.md` inspection
- required: yes
- result: passed
- evidence or reason: no historical 01C substitution remains in the diff; Batch03 execution blocks remain present.



- command/check: `rg -n "^- \\[x\\] \\(03[AB]\\)" docs/tasks/task_4.md`
- required: yes
- result: passed
- evidence or reason: 03A and 03B remain checked; no task file was modified.



- command/check: `git diff --check`
- required: no
- result: passed
- evidence or reason: no whitespace errors reported.



## Acceptance Check
- condition: Remove only unrelated historical documentation edits while preserving Batch03 evidence and task tracking.
- status: satisfied
- evidence: restored the exact committed 01C values; no implementation files, review files, or task checkboxes changed.



## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: batch_scope_repair mode forbids progress tracking changes.



## Notes for Review Agent
- changed files: docs/reports/report_4_execute_agent.md only.
- validations to rerun: targeted report diff and Batch03 checkbox inspection only.
- risk areas: none; this repair intentionally does not modify implementation or accepted Batch02 evidence.
- next task readiness: ready for A3 scope re-audit.



## Workflow Integrity Check
- single repair scope executed: batch_scope
- mode: batch_scope_repair
- no task implementation or sibling work performed
- no commit or staging performed
- task checkboxes and batch status not updated



## Repair Log



### 2026-07-12
- reason for repair: A3 SCOPE_ISSUE identified unrelated historical report/review changes mixed into the Batch02 diff.
- changes made: restored four 01C characters in the A1 report and the existing 01B A2 mode value.
- validations rerun: targeted historical diff inspection, accepted Batch02 checkbox inspection, and `git diff --check`.
- outcome: complete - only the A3-listed documentation scope findings were repaired.

### 2026-07-12 (Batch03 scope repair)
- reason for repair: A3 SCOPE_ISSUE found four historical 01C character substitutions mixed into the Batch03 execution-report diff.
- changes made: restored those four character positions to the exact committed baseline and preserved all 03A/03B evidence.
- validations rerun: targeted historical diff inspection, accepted Batch03 checkbox inspection, and `git diff --check`.
- outcome: complete - the execution-report diff now contains Batch03/batch-scope evidence only.

---

# Task Execution Report - 03A

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync

## Task
03A - Implement coalescing Candidate outbox work and idempotent graph projection

## Status
complete

## Selected Scope
- Batch: Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync
- Task ID: 03A
- Task title: Implement coalescing Candidate outbox work and idempotent graph projection
- Files allowed / repair scope: Candidate outbox coalescing, approved-profile enqueue, Candidate/Skill projection, bounded startup retry, Candidate-only graph rebuild, and directly required tests listed by task 03A.

## Source of Truth Used
- `docs/plans/Plan_4.md` > `### 7.6 Candidate graph synchronization`
- `docs/plans/Master_plan.md` > `### 8.4 Graph safety rules`
- `docs/plans/Master_plan.md` > `## 21. SQLite-to-Neo4j Synchronization`

## Dependency and User Action Check
- Dependencies (01B) and (01C) are checked complete; existing graph uniqueness constraints/client and `GraphOutboxRepository` were inspected and reused.
- User Action: None; all required graph tests use injected fakes.

## Completed Work
- Added opt-in outbox coalescing that replaces only validated safe payloads, requeues pending/failed/synced logical identities, clears stale error state, and preserves attempt history without changing default replay behavior for unrelated callers.
- Enqueued identifier-only Candidate sync work in the same caller-owned transaction as every approved singleton profile replacement.
- Added a focused projector that reloads the current validated Candidate from SQLite, merges one Candidate and canonical Skill nodes, removes stale `HAS_SKILL` edges, excludes non-score-bearing skills, preserves aliases/provisional status as properties, and never creates `RELATED_TO` edges.
- Added bounded operation-filtered processing, failed-work replay, sanitized failure status, best-effort startup processing, and the Candidate-only rebuild stage. Job, JobFamily, embedding, verification, and remaining stages stay explicitly incomplete.
- Added repository, fake-graph, integration, rebuild, and lifecycle coverage for coalescing, successive approvals, rollback, outage/replay, exact relationship replacement, exclusion, alias/provisional properties, slash-bearing skill text, startup retry, and duplicate prevention.

## Files Created or Modified
- backend/app/repositories/graph_outbox.py
- backend/app/repositories/profiles.py
- backend/app/graph/candidate_sync.py (created)
- backend/app/graph/__init__.py
- backend/app/main.py
- infrastructure/scripts/rebuild_graph.py
- backend/tests/repositories/test_graph_outbox.py
- backend/tests/graph/test_candidate_sync.py (created)
- backend/tests/integration/test_candidate_sync.py (created)
- backend/tests/infrastructure/test_rebuild_graph.py
- backend/tests/test_lifecycle.py
- docs/reports/report_4_execute_agent.md

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py tests/infrastructure/test_rebuild_graph.py tests/test_lifecycle.py`
- required: yes
- result: passed
- evidence or reason: 57 passed in 5.85s on the final required run.

- command/check: `cd backend; python -m ruff check app/repositories/graph_outbox.py app/graph/candidate_sync.py tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py`
- required: yes
- result: passed
- evidence or reason: All checks passed on the final required run.

- command/check: `cd backend; python -m mypy app/repositories/graph_outbox.py app/graph/candidate_sync.py`
- required: yes
- result: passed
- evidence or reason: Success; no issues found in 2 source files.

- command/check: touched-file Ruff for graph exports, lifecycle, profile repository, rebuild implementation, and their tests
- required: no
- result: passed
- evidence or reason: All checks passed after mechanical import ordering.

- command/check: `cd backend; python -m pytest -q tests/repositories/test_profiles.py`
- required: no
- result: passed
- evidence or reason: 7 passed in 1.60s.

- command/check: `git diff --check`
- required: no
- result: passed
- evidence or reason: exit code 0; only line-ending conversion warnings were emitted.

- command/check: `cd backend; python -m pytest -q -m neo4j tests/integration/test_candidate_sync.py`
- required: no
- result: not_run
- evidence or reason: optional live Neo4j validation was not needed; required integration coverage uses the task-mandated fake graph client.

## Acceptance Check
- condition: successive singleton Candidate changes remain one durable row but each becomes processable current-state sync work.
- status: satisfied
- evidence: repository and integration tests cover pending coalescing plus failed/synced requeue across two approvals, preserving one outbox identity.

- condition: replay/restart produces one Candidate, one Skill per canonical key, and the exact current non-excluded `HAS_SKILL` set.
- status: satisfied
- evidence: the parameter-bound `MERGE` projection deletes stale Candidate skill edges before merging the current set; stateful fake integration and startup/rebuild tests pass.

- condition: Neo4j failure preserves canonical SQLite state and retryable sanitized work without private payloads or trusted `RELATED_TO` edges.
- status: satisfied
- evidence: outage/rollback/replay tests pass; outbox payload is exactly `{candidate_id: 1}`; graph query contains no `RELATED_TO`; skill display/alias text including `CI/CD` projects normally.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode forbids task checkbox and batch-status updates.

## Notes for Review Agent
- changed files: all files listed above; pre-existing dirty 03A workspace work was inspected, preserved, and completed.
- validations to rerun: both task-required validation groups.
- risk areas: graph projection uses one atomic Cypher statement; optional live Neo4j marker validation was not run. Job/JobFamily/embedding rebuild stages intentionally remain incomplete.
- next task readiness: ready for A2 review of 03A only.

## Workflow Integrity Check
- exactly one task executed: 03A
- mode: orchestrated
- no sibling task, checkbox, batch status, commit, or staging performed

---

# Task Execution Report - 03B

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
same_task_repair

## Batch
Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync

## Task
03B - Atomically commit a draft with filesystem compensation and cleanup retry

## Status
complete

## Selected Scope
- Batch: Mandatory Batch03 - Atomic Approved State and Candidate Graph Sync
- Task ID: 03B
- Task title: Atomically commit a draft with filesystem compensation and cleanup retry
- Files allowed / repair scope: profile commit unit of work, inverse contained storage promotion, safe unreferenced-attachment cleanup selection, and directly required tests.

## Dependency and User Action Check
- dependencies: 01C, 02C, and 03A are A2 ACCEPTED; accepted caller-owned storage/repository transaction boundaries are present.
- user actions: none required.

## Source of Truth Used
- `docs/plans/Plan_4.md` - `### 7.5 Atomic replacement`
- `docs/plans/Master_plan.md` - `### 6.2 Profile storage rule`
- `docs/plans/Master_plan.md` - `### 10.4 Atomic replacement`
- `docs/plans/Master_plan.md` - `### 21.1 Outbox rule`

## Files Inspected Before Editing
- `README.md`
- `docs/tasks/task_4.md`
- cited Plan 4 and Master Plan sections
- accepted attachment storage operations and all storage lifecycle callers
- attachment/profile/preference/draft/outbox repositories and callers
- transaction manager and directly relevant tests

## Completed Work
- Added one `ProfileCommitService` unit of work that validates the pending draft/source, promotes staged bytes before SQLite commit, marks the source active, replaces the profile singleton, replaces preferences only when proposed, deletes the draft, and requeues identifier-only Candidate sync through the accepted profile repository transaction.
- Added contained active-to-staged restore by refactoring promotion and compensation onto the existing non-overwriting cross-area publisher.
- Added pre-commit compensation: ordinary failures restore promoted bytes to staged state; injected restore failure durably corrects source metadata to the still-usable active bytes while preserving the old approved profile and pending draft.
- Added post-commit old-file cleanup and bounded retry. Cleanup candidates exclude approved-profile and pending-draft references; metadata deletion is flushed transactionally, bytes are deleted before commit, and failures retain a durable retryable row.
- Preserved active-context/already-active sources without moving/deleting the current PDF, and preserved singleton preferences when omitted from the draft.
- Added failure coverage for validation, promotion, attachment/profile/preference/draft mutations, outbox enqueue, SQLite commit, compensation, byte/metadata cleanup, and referenced-old-source protection.
- Repaired post-promotion cancellation handling so `BaseException` paths compensate the filesystem before cancellation is re-raised unchanged; added a regression proving the pending source remains readable at its canonical staged path.

## Files Created or Modified
- `backend/app/services/profile_service.py` (created)
- `backend/app/services/attachment_storage.py`
- `backend/app/repositories/attachments.py`
- `backend/tests/services/test_profile_service.py` (created)
- `backend/tests/integration/test_profile_replacement.py` (created)
- `backend/tests/repositories/test_attachments.py`
- `docs/reports/report_4_execute_agent.md`

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_profile_service.py tests/integration/test_profile_replacement.py tests/repositories/test_attachments.py tests/repositories/test_graph_outbox.py`
- required: yes
- result: passed
- evidence or reason: 59 passed in 6.51s after the cancellation repair.

- command/check: `cd backend; python -m ruff check app/services/profile_service.py app/services/attachment_storage.py app/repositories tests/services/test_profile_service.py tests/integration/test_profile_replacement.py`
- required: yes
- result: passed
- evidence or reason: all checks passed.

- command/check: `cd backend; python -m mypy app/services/profile_service.py app/services/attachment_storage.py app/repositories`
- required: yes
- result: passed
- evidence or reason: success with no issues in 11 source files.

- command/check: focused TDD and referenced-old-source regression runs
- required: no
- result: passed
- evidence or reason: 31 focused tests passed after the referenced-old-source regression first failed and the cleanup root cause was corrected.

- command/check: `git diff --check`
- required: no
- result: passed
- evidence or reason: exit code 0; existing line-ending conversion warnings only.

## Acceptance Check
- condition: success leaves one singleton pointing to the intended active source, applies only proposed preferences, removes the draft, and requeues identifier-only Candidate sync in the same commit.
- status: satisfied
- evidence: success tests validate singleton/profile/preference/draft/attachment state; outbox payload is exactly `{candidate_id: 1}`.

- condition: every pre-commit failure preserves the prior approved profile/CV and a recoverable pending draft/source without a public no-profile/no-file interval.
- status: satisfied
- evidence: injected validation, promotion, repository, outbox, commit, and compensation failures keep old approved bytes readable and the proposed source usable as staged or durably corrected active state.

- condition: cleanup-only failure keeps the newly approved state usable and leaves bounded durable cleanup work removable later.
- status: satisfied
- evidence: byte- and metadata-cleanup failures retain the unreferenced row and bounded retry removes it; referenced active sources are excluded.

- condition: active-context/already-active sources commit without moving/deleting the current PDF, and omitted preferences remain unchanged.
- status: satisfied
- evidence: the active-source test preserves attachment ID/path/bytes and prior preferences while updating the profile.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: same-task repair mode forbids task checkbox and batch-status updates.

## Notes for Review Agent
- changed files: only the six 03B implementation/test files above plus this report block; accepted pre-existing 03A changes were preserved and not attributed to 03B.
- validations to rerun: both task-required validation groups.
- risk areas: compensation fallback records the promoted source active only when inverse restore fails; the pending draft reference excludes it from cleanup.
- next task readiness: ready for A2 review of 03B only.

## Workflow Integrity Check
- exactly one task executed: 03B
- mode: same_task_repair
- no sibling task, checkbox, batch status, commit, or staging performed

## Repair Log

### 2026-07-12
- reason for repair: A2 rejected the initial handoff because `asyncio.CancelledError` after promotion bypassed filesystem compensation and could strand staged metadata pointing to active-only bytes.
- changes made: added a cancellation regression first, confirmed the canonical staged path was unreadable, then widened the outer cleanup boundary to `BaseException` while preserving non-`Exception` cancellation semantics after compensation.
- validations rerun: cancellation regression passed; exact required pytest passed with 59 tests; exact Ruff and mypy commands passed.
- outcome: the pending draft source remains readable through canonical staged metadata after post-promotion cancellation; ready for same-task A2 re-review.
