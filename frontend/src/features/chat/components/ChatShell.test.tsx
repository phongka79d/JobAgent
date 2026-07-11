import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChatSSEEvent, HistoryMessage } from "../contracts";
import { createInitialChatState } from "../reducer";
import { ChatShell } from "./ChatShell";

function sseEvent(
  partial: Omit<ChatSSEEvent, "event_id" | "timestamp"> & {
    event_id?: string;
    timestamp?: string;
  },
): ChatSSEEvent {
  return {
    event_id: partial.event_id ?? crypto.randomUUID(),
    timestamp: partial.timestamp ?? "2026-01-01T00:00:00.000Z",
    ...partial,
  } as ChatSSEEvent;
}

const historyMessages: HistoryMessage[] = [
  {
    role: "user",
    content: "Prior question",
    created_at: "2026-01-01T00:00:00.000Z",
    structured_payload: null,
  },
  {
    role: "assistant",
    content: "Prior answer",
    created_at: "2026-01-01T00:00:01.000Z",
    structured_payload: null,
  },
];

/** Astryx ChatComposer uses a contenteditable textbox, not a native input. */
function submitComposer(text: string): void {
  const textbox = screen.getByRole("textbox");
  textbox.textContent = text;
  fireEvent.input(textbox);
  fireEvent.keyDown(textbox, { key: "Enter" });
}

