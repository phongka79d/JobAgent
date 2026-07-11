/**
 * Sanitized tool activity presentation via Astryx ChatToolCalls.
 * Only friendly label, status, duration, and short outcome — no raw/private fields.
 */

import { ChatToolCalls } from "@astryxdesign/core/Chat";

import type { ToolActivity } from "../reducer";
import { mapToolsToChatCalls } from "./toolMapping";

export interface ChatToolActivityProps {
  readonly tools: readonly ToolActivity[];
  readonly "data-testid"?: string;
}

/** Renders sanitized tool activity. Returns null when there are no tools. */
export function ChatToolActivity({
  tools,
  "data-testid": testId = "chat-tool-activity",
}: ChatToolActivityProps) {
  if (tools.length === 0) {
    return null;
  }

  const calls = mapToolsToChatCalls(tools);

  return (
    <ChatToolCalls
      calls={calls}
      defaultIsExpanded
      label={`Tool activity (${String(calls.length)})`}
      data-testid={testId}
    />
  );
}
