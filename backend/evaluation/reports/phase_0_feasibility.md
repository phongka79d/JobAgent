# Phase 0 Feasibility Report

This report is the single evidence destination for Phase 0 compatibility gates. Private document paths, document text, labels, credentials, authorization headers, and provider headers must not be recorded here.

## Prerequisites

Sanitized readiness transferred from task 01A:

| Prerequisite | Status | Evidence | Remaining action |
|---|---|---|---|
| Python | READY | Python 3.13.7 version check passed | None |
| Node.js | READY | Node.js v24.11.0 version check passed | None |
| npm | READY | npm 11.6.1 version check passed | None |
| Docker Compose | READY | Docker Compose v5.1.1 version check passed | None |
| Local ShopAIKey setting | READY | Ignored root environment exists with a non-empty setting; value was not recorded | Authorize live use and approve structured-schema criterion before the live gate |
| Digital PDF corpus | READY | Five digital fixtures frozen under ignored private path with generic IDs; 04C digital comparison complete; 04D reconfirmed selected `layout` still meets 4/5 | Digital mode `layout` locked; PDF gate closed in 04D |
| Image-only PDF fixture | READY | One image-only fixture frozen as `pdf_image_only_001`; dual-mode exact `NO_EXTRACTABLE_TEXT` verified in 04D (normal + layout, repeated runs) | Exact dual-mode rule closed PASS in 04D |
| Labeled retrieval subset | MISSING_OR_UNDECLARED | No declared manifest or location was available | Confirm provenance, fixed split, seed, record count, and decision criteria |
| PDF decision criterion | READY | Pre-benchmark rule recorded: at least 4 of 5 digital fixtures must yield extractable text; image-only must be `NO_EXTRACTABLE_TEXT` | Criterion unchanged after 04C measurement; do not revise post-hoc |
| Embedding decision criteria | BLOCKED_BY_USER_ACTION | No approved numeric embedding criteria were available | Record embedding criteria before measuring Batch05 |
| Committed manifest metadata | CONFIRMED | Generic non-identifying identifiers and metadata were approved | Keep real names, paths, text, and personal data in ignored local files |

## Astryx

| Evidence item | Result | Evidence | Locked decision |
|---|---|---|---|
| Pinned package version | PASS | Official npm registry `latest` metadata queried 2026-07-11 resolves both `@astryxdesign/core` and `@astryxdesign/cli` to stable `0.1.4`; `npm ls` and lockfile resolution confirm both exact pins | Use Astryx core and CLI `0.1.4` |
| Agent initializer | PASS | `npx astryx init --features agents --agent codex` completed from `frontend/`; CLI reported `0.1.4` and generated only `frontend/AGENTS.md` | Retain generated compatibility guidance; no demo or product scaffold |
| Public component imports | PASS | Pinned CLI `0.1.4` returned component documentation and a public package import for all sixteen required names; installed package export checks confirmed every documented public subpath | Use only the public imports in the matrix below |
| Required composition paths | PASS | Pinned CLI `0.1.4` documented the required chat and slot relationships summarized below; every named need is also a direct public export | Use the documented relationships below; do not use package internals |
| Focused compatibility check | PASS | `npm run check:astryx` dynamically resolved all eleven documented public subpaths and asserted all sixteen named exports against installed core `0.1.4` | Lock this command and the matrix below for Plan 2 |

Documentation command: from `frontend/`, run `npx astryx --json component <Name>`. The local binary and both packages resolve from exact `0.1.4` lockfile entries. Each row below was captured and re-run as a separate component lookup.

