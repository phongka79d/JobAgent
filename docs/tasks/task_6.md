# JobAgent Plan 6 Execution Tasks

## Purpose

Translate `docs/plans/Plan_6.md` into the mandatory, sequential work needed to
build the approved Candidate representation, reject unavailable or
revision-inconsistent graph state, retrieve up to 50 scorable Jobs, calculate
the exact deterministic matching formula, explain evidence-backed results,
register `match_jobs` as the sixth and final production tool, render up to 10
Astryx match cards, and record the small manual JD acceptance exercise.
These tasks add no dedicated score cache/table/Job column, graph repair in
matching, alternate model, reranking, public endpoint, discovery, or evaluation
project. Compact ordered results and their scores persist only in the existing
`tool_executions.result_json` for required replay/history.

## Project Context Notes

- Root `README.md` was read completely before task derivation. It records Phase
  0 and Plans 2-5 as complete, with matching/ranking explicitly left to Plan 6.
- The repository was clean when this document was derived, and
  `docs/tasks/task_6.md` did not previously exist.
- `backend/app/services/embedding_text.py` already owns
  `normalize_embedding_whitespace` and `build_job_embedding_text_v1`;
  `backend/app/adapters/shopaikey_embeddings.py` and
  `backend/app/schemas/embeddings.py` own the sole locked provider/vector
  contract. Candidate text and vectors must extend and reuse those owners.
- `backend/app/repositories/profiles.py` and the strict profile schemas already
  load approved profile/preferences. `backend/app/graph/rebuild_snapshot.py`
  already performs the only graph-package SQLite reads for the active Candidate
  and every scorable Job, so consistency/matching work must reuse or safely
  refactor that read path instead of duplicating it.
- Candidate and Job graph sync already copy SQLite `updated_at` to
  `source_updated_at`. `backend/app/graph/constraints.py` owns the cosine/1536
  Job vector index, and the provider-free rebuild is the only matching recovery
  path.
- `backend/app/services/skill_normalization.py` and
  `infrastructure/neo4j/skills_seed.yaml` are the sole alias and
  `RELATED_TO` authorities. Excluded Candidate skills are already omitted by
  the Candidate graph projection and must also be ignored by scoring.
- The production registry currently contains exactly five tools. The existing
  `(run_id, tool_call_id)` executor, durable `ToolResult`, live status, history
  hydration, one Agent graph, and one ToolNode remain the only tool path.
- Durable match cards will use compact `match_jobs` `ToolResult.data` from
  `tool_executions`. They will not copy the same result into
  `chat_messages.structured_payload` or introduce a second persistence/client
  truth path.
- The frontend already has a strict saved-job projection, safe HTTP URL helper,
  terminal history refresh, one reducer, and one assistant-row card host.
  Matching should add a focused parser/card concern and thinly extend those
  owners without changing SSE or adding a store.
- `frontend/AGENTS.md` applies to Batch04: run Astryx 0.1.4 discovery before UI
  work, use documented public components/tokens, avoid raw layout elements and
  internal imports, and do not use `Badge` for scores or decorative skill chips.
- Several shared repository, tool, history, and rendering files already meet or
  exceed the preferred 300-line ceiling. New matching behavior belongs in the
  focused Plan 6 modules; edits to large shared files must be narrow integration
  points or safe source-aligned extractions.
- Normal automated gates use temporary migrated SQLite, fake embeddings, and
  controlled Neo4j fakes. Real ShopAIKey, a live public URL, Docker, and live
  Neo4j are required only for the final manual acceptance task.
- Neutral authoring assumptions for nonblocking details use the smallest
  repository-aligned readings: Candidate `target_roles` appears once in its
  leading section; location equality uses only NFKC/collapsed-whitespace/
  casefold normalization; directed `RELATED_TO` is evaluated
  Candidate-to-Job; a seed edge's stored weight is explanation evidence while
  formula strength stays fixed at `0.6`; and timestamp parity compares UTC
  instants rather than raw `Z` versus `+00:00` strings.
- Unresolved source conflict: Plan 6 requires truthful `direct` versus `alias`
  match types/evidence, but the current normalizer resolves both to the same
  stored `SkillRef` and preserves no alias provenance. Task (02A), and therefore
  Batch02 onward, is `BLOCKED_BY_SOURCE_CONFLICT` until an explicit user/plan
  decision defines truthful post-normalization labeling or authorizes the
  required provenance/schema/reprocessing change. Taxonomy aliases alone do not
  resolve this conflict.
- No-profile matching must reuse or safely consolidate the existing profile
  failure vocabulary after auditing its duplicate owners; it must not add a
  third constant definition.
- The user-supplied agent rules apply throughout: search existing owners and all
  callers before writing, reuse/refactor rather than duplicate, keep files
  single-purpose, choose the shortest source-aligned implementation, and fix
  shared behavior at its root.

## Authority and Scope

### Primary Source

- Primary authority: `docs/plans/Plan_6.md`.
- Supporting architecture authority cited by the primary source:
  `docs/plans/Master_plan.md`.
- Repository context only: root `README.md`,
  `backend/app/services/embedding_text.py`,
  `backend/app/adapters/shopaikey_embeddings.py`,
  `backend/app/graph/`, `backend/app/repositories/`,
  `backend/app/tools/`, `backend/app/services/tool_execution.py`,
  `frontend/src/features/jobs/`, `frontend/src/features/chat/`, and
  `frontend/AGENTS.md`.

### Source Section Index

- `docs/plans/Plan_6.md > ## 1. Objective` through
  `## 5. Out of Scope` -> deterministic on-demand matching outcome, mandatory
  scope, prerequisite reuse, and prohibited expansion.
- `docs/plans/Plan_6.md > ## 6. Target Directory Structure` -> focused graph,
  schema, scoring, explanation, orchestration, tool, UI, test, and acceptance
  ownership.
- `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.1 Candidate representation and embedding`
  through `### 7.3 Vector retrieval` -> shared Candidate representation,
  cross-store revision gate, locked embedding, top-50 retrieval, and
  SQLite-authoritative hydration.
- `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.4 Skill coverage`
  through `### 7.7 Explanation and response schema` -> exact skill strengths,
  component formulas, missing-weight renormalization, quality, order, response,
  and evidence rules.
- `docs/plans/Plan_6.md` > `## 7. Technical Specifications` >
  ``### 7.8 `match_jobs` tool`` and
  `### 7.9 Match UI and manual acceptance` -> sixth tool behavior, limit,
  approved-profile policy, card content, and observation-only checklist.
- `docs/plans/Plan_6.md > ## 8. Implementation Steps` and
  `## 9. Verification & Testing Plan` -> implementation order, fake-backed
  automated evidence, manual gate, and truthful failures.
- `docs/plans/Plan_6.md > ## 10. Handoff Notes for Plan 7 / Master Phase 6` ->
  complete Phase 5 output and no redesign or expansion handoff.
