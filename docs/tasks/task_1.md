# JobAgent Plan 1 Execution Tasks

## Purpose

Retire the Phase 0 feasibility risks before production work begins by creating the
minimal scaffold, proving the pinned Astryx composition path, proving pypdf behavior
on synthetic fixtures, proving the locked ShopAIKey chat and embedding contract, and
publishing a complete compatibility decision record. These tasks do not implement
production JobAgent flows.

## Project Context Notes

- Root `README.md` was not found; project context therefore comes from the approved
  plans and current repository evidence.
- The repository currently contains planning documents, `.gitignore`, and a
  user-managed root `.env`; no frontend, backend, infrastructure, or reusable runtime
  implementation exists yet. The `.env` is ignored and its contents were not read.
- Verified local tools at task-authoring time: Python 3.13.7, Node.js 24.11.0,
  npm 11.6.1, Docker 29.3.1, and Git 2.47.0.
- The locked stack for later phases is React/TypeScript/Vite with Astryx, Python with
  FastAPI/Pydantic, ShopAIKey `gpt-4o-mini`, ShopAIKey
  `text-embedding-3-small` at 1536 dimensions, SQLite, and Neo4j. Phase 0 installs
  only what its diagnostics require.
- Apply the user-supplied `AGENTS.md` rules: search before writing, reuse or refactor
  existing logic, keep files single-purpose and preferably below 300 lines, avoid
  speculative abstractions, and inspect all callers when changing shared behavior.

## Authority and Scope

### Primary Source

- `docs/plans/Plan_1.md` in full.

`docs/plans/Master_plan.md` supplies the exact contracts referenced by the primary
source. `docs/plans/Plan_2.md` is boundary context only: it cannot start until all
tasks here are accepted and the final Phase 0 report has every gate at PASS. No
material conflict was found among these sources.

### Source Section Index

- `docs/plans/Plan_1.md` > `## 1. Objective` -> Phase 0 outcome and fail-gate rule.
- `docs/plans/Plan_1.md` > `## 3. Prerequisites from Prior Phases` -> local tools,
  secret handling, and synthetic fixture prerequisites.
- `docs/plans/Plan_1.md` > `## 4. Scope` and `## 5. Out of Scope` -> mandatory work
  and production-feature boundary.
- `docs/plans/Plan_1.md` > `## 6. Target Directory Structure` -> Phase 0 file and
  directory ownership.
- `docs/plans/Plan_1.md` > `## 7. Technical Specifications` -> scaffold, ShopAIKey,
  pypdf, Astryx, and decision-record contracts.
- `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan` -> required commands,
  observable PASS markers, manual checks, and failure handling.
- `docs/plans/Plan_1.md` > `## 10. Handoff Notes for Plan 2 / Master Phase 1` ->
  accepted Phase 0 artifacts and downstream reuse boundary.
- `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack` -> locked provider,
  models, parser, and later-phase dependency constraints.
- `docs/plans/Master_plan.md` > `## 15. Frontend UX Plan` > `### 15.3 Chat components`
  -> Astryx public-component and CLI-documentation rule.
- `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` and
  `## 17. Embedding and Retrieval` -> seven provider capabilities and the fixed
  embedding contract.
- `docs/plans/Master_plan.md` > `## 22. Local Demo Safeguards` and
  `## 23. Environment Configuration` -> one-root-environment and secret rules.
- `docs/plans/Master_plan.md` > `## 25. Implementation Phases` >
  `### Phase 0 — Feasibility and compatibility gates` -> mandatory exit gates.

### Approved Architecture and Constraints

- Keep exactly one user-managed root `.env`; commit only `.env.example` with safe
  values and empty secrets. Never print or commit keys or authorization headers.
- Keep Phase 0 diagnostic-only: no FastAPI endpoints, production adapters,
  persistence, migrations, Docker services, Agent runtime, OCR, alternate provider,
  alternate model, alternate embedding dimensions, or fallback stack.
- Use only documented public APIs from the pinned Astryx package. A missing direct
  component must have a documented same-package composition path.
- Keep `gpt-4o-mini`, `text-embedding-3-small`, 1536 finite float dimensions, and
  scalar/batch input ordering unchanged unless the approved plan itself changes.
