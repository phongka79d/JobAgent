# Phase 0 Feasibility Report

## Runtime facts

| Fact | Value |
|---|---|
| Report timestamp (local) | 2026-07-13T13:21:54+07:00 |
| Python | 3.13.7 |
| Node.js | v24.11.0 |
| npm | 11.6.1 |
| OS | Windows |
| Frontend package manager | npm (`package-lock.json`) |
| Root Python environment | ignored `.venv` recreated with `python -m venv --clear .venv` |
| Pinned Astryx core | `@astryxdesign/core@0.1.4` |
| Pinned Astryx CLI | `@astryxdesign/cli@0.1.4` |
| Pinned Astryx theme | `@astryxdesign/theme-neutral@0.1.4` |

Lockfile resolution: `frontend/package-lock.json` packages `node_modules/@astryxdesign/core`, `node_modules/@astryxdesign/cli`, and `node_modules/@astryxdesign/theme-neutral` each resolve to **0.1.4**. Clean `npm ci` reproduces this install.

Phase 0 Python pins installed from a clean environment via `pip install -e .\backend`: `pypdf==6.14.2`, `httpx==0.28.1`, `pydantic==2.12.5`.

## Initialization

| Step | Command / action | Result |
|---|---|---|
| Discover CLI | `Set-Location frontend; npx --yes @astryxdesign/cli --help` then local `npx astryx --help` after install | Documentation syntax is `astryx component [name]` (also listed under Commands) |
| Init agent docs | `Set-Location frontend; npx --yes @astryxdesign/cli init --features agents --agent codex` | Installed `frontend/AGENTS.md` with Astryx v0.1.4 agent section |
| Pin packages | Exact versions in `frontend/package.json` + lockfile | `@astryxdesign/core@0.1.4`, `@astryxdesign/cli@0.1.4`, `@astryxdesign/theme-neutral@0.1.4` |
| Minimal render | `frontend/src/main.tsx` public imports only | Production build exit 0; headless DOM confirms all required class roots |
| Clean Batch04 reproduction | `npm ci`; `npm run build`; every recorded `npx astryx component …` command | Install/build exit 0; `ALL_COMPONENT_DOCS=PASS` |

Documentation command syntax recorded from `npx astryx --help`:

```text
component [options] [name]        List components or print component docs
```

Exact per-component documentation commands used for every matrix row (also listed in the matrix Exact CLI documentation command column):

```text
npx astryx component AppShell
npx astryx component ChatLayout
npx astryx component ChatComposer
npx astryx component ChatToolCalls
npx astryx component ChatMessage
npx astryx component ButtonGroup
npx astryx component Card
npx astryx component Collapsible
npx astryx component ProgressBar
```

Optional machine-readable form (same data, append `--json` to any command above), for example: `npx astryx component AppShell --json`.

## Astryx component matrix

All components are **direct** public exports of the same pinned package `@astryxdesign/core@0.1.4`. No alternate design system. No internal package paths. Chat family components share public import `@astryxdesign/core/Chat`.

