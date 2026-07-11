# JobAgent Plan 1 Phase 0 Execution Tasks

## Purpose

Turn `docs/plans/Plan_1.md` into an executable, evidence-first Phase 0 workflow that removes ShopAIKey, Astryx, pypdf, and embedding uncertainty before product implementation begins. This task file produces compatibility evidence, locked decisions, and a safe three-folder scaffold only; it does not authorize production behavior.

## Project Context Notes

- README status: root `README.md` was read successfully during this rewrite; it currently contains only the `# JobAgent` title.
- Project purpose and current run/build/test commands remain undocumented in the root README.
- The current workspace contains the root README and planning/task documents but no documented runnable implementation baseline.
- Git metadata was usable during this rewrite, and no pre-existing working-tree changes were reported before editing this file.
- No README/source conflict was found because the README contains no task requirements; `docs/plans/Plan_1.md` and its controlling references in `docs/plans/Master_plan.md` remain authoritative.
- Source clarification: Plan 1 section 7.2 names ten Astryx components, while the controlling master-plan frontend matrix names six additional required components. Because Plan 1 explicitly says the master plan wins, Batch02 validates the union of both lists.
- Source clarification: Plan 1 allows an explicitly approved equivalent model ID, while the controlling master Phase 0 exit gate requires a successful `gpt-4o-mini` tool-call round trip. An equivalent model cannot pass this task until the affected master-plan adapter decision is explicitly revised.
- Source ambiguity: neither source defines the numeric PDF success threshold or initial embedding quality/latency baselines. The relevant tasks require those criteria to be agreed and recorded before results are evaluated.

## Authority and Scope

### Primary Source

- Primary implementation source: `docs/plans/Plan_1.md`.
- Controlling source on conflict, as declared by Plan 1: `docs/plans/Master_plan.md` sections 3, 5, 15, 16, 17, 19, and 22-25.
- Source precedence: current user instruction -> the explicitly referenced portions of `docs/plans/Master_plan.md` when a conflict exists, as required by Plan 1 -> `docs/plans/Plan_1.md` for all remaining Phase 0 detail -> current repository conventions that do not conflict with those documents.
- Root `README.md` is project context only and currently adds no task requirements.

### Source Section Index

- `docs/plans/Plan_1.md` > `## 1. Objective` -> evidence-only Phase 0 goal and prohibition on product behavior.
- `docs/plans/Plan_1.md` > `## 2. Source of Truth` -> controlling master-plan references and conflict rule.
- `docs/plans/Plan_1.md` > `## 3. Prerequisites from Prior Phases` -> local tools, API key, PDF fixtures, and labeled retrieval inputs.
- `docs/plans/Plan_1.md` > `## 4. Scope` -> mandatory scaffold and four compatibility gates.
- `docs/plans/Plan_1.md` > `## 5. Out of Scope` -> production, fallback, OCR, Qdrant, CI, and deployment exclusions.
- `docs/plans/Plan_1.md` > `## 6. Target Directory Structure` -> exact three working folders and Phase 0 paths.
- `docs/plans/Plan_1.md` > `### 7.1 ShopAIKey compatibility matrix` -> provider capabilities, evidence, schema fallback, and secret-safety rules.
- `docs/plans/Plan_1.md` > `### 7.2 Astryx component matrix` -> public import and composition evidence.
- `docs/plans/Plan_1.md` > `### 7.3 PDF benchmark record` -> per-fixture metrics and `NO_EXTRACTABLE_TEXT` behavior.
- `docs/plans/Plan_1.md` > `### 7.4 Embedding benchmark record` -> locked ShopAIKey adapter, response validation, quality metrics, and request-latency baseline.
- `docs/plans/Plan_1.md` > `### 7.5 Feasibility report decision block` -> required decision-table fields and all-pass exit rule.
- `docs/plans/Plan_1.md` > `## 8. Implementation Steps` -> required execution sequence and cleanup.
- `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan` -> minimum automated and local evidence.
- `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)` -> locked outputs and downstream blocking contract.
- `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack` -> approved stack and post-Phase-0 version pinning.
- `docs/plans/Master_plan.md` > `## 5. Repository Structure` -> exactly three top-level working folders, private-data location, and root files.
- `docs/plans/Master_plan.md` > `## 15. Frontend UX Plan` -> controlling Astryx UX boundary.
- `docs/plans/Master_plan.md` > `### 15.1 Layout` -> `AppShell` and `ChatLayout` requirements.
- `docs/plans/Master_plan.md` > `### 15.3 Chat components` -> complete Astryx component set and public-API-only rule.
- `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` -> provider adapter boundary.
- `docs/plans/Master_plan.md` > `### 16.1 Configuration` -> model, base URL, `ChatOpenAI`, and `bind_tools()` requirements.
- `docs/plans/Master_plan.md` > `### 16.2 Startup/diagnostic compatibility checks` -> six provider checks, schema fallback order, and model-switch prohibition.
- `docs/plans/Master_plan.md` > `## 17. Embedding and Retrieval` -> embedding/retrieval boundary.
- `docs/plans/Master_plan.md` > `### 17.1 Locked embedding contract` -> ShopAIKey model, dimensions, format, and no-substitution rule.
- `docs/plans/Master_plan.md` > `### 17.2 Provider compatibility gate` -> scalar/batch, ordering, dimension, quality, latency, and failure checks.
- `docs/plans/Master_plan.md` > `### 17.3 Text representations` -> candidate/job representations and no-prefix normalization policy.
- `docs/plans/Master_plan.md` > `## 19. Evaluation Plan` -> evaluation boundary.
- `docs/plans/Master_plan.md` > `### 19.1 Data policy` -> local-private data and aggregate-report policy.
- `docs/plans/Master_plan.md` > `### 19.2 Relevance labels` -> fixed seeded split and no test-set tuning.
- `docs/plans/Master_plan.md` > `## 22. Security and Privacy` -> security boundary.
- `docs/plans/Master_plan.md` > `### 22.2 Secrets` -> single-root secret ownership and no hardcoded/logged credentials.
- `docs/plans/Master_plan.md` > `### 22.4 Logging` -> allowed aggregate telemetry and prohibited content.
- `docs/plans/Master_plan.md` > `## 23. Environment Configuration` -> single root environment file and documented variable names.
- `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` -> local-only validation boundary.
- `docs/plans/Master_plan.md` > `### 24.2 Backend integration tests` -> fake-provider rule for normal automated tests.
- `docs/plans/Master_plan.md` > `### 24.5 Local verification commands` -> required single-purpose local command documentation.
- `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates` -> master exit gates and adapter-only revision rule.
- `docs/plans/Master_plan.md` > `### Phase 1 — Foundation, Docker, and source-of-truth data` -> downstream boundary that must remain blocked until Phase 0 passes.

### Approved Architecture and Constraints

- Keep exactly three product working folders: `frontend`, `backend`, and `infrastructure`; root documentation and configuration files are not a fourth working folder.
- Use React, TypeScript, Vite, and a pinned Astryx version for the frontend scaffold, without implementing product flows.
- Use Python, Pydantic v2, pypdf, an OpenAI-compatible embeddings client, and a temporary ShopAIKey diagnostic in the backend evaluation scaffold.
- Use ShopAIKey through the OpenAI-compatible contract with `gpt-4o-mini`; do not silently switch models or providers.
- Keep all configurable values in one root `.env`, document placeholders in `.env.example`, and keep real secrets and private CV/JD data untracked.
- Treat Phase 0 output as measured evidence and locked adapter decisions. Production FastAPI, LangGraph, persistence, graph, matching, and frontend product behavior remain out of scope.
- Block Plan 2 unless every required gate is `PASS`. A failed gate permits revision of only the affected adapter decision, not a broad fallback stack.

#### Repository and Implementation Constraints

- Stay inside Phase 0. Do not implement production endpoints, Agent runtime, database models, migrations, ingestion services, matching, OCR, Qdrant, CI, cloud deployment, or complete product UI flows.
- Search the repository before adding any helper, runner, schema, configuration entry, or script. Reuse or safely extend aligned logic instead of duplicating it.
- Keep modules focused on one responsibility and preferably below 300 lines. Split diagnostic, benchmark, schema, and reporting responsibilities when they would otherwise form a god file.
- Apply YAGNI: add only the minimum scaffold and diagnostic code required to prove a named gate.
- Prefer standard-library or already-pinned capabilities before adding dependencies. Remove temporary dependencies or scaffold artifacts not needed by a locked decision.
- If an intentional simplification has a meaningful ceiling, add a concise `ponytail:` comment naming the ceiling and the upgrade path; do not add routine explanatory comments.
- Fix shared causes rather than one call site. Before changing reused behavior, inspect all callers and preserve the gate contract for each caller.
- Separate user-owned inputs from agent work. Agents must not create API keys, real credentials, private CV/JD content, or labels that pretend to be user-provided evidence.
- Never print, log, report, commit, or expose API keys, Authorization headers, raw provider headers, raw CV/JD content, contact PII, or private evaluation records.
- Normal automated tests must use fakes or mocks and must not call the real ShopAIKey API. The explicitly authorized compatibility smoke test is the only live provider check.
- Use the fixed seeded validation inputs and pre-registered measurement protocol for the locked embedding model. Do not inspect held-out test results while setting thresholds.
- Record observed failures honestly. Never mark a gate `PASS`, infer a compatibility result, or claim a user action completed without evidence.
- If a gate fails, stop the Phase 1 handoff and revise only the affected adapter decision. Do not introduce an unapproved fallback provider, UI system, parser, embedding model, or deployment path.

