# Plan 1 - Master Phase 0: Feasibility and Compatibility Gates

## 1. Objective

Remove the material provider, UI-library, PDF-parsing, and embedding uncertainties before production implementation begins. This plan produces evidence and locked compatibility decisions; it does not build product behavior.

## 2. Source of Truth

- `Master_plan.md` section 3, **Locked Technology Stack**.
- Section 5, **Repository Structure**.
- Section 15, **Frontend UX Plan**.
- Section 16, **ShopAIKey Integration**.
- Section 17, **Embedding and Retrieval**.
- Section 19, **Evaluation Plan**.
- Sections 22-24, **Security and Privacy**, **Environment Configuration**, and **Local Testing Strategy**.
- Section 25, **Phase 0 - Feasibility and compatibility gates**.

If this plan conflicts with `Master_plan.md`, the master plan wins.

## 3. Prerequisites from Prior Phases

- [ ] No prior implementation phase is required.
- [ ] Python, Node.js/npm, and Docker with Compose are available locally.
- [ ] A local, gitignored ShopAIKey API key is available for the compatibility smoke test.
- [ ] Five to ten representative, digitally born PDF CV fixtures are available locally; real data is redacted and gitignored.
- [ ] An initial labeled retrieval subset exists for comparing the two locked embedding candidates.

## 4. Scope

- Create the three top-level working folders: `frontend`, `backend`, and `infrastructure`.
- Create root configuration placeholders without implementing production services.
- Pin one stable Astryx version and run its required initialization command.
- Verify the documented composition path for every required Astryx component.
- Implement a temporary ShopAIKey diagnostic covering model listing, chat completion, function calling, tool-result round trip, structured schema behavior, and streaming text.
- Benchmark pypdf normal and layout extraction, including an image-only fixture.
- Benchmark `intfloat/multilingual-e5-small` against `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` on quality, CPU latency, and memory.
- Record evidence and pass/fail decisions in `backend/evaluation/reports/phase_0_feasibility.md`.

## 5. Out of Scope

- Production FastAPI endpoints, LangGraph runtime, or frontend product flows.
- SQLite models, Alembic migrations, Neo4j schema, or graph synchronization.
- CV/JD production ingestion and extraction services.
- Matching, score tuning, or held-out ranking evaluation.
- OCR, browser automation, fallback LLM providers, BGE-M3, Qdrant, CI, or cloud deployment.
- Broad fallback stacks when a gate fails; only the affected adapter may be revised.

## 6. Target Directory Structure

```text
JobAgent/
|-- frontend/
|   |-- package.json
|   `-- src/
|-- backend/
|   |-- app/
|   |-- evaluation/
|   |   |-- fixtures/
|   |   `-- reports/
|   |       `-- phase_0_feasibility.md
|   |-- scripts/
|   |   `-- check_shopaikey_compatibility.py
|   `-- pyproject.toml
|-- infrastructure/
|   |-- docker/
|   |-- neo4j/
|   `-- scripts/
|-- .env.example
|-- .gitignore
`-- README.md
```

The scaffold must retain exactly the three working folders declared by the master plan.

## 7. Technical Specifications

### 7.1 ShopAIKey compatibility matrix

The temporary diagnostic must record one result for each capability:

| Capability | Required evidence | Gate |
|---|---|---|
| Model discovery | Requested model ID returned or an explicitly approved equivalent recorded | Pass required |
| Basic completion | Non-empty assistant response | Pass required |
| Function call | Valid tool name and JSON arguments | Pass required |
| Tool round trip | Final response after a supplied tool result | Pass required |
| Structured schema | Output validates against a local Pydantic v2 model | One reliable mode required |
| Streaming | Ordered text chunks or a documented unsupported result | Must be known before Phase 2 |

The script reads `SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`, and `LLM_MODEL` from the root environment. It must never print the API key, Authorization header, raw CV/JD content, or provider headers. It may test ordinary function schemas or JSON mode when `strict=True` is incompatible and may perform at most one schema-repair request.

### 7.2 Astryx component matrix

For the pinned Astryx package, record the public import and documented composition path for `AppShell`, `ChatLayout`, `ChatComposer`, `ChatToolCalls`, `ChatMessage`, `ButtonGroup`, `Button`, `Card`, `Collapsible`, and `ProgressBar`. Missing components must have a documented composition using public APIs; undocumented internals are prohibited.

### 7.3 PDF benchmark record

For each fixture record fixture ID, page count, parser mode, extracted character count, elapsed milliseconds, and outcome. The image-only fixture must produce `NO_EXTRACTABLE_TEXT`; OCR must not be introduced.

### 7.4 Embedding benchmark record

Compare only the two locked candidate models. Record model ID, vector dimension, validation `nDCG@10`, Recall@10, median/P95 CPU encoding latency, and peak memory. Select one model before Phase 1. Prefer E5 unless MiniLM provides a meaningful measured advantage.

### 7.5 Feasibility report decision block

The report must end with a decision table containing `Gate`, `Result`, `Evidence`, `Selected mode/version`, and `Phase impact`. Every required gate must be `PASS` before Phase 1 starts.

## 8. Implementation Steps

- [ ] Create the three-folder scaffold and minimal root placeholders.
- [ ] Add gitignore rules for root `.env`, runtime files, real CV/JD data, and private evaluation data.
- [ ] Pin Astryx, run `npx astryx init --features agents --agent codex`, and capture the package version.
- [ ] Run the pinned Astryx CLI documentation command for each required component and fill the component matrix.
- [ ] Add the isolated ShopAIKey diagnostic and execute all six compatibility checks.
- [ ] Create synthetic and local-private PDF fixture manifests; do not commit real content.
- [ ] Run pypdf normal/layout benchmarks and verify the image-only failure code.
- [ ] Run the two-model embedding benchmark on the same seeded retrieval subset.
- [ ] Write the feasibility report, lock the provider schema mode, Astryx composition, parser mode, embedding model, dimension, and pinned versions.
- [ ] Remove any temporary dependency or scaffold artifact not required by a locked gate.

## 9. Verification & Testing Plan

Automated/local commands must be single-purpose and documented in the Phase 0 report. At minimum verify:

- The ShopAIKey diagnostic exits non-zero when a required tool-call or schema gate fails.
- The diagnostic output contains no configured secret value.
- The PDF benchmark classifies the image-only fixture as `NO_EXTRACTABLE_TEXT`.
- Both embedding candidates run against the same seeded split and emit comparable metrics.
- `npm` resolves the pinned Astryx package and its required public APIs.
- The repository root contains no fourth working folder and no committed `.env` or private fixture.

Expected final evidence is a complete `phase_0_feasibility.md` with all required gates marked `PASS`. If a gate fails, stop before Plan 2 and revise only that adapter decision in the master plan or feasibility implementation.

## 10. Handoff Notes for Plan 2 (Master Phase 1)

Plan 2 receives:

- Exact pinned Python, frontend, FastAPI, Astryx, LangGraph, Neo4j-driver, and evaluation dependency decisions.
- Verified ShopAIKey model ID, tool-call mode, structured-output mode, and streaming capability.
- Verified Astryx public component/import matrix.
- Selected PDF extraction mode and `NO_EXTRACTABLE_TEXT` rule.
- Selected embedding model and vector dimension.
- The three-folder scaffold and root configuration placeholders.

Plan 2 must consume these decisions without repeating the benchmarks or adding alternate provider/UI/parser/embedding stacks. Any failed gate blocks Plan 2.
