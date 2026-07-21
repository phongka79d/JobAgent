# JobAgent README Restructure Design

## Context

The repository root `README.md` is accurate in many places but has grown to
about 1,178 lines. It mixes current onboarding and operational guidance with a
long chronological summary of Plans 1–14. That makes the current architecture,
runtime workflow, setup path, and validation commands harder to locate than
they need to be.

The replacement README is for maintainers and future AI agents working in the
repository. It is practical project documentation, not marketing copy and not a
release changelog.

## Goals

- Describe the current JobAgent system at the accepted Plan 14 baseline.
- Let a new maintainer understand the major component boundaries and workflows
  without reading every plan first.
- Provide source-backed setup, run, diagnostic, and validation commands.
- Tell future AI agents which files own behavior and which coordinated checks
  are required before changing shared contracts.
- Keep useful operational safeguards while moving historical detail behind
  links into `docs/`.

## Non-Goals

- Rewriting product behavior, plans, tasks, acceptance evidence, or source code.
- Creating a full API reference or duplicating the Master Plan's schema tables.
- Preserving a chronological summary of every implementation batch in the root
  README.
- Claiming production readiness, security guarantees, authentication, OCR, or
  multi-user support that the repository does not provide.

## Selected Approach

Replace the current README with a present-tense onboarding and operations guide
of roughly 400–600 lines. Preserve accurate, useful commands and safety notes,
but remove the long Plan-by-Plan narrative. Keep one concise current-baseline
statement and link readers to the authoritative planning, task, and acceptance
documents for history and detailed evidence.

This approach was selected over:

1. Retaining most release history and reorganizing it, which would leave the
   document difficult to scan.
2. Producing a minimal setup-only README, which would not give maintainers or AI
   agents enough architectural and workflow context.

## Evidence Hierarchy

README claims will be derived in this order:

1. Runtime code, entrypoints, manifests, and tests.
2. `infrastructure/docker-compose.yml` and `.env.example`.
3. `docs/plans/Master_plan.md` for stable architecture and product contracts.
4. Current `Plan_14.md`, `task_14.md`, and acceptance documents for the accepted
   release baseline and verification evidence.

When these sources disagree, current executable code and configuration win for
runtime facts. Uncertain facts must be marked as uncertain rather than inferred.

## README Information Architecture

The rewritten README will use the following structure:

1. **Overview** — product purpose, local single-user scope, and three runtime
   services.
2. **Current baseline** — concise Plan 14 completion statement and links to
   detailed evidence.
3. **What this repository contains** — full-stack workspace boundaries and
   authoritative sources.
4. **Repository structure** — a compact tree plus ownership explanations.
5. **Architecture** — frontend, API, Agent, domain services, persistence, graph,
   provider adapters, and their data flow.
6. **Main workflows** — ordered, file-linked descriptions of:
   - CV upload, extraction, draft approval, activation, reprocessing, and
     deletion;
   - chat turn creation, SSE streaming, Agent/tool execution, interruption, and
     resume;
   - JD detection, confirmation, ingestion, exact deduplication, graph sync,
     explicit evaluation, and deletion;
   - observability reads and graph rebuild.
7. **Frontend** — React/Vite/Astryx composition, feature ownership, reducer and
   API client boundaries, and UI validation.
8. **Backend** — FastAPI entrypoint, route/service/repository layers, LangGraph
   Agent, tools, adapters, migrations, and diagnostics.
9. **Data and external services** — SQLite source of truth, retained files,
   Neo4j derived state, ShopAIKey chat/embedding calls, and checkpoint storage.
10. **Configuration** — variable name, requiredness, purpose, and evidence
    source; no values.
11. **Setup and running** — local editable installs and the supported Compose
    workflow with confirmed ports.
12. **Testing and validation** — focused and full backend/frontend gates, plan
    validation, Compose health, diagnostics, and browser acceptance pointers.
13. **Failure and recovery** — safe retry, rebuild, volume, migration, and
    cleanup rules.
14. **Development notes for AI agents** — source-of-truth order, coordinated
    ownership, ignored/generated directories, scope discipline, and mandatory
    pre-completion checks.
15. **Known gaps and limitations** — explicit local-MVP boundaries and runtime
    dependencies.
16. **Documentation map** — links to Master Plan, Plan 14, task contract,
    acceptance evidence, designs, and review reports.

## Workflow Documentation Rules

Each main workflow will:

- start from an observable user or API action;
- name the request or UI boundary;
- identify orchestration and domain owners;
- identify SQLite, file, Neo4j, provider, or checkpoint effects;
- describe the returned SSE/API/UI outcome;
- call out confirmation, retry, deduplication, or no-side-effect boundaries;
- link to representative owning files instead of reproducing implementation
  details.

## Configuration and Secret Safety

- Never read or copy values from the ignored root `.env`.
- Derive variable names and meanings from `.env.example`, settings code, Compose,
  and frontend configuration.
- Document that process environment overrides the root `.env` for backend
  settings.
- Mark secrets such as Neo4j and ShopAIKey credentials as required without
  exposing examples beyond the tracked empty template.
- Exclude runtime database contents, retained CV/JD text, browser payloads, and
  provider bodies from README examples.

## Historical Content Policy

The README will not repeat Plan 1–14 batch narratives. It will keep:

- one current-baseline statement;
- stable architecture and safety rules still reflected in code;
- current commands and accepted operational procedures;
- direct links to plans, tasks, acceptance ledgers, and design documents.

Detailed release history remains in Git and `docs/`.

## Known Limitations to Document

- Local, single-user MVP with no authentication or authorization layer.
- Exactly one root runtime `.env` and three loopback Compose services.
- PDF-only CV input with configured size/page limits and no OCR path.
- ShopAIKey network/provider availability is required for live chat and
  embeddings.
- SQLite and retained files are authoritative; Neo4j is rebuildable derived
  state.
- Job evaluation is explicit and revision-keyed; saving a JD does not
  automatically evaluate it.
- Browser acceptance is synthetic and the normal stack is intended to remain
  available for local manual testing.

## Validation Plan

After rewriting README:

1. Verify every referenced repository path exists.
2. Verify every documented package command exists in `pyproject.toml`,
   `package.json`, Compose, or tracked scripts.
3. Run the shared plan-structure validator.
4. Run `docker compose ... config` without printing resolved secret values.
5. Run focused lightweight checks needed to validate README claims about
   entrypoints and health; do not rerun destructive setup or cleanup.
6. Scan the README for secret-like assignments, placeholder markers, stale Plan
   completion language, and unsupported claims.
7. Run `git diff --check` and inspect the final changed-path scope.

## Acceptance Criteria

- `README.md` is a current onboarding and operations guide rather than a
  chronological changelog.
- Every major source folder and runtime boundary is described.
- The main CV, chat/Agent, JD/evaluation, observability, and rebuild workflows
  are documented with owning file references.
- Setup, runtime, diagnostics, and validation commands come from tracked
  evidence.
- The mandatory `Development Notes for AI Agents` section is specific to
  JobAgent.
- Secrets are absent and uncertainty or limitations are explicit.
- Historical detail is discoverable through a concise documentation map.
