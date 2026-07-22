# JobAgent Plan 16 Execution Tasks

## Purpose

Translate `docs/plans/Plan_16.md` into the mandatory implementation and evidence
chain for profession-neutral CV/JD skill extraction, one persisted atomic-skill
truth, exact SQLite/Neo4j selected-relationship integrity, and a readable
selected-JD compatibility map. Preserve the one-active-Candidate architecture,
explicit approval/evaluation boundaries, fixed scoring formula, and rebuildable
Neo4j model.

## Project Context Notes

- Root `README.md` was read before task derivation. JobAgent is a local,
  single-user React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, and ShopAIKey
  application with exactly three loopback-only Compose services and one ignored
  root `.env`.
- README identifies Plan 15 as the current guarded-JD/re-extraction baseline.
  Runtime source and fresh tests remain authoritative; this task must not infer
  implementation state from prose alone.
- The amended Master Version 2.2 and contiguous Plans 1-16 passed a fresh
  portfolio review with all hard gates passing. This file authorizes only the
  bounded Plan 16 execution chain; it does not broaden product scope.
- Current root Git status contains the authorized planning changes to
  `Master_plan.md`, `Plan_15.md`, and `Plan_16.md`. Execution must preserve them
  and must not rewrite unrelated user changes.
- `frontend/AGENTS.md` requires Astryx CLI discovery before UI edits, Astryx
  components for layout, token-based styling, and no invented component props.
- The user explicitly permits updating SQLite code and legacy tests if the root
  fix requires it. Plan 16 currently requires no schema migration or direct
  rewrite of live rows: old records upgrade through explicit CV reprocess,
  retained-JD re-extract, and Neo4j rebuild actions.
- Test fixtures and diagnostics use repository-authored synthetic data. Real CV
  or JD content, identifiers, evidence, screenshots, stores, credentials,
  prompts, provider payloads, and graph dumps must not enter Git or reports.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_16.md`.
- Supporting: `docs/plans/Master_plan.md` Version 2.2 and
  `docs/plans/Plan_15.md` handoff.
- Context only: `README.md`, `frontend/AGENTS.md`, current source/tests,
  `infrastructure/docker-compose.yml`, and existing acceptance documents.

### Source Section Index

- `Plan_16.md` > `## Objective`, `## Master Requirement Coverage`, `## Scope`,
  and `## Out of Scope` -> mandatory outcomes, ownership, and exclusions.
- `Plan_16.md` > `### Profession-neutral digital-text gate` -> PDF acceptance
  rule and retained no-OCR failures.
- `Plan_16.md` > `### Bounded Candidate skill assertion contract` and
  `### Shared structural skill guard` -> all-section provider schema, source
  ownership, grounding, atomicity, aggregation, and bounded repair.
- `Plan_16.md` > `### Profession-neutral JD extraction` and `### Atomic
  normalization and matching parity` -> seventh JD issue code, optional-seed
  behavior, removal of grouped repair, and evaluation version invalidation.
- `Plan_16.md` > `### SQLite/Neo4j selected relationship integrity`,
  `### Backend-owned compatibility classification`, and `### Read-only API and
  raw technical graph` -> exact derived-state gate, map DTO, endpoint, and raw
  graph display metadata.
- `Plan_16.md` > `### Frontend state, map, and technical mode` -> sole saved-JD
  selection/cache owner, accessible default map, and retained technical canvas.
- `Plan_16.md` > `### Rollout and existing data`, `## Implementation`,
  `## Verification`, and `## Completion Contract` -> test-first order, explicit
  upgrade path, full gates, Docker/browser evidence, and final boundaries.

### Approved Architecture and Constraints

- Accept sufficiently long digital PDF text using Unicode content bounds, not
  identity, role, heading, language, profession, or named-skill markers.
- Extract Candidate skills from all validated `CVDocument` entries through one
  bounded provider/guard stage. Persist only atomic, source-owned, grounded
  assertions; never parse headings or delimiters locally.
- Preserve `SkillNormalizer.normalize_name()` as the sole identity owner.
  Unknown skills remain first-class; the production seed is optional curated
  aliases/relatedness, never a whitelist, parser, formatter, or fixture repair.
- Matching, embedding text, explanations, direct sync, rebuild, API, and UI
  consume the approved stored skill collections without downstream expansion.
- Keep Plan 15 provider, one-repair, exact-dedupe, re-extraction CAS, failure,
  and explicit no-auto-evaluation contracts.
- SQLite remains authoritative. The selected map is withheld when exact active
  Candidate or selected Job skill relationships differ in Neo4j; reads never
  repair, synchronize, evaluate, or call the provider.
- `useSavedJobsState` remains the sole `selectedJobId` and map-cache owner.
  React renders backend labels/evidence/statuses and contains no profession,
  skill, alias, acronym, category, or canonical-key display dictionary.
- No database migration, persisted schema field, model/provider/dependency,
  Agent/tool, scoring change, worker/queue, global ontology, automatic
  evaluation, multi-candidate support, or unrelated redesign is authorized.
- A1 and A2 do not update task checkboxes or commit. A3 and commit readiness are
  orchestration responsibilities.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Profession-neutral PDF gate and authoritative all-section Candidate skill projection | (01A), (01B) | Approved Plan 15 baseline |
