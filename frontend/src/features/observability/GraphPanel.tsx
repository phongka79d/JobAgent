/**
 * Neo4j graph inspector — React/CSS semantic list fallback with truncation data.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Spinner} from '@astryxdesign/core/Spinner';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import type {CachedResource} from './state';
import type {GraphSnapshot} from './types';

export type GraphPanelProps = {
  resource: CachedResource<GraphSnapshot>;
  onRefresh: () => void;
};

function statusBanner(snapshot: GraphSnapshot) {
  if (snapshot.status === 'ready') {
    return null;
  }
  const title =
    snapshot.status === 'stale' ? 'Graph is stale' : 'Graph unavailable';
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
      title={title}
      description={description}
      container="card"
      data-testid={`jobagent-obs-graph-status-${snapshot.status}`}
    />
  );
}

export function GraphPanel({resource, onRefresh}: GraphPanelProps) {
  const snapshot = resource.data;

  return (
    <div
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-graph"
      role="tabpanel"
      id="jobagent-obs-panel-graph"
      aria-labelledby="jobagent-obs-tab-graph"
    >
      <HStack gap={2} hAlign="between" vAlign="center">
        <Text type="label">Neo4j graph</Text>
        <Button
          label="Refresh"
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          data-testid="jobagent-obs-graph-refresh"
        />
      </HStack>

      {resource.phase === 'loading' && !snapshot ? (
        <HStack gap={2} vAlign="center" data-testid="jobagent-obs-graph-loading">
          <Spinner size="sm" />
          <Text type="body" color="secondary">
            Loading graph snapshot…
          </Text>
        </HStack>
      ) : null}

      {resource.phase === 'error' && resource.error ? (
        <Banner
          status="error"
          title="Graph request failed"
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
          <Text type="supporting" color="secondary" data-testid="jobagent-obs-graph-meta">
            status={snapshot.status}
            {snapshot.nodes_truncated
              ? ` · nodes truncated (+${snapshot.omitted_node_count})`
              : ''}
            {snapshot.edges_truncated
              ? ` · edges truncated (+${snapshot.omitted_edge_count})`
              : ''}
          </Text>
          {statusBanner(snapshot)}

          {snapshot.candidate ? (
            <div className="jobagent-obs-row" data-testid="jobagent-obs-graph-candidate">
              <Text type="label">Candidate</Text>
              <Text type="body" className="jobagent-obs-meta">
                {snapshot.candidate.id}
              </Text>
              <Text type="supporting" color="secondary">
                revision {snapshot.candidate.revision}
              </Text>
            </div>
          ) : null}

          <section aria-label="Jobs">
            <Text type="label">Jobs ({snapshot.jobs.length})</Text>
            {snapshot.jobs.length === 0 ? (
              <EmptyState title="No jobs in snapshot" isCompact />
            ) : (
              <ul className="jobagent-obs-graph-list" data-testid="jobagent-obs-graph-jobs">
                {snapshot.jobs.map((job) => (
                  <li key={job.id}>
                    <Text type="body" className="jobagent-obs-meta">
                      {job.title || job.id}
                      {job.company ? ` · ${job.company}` : ''}
                    </Text>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Skills">
            <Text type="label">Skills ({snapshot.skills.length})</Text>
            {snapshot.skills.length === 0 ? (
              <EmptyState title="No skills in snapshot" isCompact />
            ) : (
              <ul className="jobagent-obs-graph-list" data-testid="jobagent-obs-graph-skills">
                {snapshot.skills.map((skill) => (
                  <li key={skill.canonical_name}>
                    <Text type="body" className="jobagent-obs-meta">
                      {skill.canonical_name}
                    </Text>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Relationships">
            <Text type="label">Relationships ({snapshot.edges.length})</Text>
            {snapshot.edges.length === 0 ? (
              <EmptyState title="No relationships in snapshot" isCompact />
            ) : (
              <ul className="jobagent-obs-graph-list" data-testid="jobagent-obs-graph-edges">
                {snapshot.edges.map((edge, index) => (
                  <li key={`${edge.type}-${edge.source_id}-${edge.target_id}-${index}`}>
                    <Text type="body" className="jobagent-obs-meta">
                      {edge.source_id} —{edge.type}→ {edge.target_id}
                    </Text>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </VStack>
      ) : null}
    </div>
  );
}