describe("ChatShell", () => {
  it("hydrates durable history on mount", async () => {
    const fetchHistory = vi.fn().mockResolvedValue({ messages: historyMessages });

    render(
      <ChatShell
        api={{ fetchHistory }}
        wrapTheme
      />,
    );

    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Prior question")).toBeInTheDocument();
    });
    expect(screen.getByText("Prior answer")).toBeInTheDocument();
    expect(fetchHistory).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("submits a turn, shows partial text, and disables conflicting send", async () => {
    const runId = "run-1";

    const streamTurn = vi.fn(
      async (
        _body: { text: string; idempotency_key: string },
        handlers: {
          onEvent: (e: ChatSSEEvent) => void;
          onDisconnect?: () => void;
        },
      ) => {
        handlers.onEvent(
          sseEvent({ event: "run_started", run_id: runId, payload: {} }),
        );
        handlers.onEvent(
          sseEvent({
            event: "text_delta",
            run_id: runId,
            payload: { delta: "Hello " },
          }),
        );
        handlers.onEvent(
          sseEvent({
            event: "text_delta",
            run_id: runId,
            payload: { delta: "world" },
          }),
        );
        await new Promise<void>(() => {
          // never resolves — keep phase active
        });
      },
    );

    render(
      <ChatShell
        skipHydrate
        initialMessages={[]}
        api={{
          fetchHistory: vi.fn(),
          streamTurn: streamTurn as never,
        }}
      />,
    );

    submitComposer("Hi there");

    await waitFor(() => {
      expect(streamTurn).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByTestId("chat-partial-text")).toHaveTextContent(
        "Hello world",
      );
    });

    expect(screen.getByRole("textbox")).toHaveAttribute(
      "contenteditable",
      "false",
    );
  });

  it("maps sanitized tools during an active run", async () => {
    const runId = "run-tools";
    let resolveStream: (() => void) | undefined;
    const streamDone = new Promise<void>((resolve) => {
      resolveStream = resolve;
    });

    const streamTurn = vi.fn(
      async (
        _body: unknown,
        handlers: { onEvent: (e: ChatSSEEvent) => void },
      ) => {
        handlers.onEvent(
          sseEvent({ event: "run_started", run_id: runId, payload: {} }),
        );
        handlers.onEvent(
          sseEvent({
            event: "tool_started",
            run_id: runId,
            payload: {
              tool_call_id: "tc-secret-uuid",
              label: "Safe label",
              status: "running",
            },
          }),
        );
        handlers.onEvent(
          sseEvent({
            event: "tool_completed",
            run_id: runId,
            payload: {
              tool_call_id: "tc-secret-uuid",
              label: "Safe label",
              status: "complete",
              duration_ms: 250,
              outcome: "Done cleanly",
            },
          }),
        );
        await streamDone;
      },
    );

    render(
      <ChatShell
        skipHydrate
        api={{ streamTurn: streamTurn as never }}
      />,
    );

    submitComposer("go");

    await waitFor(() => {
      expect(screen.getByText(/Safe label/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Done cleanly/i)).toBeInTheDocument();
    expect(screen.queryByText("tc-secret-uuid")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/sk-live|Authorization|Traceback/i);

    await act(async () => {
      resolveStream?.();
    });
  });

  it("disables approval actions after approve is clicked (idempotent)", async () => {
    const runId = "run-approve";

    const initial = createInitialChatState();
    const withApproval = {
      ...initial,
      activeRunId: runId,
      phase: "awaiting_approval" as const,
      approval: { summary: "Apply change?", approvalKind: null },
      assistantStatus: "waiting" as const,
      seenEventIds: { e1: true as const },
    };

    let resumeCalls = 0;
    const streamResume = vi.fn(async () => {
      resumeCalls += 1;
      await new Promise<void>(() => undefined);
    });

    render(
      <ChatShell
        skipHydrate
        initialState={withApproval}
        api={{ streamResume: streamResume as never }}
      />,
    );

    expect(screen.getByTestId("chat-approval-summary")).toHaveTextContent(
      "Apply change?",
    );

    const approve = screen.getByTestId("chat-approval-approve");
    fireEvent.click(approve);

    await waitFor(() => {
      expect(streamResume).toHaveBeenCalledTimes(1);
    });

    // Resume opens the stream (STREAM_OPEN), which leaves awaiting_approval so
    // approval controls unmount — further approve clicks are impossible.
    // resumeMode also blocks re-entry if controls were still mounted.
    expect(screen.queryByTestId("chat-approval-approve")).not.toBeInTheDocument();
    fireEvent.click(approve);
    expect(resumeCalls).toBe(1);
  });

  it("does not resume Correct with empty correction text", async () => {
    const runId = "run-correct-empty";
    const withApproval = {
      ...createInitialChatState(),
      activeRunId: runId,
      phase: "awaiting_approval" as const,
      approval: { summary: "Revise this?", approvalKind: null },
      assistantStatus: "waiting" as const,
      seenEventIds: { e1: true as const },
    };

    const streamResume = vi.fn(async () => undefined);

    render(
      <ChatShell
        skipHydrate
        initialState={withApproval}
        api={{ streamResume: streamResume as never }}
      />,
    );

    const correct = screen.getByTestId("chat-approval-correct");
    expect(correct).toBeDisabled();
    fireEvent.click(correct);
    expect(streamResume).not.toHaveBeenCalled();
  });

  it("sends correction_text on successful Correct resume", async () => {
    const runId = "run-correct-ok";
    const withApproval = {
      ...createInitialChatState(),
      activeRunId: runId,
      phase: "awaiting_approval" as const,
      approval: { summary: "Revise this?", approvalKind: null },
      assistantStatus: "waiting" as const,
      seenEventIds: { e1: true as const },
    };

    type ResumeBody = {
      action: string;
      idempotency_key: string;
      correction_text?: string | null;
    };
    const streamResume = vi.fn(
      async (
        // Keep signature for mock.calls typing; never reads params.
        resumeRunId: string,
        body: ResumeBody,
      ): Promise<void> => {
        void resumeRunId;
        void body;
        await new Promise<void>(() => undefined);
      },
    );

    render(
      <ChatShell
        skipHydrate
        initialState={withApproval}
        api={{ streamResume: streamResume as never }}
      />,
    );

    const correctionRoot = screen.getByTestId("chat-approval-correction");
    const textarea =
      correctionRoot.matches("textarea")
        ? (correctionRoot as HTMLTextAreaElement)
        : correctionRoot.querySelector("textarea");
    expect(textarea).toBeTruthy();
    fireEvent.change(textarea!, {
      target: { value: "  Use a shorter summary  " },
    });

    fireEvent.click(screen.getByTestId("chat-approval-correct"));

    await waitFor(() => {
      expect(streamResume).toHaveBeenCalledTimes(1);
    });

    expect(streamResume).toHaveBeenCalledWith(
      runId,
      expect.objectContaining({
        action: "correct",
        correction_text: "Use a shorter summary",
      }),
      expect.anything(),
      expect.anything(),
    );
    const resumeBody = streamResume.mock.calls[0]![1];
    expect(resumeBody.idempotency_key.length).toBeGreaterThan(0);
  });


  it("surfaces failure and allows recovery after disconnect", async () => {
    const runId = "run-fail";

    const streamTurn = vi
      .fn()
      .mockImplementationOnce(
        async (
          _body: unknown,
          handlers: { onEvent: (e: ChatSSEEvent) => void },
        ) => {
          handlers.onEvent(
            sseEvent({ event: "run_started", run_id: runId, payload: {} }),
          );
          handlers.onEvent(
            sseEvent({
              event: "run_failed",
              run_id: runId,
              payload: {
                error_code: "PROVIDER_ERROR",
                message: "Provider unavailable",
              },
            }),
          );
        },
      )
      .mockImplementationOnce(
        async (
          _body: unknown,
          handlers: {
            onEvent: (e: ChatSSEEvent) => void;
            onDisconnect?: () => void;
          },
        ) => {
          handlers.onEvent(
            sseEvent({ event: "run_started", run_id: "run-2", payload: {} }),
          );
          handlers.onDisconnect?.();
        },
      )
      .mockImplementationOnce(
        async (
          _body: unknown,
          handlers: { onEvent: (e: ChatSSEEvent) => void },
        ) => {
          handlers.onEvent(
            sseEvent({ event: "run_started", run_id: "run-3", payload: {} }),
          );
          handlers.onEvent(
            sseEvent({
              event: "text_delta",
              run_id: "run-3",
              payload: { delta: "Recovered" },
            }),
          );
          handlers.onEvent(
            sseEvent({ event: "run_completed", run_id: "run-3", payload: {} }),
          );
        },
      );

    render(
      <ChatShell
        skipHydrate
        api={{ streamTurn: streamTurn as never }}
      />,
    );

    submitComposer("first");

    await waitFor(() => {
      expect(screen.getByTestId("chat-failure")).toHaveTextContent(
        "Provider unavailable",
      );
    });

    expect(screen.getByRole("textbox")).toHaveAttribute(
      "contenteditable",
      "true",
    );

    submitComposer("second");

    await waitFor(() => {
      expect(screen.getByTestId("chat-disconnect")).toBeInTheDocument();
    });

    submitComposer("third");

    await waitFor(() => {
      expect(screen.getByText("Recovered")).toBeInTheDocument();
    });
  });

  it("shows empty state when history is empty", () => {
    render(
      <ChatShell
        skipHydrate
        initialMessages={[]}
      />,
    );

    expect(screen.getByTestId("chat-empty-state")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Start a conversation/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByText(/Message JobAgent/i)).toBeInTheDocument();
  });
});
