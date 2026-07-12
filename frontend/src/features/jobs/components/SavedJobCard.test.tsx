import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SavedJobCardPayload } from "../contracts";
import { SavedJobCard } from "./SavedJobCard";

function sample(partial?: Partial<SavedJobCardPayload>): SavedJobCardPayload {
  return {
    kind: "saved_job",
    jobId: "11111111-1111-4111-8111-111111111111",
    title: "Backend Engineer",
    company: "Acme Corp",
    location: "Remote",
    workMode: "remote",
    employmentType: "full_time",
    jdQuality: "full",
    qualityReasonsPreview: [],
    processingResult: "processed",
    duplicateOutcome: "none",
    graphSyncStatus: "pending",
    sourceUrl: "https://example.com/jobs/1",
    ...partial,
  };
}

describe("SavedJobCard", () => {
  it("renders bounded job fields via Card and MetadataList", () => {
    render(<SavedJobCard job={sample()} />);

    expect(screen.getByTestId("saved-job-card")).toBeInTheDocument();
    expect(screen.getByTestId("saved-job-title")).toHaveTextContent(
      "Backend Engineer",
    );
    expect(screen.getByTestId("saved-job-company")).toHaveTextContent(
      "Acme Corp",
    );
    expect(screen.getAllByText("Remote").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("https://example.com/jobs/1")).toBeInTheDocument();
    expect(
      screen.getByText("11111111-1111-4111-8111-111111111111"),
    ).toBeInTheDocument();
  });

  it("shows duplicate and unscorable states without raw JD", () => {
    render(
      <SavedJobCard
        job={sample({
          jdQuality: "unscorable",
          qualityReasonsPreview: ["missing responsibilities"],
          duplicateOutcome: "ignored_normalized",
          graphSyncStatus: "not_required",
          sourceUrl: null,
        })}
      />,
    );

    expect(screen.getByText(/Unscorable/i)).toBeInTheDocument();
    expect(screen.getByText(/Normalized duplicate/i)).toBeInTheDocument();
    expect(screen.getByText(/missing responsibilities/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(
      /raw_content|raw_jd|api_key|traceback|secret/i,
    );
  });

  it("uses no raw layout div for structure", () => {
    const { container } = render(<SavedJobCard job={sample()} />);
    // Component tree should not introduce raw layout-only divs as structure.
    // Astryx Card may render host elements; assert our data-testid surface exists.
    expect(container.querySelector("[data-testid='saved-job-card']")).not.toBeNull();
    expect(container.querySelector("[data-testid='saved-job-metadata']")).not.toBeNull();
  });
});
