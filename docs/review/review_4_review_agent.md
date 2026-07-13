---

# Task Review Report - 01A

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
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01A
- Task title: Define the exact Candidate Profile, Skill, Preference, and Draft contracts
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes (working tree: untracked implementation files only; no staged/modified tracked source)
- changed files from git:
  - `?? backend/app/schemas/profile.py`
  - `?? backend/app/schemas/skills.py`
  - `?? backend/tests/unit/test_profile_schemas.py`
  - `?? docs/reports/report_4_execute_agent.md` (execution report; not implementation)
- recent commits: HEAD is prior Plan 3 work; 01A artifacts are uncommitted untracked files matching the A1 file list

## Files Reviewed
- `backend/app/schemas/skills.py`: in scope - `SkillRef` + `parse_skill_ref`; exact Master §7.1 fields; `StrictModelConfig`
- `backend/app/schemas/profile.py`: in scope - `CandidateSkill`, `ExperienceItem`, `EducationItem`, `LanguageItem`, `CandidateProfile`, `JobPreferences`, `ProfileDraftPayload`, enum Literals, confidence `Field(ge=0, le=1)`, `parse_*` helpers; validated-model boundary docstring; no ORM/IO
- `backend/tests/unit/test_profile_schemas.py`: in scope - field sets, nullability, enums, confidence bounds, extra=forbid, evidence shape, nested validation, fact/preference separation, JSON round-trip, import hygiene
- `backend/app/schemas/common.py`: dependency check - reuses existing `StrictModelConfig`
- `docs/plans/Master_plan.md` §7.1–7.3 and `docs/plans/Plan_4.md` §7.1: source contracts cross-checked against models

## Validations Reviewed
- Command/check: `Set-Location backend; python -m pytest tests/unit/test_profile_schemas.py -q`
- Required: yes
- Reported result: passed (29 passed)
- Rerun result: passed (29 passed, exit 0)
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: `Set-Location backend; python -m ruff check app/schemas/profile.py app/schemas/skills.py tests/unit/test_profile_schemas.py; python -m mypy app`
- Required: yes
- Reported result: passed
- Rerun result: passed (ruff All checks passed; mypy Success: no issues found in 50 source files)
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: search `profile_json|draft_json|preferences_json|CandidateProfile|ProfileDraftPayload` under backend/app and backend/tests
- Required: yes
- Reported result: passed (Pydantic ownership in schemas; ORM columns only; no competing contract)
- Rerun result: passed (rg via review search tool)
- Status: passed
- Notes: Pydantic models only in `app.schemas.profile` / `app.schemas.skills`; ORM JSON columns and seed empty preferences remain separate; no service JSON writer competing contracts yet

## Acceptance Review
- Task acceptance: Model fields and allowed enum values exactly match Master contracts; unknown fields and out-of-range confidence fail
- Status: satisfied
- Evidence: Field sets match Master §7.1–7.3 / Plan_4 §7.1; Literals match proficiency/source/work_mode/seniority enums; confidence ge/le on both skill and extraction confidence; extra=forbid via StrictModelConfig; tests cover rejection

- Task acceptance: Complete `ProfileDraftPayload` round-trips through JSON without merging profile facts into Job Preferences or losing correction/exclusion fields
- Status: satisfied
- Evidence: `test_profile_draft_payload_json_round_trip_preserves_separation` and merge-rejection tests; nested `candidate_profile` / `job_preferences`; `source=user_correction` and `excluded=true` preserved

- Task acceptance: No ORM, provider, filesystem, graph, route, or Agent behavior in schema modules
- Status: satisfied
- Evidence: module source and `test_schema_modules_have_no_orm_or_io_imports`

## Implementation Reality
- Real Pydantic BaseModel contracts with validation; not stubs or hardcoded success paths
- `end_date_text: str | None` correctly models Master `str | present | None` (free-form text; `"present"` is a conventional current-role string value, not a separate type)
- SkillRef isolated in `skills.py` for later Job reuse; profile models compose it

