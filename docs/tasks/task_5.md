# JobAgent Plan 5 Execution Tasks

## Purpose

Translate `docs/plans/Plan_5.md` into the mandatory, sequential work needed to
ingest public HTTP/HTTPS or pasted Job Descriptions, retain accepted inputs,
extract and normalize structured facts, apply exact-content reuse/retry,
persist locked embeddings for scorable jobs, synchronize the rebuildable graph,
expose the fourth and fifth Agent tools, and render compact saved-job outcomes.
These tasks do not add matching, discovery, public job CRUD, background work, or
production-security scope beyond the approved local-demo limits.

## Project Context Notes

- Root `README.md` was read completely before task derivation. It records Phase
  0 and Plans 2-4 as complete; Plan 5 is the first Job/JD phase and must reuse
  their database, Agent, graph, normalization, and React conversation owners.
- `backend/app/db/models/jobs.py` and migration `0001_initial_schema` already
  own the exact `job_posts` columns, enum constants, constraints, unique content
  hash, scorable embedding coupling, and processing/quality index. Plan 5
  requires no schema change or migration.
- `backend/app/core/settings.py` and `.env.example` already expose the locked
  URL timeout/size and embedding model/dimension settings through the single
  root environment boundary. `httpx==0.28.1` and
  `langchain-openai==1.3.5` are installed; Phase 0 approved
  `trafilatura==2.1.0`, but that direct pin is not yet in
  `backend/pyproject.toml`.
- `backend/app/services/profile_extraction.py` already owns proven structured
  output, retry, repair, and sanitized provider-error patterns. Job extraction
  must reuse or safely refactor aligned shared behavior instead of copying it.
- `backend/app/services/skill_normalization.py` and
  `infrastructure/neo4j/skills_seed.yaml` are the sole deterministic skill and
  seed-relationship owners. `backend/app/graph/constraints.py` already owns the
  three uniqueness constraints and cosine/1536 Job vector index, while
  `backend/app/graph/sync_candidate.py` owns the existing Candidate/Skill sync.
- The production registry currently contains exactly three profile tools.
  Plan 5 adds only `save_job` and `query_jobs`, using the existing
  `(run_id, tool_call_id)` replay, ToolResult, Agent graph, runner, history, and
  seven-event SSE path; it adds no FastAPI endpoint.
- Durable chat history already exposes validated `ToolResult.data`. Live
  `tool_status` carries only status and summary, and the single reducer already
  has a durable `history/rehydrate` action. The saved-job UI should reuse that
  truth path rather than parse assistant prose, expand SSE, or create a second
  client store.
- `frontend/AGENTS.md` applies to Batch04: run Astryx 0.1.4 CLI discovery before
  UI work, use documented public components and tokens, avoid raw layout
  elements/internal imports, and use `Badge` only for enumerated states.
- Several shared orchestration/client files already approach or exceed 300
  lines. New Job behavior belongs in the focused Plan 5 modules; shared-file
  edits must stay at narrow integration points or make a safe focused split.
- `backend/app/db/session.py` has the shared short transaction context, but five
  services locally duplicate an injected-factory variant. JD ingestion must
  extend/reuse the database owner for injected tests rather than add a sixth
  copy. The Phase 0 diagnostic likewise already validates ordered finite
  embedding responses and must consume the production validator after Plan 5.
- A read-only repository audit reported clean baseline lint/typing/frontend and
  focused model/sync gates, plus five stale full-backend assertions: obsolete
  blanket graph/no-registry guards and a five-route health expectation that
  conflict with already-completed Plan 4. Tasks (03A)/(03B) update only stale
  assertions directly guarding roots they modify; the unrelated health-route
  failure is reported as baseline debt, not folded into Plan 5 scope.
- The existing SSE schema defines `tool_status`, but the runner does not emit
  durable tool transitions. Plan 5 both declares that capability prerequisite
  operational and requires concise live status; the user-supplied root-cause
  rule authorizes (03C) only as a bounded repair of the existing contract, not a
  new event/status/executor design.
- The deterministic quality table is recorded in (01A). For (01B), the user
  approved rejecting only absent or whitespace-only acquired text; every other
  non-empty result, including short or contact-only text, proceeds unchanged to
  later quality classification and may become processed `unscorable`. Any
  remaining `query_jobs` default/tie-break decision stays with its owning task
  and must not be silently invented.
- Compact Job output uses the existing repository `outcome` naming convention.
  Exact URL dedup hashes the final plain text stored as `raw_content`, without
  whitespace normalization; this is recorded as the smallest neutral reading
  of the Plan's fetched-content hash and persisted-content requirements.
- The source-required host rebuild command conflicts with current Compose
  runtime values: `/data/jobagent.db` is a named-volume path and
  `bolt://neo4j:7687` is Docker DNS, neither reachable from host Python. Task
  (03D) records this as an explicit run-context blocker rather than adding a
  second `.env`, copying live data, or silently changing prior runtime ownership.
- The user-supplied agent rules apply throughout: search all existing owners and
  callers before writing, reuse/refactor instead of duplicating logic, keep
  modules single-purpose, prefer the shortest source-aligned implementation,
  and fix shared behavior at its root.

## Authority and Scope

### Primary Source

- Primary authority: `docs/plans/Plan_5.md`.
- Supporting architecture authority cited by that plan:
  `docs/plans/Master_plan.md`.
- Prerequisite compatibility evidence:
  `docs/feasibility/phase_0_report.md`.
- Repository context only: root `README.md`, `backend/pyproject.toml`,
  `.env.example`, `backend/app/core/settings.py`,
  `backend/app/db/models/jobs.py`, `backend/app/services/profile_extraction.py`,
  `backend/app/services/skill_normalization.py`, `backend/app/graph/`,
  `backend/app/tools/`, `backend/app/services/tool_execution.py`,
  `frontend/src/features/chat/`, and `frontend/AGENTS.md`.

### Source Section Index

- `docs/plans/Plan_5.md > ## 1. Objective` -> persistence-first outcome,
  exact-content behavior, derived-graph boundary, and no matching.
- `docs/plans/Plan_5.md > ## 3. Prerequisites from Prior Phases` -> existing
  schema, Agent/tool, provider, normalization, graph, and settings contracts.
- `docs/plans/Plan_5.md > ## 4. Scope` and `## 5. Out of Scope` -> mandatory JD
  capabilities and prohibited security, discovery, matching, worker, CRUD, and
  near-duplicate expansion.
- `docs/plans/Plan_5.md > ## 6. Target Directory Structure` -> focused module,
  test, frontend, adapter, graph, and CLI ownership.
- `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.1 Job extraction contracts`
  through
  `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.4 Extraction, repair, and quality classification`
  -> exact schemas, bounded fetch, persistence flow, retries, normalization, and
  authoritative quality.
- `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.5 Embedding adapter and text contract`
  -> sole adapter, exact vectors, shared whitespace, and versioned Job representation.
- `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.6 Job tools`
  through
  `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.9 Frontend saved-job display`
  -> compact tool outputs, direct sync, rebuild, and Astryx display.
- `docs/plans/Plan_5.md > ## 8. Implementation Steps` and
  `docs/plans/Plan_5.md > ## 9. Verification & Testing Plan` -> required work
  order, fake-backed gates, controlled checks, and failure evidence.
- `docs/plans/Plan_5.md > ## 10. Handoff Notes for Plan 6 / Master Phase 5` ->
  reusable Job, embedding, graph, tool, and rebuild artifacts.
- `docs/plans/Master_plan.md > ### 6.2 Application table schemas` and
  `docs/plans/Master_plan.md > ### 6.4 Transaction boundaries` -> existing Job
  relational invariants and short transaction ownership.
- `docs/plans/Master_plan.md > ### 7.4 Job extraction`,
  `docs/plans/Master_plan.md > ### 7.6 JD quality rules`,
  `docs/plans/Master_plan.md > ## 8. Neo4j Derived Model`, and
  `docs/plans/Master_plan.md > ## 9. Skill Normalization` -> exact facts,
  quality, identities, relationships, and shared taxonomy.
- `docs/plans/Master_plan.md > ## 11. JD Ingestion Flow`,
  ``docs/plans/Master_plan.md > ### 13.4 `save_job```,
  ``docs/plans/Master_plan.md > ### 13.5 `query_jobs```, and
  `docs/plans/Master_plan.md > ### 13.7 Tool authorization matrix` -> accepted
  inputs, duplicate policy, exact tool behavior, and availability in every state.
