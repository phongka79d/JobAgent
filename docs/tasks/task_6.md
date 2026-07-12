# JobAgent Plan 6 Phase 5 Execution Tasks

## Purpose

Execute Master Phase 5 as reviewable units that embed the approved Candidate
through the locked redaction/provider boundary, retrieve only active scorable
Jobs from the derived Neo4j index, join canonical SQLite state, compute and
explain deterministic hybrid scores, expose the seventh Agent tool and bounded
match cards, and evaluate the locked system without tuning on held-out data.
The phase stops before release hardening or any new provider, model, route,
event, data store, crawler, reranker, or product workflow.

## Project Context Notes

- Root `README.md` was read completely. It records Plan 5 Batches 01-06 as
  evidence-backed and exposes the stable Phase 4 seams consumed here.
- SQLite remains the sole canonical application source of truth. Neo4j is a
  derived, fully rebuildable Job/Skill/JobFamily graph and 1536-dimension cosine
  vector index; retrieval output is joined back to validated SQLite Jobs before
  scoring.
- Plan 5 already owns versioned `job_embedding_text_v1` construction,
  `JobEmbeddingService`, active `full|partial` Job eligibility, shared
  Candidate/Job `SkillRef` normalization, identifier-only graph outbox work,
  and Job graph/rebuild parity. Plan 6 extends these seams instead of replacing
  them.
- The approved singleton Candidate Profile and Job Preferences are available
  through `ProfileRepository` and `PreferencesRepository`. Candidate text must
  pass through the existing deterministic `redact_pii` boundary before the
  existing embedding adapter is called.
- The current repository has six production tools, seven public application
  routes, eight SSE event names, and one final-message/history
  `structured_payload` seam. Plan 6 adds only `match_jobs` and a bounded match
  payload within those existing transport boundaries.
- `JobPost.score_cache` and compact `query_jobs` score-detail exposure already
  exist. Any score-cache write must remain derived, versioned, bounded, and
  validated; it must not store raw CV/JD content, vectors, or provider data.
- Existing Phase 0 evaluation code already owns reusable nDCG, latency,
  embedding-validation, seeded-split, and held-out guard patterns. Plan 6
  refactors/reuses those primitives rather than duplicating metric logic.
- `backend/evaluation/private/` and local-private label/fixture paths are already
  gitignored. Committed evaluation material is limited to schemas, annotation
  templates, synthetic fixtures, locked configuration, aggregate metrics, and
  limitations.
- Plan 6's unchecked prerequisite markers describe capability/runtime
  preconditions, not missing Plan 5 implementation. Normal automated tests
  create approved profiles and scorable Jobs in temporary stores. The real
  150-200-JD relevance corpus, 30 annotated extraction cases, 50 tool scenarios,
  and any real redacted Candidate input remain user-owned local inputs.
- The worktree was clean when this task file was authored, and
  `docs/tasks/task_6.md` did not previously exist; there was no accepted Plan 6
  progress to preserve.
- The user-provided root rules require search-before-write, caller inspection
  for shared behavior, reuse before addition, focused modules, no duplicated
  business logic, root-cause fixes, and the shortest source-compliant diff.
- `frontend/AGENTS.md` requires Astryx CLI discovery before UI work, the
  existing `AppShell` frame, documented component props, token-based styling,
  and no raw layout `div` elements or guessed APIs.
- Backend quality commands run from `backend/`:
  `python -m ruff check app tests`, `python -m mypy app`, and
  `python -m pytest -q`. Frontend commands run from `frontend/`:
  `npm run check:astryx`, `npm run lint`, `npm run typecheck`,
  `npm run test -- --run`, and `npm run build`.
- Normal automated validation uses injected embedding/Neo4j/Agent fakes and
  temporary SQLite. It never calls real ShopAIKey, requires live Neo4j, reads
  private evaluation data, or exposes secrets or document bodies.

## Authority and Scope

### Primary Source

`docs/plans/Plan_6.md` is the user-named primary source. Its objective, scope,
technical specifications, implementation steps, verification plan, and Plan 7
handoff are authoritative. Referenced sections of
`docs/plans/Master_plan.md`, the accepted Plan 5 handoff, root `README.md`, and
repository evidence refine executable boundaries without expanding Phase 5.

### Source Section Index

- `docs/plans/Plan_6.md` > `## 1. Objective` -> complete measurable matching
  outcome.
- `docs/plans/Plan_6.md` > `## 4. Scope` -> mandatory retrieval, scoring,
  explanation, tool, evaluation, and presentation work.
- `docs/plans/Plan_6.md` > `## 5. Out of Scope` -> prohibited scoring,
  provider, collection, product, and tuning expansions.
- `docs/plans/Plan_6.md` > `## 6. Target Directory Structure` -> focused
  service/schema/evaluation/UI ownership.
- `docs/plans/Plan_6.md` > `### 7.1 Retrieval representations` -> versioned
  Candidate text, PII gate, outbox retry, top-50 vector query, and SQLite join.
- `docs/plans/Plan_6.md` > `### 7.2 Skill score` -> direct/alias/verified-related
  precedence, coverage, missing skills, and evidence.
- `docs/plans/Plan_6.md` > `### 7.3 Non-skill components` -> exact normalized
  component rules and unavailable states.
- `docs/plans/Plan_6.md` > `### 7.4 Hybrid aggregation` -> seed weights,
  renormalization, quality multiplier, stable sort, and top-10 limit.
- `docs/plans/Plan_6.md` > `### 7.5 Match result contract` -> bounded result and
  explanation fields.
- `docs/plans/Plan_6.md` > `### 7.6 Evaluation protocol` -> private datasets,
  sealed tuning/evaluation, ablations, graph decision, and thresholds.
- `docs/plans/Plan_6.md` > `## 9. Verification & Testing Plan` -> unit,
  integration, frontend, split, ablation, privacy, and exit evidence.
- `docs/plans/Plan_6.md` > `## 10. Handoff Notes for Plan 7 (Master Phase 6)` ->
  stable locked outputs and prohibited retuning.
- `docs/plans/Master_plan.md` > `## 7. Pydantic Data Contracts` through
  `## 9. Skill Normalization` -> canonical Candidate/Job/Skill evidence and
  graph-trust rules.
- `docs/plans/Master_plan.md` > `### 13.6 query_jobs` and
  `### 13.7 match_jobs` -> exact Agent-facing read/match responsibilities.
- `docs/plans/Master_plan.md` > `### 14.2 SSE contract` and
  `### 15.5 Match result card` -> unchanged event union and visible result
  fields.
- `docs/plans/Master_plan.md` > `## 17. Embedding and Retrieval` and
  `## 18. Matching Formula` -> locked provider/text/retrieval/scoring contract.
- `docs/plans/Master_plan.md` > `## 19. Evaluation Plan` -> data policy,
  fixed split, labels, scenarios, metrics, and thresholds.
- `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` through
  `## 24. Local Testing Strategy` -> bounded failures, outbox retry, privacy,
  local-only configuration, and fake-backed test obligations.
- `docs/plans/Master_plan.md` >
  `### Phase 5 — Matching, explanation, and evaluation` -> mandatory phase
  tasks and exit gate.
- `README.md` > `## Plan 6 handoff (Master Phase 5) — stable seams only` and
  `docs/plans/Plan_5.md` >
  `## 10. Handoff Notes for Plan 6 (Master Phase 5)` -> accepted Phase 4
  primitives and Plan 6 ownership limits.
