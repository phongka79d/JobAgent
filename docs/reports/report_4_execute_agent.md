---

# Task Execution Report - 01A

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
orchestrated

## Batch
Batch01 - Profile Domain and Extraction Foundations

## Task
01A - Define the exact Candidate Profile, Skill, Preference, and Draft contracts

## Status
complete

## Selected Scope
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01A
- Task title: Define the exact Candidate Profile, Skill, Preference, and Draft contracts
- Files allowed / repair scope: `backend/app/schemas/profile.py`, `backend/app/schemas/skills.py`, `backend/tests/unit/test_profile_schemas.py`

## Source of Truth Used
- `docs/plans/Plan_4.md` > §7.1 Profile and skill schemas
- `docs/plans/Master_plan.md` > §7.1 Shared skill contract
- `docs/plans/Master_plan.md` > §7.2 Candidate Profile
- `docs/plans/Master_plan.md` > §7.3 Job Preferences

## Supplemental Documents Used
- README.md (project context)
- Existing schema style from `backend/app/schemas/common.py`, `tools.py`, `chat.py`
- ORM JSON ownership in `backend/app/db/models/profiles.py`

## Dependency and User Action Check
- Dependencies: Existing `backend/app/schemas/common.py` StrictModelConfig — satisfied
- User Action: None

## Files Inspected Before Editing
- `backend/app/schemas/common.py` (StrictModelConfig)
- `backend/app/schemas/tools.py`, `chat.py`, `health.py` (strict BaseModel patterns)
- `backend/app/db/models/profiles.py` (ORM JSON columns profile_json/draft_json/preferences_json)
- `backend/tests/unit/test_tool_result.py`, `test_attachment_profile_models.py`
- Plan_4.md §7.1 and Master_plan.md §7.1–7.3

## Completed Work
- Added `SkillRef` shared identity contract in `backend/app/schemas/skills.py` with `parse_skill_ref`.
- Added profile-domain contracts in `backend/app/schemas/profile.py`:
  `CandidateSkill`, `ExperienceItem`, `EducationItem`, `LanguageItem`,
  `CandidateProfile`, `JobPreferences`, `ProfileDraftPayload`, plus enum
  Literals and `parse_candidate_profile` / `parse_job_preferences` /
  `parse_profile_draft_payload` boundary helpers.
- Both confidence fields (`CandidateSkill.confidence`,
  `CandidateProfile.extraction_confidence`) constrained with `Field(ge=0, le=1)`.
- Strict `extra="forbid"` via shared `StrictModelConfig`; no ORM/provider/fs/graph/route/agent imports in schema modules.
- Module docstring documents the validated-model boundary for later
  `profile_json` / `draft_json` / `preferences_json` writers.
- Added focused unit tests for exact fields, nullability, enums, confidence
  bounds, unknown-field rejection, evidence shape, nested validation,
  fact/preference separation, correction/exclusion preservation, JSON
  round-trip, and pure-schema import hygiene.

## Key Implementation Decisions
- `SkillRef` lives alone in `skills.py` for reuse by later Job skill contracts;
  `CandidateSkill` and remaining profile models live in `profile.py`.
- `end_date_text` typed as `str | None`; Master’s `str | present | None` is
  free-form text where `"present"` is the conventional current-role value.
- Pydantic model names intentionally match Master contract names and coexist
  with distinct SQLAlchemy row types under `app.db.models.profiles`.

## Files Created or Modified
- `backend/app/schemas/skills.py` (created)
- `backend/app/schemas/profile.py` (created)
- `backend/tests/unit/test_profile_schemas.py` (created)

## Tests or Validations Run
- command/check: `Set-Location backend; python -m pytest tests/unit/test_profile_schemas.py -q`
- required: yes
- result: passed
- evidence or reason: 29 passed