## Architecture Alignment
- Reuses `StrictModelConfig` from `app.schemas.common`
- Schema modules stay pure; validated-model boundary for later `profile_json` / `draft_json` / `preferences_json` writers documented
- No extraction, persistence, graph, or API logic in schema files
- In-scope file set only (three task Files entries)

## Hardcoding Review
- No hardcoding/overfitting of fixture strings into runtime schema logic
- Enum values match source contracts, not ad-hoc aliases

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None

### Major
- None

### Minor
- None material. Name overlap between Pydantic and SQLAlchemy `CandidateProfile` / `JobPreferences` is intentional and documented in module docstrings.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None

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
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01B
- Task title: Create the authoritative approved taxonomy and sole deterministic skill normalizer
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes (working tree: untracked 01A/01B implementation + reports; task_4.md modified for checkboxes only)
- changed files from git (01B-relevant untracked):
  - `?? backend/app/services/skill_normalization.py`
  - `?? backend/tests/fixtures/skills_seed.yaml`
  - `?? backend/tests/unit/test_skill_normalization.py`
  - `?? infrastructure/neo4j/skills_seed.yaml`
  - `?? docs/reports/report_4_execute_agent.md` (execution report; not implementation)
- recent commits: HEAD remains prior Plan 3 / task file work; 01B artifacts are uncommitted and match A1 file list

## Files Reviewed
- `infrastructure/neo4j/skills_seed.yaml`: in scope - sole production taxonomy; 18 skills + 4 RELATED_TO edges (weight 0.6, source seed) match user-approved option-1 tables exactly; JSON-compatible YAML + ponytail comments
- `backend/tests/fixtures/skills_seed.yaml`: in scope - smaller test-only synthetic taxonomy (5 skills, 2 edges); no external approval required
- `backend/app/services/skill_normalization.py`: in scope - sole loader/normalizer; stdlib json after comment strip; NFKC/whitespace/casefold/separator fingerprint; alias resolution; unknown key derivation; collision/endpoint/weight validation; canonical ordering; SkillRef + CandidateSkill preservation; production path via repo_root(); relationships_for returns only seed edges
- `backend/tests/unit/test_skill_normalization.py`: in scope - 20 unit tests covering unicode/whitespace/case/punctuation/aliases/unknowns/repeats/collisions/invalid edges/weights/self-loops/malformed seed/ordering/import hygiene
- `backend/app/schemas/skills.py`: dependency - SkillRef reused; 01A satisfied
- `docs/plans/Plan_4.md` §6 / §7.2 and `docs/plans/Master_plan.md` §8.4 / §9: source requirements cross-checked

## Validations Reviewed
- Command/check: `Set-Location backend; python -m pytest tests/unit/test_skill_normalization.py -q`
- Required: yes
- Reported result: passed (20 passed)
- Rerun result: passed (20 passed, exit 0)
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: `Set-Location backend; python -m ruff check app/services/skill_normalization.py tests/unit/test_skill_normalization.py; python -m mypy app`
- Required: yes
- Reported result: passed (ruff All checks passed; mypy Success: no issues found in 51 source files)
- Rerun result: passed (ruff All checks passed; mypy Success: no issues found in 51 source files)
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: search `skills_seed|canonical_key|Unicode|unicodedata|RELATED_TO|aliases` under `backend/app`, `backend/tests`, `infrastructure/neo4j`
- Required: yes
- Reported result: passed (sole normalizer/parser; one production seed; test fixture inject path)
- Rerun result: passed (workspace search)
- Status: passed
- Notes: Sole implementation is `app.services.skill_normalization`; production seed only under `infrastructure/neo4j/skills_seed.yaml`; fixture is test-only; graph constraint mentions Skill.canonical_key uniqueness only; status "aliases" hits in common/sse/tool_result are Plan 3 vocabulary, not skill taxonomy

