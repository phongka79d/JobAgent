import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ToolActivity } from "../reducer";
import { ChatToolActivity } from "./ChatToolActivity";
import {
  collectMappedToolVisibleStrings,
  formatToolDuration,
  mapToolsToChatCalls,
} from "./toolMapping";

const PROHIBITED = [
  "sk-live-secret",
  "Authorization",
  "Bearer ",
  "raw_args",
  "stack trace",
  "Traceback",
  "cv_pdf_body",
  "internal_tool_call_id_should_not_render",
];

describe("formatToolDuration", () => {
  it("formats milliseconds and seconds", () => {
    expect(formatToolDuration(null)).toBeUndefined();
    expect(formatToolDuration(340)).toBe("340ms");
    expect(formatToolDuration(1200)).toBe("1.2s");
    expect(formatToolDuration(15_000)).toBe("15s");
  });
});

describe("mapToolsToChatCalls", () => {
  it("maps only friendly label, status, duration, and short outcome", () => {
    const tools: ToolActivity[] = [
      {
        toolCallId: "internal_tool_call_id_should_not_render",
        label: "Lookup preferences",
        status: "complete",
        durationMs: 420,
        outcome: "Loaded 3 preferences",
      },
      {
        toolCallId: "t2",
        label: "Search",
        status: "error",
        durationMs: 90,
        outcome: "Timed out",
      },
      {
        toolCallId: "t3",
        label: "Working",
        status: "running",
        durationMs: null,
        outcome: null,
      },
    ];

    const calls = mapToolsToChatCalls(tools);
    expect(calls).toHaveLength(3);
    expect(calls[0]).toMatchObject({
      name: "Lookup preferences",
      status: "complete",
      duration: "420ms",
      target: "Loaded 3 preferences",
    });
    expect(calls[1]).toMatchObject({
      name: "Search",
      status: "error",
      duration: "90ms",
      errorMessage: "Timed out",
    });
    expect(calls[2]).toMatchObject({
      name: "Working",
      status: "running",
    });
    expect(calls[2].duration).toBeUndefined();
    expect(calls[2].target).toBeUndefined();

    const visible = collectMappedToolVisibleStrings(tools).join("\n");
    for (const bad of PROHIBITED) {
      if (bad === "internal_tool_call_id_should_not_render") {
        // key may equal toolCallId but must not appear as name/target/duration/status
        expect(calls[0].name).not.toContain(bad);
        expect(calls[0].target).not.toContain(bad);
        continue;
      }
      expect(visible).not.toContain(bad);
    }
  });

  it("never maps raw/private fields onto visible call props", () => {
    const tools: ToolActivity[] = [
      {
        toolCallId: "tc-uuid-1",
        label: "Safe tool",
        status: "complete",
        durationMs: 10,
        outcome: "ok",
      },
    ];
    const calls = mapToolsToChatCalls(tools);
    const serialized = JSON.stringify(calls);
    expect(serialized).not.toMatch(/sk-live|Authorization|raw_args|Traceback/i);
    expect(calls[0]).not.toHaveProperty("arguments");
    expect(calls[0]).not.toHaveProperty("raw");
  });

  it("sanitizes match_jobs label and allowlisted outcomes", () => {
    const tools: ToolActivity[] = [
      {
        toolCallId: "secret-match-call",
        label: "match_jobs",
        status: "complete",
        durationMs: 50,
        outcome: "matches_found",
      },
      {
        toolCallId: "secret-match-err",
        label: "Match jobs",
        status: "error",
        durationMs: 12,
        outcome: "match_failed",
      },
      {
        toolCallId: "secret-json",
        label: "match_jobs",
        status: "complete",
        durationMs: 1,
        outcome: '{"ok":true,"results":[],"raw_content":"RAW"}',
      },
    ];
    const calls = mapToolsToChatCalls(tools);
    expect(calls[0]).toMatchObject({
      name: "Match jobs",
      target: "Matches found",
    });
    expect(calls[1]).toMatchObject({
      name: "Match jobs",
      errorMessage: "Match failed",
    });
    expect(calls[2].name).toBe("Match jobs");
    expect(calls[2].target).toBeUndefined();
    const visible = collectMappedToolVisibleStrings(tools).join("\n");
    expect(visible).not.toContain("secret-match-call");
    expect(visible).not.toContain("raw_content");
    expect(visible).not.toContain("match_jobs");
  });
});

describe("ChatToolActivity", () => {
  it("renders tool label and sanitized status rows", () => {
    const tools: ToolActivity[] = [
      {
        toolCallId: "a",
        label: "Echo label",
        status: "running",
        durationMs: null,
        outcome: null,
      },
    ];
    render(<ChatToolActivity tools={tools} />);
    expect(screen.getByText(/Echo label/i)).toBeInTheDocument();
  });

  it("renders nothing when tools are empty", () => {
    const { container } = render(<ChatToolActivity tools={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
