# Plan 5 — Master Phase 4: JD Ingestion, Extraction, Exact Deduplication, and Graph Sync

> **Numbering:** `Plan_5.md` implements **Master Plan Phase 4**. It reuses the normalizer, tool runtime, SQLite ownership, and graph primitives established earlier.

## 1. Objective

Implement persistence-first ingestion of public HTTP/HTTPS Job Descriptions and pasted JD text, including constrained fetching, Trafilatura extraction, structured facts, exact content-hash reuse/retry, quality classification, production embeddings for scorable jobs, direct Job/Skill graph synchronization, compact Agent tools/UI, and a complete local Neo4j rebuild command.

Every accepted input must leave a durable SQLite record representing success or failure. Exact processed content must not be reprocessed; failed exact content must retry in the same row. Neo4j remains derived and rebuildable, and no matching/ranking behavior begins in this phase.

## 2. Source of Truth

- `docs/plans/Master_plan.md` Sections 2–4: manual JD input, any job family, locked provider/embedding/graph stack, and SQLite-first ownership.
- Sections 6.2 and 6.4: `job_posts` fields/invariants, scorable definition, state transitions, exact-hash placeholder transaction flow, and no score cache.
- Sections 7.1, 7.4, and 7.6: Job extraction/skill contracts, source evidence, and authoritative quality classification.
- Sections 8–9: Job/Skill graph shape and reuse of deterministic normalization/seed relationships.
- Section 11: accepted inputs, constrained fetch, persistence-first flow, and exact duplicate policy.
- Sections 13.4–13.5 and 13.7: `save_job`, `query_jobs`, authorization, compact output, and no approval requirement.
- Sections 15.4 and 16–17.3: concise tool UI, provider adapter, locked embeddings, whitespace normalization, and versioned Job representation.
- Sections 20–23: failure/retry, direct sync, rebuild command, safeguards, and environment limits.
- Sections 24 and 25, “Phase 4”: required tests, tasks, and exit gate.

## 3. Prerequisites from Prior Phases

- [ ] `job_posts` schema/constraints/indexes exactly match Master Section 6.
- [ ] Tool execution/replay, typed SSE, Agent registration, and concise tool activity are operational.
- [ ] ShopAIKey schema strategy is verified; normal automated tests use a fake provider.
- [ ] `SkillRef`, the deterministic normalizer, authoritative `skills_seed.yaml`, and Candidate/Skill graph sync exist.
- [ ] Neo4j uniqueness constraints/vector index are idempotent and fixed to cosine/1536 dimensions.
- [ ] Approved Candidate Profile may be absent; JD save/query must still work.
- [ ] Root settings expose URL timeout/size and locked embedding model/dimensions.

## 4. Scope

- Define exact `JobPostExtraction` and `JobSkill` Pydantic contracts.
- Implement `save_job` accepting exactly one public URL or raw text, with no approval.
- Persist URL placeholder or unique raw text before external extraction work.
- Implement basic HTTP/HTTPS download with 10-second timeout, 5 MB maximum, and `text/html`/`text/plain` only.
- Use Trafilatura for HTML main text; return a paste-text fallback when meaningful text cannot be obtained.
- Implement structured JD extraction, at most one repair, shared skill normalization, and full/partial/unscorable quality classification.
- Implement exact SHA-256 content deduplication: return existing non-failed row or retry an existing failed row in place.
- Implement the production ShopAIKey embedding adapter, shared whitespace normalization, and versioned Job text builder.
- Persist 1536-dimensional embeddings only for processed full/partial jobs.
- Directly synchronize scorable Job/Skill nodes and relationships after SQLite terminal commit.
- Implement `query_jobs` with optional ID/status/quality filters and limit `1..50`.
- Complete the local Neo4j rebuild command using stored SQLite embeddings and no provider calls.
- Render concise JD tool status and a compact saved-job card in chat.
- Add unit/integration/frontend tests for all persistence, duplicate, failure, embedding, graph, and display rules.

## 5. Out of Scope

- Automatic discovery/crawling, authenticated/paywalled/cookie-dependent/JavaScript-only pages, browser automation, or site-specific scrapers.
- SSRF/IP-range defenses, redirect validation, production threat modeling, or other security expansion beyond the locked local limits.
- Normalized/near-duplicate detection, `force_new`, content-version history, reprocessing processed rows, or a retry endpoint/flag.
- Matching, Candidate embeddings, vector retrieval, score components, rankings, or match cards.
- Alternate embedding providers/models/dimensions, local embeddings, reranking, Qdrant, evaluation datasets/metrics, or benchmarks.
- Background workers, outbox/retry queues, sync ledgers, score caches, or Neo4j repair inside reads.
- Public job CRUD endpoints or raw JD bodies in tool/history/card payloads.

