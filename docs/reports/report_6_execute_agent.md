---

# Task Execution Report - 01A

## Source Task File
docs/tasks/task_6.md

## Report File
docs/reports/report_6_execute_agent.md

## Mode
same_task_repair

## Batch
Batch01 - Safe Matching Inputs and Canonical Retrieval

## Task
01A - Build a versioned redacted Candidate embedding representation

## Status
complete

## Selected Scope
- Batch: Batch01 - Safe Matching Inputs and Canonical Retrieval
- Task ID: 01A
- Task title: Build a versioned redacted Candidate embedding representation
- Files allowed / repair scope: A2 same-task repair only — add focused over-limit `CandidateEmbeddingFields` test in `backend/tests/services/test_matching_text.py`

## Source of Truth Used
- docs/plans/Plan_6.md > ### 7.1 Retrieval representations
- docs/plans/Plan_6.md > ## 5. Out of Scope
- docs/plans/Master_plan.md > ### 17.1 Locked embedding contract
- docs/plans/Master_plan.md > ### 17.3 Text representations

## Supplemental Documents Used
- docs/plans/Plan_6.md
- docs/plans/Master_plan.md
- README.md
- docs/tasks/task_6.md (01A block)

## Dependency and User Action Check
- Dependencies: Accepted ProfileRepository, PreferencesRepository, redact_pii, and JobEmbeddingService (present; reused)
- User Action: None required
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_6.md
- docs/plans/Plan_6.md (§5, §7.1)
- docs/plans/Master_plan.md (§17.1, §17.3)
- backend/app/services/embeddings.py
- backend/app/services/matching_text.py
- backend/app/schemas/matching.py
- backend/app/services/pii_redaction.py
- backend/app/schemas/candidate.py
- backend/app/schemas/preferences.py
- backend/tests/services/test_matching_text.py
- backend/tests/services/test_embeddings.py
- backend/tests/services/test_pii_redaction.py
- Callers of JobEmbeddingService / embed_texts / build_job_embedding_text / redact_pii

## Completed Work
- Searched embedding, redaction, and profile surfaces; reused `normalize_embedding_text`, vector validation, `JobEmbeddingService.embed_texts`, and `redact_pii` without adding a second provider/model/dimension stack.
- Added `app/schemas/matching.py` with `candidate_embedding_text_v1`, `CandidateEmbeddingFields`, `CandidateEmbeddingResult`, and code-only `CandidateEmbeddingError` / codes.
- Added focused `app/services/matching_text.py`: projects profile/preferences into embedding-only fields; stable order (target roles, summary, verified non-excluded skills, experience titles, preference tokens); filters provisional/excluded skills; bounds assembled text; redacts before any provider call; maps provider failures to sanitized codes.
- Extended `JobEmbeddingService.embed_texts` with optional `representation_version` so Candidate identity labels correctly while Job default remains `job_embedding_text_v1`.
- Added `tests/services/test_matching_text.py` and one Job-adapter identity override test proving determinism, skill filtering, contact absence, zero provider calls on redaction failure, locked model/dimensions/no-prefix, and unchanged Job text.
- Same-task repair: added focused over-limit `CandidateEmbeddingFields` test asserting `build_candidate_embedding_text` raises `CandidateEmbeddingError` with `INVALID_INPUT` and that no source text appears in the exception.

