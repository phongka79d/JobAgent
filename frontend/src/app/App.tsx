/**
 * Plan 4/8/9 shell: AppShell + product sidebar + ChatPage.
 * Profile fetch/upload state lives outside the SSE reducer.
 * Product destination and collapse state are owned by the sidebar composition.
 * Shared upload endpoint for sidebar and composer; sidebar success starts
 * one concise chat turn carrying only the returned attachment_id.
 * CV Manager owns direct profile re-extraction review; chat owns only chat turns.
 */

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useMediaQuery} from '@astryxdesign/core';
import {AppShell} from '@astryxdesign/core/AppShell';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Layout, LayoutContent, LayoutPanel} from '@astryxdesign/core/Layout';
import {ResizeHandle, useResizable} from '@astryxdesign/core/Resizable';
import {VStack} from '@astryxdesign/core/VStack';

import {
  ChatPage,
  type ChatPageDeps,
  type SidebarAttachmentTurnRequest,
} from '../features/chat/ChatPage';
import {SIDEBAR_CV_TURN_MESSAGE} from '../features/profile/api';
import {
  useCvSidebarWorkspace,
  type CvSidebarDeps,
} from '../features/profile/CvSidebar';
import type {CvUploadResponse} from '../features/profile/types';
import {useCvManagerState} from '../features/cv-manager/state';
import type {CvManagerApi} from '../features/cv-manager/api';
import {
  useSavedJobsState,
  type SavedJobsController,
} from '../features/jobs/savedJobsState';
import type {SavedJobsApi} from '../features/jobs/api';
import {
  useCvTailoringState,
  type CvTailoringController,
} from '../features/cv-tailoring/state';
import type {CvTailoringApi} from '../features/cv-tailoring/api';
import {TailoringEditor} from '../features/cv-tailoring/TailoringEditor';
import type {CreateTailoringSessionRequest} from '../features/cv-tailoring/types';
import {
  useProfileWorkspaceState,
  type ProfileWorkspaceApi,
} from '../features/profile/workspaceState';
import {useWorkspaceLifecycle} from '../features/profile/useWorkspaceLifecycle';
import type {ProductDestination} from '../features/navigation/productNavigation';

export {SIDEBAR_CV_TURN_MESSAGE} from '../features/profile/api';

export type AppDeps = {
  chat?: ChatPageDeps;
  sidebar?: CvSidebarDeps;
  workspace?: Partial<ProfileWorkspaceApi>;
  savedJobs?: Partial<SavedJobsApi>;
  tailoring?: Partial<CvTailoringApi>;
  cvManager?: Partial<CvManagerApi>;
};

export type AppProps = {
  deps?: AppDeps;
};

export type MainWorkspace =
  | {kind: 'chat'}
  | {kind: 'cv-tailoring'; sessionId: string};

export function selectedScorableJobId(
  state: Pick<SavedJobsController['state'], 'list' | 'selectedJobId'>,
): string | null {
  const selected = state.list.data?.items.find(
    (item) => item.id === state.selectedJobId,
  );
  return selected?.processing_status === 'processed' &&
    (selected.jd_quality === 'full' || selected.jd_quality === 'partial')
    ? selected.id
    : null;
}

export function freshTailoringRequest(
  state: Pick<SavedJobsController['state'], 'list' | 'selectedJobId'>,
  retainedInstruction: string,
): CreateTailoringSessionRequest | null {
  const jobId = selectedScorableJobId(state);
  const instruction = retainedInstruction.trim();
  return jobId !== null || instruction !== ''
    ? {job_id: jobId, instruction}
    : null;
}

export async function reloadLatestTailoring(
  controller: {
    readonly state: Pick<
      CvTailoringController['state'],
      'draft' | 'selectedSessionId'
    >;
    readonly openSession: CvTailoringController['openSession'];
    readonly setDraft: CvTailoringController['setDraft'];
  },
): Promise<boolean> {
  const {draft, selectedSessionId} = controller.state;
  if (draft === null || selectedSessionId === null) return false;
  if (!(await controller.openSession(selectedSessionId))) return false;
  controller.setDraft(draft);
  return true;
}

function WorkspaceStatus({
  title,
  actionLabel,
  onAction,
}: {
  title: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <VStack align="center" justify="center" height="100%" width="100%">
      <Banner
        status={actionLabel ? 'error' : 'info'}
        title={title}
        endContent={
          actionLabel && onAction ? (
            <Button
              label={actionLabel}
              variant="secondary"
              onClick={onAction}
            />
          ) : undefined
        }
      />
    </VStack>
  );
}

