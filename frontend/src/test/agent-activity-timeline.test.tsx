import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it} from 'vitest';

import {AgentActivityTimeline} from '../features/chat/components/AgentActivityTimeline';
import {activityRunForAssistantDisplay} from '../features/chat/components/ChatMessageRow';
import {ChatMessages} from '../features/chat/components/ChatMessages';
import type {
  ClientAgentActivity,
  ClientMessage,
  ClientRun,
  StreamPhase,
} from '../features/chat/reducer';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const ASSISTANT_ACTIVITY = '11111111-1111-4111-8111-111111111111';
const TOOL_ACTIVITY = '22222222-2222-4222-8222-222222222222';
const TS = '2026-07-25T08:00:00.000Z';
const TS_NEW = '2026-07-25T08:00:01.000Z';

afterEach(cleanup);

function agentActivity(
  overrides: Partial<ClientAgentActivity> = {},
): ClientAgentActivity {
  return {
    activityId: ASSISTANT_ACTIVITY,
    runId: RUN_ID,
    sequence: 0,
    kind: 'assistant',
    label: 'Read active CV',
    technicalName: 'response_generation',
    state: 'completed',
    startedAt: TS,
    updatedAt: TS_NEW,
    completedAt: TS_NEW,
    durationMs: 25,
    errorCode: null,
    source: 'stream',
    ...overrides,
  };
}

