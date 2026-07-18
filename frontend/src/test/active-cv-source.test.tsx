/**
 * Strict durable read_active_cv evidence projection and row binding (Plan 12 02A).
 * Covers allowlists, bounds, forbidden-key stripping, completed-success gating,
 * revision consistency, multipage order, and row isolation.
 */
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  activeCvEvidenceForTools,
  parseActiveCvPageData,
  projectActiveCvResultData,
  READ_ACTIVE_CV_TOOL_NAME,
} from '../features/chat/activeCvEvidence';
import {
  ActiveCvSourceDialog,
  ACTIVE_CV_PARTIAL_NOTICE,
} from '../features/chat/components/ActiveCvSourceDialog';
import {
  projectToolResultData,
  toolViewToActivity,
  hydrateFromHistoryPage,
  rehydrateWithDurableTruth,
} from '../features/chat/history';
import {
  chatReducer,
  createInitialChatState,
  type ClientToolActivity,
} from '../features/chat/reducer';
import {
  parseSseEventData,
  type HistoryPage,
  type JsonObject,
  type ToolExecutionView,
  type ToolResult,
} from '../features/chat/types';
import {getRetainedCvUrl} from '../features/observability/api';

const ATTACHMENT =
  'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const ATTACHMENT_B =
  'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const RUN_ID = '11111111-1111-4111-8111-111111111111';
const TOOL_EXEC = '22222222-2222-4222-8222-222222222222';
const TOOL_EXEC_2 = '33333333-3333-4333-8333-333333333333';
const TOOL_EXEC_3 = '44444444-4444-4444-8444-444444444444';
const MSG_USER = '55555555-5555-4555-8555-555555555555';
const MSG_ASST = '66666666-6666-4666-8666-666666666666';
const MSG_USER_2 = '77777777-7777-4777-8777-777777777777';
const MSG_ASST_2 = '88888888-8888-4888-8888-888888888888';
const EVENT_A = '99999999-9999-4999-8999-999999999999';
const EVENT_B = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const TS = '2026-07-18T12:00:00.000Z';

function entryRecord(overrides: JsonObject = {}): JsonObject {
  return {
    kind: 'entry',
    section_id: 'sec-certs',
    entry_id: 'entry-1',
    ordinal: 0,
    title: 'AWS Certified',
    subtitle: null,
    date_text: '2024',
    location: null,
    body: 'Cloud practitioner certificate.',
    bullets: ['Exam passed'],
    source_chunk_ordinals: [0, 1],
    ...overrides,
  };
}

function entryMatchRecord(overrides: JsonObject = {}): JsonObject {
  return {
    ...entryRecord({
      kind: 'entry_match',
      excerpt: 'Cloud practitioner certificate.',
    }),
    ...overrides,
  };
}

function chunkRecord(overrides: JsonObject = {}): JsonObject {
  return {
    kind: 'chunk',
    ordinal: 0,
    text: 'Raw chunk text about certificates.',
    char_count: 35,
    ...overrides,
  };
}

function chunkMatchRecord(overrides: JsonObject = {}): JsonObject {
  return {
    ...chunkRecord({
      kind: 'chunk_match',
      excerpt: 'certificates',
    }),
    ...overrides,
  };
}

function rawPage(
  records: JsonObject[] = [entryRecord()],
  overrides: JsonObject = {},
): JsonObject {
  return {
    attachment_id: ATTACHMENT,
    extraction_version: 'v1',
    source_hash: 'hash-abc',
    mode: 'section',
    records,
    returned_chars: 40,
    truncated: false,
    next_cursor: null,
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
      summary: 'Read active CV page',
      data: resultData,
    } satisfies ToolResult);
  return {
    id: TOOL_EXEC,
    tool_call_id: 'tc-cv-1',
    tool_name: READ_ACTIVE_CV_TOOL_NAME,
    status: 'completed',
    duration_ms: 40,
    error_code: null,
    arguments_summary: null,
    created_at: TS,
    updated_at: TS,
    ...overrides,
    result,
  };
}

function activityFrom(
  resultData: JsonObject | null,
  overrides: Partial<ClientToolActivity> = {},
): ClientToolActivity {
  return {
    toolExecutionId: TOOL_EXEC,
    toolCallId: 'tc-cv-1',
    toolName: READ_ACTIVE_CV_TOOL_NAME,
    status: 'completed',
    durationMs: 40,
    summary: 'ok',
    errorCode: null,
    source: 'history',
    resultData,
    ...overrides,
  };
}

