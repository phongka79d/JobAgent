# Plan 7 - Master Phase 6: Hardening and Local Release

## 1. Objective

Convert the completed MVP into a reproducible local release by closing failure-path, idempotency, recovery, privacy, documentation, and end-to-end test gaps without introducing new product features or infrastructure.

## 2. Source of Truth

- `Master_plan.md` section 2, especially the explicit out-of-scope list.
- Sections 20-24 for recovery, graph rebuild, security/privacy, environment, and local testing.
- Section 25, **Phase 6 - Hardening and local release**.
- Sections 27-29 for Definition of Done, Future Work boundaries, and the final planning decision.
- Approved outputs and verification commands from `Plan_1.md` through `Plan_6.md`.

## 3. Prerequisites from Prior Phases

- [ ] All six preceding plans meet their exit gates.
- [ ] The complete synthetic CV -> approval -> JD -> sync -> match flow works locally.
- [ ] Evaluation thresholds pass with locked configuration and aggregate reports.
- [ ] Graph rebuild and all local quality commands exist.
- [ ] No unresolved schema migration or cross-phase contract change remains.

## 4. Scope

- Complete backend unit/integration, frontend, and local end-to-end suites.
- Test ShopAIKey outage, Neo4j outage, invalid schema, SSE disconnect, duplicate, and rollback scenarios.
- Verify idempotency of approval buttons and every write tool.
- Verify graph rebuild from a fresh Neo4j volume using SQLite as source of truth.
- Verify one root `.env`, localhost-only exposure, exact CORS, and secret/private-data hygiene.
- Complete root README architecture, setup, commands, demo, evaluation results, failure behavior, and limitations.
- Add a concise model/data card for extraction and matching evaluation.
- Perform a final implementation-vs-master scope audit and remove accidental out-of-scope/dead code.
- Prove fresh-clone local startup and the entire E2E flow without manual database edits.

## 5. Out of Scope

- New features, models, providers, ranking components, endpoints, data stores, worker services, or UI screens.
- Authentication, multi-user/multi-conversation support, CV history, OCR/DOCX, crawling, auto-apply, tracking, cloud deployment, or CI.
- Retuning against held-out data or changing evaluation thresholds to force a pass.
- Qdrant, Redis, Celery, Kafka, reranking, LangSmith cloud, or multi-agent handoffs.
- Treating future-work items as release blockers or silently implementing them.

## 6. Target Directory Structure

