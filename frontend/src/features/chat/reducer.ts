/**
 * Single owner of client message/run/tool streaming state (Plan 3 §7.9).
 * Deduplicates by event_id, appends ordered text deltas, exact statuses only.
 * Never infers run completion after failure or disconnect.
 */

import {
  hydrateFromHistoryPage,
  mergeOlderHistoryPage,
  recoverPendingApproval,
  rehydrateWithDurableTruth,
} from './history';
import type {
  ApprovalRequiredPayload,
  HistoryPage,
  JsonObject,
  MessageRole,
  RunState,
  SseEvent,
  ToolStatus,
} from './types';
import {parseSseEventData, SseParseError} from './types';

export type StreamPhase =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'disconnected'
  | 'failed';

export interface ClientToolActivity {
  toolExecutionId: string;
  toolCallId: string;
  toolName: string;
  status: ToolStatus;
  durationMs: number | null;
  summary: string | null;
  errorCode: string | null;
  source: 'stream' | 'history';
}

export interface ClientRun {
  id: string;
  userMessageId: string | null;
  state: RunState;
  pendingApproval: JsonObject | null;
  errorCode: string | null;
  completedAt: string | null;
  tools: ClientToolActivity[];
}

export interface ClientMessage {
  id: string;
  /** Stable React key; equals id for durable messages. */
  clientKey: string;
  role: MessageRole;
  content: string;
  createdAt: string | null;
  run: ClientRun | null;
  isStreaming: boolean;
}

export interface StreamErrorInfo {
  code: string;
  summary: string;
}

export interface ChatState {
  messages: ClientMessage[];
  /** event_id → true for deduplication */
  seenEventIds: Readonly<Record<string, true>>;
  activeRunId: string | null;
  streamingAssistantKey: string | null;
  nextCursor: string | null;
  streamPhase: StreamPhase;
  streamError: StreamErrorInfo | null;
  assistantStatus: string | null;
  pendingApproval: ApprovalRequiredPayload | null;
}

export type ChatAction =
  | {type: 'history/reset'; page: HistoryPage}
  | {type: 'history/load_older'; page: HistoryPage}
  | {type: 'history/rehydrate'; page: HistoryPage}
  | {
      type: 'turn/start';
      clientKey: string;
      message: string;
      createdAt?: string;
    }
  | {type: 'sse/event'; event: SseEvent}
  | {type: 'sse/raw'; data: unknown}
  | {type: 'stream/disconnected'}
  | {type: 'stream/http_failed'; code: string; summary: string}
  | {type: 'stream/reset_error'};

export function createInitialChatState(): ChatState {
  return {
    messages: [],
    seenEventIds: {},
    activeRunId: null,
    streamingAssistantKey: null,
    nextCursor: null,
    streamPhase: 'idle',
    streamError: null,
    assistantStatus: null,
    pendingApproval: null,
  };
}

function markSeen(
  seen: Readonly<Record<string, true>>,
  eventId: string,
): Record<string, true> {
  if (seen[eventId]) {
    return seen as Record<string, true>;
  }
  return {...seen, [eventId]: true};
}

function upsertTool(
  tools: readonly ClientToolActivity[],
  next: ClientToolActivity,
): ClientToolActivity[] {
  const idx = tools.findIndex(
    (t) =>
      t.toolExecutionId === next.toolExecutionId ||
      t.toolCallId === next.toolCallId,
  );
  if (idx === -1) {
    return [...tools, next];
  }
  const copy = [...tools];
  copy[idx] = next;
  return copy;
}

function updateAssistantForRun(
  messages: readonly ClientMessage[],
  runId: string,
  assistantKey: string | null,
  updater: (msg: ClientMessage, run: ClientRun) => ClientMessage,
): ClientMessage[] {
  return messages.map((msg) => {
    if (msg.role !== 'assistant') {
      return msg;
    }
    if (msg.run?.id === runId) {
      return updater(msg, msg.run);
    }
    if (
      assistantKey !== null &&
      msg.clientKey === assistantKey &&
      (msg.run === null || msg.run.id === runId)
    ) {
      const run: ClientRun =
        msg.run ??
        ({
          id: runId,
          userMessageId: null,
          state: 'running',
          pendingApproval: null,
          errorCode: null,
          completedAt: null,
          tools: [],
        } satisfies ClientRun);
      return updater(msg, run);
    }
    return msg;
  });
}

