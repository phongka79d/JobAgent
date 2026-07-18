# Full Functional Failure Report

Failure-only results from the fresh desktop functional QA run against the current
repository HEAD. The run used synthetic CV fixtures and synthetic/public test JD
inputs in the isolated Compose project
`jobagent-functional-qa-20260718-1135`.

Security testing and mobile/responsive testing are out of scope. This report does
not list passing test cases and does not include raw CV/JD bodies, provider
transcripts, credentials, SQL, or Cypher.

## F-01 — Desktop CV and Job deletion are blocked by CORS preflight

- **Test IDs:** `CVM-009`, `SJD-013`
- **Functional severity:** High — both user-visible permanent-delete functions are
  unusable from the frontend.
- **Affected features:** CV Manager non-active CV deletion; saved-JD deletion.
- **Observable symptom:**
  - Confirming **Delete CV** leaves the archived CV row intact and displays
    `Action failed — Failed to fetch (REQUEST_FAILED)`.
  - Confirming **Xoá JD** leaves the Job/detail intact and displays the same error.
- **Expected behavior:** After the accessible confirmation, the frontend DELETE
  request should reach the backend; successful deletion should remove the selected
  row and select a safe remaining row or empty state.
- **Reproduction:**
  1. Run frontend at `http://localhost:5173` and backend at
     `http://localhost:8000`.
  2. In CV Manager, select an archived CV, choose **Delete**, then confirm
     **Delete CV**.
  3. In **JD đã lưu**, select a Job, choose **Xoá JD**, then confirm.
  4. Equivalent sanitized preflight probe:

     ```powershell
     $headers = @{
       Origin = 'http://localhost:5173'
       'Access-Control-Request-Method' = 'DELETE'
     }
     Invoke-WebRequest -Method Options -Headers $headers `
       http://localhost:8000/api/jobs/<job-id>
     Invoke-WebRequest -Method Options -Headers $headers `
       http://localhost:8000/api/cvs/<attachment-id>
     ```

- **Frontend/network evidence:** Both preflights return HTTP `400` with
  `Access-Control-Allow-Methods: GET, POST`; the browser therefore never submits
  DELETE. The handled fetch rejection does not emit a browser-console error.
- **Backend log excerpt:**

  ```text
  OPTIONS /api/jobs/<job-id> HTTP/1.1 400 Bad Request
  OPTIONS /api/cvs/<attachment-id> HTTP/1.1 400 Bad Request
  ```

  Direct same-origin/backend calls returned `204` for the same synthetic archived
  CV and Job, confirming that the deletion coordinators work and the failure is at
  the browser-to-API boundary.
- **Root-cause evidence:** `backend/app/main.py:109` configures
  `allow_methods=["GET", "POST"]`, while the public frontend implements DELETE
  routes for both resources.

## F-02 — Saved-JD evaluation currentness stays falsely current after CV activation

- **Test IDs:** `SJD-006`, `SJD-009`
- **Functional severity:** Medium — the panel presents an obsolete score as current
  until the user manually refreshes it.
- **Affected feature:** Revision-keyed saved-JD current/stale display after approved
  CV/profile replacement.
- **Observable symptom:** With the **JD đã lưu** panel already showing a `current`
  evaluation, approving a different CV leaves the same row/detail labeled
  `current`. Clicking **Refresh JD đã lưu** immediately changes it to `stale`, shows
  **Cần đánh giá lại**, and exposes **Đánh giá lại**.
- **Expected behavior:** Successful profile/CV activation must invalidate the
  evaluation-currentness cache so the visible row/detail becomes stale without
  requiring manual refresh and without automatically re-evaluating.
- **Reproduction:**
  1. Save and evaluate a scorable synthetic Job with CV A; open its saved-JD detail
     and verify `current`.
  2. Upload CV B, approve its draft with **Save Profile**, and keep the saved-JD
     panel open.
  3. Observe that the panel still displays `current`.
  4. Click **Refresh JD đã lưu**; observe `stale` / **Cần đánh giá lại**.
- **Frontend/network evidence:** No relevant console error. Before manual refresh,
  no saved-JD reload is initiated; the later `GET /api/jobs` and detail refresh
  return the correct stale state.
- **Backend log excerpt:**

  ```text
  POST /api/chat/runs/<run-id>/resume HTTP/1.1 200 OK
  GET /api/jobs HTTP/1.1 200 OK
  GET /api/jobs/<job-id> HTTP/1.1 200 OK
  ```

  The API-derived state was `stale`; no evaluation was created automatically.
- **Root-cause evidence:** `frontend/src/app/App.tsx:116`–`119` increments only the
  profile and activation keys after Save Profile. The saved-JD invalidation key is
  separate (`App.tsx:126`–`128`) and is not incremented. In addition,
  `frontend/src/features/profile/CvSidebar.tsx:176` explicitly invalidates only
  CV/chunk/run/graph caches.

## F-03 — CV Manager becomes blank after activation while its tab is open

- **Test IDs:** `FE-008`, `CVM-001`, `CVM-005`
- **Functional severity:** Medium — the primary CV lifecycle panel loses all rows
  and state after a successful Make active flow until a manual refresh.
