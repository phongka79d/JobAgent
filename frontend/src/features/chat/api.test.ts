/**
 * @vitest-environment node
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  chatHistoryUrl,
  chatResumeUrl,
  chatTurnsUrl,
  fetchChatHistory,
  streamChatResume,
  streamChatTurn,
  ChatApiError,
} from "./api";
import { CHAT_API_PATHS, type ChatSSEEvent } from "./contracts";

const BASE = "http://127.0.0.1:8000";
const RUN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

function sseFrame(event: ChatSSEEvent): string {
  const data = JSON.stringify(event);
  return `event: ${event.event}\nid: ${event.event_id}\ndata: ${data}\n\n`;
}

function streamResponse(body: string, init?: ResponseInit): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(body));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    ...init,
  });
}

function chunkedStreamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[i]));
      i += 1;
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("chat API path helpers", () => {
  it("builds only the three approved FastAPI chat paths", () => {
    expect(chatHistoryUrl(BASE)).toBe(`${BASE}/api/chat/history`);
    expect(chatHistoryUrl(BASE, 50)).toBe(`${BASE}/api/chat/history?limit=50`);
    expect(chatTurnsUrl(BASE)).toBe(`${BASE}/api/chat/turns`);
    expect(chatResumeUrl(RUN, BASE)).toBe(
      `${BASE}/api/chat/runs/${RUN}/resume`,
    );
    expect(CHAT_API_PATHS.history).toBe("/api/chat/history");
    expect(CHAT_API_PATHS.turns).toBe("/api/chat/turns");
  });
});

describe("fetchChatHistory", () => {
  it("hydrates durable history from GET /api/chat/history", async () => {
    const payload = {
      messages: [
        {
          role: "user",
          content: "hello",
          created_at: "2026-01-01T00:00:00+00:00",
          structured_payload: null,
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        expect(String(input)).toBe(`${BASE}/api/chat/history?limit=10`);
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const result = await fetchChatHistory({ baseUrl: BASE, limit: 10 });
    expect(result.messages).toHaveLength(1);
    expect(result.messages[0]?.content).toBe("hello");
  });

  it("throws ChatApiError on non-OK history response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "history_failed" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(fetchChatHistory({ baseUrl: BASE })).rejects.toMatchObject({
      name: "ChatApiError",
      status: 500,
      code: "history_failed",
    } satisfies Partial<ChatApiError>);
  });
});

describe("streamChatTurn", () => {
  it("POSTs turn body and parses fragmented SSE frames for every event type", async () => {
    const events: ChatSSEEvent[] = [
      {
        event: "run_started",
        event_id: "1",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: {},
      },
      {
        event: "assistant_status",
        event_id: "2",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: { status: "working", message: null },
      },
      {
        event: "tool_started",
        event_id: "3",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: { tool_call_id: "t1", label: "Echo", status: "running" },
      },
      {
        event: "tool_completed",
        event_id: "4",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: {
          tool_call_id: "t1",
          label: "Echo",
          status: "complete",
          duration_ms: 5,
          outcome: "done",
        },
      },
      {
        event: "text_delta",
        event_id: "5",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: { delta: "Hi" },
      },
      {
        event: "run_completed",
        event_id: "6",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: {},
      },
    ];

    const full = events.map(sseFrame).join("");
    const mid = Math.floor(full.length / 2);
    const chunks = [full.slice(0, mid), full.slice(mid)];

    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(`${BASE}/api/chat/turns`);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        text: "hello",
        attachment_ids: [],
        idempotency_key: "turn-1",
      });
      return chunkedStreamResponse(chunks);
    });

    const received: ChatSSEEvent[] = [];
    await streamChatTurn(
      { text: "hello", idempotency_key: "turn-1" },
      { onEvent: (e) => received.push(e) },
      { baseUrl: BASE, fetchImpl },
    );

    expect(received.map((e) => e.event)).toEqual([
      "run_started",
      "assistant_status",
      "tool_started",
      "tool_completed",
      "text_delta",
      "run_completed",
    ]);
  });

  it("supports multiline data frames in the stream", async () => {
    // Split JSON on a token boundary so joined lines remain valid JSON
    // (SSE joins multiple data: lines with "\n", which is legal whitespace).
    const line1 =
      '{"event":"text_delta","event_id":"m1","run_id":"' +
      RUN +
      '","timestamp":"2026-01-01T00:00:00+00:00",';
    const line2 = '"payload":{"delta":"x"}}';
    const body = `event: text_delta\nid: m1\ndata: ${line1}\ndata: ${line2}\n\n`;

    const fetchImpl = vi.fn(async () => streamResponse(body));
    const received: ChatSSEEvent[] = [];
    // Stream ends without terminal → disconnect; still parse the event.
    let disconnected = false;
    await streamChatTurn(
      { text: "t", idempotency_key: "k" },
      {
        onEvent: (e) => received.push(e),
        onDisconnect: () => {
          disconnected = true;
        },
      },
      { baseUrl: BASE, fetchImpl },
    );
    expect(received).toHaveLength(1);
    expect(received[0]?.event).toBe("text_delta");
    if (received[0]?.event === "text_delta") {
      expect(received[0].payload.delta).toBe("x");
    }
    expect(disconnected).toBe(true);
  });

  it("fires onDisconnect when stream ends without terminal event", async () => {
    const body = sseFrame({
      event: "run_started",
      event_id: "1",
      run_id: RUN,
      timestamp: "2026-01-01T00:00:00+00:00",
      payload: {},
    });
    const fetchImpl = vi.fn(async () => streamResponse(body));
    let disconnected = false;
    await streamChatTurn(
      { text: "t", idempotency_key: "k" },
      {
        onEvent: () => undefined,
        onDisconnect: () => {
          disconnected = true;
        },
      },
      { baseUrl: BASE, fetchImpl },
    );
    expect(disconnected).toBe(true);
  });

  it("does not fire onDisconnect after terminal run_completed", async () => {
    const body =
      sseFrame({
        event: "run_started",
        event_id: "1",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: {},
      }) +
      sseFrame({
        event: "run_completed",
        event_id: "2",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: {},
      });
    const fetchImpl = vi.fn(async () => streamResponse(body));
    let disconnected = false;
    await streamChatTurn(
      { text: "t", idempotency_key: "k" },
      {
        onEvent: () => undefined,
        onDisconnect: () => {
          disconnected = true;
        },
      },
      { baseUrl: BASE, fetchImpl },
    );
    expect(disconnected).toBe(false);
  });

  it("treats approval_required as a clean stream end (no disconnect)", async () => {
    const body =
      sseFrame({
        event: "run_started",
        event_id: "1",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: {},
      }) +
      sseFrame({
        event: "approval_required",
        event_id: "2",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: { summary: "Approve?", approval_kind: null },
      });
    const fetchImpl = vi.fn(async () => streamResponse(body));
    let disconnected = false;
    const received: string[] = [];
    await streamChatTurn(
      { text: "t", idempotency_key: "k" },
      {
        onEvent: (e) => received.push(e.event),
        onDisconnect: () => {
          disconnected = true;
        },
      },
      { baseUrl: BASE, fetchImpl },
    );
    expect(received).toEqual(["run_started", "approval_required"]);
    expect(disconnected).toBe(false);
  });

  it("abort signal triggers onAbort cleanup and stops consumption", async () => {
    const controller = new AbortController();
    const encoder = new TextEncoder();
    let pullCount = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(ctrl) {
        pullCount += 1;
        if (pullCount === 1) {
          ctrl.enqueue(
            encoder.encode(
              sseFrame({
                event: "run_started",
                event_id: "1",
                run_id: RUN,
                timestamp: "2026-01-01T00:00:00+00:00",
                payload: {},
              }),
            ),
          );
          controller.abort();
          return;
        }
        // Should not keep producing after abort in normal flow
        ctrl.close();
      },
    });

    const fetchImpl = vi.fn(
      async () =>
        new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
    );

    let aborted = false;
    const events: string[] = [];
    await streamChatTurn(
      { text: "t", idempotency_key: "k" },
      {
        onEvent: (e) => events.push(e.event),
        onAbort: () => {
          aborted = true;
        },
      },
      { baseUrl: BASE, fetchImpl, signal: controller.signal },
    );
    expect(aborted).toBe(true);
  });

  it("propagates HTTP errors as ChatApiError", async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "invalid_turn" }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }),
    );
    await expect(
      streamChatTurn(
        { text: "t", idempotency_key: "k" },
        { onEvent: () => undefined },
        { baseUrl: BASE, fetchImpl },
      ),
    ).rejects.toMatchObject({ status: 400, code: "invalid_turn" });
  });

  it("notifies onError exactly once for malformed SSE frame data and still rejects", async () => {
    const body =
      "event: text_delta\nid: bad1\ndata: {not-valid-json\n\n";
    const fetchImpl = vi.fn(async () => streamResponse(body));
    const onError = vi.fn();

    await expect(
      streamChatTurn(
        { text: "t", idempotency_key: "k" },
        { onEvent: () => undefined, onError },
        { baseUrl: BASE, fetchImpl },
      ),
    ).rejects.toMatchObject({ name: "ChatContractError" });

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0]?.[0]).toMatchObject({
      name: "ChatContractError",
      code: "invalid_json",
    });
  });
});

describe("streamChatResume", () => {
  it("POSTs resume to the run-scoped path", async () => {
    const body = sseFrame({
      event: "run_started",
      event_id: "1",
      run_id: RUN,
      timestamp: "2026-01-01T00:00:00+00:00",
      payload: {},
    }) +
      sseFrame({
        event: "run_completed",
        event_id: "2",
        run_id: RUN,
        timestamp: "2026-01-01T00:00:00+00:00",
        payload: {},
      });

    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(`${BASE}/api/chat/runs/${RUN}/resume`);
      expect(JSON.parse(String(init?.body))).toEqual({
        action: "approve",
        idempotency_key: "resume-1",
        correction_text: null,
      });
      return streamResponse(body);
    });

    const events: string[] = [];
    await streamChatResume(
      RUN,
      { action: "approve", idempotency_key: "resume-1" },
      { onEvent: (e) => events.push(e.event) },
      { baseUrl: BASE, fetchImpl },
    );
    expect(events).toEqual(["run_started", "run_completed"]);
  });
});