#### Coding Requirements

- Write clean, idiomatic, readable code that follows the approved stack.
- Use descriptive names for modules, functions, variables, components, settings, and tests.
- Keep functions, components, and modules focused on one clear responsibility.
- Prefer simple, explicit control flow over clever abstractions.
- Use clear typing where the stack supports it.
- Avoid `any`, broad exception handling, hidden global state, and hardcoded configuration unless explicitly required by the source.
- Add comments only for non-obvious decisions or behavior.
- Keep frontend code free of backend-only secrets and backend-only configuration names.
- Do not add formatters, linters, frameworks, or architecture changes outside the source plan unless they already exist in the project or the user explicitly requests them.

#### Global Verification Requirements

- Root `README.md` has been created from the Phase 0 scaffold and describes only current evidence-backed state.
- Exactly three product working folders exist: `frontend`, `backend`, and `infrastructure`.
- No production endpoint, Agent runtime, database, migration, ingestion service, matching flow, OCR, Qdrant, CI, or cloud deployment was added.
- The root `.env` is user-owned and ignored; `.env.example` contains placeholders only; no nested frontend/backend `.env` exists.
- Secrets, Authorization headers, provider headers, raw CV/JD content, contact PII, raw sensitive tool arguments, and private fixtures are absent from tracked artifacts and logs.
- All mandatory batches are complete or correctly marked blocked with evidence and reason.
- Every task validation was run or marked blocked without an unsupported completion claim.
- Every detailed task ID has exactly one canonical checkbox, and its state reflects A2 acceptance or valid standalone completion.
- User actions are separated from agent work and no credentials, fixtures, labels, approvals, or threshold decisions were fabricated.
- Astryx is pinned exactly and every required UI need has a verified public import or documented public composition path.
- ShopAIKey model discovery, completion, function call, tool round trip, and one structured-schema mode pass; streaming behavior is known.
- Required ShopAIKey failures return non-zero and normal automated tests do not reach the real provider.
- PDF normal/layout measurements use the same frozen digital fixtures and the selected mode passes the pre-recorded threshold.
- The image-only fixture returns exactly `NO_EXTRACTABLE_TEXT` in both normal and layout modes with no OCR or alternate parser.
- ShopAIKey `text-embedding-3-small` uses the validation slice from the fixed seeded 60/20/20 split, exact `0`-`3` labels, registered quality/latency baselines, and fixed 1536-dimensional output.
- Scalar and batch requests preserve ordering, return finite floats, and use no E5 query/passage prefixes.
- Held-out results were not inspected for Phase 0 tuning or selection.
- Exact dependency/mode/version decisions and single-purpose commands are recorded for Plan 2.
- Temporary, duplicate, unused, raw, or out-of-scope artifacts and dependencies were removed.
- Git tracked/ignore proof is present when repository metadata is usable; otherwise Phase 0 remains blocked on that proof rather than claiming success.
- `backend/evaluation/reports/phase_0_feasibility.md` ends physically with the required decision table.
- Every required decision-table gate is `PASS` before Plan 2 is authorized.
- Implementation code is clean, idiomatic, focused, typed where appropriate, and easy to understand.

## Batch Map

| Batch | Outcome and exit evidence | Task IDs | Depends on |
|---|---|---|---|
| Batch01 - Safe Scaffold and Readiness Baseline | Safe Phase 0 scaffold and prerequisite inventory; exit evidence: Exact three-folder scaffold, root configuration boundary, ignored private inputs, and readiness record | (01A), (01B), (01C), (01D) | None |
| Batch02 - Astryx Compatibility Gate | Astryx compatibility locked; exit evidence: Pinned version plus public import/composition matrix for every required component | (02A), (02B), (02C) | Batch01 |
| Batch03 - ShopAIKey Compatibility Gate | ShopAIKey compatibility locked; exit evidence: Safe diagnostic evidence for all six provider capabilities | (03A), (03B), (03C), (03D), (03E), (03F) | Batch01 |
| Batch04 - pypdf Extraction Compatibility Gate | pypdf extraction behavior locked; exit evidence: Comparable normal/layout metrics and verified image-only classification | (04A), (04B), (04C), (04D) | Batch01 |
| Batch05 - ShopAIKey Embedding Compatibility Gate | Locked embedding adapter verified; exit evidence: API compatibility, fixed dimensions, seeded quality, and request latency | (05A), (05B), (05C), (05D) | Batch01, Batch03 |
| Batch06 - Evidence Consolidation and Phase 0 Exit Gate | Phase 0 decisions consolidated; exit evidence: Complete all-pass report, pinned decisions, clean scaffold, and Plan 2 handoff | (06A), (06B), (06C) | Batch02, Batch03, Batch04, Batch05 |

**Execution order and recovery**

- Mandatory Batch01 -> Mandatory Batch02
- Mandatory Batch01 -> Mandatory Batch03
- Mandatory Batch01 -> Mandatory Batch04
- Mandatory Batch01 -> Mandatory Batch05
- Mandatory Batch02 + Mandatory Batch03 + Mandatory Batch04 + Mandatory Batch05 -> Mandatory Batch06
- Batches 02-05 may execute independently after their Batch01 dependencies are satisfied; they are not artificially serialized.
- Mandatory Batch06 -> Plan 2 only when every required gate is `PASS`.
- Any failed gate -> affected adapter-only revision -> rerun that gate -> Mandatory Batch06 revalidation.

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated mode, and appends evidence to `docs/reports/report_1_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`, and appends evidence to `docs/review/review_1_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked; it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Safe Scaffold and Readiness Baseline

### Goal

Create only the minimum repository and evaluation structure needed to run Phase 0 gates, while proving that user-owned tools and private inputs are available or explicitly blocked.

### Dependencies

- No prior implementation batch.
- `docs/plans/Plan_1.md` and the referenced master-plan sections.
- User-owned local toolchain, ShopAIKey key, PDF fixtures, and labeled retrieval subset.

### Scope Boundary

**Why this batch exists**

Every compatibility gate depends on a common three-folder scaffold, one root configuration boundary, safe private-data handling, and honest readiness evidence.

**Files or modules likely created or updated**

- `frontend/package.json`
- `frontend/src/`
- `backend/app/`
- `backend/scripts/`
- `backend/evaluation/fixtures/`
- `backend/evaluation/labels/`
- `backend/evaluation/reports/phase_0_feasibility.md`
- `backend/pyproject.toml`
- `infrastructure/docker/`
- `infrastructure/neo4j/`
- `infrastructure/scripts/`
- `.env.example`
- `.gitignore`
- `README.md`

**Required outputs or artifacts**

- Exact three-folder product scaffold.
- Sanitized prerequisite inventory.
- Single-root configuration placeholder and ignore rules.
- Safe fixture/retrieval manifest templates.
- Pending Phase 0 feasibility-report skeleton.

**Batch acceptance**

- Scaffold and configuration boundaries match the sources without product implementation.
- Missing user-owned inputs are explicitly blocked rather than fabricated.
- Private data and secrets remain local, ignored, and absent from reports.

**Batch validation**

- Single-purpose local tool version checks.
- Filesystem comparison against the target structure.
- Environment/secret/private-data searches.
- Git ignore/tracked-file checks when Git metadata is usable; otherwise an explicit recorded limitation.

**Explicit non-goals**

- Production services, endpoints, databases, migrations, Agent logic, complete UI flows, Docker services, CI, or cloud deployment.
- Creation of real secrets, real CV/JD data, or synthetic labels presented as user evidence.

### Tasks

- [x] (01A): Verify local tools and user-owned gate inputs
  - Source of Truth: `docs/plans/Plan_1.md` > `## 3. Prerequisites from Prior Phases`; `docs/plans/Master_plan.md` > `## 22. Security and Privacy` > `### 22.2 Secrets`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy`
  - Source Requirements:
    - Python, Node.js/npm, and Docker with Compose must be available locally.
    - A local gitignored ShopAIKey key, five to ten representative digital PDF fixtures, one image-only fixture, and an initial labeled retrieval subset must be available before their dependent gates run.
    - Readiness evidence must not reveal secrets or private content.
  - Dependencies: None
  - User Action: Provide or confirm the local ShopAIKey key, redacted/private PDF fixtures, image-only fixture, and labeled retrieval subset; approve local use of those inputs without sharing their contents.
  - Agent Work: Establish a safe prerequisite inventory without fabricating provider access, private fixtures, or labels. Check tool versions and input presence, record only safe status metadata, and map missing inputs to the affected later tasks.
    1. Run single-purpose version checks for Python, Node.js, npm, and Docker Compose.
    2. Confirm required inputs exist in local, ignored locations without printing values or document content.
    3. Record ready, missing, or blocked status for each prerequisite in the temporary Batch01 execution/readiness report for later transfer by (01D).
    4. Stop each dependent live gate when its user-owned input is missing.
  - Output: Sanitized prerequisite/readiness result in the Batch01 execution report, ready for insertion into the feasibility report after (01D) creates it.
  - Acceptance:
    - Every prerequisite has evidence-backed ready, missing, or blocked status; no secret or private content appears in output.
  - Validation:
    - Required: Re-run the version and presence checks; inspect captured output for configured secret values, Authorization text, provider headers, filenames containing PII, and raw document content.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` for any live gate whose required key, fixture set, label set, or threshold approval is unavailable.
  - Files: No product file is required for this check; the future execution report records the sanitized result, while local root `.env` and private fixture paths remain read-only user-owned inputs.

- [x] (01B): Create the exact three-folder Phase 0 scaffold
  - Source of Truth: `docs/plans/Plan_1.md` > `## 4. Scope`; `docs/plans/Plan_1.md` > `## 6. Target Directory Structure`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 5. Repository Structure`
  - Source Requirements:
    - The product scaffold must contain exactly `frontend`, `backend`, and `infrastructure` as its three top-level working folders.
    - Root files hold shared configuration and documentation.
    - The scaffold must not implement production services or product flows.
  - Dependencies: (01A)
  - User Action: None
  - Agent Work: Establish the minimum directory and placeholder structure required by the compatibility work. Search current paths first, preserve aligned files, and add only missing Phase 0 directories and minimal placeholders.
    1. Inspect the repository for existing aligned scaffold files before creating anything.
    2. Create or preserve `frontend`, `backend`, and `infrastructure` as the only product working folders.
    3. Create the Phase 0 paths under `backend/app`, `backend/scripts`, `backend/evaluation`, `frontend/src`, and the declared infrastructure subfolders only as needed.
    4. Add minimal package/project placeholders without production routes, databases, Agent code, or UI flows.
    5. Create a root README placeholder that identifies Phase 0 status and does not claim unimplemented features.
  - Output: Minimal Plan 1 scaffold matching the approved directory boundary.
  - Acceptance:
    - All required Phase 0 paths exist; no fourth product working folder or production behavior was added.
  - Validation:
    - Required: Compare the filesystem against Plan 1 section 6 and master-plan section 5; enumerate non-hidden root directories and classify documentation/metadata directories separately from product working folders.
  - Blocked Condition: None
  - Files: `frontend/package.json`, `frontend/src/`, `backend/app/`, `backend/evaluation/`, `backend/scripts/`, `backend/pyproject.toml`, `infrastructure/docker/`, `infrastructure/neo4j/`, `infrastructure/scripts/`, `README.md`.

