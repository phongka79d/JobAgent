/**
 * Chronological chat message list using public Astryx Chat APIs.
 * Tool activity is concise; no approval cards or domain-tool UI.
 */

import {
  ChatMessage,
  ChatMessageBubble,
  ChatMessageList,
  ChatSystemMessage,
} from '@astryxdesign/core/Chat';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {
  ClientMessage,
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

function MessageRow({
  message,
  tools,
}: {
  message: ClientMessage;
  tools: readonly ClientToolActivity[];
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
        {runState === 'interrupted' ? (
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
}: ChatMessagesProps) {
  return (
    <ChatMessageList
      density="balanced"
      isStreaming={isStreaming}
      scrollToTopAction={onLoadOlder}
    >
      {messages.map((message, index) => (
        <MessageRow
          key={message.clientKey}
          message={message}
          tools={toolsForAssistantDisplay(messages, index)}
        />
      ))}
      <StreamNotices
        streamPhase={streamPhase}
        streamError={streamError}
        assistantStatus={assistantStatus}
      />
    </ChatMessageList>
  );
}
