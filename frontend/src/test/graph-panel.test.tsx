import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {GraphPanel} from '../features/observability/GraphPanel';
import type {CachedResource} from '../features/observability/state';
import type {GraphSnapshot} from '../features/observability/types';
import {graphReady, installMatchMedia} from './support/observability';

function renderGraphPanel(
  snapshot: GraphSnapshot,
  resourceOverrides: Partial<CachedResource<GraphSnapshot>> = {},
) {
  const onRefresh = vi.fn();
  render(
    <Theme theme={neutralTheme}>
      <GraphPanel
        resource={{
          phase: 'ready',
          data: snapshot,
          error: null,
          loaded: true,
          ...resourceOverrides,
        }}
        onRefresh={onRefresh}
      />
    </Theme>,
  );
  fireEvent.click(screen.getByRole('radio', {name: 'Kỹ thuật'}));
  return {onRefresh};
}

afterEach(() => {
  cleanup();
  installMatchMedia(false);
});

describe('graph panel', () => {
  it('renders typed nodes, directed labeled edges, controls, and safe metadata', async () => {
    renderGraphPanel(graphReady());
    const graph = await screen.findByRole('group', {
      name: 'Candidate, jobs and skills network',
    });
    expect(graph).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-graph-node-candidate:cand-1'),
    ).toHaveTextContent('Candidate');
    expect(within(graph).getByText('HAS_SKILL')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Fit view'})).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: 'Reset layout'}),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByTestId('jobagent-graph-node-candidate:cand-1'),
    );
    expect(
      screen.getByTestId('jobagent-graph-selected-metadata'),
    ).toHaveTextContent('cand-1');
  });

  it('selects a node and exposes safe metadata when it receives focus', async () => {
    renderGraphPanel(graphReady());
    const candidate = await screen.findByTestId(
      'jobagent-graph-node-candidate:cand-1',
    );

    fireEvent.focus(candidate);

    expect(candidate).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.getByTestId('jobagent-graph-selected-metadata'),
    ).toHaveTextContent('cand-1');
  });

  it('offsets parallel relationships and positions constrained labels outside nodes', async () => {
    installMatchMedia(true);
    const snapshot = graphReady();
    snapshot.candidate = null;
    snapshot.jobs = [
      {
        id: 'job-1',
        title: 'Principal Distributed Systems Engineer',
        company: 'Acme',
        revision: 'j1',
      },
    ];
    snapshot.edges = [
      {source_id: 'job-1', target_id: 'python', type: 'REQUIRES'},
      {source_id: 'job-1', target_id: 'python', type: 'PREFERS'},
    ];
    renderGraphPanel(snapshot);
    const graph = await screen.findByRole('group', {
      name: 'Candidate, jobs and skills network',
    });

    await waitFor(() => {
      const lines = [...graph.querySelectorAll('.jobagent-graph-edge')];
      const geometries = lines.map((line) =>
        ['x1', 'y1', 'x2', 'y2']
          .map((attribute) => line.getAttribute(attribute))
          .join(':'),
      );
      expect(lines).toHaveLength(2);
      expect(new Set(geometries).size).toBe(2);
    });
    const labelTransforms = [
      ...graph.querySelectorAll('.jobagent-graph-edge-label'),
    ].map((label) => label.getAttribute('transform'));
    expect(new Set(labelTransforms).size).toBe(2);

    const jobLabel = screen
      .getByTestId('jobagent-graph-node-job:job-1')
      .querySelector('text');
    expect(jobLabel).toHaveClass('jobagent-graph-node-label');
    expect(Number(jobLabel?.getAttribute('y'))).toBeGreaterThan(24);
    expect(jobLabel?.textContent?.length).toBeLessThanOrEqual(18);
  });

  it('keeps a readable semantic list and stale warning', async () => {
    const snapshot = graphReady();
    snapshot.status = 'stale';
    renderGraphPanel(snapshot);
    expect(
      await screen.findByTestId('jobagent-obs-graph-status-stale'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByText('Graph data'));
    expect(screen.getByText(/cand-1.*HAS_SKILL.*python/)).toBeInTheDocument();
  });

  it('uses the shared refreshing header and disables cached refresh', () => {
    const {onRefresh} = renderGraphPanel(graphReady(), {phase: 'loading'});
    const refresh = screen.getByTestId('jobagent-obs-graph-refresh');

    expect(refresh).toHaveAccessibleName('Refresh Neo4j graph');
    expect(refresh).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(refresh);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});
