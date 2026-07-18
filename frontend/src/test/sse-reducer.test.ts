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
  TOOL_STATUSES,
  type HistoryPage,
  type SseEvent,
  type ToolStatus,
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

  it('accepts every exact tool status pending|running|completed|failed only', () => {
    expect([...TOOL_STATUSES]).toEqual([
      'pending',
      'running',
      'completed',
      'failed',
    ]);
    const payloads: Record<ToolStatus, Record<string, unknown>> = {
      pending: {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'demo',
        status: 'pending',
      },
      running: {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'demo',
        status: 'running',
      },
      completed: {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'demo',
        status: 'completed',
        duration_ms: 8,
        summary: 'ok',
      },
      failed: {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'demo',
        status: 'failed',
        duration_ms: 4,
        error_code: 'TOOL_ERROR',
        summary: 'tool failed',
      },
    };
    for (const status of TOOL_STATUSES) {
      const parsed = parseSseEventData(
        envelope(EVENT_A, 'tool_status', payloads[status]),
      );
      expect(parsed.event).toBe('tool_status');
      if (parsed.event === 'tool_status') {
        expect(parsed.payload.status).toBe(status);
        expect(FORBIDDEN_STATUS_ALIASES.has(parsed.payload.status)).toBe(false);
      }
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

  it('records profile_commit interrupt with exact tool statuses and pending card', () => {
    let state = createInitialChatState();
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc-commit',
          tool_name: 'commit_profile_draft',
          status: 'running',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_C, 'approval_required', {
          state: 'interrupted',
          kind: 'profile_commit',
          allowed_actions: ['save_profile', 'request_changes'],
          card: {
            tool_name: 'commit_profile_draft',
            current_title: 'Engineer',
            draft_id: 'current',
          },
        }),
      ),
    ]);
    const run = state.messages.find((m) => m.role === 'assistant')?.run;
    expect(run?.state).toBe('interrupted');
    expect(run?.tools[0]?.status).toBe('running');
    expect(run?.tools[0]?.status).not.toBe('complete');
    expect(state.pendingApproval?.kind).toBe('profile_commit');
    expect(state.pendingApproval?.allowed_actions).toEqual([
      'save_profile',
      'request_changes',
    ]);
    expect(isComposerLocked(state)).toBe(true);

    // Resume completion clears pending approval through the same reducer.
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_D, 'run_started', {state: 'running', resumed: true}),
      ),
      parseSseEventData(
        envelope(EVENT_E, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc-commit',
          tool_name: 'commit_profile_draft',
          status: 'completed',
          duration_ms: 10,
          summary: 'saved',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_F, 'run_completed', {state: 'completed'}),
      ),
    ]);
    expect(state.pendingApproval).toBeNull();
    expect(isComposerLocked(state)).toBe(false);
    const done = state.messages.find((m) => m.role === 'assistant')?.run;
    expect(done?.state).toBe('completed');
    expect(done?.tools[0]?.status).toBe('completed');
  });

  it('hydrates pending profile_commit from durable history after restart', () => {
    const page: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'Commit profile',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: {
            id: RUN_ID,
            user_message_id: MSG_USER,
            state: 'interrupted',
            pending_approval: {
              kind: 'profile_commit',
              draft_id: 'current',
              allowed_actions: ['save_profile', 'request_changes'],
              card: {current_title: 'Hydrated Title'},
            },
            error_code: null,
            completed_at: null,
            created_at: TS,
            updated_at: TS,
            tool_executions: [
              {
                id: TOOL_EXEC,
                tool_call_id: 'tc1',
                tool_name: 'commit_profile_draft',
                status: 'running',
                duration_ms: null,
                error_code: null,
                result: null,
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
          content: 'Please approve',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
    const state = chatReducer(createInitialChatState(), {
      type: 'history/reset',
      page,
    });
    expect(state.pendingApproval?.kind).toBe('profile_commit');
    expect(state.pendingApproval?.card).toMatchObject({
      current_title: 'Hydrated Title',
    });
    expect(state.activeRunId).toBe(RUN_ID);
    expect(isComposerLocked(state)).toBe(true);
    expect(state.messages[0]?.run?.state).toBe('interrupted');
    expect(state.messages[0]?.run?.tools[0]?.status).toBe('running');
  });

  it('records and hydrates job_save_confirmation interrupt without a second store', () => {
    let state = createInitialChatState();
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc-jd-1',
          tool_name: 'save_job',
          status: 'running',
          duration_ms: null,
          summary: null,
        }),
      ),
      parseSseEventData(
        envelope(EVENT_C, 'approval_required', {
          state: 'interrupted',
          kind: 'job_save_confirmation',
          allowed_actions: ['save_job', 'cancel_save_job'],
          card: {
            tool_name: 'save_job',
            tool_call_id: 'tc-jd-1',
            source: 'current_message',
            text_length: 500,
            preview: {title: 'Role', company: null, skills: ['Go']},
          },
        }),
      ),
    ]);
    expect(state.pendingApproval?.kind).toBe('job_save_confirmation');
    expect(state.pendingApproval?.allowed_actions).toEqual([
      'save_job',
      'cancel_save_job',
    ]);
    expect(isComposerLocked(state)).toBe(true);

    const page: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'pasted jd',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: {
            id: RUN_ID,
            user_message_id: MSG_USER,
            state: 'interrupted',
            pending_approval: {
              kind: 'job_save_confirmation',
              allowed_actions: ['save_job', 'cancel_save_job'],
              card: {
                tool_name: 'save_job',
                tool_call_id: 'tc-jd-1',
                source: 'current_message',
                text_length: 500,
                preview: {title: 'Role', company: null, skills: ['Go']},
              },
            },
            error_code: null,
            completed_at: null,
            created_at: TS,
            updated_at: TS,
            tool_executions: [
              {
                id: TOOL_EXEC,
                tool_call_id: 'tc-jd-1',
                tool_name: 'save_job',
                status: 'running',
                duration_ms: null,
                error_code: null,
                result: null,
                arguments_summary: {source: 'current_message'},
                created_at: TS,
                updated_at: TS,
              },
            ],
          },
        },
        {
          id: MSG_ASST,
          role: 'assistant',
          content: 'unsaved',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
    const hydrated = chatReducer(createInitialChatState(), {
      type: 'history/reset',
      page,
    });
    expect(hydrated.pendingApproval?.kind).toBe('job_save_confirmation');
    expect(hydrated.activeRunId).toBe(RUN_ID);
    expect(isComposerLocked(hydrated)).toBe(true);
    expect(hydrated.messages[0]?.run?.tools[0]?.toolName).toBe('save_job');
    expect(hydrated.messages[0]?.run?.tools[0]?.status).toBe('running');
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

  it('tracks tool_status failed with exact status and never complete/error aliases', () => {
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
        envelope(EVENT_C, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: 'lookup',
          status: 'failed',
          duration_ms: 9,
          error_code: 'TOOL_ERROR',
          summary: 'lookup failed',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_D, 'run_failed', {
          state: 'failed',
          error_code: 'TOOL_ERROR',
          summary: 'tool failed the run',
        }),
      ),
    ]);
    const tools = state.messages.find((m) => m.role === 'assistant')?.run?.tools;
    expect(tools?.[0].status).toBe('failed');
    expect(tools?.[0].errorCode).toBe('TOOL_ERROR');
    expect(tools?.[0].status).not.toBe('error');
    expect(tools?.[0].status).not.toBe('complete');
    expect(state.streamPhase).toBe('failed');
    expect(
      state.messages.every(
        (m) => m.run === null || m.run.state !== 'completed',
      ),
    ).toBe(true);
  });

  it('disconnect recovery rehydrates durable tools without inventing completed', () => {
    // Mid-stream disconnect leaves non-terminal truth; same single reducer
    // history/rehydrate path supplies durable run/tool state (no second store).
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
      parseSseEventData(envelope(EVENT_C, 'text_delta', {delta: 'Partial'})),
    ]);
    state = chatReducer(state, {type: 'stream/disconnected'});
    const mid = state.messages.find((m) => m.role === 'assistant')?.run;
    expect(state.streamPhase).toBe('disconnected');
    expect(mid?.state).toBe('running');
    expect(mid?.tools[0]?.status).toBe('running');
    expect(mid?.tools[0]?.source).toBe('stream');
    expect(mid?.tools[0]?.resultData).toBeNull();

    const durablePage: HistoryPage = {
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
                duration_ms: 15,
                error_code: null,
                result: {
                  ok: true,
                  code: null,
                  summary: 'durable after disconnect',
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
          content: 'Partial and finished',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };

    // Disconnect alone never completes; durable page is the only success path.
    expect(
      state.messages.every(
        (m) => m.run === null || m.run.state !== 'completed',
      ),
    ).toBe(true);

    state = chatReducer(state, {type: 'history/rehydrate', page: durablePage});
    const durableUser = state.messages.find((m) => m.id === MSG_USER);
    expect(durableUser?.run?.state).toBe('completed');
    expect(durableUser?.run?.tools[0]?.source).toBe('history');
    expect(durableUser?.run?.tools[0]?.status).toBe('completed');
    expect(durableUser?.run?.tools[0]?.summary).toBe(
      'durable after disconnect',
    );
    expect(durableUser?.run?.tools[0]?.status).not.toBe('complete');
    // Stream-shaped assistant host is collapsed when durable assistant exists.
    expect(state.messages.some((m) => m.id === `assistant:${RUN_ID}`)).toBe(
      false,
    );
    // Still the single chatReducer — no second API/SSE event invented success.
    expect(state.seenEventIds[EVENT_A]).toBe(true);
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

describe('CV Manager reprocess via sole SSE reducer', () => {
  it('reprocess-shaped events use the same turn/start + sse/event path', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'turn/start',
      clientKey: 'user:reprocess-1',
      message:
        'Re-extract the retained CV and prepare the current draft for approval.',
    });
    state = reduceAll(state, [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc-reprocess',
          tool_name: 'propose_profile_from_cv',
          status: 'running',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_C, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc-reprocess',
          tool_name: 'propose_profile_from_cv',
          status: 'completed',
          duration_ms: 40,
          summary: 'draft ready',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_D, 'approval_required', {
          state: 'interrupted',
          kind: 'profile_commit',
          allowed_actions: ['save_profile', 'request_changes'],
          card: {
            tool_name: 'propose_profile_from_cv',
            current_title: 'Engineer',
            draft_id: 'current',
          },
        }),
      ),
    ]);

    expect(state.messages[0]?.role).toBe('user');
    expect(state.messages[0]?.content).toContain('Re-extract');
    expect(state.pendingApproval?.kind).toBe('profile_commit');
    expect(state.messages.some((m) => m.run?.state === 'interrupted')).toBe(
      true,
    );
    // No second store: streamPhase settles idle on interrupt like normal turns.
    expect(state.streamPhase).toBe('idle');
    expect(isComposerLocked(state)).toBe(true);
  });

  it('reprocess HTTP precondition failure does not invent completion', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'turn/start',
      clientKey: 'user:reprocess-2',
      message: 'Re-extract',
    });
    state = chatReducer(state, {
      type: 'stream/http_failed',
      code: 'CV_NOT_REPROCESSABLE',
      summary: 'Attachment is not reprocessable',
    });
    expect(state.streamPhase).toBe('failed');
    expect(state.streamError?.code).toBe('CV_NOT_REPROCESSABLE');
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
    // Stream path keeps resultData null; history may carry compact data or null.
    expect(messages[0].run?.tools[0].resultData).toBeNull();
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

  it('reconciles an optimistic user turn with durable history without collapsing same-text turns', () => {
    const message = 'Repeat this message';
    let state = chatReducer(createInitialChatState(), {
      type: 'turn/start',
      clientKey: 'user:optimistic',
      message,
      createdAt: TS,
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
    });

    const durable = historyPage();
    state = chatReducer(state, {
      type: 'history/rehydrate',
      page: {
        ...durable,
        items: [
          {
            id: MSG_OLD,
            role: 'user',
            content: message,
            structured_payload: null,
            created_at: TS_OLD,
            updated_at: TS_OLD,
            run: null,
          },
          {...durable.items[0], content: message},
          durable.items[1],
        ],
      },
    });

    const users = state.messages.filter((item) => item.role === 'user');
    expect(users.map((item) => item.id)).toEqual([MSG_OLD, MSG_USER]);
    expect(users.map((item) => item.content)).toEqual([message, message]);
    expect(users.find((item) => item.id === MSG_USER)?.run?.tools[0]?.source).toBe(
      'history',
    );
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
    expect(before?.[0].resultData).toBeNull();

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
    // data was null in this fixture — still explicit, not stream-shaped.
    expect(userFromHistory?.run?.tools[0].resultData).toBeNull();

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

describe('read_active_cv stream-null vs terminal history projection', () => {
  const ATTACHMENT = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';

  function activeCvToolData(
    overrides: Record<string, unknown> = {},
  ): import('../features/chat/types').JsonObject {
    return {
      attachment_id: ATTACHMENT,
      extraction_version: 'v1',
      source_hash: 'hash-1',
      mode: 'section',
      records: [
        {
          kind: 'entry',
          section_id: 'sec',
          entry_id: 'e1',
          ordinal: 0,
          title: 'Cert',
          subtitle: null,
          date_text: null,
          location: null,
          body: 'One certificate',
          bullets: [],
          source_chunk_ordinals: [0],
        },
      ],
      returned_chars: 15,
      truncated: false,
      next_cursor: null,
      ...overrides,
    } as import('../features/chat/types').JsonObject;
  }

  it('stream tool_status for read_active_cv keeps resultData null', () => {
    const state = reduceAll(createInitialChatState(), [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc-cv',
          tool_name: 'read_active_cv',
          status: 'completed',
          duration_ms: 10,
          summary: 'stream never carries body',
          error_code: null,
        }),
      ),
    ]);
    const tools = state.messages.find((m) => m.role === 'assistant')?.run?.tools;
    expect(tools?.[0].toolName).toBe('read_active_cv');
    expect(tools?.[0].status).toBe('completed');
    expect(tools?.[0].source).toBe('stream');
    expect(tools?.[0].resultData).toBeNull();
  });

  it('terminal rehydrate and restart hydrate projected read_active_cv evidence', () => {
    const state = reduceAll(createInitialChatState(), [
      parseSseEventData(
        envelope(EVENT_A, 'run_started', {state: 'running', resumed: false}),
      ),
      parseSseEventData(
        envelope(EVENT_B, 'tool_status', {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc-cv',
          tool_name: 'read_active_cv',
          status: 'running',
        }),
      ),
      parseSseEventData(
        envelope(EVENT_C, 'run_completed', {state: 'completed'}),
      ),
    ]);
    expect(
      state.messages.find((m) => m.role === 'assistant')?.run?.tools[0]
        .resultData,
    ).toBeNull();

    const durablePage: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'How many certs?',
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
                tool_call_id: 'tc-cv',
                tool_name: 'read_active_cv',
                status: 'completed',
                duration_ms: 20,
                error_code: null,
                result: {
                  ok: true,
                  code: null,
                  summary: '1 record',
                  data: activeCvToolData({
                    next_cursor: 'opaque',
                    storage_path: '/secret.pdf',
                  }),
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
          content: 'You have one certificate.',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };

    const rehydrated = rehydrateWithDurableTruth(state.messages, durablePage);
    const userTools = rehydrated.messages.find((m) => m.id === MSG_USER)?.run
      ?.tools;
    expect(userTools?.[0].source).toBe('history');
    expect(userTools?.[0].status).toBe('completed');
    expect(userTools?.[0].resultData).not.toBeNull();
    expect(userTools?.[0].resultData?.has_more).toBe(true);
    expect(userTools?.[0].resultData).not.toHaveProperty('next_cursor');
    expect(userTools?.[0].resultData).not.toHaveProperty('storage_path');
    expect(
      (userTools?.[0].resultData?.records as Array<Record<string, unknown>>)[0]
        .body,
    ).toBe('One certificate');

    const cold = hydrateFromHistoryPage(durablePage);
    const coldTools = cold.messages.find((m) => m.id === MSG_USER)?.run?.tools;
    expect(coldTools?.[0].resultData).toEqual(userTools?.[0].resultData);
  });
});
