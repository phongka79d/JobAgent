/**
 * Pure helpers: map reducer tool activity to sanitized ChatToolCalls props.
 */

import type { ChatToolCallItem, ChatToolCallStatus } from "@astryxdesign/core/Chat";

import type { ToolDisplayStatus } from "../contracts";
import type { ToolActivity } from "../reducer";

const TOOL_STATUSES = new Set<ToolDisplayStatus>([
  "pending",
  "running",
  "complete",
  "error",
]);

/**
 * Format duration_ms for ChatToolCalls (e.g. "340ms", "1.2s").
 * Returns undefined when duration is absent so the control does not resize on empty text.
 */
export function formatToolDuration(durationMs: number | null): string | undefined {
  if (durationMs === null || !Number.isFinite(durationMs) || durationMs < 0) {
    return undefined;
  }
  const ms = Math.trunc(durationMs);
  if (ms < 1000) {
    return `${ms}ms`;
  }
  const seconds = ms / 1000;
  if (seconds < 10) {
    return `${seconds.toFixed(1)}s`;
  }
  return `${Math.round(seconds)}s`;
}

function toCallStatus(status: ToolDisplayStatus): ChatToolCallStatus {
  if (TOOL_STATUSES.has(status)) {
    return status;
  }
  return "error";
}

/**
 * Map reducer tool rows to documented ChatToolCallItem props only.
 * Never includes tool_call_id, raw arguments, secrets, headers, or stack traces
 * as visible display fields.
 */
export function mapToolsToChatCalls(
  tools: readonly ToolActivity[],
): ChatToolCallItem[] {
  return tools.map((tool) => {
    const status = toCallStatus(tool.status);
    const duration = formatToolDuration(tool.durationMs);
    const outcome =
      typeof tool.outcome === "string" && tool.outcome.trim().length > 0
        ? tool.outcome.trim()
        : undefined;

    const item: ChatToolCallItem = {
      // React list key only — not rendered as visible content by ChatToolCalls.
      key: tool.toolCallId,
      name: tool.label,
      status,
    };

    if (duration !== undefined) {
      item.duration = duration;
    }

    // Short sanitized outcome: target for complete/running, errorMessage for error.
    if (outcome !== undefined) {
      if (status === "error") {
        item.errorMessage = outcome;
      } else {
        item.target = outcome;
      }
    }

    return item;
  });
}

/**
 * Visible string fields from mapped tool calls (for forbidden-value tests).
 * Does not include React keys.
 */
export function collectMappedToolVisibleStrings(
  tools: readonly ToolActivity[],
): string[] {
  const calls = mapToolsToChatCalls(tools);
  const parts: string[] = [];
  for (const call of calls) {
    parts.push(call.name);
    if (call.status) {
      parts.push(call.status);
    }
    if (call.duration) {
      parts.push(call.duration);
    }
    if (call.target) {
      parts.push(call.target);
    }
    if (call.errorMessage) {
      parts.push(call.errorMessage);
    }
  }
  return parts;
}
