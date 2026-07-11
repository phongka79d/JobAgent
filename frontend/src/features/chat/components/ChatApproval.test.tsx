import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatApproval } from "./ChatApproval";

/** Fill the Astryx TextArea (native textarea) with correction text. */
function setCorrection(text: string): void {
  const field = screen.getByTestId("chat-approval-correction");
  const textarea =
    field.matches("textarea")
      ? (field as HTMLTextAreaElement)
      : field.querySelector("textarea");
  expect(textarea).toBeTruthy();
  fireEvent.change(textarea!, { target: { value: text } });
}

describe("ChatApproval", () => {
  it("renders summary and approve/correct actions with correction field", () => {
    const onApprove = vi.fn();
    const onCorrect = vi.fn();

    render(
      <ChatApproval
        approval={{ summary: "Apply profile draft?", approvalKind: "profile" }}
        isDisabled={false}
        onApprove={onApprove}
        onCorrect={onCorrect}
      />,
    );

    expect(screen.getByTestId("chat-approval-summary")).toHaveTextContent(
      "Apply profile draft?",
    );
    expect(screen.getByTestId("chat-approval-correction")).toBeInTheDocument();
    expect(screen.getByLabelText(/Correction/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("chat-approval-approve"));
    expect(onApprove).toHaveBeenCalledTimes(1);

    // Empty correction keeps Correct disabled and does not resume.
    const correct = screen.getByTestId("chat-approval-correct");
    expect(correct).toBeDisabled();
    fireEvent.click(correct);
    expect(onCorrect).not.toHaveBeenCalled();
  });

  it("disables Correct for blank/whitespace correction and shows no resume callback", () => {
    const onCorrect = vi.fn();

    render(
      <ChatApproval
        approval={{ summary: "Continue?", approvalKind: null }}
        isDisabled={false}
        onApprove={vi.fn()}
        onCorrect={onCorrect}
      />,
    );

    const correct = screen.getByTestId("chat-approval-correct");
    expect(correct).toBeDisabled();

    setCorrection("   \n\t  ");
    expect(correct).toBeDisabled();
    fireEvent.click(correct);
    expect(onCorrect).not.toHaveBeenCalled();
  });

  it("enables Correct with nonblank text and passes trimmed correction", () => {
    const onCorrect = vi.fn();

    render(
      <ChatApproval
        approval={{ summary: "Continue?", approvalKind: null }}
        isDisabled={false}
        onApprove={vi.fn()}
        onCorrect={onCorrect}
      />,
    );

    setCorrection("  Please use the senior title instead  ");
    const correct = screen.getByTestId("chat-approval-correct");
    expect(correct).not.toBeDisabled();
    fireEvent.click(correct);

    expect(onCorrect).toHaveBeenCalledTimes(1);
    expect(onCorrect).toHaveBeenCalledWith("Please use the senior title instead");
  });

  it("disables actions while resume is in flight", () => {
    const onApprove = vi.fn();
    const onCorrect = vi.fn();

    render(
      <ChatApproval
        approval={{ summary: "Continue?", approvalKind: null }}
        isDisabled
        onApprove={onApprove}
        onCorrect={onCorrect}
      />,
    );

    const approve = screen.getByTestId("chat-approval-approve");
    expect(approve).toBeDisabled();
    fireEvent.click(approve);
    expect(onApprove).not.toHaveBeenCalled();

    const correctionRoot = screen.getByTestId("chat-approval-correction");
    const textarea =
      correctionRoot.matches("textarea")
        ? (correctionRoot as HTMLTextAreaElement)
        : correctionRoot.querySelector("textarea");
    expect(textarea).toBeTruthy();
    expect(textarea).toBeDisabled();
  });
});
