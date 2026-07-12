/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import {
  createInitialUploadState,
  isUploadInFlight,
  uploadReducer,
} from "./uploadState";

describe("uploadReducer", () => {
  it("starts idle and tracks upload success with attachment id", () => {
    const idle = createInitialUploadState();
    expect(idle.phase).toBe("idle");
    expect(isUploadInFlight(idle)).toBe(false);

    const uploading = uploadReducer(idle, {
      type: "UPLOAD_START",
      fileName: "a.pdf",
    });
    expect(uploading.phase).toBe("uploading");
    expect(uploading.fileName).toBe("a.pdf");
    expect(uploading.attachmentId).toBeNull();
    expect(isUploadInFlight(uploading)).toBe(true);

    const uploaded = uploadReducer(uploading, {
      type: "UPLOAD_SUCCESS",
      attachmentId: "id-1",
      fileName: "a.pdf",
    });
    expect(uploaded.phase).toBe("uploaded");
    expect(uploaded.attachmentId).toBe("id-1");
    expect(isUploadInFlight(uploaded)).toBe(false);
  });

  it("supports replacement by clearing the prior attachment while uploading", () => {
    const prior = uploadReducer(createInitialUploadState(), {
      type: "UPLOAD_SUCCESS",
      attachmentId: "old",
      fileName: "old.pdf",
    });
    const replacing = uploadReducer(prior, {
      type: "UPLOAD_START",
      fileName: "new.pdf",
    });
    expect(replacing.phase).toBe("uploading");
    expect(replacing.attachmentId).toBeNull();
    expect(replacing.fileName).toBe("new.pdf");
  });

  it("records errors and recovers via remove/reset", () => {
    const uploading = uploadReducer(createInitialUploadState(), {
      type: "UPLOAD_START",
      fileName: "bad.pdf",
    });
    const failed = uploadReducer(uploading, {
      type: "UPLOAD_ERROR",
      code: "MALFORMED_PDF",
      message: "MALFORMED_PDF",
    });
    expect(failed.phase).toBe("error");
    expect(failed.errorCode).toBe("MALFORMED_PDF");
    expect(failed.attachmentId).toBeNull();

    const cleared = uploadReducer(failed, { type: "REMOVE" });
    expect(cleared).toEqual(createInitialUploadState());

    const reset = uploadReducer(failed, { type: "RESET" });
    expect(reset.phase).toBe("idle");
  });
});
