/**
 * Observability sidebar UI: lazy tabs, cache, expand, collapse, safe errors (03A).
 */
import {
  cleanup,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {ObservabilityApi} from '../features/observability/api';
import type {
  ChunkDetail,
  ChunkListPage,
  CvHistoryPage,
  GraphSnapshot,
  RunHistoryPage,
} from '../features/observability/types';
import {CvSidebar} from '../features/profile/CvSidebar';
import type {ProfileReadResponse} from '../features/profile/types';

const ATTACHMENT_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const RUN_ID = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const TOOL_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
const MSG_ID = 'dddddddd-eeee-4fff-8aaa-111111111111';

function emptyProfile(): ProfileReadResponse {
  return {
    present: false,
    profile: null,
    preferences: null,
    active_attachment: null,
    draft_present: false,
    pending_attachment: null,
  };
}

function cvHistoryPage(available = true): CvHistoryPage {
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

function chunkListPage(): ChunkListPage {
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

function chunkDetail(): ChunkDetail {
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

function graphReady(): GraphSnapshot {
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

function runsPage(): RunHistoryPage {
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

function mockApi(overrides: Partial<ObservabilityApi> = {}): ObservabilityApi {
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

function renderSidebar(api: ObservabilityApi = mockApi()) {
  const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
  return {
    api,
    loadProfile,
    ...render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          isUploadDisabled={false}
          onSidebarUploadSuccess={vi.fn()}
          deps={{loadProfile, uploadCv: vi.fn(), observability: api}}
        />
      </Theme>,
    ),
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

describe('ObservabilitySidebar composition', () => {
  it('defaults to Overview and does not fetch other tabs until selected', async () => {
    const api = mockApi();
    renderSidebar(api);

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-obs-overview')).toBeInTheDocument();
    });
    expect(screen.getByTestId('jobagent-profile-state')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-cv-upload')).toBeInTheDocument();
    expect(api.fetchCvHistory).not.toHaveBeenCalled();
    expect(api.fetchRunHistory).not.toHaveBeenCalled();
    expect(api.fetchGraphSnapshot).not.toHaveBeenCalled();
    expect(api.fetchChunkList).not.toHaveBeenCalled();
  });

  it('lazy-loads CV history, caches success, and keeps data after error refresh', async () => {
    const fetchCvHistory = vi
      .fn()
      .mockResolvedValueOnce(cvHistoryPage())
      .mockRejectedValueOnce(
        Object.assign(new Error('boom'), {
          name: 'ChatApiError',
          status: 500,
          code: 'HTTP_ERROR',
          summary: 'Server error',
        }),
      );
    // Use real ChatApiError shape via mock that load maps with toSafeError
    const {ChatApiError} = await import('../lib/api/chat');
    fetchCvHistory
      .mockReset()
      .mockResolvedValueOnce(cvHistoryPage())
      .mockRejectedValueOnce(new ChatApiError(500, 'HTTP_ERROR', 'Server error'));

    const api = mockApi({fetchCvHistory});
    renderSidebar(api);

    await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
    await waitFor(() => {
      expect(api.fetchCvHistory).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText('archived.pdf')).toBeInTheDocument();

    // Re-select overview then history again — uses cache, no second fetch.
    await userEvent.click(screen.getByTestId('jobagent-obs-tab-overview'));
    await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
    await waitFor(() => {
      expect(screen.getByText('archived.pdf')).toBeInTheDocument();
    });
    expect(api.fetchCvHistory).toHaveBeenCalledTimes(1);

    // Explicit refresh forces a second request; prior data retained on failure.
    await userEvent.click(screen.getByTestId('jobagent-obs-cv-history-refresh'));
    await waitFor(() => {
      expect(api.fetchCvHistory).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByText('archived.pdf')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-obs-cv-history-error')).toBeInTheDocument();
  });

  it('requires selection for chunks, expands full text on demand, and gates file open', async () => {
    const api = mockApi();
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderSidebar(api);

    await userEvent.click(screen.getByTestId('jobagent-obs-tab-chunks'));
    expect(
      await screen.findByTestId('jobagent-obs-chunks-no-selection'),
    ).toBeInTheDocument();
    expect(api.fetchChunkList).not.toHaveBeenCalled();

    await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
    await waitFor(() => {
      expect(screen.getByText('archived.pdf')).toBeInTheDocument();
    });
    await userEvent.click(
      screen.getByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    await userEvent.click(
      screen.getByTestId(`jobagent-obs-cv-open-${ATTACHMENT_ID}`),
    );
    expect(openSpy).toHaveBeenCalledWith(
      `http://api.test/api/observability/cvs/${ATTACHMENT_ID}/file`,
      '_blank',
      'noopener,noreferrer',
    );

    await userEvent.click(screen.getByTestId('jobagent-obs-tab-chunks'));
    await waitFor(() => {
      expect(api.fetchChunkList).toHaveBeenCalledWith(
        ATTACHMENT_ID,
        {},
        expect.anything(),
      );
    });
    expect(screen.getByText('Preview only text')).toBeInTheDocument();
    expect(screen.queryByText('Full expanded chunk body for inspection')).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId('jobagent-obs-chunk-expand-0'));
    await waitFor(() => {
      expect(api.fetchChunkDetail).toHaveBeenCalled();
    });
    expect(
      await screen.findByTestId('jobagent-obs-chunk-fulltext-0'),
    ).toHaveTextContent('Full expanded chunk body for inspection');
  });

  it('disables open/download when file_available is false', async () => {
    const api = mockApi({
      fetchCvHistory: vi.fn().mockResolvedValue(cvHistoryPage(false)),
    });
    renderSidebar(api);
    await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
    await waitFor(() => {
      expect(screen.getByText('archived.pdf')).toBeInTheDocument();
    });
    const openBtn = screen.getByTestId(`jobagent-obs-cv-open-${ATTACHMENT_ID}`);
    expect(openBtn).toBeDisabled();
  });

  it('renders graph semantic fallback with truncation metadata', async () => {
    const api = mockApi();
    renderSidebar(api);
    await userEvent.click(screen.getByTestId('jobagent-obs-tab-graph'));
    await waitFor(() => {
      expect(api.fetchGraphSnapshot).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByTestId('jobagent-obs-graph-jobs')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-obs-graph-meta')).toHaveTextContent(
      /nodes truncated \(\+2\)/,
    );
    expect(screen.getByText('python')).toBeInTheDocument();
    expect(screen.getByText(/HAS_SKILL/)).toBeInTheDocument();
  });

  it('loads runs and expands structured tool details', async () => {
    const api = mockApi();
    renderSidebar(api);
    await userEvent.click(screen.getByTestId('jobagent-obs-tab-runs'));
    await waitFor(() => {
      expect(api.fetchRunHistory).toHaveBeenCalledTimes(1);
    });
    await userEvent.click(screen.getByTestId(`jobagent-obs-run-toggle-${RUN_ID}`));
    expect(
      await screen.findByTestId(`jobagent-obs-run-detail-${RUN_ID}`),
    ).toHaveTextContent('propose_profile_from_cv');
  });

  it('collapse control exposes aria-expanded and toggles compact status', async () => {
    renderSidebar();
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-obs-tabs')).toBeInTheDocument();
    });
    const collapse = screen.getByTestId('jobagent-sidebar-collapse');
    expect(collapse).toHaveAttribute('aria-expanded', 'true');

    await userEvent.click(collapse);
    expect(collapse).toHaveAttribute('aria-expanded', 'false');
    expect(
      await screen.findByTestId('jobagent-obs-collapsed-status'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-obs-tabs')).not.toBeInTheDocument();

    await userEvent.click(collapse);
    expect(collapse).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByTestId('jobagent-obs-tabs')).toBeInTheDocument();
  });

  it('shows empty and error states for independent tabs', async () => {
    const {ChatApiError} = await import('../lib/api/chat');
    const api = mockApi({
      fetchRunHistory: vi
        .fn()
        .mockRejectedValue(
          new ChatApiError(503, 'SERVICE_UNAVAILABLE', 'Runs offline'),
        ),
      fetchCvHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
    });
    renderSidebar(api);

    await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
    expect(
      await screen.findByTestId('jobagent-obs-cv-history-empty'),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('jobagent-obs-tab-runs'));
    expect(
      await screen.findByTestId('jobagent-obs-runs-error'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Runs offline/)).toBeInTheDocument();
  });
});
