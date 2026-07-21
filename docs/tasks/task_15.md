# JobAgent Plan 15 Execution Tasks

## Purpose

Translate `docs/plans/Plan_15.md` into the mandatory implementation and evidence
chain for source-grounded atomic JD extraction, one sanitized repair attempt,
safe same-ID retained-JD re-extraction, complete saved-JD detail rendering, and
truthful SQLite/Neo4j/currentness behavior. Preserve the existing provider,
stored schema, taxonomy owner, scoring/evaluation contract, Agent topology, and
explicit user-action boundaries.

## Project Context Notes

- Root `README.md` was read completely before Plan 15 derivation. JobAgent is a
  local single-user React/Astryx, FastAPI/LangGraph, SQLite, Neo4j, and ShopAIKey
  application with exactly three loopback-only Compose services and one ignored
  root `.env`.
- README reports Plan 14 complete at `c8aa1da`. The approved planning portfolio
  adds Plan 15 but does not claim Plan 15 runtime implementation. Execution must
  verify the accepted Plan 14 baseline rather than infer it from documentation.
- Primary authority is `docs/plans/Plan_15.md`. Its supporting approved design is
  `docs/superpowers/specs/2026-07-21-jd-extraction-quality-guard-design.md` at
  commit `664b6f3`; Master Version 2.0 and Plan 14 provide the architecture and
  consumed baseline cited by Plan 15.
- The Plan 15 portfolio, including the bounded observability-owner amendment,
  passed a fresh independent portfolio review at 100/100 with all hard gates
  passing. This authoring action creates only this task contract; it does not
  authorize implementation, acceptance checkbox changes, commits, or execution.
- Existing owners confirmed during derivation include
  `extract_job_post_from_text`, `SkillNormalizer`, `ingest_raw_text`,
  `ingest_url`, the Job repository, `sync_job`, saved-JD service/routes, strict
  frontend parsers, `useSavedJobsState`, `SavedJobsPanel`, and
  `ObservabilitySidebar`. Reuse these owners; do not introduce parallel state,
  cache, taxonomy, extraction, invalidation, or evaluation paths.
- The user-supplied root agent policy requires repository exploration before
  writing, bounded model delegation, primary-agent diff review, and final
  validation. `frontend/AGENTS.md` additionally requires Astryx CLI discovery
  before UI edits, existing Astryx components, token-based styling, and no raw
  layout elements.
- Automated tests use fakes and repository-authored synthetic fixtures. The only
  live-provider call is the explicit bounded diagnostic. Never record real JD/CV
  text, secrets, prompts, provider payloads, embeddings, SQL/Cypher details,
  authorization headers, or runtime stores.

## Authority and Scope

### Primary Source

- Primary: `docs/plans/Plan_15.md`.
- Supporting:
  `docs/superpowers/specs/2026-07-21-jd-extraction-quality-guard-design.md`,
  `docs/plans/Master_plan.md` Version 2.0, and `docs/plans/Plan_14.md`.
- Context only: `README.md`, `frontend/AGENTS.md`, current product owners/tests,
  `docs/acceptance/manual_jd_checklist.md`, and
  `infrastructure/docker-compose.yml`.

### Source Section Index

- `Plan_15.md` > `## Objective`, `## Master Requirement Coverage`,
  `## Prerequisites`, `## Scope`, and `## Out of Scope` -> mandatory P15
  outcomes, preserved contracts, dependencies, and exclusions.
- `Plan_15.md` > `### Locked schema and provider boundary`, `### Pure guard
  contract`, and `### Repair and failure boundary` -> guard vocabulary,
  normalization rules, provider/prompt locks, and one sanitized repair owner.
- `Plan_15.md` > `### Ordinary ingestion compatibility` -> shared guarded
  text/URL path, exact-dedupe provider-free return, and compatible unscorable
  ingestion.
- `Plan_15.md` > `### Re-extraction transaction and service`, `### Evaluation
  and graph invariants`, and `### Public API contract` -> staged work, revision
  compare-and-swap, failure preservation, stale projection, graph partial
  success, strict request, and bounded response.
- `Plan_15.md` > `### Saved-JD detail and action` -> strict frontend parsing,
  complete extraction groups, accessible confirmation, non-optimistic state,
  sole sidebar owner, and graph-generation invalidation.
- `Plan_15.md` > `### Synthetic corpus and diagnostic`, `## Implementation`,
  `## Verification`, `## Handoff Contract`, and `## Completion Contract` ->
  test-first ordering, live diagnostic, full gates, browser evidence, and binary
  completion.
- Approved design > `## Selected architecture`, `## Extraction prompt contract`,
  `## Deterministic quality guard`, `## Safe re-extraction contract`,
  `## Saved-JD user experience`, and `## Test design` -> detailed
  bugfix rationale and exact user-visible/failure behavior.

### Approved Architecture and Constraints

- Keep `ExtractedJobPost`, `JobPostExtraction`, `JobSkill`, `gpt-4o-mini`, the
  embedding model/dimensions, quality vocabulary, scoring formula/weights,
  evaluation contract, and `_MAX_REPAIR_ATTEMPTS == 1` unchanged.
- Guard accepted provider output before final normalization, quality,
  embedding, persistence, graph sync, or scoring. Use exactly the six approved
  issue codes, stable ordering, a 20-issue prompt cap, NFKC/whitespace/casefold
  comparison, and the four punctuation exceptions.
- `SkillNormalizer` and production taxonomy remain the sole canonical identity
  owner. Do not blindly split skill labels, add a second taxonomy/alias store, or
  silently drop/reassign invalid rows.
- Exact non-failed hashes remain provider-free. Ordinary new/retry ingestion may
  retain truthful `unscorable`; retained-Job replacement accepts only
  `full|partial`.
- Stage extraction, normalization, quality, and embedding outside transactions.
  One short revision-checked SQLite update commits first; same-ID Neo4j sync is
  post-commit and may return truthful partial success.
- Preserve Job identity/source/raw fields and historical evaluations. Successful
  replacement advances `job_posts.updated_at`, makes prior evaluations stale by
  the existing context contract, and performs zero automatic evaluations.
- `useSavedJobsState` remains the sole saved-job state/cache/action owner.
  `ObservabilitySidebar` only composes its action into `SavedJobsPanel` and
  consumes the existing graph-generation invalidation seam.
- No new dependency, model, migration, schema field, Agent/tool topology,
  background/bulk workflow, automatic evaluation, observability redesign, real
  JD fixture, or unrelated cleanup is authorized.
- A1 and A2 do not update checkboxes or commit. A3 audits accepted batch
  evidence; commit readiness remains Orchestrator-owned.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Pure semantic guard, sanitized extractor repair, and ordinary text/URL ingestion compatibility | (01A), (01B) | Accepted Plan 14 baseline and approved Plan 15 |