function historyWithCv(
  data: JsonObject | null = rawPage(),
  toolOverrides?: Parameters<typeof toolExecution>[1],
): HistoryPage {
  const tool = toolExecution(data, toolOverrides);
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'Tôi có mấy Certificate?',
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
        content: 'Bạn có 1 Certificate.',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

describe('projectActiveCvResultData allowlist and bounds', () => {
  it('projects entry page with approved fields, exact content, derived has_more false', () => {
    const raw = rawPage([entryRecord()], {
      next_cursor: null,
      returned_chars: 42,
    });
    const projected = projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, raw);
    expect(projected).not.toBeNull();
    expect(projected).not.toHaveProperty('next_cursor');
    expect(projected?.has_more).toBe(false);
    expect(projected?.attachment_id).toBe(ATTACHMENT);
    expect(projected?.extraction_version).toBe('v1');
    expect(projected?.source_hash).toBe('hash-abc');
    expect(projected?.mode).toBe('section');
    expect(projected?.returned_chars).toBe(42);
    expect(projected?.truncated).toBe(false);
    const rec = (projected?.records as JsonObject[])[0];
    expect(rec).toEqual(entryRecord());
    expect(rec).not.toHaveProperty('storage_path');
    expect(rec).not.toHaveProperty('provider');
  });

  it('projects entry_match, chunk, and chunk_match with optional excerpt/record_truncated', () => {
    const entryM = entryMatchRecord({record_truncated: true});
    const chunk = chunkRecord({text: 'chunk body', char_count: 10});
    const chunkM = chunkMatchRecord({excerpt: 'hit'});
    for (const [mode, record] of [
      ['search', entryM],
      ['chunk', chunk],
      ['search', chunkM],
    ] as const) {
      const projected = projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([record], {mode, next_cursor: 'opaque-cursor'}),
      );
      expect(projected?.has_more).toBe(true);
      expect(projected).not.toHaveProperty('next_cursor');
      expect((projected?.records as JsonObject[])[0]).toEqual(record);
    }
  });

  it('strips forbidden top-level and record keys while keeping allowlisted content', () => {
    const raw = rawPage(
      [
        entryRecord({
          storage_path: '/secret.pdf',
          embedding: [0.1],
          api_key: 'sk',
        }),
      ],
      {
        next_cursor: 'c1',
        arguments: {section_id: 'x'},
        storage_path: '/data/cv.pdf',
        prompt: 'SYSTEM',
        credentials: {token: 't'},
        stack: 'Error',
        provider_payload: {},
      },
    );
    const projected = projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, raw);
    expect(projected).not.toBeNull();
    expect(projected).not.toHaveProperty('next_cursor');
    expect(projected).not.toHaveProperty('arguments');
    expect(projected).not.toHaveProperty('storage_path');
    expect(projected).not.toHaveProperty('prompt');
    expect(projected).not.toHaveProperty('credentials');
    expect(projected).not.toHaveProperty('stack');
    expect(projected).not.toHaveProperty('provider_payload');
    const rec = (projected?.records as JsonObject[])[0];
    expect(rec).not.toHaveProperty('storage_path');
    expect(rec).not.toHaveProperty('embedding');
    expect(rec).not.toHaveProperty('api_key');
    expect(rec.body).toBe('Cloud practitioner certificate.');
  });

  it('preserves multipage record order and exact string content', () => {
    const records = [
      entryRecord({entry_id: 'e0', ordinal: 0, body: 'First exact'}),
      entryRecord({entry_id: 'e1', ordinal: 1, body: 'Second exact'}),
      entryRecord({entry_id: 'e2', ordinal: 2, body: 'Third exact'}),
    ];
    const projected = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage(records, {returned_chars: 33}),
    );
    const out = projected?.records as JsonObject[];
    expect(out.map((r) => r.entry_id)).toEqual(['e0', 'e1', 'e2']);
    expect(out.map((r) => r.body)).toEqual([
      'First exact',
      'Second exact',
      'Third exact',
    ]);
  });

  it('accepts source_hash null (legacy) and boundary returned_chars 0 and 12000', () => {
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([entryRecord()], {
          source_hash: null,
          returned_chars: 0,
        }),
      )?.source_hash,
    ).toBeNull();
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([entryRecord()], {returned_chars: 12_000}),
      )?.returned_chars,
    ).toBe(12_000);
  });

  it('accepts page size 1 and 10 records; rejects empty and 11', () => {
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([entryRecord()]),
      ),
    ).not.toBeNull();
    const ten = Array.from({length: 10}, (_, i) =>
      entryRecord({entry_id: `e${i}`, ordinal: i}),
    );
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage(ten)),
    ).not.toBeNull();
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([]),
      ),
    ).toBeNull();
    const eleven = Array.from({length: 11}, (_, i) =>
      entryRecord({entry_id: `e${i}`, ordinal: i}),
    );
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage(eleven)),
    ).toBeNull();
  });

  it('returns null for missing/invalid required fields and wrong vocabulary', () => {
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, null),
    ).toBeNull();
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage([entryRecord()], {
        attachment_id: 'not-a-uuid',
      })),
    ).toBeNull();
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage([entryRecord()], {
        extraction_version: '',
      })),
    ).toBeNull();
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage([entryRecord()], {
        mode: 'vector',
      })),
    ).toBeNull();
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage([entryRecord()], {
        returned_chars: 12_001,
      })),
    ).toBeNull();
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage([entryRecord()], {
        returned_chars: -1,
      })),
    ).toBeNull();
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage([entryRecord()], {
        truncated: 'yes',
      })),
    ).toBeNull();
    expect(
      projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, rawPage([entryRecord()], {
        next_cursor: 12,
      })),
    ).toBeNull();
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([entryRecord({kind: 'unknown'})]),
      ),
    ).toBeNull();
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([entryRecord({ordinal: -1})]),
      ),
    ).toBeNull();
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([entryRecord({bullets: 'not-list'})]),
      ),
    ).toBeNull();
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([entryRecord({source_chunk_ordinals: [-1]})]),
      ),
    ).toBeNull();
    expect(
      projectActiveCvResultData(
        READ_ACTIVE_CV_TOOL_NAME,
        rawPage([chunkRecord({text: 99 as unknown as string})]),
      ),
    ).toBeNull();
  });

  it('returns null for non-read_active_cv tool names', () => {
    expect(
      projectActiveCvResultData('save_job', rawPage()),
    ).toBeNull();
    expect(
      projectActiveCvResultData('match_jobs', rawPage()),
    ).toBeNull();
    expect(
      projectActiveCvResultData('query_jobs', rawPage()),
    ).toBeNull();
  });

  it('parseActiveCvPageData accepts already-projected has_more without cursor', () => {
    const projected = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()], {next_cursor: 'more'}),
    );
    expect(projected).not.toBeNull();
    const parsed = parseActiveCvPageData(projected);
    expect(parsed?.has_more).toBe(true);
    expect(parsed?.records[0]).toMatchObject({kind: 'entry'});
  });
});