| Required need | Public import | Documented role or composition | Result |
|---|---|---|---|
| `AppShell` | `import { AppShell } from "@astryxdesign/core/AppShell"` | Outermost application layout; accepts main `children` and documented `TopNav`, `SideNav`, `MobileNav`, and `Banner` slots. | PASS |
| `ChatLayout` | `import { ChatLayout } from "@astryxdesign/core/Chat"` | Full-page chat shell documented to wrap `ChatMessageList` and `ChatComposer`. | PASS |
| `ChatComposer` | `import { ChatComposer } from "@astryxdesign/core/Chat"` | Composer with public submit/stop behavior and documented drawer, action, context, input, and send-button slots. | PASS |
| `ChatToolCalls` | `import { ChatToolCalls } from "@astryxdesign/core/Chat"` | Displays one or more LLM tool/function calls; no additional component is required. | PASS |
| `ChatMessage` | `import { ChatMessage } from "@astryxdesign/core/Chat"` | Message row whose public `children` slot accepts bubbles, asset lists, tool calls, images, or other free-form content. | PASS |
| `ButtonGroup` | `import { ButtonGroup } from "@astryxdesign/core/ButtonGroup"` | Connected group for related button actions. | PASS |
| `Button` | `import { Button } from "@astryxdesign/core/Button"` | Direct action component; documented optional `Icon` and `Badge` content. | PASS |
| `Card` | `import { Card } from "@astryxdesign/core/Card"` | Bordered container for discrete, independently interactive items; no additional component is required. | PASS |
| `Collapsible` | `import { Collapsible } from "@astryxdesign/core/Collapsible"` | Triggered disclosure; `CollapsibleGroup` is the documented optional accordion wrapper. | PASS |
| `ProgressBar` | `import { ProgressBar } from "@astryxdesign/core/ProgressBar"` | Horizontal determinate or indeterminate progress indicator; no additional component is required. | PASS |
| `ChatMessageList` | `import { ChatMessageList } from "@astryxdesign/core/Chat"` | Message container whose documented children are typically `ChatMessage` or `ChatSystemMessage`. | PASS |
| `ChatSystemMessage` | `import { ChatSystemMessage } from "@astryxdesign/core/Chat"` | Short factual system/status row with an optional public `Icon` slot. | PASS |
| `MetadataList` | `import { MetadataList } from "@astryxdesign/core/MetadataList"` | Structured key-value list composed with documented `MetadataListItem` children. | PASS |
| `Badge` | `import { Badge } from "@astryxdesign/core/Badge"` | Status/category marker with optional public `Icon` content. | PASS |
| `Banner` | `import { Banner } from "@astryxdesign/core/Banner"` | Persistent page/section message and a documented `AppShell` banner slot value. | PASS |
| `Toast` | `import { Toast } from "@astryxdesign/core/Toast"` | Inline visual toast element for brief non-blocking notification content; no internal viewport API is required by this matrix. | PASS |

## ShopAIKey

Diagnostic foundation and live smoke status: `LOCKED_PASS` after authorized 03F
execution. The isolated harness loads only the three required root settings,
constructs `ChatOpenAI` through an injectable factory with the custom base URL,
binds tools through the public `bind_tools()` method, and emits typed
deterministic records through one sanitization boundary. Focused fake-provider
tests (73) passed without network use. The single-purpose live command
`python backend/scripts/check_shopaikey_compatibility.py` exited `0` once under
the ignored root environment; output was scanned for the configured secret and
prohibited data classes with zero hits. No raw provider payloads, headers, or
secret values are recorded here.

Live matrix (aggregate evidence only; one authorized run):

| Capability | Result | Aggregate evidence | Locked decision |
|---|---|---|---|
| Model discovery | PASS | Master-locked `gpt-4o-mini` present (`exact_master_lock`); configured model matches master; listed_model_count observed as a count only | Model ID `gpt-4o-mini` |
| Basic completion | PASS | Non-empty assistant response; response model match; no silent substitution | Chat completion on `gpt-4o-mini` |
| Function call | PASS | Exactly one `echo_label` call via `bind_tools()`; typed JSON args validated; no raw args stored | Tool-call mode `bind_tools` |
| Tool-call round trip | PASS | Non-empty final assistant response after synthetic tool result | Tool-result mode `tool_result_round_trip` |
| Structured schema | PASS | First permitted mode `strict_schema` met 03A criterion: 3 consecutive attempts, all validated, `repairs_used_total=0`, max one repair allowed per attempt | Structured-output mode `strict_schema`; repair policy max 1 repair/attempt |
| Streaming behavior | PASS (known) | Ordered text chunks supported (`chunk_count=6`, `non_empty_chunk_count=2`, `sequence_ordered=true`); knowledge-only, not required-pass | Streaming classification `streaming_text` / supported |

