/**
 * Chat composer panel: documented ChatComposer with optional CV PDF token drawer.
 * Upload uses shared 05B client/state (parent-owned); never stores bytes/path/hash.
 */

import { useEffect, useRef, useState } from "react";

import {
  ChatComposer,
  ChatComposerDrawer,
} from "@astryxdesign/core/Chat";
import { FileInput } from "@astryxdesign/core/FileInput";
import { Token } from "@astryxdesign/core/Token";

import type { UploadState } from "../../profile/state/uploadState";
import { isUploadInFlight } from "../../profile/state/uploadState";

const MAX_PDF_BYTES = 10 * 1024 * 1024;

export interface ChatComposerPanelProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: (value: string) => void;
  readonly onStop?: () => void;
  /** Conflicting send disabled while active or awaiting approval (unless correction). */
  readonly isDisabled: boolean;
  /** Show stop while a generation stream is active (not approval wait). */
  readonly isStopShown?: boolean;
  readonly placeholder?: string;
  readonly status?: { type: "error" | "warning"; message?: string };
  /** Shared CV upload machine (same state as sidebar). */
  readonly uploadState?: UploadState;
  /** Composer-path upload: stage attachment only (no immediate chat turn). */
  readonly onUploadFile?: (file: File) => void | Promise<void>;
  /** Remove staged PDF token before send. */
  readonly onRemoveUpload?: () => void;
  /** Bumps to focus the main composer input (profile Request Changes). */
  readonly focusRequestKey?: number;
  readonly "data-testid"?: string;
}

export function ChatComposerPanel({
  value,
  onChange,
  onSubmit,
  onStop,
  isDisabled,
  isStopShown = false,
  placeholder = "Message JobAgent…",
  status,
  uploadState,
  onUploadFile,
  onRemoveUpload,
  focusRequestKey = 0,
  "data-testid": testId = "chat-composer",
}: ChatComposerPanelProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const lastFocusKey = useRef(0);

  useEffect(() => {
    if (!focusRequestKey || focusRequestKey === lastFocusKey.current) {
      return;
    }
    lastFocusKey.current = focusRequestKey;
    // Focus the controlled composer textbox after Request Changes.
    const root = document.querySelector(`[data-testid="${testId}"]`);
    if (!(root instanceof HTMLElement)) {
      return;
    }
    const textbox = root.querySelector(
      '[contenteditable="true"], textarea, [role="textbox"]',
    );
    if (textbox instanceof HTMLElement) {
      textbox.focus();
    }
  }, [focusRequestKey, testId]);

  const inFlight = uploadState ? isUploadInFlight(uploadState) : false;
  const tokenFileName =
    uploadState &&
    (uploadState.phase === "uploaded" || uploadState.phase === "uploading")
      ? uploadState.fileName
      : null;
  const hasToken = Boolean(tokenFileName);
  const showUploadUi = Boolean(onUploadFile);

  let fileStatus:
    | { type: "error" | "warning" | "success"; message?: string }
    | undefined;
  if (uploadState?.phase === "error") {
    fileStatus = {
      type: "error",
      message: uploadState.errorMessage ?? uploadState.errorCode ?? "Upload failed",
    };
  } else if (uploadState?.phase === "uploaded") {
    fileStatus = { type: "success", message: "PDF ready to send" };
  }

  const handleFileChange = (files: File | File[] | null): void => {
    const file = Array.isArray(files) ? (files[0] ?? null) : files;
    setSelectedFile(file);
    if (file) {
      void onUploadFile?.(file);
    } else {
      onRemoveUpload?.();
    }
  };

  const drawer =
    showUploadUi && (hasToken || uploadState?.phase === "error") ? (
      <ChatComposerDrawer
        count={hasToken ? 1 : undefined}
        label="Attachments"
        defaultIsCollapsed={false}
        data-testid="chat-composer-drawer"
      >
        {tokenFileName ? (
          <Token
            label={tokenFileName}
            size="md"
            color="blue"
            description="PDF attachment for the next message"
            onRemove={
              uploadState?.phase === "uploaded" && onRemoveUpload
                ? () => {
                    setSelectedFile(null);
                    onRemoveUpload();
                  }
                : undefined
            }
            isDisabled={inFlight}
            data-testid="chat-cv-token"
          />
        ) : null}
      </ChatComposerDrawer>
    ) : undefined;

  const headerActions = showUploadUi ? (
    <FileInput
      label="Attach CV PDF"
      isLabelHidden
      value={selectedFile}
      onChange={handleFileChange}
      accept="application/pdf,.pdf"
      maxSize={MAX_PDF_BYTES}
      mode="input"
      isLoading={inFlight}
      isDisabled={isDisabled || inFlight}
      disabledMessage="Upload is unavailable while the chat is busy."
      placeholder="Attach PDF"
      status={fileStatus}
      data-testid="chat-cv-upload"
    />
  ) : undefined;

  return (
    <ChatComposer
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      onStop={onStop}
      isStopShown={isStopShown}
      isDisabled={isDisabled}
      placeholder={placeholder}
      status={status}
      statusPosition="top"
      density="balanced"
      drawer={drawer}
      headerActions={headerActions}
      data-testid={testId}
    />
  );
}
