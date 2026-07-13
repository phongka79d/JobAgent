/**
 * Chronological chat message list using public Astryx Chat APIs.
 * Tool activity is concise; profile_commit interrupts render ApprovalCard.
 */

import {
  ChatMessage,
  ChatMessageBubble,
  ChatMessageList,
  ChatSystemMessage,
} from '@astryxdesign/core/Chat';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

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
  StreamErrorInfo,
  StreamPhase,
} from '../reducer';
import {ChatToolActivity} from './ChatToolActivity';

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
};

function senderOf(
  role: ClientMessage['role'],
): 'user' | 'assistant' | 'system' {
  if (role === 'user' || role === 'assistant' || role === 'system') {
    return role;
  }
  return 'system';
}

/**
 * Tools for ChatToolCalls on an assistant row (presentation only).
 *
 * Stream-shaped client state keeps tools on the assistant run. Durable history
 * attaches tool_executions only to the initiating user message with
 * assistant.run null — project those preceding user-run tools onto the
 * assistant message so activity stays in assistant context.
 */
function toolsForAssistantDisplay(
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
  for (let i = index - 1; i >= 0; i -= 1) {
    const prev = messages[i];
    if (prev.role === 'user') {
      return prev.run?.tools ?? [];
    }
    if (prev.role === 'assistant') {
      return [];
    }
  }
  return [];
}

/**
 * Resolve the interrupted profile_commit run for a row.
 * Stream path: assistant.run. History path: preceding user.run.
 */
function profileCommitForRow(
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
    // Prefer assistant row for stream-shaped state; for user rows only when
    // there is no following assistant to host the card.
    if (message.role === 'assistant') {
      return own;
    }
    if (message.role === 'user') {
      const next = messages[index + 1];
      if (next?.role === 'assistant') {
        // Defer to assistant row projection below.
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

function MessageRow({
  message,
  tools,
  profileCommit,
  onApprovalAction,
  approvalLocked,
}: {
  message: ClientMessage;
  tools: readonly ClientToolActivity[];
  profileCommit: {run: ClientRun; pending: JsonObject} | null;
  onApprovalAction?: ChatMessagesProps['onApprovalAction'];
  approvalLocked: boolean;
}) {
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

  // Generic interrupt notice only when not rendering a profile approval card
  // on this row (and not an assistant that hosts a projected user interrupt).
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
        return (
          <MessageRow
            key={message.clientKey}
            message={message}
            tools={toolsForAssistantDisplay(messages, index)}
            profileCommit={profileCommit}
            onApprovalAction={onApprovalAction}
            approvalLocked={locked}
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
