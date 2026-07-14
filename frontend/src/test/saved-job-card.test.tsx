/**
 * Saved-job card + durable history projection tests (Plan 5 Batch04 04A).
 * Strict compact parsing, completed/failed/sync-failed cards, null fields,
 * enumerated badges, safe source URL, no raw/embedding/ranking, friendly
 * labels, terminal rehydrate, restart hydration, exact status preservation.
 */
import type {ReactElement} from 'react';
import {
  cleanup,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ChatPage, type ChatPageDeps} from '../features/chat/ChatPage';
import {ChatMessages} from '../features/chat/components/ChatMessages';
import {
  toolsForAssistantDisplay,
} from '../features/chat/components/ChatMessageRow';
import {friendlyToolLabel} from '../features/chat/components/ChatToolActivity';
import {
  hydrateFromHistoryPage,
  rehydrateWithDurableTruth,
  toolViewToActivity,
} from '../features/chat/history';
import {
  chatReducer,
  createInitialChatState,
} from '../features/chat/reducer';
import type {
  HistoryPage,
  JsonObject,
  SseEvent,
  ToolExecutionView,
  ToolResult,
} from '../features/chat/types';
import {parseSseEventData} from '../features/chat/types';
import {SavedJobCard} from '../features/jobs/SavedJobCard';
import {
  NEO4J_SYNC_FAILED_CODE,
  parseSaveJobResultData,
  projectCompactResultData,
  safeHttpUrl,
  type CompactSaveJobResult,
} from '../features/jobs/types';
import type {StreamCallbacks} from '../lib/api/chat';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const EVENT_A = '11111111-1111-4111-8111-111111111111';
const EVENT_B = '22222222-2222-4222-8222-222222222222';
const EVENT_C = '33333333-3333-4333-8333-333333333333';
const EVENT_D = '44444444-4444-4444-8444-444444444444';
const TOOL_EXEC = '77777777-7777-4777-8777-777777777777';
const MSG_USER = '88888888-8888-4888-8888-888888888888';
const MSG_ASST = '99999999-9999-4999-8999-999999999999';
const JOB_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const TS = '2026-07-14T12:00:00.000Z';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function compactSaveData(overrides?: JsonObject): JsonObject {
  return {
    job_id: JOB_ID,
    title: 'Staff Engineer',
    company: 'Acme Corp',
    source_url: 'https://example.com/jobs/1',
    processing_status: 'processed',
    jd_quality: 'full',
    outcome: 'created',
    sqlite_committed: true,
    sync_ok: true,
    failure_code: null,
    rebuild_instruction: null,
    paste_instruction: null,
    ...overrides,
  };
}

function toolExecution(
  resultData: JsonObject | null,
  overrides?: Partial<Omit<ToolExecutionView, 'result'>> & {
    result?: ToolResult;
  },
): ToolExecutionView {
  const result: ToolResult =
    overrides?.result ??
    ({
      ok: true,
      code: null,
      summary: 'Saved job description (processed/full)',
      data: resultData,
    } satisfies ToolResult);
  return {
    id: TOOL_EXEC,
    tool_call_id: 'tc-save-1',
    tool_name: 'save_job',
    status: 'completed',
    duration_ms: 120,
    error_code: null,
    arguments_summary: null,
    created_at: TS,
    updated_at: TS,
    ...overrides,
    result,
  };
}

