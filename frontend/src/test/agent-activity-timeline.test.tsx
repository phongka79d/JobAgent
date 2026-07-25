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
      .getAllByText('Rank matching jobs')
      .find((element) => element.getAttribute('aria-live') === 'polite');
    expect(current).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByLabelText('Rank matching jobs')).toBeInTheDocument();
    const disclosure = screen.getByRole('button', {
      name: /Rank matching jobs/i,
    });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');

    await user.click(disclosure);
    expect(disclosure).toHaveAttribute('aria-expanded', 'true');

    expect(screen.getByText('Read active CV')).toBeInTheDocument();
    expect(
      screen.getByText('response_generation · completed · 25ms'),
    ).toBeInTheDocument();
    expect(screen.getByText('match_jobs · running')).toBeInTheDocument();
    expect(screen.queryByText(/arguments|provider_payload|raw result/i)).not.toBeInTheDocument();
  });

  it('renders completed, interrupted, failed, and disconnected summaries', () => {
    const view = render(timeline(terminalRun('completed'), 'idle'));
    expect(screen.getByText('Completed · 2 steps')).toBeInTheDocument();

    view.rerender(timeline(terminalRun('interrupted'), 'idle'));
    expect(
      screen.getByText('Waiting for your confirmation · 2 steps'),
    ).toBeInTheDocument();

    view.rerender(timeline(terminalRun('failed'), 'failed'));
    expect(screen.getByText('Unable to complete · 2 steps')).toBeInTheDocument();

    view.rerender(timeline(runningRun(), 'disconnected'));
    expect(
      screen.getByText('Connection lost — Agent may still be running'),
    ).toBeInTheDocument();
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
