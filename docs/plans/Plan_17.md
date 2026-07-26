# Plan_17: Source-Grounded CV Tailoring and Fixed LaTeX Rendering

## Objective

Deliver immutable, editable derivative CV versions from one ready approved CV and either a selected scorable saved JD or a bounded natural-language instruction. Every successful save produces source-grounded latex-cv-v1 TeX and PDF artifacts without changing approved CV/Profile/JD truth, evaluations, matching, or Neo4j.

## Source of Truth

- docs/plans/Master_plan.md: Version 2.3 Amendment — Source-Grounded CV Tailoring and Fixed LaTeX Rendering
- docs/superpowers/specs/2026-07-26-cv-tailoring-latex-design.md: approved feature design
- docs/superpowers/plans/2026-07-26-cv-tailoring-latex.md: dependency-ordered implementation detail

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| P17-CVT-01 | 30.1 | One coordinator creates immutable derivative sessions/versions from selected JD or instruction. | Coordinator/repository tests prove artifacts, CAS, stale/read, and unchanged source truth. |
| P17-CVT-02 | 30.1 | Dynamic source sections, deterministic provenance, and shared AI/manual no-invention guard. | Schema/projection/guard/privacy-sentinel tests. |
| P17-CVT-03 | 30.1 | Nullable phone/email/GitHub approval and conditional contact rendering. | Backward-compatibility, approval/re-extraction, and renderer golden tests. |
| P17-CVT-04 | 30.2 | Plan 17 implements only the existing Main Agent plus one fixed Tailoring Agent; Main registry changes seven to eight tools. | Topology, captured-prompt, lifecycle, registry, and integration tests reject unapproved or unbounded topology. |
| P17-CVT-05 | 30.3 | Migration 0007, dual-owner runs, UUID artifacts, CAS/currentness/deletion. | Migration/repository/activity-gate/storage tests. |
| P17-CVT-06 | 30.3 | Fixed escaped latex-cv-v1 and two-pass argv-only pdflatex. | TeX goldens, fake argv tests, and real image smoke. |
| P17-CVT-07 | 30.4 | Typed API, selected-JD transport, eighth tool, safe streams/downloads/deletion. | API/SSE/header/CORS/tool-parity tests. |
| P17-CVT-08 | 30.4 | Exact three-service Compose and bounded settings. | Compose config/image/health/settings tests. |
| P17-CVT-09 | 30.4 | Astryx editor and one saved-JD state owner. | Parser/state/UI/accessibility/static-source tests. |
| P17-CVT-10 | 30.5 | Synthetic end-to-end, browser, operations, and scope evidence. | Full gates, acceptance checklist, plan/diff/secret review. |

## Prerequisites

| Producer plan or environment | Required artifact/contract | Check before work |
|---|---|---|
| Master Version 2.3 | Controlled multi-Agent governance and fixed-feature contract | Confirm the governance policy and Plan 17's bounded topology are present; do not add a generic framework or another Agent. |
| Plan_16 | Grounded skills, selected-JD compatibility, one saved-JD owner | Reuse unchanged skill, normalizer, matching, evaluation, and Neo4j owners. |
| Plans 1–15 | Ready profiles/documents, Jobs, chat SSE, migrations, activity gates, Astryx shell | Inspect existing owners and tests before adding seams. |
| Existing Compose image | frontend, backend, neo4j services | Confirm the service list remains exact. |

## Scope

- Add optional contact extraction through the existing profile approval/re-extraction flow.
- Add tailored content/provenance schemas, deterministic baseline projection, and one shared grounding guard for AI and manual saves.
- Add tailoring sessions/immutable versions, migration 0007_add_cv_tailoring, dual-owner runs, currentness/CAS, UUID artifact storage, and retryable deletion.
- Add fixed dynamic latex-cv-v1 rendering and bounded twice-run argv-only pdflatex with no shell escape in the existing backend image.
- Add only the fixed Tailoring Agent/coordinator beside the existing Main Agent, direct APIs, selected-JD propagation, and the eighth Main-Agent tool.
- Lift the sole saved-JD owner to App; implement Astryx-only sessions/editor/preview/revision UI and synthetic acceptance.

## Out of Scope