Classification rules remain: exact `gpt-4o-mini` is required under the current
master plan; an equivalent-only result fails as
`equivalent_requires_source_revision` until an adapter-only master-plan revision
is recorded. No fallback provider was introduced. Diagnostic exit aggregation
returns non-zero when any required-pass capability is not `pass`.

| Evidence item | Result | Evidence | Locked decision |
|---|---|---|---|
| Model discovery | PASS | Live 03F: `exact_master_lock` for `gpt-4o-mini` | Use `gpt-4o-mini` only under current master plan |
| Basic completion | PASS | Live 03F: non-empty response, model match | Chat completion enabled |
| Function call | PASS | Live 03F: valid `bind_tools` + `echo_label` typed args | Tool binding via `ChatOpenAI.bind_tools()` |
| Tool-call round trip | PASS | Live 03F: non-empty final response after tool result | Tool-result round trip supported |
| Structured schema | PASS | Live 03F: `strict_schema` reliable (3/3, 0 repairs) | Lock `strict_schema`; max 1 repair per attempt |
| Streaming behavior | PASS | Live 03F: ordered streaming text chunks supported | Streaming supported (`streaming_text`) |

## PDF

Manifest sources:

- Synthetic metadata: `backend/evaluation/fixtures/synthetic_pdf_manifest.json`
- Local-private template: `backend/evaluation/fixtures/local_private_pdf_manifest.template.json`
- Safe frozen aggregate: `backend/evaluation/fixtures/pdf_fixture_manifest.json`
- Populated private manifest: ignored `backend/evaluation/private/pdf_manifest.local.json`
- Pre-benchmark private criterion copy: ignored `backend/evaluation/private/pdf_pass_criterion.local.json`

User-authorized local corpus materialization (aggregate only; no private filenames or document text):

| Inventory item | Status | Safe evidence |
|---|---|---|
| Local PDF file count | READY | Six PDFs under ignored private evaluation path (5 digital + 1 image-only) |
| Documented private evaluation path | READY | Ignored `backend/evaluation/private/` populated with generic-ID copies and local manifest |
| Frozen committed/safe manifest | READY | `pdf_fixture_manifest.json` records fixture IDs, kinds, page counts, and sha256 digests only |
| User-confirmed digital corpus (5–10) | READY | Five digital fixtures frozen from the user’s existing local ignored PDF set |
| At least one user-redacted evaluation CV slot | READY | `pdf_digital_001` designated as the redacted evaluation CV slot in the private manifest |
| Image-only fixture designation | READY | `pdf_image_only_001` designated; pypdf smoke extractable character count = 0 |
| Numeric digital-fixture pass criterion (“agreed majority”) | READY | Pre-benchmark: require ≥ 4 of 5 digital fixtures with extractable character count > 0 (80% floor) |
| Pre-benchmark freeze | READY | Criterion and fixture digests recorded before Batch04 benchmark measurement |

| Evidence item | Result | Evidence | Locked decision |
|---|---|---|---|
| Frozen fixture set and criterion | READY | Safe freeze + ignored private corpus + pre-benchmark 4/5 digital success rule and image-only `NO_EXTRACTABLE_TEXT` rule; criterion_id `pdf_digital_agreed_majority_v1` unchanged in 04C | Keep 4/5 (80%) digital rule fixed |
| Normal extraction mode | MEASURED | Digital subset 5/5 `EXTRACTED_TEXT` (chars 1049/953/995/971/1038); meets frozen 4/5 | Eligible; not selected (tie on yield) |
| Layout extraction mode | MEASURED_AND_SELECTED | Digital subset 5/5 `EXTRACTED_TEXT` (identical char yields); meets frozen 4/5; equal yield vs normal | **Selected digital parser mode: `layout`** |
| Digital normal/layout comparability | PASS | Same ordered digital IDs, matching page counts (1 each), both modes full coverage; aggregate `backend/evaluation/reports/pdf_extraction_benchmark.json` | Required for 04C acceptance |
| Image-only classification | PASS | Frozen `pdf_image_only_001`: normal and layout both exact `NO_EXTRACTABLE_TEXT` with `extracted_character_count=0` on three repeated dual-mode runs; aggregate refreshed | Exact failure rule locked; no OCR |

### Digital-PDF benchmark table (04C)