- [x] (01C): Establish single-root configuration and ignore boundaries
  - Source of Truth: `docs/plans/Plan_1.md` > `## 4. Scope`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 22. Security and Privacy` > `### 22.2 Secrets`; `docs/plans/Master_plan.md` > `## 23. Environment Configuration`
  - Source Requirements:
    - Use one root `.env`; do not create frontend or backend environment files.
    - `.env.example` documents placeholders only, including `SHOPAIKEY_BASE_URL=https://api.shopaikey.com/v1`, blank `SHOPAIKEY_API_KEY`, and `LLM_MODEL=gpt-4o-mini`, with ShopAIKey and Neo4j secrets remaining backend-only.
    - Ignore the real root `.env`, runtime files, real CV/JD data, and private evaluation data.
  - Dependencies: (01B)
  - User Action: Populate the local ignored root `.env` with real values when needed; never provide those values in a report or commit.
  - Agent Work: Create the safe configuration contract required by diagnostics without writing real values. Add placeholder variable names, enforce ignore rules, and reject separate environment-file drift.
    1. Add the master-plan variable names to root `.env.example`, preserving the exact ShopAIKey base URL and model defaults while leaving secret placeholders empty.
    2. Add `.gitignore` rules for root `.env`, runtime outputs, uploaded documents, `backend/evaluation/private/`, and other local-private fixture locations.
    3. Verify frontend placeholders expose only explicitly public `VITE_` values.
    4. Search for hardcoded keys, Authorization headers, real credential values, and nested `.env` files.
  - Output: Root `.env.example` and `.gitignore` that enforce the single-root configuration and private-data boundary.
  - Acceptance:
    - Required variable names are documented once; real secrets/private data are ignored; no backend secret is exposed to frontend configuration.
  - Validation:
    - Required: Run ignore checks when Git metadata is usable, plus direct filesystem and secret-pattern searches; record the Git-metadata limitation when tracked-file proof is unavailable.
  - Blocked Condition: None for placeholder creation; `BLOCKED_BY_USER_ACTION` only for later live validation when the user has not populated the ignored root `.env`.
  - Files: `.env.example`, `.gitignore`, local `.env` excluded from agent writes.

- [x] (01D): Create evaluation manifests and an evidence-first report skeleton
  - Source of Truth: `docs/plans/Plan_1.md` > `## 6. Target Directory Structure`; `docs/plans/Plan_1.md` > `### 7.5 Feasibility report decision block`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 19. Evaluation Plan` > `### 19.1 Data policy`
  - Source Requirements:
    - Keep real CV/JD and private evaluation data local and ignored; commit only synthetic fixtures, templates, manifests without sensitive content, and aggregate reports.
    - The Phase 0 report must collect readiness, per-gate evidence, locked decisions, and a final decision table.
    - Results must remain unset until measured.
  - Dependencies: (01C)
  - User Action: Review fixture identifiers and confirm that committed metadata cannot identify a real person or expose private content.
  - Agent Work: Provide a single evidence destination and safe metadata contracts for later benchmark tasks. Create focused manifest templates and report headings without inserting fabricated results.
    1. Define synthetic and local-private PDF manifest fields using non-identifying fixture IDs and local paths that are not committed.
    2. Define a labeled retrieval-subset manifest with seed, split name, record count, and label provenance but no private text.
    3. Create report sections for prerequisites, Astryx, ShopAIKey, PDF, embeddings, locked versions, cleanup, final decisions, and handoff.
    4. Transfer the sanitized readiness statuses from (01A) into the prerequisites section without private values or content.
    5. Add the final decision-table columns `Gate`, `Result`, `Evidence`, `Selected mode/version`, and `Phase impact` with results initially pending.
  - Output: Safe Phase 0 manifest templates and `backend/evaluation/reports/phase_0_feasibility.md` skeleton.
  - Acceptance:
    - Every later gate has a structured evidence location; no pending gate is pre-marked `PASS`; committed metadata contains no private content.
  - Validation:
    - Required: Inspect manifests and report for required fields, safe paths, pending results, and absence of real document text or PII.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` if the user cannot confirm that any proposed committed fixture metadata is safely de-identified.
  - Files: `backend/evaluation/fixtures/`, `backend/evaluation/labels/` or an equivalent existing evaluation metadata path, `backend/evaluation/private/` ignored, `backend/evaluation/reports/phase_0_feasibility.md`.

## Mandatory Batch02 - Astryx Compatibility Gate

### Goal

Pin one demonstrably stable Astryx version and prove a supported public import or documented public composition path for every component required by the controlling frontend plan.

### Dependencies

- Mandatory Batch01 complete through (01B) and (01D).
- Working Node.js/npm toolchain.
- Network/package-registry access needed for the pinned package and its CLI documentation.

### Scope Boundary

**Why this batch exists**

The product UI cannot safely begin until the design-system version and component contracts are known. This gate prevents invented props, undocumented internals, and a late UI-library replacement.

**Files or modules likely created or updated**

- `frontend/package.json`
- Frontend package lock
- Astryx initialization outputs required by the pinned release
- Focused public-export compatibility check under `frontend/`
- `backend/evaluation/reports/phase_0_feasibility.md`

**Required outputs or artifacts**

- Exact stable Astryx version and initialization evidence.
- Complete sixteen-need public component/import/composition matrix.
- Reproducible resolution check and `PASS` or `FAIL` decision.

**Batch acceptance**

- Required UI needs resolve through supported public APIs for the exact pin.
- No product screen, undocumented internal, invented prop, or fallback UI stack is introduced.
- Plan 2 receives one locked Astryx version and component contract.

**Batch validation**

- Exact package-resolution check.
- One CLI documentation command per required component.
- Focused public-export resolution/type check.
- Search for undocumented internal import paths.

**Explicit non-goals**

- App shell implementation, chat UI, sidebar behavior, match cards, responsive product flows, or production frontend tests.
- Replacing Astryx or adding another UI library without an approved failed-gate revision.

### Tasks

- [ ] (02A): Select, pin, and initialize a stable Astryx release
  - Source of Truth: `docs/plans/Plan_1.md` > `## 4. Scope`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - Pin one stable Astryx version rather than a floating range.
    - Run `npx astryx init --features agents --agent codex`.
    - Capture the resolved package and CLI version without implementing product UI flows.
  - Dependencies: (01A), (01B), (01D)
  - User Action: Provide network/package-registry access if the package cannot be resolved locally; approve a non-default release only when official stable metadata is ambiguous.
  - Agent Work: Establish a reproducible design-system baseline and preserve only initialization artifacts required by the gate. Inspect existing frontend package state, select a non-prerelease release using package evidence, pin it exactly, run the required initializer, and record the result.
    1. Search `frontend/package.json` and lockfiles for an existing Astryx pin before adding or changing one.
    2. Verify that the selected release is published as stable and record the evidence source/date in the report.
    3. Pin the exact version and update the package lock using the repository package manager.
    4. Run `npx astryx init --features agents --agent codex` from the documented frontend context.
    5. Inventory generated files and remove unrelated demo or product artifacts that are not needed for compatibility inspection.
  - Output: Exact Astryx dependency pin, reproducible package lock, sanitized initialization record, and generated compatibility scaffold only.
  - Acceptance:
    - npm resolves the exact pin, the required initializer completes, the report records the package/CLI version, and no product flow or floating version was added.
  - Validation:
    - Required: Run the package-manager resolution command, inspect the lockfile for a single exact Astryx version, and compare generated paths against the Phase 0 scope.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when required registry/network access or an explicit release choice cannot be obtained.
  - Files: `frontend/package.json`, frontend package lock, Astryx initializer outputs required for documentation inspection, `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (02B): Build the complete Astryx public component matrix
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.2 Astryx component matrix`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 15. Frontend UX Plan` > `### 15.1 Layout`; `docs/plans/Master_plan.md` > `## 15. Frontend UX Plan` > `### 15.3 Chat components`
  - Source Requirements:
    - Use the pinned CLI documentation command before implementing any component.
    - Record public imports and documented composition paths; undocumented internals are prohibited.
    - Cover `AppShell`, `ChatLayout`, `ChatComposer`, `ChatToolCalls`, `ChatMessage`, `ButtonGroup`, `Button`, `Card`, `Collapsible`, `ProgressBar`, `ChatMessageList`, `ChatSystemMessage`, `MetadataList`, `Badge`, `Banner`, and `Toast`.
  - Dependencies: (02A)
  - User Action: None
  - Agent Work: Resolve the narrower Plan 1 list against the controlling master-plan UI matrix by validating the complete union of sixteen required components. Run the pinned CLI documentation command for each component and capture only public, version-specific evidence.
    1. Determine the exact CLI documentation command supported by the pinned release from its public help or official package documentation.
    2. Run the command separately for every required component.
    3. Record package export, public import path, documented role, and required composition dependencies for each component.
    4. When a named component is absent, document the supported composition using only public exports and cite the CLI evidence.
    5. Mark unresolved components as failed rather than inferring APIs or copying undocumented examples.
  - Output: Version-specific Astryx component/import/composition matrix in the Phase 0 report.
  - Acceptance:
    - All sixteen required component needs have either a verified public import or a documented public composition path; no undocumented internal is referenced.
  - Validation:
    - Required: Re-run each single-component documentation command and cross-check every matrix row against its captured output.
  - Blocked Condition: None for documentation capture; the gate remains failed if a required public import/composition path cannot be proven.
  - Files: `backend/evaluation/reports/phase_0_feasibility.md`; optional sanitized CLI evidence files under `backend/evaluation/reports/` when the report links them.

