# Plan_15: Guarded JD Extraction and Safe Retained-JD Re-extraction

## Objective

Improve the semantic reliability and inspectability of the existing JD pipeline
without changing its stored field set, provider model, scoring formula, or
taxonomy ownership. Only source-grounded direct facts, atomic skill rows, and
non-conflicting required/preferred groups may reach normalization, quality
classification, embedding, persistence, graph synchronization, or scoring.

Add one explicit **Re-extract JD** action for a retained Job. It must stage all
provider and embedding work outside a transaction, preserve the current durable
result on every pre-commit failure, atomically replace only with a `full` or
`partial` result, make existing evaluations stale through the Job revision, and
never evaluate automatically. The saved-JD detail must render the useful fields
already present in `JobPostExtraction`, including bounded expandable evidence.

## Source of Truth

- `docs/plans/Master_plan.md` Version 2.0: Sections 6.2, 6.4, 7.4, 7.7, 11,
  14, 15.2, 15.6, 19, 20, 21, 24, Phase 11, Definition of Done, and the Final
  Planning Decision.
- `docs/superpowers/specs/2026-07-21-jd-extraction-quality-guard-design.md`:
  approved bugfix scope, exact guard vocabulary, safe replacement transaction,
  response semantics, UI behavior, and acceptance design.
- `docs/plans/Plan_14.md`: intent-aware passive JD confirmation, strict durable
  source ownership, one Agent/decision/ToolNode topology, and direct-ingestion
  compatibility baseline.
- Current repository owners: `backend/app/services/jd_extraction.py`,
  `backend/app/services/jd_ingestion.py`,
  `backend/app/services/skill_normalization.py`,
  `backend/app/repositories/jobs.py`, `backend/app/graph/sync_job.py`,
  `backend/app/services/saved_jobs.py`, `backend/app/api/jobs.py`, and
  `frontend/src/features/jobs/`, and
  `frontend/src/features/observability/ObservabilitySidebar.tsx`.

If implementation evidence conflicts with this plan, the approved design and
Master Version 2.0 win. Do not broaden the phase to repair unrelated Agent, CV,
matching, graph-observability, or layout behavior.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Required evidence |
|---|---|---|---|
| P15-GRD-01 | 7.4, 11.4, 20 | Direct metadata, responsibilities, and skill evidence are source-grounded under NFKC, whitespace-collapse, and casefold comparison before downstream work. | Pure guard tests plus synthetic English/Vietnamese golden cases. |
| P15-GRD-02 | 7.4, 9, 11.4 | Skill labels are atomic; punctuation-bearing technical names and unknown atomic skills remain valid; canonical duplicates and cross-group conflicts are rejected. | Taxonomy-backed unit tests for compounds, qualifiers, exceptions, duplicates, and group conflicts. |
| P15-RPR-01 | 7.4, 20 | The current one-repair limit handles schema or guard failure with sanitized diagnostics; a second invalid result fails safely. | Fake-invoker call counts, exact issue-code/path assertions, 20-issue cap, and log/prompt redaction checks. |
| P15-ING-01 | 6.4, 11.4-11.5 | New text and URL ingestion share the guarded extractor while exact non-failed duplicate return remains provider-free. | Text/URL ingestion and exact-dedupe integration tests. |
| P15-REX-01 | 6.2, 6.4, 11.6, 20 | Explicit re-extraction preserves identity/source/raw data, stages work outside transactions, and compare-and-swap replaces only with `full` or `partial`. | Repository concurrency tests and service failure-matrix tests. |
| P15-REX-02 | 6.4, 7.7, 11.6, 17.5 | Successful replacement changes the Job revision, projects prior evaluations as stale, and performs no evaluation. | Integration assertions over Job/evaluation rows and evaluation-provider spies. |
| P15-REX-03 | 6.4, 7.7, 20, 21 | Neo4j failure after SQLite commit returns truthful partial success and rebuild guidance; same-ID sync replaces only that Job's projection. | Graph fake/Neo4j tests and HTTP response assertions. |
| P15-API-01 | 7.7, 14 | `POST /api/jobs/{job_id}/reextract` accepts no replacement fields and returns the bounded `ReextractJobResponse` or safe pre-commit errors. | Schema and saved-JD API tests, including forbidden replacement bodies. |
| P15-UI-01 | 15.2, 15.6 | Saved detail renders all existing extraction groups and a non-optimistic confirmation-based re-extract action wired through the existing sidebar-local saved-job owner. | Frontend parser, component, reducer/state, accessibility, sidebar wiring, currentness refresh, and graph-generation invalidation tests. |
| P15-QA-01 | 19, 24, Phase 11 | Deterministic tests plus one bounded live-provider diagnostic establish semantic quality on synthetic content. | Fixture results, diagnostic output, full gates, Docker health, and browser evidence. |
| P15-REG-01 | 11.2, 12, 13.4, 24, 27 | Confirmation, exact dedupe, explicit evaluation, scoring, deletion, SQLite authority, and Agent topology remain unchanged. | Existing focused/full suites and changed-path review. |