| Batch02 | Profession-neutral JD guard plus one persisted atomic-skill matching contract | (02A), (02B) | Batch01 shared guard |
| Batch03 | Exact selected graph integrity and backend compatibility-map API | (03A), (03B) | Batch01-Batch02 |
| Batch04 | Sole-owner frontend map state and accessible default/technical views | (04A), (04B) | Batch03 |
| Batch05 | Cross-profession diagnostic, rollout documentation, and release evidence | (05A) | Batch01-Batch04 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a1/<batch-id>/<task-id>/A1-a<attempt>.md`
  report.
- A2 reviews one executed task, writes only the assigned
  `.agent/<plan-id>/<run-id>/report/a2/<batch-id>/<task-id>/A2-a<attempt>.md`
  report, and the Orchestrator checks the canonical checkbox only after
  `ACCEPTED`.
- A3 runs only after every task in the selected batch has matching A1 evidence,
  A2 evidence, an Orchestrator `ACCEPTED` event, and a checked canonical task
  marker; it writes only
  `.agent/<plan-id>/<run-id>/report/a3/<batch-id>/A3-a<attempt>.md`.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Profession-Neutral Candidate Skill Truth

### Goal

Accept digital-text CVs from any profession and publish one guarded atomic skill
collection derived from all validated CV entries.

### Dependencies

- Approved Plan 15 baseline and current PDF/document/profile tests.
- Task order is (01A) then (01B); (01B) consumes the pure structural primitives
  established by (01A).

### Scope Boundary

- This batch owns only PDF meaningful-text validation, shared pure grounding and
  atomicity primitives, Candidate skill assertion orchestration, and directly
  required tests.
- It does not own JD grouping rules, matching, graph map/API, frontend, runtime
  data rewrite, or release diagnostics.

### Tasks

- [ ] (01A): Replace profession markers with a neutral PDF gate and shared pure skill primitives
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch01 - Profession-Neutral Candidate Skill Truth` > `(01A)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Profession-neutral digital-text gate`, `### Shared structural skill guard`, and `## Verification` rows `Pre-change RED` and `PDF/CV skills`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(01A)` -> execution authority
    - source-pdf: repository `docs/plans/Plan_16.md` > `### Profession-neutral digital-text gate` -> accepted/failure behavior
    - source-guard: repository `docs/plans/Plan_16.md` > `### Shared structural skill guard` -> reusable pure primitive boundary
    - owner-pdf: repository `backend/app/services/pdf_extraction.py` -> current text modes and marker gate
    - validation-pdf: repository `backend/tests/unit/test_pdf_extraction.py` -> existing PDF regression owner
  - Source Requirements:
    - Replace identity/software/skill marker families with the existing minimum non-whitespace count plus at least one Unicode letter or number after NFKC/whitespace normalization.
    - Preserve malformed, empty, short, punctuation-only, and image-only failures with no provider or OCR call.
    - Add pure containment, exact-approved-alias, heading comparison, structural compound, and sanitized issue helpers without profession tokens or side-effect imports.
  - Dependencies: None
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 300
    - timeout_seconds: 1800
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/pdf_extraction.py`, `backend/app/services/skill_assertion_guard.py`, `backend/tests/unit/test_pdf_extraction.py`, `backend/tests/unit/test_skill_assertion_guard.py`, synthetic files under `backend/tests/fixtures/cv/cross_profession/`
  - Allowed Files: the listed service/test/fixture paths only; exclude schemas, persistence, graph, API, frontend, seed, and runtime stores
  - Agent Work:
    1. Inspect current PDF modes/limits and guard utilities; add focused tests that fail for neutral professional text and missing shared primitives.
    2. Run the RED tests and confirm failures are caused by the old marker/absent-helper behavior.
    3. Implement the minimum neutral gate and pure reusable primitives, then run focused and existing PDF/guard tests green.
  - Output: Neutral digital-text acceptance and a side-effect-free shared structural helper module.
  - A1 Outcome: Synthetic digital CV text from unseeded professions passes while malformed/image/short inputs retain exact failures, and shared skill primitives have focused tests.
  - A2 Review Focus: Confirm real RED evidence, no profession dictionary, unchanged resource/no-OCR constraints, pure imports, and no scope leakage.
  - A3 Batch Evidence: P16-DOM-01 and the shared-guard foundation consumed by (01B) and (02A).
  - Acceptance:
    - Cross-profession text without prior markers passes both supported pypdf text-mode selection paths.
    - Empty, punctuation-only, below-threshold, malformed, and image-only fixtures fail exactly as before and make no provider call.
    - Shared primitives return sanitized structural results and contain no provider, DB, graph, API, logging, frontend, or named-profession logic.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_pdf_extraction.py tests/unit/test_skill_assertion_guard.py -q` -> PASS evidence: exit 0 and all focused cases pass; freshness: final attempt only
    - Required: `rg -n -i "engineer|developer|python|docker|technical skill|marketing|finance" app/services/pdf_extraction.py app/services/skill_assertion_guard.py` -> PASS evidence: no profession/skill marker branch; freshness: final diff
  - Blocked Condition: Missing usable synthetic PDF fixture tooling or a required root fix outside Allowed Files -> `BLOCKED_ENVIRONMENT` or `BLOCKED_SCOPE_CONFLICT`.
  - Files: `backend/app/services/pdf_extraction.py`, `backend/app/services/skill_assertion_guard.py`, `backend/tests/unit/test_pdf_extraction.py`, `backend/tests/unit/test_skill_assertion_guard.py`, `backend/tests/fixtures/cv/cross_profession/**`