## Files Created or Modified
- backend/app/schemas/matching.py (created; prior implementation)
- backend/app/services/matching_text.py (created; prior implementation)
- backend/app/services/embeddings.py (optional representation_version on embed_texts; prior)
- backend/tests/services/test_matching_text.py (created; repair: over-limit INVALID_INPUT + no source-text leak test)
- backend/tests/services/test_embeddings.py (representation_version override test; prior)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_matching_text.py tests/services/test_embeddings.py tests/services/test_pii_redaction.py`
- required: yes
- result: passed
- evidence or reason: 42 passed in 1.50s; recording fakes only (no network); includes `test_candidate_fields_over_limit_raises_invalid_input_without_source`.

- command/check: `cd backend; python -m ruff check app/schemas/matching.py app/services/matching_text.py app/services/embeddings.py tests/services/test_matching_text.py tests/services/test_embeddings.py; python -m mypy app/schemas/matching.py app/services/matching_text.py app/services/embeddings.py`
- required: yes
- result: passed
- evidence or reason: ruff All checks passed; mypy Success: no issues found in 3 source files.

## Acceptance Check
- condition: Equal approved profile/preferences produce byte-identical normalized Candidate text and exactly one validated 1536-float vector through the existing adapter
- status: satisfied
- evidence: `test_candidate_text_byte_identical_for_equal_inputs`, `test_equal_inputs_one_validated_vector`

- condition: Only verified, non-excluded Candidate skills enter text; no raw CV, contact PII, attachment path, provider payload, alternate model, or E5 prefix enters text/logs/errors
- status: satisfied
- evidence: `test_candidate_text_source_order_and_exclusions`, `test_redaction_removes_contact_before_provider`, `test_errors_hide_secrets_and_source`, `test_provider_error_is_code_only`, `test_candidate_fields_over_limit_raises_invalid_input_without_source`

- condition: Redaction failure makes zero fake-provider calls and returns no source text
- status: satisfied
- evidence: `test_redaction_failure_zero_provider_calls_and_no_source_text` (factory.calls and client.calls empty; code-only error)

- condition: Existing Job embedding text and Job sync/rebuild tests remain green
- status: satisfied
- evidence: `test_job_embedding_text_unchanged_by_candidate_builder` plus full `test_embeddings.py` suite green (Job adapter tests still pass)

- condition (A2 repair): Over-limit `CandidateEmbeddingFields` raises `INVALID_INPUT` with no source text in the exception
- status: satisfied
- evidence: `test_candidate_fields_over_limit_raises_invalid_input_without_source`

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: same_task_repair / orchestrated mode forbids checkbox and batch status updates

## Notes for Review Agent
- changed files (this repair): backend/tests/services/test_matching_text.py only
- validations to rerun: the two required pytest/ruff/mypy commands above
- risk areas: preference token ordering (locations then work_mode values then seniority values); current_title intentionally excluded from representation; optional embed_texts representation_version must default to Job version for existing callers; over-limit bound is fail-closed (no silent truncate)
- next task readiness: ready for A2 re-review of 01A repair

## Repair Log

### 2026-07-12
- reason for repair: A2 REJECTED_WITH_WARNINGS — missing focused over-limit `CandidateEmbeddingFields` test asserting `INVALID_INPUT` and no source text in the exception
- changes made: Added `test_candidate_fields_over_limit_raises_invalid_input_without_source` in `backend/tests/services/test_matching_text.py` (imports `MAX_CANDIDATE_EMBEDDING_TEXT_LEN`; oversize summary; asserts code-only error)
- validations rerun: required pytest (42 passed), ruff, mypy — all passed
- outcome: complete; repair item resolved


---

# Task Execution Report - 01B

## Source Task File
docs/tasks/task_6.md

## Report File
docs/reports/report_6_execute_agent.md

## Mode
orchestrated

## Batch
Batch01 - Safe Matching Inputs and Canonical Retrieval

## Task
01B - Retrieve top-50 graph candidates and rejoin canonical SQLite Jobs

## Status
complete

## Selected Scope
- Batch: Batch01 - Safe Matching Inputs and Canonical Retrieval
- Task ID: 01B
- Task title: Retrieve top-50 graph candidates and rejoin canonical SQLite Jobs
- Files allowed / repair scope: backend/app/services/retrieval.py, backend/app/repositories/job_posts.py, backend/tests/services/test_retrieval.py, backend/tests/repositories/test_job_posts.py

## Source of Truth Used
- docs/plans/Plan_6.md > ### 7.1 Retrieval representations
- docs/plans/Plan_6.md > ## 9. Verification & Testing Plan
- docs/plans/Master_plan.md > ### 17.4 Retrieval flow
- docs/plans/Master_plan.md > ### 21.2 Processing

## Supplemental Documents Used
- docs/plans/Plan_6.md
- docs/plans/Master_plan.md
- README.md
- docs/tasks/task_6.md (01B block)

## Dependency and User Action Check
- Dependencies: (01A) Candidate vector; accepted Job outbox/projector/vector index and JobPostRepository (present; reused process_job_sync_outbox, is_graph_eligible, fetch_records, VECTOR_INDEX_NAME)
- User Action: None required
- Dependencies satisfied: yes

## Files Inspected Before Editing
- README.md
- docs/tasks/task_6.md
- docs/plans/Plan_6.md (�7.1, �9)
- docs/plans/Master_plan.md (�17.4, �21.2)
- backend/app/graph/client.py (fetch_records)
- backend/app/graph/job_sync.py (is_graph_eligible, process_job_sync_outbox)
- backend/app/graph/schema.py (VECTOR_INDEX_NAME, cosine index)
- backend/app/graph/errors.py
- backend/app/repositories/job_posts.py
- backend/app/schemas/matching.py
- backend/app/services/jd_ingestion.py (_is_graph_eligible caller)
- backend/tests/graph/test_job_sync.py
- backend/tests/graph/fakes.py
- backend/tests/repositories/test_job_posts.py

## Completed Work
- Searched graph-client, eligibility, outbox, repository, rebuild, and query callers; reused `fetch_records`, `process_job_sync_outbox`, `is_graph_eligible`, and locked `VECTOR_INDEX_NAME` without duplicating SQLite/graph rules.
- Added `JobPostRepository.get_by_ids`: bounded bulk PK load (max 50 unique IDs), rejects empty/over-limit/invalid IDs, omits missing rows, collapses request duplicates, never returns raw content.
- Implemented `app/services/retrieval.py`:
  - one bounded outbox retry via existing processor before retrieval
  - parameterized top-50 `db.index.vector.queryNodes` path with fixed index identity `job_embedding_vector`
  - optional saved-Job-ID filter (1�50 unique; rejects empty/duplicate/>50) via bounded exact cosine over those IDs
  - finite similarity clamp to [0,1]; drop malformed/non-finite/duplicate graph rows; hard cap 50 unique IDs
  - SQLite rejoin preserving Neo4j rank; keep only active processed non-ignored full|partial rows with extraction; SQLite title/skills/status only
  - sanitized `RetrievalError` codes on Neo4j/input failure with zero claimed matches
- Added injected fake graph/SQLite tests covering outbox success, Neo4j failure, malformed/duplicate/stale IDs, over-limit results, filter bounds, ignored/unscorable exclusion, canonical-field precedence, rank preservation, and empty successful graph answer.

## Files Created or Modified
- backend/app/services/retrieval.py (created)
- backend/app/repositories/job_posts.py (get_by_ids bulk path)
- backend/tests/services/test_retrieval.py (created)
- backend/tests/repositories/test_job_posts.py (get_by_ids tests)

## Tests or Validations Run
- command/check: `cd backend; python -m pytest -q tests/services/test_retrieval.py tests/repositories/test_job_posts.py tests/graph/test_job_sync.py`
- required: yes
- result: passed
- evidence or reason: 45 passed in 5.08s; injected fakes only (no live Neo4j/ShopAIKey).

- command/check: `cd backend; python -m ruff check app/services/retrieval.py app/repositories/job_posts.py tests/services/test_retrieval.py tests/repositories/test_job_posts.py; python -m mypy app/services/retrieval.py app/repositories/job_posts.py`
- required: yes
- result: passed
- evidence or reason: ruff All checks passed; mypy Success: no issues found in 2 source files.

## Acceptance Check
- condition: Graph query is parameterized, returns at most 50 unique IDs, and never exposes vectors, secrets, raw content, or unbounded graph records
- status: satisfied
- evidence: `test_vector_query_parameterized_and_capped`, `test_vector_query_dedupes_malformed_and_clamps`, `test_error_repr_hides_secrets_and_content`

- condition: Current SQLite row must be active, processed, non-ignored, and full|partial to survive; SQLite title/skills/status always override graph copies
- status: satisfied
- evidence: `test_retrieve_excludes_ignored_unscorable_stale` (GRAPH TITLE MUST NOT WIN); reuses `is_graph_eligible`

- condition: Pending work receives one bounded existing-processor attempt; Neo4j failure produces sanitized failure with zero claimed matches
- status: satisfied
- evidence: `test_outbox_retry_success_then_retrieve`, `test_neo4j_failure_zero_claimed_matches`

- condition: Candidate ordering is deterministic and explicit saved-ID filters reject empty/duplicate-overflow or more than 50 IDs
- status: satisfied
- evidence: `test_join_preserves_neo4j_rank_order`, `test_saved_id_filter_bounds`, `test_retrieve_with_saved_id_filter`

## Progress Update
- task checkbox updated: no
- batch status updated: no
- reason: orchestrated mode forbids checkbox and batch status updates

## Notes for Review Agent
- changed files: backend/app/services/retrieval.py, backend/app/repositories/job_posts.py, backend/tests/services/test_retrieval.py, backend/tests/repositories/test_job_posts.py
- validations to rerun: the two required pytest/ruff/mypy commands above
- risk areas: filtered saved-ID path uses exact `vector.similarity.cosine` over at most 50 IDs rather than ANN-then-filter so all explicit IDs remain eligible; unfiltered path uses locked `job_embedding_vector` index; `graph_evidence` is intentionally empty for 02A; outbox item-level Neo4j failures are absorbed by the existing processor while vector-query failures fail closed
- next task readiness: ready for A2 review of 01B
