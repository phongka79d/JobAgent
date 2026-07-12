import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MatchCard } from "./MatchCard";
import { sampleMatchResult } from "./matchFixtures";

describe("MatchCard", () => {
  it("renders source-required fields via Card and MetadataList", () => {
    render(<MatchCard match={sampleMatchResult()} />);

    expect(screen.getByTestId("match-card")).toBeInTheDocument();
    expect(screen.getByTestId("match-card-title")).toHaveTextContent(
      "Backend Engineer",
    );
    expect(screen.getByTestId("match-card-company")).toHaveTextContent(
      "Acme Corp",
    );
    expect(screen.getAllByText("Remote").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Score 85%/i)).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
    expect(screen.getByText("Java")).toBeInTheDocument();
    expect(screen.getByTestId("match-card-source")).toHaveTextContent(
      "https://example.com/jobs/backend",
    );
  });

  it("omits related skills when empty and drops unsafe source", () => {
    render(
      <MatchCard
        match={sampleMatchResult({
          relatedSkills: [],
          sourceUrl: null,
        })}
      />,
    );

    expect(screen.queryByText("Related verified")).not.toBeInTheDocument();
    expect(screen.queryByTestId("match-card-source")).not.toBeInTheDocument();
  });

  it("exposes expandable score breakdown without raw sentinels", () => {
    render(<MatchCard match={sampleMatchResult()} />);

    const trigger = screen.getByRole("button", { name: /Score breakdown/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByTestId("match-card-breakdown-body"),
    ).toBeInTheDocument();
    expect(screen.getByText("Semantic similarity")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(
      /raw_content|raw_jd|api_key|traceback|vector|provisional/i,
    );
  });

  it("uses no raw layout div for structure", () => {
    const { container } = render(<MatchCard match={sampleMatchResult()} />);
    expect(container.querySelector("[data-testid='match-card']")).not.toBeNull();
    expect(
      container.querySelector("[data-testid='match-card-metadata']"),
    ).not.toBeNull();
  });
});
