/**
 * Consume a fetch Response body as an SSE event stream.
 * Does not infer run completion on disconnect or parse failure.
 */

import type {SseEvent, SseParseError} from '../../features/chat/types';
import {
  frameToEvent,
  IncrementalSseParser,
  type SseWireFrame,
  type SseParseResult,
} from './parser';

export type TypedSseParseResult<T> =
  | {ok: true; event: T}
  | {ok: false; error: SseParseError; frame: SseWireFrame};

export type TypedStreamHandlers<T> = {
  onEvent: (event: T) => void;
  onMalformed?: (result: Extract<TypedSseParseResult<T>, {ok: false}>) => void;
  onDisconnected?: () => void;
  onHttpError?: (status: number, body: string) => void;
};

export type StreamHandlers = {
  onEvent: (event: SseEvent) => void;
  /** Malformed frame — caller must not mark the run complete. */
  onMalformed?: (result: Extract<SseParseResult, {ok: false}>) => void;
  /** Network/body ended without a terminal run event. */
  onDisconnected?: () => void;
  onHttpError?: (status: number, body: string) => void;
};

export class StreamHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`HTTP ${status}`);
    this.name = 'StreamHttpError';
    this.status = status;
    this.body = body;
  }
}

/**
 * Read `response` as SSE until the body ends or abort.
 * Invokes onEvent for each validated event; never invents run_completed.
 */
export async function consumeSseResponse(
  response: Response,
  handlers: StreamHandlers,
  signal?: AbortSignal,
  options: {
    parseFrame?: (frame: SseWireFrame) => SseParseResult;
    isTerminal?: (event: SseEvent) => boolean;
  } = {},
): Promise<void> {
  return consumeTypedSseResponse(
    response,
    handlers,
    options.parseFrame ?? frameToEvent,
    options.isTerminal ?? ((event) => event.event === 'run_completed' || event.event === 'run_failed'),
    signal,
  );
}

export async function consumeTypedSseResponse<T>(
  response: Response,
  handlers: TypedStreamHandlers<T>,
  parseFrame: (frame: SseWireFrame) => TypedSseParseResult<T>,
  isTerminal: (event: T) => boolean,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    handlers.onHttpError?.(response.status, body);
    throw new StreamHttpError(response.status, body);
  }
  if (!response.body) {
    handlers.onDisconnected?.();
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new IncrementalSseParser();
  let sawTerminal = false;

  const handleResults = (results: TypedSseParseResult<T>[]): void => {
    for (const result of results) {
      if (!result.ok) {
        handlers.onMalformed?.(result);
        continue;
      }
      if (isTerminal(result.event)) sawTerminal = true;
      handlers.onEvent(result.event);
    }
  };

  try {
    for (;;) {
      if (signal?.aborted) {
        await reader.cancel().catch(() => undefined);
        if (!sawTerminal) {
          handlers.onDisconnected?.();
        }
        return;
      }
      const {done, value} = await reader.read();
      if (done) {
        const flushed = parser.flush().map(parseFrame);
        handleResults(flushed);
        if (!sawTerminal) {
          handlers.onDisconnected?.();
        }
        return;
      }
      const text = decoder.decode(value, {stream: true});
      handleResults(parser.feed(text).map(parseFrame));
    }
  } catch (err) {
    if (signal?.aborted) {
      if (!sawTerminal) {
        handlers.onDisconnected?.();
      }
      return;
    }
    if (!sawTerminal) {
      handlers.onDisconnected?.();
    }
    throw err;
  }
}
