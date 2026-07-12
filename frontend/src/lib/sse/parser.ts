/**
 * Incremental text/event-stream (SSE) frame parser.
 * No external EventSource dependency; works with fetch ReadableStream chunks.
 *
 * Supports:
 * - Fragmented frames across chunk boundaries
 * - Multiline `data:` fields joined with `\n` (SSE spec)
 * - `event:`, `id:`, `retry:`, and comment lines (`:`)
 */

export interface SSEFrame {
  /** Named event from `event:` field, if present. */
  readonly event: string | null;
  /** Last-event-id from `id:` field, if present. */
  readonly id: string | null;
  /** Joined data payload (empty string when data field omitted). */
  readonly data: string;
  /** Retry hint in milliseconds from `retry:`, if present and valid. */
  readonly retry: number | null;
}

export interface SSEParser {
  /** Feed a decoded UTF-8 text chunk; returns complete frames only. */
  push(chunk: string): SSEFrame[];
  /** Flush any trailing buffered event when the stream ends (no trailing blank line). */
  finish(): SSEFrame[];
  /** Clear internal buffer and field state. */
  reset(): void;
}

interface MutableFields {
  event: string | null;
  id: string | null;
  dataLines: string[];
  retry: number | null;
}

function emptyFields(): MutableFields {
  return {
    event: null,
    id: null,
    dataLines: [],
    retry: null,
  };
}

function dispatchFrame(fields: MutableFields): SSEFrame {
  return {
    event: fields.event,
    id: fields.id,
    data: fields.dataLines.join("\n"),
    retry: fields.retry,
  };
}

/**
 * Create a stateful SSE parser for one stream lifetime.
 */
export function createSSEParser(): SSEParser {
  let buffer = "";
  let fields = emptyFields();

  function processLine(line: string): SSEFrame | null {
    // SSE lines may end with \r from \r\n splits.
    if (line.endsWith("\r")) {
      line = line.slice(0, -1);
    }

    // Blank line → dispatch event.
    if (line === "") {
      // Per SSE: if no fields accumulated, ignore (keepalive-only blank).
      const hasContent =
        fields.event !== null ||
        fields.id !== null ||
        fields.dataLines.length > 0 ||
        fields.retry !== null;
      if (!hasContent) {
        return null;
      }
      const frame = dispatchFrame(fields);
      fields = emptyFields();
      return frame;
    }

    // Comment line.
    if (line.startsWith(":")) {
      return null;
    }

    let field: string;
    let value: string;
    const colon = line.indexOf(":");
    if (colon === -1) {
      field = line;
      value = "";
    } else {
      field = line.slice(0, colon);
      value = line.slice(colon + 1);
      // Optional single space after colon is stripped (SSE spec).
      if (value.startsWith(" ")) {
        value = value.slice(1);
      }
    }

    switch (field) {
      case "event":
        fields.event = value;
        break;
      case "id":
        // Null character in id is ignored per spec; treat as no-op for id.
        if (!value.includes("\0")) {
          fields.id = value;
        }
        break;
      case "data":
        fields.dataLines.push(value);
        break;
      case "retry": {
        if (/^\d+$/.test(value)) {
          fields.retry = Number.parseInt(value, 10);
        }
        break;
      }
      default:
        // Unknown fields ignored.
        break;
    }
    return null;
  }

  function consumeBuffer(completeOnly: boolean): SSEFrame[] {
    const out: SSEFrame[] = [];
    // Process line-by-line; keep incomplete trailing line in buffer.
    for (;;) {
      const nl = buffer.indexOf("\n");
      if (nl === -1) {
        if (!completeOnly && buffer.length > 0) {
          // Stream finished without a final newline: treat remaining as a line.
          const line = buffer;
          buffer = "";
          const frame = processLine(line);
          if (frame) {
            out.push(frame);
          }
          // Also dispatch if fields pending after stream end.
          const trailing = processLine("");
          if (trailing) {
            out.push(trailing);
          }
        }
        break;
      }
      const line = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 1);
      const frame = processLine(line);
      if (frame) {
        out.push(frame);
      }
    }
    return out;
  }

  return {
    push(chunk: string): SSEFrame[] {
      if (chunk.length === 0) {
        return [];
      }
      buffer += chunk;
      return consumeBuffer(true);
    },
    finish(): SSEFrame[] {
      const frames = consumeBuffer(false);
      // If fields remain without blank line, dispatch once.
      const hasContent =
        fields.event !== null ||
        fields.id !== null ||
        fields.dataLines.length > 0 ||
        fields.retry !== null;
      if (hasContent) {
        frames.push(dispatchFrame(fields));
        fields = emptyFields();
      }
      buffer = "";
      return frames;
    },
    reset(): void {
      buffer = "";
      fields = emptyFields();
    },
  };
}

/**
 * Parse a complete SSE text blob into frames (convenience for tests/sync use).
 */
export function parseSSEText(text: string): SSEFrame[] {
  const parser = createSSEParser();
  const frames = parser.push(text);
  const tail = parser.finish();
  return frames.concat(tail);
}