- Use five synthetic digital CVs and one synthetic image-only PDF; no real personal
  data or OCR is permitted.
- Treat the detailed task entries below as authoritative. Later tasks may extend the
  Phase 0 report and manifests established by earlier tasks but must not recreate
  their logic or broaden their scope.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Minimal repository and pinned Astryx evidence | (01A), (01B) | None |
| Batch02 | Reproducible pypdf compatibility evidence | (02A) | Batch01 |
| Batch03 | Reproducible ShopAIKey compatibility evidence | (03A) | Batch02 |
| Batch04 | Locked dependencies and final Phase 0 decision | (04A) | Batch03 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_1_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_1_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.

## Mandatory Batch01 - Minimal Repository and Pinned Astryx Evidence

### Goal

Establish the smallest safe repository foundation and prove that one pinned Astryx
version supports the required public components or documented compositions.

### Dependencies

None.

### Scope Boundary

This batch owns root configuration documentation, minimal Phase 0 manifests and
directories, Astryx initialization, a minimal render, and Astryx evidence. It does
not own production backend/frontend behavior, Docker services, databases, or any
provider/PDF gate.

### Tasks

- [x] (01A): Create the minimal scaffold and one-root configuration contract
  - Source of Truth: `docs/plans/Plan_1.md` > `## 6. Target Directory Structure`;
    `docs/plans/Plan_1.md` > `## 7. Technical Specifications` >
    `### 7.1 Scaffold and dependency lock`; `docs/plans/Master_plan.md` >
    `## 23. Environment Configuration`
  - Source Requirements:
    - Create only the Phase 0 `frontend/`, `backend/`, and `infrastructure/`
      scaffold and listed minimal manifests; later phases own production modules.
    - Document the exact Master Section 23 variable names in root `.env.example`.
      Keep `SHOPAIKEY_API_KEY` and `NEO4J_PASSWORD` empty, keep safe non-secret
      defaults where specified, and never load `.env.example` at runtime.
    - Preserve the existing ignored root `.env`; extend `.gitignore` only for actual
      Phase 0 secret, cache, build, runtime-data, or local-volume risks.
  - Dependencies: None
  - User Action: None. The existing root `.env` remains user-managed and must not be
    opened, copied, replaced, or committed.
  - Agent Work:
    1. Search the repository for existing manifests, configuration loaders, ignore
       rules, and owned paths; reuse aligned content and do not duplicate settings.
    2. Create the target directories and a minimal installable
       `backend/pyproject.toml` plus `backend/app/__init__.py`; include no Phase 1
       application behavior or dependencies not needed by Phase 0.
    3. Create `.env.example` with exactly the approved variable names and safe
       values, then confirm `.env`, local runtime data, caches, build outputs, and
       future local database/volume data remain ignored.
    4. Record the commands and repository evidence in the A1 execution report.
  - Output: A minimal three-folder scaffold, parseable Python project metadata, and
    a safe root environment template that later Phase 0 tasks can extend.
  - Acceptance:
    - Every directory and file assigned to (01A) exists without unrelated placeholder
      modules or production behavior; paths assigned to later tasks remain under
      their later owners.
    - `backend/pyproject.toml` is valid TOML and installable, and contains only the
      dependencies/configuration currently required for Phase 0.
    - `.env.example` contains exactly the Master Section 23 names; secret fields are
      empty and no real secret or authorization value appears in tracked files.
    - The existing `.env` is unchanged, ignored, and untracked.
  - Validation:
    - Required: `python -c "import pathlib,tomllib; tomllib.loads(pathlib.Path('backend/pyproject.toml').read_text(encoding='utf-8')); print('PYPROJECT=PASS')"` -> prints `PYPROJECT=PASS`.
    - Required: `@('frontend','backend','backend/app','backend/tests/fixtures/cv','infrastructure','infrastructure/docker','infrastructure/neo4j','infrastructure/scripts') | ForEach-Object { if (-not (Test-Path -LiteralPath $_)) { throw "Missing $_" } }; 'SCAFFOLD=PASS'` -> prints `SCAFFOLD=PASS`.
    - Required: `python -c "from pathlib import Path; expected=set('APP_ENV FRONTEND_ORIGIN VITE_API_BASE_URL SQLITE_PATH FILES_DIR NEO4J_URI NEO4J_USER NEO4J_PASSWORD SHOPAIKEY_BASE_URL SHOPAIKEY_API_KEY LLM_MODEL LLM_TEMPERATURE EMBEDDING_MODEL EMBEDDING_DIMENSIONS MAX_PDF_SIZE_MB MAX_PDF_PAGES URL_FETCH_TIMEOUT_SECONDS URL_MAX_RESPONSE_MB TOOL_LOOP_LIMIT'.split()); actual={line.split('=',1)[0] for line in Path('.env.example').read_text(encoding='utf-8').splitlines() if line and not line.lstrip().startswith('#')}; assert actual==expected,(sorted(expected-actual),sorted(actual-expected)); print('ENV_TEMPLATE=PASS')"` -> prints `ENV_TEMPLATE=PASS`.
    - Required: `git check-ignore .env; git diff --check` -> `.env` is ignored and
      the diff has no whitespace errors.
  - Blocked Condition: The primary and Master sources disagree on an environment
    name, repository owner, or tracked secret policy; stop without guessing and
    request source correction.
  - Files: `.env.example`, `.gitignore`, `backend/pyproject.toml`,
    `backend/app/__init__.py`, `frontend/`, `backend/tests/fixtures/cv/`,
    `infrastructure/docker/`, `infrastructure/neo4j/`, `infrastructure/scripts/`

