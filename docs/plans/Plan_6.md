# Plan 6 - Master Phase 5: Matching, Explanation, and Evaluation

## 1. Objective

Deliver measurable top-10 job matching for the active Candidate Profile using Neo4j vector retrieval, transparent deterministic hybrid scoring, evidence-backed skill-gap explanations, bounded weight tuning, graph ablation, local evaluation datasets, and Astryx match-result cards.

## 2. Source of Truth

- `Master_plan.md` sections 7-9 for Candidate/Job/Skill contracts and graph safety.
- Sections 13.6-13.7 for `query_jobs` and `match_jobs`.
- Sections 15.5 and 17-19 for UI, retrieval, scoring, ablation, datasets, and pass/fail thresholds.
- Sections 20-24 for failure, synchronization, privacy, environment, and testing.
- Section 25, **Phase 5 - Matching, explanation, and evaluation**.
- `Plan_5.md` provides canonical active/scorable Jobs and the synchronized vector index.

## 3. Prerequisites from Prior Phases

- [ ] An approved Candidate Profile and Job Preferences exist in SQLite.
- [ ] Active `full|partial` Jobs have canonical fields, embeddings, and synchronized Neo4j IDs.
- [ ] Ignored duplicates and unscorable Jobs are excluded from the vector index.
- [ ] The ShopAIKey `text-embedding-3-small` model, 1536 dimensions, and no-prefix preprocessing policy are fixed.
- [ ] Direct/alias skills and verified/provisional relationship status are queryable.
- [ ] Pending graph operations can be retried before a match request.

## 4. Scope

- Implement deterministic Candidate and Job embedding text builders.
- Retrieve up to 50 active scorable Jobs from the Neo4j vector index.
- Compute direct, verified-alias, and verified-related skill features.
- Compute seniority, experience, location, and work-mode components.
- Apply missing-component weight renormalization and JD quality multiplier.
- Produce deterministic score breakdowns, matched/missing skill evidence, and final top 10.
- Implement `match_jobs` and extend bounded `query_jobs` with score details.
- Build local relevance, extraction, and tool-selection datasets under the locked privacy policy.
- Benchmark the locked embedding retrieval baseline, tune weights on validation only, evaluate once on held-out data, and run graph ablation.
- Apply the locked graph-disable rule when related-skill boosts do not improve held-out `nDCG@10`.
- Implement Astryx match cards and collapsible component breakdowns.
- Generate an aggregate report with limitations and locked configuration.

Candidate embedding text must reuse Plan 4's deterministic PII-redaction service before calling ShopAIKey; a redaction failure blocks the external request. Tests must assert that contact PII never reaches the fake embedding adapter.

## 5. Out of Scope

- LLM-generated numerical scores, ShopAIKey/Jina reranking, alternate embedding models/dimensions, or local embedding runtimes.
- Population-level ranking claims, automatic public data collection, or committed real CV/JD data.
- Re-extraction, Job mutation, ontology expansion, or provisional relationship boosts.
- Application tracking, auto-apply, cover letters, interview preparation, or dashboards.
- Tuning on the held-out set or changing weights after test inspection.

## 6. Target Directory Structure

```text
JobAgent/
|-- backend/
|   |-- app/
|   |   |-- tools/match_jobs.py
|   |   |-- services/{retrieval.py,matching.py,score_components.py,explanations.py}
|   |   `-- schemas/{matching.py,score_breakdown.py}
|   |-- evaluation/
|   |   |-- fixtures/
|   |   |-- labels/
|   |   |-- private/
|   |   |-- reports/matching_evaluation.md
|   |   `-- {run_extraction.py,run_ranking.py,run_tool_selection.py}
|   `-- tests/{unit,integration}/
`-- frontend/
    `-- src/features/jobs/components/{MatchCard.tsx,ScoreBreakdown.tsx}
```

Keep text building, retrieval, component scoring, score aggregation, and explanation separate. The Agent tool delegates to the matching service and does not contain formulas.

## 7. Technical Specifications

### 7.1 Retrieval representations

Candidate text is `target roles + profile summary + verified skills + experience titles + preferences`. Job text remains `title + summary + responsibilities + required skills + preferred skills`. Apply the selected model's query/passage convention consistently. Retry bounded pending outbox items before retrieval; if Neo4j remains unavailable, return a structured failure without claiming matches.

Neo4j vector retrieval returns at most 50 active Job IDs and cosine similarities. Join canonical fields from SQLite by ID before scoring; Neo4j results never override SQLite state.

### 7.2 Skill score

For each required/preferred skill, use the strongest permitted match:

```text
direct canonical = 1.0
verified alias = 1.0
verified RELATED_TO = 0.6
provisional relationship or no match = 0.0
```

Coverage is the mean strength across each non-empty skill list. Compute:

```text
skill_score = 0.80 * required_skill_coverage
            + 0.20 * preferred_skill_coverage
