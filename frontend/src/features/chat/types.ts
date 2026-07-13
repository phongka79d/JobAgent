/**
 * Client types mirroring backend chat/SSE/history contracts (Plan 3 §7.7–7.9).
 * Application statuses are exact: run running|interrupted|completed|failed;
 * tool pending|running|completed|failed. Aliases complete/error are rejected.
 */

/** Exact run states (no complete/error aliases). */
export type RunState = 'running' | 'interrupted' | 'completed' | 'failed';

/** Exact tool statuses (no complete/error aliases). */
export type ToolStatus = 'pending' | 'running' | 'completed' | 'failed';

export type MessageRole = 'user' | 'assistant' | 'system';

export type SseEventName =
  | 'run_started'
  | 'assistant_status'
  | 'tool_status'
  | 'approval_required'
  | 'text_delta'
  | 'run_completed'
  | 'run_failed';

export const SSE_EVENT_NAMES: readonly SseEventName[] = [
  'run_started',
  'assistant_status',
  'tool_status',
  'approval_required',
  'text_delta',
  'run_completed',
  'run_failed',
] as const;

export const RUN_STATES: readonly RunState[] = [
  'running',
  'interrupted',
  'completed',
  'failed',
] as const;

export const TOOL_STATUSES: readonly ToolStatus[] = [
  'pending',
  'running',
  'completed',
  'failed',
] as const;

/** Forbidden application-status aliases (must never enter client state). */
export const FORBIDDEN_STATUS_ALIASES = new Set(['complete', 'error']);

const UUID_V4_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | {[key: string]: JsonValue};

export type JsonObject = {[key: string]: JsonValue};

export interface ToolResult {
  ok: boolean;
  code: string | null;
  summary: string;
  data: JsonObject | null;
}

export interface SseEnvelopeBase {
  event_id: string;
  run_id: string;
  timestamp: string;
}

export interface RunStartedPayload {
  state: 'running';
  resumed: boolean;
}

export interface AssistantStatusPayload {
  message: string;
}

export interface ToolStatusPayload {
  tool_execution_id: string;
  tool_call_id: string;
  tool_name: string;
  status: ToolStatus;
  duration_ms: number | null;
  summary: string | null;
  error_code: string | null;
}

export interface ApprovalRequiredPayload {
  state: 'interrupted';
  kind: string;
  allowed_actions: string[];
  card: JsonObject;
}

export interface TextDeltaPayload {
  delta: string;
}

export interface RunCompletedPayload {
  state: 'completed';
}

export interface RunFailedPayload {
  state: 'failed';
  error_code: string;
  summary: string;
}

export type SseEvent =
  | (SseEnvelopeBase & {event: 'run_started'; payload: RunStartedPayload})
  | (SseEnvelopeBase & {
      event: 'assistant_status';
      payload: AssistantStatusPayload;
    })
  | (SseEnvelopeBase & {event: 'tool_status'; payload: ToolStatusPayload})
  | (SseEnvelopeBase & {
      event: 'approval_required';
      payload: ApprovalRequiredPayload;
    })
  | (SseEnvelopeBase & {event: 'text_delta'; payload: TextDeltaPayload})
  | (SseEnvelopeBase & {event: 'run_completed'; payload: RunCompletedPayload})
  | (SseEnvelopeBase & {event: 'run_failed'; payload: RunFailedPayload});

export interface ToolExecutionView {
  id: string;
  tool_call_id: string;
  tool_name: string;
  status: ToolStatus;
  duration_ms: number | null;
  error_code: string | null;
  result: ToolResult | null;
  arguments_summary: JsonObject | null;
  created_at: string;
  updated_at: string;
}

export interface AgentRunView {
  id: string;
  user_message_id: string;
  state: RunState;
  pending_approval: JsonObject | null;
  error_code: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  tool_executions: ToolExecutionView[];
}

export interface ChatMessageView {
  id: string;
  role: MessageRole;
  content: string;
  structured_payload: JsonObject | null;
  created_at: string;
  updated_at: string;
  run: AgentRunView | null;
}