- `docs/plans/Master_plan.md > ### 6.2 Application table schemas`,
  `### 6.6 Neo4j identity mapping`, `## 7. Pydantic Data Contracts`,
  `## 8. Neo4j Derived Model`, and `## 9. Skill Normalization` -> source
  ownership, scorable Jobs, canonical identities, evidence, and seed-only
  alias/relationship rules.
- `docs/plans/Master_plan.md` > ``### 13.6 `match_jobs```,
  `### 13.7 Tool authorization matrix`, and `### 15.5 Match result card` ->
  exact Agent-facing availability and frontend result surface.
- `docs/plans/Master_plan.md > ## 17. Embedding and Retrieval` and
  `## 18. Matching Formula` -> locked representations, consistency-first
  retrieval, exact weights, unavailable components, multipliers, and tie order.
- `docs/plans/Master_plan.md > ## 19. Manual JD Acceptance` through
  `## 21. Direct SQLite-to-Neo4j Synchronization` -> manual scope, stable
  failures, no partial/stale ranking, O(n) consistency, and rebuild-only repair.
- `docs/plans/Master_plan.md > ## 24. Local Testing Strategy` and
  `## 25. Implementation Phases > ### Phase 5 — Matching, explanation, and manual acceptance`
  -> required unit/integration/frontend/manual evidence and Phase 5 exit gate.

### Approved Architecture and Constraints

- SQLite remains authoritative for the approved Candidate Profile, current Job
  Preferences, and all Job facts. Neo4j remains a revision-checked,
  rebuildable vector/skill index.
- Matching is read/compute-only. It creates no application or graph rows,
  repairs no graph data, and adds no score/ranking table, Job column, dedicated
  history/cache, or sync ledger. The existing durable tool result remains the
  sole replay/history record and may contain the compact returned scores/order.
- No active profile fails before Candidate embedding. Unavailable Neo4j returns
  `NEO4J_UNAVAILABLE`; missing, extra, or mismatched Candidate/Job revisions
  return `NEO4J_REBUILD_REQUIRED` plus the established rebuild instruction.
  Neither failure returns any ranking.
- Candidate and Job vectors use the same explicit v1 representation family,
  shared whitespace owner, `text-embedding-3-small`, float encoding, and exactly
  1536 finite values. No E5 prefixes, alternate model, local embedding, or
  reranker is permitted.
- Retrieval uses the existing Neo4j Job vector index with `k <= 50`, clamps
  cosine similarity to `[0,1]`, and hydrates current Job facts from SQLite.
- Skill matching uses only non-excluded Candidate skills and the production
  taxonomy: direct/seed-alias `1.0`, seed-related `0.6`, otherwise `0.0`.
  Unknown skills receive no inferred relationship.
- Component, hybrid, quality, and tie calculations use unrounded code-defined
  floats. Missing components are removed and remaining weights are
  renormalized; rounding is display-only.
- Explanations are deterministic projections of stored Candidate/JD evidence
  and computed facts. The LLM may introduce cards conversationally but never
  supplies scores, gaps, weights, or invented evidence.
- `match_jobs` accepts only an optional limit in `1..10`, defaults to 10,
  reads current approved preferences, and remains available during a pending
  replacement only against the approved profile.
- Production remains one Agent graph, one ToolNode, one six-tool registry, one
  durable executor/status vocabulary, one history path, and one frontend
  reducer. No public endpoint or SSE event is added.
- Match UI preserves backend order, renders at most 10 cards, sanitizes source
  URLs through the existing owner, and uses public Astryx components.
- Fixed MVP weights cannot be tuned in this task chain. Consistently unreasonable
  manual results are recorded as findings and require prior Master Plan revision.
- Normal automated tests make no real ShopAIKey, public-network, browser, or
  live Neo4j calls.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Shared Candidate representation plus revision-safe top-50 retrieval foundations | (01A), (01B), (01C) | Plans 4-5 complete |
| Batch02 | Exact deterministic skill/component scoring, ordering, and explanations | (02A), (02B), (02C), (02D) | Batch01 |
| Batch03 | Read-only matching orchestration and exactly six replay-safe production tools | (03A), (03B) | Batch02 |
| Batch04 | Durable Astryx top-result cards and completed manual JD acceptance | (04A), (04B) | Batch03 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_6_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_6_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.
- In orchestrated mode, Codex writes `.agent/handoff/a1_request.md` and invokes
  `python $env:USERPROFILE\.codex\skills\orchestrator-agent\scripts\run_a1_grok.py --cwd <REPO> --envelope-file .agent\handoff\a1_request.md`.
  A1 runs on Grok; A2/A3 and commit/approval remain on Codex. Only an explicit
  `A1_RUNTIME: codex` user instruction overrides this split.

## Mandatory Batch01 - Candidate and Revision-Safe Retrieval Foundations

### Goal

Establish the shared Candidate embedding representation, exact pre-match
cross-store gate, and bounded Neo4j retrieval/SQLite hydration without
performing scoring or registering a tool.

### Dependencies

- Plans 4 and 5 are complete and their approved profile, scorable Job,
  embedding, graph sync/index, taxonomy, and rebuild contracts are present.

### Scope Boundary

This batch does not calculate match components, assemble explanations, register
`match_jobs`, alter ingestion/sync/rebuild behavior, add UI, or persist results.

### Tasks

- [ ] (01A): Extend the shared embedding-text owner with the deterministic Candidate v1 representation
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.1 Candidate representation and embedding`; `docs/plans/Master_plan.md > ## 17. Embedding and Retrieval > ### 17.1 Locked embedding contract` through `### 17.3 Text representations`
  - Source Requirements:
    - Build from approved structured profile/preferences only, in source order:
      target roles, profile summary, normalized non-excluded skills, experience
      titles, then preferred locations/work modes/target seniority in their
      deterministic list order.
    - Reuse the exact Job whitespace/version convention; include no raw CV text,
      E5 prefix, provider call, second normalizer, or silent version change.
    - Keep Candidate and Job representation versions explicit and compatible.
  - Dependencies: Existing `CandidateProfile`, `JobPreferences`,
    `build_job_embedding_text_v1`, and locked embedding contract from Plans 4-5.
  - User Action: None.
  - Agent Work:
    1. Search `embedding_text.py`, its tests, schemas, and every builder caller;
       reuse the existing whitespace/section helpers instead of copying them.
    2. Add failing tests for exact ordering, whitespace, list determinism,
       exclusion, empty optional fields, no raw text/prefixes, and version
       compatibility.
    3. Add the minimum Candidate v1 builder and version marker to the shared
       module, keeping the existing Job output unchanged.
    4. Run focused regression, lint, and typing evidence.
  - Output: One deterministic `build_candidate_embedding_text_v1` contract that
    is compatible with the existing Job v1 representation family.
  - Acceptance:
    - Identical approved structured inputs produce byte-identical Candidate text.
    - Excluded skills and raw CV text cannot enter the representation.
    - There is exactly one embedding whitespace normalizer and the Job builder's
      established output remains unchanged.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/unit/test_candidate_embedding_text.py tests/unit/test_embedding_text.py tests/unit/test_embedding_adapter.py -q` -> exact Candidate behavior plus retained Job/vector contracts pass.
    - Required (from `backend/`): `python -m ruff check app/services/embedding_text.py tests/unit/test_candidate_embedding_text.py tests/unit/test_embedding_text.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
    - Required (from `backend/`): `rg -n "normalize_embedding_whitespace|build_job_embedding_text_v1|build_candidate_embedding_text_v1|EMBEDDING_TEXT_VERSION" app tests` -> one shared normalizer and explicit builders/versions are reviewable.
  - Blocked Condition: None.
  - Files: `backend/app/services/embedding_text.py`, `backend/tests/unit/test_candidate_embedding_text.py`, `backend/tests/unit/test_embedding_text.py`

