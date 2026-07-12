/**
 * Frontend matching workflow: raw SSE → parser → reducer → MatchCard.
 * Fake-backed only; no network. Covers live card, history hydrate, malformed,
 * duplicate events, tool failure, disconnect, and leakage sentinels.
 */

import { fireEvent, render, screen } from "@testing-library/react";
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
import { sampleMatchWire } from "../features/jobs/components/matchFixtures";

const RUN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const JOB = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const TS = "2026-03-01T10:00:00.000Z";

const LEAK =
  /raw_content|raw_jd|RAW_JD|api_key|sk-live|Traceback|stack_trace|Authorization: Bearer|document_text|arguments|vector_values/i;

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

function liveMatchFrames(matchPayload: Record<string, unknown>): ChatSSEEvent[] {
  return [
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
        tool_call_id: "t-match",
        label: "Match jobs",
        status: "running",
      },
    }),
    evt({
      event: "tool_completed",
      event_id: "e4",
      payload: {
        tool_call_id: "t-match",
        label: "Match jobs",
        status: "complete",
        duration_ms: 150,
        outcome: "Matches found",
      },
    }),
    evt({
      event: "text_delta",
      event_id: "e5",
      payload: { delta: "Here are your top matches." },
    }),
    evt({
      event: "run_completed",
      event_id: "e6",
      payload: { match_results: matchPayload },
    }),
  ];
}

