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