| Component | Package / version | Exact CLI documentation command | Public import | Required props / callbacks (from CLI docs) | Direct / composed | Status |
|---|---|---|---|---|---|---|
| AppShell | `@astryxdesign/core@0.1.4` | `npx astryx component AppShell` | `import { AppShell } from '@astryxdesign/core/AppShell'` | No required props. Optional slots: `children`, `topNav`, `sideNav`, `mobileNav`, `banner`; layout: `contentPadding`, `height`, `variant`. No required callbacks. | Direct | PASS |
| ChatLayout | `@astryxdesign/core@0.1.4` | `npx astryx component ChatLayout` | `import { ChatLayout } from '@astryxdesign/core/Chat'` | Required: `children` (ReactNode), `composer` (ReactNode). Optional: `emptyState`, `scrollButton`, `scrollRef`. No required callbacks. | Direct | PASS |
| ChatComposer | `@astryxdesign/core@0.1.4` | `npx astryx component ChatComposer` | `import { ChatComposer } from '@astryxdesign/core/Chat'` | Required callback: `onSubmit: (value: string) => void`. Optional callbacks: `onStop`, `onChange`. Optional: empty-input hint string (CLI-documented prop), `value`, `isDisabled`, `status`, etc. | Direct | PASS |
| ChatToolCalls | `@astryxdesign/core@0.1.4` | `npx astryx component ChatToolCalls` | `import { ChatToolCalls } from '@astryxdesign/core/Chat'` | Required: `calls: ChatToolCallItem[]` (`name`, optional `status` of `pending \| running \| complete \| error`, `target`, `duration`, …). Optional callback: `onExpandedChange`. | Direct | PASS |
| ChatMessage | `@astryxdesign/core@0.1.4` | `npx astryx component ChatMessage` | `import { ChatMessage } from '@astryxdesign/core/Chat'` | Required: `sender: 'user' \| 'assistant' \| 'system'`, `children: ReactNode`. Optional: `avatar`, `name`, `metadata`, `density`. No required callbacks. | Direct (children may use documented same-package `ChatMessageBubble` from `@astryxdesign/core/Chat`) | PASS |
| ButtonGroup | `@astryxdesign/core@0.1.4` | `npx astryx component ButtonGroup` | `import { ButtonGroup } from '@astryxdesign/core/ButtonGroup'` | Required: `children` (Button/IconButton), `label` (aria-label string). Optional: `orientation`, `size`, `isDisabled`. No required callbacks. Companion `Button` from `@astryxdesign/core/Button` with required `label`. | Direct | PASS |
| Card | `@astryxdesign/core@0.1.4` | `npx astryx component Card` | `import { Card } from '@astryxdesign/core/Card'` | No required props. Optional: `children`, `padding`, `variant`, size props. No required callbacks. | Direct | PASS |
| Collapsible | `@astryxdesign/core@0.1.4` | `npx astryx component Collapsible` | `import { Collapsible } from '@astryxdesign/core/Collapsible'` | Required: `trigger: ReactNode`. Optional: `children`, `defaultIsOpen`, controlled `isOpen`, callback `onOpenChange: (isOpen: boolean) => void`, group `value`. | Direct | PASS |
| ProgressBar | `@astryxdesign/core@0.1.4` | `npx astryx component ProgressBar` | `import { ProgressBar } from '@astryxdesign/core/ProgressBar'` | Required: `label: string`. Optional: `value`, `max`, `hasValueLabel`, `isIndeterminate`, `variant`, `formatValueLabel`. No required callbacks. | Direct | PASS |

### Same-package composition notes

| Need | Documented composition (same pinned package) |
|---|---|
| Chat shell | `AppShell` → `ChatLayout` with `children={ChatMessageList…}` and `composer={ChatComposer…}` |
| Message body | `ChatMessage` + documented `ChatMessageBubble` children (both from `@astryxdesign/core/Chat`) |
| Tool activity | `ChatToolCalls` inside an assistant `ChatMessage` |
| Approval actions | `ButtonGroup` + `Button` children |
| Score details | `Card` → `Collapsible` → `ProgressBar` |

No component required a cross-package or undocumented composition. Every matrix row CLI command was re-run successfully from the clean Batch04 frontend install (`ALL_COMPONENT_DOCS=PASS`).

## Astryx gate result

| Gate | Result | Evidence |
|---|---|---|
| Stable pin + lockfile | PASS | `@astryxdesign/core@0.1.4` / `@astryxdesign/cli@0.1.4` / `@astryxdesign/theme-neutral@0.1.4` in lockfile; clean `npm ci` exit 0 |
| Public imports only | PASS | `frontend/src/main.tsx` uses only documented `@astryxdesign/core/*` and theme CSS entrypoints |
| Component matrix complete | PASS | All nine required components direct + documented props/callbacks + exact CLI command |
| Minimal build | PASS | Clean Batch04 `npm run build` exit 0 |
| Minimal local render | PASS | Prior Batch01 evidence: `npm run dev -- --host 127.0.0.1` + headless DOM shows `astryx-app-shell`, chat layout/message/tool-calls/composer, card, collapsible, progressbar, button-group; build reconfirmed on clean install |