function ensureStreamingAssistant(
  state: ChatState,
  runId: string,
  timestamp: string,
): {messages: ClientMessage[]; streamingAssistantKey: string} {
  if (state.streamingAssistantKey) {
    const existing = state.messages.find(
      (m) => m.clientKey === state.streamingAssistantKey,
    );
    if (existing) {
      const messages = state.messages.map((m) => {
        if (m.clientKey !== state.streamingAssistantKey) {
          return m;
        }
        if (m.run?.id === runId) {
          return m;
        }
        return {
          ...m,
          run: {
            id: runId,
            userMessageId: m.run?.userMessageId ?? null,
            state: 'running' as const,
            pendingApproval: null,
            errorCode: null,
            completedAt: null,
            tools: m.run?.tools ?? [],
          },
          isStreaming: true,
        };
      });
      return {
        messages,
        streamingAssistantKey: state.streamingAssistantKey,
      };
    }
  }
  const key = `assistant:${runId}`;
  const assistant: ClientMessage = {
    id: key,
    clientKey: key,
    role: 'assistant',
    content: '',
    createdAt: timestamp,
    run: {
      id: runId,
      userMessageId: null,
      state: 'running',
      pendingApproval: null,
      errorCode: null,
      completedAt: null,
      tools: [],
    },
    isStreaming: true,
  };
  return {
    messages: [...state.messages, assistant],
    streamingAssistantKey: key,
  };
}

function applySseEvent(state: ChatState, event: SseEvent): ChatState {
  if (state.seenEventIds[event.event_id]) {
    return state;
  }
  const seenEventIds = markSeen(state.seenEventIds, event.event_id);

  switch (event.event) {
    case 'run_started': {
      const ensured = ensureStreamingAssistant(
        {...state, seenEventIds},
        event.run_id,
        event.timestamp,
      );
      return {
        ...state,
        seenEventIds,
        messages: ensured.messages.map((m) => {
          if (m.clientKey !== ensured.streamingAssistantKey || !m.run) {
            return m;
          }
          return {
            ...m,
            run: {...m.run, state: 'running', errorCode: null},
            isStreaming: true,
          };
        }),
        activeRunId: event.run_id,
        streamingAssistantKey: ensured.streamingAssistantKey,
        streamPhase: 'streaming',
        streamError: null,
        assistantStatus: null,
        pendingApproval: event.payload.resumed ? state.pendingApproval : null,
      };
    }
    case 'assistant_status': {
      return {
        ...state,
        seenEventIds,
        assistantStatus: event.payload.message,
        streamPhase:
          state.streamPhase === 'idle' ? 'streaming' : state.streamPhase,
      };
    }
    case 'text_delta': {
      const ensured = ensureStreamingAssistant(
        {...state, seenEventIds},
        event.run_id,
        event.timestamp,
      );
      const messages = ensured.messages.map((m) => {
        if (m.clientKey !== ensured.streamingAssistantKey) {
          return m;
        }
        return {
          ...m,
          content: m.content + event.payload.delta,
          isStreaming: true,
        };
      });
      return {
        ...state,
        seenEventIds,
        messages,
        activeRunId: event.run_id,
        streamingAssistantKey: ensured.streamingAssistantKey,
        streamPhase: 'streaming',
      };
    }
    case 'tool_status': {
      const ensured = ensureStreamingAssistant(
        {...state, seenEventIds},
        event.run_id,
        event.timestamp,
      );
      const tool: ClientToolActivity = {
        toolExecutionId: event.payload.tool_execution_id,
        toolCallId: event.payload.tool_call_id,
        toolName: event.payload.tool_name,
        status: event.payload.status,
        durationMs: event.payload.duration_ms,
        summary: event.payload.summary,
        errorCode: event.payload.error_code,
        source: 'stream',
      };
      const messages = updateAssistantForRun(
        ensured.messages,
        event.run_id,
        ensured.streamingAssistantKey,
        (msg, run) => ({
          ...msg,
          run: {...run, tools: upsertTool(run.tools, tool)},
          isStreaming: true,
        }),
      );
      return {
        ...state,
        seenEventIds,
        messages,
        activeRunId: event.run_id,
        streamingAssistantKey: ensured.streamingAssistantKey,
        streamPhase: 'streaming',
      };
    }
    case 'approval_required': {
      const ensured = ensureStreamingAssistant(
        {...state, seenEventIds},
        event.run_id,
        event.timestamp,
      );
      const messages = updateAssistantForRun(
        ensured.messages,
        event.run_id,
        ensured.streamingAssistantKey,
        (msg, run) => ({
          ...msg,
          run: {
            ...run,
            state: 'interrupted',
            pendingApproval: {
              kind: event.payload.kind,
              allowed_actions: event.payload.allowed_actions,
              card: event.payload.card,
            },
          },
          isStreaming: false,
        }),
      );
      return {
        ...state,
        seenEventIds,
        messages,
        activeRunId: event.run_id,
        streamingAssistantKey: ensured.streamingAssistantKey,
        streamPhase: 'idle',
        pendingApproval: event.payload,
        assistantStatus: null,
      };
    }
    case 'run_completed': {
      const messages = updateAssistantForRun(
        state.messages,
        event.run_id,
        state.streamingAssistantKey,
        (msg, run) => ({
          ...msg,
          run: {
            ...run,
            state: 'completed',
            errorCode: null,
            completedAt: event.timestamp,
            pendingApproval: null,
          },
          isStreaming: false,
        }),
      );
      return {
        ...state,
        seenEventIds,
        messages,
        activeRunId: null,
        streamingAssistantKey: null,
        streamPhase: 'idle',
        streamError: null,
        assistantStatus: null,
        pendingApproval: null,
      };
    }
    case 'run_failed': {
      const messages = updateAssistantForRun(
        state.messages,
        event.run_id,
        state.streamingAssistantKey,
        (msg, run) => ({
          ...msg,
          run: {
            ...run,
            state: 'failed',
            errorCode: event.payload.error_code,
            completedAt: event.timestamp,
          },
          isStreaming: false,
        }),
      );
      return {
        ...state,
        seenEventIds,
        messages,
        activeRunId: null,
        streamingAssistantKey: null,
        streamPhase: 'failed',
        streamError: {
          code: event.payload.error_code,
          summary: event.payload.summary,
        },
        assistantStatus: null,
        pendingApproval: null,
      };
    }
    default:
      return {...state, seenEventIds};
  }
}

