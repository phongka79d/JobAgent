import {render} from '@testing-library/react';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {vi} from 'vitest';

import type {ObservabilityApi} from '../../features/observability/api';
import type {
  ChunkDetail,
  ChunkListPage,
  CvHistoryPage,
  GraphSnapshot,
  RunHistoryPage,
} from '../../features/observability/types';
import {CvSidebar} from '../../features/profile/CvSidebar';
import type {ProfileReadResponse} from '../../features/profile/types';

export const ATTACHMENT_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
export const RUN_ID = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
export const TOOL_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
export const MSG_ID = 'dddddddd-eeee-4fff-8aaa-111111111111';

export function installMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList => ({
      matches,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

export function emptyProfile(): ProfileReadResponse {
  return {
    present: false,
    profile: null,
    preferences: null,
    active_attachment: null,
    draft_present: false,
    pending_attachment: null,
  };
}

export function cvHistoryPage(available = true): CvHistoryPage {
  return {
    items: [
      {
        id: ATTACHMENT_ID,
        original_name: 'archived.pdf',
        mime_type: 'application/pdf',
        size_bytes: 2048,
        page_count: 1,
        state: 'archived',
        failure_code: null,
        file_hash_abbreviated: 'abcdef012345',
        file_available: available,
        created_at: '2024-07-01T12:00:00Z',
        updated_at: '2024-07-01T12:00:00Z',
      },
    ],
    next_cursor: null,
  };
}

export function chunkListPage(): ChunkListPage {
  return {
    items: [
      {
        attachment_id: ATTACHMENT_ID,
        ordinal: 0,
        preview: 'Preview only text',
        char_count: 40,
        token_estimate: 10,
        created_at: '2024-07-01T12:00:00Z',
      },
    ],
    next_cursor: null,
  };
}

export function chunkDetail(): ChunkDetail {
  return {
    attachment_id: ATTACHMENT_ID,
    ordinal: 0,
    text: 'Full expanded chunk body for inspection',
    preview: 'Full expanded',
    char_count: 40,
    token_estimate: 10,
    created_at: '2024-07-01T12:00:00Z',
  };
}

export function graphReady(): GraphSnapshot {
  return {
    status: 'ready',
    code: null,
    summary: 'Graph projection ready',
    rebuild_instruction: null,
    candidate: {id: 'cand-1', revision: 'r1'},
    jobs: [{id: 'job-1', title: 'Engineer', company: 'Acme', revision: 'j1'}],
    skills: [{canonical_name: 'python'}],
    edges: [
      {source_id: 'cand-1', target_id: 'python', type: 'HAS_SKILL'},
    ],
    nodes_truncated: true,
    edges_truncated: false,
    omitted_node_count: 2,
    omitted_edge_count: 0,
    checked_at: '2024-07-01T12:00:00Z',
  };
}

export function runsPage(): RunHistoryPage {
  return {
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
            summary: 'profile draft proposed',
          },
        ],
      },
    ],
    next_cursor: null,
  };
}

export function mockObservabilityApi(
  overrides: Partial<ObservabilityApi> = {},
): ObservabilityApi {
  return {
    fetchCvHistory: vi.fn().mockResolvedValue(cvHistoryPage()),
    fetchChunkList: vi.fn().mockResolvedValue(chunkListPage()),
    fetchChunkDetail: vi.fn().mockResolvedValue(chunkDetail()),
    fetchRunHistory: vi.fn().mockResolvedValue(runsPage()),
    fetchGraphSnapshot: vi.fn().mockResolvedValue(graphReady()),
    getRetainedCvUrl: (id: string) =>
      `http://api.test/api/observability/cvs/${id}/file`,
    ...overrides,
  };
}

export function renderObservabilitySidebar(
  api?: ObservabilityApi,
): ReturnType<typeof render> & {
  api: ObservabilityApi;
  loadProfile: ReturnType<typeof vi.fn>;
} {
  const resolvedApi = api ?? mockObservabilityApi();
  const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
  return {
    api: resolvedApi,
    loadProfile,
    ...render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          isUploadDisabled={false}
          onSidebarUploadSuccess={vi.fn()}
          deps={{
            loadProfile,
            uploadCv: vi.fn(),
            observability: resolvedApi,
          }}
        />
      </Theme>,
    ),
  };
}