- [ ] (02C): Validate and lock the Astryx compatibility decision
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.2 Astryx component matrix`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - npm must resolve the pinned package and required public APIs.
    - The selected version and composition decisions must be locked for Plan 2.
    - Missing compatibility may revise only the Astryx adapter/UI-system decision; it must not trigger unrelated fallback stacks.
  - Dependencies: (02B)
  - User Action: Approve a master-plan adapter revision only if the required public component coverage cannot be achieved; do not approve silent substitution.
  - Agent Work: Turn the documentation matrix into an evidence-backed `PASS` or `FAIL` gate without building product screens. Add the smallest import/composition resolution check, execute it against the exact pin, record the decision, and remove unnecessary initializer artifacts.
    1. Add or reuse a focused frontend compatibility check that imports only the public exports identified in the matrix.
    2. Resolve/type-check or otherwise validate those imports using the pinned package without constructing full product flows.
    3. Confirm every composition path uses documented public APIs only.
    4. Record `PASS` only when all required needs resolve; otherwise record the exact missing need and Phase impact.
    5. Lock the package version and matrix for Plan 2 and clean unrelated temporary output.
  - Output: Astryx gate result with pinned version, public component matrix, validation command, and Plan 2 impact.
  - Acceptance:
    - Gate is `PASS` with complete evidence, or honestly `FAIL` with Plan 2 blocked and no undocumented workaround.
  - Validation:
    - Required: Run the focused public-export resolution check and package-manager resolution command; search for internal package paths or invented component APIs.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` only when a failed gate requires approval to revise the Astryx adapter decision in the master plan.
  - Files: `frontend/package.json`, frontend package lock, focused compatibility-check file under `frontend/`, `backend/evaluation/reports/phase_0_feasibility.md`.

## Mandatory Batch03 - ShopAIKey Compatibility Gate

### Goal

Implement and run one isolated, secret-safe diagnostic that characterizes all six required ShopAIKey capabilities and locks the model, tool-call, structured-output, and streaming decisions for Plan 2.

### Dependencies

- Mandatory Batch01 complete through (01D).
- User-populated, ignored root `.env` containing `SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`, and `LLM_MODEL`.
- Pydantic v2, `langchain-openai` `ChatOpenAI`, and focused HTTP support available through the minimal backend project.

### Scope Boundary

**Why this batch exists**

The later Agent and extraction phases depend on provider behavior that cannot be assumed from an OpenAI-compatible label. This gate isolates provider uncertainty before production code exists.

**Files or modules likely created or updated**

- `backend/scripts/check_shopaikey_compatibility.py`
- Focused ShopAIKey diagnostic tests under `backend/tests/` or the established backend test path
- Focused Pydantic v2 diagnostic schema/helper only when no equivalent exists
- `backend/pyproject.toml`
- `backend/evaluation/reports/phase_0_feasibility.md`

**Required outputs or artifacts**

- Fake-testable, secret-safe live diagnostic.
- Sanitized evidence for model discovery, completion, function call, tool round trip, structured schema, and streaming.
- Locked model ID, tool-call mode, schema mode, repair rule, and streaming classification.

**Batch acceptance**

- Every required-pass capability succeeds and streaming behavior is known.
- Diagnostic failure semantics are unambiguous and secret scans are clean.
- Live access remains isolated from normal automated tests.

**Batch validation**

- Focused fake-provider test suite covering success and failure branches.
- Sentinel-secret and prohibited-output scans.
- Explicitly authorized live compatibility command.
- Non-zero exit verification for tool-call and schema failures.

**Explicit non-goals**

- Production Agent integration, production prompt design, CV/JD extraction, provider failover, silent model substitution, or multiple repair loops.
- Real provider calls from the normal automated test suite.

### Tasks

