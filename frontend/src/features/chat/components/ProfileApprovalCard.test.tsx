import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApprovalState } from "../reducer";
import { ProfileApprovalCard } from "./ProfileApprovalCard";

describe("ProfileApprovalCard", () => {
  it("renders sanitized summary fields and exact Save / Request Changes actions", () => {
    const onSave = vi.fn();
    const onRequest = vi.fn();
    const approval = createApprovalState({
      summary: "Review candidate profile draft",
      approvalKind: "profile_draft",
      currentTitle: "Senior Engineer",
      skillNames: ["TypeScript", "Python"],
      experienceCount: 3,
      educationCount: 1,
      hasPreferenceChanges: true,
      targetRolesPreview: ["Backend"],
      instanceKey: "evt-1",
    });

    render(
      <ProfileApprovalCard
        approval={approval}
        isDisabled={false}
        onSaveProfile={onSave}
        onRequestChanges={onRequest}
      />,
    );

    expect(screen.getByTestId("profile-approval-summary")).toHaveTextContent(
      "Review candidate profile draft",
    );
    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.getByText(/TypeScript, Python/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Backend")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("profile-approval-save"));
    expect(onSave).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("profile-approval-request-changes"));
    expect(onRequest).toHaveBeenCalledTimes(1);

    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/draft_id|storage_path|email@|\/tmp\/|tool_args/i);
  });

  it("disables both actions when isDisabled (in-flight / post-action)", () => {
    const onSave = vi.fn();
    const onRequest = vi.fn();
    render(
      <ProfileApprovalCard
        approval={createApprovalState({
          summary: "Approve draft",
          approvalKind: "profile_draft",
          instanceKey: "evt-2",
        })}
        isDisabled
        onSaveProfile={onSave}
        onRequestChanges={onRequest}
      />,
    );

    const save = screen.getByTestId("profile-approval-save");
    const request = screen.getByTestId("profile-approval-request-changes");
    expect(save).toBeDisabled();
    expect(request).toBeDisabled();
    fireEvent.click(save);
    fireEvent.click(request);
    expect(onSave).not.toHaveBeenCalled();
    expect(onRequest).not.toHaveBeenCalled();
  });
});
