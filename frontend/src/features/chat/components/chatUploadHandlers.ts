/**
 * Shared CV upload start helpers for sidebar (turn) vs composer (token only).
 * Parent owns uploadReducer + begin/end in-flight guard.
 */

import type { StagedAttachmentResponse } from "../../profile/contracts";
import type { UploadAction } from "../../profile/state/uploadState";

export type DispatchUpload = (action: UploadAction) => void;

export async function runSidebarCvUpload(args: {
  readonly file: File;
  readonly beginUpload: () => boolean;
  readonly endUpload: () => void;
  readonly runUpload: (file: File) => Promise<StagedAttachmentResponse>;
  readonly dispatchUpload: DispatchUpload;
  readonly submitSidebarCvTurn: (attachmentId: string, text: string) => boolean;
  readonly sidebarTurnText: string;
}): Promise<void> {
  if (!args.beginUpload()) {
    return;
  }
  args.dispatchUpload({ type: "UPLOAD_START", fileName: args.file.name });
  try {
    const staged = await args.runUpload(args.file);
    const accepted = args.submitSidebarCvTurn(staged.id, args.sidebarTurnText);
    if (!accepted) {
      args.dispatchUpload({
        type: "UPLOAD_ERROR",
        code: "turn_not_accepted",
        message:
          "Upload completed but the chat could not accept the profile turn.",
      });
      return;
    }
    args.dispatchUpload({
      type: "UPLOAD_SUCCESS",
      attachmentId: staged.id,
      fileName: staged.original_name,
    });
  } catch (error: unknown) {
    dispatchUploadError(args.dispatchUpload, error);
  } finally {
    args.endUpload();
  }
}

export async function runComposerCvUpload(args: {
  readonly file: File;
  readonly beginUpload: () => boolean;
  readonly endUpload: () => void;
  readonly runUpload: (file: File) => Promise<StagedAttachmentResponse>;
  readonly dispatchUpload: DispatchUpload;
}): Promise<void> {
  if (!args.beginUpload()) {
    return;
  }
  args.dispatchUpload({ type: "UPLOAD_START", fileName: args.file.name });
  try {
    const staged = await args.runUpload(args.file);
    args.dispatchUpload({
      type: "UPLOAD_SUCCESS",
      attachmentId: staged.id,
      fileName: staged.original_name,
    });
  } catch (error: unknown) {
    dispatchUploadError(args.dispatchUpload, error);
  } finally {
    args.endUpload();
  }
}

function dispatchUploadError(
  dispatchUpload: DispatchUpload,
  error: unknown,
): void {
  if (error instanceof DOMException && error.name === "AbortError") {
    dispatchUpload({ type: "RESET" });
    return;
  }
  const code =
    error && typeof error === "object" && "code" in error
      ? String((error as { code: unknown }).code)
      : "upload_failed";
  const message = error instanceof Error ? error.message : "Upload failed";
  dispatchUpload({ type: "UPLOAD_ERROR", code, message });
}
