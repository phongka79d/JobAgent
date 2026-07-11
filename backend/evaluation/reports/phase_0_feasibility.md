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
| Digital PDF corpus | COUNT_READY | Six ignored PDFs observed; no names, paths, or content were recorded | Confirm the set is representative, digitally born, and redacted; approve the numeric criterion |
| Image-only PDF fixture | MISSING_OR_UNDECLARED | No safe designation was available | Supply or designate the local ignored fixture |
| Labeled retrieval subset | MISSING_OR_UNDECLARED | No declared manifest or location was available | Confirm provenance, fixed split, seed, record count, and decision criteria |
| PDF and embedding decision criteria | BLOCKED_BY_USER_ACTION | No approved numeric criteria were available | Record criteria before measuring affected gates |
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

| Evidence item | Result | Evidence | Locked decision |
|---|---|---|---|
| Model discovery | PENDING | Pending Batch03 evidence | PENDING |
| Basic completion | PENDING | Pending Batch03 evidence | PENDING |
| Function call | PENDING | Pending Batch03 evidence | PENDING |
| Tool-call round trip | PENDING | Pending Batch03 evidence | PENDING |
| Structured schema | PENDING | Pending Batch03 evidence | PENDING |
| Streaming behavior | PENDING | Pending Batch03 evidence | PENDING |

## PDF

Manifest sources:

- Synthetic metadata: `backend/evaluation/fixtures/synthetic_pdf_manifest.json`
- Local-private template: `backend/evaluation/fixtures/local_private_pdf_manifest.template.json`
- Populated private manifest: ignored local path declared by the template

| Evidence item | Result | Evidence | Locked decision |
|---|---|---|---|
| Frozen fixture set and criterion | PENDING | Pending Batch04 evidence | PENDING |
| Normal extraction mode | PENDING | Pending Batch04 evidence | PENDING |
| Layout extraction mode | PENDING | Pending Batch04 evidence | PENDING |
| Image-only classification | PENDING | Pending Batch04 evidence | PENDING |

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
| ShopAIKey completion schema mode | PENDING | Pending gate measurement |
| PDF extraction mode | PENDING | Pending gate measurement |
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
| ShopAIKey compatibility | PENDING | Pending Batch03 evidence | PENDING | Blocks Plan 2 |
| PDF extraction compatibility | PENDING | Pending Batch04 evidence | PENDING | Blocks Plan 2 |
| Embedding compatibility | PENDING | Pending Batch05 evidence | PENDING | Blocks Plan 2 |
| Cleanup and evidence consolidation | PENDING | Pending Batch06 evidence | PENDING | Blocks Plan 2 |
