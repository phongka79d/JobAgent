# JobAgent Plan 5 Phase 4 Execution Tasks

## Purpose

Execute Master Phase 4 as reviewable units that accept one public JD URL or
raw-text JD, retain novel raw content before provider extraction, create a
validated and explicitly classified Job record, apply exact and normalized
duplicate policy, and synchronize only active scorable Job/Skill/JobFamily data
to the derived graph. The phase extends the accepted Plan 4 Agent, skill,
outbox, chat, and Astryx seams and stops before matching, ranking, or public Job
CRUD.

## Project Context Notes

- Root `README.md` was read completely. It records Plan 4 Batches 01-06 as
  evidence-backed, so every unchecked prerequisite marker in
  `docs/plans/Plan_5.md` is stale planning state rather than new work.
- SQLite remains the sole canonical application source of truth; Neo4j remains
  a derived, fully rebuildable graph/vector index. The frontend communicates
  only with FastAPI through the existing chat surface.
- `job_posts`, `graph_sync_outbox`, all four Job status enums, exact-hash and
  normalized-key columns, duplicate linkage, sanitized failure fields, and
  embedding model/dimension identity already exist in the initial migration.
  Plan 5 adds no application table or schema revision unless execution proves a
  source-required incompatibility that cannot be solved through these fields.
- The accepted graph schema already owns unique Candidate, Job, Skill, and
  JobFamily identities plus the 1536-dimension cosine Job vector index. The
  generic outbox repository is replay-safe; only Job processing and rebuild
  stages are missing.
- Plan 4 already owns `SkillRef`, the deterministic normalization/seed service,
  four Candidate tools, one LangGraph, the eight-event SSE union, durable
  structured chat payloads, and the single Astryx `AppShell`. Plan 5 extends
  these seams and must not recreate them.
- The production `skills_seed.yaml` exists but is intentionally empty; populated
  aliases are synthetic test fixtures only. No production alias or
  `RELATED_TO` edge becomes verified without approved user/evaluation evidence.
  Deterministic provisional skills keep the mandatory path executable.
- No SQLite `skills` table is authorized. The illustrative
  `repositories/skills.py` path is not sufficient reason to invent a twelfth
  table; canonical SkillRefs remain in validated Candidate/Job JSON and Neo4j
  remains derived.
- The master flow's broad “save received, then hash” wording is reconciled with
  Plan 5's more specific exact-duplicate rule as follows: acquire and
  canonicalize text, compute its hash, return an exact existing row when found,
  and insert only novel content before any ShopAIKey extraction. A blocked URL
  or HTML page with no usable text asks for pasted text and creates no fake Job
  record because no JD content exists to retain.
- `force_new` never overrides an exact hash. For different-content normalized
  matches it requires application-owned evidence from the current user turn,
  outside the URL/raw-JD payload, and a durable allowlisted audit token; the
  LLM-visible Boolean and document text alone never authorize it.
- SQLite stores the locked embedding model/dimension identity, not a canonical
  vector column. Job sync and rebuild generate vectors through the production
  adapter and write them only to derived Neo4j; outbox payloads remain
  identifier-only.
- The existing final-message `structured_payload` seam is hydrated but does not
  yet carry tool-derived Job cards, and the frontend currently ignores it.
  Plan 5 adds one bounded saved-Job payload through that seam without adding a
  ninth SSE event or another transport.
- Existing integration seams over 300 lines receive only thin edits. New URL,
  JD, embedding, Job graph, and Job presentation behavior belongs in focused
  modules; shared files are refactored rather than duplicated where necessary.
- The user-provided root rules require search-before-write, inspection of every
  caller of changed shared behavior, reuse before addition, focused modules,
  no duplicated business logic, and the shortest source-compliant diff.
- `frontend/AGENTS.md` requires Astryx CLI discovery, documented component
  APIs, the existing `AppShell` frame, component/token styling, and no raw
  layout `div` elements, guessed props, utility styling, or hard-coded visual
  values.
- Backend quality commands run from `backend/`:
  `python -m ruff check app tests`, `python -m mypy app`, and
  `python -m pytest -q`. Frontend commands run from `frontend/`:
  `npm run check:astryx`, `npm run lint`, `npm run typecheck`,
  `npm run test -- --run`, and `npm run build`.
- Normal automated tests use injected DNS/HTTP/provider/embedding/Neo4j fakes
  and temporary local stores. They never call real ShopAIKey, fetch public
  websites, require live Neo4j, or expose secrets/raw JD bodies.

## Authority and Scope

### Primary Source

`docs/plans/Plan_5.md` is the user-named primary source. Its objective, scope,
technical specifications, implementation steps, verification plan, and Plan 6
handoff are authoritative. Referenced sections of
`docs/plans/Master_plan.md`, the accepted Plan 4 handoff, root `README.md`, and
repository evidence refine executable boundaries without expanding Phase 4.

### Source Section Index

- `docs/plans/Plan_5.md` > `## 1. Objective` -> complete Phase 4 outcome.
- `docs/plans/Plan_5.md` > `## 4. Scope` -> mandatory input, extraction,
  persistence, tool, embedding, graph, and presentation work.
- `docs/plans/Plan_5.md` > `## 5. Out of Scope` -> prohibited crawling,
  matching, CRUD, worker, and scoring work.
- `docs/plans/Plan_5.md` > `## 6. Target Directory Structure` -> likely module
  ownership and thin tool-wrapper boundary.
- `docs/plans/Plan_5.md` > `### 7.1 URL security contract` -> scheme, DNS,
  redirect, timeout, body, content-type, and fetch restrictions.
- `docs/plans/Plan_5.md` > `### 7.2 Job extraction contract` -> exact Job fields,
  JobSkill evidence, and quality-reason separation.
- `docs/plans/Plan_5.md` > `### 7.3 Persistence-first state machine` -> durable
  raw content, independent states, retry ceilings, and sanitized failures.
- `docs/plans/Plan_5.md` > `### 7.4 Duplicate policy` -> exact hash, normalized
  duplicate, and explicit `force_new` behavior.
- `docs/plans/Plan_5.md` > `### 7.5 Skill normalization` -> one shared verified
  alias/provisional pipeline.
- `docs/plans/Plan_5.md` > `### 7.6 Embedding and graph synchronization` ->
  locked representation, eligibility, graph entities, and replay.
- `docs/plans/Plan_5.md` > `### 7.7 Tool outputs` -> bounded `save_job` and
  `query_jobs` results.
- `docs/plans/Plan_5.md` > `## 9. Verification & Testing Plan` -> security,
  retention, duplicate, authorization, replay, and privacy evidence.
- `docs/plans/Plan_5.md` > `## 10. Handoff Notes for Plan 6 (Master Phase 5)` ->
  stable Phase 5 inputs and prohibited matching work.
- `docs/plans/Master_plan.md` > `## 3. Locked Technology Stack` -> Trafilatura
  and httpx ownership.
- `docs/plans/Master_plan.md` > `### 6.3 Job status dimensions` -> four
  independent state domains.
- `docs/plans/Master_plan.md` > `### 7.1 Shared skill contract`,
  `### 7.4 Job extraction`, and `### 7.5 JD quality rules` -> validated Job and
  evidence contracts.
- `docs/plans/Master_plan.md` > `## 8. Neo4j Derived Model` and
  `## 9. Skill Normalization` -> graph identity, relationships, index, aliases,
  and provisional rules.
- `docs/plans/Master_plan.md` > `## 11. JD Ingestion Flow` -> accepted inputs,
  persistence, and duplicate sequence.
- `docs/plans/Master_plan.md` > `### 13.5 save_job`,
  `### 13.6 query_jobs`, and `### 13.8 Tool authorization matrix` -> exact
  Agent-facing surface and authorization.
- `docs/plans/Master_plan.md` > `## 14. Public FastAPI Boundary` and
  `### 14.2 SSE contract` -> unchanged seven routes and eight event names.
