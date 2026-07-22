/**
 * Observability API typing and transport tests (Plan 8 / 03A).
 */
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  fetchChunkDetail,
  fetchChunkList,
  fetchCvHistory,
  fetchGraphSnapshot,
  fetchRunHistory,
  getRetainedCvUrl,
} from '../features/observability/api';
import {
  parseChunkDetail,
  parseChunkListPage,
  parseCvHistoryPage,
  parseGraphSnapshot,
  parseRunHistoryPage,
} from '../features/observability/types';
import {getApiBaseUrl} from '../lib/api/chat';

const ATTACHMENT_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const RUN_ID = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const TOOL_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
const MSG_ID = 'dddddddd-eeee-4fff-8aaa-111111111111';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('observability parsers', () => {
  it('parses CV history page and rejects storage_path / full file_hash', () => {
    const page = parseCvHistoryPage({
      items: [
        {
          id: ATTACHMENT_ID,
          original_name: 'resume.pdf',
          mime_type: 'application/pdf',
          size_bytes: 1024,
          page_count: 2,
          state: 'archived',
          failure_code: null,
          file_hash_abbreviated: 'abcdef012345',
          file_available: true,
          created_at: '2024-07-01T12:00:00Z',
          updated_at: '2024-07-01T12:00:00Z',
        },
      ],
      next_cursor: null,
    });
    expect(page.items).toHaveLength(1);
    expect(page.items[0]!.file_available).toBe(true);
    expect(page.items[0]!.state).toBe('archived');

    expect(() =>
      parseCvHistoryPage({
        items: [
          {
            id: ATTACHMENT_ID,
            original_name: 'resume.pdf',
            mime_type: 'application/pdf',
            size_bytes: 1024,
            page_count: 1,
            state: 'active',
            failure_code: null,
            file_hash_abbreviated: 'abcdef012345',
            file_available: true,
            created_at: '2024-07-01T12:00:00Z',
            updated_at: '2024-07-01T12:00:00Z',
            storage_path: 'secret/path',
          },
        ],
        next_cursor: null,
      }),
    ).toThrow(/storage_path/);

    expect(() =>
      parseCvHistoryPage({
        items: [
          {
            id: ATTACHMENT_ID,
            original_name: 'resume.pdf',
            mime_type: 'application/pdf',
            size_bytes: 1024,
            page_count: 1,
            state: 'active',
            failure_code: null,
            file_hash: 'full-hash-must-not-appear',
            file_hash_abbreviated: 'abcdef012345',
            file_available: true,
            created_at: '2024-07-01T12:00:00Z',
            updated_at: '2024-07-01T12:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    ).toThrow(/file_hash/);
  });

  it('parses chunk list without full text and chunk detail with full text', () => {
    const list = parseChunkListPage({
      items: [
        {
          attachment_id: ATTACHMENT_ID,
          ordinal: 0,
          preview: 'Hello preview',
          char_count: 120,
          token_estimate: 30,
          created_at: '2024-07-01T12:00:00Z',
        },
      ],
      next_cursor: null,
    });
    expect(list.items[0]!.preview).toBe('Hello preview');
    expect(() =>
      parseChunkListPage({
        items: [
          {
            attachment_id: ATTACHMENT_ID,
            ordinal: 0,
            preview: 'x',
            text: 'full text must not be here',
            char_count: 1,
            token_estimate: 1,
            created_at: '2024-07-01T12:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    ).toThrow(/full text/);

    const detail = parseChunkDetail({
      attachment_id: ATTACHMENT_ID,
      ordinal: 0,
      text: 'Full canonical chunk text',
      preview: 'Full canonic',
      char_count: 25,
      token_estimate: 7,
      created_at: '2024-07-01T12:00:00Z',
    });
    expect(detail.text).toBe('Full canonical chunk text');
  });

  it('parses run history without checkpoints or tool arguments', () => {
    const page = parseRunHistoryPage({
      items: [
        {
          id: RUN_ID,
          user_message_id: MSG_ID,
          state: 'completed',
          error_code: null,
          completed_at: '2024-07-01T12:01:00Z',
          created_at: '2024-07-01T12:00:00Z',
          updated_at: '2024-07-01T12:01:00Z',
          related_attachment_ids: [ATTACHMENT_ID],
          related_job_ids: [],
          tool_executions: [
            {
              id: TOOL_ID,
              tool_name: 'propose_profile_from_cv',
              status: 'completed',
              duration_ms: 12,
              error_code: null,
              summary: 'ok',
            },
          ],
        },
      ],
      next_cursor: null,
    });
    expect(page.items[0]!.tool_executions[0]!.tool_name).toBe(
      'propose_profile_from_cv',
    );

    expect(() =>
      parseRunHistoryPage({
        items: [
          {
            id: RUN_ID,
            user_message_id: MSG_ID,
            state: 'completed',
            error_code: null,
            completed_at: null,
            created_at: '2024-07-01T12:00:00Z',
            updated_at: '2024-07-01T12:00:00Z',
            related_attachment_ids: [],
            related_job_ids: [],
            tool_executions: [],
            checkpoint: {secret: true},
          },
        ],
        next_cursor: null,
      }),
    ).toThrow(/checkpoint/);
  });

  it('parses graph snapshot truncation and status contracts', () => {
    const snapshot = parseGraphSnapshot({
      status: 'ready',
      code: null,
      summary: 'Graph projection ready',
      rebuild_instruction: null,
      candidate: {id: 'cand-1', revision: 'r1'},
      jobs: [{id: 'job-1', title: 'Engineer', company: 'Acme', revision: 'j1'}],
      skills: [
        {
          canonical_name: 'audience_research',
          canonical_key: 'audience_research',
          display_name: 'Nghiên cứu đối tượng',
          category: 'research',
        },
      ],
      edges: [
        {
          source_id: 'cand-1',
          target_id: 'python',
          type: 'HAS_SKILL',
        },
      ],
      nodes_truncated: true,
      edges_truncated: false,
      omitted_node_count: 3,
      omitted_edge_count: 0,
      checked_at: '2024-07-01T12:00:00Z',
    });
    expect(snapshot.status).toBe('ready');
    expect(snapshot.nodes_truncated).toBe(true);
    expect(snapshot.omitted_node_count).toBe(3);
    // Plan-8 payloads without CV branch default empty.
    expect(snapshot.cv).toBeNull();
    expect(snapshot.sections).toEqual([]);
    expect(snapshot.entries).toEqual([]);
    expect(snapshot.skills).toEqual([
      {
        canonical_name: 'audience_research',
        canonical_key: 'audience_research',
        display_name: 'Nghiên cứu đối tượng',
        category: 'research',
      },
    ]);

    const stale = parseGraphSnapshot({
      status: 'stale',
      code: 'NEO4J_REBUILD_REQUIRED',
      summary: 'Revision mismatch',
      rebuild_instruction: 'Run graph rebuild',
      candidate: null,
      jobs: [],
      skills: [],
      edges: [],
      nodes_truncated: false,
      edges_truncated: false,
      omitted_node_count: 0,
      omitted_edge_count: 0,
      checked_at: '2024-07-01T12:00:00Z',
    });
    expect(stale.status).toBe('stale');
  });

  it('accepts active CV branch fields and structural edge types', () => {
    const snapshot = parseGraphSnapshot({
      status: 'ready',
      code: null,
      summary: 'ready with CV',
      rebuild_instruction: null,
      cv: {
        id: ATTACHMENT_ID,
        original_name: 'cv.pdf',
        extraction_version: 'doc-v1',
        revision: 'rev-cv',
      },
      sections: [
        {
          id: 's1',
          heading: 'Skills',
          kind: 'skills',
          ordinal: 0,
          entry_count: 0,
        },
      ],
      entries: [],
      candidate: {id: 'cand-1', revision: 'r1'},
      jobs: [],
      skills: [],
      edges: [
        {source_id: 'cand-1', target_id: ATTACHMENT_ID, type: 'PROJECTS_TO'},
        {source_id: ATTACHMENT_ID, target_id: 's1', type: 'HAS_SECTION'},
      ],
      nodes_truncated: false,
      edges_truncated: false,
      omitted_node_count: 0,
      omitted_edge_count: 0,
      checked_at: '2024-07-01T12:00:00Z',
    });
    expect(snapshot.cv?.id).toBe(ATTACHMENT_ID);
    expect(snapshot.sections?.[0]?.heading).toBe('Skills');
    expect(snapshot.edges[0]?.type).toBe('PROJECTS_TO');
  });
});

describe('observability fetch helpers', () => {
  it('builds retained CV URL from VITE_API_BASE_URL only', () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    try {
      // @ts-expect-error test mutation of import.meta.env
      import.meta.env.VITE_API_BASE_URL = 'http://localhost:8000/';
      expect(getApiBaseUrl()).toBe('http://localhost:8000');
      expect(getRetainedCvUrl(ATTACHMENT_ID)).toBe(
        `http://localhost:8000/api/observability/cvs/${ATTACHMENT_ID}/file`,
      );
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });

  it('fetches and parses each observability endpoint', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/observability/cvs')) {
        return new Response(
          JSON.stringify({items: [], next_cursor: null}),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.includes('/chunks/') && !url.endsWith('/chunks')) {
        return new Response(
          JSON.stringify({
            attachment_id: ATTACHMENT_ID,
            ordinal: 0,
            text: 'full',
            preview: 'full',
            char_count: 4,
            token_estimate: 1,
            created_at: '2024-07-01T12:00:00Z',
          }),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.includes('/chunks')) {
        return new Response(
          JSON.stringify({items: [], next_cursor: null}),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.endsWith('/api/observability/runs')) {
        return new Response(
          JSON.stringify({items: [], next_cursor: null}),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.endsWith('/api/observability/graph')) {
        return new Response(
          JSON.stringify({
            status: 'unavailable',
            code: 'NEO4J_UNAVAILABLE',
            summary: 'Neo4j is unavailable',
            rebuild_instruction: null,
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
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      return new Response('missing', {status: 404});
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      await expect(fetchCvHistory()).resolves.toEqual({
        items: [],
        next_cursor: null,
      });
      await expect(fetchChunkList(ATTACHMENT_ID)).resolves.toEqual({
        items: [],
        next_cursor: null,
      });
      await expect(fetchChunkDetail(ATTACHMENT_ID, 0)).resolves.toMatchObject({
        text: 'full',
        ordinal: 0,
      });
      await expect(fetchRunHistory()).resolves.toEqual({
        items: [],
        next_cursor: null,
      });
      await expect(fetchGraphSnapshot()).resolves.toMatchObject({
        status: 'unavailable',
        code: 'NEO4J_UNAVAILABLE',
      });

      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls).toContain('http://api.test/api/observability/cvs');
      expect(urls).toContain(
        `http://api.test/api/observability/cvs/${ATTACHMENT_ID}/chunks`,
      );
      expect(urls).toContain(
        `http://api.test/api/observability/cvs/${ATTACHMENT_ID}/chunks/0`,
      );
      expect(urls).toContain('http://api.test/api/observability/runs');
      expect(urls).toContain('http://api.test/api/observability/graph');
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});