| Batch02 | Revision-safe retained-JD replacement service plus strict public API | (02A), (02B) | Batch01 |
| Batch03 | Complete saved-JD detail and sole-owner non-optimistic re-extraction UI | (03A) | Batch02 |
| Batch04 | Bounded live diagnostic and same-candidate release/acceptance evidence | (04A), (04B) | Batch01-Batch03 |

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

## Mandatory Batch01 - Guarded Extraction and Ingestion Compatibility

### Goal

Reject source-ungrounded facts, compound skill rows, canonical duplicates, and
required/preferred conflicts deterministically before downstream work, then use
the existing single repair owner for both schema and semantic failures without
changing ordinary dedupe or ingestion lifecycle behavior.

### Dependencies

- Accepted Plan 14 intent-aware current-message confirmation and direct URL/text
  compatibility baseline.
- Existing strict extractor, provider retry helper, production taxonomy,
  normalizer, quality classifier, ingestion lifecycle, and fake-backed tests.
- Task order is (01A) then (01B). (01B) consumes the accepted guard contract and
  fixture from (01A).

### Scope Boundary

- This batch owns the pure guard, synthetic fixture, extractor prompt/repair
  integration, and directly required text/URL/dedupe regressions.
- It does not own retained-Job replacement, public re-extraction API, frontend,
  diagnostics, schema/model changes, taxonomy expansion, scoring, evaluation,
  graph redesign, or release evidence.

### Tasks

- [x] (01A): Implement the pure source-grounding and atomic-skill guard
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_15.md` > `## Mandatory Batch01 - Guarded Extraction and Ingestion Compatibility` > `(01A)`
  - Source of Truth: `docs/plans/Plan_15.md` > `### Pure guard contract`, `### Synthetic corpus and diagnostic`, `## Implementation` steps 1-2, and `## Verification` row `Pre-change RED`; approved design > `## Deterministic quality guard` and `### Synthetic golden corpus`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_15.md` > `(01A)` -> task authority
    - source-guard: repository `docs/plans/Plan_15.md` > `### Pure guard contract` -> exact semantic guard authority
    - source-fixture: repository `docs/plans/Plan_15.md` > `### Synthetic corpus and diagnostic` -> synthetic coverage/privacy authority
    - owner-taxonomy: repository `backend/app/services/skill_normalization.py` > `SkillNormalizer` and production taxonomy loaders -> canonical identity owner to reuse
    - owner-schema: repository `backend/app/services/jd_extraction.py` > `ExtractedJobPost` and `ExtractedJobSkillItem` -> validated provider structure consumed by the guard
    - validation-focused: repository `docs/plans/Plan_15.md` > `## Verification` > `Pre-change RED` and `Focused backend` -> validation authority
  - Source Requirements:
    - Add a pure deterministic guard that accepts retained raw JD, validated provider structure, and the existing taxonomy/normalizer view without provider, DB, embedding, graph, API, UI, or logging imports and without mutating inputs.
    - Compare source facts with Unicode NFKC, whitespace-run collapse, trim, and Unicode casefold only. Check nonblank evidence/responsibilities and non-null title/company/location; do not substring-check summary or add fuzzy heuristics.
    - Accept exact taxonomy aliases/display names, unknown atomic skills, and only the explicit `C/C++`, `.NET`, `Node.js`, and `CI/CD` punctuation exceptions. Report compound/qualified/enumerated labels without splitting or rewriting them.
    - Inspect tentative canonical identities for within-group duplicates and cross-group conflicts; never return normalized output or choose a winner.
    - Emit only `EVIDENCE_NOT_IN_SOURCE`, `RESPONSIBILITY_NOT_IN_SOURCE`, `METADATA_NOT_IN_SOURCE`, `COMPOUND_SKILL_LABEL`, `DUPLICATE_SKILL`, and `SKILL_GROUP_CONFLICT`, ordered by provider field/index then stable rule order with only safe paths/counts.
    - Add repository-authored English/Vietnamese synthetic fixture cases for grounding, atomicity, punctuation exceptions, unknown atomic rows, duplicates/conflicts, direct metadata, one-line/sectioned content, and contact-only content.
  - Dependencies: Accepted Plan 14 baseline; no earlier Plan 15 task.
  - User Action: None; use only repository-authored synthetic content and fake providers.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/jd_extraction_guard.py`, `backend/tests/fixtures/jd_extraction_golden.json`, `backend/tests/unit/test_jd_extraction_guard.py`; conditional compatibility seam in `backend/app/services/skill_normalization.py` and `backend/tests/unit/test_skill_normalization.py`
  - Allowed Files: the five listed files only. Production/test normalizer files may change only when a new red guard test proves a required compatibility seam; exclude extractor orchestration, ingestion, quality, repositories, API, graph, frontend, dependencies, runtime data, and `.env`.
  - Agent Work:
    1. Inspect `ExtractedJobPost`, taxonomy loading, alias resolution, unknown-key behavior, and existing normalization tests; record the intended red guard cases before production edits.
    2. Add the synthetic fixture and failing pure-guard tests for exact normalization, grounding, atomicity, exceptions, uniqueness/disjointness, stable issue ordering, safe issue shape, and input immutability.
    3. Implement the minimum pure guard using existing taxonomy/normalizer ownership; avoid blind splitting, new aliases, fuzzy matching, logging, or side effects.
    4. Run focused tests/static checks and inspect every changed path for source/provider/secret leakage.
  - Output: A pure deterministic guard and synthetic fixture reject every approved semantic-invalid class while preserving punctuation exceptions and unknown atomic skills.
  - A1 Outcome: Guard tests prove exact source grounding, atomic labels, exception handling, canonical uniqueness/disjointness, stable safe issues, and zero side effects.
  - A2 Review Focus: Exact six-code vocabulary, comparison algorithm, issue ordering/shape, taxonomy reuse, no input mutation/import drift, no blind splitting or taxonomy expansion, synthetic-only data, conditional normalizer seam justification, and fresh validation evidence.
  - A3 Batch Evidence: P15-GRD-01 and P15-GRD-02 guard/fixture ownership rows plus the pure half of P15-REG-01.
  - Acceptance:
    - The guard is pure, deterministic, source-grounded, taxonomy-assisted only, and emits exactly the approved safe issue vocabulary/order.
    - Protected punctuation and unknown atomic skills pass; compounds, qualifiers, canonical duplicates, and cross-group conflicts fail without mutation or silent repair.
    - Fixture content is synthetic English/Vietnamese only and contains no provider response, secret, personal data, or real JD text.
    - Only allowed files change, and any normalizer edit is backed by a focused red compatibility test rather than taxonomy expansion.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction_guard.py tests/unit/test_skill_normalization.py -q` -> PASS evidence: exit `0`, all guard/exception/identity/order cases green; freshness: final attempt only.
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app/services/jd_extraction_guard.py app/services/skill_normalization.py tests/unit/test_jd_extraction_guard.py tests/unit/test_skill_normalization.py --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check; git status --short` plus changed-path and synthetic-data inspection -> PASS evidence: no whitespace error and only allowed files/data; freshness: final attempt only.
  - Blocked Condition: Missing/unreadable extractor or taxonomy authority is `BLOCKED_MISSING_REF`; plan/design disagreement on guard semantics is `BLOCKED_SOURCE_CONFLICT`; a root fix requiring files outside `Allowed Files` is `BLOCKED_SCOPE_CONFLICT`; unavailable Python/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/services/jd_extraction_guard.py`, `backend/tests/fixtures/jd_extraction_golden.json`, `backend/tests/unit/test_jd_extraction_guard.py`, conditionally `backend/app/services/skill_normalization.py`, `backend/tests/unit/test_skill_normalization.py`