- `docs/plans/Master_plan.md > ### 15.4 Tool activity display`,
  `docs/plans/Master_plan.md > ## 16. ShopAIKey Integration`, and
  `docs/plans/Master_plan.md > ### 17.1 Locked embedding contract` through
  `docs/plans/Master_plan.md > ### 17.3 Text representations` -> concise UI and
  locked provider/text rules.
- `docs/plans/Master_plan.md > ## 20. Failure and Recovery Policy` through
  `docs/plans/Master_plan.md > ## 23. Environment Configuration`,
  `docs/plans/Master_plan.md > ## 24. Local Testing Strategy`, and
  `docs/plans/Master_plan.md > ## 25. Implementation Phases > ### Phase 4 — JD ingestion, extraction, exact deduplication, and graph sync`
  -> truthful failures, SQLite-first sync, rebuild, safeguards, tests, and exit gate.
- `docs/feasibility/phase_0_report.md > ## ShopAIKey chat and embedding gate` and
  `docs/feasibility/phase_0_report.md > ## Dependency decision record > ### Phase 1 intended versions (not installed in Phase 0)`
  -> proven embedding wire contract and approved dependency versions.

### Approved Architecture and Constraints

- SQLite owns every accepted URL/text input and all Job state. Neo4j is derived,
  uses the same IDs/timestamps, and is rebuilt from SQLite without provider calls.
- Reuse the existing `job_posts` model and constraints. No migration, score
  cache, history/version table, sync ledger, retry endpoint, or `force_new` is
  permitted.
- Transactions are short. Fetching, LLM extraction/repair, embeddings, Neo4j,
  and SSE never run inside an open SQLite transaction.
- Exact SHA-256 is computed from the exact stored extracted/pasted text. Do not
  normalize content for deduplication or add near-duplicate behavior.
- A non-failed exact match is returned unchanged with no extraction, embedding,
  or graph call. A failed exact match retries the same row after clearing all
  terminal extraction/quality/embedding fields. Processed rows are terminal.
- The complete `JobPostExtraction` validates before JSON persistence. The LLM
  supplies facts/evidence only; the existing normalizer supplies Skill identity,
  and deterministic application code alone assigns `jd_quality`.
- Only processed `full|partial` rows carry the locked finite 1536-dimensional
  embedding triplet and become Job graph nodes. Processed `unscorable` and all
  non-processed rows carry no embedding and are not vector-queryable.
- One production embedding adapter, one shared whitespace normalizer, one
  versioned Job text builder, one skill normalizer, and the existing seed file
  serve Plan 5 and later Plan 6 work.
- Direct graph sync follows a terminal SQLite commit. Sync failure never rolls
  SQLite back or downgrades the Job; it returns `NEO4J_SYNC_FAILED` plus the
  established rebuild instruction.
- The application retains one Agent graph, one ToolNode, one registry, one
  tool-replay identity, one SSE contract, and one client reducer. Production
  registration becomes exactly five tools; `match_jobs` remains absent.
- Tool/history/card payloads are compact and never contain raw JD text,
  authorization headers, secrets, provider bodies, filesystem paths, or ranking.
- Normal tests use fake HTTP, structured-output, embedding, and Neo4j adapters
  plus temporary migrated SQLite. Real ShopAIKey, public network, Docker, and
  live Neo4j checks are optional and never block mandatory task acceptance.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Exact Job contracts plus bounded input and repository primitives | (01A), (01B), (01C) | Plan 4 complete; existing Plan 2 schema/settings |
| Batch02 | Validated persistence-first URL/text processing with locked embeddings | (02A), (02B), (02C), (02D) | Batch01 artifacts as noted |
| Batch03 | Direct Job graph sync, five production tools, live status transport, and complete rebuild | (03A), (03B), (03C), (03D) | Batch02 |
| Batch04 | Compact durable React/Astryx saved-job display | (04A) | Batch03 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_5_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_5_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.
- In orchestrated mode, the user-supplied cross-runtime rule applies: Codex
  writes `.agent/handoff/a1_request.md` and invokes
  `python $env:USERPROFILE\.codex\skills\orchestrator-agent\scripts\run_a1_grok.py --cwd <REPO> --envelope-file .agent\handoff\a1_request.md`; A1 runs on
  Grok, while A2/A3 and commit/approval stay on Codex. Only an explicit
  `A1_RUNTIME: codex` user instruction overrides this split.

## Mandatory Batch01 - Job Contracts and Durable Input Primitives

### Goal

Establish exact validated Job facts/quality, a constrained URL-to-text boundary,
and focused `job_posts` persistence/query primitives before provider processing
or production tools are introduced.

### Dependencies

- Plan 2 migration `0001_initial_schema`, root settings, async sessions, UUID/UTC
  helpers, and the existing `JobPost` model are present and unchanged.
- Plan 4 `SkillRef`, deterministic skill normalizer, taxonomy, and fake-provider
  patterns pass their current tests.

### Scope Boundary

This batch owns Job schemas, deterministic quality classification, bounded URL
text acquisition, the approved Trafilatura pin, and focused Job repositories. It
does not call ShopAIKey, generate embeddings, run the end-to-end ingestion
pipeline, synchronize Neo4j, register tools, expose routes, or build UI.

### Tasks

- [x] (01A): Define exact Job extraction contracts and deterministic quality classification
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.1 Job extraction contracts`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.4 Extraction, repair, and quality classification`; `docs/plans/Master_plan.md > ## 7. Pydantic Data Contracts > ### 7.4 Job extraction`; `docs/plans/Master_plan.md > ## 7. Pydantic Data Contracts > ### 7.6 JD quality rules`
  - Source Requirements:
    - Implement exact strict `JobSkill` and `JobPostExtraction` fields,
      nullability, enums, and confidence bounds using the existing `SkillRef`.
    - Evidence remains short source text; extraction contains facts only and
      never contains aliases, relationships, or `jd_quality`.
    - One deterministic classifier assigns exactly `full|partial|unscorable`
      after full extraction validation, including contact-only/insufficient
      evidence as successfully processed `unscorable` input.
  - Dependencies: Existing `backend/app/schemas/skills.py` and
    `backend/app/db/models/jobs.py` constants.
  - User Action: Approve an exact deterministic decision table that defines
    sufficient title/description, usable skill/responsibility evidence, and
    “most scoring fields,” then revise this task to record that table before A1
    writes classifier tests or code.
  - Agent Work:
    1. Search all schema/config/enum owners and every `JobPost`, `jd_quality`,
       and `extraction_json` caller; reuse strict model configuration and ORM
       vocabulary rather than creating parallel types.
    2. Add failing focused tests for exact fields, nested validation, enums,
       bounds, evidence shape, invalid extra fields, and each deterministic
       branch in the approved table.
    3. Implement the smallest focused schema and classifier modules; keep
       quality outside the Pydantic extraction payload and avoid provider,
       persistence, graph, or tool behavior in either module.
    4. Inspect serialization/classifier callers so one validated model and one
       quality owner will govern every later JSON write.
  - Output: Strict Job extraction models and one deterministic quality API for
    all later ingestion, graph, tool, and frontend projections.
  - Acceptance:
    - Valid documents round-trip with exactly the source-approved fields; bad
      enums, confidence, shapes, nullability, or extra fields fail.
    - Equivalent validated inputs always receive the same exact quality, while
      insufficient/contact-only facts classify as `unscorable` rather than a
      processing failure.
    - `jd_quality` has one implementation owner and cannot appear in serialized
      `JobPostExtraction`; Skill aliases/relationships are never LLM fields.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_jd_extraction.py tests/unit/test_jd_quality.py -q` -> exact schema and all quality branches pass.
    - Required: `Set-Location backend; python -m ruff check app/schemas/jobs.py app/services/jd_quality.py tests/unit/test_jd_extraction.py tests/unit/test_jd_quality.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "JobPostExtraction|JobSkill|jd_quality|full|partial|unscorable" backend/app backend/tests` -> one schema/quality owner and existing ORM vocabulary are reviewable.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` until the exact quality decision
    table is approved and written into this task. Qualitative source prose alone
    is not sufficient evidence for A1/A2 to invent or accept thresholds.
  - Files: `backend/app/schemas/jobs.py`, `backend/app/services/jd_quality.py`, `backend/tests/unit/test_jd_extraction.py`, `backend/tests/unit/test_jd_quality.py`