describe('history projection chain for read_active_cv', () => {
  it('projectToolResultData chains after save/match and projects active CV', () => {
    const projected = projectToolResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()], {next_cursor: 'c'}),
    );
    expect(projected?.has_more).toBe(true);
    expect(projected).not.toHaveProperty('next_cursor');
  });

  it('toolViewToActivity projects allowlisted read_active_cv and drops adversarial keys', () => {
    const activity = toolViewToActivity(
      toolExecution(
        rawPage([entryRecord({secret: 'x'})], {
          next_cursor: null,
          storage_path: '/p',
          stack: 'trace',
        }),
      ),
    );
    expect(activity.source).toBe('history');
    expect(activity.resultData).not.toBeNull();
    expect(activity.resultData).not.toHaveProperty('next_cursor');
    expect(activity.resultData).not.toHaveProperty('storage_path');
    expect(activity.resultData).not.toHaveProperty('stack');
    expect(activity.resultData?.has_more).toBe(false);
    expect(
      parseActiveCvPageData(activity.resultData)?.records[0],
    ).toMatchObject({entry_id: 'entry-1'});
  });

  it('toolViewToActivity retains null resultData for failed/empty/malformed pages', () => {
    expect(
      toolViewToActivity(
        toolExecution(rawPage([]), {
          status: 'completed',
        }),
      ).resultData,
    ).toBeNull();
    expect(
      toolViewToActivity(
        toolExecution(rawPage([entryRecord()], {mode: 'vector'})),
      ).resultData,
    ).toBeNull();
    expect(
      toolViewToActivity(
        toolExecution(null, {
          status: 'failed',
          error_code: 'NO_ACTIVE_CV',
          result: {
            ok: false,
            code: 'NO_ACTIVE_CV',
            summary: 'none',
            data: null,
          },
        }),
      ).resultData,
    ).toBeNull();
  });

  it('hydrateFromHistoryPage supplies durable active-CV resultData', () => {
    const {messages} = hydrateFromHistoryPage(
      historyWithCv(rawPage([entryRecord()], {next_cursor: 'more'})),
    );
    const tools = messages.find((m) => m.id === MSG_USER)?.run?.tools;
    expect(tools?.[0].source).toBe('history');
    expect(tools?.[0].resultData?.has_more).toBe(true);
    expect(tools?.[0].resultData).not.toHaveProperty('next_cursor');
  });
});

