import {useState} from 'react';
import {Card} from '@astryxdesign/core/Card';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Divider} from '@astryxdesign/core/Divider';
import {HStack} from '@astryxdesign/core/HStack';
import {Icon} from '@astryxdesign/core/Icon';
import {Spinner} from '@astryxdesign/core/Spinner';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {
  ClientAgentActivity,
  ClientRun,
  StreamPhase,
} from '../reducer';
import './agent-activity.css';

type MarkerKind = 'clock' | 'error' | 'spinner' | 'success' | 'warning';

function countLabel(count: number): string {
  return `${count} ${count === 1 ? 'step' : 'steps'}`;
}

function latestActivity(
  activities: readonly ClientAgentActivity[],
): ClientAgentActivity | null {
  const running = [...activities]
    .reverse()
    .find((item) => item.state === 'running');
  return running ?? activities.at(-1) ?? null;
}

function runSummary(run: ClientRun, streamPhase: StreamPhase): string {
  const count = countLabel(run.activities.length);
  if (streamPhase === 'disconnected' && run.state === 'running') {
    return 'Connection lost — Agent may still be running';
  }
  if (run.state === 'interrupted') {
    return `Waiting for your confirmation · ${count}`;
  }
  if (run.state === 'completed') {
    return `Completed · ${count}`;
  }
  if (run.state === 'failed') {
    return `Unable to complete · ${count}`;
  }
  return latestActivity(run.activities)?.label ?? 'Connecting…';
}

function formatDuration(durationMs: number | null): string | null {
  if (durationMs === null) {
    return null;
  }
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  const seconds = durationMs / 1000;
  return `${durationMs % 1000 === 0 ? String(seconds) : seconds.toFixed(1)}s`;
}

function activityDetail(activity: ClientAgentActivity): string {
  return [
    activity.technicalName,
    activity.state,
    formatDuration(activity.durationMs),
    activity.errorCode,
  ]
    .filter((value): value is string => Boolean(value))
    .join(' · ');
}

function activityMarkerKind(
  state: ClientAgentActivity['state'],
): MarkerKind {
  if (state === 'completed') {
    return 'success';
  }
  if (state === 'failed') {
    return 'error';
  }
  if (state === 'running') {
    return 'spinner';
  }
  return 'clock';
}

function runMarkerKind(
  run: ClientRun,
  streamPhase: StreamPhase,
  isOpen: boolean,
): MarkerKind {
  if (streamPhase === 'disconnected' && run.state === 'running') {
    return 'warning';
  }
  if (run.state === 'completed') {
    return 'success';
  }
  if (run.state === 'failed') {
    return 'error';
  }
  if (run.state === 'interrupted') {
    return 'warning';
  }
  return isOpen ? 'clock' : 'spinner';
}

function StatusMarker({
  kind,
  label,
  testId,
  clockColor = 'secondary',
}: {
  kind: MarkerKind;
  label: string;
  testId: string;
  clockColor?: 'accent' | 'secondary';
}) {
  return (
    <span
      className="jobagent-agent-activity-marker"
      data-marker={kind}
      data-testid={testId}>
      {kind === 'spinner' ? (
        <Spinner size="sm" aria-label={`Running: ${label}`} />
      ) : (
        <Icon
          icon={kind}
          size="sm"
          color={kind === 'clock' ? clockColor : kind}
        />
      )}
    </span>
  );
}

export function AgentActivityTimeline({
  run,
  streamPhase,
}: {
  run: ClientRun;
  streamPhase: StreamPhase;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const summary = runSummary(run, streamPhase);
  const isRunning = run.state === 'running' && streamPhase !== 'disconnected';
  const hasActivities = run.activities.length > 0;
  const summaryMarker = runMarkerKind(run, streamPhase, isOpen);
  const header = (
    <HStack gap={1} align="center" width="100%">
      <StatusMarker
        kind={summaryMarker}
        label={summary}
        testId="jobagent-agent-activity-summary-marker"
        clockColor="accent"
      />
      <VStack gap={0} width="100%">
        <Text
          type="label"
          as="span"
          aria-live="polite"
          aria-atomic="true"
          aria-label={summary}
          className="jobagent-agent-activity-label"
          data-variant={
            summaryMarker === 'clock' || summaryMarker === 'spinner'
              ? 'accent'
              : summaryMarker
          }
          data-running={isRunning ? 'true' : 'false'}
        >
          {summary}
        </Text>
        {hasActivities ? (
          <Text type="supporting" color="secondary" as="span">
            {run.state === 'running'
              ? `View activity · ${countLabel(run.activities.length)}`
              : 'View activity'}
          </Text>
        ) : null}
      </VStack>
    </HStack>
  );

  return (
    <Card
      width="100%"
      padding={3}
      data-testid="jobagent-agent-activity-card">
      {hasActivities ? (
        <Collapsible
          trigger={header}
          isOpen={isOpen}
          onOpenChange={setIsOpen}
          className="jobagent-agent-activity-disclosure">
          <VStack
            gap={2}
            width="100%"
            data-testid="jobagent-agent-activity-list">
            <Divider />
            <VStack gap={0} width="100%">
              {run.activities.map((activity, index) => {
                const isLast = index === run.activities.length - 1;
                return (
                  <HStack
                    key={activity.activityId}
                    gap={2}
                    vAlign="start"
                    className="jobagent-agent-activity-step"
                    data-testid={`jobagent-agent-activity-row-${activity.activityId}`}
                    data-state={activity.state}
                    data-last={isLast ? 'true' : 'false'}>
                    <StatusMarker
                      kind={
                        activity.state === 'running' && !isOpen
                          ? 'clock'
                          : activityMarkerKind(activity.state)
                      }
                      label={activity.label}
                      testId={`jobagent-agent-activity-marker-${activity.activityId}`}
                    />
                    <VStack gap={0} width="100%">
                      <Text type="body">{activity.label}</Text>
                      <Text type="supporting" color="secondary">
                        {activityDetail(activity)}
                      </Text>
                    </VStack>
                  </HStack>
                );
              })}
            </VStack>
          </VStack>
        </Collapsible>
      ) : (
        header
      )}
    </Card>
  );
}
