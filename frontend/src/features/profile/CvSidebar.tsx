/**
 * Approved-profile sidebar with three product destinations.
 * App owns workspace, Saved Jobs, and tailoring state; this component composes them.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
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

import {defaultCvManagerApi, type CvManagerApi} from '../cv-manager/api';
import {CvManagerDrawer} from '../cv-manager/CvManagerDrawer';
import type {CvManagerController} from '../cv-manager/state';
import type {SavedJobsController} from '../jobs/savedJobsState';
import type {CvTailoringController} from '../cv-tailoring/state';
import {
  ProductSidebar,
  ProductSidebarContent,
  ProductSidebarNav,
  type ProductSidebarEditorMemory,
} from '../navigation/ProductSidebar';
import type {ProductDestination} from '../navigation/productNavigation';
import {
  ChatApiError,
  fetchActiveProfileCompat,
  getProfileUploadConflict,
  getActiveCvUrl,
  uploadCv,
} from './api';
import {ProfileOverviewPanel} from './ProfileOverviewPanel';
import {ProfileConversationSidebar} from './ProfileConversationSidebar';
import type {CvUploadResponse, ProfileReadResponse, ProfileUploadConflict} from './types';
import type {ProfileWorkspaceController} from './workspaceState';

export type CvSidebarDeps = {
  loadProfile?: typeof fetchActiveProfileCompat;
  uploadCv?: typeof uploadCv;
  getActiveCvUrl?: typeof getActiveCvUrl;
  cvManager?: Partial<CvManagerApi>;
};

export type CvSidebarProps = {
  /** True while a run is connecting/streaming/interrupted - disables upload. */
  isUploadDisabled: boolean;
  /** Called after a successful upload so the chat can start an ID-only turn. */
  onSidebarUploadSuccess: (result: CvUploadResponse) => void;
  /** After confirmed delete success (profile summary may need refresh). */
  onCvDeleted?: () => void;
  onProfileApproved?: () => void;
  onProfileDiscarded?: () => void;
  cvManager: CvManagerController;
  cvManagerOpenRequest?: {requestKey: number; profileId: string} | null;
  onProfileReextractConflict?: (operationId: string) => void | boolean | Promise<boolean>;
  onAgentPendingReview?: (profileId: string, revision: string) => void | boolean | Promise<boolean>;
  cvManagerRequest?: {requestKey: number; profileId: string; startAt: 'reextract'} | null;
  onCvManagerRequestHandled?: (requestKey: number) => void;
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
  savedJobsInvalidateKey: number;
  workspace: ProfileWorkspaceController;
  savedJobs: SavedJobsController;
  onCreateTailoredCv?: (jobId: string) => void;
  isTailoringPending?: boolean;
  tailoring: CvTailoringController;
  onOpenTailoringSession?: (sessionId: string) => void;
  editorMode?: boolean;
  selectedDestination?: ProductDestination;
  onSelectedDestinationChange?: (destination: ProductDestination) => void;
  editorMemoryRef?: MutableRefObject<ProductSidebarEditorMemory>;
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