## Prerequisites

| Producer or environment | Required artifact/contract | Gate before implementation |
|---|---|---|
| Plan_14 | Completed intent-aware current-message confirmation and direct URL/text compatibility | Run the existing focused Agent/job-tool confirmation tests; do not edit Agent graph or confirmation UI for this phase. |
| Approved design | `docs/superpowers/specs/2026-07-21-jd-extraction-quality-guard-design.md` at commit `664b6f3` | Confirm the schema/model/non-goals and exact guard/re-extraction contracts remain approved. |
| Existing extractor | Strict `ExtractedJobPost`, provider retry owner, one schema repair, and `JobPostExtraction` projection | Record a red semantic-guard case before changing production extraction. |
| Existing taxonomy | `SkillNormalizer` and production seed aliases/relationships | Reuse it as the sole canonical identity owner; do not add a parallel alias store. |
| Existing persistence/graph | SQLite `job_posts.updated_at`, evaluation-context derivation, `sync_job`, and rebuild instruction | Verify current revision/currentness and same-ID graph-sync behavior before adding CAS. |
| Existing saved-JD UI | Strict parsers, sidebar-local cache/action state, detail view, and dialogs | Preserve current evaluate/delete/raw-detail behavior and established Astryx components. |
| Local provider environment | Root `.env`, `.venv`, locked ShopAIKey model/configuration, and synthetic-only fixtures | Automated tests use fakes; the real provider is called only by the explicit bounded diagnostic. |

## Scope

- Strengthen the existing extraction prompt for direct source facts, verbatim
  responsibilities/evidence, atomic skill names, and explicit required versus
  preferred semantics.
- Add one pure deterministic JD extraction guard with the exact six issue codes,
  ordered bounded issues, punctuation-token exceptions, taxonomy-assisted
  atomicity checks, and canonical duplicate/group checks.
- Invoke the guard on provider output before final normalization. Reuse the
  existing single repair loop and provider retry limits with sanitized repair
  messages for both schema and semantic failures.
- Route new raw-text and URL-acquired content through the same guarded extractor
  without changing exact-hash return/retry or ordinary unscorable behavior.
- Add a focused re-extraction service and repository compare-and-swap operation
  for failed, unscorable, partial, or full retained Jobs. Only a new scorable
  result may replace the current processing result.
- Add the empty/extra-forbid public re-extraction request boundary, bounded
  response schema, safe error mapping, and post-commit graph-warning contract.
- Reuse the existing same-ID `sync_job` path and existing evaluation-context
  revision derivation; do not add graph or evaluation invalidation state.
- Render existing extraction metadata, responsibilities, required/preferred
  skills, confidence, experience, and expandable evidence in saved-JD detail.
- Add confirmation, in-flight locking, refresh, stale projection, graph warning,
  and failure-preservation behavior for **Re-extract JD**.
