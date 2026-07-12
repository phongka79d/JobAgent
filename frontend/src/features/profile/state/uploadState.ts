/**
 * Shared CV upload state machine for sidebar and chat composer.
 * Phases: idle → uploading → uploaded | error; supports removal and replacement.
 */

export type UploadPhase = "idle" | "uploading" | "uploaded" | "error";

export interface UploadState {
  readonly phase: UploadPhase;
  readonly fileName: string | null;
  readonly attachmentId: string | null;
  readonly errorCode: string | null;
  readonly errorMessage: string | null;
}

export type UploadAction =
  | { readonly type: "UPLOAD_START"; readonly fileName: string }
  | {
      readonly type: "UPLOAD_SUCCESS";
      readonly attachmentId: string;
      readonly fileName: string;
    }
  | {
      readonly type: "UPLOAD_ERROR";
      readonly code: string;
      readonly message?: string;
    }
  | { readonly type: "REMOVE" }
  | { readonly type: "RESET" };

export function createInitialUploadState(): UploadState {
  return {
    phase: "idle",
    fileName: null,
    attachmentId: null,
    errorCode: null,
    errorMessage: null,
  };
}

export function uploadReducer(
  state: UploadState,
  action: UploadAction,
): UploadState {
  switch (action.type) {
    case "UPLOAD_START":
      // Replacement clears prior attachment while a new upload is in flight.
      return {
        phase: "uploading",
        fileName: action.fileName,
        attachmentId: null,
        errorCode: null,
        errorMessage: null,
      };
    case "UPLOAD_SUCCESS":
      return {
        phase: "uploaded",
        fileName: action.fileName,
        attachmentId: action.attachmentId,
        errorCode: null,
        errorMessage: null,
      };
    case "UPLOAD_ERROR":
      return {
        phase: "error",
        fileName: state.fileName,
        attachmentId: null,
        errorCode: action.code,
        errorMessage: action.message ?? action.code,
      };
    case "REMOVE":
    case "RESET":
      return createInitialUploadState();
    default: {
      const _exhaustive: never = action;
      return _exhaustive;
    }
  }
}

/** True while an upload request must not be duplicated. */
export function isUploadInFlight(state: UploadState): boolean {
  return state.phase === "uploading";
}
