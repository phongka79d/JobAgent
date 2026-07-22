# Plan_16: Profession-Neutral CV/JD Skills And Selected-JD Compatibility Map

## Objective

Make JobAgent extract, normalize, match, synchronize, and display source-grounded
skills from CVs and JDs in any profession without changing production code or the
seed taxonomy for each new job family. A marketing, sales, operations, finance,
healthcare, design, HR, legal, software, or previously unseen CV must pass the same
digital-text gate and the same bounded document/skill pipeline. Unknown atomic
skills remain first-class even when the production seed contains no relevant
entry.

Remove the current split-brain behavior in which Candidate skills are heuristically
parsed from only a Skills section, repaired again only inside matching, and then
synchronized differently to Neo4j. The approved `CandidateProfile.skills` and
`JobPostExtraction` skill rows become the one authoritative atomic assertion set
consumed unchanged by embedding text, matching, explanations, direct graph sync,
rebuild, saved evaluation, and UI read models.

Replace the default technical global graph experience with a selected-JD
compatibility map for the active CV. It shows backend-owned exact, related,
missing-required, missing-preferred, and Candidate-only facts with source display
labels and evidence. The existing bounded Neo4j snapshot remains available under
an explicit **Kỹ thuật** mode for advanced inspection.

The phase is complete only when cross-profession synthetic fixtures work with an
empty or minimal taxonomy, selected Candidate/Job skill relationships are withheld
when Neo4j differs from SQLite, no frontend or backend profession dictionary repairs
the data, existing evaluations become stale through the version contract, and the
single active-Candidate product boundary remains unchanged.

## Source of Truth

- `docs/plans/Master_plan.md` Version 2.2: Sections 2, 7.1-7.4, 8.4-8.5, 9,
  10.2, 14, 15.2, 15.6, 18.1, 19-21, 24-25, 27, and 29.
- `docs/plans/Plan_9.md`: document-first CV extraction, active-CV lifecycle,
  bounded graph projection, and explicit reprocessing baseline.
- `docs/plans/Plan_15.md`: guarded JD extraction, retained-JD compare-and-swap
  re-extraction, complete saved detail, and explicit no-auto-evaluation baseline.
- Current repository owners named in Target Directory Structure. Existing PDF,
  document, normalizer, matching, sync, saved-JD state, graph, and frontend parser
  callers must be searched before any edit.
- Read-only 2026-07-22 diagnosis of the user-provided local CV/JD pair: grouped
  Candidate keys were persisted and synchronized, while a matching-only expansion
  plus sample-specific seed aliases produced different evaluated facts. The local
  identifiers and document content are acceptance inputs only and must not enter
  committed fixtures, logs, screenshots, or plan code.
- Read-only backend and frontend domain-hardcode audits completed for this plan:
  PDF marker gating, all-section skill ownership, matching-only expansion, JD
  technical wording, seed coupling, global graph selection, canonical-only graph
  labels, and saved-JD state ownership.
- **Approved change (2026-07-22):** every profession may supply a CV and obtain its
  actual skills; both backend and frontend hardcodes that assume one profession or
  one sample must be removed; the selected-JD non-technical map remains the approved
  default direction.
- **Change type:** `feature`.
- **Master impact:** `amendment`, explicitly authorized by the current user and
  applied as Master Version 2.2. The amendment changes the CV digital-text rule,
  Candidate/JD skill projection rules, JD guard vocabulary, matching contract
  behavior, public read-only API, graph DTO, and graph-panel UX. It adds no database
  table, provider model, dependency, Agent/tool, worker, or multi-candidate scope.

## Master Requirement Coverage