- [ ] (01B): Implement read-only Candidate/Job revision snapshots and exact consistency rejection
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.2 Pre-match consistency check`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.1 Global conventions` and `## 21. Direct SQLite-to-Neo4j Synchronization > ### 21.2 Local failure behavior`
  - Source Requirements:
    - Compare the active SQLite Candidate and complete locked-scorable SQLite
      Job ID/`updated_at` set with complete Neo4j Candidate/Job
      ID/`source_updated_at` sets for missing, extra, and mismatched revisions.
      Under the recorded neutral timestamp assumption, normalize both
      representations to UTC instants before equality rather than comparing raw
      `Z` and `+00:00` strings.
    - Return `NEO4J_UNAVAILABLE` on query failure and
      `NEO4J_REBUILD_REQUIRED` plus the established rebuild command on any
      difference; return no ranking and mutate neither store.
    - Keep the direct O(n) comparison and the exact source-required `ponytail:`
      comment; do not introduce a ledger, sync, repair, or provider call.
  - Dependencies: Plan 4 Candidate sync and Plan 5 Job sync/rebuild snapshot are
    complete; their IDs and `source_updated_at` values are authoritative inputs.
  - User Action: None.
  - Agent Work:
    1. Search all SQLite graph-snapshot, Candidate/Job sync, timestamp
       serialization, rebuild-command, driver/fake, and caller owners.
    2. Reuse or safely refactor the existing read-only rebuild snapshot
       primitives so matching does not duplicate the active Candidate/scorable
       Job query or timestamp rules; preserve every rebuild caller and test.
    3. Implement focused Neo4j snapshot loading and a direct pure set/revision
       comparison in `graph/consistency.py` with sanitized stable failures.
    4. Establish one focused scripted read fake in
       `backend/tests/fakes/matching.py` for consistency/retrieval/orchestration
       tests rather than copying local Neo4j result/session doubles.
    5. Add controlled tests for exact match, missing/extra Candidate or Job,
       timestamp mismatch, unavailable Neo4j, empty scorable corpus, no
       mutations, and the unchanged rebuild path.
  - Output: A read-only consistency result that either proves exact current
    Candidate/Job revision parity or produces one source-defined failure.
  - Acceptance:
    - Every missing, extra, or mismatched node yields
      `NEO4J_REBUILD_REQUIRED` with zero results and the canonical rebuild
      instruction.
    - Neo4j query failure yields `NEO4J_UNAVAILABLE` with zero results and no
      leaked connection details.
    - Tests show no SQLite write, Cypher write, hidden repair, sync, provider
      call, or duplicated scorable-snapshot query.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/integration/test_match_revisions.py tests/integration/test_candidate_sync.py tests/integration/test_job_sync.py tests/integration/test_graph_rebuild_preflight.py tests/integration/test_graph_rebuild_behavior.py -q` -> parity/failure cases plus retained revision-writing and rebuild behavior pass.
    - Required (from `backend/`): `python -m ruff check app/graph/consistency.py app/graph/rebuild_snapshot.py app/graph/rebuild.py tests/fakes/matching.py tests/integration/test_match_revisions.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
    - Required (from `backend/`): `rg -n "NEO4J_UNAVAILABLE|NEO4J_REBUILD_REQUIRED|source_updated_at|ponytail: O\(n\)" app/graph tests/integration/test_match_revisions.py` -> stable failures, revision inputs, and intentional simplification are reviewable.
  - Blocked Condition: `BLOCKED_BY_SOURCE_CONFLICT` only if the existing sync
    stores an incompatible revision/identity contract that cannot be reconciled
    without changing Plan 6 or the completed sync architecture; report the exact
    conflict and do not invent a new revision mechanism.
  - Files: `backend/app/graph/consistency.py`, `backend/app/graph/rebuild_snapshot.py`, `backend/app/graph/rebuild.py`, `backend/tests/fakes/matching.py`, `backend/tests/integration/test_match_revisions.py`, `backend/tests/integration/test_graph_rebuild_preflight.py`, `backend/tests/integration/test_graph_rebuild_behavior.py`

- [ ] (01C): Query the existing Job vector index at top 50 and hydrate authoritative SQLite facts
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.3 Vector retrieval`; `docs/plans/Master_plan.md > ## 17. Embedding and Retrieval > ### 17.4 Retrieval flow`
  - Source Requirements:
    - Query `db.index.vector.queryNodes` against the existing configured Job
      cosine index with `k=50` or the smaller corpus size.
    - Accept only a validated finite 1536-dimensional Candidate vector, clamp
      each cosine result to `[0,1]`, and return only IDs from the proven
      revision-consistent scorable set.
    - Hydrate scoring/explanation facts from SQLite; do not treat Neo4j metadata
      as canonical, rerank, persist, or call another model.
  - Dependencies: (01B) is A2-accepted; the Plan 5 Job vector index and locked
    embedding validator remain unchanged.
  - User Action: None.
  - Agent Work:
    1. Search the vector-index constant/DDL, graph driver/fakes, scorable
       snapshot, Job data projection, and all index-name callers; expose/reuse
       one index-name owner rather than hard-code a second literal.
    2. Add controlled retrieval tests for zero/fewer/more than 50 Jobs,
       invalid vectors, out-of-range cosine values, unknown returned IDs,
       stable retrieval order, and SQLite-authoritative metadata/source URL.
    3. Implement the focused read-only query/projection in
       `graph/retrieval.py` and reuse the (01B) authoritative snapshot or one
       bulk read; do not add an N+1 or duplicate repository business rule.
    4. Reconfirm vector-index setup and no graph/SQLite mutation.
  - Output: At most 50 revision-consistent hydrated Job candidates carrying
    authoritative SQLite facts and clamped semantic similarity.
  - Acceptance:
    - The Cypher uses the existing configured Job vector index and never
      requests more than 50 nodes.
    - Every result maps to the current scorable SQLite set; unknown/stale IDs
      fail safely instead of being silently ranked.
    - Retrieval performs no writes, alternate semantic scoring, or result
      persistence.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/integration/test_match_jobs.py tests/unit/test_graph_setup.py tests/unit/test_embedding_adapter.py -q` -> retrieval bounds, vector/index contract, clamping, and hydration pass.
    - Required (from `backend/`): `python -m ruff check app/graph/retrieval.py app/graph/constraints.py tests/integration/test_match_jobs.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
    - Required (from `backend/`): `rg -n "db\.index\.vector\.queryNodes|job_embedding_vector|50|clamp" app/graph tests/integration/test_match_jobs.py` -> one bounded index query and boundary evidence are reviewable.
  - Blocked Condition: `BLOCKED_BY_DEPENDENCY` if (01B) is not A2-accepted or
    its snapshot cannot provide the exact scorable ID/revision boundary.
  - Files: `backend/app/graph/retrieval.py`, `backend/app/graph/constraints.py`, `backend/app/graph/rebuild_snapshot.py`, `backend/tests/integration/test_match_jobs.py`, `backend/tests/unit/test_graph_setup.py`

