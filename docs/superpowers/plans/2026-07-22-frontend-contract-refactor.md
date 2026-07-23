# JobAgent Frontend Contract Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the real jobs-contract ESM cycle and consolidate only byte-equivalent frontend utilities while preserving feature-specific API/error policies and the sole chat/saved-JD state owners.

**Architecture:** Move URL display sanitization and cursor query encoding into dependency-neutral `lib/` modules, then move chat client DTO types out of the reducer into a neutral model module. Keep jobs and observability JSON/error handling separate, keep `ChatPage` as the only SSE owner, and keep `useSavedJobsState` as the only saved-JD/map cache owner.

**Tech Stack:** React 19, TypeScript 5.9, Vite 6, Vitest, ESLint, URL/URLSearchParams Web APIs, PowerShell, Git.

---

## Scope and execution boundary

- Execute after Plan 16 frontend work and `2026-07-22-dead-code-cleanup.md` are accepted.
- This plan changes no React markup, Astryx component, CSS, request endpoint, response parser policy, SSE reducer behavior, or saved-JD cache behavior.
- Do not consolidate `getJson`, `postJson`, forbidden-field checks, delete retry mapping, or domain parsers; their policies differ intentionally.
- Do not introduce a barrel file that recreates the removed dependency cycles.
- The four `docs/superpowers/plans/2026-07-22-*.md` files are planning
  artifacts. They may already be tracked or may remain untracked when execution
  starts; implementation commits must not stage them.

### Task 1: Move `safeHttpUrl` to a neutral owner and break the jobs runtime cycle

**Files:**
- Create: `frontend/src/lib/url.ts`
- Modify: `frontend/src/features/jobs/types.ts:8-14,121-145`
- Modify: `frontend/src/features/jobs/matchResult.ts:7-9`
- Modify: `frontend/src/test/saved-job-card.test.tsx:40-53`
- Test: `frontend/src/test/saved-job-card.test.tsx`
- Test: `frontend/src/test/match-card.test.tsx`
- Test: `frontend/src/test/saved-jobs-api.test.ts`

- [ ] **Step 1: Point the existing URL test at the future neutral owner**

Change the imports in `saved-job-card.test.tsx` to:

```ts
import {
  NEO4J_SYNC_FAILED_CODE,
  parseSaveJobResultData,
  projectCompactResultData,
  type CompactSaveJobResult,
} from '../features/jobs/types';
import {safeHttpUrl} from '../lib/url';
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```powershell
Set-Location frontend
npm test -- --run src/test/saved-job-card.test.tsx
```

Expected: module resolution fails because `src/lib/url.ts` does not exist.

- [ ] **Step 3: Create the neutral URL display sanitizer**

Create `frontend/src/lib/url.ts`:

```ts
/** Accept only absolute http(s) URLs for display. */
export function safeHttpUrl(
  value: string | null | undefined,
): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  const trimmed = value.trim();
  if (trimmed === '') {
    return null;
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Route both parsers to the neutral helper**

Delete the function from `jobs/types.ts`. Add this import to both job modules:

```ts
import {safeHttpUrl} from '../../lib/url';
```

Keep `types.ts -> matchResult.ts` for `parseMatchResult` and `JOB_WORK_MODES`; after this change `matchResult.ts` no longer imports `types.ts`, so the runtime cycle is removed.

- [ ] **Step 5: Run URL/parser/card regressions and verify dependency direction**

Run:

```powershell
npm test -- --run src/test/saved-job-card.test.tsx src/test/match-card.test.tsx src/test/saved-jobs-api.test.ts
npm run typecheck
rg -n "from './types'" src/features/jobs/matchResult.ts
rg -n "safeHttpUrl" src/lib/url.ts src/features/jobs/types.ts src/features/jobs/matchResult.ts src/test/saved-job-card.test.tsx
```

Expected: tests and typecheck pass; the first `rg` exits 1; the second shows one definition and the three intended consumers/tests. Exact `new URL(trimmed).toString()` output remains unchanged.

- [ ] **Step 6: Commit the cycle correction**

```powershell
Set-Location ..
git add frontend/src/lib/url.ts frontend/src/features/jobs/types.ts frontend/src/features/jobs/matchResult.ts frontend/src/test/saved-job-card.test.tsx
git commit -m "refactor(frontend): isolate safe url parsing"
```

Expected: one helper/cycle commit with no UI or API behavior change.

### Task 2: Consolidate cursor query encoding only

**Files:**
- Create: `frontend/src/lib/api/cursorQuery.ts`
- Create: `frontend/src/test/cursor-query.test.ts`
- Modify: `frontend/src/features/jobs/api.ts:118-129,249`
- Modify: `frontend/src/features/observability/api.ts:43-63,93,118,158`
- Test: `frontend/src/test/saved-jobs-api.test.ts`
- Test: `frontend/src/test/observability-api.test.ts`

- [ ] **Step 1: Add a failing pure helper test**

Create `frontend/src/test/cursor-query.test.ts`:

```ts
import {describe, expect, it} from 'vitest';

import {buildCursorQuery} from '../lib/api/cursorQuery';

describe('buildCursorQuery', () => {
  it('omits absent values', () => {
    expect(buildCursorQuery()).toBe('');
    expect(buildCursorQuery({before: null})).toBe('');
    expect(buildCursorQuery({before: ''})).toBe('');
  });

  it('preserves limit-before ordering and URLSearchParams encoding', () => {
    expect(buildCursorQuery({limit: 10, before: 'cursor value'})).toBe(
      '?limit=10&before=cursor+value',
    );
  });
});
```

- [ ] **Step 2: Run the helper test to verify RED**

Run:

```powershell
Set-Location frontend
npm test -- --run src/test/cursor-query.test.ts
```

Expected: module resolution fails because `cursorQuery.ts` does not exist.

- [ ] **Step 3: Implement the exact shared query contract**

Create `frontend/src/lib/api/cursorQuery.ts`:

```ts
export type CursorPageQuery = {
  limit?: number;
  before?: string | null;
};

export function buildCursorQuery(
  query: CursorPageQuery = {},
): string {
  const params = new URLSearchParams();
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit));
  }
  if (query.before) {
    params.set('before', query.before);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}
```

- [ ] **Step 4: Replace only the two local `buildQuery` implementations**

Import the helper in both API modules:

```ts
import {buildCursorQuery} from '../../lib/api/cursorQuery';
```

Replace the four calls exactly:

```ts
await getJson(`/api/jobs${buildCursorQuery(query)}`, signal);
await getJson(`/api/observability/cvs${buildCursorQuery(query)}`, signal);
const path = `/api/observability/cvs/${encodeURIComponent(attachmentId)}/chunks${buildCursorQuery(query)}`;
await getJson(`/api/observability/runs${buildCursorQuery(query)}`, signal);
```

Delete both local functions. Keep `SavedJobsPageQuery` and `ObservabilityPageQuery` in their current feature owners.

- [ ] **Step 5: Run pure and transport tests**

Run:

```powershell
npm test -- --run src/test/cursor-query.test.ts src/test/saved-jobs-api.test.ts src/test/observability-api.test.ts
npm run lint
npm run typecheck
rg -n "function buildQuery" src/features/jobs/api.ts src/features/observability/api.ts
```

Expected: tests, lint, and typecheck pass; the final `rg` exits 1; endpoint paths and query ordering remain exact.

- [ ] **Step 6: Commit the query-helper refactor**

```powershell
Set-Location ..
git add frontend/src/lib/api/cursorQuery.ts frontend/src/features/jobs/api.ts frontend/src/features/observability/api.ts frontend/src/test/cursor-query.test.ts
git commit -m "refactor(frontend): share cursor query encoding"
```

Expected: one pure-helper commit; no JSON/error handling moves.

### Task 3: Move chat client DTOs out of the reducer

**Files:**
- Create: `frontend/src/features/chat/model.ts`
- Modify: `frontend/src/features/chat/reducer.ts:17-72`
- Modify: `frontend/src/features/chat/history.ts:18-23`
- Modify: `frontend/src/features/chat/activeCvEvidence.ts:10`
- Modify: `frontend/src/features/chat/jobSaveConfirmation.ts:7-11`
- Test: `frontend/src/test/sse-reducer.test.ts`
- Test: `frontend/src/test/active-cv-source.test.tsx`
- Test: `frontend/src/test/job-save-confirmation.test.tsx`

- [ ] **Step 1: Capture the current type dependency cycle**

Run:

```powershell
Set-Location frontend
rg -n "from './reducer'" src/features/chat/history.ts src/features/chat/activeCvEvidence.ts src/features/chat/jobSaveConfirmation.ts
rg -n "from './history'" src/features/chat/reducer.ts
```

Expected: history and evidence/policy modules import client DTO types from the reducer while the reducer imports history runtime functions.

- [ ] **Step 2: Create the neutral chat client model**

Create `frontend/src/features/chat/model.ts`:

```ts
import type {
  JsonObject,
  MessageRole,
  RunState,
  ToolStatus,
} from './types';

export type StreamPhase =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'disconnected'
  | 'failed';

export interface ClientToolActivity {
  toolExecutionId: string;
  toolCallId: string;
  toolName: string;
  status: ToolStatus;
  durationMs: number | null;
  summary: string | null;
  errorCode: string | null;
  source: 'stream' | 'history';
  resultData: JsonObject | null;
}

export interface ClientRun {
  id: string;
  userMessageId: string | null;
  state: RunState;
  pendingApproval: JsonObject | null;
  errorCode: string | null;
  completedAt: string | null;
  tools: ClientToolActivity[];
}

export interface ClientMessage {
  id: string;
  clientKey: string;
  role: MessageRole;
  content: string;
  createdAt: string | null;
  run: ClientRun | null;
  isStreaming: boolean;
}

export interface StreamErrorInfo {
  code: string;
  summary: string;
}
```

- [ ] **Step 3: Make the reducer consume and temporarily re-export the model**

Delete the five moved declarations from `reducer.ts`, then add:

```ts
import type {
  ClientMessage,
  ClientRun,
  ClientToolActivity,
  StreamErrorInfo,
  StreamPhase,
} from './model';

export type {
  ClientMessage,
  ClientRun,
  ClientToolActivity,
  StreamErrorInfo,
  StreamPhase,
} from './model';
```

The re-export preserves current test/component imports; it does not recreate a runtime cycle because all five are type-only.

- [ ] **Step 4: Point cycle-forming production modules directly at `model.ts`**

Use direct type imports:

```ts
import type {
  ClientMessage,
  ClientRun,
  ClientToolActivity,
} from './model';
```

`history.ts` needs all three; `activeCvEvidence.ts` needs `ClientToolActivity`; `jobSaveConfirmation.ts` needs `ClientMessage` and `ClientRun`. Do not change their functions or output projections.

- [ ] **Step 5: Run chat/evidence/confirmation regressions and verify direction**

Run:

```powershell
npm test -- --run src/test/sse-reducer.test.ts src/test/active-cv-source.test.tsx src/test/job-save-confirmation.test.tsx src/test/assistant-response.test.tsx src/test/empty-match-card.test.tsx
npm run lint
npm run typecheck
rg -n "from './reducer'" src/features/chat/history.ts src/features/chat/activeCvEvidence.ts src/features/chat/jobSaveConfirmation.ts
rg -n "from './model'" src/features/chat/reducer.ts src/features/chat/history.ts src/features/chat/activeCvEvidence.ts src/features/chat/jobSaveConfirmation.ts
```

Expected: tests, lint, and typecheck pass; the first dependency search exits 1; all four modules consume `model.ts` directly.

- [ ] **Step 6: Commit the chat model boundary**

```powershell
Set-Location ..
git add frontend/src/features/chat/model.ts frontend/src/features/chat/reducer.ts frontend/src/features/chat/history.ts frontend/src/features/chat/activeCvEvidence.ts frontend/src/features/chat/jobSaveConfirmation.ts
git commit -m "refactor(frontend): isolate chat client model"
```

Expected: one type-boundary commit with identical reducer behavior.

### Task 4: Run the integrated frontend gate

**Files:**
- Validate: all files changed in Tasks 1-3

- [ ] **Step 1: Run the complete frontend verification suite**

Run:

```powershell
Set-Location frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: every command exits 0 with candidate-specific test counts.

- [ ] **Step 2: Audit imports and scope**

Run:

```powershell
rg -n "from './types'" src/features/jobs/matchResult.ts
rg -n "function buildQuery" src/features/jobs/api.ts src/features/observability/api.ts
rg -n "from './reducer'" src/features/chat/history.ts src/features/chat/activeCvEvidence.ts src/features/chat/jobSaveConfirmation.ts
Set-Location ..
git diff --check
git status --short
git diff --name-only HEAD~3..HEAD
```

Expected: all three searches return no matches; whitespace passes; exactly
three planned commits exist; no CSS, component markup, dependency manifest,
backend, Master Plan, or Task file changed. Status may additionally show the
four authorized plan artifacts when they were not committed before execution;
no other unplanned path may appear.

## Deferred low-risk duplication register

- Keep the jobs and observability `getJson` wrappers separate because saved-JD forbidden-field and retry policies differ.
- Keep domain-specific `hasOnlyKeys`, `asNullableString`, and cached-resource reducer helpers separate until a typed validation utility has a measured second consumer; moving them now would widen the Plan 16 contract diff.