- command/check: `Set-Location backend; python -m ruff check app/schemas/profile.py app/schemas/skills.py tests/unit/test_profile_schemas.py; python -m mypy app`
- required: yes
- result: passed
- evidence or reason: ruff “All checks passed!”; mypy “Success: no issues found in 50 source files”

- command/check: search `profile_json|draft_json|preferences_json|CandidateProfile|ProfileDraftPayload` under `backend/app` and `backend/tests`
- required: yes
- result: passed
- evidence or reason: Pydantic ownership is `app.schemas.profile` (+ `SkillRef` in `app.schemas.skills`); ORM JSON columns remain in `app.db.models.profiles` with seed empty-preferences write only; no competing Pydantic profile/draft contract or service JSON writer exists yet. Tests cover schema contracts and ORM metadata separately.

## Acceptance Check
- condition: Model fields and allowed enum values exactly match Master contracts; unknown fields and out-of-range confidence fail
- status: satisfied
- evidence: field-set tests, enum get_args tests, confidence ge/le rejection, extra=forbid tests

- condition: Complete `ProfileDraftPayload` round-trips through JSON without merging profile facts into Job Preferences or losing correction/exclusion fields
- status: satisfied
- evidence: `test_profile_draft_payload_json_round_trip_preserves_separation`; `source=user_correction` and `excluded=true` preserved; preferred_locations not populated from CV city in summary

- condition: No ORM, provider, filesystem, graph, route, or Agent behavior in schema modules
- status: satisfied
- evidence: module contents and `test_schema_modules_have_no_orm_or_io_imports`

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: mode is orchestrated; A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files: `backend/app/schemas/skills.py`, `backend/app/schemas/profile.py`, `backend/tests/unit/test_profile_schemas.py`
- validations to rerun: the three required checks above
- risk areas: name overlap with ORM `CandidateProfile`/`JobPreferences` (different modules; docstrings clarify); later services must import from `app.schemas.profile` for JSON validation
- next task readiness: can_review
- JSON writers inventory: seed writes empty `preferences_json` shape only; no profile/draft service writers yet — boundary documented for Batch01+ services

---

# Task Execution Report - 01B

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
orchestrated

## Batch
Batch01 - Profile Domain and Extraction Foundations

## Task
01B - Create the authoritative approved taxonomy and sole deterministic skill normalizer

## Status
complete

## Selected Scope
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01B
- Task title: Create the authoritative approved taxonomy and sole deterministic skill normalizer
- Files allowed / repair scope: `infrastructure/neo4j/skills_seed.yaml`, `backend/tests/fixtures/skills_seed.yaml`, `backend/app/services/skill_normalization.py`, `backend/tests/unit/test_skill_normalization.py`

## Source of Truth Used
- `docs/plans/Plan_4.md` > §6 Target Directory Structure
- `docs/plans/Plan_4.md` > §7.2 Skill normalization ownership
- `docs/plans/Master_plan.md` > §8.4 Graph safety rules
- `docs/plans/Master_plan.md` > §9 Skill Normalization

## Supplemental Documents Used
- README.md (project context)
- `backend/app/schemas/skills.py` (01A SkillRef)
- `backend/app/core/settings.py` (`repo_root()`)
- Demo CV fixtures under `backend/tests/fixtures/cv/` (skill names for production proposal only)
- Phase 0 meaningful-text skill markers (python, typescript, sql, react, docker, fastapi)
- User approval: option 1 — approve proposed production taxonomy as-is (envelope `USER_APPROVAL`)

## Dependency and User Action Check
- Dependencies: (01A) SkillRef — satisfied (`backend/app/schemas/skills.py` present and accepted path)
- User Action: **satisfied** — user explicitly approved option 1: production taxonomy exactly as proposed (all 18 skills + all 4 RELATED_TO edges/weights/source); no edits or substitutes
- Prior Blocked Condition: `BLOCKED_BY_USER_ACTION` — resolved by user approval; production seed written

