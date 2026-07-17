/**
 * CV Manager typed transport tests (Plan 9 / 07A).
 * Reprocess SSE path, delete status mapping, forbidden-field rejection.
 */
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  asCvDeleteErrorCode,
  asCvReprocessErrorCode,
  CV_DELETE_ERROR_CODES,
  CV_DELETE_RETRY_SUMMARY,
  CV_REPROCESS_ERROR_CODES,
  deleteCv,
  isRetryableDeleteError,
  streamCvReprocess,
  toCvManagerActionError,
} from '../features/observability/api';
import {
  selectSafeRemainingAttachmentId,
} from '../features/observability/cvManagerTypes';
import {parseGraphSnapshot} from '../features/observability/types';
import {parseSseEventData} from '../features/chat/types';
import {chatReducer, createInitialChatState} from '../features/chat/reducer';

const ATTACHMENT_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const RUN_ID = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const EVENT_A = '11111111-1111-4111-8111-111111111111';
const EVENT_B = '22222222-2222-4222-8222-222222222222';
const TS = '2026-07-13T12:00:00.000Z';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('CV Manager error code classification', () => {
  it('maps every documented reprocess and delete status code', () => {
    for (const code of Object.values(CV_REPROCESS_ERROR_CODES)) {
      expect(asCvReprocessErrorCode(code)).toBe(code);
    }
    for (const code of Object.values(CV_DELETE_ERROR_CODES)) {
      expect(asCvDeleteErrorCode(code)).toBe(code);
    }
    expect(asCvReprocessErrorCode('UNKNOWN')).toBeNull();
    expect(asCvDeleteErrorCode('UNKNOWN')).toBeNull();
    expect(
      isRetryableDeleteError(CV_DELETE_ERROR_CODES.CV_DELETE_FILE_FAILED),
    ).toBe(true);
    expect(
      isRetryableDeleteError(CV_DELETE_ERROR_CODES.CV_ACTIVE_DELETE_FORBIDDEN),
    ).toBe(false);
    const partial = toCvManagerActionError({
      code: CV_DELETE_ERROR_CODES.CV_DELETE_GRAPH_FAILED,
      summary: 'internal path leak should be replaced',
    });
    expect(partial.retryable).toBe(true);
    expect(partial.summary).toBe(CV_DELETE_RETRY_SUMMARY);
  });

  it('selects a safe remaining attachment after delete', () => {
    const items = [
      {id: 'active-1', state: 'active'},
      {id: 'arch-1', state: 'archived'},
      {id: 'arch-2', state: 'archived'},
    ];
    expect(selectSafeRemainingAttachmentId(items, 'arch-1', 'arch-1')).toBe(
      'active-1',
    );
    expect(selectSafeRemainingAttachmentId(items, 'arch-1', 'arch-2')).toBe(
      'arch-2',
    );
    expect(selectSafeRemainingAttachmentId(items, 'active-1', 'active-1')).toBe(
      'arch-1',
    );
    expect(selectSafeRemainingAttachmentId([{id: 'only', state: 'archived'}], 'only', 'only')).toBeNull();
  });
});

describe('deleteCv transport', () => {
  it('succeeds on 204 and maps documented failures safely', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, {status: 204}))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: CV_DELETE_ERROR_CODES.CV_ACTIVE_DELETE_FORBIDDEN,
              summary: 'Active CV cannot be deleted',
            },
          }),
          {status: 409, headers: {'Content-Type': 'application/json'}},
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: CV_DELETE_ERROR_CODES.CV_DELETE_FILE_FAILED,
              summary: 'file step failed',
            },
          }),
          {status: 409, headers: {'Content-Type': 'application/json'}},
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: 'X',
              summary: 'y',
              storage_path: '/secret',
            },
          }),
          {status: 500, headers: {'Content-Type': 'application/json'}},
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    try {
      await expect(deleteCv(ATTACHMENT_ID)).resolves.toBeUndefined();
      await expect(deleteCv(ATTACHMENT_ID)).rejects.toMatchObject({
        code: CV_DELETE_ERROR_CODES.CV_ACTIVE_DELETE_FORBIDDEN,
      });
      await expect(deleteCv(ATTACHMENT_ID)).rejects.toMatchObject({
        code: CV_DELETE_ERROR_CODES.CV_DELETE_FILE_FAILED,
        summary: CV_DELETE_RETRY_SUMMARY,
      });
      await expect(deleteCv(ATTACHMENT_ID)).rejects.toMatchObject({
        code: 'FORBIDDEN_FIELD',
      });
      expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
        `http://api.test/api/cvs/${ATTACHMENT_ID}`,
      );
      expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({method: 'DELETE'});
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

