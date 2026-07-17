/**
 * Plan 4/8/9 shell: AppShell + SideNav CV/observability sidebar + ChatPage.
 * Profile fetch/upload state lives outside the SSE reducer.
 * Observability tab/cache/collapse state is owned by the sidebar composition.
 * Shared upload endpoint for sidebar and composer; sidebar success starts
 * one concise chat turn carrying only the returned attachment_id.
 * CV Manager reprocess delegates SSE to ChatPage (sole stream/reducer path).
 */

import {useCallback, useRef, useState} from 'react';
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

export {SIDEBAR_CV_TURN_MESSAGE} from '../features/profile/api';

export type AppDeps = {
  chat?: ChatPageDeps;
  sidebar?: CvSidebarDeps;
};

export type AppProps = {
  deps?: AppDeps;
};

/** Concise user-visible reprocess intent (domain-agnostic; attachment_id drives tools). */
export const CV_REPROCESS_TURN_MESSAGE =
  'Re-extract the retained CV and prepare the current draft for approval.';

export function App({deps}: AppProps = {}) {
  const [uploadLocked, setUploadLocked] = useState(false);
  const [profileRefreshKey, setProfileRefreshKey] = useState(0);
  const [sidebarTurn, setSidebarTurn] =
    useState<SidebarAttachmentTurnRequest | null>(null);
  const [reprocessRequest, setReprocessRequest] =
    useState<CvReprocessRequest | null>(null);
  const [reprocessTerminal, setReprocessTerminal] =
    useState<CvReprocessTerminalNotice | null>(null);
  /** Bumps after activation/delete so sidebar invalidates profile + CV caches. */
  const [activationKey, setActivationKey] = useState(0);
  const requestKeyRef = useRef(0);

  const handleSidebarUploadSuccess = useCallback(
    (result: CvUploadResponse) => {
      setProfileRefreshKey((k) => k + 1);
      requestKeyRef.current += 1;
      setSidebarTurn({
        requestKey: requestKeyRef.current,
        attachmentId: result.attachment.id,
        message: SIDEBAR_CV_TURN_MESSAGE,
      });
    },
    [],
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
  const handleCvReprocess = useCallback((attachmentId: string): boolean => {
    requestKeyRef.current += 1;
    setReprocessRequest({
      requestKey: requestKeyRef.current,
      attachmentId,
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
      attachmentId: string,
      kind: CvReprocessTerminal,
      error?: {code: string; summary: string},
    ) => {
      setReprocessTerminal({requestKey, attachmentId, kind, error});
    },
    [],
  );

  /**
   * Save Profile success → reload profile summary and invalidate observability
   * caches so active badge / graph refresh only after approval.
   */
  const handleProfileSaved = useCallback(() => {
    setProfileRefreshKey((k) => k + 1);
    setActivationKey((k) => k + 1);
  }, []);

  /** Delete success → profile summary may change if only non-active rows removed. */
  const handleCvDeleted = useCallback(() => {
    setProfileRefreshKey((k) => k + 1);
  }, []);

  return (
    <AppShell
      contentPadding={0}
      height="fill"
      variant="surface"
      sideNav={
        <CvSidebar
          isUploadDisabled={uploadLocked}
          onSidebarUploadSuccess={handleSidebarUploadSuccess}
          onCvReprocess={handleCvReprocess}
          onCvDeleted={handleCvDeleted}
          reprocessTerminal={reprocessTerminal}
          refreshKey={profileRefreshKey}
          activationKey={activationKey}
          deps={deps?.sidebar}
        />
      }
    >
      <ChatPage
        deps={deps?.chat}
        onInteractionLockChange={setUploadLocked}
        sidebarAttachmentTurn={sidebarTurn}
        onSidebarAttachmentTurnHandled={handleSidebarTurnHandled}
        cvReprocessRequest={reprocessRequest}
        onCvReprocessHandled={handleCvReprocessHandled}
        onCvReprocessTerminal={handleCvReprocessTerminal}
        onProfileSaved={handleProfileSaved}
      />
    </AppShell>
  );
}