## Files Inspected Before Editing
- `backend/app/schemas/skills.py`, `backend/app/schemas/profile.py` (SkillRef / CandidateSkill)
- `backend/app/core/settings.py` (`repo_root`)
- `backend/app/services/skill_normalization.py` (existing sole normalizer from prior 01B work)
- `backend/tests/fixtures/skills_seed.yaml` (test-only fixture; unchanged)
- `backend/tests/unit/test_skill_normalization.py` (existing tests; unchanged)
- `infrastructure/neo4j/` (was empty except `.gitkeep`; production seed written on unblock)
- Plan_4 §7.2 and Master §8.4 / §9
- Existing 01B report proposal tables (approved as-is)

## Completed Work
- Confirmed no existing application skill normalizer, no backend YAML dependency (prior blocked run).
- Implemented sole loader/normalizer in `backend/app/services/skill_normalization.py` (prior blocked run; reused on unblock):
  - JSON-compatible YAML parse (full-line `#` comments stripped, then stdlib `json.loads`)
  - Unicode NFKC, whitespace collapse, casefold, separator/punctuation normalization
  - Approved alias resolution via comparison fingerprints
  - Deterministic unknown `canonical_key` derivation; empty aliases; `category=None`; no invented RELATED_TO
  - Collision validation (duplicate keys/aliases, invalid endpoints/weights, self-loops, duplicate edges)
  - Canonical ordering of skills and relationships
  - `normalize_candidate_skill` preserves confidence/proficiency/years/source/excluded/evidence
  - Production path constant: `infrastructure/neo4j/skills_seed.yaml` via `repo_root()`; tests inject fixture through the same `from_path` / parser path
- Created test-only fixture `backend/tests/fixtures/skills_seed.yaml` (no external approval required; unchanged on unblock).
- Added focused unit tests `backend/tests/unit/test_skill_normalization.py` (20 cases; unchanged on unblock).
- **Wrote** user-approved production taxonomy to `infrastructure/neo4j/skills_seed.yaml` with exactly the approved 18 skills and 4 RELATED_TO edges (no invented aliases/categories/relationships).
- Verified `SkillNormalizer.production()` loads 18 skills and 4 seed relationships (`python→fastapi`, `typescript→react`, `sql→postgresql`, `docker→kubernetes`, weight 0.6, source `seed`).

## Approved Production Taxonomy (USER APPROVED — option 1 as-is)

Grounded only in synthetic demo CV skill lists (digital_cv_01–05) and Phase 0 skill markers. Aliases are orthographic/synonym forms only — not LLM-invented semantic expansions. RELATED_TO weights use the Plan 6 seed default `0.6`. Written verbatim to production seed after user approval.

### Approved skills

| canonical_key | display_name | aliases | category |
|---|---|---|---|
| python | Python | python3, py | language |
| typescript | TypeScript | ts | language |
| sql | SQL | _(none)_ | data |
| react | React | reactjs, react.js | framework |
| docker | Docker | _(none)_ | devops |
| postgresql | PostgreSQL | postgres | data |
| fastapi | FastAPI | fast api | framework |
| neo4j | Neo4j | _(none)_ | data |
| pytest | pytest | _(none)_ | testing |
| kubernetes | Kubernetes | k8s | devops |
| terraform | Terraform | _(none)_ | devops |
| aws | AWS | amazon web services | cloud |
| spark | Apache Spark | pyspark | data |
| airflow | Apache Airflow | _(none)_ | data |
| dbt | dbt | _(none)_ | data |
| css | CSS | _(none)_ | frontend |
| jest | Jest | _(none)_ | testing |
| graphql | GraphQL | _(none)_ | api |

### Approved RELATED_TO edges

| from | to | weight | source |
|---|---|---|---|
| python | fastapi | 0.6 | seed |
| typescript | react | 0.6 | seed |
| sql | postgresql | 0.6 | seed |
| docker | kubernetes | 0.6 | seed |