function historyWithSaveJob(
  data: JsonObject | null = compactSaveData(),
  toolOverrides?: Parameters<typeof toolExecution>[1],
): HistoryPage {
  const tool = toolExecution(data, toolOverrides);
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'Save this JD',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: {
          id: RUN_ID,
          user_message_id: MSG_USER,
          state: 'completed',
          pending_approval: null,
          error_code: null,
          completed_at: TS,
          created_at: TS,
          updated_at: TS,
          tool_executions: [tool],
        },
      },
      {
        id: MSG_ASST,
        role: 'assistant',
        content: 'Job saved.',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

function renderWithTheme(ui: ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

function renderChat(deps: ChatPageDeps) {
  return renderWithTheme(<ChatPage deps={deps} />);
}

function sse(
  eventId: string,
  event: SseEvent['event'],
  payload: Record<string, unknown>,
): SseEvent {
  return parseSseEventData({
    event_id: eventId,
    run_id: RUN_ID,
    timestamp: TS,
    event,
    payload,
  });
}

/** Count assistant rows that would host a saved-job card for messages. */
function cardHostCount(messages: ReturnType<typeof createInitialChatState>['messages']): number {
  let count = 0;
  for (let i = 0; i < messages.length; i += 1) {
    if (messages[i].role !== 'assistant') {
      continue;
    }
    const tools = toolsForAssistantDisplay(messages, i);
    const hasSave = tools.some(
      (t) =>
        t.toolName === 'save_job' &&
        parseSaveJobResultData(t.resultData) !== null,
    );
    if (hasSave) {
      count += 1;
    }
  }
  return count;
}

describe('strict compact save_job parsing', () => {
  it('parses completed compact fields including outcome and nullables', () => {
    const parsed = parseSaveJobResultData(
      compactSaveData({
        title: null,
        company: null,
        source_url: null,
        jd_quality: 'partial',
        outcome: 'returned',
      }),
    );
    expect(parsed).toEqual({
      jobId: JOB_ID,
      title: null,
      company: null,
      sourceUrl: null,
      processingStatus: 'processed',
      jdQuality: 'partial',
      outcome: 'returned',
      sqliteCommitted: true,
      syncOk: true,
      failureCode: null,
      rebuildInstruction: null,
      pasteInstruction: null,
    } satisfies CompactSaveJobResult);
  });

  it('rejects missing required fields and invalid vocabularies', () => {
    expect(parseSaveJobResultData(null)).toBeNull();
    expect(parseSaveJobResultData({job_id: JOB_ID})).toBeNull();
    expect(
      parseSaveJobResultData(
        compactSaveData({processing_status: 'done'}),
      ),
    ).toBeNull();
    expect(
      parseSaveJobResultData(compactSaveData({outcome: 'upserted'})),
    ).toBeNull();
    expect(
      parseSaveJobResultData(compactSaveData({jd_quality: 'excellent'})),
    ).toBeNull();
  });

  it('rejects missing sync_ok and unexpected keys (exact parser)', () => {
    const withoutSync = compactSaveData();
    delete withoutSync.sync_ok;
    expect(parseSaveJobResultData(withoutSync)).toBeNull();

    expect(
      parseSaveJobResultData(
        compactSaveData({
          storage_path: '/var/data/job.db',
        }),
      ),
    ).toBeNull();
    expect(
      parseSaveJobResultData(
        compactSaveData({
          api_secret: 'sk-live-xyz',
        }),
      ),
    ).toBeNull();
    expect(
      parseSaveJobResultData(
        compactSaveData({
          nested_raw: {body: 'FULL JD', embedding: [1, 2, 3]},
        }),
      ),
    ).toBeNull();
    expect(
      parseSaveJobResultData(
        compactSaveData({
          raw_content: 'FULL JD TEXT',
          embedding_json: '[1,2,3]',
          arguments: {url: 'https://x'},
          stack: 'Error: boom',
        }),
      ),
    ).toBeNull();
  });

  it('allowlist projection retains only SaveJobResultData keys for save_job', () => {
    const projected = projectCompactResultData('save_job', {
      ...compactSaveData(),
      raw_content: 'FULL JD TEXT',
      embedding_json: '[1,2,3]',
      storage_path: '/secret/path',
      api_secret: 'sk-test',
      nested_raw: {body: 'x'},
      arguments: {text: 'jd'},
      stack: 'trace',
    });
    expect(projected).not.toBeNull();
    expect(projected).not.toHaveProperty('raw_content');
    expect(projected).not.toHaveProperty('embedding_json');
    expect(projected).not.toHaveProperty('storage_path');
    expect(projected).not.toHaveProperty('api_secret');
    expect(projected).not.toHaveProperty('nested_raw');
    expect(projected).not.toHaveProperty('arguments');
    expect(projected).not.toHaveProperty('stack');
    expect(projected?.job_id).toBe(JOB_ID);
    expect(projected?.sync_ok).toBe(true);
    expect(parseSaveJobResultData(projected)?.jobId).toBe(JOB_ID);
  });

  it('retains no result data for unrelated tools', () => {
    expect(
      projectCompactResultData('query_jobs', {
        jobs: [],
        count: 0,
        limit: 10,
      }),
    ).toBeNull();
    expect(
      projectCompactResultData('propose_profile_from_cv', {
        draft_id: 'x',
      }),
    ).toBeNull();
    expect(
      projectCompactResultData('save_job', {
        job_id: JOB_ID,
        // missing required fields
      }),
    ).toBeNull();
  });

  it('accepts only safe http(s) source URLs', () => {
    expect(safeHttpUrl('https://example.com/j')).toBe(
      'https://example.com/j',
    );
    expect(safeHttpUrl('http://example.com/j')).toBe('http://example.com/j');
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull();
    expect(safeHttpUrl('/relative')).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
  });
});

describe('SavedJobCard rendering', () => {
  it('renders completed card with processing/quality badges only and outcome metadata', () => {
    const data = parseSaveJobResultData(compactSaveData())!;
    renderWithTheme(
      <SavedJobCard
        data={data}
        summary="Saved job description (processed/full)"
      />,
    );
    expect(screen.getByTestId('jobagent-saved-job-card')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-job-processing-badge')).toHaveTextContent(
      'processed',
    );
    expect(screen.getByTestId('jobagent-job-quality-badge')).toHaveTextContent(
      'full',
    );
    // Badge is only for processing status and JD quality — not outcome.
    expect(
      screen.queryByTestId('jobagent-job-outcome-badge'),
    ).not.toBeInTheDocument();
    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(screen.getByText(JOB_ID)).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getAllByText('Staff Engineer').length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getByRole('link', {name: /example.com/})).toHaveAttribute(
      'href',
      'https://example.com/jobs/1',
    );
    expect(screen.queryByText(/rank|score|embedding/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/FULL JD/i)).not.toBeInTheDocument();
  });

  it('renders failed fetch/extraction card with stable code', () => {
    const data = parseSaveJobResultData(
      compactSaveData({
        title: null,
        company: null,
        source_url: null,
        processing_status: 'failed',
        jd_quality: null,
        outcome: 'created',
        sync_ok: null,
        failure_code: 'URL_FETCH_FAILED',
        paste_instruction: 'Paste the job text instead.',
      }),
    )!;
    renderWithTheme(
      <SavedJobCard
        data={data}
        summary="Job ingestion failed (URL_FETCH_FAILED)"
        errorCode="URL_FETCH_FAILED"
      />,
    );
    expect(screen.getByTestId('jobagent-job-processing-badge')).toHaveTextContent(
      'failed',
    );
    expect(screen.getByText(/URL_FETCH_FAILED/)).toBeInTheDocument();
    expect(screen.getByText(/Paste the job text/)).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-job-quality-badge')).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-job-outcome-badge'),
    ).not.toBeInTheDocument();
  });

  it('NEO4J_SYNC_FAILED shows processed SQLite truth without graph success', () => {
    const data = parseSaveJobResultData(
      compactSaveData({
        sync_ok: false,
        failure_code: NEO4J_SYNC_FAILED_CODE,
        rebuild_instruction: 'docker compose exec backend python -m app.graph.rebuild',
      }),
    )!;
    renderWithTheme(
      <SavedJobCard
        data={data}
        summary="Job saved to SQLite but Neo4j sync failed"
        errorCode={NEO4J_SYNC_FAILED_CODE}
      />,
    );
    expect(screen.getByTestId('jobagent-job-processing-badge')).toHaveTextContent(
      'processed',
    );
    expect(screen.getByText(/SQLite remains authoritative/i)).toBeInTheDocument();
    expect(screen.getByText(/Graph projection unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Synced$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/rank|matching success/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/rebuild/i).length).toBeGreaterThanOrEqual(1);
  });

  it('omits null title/company/source and shows outcome as plain metadata', () => {
    const data = parseSaveJobResultData(
      compactSaveData({
        title: null,
        company: null,
        source_url: null,
        outcome: 'retried',
        jd_quality: 'unscorable',
      }),
    )!;
    renderWithTheme(<SavedJobCard data={data} />);
    expect(screen.getByText('Saved job')).toBeInTheDocument();
    expect(screen.getByText('Retried in place')).toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-job-outcome-badge'),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});

describe('history resultData + friendly labels', () => {
  it('toolViewToActivity projects allowlisted save_job data and drops adversarial keys', () => {
    const activity = toolViewToActivity(
      toolExecution({
        ...compactSaveData(),
        raw_content: 'SECRET JD',
        embedding_json: '[]',
        storage_path: '/data/job.db',
        api_secret: 'sk-live',
        nested_raw: {jd: 'body'},
        arguments: {url: 'https://x'},
        stack: 'Error stack',
      }),
    );
    expect(activity.source).toBe('history');
    expect(activity.resultData).not.toBeNull();
    expect(activity.resultData).not.toHaveProperty('raw_content');
    expect(activity.resultData).not.toHaveProperty('embedding_json');
    expect(activity.resultData).not.toHaveProperty('storage_path');
    expect(activity.resultData).not.toHaveProperty('api_secret');
    expect(activity.resultData).not.toHaveProperty('nested_raw');
    expect(activity.resultData).not.toHaveProperty('arguments');
    expect(activity.resultData).not.toHaveProperty('stack');
    expect(parseSaveJobResultData(activity.resultData)?.jobId).toBe(JOB_ID);
  });

  it('toolViewToActivity retains null resultData for non-save_job tools', () => {
    const activity = toolViewToActivity(
      toolExecution(
        {
          jobs: [{job_id: JOB_ID}],
          count: 1,
          limit: 10,
        },
        {tool_name: 'query_jobs'},
      ),
    );
    expect(activity.toolName).toBe('query_jobs');
    expect(activity.resultData).toBeNull();
  });

  it('stream tool_status keeps resultData null until rehydrate', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_B, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'save_job',
        status: 'running',
        duration_ms: null,
        summary: 'Saving…',
        error_code: null,
      }),
    });
    const tools = state.messages.find((m) => m.role === 'assistant')?.run?.tools;
    expect(tools?.[0].resultData).toBeNull();
    expect(tools?.[0].status).toBe('running');
    expect(tools?.[0].source).toBe('stream');
  });

  it('history/rehydrate replaces stream tools with durable resultData', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_B, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'save_job',
        status: 'running',
        duration_ms: null,
        summary: null,
        error_code: null,
      }),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_C, 'run_completed', {state: 'completed'}),
    });

    const page = historyWithSaveJob();
    const {messages} = rehydrateWithDurableTruth(state.messages, page);
    const userTools = messages.find((m) => m.id === MSG_USER)?.run?.tools;
    expect(userTools?.[0].source).toBe('history');
    expect(userTools?.[0].status).toBe('completed');
    expect(userTools?.[0].resultData?.job_id).toBe(JOB_ID);
    expect(userTools?.[0].durationMs).toBe(120);
    // Stream assistant host is collapsed when durable assistant exists.
    expect(
      messages.some((m) => m.id === `assistant:${RUN_ID}`),
    ).toBe(false);
    expect(cardHostCount(messages)).toBe(1);
  });

  it('restart hydration via history/reset shows card fields', () => {
    const {messages} = hydrateFromHistoryPage(historyWithSaveJob());
    const tools = messages[0].run?.tools ?? [];
    expect(tools[0].resultData?.outcome).toBe('created');
    const state = chatReducer(createInitialChatState(), {
      type: 'history/reset',
      page: historyWithSaveJob(),
    });
    expect(state.messages[0].run?.tools[0].resultData?.processing_status).toBe(
      'processed',
    );
    expect(cardHostCount(state.messages)).toBe(1);
  });

  it('uses friendly Save Job / Query Jobs labels', () => {
    expect(friendlyToolLabel('save_job')).toBe('Save Job');
    expect(friendlyToolLabel('query_jobs')).toBe('Query Jobs');
  });
});

