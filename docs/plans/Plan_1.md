# Plan 1 — Master Phase 0: Feasibility and Compatibility Gates

> **Numbering:** `Plan_1.md` implements **Master Plan Phase 0**. Generated plan files are 1-based; Master Plan phase identities remain unchanged.

## Objective

Create the minimal repository scaffold and retire the four uncertainties that could invalidate later implementation: Astryx component availability, ShopAIKey chat/tool/schema/streaming/embedding compatibility, pypdf extraction quality, and image-only PDF rejection. This phase produces evidence and locked dependency versions; it does not build production JobAgent flows.

The phase is complete only when every Master Phase 0 exit gate passes. If a gate fails, revise only the affected adapter or documented composition path and rerun that gate. Do not add fallback providers, OCR, alternate embedding models, or another design system.

## Source of Truth

- `docs/plans/Master_plan.md` Sections 1–5: objective, scope guardrail, locked stack, ownership rules, and repository shape.
- Sections 10.1–10.2: PDF validation, pypdf layout extraction, representative digital fixtures, and `NO_EXTRACTABLE_TEXT` without OCR.
- Section 15.3: required Astryx components and the requirement to inspect pinned-package CLI documentation before implementation.
- Sections 16.1–16.2 and 17.1–17.2: ShopAIKey chat, tool, structured-output, streaming, and 1536-dimensional embedding compatibility contract.
- Sections 22–24: local safeguards, one-root-environment rule, synthetic fixtures, and local-only testing.
- Section 25, “Phase 0 — Feasibility and compatibility gates”: tasks and exit gate.
- Sections 27–29: MVP exclusions and the rule that failed feasibility changes the affected adapter rather than expanding the stack.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| Legacy Plan 1 scope | Master Phase 0: Feasibility and Compatibility Gates | Preserve the historical phase scope and outputs below. | Existing Verification section and accepted evidence. |

## Prerequisites

- [ ] No implementation-phase artifacts are required.
- [ ] Python, Node.js/npm, Docker, and Git are available locally.
- [ ] The developer supplies `SHOPAIKEY_API_KEY` only through the ignored root `.env`; the value is never copied into committed files or command output.
- [ ] Six synthetic PDF fixtures can be committed: five digitally born representative CVs and one image-only PDF. They must contain no real personal data.

## Scope

- Create the `frontend/`, `backend/`, and `infrastructure/` scaffold without implementing application behavior.
- Create root configuration documentation through `.env.example`; preserve the existing ignored `.env` as user-managed runtime state.
- Pin a stable Astryx version and run the required initialization command.
- Inspect and record the public composition/API path for `AppShell`, `ChatLayout`, `ChatComposer`, `ChatToolCalls`, `ChatMessage`, `ButtonGroup`, `Card`, `Collapsible`, and `ProgressBar`.
- Build one reusable ShopAIKey diagnostic covering model discovery, chat completion, function calling, tool-result round trip, structured schema behavior, text streaming, scalar embeddings, and batch embeddings.
- Verify `gpt-4o-mini` and `text-embedding-3-small` through the configured ShopAIKey base URL without silently substituting models.
- Verify exactly 1536 finite floats per embedding and stable batch ordering.
- Verify pypdf normal and layout extraction against five representative digital CV fixtures.
- Verify image-only input produces `NO_EXTRACTABLE_TEXT` and does not trigger OCR.
- Record the selected structured-output strategy and exact dependency versions for later phases.

## Out of Scope

- FastAPI endpoints, SQLAlchemy models, Alembic migrations, Docker runtime services, or Neo4j persistence.
- Production chat orchestration, SSE, LangGraph checkpoints, or durable tool execution.
- CV upload/storage, Candidate Profile schemas, profile approval, or graph synchronization.
- JD extraction, job embeddings, matching, ranking, or UI cards.
- OCR, browser automation, alternate providers/models, local embeddings, reranking, Qdrant, or broad fallback stacks.
- Real CV/JD data, public deployment, authentication, CI, or production security work.

## Target Directory Structure