Frozen criterion (pre-04A/04C measurement, not changed): require ≥ 4 of 5 digital fixtures with usable extracted character count > 0 under the selected mode (`criterion_id=pdf_digital_agreed_majority_v1`, 80% floor). Aggregate artifact: `backend/evaluation/reports/pdf_extraction_benchmark.json` (metrics only; no document text).

| Fixture ID | Kind | Pages | Normal outcome | Normal chars | Normal ms | Layout outcome | Layout chars | Layout ms |
|---|---|---:|---|---:|---:|---|---:|---:|
| pdf_digital_001 | digital | 1 | EXTRACTED_TEXT | 1049 | 5 | EXTRACTED_TEXT | 1049 | 6 |
| pdf_digital_002 | digital | 1 | EXTRACTED_TEXT | 953 | 5 | EXTRACTED_TEXT | 953 | 4 |
| pdf_digital_003 | digital | 1 | EXTRACTED_TEXT | 995 | 5 | EXTRACTED_TEXT | 995 | 4 |
| pdf_digital_004 | digital | 1 | EXTRACTED_TEXT | 971 | 4 | EXTRACTED_TEXT | 971 | 5 |
| pdf_digital_005 | digital | 1 | EXTRACTED_TEXT | 1038 | 5 | EXTRACTED_TEXT | 1038 | 4 |

| Mode | Digital successes | Required | Meets frozen 4/5 | Total digital usable chars | Notes |
|---|---:|---:|---|---:|---|
| normal | 5 / 5 | 4 | yes | 5006 | Comparable coverage; equal yield |
| layout | 5 / 5 | 4 | yes | 5006 | Comparable coverage; equal yield; **selected** |

**04C parser-mode decision:** lock pypdf **`layout`** for digital CV extraction. Both modes meet the frozen majority rule with identical per-fixture usable character yields; selection uses the master-plan ingestion path preference for layout text extraction under equal measured yield. No OCR, no alternate parser, no post-hoc threshold change. Full PDF gate closed in 04D after image-only exact-code verification.

### Image-only exact failure gate (04D)

Exact failure rule (pre-recorded, unchanged): image-only fixture must yield outcome code **`NO_EXTRACTABLE_TEXT`** with zero usable extracted characters under both `normal` and `layout`; OCR and alternate parsers are prohibited (`ocr_allowed=false`).

Frozen fixture: `pdf_image_only_001` (manifest `phase0_pdf_fixture_freeze_v1`). Aggregate evidence: `backend/evaluation/reports/pdf_extraction_benchmark.json` (`ocr_used=false`, `alternate_parser_used=false`, `parser_library=pypdf`).

| Fixture ID | Kind | Pages | Mode | Outcome (exact) | Usable chars | Elapsed ms (sample) | Repeated runs (3×) |
|---|---|---:|---|---|---:|---:|---|
| pdf_image_only_001 | image_only | 1 | normal | NO_EXTRACTABLE_TEXT | 0 | 1 | all exact code + 0 chars |
| pdf_image_only_001 | image_only | 1 | layout | NO_EXTRACTABLE_TEXT | 0 | 0–1 | all exact code + 0 chars |

| Check | Result | Evidence |
|---|---|---|
| Normal mode exact outcome | PASS | `outcome=NO_EXTRACTABLE_TEXT`, `extracted_character_count=0` |
| Layout mode exact outcome | PASS | `outcome=NO_EXTRACTABLE_TEXT`, `extracted_character_count=0` |
| Zero usable characters both modes | PASS | Non-whitespace char count is 0 for both modes |
| Repeated dual-mode stability | PASS | Three full dual-mode runs; classification and char counts stable |
| OCR package / call / alternate parser | PASS | Source and `pyproject.toml` search clean; aggregate flags `ocr_used=false`, `alternate_parser_used=false` |
| Manual text substitution | PASS | No raw-text fields in aggregate; classifier maps zero usable text only |
| Selected digital mode still meets 04C | PASS | Selected `layout` still 5/5 digital successes vs frozen 4/5 on refreshed aggregate |

**04D PDF extraction compatibility decision:** **PASS**. Selected digital parser mode remains pypdf **`layout`**. Image-only exact dual-mode failure rule is locked as `NO_EXTRACTABLE_TEXT` with zero usable characters. No OCR, no alternate parser, no post-hoc criterion change, no raw document text recorded.