| Requirement ID | Master section | Owned outcome | Verification evidence |
|---|---|---|---|
| P16-DOM-01 | 2.1, 10.2, 24.1 | Digital CV text is accepted by content bounds rather than English/software identity, role, heading, or tool markers. | Domain-neutral PDF unit tests plus cross-profession PDF fixtures and image-only regressions. |
| P16-CV-01 | 7.2, 10.2 | One bounded internal assertion stage extracts atomic semantic skill labels from all validated CV sections with source-entry ownership and verbatim grounded evidence. | Schema, batching, guard, aggregation, and full publication tests. |
| P16-CV-02 | 7.2, 9, 18.1 | CandidateProfile persistence is the sole CV skill truth; delimiter/category parsing and matching-only grouped-skill expansion are removed. | Negative source inspection, exact profile/matching/sync parity, and legacy grouped-shape regression tests. |
| P16-JD-01 | 7.4, 11.4, 19 | JD extraction and its one repair ask for semantic professional capability labels across occupations; verbatim evidence grounding and structural atomicity use no profession allowlist. | Prompt/guard call-count/redaction tests and cross-profession JD golden cases. |
| P16-NRM-01 | 7.1, 9 | Unknown atomic skills retain display labels, normalize deterministically, and direct-match without seed membership; seed is optional curated alias/relatedness only. | Empty/minimal-taxonomy normalization and matching matrix plus production-seed audit. |
| P16-MAT-01 | 7.1, 18.1, 7.7 | Matching consumes stored atomic skills without repair and bumps the evaluation contract so prior rows derive stale until explicit re-evaluation. | Matching parity tests, context-hash tests, and zero-auto-evaluate assertions. |
| P16-SYNC-01 | 8, 21 | Candidate/Job sync and rebuild project exactly the approved SQLite assertion sets and relationship properties. | Candidate/Job sync, rebuild, and injected mismatch tests. |
| P16-MAP-01 | 8.5, 18.1, 21.2 | Backend reuses skill-coverage facts to build a connected selected-JD map and withholds it on selected relationship mismatch. | Pure projection and Neo4j/SQLite integrity tests for all statuses and bounds. |
| P16-API-01 | 14, 20 | `GET /api/observability/skill-map?job_id=` is read-only, typed, bounded, redacted, and never evaluates or repairs. | API validation/error/redaction/call-count integration tests. |
| P16-FE-01 | 15.2, 15.6 | `Bản đồ CV–JD` uses the existing selected saved Job and backend display/evidence/status; raw graph remains `Kỹ thuật`. | Parser/state/component/accessibility/interaction tests and desktop browser evidence. |
| P16-FE-02 | 15.6, 24.3 | Production React contains no skill, alias, acronym, category, canonical-key formatter, or profession classification dictionary. | Static hardcode audit plus marketing/bilingual/unknown DTO fixtures. |
| P16-ROLL-01 | 6.4, 7.7, 10.3-10.5, 11.6, 21.3 | Existing records are corrected only through explicit CV reprocess/JD re-extract/rebuild, and evaluations become stale without automatic recompute. | Lifecycle/invalidation tests and local non-committed regression acceptance. |
| P16-QA-01 | 19, 24 | Software, marketing, sales/operations, finance/healthcare, bilingual, and unknown-punctuation cases pass one common pipeline without production-seed edits. | Synthetic corpus, bounded provider diagnostic, full gates, and browser checklist. |
| P16-REG-01 | 2.2, 12, 24, 27 | One user, one active Candidate/CV, one Agent/ToolNode, seven tools, fixed scoring, approval, saved-JD, and failure behavior remain intact. | Existing focused/full/backend/frontend/Docker/plan/scope gates. |

## Prerequisites

| Producer or environment | Required artifact/contract | Gate before implementation |
|---|---|---|
| Master Version 2.2 | Authorized profession-neutral semantic extraction, optional-seed, selected-map, API, UX, consistency, and rollout contracts | Shared plan validator and fresh portfolio review must approve Plans 1-16 before task writing. |
| Plan_9 | Validated `CVDocument`, complete chunks, active/archived reprocessing, profile approval, CV graph/rebuild, and one active Candidate | Run current CV document/profile/approval/sync suites and trace every profile-publication caller. |
| Plan_15 | Guarded JD extractor, one repair, retained re-extraction, saved-JD detail/state, same-ID sync, and no automatic evaluation | Run focused JD/re-extraction/saved-JD tests and preserve compare-and-swap/failure contracts. |
| Existing skill owners | `SkillRef`, `CandidateSkill`, `JobSkill`, `SkillNormalizer.normalize_name`, `compute_skill_coverage`, and match explanations | Prove which owners can be reused before adding the shared assertion guard or selected-map projector. |
| Existing graph owners | Candidate/Job sync, rebuild, revision consistency, raw observability graph, and Neo4j fakes | Capture current projected relationship payloads and read-only Cypher contracts before extending them. |
| Existing frontend owners | Sole `useSavedJobsState`, `selectedJobId`, selected detail cache, observability composition, MatchCard DTOs, and raw graph canvas | Confirm no second selection/cache/match owner is introduced. |
| Local environment | `.venv`, root `.env`, three-service Compose, synthetic PDFs/JDs, and disposable graph fixtures | Automated tests use fakes/synthetic data; real local records are optional uncommitted acceptance only. |

## Scope

- Replace profession-specific meaningful-PDF marker families with a
  language/profession-neutral digital-text gate while retaining pypdf-only,
  minimum-content, size/page, malformed, image-only, and no-OCR behavior.
- Define a strict internal Candidate skill assertion schema, bounded entry batching,
  provider invoker, pure source/atomicity guard, one repair, and deterministic
  cross-batch aggregation over the complete validated `CVDocument`.
- Integrate accepted Candidate assertions into document-first publication and remove
  local skill extraction from section headings, delimiters, and category prefixes.
- Generalize JD prompt/repair language and guard rules across professions; require
  semantic labels backed by verbatim evidence and remove code-level technology exception/seed parsing
  dependence while preserving source grounding, duplicate/group rules, issue caps,
  retry limits, and redaction.
- Keep one atomic-name normalizer and optional seed alias/relationship owner; audit
  case-specific seed additions and remove parsing/category aliases that exist only to
  repair the diagnosed sample.
- Remove matching-only Candidate expansion, update every caller, and bump the
  matching/evaluation contract version once.
- Add selected Candidate/Job Neo4j relationship loading and exact comparison against
  SQLite, then build the Section 8.5 map from existing deterministic matching facts.
- Add the strict read-only selected-map API and additive/raw technical Skill display
  metadata without exposing arbitrary graph properties.
- Extend the sole saved-JD state/API/cache owner with a map resource keyed by the
  existing `selectedJobId`, focused invalidation, and request-order protection.
- Implement the default non-technical map, filters, counts, evidence panel, safe
  states, and explicit technical-mode switch using existing React/Astryx/CSS/D3
  capabilities and no new visualization dependency.
- Add cross-profession synthetic fixtures, targeted/full tests, a bounded synthetic
  provider diagnostic, Docker/browser acceptance, and explicit local reprocess/
  re-extract/rebuild instructions.