- [x] (01B): Pin Astryx and prove every required public component path
  - Source of Truth: `docs/plans/Plan_1.md` > `## 4. Scope`;
    `docs/plans/Plan_1.md` > `## 7. Technical Specifications` >
    `### 7.1 Scaffold and dependency lock` and `### 7.4 Astryx evidence contract`;
    `docs/plans/Plan_1.md` > `## 9. Verification & Testing Plan`
  - Source Requirements:
    - Run `npx astryx init --features agents --agent codex` in `frontend/`, commit
      `package.json` and `package-lock.json`, and record the exact stable version.
    - Prove public imports, required props/callbacks, and direct availability or a
      documented same-package composition for `AppShell`, `ChatLayout`,
      `ChatComposer`, `ChatToolCalls`, `ChatMessage`, `ButtonGroup`, `Card`,
      `Collapsible`, and `ProgressBar` using the pinned CLI documentation.
    - Keep only initializer output and the minimal documented render; undocumented
      props, internal package paths, and production chat behavior are forbidden.
  - Dependencies: (01A) scaffold and manifest ownership
  - User Action: None.
  - Agent Work:
    1. Inspect the current frontend files and the pinned Astryx CLI help before
       writing UI code; use the initializer instead of hand-building its output.
    2. Run the required initializer, resolve the exact Astryx version from the
       lockfile, and implement only the smallest public-import render needed to prove
       initialization.
    3. Discover the pinned CLI's exact documentation syntax, run it for every named
       component, and test a documented composition when a component is not direct.
    4. Create `docs/feasibility/phase_0_report.md` with timestamp/runtime facts and a
       completed Astryx matrix containing package/version, exact CLI command, public
       import, required props/callbacks, and direct/composed status. Omit unfinished
       gate sections rather than adding placeholders.
    5. Run a clean package install and build, then record command output and component
       evidence in the A1 execution report.
  - Output: A locked, minimally rendering Astryx frontend and an auditable completed
    Astryx section in the Phase 0 report.
  - Acceptance:
    - `package-lock.json` resolves one exact stable Astryx version and `npm ci`
      reproduces it.
    - The minimal frontend builds and renders using documented public imports only.
    - Every required component has a complete evidence row and either exists directly
      or has a working documented composition from the same pinned package.
    - Every evidence row names the exact successful pinned-CLI documentation command;
      no placeholder, unexplained failure, invented prop, or internal import remains.
  - Validation:
    - Required: `Set-Location frontend; npx astryx --help` -> exposes the exact
      documentation-command syntax used and recorded in the report.
    - Required: rerun each exact component documentation command recorded in
      `docs/feasibility/phase_0_report.md` -> output supports its corresponding matrix
      row. This validation is discovery-bound because the approved plan forbids
      guessing the pinned CLI syntax.
    - Required: `Set-Location frontend; npm ci; npm run build` -> clean install and
      minimal production build both exit `0`.
    - Required: `Set-Location frontend; npm run dev -- --host 127.0.0.1` -> manual
      local inspection confirms the minimal Astryx render has no import/runtime error;
      stop the development server after inspection.
  - Blocked Condition: The stable pinned CLI has no inspectable documentation command,
    the initializer cannot produce a reproducible lockfile, or any required component
    lacks both a public API and a documented same-package composition path. Record the
    failed gate and do not start Batch02 or add another design system.
  - Files: `frontend/package.json`, `frontend/package-lock.json`,
    `frontend/src/main.tsx`, initializer-required frontend configuration discovered
    in step 1, `docs/feasibility/phase_0_report.md`