- Wire that action through the existing `ObservabilitySidebar` composition owner
  into `SavedJobsPanel`; keep `useSavedJobsState` as the sole saved-job action and
  cache owner and reuse the current graph-generation invalidation seam.
- Add synthetic fixtures, deterministic regressions, one explicit bounded
  provider diagnostic, full local gates, and a browser re-extraction smoke test.

## Out of Scope

- Changing `JobPostExtraction` or `JobSkill` fields; adding benefits, education,
  languages, compensation, employment type, qualifications, hiring stages, or a
  generic JD section/document model.
- Changing `gpt-4o-mini`, embedding model/dimensions, quality vocabulary,
  matching formula/weights, evaluation result contract, or taxonomy seed merely
  to improve the selected examples.
- Blindly splitting skill text on `/`, `,`, `;`, `|`, `and`, or another
  delimiter. The guard reports compounds and the provider performs the one
  bounded repair.
- Dropping, moving, or silently rewriting an invalid field or choosing a winner
  for duplicate/cross-group skills.
- A second extractor/classifier model, document-first multi-pass JD pipeline,
  model benchmark/comparison, broad taxonomy expansion, or new dependency.
- Automatic/bulk re-extraction, startup migration, background job, outbox,
  worker, retry queue, sync-state machine, or automatic evaluation.
- Accepting replacement raw JD, source URL, extraction, embedding, quality, Job
  identity, or evaluation data from the re-extraction request.
- Changing passive-JD confirmation, Agent prompt/graph/tool topology, public CV
  behavior, exact duplicate identity, deletion ordering, or unrelated sidebar
  design.
- Redesigning observability composition, moving saved-job ownership out of
  `useSavedJobsState`, or adding a second/global saved-job state, cache, or graph
  invalidation path.
- Persisting/logging provider prompts/responses, raw guard values, embeddings,
  source text, evidence text, SQL/Cypher details, or secrets outside the current
  bounded saved-detail source/evidence response.

## Target Directory Structure

```text
backend/
  app/
    api/jobs.py                         # add thin re-extract route/error mapping
    graph/sync_job.py                   # reuse; change only if a regression proves a same-ID defect
    repositories/jobs.py               # atomic revision-checked replacement
    schemas/job_evaluations.py          # zero-field request and bounded response
    services/
      jd_extraction.py                  # prompt, guard orchestration, sanitized one repair
      jd_extraction_guard.py            # new pure deterministic semantic guard
      jd_ingestion.py                   # shared guarded path; preserve ingestion semantics
      job_reextraction.py               # new staged extraction/CAS/sync coordinator
      saved_jobs.py                     # public projection/error adapter
      skill_normalization.py            # reuse only; no second taxonomy owner
  tests/
    fixtures/jd_extraction_golden.json  # synthetic English/Vietnamese cases only
    unit/
      test_jd_extraction_guard.py
      test_jd_extraction.py
      test_skill_normalization.py
    integration/
      test_job_ingestion.py
      test_jobs_repository.py
      test_job_reextraction.py
      test_saved_jobs_api.py
      test_job_sync.py
frontend/src/
  features/jobs/
    api.ts
    JobReextractDialog.tsx              # new confirmation dialog
    SavedJobDetail.tsx
    SavedJobsPanel.tsx
    savedJobsState.ts
    types.ts
  features/observability/
    ObservabilitySidebar.tsx            # wire existing saved-job owner/action only
  test/
    observability-sidebar.test.tsx
    saved-jobs-api.test.ts
    saved-jobs-panel.test.tsx
    saved-jobs-state.test.tsx
infrastructure/scripts/
  diagnose_jd_extraction.py             # new explicit synthetic provider check
docs/
  acceptance/manual_jd_checklist.md     # append dated Plan 15 evidence only
  plans/Plan_15.md
README.md                                # document the explicit diagnostic command
```