- Command/check: `SkillNormalizer.production()` load smoke
- Required: no (acceptance aid)
- Reported result: passed (18 skills, 4 edges)
- Rerun result: passed (18 skills, 4 edges; k8s→kubernetes; postgres→postgresql; unknown empty aliases/category and no edges)
- Status: passed
- Notes: A2 independent production load confirmed

## Acceptance Review
- Task acceptance: Production code loads only `infrastructure/neo4j/skills_seed.yaml` through the single service; tests inject smaller fixture via same parser
- Status: satisfied
- Evidence: `PRODUCTION_SKILLS_SEED_RELATIVE` / `SkillNormalizer.production()` / `from_path`; fixture used only in unit tests via same load path

- Task acceptance: Equivalent inputs resolve to one stable SkillRef; unknowns deterministic with no invented metadata/relationship
- Status: satisfied
- Evidence: unit tests for unicode/whitespace/case/punctuation/aliases/unknowns/repeats; `relationships_for` empty for unknowns

- Task acceptance: Duplicate/colliding keys or aliases and invalid relationship endpoints/weights fail before use
- Status: satisfied
- Evidence: invalid-seed unit tests raise SkillTaxonomyError

- Task acceptance: No second normalizer, copied taxonomy, LLM-generated alias, or automatic related-skill edge
- Status: satisfied
- Evidence: single service module; production seed equals user-approved tables only; no LLM alias generation; relationships only from seed list

- Task acceptance: User-approved production taxonomy present
- Status: satisfied
- Evidence: envelope USER_APPROVAL_NOTE option 1; seed content matches A1 approved skills/RELATED_TO tables verbatim (18 + 4)

## Implementation Reality
- Real deterministic normalizer with validation; not stubs or hardcoded success paths
- Production seed is real YAML/JSON file content matching approval; loader uses stdlib json only
- Mocks not used for production path; tests inject fixture through same parser

## Architecture Alignment
- Sole owner at `app.services.skill_normalization` per Plan_4 §7.2
- Pipeline matches Master §9.1 steps 1–6
- Graph safety: unknowns get no RELATED_TO (Master §8.4)
- SkillRef from 01A; CandidateSkill field preservation for corrections/exclusions
- No Neo4j/provider/route I/O in the normalizer module

## Hardcoding Review
- No overfitting of fixture strings into runtime success logic
- Taxonomy content is the intentional approved seed, not test-only hardcoding in production code

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Sibling checkboxes: 01A left checked; 01C/01D left unchecked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None

### Major
- None

### Minor
- None material. Unit suite primarily uses the smaller fixture; production seed correctness is covered by path constant test + independent A2 production load smoke, not a dedicated unit assertion of all 18 production rows (acceptable for this task).

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None

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
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01C
- Task title: Implement focused attachment and profile repositories over the existing schema
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes (tracked source clean for migrations/models; 01C artifacts untracked)
- changed files from git (01C-relevant):
  - `?? backend/app/repositories/attachments.py`
  - `?? backend/app/repositories/profiles.py`
  - `?? backend/tests/integration/test_cv_api.py`
  - `?? backend/tests/integration/test_profile_approval.py`
- other untracked Batch01 siblings (01A/01B/docs) present but not treated as 01C scope
- `git diff -- backend/migrations backend/app/db/models`: empty (no schema drift)
- recent commits: HEAD is prior Plan 3 / task_4 scaffolding; 01C implementation is uncommitted untracked files matching the A1 file list

