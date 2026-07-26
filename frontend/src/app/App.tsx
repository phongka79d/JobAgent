/**
 * Plan 4/8/9 shell: AppShell + SideNav CV/observability sidebar + ChatPage.
 * Profile fetch/upload state lives outside the SSE reducer.
 * Observability tab/cache/collapse state is owned by the sidebar composition.
 * Shared upload endpoint for sidebar and composer; sidebar success starts
 * one concise chat turn carrying only the returned attachment_id.
 * CV Manager reprocess delegates SSE to ChatPage (sole stream/reducer path).
 */

import {useCallback, useMemo, useRef, useState} from 'react';
import {AppShell} from '@astryxdesign/core/AppShell';
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
} from '../features/cv-tailoring/state';
import type {CvTailoringApi} from '../features/cv-tailoring/api';
import {TailoringEditor} from '../features/cv-tailoring/TailoringEditor';
import {
  useProfileWorkspaceState,
  type ProfileWorkspaceApi,
} from '../features/profile/workspaceState';

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

export function App({deps}: AppProps = {}) {
  const [uploadLocked, setUploadLocked] = useState(false);
  const workspaceApi = useMemo(() => deps?.workspace ?? {}, [deps?.workspace]);
  const workspace = useProfileWorkspaceState(workspaceApi, uploadLocked);
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
  const freshTailoringJobId = selectedScorableJobId(savedJobs.state);
  const interactionLocked = uploadLocked || workspaceLocked || tailoringLocked;
  const [mainWorkspace, setMainWorkspace] = useState<MainWorkspace>({
    kind: 'chat',
  });
  const handleOpenTailoringEditor = useCallback(
    async (sessionId: string) => {
      if (await tailoring.openSession(sessionId)) {
        setMainWorkspace({kind: 'cv-tailoring', sessionId});
      }
    },
    [tailoring.openSession],
  );
  const handleCreateTailoredCv = useCallback(
    async (jobId: string) => {
      const sessionId = await tailoring.createSession({
        job_id: jobId,
        instruction: '',
      });
      if (sessionId !== null) {
        setMainWorkspace({kind: 'cv-tailoring', sessionId});
      }
    },
    [tailoring.createSession],
  );
  const handleCreateFreshTailoredCv = useCallback(() => {
    const instruction = tailoring.state.detail.data?.session.instruction?.trim() ?? '';
    if (instruction === '') return;
    void tailoring
      .createSession({job_id: freshTailoringJobId, instruction})
      .then((sessionId) => {
        if (sessionId !== null) {
          setMainWorkspace({kind: 'cv-tailoring', sessionId});
        }
      });
  }, [freshTailoringJobId, tailoring.createSession, tailoring.state.detail.data]);
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
      <VStack hidden={mainWorkspace.kind === 'cv-tailoring'} height="100%" width="100%">
        <ChatPage
          key={workspace.state.selectedConversationId ?? 'no-conversation'}
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
      </VStack>
      {mainWorkspace.kind === 'cv-tailoring' ? (
        <TailoringEditor
          controller={tailoring}
          onBackToChat={() => setMainWorkspace({kind: 'chat'})}
          onEditProfile={handleEditProfileFromTailoring}
          canCreateFresh={Boolean(tailoring.state.detail.data?.session.instruction?.trim())}
          onCreateFresh={handleCreateFreshTailoredCv}
        />
      ) : null}
    </AppShell>
  );
}
