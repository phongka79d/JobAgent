/**
 * Plan 4 shell: AppShell + SideNav CV sidebar + ChatPage.
 * Profile fetch/upload state lives outside the SSE reducer.
 * Shared upload endpoint for sidebar and composer; sidebar success starts
 * one concise chat turn carrying only the returned attachment_id.
 */

import {useCallback, useRef, useState} from 'react';
import {AppShell} from '@astryxdesign/core/AppShell';

import {
  ChatPage,
  type ChatPageDeps,
  type SidebarAttachmentTurnRequest,
} from '../features/chat/ChatPage';
import {SIDEBAR_CV_TURN_MESSAGE} from '../features/profile/api';
import {
  CvSidebar,
  type CvSidebarDeps,
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

export function App({deps}: AppProps = {}) {
  const [uploadLocked, setUploadLocked] = useState(false);
  const [profileRefreshKey, setProfileRefreshKey] = useState(0);
  const [sidebarTurn, setSidebarTurn] =
    useState<SidebarAttachmentTurnRequest | null>(null);
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

  /** Save Profile success → reload approved sidebar state (filename/title). */
  const handleProfileSaved = useCallback(() => {
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
          refreshKey={profileRefreshKey}
          deps={deps?.sidebar}
        />
      }
    >
      <ChatPage
        deps={deps?.chat}
        onInteractionLockChange={setUploadLocked}
        sidebarAttachmentTurn={sidebarTurn}
        onSidebarAttachmentTurnHandled={handleSidebarTurnHandled}
        onProfileSaved={handleProfileSaved}
      />
    </AppShell>
  );
}
