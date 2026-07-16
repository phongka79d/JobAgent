# JobAgent Plan 7 Execution Tasks

## Purpose

Translate `docs/plans/Plan_7.md` into the final mandatory work needed to prove
and document a clean local JobAgent MVP release. The work closes only verified
test gaps, adds one disposable public-boundary E2E smoke, audits local runtime
safeguards and excluded scope, revises the existing root README, and records
fresh release evidence. It adds no product feature, schema, endpoint, tool,
Agent, service, infrastructure component, CI workflow, or production-security
claim.

## Project Context Notes

- Root `README.md` was read completely before task derivation. It records Plans
  1-6 as implemented and describes the React/Astryx, FastAPI, LangGraph,
  SQLite, Neo4j, and ShopAIKey ownership boundaries and current commands.
- `docs/tasks/task_6.md` still has seven unchecked canonical tasks `(02B)`,
  `(02C)`, `(02D)`, `(03A)`, `(03B)`, `(04A)`, and `(04B)`, although
  `README.md` and commits `6682c27`, `db8e1cf`, and `438d1e8` record Plan 6
  Batches 02-04 as complete. On 2026-07-16 the user approved deriving this file
  with reconciliation of those Plan 6 acceptance markers as an explicit
  prerequisite. This document does not alter Plan 6 progress.
- The user also approved preserving the prior Plan 5 choice-C safety decision:
  live rebuild runs only inside the existing Compose backend with
  `docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.graph.rebuild`.
  The host `infrastructure/scripts/rebuild_neo4j.py` remains help/version only;
  Plan 7's contrary no-argument wrapper expectation is treated as stale.
- `README.md` already exists and must be revised in place.
  `docs/acceptance/manual_jd_checklist.md` exists;
  `docs/acceptance/local_release_checklist.md` and
  `backend/tests/e2e/test_demo_flow.py` do not yet exist.
- Existing isolated test owners must be reused: migrated SQLite and session
  helpers under `backend/tests/support/`, provider/embedding/matching/rebuild
  fakes under `backend/tests/fakes/`, synthetic CV/taxonomy fixtures under
  `backend/tests/fixtures/`, and public dependency injection through
  `backend/app/api/dependencies.py` and `backend/app/tools/registry.py`.
- Public API/SSE helpers currently local to
  `backend/tests/integration/test_chat_api.py` may be extracted once for E2E
  reuse. Existing structured-output fakes must be consolidated rather than
  copied into a new harness.
- `frontend/AGENTS.md` applies to frontend repairs: inspect Astryx public APIs,
  preserve the existing shell and token system, and do not add raw layout,
  internal imports, or a second client state path.
- Normal automated tests use temporary files/databases and fake external
  providers. Only the explicit provider diagnostic and manual release work may
  use real ShopAIKey, Docker, live Neo4j, or browser observation.
- The root `.env` is user-managed and ignored. Never read, print, copy into a
  tracked file, or record its values. `.env.example` is documentation only.
- The user-supplied agent rules apply throughout: search existing owners and
  every caller before writing, reuse or safely refactor instead of duplicating,
  keep modules focused, choose the smallest source-aligned change, and repair
  shared behavior at its root.

## Authority and Scope

### Primary Source

- Primary authority: `docs/plans/Plan_7.md`.
- Supporting architecture authority cited by the primary source:
  `docs/plans/Master_plan.md` Sections 1-29.
- Approved conflict resolution: the user's 2026-07-16 instruction recorded in
  `Project Context Notes` above.
- Repository context only: `README.md`, `docs/tasks/task_5.md`,
  `docs/tasks/task_6.md`, `frontend/AGENTS.md`, existing application/test
  owners, `.env.example`, `.gitignore`, and
  `infrastructure/docker-compose.yml`.

### Source Section Index

- `docs/plans/Plan_7.md` > `## 1. Objective` through `## 5. Out of Scope` -> final
  local-release outcome, prerequisites, mandatory verification, and prohibited
  scope.
- `docs/plans/Plan_7.md` > `## 6. Target Directory Structure` -> E2E and release
  checklist ownership while preserving focused existing modules.
- `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix`
  -> required backend, frontend, idempotency, matching, and rebuild evidence.
- `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.2 End-to-end smoke contract`
  -> exact fake-backed public-boundary demo sequence and durable assertions.
- `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.3 Failure and recovery matrix`
  -> truthful outage, invalid-output, disconnect, duplicate, replay, resume,
  and loop-limit evidence.
- `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.4 Fresh graph and fresh-clone verification`
  -> isolated live project/worktree, fresh Neo4j volume, rebuild, matching, and
  safe teardown.
- `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.5 README contract`
  -> exact release README content and executable command requirements.
- `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.6 Environment, secret, and data audit`
  and `### 7.7 Final scope audit` -> one environment, secret/data safety,
  loopback ports, sanitized failures, and excluded-scope audit.
- `docs/plans/Plan_7.md` > `## 8. Implementation Steps` through
  `## 10. Final Handoff and Completion Contract` -> final execution order,
  fresh evidence, blocking rules, and release gate.
- `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` through
  `## 23. Environment Configuration` -> stable failures, direct sync/rebuild,
  local safeguards, and one root environment.
- `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` -> exact unit,
  integration, frontend, E2E, and README command coverage.
- `docs/plans/Master_plan.md` > `## 25. Implementation Phases` > `### Phase 6 — Polish and local release`
  and `## 27. Definition of Done` through `## 29. Final Planning Decision` ->
  final phase tasks, exit gate, exclusions, and narrow product statement.

### Approved Architecture and Constraints

- Preserve React/Astryx -> FastAPI -> one LangGraph Agent -> focused services,
  with SQLite as source of truth, Neo4j as a rebuildable derived index, and
  ShopAIKey behind existing adapters.
- Preserve exactly six production tools, seven public endpoints, one
  conversation, one Agent/ToolNode loop, and the exact run/tool/SSE status
  vocabularies.
- `(run_id, tool_call_id)` remains the only tool replay identity. Approval,
  duplicate CV/JD, and write-tool evidence must show one durable result and one
  side effect without adding another key, ledger, queue, or worker.
- Add tests only after mapping the source requirement to existing evidence.
  Reuse existing fakes, fixtures, API clients, and helpers. Production edits are
  permitted only for a reproduced Plan 7 defect and must remain in its focused
  owner with a regression test and caller audit.
- Automated tests must not call real ShopAIKey or developer services/data.
  Live work uses explicitly named disposable Compose projects and never removes
  normal developer volumes.
- Choice C is final: the host rebuild wrapper never performs a rebuild. The
  canonical in-container Compose command is the only live destructive path.
- Release evidence must be current, dated, sanitized, and truthful. A failed
  command, secret/data finding, false-success path, unresolved manual ranking
  inconsistency, or fresh-start failure blocks release completion.
- No authentication, multi-user/multi-conversation scope, OCR/DOCX, discovery,
  browser automation, auto-apply/tracking, cloud deployment, Qdrant/reranking,
  alternate embeddings, Redis/Celery/Kafka, outbox/queue/sync ledger,
  multi-agent product design, LangSmith, CI, evaluation project, tuning, or
  production security subsystem may be added.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Focused automated coverage closure | (01A), (01B), (01C), (01D), (01E), (01F), (01G), (01H) | Plan 6 acceptance markers reconciled |
| Batch02 | Disposable fake-backed public-boundary demo flow | (02A) | Batch01 |
| Batch03 | Static release safeguards and exact maintainer documentation | (03A), (03B) | Batch02 |
| Batch04 | Fresh-clone and full disposable live release evidence | (04A), (04B) | Batch03 |
| Batch05 | Fresh final current-output release gate | (05A) | Batch04 |

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

## Mandatory Batch01 - Focused Automated Contract Closure

### Goal

Map the final automated matrix to existing tests and add only missing focused
cases. Reproduced product defects require a separately typed, owner-specific
bugfix contract before the affected coverage task can pass.

### Dependencies

- Before any Batch01 dispatch, the Orchestrator must verify matching A1/A2
  `ACCEPTED` evidence or valid prior standalone completion evidence for Plan 6
  `(02B)`, `(02C)`, `(02D)`, `(03A)`, `(03B)`, `(04A)`, and `(04B)`, record
  each disposition in the current run's immutable Orchestrator decision
  evidence under `.agent/<plan-id>/<run-id>/`, then reconcile their canonical
  markers through the authorized acceptance process. The binary repository gate is that
  `docs/tasks/task_6.md` has no unchecked canonical task marker. README and
  commit messages alone do not satisfy this prerequisite, and no Plan 7 task
  may update Plan 6 progress.
- Required dispatch check (repository root):
  `$open = Select-String -Path docs/tasks/task_6.md -Pattern '^- \[ \] \((02B|02C|02D|03A|03B|04A|04B)\):'; if ($open) { $open; throw 'Plan 6 acceptance reconciliation is incomplete' }`.

### Scope Boundary

This batch adds no E2E harness, release documentation, live-provider call,
Docker/Neo4j operation, product behavior, or unrelated refactor. Coverage tasks
edit tests/support only. A reproduced product defect returns
`BLOCKED_SCOPE_CONFLICT`; the Orchestrator must approve a separate `bugfix`
task with its production owner and regression before retrying coverage.

### Tasks

