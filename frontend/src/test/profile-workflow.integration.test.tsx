/**
 * Phase 3 exit proof: full frontend profile workflow (task 06A).
 *
 * Drives raw SSE through the real streamChatTurn/streamChatResume parser into
 * the pure reducer and ChatShell for sidebar upload, composer token, proposal
 * card, Request Changes, Save Profile, duplicates, profile refresh, errors,
 * and disconnect — with injected fetch fakes only.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  type ChatState,
} from "../features/chat/reducer";
import { SIDEBAR_PROFILE_TURN_TEXT } from "../features/profile/contracts";
import type { ProfileResponse, StagedAttachmentResponse } from "../features/profile/contracts";
import {
  fetchProfile,
  uploadCv,
} from "../features/profile/api";

const RUN = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const TS = "2026-01-01T12:00:00.000Z";
const BASE_URL = "http://localhost:8000";
const ATTACHMENT_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd";
const CONTACT_SENTINEL = "unique-contact-sentinel@example.test";
const PROHIBITED_UI =
  /echo_label|Traceback|Authorization|api_key|SHOPAIKEY|sk-live|Bearer |draft_id|storage_path|unique-contact-sentinel/i;

const stagedFixture: StagedAttachmentResponse = {
  id: ATTACHMENT_ID,
  original_name: "cv.pdf",
  mime_type: "application/pdf",
  size_bytes: 128,
  page_count: 1,
  state: "staged",
};

const emptyProfile: ProfileResponse = {
  state: "none",
  profile: null,
  preferences: null,
  active_attachment: null,
};

const approvedProfile: ProfileResponse = {
  state: "active",
  profile: {
    summary: "Corrected integration summary",
    current_title: "Backend Engineer",
  },
  preferences: {
    target_roles: ["Platform Lead"],
  },
  active_attachment: {
    id: ATTACHMENT_ID,
    original_name: "cv.pdf",
    mime_type: "application/pdf",
    size_bytes: 128,
    page_count: 1,
    state: "active",
  },
};

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

function submitComposer(text: string): void {
  const textbox = screen.getByRole("textbox");
  textbox.textContent = text;
  fireEvent.input(textbox);
  fireEvent.keyDown(textbox, { key: "Enter" });
}

async function selectPdf(
  name = "cv.pdf",
  inputIndex = 0,
): Promise<void> {
  const file = new File(["%PDF-1.4 synthetic"], name, {
    type: "application/pdf",
  });
  const inputs = document.querySelectorAll(
    'input[type="file"]',
  ) as NodeListOf<HTMLInputElement>;
  expect(inputs.length).toBeGreaterThan(inputIndex);
  const input = inputs[inputIndex]!;
  await act(async () => {
    Object.defineProperty(input, "files", {
      value: [file],
      configurable: true,
    });
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function profileApprovalSequence(
  overrides: Partial<{
    event_id: string;
    summary: string;
    current_title: string;
    skill_names: string[];
  }> = {},
): ChatSSEEvent[] {
  return [
    evt({ event: "run_started", event_id: overrides.event_id ?? "p1", payload: {} }),
    evt({
      event: "tool_started",
      event_id: "p-tool-start",
      payload: {
        tool_call_id: "t1",
        label: "Propose profile",
        status: "running",
      },
    }),
    evt({
      event: "tool_completed",
      event_id: "p-tool-done",
      payload: {
        tool_call_id: "t1",
        label: "Propose profile",
        status: "complete",
        duration_ms: 8,
        outcome: "completed",
      },
    }),
    evt({
      event: "approval_required",
      event_id: overrides.event_id ? `${overrides.event_id}-a` : "p2",
      payload: {
        summary: overrides.summary ?? "Review candidate profile draft",
        approval_kind: "profile_draft",
        current_title: overrides.current_title ?? "Backend Engineer",
        skill_names: overrides.skill_names ?? ["Python", "Zig"],
        experience_count: 1,
        education_count: 0,
        has_preference_changes: true,
        target_roles_preview: ["Platform Lead"],
      },
    }),
  ];
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("profile workflow integration (parser + reducer + shell)", () => {
  it("sidebar upload starts turn with attachment, proposal card, Save Profile, refresh", async () => {
    let profileReads = 0;
    const fetchProfileImpl = vi.fn(async () => {
      profileReads += 1;
      return profileReads <= 1 ? emptyProfile : approvedProfile;
    });
    const uploadCvImpl = vi.fn().mockResolvedValue(stagedFixture);

    const saveSequence: ChatSSEEvent[] = [
      evt({ event: "run_started", event_id: "s1", payload: {} }),
      evt({
        event: "text_delta",
        event_id: "s2",
        payload: { delta: "Profile saved after approval" },
      }),
      evt({ event: "run_completed", event_id: "s3", payload: {} }),
    ];

    const chatFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/resume")) {
        return streamResponse(saveSequence.map(sseFrame).join(""));
      }
      return streamResponse(profileApprovalSequence().map(sseFrame).join(""));
    });

    render(
      <ChatShell
        skipHydrate
        initialMessages={[]}
        api={realClientApi(chatFetch as typeof fetch)}
        profileApi={{
          fetchProfile: fetchProfileImpl,
          uploadCv: uploadCvImpl,
          activeCvUrl: () => `${BASE_URL}/api/profile/cv`,
        }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });
    expect(fetchProfileImpl).toHaveBeenCalled();

    await selectPdf("side.pdf");

    await waitFor(() => {
      expect(uploadCvImpl).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(chatFetch).toHaveBeenCalled();
    });

    const turnCall = chatFetch.mock.calls.find(([u]) =>
      String(u).includes("/api/chat/turns"),
    ) as [RequestInfo | URL, RequestInit?] | undefined;
    expect(turnCall).toBeDefined();
    const turnBody = String(turnCall![1]?.body ?? "");
    expect(turnBody).toContain(SIDEBAR_PROFILE_TURN_TEXT);
    expect(turnBody).toContain(ATTACHMENT_ID);

    await waitFor(() => {
      expect(screen.getByTestId("profile-approval-card")).toBeInTheDocument();
    });
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText(/Python/i)).toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toMatch(PROHIBITED_UI);
    expect(document.body.textContent ?? "").not.toContain(CONTACT_SENTINEL);

    // Duplicate Save clicks fire at most one resume (second click is a no-op).
    const saveButton = screen.getByTestId("profile-approval-save");
    fireEvent.click(saveButton);
    fireEvent.click(saveButton);

    await waitFor(() => {
      const resumeCalls = chatFetch.mock.calls.filter(([u]) =>
        String(u).includes("/resume"),
      );
      expect(resumeCalls.length).toBe(1);
    });
    await waitFor(() => {
      expect(
        screen.getByText("Profile saved after approval"),
      ).toBeInTheDocument();
    });
    expect(document.body.textContent ?? "").not.toMatch(PROHIBITED_UI);
  });

  it("composer token submits attachment once; Request Changes yields fresh card", async () => {
    const interrupt = profileApprovalSequence({
      current_title: "Backend Engineer",
    });
    const correctResume: ChatSSEEvent[] = profileApprovalSequence({
      event_id: "cr",
      summary: "Review updated profile draft",
      current_title: "Staff Engineer",
      skill_names: ["Python"],
    });

    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/resume")) {
        const body = String(init?.body ?? "");
        expect(body).toMatch(/correct|approve/);
        return streamResponse(correctResume.map(sseFrame).join(""));
      }
      return streamResponse(interrupt.map(sseFrame).join(""));
    });

    const uploadCvImpl = vi.fn().mockResolvedValue(stagedFixture);
    const fetchProfileImpl = vi.fn().mockResolvedValue(emptyProfile);

    render(
      <ChatShell
        skipHydrate
        initialMessages={[]}
        api={realClientApi(fetchImpl as typeof fetch)}
        profileApi={{
          fetchProfile: fetchProfileImpl,
          uploadCv: uploadCvImpl,
        }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });

    // Composer file input is typically the second file input when sidebar is on.
    const inputs = document.querySelectorAll('input[type="file"]');
    const composerIndex = inputs.length > 1 ? 1 : 0;
    await selectPdf("composer.pdf", composerIndex);

    await waitFor(() => {
      expect(uploadCvImpl).toHaveBeenCalledTimes(1);
    });
    // Composer path: token only — no automatic turn until submit.
    expect(
      fetchImpl.mock.calls.filter(([u]) => String(u).includes("/api/chat/turns")),
    ).toHaveLength(0);

    submitComposer("Create a candidate profile draft from the attached CV.");

    await waitFor(() => {
      expect(screen.getByTestId("profile-approval-card")).toBeInTheDocument();
    });

    const turnCall = fetchImpl.mock.calls.find(([u]) =>
      String(u).includes("/api/chat/turns"),
    ) as [RequestInfo | URL, RequestInit?] | undefined;
    expect(String(turnCall?.[1]?.body ?? "")).toContain(ATTACHMENT_ID);

    fireEvent.click(screen.getByTestId("profile-approval-request-changes"));
    await waitFor(() => {
      expect(screen.getByTestId("profile-approval-save")).toBeDisabled();
    });

    submitComposer("Use Staff Engineer title");

    await waitFor(() => {
      expect(
        fetchImpl.mock.calls.some((rawCall) => {
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
    expect(screen.getByTestId("profile-approval-save")).not.toBeDisabled();
    expect(document.body.textContent ?? "").not.toMatch(PROHIBITED_UI);
  });

  it("maps raw profile SSE through real client into reducer without leakage", async () => {
    const sequence = profileApprovalSequence();
    const fetchImpl = vi.fn(async () =>
      streamResponse(sequence.map(sseFrame).join("")),
    );

    let state: ChatState = chatReducer(
      createInitialChatState(),
      { type: "STREAM_OPEN" },
    );
    await streamChatTurn(
      {
        text: SIDEBAR_PROFILE_TURN_TEXT,
        idempotency_key: "pw-fe-1",
        attachment_ids: [ATTACHMENT_ID],
      },
      {
        onEvent: (event) => {
          state = chatReducer(state, { type: "SSE_EVENT", event });
        },
      },
      { baseUrl: BASE_URL, fetchImpl: fetchImpl as typeof fetch },
    );

    expect(state.phase).toBe("awaiting_approval");
    expect(state.approval).toMatchObject({
      approvalKind: "profile_draft",
      currentTitle: "Backend Engineer",
      skillNames: ["Python", "Zig"],
    });
    expect(JSON.stringify(state)).not.toContain(CONTACT_SENTINEL);
    expect(JSON.stringify(state)).not.toMatch(/draft_id|storage_path/i);

    // Duplicate event_id is ignored.
    const before = state;
    state = chatReducer(state, {
      type: "SSE_EVENT",
      event: sequence[sequence.length - 1]!,
    });
    expect(state.approval?.instanceKey).toBe(before.approval?.instanceKey);
  });

  it("surfaces profile upload error and stream disconnect without prohibited content", async () => {
    const uploadCvImpl = vi.fn().mockRejectedValue(
      Object.assign(new Error("upload failed"), {
        name: "ProfileApiError",
        status: 415,
        code: "UNSUPPORTED_MEDIA_TYPE",
      }),
    );
    const fetchProfileImpl = vi.fn().mockResolvedValue(emptyProfile);

    const { unmount } = render(
      <ChatShell
        skipHydrate
        initialMessages={[]}
        api={{
          fetchHistory: async () => ({ messages: [] }),
          streamTurn: async () => undefined,
        }}
        profileApi={{
          fetchProfile: fetchProfileImpl,
          uploadCv: uploadCvImpl,
        }}
        enableProfileSidebar
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    });
    await selectPdf("bad.txt");
    await waitFor(() => {
      expect(uploadCvImpl).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(document.body.textContent ?? "").toMatch(/fail|error|upload/i);
    });
    expect(document.body.textContent ?? "").not.toMatch(PROHIBITED_UI);
    unmount();

    // Disconnect: stream ends without terminal event.
    const disconnectFetch = vi.fn(async () =>
      streamResponse(
        [
          evt({ event: "run_started", event_id: "d1", payload: {} }),
          evt({
            event: "text_delta",
            event_id: "d2",
            payload: { delta: "partial profile" },
          }),
        ]
          .map(sseFrame)
          .join(""),
      ),
    );

    render(
      <ChatShell
        skipHydrate
        initialMessages={[]}
        api={realClientApi(disconnectFetch as typeof fetch)}
        enableProfileSidebar={false}
      />,
    );
    submitComposer("Help with my CV disconnect");
    await waitFor(() => {
      expect(screen.getByTestId("chat-disconnect")).toBeInTheDocument();
    });
    expect(screen.getByTestId("chat-partial-text")).toHaveTextContent(
      "partial profile",
    );
    expect(document.body.textContent ?? "").not.toMatch(PROHIBITED_UI);
  });

  it("typed profile client paths stay on authorized FastAPI routes", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/profile") && !url.includes("/cv")) {
        return new Response(JSON.stringify(emptyProfile), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/attachments/cv")) {
        return new Response(JSON.stringify(stagedFixture), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("not found", { status: 404 });
    });

    await fetchProfile({
      baseUrl: BASE_URL,
      fetchImpl: fetchImpl as typeof fetch,
    });
    await uploadCv(new File(["%PDF"], "cv.pdf", { type: "application/pdf" }), {
      baseUrl: BASE_URL,
      fetchImpl: fetchImpl as typeof fetch,
    });

    const urls = fetchImpl.mock.calls.map(([u]) => String(u));
    expect(urls.some((u) => u.endsWith("/api/profile"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/api/attachments/cv"))).toBe(true);
    expect(urls.every((u) => !u.includes("neo4j") && !u.includes("shopaikey"))).toBe(
      true,
    );
  });
});
