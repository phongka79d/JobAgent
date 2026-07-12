/**
 * Full-path frontend transport proof (task 04A).
 *
 * Drives the real SSE client (`streamChatTurn` / `streamChatResume` / parser),
 * pure chat reducer, and ChatShell presentation with injected fetch fakes only.
 * Synthetic-tool and approval acceptance paths feed raw SSE frames through the
 * real client into reducer + ChatShell (no injected pre-parsed events).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  streamChatResume,
  streamChatTurn,
  type StreamHandlers,
  type StreamOptions,
} from "../features/chat/api";
import type {
  ChatSSEEvent,
  ResumeRequest,
  TurnRequest,
} from "../features/chat/contracts";
import { ChatShell } from "../features/chat/components/ChatShell";
import {
  chatReducer,
  createInitialChatState,
  isSendDisabled,
  type ChatState,
} from "../features/chat/reducer";

const RUN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const TS = "2026-01-01T12:00:00.000Z";
const BASE_URL = "http://localhost:8000";
const PROHIBITED_UI =
  /echo_label|Traceback|Authorization|api_key|SHOPAIKEY|sk-live|Bearer |RAW_ARG_SENTINEL/i;

function sseFrame(event: ChatSSEEvent): string {
  return `event: ${event.event}\nid: ${event.event_id}\ndata: ${JSON.stringify(event)}\n\n`;
}

function streamResponse(body: string, init?: ResponseInit): Response {
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
      ...init,
    },
  );
}

/**
 * Progressive SSE body: emit frames, optionally pause mid-stream so ChatShell
 * can observe live tool/approval UI while phase remains non-terminal.
 */
function progressiveStreamResponse(
  frames: readonly string[],
  holdAfterIndex: number,
  hold: Promise<void>,
): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      async start(controller) {
        for (let i = 0; i < frames.length; i += 1) {
          controller.enqueue(encoder.encode(frames[i]));
          if (i === holdAfterIndex) {
            await hold;
          }
        }
        controller.close();
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  );
}

function evt(
  partial: Omit<ChatSSEEvent, "event_id" | "timestamp" | "run_id"> & {
    event_id?: string;
    timestamp?: string;
    run_id?: string;
  },
): ChatSSEEvent {
  return {
    event_id: partial.event_id ?? crypto.randomUUID(),
    timestamp: partial.timestamp ?? TS,
    run_id: partial.run_id ?? RUN,
    ...partial,
  } as ChatSSEEvent;
}

function reduceAll(state: ChatState, events: ChatSSEEvent[]): ChatState {
  return events.reduce(
    (s, event) => chatReducer(s, { type: "SSE_EVENT", event }),
    state,
  );
}

function submitComposer(text: string): void {
  const textbox = screen.getByRole("textbox");
  textbox.textContent = text;
  fireEvent.input(textbox);
  fireEvent.keyDown(textbox, { key: "Enter" });
}

