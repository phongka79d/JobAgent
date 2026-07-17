/**
 * Agent run history - terminal status and structured tool details only.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {ObservabilityListSkeleton} from './ObservabilityListSkeleton';
import {ObservabilityPanelHeader} from './ObservabilityPanelHeader';
import {
  formatDurationMs,
  formatObservabilityDateTime,
  formatRunDuration,
} from './observabilityFormat';
import type {CachedResource} from './state';
import type {RunHistoryPage} from './types';

const RUN_VARIANT = {
  running: 'accent',
  interrupted: 'warning',
  completed: 'success',
  failed: 'error',
} as const;

const RUN_LABEL = {
  running: 'Running',
  interrupted: 'Interrupted',
  completed: 'Completed',
  failed: 'Failed',
} as const;

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
  const selectedRun = items.find((run) => run.id === expandedRunId) ?? null;

  return (
    <VStack
      gap={2}
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-runs"
      role="tabpanel"
      id="jobagent-obs-panel-runs"
      aria-labelledby="jobagent-obs-tab-runs"
    >
      <ObservabilityPanelHeader
        eyebrow="Execution history"
        title="Agent runs"
        onRefresh={onRefresh}
        isRefreshing={resource.phase === 'loading' && Boolean(resource.data)}
        refreshTestId="jobagent-obs-runs-refresh"
      />

      {resource.phase === 'loading' && !resource.data ? (
        <ObservabilityListSkeleton
          rows={3}
          testId="jobagent-obs-runs-loading"
        />
      ) : null}

      {resource.phase === 'error' && resource.error ? (
        <Banner
          status="error"
          title="Run history unavailable"
          description={`${resource.error.summary} (${resource.error.code})`}
          container="section"
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
        <List density="compact" hasDividers header="Agent runs">
          {items.map((run) => {
            const duration = formatRunDuration(
              run.created_at,
              run.completed_at,
            );
            const toolCount = run.tool_executions.length;
            const description = [
              RUN_LABEL[run.state],
              formatObservabilityDateTime(run.created_at),
              `${toolCount} ${toolCount === 1 ? 'tool' : 'tools'}`,
              run.error_code,
              duration,
            ]
              .filter(Boolean)
              .join(' · ');

            return (
              <ListItem
                key={run.id}
                label={`Run ${run.id}`}
                description={
                  <Text
                    type="supporting"
                    color="secondary"
                    className="jobagent-obs-meta"
                  >
                    {description}
                  </Text>
                }
                startContent={
                  <StatusDot
                    variant={RUN_VARIANT[run.state]}
                    label={RUN_LABEL[run.state]}
                  />
                }
                isSelected={run.id === expandedRunId}
                onClick={() => onToggleRun(run.id)}
                data-testid={`jobagent-obs-run-toggle-${run.id}`}
              />
            );
          })}
        </List>
      ) : null}

      {selectedRun ? (
        <VStack
          gap={2}
          className="jobagent-obs-detail"
          data-testid={`jobagent-obs-run-detail-${selectedRun.id}`}
        >
          <MetadataList
            columns="single"
            label={{position: 'top'}}
            title="Selected run"
          >
            <MetadataListItem label="Run ID">{selectedRun.id}</MetadataListItem>
            <MetadataListItem label="User message ID">
              {selectedRun.user_message_id}
            </MetadataListItem>
            <MetadataListItem label="Created">
              {formatObservabilityDateTime(selectedRun.created_at)}
            </MetadataListItem>
            <MetadataListItem label="Completed">
              {selectedRun.completed_at
                ? formatObservabilityDateTime(selectedRun.completed_at)
                : 'Not completed'}
            </MetadataListItem>
            <MetadataListItem label="Related attachments">
              {selectedRun.related_attachment_ids.length}
            </MetadataListItem>
            <MetadataListItem label="Related jobs">
              {selectedRun.related_job_ids.length}
            </MetadataListItem>
          </MetadataList>

          <Text type="label">Tool timeline</Text>
          {selectedRun.tool_executions.length === 0 ? (
            <Text type="supporting" color="secondary">
              No tool executions
            </Text>
          ) : (
            <VStack gap={2} width="100%">
              {selectedRun.tool_executions.map((tool) => (
                <HStack
                  key={tool.id}
                  gap={2}
                  vAlign="start"
                  className="jobagent-obs-tool-timeline"
                >
                  <StatusDot
                    variant={
                      tool.status === 'pending'
                        ? 'neutral'
                        : RUN_VARIANT[tool.status]
                    }
                    label={tool.status}
                  />
                  <VStack gap={0.5} width="100%">
                    <Text type="body">{tool.tool_name}</Text>
                    <Text type="supporting" color="secondary">
                      {tool.status}
                      {tool.duration_ms == null
                        ? ''
                        : ` · ${formatDurationMs(tool.duration_ms)}`}
                    </Text>
                    {tool.summary ? (
                      <Text type="supporting">{tool.summary}</Text>
                    ) : null}
                    {tool.error_code ? (
                      <Text type="supporting">{tool.error_code}</Text>
                    ) : null}
                  </VStack>
                </HStack>
              ))}
            </VStack>
          )}
        </VStack>
      ) : null}
    </VStack>
  );
}
