/**
 * Plan 4/8/9 shell: AppShell + product sidebar + ChatPage.
 * Profile fetch/upload state lives outside the SSE reducer.
 * Product destination and collapse state are owned by the sidebar composition.
 * Shared upload endpoint for sidebar and composer; sidebar success starts
 * one concise chat turn carrying only the returned attachment_id.
 * CV Manager reprocess delegates SSE to ChatPage (sole stream/reducer path).
 */

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {AppShell} from '@astryxdesign/core/AppShell';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {VStack} from '@astryxdesign/core/VStack';

import {
  ChatPage,
  type ChatPageDeps,
  type CvReprocessRequest,
  type CvReprocessTerminal,
  type SidebarAttachmentTurnRequest,
} from '../features/chat/ChatPage';
import {SIDEBAR_CV_TURN_MESSAGE} from '../features/profile/api';
import {
  CvSidebar,
  type CvSidebarDeps,
  type CvReprocessTerminalNotice,
} from '../features/profile/CvSidebar';
import type {CvUploadResponse} from '../features/profile/types';
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

export {SIDEBAR_CV_TURN_MESSAGE} from '../features/profile/api';

export type AppDeps = {
  chat?: ChatPageDeps;
  sidebar?: CvSidebarDeps;
  workspace?: Partial<ProfileWorkspaceApi>;
  savedJobs?: Partial<SavedJobsApi>;
  tailoring?: Partial<CvTailoringApi>;
};

export type AppProps = {
  deps?: AppDeps;
};

/** Concise user-visible reprocess intent (domain-agnostic; attachment_id drives tools). */
export const CV_REPROCESS_TURN_MESSAGE =
  'Re-extract the retained CV and prepare the current draft for approval.';

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
  const [reprocessRequest, setReprocessRequest] =
    useState<CvReprocessRequest | null>(null);
  const [reprocessTerminal, setReprocessTerminal] =
    useState<CvReprocessTerminalNotice | null>(null);
  /** Bumps after activation/delete so sidebar invalidates profile + CV caches. */
  const [activationKey, setActivationKey] = useState(0);
  /**
   * Bumps after activation / chat zero-result save/evaluate so sidebar-local
   * saved-JD list/detail currentness invalidates without remounting the sidebar.
   */
  const [savedJobsInvalidateKey, setSavedJobsInvalidateKey] = useState(0);
  const requestKeyRef = useRef(0);
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
  const tailoringLocked = tailoring.state.stream.phase === 'loading';
  const currentFreshTailoringRequest = freshTailoringRequest(
    savedJobs.state,
    tailoring.state.detail.data?.session.instruction ?? '',
  );
  const interactionLocked = uploadLocked || workspaceLocked || tailoringLocked;
  const [mainWorkspace, setMainWorkspace] = useState<MainWorkspace>({
    kind: 'chat',
  });
  useEffect(() => {
    if (workspaceScopeChanged) {
      setMainWorkspace({kind: 'chat'});
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
  const handleEditProfileFromTailoring = useCallback(() => {
    setMainWorkspace({kind: 'chat'});
    queueMicrotask(() => {
      requestAnimationFrame(() => {
        const composer = document.querySelector(
          '[data-testid="jobagent-chat-composer-input"]',
        );
        if (composer instanceof HTMLElement) composer.focus();
      });
    });
  }, []);

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
   * CV Manager re-extract → ChatPage profile stream (same SSE callbacks/reducer).
   * Returns false when composition should refuse (caller already pending).
   */
  const handleCvReprocess = useCallback((profileId: string): boolean => {
    requestKeyRef.current += 1;
    setReprocessRequest({
      requestKey: requestKeyRef.current,
      profileId,
      message: CV_REPROCESS_TURN_MESSAGE,
    });
    return true;
  }, []);

  const handleCvReprocessHandled = useCallback((requestKey: number) => {
    setReprocessRequest((current) =>
      current && current.requestKey === requestKey ? null : current,
    );
  }, []);

  const handleCvReprocessTerminal = useCallback(
    (
      requestKey: number,
      profileId: string,
      kind: CvReprocessTerminal,
      error?: {code: string; summary: string},
    ) => {
      setReprocessTerminal({requestKey, profileId, kind, error});
    },
    [],
  );

  /**
   * Save Profile success → one coherent activation fan-out: profile refresh,
   * observability CV/chunk/run/graph invalidation, and saved-JD currentness
   * invalidation (no remount; no automatic evaluate).
   */
  const handleProfileSaved = useCallback(() => {
    setProfileRefreshKey((k) => k + 1);
    setActivationKey((k) => k + 1);
    setSavedJobsInvalidateKey((k) => k + 1);
    void workspace.reload();
  }, [workspace.reload]);

  /** Delete success → profile summary may change if only non-active rows removed. */
  const handleCvDeleted = useCallback(() => {
    setProfileRefreshKey((k) => k + 1);
  }, []);

  const handleSavedJobsInvalidated = useCallback(() => {
    setSavedJobsInvalidateKey((k) => k + 1);
  }, []);

  return (
    <AppShell
      contentPadding={0}
      height="fill"
      variant="surface"
      data-main-workspace={mainWorkspace.kind}
      sideNav={
        <CvSidebar
          isUploadDisabled={interactionLocked}
          onSidebarUploadSuccess={handleSidebarUploadSuccess}
          onCvReprocess={handleCvReprocess}
          onCvDeleted={handleCvDeleted}
          reprocessTerminal={reprocessTerminal}
          refreshKey={profileRefreshKey}
          activationKey={activationKey}
          savedJobsInvalidateKey={savedJobsInvalidateKey}
          workspace={workspace}
          savedJobs={savedJobs}
          onCreateTailoredCv={(jobId) => {
            void handleCreateTailoredCv(jobId);
          }}
          isTailoringPending={tailoringLocked}
          tailoring={tailoring}
          onOpenTailoringSession={(sessionId) => {
            void handleOpenTailoringEditor(sessionId);
          }}
          deps={deps?.sidebar}
        />
      }
    >
      <VStack
        className="jobagent-chat-workspace"
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
            sidebarAttachmentTurn={sidebarTurn}
            onSidebarAttachmentTurnHandled={handleSidebarTurnHandled}
            cvReprocessRequest={reprocessRequest}
            onCvReprocessHandled={handleCvReprocessHandled}
            onCvReprocessTerminal={handleCvReprocessTerminal}
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
    </AppShell>
  );
}
