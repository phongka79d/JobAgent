# JobAgent Product UX and Trust Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JobAgent's profile, CV, Saved Job, chat, and tailored-CV workflows coherent, recoverable, privacy-safe, English-only, and understandable to a non-technical frontend user.

**Architecture:** Keep the existing React/Astryx and FastAPI/SQLite architecture and repair contracts at their current owners. The server remains authoritative for profile scope, CV actions, re-extraction drafts, no-op detection, grounding safety, display labels, and artifact ownership; the frontend keeps one workspace, Saved Jobs, and tailoring state owner and renders only validated projections.

**Tech Stack:** React 19, TypeScript 5.9, Astryx 0.1.4, Vitest/Testing Library, FastAPI 0.139, Pydantic 2.12, SQLAlchemy 2.0 async, SQLite, LangGraph, pytest, Ruff, mypy, fixed LaTeX/PDF rendering.

---

## Authority, scope, and execution guard

Authoritative design: `docs/superpowers/specs/2026-07-27-jobagent-product-ux-trust-repair-design.md` at commit `bd296c1`.

This is one plan because the user explicitly requested a single plan. Tasks remain dependency-ordered and independently testable. Do not split ownership, introduce a router/global state library/i18n library, add a database migration, change scoring math, remove backend observability, add a frontend E2E dependency, or add a second SSE/chat/tailoring state owner.

Before Task 1, run:

```powershell
git status --short
git diff -- backend/app/agent/tailoring_graph.py backend/tests/unit/test_cv_tailoring_agent.py frontend/src/app/App.test.tsx frontend/src/app/App.tsx frontend/src/app/theme.css
git diff --check
```

Expected baseline: exactly those five user-owned files may be modified. Preserve the existing tailoring identity-skeleton/requested-section changes and the `jobagent-chat-workspace[hidden]` fix. If the set or content differs, stop and reconcile with the user before applying this plan. Do not stage unrelated files. Only one write-capable Luna worker may operate in this working tree at a time, per root `AGENTS.md`.

## Locked cross-layer contracts

```ts
// Frontend workspace render gate.
type WorkspacePhase = 'rehydrating' | 'ready' | 'error';

// Server-projected CV actions. The browser never derives delete eligibility.
type CvManagerAction =
  | 'preview'
  | 'download'
  | 'reextract'
  | 'activate_profile'
  | 'retry_upload'
  | 'delete_cv';

// Later tailoring mutations only.
type TailoringMutationOutcome = 'version_created' | 'no_change';

// Safe user issue; raw GroundingIssue code/path never crosses the API.
type TailoringUserIssue = {
  section_id: string;
  section_heading: string;
  item_index: number | null;
  field:
    | 'title'
    | 'subtitle'
    | 'date'
    | 'location'
    | 'body'
    | 'bullet'
    | 'attribute'
    | 'section';
  reason:
    | 'not_in_source'
    | 'belongs_to_another_section'
    | 'structure_changed'
    | 'required_source_missing'
    | 'unsupported_value';
};
```

Profile re-extraction keeps `POST /api/profiles/{profile_id}/reextract` and adds:

```text
GET    /api/profiles/{profile_id}/reextract-draft
POST   /api/profiles/{profile_id}/reextract-draft/approve
DELETE /api/profiles/{profile_id}/reextract-draft?revision=<UTC timestamp>
```

CV Manager gains product routes separate from technical observability:

```text
GET    /api/cvs
GET    /api/cvs/{attachment_id}/file?disposition=inline|attachment
DELETE /api/cvs/{attachment_id}
```

`GET /api/cvs` returns server-owned `allowed_actions`. Profile-owned active/archived CVs never include `delete_cv`; only unowned staged/failed/deleting attachments can include it.

## File map and responsibility

### New backend units

- `backend/app/schemas/profile_reextraction.py`: strict direct re-extraction event, review, revision, approval, and discard DTOs.
- `backend/app/services/profile_reextraction.py`: the only direct re-extraction/review/approve/discard coordinator; reuses existing extraction/draft/approval owners.
- `backend/app/services/cv_manager_projection.py`: safe CV Manager list/action/file projection; no deletion mutation.
- `backend/app/services/tailoring_issue_projection.py`: raw issue-to-safe issue mapping plus bounded durable activity encode/decode.
- `backend/app/services/job_display.py`: one pure Saved Job display-label helper.
- `backend/tests/unit/test_profile_reextraction.py`, `test_tailoring_issue_projection.py`, `test_job_display.py`: pure projection tests.

### New frontend units

- `frontend/src/features/profile/useWorkspaceLifecycle.ts`: `pageshow` subscription only.
- `frontend/src/features/profile/copy.ts`: profile/workspace English product copy.
- `frontend/src/features/navigation/productNavigation.ts`, `ProductSidebar.tsx`: exactly three primary destinations and sidebar rail/panel composition.
- `frontend/src/features/cv-manager/types.ts`, `api.ts`, `state.ts`: strict CV list/action and direct re-extraction contracts with one transient controller.
- `frontend/src/features/cv-manager/CvManagerDrawer.tsx`, `ProfileReextractReview.tsx`, `CvDeleteDialog.tsx`, `copy.ts`, `cv-manager.css`: progressive-disclosure lifecycle UI.
- `frontend/src/lib/api/download.ts`: fetch-to-blob download helper; never changes `window.location`.
- `frontend/src/lib/hooks/useLatestRequest.ts`: generic latest-request helper moved out of observability.
- `frontend/src/features/jobs/copy.ts`, `jobs.css`: English Saved Job/match copy and retained styles.
- `frontend/src/features/cv-tailoring/copy.ts`, `presentation.ts`: English copy and one session-label/filename owner.
- `frontend/src/features/chat/copy.ts`, `activityPresentation.ts`: English chat/activity presentation without technical names/codes/timing.

### Existing convergence files

- `frontend/src/features/profile/workspaceState.ts`, `frontend/src/app/App.tsx`: coherent workspace publication and composition gates.
- `backend/app/api/profiles.py`, `backend/app/services/profile_drafts.py`, `backend/app/services/profile_approval.py`: direct re-extraction transport and existing durable truth owners.
- `backend/app/services/cv_tailoring.py`, `backend/app/repositories/cv_tailoring.py`, `backend/app/schemas/cv_tailoring.py`: no-op, safe issue, version, and recovery contracts.
- `frontend/src/features/cv-tailoring/state.ts`, `TailoringEditor.tsx`, `TailoredSectionEditor.tsx`: one draft/recovery/UI owner.
- `backend/app/services/saved_jobs.py`, `backend/app/schemas/job_evaluations.py`: Saved Job label projection.
- `backend/app/services/cv_tailoring_renderer.py`: duplicate-heading suppression only.
- `backend/app/services/conversation_titles.py`, `backend/app/agent/prompt.py`, `backend/app/agent/graph.py`: deterministic titles and explicit tailoring intent.

### Frontend-only removal boundary

After CV Manager and Saved Jobs are extracted, delete `frontend/src/features/observability/` in full and delete its technical-only graph/chunk/run/skill-map tests. Keep `backend/app/api/observability.py`, backend observability schemas/services/repositories/tests, and the existing `d3-*` package declarations unchanged.

Test snippets below extend the named existing fixture files. Any helper name introduced in a snippet (`profile`, `conversation`, `deferred`, `props`, `parentContent`, and similar) must be declared in that same test file from its current fixture builder; no production helper or hidden test dependency is implied.

---

### Task 1: Fail closed during workspace rehydration and browser restoration

**Files:**

- Create: `frontend/src/features/profile/useWorkspaceLifecycle.ts`
- Modify: `frontend/src/features/profile/workspaceState.ts`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`
- Test: `frontend/src/test/profile-workspace-state.test.tsx`

- [x] **Step 1: Write reducer and hook tests for ownership, ordering, and `pageshow`**

Extend the existing fixtures/constants in `frontend/src/test/profile-workspace-state.test.tsx`. Add this local deferred helper and pass the existing `fetchProfiles`/`fetchProfileConversations` fakes through `useProfileWorkspaceState`:

```ts
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return {promise, resolve, reject};
}
```

Add focused cases using the existing `profile`, `conversation`, API fakes, and `renderHook` helpers:

```tsx
it('publishes ready state only when every conversation belongs to the active profile', async () => {
  const api = createWorkspaceApi({
    profiles: {items: [profile('profile-a', true)], active_profile_id: 'profile-a'},
    conversations: {
      items: [conversation('conversation-b', 'profile-b', true)],
      next_cursor: null,
    },
  });
  const {result} = renderHook(() => useProfileWorkspaceState(api));

  await waitFor(() => expect(result.current.state.phase).toBe('error'));
  expect(result.current.state.conversations).toEqual([]);
  expect(result.current.state.selectedConversationId).toBeNull();
  expect(result.current.state.error).toBe('Workspace data did not match the active profile.');
});

it('ignores an older reload after a newer authoritative snapshot wins', async () => {
  const first = deferred<ProfileListResponse>();
  const second = deferred<ProfileListResponse>();
  const api = createSequencedWorkspaceApi([first.promise, second.promise]);
  const {result} = renderHook(() => useProfileWorkspaceState(api));

  act(() => { void result.current.reload(); });
  second.resolve({items: [profile('profile-b', true)], active_profile_id: 'profile-b'});
  await waitFor(() => expect(result.current.state.activeProfileId).toBe('profile-b'));
  first.resolve({items: [profile('profile-a', true)], active_profile_id: 'profile-a'});

  await waitFor(() => expect(result.current.state.activeProfileId).toBe('profile-b'));
});

it('rehydrates a persisted pageshow and removes the listener on cleanup', async () => {
  const reload = vi.fn(async () => undefined);
  const {unmount} = renderHook(() => useWorkspaceLifecycle(reload));
  window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  unmount();
  window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
  expect(reload).toHaveBeenCalledTimes(1);
});
```

- [x] **Step 2: Run the workspace tests and verify the new contract fails**

Run:

```powershell
Set-Location frontend
npm test -- --run src/test/profile-workspace-state.test.tsx
```

Expected: FAIL because `phase`, ownership validation, and `useWorkspaceLifecycle` do not exist.

- [x] **Step 3: Implement one atomic workspace snapshot reducer**

Replace the split profile/conversation publication during reload with these shapes; retain existing mutation actions for activate/rename/create/select/delete:

```ts
export type WorkspacePhase = 'rehydrating' | 'ready' | 'error';

export type ProfileWorkspaceState = {
  phase: WorkspacePhase;
  profiles: ProfileListItem[];
  activeProfileId: string | null;
  selectedConversationId: string | null;
  conversations: ConversationSummary[];
  pending: ReadonlySet<string>;
  error: string | null;
};

type WorkspaceSnapshot = {
  profiles: ProfileListResponse;
  conversations: ConversationListResponse;
};

function validateSnapshot(snapshot: WorkspaceSnapshot): WorkspaceSnapshot {
  const active = snapshot.profiles.active_profile_id;
  if (active !== null && !snapshot.profiles.items.some((item) => item.id === active)) {
    throw new Error('Workspace data did not match the active profile.');
  }
  if (snapshot.conversations.items.some((item) => item.profile_id !== active)) {
    throw new Error('Workspace data did not match the active profile.');
  }
  const selected = snapshot.conversations.items.filter((item) => item.is_selected);
  if (selected.length > 1) {
    throw new Error('Workspace data did not match the active profile.');
  }
  return snapshot;
}

// Reducer cases used by reload only.
case 'rehydrate/started':
  return {
    ...state,
    phase: 'rehydrating',
    conversations: [],
    selectedConversationId: null,
    error: null,
  };
case 'rehydrate/succeeded': {
  const snapshot = validateSnapshot(action.snapshot);
  const selected = snapshot.conversations.items.find((item) => item.is_selected);
  return {
    ...state,
    phase: 'ready',
    profiles: snapshot.profiles.items,
    activeProfileId: snapshot.profiles.active_profile_id,
    conversations: snapshot.conversations.items,
    selectedConversationId: selected?.id ?? null,
    error: null,
  };
}
case 'rehydrate/failed':
  return {
    ...state,
    phase: 'error',
    conversations: [],
    selectedConversationId: null,
    error: action.error,
  };
```

In `reload`, increment the generation, abort the prior controller, dispatch `rehydrate/started`, fetch profiles, fetch conversations only for `active_profile_id`, and dispatch one `rehydrate/succeeded`. For a null active profile, use `{items: [], next_cursor: null}`. Abort and ignore old generations; never publish the profile response alone.

- [x] **Step 4: Add the isolated `pageshow` hook and App render gate**

Create:

```ts
import {useEffect} from 'react';

export function useWorkspaceLifecycle(reload: () => Promise<void>): void {
  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) void reload();
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, [reload]);
}
```

Call it exactly once in `App`. Render a labeled loading state while `phase === 'rehydrating'`, an error Banner with a **Retry** button while `phase === 'error'`, and render `ChatPage` only while ready. Key the chat owner with both identities:

```tsx
const chatKey = `${workspace.state.activeProfileId ?? 'no-profile'}:${
  workspace.state.selectedConversationId ?? 'no-conversation'
}`;

