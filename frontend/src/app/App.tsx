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
  useProfileWorkspaceState,
  type ProfileWorkspaceApi,
} from '../features/profile/workspaceState';

export {SIDEBAR_CV_TURN_MESSAGE} from '../features/profile/api';

export type AppDeps = {
  chat?: ChatPageDeps;
  sidebar?: CvSidebarDeps;
  workspace?: Partial<ProfileWorkspaceApi>;
};

export type AppProps = {
  deps?: AppDeps;
};

/** Concise user-visible reprocess intent (domain-agnostic; attachment_id drives tools). */
export const CV_REPROCESS_TURN_MESSAGE =
  'Re-extract the retained CV and prepare the current draft for approval.';

export function App({deps}: AppProps = {}) {
  const [uploadLocked, setUploadLocked] = useState(false);
  const workspaceApi = useMemo(() => deps?.workspace ?? {}, [deps?.workspace]);
  const workspace = useProfileWorkspaceState(workspaceApi, uploadLocked);
  const workspaceLocked = workspace.state.pending.size > 0;
  const interactionLocked = uploadLocked || workspaceLocked;
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
   * CV Manager reprocess → ChatPage streamCvReprocess (same SSE callbacks/reducer).
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
          deps={deps?.sidebar}
        />
      }
    >
      <ChatPage
        key={workspace.state.selectedConversationId ?? 'no-conversation'}
        conversationId={workspace.state.selectedConversationId}
        selectedProfileState={selectedProfile?.state ?? null}
        selectedProfileSetupStatus={selectedProfile?.setup_status ?? null}
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
      />
    </AppShell>
  );
}