```

If one list is empty, renormalize within `skill_score`; if both are empty, mark the component unavailable. Missing required skills are those with strength zero. Explanation evidence must identify direct/alias/related path and source evidence without raw documents.

### 7.3 Non-skill components

All components return `[0,1]` or unavailable:

- `semantic_similarity`: clamp the Neo4j cosine score to `[0,1]`.
- `seniority_score`: 1 when the Job seniority is in target seniorities, 0 otherwise; unavailable for unknown Job seniority or empty targets.
- `experience_score`: 1 when Candidate years meet the minimum; otherwise `candidate_years / minimum`, clamped; unavailable when either value is unknown or minimum is zero/missing.
- `location_score`: 1 for normalized match with a preferred location, 0 for a known non-match; unavailable when either side is missing.
- `work_mode_score`: 1 when Job mode is acceptable, 0 for a known non-match; unavailable for unknown/missing values.

These initial deterministic rules are versioned with the tuned weight configuration.

### 7.4 Hybrid aggregation

Seed weights are:

```text
semantic_similarity 0.30
skill_score         0.40
seniority_score     0.10
experience_score    0.10
location_score      0.05
work_mode_score     0.05
```

Remove unavailable components and renormalize remaining weights to sum to 1. Apply quality after aggregation: `full=1.00`, `partial=0.85`, `unscorable=null`. Sort by final score descending with a stable Job-ID tie-break. Return at most 10.

### 7.5 Match result contract

Each result includes Job ID, title, company, location, work mode, final score, quality, semantic/skill/non-skill component values and effective weights, matched required skills, verified related skills, missing required skills, explanation lines, and source URL when available. Never expose provisional boosts or unsupported evidence.

### 7.6 Evaluation protocol

- Relevance: 150-200 public JDs, labels 0-3, fixed seeded 60/20/20 split.
- Extraction: at least 30 manually annotated JDs.
- Tool selection: at least 50 scenarios including failures and prompt injection.
- Tune ranking weights only on development/validation; keep the embedding contract fixed before one held-out evaluation.
- Compare semantic-only, exact-skill-only, semantic+exact skill, semantic+skill graph, and full hybrid.
- Disable related-skill boosts if graph expansion does not improve held-out `nDCG@10`.

Required thresholds are exactly those in master section 19.5, including extraction F1/accuracy, Precision@10, baseline wins, tool-selection accuracy, invalid arguments, zero unauthorized commits/PII leaks/false success, and latency ceilings.

## 8. Implementation Steps

- [ ] Implement versioned Candidate/Job text builders and encoding tests.
- [ ] Implement top-50 Neo4j vector retrieval with SQLite canonical-state join.
- [ ] Implement reusable direct/alias/verified-related skill matching.
- [ ] Implement each deterministic non-skill component independently.
- [ ] Implement missing-component renormalization, quality multiplier, stable sorting, and breakdown schema.
- [ ] Implement evidence-backed explanation generation without an LLM score.
- [ ] Implement `match_jobs`, precondition/outbox handling, top-10 limit, and bounded filters.
- [ ] Implement match cards and collapsible breakdown UI.
- [ ] Create seeded local dataset manifests, annotation templates, and private-data ignore rules.
- [ ] Implement extraction, ranking, tool-selection, latency, grid-search, and ablation runners.
- [ ] Tune on validation, lock configuration, run held-out evaluation once, apply graph rule, and write the aggregate report.

## 9. Verification & Testing Plan

- Unit-test every score component, alias/related precedence, unavailable values, renormalization, quality multiplier, and stable ordering.
- Assert provisional relationships contribute zero and ignored/unscorable Jobs cannot enter results.
- Integration-test outbox retry, top-50 retrieval, SQLite join, Neo4j outage, and top-10 response.
- Test `match_jobs` without a profile returns the required upload/approval guidance.
- Frontend tests verify title/company/location/mode, matched/related/missing skills, source URL, and collapsible breakdown.
- Verify seeded splits are reproducible and the held-out split is not read by tuning commands.
- Run all five ablations and record configuration, metrics, latency, and graph enable/disable decision.
- Confirm all master thresholds pass; report any failure honestly rather than adding hidden fallback behavior.

The phase exits only when locked extraction/ranking/tool/latency thresholds pass, full hybrid beats both required baselines, and every returned result has an evidence-backed transparent breakdown.

## 10. Handoff Notes for Plan 7 (Master Phase 6)

Plan 7 receives:

- Versioned text builders, selected embedding, locked hybrid weights, and deterministic component rules.
- A top-50 retrieval/top-10 response service and stable match-result contract.
- Graph ablation decision and aggregate local evaluation report.
- Complete backend/frontend evaluation commands and privacy-safe fixtures/manifests.

Plan 7 may harden, document, and verify these outputs but must not retune on held-out data, add new matching infrastructure, or expand product scope.
