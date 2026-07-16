# Observability Sidebar UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the existing Plan 8 observability sidebar as a resizable Astryx inspector with compact list views and an interactive draggable SVG Neo4j graph, without changing backend or chat contracts.

**Architecture:** Keep `AppShell`, `SideNav`, the typed observability API, and the existing lazy cache. Split navigation, shared panel chrome, graph projection, force simulation, zoom viewport, SVG rendering, and semantic fallback into focused frontend modules. Use Astryx 0.1.4 for every UI component; use modular D3 packages only for graph physics, selection, and zoom behavior.

**Tech Stack:** React 19, TypeScript 5.9, Astryx 0.1.4, d3-force 3.0.0, d3-selection 3.0.0, d3-zoom 3.0.0, Vitest, Testing Library, Vite, Docker Compose, in-app browser.

---

## Scope And File Map

This is one frontend subsystem: the existing observability sidebar. Backend
read models, schemas, routes, redaction, and graph caps stay unchanged.

**Create:**

- `frontend/src/features/profile/ProfileOverviewPanel.tsx` — Overview presentation only.
- `frontend/src/features/observability/ObservabilityTabList.tsx` — expanded/collapsed vertical tabs.
- `frontend/src/features/observability/ObservabilityPanelHeader.tsx` — shared title/refresh chrome.
- `frontend/src/features/observability/ObservabilityListSkeleton.tsx` — known-shape list loading state.
- `frontend/src/features/observability/observabilityFormat.ts` — timestamp and duration formatting.
- `frontend/src/features/observability/graphPresentation.ts` — pure API-to-graph display model.
- `frontend/src/features/observability/graphSimulation.ts` — imperative D3 force controller.
- `frontend/src/features/observability/useGraphSimulation.ts` — React lifecycle for the controller.
- `frontend/src/features/observability/useGraphViewport.ts` — resize, D3 zoom, pan, fit, and inverse coordinates.
- `frontend/src/features/observability/GraphCanvas.tsx` — responsive SVG and graph controls.
- `frontend/src/features/observability/GraphSemanticList.tsx` — Astryx semantic fallback.
- `frontend/src/test/support/observability.tsx` — shared synthetic fixtures and render helper.
- `frontend/src/test/observability-primitives.test.tsx` — shared format/chrome tests.
- `frontend/src/test/observability-navigation.test.tsx` — rail, resize, collapse, and mobile tests.
- `frontend/src/test/observability-panels.test.tsx` — Overview, CV, chunk, and run hierarchy tests.
- `frontend/src/test/graph-presentation.test.ts` — deterministic graph mapping tests.
- `frontend/src/test/graph-interaction.test.tsx` — simulation, viewport, SVG, and fallback tests.

**Modify:**

- `frontend/package.json`, `frontend/package-lock.json`
- `frontend/src/features/profile/CvSidebar.tsx`
- `frontend/src/features/observability/ObservabilitySidebar.tsx`
- `frontend/src/features/observability/CvHistoryPanel.tsx`
- `frontend/src/features/observability/ChunkPanel.tsx`
- `frontend/src/features/observability/GraphPanel.tsx`
- `frontend/src/features/observability/RunHistoryPanel.tsx`
- `frontend/src/features/observability/observability.css`
- `frontend/src/test/observability-sidebar.test.tsx`
- `frontend/src/test/setup.ts`

No backend source file changes are expected.

### Task 1: Pin The Non-Visual Graph Dependencies

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Confirm no equivalent graph engine is already installed**

Run from repository root:

```powershell
git grep -n -e "d3-force" -e "d3-zoom" -e "react-force" -- frontend/package.json frontend/package-lock.json frontend/src
```

Expected: no matches.

- [ ] **Step 2: Install exact modular runtime and type packages**

Run from `frontend/`:

```powershell
npm install --save-exact d3-force@3.0.0 d3-selection@3.0.0 d3-zoom@3.0.0
npm install --save-dev --save-exact @types/d3-force@3.0.10 @types/d3-selection@3.0.11 @types/d3-zoom@3.0.8
```

Expected: `package.json` records exact versions; Astryx remains `0.1.4`.

- [ ] **Step 3: Verify the dependency boundary and baseline**

Run from `frontend/`:

```powershell
npm list @astryxdesign/core d3-force d3-selection d3-zoom --depth=0
npm test -- --run src/test/observability-sidebar.test.tsx src/test/observability-api.test.ts
npm run typecheck
```

Expected: Astryx `0.1.4`, D3 modules `3.0.0`, and all baseline checks pass.

- [ ] **Step 4: Commit the dependency lock**

```powershell
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add graph layout dependencies"
```

### Task 2: Extract Shared Observability Test Fixtures

**Files:**
- Create: `frontend/src/test/support/observability.tsx`
- Modify: `frontend/src/test/observability-sidebar.test.tsx`
- Test: `frontend/src/test/observability-sidebar.test.tsx`

- [ ] **Step 1: Run the existing sidebar test before the test-only refactor**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-sidebar.test.tsx
```

Expected: current sidebar tests pass.

- [ ] **Step 2: Move synthetic builders into one support module**

Move the existing constants and builders from
`observability-sidebar.test.tsx` into the new module, add exports, and keep the
payloads byte-for-byte equivalent. The module must expose this surface:

```tsx
export const ATTACHMENT_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
export const RUN_ID = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
export const TOOL_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
export const MSG_ID = 'dddddddd-eeee-4fff-8aaa-111111111111';

export function emptyProfile(): ProfileReadResponse;
export function cvHistoryPage(available?: boolean): CvHistoryPage;
export function chunkListPage(): ChunkListPage;
export function chunkDetail(): ChunkDetail;
export function graphReady(): GraphSnapshot;
export function runsPage(): RunHistoryPage;
export function mockObservabilityApi(
  overrides?: Partial<ObservabilityApi>,
): ObservabilityApi;
export function renderObservabilitySidebar(
  api?: ObservabilityApi,
): ReturnType<typeof render> & {
  api: ObservabilityApi;
  loadProfile: ReturnType<typeof vi.fn>;
};
```

`renderObservabilitySidebar` must continue rendering `CvSidebar` inside
`Theme theme={neutralTheme}` with synthetic functions only.

- [ ] **Step 3: Replace local fixture definitions with imports**

Use one import block in `observability-sidebar.test.tsx`:

```tsx
import {
  ATTACHMENT_ID,
  RUN_ID,
  chunkDetail,
  chunkListPage,
  cvHistoryPage,
  graphReady,
  mockObservabilityApi,
  renderObservabilitySidebar,
  runsPage,
} from './support/observability';
```

Rename local calls from `mockApi` to `mockObservabilityApi` and from
`renderSidebar` to `renderObservabilitySidebar`. Do not alter assertions.

- [ ] **Step 4: Run the refactored test**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-sidebar.test.tsx
```

