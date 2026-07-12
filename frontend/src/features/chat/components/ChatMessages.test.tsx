import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  createApprovalState,
  createInitialChatState,
  type ChatState,
} from "../reducer";
import { ChatMessages } from "./ChatMessages";

function renderMessages(partial: Partial<ChatState>) {
  const state = { ...createInitialChatState(), ...partial };
  return render(
    <ChatMessages
      messages={state.messages}
      phase={state.phase}
      streamingText={state.streamingText}
      tools={state.tools}
      assistantStatus={state.assistantStatus}
      assistantStatusMessage={state.assistantStatusMessage}
      approval={state.approval}
      failure={state.failure}
      streamError={state.streamError}
      approvalDisabled={state.phase !== "awaiting_approval"}
      onApprove={vi.fn()}
      onCorrect={vi.fn()}
      onRequestChanges={vi.fn()}
    />,
  );
}

describe("ChatMessages", () => {
  it("renders hydrated history messages", () => {
    renderMessages({
      messages: [
        {
          role: "user",
          content: "Hello agent",
          created_at: "2026-01-01T00:00:00.000Z",
          structured_payload: null,
        },
        {
          role: "assistant",
          content: "Hello human",
          created_at: "2026-01-01T00:00:01.000Z",
          structured_payload: null,
        },
      ],
      phase: "idle",
    });

    expect(screen.getByText("Hello agent")).toBeInTheDocument();
    expect(screen.getByText("Hello human")).toBeInTheDocument();
  });

  it("renders partial assistant text while active", () => {
    renderMessages({
      phase: "active",
      streamingText: "Partial reply…",
      assistantStatus: "streaming",
    });

    expect(screen.getByTestId("chat-partial-text")).toHaveTextContent(
      "Partial reply…",
    );
  });

  it("renders active tool rows with friendly labels only", () => {
    renderMessages({
      phase: "active",
      tools: [
        {
          toolCallId: "secret-id-xyz",
          label: "Friendly tool",
          status: "running",
          durationMs: null,
          outcome: null,
        },
      ],
    });

    expect(screen.getByText(/Friendly tool/i)).toBeInTheDocument();
    expect(screen.queryByText("secret-id-xyz")).not.toBeInTheDocument();
  });

  it("renders approval summary when awaiting approval", () => {
    renderMessages({
      phase: "awaiting_approval",
      approval: createApprovalState({
        summary: "Approve this step?",
        approvalKind: null,
      }),
      assistantStatus: "waiting",
    });

    expect(screen.getByTestId("chat-approval-summary")).toHaveTextContent(
      "Approve this step?",
    );
  });

  it("renders profile approval card for profile_draft interrupts", () => {
    renderMessages({
      phase: "awaiting_approval",
      approval: createApprovalState({
        summary: "Review profile draft",
        approvalKind: "profile_draft",
        currentTitle: "Engineer",
        skillNames: ["Go"],
        instanceKey: "appr-1",
      }),
      assistantStatus: "waiting",
    });

    expect(screen.getByTestId("profile-approval-card")).toBeInTheDocument();
    expect(screen.getByTestId("profile-approval-save")).toBeInTheDocument();
    expect(
      screen.getByTestId("profile-approval-request-changes"),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/draft_id|\/var\/|raw_cv/i);
  });

  it("renders saved-job card from history structured_payload", () => {
    renderMessages({
      messages: [
        {
          role: "user",
          content: "Save this JD",
          created_at: "2026-01-01T00:00:00.000Z",
          structured_payload: null,
        },
        {
          role: "assistant",
          content: "Saved the job.",
          created_at: "2026-01-01T00:00:01.000Z",
          structured_payload: {
            kind: "saved_job",
            job_id: "33333333-3333-4333-8333-333333333333",
            title: "Platform Engineer",
            company: "Orbit",
            location: "Berlin",
            work_mode: "hybrid",
            employment_type: "full_time",
            jd_quality: "full",
            quality_reasons_preview: [],
            processing_result: "processed",
            duplicate_outcome: "none",
            graph_sync_status: "pending",
            source_url: "https://example.com/orbit",
          },
        },
      ],
      phase: "idle",
    });

    expect(screen.getByTestId("saved-job-card-1")).toBeInTheDocument();
    expect(screen.getByText("Platform Engineer")).toBeInTheDocument();
    expect(screen.getByText("Orbit")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(
      /raw_content|raw_jd|api_key|traceback|stack_trace/i,
    );
  });

  it("renders save-job tool activity with friendly label and outcome only", () => {
    renderMessages({
      phase: "active",
      tools: [
        {
          toolCallId: "internal-save-id",
          label: "Save job",
          status: "complete",
          durationMs: 120,
          outcome: "Exact duplicate",
        },
      ],
    });

    expect(screen.getByText(/Save job/i)).toBeInTheDocument();
    expect(screen.getByText(/Exact duplicate/i)).toBeInTheDocument();
    expect(screen.queryByText("internal-save-id")).not.toBeInTheDocument();
  });

  it("renders failure and disconnect system states", () => {
    const { rerender } = render(
      <ChatMessages
        messages={[]}
        phase="failed"
        streamingText=""
        tools={[]}
        assistantStatus={null}
        assistantStatusMessage={null}
        approval={null}
        failure={{ errorCode: "TOOL_LOOP_LIMIT_EXCEEDED", message: "Too many tools" }}
        streamError={null}
        approvalDisabled
        onApprove={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );
    expect(screen.getByTestId("chat-failure")).toHaveTextContent("Too many tools");

    rerender(
      <ChatMessages
        messages={[]}
        phase="disconnected"
        streamingText=""
        tools={[]}
        assistantStatus={null}
        assistantStatusMessage={null}
        approval={null}
        failure={null}
        streamError="disconnected"
        approvalDisabled
        onApprove={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );
    expect(screen.getByTestId("chat-disconnect")).toBeInTheDocument();
  });
});