Product files outside this tree are protected. The listed observability files
are limited to saved-job action wiring and its regression coverage; no
observability redesign is authorized. `backend/app/graph/sync_job.py`,
`backend/app/services/skill_normalization.py`, and existing test files change
only when the new red tests prove a required compatibility seam; their current
public ownership remains authoritative.

## Technical Specifications

### Locked schema and provider boundary

- Keep the current `ExtractedJobPost` provider schema and final
  `JobPostExtraction`/`JobSkill` schemas unchanged. Do not add `jd_quality` or
  canonical taxonomy fields to provider output.
- Keep `ShopAIKeyStructuredJdInvoker`, strict structured output, `gpt-4o-mini`,
  shared provider retry owner, and `_MAX_REPAIR_ATTEMPTS == 1`.
- Update the system prompt with the seven approved rules: direct support for
  title/company/location; source-verbatim responsibilities; one atomic skill per
  row; protected punctuation names; mandatory/neutral is required; preferred
  requires explicit optional/preferred wording; canonical uniqueness/disjoint
  groups; evidence is short and verbatim.
- The complete raw JD remains only in transient extraction messages. No prompt,
  provider output, source value, or evidence body enters logs or durable state
  beyond the already validated extraction fields.

### Pure guard contract

- `jd_extraction_guard.py` has no provider, database, embedding, graph, logging,
  FastAPI, or UI imports. It accepts the retained raw JD, validated provider
  structure, and the existing `SkillNormalizer`/approved taxonomy view only for
  deterministic inspection; it never mutates either input.
- Source comparison is exactly Unicode NFKC, collapse all whitespace runs to one
  space, trim, then Unicode `casefold`. It does not strip punctuation,
  transliterate, stem, or perform fuzzy matching.
- Every non-blank skill evidence snippet and responsibility must occur in the
  normalized source. Every non-null title, company, and location must occur.
  Summary is not substring-checked. Seniority, work mode, and experience remain
  schema-constrained facts covered by fixtures/acceptance, not a new heuristic.
- Exact approved taxonomy display names/aliases are atomic. An unknown label is
  `COMPOUND_SKILL_LABEL` when it contains at least two standalone approved
  aliases, an approved alias plus non-resolving qualifier words, or an
  enumeration delimiter joining distinct skill-like terms.
- A small explicit exception set protects `C/C++`, `.NET`, `Node.js`, and
  `CI/CD`. It supplies no canonical key, alias, category, or relationship. An
  unknown label that is otherwise atomic remains valid and follows the current
  unknown-key normalization path.
- Tentatively normalize labels only to inspect canonical identity. Keys must be
  unique inside required and preferred lists and disjoint between them. The
  guard neither returns normalized output nor chooses a group winner.
- Issues are ordered by provider field order and index, then stable rule order.
  The vocabulary is exactly `EVIDENCE_NOT_IN_SOURCE`,
  `RESPONSIBILITY_NOT_IN_SOURCE`, `METADATA_NOT_IN_SOURCE`,
  `COMPOUND_SKILL_LABEL`, `DUPLICATE_SKILL`, and `SKILL_GROUP_CONFLICT`.
  Each issue contains only code, field path, and safe structural counts.

### Repair and failure boundary

- Schema validation failure uses a generic safe repair instruction that names
  the expected schema but contains no invalid value, provider payload, or raw
  exception string. Guard failure passes at most the first 20 ordered safe
  issues plus one omitted-count integer.
- The repair prompt restates atomic labels and mandatory/default-required versus
  explicit-preferred semantics. It does not echo raw source or evidence values;
  the transient JD message already contains the source.
- One first-call schema/guard failure consumes the same single repair attempt.
  Provider retry behavior remains owned by `invoke_with_provider_retry` for each
  allowed call. A second invalid result raises the existing
  `INVALID_STRUCTURED_OUTPUT` with a fixed safe message.
- Only after guard acceptance does `extracted_to_job_post` perform final
  `SkillNormalizer` projection. Then and only then may quality, embedding,
  persistence, graph, or scoring owners run.