## Out of Scope

- Multiple active Candidates, two simultaneous people/personas, cross-CV comparison,
  archived-CV matching, multi-user ownership, or a Candidate/Profile schema redesign.
- A global skill ontology, automatic alias/relationship generation, LLM-created
  canonical keys, automatic taxonomy learning, user-editable taxonomy UI, or seed
  expansion merely to make a fixture pass.
- Inferring every noun phrase or achievement as a skill. Candidate/JD assertions must
  be explicit and source-grounded; false-positive recall is not traded for breadth.
- Blind splitting on `/`, `,`, `;`, `|`, `&`, `and`, `or`, colon, or headings;
  profession-specific punctuation allowlists; or downstream repair in matching/UI.
- New CandidateSkill/JobSkill persisted fields, database table/column/migration,
  alternate PDF parser, OCR, DOCX, vector store, provider/model, embedding dimensions,
  dependency, Agent, tool, endpoint mutation, worker, queue, outbox, or sync ledger.
- Scoring weight/formula changes, confidence-weighted matching, learned ranking,
  automatic evaluation, bulk reprocessing, background rebuild, or read-time graph
  repair.
- Replacing the existing technical graph canvas, arbitrary Cypher, client expansion,
  unbounded graph data, or a broad sidebar/theme/responsive redesign.
- Silently rewriting existing approved CV/JD/profile/evaluation rows. Correction uses
  the existing explicit reprocess/re-extract/approval/rebuild actions.
- Committing the user's real CV/JD text, filename, evidence, database row, screenshot,
  provider response, or local identifiers as a test fixture.
- Creating `docs/tasks/task_16.md`, implementing product code, or launching A1/A2/A3
  execution during this planning phase.

## Target Directory Structure

```text
backend/
  app/
    api/observability.py
    graph/
      observability.py                    # raw technical display metadata only
      selected_skill_projection.py        # read-only selected relationship payload
    schemas/
      observability.py                    # Section 8.5 strict DTOs
    services/
      pdf_extraction.py                   # profession-neutral digital-text gate
      cv_skill_projection.py              # new bounded assertion/invoker/aggregation owner
      skill_assertion_guard.py            # new shared pure grounding/atomicity primitives
      cv_document_projection.py            # profile facts; remove skill parsing
      profile_extraction.py                # document + accepted-skill orchestration
      jd_extraction.py                     # profession-neutral prompt/repair
      jd_extraction_guard.py               # reuse shared assertion guard
      skill_normalization.py               # atomic label only; no grouped expansion
      skill_matching.py                    # consume persisted Candidate skills exactly
      skill_compatibility.py               # selected-map classification/projection
      evaluation_context.py                # one matching-contract version bump
      observability.py                     # typed map assembly/status mapping
    graph/sync_candidate.py                # reuse; compatibility change only if RED proves it
    graph/sync_job.py                      # reuse; compatibility change only if RED proves it
    graph/rebuild.py                       # reuse; contract test extension
  tests/
    fixtures/
      cv/cross_profession/                 # synthetic digital PDFs only
      skill_extraction_golden.json         # synthetic CVDocument/JD cases only
    unit/
      test_pdf_extraction.py
      test_cv_skill_projection.py
      test_skill_assertion_guard.py
      test_cv_document_extraction.py
      test_jd_extraction.py
      test_jd_extraction_guard.py
      test_skill_normalization.py
      test_skill_matching.py
      test_skill_compatibility.py
      test_observability_graph.py
      test_evaluation_context.py
    integration/
      test_profile_approval.py
      test_candidate_sync.py
      test_job_ingestion.py
      test_job_reextraction.py
      test_job_sync.py
      test_graph_rebuild_contracts.py
      test_observability_api.py
      test_job_evaluations.py
frontend/src/
  features/
    jobs/
      api.ts
      types.ts
      savedJobsState.ts                  # sole selected-JD/map cache owner
    observability/
      GraphPanel.tsx                     # compatibility/technical mode composition
      SkillCompatibilityMap.tsx
      SkillCompatibilityEvidence.tsx
      TechnicalGraphPanel.tsx            # extracted current raw panel, same canvas
      graphPresentation.ts                # raw technical display_name support
      types.ts
      ObservabilitySidebar.tsx
      observability.css
  test/
    skill-compatibility-api.test.ts
    skill-compatibility-map.test.tsx
    saved-jobs-state.test.tsx
    observability-sidebar.test.tsx
    graph-presentation.test.ts
    graph-panel.test.tsx
infrastructure/
  neo4j/skills_seed.yaml                 # optional curated aliases/relations audit only
  scripts/diagnose_cross_profession_skills.py
docs/
  acceptance/cross_profession_skill_map_checklist.md
  plans/
    Master_plan.md
    Plan_15.md
    Plan_16.md
README.md                                # diagnostic/reprocess/rebuild commands only
```

Equivalent focused existing owners may be reused when the required search proves
they already own the behavior. New source modules stay below the repository's
300-line target. Do not add a second normalizer, saved-JD hook, graph endpoint
client, matching projector, or frontend evidence parser.

## Technical Specifications

### Hardcode classification and audit boundary

Plan 16 distinguishes product contracts from profession templates:

