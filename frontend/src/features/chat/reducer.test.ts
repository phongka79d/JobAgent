/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import type { ChatSSEEvent, HistoryMessage } from "./contracts";
import {
  chatReducer,
  createInitialChatState,
  isSendDisabled,
  type ChatState,
} from "./reducer";

const RUN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const OTHER_RUN = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const TS = "2026-01-01T00:00:00+00:00";

function evt<E extends ChatSSEEvent>(partial: E): E {
  return partial;
}

function reduceAll(state: ChatState, events: ChatSSEEvent[]): ChatState {
  return events.reduce(
    (s, event) => chatReducer(s, { type: "SSE_EVENT", event }),
    state,
  );
}

describe("chatReducer", () => {
  it("starts idle with send enabled", () => {
    const state = createInitialChatState();
    expect(state.phase).toBe("idle");
    expect(isSendDisabled(state)).toBe(false);
  });

  it("hydrates durable history and clears transient run state", () => {
    const prior = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    const mid = chatReducer(prior, {
      type: "SSE_EVENT",
      event: evt({
        event: "run_started",
        event_id: "e1",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
    });
    const messages: HistoryMessage[] = [
      {
        role: "user",
        content: "hello",
        created_at: TS,
        structured_payload: null,
      },
      {
        role: "assistant",
        content: "hi",
        created_at: TS,
        structured_payload: null,
      },
    ];
    const hydrated = chatReducer(mid, { type: "HYDRATE_HISTORY", messages });
    expect(hydrated.messages).toEqual(messages);
    expect(hydrated.phase).toBe("idle");
    expect(hydrated.activeRunId).toBeNull();
    expect(hydrated.streamingText).toBe("");
    expect(isSendDisabled(hydrated)).toBe(false);
  });

  it("applies every event type in a legal stream", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "1",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "assistant_status",
        event_id: "2",
        run_id: RUN,
        timestamp: TS,
        payload: { status: "thinking", message: "Working" },
      }),
      evt({
        event: "tool_started",
        event_id: "3",
        run_id: RUN,
        timestamp: TS,
        payload: {
          tool_call_id: "t1",
          label: "Lookup",
          status: "running",
        },
      }),
      evt({
        event: "tool_completed",
        event_id: "4",
        run_id: RUN,
        timestamp: TS,
        payload: {
          tool_call_id: "t1",
          label: "Lookup",
          status: "complete",
          duration_ms: 12,
          outcome: "ok",
        },
      }),
      evt({
        event: "text_delta",
        event_id: "5",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: "Hello" },
      }),
      evt({
        event: "text_delta",
        event_id: "6",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: " world" },
      }),
      evt({
        event: "run_completed",
        event_id: "7",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
    ]);

    expect(state.phase).toBe("completed");
    expect(state.streamingText).toBe("Hello world");
    expect(state.tools).toHaveLength(1);
    expect(state.tools[0]).toMatchObject({
      toolCallId: "t1",
      status: "complete",
      durationMs: 12,
      outcome: "ok",
    });
    expect(state.messages.at(-1)?.content).toBe("Hello world");
    expect(isSendDisabled(state)).toBe(false);
  });

  it("ignores duplicate event_id (replay has no effect)", () => {
    const started = evt({
      event: "run_started",
      event_id: "dup",
      run_id: RUN,
      timestamp: TS,
      payload: {},
    });
    const delta = evt({
      event: "text_delta",
      event_id: "d1",
      run_id: RUN,
      timestamp: TS,
      payload: { delta: "A" },
    });
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [started, delta]);
    const again = reduceAll(state, [started, delta, delta]);
    expect(again).toEqual(state);
    expect(again.streamingText).toBe("A");
  });

  it("ordered deltas produce exactly one assistant text stream", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "text_delta",
        event_id: "d1",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: "partial" },
      }),
      evt({
        event: "text_delta",
        event_id: "d2",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: " text" },
      }),
    ]);
    expect(state.streamingText).toBe("partial text");
    expect(state.messages.filter((m) => m.role === "assistant")).toHaveLength(0);

    state = chatReducer(state, {
      type: "SSE_EVENT",
      event: evt({
        event: "run_completed",
        event_id: "done",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
    });
    const assistants = state.messages.filter((m) => m.role === "assistant");
    expect(assistants).toHaveLength(1);
    expect(assistants[0]?.content).toBe("partial text");
  });

  it("ignores foreign-run events after run is bound", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "text_delta",
        event_id: "foreign",
        run_id: OTHER_RUN,
        timestamp: TS,
        payload: { delta: "NOPE" },
      }),
      evt({
        event: "text_delta",
        event_id: "ok",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: "yes" },
      }),
    ]);
    expect(state.streamingText).toBe("yes");
  });

  it("ignores out-of-order events before run_started", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "text_delta",
        event_id: "early",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: "early" },
      }),
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "text_delta",
        event_id: "ok",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: "ok" },
      }),
    ]);
    expect(state.streamingText).toBe("ok");
  });

  it("tracks approval and disables send", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "approval_required",
        event_id: "a",
        run_id: RUN,
        timestamp: TS,
        payload: { summary: "Apply profile changes?", approval_kind: "profile" },
      }),
    ]);
    expect(state.phase).toBe("awaiting_approval");
    expect(state.approval).toEqual({
      summary: "Apply profile changes?",
      approvalKind: "profile",
      currentTitle: null,
      skillNames: [],
      experienceCount: null,
      educationCount: null,
      hasPreferenceChanges: null,
      targetRolesPreview: [],
      instanceKey: "a",
    });
    expect(isSendDisabled(state)).toBe(true);
  });

  it("stores bounded profile approval payload fields and instance key", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "approval_required",
        event_id: "profile-evt",
        run_id: RUN,
        timestamp: TS,
        payload: {
          summary: "Review candidate profile",
          approval_kind: "profile_draft",
          current_title: "Senior Engineer",
          skill_names: ["TypeScript", "Python"],
          experience_count: 2,
          education_count: 1,
          has_preference_changes: true,
          target_roles_preview: ["Backend"],
        },
      }),
    ]);
    expect(state.approval).toMatchObject({
      summary: "Review candidate profile",
      approvalKind: "profile_draft",
      currentTitle: "Senior Engineer",
      skillNames: ["TypeScript", "Python"],
      experienceCount: 2,
      educationCount: 1,
      hasPreferenceChanges: true,
      targetRolesPreview: ["Backend"],
      instanceKey: "profile-evt",
    });
  });

  it("surfaces terminal failure distinctly", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "run_failed",
        event_id: "f",
        run_id: RUN,
        timestamp: TS,
        payload: { error_code: "TOOL_LOOP_LIMIT_EXCEEDED", message: "Stopped" },
      }),
    ]);
    expect(state.phase).toBe("failed");
    expect(state.failure).toEqual({
      errorCode: "TOOL_LOOP_LIMIT_EXCEEDED",
      message: "Stopped",
    });
    expect(isSendDisabled(state)).toBe(false);
  });

  it("marks disconnect and re-enables send; reconnect hydrates history", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "text_delta",
        event_id: "d",
        run_id: RUN,
        timestamp: TS,
        payload: { delta: "partial" },
      }),
    ]);
    expect(isSendDisabled(state)).toBe(true);

    state = chatReducer(state, { type: "STREAM_DISCONNECTED" });
    expect(state.phase).toBe("disconnected");
    expect(state.streamingText).toBe("partial");
    expect(isSendDisabled(state)).toBe(false);

    const durable: HistoryMessage[] = [
      {
        role: "user",
        content: "hi",
        created_at: TS,
        structured_payload: null,
      },
    ];
    state = chatReducer(state, { type: "HYDRATE_HISTORY", messages: durable });
    expect(state.phase).toBe("idle");
    expect(state.messages).toEqual(durable);
    expect(state.streamingText).toBe("");
  });

  it("STREAM_ABORTED sets disconnected for abort cleanup", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = chatReducer(state, {
      type: "SSE_EVENT",
      event: evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
    });
    state = chatReducer(state, { type: "STREAM_ABORTED" });
    expect(state.phase).toBe("disconnected");
    expect(state.streamError).toBe("aborted");
    expect(isSendDisabled(state)).toBe(false);
  });

  it("does not leave completed/failed on disconnect", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = reduceAll(state, [
      evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
      evt({
        event: "run_completed",
        event_id: "c",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
    ]);
    const after = chatReducer(state, { type: "STREAM_DISCONNECTED" });
    expect(after.phase).toBe("completed");
  });

  it("active phase disables send", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    expect(state.phase).toBe("active");
    expect(isSendDisabled(state)).toBe(true);
    state = chatReducer(state, {
      type: "SSE_EVENT",
      event: evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
    });
    expect(isSendDisabled(state)).toBe(true);
  });

  it("RESET_RUN clears transient fields and enables send", () => {
    let state = chatReducer(createInitialChatState(), { type: "STREAM_OPEN" });
    state = chatReducer(state, {
      type: "SSE_EVENT",
      event: evt({
        event: "run_started",
        event_id: "s",
        run_id: RUN,
        timestamp: TS,
        payload: {},
      }),
    });
    state = chatReducer(state, { type: "RESET_RUN" });
    expect(state.phase).toBe("idle");
    expect(state.activeRunId).toBeNull();
    expect(isSendDisabled(state)).toBe(false);
  });
});