export function App({deps}: AppProps = {}) {
  const [uploadLocked, setUploadLocked] = useState(false);
  const isCompactWorkspace = useMediaQuery('(max-width: 64rem)');
  const productWorkspacePanel = useResizable({
    defaultSize: 420,
    minSizePx: 320,
    maxSizePx: 720,
    autoSaveId: 'jobagent-product-workspace-panel-width-v1',
  });
  const workspaceApi = useMemo(() => deps?.workspace ?? {}, [deps?.workspace]);
  const workspace = useProfileWorkspaceState(workspaceApi, uploadLocked);
  useWorkspaceLifecycle(workspace.reload);
  const workspaceScope =
    workspace.state.phase + ':' + (workspace.state.activeProfileId ?? 'none');
  const workspaceScopeRef = useRef(workspaceScope);
  const workspaceScopeChanged = workspaceScopeRef.current !== workspaceScope;
  workspaceScopeRef.current = workspaceScope;
  const workspaceLocked = workspace.state.pending.size > 0;
  const [profileRefreshKey, setProfileRefreshKey] = useState(0);
  const [sidebarTurn, setSidebarTurn] =
    useState<SidebarAttachmentTurnRequest | null>(null);
  const [cvManagerRequest, setCvManagerRequest] = useState<{
    requestKey: number;
    profileId: string;
    startAt: 'reextract';
  } | null>(null);
  const [cvManagerOpenRequest, setCvManagerOpenRequest] = useState<{
    requestKey: number;
    profileId: string;
  } | null>(null);
  /** Bumps after activation/delete so sidebar invalidates profile + CV caches. */
  const [activationKey, setActivationKey] = useState(0);
  /**
   * Bumps after activation / chat zero-result save/evaluate so an open Saved
   * Jobs destination refreshes without remounting the App-owned controller.
   */
  const [savedJobsInvalidateKey, setSavedJobsInvalidateKey] = useState(0);
  const requestKeyRef = useRef(0);
  const cvManagerOpenRequestKeyRef = useRef(0);
  const selectedProfile = workspace.state.profiles.find(
    (profile) => profile.id === workspace.state.activeProfileId,
  );
  const savedJobs: SavedJobsController = useSavedJobsState({
    api: deps?.savedJobs,
    profileId: selectedProfile?.id ?? null,
    profileReady: selectedProfile?.state === 'ready',
  });
  const tailoring = useCvTailoringState({
    profileId: selectedProfile?.id ?? null,
    profileReady: selectedProfile?.state === 'ready',
    api: deps?.tailoring,
  });
  const cvManager = useCvManagerState({
    api: deps?.cvManager ?? deps?.sidebar?.cvManager,
    profileId: selectedProfile?.id ?? null,
    profileReady: selectedProfile?.state === 'ready',
  });
  const tailoringLocked = tailoring.state.stream.phase === 'loading';
  const reextractLocked = cvManager.state.reextract?.operation?.state === 'running';
  const currentFreshTailoringRequest = freshTailoringRequest(
    savedJobs.state,
    tailoring.state.detail.data?.session.instruction ?? '',
  );
  const interactionLocked = uploadLocked || workspaceLocked || tailoringLocked || reextractLocked;
  const [mainWorkspace, setMainWorkspace] = useState<MainWorkspace>({
    kind: 'chat',
  });
  const [productDestination, setProductDestination] =
    useState<ProductDestination>('overview');
  useEffect(() => {
    if (workspaceScopeChanged) {
      setMainWorkspace({kind: 'chat'});
      setCvManagerOpenRequest(null);
    }
  }, [workspaceScope, workspaceScopeChanged]);
  const showTailoringEditor =
    workspace.state.phase === 'ready' &&
    !workspaceScopeChanged &&
    mainWorkspace.kind === 'cv-tailoring';
  const handleOpenTailoringEditor = useCallback(
    async (sessionId: string) => {
      const requestScope = workspaceScopeRef.current;
      if (
        (await tailoring.openSession(sessionId)) &&
        requestScope === workspaceScopeRef.current
      ) {
        setMainWorkspace({kind: 'cv-tailoring', sessionId});
      }
    },
    [tailoring.openSession],
  );
  const handleCreateTailoredCv = useCallback(
    async (jobId: string) => {
      const requestScope = workspaceScopeRef.current;
      const sessionId = await tailoring.createSession({
        job_id: jobId,
        instruction: '',
      });
      if (sessionId !== null && requestScope === workspaceScopeRef.current) {
        setMainWorkspace({kind: 'cv-tailoring', sessionId});
      }
    },
    [tailoring.createSession],
  );
  const handleCreateFreshTailoredCv = useCallback(() => {
    if (currentFreshTailoringRequest === null) return;
    const requestScope = workspaceScopeRef.current;
    void tailoring
      .createSession(currentFreshTailoringRequest)
      .then((sessionId) => {
        if (sessionId !== null && requestScope === workspaceScopeRef.current) {
          setMainWorkspace({kind: 'cv-tailoring', sessionId});
        }
      });
  }, [currentFreshTailoringRequest, tailoring.createSession]);
  const handleReloadLatestTailoring = useCallback(() => {
    void reloadLatestTailoring(tailoring);
  }, [tailoring]);
  const openCvManager = useCallback((request: {profileId: string; startAt: 'reextract'}) => {
    requestKeyRef.current += 1;
    setCvManagerRequest({requestKey: requestKeyRef.current, ...request});
  }, []);

  const handleCvManagerRequestHandled = useCallback((requestKey: number) => {
    setCvManagerRequest((current) => current?.requestKey === requestKey ? null : current);
  }, []);

  const handleEditProfileFromTailoring = useCallback(() => {
    if (selectedProfile?.id) openCvManager({profileId: selectedProfile.id, startAt: 'reextract'});
  }, [openCvManager, selectedProfile?.id]);

  const handleSidebarUploadSuccess = useCallback(
    (result: CvUploadResponse) => {
      setProfileRefreshKey((k) => k + 1);
      if (result.bootstrap === null) {
        return;
      }
      workspace.adoptBootstrap(result.bootstrap);
      if (!result.bootstrap.start_extraction) {
        setSidebarTurn(null);
        return;
      }
      requestKeyRef.current += 1;
      setSidebarTurn({
        requestKey: requestKeyRef.current,
        attachmentId: result.attachment.id,
        message: SIDEBAR_CV_TURN_MESSAGE,
      });
    },
    [workspace.adoptBootstrap],
  );

  const handleSidebarTurnHandled = useCallback((requestKey: number) => {
    setSidebarTurn((current) =>
      current && current.requestKey === requestKey ? null : current,
    );
  }, []);

  /**
   * Save Profile success → one coherent activation fan-out: profile refresh,
   * product-data invalidation and Saved Job currentness invalidation
   * (no remount; no automatic evaluate).
   */
  const handleProfileSaved = useCallback(() => {
    setProfileRefreshKey((k) => k + 1);
    setActivationKey((k) => k + 1);
    savedJobs.invalidateCurrentness();
    setSavedJobsInvalidateKey((k) => k + 1);
    void workspace.reload();
  }, [savedJobs.invalidateCurrentness, workspace.reload]);

  /** Delete success → profile summary may change if only non-active rows removed. */
  const handleCvDeleted = useCallback(() => {
    setProfileRefreshKey((k) => k + 1);
  }, []);

  const openExistingCvManagerOperation = useCallback(async (profileId: string, operationId: string): Promise<boolean> => {
    if (profileId !== selectedProfile?.id || !operationId) return false;
    const opened = await cvManager.open(operationId);
    return opened;
  }, [cvManager, selectedProfile?.id]);

  const openAgentPendingReview = useCallback(async (profileId: string, reviewRevision: string): Promise<boolean> => {
    if (profileId !== selectedProfile?.id || !reviewRevision) return false;
    const opened = await cvManager.loadReview(profileId, reviewRevision, null);
    return opened;
  }, [cvManager, selectedProfile?.id]);

  const openExistingCvManagerOperationFromChat = useCallback(async (profileId: string, operationId: string): Promise<boolean> => {
    const opened = await openExistingCvManagerOperation(profileId, operationId);
    if (opened) {
      cvManagerOpenRequestKeyRef.current += 1;
      setCvManagerOpenRequest({requestKey: cvManagerOpenRequestKeyRef.current, profileId});
    }
    return opened;
  }, [openExistingCvManagerOperation]);

  const openAgentPendingReviewFromChat = useCallback(async (profileId: string, reviewRevision: string): Promise<boolean> => {
    const opened = await openAgentPendingReview(profileId, reviewRevision);
    if (opened) {
      cvManagerOpenRequestKeyRef.current += 1;
      setCvManagerOpenRequest({requestKey: cvManagerOpenRequestKeyRef.current, profileId});
    }
    return opened;
  }, [openAgentPendingReview]);

  const handleProfileReviewDiscarded = useCallback(() => {
    setProfileRefreshKey((k) => k + 1);
  }, []);

  const handleSavedJobsInvalidated = useCallback(() => {
    savedJobs.invalidateCurrentness();
    setSavedJobsInvalidateKey((k) => k + 1);
  }, [savedJobs.invalidateCurrentness]);

  const cvSidebar = useCvSidebarWorkspace({
    isUploadDisabled: interactionLocked,
    cvManager,
    cvManagerOpenRequest,
    onProfileReextractConflict: (operationId) => openExistingCvManagerOperation(selectedProfile?.id ?? '', operationId),
    onAgentPendingReview: openAgentPendingReview,
    onSidebarUploadSuccess: handleSidebarUploadSuccess,
    onCvDeleted: handleCvDeleted,
    onProfileApproved: handleProfileSaved,
    onProfileDiscarded: handleProfileReviewDiscarded,
    cvManagerRequest,
    onCvManagerRequestHandled: handleCvManagerRequestHandled,
    refreshKey: profileRefreshKey,
    activationKey,
    savedJobsInvalidateKey,
    workspace,
    savedJobs,
    onCreateTailoredCv: (jobId) => {
      void handleCreateTailoredCv(jobId);
    },
    isTailoringPending: tailoringLocked,
    tailoring,
    onOpenTailoringSession: (sessionId) => {
      void handleOpenTailoringEditor(sessionId);
    },
    editorMode: mainWorkspace.kind === 'cv-tailoring',
    selectedDestination: productDestination,
    onSelectedDestinationChange: setProductDestination,
    deps: deps?.sidebar,
  });
  const showProductWorkspacePanel =
    !showTailoringEditor && !isCompactWorkspace;

  return (
    <AppShell
      contentPadding={0}
      height="fill"
      variant="surface"
      data-main-workspace={mainWorkspace.kind}
      sideNav={cvSidebar.sideNav}
    >
      <Layout
        height="fill"
        start={
          showProductWorkspacePanel ? (
            <>
              <LayoutPanel
                className="jobagent-hidden-scrollbar"
                data-testid="jobagent-product-workspace-panel"
                hasDivider={false}
                label="JobAgent workspace"
                padding={0}
                resizable={productWorkspacePanel.props}
                role="complementary"
              >
                {cvSidebar.workspacePanel}
              </LayoutPanel>
              <ResizeHandle
                direction="horizontal"
                hasDivider
                label="Resize workspace panel"
                resizable={productWorkspacePanel.props}
              />
            </>
          ) : undefined
        }
        content={
          <LayoutContent
            className="jobagent-main-workspace jobagent-hidden-scrollbar"
            label="Main workspace"
            padding={0}
          >
            <VStack
              className="jobagent-chat-workspace jobagent-hidden-scrollbar"
              hidden={showTailoringEditor}
              height="100%"
              width="100%"
            >
              {workspace.state.phase === 'ready' ? (
                <ChatPage
                  key={`${workspace.state.activeProfileId ?? 'no-profile'}:${workspace.state.selectedConversationId ?? 'no-conversation'}`}
                  conversationId={workspace.state.selectedConversationId}
                  selectedProfileState={selectedProfile?.state ?? null}
                  selectedProfileSetupStatus={selectedProfile?.setup_status ?? null}
                  selectedJobId={savedJobs.state.selectedJobId}
                  deps={deps?.chat}
                  onInteractionLockChange={setUploadLocked}
                  uploadDisabled={interactionLocked}
                  onProfileReextractConflict={openExistingCvManagerOperationFromChat}
                  onAgentPendingReview={openAgentPendingReviewFromChat}
                  sidebarAttachmentTurn={sidebarTurn}
                  onSidebarAttachmentTurnHandled={handleSidebarTurnHandled}
                  onProfileSaved={handleProfileSaved}
                  onProfileSetupChanged={workspace.reload}
                  onCvUploadSuccess={handleSidebarUploadSuccess}
                  onSavedJobsInvalidated={handleSavedJobsInvalidated}
                  onOpenTailoringEditor={(sessionId) => {
                    void handleOpenTailoringEditor(sessionId);
                  }}
                />
              ) : workspace.state.phase === 'rehydrating' ? (
                <WorkspaceStatus title="Loading your workspace..." />
              ) : (
                <WorkspaceStatus
                  title="Your workspace could not be loaded"
                  actionLabel="Retry"
                  onAction={() => void workspace.reload()}
                />
              )}
            </VStack>
            {showTailoringEditor ? (
              <TailoringEditor
                controller={tailoring}
                onBackToChat={() => setMainWorkspace({kind: 'chat'})}
                onEditProfile={handleEditProfileFromTailoring}
                canCreateFresh={currentFreshTailoringRequest !== null}
                onCreateFresh={handleCreateFreshTailoredCv}
                onReloadLatest={handleReloadLatestTailoring}
              />
            ) : null}
          </LayoutContent>
        }
      />
      {cvSidebar.drawer}
    </AppShell>
  );
}
