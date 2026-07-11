/**
 * Typed public chat contracts matching backend Plan 3 SSE / history / turn APIs.
 * Source of truth: backend `app/schemas/sse.py` and `app/schemas/chat.py`.
 * Presentation-free: no React imports.
 */

/** Exact public SSE event names (eight-event union). */
export type SSEEventType =
  | "run_started"
  | "assistant_status"
  | "tool_started"
  | "tool_completed"
  | "approval_required"
  | "text_delta"
  | "run_completed"
  | "run_failed";

export const SSE_EVENT_TYPES = [
  "run_started",
  "assistant_status",
  "tool_started",
  "tool_completed",
  "approval_required",
  "text_delta",
  "run_completed",
  "run_failed",
] as const satisfies readonly SSEEventType[];

export const TERMINAL_SSE_EVENT_TYPES = [
  "run_completed",
  "run_failed",
] as const satisfies readonly SSEEventType[];

export type ToolDisplayStatus = "pending" | "running" | "complete" | "error";

export type AssistantDisplayStatus =
  | "thinking"
  | "working"
  | "streaming"
  | "waiting";

export interface RunStartedPayload {
  readonly [key: string]: never;
}

export interface AssistantStatusPayload {
  readonly status: AssistantDisplayStatus;
  readonly message?: string | null;
}

export interface ToolStartedPayload {
  readonly tool_call_id: string;
  readonly label: string;
  readonly status: ToolDisplayStatus;
}

export interface ToolCompletedPayload {
  readonly tool_call_id: string;
  readonly label: string;
  readonly status: ToolDisplayStatus;
  readonly duration_ms?: number | null;
  readonly outcome?: string | null;
}

export interface ApprovalRequiredPayload {
  readonly summary: string;
  readonly approval_kind?: string | null;
}

export interface TextDeltaPayload {
  readonly delta: string;
}

export interface RunCompletedPayload {
  readonly [key: string]: never;
}

export interface RunFailedPayload {
  readonly error_code: string;
  readonly message?: string | null;
}

interface SSEEventBase {
  readonly event_id: string;
  readonly run_id: string;
  readonly timestamp: string;
}

export interface RunStartedEvent extends SSEEventBase {
  readonly event: "run_started";
  readonly payload: RunStartedPayload;
}

export interface AssistantStatusEvent extends SSEEventBase {
  readonly event: "assistant_status";
  readonly payload: AssistantStatusPayload;
}

export interface ToolStartedEvent extends SSEEventBase {
  readonly event: "tool_started";
  readonly payload: ToolStartedPayload;
}

export interface ToolCompletedEvent extends SSEEventBase {
  readonly event: "tool_completed";
  readonly payload: ToolCompletedPayload;
}

export interface ApprovalRequiredEvent extends SSEEventBase {
  readonly event: "approval_required";
  readonly payload: ApprovalRequiredPayload;
}

export interface TextDeltaEvent extends SSEEventBase {
  readonly event: "text_delta";
  readonly payload: TextDeltaPayload;
}

export interface RunCompletedEvent extends SSEEventBase {
  readonly event: "run_completed";
  readonly payload: RunCompletedPayload;
}

export interface RunFailedEvent extends SSEEventBase {
  readonly event: "run_failed";
  readonly payload: RunFailedPayload;
}

export type ChatSSEEvent =
  | RunStartedEvent
  | AssistantStatusEvent
  | ToolStartedEvent
  | ToolCompletedEvent
  | ApprovalRequiredEvent
  | TextDeltaEvent
  | RunCompletedEvent
  | RunFailedEvent;

/** POST /api/chat/turns body. */
export interface TurnRequest {
  readonly text: string;
  readonly attachment_ids?: readonly string[];
  readonly idempotency_key: string;
}

/** POST /api/chat/runs/{run_id}/resume body. */
export interface ResumeRequest {
  readonly action: "approve" | "correct";
  readonly idempotency_key: string;
  readonly correction_text?: string | null;
}

/** One durable history message from GET /api/chat/history. */
export interface HistoryMessage {
  readonly role: string;
  readonly content: string;
  readonly created_at: string;
  readonly structured_payload?: Record<string, unknown> | null;
}

export interface HistoryResponse {
  readonly messages: readonly HistoryMessage[];
}

/** Approved public chat path suffixes (relative to VITE_API_BASE_URL). */
export const CHAT_API_PATHS = {
  history: "/api/chat/history",
  turns: "/api/chat/turns",
  resume: (runId: string): string =>
    `/api/chat/runs/${encodeURIComponent(runId)}/resume`,
} as const;

export class ChatContractError extends Error {
  readonly code: string;

  constructor(code: string, message?: string) {
    super(message ?? code);
    this.name = "ChatContractError";
    this.code = code;
  }
}

const ASSISTANT_STATUSES = new Set<AssistantDisplayStatus>([
  "thinking",
  "working",
  "streaming",
  "waiting",
]);

const TOOL_START_STATUSES = new Set<ToolDisplayStatus>(["pending", "running"]);
const TOOL_END_STATUSES = new Set<ToolDisplayStatus>(["complete", "error"]);

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new ChatContractError("invalid_event", `missing or invalid ${field}`);
  }
  return value;
}

