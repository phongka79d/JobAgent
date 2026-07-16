# Plan 6 — Master Phase 5: Matching, Explanation, and Manual Acceptance

> **Numbering:** `Plan_6.md` implements **Master Plan Phase 5**. It computes current results on demand from the approved profile, stored Jobs, and revision-consistent Neo4j index.

## Objective

Deliver transparent, deterministic matching: build/embed the approved Candidate representation, reject stale graph data, retrieve up to 50 scorable Jobs from Neo4j, compute exact skill and preference components, renormalize missing weights, apply quality, sort deterministically, explain evidence-backed matches/gaps, and return/render up to 10 results.

The final numerical score must be code-defined, not LLM-generated. Matching must return no partial ranking when Neo4j is unavailable or revision-inconsistent, and no persisted score cache may be added.

## Source of Truth

- `docs/plans/Master_plan.md` Sections 1–4: transparent matching objective, locked scope/stack, and SQLite/Neo4j ownership.
- Sections 6.2 and 6.6: scorable Job definition, no score cache, and cross-store identities.
- Sections 7–9: Candidate/Job/Skill fields, normalized identities, excluded skills, and seed relationships.
- Sections 13.6–13.7: `match_jobs`, limit, profile precondition, preferences source, and authorization.
- Sections 15.5 and 17: match card, shared Candidate/Job representations, consistency check, top-50 retrieval, and top-10 response.
- Section 18 in full: exact skill strengths, component formulas, weight renormalization, quality multipliers, tie order, and fixed-MVP-weight constraints.
- Section 19: manual JD acceptance without a benchmark/evaluation project.
- Sections 20–21: no-profile, Neo4j unavailable/stale behavior, O(n) revision check, and no repair inside matching.
- Sections 24 and 25, “Phase 5”: matching tests, tasks, and exit gate.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| Legacy Plan 6 scope | Master Phase 5: Matching, Explanation, and Manual Acceptance | Preserve the historical phase scope and outputs below. | Existing Verification section and accepted evidence. |

## Prerequisites

- [ ] An approved Candidate Profile/Preferences can be loaded from SQLite and Candidate/Skill data is directly synchronized with `source_updated_at`.
- [ ] Scorable Jobs are processed `full|partial` rows with locked finite 1536-dimensional embeddings and matching model metadata.
- [ ] Job/Skill graph data uses SQLite IDs/timestamps and the vector index is cosine/1536.
- [ ] Shared skill normalizer/seed taxonomy, embedding adapter, whitespace normalizer, and versioned Job text builder exist.
- [ ] Rebuild restores the complete derived graph without provider calls.
- [ ] Five production tools are registered; tool replay and compact SSE/UI status remain unchanged.

## Scope

- Implement the versioned Candidate embedding text builder using approved structured profile/preferences.
- Reuse the Plan 5 embedding adapter and exact whitespace normalization.
- Implement a pre-match Candidate/full-scorable-Job ID/revision comparison between SQLite and Neo4j.
- Return `NEO4J_UNAVAILABLE` or `NEO4J_REBUILD_REQUIRED` without ranking or repair.
- Embed the active Candidate and query the Neo4j vector index for up to 50 scorable Jobs.
- Compute direct canonical, seed alias, and seed-related skill features against non-excluded Candidate skills.
- Compute seniority, minimum-experience, location, and work-mode components exactly.
- Renormalize missing skill subweights and missing hybrid component weights.
- Apply full/partial quality multipliers and deterministic tie-breaking.
- Build deterministic evidence-backed explanations and missing-skill lists.
- Implement and register the sixth/final production tool, `match_jobs`.
- Implement Astryx match cards with score, matched/related/missing skills, source URL, and collapsible component breakdown.
- Complete the small manual JD acceptance checklist and matching unit/integration/frontend tests.

## Out of Scope