- [ ] (01B): Make bounded all-section Candidate assertions the sole persisted CV skill producer
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch01 - Profession-Neutral Candidate Skill Truth` > `(01B)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Bounded Candidate skill assertion contract`, `### Shared structural skill guard`, and `### Rollout and existing data`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(01B)` -> execution authority
    - source-candidate: repository `docs/plans/Plan_16.md` > `### Bounded Candidate skill assertion contract` -> provider/guard/aggregation authority
    - owner-document: repository `backend/app/services/cv_document_projection.py` and `backend/app/services/profile_extraction.py` -> current projection/publication owners
    - owner-provider: repository `backend/app/services/cv_document_extraction.py` and `backend/app/services/provider_retry.py` -> structured invocation/retry patterns
    - validation-candidate: repository `docs/plans/Plan_16.md` > `## Verification` row `PDF/CV skills` -> focused gate
  - Source Requirements:
    - Read bounded source-ordered entries from every validated CV section and emit strict internal assertions with name, confidence, proficiency, years, evidence, and existing entry IDs.
    - Guard source ownership, evidence/name containment, heading-only labels, structural atomicity, and duplicates before normalization; allow at most one sanitized repair per batch.
    - Aggregate equal canonical keys deterministically and publish chunks/document/profile draft atomically only after the entire assertion stage succeeds.
    - Remove section-kind-only and delimiter/category/colon skill parsing from the old document projection.
  - Dependencies: (01A) accepted shared primitives
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/cv_skill_projection.py`, `backend/app/services/cv_document_projection.py`, `backend/app/services/profile_extraction.py`, `backend/app/services/profile_drafts.py`, `backend/tests/unit/test_cv_skill_projection.py`, `backend/tests/unit/test_cv_document_extraction.py`, `backend/tests/unit/test_profile_extraction.py`
  - Allowed Files: listed CV/profile services and their focused unit/integration tests plus synthetic golden fixture; exclude persisted schema/migration, JD, matching, graph/API, frontend, seed, and real data
  - Agent Work:
    1. Trace all callers and provider dependency-injection patterns; write RED tests for skills outside `kind='skills'`, grouped headings, punctuation, ownership, repair caps, aggregation, and all-or-nothing draft publication.
    2. Implement the strict internal models, bounded entry projection/invoker/guard orchestration, and deterministic aggregation using (01A) helpers.
    3. Delete the old blind parser and update publication callers; run focused document/profile/approval regressions green.
  - Output: `CandidateProfile.skills` is produced only by the accepted all-section assertion stage.
  - A1 Outcome: Candidate skills from any validated section persist atomically with grounded evidence, while headings/grouped rows and invalid batches never publish a draft.
  - A2 Review Focus: Verify one producer, bounded calls/repair, exact caller integration, no persisted schema change, and removal rather than coexistence of blind parsing.
  - A3 Batch Evidence: P16-CV-01 and P16-CV-02 with Candidate publication parity.
  - Acceptance:
    - Every accepted skill references existing entry evidence and is atomic before normalization.
    - Skills in summary, experience, project, certification context, or `other` sections are considered by the same provider boundary without treating headings/credentials as skills by themselves.
    - No local delimiter/category/colon parser or `kind='skills'`-only producer remains.
    - Any final schema/provider/guard failure leaves prior chunks/document/profile truth intact.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_skill_projection.py tests/unit/test_skill_assertion_guard.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py -q` -> PASS evidence: exit 0; freshness: final attempt only
    - Required: `rg -n "re\.split|normalize_grouped_name|kind == ['\"]skills['\"]" app/services/cv_document_projection.py app/services/cv_skill_projection.py` -> PASS evidence: no blind/section-only skill producer; freshness: final diff
  - Blocked Condition: Provider batching cannot cover an oversized entry without changing approved contracts, or a root fix needs persisted schema/migration -> `BLOCKED_SOURCE_CONFLICT` or `BLOCKED_SCOPE_CONFLICT`.
  - Files: `backend/app/services/cv_skill_projection.py`, `backend/app/services/cv_document_projection.py`, `backend/app/services/profile_extraction.py`, `backend/app/services/profile_drafts.py`, `backend/tests/unit/test_cv_skill_projection.py`, `backend/tests/unit/test_cv_document_extraction.py`, `backend/tests/unit/test_profile_extraction.py`, `backend/tests/integration/test_profile_approval.py`

## Mandatory Batch02 - Profession-Neutral JD and Matching Parity

### Goal

Apply the same source-grounded atomic-skill invariant to JD extraction and make
every downstream Candidate consumer use the persisted collection unchanged.

### Dependencies

- Accepted Batch01 shared guard and Candidate skill truth.
- Task order is (02A) then (02B).

### Scope Boundary

- This batch owns JD prompt/guard neutrality, grouped-repair removal, optional
  seed audit, embedding/matching parity, and matching-contract invalidation.
- It does not own graph map queries, public map routes, frontend, or release UI.

### Tasks