describe('activeCvEvidenceForTools selection and revision binding', () => {
  it('selects completed successful pages in durable tool order', () => {
    const p1 = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord({entry_id: 'first'})], {next_cursor: 'c'}),
    );
    const p2 = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord({entry_id: 'second'})], {
        mode: 'chunk',
        next_cursor: null,
        records: [chunkRecord({ordinal: 1, text: 'page2', char_count: 5})],
      }),
    );
    const bundle = activeCvEvidenceForTools([
      activityFrom(p1, {
        toolExecutionId: TOOL_EXEC,
        toolCallId: 'tc1',
      }),
      activityFrom(p2, {
        toolExecutionId: TOOL_EXEC_2,
        toolCallId: 'tc2',
      }),
    ]);
    expect(bundle).not.toBeNull();
    expect(bundle?.pages).toHaveLength(2);
    expect(bundle?.pages[0].records[0]).toMatchObject({entry_id: 'first'});
    expect(bundle?.pages[1].records[0]).toMatchObject({
      kind: 'chunk',
      text: 'page2',
    });
    expect(bundle?.attachment_id).toBe(ATTACHMENT);
    expect(bundle?.extraction_version).toBe('v1');
    expect(bundle?.source_hash).toBe('hash-abc');
  });

  it('ignores failed/malformed pages when another valid page exists', () => {
    const valid = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()]),
    );
    const bundle = activeCvEvidenceForTools([
      activityFrom(null, {
        toolExecutionId: TOOL_EXEC,
        status: 'failed',
        errorCode: 'NO_ACTIVE_CV',
      }),
      activityFrom(null, {
        toolExecutionId: TOOL_EXEC_2,
        status: 'completed',
        errorCode: null,
        resultData: {broken: true} as JsonObject,
      }),
      activityFrom(valid, {
        toolExecutionId: TOOL_EXEC_3,
      }),
      activityFrom(valid, {
        toolExecutionId: 'other-tool',
        toolName: 'save_job',
      }),
    ]);
    expect(bundle?.pages).toHaveLength(1);
    expect(bundle?.pages[0].records[0]).toMatchObject({kind: 'entry'});
  });

  it('returns null when no valid page / empty-only / non-CV tools', () => {
    expect(activeCvEvidenceForTools([])).toBeNull();
    expect(
      activeCvEvidenceForTools([
        activityFrom(null, {status: 'running', errorCode: null}),
      ]),
    ).toBeNull();
    expect(
      activeCvEvidenceForTools([
        activityFrom(null, {
          toolName: 'match_jobs',
          status: 'completed',
        }),
      ]),
    ).toBeNull();
    expect(
      activeCvEvidenceForTools([
        activityFrom(null, {
          status: 'completed',
          errorCode: 'X',
          resultData: projectActiveCvResultData(
            READ_ACTIVE_CV_TOOL_NAME,
            rawPage(),
          ),
        }),
      ]),
    ).toBeNull();
  });

  it('suppresses entire bundle when valid pages disagree on revision', () => {
    const a = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()], {attachment_id: ATTACHMENT, source_hash: 'h1'}),
    );
    const b = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()], {
        attachment_id: ATTACHMENT_B,
        source_hash: 'h1',
      }),
    );
    const c = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()], {
        attachment_id: ATTACHMENT,
        source_hash: 'h2',
      }),
    );
    const d = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()], {
        attachment_id: ATTACHMENT,
        extraction_version: 'v2',
        source_hash: 'h1',
      }),
    );
    expect(
      activeCvEvidenceForTools([
        activityFrom(a, {toolExecutionId: TOOL_EXEC}),
        activityFrom(b, {toolExecutionId: TOOL_EXEC_2}),
      ]),
    ).toBeNull();
    expect(
      activeCvEvidenceForTools([
        activityFrom(a, {toolExecutionId: TOOL_EXEC}),
        activityFrom(c, {toolExecutionId: TOOL_EXEC_2}),
      ]),
    ).toBeNull();
    expect(
      activeCvEvidenceForTools([
        activityFrom(a, {toolExecutionId: TOOL_EXEC}),
        activityFrom(d, {toolExecutionId: TOOL_EXEC_2}),
      ]),
    ).toBeNull();
  });

  it('allows consistent legacy null source_hash across pages', () => {
    const p1 = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord()], {source_hash: null, next_cursor: 'c'}),
    );
    const p2 = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([chunkRecord()], {
        mode: 'chunk',
        source_hash: null,
        next_cursor: null,
      }),
    );
    const bundle = activeCvEvidenceForTools([
      activityFrom(p1, {toolExecutionId: TOOL_EXEC}),
      activityFrom(p2, {toolExecutionId: TOOL_EXEC_2}),
    ]);
    expect(bundle?.source_hash).toBeNull();
    expect(bundle?.pages).toHaveLength(2);
  });

  it('does not borrow evidence across neighboring tools without row association', () => {
    // Selector only sees the tools array it is given — neighbor tools not passed.
    const neighbor = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord({entry_id: 'neighbor'})]),
    );
    const emptyRow = activeCvEvidenceForTools([]);
    expect(emptyRow).toBeNull();
    // Only this row's tools participate.
    const rowOnly = activeCvEvidenceForTools([
      activityFrom(neighbor, {toolExecutionId: TOOL_EXEC}),
    ]);
    expect(rowOnly?.pages[0].records[0]).toMatchObject({
      entry_id: 'neighbor',
    });
  });
});

