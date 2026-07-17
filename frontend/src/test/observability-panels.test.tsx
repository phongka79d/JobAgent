import {cleanup, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  ATTACHMENT_ID,
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
});