- [ ] (02A): Make guarded JD extraction profession-neutral and evidence-grounded
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch02 - Profession-Neutral JD and Matching Parity` > `(02A)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Profession-neutral JD extraction`, `### Shared structural skill guard`, and `## Verification` row `JD/normalizer/matching`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(02A)` -> execution authority
    - source-jd: repository `docs/plans/Plan_16.md` > `### Profession-neutral JD extraction` -> prompt/guard behavior
    - baseline-plan15: repository `docs/plans/Plan_15.md` > `### Repair and failure boundary` and `### Re-extraction transaction and service` -> contracts to preserve
    - owner-jd: repository `backend/app/services/jd_extraction.py` and `backend/app/services/jd_extraction_guard.py` -> current extractor/guard
    - validation-jd: repository `backend/tests/unit/test_jd_extraction.py` and `backend/tests/unit/test_jd_extraction_guard.py` -> focused regressions
  - Source Requirements:
    - Replace technical-only recall language with semantic professional capability labels across occupations, each backed by verbatim source evidence, under the exact six-code ordered vocabulary.
    - Reuse shared structural primitives; remove named technology punctuation exceptions and seed-qualified compound parsing.
    - Preserve Plan 15 one repair, issue cap/redaction, exact dedupe, ordinary ingestion, retained re-extraction CAS, quality, embedding, sync, and failures.
  - Dependencies: (01A) accepted shared primitives
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/jd_extraction.py`, `backend/app/services/jd_extraction_guard.py`, `backend/tests/unit/test_jd_extraction.py`, `backend/tests/unit/test_jd_extraction_guard.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_job_reextraction.py`, `backend/tests/fixtures/skill_extraction_golden.json`
  - Allowed Files: listed JD extraction/guard/tests and synthetic fixture only; shared guard is read-only unless a reviewed Batch01 repair is required; exclude schemas, matching, graph/API, frontend, seed, and runtime data
  - Agent Work:
    1. Add RED cases for marketing, sales/operations, finance/healthcare, bilingual, unknown punctuation, semantic labels with grounded evidence, and second-invalid repair behavior.
    2. Generalize prompts and reuse shared primitives while preserving exact repair/call/redaction contracts.
    3. Run focused unit plus text/URL/re-extraction integration regressions green.
  - Output: One profession-neutral guarded extractor shared by ordinary ingestion and retained re-extraction.
  - A1 Outcome: JD capabilities from unseeded professions are emitted as atomic semantic labels backed by verbatim evidence under the exact six-code, one-repair contract.
  - A2 Review Focus: Confirm no prompt/example/exception bias, exact issue ordering, no leak, and full Plan 15 lifecycle preservation.
  - A3 Batch Evidence: P16-JD-01 and shared Candidate/JD guard parity.
  - Acceptance:
    - Production JD prompts contain no technical-only capability restriction or named profession examples.
    - Each semantic skill label has source-grounded verbatim evidence before normalization; unknown punctuation labels remain valid unless clearly enumerations.
    - Text, URL, exact duplicate, and retained re-extraction behavior remains compatible and second-invalid output fails safely.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction.py tests/unit/test_jd_extraction_guard.py tests/integration/test_job_ingestion.py tests/integration/test_job_reextraction.py -q` -> PASS evidence: exit 0; freshness: final attempt only
    - Required: `rg -n -i "technical skill|C/C\+\+|Node\.js|CI/CD" app/services/jd_extraction.py app/services/jd_extraction_guard.py` -> PASS evidence: no profession/technology-specific extraction branch; freshness: final diff
  - Blocked Condition: Preserving Plan 15 requires a contract change outside approved Master/Plan 16 -> `BLOCKED_SOURCE_CONFLICT`.
  - Files: `backend/app/services/jd_extraction.py`, `backend/app/services/jd_extraction_guard.py`, `backend/tests/unit/test_jd_extraction.py`, `backend/tests/unit/test_jd_extraction_guard.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_job_reextraction.py`, `backend/tests/fixtures/skill_extraction_golden.json`

- [ ] (02B): Remove downstream grouped repair and invalidate the old matching contract
  - Task Type: refactor
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch02 - Profession-Neutral JD and Matching Parity` > `(02B)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Atomic normalization and matching parity`, `### Rollout and existing data`, and `## Completion Contract`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(02B)` -> execution authority
    - source-parity: repository `docs/plans/Plan_16.md` > `### Atomic normalization and matching parity` -> one-truth requirement
    - owner-normalizer: repository `backend/app/services/skill_normalization.py` -> canonical identity owner
    - owner-matching: repository `backend/app/services/skill_matching.py`, `backend/app/services/embedding_text.py`, and `backend/app/services/evaluation_context.py` -> downstream consumers/version
    - validation-parity: repository `docs/plans/Plan_16.md` > `## Verification` row `JD/normalizer/matching` -> gate
  - Source Requirements:
    - Remove `normalize_grouped_name`, `expand_candidate_skill`, colon-prefix promotion, and all production callers/tests that require sample-specific repair.
    - Make matching, explanations, and Candidate embedding text consume non-excluded persisted Candidate skills exactly.
    - Prove unknown direct matching with empty/minimal taxonomy, audit/remove only case-specific seed repair aliases, and bump `MATCHING_CONTRACT_VERSION` once so old evaluations become stale without auto-evaluation.
  - Dependencies: (01B), (02A)
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/skill_normalization.py`, `backend/app/services/skill_matching.py`, `backend/app/services/embedding_text.py`, `backend/app/services/evaluation_context.py`, `infrastructure/neo4j/skills_seed.yaml`, related unit/integration tests
  - Allowed Files: listed services, seed audit, and directly affected normalization/matching/evaluation tests; exclude extraction, persistence schema/migrations, graph map/API, frontend, and live data
  - Agent Work:
    1. Write RED parity tests showing persisted Candidate skills are the exact matching/embedding input and old evaluations are stale under the new contract.
    2. Remove grouped expansion and case-specific seed repair entries while preserving atomic normalization and approved curated relations.
    3. Update legacy tests to assert the new invariant and run normalization/matching/explanation/evaluation suites green.
  - Output: One atomic persisted skill truth and a new explicit matching contract version.
  - A1 Outcome: Matching/embedding/explanations no longer invent Candidate skills, unknown labels direct-match without seed membership, and old evaluations derive stale with zero automatic evaluation.
  - A2 Review Focus: Inspect all callers, deleted repair paths, seed rationale, version invalidation, fixed scoring, and absence of silent row rewrites.
  - A3 Batch Evidence: P16-NRM-01, P16-MAT-01, and Candidate downstream parity.
  - Acceptance:
    - No production grouped-name/colon-prefix expansion remains.
    - Empty/minimal taxonomy supports deterministic unknown direct matches and display preservation.
    - Existing evaluation rows become stale solely through the versioned context and no evaluate call is introduced.
    - Score weights, match strengths, ordering, and explanation semantics remain unchanged.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_skill_normalization.py tests/unit/test_skill_matching.py tests/unit/test_match_explanations.py tests/unit/test_candidate_embedding_text.py tests/unit/test_evaluation_context.py tests/integration/test_job_evaluations.py -q` -> PASS evidence: exit 0; freshness: final attempt only
    - Required: `rg -n "normalize_grouped_name|expand_candidate_skill" app tests` -> PASS evidence: no production caller or legacy assertion remains; freshness: final diff
  - Blocked Condition: A valid independently curated seed alias is indistinguishable from sample-only repair without an authority decision -> `BLOCKED_USER_ACTION`.
  - Files: `backend/app/services/skill_normalization.py`, `backend/app/services/skill_matching.py`, `backend/app/services/embedding_text.py`, `backend/app/services/evaluation_context.py`, `infrastructure/neo4j/skills_seed.yaml`, `backend/tests/unit/test_skill_normalization.py`, `backend/tests/unit/test_skill_matching.py`, `backend/tests/unit/test_match_explanations.py`, `backend/tests/unit/test_candidate_embedding_text.py`, `backend/tests/unit/test_evaluation_context.py`, `backend/tests/integration/test_job_evaluations.py`