- `docs/plans/Plan_7.md` > `## 3. Prerequisites from Prior Phases` -> evidence
  that Plan 6 must hand to release hardening.

### Approved Architecture and Constraints

- Reuse the locked `text-embedding-3-small`/1536/float/no-prefix adapter and
  `job_embedding_text_v1`. Add a versioned Candidate representation only; do
  not add another provider client, model, dimension, local runtime, or reranker.
- Candidate text contains only target roles, profile summary, verified
  non-excluded skills, experience titles, and preferences in deterministic
  order. Redact it before any external call; redaction failure makes zero
  provider calls.
- Before each match, perform one visibly bounded retry of pending graph work.
  If Neo4j remains unavailable, return a structured sanitized failure and never
  claim matches.
- Neo4j returns no more than 50 Job IDs, cosine similarities, and verified
  relationship evidence. SQLite reloads and validates current records; only
  active, processed, `full|partial`, non-ignored Jobs may score.
- Restrict optional saved-job filtering to an explicit bounded list of existing
  Job IDs (maximum 50). This is the narrow source-supported interpretation that
  avoids inventing new search/filter semantics and composes with existing
  `query_jobs`.
- Direct canonical and verified aliases score 1.0, verified `RELATED_TO` paths
  score 0.6, and provisional/unverified/no paths score 0.0. Strongest-match
  precedence is deterministic and evidence never includes raw documents.
- Implement each non-skill component exactly as specified. Unavailable is
  distinct from zero; remove unavailable components and renormalize effective
  weights before applying `full=1.00` or `partial=0.85`.
- Seed weights are versioned configuration, not optimality claims. Numerical
  scores and explanations are deterministic; no LLM produces or adjusts them.
- Sort by final score descending and stable Job-ID ascending tie-break; return
  at most 10 results with component values/effective weights and bounded
  matched/related/missing evidence.
- Derived score cache may contain only the validated versioned match result
  subset needed by `query_jobs`. SQLite profile/Job facts remain canonical and
  no schema migration is authorized unless a source-required incompatibility
  is proven.
- Register exactly seven production tools after `match_jobs`. Keep exactly
  seven public routes, the eight existing SSE event names, one LangGraph, and
  the existing final-message/history structured-payload transport.
- Match cards reuse Astryx `Card`/`MetadataList`/`Collapsible`/`ProgressBar`
  through documented APIs. They do not add a dashboard or separate screen.
- Local private inputs are never committed. A deterministic seeded 60/20/20
  split is sealed before tuning; grid search reads development/validation only,
  chosen weights are locked before exactly one held-out evaluation, and test
  labels cannot be used to change weights/prompts/thresholds.
- Evaluate the five locked ablations. Disable related-skill boosts when graph
  expansion fails to improve held-out `nDCG@10`; report failures and limitations
  honestly without changing thresholds or adding fallback features.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Safe versioned Candidate representation and canonical top-50 retrieval | (01A), (01B) | Accepted Plan 5 handoff |
| Batch02 | Deterministic score components, aggregation, and explanations | (02A), (02B), (02C) | Batch01 |
| Batch03 | Seventh Agent tool and bounded backend match payload | (03A), (03B) | Batch02 |
| Batch04 | Astryx top-result presentation on the existing chat surface | (04A) | Batch03 |
| Batch05 | Privacy-safe sealed evaluation datasets and runners | (05A), (05B), (05C) | Batch04 |
| Batch06 | Locked evaluation evidence, Phase 5 exit proof, and Plan 7 handoff | (06A), (06B) | Batch05 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_6_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_6_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.
- In orchestrated mode A1 execution and repair run on Grok unless the user sets
  `A1_RUNTIME: codex`. Codex writes `.agent/handoff/a1_request.md` and invokes
  `python $env:USERPROFILE\.codex\skills\orchestrator-agent\scripts\run_a1_grok.py --cwd <REPO> --envelope-file .agent\handoff\a1_request.md`;
  A2, A3, commit control, and next-batch approval remain on Codex.

## Mandatory Batch01 - Safe Matching Inputs and Canonical Retrieval

### Goal

Produce one deterministic redacted Candidate vector and retrieve at most 50
eligible Job candidates whose scoring facts are revalidated from SQLite.

### Dependencies

Accepted Plan 5 embedding, profile/preference repository, Job graph, outbox, and
active/scorable Job contracts.

### Scope Boundary

This batch owns matching schemas, Candidate text/vector construction, bounded
graph retrieval, and canonical-state join only. It does not implement score
formulas, explanations, tools, chat payloads, UI, tuning, or evaluation runs.

### Tasks