## Files Reviewed
- `backend/app/repositories/attachments.py`: in scope - get_by_id / get_by_file_hash / get_active; create_staged; mark_active / mark_failed / retry_as_staged via explicit `_ALLOWED_TRANSITIONS`; delete (row only); InvalidAttachmentTransitionError leaves state untouched; flush-only, no commit/rollback/session open; uses existing ATTACHMENT_STATE_* and utc_now
- `backend/app/repositories/profiles.py`: in scope - singleton get/upsert active profile, get/upsert/delete current draft, get/upsert job preferences; fixed CANDIDATE_PROFILE_ID / PROFILE_DRAFT_ID / JOB_PREFERENCES_ID only; JSON dict type-gate only (no Pydantic shape validation); flush-only, no commit/rollback/IO/Neo4j
- `backend/tests/integration/test_cv_api.py`: in scope - migrated-SQLite repository cases for hash/state reads, allowed and forbidden transitions (no mutation), page_count/failure_code rules, delete, timestamps, unique hash / single-active IntegrityError, no-commit isolation, static source hygiene
- `backend/tests/integration/test_profile_approval.py`: in scope - profile/draft/preferences singleton CRUD, FK RESTRICT on active attachment delete, draft cascade on attachment delete, timestamps, no-commit isolation, no Pydantic/commit/IO in repository source
- `backend/app/db/models/attachments.py`, `backend/app/db/models/profiles.py`: dependency check - models/constants reused; no model edits
- `backend/app/repositories/tool_executions.py` (pattern reference): architecture alignment - same transition-map + flush-only style
- `backend/app/repositories/__init__.py`: package docstring still describes session ownership (no re-export change required for 01C)

## Validations Reviewed
- Command/check: `Set-Location backend; python -m pytest tests/integration/test_cv_api.py tests/integration/test_profile_approval.py -q`
- Required: yes
- Reported result: passed (32 passed)
- Rerun result: passed (32 passed, exit 0)
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: `Set-Location backend; python -m pytest tests/unit/test_attachment_profile_models.py tests/integration/test_database_contract.py tests/integration/test_migrations.py -q`
- Required: yes
- Reported result: passed (24 passed)
- Rerun result: passed (24 passed, exit 0)
- Status: passed
- Notes: schema/migration contracts do not regress

- Command/check: `Set-Location backend; python -m ruff check app/repositories/attachments.py app/repositories/profiles.py tests/integration/test_cv_api.py tests/integration/test_profile_approval.py; python -m mypy app`
- Required: yes
- Reported result: passed (ruff + mypy)
- Rerun result: passed (ruff "All checks passed!"; mypy "Success: no issues found in 53 source files")
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: `git diff -- backend/migrations backend/app/db/models`
- Required: yes
- Reported result: passed (empty)
- Rerun result: passed (empty diff; no untracked model/migration changes)
- Status: passed
- Notes: no Plan 4 migration or schema drift

## Acceptance Review
- Task acceptance: focused attachment/profile repository primitives over existing four profile-family tables; no commit/rollback; no schema migration; exact-hash lookup and explicit allowed transitions; invalid transitions non-mutating; service-owned validation/transactions
- Status: satisfied
- Evidence:
  - Repositories import only existing ORM models and state/singleton constants; create_staged relies on UUID defaults; mutations set `updated_at = utc_now()`
  - Exact `get_by_file_hash`; transitions staged→active|failed and failed→staged only; parametrized forbidden-transition tests prove state/failure_code/page_count/updated_at unchanged
  - Source inspection + flush-only isolation tests prove no session.commit/rollback, no filesystem/provider/Neo4j/routes
  - Empty migration/model git diff; Plan 2 contract tests pass
  - Tests are real migrated-SQLite integration tests, not stubs

## Implementation Reality
- Production paths are real SQLAlchemy async session operations with flush, not hardcoded success stubs
- Mocks are not used to fake repository success; IntegrityError paths exercise real SQLite constraints
- ProfileNotFoundError is defined but unused (minor; does not affect acceptance)

## Hardcoding Review
- No overfitting to fixture hashes or gold answers in production code
- Singleton IDs and state strings come from model constants, not inventing new transition vocabularies
- Tests use synthetic hashes/paths as expected for isolation

## Architecture Alignment
- Matches Plan 3 repository style (caller-owned session, flush-only, typed errors, transition maps)
- Business validation, multi-row approval ordering, filesystem, and providers correctly deferred to later services
- JSON documents stored as caller dicts without re-validating 01A Pydantic contracts at repository layer (as required)