- [x] (01B): Integrate guarded one-repair extraction into ordinary text and URL ingestion
  - Task Type: bugfix
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_15.md` > `## Mandatory Batch01 - Guarded Extraction and Ingestion Compatibility` > `(01B)`
  - Source of Truth: `docs/plans/Plan_15.md` > `### Locked schema and provider boundary`, `### Repair and failure boundary`, `### Ordinary ingestion compatibility`, `## Implementation` steps 3-5, and `## Verification` row `Focused backend`; approved design > `## Selected architecture`, `## Extraction prompt contract`, and `## New-ingestion behavior`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_15.md` > `(01B)` -> task authority
    - source-repair: repository `docs/plans/Plan_15.md` > `### Repair and failure boundary` -> one sanitized repair contract
    - source-ingestion: repository `docs/plans/Plan_15.md` > `### Ordinary ingestion compatibility` -> text/URL/dedupe compatibility
    - accepted-guard: repository `docs/tasks/task_15.md` > `(01A)` and `backend/app/services/jd_extraction_guard.py` -> accepted semantic boundary to consume
    - owner-extractor: repository `backend/app/services/jd_extraction.py` > `ShopAIKeyStructuredJdInvoker`, `_build_messages`, `_invoke_structured`, and `extract_job_post_from_text` -> existing provider/repair owner
    - owner-ingestion: repository `backend/app/services/jd_ingestion.py` > `ingest_raw_text`, `ingest_url`, and exact-hash branches -> lifecycle owner
    - validation-focused: repository `docs/plans/Plan_15.md` > `## Verification` > `Focused backend` -> command authority
  - Source Requirements:
    - Keep current provider schema, invoker, strict structured output, `gpt-4o-mini`, shared provider retry helper, and one repair attempt. Add the seven approved prompt rules without changing output fields.
    - Guard each validated provider result before `extracted_to_job_post`. Only an accepted result may normalize, classify quality, embed, persist, graph-sync, or score.
    - Schema repair uses a fixed generic safe instruction. Guard repair includes at most the first 20 ordered code/path/count issues plus omitted count; neither path echoes source values, provider payloads, raw exceptions, or evidence.
    - A first schema or guard failure consumes the same repair allowance; provider retry remains per allowed call. A second invalid result raises fixed safe `INVALID_STRUCTURED_OUTPUT`.
    - Text and URL processing call the same guarded `extract_job_post_from_text`. Existing exact non-failed duplicate return performs no provider/guard/embedding/graph/evaluation work; failed retry retains identity; ordinary truthful `unscorable` behavior remains compatible.
  - Dependencies: Accepted (01A) guard and fixture.
  - User Action: None; all automated tests use fake invokers/embedders and synthetic content.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/services/jd_extraction.py`, `backend/app/services/jd_ingestion.py`, `backend/tests/unit/test_jd_extraction.py`, `backend/tests/integration/test_job_ingestion.py`
  - Allowed Files: the four listed files only; consume (01A) files read-only. Exclude provider adapters/retry owner, schemas, quality implementation, repositories, graph, API, Agent, frontend, dependencies, diagnostics, runtime data, and `.env`.
  - Agent Work:
    1. Inspect extractor call/repair boundaries and both ingestion branches/callers; reproduce semantic-invalid acceptance, unsafe repair leakage, and ordinary compatibility cases before edits.
    2. Add failing extractor tests for prompt rules, guard-before-normalization, schema/guard repair redaction, issue cap, exact call counts, second-invalid error, provider retry caps, and log/message privacy.
    3. Integrate the accepted guard with the smallest extractor change, preserving invoker/schema/provider retry ownership and final normalization order.
    4. Add text/URL/failed-retry/exact-dedupe regressions and route both processing paths through the accepted extractor without changing quality or terminal-state semantics.
    5. Run focused/static checks and inspect logs/diffs for raw-source, evidence, provider, or secret leakage.
  - Output: Ordinary extraction accepts only guarded output, uses at most one sanitized repair, and preserves existing text/URL/dedupe/retry/unscorable behavior.
  - A1 Outcome: Fake-backed extractor and ingestion tests prove guard-before-downstream ordering, one safe repair, exact call caps, and provider-free exact duplicate return.
  - A2 Review Focus: Prompt/schema/provider locks, first/repair call counts, redaction, accepted guard reuse, downstream ordering, both source types, exact dedupe and failed retry callers, no quality/topology drift, and fresh validation.
  - A3 Batch Evidence: P15-RPR-01 and P15-ING-01 ownership rows plus integrated P15-GRD-01/P15-GRD-02 evidence.
  - Acceptance:
    - The existing extractor guards every provider result before normalization and downstream work and never exceeds one repair attempt.
    - Repair messages/logs expose only approved structural diagnostics; second-invalid output fails with the existing fixed safe code/message.
    - Text and URL flows share the same guarded extractor; exact non-failed duplicate return remains provider/embedding/graph/evaluation-free and failed retry preserves identity.
    - Stored schemas, provider/model/retry ownership, ordinary `unscorable` semantics, dependencies, and unrelated modules remain unchanged.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction_guard.py tests/unit/test_jd_extraction.py tests/unit/test_skill_normalization.py tests/unit/test_jd_quality.py tests/integration/test_job_ingestion.py -q` -> PASS evidence: exit `0` with prompt/repair/call-cap/ingestion/dedupe cases green; freshness: final attempt only.
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app/services/jd_extraction.py app/services/jd_ingestion.py tests/unit/test_jd_extraction.py tests/integration/test_job_ingestion.py --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check; git status --short` plus changed-path/redaction review -> PASS evidence: only allowed files change and no raw/provider/secret content appears; freshness: final attempt only.
  - Blocked Condition: Missing accepted (01A) evidence is `BLOCKED_MISSING_REF`; source conflict on repair/ingestion semantics is `BLOCKED_SOURCE_CONFLICT`; required provider/schema/quality/repository edits are `BLOCKED_SCOPE_CONFLICT`; unavailable tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/services/jd_extraction.py`, `backend/app/services/jd_ingestion.py`, `backend/tests/unit/test_jd_extraction.py`, `backend/tests/integration/test_job_ingestion.py`

## Mandatory Batch02 - Safe Retained-JD Replacement and Public API

### Goal