{workspace.state.phase === 'ready' ? (
  <ChatPage key={chatKey} /* existing props */ />
) : workspace.state.phase === 'rehydrating' ? (
  <WorkspaceStatus title="Loading your workspace…" />
) : (
  <WorkspaceStatus
    title="Your workspace could not be loaded"
    actionLabel="Retry"
    onAction={() => void workspace.reload()}
  />
)}
```

Preserve the existing hidden chat workspace CSS fix when placing this gate.

- [x] **Step 5: Prove App never renders stale cross-profile chat**

Add an App test that starts with Profile A/chat A, resolves a `pageshow` reload to Profile B/chat B, and asserts chat A is absent during `rehydrating` and the remount key changes once. Then run:

```powershell
npm test -- --run src/test/profile-workspace-state.test.tsx src/app/App.test.tsx
npm run typecheck
```

Expected: all selected tests PASS; TypeScript exits 0.

- [x] **Step 6: Commit the coherent workspace milestone**

```powershell
Set-Location ..
git add frontend/src/features/profile/workspaceState.ts frontend/src/features/profile/useWorkspaceLifecycle.ts frontend/src/app/App.tsx frontend/src/app/App.test.tsx frontend/src/app/theme.css frontend/src/test/profile-workspace-state.test.tsx
git diff --cached --check
git commit -m "fix: rehydrate profile workspace before rendering"
```

Verify the staged App/theme diff still contains the pre-existing `jobagent-chat-workspace[hidden]` behavior.

---

### Task 2: Add a server-authoritative product CV Manager contract

**Files:**

- Create: `backend/app/services/cv_manager_projection.py`
- Modify: `backend/app/repositories/attachments.py`
- Modify: `backend/app/schemas/cv_manager.py`
- Modify: `backend/app/api/cvs.py`
- Test: `backend/tests/integration/test_cv_manager_api.py`
- Test: `backend/tests/integration/test_cv_manager_deletion.py`

- [x] **Step 1: Write failing API tests for server-owned allowed actions**

Add cases that seed one active ready profile, one archived ready profile, one pending failed profile, and one truly unowned failed attachment:

```py
def test_cv_manager_list_projects_actions_without_storage_or_hash(cv_env) -> None:
    active, archived, pending, orphan = seed_cv_manager_matrix(cv_env)
    response = TestClient(app).get("/api/cvs")

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()["items"]}
    assert by_id[active]["allowed_actions"] == ["preview", "download", "reextract"]
    assert by_id[archived]["allowed_actions"] == [
        "preview", "download", "activate_profile", "reextract"
    ]
    assert by_id[pending]["allowed_actions"] == ["retry_upload"]
    assert by_id[orphan]["allowed_actions"] == ["delete_cv"]
    assert all("storage_path" not in item and "file_hash" not in item for item in by_id.values())

def test_profile_owned_attachment_delete_is_rejected_for_every_lifecycle_state(cv_env) -> None:
    for attachment_id in seed_profile_owned_active_archived_staged_failed(cv_env):
        response = TestClient(app).delete(f"/api/cvs/{attachment_id}")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "CV_PROFILE_OWNED_DELETE_FORBIDDEN"
```

- [x] **Step 2: Run the focused backend tests and verify route/schema failures**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_cv_manager_api.py tests/integration/test_cv_manager_deletion.py -q
```

Expected: FAIL because `GET /api/cvs`, `allowed_actions`, and the precise ownership code do not exist.

- [x] **Step 3: Implement the pure action projection**

Add `list_all` ordered by newest `created_at,id` to `repositories/attachments.py`. Define strict DTOs:

```py
CvManagerAction = Literal[
    "preview", "download", "reextract", "activate_profile", "retry_upload", "delete_cv"
]

class CvManagerItem(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    original_name: str = Field(min_length=1, max_length=500)
    state: Literal["staged", "active", "archived", "failed", "deleting"]
    failure_code: str | None
    page_count: int | None
    file_available: bool
    profile_id: UuidStr | None
    profile_display_name: str | None
    profile_state: Literal["pending", "ready", "deleting"] | None
    is_active_profile: bool
    allowed_actions: list[CvManagerAction]
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime

class CvManagerListResponse(BaseModel):
    model_config = StrictModelConfig
    items: list[CvManagerItem]
```

Use one server function:

```py
def allowed_actions(*, state: str, owner: Profile | None, is_active: bool, file_available: bool) -> list[CvManagerAction]:
    if owner is None:
        return ["delete_cv"] if state in {"staged", "failed", "deleting"} else []
    if owner.state == "pending":
        return ["retry_upload"] if state in {"staged", "failed"} else []
    actions: list[CvManagerAction] = []
    if file_available and state in {"active", "archived"}:
        actions.extend(["preview", "download"])
    if not is_active:
        actions.append("activate_profile")
    if state in {"active", "archived"}:
        actions.append("reextract")
    return actions
```

Do not add `delete_cv` for any profile owner.

- [x] **Step 4: Add safe list/file routes and precise deletion language**

Add `GET /api/cvs` and `GET /api/cvs/{attachment_id}/file`. The file route accepts only `disposition=inline|attachment`, resolves only an existing active/archived owned CV with an available retained file, and returns:

```py
headers = {
    "Content-Disposition": f'{disposition}; filename="{safe_download_name(original_name)}"',
    "X-Content-Type-Options": "nosniff",
}
return FileResponse(path, media_type="application/pdf", headers=headers)
```

Rename the misleading constant to `CV_PROFILE_OWNED_DELETE_FORBIDDEN` and return the safe summary `This CV belongs to a profile. Delete the profile from the Profile menu instead.` Keep old partial-cleanup retry codes unchanged.

- [x] **Step 5: Verify product reads and delete invariants**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_cv_manager_api.py tests/integration/test_cv_manager_deletion.py tests/integration/test_profile_deletion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/api/cvs.py app/schemas/cv_manager.py app/services/cv_manager.py app/services/cv_manager_projection.py app/repositories/attachments.py tests/integration/test_cv_manager_api.py tests/integration/test_cv_manager_deletion.py --no-cache
```

Expected: all tests PASS; Ruff exits 0.

- [x] **Step 6: Commit the product CV contract**

```powershell
Set-Location ..
git add backend/app/api/cvs.py backend/app/repositories/attachments.py backend/app/schemas/cv_manager.py backend/app/services/cv_manager.py backend/app/services/cv_manager_projection.py backend/tests/integration/test_cv_manager_api.py backend/tests/integration/test_cv_manager_deletion.py
git diff --cached --check
git commit -m "feat: expose safe CV manager actions"
```

---

### Task 3: Extract the CV Manager frontend into one typed controller

**Files:**

- Create: `frontend/src/features/cv-manager/types.ts`
- Create: `frontend/src/features/cv-manager/api.ts`
- Create: `frontend/src/features/cv-manager/state.ts`
- Create: `frontend/src/features/cv-manager/CvManagerDrawer.tsx`
- Create: `frontend/src/features/cv-manager/CvDeleteDialog.tsx`
- Create: `frontend/src/features/cv-manager/copy.ts`
- Create: `frontend/src/features/cv-manager/cv-manager.css`
- Create: `frontend/src/lib/hooks/useLatestRequest.ts`
- Modify: `frontend/src/features/profile/ProfileOverviewPanel.tsx`
- Modify: `frontend/src/features/profile/CvSidebar.tsx`
- Modify: `frontend/src/features/profile/ProfileDeleteDialog.tsx`
- Modify: `frontend/src/features/chat/components/ActiveCvSourceDialog.tsx`
- Rewrite: `frontend/src/test/cv-manager-api.test.ts`
- Rewrite: `frontend/src/test/cv-manager.test.tsx`
- Modify: `frontend/src/test/active-cv-source.test.tsx`

- [x] **Step 1: Replace inferred-action tests with strict parser tests**

Use an exact response fixture and reject extras:

```ts
it('accepts only the server action vocabulary and never infers delete eligibility', () => {
  const item = parseCvManagerItem({
    id: ATTACHMENT_ID,
    original_name: 'CV.pdf',
    state: 'active',
    failure_code: null,
    page_count: 2,
    file_available: true,
    profile_id: PROFILE_ID,
    profile_display_name: 'Frontend profile',
    profile_state: 'ready',
    is_active_profile: true,
    allowed_actions: ['preview', 'download', 'reextract'],
    created_at: NOW,
    updated_at: NOW,
  });
  expect(item.allowed_actions).not.toContain('delete_cv');
  expect(() => parseCvManagerItem({...item, storage_path: 'private'})).toThrow();
});

it('renders Delete CV only when delete_cv is in the server projection', () => {
  render(<CvManagerDrawer {...props({items: [orphanFailedItem()]})} />);
  expect(screen.getByRole('button', {name: 'Delete CV'})).toBeEnabled();
  cleanup();
  render(<CvManagerDrawer {...props({items: [profileOwnedActiveItem()]})} />);
  expect(screen.queryByRole('button', {name: 'Delete CV'})).not.toBeInTheDocument();
});
```

- [x] **Step 2: Run the CV Manager frontend tests and confirm old behavior fails**

```powershell
Set-Location frontend
npm test -- --run src/test/cv-manager-api.test.ts src/test/cv-manager.test.tsx src/test/active-cv-source.test.tsx
```

Expected: FAIL because tests still import observability modules and the old UI routes profile-owned deletion through `workspace.deleteProfile`.

- [x] **Step 3: Implement exact DTO parsing and transport**

Define `CvManagerAction`, `CvManagerItem`, `CvManagerListResponse`, and exact parsers in `types.ts`. Implement:

```ts
export async function fetchCvManager(signal?: AbortSignal): Promise<CvManagerListResponse> {
  const response = await fetch(apiUrl('/api/cvs'), {
    method: 'GET', headers: {Accept: 'application/json'}, signal,
  });
  const text = await response.text();
  if (!response.ok) throw parseErrorBody(response.status, text);
  try {
    return parseCvManagerListResponse(JSON.parse(text) as unknown);
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError(200, 'INVALID_CV_MANAGER_PAYLOAD', error instanceof Error ? error.message : 'Invalid CV Manager payload');
  }
}

export function cvFileUrl(id: string, disposition: 'inline' | 'attachment'): string {
  return apiUrl(`/api/cvs/${encodeURIComponent(id)}/file?disposition=${disposition}`);
}

export async function deleteCv(id: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(apiUrl(`/api/cvs/${encodeURIComponent(id)}`), {
    method: 'DELETE', headers: {Accept: 'application/json'}, signal,
  });
  if (response.status === 204) return;
  throw parseErrorBody(response.status, await response.text());
}
```

Move `useLatestRequest` unchanged into `frontend/src/lib/hooks/useLatestRequest.ts`; update Saved Jobs imports now so no retained product code depends on observability.

- [x] **Step 4: Implement one transient CV Manager state owner**

`useCvManagerState` owns `closed|loading|ready|error`, selected ID, one mutation per attachment, preserved prior list on refresh failure, and aborts on profile-scope change. It must call `deleteCv` only after checking the selected server projection contains `delete_cv`:

```ts
const confirmDelete = useCallback(async (id: string): Promise<boolean> => {
  const item = state.resource.data?.items.find((candidate) => candidate.id === id);
  if (!item?.allowed_actions.includes('delete_cv') || pendingRef.current.has(id)) return false;
  pendingRef.current.add(id);
  setPending(id, true);
  try {
    await api.deleteCv(id);
    await load({force: true});
    return true;
  } catch (error) {
    setActionError(id, safeCvError(error));
    return false;
  } finally {
    pendingRef.current.delete(id);
    setPending(id, false);
  }
}, [api, load, state.resource.data]);
```

- [x] **Step 5: Build the accessible drawer and Overview entry**

Run Astryx discovery before implementation:

```powershell
npx astryx build "CV lifecycle side panel with selectable rows, status, actions, and confirmation"
npx astryx component Drawer
npx astryx component List
npx astryx component AlertDialog
```

Use the returned public components/props. Add **Manage CVs** to `ProfileOverviewPanel`; render a side drawer on desktop and full-screen drawer on narrow viewports. Action buttons come only from `allowed_actions`. **Delete CV** opens a filename-scoped confirmation and never calls `workspace.deleteProfile`. Profile deletion remains in `ProfileDeleteDialog` with the exact label **Delete profile and all data**.

- [x] **Step 6: Move active-CV file callers off observability and verify**

Update `ActiveCvSourceDialog` and its test to import `cvFileUrl` from the new API. Run:

```powershell
npm test -- --run src/test/cv-manager-api.test.ts src/test/cv-manager.test.tsx src/test/active-cv-source.test.tsx src/test/cv-sidebar.test.tsx
npm run typecheck
```

Expected: selected tests PASS; typecheck exits 0; no test expects profile deletion from CV Manager.

- [x] **Step 7: Commit the extracted CV Manager**

```powershell
Set-Location ..
git add frontend/src/features/cv-manager frontend/src/lib/hooks/useLatestRequest.ts frontend/src/features/profile/ProfileOverviewPanel.tsx frontend/src/features/profile/CvSidebar.tsx frontend/src/features/jobs/savedJobsState.ts frontend/src/features/chat/components/ActiveCvSourceDialog.tsx frontend/src/test/cv-manager-api.test.ts frontend/src/test/cv-manager.test.tsx frontend/src/test/active-cv-source.test.tsx frontend/src/test/cv-sidebar.test.tsx
git diff --cached --check
git commit -m "refactor: extract product CV manager"
```

---

### Task 4: Replace observability navigation with three product destinations

**Files:**

- Create: `frontend/src/features/navigation/productNavigation.ts`
- Create: `frontend/src/features/navigation/ProductSidebar.tsx`
- Create: `frontend/src/features/jobs/jobs.css`
- Modify: `frontend/src/features/profile/CvSidebar.tsx`
- Modify: `frontend/src/features/jobs/SavedJobsPanel.tsx`
- Modify: `frontend/src/features/jobs/SavedJobDetail.tsx`
- Modify: `frontend/src/features/jobs/api.ts`
- Modify: `frontend/src/features/jobs/savedJobsState.ts`
- Modify: `frontend/src/app/App.tsx`
- Delete: `frontend/src/features/observability/`
- Create: `frontend/src/test/product-navigation.test.tsx`
- Modify: `frontend/src/test/saved-jobs-panel.test.tsx`
- Modify: `frontend/src/test/cv-tailoring-state.test.tsx`
- Delete: technical-only observability/graph/skill-map test files listed in Step 4

- [x] **Step 1: Write the three-destination and static-removal tests**

```tsx
it('exposes exactly the approved primary navigation in order', () => {
  expect(PRODUCT_DESTINATIONS.map(({id, label}) => [id, label])).toEqual([
    ['overview', 'Overview'],
    ['saved-jobs', 'Saved Jobs'],
    ['tailored-cvs', 'Tailored CVs'],
  ]);
});

