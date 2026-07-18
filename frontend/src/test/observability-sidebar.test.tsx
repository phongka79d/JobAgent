/**
 * Observability sidebar UI: lazy tabs, cache, expand, collapse, safe errors (03A).
 * Plan 11: open-tab activation reload without blank idle CV Manager.
 */
import {useState} from 'react';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {
  cleanup,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {CvSidebar} from '../features/profile/CvSidebar';
import {
  ATTACHMENT_ID,
  RUN_ID,
  cvHistoryPage,
  emptyProfile,
  mockObservabilityApi,
  renderObservabilitySidebar,
} from './support/observability';

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
    const api = mockObservabilityApi();
    renderObservabilitySidebar(api);

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

    const api = mockObservabilityApi({fetchCvHistory});
    renderObservabilitySidebar(api);

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
    const api = mockObservabilityApi();
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderObservabilitySidebar(api);

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

    await userEvent.click(screen.getByTestId('jobagent-obs-chunk-toggle-0'));
    await waitFor(() => {
      expect(api.fetchChunkDetail).toHaveBeenCalled();
    });
    expect(
      await screen.findByTestId('jobagent-obs-chunk-fulltext-0'),
    ).toHaveTextContent('Full expanded chunk body for inspection');
  });

  it('disables open/download when file_available is false', async () => {
    const api = mockObservabilityApi({
      fetchCvHistory: vi.fn().mockResolvedValue(cvHistoryPage(false)),
    });
    renderObservabilitySidebar(api);
    await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
    await waitFor(() => {
      expect(screen.getByText('archived.pdf')).toBeInTheDocument();
    });
    await userEvent.click(
      screen.getByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    const openBtn = screen.getByTestId(`jobagent-obs-cv-open-${ATTACHMENT_ID}`);
    expect(openBtn).toBeDisabled();
  });

  it('renders graph canvas with truncation metadata and semantic fallback', async () => {
    const api = mockObservabilityApi();
    renderObservabilitySidebar(api);
    await userEvent.click(screen.getByTestId('jobagent-obs-tab-graph'));
    await waitFor(() => {
      expect(api.fetchGraphSnapshot).toHaveBeenCalledTimes(1);
    });
    expect(
      await screen.findByRole('group', {
        name: 'Candidate, jobs and skills network',
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-obs-graph-meta')).toHaveTextContent(
      /nodes truncated \(\+2\)/,
    );
    await userEvent.click(screen.getByText('Graph data'));
    expect(screen.getByTestId('jobagent-obs-graph-skills')).toHaveTextContent(
      'python',
    );
    expect(screen.getByTestId('jobagent-obs-graph-edges')).toHaveTextContent(
      'HAS_SKILL',
    );
  });

  it('loads runs and expands structured tool details', async () => {
    const api = mockObservabilityApi();
    renderObservabilitySidebar(api);
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
    renderObservabilitySidebar();
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-obs-tabs')).toBeInTheDocument();
    });
    let collapse = screen.getByTestId('jobagent-sidebar-collapse');
    expect(collapse).toHaveAttribute('aria-expanded', 'true');

    await userEvent.click(collapse);
    collapse = screen.getByTestId('jobagent-sidebar-collapse');
    expect(collapse).toHaveAttribute('aria-expanded', 'false');
    expect(
      await screen.findByTestId('jobagent-obs-collapsed-status'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-obs-tabs')).not.toBeInTheDocument();

    await userEvent.click(collapse);
    collapse = screen.getByTestId('jobagent-sidebar-collapse');
    expect(collapse).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByTestId('jobagent-obs-tabs')).toBeInTheDocument();
  });

  it('shows empty and error states for independent tabs', async () => {
    const {ChatApiError} = await import('../lib/api/chat');
    const api = mockObservabilityApi({
      fetchRunHistory: vi
        .fn()
        .mockRejectedValue(
          new ChatApiError(503, 'SERVICE_UNAVAILABLE', 'Runs offline'),
        ),
      fetchCvHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
    });
    renderObservabilitySidebar(api);

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

  it('activation with CV Manager open retains rows and issues one history reload', async () => {
    let resolveSecond!: (value: ReturnType<typeof cvHistoryPage>) => void;
    const secondPromise = new Promise<ReturnType<typeof cvHistoryPage>>(
      (resolve) => {
        resolveSecond = resolve;
      },
    );
    const first = cvHistoryPage();
    const second = cvHistoryPage();
    second.items[0] = {
      ...second.items[0]!,
      original_name: 'activated.pdf',
      state: 'active',
    };
    const fetchCvHistory = vi
      .fn()
      .mockResolvedValueOnce(first)
      .mockReturnValueOnce(secondPromise);
    const api = mockObservabilityApi({fetchCvHistory});
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());

    function Harness() {
      const [activationKey, setActivationKey] = useState(0);
      return (
        <>
          <button
            type="button"
            data-testid="test-bump-activation"
            onClick={() => setActivationKey((k) => k + 1)}
          >
            activate
          </button>
          <CvSidebar
            isUploadDisabled={false}
            onSidebarUploadSuccess={vi.fn()}
            activationKey={activationKey}
            deps={{
              loadProfile,
              uploadCv: vi.fn(),
              observability: api,
            }}
          />
        </>
      );
    }

    render(
      <Theme theme={neutralTheme}>
        <Harness />
      </Theme>,
    );

    await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
    expect(await screen.findByText('archived.pdf')).toBeInTheDocument();
    expect(fetchCvHistory).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByTestId('test-bump-activation'));

    await waitFor(() => {
      expect(fetchCvHistory).toHaveBeenCalledTimes(2);
    });
    // Prior safe row remains visible while the activation reload is in flight
    // (not header-only idle / empty).
    expect(screen.getByText('archived.pdf')).toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-obs-cv-history-empty'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-obs-cv-history-loading'),
    ).not.toBeInTheDocument();

    resolveSecond(second);
    expect(await screen.findByText('activated.pdf')).toBeInTheDocument();
    expect(screen.queryByText('archived.pdf')).not.toBeInTheDocument();
  });
});