- [ ] (03A): Build the secure isolated diagnostic foundation
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.1 ShopAIKey compatibility matrix`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` > `### 16.1 Configuration`; `docs/plans/Master_plan.md` > `## 22. Security and Privacy` > `### 22.2 Secrets`; `docs/plans/Master_plan.md` > `## 22. Security and Privacy` > `### 22.4 Logging`
  - Source Requirements:
    - Read `SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`, and `LLM_MODEL` from the single root environment.
    - Use `ChatOpenAI` with the custom base URL and `bind_tools()` for provider compatibility behavior.
    - Never print the API key, Authorization header, raw provider headers, raw CV/JD content, or sensitive tool arguments.
  - Dependencies: (01C), (01D)
  - User Action: Approve and record a repeat count and pass criterion for the source term "reliably" before live structured-schema results are used to mark that gate `PASS`.
  - Agent Work: Establish a typed, deterministic diagnostic harness whose results can be reported safely and whose provider calls can be faked in normal tests. Search for existing configuration/redaction/result-schema logic, reuse it where aligned, and implement only the missing diagnostic shell.
    1. Define typed result records for capability, status, sanitized evidence, selected mode, and failure code.
    2. Load required values from the root environment without echoing them or adding fallback secrets.
    3. Centralize safe output/redaction so every capability uses the same boundary.
    4. Support dependency injection or an equivalent small seam so normal tests use a fake provider.
    5. Define required-pass capabilities separately from the streaming knowledge-only outcome.
  - Output: Secure diagnostic foundation at `backend/scripts/check_shopaikey_compatibility.py` plus focused typed schemas/helpers only when no equivalent exists.
  - Acceptance:
    - The diagnostic starts only with valid required configuration, produces deterministic sanitized result records, and can be tested without a real provider call.
  - Validation:
    - Required: Run configuration and redaction tests with sentinel secrets; confirm sentinel values and sensitive header names never appear in stdout, stderr, logs, exceptions, or report output.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` for a live reliability claim until the repeat/pass criterion is approved; fake-tested implementation may continue.
  - Files: `backend/scripts/check_shopaikey_compatibility.py`, focused backend tests, `backend/pyproject.toml`, `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (03B): Add model-discovery and basic-completion checks
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.1 ShopAIKey compatibility matrix`; `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` > `### 16.1 Configuration`; `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` > `### 16.2 Startup/diagnostic compatibility checks`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - The current master Phase 0 gate requires `gpt-4o-mini`; an equivalent may be characterized but cannot pass until the affected master-plan adapter decision is revised.
    - Basic completion must return a non-empty assistant response.
    - The diagnostic must not silently switch models.
  - Dependencies: (03A)
  - User Action: Approve and record an adapter-only master-plan revision if only an equivalent model is available; approval without source revision does not pass the gate.
  - Agent Work: Implement the checks that (03F) will use to prove that the configured endpoint exposes the master-locked model and accepts a minimal completion request. Add focused model-listing and minimal completion capability functions with safe, bounded evidence.
    1. Query model discovery using the configured base URL without logging request headers.
    2. Compare returned IDs with the configured `LLM_MODEL` and reject silent substitution.
    3. Send a content-neutral minimal chat prompt that contains no CV/JD data.
    4. Record model match status and whether a non-empty assistant response was observed, without copying unnecessary provider payloads.
  - Output: Fake-tested model-discovery and basic-completion check implementations; live results remain pending until (03F).
  - Acceptance:
    - Fake-provider tests prove correct classification of `gpt-4o-mini`, equivalent-only, missing-model, non-empty-response, and empty-response cases without claiming live compatibility.
  - Validation:
    - Required: Fake-provider tests cover `gpt-4o-mini` present, model absent, equivalent requiring source revision, empty response, and safe error output.
  - Blocked Condition: None for implementation; (03F) is `BLOCKED_BY_USER_ACTION` when only an equivalent exists and the master-plan adapter decision has not been revised.
  - Files: `backend/scripts/check_shopaikey_compatibility.py`, focused backend tests, `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (03C): Add function-call and tool-result round-trip checks
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.1 ShopAIKey compatibility matrix`; `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` > `### 16.2 Startup/diagnostic compatibility checks`; `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack`
  - Source Requirements:
    - Function calling must return the expected tool name and valid JSON arguments.
    - Supplying a tool result must produce a final assistant response.
    - Tool binding uses `ChatOpenAI.bind_tools()` through the configured ShopAIKey endpoint.
  - Dependencies: (03A)
  - User Action: None
  - Agent Work: Implement the complete tool-call-loop check that (03F) will execute against the live provider. Add one harmless synthetic tool contract and validate both the initial call and the follow-up response.
    1. Define one minimal typed synthetic tool whose input cannot contain private document data.
    2. Bind the tool and send a deterministic prompt that should select it.
    3. Validate the returned tool name and parse arguments as JSON against the local schema.
    4. Supply a synthetic tool result using the provider-compatible message contract.
    5. Validate that the provider returns a non-empty final assistant response after the tool result.
  - Output: Fake-tested function-call and tool-result round-trip check implementation; live capability evidence remains pending until (03F).
  - Acceptance:
    - Fake-provider tests prove that the check accepts the expected tool name, valid typed arguments, and final response, and rejects every named failure branch without claiming a live result.
  - Validation:
    - Required: Fake-provider tests cover malformed JSON, wrong tool, missing tool call, multiple unexpected calls, missing final response, and safe failures.
  - Blocked Condition: None beyond missing live provider access already captured by (01A).
  - Files: `backend/scripts/check_shopaikey_compatibility.py`, focused backend tests, `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (03D): Determine one reliable structured-schema mode
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.1 ShopAIKey compatibility matrix`; `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` > `### 16.2 Startup/diagnostic compatibility checks`; `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack`
  - Source Requirements:
    - Structured output must validate against a local Pydantic v2 model.
    - `strict=True` remains disabled until verified.
    - If strict schemas are incompatible, test ordinary function schemas or JSON mode and allow at most one schema-repair request.
  - Dependencies: (03A)
  - User Action: Confirm the pre-recorded reliability criterion from (03A); approve a master-plan revision only if no permitted mode satisfies it.
  - Agent Work: Implement bounded structured-output strategies and validation so (03F) can characterize live behavior and lock one reproducible mode without adding a fallback provider. Exercise permitted schema strategies in a bounded order, validate with Pydantic v2, and count repair requests explicitly.
    1. Define a small local Pydantic v2 response model with fields that test types and required values without private content.
    2. Test `strict=True` only as an observed compatibility mode and do not enable it by default before it passes.
    3. When needed, test ordinary function schema or JSON mode without changing provider/model.
    4. Permit at most one repair request for an invalid schema response and record whether it was used.
    5. Return typed per-attempt results that (03F) can evaluate against the approved reliability criterion and use to select exactly one live mode.
  - Output: Fake-tested structured-output strategy, Pydantic validation, reliability-evaluation, and repair-count implementation; live mode selection remains pending until (03F).
  - Acceptance:
    - Fake-provider tests prove that permitted modes, Pydantic validation, the approved reliability rule, and the one-repair limit are enforced without claiming a live selected mode.
  - Validation:
    - Required: Fake-provider tests cover valid output, first-response repair success, second failure, strict incompatibility, invalid types, and repair-limit enforcement.
  - Blocked Condition: None for implementation; (03F) is `BLOCKED_BY_USER_ACTION` when the reliability criterion is unapproved or every live permitted mode fails and an adapter revision is required.
  - Files: `backend/scripts/check_shopaikey_compatibility.py`, focused Pydantic schema/test files, `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (03E): Characterize streaming and enforce diagnostic exit behavior
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.1 ShopAIKey compatibility matrix`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` > `### 16.2 Startup/diagnostic compatibility checks`
  - Source Requirements:
    - Streaming must produce ordered text chunks or a documented unsupported result before Plan 2.
    - A required tool-call or structured-schema failure must make the diagnostic exit non-zero.
    - Unsupported streaming is a known capability outcome, not an invented success.
  - Dependencies: (03A), (03C), (03D)
  - User Action: None
  - Agent Work: Implement streaming classification and exit aggregation so (03F) can complete the live compatibility matrix unambiguously. Add bounded streaming observation, classify its outcome, and centralize process exit semantics.
    1. Send a content-neutral streaming request and capture only ordered text-chunk metadata needed as evidence.
    2. Classify streaming as supported with ordered chunks, unsupported with provider evidence, or failed/unknown.
    3. Return non-zero when any required-pass capability fails or remains unknown.
    4. Do not fail the overall required gate solely because streaming is explicitly and reliably documented as unsupported.
    5. Print one sanitized summary suitable for a single-purpose local command.
  - Output: Fake-tested streaming classifier and deterministic diagnostic exit-code contract; live streaming status remains pending until (03F).
  - Acceptance:
    - Fake-provider tests prove correct supported/unsupported/unknown classification, non-zero required-failure exits, and sanitized output without claiming live streaming behavior.
  - Validation:
    - Required: Fake-provider tests cover ordered chunks, out-of-order/empty chunks, explicit unsupported response, unknown failure, and exit-code aggregation.
  - Blocked Condition: None for implementation; an unknown live streaming result in (03F) keeps the gate incomplete until characterized.
  - Files: `backend/scripts/check_shopaikey_compatibility.py`, focused backend tests, `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (03F): Execute the live provider smoke test and lock ShopAIKey decisions
  - Source of Truth: `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.2 Backend integration tests`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - Normal automated tests do not call the real API; the isolated compatibility smoke test may use the local user-owned key.
    - Provider evidence must cover all six capabilities and contain no configured secret value.
    - The live tool-call round trip must use `gpt-4o-mini` under the current master plan; an equivalent remains blocked until an adapter-only source revision is approved and recorded.
    - The tool-call round trip and one reliable schema mode must pass before Plan 2.
  - Dependencies: (03B), (03C), (03D), (03E)
  - User Action: Populate the ignored root `.env`, authorize the live smoke test, and approve/record an adapter-only master-plan revision when `gpt-4o-mini` is unavailable; equivalent-model approval alone is insufficient.
  - Agent Work: Run the tested diagnostic once as the authorized live compatibility operation and preserve only sanitized aggregate evidence. Run fake-based tests first, execute the live diagnostic, scan all output for leakage, and write the locked provider decisions to the report.
    1. Run the focused fake-provider test suite and confirm no test reaches the network.
    2. Run `python backend/scripts/check_shopaikey_compatibility.py` using the local root environment.
    3. Capture exit code and sanitized capability summaries without persisting raw provider payloads or headers.
    4. Search stdout, stderr, logs, and report changes for the configured secret sentinel/value and prohibited data classes.
    5. Record model ID, tool-call mode, structured-output mode, repair policy, streaming classification, and `PASS` or `FAIL` impact.
  - Output: Complete sanitized ShopAIKey compatibility matrix and locked provider decision block.
  - Acceptance:
    - `gpt-4o-mini` completes the required completion, function-call, tool-result, and structured-schema checks under the current source; streaming is known; diagnostic exits zero; leakage scan passes. An equivalent can pass only after the controlling adapter decision is revised.
  - Validation:
    - Required: Focused fake-provider tests, live single-purpose diagnostic, exit-code check, and exact secret/prohibited-output scan.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when the key, live-test authorization, required adapter-source revision for an equivalent model, or schema reliability criterion is missing.
  - Files: `backend/scripts/check_shopaikey_compatibility.py`, focused backend tests, `backend/pyproject.toml`, `backend/evaluation/reports/phase_0_feasibility.md`; root `.env` remains user-owned and ignored.

## Mandatory Batch04 - pypdf Extraction Compatibility Gate

### Goal

Benchmark pypdf normal and layout extraction on the same representative digital CV fixtures, verify exact image-only failure behavior, and lock one parser mode without introducing OCR.

### Dependencies

- Mandatory Batch01 complete through (01D).
- Five to ten user-provided representative, digitally born PDF CV fixtures.
- One image-only PDF fixture.
- A user-approved numeric interpretation of the required digital-fixture success threshold.

### Scope Boundary

**Why this batch exists**

Later CV ingestion depends on predictable digital-PDF extraction and a clear non-text failure contract. This gate measures the baseline before production ingestion is built.

**Files or modules likely created or updated**

- PDF fixture manifest under `backend/evaluation/fixtures/`
- Ignored local PDF corpus under `backend/evaluation/private/` or another documented ignored location
- Focused pypdf benchmark runner under `backend/evaluation/`
- Focused pypdf benchmark tests
- Aggregate PDF result artifact under `backend/evaluation/reports/`
- `backend/evaluation/reports/phase_0_feasibility.md`
- `backend/pyproject.toml`

**Required outputs or artifacts**

- Frozen, privacy-safe fixture manifest and pre-recorded pass criterion.
- Normal/layout benchmark rows for every digital fixture.
- Selected parser mode plus normal/layout image-only evidence for the exact `NO_EXTRACTABLE_TEXT` rule.

**Batch acceptance**

- One pypdf mode meets the agreed digital-fixture threshold.
- The image-only fixture reproducibly yields `NO_EXTRACTABLE_TEXT` in both normal and layout modes.
- No OCR, alternate parser, raw text, or private fixture is added to the repository.

**Batch validation**

- Synthetic benchmark-runner tests.
- Same-fixture/same-order comparison check.
- Required metric and threshold calculations.
- Exact image-only outcome assertion.
- OCR/fallback dependency and raw-text leakage searches.

**Explicit non-goals**

- Production CV ingestion, OCR, alternate PDF parsers, document storage, structured CV extraction, or real-data commits.
- Changing thresholds after benchmark outcomes are known.

### Tasks

- [ ] (04A): Freeze the PDF fixture manifest and pass criterion
  - Source of Truth: `docs/plans/Plan_1.md` > `## 3. Prerequisites from Prior Phases`; `docs/plans/Plan_1.md` > `### 7.3 PDF benchmark record`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 19. Evaluation Plan` > `### 19.1 Data policy`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - Use five to ten representative digital CV PDFs plus an image-only fixture.
    - Include at least one real CV that the user redacts before evaluation; all real documents stay local and ignored.
    - Real documents remain redacted, local, and ignored; the repository keeps only safe synthetic fixtures/manifests and aggregate evidence.
    - pypdf must succeed on an "agreed majority," but the sources do not define the numeric threshold.
  - Dependencies: (01C), (01D)
  - User Action: Supply/confirm the redacted local fixture corpus, including at least one user-redacted real CV and the image-only fixture, and approve the exact digital-fixture success threshold used to interpret "agreed majority."
  - Agent Work: Establish immutable fixture IDs, privacy classification, and the pass rule before observing benchmark results. Validate fixture count/types and record safe metadata without opening private content for reporting or changing the corpus after results are known.
    1. Assign non-identifying IDs to five to ten digital fixtures, including at least one user-redacted real CV, and one image-only fixture.
    2. Record local-private versus safe-synthetic classification and confirm ignore coverage.
    3. Record the numeric success threshold and what counts as successful extraction before running the benchmark.
    4. Hash or otherwise freeze the local input set using non-reversible aggregate identifiers when safe, without committing source files.
  - Output: Frozen PDF fixture manifest and pre-recorded digital-fixture pass criterion.
  - Acceptance:
    - Corpus size/type requirements and the one-redacted-real-CV requirement are met, private paths are ignored, and the pass rule predates benchmark results.
  - Validation:
    - Required: Manifest schema/count check, file-type/page-read smoke check, ignore-state check, and timestamp/order review for the pre-recorded criterion.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when fixtures or the numeric pass criterion are missing.
  - Files: PDF manifest under `backend/evaluation/fixtures/`; private files under ignored `backend/evaluation/private/` or another documented ignored local path; `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (04B): Implement the focused pypdf benchmark recorder
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.3 PDF benchmark record`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack`
  - Source Requirements:
    - Compare pypdf normal and layout extraction only.
    - Record fixture ID, page count, parser mode, extracted character count, elapsed milliseconds, and outcome for every run.
    - Do not add OCR or a fallback parser.
  - Dependencies: (04A)
  - User Action: None
  - Agent Work: Create one focused, repeatable local benchmark path with structured aggregate output. Search for an existing evaluation runner, reuse its safe patterns, and add only the pypdf modes and metrics that are missing.
    1. Define a typed benchmark-result schema containing every required record field.
    2. Load fixtures from the frozen manifest rather than hardcoded private paths.
    3. Run normal and layout extraction with equivalent timing boundaries and deterministic ordering.
    4. Map zero usable text to the explicit outcome contract without attempting OCR.
    5. Emit aggregate machine-readable results and a concise report-ready summary without raw document text.
  - Output: Focused pypdf benchmark runner and typed aggregate result artifact.
  - Acceptance:
    - Both modes run through one consistent path, every record has all required fields, and no raw text or OCR path is emitted.
  - Validation:
    - Required: Tests with safe synthetic text PDFs, malformed inputs, and an image-only fixture; schema validation for required metrics; search for OCR/fallback dependencies.
  - Blocked Condition: None after (04A) is complete.
  - Files: Focused runner such as `backend/evaluation/benchmark_pdf_extraction.py`, focused backend tests, aggregate result output under `backend/evaluation/reports/`, `backend/pyproject.toml` if pypdf is not yet pinned.

- [ ] (04C): Run the digital-PDF comparison and select a parser mode
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.3 PDF benchmark record`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - Run normal and layout extraction across the same agreed digital fixtures.
    - Lock the selected extraction mode before Plan 2.
    - The selected mode must meet the pre-recorded success criterion on the agreed majority.
  - Dependencies: (04B)
  - User Action: Review aggregate outcomes when fixture quality or success classification is disputed; do not provide private content in the report.
  - Agent Work: Produce comparable measurements and choose one evidence-backed digital-PDF extraction mode. Execute both modes, validate result completeness, compare outcomes, and record a single selected mode or an honest failure.
    1. Run the benchmark against the frozen digital subset with normal extraction.
    2. Run it against the identical ordered subset with layout extraction.
    3. Confirm fixture IDs, page counts, and measurement coverage match across modes.
    4. Evaluate each mode against the pre-recorded success criterion and compare extraction yield/timing without post-hoc threshold changes.
    5. Select one mode and record evidence, or mark the adapter gate failed.
  - Output: Complete digital-PDF benchmark table and locked normal/layout parser decision.
  - Acceptance:
    - Comparable results exist for every digital fixture in both modes and one mode meets the approved pass criterion.
  - Validation:
    - Required: Result-set equality check, required-field/schema check, threshold calculation, repeated spot run for deterministic classification, and raw-text leakage scan.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when the pre-recorded threshold is unavailable or a disputed fixture classification requires user resolution.
  - Files: Aggregate PDF benchmark results, `backend/evaluation/reports/phase_0_feasibility.md`, benchmark runner/tests only when corrections are required.

