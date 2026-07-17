/**
 * Chat API client for Plan 3 history / turn / resume endpoints.
 * Reads only VITE_API_BASE_URL; never touches provider, database, or graph.
 */

import {
  parseHistoryPage,
  type HistoryPage,
  type SseEvent,
} from '../../features/chat/types';
import {
  consumeSseResponse,
  StreamHttpError,
  type StreamHandlers,
} from '../sse/stream';

export {StreamHttpError};

export class ChatApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly summary: string;

  constructor(status: number, code: string, summary: string) {
    super(summary);
    this.name = 'ChatApiError';
    this.status = status;
    this.code = code;
    this.summary = summary;
  }
}

/** Single environment boundary for the frontend HTTP origin. */
export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (typeof raw !== 'string' || raw.trim() === '') {
    throw new ChatApiError(
      0,
      'MISSING_API_BASE_URL',
      'VITE_API_BASE_URL is not configured',
    );
  }
  return raw.replace(/\/+$/, '');
}

/** Build an absolute API URL under the configured VITE_API_BASE_URL origin. */
export function apiUrl(path: string): string {
  const base = getApiBaseUrl();
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalized}`;
}

/** Map FastAPI-style error bodies to ChatApiError (shared by chat + profile). */
export function parseErrorBody(status: number, body: string): ChatApiError {
  try {
    const json = JSON.parse(body) as {
      detail?: {code?: string; summary?: string} | string;
    };
    if (json.detail && typeof json.detail === 'object') {
      const code =
        typeof json.detail.code === 'string'
          ? json.detail.code
          : 'HTTP_ERROR';
      const summary =
        typeof json.detail.summary === 'string'
          ? json.detail.summary
          : body.slice(0, 200) || `HTTP ${status}`;
      return new ChatApiError(status, code, summary);
    }
    if (typeof json.detail === 'string') {
      return new ChatApiError(status, 'HTTP_ERROR', json.detail);
    }
  } catch {
    // non-JSON body
  }
  return new ChatApiError(
    status,
    'HTTP_ERROR',
    body.slice(0, 200) || `HTTP ${status}`,
  );
}

export type HistoryQuery = {
  limit?: number;
  before?: string | null;
};

/** GET /api/chat/history → {items, next_cursor} */
export async function fetchChatHistory(
  query: HistoryQuery = {},
  signal?: AbortSignal,
): Promise<HistoryPage> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit));
  }
  if (query.before) {
    params.set('before', query.before);
  }
  const qs = params.toString();
  const url = apiUrl(`/api/chat/history${qs ? `?${qs}` : ''}`);
  const response = await fetch(url, {
    method: 'GET',
    headers: {Accept: 'application/json'},
    signal,
  });
  const text = await response.text();
  if (!response.ok) {
    throw parseErrorBody(response.status, text);
  }
  let json: unknown;
  try {
    json = JSON.parse(text) as unknown;
  } catch {
    throw new ChatApiError(response.status, 'INVALID_JSON', 'History body is not JSON');
  }
  return parseHistoryPage(json);
}

export type TurnRequest = {
  message: string;
  attachment_ids?: string[];
};

export type StreamCallbacks = {
  onEvent: (event: SseEvent) => void;
  onMalformed?: StreamHandlers['onMalformed'];
  onDisconnected?: () => void;
};

/**
 * POST /api/chat/turns and consume validated SSE.
 * Streamed HTTP failures surface as ChatApiError; mid-stream disconnect
 * invokes onDisconnected without inventing completion.
 */
export async function streamChatTurn(
  body: TurnRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl('/api/chat/turns'), {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message: body.message,
      attachment_ids: body.attachment_ids ?? [],
    }),
    signal,
  });
  await consumeWithMappedErrors(response, callbacks, signal);
}

/**
 * POST /api/chat/runs/{run_id}/resume and consume validated SSE.
 */
export async function streamChatResume(
  runId: string,
  action: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl(`/api/chat/runs/${runId}/resume`), {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({action}),
    signal,
  });
  await consumeWithMappedErrors(response, callbacks, signal);
}

/**
 * POST /api/cvs/{attachment_id}/reprocess and consume validated SSE.
 * Same consumeSseResponse / StreamCallbacks path as chat turns — no second stream.
 */
export async function streamCvReprocess(
  attachmentId: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/cvs/${encodeURIComponent(attachmentId)}/reprocess`),
    {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
      },
      signal,
    },
  );
  await consumeWithMappedErrors(response, callbacks, signal);
}

async function consumeWithMappedErrors(
  response: Response,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  try {
    await consumeSseResponse(
      response,
      {
        onEvent: callbacks.onEvent,
        onMalformed: callbacks.onMalformed,
        onDisconnected: callbacks.onDisconnected,
        onHttpError: (status, body) => {
          throw parseErrorBody(status, body);
        },
      },
      signal,
    );
  } catch (err) {
    if (err instanceof StreamHttpError) {
      throw parseErrorBody(err.status, err.body);
    }
    throw err;
  }
}
