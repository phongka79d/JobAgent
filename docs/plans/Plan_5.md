# Plan 5 - Master Phase 4: JD Ingestion, Extraction, Deduplication, and Graph Sync

## 1. Objective

Implement persistence-first ingestion for public JD URLs and raw text, secure extraction, structured Job records, explicit quality/status dimensions, exact and normalized duplicate handling, shared skill normalization, ShopAIKey embeddings, and rebuildable Job/Skill/JobFamily synchronization to Neo4j.

## 2. Source of Truth

- `Master_plan.md` sections 6.3, 7.1, 7.4, and 7.5 for Job status and extraction contracts.
- Sections 8-9 for graph data and shared skill normalization.
- Section 11, **JD Ingestion Flow**.
- Tool contracts 13.5-13.6 and the authorization matrix.
- Sections 16-17 for structured extraction and selected embeddings.
- Sections 20-24 for failure, outbox, SSRF/privacy, environment, and tests.
- Section 25, **Phase 4 - JD ingestion, extraction, deduplication, and graph sync**.
- `Plan_4.md` owns shared skill contracts, Agent tool seams, and outbox patterns reused here.

## 3. Prerequisites from Prior Phases

- [ ] `job_posts` and `graph_sync_outbox` tables are migrated.
- [ ] Agent tool registration, SSE status, and structured chat cards are stable.
- [ ] ShopAIKey schema mode and the `text-embedding-3-small` 1536-dimensional contract are locked.
- [ ] Shared `SkillRef` canonicalization, verified aliases, and provisional-skill rules exist.
- [ ] Neo4j constraints/vector index and replay-safe outbox processing are available.

## 4. Scope

- Accept exactly one public HTTP/HTTPS URL or raw JD text through `save_job`.
- Implement DNS/redirect-aware SSRF protection and bounded HTTP retrieval.
- Use Trafilatura for HTML main text and request pasted text when meaningful extraction fails.
- Persist raw input before structured extraction and retain failed records.
- Implement JobPost structured extraction with one schema-repair attempt.
- Classify JDs as `full`, `partial`, or `unscorable` with reasons.
- Implement exact-content and normalized company/title/location duplicate policies, including explicit `force_new` authorization.
- Reuse shared skill normalization and seed aliases; create deterministic provisional skills.
- Implement `save_job` and read-only `query_jobs` tools.
- Generate ShopAIKey embeddings for active scorable records.
- Synchronize active Job, Skill, and JobFamily graph data through the outbox.
- Render sanitized JD tool status and a saved-job card in chat.

## 5. Out of Scope

- Automatic crawling/discovery, authenticated/paywalled pages, cookies, JavaScript rendering, or browser automation.
- Matching/ranking, score caches, graph boosts, evaluation tuning, or top-result cards.
- Synchronizing or scoring ignored duplicates or unscorable records.
- Salary-based scoring, automatic trusted `RELATED_TO` edges, global ontology building, or reranking.
- Public Job CRUD endpoints, background worker infrastructure, or continuous outbox polling.

## 6. Target Directory Structure

```text
JobAgent/
|-- backend/
|   |-- app/
|   |   |-- tools/{save_job.py,query_jobs.py}
|   |   |-- services/{url_fetcher.py,jd_ingestion.py,jd_extraction.py,skill_normalization.py,embeddings.py}
|   |   |-- repositories/{job_posts.py,skills.py}
|   |   |-- schemas/{job_post.py,job_tools.py}
|   |   |-- graph/{job_sync.py,outbox_processor.py}
|   |   `-- security/url_policy.py
|   |-- evaluation/fixtures/
|   `-- tests/{unit,integration}/
`-- frontend/
    `-- src/features/jobs/{components,state}/
```

Tool wrappers validate Agent-facing inputs and delegate to one ingestion service. URL policy, extraction, normalization, persistence, and graph sync remain separate focused modules.

## 7. Technical Specifications

### 7.1 URL security contract

Allow only `http` and `https`. Reject credentials in URLs and block localhost names plus loopback, private, link-local, unspecified, multicast, and cloud metadata address ranges for IPv4 and IPv6. Resolve all A/AAAA results before connecting and reject when any resolved address is forbidden. Re-resolve and validate every redirect target; allow at most three redirects. Apply a 10-second timeout, 5 MB streamed-body ceiling, and `text/html|text/plain` content-type allowlist. Use no cookies, authentication, proxy bypass, browser session, or JavaScript renderer.

### 7.2 Job extraction contract

Implement the master-defined `JobPostExtraction` fields exactly:

```text
title, company, summary, responsibilities,
required_skills, preferred_skills,
seniority, min_experience_years, max_experience_years,
location, work_mode, employment_type,
education_requirements, language_requirements,
salary_text, job_family, extraction_confidence, jd_quality
```

Required/preferred skills use `SkillRef` plus confidence/evidence. Evidence is short and source-grounded. Salary is display-only. The quality classifier stores reasons separately from the extraction object: `full` needs usable title/description and scoring evidence; `partial` supports at least semantic and skill signals but misses important fields; `unscorable` lacks meaningful responsibility/skill evidence.

