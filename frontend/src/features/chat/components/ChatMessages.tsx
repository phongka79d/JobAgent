/**
 * Chronological chat message list using public Astryx Chat APIs.
 * List/notices owner; per-row tools/approval/job cards live in ChatMessageRow.
 */

import {
  ChatMessageList,
  ChatSystemMessage,
} from '@astryxdesign/core/Chat';

import type {CompactMatchResult} from '../../jobs/matchResult';
import type {ProfileApprovalAction} from '../../profile/ApprovalCard';
import type {
  ClientMessage,
  StreamErrorInfo,
  StreamPhase,
} from '../reducer';
import {
  ChatMessageRow,
  profileCommitForRow,
  sourceMessageIdForAssistantDisplay,
  toolsForAssistantDisplay,
} from './ChatMessageRow';
import type {RecoveryEntry} from '../useSavedJobRecovery';

export type ChatMessagesProps = {
  messages: readonly ClientMessage[];
  streamPhase: StreamPhase;
  streamError: StreamErrorInfo | null;
  assistantStatus: string | null;
  /** When set, list offers load-older via scroll-to-top. */
  onLoadOlder?: () => Promise<void>;
  isStreaming: boolean;
  /** First accepted approval action for a run (buttons stay disabled). */
  onApprovalAction?: (runId: string, action: ProfileApprovalAction) => void;
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

/**
 * Status notices for stream lifecycle — never false-complete a run.
 */
function StreamNotices({
  streamPhase,
  streamError,
  assistantStatus,
}: {
  streamPhase: StreamPhase;
  streamError: StreamErrorInfo | null;
  assistantStatus: string | null;
}) {
  const notices: {key: string; text: string}[] = [];

  if (assistantStatus) {
    notices.push({key: 'assistant-status', text: assistantStatus});
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
  assistantStatus,
  onLoadOlder,
  isStreaming,
  onApprovalAction,
  approvalLockedRunIds,
  getRecoveryEntry,
  isRecoveryPending,
  onSaveAndEvaluate,
}: ChatMessagesProps) {
  return (
    <ChatMessageList
      density="balanced"
      isStreaming={isStreaming}
      scrollToTopAction={onLoadOlder}
    >
      {messages.map((message, index) => {
        const profileCommit = profileCommitForRow(messages, index);
        const locked = profileCommit
          ? isApprovalLocked(profileCommit.run.id, approvalLockedRunIds)
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
            sourceMessageId={sourceMessageId}
            profileCommit={profileCommit}
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
      <StreamNotices
        streamPhase={streamPhase}
        streamError={streamError}
        assistantStatus={assistantStatus}
      />
    </ChatMessageList>
  );
}
