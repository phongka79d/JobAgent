/**
 * Approved-profile sidebar with the observability inspector.
 * Profile and upload state stay here; presentation and inspector state are delegated.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {VStack} from '@astryxdesign/core/VStack';
import {Icon} from '@astryxdesign/core/Icon';
import {NavIcon} from '@astryxdesign/core/NavIcon';
import {
  SideNav,
  SideNavCollapseButton,
  SideNavHeading,
  useSideNavCollapse,
  useSideNavRenderMode,
} from '@astryxdesign/core/SideNav';

import type {ObservabilityApi} from '../observability/api';
import type {CvManagerApi} from '../cv-manager/api';
import {CvManagerDrawer} from '../cv-manager/CvManagerDrawer';
import {useCvManagerState} from '../cv-manager/state';
import {
  createEmptySavedJobsController,
  type SavedJobsController,
} from '../jobs/savedJobsState';
import type {CvTailoringController} from '../cv-tailoring/state';
import {ObservabilitySidebar} from '../observability/ObservabilitySidebar';
import {useObservabilityState} from '../observability/state';
import {
  ChatApiError,
  fetchActiveProfileCompat,
  getActiveCvUrl,
  uploadCv,
} from './api';
import {ProfileOverviewPanel} from './ProfileOverviewPanel';
import {ProfileConversationSidebar} from './ProfileConversationSidebar';
import type {CvUploadResponse, ProfileReadResponse} from './types';
import type {ProfileWorkspaceController} from './workspaceState';

export type CvSidebarDeps = {
  loadProfile?: typeof fetchActiveProfileCompat;
  uploadCv?: typeof uploadCv;
  getActiveCvUrl?: typeof getActiveCvUrl;
  observability?: Partial<ObservabilityApi>;
  cvManager?: Partial<CvManagerApi>;
};

/** Terminal notice from ChatPage reprocess stream (clear pending / record error). */
export type CvReprocessTerminalNotice = {
  requestKey: number;
  profileId: string;
  kind: 'completed' | 'failed' | 'interrupted' | 'http_error';
  error?: {code: string; summary: string};
};

export type CvSidebarProps = {
  /** True while a run is connecting/streaming/interrupted - disables upload. */
  isUploadDisabled: boolean;
  /** Called after a successful upload so the chat can start an ID-only turn. */
  onSidebarUploadSuccess: (result: CvUploadResponse) => void;
  /**
   * CV Manager reprocess request → App → ChatPage stream path.
   * Returns false when composition refuses (locked/duplicate).
   */
  onCvReprocess?: (profileId: string) => boolean;
  /** After confirmed delete success (profile summary may need refresh). */
  onCvDeleted?: () => void;
  /** Latest reprocess terminal event from ChatPage (via App). */
  reprocessTerminal?: CvReprocessTerminalNotice | null;
  /** Increment / change to force a profile reload (e.g. after Save Profile). */
  refreshKey?: number;
  /**
   * Increment after activation (Save Profile) so CV Manager caches invalidate
   * without changing selection until approved data reloads.
   */
  activationKey?: number;
  /**
   * Increment after activation / chat zero-result save/evaluate so sidebar-local
   * saved-JD state marks list/detail non-current (no remount, no second store).
   */
  savedJobsInvalidateKey?: number;
  workspace?: ProfileWorkspaceController;
  savedJobs?: SavedJobsController;
  onCreateTailoredCv?: (jobId: string) => void;
  isTailoringPending?: boolean;
  tailoring?: CvTailoringController;
  onOpenTailoringSession?: (sessionId: string) => void;
  deps?: CvSidebarDeps;
};

function profileStateLabel(profile: ProfileReadResponse | null): {
  text: string;
  variant: 'success' | 'neutral' | 'warning' | 'error';
} {
  if (profile === null) {
    return {text: 'Loading...', variant: 'neutral'};
  }
  if (profile.present) {
    const title = profile.profile?.current_title?.trim();
    return {
      text: title ? `Active - ${title}` : 'Active profile',
      variant: 'success',
    };
  }
  if (profile.draft_present) {
    return {
      text: 'Draft ready - click Save Profile in chat',
      variant: 'warning',
    };
  }
  return {text: 'No approved profile', variant: 'neutral'};
}

function SidebarCollapseControl() {
  const {isCollapsed} = useSideNavCollapse();
  return (
    <SideNavCollapseButton
      aria-expanded={!isCollapsed}
      data-testid="jobagent-sidebar-collapse"
    />
  );
}

function CvSidebarShell({children}: {children?: ReactNode}) {
  const viewportWidth = window.innerWidth;

  return (
    <SideNav
      resizable={{
        defaultWidth: Math.round(viewportWidth * 0.6),
        minWidth: 360,
        maxWidth: Math.round(viewportWidth * 0.72),
        autoSaveId: 'jobagent-observability-sidebar-width-v2',
      }}
      collapsible={{hasButton: false}}
      className="jobagent-cv-sidebar-shell"
      header={
        <SideNavHeading
          heading="JobAgent"
          subheading="CV & profile"
          icon={<NavIcon icon={<Icon icon="search" />} />}
        />
      }
      footerIcons={<SidebarCollapseControl />}
      data-testid="jobagent-cv-sidebar"
    >
      {children}
    </SideNav>
  );
}