```text
JobAgent/
|-- backend/
|   |-- evaluation/
|   |   |-- reports/
|   |   |-- MODEL_DATA_CARD.md
|   |   `-- README.md
|   |-- tests/{unit,integration,e2e}/
|   `-- pyproject.toml
|-- frontend/
|   |-- src/test/
|   `-- package.json
|-- infrastructure/
|   |-- docker-compose.yml
|   `-- scripts/rebuild_graph.py
|-- .env.example
|-- .gitignore
`-- README.md
```

Hardening may split oversized existing modules or delete dead code, but it must preserve established contracts and behavior.

## 7. Technical Specifications

### 7.1 Release test matrix

The local release suite must cover:

| Layer | Required proof |
|---|---|
| Backend unit | Redaction, schemas, canonicalization, duplicates, quality, scoring, authorization, injection isolation, outbox idempotency |
| Backend integration | Upload, SSE ordering, interrupt/resume, SQLite migrations, Neo4j sync/rebuild, fake ShopAIKey failures |
| Frontend | SSE reducer, tool mapping, approval idempotency, attachment state, hydration, match breakdown, disconnect/error states |
| End to end | Synthetic PDF -> draft -> approve -> raw JD -> save/sync -> match -> explanation |
| Operational | Fresh volumes, restart persistence, provider outage, Neo4j outage/recovery, graph rebuild |

Normal automated tests must use fake ShopAIKey responses. The real compatibility smoke test remains explicit and local.

### 7.2 Failure and recovery acceptance

Every failure in master section 20 must map to a stable error code, persisted state where required, sanitized user message, and test. No path may report success after a failed tool. Retry ceilings remain: one provider retry, one schema repair, no LLM-controlled retry loops, and at most six tool iterations.

Neo4j outage must preserve SQLite writes and retryable outbox state. A rebuild must clear only JobAgent-derived graph data, recreate constraints/vector index, load active/scorable SQLite records, recompute embeddings when needed, verify entity counts, and update sync states.

### 7.3 Security and privacy release gate

- Frontend/backend published ports bind to `127.0.0.1`; Neo4j stays internal unless an explicit localhost development profile is used.
- CORS allows the exact configured frontend origin.
- Root `.env` is the only environment file and is ignored; `.env.example` contains no secrets.
- Logs/SSE exclude raw CV/JD text, contact PII, keys, Authorization headers, raw tool arguments, and stack traces.
- Runtime files and real evaluation data remain outside Git.
- CV/JD prompt content remains delimited as untrusted data and cannot authorize tools.

### 7.4 Documentation contract

The root README must describe architecture/ownership, prerequisites, root environment setup, Docker startup, migrations, backend/frontend quality commands, Neo4j tests/rebuild, ShopAIKey diagnostic, extraction/ranking evaluation, demo flow, troubleshooting, evaluation results, graph ablation decision, privacy, limitations, and explicit non-goals. Commands must be copy-pasteable and single-purpose.

The model/data card records model/provider IDs, embedding selection, data provenance and split, per-profile limitation, extraction/ranking/tool metrics, latency environment, PII handling, graph ablation result, known limitations, and prohibited population-level claims.

### 7.5 Definition-of-Done audit

Create a checklist mapping every item in master section 27 to concrete code/test/report evidence. Separately search dependencies, configuration, routes, services, and UI for every item in section 2.2. Remove accidental scope/dead dependencies or document a blocker; do not waive the master boundary.

## 8. Implementation Steps

- [ ] Inventory current tests against the master test strategy and fill only evidence gaps.
- [ ] Add failure-injection coverage for provider, schema, graph, SSE, duplicate, and replacement paths.
- [ ] Audit every write tool and UI action for stable idempotency keys and replay behavior.
- [ ] Run migrations and the E2E flow on fresh volumes and on restarted persistent volumes.
- [ ] Rebuild a fresh Neo4j volume from SQLite and verify IDs, counts, embeddings, constraints, and sync states.
- [ ] Audit localhost binding, CORS, root environment usage, logs/SSE, Git tracking, and private-data ignore rules.
- [ ] Run backend lint/type-check/tests, frontend lint/type-check/tests, graph tests, and all evaluation commands.
- [ ] Write/update README and the model/data card from measured current results only.
- [ ] Map all Definition-of-Done items to evidence and audit the explicit out-of-scope list.
- [ ] Remove dead experiments, temporary diagnostic exposure, duplicate logic, and accidental dependencies.
- [ ] Perform the final fresh-clone-equivalent Docker startup and synthetic E2E demonstration.

## 9. Verification & Testing Plan

Run and record all single-purpose local commands required by master section 24.5. The release passes only when:

- Backend lint, type-check, unit, and integration suites pass.
- Frontend lint, type-check, reducer, and component suites pass.
- Neo4j integration and clean-volume rebuild checks pass.
- ShopAIKey compatibility smoke test passes using local credentials.
- Extraction, ranking, tool-selection, and latency reports meet locked thresholds.
- Full Docker Compose starts from fresh local state with one root `.env`.
- The complete synthetic E2E flow works without manual database edits.
- Failure tests prove no false success, unauthorized profile commit, PII leak, duplicate write, or unrecoverable canonical-state loss.
- Git contains no secret, real CV/JD data, runtime file, extra environment file, CI workflow, or out-of-scope dependency.
- README commands and documented behavior match the verified implementation.

Any failed condition blocks release; fix the owning existing module and rerun its focused tests plus the affected E2E path.

## 10. Handoff Notes for MVP Completion

The completed handoff consists of:

- A reproducible local Docker Compose application using one root `.env`.
- SQLite canonical state with a rebuildable Neo4j graph/vector index.
- One Agent, one conversation, one active CV/profile, seven tools, manual JD input, and transparent matching.
- Passing local test/evaluation evidence, graph ablation decision, README, and model/data card.
- A final scope/Definition-of-Done evidence checklist.

No later work is implied by this plan. Items in master section 28 remain future options and require a new approved master-plan revision before implementation.