Add one explicit same-ID re-extraction path that stages provider/embedding work
outside transactions, conditionally replaces only a scorable result under the
captured revision, preserves durable truth on all pre-commit failures, advances
evaluation currentness without evaluation, and truthfully reports post-commit
graph failure.

### Dependencies

- Accepted Batch01 guarded extractor and ordinary ingestion compatibility.
- Existing SQLite Job/evaluation ownership, revision-keyed currentness,
  embedding adapter, same-ID `sync_job`, rebuild instruction, saved-JD projection,
  FastAPI error conventions, and fake-backed integration harnesses.
- Task order is (02A) then (02B). (02B) exposes only the accepted service/repository
  contract from (02A).

### Scope Boundary

- This batch owns the revision compare-and-swap, staged coordinator, strict
  request/response, saved-JD adapter, route/error map, and required graph/currentness
  regressions.
- It does not own migrations, new state columns/tables, evaluation execution,
  automatic/bulk/background work, graph redesign, frontend, diagnostics, Agent,
  or ordinary ingestion semantics.

### Tasks

- [x] (02A): Implement revision-checked replacement and staged re-extraction service
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_15.md` > `## Mandatory Batch02 - Safe Retained-JD Replacement and Public API` > `(02A)`
  - Source of Truth: `docs/plans/Plan_15.md` > `### Re-extraction transaction and service`, `### Evaluation and graph invariants`, `## Implementation` steps 6-7, and `## Verification` row `Focused backend`; approved design > `## Safe re-extraction contract`, `### Staged execution`, and `### Evaluation currentness`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_15.md` > `(02A)` -> task authority
    - source-transaction: repository `docs/plans/Plan_15.md` > `### Re-extraction transaction and service` -> staged/CAS field contract
    - source-invariants: repository `docs/plans/Plan_15.md` > `### Evaluation and graph invariants` -> stale/no-evaluate/same-ID graph contract
    - accepted-extractor: repository `docs/tasks/task_15.md` > `(01B)` and `backend/app/services/jd_extraction.py` -> guarded extraction owner to reuse
    - owner-repository: repository `backend/app/repositories/jobs.py` > Job lookup and processing transitions -> SQLite Job owner
    - owner-graph: repository `backend/app/graph/sync_job.py` > `sync_job` -> same-ID projection owner
    - owner-currentness: repository `backend/app/services/saved_jobs.py` > evaluation-context/currentness derivation -> invariant caller to preserve
    - validation-focused: repository `docs/plans/Plan_15.md` > `## Verification` > `Focused backend` -> validation authority
  - Source Requirements:
    - Load the exact Job, copy an immutable working snapshot, capture `updated_at`, and reject unknown or missing/blank retained source before provider work.
    - Outside transactions run the accepted guarded extractor, normalizer/quality owner, and locked embedding provider only for `full|partial`; reject `unscorable` without mutation.
    - Execute one short conditional SQLite update matching `id` and captured `updated_at`; replace only processing status, extraction JSON, quality, failure code, complete embedding triplet, and a strictly later revision.
    - Preserve identity/source/raw/hash/created fields and every evaluation row. A zero-row update returns `JOB_REEXTRACT_CONFLICT` with no retry/overwrite; reload and validate the committed Job.
    - After commit call existing same-ID `sync_job`. Graph failure retains SQLite truth and returns `sync_ok=false`, `NEO4J_SYNC_FAILED`, and safe rebuild guidance.
    - Every provider/guard/normalization/quality/embedding/transaction/conflict failure preserves exact prior durable Job and evaluation currentness. Make zero evaluation/scoring calls.
  - Dependencies: Accepted Batch01, especially (01B).
  - User Action: None; service/repository tests use fake providers, embedders, graph drivers, and disposable SQLite.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/repositories/jobs.py`, `backend/app/services/job_reextraction.py`, `backend/tests/integration/test_jobs_repository.py`, `backend/tests/integration/test_job_reextraction.py`; conditional same-ID seam in `backend/app/graph/sync_job.py` and `backend/tests/integration/test_job_sync.py`
  - Allowed Files: the six listed files only. `sync_job.py` may change only when a new red regression proves its current same-ID behavior violates Plan 15; exclude models/migrations, schemas/API/saved-job adapter, evaluation/scoring owners, ingestion, Agent, frontend, dependencies, runtime data, and `.env`.
  - Agent Work:
    1. Inspect repository transaction patterns, embedding/quality owners, `sync_job`, evaluation-context callers, and Job field ownership; add RED repository/service/concurrency/failure-matrix tests before implementation.
    2. Implement one conditional replacement operation with explicit allowed fields, strict revision advance, zero-row conflict, and committed reload.
    3. Implement the focused coordinator with an immutable snapshot, all provider/embedding work staged outside transactions, accepted Batch01 extractor reuse, post-commit graph sync, and no evaluation/scoring call.
    4. Prove success, unscorable, every pre-commit failure class, conflict, graph partial success, stale projection, unchanged historical rows, and unrelated graph branches through fakes/integration tests.
    5. Run focused/static checks and review transaction boundaries and changed paths.
  - Output: A reusable re-extraction coordinator atomically replaces only accepted same-ID Job fields and preserves truthful failure/currentness/graph behavior.
  - A1 Outcome: Repository and service tests prove staged work, strict CAS field ownership, revision advance, failure preservation, stale-without-evaluate behavior, and truthful post-commit graph partial success.
  - A2 Review Focus: Transaction duration, immutable snapshot, CAS predicate/fields, strict later timestamp, all failure branches, evaluation spies, graph ordering/scope, conditional `sync_job` edits, caller compatibility, no migration/state drift, and fresh evidence.
  - A3 Batch Evidence: P15-REX-01, P15-REX-02, and P15-REX-03 repository/service/currentness/graph rows.
  - Acceptance:
    - All provider/embedding work is outside transactions and only a `full|partial` accepted result reaches one revision-checked replacement transaction.
    - CAS changes only approved mutable fields, advances revision strictly, preserves identity/source/raw/evaluations, and conflicts without retry or overwrite.
    - Successful replacement projects previous evaluation as stale with zero evaluation/scoring calls.
    - SQLite commits before same-ID graph sync; graph failure returns safe partial-success data without rolling back SQLite or mutating unrelated graph branches.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_jobs_repository.py tests/integration/test_job_reextraction.py tests/integration/test_job_sync.py -q` -> PASS evidence: exit `0` with CAS/concurrency/failure/currentness/graph cases green; freshness: final attempt only.
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app/repositories/jobs.py app/services/job_reextraction.py app/graph/sync_job.py tests/integration/test_jobs_repository.py tests/integration/test_job_reextraction.py tests/integration/test_job_sync.py --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check; git status --short` plus transaction/field/caller changed-path review -> PASS evidence: only allowed files and no migration/evaluation/provider topology drift; freshness: final attempt only.
  - Blocked Condition: Missing accepted Batch01 extractor is `BLOCKED_MISSING_REF`; source conflict on field ownership/transaction/graph ordering is `BLOCKED_SOURCE_CONFLICT`; a required model/migration/evaluation/API edit is `BLOCKED_SCOPE_CONFLICT`; unavailable DB/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/repositories/jobs.py`, `backend/app/services/job_reextraction.py`, `backend/tests/integration/test_jobs_repository.py`, `backend/tests/integration/test_job_reextraction.py`, conditionally `backend/app/graph/sync_job.py`, `backend/tests/integration/test_job_sync.py`