function runningRun(): ClientRun {
  return {
    id: RUN_ID,
    userMessageId: null,
    state: 'running',
    pendingApproval: null,
    errorCode: null,
    completedAt: null,
    tools: [],
    activities: [
      agentActivity(),
      agentActivity({
        activityId: TOOL_ACTIVITY,
        sequence: 1,
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

function terminalRun(state: 'completed' | 'failed' | 'interrupted'): ClientRun {
  const run = runningRun();
  return {
    ...run,
    state,
    errorCode: state === 'failed' ? 'AGENT_FAILED' : null,
    completedAt: state === 'completed' || state === 'failed' ? TS_NEW : null,
    activities: run.activities.map((item) =>
      item.state === 'running'
        ? {
            ...item,
            state: 'completed',
            completedAt: TS_NEW,
            durationMs: 40,
          }
        : item,
    ),
  };
}

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

function timeline(run: ClientRun, streamPhase: StreamPhase = 'streaming') {
  return (
    <Theme theme={neutralTheme}>
      <AgentActivityTimeline run={run} streamPhase={streamPhase} />
    </Theme>
  );
}

describe('AgentActivityTimeline', () => {
  it('shows backend label and expands friendly plus technical activity', async () => {
    const user = userEvent.setup();
    render(timeline(runningRun()));

    const current = screen
      .getAllByText('Checking job matches')
      .find((element) => element.getAttribute('aria-live') === 'polite');
    expect(current).toHaveAttribute('aria-live', 'polite');
    expect(
      screen.getByRole('status', {name: 'Running: Checking job matches'}),
    ).toBeInTheDocument();
    const disclosure = screen.getByRole('button', {
      name: /Checking job matches/i,
    });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');

    await user.click(disclosure);
    expect(disclosure).toHaveAttribute('aria-expanded', 'true');

    expect(screen.getByText('Read active CV')).toBeInTheDocument();
    expect(screen.getByText('Complete')).toBeInTheDocument();
    expect(screen.getAllByText('Checking job matches')).toHaveLength(2);
    expect(screen.getByText('In progress')).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/response_generation|match_jobs|25ms/i);
    expect(document.body).not.toHaveTextContent(
      /arguments|result|provider_payload|raw cv|cv_text/i,
    );
  });

  it('uses one Card and moves the single running Spinner when expanded', async () => {
    const user = userEvent.setup();
    render(timeline(runningRun()));

    const card = screen.getByTestId('jobagent-agent-activity-card');
    expect(card).toHaveClass('astryx-card');

    const disclosure = screen.getByRole('button', {
      name: /Checking job matches/i,
    });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    expect(disclosure.parentElement).toHaveClass(
      'jobagent-agent-activity-disclosure',
    );
    expect(
      screen.getByTestId('jobagent-agent-activity-summary-marker'),
    ).toHaveAttribute('data-marker', 'spinner');
    expect(
      screen.getAllByRole('status', {name: 'Running: Checking job matches'}),
    ).toHaveLength(1);

    await user.click(disclosure);

    expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('jobagent-agent-activity-list')).toBeVisible();
    expect(
      screen.getByTestId('jobagent-agent-activity-summary-marker'),
    ).toHaveAttribute('data-marker', 'clock');
    expect(
      screen.getAllByRole('status', {name: 'Running: Checking job matches'}),
    ).toHaveLength(1);
  });

  it('maps activity states and exposes connector-safe last-row hooks', async () => {
    const user = userEvent.setup();
    render(timeline(markerRun()));

    await user.click(
      screen.getByRole('button', {name: /Checking job matches/i}),
    );

    const list = screen.getByTestId('jobagent-agent-activity-list');
    const rows = Array.from(
      list.querySelectorAll<HTMLElement>(
        '[data-testid^="jobagent-agent-activity-row-"]',
      ),
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

    expect(screen.getAllByText('Complete').length).toBeGreaterThan(0);
    expect(screen.getByText('Could not complete')).toBeInTheDocument();
    expect(screen.getAllByText('Checking job matches')).toHaveLength(2);
    expect(document.body).not.toHaveTextContent(
      /response_generation|check_provider_response|match_jobs|40ms|PROVIDER_UNAVAILABLE/i,
    );
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

  it('renders completed, interrupted, failed, and disconnected summaries', () => {
    const view = render(timeline(terminalRun('completed'), 'idle'));
    expect(screen.getByText('Completed · 2 steps')).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-agent-activity-summary-marker'),
    ).toHaveAttribute('data-marker', 'success');
    expect(screen.getByText('Completed · 2 steps')).toHaveAttribute(
      'data-running',
      'false',
    );

    view.rerender(timeline(terminalRun('interrupted'), 'idle'));
    expect(
      screen.getByText('Waiting for your confirmation · 2 steps'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-agent-activity-summary-marker'),
    ).toHaveAttribute('data-marker', 'warning');
    expect(
      screen.getByText('Waiting for your confirmation · 2 steps'),
    ).toHaveAttribute('data-running', 'false');

    view.rerender(timeline(terminalRun('failed'), 'failed'));
    expect(screen.getByText('Unable to complete · 2 steps')).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-agent-activity-summary-marker'),
    ).toHaveAttribute('data-marker', 'error');
    expect(screen.getByText('Unable to complete · 2 steps')).toHaveAttribute(
      'data-running',
      'false',
    );

    view.rerender(timeline(runningRun(), 'disconnected'));
    expect(
      screen.getByText('Connection lost. Your request may still be running.'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-agent-activity-summary-marker'),
    ).toHaveAttribute('data-marker', 'warning');
    expect(
      screen.getByText('Connection lost. Your request may still be running.'),
    ).toHaveAttribute('data-running', 'false');
  });

  it('projects one durable user run onto one assistant row', () => {
    const run = terminalRun('completed');
    const user: ClientMessage = {
      id: 'user-1',
      clientKey: 'user-1',
      role: 'user',
      content: 'Find jobs',
      createdAt: TS,
      run,
      isStreaming: false,
    };
    const assistant: ClientMessage = {
      id: 'assistant-1',
      clientKey: 'assistant-1',
      role: 'assistant',
      content: 'Done',
      createdAt: TS_NEW,
      run: null,
      isStreaming: false,
    };
    expect(activityRunForAssistantDisplay([user, assistant], 1)).toBe(run);

    const owned: ClientMessage = {
      ...assistant,
      id: 'assistant-owner',
      clientKey: 'assistant-owner',
      run,
    };
    expect(
      activityRunForAssistantDisplay([user, assistant, owned], 1),
    ).toBeNull();
  });

  it('keeps the pre-run notice after a historical activity timeline', () => {
    const run = terminalRun('completed');
    const historicalUser: ClientMessage = {
      id: 'user-history',
      clientKey: 'user-history',
      role: 'user',
      content: 'Earlier request',
      createdAt: TS,
      run,
      isStreaming: false,
    };
    const historicalAssistant: ClientMessage = {
      id: 'assistant-history',
      clientKey: 'assistant-history',
      role: 'assistant',
      content: 'Earlier answer',
      createdAt: TS,
      run: null,
      isStreaming: false,
    };
    const currentUser: ClientMessage = {
      id: 'user-current',
      clientKey: 'user-current',
      role: 'user',
      content: 'New request',
      createdAt: TS_NEW,
      run: null,
      isStreaming: false,
    };

    render(
      <Theme theme={neutralTheme}>
        <ChatMessages
          messages={[historicalUser, historicalAssistant, currentUser]}
          streamPhase="connecting"
          streamError={null}
          isStreaming
        />
      </Theme>,
    );

    expect(screen.getByText('Connecting…')).toBeInTheDocument();
  });
});