**ASTRYX_COMPATIBILITY=PASS**

---

## pypdf extraction gate

| Fact | Value |
|---|---|
| Exact pypdf version | `6.14.2` (pinned in `backend/pyproject.toml` as `pypdf==6.14.2`) |
| Diagnostic command | `.\.venv\Scripts\python.exe infrastructure/scripts/verify_pdf_extraction.py` |
| Fixture directory | `backend/tests/fixtures/cv/` |
| Aggregate threshold | At least **4 of 5** digital fixtures must pass the meaningful-text rule |
| Allowed digital failures | **none** (observed **5/5** digital PASS) |
| Image-only expectation | Must be classified `NO_EXTRACTABLE_TEXT` (must not be accepted) |
| OCR | **Never** imported, subprocessed, or called; pypdf digital text only |
| Clean Batch04 rerun | exit `0`, digital_pass=5/5, image-only=`NO_EXTRACTABLE_TEXT`, `PYPDF_COMPATIBILITY=PASS` |

### Meaningful-text rule (owned by `infrastructure/scripts/verify_pdf_extraction.py`)

After whitespace normalization (collapse runs of whitespace, strip), text is **meaningful** when:

1. Non-whitespace character count is **>= 80**, and
2. The lowercased text contains at least one **identity** marker (`email`, `phone`, `@`, `name`), one **experience** marker (`experience`, `engineer`, `developer`, `analyst`, `worked`, `senior`, `staff`, `platform`), and one **skills** marker (`skills`, `python`, `typescript`, `sql`, `react`, `docker`, `fastapi`).

A digital fixture **PASS**es when **either** pypdf normal or layout extraction yields meaningful text. Text that fails the rule is treated as non-extractable. The image-only fixture must fail the rule in both modes and is reported as `NO_EXTRACTABLE_TEXT`. No OCR fallback is permitted.

### Per-fixture outcomes

Measurements: page count; non-whitespace character count after whitespace-only normalization for **normal** and **layout** extraction modes.

| Fixture | Kind | Pages | Normal non-ws | Layout non-ws | Normal meaningful | Layout meaningful | Result |
|---|---|---:|---:|---:|---|---|---|
| `digital_cv_01.pdf` | digital (classic single-column) | 1 | 421 | 421 | yes | yes | PASS |
| `digital_cv_02.pdf` | digital (data/product hybrid) | 1 | 422 | 422 | yes | yes | PASS |
| `digital_cv_03.pdf` | digital (split header / compact body) | 1 | 330 | 330 | yes | yes | PASS |
| `digital_cv_04.pdf` | digital (multi-role bullets) | 1 | 534 | 534 | yes | yes | PASS |
| `digital_cv_05.pdf` | digital (skills-first) | 1 | 340 | 340 | yes | yes | PASS |
| `image_only_cv.pdf` | image-only (full-page RGB JPEG XObject 1240×1754, no text layer) | 1 | 0 | 0 | no | no | `NO_EXTRACTABLE_TEXT` |

All five digital fixtures use synthetic identities only (no real personal data). The image-only fixture is a single letter-size page (`MediaBox [0 0 612 792]`) whose content stream only paints `/Im0 Do` (no `BT`/`Tj`/`TJ` text operators). The embedded DeviceRGB JPEG is a **visibly representative synthetic CV page** (1240×1754 px at generation time): dark header with synthetic name/contact, SUMMARY / EXPERIENCE / SKILLS / EDUCATION sections drawn as pixels only (`Jordan SampleCandidate`, invented job titles and skill labels used only as raster art). pypdf extracts empty text in both modes. No real personal data; no OCR path.

### Aggregate and gate result

| Metric | Value |
|---|---|
| Digital successes | **5/5** (threshold >= 4/5) |
| Allowed digital failure named | none |
| Image-only | `NO_EXTRACTABLE_TEXT` (rejected as required) |
| Diagnostic exit code | `0` |
| Final marker | `PYPDF_COMPATIBILITY=PASS` |