## Mandatory Batch02 - Deterministic Scoring and Explanation

### Goal

Turn retrieved authoritative Candidate/Job facts into exact skill and preference
components, renormalized quality-adjusted scores, deterministic order, and
evidence-consistent response objects.

### Dependencies

- Batch01 is fully A2-accepted, including its explicit Candidate, consistency,
  retrieval, and hydrated Job projections.

### Scope Boundary

This batch is pure calculation/projection. It does not open database or graph
connections, call providers/LLMs, register tools, render UI, or persist scores.

### Tasks

- [ ] (02A): Compute strongest direct, seed-alias, and seed-related skill evidence
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.4 Skill coverage`; `docs/plans/Master_plan.md > ## 18. Matching Formula > ### 18.1 Skill coverage`
  - Source Requirements:
    - Ignore Candidate skills with `excluded=true` and select each Job skill's
      strongest deterministic Candidate match: direct canonical/seed alias
      `1.0`, seed `RELATED_TO` `0.6`, or none `0.0`.
    - Alias and related evidence comes only from the authoritative seed; unknown
      skills receive no inferred related match. Record the winning Candidate
      skill, truthful match type, strength, and stored/seed evidence.
    - Under the recorded neutral relationship assumption, evaluate directed
      seed relationships from Candidate skill to Job skill and retain the seed
      edge weight as evidence metadata while matching strength remains the
      formula's fixed `0.6`.
    - Average each non-empty required/preferred list; an empty list is
      unavailable, a non-empty zero-match list is `0`, and `0.80/0.20`
      renormalizes over available lists.
  - Dependencies: (01A), (01B), and (01C) are A2-accepted; the Plan 4
    `SkillNormalizer` and production taxonomy remain the only identity owners.
  - User Action: None.
  - Agent Work:
    1. Before implementation, obtain an explicit user/plan resolution for the
       lost alias-provenance conflict recorded in Project Context Notes; do not
       treat taxonomy alias availability as provenance or fabricate an alias
       label.
    2. After resolution, search the normalizer, taxonomy dataclasses,
       Candidate/Job skill schemas, graph sync, seed parser, stored records, and
       every exclusion/relationship caller.
    3. Add failing table-driven tests for the approved direct/alias labeling,
       related/competing strengths, directed edges, fixed `0.6` versus seed
       metadata weight, excluded/unknown skills, no matches, empty required or
       preferred lists, both empty, and deterministic ties.
    4. Implement focused pure matching/coverage functions that consume the
       approved provenance contract and existing normalized taxonomy without
       copying normalization or graph behavior.
    5. Verify returned evidence is sufficient for later deterministic
       explanation and contains no invented relationship or provenance.
  - Output: Pure skill-match facts plus nullable required/preferred coverage and
    renormalized `skill_score`.
  - Acceptance:
    - Strongest-match precedence and exact `1.0/0.6/0.0` strengths pass every
      direct/alias/related/excluded/unknown case.
    - Empty and zero-match lists remain distinguishable and renormalize exactly.
    - The implementation imports the existing taxonomy/normalizer contract and
      adds no alias table, fuzzy match, LLM call, or duplicate normalizer.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/unit/test_skill_matching.py tests/unit/test_skill_normalization.py -q` -> exact skill behavior and retained normalization pass.
    - Required (from `backend/`): `python -m ruff check app/services/skill_matching.py tests/unit/test_skill_matching.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
  - Blocked Condition: `BLOCKED_BY_SOURCE_CONFLICT` until explicit user/plan
    authority defines how stored normalized skills truthfully distinguish
    `direct` from `alias`, or authorizes provenance/schema/reprocessing scope.
    Taxonomy alias exposure alone does not unblock the task. After resolution,
    `BLOCKED_BY_DEPENDENCY` also applies until Batch01 is fully A2-accepted.
  - Files: `backend/app/services/skill_matching.py`, `backend/tests/unit/test_skill_matching.py`, `backend/tests/unit/test_skill_normalization.py`

- [ ] (02B): Implement exact seniority, experience, location, and work-mode components
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.5 Other score components`; `docs/plans/Master_plan.md > ## 18. Matching Formula > ### 18.2 Initial hybrid seed`
  - Source Requirements:
    - Return only normalized `[0,1]` values or explicit unavailable state using
      the exact seniority, minimum-experience, location, and work-mode rules.
    - Experience uses Candidate total years and JD minimum only; zero minimum is
      `1`, unmet minimum is a clamped ratio, and maximum years is descriptive.
    - Location comparison applies Unicode NFKC, trim/collapsed whitespace, and
      casefolding in one focused helper, then exact membership. It adds no
      punctuation, fuzzy, geographic, or synonym interpretation.
    - Seniority and work mode use exact enum membership and no ladders.
  - Dependencies: (02A) is A2-accepted and establishes the matching fact
    conventions; existing strict profile/Job schemas define valid inputs.
  - User Action: None.
  - Agent Work:
    1. Search existing Unicode/whitespace/comparison helpers and every
       profile/Job field owner before selecting the smallest reusable boundary;
       do not repurpose skill-specific alias behavior for locations.
    2. Add failing boundary tests for unavailable inputs, exact match/mismatch,
       zero/equal/below/above valid experience, exact location normalization,
       and clamping.
    3. Implement small pure component functions and one clearly named
       deterministic location comparison helper.
    4. Confirm no maximum-years penalty, seniority ladder, fuzzy location, or
       LLM/provider dependency exists.
  - Output: Four focused nullable component functions with exact source-defined
    boundaries.
  - Acceptance:
    - Every component returns exactly the source-defined value or unavailable
      state for all boundary cases.
    - Location normalization is deterministic and centralized; comparison
      remains exact after the locked minimal normalization.
    - Maximum years, fuzzy logic, seniority distance, and provider inference do
      not influence a score.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/unit/test_match_components.py -q` -> all component and boundary cases pass.
    - Required (from `backend/`): `python -m ruff check app/services/match_components.py tests/unit/test_match_components.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
  - Blocked Condition: `BLOCKED_BY_DEPENDENCY` if (02A) is not A2-accepted.
  - Files: `backend/app/services/match_components.py`, `backend/tests/unit/test_match_components.py`

