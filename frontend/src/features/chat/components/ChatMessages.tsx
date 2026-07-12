/**
 * Message list: durable history, partial assistant stream, tools, system states.
 */

import {
  ChatMessage,
  ChatMessageBubble,
  ChatMessageList,
  ChatSystemMessage,
} from "@astryxdesign/core/Chat";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import { SavedJobCard } from "../../jobs/components/SavedJobCard";
import { parseSavedJobCardPayload } from "../../jobs/contracts";
import type { HistoryMessage } from "../contracts";
import type { ApprovalState, ChatPhase, ChatState, FailureState } from "../reducer";
import { ChatApproval } from "./ChatApproval";
import { ChatToolActivity } from "./ChatToolActivity";

function messageSender(
  role: string,
): "user" | "assistant" | "system" {
  if (role === "user") {
    return "user";
  }
  if (role === "system") {
    return "system";
  }
  return "assistant";
}

function messageKey(message: HistoryMessage, index: number): string {
  return `${message.role}-${message.created_at}-${String(index)}`;
}

export interface ChatMessagesProps {
  readonly messages: readonly HistoryMessage[];
  readonly phase: ChatPhase;
  readonly streamingText: string;
  readonly tools: ChatState["tools"];
  readonly assistantStatus: ChatState["assistantStatus"];
  readonly assistantStatusMessage: string | null;
  readonly approval: ApprovalState | null;
  readonly failure: FailureState | null;
  readonly streamError: string | null;
  readonly approvalDisabled: boolean;
  readonly onApprove: () => void;
  /** Generic path: nonblank correction text from the approval field. */
  readonly onCorrect: (correctionText: string) => void;
  /** Profile path: Request Changes focuses main composer. */
  readonly onRequestChanges?: () => void;
  readonly "data-testid"?: string;
}

function shouldShowLiveAssistant(phase: ChatPhase): boolean {
  return (
    phase === "active" ||
    phase === "awaiting_approval" ||
    phase === "disconnected" ||
    phase === "failed"
  );
}

function assistantStatusLabel(
  status: ChatState["assistantStatus"],
  message: string | null,
): string | null {
  if (message && message.trim().length > 0) {
    return message.trim();
  }
  if (!status) {
    return null;
  }
  switch (status) {
    case "thinking":
      return "Thinking…";
    case "working":
      return "Working…";
    case "streaming":
      return "Responding…";
    case "waiting":
      return "Waiting for approval…";
    default:
      return null;
  }
}

/**
 * Presentational message log driven by pure chat state.
 * Does not fetch or mutate transport.
 */
export function ChatMessages({
  messages,
  phase,
  streamingText,
  tools,
  assistantStatus,
  assistantStatusMessage,
  approval,
  failure,
  streamError,
  approvalDisabled,
  onApprove,
  onCorrect,
  onRequestChanges,
  "data-testid": testId = "chat-messages",
}: ChatMessagesProps) {
  const live = shouldShowLiveAssistant(phase);
  const statusLabel = live
    ? assistantStatusLabel(assistantStatus, assistantStatusMessage)
    : null;
  const showPartialText = live && streamingText.length > 0;
  const showTools = live && tools.length > 0;
  const showLiveRow =
    live &&
    (showPartialText ||
      showTools ||
      statusLabel !== null ||
      approval !== null ||
      failure !== null ||
      (streamError !== null && phase === "disconnected"));

  const isStreaming =
    phase === "active" && (streamingText.length > 0 || tools.length > 0);

  return (
    <ChatMessageList
      density="balanced"
      isStreaming={isStreaming}
      data-testid={testId}
    >
      {messages.map((message, index) => {
        const sender = messageSender(message.role);
        if (sender === "system") {
          return (
            <ChatSystemMessage key={messageKey(message, index)}>
              {message.content}
            </ChatSystemMessage>
          );
        }
        const savedJob =
          sender === "assistant"
            ? parseSavedJobCardPayload(message.structured_payload ?? null)
            : null;
        return (
          <ChatMessage key={messageKey(message, index)} sender={sender}>
            <VStack gap={2}>
              {message.content.trim().length > 0 ? (
                <ChatMessageBubble
                  variant={sender === "assistant" ? "ghost" : "filled"}
                >
                  <Text type="body" as="p">
                    {message.content}
                  </Text>
                </ChatMessageBubble>
              ) : null}
              {savedJob ? (
                <SavedJobCard
                  job={savedJob}
                  data-testid={`saved-job-card-${String(index)}`}
                />
              ) : null}
            </VStack>
          </ChatMessage>
        );
      })}

      {showLiveRow ? (
        <ChatMessage sender="assistant" data-testid="chat-live-assistant">
          <VStack gap={2}>
            {statusLabel ? (
              <ChatSystemMessage data-testid="chat-assistant-status">
                {statusLabel}
              </ChatSystemMessage>
            ) : null}

            {showTools ? <ChatToolActivity tools={tools} /> : null}

            {showPartialText ? (
              <ChatMessageBubble variant="ghost">
                <Text type="body" as="p" data-testid="chat-partial-text">
                  {streamingText}
                </Text>
              </ChatMessageBubble>
            ) : null}

            {approval && phase === "awaiting_approval" ? (
              <ChatApproval
                approval={approval}
                isDisabled={approvalDisabled}
                onApprove={onApprove}
                onCorrect={onCorrect}
                onRequestChanges={onRequestChanges}
              />
            ) : null}

            {failure && phase === "failed" ? (
              <ChatSystemMessage data-testid="chat-failure">
                {failure.message && failure.message.trim().length > 0
                  ? failure.message
                  : `Run failed (${failure.errorCode})`}
              </ChatSystemMessage>
            ) : null}

            {phase === "disconnected" && streamError ? (
              <ChatSystemMessage data-testid="chat-disconnect">
                Connection lost. You can retry or send a new message.
              </ChatSystemMessage>
            ) : null}
          </VStack>
        </ChatMessage>
      ) : null}

      {phase === "completed" ? (
        <ChatSystemMessage data-testid="chat-completed">
          Response complete
        </ChatSystemMessage>
      ) : null}
    </ChatMessageList>
  );
}