Expected: the same tests pass; the original test file is below 300 lines.

- [ ] **Step 5: Commit the test support split**

```powershell
git add frontend/src/test/support/observability.tsx frontend/src/test/observability-sidebar.test.tsx
git commit -m "test: extract observability fixtures"
```

### Task 3: Add Shared Formatting And Panel Chrome

**Files:**
- Create: `frontend/src/features/observability/observabilityFormat.ts`
- Create: `frontend/src/features/observability/ObservabilityPanelHeader.tsx`
- Create: `frontend/src/features/observability/ObservabilityListSkeleton.tsx`
- Create: `frontend/src/test/observability-primitives.test.tsx`

- [ ] **Step 1: Write failing format and component tests**

```tsx
import {render, screen} from '@testing-library/react';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it, vi} from 'vitest';

import {ObservabilityListSkeleton} from '../features/observability/ObservabilityListSkeleton';
import {ObservabilityPanelHeader} from '../features/observability/ObservabilityPanelHeader';
import {
  formatDurationMs,
  formatObservabilityDateTime,
  formatRunDuration,
} from '../features/observability/observabilityFormat';

describe('observability presentation primitives', () => {
  it('formats valid values and preserves invalid timestamps safely', () => {
    expect(formatDurationMs(96)).toBe('96 ms');
    expect(formatDurationMs(1800)).toBe('1.8 s');
    expect(formatDurationMs(60000)).toBe('1 min');
    expect(formatRunDuration('2024-07-01T12:00:00Z', '2024-07-01T12:00:12Z')).toBe('12 s');
    expect(formatObservabilityDateTime('not-a-date')).toBe('not-a-date');
  });

  it('renders accessible refresh chrome and known-shape skeleton rows', () => {
    render(
      <Theme theme={neutralTheme}>
        <ObservabilityPanelHeader
          eyebrow="RUN HISTORY"
          title="Recent activity"
          onRefresh={vi.fn()}
          isRefreshing
          refreshTestId="refresh-runs"
        />
        <ObservabilityListSkeleton rows={3} testId="runs-skeleton" />
      </Theme>,
    );
    expect(screen.getByRole('button', {name: 'Refresh Recent activity'})).toBeDisabled();
    expect(screen.getByTestId('runs-skeleton').children).toHaveLength(3);
  });
});
```

- [ ] **Step 2: Run the test and verify the missing modules fail**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-primitives.test.tsx
```

Expected: FAIL because the three modules do not exist.

- [ ] **Step 3: Implement the pure formatting helpers**

```ts
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export function formatObservabilityDateTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateTimeFormatter.format(parsed);
}

export function formatDurationMs(value: number): string {
  if (value < 1000) {
    return `${value} ms`;
  }
  if (value >= 60000) {
    const minutes = value / 60000;
    return `${Number.isInteger(minutes) ? minutes.toFixed(0) : minutes.toFixed(1)} min`;
  }
  const seconds = value / 1000;
  return `${Number.isInteger(seconds) ? seconds.toFixed(0) : seconds.toFixed(1)} s`;
}

export function formatRunDuration(
  createdAt: string,
  completedAt: string | null,
): string | null {
  if (!completedAt) {
    return null;
  }
  const start = new Date(createdAt).getTime();
  const end = new Date(completedAt).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return null;
  }
  return formatDurationMs(end - start);
}
```

- [ ] **Step 4: Implement the Astryx panel header and skeleton**

`ObservabilityPanelHeader` must use `Text`, `VStack`, `HStack`, and
`IconButton`. Its refresh button uses a familiar refresh glyph inside the
Astryx control, with both `label` and `tooltip`:

```tsx
<IconButton
  label={`Refresh ${title}`}
  tooltip={`Refresh ${title}`}
  icon={<span aria-hidden="true">↻</span>}
  variant="ghost"
  size="sm"
  isLoading={isRefreshing}
  onClick={onRefresh}
  data-testid={refreshTestId}
/>
```

`ObservabilityListSkeleton` must render `rows` Astryx `Skeleton` pairs inside a
`VStack`, assign `index={index * 2}` and `index={index * 2 + 1}`, and expose only
the requested wrapper test ID. Do not render a simultaneous `Spinner`.

- [ ] **Step 5: Run focused tests**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-primitives.test.tsx
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit shared primitives**

```powershell
git add frontend/src/features/observability/observabilityFormat.ts frontend/src/features/observability/ObservabilityPanelHeader.tsx frontend/src/features/observability/ObservabilityListSkeleton.tsx frontend/src/test/observability-primitives.test.tsx
git commit -m "feat: add observability presentation primitives"
```

### Task 4: Build Astryx Navigation, Resize, Collapse, Mobile, And Overview

**Files:**
- Create: `frontend/src/features/observability/ObservabilityTabList.tsx`
- Create: `frontend/src/features/profile/ProfileOverviewPanel.tsx`
- Create: `frontend/src/test/observability-navigation.test.tsx`
- Modify: `frontend/src/features/profile/CvSidebar.tsx`
- Modify: `frontend/src/features/observability/ObservabilitySidebar.tsx`
- Modify: `frontend/src/features/observability/observability.css`
- Test: `frontend/src/test/cv-sidebar.test.tsx`

- [ ] **Step 1: Write failing navigation tests**

```tsx
it('uses a vertical tab list and Astryx resize handle', async () => {
  renderObservabilitySidebar();
  expect(await screen.findByRole('tablist', {name: 'Observability inspector'}))
    .toHaveAttribute('aria-orientation', 'vertical');
  expect(screen.getByRole('separator', {name: 'Resize sidebar'})).toBeInTheDocument();
});

it('keeps tabs in the collapsed rail and expands the selected view', async () => {
  renderObservabilitySidebar();
  await userEvent.click(await screen.findByTestId('jobagent-sidebar-collapse'));
  expect(screen.getByRole('tab', {name: 'Neo4j graph'})).toBeInTheDocument();
  await userEvent.click(screen.getByRole('tab', {name: 'Neo4j graph'}));
  expect(await screen.findByTestId('jobagent-obs-graph')).toBeInTheDocument();
  expect(screen.getByTestId('jobagent-sidebar-collapse')).toHaveAttribute('aria-expanded', 'true');
});

