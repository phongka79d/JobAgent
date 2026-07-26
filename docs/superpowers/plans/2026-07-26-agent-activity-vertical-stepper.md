# Agent Activity Vertical Stepper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace standalone Agent activity dots with a rounded Astryx Card containing a collapsed summary and an expanded, vertically connected status stepper.

**Architecture:** Keep `runSummary`, `formatDuration`, and `activityDetail` as the existing presentation-rule owners. Add local controlled disclosure state solely to transfer the one visible running Spinner between the collapsed summary and expanded running row; render terminal markers with Astryx Icon and draw the decorative dashed rail with token-only CSS.

**Tech Stack:** React 19, TypeScript 5.9, Astryx 0.1.4 (`Card`, `Collapsible`, `Divider`, `Icon`, `Spinner`, stacks, and text), CSS design tokens, Vitest, Testing Library, Docker Compose, in-app browser.

---

## Scope and file map

This is one frontend presentation slice. Do not change the durable activity
schema, reducer, SSE, history hydration, backend, dependencies, assistant answer
rendering, job cards, approval cards, or composer.

**Modify only:**

- `frontend/src/features/chat/components/AgentActivityTimeline.tsx` — owns the Card, controlled disclosure, aggregate marker, activity marker mapping, and existing safe summary/detail text.
- `frontend/src/features/chat/components/agent-activity.css` — owns only full-width disclosure alignment, the fixed marker column, dashed connector, and existing shimmer/reduced-motion styling.
- `frontend/src/test/agent-activity-timeline.test.tsx` — proves Card/disclosure structure, state markers, connector hooks, single visible Spinner, summaries, durable projection, and privacy.

**Create for workflow tracking only:**

- `docs/superpowers/plans/2026-07-26-agent-activity-vertical-stepper.md` — this plan; mark every completed execution step `[x]` immediately after its command or edit succeeds.

## Task 1: Prepare the isolated frontend baseline

**Files:**

- Read: `frontend/AGENTS.md`
- Read: `docs/superpowers/specs/2026-07-26-agent-activity-vertical-stepper-design.md`
- Read: `frontend/src/features/chat/components/AgentActivityTimeline.tsx`
- Read: `frontend/src/features/chat/components/agent-activity.css`
- Read: `frontend/src/test/agent-activity-timeline.test.tsx`
- No production files change.

- [ ] **Step 1: Set up or enter the requested worktree**

Use `superpowers:using-git-worktrees`. Detect isolation first:

```powershell
$gitDir = git rev-parse --path-format=absolute --git-dir
$gitCommonDir = git rev-parse --path-format=absolute --git-common-dir
$branch = git branch --show-current
git worktree list --porcelain
```

Expected: if `$gitDir -eq $gitCommonDir`, create a linked worktree for branch
`feat/agent-thinking-status` using the skill's directory-selection and ignore
checks. If the branch/worktree already exists, enter it rather than creating a
duplicate. All remaining commands run from that worktree.

- [ ] **Step 2: Confirm the exact Astryx public contracts**

Run from `frontend`:

```powershell
npx astryx build "rounded collapsible agent activity vertical stepper" --detail compact
npx astryx component Card --detail compact
npx astryx component Collapsible --detail compact
npx astryx component Divider --detail compact
npx astryx component Icon --detail compact
npx astryx component Spinner --detail compact
npx astryx docs tokens --detail compact
```

Expected: Card supports `width="100%"` and `padding={3}`; Collapsible supports
controlled `isOpen`/`onOpenChange`; semantic Icon names include `success`,
`error`, `warning`, and `clock`; Spinner supports `size="sm"` and an
`aria-label`; no public Timeline component exists.

- [ ] **Step 3: Restore dependencies in the worktree**

Run:

```powershell
Set-Location frontend
npm ci --no-audit --no-fund
```

Expected: exit `0` with Astryx packages at `0.1.4`.

- [ ] **Step 4: Run the focused baseline tests**

Run:

```powershell
npm run test -- --run src/test/agent-activity-timeline.test.tsx src/test/chat-page.test.tsx
```

Expected: both files pass before edits. Stop and report any baseline failure;
do not hide it inside this visual change.

## Task 2: Build the Card and vertical status stepper with TDD

**Files:**

- Modify: `frontend/src/test/agent-activity-timeline.test.tsx`
- Modify: `frontend/src/features/chat/components/AgentActivityTimeline.tsx`
- Modify: `frontend/src/features/chat/components/agent-activity.css`

- [ ] **Step 1: Add the four-state activity fixture**

Add this helper after `terminalRun` in
`frontend/src/test/agent-activity-timeline.test.tsx`:

```tsx
function markerRun(): ClientRun {
  return {
    ...runningRun(),
    activities: [
      agentActivity(),
      agentActivity({
        activityId: '33333333-3333-4333-8333-333333333333',
        sequence: 1,
        label: 'Wait for dependency',
        technicalName: 'wait_for_dependency',
        state: 'pending',
        startedAt: TS_NEW,
        updatedAt: TS_NEW,
        completedAt: null,
        durationMs: null,
      }),
      agentActivity({
        activityId: '44444444-4444-4444-8444-444444444444',
        sequence: 2,
        label: 'Check provider response',
        technicalName: 'check_provider_response',
        state: 'failed',
        startedAt: TS_NEW,
        updatedAt: TS_NEW,
        completedAt: TS_NEW,
        durationMs: 40,
        errorCode: 'PROVIDER_UNAVAILABLE',
      }),
      agentActivity({
        activityId: TOOL_ACTIVITY,
        sequence: 3,
        kind: 'tool',
        label: 'Rank matching jobs',
        technicalName: 'match_jobs',
        state: 'running',
        startedAt: TS_NEW,
        updatedAt: TS_NEW,
        completedAt: null,
        durationMs: null,
      }),
    ],
  };
}
```

- [ ] **Step 2: Write failing Card, disclosure, marker, connector, and Spinner tests**

Add these tests inside the existing `describe('AgentActivityTimeline', ...)`
block. Preserve the existing durable projection and pre-run notice tests.

```tsx
it('uses one Card and moves the single running Spinner when expanded', async () => {
  const user = userEvent.setup();
  render(timeline(runningRun()));

  const card = screen.getByTestId('jobagent-agent-activity-card');
  expect(card).toHaveClass('astryx-card');

  const disclosure = screen.getByRole('button', {
    name: /Rank matching jobs/i,
  });
  expect(disclosure).toHaveAttribute('aria-expanded', 'false');
  expect(disclosure).toHaveStyle({width: '100%'});
  expect(disclosure.parentElement).toHaveClass(
    'jobagent-agent-activity-disclosure',
  );
  expect(
    screen.getByTestId('jobagent-agent-activity-list'),
  ).not.toBeVisible();
  expect(
    screen.getByTestId('jobagent-agent-activity-summary-marker'),
  ).toHaveAttribute('data-marker', 'spinner');
  expect(
    screen.getAllByRole('status', {name: 'Running: Rank matching jobs'}),
  ).toHaveLength(1);

  await user.click(disclosure);

  expect(disclosure).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByTestId('jobagent-agent-activity-list')).toBeVisible();
  expect(
    screen.getByTestId('jobagent-agent-activity-summary-marker'),
  ).toHaveAttribute('data-marker', 'clock');
  expect(
    screen.getAllByRole('status', {name: 'Running: Rank matching jobs'}),
  ).toHaveLength(1);
});

it('maps activity states and exposes connector-safe last-row hooks', async () => {
  const user = userEvent.setup();
  render(timeline(markerRun()));

  await user.click(
    screen.getByRole('button', {name: /Rank matching jobs/i}),
  );

  const list = screen.getByTestId('jobagent-agent-activity-list');
  const rows = Array.from(
    list.querySelectorAll<HTMLElement>('[data-testid^="jobagent-agent-activity-row-"]'),
  );
  expect(rows).toHaveLength(4);
  expect(rows.map((row) => row.dataset.last)).toEqual([
    'false',
    'false',
    'false',
    'true',
  ]);
  expect(rows.map((row) => row.dataset.state)).toEqual([
    'completed',
    'pending',
    'failed',
    'running',
  ]);
  expect(
    rows.map(
      (row) =>
        row.querySelector<HTMLElement>('[data-marker]')?.dataset.marker,
    ),
  ).toEqual(['success', 'clock', 'error', 'spinner']);

  expect(
    screen.getByText('response_generation · completed · 25ms'),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      'check_provider_response · failed · 40ms · PROVIDER_UNAVAILABLE',
    ),
  ).toBeInTheDocument();
  expect(screen.getByText('match_jobs · running')).toBeInTheDocument();
});

it('uses warning markers for interrupted and disconnected summaries', () => {
  const view = render(timeline(terminalRun('interrupted'), 'idle'));
  expect(
    screen.getByTestId('jobagent-agent-activity-summary-marker'),
  ).toHaveAttribute('data-marker', 'warning');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();

  view.rerender(timeline(runningRun(), 'disconnected'));
  expect(
    screen.getByTestId('jobagent-agent-activity-summary-marker'),
  ).toHaveAttribute('data-marker', 'warning');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('renders an empty activity run in a non-disclosure Card', () => {
  render(
    timeline({
      ...runningRun(),
      activities: [],
    }),
  );

  expect(screen.getByTestId('jobagent-agent-activity-card')).toHaveClass(
    'astryx-card',
  );
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(
    screen.getByRole('status', {name: 'Running: Connecting…'}),
  ).toBeInTheDocument();
});
```