## Key Implementation Decisions
- Stdlib JSON after comment strip — no new YAML dependency; ponytail documented in module/fixture/production seed headers.
- Comparison fingerprint strips separators so `React.JS` / `react-js` / `React JS` match one seed entry.
- Unknown keys use underscore-joined lowercased alnum tokens (`Neo4j Graph` → `neo4j_graph` when not a seed label; seed `neo4j` resolves when input fingerprints to that entry).
- Production seed written only after explicit user approval of the proposed table (option 1, as-is).
- Unblock reused existing normalizer, test fixture, and unit tests without modification.

## Files Created or Modified
- `backend/app/services/skill_normalization.py` (created on initial 01B run; unchanged on unblock)
- `backend/tests/fixtures/skills_seed.yaml` (created on initial 01B run; unchanged on unblock)
- `backend/tests/unit/test_skill_normalization.py` (created on initial 01B run; unchanged on unblock)
- `infrastructure/neo4j/skills_seed.yaml` (created on unblock with user-approved taxonomy only)
- `docs/reports/report_4_execute_agent.md` (01B block updated)

## Tests or Validations Run
- command/check: `Set-Location backend; python -m pytest tests/unit/test_skill_normalization.py -q`
- required: yes
- result: passed
- evidence or reason: 20 passed (rerun after production seed write)

- command/check: `Set-Location backend; python -m ruff check app/services/skill_normalization.py tests/unit/test_skill_normalization.py; python -m mypy app`
- required: yes
- result: passed
- evidence or reason: ruff “All checks passed!”; mypy “Success: no issues found in 51 source files” (rerun after production seed write)

- command/check: search `skills_seed|canonical_key|Unicode|unicodedata|RELATED_TO|aliases` under `backend/app`, `backend/tests`, `infrastructure/neo4j`
- required: yes
- result: passed
- evidence or reason: Sole normalizer/parser remains `app.services.skill_normalization`; production taxonomy is only `infrastructure/neo4j/skills_seed.yaml` (18 skills + 4 relationships); test fixture remains the smaller inject path; graph constraints mention Skill.canonical_key uniqueness only (no second normalizer). Unrelated status “aliases” hits in common/sse/tool_result are Plan 3 status vocabulary, not skill taxonomy.

- command/check: `SkillNormalizer.production()` load smoke (18 skills, 4 edges; alias samples k8s→kubernetes, postgres→postgresql)
- required: no (acceptance aid)
- result: passed
- evidence or reason: production path loads and normalizes approved aliases without inventing relationships for unknowns

## Acceptance Check
- condition: Production code loads only `infrastructure/neo4j/skills_seed.yaml` through the single service; tests inject smaller fixture via same parser
- status: satisfied
- evidence: `SkillNormalizer.production()` / `load_production_skill_taxonomy()` load production seed; `from_path` used by tests with fixture; single service module

- condition: Equivalent inputs resolve to one stable SkillRef; unknowns deterministic with no invented metadata/relationship
- status: satisfied
- evidence: unit tests for unicode/whitespace/case/punctuation/aliases/unknowns/repeats/relationships_for

- condition: Duplicate/colliding keys or aliases and invalid relationship endpoints/weights fail before use
- status: satisfied
- evidence: invalid-seed unit tests

- condition: No second normalizer, copied taxonomy, LLM-generated alias, or automatic related-skill edge
- status: satisfied
- evidence: single service module; fixture is test-only; production seed contains only user-approved rows

- condition: User-approved production taxonomy present
- status: satisfied
- evidence: option 1 approval applied; `infrastructure/neo4j/skills_seed.yaml` matches approved skills and RELATED_TO table exactly

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: mode is orchestrated; A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files (cumulative 01B): `backend/app/services/skill_normalization.py`, `backend/tests/fixtures/skills_seed.yaml`, `backend/tests/unit/test_skill_normalization.py`, `infrastructure/neo4j/skills_seed.yaml`
- unblock delta: only `infrastructure/neo4j/skills_seed.yaml` + this report block update
- validations to rerun: the three required checks above
- risk areas: taxonomy is deliberately small/demo-grounded; later graph seed consumers must load only this file through the single normalizer; do not expand aliases/edges without new user approval
- next task readiness: can_review