## Embeddings

Manifest source: `backend/evaluation/labels/retrieval_subset_manifest.template.json`. The populated records and any private text remain in the ignored path declared by the template.

| Evidence item | Result | Evidence | Locked decision |
|---|---|---|---|
| Seeded split and label provenance | PENDING | Pending Batch05 evidence | PENDING |
| Scalar and batch compatibility | PENDING | Pending Batch05 evidence | PENDING |
| Ordering, dimensions, and finite values | PENDING | Pending Batch05 evidence | PENDING |
| Quality baseline | PENDING | Pending Batch05 evidence | PENDING |
| Request-latency baseline | PENDING | Pending Batch05 evidence | PENDING |
| Failure behavior | PENDING | Pending Batch05 evidence | PENDING |

## Locked Versions

| Dependency or mode | Selected version or mode | Evidence |
|---|---|---|
| Astryx | `@astryxdesign/core` `0.1.4`; `@astryxdesign/cli` `0.1.4` | Official npm `latest` metadata on 2026-07-11, exact package/lockfile declarations, CLI `--version`, and successful initializer |
| ShopAIKey chat model | `gpt-4o-mini` | Live 03F model discovery exact master lock; tool-call and completion on same model |
| ShopAIKey tool-call mode | `bind_tools` + `tool_result_round_trip` | Live 03F function-call and tool-result checks |
| ShopAIKey completion schema mode | `strict_schema` | Live 03F three consecutive validated attempts; repairs_used_total=0; max 1 repair/attempt policy |
| ShopAIKey streaming | supported (`streaming_text`) | Live 03F ordered non-empty text chunks; knowledge-only |
| PDF extraction mode | `layout` (digital; Batch04 closed) | 04C: both digital modes 5/5 vs frozen 4/5 with equal yield; layout locked; 04D: image-only dual-mode exact `NO_EXTRACTABLE_TEXT` PASS |
| Embedding adapter contract | PENDING | Pending gate measurement |

## Cleanup

| Check | Result | Evidence |
|---|---|---|
| Temporary dependencies removed | PENDING | Pending Phase 0 consolidation |
| Duplicate or unused scaffold removed | PENDING | Pending Phase 0 consolidation |
| Private inputs remain ignored and untracked | PENDING | Pending final Git audit |
| Aggregate evidence contains no private content | PENDING | Pending final privacy audit |

## Handoff

Plan 2 remains blocked until every required gate is measured, supported by evidence, and marked `PASS`. A failed gate permits revision only of the affected adapter decision.

## Final Decisions

| Gate | Result | Evidence | Selected mode/version | Phase impact |
|---|---|---|---|---|
| Prerequisite readiness | PENDING | Sanitized inventory above; user actions remain | PENDING | Blocks affected live gates |
| Astryx compatibility | PASS | Exact npm resolution, initializer evidence, sixteen pinned CLI lookups, and `npm run check:astryx` | `@astryxdesign/core` and `@astryxdesign/cli` `0.1.4`; public matrix above | Astryx decision is locked for Plan 2; overall Plan 2 remains blocked on other Phase 0 gates |
| ShopAIKey compatibility | PASS | Live 03F diagnostic exit 0; all six capabilities characterized; secret/leakage scan clean; fake suite 73 passed without network | Model `gpt-4o-mini`; tools `bind_tools` + tool-result round trip; schema `strict_schema` (max 1 repair/attempt); streaming supported | ShopAIKey provider decisions locked for Plan 2; overall Plan 2 remains blocked on PDF, embeddings, and consolidation gates |
| PDF extraction compatibility | PASS | 04C digital majority met with `layout` locked; 04D image-only normal+layout exact `NO_EXTRACTABLE_TEXT` / 0 chars on repeated runs; OCR/alternate search clean | Digital mode `layout`; image-only exact failure `NO_EXTRACTABLE_TEXT` | PDF adapter locked for Plan 2; overall Plan 2 remains blocked on embeddings and consolidation gates |
| Embedding compatibility | PENDING | Pending Batch05 evidence | PENDING | Blocks Plan 2 |
| Cleanup and evidence consolidation | PENDING | Pending Batch06 evidence | PENDING | Blocks Plan 2 |