describe('ChatPage durable saved-job card', () => {
  it('renders compact card from restart history load', async () => {
    const loadHistory = vi.fn().mockResolvedValue(historyWithSaveJob());
    renderChat({loadHistory, sendTurn: vi.fn()});

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-saved-job-card')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('jobagent-saved-job-card')).toHaveLength(1);
    expect(screen.getByText('Save Job')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText(JOB_ID)).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-job-processing-badge')).toHaveTextContent(
      'processed',
    );
    expect(
      screen.queryByTestId('jobagent-job-outcome-badge'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_content|embedding_json/i)).not.toBeInTheDocument();
  });

  it('terminal rehydrate renders exactly one card when stream and durable IDs differ', () => {
    // Simulate stream-shaped state then history/rehydrate (ChatPage terminal path).
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'turn/start',
      clientKey: 'user:live',
      message: 'Please save this job',
      createdAt: '2026-07-14T11:00:00.000Z',
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_B, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'save_job',
        status: 'running',
        duration_ms: null,
        summary: 'Saving job…',
        error_code: null,
      }),
    });
    // Stream tools never carry compact data.
    const streamTools = state.messages.find((m) => m.role === 'assistant')?.run
      ?.tools;
    expect(streamTools?.[0].resultData).toBeNull();

    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_C, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'save_job',
        status: 'completed',
        duration_ms: 50,
        summary: 'Saved',
        error_code: null,
      }),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_D, 'run_completed', {state: 'completed'}),
    });

    // Terminal ChatPage path: history/rehydrate with durable ToolResult.data.
    state = chatReducer(state, {
      type: 'history/rehydrate',
      page: historyWithSaveJob(),
    });

    const userTools = state.messages.find((m) => m.id === MSG_USER)?.run?.tools;
    expect(userTools?.[0].resultData?.job_id).toBe(JOB_ID);
    // Stream assistant:<run_id> must not remain alongside durable assistant.
    expect(
      state.messages.some((m) => m.id === `assistant:${RUN_ID}`),
    ).toBe(false);
    expect(cardHostCount(state.messages)).toBe(1);

    renderWithTheme(
      <ChatMessages
        messages={state.messages}
        streamPhase="idle"
        streamError={null}
        assistantStatus={null}
        isStreaming={false}
      />,
    );
    expect(screen.getAllByTestId('jobagent-saved-job-card')).toHaveLength(1);
    expect(screen.getAllByText(JOB_ID)).toHaveLength(1);
    expect(screen.queryByText(/ranking|match score/i)).not.toBeInTheDocument();
  });

  it('ChatPage invokes history rehydrate after terminal run_completed with exact one card', async () => {
    const durablePage = historyWithSaveJob();
    let historyCalls = 0;
    const loadHistory = vi.fn(async () => {
      historyCalls += 1;
      if (historyCalls === 1) {
        return {items: [], next_cursor: null};
      }
      return durablePage;
    });
    const sendTurn = vi.fn(
      async (
        _body: {message: string},
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
        );
        cbs.onEvent(
          sse(EVENT_C, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc1',
            tool_name: 'save_job',
            status: 'completed',
            duration_ms: 50,
            summary: 'Saved',
            error_code: null,
          }),
        );
        cbs.onEvent(sse(EVENT_D, 'run_completed', {state: 'completed'}));
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    const user = userEvent.setup();
    const editable =
      (container.querySelector(
        '[contenteditable="true"]',
      ) as HTMLElement | null) ??
      (container.querySelector('[role="textbox"]') as HTMLElement | null);
    await user.click(editable!);
    await user.keyboard('Please save this job');
    await waitFor(() => {
      expect(
        screen
          .getAllByRole('button', {name: 'Send'})
          .some((b) => !(b as HTMLButtonElement).disabled),
      ).toBe(true);
    });
    await user.click(
      screen
        .getAllByRole('button', {name: 'Send'})
        .find((b) => !(b as HTMLButtonElement).disabled)!,
    );
    await waitFor(() => {
      expect(historyCalls).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expect(screen.getAllByTestId('jobagent-saved-job-card')).toHaveLength(1);
    });
  });

  it('query_jobs history stays tool activity without a ranking surface', async () => {
    const page: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'List jobs',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: {
            id: RUN_ID,
            user_message_id: MSG_USER,
            state: 'completed',
            pending_approval: null,
            error_code: null,
            completed_at: TS,
            created_at: TS,
            updated_at: TS,
            tool_executions: [
              {
                id: TOOL_EXEC,
                tool_call_id: 'tc-q',
                tool_name: 'query_jobs',
                status: 'completed',
                duration_ms: 10,
                error_code: null,
                result: {
                  ok: true,
                  code: null,
                  summary: 'Found 1 job(s)',
                  data: {
                    jobs: [
                      {
                        job_id: JOB_ID,
                        title: 'X',
                        company: 'Y',
                        source_url: null,
                        processing_status: 'processed',
                        jd_quality: 'full',
                      },
                    ],
                    count: 1,
                    limit: 10,
                  },
                },
                arguments_summary: null,
                created_at: TS,
                updated_at: TS,
              },
            ],
          },
        },
        {
          id: MSG_ASST,
          role: 'assistant',
          content: 'Here are recent jobs.',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(page),
      sendTurn: vi.fn(),
    });
    await waitFor(() => {
      expect(screen.getByText('Query Jobs')).toBeInTheDocument();
    });
    expect(screen.getByText('Found 1 job(s)')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-saved-job-card')).not.toBeInTheDocument();
    expect(screen.queryByText(/rank|score/i)).not.toBeInTheDocument();
  });

  it('sync-failed history remains visibly failed with processed status', async () => {
    const page = historyWithSaveJob(
      compactSaveData({
        sync_ok: false,
        failure_code: NEO4J_SYNC_FAILED_CODE,
        rebuild_instruction: 'run local graph rebuild',
      }),
      {
        status: 'failed',
        error_code: NEO4J_SYNC_FAILED_CODE,
        result: {
          ok: false,
          code: NEO4J_SYNC_FAILED_CODE,
          summary:
            'Job saved to SQLite but Neo4j sync failed; run local graph rebuild',
          data: compactSaveData({
            sync_ok: false,
            failure_code: NEO4J_SYNC_FAILED_CODE,
            rebuild_instruction: 'run local graph rebuild',
          }),
        },
      },
    );
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(page),
      sendTurn: vi.fn(),
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-saved-job-card')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('jobagent-saved-job-card')).toHaveLength(1);
    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-job-processing-badge')).toHaveTextContent(
      'processed',
    );
    expect(screen.getByText(/SQLite remains authoritative/i)).toBeInTheDocument();
  });
});