## Repair Log

### 2026-07-13 (user-action unblock resume)
- reason for repair: prior 01B status was `blocked` (`BLOCKED_BY_USER_ACTION`); user approved option 1 — proposed production taxonomy as-is (all skills + RELATED_TO edges)
- changes made: wrote `infrastructure/neo4j/skills_seed.yaml` with only the approved 18 skills and 4 RELATED_TO edges; left normalizer, fixture, and unit tests unchanged; updated this 01B report block to `complete`
- validations rerun: pytest `tests/unit/test_skill_normalization.py` (20 passed); ruff + mypy (passed); sole-owner search under `backend/app`, `backend/tests`, `infrastructure/neo4j` (passed); production load smoke (18 skills, 4 edges)
- outcome: acceptance satisfied; status `complete`; nextTaskReadiness `can_review`

---

# Task Execution Report - 01C

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
orchestrated

## Batch
Batch01 - Profile Domain and Extraction Foundations

## Task
01C - Implement focused attachment and profile repositories over the existing schema

## Status
complete

## Selected Scope
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01C
- Task title: Implement focused attachment and profile repositories over the existing schema
- Files allowed / repair scope: `backend/app/repositories/attachments.py`, `backend/app/repositories/profiles.py`, `backend/tests/integration/test_cv_api.py`, `backend/tests/integration/test_profile_approval.py`

## Source of Truth Used
- `docs/plans/Plan_4.md` > §6 Target Directory Structure
- `docs/plans/Plan_4.md` > §7.3 Upload validation and exact-hash state handling
- `docs/plans/Plan_4.md` > §7.6 Approval decisions and atomic commit
- `docs/plans/Master_plan.md` > §6.2 Application table schemas (attachments, candidate_profile, profile_drafts, job_preferences)
- `docs/plans/Master_plan.md` > §6.3 Foreign-key and deletion rules

## Supplemental Documents Used
- README.md (project context)
- Existing repository patterns: `backend/app/repositories/agent_runs.py`, `chat_messages.py`, `tool_executions.py`
- ORM models: `backend/app/db/models/attachments.py`, `profiles.py`
- Session helpers: `backend/app/db/session.py`, `backend/tests/support/db_migration.py`
- Integration style from `backend/tests/integration/test_chat_persistence.py`, `test_tool_replay.py`

## Dependency and User Action Check
- Dependencies: (01A) complete; Plan 2 schema at Alembic head `0001_initial_schema` — satisfied
- User Action: None

## Files Inspected Before Editing
- `backend/app/db/models/attachments.py` (state constants, CHECKs, partial unique active)
- `backend/app/db/models/profiles.py` (singleton IDs, FKs, JSON columns)
- `backend/app/repositories/agent_runs.py`, `tool_executions.py`, `chat_messages.py` (session ownership, transition maps, error style, no-commit)
- `backend/app/db/session.py`, `backend/tests/support/db_migration.py`
- `backend/tests/integration/test_chat_persistence.py`, `test_database_contract.py`
- Plan_4 §6 / §7.3 / §7.6 and Master §6.2 / §6.3

## Completed Work
- Implemented `backend/app/repositories/attachments.py`:
  - Reads: `get_by_id`, `get_by_file_hash` (exact hash), `get_active`
  - Create: `create_staged` with optional page_count
  - Explicit transitions only: `mark_active` (staged→active, requires page_count), `mark_failed` (staged→failed + failure_code), `retry_as_staged` (failed→staged, clears failure_code)
  - `delete` for unreferenced rows (no filesystem touch)
  - Invalid transitions raise `InvalidAttachmentTransitionError` without mutating state
  - No commit/rollback; uses existing state constants and `utc_now`