- [ ] (02C): Renormalize exact hybrid weights, apply quality, and sort without rounding
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.6 Hybrid score, missing fields, and order`; `docs/plans/Master_plan.md > ## 18. Matching Formula > ### 18.2 Initial hybrid seed` through `### 18.4 Fixed MVP weights`
  - Source Requirements:
    - Use exact base weights: semantic `0.30`, skill `0.40`, seniority `0.10`,
      experience `0.10`, location `0.05`, and work mode `0.05`.
    - Remove unavailable components, renormalize available weights to one, then
      apply quality `full=1.00` or `partial=0.85`; unscorable Jobs never receive
      a retrievable final score.
    - Keep unrounded floats and sort by final score descending, skill score
      descending nulls last, semantic similarity descending, then Job ID
      ascending. Return no more than the caller's `1..10` limit.
  - Dependencies: (02A) and (02B) are A2-accepted.
  - User Action: None.
  - Agent Work:
    1. Search all Job quality constants/private scorable sets, compact ordering
       helpers, numeric clamping, and score-like model/migration fields before
       adding logic; import or safely consolidate one existing quality owner
       rather than add another repeated set.
    2. Add exhaustive tests for every single/multiple missing-component
       combination, available-weight sum, full/partial quality, invalid
       unscorable input, unrounded near ties, null skill ordering, exact ties,
       ID tie-break, and result limits.
    3. Implement one pure formula/order owner using named source weights; do not
       round, persist, tune, or ask an LLM for numerical values.
    4. Verify the database/migrations gain no score/ranking field or cache.
  - Output: Deterministic scored candidates with effective weights,
    quality multiplier, exact order, and bounded top-result selection.
  - Acceptance:
    - Effective weights of available components sum to exactly the normalized
      formula within deterministic floating-point tolerance.
    - Full/partial multipliers and all four tie keys produce the exact expected
      order using unrounded values.
    - No model, migration, repository write, score cache, or configurable weight
      surface is added.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/unit/test_match_components.py tests/unit/test_match_ordering.py -q` -> missing-weight, quality, ordering, and limit cases pass.
    - Required (from `backend/`): `python -m ruff check app/services/match_components.py tests/unit/test_match_components.py tests/unit/test_match_ordering.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
    - Required (from `backend/`): `$hits = Get-ChildItem -Path app/db,migrations -Recurse -File | Select-String -Pattern 'score_cache|match_score|final_score'; if ($hits) { $hits; throw 'persistent matching field/cache found' }` -> exits zero only when no persistent matching field or cache exists, including in untracked files.
  - Blocked Condition: `BLOCKED_BY_DEPENDENCY` if (02A) or (02B) is not
    A2-accepted.
  - Files: `backend/app/services/match_components.py`, `backend/tests/unit/test_match_components.py`, `backend/tests/unit/test_match_ordering.py`

- [ ] (02D): Define compact match response schemas and deterministic evidence explanations
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.7 Explanation and response schema`; `docs/plans/Master_plan.md > ## 7. Pydantic Data Contracts > ### 7.5 Tool execution result` and `## 24. Local Testing Strategy > ### 24.1 Backend unit tests`
  - Source Requirements:
    - Each result exposes compact authoritative Job metadata/source URL,
      unrounded values, explicit unavailable components, effective weights,
      quality multiplier, matched required/preferred skills, seed-related
      evidence, missing required skills, and one deterministic summary.
    - Direct/alias evidence identifies the winning Candidate skill; related
      evidence identifies the seed relationship/weight; gaps are only required
      skills whose best strength is zero.
    - Explanations must agree with stored profile/JD evidence and computed facts,
      never invent reasons, expose raw bodies/embeddings, or use an LLM.
  - Dependencies: (02A), (02B), and (02C) are A2-accepted and own the internal
    evidence/component/scored facts consumed here.
  - User Action: None.
  - Agent Work:
    1. Search existing strict Pydantic/`ToolResult`/frontend compact projection
       conventions and all potentially sensitive Job/Profile fields.
    2. Define one strict `extra="forbid"` matching response contract in
       `schemas/matching.py`; lock exact JSON field names and encode unavailable
       components as explicit nullable values before frontend fixtures exist,
       without duplicating internal scoring rules.
    3. Add a pure explanation projector that assembles stable prose and lists
       only from (02A)-(02C) facts, preserving source evidence and order.
    4. Add focused deterministic explanation tests for repeatability,
       unavailable labels, direct/alias/related/missing evidence, sanitized
       compactness, and no invented/raw data.
  - Output: One backend-owned JSON contract for ordered match results and one
    deterministic facts-to-explanation projector.
  - Acceptance:
    - Repeated projection of identical facts produces identical validated JSON
      and summary text.
    - Every displayed reason/gap is traceable to stored Candidate/JD or seed
      evidence and the exact winning match.
    - Raw CV/JD text, embeddings, secrets, provider bodies, filesystem paths,
      and alternate numerical scores cannot enter the response.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/unit/test_match_explanations.py tests/unit/test_skill_matching.py tests/unit/test_match_components.py tests/unit/test_match_ordering.py -q` -> response/explanation cases and all upstream facts pass.
    - Required (from `backend/`): `python -m ruff check app/schemas/matching.py app/services/match_explanations.py tests/unit/test_match_explanations.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
    - Required (from `backend/`): `$hits = Select-String -Path app/schemas/matching.py,app/services/match_explanations.py -Pattern 'raw_content|embedding_json|profile_json|draft_json|storage_path|provider_response|api_key'; if ($hits) { $hits; throw 'prohibited raw/sensitive match field found' }` -> exits zero only when prohibited raw/sensitive result fields are absent.
  - Blocked Condition: `BLOCKED_BY_DEPENDENCY` if any of (02A), (02B), or
    (02C) is not A2-accepted.
  - Files: `backend/app/schemas/matching.py`, `backend/app/services/match_explanations.py`, `backend/tests/unit/test_match_explanations.py`

## Mandatory Batch03 - Matching Orchestration and Sixth Tool

### Goal

Compose the accepted Batch01/02 owners into one read-only matching service and
expose it through the existing replay/status/history path as exactly one new
production tool.

### Dependencies

- Batches 01 and 02 are fully A2-accepted.

### Scope Boundary

This batch adds no endpoint, SSE event/status, second registry/executor,
matching write, graph repair, alternate provider, frontend rendering, or manual
weight change.

### Tasks