/** Real client wrappers: raw SSE → parser → handlers (used by ChatShell). */
function realClientApi(fetchImpl: typeof fetch) {
  return {
    fetchHistory: async () => ({ messages: [] as const }),
    streamTurn: (
      body: TurnRequest,
      handlers: StreamHandlers,
      opts?: StreamOptions,
    ) =>
      streamChatTurn(body, handlers, {
        ...opts,
        baseUrl: BASE_URL,
        fetchImpl,
      }),
    streamResume: (
      runId: string,
      body: ResumeRequest,
      handlers: StreamHandlers,
      opts?: StreamOptions,
    ) =>
      streamChatResume(runId, body, handlers, {
        ...opts,
        baseUrl: BASE_URL,
        fetchImpl,
      }),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("chat transport integration (client + reducer + shell)", () => {
  it("streams ordinary completion through real SSE client into reducer state", async () => {
    const sequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "e1", payload: {} }),
      evt({
        event: "assistant_status",
        event_id: "e2",
        payload: { status: "working", message: null },
      }),
      evt({
        event: "text_delta",
        event_id: "e3",
        payload: { delta: "Hello " },
      }),
      evt({
        event: "text_delta",
        event_id: "e4",
        payload: { delta: "world" },
      }),
      evt({ event: "run_completed", event_id: "e5", payload: {} }),
    ];

    const fetchImpl = vi.fn(async () =>
      streamResponse(sequence.map(sseFrame).join("")),
    );

    let state = createInitialChatState();
    state = chatReducer(state, { type: "STREAM_OPEN" });

    await streamChatTurn(
      { text: "Help with my CV", idempotency_key: "fe-ordinary-1" },
      {
        onEvent: (event) => {
          state = chatReducer(state, { type: "SSE_EVENT", event });
        },
      },
      { baseUrl: BASE_URL, fetchImpl: fetchImpl as typeof fetch },
    );

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const firstCall = fetchImpl.mock.calls[0] as unknown as
      | [RequestInfo | URL, RequestInit?]
      | undefined;
    expect(firstCall).toBeDefined();
    const url = String(firstCall![0]);
    const init = (firstCall![1] ?? {}) as RequestInit;
    expect(url).toContain("/api/chat/turns");
    expect(init.method).toBe("POST");
    expect(state.phase).toBe("completed");
    expect(state.streamingText).toBe("Hello world");
    expect(state.messages.some((m) => m.content === "Hello world")).toBe(true);
    expect(state.tools).toHaveLength(0);
    expect(isSendDisabled(state)).toBe(false);
  });

  it("maps synthetic tool activity raw SSE through real client into reducer and ChatShell", async () => {
    const toolSequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "e1", payload: {} }),
      evt({
        event: "assistant_status",
        event_id: "e2",
        payload: { status: "working" },
      }),
      evt({
        event: "tool_started",
        event_id: "e3",
        payload: {
          tool_call_id: "t1",
          label: "Echo label",
          status: "running",
        },
      }),
      evt({
        event: "tool_completed",
        event_id: "e4",
        payload: {
          tool_call_id: "t1",
          label: "Echo label",
          status: "complete",
          duration_ms: 12,
          outcome: "completed",
        },
      }),
      evt({
        event: "text_delta",
        event_id: "e5",
        payload: { delta: "done after echo" },
      }),
      evt({ event: "run_completed", event_id: "e6", payload: {} }),
    ];
    const frames = toolSequence.map(sseFrame);

    // Reducer path: raw wire → real streamChatTurn parser → pure reducer.
    const fetchForReducer = vi.fn(async () =>
      streamResponse(frames.join("")),
    );
    let reduced = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    await streamChatTurn(
      {
        text: "Match my profile keywords",
        idempotency_key: "fe-tool-1",
      },
      {
        onEvent: (event) => {
          reduced = chatReducer(reduced, { type: "SSE_EVENT", event });
        },
      },
      { baseUrl: BASE_URL, fetchImpl: fetchForReducer as typeof fetch },
    );
    expect(fetchForReducer).toHaveBeenCalledTimes(1);
    const reducerCall = fetchForReducer.mock.calls[0] as unknown as
      | [RequestInfo | URL, RequestInit?]
      | undefined;
    expect(String(reducerCall?.[0])).toContain("/api/chat/turns");
    expect(reduced.tools).toHaveLength(1);
    expect(reduced.tools[0]?.label).toBe("Echo label");
    expect(reduced.tools[0]?.status).toBe("complete");
    expect(reduced.tools[0]?.outcome).toBe("completed");
    expect(reduced.streamingText).toBe("done after echo");
    expect(reduced.phase).toBe("completed");

    // Shell path: same raw SSE through real streamChatTurn (no pre-parsed inject).
    let releaseStream: (() => void) | undefined;
    const hold = new Promise<void>((resolve) => {
      releaseStream = resolve;
    });

    const fetchForShell = vi.fn(async () =>
      // Hold after tool_completed so tools remain visible in live phase.
      progressiveStreamResponse(frames, 3, hold),
    );

    render(
      <ChatShell enableProfileSidebar={false}
        skipHydrate
        initialMessages={[]}
        api={realClientApi(fetchForShell as typeof fetch)}
      />,
    );

    submitComposer("Match my profile keywords");

    await waitFor(() => {
      expect(screen.getByTestId("chat-tool-activity")).toBeInTheDocument();
    });
    expect(screen.getByText(/Echo label/i)).toBeInTheDocument();

    const bodyWhileLive = document.body.textContent ?? "";
    expect(bodyWhileLive).not.toMatch(PROHIBITED_UI);
    expect(bodyWhileLive).not.toMatch(/echo:ping|arguments|tool_call_id.*c0/i);

    releaseStream?.();

    await waitFor(() => {
      expect(screen.getByText("done after echo")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("chat-completed")).toBeInTheDocument();
    });
    expect(fetchForShell).toHaveBeenCalled();
    const shellCall = fetchForShell.mock.calls[0] as unknown as
      | [RequestInfo | URL, RequestInit?]
      | undefined;
    expect(String(shellCall?.[0])).toContain("/api/chat/turns");
  });

  it("handles approval_required then resume through real client/parser into shell", async () => {
    const interruptSequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "e1", payload: {} }),
      evt({
        event: "assistant_status",
        event_id: "e2",
        payload: { status: "waiting" },
      }),
      evt({
        event: "approval_required",
        event_id: "e3",
        payload: {
          summary: "Approval required to continue",
          approval_kind: "approval_required",
        },
      }),
    ];

    const resumeSequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "r1", payload: {} }),
      evt({
        event: "text_delta",
        event_id: "r2",
        payload: { delta: "saved after resume" },
      }),
      evt({ event: "run_completed", event_id: "r3", payload: {} }),
    ];

    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/resume")) {
        return streamResponse(resumeSequence.map(sseFrame).join(""));
      }
      return streamResponse(interruptSequence.map(sseFrame).join(""));
    });

    // Reducer path via real streamChatTurn / streamChatResume.
    let state = createInitialChatState();
    state = chatReducer(state, { type: "STREAM_OPEN" });
    await streamChatTurn(
      {
        text: "Please update my candidate profile draft",
        idempotency_key: "fe-interrupt-1",
      },
      {
        onEvent: (event) => {
          state = chatReducer(state, { type: "SSE_EVENT", event });
        },
      },
      { baseUrl: BASE_URL, fetchImpl: fetchImpl as typeof fetch },
    );
    expect(state.phase).toBe("awaiting_approval");
    expect(state.approval?.summary).toMatch(/Approval required/i);
    expect(isSendDisabled(state)).toBe(true);

    state = chatReducer(state, { type: "STREAM_OPEN" });
    await streamChatResume(
      RUN,
      { action: "approve", idempotency_key: "fe-resume-1" },
      {
        onEvent: (event) => {
          state = chatReducer(state, { type: "SSE_EVENT", event });
        },
      },
      { baseUrl: BASE_URL, fetchImpl: fetchImpl as typeof fetch },
    );
    expect(state.phase).toBe("completed");
    expect(state.streamingText).toBe("saved after resume");
    expect(
      fetchImpl.mock.calls.some(([u]) => String(u).includes(`/runs/${RUN}/resume`)),
    ).toBe(true);

    // Shell path: real streamChatTurn/Resume parsing (raw frames only).
    const shellFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/resume")) {
        return streamResponse(resumeSequence.map(sseFrame).join(""));
      }
      return streamResponse(interruptSequence.map(sseFrame).join(""));
    });

    render(
      <ChatShell enableProfileSidebar={false}
        skipHydrate
        initialMessages={[]}
        api={realClientApi(shellFetch as typeof fetch)}
      />,
    );

    submitComposer("Please update my candidate profile draft");

    await waitFor(() => {
      expect(screen.getByTestId("chat-approval")).toBeInTheDocument();
    });
    expect(document.body.textContent ?? "").not.toMatch(PROHIBITED_UI);

    fireEvent.click(screen.getByTestId("chat-approval-approve"));

    await waitFor(() => {
      expect(
        shellFetch.mock.calls.some(([u]) => String(u).includes("/resume")),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByText("saved after resume")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("chat-completed")).toBeInTheDocument();
    });
  });

  it("parses profile_draft approval payload, Save Profile, and composer correction", async () => {
    const interruptSequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "p1", payload: {} }),
      evt({
        event: "approval_required",
        event_id: "p2",
        payload: {
          summary: "Review candidate profile draft",
          approval_kind: "profile_draft",
          current_title: "Senior Engineer",
          skill_names: ["TypeScript", "Python"],
          experience_count: 2,
          education_count: 1,
          has_preference_changes: true,
          target_roles_preview: ["Backend"],
        },
      }),
    ];
    const resumeSequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "pr1", payload: {} }),
      evt({
        event: "text_delta",
        event_id: "pr2",
        payload: { delta: "profile saved" },
      }),
      evt({ event: "run_completed", event_id: "pr3", payload: {} }),
    ];

    // Raw SSE → real parser → reducer keeps only display fields + instance key.
    const fetchForReducer = vi.fn(async () =>
      streamResponse(interruptSequence.map(sseFrame).join("")),
    );
    let reduced = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    await streamChatTurn(
      {
        text: "Create a candidate profile draft from the attached CV.",
        idempotency_key: "fe-profile-1",
        attachment_ids: ["att-staged-1"],
      },
      {
        onEvent: (event) => {
          reduced = chatReducer(reduced, { type: "SSE_EVENT", event });
        },
      },
      { baseUrl: BASE_URL, fetchImpl: fetchForReducer as typeof fetch },
    );
    expect(reduced.phase).toBe("awaiting_approval");
    expect(reduced.approval).toMatchObject({
      approvalKind: "profile_draft",
      currentTitle: "Senior Engineer",
      skillNames: ["TypeScript", "Python"],
      instanceKey: "p2",
    });
    const turnCall = fetchForReducer.mock.calls[0] as unknown as
      | [RequestInfo | URL, RequestInit?]
      | undefined;
    const turnInit = (turnCall?.[1] ?? {}) as RequestInit;
    expect(String(turnInit.body)).toContain("att-staged-1");

    // Shell: Save Profile → one approve resume.
    const saveFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/resume")) {
        return streamResponse(resumeSequence.map(sseFrame).join(""));
      }
      return streamResponse(interruptSequence.map(sseFrame).join(""));
    });
    const { unmount: unmountSave } = render(
      <ChatShell
        enableProfileSidebar={false}
        skipHydrate
        initialMessages={[]}
        api={realClientApi(saveFetch as typeof fetch)}
      />,
    );
    submitComposer("Create a candidate profile draft from the attached CV.");
    await waitFor(() => {
      expect(screen.getByTestId("profile-approval-card")).toBeInTheDocument();
    });
    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toMatch(
      /draft_id|storage_path|att-staged|RAW_CV|email@/i,
    );
    fireEvent.click(screen.getByTestId("profile-approval-save"));
    await waitFor(() => {
      expect(
        saveFetch.mock.calls.some(([u]) => String(u).includes("/resume")),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByText("profile saved")).toBeInTheDocument();
    });
    unmountSave();

    // Shell: Request Changes → composer correct resume (same run).
    const correctResume: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "cr1", payload: {} }),
      evt({
        event: "approval_required",
        event_id: "cr2",
        payload: {
          summary: "Review updated profile draft",
          approval_kind: "profile_draft",
          current_title: "Staff Engineer",
        },
      }),
    ];
    const correctFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/resume")) {
        return streamResponse(correctResume.map(sseFrame).join(""));
      }
      return streamResponse(interruptSequence.map(sseFrame).join(""));
    });
    render(
      <ChatShell
        enableProfileSidebar={false}
        skipHydrate
        initialMessages={[]}
        api={realClientApi(correctFetch as typeof fetch)}
      />,
    );
    submitComposer("Create a candidate profile draft from the attached CV.");
    await waitFor(() => {
      expect(screen.getByTestId("profile-approval-request-changes")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("profile-approval-request-changes"));
    await waitFor(() => {
      expect(screen.getByTestId("profile-approval-save")).toBeDisabled();
    });
    submitComposer("Use Staff Engineer title");
    await waitFor(() => {
      expect(
        correctFetch.mock.calls.some((rawCall) => {
          const call = rawCall as unknown as [
            RequestInfo | URL,
            RequestInit | undefined,
          ];
          const u = call[0];
          const init = call[1];
          if (!String(u).includes("/resume")) {
            return false;
          }
          const body = String(init?.body ?? "");
          return body.includes("correct") && body.includes("Staff Engineer");
        }),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByTestId("profile-approval-card")).toBeInTheDocument();
      expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
    });
    // Fresh reapproval is independently actionable (not disabled).
    expect(screen.getByTestId("profile-approval-save")).not.toBeDisabled();
  });

  it("ignores duplicate event_id and keeps ordered tool/text state", () => {
    const base: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "e1", payload: {} }),
      evt({
        event: "tool_started",
        event_id: "e2",
        payload: {
          tool_call_id: "t1",
          label: "Echo label",
          status: "running",
        },
      }),
      evt({
        event: "tool_completed",
        event_id: "e3",
        payload: {
          tool_call_id: "t1",
          label: "Echo label",
          status: "complete",
          duration_ms: 5,
          outcome: "completed",
        },
      }),
      evt({
        event: "text_delta",
        event_id: "e4",
        payload: { delta: "once" },
      }),
      evt({ event: "run_completed", event_id: "e5", payload: {} }),
    ];

    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, base);
    const afterFirst = state;

    // Replay entire sequence including duplicates — pure no-ops.
    state = reduceAll(state, base);
    expect(state.streamingText).toBe(afterFirst.streamingText);
    expect(state.streamingText).toBe("once");
    expect(state.tools).toHaveLength(1);
    expect(state.phase).toBe("completed");
    expect(Object.keys(state.seenEventIds)).toHaveLength(5);
  });

  it("surfaces run_failed and disconnect without prohibited content", async () => {
    const failSequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "e1", payload: {} }),
      evt({
        event: "run_failed",
        event_id: "e2",
        payload: { error_code: "AGENT_DECISION_FAILED", message: null },
      }),
    ];

    const failFetch = vi.fn(async () =>
      streamResponse(failSequence.map(sseFrame).join("")),
    );

    const { unmount } = render(
      <ChatShell enableProfileSidebar={false}
        skipHydrate
        initialMessages={[]}
        api={realClientApi(failFetch as typeof fetch)}
      />,
    );

    submitComposer("Help with my CV that fails");

    await waitFor(() => {
      expect(screen.getByTestId("chat-failure")).toBeInTheDocument();
    });
    expect(document.body.textContent).not.toMatch(
      /Traceback|Authorization|sentinel-shopaikey|api_key/i,
    );
    unmount();

    // Disconnect path: stream ends without terminal event (raw SSE → real client).
    const disconnectFetch = vi.fn(async () =>
      streamResponse(
        [
          evt({ event: "run_started", event_id: "d1", payload: {} }),
          evt({
            event: "text_delta",
            event_id: "d2",
            payload: { delta: "partial" },
          }),
        ]
          .map(sseFrame)
          .join(""),
      ),
    );

    render(
      <ChatShell enableProfileSidebar={false}
        skipHydrate
        initialMessages={[]}
        api={realClientApi(disconnectFetch as typeof fetch)}
      />,
    );

    submitComposer("Help with my CV disconnect");

    await waitFor(() => {
      expect(screen.getByTestId("chat-disconnect")).toBeInTheDocument();
    });
    expect(screen.getByTestId("chat-partial-text")).toHaveTextContent("partial");
  });

  it("never routes turn/resume outside approved /api/chat paths", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/chat/history")) {
        return new Response(JSON.stringify({ messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/chat/turns") || url.includes("/api/chat/runs/")) {
        return streamResponse(
          [
            evt({ event: "run_started", event_id: "e1", payload: {} }),
            evt({
              event: "text_delta",
              event_id: "e2",
              payload: { delta: "ok" },
            }),
            evt({ event: "run_completed", event_id: "e3", payload: {} }),
          ]
            .map(sseFrame)
            .join(""),
        );
      }
      return new Response("not found", { status: 404 });
    });

    vi.stubGlobal("fetch", fetchImpl);

    // Real client helpers (not ChatShell inject).
    await streamChatTurn(
      { text: "CV help", idempotency_key: "path-1" },
      { onEvent: () => undefined },
      { baseUrl: BASE_URL, fetchImpl: fetchImpl as typeof fetch },
    );
    await streamChatResume(
      RUN,
      { action: "approve", idempotency_key: "path-resume" },
      { onEvent: () => undefined },
      { baseUrl: BASE_URL, fetchImpl: fetchImpl as typeof fetch },
    );

    for (const [u] of fetchImpl.mock.calls) {
      const url = String(u);
      expect(url).toMatch(/\/api\/chat\/(history|turns|runs\/)/);
      expect(url).not.toMatch(/upload|profile|job|match|openai|shopaikey|synthetic/i);
    }
  });
});
