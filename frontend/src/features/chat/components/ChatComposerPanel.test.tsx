import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  createInitialUploadState,
  type UploadState,
} from "../../profile/state/uploadState";
import { ChatComposerPanel } from "./ChatComposerPanel";

function renderPanel(opts: {
  uploadState?: UploadState;
  onUploadFile?: (file: File) => void;
  onRemoveUpload?: () => void;
  onSubmit?: (value: string) => void;
  isDisabled?: boolean;
  focusRequestKey?: number;
}) {
  return render(
    <ChatComposerPanel
      value=""
      onChange={vi.fn()}
      onSubmit={opts.onSubmit ?? vi.fn()}
      isDisabled={opts.isDisabled ?? false}
      uploadState={opts.uploadState}
      onUploadFile={opts.onUploadFile}
      onRemoveUpload={opts.onRemoveUpload}
      focusRequestKey={opts.focusRequestKey}
    />,
  );
}

describe("ChatComposerPanel", () => {
  it("shows a removable PDF token when upload state is uploaded", () => {
    const onRemove = vi.fn();
    const uploadState: UploadState = {
      ...createInitialUploadState(),
      phase: "uploaded",
      fileName: "resume.pdf",
      attachmentId: "att-1",
    };

    renderPanel({
      uploadState,
      onUploadFile: vi.fn(),
      onRemoveUpload: onRemove,
    });

    expect(screen.getByTestId("chat-cv-token")).toHaveTextContent("resume.pdf");
    // Token remove is the X control associated with the token.
    const token = screen.getByTestId("chat-cv-token");
    const removeBtn = token.querySelector("button");
    expect(removeBtn).toBeTruthy();
    fireEvent.click(removeBtn!);
    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it("does not put attachment id or path into visible chat token label", () => {
    const uploadState: UploadState = {
      ...createInitialUploadState(),
      phase: "uploaded",
      fileName: "cv.pdf",
      attachmentId: "uuid-secret-attachment",
    };
    renderPanel({
      uploadState,
      onUploadFile: vi.fn(),
      onRemoveUpload: vi.fn(),
    });
    expect(screen.getByTestId("chat-cv-token")).toHaveTextContent("cv.pdf");
    expect(document.body.textContent).not.toMatch(
      /uuid-secret-attachment|\/tmp\/|storage_path/i,
    );
  });

  it("renders attach control when upload handler is provided", () => {
    renderPanel({
      uploadState: createInitialUploadState(),
      onUploadFile: vi.fn(),
    });
    expect(screen.getByTestId("chat-cv-upload")).toBeInTheDocument();
  });
});