- Mutating/backfilling approved or archived CV, CVDocument, Candidate Profile, Job, evaluation, matching, or Neo4j records.
- Any other Agent in this phase; unapproved or unbounded Agent topology, model-driven recursive spawn, peer-handoff mesh, tailoring ToolNode, generic Agent framework, worker, queue, background job, fourth Compose service, new provider/model, or tailored-CV graph/vector data.
- Arbitrary LaTeX/template editing/upload, user packages/images/fonts, shell execution, runtime compiler networking, raw artifact paths/source text/JD, or compiler log persistence.
- Automatic creation/evaluation/contact backfill; contact inference from a username, profession, or repository mention.
- Tailwind, a second UI system, raw colors, guessed Astryx props, layout divs, duplicate saved-JD owner, or second chat stream/reducer.
- Reimplementation of Plan 16 skill normalization, evaluation, matching, or selected-map contracts.

## Target Directory Structure

    backend/
      app/{agent,api,db/models,repositories,schemas,services,storage}/cv_tailoring*.py
      app/tools/cv_tailoring.py
      migrations/versions/0007_add_cv_tailoring.py
      tests/{unit,integration,e2e}/...cv_tailoring...
    frontend/src/features/cv-tailoring/{types,api,state,Tailoring*.tsx,cv-tailoring.css}
    frontend/src/app/App.tsx
    infrastructure/{docker/backend.Dockerfile,docker-compose.yml}
    .env.example
    README.md
    docs/{operations,acceptance}/cv-tailoring-latex.md

## Technical Specifications

### Source-grounding and privacy

- TailoringCoordinator is the sole generation/revision owner for direct and Main-Agent entries. Creation requires a ready profile with approved full_name and either a full/partial Job or bounded instruction.
- A deterministic baseline contains every approved source section. IDs/headings/kinds/ordinals/order are immutable; server-owned fact IDs bind fields to source revision, section, entry, and path. Untargeted sections copy exactly from baseline or parent.
- The fixed Tailoring Agent receives outline/JD/instruction, then only selected section bodies/facts. It never receives contacts, unrelated bodies, raw PDF/JD, reference template, LaTeX, paths, Neo4j, or secrets. `TailoringCoordinator` is its sole launch/lifecycle owner; it has no ToolNode, dynamic/peer delegation, or spawn edge and shares one schema/grounding repair budget.
- AI and manual saves use the same fact-bank guard. Unsupported facts, changed section/attribute identity, cross-section evidence, unknown fields, excess content, and ungrounded names/dates/numbers/URLs/skills fail safely.

### Persistence, renderer, and compiler

- Session lifecycle is generating, ready, failed, deleting; immutable version creators are ai or user. Session currentness checks profile timestamp, CV hash, selected Job timestamp, and template version. Version creation CASes parent/latest number and returns TAILORING_PARENT_CONFLICT without overwrite.
- agent_runs run_kind is chat or cv_tailoring with owner XOR for this phase. Tailoring runs have a session and no user message; optional parent is only the same-profile Main-Agent chat run. Existing activity/checkpoint/terminal rules apply. A future Agent needs its own approved plan, migration, ownership checks, and tests rather than a generic run type.
- Server-derived UUID paths beneath FILES_DIR/cv-tailoring stage/promote fixed resume.tex and resume.pdf before short CAS. Clients never provide or see paths. Deletes are owned and retryable.
- latex-cv-v1 is the sole fixed template and escapes text/validated URLs while rendering all source sections, including unknown kinds. pdflatex runs twice by argv with no shell escape, timeout and TeX/PDF/page bounds; it uses safe code-only failure and no persisted logs.

### API, runtime, and UI

- Implement exactly the Master 30.4 endpoints. Session/AI-version streams reuse the seven existing SSE events; no new event or run-start field. Create-session exposes X-CV-Tailoring-Session-Id through CORS and disconnect is never success.
- Add nullable selected-JD transport to chat only; backend reloads/validates it. create_tailored_cv is Main tool eight and returns safe IDs/status, never bodies/artifacts.
- Compose remains exactly frontend, backend, neo4j; TeX packages and compile smoke live in the existing backend image. Settings bound instruction, sections/items, TeX, timeout, and PDF size.
- App owns one useSavedJobsState. Astryx neutral components/tokens provide sessions, both entries, structured editing, scoped AI edit, explicit save, evidence, immutable versions/downloads/PDF preview, stale/conflict/delete recovery, desktop split view, and accessible mobile tabs.

## Implementation

