import {act, cleanup, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  ATTACHMENT_ID,
  chunkDetail,
  chunkListPage,
  installMatchMedia,
  mockObservabilityApi,
  renderObservabilitySidebar,
} from './support/observability';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  installMatchMedia(false);
});

describe('Observability list panels', () => {
  it('selects a CV from one divided Astryx list and shows details outside the row', async () => {
    const api = mockObservabilityApi();
    renderObservabilitySidebar(api);
    await userEvent.click(screen.getByRole('tab', {name: 'CV history'}));
    const item = await screen.findByTestId(
      `jobagent-obs-cv-select-${ATTACHMENT_ID}`,
    );
    await userEvent.click(item);
    const panel = screen.getByTestId('jobagent-obs-cv-history');
    const detail = within(panel).getByTestId('jobagent-obs-cv-detail');
    expect(item).toHaveAttribute('aria-selected', 'true');
    expect(item).not.toContainElement(detail);
    expect(within(panel).getAllByRole('list', {name: 'CV history'})).toHaveLength(1);
    expect(within(panel).getAllByTestId('jobagent-obs-cv-detail')).toHaveLength(1);
    expect(detail).toHaveTextContent('abcdef012345');
    expect(
      screen.getByTestId(`jobagent-obs-cv-open-${ATTACHMENT_ID}`),
    ).toBeEnabled();
  });

  it('loads one chunk detail from the selected list row', async () => {
    const api = mockObservabilityApi();
    renderObservabilitySidebar(api);
    await userEvent.click(screen.getByRole('tab', {name: 'CV history'}));
    await userEvent.click(
      await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    await userEvent.click(screen.getByRole('tab', {name: 'LLM chunks'}));
    await userEvent.click(
      await screen.findByTestId('jobagent-obs-chunk-toggle-0'),
    );
    expect(
      await screen.findByTestId('jobagent-obs-chunk-fulltext-0'),
    ).toHaveTextContent('Full expanded chunk body for inspection');
  });

  it('deduplicates a pending chunk after collapse and re-expansion', async () => {
    let resolveDetail!: (detail: ReturnType<typeof chunkDetail>) => void;
    const pendingDetail = new Promise<ReturnType<typeof chunkDetail>>(
      (resolve) => {
        resolveDetail = resolve;
      },
    );
    const api = mockObservabilityApi({
      fetchChunkDetail: vi.fn().mockReturnValue(pendingDetail),
    });
    renderObservabilitySidebar(api);
    await userEvent.click(screen.getByRole('tab', {name: 'CV history'}));
    await userEvent.click(
      await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    await userEvent.click(screen.getByRole('tab', {name: 'LLM chunks'}));
    const row = await screen.findByTestId('jobagent-obs-chunk-toggle-0');

    await userEvent.click(row);
    expect(row).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByLabelText('Loading full text...')).toBeInTheDocument();

    await userEvent.click(row);
    expect(row).not.toHaveAttribute('aria-selected');

    await userEvent.click(row);
    expect(row).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByLabelText('Loading full text...')).toBeInTheDocument();
    expect(api.fetchChunkDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveDetail(chunkDetail());
      await pendingDetail;
    });

    expect(
      await screen.findByTestId('jobagent-obs-chunk-fulltext-0'),
    ).toHaveTextContent('Full expanded chunk body for inspection');
  });

  it('keeps a rejected chunk selected and shows only the safe error', async () => {
    const {ChatApiError} = await import('../lib/api/chat');
    const error = Object.assign(
      new ChatApiError(500, 'DETAIL_FAILED', 'Chunk detail unavailable'),
      {raw_payload: 'raw-secret-chunk-payload'},
    );
    const api = mockObservabilityApi({
      fetchChunkDetail: vi.fn().mockRejectedValue(error),
    });
    renderObservabilitySidebar(api);
    await userEvent.click(screen.getByRole('tab', {name: 'CV history'}));
    await userEvent.click(
      await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    await userEvent.click(screen.getByRole('tab', {name: 'LLM chunks'}));
    const row = await screen.findByTestId('jobagent-obs-chunk-toggle-0');

    await userEvent.click(row);
    const banner = await screen.findByTestId(
      'jobagent-obs-chunk-detail-error-0',
    );
    expect(row).toHaveAttribute('aria-selected', 'true');
    expect(banner).toHaveTextContent('Chunk detail unavailable');
    expect(banner).toHaveTextContent('DETAIL_FAILED');
    expect(screen.queryByText('raw-secret-chunk-payload')).not.toBeInTheDocument();
  });

  it('keeps cached chunk rows after a safe refresh error', async () => {
    const {ChatApiError} = await import('../lib/api/chat');
    const error = Object.assign(
      new ChatApiError(500, 'CHUNK_LIST_FAILED', 'Chunk list refresh failed'),
      {raw_payload: 'raw-secret-list-payload'},
    );
    const fetchChunkList = vi
      .fn()
      .mockResolvedValueOnce(chunkListPage())
      .mockRejectedValueOnce(error);
    const api = mockObservabilityApi({fetchChunkList});
    renderObservabilitySidebar(api);
    await userEvent.click(screen.getByRole('tab', {name: 'CV history'}));
    await userEvent.click(
      await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    await userEvent.click(screen.getByRole('tab', {name: 'LLM chunks'}));
    const row = await screen.findByTestId('jobagent-obs-chunk-toggle-0');
    expect(
      screen.queryByTestId('jobagent-obs-chunk-fulltext-0'),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId('jobagent-obs-chunks-refresh'));
    await waitFor(() => {
      expect(fetchChunkList).toHaveBeenCalledTimes(2);
    });
    const banner = await screen.findByTestId('jobagent-obs-chunks-error');
    expect(row).toBeInTheDocument();
    expect(banner).toHaveTextContent('Chunk list refresh failed');
    expect(banner).toHaveTextContent('CHUNK_LIST_FAILED');
    expect(screen.queryByText('raw-secret-list-payload')).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-obs-chunk-fulltext-0'),
    ).not.toBeInTheDocument();
  });
});