- `docs/plans/Master_plan.md` > `### 15.3 Chat components` and
  `### 15.4 Tool activity display` -> Astryx Job card and sanitized status.
- `docs/plans/Master_plan.md` > `## 16. ShopAIKey Integration` and
  `## 17. Embedding and Retrieval` -> locked provider/embedding adapter and
  representation contract; retrieval remains later-phase scope.
- `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` through
  `## 24. Local Testing Strategy` -> bounded failures, outbox, security,
  configuration, and fake-backed validation.
- `docs/plans/Master_plan.md` >
  `### Phase 4 — JD ingestion, extraction, deduplication, and graph sync` ->
  mandatory phase tasks and exit gate.
- `docs/plans/Plan_4.md` > `## 10. Handoff Notes for Plan 5 (Master Phase 4)`
  and `README.md` > `## Plan 5 handoff (Master Phase 4) — stable seams only`
  -> accepted Phase 3 primitives and Plan 5 ownership limits.

### Approved Architecture and Constraints

- Accept exactly one public HTTP/HTTPS URL or one nonblank raw JD text input
  through `save_job`. Do not add a JD upload route, public Job CRUD, crawler,
  authenticated fetch, browser, JavaScript renderer, or alternate input path.
- Use typed root settings already present for the 10-second URL timeout, 5 MB
  streamed-body limit, embedding identity, and provider configuration. Add
  direct exact runtime pins for locked httpx/Trafilatura dependencies without
  adding a second HTTP or HTML extraction stack.
- URL safety validates every A/AAAA result and each redirect before connecting.
  The connection must remain bound to a vetted address or verify the actual
  peer against the vetted set; a preflight DNS check followed by an unguarded
  hostname re-resolution is not sufficient.
- Canonical raw content preserves semantic case, punctuation, and internal line
  structure while normalizing Unicode/line-ending and edge whitespace
  differences. `raw_content_hash` is SHA-256 of that canonical content.
- The normalized duplicate identity is computed only when company, title, and
  location all normalize to nonblank values. Use a versioned, collision-safe
  digest of the three length-delimited normalized components; never truncate a
  human-readable composite into collisions.
- Reuse `SkillRef` and one normalization implementation. A minimal `JobSkill`
  adds only relationship-level confidence/evidence around that shared
  contract; no matching weight or trusted relationship field belongs here.
- Classify quality conservatively and deterministically. `full` requires a
  usable title/description, grounded responsibility/skill evidence, and a
  majority of available scoring-field groups; `partial` retains semantic plus
  grounded skill signals but misses the full threshold; `unscorable` lacks
  either meaningful responsibility/skill evidence or sufficient semantic
  content. Store reasons separately for every non-full result.
- Use `ShopAIKeyChatAdapter.invoke_structured` unchanged for the existing
  one-transient-retry and one-schema-repair ceilings. Do not wrap it in another
  retry loop or silently change the model/schema mode.
- Exact duplicates return the existing Job ID with zero new row, extraction,
  embedding, or outbox effect. Different-content normalized duplicates persist
  as `ignored_duplicate`/`not_required` unless explicitly authorized.
- Keep `processing_status`, `jd_quality`, `graph_sync_status`, and
  `record_status` independent. Provider/schema failures retain the raw row with
  stable sanitized error data; Neo4j failure never rolls back canonical Job
  state.
- Embed only active `full|partial` Jobs with
  `text-embedding-3-small`/1536/float, bounded batches, preserved ordering, and
  no E5 prefixes. Ignored or unscorable rows never embed, sync, or score.
- Every graph-eligible Job transaction enqueues or requeues one identifier-only
  `upsert_job` operation in the same SQLite transaction. Processing reloads
  current validated state, generates the derived vector, and uses parameterized
  `MERGE` by SQLite ID/canonical key.
- Preserve Candidate graph behavior. Job projection owns `Job`, `Skill`,
  `JobFamily`, `REQUIRES`, `PREFERS`, and conditional `IN_FAMILY` only; it never
  creates trusted `RELATED_TO` edges.
- Keep the exact seven public application routes and eight SSE event names.
  Tools call services/repositories directly and never call back into FastAPI.
- Production registers exactly the four accepted Candidate tools plus
  `save_job` and `query_jobs`. `match_jobs`, ranking, retrieval, score
  computation, top-result cards, and evaluation tuning remain Plan 6 work.
- Saved-Job presentation uses one bounded validated payload on the existing
  final-message/SSE/history seam. Raw JD, raw tool arguments, credentials,
  redirect/DNS details, stack traces, and provider bodies never enter chat,
  durable tool summaries, logs, cards, or errors.

## Batch Map

| Batch | Outcome | Task IDs | Depends on |
|---|---|---|---|
| Batch01 | Safe public URL and raw-text JD acquisition | (01A), (01B) | Accepted Plan 4/config handoff |
| Batch02 | Validated Job records and persistence-first duplicate state | (02A), (02B) | Batch01 |
| Batch03 | Shared Job skill normalization and locked Job embeddings | (03A), (03B) | Batch02 |
| Batch04 | Persistence-first Agent-facing Job workflow | (04A), (04B) | Batch03 |
| Batch05 | Replay-safe Job graph projection and complete rebuild | (05A), (05B) | Batch04 |
| Batch06 | Sanitized chat presentation and Phase 4 exit proof | (06A), (06B) | Batch05 |

## Agent Handoff Contract

- A1 executes one selected task only, does not update checkboxes in orchestrated
  mode, and appends evidence to `docs/reports/report_5_execute_agent.md`.
- A2 reviews one executed task, checks only its canonical checkbox on `ACCEPTED`,
  and appends evidence to `docs/review/review_5_review_agent.md`.
- A3 runs only after every task in the selected batch is A2-accepted and checked;
  it audits batch scope and commit readiness without changing task progress.
- Batch completion and commits belong to the orchestrator, not A1, A2, or A3.
- In orchestrated mode A1 execution and repair run on Grok unless the user sets
  `A1_RUNTIME: codex`. Codex writes `.agent/handoff/a1_request.md` and invokes
  `python $env:USERPROFILE\.codex\skills\orchestrator-agent\scripts\run_a1_grok.py --cwd <REPO> --envelope-file .agent\handoff\a1_request.md`;
  A2, A3, commit control, and next-batch approval remain on Codex.

## Mandatory Batch01 - Safe Public JD Input Acquisition

### Goal

Acquire one public URL or pasted JD as bounded meaningful text without exposing
the service to SSRF, hidden fetch fallbacks, or unbounded content.

### Dependencies

Accepted Plan 4 handoff plus the existing typed root URL settings.

### Scope Boundary

This batch owns URL policy, controlled retrieval, HTML main-text extraction,
and raw-text validation only. It does not call ShopAIKey, persist Job records,
deduplicate, embed, synchronize, register tools, or change public routes.

### Tasks

