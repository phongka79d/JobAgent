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

/** Allowlisted match_jobs public outcome tokens → short display labels. */
const MATCH_JOBS_OUTCOME_LABELS: Readonly<Record<string, string>> = {
  matches_found: "Matches found",
  no_matches: "No matches",
  profile_required: "Profile required",
  match_failed: "Match failed",
  matchesfound: "Matches found",
  nomatches: "No matches",
  profilerequired: "Profile required",
  matchfailed: "Match failed",
};

const MATCH_JOBS_LABELS = new Set([
  "match_jobs",
  "match jobs",
  "matchjobs",
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
 * Sanitize tool display labels (e.g. raw match_jobs → Match jobs).
 * Backend already emits friendly labels; this is a fail-closed display guard.
 */
export function sanitizeToolLabel(label: string): string {
  const cleaned = label.trim().replace(/\s+/g, " ");
  if (!cleaned) {
    return "Tool";
  }
  const key = cleaned.toLowerCase().replace(/_/g, " ");
  if (MATCH_JOBS_LABELS.has(key.replace(/\s+/g, " ")) || MATCH_JOBS_LABELS.has(key.replace(/\s+/g, ""))) {
    return "Match jobs";
  }
  if (key === "match jobs") {
    return "Match jobs";
  }
  return cleaned.slice(0, 128);
}

/**
 * Sanitize short tool outcomes. Known match_jobs tokens map to friendly text;
 * free-form long bodies are truncated (never raw tool JSON).
 */
export function sanitizeToolOutcome(outcome: string | null): string | undefined {
  if (outcome === null || typeof outcome !== "string") {
    return undefined;
  }
  const cleaned = outcome.trim().replace(/\s+/g, " ");
  if (!cleaned) {
    return undefined;
  }
  const token = cleaned.toLowerCase().replace(/-/g, "_").replace(/\s+/g, "_");
  const mapped = MATCH_JOBS_OUTCOME_LABELS[token];
  if (mapped) {
    return mapped;
  }
  // Friendly outcomes already on the wire (backend labels).
  const lower = cleaned.toLowerCase();
  if (
    lower === "matches found" ||
    lower === "no matches" ||
    lower === "profile required" ||
    lower === "match failed"
  ) {
    return cleaned.length <= 64 ? cleaned : cleaned.slice(0, 64);
  }
  // Reject JSON / argument-shaped bodies that must never display.
  if (
    cleaned.startsWith("{") ||
    cleaned.startsWith("[") ||
    cleaned.includes('"arguments"') ||
    cleaned.includes("raw_content") ||
    cleaned.length > 128
  ) {
    return undefined;
  }
  return cleaned.slice(0, 64);
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
    const outcome = sanitizeToolOutcome(tool.outcome);

    const item: ChatToolCallItem = {
      // React list key only — not rendered as visible content by ChatToolCalls.
      key: tool.toolCallId,
      name: sanitizeToolLabel(tool.label),
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
