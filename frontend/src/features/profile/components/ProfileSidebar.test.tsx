import type { ReactElement } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Theme } from "@astryxdesign/core";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";

import type { ProfileResponse } from "../contracts";
import { createInitialUploadState, uploadReducer } from "../state/uploadState";
import { ProfileSidebar } from "./ProfileSidebar";

function wrap(ui: ReactElement) {
  return render(
    <Theme theme={neutralTheme} mode="light">
      {ui}
    </Theme>,
  );
}

const noneProfile: ProfileResponse = {
  state: "none",
  profile: null,
  preferences: null,
  active_attachment: null,
};

const activeProfile: ProfileResponse = {
  state: "active",
  profile: { summary: "Engineer" },
  preferences: null,
  active_attachment: {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    original_name: "resume.pdf",
    mime_type: "application/pdf",
    size_bytes: 20,
    page_count: 1,
    state: "active",
  },
};

describe("ProfileSidebar", () => {
  it("renders only authorized profile fields and active CV link", () => {
    wrap(
      <ProfileSidebar
        profile={activeProfile}
        uploadState={createInitialUploadState()}
        onUploadFile={vi.fn()}
        activeCvHref="http://127.0.0.1:8000/api/profile/cv"
      />,
    );

    expect(screen.getByTestId("profile-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("profile-state-label")).toHaveTextContent(
      /Profile active/i,
    );
    expect(screen.getByText("resume.pdf")).toBeInTheDocument();
    const link = screen.getByTestId("profile-cv-download");
    expect(link).toHaveAttribute("href", "http://127.0.0.1:8000/api/profile/cv");
    expect(screen.queryByText(/editor|preferences|draft_id|storage_path/i)).not.toBeInTheDocument();
  });

  it("shows no-profile state and empty CV without a download link", () => {
    wrap(
      <ProfileSidebar
        profile={noneProfile}
        uploadState={createInitialUploadState()}
        onUploadFile={vi.fn()}
        activeCvHref={null}
      />,
    );
    expect(screen.getByTestId("profile-state-label")).toHaveTextContent(
      /No profile yet/i,
    );
    expect(screen.getByTestId("profile-cv-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("profile-cv-download")).not.toBeInTheDocument();
  });

  it("invokes shared onUploadFile when a PDF is selected", () => {
    const onUploadFile = vi.fn();
    wrap(
      <ProfileSidebar
        profile={noneProfile}
        uploadState={createInitialUploadState()}
        onUploadFile={onUploadFile}
        activeCvHref={null}
      />,
    );

    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement | null;
    expect(input).not.toBeNull();
    const file = new File(["%PDF-1.4"], "new.pdf", { type: "application/pdf" });
    fireEvent.change(input!, { target: { files: [file] } });
    expect(onUploadFile).toHaveBeenCalledTimes(1);
    expect(onUploadFile.mock.calls[0]?.[0]).toBeInstanceOf(File);
    expect((onUploadFile.mock.calls[0]?.[0] as File).name).toBe("new.pdf");
  });

  it("surfaces upload error status from the shared upload state machine", () => {
    const errorState = uploadReducer(
      uploadReducer(createInitialUploadState(), {
        type: "UPLOAD_START",
        fileName: "bad.pdf",
      }),
      { type: "UPLOAD_ERROR", code: "MALFORMED_PDF", message: "MALFORMED_PDF" },
    );
    wrap(
      <ProfileSidebar
        profile={noneProfile}
        uploadState={errorState}
        onUploadFile={vi.fn()}
        activeCvHref={null}
      />,
    );
    expect(screen.getByText(/MALFORMED_PDF/i)).toBeInTheDocument();
  });
});
