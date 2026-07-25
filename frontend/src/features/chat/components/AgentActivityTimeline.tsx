import {Collapsible} from '@astryxdesign/core/Collapsible';
import {HStack} from '@astryxdesign/core/HStack';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {
  ClientAgentActivity,
  ClientRun,
  StreamPhase,
} from '../reducer';
import './agent-activity.css';

const ACTIVITY_VARIANT = {
  pending: 'neutral',
  running: 'accent',
  completed: 'success',
  failed: 'error',
} as const;

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

export function AgentActivityTimeline({
  run,
  streamPhase,
}: {
  run: ClientRun;
  streamPhase: StreamPhase;
}) {
  const summary = runSummary(run, streamPhase);
  const isRunning = run.state === 'running' && streamPhase !== 'disconnected';
  const trigger = (
    <VStack gap={0} width="100%">
      <HStack gap={1} align="center">
        <StatusDot
          variant={
            streamPhase === 'disconnected'
              ? 'warning'
              : run.state === 'failed'
                ? 'error'
                : run.state === 'completed'
                  ? 'success'
                  : run.state === 'interrupted'
                    ? 'warning'
                    : 'accent'
          }
          label={summary}
          isPulsing={isRunning}
        />
        <Text
          type="label"
          as="span"
          aria-live="polite"
          aria-atomic="true"
          className="jobagent-agent-activity-label"
          data-running={isRunning ? 'true' : 'false'}
        >
          {summary}
        </Text>
      </HStack>
      {run.activities.length > 0 ? (
        <Text type="supporting" color="secondary" as="span">
          {run.state === 'running'
            ? `View activity · ${countLabel(run.activities.length)}`
            : 'View activity'}
        </Text>
      ) : null}
    </VStack>
  );

  if (run.activities.length === 0) {
    return trigger;
  }

  return (
    <Collapsible trigger={trigger} defaultIsOpen={false}>
      <VStack gap={1} width="100%" data-testid="jobagent-agent-activity-list">
        {run.activities.map((activity) => (
          <HStack key={activity.activityId} gap={2} vAlign="start">
            <StatusDot
              variant={ACTIVITY_VARIANT[activity.state]}
              label={activity.state}
              isPulsing={activity.state === 'running' && isRunning}
            />
            <VStack gap={0} width="100%">
              <Text type="body">{activity.label}</Text>
              <Text type="supporting" color="secondary">
                {activityDetail(activity)}
              </Text>
            </VStack>
          </HStack>
        ))}
      </VStack>
    </Collapsible>
  );
}