## Mandatory Batch03 - Exact Graph Integrity and Compatibility API

### Goal

Build a bounded backend-owned map for one active Candidate and one selected Job,
returning no items unless Neo4j exactly represents authoritative SQLite skills.

### Dependencies

- Accepted Batch01 Candidate truth and Batch02 Job/matching truth.
- Task order is (03A) then (03B).

### Scope Boundary

- This batch owns selected relationship reads/comparison, compatibility
  projection, strict DTO/service/route, and additive raw graph Skill metadata.
- It does not own frontend inference, scoring changes, graph writes, arbitrary
  Cypher, auto-repair, or a sync ledger.

### Tasks

- [ ] (03A): Add exact selected relationship integrity and backend compatibility projection
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch03 - Exact Graph Integrity and Compatibility API` > `(03A)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### SQLite/Neo4j selected relationship integrity` and `### Backend-owned compatibility classification`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(03A)` -> execution authority
    - source-integrity: repository `docs/plans/Plan_16.md` > `### SQLite/Neo4j selected relationship integrity` -> exact comparison
    - source-map: repository `docs/plans/Plan_16.md` > `### Backend-owned compatibility classification` -> item classification
    - owner-sync: repository `backend/app/graph/sync_candidate.py`, `backend/app/graph/sync_job.py`, and `backend/app/graph/consistency.py` -> expected payload/revision owners
    - owner-match: repository `backend/app/services/skill_matching.py` -> direct/related winner owner
  - Source Requirements:
    - Load only active Candidate `HAS_SKILL` and selected Job `REQUIRES`/`PREFERS` relationships plus connected Skill identities and allowlisted properties.
    - Compare complete expected/actual sets including type, canonical key, confidence, years/proficiency, and bounded evidence; withhold on missing/extra/duplicate/mismatch or unavailable Neo4j.
    - Reuse deterministic skill-coverage winners for direct, related, missing-required, missing-preferred, and Candidate-only items; fail above 200 rather than truncating.
  - Dependencies: (01B), (02B)
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/graph/selected_skill_projection.py`, `backend/app/services/skill_compatibility.py`, existing sync/consistency projectors, unit/integration graph tests
  - Allowed Files: new selected projection/compatibility modules and focused tests; existing sync modules only if a RED parity test proves a bounded root defect; exclude route/DTO/frontend/migration/write repair
  - Agent Work:
    1. Reuse current sync parameter projectors and write RED ready/missing/extra/duplicate/property/unavailable/limit/classification tests.
    2. Implement fixed read-only Cypher, expected/actual comparison, and compatibility projection over SQLite assertions.
    3. Run pure, sync, rebuild, and fake-Neo4j regressions; confirm zero mutation/provider/evaluation calls.
  - Output: A pure/read-only selected relationship gate and compatibility item projector.
  - A1 Outcome: Backend returns a complete five-status compatibility result only when selected Neo4j skill relationships exactly match SQLite.
  - A2 Review Focus: Verify query allowlist/bounds, payload completeness, sync projector reuse, no read-time repair, deterministic order/counts, and 200-item fail-fast.
  - A3 Batch Evidence: P16-SYNC-01 and P16-MAP-01 core integrity evidence.
  - Acceptance:
    - Missing, extra, duplicate, or mismatched selected relationships produce `NEO4J_REBUILD_REQUIRED` and no items even when node revisions match.
    - Unavailable graph produces `NEO4J_UNAVAILABLE`; no read performs writes, provider calls, embeddings, or evaluations.
    - Ready items/counts exactly reflect backend direct/related/missing/additional facts in source order.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_skill_compatibility.py tests/integration/test_candidate_sync.py tests/integration/test_job_sync.py tests/integration/test_graph_rebuild_contracts.py -q` -> PASS evidence: exit 0; freshness: final attempt only
  - Blocked Condition: Exact payload reuse requires changing sync/public contracts outside approved files -> `BLOCKED_SCOPE_CONFLICT`.
  - Files: `backend/app/graph/selected_skill_projection.py`, `backend/app/services/skill_compatibility.py`, `backend/app/graph/sync_candidate.py`, `backend/app/graph/sync_job.py`, `backend/tests/unit/test_skill_compatibility.py`, `backend/tests/integration/test_candidate_sync.py`, `backend/tests/integration/test_job_sync.py`, `backend/tests/integration/test_graph_rebuild_contracts.py`

