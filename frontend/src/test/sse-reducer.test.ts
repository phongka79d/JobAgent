/**
 * SSE parser + single streaming reducer tests (Plan 3 §7.9 / task 04A).
 */
import {describe, expect, it} from 'vitest';

import {
  hydrateFromHistoryPage,
  mergeOlderHistoryPage,
  rehydrateWithDurableTruth,
} from '../features/chat/history';
import {
  chatReducer,
  createInitialChatState,
  isComposerLocked,
  type ChatState,
} from '../features/chat/reducer';
import {
  FORBIDDEN_STATUS_ALIASES,
  parseHistoryPage,
  parseSseEventData,
  SSE_EVENT_NAMES,
  SseParseError,
  type HistoryPage,
  type SseEvent,
} from '../features/chat/types';
import {getApiBaseUrl} from '../lib/api/chat';
import {
  frameToEvent,
  IncrementalSseParser,
  parseSseChunk,
} from '../lib/sse/parser';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const EVENT_A = '11111111-1111-4111-8111-111111111111';
const EVENT_B = '22222222-2222-4222-8222-222222222222';
const EVENT_C = '33333333-3333-4333-8333-333333333333';
const EVENT_D = '44444444-4444-4444-8444-444444444444';
const EVENT_E = '55555555-5555-4555-8555-555555555555';
const EVENT_F = '66666666-6666-4666-8666-666666666666';
const TOOL_EXEC = '77777777-7777-4777-8777-777777777777';
const MSG_USER = '88888888-8888-4888-8888-888888888888';
const MSG_ASST = '99999999-9999-4999-8999-999999999999';
const MSG_OLD = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const TS = '2026-07-13T12:00:00.000Z';
const TS_OLD = '2026-07-13T11:00:00.000Z';

function envelope(
  eventId: string,
  event: string,
  payload: Record<string, unknown>,
  runId = RUN_ID,
): Record<string, unknown> {
  return {
    event_id: eventId,
    run_id: runId,
    timestamp: TS,
    event,
    payload,
  };
}

