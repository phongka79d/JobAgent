/**
 * CV profile sidebar: active filename, profile state, upload/replace, view/download.
 * Uses only documented Astryx SideNav / FileInput / StatusDot / Token / Link APIs.
 */

import { useState } from "react";

import { FileInput } from "@astryxdesign/core/FileInput";
import { HStack } from "@astryxdesign/core/HStack";
import { Link } from "@astryxdesign/core/Link";
import { SideNav, SideNavHeading } from "@astryxdesign/core/SideNav";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";

import type { ProfileResponse } from "../contracts";
import type { UploadState } from "../state/uploadState";
import { isUploadInFlight } from "../state/uploadState";

const MAX_PDF_BYTES = 10 * 1024 * 1024;

export interface ProfileSidebarProps {
  readonly profile: ProfileResponse | null;
  readonly profileLoading?: boolean;
  readonly profileError?: string | null;
  readonly uploadState: UploadState;
  /** Shared upload entry — parent owns multipart client + state machine. */
  readonly onUploadFile: (file: File) => void | Promise<void>;
  /** Optional removal of a pending staged upload token (not active CV). */
  readonly onRemoveUpload?: () => void;
  /** Absolute safe URL for GET /api/profile/cv when an active CV exists. */
  readonly activeCvHref: string | null;
  readonly uploadDisabled?: boolean;
  readonly "data-testid"?: string;
}

function profileStatusLabel(profile: ProfileResponse | null): {
  variant: "success" | "neutral" | "warning" | "error";
  label: string;
  text: string;
} {
  if (!profile) {
    return { variant: "neutral", label: "Profile unknown", text: "Profile unknown" };
  }
  if (profile.state === "active") {
    return { variant: "success", label: "Profile active", text: "Profile active" };
  }
  return { variant: "neutral", label: "No profile", text: "No profile yet" };
}

/**
 * Side navigation content for the single AppShell.sideNav slot.
 * No raw layout divs; width uses SideNav documented defaults (no forced 256px).
 */
export function ProfileSidebar({
  profile,
  profileLoading = false,
  profileError = null,
  uploadState,
  onUploadFile,
  onRemoveUpload,
  activeCvHref,
  uploadDisabled = false,
  "data-testid": testId = "profile-sidebar",
}: ProfileSidebarProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const status = profileStatusLabel(profile);
  const activeName = profile?.active_attachment?.original_name ?? null;
  const pendingName =
    uploadState.phase === "uploaded" || uploadState.phase === "uploading"
      ? uploadState.fileName
      : null;
  const displayName = pendingName ?? activeName;
  const inFlight = isUploadInFlight(uploadState);
  const inputDisabled = uploadDisabled || inFlight;

  let fileStatus:
    | { type: "error" | "warning" | "success"; message?: string }
    | undefined;
  if (uploadState.phase === "error") {
    fileStatus = {
      type: "error",
      message: uploadState.errorMessage ?? uploadState.errorCode ?? "Upload failed",
    };
  } else if (uploadState.phase === "uploaded") {
    fileStatus = { type: "success", message: "CV uploaded" };
  }

  const handleChange = (files: File | File[] | null): void => {
    const file = Array.isArray(files) ? (files[0] ?? null) : files;
    setSelectedFile(file);
    if (file) {
      void onUploadFile(file);
    } else {
      onRemoveUpload?.();
    }
  };

  return (
    <SideNav
      collapsible
      header={<SideNavHeading heading="JobAgent" subheading="Candidate CV" />}
      data-testid={testId}
    >
      <VStack gap={4} data-testid="profile-sidebar-body">
        <VStack gap={2}>
          <Text type="label" as="p">
            Profile state
          </Text>
          <HStack gap={2} align="center">
            <StatusDot
              variant={status.variant}
              label={status.label}
              isPulsing={profileLoading || inFlight}
            />
            <Text type="supporting" as="span" data-testid="profile-state-label">
              {profileLoading ? "Loading profile…" : status.text}
            </Text>
          </HStack>
          {profileError ? (
            <Text type="supporting" color="secondary" data-testid="profile-load-error">
              {profileError}
            </Text>
          ) : null}
        </VStack>

        <VStack gap={2}>
          <Text type="label" as="p">
            Active CV
          </Text>
          {displayName ? (
            <Token
              label={displayName}
              size="md"
              color="blue"
              description="Active or staging CV filename"
              onRemove={
                uploadState.phase === "uploaded" && onRemoveUpload
                  ? () => {
                      setSelectedFile(null);
                      onRemoveUpload();
                    }
                  : undefined
              }
              data-testid="profile-cv-filename"
            />
          ) : (
            <Text type="supporting" data-testid="profile-cv-empty">
              No active CV
            </Text>
          )}
          {activeCvHref && profile?.active_attachment ? (
            <Link
              href={activeCvHref}
              isStandalone
              target="_blank"
              rel="noopener noreferrer"
              data-testid="profile-cv-download"
            >
              View / download active CV
            </Link>
          ) : null}
        </VStack>

        <FileInput
          label={activeName ? "Replace CV" : "Upload CV"}
          value={selectedFile}
          onChange={handleChange}
          accept="application/pdf,.pdf"
          maxSize={MAX_PDF_BYTES}
          mode="dropzone"
          isLoading={inFlight}
          isDisabled={inputDisabled}
          disabledMessage="Upload is unavailable while a request is in flight."
          description="PDF only, max 10 MB and 10 pages."
          placeholder="Choose PDF"
          status={fileStatus}
          data-testid="profile-cv-upload"
        />
      </VStack>
    </SideNav>
  );
}