## Report Accuracy
- A1 status complete, file list, validation counts (32+24), ruff/mypy, and empty migration/model diff match repository evidence
- Scope limited to allowed files; test modules named for later API/approval growth but currently repository-focused only (explicitly noted by A1 and acceptable per task Files list)

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Sibling checkboxes: 01A/01B left checked; 01D left unchecked
- Batch status updated by reviewer: no

## Issues

### Blocking
- None

### Major
- None

### Minor
- `ProfileNotFoundError` is declared in `profiles.py` but unused (harmless reserved error class).
- Working tree also contains untracked 01A/01B artifacts and execution/review docs; not attributed to 01C and not scope-violating for this review.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None

---

# Task Review Report - 01D

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
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01D
- Task title: Promote the proven pypdf extraction and meaningful-text rule into one production owner
- Executor status reported: complete

## Git Diff Evidence
- git status reviewed: yes
- git diff reviewed: yes
- changed files from git (01D-relevant):
  - `?? backend/app/services/pdf_extraction.py` (created)
  - `?? backend/tests/unit/test_pdf_extraction.py` (created)
  - ` M infrastructure/scripts/verify_pdf_extraction.py` (refactored to import production owner; -100/+61 net simplification)
  - `docs/reports/report_4_execute_agent.md` (execution report; not implementation)
- recent commits: HEAD is prior Plan 3 / task_4 scaffolding; 01D implementation is uncommitted working-tree work matching the A1 file list
- sibling Batch01 untracked artifacts (schemas, repositories, skills seed, other reports) are present but not attributed to 01D and not required for this review

## Files Reviewed
- `backend/app/services/pdf_extraction.py`: in scope - sole production owner; Phase 0 constants (`MIN_NON_WHITESPACE_CHARS=80`, identity/experience/skills markers, `MEANINGFUL_TEXT_RULE`); `is_meaningful_text` / normalize / measure; pypdf-only `PdfReader` via `_open_reader`, `parse_page_count`, `extract_modes` (normal + layout), `extract_pdf_text`; stable `NO_EXTRACTABLE_TEXT` / `MALFORMED_PDF` + `PdfMalformedError`; transient `PdfTextExtraction` with layout-preferred `preferred_text`; explicit no-OCR / no-public-raw-text ownership docs
- `backend/tests/unit/test_pdf_extraction.py`: in scope - five digital fixtures meaningful, image-only `NO_EXTRACTABLE_TEXT` with 0 non-ws, page counts, malformed inputs, rule thresholds, preferred_text layout/normal, source/AST bans on OCR and alternate parsers, Phase 0 constant asserts
- `infrastructure/scripts/verify_pdf_extraction.py`: in scope - diagnostic imports `extract_modes`, `is_meaningful_text`, `measure`, `MEANINGFUL_TEXT_RULE`, `NO_EXTRACTABLE_TEXT`, `PdfMalformedError` from `app.services.pdf_extraction`; no local marker/threshold/`PdfReader` definitions; retains digital aggregate (>=4/5), image-only rejection, and `PYPDF_COMPATIBILITY=PASS`
- `backend/pyproject.toml`: dependency check - `pypdf==6.14.2` pin present
- `backend/tests/fixtures/cv/`: dependency check - five digital + `image_only_cv.pdf` present
- Ownership scan: marker constants and `PdfReader(` only defined/used in production owner; tests import/assert; diagnostic has no local copies; no tesseract/OCR implementation under backend or infrastructure (ban lists in tests only)

## Validations Reviewed
- Command/check: `Set-Location backend; python -m pytest tests/unit/test_pdf_extraction.py -q`
- Required: yes
- Reported result: passed (24 passed)
- Rerun result: passed (24 dots / exit 0)
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: `python infrastructure/scripts/verify_pdf_extraction.py`
- Required: yes
- Reported result: passed (`PYPDF_COMPATIBILITY=PASS`, digital 5/5, image_only=NO_EXTRACTABLE_TEXT, pypdf 6.14.2)
- Rerun result: passed (exit 0; digital_pass=5/5; non-ws 421/422/330/534/340; image 0/0; ends with `PYPDF_COMPATIBILITY=PASS`)
- Status: passed
- Notes: A2 independent rerun confirmed; Phase 0 non-ws counts match A1 report