In the existing summary test, add these assertions after each render/rerender:

```tsx
expect(
  screen.getByTestId('jobagent-agent-activity-summary-marker'),
).toHaveAttribute('data-marker', 'success');
expect(screen.getByText('Completed · 2 steps')).toHaveAttribute(
  'data-running',
  'false',
);

expect(
  screen.getByTestId('jobagent-agent-activity-summary-marker'),
).toHaveAttribute('data-marker', 'warning');
expect(
  screen.getByText('Waiting for your confirmation · 2 steps'),
).toHaveAttribute('data-running', 'false');

expect(
  screen.getByTestId('jobagent-agent-activity-summary-marker'),
).toHaveAttribute('data-marker', 'error');
expect(screen.getByText('Unable to complete · 2 steps')).toHaveAttribute(
  'data-running',
  'false',
);

expect(
  screen.getByTestId('jobagent-agent-activity-summary-marker'),
).toHaveAttribute('data-marker', 'warning');
expect(
  screen.getByText('Connection lost — Agent may still be running'),
).toHaveAttribute('data-running', 'false');
```

Keep and strengthen the existing privacy assertion in the expansion test:

```tsx
expect(document.body).not.toHaveTextContent(
  /arguments|result|provider_payload|raw cv|cv_text/i,
);
```

- [ ] **Step 3: Run the focused test to verify RED**

Run from `frontend`:

```powershell
npm run test -- --run src/test/agent-activity-timeline.test.tsx
```

Expected: new tests fail because there is no Card test ID, controlled marker
transfer, semantic Icon/Spinner mapping, or `data-last` row hook. Existing tests
must not be the source of failure.

- [ ] **Step 4: Replace the timeline component with the minimal implementation**

Replace `frontend/src/features/chat/components/AgentActivityTimeline.tsx` with:

```tsx
import {useState} from 'react';
import {Card} from '@astryxdesign/core/Card';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Divider} from '@astryxdesign/core/Divider';
import {HStack} from '@astryxdesign/core/HStack';
import {Icon} from '@astryxdesign/core/Icon';
import {Spinner} from '@astryxdesign/core/Spinner';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {
  ClientAgentActivity,
  ClientRun,
  StreamPhase,
} from '../reducer';
import './agent-activity.css';

type MarkerKind = 'clock' | 'error' | 'spinner' | 'success' | 'warning';

function countLabel(count: number): string {
  return `${count} ${count === 1 ? 'step' : 'steps'}`;
}

function latestActivity(
  activities: readonly ClientAgentActivity[],
): ClientAgentActivity | null {
  const running = [...activities]
    .reverse()
    .find((item) => item.state === 'running');
  return running ?? activities.at(-1) ?? null;
}

function runSummary(run: ClientRun, streamPhase: StreamPhase): string {
  const count = countLabel(run.activities.length);
  if (streamPhase === 'disconnected' && run.state === 'running') {
    return 'Connection lost — Agent may still be running';
  }
  if (run.state === 'interrupted') {
    return `Waiting for your confirmation · ${count}`;
  }
  if (run.state === 'completed') {
    return `Completed · ${count}`;
  }
  if (run.state === 'failed') {
    return `Unable to complete · ${count}`;
  }
  return latestActivity(run.activities)?.label ?? 'Connecting…';
}

function formatDuration(durationMs: number | null): string | null {
  if (durationMs === null) {
    return null;
  }
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  const seconds = durationMs / 1000;
  return `${durationMs % 1000 === 0 ? String(seconds) : seconds.toFixed(1)}s`;
}

function activityDetail(activity: ClientAgentActivity): string {
  return [
    activity.technicalName,
    activity.state,
    formatDuration(activity.durationMs),
    activity.errorCode,
  ]
    .filter((value): value is string => Boolean(value))
    .join(' · ');
}

function activityMarkerKind(
  state: ClientAgentActivity['state'],
): MarkerKind {
  if (state === 'completed') {
    return 'success';
  }
  if (state === 'failed') {
    return 'error';
  }
  if (state === 'running') {
    return 'spinner';
  }
  return 'clock';
}

function runMarkerKind(
  run: ClientRun,
  streamPhase: StreamPhase,
  isOpen: boolean,
): MarkerKind {
  if (streamPhase === 'disconnected' && run.state === 'running') {
    return 'warning';
  }
  if (run.state === 'completed') {
    return 'success';
  }
  if (run.state === 'failed') {
    return 'error';
  }
  if (run.state === 'interrupted') {
    return 'warning';
  }
  return isOpen ? 'clock' : 'spinner';
}

function StatusMarker({
  kind,
  label,
  testId,
  clockColor = 'secondary',
}: {
  kind: MarkerKind;
  label: string;
  testId: string;
  clockColor?: 'accent' | 'secondary';
}) {
  return (
    <span
      className="jobagent-agent-activity-marker"
      data-marker={kind}
      data-testid={testId}>
      {kind === 'spinner' ? (
        <Spinner size="sm" aria-label={`Running: ${label}`} />
      ) : (
        <Icon
          icon={kind}
          size="sm"
          color={kind === 'clock' ? clockColor : kind}
        />
      )}
    </span>
  );
}

export function AgentActivityTimeline({
  run,
  streamPhase,
}: {
  run: ClientRun;
  streamPhase: StreamPhase;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const summary = runSummary(run, streamPhase);
  const isRunning = run.state === 'running' && streamPhase !== 'disconnected';
  const hasActivities = run.activities.length > 0;
  const summaryMarker = runMarkerKind(run, streamPhase, isOpen);
  const header = (
    <HStack gap={1} align="center" width="100%">
      <StatusMarker
        kind={summaryMarker}
        label={summary}
        testId="jobagent-agent-activity-summary-marker"
        clockColor="accent"
      />
      <VStack gap={0} width="100%">
        <Text
          type="label"
          as="span"
          aria-live="polite"
          aria-atomic="true"
          className="jobagent-agent-activity-label"
          data-running={isRunning ? 'true' : 'false'}>
          {summary}
        </Text>
        {hasActivities ? (
          <Text type="supporting" color="secondary" as="span">
            {run.state === 'running'
              ? `View activity · ${countLabel(run.activities.length)}`
              : 'View activity'}
          </Text>
        ) : null}
      </VStack>
    </HStack>
  );

  return (
    <Card
      width="100%"
      padding={3}
      data-testid="jobagent-agent-activity-card">
      {hasActivities ? (
        <Collapsible
          trigger={header}
          isOpen={isOpen}
          onOpenChange={setIsOpen}
          className="jobagent-agent-activity-disclosure">
          <VStack
            gap={2}
            width="100%"
            data-testid="jobagent-agent-activity-list">
            <Divider />
            <VStack gap={0} width="100%">
              {run.activities.map((activity, index) => {
                const isLast = index === run.activities.length - 1;
                return (
                  <HStack
                    key={activity.activityId}
                    gap={2}
                    vAlign="start"
                    className="jobagent-agent-activity-step"
                    data-testid={`jobagent-agent-activity-row-${activity.activityId}`}
                    data-state={activity.state}
                    data-last={isLast ? 'true' : 'false'}>
                    <StatusMarker
                      kind={activityMarkerKind(activity.state)}
                      label={activity.label}
                      testId={`jobagent-agent-activity-marker-${activity.activityId}`}
                    />
                    <VStack gap={0} width="100%">
                      <Text type="body">{activity.label}</Text>
                      <Text type="supporting" color="secondary">
                        {activityDetail(activity)}
                      </Text>
                    </VStack>
                  </HStack>
                );
              })}
            </VStack>
          </VStack>
        </Collapsible>
      ) : (
        header
      )}
    </Card>
  );
}
```