- [ ] (04D): Verify exact image-only failure behavior and close the PDF gate
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.3 PDF benchmark record`; `docs/plans/Plan_1.md` > `## 5. Out of Scope`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - The image-only fixture must produce the exact outcome `NO_EXTRACTABLE_TEXT`.
    - OCR is prohibited in this phase.
    - A failed parser gate permits revision of only the parser adapter decision.
  - Dependencies: (04B), (04C)
  - User Action: Approve a parser-adapter revision only if the required behavior cannot be achieved without leaving the approved pypdf/no-OCR boundary.
  - Agent Work: Prove the downstream-visible no-text rule in both benchmark modes and finalize the pypdf compatibility decision. Execute both normal and layout modes on the image-only fixture, verify exact classification in each, scan dependencies for OCR, and record the selected-mode Phase impact.
    1. Run the benchmark against the frozen image-only fixture using normal extraction and layout extraction.
    2. Assert exact outcome code `NO_EXTRACTABLE_TEXT` and zero usable extracted characters for both modes.
    3. Confirm no OCR call, OCR package, alternate parser, or manual text substitution is used.
    4. Record both mode results, the selected mode, exact failure rule, benchmark evidence, and `PASS` or `FAIL` result.
  - Output: Verified normal/layout `NO_EXTRACTABLE_TEXT` evidence and final PDF gate decision.
  - Acceptance:
    - Both modes reproducibly return the exact outcome, no OCR path exists, and the selected digital mode also satisfies (04C).
  - Validation:
    - Required: Focused exact-code assertions for normal and layout modes, dependency/source search for OCR or alternate parsers, and repeated image-only runs.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` only when a failed gate requires an approved parser-adapter revision.
  - Files: Focused benchmark tests, aggregate PDF benchmark results, `backend/evaluation/reports/phase_0_feasibility.md`.

## Mandatory Batch05 - ShopAIKey Embedding Compatibility Gate

### Goal

Verify the locked ShopAIKey `text-embedding-3-small` adapter with 1536-dimensional output, then record retrieval-quality and request-latency baselines for Plan 2.

### Dependencies

- Mandatory Batch01 complete through (01D) and the Batch03 ShopAIKey diagnostic foundation available.
- User-provided or user-confirmed initial labeled retrieval subset.
- Explicit authorization for the live ShopAIKey embedding smoke test.
- Pre-recorded quality and request-latency baselines for validating the fixed adapter.

### Scope Boundary

**Why this batch exists**

The relational/graph foundation and later ranking work require a verified provider contract before schema or vector-index implementation. This gate confirms that ShopAIKey actually honors the fixed model, dimension, batching, and response-shape requirements.

**Files or modules likely created or updated**

- Retrieval-subset manifest under `backend/evaluation/labels/`
- Ignored local labeled data path
- Focused embedding benchmark runner under `backend/evaluation/`
- Focused benchmark/metric tests
- Aggregate embedding result artifact under `backend/evaluation/reports/`
- `backend/evaluation/reports/phase_0_feasibility.md`
- `backend/pyproject.toml`
- `.env.example`

**Required outputs or artifacts**

- Frozen validation slice from the seeded 60/20/20 split, locked `0`-`3` labels, and pre-registered quality/latency baselines.
- Sanitized scalar/batch compatibility and failure-path evidence.
- Retrieval quality and provider request-latency baseline results.
- One locked ShopAIKey model/dimension/preprocessing contract.

**Batch acceptance**

- Only ShopAIKey `text-embedding-3-small` with `dimensions=1536` is exercised.
- Scalar and batch inputs return ordered, finite float vectors with exactly 1536 values each.
- The fixed adapter passes the approved initial quality and request-latency baselines.

**Batch validation**

- Metric, percentile, dimension, response-order, finite-value, allowlist, and seed-handling tests.
- Scalar/batch equivalence checks for identical inputs.
- Aggregate result completeness and private-data scans.
- Failure-path and secret-safety checks.

**Explicit non-goals**

- Alternate embedding models or dimensions, local/GPU embedding serving, Neo4j indexes, production retrieval, ranking-weight tuning, held-out ranking claims, or full Phase 5 evaluation.
- Post-hoc baselines or threshold changes made after results are visible.

### Tasks

- [ ] (05A): Freeze the seeded retrieval subset and embedding validation protocol
  - Source of Truth: `docs/plans/Plan_1.md` > `## 3. Prerequisites from Prior Phases`; `docs/plans/Plan_1.md` > `### 7.4 Embedding benchmark record`; `docs/plans/Master_plan.md` > `## 17. Embedding and Retrieval` > `### 17.1 Locked embedding contract`; `docs/plans/Master_plan.md` > `## 17. Embedding and Retrieval` > `### 17.2 Provider compatibility gate`; `docs/plans/Master_plan.md` > `## 19. Evaluation Plan` > `### 19.2 Relevance labels`
  - Source Requirements:
    - Lock ShopAIKey `text-embedding-3-small`, `dimensions=1536`, float encoding, and no E5 prefixes before execution.
    - Use relevance labels `0`-`3` and the validation slice of the fixed seeded 60/20/20 split; do not inspect held-out results.
    - Record numeric `nDCG@10`, Recall@10, and median/P95 provider-latency baselines before execution.
  - Dependencies: (01D)
  - User Action: Confirm label provenance and split; approve the numeric quality/latency baselines and live embedding-call authorization.
  - Agent Work: Freeze safe subset metadata, representations, request boundaries, batching ceiling, timeout policy, and pass criteria before live results are observed.
  - Output: Frozen retrieval-subset manifest and pre-registered ShopAIKey embedding validation protocol.
  - Acceptance: The protocol fixes model, dimensions, encoding, preprocessing, inputs, metrics, thresholds, and failure criteria without loading held-out outcomes.
  - Validation: Required manifest/schema, seed/split integrity, threshold timestamp/order, and held-out-access checks.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when labels/split, numeric baselines, or live-use authorization are missing.
  - Files: Retrieval manifest, ignored local data paths, and `backend/evaluation/reports/phase_0_feasibility.md`.