- [x] (01B): Implement bounded HTTP/HTTPS and Trafilatura/plain-text acquisition
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.2 URL fetch contract`; `docs/plans/Plan_5.md > ## 9. Verification & Testing Plan > ### Failure handling`; `docs/plans/Master_plan.md > ## 11. JD Ingestion Flow > ### 11.2 Simple URL fetching`; `docs/plans/Master_plan.md > ## 22. Local Demo Safeguards`
  - Source Requirements:
    - Accept only `http|https`, enforce the configured 10-second controlled
      timeout and 5 MB limit while streaming, and accept only `text/html` or
      `text/plain` after ignoring charset parameters.
    - Send no cookies/authentication and use no browser/JavaScript renderer.
      Decode plain text directly and pass HTML through Trafilatura main-text
      extraction using the approved direct `trafilatura==2.1.0` pin.
    - Return a stable sanitized paste-text fallback for unsupported,
      unavailable, or empty extracted text; never log headers or a full source.
      Do not add SSRF/IP-range or redirect-validation, crawler, scraper, or
      threat-model scope.
    - After decoding or HTML extraction, reject only an absent result or text
      whose `strip()` is empty. Accept every other non-empty result unchanged,
      including short or contact-only text, for later deterministic quality
      classification; do not add a length, keyword, or contact heuristic.
  - Dependencies: Existing URL settings, `httpx==0.28.1`, and Phase 0's approved
    `trafilatura==2.1.0` version evidence.
  - User Action: None. On 2026-07-14 the user approved the exact admission
    predicate recorded above before A1 implementation.
  - Agent Work:
    1. Search installed dependencies, settings validators, HTTP-client fakes,
       text-decoding/whitespace helpers, and every fetch-like caller before
       adding code; reuse the standard/client facilities already present.
    2. Add the exact Trafilatura direct pin and failing fake-transport
       tests for schemes, timeout, streamed over-limit responses, content types,
       decoding, HTML extraction, every approved admission boundary, and
       sanitized failures.
    3. Implement one focused fetch/text-acquisition service with injected
       client/transport seams and apply only the approved admission predicate.
    4. Inspect all logs/errors/callers for authorization, full-document,
       unlimited-buffering, browser, and duplicated fetch behavior.
  - Output: A fake-testable constrained URL-to-JD-text boundary with stable
    paste-text fallback and no persistence/provider/graph behavior.
  - Acceptance:
    - Unsupported schemes/types, timeout/unavailable responses, over-5-MB
      streams, and empty extraction fail predictably without unbounded buffering.
    - Supported HTML uses Trafilatura and supported plain text bypasses it;
      charset parameters do not alter the exact MIME allowlist.
    - Missing or whitespace-only acquired text returns the stable paste-text
      fallback, while short/contact-only non-empty text succeeds without a
      length or semantic heuristic and remains eligible for later `unscorable`.
    - No auth/cookies/browser/site-specific scraper, SSRF expansion, full-body
      logging, or alternate extraction dependency is introduced.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_url_fetch.py -q` -> all fake HTTP, limit, MIME, extraction, and failure cases pass without network access.
    - Required: `Set-Location backend; python -m ruff check app/services/url_fetch.py tests/unit/test_url_fetch.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "trafilatura|URL_FETCH_TIMEOUT_SECONDS|URL_MAX_RESPONSE_MB|Authorization|Cookie|text/html|text/plain" backend/pyproject.toml backend/app backend/tests` -> exact pin/settings and absence of secret-bearing fetch behavior are reviewable.
    - Optional: `python -m pip install -e .\backend` -> the approved direct Trafilatura pin resolves in the user's local environment; network/package-index availability does not replace fake test evidence.
  - Blocked Condition: A resolver conflict for `trafilatura==2.1.0` blocks
    execution; report the exact resolver evidence and do not choose another
    extractor/version or add a browser fallback. Otherwise None.
  - Files: `backend/pyproject.toml`, `backend/app/services/url_fetch.py`, `backend/tests/unit/test_url_fetch.py`

- [x] (01C): Implement focused Job repository transitions, exact-hash lookup, and compact queries
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.3 Persistence-first ingestion and exact deduplication`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.6 Job tools`; ``docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.2 Application table schemas > #### `job_posts```; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.4 Transaction boundaries`
  - Source Requirements:
    - Reuse the existing Job model, UUID/UTC helpers, status/quality constants,
      unique content hash, scorable embedding coupling, and migrated schema.
    - Provide focused primitives for raw/URL creation, exact-hash and ID reads,
      failed-row clearing/retry, legal status transitions, URL-placeholder
      deletion, terminal writes, and newest deterministic filtered queries.
    - Repositories participate in caller-owned short transactions and never
      commit, call HTTP/providers/Neo4j, validate LLM output, or expose raw
      content through compact query projections.
  - Dependencies: (01A); existing async-session/repository conventions and
    migration `0001_initial_schema`.
  - User Action: None.
  - Agent Work:
    1. Search every ORM Job caller and the attachment/profile/chat repository
       patterns; inspect all model constraints and shared UUID/UTC helpers before
       defining a repository API.
    2. Add migrated-SQLite tests for placeholder/raw creation, hash/ID lookup,
       legal transition timestamps, failed-field clearing, deletion, filters,
       limit, and deterministic newest ordering.
    3. Implement only the narrow flush-only/read primitives needed by later
       orchestration; keep transactions, full-model validation, external work,
       and ToolResult shaping in their proper service/tool owners.
    4. Inspect every Job write/read caller and prove there is no second status,
       hash, transaction, query-order, or compact-projection implementation.
  - Output: One focused persistence API over the unchanged `job_posts` schema.
  - Acceptance:
    - Repository tests use the migrated temporary database and preserve every
      existing constraint; no migration or `create_all()` path appears.
    - Failed retry clearing removes failure/extraction/quality/all embedding
      terminal fields on the same row and legal transition timestamps update in UTC.
    - Filtered reads use exact database vocabulary, limit `1..50`, deterministic
      newest order, and compact data without raw content or embeddings.
    - Repository functions flush/read/delete only and contain no commit,
      provider, HTTP, graph, Agent, or presentation logic.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_jobs_repository.py tests/unit/test_job_post_model.py -q` -> repository behavior and unchanged schema constraints pass.
    - Required: `Set-Location backend; python -m ruff check app/repositories/jobs.py tests/integration/test_jobs_repository.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "JobPost|raw_content_hash|processing_status|jd_quality|commit\(|create_all" backend/app/repositories backend/app/services backend/tests/integration/test_jobs_repository.py` -> one repository owner, caller-owned commits, and no schema shortcut are reviewable.
  - Blocked Condition: None.
  - Files: `backend/app/repositories/jobs.py`, `backend/tests/integration/test_jobs_repository.py`

## Mandatory Batch02 - Persistence-First Extraction and Embeddings

### Goal

Turn each accepted raw-text or URL input into one durable processed/failed Job
through validated structured extraction, shared normalization, deterministic
quality, and locked embeddings, with exact duplicate return/retry semantics.

### Dependencies

- Batch01 Job schemas, quality classifier, URL acquisition boundary, and Job
  repository primitives are A2-accepted.
- Existing fake ShopAIKey patterns, single settings boundary, Skill normalizer,
  and temporary migrated-SQLite harness remain available.

### Scope Boundary

This batch owns structured JD extraction, the sole production embedding adapter,
shared representation text, and complete SQLite-first text/URL orchestration. It
does not synchronize Neo4j, register production tools, add routes, rebuild the
graph, create frontend UI, or implement matching/retrieval.

### Tasks

- [ ] (02A): Implement validated structured JD extraction, repair, and shared skill normalization
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.1 Job extraction contracts`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.4 Extraction, repair, and quality classification`; `docs/plans/Master_plan.md > ## 16. ShopAIKey Integration > ### 16.2 Startup/diagnostic compatibility checks`; `docs/plans/Master_plan.md > ## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Use locked `gpt-4o-mini` structured extraction with full Pydantic
      validation, at most one schema-repair request, and at most one retry for a
      timeout/rate-limit failure before returning a stable sanitized failure.
    - Extract facts and short copied evidence only. Normalize every required and
      preferred skill through Plan 4's one normalizer; the LLM never supplies
      canonical aliases, categories, relationships, or quality.
    - Keep raw JD text transient at this service boundary and make normal tests
      deterministic through an injected fake structured-output invoker.
  - Dependencies: (01A); existing `profile_extraction.py` provider/repair
    patterns and `skill_normalization.py` owner.
  - User Action: None for required tests. The retained live ShopAIKey diagnostic is optional.
  - Agent Work:
    1. Search `profile_extraction.py`, the ShopAIKey chat adapter, provider error
       classifier/retry loop, prompts, fake invokers, normalizer APIs, and all
       callers. Extract the stable provider classification plus one-retry loop
       into `app/services/provider_retry.py`; keep domain-specific schema repair
       prompts/coercion in their profile/JD owners.
    2. Add failing fake-invoker tests for valid output, invalid output plus one
       repair, repair exhaustion, one retryable provider failure, non-retryable
       failure, evidence/extra-field rejection, and deterministic normalization.
    3. Implement a focused JD extraction service that returns only a validated
       normalized `JobPostExtraction` or a stable sanitized error and never
       writes SQLite, calls embeddings/Neo4j, or assigns quality.
    4. Inspect all old/new structured-extraction callers so shared provider
       classification/retry has one owner and profile behavior remains unchanged.
  - Output: One fake-testable structured JD extraction/normalization boundary.
  - Acceptance:
    - A valid fake response produces the exact normalized model; all skill
      identities come from the existing normalizer and preserve source evidence.
    - Invalid schema makes no more than one repair request; a retryable provider
      error retries no more than once; exhausted/error paths expose no secret or
      full provider/source body.
    - The service performs no persistence, embedding, graph, ToolResult, route,
      or quality-classification work; both domains use the exact shared provider
      retry/error owner without sharing domain prompts or schemas.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_jd_extraction.py tests/unit/test_skill_normalization.py tests/unit/test_profile_extraction.py -q` -> JD extraction and retained profile/normalizer behavior pass with fakes.
    - Required: `Set-Location backend; python -m ruff check app/services/provider_retry.py app/services/jd_extraction.py app/services/profile_extraction.py tests/unit/test_jd_extraction.py tests/unit/test_profile_extraction.py; python -m mypy app` -> focused shared retry/extraction lint and application typing pass.
    - Required: `rg -n "with_structured_output|schema.*repair|rate|timeout|SkillNormalizer|JobPostExtraction" backend/app/services backend/app/adapters backend/tests/unit` -> bounded retry/repair and one normalization/provider-error path are reviewable.
    - Optional: `python infrastructure/scripts/diagnose_shopaikey.py` -> the user may explicitly reconfirm the sanitized real-provider compatibility marker from an ignored root `.env`; it is not a normal-test prerequisite.
  - Blocked Condition: The locked provider/model no longer satisfies the
    Phase 0 structured-output contract. Report a sanitized minimal compatibility
    failure; do not switch provider/model, relax validation, or add unbounded repair.
  - Files: `backend/app/services/provider_retry.py`, `backend/app/services/profile_extraction.py`, `backend/app/services/jd_extraction.py`, `backend/tests/unit/test_profile_extraction.py`, `backend/tests/unit/test_jd_extraction.py`

- [ ] (02B): Implement the sole production embedding adapter and versioned Job representation
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.5 Embedding adapter and text contract`; `docs/plans/Master_plan.md > ## 16. ShopAIKey Integration > ### 16.1 Configuration`; `docs/plans/Master_plan.md > ## 17. Embedding and Retrieval > ### 17.1 Locked embedding contract`; `docs/plans/Master_plan.md > ## 17. Embedding and Retrieval > ### 17.3 Text representations`
  - Source Requirements:
    - One production adapter uses the configured ShopAIKey OpenAI-compatible
      endpoint, `text-embedding-3-small`, `dimensions=1536`, and float encoding
      for ordered scalar/batch inputs without model/dimension fallback.
    - Validate response count/index order, exactly 1536 finite floats per input,
      and stable sanitized timeout/rate-limit/invalid-response errors.
    - One shared whitespace normalizer and explicit
      `build_job_embedding_text_v1` concatenate title, summary,
      responsibilities, required skills, and preferred skills in that order,
      using canonical display names and deterministic separators with no E5 prefix.
  - Dependencies: (01A); locked settings, Phase 0 embedding evidence, and the
    existing `langchain-openai==1.3.5`/`httpx==0.28.1` dependency surface.
  - User Action: None for required deterministic tests. Live provider smoke is optional.
  - Agent Work:
    1. Search the Phase 0 embedding diagnostic (including its existing ordered
       finite-vector validators), installed OpenAI-compatible client APIs,
       settings, text/whitespace helpers, and every embedding-like caller; move
       shared validation into the production owner and make the diagnostic
       consume it rather than copying the proven contract.
    2. Add failing tests for scalar and distinct ordered batch inputs, explicit
       request model/dimensions/encoding, count/index mismatch, short/long/non-
       finite vectors, sanitized errors, whitespace normalization, field order,
       canonical display names, deterministic separators, and version marking.
    3. Implement one focused adapter plus embedding-vector validation schema and
       one representation module; do not place provider calls in schemas or text
       builders and do not create a Candidate builder before Plan 6.
    4. Inspect every adapter/text caller and export a small stable API that Plan
       6 can extend without copying whitespace or transport behavior.
  - Output: A locked ordered embedding API and deterministic versioned Job text contract.
  - Acceptance:
    - Scalar and batch results preserve input order and contain exactly 1536
      finite floats; any count/index/vector violation fails before persistence.
    - The request always carries configured locked model, 1536 dimensions, and
      float encoding; no alternate client/model/dimension/local fallback exists.
    - Equivalent structured Job facts produce byte-identical v1 text with the
      exact approved field order and no raw HTML, E5 prefix, or quality field.
    - Whitespace normalization, vector validation, and provider transport each
      have one production owner; the retained diagnostic imports the same
      validator and preserves its sanitized PASS/FAIL contract.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_embedding_adapter.py tests/unit/test_embedding_text.py -q` -> adapter validation/order and representation determinism pass with fakes.
    - Required: `Set-Location backend; python -m ruff check app/adapters/shopaikey_embeddings.py app/schemas/embeddings.py app/services/embedding_text.py tests/unit/test_embedding_adapter.py tests/unit/test_embedding_text.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "OpenAIEmbeddings|/v1/embeddings|encoding_format|dimensions|isfinite|build_job_embedding_text_v1|normalize.*whitespace" backend/app backend/tests infrastructure/scripts/shopaikey_diag` -> one adapter/normalizer and exact wire/text contract are reviewable.
    - Optional: `python infrastructure/scripts/diagnose_shopaikey.py` -> user-managed live scalar/batch compatibility remains separately verifiable without entering automated acceptance.
  - Blocked Condition: None. A client limitation must be handled inside the one
    approved adapter using already-installed dependencies; it does not authorize
    a second adapter, alternate provider/model, or changed dimensions.
  - Files: `backend/app/adapters/shopaikey_embeddings.py`, `backend/app/schemas/embeddings.py`, `backend/app/services/embedding_text.py`, `infrastructure/scripts/shopaikey_diag/embeddings.py`, `backend/tests/unit/test_embedding_adapter.py`, `backend/tests/unit/test_embedding_text.py`

- [ ] (02C): Implement raw-text persistence-first selection, processing, and exact retry
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.3 Persistence-first ingestion and exact deduplication`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.4 Extraction, repair, and quality classification`; `docs/plans/Plan_5.md > ## 9. Verification & Testing Plan > ### Backend commands`; `docs/plans/Master_plan.md > ## 11. JD Ingestion Flow > ### 11.3 Persistence-first processing`; `docs/plans/Master_plan.md > ## 11. JD Ingestion Flow > ### 11.4 Exact duplicate policy`
  - Source Requirements:
    - Require non-whitespace pasted text, compute exact SHA-256 before insert,
      and either return an existing non-failed row unchanged, retry an existing
      failed row in place, or persist one new `received` row before processing.
    - Failed retry clears failure, extraction, quality, and all embedding fields
      on the same ID. A new/selected row enters `processing` in a short
      transaction before any extraction/embedding call.
    - Validate/extract, normalize, classify, embed only `full|partial`, and write
      one processed/failed terminal state in a short transaction. Accepted raw
      text remains after every provider/schema/embedding failure.
  - Dependencies: (01A), (01C), (02A), and (02B).
  - User Action: None.
  - Agent Work:
    1. Search every Job write/transaction/hash/status caller plus the existing
       five private `_short_transaction` copies and root `session_scope`;
       minimally extend the database-owned context to accept an injected factory
       for tests and use it here instead of adding a sixth transaction helper.
    2. Add migrated-SQLite/fake tests for new raw input, non-failed duplicate
       return with zero external calls, failed same-ID retry and field clearing,
       different-content insertion, quality branches, exact embedding coupling,
       and extraction/schema/embedding failures retaining raw text.
    3. Implement a small orchestration service that coordinates existing focused
       owners, commits before/after external work only, validates vector/model/
       dimensions before the terminal write, and leaves graph sync/tool shaping
       to Batch03.
    4. Inspect all service/repository callers for duplicate hash logic, commits
       around external calls, reprocessing of terminal rows, raw-data leakage,
       or a growing God file. Keep `jd_ingestion.py` as thin orchestration over
       the exact focused owners already listed; do not create an unlisted module.
  - Output: Durable raw-text ingestion through terminal SQLite state with exact
    duplicate return and failed-row retry behavior.
  - Acceptance:
    - The first accepted text is committed before external work and remains on
      the same row after every tested extraction/embedding failure.
    - A non-failed exact duplicate returns the same ID/fields with no extraction,
      embedding, update, or new row; a failed duplicate retries the same ID after
      clearing every terminal field.
    - Processed `full|partial` rows have a valid locked embedding triplet;
      processed `unscorable` and failed rows have all embedding fields null.
    - No transaction spans an external call, processed rows cannot be
      reprocessed, and no normalized/near-duplicate or `force_new` behavior exists.
    - JD ingestion uses the shared database transaction context with an injected
      factory; it defines no local `_short_transaction` copy and existing global
      `session_scope()` callers remain compatible.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_job_ingestion.py tests/integration/test_jobs_repository.py -q` -> raw persistence, duplicate, retry, quality, embedding, and durable failure cases pass with fakes.
    - Required: `Set-Location backend; python -m ruff check app/db/session.py app/services/jd_ingestion.py app/repositories/jobs.py tests/integration/test_job_ingestion.py; python -m mypy app` -> shared transaction/orchestration/repository lint and application typing pass.
    - Required: `Set-Location backend; python -m pytest tests/integration/test_database_pragmas.py -q` -> the refactored shared session context retains connection and caller behavior.
    - Required: `rg -n "sha256|raw_content_hash|received|processing|processed|failed|commit\(|embed|extract" backend/app/services/jd_ingestion.py backend/app/repositories/jobs.py backend/tests/integration/test_job_ingestion.py` -> exact selection, short transaction, and terminal coupling are reviewable.
  - Blocked Condition: None.
  - Files: `backend/app/db/session.py`, `backend/app/services/jd_ingestion.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_database_pragmas.py`

- [ ] (02D): Complete URL placeholder, fetched-hash reuse, and durable fetch-failure flow
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.2 URL fetch contract`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.3 Persistence-first ingestion and exact deduplication`; `docs/plans/Plan_5.md > ## 9. Verification & Testing Plan > ### Failure handling`; `docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.4 Transaction boundaries`; `docs/plans/Master_plan.md > ## 11. JD Ingestion Flow`
  - Source Requirements:
    - Commit a `received` URL placeholder with the original URL and null content/
      hash before fetching. Fetch outside a transaction; fetch failure marks that
      placeholder `failed` with a stable code and paste-text instruction.
    - Hash the exact acquired text. On an existing non-failed match, delete the
      placeholder and return the existing row without processing; on an existing
      failed match, delete the placeholder and retry that same failed row; on no
      match, persist content/hash into the placeholder and process it normally.
    - Provider/embedding failure after acquisition retains the fetched text/hash;
      placeholder deletion occurs only when another exact row was selected.
  - Dependencies: (01B) and (02C).
  - User Action: None for required fake-backed tests. Controlled public URL checks are optional.
  - Agent Work:
    1. Search all (01B)/(02C) interfaces, Job repository placeholder operations,
       transaction callers, and fake HTTP fixtures before extending the single
       ingestion owner.
    2. Extend tests for placeholder visibility before fetch, unsupported/
       unavailable/empty fetch failure, new fetched content, URL-to-text and
       URL-to-URL exact matches, non-failed zero-call return, failed same-ID
       retry, placeholder deletion, and retained acquired text after later failure.
    3. Extend the orchestration service with the narrow URL selection path,
       reusing the exact downstream processing pipeline from (02C) rather than
       copying extraction/quality/embedding/terminal-write logic.
    4. Inspect every placeholder/hash/delete/processing caller for orphan rows,
       wrong-row retry, external work in a transaction, or full URL/body leakage.
  - Output: One complete persistence-first ingestion service for exactly one URL
    or pasted-text input, still unregistered as a production tool.
  - Acceptance:
    - Every submitted URL has a committed placeholder before fake fetch begins;
      fetch failure leaves that URL row failed and asks for pasted text.
    - Exact fetched content selects one existing row with the source-approved
      return/retry behavior and always deletes only the temporary placeholder.
    - Unique fetched content remains on its placeholder row through processing;
      later failures retain URL, exact text, and hash with no duplicate row.
    - URL/text share one downstream processing implementation, and no site-
      specific/browser/security-expansion or public route is introduced.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_url_fetch.py tests/integration/test_job_ingestion.py -q` -> all URL placeholder/fetch/hash/duplicate/failure cases pass without network access.
    - Required: `Set-Location backend; python -m ruff check app/services/url_fetch.py app/services/jd_ingestion.py tests/unit/test_url_fetch.py tests/integration/test_job_ingestion.py; python -m mypy app` -> focused lint and application typing pass.
    - Required: `rg -n "source_url|placeholder|raw_content_hash|delete|paste|fetch" backend/app/services/jd_ingestion.py backend/app/repositories/jobs.py backend/tests/integration/test_job_ingestion.py` -> persistence-before-fetch and exact placeholder disposition are reviewable.
    - Optional: submit one supported public URL and one pasted synthetic JD through a focused local service smoke -> each leaves durable truthful SQLite state; unavailable network does not block required acceptance.
  - Blocked Condition: None.
  - Files: `backend/app/services/jd_ingestion.py`, `backend/tests/integration/test_job_ingestion.py`

## Mandatory Batch03 - Derived Job Graph, Tools, and Rebuild

### Goal

Project scorable terminal Jobs into the existing derived graph, expose compact
replay-safe `save_job`/`query_jobs` capabilities through the one Agent runtime,
and complete a safe provider-free rebuild of Candidate/Job/Skill state.

### Dependencies

- Batch02 complete ingestion pipeline and locked Job embeddings are A2-accepted.
- Existing graph driver/schema, Candidate sync, skill taxonomy, tool execution/
  replay, Agent dependency injection, and chat history contracts remain intact.

### Scope Boundary

This batch owns post-commit Job graph projection, the fourth/fifth production
tools, exact five-tool registration, the shared durable tool-status SSE path,
and the one local rebuild service/CLI. It does not add matching/retrieval,
Candidate embeddings, graph repair during reads, public routes,
workers/queues/ledgers, alternate models, or frontend rendering.

### Tasks

- [ ] (03A): Synchronize scorable Job/Skill graph data idempotently after SQLite commit
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.7 Direct Job graph synchronization`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.3 Persistence-first ingestion and exact deduplication`; `docs/plans/Master_plan.md > ## 8. Neo4j Derived Model`; `docs/plans/Master_plan.md > ## 21. Direct SQLite-to-Neo4j Synchronization > ### 21.1 Direct sync rule`; `docs/plans/Master_plan.md > ## 21. Direct SQLite-to-Neo4j Synchronization > ### 21.2 Local failure behavior`
  - Source Requirements:
    - After a processed `full|partial` SQLite commit, parameterized idempotent
      Cypher MERGEs `Job{id=<SQLite UUID>}`, copies approved properties and the
      exact finite embedding, and sets `source_updated_at=job_posts.updated_at`.
    - Replace only that Job's `REQUIRES`/`PREFERS` relationships, MERGE normalized
      Skills, preserve confidence/evidence, and reuse only the approved seed
      Skill/`RELATED_TO` projection. Unscorable/failed Jobs are never synced.
    - A graph failure leaves the processed row unchanged and returns the one
      shared `NEO4J_SYNC_FAILED` contract plus rebuild instruction. Exact
      duplicate return does not call sync or create another node.
  - Dependencies: (02D); existing `constraints.py`, `sync_candidate.py`, graph
    driver, and skill normalizer/taxonomy.
  - User Action: None for required fake-driver tests. Live Neo4j is optional.
  - Agent Work:
    1. Search every graph module/test and all seed Skill/`RELATED_TO`, driver
       protocol, result-consumption, timestamp, and Neo4j failure helpers. Move
       the smallest genuinely shared graph projection primitives out of
       `sync_candidate.py` so Job sync/rebuild can reuse them without requiring
       an active Candidate or duplicating Cypher/business logic.
    2. Add fake-driver tests for exact parameters, finite vector, IDs/timestamp,
       required/preferred replacement, unknown/seed Skills, approved related
       edges, repeat idempotency, unscorable exclusion, duplicate no-op, and
       graph failure after committed SQLite truth.
    3. Implement focused `sync_job` and connect it only after a scorable terminal
       commit in the ingestion service; keep SQLite/provider calls out of graph
       modules and graph calls out of repositories/transactions.
    4. Replace stale blanket “no domain graph behavior” guards in
       `test_graph_setup.py` with precise base-DDL ownership checks, then inspect
       Candidate/Job/rebuild callers so shared graph behavior remains one owner.
  - Output: One idempotent Job/Skill projection path with truthful post-commit failure.
  - Acceptance:
    - Repeating a sync yields one Job identity and current relationships with
      exact SQLite UUID/UTC revision, normalized Skills, evidence, and embedding.
    - Only the target Job's relationships are cleared/rebuilt; fixed DDL stays in
      `constraints.py`, and unknown skills receive no invented related edge.
    - Candidate sync still works and the approved seed can be projected even
      when no Candidate exists; shared graph constants/helpers are not copied.
    - A fake graph error returns `NEO4J_SYNC_FAILED`/rebuild guidance after the
      processed SQLite row is visible and never changes it to failed.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_job_sync.py tests/integration/test_job_ingestion.py tests/integration/test_candidate_sync.py tests/unit/test_graph_setup.py -q` -> Job/Candidate sync, post-commit failure, and precise schema ownership pass with fakes.
    - Required: `Set-Location backend; python -m ruff check app/graph/sync_job.py app/graph/sync_candidate.py app/graph/sync_shared.py app/services/jd_ingestion.py tests/integration/test_job_sync.py tests/unit/test_graph_setup.py; python -m mypy app` -> shared graph and integration lint/typing pass.
    - Required: `rg -n "MERGE|REQUIRES|PREFERS|RELATED_TO|source_updated_at|NEO4J_SYNC_FAILED|rebuild_neo4j" backend/app/graph backend/app/services/jd_ingestion.py backend/tests` -> parameterized ownership, reuse, and truthful failure are reviewable.
  - Blocked Condition: None.
  - Files: `backend/app/graph/sync_shared.py`, `backend/app/graph/sync_candidate.py`, `backend/app/graph/sync_job.py`, `backend/app/services/jd_ingestion.py`, `backend/tests/integration/test_job_sync.py`, `backend/tests/integration/test_job_ingestion.py`, `backend/tests/integration/test_candidate_sync.py`, `backend/tests/unit/test_graph_setup.py`

- [ ] (03B): Expose compact replay-safe Job tools and register exactly five production tools
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.6 Job tools`; `docs/plans/Plan_5.md > ## 4. Scope`; `docs/plans/Plan_5.md > ## 5. Out of Scope`; ``docs/plans/Master_plan.md > ## 13. Agent-Facing Tool Contracts > ### 13.4 `save_job```; ``docs/plans/Master_plan.md > ## 13. Agent-Facing Tool Contracts > ### 13.5 `query_jobs```; `docs/plans/Master_plan.md > ## 13. Agent-Facing Tool Contracts > ### 13.7 Tool authorization matrix`
  - Source Requirements:
    - `save_job` validates exactly one of `url|text`, requires no approval or
      active profile/draft, calls the complete ingestion/direct-sync service,
      and uses the existing durable tool execution/replay identity.
    - Its compact result contains `job_id`, nullable title/company/source URL,
      exact processing status/quality, `outcome=created|returned|retried`, and
      truthful SQLite/sync state. A post-commit sync failure is a failed
      ToolResult with `NEO4J_SYNC_FAILED`, `sqlite_committed=true`, and no raw JD.
    - `query_jobs` is read-only, validates optional ID/status/quality plus limit
      `1..50`, and returns compact newest deterministic rows without raw
      content/embeddings. The source does not select its default or tie-breaker.
    - Production registration becomes exactly the three profile tools followed
      by `save_job` and `query_jobs`; `match_jobs` and synthetic tools remain absent.
  - Dependencies: (03A); existing ToolResult/tool-execution/replay, registry,
    dependency injection, Agent graph, prompt, and history owners.
  - User Action: Approve the exact `query_jobs` default limit and deterministic
    newest tie-break order, then revise this task to record both before A1
    defines the public tool schema/query tests.
  - Agent Work:
    1. Search all profile tool factories, `execute_tool`/replay callers,
       registry/dependency construction, prompt tool-name projection, compact
       result schemas, authorization tests, and every assertion about production
       tool count before defining the Job tool boundary.
    2. Add tests for exactly-one input, all profile/draft authorization states,
       compact created/returned/retried and failed/sync-failed results, query
       filters/approved default/order, raw-data exclusion, same-call replay, and
       exact five production tool names/order.
    3. Implement strict compact Job input/output models and focused tool
       factories that close over existing service dependencies, call the one
       execution/replay owner, and never call FastAPI routes or add idempotency.
    4. Wire the two tools through the current registry/dependency seam and update
       every affected three-tool/empty-registry caller assertion, including the
       stale Plan 3/4 assertion in `test_profile_extraction.py`; prove by route
       inspection that Plan 5 adds no endpoint, and do not absorb the unrelated
       pre-existing health-route test failure or weaken runtime invariants.
  - Output: Exactly five production tools with compact durable Job outcomes and
    unchanged one-Agent/tool-replay architecture.
  - Acceptance:
    - Production registry names are exactly `propose_profile_from_cv`,
      `propose_profile_update`, `commit_profile_draft`, `save_job`, and
      `query_jobs`; no sixth/domain/synthetic tool is present.
    - `save_job` works in every Master authorization state, rejects both/neither
      input, and replay of the same `(run_id, tool_call_id)` performs no second
      fetch/extraction/embedding/SQLite/Neo4j side effect.
    - ToolResult success/failure coupling is exact; sync-failed output reports
      committed processed truth without false graph success.
    - Query validation/order/filtering follows the approved exact contract and all result,
      arguments-summary, history, and SSE surfaces exclude raw JD/embedding data.
    - No job route, second registry/executor/idempotency key, approval, matching
      tool, or status alias is introduced.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_job_tools.py tests/integration/test_job_ingestion.py tests/integration/test_tool_replay.py tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py tests/integration/test_profile_approval.py tests/unit/test_agent_graph.py tests/unit/test_profile_extraction.py -q` -> compact tools, authorization, replay, exact registry, and retained profile/chat paths pass.
    - Required: `Set-Location backend; python -m ruff check app/schemas/jobs.py app/tools/jobs.py app/tools/registry.py app/api/dependencies.py app/agent/graph.py tests/integration/test_job_tools.py tests/unit/test_agent_graph.py tests/unit/test_profile_extraction.py; python -m mypy app` -> tool/registry integration lint and application typing pass.
    - Required: `rg -n "save_job|query_jobs|match_jobs|production_registry|raw_content|embedding_json|outcome|sqlite_committed|sync_ok" backend/app backend/tests` -> exact tool set, compact contract, replay path, and prohibited data are reviewable.
    - Required: `rg -n "@router\.(get|post|put|patch|delete)|include_router|/api/jobs" backend/app` -> Plan 5 registers no public Job route and leaves the existing endpoint boundary unchanged.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` until the query default and
    deterministic tie-break order are approved and written into this task.
  - Files: `backend/app/schemas/jobs.py`, `backend/app/tools/jobs.py`, `backend/app/tools/registry.py`, `backend/app/api/dependencies.py`, `backend/app/agent/graph.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_tool_replay.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/integration/test_interrupt_resume.py`, `backend/tests/integration/test_profile_approval.py`, `backend/tests/unit/test_agent_graph.py`, `backend/tests/unit/test_profile_extraction.py`