Do not move or duplicate `runSummary`, `formatDuration`, or `activityDetail`.
The new helpers map visual markers only; adjacent text remains authoritative.

- [ ] **Step 5: Replace the CSS with token-only layout and connector styling**

Replace `frontend/src/features/chat/components/agent-activity.css` with:

```css
.jobagent-agent-activity-disclosure,
.jobagent-agent-activity-disclosure > button {
  width: 100%;
}

.jobagent-agent-activity-disclosure > button > span:first-child {
  flex: 1 1 auto;
  min-width: 0;
}

.jobagent-agent-activity-step {
  position: relative;
  padding-block-end: var(--spacing-2);
}

.jobagent-agent-activity-step[data-last='true'] {
  padding-block-end: 0;
}

.jobagent-agent-activity-marker {
  position: relative;
  display: inline-flex;
  flex: 0 0 var(--spacing-5);
  align-items: center;
  justify-content: center;
  width: var(--spacing-5);
  min-height: var(--spacing-5);
}

.jobagent-agent-activity-step[data-last='false']::after {
  position: absolute;
  inset-block-start: var(--spacing-5);
  inset-block-end: calc(-1 * var(--spacing-2));
  inset-inline-start: calc(var(--spacing-2) + var(--spacing-0-5));
  border-inline-start: var(--border-width) dashed
    var(--color-border-emphasized);
  content: '';
}

.jobagent-agent-activity-label[data-running='true'] {
  color: transparent;
  background-image: linear-gradient(
    90deg,
    var(--color-text-secondary),
    var(--color-text-primary),
    var(--color-text-secondary)
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  animation: jobagent-agent-thinking-shimmer var(--duration-slow-max) linear
    infinite;
}

@keyframes jobagent-agent-thinking-shimmer {
  to {
    background-position: -200% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .jobagent-agent-activity-label[data-running='true'] {
    color: var(--color-text-primary);
    background-image: none;
    animation: none;
  }
}
```

The percentage values animate only relative gradient geometry; every color,
spacing, border width, radius, and duration remains owned by Astryx tokens or
Card.

- [ ] **Step 6: Run the focused test to verify GREEN**

Run:

```powershell
npm run test -- --run src/test/agent-activity-timeline.test.tsx
```

Expected: all timeline tests pass. The collapsed state has one visible summary
Spinner; expanded state has one visible activity Spinner; terminal/disconnected
states have none.