describe("matching-workflow integration", () => {
  it("parses live SSE frames into the same match card as history", () => {
    const matchPayload = sampleMatchWire(JOB);
    const frames = liveMatchFrames(matchPayload);

    // Raw JSON SSE path (same as wire).
    const rawCompleted = JSON.stringify({
      event: "run_completed",
      event_id: "e6",
      run_id: RUN,
      timestamp: TS,
      payload: { match_results: matchPayload },
    });
    const parsedCompleted = parseChatSSEData(rawCompleted);
    expect(parsedCompleted.event).toBe("run_completed");
    if (parsedCompleted.event === "run_completed") {
      expect(parsedCompleted.payload.match_results).toMatchObject({
        kind: "match_results",
        count: 1,
      });
    }

    const live = reduceAll(frames);
    expect(live.phase).toBe("completed");
    expect(live.messages.at(-1)?.structured_payload).toMatchObject({
      kind: "match_results",
      count: 1,
      results: [{ job_id: JOB, title: "Backend Engineer", final_score: 0.85 }],
    });
    expect(JSON.stringify(live.messages.at(-1)?.structured_payload)).not.toMatch(
      LEAK,
    );

    const liveView = renderState(live);
    expect(screen.getByTestId("match-card-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("match-card-0-0-title")).toHaveTextContent(
      "Backend Engineer",
    );
    expect(screen.getByTestId("match-card-0-0-company")).toHaveTextContent(
      "Acme Corp",
    );
    expect(screen.getByText(/Score 85%/i)).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
    expect(screen.getByText("Java")).toBeInTheDocument();
    expect(screen.getByText("https://example.com/jobs/backend")).toBeInTheDocument();

    // Expand breakdown (Collapsible keeps content mounted; assert a11y state).
    const breakdownTrigger = screen.getByRole("button", {
      name: /Score breakdown/i,
    });
    expect(breakdownTrigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(breakdownTrigger);
    expect(breakdownTrigger).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByTestId("match-card-0-0-breakdown-body"),
    ).toBeInTheDocument();
    expect(screen.getByText("Semantic similarity")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(LEAK);
    liveView.unmount();

    // History hydrate path uses the same structured_payload shape.
    const hydrated = chatReducer(createInitialChatState(), {
      type: "HYDRATE_HISTORY",
      messages: [
        {
          role: "user",
          content: "Match me",
          created_at: TS,
          structured_payload: null,
        },
        {
          role: "assistant",
          content: "Here are your top matches.",
          created_at: TS,
          structured_payload: matchPayload,
        },
      ],
    });
    expect(hydrated.messages[1]?.structured_payload).toMatchObject({
      kind: "match_results",
      results: [{ job_id: JOB }],
    });

    // Render history identically to live validated card fields.
    renderState(hydrated);
    expect(screen.getByTestId("match-card-1-0")).toBeInTheDocument();
    expect(screen.getByTestId("match-card-1-0-title")).toHaveTextContent(
      "Backend Engineer",
    );
    expect(screen.getByText(/Score 85%/i)).toBeInTheDocument();
  });

  it("ignores duplicate event_ids and malformed match payloads", () => {
    const good = sampleMatchWire(JOB);
    let state = reduceAll([
      evt({ event: "run_started", event_id: "d1", payload: {} }),
      evt({
        event: "text_delta",
        event_id: "d2",
        payload: { delta: "Partial" },
      }),
      evt({
        event: "run_completed",
        event_id: "d3",
        payload: {
          match_results: {
            kind: "match_results",
            count: 1,
            results: [{ job_id: "bad", final_score: 99 }],
          },
        },
      }),
    ]);
    expect(state.phase).toBe("completed");
    expect(state.messages.at(-1)?.structured_payload).toBeNull();
    expect(state.messages.at(-1)?.content).toBe("Partial");

    // Duplicate completed with good payload is ignored (already terminal).
    state = chatReducer(state, {
      type: "SSE_EVENT",
      event: evt({
        event: "run_completed",
        event_id: "d4",
        payload: { match_results: good },
      }),
    });
    expect(state.messages.at(-1)?.structured_payload).toBeNull();

    // Duplicate event_id on live path
    let live = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    const completed = evt({
      event: "run_completed",
      event_id: "same",
      payload: { match_results: good },
    });
    live = chatReducer(live, {
      type: "SSE_EVENT",
      event: evt({ event: "run_started", event_id: "s", payload: {} }),
    });
    live = chatReducer(live, {
      type: "SSE_EVENT",
      event: evt({
        event: "text_delta",
        event_id: "t",
        payload: { delta: "Ok" },
      }),
    });
    live = chatReducer(live, { type: "SSE_EVENT", event: completed });
    const afterDup = chatReducer(live, { type: "SSE_EVENT", event: completed });
    expect(afterDup.messages).toHaveLength(live.messages.length);
    expect(afterDup.messages.at(-1)?.structured_payload).toMatchObject({
      kind: "match_results",
      results: [{ job_id: JOB }],
    });
  });

  it("never shows false success on tool failure or disconnect", () => {
    const failed = reduceAll([
      evt({ event: "run_started", event_id: "f1", payload: {} }),
      evt({
        event: "tool_started",
        event_id: "f2",
        payload: {
          tool_call_id: "tm",
          label: "Match jobs",
          status: "running",
        },
      }),
      evt({
        event: "tool_completed",
        event_id: "f3",
        payload: {
          tool_call_id: "tm",
          label: "Match jobs",
          status: "error",
          duration_ms: 10,
          outcome: "Match failed",
        },
      }),
      evt({
        event: "run_failed",
        event_id: "f4",
        payload: {
          error_code: "MATCH_JOBS_RETRIEVAL_FAILED",
          message: "Could not match jobs",
        },
      }),
    ]);
    expect(failed.phase).toBe("failed");
    expect(failed.failure?.errorCode).toBe("MATCH_JOBS_RETRIEVAL_FAILED");
    expect(
      failed.messages.some((m) => m.structured_payload?.kind === "match_results"),
    ).toBe(false);
    renderState(failed);
    expect(screen.getByTestId("chat-failure")).toHaveTextContent(
      "Could not match jobs",
    );
    expect(screen.queryByTestId(/match-card/)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(LEAK);

    let disconnected = chatReducer(createInitialChatState(), {
      type: "STREAM_OPEN",
    });
    disconnected = chatReducer(disconnected, {
      type: "SSE_EVENT",
      event: evt({ event: "run_started", event_id: "x1", payload: {} }),
    });
    disconnected = chatReducer(disconnected, {
      type: "SSE_EVENT",
      event: evt({
        event: "tool_started",
        event_id: "x2",
        payload: {
          tool_call_id: "tm2",
          label: "Match jobs",
          status: "running",
        },
      }),
    });
    disconnected = chatReducer(disconnected, {
      type: "STREAM_DISCONNECTED",
    });
    expect(disconnected.phase).toBe("disconnected");
    expect(
      disconnected.messages.some(
        (m) => m.structured_payload?.kind === "match_results",
      ),
    ).toBe(false);
    const { unmount } = render(
      <ChatMessages
        messages={disconnected.messages}
        phase={disconnected.phase}
        streamingText={disconnected.streamingText}
        tools={disconnected.tools}
        assistantStatus={disconnected.assistantStatus}
        assistantStatusMessage={disconnected.assistantStatusMessage}
        approval={null}
        failure={null}
        streamError="disconnected"
        approvalDisabled
        onApprove={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );
    expect(screen.getByTestId("chat-disconnect")).toBeInTheDocument();
    expect(screen.queryByTestId(/match-card/)).not.toBeInTheDocument();
    unmount();
  });

  it("rejects oversized match payload and private source URLs", () => {
    const wire = sampleMatchWire(JOB);
    const results = wire.results as Record<string, unknown>[];
    results[0] = {
      ...results[0],
      source_url: "http://localhost/private",
    };
    const live = reduceAll(liveMatchFrames(wire));
    expect(live.messages.at(-1)?.structured_payload).toMatchObject({
      kind: "match_results",
      results: [{ source_url: null }],
    });
    renderState(live);
    expect(screen.queryByText(/localhost/i)).not.toBeInTheDocument();
  });
});
