import {Banner} from '@astryxdesign/core/Banner';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Skeleton} from '@astryxdesign/core/Skeleton';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {useMemo} from 'react';

import {GraphCanvas} from './GraphCanvas';
import {toGraphModel} from './graphPresentation';
import {GraphSemanticList} from './GraphSemanticList';
import {GraphVisualizationBoundary} from './GraphVisualizationBoundary';
import {ObservabilityPanelHeader} from './ObservabilityPanelHeader';
import {formatObservabilityDateTime} from './observabilityFormat';
import type {CachedResource} from './state';
import type {GraphSnapshot} from './types';

export type GraphPanelProps = {
  resource: CachedResource<GraphSnapshot>;
  onRefresh: () => void;
};

function statusBanner(snapshot: GraphSnapshot) {
  if (snapshot.status === 'ready') return null;
  const description = [
    snapshot.summary,
    snapshot.code ? `(${snapshot.code})` : null,
    snapshot.rebuild_instruction,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Banner
      status={snapshot.status === 'stale' ? 'warning' : 'error'}
      title={snapshot.status === 'stale' ? 'Graph is stale' : 'Graph unavailable'}
      description={description}
      container="card"
      data-testid={`jobagent-obs-graph-status-${snapshot.status}`}
    />
  );
}

function GraphLoadingSkeleton() {
  return (
    <VStack gap={2} width="100%" data-testid="jobagent-obs-graph-loading">
      <Skeleton width="55%" height="var(--spacing-3)" radius={1} />
      <Skeleton width="75%" height="var(--spacing-2)" radius={1} index={1} />
      <section className="jobagent-graph-skeleton-canvas">
        <Skeleton width="100%" height="100%" radius={4} index={2} />
      </section>
    </VStack>
  );
}

export function GraphPanel({resource, onRefresh}: GraphPanelProps) {
  const snapshot = resource.data;
  const nodeCount = snapshot
    ? (snapshot.candidate ? 1 : 0) + snapshot.jobs.length + snapshot.skills.length
    : 0;
  const canRenderGraph =
    snapshot !== null &&
    (snapshot.status === 'ready' || snapshot.status === 'stale') &&
    nodeCount > 0;
  const model = useMemo(
    () => (canRenderGraph && snapshot ? toGraphModel(snapshot) : null),
    [canRenderGraph, snapshot],
  );

  return (
    <div
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-graph"
      role="tabpanel"
      id="jobagent-obs-panel-graph"
      aria-labelledby="jobagent-obs-tab-graph"
    >
      <ObservabilityPanelHeader
        eyebrow="Graph projection"
        title="Neo4j graph"
        onRefresh={onRefresh}
        isRefreshing={resource.phase === 'loading'}
        refreshTestId="jobagent-obs-graph-refresh"
      />

      {resource.phase === 'loading' && !snapshot ? (
        <GraphLoadingSkeleton />
      ) : null}

      {resource.phase === 'error' && resource.error ? (
        <Banner
          status="error"
          title={snapshot ? 'Graph refresh failed' : 'Graph request failed'}
          description={`${resource.error.summary} (${resource.error.code})`}
          container="card"
          data-testid="jobagent-obs-graph-error"
        />
      ) : null}

      {snapshot ? (
        <VStack gap={2} width="100%">
          <Text type="body" data-testid="jobagent-obs-graph-summary">
            {snapshot.summary}
          </Text>
          <Text
            type="supporting"
            color="secondary"
            data-testid="jobagent-obs-graph-meta"
          >
            {nodeCount} nodes · {snapshot.edges.length} relationships · checked{' '}
            {formatObservabilityDateTime(snapshot.checked_at)}
            {snapshot.nodes_truncated
              ? ` · nodes truncated (+${snapshot.omitted_node_count})`
              : ''}
            {snapshot.edges_truncated
              ? ` · edges truncated (+${snapshot.omitted_edge_count})`
              : ''}
          </Text>

          {statusBanner(snapshot)}

          {model ? (
            <GraphVisualizationBoundary
              key={model.identity}
              resetKey={snapshot}
            >
              <GraphCanvas model={model} />
            </GraphVisualizationBoundary>
          ) : null}

          {snapshot.status !== 'unavailable' && nodeCount === 0 ? (
            <EmptyState
              title="No graph nodes available"
              description="The current projection has no candidate, job, or skill nodes."
              isCompact
            />
          ) : null}

          <GraphSemanticList snapshot={snapshot} />
        </VStack>
      ) : null}
    </div>
  );
}
