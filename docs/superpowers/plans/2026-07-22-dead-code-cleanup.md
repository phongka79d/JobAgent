# JobAgent Dead-Code Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove verified dead frontend state, compatibility facades, unused exports, and uncalled backend helpers without changing any public behavior or Plan 16 ownership contract.

**Architecture:** Treat deletion as an absence-driven refactor: prove each symbol has no live caller, remove only the dead surface, and preserve the canonical transport, reducer, registry, route, and graph safety owners. Execute this plan only after overlapping Plan 16 work is accepted; keep each deletion group in an independently revertible commit.

**Tech Stack:** React 19, TypeScript 5.9, Vitest, FastAPI, Python 3.11+, Pytest, Ruff, Mypy, PowerShell, Git.

---

## Scope and execution boundary

- Execute after the active Plan 16 batch that edits `savedJobsState.ts`, jobs/observability API types, `skill_assertion_guard.py`, or `sync_cv.py` has been accepted.
- Do not modify `docs/plans/Master_plan.md`, `docs/plans/Plan_16.md`, or `docs/tasks/task_16.md`.
- The four `docs/superpowers/plans/2026-07-22-*.md` files are planning
  artifacts. They may already be tracked or may remain untracked when execution
  starts; implementation commits must not stage them.
- Preserve standalone `saveAndEvaluateJob()` in `frontend/src/features/jobs/api.ts`; `ChatPage` and `useSavedJobRecovery` are its live owners.
- Preserve standalone `streamCvReprocess()` in `frontend/src/lib/api/chat.ts`; `ChatPage` remains the only reprocess SSE/reducer owner.
- Do not delete `extract_document_and_profile_from_chunks`, `build_initial_agent_state`, or `agent_state_field_names` in this plan. They are test seams requiring a separate design decision.
- Do not classify FastAPI decorators, Agent tool factories, registry callbacks, CLI modules, or fixed Cypher constants as dead based only on ordinary import counts.

### Task 1: Remove the dead saved-JD save-and-evaluate state branch

**Files:**
- Modify: `frontend/src/features/jobs/savedJobsState.ts:17-24,47-58,87-92,323-339,618-718,1010-1072`
- Modify: `frontend/src/features/jobs/api.ts:389-406`
- Test: `frontend/src/test/saved-jobs-state.test.tsx`
- Test: `frontend/src/test/saved-jobs-api.test.ts`
- Test: `frontend/src/test/empty-match-card.test.tsx`

- [ ] **Step 1: Run the characterization tests before deleting state**

Run:

```powershell
Set-Location frontend
npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-state.test.tsx src/test/empty-match-card.test.tsx
```

Expected: all selected tests pass. The empty-match tests prove that `ChatPage -> useSavedJobRecovery -> saveAndEvaluateJob` is the live path.

- [ ] **Step 2: Record the dead symbols before deletion**

Run:

```powershell
rg -n "SaveAndEvaluateResponse|pendingSaveByMessage|saveErrorsByMessage|save_begin|save_end|save_error|save_success|const saveAndEvaluate|saveAndEvaluate," src/features/jobs/savedJobsState.ts
rg -n "\.saveAndEvaluate\b|savedJobs\.saveAndEvaluate\b" src -g '*.ts' -g '*.tsx'
```

Expected: the first command finds only the self-contained state branch; the second command returns no consumer of the hook member.

- [ ] **Step 3: Delete the dead reducer and hook branch**

Remove the `SaveAndEvaluateResponse` import, both source-message maps, all four `save_*` action variants and reducer cases, `saveInFlightRef`, the `saveAndEvaluate` callback, and both unconsumed hook-return pending wrappers. Keep the module-level `isJobActionPending()` because the reducer uses it.

The resulting action slice and hook return must have this shape:

```ts
export type SavedJobsActionSlice = {
  pendingByJob: Readonly<Record<string, SavedJobActionKind>>;
  errorsByJob: Readonly<Record<string, SavedJobsSafeError>>;
};

export const initialSavedJobsActionSlice: SavedJobsActionSlice = {
  pendingByJob: {},
  errorsByJob: {},
};

return {
  state,
  selectJob,
  clearActionError,
  loadList,
  loadDetail,
  loadSkillMap,
  evaluateJob,
  confirmDelete,
  confirmReextract,
  invalidateCurrentness,
};
```

- [ ] **Step 4: Narrow the aggregate saved-Jobs API without deleting the live transport**

Keep the exported `saveAndEvaluateJob()` function unchanged. Remove only its aggregate state-hook field:

```ts
export type SavedJobsApi = {
  fetchSavedJobs: typeof fetchSavedJobs;
  fetchSavedJobDetail: typeof fetchSavedJobDetail;
  fetchSelectedJobSkillMap: typeof fetchSelectedJobSkillMap;
  evaluateSavedJob: typeof evaluateSavedJob;
  reextractSavedJob: typeof reextractSavedJob;
  deleteSavedJob: typeof deleteSavedJob;
};

export const defaultSavedJobsApi: SavedJobsApi = {
  fetchSavedJobs,
  fetchSavedJobDetail,
  fetchSelectedJobSkillMap,
  evaluateSavedJob,
  reextractSavedJob,
  deleteSavedJob,
};
```

- [ ] **Step 5: Verify the dead branch is absent and live recovery still works**

Run:

```powershell
rg -n "SaveAndEvaluateResponse|pendingSaveByMessage|saveErrorsByMessage|save_begin|save_end|save_error|save_success|const saveAndEvaluate|saveAndEvaluate," src/features/jobs/savedJobsState.ts
npm test -- --run src/test/saved-jobs-api.test.ts src/test/saved-jobs-state.test.tsx src/test/empty-match-card.test.tsx
npm run typecheck
```

Expected: `rg` exits 1 with no matches; all selected tests and `tsc --noEmit` pass.

- [ ] **Step 6: Commit the saved-JD state cleanup**

```powershell
Set-Location ..
git add frontend/src/features/jobs/savedJobsState.ts frontend/src/features/jobs/api.ts
git commit -m "refactor(frontend): remove dead saved-jd save state"
```

Expected: one commit containing only the two saved-JD files.

### Task 2: Remove stale CV compatibility facades

**Files:**
- Delete: `frontend/src/features/observability/CvHistoryPanel.tsx`
- Modify: `frontend/src/features/observability/api.ts:8-13,36,284-295`
- Modify: `frontend/src/features/observability/cvManagerState.ts:63-69`
- Modify: `frontend/src/test/cv-manager-api.test.ts:7-17`
- Modify: `frontend/src/test/support/observability.tsx:232-245`
- Test: `frontend/src/test/cv-manager.test.tsx`
- Test: `frontend/src/test/observability-sidebar.test.tsx`

- [ ] **Step 1: Prove the compatibility file and pending-kind helper have no caller**

Run:

```powershell
Set-Location frontend
rg -n "CvHistoryPanel|CvHistoryPanelProps|isCvActionKindPending" src -g '*.ts' -g '*.tsx'
rg -n "streamCvReprocess" src/features src/lib -g '*.ts' -g '*.tsx'
```

Expected: `CvHistoryPanel` and `isCvActionKindPending` occur only at their definitions; production reprocess use resolves to `lib/api/chat.ts` and `ChatPage.tsx`, while the observability occurrence is only a facade.

- [ ] **Step 2: Remove the obsolete file and helper**

Delete the compatibility file explicitly:

```powershell
git rm src/features/observability/CvHistoryPanel.tsx
```

Delete only `isCvActionKindPending` from `cvManagerState.ts`; preserve
`isCvActionPending`, which is used to block duplicate actions.

The retained state helper must remain:

```ts
export function isCvActionPending(
  slice: CvManagerActionSlice,
  attachmentId: string,
): boolean {
  return slice.pendingByAttachment[attachmentId] !== undefined;
}
```

- [ ] **Step 3: Remove only the observability reprocess facade**

Remove the `streamCvReprocess` import/re-export and the `ObservabilityApi` field/default-object member. Do not change `getRetainedCvUrl`, CV deletion, or read APIs.

The resulting aggregate type must be:

```ts
export type ObservabilityApi = {
  fetchCvHistory: typeof fetchCvHistory;
  fetchChunkList: typeof fetchChunkList;
  fetchChunkDetail: typeof fetchChunkDetail;
  fetchRunHistory: typeof fetchRunHistory;
  fetchGraphSnapshot: typeof fetchGraphSnapshot;
  getRetainedCvUrl: typeof getRetainedCvUrl;
  deleteCv: typeof deleteCv;
};
```

- [ ] **Step 4: Move the SSE transport test to the real owner**

Change the test imports to this ownership split:

```ts
import {streamCvReprocess} from '../lib/api/chat';
import {
  asCvDeleteErrorCode,
  asCvReprocessErrorCode,
  CV_DELETE_ERROR_CODES,
  CV_DELETE_RETRY_SUMMARY,
  CV_REPROCESS_ERROR_CODES,
  deleteCv,
  isRetryableDeleteError,
  toCvManagerActionError,
} from '../features/observability/api';
```

Remove this property from `mockObservabilityApi()`:

```ts
streamCvReprocess: vi.fn().mockResolvedValue(undefined),
```