1. Write RED tests for contacts, schemas/provenance, grounding/privacy, persistence/run XOR, artifact safety, compiler argv, API/SSE, and frontend owner/parser behavior.
2. Extend contact extraction/projection/drafts/approval with nullable backward-compatible fields; prove ambiguity and GitHub rules.
3. Add tailored content/patch/provenance contracts, baseline fact projection, and the common AI/manual grounding guard.
4. Add models/repositories/migration 0007, run-owner checks, version CAS/currentness, and activity-gate coverage without breaking chat.
5. Add UUID artifact storage, fixed renderer, settings, compiler, TeX image packages, and synthetic bilingual compile smoke.
6. Implement the fixed Agent and coordinator with authoritative source loading, selected-only context, sole coordinator launch/lifecycle ownership, bounded repair/retry, staging/CAS, and truthful failures; add no other Agent.
7. Add routes, artifact streaming/deletion, CORS header, selected-JD propagation, and Main tool eight with direct/tool parity.
8. Add strict TypeScript API/SSE parsing and move the existing saved-JD state instance to App.
9. Build Astryx sessions/editor/preview after component discovery; preserve ChatPage and cover accessibility/responsive/error/conflict behavior.
10. Document operations/acceptance and run full synthetic, browser, Compose, portfolio, scope, and secret verification.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Contact/content guard | Set-Location backend; run focused contact, schema, projection, and guard Pytest files. | Backward compatibility, grounded dynamic sections, privacy, and no-invention pass. |
| Persistence/artifacts | Set-Location backend; run tailoring models, storage, renderer, repository, migrations, and activity-gate tests. | Migration, CAS, paths, currentness, cleanup, and run ownership pass. |
| Compiler/runtime | Set-Location backend; run compiler, dependency-manifest, Compose, and real compiler integration tests. | Exact two argv-only no-shell calls, safe bounds, image smoke, and three services pass. |
| Agent/API | Set-Location backend; run tailoring Agent/coordinator/API/deletion tests. | Fixed Phase 13 topology, coordinator-owned parent/child lifecycle, privacy/repair limits, direct/tool parity, header/CORS, and safe deletion pass; unapproved or unbounded topology is rejected. |
| Frontend | Set-Location frontend; run tailoring API/state/editor/accessibility tests, lint, typecheck, and build. | Strict parser, one state owner, Astryx/accessibility/static constraints, and build pass. |
| Full/release | Run backend Ruff/Mypy/full Pytest; frontend full gates; Compose build/health; synthetic browser acceptance. | No private data; both entry paths, optional contacts, stale/conflict/delete, preview, and mobile states pass. |
| Portfolio/scope | Run shared plan validator, git diff --check, and git status --short. | Plans 1–17 contiguous, only Plan 17 terminal, no unauthorized data/scope. |

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Master Version 2.3 | Controlled multi-Agent governance, fixed tailoring topology, and public contracts | It permits future Agents only through separately approved coordinator-owned contracts; this phase adds no other Agent. |
| Plan_16 | Grounded skills, selected-JD compatibility, one saved-JD owner | Tailoring does not change those business-rule owners. |
| Plans 1–15 | Profile/JD/chat/activity/migration/Astryx baseline | Historical contracts remain compatible. |
| Approved design/implementation plan | Detailed locked choices and sequencing | No reference/sample facts are reused. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| task-writing-agent after portfolio approval | Plan 17 requirement map and batches | Task 17 maps P17-CVT-01 through P17-CVT-10 to bounded A1/A2/A3 work. |
| Future A1 implementation | Cross-layer tailoring contract | Test-first work preserves grounding, privacy, and derivative-source boundaries. |
| Future A2/A3 review | Functional/scope acceptance criteria | Evidence proves the fixed Phase 13 topology/eight-tool change is bounded and adds no project-wide Agent cap. |

## Completion Contract

Plan 17 is complete when selected-JD and instruction-only requests use one coordinator to create immutable, grounded latex-cv-v1 TeX and PDF versions. The Tailoring Agent receives only approved staged context; manual and AI changes use the same guard; source section identity/order—including unknown sections—survives; and optional contacts omit cleanly.

Migration 0007_add_cv_tailoring, dual-owner runs, UUID artifact lifecycle, CAS/currentness/delete behavior, twice-run argv-only pdflatex with no shell escape, and CORS-exposed X-CV-Tailoring-Session-Id pass synthetic focused/full checks. The Main registry has exactly eight tools and this phase's topology is the existing Main Agent plus one fixed Tailoring Agent; it adds no other Agent, while future Agents remain subject to the approved controlled governance contract. Existing SSE vocabulary and exactly three Compose services remain unchanged.

The Astryx neutral frontend uses one saved-JD owner and covers both entries, sessions, editor, versions, evidence, safe download/preview, stale/conflict/error/delete recovery, responsive accessibility, and no raw-source leakage. Approved CV/Profile/JD, evaluations, matching, and Neo4j truth remain unchanged. Full backend/frontend/migration/Compose/compiler/browser/portfolio/diff/secret gates pass without real CV/JD data, unapproved or unbounded Agent topology, generic Agent framework, worker/queue/service, shell compiler, or unrelated scope expansion.