### Ordinary ingestion compatibility

- Text and URL flows call the same guarded `extract_job_post_from_text`; do not
  fork guard behavior by source type or add a second extraction entry point.
- Existing non-failed exact hashes return their retained Job without extraction,
  guard, embedding, graph sync, or evaluation. Existing failed-row retry keeps
  its current identity and uses the guarded pipeline once accepted.
- Ordinary new/retry ingestion may still persist a truthful validated
  `unscorable` result under the current quality rules. The stricter `full|partial`
  acceptance applies only to replacement of a retained Job.

### Re-extraction transaction and service

1. Load the exact Job by ID, copy the immutable working snapshot, and capture
   `updated_at`. Reject unknown ID or blank/missing retained `raw_content` with a
   safe error before any provider call.
2. Outside any transaction, run the guarded extractor, existing normalizer and
   quality classifier, then build embedding text and call the locked embedding
   provider only when quality is `full` or `partial`.
3. Reject `unscorable` as `JOB_NOT_SCORABLE`. Do not mutate the Job, graph, or
   evaluation rows.
4. Open one short SQLite transaction. The repository executes one conditional
   update where `id` and captured `updated_at` both match, replacing only
   `processing_status='processed'`, `extraction_json`, `jd_quality`, null
   `failure_code`, the complete embedding triplet, and `updated_at`.
5. Set the new revision strictly later than the captured revision (UTC now, or
   captured revision plus one microsecond when needed) so currentness cannot
   remain accidentally equal. A zero-row update raises
   `JOB_REEXTRACT_CONFLICT`; do not retry or overwrite.
6. Preserve `id`, `source_type`, `source_url`, `raw_content`,
   `raw_content_hash`, `created_at`, and all evaluation rows. Reload/validate the
   committed Job before returning from the persistence boundary.
7. After commit, use the existing idempotent `sync_job` for that same Job ID.
   Success returns `sync_ok=true`. Failure keeps SQLite truth and returns
   `sync_ok=false`, `NEO4J_SYNC_FAILED`, and the existing rebuild instruction.

Provider, guard, normalization, quality, embedding, transaction, and conflict
failures leave the exact prior durable Job and evaluation currentness unchanged.
The coordinator makes no call to `evaluate_job`, matching, or evaluation
repositories.

### Evaluation and graph invariants

- Reuse the existing evaluation-context hash input
  `job_posts.updated_at`. Do not add an invalidation column/table/cache key and do
  not edit historical `job_evaluations` rows.
- Tests must begin with one current evaluation, perform successful re-extraction,
  and prove that the same row becomes `stale` through normal list/detail
  projection with zero evaluation-provider/scoring calls.
- `sync_job` continues to replace only the same Job's metadata and
  `REQUIRES`/`PREFERS` edges. Shared Skills, seed `RELATED_TO`, Candidate/CV
  branches, and unrelated Jobs remain unchanged. No graph deletion precedes the
  SQLite commit.

### Public API contract

- Add `POST /api/jobs/{job_id}/reextract`. Absent or empty JSON is allowed; a
  zero-field `extra='forbid'` request boundary (or equivalent strict boundary)
  rejects raw JD, URL, extraction, embedding, quality, evaluation, and arbitrary
  fields with `422` before the service call.
- HTTP 200 validates exactly as `ReextractJobResponse`: `outcome='updated'`,
  one current `SavedJobListItem`, `sync_ok`, `code`, and
  `rebuild_instruction`. `sync_ok=true` requires both optional fields null;
  `sync_ok=false` requires `code='NEO4J_SYNC_FAILED'` and non-blank safe rebuild
  guidance.
- Every pre-commit failure uses `detail={code, summary}` and no success model.
  Add `JOB_REEXTRACT_CONFLICT`; reuse the existing
  `JD_SOURCE_NOT_RECOVERABLE`, `JOB_NOT_FOUND`, `JOB_NOT_SCORABLE`, extraction
  provider/validation, and embedding codes with path-appropriate safe summaries
  and current HTTP mapping conventions.
