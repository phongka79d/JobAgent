import type {JsonObject, MessageRole, RunState, ToolStatus} from './types';

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
  /**
   * Durable ToolResult.data projection only.
   * Stream-shaped tools keep null until history/rehydrate supplies truth.
   */
  resultData: JsonObject | null;
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
