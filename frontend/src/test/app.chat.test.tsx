import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import type { ChatSSEEvent } from "../features/chat/contracts";

function sseFrame(event: ChatSSEEvent): string {
  return `event: ${event.event}\nid: ${event.event_id}\ndata: ${JSON.stringify(event)}\n\n`;
}

function streamResponse(body: string): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(body));
        controller.close();
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  );
}

function noneProfileBody(): string {
  return JSON.stringify({
    state: "none",
    profile: null,
    preferences: null,
    active_attachment: null,
  });
}

function submitComposer(text: string): void {
  const textbox = screen.getByRole("textbox");
  textbox.textContent = text;
  fireEvent.input(textbox);
  fireEvent.keyDown(textbox, { key: "Enter" });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App chat first screen", () => {
  it("renders the chat experience with profile sidebar, not a landing placeholder", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/chat/history")) {
          return new Response(JSON.stringify({ messages: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/profile") && !url.includes("/cv")) {
          return new Response(noneProfileBody(), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("chat-empty-state")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });

    expect(
      screen.getByRole("heading", { name: /Start a conversation/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/product workflows are intentionally disabled/i),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByText(/Message JobAgent/i)).toBeInTheDocument();
  });

  it("hydrates history and streams a turn through the App shell", async () => {
    const runId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/chat/history")) {
        return new Response(
          JSON.stringify({
            messages: [
              {
                role: "user",
                content: "Hydrated user",
                created_at: "2026-01-01T00:00:00.000Z",
                structured_payload: null,
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/profile") && !url.includes("/cv")) {
        return new Response(noneProfileBody(), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/chat/turns") && init?.method === "POST") {
        const events: ChatSSEEvent[] = [
          {
            event: "run_started",
            event_id: "e1",
            run_id: runId,
            timestamp: "2026-01-01T00:01:00.000Z",
            payload: {},
          },
          {
            event: "text_delta",
            event_id: "e2",
            run_id: runId,
            timestamp: "2026-01-01T00:01:01.000Z",
            payload: { delta: "Streamed " },
          },
          {
            event: "text_delta",
            event_id: "e3",
            run_id: runId,
            payload: { delta: "reply" },
            timestamp: "2026-01-01T00:01:02.000Z",
          },
          {
            event: "run_completed",
            event_id: "e4",
            run_id: runId,
            timestamp: "2026-01-01T00:01:03.000Z",
            payload: {},
          },
        ];
        return streamResponse(events.map(sseFrame).join(""));
      }
      return new Response("not found", { status: 404 });
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Hydrated user")).toBeInTheDocument();
    });

    submitComposer("New turn");

    await waitFor(() => {
      expect(screen.getByText("Streamed reply")).toBeInTheDocument();
    });

    const turnCalls = fetchMock.mock.calls.filter(
      ([u, init]) =>
        String(u).includes("/api/chat/turns") &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(turnCalls.length).toBe(1);

    for (const [u] of fetchMock.mock.calls) {
      const url = String(u);
      expect(url).toMatch(
        /\/api\/(chat\/(history|turns|runs\/)|profile(?:\/cv)?)/,
      );
      expect(url).not.toMatch(/job|match|openai|shopaikey|attachments/i);
    }

    expect(document.body.textContent).not.toMatch(
      /sk-live|Authorization:|Traceback|raw_args/i,
    );
  });
});