- [ ] (03B): Expose the strict read-only map API and readable raw Skill metadata
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch03 - Exact Graph Integrity and Compatibility API` > `(03B)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Read-only API and raw technical graph`, Master Version 2.2 > `### 8.5 Selected-JD compatibility projection`, and `## 14. Public FastAPI Boundary`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(03B)` -> execution authority
    - source-api: repository `docs/plans/Plan_16.md` > `### Read-only API and raw technical graph` -> route/DTO behavior
    - owner-observability: repository `backend/app/api/observability.py`, `backend/app/services/observability.py`, `backend/app/schemas/observability.py`, and `backend/app/graph/observability.py` -> existing bounded read owners
    - validation-api: repository `backend/tests/integration/test_observability_api.py` and `backend/tests/unit/test_observability_graph.py` -> focused API/graph gates
  - Source Requirements:
    - Add strict selected-map schemas and `GET /api/observability/skill-map?job_id=<UUID>` as a thin read-only adapter over (03A).
    - Return typed ready/stale/unavailable bodies and documented safe errors without raw CV/JD, embeddings, prompts, storage, SQL/Cypher, or provider data.
    - Extend raw technical Skill DTO with opaque key, `display_name`, and optional category while preserving caps/topology/states/no-query behavior.
  - Dependencies: (03A)
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/schemas/observability.py`, `backend/app/services/observability.py`, `backend/app/api/observability.py`, `backend/app/graph/observability.py`, related unit/integration tests
  - Allowed Files: listed observability schema/service/route/graph modules and focused tests only; exclude matching, persistence/migrations, graph writes, frontend, and runtime data
  - Agent Work:
    1. Add RED schema, service, route, redaction, call-count, and raw display metadata tests.
    2. Implement strict models, service mapping, route, and additive raw graph projection using (03A).
    3. Run focused observability/API plus existing graph snapshot regressions green.
  - Output: A bounded typed read-only map endpoint and readable raw technical Skill DTO.
  - A1 Outcome: The public endpoint returns validated selected-JD compatibility states without mutation/leakage, and technical graph Skills expose server display labels.
  - A2 Review Focus: Check strict coupling/status/error mapping, redaction, route thinness, item/cap behavior, backwards compatibility, and zero side effects.
  - A3 Batch Evidence: P16-API-01 plus remaining P16-MAP-01 and raw-graph contract evidence.
  - Acceptance:
    - Ready/stale/unavailable and documented error cases validate strictly and contain no forbidden fields.
    - Loading the endpoint never evaluates, synchronizes, rebuilds, embeds, or calls a provider.
    - Existing raw graph caps, allowed topology, stale/unavailable behavior, and no arbitrary query remain intact.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_skill_compatibility.py tests/unit/test_observability_graph.py tests/integration/test_observability_api.py -q` -> PASS evidence: exit 0; freshness: final attempt only
  - Blocked Condition: Existing public status conventions conflict materially with Master Section 8.5 -> `BLOCKED_SOURCE_CONFLICT`.
  - Files: `backend/app/schemas/observability.py`, `backend/app/services/observability.py`, `backend/app/api/observability.py`, `backend/app/graph/observability.py`, `backend/tests/unit/test_observability_graph.py`, `backend/tests/integration/test_observability_api.py`, `backend/tests/unit/test_skill_compatibility.py`

## Mandatory Batch04 - Readable Frontend Compatibility Map

### Goal

Use the existing selected saved Job to render backend-owned compatibility facts
as the default non-technical graph-panel experience while retaining the current
technical inspector.

### Dependencies

- Accepted Batch03 DTO/API.
- Task order is (04A) then (04B).

### Scope Boundary

- This batch owns strict frontend parsing/API/state and graph-panel
  presentation/accessibility only.
- It does not infer matches, add skill dictionaries, change scoring, redesign
  the sidebar/theme, or add a visualization dependency/store.

### Tasks

