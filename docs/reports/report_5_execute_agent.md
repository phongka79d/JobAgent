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