export function CvSidebar(props: CvSidebarProps) {
  const renderMode = useSideNavRenderMode();

  if (renderMode === 'topbar') {
    return <CvSidebarShell />;
  }

  return <CvSidebarController {...props} />;
}

function CvSidebarController({
  isUploadDisabled,
  onSidebarUploadSuccess,
  onCvReprocess,
  onCvDeleted,
  reprocessTerminal = null,
  refreshKey = 0,
  activationKey = 0,
  savedJobsInvalidateKey = 0,
  workspace,
  savedJobs,
  onCreateTailoredCv,
  isTailoringPending = false,
  tailoring,
  onOpenTailoringSession,
  deps,
}: CvSidebarProps) {
  const selectedWorkspaceProfile = workspace?.state.profiles.find(
    (candidate) => candidate.id === workspace.state.activeProfileId,
  );
  const observability = useObservabilityState({
    api: deps?.observability,
    profileId: selectedWorkspaceProfile?.id,
    profileReady: workspace ? selectedWorkspaceProfile?.state === 'ready' : true,
  });
  const cvManager = useCvManagerState({
    api: deps?.cvManager,
    profileId: selectedWorkspaceProfile?.id,
    profileReady: selectedWorkspaceProfile?.state === 'ready',
  });
  const [isCvManagerOpen, setIsCvManagerOpen] = useState(false);
  const {endReprocess, failReprocess, invalidateAfterActivation} = observability;
  const loadProfile = deps?.loadProfile ?? fetchActiveProfileCompat;
  const doUpload = deps?.uploadCv ?? uploadCv;
  const cvUrl = deps?.getActiveCvUrl ?? getActiveCvUrl;

  const [profile, setProfile] = useState<ProfileReadResponse | null>(null);
  const profileScope = workspace?.state.activeProfileId ?? 'legacy';
  const [loadedProfileScope, setLoadedProfileScope] = useState<string | null>(
    null,
  );
  const scopedProfile =
    loadedProfileScope === profileScope ? profile : null;
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const loadedRefreshKey = useRef(refreshKey);
  const loadedActivationKey = useRef(activationKey);
  const handledTerminalKey = useRef<number | null>(null);

  // After Save Profile activation: invalidate CV/chunk/run/graph caches only.
  useEffect(() => {
    if (loadedActivationKey.current === activationKey) {
      return;
    }
    loadedActivationKey.current = activationKey;
    invalidateAfterActivation();
  }, [activationKey, invalidateAfterActivation]);

  // Clear reprocess pending / record transport error from ChatPage terminal.
  useEffect(() => {
    if (!reprocessTerminal) {
      return;
    }
    if (handledTerminalKey.current === reprocessTerminal.requestKey) {
      return;
    }
    handledTerminalKey.current = reprocessTerminal.requestKey;
    const actionId =
      scopedProfile?.active_attachment?.id ?? reprocessTerminal.profileId;
    if (reprocessTerminal.kind === 'http_error' && reprocessTerminal.error) {
      failReprocess(actionId, reprocessTerminal.error);
    } else {
      endReprocess(actionId);
    }
  }, [endReprocess, failReprocess, reprocessTerminal, scopedProfile]);

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await loadProfile(signal);
        if (!signal?.aborted) {
          setProfile(next);
          setLoadedProfileScope(profileScope);
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
    [loadProfile, profileScope],
  );

  useEffect(() => {
    const isRefreshRequested = loadedRefreshKey.current !== refreshKey;
    loadedRefreshKey.current = refreshKey;
    const isProfileScopeChanged = loadedProfileScope !== profileScope;
    if (profile !== null && !isRefreshRequested && !isProfileScopeChanged) {
      return;
    }

    const controller = new AbortController();
    void reload(controller.signal);
    return () => {
      controller.abort();
    };
  }, [loadedProfileScope, profile, profileScope, reload, refreshKey]);

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
        onSidebarUploadSuccess(result);
        await reload();
      } catch (err) {
        const code = err instanceof ChatApiError ? err.code : 'UPLOAD_FAILED';
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'CV upload failed';
        setUploadError(`${summary} (${code})`);
      } finally {
        setIsUploading(false);
      }
    },
    [doUpload, isUploadDisabled, isUploading, onSidebarUploadSuccess, reload],
  );

  const handleRetryUpload = useCallback(
    async (target: {id: string}, file: File) => {
      if (isUploadDisabled || isUploading) return;
      setIsUploading(true);
      setUploadError(null);
      try {
        const result = await doUpload(file);
        const expectedConversationId = workspace?.state.conversations.find(
          (conversation) => conversation.profile_id === target.id,
        )?.id;
        if (
          result.outcome !== 'retry_pending' ||
          result.bootstrap?.profile.id !== target.id ||
          result.bootstrap.conversation.profile_id !== target.id ||
          result.bootstrap.conversation.id !== expectedConversationId ||
          !result.bootstrap.start_extraction
        ) {
          throw new Error('Retry upload returned inconsistent profile ownership');
        }
        onSidebarUploadSuccess(result);
        await reload();
      } catch (err) {
        const code = err instanceof ChatApiError ? err.code : 'UPLOAD_FAILED';
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'CV upload failed';
        setUploadError(`${summary} (${code})`);
      } finally {
        setIsUploading(false);
      }
    },
    [
      doUpload,
      isUploadDisabled,
      isUploading,
      onSidebarUploadSuccess,
      reload,
      workspace,
    ],
  );

  const handleViewDownload = useCallback(() => {
    if (!scopedProfile?.present || !scopedProfile.active_attachment) {
      return;
    }
    window.open(cvUrl(), '_blank', 'noopener,noreferrer');
  }, [cvUrl, scopedProfile]);

  const handleCvManagerDeleted = useCallback(() => {
    void reload();
    onCvDeleted?.();
  }, [onCvDeleted, reload]);

  const state = profileStateLabel(scopedProfile);
  const activeName = scopedProfile?.active_attachment?.original_name ?? null;
  const pendingName = scopedProfile?.pending_attachment?.original_name ?? null;
  const displayCvName = activeName ?? pendingName;
  const hasActive = Boolean(profile?.present && activeName);
  const uploadLabel = hasActive ? 'Upload new CV' : 'Upload CV';
  const disabledReason = isUploadDisabled
    ? 'Upload is disabled while a run is active or waiting for approval'
    : undefined;
  const cvName = displayCvName
    ? hasActive
      ? displayCvName
      : `${displayCvName} (staged - not saved)`
    : 'No active CV';

  const overview = (
    <VStack gap={4} width="100%">
      {workspace ? (
        <ProfileConversationSidebar
          workspace={workspace}
          isInteractionLocked={isUploadDisabled}
          onReextract={(target) => {
            if (
              target.id === workspace.state.activeProfileId &&
              scopedProfile?.active_attachment
            ) {
              onCvReprocess?.(target.id);
            }
          }}
          onRetryUpload={handleRetryUpload}
          onProfileDeleted={onCvDeleted}
        />
      ) : null}
      <ProfileOverviewPanel
        stateLabel={state.text}
        stateVariant={state.variant}
        cvName={cvName}
        selectedFile={selectedFile}
        loadError={loadError}
        uploadError={uploadError}
        uploadLabel={uploadLabel}
        isUploadDisabled={isUploadDisabled}
        isUploading={isUploading}
        disabledReason={disabledReason}
        canViewDownload={hasActive}
        onFileChange={handleFileChange}
        onUpload={handleUpload}
        onViewDownload={handleViewDownload}
        onManageCvs={() => {
          setIsCvManagerOpen(true);
          void cvManager.open();
        }}
      />
      <CvManagerDrawer
        isOpen={isCvManagerOpen}
        onOpenChange={setIsCvManagerOpen}
        controller={cvManager}
        onCvReprocess={(attachmentId) => {
          const item = cvManager.state.items.find((candidate) => candidate.id === attachmentId);
          if (item?.profile_id) onCvReprocess?.(item.profile_id);
        }}
        onActivateProfile={(attachmentId) => {
          const item = cvManager.state.items.find((candidate) => candidate.id === attachmentId);
          if (item?.profile_id) void workspace?.activate(item.profile_id);
        }}
        onDeleted={handleCvManagerDeleted}
      />
    </VStack>
  );

  return (
    <CvSidebarShell>
      <ObservabilitySidebar
        overview={overview}
        collapsedStatus={{
          label: state.text,
          variant: state.variant,
          cvName: displayCvName,
        }}
        observability={observability}
        savedJobs={savedJobs ?? createEmptySavedJobsController()}
        profileSetupInProgress={Boolean(
          workspace && selectedWorkspaceProfile?.state !== 'ready',
        )}
        profileId={selectedWorkspaceProfile?.id ?? null}
        profileDisplayName={selectedWorkspaceProfile?.display_name ?? ''}
        onProfileDelete={
          workspace
            ? async (profileId) => workspace.deleteProfile(profileId)
            : undefined
        }
        isInteractionLocked={isUploadDisabled}
        savedJobsInvalidateKey={savedJobsInvalidateKey}
        onCvReprocess={(attachmentId) =>
          selectedWorkspaceProfile
            ? onCvReprocess?.(selectedWorkspaceProfile.id) ?? false
            : onCvReprocess?.(attachmentId) ?? false
        }
        onCvDeleted={onCvDeleted}
        onCreateTailoredCv={onCreateTailoredCv}
        isTailoringPending={isTailoringPending}
        tailoring={tailoring}
        onOpenTailoringSession={onOpenTailoringSession}
      />
    </CvSidebarShell>
  );
}