- [x] (02B): Expose the strict re-extraction request, response, and safe error contract
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_15.md` > `## Mandatory Batch02 - Safe Retained-JD Replacement and Public API` > `(02B)`
  - Source of Truth: `docs/plans/Plan_15.md` > `### Public API contract`, `### Re-extraction transaction and service`, `## Implementation` step 8, and `## Verification` row `Focused backend`; approved design > `### Public command` and `### Failure semantics`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_15.md` > `(02B)` -> task authority
    - source-api: repository `docs/plans/Plan_15.md` > `### Public API contract` -> request/response/status/redaction authority
    - accepted-service: repository `docs/tasks/task_15.md` > `(02A)` and `backend/app/services/job_reextraction.py` -> service contract to expose
    - owner-schemas: repository `backend/app/schemas/job_evaluations.py` > saved-Job request/response models -> public DTO owner
    - owner-service: repository `backend/app/services/saved_jobs.py` > saved list/detail/evaluate/delete adapters and safe errors -> projection/error owner
    - owner-route: repository `backend/app/api/jobs.py` > saved-Job routes and `_http_for_service_error` -> FastAPI boundary owner
    - validation-api: repository `backend/tests/integration/test_saved_jobs_api.py` -> existing route/schema/error regression owner
  - Source Requirements:
    - Add `POST /api/jobs/{job_id}/reextract`. Absent or empty JSON is allowed; a zero-field `extra='forbid'` request boundary rejects every replacement/arbitrary field with 422 before service invocation.
    - HTTP 200 validates exactly as `ReextractJobResponse`: `outcome='updated'`, one current `SavedJobListItem`, `sync_ok`, `code`, and `rebuild_instruction` with strict true/null or false/`NEO4J_SYNC_FAILED`/nonblank coupling.
    - Map all pre-commit failures to safe `detail={code, summary}` using current conventions, including `JOB_REEXTRACT_CONFLICT`, source/not-found/not-scorable, extraction validation/provider, and embedding errors. Do not return a success model for these failures.
    - Route/service logs may contain Job ID, safe code, phase, and sync flag only; never raw source/evidence/provider/prompt/embedding/SQL/Cypher/secrets.
    - Reuse the accepted (02A) coordinator and existing saved-list projection. Do not call evaluation/matching or add replacement DTO fields.
  - Dependencies: Accepted (02A) service/repository behavior.
  - User Action: None; API tests use dependency overrides/fakes and disposable state.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/app/schemas/job_evaluations.py`, `backend/app/services/saved_jobs.py`, `backend/app/api/jobs.py`, `backend/tests/integration/test_saved_jobs_api.py`
  - Allowed Files: the four listed files only; consume (02A) files read-only. Exclude models/migrations/repositories, extraction/embedding/graph/evaluation implementations, Agent, frontend, dependencies, runtime data, and `.env`.
  - Agent Work:
    1. Inspect existing strict saved-JD DTOs, projection adapters, route/error maps, dependency injection, and API tests; add RED body/model/error/spy cases.
    2. Add the zero-field request and strictly coupled bounded response schemas without changing existing DTO fields.
    3. Add the smallest saved-service adapter and route delegating to (02A), preserving safe status/error conventions and no-evaluate behavior.
    4. Test absent/empty/forbidden bodies, full success, graph partial success, every pre-commit error family, output validation, service call suppression on 422, and log redaction.
    5. Run focused/static checks and inspect public contract/callers/diffs.
  - Output: A strict explicit re-extraction endpoint truthfully exposes accepted replacement and graph partial success without accepting client replacement data.
  - A1 Outcome: API tests prove strict empty-only input, bounded coupled output, safe pre-commit errors, graph partial success, and zero evaluation/replacement-field authority.
  - A2 Review Focus: DTO strictness/coupling, route status map, service delegation, list-item currentness, forbidden-body short circuit, error/log redaction, caller compatibility, no migration/evaluation drift, and fresh validation.
  - A3 Batch Evidence: P15-API-01 plus public portions of P15-REX-02/P15-REX-03 and Batch02 integration matrix.
  - Acceptance:
    - Only absent/empty request bodies reach the service; replacement and arbitrary fields fail 422 before service execution.
    - Success and graph-warning success strictly satisfy `ReextractJobResponse`; every pre-commit failure uses safe error detail and no success model.
    - The response row reflects post-replacement evaluation currentness, and no route/service path dispatches evaluation or matching.
    - Only allowed API/schema/service/test files change with no schema migration, secret/raw-data logging, or public drift outside the new route.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_job_reextraction.py tests/integration/test_saved_jobs_api.py -q` -> PASS evidence: exit `0` with request/response/error/graph/no-evaluate cases green; freshness: final attempt only.
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app/schemas/job_evaluations.py app/services/saved_jobs.py app/api/jobs.py tests/integration/test_saved_jobs_api.py --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check; git status --short` plus route/schema/log changed-path review -> PASS evidence: only allowed files and safe public payloads; freshness: final attempt only.
  - Blocked Condition: Missing accepted (02A) service contract is `BLOCKED_MISSING_REF`; source conflict on status/DTO/error semantics is `BLOCKED_SOURCE_CONFLICT`; required repository/model/evaluation/frontend edits are `BLOCKED_SCOPE_CONFLICT`; unavailable API/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `backend/app/schemas/job_evaluations.py`, `backend/app/services/saved_jobs.py`, `backend/app/api/jobs.py`, `backend/tests/integration/test_saved_jobs_api.py`

## Mandatory Batch03 - Complete Saved-JD Detail and Re-extraction UI

### Goal

Render all useful existing extraction fields and add one accessible,
confirmation-based, non-optimistic **Re-extract JD** action using the existing
sidebar-local state/cache owner and graph-generation invalidation seam.

### Dependencies

- Accepted Batch02 strict API and returned `SavedJobListItem` currentness contract.
- Existing saved-JD parser/client/reducer/panel/detail patterns,
  `JobDeleteDialog` AlertDialog pattern, `useSavedJobsState` sole ownership, and
  `ObservabilitySidebar` composition/effect wiring.

### Scope Boundary

- This batch owns only the named jobs UI/client/state files, the existing
  observability composition owner, and four focused test files.
- It does not own backend behavior, chat/SSE state, a second hook/store/context,
  global cache, observability redesign/CSS, layout redesign, dependency changes,
  or automatic evaluation.

### Tasks

- [x] (03A): Render complete extraction detail and wire sole-owner re-extraction
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_15.md` > `## Mandatory Batch03 - Complete Saved-JD Detail and Re-extraction UI` > `(03A)`
  - Source of Truth: `docs/plans/Plan_15.md` > `### Saved-JD detail and action`, `## Implementation` step 9, `## Verification` rows `Focused frontend`, `Browser re-extraction`, and `Failure browser check`; `frontend/AGENTS.md` > Astryx workflow/rules.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_15.md` > `(03A)` -> task authority
    - source-ui: repository `docs/plans/Plan_15.md` > `### Saved-JD detail and action` -> rendering/action/state authority
    - source-owner-repair: repository `docs/plans/Plan_15.md` > `## Target Directory Structure` and `## Out of Scope` -> observability wiring-only boundary
    - frontend-rules: repository `frontend/AGENTS.md` > Astryx workflow and rules -> mandatory design-system discovery/implementation rules
    - owner-api-types: repository `frontend/src/features/jobs/api.ts` and `frontend/src/features/jobs/types.ts` > saved-JD API/parsers -> strict client boundary
    - owner-state: repository `frontend/src/features/jobs/savedJobsState.ts` > `SavedJobActionKind`, reducer, and `useSavedJobsState` -> sole state/cache/action owner
    - owner-composition: repository `frontend/src/features/observability/ObservabilitySidebar.tsx` > sole `useSavedJobsState` instance and graph-generation effect -> wiring/invalidation owner
    - owner-dialog-pattern: repository `frontend/src/features/jobs/JobDeleteDialog.tsx` > `AlertDialog` composition -> accessible confirmation pattern to reuse
    - validation-frontend: repository `docs/plans/Plan_15.md` > `## Verification` > `Focused frontend` -> command authority
  - Source Requirements:
    - Keep strict parsing in `types.ts`; add strict response/error coupling without coercing malformed sync/code/rebuild combinations.
    - Render metadata, ordered responsibilities, required skills, preferred skills, experience, extraction confidence, and bounded evidence already present in `JobPostExtraction`. Evidence is collapsed by default; all empty states are explicit; raw source remains in its existing bounded section.
    - Add `JobReextractDialog.tsx` naming the Job and stating identity/raw preservation, pre-commit failure preservation, stale-on-success, and no automatic evaluation. Confirm/cancel/focus/keyboard behavior must be accessible.
    - Extend the existing per-Job action union with `reextract`; allow one action per Job in flight. Never optimistically patch extraction.
    - On success refresh/patch compact row, refetch selected detail, refresh currentness, and bump existing graph generation. Graph-warning success still refreshes SQLite views and shows rebuild guidance; pre-commit failure preserves cached list/detail and shows only safe summary.
    - Keep the sole `useSavedJobsState` instance in `ObservabilitySidebar`, pass its action through props into `SavedJobsPanel`, and reuse the existing graph invalidation effect. Add no second hook/context/store/cache/request/invalidation path.
  - Dependencies: Accepted Batch02, especially strict (02B) API contract.
  - User Action: None for automated tests. Astryx discovery commands are mandatory read-only preparation before UI edits.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/features/jobs/api.ts`, `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/features/jobs/SavedJobDetail.tsx`, `frontend/src/features/jobs/SavedJobsPanel.tsx`, `frontend/src/features/jobs/JobReextractDialog.tsx`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/test/saved-jobs-api.test.ts`, `frontend/src/test/saved-jobs-panel.test.tsx`, `frontend/src/test/saved-jobs-state.test.tsx`, `frontend/src/test/observability-sidebar.test.tsx`
  - Allowed Files: the eleven listed files only. Exclude `JobDeleteDialog.tsx` except read-only reuse, observability state/CSS/layout, chat/SSE, backend, package/dependency files, generated artifacts, runtime data, and `.env`.
  - Agent Work:
    1. Run `Set-Location frontend; npx astryx build "saved job detail re-extraction confirmation"; npx astryx component AlertDialog; npx astryx docs tokens`, then inspect existing jobs UI/state/tests and sidebar callers before writing UI.
    2. Add RED strict parser/API tests for success coupling, safe errors, forbidden malformed payloads, and the explicit POST call.
    3. Add RED detail/panel/dialog tests for every extraction group, explicit empty states, collapsed bounded evidence, consequence copy, focus/keyboard behavior, cancel, per-Job lock, graph warning, and pre-commit preservation.
    4. Extend the sole reducer/hook owner and add state tests for non-optimistic pending/success/failure transitions, list/detail/currentness refresh, graph generation, and zero evaluate dispatch.
    5. Implement the smallest Astryx-compliant detail/dialog/panel changes and wire the existing action through `ObservabilitySidebar`; add a sidebar regression proving sole ownership and invalidation consumption.
    6. Run focused/full frontend checks and inspect UI paths for raw HTML/layout/style/dependency/state-owner drift.
  - Output: Saved-JD detail exposes all existing structured fields and one accessible truthful re-extraction action through the sole sidebar-local owner.
  - A1 Outcome: Frontend tests prove strict parsing, complete bounded detail, accessible confirmation, non-optimistic preservation, currentness refresh, graph warning/invalidation, and no second state owner or evaluate call.
  - A2 Review Focus: Astryx discovery/rules, parser strictness, evidence bounds/empty states, dialog accessibility/copy, per-Job action lock, state transitions, sidebar caller wiring, graph-generation effect, failure preservation, no second owner/dependency/layout drift, and fresh validation.
  - A3 Batch Evidence: P15-UI-01 frontend parser/component/state/accessibility/sidebar-wiring/currentness/invalidation rows.
  - Acceptance:
    - Saved detail visibly renders every approved existing extraction group with bounded collapsed evidence and explicit empty states.
    - The dialog is accessible, names the Job, states all four consequences, locks correctly, and never triggers optimistic extraction or automatic evaluation.
    - Success refreshes list/detail/currentness and existing graph generation; graph partial success shows rebuild guidance; pre-commit failure preserves cached truth.
    - `ObservabilitySidebar` retains the only `useSavedJobsState` instance and only passes the existing action into `SavedJobsPanel`; no second state/cache/request/invalidation path or observability redesign exists.
    - Only allowed files change and Astryx components/tokens/patterns are reused without new dependency or raw layout/CSS drift.
  - Validation:
    - Required: `Set-Location frontend; npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-sidebar.test.tsx` -> PASS evidence: exit `0` with parser/detail/dialog/state/sidebar cases green; freshness: final attempt only.
    - Required: `Set-Location frontend; npm run lint; npm run typecheck; npm run build` -> PASS evidence: all three exit `0`; freshness: final attempt only.
    - Required: `git diff --check; git status --short` plus search/inspection for `useSavedJobsState`, re-extraction calls, raw elements/styles, and changed paths -> PASS evidence: one state owner and only allowed files; freshness: final attempt only.
  - Blocked Condition: Missing accepted Batch02 API is `BLOCKED_MISSING_REF`; Plan/API/Astryx conflict is `BLOCKED_SOURCE_CONFLICT`; required backend/observability-state/CSS/dependency/chat edits are `BLOCKED_SCOPE_CONFLICT`; unavailable Node/Astryx/test tooling is `BLOCKED_ENVIRONMENT`.
  - Files: `frontend/src/features/jobs/api.ts`, `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/savedJobsState.ts`, `frontend/src/features/jobs/SavedJobDetail.tsx`, `frontend/src/features/jobs/SavedJobsPanel.tsx`, `frontend/src/features/jobs/JobReextractDialog.tsx`, `frontend/src/features/observability/ObservabilitySidebar.tsx`, `frontend/src/test/saved-jobs-api.test.ts`, `frontend/src/test/saved-jobs-panel.test.tsx`, `frontend/src/test/saved-jobs-state.test.tsx`, `frontend/src/test/observability-sidebar.test.tsx`