## 6. Target Directory Structure

```text
JobAgent/
├── backend/
│   ├── app/
│   │   ├── adapters/
│   │   │   └── shopaikey_embeddings.py
│   │   ├── graph/
│   │   │   ├── rebuild.py
│   │   │   └── sync_job.py
│   │   ├── repositories/
│   │   │   └── jobs.py
│   │   ├── schemas/
│   │   │   ├── embeddings.py
│   │   │   └── jobs.py
│   │   ├── services/
│   │   │   ├── embedding_text.py
│   │   │   ├── jd_extraction.py
│   │   │   ├── jd_ingestion.py
│   │   │   ├── jd_quality.py
│   │   │   └── url_fetch.py
│   │   └── tools/
│   │       └── jobs.py
│   └── tests/
│       ├── integration/
│       │   ├── test_graph_rebuild.py
│       │   ├── test_job_ingestion.py
│       │   └── test_job_sync.py
│       └── unit/
│           ├── test_embedding_adapter.py
│           ├── test_embedding_text.py
│           ├── test_jd_extraction.py
│           └── test_jd_quality.py
├── frontend/
│   └── src/
│       ├── features/jobs/
│       │   ├── SavedJobCard.tsx
│       │   └── types.ts
│       └── test/
│           └── saved-job-card.test.tsx
└── infrastructure/
    └── scripts/
        └── rebuild_neo4j.py
```

The CLI wrapper imports `backend/app/graph/rebuild.py`; it must not duplicate rebuild logic. The embedding adapter and text normalizer are shared production components that Plan 6 extends for Candidate representation.

## 7. Technical Specifications

### 7.1 Job extraction contracts

Implement exactly:

```text
JobSkill
- skill: SkillRef
- confidence: float in [0, 1]
- evidence: list[str]

JobPostExtraction
- title: str | None
- company: str | None
- summary: str
- responsibilities: list[str]
- required_skills: list[JobSkill]
- preferred_skills: list[JobSkill]
- seniority: intern | junior | mid | senior | lead | unknown
- min_experience_years: float | None
- max_experience_years: float | None
- location: str | None
- work_mode: remote | hybrid | onsite | unknown
- extraction_confidence: float in [0, 1]
```

Evidence snippets are short and copied from source text. The LLM does not assign aliases, relationships, or `jd_quality`. Normalize extracted skills only through Plan 4’s shared normalizer. Validate the full extraction before any `extraction_json` write.

### 7.2 URL fetch contract

`url_fetch.py`:

- Accepts only `http` and `https` URLs.
- Uses configured `URL_FETCH_TIMEOUT_SECONDS=10` across the controlled download.
- Enforces `URL_MAX_RESPONSE_MB=5` while streaming, not after unlimited buffering.
- Accepts response content type only `text/html` or `text/plain` (ignoring charset parameters).
- Sends no cookies/authentication and uses no browser/JavaScript renderer.
- For HTML, passes decoded content to Trafilatura main-text extraction; plain text uses the decoded body directly.
- Applies the documented meaningful-JD-text check. When unavailable/unsupported/empty, returns a stable failure instructing the user to paste JD text.
- Never logs authorization headers or a full source document.

No broader URL-security system is introduced; this remains a local demo limitation documented in the final README.

### 7.3 Persistence-first ingestion and exact deduplication

`save_job` accepts a discriminated input with exactly one of `url` or `text`.

For raw text:

1. Require meaningful non-empty text and compute SHA-256 before insertion.
2. Look up `raw_content_hash`.
3. Existing non-failed row: return it unchanged with no extraction/embedding/sync.
4. Existing failed row: select that row for retry; clear `failure_code`, `extraction_json`, `jd_quality`, and all three embedding fields; set `processing`; do not create another row.
5. No match: insert one `received` row containing raw text/hash, then set it to `processing` in a short transaction.

For URL:

1. Commit a `received` placeholder containing `source_type='url'`, `source_url`, and null raw content/hash.
2. Fetch outside any transaction. Fetch failure marks that placeholder `failed` with stable code; submitted URL remains stored.
3. Compute fetched-content SHA-256 and look up an exact match.
4. Existing non-failed row: delete the temporary placeholder and return the existing row without reprocessing.
5. Existing failed row: delete the temporary placeholder, clear/reuse that failed row, and set it to `processing`.
6. No match: persist fetched raw content/hash into the placeholder, then set it to `processing`.