### 7.3 Persistence-first state machine

```text
received -> processing -> processed
                      `-> failed
```

Persist source type, source URL when present, and raw content before LLM extraction. Store failures with a stable error code and sanitized message. Keep `processing_status`, `jd_quality`, `graph_sync_status`, and `record_status` independent. A provider timeout/rate limit retries once; invalid output receives at most one repair.

### 7.4 Duplicate policy

Compute SHA-256 `raw_content_hash` over canonicalized retrieved/pasted text before extraction. An exact hash returns the existing Job ID and performs no insert, extraction, embedding, or sync. After extraction, compute a normalized key only when company, title, and location are sufficient. A matching normalized key with different content inserts a row with `record_status=ignored_duplicate`, `duplicate_of_job_id`, and `graph_sync_status=not_required`; it is not embedded or scored. `force_new=true` is accepted only when the current user turn explicitly states this is a separate position and that authorization is recorded.

### 7.5 Skill normalization

Use one shared pipeline: Unicode normalization, whitespace collapse, lowercase comparison, punctuation/separator normalization, verified seed alias resolution, existing canonical lookup, then deterministic provisional key creation. Store aliases on the canonical Skill. Only seed or explicit-user-confirmed `RELATED_TO` edges are verified and later score-bearing.

### 7.6 Embedding and graph synchronization

Embed only active `full|partial` jobs through ShopAIKey `text-embedding-3-small` with `dimensions=1536`, using the master Job representation: title + summary + responsibilities + required skills + preferred skills. Use bounded batches, preserve input/output ordering, and apply no E5 prefixes. Store model and dimension identity with canonical Job state and enqueue Job sync. Outbox processing `MERGE`s Job, Skill, JobFamily, `REQUIRES`, `PREFERS`, and `IN_FAMILY` by SQLite IDs/canonical keys. Replays must not duplicate data. Ignored duplicates and unscorable jobs never enter Neo4j.

### 7.7 Tool outputs

`save_job` returns Job ID, source, processing result, quality/reasons, duplicate outcome, graph-sync state, and a sanitized display summary. `query_jobs` accepts a Job ID or bounded filters and returns compact structured fields/score details when present; it does not return raw content or an unbounded corpus.

## 8. Implementation Steps

- [ ] Implement the URL parser, DNS/IP policy, bounded redirect loop, streaming response limit, and SSRF tests.
- [ ] Implement raw-text validation and Trafilatura extraction with meaningful-text checks.
- [ ] Implement JobPost schemas, quality classifier, one-repair extraction adapter, and evidence validation.
- [ ] Implement persistence-first repository transitions and stable failure codes.
- [ ] Implement exact-hash deduplication before extraction and normalized-key deduplication after extraction.
- [ ] Consolidate skill normalization into the shared service and add the small verified `skills_seed.yaml`.
- [ ] Implement `save_job` authorization/orchestration and bounded `query_jobs` reads.
- [ ] Implement the embedding text builder and ShopAIKey batch adapter using the locked contract.
- [ ] Implement Job graph payloads, outbox processing, replay safety, and rebuild data loader.
- [ ] Add sanitized tool events and saved-job chat card.
- [ ] Add unit, integration, Agent-tool, graph, and frontend tests.

## 9. Verification & Testing Plan

- Unit-test URL schemes, credentials, private/loopback/link-local/metadata IPs, DNS rebinding-resistant validation, redirects, content types, timeout, and body limit.
- Verify a failed URL extraction asks for pasted text and creates no hidden browser fallback.
- Verify raw input persists before extraction and remains after provider/schema failure.
- Verify exactly one retry for provider timeout and one repair for invalid schema.
- Test `full`, `partial`, and `unscorable` classifications with required reasons.
- Verify exact duplicates do not insert/reprocess and normalized duplicates persist but do not embed/sync/score.
- Verify unauthorized `force_new` is rejected and explicit authorization creates an active separate record.
- Verify skill alias/provisional behavior is identical for Candidate and Job paths.
- Replay Job outbox operations and rebuild from SQLite; compare active/scorable IDs and entity counts.
- Verify chat/log output contains no raw JD, secret, internal stack trace, or unsafe URL details.

The phase exits only when raw inputs survive failures, duplicate rules are exact, private/local URLs are blocked, and all active scorable jobs are queryable in Neo4j with matching SQLite IDs.

## 10. Handoff Notes for Plan 6 (Master Phase 5)

Plan 6 receives:

- Active `full|partial` Job records with canonical structured fields and ShopAIKey embeddings.
- Ignored/unscorable records explicitly excluded from retrieval.
- Candidate and Job Skill nodes with direct/alias data and only verified score-bearing relationships.
- Rebuildable Neo4j Job vector index and synchronized SQLite IDs.
- Stable `query_jobs`/tool-result/card seams for adding score details.

Plan 6 owns retrieval, deterministic scoring, explanations, tuning, and evaluation. It must not re-extract JDs, create a second normalization path, score ignored/unscorable records, or make SQLite subordinate to Neo4j.