export interface HistoryPage {
  items: ChatMessageView[];
  next_cursor: string | null;
}

export class SseParseError extends Error {
  readonly kind = 'sse_parse_error';

  constructor(message: string) {
    super(message);
    this.name = 'SseParseError';
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isUuidV4(value: string): boolean {
  return UUID_V4_RE.test(value.toLowerCase());
}

export function rejectStatusAlias(value: string): void {
  if (FORBIDDEN_STATUS_ALIASES.has(value)) {
    throw new SseParseError(
      `status alias '${value}' is not a valid application status`,
    );
  }
}

function requireString(obj: Record<string, unknown>, key: string): string {
  const v = obj[key];
  if (typeof v !== 'string' || v === '') {
    throw new SseParseError(`${key} must be a non-empty string`);
  }
  return v;
}

function requireUuid(obj: Record<string, unknown>, key: string): string {
  const v = requireString(obj, key).toLowerCase();
  if (!isUuidV4(v)) {
    throw new SseParseError(`${key} must be a UUID v4`);
  }
  return v;
}

function asToolStatus(value: unknown): ToolStatus {
  if (typeof value !== 'string') {
    throw new SseParseError('tool status must be a string');
  }
  rejectStatusAlias(value);
  if (!(TOOL_STATUSES as readonly string[]).includes(value)) {
    throw new SseParseError(`invalid tool status '${value}'`);
  }
  return value as ToolStatus;
}

function asRunState(value: unknown): RunState {
  if (typeof value !== 'string') {
    throw new SseParseError('run state must be a string');
  }
  rejectStatusAlias(value);
  if (!(RUN_STATES as readonly string[]).includes(value)) {
    throw new SseParseError(`invalid run state '${value}'`);
  }
  return value as RunState;
}

function parseToolStatusPayload(raw: Record<string, unknown>): ToolStatusPayload {
  const status = asToolStatus(raw.status);
  const tool_execution_id = requireUuid(raw, 'tool_execution_id');
  const tool_call_id = requireString(raw, 'tool_call_id');
  const tool_name = requireString(raw, 'tool_name');
  const duration_ms =
    raw.duration_ms === undefined || raw.duration_ms === null
      ? null
      : typeof raw.duration_ms === 'number' &&
          Number.isInteger(raw.duration_ms) &&
          raw.duration_ms >= 0
        ? raw.duration_ms
        : (() => {
            throw new SseParseError('duration_ms must be a non-negative integer');
          })();
  const summary =
    raw.summary === undefined || raw.summary === null
      ? null
      : typeof raw.summary === 'string'
        ? raw.summary
        : (() => {
            throw new SseParseError('summary must be a string or null');
          })();
  const error_code =
    raw.error_code === undefined || raw.error_code === null
      ? null
      : typeof raw.error_code === 'string'
        ? raw.error_code
        : (() => {
            throw new SseParseError('error_code must be a string or null');
          })();

  if (status === 'failed' && (error_code === null || error_code.trim() === '')) {
    throw new SseParseError('tool_status failed requires error_code');
  }
  if (
    (status === 'completed' || status === 'failed') &&
    duration_ms === null
  ) {
    throw new SseParseError('tool_status completed|failed requires duration_ms');
  }
  if (status === 'pending' || status === 'running') {
    if (duration_ms !== null) {
      throw new SseParseError('pending|running must not include duration_ms');
    }
    if (error_code !== null) {
      throw new SseParseError('pending|running must not include error_code');
    }
  }
  if (status === 'completed' && error_code !== null) {
    throw new SseParseError('completed must not include error_code');
  }

  return {
    tool_execution_id,
    tool_call_id,
    tool_name,
    status,
    duration_ms,
    summary,
    error_code,
  };
}

/**
 * Validate a JSON data envelope from SSE `data:` into a typed SseEvent.
 * Unknown/malformed events throw SseParseError (callers must not mutate state).
 */
export function parseSseEventData(data: unknown): SseEvent {
  if (!isObject(data)) {
    throw new SseParseError('SSE data must be a JSON object');
  }
  const event_id = requireUuid(data, 'event_id');
  const run_id = requireUuid(data, 'run_id');
  const timestamp = requireString(data, 'timestamp');
  const event = requireString(data, 'event');
  if (!(SSE_EVENT_NAMES as readonly string[]).includes(event)) {
    throw new SseParseError(`unknown SSE event '${event}'`);
  }
  if (!isObject(data.payload)) {
    throw new SseParseError('payload must be an object');
  }
  const payload = data.payload;
  const base = {event_id, run_id, timestamp};

  switch (event as SseEventName) {
    case 'run_started': {
      if (payload.state !== 'running') {
        rejectStatusAlias(String(payload.state ?? ''));
        throw new SseParseError("run_started requires state='running'");
      }
      if (typeof payload.resumed !== 'boolean') {
        throw new SseParseError('run_started requires resumed: boolean');
      }
      return {
        ...base,
        event: 'run_started',
        payload: {state: 'running', resumed: payload.resumed},
      };
    }
    case 'assistant_status': {
      const message = requireString(payload, 'message');
      return {...base, event: 'assistant_status', payload: {message}};
    }
    case 'tool_status':
      return {
        ...base,
        event: 'tool_status',
        payload: parseToolStatusPayload(payload),
      };
    case 'approval_required': {
      if (payload.state !== 'interrupted') {
        rejectStatusAlias(String(payload.state ?? ''));
        throw new SseParseError("approval_required requires state='interrupted'");
      }
      const kind = requireString(payload, 'kind');
      if (!Array.isArray(payload.allowed_actions) || payload.allowed_actions.length === 0) {
        throw new SseParseError('allowed_actions must be a non-empty string array');
      }
      const allowed_actions = payload.allowed_actions.map((a) => {
        if (typeof a !== 'string' || a.trim() === '') {
          throw new SseParseError('allowed_actions entries must be non-empty strings');
        }
        return a;
      });
      const card = isObject(payload.card) ? (payload.card as JsonObject) : {};
      return {
        ...base,
        event: 'approval_required',
        payload: {state: 'interrupted', kind, allowed_actions, card},
      };
    }
    case 'text_delta': {
      const delta = requireString(payload, 'delta');
      return {...base, event: 'text_delta', payload: {delta}};
    }
    case 'run_completed': {
      if (payload.state !== 'completed') {
        rejectStatusAlias(String(payload.state ?? ''));
        throw new SseParseError("run_completed requires state='completed'");
      }
      return {...base, event: 'run_completed', payload: {state: 'completed'}};
    }
    case 'run_failed': {
      if (payload.state !== 'failed') {
        rejectStatusAlias(String(payload.state ?? ''));
        throw new SseParseError("run_failed requires state='failed'");
      }
      const error_code = requireString(payload, 'error_code');
      const summary = requireString(payload, 'summary');
      return {
        ...base,
        event: 'run_failed',
        payload: {state: 'failed', error_code, summary},
      };
    }
    default:
      throw new SseParseError(`unknown SSE event '${event}'`);
  }
}

/** Parse durable history page JSON; rejects role=tool and status aliases. */
export function parseHistoryPage(data: unknown): HistoryPage {
  if (!isObject(data)) {
    throw new SseParseError('history response must be an object');
  }
  if (!Array.isArray(data.items)) {
    throw new SseParseError('history.items must be an array');
  }
  const next_cursor =
    data.next_cursor === null || data.next_cursor === undefined
      ? null
      : typeof data.next_cursor === 'string'
        ? data.next_cursor
        : (() => {
            throw new SseParseError('next_cursor must be string or null');
          })();

  const items = data.items.map((item, index) =>
    parseChatMessageView(item, `items[${index}]`),
  );
  return {items, next_cursor};
}

function parseChatMessageView(raw: unknown, path: string): ChatMessageView {
  if (!isObject(raw)) {
    throw new SseParseError(`${path} must be an object`);
  }
  const id = requireUuid(raw, 'id');
  const role = requireString(raw, 'role');
  if (role === 'tool') {
    throw new SseParseError('history must not contain role=tool messages');
  }
  if (role !== 'user' && role !== 'assistant' && role !== 'system') {
    throw new SseParseError(`${path}.role invalid`);
  }
  if (typeof raw.content !== 'string') {
    throw new SseParseError(`${path}.content must be a string`);
  }
  const structured_payload =
    raw.structured_payload === null || raw.structured_payload === undefined
      ? null
      : isObject(raw.structured_payload)
        ? (raw.structured_payload as JsonObject)
        : (() => {
            throw new SseParseError(`${path}.structured_payload invalid`);
          })();
  const created_at = requireString(raw, 'created_at');
  const updated_at = requireString(raw, 'updated_at');
  const run =
    raw.run === null || raw.run === undefined
      ? null
      : parseAgentRunView(raw.run, `${path}.run`);
  return {
    id,
    role,
    content: raw.content,
    structured_payload,
    created_at,
    updated_at,
    run,
  };
}

function parseAgentRunView(raw: unknown, path: string): AgentRunView {
  if (!isObject(raw)) {
    throw new SseParseError(`${path} must be an object`);
  }
  const id = requireUuid(raw, 'id');
  const user_message_id = requireUuid(raw, 'user_message_id');
  const state = asRunState(raw.state);
  const pending_approval =
    raw.pending_approval === null || raw.pending_approval === undefined
      ? null
      : isObject(raw.pending_approval)
        ? (raw.pending_approval as JsonObject)
        : (() => {
            throw new SseParseError(`${path}.pending_approval invalid`);
          })();
  const error_code =
    raw.error_code === null || raw.error_code === undefined
      ? null
      : typeof raw.error_code === 'string'
        ? raw.error_code
        : (() => {
            throw new SseParseError(`${path}.error_code invalid`);
          })();
  const completed_at =
    raw.completed_at === null || raw.completed_at === undefined
      ? null
      : typeof raw.completed_at === 'string'
        ? raw.completed_at
        : (() => {
            throw new SseParseError(`${path}.completed_at invalid`);
          })();
  const created_at = requireString(raw, 'created_at');
  const updated_at = requireString(raw, 'updated_at');
  if (!Array.isArray(raw.tool_executions)) {
    throw new SseParseError(`${path}.tool_executions must be an array`);
  }
  const tool_executions = raw.tool_executions.map((t, i) =>
    parseToolExecutionView(t, `${path}.tool_executions[${i}]`),
  );
  return {
    id,
    user_message_id,
    state,
    pending_approval,
    error_code,
    completed_at,
    created_at,
    updated_at,
    tool_executions,
  };
}

function parseToolExecutionView(raw: unknown, path: string): ToolExecutionView {
  if (!isObject(raw)) {
    throw new SseParseError(`${path} must be an object`);
  }
  const status = asToolStatus(raw.status);
  return {
    id: requireUuid(raw, 'id'),
    tool_call_id: requireString(raw, 'tool_call_id'),
    tool_name: requireString(raw, 'tool_name'),
    status,
    duration_ms:
      raw.duration_ms === null || raw.duration_ms === undefined
        ? null
        : typeof raw.duration_ms === 'number'
          ? raw.duration_ms
          : (() => {
              throw new SseParseError(`${path}.duration_ms invalid`);
            })(),
    error_code:
      raw.error_code === null || raw.error_code === undefined
        ? null
        : typeof raw.error_code === 'string'
          ? raw.error_code
          : (() => {
              throw new SseParseError(`${path}.error_code invalid`);
            })(),
    result:
      raw.result === null || raw.result === undefined
        ? null
        : (raw.result as ToolResult),
    arguments_summary:
      raw.arguments_summary === null || raw.arguments_summary === undefined
        ? null
        : isObject(raw.arguments_summary)
          ? (raw.arguments_summary as JsonObject)
          : null,
    created_at: requireString(raw, 'created_at'),
    updated_at: requireString(raw, 'updated_at'),
  };
}