- Implemented `backend/app/repositories/profiles.py`:
  - Singleton active profile get/upsert (`id=active`)
  - Singleton draft get/upsert/delete (`id=current`)
  - Singleton job preferences get/upsert (`id=active`)
  - No JSON-shape validation (service-owned); no commit; fixed singleton ID constants only
- Added migrated-SQLite integration tests:
  - `tests/integration/test_cv_api.py` — hash/state reads, allowed/forbidden transitions, timestamps, missing rows, unique hash / single-active constraints, no-commit ownership
  - `tests/integration/test_profile_approval.py` — profile/draft/preferences singleton CRUD, FK RESTRICT, cascade draft delete, timestamps, no-commit, no Pydantic/IO in repository source
- Confirmed migration/schema paths unchanged; Plan 2/3 schema tests still pass

## Key Implementation Decisions
- Mirror tool_execution/agent_run repository style: module-level async functions, base + typed errors, explicit `_ALLOWED_TRANSITIONS` map, flush-only mutations
- Attachment repository does not transition away from `active` (removal is delete after service repoint)
- Profile repository stores caller-provided dict JSON without re-validating 01A Pydantic contracts (later services own validation boundary)
- Test files named for later API/approval growth but currently repository-focused only (per task Files list)

## Files Created or Modified
- `backend/app/repositories/attachments.py` (created)
- `backend/app/repositories/profiles.py` (created)
- `backend/tests/integration/test_cv_api.py` (created)
- `backend/tests/integration/test_profile_approval.py` (created)
- `docs/reports/report_4_execute_agent.md` (01C block appended)

## Tests or Validations Run
- command/check: `Set-Location backend; python -m pytest tests/integration/test_cv_api.py tests/integration/test_profile_approval.py -q`
- required: yes
- result: passed
- evidence or reason: 32 passed

- command/check: `Set-Location backend; python -m pytest tests/unit/test_attachment_profile_models.py tests/integration/test_database_contract.py tests/integration/test_migrations.py -q`
- required: yes
- result: passed
- evidence or reason: 24 passed (schema/migration contracts unchanged)

- command/check: `Set-Location backend; python -m ruff check app/repositories/attachments.py app/repositories/profiles.py tests/integration/test_cv_api.py tests/integration/test_profile_approval.py; python -m mypy app`
- required: yes
- result: passed
- evidence or reason: ruff "All checks passed!"; mypy "Success: no issues found in 53 source files"

- command/check: `git diff -- backend/migrations backend/app/db/models`
- required: yes
- result: passed
- evidence or reason: empty diff — no Plan 4 migration or schema drift

## Acceptance Check
- condition: Only existing four profile-family tables; preserve singleton IDs, attachment state constants, UUIDs, UTC updates
- status: satisfied
- evidence: repositories import only Attachment/CandidateProfile/ProfileDraft/JobPreferences and existing constants; create_staged uses UUID defaults; transitions set `updated_at = utc_now()`; tests assert singleton IDs and UUID ids

- condition: Exact-hash lookup and each permitted attachment transition are explicit; invalid transitions do not mutate state
- status: satisfied
- evidence: `get_by_file_hash`; `mark_active` / `mark_failed` / `retry_as_staged`; parametrized forbidden-transition tests assert state/failure_code/page_count/updated_at unchanged

- condition: Repositories neither commit/rollback nor touch files, provider clients, checkpoints, routes, Neo4j, or unvalidated raw CV text
- status: satisfied
- evidence: source inspection tests; flush-only uncommitted isolation tests; no storage/provider imports

- condition: Migration/schema files remain unchanged
- status: satisfied
- evidence: `git diff -- backend/migrations backend/app/db/models` empty; Plan 2 contract tests pass

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: mode is orchestrated; A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files: `backend/app/repositories/attachments.py`, `backend/app/repositories/profiles.py`, `backend/tests/integration/test_cv_api.py`, `backend/tests/integration/test_profile_approval.py`
- validations to rerun: the four required checks above
- risk areas: services must still own cross-row approval ordering (repoint profile before delete old active), Pydantic JSON validation before upsert, and filesystem cleanup; repositories intentionally do not validate profile/draft JSON shape
- next task readiness: can_review

