/**
 * Typed chat transport: history hydration + turn/resume SSE streams.
 * Uses only the three approved FastAPI paths via `readPublicConfig().apiBaseUrl`.
 */

import { readPublicConfig } from "../../app/env";
import { createSSEParser } from "../../lib/sse/parser";
import {
  CHAT_API_PATHS,
  isTerminalSSEEvent,
  parseChatSSEData,
  parseHistoryResponse,
  type ChatSSEEvent,
  type HistoryResponse,
  type ResumeRequest,
  type TurnRequest,
} from "./contracts";

export class ChatApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message?: string) {
    super(message ?? code);
    this.name = "ChatApiError";
    this.status = status;
    this.code = code;
  }
}

export interface StreamHandlers {
  readonly onEvent: (event: ChatSSEEvent) => void;
  /** Fired when the stream ends without a terminal event (and not aborted). */
  readonly onDisconnect?: () => void;
  /** Fired when AbortSignal aborts the in-flight request/stream. */
  readonly onAbort?: () => void;
  readonly onError?: (error: unknown) => void;
}

export interface HistoryQuery {
  readonly limit?: number;
  readonly signal?: AbortSignal;
  /** Optional base URL override for tests; production uses VITE_API_BASE_URL. */
  readonly baseUrl?: string;
}

export interface StreamOptions {
  readonly signal?: AbortSignal;
  readonly baseUrl?: string;
  /** Injected fetch for tests. */
  readonly fetchImpl?: typeof fetch;
}

function resolveBaseUrl(override?: string): string {
  const raw = override ?? readPublicConfig().apiBaseUrl;
  return raw.replace(/\/+$/, "");
}

function joinUrl(baseUrl: string, path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

async function readErrorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail;
    }
  } catch {
    // ignore non-JSON error bodies
  }
  return `http_${response.status}`;
}

/**
 * GET /api/chat/history — hydrate durable conversation messages.
 */
export async function fetchChatHistory(
  query: HistoryQuery = {},
): Promise<HistoryResponse> {
  const baseUrl = resolveBaseUrl(query.baseUrl);
  const url = new URL(joinUrl(baseUrl, CHAT_API_PATHS.history));
  if (query.limit !== undefined) {
    url.searchParams.set("limit", String(query.limit));
  }

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: { Accept: "application/json" },
    signal: query.signal,
  });

  if (!response.ok) {
    const code = await readErrorCode(response);
    throw new ChatApiError(response.status, code);
  }

  const json: unknown = await response.json();
  return parseHistoryResponse(json);
}

async function consumeSSEResponse(
  response: Response,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.body) {
    throw new ChatApiError(response.status, "empty_body", "SSE response has no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSSEParser();
  let sawTerminal = false;
  let aborted = false;

  const onAbort = (): void => {
    aborted = true;
    void reader.cancel().catch(() => undefined);
  };

  if (signal) {
    if (signal.aborted) {
      onAbort();
      handlers.onAbort?.();
      return;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  }

  const emitFrameData = (data: string): void => {
    if (!data) {
      return;
    }
    const event = parseChatSSEData(data);
    handlers.onEvent(event);
    if (isTerminalSSEEvent(event)) {
      sawTerminal = true;
    }
    // Interrupt streams end at approval_required without a terminal event.
    if (event.event === "approval_required") {
      sawTerminal = true;
    }
  };

  try {
    for (;;) {
      if (aborted || signal?.aborted) {
        handlers.onAbort?.();
        return;
      }
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      const chunk = decoder.decode(value, { stream: true });
      for (const frame of parser.push(chunk)) {
        emitFrameData(frame.data);
      }
    }

    const tail = decoder.decode();
    if (tail) {
      for (const frame of parser.push(tail)) {
        emitFrameData(frame.data);
      }
    }
    for (const frame of parser.finish()) {
      emitFrameData(frame.data);
    }

    if (aborted || signal?.aborted) {
      handlers.onAbort?.();
      return;
    }
    if (!sawTerminal) {
      handlers.onDisconnect?.();
    }
  } catch (error) {
    if (aborted || signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) {
      handlers.onAbort?.();
      return;
    }
    handlers.onError?.(error);
    throw error;
  } finally {
    if (signal) {
      signal.removeEventListener("abort", onAbort);
    }
    try {
      reader.releaseLock();
    } catch {
      // already released
    }
  }
}

async function postSSE(
  path: string,
  body: unknown,
  handlers: StreamHandlers,
  options: StreamOptions = {},
): Promise<void> {
  const baseUrl = resolveBaseUrl(options.baseUrl);
  const fetchImpl = options.fetchImpl ?? fetch;
  const url = joinUrl(baseUrl, path);

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (error) {
    if (
      options.signal?.aborted ||
      (error instanceof DOMException && error.name === "AbortError")
    ) {
      handlers.onAbort?.();
      return;
    }
    handlers.onError?.(error);
    throw error;
  }

  if (!response.ok) {
    const code = await readErrorCode(response);
    const err = new ChatApiError(response.status, code);
    handlers.onError?.(err);
    throw err;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream") && !contentType.includes("text/plain")) {
    // Some test fakes omit content-type; still try to stream if body exists.
    if (!response.body) {
      const err = new ChatApiError(
        response.status,
        "invalid_content_type",
        `expected text/event-stream, got ${contentType}`,
      );
      handlers.onError?.(err);
      throw err;
    }
  }

  // Stream-consumption errors (malformed JSON, contract validation, read
  // failures) are notified exactly once inside consumeSSEResponse, then rethrown.
  // Do not re-notify here — callers must receive a single onError per failure.
  await consumeSSEResponse(response, handlers, options.signal);
}

/**
 * POST /api/chat/turns — start a user turn and stream validated SSE events.
 */
export async function streamChatTurn(
  body: TurnRequest,
  handlers: StreamHandlers,
  options: StreamOptions = {},
): Promise<void> {
  const payload = {
    text: body.text,
    attachment_ids: body.attachment_ids ? [...body.attachment_ids] : [],
    idempotency_key: body.idempotency_key,
  };
  await postSSE(CHAT_API_PATHS.turns, payload, handlers, options);
}

/**
 * POST /api/chat/runs/{run_id}/resume — resume an interrupted run on the same identity.
 */
export async function streamChatResume(
  runId: string,
  body: ResumeRequest,
  handlers: StreamHandlers,
  options: StreamOptions = {},
): Promise<void> {
  const payload = {
    action: body.action,
    idempotency_key: body.idempotency_key,
    correction_text: body.correction_text ?? null,
  };
  await postSSE(CHAT_API_PATHS.resume(runId), payload, handlers, options);
}

/** Approved path helpers for tests and callers. */
export function chatHistoryUrl(baseUrl?: string, limit?: number): string {
  const url = new URL(joinUrl(resolveBaseUrl(baseUrl), CHAT_API_PATHS.history));
  if (limit !== undefined) {
    url.searchParams.set("limit", String(limit));
  }
  return url.toString();
}

export function chatTurnsUrl(baseUrl?: string): string {
  return joinUrl(resolveBaseUrl(baseUrl), CHAT_API_PATHS.turns);
}

export function chatResumeUrl(runId: string, baseUrl?: string): string {
  return joinUrl(resolveBaseUrl(baseUrl), CHAT_API_PATHS.resume(runId));
}