- **Affected feature:** CV Manager archived **Make active** / Save Profile completion.
- **Observable symptom:** Starting **Make active** from an archived CV, approving the
  resulting draft, and remaining on CV Manager leaves only the panel heading and
  refresh button. There is no row list, loading state, empty state, or error state.
  The blank state persisted beyond completion; **Refresh CV Manager** restored the
  correct active/archived rows.
- **Expected behavior:** After activation, CV Manager should automatically reload
  and show the new sole active row plus retained archived rows, with a truthful
  loading state while the request is in progress.
- **Reproduction:**
  1. Keep CV Manager selected with one active and one archived synthetic CV.
  2. Select the archived row and choose **Make active**.
  3. Approve the draft with **Save Profile**.
  4. Observe the header-only blank panel.
  5. Click **Refresh CV Manager**; the expected swapped rows appear.
- **Frontend/network evidence:** No relevant console error. No automatic CV-history
  request follows cache invalidation while the tab ID remains unchanged; the manual
  refresh issues `GET /api/observability/cvs` and restores content.
- **Backend log excerpt:**

  ```text
  POST /api/chat/runs/<run-id>/resume HTTP/1.1 200 OK
  GET /api/observability/cvs HTTP/1.1 200 OK   # manual refresh
  ```

- **Root-cause evidence:**
  - `frontend/src/features/observability/state.ts:442`–`452` replaces CV history
    with an empty resource on activation.
  - The loading effect in
    `frontend/src/features/observability/ObservabilitySidebar.tsx:62`–`81` is
    triggered only by selected tab/attachment changes. Activation leaves those
    values unchanged, so clearing the cache does not trigger a reload.

## F-04 — Agent claims a duplicate URL Job was created without calling a tool

- **Test IDs:** `CHAT-005`, `JD-003`
- **Functional severity:** High — the assistant reports a successful data mutation
  that did not occur.
- **Affected feature:** Conversation-driven `save_job` invocation and exact URL Job
  deduplication.
- **Observable symptom:** For the explicit request “Use `save_job` once again with
  the exact URL and report whether the existing Job is reused,” the assistant
  replied that a new entry was created. The turn displayed no tool activity, the
  durable run had zero tool executions, and total Job count did not change.
- **Expected behavior:** A save request must invoke the registered `save_job` tool
  and derive its response from the durable ToolResult. For an exact duplicate URL,
  the existing Job should be returned and no new identity created.
- **Reproduction:**
  1. Save `https://example.com` once through chat; it creates one truthful
     processed/unscorable synthetic Job.
  2. Send: `Use save_job once again with the exact URL https://example.com and
     report whether the existing Job is reused. Do not call other tools.`
  3. Observe an assistant-only success claim with no tool row/card.
  4. Inspect the latest durable run and saved Job count.
- **Frontend/network evidence:** The message row contains no **Save Job** activity.
  Browser console has no relevant error because the incorrect result is normal LLM
  text, not a transport failure.
- **Backend evidence:**

  ```text
  POST /api/chat/turns HTTP/1.1 200 OK
  run state=completed, tool_executions=0
  saved Job count before=3, after=3
  ```

  A corrective retry that explicitly forbade inference did invoke `save_job` and
  returned `Returned existing job for exact content match`, proving the duplicate
  backend path itself is functional.
- **Root-cause evidence:** The production prompt says saved-job actions require a
  registered capability (`backend/app/agent/prompt.py:57`–`61`), but the decision
  path has no deterministic postcondition preventing a mutation-success claim when
  the model emits ordinary text without a tool call.

## F-05 — Unscorable saved-JD detail is rejected by the frontend parser

- **Test IDs:** `JD-005`, `SJD-003`
- **Functional severity:** Medium — a successfully stored unscorable URL Job can be
  listed but its detail cannot be rendered.
- **Affected feature:** Saved-JD selection/detail for valid processed-unscorable
  Jobs.
- **Observable symptom:** Selecting the unscorable URL Job displays:
  `Detail unavailable — extraction.summary must be a non-empty string
  (INVALID_SAVED_JOB_DETAIL_PAYLOAD)`. Compact metadata and actions remain visible,
  but validated extraction detail does not render.
- **Expected behavior:** The saved-JD detail parser should accept every payload
  allowed by the backend `JobPostExtraction` contract and render a graceful partial
  or unscorable detail when optional descriptive text is empty.
- **Reproduction:**
  1. Ask `save_job` to ingest `https://example.com`.
  2. Observe a truthful `processed/unscorable` save outcome.
  3. Refresh **JD đã lưu** and select the newest `unscorable · none` row.
  4. Observe the invalid-payload alert.
- **Frontend/network evidence:** `GET /api/jobs/<job-id>` returns HTTP `200`; the
  client rejects the JSON locally. Sanitized inspection showed
  `extraction.summary` is a string with length `0`. No browser-console error is
  emitted because the parser exception is converted to panel error state.
- **Backend log excerpt:**

  ```text
  GET /api/jobs/<job-id> HTTP/1.1 200 OK
  ```

  A subsequent evaluation attempt correctly returned `409 JOB_NOT_SCORABLE`; that
  controlled error is not this failure.
- **Root-cause evidence:** `backend/app/schemas/jobs.py:99` permits any string for
  `summary`, including `""`, while
  `frontend/src/features/jobs/types.ts:748` requires a non-empty string. The two
  public contracts disagree on a valid unscorable extraction.