- [ ] (04A): Add strict selected-map parsing and sole-owner saved-JD cache state
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch04 - Readable Frontend Compatibility Map` > `(04A)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Frontend state, map, and technical mode` paragraphs for strict parser, `useSavedJobsState`, loading, invalidation, and no auto-evaluation.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(04A)` -> execution authority
    - source-fe-state: repository `docs/plans/Plan_16.md` > `### Frontend state, map, and technical mode` -> sole-owner state contract
    - owner-jobs: repository `frontend/src/features/jobs/api.ts`, `types.ts`, and `savedJobsState.ts` -> existing selected-JD/API/cache owners
    - owner-sidebar: repository `frontend/src/features/observability/ObservabilitySidebar.tsx` -> sole hook composition
    - validation-fe-state: repository `frontend/src/test/saved-jobs-state.test.tsx` and `frontend/src/test/observability-sidebar.test.tsx` -> state/invalidation gates
  - Source Requirements:
    - Strictly parse every backend status/item/requirement/strength/relation/count coupling and reject unknown/forbidden/over-limit data.
    - Store maps by Job ID in the existing `useSavedJobsState`; reuse `selectedJobId`, request-order guards, and focused invalidation.
    - Map reads never evaluate; approval/re-extraction/deletion/graph-generation/currentness events invalidate only affected cached maps.
  - Dependencies: (03B)
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/jobs/api.ts`, `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, focused tests
  - Allowed Files: listed jobs/sidebar modules and focused tests only; exclude graph presentation components/CSS until (04B), backend, dependencies, and second stores/hooks
  - Agent Work:
    1. Add RED parser/state/request-order/invalidation/no-evaluate tests using software, marketing, bilingual, and unknown-skill DTO fixtures.
    2. Implement strict types/client and extend the sole saved-JD reducer/hook/cache.
    3. Pass selected map state/actions through sidebar composition and run focused state/API tests green.
  - Output: One strict frontend map resource keyed by the existing selected Job.
  - A1 Outcome: `useSavedJobsState` exclusively loads, caches, refreshes, and invalidates strict selected-JD map resources without dispatching evaluation.
  - A2 Review Focus: Verify parser strictness, race handling, single ownership, invalidation coverage, no domain dictionaries, and no duplicated fetch/store.
  - A3 Batch Evidence: State/transport half of P16-FE-01 and P16-FE-02.
  - Acceptance:
    - Malformed coupling, unknown fields, forbidden internal/raw fields, wrong counts/strengths, or over-limit items fail parsing safely.
    - No second `selectedJobId`, map hook, cache, match classifier, alias map, or canonical formatter exists.
    - Map loading and invalidation make zero evaluate calls.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/skill-compatibility-api.test.ts src/test/saved-jobs-state.test.tsx src/test/observability-sidebar.test.tsx` -> PASS evidence: exit 0; freshness: final attempt only
  - Blocked Condition: Required ownership would create a second state path or leave Allowed Files -> `BLOCKED_SCOPE_CONFLICT`.
  - Files: `frontend/src/features/jobs/api.ts`, `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/test/skill-compatibility-api.test.ts`, `frontend/src/test/saved-jobs-state.test.tsx`, `frontend/src/test/observability-sidebar.test.tsx`

- [ ] (04B): Render the accessible default map and retain the technical inspector
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch04 - Readable Frontend Compatibility Map` > `(04B)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Frontend state, map, and technical mode`, Master Version 2.2 > `### 15.2 Sidebar`, and `frontend/AGENTS.md`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(04B)` -> execution authority
    - source-fe-map: repository `docs/plans/Plan_16.md` > `### Frontend state, map, and technical mode` -> map/view behavior
    - frontend-astryx: repository `frontend/AGENTS.md` -> mandatory component/token workflow
    - owner-graph: repository `frontend/src/features/observability/GraphPanel.tsx`, `GraphCanvas.tsx`, `GraphSemanticList.tsx`, and `graphPresentation.ts` -> current technical view
    - validation-fe-map: repository `docs/plans/Plan_16.md` > `## Verification` rows `Frontend focused`, `Synthetic browser map`, and `Mismatch/failure browser check` -> acceptance
  - Source Requirements:
    - Run Astryx discovery before UI edits and use existing components/tokens.
    - Default to a semantic accessible CV-JD layout with anchors, five backend statuses/filters/counts, readable assertion cards, evidence detail, and explicit safe states.
    - Retain the current raw graph canvas/list/controls under `Kỹ thuật`; use server `display_name` as primary Skill label and confine raw identifiers to technical metadata.
    - Never infer status from graph edges or add skill/profession/acronym/category/canonical formatting logic.
  - Dependencies: (04A)
  - User Action: None
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/observability/GraphPanel.tsx`, `SkillCompatibilityMap.tsx`, `SkillCompatibilityEvidence.tsx`, `TechnicalGraphPanel.tsx`, `graphPresentation.ts`, `GraphSemanticList.tsx`, `types.ts`, `observability.css`, focused component/interaction tests
  - Allowed Files: listed observability components/styles/types and focused tests only; exclude jobs state/API except reviewed (04A) repair, dependencies/package files, backend, and unrelated shell/theme
  - Agent Work:
    1. Run `npx astryx build`, component, layout, and token discovery for the approved semantic map; record only safe CLI evidence.
    2. Add RED rendering/accessibility/filter/evidence/safe-state/technical-mode/display-label tests.
    3. Split technical composition without replacing its canvas, implement the semantic map with Astryx/tokens, and run focused plus existing graph interaction tests green.
  - Output: A readable default `Bản đồ CV–JD` and unchanged-capability `Kỹ thuật` mode.
  - A1 Outcome: Non-technical users see backend-classified labels/evidence without raw keys, while technical users retain the bounded existing graph controls.
  - A2 Review Focus: Inspect Astryx compliance, semantic DOM/keyboard behavior, safe states, narrow layout, no raw/default leakage, no dictionaries/inference, and technical regression coverage.
  - A3 Batch Evidence: Presentation half of P16-FE-01 and P16-FE-02.
  - Acceptance:
    - Default mode exposes all five text-labeled filters/counts and separate Candidate/JD evidence using backend `display_name` only.
    - Default mode shows no UUID, canonical key, raw relationship code, unrelated seed node, or frontend-inferred match.
    - Technical mode retains pan/zoom/fit/reset, caps/truncation/stale metadata, semantic list, and raw identifiers in technical metadata.
    - Loading, refresh, empty, no-profile, no-job, stale, unavailable, and error states are keyboard/screen-reader usable and do not trap the chat UI.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/skill-compatibility-map.test.tsx src/test/graph-presentation.test.ts src/test/graph-panel.test.tsx src/test/graph-interaction.test.tsx src/test/observability-sidebar.test.tsx` -> PASS evidence: exit 0; freshness: final attempt only
    - Required: `rg -n -i "python|kubernetes|google ads|marketing|canonical.*replace|split\(['\"]_" src/features/observability src/features/jobs -g "!**/*.test.*"` -> PASS evidence: no domain/canonical formatter logic; freshness: final diff
  - Blocked Condition: Pinned Astryx lacks a required accessible composition and no approved existing-component composition is possible -> `BLOCKED_SOURCE_CONFLICT`.
  - Files: `frontend/src/features/observability/GraphPanel.tsx`, `frontend/src/features/observability/SkillCompatibilityMap.tsx`, `frontend/src/features/observability/SkillCompatibilityEvidence.tsx`, `frontend/src/features/observability/TechnicalGraphPanel.tsx`, `frontend/src/features/observability/GraphSemanticList.tsx`, `frontend/src/features/observability/graphPresentation.ts`, `frontend/src/features/observability/types.ts`, `frontend/src/features/observability/observability.css`, `frontend/src/test/skill-compatibility-map.test.tsx`, `frontend/src/test/graph-presentation.test.ts`, `frontend/src/test/graph-panel.test.tsx`, `frontend/src/test/graph-interaction.test.tsx`, `frontend/src/test/observability-sidebar.test.tsx`

## Mandatory Batch05 - Cross-Profession Release and Explicit Rollout

### Goal