```text
JobAgent/
├── .env                         # existing ignored local secrets; never generated from committed values
├── .env.example                 # names and safe placeholders only
├── .gitignore                   # confirm secrets, runtime data, and generated files remain ignored
├── backend/
│   ├── app/
│   │   └── __init__.py
│   ├── tests/
│   │   └── fixtures/
│   │       └── cv/
│   │           ├── digital_cv_01.pdf
│   │           ├── digital_cv_02.pdf
│   │           ├── digital_cv_03.pdf
│   │           ├── digital_cv_04.pdf
│   │           ├── digital_cv_05.pdf
│   │           └── image_only_cv.pdf
│   └── pyproject.toml           # only dependencies needed by the feasibility scripts, pinned after checks
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   └── src/
│       └── main.tsx             # Astryx initializer output/minimal render only
├── infrastructure/
│   ├── docker/
│   ├── neo4j/
│   └── scripts/
│       ├── diagnose_shopaikey.py
│       └── verify_pdf_extraction.py
└── docs/
    └── feasibility/
        └── phase_0_report.md
```

Do not add empty placeholder modules outside this tree. Later phases create directories when they first own real behavior.

## Technical Specifications

### 7.1 Scaffold and dependency lock

- Run `npx astryx init --features agents --agent codex` in `frontend/` and commit both `package.json` and `package-lock.json`.
- Resolve the exact Astryx version from the lockfile. Record it in `docs/feasibility/phase_0_report.md`; later phases must use that version and its observed public APIs.
- `backend/pyproject.toml` may contain only the minimum Phase 0 runtime/dev dependencies needed for ShopAIKey HTTP checks, Pydantic validation, pypdf extraction, and local tests. Exact versions are locked after the checks succeed.
- `.env.example` must expose the Master Section 23 variable names with empty secrets. It must not be loaded as runtime configuration and must not contain a real key.

### 7.2 ShopAIKey diagnostic contract

`infrastructure/scripts/diagnose_shopaikey.py` is a reusable local diagnostic, not a production adapter. It must:

1. Read `SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS` from the process environment/root `.env` through the chosen minimal settings loader.
2. Fail fast when the API key is absent, while printing only the missing variable name.
3. Call `/v1/models` and verify the configured chat and embedding model IDs, or record an explicitly approved provider-equivalent ID without changing configuration silently.
4. Obtain a basic chat completion from `gpt-4o-mini`.
5. Bind one synthetic, side-effect-free function and prove a tool call can be received, validated, answered with a tool result, and followed by a final assistant response.
6. Exercise the provider’s structured schema behavior. Prefer the verified strict mode only if it passes; otherwise record ordinary function schema or JSON mode plus Pydantic validation and one repair as the production strategy.
7. Verify streamed text contains ordered, non-empty deltas and a normal terminal response.
8. Request one scalar embedding and one ordered batch of at least two distinct inputs using `text-embedding-3-small`, `dimensions=1536`, and float encoding.
9. Assert one output per input, stable index ordering, exactly 1536 values per vector, and `math.isfinite` for every value.
10. Convert timeout, rate-limit, malformed response, model absence, dimension mismatch, and ordering mismatch into a non-zero exit with a concise code. Never print request authorization headers or keys.

Successful output must be a short capability table followed by `SHOPAIKEY_COMPATIBILITY=PASS`. A failure must end with `SHOPAIKEY_COMPATIBILITY=FAIL` and the failed capability.

### 7.3 PDF feasibility contract

`infrastructure/scripts/verify_pdf_extraction.py` must:

- Iterate the six committed synthetic fixtures from `backend/tests/fixtures/cv/`.
- For each digital PDF, run pypdf normal extraction and layout extraction, normalize whitespace only for measurement, and report page count plus non-whitespace character count.
- Define “success” as meaningful identity/experience/skills text being present in at least four of the five digital fixtures. The report must name the one allowed failure if present.
- Classify the image-only fixture as `NO_EXTRACTABLE_TEXT` using the same documented minimum-text/quality rule intended for the production parser.
- Return non-zero if fewer than four digital fixtures succeed or if the image-only fixture is accepted.
- Never introduce or call OCR.

Successful output ends with `PYPDF_COMPATIBILITY=PASS`.

### 7.4 Astryx evidence contract

The feasibility report must capture, for each required component:

- Exact installed package/version.
- Exact CLI documentation command used against that pinned version.
- Public import path.
- Required props and event/callback names needed by the Master UX.
- Whether it exists directly or requires composition from documented public components.

Undocumented props and internal package paths are forbidden. A missing component is acceptable only when the report provides a documented composition path using the same pinned Astryx package.

### 7.5 Phase report decision record

`docs/feasibility/phase_0_report.md` must contain:

- Timestamp and local runtime versions.
- Locked Astryx, FastAPI (at least `0.135.0` for native SSE), LangGraph/LangChain, Pydantic, SQLAlchemy, Neo4j-driver, pypdf, Trafilatura, httpx, embedding-client, and minimal local lint/type/test tool versions intended for Phase 1 installation.
- ShopAIKey results for all seven capabilities and the exact selected schema strategy.
- Astryx component matrix.
- Per-fixture pypdf outcome and aggregate threshold.
- Final gate status with no unresolved or placeholder entries.

This report locks compatibility facts; it may not revise the Master’s architecture, model IDs, embedding dimensions, or MVP scope.

## Implementation

- [ ] Create only the scaffold directories and minimal package manifests listed in Section 6.
- [ ] Extend `.gitignore` only as needed to keep `.env`, uploaded/runtime data, caches, build output, and local Neo4j/SQLite volumes out of Git.
- [ ] Create `.env.example` from Master Section 23 using safe empty placeholders.
- [ ] Initialize Astryx with the required command, lock its stable version, and verify the minimal frontend renders.
- [ ] Run the pinned Astryx CLI documentation command for every required component and record its public API/composition result.
- [ ] Add the six synthetic PDF fixtures with no real personal data.
- [ ] Implement the PDF feasibility script and run both normal and layout extraction.
- [ ] Implement the ShopAIKey diagnostic with side-effect-free synthetic tool/schema cases.
- [ ] Run scalar and batch embedding checks and assert dimensions, finiteness, count, and order.
- [ ] Pin the successful dependency versions in package manifests/lockfiles.
- [ ] Complete `docs/feasibility/phase_0_report.md` with evidence and the selected schema mode.
- [ ] Rerun every gate from a clean local environment and stop if any required result is not PASS.

## Verification

### Automated/local commands

```powershell
python infrastructure/scripts/verify_pdf_extraction.py
```

Expected: exit `0`, at least `4/5` digital fixtures accepted, image-only fixture rejected with `NO_EXTRACTABLE_TEXT`, and final line `PYPDF_COMPATIBILITY=PASS`.

```powershell
python infrastructure/scripts/diagnose_shopaikey.py
```

Expected: exit `0`, each capability marked PASS, scalar/batch vectors reported as 1536-dimensional finite values in input order, and final line `SHOPAIKEY_COMPATIBILITY=PASS`. This is the only normal check allowed to call the real provider.

```powershell
Set-Location frontend
npm ci
npm run build
```

Expected: clean install from `package-lock.json` and successful minimal Astryx build using only documented imports.

Run the exact pinned Astryx CLI documentation command recorded in the feasibility report for each required component. Expected: each component has a public API or documented composition path.

### Manual verification

- Inspect `git diff --check` and tracked files; no `.env`, API key, real CV, runtime database, or generated volume data appears.
- Confirm diagnostic logs do not contain the API key or authorization header.
- Open the minimal frontend and confirm Astryx initializes without an undocumented import or runtime error.
- Review the phase report for placeholders, unexplained failures, or unapproved model substitutions.

### Failure handling

- A failed ShopAIKey capability blocks Plan 2. Adjust only the relevant adapter/schema mode and rerun.
- A missing Astryx component blocks Plan 2 until a documented same-library composition path is recorded.
- Fewer than four successful digital fixtures blocks Plan 2; do not add OCR or another parser stack.
- Any embedding model/dimension mismatch blocks Plan 2; do not change the locked model or `1536` dimensions.

## Handoff Contract

### Consumes
- docs/plans/Master_plan.md and the prior plan outputs named in Prerequisites.

### Produces
- The completed Master Phase 0: Feasibility and Compatibility Gates artifacts, scope decisions, and verification evidence preserved below.

### Next Consumer
Plan_2.md consumes the produced artifacts and must not reimplement this phase's owned work.

### Historical Handoff Notes

Plan 2 may consume only these Phase 0 outputs:

- The three-folder scaffold and committed dependency manifests/lockfiles.
- `docs/feasibility/phase_0_report.md` with all gates PASS.
- The pinned Astryx version and exact public component composition/API notes.
- The verified `ChatOpenAI` schema/tool/streaming mode and embedding request shape.
- The reusable ShopAIKey diagnostic and synthetic PDF fixtures.
- The documented pypdf meaningful-text rejection rule and `NO_EXTRACTABLE_TEXT` evidence.

Plan 2 must not repeat provider/UI/parser feasibility work, change the locked model or embedding dimensions, or broaden fallback stacks. It may configure production adapters only according to the recorded compatibility results. If any Phase 0 gate is not PASS, Plan 2 must not start.