| Kind | Policy | Examples |
|---|---|---|
| Profession data | Forbidden in production extraction/matching/presentation logic | Skill names, role titles, industry headings, aliases, categories, acronyms, known CV/JD phrases. |
| Optional curated knowledge | Allowed only in `skills_seed.yaml`, never required for extraction/display | Independently reviewed aliases and `RELATED_TO` edges. |
| Product vocabulary | Allowed and typed | `required`, `preferred`, `direct`, `related`, graph status/error codes. |
| Deterministic formula | Preserved from Master | Match strengths, score weights, quality multiplier, stable ordering. |
| Safety/resource bound | Allowed and documented | PDF size/pages/minimum text, batch character caps, item limits. |
| UI presentation | Allowed and accessible | Vietnamese labels, filter names, status colors/icons, technical-mode labels. |

Search backend/frontend production source before and after implementation. A test
fixture may contain named skills, but production Python/React may not branch on or
format a specific profession/skill. The production seed is reviewed separately and
does not make this audit pass merely because a hardcoded value moved from code to
data.

### Profession-neutral digital-text gate

- Retain `pypdf`, normal/layout modes, PDF magic/MIME/page/size limits,
  `MIN_NON_WHITESPACE_CHARS`, and `NO_EXTRACTABLE_TEXT`.
- After NFKC and whitespace normalization, a mode is meaningful when it meets the
  minimum non-whitespace count and contains at least one Unicode letter or number.
  It does not require `email`, `experience`, `engineer`, `skills`, `python`, or any
  equivalent marker family.
- Empty, punctuation-only, below-threshold, malformed, and image-only PDFs retain
  existing safe failures and make no provider call. OCR remains absent.
- Tests cover synthetic software, marketing, finance, healthcare, sales/operations,
  Vietnamese, and English digital text with none of the former software markers.
  The Phase 0 aggregate diagnostic is updated only as required by this new accepted
  contract, not weakened to accept empty/image-only input.

### Bounded Candidate skill assertion contract

Create a focused strict internal provider model:

```text
ExtractedCandidateSkillAssertion
- name: str
- confidence: float
- proficiency: beginner | intermediate | advanced | unknown
- years: float | None
- evidence: list[str]
- source_entry_ids: list[str]

ExtractedCandidateSkillBatch
- assertions: list[ExtractedCandidateSkillAssertion]
```

- Serialize bounded source-ordered CV entry projections containing only section
  ID/heading/kind, entry ID/ordinal, title/subtitle/date/location/body/bullets, and
  safe string/list attributes. Do not send PDF bytes, chunks outside the referenced
  entries, storage data, hashes, or another profile.
- Batch by serialized character count under one module-owned provider safety bound.
  This bound is a resource constant, not a profession rule, and introduces no new
  environment variable or duplicate Settings owner.
- The prompt asks for source-supported professional capabilities, tools, methods,
  platforms, and domain practices from every section. It requires one concise semantic
  label per atomic capability, original source-entry IDs, short verbatim evidence, and no aliases/categories/
  relationships. It explicitly excludes headings/group labels, employers, degrees,
  certificates as credentials, achievements, and generic nouns unless the source
  separately names them as a capability.
- Run strict structured output with the locked model/method and shared provider retry.
  Schema or semantic failure receives at most one sanitized repair for that batch.
  Logs contain batch/entry/issue counts only.
- The pure guard validates existing source-entry IDs, ascending unique ownership,
  evidence containment in the referenced entries, non-heading semantic labels,
  structural atomicity, and within-batch normalized
  uniqueness. It neither calls the provider nor returns source values in issues.
- Normalize only accepted atomic names. Across batches, merge equal canonical keys in
  first-source order, merge unique evidence stably, use maximum accepted confidence,
  retain years only when non-null values agree, and retain proficiency only when
  non-unknown values agree; conflicting specificity becomes `None`/`unknown` rather
  than an invented winner.
- Build `CandidateProfile.skills` from that aggregate. Other CandidateProfile fields
  remain derived from the validated document by their existing owners. Atomic draft
  publication still writes chunks, document draft, and profile draft together after
  all provider/guard/projection work succeeds outside the transaction.

### Shared structural skill guard

`skill_assertion_guard.py` owns only reusable pure primitives: NFKC/whitespace/
casefold containment, exact approved-alias lookup, heading comparison, structural
compound detection, and safe issue projection. It has no provider, database, graph,
FastAPI, logging, or frontend imports.

- Seed membership never decides whether a label is a skill and never promotes a
  category prefix. An exact full-label seed alias may establish normalization
  identity and approved atomic punctuation only.
- Do not split. Reject clear enumerations containing multiple non-empty skill-like
  labels. Preserve punctuation inside contiguous unknown labels; no list of valid
  technical/marketing/finance tokens exists in code.
- CV-specific ownership/heading rules remain in the CV projection owner. JD-specific
  required/preferred group checks remain in `jd_extraction_guard.py`. Both apply the
  same semantic-label, verbatim-evidence, and structural-atomicity invariant.
- Guard issue payloads contain code, field path, and structural count only, capped at
  20. Source/evidence/name values, provider payloads, prompts, and exception text do
  not enter repair diagnostics or logs.

### Profession-neutral JD extraction

- Keep `ExtractedJobPost`, final `JobPostExtraction`, `gpt-4o-mini`, strict schema,
  provider retry, and one schema-or-semantic repair.
- Replace `technical skill/framework/model/platform` wording with explicit
  source-supported professional capabilities across any occupation. Examples are
  prohibited in the production prompt when they would bias one profession; synthetic
  examples belong in tests only.