- Route/service logs may contain Job ID, outcome code, and counts only. They may
  not contain request bodies, raw source, extraction/evidence, provider payload,
  embedding, prompt, SQL/Cypher, rebuild internals, or secrets.

### Saved-JD detail and action

- Keep strict parsing in `types.ts`; add strict parsing for the response coupling
  above. Never coerce malformed `sync_ok`/code/rebuild combinations.
- Render four bounded groups in `SavedJobDetail.tsx`: metadata; ordered
  responsibilities; required skills; preferred skills. Metadata includes title,
  company, summary, seniority, experience range, location, work mode, and
  extraction confidence. Skills use canonical display labels and confidence.
- Evidence is collapsed by default behind an accessible control and preserves
  backend order. Empty responsibility/skill/evidence states render concise
  explicit text rather than disappearing. Raw source stays in its existing
  bounded section.
- `JobReextractDialog.tsx` names the selected Job and states the four approved
  consequences: identity/raw source preserved; pre-commit failure preserves the
  current extraction; success makes an existing evaluation stale; evaluation is
  not automatic. Confirm and cancel are keyboard/focus safe.
- Extend the existing per-Job action union/state with `reextract`; one action per
  Job is allowed in flight. No optimistic extraction patch is permitted. On
  success, patch/refresh the compact row, refetch selected detail, refresh
  currentness, and invalidate graph projection. A graph-warning success still
  refreshes SQLite-backed views. On failure, preserve current list/detail data
  and show only the safe summary.
- `ObservabilitySidebar.tsx` continues to instantiate the sole
  `useSavedJobsState` owner. It passes that owner's re-extraction action into
  `SavedJobsPanel` and reuses the existing saved-job success effect so a
  successful replacement refreshes list/detail/evaluation currentness and bumps
  graph generation. Do not introduce a second hook instance, context, store,
  cache, request path, or observability-specific re-extraction implementation.

### Synthetic corpus and diagnostic

- `jd_extraction_golden.json` contains only repository-authored synthetic English
  and Vietnamese text. It covers one-line and sectioned forms, direct metadata,
  compound alternatives, punctuation-bearing names, neutral/mandatory/preferred
  wording, duplicates/cross-group output fakes, missing-source facts, and
  contact-only content.
- Deterministic tests may inject invalid provider output but never call the
  network. Expected assertions are field facts/invariants, not a broad scoring
  metric or model ranking.
- `diagnose_jd_extraction.py` is an explicit finite command over the approved
  live subset of the fixture. It uses the configured locked provider, the real
  guarded extractor, no persistence/embedding/graph/evaluation call, prints only
  case IDs and pass/fail safe summaries, and exits non-zero on any invariant
  failure. It never prints source, evidence, provider payload, or prompt.

## Implementation

1. Run the current extraction/ingestion/saved-JD baseline and record a clean
   starting status. Add failing unit cases that current code accepts: invented
   evidence/responsibility/metadata, compound/qualified taxonomy labels,
   duplicate canonical skills, and cross-group conflicts.
2. Add the synthetic fixture and implement the pure guard test-first. Prove the
   normalization representation, punctuation exceptions, unknown-atomic
   acceptance, deterministic issue ordering, exact vocabulary, and 20-issue cap.
3. Add failing extractor tests for prompt rules, guard-before-normalization,
   sanitized schema/guard repair, exact first/repair call counts, second-invalid
   failure, provider retry caps, and absence of raw values in messages/logs other
   than the existing transient source message.
4. Integrate the guard into `jd_extraction.py` with the smallest change. Run the
   focused extractor/normalizer/quality tests before touching persistence.
5. Add failing text/URL ingestion and exact-dedupe regression tests, then route
   both processing branches through the accepted guarded extractor without
   changing ordinary quality or terminal-state behavior.