- [x] (01A): Build a versioned redacted Candidate embedding representation
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.1 Retrieval representations`; `docs/plans/Plan_6.md` > `## 5. Out of Scope`; `docs/plans/Master_plan.md` > `### 17.1 Locked embedding contract`; `docs/plans/Master_plan.md` > `### 17.3 Text representations`
  - Source Requirements:
    - Deterministically represent target roles, profile summary, verified non-excluded skills, experience titles, and preferences with the locked no-prefix normalization.
    - Reuse `JobEmbeddingService` and `job_embedding_text_v1`; add no provider/model/dimension stack.
    - Apply `redact_pii` before the Candidate embedding call and fail closed with sanitized codes on redaction/provider failure.
  - Dependencies: Accepted `ProfileRepository`, `PreferencesRepository`, `redact_pii`, and `JobEmbeddingService`
  - User Action: None
  - Agent Work:
    1. Search every embedding/text/redaction/profile caller and reuse the existing normalization, vector validation, error, and adapter paths; split focused text-building code if extending `embeddings.py` would deepen its existing broad responsibility.
    2. Define strict matching input/result primitives and a versioned Candidate text builder with stable field/list ordering, verified/non-excluded skill selection, bounded text, and no contact or storage fields.
    3. Compose redaction and the existing generic embedding call so redaction failure occurs before client construction/request and every error remains code-only.
    4. Add encoding/order/bounds tests plus recording-fake tests proving exact model/dimensions/no-prefix behavior, unchanged Job text output, zero provider calls after redaction failure, and contact-sentinel absence.
  - Output: A validated Candidate embedding input/vector contract with explicit representation version and sanitized failure states.
  - Acceptance:
    - Equal approved profile/preferences produce byte-identical normalized Candidate text and exactly one validated 1536-float vector through the existing adapter.
    - Only verified, non-excluded Candidate skills enter text; no raw CV, contact PII, attachment path, provider payload, alternate model, or E5 prefix enters text/logs/errors.
    - Redaction failure makes zero fake-provider calls and returns no source text.
    - Existing Job embedding text and Job sync/rebuild tests remain green.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_matching_text.py tests/services/test_embeddings.py tests/services/test_pii_redaction.py` -> deterministic Candidate representation, fail-closed redaction, and unchanged Job adapter tests pass.
    - Required: `cd backend; python -m ruff check app/schemas/matching.py app/services/matching_text.py app/services/embeddings.py tests/services/test_matching_text.py tests/services/test_embeddings.py; python -m mypy app/schemas/matching.py app/services/matching_text.py app/services/embeddings.py` -> focused lint and strict typing pass.
  - Blocked Condition: Existing validated profile/preferences cannot supply a source-required representation field without changing an accepted schema; report `BLOCKED_BY_SOURCE_CONFLICT` and do not add duplicate profile state.
  - Files: `backend/app/schemas/matching.py`, `backend/app/services/matching_text.py`, `backend/app/services/embeddings.py`, `backend/tests/services/test_matching_text.py`, `backend/tests/services/test_embeddings.py`

- [x] (01B): Retrieve top-50 graph candidates and rejoin canonical SQLite Jobs
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.1 Retrieval representations`; `docs/plans/Plan_6.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 17.4 Retrieval flow`; `docs/plans/Master_plan.md` > `### 21.2 Processing`
  - Source Requirements:
    - Retry pending Job graph work once through the existing bounded processor before retrieval and fail without false success if Neo4j remains unavailable.
    - Query the existing cosine index for at most 50 active/scorable Job IDs and similarities, optionally restricted to at most 50 explicit saved Job IDs.
    - Reload canonical Job facts from SQLite by ID, discard stale/ineligible/ignored/unscorable rows, and never accept Neo4j properties as canonical state.
  - Dependencies: (01A) Candidate vector; accepted Job outbox/projector/vector index and `JobPostRepository`
  - User Action: None
  - Agent Work:
    1. Search all graph-client, Job eligibility, outbox, repository, rebuild, and query callers; reuse `fetch_records`, `process_job_sync_outbox`, and one shared eligibility predicate instead of duplicating graph/SQLite rules.
    2. Implement a parameterized fixed vector-query boundary with an exact 50 ceiling, finite clamped similarities, verified index identity, explicit saved-ID filter bounds, and sanitized Neo4j failures.
    3. Add one bounded repository bulk-read/join path only if needed; preserve Neo4j rank while filtering against current SQLite processing/record/quality/duplicate state.
    4. Add injected graph/SQLite tests for outbox success/failure, malformed/duplicate/stale IDs, over-limit results, filter bounds, ignored/unscorable exclusion, canonical-field precedence, and zero live services.
  - Output: An ordered tuple of at most 50 canonical scorable Job candidates with Job ID, clamped semantic similarity, validated extraction/quality, and only verified graph evidence needed later.
  - Acceptance:
    - The graph query is parameterized, returns at most 50 unique IDs, and never exposes vectors, secrets, raw content, or unbounded graph records.
    - A current SQLite row must be active, processed, non-ignored, and `full|partial` to survive; SQLite title/skills/status always override graph copies.
    - Pending work receives one bounded existing-processor attempt; Neo4j failure produces a sanitized failure with zero claimed matches.
    - Candidate ordering is deterministic and explicit saved-ID filters reject empty/duplicate-overflow or more than 50 IDs.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_retrieval.py tests/repositories/test_job_posts.py tests/graph/test_job_sync.py` -> retrieval, canonical join, exclusion, and retry matrix passes with fakes.
    - Required: `cd backend; python -m ruff check app/services/retrieval.py app/repositories/job_posts.py tests/services/test_retrieval.py tests/repositories/test_job_posts.py; python -m mypy app/services/retrieval.py app/repositories/job_posts.py` -> focused lint and strict typing pass.
  - Blocked Condition: The accepted Neo4j driver/index cannot return Job IDs and cosine similarities through the existing graph client, or a required canonical eligibility field is unavailable in SQLite; report `BLOCKED_BY_SOURCE_CONFLICT` without trusting graph state or adding another store.
  - Files: `backend/app/services/retrieval.py`, `backend/app/repositories/job_posts.py`, `backend/tests/services/test_retrieval.py`, `backend/tests/repositories/test_job_posts.py`

## Mandatory Batch02 - Deterministic Scoring and Explanations

### Goal

Convert canonical retrieved candidates into stable normalized score breakdowns,
evidence-backed explanations, and final top-10 ordering without an LLM score.

### Dependencies

Batch01 Candidate/Job retrieval contracts.

### Scope Boundary

This batch owns pure feature computation, aggregation, result schemas, and
explanation generation. It does not register tools, persist chat payloads,
render UI, tune weights, or read held-out evaluation data.

### Tasks

- [x] (02A): Compute direct, alias, and verified-related skill evidence
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.2 Skill score`; `docs/plans/Master_plan.md` > `### 8.4 Graph safety rules`; `docs/plans/Master_plan.md` > `### 18.1 Skill coverage`
  - Source Requirements:
    - Apply strongest-match precedence: direct canonical or verified alias 1.0, verified `RELATED_TO` 0.6, provisional/unverified/no match 0.0.
    - Compute required/preferred mean coverage with internal 0.80/0.20 renormalization and make skill score unavailable only when both lists are empty.
    - Identify matched, verified-related, and strength-zero missing required skills with bounded source evidence and no raw documents.
  - Dependencies: (01B) canonical Candidate/Job skills and verified graph evidence; accepted shared `SkillRef` normalization
  - User Action: None
  - Agent Work:
    1. Search normalization/seed/graph callers and reuse canonical keys and verified alias properties; inspect every `RELATED_TO` producer/consumer before adding the read-only verified-edge query.
    2. Implement pure strongest-path matching and coverage functions with stable deduplication/order and explicit typed evidence for direct, alias, related, provisional, and no-match cases.
    3. Restrict graph paths to `verified=true` and bounded evidence/source fields; never infer or persist relationships or boost provisional skills.
    4. Add table-driven unit tests for precedence, empty lists, alias collisions, bidirectional/duplicate related paths, excluded/provisional skills, evidence bounds, and required/preferred renormalization.
  - Output: A deterministic skill component containing availability, score, sub-coverages, and bounded matched/related/missing evidence.
  - Acceptance:
    - Direct/verified-alias matches always beat related paths; verified related paths contribute exactly 0.6; provisional/unverified paths contribute zero.
    - Empty one-side skill lists renormalize within the skill component; both empty makes it unavailable rather than zero.
    - Every missing required skill has strongest strength zero, and every related explanation names a verified bounded path.
    - No second normalization/ontology path or graph mutation is added.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_skill_matching.py tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py` -> precedence, coverage, and shared-normalization tests pass.
    - Required: `cd backend; python -m ruff check app/services/skill_matching.py app/services/skill_normalization.py tests/services/test_skill_matching.py; python -m mypy app/services/skill_matching.py app/services/skill_normalization.py` -> focused lint and strict typing pass.
  - Blocked Condition: Verified relationship status/source cannot be distinguished from provisional graph data; report `BLOCKED_BY_SOURCE_CONFLICT` and treat related boosts as disabled rather than trusting ambiguous edges.
  - Files: `backend/app/services/skill_matching.py`, `backend/app/services/retrieval.py`, `backend/tests/services/test_skill_matching.py`, `backend/tests/services/test_retrieval.py`

- [x] (02B): Compute non-skill components and renormalized hybrid scores
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.3 Non-skill components`; `docs/plans/Plan_6.md` > `### 7.4 Hybrid aggregation`; `docs/plans/Master_plan.md` > `### 18.2 Initial hybrid seed`; `docs/plans/Master_plan.md` > `### 18.3 Missing fields`
  - Source Requirements:
    - Implement semantic, seniority, experience, location, and work-mode rules exactly, returning `[0,1]` or unavailable.
    - Apply versioned seed weights 0.30/0.40/0.10/0.10/0.05/0.05, remove unavailable components, and renormalize effective weights to one.
    - Multiply only after aggregation by `full=1.00` or `partial=0.85`; unscorable never receives a final score.
  - Dependencies: (02A) skill component; (01B) canonical Candidate preferences and Job fields
  - User Action: None
  - Agent Work:
    1. Search existing normalization, quality, numeric validation, and score-cache code; reuse enum/token normalization and keep formulas in pure focused functions.
    2. Implement each component independently with unavailable distinct from zero, finite/clamped numeric handling, normalized location equality, and exact work-mode/seniority membership.
    3. Define one versioned immutable seed-weight configuration and pure aggregator that proves effective weights sum to one before the quality multiplier.
    4. Add boundary/property-style cases for unknowns, empty targets, zero/missing minimum experience, partial experience ratios, cosine extremes, all-unavailable input, invalid weights, and quality multipliers.
  - Output: A strict component/effective-weight breakdown and finite deterministic base/final score for each eligible Job.
  - Acceptance:
    - Every component matches Plan 6's binary/ratio/clamp/unavailable rule and never yields NaN, infinity, or an out-of-range value.
    - Available effective weights sum to one within a documented numeric tolerance; unavailable weights are absent, not silently zero-weighted.
    - Quality is applied after aggregation exactly once; `partial` multiplies by 0.85 and `unscorable` cannot enter aggregation.
    - Seed configuration is versioned and contains no tuned/held-out values.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_score_components.py tests/services/test_matching.py` -> component, renormalization, numeric, and quality cases pass.
    - Required: `cd backend; python -m ruff check app/services/score_components.py app/services/matching.py app/schemas/score_breakdown.py tests/services/test_score_components.py tests/services/test_matching.py; python -m mypy app/services/score_components.py app/services/matching.py app/schemas/score_breakdown.py` -> focused lint and strict typing pass.
  - Blocked Condition: A source-required Candidate or Job field has incompatible accepted enum semantics; report `BLOCKED_BY_SOURCE_CONFLICT` without guessing mappings or altering upstream extraction.
  - Files: `backend/app/services/score_components.py`, `backend/app/services/matching.py`, `backend/app/schemas/score_breakdown.py`, `backend/tests/services/test_score_components.py`, `backend/tests/services/test_matching.py`

- [x] (02C): Rank top 10 and generate bounded evidence-backed explanations
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.4 Hybrid aggregation`; `docs/plans/Plan_6.md` > `### 7.5 Match result contract`; `docs/plans/Plan_6.md` > `## 5. Out of Scope`
  - Source Requirements:
    - Return Job identity/display fields, final score, quality, every component/effective weight, matched/related/missing required skills, explanation lines, and safe public source URL.
    - Generate explanations deterministically from computed evidence; never use an LLM for numerical scores or unsupported claims.
    - Sort by descending final score with stable Job-ID tie-break and return at most 10.
  - Dependencies: (02A) skill evidence and (02B) hybrid breakdown
  - User Action: None
  - Agent Work:
    1. Search existing bounded Job display/source-URL validators and score-cache views; reuse them rather than duplicating card safety rules.
    2. Complete strict match-result schemas with size/count/text/URL/numeric bounds and a version/config identity suitable for derived cache and transport.
    3. Implement explanation lines from component values and explicit skill paths only, with deterministic ordering/truncation and no raw evidence bodies.
    4. Compose scoring for up to 50 inputs, stable-sort, cap the final result at 10, and add permutation/tie/bound/privacy tests.
  - Output: A versioned ordered `MatchResult` collection of at most 10 validated transparent results.
  - Acceptance:
    - Same canonical inputs/config produce identical JSON-compatible results and Job-ID tie order independent of input ordering.
    - Every visible claim is traceable to a component or bounded skill path; provisional paths and raw documents never appear.
    - Result, evidence, explanation, and URL bounds fail closed; no more than 10 results survive.
    - No model call, reranking, alternate vector lookup, or Job mutation occurs in the pure ranking/explanation layer.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_explanations.py tests/services/test_matching.py tests/schemas/test_matching.py` -> stable ranking, contract bounds, and evidence tests pass.
    - Required: `cd backend; python -m ruff check app/services/explanations.py app/services/matching.py app/schemas/matching.py app/schemas/score_breakdown.py tests/services/test_explanations.py tests/services/test_matching.py tests/schemas/test_matching.py; python -m mypy app/services/explanations.py app/services/matching.py app/schemas/matching.py app/schemas/score_breakdown.py` -> focused lint and strict typing pass.
  - Blocked Condition: Existing safe Job display/source URL contract cannot be reused without exposing prohibited fields; report `BLOCKED_BY_SOURCE_CONFLICT` and do not weaken transport privacy.
  - Files: `backend/app/services/explanations.py`, `backend/app/services/matching.py`, `backend/app/schemas/matching.py`, `backend/app/schemas/score_breakdown.py`, `backend/tests/services/test_explanations.py`, `backend/tests/services/test_matching.py`, `backend/tests/schemas/test_matching.py`

## Mandatory Batch03 - Agent Tool and Backend Match Payload

### Goal

Expose deterministic matching through the seventh production tool and the
existing bounded final-message/SSE/history seam.

### Dependencies

Batch02 stable matching service/result contract and accepted chat/tool
infrastructure.

### Scope Boundary

This batch owns `match_jobs` orchestration, derived score-cache/query exposure,
tool registration, and backend match payload transport. It adds no route, SSE
event, write approval, frontend component, evaluation tuning, or Job mutation.

### Tasks

- [x] (03A): Register match_jobs with profile, outbox, limit, and cache guards
  - Source of Truth: `docs/plans/Plan_6.md` > `## 4. Scope`; `docs/plans/Plan_6.md` > `### 7.1 Retrieval representations`; `docs/plans/Master_plan.md` > `### 13.6 query_jobs`; `docs/plans/Master_plan.md` > `### 13.7 match_jobs`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Require an approved profile, default to and cap at 10 results, validate optional saved Job IDs, retry pending graph work before retrieval, and return sanitized guidance/failure states.
    - Delegate embedding/retrieval/scoring/explanation to services; the tool contains no formulas.
    - Register exactly seven production tools and let bounded `query_jobs` expose validated score details only when already cached.
  - Dependencies: (02C) stable matching service/result; existing database, graph, embedding, outbox, `query_jobs`, and registry seams
  - User Action: None
  - Agent Work:
    1. Search all tool registry/startup/query/cache/chat callers and inspect every caller of shared repository methods before edits; reuse current service construction and code-only tool error conventions.
    2. Implement strict `MatchJobsInput` and a thin service/tool wrapper that loads approved profile/preferences, handles no-profile guidance, validates limit/IDs, runs the bounded outbox/retrieval/matching pipeline, and never reports success after failure.
    3. Persist only validated versioned derived score-cache details needed by `query_jobs` using caller-owned transactions; do not cache vectors, raw text, provider payloads, or failed/ignored/unscorable results.
    4. Register `match_jobs` as the seventh tool and add fake-backed tests for preconditions, limits, filters, retry/outage, duplicate calls, cache exposure, registry count, and unchanged seven-route inventory.
  - Output: One strict read-only `match_jobs` tool returning a sanitized top-result payload or stable guidance/error code, plus bounded cached score details readable by `query_jobs`.
  - Acceptance:
    - No approved profile returns upload/approval guidance with zero embed/graph/cache calls; Neo4j/redaction/provider failure returns no matches or false success.
    - Result limit defaults to 10, never exceeds 10, and saved-ID filters never exceed 50.
    - Production registry names are exactly the prior six plus `match_jobs`; public routes remain exactly seven.
    - `query_jobs` exposes only validated existing score details and never computes scores, returns raw JD/CV, or trusts stale/ineligible cache.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/tools/test_match_jobs.py tests/tools/test_query_jobs.py tests/tools/test_registry.py tests/agent/test_graph.py tests/api/test_chat.py` -> precondition, failure, cache, registry, and route tests pass with fakes.
    - Required: `cd backend; python -m ruff check app/tools/match_jobs.py app/tools/query_jobs.py app/tools/registry.py app/main.py app/repositories/job_posts.py tests/tools; python -m mypy app/tools/match_jobs.py app/tools/query_jobs.py app/tools/registry.py app/main.py app/repositories/job_posts.py` -> focused lint and strict typing pass.
  - Blocked Condition: Existing `score_cache` cannot safely store the bounded versioned result without a migration or the production composition root cannot inject the accepted graph/embedding services; report `BLOCKED_BY_SOURCE_CONFLICT` before changing persistence architecture.
  - Files: `backend/app/tools/match_jobs.py`, `backend/app/tools/query_jobs.py`, `backend/app/tools/registry.py`, `backend/app/main.py`, `backend/app/repositories/job_posts.py`, `backend/tests/tools/test_match_jobs.py`, `backend/tests/tools/test_query_jobs.py`, `backend/tests/tools/test_registry.py`

- [x] (03B): Carry one bounded match-results payload through existing chat transport
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.5 Match result contract`; `docs/plans/Master_plan.md` > `### 14.2 SSE contract`; `docs/plans/Master_plan.md` > `### 15.5 Match result card`; `docs/plans/Master_plan.md` > `### 22.4 Logging`
  - Source Requirements:
    - Attach validated top results to final assistant `structured_payload`, `run_completed`, and history hydration without adding a ninth event.
    - Keep the payload bounded and limited to visible match fields/evidence; exclude raw CV/JD, vectors, provider data, secrets, stack traces, and raw tool arguments/results.
    - Sanitize `match_jobs` tool activity through existing allowlisted status summaries.
  - Dependencies: (03A) tool payload and (02C) match-result schemas; accepted saved-Job structured-payload seam
  - User Action: None
  - Agent Work:
    1. Search every structured-payload validator, chat persistence/finalization, SSE, history, and frontend mirror caller; extend the existing tagged union rather than creating a parallel transport.
    2. Add one bounded `match_results` backend card schema and fail-closed parser/builder derived from validated tool output.
    3. Extend chat finalization, `run_completed` payload, and history serialization to preserve exactly one valid match payload while ignoring malformed/oversized content and maintaining idempotency.
    4. Add backend schema/API/integration tests for live/history equivalence, duplicate events/turns, tool failure, malformed payload, bounds, event-name inventory, and sentinel absence across wire/history/database/logs.
  - Output: A validated match-results card payload on the existing `run_completed` and durable assistant history contract.
  - Acceptance:
    - The SSE event-name union remains exactly eight; `run_completed` carries at most one bounded match payload and existing saved-Job payload behavior remains compatible.
    - Live and hydrated match payloads validate to the same safe contract; malformed/oversized data fails closed without breaking the assistant message.
    - Tool failures never emit a success card, and privacy sentinels are absent from SSE, history, durable structured payloads, tool summaries, and captured logs.
    - No public route, alternate websocket/event, raw tool result, or second conversation payload store is added.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/schemas/test_matching.py tests/schemas/test_sse.py tests/integration/test_matching_chat.py tests/api/test_chat.py tests/integration/test_job_chat.py` -> bounded live/history/failure transport tests pass.
    - Required: `cd backend; python -m ruff check app/schemas/matching.py app/schemas/sse.py app/schemas/chat.py app/services/chat_service.py app/api/chat.py tests/schemas tests/integration/test_matching_chat.py tests/api/test_chat.py; python -m mypy app/schemas/matching.py app/schemas/sse.py app/schemas/chat.py app/services/chat_service.py app/api/chat.py` -> focused lint and strict typing pass.
  - Blocked Condition: The accepted structured-payload union cannot represent match results without changing event names or public routes; report `BLOCKED_BY_SOURCE_CONFLICT` and do not add another transport.
  - Files: `backend/app/schemas/matching.py`, `backend/app/schemas/sse.py`, `backend/app/schemas/chat.py`, `backend/app/services/chat_service.py`, `backend/app/api/chat.py`, `backend/tests/schemas/test_matching.py`, `backend/tests/schemas/test_sse.py`, `backend/tests/integration/test_matching_chat.py`, `backend/tests/api/test_chat.py`

## Mandatory Batch04 - Astryx Match Presentation

### Goal

Render validated live and hydrated top results with transparent score and skill
evidence inside the existing Astryx chat experience.

### Dependencies

Batch03 backend payload and accepted frontend parser/reducer/chat shell.

### Scope Boundary

This batch owns the frontend contract, reducer/hydration mapping, tool label,
`MatchCard`, and `ScoreBreakdown` only. It adds no dashboard, route, backend
formula, alternate state store, custom design system, or evaluation behavior.

### Tasks

- [x] (04A): Render bounded Astryx match cards and collapsible breakdowns
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.5 Match result contract`; `docs/plans/Plan_6.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 15.3 Chat components`; `docs/plans/Master_plan.md` > `### 15.5 Match result card`; `docs/plans/Master_plan.md` > `### 24.3 Frontend tests`
  - Source Requirements:
    - Show title, company, location, work mode, final score, matched required, verified related, missing required, safe source URL, and expandable component/effective-weight breakdown.
    - Reuse live `run_completed` and durable history payloads with one strict fail-closed parser and sanitized `match_jobs` tool status.
    - Use documented pinned Astryx Card/MetadataList/Collapsible/ProgressBar composition and existing AppShell/chat layout.
  - Dependencies: (03B) backend match payload; accepted frontend chat contracts/reducer/messages and `frontend/AGENTS.md`
  - User Action: None
  - Agent Work:
    1. Run `cd frontend; npx astryx build "chat job match result score breakdown"; npx astryx component Card; npx astryx component MetadataList; npx astryx component Collapsible; npx astryx component ProgressBar` and record the pinned 0.1.4 APIs before editing.
    2. Search all saved-Job contracts, structured-payload parsers, reducer, message rendering, tool mapping, and tests; share safe URL/text/token helpers rather than duplicating presentation validation.
    3. Implement strict bounded match contracts and identical live/history reducer hydration, then focused `MatchCard` and `ScoreBreakdown` components using component props/tokens and semantic accessible controls.
    4. Add component/reducer/full-raw-SSE tests for complete/partial fields, score formatting, matched/related/missing evidence, safe URL, expand/collapse, malformed/duplicate payloads, history, tool failure, disconnect, and no raw sentinel.
  - Output: Responsive accessible top-result cards with transparent collapsible score breakdowns on the existing chat message path.
  - Acceptance:
    - Live and hydrated results render identically; malformed/oversized/unsafe payloads are ignored without crashing or rendering unsafe URLs/text.
    - Cards show every source-required field and related skills only when verified evidence exists; the breakdown shows component values and effective weights.
    - `match_jobs` activity uses sanitized existing tool-status UI and failure/disconnect states never show false success.
    - Astryx CLI evidence names the used public APIs; no raw layout `div`, hard-coded visual value, dashboard, second shell, or guessed prop is added.
  - Validation:
    - Required: `cd frontend; npm run check:astryx; npm run test -- --run src/features/jobs src/features/chat/reducer.test.ts src/features/chat/components/ChatMessages.test.tsx src/test/matching-workflow.integration.test.tsx` -> Astryx compatibility, payload, reducer, component, live/history, and failure tests pass.
    - Required: `cd frontend; npm run lint; npm run typecheck; npm run build` -> frontend lint, type-check, and production build pass.
  - Blocked Condition: Pinned Astryx 0.1.4 lacks a documented composition path for a required card/breakdown behavior; report `BLOCKED_BY_SOURCE_CONFLICT` with CLI evidence and do not guess props or add another UI library.
  - Files: `frontend/src/features/jobs/contracts.ts`, `frontend/src/features/jobs/components/MatchCard.tsx`, `frontend/src/features/jobs/components/ScoreBreakdown.tsx`, `frontend/src/features/jobs/components/MatchCard.test.tsx`, `frontend/src/features/jobs/components/ScoreBreakdown.test.tsx`, `frontend/src/features/chat/contracts.ts`, `frontend/src/features/chat/reducer.ts`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/components/toolMapping.ts`, `frontend/src/test/matching-workflow.integration.test.tsx`

## Mandatory Batch05 - Sealed Evaluation Tooling

### Goal

Create privacy-safe local dataset contracts and reproducible extraction,
tool-selection, ranking, latency, tuning, and ablation runners that prevent
held-out leakage.

### Dependencies

Batch04 complete matching behavior and existing Phase 0 evaluation primitives.

### Scope Boundary

This batch owns committed schemas/templates/synthetic fixtures, deterministic
split enforcement, metric/runners, and tests. It does not create private labels,
call real providers during acceptance, tune on held-out data, publish passing
metrics, or change production weights.

### Tasks

- [x] (05A): Seal private dataset contracts and the fixed 60/20/20 split
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.6 Evaluation protocol`; `docs/plans/Master_plan.md` > `### 19.1 Data policy` through `### 19.4 Tool-selection dataset`; `docs/plans/Master_plan.md` > `### 22.4 Logging`
  - Source Requirements:
    - Define local inputs for 150-200 relevance-labeled public JDs, at least 30 extraction annotations, at least 50 tool scenarios, and one Candidate context under the locked privacy policy.
    - Use deterministic seeded 60/20/20 development/validation/held-out assignment and prevent tuning code from reading held-out labels/results.
    - Commit only schemas, templates, synthetic fixtures, aggregate-safe manifests, and protocol metadata; private/raw data remains ignored.
  - Dependencies: Accepted evaluation directories/`.gitignore` and reusable Phase 0 seeded-split patterns
  - User Action: None for schemas/templates/tests. Real annotation/population is deferred to (06A).
  - Agent Work:
    1. Search all evaluation schemas/manifests/split/metric helpers and ignore rules; reuse Phase 0 protocol and JSON validation patterns while separating Plan 6 responsibilities into focused modules.
    2. Define strict versioned contracts for relevance labels 0-3, extraction annotations, tool scenarios/outcomes, Candidate reference, safe IDs/digests, and aggregate-only manifests with no document body/contact fields.
    3. Implement deterministic seeded entity-level 60/20/20 assignment, count/uniqueness/leakage validation, sealed held-out access tokens/commands, and explicit development/validation versus test readers.
    4. Add committed annotation templates and small synthetic fixtures plus tests for required counts, reproducibility, duplicates, cross-split leakage, private paths, raw/PII fields, and tuning attempts to load held-out data.
  - Output: A versioned privacy-safe evaluation protocol, input schemas/templates, synthetic fixtures, and enforced split loader.
  - Acceptance:
    - Contract validation enforces 150-200 relevance items, at least 30 extraction items, at least 50 required-scenario items, labels 0-3, unique IDs, and deterministic 60/20/20 membership.
    - Development/validation loaders cannot return held-out labels; only the explicit sealed-test command can access the held-out partition after a lock artifact exists.
    - Committed files contain no real CV/JD body, contact PII, private labels, or secret/path material; existing private paths remain gitignored.
    - Templates are concrete schema examples, not prefilled fabricated evaluation evidence.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/evaluation/test_dataset_contracts.py tests/evaluation/test_split_protocol.py` -> schema, count, reproducibility, privacy, and held-out guard tests pass on synthetic fixtures.
    - Required: `cd backend; python -m ruff check evaluation/dataset_contracts.py evaluation/split_protocol.py tests/evaluation; python -m mypy evaluation/dataset_contracts.py evaluation/split_protocol.py` -> focused lint and strict typing pass.
    - Required: `git check-ignore backend/evaluation/private/probe.json backend/evaluation/labels/local-private/probe.json backend/evaluation/fixtures/local-private/probe.json` -> every private probe path is ignored.
  - Blocked Condition: Existing tracked evaluation data contains real/private content or the split cannot be sealed without exposing held-out labels to tuning code; report `BLOCKED_BY_SECURITY` and do not proceed to runner or evaluation work.
  - Files: `backend/evaluation/dataset_contracts.py`, `backend/evaluation/split_protocol.py`, `backend/evaluation/labels/matching_protocol.json`, `backend/evaluation/labels/relevance_labels.template.json`, `backend/evaluation/labels/extraction_labels.template.json`, `backend/evaluation/labels/tool_selection_scenarios.template.json`, `backend/evaluation/fixtures/matching_synthetic.json`, `backend/tests/evaluation/test_dataset_contracts.py`, `backend/tests/evaluation/test_split_protocol.py`, `.gitignore`

- [x] (05B): Implement extraction and tool-selection threshold runners
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.6 Evaluation protocol`; `docs/plans/Master_plan.md` > `### 19.3 Extraction dataset` through `### 19.5 Pass/fail metrics`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Compute required/preferred skill entity F1, seniority/work-mode macro-F1, location accuracy, tool-selection accuracy, invalid-argument rate, unauthorized profile commits, PII leaks, false success, first-SSE latency, and extraction timeout.
    - Cover the required CV/profile/approval/JD/duplicate/match/no-profile/unrelated/failure/prompt-injection scenarios.
    - Use production contracts with injected fakes in tests, sanitized aggregate output, and exact locked thresholds.
  - Dependencies: (05A) validated development/validation dataset loaders and accepted production Agent/extraction contracts
  - User Action: None for runner implementation and synthetic verification. Private evaluation execution is deferred to (06A).
  - Agent Work:
    1. Search Phase 0 metrics, fake adapters, Agent integration fixtures, extraction schemas, and timing helpers; extract shared metric primitives only where reuse removes duplication.
    2. Implement `run_extraction.py` with deterministic entity matching and exact F1/macro-F1/accuracy/timeout aggregation, strict missing/invalid prediction handling, and no raw-row report fields.
    3. Implement `run_tool_selection.py` using fake-backed production tool schemas/policy to score selection, arguments, unauthorized commits, PII leakage, false success, first-event latency, failures, and embedded prompt injection.
    4. Add CLI/help, schema, metric-boundary, retry/failure, privacy-sentinel, and synthetic pass/fail tests; exit nonzero when any locked threshold fails.
  - Output: Two deterministic local runners producing versioned aggregate JSON evidence and explicit per-metric PASS/FAIL without private content.
  - Acceptance:
    - Extraction runner computes all five locked extraction/timeout measures with exact thresholds and treats missing/invalid output as failure.
    - Tool runner computes accuracy, invalid arguments, zero-count safety metrics, and first-event latency across every required scenario category.
    - Failures never become skipped/pass, no runner mutates production state outside temporary fixtures, and reports contain only aggregate/safe IDs.
    - Normal tests use fakes and make zero ShopAIKey/public-network/live-Neo4j calls.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/evaluation/test_run_extraction.py tests/evaluation/test_run_tool_selection.py` -> metric, scenario, failure, latency, and privacy tests pass.
    - Required: `cd backend; python -m evaluation.run_extraction --help; python -m evaluation.run_tool_selection --help` -> both local CLIs expose explicit input/output/split modes without loading private data.
    - Required: `cd backend; python -m ruff check evaluation/run_extraction.py evaluation/run_tool_selection.py tests/evaluation; python -m mypy evaluation/run_extraction.py evaluation/run_tool_selection.py` -> focused lint and strict typing pass.
  - Blocked Condition: A locked metric cannot be computed from the approved extraction/tool contracts without raw/private data in committed output; report `BLOCKED_BY_SOURCE_CONFLICT` and do not weaken privacy or thresholds.
  - Files: `backend/evaluation/metrics.py`, `backend/evaluation/run_extraction.py`, `backend/evaluation/run_tool_selection.py`, `backend/tests/evaluation/test_run_extraction.py`, `backend/tests/evaluation/test_run_tool_selection.py`

- [x] (05C): Implement ranking grid search, latency, sealed test, and graph ablation
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.6 Evaluation protocol`; `docs/plans/Master_plan.md` > `### 18.4 Weight tuning`; `docs/plans/Master_plan.md` > `### 18.5 Graph ablation rule`; `docs/plans/Master_plan.md` > `### 19.5 Pass/fail metrics`
  - Source Requirements:
    - Evaluate semantic-only, exact-skill-only, semantic+exact, semantic+skill-graph, and full-hybrid configurations.
    - Tune bounded weights on development/validation nDCG@10 only, emit a lock artifact, allow one held-out evaluation afterward, and never expose test labels to tuning.
    - Compute Precision@10, nDCG@10 baseline wins, and P95 matching latency for 200 Jobs; apply the exact graph-disable rule.
  - Dependencies: (05A) sealed splits; Batch02 versioned scoring configuration; reusable Phase 0 nDCG/latency functions
  - User Action: None for runner implementation and synthetic verification. Private tuning/test execution is deferred to (06A).
  - Agent Work:
    1. Search existing nDCG/Recall/percentile/embedding benchmark functions and production scoring configuration; refactor shared pure metrics instead of copying formulas.
    2. Implement bounded deterministic grid generation/evaluation over development and validation only, stable tie selection, a content-digested lock artifact, and hard rejection of held-out labels/results during tuning.
    3. Implement an explicit sealed-test mode that verifies the lock/config/data digests, runs exactly the five ablations and 200-Job warm latency, computes locked metrics, and emits an immutable aggregate result plus graph-enable decision.
    4. Add tests for metric math, grid bounds, stable selection, baselines, lock tampering, repeated held-out execution, split leakage, graph pass/fail decision, latency threshold, and aggregate-only output.
  - Output: A reproducible ranking CLI that separately tunes/locks validation configuration and performs one guarded held-out/ablation/latency evaluation.
  - Acceptance:
    - Tuning code has no held-out-reader import/path and cannot emit a lock from test metrics; chosen weights are finite, nonnegative, versioned, and normalized.
    - Sealed-test mode refuses missing/tampered/reused locks and records all five ablations, Precision@10, nDCG@10, baseline comparisons, P95 latency, and graph decision.
    - Related boosts are enabled only when the graph ablation improves held-out nDCG@10; otherwise the locked production configuration disables them.
    - Synthetic tests prove failures are reported, never hidden by threshold/model/weight changes.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/evaluation/test_run_ranking.py tests/test_embedding_benchmark.py` -> metric reuse, seal, grid, ablation, latency, and leakage tests pass.
    - Required: `cd backend; python -m evaluation.run_ranking --help` -> separate `tune` and `sealed-test` commands and explicit safe paths are documented.
    - Required: `cd backend; python -m ruff check evaluation/run_ranking.py evaluation/metrics.py evaluation/benchmark_embeddings.py tests/evaluation/test_run_ranking.py; python -m mypy evaluation/run_ranking.py evaluation/metrics.py` -> focused lint and strict typing pass.
  - Blocked Condition: Held-out isolation cannot be enforced in-process or production scoring configuration cannot be locked without manual post-test mutation; report `BLOCKED_BY_SECURITY` or `BLOCKED_BY_SOURCE_CONFLICT` and do not run held-out evaluation.
  - Files: `backend/evaluation/metrics.py`, `backend/evaluation/run_ranking.py`, `backend/evaluation/benchmark_embeddings.py`, `backend/tests/evaluation/test_run_ranking.py`, `backend/tests/test_embedding_benchmark.py`

## Mandatory Batch06 - Locked Evaluation and Phase 5 Exit

### Goal

Use user-owned private labels to lock and evaluate the system once, apply the
graph rule, publish aggregate limitations, prove the complete fake-backed
matching slice, and hand stable outputs to Plan 7.

### Dependencies

All Batch05 runners accepted; user-owned ignored evaluation inputs populated and
validated; no held-out run has occurred for the current protocol/config digest.

### Scope Boundary

This batch owns execution evidence, the locked production weight/graph
configuration, aggregate report, full integration proof, README handoff, and
quality gates. It does not collect data automatically, expose private rows,
retune after test inspection, change thresholds/models, add fallbacks, or
perform Plan 7 release hardening.

### Tasks

- [ ] (06A): Tune on validation and run the one sealed held-out evaluation
  - Source of Truth: `docs/plans/Plan_6.md` > `### 7.6 Evaluation protocol`; `docs/plans/Plan_6.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `## 19. Evaluation Plan`
  - Source Requirements:
    - Validate 150-200 relevance labels, at least 30 extraction annotations, at least 50 tool scenarios, and the redacted Candidate input under the fixed seeded split.
    - Tune weights only on development/validation, lock them, run held-out exactly once, run all ablations/latency, and apply the graph-disable rule.
    - Pass every locked extraction/ranking/tool/latency threshold or report the honest failure without hidden fallback/tuning.
  - Dependencies: (05B), (05C), and user-populated ignored local datasets matching (05A); current protocol/config has no sealed-test result
  - User Action: Before execution, create and manually verify the ignored `backend/evaluation/private/relevance.json` (150-200 public-JD labels), `extraction.json` (at least 30 annotations), `tool_selection.json` (at least 50 scenarios), and `candidate_profile.json` (one approved/redacted Candidate reference) from the committed templates. Confirm no real raw CV/JD/contact data is tracked and authorize the one held-out run after reviewing validation-only results.
  - Agent Work:
    1. Validate counts, schemas, digests, split isolation, ignore status, and privacy without printing raw/private rows; stop before tuning on any failure.
    2. Run extraction and tool-selection evaluation, then development/validation grid search; review only validation aggregates and write the content-digested locked weight/config artifact.
    3. After explicit user authorization recorded in the execution report, invoke sealed-test once for held-out ranking, all five ablations, graph decision, and 200-Job latency; never reopen test labels for tuning.
    4. Apply only the locked weight/related-boost configuration produced by the protocol and preserve immutable aggregate JSON evidence; report every failed metric exactly.
  - Output: A committed locked matching configuration and privacy-safe aggregate extraction/tool/ranking/ablation/latency results tied to protocol/data digests.
  - Acceptance:
    - Dataset counts/categories and 60/20/20 split validate; all private inputs remain ignored and no raw/private content enters Git, reports, logs, or chat.
    - Locked weights derive only from development/validation and are persisted before the sole held-out command.
    - Held-out evidence includes every locked metric and five ablations; graph boosts match the exact measured enable/disable rule.
    - Every threshold passes. If any threshold fails, this task is not accepted and the report records failure without changing thresholds, model, held-out-tuned weights, or architecture.
  - Validation:
    - Required: `cd backend; python -m evaluation.run_extraction --input evaluation/private/extraction.json --output evaluation/private/results/extraction.json; python -m evaluation.run_tool_selection --input evaluation/private/tool_selection.json --output evaluation/private/results/tool_selection.json` -> private evaluations complete with aggregate-only PASS evidence.
    - Required: `cd backend; python -m evaluation.run_ranking tune --input evaluation/private/relevance.json --lock evaluation/reports/matching_config.json --validation-output evaluation/private/results/ranking_validation.json` -> validation-only grid search emits the pre-test lock.
    - Required: `cd backend; python -m evaluation.run_ranking sealed-test --input evaluation/private/relevance.json --lock evaluation/reports/matching_config.json --output evaluation/private/results/ranking_test.json` -> the authorized one-time held-out run emits all ablations, locked metrics, latency, and graph decision.
    - Required: `git status --short; git diff --check` -> no private input/result file is tracked and the locked config diff is clean.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` until all exact private files and the explicit one-time held-out authorization exist. Also block on invalid/private leakage, prior sealed-test use for the same digest, or any failed locked threshold; never fabricate data or force a pass.
  - Files: `backend/evaluation/private/relevance.json` (ignored user input), `backend/evaluation/private/extraction.json` (ignored user input), `backend/evaluation/private/tool_selection.json` (ignored user input), `backend/evaluation/private/candidate_profile.json` (ignored user input), `backend/evaluation/private/results/extraction.json` (ignored aggregate), `backend/evaluation/private/results/tool_selection.json` (ignored aggregate), `backend/evaluation/private/results/ranking_validation.json` (ignored aggregate), `backend/evaluation/private/results/ranking_test.json` (ignored aggregate), `backend/evaluation/reports/matching_config.json`, `backend/app/services/matching.py`

- [ ] (06B): Prove Phase 5 and publish the stable Plan 7 handoff
  - Source of Truth: `docs/plans/Plan_6.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_6.md` > `## 10. Handoff Notes for Plan 7 (Master Phase 6)`; `docs/plans/Master_plan.md` > `### Phase 5 — Matching, explanation, and evaluation`; `docs/plans/Plan_7.md` > `## 3. Prerequisites from Prior Phases`
  - Source Requirements:
    - Prove the full Candidate-to-top-10 flow, exclusions, failures, transparent breakdowns, seven-tool/seven-route/eight-event exposure, and locked evaluation thresholds.
    - Generate an aggregate matching evaluation report with configuration, digests, metrics, graph decision, per-profile limitation, failures, and no private rows.
    - Publish versioned text builders, locked weights/rules, retrieval/result contracts, graph decision, commands, and limitations as the stable Plan 7 handoff.
  - Dependencies: (06A) accepted locked configuration and passing aggregate evidence; (04A) frontend result cards
  - User Action: None after (06A). Optional live ShopAIKey/Neo4j/Compose observation requires a populated ignored root `.env` and is not required or claimed by automated acceptance.
  - Agent Work:
    1. Search existing full-workflow fixtures, route/tool/exposure scans, README handoffs, and report conventions; extend them without duplicating prior CV/JD setup or evaluation metric logic.
    2. Add a fake-backed backend integration proof from approved profile/scorable Jobs through redaction, candidate embedding, bounded outbox retry, top-50 retrieval, SQLite join, scoring/cache/tool/chat/history, top-10 explanations, outage, and restart; assert ignored/unscorable/provisional/private sentinels never enter results.
    3. Complete the raw-SSE-to-reducer-to-Astryx frontend workflow proof for live/history cards, breakdowns, duplicate events, tool error, malformed data, and disconnect.
    4. Generate `matching_evaluation.md` only from validated aggregate outputs, then update root README Phase 5 status/commands/limitations/Plan 7 handoff and run full backend/frontend/Compose/exposure gates.
  - Output: Passing Phase 5 full-path evidence, aggregate evaluation report, current README handoff, and stable Plan 7 inputs.
  - Acceptance:
    - Backend/frontend full workflows prove deterministic top-10 order, transparent bounded evidence, score-cache/query behavior, no-profile guidance, outage failure, restart hydration, and zero raw/PII/secret leakage with fakes.
    - Aggregate report records every locked threshold, five ablations, exact locked weights/version/digests, graph decision, latency, failures/limitations, and per-profile-only claims without private examples.
    - Production exposure is exactly seven tools, seven public application routes, eight SSE event names, one LangGraph, and no public Job CRUD/new infrastructure.
    - Full backend/frontend/Compose quality gates pass and README accurately hands Plan 7 the stable contracts without claiming optional live observation.
  - Validation:
    - Required: `cd backend; python -m ruff check app tests evaluation; python -m mypy app; python -m pytest -q; python -m pytest -q tests/integration/test_full_matching_workflow.py` -> full backend quality and matching workflow pass with no real provider/Neo4j calls.
    - Required: `cd frontend; npm ci --ignore-scripts; npm run check:astryx; npm run lint; npm run typecheck; npm run test -- --run; npm run test -- --run src/test/matching-workflow.integration.test.tsx; npm run build` -> full frontend quality and raw-SSE matching workflow pass.
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml config; docker compose --env-file .env.example -f infrastructure/docker-compose.yml build` -> static three-service Compose remains valid without real secrets.
    - Required: `rg -n "match_jobs|saved_job|match_results|RELATED_TO|raw_cv|document_text|contact_address" backend/app frontend/src; rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api; git diff --check` -> expected domain seams are reviewed, routes remain seven, prohibited leakage/exposure is absent, and the diff is clean.
  - Blocked Condition: Any locked threshold/full-path/quality/exposure gate fails, aggregate evidence is missing or contains private data, or README cannot state an honest Phase 5 exit; report the failing evidence and do not mark the task or phase complete.
  - Files: `backend/tests/integration/test_full_matching_workflow.py`, `frontend/src/test/matching-workflow.integration.test.tsx`, `backend/evaluation/reports/matching_evaluation.md`, `README.md`

## Optional Future Tracks

This track is not part of the mandatory MVP batch chain.

After Plan 7 release gates pass, only separately approved future work may
consider alternate embedding models/dimensions, reranking, broader/public data
collection, population-level evaluation, automatic job discovery, application
tracking, dashboards, Qdrant, authentication, cloud deployment, or CI. None of
these may be used to satisfy or bypass a Plan 6 task or threshold.
