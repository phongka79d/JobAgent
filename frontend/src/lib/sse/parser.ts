/**
 * Incremental SSE wire parser for FastAPI-framed chat streams.
 * Handles split frames across chunk boundaries; ignores comments and empty fields.
 */

import {parseSseEventData, type SseEvent, SseParseError} from '../../features/chat/types';

export interface SseWireFrame {
  id: string | null;
  event: string | null;
  data: string;
}

export type SseParseResult =
  | {ok: true; event: SseEvent}
  | {ok: false; error: SseParseError; frame: SseWireFrame};

/**
 * Stateful incremental parser: feed text chunks, receive completed frames.
 */
export class IncrementalSseParser {
  private buffer = '';

  /** Push a text chunk; return fully assembled frames (may be empty). */
  feed(chunk: string): SseWireFrame[] {
    this.buffer += chunk;
    const frames: SseWireFrame[] = [];
    // SSE frames end with a blank line (\n\n or \r\n\r\n).
    for (;;) {
      const normalized = this.buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
      this.buffer = normalized;
      const sep = this.buffer.indexOf('\n\n');
      if (sep === -1) {
        break;
      }
      const raw = this.buffer.slice(0, sep);
      this.buffer = this.buffer.slice(sep + 2);
      const frame = parseWireBlock(raw);
      if (frame !== null) {
        frames.push(frame);
      }
    }
    return frames;
  }

  /** Flush remaining buffer as a frame if it has data (stream end). */
  flush(): SseWireFrame[] {
    const rest = this.buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd();
    this.buffer = '';
    if (rest === '') {
      return [];
    }
    const frame = parseWireBlock(rest);
    return frame === null ? [] : [frame];
  }

  reset(): void {
    this.buffer = '';
  }
}

function parseWireBlock(block: string): SseWireFrame | null {
  if (block.trim() === '') {
    return null;
  }
  let id: string | null = null;
  let event: string | null = null;
  const dataLines: string[] = [];

  for (const line of block.split('\n')) {
    if (line === '' || line.startsWith(':')) {
      continue;
    }
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    // Optional single leading space after colon (SSE spec).
    if (value.startsWith(' ')) {
      value = value.slice(1);
    }
    switch (field) {
      case 'id':
        id = value;
        break;
      case 'event':
        event = value;
        break;
      case 'data':
        dataLines.push(value);
        break;
      default:
        // ignore retry and unknown fields
        break;
    }
  }

  if (dataLines.length === 0) {
    return null;
  }
  return {id, event, data: dataLines.join('\n')};
}

/** Parse one wire frame into a typed event or a safe parse failure. */
export function frameToEvent(frame: SseWireFrame): SseParseResult {
  let json: unknown;
  try {
    json = JSON.parse(frame.data) as unknown;
  } catch {
    return {
      ok: false,
      error: new SseParseError('SSE data is not valid JSON'),
      frame,
    };
  }
  try {
    const event = parseSseEventData(json);
    if (frame.event !== null && frame.event !== event.event) {
      return {
        ok: false,
        error: new SseParseError(
          `wire event name '${frame.event}' mismatches data event '${event.event}'`,
        ),
        frame,
      };
    }
    if (frame.id !== null && frame.id.toLowerCase() !== event.event_id) {
      return {
        ok: false,
        error: new SseParseError(
          `wire id '${frame.id}' mismatches event_id '${event.event_id}'`,
        ),
        frame,
      };
    }
    return {ok: true, event};
  } catch (err) {
    const error =
      err instanceof SseParseError
        ? err
        : new SseParseError(err instanceof Error ? err.message : 'parse failed');
    return {ok: false, error, frame};
  }
}

/** Convenience: feed chunk text and map complete frames to parse results. */
export function parseSseChunk(
  parser: IncrementalSseParser,
  chunk: string,
): SseParseResult[] {
  return parser.feed(chunk).map(frameToEvent);
}