**PYPDF_COMPATIBILITY=PASS**

---

## ShopAIKey chat and embedding gate

| Fact | Value |
|---|---|
| Diagnostic command | `.\.venv\Scripts\python.exe infrastructure/scripts/diagnose_shopaikey.py` |
| Module layout | thin entrypoint + `infrastructure/scripts/shopaikey_diag/` (`common`, `chat_checks`, `tools_schema`, `schema_checks`, `streaming`, `embeddings`, `runner`) |
| HTTP client | `httpx==0.28.1` (pinned in `backend/pyproject.toml`) |
| Schema validation | `pydantic==2.12.5` (pinned in `backend/pyproject.toml`) |
| Provider base host | `api.shopaikey.com` (from `SHOPAIKEY_BASE_URL`; secret path omitted) |
| Requested chat model | `gpt-4o-mini` |
| Observed chat model | `gpt-4o-mini` |
| Requested embedding model | `text-embedding-3-small` |
| Observed embedding model | `text-embedding-3-small` (scalar and batch) |
| Requested embedding dimensions | `1536` |
| Encoding | `float` |
| Silent model/dimension substitution | **none** (locked IDs enforced; no equivalent ID used) |
| Selected production schema strategy | **`strict_json_schema`** (`response_format.type=json_schema` with `strict=true`; validated with Pydantic `SyntheticCard`) |
| Alternate strategies probed only if strict fails | ordinary function schema + Pydantic; JSON mode + Pydantic with at most one repair |
| Clean Batch04 live rerun | one allowed live-provider run; exit `0`; **7/7** capabilities PASS; `SHOPAIKEY_COMPATIBILITY=PASS` |

### Configuration load contract

The diagnostic loads only `SHOPAIKEY_BASE_URL`, `SHOPAIKEY_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS` through a minimal root `.env` + process-environment loader. Missing or invalid configuration is routed through the common failure formatter: names `SHOPAIKEY_API_KEY` without its value, prints `failed_capability=config`, exits non-zero, and ends with `SHOPAIKEY_COMPATIBILITY=FAIL`. No success or failure path prints the key, an `Authorization` header, or full secret configuration.

### Seven capability results

| Capability | Status | Evidence (sanitized) |
|---|---|---|
| model_discovery | PASS | `/v1/models` listed both `gpt-4o-mini` and `text-embedding-3-small` |
| basic_chat | PASS | Chat completion via `gpt-4o-mini`; non-empty assistant content (`content_len=4`) |
| function_calling | PASS | Forced `synthetic_add` tool call; validated args `a=17`, `b=25` |
| tool_result_round_trip | PASS | Tool result `sum=42` continued to non-empty final assistant text containing `42` |
| structured_schema | PASS | Strict JSON schema returned `label=alpha`, `value=7`; strategy=`strict_json_schema` |
| ordered_text_streaming | PASS | Sequential non-empty deltas normalize to exactly `1 2 3 4 5`; `finish_reason=stop`; terminal `[DONE]` observed (`delta_count=9`, `done=yes`, `ordered=yes`) |
| scalar_batch_embeddings | PASS | Scalar 1×1536 finite floats; batch 2 distinct inputs → 2 list-order-validated 1536-d finite vectors (`index` checked without sorting) |

### Streaming assertion contract

Ordered streaming requires: (1) joined non-empty content deltas normalize to exactly `1 2 3 4 5`; (2) a non-empty finish reason; (3) terminal `[DONE]`. Malformed JSON payloads and invalid chunk shapes fail with `MALFORMED_RESPONSE` / `STREAM_FAIL` rather than being skipped. Local fake streams for arbitrary content, malformed JSON, reversed/missing sequence, missing finish reason, and missing `[DONE]` all fail; a valid multi-delta stream with finish reason plus `[DONE]` passes.

### Embedding contract evidence

| Check | Result |
|---|---|
| Scalar input | 1 output vector |
| Batch inputs | 2 distinct strings → 2 vectors |
| Dimensions | exactly **1536** per vector (scalar and batch) |
| Finiteness | all values `math.isfinite` |
| Ordering | response items validated in **returned list order** against expected indices (no pre-sort); reversed `[index=1, index=0]` raises `ORDERING_MISMATCH`; batch vectors not identical |
| Encoding | `encoding_format=float` |