## Mandatory Batch02 - Reproducible pypdf Compatibility Evidence

### Goal

Prove that the locked pypdf baseline extracts meaningful text from representative
synthetic digital CVs and rejects an image-only CV without OCR.

### Dependencies

(01A) scaffold/configuration and (01B) established Phase 0 report.

### Scope Boundary

This batch owns only the six synthetic PDF fixtures, the reusable extraction
diagnostic, its minimum Phase 0 dependency, and the PDF report evidence. It does not
own upload validation, storage, profile extraction, OCR, or a production parser.

### Tasks

- [ ] (02A): Build and pass the synthetic pypdf extraction gate
  - Source of Truth: `docs/plans/Plan_1.md` > `## 7. Technical Specifications` >
    `### 7.3 PDF feasibility contract`; `docs/plans/Plan_1.md` >
    `## 9. Verification & Testing Plan` > `### Automated/local commands`;
    `docs/plans/Master_plan.md` > `## 10. CV Ingestion and Approval Flow` >
    `### 10.2 Processing`
  - Source Requirements:
    - Commit five representative digitally born synthetic CVs and one synthetic
      image-only PDF with no real personal data.
    - Run both pypdf normal and layout extraction on every digital fixture, normalize
      whitespace only for measurement, and report page count and non-whitespace
      character count.
    - Apply one documented meaningful-text rule: at least four digital fixtures must
      contain useful identity/experience/skills text, while the image-only fixture
      must be `NO_EXTRACTABLE_TEXT`. Never introduce or call OCR.
  - Dependencies: (01A) `backend/pyproject.toml` and fixture path; (01B)
    `docs/feasibility/phase_0_report.md`
  - User Action: None.
  - Agent Work:
    1. Search for existing PDF helpers, fixture generators, and quality rules before
       writing; reuse any aligned implementation and keep the feasibility rule in one
       owned location.
    2. Create the six named fixtures using synthetic identities and varied but
       representative experience/skills layouts; ensure the image-only file has no
       text layer. Do not add a runtime dependency solely for fixture generation when
       standard or already-installed tooling suffices.
    3. Add only the required pinned pypdf/test dependency to
       `backend/pyproject.toml`, then implement the single-purpose diagnostic with
       deterministic iteration, concise per-fixture output, and non-zero gate exits.
    4. Run the diagnostic and extend the Phase 0 report with the exact pypdf version,
       meaningful-text rule, per-fixture normal/layout outcomes, any one allowed
       digital failure, aggregate threshold, and final PDF gate result.
    5. Inspect the script and all callers to confirm that no OCR import, subprocess,
       service, or fallback path exists; append evidence to the A1 report.
  - Output: Six safe fixtures, one reusable pypdf diagnostic, and complete PDF gate
    evidence in the Phase 0 report.
  - Acceptance:
    - All six named PDFs are valid and synthetic; the five digital files contain
      extractable representative CV text and the image-only file has no text layer.
    - The script evaluates both extraction modes, reports the required measurements,
      exits non-zero below threshold or when image-only is accepted, and never uses
      OCR.
    - At least four of five digital fixtures pass the documented meaningful-text rule,
      the image-only fixture is `NO_EXTRACTABLE_TEXT`, and the final output is
      `PYPDF_COMPATIBILITY=PASS`.
    - The report contains complete reproducible per-fixture and aggregate evidence
      with no placeholder or hidden failure.
  - Validation:
    - Required: `python infrastructure/scripts/verify_pdf_extraction.py` -> exits `0`,
      reports at least `4/5` digital successes, rejects `image_only_cv.pdf` as
      `NO_EXTRACTABLE_TEXT`, and ends with `PYPDF_COMPATIBILITY=PASS`.
    - Required: `git diff --check` -> fixture/script/report changes introduce no diff
      errors.
  - Blocked Condition: Fewer than four representative digital fixtures pass, the
    image-only fixture is accepted, or the result requires OCR/another parser. Record
    the failing evidence, revise only the pypdf rule/composition allowed by the plan,
    and do not start Batch03 until this task passes.
  - Files: `backend/pyproject.toml`,
    `backend/tests/fixtures/cv/digital_cv_01.pdf`,
    `backend/tests/fixtures/cv/digital_cv_02.pdf`,
    `backend/tests/fixtures/cv/digital_cv_03.pdf`,
    `backend/tests/fixtures/cv/digital_cv_04.pdf`,
    `backend/tests/fixtures/cv/digital_cv_05.pdf`,
    `backend/tests/fixtures/cv/image_only_cv.pdf`,
    `infrastructure/scripts/verify_pdf_extraction.py`,
    `docs/feasibility/phase_0_report.md`