function CvSidebarShell({
  children,
  mode = 'panel',
}: {
  children?: ReactNode;
  mode?: 'rail' | 'panel';
}) {
  const viewportWidth = window.innerWidth;
  const railWidth = Math.min(
    220,
    Math.max(180, Math.round(viewportWidth * 0.12)),
  );
  const panelWidth = Math.min(
    420,
    Math.max(320, Math.round(viewportWidth * 0.24)),
  );

  return (
    <SideNav
      resizable={{
        defaultWidth: mode === 'rail' ? railWidth : panelWidth,
        minWidth: mode === 'rail' ? 160 : 300,
        maxWidth: mode === 'rail' ? 240 : 460,
        // ponytail: Intentionally no autoSaveId: Astryx restores collapsed width 0 independently of SideNav collapse state.
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

function CvSidebarController(props: CvSidebarProps) {
  const workspace = useCvSidebarWorkspace(props);

  return (
    <CvSidebarShell>
      {workspace.legacySidebar}
      {workspace.drawer}
    </CvSidebarShell>
  );
}

export type CvSidebarWorkspace = {
  readonly sideNav: ReactNode;
  readonly workspacePanel: ReactNode;
  readonly drawer: ReactNode;
  readonly legacySidebar: ReactNode;
};

function CvWorkspaceSideNav({
  rail,
  drawer,
}: {
  rail: ReactNode;
  drawer: ReactNode;
}) {
  const renderMode = useSideNavRenderMode();
  const content =
    renderMode === 'drawer' || renderMode === 'drawer-content'
      ? drawer
      : rail;

  return (
    <CvSidebarShell mode={renderMode === 'default' ? 'rail' : 'panel'}>
      {content}
    </CvSidebarShell>
  );
}

export function useCvSidebarWorkspace({
  isUploadDisabled,
  onSidebarUploadSuccess,
  onCvDeleted,
  onProfileApproved,
  onProfileDiscarded,
  cvManager,
  cvManagerOpenRequest = null,
  onProfileReextractConflict,
  onAgentPendingReview,
  cvManagerRequest = null,
  onCvManagerRequestHandled,
  refreshKey = 0,
  activationKey = 0,
  savedJobsInvalidateKey,
  workspace,
  savedJobs,
  onCreateTailoredCv,
  isTailoringPending = false,
  tailoring,
  onOpenTailoringSession,
  editorMode = false,
  selectedDestination,
  onSelectedDestinationChange,
  editorMemoryRef,
  deps,
}: CvSidebarProps): CvSidebarWorkspace {
  const [uploadConflict, setUploadConflict] = useState<ProfileUploadConflict | null>(null);
  const [isCvManagerOpen, setIsCvManagerOpen] = useState(false);
  const [localProductDestination, setLocalProductDestination] =
    useState<ProductDestination>('overview');
  const productDestination = selectedDestination ?? localProductDestination;
  const setProductDestination = useCallback(
    (destination: ProductDestination) => {
      if (onSelectedDestinationChange) {
        onSelectedDestinationChange(destination);
      } else {
        setLocalProductDestination(destination);
      }
    },
    [onSelectedDestinationChange],
  );
  const localProductEditorMemoryRef =
    useRef<ProductSidebarEditorMemory>(null);
  const productEditorMemoryRef =
    editorMemoryRef ?? localProductEditorMemoryRef;
  const handledCvManagerRequests = useRef(new Set<number>());
  const handledCvManagerOpenRequests = useRef(new Set<number>());
  const loadProfile = deps?.loadProfile ?? fetchActiveProfileCompat;
  const doUpload = deps?.uploadCv ?? uploadCv;
  const cvUrl = deps?.getActiveCvUrl ?? getActiveCvUrl;
  const discardProfileReextractReview =
    deps?.cvManager?.discardProfileReextractReview ??
    defaultCvManagerApi.discardProfileReextractReview;

  const [profile, setProfile] = useState<ProfileReadResponse | null>(null);
  const profileScope = workspace.state.activeProfileId ?? 'legacy';
  const workspaceIsReady =
    workspace.state.phase === undefined || workspace.state.phase === 'ready';
  const [loadedProfileScope, setLoadedProfileScope] = useState<string | null>(
    null,
  );
  const scopedProfile =
    workspaceIsReady && loadedProfileScope === profileScope ? profile : null;
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDiscardingPendingReview, setIsDiscardingPendingReview] =
    useState(false);
  const [pendingReviewDiscardError, setPendingReviewDiscardError] = useState<
    string | null
  >(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const loadedRefreshKey = useRef(refreshKey);
  const loadedActivationKey = useRef(activationKey);

  useEffect(() => {
    setUploadError(null);
    setUploadConflict(null);
  }, [profileScope]);

  useEffect(() => {
    if (!workspaceIsReady) setLoadedProfileScope(null);
  }, [workspaceIsReady]);

  useEffect(() => {
    loadedActivationKey.current = activationKey;
  }, [activationKey]);

  useEffect(() => {
    if (!cvManagerRequest || handledCvManagerRequests.current.has(cvManagerRequest.requestKey)) return;
    if (cvManagerRequest.profileId !== workspace.state.activeProfileId) return;
    handledCvManagerRequests.current.add(cvManagerRequest.requestKey);
    setIsCvManagerOpen(true);
    void cvManager.open().then(() => cvManager.startReextract(cvManagerRequest.profileId));
    onCvManagerRequestHandled?.(cvManagerRequest.requestKey);
  }, [cvManager, cvManagerRequest, onCvManagerRequestHandled, workspace.state.activeProfileId]);

  useEffect(() => {
    if (!cvManagerOpenRequest || handledCvManagerOpenRequests.current.has(cvManagerOpenRequest.requestKey)) return;
    handledCvManagerOpenRequests.current.add(cvManagerOpenRequest.requestKey);
    if (cvManagerOpenRequest.profileId !== workspace.state.activeProfileId) return;
    setIsCvManagerOpen(true);
  }, [cvManagerOpenRequest, workspace.state.activeProfileId]);

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      if (!workspaceIsReady) return;
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
    [loadProfile, profileScope, workspaceIsReady],
  );

  useEffect(() => {
    if (!workspaceIsReady) return;
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
  }, [loadedProfileScope, profile, profileScope, reload, refreshKey, workspaceIsReady]);

  const handleFileChange = useCallback(
    (files: File | File[] | null) => {
      const file = Array.isArray(files) ? (files[0] ?? null) : files;
      setSelectedFile(file);
      setUploadError(null);
      setUploadConflict(null);
      setPendingReviewDiscardError(null);
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
        setUploadConflict(getProfileUploadConflict(err));
        if (code === 'PROFILE_REVIEW_PENDING') {
          await reload();
        }
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
        const expectedConversationId = workspace.state.conversations.find(
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

  const handleReviewPendingChanges = useCallback(() => {
    const pendingReview = scopedProfile?.pending_review;
    if (!pendingReview?.can_review) {
      return;
    }
    const controller = new AbortController();
    setIsCvManagerOpen(true);
    void cvManager.loadReview(
      pendingReview.profile_id,
      pendingReview.revision,
      controller.signal,
    );
  }, [cvManager, scopedProfile?.pending_review]);

  const handleDiscardPendingReview = useCallback(async () => {
    const pendingReview = scopedProfile?.pending_review;
    if (!pendingReview || isDiscardingPendingReview) {
      return;
    }
    const controller = new AbortController();
    setIsDiscardingPendingReview(true);
    setPendingReviewDiscardError(null);
    try {
      await discardProfileReextractReview(
        pendingReview.profile_id,
        pendingReview.revision,
        controller.signal,
      );
      setUploadError(null);
      await reload(controller.signal);
      onProfileDiscarded?.();
    } catch (err) {
      const summary =
        err instanceof ChatApiError
          ? err.summary
          : err instanceof Error
            ? err.message
            : 'Unable to discard the pending profile review';
      setPendingReviewDiscardError(summary);
    } finally {
      setIsDiscardingPendingReview(false);
    }
  }, [
    discardProfileReextractReview,
    isDiscardingPendingReview,
    onProfileDiscarded,
    reload,
    scopedProfile?.pending_review,
  ]);

  const handleProfileReviewDiscarded = useCallback(() => {
    setUploadError(null);
    setPendingReviewDiscardError(null);
    void reload();
    onProfileDiscarded?.();
  }, [onProfileDiscarded, reload]);

  const handleProfileReextractConflict = useCallback(async (operationId: string) => {
    if (!operationId) return;
    const opened = onProfileReextractConflict ? await onProfileReextractConflict(operationId) : true;
    if (opened === false) return;
    setIsCvManagerOpen(true);
  }, [onProfileReextractConflict]);

  const handleAgentPendingReview = useCallback(async (profileId: string, reviewRevision: string) => {
    if (profileId !== workspace.state.activeProfileId || !reviewRevision) return;
    const opened = onAgentPendingReview ? await onAgentPendingReview(profileId, reviewRevision) : true;
    if (opened === false) return;
    setIsCvManagerOpen(true);
  }, [onAgentPendingReview, workspace.state.activeProfileId]);

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
      <ProfileConversationSidebar
        workspace={workspace}
        isInteractionLocked={isUploadDisabled}
        onReextract={(target) => {
          if (
            target.id === workspace.state.activeProfileId &&
            scopedProfile?.active_attachment
          ) {
            setIsCvManagerOpen(true);
            void cvManager.startReextract(target.id);
          }
        }}
        onRetryUpload={handleRetryUpload}
        onProfileDeleted={onCvDeleted}
      />
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
        pendingReview={scopedProfile?.pending_review ?? null}
        uploadConflict={uploadConflict}
        isDiscardingPendingReview={isDiscardingPendingReview}
        pendingReviewDiscardError={pendingReviewDiscardError}
        canViewDownload={hasActive}
        onFileChange={handleFileChange}
        onUpload={handleUpload}
        onReviewPendingChanges={handleReviewPendingChanges}
        onProfileReextractConflict={handleProfileReextractConflict}
        onAgentPendingReview={handleAgentPendingReview}
        onDiscardPendingReview={handleDiscardPendingReview}
        onViewDownload={handleViewDownload}
        onManageCvs={() => {
          setIsCvManagerOpen(true);
          void cvManager.open();
        }}
      />
    </VStack>
  );

  const legacySidebar = (
    <ProductSidebar
      overview={overview}
      savedJobs={savedJobs}
      savedJobsInvalidateKey={savedJobsInvalidateKey}
      onCreateTailoredCv={onCreateTailoredCv}
      isTailoringPending={isTailoringPending}
      tailoring={tailoring}
      onOpenTailoringSession={onOpenTailoringSession}
      editorMode={editorMode}
      selectedDestination={productDestination}
      onSelectedDestinationChange={setProductDestination}
      editorMemoryRef={productEditorMemoryRef}
    />
  );
  const workspacePanel = (
    <ProductSidebarContent
      overview={overview}
      savedJobs={savedJobs}
      savedJobsInvalidateKey={savedJobsInvalidateKey}
      onCreateTailoredCv={onCreateTailoredCv}
      isTailoringPending={isTailoringPending}
      tailoring={tailoring}
      onOpenTailoringSession={onOpenTailoringSession}
      editorMode={editorMode}
      selectedDestination={productDestination}
    />
  );
  const sideNav = (
    <CvWorkspaceSideNav
      rail={
        <ProductSidebarNav
          selectedDestination={productDestination}
          onSelectedDestinationChange={setProductDestination}
          editorMode={editorMode}
          editorMemoryRef={productEditorMemoryRef}
        />
      }
      drawer={legacySidebar}
    />
  );
  const drawer = (
    <CvManagerDrawer
      isOpen={isCvManagerOpen}
      onOpenChange={setIsCvManagerOpen}
      controller={cvManager}
      onActivateProfile={(attachmentId) => {
        const item = cvManager.state.items.find(
          (candidate) => candidate.id === attachmentId,
        );
        if (item?.profile_id) void workspace.activate(item.profile_id);
      }}
      onDeleted={handleCvManagerDeleted}
      onProfileApproved={onProfileApproved}
      onProfileDiscarded={handleProfileReviewDiscarded}
    />
  );

  return {sideNav, workspacePanel, drawer, legacySidebar};
}
