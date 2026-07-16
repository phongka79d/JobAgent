/**
 * Approved-profile sidebar (Master §15.2).
 * Shows only: active CV filename, profile state, upload/replace, view/download.
 * Upload uses the shared POST /api/attachments/cv path; success notifies parent
 * so ChatPage can start one concise turn with the returned attachment_id only.
 */

import {useCallback, useEffect, useState} from 'react';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {FileInput} from '@astryxdesign/core/FileInput';
import {SideNav, SideNavHeading} from '@astryxdesign/core/SideNav';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import {
  ChatApiError,
  fetchProfile,
  getActiveCvUrl,
  uploadCv,
} from './api';
import type {CvUploadResponse, ProfileReadResponse} from './types';

export type CvSidebarDeps = {
  loadProfile?: typeof fetchProfile;
  uploadCv?: typeof uploadCv;
  getActiveCvUrl?: typeof getActiveCvUrl;
};

export type CvSidebarProps = {
  /** True while a run is connecting/streaming/interrupted — disables upload. */
  isUploadDisabled: boolean;
  /** Called after a successful upload so the chat can start an ID-only turn. */
  onSidebarUploadSuccess: (result: CvUploadResponse) => void;
  /** Increment / change to force a profile reload (e.g. after Save Profile). */
  refreshKey?: number;
  deps?: CvSidebarDeps;
};

const MAX_PDF_BYTES = 10 * 1024 * 1024;

function profileStateLabel(profile: ProfileReadResponse | null): {
  text: string;
  variant: 'success' | 'neutral' | 'warning' | 'error';
} {
  if (profile === null) {
    return {text: 'Loading…', variant: 'neutral'};
  }
  if (profile.present) {
    const title = profile.profile?.current_title?.trim();
    return {
      text: title ? `Active · ${title}` : 'Active profile',
      variant: 'success',
    };
  }
  if (profile.draft_present) {
    return {
      text: 'Draft ready · click Save Profile in chat',
      variant: 'warning',
    };
  }
  return {text: 'No approved profile', variant: 'neutral'};
}

export function CvSidebar({
  isUploadDisabled,
  onSidebarUploadSuccess,
  refreshKey = 0,
  deps,
}: CvSidebarProps) {
  const loadProfile = deps?.loadProfile ?? fetchProfile;
  const doUpload = deps?.uploadCv ?? uploadCv;
  const cvUrl = deps?.getActiveCvUrl ?? getActiveCvUrl;

  const [profile, setProfile] = useState<ProfileReadResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await loadProfile(signal);
        if (!signal?.aborted) {
          setProfile(next);
          setLoadError(null);
        }
      } catch (err) {
        if (signal?.aborted) {
          return;
        }
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'Failed to load profile';
        setLoadError(summary);
      }
    },
    [loadProfile],
  );

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => {
      controller.abort();
    };
  }, [reload, refreshKey]);

  const handleFileChange = useCallback(
    (files: File | File[] | null) => {
      const file = Array.isArray(files) ? (files[0] ?? null) : files;
      setSelectedFile(file);
      setUploadError(null);
    },
    [],
  );

  const handleUpload = useCallback(
    async (files: File | File[] | null) => {
      const file = Array.isArray(files) ? (files[0] ?? null) : files;
      if (!file || isUploadDisabled || isUploading) {
        return;
      }
      setIsUploading(true);
      setUploadError(null);
      try {
        const result = await doUpload(file);
        setSelectedFile(null);
        // Refresh sidebar metadata after staging/active reuse.
        await reload();
        onSidebarUploadSuccess(result);
      } catch (err) {
        const code = err instanceof ChatApiError ? err.code : 'UPLOAD_FAILED';
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'CV upload failed';
        // Surface stable backend failures; never invent success.
        setUploadError(`${summary} (${code})`);
      } finally {
        setIsUploading(false);
      }
    },
    [doUpload, isUploadDisabled, isUploading, onSidebarUploadSuccess, reload],
  );

  const handleViewDownload = useCallback(() => {
    if (!profile?.present || !profile.active_attachment) {
      return;
    }
    // Navigate to the stream endpoint; browser handles Content-Disposition.
    // Do not fetch Blob into React state.
    const url = cvUrl();
    window.open(url, '_blank', 'noopener,noreferrer');
  }, [cvUrl, profile]);

  const state = profileStateLabel(profile);
  const activeName = profile?.active_attachment?.original_name ?? null;
  const pendingName = profile?.pending_attachment?.original_name ?? null;
  const displayCvName = activeName ?? pendingName;
  const hasActive = Boolean(profile?.present && activeName);
  const uploadLabel = hasActive ? 'Replace CV' : 'Upload CV';
  const disabledReason = isUploadDisabled
    ? 'Upload is disabled while a run is active or waiting for approval'
    : undefined;

  return (
    <SideNav
      collapsible
      header={
        <SideNavHeading
          heading="JobAgent"
          subheading="CV & profile"
        />
      }
      data-testid="jobagent-cv-sidebar"
    >
      <VStack
        gap={3}
        padding={3}
        width="100%"
        data-testid="jobagent-cv-sidebar-body"
      >
        <VStack gap={1}>
          <Text type="label" color="secondary">
            Profile state
          </Text>
          <HStack gap={2} vAlign="center">
            <StatusDot variant={state.variant} label={state.text} />
            <Text type="body" data-testid="jobagent-profile-state">
              {state.text}
            </Text>
          </HStack>
        </VStack>

        <VStack gap={1}>
          <Text type="label" color="secondary">
            Active CV
          </Text>
          <Text
            type="body"
            data-testid="jobagent-active-cv-filename"
            maxLines={2}
          >
            {displayCvName
              ? hasActive
                ? displayCvName
                : `${displayCvName} (staged · not saved)`
              : 'No active CV'}
          </Text>
        </VStack>

        {loadError ? (
          <Banner
            status="error"
            title="Profile load failed"
            description={loadError}
            container="card"
          />
        ) : null}

        {uploadError ? (
          <Banner
            status="error"
            title="Upload failed"
            description={uploadError}
            container="card"
            data-testid="jobagent-cv-upload-error"
          />
        ) : null}

        <FileInput
          label={uploadLabel}
          value={selectedFile}
          onChange={handleFileChange}
          changeAction={handleUpload}
          accept="application/pdf,.pdf"
          maxSize={MAX_PDF_BYTES}
          mode="input"
          isDisabled={isUploadDisabled || isUploading}
          disabledMessage={disabledReason}
          isLoading={isUploading}
          placeholder="Choose PDF…"
          description="PDF only, up to 10 MB / 10 pages"
          data-testid="jobagent-cv-upload"
        />

        <Button
          label="View / download CV"
          variant="secondary"
          size="sm"
          isDisabled={!hasActive}
          onClick={handleViewDownload}
          data-testid="jobagent-cv-download"
        />
      </VStack>
    </SideNav>
  );
}