- [ ] (05B): Implement the focused ShopAIKey embedding diagnostic and benchmark
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.4 Embedding benchmark record`; `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Master_plan.md` > `### 17.1 Locked embedding contract`; `docs/plans/Master_plan.md` > `### 17.3 Text representations`
  - Source Requirements: Call only `text-embedding-3-small` with `dimensions=1536`; support scalar and bounded batch inputs; validate ordering, exactly 1536 finite floats, and sanitized provider failures; apply no E5 prefixes.
  - Dependencies: (03A), (05A)
  - User Action: None beyond the authorized local ShopAIKey credentials.
  - Agent Work: Reuse the Batch03 provider configuration/HTTP boundary and existing metrics; add only the missing embedding request, validation, and aggregate benchmark behavior.
  - Output: Focused ShopAIKey embedding runner and typed aggregate result schema.
  - Acceptance: The runner rejects alternate models/dimensions, never logs sensitive inputs or credentials, and produces all required compatibility, quality, and latency fields.
  - Validation: Required synthetic tests for metrics, percentiles, scalar/batch response ordering, dimension/finite values, allowlist, deterministic seed handling, provider failures, and private-text suppression.
  - Blocked Condition: None; live execution is deferred to (05C).
  - Files: Focused runner/tests, `backend/pyproject.toml`, and aggregate report path.

- [ ] (05C): Execute the live ShopAIKey embedding compatibility and baseline run
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.4 Embedding benchmark record`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 17.2 Provider compatibility gate`; `docs/plans/Master_plan.md` > `## 19. Evaluation Plan` > `### 19.2 Relevance labels`
  - Source Requirements: Use only redacted or synthetic text from the frozen validation slice and pre-registered protocol; run scalar, batch, invalid-response/failure handling, retrieval metrics, and latency measurements without exposing raw text.
  - Dependencies: (05B)
  - User Action: Ensure the ignored credentials and approved labeled subset remain available.
  - Agent Work: Execute the authorized live run, confirm scalar/batch equivalence and ordering, record dimension/finite-value checks, and store sanitized aggregate metrics.
  - Output: Complete compatibility record plus model ID, dimension, `nDCG@10`, Recall@10, and median/P95 request latency.
  - Acceptance: Every required field is complete, all vectors have 1536 finite floats in source order, and no held-out metric or raw private text appears.
  - Validation: Required schema/dimension/order checks, metric recomputation, model allowlist, failure-path check, and held-out/private-data scan.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when live authorization, credentials, or the frozen labeled subset is unavailable.
  - Files: Aggregate embedding result, feasibility report, and runner/tests only when corrections are required.

- [ ] (05D): Lock the verified ShopAIKey embedding handoff
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.4 Embedding benchmark record`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`; `docs/plans/Master_plan.md` > `### 17.2 Provider compatibility gate`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements: The downstream contract is fixed as ShopAIKey `text-embedding-3-small`, 1536 dimensions, float encoding, no E5 prefixes, and the versioned text representations; it passes only when compatibility and pre-recorded quality/latency gates pass.
  - Dependencies: (05C)
  - User Action: Approve an embedding-adapter revision only if the locked provider contract fails.
  - Agent Work: Recalculate gate results, record the exact request/preprocessing/batching/error contract and evidence, then mark `PASS` or block Plan 2 without substituting a model.
  - Output: Verified embedding adapter handoff and evidence-backed gate result.
  - Acceptance: The exact fixed contract is recorded and passes every gate, or Phase 0 honestly blocks with only the adapter revision path identified.
  - Validation: Required independent quality/latency recalculation, model/dimension/order checks, failure evidence, and source/report cross-check.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when baselines were not approved or a failed gate requires an approved adapter revision.
  - Files: Aggregate embedding results, feasibility report, and `.env.example`.

## Mandatory Batch06 - Evidence Consolidation and Phase 0 Exit Gate

### Goal

Consolidate measured gate evidence, lock compatible versions and adapter decisions, remove unnecessary temporary artifacts, and produce an honest Plan 2 handoff only when every required gate passes.

### Dependencies

- Mandatory Batch02 complete through (02C).
- Mandatory Batch03 complete through (03F).
- Mandatory Batch04 complete through (04D).
- Mandatory Batch05 complete through (05D).
- All required user approvals and inputs recorded without secrets or private content.

### Scope Boundary

**Why this batch exists**

Individual diagnostics are not a phase exit. Plan 2 requires one coherent, reproducible decision record and a clean scaffold whose versions, commands, security boundaries, and blocking status agree.

**Files or modules likely created or updated**

- `backend/evaluation/reports/phase_0_feasibility.md`
- Sanitized aggregate artifacts under `backend/evaluation/reports/`
- `backend/pyproject.toml` and backend lockfile if used
- `frontend/package.json` and frontend package lock
- `.env.example`
- `.gitignore`
- `README.md`
- Gate-required scripts/tests only

**Required outputs or artifacts**