---

# Task Execution Report - 01D

## Source Task File
docs/tasks/task_4.md

## Report File
docs/reports/report_4_execute_agent.md

## Mode
orchestrated

## Batch
Batch01 - Profile Domain and Extraction Foundations

## Task
01D - Promote the proven pypdf extraction and meaningful-text rule into one production owner

## Status
complete

## Selected Scope
- Batch: Batch01 - Profile Domain and Extraction Foundations
- Task ID: 01D
- Task title: Promote the proven pypdf extraction and meaningful-text rule into one production owner
- Files allowed / repair scope: `backend/app/services/pdf_extraction.py`, `backend/tests/unit/test_pdf_extraction.py`, `infrastructure/scripts/verify_pdf_extraction.py`

## Source of Truth Used
- `docs/plans/Plan_4.md` > §7.3 Upload validation and exact-hash state handling
- `docs/plans/Plan_4.md` > §7.4 PDF/profile extraction
- `docs/plans/Plan_4.md` > §9 Verification & Testing Plan
- `docs/feasibility/phase_0_report.md` > ## pypdf extraction gate

## Supplemental Documents Used
- README.md (project context; Phase 0 diagnostic command)
- Existing Phase 0 diagnostic `infrastructure/scripts/verify_pdf_extraction.py` (pre-refactor constants/helpers)
- Existing fixtures `backend/tests/fixtures/cv/`
- `backend/app/services/skill_normalization.py` (service ownership style)
- `backend/pyproject.toml` (`pypdf==6.14.2` pin)

## Dependency and User Action Check
- Dependencies: Existing Phase 0 synthetic CV fixtures and pypdf pin — satisfied
- User Action: None

## Files Inspected Before Editing
- `infrastructure/scripts/verify_pdf_extraction.py` (owned rule, extract_modes, diagnostic output)
- `docs/feasibility/phase_0_report.md` (recorded gate outcomes and rule text)
- `backend/tests/fixtures/cv/` (five digital + image_only fixtures)
- `backend/pyproject.toml` (pypdf pin)
- `backend/app/core/settings.py` (MAX_PDF_PAGES surface for upload later)
- `backend/app/services/skill_normalization.py` (module ownership pattern)
- Search of backend + infrastructure/scripts for PdfReader / markers / OCR callers (only diagnostic prior to this task)

## Completed Work
- Created `backend/app/services/pdf_extraction.py` as sole production owner of:
  - Exact Phase 0 constants: `MIN_NON_WHITESPACE_CHARS`, `IDENTITY_MARKERS`, `EXPERIENCE_MARKERS`, `SKILLS_MARKERS`, `MEANINGFUL_TEXT_RULE`
  - Normalization/measure helpers and `is_meaningful_text`
  - pypdf-only `PdfReader` extraction (normal + layout), `parse_page_count`, `extract_modes`, `extract_pdf_text`
  - Stable codes `NO_EXTRACTABLE_TEXT` / `MALFORMED_PDF` and `PdfMalformedError`
  - Transient `PdfTextExtraction` (layout-preferred `preferred_text`; no public logging/persistence of raw text)
- Added focused unit tests covering all five digital fixtures, image-only `NO_EXTRACTABLE_TEXT`, malformed inputs, page counts, normal/layout outcomes, rule thresholds, and AST/source bans on OCR/alternate parsers
- Refactored Phase 0 diagnostic to import rule + extraction from the production owner (no local threshold/marker/`PdfReader` copy); preserved per-fixture lines, aggregate threshold (>=4/5), and `PYPDF_COMPATIBILITY=PASS` marker

