/**
 * Pure chat SSE reducer: deterministic state transitions by run_id + event_id.
 * Presentation-free; UI maps this state into Astryx components (task 03C).
 */

import type {
  AssistantDisplayStatus,
  ChatSSEEvent,
  HistoryMessage,
  ToolDisplayStatus,
} from "./contracts";

/** Distinguishable run/connection phases for send-disable and UI. */
export type ChatPhase =
  | "idle"
  | "active"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "disconnected";

export interface ToolActivity {
  readonly toolCallId: string;
  readonly label: string;
  readonly status: ToolDisplayStatus;
  readonly durationMs: number | null;
  readonly outcome: string | null;
}

export interface ApprovalState {
  readonly summary: string;
  readonly approvalKind: string | null;
}

export interface FailureState {
  readonly errorCode: string;
  readonly message: string | null;
}

export interface ChatState {
  readonly messages: readonly HistoryMessage[];
  readonly activeRunId: string | null;
  readonly phase: ChatPhase;
  /** Event IDs already applied for the active/last stream (dedupe key). */
  readonly seenEventIds: Readonly<Record<string, true>>;
  readonly assistantStatus: AssistantDisplayStatus | null;
  readonly assistantStatusMessage: string | null;
  /** Concatenated ordered text_delta stream for the current run. */
  readonly streamingText: string;
  readonly tools: readonly ToolActivity[];
  readonly approval: ApprovalState | null;
  readonly failure: FailureState | null;
  /** Transport-level error message (abort/network), separate from run_failed. */
  readonly streamError: string | null;
}

export type ChatAction =
  | { readonly type: "HYDRATE_HISTORY"; readonly messages: readonly HistoryMessage[] }
  | { readonly type: "STREAM_OPEN" }
  | { readonly type: "SSE_EVENT"; readonly event: ChatSSEEvent }
  | { readonly type: "STREAM_DISCONNECTED" }
  | { readonly type: "STREAM_ABORTED" }
  | { readonly type: "STREAM_ERROR"; readonly message: string }
  | { readonly type: "RESET_RUN" };

export function createInitialChatState(
  partial?: Partial<Pick<ChatState, "messages">>,
): ChatState {
  return {
    messages: partial?.messages ?? [],
    activeRunId: null,
    phase: "idle",
    seenEventIds: {},
    assistantStatus: null,
    assistantStatusMessage: null,
    streamingText: "",
    tools: [],
    approval: null,
    failure: null,
    streamError: null,
  };
}

/**
 * True while a turn is in flight or blocked on approval (conflicting send).
 * Idle, completed, failed, and disconnected allow a new send/resume path.
 */
export function isSendDisabled(state: ChatState): boolean {
  return state.phase === "active" || state.phase === "awaiting_approval";
}

function clearTransientRunFields(state: ChatState): ChatState {
  return {
    ...state,
    activeRunId: null,
    phase: "idle",
    seenEventIds: {},
    assistantStatus: null,
    assistantStatusMessage: null,
    streamingText: "",
    tools: [],
    approval: null,
    failure: null,
    streamError: null,
  };
}

function withSeen(state: ChatState, eventId: string): ChatState {
  if (state.seenEventIds[eventId]) {
    return state;
  }
  return {
    ...state,
    seenEventIds: { ...state.seenEventIds, [eventId]: true },
  };
}

function appendAssistantMessage(state: ChatState, content: string, timestamp: string): ChatState {
  if (!content) {
    return state;
  }
  const message: HistoryMessage = {
    role: "assistant",
    content,
    created_at: timestamp,
    structured_payload: null,
  };
  return {
    ...state,
    messages: [...state.messages, message],
  };
}