Processing external calls occur outside transactions. After extraction/embedding, one short transaction writes either processed terminal fields or `failed` plus stable code. Previously accepted URL/raw text is never rolled back. `processed` is terminal; different content always creates a new Job.

### 7.4 Extraction, repair, and quality classification

Processing order is:

```text
persist/select unique raw input
→ processing
→ gpt-4o-mini structured extraction
→ Pydantic validation
→ at most one schema-repair request when invalid
→ shared skill normalization
→ deterministic jd_quality classification
→ embedding for full/partial only
→ terminal SQLite commit
→ direct graph sync for scorable jobs
```

- Provider timeout/rate limit retries once; schema repair is at most one separate request; then mark failed safely.
- `full`: sufficient title/description plus usable skill/responsibility evidence and most scoring fields.
- `partial`: enough semantic and skill signal, but important fields are missing.
- `unscorable`: insufficient responsibilities/skills, contact-only content, or insufficient evidence.
- `jd_quality` exists only in the authoritative column, never inside `extraction_json`.
- Unscorable extraction is a successfully `processed` row with all embedding fields null.

### 7.5 Embedding adapter and text contract

`shopaikey_embeddings.py` is the sole production embedding adapter:

- Calls the configured OpenAI-compatible `/v1/embeddings` endpoint with `EMBEDDING_MODEL=text-embedding-3-small`, `dimensions=1536`, and float encoding.
- Supports ordered scalar/batch inputs and validates count/index order, exactly 1536 values, and finite floats.
- Emits stable timeout/rate-limit/invalid-response codes; it never switches model/dimensions.

`embedding_text.py` owns one shared whitespace normalizer and versioned builders. `build_job_embedding_text_v1` concatenates in this order:

```text
title + summary + responsibilities + required skills + preferred skills
```

Use structured extraction, canonical skill display names, deterministic separators, and the same documented whitespace normalization that Plan 6 must reuse. No E5 query/passage prefixes.

Processed `full|partial` rows require `embedding_json`, configured model, and `1536`; every other row requires all embedding fields null. Validate exact finite length before the terminal write.

### 7.6 Job tools

`save_job(url | text)`:

- Owns persistence-first fetching/extraction/dedup/embedding/direct-sync orchestration.
- Requires no approval and is allowed with or without an active profile/draft.
- Returns compact ID, title/company when available, status, quality, source URL, and whether the row was created/returned/retried; never raw content.
- A direct-sync failure after processed commit returns `NEO4J_SYNC_FAILED` and rebuild instruction without changing the processed row.

`query_jobs(job_id?, processing_status?, jd_quality?, limit=...)`:

- Is read-only; validates `limit in 1..50`.
- Returns compact saved-job/status/quality data, newest deterministic results, and no raw JD by default.
- Supports the exact database status/quality vocabulary only.

These become production tools four and five. Tool execution/replay remains owned by Plan 3.

### 7.7 Direct Job graph synchronization

After a scorable terminal SQLite commit, `sync_job.py` uses idempotent parameterized Cypher to:

- `MERGE` `Job{id=<SQLite UUID>}`.
- Set title, company, location, work mode, seniority, quality, 1536-float embedding, and `source_updated_at=job_posts.updated_at`.
- Replace this Job’s `REQUIRES`/`PREFERS` relationships from the validated normalized extraction.
- `MERGE` canonical Skill nodes and relationship properties `confidence`/evidence.
- Reuse existing seed Skills/`RELATED_TO`; do not generate new relationships from LLM output.

Failed or unscorable rows are not vector-queryable Job nodes. Exact duplicates do not create another node. SQLite remains authoritative if sync fails.

### 7.8 Rebuild command

`python infrastructure/scripts/rebuild_neo4j.py` calls one application rebuild service that:

1. Reads every processed `full|partial` row and verifies stored embedding model/dimensions/exact finite vector length against locked settings. On mismatch, exit non-zero with an instruction to restore the original configuration; do not call the provider or re-embed.
2. Clears only JobAgent `Candidate`, `Job`, and `Skill` nodes and their JobAgent relationships. It must not issue an unrestricted database wipe.
3. Recreates idempotent uniqueness constraints and the cosine/1536 vector index.
4. Reads the active Candidate (if present) and all scorable Jobs from SQLite.
5. Reuses `sync_candidate.py`, `sync_job.py`, and the seed loader to rebuild Candidate, Job, Skill, `HAS_SKILL`, `REQUIRES`, `PREFERS`, and `RELATED_TO` data.
6. Makes no ShopAIKey call and performs no SQLite mutation.
7. Prints counts for Candidate, Job, Skill, and each relationship type; exits non-zero on any failure.

### 7.9 Frontend saved-job display