- [ ] **Step 7: Run the chat-page regression test**

Run:

```powershell
npm run test -- --run src/test/chat-page.test.tsx
```

Expected: pass with no reducer, hydration, answer, approval, or job-card changes.

- [ ] **Step 8: Review and commit the focused frontend slice**

Run from the worktree root:

```powershell
git diff -- frontend/src/features/chat/components/AgentActivityTimeline.tsx frontend/src/features/chat/components/agent-activity.css frontend/src/test/agent-activity-timeline.test.tsx
git diff --check
git add frontend/src/features/chat/components/AgentActivityTimeline.tsx frontend/src/features/chat/components/agent-activity.css frontend/src/test/agent-activity-timeline.test.tsx docs/superpowers/plans/2026-07-26-agent-activity-vertical-stepper.md
git commit -m "feat(frontend): add Agent activity vertical stepper"
```

Expected: only the three approved frontend files plus this checkbox plan are in
the commit. Do not include generated files or unrelated changes.

## Task 3: Run full gates and verify the rebuilt app

**Files:**

- No planned source changes. Fix only failures caused by this feature and keep
  any repair within the three approved frontend files.

- [ ] **Step 1: Run all frontend gates**

Run from `frontend`:

```powershell
npm run test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: all commands pass. The existing Vite chunk-size advisory is allowed;
new Astryx, accessibility, CSS, lint, or type errors are not.

- [ ] **Step 2: Verify scope and repository hygiene**

Run from the worktree root:

```powershell
git status --short
git diff --check HEAD^..HEAD
git diff --stat main...HEAD
git diff --name-only main...HEAD
```

Expected: implementation changes remain limited to the three approved frontend
files plus approved design/plan documentation. No backend, dependency, reducer,
SSE, history, or generated-artifact changes appear.

- [ ] **Step 3: Rebuild the existing Docker Compose project without deleting volumes**

Run from the worktree root:

```powershell
$project = 'jobagent-cv-profile-reset-smoke'
if ($project -ne 'jobagent-cv-profile-reset-smoke') {
  throw 'Unexpected Compose project'
}
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project up -d --build
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project ps
```

Expected: frontend, backend, and Neo4j are running/healthy. Do not run
`down -v`; preserve existing local data.

- [ ] **Step 4: Verify the UI in the default in-app browser**

Use `browser:control-in-app-browser`, not Chrome control. Open
`http://localhost:5173/`, reuse the current ready profile/conversation, and
verify:

1. The timeline is enclosed by one rounded Card and the chevron is at the far right.
2. Collapsed state shows only the summary, `View activity`, and one aggregate marker/Spinner.
3. Expanded state shows `(V)`, clock/Spinner, `(X)`, and warning/error icons in a vertical list with dashed connectors.
4. Only the last row has no outgoing connector; labels, technical names, exact states, durations, and safe error codes remain readable.
5. Running state shows exactly one visible Spinner, and terminal/disconnected summary states do not shimmer incorrectly.

Do not inspect cookies, local storage, credentials, raw CV text, provider
payloads, or database paths. Leave the verified app tab open for handoff.

- [ ] **Step 5: Inspect bounded container logs for feature errors**

Run:

```powershell
$project = 'jobagent-cv-profile-reset-smoke'
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project logs --tail 120 frontend
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project logs --tail 120 backend
```

Expected: no frontend runtime, Astryx, SSE, or backend regression errors. Never
print `.env`, credentials, provider payloads, or user content.

- [ ] **Step 6: Mark all successful steps `[x]` and commit the final plan state**

Update this plan immediately after each successful step, then run:

```powershell
git add docs/superpowers/plans/2026-07-26-agent-activity-vertical-stepper.md
git commit -m "docs: complete Agent activity stepper plan"
git status --short --branch
git log --oneline --decorate --max-count=5
```

Expected: clean worktree on `feat/agent-thinking-status`, all completed steps
show `[x]`, and the latest commits contain the focused implementation plus its
verified plan state.
