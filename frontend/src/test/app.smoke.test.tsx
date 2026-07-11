import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App shell smoke", () => {
  it("renders the base Astryx chat shell as the first screen", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Start a conversation/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });
});