Use pinned Astryx `Card`, `MetadataList`, `Badge`, and tool status components. A saved-job card may show ID, title, company, source URL, processing status, quality, and concise result/failure summary. It must not show full raw content or imply ranking.

## 8. Implementation Steps

- [ ] Define failing Job schema/quality tests, then implement exact extraction models and deterministic classifier.
- [ ] Implement bounded HTTP/HTTPS fetch and Trafilatura/plain-text extraction with fake HTTP tests.
- [ ] Implement Job repository transitions and exact-hash lookups by reusing existing session/UUID/UTC helpers.
- [ ] Implement raw-text persistence-first selection and prove duplicate return/failed-row retry without new rows.
- [ ] Implement URL placeholder/fetch/hash/placeholder-delete flow and prove raw URL/text retention on failures.
- [ ] Implement structured extraction, one repair, shared skill normalization, and terminal quality persistence.
- [ ] Implement the sole production embedding adapter, whitespace normalizer, and versioned Job text builder with deterministic fake vectors.
- [ ] Enforce scorable/all-or-none embedding invariants before every terminal write.
- [ ] Implement `save_job`/`query_jobs` and register them with the existing Agent/tool runtime.
- [ ] Implement idempotent direct Job sync by reusing graph/seed primitives.
- [ ] Implement rebuild service and thin CLI wrapper by reusing Candidate/Job sync functions.
- [ ] Implement concise saved-job card/status UI.
- [ ] Add unit/integration/frontend tests for URL/text paths, exact duplicates, failed retry, extraction/embedding failure, graph sync/rebuild, and compact output.

## 9. Verification & Testing Plan

### Backend commands

```powershell
Set-Location backend
python -m pytest tests/unit/test_jd_extraction.py tests/unit/test_jd_quality.py -q
python -m pytest tests/unit/test_embedding_adapter.py tests/unit/test_embedding_text.py -q
python -m pytest tests/integration/test_job_ingestion.py tests/integration/test_job_sync.py -q
python -m pytest tests/integration/test_graph_rebuild.py -q
```

Expected evidence:

- URL/text input persists before extraction; raw input remains after provider/schema failure.
- Processed duplicate returns the same ID without provider/embedding calls; failed duplicate retries the same ID after clearing terminal fields.
- URL placeholder is deleted whenever an existing row is selected.
- Full/partial rows have exact fake 1536-float embeddings; unscorable/failed rows have none.
- Job/Skill sync is idempotent and uses matching IDs/timestamps.
- Rebuild restores Candidate/Job/Skill counts from SQLite without provider calls or SQLite changes; mismatched embedding configuration fails with restoration instructions.

### Frontend commands

```powershell
Set-Location frontend
npm test -- --run src/test/saved-job-card.test.tsx
npm run typecheck
npm run build
```

Expected: compact status/quality/source rendering, exact tool statuses, and truthful failed/sync-failed states without raw JD text.

### Controlled local checks

- Submit one public supported URL and one pasted synthetic JD; verify each creates a durable row and scorable rows appear in Neo4j with equal ID/`source_updated_at`.
- Submit identical processed text; verify no second row/node/provider call.
- Simulate fetch/extraction/embedding/Neo4j failures and verify durable input plus stable truthful status.
- Run rebuild against a fresh Neo4j volume and compare printed counts to SQLite.

Normal tests must use fake HTTP/provider/embedding adapters. The real ShopAIKey diagnostic remains a separate explicit smoke command.

### Failure handling

- Unsupported/unavailable URL asks for pasted text and leaves its URL placeholder failed.
- Invalid structured output gets one repair, then a failed row; no false success.
- Neo4j sync failure preserves processed SQLite data and returns `NEO4J_SYNC_FAILED` with rebuild instruction.
- Embedding mismatch/non-finite response prevents a scorable terminal commit and is never silently corrected by changing configuration.

## 10. Handoff Notes for Plan 6 / Master Phase 5

Plan 6 receives:

- Durable processed/failed Jobs with exact duplicate semantics and authoritative quality.
- Validated normalized Job facts/evidence and shared Skill identities.
- The sole production embedding adapter, shared whitespace normalizer, and versioned Job representation builder.
- Scorable Job embeddings stored in SQLite and synchronized to Neo4j with source revisions.
- Production tools `save_job` and `query_jobs`, bringing the registered total to five.
- A complete non-provider Neo4j rebuild command.

Plan 6 adds only the versioned Candidate representation, consistency check, retrieval/scoring/explanation, sixth tool (`match_jobs`), and match UI. It must not reimplement ingestion, normalization, embeddings transport, Job sync, or rebuild behavior.
