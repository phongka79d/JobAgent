import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatShell } from "../../chat/components/ChatShell";
import type { ChatSSEEvent } from "../../chat/contracts";
import { createInitialChatState } from "../../chat/reducer";
import { SIDEBAR_PROFILE_TURN_TEXT } from "../contracts";
import type { StagedAttachmentResponse } from "../contracts";

const stagedFixture: StagedAttachmentResponse = {
  id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
  original_name: "side.pdf",
  mime_type: "application/pdf",
  size_bytes: 8,
  page_count: 1,
  state: "staged",
};

const emptyProfile = {
  state: "none" as const,
  profile: null,
  preferences: null,
  active_attachment: null,
};

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

async function selectPdf(
  name = "side.pdf",
): Promise<void> {
  const file = new File(["%PDF-1.4"], name, { type: "application/pdf" });
  const input = document.querySelector(
    'input[type="file"]',
  ) as HTMLInputElement | null;
  expect(input).not.toBeNull();
  await act(async () => {
    Object.defineProperty(input!, "files", {
      value: [file],
      configurable: true,
    });
    input!.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("ChatShell profile sidebar integration", () => {
  it("loads profile, uploads once, and starts exactly one sidebar turn", async () => {
    const fetchProfile = vi.fn().mockResolvedValue(emptyProfile);
    const uploadCv = vi.fn().mockResolvedValue(stagedFixture);
    const streamTurn = vi.fn().mockResolvedValue(undefined);
    const fetchHistory = vi.fn().mockResolvedValue({ messages: [] });

    render(
      <ChatShell
        skipHydrate={false}
        api={{ fetchHistory, streamTurn }}
        profileApi={{
          fetchProfile,
          uploadCv,
          activeCvUrl: () => "http://127.0.0.1:8000/api/profile/cv",
        }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });
    expect(fetchProfile).toHaveBeenCalled();

    await selectPdf();

    await waitFor(() => {
      expect(uploadCv).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(streamTurn).toHaveBeenCalledTimes(1);
    });

    const turnBody = streamTurn.mock.calls[0]?.[0] as {
      text: string;
      attachment_ids?: string[];
    };
    expect(turnBody.text).toBe(SIDEBAR_PROFILE_TURN_TEXT);
    expect(turnBody.attachment_ids).toEqual([stagedFixture.id]);

    // No second upload from a single selection.
    expect(uploadCv).toHaveBeenCalledTimes(1);
  });

  it("defers sidebar turn through hydration then starts exactly one turn", async () => {
    let resolveHistory: ((value: { messages: [] }) => void) | undefined;
    const fetchHistory = vi.fn(
      () =>
        new Promise<{ messages: [] }>((resolve) => {
          resolveHistory = resolve;
        }),
    );
    const fetchProfile = vi.fn().mockResolvedValue(emptyProfile);
    const uploadCv = vi.fn().mockResolvedValue(stagedFixture);
    const streamTurn = vi.fn().mockResolvedValue(undefined);

    render(
      <ChatShell
        api={{ fetchHistory, streamTurn }}
        profileApi={{ fetchProfile, uploadCv }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();

    await selectPdf();

    await waitFor(() => {
      expect(uploadCv).toHaveBeenCalledTimes(1);
    });
    // Still hydrating — turn must be deferred, not dropped.
    expect(streamTurn).not.toHaveBeenCalled();
    expect(screen.getByText(/CV uploaded/i)).toBeInTheDocument();

    await act(async () => {
      resolveHistory?.({ messages: [] });
    });

    await waitFor(() => {
      expect(streamTurn).toHaveBeenCalledTimes(1);
    });
    const turnBody = streamTurn.mock.calls[0]?.[0] as {
      text: string;
      attachment_ids?: string[];
    };
    expect(turnBody.text).toBe(SIDEBAR_PROFILE_TURN_TEXT);
    expect(turnBody.attachment_ids).toEqual([stagedFixture.id]);
    expect(uploadCv).toHaveBeenCalledTimes(1);
  });

  it("queues sidebar turn while active and flushes exactly once when free", async () => {
    const runId = "run-active-block";
    let releaseTurn: (() => void) | undefined;
    const streamTurn = vi.fn(
      async (
        _body: { text: string; idempotency_key: string },
        handlers: {
          onEvent: (e: ChatSSEEvent) => void;
        },
      ) => {
        handlers.onEvent(
          sseEvent({ event: "run_started", run_id: runId, payload: {} }),
        );
        await new Promise<void>((resolve) => {
          releaseTurn = resolve;
        });
        handlers.onEvent(
          sseEvent({
            event: "run_completed",
            run_id: runId,
            payload: {},
          }),
        );
      },
    );
    const fetchProfile = vi.fn().mockResolvedValue(emptyProfile);
    const uploadCv = vi.fn().mockResolvedValue(stagedFixture);

    render(
      <ChatShell
        skipHydrate
        initialState={createInitialChatState()}
        api={{ streamTurn }}
        profileApi={{ fetchProfile, uploadCv }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });

    // Start a normal turn so phase becomes active.
    const textbox = screen.getByRole("textbox");
    textbox.textContent = "hello agent";
    fireEvent.input(textbox);
    fireEvent.keyDown(textbox, { key: "Enter" });

    await waitFor(() => {
      expect(streamTurn).toHaveBeenCalledTimes(1);
    });

    await selectPdf();
    await waitFor(() => {
      expect(uploadCv).toHaveBeenCalledTimes(1);
    });
    // Upload succeeded UI, but second turn not started while active.
    expect(screen.getByText(/CV uploaded/i)).toBeInTheDocument();
    expect(streamTurn).toHaveBeenCalledTimes(1);

    await act(async () => {
      releaseTurn?.();
    });

    await waitFor(() => {
      expect(streamTurn).toHaveBeenCalledTimes(2);
    });
    const sidebarBody = streamTurn.mock.calls[1]?.[0] as {
      text: string;
      attachment_ids?: string[];
    };
    expect(sidebarBody.text).toBe(SIDEBAR_PROFILE_TURN_TEXT);
    expect(sidebarBody.attachment_ids).toEqual([stagedFixture.id]);
    expect(uploadCv).toHaveBeenCalledTimes(1);
  });

  it("FIFO-queues two sidebar uploads while blocked and flushes each attachment turn in order", async () => {
    const firstId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    const secondId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
    const firstStaged: StagedAttachmentResponse = {
      ...stagedFixture,
      id: firstId,
      original_name: "first.pdf",
    };
    const secondStaged: StagedAttachmentResponse = {
      ...stagedFixture,
      id: secondId,
      original_name: "second.pdf",
    };

    let resolveHistory: ((value: { messages: [] }) => void) | undefined;
    const fetchHistory = vi.fn(
      () =>
        new Promise<{ messages: [] }>((resolve) => {
          resolveHistory = resolve;
        }),
    );
    const fetchProfile = vi.fn().mockResolvedValue(emptyProfile);
    const uploadCv = vi
      .fn()
      .mockResolvedValueOnce(firstStaged)
      .mockResolvedValueOnce(secondStaged);

    // Sequentially release each turn so the FIFO can flush one-by-one.
    const turnReleases: Array<() => void> = [];
    let turnCount = 0;
    const streamTurn = vi.fn(
      async (
        _body: {
          text: string;
          idempotency_key: string;
          attachment_ids?: readonly string[];
        },
        handlers: {
          onEvent: (e: ChatSSEEvent) => void;
        },
      ) => {
        const idx = turnCount;
        turnCount += 1;
        const runId = `run-fifo-${idx}`;
        handlers.onEvent(
          sseEvent({ event: "run_started", run_id: runId, payload: {} }),
        );
        await new Promise<void>((resolve) => {
          turnReleases[idx] = resolve;
        });
        handlers.onEvent(
          sseEvent({
            event: "run_completed",
            run_id: runId,
            payload: {},
          }),
        );
      },
    );

    render(
      <ChatShell
        api={{ fetchHistory, streamTurn }}
        profileApi={{ fetchProfile, uploadCv }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();

    await selectPdf("first.pdf");
    await waitFor(() => {
      expect(uploadCv).toHaveBeenCalledTimes(1);
    });
    expect(streamTurn).not.toHaveBeenCalled();

    await selectPdf("second.pdf");
    await waitFor(() => {
      expect(uploadCv).toHaveBeenCalledTimes(2);
    });
    // Still hydrating: both uploads accepted, zero turns started, no overwrite drop.
    expect(streamTurn).not.toHaveBeenCalled();

    await act(async () => {
      resolveHistory?.({ messages: [] });
    });

    // First queued turn starts when hydrate clears.
    await waitFor(() => {
      expect(streamTurn).toHaveBeenCalledTimes(1);
    });
    const firstBody = streamTurn.mock.calls[0]?.[0] as {
      text: string;
      attachment_ids?: string[];
    };
    expect(firstBody.text).toBe(SIDEBAR_PROFILE_TURN_TEXT);
    expect(firstBody.attachment_ids).toEqual([firstId]);

    // Complete first turn so the second FIFO item can flush.
    await act(async () => {
      turnReleases[0]?.();
    });

    await waitFor(() => {
      expect(streamTurn).toHaveBeenCalledTimes(2);
    });
    const secondBody = streamTurn.mock.calls[1]?.[0] as {
      text: string;
      attachment_ids?: string[];
    };
    expect(secondBody.text).toBe(SIDEBAR_PROFILE_TURN_TEXT);
    expect(secondBody.attachment_ids).toEqual([secondId]);

    // Exactly one upload and one attachment-specific turn per accepted file; order preserved; no duplicate third turn.
    expect(uploadCv).toHaveBeenCalledTimes(2);
    expect(streamTurn).toHaveBeenCalledTimes(2);
    expect(streamTurn.mock.calls.map((c) => (c[0] as { attachment_ids?: string[] }).attachment_ids)).toEqual([
      [firstId],
      [secondId],
    ]);
  });

  it("recovers from upload error without starting a turn", async () => {
    const fetchProfile = vi.fn().mockResolvedValue(emptyProfile);
    const uploadCv = vi.fn().mockRejectedValue(
      Object.assign(new Error("UNSUPPORTED_MEDIA_TYPE"), {
        code: "UNSUPPORTED_MEDIA_TYPE",
        status: 415,
        name: "ProfileApiError",
      }),
    );
    const streamTurn = vi.fn();
    const fetchHistory = vi.fn().mockResolvedValue({ messages: [] });

    render(
      <ChatShell
        api={{ fetchHistory, streamTurn }}
        profileApi={{ fetchProfile, uploadCv }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });

    const file = new File(["%PDF-not-really"], "bad.pdf", {
      type: "application/pdf",
    });
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement | null;
    await act(async () => {
      Object.defineProperty(input!, "files", {
        value: [file],
        configurable: true,
      });
      input!.dispatchEvent(new Event("change", { bubbles: true }));
    });

    await waitFor(() => {
      expect(uploadCv).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      // Shared upload state surfaces the error on both sidebar and composer FileInputs.
      expect(
        screen.getAllByText(/UNSUPPORTED_MEDIA_TYPE/i).length,
      ).toBeGreaterThanOrEqual(1);
    });
    expect(streamTurn).not.toHaveBeenCalled();
  });
});
