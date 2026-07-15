/**
 * Per-message row owner: tools, approval card, saved-job, and match cards.
 * ChatMessages remains responsible for list/notices only.
 */

import {
  ChatMessage,
  ChatMessageBubble,
  ChatSystemMessage,
} from '@astryxdesign/core/Chat';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {MatchCard} from '../../jobs/MatchCard';
import {
  isMatchJobsToolName,
  parseMatchJobsResultData,
  type CompactMatchJobsResult,
} from '../../jobs/matchResult';
import {SavedJobCard} from '../../jobs/SavedJobCard';
import {
  isSaveJobToolName,
  parseSaveJobResultData,
} from '../../jobs/types';
import {
  ApprovalCard,
  parseProfileCommitProjection,
  type ProfileApprovalAction,
} from '../../profile/ApprovalCard';
import type {JsonObject} from '../types';
import type {
  ClientMessage,
  ClientRun,
  ClientToolActivity,
} from '../reducer';
import {ChatToolActivity} from './ChatToolActivity';

export type ChatMessageRowProps = {
  message: ClientMessage;
  tools: readonly ClientToolActivity[];
  profileCommit: {run: ClientRun; pending: JsonObject} | null;
  onApprovalAction?: (runId: string, action: ProfileApprovalAction) => void;
  approvalLocked: boolean;
};

/**
 * Tools for ChatToolCalls on an assistant row (presentation only).
 *
 * Stream-shaped client state keeps tools on the assistant run. Durable history
 * attaches tool_executions only to the initiating user message with
 * assistant.run null — project those preceding user-run tools onto the
 * assistant message so activity stays in assistant context.
 *
 * Canonical host selection: if another assistant already owns the same durable
 * run or tool-execution identities, do not project a second host (exact-one card).
 */
export function toolsForAssistantDisplay(
  messages: readonly ClientMessage[],
  index: number,
): readonly ClientToolActivity[] {
  const message = messages[index];
  if (!message || message.role !== 'assistant') {
    return [];
  }
  const ownTools = message.run?.tools ?? [];
  if (ownTools.length > 0) {
    return ownTools;
  }

  let projected: readonly ClientToolActivity[] = [];
  let projectedRunId: string | null = null;
  for (let i = index - 1; i >= 0; i -= 1) {
    const prev = messages[i];
    if (prev.role === 'user') {
      projected = prev.run?.tools ?? [];
      projectedRunId = prev.run?.id ?? null;
      break;
    }
    if (prev.role === 'assistant') {
      return [];
    }
  }
  if (projected.length === 0) {
    return [];
  }

  const projectedExecIds = new Set(
    projected.map((t) => t.toolExecutionId),
  );
  for (let i = 0; i < messages.length; i += 1) {
    if (i === index) {
      continue;
    }
    const other = messages[i];
    if (other.role !== 'assistant') {
      continue;
    }
    const otherTools = other.run?.tools ?? [];
    if (otherTools.length === 0) {
      continue;
    }
    if (projectedRunId !== null && other.run?.id === projectedRunId) {
      // Another assistant already hosts this durable run's tools.
      return [];
    }
    if (otherTools.some((t) => projectedExecIds.has(t.toolExecutionId))) {
      // Same durable tool execution already rendered on another assistant.
      return [];
    }
  }
  return projected;
}

/**
 * Resolve the interrupted profile_commit run for a row.
 * Stream path: assistant.run. History path: preceding user.run.
 */
export function profileCommitForRow(
  messages: readonly ClientMessage[],
  index: number,
): {run: ClientRun; pending: JsonObject} | null {
  const message = messages[index];
  if (!message) {
    return null;
  }

  const tryRun = (run: ClientRun | null | undefined) => {
    if (!run || run.state !== 'interrupted' || !run.pendingApproval) {
      return null;
    }
    const parsed = parseProfileCommitProjection(run.pendingApproval);
    if (!parsed) {
      return null;
    }
    return {run, pending: run.pendingApproval};
  };

  const own = tryRun(message.run);
  if (own) {
    if (message.role === 'assistant') {
      return own;
    }
    if (message.role === 'user') {
      const next = messages[index + 1];
      if (next?.role === 'assistant') {
        return null;
      }
      return own;
    }
  }

  if (message.role === 'assistant') {
    for (let i = index - 1; i >= 0; i -= 1) {
      const prev = messages[i];
      if (prev.role === 'user') {
        return tryRun(prev.run);
      }
      if (prev.role === 'assistant') {
        return null;
      }
    }
  }
  return null;
}