/**
 * Pure chat reducer — sole owner of streaming/history client state.
 */
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'history/reset': {
      const {messages, nextCursor} = hydrateFromHistoryPage(action.page);
      const recovered = recoverPendingApproval(messages);
      return {
        ...createInitialChatState(),
        messages,
        nextCursor,
        pendingApproval: recovered.pendingApproval,
        activeRunId: recovered.activeRunId,
      };
    }
    case 'history/load_older': {
      const {messages, nextCursor} = mergeOlderHistoryPage(
        state.messages,
        action.page,
      );
      // Prefer existing in-memory interrupt; otherwise recover from merged set.
      const recovered =
        state.pendingApproval !== null
          ? {
              pendingApproval: state.pendingApproval,
              activeRunId: state.activeRunId,
            }
          : recoverPendingApproval(messages);
      return {
        ...state,
        messages,
        nextCursor,
        pendingApproval: recovered.pendingApproval,
        activeRunId: recovered.activeRunId,
      };
    }
    case 'history/rehydrate': {
      const {messages, nextCursor} = rehydrateWithDurableTruth(
        state.messages,
        action.page,
      );
      const recovered = recoverPendingApproval(messages);
      return {
        ...state,
        messages,
        nextCursor,
        // Durable interrupted runs reconstruct pending approval after restart.
        pendingApproval:
          recovered.pendingApproval ??
          (state.streamPhase === 'streaming' ? state.pendingApproval : null),
        activeRunId: recovered.activeRunId ?? state.activeRunId,
        // Durable truth ends in-flight streaming presentation for hydrated runs.
        streamPhase:
          state.streamPhase === 'streaming' ? state.streamPhase : state.streamPhase,
      };
    }
    case 'turn/start': {
      const user: ClientMessage = {
        id: action.clientKey,
        clientKey: action.clientKey,
        role: 'user',
        content: action.message,
        createdAt: action.createdAt ?? new Date().toISOString(),
        run: null,
        isStreaming: false,
      };
      return {
        ...state,
        messages: [...state.messages, user],
        streamPhase: 'connecting',
        streamError: null,
        assistantStatus: null,
        pendingApproval: null,
        activeRunId: null,
        streamingAssistantKey: null,
      };
    }
    case 'sse/event':
      return applySseEvent(state, action.event);
    case 'sse/raw': {
      try {
        const event = parseSseEventData(action.data);
        return applySseEvent(state, event);
      } catch (err) {
        // Unknown/malformed: fail safely without mutating domain state.
        if (err instanceof SseParseError) {
          return state;
        }
        return state;
      }
    }
    case 'stream/disconnected': {
      // Visible non-complete: never set run state to completed.
      const messages = state.messages.map((m) => {
        if (!m.isStreaming && m.run?.state !== 'running') {
          return m;
        }
        if (m.run?.state === 'running') {
          return {
            ...m,
            isStreaming: false,
            // Leave state as running — disconnect is not terminal success/failure.
          };
        }
        return {...m, isStreaming: false};
      });
      return {
        ...state,
        messages,
        streamPhase: 'disconnected',
        streamingAssistantKey: null,
        // activeRunId retained so UI can show which run was interrupted by disconnect
      };
    }
    case 'stream/http_failed': {
      const messages = state.messages.map((m) =>
        m.isStreaming ? {...m, isStreaming: false} : m,
      );
      return {
        ...state,
        messages,
        streamPhase: 'failed',
        streamError: {code: action.code, summary: action.summary},
        streamingAssistantKey: null,
        activeRunId: null,
      };
    }
    case 'stream/reset_error':
      return {
        ...state,
        streamError: null,
        streamPhase:
          state.streamPhase === 'failed' || state.streamPhase === 'disconnected'
            ? 'idle'
            : state.streamPhase,
      };
    default:
      return state;
  }
}

/** True when composer should be disabled (in-flight or interrupted). */
export function isComposerLocked(state: ChatState): boolean {
  if (
    state.streamPhase === 'connecting' ||
    state.streamPhase === 'streaming'
  ) {
    return true;
  }
  if (state.pendingApproval !== null) {
    return true;
  }
  return state.messages.some((m) => m.run?.state === 'interrupted');
}
