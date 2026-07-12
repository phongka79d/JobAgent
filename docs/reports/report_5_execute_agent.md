---

# Task Execution Report - 01A

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch01 - Safe Public JD Input Acquisition

## Task
01A - Enforce DNS/redirect-aware URL policy and bounded HTTP retrieval

## Status
complete

## Selected Scope
- Batch: Mandatory Batch01 - Safe Public JD Input Acquisition
- Task ID: 01A
- Task title: Enforce DNS/redirect-aware URL policy and bounded HTTP retrieval
- Files allowed / repair scope: `backend/app/security/__init__.py`, `backend/app/security/url_policy.py`, `backend/app/services/url_fetcher.py`, `backend/pyproject.toml`, `backend/tests/security/test_url_policy.py`, `backend/tests/services/test_url_fetcher.py`

## Source of Truth Used
- docs/plans/Plan_5.md > ### 7.1 URL security contract
- docs/plans/Plan_5.md > ## 5. Out of Scope
- docs/plans/Master_plan.md > ### 11.2 URL security
- docs/plans/Master_plan.md > ## 20. Failure and Recovery Policy

## Supplemental Documents Used
- docs/plans/Plan_5.md
- docs/plans/Master_plan.md
- docs/tasks/task_5.md (01A block)

## Dependency and User Action Check
- Dependencies: Existing `backend/app/config.py` URL timeout/body settings (`URL_FETCH_TIMEOUT_SECONDS`, `URL_MAX_RESPONSE_MB`) and locked httpx choice present
- User Action: None required
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_5.md
- docs/plans/Plan_5.md (Â§5, Â§7.1)
- docs/plans/Master_plan.md (Â§3 stack, Â§11.2, Â§20)
- backend/app/config.py
- backend/pyproject.toml
- backend/app/services/shopaikey_chat.py (stable code-only error pattern)
- backend/app/services/pdf_text.py (stable code-only error pattern)
- backend/app/services/attachment_storage_errors.py
- backend/tests/test_config.py (URL settings presence)

## Completed Work
- Searched configuration/HTTP/provider surfaces; reused typed root `url_fetch_timeout_seconds` / `url_max_response_mb` via `UrlFetcher.from_settings`.
- Added direct exact runtime pins: `httpx==0.28.1`, `trafilatura==2.1.0` (Python 3.13 resolved via `pip install -e ".[test]"`).
- Implemented pure `app/security/url_policy.py`: credential-free HTTP/HTTPS only; blocks localhost/metadata hostnames; blocks loopback/private/link-local/unspecified/multicast/reserved/metadata IPv4+IPv6 including IPv4-mapped forms; validates every DNS answer (mixed sets fail closed); re-validates redirect targets.
- Implemented `app/services/url_fetcher.py`: injected DNS resolver + transport factory; `BoundIPTransport` dials only a pre-vetted address while preserving Host/SNI; manual redirect loop (max 3); overall timeout budget; streamed body ceiling (5 MB default); `text/html|text/plain` media-type allowlist with parameter stripping; `trust_env=False`, no cookies/auth/auto-redirect; stable sanitized `UrlFetchError` codes only.
- Added injected security matrix tests (no public network): allowed public targets, mixed safe/forbidden DNS, rebinding on redirect, redirect overflow, timeouts, media-type parameters, oversized/streaming bodies, peer-within-vetted-set, secret/URL-detail absence, no second fetch stack.

## Files Created or Modified
- backend/app/security/__init__.py (created)
- backend/app/security/url_policy.py (created)
- backend/app/services/url_fetcher.py (created)
- backend/pyproject.toml (httpx/trafilatura exact pins)
- backend/tests/security/__init__.py (created)
- backend/tests/security/test_url_policy.py (created)
- backend/tests/services/test_url_fetcher.py (created)

## Tests or Validations Run
- command/check: `cd backend; python -m pip install -e ".[test]"`
- required: yes
- result: passed
- evidence or reason: Exact pins resolved on Python 3.13.7; `httpx==0.28.1` and `trafilatura==2.1.0` installed successfully (exit 0).

- command/check: `cd backend; python -m pytest -q tests/security/test_url_policy.py tests/services/test_url_fetcher.py`
- required: yes
- result: passed
- evidence or reason: 69 passed in ~1.1s; injected DNS/transport only (no network calls).

- command/check: `cd backend; python -m ruff check app/security app/services/url_fetcher.py tests/security tests/services/test_url_fetcher.py`
- required: yes
- result: passed
- evidence or reason: All checks passed.