/**
 * First durable save_job tool with a strict compact projection for this row.
 * query_jobs stays tool-activity only (no ranking card).
 */
export function saveJobResultForTools(
  tools: readonly ClientToolActivity[],
): {
  data: NonNullable<ReturnType<typeof parseSaveJobResultData>>;
  summary: string | null;
  errorCode: string | null;
} | null {
  for (const tool of tools) {
    if (!isSaveJobToolName(tool.toolName)) {
      continue;
    }
    const parsed = parseSaveJobResultData(tool.resultData);
    if (!parsed) {
      continue;
    }
    return {
      data: parsed,
      summary: tool.summary,
      errorCode: tool.errorCode ?? parsed.failureCode,
    };
  }
  return null;
}

/**
 * First durable match_jobs tool with a strict compact projection for this row.
 * Preserves backend result order; at most 10 cards (parser-enforced).
 */
export function matchJobsResultForTools(
  tools: readonly ClientToolActivity[],
): CompactMatchJobsResult | null {
  for (const tool of tools) {
    if (!isMatchJobsToolName(tool.toolName)) {
      continue;
    }
    const parsed = parseMatchJobsResultData(tool.resultData);
    if (!parsed) {
      continue;
    }
    return parsed;
  }
  return null;
}

function senderOf(
  role: ClientMessage['role'],
): 'user' | 'assistant' | 'system' {
  if (role === 'user' || role === 'assistant' || role === 'system') {
    return role;
  }
  return 'system';
}

export function ChatMessageRow({
  message,
  tools,
  profileCommit,
  onApprovalAction,
  approvalLocked,
}: ChatMessageRowProps) {
  if (message.role === 'system') {
    return (
      <ChatSystemMessage key={message.clientKey}>
        {message.content}
      </ChatSystemMessage>
    );
  }

  const runState = message.run?.state;
  const showTools = message.role === 'assistant' && tools.length > 0;
  const parsed = profileCommit
    ? parseProfileCommitProjection(profileCommit.pending)
    : null;
  const showApprovalCard =
    parsed !== null &&
    profileCommit !== null &&
    (message.role === 'assistant' || message.role === 'user');

  const savedJob =
    message.role === 'assistant' ? saveJobResultForTools(tools) : null;
  const matchJobs =
    message.role === 'assistant' ? matchJobsResultForTools(tools) : null;

  const showGenericInterrupted =
    runState === 'interrupted' && !showApprovalCard && parsed === null;

  return (
    <ChatMessage key={message.clientKey} sender={senderOf(message.role)}>
      <VStack gap={1}>
        {showTools ? <ChatToolActivity tools={tools} /> : null}
        {message.content !== '' || message.isStreaming ? (
          <ChatMessageBubble
            variant={message.role === 'assistant' ? 'ghost' : 'filled'}
          >
            {message.content === '' && message.isStreaming
              ? '…'
              : message.content}
          </ChatMessageBubble>
        ) : null}
        {savedJob ? (
          <SavedJobCard
            data={savedJob.data}
            summary={savedJob.summary}
            errorCode={savedJob.errorCode}
          />
        ) : null}
        {matchJobs
          ? matchJobs.results.map((result) => (
              <MatchCard key={result.jobId} data={result} />
            ))
          : null}
        {showApprovalCard && parsed && profileCommit ? (
          <ApprovalCard
            card={parsed.card}
            allowedActions={parsed.allowedActions}
            isDisabled={approvalLocked}
            runId={profileCommit.run.id}
            onAction={(action) => {
              onApprovalAction?.(profileCommit.run.id, action);
            }}
          />
        ) : null}
        {showGenericInterrupted ? (
          <Text type="supporting" color="secondary" as="p">
            Run interrupted
          </Text>
        ) : null}
        {runState === 'failed' && message.run?.errorCode ? (
          <Text type="supporting" color="secondary" as="p">
            Run failed ({message.run.errorCode})
          </Text>
        ) : null}
      </VStack>
    </ChatMessage>
  );
}
