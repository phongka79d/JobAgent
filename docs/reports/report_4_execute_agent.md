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