it('lets AppShell expose the same inspector through automatic mobile navigation', async () => {
  installMatchMedia(true);
  const api = mockObservabilityApi();
  render(
    <Theme theme={neutralTheme}>
      <AppShell
        sideNav={
          <CvSidebar
            isUploadDisabled={false}
            onSidebarUploadSuccess={vi.fn()}
            deps={{
              loadProfile: vi.fn().mockResolvedValue(emptyProfile()),
              uploadCv: vi.fn(),
              observability: api,
            }}
          />
        }
      >
        <div data-testid="mobile-chat-content">Chat</div>
      </AppShell>
    </Theme>,
  );
  const open = await screen.findByRole('button', {name: 'Open navigation'});
  await userEvent.click(open);
  expect(await screen.findByRole('tab', {name: 'Overview'})).toBeInTheDocument();
  expect(screen.getByTestId('mobile-chat-content')).toBeInTheDocument();
});
```

Add `installMatchMedia(matches: boolean)` to the shared test support; it must
return a `MediaQueryList`-shaped object using the supplied `matches` value.
Import `AppShell`, `Theme`, `neutralTheme`, `CvSidebar`, `emptyProfile`,
Testing Library `render`, and Vitest `vi` in the navigation test.

- [ ] **Step 2: Run the tests and verify old navigation fails**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-navigation.test.tsx
```

Expected: FAIL because the current tabs are wrapped `Button` controls, the
SideNav is not resizable, and collapsed mode removes the tabs.

- [ ] **Step 3: Implement `ObservabilityTabList` with Astryx only**

```tsx
import {Icon, type IconName} from '@astryxdesign/core/Icon';
import {Tab, TabList} from '@astryxdesign/core/TabList';
import {Tooltip} from '@astryxdesign/core/Tooltip';

import type {ObservabilityTabId} from './types';

const TABS: ReadonlyArray<{
  id: ObservabilityTabId;
  label: string;
  icon: IconName;
}> = [
  {id: 'overview', label: 'Overview', icon: 'info'},
  {id: 'cv-history', label: 'CV history', icon: 'clock'},
  {id: 'chunks', label: 'LLM chunks', icon: 'viewColumns'},
  {id: 'graph', label: 'Neo4j graph', icon: 'arrowsUpDown'},
  {id: 'runs', label: 'Agent runs', icon: 'wrench'},
];

export function ObservabilityTabList({
  value,
  isCollapsed,
  onChange,
}: {
  value: ObservabilityTabId;
  isCollapsed: boolean;
  onChange: (value: ObservabilityTabId) => void;
}) {
  return (
    <div className="jobagent-obs-tab-rail">
      <TabList
        value={value}
        onChange={(next) => {
          const tab = TABS.find((item) => item.id === next);
          if (tab) onChange(tab.id);
        }}
        orientation="vertical"
        size="sm"
      >
        {TABS.map((tab) => (
          <Tab
            key={tab.id}
            value={tab.id}
            label={tab.label}
            isLabelHidden={isCollapsed}
            icon={
              <Tooltip content={tab.label} isEnabled={isCollapsed} placement="end">
                <Icon icon={tab.icon} size="sm" />
              </Tooltip>
            }
            id={`jobagent-obs-tab-${tab.id}`}
            data-testid={`jobagent-obs-tab-${tab.id}`}
          />
        ))}
      </TabList>
    </div>
  );
}
```

- [ ] **Step 4: Extract Overview presentation**

Create `ProfileOverviewPanel` with explicit props for state label/variant,
filename, selected file, upload errors, upload handlers, disabled/loading state,
and view/download. Use a single-column Astryx `MetadataList` for `Profile state`
and `Active CV`, then the existing Astryx `Banner`, `FileInput`, and `Button`.
Keep these existing test IDs unchanged:

```tsx
<Text type="body" data-testid="jobagent-profile-state">{state.text}</Text>
<Text type="body" maxLines={2} data-testid="jobagent-active-cv-filename">
  {cvName}
</Text>
<FileInput data-testid="jobagent-cv-upload" />
<Button data-testid="jobagent-cv-download" />
```

`CvSidebar` continues to own all async profile/upload logic; the new component
must not fetch or open URLs itself.

- [ ] **Step 5: Replace custom SideNav controls with Astryx ownership**

Replace local collapse state and footer `Button` with this configuration:

```tsx
<SideNav
  resizable={{
    defaultWidth: 420,
    minWidth: 360,
    maxWidth: 560,
    autoSaveId: 'jobagent-observability-sidebar-width',
  }}
  collapsible={{hasButton: false}}
  className="jobagent-cv-sidebar-shell"
  header={
    <SideNavHeading
      heading="JobAgent"
      subheading="CV & profile"
      icon={<NavIcon icon={<Icon icon="search" />} />}
    />
  }
  footerIcons={
    <SideNavCollapseButton data-testid="jobagent-sidebar-collapse" />
  }
  data-testid="jobagent-cv-sidebar"
>
  <ObservabilitySidebar
    overview={overview}
    collapsedStatus={collapsedStatus}
    api={deps?.observability}
  />
</SideNav>
```

- [ ] **Step 6: Make collapsed tab selection expand the inspector**

In `ObservabilitySidebar`, read `{isCollapsed, toggle}` from
`useSideNavCollapse`. Render `ObservabilityTabList` in both states. Its change
handler must select first, then call `toggle()` only when collapsed:

```tsx
const handleSelectTab = (tab: ObservabilityTabId) => {
  obs.selectTab(tab);
  if (isCollapsed) {
    toggle();
  }
};
```

Expanded content belongs in `.jobagent-obs-content`; collapsed content keeps the
tab rail plus the visibly labeled `StatusDot`/CV status. Do not create a custom
mobile drawer: the existing `AppShell` already renders Astryx `MobileNav` below
`md`, using its default 320px width capped at 85vw.

- [ ] **Step 7: Add responsive grid/rail CSS using Astryx tokens**