## Mandatory Batch04 - Diagnostic and Release Evidence

### Goal

Prove the guarded extractor against a bounded live synthetic corpus, then run all
focused/full/static/plan/Compose/browser gates on one unchanged candidate and
append sanitized acceptance evidence without using real JD data.

### Dependencies

- Accepted Batch01-Batch03 implementation and tests.
- Valid user-managed root `.env` for the explicit live diagnostic and normal
  Docker stack; Docker/Node/Python/browser tooling available locally.
- Task order is (04A) then (04B). Any product/test/config change after a gate
  invalidates affected evidence and requires rerun.

### Scope Boundary

- (04A) owns only the explicit diagnostic script and README command/status text.
  (04B) owns only dated Plan 15 evidence appended to the existing manual JD
  checklist.
- This batch does not repair product failures, change fixtures, expose provider
  output, write runtime data into Git, rebuild unrelated graph state, or broaden
  release scope. Failures route back to the owning earlier task.

### Tasks

- [ ] (04A): Add and run the bounded synthetic live-provider diagnostic
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_15.md` > `## Mandatory Batch04 - Diagnostic and Release Evidence` > `(04A)`
  - Source of Truth: `docs/plans/Plan_15.md` > `### Synthetic corpus and diagnostic`, `## Implementation` steps 10 and 12, and `## Verification` row `Synthetic provider diagnostic`.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_15.md` > `(04A)` -> task authority
    - source-diagnostic: repository `docs/plans/Plan_15.md` > `### Synthetic corpus and diagnostic` -> finite live-check/privacy contract
    - source-command: repository `docs/plans/Plan_15.md` > `## Verification` > `Synthetic provider diagnostic` -> exact command/result authority
    - accepted-fixture: repository `docs/tasks/task_15.md` > `(01A)` and `backend/tests/fixtures/jd_extraction_golden.json` -> synthetic cases to consume read-only
    - owner-diagnostic-pattern: repository `infrastructure/scripts/diagnose_shopaikey.py` -> safe explicit provider diagnostic conventions to reuse
    - owner-readme: repository `README.md` > `## Testing and Validation` -> command documentation owner
  - Source Requirements:
    - Add one explicit finite diagnostic over the approved live subset of the accepted synthetic fixture using the configured locked provider and real guarded extractor only.
    - Make no persistence, embedding, graph, evaluation, or runtime-store call. Print only case ID and safe pass/fail summary; never print source, evidence, prompt, provider payload, secret, or raw exception.
    - Exit nonzero when any metadata, atomicity, group, grounding, or quality invariant fails. Do not introduce a model comparison, quality score, broad benchmark, new dependency, or real/proprietary JD.
    - Document the exact explicit command and privacy/credential prerequisites in README without claiming automated fake tests prove live semantic quality.
  - Dependencies: Accepted (01A) fixture/guard and (01B) integrated extractor; Batch02/03 may proceed independently but must be accepted before (04B).
  - User Action: Before validation, ensure the ignored root `.env` contains valid existing ShopAIKey credentials and network access. Do not provide or print secret values; missing credentials/network is a blocker, not authorization to edit `.env`.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 3600
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `infrastructure/scripts/diagnose_jd_extraction.py`, `README.md`
  - Allowed Files: the two listed files only; fixture/extractor/provider settings are read-only. Exclude `.env`, dependencies, product code/tests, acceptance docs, runtime data, provider transcripts, and generated output.
  - Agent Work:
    1. Inspect the accepted fixture/guard/extractor and existing safe ShopAIKey diagnostic conventions; define finite invariant-only result handling before edits.
    2. Implement the diagnostic with no persistence/downstream imports/calls and fixed safe output/error handling.
    3. Add the exact command and synthetic/privacy/live-provider caveat to README while preserving current baseline truth.
    4. Run syntax/static checks and the explicit live command once with configured credentials; inspect stdout/stderr and changed paths for leakage.
  - Output: A documented finite live-provider diagnostic validates approved synthetic extraction invariants without persisting or exposing source/provider data.
  - A1 Outcome: The explicit diagnostic exits zero on the accepted live synthetic subset, emits only case IDs/safe statuses, and makes no downstream or secret-bearing output.
  - A2 Review Focus: Finite fixture subset, real guarded extractor reuse, no persistence/embedding/graph/evaluation, safe output/error paths, exit semantics, provider/model/dependency locks, README truthfulness, credential handling, and fresh live evidence.
  - A3 Batch Evidence: P15-QA-01 live semantic diagnostic row and README command ownership.
  - Acceptance:
    - The script uses only accepted synthetic cases and the production guarded extractor with the locked configured provider.
    - It makes no persistence/embedding/graph/evaluation call, exits nonzero on invariant failure, and never prints source/evidence/provider/prompt/secret/raw-error content.
    - README documents the exact explicit command, live credential/network prerequisite, synthetic-only boundary, and non-benchmark status.
    - No dependency, provider/model setting, `.env`, product code, fixture, runtime data, or unrelated documentation changes.
  - Validation:
    - Required: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_jd_extraction.py --cases backend/tests/fixtures/jd_extraction_golden.json` -> PASS evidence: exit `0`, every approved live case reports only ID/pass status and all invariants pass; freshness: final attempt only.
    - Required: `& '.\.venv\Scripts\python.exe' -m py_compile infrastructure/scripts/diagnose_jd_extraction.py; Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check ..\infrastructure\scripts\diagnose_jd_extraction.py --no-cache` -> PASS evidence: both exit `0`; freshness: final attempt only.
    - Required: `git diff --check; git status --short` plus stdout/stderr, import/call, README, and changed-path review -> PASS evidence: safe output and only allowed files; freshness: final attempt only.
  - Blocked Condition: Missing accepted fixture/extractor is `BLOCKED_MISSING_REF`; source conflict on live scope/privacy is `BLOCKED_SOURCE_CONFLICT`; missing valid credentials/network requiring user setup is `BLOCKED_USER_ACTION`; unavailable Python/provider runtime is `BLOCKED_ENVIRONMENT`; a required product/fixture/dependency edit is `BLOCKED_SCOPE_CONFLICT`.
  - Files: `infrastructure/scripts/diagnose_jd_extraction.py`, `README.md`

- [ ] (04B): Run same-candidate full gates and record sanitized browser acceptance
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_15.md` > `## Mandatory Batch04 - Diagnostic and Release Evidence` > `(04B)`
  - Source of Truth: `docs/plans/Plan_15.md` > `## Verification`, `## Implementation` steps 10-12, and `## Completion Contract`; `docs/acceptance/manual_jd_checklist.md` > existing append-only JD acceptance evidence.
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_15.md` > `(04B)` -> task authority
    - source-verification: repository `docs/plans/Plan_15.md` > `## Verification` -> complete gate/browser/scope authority
    - source-completion: repository `docs/plans/Plan_15.md` > `## Completion Contract` -> binary release boundary
    - accepted-diagnostic: repository `docs/tasks/task_15.md` > `(04A)` -> live semantic evidence prerequisite
    - owner-compose: repository `infrastructure/docker-compose.yml` -> normal three-service candidate stack
    - owner-acceptance: repository `docs/acceptance/manual_jd_checklist.md` -> dated sanitized evidence destination
    - validation-readme: repository `README.md` > `## Testing and Validation` -> full repository command conventions
  - Source Requirements:
    - On one unchanged candidate run focused and full backend/frontend tests, Ruff, mypy, lint, typecheck, build, contiguous plan validation, diff/scope/secret review, Docker Compose build/start/health, and the accepted live diagnostic.
    - Browser-smoke one retained synthetic JD with a current evaluation: inspect all extraction groups, confirm re-extraction once, and prove stable Job/source/raw identity, refreshed detail, stale-without-evaluate state, and same-ID graph update or explicit rebuild guidance.
    - Exercise one controlled pre-commit failure and prove dialog unlock, preserved prior detail/evaluation, safe error, no optimistic state, and no graph/evaluate call.
    - Record network/console/sanitized-log evidence without real JD text, provider output, secrets, runtime paths, SQL/Cypher, or raw screenshots/data. Append dated attempt-specific Plan 15 evidence only.
    - Any later product/test/config change invalidates affected evidence. This task does not repair failures; route them to the owning earlier task and rerun on a fresh unchanged candidate.
  - Dependencies: Accepted (01A), (01B), (02A), (02B), (03A), and (04A), including their fresh required validation.
  - User Action: Ensure Docker Desktop, browser access, normal root `.env`, and valid provider/network are available. Use only synthetic retained JD/evaluation data and never disclose credentials or real data.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/manual_jd_checklist.md`
  - Allowed Files: `docs/acceptance/manual_jd_checklist.md` only. All product/test/config/fixture/README files are read-only; generated/runtime/provider/browser artifacts remain outside Git and `.agent` evidence remains unstaged.
  - Agent Work:
    1. Confirm accepted prerequisite evidence and a clean understood candidate diff; record candidate revision/change set without staging or committing.
    2. Run the exact focused/full backend/frontend/static/plan/live-diagnostic gates and retain only safe command/result summaries.
    3. Build/start the normal three-service Compose stack with wait/health and verify `/api/health` on the same candidate.
    4. Perform the synthetic desktop success and controlled pre-commit failure browser procedures; inspect network calls, console, currentness, graph behavior, and sanitized logs.
    5. Append dated attempt-specific pass/fail evidence to the existing checklist, run diff/scope/secret review, and invalidate/rerun affected evidence if the candidate changed.
  - Output: One same-candidate sanitized acceptance entry proves or truthfully blocks Plan 15 across automated, live-provider, Docker, browser, currentness, graph, privacy, and scope gates.
  - A1 Outcome: Full gates, healthy normal stack, and synthetic success/failure browser evidence are recorded for one unchanged candidate with no raw-data/secret leak.
  - A2 Review Focus: Prerequisite acceptance, exact candidate freshness, all required command exits, Docker health, browser identity/currentness/no-evaluate/graph/failure observations, synthetic/privacy handling, append-only evidence, no product edits, and honest skipped/failed reporting.
  - A3 Batch Evidence: P15-QA-01 and P15-REG-01 release matrix plus final Plan 15 completion/scope/diff evidence.
  - Acceptance:
    - Every required focused/full/static/plan/live diagnostic and Docker health gate passes on the same unchanged candidate.
    - Success browser evidence proves complete detail, one confirmed re-extraction, stable identity/raw source, stale existing evaluation with no evaluate request, and current graph or explicit rebuild guidance.
    - Failure browser evidence proves unlocked/preserved non-optimistic UI, safe error, and no graph/evaluate side effect.
    - The dated checklist entry contains only synthetic/sanitized evidence, accurately records candidate and results, and no product/test/config/runtime/secret file changes in this task.
  - Validation:
    - Required: `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction_guard.py tests/unit/test_jd_extraction.py tests/unit/test_skill_normalization.py tests/unit/test_jd_quality.py tests/integration/test_job_ingestion.py tests/integration/test_jobs_repository.py tests/integration/test_job_reextraction.py tests/integration/test_saved_jobs_api.py tests/integration/test_job_sync.py -q; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q` -> PASS evidence: every command exit `0`; freshness: final unchanged candidate only.
    - Required: `Set-Location frontend; npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-sidebar.test.tsx; npm test -- --run; npm run lint; npm run typecheck; npm run build` -> PASS evidence: every command exit `0`; freshness: final unchanged candidate only.
    - Required: `& '.\.venv\Scripts\python.exe' 'C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py' 'docs/plans' --json; $env:PYTHONPATH=(Resolve-Path 'backend').Path; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_jd_extraction.py --cases backend/tests/fixtures/jd_extraction_golden.json` -> PASS evidence: contiguous Plans 1-15 and live synthetic cases exit `0`; freshness: final unchanged candidate only.
    - Required: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180; Invoke-RestMethod http://127.0.0.1:8000/api/health` -> PASS evidence: normal three-service stack ready and health response successful; freshness: final unchanged candidate only.
    - Required: Browser procedure at `http://localhost:5173/` using repository-authored synthetic retained Job/current evaluation, followed by one controlled pre-commit failure -> PASS evidence: all success/failure observations in Source Requirements recorded with network/console/sanitized-log checks; freshness: final unchanged candidate only.
    - Required: `git diff --check; git status --short` plus changed-path, secret/runtime-data, model/schema/weight/dependency/Agent/CV/observability-owner review -> PASS evidence: this task changes only the allowed checklist and the combined candidate remains within Plan 15; freshness: final unchanged candidate only.
  - Blocked Condition: Missing or rejected prerequisite task evidence is `BLOCKED_MISSING_REF`; any product/test/config failure requiring repair is `BLOCKED_SCOPE_CONFLICT` and must return to its owning task; missing Docker/Node/Python/browser/provider runtime is `BLOCKED_ENVIRONMENT`; missing user-managed credentials/network/setup is `BLOCKED_USER_ACTION`; source/acceptance disagreement is `BLOCKED_SOURCE_CONFLICT`.
  - Files: `docs/acceptance/manual_jd_checklist.md`