- command/check: `cd backend; python -m mypy app/security app/services/url_fetcher.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 3 source files.

## Acceptance Check
- condition: Forbidden address classes, URL credentials, unsafe redirects, and mixed DNS answer sets fail before content is accepted
- status: satisfied
- evidence: Policy and fetcher tests for credentials, localhost/metadata, private/loopback/link-local/IPv4-mapped, mixed DNS, redirect-to-private, and rebinding sequences.

- condition: At most three redirects; configured timeout; 5 MB body ceiling; only text/html|text/plain
- status: satisfied
- evidence: Redirect overflow, timeout mapping, oversized/streaming body, media-type parameter and rejection tests; settings-driven ceilings via `from_settings`.

- condition: Connected/peer address stays within validated set; failures/logs lack raw URL, DNS detail, proxy credential, or response body
- status: satisfied
- evidence: Peer-within-vetted-set test; code-only exception str/repr assertions excluding secrets, URLs, bodies, and address detail.

- condition: No browser, JavaScript renderer, cookie, authentication, public network test, or second fetch implementation
- status: satisfied
- evidence: Single httpx-based fetcher; trust_env/follow_redirects/auth assertions; module scan for requests/playwright/selenium; all tests injected.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode â€” A1 must not update checkboxes or batch status

## Key Implementation Decisions
- SSRF connect path uses httpcore `network_backend` so TCP dials the vetted IP while Host/SNI remain the policy-validated hostname (no unguarded re-resolve).
- Mixed DNS answers fail closed entirely (no â€œprefer publicâ€ filtering).
- Trafilatura pinned now for locked-stack installability; HTML extraction remains task 01B scope.

## Notes for Review Agent
- changed files: security package, url_fetcher, pyproject pins, security/fetcher tests
- validations to rerun: the three required backend commands above
- risk areas: BoundIPTransport TLS path is production-oriented; unit tests inject ScriptedTransport and do not exercise live TLS
- next task readiness: can_review

---

# Task Execution Report - 01B

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch01 - Safe Public JD Input Acquisition

## Task
01B - Produce deterministic meaningful JD text from URL or pasted input

## Status
complete

## Selected Scope
- Batch: Mandatory Batch01 - Safe Public JD Input Acquisition
- Task ID: 01B
- Task title: Produce deterministic meaningful JD text from URL or pasted input
- Files allowed / repair scope: `backend/app/services/jd_source.py`, `backend/tests/services/test_jd_source.py`, `backend/tests/fixtures/jds/*`

## Source of Truth Used
- docs/plans/Plan_5.md > ## 4. Scope
- docs/plans/Plan_5.md > ## 5. Out of Scope
- docs/plans/Plan_5.md > ## 9. Verification & Testing Plan
- docs/plans/Master_plan.md > ### 11.1 Accepted inputs
- docs/plans/Master_plan.md > ### 11.2 URL security

## Supplemental Documents Used
- docs/plans/Plan_5.md
- docs/plans/Master_plan.md
- docs/tasks/task_5.md (01B block)

## Dependency and User Action Check
- Dependencies: (01A) controlled fetch result (`UrlFetcher` / `UrlFetchResult`) and direct Trafilatura pin (`trafilatura==2.1.0`) present
- User Action: None during normal execution; runtime paste after `JD_TEXT_REQUIRED` is a product outcome, not an agent blocker
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_5.md
- docs/plans/Plan_5.md (§4, §5, §9)
- docs/plans/Master_plan.md (§11.1, §11.2)
- backend/app/services/url_fetcher.py
- backend/app/schemas/chat.py (32_768 pasted user-text ceiling)
- backend/app/services/chat_service.py (user-text size validation pattern)
- backend/app/services/pdf_text.py (stable code-only error pattern)
- backend/app/services/pii_redaction.py (code-only error pattern)
- backend/app/services/skill_normalization.py (Unicode primitives; not reused for JD identity — case/punctuation must be preserved)
- backend/tests/services/test_url_fetcher.py (injected fetcher test patterns)
- backend/pyproject.toml (trafilatura pin)

## Completed Work
- Searched text normalization, chat-size, PII-redaction, and extraction helpers; reused the chat 32,768-character pasted ceiling as `MAX_PASTED_JD_TEXT_LEN`.
- Implemented `app/services/jd_source.py`: strict one-of `url`/`raw_text` validation; NFC Unicode + line-ending + edge-whitespace canonicalization preserving semantic case/punctuation/internal structure; SHA-256 content hash over canonical UTF-8 text.
- Raw path never invokes the fetcher; URL path requires (01A) `UrlFetcher` and never bypasses it (`UrlFetchError` propagated unchanged).
- Approved `text/plain` bodies decode directly; approved `text/html` runs through Trafilatura only (`include_comments=False`, `with_metadata=False`, no scripts/links/formatting); blank/failed extraction returns `JD_TEXT_REQUIRED` with no browser/JavaScript/alternate-parser/provider fallback.
- Contact-only nonblank HTML is acquired (quality classification deferred to Batch02).
- Added synthetic fixtures under `tests/fixtures/jds/` and focused tests covering equivalent raw/plain/HTML hashes, blank/malformed/extraction failure, oversize paste, no-fallback/no-leak surfaces.

## Files Created or Modified
- backend/app/services/jd_source.py (created)
- backend/tests/services/test_jd_source.py (created)
- backend/tests/fixtures/jds/equivalent_plain.txt (created)
- backend/tests/fixtures/jds/equivalent.html (created)
- backend/tests/fixtures/jds/blank.html (created)
- backend/tests/fixtures/jds/malformed.html (created)
- backend/tests/fixtures/jds/contact_only.html (created)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_jd_source.py tests/services/test_url_fetcher.py`
- required: yes
- result: passed
- evidence or reason: 43 passed in ~1.75s (raw/plain/HTML acquisition, no-fallback, and existing 01A fetcher suite).

- command/check: `cd backend; python -m ruff check app/services/jd_source.py tests/services/test_jd_source.py`
- required: yes
- result: passed
- evidence or reason: All checks passed (after isort fix).

- command/check: `cd backend; python -m mypy app/services/jd_source.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 1 source file.

## Acceptance Check
- condition: Exactly one URL or raw-text input; raw path never calls fetcher; URL path never bypasses (01A)
- status: satisfied
- evidence: One-of validation tests; CountingFetcher raw-path assertion; URL path uses `UrlFetcher.fetch` and propagates `UrlFetchError` for blocked targets.

- condition: Equivalent URL/pasted content produces identical canonical text/hash; case, punctuation, and line content preserved
- status: satisfied
- evidence: Plain URL vs paste parity test; HTML URL vs paste-of-extracted-text hash identity; Unicode NFC/CRLF/edge-whitespace canonicalization tests preserve `Senior Engineer!` / `C++` style content.

- condition: Blank/failed Trafilatura output returns `JD_TEXT_REQUIRED` with no Job row, provider, browser, JavaScript, authenticated, or paywall fallback
- status: satisfied
- evidence: blank.html, malformed.html, and extractor-exception tests return only `JD_TEXT_REQUIRED`; no Job persistence/provider calls in this module; single controlled GET only.

- condition: Raw JD text and unsafe source details absent from exception strings, logs, or test snapshots of error surfaces
- status: satisfied
- evidence: Code-only `JdSourceError` str/repr with cleared cause/context; leak assertions against JD body, emails, URLs, secrets, browser tool names.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode — A1 must not update checkboxes or batch status

## Key Implementation Decisions
- Pasted ceiling mirrors chat turn limit (32_768) rather than the 5 MB HTTP body ceiling.
- HTML vs paste hash identity is proven after Trafilatura extraction (paste the acquired main text), which is the later exact-hash contract.
- Nonblank contact-only extraction is treated as acquired content; unscorable classification remains Batch02.

## Notes for Review Agent
- changed files: `jd_source.py`, `test_jd_source.py`, `tests/fixtures/jds/*`
- validations to rerun: the two required backend command groups above
- risk areas: Trafilatura main-text output can include nav/footer noise on real pages; quality gating is intentionally out of scope for 01B
- next task readiness: can_review

---

# Task Execution Report - 02A

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch02 - Validated Job Records and Persistence

## Task
02A - Validate grounded Job extraction and deterministic quality

## Status
complete

## Selected Scope
- Batch: Mandatory Batch02 - Validated Job Records and Persistence
- Task ID: 02A
- Task title: Validate grounded Job extraction and deterministic quality
- Files allowed / repair scope: `backend/app/schemas/job_post.py`, `backend/app/services/jd_quality.py`, `backend/app/services/jd_extraction.py`, `backend/app/schemas/__init__.py`, `backend/tests/schemas/test_job_post.py`, `backend/tests/services/test_jd_quality.py`, `backend/tests/services/test_jd_extraction.py`

## Source of Truth Used
- docs/plans/Plan_5.md > ### 7.2 Job extraction contract
- docs/plans/Plan_5.md > ### 7.3 Persistence-first state machine
- docs/plans/Master_plan.md > ### 7.1 Shared skill contract
- docs/plans/Master_plan.md > ### 7.4 Job extraction
- docs/plans/Master_plan.md > ### 7.5 JD quality rules

## Supplemental Documents Used
- docs/plans/Plan_5.md
- docs/plans/Master_plan.md
- docs/tasks/task_5.md (02A block)

## Dependency and User Action Check
- Dependencies: (01B) accepted; existing `SkillRef`, deterministic PII redaction, untrusted-document wrapper pattern, and `ShopAIKeyChatAdapter.invoke_structured`
- User Action: None required
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_5.md
- docs/plans/Plan_5.md (Â§7.2, Â§7.3)
- docs/plans/Master_plan.md (Â§7.1, Â§7.4, Â§7.5, Â§8.2, Â§18.2)
- backend/app/schemas/candidate.py
- backend/app/schemas/preferences.py
- backend/app/schemas/__init__.py
- backend/app/services/profile_extraction.py
- backend/app/services/shopaikey_chat.py
- backend/app/services/pii_redaction.py
- backend/app/db/enums.py
- backend/app/db/models/jobs.py
- backend/tests/schemas/test_candidate.py
- backend/tests/services/test_profile_extraction.py
- backend/tests/fakes/profile_extraction.py
- backend/tests/services/test_shopaikey_chat.py

## Completed Work
- Reused Candidate strict Pydantic bounds (`SkillRef`, evidence/confidence/years helpers), profile extraction grounding/PII fail-closed pattern, untrusted document delimiting, and `ShopAIKeyChatAdapter.invoke_structured` ceilings (no second retry loop).
- Defined `JobSkill` as shared `SkillRef` plus relationship-level confidence/evidence only (no weights, match fields, or trusted graph relationships).
- Defined `JobPostExtraction` with exact master field inventory and enums: seniority, work_mode (+unknown), employment_type, jd_quality; salary display-only; `extra="forbid"`.
- Implemented deterministic classifier in `jd_quality.py`: full = usable title + description + grounded responsibility/skill evidence + majority (5/9) scoring-field groups; partial = semantic + grounded skill signals below full; unscorable for contact-only/lower cases; reasons outside extraction for every non-full outcome; salary excluded from scoring groups.
- Implemented `jd_extraction.py`: untrusted JD wrapper, single adapter invoke, evidence grounding against canonical source, contact-PII reject via `redact_pii`, deterministic quality overwrite, stable code-only failures.
- Added fake-backed tests for schema/enums/bounds, quality category boundaries/reasons, fabricated evidence, overlong evidence, prompt injection delimiting, PII failure, one transient retry, one schema repair, and zero raw/provider leakage.

## Files Created or Modified
- backend/app/schemas/job_post.py (created)
- backend/app/services/jd_quality.py (created)
- backend/app/services/jd_extraction.py (created)
- backend/app/schemas/__init__.py (exports)
- backend/tests/schemas/test_job_post.py (created)
- backend/tests/services/test_jd_quality.py (created)
- backend/tests/services/test_jd_extraction.py (created)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/schemas/test_job_post.py tests/services/test_jd_quality.py tests/services/test_jd_extraction.py tests/services/test_shopaikey_chat.py tests/services/test_pii_redaction.py`
- required: yes
- result: passed
- evidence or reason: 115 passed in ~1.3s; fakes only (no real ShopAIKey calls).

- command/check: `cd backend; python -m ruff check app/schemas/job_post.py app/services/jd_quality.py app/services/jd_extraction.py tests/schemas/test_job_post.py tests/services/test_jd_quality.py tests/services/test_jd_extraction.py`
- required: yes
- result: passed
- evidence or reason: All checks passed (after isort auto-fix on two test modules).

- command/check: `cd backend; python -m mypy app/schemas/job_post.py app/services/jd_quality.py app/services/jd_extraction.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 3 source files.

## Acceptance Check
- condition: Extraction schema contains exactly source-required fields and rejects extra/invalid enums, confidence, years, and evidence
- status: satisfied
- evidence: `test_job_post.py` exact field-set assertion, enum/confidence/years/evidence/extra-forbid cases.

- condition: Required/preferred evidence is short, contact-redacted, and grounded in canonical JD text; fabricated evidence cannot persist
- status: satisfied
- evidence: grounding tests reject fabricated/empty evidence; PII tests reject email/phone in extraction; schema rejects overlong evidence.

- condition: Representative full, partial, unscorable, and contact-only fixtures produce deterministic categories with reasons for every non-full result
- status: satisfied
- evidence: `test_jd_quality.py` and extraction path tests for full (empty reasons), partial (reasons), unscorable/contact-only (reasons).

- condition: Tests prove exactly one transient retry and one invalid-schema repair ceiling through the reused adapter, with zero real provider calls
- status: satisfied
- evidence: `test_jd_extraction.py` timeout retry once, repair once then succeed/fail; `StructuredFactory` injectable fake; existing `test_shopaikey_chat.py` ceilings remain green.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode â€” A1 must not update checkboxes or batch status

## Key Implementation Decisions
- `JobSkill` wraps unchanged `SkillRef` with relationship confidence/evidence (Master Â§8.2 REQUIRES/PREFERS props); no SkillRef mutation.
- Nine scoring-field groups aligned to hybrid components plus education/language/job_family; majority threshold is 5; salary excluded.
- Classifier always overwrites LLM-supplied `jd_quality`; reasons live on `JdQualityAssessment` / `JobExtractionResult.quality_reasons`, not inside nested fields beyond the enum value itself.
- Contact PII fail-closed mirrors profile extraction (reject rather than silently strip) so contact evidence cannot persist.

## Notes for Review Agent
- changed files: `job_post.py`, `jd_quality.py`, `jd_extraction.py`, `schemas/__init__.py`, three new test modules
- validations to rerun: the two required backend command groups in the task Validation section
- risk areas: majority threshold and nine-group inventory are an executable interpretation of Master Â§7.5 + Â§18.2; 02B owns persistence of `quality_reasons`
- next task readiness: can_review

---

# Task Execution Report - 02B

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch02 - Validated Job Records and Persistence

## Task
02B - Implement persistence-first Job state and duplicate primitives

## Status
complete

## Selected Scope
- Batch: Mandatory Batch02 - Validated Job Records and Persistence
- Task ID: 02B
- Task title: Implement persistence-first Job state and duplicate primitives
- Files allowed / repair scope: `backend/app/repositories/job_posts.py`, `backend/app/repositories/__init__.py`, `backend/tests/repositories/test_job_posts.py`, `backend/tests/db/test_models.py`, `backend/tests/integration/test_migrations.py`

## Source of Truth Used
- docs/plans/Plan_5.md > ### 7.3 Persistence-first state machine
- docs/plans/Plan_5.md > ### 7.4 Duplicate policy
- docs/plans/Plan_5.md > ### 7.7 Tool outputs
- docs/plans/Master_plan.md > ### 6.3 Job status dimensions
- docs/plans/Master_plan.md > ### 11.4 Duplicate policy

## Supplemental Documents Used
- docs/plans/Plan_5.md
- docs/plans/Master_plan.md
- docs/tasks/task_5.md (02B block)
- docs/reports/report_5_execute_agent.md (prior 02A block for quality_reasons handoff)

## Dependency and User Action Check
- Dependencies: (02A) JobPostExtraction/JdQuality schemas present; existing JobPost ORM/migration with unique raw_content_hash and four independent status columns; caller-owned repository patterns (profiles, agent_runs) present
- User Action: None required
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_5.md
- docs/plans/Plan_5.md (§7.3, §7.4, §7.7)
- docs/plans/Master_plan.md (§6.3, §11.3, §11.4, §13.5-13.6)
- backend/app/db/models/jobs.py
- backend/app/db/enums.py
- backend/app/schemas/job_post.py
- backend/app/services/jd_source.py (hash_canonical_text)
- backend/app/services/jd_quality.py (quality_reasons shape)
- backend/app/repositories/agent_runs.py (ON CONFLICT + FSM pattern)
- backend/app/repositories/profiles.py (validated JSON boundary pattern)
- backend/app/repositories/tool_executions.py (error sanitization)
- backend/app/repositories/__init__.py
- backend/migrations/versions/c885a5846d85_initial_application_schema.py (job_posts unique hash)
- backend/tests/db/test_models.py
- backend/tests/integration/test_migrations.py
- backend/tests/repositories/test_agent_runs.py (concurrent race pattern)
- backend/tests/repositories/test_profiles.py

## Completed Work
- Searched JobPost/migration/repository/hash callers; reused existing job_posts schema only (no Skill table, no new migration). Confirmed unique `raw_content_hash` supports exact no-insert under SQLite concurrency via INSERT ON CONFLICT DO NOTHING.
- Implemented `JobPostRepository` (caller-owned flush-only transactions): exact-hash lookup, novel `received` create-or-return, guarded `received -> processing -> processed|failed` transitions, validated extraction/quality storage, automatic + explicit ignored-duplicate marking, independent graph-sync updates, embedding identity storage, sanitized error code/message.
- Implemented versioned normalized identity (`v1:` + SHA-256 over length-delimited NFC/casefold/whitespace-collapsed company/title/location); returns None when any component blank (exact dedup only).
- Compact `JobPostRecord` omits raw content, hashes, embeddings, and error internals. List filters default 10 / max 50; no unbounded list API.
- Temporary-SQLite tests cover state combinations, rollback, corrupt JSON, exact races, normalized duplicates, force_new, insufficient keys, failure retention, bounded reads, and compact-view privacy.

## Files Created or Modified
- backend/app/repositories/job_posts.py (created)
- backend/app/repositories/__init__.py (exports)
- backend/tests/repositories/test_job_posts.py (created)
- backend/tests/db/test_models.py (unchanged; existing schema compatibility covered by suite)
- backend/tests/integration/test_migrations.py (unchanged; existing migration suite remains green)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/repositories/test_job_posts.py tests/db/test_models.py tests/integration/test_migrations.py`
- required: yes
- result: passed
- evidence or reason: 43 passed in ~6.8s (temporary SQLite only; no real providers/network).

- command/check: `cd backend; python -m ruff check app/repositories/job_posts.py tests/repositories/test_job_posts.py tests/db/test_models.py tests/integration/test_migrations.py; python -m mypy app/repositories/job_posts.py`
- required: yes
- result: passed
- evidence or reason: Ruff all checks passed; mypy Success: no issues found in 1 source file.

## Acceptance Check
- condition: Novel record committed as `received` with canonical raw content/hash before provider call; later failure retains content and sanitized failure state
- status: satisfied
- evidence: `test_novel_received_persists_raw_before_processing`, `test_failure_retains_raw_content_and_sanitized_error` (ORM row retains raw_content; compact view omits it).

- condition: Repeating the same hash returns original ID; row/provider/embedding/outbox counts unchanged, including concurrent attempts
- status: satisfied
- evidence: `test_exact_hash_returns_existing_no_second_row`, `test_concurrent_exact_hash_inserts_one_row` (count==1, outbox==0).

- condition: Different hash with same sufficient normalized key can persist as `ignored_duplicate` with `duplicate_of_job_id` and `graph_sync_status=not_required`; insufficient keys use exact dedup only
- status: satisfied
- evidence: `test_normalized_duplicate_marks_ignored_not_required`, `test_insufficient_identity_uses_exact_dedup_only`, `test_force_new_keeps_active_despite_normalized_match`.

- condition: Status transitions reject illegal combinations; repository reads validate JSON; no read/filter path returns raw JD or unbounded corpus
- status: satisfied
- evidence: illegal transition tests; corrupt JSON raises JobPostValidationError; list limit max 50; JobPostRecord slots exclude raw/hash/error/embedding fields.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode — A1 must not update checkboxes or batch status

## Key Implementation Decisions
- Reuse `hash_canonical_text` from jd_source for hash verification; optional caller-supplied hash must match.
- Exact races: pre-select + SQLite INSERT ON CONFLICT DO NOTHING on `raw_content_hash` then re-select (agent_runs pattern).
- Normalized key: `v1:` + SHA-256 of length-delimited normalized components; column remains non-unique so ignored duplicates share the key.
- mark_processed applies automatic ignored-duplicate when an older active processed peer owns the same key unless `force_new=True`.
- Compact reads never surface error_code/error_message (stored on ORM for failure retention); services can load ORM if needed for save_job display.

## Notes for Review Agent
- changed files: `job_posts.py` repository, `__init__.py` exports, `test_job_posts.py`; model/migration test modules unchanged
- validations to rerun: the two required backend command groups in the task Validation section
- risk areas: concurrent normalized-duplicate both-active race is mitigated by SQLite write serialization + post-flush peer lookup; partial unique index was not required and no migration was added
- next task readiness: can_review

---

# Task Execution Report - 03A

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch03 - Shared Normalization and Locked Embeddings

## Task
03A - Extend the shared normalization seam to Job skills

## Status
complete

## Selected Scope
- Batch: Mandatory Batch03 - Shared Normalization and Locked Embeddings
- Task ID: 03A
- Task title: Extend the shared normalization seam to Job skills
- Files allowed / repair scope: `backend/app/services/skill_normalization.py`, optional focused shared files under `backend/app/services/` or `backend/app/schemas/`, `backend/app/data/skills_seed.yaml` only with approved evidence, `backend/tests/services/test_skill_normalization.py`, `backend/tests/services/test_job_skill_normalization.py` (plus package export in `backend/app/services/__init__.py` for public compatibility)

## Source of Truth Used
- docs/plans/Plan_5.md > ### 7.5 Skill normalization
- docs/plans/Master_plan.md > ### 8.4 Graph safety rules
- docs/plans/Master_plan.md > ## 9. Skill Normalization
- docs/plans/Plan_4.md > ## 10. Handoff Notes for Plan 5 (Master Phase 4)

## Supplemental Documents Used
- docs/tasks/task_5.md (03A block)
- docs/plans/Plan_5.md
- docs/plans/Master_plan.md
- docs/plans/Plan_4.md

## Dependency and User Action Check
- Dependencies: (02A) JobSkill contract present in `app/schemas/job_post.py`; Plan 4 normalization/seed (`skill_normalization.py`, empty production `skills_seed.yaml`, synthetic fixture seed) present
- User Action: None for provisional behavior; no approved production alias evidence supplied, so production seed left empty
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_5.md
- docs/plans/Plan_5.md (§7.5)
- docs/plans/Master_plan.md (§8.4, §9)
- docs/plans/Plan_4.md (§10 handoff)
- backend/app/services/skill_normalization.py
- backend/app/schemas/job_post.py (JobSkill)
- backend/app/schemas/candidate.py (SkillRef, CandidateSkill)
- backend/app/data/skills_seed.yaml
- backend/tests/fixtures/skills_seed_test.yaml
- backend/tests/services/test_skill_normalization.py
- backend/app/services/profile_extraction.py (Candidate caller)
- backend/app/services/__init__.py
- Callers via repo search: SkillRef/normalization/seed/graph/test surfaces

## Completed Work
- Refactored shared SkillRef identity resolution (`resolve_skill_ref`, match-key lookup, existing-canonical index) so Candidate and Job share one Unicode/whitespace/case/punctuation ? verified-alias ? existing-canonical ? provisional pipeline.
- Preserved Candidate exclusion / user_correction semantics via `normalize_candidate_skills` (public import and behavior unchanged).
- Added JobSkill adapter `normalize_job_skills` (preserves relationship confidence/evidence; deterministic within-list dedupe by canonical_key) and `normalize_job_skill_lists` (shared catalog/index; preferred drops keys already in required).
- Kept production `skills_seed.yaml` empty; synthetic seed used only in tests.
- Added `tests/services/test_job_skill_normalization.py` covering Job adapter, required/preferred behavior, Candidate?Job parity (seed status/aliases/provisional keys/existing reuse), empty production seed, and no RELATED_TO/weight fields.
- Exported new public symbols from `app.services` for stable consumption.

## Files Created or Modified
- backend/app/services/skill_normalization.py
- backend/app/services/__init__.py
- backend/tests/services/test_job_skill_normalization.py

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py tests/services/test_profile_extraction.py tests/graph/test_candidate_sync.py`
- required: yes
- result: passed
- evidence or reason: 59 passed in 4.22s

- command/check: `cd backend; python -m ruff check app/services/skill_normalization.py app/schemas/candidate.py app/schemas/job_post.py tests/services/test_skill_normalization.py tests/services/test_job_skill_normalization.py; python -m mypy app/services/skill_normalization.py app/schemas/candidate.py app/schemas/job_post.py`
- required: yes
- result: passed
- evidence or reason: ruff All checks passed; mypy Success: no issues found in 3 source files

## Acceptance Check
- condition: Equivalent Candidate and Job surfaces resolve to the same seed canonical key/status/aliases; unknown forms produce the same deterministic provisional key
- status: satisfied
- evidence: `test_candidate_job_parity_seed_canonical_status_aliases`, `test_candidate_job_parity_provisional_keys`

- condition: Existing canonical keys reused without Neo4j authority; required/preferred evidence and Candidate exclusions remain intact
- status: satisfied
- evidence: `test_job_existing_canonical_key_reused_not_verified`, `test_job_preserves_relationship_confidence_and_evidence`, `test_job_skill_lists_dedupe_and_required_wins_over_preferred`, `test_candidate_exclusions_unchanged_by_job_adapter`, Candidate regression suite green

- condition: Existing Candidate normalization/profile tests remain green; no second seed, SQLite Skill table, alias node, or trusted LLM relationship introduced
- status: satisfied
- evidence: Candidate tests in required suite pass; single production seed path empty; JobSkill dump rejects related_to/weight; no new tables

- condition: Production seed changes cite approved evidence; synthetic fixture aliases never enter production data
- status: satisfied
- evidence: `skills_seed.yaml` unchanged (`skills: []`); `test_production_seed_remains_empty` / `test_load_production_seed_is_empty_and_valid`

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode - A1 must not update checkboxes or batch status

## Key Implementation Decisions
- Shared core is `resolve_skill_ref` on SkillRef surfaces inside the existing service module (no extra focused modules needed; avoids duplicate pipelines and keeps public Candidate imports stable).
- Job path deliberately has no exclusion API; Candidate exclusions unchanged.
- Preferred list drops keys already present in required after independent normalization (deterministic REQUIRES-over-PREFERS).
- Production seed left empty because no approved user/evaluation alias evidence was supplied (blocked condition not triggered: empty seed is acceptable).

## Notes for Review Agent
- changed files: skill_normalization.py, services/__init__.py, test_job_skill_normalization.py
- validations to rerun: the two required backend command groups in the task Validation section
- risk areas: later 04A should call `normalize_job_skill_lists` after extraction; ensure relationship vs nested SkillRef confidence are not conflated
- next task readiness: can_review

---

# Task Execution Report - 03B

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch03 - Shared Normalization and Locked Embeddings

## Task
03B - Build versioned Job text and locked ShopAIKey embeddings

## Status
complete

## Selected Scope
- Batch: Mandatory Batch03 - Shared Normalization and Locked Embeddings
- Task ID: 03B
- Task title: Build versioned Job text and locked ShopAIKey embeddings
- Files allowed / repair scope: `backend/app/services/embeddings.py`, `backend/evaluation/benchmark_embeddings.py` only for shared primitive reuse, `backend/tests/services/test_embeddings.py`, `backend/tests/test_embedding_benchmark.py`

## Source of Truth Used
- docs/plans/Plan_5.md > ### 7.6 Embedding and graph synchronization
- docs/plans/Master_plan.md > ### 16.1 Configuration
- docs/plans/Master_plan.md > ### 17.1 Locked embedding contract
- docs/plans/Master_plan.md > ### 17.3 Text representations

## Supplemental Documents Used
- docs/plans/Plan_5.md (### 7.6 Embedding and graph synchronization)
- docs/plans/Master_plan.md (### 16.1 Configuration; ### 17.1 Locked embedding contract; ### 17.3 Text representations)
- docs/tasks/task_5.md (03B block)
- backend/evaluation/benchmark_embeddings.py (Phase 0 primitives)
- backend/app/config.py (typed root embedding settings)
- backend/app/schemas/job_post.py (JobPostExtraction / JobSkill)
- backend/app/services/shopaikey_chat.py (sanitized error / one-retry pattern)

## Dependency and User Action Check
- Dependencies: (02A), (03A), typed root settings, declared `langchain-openai==1.0.3`, accepted Phase 0 embedding evidence
- User Action: None for required fake-backed tests
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_5.md
- docs/plans/Plan_5.md §7.6
- docs/plans/Master_plan.md §§16.1, 17.1, 17.3
- backend/app/config.py
- backend/app/schemas/job_post.py
- backend/app/schemas/candidate.py (SkillRef)
- backend/evaluation/benchmark_embeddings.py
- backend/tests/test_embedding_benchmark.py
- backend/app/services/shopaikey_chat.py
- langchain_openai.OpenAIEmbeddings surface (model/dimensions/base_url/chunk_size/max_retries)

## Completed Work
- Searched Phase 0 benchmark, typed settings, and installed `OpenAIEmbeddings`; extracted shared normalization, batch-16, ordering, finite-vector, allowlist, and sanitize primitives into production module.
- Implemented versioned deterministic Job representation builder (`job_embedding_text_v1`) with fixed source order title ? summary ? responsibilities ? required skills ? preferred skills; collapses whitespace; strips accidental E5 prefixes; excludes salary, company, location, URL, HTML, education, match features.
- Implemented injectable `JobEmbeddingService` using configured ShopAIKey base URL/key, locked model/dimensions/float encoding, `chunk_size`/`max_batch_size` = 16, application-owned one transient retry (`max_retries=0` on client), cancellation hook, and secret-safe repr.
- Validates response count against request size, exact 1536 dimensions, finite floats, model/config identity; fail-closed empty/oversized/mismatched responses with sanitized codes only.
- Refactored Phase 0 `benchmark_embeddings.py` to import shared primitives from `app.services.embeddings` (no duplicated contract logic); evaluation-only config/metrics/runner retained.
- Added scalar/batch fakes covering order, boundaries, invalid dimensions/counts/non-finite, timeout retry budget, cancellation, secret-safe errors/repr, and socket-blocked zero network.

## Files Created or Modified
- backend/app/services/embeddings.py (created)
- backend/evaluation/benchmark_embeddings.py (shared primitive reuse)
- backend/tests/services/test_embeddings.py (created)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_embeddings.py tests/test_embedding_benchmark.py`
- required: yes
- result: passed
- evidence or reason: 50 passed in ~1.7s; fakes only, no ShopAIKey network.

- command/check: `cd backend; python -m ruff check app/services/embeddings.py evaluation/benchmark_embeddings.py tests/services/test_embeddings.py tests/test_embedding_benchmark.py; python -m mypy app/services/embeddings.py`
- required: yes
- result: passed
- evidence or reason: ruff All checks passed; mypy Success: no issues found in 1 source file.

- command/check: optional live `python -m evaluation.benchmark_embeddings`
- required: no
- result: not_run
- evidence or reason: Optional; requires user-owned ignored root `.env`; not required for acceptance.

## Acceptance Check
- condition: Representation contains exactly source-ordered Job fields, is deterministic/versioned, adds no E5 prefix, salary, raw HTML, source URL, or match feature
- status: satisfied
- evidence: `test_job_text_source_order_and_excludes_non_embedding_fields`, `test_job_text_deterministic_and_versioned`, `test_job_text_strips_accidental_e5_prefixes`

- condition: Batches of 1-16 preserve order; every accepted vector has exactly 1536 finite floats; empty/oversized/mismatched responses fail closed
- status: satisfied
- evidence: `test_embed_job_scalar_identity_and_dimensions`, `test_embed_jobs_batch_preserves_order_1_to_16`, `test_batch_size_boundaries`, `test_mismatched_response_count_dimensions_non_finite`

- condition: Model, dimensions, base URL, retry budget, and provider cannot silently change; errors/logs/reprs reveal no API key or input text
- status: satisfied
- evidence: `test_from_settings_locked_construction_kwargs`, `test_one_transient_retry_on_timeout_then_success`, `test_transient_retry_budget_exhausted`, `test_errors_and_repr_hide_secrets_and_input_text`, `test_disallowed_model_cannot_be_constructed`

- condition: Normal tests use fakes only; Phase 0 benchmark behavior remains compatible through shared primitives
- status: satisfied
- evidence: Full `tests/test_embedding_benchmark.py` green; benchmark imports production normalize/validate/allowlist/sanitize; `test_zero_network_for_required_path` with socket block

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode - A1 must not update checkboxes or batch status

## Key Implementation Decisions
- Shared contract primitives live in production `app/services/embeddings.py`; Phase 0 benchmark reuses them to avoid divergent business logic.
- Default client is `langchain_openai.OpenAIEmbeddings` with `max_retries=0` and `check_embedding_ctx_length=False`; application owns single timeout/rate-limit retry.
- Skill names in Job text use `SkillRef.display_name` only (not confidence/evidence/canonical_key).
- `JobEmbeddingResult` carries vectors plus model/dimensions/representation_version/encoding identity for later SQLite/graph consumers.

## Notes for Review Agent
- changed files: embeddings.py, benchmark_embeddings.py, test_embeddings.py
- validations to rerun: the two required backend command groups in the task Validation section
- risk areas: later graph/outbox stages should consume `JobEmbeddingService.embed_job(s)` and store model/dimension identity; do not reintroduce E5 prefixes or alternate dimensions
- next task readiness: can_review

---

# Task Execution Report - 04A

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch04 - Agent-Facing Job Workflow

## Task
04A - Orchestrate persistence-first JD ingestion and duplicate policy

## Status
complete

## Selected Scope
- Batch: Mandatory Batch04 - Agent-Facing Job Workflow
- Task ID: 04A
- Task title: Orchestrate persistence-first JD ingestion and duplicate policy
- Files allowed / repair scope: `backend/app/services/jd_ingestion.py`, `backend/app/schemas/job_tools.py`, `backend/app/repositories/job_posts.py`, `backend/tests/services/test_jd_ingestion.py`, `backend/tests/repositories/test_graph_outbox.py`

## Source of Truth Used
- docs/plans/Plan_5.md > ### 7.3 Persistence-first state machine
- docs/plans/Plan_5.md > ### 7.4 Duplicate policy
- docs/plans/Plan_5.md > ### 7.6 Embedding and graph synchronization
- docs/plans/Master_plan.md > ### 13.5 save_job
- docs/plans/Master_plan.md > ### 21.1 Outbox rule

## Supplemental Documents Used
- docs/plans/Plan_5.md (### 7.3; ### 7.4; ### 7.6)
- docs/plans/Master_plan.md (### 13.5 save_job; ### 21.1 Outbox rule)
- docs/tasks/task_5.md (04A block)

## Dependency and User Action Check
- Dependencies: (01B) jd_source, (02A) schemas/quality, (02B) JobPostRepository, (03A) normalize_job_skill_lists, (03B) embedding identity constants, generic GraphOutboxRepository â€” all present
- User Action: None during tests
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md (project context via task notes / prior Plan 5 evidence)
- docs/tasks/task_5.md (04A)
- docs/plans/Plan_5.md (Â§7.3, Â§7.4, Â§7.6)
- docs/plans/Master_plan.md (Â§11.3â€“11.4, Â§13.5, Â§21.1)
- backend/app/services/jd_source.py
- backend/app/services/jd_extraction.py
- backend/app/services/jd_quality.py
- backend/app/services/skill_normalization.py
- backend/app/services/embeddings.py (identity constants only)
- backend/app/repositories/job_posts.py
- backend/app/repositories/graph_outbox.py
- backend/app/repositories/profiles.py (same-transaction outbox pattern)
- backend/app/db/enums.py
- backend/app/db/models/jobs.py
- backend/app/schemas/job_post.py
- backend/tests/repositories/test_job_posts.py
- backend/tests/repositories/test_graph_outbox.py
- backend/tests/services/test_jd_extraction.py

## Completed Work
- Searched Job/outbox/tool/transaction/idempotency callers; reused one service boundary (`JDIngestionService`) with injected acquire/extract collaborators; kept tool/HTTP logic out of the service.
- Implemented exact order: acquire/canonicalize/hash â†’ exact-hash return existing â†’ commit novel `received` â†’ mark `processing` â†’ extract/normalize/re-classify quality â†’ atomic `processed` plus either ignored/`not_required` or active embedding identity + identifier-only `upsert_job` enqueue via generic `GraphOutboxRepository` (Candidate semantics unchanged; no second outbox).
- Extraction/provider failures retain the raw row as `failed` with domain-stable sanitized codes (`JD_PROVIDER_TIMEOUT`, `JD_PROVIDER_RATE_LIMIT`, `JD_SCHEMA_INVALID`, â€¦); exact duplicates cause zero new Job/extract/embedding/outbox work even when `force_new_authorized=True`.
- Normalized different-content duplicates default to `ignored_duplicate`/`not_required`; application-authorized `force_new_authorized` creates a separate active scorable record without mutating the earlier canonical row.
- Only active `full|partial` records store locked embedding model/dimension identity and enqueue/requeue one `{"job_id": ...}` outbox row; unscorable/ignored never do.
- Added strict `SaveJobResult` / `JobDisplaySummary` in `job_tools.py` and injected call-order/failure/duplicate/eligibility/idempotency tests.
- `job_posts.py` and `test_graph_outbox.py` required no code changes; existing repository primitives and outbox suite remain the shared foundation.

## Files Created or Modified
- backend/app/services/jd_ingestion.py (created)
- backend/app/schemas/job_tools.py (created)
- backend/tests/services/test_jd_ingestion.py (created)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_jd_ingestion.py tests/repositories/test_job_posts.py tests/repositories/test_graph_outbox.py`
- required: yes
- result: passed
- evidence or reason: 60 passed in ~11.3s; injected fakes only (no network/provider/Neo4j).

- command/check: `cd backend; python -m ruff check app/services/jd_ingestion.py app/repositories/job_posts.py tests/services/test_jd_ingestion.py; python -m mypy app/services/jd_ingestion.py app/repositories/job_posts.py`
- required: yes
- result: passed
- evidence or reason: ruff All checks passed; mypy Success: no issues found in 2 source files.

## Acceptance Check
- condition: Novel raw content commits before the first LLM call and remains after timeout/rate-limit/invalid-schema failure
- status: satisfied
- evidence: `test_novel_raw_commits_before_extract_and_enqueues_outbox` asserts ORM row + raw content before extract; `test_provider_failure_retains_raw_after_received_commit` retains raw + JD_* codes, zero outbox.

- condition: Exact duplicates cause zero new Job, extraction, embedding, or outbox work even when override is requested
- status: satisfied
- evidence: `test_exact_duplicate_skips_extract_embedding_outbox_even_with_force_new`, `test_repeated_exact_save_is_idempotent`.

- condition: Different-content normalized duplicates persist ignored/not_required by default; authorized override creates active separate record without changing earlier row
- status: satisfied
- evidence: `test_normalized_duplicate_ignored_by_default`, `test_authorized_force_new_creates_active_separate_record`.

- condition: Only active full/partial records record locked embedding identity and enqueue one identifier-only Job operation; unscorable/ignored never do
- status: satisfied
- evidence: novel full/partial path stores model/dims + upsert_job payload `{"job_id": ...}`; unscorable and ignored tests assert no outbox and null embedding identity.

- condition: Every failure/result is sanitized; no raw content, secret, unsafe URL details, or provider payload in outbox/summaries
- status: satisfied
- evidence: `_assert_result_sanitized`, outbox payload identity-only, SaveJobResult extra=forbid rejects raw_content.

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode â€” A1 must not update checkboxes or batch status

## Key Implementation Decisions
- Same-transaction Job outbox reuses generic `GraphOutboxRepository.enqueue` with `JOB_UPSERT_OPERATION="upsert_job"` and identifier-only payload (Candidate `sync_candidate` semantics untouched; no second outbox).
- `force_new_authorized` is a service-level Boolean only; never overrides exact hash; FORCE_NEW outcome reported only when an older active peer shares the normalized key.
- Embedding vectors are not generated in 04A; only locked model/dimension identity is stored for later graph processing.
- Quality is re-applied after skill normalization to match master extract â†’ normalize â†’ classify order.

## Notes for Review Agent
- changed files: `jd_ingestion.py`, `job_tools.py`, `test_jd_ingestion.py` (job_posts/graph_outbox test modules unchanged)
- validations to rerun: the two required backend command groups in the task Validation section
- risk areas: 04B must derive `force_new_authorized` from current-turn state outside the JD payload; do not pass tool Boolean alone
- next task readiness: can_review

---

# Task Execution Report - 04B

## Source Task File
docs/tasks/task_5.md

## Report File
docs/reports/report_5_execute_agent.md

## Mode
orchestrated

## Batch
Mandatory Batch04 - Agent-Facing Job Workflow

## Task
04B - Expose bounded Job tools with application-owned override authorization

## Status
complete

## Selected Scope
- Batch: Mandatory Batch04 - Agent-Facing Job Workflow
- Task ID: 04B
- Task title: Expose bounded Job tools with application-owned override authorization
- Files allowed / repair scope: `backend/app/tools/save_job.py`, `backend/app/tools/query_jobs.py`, `backend/app/tools/registry.py`, `backend/app/main.py`, `backend/app/services/chat_service.py` (allowlisted audit token only), `backend/tests/tools/test_save_job.py`, `backend/tests/tools/test_query_jobs.py`, `backend/tests/tools/test_registry.py`

## Source of Truth Used
- docs/plans/Plan_5.md > ### 7.7 Tool outputs
- docs/plans/Plan_5.md > ## 5. Out of Scope
- docs/plans/Master_plan.md > ### 13.5 save_job
- docs/plans/Master_plan.md > ### 13.6 query_jobs
- docs/plans/Master_plan.md > ### 13.8 Tool authorization matrix

## Supplemental Documents Used
- docs/plans/Plan_5.md (### 7.7; ## 5 Out of Scope)
- docs/plans/Master_plan.md (### 13.5; ### 13.6; ### 13.8)
- docs/tasks/task_5.md (04B block)
- README.md (seven public routes; Plan 5 context)

## Dependency and User Action Check
- Dependencies: (04A) JDIngestionService/SaveJobResult present; InjectedState pattern (profile_commit); Agent registry/startup; durable tool-observability seam in chat_service â€” all present
- User Action: None
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_5.md (04B)
- docs/plans/Plan_5.md (Â§5, Â§7.7)
- docs/plans/Master_plan.md (Â§13.5â€“13.8)
- backend/app/tools/registry.py, candidate_context.py, profile_commit.py, profile_draft.py
- backend/app/services/jd_ingestion.py, chat_service.py
- backend/app/schemas/job_tools.py
- backend/app/repositories/job_posts.py (list_filtered/get_by_id compact views)
- backend/app/agent/state.py, graph.py (messages_for_this_turn / HumanMessage)
- backend/app/main.py
- backend/app/api/chat.py (public tool outcome mapping; seven routes unchanged)
- backend/tests/tools/test_registry.py, test_profile_commit.py
- backend/tests/services/test_jd_ingestion.py

## Completed Work
- Searched production tool factories, registry/startup, Agent state keys, tool-result parsing, and route exposure; kept wrappers thin and preserved exact Agent state keys (`messages_for_this_turn` only for force_new auth).
- Implemented `save_job` with strict `SaveJobInput` (exactly one of url/raw_text + optional force_new). `force_new` authorization is derived from current-turn user text in InjectedState after excluding the exact URL/raw-JD payload; requires explicit "separate position" or "distinct position"; document/tool-arg-only claims rejected; unauthorized overrides return FORCE_NEW_UNAUTHORIZED with zero service mutation.
- Authorized overrides attach one allowlisted `authorization_audit=force_new_authorized` token on the tool result; chat_service records that exact token in durable `arguments_summary` (never user turn/JD).
- Implemented `query_jobs` ID mode or filter mode over JobPostRepository compact views; default limit 10, max 50; returns existing score_cache when present; never computes scores; excludes raw/hash/error/embedding/provider fields.
- Expanded production registry to exactly six tools; wired JDIngestionService + tools in main.py; `match_jobs` remains reserved only (no implementation).
- Added focused tool/registry tests; existing Agent graph/prompt and chat API tests remain green.

## Files Created or Modified
- backend/app/tools/save_job.py (created)
- backend/app/tools/query_jobs.py (created)
- backend/app/tools/registry.py (PRODUCTION_TOOL_NAMES; six-tool create_production_registry)
- backend/app/tools/__init__.py (export PRODUCTION_TOOL_NAMES)
- backend/app/main.py (wire save_job + query_jobs)
- backend/app/services/chat_service.py (force_new_authorized durable audit token)
- backend/tests/tools/test_save_job.py (created)
- backend/tests/tools/test_query_jobs.py (created)
- backend/tests/tools/test_registry.py (updated for six production tools)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/tools/test_save_job.py tests/tools/test_query_jobs.py tests/tools/test_registry.py tests/agent/test_graph.py tests/agent/test_prompt.py tests/api/test_chat.py`
- required: yes
- result: passed
- evidence or reason: 60 passed in ~7.9s

- command/check: `cd backend; python -m ruff check app/tools app/tools/registry.py app/main.py tests/tools tests/agent/test_graph.py tests/agent/test_prompt.py`
- required: yes
- result: passed
- evidence or reason: All checks passed

- command/check: `cd backend; python -m mypy app/tools app/main.py`
- required: yes
- result: passed
- evidence or reason: Success: no issues found in 8 source files. Note: the task-listed co-invocation `mypy app/tools app/tools/registry.py app/main.py` collides on module path mapping (duplicate `app.tools.registry`); the same modules are covered by `mypy app/tools app/main.py`.

- command/check: inventory of `@(router|app).(get|post|put|patch|delete)` under backend/app/api
- required: yes
- result: passed
- evidence or reason: exactly 7 authorized application routes (health, attachments/cv, profile, profile/cv, chat/history, chat/turns, chat/runs/{run_id}/resume)

## Acceptance Check
- condition: save_job rejects neither/both input modes and unauthorized force_new with zero mutation; explicit current-turn declaration outside JD creates exactly one allowlisted audit token
- status: satisfied
- evidence: test_save_job_input_rejects_neither_and_both; test_unauthorized_force_new_zero_mutation; test_authorized_force_new_calls_service_and_emits_audit_token; declaration exclusion tests

- condition: query_jobs supports one ID or bounded filters, defaults to 10, caps at 50, excludes raw content/hash/error/vector/provider/internal fields
- status: satisfied
- evidence: test_query_by_id_returns_compact_view; test_filter_mode_default_limit_and_cap; privacy assertions on raw/hash/error/embedding

- condition: Production registry names are exactly the six listed tools; no match_jobs implementation
- status: satisfied
- evidence: test_production_registry_contains_exactly_six_tools; test_no_match_jobs_implementation_in_tools; match_jobs remains in LATER_PHASE only

- condition: Tools call services directly, use existing graph/transport, preserve Candidate behavior, no public route or match_jobs
- status: satisfied
- evidence: main.py wires services into tools; no new API routes; route inventory still 7; Candidate tools still registered; agent/chat tests green

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode â€” A1 must not update checkboxes or batch status

## Key Implementation Decisions
- force_new authorization scans only `messages_for_this_turn` Human/user text after removing the exact tool payload (url/raw_text); LLM Boolean alone never authorizes.
- Durable audit token is exactly `force_new_authorized`, written by save_job as `"authorization_audit":"force_new_authorized"` and mapped by chat_service into tool_executions.arguments_summary.
- PRODUCTION_TOOL_NAMES (six) is the production set; CURRENT_PROFILE_TOOL_NAMES remains the four-tool Candidate subset; match_jobs stays reserved-only.

## Notes for Review Agent
- changed files: save_job.py, query_jobs.py, registry.py, tools/__init__.py, main.py, chat_service.py, test_save_job.py, test_query_jobs.py, test_registry.py
- validations to rerun: required pytest list + ruff + mypy on app/tools and app/main.py + seven-route inventory
- risk areas: broader integration suites that still construct create_production_registry with only four Candidate stubs will fail until they pass all six production tools; PRODUCTION_FORBIDDEN_RE in profile_workflow still bans `save_job(` call-site text (out of 04B file list)
- next task readiness: can_review
