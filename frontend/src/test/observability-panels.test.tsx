import {act, cleanup, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  ATTACHMENT_ID,
  chunkDetail,
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
    expect(item).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('jobagent-obs-cv-detail')).toHaveTextContent(
      'abcdef012345',
    );
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

  it('selects a pending chunk and ignores late success after collapse', async () => {
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
    await act(async () => {
      resolveDetail(chunkDetail());
      await pendingDetail;
    });

    expect(row).not.toHaveAttribute('aria-selected');
    expect(
      screen.queryByTestId('jobagent-obs-chunk-fulltext-0'),
    ).not.toBeInTheDocument();
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
});