### Error normalization (implemented)

Timeout, HTTP 429 rate-limit, malformed JSON/shape, model absence, dimension mismatch, and ordering mismatch map to concise non-zero codes (`TIMEOUT`, `RATE_LIMIT`, `MALFORMED_RESPONSE`, `MODEL_ABSENCE`, `DIMENSION_MISMATCH`, `ORDERING_MISMATCH`, plus capability-specific `SCHEMA_FAIL` / `STREAM_FAIL` / `TOOL_FAIL` / `HTTP_ERROR` / `MISSING_KEY`). Failures print `failed_capability` set to the capability identifier and end with `SHOPAIKEY_COMPATIBILITY=FAIL`. Exception paths redact any accidental secret substring before printing.

### Gate result

| Metric | Value |
|---|---|
| Capability PASS count | **7/7** |
| Diagnostic exit code | `0` |
| Final marker | `SHOPAIKEY_COMPATIBILITY=PASS` |
| Live provider calls (Batch04 final) | exactly one successful full diagnostic run from the clean `.venv` |

**SHOPAIKEY_COMPATIBILITY=PASS**

---

## Dependency decision record

Phase 0 installs **only** packages required by feasibility diagnostics and the minimal Astryx frontend. Phase 1 application packages are recorded here with exact intended versions that exist on the public registries and respect the locked Master stack. They are **not** installed by Phase 0 manifests.

### Phase 0 installed pins (manifests / lockfiles)

| Package | Exact version | Manifest | Proven by |
|---|---|---|---|
| `@astryxdesign/core` | `0.1.4` | `frontend/package.json` + lockfile | Astryx matrix + clean build |
| `@astryxdesign/cli` | `0.1.4` | `frontend/package.json` + lockfile | CLI docs commands |
| `@astryxdesign/theme-neutral` | `0.1.4` | `frontend/package.json` + lockfile | theme CSS entry + build |
| `react` | `19.2.7` | `frontend/package.json` + lockfile | minimal render build |
| `react-dom` | `19.2.7` | `frontend/package.json` + lockfile | minimal render build |
| `vite` | `6.4.3` | `frontend/package.json` + lockfile | `npm run build` |
| `typescript` | `5.9.3` | `frontend/package.json` + lockfile | build toolchain |
| `@vitejs/plugin-react` | `4.7.0` | `frontend/package.json` + lockfile | build toolchain |
| `@types/react` | `19.2.17` | `frontend/package.json` + lockfile | types only |
| `@types/react-dom` | `19.2.3` | `frontend/package.json` + lockfile | types only |
| `pypdf` | `6.14.2` | `backend/pyproject.toml` | PDF gate clean rerun |
| `httpx` | `0.28.1` | `backend/pyproject.toml` | ShopAIKey diagnostic HTTP client |
| `pydantic` | `2.12.5` | `backend/pyproject.toml` | schema/tool argument validation |

No duplicate or unused Phase 0 application dependencies remain. Diagnostic modules import only `httpx`, `pydantic`, and the standard library plus `pypdf` in the PDF script.

### Phase 1 intended versions (not installed in Phase 0)

Verified present on PyPI at report time. Compatible with proven Phase 0 pins where shared (`pydantic==2.12.5`, `httpx==0.28.1`, `pypdf==6.14.2`).

