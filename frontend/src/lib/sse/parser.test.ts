/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import { createSSEParser, parseSSEText } from "./parser";

describe("createSSEParser", () => {
  it("parses a complete single-frame event", () => {
    const text =
      'event: run_started\nid: e1\ndata: {"event":"run_started"}\n\n';
    const frames = parseSSEText(text);
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({
      event: "run_started",
      id: "e1",
      data: '{"event":"run_started"}',
      retry: null,
    });
  });

  it("handles fragmented frames across chunk boundaries", () => {
    const parser = createSSEParser();
    const part1 = 'event: text_delta\nid: d1\ndata: {"event":"text_delta","pay';
    const part2 = 'load":{"delta":"Hel"}}\n\n';
    expect(parser.push(part1)).toEqual([]);
    const frames = parser.push(part2);
    expect(frames).toHaveLength(1);
    expect(frames[0]?.id).toBe("d1");
    expect(frames[0]?.data).toContain('"delta":"Hel"');
  });

  it("joins multiline data fields with newline", () => {
    const text = "data: line one\ndata: line two\ndata: line three\n\n";
    const frames = parseSSEText(text);
    expect(frames).toHaveLength(1);
    expect(frames[0]?.data).toBe("line one\nline two\nline three");
  });

  it("strips optional space after colon", () => {
    const frames = parseSSEText("data: hello\n\n");
    expect(frames[0]?.data).toBe("hello");
  });

  it("ignores comment lines", () => {
    const frames = parseSSEText(": keep-alive\ndata: x\n\n");
    expect(frames).toHaveLength(1);
    expect(frames[0]?.data).toBe("x");
  });

  it("parses multiple consecutive frames", () => {
    const text =
      "data: {\"a\":1}\n\n" +
      "event: text_delta\ndata: {\"b\":2}\n\n" +
      "id: last\ndata: {\"c\":3}\n\n";
    const frames = parseSSEText(text);
    expect(frames).toHaveLength(3);
    expect(frames[0]?.data).toBe('{"a":1}');
    expect(frames[1]?.event).toBe("text_delta");
    expect(frames[2]?.id).toBe("last");
  });

  it("parses retry field when numeric", () => {
    const frames = parseSSEText("retry: 3000\ndata: ok\n\n");
    expect(frames[0]?.retry).toBe(3000);
  });

  it("finish() flushes a trailing event without blank line", () => {
    const parser = createSSEParser();
    expect(parser.push("data: trailing")).toEqual([]);
    const frames = parser.finish();
    expect(frames).toHaveLength(1);
    expect(frames[0]?.data).toBe("trailing");
  });

  it("reset() clears partial buffer", () => {
    const parser = createSSEParser();
    parser.push("data: partial");
    parser.reset();
    const frames = parser.push("data: full\n\n");
    expect(frames).toHaveLength(1);
    expect(frames[0]?.data).toBe("full");
  });

  it("handles CRLF line endings", () => {
    const frames = parseSSEText("data: crlf\r\n\r\n");
    expect(frames).toHaveLength(1);
    expect(frames[0]?.data).toBe("crlf");
  });

  it("matches backend wire chunk shape", () => {
    const data = JSON.stringify({
      event: "run_started",
      event_id: "ev-1",
      run_id: "11111111-1111-1111-1111-111111111111",
      timestamp: "2026-01-01T00:00:00+00:00",
      payload: {},
    });
    const wire = `event: run_started\nid: ev-1\ndata: ${data}\n\n`;
    const frames = parseSSEText(wire);
    expect(frames).toHaveLength(1);
    expect(frames[0]?.event).toBe("run_started");
    expect(frames[0]?.id).toBe("ev-1");
    expect(JSON.parse(frames[0]!.data)).toMatchObject({
      event: "run_started",
      event_id: "ev-1",
    });
  });
});
