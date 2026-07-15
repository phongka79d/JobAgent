/**
 * Concise tool activity for assistant messages (Plan 3 §7.9 / Master §15.4).
 *
 * Application/client state uses exact JobAgent tool statuses only:
 *   pending | running | completed | failed
 *
 * Astryx ChatToolCalls optional visual `status` prop uses a different vocabulary:
 *   pending | running | complete | error
 * Mapping to that prop happens only at this presentation boundary and never
 * enters reducer/API/application state. Exact JobAgent status text is always
 * rendered as visible text via `stats` so users see completed/failed, not aliases.
 */

import {
  ChatToolCalls,
  type ChatToolCallItem,
  type ChatToolCallStatus,
} from '@astryxdesign/core/Chat';
import {Text} from '@astryxdesign/core/Text';

import type {ClientToolActivity} from '../reducer';
import type {ToolStatus} from '../types';

/** Explicit friendly labels for production tools (Master §15.4 / Plan 6 §7.9). */
const FRIENDLY_TOOL_LABELS: Readonly<Record<string, string>> = {
  save_job: 'Save Job',
  query_jobs: 'Query Jobs',
  match_jobs: 'Match Jobs',
  propose_profile_from_cv: 'Propose Profile From Cv',
  propose_profile_update: 'Propose Profile Update',
  commit_profile_draft: 'Commit Profile Draft',
};

/** Friendly label: snake/kebab tool names → title-like words. */
export function friendlyToolLabel(toolName: string): string {
  const known = FRIENDLY_TOOL_LABELS[toolName];
  if (known) {
    return known;
  }
  const spaced = toolName.replace(/[_-]+/g, ' ').trim();
  if (spaced === '') {
    return toolName;
  }
  return spaced.replace(/\b\w/g, (ch) => ch.toUpperCase());
}

/** Duration for Astryx `duration` string prop (ms or s). */
export function formatToolDuration(durationMs: number | null): string | undefined {
  if (durationMs === null || durationMs < 0) {
    return undefined;
  }
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  const seconds = durationMs / 1000;
  const rounded =
    durationMs % 1000 === 0 ? String(seconds) : seconds.toFixed(1);
  return `${rounded}s`;
}

/**
 * Presentation-only map: JobAgent exact status → Astryx visual icon status.
 * Do not use the return value as application state.
 */
export function toAstryxVisualToolStatus(
  status: ToolStatus,
): ChatToolCallStatus {
  switch (status) {
    case 'pending':
      return 'pending';
    case 'running':
      return 'running';
    case 'completed':
      // Visual prop only — application state remains `completed`.
      return 'complete';
    case 'failed':
      // Visual prop only — application state remains `failed`.
      return 'error';
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

/** Short outcome only — never raw arguments, documents, or stacks. */
export function shortToolOutcome(tool: ClientToolActivity): string | undefined {
  if (tool.summary && tool.summary.trim() !== '') {
    return tool.summary.trim();
  }
  if (tool.status === 'failed' && tool.errorCode) {
    return tool.errorCode;
  }
  return undefined;
}

function toCallItem(tool: ClientToolActivity): ChatToolCallItem {
  const exactStatus = tool.status;
  const outcome = shortToolOutcome(tool);
  return {
    key: tool.toolExecutionId,
    name: friendlyToolLabel(tool.toolName),
    // Visual icon status only (Astryx vocabulary); not stored in client state.
    status: toAstryxVisualToolStatus(exactStatus),
    duration: formatToolDuration(tool.durationMs),
    // Target holds a short outcome when present (no raw args/documents).
    target: outcome,
    // Exact JobAgent status text — users always see pending|running|completed|failed.
    stats: (
      <Text type="supporting" color="secondary" as="span">
        {exactStatus}
      </Text>
    ),
  };
}

export type ChatToolActivityProps = {
  tools: readonly ClientToolActivity[];
};

/**
 * Renders durable/stream tool activity through public ChatToolCalls.
 * Returns null when there are no tools.
 */
export function ChatToolActivity({tools}: ChatToolActivityProps) {
  if (tools.length === 0) {
    return null;
  }
  const calls = tools.map(toCallItem);
  return <ChatToolCalls calls={calls} defaultIsExpanded />;
}