function optionalString(value: unknown): string | null {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string") {
    throw new ChatContractError("invalid_event", "invalid optional string");
  }
  return value;
}

function optionalNonNegativeInt(value: unknown): number | null {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new ChatContractError("invalid_event", "invalid duration_ms");
  }
  return Math.trunc(value);
}

/**
 * Parse and validate one backend SSE JSON object into the eight-event union.
 * Rejects unknown types and mismatched payloads.
 */
export function parseChatSSEEvent(raw: unknown): ChatSSEEvent {
  if (!isPlainObject(raw)) {
    throw new ChatContractError("invalid_event", "event must be an object");
  }

  const eventName = raw.event;
  if (typeof eventName !== "string" || !SSE_EVENT_TYPES.includes(eventName as SSEEventType)) {
    throw new ChatContractError("unknown_event", "unknown event type");
  }

  const event_id = requireString(raw.event_id, "event_id");
  const run_id = requireString(raw.run_id, "run_id");
  const timestamp = requireString(raw.timestamp, "timestamp");
  const payload = raw.payload;
  if (!isPlainObject(payload)) {
    throw new ChatContractError("invalid_event", "payload must be an object");
  }

  const base = { event_id, run_id, timestamp } as const;

  switch (eventName as SSEEventType) {
    case "run_started":
      return { ...base, event: "run_started", payload: {} };
    case "run_completed":
      return { ...base, event: "run_completed", payload: {} };
    case "assistant_status": {
      const status = payload.status;
      if (typeof status !== "string" || !ASSISTANT_STATUSES.has(status as AssistantDisplayStatus)) {
        throw new ChatContractError("invalid_event", "invalid assistant status");
      }
      return {
        ...base,
        event: "assistant_status",
        payload: {
          status: status as AssistantDisplayStatus,
          message: optionalString(payload.message),
        },
      };
    }
    case "tool_started": {
      const status = (payload.status ?? "running") as string;
      if (!TOOL_START_STATUSES.has(status as ToolDisplayStatus)) {
        throw new ChatContractError("invalid_event", "invalid tool_started status");
      }
      return {
        ...base,
        event: "tool_started",
        payload: {
          tool_call_id: requireString(payload.tool_call_id, "tool_call_id"),
          label: requireString(payload.label, "label"),
          status: status as ToolDisplayStatus,
        },
      };
    }
    case "tool_completed": {
      const status = payload.status;
      if (typeof status !== "string" || !TOOL_END_STATUSES.has(status as ToolDisplayStatus)) {
        throw new ChatContractError("invalid_event", "invalid tool_completed status");
      }
      return {
        ...base,
        event: "tool_completed",
        payload: {
          tool_call_id: requireString(payload.tool_call_id, "tool_call_id"),
          label: requireString(payload.label, "label"),
          status: status as ToolDisplayStatus,
          duration_ms: optionalNonNegativeInt(payload.duration_ms),
          outcome: optionalString(payload.outcome),
        },
      };
    }
    case "approval_required":
      return {
        ...base,
        event: "approval_required",
        payload: {
          summary: requireString(payload.summary, "summary"),
          approval_kind: optionalString(payload.approval_kind),
        },
      };
    case "text_delta": {
      const delta = payload.delta;
      if (typeof delta !== "string" || delta.length === 0) {
        throw new ChatContractError("invalid_event", "invalid delta");
      }
      return {
        ...base,
        event: "text_delta",
        payload: { delta },
      };
    }
    case "run_failed":
      return {
        ...base,
        event: "run_failed",
        payload: {
          error_code: requireString(payload.error_code, "error_code"),
          message: optionalString(payload.message),
        },
      };
    default: {
      const _exhaustive: never = eventName as never;
      throw new ChatContractError("unknown_event", String(_exhaustive));
    }
  }
}

/** Parse SSE `data:` payload string as a chat event. */
export function parseChatSSEData(data: string): ChatSSEEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(data) as unknown;
  } catch {
    throw new ChatContractError("invalid_json", "SSE data is not valid JSON");
  }
  return parseChatSSEEvent(parsed);
}

/** Parse GET /api/chat/history JSON body. */
export function parseHistoryResponse(raw: unknown): HistoryResponse {
  if (!isPlainObject(raw) || !Array.isArray(raw.messages)) {
    throw new ChatContractError("invalid_history", "history response invalid");
  }
  const messages: HistoryMessage[] = raw.messages.map((item, index) => {
    if (!isPlainObject(item)) {
      throw new ChatContractError("invalid_history", `message ${index} invalid`);
    }
    const role = requireString(item.role, "role");
    const content = typeof item.content === "string" ? item.content : "";
    const created_at = requireString(item.created_at, "created_at");
    let structured_payload: Record<string, unknown> | null = null;
    if (item.structured_payload !== undefined && item.structured_payload !== null) {
      if (!isPlainObject(item.structured_payload)) {
        throw new ChatContractError("invalid_history", "structured_payload invalid");
      }
      structured_payload = item.structured_payload;
    }
    return { role, content, created_at, structured_payload };
  });
  return { messages };
}

export function isTerminalSSEEvent(
  event: ChatSSEEvent,
): event is RunCompletedEvent | RunFailedEvent {
  return event.event === "run_completed" || event.event === "run_failed";
}