- Command/check: `Set-Location backend; python -m ruff check app/services/pdf_extraction.py tests/unit/test_pdf_extraction.py ../infrastructure/scripts/verify_pdf_extraction.py; python -m mypy app`
- Required: yes
- Reported result: passed
- Rerun result: passed (ruff All checks passed; mypy Success: no issues found in 54 source files)
- Status: passed
- Notes: A2 independent rerun confirmed

- Command/check: ownership search `MIN_NON_WHITESPACE_CHARS|IDENTITY_MARKERS|EXPERIENCE_MARKERS|SKILLS_MARKERS|ocr|tesseract|PdfReader` under backend and infrastructure/scripts
- Required: yes
- Reported result: passed (one quality-rule owner, pypdf-only, no OCR implementation)
- Rerun result: passed (workspace search tools)
- Status: passed
- Notes: Single definition site for markers/threshold and PdfReader in `app.services.pdf_extraction`; diagnostic reuses via import; OCR mentions are denial-only or test ban lists

## Acceptance Review
- Task acceptance: All five digital fixtures preserve recorded gate behavior; raster-only returns NO_EXTRACTABLE_TEXT with no OCR path
- Status: satisfied
- Evidence: unit tests parametrize all five digital CVs as meaningful with page_count=1; image_only failure_code=NO_EXTRACTABLE_TEXT and 0 non-ws; diagnostic 5/5 + image_only=NO_EXTRACTABLE_TEXT; source/AST bans OCR/alternate parsers

- Task acceptance: Maximum-page decision can be made from parsed page count before final attachment row/file creation
- Status: satisfied
- Evidence: `parse_page_count` and `PdfTextExtraction.page_count` expose page count without requiring public raw-text contracts; unit test asserts page_count == 1 and <= 10 (MAX_PDF_PAGES surface)

- Task acceptance: Production and diagnostic share one meaningful-text implementation; no threshold/marker copy or alternate PDF parser
- Status: satisfied
- Evidence: diagnostic imports rule + extraction from production owner only; ownership scan shows single definition site; no alternate parsers introduced

## Implementation Reality
- Real pypdf digital-text extraction (normal + layout) and shared quality rule; not stubs or hardcoded fixture success
- Malformed paths raise `PdfMalformedError` with stable `MALFORMED_PDF`
- Image-only path yields empty extraction and stable `NO_EXTRACTABLE_TEXT` without OCR

## Architecture Alignment
- One production owner under `app.services.pdf_extraction` shared by diagnostic
- Raw text documented as transient service-private data; no public contract serialization in this module
- `MAX_PDF_PAGES` enforcement correctly deferred to later upload service using `parse_page_count` / page_count
- In-scope file set only for 01D implementation (plus report)

## Hardcoding Review
- No overfitting of fixture filenames or gold non-ws counts into production logic
- Marker lists and threshold match Phase 0 proven rule; tests verify constants and behavior, not fake success

## Report Accuracy
- A1 status complete, file list, validation claims (24 tests, diagnostic PASS, ruff/mypy, ownership), and acceptance mapping match repository evidence
- Shell `rg` unavailable note is credible; equivalent search confirmed

## Progress Tracking
- Selected task checkbox before review: unchecked
- Checkbox updated by reviewer: yes
- Checkbox final state: checked
- Sibling checkboxes: not modified by this review
- Batch status updated by reviewer: no

## Issues

### Blocking
- None

### Major
- None

### Minor
- Working tree also contains untracked 01A/01B/01C artifacts and execution/review docs; not attributed to 01D and not scope-violating for this review.

## Decision
- Accept selected task: yes
- Repair required: no
- Can next task proceed: yes
- Batch can be marked complete by A2: no
- A3 can rerun: no
- Next action: close_task

## Repair Instructions
- None
