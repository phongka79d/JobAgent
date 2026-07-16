import {render, screen} from '@testing-library/react';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it, vi} from 'vitest';

import {ObservabilityListSkeleton} from '../features/observability/ObservabilityListSkeleton';
import {ObservabilityPanelHeader} from '../features/observability/ObservabilityPanelHeader';
import {
  formatDurationMs,
  formatObservabilityDateTime,
  formatRunDuration,
} from '../features/observability/observabilityFormat';

describe('observability presentation primitives', () => {
  it('formats valid values and preserves invalid timestamps safely', () => {
    expect(formatDurationMs(96)).toBe('96 ms');
    expect(formatDurationMs(1800)).toBe('1.8 s');
    expect(formatDurationMs(60000)).toBe('1 min');
    expect(formatRunDuration('2024-07-01T12:00:00Z', '2024-07-01T12:00:12Z')).toBe(
      '12 s',
    );
    expect(formatObservabilityDateTime('not-a-date')).toBe('not-a-date');
  });

  it('renders accessible refresh chrome and known-shape skeleton rows', () => {
    render(
      <Theme theme={neutralTheme}>
        <ObservabilityPanelHeader
          eyebrow="RUN HISTORY"
          title="Recent activity"
          onRefresh={vi.fn()}
          isRefreshing
          refreshTestId="refresh-runs"
        />
        <ObservabilityListSkeleton rows={3} testId="runs-skeleton" />
      </Theme>,
    );
    const refreshButton = screen.getByRole('button', {
      name: 'Refresh Recent activity',
    });
    expect(refreshButton).toHaveAttribute('aria-disabled', 'true');
    expect(refreshButton).not.toBeDisabled();
    expect(screen.getByTestId('runs-skeleton').children).toHaveLength(3);
  });
});