6. Add repository RED tests for successful conditional replacement, strict field
   ownership, revision advance, failed/unscorable source states, and a zero-row
   concurrent update. Implement the single compare-and-swap operation.
7. Add service RED tests for the full staged success/failure matrix and
   evaluation/graph spies. Implement `job_reextraction.py`, reuse existing
   embedding and `sync_job` owners, and prove no transaction spans provider or
   embedding work.
8. Add response/request schemas, saved-job projection adapter, route, error map,
   and API tests. Reject replacement fields and verify HTTP 200 graph partial
   success separately from all pre-commit errors.
9. Add frontend RED tests for strict response parsing, full extraction rendering,
   empty states, collapsed evidence, dialog copy/focus, action lock, cancel,
   success refresh/stale state, graph warning, and failure preservation. Implement
   the smallest changes inside `frontend/src/features/jobs/`, then wire the
   existing state action through `ObservabilitySidebar.tsx`. Add a focused
   sidebar regression proving list/detail/currentness refresh and graph-generation
   invalidation without a second state owner.
10. Add the explicit provider diagnostic and run it against synthetic fixtures.
    Then run focused/full backend and frontend gates, shared plan validation,
    changed-path review, and diff checks.
11. Rebuild/start the normal Docker stack and perform one desktop browser smoke
    with a retained synthetic JD and existing evaluation. Record stable Job/raw
    identity, refreshed structured fields, stale-without-evaluate state, graph
    consistency/rebuild behavior, network calls, console, and sanitized logs.
12. Document the explicit bounded diagnostic command in `README.md` and append
    dated attempt-specific evidence to the existing manual checklist. Any later
    product/test/config change invalidates and reruns affected gates.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Pre-change RED | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction_guard.py tests/unit/test_jd_extraction.py -q` | New semantic cases fail for the intended missing-guard reasons before production edits. |
| Focused backend | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction_guard.py tests/unit/test_jd_extraction.py tests/unit/test_skill_normalization.py tests/unit/test_jd_quality.py tests/integration/test_job_ingestion.py tests/integration/test_jobs_repository.py tests/integration/test_job_reextraction.py tests/integration/test_saved_jobs_api.py tests/integration/test_job_sync.py -q` | Guard, repair caps/redaction, ordinary ingestion/dedupe, CAS/failure preservation, stale evaluation, API, and same-ID graph sync pass. |
| Backend static/full | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q` | Full backend is green with fake providers and no schema/topology regression. |
| Focused frontend | `Set-Location frontend; npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-panel.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-sidebar.test.tsx` | Strict response/error parsing, full detail, dialog/action, sidebar wiring, list/detail/currentness refresh, graph-generation invalidation, warning, and preservation pass without a second state owner. |
| Frontend static/full | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Full frontend suite and production build pass without shell/layout regressions. |
| Synthetic provider diagnostic | `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_jd_extraction.py --cases backend/tests/fixtures/jd_extraction_golden.json` | Every approved live case reports only case ID/pass status and satisfies metadata, atomicity, group, grounding, and quality invariants; no source/provider text is printed. |
| Plan structure | `& '.\.venv\Scripts\python.exe' 'C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py' 'docs/plans' --json` | Contiguous Plans 1-15; Plans 1-14 hand off normally and only Plan 15 is terminal. |
| Docker health | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180` then `Invoke-RestMethod http://127.0.0.1:8000/api/health` | Backend/frontend/Neo4j and overall SQLite/filesystem health are ready on the candidate build. |
| Browser re-extraction | Open `http://localhost:5173/`; select a retained synthetic JD with a current evaluation; inspect all extraction groups; confirm **Re-extract JD** once. | Same Job ID/source/raw hash, refreshed detail, evaluation becomes stale, no evaluate request, same-ID graph projection is current or explicit rebuild guidance appears, and no console/raw-log leak occurs. |
| Failure browser check | Use a controlled fake/API seam or retained non-recoverable synthetic row; trigger one pre-commit failure. | Dialog unlocks, previous extraction/evaluation display remains, safe error is visible, and no optimistic state or graph/evaluate call occurs. |
| Scope hygiene | `git diff --check; git status --short` plus changed-path and secret/runtime-data review | Only Plan 15 owners/tests/fixtures/diagnostic/evidence change; no model/schema/weight/dependency/Agent/CV/unrelated cleanup is introduced. |