- Complete feasibility report with final decision table at EOF.
- Exact dependency and adapter decision locks.
- Clean, safe, minimal three-folder scaffold.
- Explicit `PASS` handoff or blocked adapter-only revision path.

**Batch acceptance**

- Every required gate has reproducible, sanitized evidence.
- Plan 2 starts only after an all-pass assertion succeeds.
- README, report, dependency locks, commands, and tracker agree.
- No secret, private source data, unnecessary experiment, fallback stack, or production behavior remains.

**Batch validation**

- Full Phase 0 source-to-evidence checklist.
- All focused fake-based tests and authorized live/local diagnostics.
- Dependency/package resolution and exact-pin checks.
- Secret/private-data, environment, root-folder, OCR/fallback, and out-of-scope scans.
- Git tracked/ignore checks when repository metadata is functional.
- Final report-table EOF and all-pass assertions.

**Explicit non-goals**

- Starting Plan 2 implementation, repeating passed benchmarks, broad dependency upgrades, CI, deployment, or any deferred production feature.
- Claiming a blocked or failed gate is practically complete.

### Tasks

- [ ] (06A): Assemble feasibility evidence and a provisional decision table
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.5 Feasibility report decision block`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`
  - Source Requirements:
    - The report must contain evidence and decisions for scaffold safety, Astryx, ShopAIKey, PDF extraction, and embeddings.
    - The report must end with a table containing `Gate`, `Result`, `Evidence`, `Selected mode/version`, and `Phase impact`; its status remains provisional until post-cleanup validation in (06B).
    - Every required gate must ultimately be `PASS` before Plan 2 starts.
  - Dependencies: (02C), (03F), (04D), (05D)
  - User Action: Confirm any still-pending approvals or explicitly accept that Phase 0 remains blocked; never paste secrets or private source content.
  - Agent Work: Convert gate-level aggregate outputs into one auditable draft without copying raw provider payloads, private texts, or unverified claims. Cross-check source requirements against gate artifacts, reconcile inconsistent gate-level status, and draft a clearly provisional decision table at the physical end of the report.
    1. Complete prerequisite, protocol, gate-version, command, measurement, and security sections from aggregate evidence.
    2. Link or name reproducible local artifacts and single-purpose commands for each gate.
    3. Verify every claimed selection matches its source result and approved threshold/rule.
    4. Populate one provisional decision row per required gate with `PASS`, `FAIL`, or `BLOCKED`, never an implied success.
    5. Mark the table provisional pending (06B), place it at the physical end of `phase_0_feasibility.md`, and do not append narrative after it.
  - Output: Evidence-complete draft of `backend/evaluation/reports/phase_0_feasibility.md` with a provisional decision table at EOF.
  - Acceptance:
    - Every draft claim traces to a sanitized artifact/command, all required columns are populated, no incomplete gate is marked `PASS`, and no final Phase 0 completion claim is made.
  - Validation:
    - Required: Source-to-report requirement checklist, artifact existence check, heading/order check, provisional-table EOF check, gate-status consistency check, and secret/private-data scan.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when a required user input/approval prevents a gate decision; otherwise a failed technical gate is recorded as `FAIL`.
  - Files: `backend/evaluation/reports/phase_0_feasibility.md` and existing sanitized aggregate artifacts only.

- [ ] (06B): Lock versions, remove temporary artifacts, and run global safety checks
  - Source of Truth: `docs/plans/Plan_1.md` > `## 8. Implementation Steps`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`; `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack`; `docs/plans/Master_plan.md` > `## 23. Environment Configuration`; `docs/plans/Master_plan.md` > `## 24. Local Testing Strategy` > `### 24.5 Local verification commands`
  - Source Requirements:
    - Lock exact compatible Python/frontend/FastAPI/Astryx/LangGraph/Neo4j-driver/evaluation dependency decisions for Plan 2; FastAPI must be at least `0.135.0`.
    - Remove temporary dependencies or scaffold artifacts not required by a locked gate.
    - Verify npm resolution, the exact three product working folders, single-root environment use, and absence of tracked/committed secrets or private fixtures.
    - Keep validation local-only; do not add CI.
  - Dependencies: (06A)
  - User Action: Repair or initialize repository Git metadata if tracked-file/ignore proof is required and remains unavailable; confirm no local private file should be committed.
  - Agent Work: Leave a minimal reproducible handoff surface rather than an accumulation of Phase 0 experiments. Pin exact compatible decisions, remove unused artifacts/dependencies, document only real commands, and execute the global validation matrix.
    1. Reconcile dependency declarations/locks with the versions proven or resolved during Phase 0, including the master-plan minimum for FastAPI.
    2. Record the exact Python, frontend, FastAPI, Astryx, LangGraph, Neo4j-driver, pypdf, Pydantic, ShopAIKey adapter, and embedding/evaluation dependency decisions.
    3. Remove demo output, duplicate helpers, unused packages, caches, raw provider output, and benchmark artifacts not required for reproducibility.
    4. Document single-purpose Phase 0 commands in the report and README; mark future production commands as not yet available rather than inventing them.
    5. Verify required ShopAIKey failure exits, secret-safe output, both image-only parser-mode classifications, fixed-split embedding metrics, Astryx resolution, three-folder boundary, root env rules, and private-data ignore rules.
    6. Use tracked-file/ignore checks when Git is functional; otherwise record that repository-state proof remains blocked and do not claim it passed.
    7. Update the report with post-cleanup evidence and revised provisional rows while keeping the decision table at EOF for finalization in (06C).
  - Output: Exact dependency locks, clean Phase 0 scaffold, documented commands, and global validation results.
  - Acceptance:
    - Only gate-required artifacts/dependencies remain, all reproducible decisions are pinned, validation evidence is complete, and no secret/private data is exposed.
  - Validation:
    - Required: Backend/frontend resolution checks, focused tests, all single-purpose gate commands, filesystem structure audit, dependency/source searches, secret scan, and Git tracked/ignore audit when available.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when unusable Git metadata prevents required proof that `.env` and private fixtures are not committed; other validation failures remain technical `FAIL` results.
  - Files: `backend/pyproject.toml`, backend lockfile if used, `frontend/package.json`, frontend package lock, `.env.example`, `.gitignore`, `README.md`, `backend/evaluation/reports/phase_0_feasibility.md`, gate-required scripts/tests/artifacts.

- [ ] (06C): Enforce the Phase 0 exit gate and produce the Plan 2 handoff
  - Source of Truth: `docs/plans/Plan_1.md` > `### 7.5 Feasibility report decision block`; `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 (Master Phase 1)`; `docs/plans/Master_plan.md` > `### Phase 0 — Feasibility and compatibility gates`; `docs/plans/Master_plan.md` > `### Phase 1 — Foundation, Docker, and source-of-truth data`
  - Source Requirements:
    - Plan 2 receives exact pinned dependency decisions, verified ShopAIKey behavior, verified Astryx APIs, selected PDF mode/rule, the locked `text-embedding-3-small`/1536 contract, and the safe scaffold.
    - Every required gate must be `PASS`; any `FAIL`, `BLOCKED`, or unknown result blocks Plan 2.
    - A failed gate may revise only its affected adapter; no broad fallback stack is allowed.
  - Dependencies: (06B)
  - User Action: Approve any required adapter-only master-plan revision and supply missing user-owned prerequisites; otherwise none when all rows pass.
  - Agent Work: Make phase progression a mechanical consequence of the evidence rather than a narrative assertion. Finalize the table from post-cleanup evidence, set Phase 0 status, prepare the exact handoff, and preserve the final decision table at report EOF.
    1. Confirm every mandatory task and validation, including (06B) cleanup and global safety checks, is complete or explicitly blocked with reason.
    2. Replace provisional statuses with final evidence-backed rows and require `PASS` for all required scaffold, Astryx, provider, PDF, embedding, cleanup, and safety gates.
    3. When any result is not `PASS`, set Phase 0/Plan 2 status to blocked and identify only the affected adapter revision path.
    4. When all results pass, record the exact pins, modes, dimensions, public API matrix, commands, and scaffold artifacts Plan 2 must consume without re-benchmarking.
    5. Update README Phase 0 status and the canonical task checkboxes from evidence, remove the provisional marker, then re-check final report-table EOF and source consistency.
  - Output: Final `backend/evaluation/reports/phase_0_feasibility.md`, evidence-backed Phase 0 status, and complete Plan 2 handoff contract.
  - Acceptance:
    - Plan 2 is authorized only when every required gate is `PASS`; otherwise the blocking reason and adapter-only repair scope are explicit.
  - Validation:
    - Required: Final decision-table all-pass assertion, handoff completeness checklist, canonical task-checkbox synchronization, README/report status comparison, and out-of-scope/fallback search.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` for missing prerequisites or required adapter revision approval; any technical gate failure also blocks Plan 2 without being mislabeled as user-blocked.
  - Files: `backend/evaluation/reports/phase_0_feasibility.md`, `README.md`, dependency/configuration locks, this task file only when A2 updates a canonical task checkbox.

## Optional Future Tracks

No optional implementation track is authorized by Plan 1. All items listed under `docs/plans/Plan_1.md` section 5 remain out of scope, and future master-plan phases must be handled by their own approved task files.
