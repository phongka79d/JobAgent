import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "../app/App";

describe("App shell smoke", () => {
  it("renders the neutral Astryx shell without product workflows", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { level: 1, name: "JobAgent" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/product workflows are intentionally disabled/i),
    ).toBeInTheDocument();
  });
});