The live-provider diagnostic and browser checks are mandatory release evidence;
schema-only fake tests are not sufficient proof of semantic extraction quality.
Never place real or proprietary JD text in fixtures, logs, screenshots, or the
acceptance ledger.

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Master Version 2.0 | Guarded extraction, retained-JD CAS, public response, UI, failure, and verification requirements | Version 2.0 remains the architecture authority for this increment. |
| Plan_14 | Intent-aware passive confirmation, exact durable source binding, and unchanged direct URL/text behavior | Plan 15 does not edit Agent topology or confirmation ownership. |
| Approved design | `docs/superpowers/specs/2026-07-21-jd-extraction-quality-guard-design.md` | Schema/model/non-goals and safe failure semantics remain fixed. |
| Existing runtime | Extractor/normalizer/quality/embedding/SQLite/graph/evaluation/saved-detail owners | Existing owners are extended or reused without a parallel pipeline. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Saved-JD ingestion and matching | Source-grounded atomic extraction accepted before normalization and scoring | Guard/repair/ingestion tests and bounded synthetic provider diagnostic. |
| Retained-JD user flow | Same-ID safe re-extraction with CAS preservation, stale evaluation projection, and truthful graph partial success | Repository/service/API tests plus browser success/failure evidence. |
| Saved-JD UI | Complete existing extraction rendering and accessible non-optimistic action | Parser/state/component tests and desktop browser inspection. |
| Release handoff | Validated terminal incremental portfolio and candidate evidence | Full gates, Docker health, plan validator, acceptance ledger, and scope/diff review. |

## Completion Contract

Plan 15 is complete only when the locked single-pass extractor rejects every
ungrounded guarded fact, compound skill label, canonical duplicate, and
required/preferred conflict before normalization or downstream work; it permits
the approved punctuation tokens and unknown atomic skills; and it uses at most
one sanitized repair with the exact bounded issue vocabulary. Text and URL
ingestion share this boundary, while exact non-failed duplicates remain
provider-free and ordinary truthful unscorable ingestion remains compatible.

The public re-extraction action must reload retained source by Job ID, stage all
provider/embedding work outside a transaction, atomically replace only a
`full|partial` result under the captured revision, preserve identity/source/raw
fields, and leave the previous durable truth untouched on every pre-commit
failure. Successful replacement must make existing evaluations stale solely
through `job_posts.updated_at`, make zero evaluation calls, and synchronize the
same Job identity. A post-commit graph failure must return HTTP 200 partial
success with `NEO4J_SYNC_FAILED` and safe rebuild guidance while SQLite remains
truth.

Saved-JD detail must visibly render metadata, experience, extraction confidence,
ordered responsibilities, distinct required/preferred skills, and collapsed
grounded evidence with explicit empty states. The confirmation/action must be
accessible, locked while pending, non-optimistic, truthful on partial success,
and preserving on failure. It must be wired through the existing
`ObservabilitySidebar` composition while `useSavedJobsState` remains the sole
saved-job state/cache owner and the existing graph-generation invalidation seam
remains authoritative; no observability redesign or second state path is
allowed. Focused and full backend/frontend gates, static
checks, the contiguous plan validator, Docker health, bounded synthetic
live-provider diagnostic, browser success/failure evidence, and final scope/diff
review must all pass on the same candidate. No product schema field, provider
model, embedding/scoring contract, taxonomy owner, dependency, Agent topology,
blind splitter, background workflow, bulk repair, automatic evaluation, real JD
fixture, raw-data leak, or unrelated refactor may be introduced.