describe('streamCvReprocess SSE path', () => {
  it('POSTs reprocess and feeds events into the sole chat reducer', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';

    const started = {
      event_id: EVENT_A,
      run_id: RUN_ID,
      timestamp: TS,
      event: 'run_started',
      payload: {state: 'running', resumed: false},
    };
    const approval = {
      event_id: EVENT_B,
      run_id: RUN_ID,
      timestamp: TS,
      event: 'approval_required',
      payload: {
        state: 'interrupted',
        kind: 'profile_commit',
        allowed_actions: ['save_profile', 'request_changes'],
        card: {
          tool_name: 'propose_profile_from_cv',
          current_title: 'Engineer',
          draft_id: 'current',
        },
      },
    };
    const body =
      `id: ${EVENT_A}\nevent: run_started\ndata: ${JSON.stringify(started)}\n\n` +
      `id: ${EVENT_B}\nevent: approval_required\ndata: ${JSON.stringify(approval)}\n\n`;

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, {
        status: 200,
        headers: {'Content-Type': 'text/event-stream'},
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    let state = createInitialChatState();
    const events: string[] = [];

    try {
      await streamCvReprocess(ATTACHMENT_ID, {
        onEvent: (event) => {
          events.push(event.event);
          state = chatReducer(state, {type: 'sse/event', event});
        },
      });

      expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
        `http://api.test/api/cvs/${ATTACHMENT_ID}/reprocess`,
      );
      expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({method: 'POST'});
      expect(events).toEqual(['run_started', 'approval_required']);
      expect(state.pendingApproval?.kind).toBe('profile_commit');
      expect(state.messages.some((m) => m.run?.state === 'interrupted')).toBe(
        true,
      );
      // Same parseSseEventData owner as chat turns.
      expect(
        parseSseEventData(started).event,
      ).toBe('run_started');
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });

  it('maps reprocess HTTP precondition failures', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: CV_REPROCESS_ERROR_CODES.CV_NOT_REPROCESSABLE,
              summary: 'Not reprocessable',
            },
          }),
          {status: 409, headers: {'Content-Type': 'application/json'}},
        ),
      ),
    );
    try {
      await expect(
        streamCvReprocess(ATTACHMENT_ID, {onEvent: () => undefined}),
      ).rejects.toMatchObject({
        code: CV_REPROCESS_ERROR_CODES.CV_NOT_REPROCESSABLE,
      });
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

describe('graph CV branch typing', () => {
  it('parses fixed CV/section/entry nodes and structural edges', () => {
    const snapshot = parseGraphSnapshot({
      status: 'ready',
      code: null,
      summary: 'ready',
      rebuild_instruction: null,
      cv: {
        id: ATTACHMENT_ID,
        original_name: 'resume.pdf',
        extraction_version: 'v1',
        revision: 'rev-1',
      },
      sections: [
        {
          id: 'sec-1',
          heading: 'Experience',
          kind: 'experience',
          ordinal: 0,
          entry_count: 1,
        },
      ],
      entries: [
        {
          id: 'ent-1',
          section_id: 'sec-1',
          ordinal: 0,
          title: 'Engineer',
          subtitle: 'Acme',
          date_text: '2020',
          preview: 'Did things',
        },
      ],
      candidate: {id: 'cand-1', revision: 'r1'},
      jobs: [],
      skills: [],
      edges: [
        {
          source_id: 'cand-1',
          target_id: ATTACHMENT_ID,
          type: 'PROJECTS_TO',
        },
        {
          source_id: ATTACHMENT_ID,
          target_id: 'sec-1',
          type: 'HAS_SECTION',
        },
        {
          source_id: 'sec-1',
          target_id: 'ent-1',
          type: 'HAS_ENTRY',
        },
      ],
      nodes_truncated: false,
      edges_truncated: false,
      omitted_node_count: 0,
      omitted_edge_count: 0,
      checked_at: '2024-07-01T12:00:00Z',
    });
    expect(snapshot.cv?.original_name).toBe('resume.pdf');
    expect(snapshot.sections).toHaveLength(1);
    expect(snapshot.entries?.[0]?.preview).toBe('Did things');
    expect(snapshot.edges.map((e) => e.type)).toEqual([
      'PROJECTS_TO',
      'HAS_SECTION',
      'HAS_ENTRY',
    ]);
    expect(() =>
      parseGraphSnapshot({
        status: 'ready',
        code: null,
        summary: 'ready',
        rebuild_instruction: null,
        cv: {
          id: ATTACHMENT_ID,
          original_name: 'x',
          extraction_version: 'v1',
          revision: 'r',
          storage_path: '/nope',
        },
        candidate: null,
        jobs: [],
        skills: [],
        edges: [],
        nodes_truncated: false,
        edges_truncated: false,
        omitted_node_count: 0,
        omitted_edge_count: 0,
        checked_at: '2024-07-01T12:00:00Z',
      }),
    ).toThrow(/storage_path/);
  });
});