| Package | Intended version | Role | Notes |
|---|---|---|---|
| `fastapi` | `0.139.0` | Backend API / native SSE | Meets Master minimum `>=0.135.0` for native SSE; requires `pydantic>=2.9.0` (satisfied by `2.12.5`) |
| `uvicorn` | `0.51.0` | ASGI server | Companion to FastAPI local/runtime serving |
| `langgraph` | `1.2.9` | Agent orchestration | Master: single controlled tool loop with interrupt/resume |
| `langchain` | `1.3.13` | LangChain integration surface | Paired with LangGraph / OpenAI-compatible adapters |
| `langchain-core` | `1.4.9` | Shared LangChain primitives | Transitive/core pin aligned with langchain 1.3.x |
| `langchain-openai` | `1.3.5` | Production `ChatOpenAI` + embedding client | OpenAI-compatible ShopAIKey base URL/key; Phase 0 proved the HTTP contract via `httpx` |
| `pydantic` | `2.12.5` | Validation contracts | Same proven Phase 0 pin |
| `sqlalchemy` | `2.0.51` | SQLAlchemy 2 async ORM | Master: SQLite source of truth |
| `aiosqlite` | `0.22.1` | Async SQLite driver | Companion to SQLAlchemy 2 async |
| `alembic` | `1.18.5` | Migrations | Master: owns application tables |
| `neo4j` | `6.2.0` | Official Neo4j Python driver | Graph/vector store client |
| `pypdf` | `6.14.2` | PDF text extraction baseline | Same proven Phase 0 pin |
| `trafilatura` | `2.1.0` | Public HTML main-text extraction | Master web extraction baseline; not required by Phase 0 diagnostics |
| `httpx` | `0.28.1` | HTTP client | Same proven Phase 0 pin for URL fetch and provider checks |
| Embedding client (production) | `langchain-openai==1.3.5` | Hosted embeddings via ShopAIKey | Request shape locked: model `text-embedding-3-small`, `encoding_format=float`, dimensions **1536**, preserve input order |
| Embedding client (diagnostic proven) | `httpx==0.28.1` | Phase 0 direct OpenAI-compatible HTTP | Evidence retained for adapter implementation |
| `ruff` | `0.15.21` | Local lint | Minimum local lint tool for later phases |
| `mypy` | `1.18.2` | Local type checking | Minimum local type tool for later phases |
| `pytest` | `9.1.1` | Local tests | Minimum local test tool for later phases |

Compatibility notes:

- No unresolved registry resolution failures for the intended versions above.
- No alternate provider, model ID, embedding dimension, OCR stack, or design system is approved.
- Locked models remain `gpt-4o-mini` and `text-embedding-3-small` at **1536** dimensions.
- Production schema strategy remains **`strict_json_schema`** as proven by the ShopAIKey gate.

---

## Final Phase 0 gate status

| Gate | Status | Matching clean-environment evidence |
|---|---|---|
| Scaffold + root env contract | PASS | Prior Batch01; `.env.example` Master Section 23 names; root `.env` ignored and untracked |
| Astryx pin + public component matrix | PASS | Clean `npm ci` / `npm run build`; nine CLI docs commands `ALL_COMPONENT_DOCS=PASS` |
| pypdf synthetic extraction | PASS | Clean venv diagnostic exit 0; 5/5 digital; image-only `NO_EXTRACTABLE_TEXT`; `PYPDF_COMPATIBILITY=PASS` |
| ShopAIKey seven capabilities + schema | PASS | One live diagnostic from clean venv; 7/7; strategy `strict_json_schema`; `SHOPAIKEY_COMPATIBILITY=PASS` |
| Embeddings 1536 finite ordered | PASS | Scalar + batch 1536 finite floats; list-order validation |
| Dependency lock + decision record | PASS | Phase 0 exact pins only in manifests; Phase 1 intended versions recorded and registry-verified |
| Secrets / scope hygiene | PASS | No tracked `.env`; no keys or auth headers in diffs; no real CV data, OCR, alternate providers, or production JobAgent behavior |

**PHASE_0_OVERALL=PASS**

Plan 2 may begin using exactly the handoff artifacts named in Plan 1 Section 10: three-folder scaffold and committed manifests/lockfiles; this report with all gates PASS; pinned Astryx version and public component API/composition notes; verified schema/tool/streaming mode and embedding request shape; reusable ShopAIKey diagnostic and synthetic PDF fixtures; documented pypdf meaningful-text rule and `NO_EXTRACTABLE_TEXT` evidence. Plan 2 must not repeat Phase 0 feasibility work, change locked models or 1536 dimensions, or broaden fallback stacks.