- [ ] (03C): Repair the unmet durable tool-status prerequisite on the existing SSE path
  - Source of Truth: `docs/plans/Plan_5.md > ## 3. Prerequisites from Prior Phases`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.6 Job tools`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.9 Frontend saved-job display`; ``docs/plans/Master_plan.md > ## 6. SQLite Database Contract > ### 6.2 Application table schemas > #### `tool_executions```; `docs/plans/Master_plan.md > ## 14. Public FastAPI Boundary > ### 14.2 SSE contract`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.4 Tool activity display`
  - Source Requirements:
    - Repository evidence shows the Plan 5 prerequisite is not operational: the
      approved `tool_status` schema/client exist, but no runner emission owner
      exists. This task repairs only that missing transport seam under the
      user's root-cause rule; it does not redesign the prerequisite contract.
    - Emit validated `tool_status` events from the same durable execution that
      owns `(run_id, tool_call_id)`, carrying the persisted execution UUID/name,
      exact `pending|running|completed|failed` state, terminal duration/summary,
      and failure code coupling.
    - Preserve ordered transitions and replay truth. An approval interrupt keeps
      the one row `running`; its accepted resume terminalizes that row. Re-entry
      of a terminal invocation may project stored terminal truth but never repeat
      a side effect or create another execution/event identity.
    - Keep the existing seven event names and strict payload. Tool status never
      carries raw arguments/documents, full ToolResult data, secrets, or stacks;
      compact saved-job data remains a durable-history concern for Batch04.
  - Dependencies: (03B); existing tool repository/service, ToolNode graph,
    runner, chat SSE framing, and frontend status parser.
  - User Action: None.
  - Agent Work:
    1. Search every tool status transition, ToolNode/tool-factory invocation,
       runner stream callback, chat transport, SSE schema, replay, interrupt,
       and client parser caller; confirm the existing schema has no emission
       owner before changing the shared root.
    2. Add fake-tool integration tests for pending/running/completed, failed,
       interrupt/running/resume/completed, terminal replay, concurrent identity,
       event ordering/dedup IDs, duration/summary/error coupling, and raw-data
       exclusion across profile and Job tools.
    3. Implement one request-scoped status publication seam around the existing
       durable transitions and merge it into the one runner/SSE iterator. Do not
       add a second executor, polling store, event name, client state machine, or
       non-durable tool identity.
    4. Inspect every changed shared caller and rerun retained tool replay,
       Agent-runner, interrupt/resume, chat API/history, and profile approval
       tests so the root repair is correct for all tools, not only `save_job`.
  - Output: Live, durable, replay-safe tool activity over the already-approved
    `tool_status` SSE contract.
  - Acceptance:
    - A normal fake tool produces ordered statuses with one durable execution ID
      and exact terminal duration/summary; failure uses exact coupled error code.
    - An interrupted approval emits/retains `running` and the accepted resume
      emits one terminal status on the same ID; replay performs no side effect.
    - Job and profile tools use the same publication/execution owner, and client
      parsers accept events without a new status alias or second store.
    - No raw argument/document, ToolResult data, secret, provider body, or stack
      appears in an SSE payload or log.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/unit/test_sse_contract.py tests/integration/test_agent_runner.py tests/integration/test_tool_replay.py tests/integration/test_interrupt_resume.py tests/integration/test_chat_api.py tests/integration/test_chat_history.py tests/integration/test_job_tools.py tests/integration/test_profile_approval.py -q` -> strict ordered status, replay, interrupt, and all tool callers pass with fakes.
    - Required: `Set-Location backend; python -m ruff check app/services/tool_execution.py app/agent/runner.py app/services/chat_turns.py app/schemas/sse.py app/tools/profile.py app/tools/jobs.py tests/integration/test_agent_runner.py tests/integration/test_tool_replay.py tests/integration/test_chat_api.py; python -m mypy app` -> shared status transport lint and application typing pass.
    - Required: `rg -n "tool_status|pending|running|completed|failed|tool_execution_id|tool_call_id|result_json|raw_content" backend/app/agent backend/app/services backend/app/tools backend/tests/integration` -> one durable transition/publication owner and safe payload are reviewable.
  - Blocked Condition: The pinned LangGraph ToolNode/runtime cannot expose a
    request-scoped transition seam without replacing the existing executor or
    durable identity. Report a minimal failing fake-tool trace and installed
    version evidence; do not add parallel execution or client state.
  - Files: `backend/app/services/tool_execution.py`, `backend/app/agent/runner.py`, `backend/app/services/chat_turns.py`, `backend/app/schemas/sse.py`, `backend/app/tools/profile.py`, `backend/app/tools/jobs.py`, `backend/app/tools/registry.py`, `backend/app/api/dependencies.py`, `backend/tests/integration/test_agent_runner.py`, `backend/tests/integration/test_tool_replay.py`, `backend/tests/integration/test_interrupt_resume.py`, `backend/tests/integration/test_chat_api.py`, `backend/tests/integration/test_chat_history.py`, `backend/tests/integration/test_job_tools.py`, `backend/tests/integration/test_profile_approval.py`

- [ ] (03D): Complete the safe provider-free Neo4j rebuild service and thin CLI
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.8 Rebuild command`; `docs/plans/Plan_5.md > ## 9. Verification & Testing Plan > ### Backend commands`; `docs/plans/Master_plan.md > ## 21. Direct SQLite-to-Neo4j Synchronization > ### 21.3 Rebuild command`; `docs/plans/Master_plan.md > ## 22. Local Demo Safeguards`; `docs/plans/Master_plan.md > ## 24. Local Testing Strategy > ### 24.5 Local verification commands`
  - Source Requirements:
    - Before deleting graph data, validate every processed `full|partial` stored
      embedding against locked model/dimensions and exact finite vector length;
      mismatch exits non-zero with configuration-restoration guidance and no
      provider call, SQLite mutation, or graph clear.
    - Clear only JobAgent `Candidate`, `Job`, and `Skill` nodes/relationships,
      recreate existing constraints/index, then rebuild optional Candidate,
      every scorable Job, normalized Skills, and approved relationships through
      the existing sync/seed owners using stored embeddings.
    - The thin `python infrastructure/scripts/rebuild_neo4j.py` wrapper imports
      one application rebuild service, prints Candidate/Job/Skill and each
      relationship count, and exits non-zero on any failure.
  - Dependencies: (03A); existing profile/Job repositories, graph driver/schema,
    Candidate/Job/shared skill sync, settings, and root environment boundary.
  - User Action: Select exactly one run-context resolution and revise this task's
    authority/files/commands before A1 starts: (A) keep the exact host command
    but authorize it to delegate execution to a backend-container module that
    imports/calls the rebuild service; (B) authorize a host-accessible SQLite/
    loopback-Neo4j remap while retaining one root environment boundary; or (C)
    authorize replacing the Plan's host command with an explicit Compose-exec
    command. Each choice relaxes a different current source/runtime constraint;
    separately confirm the named local Neo4j target may be cleared/rebuilt
    before the required live command is run.
  - Agent Work:
    1. Search all graph clear/setup/sync/count helpers, settings/database engine
       construction, infrastructure wrappers, Compose volumes/hostnames, and
       README commands before implementing; reuse shared sync/schema primitives.
    2. Apply only the recorded A, B, or C run-context choice and its revised
       exact file/command scope. Do not add a second env, copy live data, broaden
       mounts, or mix approaches.
    3. Add fake-driver/migrated-SQLite tests for mismatch preflight before clear,
       label-scoped deletion, empty Candidate, all scorable Jobs, excluded rows,
       schema recreation, seed-only rebuild, exact counts, provider prohibition,
       SQLite immutability, repeat safety, and non-zero errors.
    4. Implement one focused rebuild service and thin import-only CLI, then
       document the approved operational command, no-provider behavior, and
       URL/local-demo limitations in the root README without duplicating logic.
  - Output: One safe, repeatable, stored-embedding graph rebuild command with an
    explicit runnable local/Compose context.
  - Acceptance:
    - Any mismatched model/dimension/count/non-finite vector fails before the
      first destructive graph statement and instructs configuration restoration.
    - Clear logic is label/relationship scoped and contains no unrestricted
      `MATCH (n) DETACH DELETE n`; unrelated graph data is preserved in tests.
    - With no Candidate, seed Skills/relationships and all scorable Jobs still
      rebuild; with a Candidate, the same Candidate sync owner is reused.
    - Rebuild makes no embedding/ShopAIKey call and no SQLite write, prints exact
      entity/relationship counts, is repeat-safe, and returns non-zero on failure.
    - The user-approved canonical command is runnable against the documented
      authoritative store/graph context and the approved single configuration boundary.
  - Validation:
    - Required: `Set-Location backend; python -m pytest tests/integration/test_graph_rebuild.py tests/integration/test_job_sync.py tests/integration/test_candidate_sync.py tests/unit/test_graph_setup.py -q` -> preflight, scoped clear, reuse, counts, and no-provider behavior pass with fakes.
    - Required: `Set-Location backend; python -m ruff check app/graph/rebuild.py app/graph/sync_job.py app/graph/sync_candidate.py app/graph/sync_shared.py tests/integration/test_graph_rebuild.py; python -m mypy app` -> rebuild/shared graph lint and application typing pass.
    - Required: `python infrastructure/scripts/rebuild_neo4j.py --help` -> the thin CLI imports successfully and documents its exact non-secret execution contract without touching stores.
    - Required: `rg -n "DETACH DELETE|MATCH \(n\)|ShopAIKey|embed|commit\(|Candidate|Job|Skill|HAS_SKILL|REQUIRES|PREFERS|RELATED_TO" backend/app/graph/rebuild.py infrastructure/scripts/rebuild_neo4j.py backend/tests/integration/test_graph_rebuild.py` -> scoped deletion, provider/SQLite prohibition, and complete counts are reviewable.
    - Required after choice A or B: `python infrastructure/scripts/rebuild_neo4j.py` -> exits zero against the actual authoritative SQLite/Neo4j context, makes no provider call/SQLite mutation, and prints all required counts.
    - Required after choice C: `docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.graph.rebuild` -> exits zero inside the authoritative Compose context, makes no provider call/SQLite mutation, and prints all required counts.
  - Blocked Condition: `BLOCKED_BY_USER_ACTION` while no approved execution
    choice and matching task revision reconcile the command with the Compose-only
    `/data` volume and `neo4j` service hostname. A1 must not implement only the
    fake-tested subset or treat `--help` as rebuild acceptance.
  - Files: `backend/app/graph/rebuild.py`, `infrastructure/scripts/rebuild_neo4j.py`, `backend/tests/integration/test_graph_rebuild.py`, `README.md`