- [x] (01A): Enforce DNS/redirect-aware URL policy and bounded HTTP retrieval
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.1 URL security contract`; `docs/plans/Plan_5.md` > `## 5. Out of Scope`; `docs/plans/Master_plan.md` > `### 11.2 URL security`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy`
  - Source Requirements:
    - Permit only credential-free HTTP/HTTPS URLs; block localhost, loopback, private, link-local, unspecified, multicast, and metadata destinations for IPv4 and IPv6.
    - Validate every DNS answer and redirect target, allow at most three redirects, and enforce the existing 10-second/5 MB/HTML-or-plain-text ceilings.
    - Use no cookies, authentication, environment proxy, browser session, JavaScript renderer, or alternate fetch path; failures expose stable sanitized codes only.
  - Dependencies: Existing `backend/app/config.py` URL timeout/body settings and locked httpx choice
  - User Action: None
  - Agent Work:
    1. Search all configuration, HTTP, provider, logging, and URL callers; reuse typed settings and add only direct exact httpx/Trafilatura pins required by the locked stack.
    2. Implement a pure URL parser/DNS/IP policy that handles literals, every A/AAAA answer, IPv4-mapped IPv6, localhost/metadata names, credentials, and redirect targets.
    3. Implement a manually bounded redirect/stream loop whose actual connection is bound to or verified against a vetted address; disable ambient proxies/cookies/auth and sanitize every failure.
    4. Add injected resolver/transport tests for allowed public targets, mixed safe/forbidden answers, rebinding attempts, redirect overflow, timeouts, media-type parameters, oversized/streaming bodies, and secret/URL-detail absence.
  - Output: A controlled URL fetch result containing bounded response bytes, approved media type, and safe source metadata or one stable paste-text/error outcome.
  - Acceptance:
    - All forbidden address classes, URL credentials, unsafe redirect targets, and mixed DNS answer sets fail before content is accepted.
    - No request follows more than three redirects, runs beyond the configured timeout, buffers more than 5 MB, or accepts a media type outside `text/html|text/plain`.
    - Tests prove the connected/peer address remains within the validated set and no raw URL, DNS detail, proxy credential, or response body leaks in failures/logs.
    - No browser, JavaScript, cookie, authentication, public network test, or second fetch implementation is added.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/security/test_url_policy.py tests/services/test_url_fetcher.py` -> injected DNS/transport security matrix passes without network calls.
    - Required: `cd backend; python -m ruff check app/security app/services/url_fetcher.py tests/security tests/services/test_url_fetcher.py; python -m mypy app/security app/services/url_fetcher.py` -> focused lint and strict typing pass.
    - Required: `cd backend; python -m pip install -e ".[test]"` -> exact runtime pins resolve for Python 3.13; a package-index outage is recorded as `BLOCKED_BY_ENVIRONMENT` rather than bypassing the pinned dependencies.
  - Blocked Condition: Locked httpx/Trafilatura versions cannot be resolved for Python 3.13 or the chosen transport cannot bind/verify vetted addresses; report `BLOCKED_BY_ENVIRONMENT` or `BLOCKED_BY_SOURCE_CONFLICT` with evidence and do not weaken SSRF policy.
  - Files: `backend/app/security/__init__.py`, `backend/app/security/url_policy.py`, `backend/app/services/url_fetcher.py`, `backend/pyproject.toml`, `backend/tests/security/test_url_policy.py`, `backend/tests/services/test_url_fetcher.py`

- [x] (01B): Produce deterministic meaningful JD text from URL or pasted input
  - Source of Truth: `docs/plans/Plan_5.md` > `## 4. Scope`; `docs/plans/Plan_5.md` > `## 5. Out of Scope`; `docs/plans/Plan_5.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 11.1 Accepted inputs`; `docs/plans/Master_plan.md` > `### 11.2 URL security`
  - Source Requirements:
    - Accept exactly one public URL or raw JD text, use Trafilatura only for HTML main text, and use plain text directly.
    - A blank/unusable HTML extraction asks for pasted text and never invokes a browser or hidden parser fallback.
    - Canonical text must be deterministic so URL and pasted representations of the same JD hash identically later.
  - Dependencies: (01A) controlled fetch result and direct Trafilatura dependency
  - User Action: None during normal execution. A runtime user must paste JD text after the explicit `JD_TEXT_REQUIRED` outcome.
  - Agent Work:
    1. Search existing text normalization, chat-size, PII-redaction, and extraction helpers; reuse the current 32,768-character pasted user-text ceiling instead of inventing an unbounded tool input.
    2. Implement strict one-of input validation, deterministic Unicode/line-ending/edge-whitespace canonicalization that preserves semantic case/punctuation/internal structure, and SHA-256 hashing over canonical text.
    3. Decode approved `text/plain` bodies directly and run approved `text/html` through Trafilatura with scripts/comments/metadata excluded; treat only nonblank extracted text as acquired content and leave content-only quality decisions to Batch02.
    4. Add synthetic raw/plain/HTML fixtures covering equivalent canonical forms, blank/malformed/contact-only pages, extraction failure, oversize pasted input, and proof of zero browser/provider calls or raw-content leakage.
  - Output: One typed acquired-JD object with source type, safe source URL when present, canonical text, and content hash, or a stable paste-text request.
  - Acceptance:
    - Exactly one URL or raw-text input is required; the raw path never calls the fetcher and the URL path never bypasses (01A).
    - Equivalent URL/pasted content produces identical canonical text/hash while semantic case, punctuation, and line content remain intact.
    - Blank/failed Trafilatura output returns `JD_TEXT_REQUIRED` with no Job row, provider call, browser, JavaScript, authenticated, or paywall fallback.
    - Raw JD text and unsafe source details do not appear in exception strings, logs, or test snapshots.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_jd_source.py tests/services/test_url_fetcher.py` -> raw/plain/HTML acquisition and no-fallback tests pass.
    - Required: `cd backend; python -m ruff check app/services/jd_source.py tests/services/test_jd_source.py; python -m mypy app/services/jd_source.py` -> focused lint and strict typing pass.
  - Blocked Condition: Trafilatura cannot support the required deterministic main-text path on Python 3.13; report `BLOCKED_BY_ENVIRONMENT` without adding browser/JavaScript or alternate extraction behavior.
  - Files: `backend/app/services/jd_source.py`, `backend/tests/services/test_jd_source.py`, `backend/tests/fixtures/jds/*`

## Mandatory Batch02 - Validated Job Records and Persistence

### Goal

Turn acquired JD text into one strict, grounded Job extraction and a durable
SQLite record whose status, duplicate, and failure transitions remain explicit.

### Dependencies

Every Batch01 task is A2-accepted and checked.

### Scope Boundary

This batch owns Job schemas, deterministic quality, structured extraction,
canonical persistence, duplicate primitives, and bounded repository reads. It
does not expose tools, embed, synchronize Neo4j, or render frontend cards.

### Tasks

- [x] (02A): Validate grounded Job extraction and deterministic quality
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.2 Job extraction contract`; `docs/plans/Plan_5.md` > `### 7.3 Persistence-first state machine`; `docs/plans/Master_plan.md` > `### 7.1 Shared skill contract`; `docs/plans/Master_plan.md` > `### 7.4 Job extraction`; `docs/plans/Master_plan.md` > `### 7.5 JD quality rules`
  - Source Requirements:
    - Implement every master-defined `JobPostExtraction` field exactly; salary remains display-only.
    - Required/preferred skills use the shared `SkillRef` plus bounded relationship confidence and short source-grounded, contact-redacted evidence.
    - Classify `full|partial|unscorable` conservatively, store non-full reasons separately, and use one provider transient retry plus at most one schema repair.
  - Dependencies: (01B), existing `SkillRef`, deterministic PII redaction, untrusted-document wrapper, and `ShopAIKeyChatAdapter.invoke_structured`
  - User Action: None
  - Agent Work:
    1. Search Candidate schema/extraction/redaction/provider callers and reuse their strict Pydantic, evidence, prompt-delimiting, and sanitized-error patterns.
    2. Define focused Job/JobSkill/extraction/quality models with exact enums and bounds; do not add scoring weights, match fields, or trusted graph relationships.
    3. Implement a deterministic classifier: `full` requires usable title/description, grounded responsibility/skill evidence, and a majority of populated scoring-field groups; `partial` requires semantic plus grounded skill signals but misses the full threshold; all lower/contact-only cases are `unscorable`. Persist reasons outside the extraction object for non-full outcomes.
    4. Invoke the existing structured adapter once, relying on its existing shared retry/repair ceilings; delimit JD content as untrusted, validate evidence against canonical source text, redact contact evidence, and return stable code-only failures.
    5. Add fake-backed tests for all fields/enums, category boundaries/reasons, fabricated or overlong evidence, prompt injection, redaction failure, one retry, one repair, and no raw/provider leakage.
  - Output: A validated `JobPostExtraction` plus deterministic quality/reasons or one sanitized stable extraction failure.
  - Acceptance:
    - The extraction schema contains exactly the source-required fields and rejects extra/invalid enums, confidence, years, and evidence.
    - Required/preferred evidence is short, contact-redacted, and grounded in canonical JD text; fabricated evidence cannot persist.
    - Representative full, partial, unscorable, and contact-only fixtures produce deterministic categories, with reasons for every non-full result.
    - Tests prove exactly one transient retry and one invalid-schema repair ceiling through the reused adapter, with zero real provider calls.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/schemas/test_job_post.py tests/services/test_jd_quality.py tests/services/test_jd_extraction.py tests/services/test_shopaikey_chat.py tests/services/test_pii_redaction.py` -> schema, classifier, provider, grounding, and redaction tests pass.
    - Required: `cd backend; python -m ruff check app/schemas/job_post.py app/services/jd_quality.py app/services/jd_extraction.py tests/schemas/test_job_post.py tests/services/test_jd_quality.py tests/services/test_jd_extraction.py; python -m mypy app/schemas/job_post.py app/services/jd_quality.py app/services/jd_extraction.py` -> focused lint and strict typing pass.
  - Blocked Condition: The master `JobSkill` name and Plan 5's “SkillRef plus confidence/evidence” cannot be represented without changing the accepted `SkillRef` semantics; report `BLOCKED_BY_SOURCE_CONFLICT` rather than duplicating or mutating the shared contract.
  - Files: `backend/app/schemas/job_post.py`, `backend/app/services/jd_quality.py`, `backend/app/services/jd_extraction.py`, `backend/app/schemas/__init__.py`, `backend/tests/schemas/test_job_post.py`, `backend/tests/services/test_jd_quality.py`, `backend/tests/services/test_jd_extraction.py`

- [x] (02B): Implement persistence-first Job state and duplicate primitives
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.3 Persistence-first state machine`; `docs/plans/Plan_5.md` > `### 7.4 Duplicate policy`; `docs/plans/Plan_5.md` > `### 7.7 Tool outputs`; `docs/plans/Master_plan.md` > `### 6.3 Job status dimensions`; `docs/plans/Master_plan.md` > `### 11.4 Duplicate policy`
  - Source Requirements:
    - Persist novel raw content before LLM extraction and retain it after provider/schema failure with stable sanitized error data.
    - An exact content hash returns the existing Job with no insert; a different-content normalized match persists as ignored/not-required with a duplicate link.
    - Keep all status dimensions independent and expose only compact bounded reads without raw content.
  - Dependencies: (02A), existing `JobPost` ORM/migration, and existing caller-owned transaction/repository patterns
  - User Action: None
  - Agent Work:
    1. Search all `JobPost`, migration, repository, transaction, JSON-validation, and hash callers; reuse the existing schema and do not add a Skill table or redundant migration.
    2. Implement a caller-owned-transaction repository for exact lookup, novel `received` creation, guarded `processing -> processed|failed` transitions, validated extraction/quality storage, duplicate marking, graph-status updates, and stable code/message failures.
    3. Build the normalized identity only when company/title/location all normalize nonblank, using one versioned SHA-256 digest over length-delimited normalized components; make exact/normalized decisions atomic under concurrent inserts.
    4. Validate opaque `extracted_json` at repository boundaries and implement ID lookup plus default-10/max-50 filters; repository/public views omit raw content, hashes, embeddings, error internals, and unbounded list methods.
    5. Add temporary-SQLite tests for every state combination, rollback, corrupt JSON, exact races, normalized duplicates, insufficient keys, failure retention, bounded reads, and migration compatibility.
  - Output: A strict `JobPostRepository` and compact read model supporting the complete persistence/duplicate state machine.
  - Acceptance:
    - A novel record is committed as `received` with canonical raw content/hash before any provider call; a later failure retains that content and sanitized failure state.
    - Repeating the same hash returns the original ID and leaves row, provider, embedding, and outbox counts unchanged, including concurrent attempts.
    - A different hash with the same sufficient normalized key can persist as `ignored_duplicate` with `duplicate_of_job_id` and `graph_sync_status=not_required`; insufficient keys use exact dedup only.
    - Status transitions reject illegal combinations, repository reads validate JSON, and no read/filter path returns raw JD or an unbounded corpus.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/repositories/test_job_posts.py tests/db/test_models.py tests/integration/test_migrations.py` -> state, duplicate, JSON, concurrency, and existing-schema tests pass.
    - Required: `cd backend; python -m ruff check app/repositories/job_posts.py tests/repositories/test_job_posts.py tests/db/test_models.py tests/integration/test_migrations.py; python -m mypy app/repositories/job_posts.py` -> focused lint and strict typing pass.
  - Blocked Condition: The existing non-null/unique hash or status schema cannot implement exact no-insert plus novel-content retention under SQLite concurrency; report the exact conflict before proposing a migration.
  - Files: `backend/app/repositories/job_posts.py`, `backend/app/repositories/__init__.py`, `backend/tests/repositories/test_job_posts.py`, `backend/tests/db/test_models.py`, `backend/tests/integration/test_migrations.py`

## Mandatory Batch03 - Shared Normalization and Locked Embeddings

### Goal

Reuse one Candidate/Job skill identity pipeline and generate validated,
versioned Job embeddings through the already locked ShopAIKey contract.

### Dependencies

Every Batch02 task is A2-accepted and checked.

### Scope Boundary

This batch owns shared normalization refactoring and the production embedding
adapter/text builder. It does not orchestrate `save_job`, enqueue graph work,
write Neo4j, register tools, or implement retrieval/matching.

### Tasks

- [x] (03A): Extend the shared normalization seam to Job skills
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.5 Skill normalization`; `docs/plans/Master_plan.md` > `### 8.4 Graph safety rules`; `docs/plans/Master_plan.md` > `## 9. Skill Normalization`; `docs/plans/Plan_4.md` > `## 10. Handoff Notes for Plan 5 (Master Phase 4)`
  - Source Requirements:
    - Candidate and Job inputs use one Unicode/whitespace/case/punctuation, verified-alias, existing-canonical, and provisional-key pipeline.
    - Aliases remain properties of canonical Skills; only approved seed entries are verified and no LLM-created `RELATED_TO` becomes trusted.
    - Existing Candidate behavior and exclusions remain unchanged.
  - Dependencies: (02A) `JobSkill` contract and accepted Plan 4 normalization/seed
  - User Action: None for provisional behavior. Adding any production verified alias requires explicit approved evidence and is otherwise blocked.
  - Agent Work:
    1. Search every `SkillRef`, normalization, seed, Candidate extraction, graph, and test caller before changing the 514-line service; identify the smallest shared core rather than adding a Job-specific duplicate.
    2. Extract/refactor reusable label, alias, catalog, and provisional primitives into focused modules only where needed, preserving existing public imports and Candidate semantics.
    3. Add a JobSkill adapter that normalizes nested SkillRefs, preserves relationship confidence/evidence, reuses existing canonical keys, deduplicates required/preferred lists deterministically, and never upgrades unapproved identities.
    4. Keep the production seed empty unless approved evidence is supplied; use synthetic seeds only in tests and add Candidate-versus-Job parity/regression coverage.
  - Output: One shared normalization implementation consumed by both Candidate and Job paths, with stable public compatibility.
  - Acceptance:
    - Equivalent Candidate and Job surfaces resolve to the same seed canonical key/status/aliases, and unknown forms produce the same deterministic provisional key.
    - Existing canonical keys are reused without consulting Neo4j as authority; required/preferred evidence and Candidate exclusions remain intact.
    - Existing Candidate normalization/profile tests remain green and no second seed, SQLite Skill table, alias node, or trusted LLM relationship is introduced.
    - Production seed changes, if any, cite approved evidence; synthetic fixture aliases never enter production data.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py tests/services/test_profile_extraction.py tests/graph/test_candidate_sync.py` -> Candidate regression and Job parity/provisional tests pass.
    - Required: `cd backend; python -m ruff check app/services/skill_normalization.py app/schemas/candidate.py app/schemas/job_post.py tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py; python -m mypy app/services/skill_normalization.py app/schemas/candidate.py app/schemas/job_post.py` -> focused lint and strict typing pass.
  - Blocked Condition: A nonempty verified production seed is required for acceptance but no approved user/evaluation alias evidence exists; report `BLOCKED_BY_USER_ACTION` and do not promote test data.
  - Files: `backend/app/services/skill_normalization.py`, optional focused shared files under `backend/app/services/` or `backend/app/schemas/`, `backend/app/data/skills_seed.yaml` only with approved evidence, `backend/tests/services/test_skill_normalization.py`, `backend/tests/services/test_job_skill_normalization.py`

- [x] (03B): Build versioned Job text and locked ShopAIKey embeddings
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.6 Embedding and graph synchronization`; `docs/plans/Master_plan.md` > `### 16.1 Configuration`; `docs/plans/Master_plan.md` > `### 17.1 Locked embedding contract`; `docs/plans/Master_plan.md` > `### 17.3 Text representations`
  - Source Requirements:
    - Build Job text from title, summary, responsibilities, required skills, and preferred skills only.
    - Use ShopAIKey `text-embedding-3-small` with 1536 finite floats, bounded batches, stable input/output ordering, documented normalization, and no E5 prefixes.
    - Fail with sanitized provider codes and never switch model/dimensions/provider.
  - Dependencies: (02A), (03A), typed root settings, declared `langchain-openai`, and accepted Phase 0 embedding evidence
  - User Action: None for required fake-backed tests; real ShopAIKey diagnostics require a user-owned ignored root `.env` and are optional.
  - Agent Work:
    1. Search the Phase 0 benchmark, tests, settings, and installed `OpenAIEmbeddings` surface; extract/reuse proven normalization, batch-16, ordering, finite-vector, and error primitives instead of copying evaluation logic into production.
    2. Implement one versioned deterministic Job representation builder with source order fixed as title, summary, responsibilities, required skills, preferred skills; collapse whitespace and strip E5-style prefixes without adding scoring/retrieval content.
    3. Implement an injectable production adapter using only the configured ShopAIKey base URL/key, locked model/dimensions/float encoding, one transient retry, and batch size at most 16.
    4. Validate response count/order, exact dimensions, finite numeric values, model/config identity, and sanitized failures; update Phase 0 benchmark code to consume shared primitives when required to avoid duplicate business logic.
    5. Add scalar/batch fakes for ordering, boundaries, invalid values/dimensions/counts, timeout/rate limit, cancellation, secret-safe repr/logging, and zero network calls.
  - Output: A production `JobEmbeddingService` returning ordered validated vectors plus version/model/dimension identity.
  - Acceptance:
    - The representation contains exactly the source-ordered Job fields, is deterministic/versioned, and adds no E5 prefix, salary, raw HTML, source URL, or match feature.
    - Batches of 1-16 preserve input/output order and every accepted vector contains exactly 1536 finite floats; empty/oversized/mismatched responses fail closed.
    - Model, dimensions, base URL, retry budget, and provider cannot silently change, and errors/logs/reprs reveal no API key or input text.
    - Normal tests use fakes only and Phase 0 benchmark behavior remains compatible through shared primitives.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_embeddings.py tests/test_embedding_benchmark.py` -> builder, scalar/batch, order, vector, retry, and compatibility tests pass.
    - Required: `cd backend; python -m ruff check app/services/embeddings.py evaluation/benchmark_embeddings.py tests/services/test_embeddings.py tests/test_embedding_benchmark.py; python -m mypy app/services/embeddings.py` -> focused lint and strict typing pass.
    - Optional: `cd backend; python -m evaluation.benchmark_embeddings` -> user-authorized live compatibility observation only; never required for acceptance or run without ignored credentials.
  - Blocked Condition: The declared `langchain-openai` version cannot issue the locked embeddings request without changing provider/model/dimensions; report `BLOCKED_BY_SOURCE_CONFLICT` rather than adding a second provider or local runtime.
  - Files: `backend/app/services/embeddings.py`, `backend/evaluation/benchmark_embeddings.py` only for shared primitive reuse, `backend/tests/services/test_embeddings.py`, `backend/tests/test_embedding_benchmark.py`

## Mandatory Batch04 - Agent-Facing Job Workflow

### Goal

Compose safe acquisition, persistence, extraction, normalization, eligibility,
and outbox creation behind thin `save_job` and `query_jobs` Agent tools.

### Dependencies

Every Batch03 task is A2-accepted and checked.

### Scope Boundary

This batch owns application orchestration, `force_new` authorization/audit,
bounded reads, tool wrappers, and production registration. It does not add a
public Job endpoint, perform graph projection/rebuild, render the card, or
implement matching/scoring.

### Tasks

- [x] (04A): Orchestrate persistence-first JD ingestion and duplicate policy
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.3 Persistence-first state machine`; `docs/plans/Plan_5.md` > `### 7.4 Duplicate policy`; `docs/plans/Plan_5.md` > `### 7.6 Embedding and graph synchronization`; `docs/plans/Master_plan.md` > `### 13.5 save_job`; `docs/plans/Master_plan.md` > `### 21.1 Outbox rule`
  - Source Requirements:
    - One service handles exactly one URL/text input, persists novel raw content before extraction, applies bounded extraction/normalization/quality, and retains failed records.
    - Exact duplicates do nothing and return the existing ID; normalized duplicates persist ignored unless a different-position override is explicitly authorized.
    - Active full/partial records store embedding identity and enqueue Job sync in the same transaction; ignored/unscorable records are not required.
  - Dependencies: (01B), (02A), (02B), (03A), (03B), and generic `GraphOutboxRepository`
  - User Action: None during tests. A user requesting `force_new` must explicitly state outside the JD payload that it is a separate/distinct position.
  - Agent Work:
    1. Search every Job, outbox, tool, transaction, current-turn state, idempotency, and failure caller; reuse one service boundary and keep tool/HTTP logic out of it.
    2. Implement exact order: acquire/canonicalize/hash; return an exact existing row; commit novel `received` content; mark processing; extract/normalize/classify; atomically mark processed and either ignored/not-required or active pending plus identifier-only `upsert_job` enqueue.
    3. On extraction/provider failure, atomically retain the raw row as failed with stable code/sanitized message. On post-commit graph/provider unavailability, preserve canonical processed state and retryable sync state.
    4. Accept a service-level normalized-duplicate override only from an application-derived authorization Boolean. Never let it override an exact hash or originate from JD/tool arguments.
    5. Return one strict bounded result with Job ID, source, processing result, quality/reasons, duplicate outcome, graph state, and safe display summary; add call-order/failure/idempotency tests with injected collaborators.
  - Output: One `JDIngestionService` implementing the canonical save state machine and same-transaction Job outbox creation.
  - Acceptance:
    - Tests prove novel raw content commits before the first LLM call and remains after timeout/rate-limit/invalid-schema failure.
    - Exact duplicates cause zero new Job, extraction, embedding, or outbox work even when override is requested.
    - Different-content normalized duplicates persist ignored/not-required by default; an application-authorized override creates an active separate record without changing the earlier canonical row.
    - Only active full/partial records record locked embedding identity and enqueue/requeue one identifier-only Job operation; unscorable/ignored records never do.
    - Every failure/result is sanitized and no raw content, secret, unsafe URL details, or provider payload enters outbox, summaries, or logs.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/services/test_jd_ingestion.py tests/repositories/test_job_posts.py tests/repositories/test_graph_outbox.py` -> call order, retention, duplicate, eligibility, transaction, and outbox tests pass.
    - Required: `cd backend; python -m ruff check app/services/jd_ingestion.py app/repositories/job_posts.py tests/services/test_jd_ingestion.py; python -m mypy app/services/jd_ingestion.py app/repositories/job_posts.py` -> focused lint and strict typing pass.
  - Blocked Condition: Same-transaction Job status/outbox creation cannot reuse the generic repository without changing accepted Candidate semantics; report `BLOCKED_BY_SOURCE_CONFLICT` rather than adding a second outbox.
  - Files: `backend/app/services/jd_ingestion.py`, `backend/app/schemas/job_tools.py`, `backend/app/repositories/job_posts.py`, `backend/tests/services/test_jd_ingestion.py`, `backend/tests/repositories/test_graph_outbox.py`

- [x] (04B): Expose bounded Job tools with application-owned override authorization
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.7 Tool outputs`; `docs/plans/Plan_5.md` > `## 5. Out of Scope`; `docs/plans/Master_plan.md` > `### 13.5 save_job`; `docs/plans/Master_plan.md` > `### 13.6 query_jobs`; `docs/plans/Master_plan.md` > `### 13.8 Tool authorization matrix`
  - Source Requirements:
    - `save_job` validates exactly one URL/raw-text input plus optional `force_new` and delegates all business work to the ingestion service without approval.
    - `query_jobs` reads one Job ID or bounded filters and never returns a raw JD or unbounded corpus; score details appear only when already present.
    - Production exposes the four Candidate tools plus these two Job tools and no `match_jobs`.
  - Dependencies: (04A), existing `InjectedState` tool pattern, Agent registry, startup wiring, and durable tool-observability seam
  - User Action: None
  - Agent Work:
    1. Search all production tool factories, registry/startup callers, Agent state/message shapes, tool-result parsing, and route/exposure tests; keep wrappers thin and preserve exact Agent state keys.
    2. Build strict `save_job` args and derive `force_new` authorization from the current user turn in injected application state after excluding the exact URL/raw-JD payload. Require an explicit “separate position” or “distinct position” declaration; reject claims found only in document/tool arguments.
    3. Record authorized overrides as one allowlisted durable tool-summary token without storing the user turn/JD; unauthorized overrides fail before service mutation.
    4. Build `query_jobs` as ID mode or default-10/max-50 filter mode over compact validated repository views; it may return existing `score_cache` details but never computes scores.
    5. Register exactly six production tools, wire injected services in `main.py`, retain `match_jobs` as reserved only, and add tool/registry/prompt/idempotency/route tests.
  - Output: Two Agent-facing tools on the existing LangGraph registry with durable sanitized authorization evidence.
  - Acceptance:
    - `save_job` rejects neither/both input modes and unauthorized `force_new` with zero mutation; an explicit current-turn declaration outside the JD creates exactly one allowlisted audit token.
    - `query_jobs` supports one ID or bounded filters, defaults to 10, caps at 50, and excludes raw content/hash/error/vector/provider/internal fields.
    - Production registry names are exactly `get_candidate_context`, `propose_profile_from_cv`, `propose_profile_update`, `commit_profile_draft`, `save_job`, and `query_jobs`.
    - Tools call services directly, use the existing graph/transport, preserve Candidate behavior, and add no public route or `match_jobs` implementation.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/tools/test_save_job.py tests/tools/test_query_jobs.py tests/tools/test_registry.py tests/agent/test_graph.py tests/agent/test_prompt.py tests/api/test_chat.py` -> input, authorization, bounded read, registration, and existing Agent/API tests pass.
    - Required: `cd backend; python -m ruff check app/tools app/tools/registry.py app/main.py tests/tools tests/agent/test_graph.py tests/agent/test_prompt.py; python -m mypy app/tools app/tools/registry.py app/main.py` -> focused lint and strict typing pass.
    - Required: `rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api` -> reviewed inventory remains exactly the seven authorized application routes.
  - Blocked Condition: Current-turn application state cannot distinguish the user declaration from the URL/raw-JD payload without changing the accepted state/transport contract; report `BLOCKED_BY_SOURCE_CONFLICT` and do not trust the LLM Boolean.
  - Files: `backend/app/tools/save_job.py`, `backend/app/tools/query_jobs.py`, `backend/app/tools/registry.py`, `backend/app/main.py`, `backend/app/services/chat_service.py` only for the allowlisted audit token, `backend/tests/tools/test_save_job.py`, `backend/tests/tools/test_query_jobs.py`, `backend/tests/tools/test_registry.py`

## Mandatory Batch05 - Rebuildable Job Graph Projection

### Goal

Process identifier-only Job outbox work into an idempotent active/scorable
Job/Skill/JobFamily graph and rebuild that derived slice completely from SQLite.

### Dependencies

Every Batch04 task is A2-accepted and checked.

### Scope Boundary

This batch owns Job embedding-at-sync, graph projection, bounded retry/status,
startup processing, and rebuild parity. It does not implement retrieval,
matching, scoring, continuous polling, background-worker infrastructure, or
trusted relationship discovery.

### Tasks

- [x] (05A): Process replay-safe Job/Skill/JobFamily outbox projections
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.6 Embedding and graph synchronization`; `docs/plans/Master_plan.md` > `## 8. Neo4j Derived Model`; `docs/plans/Master_plan.md` > `### 21.1 Outbox rule` through `### 21.3 Idempotency`; `docs/plans/Plan_4.md` > `### 7.6 Candidate graph synchronization`
  - Source Requirements:
    - Only active full/partial Jobs embed and synchronize; ignored/unscorable records never enter Neo4j.
    - Merge Job/Skill/JobFamily and `REQUIRES|PREFERS|IN_FAMILY` by SQLite ID/canonical key with replay-safe aliases/evidence and no trusted LLM relationship.
    - Process immediately best-effort after commit and in bounded startup retries; graph failure preserves SQLite and retryable state.
  - Dependencies: (03B), (04A), existing graph schema/client/fakes, generic outbox, Candidate projector, and lifecycle
  - User Action: None for fake-backed tests; live Neo4j is optional.
  - Agent Work:
    1. Search every Candidate/outbox/lifecycle/rebuild caller and Cypher parameter contract; extract a small shared processor only if it removes real duplicated claim/status/retry logic.
    2. Implement an identifier-only `upsert_job` processor that reloads and validates current SQLite state, rejects ineligible rows, generates the derived vector, and uses parameter-bound Cypher.
    3. Idempotently replace one Job's derived properties/`REQUIRES`/`PREFERS`/`IN_FAMILY` projection, merge Skill aliases without alias nodes, create a deterministic JobFamily key only when present, and never create `RELATED_TO`.
    4. Atomically map outbox success/failure to Job `graph_sync_status`, requeue bounded failed work, and extend startup/immediate processing without continuous polling or Candidate regressions.
    5. Add fake-Neo4j/outbox/lifecycle tests for eligibility, exact parameters, embedding failure, Neo4j failure, replay, stale-edge removal, alias union, and zero duplicate entities/relationships.
  - Output: Bounded `process_job_sync_outbox` behavior and startup/immediate integration over the existing graph/outbox.
  - Acceptance:
    - Processing reloads by Job ID and never carries raw content/vector/path/secret data in the outbox payload.
    - Active full/partial rows produce one Job ID, canonical Skills, optional JobFamily, correct edge sets, and a 1536-vector; ignored/unscorable rows remain absent.
    - Replaying/requeueing the same operation produces no duplicate node/edge and removes stale owned edges without affecting Candidate or unrelated graph data.
    - Embedding/Neo4j failure leaves canonical Job processed, marks retryable sync/outbox failure with sanitized codes, and never spins continuously.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/graph/test_job_sync.py tests/integration/test_job_sync.py tests/repositories/test_graph_outbox.py tests/graph/test_candidate_sync.py tests/integration/test_candidate_sync.py tests/test_lifecycle.py` -> projection, replay, failure, Candidate regression, and lifecycle tests pass.
    - Required: `cd backend; python -m ruff check app/graph/job_sync.py app/graph/lifecycle.py app/repositories/graph_outbox.py tests/graph/test_job_sync.py tests/integration/test_job_sync.py tests/test_lifecycle.py; python -m mypy app/graph/job_sync.py app/graph/lifecycle.py` -> focused lint and strict typing pass.
  - Blocked Condition: Job processing requires raw/vector data in the outbox or a second graph client to meet the source; report `BLOCKED_BY_SOURCE_CONFLICT` rather than bypassing identifier-only reload and the shared client.
  - Files: `backend/app/graph/job_sync.py`, optional `backend/app/graph/outbox_processor.py` only when shared by Candidate and Job, `backend/app/graph/lifecycle.py`, `backend/app/main.py`, `backend/tests/graph/test_job_sync.py`, `backend/tests/integration/test_job_sync.py`, `backend/tests/test_lifecycle.py`

- [x] (05B): Rebuild and verify the complete Candidate/Job derived graph
  - Source of Truth: `docs/plans/Plan_5.md` > `### 7.6 Embedding and graph synchronization`; `docs/plans/Plan_5.md` > `## 9. Verification & Testing Plan`; `docs/plans/Master_plan.md` > `### 8.3 Constraints and indexes`; `docs/plans/Master_plan.md` > `### 21.4 Rebuild`; `docs/plans/Plan_5.md` > `## 10. Handoff Notes for Plan 6 (Master Phase 5)`
  - Source Requirements:
    - The safe rebuild recreates constraints/vector index, preserves the accepted Candidate slice, reloads active/scorable Jobs/Skills/JobFamilies, recomputes vectors when required, and verifies IDs/counts/statuses.
    - Ignored duplicates and unscorable Jobs remain excluded; replay/rebuild results match canonical SQLite IDs.
    - Destructive behavior remains explicit and contained to JobAgent-derived labels.
  - Dependencies: (05A), existing dry-run/confirmation rebuild CLI and graph schema
  - User Action: None for required fake-backed parity. Live destructive Neo4j validation requires explicit user confirmation and is optional.
  - Agent Work:
    1. Search all rebuild stages/tests/callers and keep `infrastructure/scripts/rebuild_graph.py` as a thin CLI; move new Job load/embedding/count logic into focused reusable graph modules rather than expanding the existing 552-line script inline.
    2. Complete the deferred Job/entity/embedding/verification stages using the same Candidate and Job projectors, safe clear, schema bootstrap, bounded SQLite reads, and fake-injectable embedding/client seams.
    3. Add a minimal bounded Neo4j read-result method only if required for ID/count verification; keep queries parameterized and sanitize failures.
    4. Recompute Job vectors during rebuild, compare active full/partial SQLite ID/entity/edge counts, exclude ignored/unscorable IDs, and update Job/outbox sync state only after verified success.
    5. Add dry-run, confirmation, partial-failure, Candidate preservation, replay, count/ID mismatch, and complete fake-backed parity tests.
  - Output: One safe rebuild command that completes Candidate plus active/scorable Job graph reconstruction and parity verification.
  - Acceptance:
    - Default dry-run is non-destructive; destructive mode requires the existing explicit confirmation and clears only JobAgent-derived labels/edges.
    - A successful rebuild recreates the four constraints/vector index, accepted Candidate projection, every active full/partial Job projection/vector, and matching canonical IDs/counts.
    - Ignored/unscorable Jobs remain absent, mismatches fail non-zero with sanitized evidence, and sync states are not falsely marked on partial failure.
    - New rebuild logic lives in focused modules and does not duplicate the online Job projector or turn the existing CLI into a larger god file.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/infrastructure/test_rebuild_graph.py tests/graph/test_job_sync.py tests/graph/test_candidate_sync.py tests/integration/test_job_sync.py` -> safe CLI, parity, exclusion, failure, and Candidate/Job replay tests pass.
    - Required: `python infrastructure/scripts/rebuild_graph.py --help; python infrastructure/scripts/rebuild_graph.py` -> help and default dry-run execute without destructive mutation; the documented incomplete-stage exit must be removed only when all required stages are implemented.
    - Required: `cd backend; python -m ruff check app/graph infrastructure/scripts/rebuild_graph.py tests/infrastructure/test_rebuild_graph.py tests/graph; python -m mypy app/graph` -> focused lint and strict typing pass.
    - Optional: `cd backend; python -m pytest -q -m neo4j tests/graph/test_schema.py tests/integration/test_job_sync.py` -> user-authorized live Neo4j observation only; skips do not replace required fake-backed proof.
  - Blocked Condition: Required count/ID parity cannot be observed through a bounded safe client method or destructive scope cannot remain label-contained; report `BLOCKED_BY_SOURCE_CONFLICT` and do not claim rebuild completion.
  - Files: `backend/app/graph/job_sync.py`, focused rebuild support under `backend/app/graph/`, `backend/app/graph/client.py` only for bounded result reads, `infrastructure/scripts/rebuild_graph.py`, `backend/tests/infrastructure/test_rebuild_graph.py`, `backend/tests/integration/test_job_sync.py`

## Mandatory Batch06 - Chat Presentation and Phase 4 Exit

### Goal

Render sanitized Job activity/card data through the existing chat transport and
prove the complete fake-backed Phase 4 slice, production exposure, privacy, and
stable Plan 6 handoff.

### Dependencies

Every Batch05 task is A2-accepted and checked.

### Scope Boundary

This batch owns the bounded saved-Job payload, Astryx card/status presentation,
cross-component exit evidence, and root README handoff. It may repair only
Phase 4 defects exposed by that proof; it does not add match results, ranking
UI, Job management screens, routes, crawlers, live-provider requirements, or
future hardening.

### Tasks

- [x] (06A): Render sanitized JD activity and one saved-Job chat card
  - Source of Truth: `docs/plans/Plan_5.md` > `## 4. Scope`; `docs/plans/Plan_5.md` > `### 7.7 Tool outputs`; `docs/plans/Master_plan.md` > `### 14.2 SSE contract`; `docs/plans/Master_plan.md` > `### 15.3 Chat components`; `docs/plans/Master_plan.md` > `### 15.4 Tool activity display`
  - Source Requirements:
    - Show sanitized Job tool labels/status/duration/outcome and a structured saved-Job card.
    - Preserve the existing eight SSE event names and durable history/reconnect behavior.
    - Never expose raw JD/tool arguments, secrets, stack traces, unsafe URL details, or later score/match presentation.
  - Dependencies: (04B), (05A), existing SSE/final-message/history/reducer/`ChatMessages` seams, and `frontend/AGENTS.md`
  - User Action: None
  - Agent Work:
    1. Search every backend SSE/history/tool-result validator and frontend parser/reducer/message/card caller; define one minimal saved-Job payload shared between live completion and durable history.
    2. Validate and persist only bounded display fields from a successful `save_job` result: kind, Job ID for later queries, title/company/location/work mode/employment type, quality/reasons preview, duplicate outcome, graph state, and validated public source URL when present. Do not persist the tool body.
    3. Extend the existing `run_completed`/final-message payload compatibly, keep all eight event names unchanged, and make malformed/unsafe Job payloads fail closed to ordinary sanitized text/status.
    4. Explicitly use the Astryx workflow: `npx astryx build "saved job chat card and JD tool status"`, then inspect `ChatToolCalls`, `Card`, `MetadataList`, and the documented enumerated-status component before implementation.
    5. Add focused `frontend/src/features/jobs/` contracts/component files and thin chat reducer/message integration so live SSE and hydrated history render the same card without raw `div` layout, guessed props, or hard-coded visual values.
    6. Add backend/frontend tests for processed/duplicate/unscorable/failed states, reconnect hydration, malformed payloads, duplicate events, and raw/secret/stack/URL-detail sentinels.
  - Output: One typed saved-Job card and sanitized Job activity display on the existing chat/history transport.
  - Acceptance:
    - The public SSE union still contains exactly eight names; no Job API route, second stream, or parallel chat state is added.
    - A successful save renders the same bounded Job card live and after history hydration, while duplicate/unscorable/graph-failed states remain understandable and sanitized.
    - Tool activity shows only friendly label, approved status, duration, and short outcome; raw JD/arguments/provider/internal data never reaches SSE/history/UI/log snapshots.
    - Astryx discovery evidence is recorded, the existing `AppShell` remains, and the focused Job component follows documented component/token/no-raw-div rules.
  - Validation:
    - Required: `cd backend; python -m pytest -q tests/schemas/test_sse.py tests/api/test_chat.py tests/integration/test_chat_transport.py tests/integration/test_job_chat.py` -> saved payload, eight-event, persistence, reconnect, and leakage tests pass.
    - Required: `cd frontend; npx astryx build "saved job chat card and JD tool status"; npx astryx component ChatToolCalls; npx astryx component Card; npx astryx component MetadataList` -> pinned component guidance is captured before UI edits.
    - Required: `cd frontend; npm run test -- --run src/features/jobs src/features/chat/reducer.test.ts src/features/chat/components/ChatMessages.test.tsx src/features/chat/components/ChatToolActivity.test.tsx src/test/job-workflow.integration.test.tsx; npm run check:astryx; npm run lint; npm run typecheck; npm run build` -> Job/chat components and all frontend quality gates pass.
  - Blocked Condition: The pinned Astryx package lacks a documented component needed for the minimal card; report `BLOCKED_BY_ENVIRONMENT` with CLI output and use only another documented pinned Astryx component after review, never guessed props or raw layout.
  - Files: `backend/app/schemas/job_tools.py`, `backend/app/schemas/sse.py`, `backend/app/services/chat_service.py`, `backend/app/api/chat.py`, `backend/tests/integration/test_job_chat.py`, `frontend/src/features/jobs/contracts.ts`, `frontend/src/features/jobs/components/SavedJobCard.tsx`, `frontend/src/features/chat/contracts.ts`, `frontend/src/features/chat/reducer.ts`, `frontend/src/features/chat/components/ChatMessages.tsx`, focused tests

- [x] (06B): Prove Phase 4 and publish the stable Plan 6 handoff
  - Source of Truth: `docs/plans/Plan_5.md` > `## 9. Verification & Testing Plan`; `docs/plans/Plan_5.md` > `## 10. Handoff Notes for Plan 6 (Master Phase 5)`; `docs/plans/Master_plan.md` > `## 20. Failure and Recovery Policy` through `## 24. Local Testing Strategy`; `docs/plans/Master_plan.md` > `### Phase 4 — JD ingestion, extraction, deduplication, and graph sync`
  - Source Requirements:
    - Prove raw failure retention, exact/no-reprocess and normalized/ignored duplicate rules, explicit override authorization, shared normalization, private/local URL blocking, and graph replay/rebuild parity.
    - The phase exits only when active full/partial Jobs are queryable in the graph by matching SQLite IDs and all raw/secret surfaces remain clean.
    - Publish only active scorable Jobs, canonical Skills, Job vectors/graph identity, and stable query/card seams to Plan 6; matching remains unimplemented.
  - Dependencies: Every earlier Plan 5 task and accepted Plan 4 full-profile transport fixture
  - User Action: None for required proof. Live ShopAIKey/Neo4j/Compose observation uses only a user-populated ignored root `.env` and is optional.
  - Agent Work:
    1. Search existing full transport/profile fixtures, route/tool inventories, secret scans, README handoffs, and every shared seam changed by Plan 5; reuse them instead of creating a second harness.
    2. Add one backend fake-backed full flow covering public URL and raw text, SSRF rejection, HTML paste fallback, persistence before extraction, retry/repair, full/partial/unscorable states, exact return, normalized ignore, unauthorized/authorized override, query, pending/failure sync, replay, restart, and rebuild parity.
    3. Assert Candidate/Job normalization parity, exact active/scorable SQLite-to-Neo4j IDs/counts, no ignored/unscorable entities, and no duplicate Job/Skill/JobFamily nodes or relationships after replay/rebuild.
    4. Add one frontend raw-SSE-through-parser/reducer/shell flow for Job tool status, saved card, duplicate/unscorable/graph-failure outcomes, history hydration, malformed payload, disconnect, and duplicate events.
    5. Verify production has exactly six tools, exactly seven application routes, no `match_jobs`/matching/ranking/public Job CRUD, and zero raw JD/credential/unsafe URL/stack sentinels across requests, SSE, history, tool rows, outbox, graph parameters, logs, errors, and UI.
    6. Update root `README.md` with evidence-backed Plan 5 batches/commands, current limitations, safe optional live observation, and the precise Plan 6 handoff. Do not claim optional runs that were not executed.
  - Output: Reproducible Phase 4 exit evidence and a current root README authorizing only stable Plan 6 inputs.
  - Acceptance:
    - Full fake-backed backend/frontend flows pass with zero real provider/public-URL calls and zero raw/secret/unsafe-detail sentinel leakage.
    - Raw novel JD survives every extraction failure; exact duplicates cause no reprocessing; normalized duplicates remain stored but absent from embedding/graph/query defaults; authorized override is durably auditable.
    - Replayed online sync and complete rebuild produce matching active full/partial SQLite IDs/counts with no duplicate entities/edges and no Candidate regression.
    - Production exposure is exactly six tools and seven routes; matching, ranking, score generation, Job CRUD/UI, crawlers, workers, and ninth SSE events remain absent.
    - Root `README.md` truthfully records Plan 5 completion evidence, exact commands, remaining limitations, and stable Plan 6 ownership.
  - Validation:
    - Required: `cd backend; python -m ruff check app tests; python -m mypy app; python -m pytest -q; python -m pytest -q tests/integration/test_full_job_workflow.py` -> all backend gates and focused Phase 4 workflow pass without network calls.
    - Required: `cd frontend; npm ci --ignore-scripts; npm run check:astryx; npm run lint; npm run typecheck; npm run test -- --run; npm run test -- --run src/test/job-workflow.integration.test.tsx; npm run build` -> all frontend gates and focused Job workflow pass.
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml config` -> static three-service configuration resolves without real secrets.
    - Required: `docker compose --env-file .env.example -f infrastructure/docker-compose.yml build` -> production images include the locked URL/HTML dependencies and build; unavailable Docker is recorded as `BLOCKED_BY_ENVIRONMENT` rather than claimed.
    - Required: `rg -n "raw_jd|raw_content|document_text|authorization|Bearer |api[_-]?key|save_job|query_jobs|match_jobs|score" backend/app frontend/src; rg -n "@(router|app)\.(get|post|put|patch|delete)" backend/app/api; git diff --check` -> reviewed privacy/domain/route inventory and clean diff evidence are recorded, with terms present only where authorized.
    - Optional: `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d` followed by one user-observed public-URL/raw-text save/query/read flow -> local live observation only with user-owned ignored secrets; never required for acceptance.
  - Blocked Condition: A required local command cannot run because Docker/tooling is unavailable; record `BLOCKED_BY_ENVIRONMENT` for that command. Any functional, security, privacy, duplicate, authorization, replay, rebuild, route, or tool failure remains an implementation defect rather than an environment blocker.
  - Files: `backend/tests/integration/test_full_job_workflow.py`, `backend/tests/fixtures/jds/*`, `frontend/src/test/job-workflow.integration.test.tsx`, `README.md`, and only narrow Plan 5 implementation/test files required to repair failures exposed by this task

## Optional Future Tracks

No optional implementation track is authorized by Plan 5. Automatic crawling,
authenticated/paywalled or JavaScript-rendered pages, browser automation,
public Job CRUD, matching/ranking/retrieval, score caches, graph boosts,
evaluation tuning, top-result cards, salary scoring, continuous workers,
Qdrant, CI, cloud deployment, and automatic trusted `RELATED_TO` edges remain
outside the mandatory Phase 4 batch chain. Live provider, Neo4j, browser, or
Compose observations may be recorded as optional validation only and do not
replace fake-backed acceptance.