## Key Implementation Decisions
- Single implementation of markers/threshold; diagnostic reuses via import only
- `parse_page_count` / `page_count` on extraction result enable MAX_PDF_PAGES decision before final attachment row/file creation
- Production prefers layout text when meaningful; gate success remains either-mode (Phase 0)
- Raw text fields documented as service-private transient data
- Diagnostic adds backend root to `sys.path` so checkout runs without relying solely on editable install

## Files Created or Modified
- `backend/app/services/pdf_extraction.py` (created)
- `backend/tests/unit/test_pdf_extraction.py` (created)
- `infrastructure/scripts/verify_pdf_extraction.py` (refactored to consume production owner)
- `docs/reports/report_4_execute_agent.md` (01D block appended)

## Tests or Validations Run
- command/check: `Set-Location backend; python -m pytest tests/unit/test_pdf_extraction.py -q`
- required: yes
- result: passed
- evidence or reason: 24 passed

- command/check: `python infrastructure/scripts/verify_pdf_extraction.py`
- required: yes
- result: passed
- evidence or reason: exit 0; digital_pass=5/5; image_only=NO_EXTRACTABLE_TEXT; ends with `PYPDF_COMPATIBILITY=PASS`; pypdf_version=6.14.2; non-ws counts match Phase 0 table (421/422/330/534/340; image 0/0)

- command/check: `Set-Location backend; python -m ruff check app/services/pdf_extraction.py tests/unit/test_pdf_extraction.py ../infrastructure/scripts/verify_pdf_extraction.py; python -m mypy app`
- required: yes
- result: passed
- evidence or reason: ruff "All checks passed!"; mypy "Success: no issues found in 54 source files"

- command/check: `rg -n "MIN_NON_WHITESPACE_CHARS|IDENTITY_MARKERS|EXPERIENCE_MARKERS|SKILLS_MARKERS|ocr|tesseract|PdfReader" backend infrastructure/scripts` (shell `rg` unavailable; equivalent Python/path search used)
- required: yes
- result: passed
- evidence or reason: marker constants and `PdfReader` defined only in `backend/app/services/pdf_extraction.py`; tests import/assert them; diagnostic has no local marker/`PdfReader` definitions; no tesseract implementation; OCR mentions are denial-only

## Acceptance Check
- condition: All five digital fixtures preserve recorded gate behavior; raster-only fixture returns NO_EXTRACTABLE_TEXT with no OCR path
- status: satisfied
- evidence: unit tests parametrize all digital fixtures as meaningful; image_only failure_code=NO_EXTRACTABLE_TEXT with 0 non-ws; diagnostic 5/5 + image_only=NO_EXTRACTABLE_TEXT; source bans OCR/alternate parsers

- condition: Maximum-page decision can be made from parsed page count before final attachment row/file creation
- status: satisfied
- evidence: `parse_page_count` and `PdfTextExtraction.page_count` expose page count without requiring public raw-text contracts; unit test covers page_count == 1 for fixtures

- condition: Production and diagnostic share one meaningful-text implementation; no threshold/marker copy or alternate PDF parser
- status: satisfied
- evidence: diagnostic imports `is_meaningful_text`, `extract_modes`, `measure`, `MEANINGFUL_TEXT_RULE`, `NO_EXTRACTABLE_TEXT` from `app.services.pdf_extraction`; ownership scan shows single definition site for markers and PdfReader

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: mode is orchestrated; A1 must not update checkboxes or batch status

## Notes for Review Agent
- changed files: `backend/app/services/pdf_extraction.py`, `backend/tests/unit/test_pdf_extraction.py`, `infrastructure/scripts/verify_pdf_extraction.py`
- validations to rerun: the four required checks above
- risk areas: later upload service (02A) must call `parse_page_count` / `extract_pdf_text` and enforce MAX_PDF_PAGES/size/magic without reimplementing the quality rule or logging raw text; `MALFORMED_PDF` code is stable for service mapping
- next task readiness: can_review