- Changing ingestion, re-extracting/re-embedding Jobs, graph repair/upsert in matching, or a sync ledger.
- Score persistence/cache/history, user-configurable weights, statistical weight optimization, LLM numerical scoring, reranking, or alternate models.
- A labeled JD dataset, benchmark suite, ranking metrics, grid search, ablation, evaluation report, or automated model-selection project.
- Qdrant, local embeddings, Jina/ShopAIKey reranking, automatic job discovery, or non-job-family filters.
- Application tracking, auto-apply, cover letters, interview preparation, or new public endpoints.
- Fuzzy/LLM-invented skill relationships beyond canonical/seed alias/seed `RELATED_TO` behavior.

## Target Directory Structure

```text
JobAgent/
├── backend/
│   ├── app/
│   │   ├── graph/
│   │   │   ├── consistency.py
│   │   │   └── retrieval.py
│   │   ├── schemas/
│   │   │   └── matching.py
│   │   ├── services/
│   │   │   ├── match_components.py
│   │   │   ├── match_explanations.py
│   │   │   ├── matching.py
│   │   │   └── skill_matching.py
│   │   └── tools/
│   │       └── matching.py
│   └── tests/
│       ├── integration/
│       │   ├── test_match_jobs.py
│       │   └── test_match_revisions.py
│       └── unit/
│           ├── test_candidate_embedding_text.py
│           ├── test_match_components.py
│           ├── test_match_ordering.py
│           └── test_skill_matching.py
├── frontend/
│   └── src/
│       ├── features/jobs/
│       │   ├── MatchCard.tsx
│       │   └── ScoreBreakdown.tsx
│       └── test/
│           └── match-card.test.tsx
└── docs/
    └── acceptance/
        └── manual_jd_checklist.md
```

Extend `backend/app/services/embedding_text.py` with `build_candidate_embedding_text_v1`; do not create a second whitespace normalizer. Keep each scoring concern focused so formula, skill matching, orchestration, and prose explanation do not form a God file.

## Technical Specifications

### 7.1 Candidate representation and embedding

`build_candidate_embedding_text_v1` consumes only approved structured state and concatenates in this order:

```text
target roles + profile summary + normalized non-excluded skills + experience titles + preferences
```

Preferences include the approved preferred locations, acceptable work modes, and target seniority values in deterministic list order. Use the exact shared whitespace normalization/version marker contract from Plan 5. Never include raw CV text or E5 query/passage prefixes.

Call the sole ShopAIKey embedding adapter with `text-embedding-3-small`, float encoding, and 1536 dimensions. Validate exact finite vector length before graph retrieval. Candidate and Job representation versions must be explicit and compatible; a version change is code/config migration work, not a silent text change.

### 7.2 Pre-match consistency check

Before embedding/retrieval:

1. Load the active Candidate `(id='active', updated_at)` and the full SQLite set of scorable Job `(id, updated_at)` pairs.
2. Read the complete Neo4j Candidate and Job `(id, source_updated_at)` sets; every Job node is expected to correspond to a current SQLite scorable Job.
3. Compare for missing, extra, or timestamp-mismatched Candidate/Job nodes.
4. If Neo4j cannot be queried, return `NEO4J_UNAVAILABLE` and no results.
5. If any set/revision differs, return `NEO4J_REBUILD_REQUIRED` with the established rebuild command and no results.
6. Do not mutate either store, sync missing nodes, or hide inconsistency in the matching path.

Keep the O(n) comparison direct and readable. Include the Master’s intentional simplification near the implementation:

```text
ponytail: O(n) ID/revision comparison is intentional for the small local corpus; replace with a sync ledger only beyond portfolio scale.
```

No active profile returns the user-facing upload/approve-first failure before Candidate embedding.

### 7.3 Vector retrieval

- Query the configured Neo4j Job vector index using `db.index.vector.queryNodes` with the Candidate vector and `k=50` (or fewer when the corpus is smaller).
- Only revision-consistent scorable Job nodes participate.
- Clamp each returned cosine score to `[0,1]` as `semantic_similarity`.
- Join retrieved Job IDs back to authoritative SQLite extraction/preferences inputs for scoring/explanation; Neo4j does not become the canonical record.
- Do not apply another semantic model or reranker.

### 7.4 Skill coverage

Ignore Candidate skills with `excluded=true`. For each Job skill, take the strongest Candidate match:

```text
direct canonical match = 1.0
seed alias match       = 1.0
seed RELATED_TO match  = 0.6
no match               = 0.0
```

Aliases/relationships must come only from the authoritative seed taxonomy. Unknown skills receive no inferred related match. Record the winning Candidate skill and match type for explanation.

For each required/preferred list:

- Non-empty list: arithmetic mean of best strengths; no matches yields `0`.
- Empty list: coverage unavailable (`null`), not zero.

Combine:

```text
skill_score = 0.80 × required_skill_coverage
            + 0.20 × preferred_skill_coverage
```

Renormalize `0.80/0.20` over whichever list is available. `skill_score` is unavailable only when both lists are empty.

### 7.5 Other score components

All available components are normalized to `[0,1]`:

- `semantic_similarity = clamp(neo4j_cosine_score, 0, 1)`.
- `seniority_score`: unavailable when JD seniority is `unknown` or target list empty; otherwise `1` for exact membership, else `0`.
- `experience_score`: unavailable when Candidate total years or JD minimum years is absent; `1` when minimum is zero or Candidate meets it; otherwise `clamp(candidate_years / minimum_years, 0, 1)`. Maximum years is descriptive only.
- `location_score`: unavailable when JD location is absent or preferred locations empty; otherwise normalize strings through the one focused deterministic comparison helper, then exact membership `1` or mismatch `0`.
- `work_mode_score`: unavailable when JD mode is `unknown` or acceptable modes empty; otherwise membership `1` or mismatch `0`.

Do not add fuzzy location, seniority ladders, maximum-years penalties, or LLM interpretation.

### 7.6 Hybrid score, missing fields, and order

Use exact base weights:

```text
semantic_similarity 0.30
skill_score         0.40
seniority_score     0.10
experience_score    0.10
location_score      0.05
work_mode_score     0.05
```

Remove unavailable components and renormalize remaining weights to sum to `1`. Then multiply:

```text
full quality    × 1.00
partial quality × 0.85
unscorable      final_score = null (never retrieved as scorable)
```

Keep unrounded floats for calculation/order. Sort exactly:

1. `final_score DESC`.
2. `skill_score DESC NULLS LAST`.
3. `semantic_similarity DESC`.
4. `job.id ASC`.

Round only for UI display. Return at most requested `limit`, default/final maximum `10`. Do not persist results.

### 7.7 Explanation and response schema

Each match result contains compact authoritative Job metadata, source URL, unrounded score values for client formatting, and:

- Matched required/preferred skills with winning Candidate skill, direct/alias match type, strength, and source evidence.
- Related skills with seed relationship evidence/weight and strength `0.6`.
- Missing required skills where best strength is `0`.
- Component values or explicit unavailable state.
- Effective renormalized weights and quality multiplier.
- One deterministic summary assembled from these facts.

Explanations must agree with displayed profile/JD evidence and may not invent reasons. The LLM may conversationally introduce returned cards but cannot alter scores/gaps.

### 7.8 `match_jobs` tool

Input: optional integer limit in `1..10`; default `10`. It reads the current approved Job Preferences from SQLite and:

1. Requires active profile.
2. Runs revision consistency.
3. Builds/embeds Candidate text.
4. Retrieves up to 50.
5. Computes features/scores/explanations.
6. Returns up to the requested top results.

This is the sixth and final Agent-facing JobAgent tool. It is read/compute-only, creates no application/graph rows, and uses existing tool replay/status contracts. During a pending replacement draft, it matches against the approved profile only.

### 7.9 Match UI and manual acceptance

Each Astryx card shows title, company, location, work mode, final score, matched required skills, seed-related skills, missing required skills, and source URL when present. A pinned `Collapsible` contains `ProgressBar`/component values, effective weights, and unavailable labels. UI rounding must not change order.

`docs/acceptance/manual_jd_checklist.md` is a disposable local checklist covering URL/text save, full/partial/unscorable classification, extracted fields, exact duplicate return/failed retry, plausible ranking, score/evidence agreement, and documented failures. It contains observations only—not a dataset, metric, or evaluation report.