Prove the complete candidate with synthetic cross-profession data, full static
and runtime gates, a bounded diagnostic, browser evidence, and an explicit
non-destructive upgrade path for existing local records.

### Dependencies

- Accepted Batch01-Batch04.

### Scope Boundary

- This batch owns synthetic diagnostic/checklist/README updates and final
  verification only.
- It does not add a benchmark, production taxonomy, migration, auto-backfill,
  background workflow, new dependency, or committed real-data evidence.

### Tasks

- [ ] (05A): Add cross-profession diagnostic and collect same-candidate release evidence
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_16.md` > `## Mandatory Batch05 - Cross-Profession Release and Explicit Rollout` > `(05A)`
  - Source of Truth: `docs/plans/Plan_16.md` > `### Rollout and existing data`, `## Verification`, and `## Completion Contract`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_16.md` > `(05A)` -> execution authority
    - source-release: repository `docs/plans/Plan_16.md` > `## Verification` and `## Completion Contract` -> final evidence
    - owner-diagnostic: repository `infrastructure/scripts/diagnose_jd_extraction.py` -> bounded safe diagnostic pattern
    - owner-docs: repository `README.md` > `## Testing and Validation` and `## Failure and Recovery` -> command/rollout documentation
    - validation-compose: repository `infrastructure/docker-compose.yml` -> supported three-service runtime
  - Source Requirements:
    - Add a bounded synthetic live-provider diagnostic that prints only case IDs/status/counts and persists/syncs/evaluates nothing.
    - Prove software, marketing, sales/operations, finance/healthcare, bilingual, and unknown punctuation cases with no production-seed additions.
    - Run focused/full backend/frontend/plan/build/Docker/browser/hardcode/scope/data/secret gates on the same candidate.
    - Document explicit CV reprocess/approval, JD re-extract, rebuild-if-required, stale evaluation, and manual re-evaluation; never rewrite SQLite JSON directly.
  - Dependencies: (01A), (01B), (02A), (02B), (03A), (03B), (04A), (04B)
  - User Action: Valid local root `.env` provider credentials are required only for the explicit live diagnostic; the user has authorized optional local supplied-record reprocess/re-extract, but no real content or identifier may be recorded.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `infrastructure/scripts/diagnose_cross_profession_skills.py`, `backend/tests/fixtures/skill_extraction_golden.json`, `docs/acceptance/cross_profession_skill_map_checklist.md`, `README.md`, directly required diagnostic tests
  - Allowed Files: listed diagnostic/synthetic fixture/acceptance/README/test paths; implementation files only for a reviewed defect found by required gates; exclude migrations, dependencies, runtime stores, `.env`, real data, and unrelated docs
  - Agent Work:
    1. Write RED diagnostic safety/case-selection tests, implement the bounded script by reusing the existing production extraction owners, and run it with fakes.
    2. Add the synthetic browser/rollout checklist and README commands/recovery notes without real identifiers/content.
    3. Run every Plan 16 focused/full/static/build/plan/Docker/browser/hardcode/scope gate; record failures and final fresh evidence. Optionally exercise supplied local records only through supported UI/API actions.
  - Output: Sanitized cross-profession diagnostic, explicit rollout documentation, and complete release evidence.
  - A1 Outcome: The same candidate build passes synthetic cross-profession extraction/matching/sync/map/UI gates and documents non-destructive upgrade steps for existing records.
  - A2 Review Focus: Verify diagnostic redaction/call scope, no benchmark/taxonomy creep, command freshness, Docker/browser evidence, no direct SQLite rewrite, and no real-data/secret artifact.
  - A3 Batch Evidence: P16-ROLL-01, P16-QA-01, P16-REG-01, and final completion contract.
  - Acceptance:
    - Diagnostic uses the configured locked provider only when explicitly invoked, prints no source/evidence/prompt/provider body/secret, and performs no persistence/embedding/graph/evaluation work.
    - Full backend/frontend static/tests/build, plan validation, Docker health, synthetic browser map, mismatch behavior, and hardcode/scope/data/secret audits pass on one candidate.
    - Existing records are upgraded only through explicit supported actions; old evaluation currentness changes by contract/revision and no automatic evaluation occurs.
    - Git contains no real CV/JD data, identifiers, screenshots, runtime stores, `.env`, credentials, or provider transcript.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q` -> PASS evidence: every command exit 0; freshness: final candidate only
    - Required: `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: every command exit 0; freshness: final candidate only
    - Required: `python C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py docs/plans --json` -> PASS evidence: contiguous valid Plans 1-16; freshness: final candidate only
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` and `Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS evidence: three services and all health components ready; freshness: final candidate only
    - Required: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_cross_profession_skills.py --cases backend/tests/fixtures/skill_extraction_golden.json` -> PASS evidence: approved safe case IDs pass with no leaked body; freshness: final candidate only
    - Required: `git diff --check; git status --short` plus changed-path/hardcode/data/secret review -> PASS evidence: only authorized paths and no forbidden artifact; freshness: final candidate only
  - Blocked Condition: Missing provider credentials for the mandatory live diagnostic -> `BLOCKED_USER_ACTION`; unavailable Docker/browser runtime -> `BLOCKED_ENVIRONMENT`; any required fix outside Plan 16 scope -> `BLOCKED_SCOPE_CONFLICT`.
  - Files: `infrastructure/scripts/diagnose_cross_profession_skills.py`, `backend/tests/fixtures/skill_extraction_golden.json`, `backend/tests/**`, `frontend/src/test/**`, `docs/acceptance/cross_profession_skill_map_checklist.md`, `README.md`

## Optional Future Tracks

This track is not part of the mandatory MVP batch chain. Multi-candidate/persona
support, archived-CV matching, a global ontology, OCR/DOCX, automatic taxonomy
learning, bulk/background reprocessing, and learned ranking remain future work
and require a separate Master amendment.