- [x] (01A): Close persistent data and SQLite/Alembic contract coverage gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01A)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.1 Backend unit tests` and `### 24.2 Backend integration tests`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01A)` -> task authority
    - source-automated-matrix: repository `docs/plans/Plan_7.md` > `### 7.1 Final automated coverage matrix` -> persistent-contract evidence
    - validation-foundation: repository `backend/tests/unit/test_tool_result.py` and `backend/tests/integration/test_database_contract.py` -> existing validation owners
    - existing-db-harness: repository `backend/tests/support/db_migration.py` -> isolated migration/session reuse
    - prerequisite-plan6: repository `docs/tasks/task_6.md` > canonical tasks `(02B)` through `(04B)` -> required accepted predecessor state
  - Source Requirements:
    - Prove exact Pydantic/status/UUID/UTC/singleton/ToolResult/embedding limits
      and fresh/initialized migrations, PRAGMAs, named constraints, indexes,
      foreign keys, cascades, singleton seeds, no runtime `create_all()`, and no
      checkpoint ownership collision.
    - Map every requirement to an existing test before adding a case; do not
      duplicate fixtures or weaken an assertion to obtain PASS.
  - Dependencies: The binary Plan 6 acceptance reconciliation gate described in this batch; no Batch01 task dependency.
  - User Action: Before dispatch, the Orchestrator verifies matching acceptance evidence and reconciles the seven exact Plan 6 markers; A1 must not perform that action.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/unit/test_tool_result.py`, `backend/tests/unit/test_core_conventions.py`, `backend/tests/unit/test_chat_models.py`, `backend/tests/unit/test_attachment_profile_models.py`, `backend/tests/unit/test_profile_schemas.py`, `backend/tests/unit/test_job_post_model.py`, `backend/tests/unit/test_embedding_adapter.py`, `backend/tests/unit/test_settings.py`, `backend/tests/integration/test_database_contract.py`, `backend/tests/integration/test_database_pragmas.py`, `backend/tests/integration/test_migrations.py`
  - Allowed Files: the listed test files and `backend/tests/support/db_migration.py`; exclude all `backend/app/**`, Agent/chat/domain/matching/rebuild/frontend/infrastructure/docs owners.
  - Agent Work:
    1. Search the named tests, schema/model/migration owners, and shared
       migration fixture before writing; build a requirement-to-test map.
    2. Add only missing persistent-contract cases, reusing the existing
       migration/session/schema-parity helpers. Do not create a second harness.
    3. If a case reproduces product behavior, report its exact owner/callers and
       block for a separately typed bugfix; do not edit production here.
    4. Run focused validation and record only final-attempt
       evidence.
  - Output: Complete repository-verifiable persistent data and SQLite/Alembic coverage.
  - A1 Outcome: Every Pydantic/data and SQLite/Alembic matrix row has a named passing test with no duplicated harness.
  - A2 Review Focus: Feature-rubric completeness and reuse; hard gates `HG-01`, `HG-02`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover exact schema/status coupling, isolated migrations, no production diff, no duplicate/hardcoded owner, and fresh evidence.
  - A3 Batch Evidence: Persistent-contract rows and sole ownership of data/schema/migration test changes.
  - Acceptance:
    - Every source-listed persistent data/database row maps to a named passing test.
    - Normal tests use isolated SQLite/fakes and make no provider, browser, or live Neo4j call.
    - No production file, schema, migration, status alias, or runtime topology is changed.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/unit/test_tool_result.py tests/unit/test_core_conventions.py tests/unit/test_chat_models.py tests/unit/test_attachment_profile_models.py tests/unit/test_profile_schemas.py tests/unit/test_job_post_model.py tests/unit/test_embedding_adapter.py tests/unit/test_settings.py -q` -> PASS evidence: exit `0` and all persistent-contract unit rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_database_contract.py tests/integration/test_database_pragmas.py tests/integration/test_migrations.py -q` -> PASS evidence: exit `0` and isolated database/migration rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/unit/test_tool_result.py tests/unit/test_core_conventions.py tests/unit/test_chat_models.py tests/unit/test_attachment_profile_models.py tests/unit/test_profile_schemas.py tests/unit/test_job_post_model.py tests/unit/test_embedding_adapter.py tests/unit/test_settings.py tests/integration/test_database_contract.py tests/integration/test_database_pragmas.py tests/integration/test_migrations.py` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_SOURCE_CONFLICT` if Plan 6 acceptance remains unreconciled; `BLOCKED_ENVIRONMENT` if the pinned local Python/test tools are unavailable; `BLOCKED_SCOPE_CONFLICT` if a reproduced root fix must leave `Allowed Files`.
  - Files: the files in `Likely Files` plus `backend/tests/support/db_migration.py` only if reused

- [x] (01B): Close CV and profile lifecycle coverage gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01B)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix` and `### 7.3 Failure and recovery matrix`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.1 Backend unit tests` and `### 24.2 Backend integration tests`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01B)` -> task authority
    - source-profile-matrix: repository `docs/plans/Plan_7.md` > `### 7.1 Final automated coverage matrix` -> CV/profile requirements
    - validation-profile: repository `backend/tests/integration/test_cv_api.py` and `backend/tests/integration/test_profile_approval.py` -> existing lifecycle evidence
    - validation-candidate-sync: repository `backend/tests/integration/test_candidate_sync.py` -> derived projection evidence
  - Source Requirements:
    - Prove PDF MIME/magic/size/page/text limits, active/staged/failed hash
      reuse, validated extraction/draft/change loop, approval guard,
      rollback-safe replacement, restart persistence, and Candidate sync.
    - Prove invalid profile output uses one repair then safe failure, and Neo4j
      sync failure retains committed SQLite truth with the stable rebuild path.
    - Leave cross-tool replay, repeated approval identity, and terminal resume
      side-effect counting to (01H).
  - Dependencies: The binary Plan 6 acceptance reconciliation gate described in this batch; no Batch01 task dependency.
  - User Action: None after the batch prerequisite is satisfied.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/unit/test_profile_extraction.py`, `backend/tests/unit/test_pdf_extraction.py`, `backend/tests/integration/test_cv_api.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/integration/test_candidate_sync.py`
  - Allowed Files: the listed test files and a new/reused profile structured-output fake under `backend/tests/fakes/**`, excluding existing embedding/matching/rebuild fakes; exclude all `backend/app/**`, JD/replay/matching/rebuild/frontend/infrastructure/docs owners.
  - Agent Work:
    1. Search upload/extraction/draft/approval/sync tests, fixtures, and shared
       structured-output fakes before writing; map every CV/profile row.
    2. Add only missing lifecycle/failure cases and consolidate a fake only when
       an existing and new test both reuse it.
    3. If a case reproduces product behavior, identify its focused owner and all
       callers, then block for a separately typed bugfix.
    4. Run focused profile/CV/Candidate-sync validation with fresh evidence.
  - Output: Complete fake-backed CV/profile lifecycle and Candidate-sync coverage.
  - A1 Outcome: Every CV/profile matrix row has deterministic passing evidence over disposable files and SQLite.
  - A2 Review Focus: Feature-rubric coverage completeness and fixture reuse; hard gates `HG-01`, `HG-02`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover exact file/row lifecycle, SQLite-first sync truth, no production/duplicate/hardcoded path, no real provider/Neo4j, and fresh evidence.
  - A3 Batch Evidence: CV/profile lifecycle rows and sole ownership of profile-domain test changes.
  - Acceptance:
    - Active/staged/failed CV, approval/change, replacement, restart, and Candidate-sync rows have named passing tests.
    - Invalid output and sync failure persist truthful stable codes with no false success, secret, or raw CV leakage.
    - Tests use synthetic PDFs, temp files/SQLite, and controlled fakes only.
    - No production, schema, endpoint, tool, retry, or sync architecture is changed.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/unit/test_profile_extraction.py tests/unit/test_pdf_extraction.py -q` -> PASS evidence: exit `0` and profile/PDF behavior passes; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_cv_api.py tests/integration/test_profile_approval.py tests/integration/test_candidate_sync.py -q` -> PASS evidence: exit `0` and lifecycle/sync rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/unit/test_profile_extraction.py tests/unit/test_pdf_extraction.py tests/integration/test_cv_api.py tests/integration/test_profile_approval.py tests/integration/test_candidate_sync.py tests/fakes` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_ENVIRONMENT` if the fake-backed suite cannot run; `BLOCKED_SCOPE_CONFLICT` if any new case exposes product behavior; `BLOCKED_AMBIGUOUS_REF` if structured-output fake ownership cannot be consolidated without duplication.
  - Files: the files in `Likely Files` plus only the shared profile fake actually reused

- [x] (01C): Close deterministic matching coverage gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01C)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix` and `### 7.3 Failure and recovery matrix`; `docs/plans/Master_plan.md` > `## 17. Embedding and Retrieval` through `## 20. Failure and Recovery Policy`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01C)` -> task authority
    - source-matching: repository `docs/plans/Plan_7.md` > `### 7.1 Final automated coverage matrix` -> matching rows
    - validation-matching: repository `backend/tests/integration/test_match_jobs.py` and `backend/tests/integration/test_match_revisions.py` -> existing match evidence
    - validation-formula: repository `backend/tests/unit/test_match_components.py` and `backend/tests/unit/test_match_explanations.py` -> deterministic compute evidence
  - Source Requirements:
    - Prove unavailable/revision-inconsistent graph rejection, retrieval limit,
      all deterministic score components, missing-component renormalization,
      quality/tie order, strict evidence explanations, and zero partial results.
    - Automated tests use fake embeddings/controlled graph reads and never call
      the provider, a live Neo4j instance, or a destructive graph path.
  - Dependencies: The binary Plan 6 acceptance reconciliation gate described in this batch; no Batch01 task dependency.
  - User Action: None after the batch prerequisite is satisfied.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/unit/test_candidate_embedding_text.py`, `backend/tests/unit/test_skill_matching.py`, `backend/tests/unit/test_match_components.py`, `backend/tests/unit/test_match_ordering.py`, `backend/tests/unit/test_match_explanations.py`, `backend/tests/integration/test_match_revisions.py`, `backend/tests/integration/test_match_jobs.py`, `backend/tests/fakes/matching.py`, `backend/tests/fakes/embeddings.py`
  - Allowed Files: the listed tests/fakes only; exclude all `backend/app/**`, rebuild/sync/frontend/infrastructure/docs owners.
  - Agent Work:
    1. Search all matching tests, fake embeddings/graph reads, scoring owners,
       and callers; map source rows before adding cases.
    2. Add only missing deterministic fake-backed assertions, reusing the
       matching and rebuild fake owners.
    3. If a case reproduces product behavior, identify its focused owner and
       callers, then block for a separately typed bugfix.
    4. Run the complete matching regression set and focused lint with
       final-attempt evidence.
  - Output: Complete deterministic matching coverage without a provider or live graph.
  - A1 Outcome: Every matching matrix row passes with exact failures, retrieval, unrounded order, components, and evidence.
  - A2 Review Focus: Feature-rubric deterministic coverage and fake reuse; hard gates `HG-01`, `HG-02`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover zero partial ranking, no provider/live/destructive graph access, no production/duplicate/hardcoded path, and fresh evidence.
  - A3 Batch Evidence: Matching rows and sole ownership of scoring/retrieval/revision test changes.
  - Acceptance:
    - Every matching component, unavailable state, tie, and explanation row has deterministic passing evidence.
    - Tests use fake embeddings and controlled graph reads with no provider/live/destructive call.
    - No production file, alternate model, graph repair, score cache, or partial ranking path is added.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/unit/test_candidate_embedding_text.py tests/unit/test_skill_matching.py tests/unit/test_match_components.py tests/unit/test_match_ordering.py tests/unit/test_match_explanations.py -q` -> PASS evidence: exit `0` and deterministic compute rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_match_revisions.py tests/integration/test_match_jobs.py -q` -> PASS evidence: exit `0` and matching integration rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/unit/test_candidate_embedding_text.py tests/unit/test_skill_matching.py tests/unit/test_match_components.py tests/unit/test_match_ordering.py tests/unit/test_match_explanations.py tests/integration/test_match_revisions.py tests/integration/test_match_jobs.py tests/fakes/matching.py tests/fakes/embeddings.py` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_ENVIRONMENT` if fake-backed matching tests cannot run; `BLOCKED_SCOPE_CONFLICT` if any new case exposes product behavior; `BLOCKED_AMBIGUOUS_REF` if matching fake ownership cannot be resolved without duplication.
  - Files: the files in `Likely Files`

- [x] (01D): Close frontend status, history, approval, card, error, and disconnect gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01D)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix` and `### 7.3 Failure and recovery matrix`; `docs/plans/Master_plan.md` > `## 15. Frontend UX Plan` and `## 24. Local Testing Strategy` > `### 24.3 Frontend tests`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01D)` -> task authority
    - source-frontend: repository `docs/plans/Plan_7.md` > `### 7.1 Final automated coverage matrix` -> frontend evidence rows
    - validation-frontend: repository `frontend/src/test/chat-page.test.tsx` and `frontend/src/test/sse-reducer.test.ts` -> existing client owners
    - frontend-rules: repository `frontend/AGENTS.md` > `ASTRYX:START` -> UI implementation constraints
  - Source Requirements:
    - Prove the reducer and UI accept exact tool statuses, hydrate/load older
      durable truth, disable approval actions idempotently, maintain sidebar
      state, render saved/match cards, and show error/disconnected states.
    - Prove disconnect recovery hydrates durable run/tool truth without a
      second reducer, store, API, SSE event, or false-success surface.
    - Use the existing public Astryx components/tokens and test the current
      single client state/transport path without changing production UI.
  - Dependencies: The binary Plan 6 acceptance reconciliation gate described in this batch; no Batch01 task dependency.
  - User Action: None after the batch prerequisite is satisfied.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `frontend/src/test/sse-reducer.test.ts`, `frontend/src/test/chat-page.test.tsx`, `frontend/src/test/approval-card.test.tsx`, `frontend/src/test/cv-sidebar.test.tsx`, `frontend/src/test/saved-job-card.test.tsx`, `frontend/src/test/match-card.test.tsx`
  - Allowed Files: the listed test files and `frontend/src/test/setup.ts` only if a shared fixture is required; exclude all production frontend, `frontend/AGENTS.md`, backend, infrastructure, and docs.
  - Agent Work:
    1. Read `frontend/AGENTS.md`; search the reducer, history projection,
       pagination, approval/sidebar, saved/match cards, error/disconnect owners,
       and every caller before changing a test.
    2. Map all frontend matrix rows to current tests and add only missing cases.
    3. If a test reproduces product behavior, identify its narrow existing
       owner/callers and block for a separately typed bugfix.
    4. Run the full frontend test, lint, type, and build gates and record fresh
       final evidence.
  - Output: Complete frontend matrix evidence with truthful disconnect/recovery and no parallel client architecture.
  - A1 Outcome: Every Plan 7 frontend row passes for live-state projection and durable rehydration through the existing client owners.
  - A2 Review Focus: Feature-rubric UI coverage and fixture reuse; hard gates `HG-01`, `HG-02`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover exact statuses, one reducer/history truth, no production/Astryx redesign or hardcoded path, no network dependency, and fresh evidence.
  - A3 Batch Evidence: Frontend rows and ownership of any test/UI changes without overlap with backend tasks.
  - Acceptance:
    - All source-listed frontend states have deterministic tests, including disconnect and load-older behavior.
    - Approval/card/sidebar behavior renders once from durable truth and retains exact statuses.
    - No production UI, raw layout/style value, internal Astryx import, client store, reducer, endpoint, or SSE contract is changed.
  - Validation:
    - Required (repository root): `Set-Location frontend; npm test -- --run` -> PASS evidence: exit `0` and all frontend tests pass; freshness: final attempt only.
    - Required (repository root): `Set-Location frontend; npm run lint; if ($LASTEXITCODE -ne 0) { throw 'frontend lint failed' }; npm run typecheck; if ($LASTEXITCODE -ne 0) { throw 'frontend typecheck failed' }; npm run build; if ($LASTEXITCODE -ne 0) { throw 'frontend build failed' }` -> PASS evidence: every command exits `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_ENVIRONMENT` if the pinned Node/Astryx toolchain is unavailable; `BLOCKED_SCOPE_CONFLICT` if any new case exposes product behavior; `BLOCKED_MISSING_REF` if a required Astryx public component contract cannot be inspected.
  - Files: the files in `Likely Files` plus `frontend/src/test/setup.ts` only if shared

- [x] (01E): Close conversation, Agent, SSE, history, and checkpoint coverage gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01E)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix` and `### 7.3 Failure and recovery matrix`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.1 Backend unit tests` and `### 24.2 Backend integration tests`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01E)` -> task authority
    - source-agent-matrix: repository `docs/plans/Plan_7.md` > `### 7.1 Final automated coverage matrix` -> conversation/Agent requirements
    - validation-agent: repository `backend/tests/unit/test_agent_graph.py` and `backend/tests/integration/test_agent_runner.py` -> loop/SSE/checkpoint evidence
    - validation-history: repository `backend/tests/integration/test_chat_api.py` and `backend/tests/integration/test_chat_history.py` -> public history/cursor evidence
  - Source Requirements:
    - Prove greeting/general conversation without tools, exact SSE schema/order,
      bounded context, exactly six production tools, controlled loop overflow,
      interrupt/resume infrastructure, terminal checkpoint cleanup, durable
      history hydration, pagination, and malformed-cursor `422`.
    - Prove only exact run/tool statuses enter persistence/SSE and package-owned
      checkpoint tables remain outside Alembic/application ownership.
    - Leave write identity, approval-action, and terminal-resume side-effect
      counting to (01H).
  - Dependencies: The binary Plan 6 acceptance reconciliation gate described in this batch; no Batch01 task dependency.
  - User Action: None after the batch prerequisite is satisfied.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/unit/test_sse_contract.py`, `backend/tests/unit/test_agent_context.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/integration/test_agent_runner.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/integration/test_chat_history.py`, `backend/tests/integration/test_chat_persistence.py`, `backend/tests/integration/test_interrupt_resume.py`, `backend/tests/fakes/fake_chat_model.py`, `backend/tests/fakes/synthetic_tool.py`
  - Allowed Files: the listed tests/fakes and a focused shared public/SSE helper under `backend/tests/support/**`; exclude all `backend/app/**`, domain/replay/matching/rebuild/frontend/infrastructure/docs owners.
  - Agent Work:
    1. Search the named tests, fake chat/synthetic tool, public dependency
       overrides, runner/checkpoint/history owners, and callers; map each row.
    2. Add only missing conversation/transport cases and extract a shared helper
       only when existing and new tests both use it.
    3. If a case reproduces product behavior, identify its owner/callers and
       block for a separately typed bugfix.
    4. Run focused Agent/public/history validation and lint with fresh evidence.
  - Output: Complete fake-backed conversation, Agent, SSE, history, and checkpoint coverage.
  - A1 Outcome: Every conversation/Agent/transport matrix row has deterministic passing evidence without a real provider or second harness.
  - A2 Review Focus: Feature-rubric transport coverage and helper reuse; hard gates `HG-01`, `HG-02`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover exact status/event order, controlled loop/checkpoint behavior, no production/duplicate/hardcoded path, no real provider, and fresh evidence.
  - A3 Batch Evidence: Conversation/Agent/SSE/history rows and sole ownership of transport test changes.
  - Acceptance:
    - Every listed conversation, loop, event, context, checkpoint, history, and cursor row maps to a named passing test.
    - Greetings/general questions complete without tool events and overflow fails with the stable controlled error.
    - Tests use temp SQLite/checkpoints and fake chat only; no network/live service is accessed.
    - No production, endpoint, event, status, checkpoint, or Agent architecture is changed.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/unit/test_sse_contract.py tests/unit/test_agent_context.py tests/unit/test_agent_graph.py -q` -> PASS evidence: exit `0` and unit rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_agent_runner.py tests/integration/test_chat_api.py tests/integration/test_chat_history.py tests/integration/test_chat_persistence.py tests/integration/test_interrupt_resume.py -q` -> PASS evidence: exit `0` and transport/history/interrupt rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/unit/test_sse_contract.py tests/unit/test_agent_context.py tests/unit/test_agent_graph.py tests/integration/test_agent_runner.py tests/integration/test_chat_api.py tests/integration/test_chat_history.py tests/integration/test_chat_persistence.py tests/integration/test_interrupt_resume.py tests/fakes/fake_chat_model.py tests/fakes/synthetic_tool.py tests/support` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_ENVIRONMENT` if the isolated Agent suite cannot run; `BLOCKED_SCOPE_CONFLICT` if any case exposes product behavior; `BLOCKED_AMBIGUOUS_REF` if public/SSE helper ownership cannot be consolidated without duplication.
  - Files: the files in `Likely Files` plus only the shared support helper actually reused

- [x] (01F): Close JD ingestion, provider-failure, duplicate, and Job-sync coverage gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01F)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix` and `### 7.3 Failure and recovery matrix`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` and `## 24. Local Testing Strategy`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01F)` -> task authority
    - source-jd-matrix: repository `docs/plans/Plan_7.md` > `### 7.1 Final automated coverage matrix` -> JD requirements
    - validation-jd: repository `backend/tests/integration/test_job_ingestion.py` and `backend/tests/integration/test_job_tools.py` -> persistence/tool evidence
    - validation-job-sync: repository `backend/tests/integration/test_job_sync.py` -> SQLite-first graph evidence
  - Source Requirements:
    - Prove URL/text persistence-first behavior, bounded acquisition, one
      timeout/rate retry, one invalid-schema repair, quality classification,
      exact non-failed return/failed-row retry, locked embedding, raw retention
      on failure, and SQLite-first Job sync failure.
    - Prove duplicate/retry row/provider/graph counts without testing repeated
      `(run_id, tool_call_id)` identities, which belong to (01H).
    - Use fake HTTP/provider/embedding/graph seams and no real external state.
  - Dependencies: (01B) and (01C) are A2-accepted so structured-output and embedding fake ownership is stable; the Plan 6 gate is satisfied.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/unit/test_jd_extraction.py`, `backend/tests/unit/test_jd_quality.py`, `backend/tests/unit/test_url_fetch.py`, `backend/tests/unit/test_embedding_text.py`, `backend/tests/integration/test_jobs_repository.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_job_sync.py`
  - Allowed Files: the listed test files; one shared structured-output fake under `backend/tests/fakes/**`, reusing (01B)'s artifact if present; `backend/tests/fakes/embeddings.py`; exclude all `backend/app/**`, replay/matching/rebuild/frontend/infrastructure/docs owners.
  - Agent Work:
    1. Search JD extraction/quality/fetch/embedding/persistence/tool/sync tests,
       shared fakes, and callers; map each source row before adding cases.
    2. Add only missing fake-backed domain/duplicate/failure assertions and
       reuse (01B)'s structured-output fake when present or establish the one
       shared owner after checking all existing fake callers.
    3. If a case reproduces product behavior, identify its owner/callers and
       block for a separately typed bugfix.
    4. Run focused JD/Job/sync validation and lint with fresh evidence.
  - Output: Complete fake-backed JD lifecycle, duplicate/retry, provider-failure, and Job-sync coverage.
  - A1 Outcome: Every JD matrix row has deterministic passing evidence with exact persistence and failure counts.
  - A2 Review Focus: Feature-rubric JD coverage and fake reuse; hard gates `HG-01`, `HG-02`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover persistence-first and duplicate/retry/capped repair behavior, no real external or production/duplicate/hardcoded path, and fresh evidence.
  - A3 Batch Evidence: JD lifecycle/failure/sync rows and sole ownership of Job-domain test changes.
  - Acceptance:
    - URL/text, extraction/repair, quality, embedding, duplicate/retry, raw-retention, and Job-sync rows map to passing tests.
    - Exact non-failed duplicates return and failed duplicates retry the same row without new Job/provider/graph effects.
    - Tests use fake HTTP/provider/embedding/graph and isolated SQLite only.
    - No production, model, retry, persistence, sync, endpoint, or tool contract is changed.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/unit/test_jd_extraction.py tests/unit/test_jd_quality.py tests/unit/test_url_fetch.py tests/unit/test_embedding_text.py -q` -> PASS evidence: exit `0` and unit rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_jobs_repository.py tests/integration/test_job_ingestion.py tests/integration/test_job_tools.py tests/integration/test_job_sync.py -q` -> PASS evidence: exit `0` and persistence/tool/sync rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/unit/test_jd_extraction.py tests/unit/test_jd_quality.py tests/unit/test_url_fetch.py tests/unit/test_embedding_text.py tests/integration/test_jobs_repository.py tests/integration/test_job_ingestion.py tests/integration/test_job_tools.py tests/integration/test_job_sync.py tests/fakes` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_ENVIRONMENT` if the fake-backed JD suite cannot run; `BLOCKED_SCOPE_CONFLICT` if any case exposes product behavior; `BLOCKED_AMBIGUOUS_REF` if shared structured-output ownership remains unresolved after (01B).
  - Files: the files in `Likely Files` plus only the established shared fakes actually reused

- [x] (01G): Close provider-free rebuild coverage gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01G)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix` and `### 7.4 Fresh graph and fresh-clone verification`; `docs/plans/Master_plan.md` > `## 21. Direct SQLite-to-Neo4j Synchronization` > `### 21.3 Rebuild command`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01G)` -> task authority
    - source-rebuild: repository `docs/plans/Plan_7.md` > `### 7.1 Final automated coverage matrix` -> rebuild requirements
    - validation-rebuild: repository `backend/tests/integration/test_graph_rebuild_behavior.py` and `backend/tests/integration/test_graph_rebuild_preflight.py` -> existing behavior evidence
    - validation-choice-c: repository `backend/tests/integration/test_graph_rebuild_cli.py` -> host-wrapper/target safety evidence
  - Source Requirements:
    - Prove stored-embedding preflight before clear, fresh/empty projection,
      exact endpoint-scoped entity/relationship counts, no provider call/SQLite
      mutation, repeat safety, mismatch non-zero behavior, and scoped deletion.
    - Preserve choice C: fake-backed tests may exercise rebuild logic, while the
      host wrapper remains help/version only and no live destructive action runs.
  - Dependencies: The binary Plan 6 acceptance reconciliation gate described in this batch; no Batch01 task dependency.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/integration/test_graph_rebuild_contracts.py`, `backend/tests/integration/test_graph_rebuild_preflight.py`, `backend/tests/integration/test_graph_rebuild_behavior.py`, `backend/tests/integration/test_graph_rebuild_cli.py`, `backend/tests/fakes/graph_rebuild.py`, `backend/tests/support/graph_rebuild.py`
  - Allowed Files: the listed test/fake/support files only; exclude all `backend/app/**`, `infrastructure/scripts/rebuild_neo4j.py`, Compose, matching/sync/frontend/docs owners.
  - Agent Work:
    1. Search rebuild tests/fakes/support, target/preflight/ops callers, and the
       approved host-wrapper contract; map every rebuild row.
    2. Add only missing deterministic fake-backed assertions, reusing the sole
       rebuild fake/support owners.
    3. If a case reproduces product behavior or choice-C conflict, identify the
       exact owner/callers and block for a separately typed bugfix.
    4. Run the full fake-backed rebuild regression and focused lint.
  - Output: Complete provider-free rebuild coverage with choice-C safety preserved.
  - A1 Outcome: Every rebuild matrix row passes with exact preflight, count, immutability, failure, and target evidence.
  - A2 Review Focus: Feature-rubric rebuild coverage and fake reuse; hard gates `HG-01`, `HG-02`, `HG-03`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover preflight/scoped deletion, no provider/SQLite write/live action, help-only wrapper, no production/duplicate/hardcoded path, and fresh evidence.
  - A3 Batch Evidence: Rebuild rows and sole ownership of rebuild test/fake/support changes.
  - Acceptance:
    - Mismatch fails before clear; successful fake rebuild reports exact endpoint-scoped counts and repeat safety.
    - Tests prove no embedding/provider call, SQLite mutation, unrestricted wipe, or unrelated-label count.
    - Host no-arg rebuild remains refused and choice C remains the only live path.
    - No production, wrapper, Compose, sync, or topology file is changed.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_graph_rebuild_contracts.py tests/integration/test_graph_rebuild_preflight.py tests/integration/test_graph_rebuild_behavior.py tests/integration/test_graph_rebuild_cli.py -q` -> PASS evidence: exit `0` and all rebuild rows pass; freshness: final attempt only.
    - Required (repository root): `python infrastructure/scripts/rebuild_neo4j.py --help` -> PASS evidence: exit `0`, choice-C command is documented, and no store is opened; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/integration/test_graph_rebuild_contracts.py tests/integration/test_graph_rebuild_preflight.py tests/integration/test_graph_rebuild_behavior.py tests/integration/test_graph_rebuild_cli.py tests/fakes/graph_rebuild.py tests/support/graph_rebuild.py` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_SOURCE_CONFLICT` if a case requires host-side rebuild or weaker choice-C checks; `BLOCKED_ENVIRONMENT` if fake-backed rebuild tests cannot run; `BLOCKED_SCOPE_CONFLICT` if any case exposes product behavior.
  - Files: the files in `Likely Files`

- [x] (01H): Close write-tool, approval-action, and terminal-resume idempotency gaps
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch01 - Focused Automated Contract Closure` > `(01H)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.1 Final automated coverage matrix` and `### 7.3 Failure and recovery matrix`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.2 Backend integration tests`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(01H)` -> task authority
    - source-idempotency: repository `docs/plans/Plan_7.md` > `### 7.3 Failure and recovery matrix` -> exact side-effect requirements
    - validation-replay: repository `backend/tests/integration/test_tool_replay.py` and `backend/tests/integration/test_interrupt_resume.py` -> generic identity/resume evidence
    - validation-write-tools: repository `backend/tests/integration/test_profile_approval.py` and `backend/tests/integration/test_job_tools.py` -> write-domain evidence
  - Source Requirements:
    - Prove each write tool, Save/Request Changes decision, rapid repeated
      approval, and terminal resume stores one ToolResult and performs one
      SQLite/file/graph/provider side effect per `(run_id, tool_call_id)`.
    - Prove terminal re-entry returns stored truth without repeating extraction,
      persistence, graph sync, status publication, or accepted decision.
    - Reuse the sole executor/replay identity; add no second key or local fake
      executor and make no real external call.
  - Dependencies: (01B), (01E), and (01F) are A2-accepted so domain/transport test ownership is stable.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/integration/test_tool_replay.py`, `backend/tests/integration/test_interrupt_resume.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_agent_runner.py`
  - Allowed Files: the listed test files only; exclude all `backend/app/**`, domain fakes, matching/rebuild/frontend/infrastructure/docs owners.
  - Agent Work:
    1. Search the generic executor/replay tests and every production write-tool,
       approval, resume, status-publication, and side-effect assertion/caller.
    2. Build an exact write-tool/decision identity matrix and add only missing
       repeated/re-entry cases in the established test files.
    3. Assert row/result/file/provider/graph/publication counts before and after
       replay. If behavior is wrong, block with the exact production owner and
       callers for a separately typed bugfix.
    4. Run the cross-cutting replay/resume/write-tool regression and lint.
  - Output: Complete cross-cutting write/approval/resume idempotency evidence over the one durable executor.
  - A1 Outcome: Every write identity and approval/resume re-entry path proves one stored result and one permitted side effect.
  - A2 Review Focus: Feature-rubric identity-matrix completeness; hard gates `HG-01`, `HG-02`, `HG-04`, `HG-05`, `HG-07`, and `HG-09` cover exact side-effect counts, one executor/key, terminal no-op replay, no production/duplicate/hardcoded path, no real external state, and fresh evidence.
  - A3 Batch Evidence: Idempotency rows and known sequential ownership over shared profile/Job test files after (01B)/(01F).
  - Acceptance:
    - Every write tool and both approval actions have same-identity first-run/replay evidence with exact counts.
    - Terminal resume/repeated rapid action accepts once and never replays graph/provider/persistence work.
    - Status publication and stored ToolResult remain exact and truthful on success/failure/replay.
    - No production file, second key/executor, retry path, or external call is added.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_tool_replay.py tests/integration/test_interrupt_resume.py tests/integration/test_profile_approval.py tests/integration/test_job_tools.py tests/integration/test_agent_runner.py -q` -> PASS evidence: exit `0` and identity/side-effect rows pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/integration/test_tool_replay.py tests/integration/test_interrupt_resume.py tests/integration/test_profile_approval.py tests/integration/test_job_tools.py tests/integration/test_agent_runner.py` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_SCOPE_CONFLICT` if any matrix row exposes production behavior; `BLOCKED_AMBIGUOUS_REF` if more than one replay identity/executor appears authoritative; `BLOCKED_ENVIRONMENT` if the isolated suite cannot run.
  - Files: the files in `Likely Files`

## Mandatory Batch02 - Disposable Public-Boundary Demo Flow

### Goal

Add one fake-backed E2E test that proves the locked greeting-to-matching flow
through public FastAPI boundaries with disposable SQLite, files, checkpoints,
and controlled graph/provider fakes.

### Dependencies

- Batch01 is fully A2-accepted and establishes stable focused contracts/fakes.

### Scope Boundary

This batch adds one test flow and only genuinely shared test support. It does
not call real services, use developer data/volumes, test the frontend through
browser automation, or repair product code. A reproduced product defect blocks
for an owner-scoped Batch01 repair.

### Tasks

- [x] (02A): Add the complete fake-backed public-boundary E2E smoke
  - Task Type: feature
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch02 - Disposable Public-Boundary Demo Flow` > `(02A)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.2 End-to-end smoke contract`; `docs/plans/Plan_7.md` > `## 9. Verification & Testing Plan` > `### Full local automated suite`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.4 End-to-end smoke test`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(02A)` -> task authority
    - source-e2e: repository `docs/plans/Plan_7.md` > `### 7.2 End-to-end smoke contract` -> exact flow/assertions
    - validation-public-harness: repository `backend/tests/integration/test_chat_api.py` -> reusable dependency override/SSE helpers and public-boundary validation authority
    - existing-test-foundation: repository `backend/tests/support/db_migration.py` and `backend/tests/fakes/` -> disposable state/fake owners
  - Source Requirements:
    - Exercise greeting with no tools, same-conversation continuation,
      synthetic PDF upload, attachment turn, validated draft, approval_required,
      save via resume, synthetic JD text save/extract/embed/sync, and matching
      with ordered score/gaps.
    - Assert durable messages/runs/tools, one active CV/profile, deleted draft
      and terminal checkpoints, processed scorable Job, matching revisions,
      exact statuses/events, and no false-success text.
    - Use dependency-overridden provider/embedding/graph fakes and disposable
      SQLite/files only; never read root `.env` or developer state.
  - Dependencies: (01A) through (01H) are A2-accepted.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `backend/tests/e2e/__init__.py`, `backend/tests/e2e/test_demo_flow.py`, `backend/tests/support/public_api.py`, `backend/tests/fakes/embeddings.py`, `backend/tests/fakes/matching.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/conftest.py`
  - Allowed Files: `backend/tests/e2e/**`; one focused reusable helper under `backend/tests/support/**`; existing `backend/tests/fakes/**` only to consolidate a fake used by E2E and an existing test; `backend/tests/integration/test_chat_api.py` only to extract existing public/SSE helpers; `backend/tests/conftest.py` only for a shared fixture; exclude all `backend/app/**`, frontend, infrastructure, docs, real `.env`, and live data.
  - Agent Work:
    1. Search `test_chat_api.py`, test support/fakes, profile/JD invoker fakes,
       registry/dependency injection, and fixture callers before writing.
    2. Refactor existing public API/SSE helpers or duplicated fake invokers only
       where E2E creates real second-use reuse; do not copy them locally.
    3. Implement the exact sequence in one E2E test with isolated migrated
       SQLite, temp files/checkpoints, controlled Neo4j, and fake adapters.
    4. Assert durable state and exact event/status order after each boundary,
       including replay-safe approval and absence of false success.
    5. Run E2E plus affected integration regressions and quality gates.
  - Output: `backend/tests/e2e/test_demo_flow.py` proving the complete locked public-boundary flow without real external state.
  - A1 Outcome: One disposable test completes greeting, profile approval, JD persistence/sync, and deterministic matching with all durable assertions.
  - A2 Review Focus: Feature-rubric public-boundary completeness and helper reuse; hard gates `HG-01`, `HG-02`, `HG-03`, `HG-04`, `HG-05`, `HG-07`, `HG-08`, and `HG-09` cover durable assertions, no hardcoded false flow/product diff, no provider/network/developer-state access, matching validated revision, and fresh evidence.
  - A3 Batch Evidence: The sole Batch02 E2E requirement row and ownership of the new test/support artifacts.
  - Acceptance:
    - The exact source sequence completes through public FastAPI APIs and resume semantics.
    - Durable database/files/checkpoint/tool/result assertions match the source and no false-success text appears.
    - The test is deterministic, fake-backed, and cannot access root `.env`, developer SQLite/files, live Neo4j, network, or browser.
    - No duplicate public API/SSE helper or structured-output fake is introduced.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m pytest tests/e2e/test_demo_flow.py -q` -> PASS evidence: exit `0` and complete flow passes; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m pytest tests/integration/test_chat_api.py tests/integration/test_profile_approval.py tests/integration/test_job_tools.py tests/integration/test_match_jobs.py -q` -> PASS evidence: exit `0` and affected public/domain regressions pass; freshness: final attempt only.
    - Required (repository root): `Set-Location backend; python -m ruff check tests/e2e tests/support tests/fakes tests/integration/test_chat_api.py` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_SCOPE_CONFLICT` if E2E exposes a product defect requiring `backend/app/**`; `BLOCKED_AMBIGUOUS_REF` if public API or structured-output fake ownership cannot be consolidated without competing owners; `BLOCKED_ENVIRONMENT` if the isolated test toolchain is unavailable.
  - Files: `backend/tests/e2e/**`, one reused helper under `backend/tests/support/**`, and only the existing fake/integration fixture files actually refactored

## Mandatory Batch03 - Static Safeguards and Release Documentation

### Goal

Audit the tracked runtime/configuration surface, initialize sanitized release
evidence, and revise the existing README into the exact executable local MVP
guide required before clean-checkout verification.

### Dependencies

- Batch02 is fully A2-accepted and all local automated commands are stable.

### Scope Boundary

This batch performs static repository/configuration/documentation work only. It
does not read secret values, run a live provider, start Compose, mutate data,
add a security subsystem, or repair product behavior.

### Tasks

- [x] (03A): Audit environment, secrets, tracked data, ports, and excluded scope
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch03 - Static Safeguards and Release Documentation` > `(03A)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.6 Environment, secret, and data audit` and `### 7.7 Final scope audit`; `docs/plans/Plan_7.md` > `## 9. Verification & Testing Plan` > `### Repository checks`; `docs/plans/Master_plan.md` > `### 2.2 Explicitly out of scope`, `## 22. Local Demo Safeguards`, and `## 23. Environment Configuration`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(03A)` -> task authority
    - source-safeguards: repository `docs/plans/Plan_7.md` > `### 7.6 Environment, secret, and data audit` -> audit requirements
    - validation-settings: repository `.env.example`, `.gitignore`, `backend/app/core/settings.py`, and `backend/tests/unit/test_settings.py` -> one-environment authority
    - validation-compose: repository `infrastructure/docker-compose.yml` -> service/port/volume authority
  - Source Requirements:
    - Prove one ignored root `.env`, safe/complete `.env.example`, no nested
      runtime env, and no Compose runtime load of `.env.example`.
    - Audit tracked state and history candidates without printing credential
      values; allow only explicitly synthetic fixture PDFs and no runtime DB,
      upload, graph data/log, real CV/JD, provider response, or CI workflow.
    - Prove loopback-only published ports, safe payload/log boundaries, exactly
      three services, and absence of implemented/configured excluded scope.
    - Initialize `local_release_checklist.md` with dated evidence rows and exact
      owners; do not create a second progress tracker.
  - Dependencies: (02A) is A2-accepted.
  - User Action: If a credential candidate is found, stop; the user must remove it from tracked/current state, rotate it externally, and confirm rotation without sharing the value.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 7200
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `docs/acceptance/local_release_checklist.md`, `.env.example`, `.gitignore`, `infrastructure/docker-compose.yml`, `backend/app/core/settings.py`, `backend/tests/unit/test_settings.py`
  - Allowed Files: `docs/acceptance/local_release_checklist.md`, `.env.example`, `.gitignore`, `infrastructure/docker-compose.yml`, `infrastructure/docker/backend.Dockerfile`, `infrastructure/docker/frontend.Dockerfile`, `backend/app/core/settings.py`, `backend/tests/unit/test_settings.py`, `frontend/src/vite-env.d.ts`; exclude root `.env`, runtime data, product features, dependencies, new services, CI, and security tooling.
  - Agent Work:
    1. Search current/tracked/history filenames, environment loaders, Compose,
       Dockerfiles, settings/tests, manifests, public payload/log owners, and
       UI configuration without reading or echoing root `.env` values.
    2. Classify candidate history/current secret paths using filenames and
       sanitized metadata only; legitimate fake/test auth construction is not a
       credential, but every candidate must be dispositioned.
    3. Audit services/ports/volumes, tracked runtime data, synthetic fixtures,
       CI absence, and implemented/configured Master exclusions.
    4. Fix only a demonstrated config/docs defect in the allowed owner; do not
       add production-security scope.
    5. Create one concise `local_release_checklist.md` with exact headings
       `## Automated Coverage`, `## Static Safeguards`, `## Fresh Clone`,
       `## Failure and Recovery`, `## Fresh Graph Rebuild`, `## Manual Demo`,
       `## Final Scope Audit`, and `## Final Rerun`. Every evidence table uses
       `Requirement | Evidence | Status | Date (UTC)`, with plain status cells
       and no task checkboxes.
  - Output: A safe static release audit and the single source-supported local release evidence checklist.
  - A1 Outcome: Static repository/configuration checks pass with sanitized evidence and one initialized release checklist.
  - A2 Review Focus: Docs-config rubric accuracy and minimal config scope; hard gates `HG-01` through `HG-07` cover no secret values, exact env/service/port/data sets, complete history disposition, no authority/security/product drift, and one configuration/checklist truth.
  - A3 Batch Evidence: Static safeguard/scope rows and first ownership of `local_release_checklist.md`.
  - Acceptance:
    - Only root `.env` and tracked `.env.example` exist outside ignored tool directories; root `.env` is ignored and untracked.
    - Secret fields in `.env.example` are empty, documented variables align with settings/Compose, and no runtime loads `.env.example`.
    - Only synthetic fixture PDFs are tracked; no runtime DB/upload/graph/log/provider response or CI workflow is tracked or present as implemented scope.
    - Compose declares exactly frontend/backend/neo4j with loopback published ports and no source/env-file mount.
    - The checklist contains all required evidence sections, uses the exact
      four-column evidence-table contract, and has no checklist syntax.
  - Validation:
    - Required (repository root): `$envFiles = @(rg --files --hidden --no-ignore -g '.env*' -g '!.git/**' -g '!**/node_modules/**' -g '!**/.venv/**'); if (@($envFiles | Sort-Object) -join ',' -ne '.env,.env.example') { $envFiles; throw 'unexpected environment file' }; git check-ignore -q .env; if ($LASTEXITCODE -ne 0) { throw 'root .env is not ignored' }; $trackedEnv = @(git ls-files -- .env); if ($LASTEXITCODE -ne 0) { throw 'tracked environment query failed' }; if ($trackedEnv) { throw 'root .env is tracked' }` -> PASS evidence: exit `0` and only the approved two root names exist; freshness: final attempt only.
    - Required (repository root): `$values = @{}; Get-Content .env.example | Where-Object { $_ -match '^[A-Z0-9_]+=' } | ForEach-Object { $name, $value = $_ -split '=', 2; if ($values.ContainsKey($name)) { throw "duplicate template variable: $name" }; $values[$name] = $value }; foreach ($name in @('NEO4J_PASSWORD','SHOPAIKEY_API_KEY')) { if (-not $values.ContainsKey($name) -or $values[$name] -ne '') { throw "unsafe or missing empty template secret field: $name" } }; $settingsNames = @([regex]::Matches((Get-Content -Raw backend/app/core/settings.py),'(?m)^    ([A-Z][A-Z0-9_]+):') | ForEach-Object { $_.Groups[1].Value }); $expected = @($settingsNames + 'VITE_API_BASE_URL' | Sort-Object -Unique); $composeNames = @([regex]::Matches((Get-Content -Raw infrastructure/docker-compose.yml),'\$\{([A-Z][A-Z0-9_]+)\}') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique); $templateNames = @($values.Keys | Sort-Object); if (Compare-Object $templateNames $expected) { throw '.env.example and Settings variable sets differ' }; if (Compare-Object $templateNames $composeNames) { throw '.env.example and Compose variable sets differ' }; Set-Location backend; python -m pytest tests/unit/test_settings.py -q` -> PASS evidence: exact variable sets, empty secrets, and settings tests pass; freshness: final attempt only.
    - Required (repository root): `$tracked = @(git ls-files); $history = @(git log --all --name-only --pretty=format: | Where-Object { $_ }); $paths = @($tracked + $history | Sort-Object -Unique); $forbidden = @($paths | Where-Object { $_ -match '(?i)^data/|^backend/(runtime|uploads?)/|(^|/)neo4j/(data|logs)(/|$)|(^|/)neo4j_(data|logs)(/|$)|\.(db|sqlite|sqlite3)$' }); if ($forbidden) { $forbidden; throw 'runtime data exists in tracked history' }; $badPdf = @($paths | Where-Object { $_ -match '(?i)\.pdf$' -and $_ -notmatch '^backend/tests/fixtures/cv/' }); if ($badPdf) { $badPdf; throw 'non-synthetic PDF exists in tracked history' }; if (Test-Path '.github/workflows') { throw 'CI workflow is out of scope' }` -> PASS evidence: no forbidden current/historical runtime/real-data/CI path; freshness: final attempt only.
    - Required (repository root): `$lines = Get-Content infrastructure/docker-compose.yml; $services = @(); $ports = @(); $section = ''; foreach ($line in $lines) { if ($line -match '^(services|volumes):\s*$') { $section = $Matches[1]; continue }; if ($section -eq 'services' -and $line -match '^  ([a-z][a-z0-9_-]+):\s*$') { $services += $Matches[1] }; if ($line -match '^    ports:\s*$') { $section = 'ports'; continue }; if ($section -eq 'ports' -and $line -match '^      -\s+"?([^"\s]+)"?\s*$') { $ports += $Matches[1]; continue }; if ($section -eq 'ports' -and $line -match '^    \S') { $section = 'services' } }; $expectedServices = @('backend','frontend','neo4j'); $expectedPorts = @('127.0.0.1:5173:5173','127.0.0.1:8000:8000','127.0.0.1:7474:7474','127.0.0.1:7687:7687'); if (Compare-Object @($services | Sort-Object) @($expectedServices | Sort-Object)) { throw 'Compose service set differs' }; if (Compare-Object @($ports | Sort-Object) @($expectedPorts | Sort-Object)) { throw 'Compose published-port set differs' }; Set-Location backend; python -m pytest tests/unit/test_shopaikey_chat.py tests/unit/test_tool_result.py tests/unit/test_url_fetch.py -q` -> PASS evidence: exact service/loopback-port sets and sanitization tests pass; freshness: final attempt only.
    - Required sanitized audit (repository root): `$pattern = '(SHOPAIKEY_API_KEY|NEO4J_PASSWORD)[=:][^[:space:]]+|Authorization.{0,20}Bearer|sk-[A-Za-z0-9_-]{20,}'; $current = @(git grep -I -l -E $pattern -- . 2>$null); $history = @(git log --all -G $pattern --format='commit:%H' --name-only -- .); $current; $history` -> PASS evidence: output contains current paths and historical `commit:path` groupings only, never matched values, and every candidate revision is classified as safe template, synthetic fake, required runtime construction, or a resolved/rotated incident; freshness: final attempt only.
    - Required (repository root): `git diff --check; if ($LASTEXITCODE -ne 0) { throw 'whitespace errors' }; $bad = Select-String -Path docs/acceptance/local_release_checklist.md -Pattern '^- \[[ xX]\]'; if ($bad) { $bad; throw 'release checklist must not duplicate task status' }` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_USER_ACTION` immediately on a credential finding until external rotation/removal is confirmed; `BLOCKED_SCOPE_CONFLICT` if correction requires product/security architecture; `BLOCKED_ENVIRONMENT` if Git/rg/Python required for the audit is unavailable.
  - Files: `docs/acceptance/local_release_checklist.md` and only a demonstrated config/test owner named in `Allowed Files`

- [x] (03B): Revise the root README into the exact local release guide
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch03 - Static Safeguards and Release Documentation` > `(03B)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.5 README contract`; `docs/plans/Plan_7.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_7.md` > `## 10. Final Handoff and Completion Contract`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.5 Local verification commands`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(03B)` -> task authority
    - source-readme: repository `docs/plans/Plan_7.md` > `### 7.5 README contract` -> exact content contract
    - validation-readme: repository `README.md` -> document under revision
    - source-choice-c: repository `docs/tasks/task_5.md` > `(03D)` -> approved rebuild context, as confirmed by the user
  - Source Requirements:
    - Document purpose/narrow scope; architecture/ownership; repository layout;
      prerequisites and one root `.env`; exact bootstrap/Compose and each
      single-purpose backend/frontend/E2E/Neo4j/provider/rebuild/manual command;
      full demo; data persistence/safe disposable cleanup; failures/recovery;
      safeguards/limitations; local-only synthetic/no-CI testing policy.
    - Commands must state their working directory, be executable verbatim, and
      use safe non-secret Compose checks and choice C.
    - Consolidate stale phase diary material as needed; do not add placeholder
      commands, production claims, or a no-argument host rebuild path.
  - Dependencies: (03A) is A2-accepted and owns the final static findings/command boundaries.
  - User Action: None.
  - Runtime Policy:
    - check_after_seconds: 600
    - timeout_seconds: 5400
    - quiet_until_due: true
    - max_repair_attempts: 2
  - Likely Files: `README.md`
  - Allowed Files: `README.md` only; exclude application, tests, config, plans, checklists, and root `.env`.
  - Agent Work:
    1. Search existing README sections/commands and authoritative repository
       scripts/manifests before writing; reuse exact current commands.
    2. Revise/consolidate the README around the eleven Plan 7 contract items,
       preserving only current architecture and release-relevant detail.
    3. Make every required command single-purpose, cwd-explicit, non-placeholder,
       and safe: Compose config uses non-secret output, live rebuild uses choice
       C, disposable startup uses detached `--wait`, teardown names its project,
       and the host wrapper is help only.
    4. Cross-check every path/command against repository owners and run static
       documentation validation. Live verbatim execution belongs to (04A).
  - Output: One maintainable root README sufficient for a fresh local clone and honest MVP operation/recovery.
  - A1 Outcome: README contains every Plan 7 release section and exact safe command with no stale or conflicting runtime guidance.
  - A2 Review Focus: Docs-config rubric completeness and command accuracy; hard gates `HG-01` through `HG-07` cover all eleven source items, executable ownership, choice C, one root env, safe cleanup, honest limits, and no conflicting/duplicate guidance.
  - A3 Batch Evidence: README requirement coverage and sole ownership of the release guide.
  - Acceptance:
    - Every Plan 7 README item appears once with current repository-aligned content.
    - Backend lint/type/unit/integration/E2E; frontend install/lint/type/test/build; live Neo4j/provider; rebuild; manual JD; and Compose commands are exact and cwd-explicit.
    - Cleanup distinguishes named disposable volumes from user data and never suggests deleting normal volumes.
    - README states no authentication/public exposure/production-security claim, local-only tests, synthetic committed fixtures, real data outside Git, and no CI.
    - The host wrapper is help/version only and the canonical rebuild command is the approved Compose exec path.
  - Validation:
    - Required (repository root): `rg -n '^## ' README.md` -> PASS evidence: purpose/scope, architecture, layout, prerequisites/environment, setup/startup, verification, demo, data/cleanup, failure/recovery, safeguards/limitations, and testing policy headings are reviewable; freshness: final attempt only.
    - Required (repository root): `rg -n 'tests/e2e/test_demo_flow\.py|diagnose_shopaikey\.py|manual_jd_checklist\.md|config --quiet|--wait|exec -T backend python -m app\.graph\.rebuild|rebuild_neo4j\.py --help|down -v --remove-orphans' README.md` -> PASS evidence: every critical exact command/safety token is present; freshness: final attempt only.
    - Required (repository root): `git diff --check -- README.md` -> PASS evidence: exit `0`; freshness: final attempt only.
    - Required manual check (repository root): compare every fenced required command with its script/package/Compose owner and record the verbatim command ledger in A1 evidence -> PASS evidence: no placeholder or stale path; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_SOURCE_CONFLICT` if README requirements cannot preserve choice C or one-root-env safety; `BLOCKED_MISSING_REF` if a required command has no repository owner; `BLOCKED_SCOPE_CONFLICT` if command correctness requires non-documentation changes.
  - Files: `README.md`

## Mandatory Batch04 - Disposable Local Release Evidence

### Goal

Prove the documented release from a clean checkout and then execute the full
real-provider/manual failure, demo, fresh-graph, rebuild, and recovery sequence
only in explicitly named disposable local resources.

### Dependencies

- Batch03 is fully A2-accepted; README and release-checklist structure are stable.

### Scope Boundary

These tasks write sanitized evidence only. They do not edit product/config/test
code, expose secrets/raw documents, use browser automation, or touch normal
developer volumes. Any implementation defect blocks for an owner-scoped repair.

### Tasks

- [x] (04A): Verify every README command from a disposable clean checkout
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch04 - Disposable Local Release Evidence` > `(04A)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.4 Fresh graph and fresh-clone verification` and `### 7.5 README contract`; `docs/plans/Plan_7.md` > `## 9. Verification & Testing Plan` > `### Compose/release checks`; `docs/plans/Master_plan.md` > `## 25. Implementation Phases` > `### Phase 6 — Polish and local release`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(04A)` -> task authority
    - source-fresh-clone: repository `docs/plans/Plan_7.md` > `### 7.4 Fresh graph and fresh-clone verification` -> clean-checkout procedure
    - validation-command-ledger: repository `README.md` > release verification commands -> verbatim command authority
    - validation-checklist: repository `docs/acceptance/local_release_checklist.md` > fresh-clone section -> evidence owner
  - Source Requirements:
    - Use a clean exported checkout or disposable worktree, create only its root
      untracked `.env` from `.env.example`, supply user-managed local secrets,
      and run every README command without undocumented setup/database edits.
    - Prove backend/frontend automated gates, provider diagnostic, safe Compose
      config/startup/health, exactly three services, loopback ports, and local
      persistence using named disposable project `jobagent-plan7-clone`.
    - Teardown only that project/volumes and safely remove only the verified
      disposable worktree after evidence is captured.
  - Dependencies: (03A) and (03B) are A2-accepted.
  - User Action: Provide a valid ignored root environment in the disposable checkout, Docker, free loopback ports, provider/network access, and permission to create/remove only the named worktree and `jobagent-plan7-clone` project/volumes; never share secret values.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/local_release_checklist.md`
  - Allowed Files: `docs/acceptance/local_release_checklist.md` fresh-clone/README-command section only; external disposable worktree and named Docker resources as authorized; exclude all tracked code/config/README changes, normal root `.env`, and normal developer Docker resources.
  - Agent Work:
    1. Resolve and verify an unused absolute sibling worktree path under the
       repository parent; refuse an existing/unexpected path, then create a
       detached clean worktree at current HEAD.
    2. Copy `.env.example` only to that worktree's ignored root `.env`; pause for
       the user to supply local secret values without reading/printing them.
    3. Execute every README required command verbatim from its documented cwd,
       recording command, exit code, date, and sanitized result. Use Compose
       project `jobagent-plan7-clone`, detached startup, health, and service/port
       checks rather than an unbounded foreground process.
    4. Treat skip, failure, undocumented setup, lockfile change, database edit,
       provider failure, or secret-bearing output as failure, not PASS.
    5. Teardown only `jobagent-plan7-clone` with its volumes. Verify the exact
       registered worktree path is the intended sibling, its tracked status is
       clean, and it is not the main worktree; then use the explicitly authorized
       forced Git worktree removal to clear its ignored generated artifacts and
       prune only its registration.
    6. Record dated sanitized evidence in only the assigned checklist section.
  - Output: Dated proof that a clean checkout plus one root `.env` executes every documented command and starts the three-service local stack.
  - A1 Outcome: Every README command passes verbatim in a clean disposable checkout with no undocumented step or data edit.
  - A2 Review Focus: Docs-config-rubric evidence accuracy; hard gates `HG-01` through `HG-06` plus `HG-08` cover clean validated HEAD, one-env setup, every command/no skips, exact healthy services, provider sanitation, safe forced named cleanup, and checklist-only diff.
  - A3 Batch Evidence: Fresh-clone command/startup rows and ownership of `jobagent-plan7-clone` evidence.
  - Acceptance:
    - The disposable checkout starts from current HEAD with no tracked modification and only one ignored root `.env`.
    - Every README command executes verbatim with current PASS evidence; automated tests make no real provider call except the diagnostic.
    - Compose reports exactly frontend/backend/neo4j on loopback ports and health is available.
    - Only the named project volumes/worktree are removed; normal developer resources remain untouched.
  - Validation:
    - Required (repository root): `$releaseRoot = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent (Get-Location).Path) 'JobAgent-plan7-release')); if (Test-Path -LiteralPath $releaseRoot) { throw "disposable worktree path already exists: $releaseRoot" }; git worktree add --detach $releaseRoot HEAD; if ($LASTEXITCODE -ne 0) { throw 'disposable worktree creation failed' }; git worktree list --porcelain` -> PASS evidence: creation exits `0`, the exact resolved path is registered at current HEAD, and no pre-existing target was reused; freshness: final attempt only.
    - Required (disposable checkout root): execute the complete required command ledger from `README.md`, including `python -m pip install -e .\backend`, backend lint/type/unit/integration/E2E, frontend `npm ci`/lint/type/test/build, `python infrastructure/scripts/diagnose_shopaikey.py`, `python infrastructure/scripts/rebuild_neo4j.py --help`, and manual-checklist discovery -> PASS evidence: every command exits `0` with sanitized output; freshness: final attempt only.
    - Required fresh-project check (disposable checkout root): `$project = 'jobagent-plan7-clone'; $containers = @(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.ID}}'); if ($LASTEXITCODE -ne 0) { throw 'Docker container query failed' }; $volumes = @(docker volume ls -q --filter "label=com.docker.compose.project=$project"); if ($LASTEXITCODE -ne 0) { throw 'Docker volume query failed' }; $networks = @(docker network ls -q --filter "label=com.docker.compose.project=$project"); if ($LASTEXITCODE -ne 0) { throw 'Docker network query failed' }; $existing = @($containers + $volumes + $networks | Where-Object { $_ }); if ($existing.Count -ne 0) { $existing; throw 'named clone project is not fresh' }` -> PASS evidence: no container/volume/network with the named project label exists before startup; freshness: final attempt only.
    - Required (disposable checkout root): `$project = 'jobagent-plan7-clone'; $expected = @('backend','frontend','neo4j'); $services = @(docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project config --services); if ($LASTEXITCODE -ne 0 -or (Compare-Object @($services | Sort-Object) @($expected | Sort-Object))) { throw 'Compose config/service set failed' }; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project config --quiet; if ($LASTEXITCODE -ne 0) { throw 'Compose config failed' }; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project up --build -d --wait --wait-timeout 180; if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed' }; $rows = @(docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project ps --format json | ConvertFrom-Json); if ($LASTEXITCODE -ne 0 -or $rows.Count -ne 3) { throw 'Compose status failed' }; foreach ($name in $expected) { $row = @($rows | Where-Object Service -eq $name); if ($row.Count -ne 1 -or $row[0].State -ne 'running' -or $row[0].Health -ne 'healthy') { throw "service not healthy: $name" } }` -> PASS evidence: exact config set and exactly three running/healthy services with no resolved secret output; freshness: final attempt only.
    - Required authorized teardown (disposable checkout root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-clone down -v --remove-orphans` -> PASS evidence: exit `0` and only named project resources are removed; freshness: final attempt only.
    - Required authorized worktree cleanup (repository root): recompute `$releaseRoot` exactly as above; verify it is the registered intended sibling path, is beneath the repository parent, and is not the main worktree; run `$tracked = @(git -C $releaseRoot status --porcelain --untracked-files=no); if ($LASTEXITCODE -ne 0 -or $tracked) { $tracked; throw 'disposable worktree has tracked changes' }; git worktree remove --force $releaseRoot; if ($LASTEXITCODE -ne 0) { throw 'verified disposable worktree removal failed' }; git worktree prune; if ($LASTEXITCODE -ne 0) { throw 'worktree prune failed' }` -> PASS evidence: exit `0` and only the verified disposable worktree, ignored environment, and generated artifacts are removed; freshness: final attempt only.
    - Required (repository root): `git diff --check -- docs/acceptance/local_release_checklist.md` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_USER_ACTION` if credentials, Docker/network, free ports, or authorization are unavailable; `BLOCKED_ENVIRONMENT` if a documented command/tool cannot run; `BLOCKED_PERMISSION` if named worktree/project lifecycle is not permitted; `BLOCKED_SCOPE_CONFLICT` if a product/config/doc defect is found.
  - Files: `docs/acceptance/local_release_checklist.md`

- [x] (04B): Execute the manual demo, failure matrix, and fresh-volume rebuild
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch04 - Disposable Local Release Evidence` > `(04B)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 7. Technical Specifications` > `### 7.3 Failure and recovery matrix` and `### 7.4 Fresh graph and fresh-clone verification`; `docs/plans/Plan_7.md` > `## 9. Verification & Testing Plan` > `### Explicit provider and graph checks` and `### Compose/release checks`; `docs/plans/Plan_7.md` > `## 10. Final Handoff and Completion Contract`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(04B)` -> task authority
    - source-live-matrix: repository `docs/plans/Plan_7.md` > `### 7.3 Failure and recovery matrix` -> live/automated evidence rows
    - validation-manual-jd: repository `docs/acceptance/manual_jd_checklist.md` -> retained prior acceptance and normalization observation
    - validation-choice-c: repository `backend/app/graph/rebuild_target.py` > `CANONICAL_COMPOSE_REBUILD_COMMAND` -> live rebuild authority
    - validation-release: repository `docs/acceptance/local_release_checklist.md` > live demo/failure/rebuild sections -> evidence owner
  - Source Requirements:
    - With real configured provider and Astryx UI, complete greeting, CV upload,
      draft review/change/save, restart persistence, JD URL/text save, matching,
      score/gap explanation, and truthful tool/history states.
    - Combine current automated evidence for controlled timeout/rate/schema/loop/
      replay rows with live observations for disconnect, duplicate/approval
      actions, Neo4j sync/match outage, revision mismatch, and recovery.
    - Populate SQLite with synthetic accepted data, recreate only a named fresh
      Neo4j volume, run choice-C rebuild, compare source/projection counts, and
      prove revision-safe matching afterward with no provider call/SQLite write
      during rebuild.
    - Explicitly disposition the existing manual JD normalization observation;
      any unresolved false-success/ranking inconsistency blocks release.
  - Dependencies: (04A) is A2-accepted; Batch01/02 automated evidence is current and README commands passed cleanly.
  - User Action: Provide/retain valid ignored credentials, Docker, free ports, network/provider access, and permission for project `jobagent-plan7-demo`; perform or confirm browser-visible UI/disconnect/rapid-action observations. Never paste secrets or raw CV/JD text into evidence.
  - Runtime Policy:
    - check_after_seconds: 900
    - timeout_seconds: 14400
    - quiet_until_due: true
    - max_repair_attempts: 1
  - Likely Files: `docs/acceptance/local_release_checklist.md`
  - Allowed Files: `docs/acceptance/local_release_checklist.md` live failure/demo/rebuild sections only; external project `jobagent-plan7-demo` and its exact volumes as authorized; exclude application/tests/config/README/manual-JD edits, normal root data, and any unnamed Docker resource.
  - Agent Work:
    1. Start only named project `jobagent-plan7-demo`; verify health and loopback
       endpoints without capturing resolved environment values.
    2. Through the real UI/provider, perform the full source sequence with
       synthetic inputs, including request-changes then save, restart hydration,
       URL and text JD, duplicate actions, and match explanations.
    3. Exercise visible disconnect/recovery and rapid repeated approval/terminal
       resume; combine these observations with fresh Batch01/02 controlled test
       evidence for provider retry, invalid schema, loop overflow, and every
       write-tool identity.
    4. Stop Neo4j, save one synthetic JD, and observe committed SQLite plus
       `NEO4J_SYNC_FAILED`; match must return `NEO4J_UNAVAILABLE`. Restart Neo4j
       and observe `NEO4J_REBUILD_REQUIRED` with zero results.
    5. Stop/down only the named project while retaining its application volume;
       inspect Compose labels for the exact named Neo4j data/log volumes before
       removing only those volumes. Restart to create a fresh empty graph.
    6. Record sanitized SQLite source counts and pre-rebuild SQLite metadata,
       run the canonical in-container rebuild, compare printed entity/
       relationship counts with source projections, verify SQLite metadata is
       unchanged, and prove matching revisions/results pass.
    7. Resolve the prior manual normalization observation as consistent evidence
       or a reproducible defect. Record only observed dated outcomes; never tune
       weights, fabricate evidence, or repair code in this task.
    8. Teardown only `jobagent-plan7-demo` and its volumes after evidence is
       captured, then update only assigned checklist sections.
  - Output: Complete dated sanitized live demo, failure/recovery, fresh-graph, rebuild, and matching evidence.
  - A1 Outcome: The disposable real local stack completes the full demo and every release failure/rebuild row without false success or unsafe cleanup.
  - A2 Review Focus: Docs-config-rubric observed-evidence accuracy; hard gates `HG-01` through `HG-06` plus `HG-08` cover browser truth, evidence labeling, exact failures/side effects, fresh-volume/SQLite immutability, choice C, resolved normalization, sanitation, and named teardown.
  - A3 Batch Evidence: Live demo/failure/rebuild rows and combined file/resource ownership for the disposable release batch.
  - Acceptance:
    - Every failure/recovery row has dated PASS evidence from the correct controlled automated or live boundary; no assumption is marked observed.
    - The full UI flow and restart hydration complete with truthful exact statuses, one accepted action, and no false success.
    - Fresh Neo4j rebuild counts agree with SQLite/approved seed projections, makes no provider call/SQLite mutation, and matching passes revision checks afterward.
    - The manual normalization observation is explicitly resolved; any inconsistency leaves the task unchecked.
    - Only named disposable resources are removed and no secret/raw document is recorded.
  - Validation:
    - Required (repository root): `python infrastructure/scripts/diagnose_shopaikey.py` -> PASS evidence: exit `0` and terminal `SHOPAIKEY_COMPATIBILITY=PASS` with sanitized output; freshness: final attempt only.
    - Required (repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-demo up --build -d --wait --wait-timeout 180; if ($LASTEXITCODE -ne 0) { throw 'demo Compose startup failed' }; $health = Invoke-RestMethod http://127.0.0.1:8000/api/health; if ($health.overall -ne 'available') { throw 'demo health unavailable' }; $health` -> PASS evidence: named stack starts and reports available components without connection details; freshness: final attempt only.
    - Required manual check: perform the complete greeting/CV/change/save/restart/JD URL+text/duplicate/match/explanation flow and disconnect/rapid-action observations in the Astryx UI -> PASS evidence: dated sanitized rows with visible state and durable rehydrate result; freshness: final attempt only.
    - Required outage checks (repository root): run `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-demo stop neo4j; if ($LASTEXITCODE -ne 0) { throw 'Neo4j stop failed' }`, perform the source-listed save/match observations, then run `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-demo start neo4j; if ($LASTEXITCODE -ne 0) { throw 'Neo4j start failed' }` -> PASS evidence: `NEO4J_SYNC_FAILED`, `NEO4J_UNAVAILABLE`, then `NEO4J_REBUILD_REQUIRED`, all with zero false-success/partial ranking; freshness: final attempt only.
    - Required fresh-volume check (repository root): `$project = 'jobagent-plan7-demo'; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project down --remove-orphans; if ($LASTEXITCODE -ne 0) { throw 'named project stop failed' }; $volumes = @("${project}_neo4j_data","${project}_neo4j_logs"); foreach ($volume in $volumes) { $owner = docker volume inspect $volume --format '{{ index .Labels "com.docker.compose.project" }}'; if ($LASTEXITCODE -ne 0 -or $owner -ne $project) { throw "refusing unverified volume: $volume" } }; docker volume rm $volumes; if ($LASTEXITCODE -ne 0) { throw 'verified graph-volume removal failed' }; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project up -d --wait --wait-timeout 180; if ($LASTEXITCODE -ne 0) { throw 'fresh graph startup failed' }; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project exec -T backend python -m app.graph.rebuild; if ($LASTEXITCODE -ne 0) { throw 'choice-C rebuild failed' }` -> PASS evidence: only label-verified named graph volumes are recreated, rebuild exits `0` with source-consistent Candidate/Job/Skill/relationship counts, no provider call, and unchanged SQLite metadata; freshness: final attempt only.
    - Required post-rebuild check: request matching through the same public/UI flow -> PASS evidence: revision gate passes and ordered evidence-backed results return; freshness: final attempt only.
    - Required authorized teardown (repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-demo down -v --remove-orphans` -> PASS evidence: exit `0` and only the named project is removed; freshness: final attempt only.
    - Required (repository root): `git diff --check -- docs/acceptance/local_release_checklist.md` -> PASS evidence: exit `0`; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_USER_ACTION` if credentials, browser observations, Docker/network, ports, or authorization are unavailable; `BLOCKED_PERMISSION` if exact named volume lifecycle cannot be verified; `BLOCKED_SCOPE_CONFLICT` on any product/config/test defect; `BLOCKED_SOURCE_CONFLICT` if the manual normalization observation cannot be resolved consistently with stored evidence.
  - Files: `docs/acceptance/local_release_checklist.md`

## Mandatory Batch05 - Final Current-Output Release Gate

### Goal

Re-run every final gate from current output, perform the final repository and
out-of-scope audit, and leave one complete dated checklist proving all Plan 7
completion conditions simultaneously.

### Dependencies

- Batch04 is fully A2-accepted; all prior repairs, documentation, and live
  evidence are in current repository state.

### Scope Boundary

This batch verifies and records only. It does not repair code/config/docs,
change accepted evidence, add future work, commit, or clean unrelated state. A
failure routes to a separately bounded owning repair and this task remains
unchecked until a fully fresh rerun.

### Tasks

- [x] (05A): Run the final complete release, repository, and scope audit
  - Task Type: docs-config
  - Artifact Root: `.agent/<plan-id>/<run-id>/`
  - Task Contract: `docs/tasks/task_7.md` > `## Mandatory Batch05 - Final Current-Output Release Gate` > `(05A)`
  - Source of Truth: `docs/plans/Plan_7.md` > `## 8. Implementation Steps`; `docs/plans/Plan_7.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_7.md` > `## 10. Final Handoff and Completion Contract`; `docs/plans/Master_plan.md` > `### 2.2 Explicitly out of scope`, `## 25. Implementation Phases` > `### Phase 6 — Polish and local release`, and `## 27. Definition of Done` through `## 29. Final Planning Decision`
  - Suggested Refs:
    - task-contract: repository `docs/tasks/task_7.md` > `(05A)` -> task authority
    - source-final-gate: repository `docs/plans/Plan_7.md` > `## 10. Final Handoff and Completion Contract` -> simultaneous completion requirements
    - validation-readme: repository `README.md` > verification commands -> final command authority
    - validation-checklist: repository `docs/acceptance/local_release_checklist.md` -> final evidence owner
  - Source Requirements:
    - Re-run all backend/frontend/E2E/provider/graph/Compose/repository checks
      after the final repair; stale output or skips cannot complete release.
    - Audit source, manifests, Compose, migrations, docs, and UI against every
      named exclusion while distinguishing clearly labeled future-work text
      from implemented/configured scope.
    - Confirm every checklist row has dated PASS evidence, every manual/live
      prerequisite remains satisfied, all real data/secrets stay outside Git,
      and every final handoff condition is simultaneously true.
  - Dependencies: (04A) and (04B) are A2-accepted and every earlier canonical task is checked.
  - User Action: Keep the confirmed ignored credentials, Docker, network/provider access, and free ports available for the final diagnostic/Compose rerun; rotate externally if a new credential incident is detected.
  - Runtime Policy:
    - check_after_seconds: 1200
    - timeout_seconds: 18000
    - quiet_until_due: true
    - max_repair_attempts: 0
  - Likely Files: `docs/acceptance/local_release_checklist.md`
  - Allowed Files: `docs/acceptance/local_release_checklist.md` final-rerun/scope/conclusion sections only; external named project `jobagent-plan7-final`; exclude every application/test/config/README/plan/task file and normal developer resource.
  - Agent Work:
    1. Verify all prior canonical markers/evidence and current HEAD/diff scope;
       refuse stale or mismatched evidence.
    2. Run the complete backend unit/integration/E2E/lint/type suite and complete
       frontend clean-install/lint/type/test/build suite from current output.
    3. Run the real provider diagnostic and a named three-service Compose
       config/startup/health/rebuild smoke, then teardown only that project.
    4. Re-run sanitized environment/tracked-data/history/repository checks and
       inspect dependencies, services, routes/tools/schemas/migrations/docs/UI
       for every Master/Plan 7 exclusion. Classify documentation-only future
       mentions separately from implementation.
    5. Review the manual JD artifact and every local-release row; any FAIL,
       BLOCKED, PENDING, skip, secret, real-data finding, false success, or
       unresolved ranking inconsistency fails the gate.
    6. Update only final checklist rows with dated fresh evidence. On any defect,
       return the exact blocker/owner without repair; the full task must rerun
       after an owner-scoped fix.
  - Output: One complete current-output release checklist and explicit final narrow-scope audit.
  - A1 Outcome: All Plan 7 automated, live, repository, documentation, and exclusion gates pass simultaneously from current output.
  - A2 Review Focus: Docs-config-rubric final-evidence accuracy; hard gates `HG-01` through `HG-09` cover fresh complete no-skip evidence, exact validated revision/diff, safe scope classification, all simultaneous handoff conditions, no duplicate/hardcoded bypass, and checklist-only edit.
  - A3 Batch Evidence: The sole final batch gate covering every requirement, validation, and final file/resource ownership row.
  - Acceptance:
    - Full backend, frontend, E2E, provider, graph, Compose, repository, and manual evidence is current and passing with no skip used as acceptance.
    - Every checklist status cell is dated PASS; no FAIL/BLOCKED/PENDING or unresolved observation remains.
    - Git contains only intended source/docs/synthetic fixtures and no secret, runtime state, real CV/JD, generated provider response, or CI workflow.
    - Exactly the narrow one-user/one-conversation/one-CV/one-Agent local product remains; all explicit exclusions are absent as implemented/configured scope.
    - Fresh clone plus one root `.env`, complete demo, rebuild/recovery, and honest limitations are all proven at the same revision.
  - Validation:
    - Required (repository root): `Set-Location backend; python -m ruff check .; if ($LASTEXITCODE -ne 0) { throw 'ruff failed' }; python -m mypy app; if ($LASTEXITCODE -ne 0) { throw 'mypy failed' }; python -m pytest tests/unit -q; if ($LASTEXITCODE -ne 0) { throw 'unit tests failed' }; python -m pytest tests/integration -q; if ($LASTEXITCODE -ne 0) { throw 'integration tests failed' }; python -m pytest tests/e2e/test_demo_flow.py -q; if ($LASTEXITCODE -ne 0) { throw 'E2E test failed' }` -> PASS evidence: every command exits `0` with no real provider call in tests; freshness: final attempt only.
    - Required (repository root): `Set-Location frontend; npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }; npm run lint; if ($LASTEXITCODE -ne 0) { throw 'frontend lint failed' }; npm run typecheck; if ($LASTEXITCODE -ne 0) { throw 'frontend typecheck failed' }; npm test -- --run; if ($LASTEXITCODE -ne 0) { throw 'frontend tests failed' }; npm run build; if ($LASTEXITCODE -ne 0) { throw 'frontend build failed' }` -> PASS evidence: every command exits `0` with no lockfile drift; freshness: final attempt only.
    - Required (repository root): `python infrastructure/scripts/diagnose_shopaikey.py; if ($LASTEXITCODE -ne 0) { throw 'provider diagnostic failed' }; python infrastructure/scripts/rebuild_neo4j.py --help; if ($LASTEXITCODE -ne 0) { throw 'host-wrapper help failed' }` -> PASS evidence: diagnostic ends `SHOPAIKEY_COMPATIBILITY=PASS`, wrapper help exits `0`, and output is sanitized; freshness: final attempt only.
    - Required fresh-project check (repository root): `$project = 'jobagent-plan7-final'; $containers = @(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.ID}}'); if ($LASTEXITCODE -ne 0) { throw 'Docker container query failed' }; $volumes = @(docker volume ls -q --filter "label=com.docker.compose.project=$project"); if ($LASTEXITCODE -ne 0) { throw 'Docker volume query failed' }; $networks = @(docker network ls -q --filter "label=com.docker.compose.project=$project"); if ($LASTEXITCODE -ne 0) { throw 'Docker network query failed' }; $existing = @($containers + $volumes + $networks | Where-Object { $_ }); if ($existing.Count -ne 0) { $existing; throw 'named final project is not fresh' }` -> PASS evidence: no container/volume/network with the named project label exists before startup; freshness: final attempt only.
    - Required (repository root): `$project = 'jobagent-plan7-final'; $expected = @('backend','frontend','neo4j'); $services = @(docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project config --services); if ($LASTEXITCODE -ne 0 -or (Compare-Object @($services | Sort-Object) @($expected | Sort-Object))) { throw 'final Compose service set failed' }; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project config --quiet; if ($LASTEXITCODE -ne 0) { throw 'final Compose config failed' }; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project up --build -d --wait --wait-timeout 180; if ($LASTEXITCODE -ne 0) { throw 'final Compose startup failed' }; $rows = @(docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project ps --format json | ConvertFrom-Json); if ($LASTEXITCODE -ne 0 -or $rows.Count -ne 3) { throw 'final Compose status failed' }; foreach ($name in $expected) { $row = @($rows | Where-Object Service -eq $name); if ($row.Count -ne 1 -or $row[0].State -ne 'running' -or $row[0].Health -ne 'healthy') { throw "final service not healthy: $name" } }; $health = Invoke-RestMethod http://127.0.0.1:8000/api/health; if ($health.overall -ne 'available') { throw 'final backend health unavailable' }; docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project exec -T backend python -m app.graph.rebuild; if ($LASTEXITCODE -ne 0) { throw 'final choice-C rebuild failed' }` -> PASS evidence: exact three-service set is running/healthy and choice-C seed-only or source-backed rebuild exits successfully without secret output; freshness: final attempt only.
    - Required authorized teardown (repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan7-final down -v --remove-orphans` -> PASS evidence: exit `0` and only named resources are removed; freshness: final attempt only.
    - Required (repository root): `git status --short; if ($LASTEXITCODE -ne 0) { throw 'git status failed' }; git diff --check; if ($LASTEXITCODE -ne 0) { throw 'whitespace errors' }; git ls-files; if ($LASTEXITCODE -ne 0) { throw 'tracked-file listing failed' }` plus the sanitized environment/history/data audit from (03A) -> PASS evidence: only intended changes and allowed synthetic fixtures are present, with no whitespace/secret/runtime-data finding; freshness: final attempt only.
    - Required (repository root): `$path = 'docs/acceptance/local_release_checklist.md'; $requiredSections = @('Automated Coverage','Static Safeguards','Fresh Clone','Failure and Recovery','Fresh Graph Rebuild','Manual Demo','Final Scope Audit','Final Rerun'); $text = Get-Content -Raw $path; foreach ($section in $requiredSections) { if ($text -notmatch [regex]::Escape("## $section")) { throw "missing release section: $section" } }; $rows = @(Get-Content $path | Where-Object { $_ -match '^\|' -and $_ -notmatch '^\|\s*Requirement\s*\|' -and $_ -notmatch '^\|[\s:|-]+\|$' }); if ($rows.Count -eq 0) { throw 'release checklist has no evidence rows' }; $bad = @($rows | Where-Object { $_ -notmatch '\|\s*PASS\s*\|' -or $_ -notmatch '\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*$' }); if ($bad) { $bad; throw 'release evidence row is not dated PASS' }` -> PASS evidence: all required sections exist and every nonempty evidence row is dated PASS; freshness: final attempt only.
    - Required manual scope check: inspect source/manifests/Compose/migrations/docs/UI for every exact exclusion listed in `docs/plans/Plan_7.md > ### 7.7 Final scope audit`, recording implemented/configured absence separately from labeled future-work mentions -> PASS evidence: complete dated exclusion matrix; freshness: final attempt only.
  - Blocked Condition: `BLOCKED_USER_ACTION` if final provider/Docker prerequisites are unavailable or a credential needs rotation; `BLOCKED_ENVIRONMENT` on any unavailable required tool/service; `BLOCKED_SCOPE_CONFLICT` on any failing command/product/config/doc defect; `BLOCKED_SOURCE_CONFLICT` on any unresolved prerequisite, false-success path, or ranking inconsistency.
  - Files: `docs/acceptance/local_release_checklist.md`