## Mandatory Batch03 - Reproducible ShopAIKey Compatibility Evidence

### Goal

Prove the locked ShopAIKey chat, tool/schema/streaming, and scalar/batch embedding
contract through one safe reusable local diagnostic.

### Dependencies

(02A) accepted, with the shared manifest and Phase 0 report available.

### Scope Boundary

This batch owns a diagnostic script, only its minimum Phase 0 dependencies, and
provider evidence. It does not own a production LLM/embedding adapter, Agent flow,
retrieval, provider fallback, benchmark, or real business tool.

### Tasks

- [ ] (03A): Build and pass the ShopAIKey chat and embedding gate
  - Source of Truth: `docs/plans/Plan_1.md` > `## 7. Technical Specifications` >
    `### 7.2 ShopAIKey diagnostic contract`; `docs/plans/Master_plan.md` >
    `## 16. ShopAIKey Integration` > `### 16.1 Configuration` and
    `### 16.2 Startup/diagnostic compatibility checks`;
    `docs/plans/Master_plan.md` > `## 17. Embedding and Retrieval` >
    `### 17.1 Locked embedding contract` and `### 17.2 Provider compatibility gate`
  - Source Requirements:
    - Read `SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`, `LLM_MODEL`,
      `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS` through one minimal loader from
      process/root environment; fail fast on a missing key without printing values.
    - Prove exactly seven capability groups: model discovery, basic chat, function
      calling, tool-result round trip, structured schema, ordered text streaming, and
      scalar/batch embeddings.
    - Keep `gpt-4o-mini` and `text-embedding-3-small`; embeddings must use float
      encoding and exactly 1536 finite values per input in stable input order.
    - Prefer strict schema only when it passes. Otherwise select ordinary function
      schema or JSON mode with Pydantic validation and at most one repair; record the
      exact production strategy without silently substituting models or dimensions.
  - Dependencies: (01A) root environment contract; (02A) shared
    `backend/pyproject.toml` and Phase 0 report
  - User Action: Before live validation, place a valid `SHOPAIKEY_API_KEY` only in the
    ignored root `.env` and ensure provider/network access. Never paste the value into
    reports, tracked files, prompts, or command output.
  - Agent Work:
    1. Search for existing settings, HTTP/client, schema, and diagnostic logic; reuse
       aligned code and installed dependencies before adding any helper or package.
    2. Implement one side-effect-free synthetic function and the seven capability
       groups, including validated tool arguments/result/final response, strict-mode
       probing, ordered non-empty stream deltas, and scalar plus distinct batch
       embeddings.
    3. Normalize timeout, rate-limit, malformed response, model absence, dimension
       mismatch, and ordering mismatch into concise non-zero failure codes. Ensure
       exception/log paths never expose a key, authorization header, or full secret
       configuration.
    4. Add only minimum successful pinned diagnostic dependencies to
       `backend/pyproject.toml`, run the real-provider check once per validation, and
       emit a short seven-row table followed by the required final marker.
    5. Extend the Phase 0 report with exact client/provider dependency versions,
       results for all seven groups, requested/observed model IDs, embedding evidence,
       error behavior, and the selected schema strategy; append sanitized evidence to
       the A1 report.
  - Output: A reusable safe ShopAIKey diagnostic and complete provider/embedding
    compatibility evidence.
  - Acceptance:
    - Missing-key behavior names only `SHOPAIKEY_API_KEY` and exits non-zero; no
      success or failure path prints a key or authorization header.
    - Model discovery verifies both configured IDs. Any equivalent ID is used only
      after explicit user approval and without silently changing configuration.
    - Chat, function calling, tool-result continuation, selected schema validation,
      and ordered streaming all pass with side-effect-free synthetic data.
    - Scalar and at least two-input batch embeddings return one ordered vector per
      input, each containing exactly 1536 finite floats.
    - Success exits `0` and ends with `SHOPAIKEY_COMPATIBILITY=PASS`; every specified
      failure exits non-zero and ends with `SHOPAIKEY_COMPATIBILITY=FAIL` plus the
      failed capability.
  - Validation:
    - Required: `python infrastructure/scripts/diagnose_shopaikey.py` -> exits `0`,
      marks all seven capability groups PASS, reports finite ordered 1536-dimensional
      scalar/batch embeddings, and ends with `SHOPAIKEY_COMPATIBILITY=PASS`.
    - Required: inspect captured stdout/stderr and `git diff --check` -> no API key,
      authorization header, secret value, malformed diff, or unapproved model change
      appears. This is the only normal validation permitted to call the real provider.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` when the key/provider access is
    missing or an equivalent model ID requires approval. Any failed capability,
    unstable ordering, non-finite/wrong-sized vector, or need for another provider,
    model, or dimension blocks Batch04; revise only the affected diagnostic
    adapter/schema path and rerun.
  - Files: `backend/pyproject.toml`,
    `infrastructure/scripts/diagnose_shopaikey.py`,
    `docs/feasibility/phase_0_report.md`

## Mandatory Batch04 - Locked Dependencies and Final Phase 0 Decision

### Goal

Reproduce all gates from a clean local environment, lock successful dependency
facts, and publish the complete PASS decision required for Plan 2.

### Dependencies

(01A), (01B), (02A), and (03A) accepted with their evidence available.

### Scope Boundary

This batch may reconcile Phase 0 manifests and finish the single feasibility report.
It may fix only evidence/locking issues in those artifacts; implementation repair
belongs to the owning earlier task. It does not add Phase 1 application behavior.

### Tasks

- [ ] (04A): Lock the successful stack and finalize every Phase 0 exit gate
  - Source of Truth: `docs/plans/Plan_1.md` > `## 7. Technical Specifications` >
    `### 7.5 Phase report decision record`; `docs/plans/Plan_1.md` >
    `## 8. Implementation Steps`; `docs/plans/Plan_1.md` >
    `## 9. Verification & Testing Plan`; `docs/plans/Plan_1.md` >
    `## 10. Handoff Notes for Plan 2 / Master Phase 1`
  - Source Requirements:
    - Record timestamp/local runtimes and exact intended versions for Astryx,
      FastAPI `>=0.135.0`, LangGraph/LangChain, Pydantic, SQLAlchemy, Neo4j driver,
      pypdf, Trafilatura, httpx, the selected embedding client, and minimum local
      lint/type/test tools.
    - Pin dependencies actually required by Phase 0 in their manifests/lockfiles;
      record later Phase 1 intended versions in the report without installing unused
      Phase 1 application behavior.
    - Reproduce Astryx, pypdf, ShopAIKey, schema, streaming, and embedding evidence
      from a clean local environment. The final report must have no unresolved or
      placeholder entry and may not revise architecture, model IDs, dimensions, or
      MVP scope.
  - Dependencies: (01B) Astryx lock/matrix, (02A) pypdf fixtures/rule/results, and
    (03A) provider diagnostic/schema/results
  - User Action: Keep the valid `SHOPAIKEY_API_KEY` available only through the ignored
    root `.env` for the one live-provider rerun; confirm any provider-equivalent ID
    explicitly before it can be recorded as approved.
  - Agent Work:
    1. Search manifests, scripts, report sections, and all dependency/client callers;
       remove duplicate or unused Phase 0 dependencies and reconcile one exact version
       for each owned package without changing successful behavior.
    2. Complete the report's dependency decision record and verify that every intended
       later dependency version exists, respects the locked stack, and has no
       unresolved compatibility conflict. Keep non-Phase-0 dependencies out of the
       install manifest when the diagnostics do not need them.
    3. Recreate the ignored root Python environment, install from
       `backend/pyproject.toml`, perform a clean npm install, rerun both diagnostics,
       rerun every recorded Astryx documentation command, and rebuild the frontend.
    4. Finish the report with all seven ShopAIKey results and schema strategy, the
       Astryx matrix, all PDF outcomes/threshold, locked versions, and one final gate
       status. Do not claim external setup succeeded without the observed rerun.
    5. Audit tracked files and diffs for secrets, real personal data, runtime data,
       generated volumes, undocumented imports, fallback stacks, placeholders, and
       out-of-scope implementation; append sanitized final evidence to the A1 report.
  - Output: Reproducible Phase 0 manifests/lockfiles and a complete
    `docs/feasibility/phase_0_report.md` that either authoritatively passes every gate
    or blocks Plan 2 with the exact failed gate.
  - Acceptance:
    - The Python manifest and npm lockfile contain exact, minimal, internally
      consistent Phase 0 dependency versions; the report separately names every
      required later-stack version, including FastAPI at least 0.135.0.
    - The report contains timestamp/runtimes, a complete Astryx matrix, all seven
      ShopAIKey capabilities and selected schema strategy, per-fixture pypdf results,
      aggregate threshold, and fixed 1536-dimensional embedding evidence.
    - Every required gate is PASS with matching rerun evidence; there are no
      placeholders, unresolved failures, silent substitutions, or architecture/scope
      changes.
    - `.env`, secrets, authorization headers, real CV data, runtime databases,
      generated volumes, OCR, alternate providers/models, and production JobAgent
      behavior are absent from tracked changes.
    - Plan 2 receives exactly the artifacts named in Plan 1 Section 10 and can begin
      without repeating Phase 0 feasibility work.
  - Validation:
    - Required: `python -m venv --clear .venv; .\.venv\Scripts\python.exe -m pip install --upgrade pip; .\.venv\Scripts\python.exe -m pip install -e .\backend` -> a clean ignored Python environment installs the Phase 0 project successfully.
    - Required: `.\.venv\Scripts\python.exe infrastructure/scripts/verify_pdf_extraction.py` -> exits `0` and ends `PYPDF_COMPATIBILITY=PASS`.
    - Required: `.\.venv\Scripts\python.exe infrastructure/scripts/diagnose_shopaikey.py` -> exits `0` and ends `SHOPAIKEY_COMPATIBILITY=PASS`; this is the one allowed live-provider rerun.
    - Required: `Set-Location frontend; npm ci; npm run build` -> clean frontend install
      and build exit `0` using the pinned Astryx package.
    - Required: rerun every exact Astryx CLI documentation command recorded in the
      report -> all public API/composition evidence remains reproducible.
    - Required: `Set-Location ..; git check-ignore .env; if (git ls-files -- '.env') { throw '.env is tracked' }; git diff --check` -> `.env` is ignored/untracked and the repository diff is clean.
    - Required: `rg -n '(?i)\b(TODO|TBD)\b|<[^>]+>' docs/feasibility/phase_0_report.md` -> returns no matches; A2 also inspects the final report for semantic placeholders and unresolved entries.
  - Blocked Condition: Any required command or evidence gate is not PASS, any exact
    dependency cannot be resolved compatibly, a provider-equivalent ID lacks explicit
    approval, or remediation would require forbidden scope. Identify the owning task,
    record the exact gate failure, and keep Plan 2 blocked until that task is repaired
    and re-reviewed.
  - Files: `backend/pyproject.toml`, `frontend/package.json`,
    `frontend/package-lock.json`, `.env.example`, `.gitignore`,
    `docs/feasibility/phase_0_report.md`