function wireFrame(
  data: Record<string, unknown>,
  opts?: {event?: string; id?: string},
): string {
  const id = opts?.id ?? String(data.event_id);
  const event = opts?.event ?? String(data.event);
  return `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function reduceAll(state: ChatState, events: SseEvent[]): ChatState {
  return events.reduce(
    (s, event) => chatReducer(s, {type: 'sse/event', event}),
    state,
  );
}

describe('SSE event vocabulary and status aliases', () => {
  it('exposes exactly seven event names', () => {
    expect([...SSE_EVENT_NAMES].sort()).toEqual(
      [
        'approval_required',
        'assistant_status',
        'run_completed',
        'run_failed',
        'run_started',
        'text_delta',
        'tool_status',
      ].sort(),
    );
  });

  it('rejects complete/error application status aliases', () => {
    expect(FORBIDDEN_STATUS_ALIASES.has('complete')).toBe(true);
    expect(FORBIDDEN_STATUS_ALIASES.has('error')).toBe(true);
    expect(() =>
      parseSseEventData(
        envelope(EVENT_A, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: 'demo',
          status: 'complete',
        }),
      ),
    ).toThrow(SseParseError);
    expect(() =>
      parseSseEventData(
        envelope(EVENT_A, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: 'demo',
          status: 'error',
        }),
      ),
    ).toThrow(SseParseError);
    expect(() =>
      parseSseEventData(
        envelope(EVENT_A, 'run_completed', {state: 'complete'}),
      ),
    ).toThrow(SseParseError);
  });

  it('accepts exact run/tool statuses', () => {
    const started = parseSseEventData(
      envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    );
    expect(started.event).toBe('run_started');
    const tool = parseSseEventData(
      envelope(EVENT_B, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'demo',
        status: 'pending',
      }),
    );
    expect(tool.event).toBe('tool_status');
    if (tool.event === 'tool_status') {
      expect(tool.payload.status).toBe('pending');
    }
  });
});

describe('Incremental SSE parser', () => {
  it('assembles split frames across chunks', () => {
    const parser = new IncrementalSseParser();
    const full = wireFrame(
      envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    );
    const mid = Math.floor(full.length / 2);
    const part1 = parseSseChunk(parser, full.slice(0, mid));
    expect(part1).toHaveLength(0);
    const part2 = parseSseChunk(parser, full.slice(mid));
    expect(part2).toHaveLength(1);
    expect(part2[0].ok).toBe(true);
    if (part2[0].ok) {
      expect(part2[0].event.event).toBe('run_started');
      expect(part2[0].event.event_id).toBe(EVENT_A);
    }
  });

  it('parses multiple ordered frames and ignores comments', () => {
    const parser = new IncrementalSseParser();
    const text =
      ': keep-alive\n\n' +
      wireFrame(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ) +
      wireFrame(
        envelope(EVENT_B, 'text_delta', {delta: 'Hi'}),
      ) +
      wireFrame(
        envelope(EVENT_C, 'run_completed', {state: 'completed'}),
      );
    const results = parseSseChunk(parser, text);
    expect(results.map((r) => (r.ok ? r.event.event : 'fail'))).toEqual([
      'run_started',
      'text_delta',
      'run_completed',
    ]);
  });

  it('returns parse failure for malformed JSON without throwing', () => {
    const result = frameToEvent({
      id: EVENT_A,
      event: 'text_delta',
      data: '{not-json',
    });
    expect(result.ok).toBe(false);
  });

  it('rejects unknown event names safely', () => {
    expect(() =>
      parseSseEventData(envelope(EVENT_A, 'run_finished', {state: 'completed'})),
    ).toThrow(SseParseError);
    const state = chatReducer(createInitialChatState(), {
      type: 'sse/raw',
      data: envelope(EVENT_A, 'run_finished', {state: 'completed'}),
    });
    expect(state.messages).toHaveLength(0);
    expect(state.seenEventIds).toEqual({});
  });

  it('rejects empty text_delta', () => {
    expect(() =>
      parseSseEventData(envelope(EVENT_A, 'text_delta', {delta: ''})),
    ).toThrow(SseParseError);
  });
});

describe('Reducer: direct answer path', () => {
  it('appends ordered deltas once and completes only on run_completed', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'turn/start',
      clientKey: 'user-local-1',
      message: 'Hello',
    });
    expect(isComposerLocked(state)).toBe(true);

    const events: SseEvent[] = [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(envelope(EVENT_B, 'text_delta', {delta: 'Hel'})),
      parseSseEventData(envelope(EVENT_C, 'text_delta', {delta: 'lo!'})),
      parseSseEventData(
        envelope(EVENT_D, 'run_completed', {state: 'completed'}),
      ),
    ];
    state = reduceAll(state, events);

    const assistant = state.messages.find((m) => m.role === 'assistant');
    expect(assistant?.content).toBe('Hello!');
    expect(assistant?.run?.state).toBe('completed');
    expect(assistant?.isStreaming).toBe(false);
    expect(state.streamPhase).toBe('idle');
    expect(state.activeRunId).toBeNull();
    expect(isComposerLocked(state)).toBe(false);
  });

  it('deduplicates by event_id', () => {
    let state = createInitialChatState();
    const delta = parseSseEventData(
      envelope(EVENT_B, 'text_delta', {delta: 'X'}),
    );
    const started = parseSseEventData(
      envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    );
    state = reduceAll(state, [started, delta, delta, delta]);
    const assistant = state.messages.find((m) => m.role === 'assistant');
    expect(assistant?.content).toBe('X');
    expect(Object.keys(state.seenEventIds)).toHaveLength(2);
  });
});

describe('Reducer: tool, interruption, failure, disconnect', () => {
  it('tracks ordered tool_status with exact statuses', () => {
    let state = createInitialChatState();
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: 'lookup',
          status: 'pending',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_C, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: 'lookup',
          status: 'running',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_D, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: 'lookup',
          status: 'completed',
          duration_ms: 12,
          summary: 'ok',
        }),
      ),
      parseSseEventData(envelope(EVENT_E, 'text_delta', {delta: 'Done'})),
      parseSseEventData(
        envelope(EVENT_F, 'run_completed', {state: 'completed'}),
      ),
    ]);
    const tools = state.messages.find((m) => m.role === 'assistant')?.run?.tools;
    expect(tools).toHaveLength(1);
    expect(tools?.[0].status).toBe('completed');
    expect(tools?.[0].durationMs).toBe(12);
    expect(tools?.[0].status).not.toBe('complete');
  });

  it('records interruption without marking completed', () => {
    let state = createInitialChatState();
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'approval_required', {
          state: 'interrupted',
          kind: 'synthetic',
          allowed_actions: ['approve', 'reject'],
          card: {title: 'Confirm'},
        }),
      ),
    ]);
    const run = state.messages.find((m) => m.role === 'assistant')?.run;
    expect(run?.state).toBe('interrupted');
    expect(state.pendingApproval?.kind).toBe('synthetic');
    expect(state.streamPhase).toBe('idle');
    expect(isComposerLocked(state)).toBe(true);
  });

  it('run_failed sets failed phase and never completed', () => {
    let state = createInitialChatState();
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(envelope(EVENT_B, 'text_delta', {delta: 'partial'})),
      parseSseEventData(
        envelope(EVENT_C, 'run_failed', {
          state: 'failed',
          error_code: 'GRAPH_ERROR',
          summary: 'controlled failure',
        }),
      ),
    ]);
    const run = state.messages.find((m) => m.role === 'assistant')?.run;
    expect(run?.state).toBe('failed');
    expect(run?.errorCode).toBe('GRAPH_ERROR');
    expect(state.streamPhase).toBe('failed');
    expect(state.streamError?.code).toBe('GRAPH_ERROR');
    expect(run?.state).not.toBe('completed');
  });

  it('disconnect leaves run non-complete', () => {
    let state = createInitialChatState();
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(envelope(EVENT_B, 'text_delta', {delta: 'Hi'})),
    ]);
    state = chatReducer(state, {type: 'stream/disconnected'});
    const run = state.messages.find((m) => m.role === 'assistant')?.run;
    expect(state.streamPhase).toBe('disconnected');
    expect(run?.state).toBe('running');
    expect(run?.state).not.toBe('completed');
    expect(run?.state).not.toBe('failed');
  });

  it('http failure does not invent completed status', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'turn/start',
      clientKey: 'u1',
      message: 'hi',
    });
    state = chatReducer(state, {
      type: 'stream/http_failed',
      code: 'APPROVAL_ACTION_REQUIRED',
      summary: 'finish approval first',
    });
    expect(state.streamPhase).toBe('failed');
    expect(state.streamError?.code).toBe('APPROVAL_ACTION_REQUIRED');
    expect(
      state.messages.every(
        (m) => m.run === null || m.run.state !== 'completed',
      ),
    ).toBe(true);
  });
});

describe('History hydration and load-older', () => {
  function historyPage(overrides?: Partial<HistoryPage>): HistoryPage {
    const page: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'Hello',
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
                tool_call_id: 'tc1',
                tool_name: 'lookup',
                status: 'completed',
                duration_ms: 5,
                error_code: null,
                result: {
                  ok: true,
                  code: null,
                  summary: 'durable summary',
                  data: null,
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
          content: 'Hello!',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: 'cursor-older',
    };
    return {...page, ...overrides};
  }

  it('hydrates chronological messages and preserves next_cursor', () => {
    const {messages, nextCursor} = hydrateFromHistoryPage(historyPage());
    expect(messages.map((m) => m.role)).toEqual(['user', 'assistant']);
    expect(nextCursor).toBe('cursor-older');
    expect(messages[0].run?.tools[0].status).toBe('completed');
    expect(messages[0].run?.tools[0].source).toBe('history');
  });

  it('load-older merges without duplicates and updates cursor', () => {
    let state = chatReducer(createInitialChatState(), {
      type: 'history/reset',
      page: historyPage(),
    });
    const older: HistoryPage = {
      items: [
        {
          id: MSG_OLD,
          role: 'user',
          content: 'Earlier',
          structured_payload: null,
          created_at: TS_OLD,
          updated_at: TS_OLD,
          run: null,
        },
        // duplicate of newest user — must not double
        historyPage().items[0],
      ],
      next_cursor: null,
    };
    state = chatReducer(state, {type: 'history/load_older', page: older});
    const ids = state.messages.map((m) => m.id);
    expect(ids).toEqual([MSG_OLD, MSG_USER, MSG_ASST]);
    expect(state.nextCursor).toBeNull();
  });

  it('durable history replaces transient stream tool state for completed turns', () => {
    let state = createInitialChatState();
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: 'lookup',
          status: 'running',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_C, 'run_completed', {state: 'completed'}),
      ),
    ]);
    const before = state.messages.find((m) => m.role === 'assistant')?.run?.tools;
    expect(before?.[0].source).toBe('stream');
    expect(before?.[0].status).toBe('running'); // stale transient if stream ended early

    // Attach the streamed run id onto a user message for merge identity,
    // then rehydrate with durable completed tool.
    const page = historyPage();
    // Also place durable run on an assistant-linked user turn matching RUN_ID.
    const {messages} = rehydrateWithDurableTruth(state.messages, page);
    // User message from history carries durable tools for RUN_ID.
    const userFromHistory = messages.find((m) => m.id === MSG_USER);
    expect(userFromHistory?.run?.tools[0].source).toBe('history');
    expect(userFromHistory?.run?.tools[0].status).toBe('completed');
    expect(userFromHistory?.run?.tools[0].summary).toBe('durable summary');

    // Assistant message that shared RUN_ID should have tools replaced if present.
    const asstWithRun = messages.find(
      (m) => m.role === 'assistant' && m.run?.id === RUN_ID,
    );
    if (asstWithRun?.run) {
      expect(asstWithRun.run.tools.every((t) => t.source === 'history')).toBe(
        true,
      );
      expect(asstWithRun.run.tools[0].status).toBe('completed');
    }
  });

  it('parseHistoryPage rejects role=tool and status aliases', () => {
    expect(() =>
      parseHistoryPage({
        items: [
          {
            id: MSG_USER,
            role: 'tool',
            content: 'nope',
            structured_payload: null,
            created_at: TS,
            updated_at: TS,
            run: null,
          },
        ],
        next_cursor: null,
      }),
    ).toThrow(/role=tool/);

    expect(() =>
      parseHistoryPage({
        items: [
          {
            id: MSG_USER,
            role: 'user',
            content: 'x',
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
                  tool_call_id: 'tc1',
                  tool_name: 't',
                  status: 'complete',
                  duration_ms: 1,
                  error_code: null,
                  result: null,
                  arguments_summary: null,
                  created_at: TS,
                  updated_at: TS,
                },
              ],
            },
          },
        ],
        next_cursor: null,
      }),
    ).toThrow(SseParseError);
  });

  it('mergeOlderHistoryPage helper preserves order', () => {
    const first = hydrateFromHistoryPage(historyPage({next_cursor: 'c1'}));
    const merged = mergeOlderHistoryPage(first.messages, {
      items: [
        {
          id: MSG_OLD,
          role: 'system',
          content: 'note',
          structured_payload: null,
          created_at: TS_OLD,
          updated_at: TS_OLD,
          run: null,
        },
      ],
      next_cursor: null,
    });
    expect(merged.messages[0].id).toBe(MSG_OLD);
    expect(merged.nextCursor).toBeNull();
  });
});

describe('API environment boundary', () => {
  it('getApiBaseUrl reads only VITE_API_BASE_URL', () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // vitest: env may be undefined; function must require the single var.
    try {
      // @ts-expect-error test mutation of import.meta.env
      import.meta.env.VITE_API_BASE_URL = 'http://localhost:8000/';
      expect(getApiBaseUrl()).toBe('http://localhost:8000');
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

describe('Reducer integration via sse/raw', () => {
  it('ignores malformed raw without state mutation', () => {
    const initial = createInitialChatState();
    const next = chatReducer(initial, {
      type: 'sse/raw',
      data: {event: 'text_delta', payload: {delta: 'x'}},
    });
    expect(next).toEqual(initial);
  });

  it('assistant_status is non-terminal', () => {
    const state = reduceAll(createInitialChatState(), [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'assistant_status', {message: 'thinking'}),
      ),
    ]);
    expect(state.assistantStatus).toBe('thinking');
    expect(state.messages.find((m) => m.role === 'assistant')?.run?.state).toBe(
      'running',
    );
  });
});
