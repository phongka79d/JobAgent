import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {GraphPanel} from '../features/observability/GraphPanel';
import {graphReady} from './support/observability';

const graphCanvasState = vi.hoisted(() => ({shouldThrow: true}));

vi.mock('../features/observability/GraphCanvas', () => ({
  GraphCanvas() {
    if (graphCanvasState.shouldThrow) {
      throw new Error('Forced graph canvas failure');
    }
    return <div data-testid="jobagent-graph-canvas-recovered" />;
  },
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  graphCanvasState.shouldThrow = true;
});

describe('graph visualization failure isolation', () => {
  it('keeps the semantic fallback mounted when the canvas fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const snapshot = graphReady();

    expect(() =>
      render(
        <Theme theme={neutralTheme}>
          <GraphPanel
            resource={{
              phase: 'ready',
              data: snapshot,
              error: null,
              loaded: true,
            }}
            onRefresh={vi.fn()}
          />
        </Theme>,
      ),
    ).not.toThrow();
    expect(
      screen.getByTestId('jobagent-graph-visualization-error'),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByText('Graph data'));
    expect(screen.getByTestId('jobagent-obs-graph-edges')).toHaveTextContent(
      'cand-1 —HAS_SKILL→ python',
    );
  });

  it('recovers a failed canvas on a new same-topology snapshot', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const snapshot = graphReady();
    const view = render(
      <Theme theme={neutralTheme}>
        <GraphPanel
          resource={{phase: 'ready', data: snapshot, error: null, loaded: true}}
          onRefresh={vi.fn()}
        />
      </Theme>,
    );

    expect(
      screen.getByTestId('jobagent-graph-visualization-error'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByText('Graph data'));
    expect(screen.getByTestId('jobagent-obs-graph-edges')).toHaveTextContent(
      /cand-1.*HAS_SKILL.*python/,
    );

    graphCanvasState.shouldThrow = false;
    const refreshedSnapshot = {
      ...snapshot,
      summary: 'Graph projection refreshed',
      checked_at: '2024-07-01T12:05:00Z',
    };
    view.rerender(
      <Theme theme={neutralTheme}>
        <GraphPanel
          resource={{
            phase: 'ready',
            data: refreshedSnapshot,
            error: null,
            loaded: true,
          }}
          onRefresh={vi.fn()}
        />
      </Theme>,
    );

    expect(
      screen.getByTestId('jobagent-graph-canvas-recovered'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-obs-graph-edges')).toHaveTextContent(
      /cand-1.*HAS_SKILL.*python/,
    );
  });
});