- [ ] (03A): Orchestrate consistency-first Candidate embedding, retrieval, scoring, and explanation
  - Source of Truth: `docs/plans/Plan_6.md` > `## 7. Technical Specifications` > ``### 7.8 `match_jobs` tool`` and `## 9. Verification & Testing Plan` > `### Failure handling`; `docs/plans/Master_plan.md` > `## 6. SQLite Database Contract` > `### 6.1 Global conventions`, `## 17. Embedding and Retrieval` > `### 17.4 Retrieval flow`, and `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Load the current approved profile/preferences, reject no-profile before
      provider work, run revision consistency, build/embed/validate Candidate
      v1, retrieve up to 50, compute/project facts, and return requested top
      `1..10` (default 10) in that exact order.
      No profile reuses or safely consolidates the source-appropriate existing
      profile failure vocabulary with upload/approve-first user guidance; it
      does not add a third duplicate code definition.
    - During a pending replacement use only the approved profile/preferences.
      Keep SQLite/Neo4j/provider calls outside SQLite transactions.
    - Provider, unavailable, and stale failures are stable and truthful; stale
      or unavailable graph state returns zero partial results and performs no
      repair. The service persists nothing; once wrapped by (03B), only the
      existing durable tool result may retain the returned compact scores/order.
  - Dependencies: (01A)-(01C) and (02A)-(02D) are all A2-accepted.
  - User Action: None.
  - Agent Work:
    1. Search profile/preference repositories, session boundaries, the existing
       `EmbeddingClient` protocol/adapter/local test fakes, all new matching
       owners, rebuild instructions, and every caller before composing the
       service. Reuse or safely extract one shared counting fake instead of
       adding another embedding protocol/fake.
    2. Add fake-backed migrated-SQLite/controlled-Neo4j tests for no profile,
       approved profile with pending draft, empty corpus, limit bounds/default,
       success order/evidence, provider failure, unavailable/stale graph,
       no partial result, no open transaction during external calls, and no
       persistence.
    3. Implement a thin `services/matching.py` orchestrator that delegates every
       representation, consistency, retrieval, formula, and explanation rule to
       its accepted owner and maps sanitized failures once.
    4. Re-run shared rebuild/embedding/scoring regressions to prove composition
       did not fork their contracts.
  - Output: One injectable read-only matching service returning the strict
    Batch02 response or one stable truthful failure.
  - Acceptance:
    - The exact call order is profile precondition, consistency, Candidate
      embedding validation, top-50 retrieval, deterministic scoring/explanation,
      then top-limit projection.
    - Fake-backed success returns at most 10 ordered evidence-consistent results;
      every failure path returns zero results and the correct stable guidance.
    - Database and graph mutation counters remain zero and no dedicated
      score/cache record exists after success or failure.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/integration/test_match_revisions.py tests/integration/test_match_jobs.py -q` -> end-to-end fake-backed matching and failure cases pass.
    - Required (from `backend/`): `python -m pytest tests/unit/test_candidate_embedding_text.py tests/unit/test_skill_matching.py tests/unit/test_match_components.py tests/unit/test_match_ordering.py tests/unit/test_match_explanations.py -q` -> delegated deterministic owners pass.
    - Required (from `backend/`): `python -m pytest tests/integration/test_graph_rebuild_preflight.py tests/integration/test_graph_rebuild_behavior.py -q` -> shared snapshot/rebuild regressions pass.
    - Required (from `backend/`): `python -m pytest tests/integration/test_job_ingestion.py tests/integration/test_job_tools.py -q` -> both consumers of the consolidated embedding fake retain their complete behavior.
    - Required (from `backend/`): `python -m ruff check app/services/matching.py app/graph/consistency.py app/graph/retrieval.py app/schemas/matching.py tests/fakes/matching.py tests/fakes/embeddings.py tests/integration/test_match_jobs.py tests/integration/test_match_revisions.py tests/integration/test_job_ingestion.py tests/integration/test_job_tools.py` -> matching and both refactored fake consumers pass focused lint.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
  - Blocked Condition: `BLOCKED_BY_DEPENDENCY` if any Batch01 or Batch02 task is
    not A2-accepted.
  - Files: `backend/app/services/matching.py`, `backend/tests/fakes/matching.py`, `backend/tests/fakes/embeddings.py`, `backend/tests/integration/test_match_jobs.py`, `backend/tests/integration/test_match_revisions.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_job_tools.py`

- [ ] (03B): Register replay-safe `match_jobs` as the sixth and final production tool
  - Source of Truth: `docs/plans/Plan_6.md` > `## 7. Technical Specifications` > ``### 7.8 `match_jobs` tool``; `docs/plans/Master_plan.md` > `## 13. Agent-Facing Tool Contracts` > ``### 13.6 `match_jobs``` and `### 13.7 Tool authorization matrix`
  - Source Requirements:
    - Expose optional integer `limit` in `1..10` with default 10 and return the
      strict compact matching response/failure through existing `ToolResult`
      coupling.
    - Use the existing `(run_id, tool_call_id)` durable executor/replay/status
      path and register exactly six production tools. Do not add another
      idempotency key, executor, graph, ToolNode, route, event, or status alias.
    - Keep `match_jobs` read/compute-only and available with an active approved
      profile, including while a replacement draft is pending.
  - Dependencies: (03A) is A2-accepted; the Plan 5 five-tool registry and
    durable tool infrastructure remain the integration owners.
  - User Action: None.
  - Agent Work:
    1. Search `match_jobs` guards, every exact-five/absence assertion, registry
       construction, API dependency injection, Agent graph documentation,
       prompt authorization, executor, history, runner, and tool-name caller
       before editing.
    2. Add `tools/matching.py` with strict input, compact argument summary, one
       service invocation, complete exception-to-failed-`ToolResult` mapping,
       and existing durable executor use; no failure may escape and leave the
       durable tool row `running`.
    3. Thinly inject/register the matching dependency after the five existing
       tools; update prompt/authorization and stale exact-five/absence tests at
       their shared root without weakening unrelated tool assertions.
    4. Prove first execution, terminal replay without recomputation,
       status/history hydration, provider/Neo4j failure truthfulness,
       no-profile/pending-draft behavior, and absence of any new API/SSE/state
       path.
  - Output: Exactly six production Agent-facing tools, with `match_jobs`
    replay-safe and its compact result durably available to the existing history
    client path.
  - Acceptance:
    - Production tool names are exactly the three profile tools, `save_job`,
      `query_jobs`, then `match_jobs`; synthetic or duplicate tools remain absent.
    - Re-entering the same terminal invocation returns the stored result and
      does not recompute/embed/query; live and durable statuses retain only
      `pending|running|completed|failed`.
    - Every provider/Neo4j/service exception becomes a terminal failed
      `ToolResult`; none leaves a row running or lets Agent/UI claim success.
    - No endpoint, SSE schema/event, second executor/registry/store, graph write,
      `chat_messages` result copy, or dedicated score persistence outside the
      existing `tool_executions.result_json` is introduced.
  - Validation:
    - Required (from `backend/`): `python -m pytest tests/integration/test_match_jobs.py tests/integration/test_tool_replay.py tests/integration/test_agent_runner.py tests/integration/test_chat_history.py -q` -> tool execution/replay/status/history contracts pass.
    - Required (from `backend/`): `python -m pytest tests/integration/test_job_tools.py tests/integration/test_interrupt_resume.py tests/integration/test_profile_approval.py tests/unit/test_agent_graph.py tests/unit/test_shopaikey_chat.py tests/unit/test_profile_extraction.py -q` -> exact-six registry and all prior tool/authorization regressions pass.
    - Required (from `backend/`): `python -m ruff check app/tools/matching.py app/tools/registry.py app/api/dependencies.py app/agent/graph.py app/agent/prompt.py tests/integration/test_match_jobs.py tests/unit/test_agent_graph.py` -> focused lint passes.
    - Required (from `backend/`): `python -m mypy app` -> backend typing passes.
    - Required (from `backend/`): `rg -n "match_jobs|production_registry|five tools|six tools|never registered|stay absent" app tests` -> every old absence/exact-five caller is intentionally preserved or updated and the one production registration is reviewable.
  - Blocked Condition: `BLOCKED_BY_DEPENDENCY` if (03A) is not A2-accepted.
  - Files: `backend/app/tools/matching.py`, `backend/app/tools/registry.py`, `backend/app/api/dependencies.py`, `backend/app/agent/graph.py`, `backend/app/agent/prompt.py`, `backend/tests/integration/test_match_jobs.py`, `backend/tests/integration/test_tool_replay.py`, `backend/tests/integration/test_agent_runner.py`, `backend/tests/integration/test_chat_history.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_interrupt_resume.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/unit/test_shopaikey_chat.py`, `backend/tests/unit/test_profile_extraction.py`