- [ ] **Step 5: Run the CV Manager regressions**

Run:

```powershell
npm test -- --run src/test/cv-manager-api.test.ts src/test/cv-manager.test.tsx src/test/observability-sidebar.test.tsx
npm run typecheck
rg -n "CvHistoryPanel|CvHistoryPanelProps|isCvActionKindPending" src -g '*.ts' -g '*.tsx'
```

Expected: tests and typecheck pass; the final `rg` exits 1 with no matches.

- [ ] **Step 6: Commit the CV facade cleanup**

```powershell
Set-Location ..
git add frontend/src/features/observability frontend/src/test/cv-manager-api.test.ts frontend/src/test/support/observability.tsx
git commit -m "refactor(frontend): remove stale cv facades"
```

Expected: one commit containing the deleted compatibility file and the four focused facade/test edits.

### Task 3: Prune verified unused frontend exports

**Files:**
- Modify: `frontend/src/features/chat/activeCvEvidence.ts:25,472-474`
- Modify: `frontend/src/features/chat/jobSaveConfirmation.ts:37-40`
- Modify: `frontend/src/features/jobs/matchResult.ts:87-96`
- Modify: `frontend/src/features/jobs/types.ts:49,403-405`
- Modify: `frontend/src/features/observability/observabilityTabs.ts:35-36`
- Modify: `frontend/src/features/profile/types.ts:79-82`
- Test: `frontend/src/test/saved-job-card.test.tsx`
- Test: `frontend/src/test/job-save-confirmation.test.tsx`
- Test: `frontend/src/test/observability-sidebar.test.tsx`

- [ ] **Step 1: Reconfirm every export has only its definition**

Run:

```powershell
Set-Location frontend
$symbols = 'ActiveCvRecordKind|isReadActiveCvToolName|JOB_SAVE_CONFIRMATION_ACTIONS|MATCH_COMPONENT_LABELS|QUERY_JOBS_TOOL_NAME|SAVED_JOBS_LIMIT_MIN|SAVED_JOBS_LIMIT_MAX|SAVED_JOBS_DEFAULT_LIMIT|SAVED_JOBS_TAB_ID|SAVED_JOBS_TAB_LABEL|ProfileApiParseError'
rg -n $symbols src -g '*.ts' -g '*.tsx'
```

Expected: one definition for each symbol and no import/use elsewhere.

- [ ] **Step 2: Delete the unused declarations without moving live labels or validators**

Apply these exact deletions:

```diff
-export type ActiveCvRecordKind = ActiveCvEntryKind | ActiveCvChunkKind;
-export function isReadActiveCvToolName(toolName: string): boolean {
-  return toolName === READ_ACTIVE_CV_TOOL_NAME;
-}
-export const JOB_SAVE_CONFIRMATION_ACTIONS: readonly JobSaveConfirmationAction[] =
-  [SAVE_JOB_ACTION, CANCEL_SAVE_JOB_ACTION];
-export const MATCH_COMPONENT_LABELS: Readonly<
-  Record<(typeof COMPONENT_KEYS)[number], string>
-> = {
-  semantic_similarity: 'Semantic similarity',
-  skill_score: 'Skill coverage',
-  seniority_score: 'Seniority',
-  experience_score: 'Experience',
-  location_score: 'Location',
-  work_mode_score: 'Work mode',
-};
-export const QUERY_JOBS_TOOL_NAME = 'query_jobs' as const;
-export const SAVED_JOBS_LIMIT_MIN = 1;
-export const SAVED_JOBS_LIMIT_MAX = 50;
-export const SAVED_JOBS_DEFAULT_LIMIT = 50;
-export const SAVED_JOBS_TAB_ID = 'saved-jobs';
-export const SAVED_JOBS_TAB_LABEL = 'JD đã lưu';
-export type ProfileApiParseError = {
-  code: string;
-  summary: string;
-};
```

Keep `READ_ACTIVE_CV_TOOL_NAME`, the live confirmation action union, `ScoreBreakdown.tsx`'s Vietnamese component labels, all parser-local status arrays, and `OBSERVABILITY_TABS` unchanged.

- [ ] **Step 3: Verify compile-time and presentation behavior**

Run:

```powershell
rg -n $symbols src -g '*.ts' -g '*.tsx'
npm test -- --run src/test/saved-job-card.test.tsx src/test/job-save-confirmation.test.tsx src/test/observability-sidebar.test.tsx
npm run lint
npm run typecheck
```

Expected: `rg` exits 1; selected tests, ESLint, and TypeScript pass.

- [ ] **Step 4: Commit the export cleanup**

