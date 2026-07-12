/**
 * Frontend Job workflow path: raw SSE → parser → reducer → ChatMessages card.
 * Fake-backed only; no network. Covers live card, history hydrate, malformed,
 * duplicate events, and leakage sentinels.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatMessages } from "../features/chat/components/ChatMessages";
import {
  parseChatSSEData,
  type ChatSSEEvent,
} from "../features/chat/contracts";
import {
  chatReducer,
  createInitialChatState,
  type ChatState,
} from "../features/chat/reducer";

const RUN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const JOB = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const TS = "2026-03-01T10:00:00.000Z";

const LEAK =
  /raw_content|raw_jd|RAW_JD|api_key|sk-live|Traceback|stack_trace|Authorization: Bearer|document_text|arguments/i;

function evt(partial: Partial<ChatSSEEvent> & Pick<ChatSSEEvent, "event">): ChatSSEEvent {
  const base = {
    event_id: partial.event_id ?? `e-${partial.event}`,
    run_id: partial.run_id ?? RUN,
    timestamp: partial.timestamp ?? TS,
  };
  return { ...base, ...partial } as ChatSSEEvent;
}

function reduceAll(events: readonly ChatSSEEvent[]): ChatState {
  let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
  for (const event of events) {
    state = chatReducer(state, { type: "SSE_EVENT", event });
  }
  return state;
}

function renderState(state: ChatState) {
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
      approvalDisabled
      onApprove={vi.fn()}
      onCorrect={vi.fn()}
    />,
  );
}

const savedJobPayload = {
  kind: "saved_job",
  job_id: JOB,
  title: "Staff Engineer",
  company: "Northwind",
  location: "Seattle",
  work_mode: "remote",
  employment_type: "full_time",
  jd_quality: "full",
  quality_reasons_preview: [],
  processing_result: "processed",
  duplicate_outcome: "none",
  graph_sync_status: "pending",
  source_url: "https://example.com/jobs/staff",
};

describe("job-workflow integration", () => {
  it("parses live SSE frames into the same saved-job card as history", () => {
    const frames = [
      evt({ event: "run_started", event_id: "e1", payload: {} }),
      evt({
        event: "assistant_status",
        event_id: "e2",
        payload: { status: "working", message: null },
      }),
      evt({
        event: "tool_started",
        event_id: "e3",
        payload: {
          tool_call_id: "t1",
          label: "Save job",
          status: "running",
        },
      }),
      evt({
        event: "tool_completed",
        event_id: "e4",
        payload: {
          tool_call_id: "t1",
          label: "Save job",
          status: "complete",
          duration_ms: 88,
          outcome: "Job saved",
        },
      }),
      evt({
        event: "text_delta",
        event_id: "e5",
        payload: { delta: "I saved that role." },
      }),
      evt({
        event: "run_completed",
        event_id: "e6",
        payload: { saved_job: savedJobPayload },
      }),
    ];

    // Wire-format round-trip through parser (fail closed on garbage).
    const parsed = frames.map((frame) =>
      parseChatSSEData(JSON.stringify(frame)),
    );
    expect(parsed.map((e) => e.event)).toEqual([
      "run_started",
      "assistant_status",
      "tool_started",
      "tool_completed",
      "text_delta",
      "run_completed",
    ]);

    const live = reduceAll(parsed);
    expect(live.phase).toBe("completed");
    expect(live.tools[0]).toMatchObject({
      label: "Save job",
      status: "complete",
      outcome: "Job saved",
      durationMs: 88,
    });
    expect(live.messages.at(-1)?.structured_payload).toMatchObject({
      kind: "saved_job",
      job_id: JOB,
      title: "Staff Engineer",
    });

    const liveView = renderState(live);
    expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
    expect(screen.getByText("Northwind")).toBeInTheDocument();
    expect(screen.getByText(/I saved that role/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(LEAK);
    liveView.unmount();

    // History hydrate path uses the same structured_payload shape.
    const hydrated = chatReducer(createInitialChatState(), {
      type: "HYDRATE_HISTORY",
      messages: [
        {
          role: "user",
          content: "save job",
          created_at: TS,
          structured_payload: null,
        },
        {
          role: "assistant",
          content: "I saved that role.",
          created_at: TS,
          structured_payload: {
            ...savedJobPayload,
          },
        },
      ],
    });
    const histView = renderState(hydrated);
    expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
    expect(screen.getByText("https://example.com/jobs/staff")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(LEAK);
    histView.unmount();
  });

  it("keeps duplicate/unscorable/graph-failed outcomes understandable", () => {
    const variants: Array<{
      outcome: string;
      quality: string;
      duplicate: string;
      graph: string;
    }> = [
      {
        outcome: "Exact duplicate",
        quality: "full",
        duplicate: "exact",
        graph: "not_required",
      },
      {
        outcome: "Unscorable",
        quality: "unscorable",
        duplicate: "none",
        graph: "not_required",
      },
      {
        outcome: "Job saved graph failed",
        quality: "partial",
        duplicate: "none",
        graph: "failed",
      },
    ];

    for (const v of variants) {
      const state = reduceAll([
        evt({ event: "run_started", event_id: `s-${v.outcome}`, payload: {} }),
        evt({
          event: "tool_started",
          event_id: `ts-${v.outcome}`,
          payload: {
            tool_call_id: "t1",
            label: "Save job",
            status: "running",
          },
        }),
        evt({
          event: "tool_completed",
          event_id: `tc-${v.outcome}`,
          payload: {
            tool_call_id: "t1",
            label: "Save job",
            status: "complete",
            duration_ms: 10,
            outcome: v.outcome,
          },
        }),
        evt({
          event: "text_delta",
          event_id: `d-${v.outcome}`,
          payload: { delta: "Done." },
        }),
        evt({
          event: "run_completed",
          event_id: `c-${v.outcome}`,
          payload: {
            saved_job: {
              ...savedJobPayload,
              jd_quality: v.quality,
              duplicate_outcome: v.duplicate,
              graph_sync_status: v.graph,
              quality_reasons_preview:
                v.quality === "unscorable" ? ["missing skills"] : [],
            },
          },
        }),
      ]);
      expect(state.tools[0]?.outcome).toBe(v.outcome);
      expect(state.messages.at(-1)?.structured_payload).toMatchObject({
        kind: "saved_job",
        jd_quality: v.quality,
        duplicate_outcome: v.duplicate,
        graph_sync_status: v.graph,
      });
    }
  });

  it("ignores duplicate event_ids and malformed saved_job payloads", () => {
    const open = evt({ event: "run_started", event_id: "dup-1", payload: {} });
    const delta = evt({
      event: "text_delta",
      event_id: "dup-2",
      payload: { delta: "Hello" },
    });
    const complete = evt({
      event: "run_completed",
      event_id: "dup-3",
      payload: {
        saved_job: {
          kind: "saved_job",
          job_id: "not-a-uuid",
          processing_result: "processed",
          duplicate_outcome: "none",
          graph_sync_status: "pending",
          raw_content: "RAW_JD_BODY",
          api_key: "sk-live-secret",
        },
      },
    });

    const state = reduceAll([open, delta, complete, complete]);
    expect(state.phase).toBe("completed");
    expect(state.messages.at(-1)?.content).toBe("Hello");
    expect(state.messages.at(-1)?.structured_payload).toBeNull();
    expect(JSON.stringify(state)).not.toMatch(LEAK);

    // Replaying seen ids is a pure no-op.
    const again = chatReducer(state, { type: "SSE_EVENT", event: complete });
    expect(again).toEqual(state);
  });

  it("never surfaces raw JD or secrets in tool activity mapping", () => {
    const state = reduceAll([
      evt({ event: "run_started", event_id: "r1", payload: {} }),
      evt({
        event: "tool_started",
        event_id: "r2",
        payload: {
          tool_call_id: "internal-id-secret",
          label: "Save job",
          status: "running",
        },
      }),
      evt({
        event: "tool_completed",
        event_id: "r3",
        payload: {
          tool_call_id: "internal-id-secret",
          label: "Save job",
          status: "complete",
          duration_ms: 5,
          outcome: "Duplicate ignored",
        },
      }),
    ]);

    render(
      <ChatMessages
        messages={[]}
        phase="active"
        streamingText=""
        tools={state.tools}
        assistantStatus="working"
        assistantStatusMessage={null}
        approval={null}
        failure={null}
        streamError={null}
        approvalDisabled
        onApprove={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );

    expect(screen.getByText(/Save job/i)).toBeInTheDocument();
    expect(screen.getByText(/Duplicate ignored/i)).toBeInTheDocument();
    expect(screen.queryByText("internal-id-secret")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(LEAK);
  });

  it("disconnect mid-save keeps prior tool status and never leaks raw frames", () => {
    let state = reduceAll([
      evt({ event: "run_started", event_id: "d1", payload: {} }),
      evt({
        event: "tool_started",
        event_id: "d2",
        payload: {
          tool_call_id: "t-save",
          label: "Save job",
          status: "running",
        },
      }),
    ]);
    expect(state.phase).toBe("active");
    expect(state.tools[0]?.status).toBe("running");

    state = chatReducer(state, { type: "STREAM_DISCONNECTED" });
    expect(state.phase).toBe("disconnected");
    expect(state.streamError).toBeTruthy();
    // In-flight tool row retained for context; no raw payload fields.
    expect(state.tools[0]?.label).toBe("Save job");
    expect(JSON.stringify(state)).not.toMatch(LEAK);

    const view = renderState(state);
    expect(screen.getByTestId("chat-disconnect")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(LEAK);
    view.unmount();

    // History hydrate after disconnect restores a completed saved-job card.
    const recovered = chatReducer(createInitialChatState(), {
      type: "HYDRATE_HISTORY",
      messages: [
        {
          role: "user",
          content: "save this role",
          created_at: TS,
          structured_payload: null,
        },
        {
          role: "assistant",
          content: "Saved.",
          created_at: TS,
          structured_payload: { ...savedJobPayload },
        },
      ],
    });
    const recoveredView = renderState(recovered);
    expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(LEAK);
    recoveredView.unmount();
  });
});