```css
.jobagent-obs-root {
  display: grid;
  grid-template-columns: 7rem minmax(0, 1fr);
  width: 100%;
  min-width: 0;
}

.jobagent-obs-root[data-collapsed='true'] {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.jobagent-obs-tab-rail,
.jobagent-obs-content {
  min-width: 0;
}

.jobagent-obs-content {
  border-inline-start: 1px solid var(--color-border);
  padding: var(--spacing-2);
}

@media (max-width: 767px) {
  .jobagent-obs-root {
    display: flex;
    flex-direction: column;
  }

  .jobagent-obs-content {
    border-inline-start: 0;
    border-block-start: 1px solid var(--color-border);
  }
}
```

- [ ] **Step 8: Run navigation, profile, and regression tests**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-navigation.test.tsx src/test/observability-sidebar.test.tsx src/test/cv-sidebar.test.tsx src/test/chat-page.test.tsx
npm run typecheck
```

Expected: PASS.

- [ ] **Step 9: Browser checkpoint for Overview, resize, collapse, and mobile**

Rebuild/start Compose from repository root:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
```

Then use the in-app browser at `http://localhost:5173`.
Verify 1440x900, 1024x768, and 390x844. Drag the Astryx resize handle through
360–560px, collapse/expand, select a tab from the rail, open/close the automatic
mobile drawer with button/Escape/backdrop, and confirm the composer remains
visible after close. Expected: no overlap, clipped labels, or console errors.

- [ ] **Step 10: Commit navigation and Overview**

```powershell
git add frontend/src/features/profile/ProfileOverviewPanel.tsx frontend/src/features/profile/CvSidebar.tsx frontend/src/features/observability/ObservabilityTabList.tsx frontend/src/features/observability/ObservabilitySidebar.tsx frontend/src/features/observability/observability.css frontend/src/test/observability-navigation.test.tsx frontend/src/test/support/observability.tsx
git commit -m "feat: rebuild observability navigation with Astryx"
```

### Task 5: Convert CV History And Chunks To Astryx Lists

**Files:**
- Modify: `frontend/src/features/observability/CvHistoryPanel.tsx`
- Modify: `frontend/src/features/observability/ChunkPanel.tsx`
- Create: `frontend/src/test/observability-panels.test.tsx`
- Modify: `frontend/src/features/observability/observability.css`

- [ ] **Step 1: Write failing hierarchy tests**

```tsx
it('selects a CV from one divided Astryx list and shows details outside the row', async () => {
  const api = mockObservabilityApi();
  renderObservabilitySidebar(api);
  await userEvent.click(screen.getByRole('tab', {name: 'CV history'}));
  const item = await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`);
  await userEvent.click(item);
  expect(item).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByTestId('jobagent-obs-cv-detail')).toHaveTextContent('abcdef012345');
  expect(screen.getByTestId(`jobagent-obs-cv-open-${ATTACHMENT_ID}`)).toBeEnabled();
});