describe('stream vs terminal active-CV evidence', () => {
  it('stream tool_status keeps resultData null for read_active_cv', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'sse/event',
      event: parseSseEventData({
        event_id: EVENT_A,
        run_id: RUN_ID,
        timestamp: TS,
        event: 'run_started',
        payload: {state: 'running', resumed: false},
      }),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: parseSseEventData({
        event_id: EVENT_B,
        run_id: RUN_ID,
        timestamp: TS,
        event: 'tool_status',
        payload: {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: READ_ACTIVE_CV_TOOL_NAME,
          status: 'running',
          duration_ms: null,
          summary: 'Reading…',
          error_code: null,
        },
      }),
    });
    const tools = state.messages.find((m) => m.role === 'assistant')?.run
      ?.tools;
    expect(tools?.[0].resultData).toBeNull();
    expect(tools?.[0].source).toBe('stream');
    expect(
      activeCvEvidenceForTools(tools ?? []),
    ).toBeNull();
  });

  it('terminal rehydrate and restart hydrate the same durable evidence bundle', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'sse/event',
      event: parseSseEventData({
        event_id: EVENT_A,
        run_id: RUN_ID,
        timestamp: TS,
        event: 'run_started',
        payload: {state: 'running', resumed: false},
      }),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: parseSseEventData({
        event_id: EVENT_B,
        run_id: RUN_ID,
        timestamp: TS,
        event: 'tool_status',
        payload: {
          tool_execution_id: TOOL_EXEC,
          tool_call_id: 'tc1',
          tool_name: READ_ACTIVE_CV_TOOL_NAME,
          status: 'running',
          duration_ms: null,
          summary: null,
          error_code: null,
        },
      }),
    });

    const page = historyWithCv(
      rawPage([entryRecord(), entryRecord({entry_id: 'e2', ordinal: 1})], {
        next_cursor: null,
      }),
    );
    const rehydrated = rehydrateWithDurableTruth(state.messages, page);
    const userTools = rehydrated.messages.find((m) => m.id === MSG_USER)?.run
      ?.tools;
    expect(userTools?.[0].source).toBe('history');
    expect(userTools?.[0].resultData).not.toBeNull();
    const fromRehydrate = activeCvEvidenceForTools(userTools ?? []);
    expect(fromRehydrate?.pages[0].records).toHaveLength(2);

    const cold = hydrateFromHistoryPage(page);
    const coldTools = cold.messages.find((m) => m.id === MSG_USER)?.run?.tools;
    const fromCold = activeCvEvidenceForTools(coldTools ?? []);
    expect(fromCold).toEqual(fromRehydrate);
  });

  it('evidence never crosses a second turn boundary when tools are per-row', () => {
    const pageA = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord({entry_id: 'turn-a'})]),
    );
    const pageB = projectActiveCvResultData(
      READ_ACTIVE_CV_TOOL_NAME,
      rawPage([entryRecord({entry_id: 'turn-b'})], {
        attachment_id: ATTACHMENT_B,
        source_hash: 'other',
      }),
    );
    // Each assistant row receives only its associated tools.
    expect(
      activeCvEvidenceForTools([
        activityFrom(pageA, {toolExecutionId: TOOL_EXEC}),
      ])?.pages[0].records[0],
    ).toMatchObject({entry_id: 'turn-a'});
    expect(
      activeCvEvidenceForTools([
        activityFrom(pageB, {toolExecutionId: TOOL_EXEC_2}),
      ])?.pages[0].records[0],
    ).toMatchObject({entry_id: 'turn-b'});
    // Mixing revisions (as if wrongly shared) suppresses.
    expect(
      activeCvEvidenceForTools([
        activityFrom(pageA, {toolExecutionId: TOOL_EXEC}),
        activityFrom(pageB, {toolExecutionId: TOOL_EXEC_2}),
      ]),
    ).toBeNull();

    // History with two turns keeps tools on each user run separately.
    const multi: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'q1',
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
              toolExecution(rawPage([entryRecord({entry_id: 'turn-a'})])),
            ],
          },
        },
        {
          id: MSG_ASST,
          role: 'assistant',
          content: 'a1',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
        {
          id: MSG_USER_2,
          role: 'user',
          content: 'q2',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: {
            id: 'aaaaaaaa-bbbb-4ccc-8ddd-ffffffffffff',
            user_message_id: MSG_USER_2,
            state: 'completed',
            pending_approval: null,
            error_code: null,
            completed_at: TS,
            created_at: TS,
            updated_at: TS,
            tool_executions: [
              toolExecution(
                rawPage([entryRecord({entry_id: 'turn-b'})], {
                  attachment_id: ATTACHMENT_B,
                }),
                {
                  id: TOOL_EXEC_2,
                  tool_call_id: 'tc2',
                },
              ),
            ],
          },
        },
        {
          id: MSG_ASST_2,
          role: 'assistant',
          content: 'a2',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
    const {messages} = hydrateFromHistoryPage(multi);
    const t1 = messages.find((m) => m.id === MSG_USER)?.run?.tools ?? [];
    const t2 = messages.find((m) => m.id === MSG_USER_2)?.run?.tools ?? [];
    expect(activeCvEvidenceForTools(t1)?.pages[0].records[0]).toMatchObject({
      entry_id: 'turn-a',
    });
    expect(activeCvEvidenceForTools(t2)?.pages[0].records[0]).toMatchObject({
      entry_id: 'turn-b',
    });
  });
});