## Mandatory Batch04 - Durable Saved-Job Chat Display

### Goal

Render compact created/returned/retried and truthful failed/sync-failed Job
outcomes through the existing durable history, single reducer, assistant message
composition, and pinned public Astryx components.

### Dependencies

- All Batch03 tasks (03A), (03B), (03C), and (03D) are A2-accepted; the UI
  directly consumes the compact Job ToolResult and durable status/history paths.
- Existing typed history/SSE parsing, durable history rehydration action, one
  chat reducer, ChatMessages/tool activity, and exact status vocabulary remain.
- Pinned Astryx 0.1.4 public CLI/component evidence and `frontend/AGENTS.md` apply.

### Scope Boundary

This batch owns strict frontend Job-result types, one saved-job card, friendly Job
tool labels/status, and minimal durable-history integration. It does not add a
jobs page/list, public job API, raw JD view, editor, ranking/match UI, second
state store, SSE event/payload expansion, custom design system, or internal
Astryx imports.

### Tasks

- [ ] (04A): Render a durable compact saved-job card through the single chat state path
  - Source of Truth: `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.9 Frontend saved-job display`; `docs/plans/Plan_5.md > ## 7. Technical Specifications > ### 7.6 Job tools`; `docs/plans/Plan_5.md > ## 9. Verification & Testing Plan > ### Frontend commands`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.3 Chat components`; `docs/plans/Master_plan.md > ## 15. Frontend UX Plan > ### 15.4 Tool activity display`
  - Source Requirements:
    - Strictly parse the compact `save_job` ToolResult projection and render ID,
      nullable title/company/source URL, exact processing status/quality,
      created/returned/retried outcome, and concise success/failure summary using
      public Astryx `Card`, `MetadataList`, `Badge`, and existing tool activity.
    - Show exact `pending|running|completed|failed` tool status/duration and
      friendly labels. `NEO4J_SYNC_FAILED` must show processed SQLite truth plus
      graph/rebuild failure without implying ranking or graph success.
    - Reuse durable `ToolResult.data` from chat history. Preserve only its
      whitelisted compact value as `ClientToolActivity.resultData`, then invoke
      the existing `history/rehydrate` action after terminal turns so live and
      restarted cards share one truth path; do not parse assistant text or expand SSE.
  - Dependencies: (03A), (03B), (03C), and (03D); existing `ChatPage`, history
    parser/projector, reducer, `ChatMessages`, and `ChatToolActivity`.
  - User Action: None for required frontend tests. Full local UI smoke is optional.
  - Agent Work:
    1. Run Astryx discovery in the order required by `frontend/AGENTS.md`:
       `build` for a saved Job result in chat, relevant layout/token docs, then
       public `Card`, `MetadataList`, `Badge`, and tool-status component docs;
       inspect every history/reducer/message/tool-result caller before editing.
    2. Add tests for strict compact parsing, completed/failed/sync-failed cards,
       null fields, enumerated badges, safe source URL, no raw/embedding/ranking,
       friendly tool labels, terminal history rehydrate, restart hydration, and
       exact status preservation.
    3. Implement focused `features/jobs` types/card and the smallest shared root
       fix that retains generic ToolResult data through durable history and
       terminally rehydrates the one reducer. Keep stream-shaped data null until
       durable truth arrives and do not add a competing result store.
    4. Extract the existing per-message row/tool/approval projection into the
       exact `features/chat/components/ChatMessageRow.tsx` owner, leaving
       `ChatMessages.tsx` responsible for list/notices. Integrate the parsed Job
       card there while all Job parsing/rendering stays in `features/jobs`.
  - Output: A restart-safe compact saved-job result card and truthful Job tool
    activity over the existing chat history/reducer.
  - Acceptance:
    - A completed `save_job` displays the exact compact fields/outcome after
      terminal durable rehydration and after restart; `query_jobs` remains a
      concise tool result without an invented ranking surface.
    - Failed fetch/extraction/embedding and committed-sync-failed results remain
      visibly failed with their stable summary/code; processed SQLite truth is
      not mislabeled as graph success.
    - Tool/application statuses remain exact, and `Badge` is used only for
      enumerated processing/quality state through documented public Astryx APIs.
    - Raw JD text, embeddings, arguments, secrets, storage paths, stack traces,
      score/rank claims, second reducer/store, SSE expansion, raw layout elements,
      internal Astryx imports, and duplicated result parsing are absent.
    - Shared client owners remain focused; all callers of changed history/tool
      projection behavior pass retained chat/profile tests.
  - Validation:
    - Required: `Set-Location frontend; npx astryx build "saved job result card in chat"; npx astryx docs layout; npx astryx docs tokens; npx astryx component Card; npx astryx component MetadataList; npx astryx component Badge; npx astryx component ChatToolCalls` -> pinned public card/metadata/state/tool APIs are documented before implementation.
    - Required: `Set-Location frontend; npm test -- --run src/test/saved-job-card.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts src/test/approval-card.test.tsx; npm run lint; npm run typecheck; npm run build` -> card, terminal/restart hydration, shared reducer, retained approval, lint, typing, and build pass.
    - Required: `Set-Location backend; python -m pytest tests/integration/test_job_tools.py tests/integration/test_chat_history.py tests/integration/test_chat_api.py -q` -> durable compact ToolResult/history contracts consumed by the UI pass with fakes.
    - Required: `rg -n "save_job|query_jobs|ToolResult|resultData|history/rehydrate|raw_content|embedding_json|NEO4J_SYNC_FAILED|@astryxdesign/.*/(src|dist)/|<div" frontend/src` -> one durable result path, safe compact rendering, and Astryx boundaries are reviewable.
    - Optional: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d` -> with user-managed prerequisites, one synthetic pasted/public JD visibly produces a truthful durable card across reload; unavailable live prerequisites do not block acceptance.
  - Blocked Condition: A required Astryx 0.1.4 public API cannot compose the
    source-required card/metadata/enumerated state. Report exact CLI evidence;
    do not invent props, use internal modules/raw layout, or add another design system.
  - Files: `frontend/src/features/jobs/types.ts`, `frontend/src/features/jobs/SavedJobCard.tsx`, `frontend/src/features/chat/history.ts`, `frontend/src/features/chat/reducer.ts`, `frontend/src/features/chat/ChatPage.tsx`, `frontend/src/features/chat/components/ChatMessages.tsx`, `frontend/src/features/chat/components/ChatMessageRow.tsx`, `frontend/src/features/chat/components/ChatToolActivity.tsx`, `frontend/src/test/saved-job-card.test.tsx`, `frontend/src/test/chat-page.test.tsx`, `frontend/src/test/sse-reducer.test.ts`, `frontend/src/test/approval-card.test.tsx`