it('loads one chunk detail from the selected list row', async () => {
  const api = mockObservabilityApi();
  renderObservabilitySidebar(api);
  await userEvent.click(screen.getByRole('tab', {name: 'CV history'}));
  await userEvent.click(await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`));
  await userEvent.click(screen.getByRole('tab', {name: 'LLM chunks'}));
  await userEvent.click(await screen.findByTestId('jobagent-obs-chunk-toggle-0'));
  expect(await screen.findByTestId('jobagent-obs-chunk-fulltext-0'))
    .toHaveTextContent('Full expanded chunk body for inspection');
});
```

- [ ] **Step 2: Run the panel test and verify it fails**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-panels.test.tsx
```

Expected: FAIL because the current panels use bordered row wrappers and action
buttons inside every row.

- [ ] **Step 3: Implement CV History as one divided list**

Use `ObservabilityPanelHeader`, `ObservabilityListSkeleton`, `List`, `ListItem`,
`StatusDot`, `MetadataList`, and `MetadataListItem`. The list item owns selection;
the open command is in a separate detail region:

```ts
function attachmentVariant(state: CvHistoryItem['state']) {
  if (state === 'active') return 'success' as const;
  if (state === 'staged') return 'warning' as const;
  if (state === 'failed') return 'error' as const;
  return 'neutral' as const;
}
```

```tsx
<List density="compact" hasDividers header="CV history">
  {items.map((item) => (
    <ListItem
      key={item.id}
      label={item.original_name}
      description={`${item.state} · ${formatObservabilityDateTime(item.created_at)}`}
      startContent={<StatusDot variant={attachmentVariant(item.state)} label={item.state} />}
      endContent={item.file_available ? 'Available' : 'Unavailable'}
      isSelected={item.id === selectedAttachmentId}
      onClick={() => onSelect(item)}
      data-testid={`jobagent-obs-cv-select-${item.id}`}
    />
  ))}
</List>
```

When selected, render `jobagent-obs-cv-detail` below the list with exact safe
fields: state, abbreviated hash, page count, size bytes, created time, and
updated time. Put the `Open / download` Astryx `Button` there and keep its
existing test ID and `file_available` gate.

- [ ] **Step 4: Implement Chunks as one divided list with one detail region**

Each `ListItem` owns expand/collapse and uses this stable test ID:

```tsx
<ListItem
  key={key}
  label={`Chunk #${item.ordinal}`}
  description={item.preview}
  endContent={`${item.char_count} chars · ~${item.token_estimate} tokens`}
  isSelected={expandedOrdinal === item.ordinal}
  onClick={() =>
    expandedOrdinal === item.ordinal ? onCollapse() : onExpand(item.ordinal)
  }
  data-testid={`jobagent-obs-chunk-toggle-${item.ordinal}`}
/>
```

Render the selected detail below the list. Keep the labeled `Spinner` only for
unknown-height detail loading, keep the safe error `Banner`, and keep the bounded
`pre.jobagent-obs-fulltext`. Initial list loading uses skeleton rows only.

- [ ] **Step 5: Preserve cached data during refresh and error**

Pass `isRefreshing={phase === 'loading' && Boolean(resource.data)}` to the shared
header. Render error banners independently of list rendering so cached list data
remains visible when `phase === 'error'` and `data` is non-null.

- [ ] **Step 6: Run focused and regression tests**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-panels.test.tsx src/test/observability-sidebar.test.tsx src/test/observability-navigation.test.tsx
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Browser checkpoint for CV History and LLM Chunks**

Rebuild the stack from repository root before opening the browser:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
```

At `http://localhost:5173`, select an archived synthetic CV, verify unavailable
files disable the command, select an available file, switch to Chunks, expand
one ordinal, collapse it, and expand another if available. Test at 420px and
360px sidebar widths. Expected: one selected detail, no nested card, no text
overflow, and no sensitive full text before explicit expansion.

- [ ] **Step 8: Commit list panels**

```powershell
git add frontend/src/features/observability/CvHistoryPanel.tsx frontend/src/features/observability/ChunkPanel.tsx frontend/src/features/observability/observability.css frontend/src/test/observability-panels.test.tsx
git commit -m "feat: streamline CV and chunk inspection"
```

### Task 6: Convert Agent Runs To A Status List And Tool Timeline

**Files:**
- Modify: `frontend/src/features/observability/RunHistoryPanel.tsx`
- Modify: `frontend/src/features/observability/observability.css`
- Test: `frontend/src/test/observability-panels.test.tsx`

- [ ] **Step 1: Add a failing run hierarchy test**

```tsx
it('shows run status, duration, safe metadata, and a tool timeline', async () => {
  renderObservabilitySidebar(mockObservabilityApi());
  await userEvent.click(screen.getByRole('tab', {name: 'Agent runs'}));
  const run = await screen.findByTestId(`jobagent-obs-run-toggle-${RUN_ID}`);
  expect(run).toHaveTextContent('Completed');
  expect(run).toHaveTextContent('1 min');
  await userEvent.click(run);
  const detail = await screen.findByTestId(`jobagent-obs-run-detail-${RUN_ID}`);
  expect(detail).toHaveTextContent(MSG_ID);
  expect(detail).toHaveTextContent('propose_profile_from_cv');
  expect(detail).toHaveTextContent('12 ms');
  expect(detail).not.toHaveTextContent('arguments');
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-panels.test.tsx
```

Expected: FAIL on the new list/detail contract.

- [ ] **Step 3: Implement the divided run list**

Map run states locally to Astryx variants without creating aliases:

```ts
const RUN_VARIANT = {
  running: 'accent',
  interrupted: 'warning',
  completed: 'success',
  failed: 'error',
} as const;

const RUN_LABEL = {
  running: 'Running',
  interrupted: 'Interrupted',
  completed: 'Completed',
  failed: 'Failed',
} as const;
```

Use `ListItem` as the only row interaction. Its visible description includes
the exact run state, formatted timestamp, tool count, safe error code, and
computed run duration when `completed_at` is present. Keep state vocabulary
`running|interrupted|completed|failed` unchanged in data/state; `RUN_LABEL`
provides display capitalization only.

- [ ] **Step 4: Render selected metadata and tool timeline outside the row**

The detail region contains one `MetadataList` with Run ID, User message ID,
Created, Completed, related attachment count, and related job count. Render tool
executions with Astryx `StatusDot`, `Text`, `HStack`, and `VStack` plus one CSS
timeline rule. Each tool shows only:

```tsx
<Text type="body">{tool.tool_name}</Text>
<Text type="supporting" color="secondary">
  {tool.status}
  {tool.duration_ms == null ? '' : ` · ${formatDurationMs(tool.duration_ms)}`}
</Text>
{tool.summary ? <Text type="supporting">{tool.summary}</Text> : null}
{tool.error_code ? <Text type="supporting">{tool.error_code}</Text> : null}
```

Do not add prompts, arguments, checkpoints, stack traces, or provider fields.

- [ ] **Step 5: Run tests and typecheck**

Run from `frontend/`:

```powershell
npm test -- --run src/test/observability-panels.test.tsx src/test/observability-api.test.ts src/test/observability-sidebar.test.tsx
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Browser checkpoint for Agent Runs**

Rebuild the stack from repository root before opening the browser:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
```

At `http://localhost:5173`, inspect completed, interrupted, and failed synthetic
runs. Expand and collapse multiple rows. Expected: only one detail is open,
status is readable without color, long IDs wrap, and no tool detail leaks
forbidden fields.

- [ ] **Step 7: Commit Agent Runs**

```powershell
git add frontend/src/features/observability/RunHistoryPanel.tsx frontend/src/features/observability/observability.css frontend/src/test/observability-panels.test.tsx
git commit -m "feat: add compact agent run timeline"
```

### Task 7: Build The Deterministic Graph Presentation Model

**Files:**
- Create: `frontend/src/features/observability/graphPresentation.ts`
- Create: `frontend/src/test/graph-presentation.test.ts`

- [ ] **Step 1: Write failing graph mapping tests**

```ts
import {describe, expect, it} from 'vitest';

import {toGraphModel} from '../features/observability/graphPresentation';
import {graphReady} from './support/observability';

describe('graph presentation mapping', () => {
  it('namespaces and sorts bounded nodes and resolves directed edges', () => {
    const model = toGraphModel(graphReady());
    expect(model.nodes.map((node) => node.key)).toEqual([
      'candidate:cand-1',
      'job:job-1',
      'skill:python',
    ]);
    expect(model.links).toEqual([
      expect.objectContaining({
        key: 'HAS_SKILL:candidate:cand-1->skill:python',
        source: 'candidate:cand-1',
        target: 'skill:python',
        type: 'HAS_SKILL',
      }),
    ]);
  });

  it('drops an inconsistent edge instead of crashing the graph', () => {
    const snapshot = graphReady();
    snapshot.edges.push({source_id: 'missing', target_id: 'python', type: 'REQUIRES'});
    expect(toGraphModel(snapshot).links).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the test and verify the module is missing**

Run from `frontend/`:

```powershell
npm test -- --run src/test/graph-presentation.test.ts
```

Expected: FAIL because `graphPresentation.ts` does not exist.

- [ ] **Step 3: Define focused graph display types**

```ts
import type {SimulationLinkDatum, SimulationNodeDatum} from 'd3-force';
import type {GraphEdgeType, GraphSnapshot} from './types';

export type GraphNodeKind = 'candidate' | 'job' | 'skill';

export type GraphNodeDatum = SimulationNodeDatum & {
  key: string;
  rawId: string;
  kind: GraphNodeKind;
  label: string;
  metadata: ReadonlyArray<readonly [label: string, value: string]>;
};

export type GraphLinkDatum = SimulationLinkDatum<GraphNodeDatum> & {
  key: string;
  type: GraphEdgeType;
  source: string | GraphNodeDatum;
  target: string | GraphNodeDatum;
};

export type GraphModel = {
  identity: string;
  nodes: GraphNodeDatum[];
  links: GraphLinkDatum[];
};
```

- [ ] **Step 4: Implement exact endpoint resolution and stable ordering**

Use namespaced internal keys while keeping API IDs untouched:

```ts
function sourceKey(type: GraphEdgeType, id: string): string {
  if (type === 'HAS_SKILL') return `candidate:${id}`;
  if (type === 'REQUIRES' || type === 'PREFERS') return `job:${id}`;
  return `skill:${id}`;
}

function targetKey(id: string): string {
  return `skill:${id}`;
}
```

Build Candidate metadata from ID/revision, Job metadata from ID/title/company/
revision, and Skill metadata from canonical name. Sort nodes by
`kind:key`; sort edges by `type:source:target`; filter edges whose resolved
endpoints are absent. Build `identity` by joining the sorted node/link keys so a
refresh with identical graph contents preserves user layout.

- [ ] **Step 5: Run graph mapping tests and typecheck**

Run from `frontend/`:

```powershell
npm test -- --run src/test/graph-presentation.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit the graph model**

```powershell
git add frontend/src/features/observability/graphPresentation.ts frontend/src/test/graph-presentation.test.ts
git commit -m "feat: map observability snapshots to graph data"
```

### Task 8: Add Force Simulation, Node Pinning, Resize, Pan, Zoom, And Fit

**Files:**
- Create: `frontend/src/features/observability/graphSimulation.ts`
- Create: `frontend/src/features/observability/useGraphSimulation.ts`
- Create: `frontend/src/features/observability/useGraphViewport.ts`
- Create: `frontend/src/test/graph-interaction.test.tsx`
- Modify: `frontend/src/test/setup.ts`

- [ ] **Step 1: Write failing controller and fit tests**

```tsx
it('pins a dragged node, keeps it pinned on drop, and releases all pins on reset', () => {
  const controller = createGraphSimulation(
    toGraphModel(graphReady()),
    640,
    420,
    vi.fn(),
  );
  controller.beginDrag('candidate:cand-1');
  controller.dragNode('candidate:cand-1', 120, 140);
  controller.endDrag();
  expect(controller.nodes[0]).toMatchObject({fx: 120, fy: 140});
  controller.resetLayout();
  expect(controller.nodes.every((node) => node.fx == null && node.fy == null)).toBe(true);
  controller.stop();
});

it('calculates a bounded fit transform around positioned nodes', () => {
  const transform = calculateFitTransform(
    [{x: 0, y: 0}, {x: 200, y: 100}],
    {width: 600, height: 400},
    40,
  );
  expect(transform.k).toBeGreaterThan(0);
  expect(transform.k).toBeLessThanOrEqual(4);
});

it('settles synchronously when reduced motion is requested', () => {
  const controller = createGraphSimulation(
    toGraphModel(graphReady()),
    640,
    420,
    vi.fn(),
    {reducedMotion: true},
  );
  expect(
    controller.nodes.every(
      (node) =>
        typeof node.x === 'number' &&
        Number.isFinite(node.x) &&
        typeof node.y === 'number' &&
        Number.isFinite(node.y),
    ),
  ).toBe(true);
  controller.stop();
});
```

- [ ] **Step 2: Run the graph interaction test and verify missing modules fail**

Run from `frontend/`:

```powershell
npm test -- --run src/test/graph-interaction.test.tsx
```

Expected: FAIL because simulation and viewport modules do not exist.

- [ ] **Step 3: Implement an imperative force controller**

`createGraphSimulation` clones model nodes/links and configures exactly these
forces:

```ts
const simulation = forceSimulation(nodes)
  .force(
    'link',
    forceLink<GraphNodeDatum, GraphLinkDatum>(links)
      .id((node) => node.key)
      .distance(96)
      .strength(0.7),
  )
  .force('charge', forceManyBody().strength(-260))
  .force('collision', forceCollide<GraphNodeDatum>().radius(38).strength(0.9))
  .force('center', forceCenter(width / 2, height / 2))
  .on('tick', onTick);
```

Accept an optional `{reducedMotion?: boolean}` configuration and return
`{nodes, links, resize, beginDrag, dragNode, endDrag, resetLayout, stop}`.
`dragNode` sets `x/y/fx/fy`; `endDrag` sets `alphaTarget(0)` without clearing
`fx/fy`; `resetLayout` clears all pins and restarts at alpha 1; `resize` replaces
only the center force so current nodes and pins survive. When reduced motion is
true, stop the timer, run a bounded synchronous `simulation.tick(120)`, and call
`onTick` once. Reset uses another bounded synchronous settle instead of an
animated restart.

- [ ] **Step 4: Wrap controller lifecycle in `useGraphSimulation`**

The hook creates a controller only when `model.identity` changes, calls
`controller.resize(width, height)` on size changes, increments a render revision
on D3 ticks, and calls `controller.stop()` in effect cleanup. Export the
controller factory type so the test can inject a fake factory and assert cleanup
without waiting for D3 timers. Read
`window.matchMedia('(prefers-reduced-motion: reduce)').matches` and pass it to
the controller; do not create a second animation path in `GraphCanvas`.

- [ ] **Step 5: Implement viewport size, D3 zoom, pan, fit, and coordinate inversion**

`useGraphViewport(containerRef, svgRef, nodes, identity)` must:

```ts
export function calculateFitTransform(
  nodes: ReadonlyArray<{x?: number; y?: number}>,
  size: {width: number; height: number},
  padding = 40,
) {
  const points = nodes.filter(
    (node): node is {x: number; y: number} =>
      typeof node.x === 'number' &&
      Number.isFinite(node.x) &&
      typeof node.y === 'number' &&
      Number.isFinite(node.y),
  );
  if (points.length === 0) return zoomIdentity;
  const minX = Math.min(...points.map((node) => node.x));
  const maxX = Math.max(...points.map((node) => node.x));
  const minY = Math.min(...points.map((node) => node.y));
  const maxY = Math.max(...points.map((node) => node.y));
  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  const scale = Math.min(
    4,
    Math.max(
      0.25,
      Math.min(
        Math.max(1, size.width - padding * 2) / spanX,
        Math.max(1, size.height - padding * 2) / spanY,
      ),
    ),
  );
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  return zoomIdentity
    .translate(size.width / 2 - centerX * scale, size.height / 2 - centerY * scale)
    .scale(scale);
}
```

Then configure D3 zoom:

```ts
const behavior = zoom<SVGSVGElement, unknown>()
  .scaleExtent([0.25, 4])
  .filter((event) => {
    const target = event.target;
    return !(target instanceof Element && target.closest('[data-graph-node]'));
  })
  .on('zoom.jobagent', (event) => setTransform(event.transform));
```

Observe the container with `ResizeObserver`; update `{width,height}` without
recreating the force controller. `toGraphPoint(clientX, clientY)` subtracts the
SVG bounding rect then uses `transform.invert`. `fitView()` calls
`behavior.transform` with `calculateFitTransform`. Auto-fit once per new
`identity`, after the first tick in which every node has finite coordinates;
explicit Fit never releases pins. Cleanup disconnects the observer and removes
`.zoom` listeners from the SVG selection.

- [ ] **Step 6: Make the shared ResizeObserver stub callback-capable**

Update `frontend/src/test/setup.ts` so the stub stores the constructor callback
and calls it from `observe` with the target's current bounding rectangle. Keep
the existing global/window assignments and existing chat tests compatible.

- [ ] **Step 7: Run interaction tests and regressions**

Run from `frontend/`:

```powershell
npm test -- --run src/test/graph-interaction.test.tsx src/test/chat-page.test.tsx
npm run typecheck
```

Expected: PASS with no pending D3 timers after unmount.

- [ ] **Step 8: Commit graph interaction infrastructure**

```powershell
git add frontend/src/features/observability/graphSimulation.ts frontend/src/features/observability/useGraphSimulation.ts frontend/src/features/observability/useGraphViewport.ts frontend/src/test/graph-interaction.test.tsx frontend/src/test/setup.ts
git commit -m "feat: add interactive graph layout engine"
```

### Task 9: Render The SVG Graph And Semantic Fallback

**Files:**
- Create: `frontend/src/features/observability/GraphCanvas.tsx`
- Create: `frontend/src/features/observability/GraphSemanticList.tsx`
- Modify: `frontend/src/features/observability/GraphPanel.tsx`
- Modify: `frontend/src/features/observability/observability.css`
- Test: `frontend/src/test/graph-interaction.test.tsx`
- Test: `frontend/src/test/observability-sidebar.test.tsx`

- [ ] **Step 1: Add failing SVG and fallback tests**

Define this test helper in `graph-interaction.test.tsx`:

Import `render`, `screen`, and `within` from Testing Library; `Theme`,
`neutralTheme`, `GraphPanel`, `GraphSnapshot`, and `vi` from their existing
package/project modules.

```tsx
function renderGraphPanel(snapshot: GraphSnapshot) {
  return render(
    <Theme theme={neutralTheme}>
      <GraphPanel
        resource={{phase: 'ready', data: snapshot, error: null, loaded: true}}
        onRefresh={vi.fn()}
      />
    </Theme>,
  );
}
```

```tsx
it('renders typed nodes, directed labeled edges, controls, and safe metadata', async () => {
  renderGraphPanel(graphReady());
  const graph = await screen.findByRole('group', {
    name: 'Candidate, jobs and skills network',
  });
  expect(graph).toBeInTheDocument();
  expect(screen.getByTestId('jobagent-graph-node-candidate:cand-1')).toHaveTextContent('Candidate');
  expect(within(graph).getByText('HAS_SKILL')).toBeInTheDocument();
  expect(screen.getByRole('button', {name: 'Fit view'})).toBeInTheDocument();
  expect(screen.getByRole('button', {name: 'Reset layout'})).toBeInTheDocument();
  await userEvent.click(screen.getByTestId('jobagent-graph-node-candidate:cand-1'));
  expect(screen.getByTestId('jobagent-graph-selected-metadata')).toHaveTextContent('cand-1');
});

it('keeps a readable semantic list and stale warning', async () => {
  const snapshot = graphReady();
  snapshot.status = 'stale';
  renderGraphPanel(snapshot);
  expect(await screen.findByTestId('jobagent-obs-graph-status-stale')).toBeInTheDocument();
  await userEvent.click(screen.getByText('Graph data'));
  expect(screen.getByText(/cand-1.*HAS_SKILL.*python/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test and verify graph UI fails**

Run from `frontend/`:

```powershell
npm test -- --run src/test/graph-interaction.test.tsx src/test/observability-sidebar.test.tsx
```

Expected: FAIL because the current GraphPanel is semantic-list-first and has no
SVG, D3 interactions, or graph controls.

- [ ] **Step 3: Update the existing graph regression assertion**

In `observability-sidebar.test.tsx`, replace the semantic-list-first assertion
with an SVG-first assertion, then explicitly open the fallback:

```tsx
expect(await screen.findByRole('group', {
  name: 'Candidate, jobs and skills network',
})).toBeInTheDocument();
expect(screen.getByTestId('jobagent-obs-graph-meta')).toHaveTextContent(
  /nodes truncated \(\+2\)/,
);
await userEvent.click(screen.getByText('Graph data'));
expect(screen.getByTestId('jobagent-obs-graph-skills')).toHaveTextContent('python');
expect(screen.getByTestId('jobagent-obs-graph-edges')).toHaveTextContent('HAS_SKILL');
```

- [ ] **Step 4: Implement `GraphCanvas`**

Compose `useGraphSimulation` and `useGraphViewport`. Render one responsive SVG:

```tsx
const arrowMarkerId = useId().replaceAll(':', '');

<svg
  ref={svgRef}
  role="group"
  aria-label="Candidate, jobs and skills network"
  className="jobagent-graph-svg"
  viewBox={`0 0 ${size.width} ${size.height}`}
>
  <defs>
    <marker id={arrowMarkerId} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
      <path d="M0,0 L8,4 L0,8 Z" className="jobagent-graph-arrow" />
    </marker>
  </defs>
  <g transform={transform.toString()}>
    {links.map((link) => <GraphEdgeView key={link.key} link={link} markerId={arrowMarkerId} />)}
    {nodes.map((node) => <GraphNodeView key={node.key} node={node} />)}
  </g>
</svg>
```

Edges render before nodes. Every edge has a line/path, `markerEnd`, and a
centered relationship label with a token-based label background. Every node is
a focusable `<g role="button" tabIndex={0}>` with circle and text, exact test ID,
safe accessible name, selected state, pointer capture, and drag handlers that
convert client coordinates through `toGraphPoint`. Define `GraphEdgeView` and
`GraphNodeView` as file-local components in `GraphCanvas.tsx`; `GraphNodeView`
must select on click and on Enter/Space so SVG interaction is not pointer-only.

Above the SVG, use Astryx `Button` controls labeled `Fit view` and
`Reset layout`. Below it, show a visible Candidate/Job/Skill legend and an
unframed Astryx `MetadataList` for the selected node. Do not add a canvas, raw
HTML button, or non-Astryx toolbar.

- [ ] **Step 5: Implement `GraphSemanticList`**

Use an uncontrolled Astryx `Collapsible` with `defaultIsOpen={false}` and
trigger `Graph data`. Inside, render three Astryx `List` sections for nodes and
relationships. Relationship labels use the exact form:

```tsx
`${edge.source_id} —${edge.type}→ ${edge.target_id}`
```

Include server truncation/omitted counts. The list receives the original typed
snapshot, not D3-mutated data.

- [ ] **Step 6: Integrate graph resource states in `GraphPanel`**

Use `toGraphModel(snapshot)` only for `ready` or `stale` snapshots with nodes.
Show:

- SVG + warning Banner for `stale`.
- Error Banner and no current graph for `unavailable`.
- SVG + cached refresh error Banner when request phase is error but safe data exists.
- Graph-shaped Astryx Skeleton for initial loading.
- Context-specific compact EmptyState when ready data has no nodes.
- Summary, checked time, and exact truncation metadata above the canvas.

Keep the semantic fallback mounted whenever snapshot data exists.

- [ ] **Step 7: Add token-based graph CSS**

```css
.jobagent-graph-canvas {
  position: relative;
  width: 100%;
  height: clamp(20rem, 48vh, 30rem);
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-container);
  background: var(--color-background-surface);
  touch-action: none;
}

.jobagent-graph-node--candidate circle {
  fill: var(--color-background-green);
  stroke: var(--color-border-green);
}

.jobagent-graph-node--job circle {
  fill: var(--color-background-purple);
  stroke: var(--color-border-purple);
}

.jobagent-graph-node--skill circle {
  fill: var(--color-background-blue);
  stroke: var(--color-border-blue);
}

.jobagent-graph-edge {
  stroke: var(--color-border-gray);
  fill: none;
}

.jobagent-graph-arrow {
  fill: var(--color-border-gray);
  stroke: none;
}
```

Use Astryx spacing, radius, text, border, and color variables throughout. Add a
clear focus ring and selected-node stroke. Do not hardcode graph palette hex
values.

- [ ] **Step 8: Run graph, sidebar, and build checks**

Run from `frontend/`:

```powershell
npm test -- --run src/test/graph-presentation.test.ts src/test/graph-interaction.test.tsx src/test/observability-sidebar.test.tsx src/test/observability-api.test.ts
npm run lint
npm run typecheck
npm run build
```

Expected: PASS; the only allowed build warning is the existing Vite chunk-size warning.

- [ ] **Step 9: Browser checkpoint for the complete graph**

Rebuild the stack from repository root before opening the browser:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
```

At `http://localhost:5173`, verify a nonblank network at desktop and 390px mobile:

1. Count visible Candidate/Job/Skill circles and relationship labels.
2. Drag one node and verify it remains at the drop position while neighbors settle.
3. Pan the empty canvas area.
4. Wheel/pinch zoom and verify the SVG transform changes.
5. Click Fit and verify every node is framed.
6. Click Reset and verify manual pins release and layout restarts.
7. Select/focus nodes and inspect only allowlisted metadata.
8. Open Graph data and compare node/edge counts to the canvas/server metadata.
9. Inspect stale, unavailable, truncated, and cached refresh-error states.
10. Confirm no blank SVG, overlapping controls, trapped gestures, or console errors.

- [ ] **Step 10: Commit the complete graph UI**

```powershell
git add frontend/src/features/observability/GraphCanvas.tsx frontend/src/features/observability/GraphSemanticList.tsx frontend/src/features/observability/GraphPanel.tsx frontend/src/features/observability/observability.css frontend/src/test/graph-interaction.test.tsx frontend/src/test/observability-sidebar.test.tsx
git commit -m "feat: render interactive Neo4j graph"
```

### Task 10: Full Regression, Compose, And Final Browser Acceptance

**Files:**
- Modify only if verification exposes a scoped defect in the files above.

- [ ] **Step 1: Run all frontend automated checks from a fresh attempt**

Run from `frontend/`:

```powershell
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: every test passes; lint/typecheck/build exit 0; only the existing Vite
chunk-size warning is permitted.

- [ ] **Step 2: Re-run unaffected backend observability contracts**

Run from `backend/`:

```powershell
py -3.13 -m pytest tests/unit/test_observability_graph.py tests/integration/test_observability_api.py -q
```

Expected: PASS with no backend source diff.

- [ ] **Step 3: Rebuild and wait for the local stack**

Run from repository root:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
docker compose --env-file .env -f infrastructure/docker-compose.yml ps
```

Expected: frontend, backend, and Neo4j are healthy; FE remains
`http://localhost:5173`, BE remains `http://localhost:8000`.

- [ ] **Step 4: Run the complete browser matrix**

Use the in-app browser and synthetic data only. Repeat the design-spec browser
sequence at 1440x900, 1024x768, and 390x844. Test Overview, CV History, Chunks,
Graph, Runs, resize, collapsed rail, automatic mobile drawer, initial loading,
empty, cached refresh error, stale, unavailable, and truncated graph states.
Inspect browser console after each major view.

Expected: no visual overlap, overflow, blank graph, inaccessible control,
forbidden data, 5xx response, or console error; chat and composer remain usable.

- [ ] **Step 5: Check scope and file hygiene**

Run from repository root:

```powershell
git diff --check
git status --short
git diff --name-only 4be4b0a..HEAD
```

Expected: only the planned frontend files, tests, dependency lock, and approved
design/plan documentation are changed. `.env`, backend source, and real CV data
are untouched. Preserve any pre-existing unrelated `.gitignore` modification.

- [ ] **Step 6: Commit only scoped verification fixes if needed**

If Step 1–5 required a scoped correction, stage the exact corrected files and
commit:

```powershell
git commit -m "fix: complete observability UI acceptance"
```

If no correction was needed, do not create an empty commit.

- [ ] **Step 7: Report evidence**

Report the final test counts, lint/typecheck/build status, backend focused test
result, Compose health, browser viewport matrix, graph interactions exercised,
and any residual warning. Do not claim completion without fresh output from
Steps 1–5.