## Mandatory Batch04 - Match Cards and Manual Acceptance

### Goal

Render backend-ordered deterministic results through the existing durable chat
truth path and complete the source-scoped local manual JD observations.

### Dependencies

- Batch03 is fully A2-accepted and owns the final strict `match_jobs`
  `ToolResult.data` contract.

### Scope Boundary

This batch does not create a dashboard, second client store, new stream/API,
custom design system, benchmark/dataset/metric/report, automatic weight tuning,
or production deployment.

### Tasks

- [ ] (04A): Render durable backend-ordered Astryx match cards and score breakdowns
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.9 Match UI and manual acceptance`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.5 Match result card` and `## 24. Local Testing Strategy > ### 24.3 Frontend tests`
  - Source Requirements:
    - Each card shows title, company, location, work mode, display-rounded final
      score, matched required skills, seed-related skills, missing required
      skills, and safe source URL when present.
    - A public Astryx `Collapsible` contains labeled `ProgressBar` component
      values, effective weights, quality multiplier, and explicit unavailable
      states. UI formatting never changes backend order.
    - Live terminal and restarted history use the existing durable
      `ToolResult.data` projection, one reducer, and one assistant-row host.
  - Dependencies: (03B) is A2-accepted and its backend schema/fixtures are the
    sole JSON authority.
  - User Action: None.
  - Agent Work:
    1. Run the required Astryx build/docs/component discovery before UI edits;
       inspect the build-selected `detail-page` template skeleton, but do not
       scaffold or replace the existing page/frame.
    2. Search the saved-job parser/card, `safeHttpUrl`, history projection,
       terminal refetch, reducer, assistant-row ownership, and tool-label caller.
       Keep `types.ts`/history/message-row edits thin because they are already
       large.
    3. Add focused `matchResult.ts` strict DTO/allowlist parsing, then implement
       `MatchCard` and `ScoreBreakdown` with public Astryx components/tokens.
       Parse at most 10 results and map the array without sorting.
    4. Extend the existing history projection for validated `match_jobs` data,
       render cards only on the single assistant host, and add the explicit
       friendly sixth-tool label; do not change reducer/SSE/API behavior unless
       a failing source-required test proves a root gap.
    5. Test live terminal refresh, restart hydration, exact-one rendering,
       backend order, display-only rounding, safe/absent URL, all skill groups,
       unavailable components, effective weights, and prior saved-job/approval
       behavior.
  - Output: Restart-safe ordered match cards and collapsible score detail through
    the existing chat/history truth path.
  - Acceptance:
    - At most 10 cards render exactly once and in the backend array order for
      both terminal refresh and history rehydrate.
    - Every source-required field, unavailable state, and effective weight is
      visible; scores are rounded only in formatting and source URLs use the
      existing safe HTTP helper.
    - No raw `div`, raw color/spacing value, internal Astryx import, decorative
      score/skill `Badge`, second result store, reducer, SSE event, or API path
      is added.
  - Validation:
    - Required (from `frontend/` before implementation): `npx astryx build "job match result cards in chat with collapsible score breakdown"` -> pinned public component/layout guidance is captured in A1 evidence.
    - Required (from `frontend/` before implementation): `npx astryx template detail-page --skeleton` -> the build-selected template is studied without scaffolding or replacing the existing shell.
    - Required (from `frontend/` before implementation): `npx astryx docs layout` and `npx astryx docs tokens` -> shell/token constraints are reviewed.
    - Required (from `frontend/` before implementation): `npx astryx component Card`, `npx astryx component MetadataList`, `npx astryx component Collapsible`, `npx astryx component ProgressBar`, `npx astryx component Link`, `npx astryx component Token`, and `npx astryx component ChatToolCalls` -> every public component contract used is verified.
    - Required (from `frontend/`): `npm test -- --run src/test/match-card.test.tsx src/test/saved-job-card.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts src/test/approval-card.test.tsx` -> matching and affected durable-chat regressions pass.
    - Required (from `frontend/`): `npm run lint` -> frontend lint passes.
    - Required (from `frontend/`): `npm run typecheck` -> frontend typing passes.
    - Required (from `frontend/`): `npm run build` -> production build passes.
    - Required (from `frontend/`): `$paths = @('src/features/jobs/matchResult.ts','src/features/jobs/MatchCard.tsx','src/features/jobs/ScoreBreakdown.tsx','src/features/chat/history.ts','src/features/chat/components/ChatMessageRow.tsx','src/features/chat/components/ChatToolActivity.tsx','src/test/match-card.test.tsx'); $hits = Select-String -Path $paths -Pattern '<div|@astryxdesign/.+/(src|dist)/|#[0-9A-Fa-f]{3,8}|\b[0-9]+px\b|\bBadge\b'; if ($hits) { $hits; throw 'forbidden match UI pattern found' }` -> exits zero only when the complete changed UI scope has no raw layout element/value, internal import, or match-card `Badge`.
  - Blocked Condition: `BLOCKED_BY_DEPENDENCY` if (03B) is not A2-accepted or
    its strict result schema is not stable enough to generate frontend fixtures
    without inventing a parallel JSON shape.
  - Files: `frontend/src/features/jobs/matchResult.ts`, `frontend/src/features/jobs/MatchCard.tsx`, `frontend/src/features/jobs/ScoreBreakdown.tsx`, `frontend/src/features/chat/history.ts`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatToolActivity.tsx`, `frontend/src/test/match-card.test.tsx`

- [ ] (04B): Execute and record the disposable manual JD acceptance observations
  - Source of Truth: `docs/plans/Plan_6.md > ## 7. Technical Specifications > ### 7.9 Match UI and manual acceptance` and `## 9. Verification & Testing Plan > ### Manual acceptance`; `docs/plans/Master_plan.md > ## 19. Manual JD Acceptance` and `## 25. Implementation Phases > ### Phase 5 — Matching, explanation, and manual acceptance`
  - Source Requirements:
    - Record observations for URL and pasted-text save; full, partial, and
      unscorable classification; extracted fields; exact duplicate return;
      failed-row retry; plausible ranking; score/evidence/gap agreement; and
      documented URL/extraction/provider/Neo4j failures.
    - Use only a small disposable representative set. The artifact is an
      observation checklist, not a dataset, benchmark, metric, grid search,
      ablation, model-selection project, or evaluation report.
    - Do not tune weights. Consistently unreasonable ordering is a recorded
      finding that requires a Master Plan revision before any formula change.
  - Dependencies: (01A)-(01C), (02A)-(02D), (03A)-(03B), and (04A) are
    A2-accepted; the automated backend/frontend matching gates pass.
  - User Action: Before execution, provide/confirm the ignored root `.env` with
    valid `SHOPAIKEY_API_KEY` and `NEO4J_PASSWORD`, working Docker, free loopback
    ports, network access for the chosen public URL/provider, and permission to
    use and delete an isolated disposable Compose project. Be available to
    perform/confirm browser-visible manual observations. Never paste secret
    values into the task, report, logs, or checklist.
  - Agent Work:
    1. Create `docs/acceptance/manual_jd_checklist.md` as a compact table of the
       exact source items, sanitized input identifiers, observed result, and
       dated notes; do not create a second implementation progress tracker.
    2. Re-run the complete Plan 6 automated backend/frontend gates before live
       observations.
    3. Start an isolated `jobagent-plan6-acceptance` Compose project only after
       the user action is confirmed; verify health, then exercise the locked
       chat/profile/JD/matching flow with disposable representative inputs.
    4. Induce provider failure reversibly by recreating only the isolated
       backend with a known-invalid process override, observe one failed
       save/match, remove the override, recreate from the ignored root `.env`,
       and prove matching recovers. Never read or print the real key.
    5. Induce graph failures reversibly: stop isolated Neo4j, save one new
       disposable Job and observe committed SQLite plus `NEO4J_SYNC_FAILED`,
       observe `NEO4J_UNAVAILABLE` on matching, restart Neo4j, observe
       `NEO4J_REBUILD_REQUIRED`, run the canonical in-container rebuild, then
       prove matching succeeds.
    6. Record only actually observed classifications, IDs/outcomes, ordering,
       score/evidence agreement, and sanitized failures. Never fabricate,
       statistically summarize, or expose raw CV/JD/secrets/provider bodies.
    7. If a source-required observation fails, record the exact defect and leave
       the task unaccepted; do not repair code, tune weights, or expand scope in
       this documentation-only task.
    8. After observations are recorded, delete only the explicitly named
       isolated Compose project's containers, networks, and volumes with the
       exact teardown command; do not touch the developer's normal project.
  - Output: `docs/acceptance/manual_jd_checklist.md` containing complete,
    sanitized, dated observations for every Section 19 item.
  - Acceptance:
    - Every source-listed behavior has an actual pass/fail observation and
      concise evidence; no item is marked complete from assumption.
    - Representative successful rankings are plausible and their displayed
      scores, matched/related/missing skills, unavailable fields, and Job/profile
      evidence agree.
    - Failures are truthful, secrets/raw documents are absent, and the artifact
      contains no benchmark, metric, tuning, or evaluation-project content.
  - Validation:
    - Required (from repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance up --build -d` -> isolated frontend/backend/Neo4j services start after user authorization.
    - Required (from repository root): `Invoke-RestMethod http://127.0.0.1:8000/api/health` -> SQLite, filesystem, and Neo4j health is observed without leaked connection details.
    - Required provider-failure procedure (from repository root): `try { $env:SHOPAIKEY_API_KEY='invalid-plan6-acceptance'; docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance up -d --force-recreate backend } finally { Remove-Item Env:SHOPAIKEY_API_KEY -ErrorAction SilentlyContinue }` -> the isolated backend uses only the known-invalid override; one disposable save/match records a sanitized provider failure.
    - Required provider restore (from repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance up -d --force-recreate backend` -> the ignored root environment is restored and a subsequent match succeeds.
    - Required graph-failure procedure (from repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance stop neo4j` -> a new disposable Job observes committed SQLite plus `NEO4J_SYNC_FAILED`, and matching observes `NEO4J_UNAVAILABLE`.
    - Required graph restore/revision procedure (from repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance start neo4j` -> matching first observes `NEO4J_REBUILD_REQUIRED` for the unsynced Job.
    - Required isolated rebuild (from repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance exec -T backend python -m app.graph.rebuild` -> the isolated graph rebuild exits zero and subsequent matching succeeds.
    - Required (from `backend/`): `python -m pytest tests/unit/test_candidate_embedding_text.py tests/unit/test_skill_matching.py -q` -> representation/skill gates pass.
    - Required (from `backend/`): `python -m pytest tests/unit/test_match_components.py tests/unit/test_match_ordering.py tests/unit/test_match_explanations.py -q` -> formula/order/explanation gates pass.
    - Required (from `backend/`): `python -m pytest tests/integration/test_match_revisions.py tests/integration/test_match_jobs.py -q` -> revision/tool integration gates pass.
    - Required (from `frontend/`): `npm test -- --run src/test/match-card.test.tsx`, `npm run typecheck`, and `npm run build` -> source-required match-card gates pass.
    - Required manual check: perform every `docs/acceptance/manual_jd_checklist.md` row against the disposable local stack -> each row contains a dated observed result and sanitized evidence.
    - Required (from repository root): `rg -n "URL|pasted text|full|partial|unscorable|duplicate|retry|ranking|score|evidence|failure" docs/acceptance/manual_jd_checklist.md` -> every mandatory observation category is present.
    - Required (from repository root): `git diff --check` -> tracked documentation changes have no whitespace errors.
    - Required (from repository root): `$bad = Select-String -Path docs/acceptance/manual_jd_checklist.md -Pattern '[ \t]+$'; if ($bad) { $bad; throw 'manual checklist has trailing whitespace' }` -> the newly created/untracked checklist is checked explicitly.
    - Required authorized teardown (from repository root): `docker compose --env-file .env -f infrastructure/docker-compose.yml -p jobagent-plan6-acceptance down -v --remove-orphans` -> only the named disposable project's containers, networks, and volumes are removed after observations.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` if the confirmed ignored
    credentials, Docker, free ports, network/provider access, or isolated local
    acceptance authorization is unavailable; preserve automated evidence and do
    not claim the manual gate passed.
  - Files: `docs/acceptance/manual_jd_checklist.md`