```powershell
Set-Location ..
git add frontend/src/features/chat frontend/src/features/jobs frontend/src/features/observability/observabilityTabs.ts frontend/src/features/profile/types.ts
git commit -m "refactor(frontend): prune unused exports"
```

Expected: one frontend-only export cleanup commit.

### Task 4: Remove uncalled backend helpers and stale exports

**Files:**
- Modify: `backend/app/services/skill_assertion_guard.py:47-57,138`
- Modify: `backend/tests/unit/test_skill_assertion_guard.py:35-44`
- Validate only: `backend/app/repositories/attachment_text_chunks.py:86-98` (the ordinal getter remains the canonical getter for the next backend plan)
- Modify: `backend/app/repositories/profiles.py:32-33`
- Modify: `backend/app/schemas/cv_document.py:177-196`
- Modify: `backend/app/services/cv_upload.py:435-441`
- Modify: `backend/app/graph/sync_cv.py:321-345`
- Modify: `backend/app/graph/delete_cv.py:35-37,106`
- Test: `backend/tests/unit/test_attachment_text_chunks.py`
- Test: `backend/tests/unit/test_cv_document.py`
- Test: `backend/tests/unit/test_cv_graph.py`
- Test: `backend/tests/integration/test_cv_manager_deletion.py`

- [ ] **Step 1: Capture the current dead-symbol inventory**

Run:

```powershell
Set-Location backend
$symbols = 'is_label_grounded|ProfileNotFoundError|parse_cv_section|parse_cv_entry|iter_bytes_as_chunks|allowed_sync_labels|allowed_sync_relationships|delete_cv_branch_cypher'
rg -n $symbols app tests -g '*.py'
```

Expected: matches are definitions, `__all__` entries, the obsolete `is_label_grounded` test, and the old deletion test name; the deletion test reads `DELETE_CV_BRANCH_CYPHER` directly rather than calling the wrapper.

- [ ] **Step 2: Delete the exact helpers and clean their imports/exports**

Remove the function/class definitions and their `__all__` entries. Remove the obsolete `is_label_grounded` unit test instead of replacing it with a test for deleted behavior. Rename `test_delete_cv_branch_cypher_is_allowlisted` to `test_delete_cv_branch_constant_is_allowlisted`; it validates `DELETE_CV_BRANCH_CYPHER`, which remains unchanged.

Also remove imports made unused by deletion, including `AsyncIterator` from `cv_upload.py` only if no remaining annotation uses it.

- [ ] **Step 3: Verify no deleted symbol remains**

Run:

```powershell
rg -n $symbols app tests -g '*.py'
```

Expected: exit 1 with no matches after the deletion test has been renamed to `test_delete_cv_branch_constant_is_allowlisted`.

- [ ] **Step 4: Run focused backend regression tests and static checks**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_skill_assertion_guard.py tests/unit/test_cv_document.py tests/unit/test_attachment_text_chunks.py tests/unit/test_cv_graph.py tests/integration/test_cv_manager_deletion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: all selected tests pass; Ruff reports `All checks passed!`; Mypy reports success for the application package.

- [ ] **Step 5: Commit the backend helper cleanup**

```powershell
Set-Location ..
git add backend/app backend/tests/unit/test_skill_assertion_guard.py backend/tests/integration/test_cv_manager_deletion.py
git commit -m "refactor(backend): remove uncalled helpers"
```

Expected: one backend-only cleanup commit with no route, schema, migration, tool, or persistence behavior change.

### Task 5: Run the integrated cleanup gate

**Files:**
- Validate: all files changed in Tasks 1-4

- [ ] **Step 1: Run the full automated gates**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q

Set-Location ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: every command exits 0; test counts are reported from this candidate rather than copied from older acceptance evidence.

- [ ] **Step 2: Audit scope, deleted symbols, and the dirty user file**

Run:

```powershell
Set-Location ..
git diff --check
git status --short
git log -4 --oneline
rg -n "CvHistoryPanel|pendingSaveByMessage|saveErrorsByMessage|is_label_grounded|iter_bytes_as_chunks" backend/app backend/tests frontend/src -g '*.py' -g '*.ts' -g '*.tsx'
```

Expected: whitespace is clean; the four planned commits are present; the final
`rg` has no matches; `docs/plans/Master_plan.md` remains exactly the user's
pre-existing modification and is absent from every cleanup commit. Status may
also show the four authorized plan artifacts when they were not committed
before execution; no other unplanned path may appear.

- [ ] **Step 3: Close the plan only after all four focused commits pass the integrated gate**

If validation exposes a defect, return to the specific task, edit only its listed files, rerun that task's focused command and this integrated gate, and use that task's existing commit command. Do not create an additional cleanup scope or an empty commit.