describe('ActiveCvSourceDialog exact evidence and original CV', () => {
  beforeEach(() => {
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModal() {
        this.setAttribute('open', '');
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function close() {
        this.removeAttribute('open');
      };
    }
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  function evidenceBundle(
    pages: JsonObject[] = [rawPage([entryRecord()])],
  ): NonNullable<ReturnType<typeof activeCvEvidenceForTools>> {
    const tools = pages.map((page, i) =>
      activityFrom(
        projectActiveCvResultData(READ_ACTIVE_CV_TOOL_NAME, page),
        {
          toolExecutionId: i === 0 ? TOOL_EXEC : TOOL_EXEC_2,
          toolCallId: `tc-${i}`,
        },
      ),
    );
    const bundle = activeCvEvidenceForTools(tools);
    if (!bundle) {
      throw new Error('expected bundle');
    }
    return bundle;
  }

  it('renders every page and record in durable order without deduplication', () => {
    const page1 = rawPage(
      [
        entryRecord({entry_id: 'e0', body: 'First exact body'}),
        entryRecord({entry_id: 'e1', body: 'Second exact body', ordinal: 1}),
      ],
      {next_cursor: 'more'},
    );
    const page2 = rawPage(
      [
        chunkRecord({ordinal: 0, text: 'Chunk zero text', char_count: 15}),
        chunkMatchRecord({
          ordinal: 1,
          text: 'Chunk match text',
          char_count: 16,
          excerpt: 'match hit',
        }),
      ],
      {mode: 'search', next_cursor: null},
    );
    // Duplicate body intentionally retained — Agent saw both.
    const page3 = rawPage(
      [entryRecord({entry_id: 'e0', body: 'First exact body'})],
      {mode: 'section', next_cursor: null},
    );

    const evidence = evidenceBundle([page1, page2, page3]);
    render(
      <Theme theme={neutralTheme}>
        <ActiveCvSourceDialog
          isOpen
          onOpenChange={() => {}}
          evidence={evidence}
        />
      </Theme>,
    );

    expect(screen.getByText('Nguồn từ CV')).toBeInTheDocument();
    const pages = screen.getAllByTestId('jobagent-active-cv-evidence-page');
    expect(pages).toHaveLength(3);
    const records = screen.getAllByTestId('jobagent-active-cv-evidence-record');
    expect(records).toHaveLength(5);
    // Exact content preserved including duplicate.
    expect(screen.getAllByText('First exact body')).toHaveLength(2);
    expect(screen.getByText('Second exact body')).toBeInTheDocument();
    expect(screen.getByText('Chunk zero text')).toBeInTheDocument();
    expect(screen.getByText('Chunk match text')).toBeInTheDocument();
    expect(screen.getByText(/Excerpt: match hit/)).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-active-cv-partial-notice'),
    ).toBeInTheDocument();
    expect(screen.getByText(ACTIVE_CV_PARTIAL_NOTICE)).toBeInTheDocument();
  });

  it('opens the answer attachment via getRetainedCvUrl with required options', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';
    try {
      const openSpy = vi
        .spyOn(window, 'open')
        .mockImplementation(() => null);
      const fetchSpy = vi.spyOn(globalThis, 'fetch');
      const evidence = evidenceBundle([
        rawPage([entryRecord()], {attachment_id: ATTACHMENT}),
      ]);

      const user = userEvent.setup();
      render(
        <Theme theme={neutralTheme}>
          <ActiveCvSourceDialog
            isOpen
            onOpenChange={() => {}}
            evidence={evidence}
          />
        </Theme>,
      );

      await user.click(screen.getByTestId('jobagent-active-cv-open-original'));
      expect(openSpy).toHaveBeenCalledTimes(1);
      expect(openSpy).toHaveBeenCalledWith(
        getRetainedCvUrl(ATTACHMENT),
        '_blank',
        'noopener,noreferrer',
      );
      // Zero evidence/chunk network requests from the dialog.
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });

  it('closes via button and Escape without fetching', async () => {
    const onOpenChange = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const user = userEvent.setup();
    render(
      <Theme theme={neutralTheme}>
        <ActiveCvSourceDialog
          isOpen
          onOpenChange={onOpenChange}
          evidence={evidenceBundle()}
        />
      </Theme>,
    );

    await user.click(screen.getByTestId('jobagent-active-cv-close'));
    expect(onOpenChange).toHaveBeenCalledWith(false);

    onOpenChange.mockClear();
    await user.keyboard('{Escape}');
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('shows entry metadata, bullets, and search excerpts; no hash/cursor as primary copy', () => {
    const evidence = evidenceBundle([
      rawPage(
        [
          entryMatchRecord({
            title: 'AWS Certified',
            subtitle: 'Foundational',
            date_text: '2024',
            location: 'Remote',
            excerpt: 'Cloud practitioner certificate.',
            bullets: ['Exam passed'],
          }),
        ],
        {mode: 'search', source_hash: 'secret-hash', next_cursor: null},
      ),
    ]);

    render(
      <Theme theme={neutralTheme}>
        <ActiveCvSourceDialog
          isOpen
          onOpenChange={() => {}}
          evidence={evidence}
        />
      </Theme>,
    );

    expect(screen.getByText('AWS Certified')).toBeInTheDocument();
    expect(screen.getByText('Foundational')).toBeInTheDocument();
    expect(screen.getByText('2024')).toBeInTheDocument();
    expect(screen.getByText('Remote')).toBeInTheDocument();
    expect(screen.getByText(/• Exam passed/)).toBeInTheDocument();
    expect(
      screen.getByText(/Excerpt: Cloud practitioner certificate\./),
    ).toBeInTheDocument();
    expect(screen.queryByText('secret-hash')).not.toBeInTheDocument();
    expect(screen.queryByText(/next_cursor/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/read_active_cv/i)).not.toBeInTheDocument();
  });
});