function applySSEEvent(state: ChatState, event: ChatSSEEvent): ChatState {
  // Duplicate event_id: pure no-op (same reference not required; content equal).
  if (state.seenEventIds[event.event_id]) {
    return state;
  }

  // Foreign run after we bound a run_id: ignore.
  if (
    state.activeRunId !== null &&
    event.run_id !== state.activeRunId &&
    event.event !== "run_started"
  ) {
    return state;
  }

  // Terminal phases ignore further stream events (except already-handled dupes).
  if (state.phase === "completed" || state.phase === "failed") {
    return state;
  }

  // Events before run_started (except run_started itself) are ignored.
  if (event.event !== "run_started" && state.activeRunId === null) {
    // Allow events if STREAM_OPEN set phase active without run yet only for run_started.
    if (state.phase !== "active" && state.phase !== "awaiting_approval") {
      return state;
    }
    // Still require run_started first to bind run_id for non-start events.
    return state;
  }

  switch (event.event) {
    case "run_started": {
      // New run supersedes prior active/disconnected stream binding.
      if (state.activeRunId !== null && event.run_id !== state.activeRunId) {
        // Ignore foreign run_started while another run is bound and not terminal.
        if (state.phase === "active" || state.phase === "awaiting_approval") {
          return state;
        }
      }
      return withSeen(
        {
          ...state,
          activeRunId: event.run_id,
          phase: "active",
          assistantStatus: null,
          assistantStatusMessage: null,
          streamingText: "",
          tools: [],
          approval: null,
          failure: null,
          streamError: null,
          seenEventIds: {},
        },
        event.event_id,
      );
    }
    case "assistant_status": {
      if (state.phase !== "active") {
        return state;
      }
      return withSeen(
        {
          ...state,
          assistantStatus: event.payload.status,
          assistantStatusMessage: event.payload.message ?? null,
        },
        event.event_id,
      );
    }
    case "tool_started": {
      if (state.phase !== "active") {
        return state;
      }
      const existing = state.tools.find((t) => t.toolCallId === event.payload.tool_call_id);
      if (existing) {
        return withSeen(state, event.event_id);
      }
      const tool: ToolActivity = {
        toolCallId: event.payload.tool_call_id,
        label: event.payload.label,
        status: event.payload.status,
        durationMs: null,
        outcome: null,
      };
      return withSeen(
        {
          ...state,
          tools: [...state.tools, tool],
        },
        event.event_id,
      );
    }
    case "tool_completed": {
      if (state.phase !== "active") {
        return state;
      }
      const idx = state.tools.findIndex((t) => t.toolCallId === event.payload.tool_call_id);
      let tools: readonly ToolActivity[];
      const completed: ToolActivity = {
        toolCallId: event.payload.tool_call_id,
        label: event.payload.label,
        status: event.payload.status,
        durationMs: event.payload.duration_ms ?? null,
        outcome: event.payload.outcome ?? null,
      };
      if (idx === -1) {
        tools = [...state.tools, completed];
      } else {
        const next = state.tools.slice();
        next[idx] = completed;
        tools = next;
      }
      return withSeen({ ...state, tools }, event.event_id);
    }
    case "approval_required": {
      if (state.phase !== "active") {
        return state;
      }
      return withSeen(
        {
          ...state,
          phase: "awaiting_approval",
          approval: {
            summary: event.payload.summary,
            approvalKind: event.payload.approval_kind ?? null,
          },
          assistantStatus: "waiting",
        },
        event.event_id,
      );
    }
    case "text_delta": {
      if (state.phase !== "active") {
        return state;
      }
      return withSeen(
        {
          ...state,
          streamingText: state.streamingText + event.payload.delta,
          assistantStatus: state.assistantStatus ?? "streaming",
        },
        event.event_id,
      );
    }
    case "run_completed": {
      if (state.phase !== "active" && state.phase !== "awaiting_approval") {
        return state;
      }
      const withText = appendAssistantMessage(
        withSeen(state, event.event_id),
        state.streamingText,
        event.timestamp,
      );
      return {
        ...withText,
        phase: "completed",
        approval: null,
        failure: null,
        streamError: null,
      };
    }
    case "run_failed": {
      if (state.phase !== "active" && state.phase !== "awaiting_approval") {
        return state;
      }
      return {
        ...withSeen(state, event.event_id),
        phase: "failed",
        failure: {
          errorCode: event.payload.error_code,
          message: event.payload.message ?? null,
        },
        approval: null,
        streamError: null,
      };
    }
    default: {
      const _never: never = event;
      return _never;
    }
  }
}

/**
 * Pure chat reducer. Same action sequence always yields the same state.
 * Replaying an event_id is a no-op; ordered deltas form one assistant stream.
 */
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "HYDRATE_HISTORY": {
      // Durable history is source of truth after reconnect; clear transient run UI.
      return {
        ...createInitialChatState({ messages: [...action.messages] }),
      };
    }
    case "STREAM_OPEN": {
      // Begin a turn/resume stream; bind run_id on first run_started.
      return {
        ...clearTransientRunFields(state),
        messages: state.messages,
        phase: "active",
      };
    }
    case "SSE_EVENT":
      return applySSEEvent(state, action.event);
    case "STREAM_DISCONNECTED": {
      // Only mark disconnect if we were mid-stream (not already terminal).
      if (
        state.phase === "completed" ||
        state.phase === "failed" ||
        state.phase === "idle"
      ) {
        return state;
      }
      return {
        ...state,
        phase: "disconnected",
        streamError: state.streamError ?? "disconnected",
      };
    }
    case "STREAM_ABORTED": {
      if (
        state.phase === "completed" ||
        state.phase === "failed" ||
        state.phase === "idle"
      ) {
        return state;
      }
      return {
        ...state,
        phase: "disconnected",
        streamError: "aborted",
      };
    }
    case "STREAM_ERROR": {
      if (state.phase === "completed" || state.phase === "failed") {
        return state;
      }
      return {
        ...state,
        phase: "disconnected",
        streamError: action.message,
      };
    }
    case "RESET_RUN":
      return clearTransientRunFields(state);
    default: {
      const _never: never = action;
      return _never;
    }
  }
}