- Permit a concise semantic skill label that need not repeat the JD wording, while
  requiring every evidence snippet to occur in the retained source. Keep the ordered
  six-code guard vocabulary plus metadata/responsibility, duplicate, and
  required/preferred-disjoint rules.
- Replace the code-level `C/C++`/`.NET`/`Node.js`/`CI/CD` exemption set and
  taxonomy-qualified compound rule with the shared structural guard. Unknown
  punctuation-bearing skills remain valid unless the output clearly enumerates
  multiple labels.
- Text ingestion, URL ingestion, retained re-extraction, quality, embedding, exact
  dedupe, and same-ID sync all continue through this single accepted extraction path.

### Atomic normalization and matching parity

- Preserve `SkillNormalizer.normalize_name()` as the sole identity owner. It receives
  one guarded atomic label, resolves optional approved aliases, or creates an unknown
  key/display with no relationship.
- Remove `normalize_grouped_name()`, `expand_candidate_skill()`, colon-prefix
  promotion, and their production callers. Delete/replace tests that assert the
  diagnosed sample-specific repair shape.
- `compute_skill_coverage()` consumes non-excluded stored Candidate skills exactly.
  It remains the owner of direct/related/none facts, strengths, order, and strongest
  winner. Scoring weights and explanation models do not change.
- Audit `skills_seed.yaml`. Remove aliases that encode a source category/group or were
  added solely to repair one CV/JD. Retain an entry only when it is independently
  valid curated alias/relatedness knowledge. New cross-profession tests inject an
  empty/minimal taxonomy and never edit this file to pass.
- Set one explicit new `MATCHING_CONTRACT_VERSION` after the atomic path changes.
  Existing `job_evaluations` become stale by context hash; no row rewrite or automatic
  evaluation occurs.

### SQLite/Neo4j selected relationship integrity

- SQLite remains authoritative. Build expected Candidate rows from approved
  non-excluded `CandidateSkill` values and expected Job rows from validated required/
  preferred `JobSkill` values using the same parameter projectors as direct sync.
- Load the exact active Candidate's `HAS_SKILL` and selected Job's `REQUIRES`/
  `PREFERS` relationships plus their connected Skill identities and allowlisted
  properties. No global Skill query, arbitrary label, embedding, CV body, or mutation
  is allowed.
- Compare complete sets and relationship type, canonical key, confidence, Candidate
  years/proficiency, and bounded evidence. Source-context display names come from
  SQLite and are not compared to the shared Skill node's last-writer display value.
- Missing, extra, duplicate, or property-mismatched rows return
  `NEO4J_REBUILD_REQUIRED`; driver failures return `NEO4J_UNAVAILABLE`. Both withhold
  all compatibility items and perform no sync/rebuild/evaluation.
- Direct Candidate/Job sync and rebuild must pass parity tests unchanged. If a RED
  fault test proves partial-publish behavior, repair the existing sync transaction/
  completion ordering in that owner; do not add a sync ledger or alternate projector.

### Backend-owned compatibility classification

- Require an active approved profile and one processed `full|partial` saved Job.
- After revision and relationship integrity pass, call the existing skill-coverage
  owner over authoritative SQLite rows.
- Emit one item per Job skill in source order:
  - direct winner → `direct`, strength `1.0`;
  - approved seed relation winner → `related`, strength `0.6` plus relation fields;
  - no required winner → `missing_required`, strength `0.0`;
  - no preferred winner → `missing_preferred`, strength `0.0`.
- Append non-excluded Candidate skills that did not win any Job skill as
  `candidate_only`, requirement `none`, strength `0.0`, in Candidate source order.
- Candidate and Job assertion views retain separate canonical keys, display names,
  confidence, and evidence. The display label is never reconstructed from a key or
  the global Skill node.
- Compute counts from validated items and require exact coupling. At more than 200
  items, return `SKILL_MAP_LIMIT_EXCEEDED` and no partial list.
- This is a skill read model only. It computes no semantic embedding/final score,
  persists no evaluation, and does not replace MatchCard or ScoreBreakdown.

### Read-only API and raw technical graph

- Add `GET /api/observability/skill-map?job_id=<UUID>` with a strict query and the
  Master Section 8.5 response. Routes validate/map errors and delegate; services own
  reads/classification.
- `ready` returns the complete bounded selected map. `stale` and `unavailable` are
  typed 200 bodies with empty items and safe guidance. Missing/non-scorable Job,
  missing active profile, and item-limit failures use the documented safe HTTP
  errors. No response contains raw CV/JD text, embedding, storage path, prompt,
  credentials, provider data, stack, SQL, or Cypher.
- Extend the raw `GraphSkillNode` to carry `canonical_key`, `display_name`, and
  optional category. Keep raw graph node/edge caps, allowlisted labels/types,
  active-CV branch, truncation, and stale/unavailable behavior. It accepts no query.

### Frontend state, map, and technical mode

- Extend the existing jobs API/types with a strict selected-map parser. Reject unknown
  fields, invalid status/requirement/match coupling, wrong strengths, malformed
  relation data, count mismatches, forbidden raw/internal fields, and over-limit
  lists rather than coercing them.
- `useSavedJobsState` owns `skillMaps[jobId]`, `loadSkillMap`, refresh, request-order
  guards, and invalidation. Reuse its existing `selectedJobId`; do not add selected JD
  state to observability or `GraphPanel`.