## Implementation

- [ ] Add failing Candidate representation tests, then extend the shared embedding-text module with the deterministic v1 builder.
- [ ] Implement read-only SQLite/Neo4j revision snapshots and exact O(n) comparison with unavailable/stale error tests.
- [ ] Implement top-50 vector retrieval and SQLite authoritative-data hydration.
- [ ] Implement strongest direct/alias/seed-related skill matching with excluded/empty-list tests.
- [ ] Implement seniority, experience, location, and work-mode components as focused pure functions.
- [ ] Implement missing-component renormalization, quality multiplier, and exact deterministic sorting with tie tests.
- [ ] Implement deterministic explanation/result schemas from computed facts/evidence.
- [ ] Implement/register `match_jobs` using existing context, embedding adapter, repository, tool replay, and SSE status infrastructure.
- [ ] Implement match cards/collapsible breakdown and preserve backend ordering.
- [ ] Complete integration tests with fake embeddings and controlled Neo4j fixtures.
- [ ] Execute and record the Section 19 manual acceptance checklist using disposable synthetic/representative inputs.

## Verification

### Backend commands

```powershell
Set-Location backend
python -m pytest tests/unit/test_candidate_embedding_text.py tests/unit/test_skill_matching.py -q
python -m pytest tests/unit/test_match_components.py tests/unit/test_match_ordering.py -q
python -m pytest tests/integration/test_match_revisions.py tests/integration/test_match_jobs.py -q
```

Expected evidence:

- Candidate/Job builders share normalization and locked embedding configuration.
- Empty skill lists, excluded skills, direct/alias/related best matches, zero matches, and unavailable skill score behave exactly.
- Every component boundary, missing-weight case, quality multiplier, unrounded sort, and exact tie is deterministic.
- Missing/extra/mismatched graph revisions return `NEO4J_REBUILD_REQUIRED`; unavailable graph returns `NEO4J_UNAVAILABLE`; neither returns rankings or mutates graph.
- Fake-embedding integration returns at most 10 evidence-consistent ordered results and persists no score cache.

### Frontend commands

```powershell
Set-Location frontend
npm test -- --run src/test/match-card.test.tsx
npm run typecheck
npm run build
```

Expected: cards preserve backend order, round display only, show source/matched/related/missing fields, mark unavailable components, and expose collapsible effective-weight breakdown.

### Manual acceptance

Run every item in `docs/acceptance/manual_jd_checklist.md` with a small disposable set. Expected: representative URL/text inputs classify/extract/rank plausibly; exact duplicate and failure behavior match the durable records; displayed evidence and gaps agree with the approved profile and JD.

Do not convert these observations into a benchmark or tune weights statistically. A manual weight change is allowed only when results are consistently obviously unreasonable and must revise the Master Plan first.

### Failure handling

- No profile asks the user to upload/approve a CV before matching.
- Provider embedding failure returns a stable failure; no alternate model or stale vector is used.
- Neo4j unavailable/stale returns no partial result and points to rebuild where appropriate.
- A failed tool never leads the Agent/UI to claim a successful ranking.

## Handoff Contract

### Consumes
- docs/plans/Master_plan.md and the prior plan outputs named in Prerequisites.

### Produces
- The completed Master Phase 5: Matching, Explanation, and Manual Acceptance artifacts, scope decisions, and verification evidence preserved below.

### Next Consumer
Plan_7.md consumes the produced artifacts and must not reimplement this phase's owned work.

### Historical Handoff Notes

Plan 7 receives the complete MVP feature set:

- Six exact Agent-facing tools and natural direct conversation.
- Approved CV/profile/preference flow with human approval.
- Durable URL/text Jobs, exact duplicate/retry, embeddings, direct sync, and rebuild.
- Revision-safe top-50 retrieval, deterministic top-10 scoring/explanation, and match cards.
- Feature-level backend/frontend/integration tests and a completed manual JD checklist.

Plan 7 may harden, verify, document, and repair in-scope defects only. It must not redesign formulas, add new tools/endpoints/infrastructure, create evaluation systems, or expand any explicitly out-of-scope item.
