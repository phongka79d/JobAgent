/**
 * Chronological chat message list using public Astryx Chat APIs.
 * List/notices owner; per-row tools/approval/job cards live in ChatMessageRow.
 */

import {
  ChatMessageList,
  ChatSystemMessage,
} from '@astryxdesign/core/Chat';

import type {CompactMatchResult} from '../../jobs/matchResult';
import {jobSaveConfirmationForRow} from '../jobSaveConfirmation';
import type {
  ClientMessage,
  ClientRun,
  StreamErrorInfo,
  StreamPhase,
} from '../reducer';
import {
  activityRunForAssistantDisplay,
  ChatMessageRow,
  profileCommitForRow,
  sourceMessageIdForAssistantDisplay,
  toolsForAssistantDisplay,
  type ChatApprovalAction,
} from './ChatMessageRow';
import type {RecoveryEntry} from '../useSavedJobRecovery';

export type ChatMessagesProps = {
  messages: readonly ClientMessage[];
  streamPhase: StreamPhase;
  streamError: StreamErrorInfo | null;
  /** When set, list offers load-older via scroll-to-top. */
  onLoadOlder?: () => Promise<void>;
  isStreaming: boolean;
  /** First accepted approval action for a run (buttons stay disabled). */
  onApprovalAction?: (runId: string, action: ChatApprovalAction) => void;
  /** Run ids whose approval action was already accepted (local lock only). */
  approvalLockedRunIds?: ReadonlySet<string> | readonly string[];
  /** Local recovery lookup by durable source_message_id (not chat reducer). */
  getRecoveryEntry?: (sourceMessageId: string) => RecoveryEntry;
  isRecoveryPending?: (sourceMessageId: string) => boolean;
  onSaveAndEvaluate?: (sourceMessageId: string) => void;
};

function isApprovalLocked(
  runId: string,
  locked: ChatMessagesProps['approvalLockedRunIds'],
): boolean {
  if (!locked) {
    return false;
  }
  if (locked instanceof Set) {
    return locked.has(runId);
  }
  return (locked as readonly string[]).includes(runId);
}

function reloadedRunningActivityHost(
  messages: readonly ClientMessage[],
): {message: ClientMessage; run: ClientRun; sourceMessageId: string} | null {
  const latest = messages.at(-1);
  if (
    !latest ||
    latest.role !== 'user' ||
    latest.run?.state !== 'running'
  ) {
    return null;
  }
  const ownedByAssistant = messages.some(
    (message) =>
      message.role === 'assistant' && message.run?.id === latest.run?.id,
  );
  if (ownedByAssistant) {
    return null;
  }
  const key = `assistant:${latest.run.id}`;
  return {
    message: {
      id: key,
      clientKey: key,
      role: 'assistant',
      content: '',
      createdAt: latest.createdAt,
      run: null,
      isStreaming: false,
    },
    run: latest.run,
    sourceMessageId: latest.id,
  };
}

/**
 * Status notices for stream lifecycle — never false-complete a run.
 */
function StreamNotices({
  streamPhase,
  streamError,
  hasRunBackedAssistant,
}: {
  streamPhase: StreamPhase;
  streamError: StreamErrorInfo | null;
  hasRunBackedAssistant: boolean;
}) {
  const notices: {key: string; text: string}[] = [];

  if (hasRunBackedAssistant) {
    return null;
  }
  if (streamPhase === 'connecting') {
    notices.push({key: 'connecting', text: 'Connecting…'});
  }
  if (streamPhase === 'disconnected') {
    notices.push({
      key: 'disconnected',
      text: 'Stream disconnected — run is not completed',
    });
  }
  if (streamPhase === 'failed' && streamError) {
    notices.push({
      key: 'failed',
      text: `Run failed: ${streamError.summary} (${streamError.code})`,
    });
  } else if (streamPhase === 'failed') {
    notices.push({key: 'failed', text: 'Run failed'});
  }

  if (notices.length === 0) {
    return null;
  }

  return (
    <>
      {notices.map((n) => (
        <ChatSystemMessage key={n.key}>{n.text}</ChatSystemMessage>
      ))}
    </>
  );
}

export function ChatMessages({
  messages,
  streamPhase,
  streamError,
  onLoadOlder,
  isStreaming,
  onApprovalAction,
  approvalLockedRunIds,
  getRecoveryEntry,
  isRecoveryPending,
  onSaveAndEvaluate,
}: ChatMessagesProps) {
  let latestUserIndex = -1;
  messages.forEach((message, index) => {
    if (message.role === 'user') {
      latestUserIndex = index;
    }
  });
  const hasRunBackedAssistant = messages.some(
    (_message, index) =>
      index > latestUserIndex &&
      activityRunForAssistantDisplay(messages, index) !== null,
  );
  const reloadedRunningHost = reloadedRunningActivityHost(messages);
  return (
    <ChatMessageList
      density="balanced"
      isStreaming={isStreaming}
      scrollToTopAction={onLoadOlder}
    >
      {messages.map((message, index) => {
        const activityRun = activityRunForAssistantDisplay(messages, index);
        const profileCommit = profileCommitForRow(messages, index);
        const jobSaveConfirmation = jobSaveConfirmationForRow(
          messages,
          index,
        );
        const interruptRunId =
          profileCommit?.run.id ?? jobSaveConfirmation?.run.id ?? null;
        const locked = interruptRunId
          ? isApprovalLocked(interruptRunId, approvalLockedRunIds)
          : false;
        const sourceMessageId = sourceMessageIdForAssistantDisplay(
          messages,
          index,
        );
        const recovery =
          sourceMessageId && getRecoveryEntry
            ? getRecoveryEntry(sourceMessageId)
            : null;
        const recoveredMatch: CompactMatchResult | null =
          recovery?.recoveredMatch ?? null;
        return (
          <ChatMessageRow
            key={message.clientKey}
            message={message}
            tools={toolsForAssistantDisplay(messages, index)}
            activityRun={activityRun}
            streamPhase={streamPhase}
            sourceMessageId={sourceMessageId}
            profileCommit={profileCommit}
            jobSaveConfirmation={jobSaveConfirmation}
            onApprovalAction={onApprovalAction}
            approvalLocked={locked}
            recoveryPending={
              sourceMessageId
                ? (isRecoveryPending?.(sourceMessageId) ?? false)
                : false
            }
            recoveredMatch={recoveredMatch}
            recoveryFailureHint={recovery?.failureHint ?? null}
            onSaveAndEvaluate={onSaveAndEvaluate}
          />
        );
      })}
      {reloadedRunningHost ? (
        <ChatMessageRow
          key={reloadedRunningHost.message.clientKey}
          message={reloadedRunningHost.message}
          tools={[]}
          activityRun={reloadedRunningHost.run}
          streamPhase="disconnected"
          sourceMessageId={reloadedRunningHost.sourceMessageId}
          profileCommit={null}
          jobSaveConfirmation={null}
          approvalLocked={false}
        />
      ) : null}
      <StreamNotices
        streamPhase={streamPhase}
        streamError={streamError}
        hasRunBackedAssistant={hasRunBackedAssistant}
      />
    </ChatMessageList>
  );
}