- Graph-tab selection loads the saved-JD list lazily when needed, then the selected
  map. Active-CV approval, Job re-extraction/deletion, graph invalidation/rebuild
  refresh, and any selected-detail currentness signal invalidate only affected maps
  while retaining the last safe data during refresh. Evaluation never creates the map
  and no map read dispatches evaluate.
- Default `Bản đồ CV–JD` uses a deterministic React/CSS semantic layout with the
  active CV and selected Job as anchors, status counts/filters, readable assertion
  cards, and a selected evidence panel. Decorative connections may use existing SVG/
  CSS; the semantic DOM remains keyboard/screen-reader usable. Do not create a second
  force simulation or dependency.
- Filters are `Khớp chính xác`, `Liên quan`, `Thiếu bắt buộc`, `Ưu tiên chưa có`, and
  `Kỹ năng bổ sung`. UI color/icon is supplemental; text labels and evidence convey
  meaning. Empty/loading/refresh/error/stale/unavailable/no-profile/no-job states are
  explicit and preserve safe cached data.
- An explicit view switch selects `Phù hợp CV–JD` or `Kỹ thuật`. Technical mode
  composes the existing raw graph canvas/semantic list, controls, caps, and metadata.
  It may show raw IDs/canonical keys/relationship codes. Its primary Skill label is
  server `display_name`, with canonical key only in technical metadata.
- React maps only typed backend statuses to user copy. It contains no skill-name map,
  acronym expansion, alias/category registry, canonical-key title-casing, profession
  branch, or match inference from `HAS_SKILL`/`REQUIRES` edges.

### Rollout and existing data

- No migration/backfill rewrites approved JSON. Existing malformed grouped skills
  remain historical truth until the user explicitly reprocesses and approves that CV.
- Retained JDs are corrected only through existing **Re-extract JD** compare-and-swap.
  Success changes Job revision; prior evaluations become stale and no evaluate call
  occurs.
- After explicit approval/re-extraction, direct sync updates the same Candidate/Job
  identities. The existing rebuild command remains the recovery path for stale graph
  data and calls no provider.
- Local acceptance reprocesses the user-supplied regression CV and re-extracts the
  selected regression JD without committing their content or identifiers. It verifies
  the formerly grouped skills are atomic in CandidateProfile/Neo4j/map, the latest
  evaluation is stale before explicit rerun, and displayed gaps agree with actual
  source evidence. It must not assert absent JD skills as present merely to raise the
  score.

## Implementation

1. Run the current focused/full baselines, shared plan validator, and read-only
   hardcode searches. Record RED cases for a sufficiently long non-technical PDF,
   grouped CV skill lines, skills outside `kind='skills'`, matching/Neo4j divergence,
   technical-only JD recall, global seed-only graph nodes, and canonical labels.
2. Add cross-profession synthetic PDF/document/JD fixtures without modifying the
   production seed. Add failing PDF and shared atomic/grounding guard tests, then
   implement the profession-neutral digital-text gate and pure shared primitives.
3. Add failing Candidate assertion schema/batch/guard/repair/aggregation tests.
   Implement `cv_skill_projection.py` and integrate it after validated CVDocument
   creation but before atomic draft publication.
4. Remove skill parsing from `cv_document_projection.py`, grouped-name normalization,
   and matching-only expansion. Update all callers and add exact CandidateProfile →
   embedding/matching/explanation/sync/rebuild parity tests.
5. Add JD prompt/guard RED cases for marketing, sales/operations, finance/healthcare,
   bilingual, unknown punctuation, semantic labels with grounded evidence, and second-invalid repair. Reuse
   the shared guard while preserving Plan 15 extraction/retry/re-extraction behavior.
6. Audit the production seed and matching version. Remove only case-specific parsing
   aliases/relations, set the new contract version, and prove old evaluations derive
   stale with zero evaluation calls.
7. Add failing selected Candidate/Job relationship reader and integrity tests. Build
   fixed read-only Cypher, exact expected/actual comparison, mismatch states, and
   backend compatibility projection by reusing `compute_skill_coverage` facts.
8. Add strict observability schemas/service/route and API tests for active/profile/job
   gates, ready/stale/unavailable, redaction, item limit, no global seed nodes, and zero
   mutation/evaluation/provider calls. Extend raw Skill display metadata additively.
9. Add failing frontend map DTO/parser/state/request-order/invalidation tests. Extend
   the sole saved-JD API/state owner and pass its existing selection/resource through
   `ObservabilitySidebar`; do not add another hook/store/cache.
10. Split raw technical composition from `GraphPanel`, implement the default semantic
    compatibility layout, filters, counts, evidence panel, accessible mode switch,
    safe states, and `display_name` technical labels using existing Astryx/CSS/D3.
11. Add the bounded cross-profession diagnostic and focused/full regressions. Run
    static hardcode audits proving named skills occur only in fixtures/tests/optional
    seed data, not production branching or formatting logic.
12. Run full backend/frontend static/test/build gates, graph rebuild contracts, plan
    validator, Docker rebuild/health, and the synthetic browser checklist. Then, only
    as an uncommitted local acceptance, explicitly reprocess/approve the supplied CV,
    re-extract the supplied JD, rebuild if required, and explicitly re-evaluate once.
    Inspect SQLite/Neo4j/map/evidence parity and sanitized logs before handoff.

