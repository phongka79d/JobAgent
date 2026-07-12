import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fullComponents } from "./matchFixtures";
import { ScoreBreakdown } from "./ScoreBreakdown";

describe("ScoreBreakdown", () => {
  it("starts collapsed and expands to show component weights", () => {
    render(<ScoreBreakdown components={fullComponents()} />);

    const trigger = screen.getByRole("button", { name: /Score breakdown/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("score-breakdown-body")).toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByTestId("score-breakdown-progress-semantic_similarity"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("score-breakdown-row-skill_score"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Effective weight").length).toBeGreaterThan(0);
  });

  it("lists unavailable components without progress bars", () => {
    const components = fullComponents({
      location_score: { available: false },
      work_mode_score: { available: false },
    }).map((c) => {
      if (!c.available) {
        return c;
      }
      const map: Record<string, number> = {
        semantic_similarity: 0.3,
        skill_score: 0.4,
        seniority_score: 0.15,
        experience_score: 0.15,
      };
      return {
        ...c,
        effectiveWeight: map[c.name] ?? c.effectiveWeight,
      };
    });

    render(<ScoreBreakdown components={components} />);
    fireEvent.click(screen.getByText("Score breakdown"));
    expect(
      screen.getByTestId("score-breakdown-unavailable-location_score"),
    ).toHaveTextContent("Unavailable");
    expect(
      screen.getByTestId("score-breakdown-unavailable-work_mode_score"),
    ).toHaveTextContent("Unavailable");
  });
});