it('contains no product imports or labels for technical panels', () => {
  const source = readRetainedFrontendSource();
  for (const forbidden of ['LLM chunks', 'Neo4j graph', 'Agent runs', 'features/observability']) {
    expect(source).not.toContain(forbidden);
  }
});
```

- [ ] **Step 2: Run navigation/Saved Jobs tests and verify seven-tab assumptions fail**

```powershell
Set-Location frontend
npm test -- --run src/test/product-navigation.test.tsx src/test/saved-jobs-panel.test.tsx src/test/cv-tailoring-state.test.tsx
```

Expected: FAIL because `OBSERVABILITY_TABS`, `ObservabilitySidebar`, and seven-tab assertions remain.

- [x] **Step 3: Implement `ProductSidebar` without another data owner**

Use one local selected destination and the existing controllers passed from `App`:

```ts
export type ProductDestination = 'overview' | 'saved-jobs' | 'tailored-cvs';

export const PRODUCT_DESTINATIONS = [
  {id: 'overview', label: 'Overview', icon: 'info'},
  {id: 'saved-jobs', label: 'Saved Jobs', icon: 'copy'},
  {id: 'tailored-cvs', label: 'Tailored CVs', icon: 'clock'},
] as const satisfies readonly ProductDestinationDefinition[];
```

`ProductSidebar` renders the supplied Overview content, the existing `SavedJobsPanel`, or `TailoringSessionsPanel`. It calls only the existing `savedJobs` and `tailoring` controllers; it does not invoke their hooks. Opening a destination expands a collapsed rail and loads only that destination's existing controller.

- [x] **Step 4: Move retained styles and remove technical modules/tests**

Move Saved Job rules from `observability.css` into `jobs.css` and CV Manager rules into `cv-manager.css`, renaming `jobagent-obs-*` classes to feature names. Delete all files under `frontend/src/features/observability/` after imports are removed. Delete these technical-only suites:

```text
frontend/src/test/graph-interaction.test.tsx
frontend/src/test/graph-panel-error.test.tsx
frontend/src/test/graph-panel.test.tsx
frontend/src/test/graph-presentation.test.ts
frontend/src/test/graph-viewport.test.tsx
frontend/src/test/observability-api.test.ts
frontend/src/test/observability-navigation.test.tsx
frontend/src/test/observability-panels.test.tsx
frontend/src/test/observability-primitives.test.tsx
frontend/src/test/observability-sidebar.test.tsx
frontend/src/test/observability-state.test.tsx
frontend/src/test/skill-compatibility-api.test.ts
frontend/src/test/skill-compatibility-map.test.tsx
frontend/src/test/support/observability.tsx
```

Remove skill-map transport/cache code from `features/jobs/api.ts`, `types.ts`, and `savedJobsState.ts`; it has no remaining product consumer. Replace Saved Jobs' observability skeleton/header imports with direct Astryx `Skeleton`, `Heading`, and `Button` composition. Do not modify backend observability files or `frontend/package.json`.

- [x] **Step 5: Update App composition and sole-owner static assertions**

Pass `workspace`, `savedJobs`, and `tailoring` into `CvSidebar`/`ProductSidebar`. Keep the only `useSavedJobsState` and `useCvTailoringState` calls in `App`. Replace the old raw-source assertion with:

```ts
it('keeps singleton product state hooks in App', () => {
  expect(appSource.match(/useSavedJobsState\(/g)).toHaveLength(1);
  expect(appSource.match(/useCvTailoringState\(/g)).toHaveLength(1);
  expect(retainedFeatureSource).not.toMatch(/useSavedJobsState\(|useCvTailoringState\(/);
});
```

- [ ] **Step 6: Verify navigation, build, and static removal**

```powershell
npm test -- --run src/test/product-navigation.test.tsx src/test/saved-jobs-panel.test.tsx src/test/cv-tailoring-sessions-panel.test.tsx src/test/cv-tailoring-state.test.tsx src/test/cv-sidebar.test.tsx src/app/App.test.tsx
npm run lint
npm run typecheck
npm run build
rg -n "features/observability|LLM chunks|Neo4j graph|Agent runs" src
```

Expected: tests/lint/typecheck/build PASS. The final `rg` exits 1 with no matches in retained source.

- [x] **Step 7: Commit the product navigation milestone**

```powershell
Set-Location ..
git add frontend/src/features/navigation frontend/src/features/observability frontend/src/features/jobs frontend/src/features/profile/CvSidebar.tsx frontend/src/app/App.tsx frontend/src/test/product-navigation.test.tsx frontend/src/test/saved-jobs-panel.test.tsx frontend/src/test/cv-tailoring-state.test.tsx
git diff --cached --check
git commit -m "refactor: simplify product navigation"
```

Before committing, inspect `git diff --cached --name-status` and confirm no backend observability path and no dependency manifest is staged.

---

### Task 5: Replace chat-based CV re-extraction with a durable direct review workflow

**Files:**

- Create: `backend/app/schemas/profile_reextraction.py`
- Create: `backend/app/services/profile_reextraction.py`
- Modify: `backend/app/api/sse.py`
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/app/api/profiles.py`
- Modify: `backend/app/schemas/profile.py`
- Modify: `backend/app/services/profile_approval.py`
- Modify: `backend/app/services/activity_gate.py`
- Modify: `backend/app/services/profile_activation.py`
- Modify: `backend/app/services/cv_upload.py`
- Modify: `backend/app/services/profile_deletion.py`
- Modify: `backend/app/repositories/profiles.py`
- Modify: `backend/app/repositories/cv_documents.py`
- Test: `backend/tests/unit/test_profile_reextraction.py`
- Test: `backend/tests/integration/test_profile_reextraction.py`
- Test: `backend/tests/integration/test_profiles_api.py`
- Test: `backend/tests/integration/test_profile_selection.py`
- Test: `backend/tests/integration/test_cv_api.py`
- Test: `backend/tests/integration/test_profile_deletion.py`
- Test: `backend/tests/unit/test_api_sse.py`

- [x] **Step 1: Define strict event/review contracts and write parser tests**

Create the new schema module with bounded fields and no raw text/path/provider payloads:

```py
ReextractStage = Literal[
    "validating_source", "extracting_document", "projecting_profile", "publishing_review"
]

class ProfileReextractProgress(BaseModel):
    model_config = StrictModelConfig
    stage: ReextractStage
    message: str = Field(min_length=1, max_length=160)

class PublicProfileSnapshot(BaseModel):
    model_config = StrictModelConfig
    full_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=254)
    github_url: str | None = Field(default=None, max_length=500)
    summary: str = Field(max_length=600)
    current_title: str | None = Field(default=None, max_length=200)
    skill_labels: list[str] = Field(max_length=50)

class ProfileFieldChange(BaseModel):
    model_config = StrictModelConfig
    field: Literal["full_name", "location", "phone", "email", "github_url", "summary", "current_title"]
    before: str | float | None
    after: str | float | None

class ProfileCollectionDeltas(BaseModel):
    model_config = StrictModelConfig
    experiences: int
    education: int
    languages: int
    certifications: int

class ConfidenceDelta(BaseModel):
    model_config = StrictModelConfig
    before: float = Field(ge=0, le=1)
    after: float = Field(ge=0, le=1)

class ProfileReextractReview(BaseModel):
    model_config = StrictModelConfig
    profile_id: UuidStr
    revision: AwareUtcDatetime
    current: PublicProfileSnapshot
    proposed: PublicProfileSnapshot
    changed_fields: list[ProfileFieldChange] = Field(max_length=24)
    skills_added: list[str] = Field(max_length=50)
    skills_removed: list[str] = Field(max_length=50)
    collection_deltas: ProfileCollectionDeltas
    extraction_confidence: ConfidenceDelta | None
    can_approve: bool
    can_discard: bool

class ProfileReextractReviewReady(BaseModel):
    model_config = StrictModelConfig
    revision: AwareUtcDatetime

class ProfileReextractFailed(BaseModel):
    model_config = StrictModelConfig
    code: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=200)
    draft_available: bool

class ProfileReextractApproveRequest(BaseModel):
    model_config = StrictModelConfig
    revision: AwareUtcDatetime

class ProfileReextractApprovalResponse(BaseModel):
    model_config = StrictModelConfig
    profile_id: UuidStr
    approved: bool
    sync_ok: bool
    warning: SafeWarning | None

class ProfileReextractEvent(BaseModel):
    model_config = StrictModelConfig
    event_id: UuidStr
    operation_id: UuidStr
    profile_id: UuidStr
    timestamp: AwareUtcDatetime
    event: Literal["reextract_progress", "reextract_review_ready", "reextract_failed"]
    payload: ProfileReextractProgress | ProfileReextractReviewReady | ProfileReextractFailed

    @model_validator(mode="after")
    def event_matches_payload(self) -> "ProfileReextractEvent":
        expected = {
            "reextract_progress": ProfileReextractProgress,
            "reextract_review_ready": ProfileReextractReviewReady,
            "reextract_failed": ProfileReextractFailed,
        }[self.event]
        if not isinstance(self.payload, expected):
            raise ValueError("profile re-extract event/payload mismatch")
        return self
```

Use a pure `build_review(current, proposed, profile_id, revision)` helper and tests for scalar changes, skill set changes, collection counts, confidence deltas, bounded output, and absence of `raw_text`, `storage_path`, `source_attachment_id`, `fact_id`, and provider fields.

- [ ] **Step 2: Run the new schema tests and verify missing-contract failure**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_reextraction.py -q
```

Expected: FAIL until the new models, parsers, and projection helper are present.

- [x] **Step 3: Add a generic validated SSE response seam without changing chat event names**

In `backend/app/api/sse.py`, keep `open_sse_response` unchanged for the seven chat events and add:

```py
async def open_typed_sse_response(
    events: AsyncIterator[T],
    *,
    serializer: Callable[[T], bytes],
    error_mapper: StreamErrorMapper,
    error_types: Sequence[type[Exception]],
    headers: Mapping[str, str] | None = None,
) -> EventSourceResponse:
    iterator = events.__aiter__()
    try:
        first = await iterator.__anext__()
    except StopAsyncIteration:
        raise HTTPException(status_code=500, detail={"code": "EMPTY_STREAM", "summary": "Operation produced no events"}) from None
    except Exception as exc:
        if isinstance(exc, tuple(error_types)):
            raise error_mapper(exc) from exc
        raise

    async def produce() -> AsyncIterator[bytes]:
        try:
            yield serializer(first)
            async for event in iterator:
                yield serializer(event)
        finally:
            await _close_async_iterator(iterator)

    return ClosingEventSourceResponse(produce(), headers=dict(headers or {}))
```

The profile event serializer validates the discriminated model, writes `event`, `id`, and compact JSON data, and is unit-tested for split/invalid frames on the existing wire parser. Do not add profile events to the chat `SseEventName` union.

- [x] **Step 4: Implement the direct coordinator using existing extraction/draft/approval owners**

`ProfileReextractionCoordinator.stream(profile_id)` must:

1. check the active ready profile and its retained file without creating a conversation, message, run, tool execution, or title;
2. yield `validating_source`, then `extracting_document`;
3. call `propose_profile_from_cv(..., reprocess=True, target_profile_id=profile_id)` from `profile_drafts.py` rather than duplicating extraction;
4. yield `projecting_profile` and `publishing_review` after the validated result is available;
5. return `reextract_review_ready` containing only the draft revision and profile identity; and
6. yield `reextract_failed` with a stable safe code/summary while preserving approved truth.

Use `asyncio.CancelledError` handling so cancellation before the atomic draft publication exits without a new draft; a disconnect after publication leaves the draft recoverable through GET. The coordinator may emit a progress stage immediately before each existing service boundary; it must not claim a provider substage it cannot observe.

Add `GET` review loading that requires the requested ready profile, verifies `draft.target_profile_id` and `source_attachment_id`, parses the draft with `parse_profile_draft_payload`, loads the approved profile/preferences, and uses `draft.updated_at.isoformat()` as the optimistic revision. Add approve/discard methods that compare the supplied revision and profile owner inside the transaction.

- [x] **Step 5: Make approval and discard revision-safe and enforce the review gate**

Extend `commit_approved_draft` with `expected_draft_updated_at: datetime | None`; `_load_preflight` must reject a changed `ProfileDraft.updated_at` with `PROFILE_REEXTRACT_CONFLICT` in both its read and write sessions. Discard must delete the matching profile draft and `cv_document_drafts` row in one transaction:

```py
async with session_scope(factory) as session:
    draft = await profile_repo.get_current_draft(session)
    if draft is None or draft.target_profile_id != profile_id:
        raise ProfileReextractError("PROFILE_REEXTRACT_DRAFT_NOT_FOUND", "No review is available for this profile")
    if _aware(draft.updated_at) != _aware(expected_revision):
        raise ProfileReextractError("PROFILE_REEXTRACT_CONFLICT", "The review changed; reload it before discarding")
    attachment_id = draft.source_attachment_id
    await profile_repo.delete_current_draft(session)
    if attachment_id is not None:
        await cv_doc_repo.delete_draft(session, attachment_id)
```

Add `assert_profile_review_clear` to `activity_gate.py` and call it from profile activation, profile deletion, CV upload, and profile re-extraction preconditions. It checks only a published current draft for the affected profile and returns `PROFILE_REVIEW_PENDING`; chat correction and explicit approve/discard remain allowed. Add tests proving profile switch, upload, second re-extract, and deletion are blocked until approve/discard.

- [x] **Step 6: Replace the route dependency and remove chat side effects**

Add `ProfileReextractDeps` in `backend/app/api/dependencies.py` containing the existing session factory, attachment storage, document invoker, `SkillNormalizer`, settings, SQLite path, and optional Neo4j driver. Replace `ChatAgentDeps`/`stream_cv_reprocess` in `profiles.py` with the coordinator and add the three review routes. Map errors to 404/409/422/500 with `{code, summary}` only.

Add an integration assertion after POST plus complete stream:

```py
assert count_rows(ChatMessage) == before_messages
assert count_rows(AgentRun) == before_runs
assert count_rows(ToolExecution) == before_tools
assert count_rows(Conversation) == before_conversations
assert (await profile_repo.get_current_draft(session)).target_profile_id == profile_id
```

The stream must contain `reextract_progress`/`reextract_review_ready` or one `reextract_failed`, never `run_started`, `approval_required`, a synthetic user sentence, attachment UUID display text, or a chat conversation id.

- [ ] **Step 7: Run direct re-extraction backend gates**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_reextraction.py tests/unit/test_api_sse.py tests/integration/test_profile_reextraction.py tests/integration/test_profiles_api.py tests/integration/test_profile_selection.py tests/integration/test_cv_api.py tests/integration/test_profile_deletion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/api/sse.py app/api/profiles.py app/api/dependencies.py app/schemas/profile_reextraction.py app/services/profile_reextraction.py app/services/profile_approval.py app/services/activity_gate.py app/services/profile_activation.py app/services/cv_upload.py app/services/profile_deletion.py --no-cache
```

Expected: all selected tests PASS and Ruff exits 0.

- [x] **Step 8: Commit the direct backend lifecycle**

```powershell
Set-Location ..
git add backend/app/api/sse.py backend/app/api/profiles.py backend/app/api/dependencies.py backend/app/schemas/profile_reextraction.py backend/app/schemas/profile.py backend/app/services/profile_reextraction.py backend/app/services/profile_approval.py backend/app/services/activity_gate.py backend/app/services/profile_activation.py backend/app/services/cv_upload.py backend/app/services/profile_deletion.py backend/app/repositories/profiles.py backend/app/repositories/cv_documents.py backend/tests/unit/test_profile_reextraction.py backend/tests/unit/test_api_sse.py backend/tests/integration/test_profile_reextraction.py backend/tests/integration/test_profiles_api.py backend/tests/integration/test_profile_selection.py backend/tests/integration/test_cv_api.py backend/tests/integration/test_profile_deletion.py
git diff --cached --check
git commit -m "feat: make CV re-extraction a direct review workflow"
```

---

### Task 6: Connect direct review UI and make every profile proposal visible

**Files:**

- Modify: `frontend/src/features/cv-manager/types.ts`
- Modify: `frontend/src/features/cv-manager/api.ts`
- Modify: `frontend/src/features/cv-manager/state.ts`
- Modify: `frontend/src/features/cv-manager/CvManagerDrawer.tsx`
- Create: `frontend/src/features/cv-manager/ProfileReextractReview.tsx`
- Modify: `frontend/src/features/profile/ApprovalCard.tsx`
- Modify: `frontend/src/features/profile/copy.ts`
- Modify: `frontend/src/features/profile/api.ts`
- Modify: `frontend/src/features/chat/reducer.ts`
- Modify: `frontend/src/features/chat/ChatPage.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/test/cv-manager-api.test.ts`
- Create: `frontend/src/test/cv-manager-reextract.test.tsx`
- Modify: `frontend/src/test/approval-card.test.tsx`
- Modify: `frontend/src/test/chat-page.test.tsx`
- Modify: `frontend/src/test/sse-reducer.test.ts`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: Write direct-stream, review-diff, and no-synthetic-chat tests**

```tsx
it('renders progress and a recoverable review without touching the chat reducer', async () => {
  const api = createCvManagerApi({
    streamReextract: async (_profileId, handlers) => {
      handlers.onEvent(progress('extracting_document'));
      handlers.onEvent(reviewReady('2026-07-28T10:00:00Z'));
    },
    getReview: vi.fn().mockResolvedValue(reviewFixture()),
  });
  render(<CvManagerDrawer {...props({api, open: true})} />);
  await userEvent.click(screen.getByRole('button', {name: 'Re-extract'}));
  expect(await screen.findByText('Review changes')).toBeInTheDocument();
  expect(screen.getByText('Skills added')).toBeInTheDocument();
  expect(screen.queryByTestId('jobagent-chat-page')).not.toBeInTheDocument();
});

it('keeps approved values until Save review and discards only matching drafts', async () => {
  const api = createCvManagerApi({getReview: vi.fn().mockResolvedValue(reviewFixture())});
  render(<CvManagerDrawer {...props({api, open: true})} />);
  await userEvent.click(screen.getByRole('button', {name: 'Discard review'}));
  expect(api.discardReview).toHaveBeenCalledWith(PROFILE_ID, REVIEW_REVISION);
  expect(screen.getByText('Review discarded')).toBeInTheDocument();
});
```

Update `ApprovalCard` fixture expectations so an initial proposal with `{profile: {summary, current_title, phone, email}, preferences: {...}}` renders those actual values instead of the empty fallback.

- [ ] **Step 2: Run focused frontend tests and verify old chat reprocess wiring fails**

```powershell
Set-Location frontend
npm test -- --run src/test/cv-manager-api.test.ts src/test/cv-manager-reextract.test.tsx src/test/approval-card.test.tsx src/test/chat-page.test.tsx src/test/sse-reducer.test.ts src/app/App.test.tsx
```

Expected: FAIL because `streamProfileReextract` still feeds the chat SSE reducer and `ChatPage` still owns `CvReprocessRequest`.

- [x] **Step 3: Add strict direct event parsing and controller transitions**

Implement `parseProfileReextractEvent` with exact event/payload keys and a feature-specific stream consumer built on the generic wire parser. State transitions are:

```ts
type ReextractPhase = 'idle' | 'loading' | 'review' | 'error';

// progress: phase=loading, preserve prior review only when its revision still matches
// review_ready: GET the durable review before phase=review
// failed: phase=error, preserve approved profile and expose Retry/Discard as server allows
```

Every mutation carries `{profileId, revision}` and ignores late responses after profile scope changes. Approve success calls `workspace.reload`, invalidates Saved Jobs/tailoring through existing App callbacks, and closes the drawer. Discard success closes only the review. A stream disconnect calls `getReview` before reporting failure; it never marks approval complete from a missing terminal event.

- [x] **Step 4: Remove the old reprocess chat path and wire Edit Profile Information**

Delete `CvReprocessRequest`, `CvReprocessTerminal`, `CV_REPROCESS_TURN_MESSAGE`, `onCvReprocess`, and `onCvReprocessTerminal` from `App.tsx`, `CvSidebar.tsx`, `ChatPage.tsx`, and their tests. `CvSidebar` opens the CV Manager drawer for the selected profile. `TailoringEditor`'s `onEditProfile` callback must call `openCvManager({profileId, startAt: 'reextract'})`, leaving the tailored workspace state intact until the user explicitly returns.

Keep the sidebar upload's initial profile bootstrap/chat approval path unchanged; only the later active/archived re-extraction path becomes direct.

- [ ] **Step 5: Make review accessible and verify state preservation**

Use Astryx `AlertDialog`, `Disclosure`, `Banner`, `Button`, and `Text` with an accessible name, focus restoration, Escape behavior, live region for progress/error, and disabled reasons. Each changed field has a stable `id` and the summary/error has `aria-describedby`. Add keyboard tests for Save, Discard, Retry, Escape, and focus return to **Manage CVs**.

```powershell
npx astryx component AlertDialog
npx astryx component Disclosure
npm test -- --run src/test/cv-manager-reextract.test.tsx src/test/approval-card.test.tsx src/app/App.test.tsx
npm run typecheck
```

Expected: all selected tests PASS and typecheck exits 0.

- [x] **Step 6: Commit the direct review UI**

```powershell
Set-Location ..
git add frontend/src/features/cv-manager frontend/src/features/profile/ApprovalCard.tsx frontend/src/features/profile/copy.ts frontend/src/features/profile/api.ts frontend/src/features/chat/reducer.ts frontend/src/features/chat/ChatPage.tsx frontend/src/app/App.tsx frontend/src/features/profile/CvSidebar.tsx frontend/src/test/cv-manager-api.test.ts frontend/src/test/cv-manager-reextract.test.tsx frontend/src/test/approval-card.test.tsx frontend/src/test/chat-page.test.tsx frontend/src/test/sse-reducer.test.ts frontend/src/app/App.test.tsx
git diff --cached --check
git commit -m "feat: review CV extraction outside chat"

---

### Task 7: Make later tailoring no-ops terminal successes with no artifacts

**Files:**

- Modify: `backend/app/schemas/cv_tailoring.py`
- Modify: `backend/app/schemas/sse.py`
- Modify: `backend/app/services/cv_tailoring.py`
- Modify: `backend/app/tools/cv_tailoring.py`
- Modify: `backend/app/repositories/cv_tailoring.py`
- Modify: `backend/app/api/cv_tailoring.py`
- Modify: `backend/tests/integration/test_cv_tailoring_coordinator.py`
- Modify: `backend/tests/integration/test_cv_tailoring_api.py`
- Modify: `backend/tests/unit/test_cv_tailoring_schemas.py`

- [x] **Step 1: Add failing equality/outcome tests before changing generation**

Extend `test_later_ai_and_manual_versions_form_one_immutable_parent_chain` with the unchanged-content cases:

```py
async def test_later_manual_no_change_does_not_compile_or_insert(
    coordinator, latest, compiler, storage, repository_spy
) -> None:
    result = await coordinator.create_manual_version(
        session_id=latest.session_id,
        parent_version_id=latest.id,
        content=parse_tailored_content(latest.content_json),
    )
    assert result.outcome == "no_change"
    assert result.version_id == latest.id
    assert result.version_number == latest.version_number
    assert compiler.calls == []
    assert storage.promotions == []
    assert repository_spy.version_inserts == 0

async def test_later_ai_no_change_completes_run_without_version_or_timestamp_change(
    coordinator, latest, fake_invoker, compiler, session_factory
) -> None:
    before = await session_snapshot(session_factory, latest.session_id)
    launch = await coordinator.prepare_ai_version(
        session_id=latest.session_id,
        parent_version_id=latest.id,
        instruction="Make the summary stronger",
        target_section_ids=["summary"],
    )
    fake_invoker.return_parent_content = True
    events = [event async for event in coordinator.stream_initial_version(launch)]
    after = await session_snapshot(session_factory, latest.session_id)
    assert events[-1].payload.outcome == "no_change"
    assert after.latest_version_number == before.latest_version_number
    assert after.updated_at == before.updated_at
    assert compiler.calls == []
```

Retain the initial-generation test and assert Version 1 is still created when its content equals the baseline.

- [ ] **Step 2: Run the tailoring coordinator tests and confirm the old version-creation behavior fails**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_api.py tests/unit/test_cv_tailoring_schemas.py -q
```

Expected: FAIL because manual and AI later mutations currently always render/promote/CAS a new version and terminal completion has no outcome.

- [x] **Step 3: Define a single canonical content comparison and typed response**

Add to `cv_tailoring.py`:

```py
TailoringMutationOutcome = Literal["version_created", "no_change"]

class TailoringVersionMutationResponse(BaseModel):
    model_config = StrictModelConfig
    outcome: TailoringMutationOutcome
    session_id: UuidStr
    version_id: UuidStr
    version_number: int = Field(ge=1)
    currentness: Literal["current"] = "current"

    @model_validator(mode="after")
    def identity_is_present(self) -> "TailoringVersionMutationResponse":
        if not self.version_id or self.version_number < 1:
            raise ValueError("no-op must return its unchanged parent identity")
        return self

def canonical_tailored_content(content: TailoredCVContent) -> dict[str, Any]:
    return content.model_dump(mode="json", exclude_none=False)

def tailored_content_equal(left: TailoredCVContent, right: TailoredCVContent) -> bool:
    return canonical_tailored_content(left) == canonical_tailored_content(right)
```

Use this helper after patch/guard validation and before `create_staging_dir`, compiler invocation, storage promotion, or `create_version_cas`. Keep renderer bytes, timestamps, provenance ordering, and IDs out of equality.

Replace the old `TailoringVersionCreateResponse` return type at the manual route, coordinator `get_completed_version`, and `build_create_tailored_cv_tool` result projection with `TailoringVersionMutationResponse`; Version 1 still returns `outcome="version_created"` and later unchanged calls return `outcome="no_change"` with the parent identity.

- [x] **Step 4: Add no-change repository transitions and wire manual/AI paths**

Add `complete_no_change(session, session_id, expected_latest_version_number)` that updates `state='ready'` and clears `error_code` without touching `updated_at`. For later AI preparation, do not touch `updated_at` when marking generating; a real version CAS still sets it. For manual mutations, compare before marking generating. Return the unchanged parent in the typed response. For initial generation (`expected_latest_version_number == 0`), always invoke `_render_promote_commit`.

Extend `RunCompletedPayload` with optional, strictly coupled tailoring fields:

```py
class RunCompletedPayload(BaseModel):
    model_config = StrictModelConfig
    state: Literal["completed"] = "completed"
    outcome: Literal["version_created", "no_change"] | None = None
    version_id: UuidStr | None = None
    version_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def terminal_identity(self) -> "RunCompletedPayload":
        if self.outcome is None and (self.version_id is not None or self.version_number is not None):
            raise ValueError("tailoring identity requires an outcome")
        if self.outcome is not None and (self.version_id is None or self.version_number is None):
            raise ValueError("tailoring outcome requires version identity")
        return self
```

Chat completion events continue to contain only `{"state":"completed"}`. Update `get_completed_version` to return the completed run's latest version, which is the parent for `no_change`.

- [ ] **Step 5: Add API and persistence recovery assertions**

Update `POST /cv-tailoring/sessions/{id}/versions` to use the new response model. Assert a disconnected AI stream can recover by fetching session detail and comparing the known parent ID with the unchanged latest version; no new no-op database column is permitted.

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_api.py tests/unit/test_cv_tailoring_schemas.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/schemas/cv_tailoring.py app/schemas/sse.py app/services/cv_tailoring.py app/repositories/cv_tailoring.py app/api/cv_tailoring.py --no-cache
```

Expected: PASS; compiler/storage/version spies remain untouched for later no-op cases.

- [x] **Step 6: Commit the backend no-op contract**

```powershell
Set-Location ..
git add backend/app/schemas/cv_tailoring.py backend/app/schemas/sse.py backend/app/services/cv_tailoring.py backend/app/tools/cv_tailoring.py backend/app/repositories/cv_tailoring.py backend/app/api/cv_tailoring.py backend/tests/integration/test_cv_tailoring_coordinator.py backend/tests/integration/test_cv_tailoring_api.py backend/tests/unit/test_cv_tailoring_schemas.py
git diff --cached --check
git commit -m "fix: make unchanged tailoring mutations no-ops"
```

---

### Task 8: Project tailoring no-op outcomes through the frontend

**Files:**

- Modify: `frontend/src/features/cv-tailoring/types.ts`
- Modify: `frontend/src/features/cv-tailoring/api.ts`
- Modify: `frontend/src/features/cv-tailoring/state.ts`
- Modify: `frontend/src/features/cv-tailoring/TailoringEditor.tsx`
- Create: `frontend/src/features/cv-tailoring/copy.ts`
- Modify: `frontend/src/features/chat/types.ts`
- Modify: `frontend/src/lib/sse/parser.ts`
- Modify: `frontend/src/lib/sse/stream.ts`
- Modify: `frontend/src/test/cv-tailoring-api.test.ts`
- Modify: `frontend/src/test/cv-tailoring-state.test.tsx`
- Modify: `frontend/src/test/cv-tailoring-editor.test.tsx`
- Modify: `frontend/src/test/sse-reducer.test.ts`

- [x] **Step 1: Write strict parser/state tests for both outcomes**

```tsx
it('parses a manual no_change response and exposes the unchanged parent', async () => {
  const response = await parseTailoringMutationResponse({
    outcome: 'no_change',
    session_id: SESSION_ID,
    version_id: PARENT_VERSION_ID,
    version_number: 2,
    currentness: 'current',
  });
  expect(response.outcome).toBe('no_change');
  expect(response.version_id).toBe(PARENT_VERSION_ID);
});

it('renders the no-change message and does not append a version row', async () => {
  const controller = renderTailoringController({manualOutcome: noChangeResponse()});
  await act(() => controller.result.current.saveDraft());
  expect(controller.result.current.state.sessions.data?.items[0].latest_version_number).toBe(2);
  expect(controller.result.current.state.stream.error).toBeNull();
  expect(screen.getByText('There are no changes to save.')).toBeInTheDocument();
});

it('recovers a disconnected no-op by matching the known parent to durable detail', async () => {
  const controller = renderTailoringController({stream: 'disconnect', detail: detailWithParentVersion()});
  await act(() => controller.result.current.saveAiEdit());
  expect(controller.result.current.state.lastOutcome).toBe('no_change');
});
```

- [ ] **Step 2: Run focused frontend tests and verify parser failures**

```powershell
Set-Location frontend
npm test -- --run src/test/cv-tailoring-api.test.ts src/test/cv-tailoring-state.test.tsx src/test/cv-tailoring-editor.test.tsx src/test/sse-reducer.test.ts
```

Expected: FAIL because the exact parsers reject `outcome` and state has no no-op projection.

- [x] **Step 3: Extend strict types and the generic SSE parser**

Add `TailoringMutationOutcome`, `TailoringVersionMutationResponse`, and `lastOutcome` to the tailoring state. Extend `CreateTailoredCvResultData` with the same required `outcome` field so chat-created Version 1 is projected as `version_created`. Make `frameToEvent` remain the chat adapter while `consumeSseResponse` accepts an optional `parseFrame` callback; add `consumeTypedSseResponse<T>` for tailoring/direct profile events. Its terminal detector is supplied by the caller, so profile re-extract does not become a chat run.

The tailoring parser accepts `run_completed` with optional outcome/identity and rejects an identity without an outcome. It accepts `run_failed.issues` only after Task 9 adds that exact safe projection.

- [x] **Step 4: Implement no-op state transitions and copy**

Use feature-local constants:

```ts
export const TAILORING_COPY = {
  noChangeAi: 'AI found no source-supported changes to apply.',
  noChangeManual: 'There are no changes to save.',
  previewPdf: 'Preview PDF',
  downloadPdf: 'Download PDF',
  downloadLatex: 'Download LaTeX source',
} as const;
```

On `no_change`, keep the selected detail/version/draft, clear the mutation error, set `lastOutcome`, and do not alter the session list's latest version. On `version_created`, retain current behavior. On disconnect, fetch detail and classify no-change only when the known parent ID/number is still the durable selected version and the latest run is completed; otherwise keep the existing disconnected recovery state.

- [ ] **Step 5: Verify UI and transport behavior**

```powershell
npm test -- --run src/test/cv-tailoring-api.test.ts src/test/cv-tailoring-state.test.tsx src/test/cv-tailoring-editor.test.tsx src/test/sse-reducer.test.ts
npm run typecheck
```

Expected: PASS and typecheck exits 0. Add a static assertion that no `no_change` path calls `compile`, `promote`, or `create_version` mocks.

- [x] **Step 6: Commit frontend no-op handling**

```powershell
Set-Location ..
git add frontend/src/features/cv-tailoring frontend/src/features/chat/types.ts frontend/src/lib/sse/parser.ts frontend/src/lib/sse/stream.ts frontend/src/test/cv-tailoring-api.test.ts frontend/src/test/cv-tailoring-state.test.tsx frontend/src/test/cv-tailoring-editor.test.tsx frontend/src/test/sse-reducer.test.ts
git diff --cached --check
git commit -m "feat: show tailoring no-op outcomes"
```

---

### Task 9: Map and durably recover safe grounding issues

**Files:**

- Create: `backend/app/services/tailoring_issue_projection.py`
- Modify: `backend/app/agent/tailoring_graph.py`
- Modify: `backend/app/services/cv_tailoring.py`
- Modify: `backend/app/services/cv_tailoring_guard.py`
- Modify: `backend/app/services/agent_activity.py`
- Modify: `backend/app/repositories/agent_activities.py`
- Modify: `backend/app/schemas/cv_tailoring.py`
- Modify: `backend/app/schemas/sse.py`
- Modify: `backend/app/api/cv_tailoring.py`
- Test: `backend/tests/unit/test_tailoring_issue_projection.py`
- Modify: `backend/tests/unit/test_cv_tailoring_guard.py`
- Modify: `backend/tests/unit/test_cv_tailoring_agent.py`
- Modify: `backend/tests/integration/test_cv_tailoring_coordinator.py`
- Modify: `backend/tests/integration/test_cv_tailoring_api.py`

- [x] **Step 1: Write pure mapping/privacy tests**

Define the backend response model before writing the tests:

```py
class TailoringUserIssue(BaseModel):
    model_config = StrictModelConfig
    section_id: str = Field(min_length=1, max_length=120)
    section_heading: str = Field(min_length=1, max_length=200)
    item_index: int | None = Field(default=None, ge=0, le=30)
    field: Literal["title", "subtitle", "date", "location", "body", "bullet", "attribute", "section"]
    reason: Literal["not_in_source", "belongs_to_another_section", "structure_changed", "required_source_missing", "unsupported_value"]
```

```py
def test_maps_internal_issue_to_bounded_user_issue() -> None:
    issue = GroundingIssue(code="CROSS_SECTION_FACT", path="sections[1].items[0].body")
    projected = project_grounding_issues(issue_list=[issue], parent=_content())
    assert projected == [TailoringUserIssue(
        section_id="experience", section_heading="Experience", item_index=0,
        field="body", reason="belongs_to_another_section",
    )]

def test_unknown_path_collapses_to_one_generic_section_issue() -> None:
    projected = project_grounding_issues(
        issue_list=[GroundingIssue(code="UNKNOWN_FACT", path="provider.secret[99]")],
        parent=_content(),
    )
    assert len(projected) == 1
    assert projected[0].field == "section"
    assert "provider.secret" not in projected[0].model_dump_json()

def test_durable_activity_codec_round_trips_only_allowlisted_identity() -> None:
    key = encode_internal_issue(GroundingIssue(code="EMPTY_PROVENANCE", path="sections[0].items[2].bullets[1]"))
    assert decode_internal_issue(key) == GroundingIssue(code="EMPTY_PROVENANCE", path="sections[0].items[2].bullets[1]")
```

- [ ] **Step 2: Run mapping tests and verify missing safe projection**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_tailoring_issue_projection.py tests/unit/test_cv_tailoring_guard.py -q
```

Expected: FAIL because raw issues are currently discarded and no user projection exists.

- [x] **Step 3: Implement bounded issue mapping and existing-activity persistence**

Map only the seven allowlisted internal codes and parse paths matching `sections[n]`, optional `items[n]`, and known field suffixes. Cap output at ten issues; deduplicate by `(section_id, item_index, field, reason)`. Unknown code/path returns one generic section issue. Never include rejected text, fact IDs, provider output, prompt, or raw path in the returned model.

Persist internal identity through the existing `AgentActivity` columns so no migration is introduced:

```py
# ponytail: the existing activity row is the approved durable seam for bounded
# grounding identity; move to a dedicated JSON column only if a future schema
# migration is explicitly approved.
technical_name = encode_internal_issue(issue)  # server-only, allowlisted path
error_code = issue.code
label = "Source support check"
```

Add `record_grounding_issues(run_id, issues)` that creates at most ten terminal assistant activities. The API decodes only this prefix and maps it before returning `TailoringUserIssue`; it sets `technical_name`, `error_code`, and raw activity labels to `null` in the public tailoring detail projection. Existing normal activity rows retain their current behavior.

- [x] **Step 4: Preserve issues through AI/manual coordinator failures**

Extend `TailoringError` with `issues: tuple[GroundingIssue, ...]`. When the graph returns `result["issues"]`, parse each strict `GroundingIssue`, pass them to `_fail_generation`, and record them before checkpoint cleanup. Manual guard failures pass the same tuple to the HTTP error projection. Unknown exceptions still map to one generic issue.

Extend the tailoring-only terminal payload and detail response:

```py
class TailoringRunSummary(BaseModel):
    # existing fields...
    issues: list[TailoringUserIssue] = Field(default_factory=list, max_length=10)

class RunFailedPayload(BaseModel):
    # existing fields...
    issues: list[TailoringUserIssue] | None = Field(default=None, max_length=10)
```

Chat failures continue to omit `issues`; a tailoring failure includes only the safe projection.

- [ ] **Step 5: Verify disconnect/detail/API privacy recovery**

Add integration assertions that after an AI grounding failure and stream disconnect, `GET /cv-tailoring/sessions/{id}` returns the same safe `issues`, while `technical_name`, raw error paths, source text, fact IDs, and provider payloads are absent. Verify manual HTTP errors return the same `issues` shape and preserve the local draft.

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_tailoring_issue_projection.py tests/unit/test_cv_tailoring_guard.py tests/integration/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/services/tailoring_issue_projection.py app/services/cv_tailoring.py app/services/agent_activity.py app/repositories/agent_activities.py app/schemas/cv_tailoring.py app/schemas/sse.py app/api/cv_tailoring.py --no-cache
```

Expected: PASS; no migration file is created.

- [x] **Step 6: Commit safe grounding recovery**

```powershell
Set-Location ..
git add backend/app/services/tailoring_issue_projection.py backend/app/agent/tailoring_graph.py backend/app/services/cv_tailoring.py backend/app/services/cv_tailoring_guard.py backend/app/services/agent_activity.py backend/app/repositories/agent_activities.py backend/app/schemas/cv_tailoring.py backend/app/schemas/sse.py backend/app/api/cv_tailoring.py backend/tests/unit/test_tailoring_issue_projection.py backend/tests/unit/test_cv_tailoring_guard.py backend/tests/unit/test_cv_tailoring_agent.py backend/tests/integration/test_cv_tailoring_coordinator.py backend/tests/integration/test_cv_tailoring_api.py
git diff --cached --check
git commit -m "feat: project safe tailoring grounding issues"
```

---

### Task 10: Add field-level grounding recovery to the editor

**Files:**

- Modify: `frontend/src/features/cv-tailoring/types.ts`
- Modify: `frontend/src/features/cv-tailoring/state.ts`
- Modify: `frontend/src/features/cv-tailoring/TailoringEditor.tsx`
- Modify: `frontend/src/features/cv-tailoring/TailoredSectionEditor.tsx`
- Modify: `frontend/src/features/cv-tailoring/copy.ts`
- Modify: `frontend/src/test/cv-tailoring-state.test.tsx`
- Modify: `frontend/src/test/cv-tailoring-editor.test.tsx`
- Modify: `frontend/src/test/cv-tailoring-accessibility.test.tsx`

- [x] **Step 1: Write issue parsing and recovery tests**

```tsx
it('focuses the field, opens source evidence, and connects the issue with aria-describedby', async () => {
  render(<TailoringEditor {...props({issues: [bodyIssue()]})} />);
  const field = screen.getByRole('textbox', {name: 'Experience body'});
  expect(field).toHaveAttribute('aria-describedby', expect.stringContaining('tailoring-issue'));
  await userEvent.click(screen.getByRole('button', {name: 'View source'}));
  expect(screen.getByRole('region', {name: 'Experience source evidence'})).toHaveFocus();
});

it('Undo change restores the selected parent item without changing unrelated sections', async () => {
  const controller = renderTailoringEditor({draft: editedContent(), parent: parentContent(), issues: [bodyIssue()]});
  await userEvent.click(screen.getByRole('button', {name: 'Undo change'}));
  expect(controller.draft.sections[1].items[0].body).toEqual(parentContent().sections[1].items[0].body);
});

it('Try again preserves the previous instruction but does not submit automatically', async () => {
  const onRetry = vi.fn();
  render(<TailoringEditor {...props({issues: [bodyIssue()], onRetry})} />);
  await userEvent.click(screen.getByRole('button', {name: 'Try again'}));
  expect(onRetry).toHaveBeenCalledWith('Prioritize source-supported experience');
  expect(api.streamAiVersion).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run editor tests and verify the current generic error behavior fails**

```powershell
Set-Location frontend
npm test -- --run src/test/cv-tailoring-state.test.tsx src/test/cv-tailoring-editor.test.tsx src/test/cv-tailoring-accessibility.test.tsx
```

Expected: FAIL because state stores only `TailoringSafeError` and the editor has no issue bindings/recovery actions.

- [x] **Step 3: Add strict issue types and state ownership**

Mirror the backend allowlist exactly in `types.ts`; parse at most ten issues and reject extra keys. Store issues with the stream/detail error, but keep the local draft and selected parent unchanged on failure. Add state callbacks:

```ts
undoIssue(issue: TailoringUserIssue): void;
focusIssue(issue: TailoringUserIssue): void;
retryIssue(issue: TailoringUserIssue): void;
```

`undoIssue` copies only the addressed parent field/item. `focusIssue` sets a pending focus target consumed by the editor after render. `retryIssue` opens the existing scoped AI dialog with the prior instruction and never calls the API until the user confirms.

- [x] **Step 4: Render safe issue cards and accessible field links**

Create stable field IDs from section ID/item index/field using the already parsed safe values. Pass `issueIds` into `TailoredSectionEditor`, render an English reason from `copy.ts`, and attach `aria-describedby`. Use `View source`, `Undo change`, and `Try again` buttons with visible labels/tooltips and live-region announcements. Do not show internal code/path or rejected text.

- [ ] **Step 5: Verify all recovery actions and static accessibility rules**

```powershell
npm test -- --run src/test/cv-tailoring-state.test.tsx src/test/cv-tailoring-editor.test.tsx src/test/cv-tailoring-accessibility.test.tsx
npm run lint
npm run typecheck
```

Expected: PASS. The accessibility test must also assert no nested buttons, icon-only controls have labels, and reduced-motion CSS remains enabled.

- [x] **Step 6: Commit editor recovery**

```powershell
Set-Location ..
git add frontend/src/features/cv-tailoring/types.ts frontend/src/features/cv-tailoring/state.ts frontend/src/features/cv-tailoring/TailoringEditor.tsx frontend/src/features/cv-tailoring/TailoredSectionEditor.tsx frontend/src/features/cv-tailoring/copy.ts frontend/src/test/cv-tailoring-state.test.tsx frontend/src/test/cv-tailoring-editor.test.tsx frontend/src/test/cv-tailoring-accessibility.test.tsx
git diff --cached --check
git commit -m "feat: add grounded tailoring recovery actions"

---

### Task 11: Suppress redundant renderer headings while preserving real titles

**Files:**

- Modify: `backend/app/services/cv_tailoring_renderer.py`
- Modify: `backend/tests/unit/test_cv_tailoring_renderer.py`
- Modify: `backend/tests/integration/test_cv_tailoring_compiler.py`

- [x] **Step 1: Write renderer and real-PDF assertions**

```py
def test_item_title_equal_to_section_heading_is_omitted_case_and_unicode_insensitive() -> None:
    content = _content(
        sections=[
            _section(
                heading="TECHNICAL SKILLS",
                kind="skills",
                items=[_item(title="  technical\u00a0skills ", body="Python")],
            )
        ]
    )
    tex = render_latex_cv(content)
    assert "technical\\u00a0skills" not in tex.lower()
    assert "Python" in tex

def test_genuine_item_title_is_retained() -> None:
    tex = render_latex_cv(_content(sections=[_section(
        heading="PROJECTS", kind="projects", items=[_item(title="Resume parser", body="Built parser")]
    )]))
    assert "Resume parser" in tex
```

Extend the real `pdflatex` integration fixture to include SUMMARY, EDUCATION, TECHNICAL SKILLS, and PROJECTS, extract PDF text with `pypdf.PdfReader`, and assert each section heading occurs once while `Resume parser` occurs once. Keep the existing skip when `pdflatex` is unavailable.

- [ ] **Step 2: Run renderer tests and verify duplicate headings remain**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_renderer.py tests/integration/test_cv_tailoring_compiler.py -q
```

Expected: FAIL because every item renderer currently emits its title unconditionally.

- [x] **Step 3: Implement one comparison-only normalizer at the renderer seam**

```py
import unicodedata

def _comparison_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.casefold().split())

def _display_item_title(item: TailoredItem, section_heading: str) -> SourceBoundText | None:
    title = item.title
    if title is None or _comparison_text(title.text) == _comparison_text(section_heading):
        return None
    return title
```

Pass `section.heading` into `_render_simple_item`, `_render_compact_item`, and `_render_generic_item`. Omit only the presentation title; retain `content_json`, provenance, source IDs, and all other fields unchanged. Do not use this helper for job/project/certificate titles that do not equal the containing heading.

- [ ] **Step 4: Verify and commit renderer behavior**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_renderer.py tests/integration/test_cv_tailoring_compiler.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/services/cv_tailoring_renderer.py tests/unit/test_cv_tailoring_renderer.py --no-cache
Set-Location ..
git add backend/app/services/cv_tailoring_renderer.py backend/tests/unit/test_cv_tailoring_renderer.py backend/tests/integration/test_cv_tailoring_compiler.py
git diff --cached --check
git commit -m "fix: avoid repeated CV section headings"
```

Expected: tests PASS; compiler test may be skipped only for absent TeX.

---

### Task 12: Separate PDF preview from authenticated blob downloads

**Files:**

- Create: `frontend/src/lib/api/download.ts`
- Modify: `frontend/src/features/cv-tailoring/api.ts`
- Modify: `frontend/src/features/cv-tailoring/TailoringPdfPreview.tsx`
- Modify: `frontend/src/features/cv-tailoring/TailoringVersionActions.tsx`
- Modify: `frontend/src/features/cv-tailoring/copy.ts`
- Modify: `frontend/src/test/cv-tailoring-api.test.ts`
- Modify: `frontend/src/test/cv-tailoring-editor.test.tsx`
- Create: `frontend/src/test/artifact-download.test.ts`

- [x] **Step 1: Write navigation/download isolation tests**

```ts
it('uses a new tab only for PDF preview', async () => {
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  render(<TailoringVersionActions {...props({pdfAvailable: true, sourceAvailable: true})} />);
  await userEvent.click(screen.getByRole('button', {name: 'Preview PDF'}));
  expect(open).toHaveBeenCalledWith(expect.stringContaining('/pdf'), '_blank', 'noopener,noreferrer');
  expect(window.location.href).not.toContain('/pdf');
});

it('downloads PDF and LaTeX through blob URLs without changing the JobAgent location', async () => {
  const click = vi.fn();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Blob(['x']), {status: 200})));
  vi.spyOn(document, 'createElement').mockReturnValue({click, set href(_: string) {}, set download(_: string) {}, remove() {}} as unknown as HTMLElement);
  await downloadArtifact('http://api.test/pdf', 'resume.pdf');
  await downloadArtifact('http://api.test/source', 'resume.tex');
  expect(click).toHaveBeenCalledTimes(2);
});

it('keeps the editor open and shows a safe error when an artifact fetch fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', {status: 503})));
  render(<TailoringVersionActions {...props({pdfAvailable: true})} />);
  await userEvent.click(screen.getByRole('button', {name: 'Download PDF'}));
  expect(await screen.findByText('The PDF could not be downloaded.')).toBeInTheDocument();
  expect(screen.getByTestId('jobagent-tailoring-editor')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run artifact tests and verify direct-link navigation fails the new contract**

```powershell
Set-Location frontend
npm test -- --run src/test/artifact-download.test.ts src/test/cv-tailoring-api.test.ts src/test/cv-tailoring-editor.test.tsx
```

Expected: FAIL because `.tex` is currently a normal anchor and PDF actions do not share a blob helper.

- [x] **Step 3: Implement the bounded download helper**

```ts
import {parseErrorBody} from './chat';

export async function downloadArtifact(url: string, filename: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(url, {method: 'GET', headers: {Accept: 'application/octet-stream'}, signal});
  if (!response.ok) throw parseErrorBody(response.status, await response.text());
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export function safeArtifactName(label: string, extension: 'pdf' | 'tex'): string {
  const base = label.normalize('NFKC').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || 'tailored-cv';
  return `${base}.${extension}`;
}
```

Keep the iframe on the inline PDF URL for embedded preview, use `window.open` only for **Preview PDF**, and use `downloadArtifact` for **Download PDF** and **Advanced → Download LaTeX source**. Show a feature-local English error and leave `window.location` untouched.

- [ ] **Step 4: Verify and commit artifact delivery**

```powershell
npm test -- --run src/test/artifact-download.test.ts src/test/cv-tailoring-api.test.ts src/test/cv-tailoring-editor.test.tsx
npm run typecheck
Set-Location ..
git add frontend/src/lib/api/download.ts frontend/src/features/cv-tailoring/api.ts frontend/src/features/cv-tailoring/TailoringPdfPreview.tsx frontend/src/features/cv-tailoring/TailoringVersionActions.tsx frontend/src/features/cv-tailoring/copy.ts frontend/src/test/artifact-download.test.ts frontend/src/test/cv-tailoring-api.test.ts frontend/src/test/cv-tailoring-editor.test.tsx
git diff --cached --check
git commit -m "fix: keep CV artifact downloads inside JobAgent"
```

---

### Task 13: Make the tailored editor layout and sidebar transitions coherent

**Files:**

- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/features/navigation/ProductSidebar.tsx`
- Modify: `frontend/src/features/cv-tailoring/TailoringEditor.tsx`
- Modify: `frontend/src/features/cv-tailoring/TailoringPdfPreview.tsx`
- Modify: `frontend/src/features/cv-tailoring/cv-tailoring.css`
- Modify: `frontend/src/features/profile/CvSidebar.tsx`
- Modify: `frontend/src/test/cv-tailoring-editor.test.tsx`
- Modify: `frontend/src/test/cv-tailoring-accessibility.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: Write desktop/narrow/sidebar restoration tests**

```tsx
it('reduces the secondary sidebar to the rail while the editor is active and restores the prior destination', async () => {
  render(<App deps={deps} />);
  await userEvent.click(screen.getByRole('button', {name: 'Saved Jobs'}));
  await userEvent.click(screen.getByRole('button', {name: 'Create tailored CV'}));
  expect(screen.getByTestId('jobagent-product-sidebar')).toHaveAttribute('data-editor-mode', 'true');
  await userEvent.click(screen.getByRole('button', {name: 'Back to chat'}));
  expect(screen.getByTestId('jobagent-product-sidebar')).toHaveAttribute('data-selected-destination', 'saved-jobs');
});

it('uses Content and Preview tabs on a narrow viewport with one scroll owner per pane', async () => {
  installMatchMedia(false);
  render(<TailoringEditor {...props()} />);
  expect(screen.getByRole('tab', {name: 'Content'})).toHaveAttribute('aria-selected', 'true');
  await userEvent.click(screen.getByRole('tab', {name: 'Preview'}));
  expect(screen.getByRole('tabpanel', {name: 'Preview'})).toBeVisible();
  expect(document.querySelectorAll('[data-scroll-owner="viewport"]')).toHaveLength(2);
});
```

- [ ] **Step 2: Run layout tests and verify the current persistent-column behavior fails**

```powershell
Set-Location frontend
npm test -- --run src/test/cv-tailoring-editor.test.tsx src/test/cv-tailoring-accessibility.test.tsx src/app/App.test.tsx
```

Expected: FAIL for rail restoration/context header/scroll ownership assertions.

- [x] **Step 3: Implement one editor context header and two-pane scroll contract**

Move session label, currentness, version, actions, and context into the editor header. Desktop renders one content pane and one PDF pane; only each pane may scroll. Narrow view renders Astryx tabs named **Content** and **Preview** and mounts one visible pane at a time. Use `Stack`, `StackItem`, `Tabs`, and tokenized CSS; do not add raw layout `<div>`, raw hex, or raw CSS pixel declarations.

- [x] **Step 4: Preserve sidebar collapse/selection state through editor mode**

`ProductSidebar` stores the previous selected destination/collapse state in a ref when `editorMode` becomes true, exposes the rail only, and restores the ref when returning to chat/list. `App` passes `editorMode={mainWorkspace.kind === 'cv-tailoring'}` and an `onOpenCvManager` callback. `TailoringEditor` **Edit Profile Information** invokes that callback instead of focusing the chat composer.

- [ ] **Step 5: Run Astryx/a11y gates and commit**

```powershell
npx astryx docs layout
npx astryx docs tokens
npm test -- --run src/test/cv-tailoring-editor.test.tsx src/test/cv-tailoring-accessibility.test.tsx src/app/App.test.tsx
npm run lint
npm run typecheck
Set-Location ..
git add frontend/src/app/App.tsx frontend/src/features/navigation/ProductSidebar.tsx frontend/src/features/cv-tailoring/TailoringEditor.tsx frontend/src/features/cv-tailoring/TailoringPdfPreview.tsx frontend/src/features/cv-tailoring/cv-tailoring.css frontend/src/features/profile/CvSidebar.tsx frontend/src/test/cv-tailoring-editor.test.tsx frontend/src/test/cv-tailoring-accessibility.test.tsx frontend/src/app/App.test.tsx
git diff --cached --check
git commit -m "fix: align tailored editor layout and navigation"
```

---

### Task 14: Create one backend-owned Saved Job and tailoring-session label

**Files:**

- Create: `backend/app/services/job_display.py`
- Modify: `backend/app/schemas/job_evaluations.py`
- Modify: `backend/app/schemas/matching.py`
- Modify: `backend/app/services/saved_jobs.py`
- Modify: `backend/app/services/match_scoring.py`
- Modify: `backend/app/schemas/cv_tailoring.py`
- Modify: `backend/app/services/cv_tailoring.py`
- Test: `backend/tests/unit/test_job_display.py`
- Modify: `backend/tests/integration/test_saved_jobs_api.py`
- Modify: `backend/tests/unit/test_match_components.py`
- Modify: `backend/tests/unit/test_cv_tailoring_schemas.py`
- Modify: `backend/tests/integration/test_cv_tailoring_api.py`
- Modify: `backend/tests/integration/test_cv_tailoring_repository.py`

- [ ] **Step 1: Write pure display-label tests**

```py
def test_saved_job_label_prefers_title_and_company() -> None:
    assert derive_saved_job_display_label(title="Backend Engineer", company="Acme", summary="ignored", saved_at=NOW) == "Backend Engineer · Acme"

def test_saved_job_label_uses_first_summary_sentence_then_date() -> None:
    assert derive_saved_job_display_label(title=None, company=None, summary="Build APIs. Second sentence.", saved_at=NOW) == "Build APIs"
    assert derive_saved_job_display_label(title=None, company=None, summary="   ", saved_at=datetime(2026, 7, 28, tzinfo=UTC)) == "Untitled saved job · 2026-07-28"
```

Add API assertions that list, detail, evaluate, re-extract, and delete projections carry the same `display_label`, and that no UUID prefix appears when title/company/summary are absent.

- [ ] **Step 2: Run label tests and verify missing DTO fields**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_display.py tests/integration/test_saved_jobs_api.py tests/unit/test_match_components.py -q
```

Expected: FAIL because `display_label` is not in the strict saved-job or match contracts.

- [ ] **Step 3: Implement the pure label helper and Saved Job projection**

```py
def derive_saved_job_display_label(*, title: str | None, company: str | None, summary: str | None, saved_at: datetime) -> str:
    clean_title = _clean(title)
    clean_company = _clean(company)
    if clean_title and clean_company:
        return f"{clean_title} · {clean_company}"
    if clean_title or clean_company:
        return clean_title or clean_company  # type: ignore[return-value]
    sentence = _first_meaningful_sentence(summary)
    if sentence:
        return sentence[:120]
    return f"Untitled saved job · {_aware_utc(saved_at).date().isoformat()}"
```

Call it only from `saved_jobs.py::_list_item`, using validated extraction summary and the persisted `created_at`. Add `display_label: str = Field(min_length=1, max_length=140)` to `SavedJobListItem` and keep `SavedJobDetail.compact` as the sole detail source.

- [ ] **Step 4: Add backward-compatible match/session snapshots**

Add optional `display_label: str | None = Field(default=None, max_length=140)` to `MatchResult`; populate it in `match_scoring.py` from the same helper without changing scores, ordering, weights, or formula. Old stored results remain valid because the field is optional. Add optional `display_label` to `TailoringJobLabel`; `_resolve_new_snapshot` stores the same server projection. Parsers accept old `{title, company}` JSON and derive the label at display time.

- [ ] **Step 5: Verify label consistency and commit backend contracts**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_display.py tests/integration/test_saved_jobs_api.py tests/unit/test_match_components.py tests/unit/test_cv_tailoring_schemas.py tests/integration/test_cv_tailoring_api.py tests/integration/test_cv_tailoring_repository.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/services/job_display.py app/services/saved_jobs.py app/services/match_scoring.py app/services/cv_tailoring.py app/schemas/job_evaluations.py app/schemas/matching.py app/schemas/cv_tailoring.py --no-cache
Set-Location ..
git add backend/app/services/job_display.py backend/app/services/saved_jobs.py backend/app/services/match_scoring.py backend/app/services/cv_tailoring.py backend/app/schemas/job_evaluations.py backend/app/schemas/matching.py backend/app/schemas/cv_tailoring.py backend/tests/unit/test_job_display.py backend/tests/integration/test_saved_jobs_api.py backend/tests/unit/test_match_components.py backend/tests/unit/test_cv_tailoring_schemas.py backend/tests/integration/test_cv_tailoring_api.py backend/tests/integration/test_cv_tailoring_repository.py
git diff --cached --check
git commit -m "feat: give jobs and tailoring sessions stable labels"
```

---

### Task 15: Remove UUIDs/raw score internals and standardize retained frontend copy

**Files:**

- Create: `frontend/src/features/jobs/copy.ts`
- Create: `frontend/src/features/cv-tailoring/presentation.ts`
- Create: `frontend/src/features/chat/copy.ts`
- Create: `frontend/src/features/chat/activityPresentation.ts`
- Modify: `frontend/src/features/jobs/types.ts`
- Modify: `frontend/src/features/jobs/SavedJobsPanel.tsx`
- Modify: `frontend/src/features/jobs/SavedJobCard.tsx`
- Modify: `frontend/src/features/jobs/SavedJobDetail.tsx`
- Modify: `frontend/src/features/jobs/MatchCard.tsx`
- Modify: `frontend/src/features/jobs/ScoreBreakdown.tsx`
- Modify: `frontend/src/features/cv-tailoring/types.ts`
- Modify: `frontend/src/features/cv-tailoring/TailoringSessionsPanel.tsx`
- Modify: `frontend/src/features/cv-tailoring/TailoringEditor.tsx`
- Modify: `frontend/src/features/cv-tailoring/TailoringSessionDeleteDialog.tsx`
- Modify: `frontend/src/features/cv-tailoring/TailoringVersionActions.tsx`
- Modify: `frontend/src/features/chat/components/AgentActivityTimeline.tsx`
- Modify: `frontend/src/features/chat/components/ChatMessageRow.tsx`
- Modify: `frontend/src/features/profile/ProfileListPanel.tsx`
- Modify: `frontend/src/features/profile/ConversationListPanel.tsx`
- Modify: `frontend/src/features/profile/ProfileDeleteDialog.tsx`
- Modify: `frontend/src/test/saved-jobs-panel.test.tsx`
- Modify: `frontend/src/test/saved-job-card.test.tsx`
- Modify: `frontend/src/test/match-card.test.tsx`
- Modify: `frontend/src/test/agent-activity-timeline.test.tsx`
- Modify: `frontend/src/test/cv-tailoring-sessions-panel.test.tsx`
- Modify: `frontend/src/test/cv-tailoring-editor.test.tsx`
- Modify: `frontend/src/test/profile-conversation-sidebar.test.tsx`

- [ ] **Step 1: Write no-leak presentation tests**

```tsx
it('uses the server display label in list, detail, dialog, and match card', async () => {
  render(<SavedJobsPanel {...props({item: {...job, display_label: 'Senior API Engineer · Acme'}})} />);
  expect(screen.getAllByText('Senior API Engineer · Acme').length).toBeGreaterThan(0);
  expect(screen.queryByText(new RegExp(JOB_ID.slice(0, 8)))).not.toBeInTheDocument();
});

it('does not render raw score components, weights, UUIDs, or internal unavailable labels', async () => {
  render(<MatchCard result={matchResultWithDisplayLabel()} />);
  expect(screen.queryByText(/effective_weights|semantic_similarity|Unavailable components|job-/i)).not.toBeInTheDocument();
  expect(screen.getByText(/Not enough CV\/JD information to score experience/i)).toBeInTheDocument();
});

it('hides technical activity names, codes, and timing', async () => {
  render(<AgentActivityTimeline run={agentActivityWithSecrets()} />);
  expect(screen.getByText('Checking source support')).toBeInTheDocument();
  expect(screen.queryByText('create_tailored_cv')).not.toBeInTheDocument();
  expect(screen.queryByText('TAILORING_GROUNDING_FAILED')).not.toBeInTheDocument();
  expect(screen.queryByText(/ms$/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run retained presentation tests and verify duplicated fallbacks fail**

```powershell
Set-Location frontend
npm test -- --run src/test/saved-jobs-panel.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/agent-activity-timeline.test.tsx src/test/cv-tailoring-sessions-panel.test.tsx src/test/cv-tailoring-editor.test.tsx
```

Expected: FAIL because four Saved Job/session components derive independent UUID fallbacks and activity currently renders technical details.

- [ ] **Step 3: Replace every label branch with one projection helper**

Implement:

```ts
export function sessionDisplayLabel(session: TailoringSessionSummary): string {
  const label = session.job_label;
  if (label?.display_label?.trim()) return label.display_label.trim();
  if (label?.title?.trim() && label?.company?.trim()) return `${label.title.trim()} · ${label.company.trim()}`;
  if (label?.title?.trim() || label?.company?.trim()) return label.title?.trim() || label.company!.trim();
  if (session.instruction.trim()) return session.instruction.trim().slice(0, 100);
  return `Untitled tailored CV · ${new Intl.DateTimeFormat('en-CA', {dateStyle: 'short', timeZone: 'UTC'}).format(new Date(session.created_at))}`;
}
```

Use it in sessions list, editor header, delete dialog, and `safeArtifactName`. Use `item.display_label` in Saved Jobs list/detail/cards/dialogs. For old match payloads with no `display_label`, use title/company or the literal `Saved job`; never use `job_id` or a UUID prefix.

- [ ] **Step 4: Make score/activity presentation human-readable**

`ScoreBreakdown` groups matched, related, and missing skills under **Why this score**. Round percentages through the existing `formatDisplayScore`; explain quality multiplier as reduced confidence from incomplete extraction; replace unavailable dimensions with fixed English sentences. `activityPresentation.ts` maps known activity labels/states to **View activity**/**Hide activity**, strips `technicalName`, `errorCode`, raw duration, and internal state names, and preserves the durable activity list/order.

Move all retained product strings to feature-local `copy.ts` modules. Update profile/conversation/status/dialog labels to English while leaving source CV/JD text and skill names untouched. Add a static test scanning retained feature source for known Vietnamese product literals and raw UUID fallback patterns.

- [ ] **Step 5: Verify presentation and English copy**

```powershell
npm test -- --run src/test/saved-jobs-panel.test.tsx src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/agent-activity-timeline.test.tsx src/test/cv-tailoring-sessions-panel.test.tsx src/test/cv-tailoring-editor.test.tsx src/test/profile-conversation-sidebar.test.tsx
npm run lint
npm run typecheck
```

Expected: PASS; no retained UI test contains a UUID-based user-facing assertion.

- [ ] **Step 6: Commit presentation cleanup**

```powershell
Set-Location ..
git add frontend/src/features/jobs frontend/src/features/cv-tailoring frontend/src/features/chat frontend/src/features/profile/ProfileListPanel.tsx frontend/src/features/profile/ConversationListPanel.tsx frontend/src/features/profile/ProfileDeleteDialog.tsx frontend/src/test/saved-jobs-panel.test.tsx frontend/src/test/saved-job-card.test.tsx frontend/src/test/match-card.test.tsx frontend/src/test/agent-activity-timeline.test.tsx frontend/src/test/cv-tailoring-sessions-panel.test.tsx frontend/src/test/cv-tailoring-editor.test.tsx frontend/src/test/profile-conversation-sidebar.test.tsx
git diff --cached --check
git commit -m "fix: remove internal identifiers from product UI"
```

---

### Task 16: Normalize conversation titles and prove explicit tailoring intent

**Files:**

- Modify: `backend/app/db/models/profiles.py`
- Modify: `backend/app/services/conversation_titles.py`
- Modify: `backend/app/repositories/conversations.py`
- Modify: `backend/app/agent/prompt.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/tests/unit/test_conversation_titles.py`
- Modify: `backend/tests/integration/test_conversations_api.py`
- Modify: `backend/tests/integration/test_chat_persistence.py`
- Modify: `backend/tests/unit/test_agent_graph.py`
- Modify: `backend/tests/integration/test_agent_runner.py`
- Modify: `frontend/src/features/profile/conversationTypes.ts`
- Modify: `frontend/src/test/conversation-api.test.ts`
- Modify: `frontend/src/test/profile-api.test.ts`
- Modify: `frontend/src/test/profile-workspace-state.test.tsx`

- [ ] **Step 1: Write title and decision-path regressions**

```py
def test_blank_title_uses_english_default() -> None:
    assert derive_conversation_title("   ") == "New chat"

@pytest.mark.parametrize("message", [
    "Tailor my CV for this saved job",
    "Edit my resume to emphasize the API work",
    "Generate a CV targeted at the selected role",
])
def test_explicit_tailoring_intent_requires_create_tool(message, fake_model) -> None:
    state = invoke_graph_with_message(message, model=fake_model)
    assert [call["name"] for call in tool_calls(state)] == ["create_tailored_cv"]

def test_assistant_prose_cannot_claim_tailoring_success_without_tool_result(fake_model) -> None:
    state = invoke_graph_with_message("Please tailor my CV", model=fake_model.prose_only())
    assert state["tool_result"] is None
    assert state["messages"][-1].content != "Your CV was tailored successfully."
```

- [ ] **Step 2: Run title/intent tests and verify current defaults/decision gaps**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_conversation_titles.py tests/integration/test_conversations_api.py tests/integration/test_chat_persistence.py tests/unit/test_agent_graph.py tests/integration/test_agent_runner.py -q
```

Expected: the title test fails on `Chat mới`; representative intent tests fail or expose prompt-only coverage.

- [ ] **Step 3: Change only the default/title prompt contract**

Set `NEW_CONVERSATION_TITLE = "New chat"`. Keep `derive_conversation_title`'s whitespace normalization, length cap, and first ordinary non-empty user-message guard. Upload/re-extraction/approval/system messages remain excluded from title derivation.

Expand the existing tailoring prompt with the bounded synonyms **edit**, **revise**, **customize**, and **generate**. Add decision-path tests through the existing fake-model/tool registry; do not add a natural-language success classifier or change the final durable `create_tailored_cv` boundary.

- [ ] **Step 4: Update frontend fixture contracts and verify**

Replace Vietnamese default-title fixtures with `New chat`; retain source-message text fixtures unchanged. Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_conversation_titles.py tests/integration/test_conversations_api.py tests/integration/test_chat_persistence.py tests/unit/test_agent_graph.py tests/integration/test_agent_runner.py -q
Set-Location ..\frontend
npm test -- --run src/test/conversation-api.test.ts src/test/profile-api.test.ts src/test/profile-workspace-state.test.tsx
```

Expected: PASS with no synthetic re-extraction title/message regression.

- [ ] **Step 5: Commit title and intent contracts**

```powershell
Set-Location ..
git add backend/app/db/models/profiles.py backend/app/services/conversation_titles.py backend/app/repositories/conversations.py backend/app/agent/prompt.py backend/app/agent/graph.py backend/tests/unit/test_conversation_titles.py backend/tests/integration/test_conversations_api.py backend/tests/integration/test_chat_persistence.py backend/tests/unit/test_agent_graph.py backend/tests/integration/test_agent_runner.py frontend/src/features/profile/conversationTypes.ts frontend/src/test/conversation-api.test.ts frontend/src/test/profile-api.test.ts frontend/src/test/profile-workspace-state.test.tsx
git diff --cached --check
git commit -m "fix: use clear conversation titles and tailoring intent"
```

---

### Task 17: Run final accessibility, browser, documentation, and full regression gates

**Files:**

- Create: `docs/acceptance/product-ux-trust-repair-checklist.md`
- Modify: `README.md`
- Modify: `frontend/src/test/cv-tailoring-accessibility.test.tsx`
- Create: `frontend/src/test/product-copy-static.test.ts`
- Modify: `backend/tests/e2e/test_cv_tailoring_flow.py`
- Modify: `backend/tests/e2e/test_demo_flow.py`

- [ ] **Step 1: Add static and accessibility acceptance tests**

The static test must assert:

```ts
const retained = readSourceTree([
  'src/app', 'src/features/profile', 'src/features/navigation',
  'src/features/cv-manager', 'src/features/jobs', 'src/features/cv-tailoring', 'src/features/chat',
]);
expect(retained).not.toMatch(/LLM chunks|Neo4j graph|Agent runs/);
expect(retained).not.toMatch(/Job \$\{.*slice\(0, 8\)|JD \$\{.*slice\(0, 8\)/);
const nonAppOwners = readSourceTree([
  'src/features/profile', 'src/features/navigation', 'src/features/cv-manager',
  'src/features/jobs', 'src/features/cv-tailoring', 'src/features/chat',
]);
expect(nonAppOwners).not.toMatch(/useSavedJobsState\(|useCvTailoringState\(/);
```

Scope the state-hook assertion to files other than `src/app/App.tsx`, where the two legitimate state-owner calls remain. Add dialog accessible-name/focus, live-region, keyboard order, reduced-motion, narrow drawer, and no-overlapping-scroll assertions to `cv-tailoring-accessibility.test.tsx` and CV Manager tests.

- [ ] **Step 2: Run complete local automated gates**

```powershell
Set-Location backend
& '..\\.venv\\Scripts\\python.exe' -m pytest -q
& '..\\.venv\\Scripts\\python.exe' -m ruff check app tests --no-cache
& '..\\.venv\\Scripts\\python.exe' -m mypy app --no-incremental

Set-Location ..\\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build

Set-Location ..
git diff --check
git status --short
```

Expected: all commands exit 0. A TeX integration test may report its documented skip when `pdflatex` is unavailable; report that skip rather than claiming compiler evidence.

- [ ] **Step 3: Update the sanitized acceptance checklist and README**

Document only synthetic data and user-visible checks in `docs/acceptance/product-ux-trust-repair-checklist.md`: two-profile Back/Forward restoration, direct re-extract progress/review/Discard/Retry/Save, no chat side effects, no-op AI/manual mutation, grounding recovery buttons, CV/profile deletion scope, PDF/LaTeX downloads, non-repeated headings, three primary destinations, no UUID/raw-score/internal activity text, desktop/narrow keyboard/focus/reduced-motion behavior. Update README links/runtime workflow without exposing provider payloads, private paths, or logs.

- [ ] **Step 4: Perform browser acceptance through the frontend only**

Start the supported local stack:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Use the in-app Browser skill at `http://localhost:5173` with synthetic CV/JD data. Do not inspect backend logs. Execute the checklist as a non-technical user: select a JD, create a tailored CV, open it so the chat workspace is replaced, return to chat, edit each section, exercise no-op and grounding recovery, open Manage CVs, re-extract and review, preview/download artifacts, switch profiles, use browser Back, and verify every label/action is understandable. Record only screenshots/visible outcomes and safe error summaries.

- [ ] **Step 5: Inspect final diff and commit acceptance evidence**

```powershell
git diff --check
git status --short
git diff --stat
```

Confirm no migration, new dependency, backend observability deletion, secret/runtime file, `.agent` artifact, raw provider payload, or unrelated user hunk is staged. Commit only the checklist/docs/tests:

```powershell
git add docs/acceptance/product-ux-trust-repair-checklist.md README.md frontend/src/test/cv-tailoring-accessibility.test.tsx frontend/src/test/product-copy-static.test.ts backend/tests/e2e/test_cv_tailoring_flow.py backend/tests/e2e/test_demo_flow.py
git diff --cached --check
git commit -m "docs: record UX trust repair acceptance"
```

## Plan self-review

### Spec coverage

| Design requirement | Plan task(s) |
| --- | --- |
| Profile/conversation ownership and Back/Forward rehydration | 1 |
| Direct re-extraction, durable review, approval/discard, no chat side effects | 5–6 |
| Initial approval shows actual proposed values | 5–6 |
| Profile-review gate and prior-truth preservation | 5 |
| CV Manager action scope and profile deletion wording | 2–4, 6 |
| Three primary destinations and technical-panel removal | 4 |
| Later tailoring no-op and initial Version 1 exception | 7–8 |
| Safe grounding issues and all three recovery actions | 9–10 |
| Separate preview/PDF/LaTeX downloads | 12 |
| Renderer duplicate-heading suppression | 11 |
| Editor layout, sidebar rail, responsive and accessibility behavior | 13, 17 |
| Saved Job/session labels, score and activity presentation | 14–15 |
| English chrome and deterministic conversation titles | 15–16 |
| Explicit tailoring intent and durable-result-only success | 16 |
| Browser acceptance, privacy/static/build/full gates | 17 |

### Placeholder and scope checks

The plan contains no unresolved placeholder marker or vague implementation-only step. Every production change names a file, an owner, a failing test, an exact command, an expected result, and a commit boundary. New files are limited to the file map above; no migration, dependency, service, router, or global-state expansion is permitted.

### Type and transport consistency

- `TailoringMutationOutcome` is defined once in backend/frontend tailoring contracts and is carried through manual JSON, `create_tailored_cv` ToolResult data, AI `run_completed`, and durable detail recovery.
- Profile re-extraction uses its own event union and generic SSE serializer/consumer; chat retains exactly seven event names and its reducer never receives profile events.
- `TailoringUserIssue` has the same field/reason vocabulary in backend schema, frontend parser, HTTP error, SSE failure, and session-detail recovery. Raw `GroundingIssue` code/path remains server-only.
- `CvManagerAction` is server-projected and parsed exactly; no frontend component derives deletion eligibility or calls `workspace.deleteProfile` for a CV action.
- `display_label` is optional for old persisted MatchResult/TailoringJobLabel JSON and required only in new Saved Job list projections; all frontend fallbacks remain UUID-free.

### Final pre-handoff checks

```powershell
$p='C:\Users\ACER\OtherProjects\JobAgent\docs\superpowers\plans\2026-07-27-jobagent-product-ux-trust-repair.md'
$forbidden = @('T'+'BD', 'TO'+'DO', 'implement '+'later', 'write '+'tests for the '+'above')
Select-String -Path $p -Pattern ($forbidden -join '|') -CaseSensitive
if ($LASTEXITCODE -eq 0) { throw 'plan placeholder found' }
git diff --no-index --check -- NUL $p 2>&1
if ($LASTEXITCODE -gt 1) { throw 'plan whitespace check failed' }
```

Expected: placeholder search returns no match; the no-index diff emits only Git's normal LF/CRLF warning and no trailing-whitespace diagnostic. The five pre-existing user-owned files remain unstaged.