## Verification

| Check | Command or procedure | Expected evidence |
|---|---|---|
| Pre-change RED | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_pdf_extraction.py tests/unit/test_cv_skill_projection.py tests/unit/test_skill_assertion_guard.py tests/unit/test_skill_matching.py -q` | New non-technical PDF, all-section atomic skill, and no-matching-repair assertions fail for the diagnosed old behavior before production edits. |
| PDF/CV skills | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_pdf_extraction.py tests/unit/test_cv_skill_projection.py tests/unit/test_skill_assertion_guard.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py -q` | Cross-profession digital PDFs pass, image/empty/short fail, all-section source-owned atomic assertions and one repair/aggregation/publication rules pass. |
| JD/normalizer/matching | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction.py tests/unit/test_jd_extraction_guard.py tests/unit/test_skill_normalization.py tests/unit/test_skill_matching.py tests/unit/test_match_explanations.py tests/unit/test_evaluation_context.py -q` | Profession-neutral semantic labels with grounded evidence, six-code JD guard, empty-taxonomy unknown matching, no grouped expansion, explanation parity, and contract bump pass. |
| Lifecycle/sync/rebuild | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_profile_approval.py tests/integration/test_candidate_sync.py tests/integration/test_job_ingestion.py tests/integration/test_job_reextraction.py tests/integration/test_job_sync.py tests/integration/test_graph_rebuild_contracts.py tests/integration/test_job_evaluations.py -q` | Explicit approval/re-extraction, exact assertion sync/rebuild, stale evaluation with no auto-run, same identities, and failure preservation pass. |
| Selected map backend/API | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_skill_compatibility.py tests/unit/test_observability_graph.py tests/integration/test_observability_api.py -q` | Connected-only map, semantic skill labels/source evidence, all five statuses, exact relationship mismatch withholding, redaction, 200 bound, zero evaluation/mutation, and raw display metadata pass. |
| Frontend focused | `Set-Location frontend; npm test -- --run src/test/skill-compatibility-api.test.ts src/test/skill-compatibility-map.test.tsx src/test/saved-jobs-state.test.tsx src/test/observability-sidebar.test.tsx src/test/graph-presentation.test.ts src/test/graph-panel.test.tsx` | Sole selection/cache owner, strict DTO, invalidation, filters/evidence/accessibility/safe states, no canonical labels in default mode, and unchanged technical interactions pass. |
| Existing frontend regressions | `Set-Location frontend; npm test -- --run src/test/match-card.test.tsx src/test/saved-jobs-panel.test.tsx src/test/cv-manager.test.tsx src/test/observability-api.test.ts src/test/graph-interaction.test.tsx` | Match/saved-JD/CV Manager/raw graph behavior remains compatible. |
| Backend full/static | `Set-Location backend; & '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache; & '..\.venv\Scripts\python.exe' -m mypy app --no-incremental; & '..\.venv\Scripts\python.exe' -m pytest -q` | Full backend passes with fakes, no real provider in normal tests, and no schema/topology drift. |
| Frontend full/build | `Set-Location frontend; npm test -- --run; npm run lint; npm run typecheck; npm run build` | Full frontend and production build pass with no dependency or shell regression. |
| Bounded provider diagnostic | `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & '.\.venv\Scripts\python.exe' infrastructure/scripts/diagnose_cross_profession_skills.py --cases backend/tests/fixtures/skill_extraction_golden.json` | Approved synthetic profession cases report IDs/status/counts only; explicit skills are grounded/atomic, no production-seed change is needed, and no source/evidence/provider body is printed. |
| Hardcode audit | Review `rg -n -i "python|docker|engineer|technical skill|machine learning|google ads|marketing" backend/app frontend/src -g "!**/test/**" -g "!**/tests/**"` plus the changed diff and seed file. | Any occurrence is a justified framework/product string or optional seed datum; no PDF/extraction/guard/matching/frontend branch or formatter depends on a named profession/skill. |
| Plan structure | `& '.\.venv\Scripts\python.exe' 'C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py' 'docs/plans' --json` | Plans 1-16 are contiguous; Plans 1-15 hand off normally and only Plan 16 is terminal. |
| Docker health | `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180`; then `Invoke-RestMethod http://127.0.0.1:8000/api/health` | Frontend/backend/Neo4j and SQLite/filesystem/Neo4j components are healthy on the candidate build. |
| Synthetic browser map | At `http://localhost:5173`, approve an unseeded-profession synthetic CV, save/re-extract a different-profession synthetic JD, select it, open `Bản đồ CV–JD`, exercise every filter/evidence row, then switch to `Kỹ thuật`. | Correct semantic labels/source evidence and backend classes appear; no unrelated seed skill/raw key/relationship code appears in default mode; technical mode retains raw controls; no evaluate request or console error occurs. |
| Mismatch/failure browser check | Use the controlled graph fake/integration seam to remove or alter one selected skill relationship, then refresh the map. | UI shows stale/rebuild guidance and no partial compatibility items; it never repairs or claims readiness. |
| Local supplied-record acceptance | Without committing identifiers/content, use existing CV Manager/JD actions to reprocess the supplied local CV, re-extract the selected local JD, rebuild if instructed, inspect the map, and explicitly evaluate once. | Group headings are absent as skills, atomic source skills agree across approved profile/Neo4j/map, actual absent JD skills remain missing, prior evaluation was stale before the explicit rerun, and logs/output contain no raw document data. |
| Scope hygiene | `git diff --check; git status --short` plus changed-path, migration/manifest/route/tool/Agent/source-length/data/secret review | Only authorized Master/Plan 15/Plan 16 and Plan 16 implementation owners change; no database migration, dependency, new Agent/tool, auto-evaluation, global ontology, multi-candidate feature, real data, or secret appears. |

