/**
 * Agent run history — terminal status and structured tool details only.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Spinner} from '@astryxdesign/core/Spinner';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import type {CachedResource} from './state';
import type {RunHistoryPage} from './types';

export type RunHistoryPanelProps = {
  resource: CachedResource<RunHistoryPage>;
  expandedRunId: string | null;
  onToggleRun: (runId: string) => void;
  onRefresh: () => void;
};

export function RunHistoryPanel({
  resource,
  expandedRunId,
  onToggleRun,
  onRefresh,
}: RunHistoryPanelProps) {
  const items = resource.data?.items ?? [];

  return (
    <div
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-runs"
      role="tabpanel"
      id="jobagent-obs-panel-runs"
      aria-labelledby="jobagent-obs-tab-runs"
    >
      <HStack gap={2} hAlign="between" vAlign="center">
        <Text type="label">Agent runs</Text>
        <Button
          label="Refresh"
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          data-testid="jobagent-obs-runs-refresh"
        />
      </HStack>

      {resource.phase === 'loading' && !resource.data ? (
        <HStack gap={2} vAlign="center" data-testid="jobagent-obs-runs-loading">
          <Spinner size="sm" />
          <Text type="body" color="secondary">
            Loading runs…
          </Text>
        </HStack>
      ) : null}

      {resource.phase === 'error' && resource.error ? (
        <Banner
          status="error"
          title="Run history unavailable"
          description={`${resource.error.summary} (${resource.error.code})`}
          container="card"
          data-testid="jobagent-obs-runs-error"
        />
      ) : null}

      {resource.phase === 'empty' ||
      (resource.loaded && items.length === 0 && resource.phase !== 'error') ? (
        <EmptyState
          title="No agent runs yet"
          description="Completed and interrupted runs appear here."
          isCompact
          data-testid="jobagent-obs-runs-empty"
        />
      ) : null}

      {items.length > 0 ? (
        <VStack gap={2} width="100%">
          {items.map((run) => {
            const expanded = expandedRunId === run.id;
            return (
              <div
                key={run.id}
                className="jobagent-obs-row"
                data-testid={`jobagent-obs-run-${run.id}`}
              >
                <Text type="body" className="jobagent-obs-meta">
                  Run {run.id.slice(0, 8)}…
                </Text>
                <Text type="supporting" color="secondary" className="jobagent-obs-meta">
                  {run.state}
                  {run.error_code ? ` · ${run.error_code}` : ''}
                  {' · '}
                  {run.created_at}
                </Text>
                <Button
                  label={expanded ? 'Hide details' : 'Show details'}
                  variant="secondary"
                  size="sm"
                  onClick={() => onToggleRun(run.id)}
                  data-testid={`jobagent-obs-run-toggle-${run.id}`}
                />
                {expanded ? (
                  <VStack gap={1} width="100%" data-testid={`jobagent-obs-run-detail-${run.id}`}>
                    {run.tool_executions.length === 0 ? (
                      <Text type="supporting" color="secondary">
                        No tool executions
                      </Text>
                    ) : (
                      run.tool_executions.map((tool) => (
                        <div key={tool.id} className="jobagent-obs-meta">
                          <Text type="body">
                            {tool.tool_name} · {tool.status}
                            {tool.duration_ms != null
                              ? ` · ${tool.duration_ms}ms`
                              : ''}
                          </Text>
                          {tool.summary ? (
                            <Text type="supporting" color="secondary">
                              {tool.summary}
                            </Text>
                          ) : null}
                          {tool.error_code ? (
                            <Text type="supporting" color="secondary">
                              {tool.error_code}
                            </Text>
                          ) : null}
                        </div>
                      ))
                    )}
                  </VStack>
                ) : null}
              </div>
            );
          })}
        </VStack>
      ) : null}
    </div>
  );
}
