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
| Pinned package version | PENDING | Pending Batch02 evidence | PENDING |
| Public component imports | PENDING | Pending Batch02 evidence | PENDING |
| Required composition paths | PENDING | Pending Batch02 evidence | PENDING |

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
| Astryx | PENDING | Pending gate measurement |
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
| Astryx compatibility | PENDING | Pending Batch02 evidence | PENDING | Blocks Plan 2 |
| ShopAIKey compatibility | PENDING | Pending Batch03 evidence | PENDING | Blocks Plan 2 |
| PDF extraction compatibility | PENDING | Pending Batch04 evidence | PENDING | Blocks Plan 2 |
| Embedding compatibility | PENDING | Pending Batch05 evidence | PENDING | Blocks Plan 2 |
| Cleanup and evidence consolidation | PENDING | Pending Batch06 evidence | PENDING | Blocks Plan 2 |