The live diagnostic is bounded semantic evidence, not a benchmark or a reason to add
profession terms to the seed. Any later product/test/config change invalidates and
reruns affected evidence.

## Handoff Contract

### Consumes

| Producer | Artifact/contract | Assumption |
|---|---|---|
| Master Version 2.2 | Profession-neutral PDF/CV/JD skill, optional-seed, selected-map, public API, UX, consistency, and rollout authority | Version 2.2 remains the architecture authority for this increment. |
| Plans 1-8 | Local runtime, one Agent, source-of-truth schemas, profile approval, normalizer, graph sync/rebuild, matching, and observability baseline | Historical ownership remains unchanged except where Version 2.2 explicitly amends it. |
| Plans 9-14 | Document-first CV Manager, active reads, saved-JD/evaluation lifecycle, readable UX, and reliable passive saving | Reuse these owners; do not reopen their unrelated scope. |
| Plan_15 | Source-grounded JD extraction, safe retained re-extraction, saved detail, same-ID sync, and explicit no-auto-evaluation | Profession-neutral changes preserve grounding, one repair, CAS, and failure truth. |
| Current user authorization | 2026-07-22 request for every profession plus full FE/BE hardcode audit/removal | Authorizes Master amendment, Plan 15 terminal replacement, and this Plan 16. |

### Produces

| Consumer | Artifact/contract | Acceptance evidence |
|---|---|---|
| Fresh portfolio review | Master Version 2.2, amended Plan 15 handoff, and `Plan_16.md` | Shared validator plus independent full portfolio review approve requirement ownership and execution readiness. |
| `task-writing-agent` after approval | `docs/tasks/task_16.md` | One authoritative task maps P16-DOM-01 through P16-REG-01 to bounded A1/A2/A3 work and evidence. |
| Future A1 implementation | Test-first PDF/CV/JD/normalizer/matching/sync/map/API/FE rollout sequence | The task reuses named owners and preserves all out-of-scope boundaries. |
| Future A2/A3 review | Independent functional and scope acceptance | Evidence proves cross-profession behavior, one skill truth, exact cross-store parity, non-technical display, explicit rollout, and no hardcoded domain repair. |

## Completion Contract

Plan 16 is complete only when a sufficiently long digital CV from every approved
synthetic profession passes the same pypdf gate without English identity,
software-role, heading, programming-language, or tool markers, while malformed,
short, punctuation-only, and image-only PDFs retain exact safe failures with no OCR.

The complete validated `CVDocument`, not one named section or delimiter parser, must
feed one bounded Candidate skill assertion stage. Every persisted Candidate and Job
skill must be atomic, source-grounded, and normalized only after its guard passes.
Unknown skills must retain display labels, direct-match, synchronize, rebuild, and
render with an empty/minimal taxonomy. Matching, explanations, embedding text,
Candidate/Job sync, rebuild, and UI may not split, promote, infer, or repair a
different skill set. JD extraction must use profession-neutral wording, semantic labels
with verbatim evidence grounding, structural atomicity, the six safe issue codes, and no technology-token
exception list while preserving Plan 15's one repair, dedupe, re-extraction, and
failure boundaries.

The selected-JD endpoint must compare exact selected Candidate/Job Neo4j
relationships with authoritative SQLite before returning a map, reuse deterministic
skill-coverage facts, include only connected/winning items with separate source
labels/evidence, fail explicitly above 200 items, and perform no provider, mutation,
repair, embedding, or evaluation work. Missing/extra/property-mismatched graph data
must return `NEO4J_REBUILD_REQUIRED` and no partial map even when node revisions
match.

The frontend must keep `useSavedJobsState` as the sole selected-JD/map cache owner.
`Bản đồ CV–JD` is the default accessible view with backend counts, all five filters,
source evidence, safe states, and no UUID/canonical/raw relationship labels or
profession dictionaries. `Kỹ thuật` retains the current bounded canvas and controls,
uses server `display_name` as the primary Skill label, and confines raw identifiers to
technical metadata. No React alias, acronym, category, canonical formatter, or match
inference may be added.

The matching contract version must make old saved evaluations stale. Existing CV/JD
records are corrected only through explicit reprocess/approval/re-extract/rebuild,
never silent JSON rewrite or automatic evaluation. Focused and full backend/frontend
static/test/build gates, cross-profession synthetic diagnostic, exact sync/rebuild and
selected-map integrity tests, shared plan validator, Docker health, synthetic browser
acceptance, optional uncommitted supplied-record acceptance, and final hardcode/scope/
data/secret review must all pass on the same candidate. One user, one active
Candidate/CV, one Agent/ToolNode, seven tools, fixed score formula, SQLite authority,
Neo4j rebuildability, explicit evaluation, and all Plan 15 failure contracts remain
unchanged. No database migration, provider/model/dependency, global ontology,
multi-candidate feature, worker/queue, automatic evaluation, real-data fixture, or
unrelated redesign is introduced.
